"""Errors from AI features."""

from app.ai.schemas import AIUsageInfo


class AIReadError(Exception):
    """The AI could not read the list. `retryable` tells the UI whether Retry may help.
    `usage` is set when tokens were spent anyway, so the cost can still be logged."""

    def __init__(self, message: str, *, retryable: bool, usage: AIUsageInfo | None = None):
        super().__init__(message)
        self.retryable = retryable
        self.usage = usage
