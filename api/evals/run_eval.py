"""Run the AI list reader on every case in evals/cases/ and print accuracy per field.

    cd api
    uv run python -m evals.run_eval                 # all cases
    uv run python -m evals.run_eval --case dr-001   # one case
    uv run python -m evals.run_eval --verbose       # show each wrong line

Each run calls the real AI and costs money (the total is printed at the end).
See evals/README.md for how to add cases.
"""

import argparse
import json
import sys
import uuid
from decimal import Decimal
from pathlib import Path

from app.ai.anthropic_reader import AnthropicVisionReader
from app.ai.errors import AIReadError
from app.ai.pricing import cost_centavos
from app.ai.schemas import CatalogConversion, CatalogEntry
from app.core.config import settings
from app.inventory.scan_service import sniff_image_type
from app.products.catalog import load_catalog
from evals.scoring import CaseScore, ExpectedLine, pct, score_case

CASES_DIR = Path(__file__).parent / "cases"
IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp")
KEY_NAMESPACE = uuid.UUID("5b0c2f0e-5a1c-4f5e-9d0a-2e7c1d9a3f11")


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


def load_expected(path: Path, ids: dict[str, uuid.UUID]) -> tuple[str, list[ExpectedLine]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    lines = []
    for i, line in enumerate(data["lines"], start=1):
        product = line["product"]
        if product is None or product.startswith("new:"):
            pid = None
        elif product.lower() in ids:
            pid = ids[product.lower()]
        else:
            sys.exit(f"{path.name} line {i}: unknown product {product!r} (use a catalog key)")
        lines.append(ExpectedLine(pid, Decimal(str(line["qty"])), line["unit"]))
    return data.get("type", "stock_in"), lines


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--case", help="run only cases whose name contains this text")
    parser.add_argument("--verbose", action="store_true", help="print every wrong line")
    args = parser.parse_args()

    images = sorted(p for p in CASES_DIR.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)
    if args.case:
        images = [p for p in images if args.case in p.stem]
    if not images:
        sys.exit(f"No photos in {CASES_DIR}. See evals/README.md to add cases.")

    catalog, ids = catalog_entries()
    reader = AnthropicVisionReader()
    total = CaseScore()
    cost = Decimal(0)
    failed = 0

    print(f"Model: {settings.AI_MODEL} (effort {settings.AI_EFFORT}), {len(images)} case(s)\n")
    header = ("case", "lines", "product", "qty", "unit", "all 3", "miss", "extra")
    widths = (-24, 7, 9, 8, 8, 8, 6, 6)
    print(
        "".join(f"{h:<{-w}}" if w < 0 else f"{h:>{w}}" for h, w in zip(header, widths, strict=True))
    )
    for image_path in images:
        expected_path = image_path.with_suffix(".json")
        if not expected_path.exists():
            print(f"{image_path.stem:<24}  skipped: no {expected_path.name}")
            continue
        scan_type, expected = load_expected(expected_path, ids)
        data = image_path.read_bytes()
        media_type = sniff_image_type(data)
        if media_type is None:
            print(f"{image_path.stem:<24}  skipped: not a JPEG/PNG/WebP file")
            continue
        try:
            result = reader.read_list(data, media_type, catalog, scan_type)
        except AIReadError as e:
            failed += 1
            if e.usage:
                cost += cost_centavos(e.usage)
            print(f"{image_path.stem:<24}  FAILED: {e}")
            continue
        cost += cost_centavos(result.usage)
        s = score_case(expected, result.lines)
        total.add(s)
        n = s.expected
        print(
            f"{image_path.stem:<24}{n:>7}{pct(s.product_ok, n):>9}{pct(s.qty_ok, n):>8}"
            f"{pct(s.unit_ok, n):>8}{pct(s.all_ok, n):>8}{s.missing:>6}{s.extra:>6}"
        )
        if args.verbose:
            for note in s.notes:
                print(f"    - {note}")

    n = total.expected
    print("-" * 76)
    print(
        f"{'TOTAL':<24}{n:>7}{pct(total.product_ok, n):>9}{pct(total.qty_ok, n):>8}"
        f"{pct(total.unit_ok, n):>8}{pct(total.all_ok, n):>8}{total.missing:>6}{total.extra:>6}"
    )
    if failed:
        print(f"\n{failed} case(s) failed to read.")
    print(f"\nCost: ₱{cost / 100:.2f}")


if __name__ == "__main__":
    main()
