"""Fixed lists shared by models, schemas, the seed catalog, and tests."""

from typing import Literal, get_args

# The category type; CATEGORIES is derived from it so the two can't drift apart.
Category = Literal[
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
]
CATEGORIES: tuple[str, ...] = get_args(Category)

PAGE_SIZE = 20
MAX_BULK_DELETE = 2000


def sql_in_list(values: tuple[str, ...]) -> str:
    """Render values as a SQL IN list for CHECK constraints, e.g. "('a', 'b')"."""
    return "(" + ", ".join("'" + v.replace("'", "''") + "'" for v in values) + ")"
