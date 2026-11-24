from typing import Any


def lunch(day: str = "2026-02-03", amount: str = "12.50", **overrides: Any) -> dict:
    body = {
        "date": day,
        "payee": "Cafe",
        "narration": "Lunch",
        "tags": ["trip"],
        "postings": [
            {"account": "Assets:Bank", "units": {"number": f"-{amount}", "currency": "USD"}},
            {"account": "Expenses:Food"},
        ],
    }
    body.update(overrides)
    return body
