"""Which AI provider reads list photos. The rest of the app depends only on the
VisionReader interface (app/ai/base.py), never on a provider's module.

To add a provider: implement VisionReader in its own module, add its name to
AI_PROVIDER in settings, and add a branch below.
"""

from functools import cache

from app.ai.base import VisionReader
from app.core.config import settings


@cache
def get_vision_reader() -> VisionReader:
    """The configured reader (FastAPI dependency; tests override it with a fake)."""
    if settings.AI_PROVIDER == "anthropic":
        from app.ai.anthropic_reader import AnthropicVisionReader

        return AnthropicVisionReader()
    raise ValueError(f"Unknown AI_PROVIDER: {settings.AI_PROVIDER}")
