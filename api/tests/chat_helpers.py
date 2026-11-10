"""A scripted stand-in for the chat model: no network, no API key.

Each step is a ChatTurn, or a function that gets the call's keyword arguments (system,
context, items, tools, allow_tools, timeout) and returns one, so a step can read the
tool results the previous step produced. Every call is recorded in `.calls`.
"""

import itertools
import json
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import pytest
from google.genai import types

from app.ai.base import ChatTurn, ToolCall, ToolResults
from app.ai.schemas import AIUsageInfo

Step = ChatTurn | Callable[[dict[str, Any]], ChatTurn]
_ids = itertools.count(1)


def usage(tokens_in: int = 1000, tokens_out: int = 100) -> AIUsageInfo:
    return AIUsageInfo(
        model="fake-chat", provider="gemini", input_tokens=tokens_in, output_tokens=tokens_out
    )


def calls(*pairs: tuple[str, dict[str, Any]]) -> ChatTurn:
    """A turn that asks for these tool calls (name, input)."""
    return ChatTurn(
        text="",
        tool_calls=[ToolCall(f"call_{next(_ids)}", name, args) for name, args in pairs],
        stop="tool_use",
        usage=usage(),
        raw=[],
    )


def say(text: str) -> ChatTurn:
    return ChatTurn(text=text, tool_calls=[], stop="end", usage=usage(), raw=[])


def last_results(kwargs: dict[str, Any]) -> list[dict[str, Any]]:
    """The tool results the model just received, parsed from JSON."""
    results = kwargs["items"][-1]
    assert isinstance(results, ToolResults)
    return [json.loads(r.content) for r in results.results]


class ScriptedModel:
    def __init__(self, *steps: Step) -> None:
        self.steps = list(steps)
        self.calls: list[dict[str, Any]] = []

    def respond(self, **kwargs: Any) -> ChatTurn:
        self.calls.append(kwargs)
        if not self.steps:
            raise AssertionError("the model was called more often than scripted")
        step = self.steps.pop(0)
        return step(kwargs) if callable(step) else step


def gemini_reply(turn: ChatTurn) -> SimpleNamespace:
    parts = [
        SimpleNamespace(
            text=None,
            thought=False,
            function_call=SimpleNamespace(id=c.id, name=c.name, args=c.input),
        )
        for c in turn.tool_calls
    ]
    if turn.text:
        parts.append(SimpleNamespace(text=turn.text, thought=False, function_call=None))
    reason = {
        "refusal": types.FinishReason.SAFETY,
        "max_tokens": types.FinishReason.MAX_TOKENS,
    }.get(turn.stop, types.FinishReason.STOP)
    return SimpleNamespace(
        model_version=turn.usage.model,
        prompt_feedback=None,
        candidates=[
            SimpleNamespace(
                finish_reason=reason,
                content=SimpleNamespace(role="model", parts=parts),
            )
        ],
        usage_metadata=SimpleNamespace(
            prompt_token_count=turn.usage.input_tokens + turn.usage.cache_read_tokens,
            cached_content_token_count=turn.usage.cache_read_tokens,
            candidates_token_count=turn.usage.output_tokens,
            thoughts_token_count=0,
        ),
    )


class GeminiScriptedModel(ScriptedModel):
    def respond(self, **kwargs: Any) -> ChatTurn:
        from app.ai.gemini_chat import GeminiChatModel

        turn = super().respond(**kwargs)
        client = SimpleNamespace(
            models=SimpleNamespace(generate_content=lambda **_: gemini_reply(turn))
        )
        return GeminiChatModel(client).respond(**kwargs)  # type: ignore[arg-type]


@pytest.fixture(params=["scripted", "gemini"])
def chat_model(api, request):
    from app.ai.provider import get_chat_model
    from app.main import app

    def install(*steps: Step) -> ScriptedModel:
        model = (GeminiScriptedModel if request.param == "gemini" else ScriptedModel)(*steps)
        app.dependency_overrides[get_chat_model] = lambda: model
        return model

    return install


def ask(api, headers, question: str, history: list[dict[str, str]] | None = None):
    body = {"messages": [*(history or []), {"role": "user", "content": question}]}
    return api.post("/insights/chat", json=body, headers=headers)
