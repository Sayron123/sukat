"""Which AI provider reads list photos and answers chat questions. The rest of the app
depends only on the VisionReader, ScanAI and ChatModel interfaces (app/ai/base.py), never
on a provider's module.

To add a provider: implement ScanAI (read_photo, match_items) in its own module, add
its name to AI_PROVIDER in settings, and add a branch in get_scan_ai() below.
"""

from functools import cache

from app.ai.base import ChatModel, ScanAI, VisionReader
from app.core.config import settings


@cache
def get_vision_reader() -> VisionReader:
    """The scan reader (FastAPI dependency; tests override it with a fake): the
    multi-step pipeline (read -> match -> check) on the AI_PROVIDER's model."""
    from app.ai.scan_pipeline import MultiStepReader

    return MultiStepReader(get_scan_ai())


@cache
def get_scan_ai() -> ScanAI:
    """The AI steps of the multi-step scan, from AI_PROVIDER ("anthropic" or "gemini")."""
    if settings.AI_PROVIDER == "gemini":
        from app.ai.gemini_reader import GeminiScanAI

        return GeminiScanAI()
    if settings.AI_PROVIDER == "anthropic":
        from app.ai.anthropic_reader import AnthropicScanAI

        return AnthropicScanAI()
    raise ValueError(f"Unknown AI_PROVIDER: {settings.AI_PROVIDER}")


@cache
def get_chat_model() -> ChatModel:
    """The chat model (FastAPI dependency; tests override it with a fake). Always Claude:
    AI_PROVIDER picks the scan reader only, since chat has no Gemini version yet."""
    from app.ai.anthropic_chat import AnthropicChatModel

    return AnthropicChatModel()
