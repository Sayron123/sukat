"""ScanAI implementation on Google's Gemini API (official google-genai SDK).

Both steps use structured output (a JSON schema) and the least thinking the model
allows: turned off on 2.x models (thinking_budget=0), AI_GEMINI_THINKING_LEVEL on 3.x
and later (Pro models can't go below LOW).
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


def thinking_config(model: str) -> types.ThinkingConfig:
    name = model.lower()
    if name.startswith("gemini-2"):
        return types.ThinkingConfig(thinking_budget=128 if "pro" in name else 0)
    level = types.ThinkingLevel(settings.AI_GEMINI_THINKING_LEVEL.upper())
    if "pro" in name and level == types.ThinkingLevel.MINIMAL:
        level = types.ThinkingLevel.LOW
    return types.ThinkingConfig(thinking_level=level)


def is_transient(error: errors.APIError) -> bool:
    code = error.code or 0
    return code in (408, 429) or code >= 500


def usage_info(response: Any, model: str, *, backup: bool = False) -> AIUsageInfo:
    u = response.usage_metadata
    prompt_tokens = (u.prompt_token_count or 0) if u else 0
    cached = (u.cached_content_token_count or 0) if u else 0
    answer = (u.candidates_token_count or 0) if u else 0
    thoughts = (u.thoughts_token_count or 0) if u else 0
    return AIUsageInfo(
        model=response.model_version or model,
        provider=PROVIDER,
        input_tokens=max(prompt_tokens - cached, 0),
        output_tokens=answer + thoughts,
        cache_read_tokens=cached,
        backup=backup,
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


class GeminiScanAI:
    def __init__(
        self,
        client: genai.Client | None = None,
        *,
        model: str | None = None,
        max_retries: int | None = None,
        backup: bool = False,
    ) -> None:
        self._client = client
        self.model = model or settings.AI_MODEL
        self.backup = backup
        self.max_retries = settings.AI_MAX_RETRIES if max_retries is None else max_retries

    @property
    def client(self) -> genai.Client:
        # Built on first use: genai.Client() raises when no API key can be found, and a
        # missing key should fail one scan with a clear message, not the app's startup.
        if self._client is None:
            try:
                self._client = genai.Client(
                    api_key=settings.GEMINI_API_KEY.get_secret_value() or None,
                    http_options=types.HttpOptions(
                        timeout=int(settings.AI_TIMEOUT_SECONDS * 1000),
                        retry_options=types.HttpRetryOptions(attempts=self.max_retries + 1),
                    ),
                )
            except ValueError as e:
                raise AIReadError("The reader is not set up yet.", retryable=False) from e
        return self._client

    def _generate(self, contents: list[Any], system: str, schema: dict) -> tuple[Any, AIUsageInfo]:
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    response_mime_type="application/json",
                    response_json_schema=schema,
                    thinking_config=thinking_config(self.model),
                    max_output_tokens=MAX_OUTPUT_TOKENS,
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

        usage = usage_info(response, self.model, backup=self.backup)
        if is_blocked(response):
            raise AIReadError("This photo could not be read.", retryable=False, usage=usage)
        if finish_reason(response) == types.FinishReason.MAX_TOKENS:
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
