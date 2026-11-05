"""Guards the rules in app/products/README.md for seed_catalog.json."""

from collections import Counter

from app.products.catalog import load_catalog
from app.products.constants import CATEGORIES


def test_catalog_loads_and_has_about_150_items():
    items = load_catalog().items
    assert 140 <= len(items) <= 170


def test_every_category_is_used():
    assert {i.category for i in load_catalog().items} == set(CATEGORIES)


def test_keys_names_and_aliases_are_unique():
    items = load_catalog().items
    for counter in (
        Counter(i.key for i in items),
        Counter(i.name.lower() for i in items),
        Counter(a for i in items for a in i.aliases),
    ):
        dupes = [k for k, n in counter.items() if n > 1]
        assert not dupes, dupes


def test_text_is_normalized():
    for item in load_catalog().items:
        assert item.base_unit == item.base_unit.lower()
        assert item.aliases, item.name
        for alias in item.aliases:
            assert alias == alias.strip().lower() and alias, (item.name, alias)
        for conv in item.conversions:
            assert conv.from_unit == conv.from_unit.lower()
            assert conv.from_unit != item.base_unit


def test_no_prices_in_catalog():
    raw = load_catalog().model_dump()
    assert all("price" not in key for item in raw["items"] for key in item)


def test_examples_from_the_spec_are_present():
    aliases = {a for i in load_catalog().items for a in i.aliases}
    assert {"sem", "bakal 10mm", "plywood 1/2"} <= aliases


def test_units_are_already_in_canonical_spelling():
    from app.products.units import normalize_unit

    for item in load_catalog().items:
        assert normalize_unit(item.base_unit) == item.base_unit, item.name
        for conv in item.conversions:
            assert normalize_unit(conv.from_unit) == conv.from_unit, item.name
