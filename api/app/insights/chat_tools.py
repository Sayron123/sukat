"""The report functions, wrapped as tools the AI chat can call.

Each tool has a name, a description for the model, and a Pydantic input model (its JSON
schema is what the model sees). The server runs the tool with the store_id and role
from the caller's token: tool inputs never carry a store or user, and unknown fields
(like a "store_id" the model made up) are refused by the input model.

A tool returns a ToolOutcome:
- `content`: JSON text for the model. Amounts get a peso string next to them
  ("total_centavos": 125050, "total_peso": "₱1,250.50") so the model never does math.
- `data`: the report's own Pydantic result, used for the table/chart on screen, so the
  numbers shown come from the database, never from the model's text.

stock_check is deliberately not a tool: it's a manager's audit, not a chat question.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.insights import reports
from app.insights.schemas import (
    DateRange,
    LowStockItem,
    MovementFilters,
    MovementKind,
    TopBy,
)
from app.products.service import ProductSearch, search_products
from app.stores.models import Role

NOT_ALLOWED = "not allowed for your role"
FIND_PRODUCT_MAX = 5
ALL_ROLES = frozenset({Role.MANAGER, Role.SECRETARY, Role.MEMBER})
WRITERS = frozenset({Role.MANAGER, Role.SECRETARY})


@dataclass(frozen=True)
class ToolContext:
    """Who is asking. Built by the server from the verified token, never from the model."""

    db: Session
    store_id: UUID
    role: str
    now: datetime | None = None  # tests pin the clock; None = real time


@dataclass
class ToolOutcome:
    ok: bool
    content: str  # JSON text sent back to the model
    data: BaseModel | None = None  # the report result (for the on-screen table/chart)
    error: str | None = None
    args: BaseModel | None = None  # the validated input, e.g. which dates were asked


# ---------- inputs (what the model may send) ----------

_START = "First day, YYYY-MM-DD, store time (Asia/Manila). Omit start and end for today."
_START_ALL = "First day, YYYY-MM-DD, store time (Asia/Manila). Omit start and end for all time."
_END = "Last day (included), YYYY-MM-DD. Omit to use the same day as start."


class _In(BaseModel):
    # Refuse fields that aren't in the schema, e.g. a store_id or user_id the model
    # invented (or was talked into by text in a product name).
    model_config = ConfigDict(extra="forbid")


class SalesSummaryIn(_In):
    start: date | None = Field(None, description=_START)
    end: date | None = Field(None, description=_END)


class TopProductsIn(_In):
    start: date | None = Field(None, description=_START)
    end: date | None = Field(None, description=_END)
    by: TopBy = Field("qty", description='"qty" = most units sold, "revenue" = most pesos')
    limit: int = Field(5, ge=1, le=20, description="How many products, 1-20")


class LowStockIn(_In):
    pass


class StockMovementsIn(_In):
    start: date | None = Field(None, description=_START_ALL)
    end: date | None = Field(None, description=_END)
    product_id: UUID | None = Field(None, description="Only this product (from find_product)")
    kind: MovementKind | None = Field(
        None, description='"sale", "stock_in", "adjustment", or "void" (undone by a void)'
    )
    page: int = Field(1, ge=1, le=50, description="20 rows per page, newest first")


class ProductHistoryIn(_In):
    product_id: UUID = Field(description="The product's id, from find_product")
    start: date | None = Field(None, description=_START_ALL)
    end: date | None = Field(None, description=_END)
    page: int = Field(1, ge=1, le=50, description="20 rows per page, newest first")


class FindProductIn(_In):
    query: str = Field(
        min_length=1, max_length=80, description="Name or other name, e.g. 'sem' or 'pako 4'"
    )


# ---------- outputs that aren't report models already ----------


class LowStockResult(BaseModel):
    items: list[LowStockItem]
    count: int


class ProductMatch(BaseModel):
    product_id: UUID
    name: str
    category: str
    base_unit: str
    stock_qty: Decimal
    price_centavos: int | None  # per base unit
    low_stock_level: Decimal | None


class FindProductResult(BaseModel):
    query: str
    items: list[ProductMatch]  # best matches first, at most 5
    total_matches: int


# ---------- the tools ----------


def _range(start: date | None, end: date | None, default_today: bool) -> DateRange | None:
    return reports.make_range(start, end, default_today=default_today)


def _range_or_today(start: date | None, end: date | None) -> DateRange:
    period = reports.make_range(start, end, default_today=True)
    if period is None:  # make_range always returns a range with default_today=True
        raise RuntimeError("no date range")
    return period


def _sales_summary(ctx: ToolContext, args: SalesSummaryIn) -> BaseModel:
    period = _range_or_today(args.start, args.end)
    return reports.sales_summary(ctx.db, ctx.store_id, period, now=ctx.now)


def _top_products(ctx: ToolContext, args: TopProductsIn) -> BaseModel:
    period = _range_or_today(args.start, args.end)
    return reports.top_products(ctx.db, ctx.store_id, period, args.limit, args.by)


def _low_stock(ctx: ToolContext, args: LowStockIn) -> BaseModel:
    items = reports.low_stock(ctx.db, ctx.store_id)
    return LowStockResult(items=items, count=len(items))


def _stock_movements(ctx: ToolContext, args: StockMovementsIn) -> BaseModel:
    filters = MovementFilters(
        range=_range(args.start, args.end, default_today=False),
        product_id=args.product_id,
        kind=args.kind,
        page=args.page,
    )
    return reports.stock_movements(ctx.db, ctx.store_id, filters)


def _product_history(ctx: ToolContext, args: ProductHistoryIn) -> BaseModel:
    period = _range(args.start, args.end, default_today=False)
    return reports.product_history(ctx.db, ctx.store_id, args.product_id, period, args.page)


def _find_product(ctx: ToolContext, args: FindProductIn) -> BaseModel:
    rows, total = search_products(ctx.db, ctx.store_id, ProductSearch(q=args.query))
    return FindProductResult(
        query=args.query,
        items=[
            ProductMatch(
                product_id=p.id,
                name=p.name,
                category=p.category,
                base_unit=p.base_unit,
                stock_qty=p.stock_qty,
                price_centavos=p.price_centavos,
                low_stock_level=p.low_stock_level,
            )
            for p in rows[:FIND_PRODUCT_MAX]
        ],
        total_matches=total,
    )


@dataclass(frozen=True)
class ChatTool:
    name: str
    description: str
    input_model: type[_In]
    run: Callable[[ToolContext, Any], BaseModel]
    roles: frozenset[str] = field(default=ALL_ROLES)

    def spec(self) -> dict[str, Any]:
        """Provider-neutral definition: name, description, JSON schema of the input."""
        schema = self.input_model.model_json_schema()
        schema.pop("title", None)
        return {"name": self.name, "description": self.description, "input_schema": schema}


TOOLS: dict[str, ChatTool] = {
    t.name: t
    for t in (
        ChatTool(
            "sales_summary",
            "Total pesos and number of sales (voided sales excluded) for a date range, "
            "compared with an earlier period ('compared_to' says which, e.g. 'same time "
            "yesterday'). Use for: sales today, this week, yesterday vs today.",
            SalesSummaryIn,
            _sales_summary,
        ),
        ChatTool(
            "top_products",
            "Best-selling products in a date range, by quantity sold (in each product's "
            "base unit) or by revenue. Use for: best seller, top product, what sells most.",
            TopProductsIn,
            _top_products,
            roles=WRITERS,
        ),
        ChatTool(
            "low_stock",
            "Products at or below their low-stock alert level, lowest stock first. Use "
            "for: what's low, what to reorder, what's running out.",
            LowStockIn,
            _low_stock,
        ),
        ChatTool(
            "stock_movements",
            "Stock changes (sales, deliveries, adjustments, voids), newest first, 20 per "
            "page, each with the stock right after it. Filter by dates, product, or kind.",
            StockMovementsIn,
            _stock_movements,
        ),
        ChatTool(
            "product_history",
            "One product's stock changes, newest first, with the stock after each. Needs "
            "the product_id: call find_product first.",
            ProductHistoryIn,
            _product_history,
        ),
        ChatTool(
            "find_product",
            "Search this store's products by name or other name (aliases). Returns up to "
            "5 matches with product_id, current stock and price. Use to answer 'how many "
            "X do we have' and to get a product_id for product_history.",
            FindProductIn,
            _find_product,
        ),
    )
}


def tool_specs() -> list[dict[str, Any]]:
    """All tool definitions, in a fixed order (keeps the prompt cache stable)."""
    return [TOOLS[name].spec() for name in sorted(TOOLS)]


def _with_pesos(value: Any) -> Any:
    """Copy of JSON-ready data where every `x_centavos` number also gets `x_peso`."""
    if isinstance(value, list):
        return [_with_pesos(v) for v in value]
    if not isinstance(value, dict):
        return value
    out: dict[str, Any] = {}
    for key, v in value.items():
        out[key] = _with_pesos(v)
        if key.endswith("_centavos") and isinstance(v, int) and not isinstance(v, bool):
            out[key.removesuffix("_centavos") + "_peso"] = peso(v)
    return out


def peso(centavos: int) -> str:
    """125050 -> '₱1,250.50' (negative amounts get a minus sign)."""
    sign = "-" if centavos < 0 else ""
    whole, cents = divmod(abs(centavos), 100)
    return f"{sign}₱{whole:,}.{cents:02d}"


def _error(message: str) -> ToolOutcome:
    return ToolOutcome(ok=False, content=json.dumps({"error": message}), error=message)


def run_tool(ctx: ToolContext, name: str, raw_input: Any) -> ToolOutcome:
    """Run one tool call from the model. Never raises for bad input: the model gets an
    error it can explain or correct.

    Order: known tool -> role allowed -> input valid -> run (with ctx's store only).
    """
    tool = TOOLS.get(name)
    if tool is None:
        return _error(f"unknown tool {name!r}")
    if ctx.role not in tool.roles:
        return _error(NOT_ALLOWED)
    try:
        args = tool.input_model.model_validate(raw_input if raw_input is not None else {})
    except ValidationError as e:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in err['loc']) or 'input'}: {err['msg']}" for err in e.errors()
        )
        return _error(f"invalid input: {problems}")
    try:
        result = tool.run(ctx, args)
    except AppError as e:  # e.g. bad date range, product of another store (not found)
        return _error(str(e))
    payload = _with_pesos(result.model_dump(mode="json"))
    return ToolOutcome(
        ok=True, content=json.dumps(payload, ensure_ascii=False), data=result, args=args
    )
