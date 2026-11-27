import datetime as dt
from decimal import Decimal

from beancount import loader

from beancount_mcp.ledger.checks import checks
from beancount_mcp.models import AccountInfo, LedgerError

D = dt.date.fromisoformat
TODAY = D("2026-06-01")


def info(name, kind=None, opened="2025-01-01"):
    return AccountInfo(name=name, open_date=D(opened), type=kind)


def run(text, accounts, balances, errors=(), stale=45):
    entries = loader.load_string(text)[0]
    return checks(entries, accounts, balances, list(errors), TODAY, stale)


def kinds(found):
    return sorted(f.kind for f in found)


def test_a_quiet_ledger_has_no_findings():
    text = '2026-05-01 open Assets:Bank\n2026-05-20 balance Assets:Bank 100 GBP\n2026-05-01 open Equity:Open\n2026-05-02 * "x"\n  Assets:Bank 100 GBP\n  Equity:Open -100 GBP\n'
    assert run(text, [info("Assets:Bank", "checking")], {"Assets:Bank": {"GBP": Decimal(100)}}) == []


def test_overdrawn_cash_is_a_warning_but_a_card_in_debt_is_not():
    found = run("", [info("Assets:Cash", "cash"), info("Liabilities:Card", "credit_card")],
                {"Assets:Cash": {"GBP": Decimal(-5)}, "Liabilities:Card": {"GBP": Decimal(-300)}})
    assert [(f.kind, f.severity, f.account) for f in found if f.severity == "warning"] == [("overdrawn", "warning", "Assets:Cash")]
    assert "-5 GBP" in found[0].detail


def test_a_balance_never_or_long_ago_checked_is_stale():
    text = "2025-01-01 open Assets:Bank\n2026-03-01 balance Assets:Bank 0 GBP\n"
    found = run(text, [info("Assets:Bank", "checking")], {"Assets:Bank": {"GBP": Decimal(10)}})
    assert kinds(found) == ["stale_balance"] and "since 2026-03-01" in found[0].title
    never = run("", [info("Assets:Bank", "checking")], {"Assets:Bank": {"GBP": Decimal(10)}})
    assert "never" in never[0].title
    assert run(text, [info("Assets:Bank", "checking")], {"Assets:Bank": {"GBP": Decimal(10)}}, stale=120) == []
    assert run("", [info("Assets:Bank", "checking", opened="2026-05-01")], {"Assets:Bank": {}}) == []


def test_identical_entries_are_flagged_unless_recurring():
    block = '2026-05-03 * "Cafe" "Lunch"\n  Expenses:Food 5 GBP\n  Assets:Bank -5 GBP\n'
    base = "2025-01-01 open Expenses:Food\n2025-01-01 open Assets:Bank\n"
    found = run(base + block + block, [], {})
    assert kinds(found) == ["duplicate"] and len(found[0].transactions) == 2 and found[0].severity == "warning"
    tagged = block.replace("\n  Expenses", '\n  recurring: "rent"\n  Expenses', 1)
    assert run(base + tagged + tagged, [], {}) == []
    assert run(base + block + block.replace("5 GBP", "6 GBP").replace("-5", "-6"), [], {}) == []


def test_uncategorised_pending_and_future_entries():
    text = (
        "2025-01-01 open Expenses:Uncategorised\n2025-01-01 open Assets:Bank\n"
        '2026-05-03 ! "Cafe" "Pending one"\n  Expenses:Uncategorised 5 GBP\n  Assets:Bank -5 GBP\n'
        '2026-07-03 * "Later"\n  Expenses:Uncategorised 7 GBP\n  Assets:Bank -7 GBP\n'
    )
    found = run(text, [], {})
    assert kinds(found) == ["future", "pending", "uncategorised"]
    assert next(f for f in found if f.kind == "uncategorised").title.startswith("2 transaction(s)")


def test_an_empty_account_untouched_for_months_is_unused_and_ledger_errors_come_first():
    found = run("", [info("Assets:Old", "checking", opened="2025-01-01")], {}, [LedgerError(message="boom")])
    assert [f.kind for f in found] == ["ledger_error", "unused"] and found[0].detail == "boom"
    assert run("", [info("Assets:Recent", "checking", opened="2026-05-01")], {}) == []


def test_amounts_in_findings_are_written_with_thousands_commas():
    found = run("", [info("Assets:Cash", "cash")], {"Assets:Cash": {"GBP": Decimal("-1234567.80")}})
    assert "-1,234,567.80 GBP" in found[0].detail
