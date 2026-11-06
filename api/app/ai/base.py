"""Provider-agnostic interfaces: reading a list photo, and chatting with tools."""

from dataclasses import dataclass
from typing import Any, Literal, Protocol

from app.ai.schemas import AIUsageInfo, CatalogEntry, ReadResult

ImageType = Literal["image/jpeg", "image/png", "image/webp"]
ScanType = Literal["sale", "stock_in"]


class VisionReader(Protocol):
    def read_list(
        self,
        image: bytes,
        media_type: ImageType,
        catalog: list[CatalogEntry],
        scan_type: ScanType,
    ) -> ReadResult:
        """Read the list in `image`, matching items against `catalog`.

        @raises AIReadError on timeouts, refusals, or unusable output
        """
        ...


# ---------- chat with tools (Phase 6) ----------
# Provider-neutral shapes: the chat loop (app/insights/chat_service.py) only uses these,
# and each provider converts them to its own API format.


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    input: Any  # parsed JSON from the model; validated by the tool, never trusted


@dataclass(frozen=True)
class ChatTurn:
    """One reply from the model."""

    text: str
    tool_calls: list[ToolCall]
    stop: Literal["end", "tool_use", "max_tokens", "refusal"]
    usage: AIUsageInfo
    # The provider's own reply content, sent back unchanged on the next call (it can
    # hold reasoning blocks that must be returned as they were).
    raw: Any = None


@dataclass(frozen=True)
class UserText:
    text: str


@dataclass(frozen=True)
class AssistantText:
    """An earlier answer, from the history the browser sends (text only)."""

    text: str


@dataclass(frozen=True)
class ToolResult:
    call_id: str
    content: str  # JSON text
    is_error: bool = False


@dataclass(frozen=True)
class ToolResults:
    results: list[ToolResult]


ChatItem = UserText | AssistantText | ChatTurn | ToolResults


class ChatModel(Protocol):
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
        """One model call.

        @param system the fixed instructions (cacheable)
        @param context per-request facts placed after them (today's date, the role)
        @param items the conversation so far, oldest first
        @param tools provider-neutral specs: name, description, input_schema
        @param allow_tools False forces a text answer (tool-call limit reached)
        @param timeout seconds left for this call
        @raises AIChatError on timeouts or API errors
        """
        ...
