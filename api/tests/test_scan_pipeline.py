"""The multi-step scan (read -> match -> check) with a mocked AI: glossary, fuzzy
matching, the AI only for unmatched lines, the math check, AI request counts, and
what's stored and logged."""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.ai.errors import AIReadError
from app.ai.models import AIUsage
from app.ai.scan_check import parse_money, parse_qty, total_mismatch
from app.ai.scan_match import (
    item_text,
    match_by_code,
    normalize_text,
    normalize_unit_text,
)
from app.ai.scan_pipeline import MultiStepReader
from app.ai.schemas import AIUsageInfo, CatalogConversion, CatalogEntry, MatchAnswer, ReadLine
from app.core.config import settings
from app.inventory.models import Scan
from tests.conftest import make_product, upload_photo


def row(raw, qty=None, unit=None, price=None, total=None, confidence=0.95) -> ReadLine:
    return ReadLine(
        raw_text=raw,
        qty_text=qty,
        unit_text=unit,
        price_text=price,
        total_text=total,
        confidence=confidence,
    )


def entry(name, base_unit="pc", aliases=(), conversions=()) -> CatalogEntry:
    return CatalogEntry(uuid.uuid4(), name, base_unit, tuple(aliases), tuple(conversions))


CEMENT = entry("Portland Cement 40kg", "bag", ["sem", "semento", "cement"])
NAIL_4 = entry('Common Wire Nail 4"', "kg", ["pako 4"], [CatalogConversion("box", Decimal(25))])
NAIL_3 = entry('Common Wire Nail 3"', "kg", ["pako 3"])
BAR_10 = entry("Deformed Bar 10mm x 6m", "pc", ["bakal 10mm", "rebar 10"])
BAR_12 = entry("Deformed Bar 12mm x 6m", "pc", ["bakal 12mm", "rebar 12"])
CHB_6 = entry('Hollow Block 6"', "pc", ["chb 6"])
CATALOG = [CEMENT, NAIL_4, NAIL_3, BAR_10, BAR_12, CHB_6]


class FakeAI:
    """Mocked ScanAI: returns the given read rows; answers match requests from a dict
    {line text: ref}, and records what it was asked."""

    def __init__(self, rows, answers=None, match_error=None):
        self.rows = rows
        self.answers = answers or {}
        self.match_error = match_error
        self.match_calls: list[tuple[list, str]] = []

    def read_photo(self, image, media_type):
        return self.rows, AIUsageInfo(
            model="fake", provider="gemini", input_tokens=1000, output_tokens=100
        )

    def match_items(self, items, catalog_text):
        self.match_calls.append((items, catalog_text))
        if self.match_error:
            raise self.match_error
        usage = AIUsageInfo(model="fake", provider="gemini", input_tokens=400, output_tokens=20)
        return [MatchAnswer(line=i.line, product_id=self.answers.get(i.text)) for i in items], usage


def read(rows, catalog=CATALOG, scan_type="stock_in", **kw):
    ai = FakeAI(rows, **kw)
    return ai, MultiStepReader(ai).read_list(b"img", "image/jpeg", catalog, scan_type)


# ---------- glossary normalization ----------


@pytest.mark.parametrize(
    ("text", "normalized"),
    [
        ("sem", "semento"),
        ("SMNTO", "semento"),
        ("bkl 10mm", "bakal 10mm"),
        ('2 BX Pakong 4"', "2 bx pakong 4"),
        ("pako 4 pulgada", "pako 4"),
        ("chb 6", "hollow block 6"),
        ("angle bar 1-1/2", "angle bar 1 1/2"),
        ("  Pintura,  puti!! ", "paint puti"),
    ],
)
def test_glossary_normalization(text, normalized):
    assert normalize_text(text) == normalized


@pytest.mark.parametrize(
    ("unit", "normalized"),
    [("pcs", "pc"), ("piraso", "pc"), ("Kls.", "kg"), ("sk", "bag"), ("bx", "box"), ("", "")],
)
def test_unit_glossary(unit, normalized):
    assert normalize_unit_text(unit) == normalized


def test_item_text_drops_qty_unit_price_and_total():
    assert item_text(row("10 bags sem @250   2,500", "10", "bags", "@250", "2,500")) == "sem"
    assert item_text(row('2 bx pako 4"', "2", "bx")) == 'pako 4"'  # the size "4" stays
    assert item_text(row("5 pcs bkl 10mm - 198", "5", "pcs", "198")) == "bkl 10mm"


@pytest.mark.parametrize(
    ("raw", "qty", "unit", "price", "total", "item"),
    [
        ("Marine Plywood 3/4 3pcs. 1470 4.410", "3", "pcs.", "1470", "4.410", "Marine Plywood 3/4"),
        ("marine Plywood 1/4 2pcs. 550 1.100", "2", "pcs.", "550", "1.100", "marine Plywood 1/4"),
        ('Orange pipe 2" S600 2pcs 350 700', "2", "pcs", "350", "700", 'Orange pipe 2" S600'),
        ("3M SP # 240 10pcs 25 250", "10", "pcs", "25", "250", "3M SP # 240"),
        ("Fin. nail 2 & 1 1kl 150", "1", "kl", None, "150", "Fin. nail 2 & 1"),
        ('4 pako 4"', "4", None, None, None, 'pako 4"'),
    ],
)
def test_item_text_keeps_sizes_in_column_rows(raw, qty, unit, price, total, item):
    assert item_text(row(raw, qty, unit, price, total)) == item


# ---------- matching by code ----------


def _methods(rows, catalog=CATALOG):
    return [(m.method, m.product_id) for m in match_by_code(rows, catalog)]


def test_exact_match_through_the_glossary():
    # "sem" and "bkl" are expanded on both sides, then match an alias exactly.
    assert _methods([row("10 sem", "10"), row("5 bkl 10mm", "5")]) == [
        ("exact", str(CEMENT.product_id)),
        ("exact", str(BAR_10.product_id)),
    ]


def test_fuzzy_match_above_the_threshold():
    [m] = match_by_code([row('2 hollow blocks 6"', "2")], CATALOG)
    assert m.method == "fuzzy" and m.product_id == str(CHB_6.product_id)
    assert m.score is not None and m.score >= settings.SCAN_FUZZY_THRESHOLD


def test_fuzzy_threshold_comes_from_settings(monkeypatch):
    monkeypatch.setattr(settings, "SCAN_FUZZY_THRESHOLD", 99)
    assert _methods([row('2 hollow blocks 6"', "2")]) == [("none", None)]


def test_fuzzy_never_changes_a_size():
    # "bakal 14mm" scores 90 against "bakal 10mm" (enough to pass the threshold), but a
    # size the product doesn't have means it's a different product.
    only_10mm = [CEMENT, BAR_10, CHB_6]
    assert _methods([row("3 bakal 14mm", "3")], only_10mm) == [("none", None)]
    assert _methods([row('2 hollow block 8"', "2")], only_10mm) == [("none", None)]
    assert _methods([row("3 bakal 10 mm", "3")], only_10mm) == [  # same size: still matches
        ("fuzzy", str(BAR_10.product_id))
    ]


def test_fuzzy_leaves_ties_to_the_ai():
    # "wire nail" fits the 3" and the 4" nails equally well.
    assert _methods([row("2 common wire nail", "2")]) == [("none", None)]


# ---------- the AI only for unmatched lines ----------


def test_only_unmatched_lines_go_to_one_ai_call():
    rows = [row("10 sem", "10", "bag"), row("2 kl pakong 4 pulgada", "2", "kl"), row("1 gal paint")]
    ai, result = read(rows, answers={"2 kl pakong 4 pulgada": "P2"})  # P2 = 4" nail by name
    [(items, catalog_text)] = ai.match_calls  # exactly one AI match call
    assert [i.line for i in items] == [1, 2]  # cement was matched by code
    assert 'P2 | Common Wire Nail 4"' in catalog_text
    assert [line.product_id for line in result.lines] == [
        CEMENT.product_id,
        NAIL_4.product_id,
        None,
    ]
    assert [m["method"] for m in result.steps["match"]["lines"]] == ["exact", "ai", "none"]
    assert result.ai_requests == 2
    assert [f for f, _ in result.calls] == ["scan_read", "scan_match"]


def test_ai_answers_outside_the_list_are_ignored():
    rows = [row("1 mystery item", "1", "pc"), row("2 other thing", "2", "pc")]
    _, result = read(rows, answers={"1 mystery item": "P999", "2 other thing": "not-a-ref"})
    assert [line.product_id for line in result.lines] == [None, None]


def test_failed_ai_match_keeps_the_lines_unmatched():
    error = AIReadError(
        "busy", retryable=True, usage=AIUsageInfo(model="fake", provider="gemini", input_tokens=50)
    )
    _, result = read([row("1 mystery item", "1", "pc")], match_error=error)
    assert result.lines[0].product_id is None
    assert result.steps["match"]["error"] == "busy"
    assert [f for f, _ in result.calls] == ["scan_read", "scan_match"]  # its cost still logged


def test_scan_matched_fully_by_code_makes_one_ai_request():
    rows = [row("10 sem @250", "10", "bags", "@250"), row("2 bx pako 4", "2", "bx")]
    ai, result = read(rows)
    assert ai.match_calls == []
    assert result.ai_requests == 1 and [f for f, _ in result.calls] == ["scan_read"]
    assert result.usage.input_tokens == 1000  # only the read call


def test_no_products_means_no_match_call():
    ai, result = read([row("10 sem", "10")], catalog=[])
    assert ai.match_calls == [] and result.ai_requests == 1


# ---------- the check step ----------


@pytest.mark.parametrize(
    ("text", "qty"),
    [
        ("10", "10"),
        ("2.5", "2.5"),
        ("1/2", "0.5"),
        ("1 1/2", "1.5"),
        ("1½", "1.5"),
        ("1,000", "1000"),
    ],
)
def test_parse_qty(text, qty):
    assert parse_qty(text) == Decimal(qty)


@pytest.mark.parametrize("text", [None, "", "?5", "0", "-2", "x2", "1/0"])
def test_unreadable_qty_is_none(text):
    assert parse_qty(text) is None


@pytest.mark.parametrize(
    ("text", "centavos"),
    [
        ("@250", 25000),
        ("₱1,250.50", 125050),
        ("P85/kg", 8500),
        ("= 2,500", 250000),
        ("abc", None),
        ("4.410", 441000),
        ("@1.470", 147000),
        ("12.500", 1250000),
        ("4.41", 441),
        ("0.500", 50),
    ],
)
def test_parse_money(text, centavos):
    assert parse_money(text) == centavos


def test_math_check_flags_a_wrong_total():
    rows = [
        row("10 sem @250 2,600", "10", "bags", "@250", "2,600"),  # 10 x 250 = 2,500, not 2,600
        row("10 sem @250 2,500", "10", "bags", "@250", "2,500"),  # right
        row("3 sem @33.33 100", "3", "bags", "@33.33", "100"),  # 99.99: rounding, fine
    ]
    _, result = read(rows)
    reasons = [c["reasons"] for c in result.steps["check"]]
    assert "total_mismatch" in reasons[0]
    assert "total_mismatch" not in reasons[1] and "total_mismatch" not in reasons[2]
    assert result.steps["check"][0]["computed_total_centavos"] == 250000
    assert result.steps["check"][0]["written_total_centavos"] == 260000


def test_total_tolerance_comes_from_settings(monkeypatch):
    assert not total_mismatch(Decimal(10), 25000, 250050)  # ₱0.50 off: within ₱1
    monkeypatch.setattr(settings, "SCAN_TOTAL_TOLERANCE_CENTAVOS", 0)
    assert total_mismatch(Decimal(10), 25000, 250050)


def test_a_total_with_a_dot_for_thousands_is_not_a_mismatch():
    _, result = read([row("Marine Plywood 3/4 3pcs. 1470 4.410", "3", "pcs", "1470", "4.410")])
    check = result.steps["check"][0]
    assert check["written_total_centavos"] == 441000
    assert "total_mismatch" not in check["reasons"]
    assert not total_mismatch(Decimal(3), 147000, 441)


def test_price_comes_from_the_total_when_only_a_total_is_written():
    _, result = read([row("2 bx pako 4 1,700", "2", "bx", None, "1,700")])
    line = result.lines[0]
    assert line.unit_price_centavos == 85000 and result.steps["check"][0]["price_from_total"]
    assert "total_mismatch" not in result.steps["check"][0]["reasons"]
    assert result.steps["check"][0]["qty_base"] == "50.000"  # 2 box x 25 kg, via convert()


def test_check_reasons():
    rows = [
        row("10 sem", "10", "bags", confidence=0.5),  # low confidence
        row("?? sem", None, "bags"),  # no qty
        row("10 sem", "10", None),  # no unit (never guessed)
        row("3 drum sem", "3", "drum"),  # cement can't be counted in drums
        row("2 bakal 14mm", "2", "pcs"),  # no product: a new one for stock in
    ]
    _, result = read(rows)
    assert [c["reasons"] for c in result.steps["check"]] == [
        ["low_confidence"],
        ["no_qty"],
        ["no_unit"],
        ["unknown_unit"],
        ["new_product"],
    ]
    assert result.lines[4].suggested_new_name == "Bakal 14mm"


def test_sales_never_suggest_new_products():
    _, result = read([row("2 bakal 14mm", "2", "pcs")], scan_type="sale")
    assert result.lines[0].suggested_new_name is None
    assert result.steps["check"][0]["reasons"] == ["no_product"]


# ---------- through the API: stored steps, logged usage, review screen ----------


def test_scan_stores_each_step_and_logs_each_ai_request(api, db, manager, storage):
    from app.ai.provider import get_vision_reader
    from app.main import app

    make_product(api, manager, aliases=["sem"])
    nails = make_product(
        api, manager, name='Common Wire Nail 4"', category="Nails & Screws", base_unit="kg"
    )
    ai = FakeAI(
        [row("10 sem @250 2,600", "10", "bags", "@250", "2,600"), row("2 kl pakong 4", "2", "kl")],
        answers={"2 kl pakong 4": "P1"},  # P1 = the nail (sorted by name)
    )
    app.dependency_overrides[get_vision_reader] = lambda: MultiStepReader(ai)
    key = upload_photo(api, manager, storage)
    res = api.post("/scans", json={"photo_key": key, "type": "stock_in"}, headers=manager)
    assert res.status_code == 201, res.text
    cement_line, nail_line = res.json()["lines"]
    assert "total_mismatch" in cement_line["check_reasons"]  # shown on the review screen
    assert nail_line["product_id"] == nails["id"] and nail_line["qty_base"] == "2.000"

    stored = db.scalar(select(Scan)).ai_result_json
    assert set(stored["steps"]) == {"read", "match", "check"} and stored["ai_requests"] == 2
    assert stored["steps"]["read"][0]["price_text"] == "@250"
    assert stored["lines"][0]["line_total_centavos"] == 260000
    rows = db.execute(select(AIUsage.feature, AIUsage.tokens_in)).all()
    assert sorted(rows) == [("scan_match", 400), ("scan_read", 1000)]
