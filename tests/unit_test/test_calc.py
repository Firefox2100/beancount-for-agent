from decimal import Decimal

import pytest

from beancount_mcp.calc import MAX_LENGTH, CalcError, evaluate


@pytest.mark.parametrize("text,expected", [
    ("18.65 + 6.60 + 7.40", "32.65"),
    ("48 / 3", "16.00"),
    ("2 + 3 * 4", "14.00"),
    ("(2 + 3) * 4", "20.00"),
    ("(100 - 15) / 2", "42.50"),
    ("-5 + 8", "3.00"),
    ("10 - -2", "12.00"),
    ("1,200.50 + 0.25", "1200.75"),
    ("42 * 1.15", "48.30"),
    ("0.1 + 0.2", "0.30"),
    ("=18.65+6.60", "25.25"),
    ("12 × 3", "36.00"),
    ("9 ÷ 3", "3.00"),
    ("10 − 4", "6.00"),
    (".5 + .25", "0.75"),
])
def test_formulas_are_exact(text, expected):
    assert evaluate(text).value == Decimal(expected)


def test_a_plain_number_is_returned_as_written():
    for text in ("12.5", "7", "1,200", ".5", "-40", "+3.5"):
        result = evaluate(text)
        assert not result.is_formula
        assert result.value == Decimal(text.replace(",", ""))
    assert str(evaluate("-40").value) == "-40"
    assert evaluate("(40)").is_formula and evaluate("40 + 0").is_formula
    assert str(evaluate("12.50").value) == "12.50"


def test_results_keep_the_most_places_written_and_at_least_two():
    assert str(evaluate("1 / 3").value) == "0.33"
    assert str(evaluate("1 / 3", minimum_places=8).value) == "0.33333333"
    assert str(evaluate("0.123 + 0.0004").value) == "0.1234"
    assert str(evaluate("100 / 8").value) == "12.50"


def test_rounding_is_half_even_on_the_exact_result():
    assert evaluate("0.125 + 0").value == Decimal("0.125")
    assert evaluate("2.675 * 1", minimum_places=2).value == Decimal("2.675")
    assert evaluate("1 / 8", minimum_places=2).value == Decimal("0.12")
    assert evaluate("3 / 8", minimum_places=2).value == Decimal("0.38")


def test_the_exact_value_is_kept_beside_the_rounded_one():
    result = evaluate("1 / 3")
    assert result.value == Decimal("0.33") and result.exact > Decimal("0.3333333333")


@pytest.mark.parametrize("text,fragment", [
    ("10 / 0", "division by zero"),
    ("10 / (5 - 5)", "division by zero"),
    ("2 ** 3", "number was expected"),
    ("2 3", "unexpected"),
    ("2(3)", "unexpected"),
    ("(1 + 2", "never closed"),
    ("1 + 2)", "unexpected"),
    ("1 +", "ends where a number"),
    ("", "nothing to calculate"),
    ("   ", "nothing to calculate"),
    ("1e5", 'cannot read "e"'),
    ("10%", 'cannot read "%"'),
    ("1,20", 'cannot read ","'),
    ("abc", 'cannot read "a"'),
    ("sqrt(4)", 'cannot read "s"'),
    ("__import__('os')", 'cannot read "_"'),
    ("1; 2", 'cannot read ";"'),
    ("999999999999999 * 1000", "too large"),
])
def test_what_is_not_arithmetic_is_refused_and_says_what_to_send(text, fragment):
    with pytest.raises(CalcError, match=fragment):
        evaluate(text)


def test_length_and_nesting_are_limited():
    with pytest.raises(CalcError, match="too long"):
        evaluate("1+" * MAX_LENGTH)
    with pytest.raises(CalcError, match="too deeply nested"):
        evaluate("-" * 40 + "1")
    assert evaluate("(" * 10 + "1" + ")" * 10).value == Decimal("1")


def test_the_error_is_a_value_error_so_validation_reports_it():
    assert issubclass(CalcError, ValueError)
