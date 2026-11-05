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
    monkeypatch.setattr(run_eval, "AnthropicVisionReader", FakeReader)
    monkeypatch.setattr("sys.argv", ["run_eval", "--verbose"])
    run_eval.main()
    out = capsys.readouterr().out
    assert "dr-001" in out and "TOTAL" in out
    assert "100.0%" in out and " 50.0%" in out  # product right; qty 1 of 2
    assert "got 3 bx; expected 2 box" in out and "Cost: ₱" in out
