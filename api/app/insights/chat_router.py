"""POST /v1/insights/chat: ask the AI about this store's sales and stock."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.ai.base import ChatModel
from app.ai.provider import get_chat_model
from app.auth.deps import CurrentMemberDep, DbSession
from app.insights import chat_service
from app.insights.chat_schemas import ChatIn, ChatOut

router = APIRouter(prefix="/insights", tags=["insights"])

ChatModelDep = Annotated[ChatModel, Depends(get_chat_model)]


@router.post("/chat", response_model=ChatOut)
def chat(body: ChatIn, current: CurrentMemberDep, db: DbSession, model: ChatModelDep) -> ChatOut:
    """Any staff member. The browser sends the conversation (only the last 10 messages
    are used; nothing is saved). The answer comes with an optional table or chart built
    from the tools' results. 429 with code "chat_rate_limited" after 30 questions per
    store per hour; 503 with code "chat_unavailable" (and "retryable") when the AI fails.
    """
    return chat_service.ask(db, current.store_id, current.role, body.messages, model)
