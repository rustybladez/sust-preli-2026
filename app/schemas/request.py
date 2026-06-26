from typing import Any

from pydantic import BaseModel, Field

from app.schemas.enums import (
    Channel,
    Language,
    TransactionStatus,
    TransactionType,
    UserType,
)


class Transaction(BaseModel):
    transaction_id: str
    timestamp: str
    type: TransactionType
    amount: float
    counterparty: str
    status: TransactionStatus


class TicketRequest(BaseModel):
    ticket_id: str
    complaint: str
    language: Language | None = None
    channel: Channel | None = None
    user_type: UserType | None = None
    campaign_context: str | None = None
    transaction_history: list[Transaction] = Field(default_factory=list)
    metadata: dict[str, Any] | None = None
