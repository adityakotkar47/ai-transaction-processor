"""
Gemini LLM provider using google-genai SDK.

Implementation:
- Batched classification: ≤30 transactions per API call
- Structured JSON output via response_mime_type="application/json"
- Retry logic via @llm_retry decorator (exponential backoff)
- Exceptions propagate to caller for llm_failed handling
"""

import json
import logging

from google import genai
from google.genai import types

from app.core.config import settings
from app.domain.enums import VALID_CATEGORIES
from app.services.llm.provider import LLMProvider
from app.services.llm.retry import llm_retry

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 30  # rows per batch call — safe token ceiling for 3.5-flash


class GeminiProvider(LLMProvider):
    def __init__(self) -> None:
        if not settings.GEMINI_API_KEY or settings.GEMINI_API_KEY.startswith("REPLACE"):
            raise ValueError(
                "GEMINI_API_KEY is not set. "
                "Add your key to .env.defaults or set the environment variable."
            )
        self._client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self._model = settings.GEMINI_MODEL

    # ── Classification ────────────────────────────────────────────────────────

    def classify_batch(self, transactions: list[dict]) -> dict[str, str]:
        """
        Batch-classify all transactions.  Chunks into ≤30 per API call.
        Batch processing required: minimum 2 transactions per API call.

        Returns {id: category} dict.
        """
        results: dict[str, str] = {}
        for i in range(0, len(transactions), _CHUNK_SIZE):
            chunk = transactions[i : i + _CHUNK_SIZE]
            chunk_results = self._classify_chunk(chunk)
            results.update(chunk_results)
            logger.debug("Classified chunk %d–%d", i, i + len(chunk))
        return results

    @llm_retry
    def _classify_chunk(self, rows: list[dict]) -> dict[str, str]:
        categories_str = ", ".join(VALID_CATEGORIES)
        payload = [
            {"id": r["id"], "merchant": r["merchant"], "amount": r["amount"],
             "currency": r["currency"], "hint_category": r.get("category", "")}
            for r in rows
        ]
        prompt = (
            f"You are a financial transaction classifier.\n"
            f"Classify each transaction into EXACTLY ONE of: {categories_str}.\n\n"
            f"Transactions (JSON array):\n{json.dumps(payload, indent=2)}\n\n"
            f"Return ONLY valid JSON in this exact structure (no extra keys, no markdown):\n"
            f'{{"classifications": [{{"id": "<uuid>", "category": "<category>"}}, ...]}}\n\n'
            f"Use the merchant name and hint_category as classification signals. "
            f'If uncertain, use "Uncategorised".'
        )
        response = self._client.models.generate_content(
            model=self._model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1,
            ),
        )
        raw = response.text.strip()
        data = json.loads(raw)
        return {item["id"]: item["category"] for item in data.get("classifications", [])}

    # ── Narrative summary ─────────────────────────────────────────────────────

    def generate_summary(self, transactions: list[dict]) -> dict:
        """
        Generate a structured JSON narrative from the full transaction list
        in a single LLM call.
        """
        return self._generate_summary_inner(transactions)

    @llm_retry
    def _generate_summary_inner(self, transactions: list[dict]) -> dict:
        # Compute lightweight aggregates client-side to keep the prompt small
        total_spend = sum(t.get("amount", 0) or 0 for t in transactions)
        anomaly_count = sum(1 for t in transactions if t.get("is_anomaly"))

        # Include first 60 rows in prompt to avoid huge token count
        sample = transactions[:60]
        remainder_note = (
            f"\n(+ {len(transactions) - 60} more transactions not shown)"
            if len(transactions) > 60
            else ""
        )

        prompt = (
            "You are a financial risk analyst.  "
            f"Analyse the following {len(transactions)} transactions "
            f"(total spend: {total_spend:,.2f}, anomalies: {anomaly_count}) "
            f"and return a structured JSON summary.\n\n"
            f"Transaction sample:\n{json.dumps(sample, indent=2)}{remainder_note}\n\n"
            "Return ONLY this JSON structure (no markdown, no extra keys):\n"
            "{\n"
            '  "total_spend": <float>,\n'
            '  "top_merchants": [{"merchant": "<name>", "total": <float>, "count": <int>}],\n'
            '  "anomaly_count": <int>,\n'
            '  "category_breakdown": {"<category>": <total_float>},\n'
            '  "narrative": "<2-3 sentence analysis of spending patterns and risk>",\n'
            '  "risk_level": "<low|medium|high>"\n'
            "}\n\n"
            "Risk level rules: "
            "high = anomaly_count > 3 OR any single transaction > 50000; "
            "medium = anomaly_count > 0; "
            "low = otherwise."
        )

        response = self._client.models.generate_content(
            model=self._model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.2,
            ),
        )
        raw = response.text.strip()
        return json.loads(raw)
