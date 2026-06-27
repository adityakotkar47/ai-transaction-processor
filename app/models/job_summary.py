import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class JobSummary(Base):
    __tablename__ = "job_summaries"
    __table_args__ = (UniqueConstraint("job_id", name="uq_job_summaries_job_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )

    total_spend: Mapped[float | None] = mapped_column(Numeric(15, 2), nullable=True)
    top_merchants: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    anomaly_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    category_breakdown: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    narrative: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_level: Mapped[str | None] = mapped_column(String(10), nullable=True)
    llm_failed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Relationship
    job: Mapped["Job"] = relationship("Job", back_populates="summary")  # noqa: F821

    def __repr__(self) -> str:
        return f"<JobSummary job_id={self.job_id} risk={self.risk_level} llm_failed={self.llm_failed}>"
