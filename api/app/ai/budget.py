import math
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.models import AIUsage
from app.ai.schemas import AIUsageOut
from app.core.config import settings
from app.core.errors import TooManyRequests
from app.stores.models import Store

SCAN_FEATURE_PREFIX = "scan_"
_STORE_TZ = ZoneInfo(settings.STORE_TIMEZONE)


class AIBudgetReached(TooManyRequests):
    code = "ai_budget_reached"


def month_bounds(now: datetime | None = None) -> tuple[datetime, datetime]:
    local = (now or datetime.now(UTC)).astimezone(_STORE_TZ)
    start = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return start, (start + timedelta(days=32)).replace(day=1)


def _budget(db: Session, store_id: UUID) -> int:
    custom = db.scalar(select(Store.ai_monthly_budget_centavos).where(Store.id == store_id))
    return settings.AI_MONTHLY_BUDGET_CENTAVOS if custom is None else custom


def _spent(db: Session, store_id: UUID, start: datetime, end: datetime) -> dict[str, Decimal]:
    rows = db.execute(
        select(AIUsage.feature, func.sum(AIUsage.cost_centavos))
        .where(AIUsage.store_id == store_id, AIUsage.created_at >= start, AIUsage.created_at < end)
        .group_by(AIUsage.feature)
    ).all()
    return {feature: total for feature, total in rows}


def _peso(centavos: int) -> str:
    return f"₱{centavos // 100:,}.{centavos % 100:02d}"


def ensure_within_budget(db: Session, store_id: UUID, now: datetime | None = None) -> None:
    now = now or datetime.now(UTC)
    start, end = month_bounds(now)
    budget = _budget(db, store_id)
    if sum(_spent(db, store_id, start, end).values(), Decimal(0)) < budget:
        return
    wait = max(1, int((end - now).total_seconds()))
    raise AIBudgetReached(
        f"Your store has used its {_peso(budget)} AI budget for this month. "
        f"Photo reading and the AI assistant will work again on {end:%b} {end.day}.",
        headers={"Retry-After": str(wait)},
        extra={"resets_at": end.isoformat()},
    )


def usage_summary(db: Session, store_id: UUID, now: datetime | None = None) -> AIUsageOut:
    start, end = month_bounds(now)
    budget = _budget(db, store_id)
    spent = _spent(db, store_id, start, end)
    total = sum(spent.values(), Decimal(0))
    scans = sum(
        (v for k, v in spent.items() if k.startswith(SCAN_FEATURE_PREFIX)), Decimal(0)
    )
    used = math.ceil(total)
    return AIUsageOut(
        month=f"{start:%B %Y}",
        resets_on=end.date(),
        budget_centavos=budget,
        spent_centavos=used,
        remaining_centavos=max(0, budget - used),
        scans_centavos=math.ceil(scans),
        chat_centavos=used - math.ceil(scans),
        reached=total >= budget,
    )
