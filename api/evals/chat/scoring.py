"""How a chat eval case is scored: did the model's first tool call pick the expected
tool, with the expected arguments? (Tested in tests/test_chat_eval_scoring.py.)

Arguments are read through the tool's own input model, then the tool's date defaults
are applied, so "no dates" and "today's dates" count as the same request.
"""

from dataclasses import dataclass
from datetime import date
from typing import Any

from pydantic import ValidationError

from app.insights.chat_tools import TOOLS

TODAY_DEFAULT = {"sales_summary", "top_products"}  # no dates = today


@dataclass(frozen=True)
class Result:
    tool_ok: bool
    args_ok: bool
    got: str  # what the model called, for the report


def effective_args(name: str, raw: Any, today: date) -> dict[str, Any] | None:
    """The arguments as the tool would use them, as strings; None if they're invalid."""
    tool = TOOLS.get(name)
    if tool is None:
        return None
    try:
        args = tool.input_model.model_validate(raw or {})
    except ValidationError:
        return None
    out = {k: (str(v) if v is not None else None) for k, v in args.model_dump().items()}
    if "start" in out:
        start, end = out["start"], out["end"]
        if start is None and end is None and name in TODAY_DEFAULT:
            start = end = today.isoformat()
        out["start"], out["end"] = start or end, end or start
    return out


def score_case(expect: dict[str, Any], call: tuple[str, Any] | None, today: date) -> Result:
    """@param call the first tool call (name, input), or None if the model answered in text"""
    want = expect.get("tool")
    if call is None:
        return Result(tool_ok=want is None, args_ok=want is None, got="(no tool)")
    name, raw = call
    got = f"{name}({raw})"
    if name != want:
        return Result(tool_ok=False, args_ok=False, got=got)
    args = effective_args(name, raw, today)
    if args is None:
        return Result(tool_ok=True, args_ok=False, got=got)
    ok = all(str(args.get(k)) == str(v) for k, v in expect.get("args", {}).items())
    if "query_contains" in expect:
        ok = ok and expect["query_contains"].lower() in (args.get("query") or "").lower()
    return Result(tool_ok=True, args_ok=ok, got=got)
