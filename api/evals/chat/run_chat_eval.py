"""Ask the real chat model every question in evals/chat/cases.json and report how many
pick the right tool (and the right arguments) on the first call.

    cd api
    uv run python -m evals.chat.run_chat_eval              # all 20 questions
    uv run python -m evals.chat.run_chat_eval --case tg-   # ids containing "tg-"
    uv run python -m evals.chat.run_chat_eval --verbose    # show every call

Only the first model call of each question is made (no tools are run, no database is
needed), with "today" fixed to the date in cases.json. Each run costs money; the total
is printed at the end.
"""

import argparse
import json
import sys
from datetime import UTC, date, datetime, time
from pathlib import Path

from app.ai.base import UserText
from app.ai.errors import AIChatError
from app.ai.pricing import cost_centavos
from app.ai.provider import get_chat_model
from app.core.config import settings
from app.insights.chat_service import request_context, system_prompt
from app.insights.chat_tools import tool_specs
from evals.chat.scoring import Result, score_case

CASES = Path(__file__).parent / "cases.json"


def noon_manila(day: date) -> datetime:
    """12:00 PM Manila (04:00 UTC) on `day`: a 'now' safely inside that store day."""
    return datetime.combine(day, time(4, 0), UTC)


def main() -> int:
    parser = argparse.ArgumentParser(description="Score the chat model's tool choice.")
    parser.add_argument("--case", default="", help="only ids containing this text")
    parser.add_argument("--verbose", action="store_true")
    opts = parser.parse_args()

    spec = json.loads(CASES.read_text(encoding="utf-8"))
    today = date.fromisoformat(spec["today"])
    cases = [c for c in spec["cases"] if opts.case in c["id"]]
    model = get_chat_model()
    tools = tool_specs()
    total_cost = 0
    results: list[Result] = []

    print(f"{'case':<26}{'tool':>6}{'args':>6}  expected -> got")
    for case in cases:
        role = case.get("role", "manager")
        try:
            turn = model.respond(
                system=system_prompt(),
                context=request_context(role, noon_manila(today)),
                items=[UserText(case["question"])],
                tools=tools,
                allow_tools=True,
                timeout=settings.AI_CHAT_TIMEOUT_SECONDS,
            )
        except TypeError as e:  # the SDK found no API key or login
            if "authentication" not in str(e):
                raise
            print("No API key: set ANTHROPIC_API_KEY in api/.env (see evals/chat/README.md).")
            return 2
        except AIChatError as e:
            print(f"{case['id']:<26} ERROR {e}")
            results.append(Result(False, False, "(error)"))
            if e.usage:
                total_cost += cost_centavos(e.usage)
            continue
        total_cost += cost_centavos(turn.usage)
        first = turn.tool_calls[0] if turn.tool_calls else None
        result = score_case(case["expect"], (first.name, first.input) if first else None, today)
        results.append(result)
        mark = {True: "ok", False: "--"}
        expected = case["expect"].get("tool") or "(no tool)"
        line = f"{case['id']:<26}{mark[result.tool_ok]:>6}{mark[result.args_ok]:>6}  {expected}"
        if opts.verbose or not result.args_ok:
            line += f" -> {result.got}"
            if not first and turn.text:
                line += f"  text: {turn.text[:80]!r}"
        print(line)

    n = len(results)
    tool_ok = sum(r.tool_ok for r in results)
    args_ok = sum(r.args_ok for r in results)
    print()
    print(f"Right tool:              {tool_ok}/{n} ({tool_ok * 100 // max(n, 1)}%)")
    print(f"Right tool + arguments:  {args_ok}/{n} ({args_ok * 100 // max(n, 1)}%)")
    print(f"Model: {settings.AI_MODEL}, effort {settings.AI_CHAT_EFFORT}")
    print(f"Cost: ₱{total_cost / 100:.2f}")
    return 0 if n and tool_ok == n else 1


if __name__ == "__main__":
    sys.exit(main())
