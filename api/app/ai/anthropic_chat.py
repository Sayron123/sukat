"""ChatModel implementation on the Anthropic Messages API (Claude), with tool use.

One call per respond(); the tool loop itself is provider-neutral and lives in
app/insights/chat_service.py.
"""

from typing import Any

import anthropic
from anthropic.types.beta import BetaMessageParam, BetaToolParam

from app.ai.anthropic_reader import FALLBACK_BETA, _usage
from app.ai.base import AssistantText, ChatItem, ChatTurn, ToolCall, ToolResults, UserText
from app.ai.errors import AIChatError
from app.core.config import settings

_STOPS = {"tool_use": "tool_use", "max_tokens": "max_tokens", "refusal": "refusal"}


def _messages(items: list[ChatItem]) -> list[BetaMessageParam]:
    """Provider-neutral items -> Messages API messages. Consecutive messages with the
    same role are allowed: the API joins them into one turn."""
    out: list[BetaMessageParam] = []
    for item in items:
        if isinstance(item, UserText):
            out.append({"role": "user", "content": item.text})
        elif isinstance(item, AssistantText):
            out.append({"role": "assistant", "content": item.text})
        elif isinstance(item, ToolResults):
            out.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": r.call_id,
                            "content": r.content,
                            "is_error": r.is_error,
                        }
                        for r in item.results
                    ],
                }
            )
        else:  # ChatTurn: send the model's own content back unchanged (reasoning included)
            out.append({"role": "assistant", "content": item.raw})
    return out


def _tools(specs: list[dict[str, Any]]) -> list[BetaToolParam]:
    return [
        {"name": t["name"], "description": t["description"], "input_schema": t["input_schema"]}
        for t in specs
    ]


class AnthropicChatModel:
    def __init__(self, client: anthropic.Anthropic | None = None, *, model: str | None = None):
        self.model = model or settings.AI_MODEL
        # Retries are off: one question has one overall deadline, and the caller passes
        # the time left to each call.
        self.client = client or anthropic.Anthropic(
            api_key=settings.ANTHROPIC_API_KEY.get_secret_value() or None, max_retries=0
        )

    def respond(
        self,
        *,
        system: str,
        context: str,
        items: list[ChatItem],
        tools: list[dict[str, Any]],
        allow_tools: bool,
        timeout: float,
    ) -> ChatTurn:
        extra: dict[str, Any] = {}
        if settings.AI_REFUSAL_FALLBACK:
            extra = {"betas": [FALLBACK_BETA], "fallbacks": "default"}
        try:
            response = self.client.with_options(timeout=timeout).beta.messages.create(
                model=self.model,
                max_tokens=settings.AI_CHAT_MAX_TOKENS,
                # Cache order: tools, then the fixed instructions (breakpoint here), then
                # the per-request context (date, role), which changes every day.
                tools=_tools(tools),
                tool_choice={"type": "auto"} if allow_tools else {"type": "none"},
                system=[
                    {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}},
                    {"type": "text", "text": context},
                ],
                messages=_messages(items),
                output_config={"effort": settings.AI_CHAT_EFFORT},
                **extra,
            )
        except TypeError as e:  # the SDK found no API key or login
            if "authentication" not in str(e):
                raise
            raise AIChatError("The assistant is not set up yet.", retryable=False) from e
        except (anthropic.APITimeoutError, anthropic.APIConnectionError) as e:
            raise AIChatError("That took too long. Please try again.", retryable=True) from e
        except anthropic.RateLimitError as e:
            raise AIChatError("The assistant is busy. Please try again.", retryable=True) from e
        except anthropic.APIStatusError as e:
            if e.status_code >= 500:
                raise AIChatError(
                    "The assistant had a problem. Please try again.", retryable=True
                ) from e
            raise AIChatError("The assistant is not set up correctly.", retryable=False) from e

        text = "".join(b.text for b in response.content if b.type == "text").strip()
        calls = [
            ToolCall(id=b.id, name=b.name, input=b.input)
            for b in response.content
            if b.type == "tool_use"
        ]
        stop = _STOPS.get(response.stop_reason or "", "end")
        return ChatTurn(
            text=text,
            tool_calls=calls,
            stop=stop,  # type: ignore[arg-type]  # values come from _STOPS / "end"
            usage=_usage(response),
            raw=response.content,
        )
