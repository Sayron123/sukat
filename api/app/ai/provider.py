"""Which AI provider reads list photos. The rest of the app depends only on the
VisionReader interface (app/ai/base.py), never on a provider's module.

To add a provider: implement VisionReader in its own module, add its name to
AI_PROVIDER in settings, and add a branch below.
"""

from functools import cache

from app.ai.base import ScanAI, VisionReader
from app.core.config import settings


@cache
def get_vision_reader() -> VisionReader:
    """The configured reader (FastAPI dependency; tests override it with a fake)."""
    if settings.AI_PROVIDER == "anthropic":
        from app.ai.anthropic_reader import AnthropicVisionReader

        return AnthropicVisionReader()
    raise ValueError(f"Unknown AI_PROVIDER: {settings.AI_PROVIDER}")


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
