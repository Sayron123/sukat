"""The AI chat: answer a staff member's question about their store with the report tools.

Flow for one question:
1. Take the last 10 messages from the browser (nothing is stored on the server).
2. Call the model with the fixed system prompt (prompts/chat.md), today's date and the
   user's role, and the tools.
3. While it asks for tools: run them with the store and role from the token, send the
   results back. At most 5 tool calls per question, all within one overall timeout.
4. Return its answer, plus a small table or chart built from the last tool result (the
   numbers on screen come from the database, not from the model's text).
5. Log the tokens and cost to ai_usage with feature "chat". The row is reserved before
   the call, which is also how the hourly limit per store is counted.
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from functools import cache
from pathlib import Path
from typing import Any
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.base import (
    AssistantText,
    ChatItem,
    ChatModel,
    ChatTurn,
    ToolResult,
    ToolResults,
    UserText,
)
from app.ai.budget import ensure_within_budget
from app.ai.errors import AIChatError
from app.ai.models import AIUsage
from app.ai.schemas import AIUsageInfo
from app.ai.usage import fill_usage, log_usage
from app.core.config import settings
from app.core.errors import AppError, TooManyRequests
from app.insights import reports
from app.insights.chat_schemas import ChatBar, ChatData, ChatMessageIn, ChatOut
from app.insights.chat_tools import (
    FindProductResult,
    LowStockResult,
    ToolContext,
    ToolOutcome,
    peso,
    run_tool,
    tool_specs,
)
from app.insights.schemas import DateRange, MovementPage, SalesSummary, TopProducts
from app.stores.models import Store

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).parent / "prompts" / "chat.md"
FEATURE = "chat"
FAILED_ATTEMPT_FEATURE = "chat_failed_attempt"
TABLE_ROWS = 10
MIN_CALL_SECONDS = 2.0  # don't start a model call with less time than this left
RATE_WINDOW = timedelta(hours=1)

TOO_SLOW = "Sorry, that took too long. Please try again, or ask a simpler question."
NO_ANSWER = "Sorry, I couldn't answer that. Please try asking another way."
REFUSED = "Sorry, I can't help with that one. I can answer questions about your sales and stock."
TOO_LONG = "Sorry, that answer got too long. Try asking about a shorter period or fewer items."


@cache
def system_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def request_context(role: str, now: datetime | None = None) -> str:
    """The per-request facts the model needs: today in store time, and the role."""
    today = reports.store_today(now)
    monday = today - timedelta(days=today.weekday())
    return (
        f"Today is {today:%A}, {today.isoformat()} (store time, Asia/Manila). "
        f"This week started on Monday {monday.isoformat()}. "
        f"This month started on {today.replace(day=1).isoformat()}. "
        f"The user's role is {role}."
    )


def history_items(messages: list[ChatMessageIn]) -> list[ChatItem]:
    """The last CHAT_HISTORY_MESSAGES messages, starting with a user message (the
    model's conversation must start with the user)."""
    recent = messages[-settings.CHAT_HISTORY_MESSAGES :]
    while recent and recent[0].role != "user":
        recent = recent[1:]
    return [UserText(m.content) if m.role == "user" else AssistantText(m.content) for m in recent]


def _add(a: AIUsageInfo | None, b: AIUsageInfo) -> AIUsageInfo:
    if a is None:
        return b
    return AIUsageInfo(
        model=b.model or a.model,
        provider=b.provider or a.provider,
        input_tokens=a.input_tokens + b.input_tokens,
        output_tokens=a.output_tokens + b.output_tokens,
        cache_write_tokens=a.cache_write_tokens + b.cache_write_tokens,
        cache_read_tokens=a.cache_read_tokens + b.cache_read_tokens,
    )


@dataclass
class ChatResult:
    answer: str
    data: ChatData | None
    tools_used: list[str]
    usage: AIUsageInfo | None  # None when no model call finished
    outcomes: list[tuple[str, ToolOutcome]] = field(default_factory=list)
    timed_out: bool = False


class ChatFailed(Exception):
    """The model call failed; `usage` holds what was spent before it did."""

    def __init__(self, error: AIChatError, usage: AIUsageInfo | None):
        super().__init__(str(error))
        self.error = error
        self.usage = usage


def run_chat(
    db: Session,
    store_id: UUID,
    role: str,
    messages: list[ChatMessageIn],
    model: ChatModel,
    now: datetime | None = None,
) -> ChatResult:
    """Answer the last user message. Does not log usage.

    Commits after each tool round to end the read transaction (the tools only read), so
    no pooled connection is held while the model thinks.

    @raises ChatFailed when a model call fails (with the usage spent so far)
    """
    ctx = ToolContext(db=db, store_id=store_id, role=role, now=now)
    items: list[ChatItem] = history_items(messages)
    specs = tool_specs()
    context = request_context(role, now)
    deadline = time.monotonic() + settings.AI_CHAT_TIMEOUT_SECONDS
    usage: AIUsageInfo | None = None
    outcomes: list[tuple[str, ToolOutcome]] = []
    calls = 0
    answer = NO_ANSWER
    timed_out = False

    # One model call per round: up to CHAT_MAX_TOOL_CALLS rounds with tools, then a
    # last one that must answer in text.
    for _ in range(settings.CHAT_MAX_TOOL_CALLS + 1):
        left = deadline - time.monotonic()
        if left < MIN_CALL_SECONDS:
            answer = TOO_SLOW
            timed_out = True
            break
        allow_tools = calls < settings.CHAT_MAX_TOOL_CALLS
        try:
            turn: ChatTurn = model.respond(
                system=system_prompt(),
                context=context,
                items=list(items),  # a copy: the list keeps growing after this call
                tools=specs,
                allow_tools=allow_tools,
                timeout=left,
            )
        except AIChatError as e:
            raise ChatFailed(e, _add(usage, e.usage) if e.usage else usage) from e
        usage = _add(usage, turn.usage)

        if turn.stop == "refusal":
            answer = REFUSED
            break
        if turn.stop == "tool_use" and turn.tool_calls and allow_tools:
            items.append(turn)
            results = []
            for call in turn.tool_calls:
                if calls >= settings.CHAT_MAX_TOOL_CALLS:
                    results.append(
                        ToolResult(
                            call.id,
                            '{"error": "tool call limit reached; answer with what you have"}',
                            is_error=True,
                        )
                    )
                    continue
                calls += 1
                outcome = run_tool(ctx, call.name, call.input)
                outcomes.append((call.name, outcome))
                results.append(ToolResult(call.id, outcome.content, is_error=not outcome.ok))
            items.append(ToolResults(results))
            db.commit()
            continue
        if turn.stop == "max_tokens":
            answer = TOO_LONG
        else:
            answer = turn.text or NO_ANSWER
        break

    return ChatResult(
        answer=answer,
        data=build_display(outcomes, reports.store_today(now)),
        tools_used=[name for name, _ in outcomes],
        usage=usage,
        outcomes=outcomes,
        timed_out=timed_out,
    )


class ChatRateLimited(TooManyRequests):
    code = "chat_rate_limited"


class ChatUnavailable(AppError):
    """The model couldn't answer (timeout, API error). `retryable` says if Retry may help."""

    status_code = 503
    code = "chat_unavailable"


def _clock(t: datetime) -> str:
    """'3:05 PM' in store time (no %-I: it doesn't exist on Windows)."""
    return t.astimezone(reports.STORE_TZ).strftime("%I:%M %p").lstrip("0")


def reserve_question(db: Session, store_id: UUID, now: datetime | None = None) -> AIUsage:
    """Count this question against the store's hourly limit and reserve its ai_usage
    row (filled with the real tokens and cost after the call). Commits.

    The store row is locked for the count, so two questions sent at the same moment
    can't both take the last slot.
    @raises AIBudgetReached when the store has used this month's AI budget
    @raises ChatRateLimited with the time a slot frees up
    """
    ensure_within_budget(db, store_id, now)
    now = now or datetime.now(UTC)
    limit = settings.CHAT_QUESTIONS_PER_HOUR
    db.execute(select(Store.id).where(Store.id == store_id).with_for_update())
    recent = db.scalars(
        select(AIUsage.created_at)
        .where(
            AIUsage.store_id == store_id,
            AIUsage.feature == FEATURE,
            AIUsage.created_at > now - RATE_WINDOW,
        )
        .order_by(AIUsage.created_at)
    ).all()
    if len(recent) >= limit:
        db.rollback()  # release the lock
        free_at = recent[len(recent) - limit] + RATE_WINDOW
        wait = max(1, int((free_at - now).total_seconds()))
        raise ChatRateLimited(
            f"Your store has asked {limit} questions in the last hour. "
            f"You can ask again at {_clock(free_at)}.",
            headers={"Retry-After": str(wait)},
            extra={"retry_at": free_at.isoformat()},
        )
    row = AIUsage(
        store_id=store_id,
        feature=FEATURE,
        provider=settings.AI_PROVIDER,
        model=settings.AI_MODEL,
        tokens_in=0,
        tokens_out=0,
        cost_centavos=Decimal(0),
        created_at=now,
    )
    db.add(row)
    db.commit()
    return row


def _run_with_backup(
    db: Session,
    store_id: UUID,
    role: str,
    messages: list[ChatMessageIn],
    model: ChatModel,
    backup: ChatModel | None,
    now: datetime | None,
) -> ChatResult:
    try:
        result = run_chat(db, store_id, role, messages, model, now)
    except ChatFailed as e:
        if backup is None or not e.error.retryable:
            raise
        db.rollback()
        logger.warning("Main AI provider failed a chat for store %s: %s", store_id, e)
        spent = e.usage
    else:
        if backup is None or not result.timed_out:
            return result
        logger.warning("Main AI provider ran out of time on a chat for store %s", store_id)
        spent = result.usage
    if spent is not None:
        log_usage(db, store_id, FAILED_ATTEMPT_FEATURE, spent)
    db.commit()
    return run_chat(db, store_id, role, messages, backup, now)


def ask(
    db: Session,
    store_id: UUID,
    role: str,
    messages: list[ChatMessageIn],
    model: ChatModel,
    backup: ChatModel | None = None,
    now: datetime | None = None,
) -> ChatOut:
    """Check the hourly limit, answer, and log the tokens and cost to ai_usage
    (feature "chat"), also when the model failed after spending tokens.

    @raises AIBudgetReached (429) when the store has used this month's AI budget
    @raises ChatRateLimited (429) when the store asked too many questions this hour
    @raises ChatUnavailable (503) when the model could not answer
    """
    row = reserve_question(db, store_id, now)
    try:
        result = _run_with_backup(db, store_id, role, messages, model, backup, now)
    except ChatFailed as e:
        db.rollback()  # nothing from the tools is kept; the row is re-read below
        if e.usage is not None:
            fill_usage(db.merge(row), e.usage)
            db.commit()
        raise ChatUnavailable(str(e.error), extra={"retryable": e.error.retryable}) from None
    if result.usage is not None:
        fill_usage(row, result.usage)
    db.commit()
    return ChatOut(answer=result.answer, data=result.data, tools_used=result.tools_used)


# ---------- the table / chart under the answer ----------


def qty_text(qty: Decimal) -> str:
    """Decimal("12.500") -> "12.5", Decimal("3.000") -> "3"."""
    text = f"{qty:f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def _day_text(day: date) -> str:
    return f"{day:%b} {day.day}"


def _range_label(period: DateRange, today: date) -> str:
    if period.start == period.end:
        if period.start == today:
            return "Today"
        if period.start == today - timedelta(days=1):
            return "Yesterday"
        return _day_text(period.start)
    return f"{_day_text(period.start)} – {_day_text(period.end)}"


def _sales_bars(s: SalesSummary, today: date) -> ChatData:
    previous = s.compared_to[:1].upper() + s.compared_to[1:]
    return ChatData(
        kind="bar",
        title="Sales",
        tool="sales_summary",
        basis="sales",
        range=s.range,
        bars=[
            ChatBar(
                label=previous,
                value=Decimal(s.previous.total_centavos),
                display=peso(s.previous.total_centavos),
            ),
            ChatBar(
                label=_range_label(s.range, today),
                value=Decimal(s.total_centavos),
                display=peso(s.total_centavos),
            ),
        ],
    )


def _top_bars(t: TopProducts) -> ChatData:
    by_qty = t.by == "qty"
    return ChatData(
        kind="bar",
        title="Top products by quantity" if by_qty else "Top products by revenue",
        tool="top_products",
        basis="sales",
        range=t.range,
        bars=[
            ChatBar(
                label=p.name,
                value=p.qty if by_qty else Decimal(p.revenue_centavos),
                display=f"{qty_text(p.qty)} {p.base_unit}" if by_qty else peso(p.revenue_centavos),
            )
            for p in t.items
        ],
    )


def _movement_table(name: str, page: MovementPage, period: DateRange | None) -> ChatData:
    rows = [
        [
            m.created_at.astimezone(reports.STORE_TZ).strftime("%b %d, %I:%M %p"),
            m.product_name,
            f"{'+' if m.qty_change > 0 else ''}{qty_text(m.qty_change)} {m.base_unit}",
            f"{qty_text(m.stock_after)} {m.base_unit}",
        ]
        for m in page.items[:TABLE_ROWS]
    ]
    return ChatData(
        kind="table",
        title="Stock changes",
        tool=name,
        basis="stock" if period else None,
        range=period,
        columns=["When", "Product", "Change", "Stock after"],
        rows=rows,
    )


def build_display(outcomes: list[tuple[str, ToolOutcome]], today: date) -> ChatData | None:
    """The table or chart for the answer: from the last successful tool result.
    find_product is only a lookup step, so it's used only when nothing else ran."""
    usable = [(n, o) for n, o in outcomes if o.ok and o.data is not None]
    if not usable:
        return None
    main = [(n, o) for n, o in usable if n != "find_product"]
    name, outcome = (main or usable)[-1]
    data: BaseModel | None = outcome.data
    if isinstance(data, SalesSummary):
        return _sales_bars(data, today)
    if isinstance(data, TopProducts):
        return _top_bars(data) if data.items else None
    if isinstance(data, LowStockResult):
        return ChatData(
            kind="table",
            title=f"Low stock ({data.count})",
            tool=name,
            columns=["Product", "Stock", "Alert at"],
            rows=[
                [
                    i.name,
                    f"{qty_text(i.stock_qty)} {i.base_unit}",
                    f"{qty_text(i.low_stock_level)} {i.base_unit}",
                ]
                for i in data.items[:TABLE_ROWS]
            ],
        )
    if isinstance(data, MovementPage):
        args: Any = outcome.args
        period = reports.make_range(args.start, args.end, default_today=False) if args else None
        return _movement_table(name, data, period) if data.items else None
    if isinstance(data, FindProductResult):
        if not data.items:
            return None
        return ChatData(
            kind="table",
            title="Products",
            tool=name,
            columns=["Product", "Stock", "Price"],
            rows=[
                [
                    p.name,
                    f"{qty_text(p.stock_qty)} {p.base_unit}",
                    f"{peso(p.price_centavos)}/{p.base_unit}"
                    if p.price_centavos is not None
                    else "—",
                ]
                for p in data.items
            ],
        )
    return None
