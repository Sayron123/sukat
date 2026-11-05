"""Run the AI list reader on every case in evals/cases/ and print accuracy per field.

    cd api
    uv run python -m evals.run_eval                 # all cases
    uv run python -m evals.run_eval --case dr-001   # one case
    uv run python -m evals.run_eval --type sale     # only sale receipts
    uv run python -m evals.run_eval --verbose       # show each wrong line

Each run calls the real AI and costs money (the total is printed at the end).
See evals/README.md for how to add cases.
"""

import argparse
import json
import sys
import uuid
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from app.ai.base import ScanType
from app.ai.errors import AIReadError
from app.ai.pricing import cost_centavos
from app.ai.provider import get_vision_reader
from app.ai.schemas import CatalogConversion, CatalogEntry
from app.core.config import settings
from app.inventory.scan_service import sniff_image_type
from app.products.catalog import load_catalog
from evals.scoring import NOT_SCORED, CaseScore, ExpectedLine, pct, score_case

CASES_DIR = Path(__file__).parent / "cases"
IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp")
KEY_NAMESPACE = uuid.UUID("5b0c2f0e-5a1c-4f5e-9d0a-2e7c1d9a3f11")
# Text in the expected file -> scan type (an explicit table keeps the type checker happy).
SCAN_TYPES: dict[str, ScanType] = {"stock_in": "stock_in", "sale": "sale"}

COLUMNS = ("case", "lines", "product", "qty", "unit", "all 3", "price", "miss", "extra")
WIDTHS = (-26, 6, 9, 8, 8, 8, 8, 6, 6)


def row(*values: object) -> str:
    """One table row: first column left-aligned, the rest right-aligned."""
    return "".join(
        f"{str(v):<{-w}}" if w < 0 else f"{str(v):>{w}}"
        for v, w in zip(values, WIDTHS, strict=True)
    )


def score_row(name: str, s: CaseScore) -> str:
    n = s.expected
    return row(
        name,
        n,
        pct(s.product_ok, n),
        pct(s.qty_ok, n),
        pct(s.unit_ok, n),
        pct(s.all_ok, n),
        pct(s.price_ok, s.price_checked),
        s.missing,
        s.extra,
    )


def catalog_entries() -> tuple[list[CatalogEntry], dict[str, uuid.UUID]]:
    """The starter catalog as the AI's product list, with stable fake ids per key."""
    entries, ids = [], {}
    for item in load_catalog().items:
        pid = uuid.uuid5(KEY_NAMESPACE, item.key)
        ids[item.key] = pid
        ids[item.name.lower()] = pid
        entries.append(
            CatalogEntry(
                product_id=pid,
                name=item.name,
                base_unit=item.base_unit,
                aliases=tuple(item.aliases),
                conversions=tuple(
                    CatalogConversion(c.from_unit, c.factor) for c in item.conversions
                ),
            )
        )
    return entries, ids


def _price(line: dict, where: str) -> object:
    """Expected price per unit in centavos, from pesos in the file ("unit_price")."""
    if "unit_price" not in line:
        return NOT_SCORED
    if line["unit_price"] is None:
        return None
    try:
        pesos = Decimal(str(line["unit_price"]))
    except ArithmeticError:
        sys.exit(f"{where}: unit_price must be a number of pesos or null")
    return int((pesos * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def load_expected(path: Path, ids: dict[str, uuid.UUID]) -> tuple[ScanType, list[ExpectedLine]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    scan_type = SCAN_TYPES.get(data.get("type", "stock_in"))
    if scan_type is None:
        sys.exit(f"{path.name}: type must be one of {', '.join(SCAN_TYPES)}")
    lines = []
    for i, line in enumerate(data["lines"], start=1):
        where = f"{path.name} line {i}"
        product = line["product"]
        if product is None or product.startswith("new:"):
            pid = None
        elif product.lower() in ids:
            pid = ids[product.lower()]
        else:
            sys.exit(f"{where}: unknown product {product!r} (use a catalog key)")
        lines.append(
            ExpectedLine(pid, Decimal(str(line["qty"])), line["unit"], _price(line, where))
        )
    return scan_type, lines


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--case", help="run only cases whose name contains this text")
    parser.add_argument("--type", choices=list(SCAN_TYPES), help="run only this kind of case")
    parser.add_argument("--verbose", action="store_true", help="print every wrong line")
    args = parser.parse_args()

    images = sorted(p for p in CASES_DIR.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)
    if args.case:
        images = [p for p in images if args.case in p.stem]
    if not images:
        sys.exit(f"No photos in {CASES_DIR}. See evals/README.md to add cases.")

    catalog, ids = catalog_entries()
    reader = get_vision_reader()
    totals = {t: CaseScore() for t in SCAN_TYPES}
    cost = Decimal(0)
    failed = 0

    print(f"Model: {settings.AI_MODEL} (effort {settings.AI_EFFORT})\n")
    print(row(*COLUMNS))
    for image_path in images:
        expected_path = image_path.with_suffix(".json")
        if not expected_path.exists():
            print(f"{image_path.stem:<26}skipped: no {expected_path.name}")
            continue
        scan_type, expected = load_expected(expected_path, ids)
        if args.type and scan_type != args.type:
            continue
        data = image_path.read_bytes()
        media_type = sniff_image_type(data)
        if media_type is None:
            print(f"{image_path.stem:<26}skipped: not a JPEG/PNG/WebP file")
            continue
        try:
            result = reader.read_list(data, media_type, catalog, scan_type)
        except AIReadError as e:
            failed += 1
            if e.usage:
                cost += cost_centavos(e.usage)
            print(f"{image_path.stem:<26}FAILED: {e}")
            continue
        cost += cost_centavos(result.usage)
        s = score_case(expected, result.lines)
        totals[scan_type].add(s)
        print(score_row(f"{image_path.stem} ({'sale' if scan_type == 'sale' else 'in'})", s))
        if args.verbose:
            for note in s.notes:
                print(f"    - {note}")

    print("-" * 79)
    overall = CaseScore()
    for scan_type, s in totals.items():
        if s.expected:
            print(score_row(f"TOTAL {scan_type}", s))
            overall.add(s)
    print(score_row("TOTAL", overall))
    if failed:
        print(f"\n{failed} case(s) failed to read.")
    print(f"\nCost: ₱{cost / 100:.2f}")


if __name__ == "__main__":
    main()
