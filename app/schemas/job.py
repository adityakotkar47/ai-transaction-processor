from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------

class JobCreateResponse(BaseModel):
    job_id: UUID
    status: str
    message: str


# ---------------------------------------------------------------------------
# Status response (includes optional summary block when completed)
# ---------------------------------------------------------------------------

class SummaryBrief(BaseModel):
    total_spend: float | None = None
    anomaly_count: int | None = None
    narrative: str | None = None
    risk_level: str | None = None
    llm_failed: bool = False


class JobStatusResponse(BaseModel):
    job_id: UUID
    status: str
    original_filename: str
    total_rows: int | None = None
    cleaned_rows: int | None = None
    duplicate_rows: int | None = None
    anomaly_count: int | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime
    summary: SummaryBrief | None = None


# ---------------------------------------------------------------------------
# Full results response
# ---------------------------------------------------------------------------

class JobResultsResponse(BaseModel):
    job_id: UUID
    status: str
    transactions: list[Any] = Field(default_factory=list)
    anomalies: list[Any] = Field(default_factory=list)
    summary: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# List jobs response
# ---------------------------------------------------------------------------

class JobListItem(BaseModel):
    job_id: UUID
    status: str
    original_filename: str
    total_rows: int | None = None
    cleaned_rows: int | None = None
    anomaly_count: int | None = None
    created_at: datetime
    updated_at: datetime


class JobListResponse(BaseModel):
    jobs: list[JobListItem]
    total: int
    page: int
    page_size: int
