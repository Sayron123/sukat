"""ScanAI implementation on the Anthropic Messages API (Claude)."""

import base64
from typing import Any

import anthropic

from app.ai.base import ImageType
from app.ai.errors import AIReadError
from app.ai.scan_output import (
    MATCH_PROMPT,
    MAX_OUTPUT_TOKENS,
    READ_PROMPT,
    READ_REQUEST,
    match_request,
    parse_match,
    parse_read,
    prompt,
)
from app.ai.schemas import (
    MATCH_SCHEMA,
    READ_SCHEMA,
    AIUsageInfo,
    MatchAnswer,
    MatchItem,
    ReadLine,
)
from app.core.config import settings

FALLBACK_BETA = "server-side-fallback-2026-07-01"  # refusal fallback (AI_REFUSAL_FALLBACK)


def _usage(response: Any) -> AIUsageInfo:
    u = response.usage
    return AIUsageInfo(
        model=response.model,
        input_tokens=u.input_tokens or 0,
        output_tokens=u.output_tokens or 0,
        cache_write_tokens=u.cache_creation_input_tokens or 0,
        cache_read_tokens=u.cache_read_input_tokens or 0,
    )


# ---------- multi-step scan (ScanAI) ----------


class AnthropicScanAI:
    """ScanAI on Claude: one Messages API call per AI step, structured output."""

    def __init__(self, client: anthropic.Anthropic | None = None) -> None:
        self.client = client or anthropic.Anthropic(
            api_key=settings.ANTHROPIC_API_KEY.get_secret_value() or None,
            timeout=settings.AI_TIMEOUT_SECONDS,
            max_retries=settings.AI_MAX_RETRIES,
        )

    def _create(
        self, system: list[Any], content: list[Any], schema: dict
    ) -> tuple[Any, AIUsageInfo]:
        extra: dict[str, Any] = {}
        if settings.AI_REFUSAL_FALLBACK:
            extra = {"betas": [FALLBACK_BETA], "fallbacks": "default"}
        try:
            response = self.client.beta.messages.create(
                model=settings.AI_MODEL,
                max_tokens=MAX_OUTPUT_TOKENS,
                system=system,
                messages=[{"role": "user", "content": content}],
                output_config={
                    "effort": settings.AI_EFFORT,
                    "format": {"type": "json_schema", "schema": schema},
                },
                **extra,
            )
        except TypeError as e:  # the SDK found no API key or login
            if "authentication" not in str(e):
                raise
            raise AIReadError("The reader is not set up yet.", retryable=False) from e
        except (anthropic.APITimeoutError, anthropic.APIConnectionError) as e:
            raise AIReadError("Reading took too long. Please try again.", retryable=True) from e
        except anthropic.RateLimitError as e:
            raise AIReadError("The reader is busy. Please try again.", retryable=True) from e
        except anthropic.APIStatusError as e:
            if e.status_code >= 500:
                raise AIReadError(
                    "The reader had a problem. Please try again.", retryable=True
                ) from e
            raise AIReadError("The reader is not set up correctly.", retryable=False) from e

        usage = _usage(response)
        if response.stop_reason == "refusal":
            raise AIReadError("This photo could not be read.", retryable=False, usage=usage)
        if response.stop_reason == "max_tokens":
            raise AIReadError(
                "The list is too long for one photo. Take it in parts.",
                retryable=False,
                usage=usage,
            )
        text = next((b.text for b in response.content if b.type == "text"), None)
        return text, usage

    def read_photo(self, image: bytes, media_type: ImageType) -> tuple[list[ReadLine], AIUsageInfo]:
        text, usage = self._create(
            [{"type": "text", "text": prompt(READ_PROMPT)}],
            [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": base64.standard_b64encode(image).decode("ascii"),
                    },
                },
                {"type": "text", "text": READ_REQUEST},
            ],
            READ_SCHEMA,
        )
        return parse_read(text, usage), usage

    def match_items(
        self, items: list[MatchItem], catalog_text: str
    ) -> tuple[list[MatchAnswer], AIUsageInfo]:
        text, usage = self._create(
            [
                {"type": "text", "text": prompt(MATCH_PROMPT)},
                # The store's product list changes rarely: cache it across scans.
                {"type": "text", "text": catalog_text, "cache_control": {"type": "ephemeral"}},
            ],
            [{"type": "text", "text": match_request(items)}],
            MATCH_SCHEMA,
        )
        return parse_match(text, usage), usage
