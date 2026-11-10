import json
from decimal import Decimal
from typing import Any

import httpx2
from google import genai
from google.genai import errors, types
from pydantic import ValidationError

from app.ai.base import ImageType
from app.ai.convert import catalog_refs, catalog_text, parse_result, system_prompt
from app.ai.errors import AIReadError
from app.ai.schemas import RAW_RESULT_SCHEMA, AIUsageInfo, CatalogEntry, ReadResult
from app.core.config import settings

PROVIDER = "gemini"
NETWORK_ERRORS = (httpx2.TransportError, errors.UnknownApiResponseError)
_BLOCKED = {
    types.FinishReason.SAFETY,
    types.FinishReason.RECITATION,
    types.FinishReason.BLOCKLIST,
    types.FinishReason.PROHIBITED_CONTENT,
    types.FinishReason.SPII,
    types.FinishReason.IMAGE_SAFETY,
    types.FinishReason.IMAGE_PROHIBITED_CONTENT,
    types.FinishReason.IMAGE_RECITATION,
}


def make_client() -> genai.Client | None:
    try:
        return genai.Client(api_key=settings.GEMINI_API_KEY.get_secret_value() or None)
    except ValueError:
        return None


def thinking_config() -> types.ThinkingConfig:
    level = types.ThinkingLevel(settings.AI_GEMINI_THINKING_LEVEL.upper())
    return types.ThinkingConfig(thinking_level=level)


def is_transient(error: errors.APIError) -> bool:
    code = error.code or 0
    return code in (408, 429) or code >= 500


def usage_info(response: Any, model: str) -> AIUsageInfo:
    u = response.usage_metadata
    prompt = (u.prompt_token_count or 0) if u else 0
    cached = (u.cached_content_token_count or 0) if u else 0
    answer = (u.candidates_token_count or 0) if u else 0
    thoughts = (u.thoughts_token_count or 0) if u else 0
    return AIUsageInfo(
        model=response.model_version or model,
        provider=PROVIDER,
        input_tokens=prompt - cached,
        output_tokens=answer + thoughts,
        cache_read_tokens=cached,
    )


def finish_reason(response: Any) -> Any:
    return response.candidates[0].finish_reason if response.candidates else None


def is_blocked(response: Any) -> bool:
    feedback = response.prompt_feedback
    return bool(feedback and feedback.block_reason) or finish_reason(response) in _BLOCKED


def reply_parts(response: Any) -> list[Any]:
    if not response.candidates or response.candidates[0].content is None:
        return []
    return response.candidates[0].content.parts or []


def reply_text(parts: list[Any]) -> str:
    return "".join(p.text for p in parts if p.text and not p.thought).strip()


class GeminiVisionReader:
    def __init__(
        self,
        client: genai.Client | None = None,
        *,
        model: str | None = None,
        max_retries: int | None = None,
    ) -> None:
        self.client = client
        self.model = model or settings.AI_MODEL
        self.max_retries = settings.AI_MAX_RETRIES if max_retries is None else max_retries

    def read_list(
        self,
        image: bytes,
        media_type: ImageType,
        catalog: list[CatalogEntry],
        scan_type: str,
    ) -> ReadResult:
        self.client = self.client or make_client()
        if self.client is None:
            raise AIReadError("The reader is not set up correctly.", retryable=False)

        refs = catalog_refs(catalog)
        kind = "a supplier delivery (stock in)" if scan_type == "stock_in" else "a customer sale"
        retry = types.HttpRetryOptions(attempts=self.max_retries + 1) if self.max_retries else None
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=[
                    types.Content(
                        role="user",
                        parts=[
                            types.Part.from_bytes(data=image, mime_type=media_type),
                            types.Part(text=f"This list is {kind}. Read every item line."),
                        ],
                    )
                ],
                config=types.GenerateContentConfig(
                    system_instruction=f"{system_prompt(scan_type)}\n\n{catalog_text(refs)}",
                    max_output_tokens=16000,
                    thinking_config=thinking_config(),
                    response_mime_type="application/json",
                    response_json_schema=RAW_RESULT_SCHEMA,
                    http_options=types.HttpOptions(
                        timeout=int(settings.AI_TIMEOUT_SECONDS * 1000), retry_options=retry
                    ),
                ),
            )
        except httpx2.TimeoutException as e:
            raise AIReadError("Reading took too long. Please try again.", retryable=True) from e
        except NETWORK_ERRORS as e:
            raise AIReadError("The reader had a problem. Please try again.", retryable=True) from e
        except errors.APIError as e:
            if e.code == 429:
                raise AIReadError("The reader is busy. Please try again.", retryable=True) from e
            if is_transient(e):
                raise AIReadError(
                    "The reader had a problem. Please try again.", retryable=True
                ) from e
            raise AIReadError("The reader is not set up correctly.", retryable=False) from e

        usage = usage_info(response, self.model)
        if is_blocked(response):
            raise AIReadError("This photo could not be read.", retryable=False, usage=usage)
        if finish_reason(response) == types.FinishReason.MAX_TOKENS:
            raise AIReadError(
                "The list is too long for one photo. Take it in parts.",
                retryable=False,
                usage=usage,
            )

        text = reply_text(reply_parts(response))
        try:
            data = json.loads(text, parse_float=Decimal)
            lines = parse_result(data, refs)
        except (json.JSONDecodeError, ValidationError) as e:
            raise AIReadError(
                "The reader gave an unexpected answer. Please try again.",
                retryable=True,
                usage=usage,
            ) from e
        return ReadResult(lines=lines, usage=usage, raw=json.loads(text))
