"""The store's product list as prompt text, with short refs (P1, P2, ...)."""

from app.ai.schemas import CatalogEntry


def catalog_refs(catalog: list[CatalogEntry]) -> list[tuple[str, CatalogEntry]]:
    """Give each product a short ref (P1, P2, ...) in a stable order (name, then id),
    so the prompt text is byte-identical between scans and the prompt cache hits."""
    ordered = sorted(catalog, key=lambda e: (e.name.lower(), str(e.product_id)))
    return [(f"P{i}", entry) for i, entry in enumerate(ordered, start=1)]


def catalog_text(refs: list[tuple[str, CatalogEntry]]) -> str:
    """One product per line: `P12 | name | unit: kg | also: a, b | 1 box = 25 kg`."""
    if not refs:
        return "The store has no products yet. Use product_ref null for every line."
    rows = ["The store's products (ref | name | base unit | other names | other units):"]
    for ref, e in refs:
        parts = [ref, e.name, f"unit: {e.base_unit}"]
        if e.aliases:
            parts.append("also: " + ", ".join(e.aliases))
        if e.conversions:
            parts.append(
                "; ".join(
                    f"1 {c.from_unit} = {c.factor.normalize():f} {e.base_unit}"
                    for c in e.conversions
                )
            )
        rows.append(" | ".join(parts))
    return "\n".join(rows)


__all__ = ["catalog_refs", "catalog_text"]
