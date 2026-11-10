"""Which AI provider reads list photos and answers chat questions. The rest of the app
depends only on the VisionReader, ScanAI and ChatModel interfaces (app/ai/base.py), never
on a provider's module.

To add a provider: implement ScanAI and ChatModel in their own modules, add its name to
AI_PROVIDER and AI_FALLBACK_PROVIDER in settings, and add a branch below.
"""

from functools import cache

from app.ai.base import ChatModel, ScanAI, VisionReader
from app.core.config import settings


def _scan_ai(provider: str, model: str, max_retries: int) -> ScanAI:
    if provider == "gemini":
        from app.ai.gemini_reader import GeminiScanAI

        return GeminiScanAI(model=model, max_retries=max_retries)
    if provider == "anthropic":
        from app.ai.anthropic_reader import AnthropicScanAI

        return AnthropicScanAI(model=model, max_retries=max_retries)
    raise ValueError(f"Unknown AI provider: {provider}")


def _chat(provider: str, model: str) -> ChatModel:
    if provider == "gemini":
        from app.ai.gemini_chat import GeminiChatModel

        return GeminiChatModel(model=model)
    if provider == "anthropic":
        from app.ai.anthropic_chat import AnthropicChatModel

        return AnthropicChatModel(model=model)
    raise ValueError(f"Unknown AI provider: {provider}")


@cache
def get_scan_ai() -> ScanAI:
    retries = 0 if settings.has_ai_fallback else settings.AI_MAX_RETRIES
    return _scan_ai(settings.AI_PROVIDER, settings.AI_MODEL, retries)


@cache
def get_vision_reader() -> VisionReader:
    from app.ai.scan_pipeline import MultiStepReader

    return MultiStepReader(get_scan_ai())


@cache
def get_backup_vision_reader() -> VisionReader | None:
    if not settings.has_ai_fallback:
        return None
    from app.ai.scan_pipeline import MultiStepReader

    return MultiStepReader(_scan_ai(settings.AI_FALLBACK_PROVIDER, settings.AI_FALLBACK_MODEL, 0))


@cache
def get_chat_model() -> ChatModel:
    return _chat(settings.AI_PROVIDER, settings.AI_MODEL)


@cache
def get_backup_chat_model() -> ChatModel | None:
    if not settings.has_ai_fallback:
        return None
    return _chat(settings.AI_FALLBACK_PROVIDER, settings.AI_FALLBACK_MODEL)
