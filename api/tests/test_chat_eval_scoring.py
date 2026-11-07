"""The chat eval's scoring (evals/chat/scoring.py) and runner, with a fake model."""

import json
import sys
from datetime import date

import pytest

from app.ai.base import ChatTurn, ToolCall
from app.ai.schemas import AIUsageInfo
from evals.chat import run_chat_eval
from evals.chat.scoring import score_case

TODAY = date(2026, 11, 6)
CASES = json.loads(run_chat_eval.CASES.read_text(encoding="utf-8"))


def test_today_by_default_counts_as_today():
    expect = {"tool": "sales_summary", "args": {"start": "2026-11-06", "end": "2026-11-06"}}
    assert score_case(expect, ("sales_summary", {}), TODAY).args_ok
    assert score_case(expect, ("sales_summary", {"start": "2026-11-06"}), TODAY).args_ok
    wrong_day = score_case(expect, ("sales_summary", {"start": "2026-11-05"}), TODAY)
    assert wrong_day.tool_ok and not wrong_day.args_ok


def test_wrong_tool_bad_args_and_no_tool():
    expect = {"tool": "top_products", "args": {"by": "revenue"}}
    assert not score_case(expect, ("sales_summary", {}), TODAY).tool_ok
    assert score_case(expect, ("top_products", {"by": "revenue"}), TODAY).args_ok
    assert not score_case(expect, ("top_products", {}), TODAY).args_ok  # default is qty
    bad = score_case(expect, ("top_products", {"by": "revenue", "store_id": "x"}), TODAY)
    assert bad.tool_ok and not bad.args_ok  # an input the tool would refuse
    assert not score_case(expect, None, TODAY).tool_ok
    off_topic = {"tool": None}
    assert score_case(off_topic, None, TODAY).args_ok
    assert not score_case(off_topic, ("low_stock", {}), TODAY).tool_ok


def test_query_contains_ignores_case():
    expect = {"tool": "find_product", "query_contains": "pako"}
    assert score_case(expect, ("find_product", {"query": "Pako 4"}), TODAY).args_ok
    assert not score_case(expect, ("find_product", {"query": "nail"}), TODAY).args_ok


def test_cases_file_is_consistent():
    """20 cases, unique ids, and each expectation is reachable by a valid call."""
    cases = CASES["cases"]
    assert len(cases) == 20 and len({c["id"] for c in cases}) == 20
    assert date.fromisoformat(CASES["today"]) == TODAY
    for case in cases:
        expect = case["expect"]
        if expect["tool"] is None:
            continue
        args = dict(expect.get("args", {}))
        if "query_contains" in expect:
            args["query"] = expect["query_contains"]
        assert score_case(expect, (expect["tool"], args), TODAY).args_ok, case["id"]


class FakeModel:
    """Answers each question with the expected call, except one wrong on purpose."""

    def __init__(self):
        self.by_question = {c["question"]: c["expect"] for c in CASES["cases"]}

    def respond(self, *, items, context, **kwargs):
        assert "Today is Friday, 2026-11-06" in context
        expect = self.by_question[items[-1].text]
        usage = AIUsageInfo(model="fake", input_tokens=1000, output_tokens=50)
        if expect["tool"] is None or expect["tool"] == "low_stock":
            return ChatTurn("No tool.", [], "end", usage)  # wrong for the low_stock cases
        args = dict(expect.get("args", {}))
        if "query_contains" in expect:
            args["query"] = expect["query_contains"]
        return ChatTurn("", [ToolCall("t1", expect["tool"], args)], "tool_use", usage)


def test_runner_reports_the_score(monkeypatch, capsys):
    monkeypatch.setattr(run_chat_eval, "get_chat_model", lambda: FakeModel())
    monkeypatch.setattr(sys, "argv", ["run_chat_eval"])
    assert run_chat_eval.main() == 1  # not every case right
    out = capsys.readouterr().out
    assert "Right tool:              17/20 (85%)" in out  # the 3 low_stock cases missed
    assert "Right tool + arguments:  17/20 (85%)" in out
    assert "Cost: ₱" in out


@pytest.mark.parametrize("case_id", [c["id"] for c in CASES["cases"]])
def test_every_case_has_a_question(case_id):
    case = next(c for c in CASES["cases"] if c["id"] == case_id)
    assert case["question"].strip()
