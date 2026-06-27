"""
Unit tests for the AnomalyDetector service.
"""

import pandas as pd
import pytest

from app.services.anomaly.detector import AnomalyDetector


@pytest.fixture()
def base_df():
    """A minimal clean DataFrame (post-cleaner) for anomaly tests."""
    return pd.DataFrame(
        {
            "txn_id":     ["T1",   "T2",   "T3",   "T4",   "T5",   "T6"],
            "txn_date":   ["2024-01-01"] * 6,
            "merchant":   ["Swiggy", "Zomato", "Amazon", "Ola",   "IRCTC", "Flipkart"],
            "amount":     [250.0,   300.0,   500.0,   400.0,   600.0,   10000.0],
            "currency":   ["INR",   "USD",   "USD",   "INR",   "INR",   "INR"],
            "status":     ["SUCCESS"] * 6,
            "category":   ["Food",  "Food",  "Shopping", "Transport", "Travel", "Shopping"],
            "account_id": ["ACC1",  "ACC1",  "ACC1",  "ACC1",  "ACC1",  "ACC1"],
            "notes":      [""] * 6,
        }
    )


class TestCurrencyMismatch:
    def test_inr_only_merchant_with_usd_is_flagged(self, base_df):
        detector = AnomalyDetector()
        result = detector.detect(base_df)
        # Zomato + USD → flag
        zomato_row = result[result["merchant"] == "Zomato"]
        assert zomato_row["is_anomaly"].iloc[0] is True
        assert "Currency mismatch" in zomato_row["anomaly_reason"].iloc[0]

    def test_inr_only_merchant_with_inr_not_flagged(self, base_df):
        detector = AnomalyDetector()
        result = detector.detect(base_df)
        swiggy_row = result[result["merchant"] == "Swiggy"]
        # Swiggy + INR → no currency mismatch flag
        # (may still be flagged for statistical outlier separately)
        assert "Currency mismatch" not in swiggy_row["anomaly_reason"].iloc[0]

    def test_inr_preferred_merchant_with_usd_is_suspicious(self, base_df):
        detector = AnomalyDetector()
        result = detector.detect(base_df)
        amazon_row = result[result["merchant"] == "Amazon"]
        assert amazon_row["is_anomaly"].iloc[0] is True
        assert "Suspicious currency" in amazon_row["anomaly_reason"].iloc[0]


class TestStatisticalOutlier:
    def test_large_amount_flagged(self):
        df = pd.DataFrame(
            {
                "txn_id":     [f"T{i}" for i in range(6)],
                "txn_date":   ["2024-01-01"] * 6,
                "merchant":   ["Amazon"] * 6,
                "amount":     [1000.0, 1100.0, 900.0, 1050.0, 950.0, 50000.0],  # last is outlier
                "currency":   ["INR"] * 6,
                "status":     ["SUCCESS"] * 6,
                "category":   ["Shopping"] * 6,
                "account_id": ["ACC1"] * 6,
                "notes":      [""] * 6,
            }
        )
        detector = AnomalyDetector(outlier_multiplier=3.0)
        result = detector.detect(df)
        # median ≈ 1000; 50000 > 3×1000
        outlier_row = result[result["amount"] == 50000.0]
        assert outlier_row["is_anomaly"].iloc[0] is True
        assert "Statistical outlier" in outlier_row["anomaly_reason"].iloc[0]

    def test_normal_amount_not_flagged(self):
        df = pd.DataFrame(
            {
                "txn_id":     ["T1", "T2", "T3"],
                "txn_date":   ["2024-01-01"] * 3,
                "merchant":   ["Amazon"] * 3,
                "amount":     [1000.0, 1100.0, 900.0],
                "currency":   ["INR"] * 3,
                "status":     ["SUCCESS"] * 3,
                "category":   ["Shopping"] * 3,
                "account_id": ["ACC1"] * 3,
                "notes":      [""] * 3,
            }
        )
        result = AnomalyDetector().detect(df)
        assert result["is_anomaly"].sum() == 0

    def test_dual_reason_concatenated(self):
        """A transaction can be both a statistical outlier AND a currency mismatch."""
        df = pd.DataFrame(
            {
                "txn_id":     ["T1", "T2", "T3"],
                "txn_date":   ["2024-01-01"] * 3,
                "merchant":   ["Zomato", "Zomato", "Zomato"],
                "amount":     [300.0, 350.0, 50000.0],  # last is outlier
                "currency":   ["INR", "INR", "USD"],     # last is also mismatch
                "status":     ["SUCCESS"] * 3,
                "category":   ["Food"] * 3,
                "account_id": ["ACC1"] * 3,
                "notes":      [""] * 3,
            }
        )
        result = AnomalyDetector().detect(df)
        last_row = result[result["txn_id"] == "T3"]
        reason = last_row["anomaly_reason"].iloc[0]
        assert "Statistical outlier" in reason
        assert "Currency mismatch" in reason
        assert ";" in reason  # reasons are concatenated

    def test_real_csv_txn2000_series_flagged(self):
        """TXN2000-TXN2004 in the real CSV are ~91k-193k vs typical 1k-15k per account."""
        import os
        csv_path = os.path.join(
            os.path.dirname(__file__), "..", "transactions.csv"
        )
        if not os.path.exists(csv_path):
            pytest.skip("transactions.csv not found")

        from app.services.cleaning.cleaner import TransactionCleaner
        raw = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
        cleaned, _ = TransactionCleaner().clean(raw)
        result = AnomalyDetector().detect(cleaned)

        # TXN200x rows should all be flagged as outliers
        high_amount_rows = result[result["amount"] > 50000]
        assert len(high_amount_rows) > 0
        for _, row in high_amount_rows.iterrows():
            assert row["is_anomaly"] is True or bool(row["is_anomaly"])
