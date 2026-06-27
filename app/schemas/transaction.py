from datetime import date
from uuid import UUID

from pydantic import BaseModel


class TransactionOut(BaseModel):
    id: UUID
    txn_id: str | None = None
    txn_date: date | None = None
    merchant: str | None = None
    amount: float | None = None
    currency: str | None = None
    status: str | None = None
    category: str | None = None
    account_id: str | None = None
    notes: str | None = None
    is_anomaly: bool = False
    anomaly_reason: str | None = None
    llm_category: str | None = None
    llm_failed: bool = False

    model_config = {"from_attributes": True}
