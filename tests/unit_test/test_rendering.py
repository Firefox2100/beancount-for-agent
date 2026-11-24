from datetime import date
from decimal import Decimal

from beancount import loader

from beancount_mcp.ledger.edit import _render_directive, _render_transaction, _span
from beancount_mcp.models import BalanceAssertion, TransactionInput


def test_transaction_roundtrips_through_beancount():
    transaction = TransactionInput.model_validate(
        {
            "date": "2026-01-02",
            "payee": 'Caf"e',
            "narration": "back\\slash",
            "tags": ["b", "a"],
            "postings": [
                {"account": "Assets:Bank", "units": {"number": "-12.5", "currency": "USD"}},
                {"account": "Expenses:Food"},
            ],
            "meta": {"note": 'say "hi"'},
        }
    )
    text = _render_transaction(transaction, "abc")
    ledger = "2026-01-01 open Assets:Bank\n2026-01-01 open Expenses:Food\n" + text
    entries, errors, _ = loader.load_string(ledger)
    parsed = entries[-1]
    assert errors == []
    assert (parsed.payee, parsed.narration) == ('Caf"e', "back\\slash")
    assert parsed.meta["id"] == "abc" and parsed.meta["note"] == 'say "hi"'
    assert parsed.tags == {"a", "b"}


def test_directive_has_id():
    text = _render_directive(
        BalanceAssertion(date=date(2026, 1, 1), account="Assets:Bank", amount={"number": "1", "currency": "USD"}),
        "xyz",
    )
    assert text.startswith("2026-01-01 balance Assets:Bank") and 'id: "xyz"' in text


def test_span_covers_indented_lines_and_one_blank():
    lines = ["a\n", "2026-01-01 * \"x\"\n", "  id: \"1\"\n", "  A  1 USD\n", "\n", "next\n"]
    assert _span(lines, 2) == (1, 5)


def test_span_at_end_of_file():
    lines = ["2026-01-01 * \"x\"\n", "  A  1 USD\n"]
    assert _span(lines, 1) == (0, 2)


def test_priced_whole_amounts_still_balance():
    transaction = TransactionInput.model_validate(
        {
            "date": "2026-01-02",
            "postings": [
                {
                    "account": "Assets:A",
                    "units": {"number": "3", "currency": "GBP"},
                    "price": {"number": str(Decimal(4) / Decimal(3)), "currency": "USD"},
                },
                {"account": "Assets:B", "units": {"number": "-4", "currency": "USD"}},
            ],
        }
    )
    text = _render_transaction(transaction, "abc")
    _, errors, _ = loader.load_string("2026-01-01 open Assets:A\n2026-01-01 open Assets:B\n" + text)
    assert errors == []
