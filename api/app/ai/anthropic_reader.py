"""VisionReader implementation on the Anthropic Messages API (Claude)."""

import base64
import json
from decimal import Decimal
from functools import cache
from pathlib import Path
from typing import Any

import anthropic
from pydantic import ValidationError

from app.ai.base import ImageType
from app.ai.convert import catalog_refs, catalog_text, parse_result
from app.ai.errors import AIReadError
from app.ai.schemas import RAW_RESULT_SCHEMA, AIUsageInfo, CatalogEntry, ReadResult
from app.core.config import settings

PROMPT_PATH = Path(__file__).parent / "prompts" / "read_list.md"
FALLBACK_BETA = "server-side-fallback-2026-07-01"


@cache
def _system_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def _usage(response: Any) -> AIUsageInfo:
    u = response.usage
    return AIUsageInfo(
        model=response.model,
        input_tokens=u.input_tokens or 0,
        output_tokens=u.output_tokens or 0,
        cache_write_tokens=u.cache_creation_input_tokens or 0,
        cache_read_tokens=u.cache_read_input_tokens or 0,
    )


class AnthropicVisionReader:
    def __init__(self, client: anthropic.Anthropic | None = None) -> None:
        # timeout + max_retries=1: one automatic retry on timeouts, 429, 5xx and network errors.
        self.client = client or anthropic.Anthropic(
            api_key=settings.ANTHROPIC_API_KEY or None,
            timeout=settings.AI_TIMEOUT_SECONDS,
            max_retries=settings.AI_MAX_RETRIES,
        )

    def read_list(
        self,
        image: bytes,
        media_type: ImageType,
        catalog: list[CatalogEntry],
        scan_type: str,
    ) -> ReadResult:
        refs = catalog_refs(catalog)
        kind = "a supplier delivery (stock in)" if scan_type == "stock_in" else "a customer sale"
        extra: dict[str, Any] = {}
        if settings.AI_REFUSAL_FALLBACK:
            # If a safety classifier declines, the API re-runs on a recommended model.
            extra = {"betas": [FALLBACK_BETA], "fallbacks": "default"}

        try:
            response = self.client.beta.messages.create(
                model=settings.AI_MODEL,
                max_tokens=16000,
                # Order matters for caching: fixed prompt, then this store's product list
                # (cached), then the photo, which changes every time.
                system=[
                    {"type": "text", "text": _system_prompt()},
                    {
                        "type": "text",
                        "text": catalog_text(refs),
                        "cache_control": {"type": "ephemeral"},
                    },
                ],
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": base64.standard_b64encode(image).decode("ascii"),
                                },
                            },
                            {"type": "text", "text": f"This list is {kind}. Read every item line."},
                        ],
                    }
                ],
                output_config={
                    "effort": settings.AI_EFFORT,
                    "format": {"type": "json_schema", "schema": RAW_RESULT_SCHEMA},
                },
                **extra,
            )
        except (anthropic.APITimeoutError, anthropic.APIConnectionError) as e:
            raise AIReadError("Reading took too long. Please try again.", retryable=True) from e
        except anthropic.RateLimitError as e:
            raise AIReadError("The reader is busy. Please try again.", retryable=True) from e
        except anthropic.APIStatusError as e:
            if e.status_code >= 500:
                raise AIReadError(
                    "The reader had a problem. Please try again.", retryable=True
                ) from e
            # 400/401/403/404: our request or configuration is wrong; retrying won't help.
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
        try:
            data = json.loads(text or "", parse_float=Decimal)
            lines = parse_result(data, refs)
        except (json.JSONDecodeError, ValidationError) as e:
            raise AIReadError(
                "The reader gave an unexpected answer. Please try again.",
                retryable=True,
                usage=usage,
            ) from e
        return ReadResult(lines=lines, usage=usage, raw=json.loads(text or "{}"))
