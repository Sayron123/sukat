import uuid
from decimal import Decimal

from evals.run_eval import catalog_entries, load_expected
from evals.scoring import ExpectedLine, score_case
from tests.conftest import scan_line

A, B, C = (uuid.uuid4() for _ in range(3))


def exp(pid, qty, unit):
    return ExpectedLine(pid, Decimal(qty), unit)


def test_perfect_read():
    s = score_case(
        [exp(A, "2", "box"), exp(B, "10", "bag")],
        [scan_line(A, qty=Decimal("2"), unit="bx"), scan_line(B, qty=Decimal("10"), unit="sako")],
    )
    assert (s.product_ok, s.qty_ok, s.unit_ok, s.all_ok, s.missing, s.extra) == (2, 2, 2, 2, 0, 0)


def test_skipped_line_does_not_shift_the_rest():
    s = score_case(
        [exp(A, "1", "pc"), exp(B, "2", "pc"), exp(C, "3", "pc")],
        [scan_line(A, qty=Decimal("1")), scan_line(C, qty=Decimal("3"))],
    )
    assert s.all_ok == 2 and s.missing == 1 and s.extra == 0


def test_wrong_product_and_extra_line():
    s = score_case(
        [exp(A, "1", "pc")],
        [scan_line(B, qty=Decimal("1")), scan_line(None, raw_text="TOTAL")],
    )
    assert s.product_ok == 0 and s.qty_ok == 1 and s.extra == 1


def test_new_product_counts_as_right_when_unmatched():
    s = score_case([exp(None, "5", "pc")], [scan_line(None, qty=Decimal("5"))])
    assert s.all_ok == 1


def test_example_case_file_loads_against_the_catalog():
    from pathlib import Path

    _, ids = catalog_entries()
    scan_type, lines = load_expected(Path("evals/cases/_example.json"), ids)
    assert scan_type == "stock_in" and len(lines) == 4
    assert lines[3].product_id is None and lines[1].qty == Decimal("2")


def test_runner_end_to_end_with_fake_reader(tmp_path, monkeypatch, capsys):
    import json

    from app.ai.schemas import AIUsageInfo, ReadResult
    from evals import run_eval

    _, ids = catalog_entries()
    (tmp_path / "dr-001.jpg").write_bytes(b"\xff\xd8\xff\xe0fake")
    (tmp_path / "dr-001.json").write_text(
        json.dumps(
            {
                "lines": [
                    {"product": "portland-cement-40kg", "qty": 10, "unit": "bag"},
                    {"product": "common-wire-nail-4in", "qty": 2, "unit": "box"},
                ]
            }
        )
    )

    class FakeReader:
        def read_list(self, image, media_type, catalog, scan_type):
            lines = [
                scan_line(ids["portland-cement-40kg"], qty=Decimal("10"), unit="sako"),
                scan_line(ids["common-wire-nail-4in"], qty=Decimal("3"), unit="bx"),
            ]
            return ReadResult(lines, AIUsageInfo("fake", input_tokens=1000, output_tokens=100))

    monkeypatch.setattr(run_eval, "CASES_DIR", tmp_path)
    monkeypatch.setattr(run_eval, "get_vision_reader", FakeReader)
    monkeypatch.setattr("sys.argv", ["run_eval", "--verbose"])
    run_eval.main()
    out = capsys.readouterr().out
    assert "dr-001" in out and "TOTAL" in out
    assert "100.0%" in out and " 50.0%" in out  # product right; qty 1 of 2
    assert "got 3 bx; expected 2 box" in out and "Cost: ₱" in out


def test_sale_prices_are_scored_only_when_given():
    from evals.scoring import NOT_SCORED

    s = score_case(
        [
            ExpectedLine(A, Decimal("1"), "bag", 26000),  # written ₱260
            ExpectedLine(B, Decimal("1"), "kg", None),  # no price written
            ExpectedLine(C, Decimal("1"), "pc", NOT_SCORED),
        ],
        [
            scan_line(A, qty=Decimal("1"), unit="bag", unit_price_centavos=26000),
            scan_line(B, qty=Decimal("1"), unit="kg", unit_price_centavos=8500),  # invented
            scan_line(C, qty=Decimal("1"), unit="pc", unit_price_centavos=999),
        ],
    )
    assert (s.price_checked, s.price_ok) == (2, 1)
    assert s.all_ok == 3  # price is its own column, not part of "all 3"
    assert any("price 8500 != None" in n for n in s.notes)


def test_example_sale_case_loads():
    from pathlib import Path

    from evals.scoring import NOT_SCORED

    _, ids = catalog_entries()
    scan_type, lines = load_expected(Path("evals/cases/_example_sale.json"), ids)
    assert scan_type == "sale"
    assert [line.unit_price_centavos for line in lines] == [26000, 8500, None, NOT_SCORED]
    assert lines[3].product_id is None


def test_runner_reports_sale_and_stock_in_separately(tmp_path, monkeypatch, capsys):
    import json

    from app.ai.schemas import AIUsageInfo, ReadResult
    from evals import run_eval

    _, ids = catalog_entries()
    cement = "portland-cement-40kg"
    for name, kind in (("in-001", "stock_in"), ("sale-001", "sale")):
        (tmp_path / f"{name}.jpg").write_bytes(b"\xff\xd8\xff\xe0fake")
        line = {"product": cement, "qty": 2, "unit": "bag"}
        if kind == "sale":
            line["unit_price"] = 260
        (tmp_path / f"{name}.json").write_text(json.dumps({"type": kind, "lines": [line]}))

    seen = []

    class FakeReader:
        def read_list(self, image, media_type, catalog, scan_type):
            seen.append(scan_type)
            line = scan_line(ids[cement], qty=Decimal("2"), unit="bag", unit_price_centavos=26000)
            return ReadResult([line], AIUsageInfo("fake", input_tokens=10, output_tokens=5))

    monkeypatch.setattr(run_eval, "CASES_DIR", tmp_path)
    monkeypatch.setattr(run_eval, "get_vision_reader", FakeReader)
    monkeypatch.setattr("sys.argv", ["run_eval"])
    run_eval.main()
    out = capsys.readouterr().out
    assert sorted(seen) == ["sale", "stock_in"]  # each case read with its own prompt
    assert "TOTAL stock_in" in out and "TOTAL sale" in out
    assert "sale-001 (sale)" in out and "in-001 (in)" in out

    monkeypatch.setattr("sys.argv", ["run_eval", "--type", "sale"])
    seen.clear()
    run_eval.main()
    assert seen == ["sale"]


def test_runner_reports_each_step_and_ai_requests(tmp_path, monkeypatch, capsys):
    """run_eval on two cases with a mocked AI: one matched fully by code (1 request),
    one needing the AI match (2 requests)."""
    import json
    import sys

    from app.ai.scan_pipeline import MultiStepReader
    from app.ai.schemas import AIUsageInfo, MatchAnswer, ReadLine
    from evals import run_eval

    def row(raw, qty, unit):
        return ReadLine(
            raw_text=raw,
            qty_text=qty,
            unit_text=unit,
            price_text=None,
            total_text=None,
            confidence=0.95,
        )

    reads = {
        b"\xff\xd8\xff\xe0case-a": [
            row("10 bags sem", "10", "bags"),
            row("2 bx pako 4", "2", "bx"),
        ],
        b"\xff\xd8\xff\xe0case-b": [row("5 pcs pakong 4 pulgada", "5", "kls")],  # unit misread
    }

    class FakeAI:
        def read_photo(self, image, media_type):
            return reads[image], AIUsageInfo(model="fake", input_tokens=100)

        def match_items(self, items, catalog_text):
            ref = next(
                line.split(" | ")[0]
                for line in catalog_text.splitlines()
                if 'Common Wire Nail 4"' in line
            )
            usage = AIUsageInfo(model="fake", input_tokens=50)
            return [MatchAnswer(line=i.line, product_id=ref) for i in items], usage

    for name, image in (
        ("case-a", b"\xff\xd8\xff\xe0case-a"),
        ("case-b", b"\xff\xd8\xff\xe0case-b"),
    ):
        (tmp_path / f"{name}.jpg").write_bytes(image)
    (tmp_path / "case-a.json").write_text(
        json.dumps(
            {
                "type": "stock_in",
                "lines": [
                    {"product": "portland-cement-40kg", "qty": 10, "unit": "bag"},
                    {"product": "common-wire-nail-4in", "qty": 2, "unit": "box"},
                ],
            }
        )
    )
    (tmp_path / "case-b.json").write_text(
        json.dumps(
            {
                "type": "stock_in",
                "lines": [{"product": "common-wire-nail-4in", "qty": 5, "unit": "pc"}],
            }
        )
    )
    monkeypatch.setattr(run_eval, "CASES_DIR", tmp_path)
    monkeypatch.setattr(run_eval, "get_vision_reader", lambda: MultiStepReader(FakeAI()))
    monkeypatch.setattr(sys, "argv", ["run_eval"])
    run_eval.main()
    out = capsys.readouterr().out
    assert (
        "case-a (in)                    2  100.0%  100.0%  100.0%       -     0     0    1.0" in out
    )
    # case-b: product right (via the AI), but "kls" isn't "pc": read wrong, final wrong.
    assert (
        "case-b (in)                    1    0.0%  100.0%    0.0%       -     0     0    2.0" in out
    )
    assert (
        "AI requests: 3 for 2 scans (1.5 per scan; 1 matched fully by code with 1 request)" in out
    )
    assert "Lines matched by code: 2/3, by AI: 1, not matched: 0" in out
