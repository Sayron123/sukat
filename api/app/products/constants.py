"""Fixed lists shared by models, schemas, the seed catalog, and tests."""

CATEGORIES: tuple[str, ...] = (
    "Cement",
    "Steel",
    "Wood",
    "Nails & Screws",
    "Paint",
    "Electrical",
    "Plumbing",
    "Roofing",
    "Tools",
    "Others",
)

PAGE_SIZE = 20


def sql_in_list(values: tuple[str, ...]) -> str:
    """Render values as a SQL IN list for CHECK constraints, e.g. "('a', 'b')"."""
    return "(" + ", ".join("'" + v.replace("'", "''") + "'" for v in values) + ")"
