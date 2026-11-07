"""Request and response shapes of the AI chat (POST /v1/insights/chat)."""

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.insights.schemas import DateRange

MAX_MESSAGE_CHARS = 2000


class ChatMessageIn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)


class ChatIn(BaseModel):
    """The conversation, kept in the browser (never saved on the server). Only the last
    10 messages are used; the last one must be the user's new question."""

    messages: list[ChatMessageIn] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def _ends_with_question(self) -> "ChatIn":
        if self.messages[-1].role != "user":
            raise ValueError("the last message must be the user's question")
        return self


class ChatBar(BaseModel):
    label: str
    value: Decimal  # exact number from the report (centavos or a quantity)
    display: str  # "₱1,250.50" or "12 bag"


class ChatData(BaseModel):
    """A small table or bar chart built from a tool's result (never from the model's
    text), so the numbers on screen are the database's numbers."""

    kind: Literal["table", "bar"]
    title: str
    tool: str  # which tool the numbers came from
    # What the numbers cover, for "Based on sales from <dates>". None = no date range
    # (current stock, a product search, all-time history).
    basis: Literal["sales", "stock"] | None = None
    range: DateRange | None = None
    columns: list[str] = []
    rows: list[list[str]] = []
    bars: list[ChatBar] = []


class ChatOut(BaseModel):
    answer: str
    data: ChatData | None = None
    tools_used: list[str]  # tool names in the order they ran
