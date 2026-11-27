import pytest

from beancount_mcp.ui.present import grouped, held


@pytest.mark.parametrize("value,expected", [
    ("0", "0"), ("999", "999"), ("1000", "1,000"), ("123456.78", "123,456.78"), ("-1234567.8", "-1,234,567.8"),
    ("1234567890123456.789", "1,234,567,890,123,456.789"), ("12.5", "12.5"), ("abc", "abc"), ("", ""),
])
def test_numbers_are_grouped_by_thousands_without_touching_the_decimals(value, expected):
    assert grouped(value) == expected


def test_held_amounts_are_grouped_per_currency():
    assert held({"GBP": "48469.17", "USD": "30"}) == "48,469.17 GBP · 30 USD" and held({}) == "—"
