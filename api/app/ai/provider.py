"""Which AI provider reads list photos and answers chat questions. The rest of the app
depends only on the VisionReader and ChatModel interfaces (app/ai/base.py), never on a
provider's module.

To add a provider: implement VisionReader and ChatModel in their own modules, add its name
to AI_PROVIDER and AI_FALLBACK_PROVIDER in settings, and add a branch below.
"""

from functools import cache

from app.ai.base import ChatModel, VisionReader
from app.core.config import settings


def _reader(provider: str, model: str, max_retries: int) -> VisionReader:
    if provider == "gemini":
        from app.ai.gemini_reader import GeminiVisionReader

        return GeminiVisionReader(model=model, max_retries=max_retries)
    if provider == "anthropic":
        from app.ai.anthropic_reader import AnthropicVisionReader

        return AnthropicVisionReader(model=model, max_retries=max_retries)
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
def get_vision_reader() -> VisionReader:
    """The configured reader (FastAPI dependency; tests override it with a fake)."""
    retries = 0 if settings.has_ai_fallback else settings.AI_MAX_RETRIES
    return _reader(settings.AI_PROVIDER, settings.AI_MODEL, retries)


@cache
def get_backup_vision_reader() -> VisionReader | None:
    if not settings.has_ai_fallback:
        return None
    return _reader(settings.AI_FALLBACK_PROVIDER, settings.AI_FALLBACK_MODEL, 0)


@cache
def get_chat_model() -> ChatModel:
    """The configured chat model (FastAPI dependency; tests override it with a fake)."""
    return _chat(settings.AI_PROVIDER, settings.AI_MODEL)


@cache
def get_backup_chat_model() -> ChatModel | None:
    if not settings.has_ai_fallback:
        return None
    return _chat(settings.AI_FALLBACK_PROVIDER, settings.AI_FALLBACK_MODEL)
