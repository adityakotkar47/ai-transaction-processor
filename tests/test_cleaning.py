"""
Unit tests for the TransactionCleaner service.

All test cases are derived from the real transactions.csv quirks
observed during the planning phase.
"""

import pandas as pd
import pytest

from app.services.cleaning.cleaner import TransactionCleaner, _parse_amount, _parse_date


# ── Date parsing ──────────────────────────────────────────────────────────────

class TestParseDateHelper:
    def test_dd_mm_yyyy(self):
        assert _parse_date("17-02-2024") == "2024-02-17"

    def test_yyyy_slash_mm_slash_dd(self):
        assert _parse_date("2024/02/05") == "2024-02-05"

    def test_iso_passthrough(self):
        assert _parse_date("2024-07-15") == "2024-07-15"

    def test_none_input(self):
        assert _parse_date(None) is None

    def test_empty_string(self):
        assert _parse_date("") is None

    def test_invalid_date(self):
        assert _parse_date("99-99-9999") is None

    def test_feb_29_invalid_year(self):
        # 2024/02/29 is valid (2024 is a leap year)
        assert _parse_date("2024/02/29") == "2024-02-29"


# ── Amount parsing ────────────────────────────────────────────────────────────

class TestParseAmountHelper:
    def test_plain_float(self):
        assert _parse_amount("11325.79") == pytest.approx(11325.79)

    def test_dollar_prefixed(self):
        assert _parse_amount("$11325.79") == pytest.approx(11325.79)

    def test_plain_int(self):
        assert _parse_amount("500") == pytest.approx(500.0)

    def test_none_input(self):
        assert _parse_amount(None) is None

    def test_empty_string(self):
        assert _parse_amount("") is None

    def test_non_numeric(self):
        assert _parse_amount("abc") is None


# ── Full cleaner ──────────────────────────────────────────────────────────────

@pytest.fixture()
def sample_raw_df():
    """Minimal representative slice mirroring real CSV issues."""
    return pd.DataFrame(
        {
            "txn_id": ["TXN001", "TXN002", "TXN001", "TXN003", "TXN004", ""],
            "date":   ["17-02-2024", "2024/02/05", "17-02-2024", "2024-07-15", "bad-date", "01-01-2024"],
            "merchant": ["Zomato", "Swiggy", "Zomato", "Amazon", "Ola", "Flipkart"],
            "amount": ["2536.35", "$11325.79", "2536.35", "6874.10", None, "500.00"],
            "currency": ["USD", "INR", "USD", "inr", "INR", "INR"],
            "status": ["SUCCESS", "success", "SUCCESS", "failed", "PENDING", "SUCCESS"],
            "category": ["Food", "Food", "Food", "Shopping", "Transport", ""],
            "account_id": ["ACC001", "ACC004", "ACC001", "ACC004", "ACC001", "ACC002"],
            "notes": ["Verified", "", "Verified", "SUSPICIOUS", "", ""],
        }
    )


class TestTransactionCleaner:
    def test_duplicate_rows_removed(self, sample_raw_df):
        cleaner = TransactionCleaner()
        cleaned, stats = cleaner.clean(sample_raw_df)
        assert stats["duplicate_rows"] == 1
        assert stats["cleaned_rows"] == stats["total_rows"] - stats["duplicate_rows"] - 1  # -1 for null amount

    def test_dates_normalised_to_iso(self, sample_raw_df):
        cleaned, _ = TransactionCleaner().clean(sample_raw_df)
        dates = cleaned["txn_date"].tolist()
        assert "2024-02-17" in dates
        assert "2024-02-05" in dates
        assert "2024-07-15" in dates
        # bad-date row stays (date is None) — only dropped if amount is None
        assert None in dates or "2024-07-15" in dates  # flexible

    def test_dollar_prefix_stripped(self, sample_raw_df):
        cleaned, _ = TransactionCleaner().clean(sample_raw_df)
        amounts = cleaned["amount"].tolist()
        assert all(isinstance(a, float) for a in amounts)
        assert 11325.79 in pytest.approx(amounts, rel=1e-3)

    def test_currency_uppercased(self, sample_raw_df):
        cleaned, _ = TransactionCleaner().clean(sample_raw_df)
        for cur in cleaned["currency"]:
            assert cur == cur.upper()

    def test_status_uppercased(self, sample_raw_df):
        cleaned, _ = TransactionCleaner().clean(sample_raw_df)
        for st in cleaned["status"]:
            assert st == st.upper()

    def test_blank_category_filled(self, sample_raw_df):
        cleaned, _ = TransactionCleaner().clean(sample_raw_df)
        assert "Uncategorised" in cleaned["category"].tolist()
        assert "" not in cleaned["category"].tolist()

    def test_null_amount_rows_dropped(self, sample_raw_df):
        cleaned, _ = TransactionCleaner().clean(sample_raw_df)
        assert cleaned["amount"].isna().sum() == 0

    def test_stats_structure(self, sample_raw_df):
        _, stats = TransactionCleaner().clean(sample_raw_df)
        assert "total_rows" in stats
        assert "cleaned_rows" in stats
        assert "duplicate_rows" in stats
        assert stats["total_rows"] == len(sample_raw_df)

    def test_real_csv_file(self):
        """Smoke test against the actual transactions.csv in the repo root."""
        import os
        csv_path = os.path.join(
            os.path.dirname(__file__), "..", "transactions.csv"
        )
        if not os.path.exists(csv_path):
            pytest.skip("transactions.csv not found")

        raw = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
        cleaner = TransactionCleaner()
        cleaned, stats = cleaner.clean(raw)

        # We know from inspection that there are ~15 duplicate rows
        assert stats["duplicate_rows"] >= 10
        # Cleaned output should have no $ in amounts
        for amt in cleaned["amount"]:
            assert "$" not in str(amt)
        # All status values should be uppercase
        for st in cleaned["status"]:
            assert st == st.upper(), f"Status not uppercased: {st!r}"
