from uuid import UUID

from sqlalchemy.orm import Session

from app.ai.models import AIUsage
from app.ai.pricing import cost_centavos
from app.ai.schemas import AIUsageInfo


def log_usage(db: Session, store_id: UUID, feature: str, usage: AIUsageInfo) -> AIUsage:
    """Add one ai_usage row. Does not commit: it is saved with the caller's changes."""
    row = AIUsage(store_id=store_id, feature=feature)
    fill_usage(row, usage)
    db.add(row)
    return row


def fill_usage(row: AIUsage, usage: AIUsageInfo) -> None:
    """Set the model, tokens and cost of a row (e.g. one reserved before the call)."""
    row.provider = usage.provider
    row.model = usage.model
    row.tokens_in = usage.tokens_in
    row.tokens_out = usage.output_tokens
    row.cost_centavos = cost_centavos(usage)
