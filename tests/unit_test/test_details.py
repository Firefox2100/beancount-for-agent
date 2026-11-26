import pytest
from pydantic import ValidationError

from beancount_mcp.models.details import AccountDetails, for_agent, from_meta, to_meta


def test_numbers_are_normalised():
    details = AccountDetails(
        sort_code="201234", account_number="1234 5678", iban="gb29 nwbk 6016 1331 9268 19",
        swift_bic="barcgb22", card_number="4929 1234-5678 9012", card_expiry="8/2028", routing_number="021000021",
    )
    assert details.sort_code == "20-12-34"
    assert details.account_number == "12345678"
    assert details.iban == "GB29NWBK60161331926819"
    assert details.swift_bic == "BARCGB22"
    assert details.card_number == "4929123456789012"
    assert details.card_expiry == "08/28"


@pytest.mark.parametrize("field,value", [
    ("sort_code", "12345"), ("iban", "1234"), ("swift_bic", "ABC"), ("card_number", "1234"),
    ("card_expiry", "13/28"), ("routing_number", "12345678"), ("bank_name", "line\nbreak"),
])
def test_bad_values_are_refused(field, value):
    with pytest.raises(ValidationError):
        AccountDetails(**{field: value})


def test_there_is_no_place_for_secrets():
    for name in ("cvv", "cvc", "pin", "password"):
        with pytest.raises(ValidationError):
            AccountDetails(**{name: "123"})


def test_meta_round_trip_uses_hyphenated_keys():
    meta = to_meta(AccountDetails(bank_name="Barclays", sort_code="201234"))
    assert meta == {"bank-name": "Barclays", "sort-code": "20-12-34"}
    assert from_meta({**meta, "type": "checking"}) == {"bank_name": "Barclays", "sort_code": "20-12-34"}


def test_agents_see_sensitive_fields_masked():
    shown = for_agent({
        "bank_name": "Barclays", "swift_bic": "BARCGB22", "sort_code": "20-12-34",
        "account_number": "12345678", "card_number": "4929123456789012", "card_expiry": "08/28",
    })
    assert shown["bank_name"] == "Barclays" and shown["swift_bic"] == "BARCGB22"
    assert shown["account_number"] == "••••5678"
    assert shown["card_number"] == "••••9012"
    assert shown["sort_code"] == "••••34"
    assert shown["card_expiry"] == "••/••"
