"""The multi-step scan: read -> match -> check.

1. read (AI, photo only): copy each row as written (app/ai/prompts/scan_read.md).
2. match (code, then AI only for leftovers): find each row's product
   (app/ai/scan_match.py).
3. check (code): numbers, unit conversion, the math, and what needs a look
   (app/ai/scan_check.py).

MultiStepReader is a VisionReader, so the rest of the app (scan_service, the eval
script) uses it like any reader. Each step's output is returned in `steps` and stored
on the scan (scans.ai_result_json) to see where errors happen. A scan that matches
fully by code makes 1 AI request; otherwise 2.
"""

from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from app.ai.base import ImageType, ScanAI, ScanType
from app.ai.scan_check import check_line, line_total, parse_money, parse_qty
from app.ai.scan_match import MatchStep, match_lines, normalize_unit_text
from app.ai.schemas import AIUsageInfo, CatalogEntry, ReadLine, ReadResult, ScanLine

NAME_MAX = 160


def _suggested_name(item: str) -> str | None:
    """'plywood marine 1/4' -> 'Plywood marine 1/4' (for "add as new product")."""
    item = item.strip()[:NAME_MAX]
    return (item[0].upper() + item[1:]) if item else None


def _sum(usages: list[AIUsageInfo]) -> AIUsageInfo:
    first = usages[0]
    return AIUsageInfo(
        model=first.model,
        input_tokens=sum(u.input_tokens for u in usages),
        output_tokens=sum(u.output_tokens for u in usages),
        cache_write_tokens=sum(u.cache_write_tokens for u in usages),
        cache_read_tokens=sum(u.cache_read_tokens for u in usages),
        provider=first.provider,
    )


class MultiStepReader:
    def __init__(self, ai: ScanAI) -> None:
        self.ai = ai

    def read_list(
        self,
        image: bytes,
        media_type: ImageType,
        catalog: list[CatalogEntry],
        scan_type: ScanType,
    ) -> ReadResult:
        """@raises AIReadError when step 1 (reading the photo) fails. A failed step 2
        AI call only leaves those lines unmatched."""
        read_lines, read_usage = self.ai.read_photo(image, media_type)
        match = match_lines(read_lines, catalog, self.ai)
        lines, checks = _check(read_lines, match, catalog, scan_type)

        calls: list[tuple[str, AIUsageInfo]] = [("scan_read", read_usage)]
        if match.usage is not None:
            calls.append(("scan_match", match.usage))
        return ReadResult(
            lines=lines,
            usage=_sum([u for _, u in calls]),
            raw={},
            calls=calls,
            steps={
                "read": [line.model_dump(mode="json") for line in read_lines],
                "match": match.as_json(),
                "check": checks,
            },
            ai_requests=1 + match.ai_requests,
        )


def _check(
    read_lines: list[ReadLine], match: MatchStep, catalog: list[CatalogEntry], scan_type: str
) -> tuple[list[ScanLine], list[dict]]:
    by_id = {str(e.product_id): e for e in catalog}
    lines: list[ScanLine] = []
    checks: list[dict] = []
    for read, m in zip(read_lines, match.matches, strict=True):
        qty = parse_qty(read.qty_text)
        unit = normalize_unit_text(read.unit_text)[:20]
        price = parse_money(read.price_text)
        written_total = parse_money(read.total_text)
        price_from_total = False
        if price is None and written_total is not None and qty is not None:
            # Only a line total was written: the unit price comes from it.
            price = int((Decimal(written_total) / qty).quantize(Decimal(1), ROUND_HALF_UP))
            price_from_total = True
        product = by_id.get(m.product_id) if m.product_id else None
        suggested = None
        if product is None and scan_type == "stock_in":  # sales never create products
            suggested = _suggested_name(m.item)
        reasons, qty_base = check_line(
            confidence=read.confidence,
            product=product,
            is_new=suggested is not None,
            qty=qty,
            unit=unit,
            unit_price_centavos=price,
            written_total_centavos=written_total,
        )
        lines.append(
            ScanLine(
                raw_text=read.raw_text.strip()[:300],
                product_id=UUID(m.product_id) if m.product_id else None,
                suggested_new_name=suggested,
                qty=qty,
                unit=unit,
                unit_price_centavos=price,
                confidence=read.confidence,
                line_total_centavos=written_total,
            )
        )
        checks.append(
            {
                "line": m.line,
                "qty": str(qty) if qty is not None else None,
                "unit": unit,
                "unit_price_centavos": price,
                "price_from_total": price_from_total,
                "written_total_centavos": written_total,
                "computed_total_centavos": line_total(qty, price),
                "qty_base": str(qty_base) if qty_base is not None else None,
                "reasons": reasons,
            }
        )
    return lines, checks
