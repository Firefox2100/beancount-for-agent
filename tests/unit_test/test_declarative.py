import datetime as dt
from decimal import Decimal

import pytest
from pydantic import ValidationError

from beancount_mcp.ledger.errors import RecipeError
from beancount_mcp.models import AccountInfo, AccountProfile
from beancount_mcp.models.declarative import RecipeDefinition
from beancount_mcp.recipes import declarative
from beancount_mcp.recipes.base import RecipeContext

OPEN = dt.date(2025, 1, 1)


def definition(**overrides) -> RecipeDefinition:
    values = dict(
        title="Bank fee", description="A fee the bank took.", kinds=["checking"],
        params={"fee": {"type": "amount", "description": "What was taken."}},
        narration="Bank fee", postings=[{"account": "@self", "amount": "-$fee"}, {"account": "Expenses:Fees", "amount": "$fee"}],
    )
    return RecipeDefinition.model_validate({**values, **overrides})


def context(account="Assets:Checking", currencies=("GBP",), extra=()) -> RecipeContext:
    names = {account: AccountInfo(name=account, open_date=OPEN, currencies=list(currencies), type="checking")}
    for name, ccy in (("Expenses:Fees", ["GBP"]), ("Assets:Savings", ["GBP"]), *extra):
        names[name] = AccountInfo(name=name, open_date=OPEN, currencies=list(ccy))
    return RecipeContext(account=account, kind="checking", profile=AccountProfile(), accounts=names, balance=lambda _name: {})


def perform(item: RecipeDefinition, params: dict, ctx: RecipeContext | None = None):
    recipe = declarative.build("fee", item)
    return recipe.compile(recipe.params.model_validate(params), ctx or context())


def lines(operation):
    return [(p.account, str(p.units.number) + " " + p.units.currency if p.units else None) for p in operation.transaction.postings]


def test_a_definition_becomes_a_recipe_with_a_normal_parameter_schema():
    recipe = declarative.build("bank_fee", definition())
    schema = recipe.params.model_json_schema()
    assert (recipe.id, recipe.kinds) == ("bank_fee", frozenset({"checking"}))
    assert schema["required"] == ["fee"] and schema["properties"]["fee"]["description"] == "What was taken."
    assert "date" in schema["properties"] and "date" not in schema.get("required", [])


def test_postings_copy_and_negate_the_amount_and_the_sign_the_agent_writes_is_ignored():
    for given in ("5.30", "-5.30", "5.30 GBP", 5.3):
        first, second = perform(definition(), {"fee": given}).transaction.postings
        assert (first.account, first.units.number, first.units.currency) == ("Assets:Checking", Decimal("-5.3"), "GBP")
        assert (second.account, second.units.number) == ("Expenses:Fees", Decimal("5.3"))


def test_a_formula_is_worked_out_here_like_everywhere_else():
    operation = perform(definition(), {"fee": "2.10 + 3.20 GBP"})
    assert lines(operation)[1] == ("Expenses:Fees", "5.30 GBP")


def test_the_rest_of_the_entry_is_left_to_balance():
    item = definition(postings=[{"account": "@self", "amount": "-$fee"}, {"account": "Expenses:Fees"}])
    assert lines(perform(item, {"fee": "5 GBP"})) == [("Assets:Checking", "-5 GBP"), ("Expenses:Fees", None)]


def test_account_parameters_are_checked_against_the_types_they_may_be():
    item = definition(
        params={"to": {"type": "account", "under": ["Assets"]}, "amount": {"type": "amount"}},
        postings=[{"account": "@self", "amount": "-$amount"}, {"account": "$to", "amount": "$amount"}],
    )
    assert lines(perform(item, {"to": "Assets:Savings", "amount": "20 GBP"})) == [("Assets:Checking", "-20 GBP"), ("Assets:Savings", "20 GBP")]
    with pytest.raises(RecipeError, match="must be an account under Assets"):
        perform(item, {"to": "Expenses:Fees", "amount": "20 GBP"})
    with pytest.raises(RecipeError, match="is not open"):
        perform(item, {"to": "Assets:Nowhere", "amount": "20 GBP"})


def test_text_and_tags_fill_the_payee_narration_and_tags():
    item = definition(
        params={"fee": {"type": "amount"}, "why": {"type": "text", "required": False, "default": "monthly charge"}, "labels": {"type": "tags", "required": False}},
        payee="Barclays", narration="Fee: {why}, {fee}", tags=["bank"],
    )
    operation = perform(item, {"fee": "5 GBP", "labels": ["review"]})
    transaction = operation.transaction
    assert (transaction.payee, transaction.narration) == ("Barclays", "Fee: monthly charge, 5 GBP")
    assert transaction.tags == ["bank", "review"] and transaction.date == dt.date.today()


def test_a_bare_number_needs_the_currency_when_the_account_holds_several():
    two = context(currencies=("GBP", "USD"))
    with pytest.raises(RecipeError, match="give the currency"):
        perform(definition(), {"fee": "5"}, two)
    assert lines(perform(definition(), {"fee": "5 USD"}, two))[0][1] == "-5 USD"


@pytest.mark.parametrize("change,fragment", [
    ({"postings": [{"account": "@self", "amount": "-$fee * 2"}, {"account": "Expenses:Fees"}]}, "must be \\$name or -\\$name"),
    ({"postings": [{"account": "@self"}, {"account": "Expenses:Fees"}]}, "at most one posting"),
    ({"postings": [{"account": "@self", "amount": "-$nope"}, {"account": "Expenses:Fees", "amount": "$fee"}]}, "not an amount parameter"),
    ({"postings": [{"account": "$where", "amount": "-$fee"}, {"account": "@self", "amount": "$fee"}]}, "not an account parameter"),
    ({"postings": [{"account": "Fees", "amount": "-$fee"}, {"account": "@self", "amount": "$fee"}]}, "full account name"),
    ({"narration": "Fee {missing}"}, "narration uses \\{missing\\}"),
    ({"params": {"fee": {"type": "amount"}, "self": {"type": "text"}}}, "self is reserved"),
    ({"params": {"fee": {"type": "amount"}, "date": {"type": "text"}}}, "must be a date parameter"),
    ({"params": {"fee": {"type": "amount"}, "extra": {"type": "account"}}}, "required but never used"),
    ({"postings": [{"account": "@self", "amount": "-$fee"}]}, "at least 2"),
    ({"kinds": []}, "at least 1"),
])
def test_a_definition_that_cannot_work_is_refused_with_the_reason(change, fragment):
    with pytest.raises(ValidationError, match=fragment):
        definition(**change)


def test_context_checks_refuse_a_clash_with_a_built_in_and_an_optional_parameter_a_posting_needs():
    assert declarative.problems(definition(), {"spend"}, "bank_fee") == []
    assert "built-in recipe" in declarative.problems(definition(), {"spend"}, "spend")[0]
    optional = definition(params={"fee": {"type": "amount", "required": False}})
    assert "optional but a posting needs it" in declarative.problems(optional, set(), "bank_fee")[0]
    defaulted = definition(params={"fee": {"type": "amount", "required": False, "default": "2.50 GBP"}})
    assert declarative.problems(defaulted, set(), "bank_fee") == []
    assert lines(perform(defaulted, {}))[1] == ("Expenses:Fees", "2.50 GBP")


def test_a_required_parameter_with_a_default_is_a_mistake_and_under_is_for_accounts_only():
    with pytest.raises(ValidationError, match="not required"):
        definition(params={"fee": {"type": "amount", "default": "1 GBP"}})
    with pytest.raises(ValidationError, match="only applies to an account"):
        definition(params={"fee": {"type": "amount", "under": ["Assets"]}})


def test_the_summary_reads_in_plain_lines():
    text = "\n".join(declarative.summary(definition(payee="Barclays")))
    assert "for: checking" in text and "parameter fee (amount; required)" in text
    assert "posting: @self  -$fee" in text and "posting: Expenses:Fees  $fee" in text and "payee: Barclays" in text
    assert Decimal  # keep the import honest
