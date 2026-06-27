"""
Anomaly detection service.

Two independent rules:
1. Statistical outlier: amount > 3× account median
2. Currency mismatch: non-INR on INR-only merchants

Rules can fire simultaneously (reasons concatenated with "; ").
"""

import logging

import pandas as pd

from app.domain.enums import INR_ONLY_MERCHANTS, INR_PREFERRED_MERCHANTS

logger = logging.getLogger(__name__)


class AnomalyDetector:
    """Stateless anomaly annotator.  Adds `is_anomaly` and `anomaly_reason` columns."""

    def __init__(self, outlier_multiplier: float = 3.0) -> None:
        self.outlier_multiplier = outlier_multiplier

    def detect(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Annotate a cleaned DataFrame with anomaly flags.

        Parameters
        ----------
        df : cleaned output from TransactionCleaner

        Returns
        -------
        Annotated DataFrame with two new columns:
            is_anomaly     : bool
            anomaly_reason : str  (empty string when not an anomaly)
        """
        df = df.copy()
        df["is_anomaly"] = False
        df["anomaly_reason"] = ""

        df = self._flag_statistical_outliers(df)
        df = self._flag_currency_mismatches(df)

        total = int(df["is_anomaly"].sum())
        logger.info("Anomaly detection complete: %d/%d transactions flagged", total, len(df))
        return df

    # ── Rule 1: Statistical outlier ───────────────────────────────────────────

    def _flag_statistical_outliers(self, df: pd.DataFrame) -> pd.DataFrame:
        """Flag rows where amount > outlier_multiplier × account median."""
        if "account_id" not in df.columns or "amount" not in df.columns:
            return df

        medians: pd.Series = df.groupby("account_id")["amount"].median()

        for idx, row in df.iterrows():
            acc = row.get("account_id")
            amt = row.get("amount")
            if acc is None or amt is None or pd.isna(amt):
                continue
            median = medians.get(acc)
            if median is None or median <= 0:
                continue
            if float(amt) > self.outlier_multiplier * float(median):
                reason = (
                    f"Statistical outlier: amount {float(amt):,.2f} is "
                    f">{self.outlier_multiplier}× account {acc} median {float(median):,.2f}"
                )
                df.at[idx, "is_anomaly"] = True
                df.at[idx, "anomaly_reason"] = self._append_reason(
                    df.at[idx, "anomaly_reason"], reason
                )

        return df

    # ── Rule 2: Currency / merchant mismatch ─────────────────────────────────

    def _flag_currency_mismatches(self, df: pd.DataFrame) -> pd.DataFrame:
        """Flag rows where a domestic merchant is charged in a foreign currency."""
        if "merchant" not in df.columns or "currency" not in df.columns:
            return df

        for idx, row in df.iterrows():
            merchant_raw = row.get("merchant")
            currency = str(row.get("currency", "")).strip().upper()
            if not merchant_raw:
                continue
            merchant = str(merchant_raw).strip().lower()

            if merchant in INR_ONLY_MERCHANTS and currency != "INR":
                reason = (
                    f"Currency mismatch: '{merchant_raw}' only accepts INR, "
                    f"got {currency}"
                )
                df.at[idx, "is_anomaly"] = True
                df.at[idx, "anomaly_reason"] = self._append_reason(
                    df.at[idx, "anomaly_reason"], reason
                )

            elif merchant in INR_PREFERRED_MERCHANTS and currency not in ("INR", ""):
                reason = (
                    f"Suspicious currency: '{merchant_raw}' typically charges INR, "
                    f"got {currency}"
                )
                df.at[idx, "is_anomaly"] = True
                df.at[idx, "anomaly_reason"] = self._append_reason(
                    df.at[idx, "anomaly_reason"], reason
                )

        return df

    # ── Internal helper ───────────────────────────────────────────────────────

    @staticmethod
    def _append_reason(existing: str, new_reason: str) -> str:
        if existing:
            return f"{existing}; {new_reason}"
        return new_reason
