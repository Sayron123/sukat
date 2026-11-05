"""Starter catalog: common PH hardware items a new store can import.

Loaded once from seed_catalog.json and validated with Pydantic, so a typo in the file
fails loudly at startup/tests instead of creating bad products later.
"""

import json
from decimal import Decimal
from functools import cache
from pathlib import Path

from pydantic import BaseModel, Field

from app.products.constants import Category

CATALOG_PATH = Path(__file__).with_name("seed_catalog.json")


class CatalogConversion(BaseModel):
    from_unit: str = Field(min_length=1, max_length=20)
    factor: Decimal = Field(gt=0)  # 1 from_unit = factor base_unit


class CatalogItem(BaseModel):
    key: str = Field(pattern=r"^[a-z0-9-]+$")  # stable id used by the import endpoint
    name: str = Field(min_length=1, max_length=160)
    category: Category
    base_unit: str = Field(min_length=1, max_length=20)
    aliases: list[str]
    conversions: list[CatalogConversion]


class Catalog(BaseModel):
    version: int
    items: list[CatalogItem]


@cache
def load_catalog() -> Catalog:
    """Read and validate the catalog file (cached after the first call)."""
    return Catalog.model_validate(json.loads(CATALOG_PATH.read_text(encoding="utf-8")))


@cache
def catalog_by_key() -> dict[str, CatalogItem]:
    return {item.key: item for item in load_catalog().items}
