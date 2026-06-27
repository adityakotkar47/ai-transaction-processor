"""
Transaction CSV cleaner.

Handles all observed dirty-data patterns from the real transactions.csv:
  - Three date formats: DD-MM-YYYY, YYYY/MM/DD, YYYY-MM-DD  → ISO 8601
  - $-prefixed amounts (e.g. "$11325.79")                   → numeric float
  - Mixed-case currency (e.g. "inr")                        → uppercase
  - Mixed-case status (e.g. "success")                      → uppercase
  - Blank category cells                                     → "Uncategorised"
  - Exact duplicate rows                                     → first occurrence kept
  - Invalid (null) amounts                                   → row dropped
"""

import logging
import re
from datetime import datetime

import pandas as pd

logger = logging.getLogger(__name__)

# ── Supported date patterns, tried in order ──────────────────────────────────
_DATE_FORMATS = [
    "%d-%m-%Y",   # 17-02-2024
    "%Y/%m/%d",   # 2024/02/05
    "%Y-%m-%d",   # 2024-07-15  (ISO, already correct)
]


def _parse_date(raw: str) -> str | None:
    """Return ISO 8601 date string or None if unparseable."""
    if not raw or pd.isna(raw):
        return None
    s = str(raw).strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    logger.debug("Unparseable date value: %r", s)
    return None


_CURRENCY_SYMBOL_RE = re.compile(r"[^\d.]")


def _parse_amount(raw) -> float | None:
    """Strip any non-numeric prefix/suffix (e.g. '$') and return float or None."""
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    s = str(raw).strip()
    cleaned = _CURRENCY_SYMBOL_RE.sub("", s)
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        logger.debug("Unparseable amount value: %r", s)
        return None


# ── Column name normalisation map (raw CSV → internal name) ──────────────────
_COL_RENAME = {
    "date": "txn_date",
}


class TransactionCleaner:
    """Stateless, idempotent CSV cleaner."""

    def clean(self, df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
        """
        Clean a raw transaction DataFrame.

        Returns
        -------
        (cleaned_df, stats)
            cleaned_df : normalised DataFrame ready for anomaly detection
            stats      : dict with total_rows, cleaned_rows, duplicate_rows
        """
        total_rows = len(df)
        df = df.copy()

        # Normalise column names to lowercase + strip whitespace
        df.columns = [c.strip().lower() for c in df.columns]
        df = df.rename(columns=_COL_RENAME)

        # ── 1. Normalise dates → ISO 8601 ─────────────────────────────────
        if "txn_date" in df.columns:
            df["txn_date"] = df["txn_date"].apply(_parse_date)

        # ── 2. Strip currency symbols from amount → numeric ────────────────
        if "amount" in df.columns:
            df["amount"] = df["amount"].apply(_parse_amount)

        # ── 3. Uppercase currency and status ──────────────────────────────
        for col in ("currency", "status"):
            if col in df.columns:
                df[col] = df[col].apply(
                    lambda v: str(v).strip().upper() if v and not pd.isna(v) else v
                )

        # ── 4. Fill missing / blank categories ────────────────────────────
        if "category" in df.columns:
            df["category"] = df["category"].apply(
                lambda v: "Uncategorised"
                if (v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() == "")
                else str(v).strip()
            )

        # ── 5. Drop exact duplicate rows (keep first occurrence) ──────────
        before_dedup = len(df)
        df = df.drop_duplicates()
        duplicate_rows = before_dedup - len(df)

        if duplicate_rows:
            logger.info("Removed %d exact duplicate rows", duplicate_rows)

        # ── 6. Drop rows with null amount (cannot be processed) ───────────
        df = df.dropna(subset=["amount"])

        cleaned_rows = len(df)

        stats = {
            "total_rows": total_rows,
            "cleaned_rows": cleaned_rows,
            "duplicate_rows": duplicate_rows,
        }

        logger.info(
            "Cleaning complete: %d raw → %d clean (%d dupes removed)",
            total_rows, cleaned_rows, duplicate_rows,
        )

        return df.reset_index(drop=True), stats
