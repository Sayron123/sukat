from decimal import Decimal

from app.ai.schemas import AIUsageInfo
from app.core.config import settings

_MILLION = Decimal(1_000_000)


def cost_centavos(usage: AIUsageInfo) -> Decimal:
    """Estimated cost of one call in PHP centavos, from the price settings of the
    provider that answered (Claude: AI_PRICE_*, Gemini: GEMINI_PRICE_*).

    Uses the configured model's prices even if a refusal fallback answered; fallbacks
    are rare and priced the same or lower.
    """
    if usage.provider == "gemini":
        usd = (
            Decimal(usage.input_tokens) * settings.GEMINI_PRICE_INPUT_PER_MTOK_USD
            + Decimal(usage.output_tokens) * settings.GEMINI_PRICE_OUTPUT_PER_MTOK_USD
            + Decimal(usage.cache_read_tokens) * settings.GEMINI_PRICE_CACHE_READ_PER_MTOK_USD
        ) / _MILLION
    else:
        usd = (
            Decimal(usage.input_tokens) * settings.AI_PRICE_INPUT_PER_MTOK_USD
            + Decimal(usage.output_tokens) * settings.AI_PRICE_OUTPUT_PER_MTOK_USD
            + Decimal(usage.cache_write_tokens) * settings.AI_PRICE_CACHE_WRITE_PER_MTOK_USD
            + Decimal(usage.cache_read_tokens) * settings.AI_PRICE_CACHE_READ_PER_MTOK_USD
        ) / _MILLION
    return (usd * settings.USD_TO_PHP * 100).quantize(Decimal("0.0001"))
