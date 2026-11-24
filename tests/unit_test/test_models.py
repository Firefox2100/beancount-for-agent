import pytest
from pydantic import ValidationError

from beancount_mcp.models import CreateLedgerRequest, Operation, TransactionInput
from pydantic import TypeAdapter

POSTINGS = [
    {"account": "Assets:Bank", "units": {"number": "-1", "currency": "USD"}},
    {"account": "Expenses:Food"},
]


def transaction(**overrides):
    return TransactionInput.model_validate({"date": "2026-01-01", "postings": POSTINGS, **overrides})


@pytest.mark.parametrize("narration", ["a\nb", "a\rb", "a\x00b", "a\x7fb"])
def test_control_characters_rejected(narration):
    with pytest.raises(ValidationError):
        transaction(narration=narration)


@pytest.mark.parametrize("account", ["assets:bank", "Assets", "Assets:", "Cash:Bank", 'Assets:"x"'])
def test_bad_account_names_rejected(account):
    with pytest.raises(ValidationError):
        transaction(postings=[{"account": account}, POSTINGS[1]])


@pytest.mark.parametrize("currency", ["usd", "US D", "", "U" * 30])
def test_bad_currencies_rejected(currency):
    with pytest.raises(ValidationError):
        transaction(postings=[{"account": "Assets:A", "units": {"number": "1", "currency": currency}}, POSTINGS[1]])


def test_reserved_meta_and_bad_keys_rejected():
    with pytest.raises(ValidationError):
        transaction(meta={"id": "x"})
    with pytest.raises(ValidationError):
        transaction(meta={"Bad Key": "x"})


def test_needs_two_postings():
    with pytest.raises(ValidationError):
        transaction(postings=POSTINGS[:1])


def test_non_finite_numbers_rejected():
    with pytest.raises(ValidationError):
        transaction(postings=[{"account": "Assets:A", "units": {"number": "NaN", "currency": "USD"}}, POSTINGS[1]])


def test_ledger_id_pattern():
    CreateLedgerRequest(id="personal-2026")
    for bad in ("", "../x", "Upper", "a/b", "-a", "a" * 65):
        with pytest.raises(ValidationError):
            CreateLedgerRequest(id=bad)


def test_operation_union_dispatches_on_kind():
    adapter = TypeAdapter(Operation)
    operation = adapter.validate_python({"kind": "delete_transaction", "id": "abc"})
    assert operation.id == "abc"
    with pytest.raises(ValidationError):
        adapter.validate_python({"kind": "nope"})
