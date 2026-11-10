"""Shared by the scan AI providers: the prompt files, and checking each step's JSON."""

import json
from functools import cache
from pathlib import Path

from pydantic import ValidationError

from app.ai.errors import AIReadError
from app.ai.schemas import AIUsageInfo, MatchAnswer, MatchOutput, ReadLine, ReadOutput

PROMPTS_DIR = Path(__file__).parent / "prompts"
READ_PROMPT = "scan_read.md"
MATCH_PROMPT = "scan_match.md"
READ_REQUEST = "Read every item row of this list."
MAX_OUTPUT_TOKENS = 16000


@cache
def prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


def parse_read(text: str | None, usage: AIUsageInfo) -> list[ReadLine]:
    """@raises AIReadError (retryable) when the JSON doesn't match the read schema"""
    try:
        return ReadOutput.model_validate(json.loads(text or "")).lines
    except (json.JSONDecodeError, ValidationError) as e:
        raise AIReadError(
            "The reader gave an unexpected answer. Please try again.",
            retryable=True,
            usage=usage,
        ) from e


def parse_match(text: str | None, usage: AIUsageInfo) -> list[MatchAnswer]:
    """@raises AIReadError (retryable) when the JSON doesn't match the match schema"""
    try:
        return MatchOutput.model_validate(json.loads(text or "")).matches
    except (json.JSONDecodeError, ValidationError) as e:
        raise AIReadError(
            "The matcher gave an unexpected answer.", retryable=True, usage=usage
        ) from e


def match_request(items: list) -> str:
    """The user message for the match step: one JSON object per unmatched line."""
    return "Match these lines:\n" + json.dumps(
        [{"line": i.line, "text": i.text} for i in items], ensure_ascii=False
    )
