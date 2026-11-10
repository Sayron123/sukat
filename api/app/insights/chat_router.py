"""AI chat about this store's sales and stock, and this month's AI usage."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.ai.base import ChatModel
from app.ai.budget import usage_summary
from app.ai.provider import get_backup_chat_model, get_chat_model
from app.ai.schemas import AIUsageOut
from app.auth.deps import CurrentMember, DbSession, VerifiedMemberDep, require_role
from app.insights import chat_service
from app.insights.chat_schemas import ChatIn, ChatOut
from app.stores.models import Role

router = APIRouter(prefix="/insights", tags=["insights"])

ChatModelDep = Annotated[ChatModel, Depends(get_chat_model)]
BackupChatDep = Annotated[ChatModel | None, Depends(get_backup_chat_model)]
Manager = Annotated[CurrentMember, Depends(require_role(Role.MANAGER))]


@router.post("/chat", response_model=ChatOut)
def chat(
    body: ChatIn,
    current: VerifiedMemberDep,
    db: DbSession,
    model: ChatModelDep,
    backup: BackupChatDep,
) -> ChatOut:
    """Any staff member. The browser sends the conversation (only the last 10 messages
    are used; nothing is saved). The answer comes with an optional table or chart built
    from the tools' results. 429 with code "chat_rate_limited" after 30 questions per
    store per hour or "ai_budget_reached" when this month's AI budget is used; 503 with
    code "chat_unavailable" (and "retryable") when the AI fails.
    """
    return chat_service.ask(db, current.store_id, current.role, body.messages, model, backup)


@router.get("/ai-usage", response_model=AIUsageOut)
def ai_usage(current: Manager, db: DbSession) -> AIUsageOut:
    return usage_summary(db, current.store_id)
