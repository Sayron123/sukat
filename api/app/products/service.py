"""Product rules and queries. Every function is scoped to one store_id.

Callers (the router, the stock-in service, scripts) pass the store_id from the
authenticated caller; nothing here trusts a store_id from request data.
Raises AppError subclasses (see app.core.errors); never commits half a change.
"""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import Select, case, delete, exists, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import Conflict, Invalid, NotFound
from app.inventory.models import StockMovement, TransactionItem
from app.products.catalog import CatalogItem, catalog_by_key, load_catalog
from app.products.constants import MAX_BULK_DELETE, PAGE_SIZE
from app.products.models import Product, ProductAlias, UnitConversion
from app.products.schemas import (
    ConversionIn,
    DroppedAlias,
    ImportOut,
    ProductCreate,
    ProductDeleteOut,
    ProductUpdate,
    SkippedItem,
)

# ---------- reading ----------


def get_product(db: Session, store_id: UUID, product_id: UUID) -> Product:
    """A product of this store.

    @raises NotFound also for another store's product, so its existence isn't revealed
    """
    product = db.scalar(
        select(Product).where(Product.id == product_id, Product.store_id == store_id)
    )
    if product is None:
        raise NotFound("Product not found")
    return product


def _like_pattern(text: str) -> str:
    """'%text%' for LIKE, with LIKE's own wildcards escaped so "50%" matches literally."""
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


@dataclass(frozen=True)
class ProductSearch:
    q: str | None = None
    category: str | None = None
    low_stock: bool = False
    include_archived: bool = False
    page: int = 1  # 1-based; the caller bounds it (huge offsets overflow Postgres bigint)


def _matching(store_id: UUID, search: ProductSearch) -> tuple[Select[Product], list]:
    stmt: Select[Product] = select(Product).where(Product.store_id == store_id)
    if not search.include_archived:
        stmt = stmt.where(Product.archived.is_(False))
    if search.category:
        stmt = stmt.where(Product.category == search.category)
    if search.low_stock:
        stmt = stmt.where(
            Product.low_stock_level.is_not(None), Product.stock_qty <= Product.low_stock_level
        )

    order = [func.lower(Product.name), Product.id]
    term = " ".join((search.q or "").split()).lower()
    if term:
        pattern = _like_pattern(term)

        def alias_matches(cond):
            return exists().where(
                ProductAlias.product_id == Product.id, ProductAlias.store_id == store_id, cond
            )

        stmt = stmt.where(
            or_(
                func.lower(Product.name).like(pattern, escape="\\"),
                alias_matches(ProductAlias.alias.like(pattern, escape="\\")),
            )
        )
        exact = or_(func.lower(Product.name) == term, alias_matches(ProductAlias.alias == term))
        order.insert(0, case((exact, 0), else_=1))
    return stmt, order


def search_products(
    db: Session, store_id: UUID, search: ProductSearch
) -> tuple[list[Product], int]:
    """One page (PAGE_SIZE) of products, sorted by name, plus the total match count.

    `q` matches anywhere in the name or any alias, ignoring case and extra spaces.
    Exact name/alias matches come first, so "sem" puts cement on top.
    """
    stmt, order = _matching(store_id, search)
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    offset = (search.page - 1) * PAGE_SIZE
    rows = db.scalars(stmt.order_by(*order).offset(offset).limit(PAGE_SIZE)).all()
    return list(rows), total


def matching_ids(db: Session, store_id: UUID, search: ProductSearch) -> list[UUID]:
    stmt, order = _matching(store_id, search)
    return list(
        db.scalars(stmt.with_only_columns(Product.id).order_by(*order).limit(MAX_BULK_DELETE))
    )


# ---------- writing ----------


def ensure_unique(
    db: Session,
    store_id: UUID,
    name: str | None,
    aliases: list[str] | None,
    exclude_id: UUID | None = None,
) -> None:
    """Check the name and aliases aren't used by ANOTHER product in this store.
    (The database also enforces this; checking first gives a clear message.)

    @raises Conflict naming the clash (and saying so if the clash is archived)
    """
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
            raise Conflict(f'A product named "{taken.name}" already exists{hint}')
    if aliases:
        row = db.execute(
            select(ProductAlias.alias, Product.name)
            .join(Product, Product.id == ProductAlias.product_id)
            .where(*others, ProductAlias.alias.in_(aliases))
            .limit(1)
        ).first()
        if row:
            raise Conflict(f'Alias "{row.alias}" is already used by "{row.name}"')


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


def _commit(db: Session) -> None:
    """Commit; a unique-constraint race (two people saving at once) becomes a Conflict."""
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise Conflict("That name or alias is already used in this store") from None


def create_product(db: Session, store_id: UUID, data: ProductCreate) -> Product:
    """Create a product (stock 0) with its aliases and conversions. Commits."""
    ensure_unique(db, store_id, data.name, data.aliases)
    product = Product(
        store_id=store_id,
        name=data.name,
        category=data.category,
        base_unit=data.base_unit,
        price_centavos=data.price_centavos,
        low_stock_level=data.low_stock_level,
    )
    db.add(product)
    db.flush()  # get product.id before adding children
    _set_aliases(product, data.aliases)
    _set_conversions(product, data.conversions)
    _commit(db)
    db.refresh(product)
    return product


def _has_moved(db: Session, store_id: UUID, product_id: UUID) -> bool:
    """True if any stock movement or transaction line (saved or voided) uses the product."""
    moved = exists().where(
        StockMovement.store_id == store_id, StockMovement.product_id == product_id
    )
    in_txn = exists().where(
        TransactionItem.store_id == store_id, TransactionItem.product_id == product_id
    )
    return bool(db.scalar(select(or_(moved, in_txn))))


def update_product(db: Session, store_id: UUID, product_id: UUID, data: ProductUpdate) -> Product:
    """Change only the fields present in `data`. Sent aliases/conversions replace the
    whole list. stock_qty is never changed here (only by stock movements). Commits.

    @raises Conflict if the base unit changes while there is stock, or after any stock
        movement or transaction line exists for the product (the same advice either way:
        stock can only reach 0 through a movement, so "bring stock to 0" can't help)
    @raises Invalid if the base unit changes without re-sent conversions, or a
        conversion would use the base unit itself
    """
    product = get_product(db, store_id, product_id)
    fields = data.model_fields_set
    ensure_unique(
        db,
        store_id,
        data.name if "name" in fields else None,
        data.aliases if "aliases" in fields else None,
        exclude_id=product.id,
    )
    if "base_unit" in fields and data.base_unit != product.base_unit:
        # Lock the row first, like stock_service does when saving stock. A sale or
        # stock-in in progress then finishes before the check below, so its movement is
        # seen; one that starts later waits and then reads the new unit.
        db.refresh(product, with_for_update=True)
        # stock_qty and every conversion factor are measured in the base unit, so changing
        # it would silently re-interpret them (50 kg would become "50 g"). Movements and
        # transaction lines store quantities without a unit (the base unit of the time),
        # so after a change history would show "+10 roll" as "+10 m" and best sellers
        # would add rolls and metres together.
        if product.stock_qty != 0 or _has_moved(db, store_id, product.id):
            raise Conflict(
                "Can't change the base unit after stock has moved. "
                "Archive this product and add a new one with the new unit."
            )
        if product.conversions and data.conversions is None:
            raise Invalid(
                "Changing the base unit changes what each conversion means. "
                "Send the conversions again for the new base unit."
            )
    for field in ("name", "category", "base_unit", "price_centavos", "low_stock_level"):
        if field in fields:
            setattr(product, field, getattr(data, field))
    if data.aliases is not None:
        _set_aliases(product, data.aliases)
    if data.conversions is not None:
        _set_conversions(product, data.conversions)
    if any(c.from_unit == product.base_unit for c in product.conversions):
        raise Invalid("A conversion cannot use the base unit itself")
    _commit(db)
    db.refresh(product)
    return product


def set_archived(db: Session, store_id: UUID, product_id: UUID, archived: bool) -> Product:
    """Hide (or show again) a product. Nothing is deleted, so past records stay valid."""
    product = get_product(db, store_id, product_id)
    product.archived = archived
    db.commit()
    db.refresh(product)
    return product


def delete_products(db: Session, store_id: UUID, product_ids: list[UUID]) -> ProductDeleteOut:
    rows = db.execute(
        select(Product.id, Product.name)
        .where(Product.store_id == store_id, Product.id.in_(set(product_ids)))
        .order_by(Product.id)
        .with_for_update()
    ).all()
    ids = {row.id for row in rows}
    used = set(
        db.scalars(
            select(StockMovement.product_id).where(
                StockMovement.store_id == store_id, StockMovement.product_id.in_(ids)
            )
        )
    ) | set(
        db.scalars(
            select(TransactionItem.product_id).where(
                TransactionItem.store_id == store_id, TransactionItem.product_id.in_(ids)
            )
        )
    )
    unused = ids - used
    try:
        if unused:
            db.execute(
                delete(Product)
                .where(Product.store_id == store_id, Product.id.in_(unused))
                .execution_options(synchronize_session=False)
            )
        db.commit()
    except IntegrityError:
        db.rollback()
        raise Conflict("Some of these products were just used. Please try again.") from None
    kept = sorted((row.name for row in rows if row.id in used), key=str.lower)
    return ProductDeleteOut(deleted=len(unused), kept=kept)


def delete_product(db: Session, store_id: UUID, product_id: UUID) -> None:
    result = delete_products(db, store_id, [product_id])
    if result.kept:
        raise Conflict(
            f'"{result.kept[0]}" has sales or stock history, so it can\'t be deleted. '
            "Archive it instead."
        )
    if not result.deleted:
        raise NotFound("Product not found")


# ---------- starter catalog ----------


def catalog_for_store(db: Session, store_id: UUID) -> list[tuple[CatalogItem, bool, bool]]:
    """Every starter item, with whether the store has an active product of that name and
    whether it has an archived one."""
    archived_by_name = dict(
        db.execute(
            select(func.lower(Product.name), Product.archived).where(Product.store_id == store_id)
        ).all()
    )
    rows = []
    for item in load_catalog().items:
        archived = archived_by_name.get(item.name.lower())
        rows.append((item, archived is False, archived is True))
    return rows


def import_catalog(db: Session, store_id: UUID, keys: list[str]) -> ImportOut:
    """Copy chosen starter items into the store as products (no prices, stock 0).

    - Items whose name is already an active product are skipped (safe to run twice).
    - Items whose name is an archived product bring that product back (unarchived, with
      its history), since product names are unique per store.
    - An alias already used by another product in the store is left off that item.
    All changes are saved in one transaction. Commits.

    @raises Invalid for unknown keys (nothing is imported)
    """
    by_key = catalog_by_key()
    unknown = sorted({k for k in keys if k not in by_key})
    if unknown:
        raise Invalid(f"Unknown catalog keys: {', '.join(unknown)}")

    archived_by_name = {
        product.name.lower(): product
        for product in db.scalars(
            select(Product).where(Product.store_id == store_id, Product.archived.is_(True))
        )
    }
    names = set(db.scalars(select(func.lower(Product.name)).where(Product.store_id == store_id)))
    used_aliases = set(
        db.scalars(select(ProductAlias.alias).where(ProductAlias.store_id == store_id))
    )

    created, restored, skipped, dropped = 0, 0, [], []
    for key in dict.fromkeys(keys):  # de-duplicate, keep order
        item = by_key[key]
        archived = archived_by_name.pop(item.name.lower(), None)
        if archived is not None:
            archived.archived = False
            restored += 1
            continue
        if item.name.lower() in names:
            skipped.append(SkippedItem(key=key, name=item.name, reason="already in store"))
            continue
        product = Product(
            store_id=store_id, name=item.name, category=item.category, base_unit=item.base_unit
        )
        for alias in item.aliases:
            if alias in used_aliases:
                dropped.append(DroppedAlias(key=key, alias=alias, reason="used by another product"))
                continue
            product.aliases.append(ProductAlias(store_id=store_id, alias=alias))
            used_aliases.add(alias)
        for conv in item.conversions:
            product.conversions.append(
                UnitConversion(store_id=store_id, from_unit=conv.from_unit, factor=conv.factor)
            )
        db.add(product)
        names.add(item.name.lower())
        created += 1

    _commit(db)
    return ImportOut(created=created, restored=restored, skipped=skipped, dropped_aliases=dropped)
