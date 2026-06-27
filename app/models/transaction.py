import uuid
from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        Index("ix_transactions_job_id", "job_id"),
        Index("ix_transactions_account_id", "account_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )

    # --- Cleaned CSV fields ---
    txn_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    txn_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    merchant: Mapped[str | None] = mapped_column(String(255), nullable=True)
    amount: Mapped[float | None] = mapped_column(Numeric(15, 2), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    account_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Anomaly flags ---
    is_anomaly: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    anomaly_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- LLM output ---
    llm_category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    llm_failed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Relationship
    job: Mapped["Job"] = relationship("Job", back_populates="transactions")  # noqa: F821

    def __repr__(self) -> str:
        return f"<Transaction txn_id={self.txn_id} merchant={self.merchant} amount={self.amount}>"
