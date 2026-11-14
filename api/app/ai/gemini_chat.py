import json
from typing import Any

import httpx2
from google import genai
from google.genai import errors, types

from app.ai.base import (
    AssistantText,
    ChatItem,
    ChatTurn,
    ToolCall,
    ToolResult,
    ToolResults,
    UserText,
)
from app.ai.errors import AIChatError
from app.ai.gemini_reader import (
    NETWORK_ERRORS,
    finish_reason,
    is_blocked,
    is_transient,
    make_client,
    reply_parts,
    reply_text,
    thinking_config,
    usage_info,
)
from app.core.config import settings

_LOCAL_CALL_ID = "local-call-"


def _function_response(result: ToolResult, name: str) -> types.FunctionResponse:
    key = "error" if result.is_error else "output"
    call_id = None if result.call_id.startswith(_LOCAL_CALL_ID) else result.call_id
    return types.FunctionResponse(id=call_id, name=name, response={key: json.loads(result.content)})


def _contents(items: list[ChatItem]) -> list[Any]:
    names = {
        call.id: call.name
        for item in items
        if isinstance(item, ChatTurn)
        for call in item.tool_calls
    }
    out: list[Any] = []
    for item in items:
        if isinstance(item, UserText):
            out.append(types.Content(role="user", parts=[types.Part(text=item.text)]))
        elif isinstance(item, AssistantText):
            out.append(types.Content(role="model", parts=[types.Part(text=item.text)]))
        elif isinstance(item, ToolResults):
            parts = [
                types.Part(function_response=_function_response(r, names[r.call_id]))
                for r in item.results
            ]
            out.append(types.Content(role="user", parts=parts))
        else:
            out.append(item.raw)
    return out


def _tools(specs: list[dict[str, Any]]) -> list[types.Tool] | None:
    if not specs:
        return None
    declarations = [
        types.FunctionDeclaration(
            name=t["name"], description=t["description"], parameters_json_schema=t["input_schema"]
        )
        for t in specs
    ]
    return [types.Tool(function_declarations=declarations)]


def _tool_config(specs: list[dict[str, Any]], allow_tools: bool) -> types.ToolConfig | None:
    if not specs:
        return None
    mode = (
        types.FunctionCallingConfigMode.AUTO
        if allow_tools
        else types.FunctionCallingConfigMode.NONE
    )
    return types.ToolConfig(function_calling_config=types.FunctionCallingConfig(mode=mode))


class GeminiChatModel:
    def __init__(
        self, client: genai.Client | None = None, *, model: str | None = None, backup: bool = False
    ) -> None:
        self.client = client
        self.model = model or settings.AI_MODEL
        self.backup = backup

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
        self.client = self.client or make_client()
        if self.client is None:
            raise AIChatError("The assistant is not set up yet.", retryable=False)

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=_contents(items),
                config=types.GenerateContentConfig(
                    system_instruction=f"{system}\n\n{context}",
                    max_output_tokens=settings.AI_CHAT_MAX_TOKENS,
                    thinking_config=thinking_config(self.model),
                    tools=_tools(tools),
                    tool_config=_tool_config(tools, allow_tools),
                    http_options=types.HttpOptions(timeout=max(1, int(timeout * 1000))),
                ),
            )
        except httpx2.TimeoutException as e:
            raise AIChatError("That took too long. Please try again.", retryable=True) from e
        except NETWORK_ERRORS as e:
            raise AIChatError(
                "The assistant had a problem. Please try again.", retryable=True
            ) from e
        except errors.APIError as e:
            if e.code == 429:
                raise AIChatError("The assistant is busy. Please try again.", retryable=True) from e
            if is_transient(e):
                raise AIChatError(
                    "The assistant had a problem. Please try again.", retryable=True
                ) from e
            raise AIChatError("The assistant is not set up correctly.", retryable=False) from e

        usage = usage_info(response, self.model, backup=self.backup)
        parts = reply_parts(response)
        calls = [
            ToolCall(
                id=p.function_call.id or f"{_LOCAL_CALL_ID}{i}",
                name=p.function_call.name,
                input=p.function_call.args or {},
            )
            for i, p in enumerate(parts)
            if p.function_call
        ]
        reason = finish_reason(response)
        if is_blocked(response):
            stop = "refusal"
        elif reason == types.FinishReason.MAX_TOKENS:
            stop = "max_tokens"
        elif calls:
            stop = "tool_use"
        elif reason == types.FinishReason.STOP:
            stop = "end"
        else:
            raise AIChatError(
                "The assistant had a problem. Please try again.", retryable=True, usage=usage
            )
        return ChatTurn(
            text=reply_text(parts),
            tool_calls=calls,
            stop=stop,
            usage=usage,
            raw=response.candidates[0].content if response.candidates else None,
        )
