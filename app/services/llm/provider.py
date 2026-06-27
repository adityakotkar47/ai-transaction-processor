"""
LLM provider abstraction.

GeminiProvider is the sole concrete implementation.
The abstract base class keeps the design open for extension
without the codebase depending on any specific SDK.
"""

from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """Abstract LLM provider — all implementations must respect these contracts."""

    @abstractmethod
    def classify_batch(self, transactions: list[dict]) -> dict[str, str]:
        """
        Classify a list of transactions into categories.

        Parameters
        ----------
        transactions : list of dicts with keys:
            id        – DB UUID (string) used to map results back
            merchant  – merchant name
            amount    – float
            currency  – e.g. "INR"
            category  – existing category (hint for LLM)

        Returns
        -------
        dict mapping id (str) → llm_category (str)
        """
        ...

    @abstractmethod
    def generate_summary(self, transactions: list[dict]) -> dict:
        """
        Generate a structured JSON narrative summary.

        Parameters
        ----------
        transactions : list of dicts with keys:
            id, merchant, amount, currency, category, is_anomaly, status

        Returns
        -------
        dict with keys:
            total_spend, top_merchants, anomaly_count,
            category_breakdown, narrative, risk_level
        """
        ...


def get_llm_provider() -> LLMProvider:
    """Factory: returns a GeminiProvider instance."""
    from app.services.llm.gemini import GeminiProvider  # noqa: PLC0415

    return GeminiProvider()
