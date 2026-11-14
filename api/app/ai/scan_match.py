"""Step 2 "match": find which of the store's products each read line is.

Code first, AI last:
1. Take the item part of the row (the row minus its quantity, unit, price and total).
2. Normalize it: lowercase, sizes cleaned ("4\"" and "4 pulgada" -> "4"), and short
   forms expanded from prompts/glossary.json ("sem" -> "semento", "bkl" -> "bakal").
   The store's product names and aliases are normalized the same way.
3. Exact match on a name or alias.
4. Fuzzy match (rapidfuzz): must score at least SCAN_FUZZY_THRESHOLD, clearly beat
   every other product, and contain no size number the product doesn't have (so
   "bakal 10mm" never becomes the 12mm bar).
5. Only the lines still unmatched go to ONE AI call with the product list; it must
   answer an id from the list or null.
"""

import json
import re
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Literal

from rapidfuzz import fuzz, process

from app.ai.base import ScanAI
from app.ai.convert import catalog_refs, catalog_text
from app.ai.errors import AIReadError
from app.ai.schemas import AIUsageInfo, CatalogEntry, MatchItem, ReadLine
from app.core.config import settings
from app.products.units import normalize_unit

GLOSSARY_PATH = Path(__file__).parent / "prompts" / "glossary.json"
AMBIGUOUS_MARGIN = 3  # the best product must beat the next one by this many points
MIN_ITEM_CHARS = 2

Method = Literal["exact", "fuzzy", "ai", "none"]


@cache
def glossary() -> dict[str, dict[str, str]]:
    data = json.loads(GLOSSARY_PATH.read_text(encoding="utf-8"))
    return {"words": data["words"], "units": data["units"]}


_INCH = re.compile(r"(\d)\s*(?:\"|”|″|''|inches|inch|in\b|pulgada|pulg\b)")
_DASH_BETWEEN_NUMBERS = re.compile(r"(\d)-(\d)")
_NOT_WORD = re.compile(r"[^\w./]+")
_NUMBER = re.compile(r"\d+(?:[./]\d+)?")
_PRICE_MARKS = re.compile(r"(?:^|\s)(?:@|₱|php|p(?=\d)|=|x)(?=\s|\d|$)", re.IGNORECASE)


def normalize_text(text: str) -> str:
    """'2 BX Pakong 4" ' -> '2 bx pakong 4'; 'sem' -> 'semento' (glossary words)."""
    t = text.lower()
    t = _INCH.sub(r"\1 ", t)
    t = _DASH_BETWEEN_NUMBERS.sub(r"\1 \2", t)
    t = _NOT_WORD.sub(" ", t)
    words = glossary()["words"]
    return " ".join(words.get(w, w) for w in t.split()).strip(" ./")


def normalize_unit_text(unit_text: str | None) -> str:
    """'pcs' / 'piraso' -> 'pc', 'kls' -> 'kg', 'sk' -> 'bag'; '' when none."""
    if not unit_text:
        return ""
    cleaned = unit_text.strip().lower().rstrip(".")
    return normalize_unit(glossary()["units"].get(cleaned, cleaned))


def _remove_once(text: str, part: str | None) -> str:
    if not part:
        return text
    i = text.lower().find(part.lower())
    return text if i < 0 else (text[:i] + " " + text[i + len(part) :])


def item_text(line: ReadLine) -> str:
    """The item part of a row: the row without its total, price, quantity and unit.
    '10 bags sem @250  2,500' -> 'sem'."""
    text = line.raw_text
    for part in (line.total_text, line.price_text):
        text = _remove_once(text, part)
    qty, unit = line.qty_text, line.unit_text
    if qty and unit:
        text, n = re.subn(
            rf"(?<![\w./]){re.escape(qty)}\s*{re.escape(unit)}(?!\w)",
            " ",
            text,
            count=1,
            flags=re.IGNORECASE,
        )
        if n:
            qty = unit = None
    for part in (qty, unit):
        if part:
            text = re.sub(
                rf"(?<![\w./#]){re.escape(part)}(?![\w./\"”″'])",
                " ",
                text,
                count=1,
                flags=re.IGNORECASE,
            )
    text = _PRICE_MARKS.sub(" ", text)
    return " ".join(text.split()).strip(" -,:;")


def _numbers(text: str) -> set[str]:
    return set(_NUMBER.findall(text))


@dataclass(frozen=True)
class LineMatch:
    line: int
    item: str  # item text as written
    normalized: str
    method: Method
    product_id: str | None  # UUID as text
    score: float | None = None  # fuzzy score, for the stored step output


class _Index:
    """The store's names and aliases, normalized, for exact and fuzzy lookup."""

    def __init__(self, catalog: list[CatalogEntry]) -> None:
        self.exact: dict[str, set[str]] = {}
        self.texts: list[str] = []
        self.owners: list[str] = []
        for entry in catalog:
            for text in (entry.name, *entry.aliases):
                norm = normalize_text(text)
                if not norm:
                    continue
                pid = str(entry.product_id)
                self.exact.setdefault(norm, set()).add(pid)
                self.texts.append(norm)
                self.owners.append(pid)

    def find(self, norm: str) -> tuple[Method, str | None, float | None]:
        owners = self.exact.get(norm, set())
        if len(owners) == 1:
            return "exact", next(iter(owners)), 100.0
        if len(norm) < MIN_ITEM_CHARS or not self.texts:
            return "none", None, None
        wanted = _numbers(norm)
        best: dict[str, float] = {}
        for text, score, i in process.extract(
            norm, self.texts, scorer=fuzz.token_set_ratio, limit=20, score_cutoff=1
        ):
            if not wanted <= _numbers(text):  # a size the product doesn't have
                continue
            pid = self.owners[i]
            best[pid] = max(best.get(pid, 0.0), float(score))
        ranked = sorted(best.items(), key=lambda kv: kv[1], reverse=True)
        if not ranked or ranked[0][1] < settings.SCAN_FUZZY_THRESHOLD:
            return "none", None, ranked[0][1] if ranked else None
        if len(ranked) > 1 and ranked[0][1] - ranked[1][1] < AMBIGUOUS_MARGIN:
            return "none", None, ranked[0][1]  # two products fit equally: let the AI decide
        return "fuzzy", ranked[0][0], ranked[0][1]


def match_by_code(lines: list[ReadLine], catalog: list[CatalogEntry]) -> list[LineMatch]:
    index = _Index(catalog)
    out = []
    for i, line in enumerate(lines):
        item = item_text(line)
        norm = normalize_text(item)
        method, pid, score = index.find(norm) if norm else ("none", None, None)
        out.append(LineMatch(i, item, norm, method, pid, score))
    return out


@dataclass
class MatchStep:
    matches: list[LineMatch]
    usages: list[AIUsageInfo] = field(default_factory=list)
    error: str | None = None  # the AI call failed: those lines stay unmatched
    ai_requests: int = 0
    by_backup: bool = False

    def as_json(self) -> dict:
        return {
            "lines": [
                {
                    "line": m.line,
                    "item": m.item,
                    "normalized": m.normalized,
                    "method": m.method,
                    "product_id": m.product_id,
                    "score": m.score,
                }
                for m in self.matches
            ],
            "ai_requests": self.ai_requests,
            "by_backup": self.by_backup,
            "error": self.error,
        }


def match_lines(
    lines: list[ReadLine],
    catalog: list[CatalogEntry],
    ai: ScanAI,
    backup: ScanAI | None = None,
) -> MatchStep:
    """Match every line: code first; then one AI call for the rest (if any, and if the
    store has products). If that call fails in a way a retry may fix (busy, timeout) and
    a backup is set, the backup gets the same request once. If it still fails, those
    lines just stay unmatched: staff pick the product on the review screen."""
    matches = match_by_code(lines, catalog)
    todo = [m for m in matches if m.product_id is None and m.normalized]
    if not todo or not catalog:
        return MatchStep(matches)

    refs = catalog_refs(catalog)
    by_ref = {ref: str(entry.product_id) for ref, entry in refs}
    asked = {m.line for m in todo}
    items = [MatchItem(line=m.line, text=lines[m.line].raw_text) for m in todo]
    products = catalog_text(refs)
    usages: list[AIUsageInfo] = []
    by_backup = False
    try:
        answers, usage = ai.match_items(items, products)
    except AIReadError as e:
        if e.usage is not None:
            usages.append(e.usage)
        if backup is None or not e.retryable:
            return MatchStep(matches, usages, error=str(e), ai_requests=1)
        try:
            answers, usage = backup.match_items(items, products)
        except AIReadError as backup_error:
            if backup_error.usage is not None:
                usages.append(backup_error.usage)
            return MatchStep(matches, usages, error=str(backup_error), ai_requests=2)
        by_backup = True
    usages.append(usage)
    for answer in answers:
        pid = by_ref.get((answer.product_id or "").strip().upper())
        if answer.line in asked and pid is not None:  # ignore unknown ids and lines
            m = matches[answer.line]
            matches[answer.line] = LineMatch(m.line, m.item, m.normalized, "ai", pid)
            asked.discard(answer.line)  # one answer per line
    return MatchStep(matches, usages, ai_requests=2 if by_backup else 1, by_backup=by_backup)
