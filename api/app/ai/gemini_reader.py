"""ScanAI implementation on Google's Gemini API (official google-genai SDK).

Both steps use structured output (a JSON schema) and the least thinking the model
allows: turned off on 2.x models (thinking_budget=0), the lowest level on 3.x and
later (thinking_level=MINIMAL, or LOW on Pro models, which can't go lower).
"""

from typing import Any

import httpx2
from google import genai
from google.genai import errors, types

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

_BLOCKED = {
    types.FinishReason.SAFETY,
    types.FinishReason.PROHIBITED_CONTENT,
    types.FinishReason.BLOCKLIST,
    types.FinishReason.SPII,
    types.FinishReason.IMAGE_SAFETY,
    types.FinishReason.IMAGE_PROHIBITED_CONTENT,
    types.FinishReason.RECITATION,
}


def thinking_config(model: str) -> types.ThinkingConfig:
    """The least thinking `model` accepts. 2.x Flash models can turn it off; 2.x Pro
    needs at least 128 tokens; 3.x and later use levels (Pro's lowest is LOW)."""
    name = model.lower()
    if name.startswith("gemini-2"):
        return types.ThinkingConfig(thinking_budget=128 if "pro" in name else 0)
    level = types.ThinkingLevel.LOW if "pro" in name else types.ThinkingLevel.MINIMAL
    return types.ThinkingConfig(thinking_level=level)


def _usage(response: Any) -> AIUsageInfo:
    """Gemini counts: prompt (includes cached), candidates, thoughts (billed as output)."""
    u = response.usage_metadata
    cached = (u.cached_content_token_count or 0) if u else 0
    prompt_tokens = (u.prompt_token_count or 0) if u else 0
    return AIUsageInfo(
        model=response.model_version or settings.GEMINI_MODEL,
        input_tokens=max(prompt_tokens - cached, 0),
        output_tokens=((u.candidates_token_count or 0) + (u.thoughts_token_count or 0)) if u else 0,
        cache_read_tokens=cached,
        provider="gemini",
    )


class GeminiScanAI:
    def __init__(self, client: genai.Client | None = None) -> None:
        self._client = client

    @property
    def client(self) -> genai.Client:
        # Built on first use: genai.Client() raises when no API key can be found, and a
        # missing key should fail one scan with a clear message, not the app's startup.
        if self._client is None:
            try:
                self._client = genai.Client(
                    api_key=settings.GEMINI_API_KEY.get_secret_value() or None,
                    http_options=types.HttpOptions(
                        timeout=int(settings.AI_TIMEOUT_SECONDS * 1000),  # milliseconds
                        retry_options=types.HttpRetryOptions(attempts=settings.AI_MAX_RETRIES + 1),
                    ),
                )
            except ValueError as e:  # no API key
                raise AIReadError("The reader is not set up yet.", retryable=False) from e
        return self._client

    def _generate(self, contents: list[Any], system: str, schema: dict) -> tuple[Any, AIUsageInfo]:
        try:
            response = self.client.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    response_mime_type="application/json",
                    response_json_schema=schema,
                    thinking_config=thinking_config(settings.GEMINI_MODEL),
                    max_output_tokens=MAX_OUTPUT_TOKENS,
                ),
            )
        except (httpx2.TimeoutException, httpx2.NetworkError) as e:
            raise AIReadError("Reading took too long. Please try again.", retryable=True) from e
        except errors.APIError as e:
            if e.code == 429:
                raise AIReadError("The reader is busy. Please try again.", retryable=True) from e
            if e.code >= 500:
                raise AIReadError(
                    "The reader had a problem. Please try again.", retryable=True
                ) from e
            # 400/401/403/404: our request or configuration is wrong; retrying won't help.
            raise AIReadError("The reader is not set up correctly.", retryable=False) from e

        usage = _usage(response)
        feedback = response.prompt_feedback
        if feedback is not None and feedback.block_reason:
            raise AIReadError("This photo could not be read.", retryable=False, usage=usage)
        candidate = response.candidates[0] if response.candidates else None
        reason = candidate.finish_reason if candidate else None
        if reason in _BLOCKED:
            raise AIReadError("This photo could not be read.", retryable=False, usage=usage)
        if reason == types.FinishReason.MAX_TOKENS:
            raise AIReadError(
                "The list is too long for one photo. Take it in parts.",
                retryable=False,
                usage=usage,
            )
        return response, usage

    def read_photo(self, image: bytes, media_type: ImageType) -> tuple[list[ReadLine], AIUsageInfo]:
        response, usage = self._generate(
            [types.Part.from_bytes(data=image, mime_type=media_type), READ_REQUEST],
            prompt(READ_PROMPT),
            READ_SCHEMA,
        )
        return parse_read(response.text, usage), usage

    def match_items(
        self, items: list[MatchItem], catalog_text: str
    ) -> tuple[list[MatchAnswer], AIUsageInfo]:
        response, usage = self._generate(
            [match_request(items)],
            prompt(MATCH_PROMPT) + "\n\n" + catalog_text,
            MATCH_SCHEMA,
        )
        return parse_match(response.text, usage), usage
