"""Products API. Every query is filtered by the caller's store_id from the token."""

import math
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import Select, case, exists, func, or_, select
from sqlalchemy.exc import IntegrityError

from app.auth.deps import CurrentMember, CurrentMemberDep, DbSession, require_role
from app.products.catalog import catalog_by_key, load_catalog
from app.products.constants import PAGE_SIZE
from app.products.models import Product, ProductAlias, UnitConversion
from app.products.schemas import (
    CatalogItemOut,
    Category,
    ConversionIn,
    ConversionOut,
    DroppedAlias,
    ImportIn,
    ImportOut,
    ProductCreate,
    ProductOut,
    ProductPage,
    ProductUpdate,
    SkippedItem,
)
from app.stores.models import Role

router = APIRouter(tags=["products"])

# Manager and secretary can change products; members can only read.
Writer = Annotated[CurrentMember, Depends(require_role(Role.MANAGER, Role.SECRETARY))]


# ---------- helpers ----------


def _out(p: Product) -> ProductOut:
    return ProductOut(
        id=p.id,
        name=p.name,
        category=p.category,
        base_unit=p.base_unit,
        price_centavos=p.price_centavos,
        stock_qty=p.stock_qty,
        low_stock_level=p.low_stock_level,
        is_low_stock=p.low_stock_level is not None and p.stock_qty <= p.low_stock_level,
        archived=p.archived,
        aliases=[a.alias for a in p.aliases],
        conversions=[ConversionOut(from_unit=c.from_unit, factor=c.factor) for c in p.conversions],
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


def _get_product(db: DbSession, store_id: UUID, product_id: UUID) -> Product:
    """A product of THIS store, else 404 (another store's product looks like it doesn't exist)."""
    product = db.scalar(
        select(Product).where(Product.id == product_id, Product.store_id == store_id)
    )
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
    return product


def _like_pattern(text: str) -> str:
    """'%text%' for LIKE, with LIKE's own wildcards escaped so "50%" matches literally."""
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _ensure_unique(
    db: DbSession,
    store_id: UUID,
    name: str | None,
    aliases: list[str] | None,
    exclude_id: UUID | None = None,
) -> None:
    """409 if the name or any alias is already used by ANOTHER product in this store.
    (The database also enforces this; checking first gives a clear message.)"""
    others = [Product.store_id == store_id]
    if exclude_id is not None:
        others.append(Product.id != exclude_id)
    if name is not None:
        taken = db.execute(
            select(Product.name, Product.archived).where(
                *others, func.lower(Product.name) == name.lower()
            )
        ).first()
        if taken:
            # Archived products are hidden from the list, so say so or the 409 looks wrong.
            hint = " (archived: unarchive it instead)" if taken.archived else ""
            raise HTTPException(
                status.HTTP_409_CONFLICT, f'A product named "{taken.name}" already exists{hint}'
            )
    if aliases:
        row = db.execute(
            select(ProductAlias.alias, Product.name)
            .join(Product, Product.id == ProductAlias.product_id)
            .where(*others, ProductAlias.alias.in_(aliases))
            .limit(1)
        ).first()
        if row:
            raise HTTPException(
                status.HTTP_409_CONFLICT, f'Alias "{row.alias}" is already used by "{row.name}"'
            )


def _set_aliases(product: Product, aliases: list[str]) -> None:
    """Make product.aliases equal `aliases`. Keeps unchanged rows instead of delete+insert,
    which would hit the unique constraint (SQLAlchemy inserts before it deletes)."""
    wanted = set(aliases)
    product.aliases[:] = [a for a in product.aliases if a.alias in wanted]
    have = {a.alias for a in product.aliases}
    for alias in aliases:
        if alias not in have:
            product.aliases.append(ProductAlias(store_id=product.store_id, alias=alias))


def _set_conversions(product: Product, conversions: list[ConversionIn]) -> None:
    """Same idea as _set_aliases: update factors in place, add new units, drop missing ones."""
    wanted = {c.from_unit: c.factor for c in conversions}
    product.conversions[:] = [c for c in product.conversions if c.from_unit in wanted]
    for conv in product.conversions:
        conv.factor = wanted.pop(conv.from_unit)
    for unit, factor in wanted.items():
        product.conversions.append(
            UnitConversion(store_id=product.store_id, from_unit=unit, factor=factor)
        )


def _commit_or_409(db: DbSession) -> None:
    """Commit; a unique-constraint race (two people saving at once) becomes a 409."""
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "That name or alias is already used in this store"
        ) from None


# ---------- products ----------


@router.get("/products", response_model=ProductPage)
def list_products(
    current: CurrentMemberDep,
    db: DbSession,
    q: Annotated[str | None, Query(max_length=80, description="Search name or alias")] = None,
    category: Category | None = None,
    low_stock: bool = False,
    include_archived: bool = False,
    # Upper bound keeps OFFSET inside Postgres' bigint range (huge values crashed with 500).
    page: Annotated[int, Query(ge=1, le=10_000)] = 1,
) -> ProductPage:
    """List this store's products, 20 per page, sorted by name.

    `q` matches anywhere in the name or any alias, ignoring case. Exact name/alias
    matches are listed first, so typing "sem" puts cement on top.
    """
    stmt: Select[tuple[Product]] = select(Product).where(Product.store_id == current.store_id)
    if not include_archived:
        stmt = stmt.where(Product.archived.is_(False))
    if category:
        stmt = stmt.where(Product.category == category)
    if low_stock:
        stmt = stmt.where(
            Product.low_stock_level.is_not(None), Product.stock_qty <= Product.low_stock_level
        )

    order = [func.lower(Product.name), Product.id]
    term = " ".join((q or "").split()).lower()
    if term:
        pattern = _like_pattern(term)

        def alias_matches(cond):
            return exists().where(
                ProductAlias.product_id == Product.id,
                ProductAlias.store_id == current.store_id,
                cond,
            )

        stmt = stmt.where(
            or_(
                func.lower(Product.name).like(pattern, escape="\\"),
                alias_matches(ProductAlias.alias.like(pattern, escape="\\")),
            )
        )
        exact = or_(func.lower(Product.name) == term, alias_matches(ProductAlias.alias == term))
        order.insert(0, case((exact, 0), else_=1))

    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    rows = db.scalars(stmt.order_by(*order).offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE)).all()
    return ProductPage(
        items=[_out(p) for p in rows],
        total=total,
        page=page,
        page_size=PAGE_SIZE,
        pages=max(1, math.ceil(total / PAGE_SIZE)),
    )


@router.post("/products", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
def create_product(body: ProductCreate, current: Writer, db: DbSession) -> ProductOut:
    _ensure_unique(db, current.store_id, body.name, body.aliases)
    product = Product(
        store_id=current.store_id,
        name=body.name,
        category=body.category,
        base_unit=body.base_unit,
        price_centavos=body.price_centavos,
        low_stock_level=body.low_stock_level,
    )
    db.add(product)
    db.flush()  # get product.id before adding children
    _set_aliases(product, body.aliases)
    _set_conversions(product, body.conversions)
    _commit_or_409(db)
    db.refresh(product)
    return _out(product)


@router.get("/products/{product_id}", response_model=ProductOut)
def get_product(product_id: UUID, current: CurrentMemberDep, db: DbSession) -> ProductOut:
    return _out(_get_product(db, current.store_id, product_id))


@router.patch("/products/{product_id}", response_model=ProductOut)
def update_product(
    product_id: UUID, body: ProductUpdate, current: Writer, db: DbSession
) -> ProductOut:
    """Change product details. stock_qty is NOT editable here; it changes only through
    stock movements (later phase)."""
    product = _get_product(db, current.store_id, product_id)
    fields = body.model_fields_set
    _ensure_unique(
        db,
        current.store_id,
        body.name if "name" in fields else None,
        body.aliases if "aliases" in fields else None,
        exclude_id=product.id,
    )
    if "base_unit" in fields and body.base_unit != product.base_unit:
        # stock_qty and every conversion factor are measured in the base unit, so changing
        # it would silently re-interpret them (50 kg would become "50 g").
        if product.stock_qty != 0:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"Can't change the base unit while there is stock "
                f"({product.stock_qty.normalize():f} {product.base_unit}). Bring stock to 0 first.",
            )
        if product.conversions and body.conversions is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "Changing the base unit changes what each conversion means. "
                "Send the conversions again for the new base unit.",
            )
    for field in ("name", "category", "base_unit", "price_centavos", "low_stock_level"):
        if field in fields:
            setattr(product, field, getattr(body, field))
    if body.aliases is not None:
        _set_aliases(product, body.aliases)
    if body.conversions is not None:
        _set_conversions(product, body.conversions)
    if any(c.from_unit == product.base_unit for c in product.conversions):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "A conversion cannot use the base unit itself"
        )
    _commit_or_409(db)
    db.refresh(product)
    return _out(product)


def _set_archived(product_id: UUID, current: CurrentMember, db: DbSession, value: bool):
    product = _get_product(db, current.store_id, product_id)
    product.archived = value
    db.commit()
    db.refresh(product)
    return _out(product)


@router.post("/products/{product_id}/archive", response_model=ProductOut)
def archive_product(product_id: UUID, current: Writer, db: DbSession) -> ProductOut:
    """Hide a product from the normal list. Nothing is deleted, so past sales stay valid."""
    return _set_archived(product_id, current, db, True)


@router.post("/products/{product_id}/unarchive", response_model=ProductOut)
def unarchive_product(product_id: UUID, current: Writer, db: DbSession) -> ProductOut:
    return _set_archived(product_id, current, db, False)


# ---------- starter catalog ----------


@router.get("/catalog", response_model=list[CatalogItemOut])
def get_catalog(current: CurrentMemberDep, db: DbSession) -> list[CatalogItemOut]:
    """All starter items, each marked if this store already has a product with that name."""
    existing = set(
        db.scalars(
            select(func.lower(Product.name)).where(Product.store_id == current.store_id)
        ).all()
    )
    return [
        CatalogItemOut(
            key=i.key,
            name=i.name,
            category=i.category,
            base_unit=i.base_unit,
            aliases=i.aliases,
            conversions=[
                ConversionOut(from_unit=c.from_unit, factor=c.factor) for c in i.conversions
            ],
            already_in_store=i.name.lower() in existing,
        )
        for i in load_catalog().items
    ]


@router.post("/products/import", response_model=ImportOut)
def import_catalog_items(body: ImportIn, current: Writer, db: DbSession) -> ImportOut:
    """Copy chosen starter items into this store as products (no prices, stock 0).

    - Items whose name already exists in the store are skipped (safe to run twice).
    - An alias already used by another product in the store is left off that item.
    All new products are saved in one transaction.
    """
    by_key = catalog_by_key()
    unknown = sorted({k for k in body.keys if k not in by_key})
    if unknown:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"Unknown catalog keys: {', '.join(unknown)}"
        )

    sid = current.store_id
    archived_by_name = dict(
        db.execute(
            select(func.lower(Product.name), Product.archived).where(Product.store_id == sid)
        ).all()
    )
    names = set(archived_by_name)
    used_aliases = set(db.scalars(select(ProductAlias.alias).where(ProductAlias.store_id == sid)))

    created, skipped, dropped = 0, [], []
    for key in dict.fromkeys(body.keys):  # de-duplicate, keep order
        item = by_key[key]
        if item.name.lower() in names:
            archived = archived_by_name.get(item.name.lower())
            reason = "archived in store" if archived else "already in store"
            skipped.append(SkippedItem(key=key, name=item.name, reason=reason))
            continue
        product = Product(
            store_id=sid, name=item.name, category=item.category, base_unit=item.base_unit
        )
        for alias in item.aliases:
            if alias in used_aliases:
                dropped.append(DroppedAlias(key=key, alias=alias, reason="used by another product"))
                continue
            product.aliases.append(ProductAlias(store_id=sid, alias=alias))
            used_aliases.add(alias)
        for conv in item.conversions:
            product.conversions.append(
                UnitConversion(store_id=sid, from_unit=conv.from_unit, factor=conv.factor)
            )
        db.add(product)
        names.add(item.name.lower())
        created += 1

    _commit_or_409(db)
    return ImportOut(created=created, skipped=skipped, dropped_aliases=dropped)
