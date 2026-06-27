from pydantic import BaseModel


class MerchantStat(BaseModel):
    merchant: str
    total: float
    count: int


class LLMSummary(BaseModel):
    total_spend: float | None = None
    top_merchants: list[MerchantStat] | None = None
    anomaly_count: int | None = None
    category_breakdown: dict[str, float] | None = None
    narrative: str | None = None
    risk_level: str | None = None
    llm_failed: bool = False
