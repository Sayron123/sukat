from decimal import Decimal

from app.ai.schemas import AIUsageInfo
from app.core.config import settings

_MILLION = Decimal(1_000_000)


def _prices(provider: str) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    if provider == settings.AI_FALLBACK_PROVIDER:
        return (
            settings.AI_FALLBACK_PRICE_INPUT_PER_MTOK_USD,
            settings.AI_FALLBACK_PRICE_OUTPUT_PER_MTOK_USD,
            settings.AI_FALLBACK_PRICE_CACHE_WRITE_PER_MTOK_USD,
            settings.AI_FALLBACK_PRICE_CACHE_READ_PER_MTOK_USD,
        )
    return (
        settings.AI_PRICE_INPUT_PER_MTOK_USD,
        settings.AI_PRICE_OUTPUT_PER_MTOK_USD,
        settings.AI_PRICE_CACHE_WRITE_PER_MTOK_USD,
        settings.AI_PRICE_CACHE_READ_PER_MTOK_USD,
    )


def cost_centavos(usage: AIUsageInfo) -> Decimal:
    """Estimated cost of one call in PHP centavos, from the price settings.

    Uses the configured model's prices even if a refusal fallback answered; fallbacks
    are rare and priced the same or lower.
    """
    price_in, price_out, price_write, price_read = _prices(usage.provider)
    usd = (
        Decimal(usage.input_tokens) * price_in
        + Decimal(usage.output_tokens) * price_out
        + Decimal(usage.cache_write_tokens) * price_write
        + Decimal(usage.cache_read_tokens) * price_read
    ) / _MILLION
    return (usd * settings.USD_TO_PHP * 100).quantize(Decimal("0.0001"))
