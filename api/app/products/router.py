"""Products HTTP endpoints. Thin: check the role, call products.service, shape the response."""

import math
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.auth.deps import CurrentMember, CurrentMemberDep, DbSession, require_role
from app.products import service
from app.products.constants import PAGE_SIZE, Category
from app.products.models import Product
from app.products.schemas import (
    CatalogItemOut,
    ConversionOut,
    ImportIn,
    ImportOut,
    ProductCreate,
    ProductDeleteIn,
    ProductDeleteOut,
    ProductOut,
    ProductPage,
    ProductUpdate,
)
from app.stores.models import Role

router = APIRouter(tags=["products"])

# Manager and secretary can change products; members can only read.
Writer = Annotated[CurrentMember, Depends(require_role(Role.MANAGER, Role.SECRETARY))]
Manager = Annotated[CurrentMember, Depends(require_role(Role.MANAGER))]


def product_out(p: Product) -> ProductOut:
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
    """This store's products, 20 per page. See service.search_products for matching rules."""
    search = service.ProductSearch(q, category, low_stock, include_archived, page)
    rows, total = service.search_products(db, current.store_id, search)
    return ProductPage(
        items=[product_out(p) for p in rows],
        total=total,
        page=page,
        page_size=PAGE_SIZE,
        pages=max(1, math.ceil(total / PAGE_SIZE)),
    )


@router.post("/products", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
def create_product(body: ProductCreate, current: Writer, db: DbSession) -> ProductOut:
    return product_out(service.create_product(db, current.store_id, body))


# Declared before /products/{product_id} so "catalog" isn't read as a product id.
@router.get("/products/catalog", response_model=list[CatalogItemOut])
def get_catalog(current: CurrentMemberDep, db: DbSession) -> list[CatalogItemOut]:
    """All starter items, each marked if this store already has a product with that name."""
    return [
        CatalogItemOut(
            key=item.key,
            name=item.name,
            category=item.category,
            base_unit=item.base_unit,
            aliases=item.aliases,
            conversions=[
                ConversionOut(from_unit=c.from_unit, factor=c.factor) for c in item.conversions
            ],
            already_in_store=in_store,
            archived_in_store=archived,
        )
        for item, in_store, archived in service.catalog_for_store(db, current.store_id)
    ]


@router.get("/products/ids", response_model=list[UUID])
def list_product_ids(
    current: Manager,
    db: DbSession,
    q: Annotated[str | None, Query(max_length=80)] = None,
    category: Category | None = None,
) -> list[UUID]:
    return service.matching_ids(db, current.store_id, service.ProductSearch(q, category))


@router.get("/products/{product_id}", response_model=ProductOut)
def get_product(product_id: UUID, current: CurrentMemberDep, db: DbSession) -> ProductOut:
    return product_out(service.get_product(db, current.store_id, product_id))


@router.patch("/products/{product_id}", response_model=ProductOut)
def update_product(
    product_id: UUID, body: ProductUpdate, current: Writer, db: DbSession
) -> ProductOut:
    """Change product details (not stock_qty: that changes only through stock movements)."""
    return product_out(service.update_product(db, current.store_id, product_id, body))


@router.post("/products/{product_id}/archive", response_model=ProductOut)
def archive_product(product_id: UUID, current: Writer, db: DbSession) -> ProductOut:
    """Hide a product from the normal list. Nothing is deleted, so past sales stay valid."""
    return product_out(service.set_archived(db, current.store_id, product_id, True))


@router.post("/products/{product_id}/unarchive", response_model=ProductOut)
def unarchive_product(product_id: UUID, current: Writer, db: DbSession) -> ProductOut:
    return product_out(service.set_archived(db, current.store_id, product_id, False))


@router.delete("/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(product_id: UUID, current: Manager, db: DbSession) -> None:
    service.delete_product(db, current.store_id, product_id)


@router.post("/products/bulk-delete", response_model=ProductDeleteOut)
def delete_products(body: ProductDeleteIn, current: Manager, db: DbSession) -> ProductDeleteOut:
    return service.delete_products(db, current.store_id, body.ids)


@router.post("/products/import", response_model=ImportOut)
def import_catalog_items(body: ImportIn, current: Writer, db: DbSession) -> ImportOut:
    """Copy chosen starter items into this store. Safe to run twice."""
    return service.import_catalog(db, current.store_id, body.keys)
