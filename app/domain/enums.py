from enum import StrEnum


class JobStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    LLM_FAILED = "llm_failed"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# Categories that the LLM must choose from
VALID_CATEGORIES: list[str] = [
    "Food",
    "Shopping",
    "Travel",
    "Transport",
    "Utilities",
    "Entertainment",
    "Cash Withdrawal",
    "Uncategorised",
]

# Merchants that are exclusively INR (flagged if any other currency is used)
INR_ONLY_MERCHANTS: frozenset[str] = frozenset({
    "swiggy",
    "zomato",
    "jio recharge",
    "ola",
    "irctc",
    "hdfc atm",
    "bookmyshow",
})

# Merchants where non-INR is suspicious but could be legitimate
INR_PREFERRED_MERCHANTS: frozenset[str] = frozenset({
    "makemytrip",
    "amazon",
    "flipkart",
})
