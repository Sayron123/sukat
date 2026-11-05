from uuid import UUID

from sqlalchemy.orm import Session

from app.ai.models import AIUsage
from app.ai.pricing import cost_centavos
from app.ai.schemas import AIUsageInfo


def log_usage(db: Session, store_id: UUID, feature: str, usage: AIUsageInfo) -> AIUsage:
    """Add one ai_usage row. Does not commit: it is saved with the caller's changes."""
    row = AIUsage(
        store_id=store_id,
        feature=feature,
        model=usage.model,
        tokens_in=usage.tokens_in,
        tokens_out=usage.output_tokens,
        cost_centavos=cost_centavos(usage),
    )
    db.add(row)
    return row
