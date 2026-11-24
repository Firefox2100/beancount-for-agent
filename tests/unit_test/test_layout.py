from datetime import date

import pytest

from beancount_mcp.ledger.layout import (
    MAIN_FILE,
    accounts_file,
    initial_files,
    quote,
    structure_problems,
    transaction_file,
)
from beancount_mcp.models import Layout

DAY = date(2026, 3, 9)


@pytest.mark.parametrize(
    ("layout", "expected"),
    [
        (Layout.SINGLE, "main.beancount"),
        (Layout.YEARLY, "transactions/2026.beancount"),
        (Layout.MONTHLY, "transactions/2026-03.beancount"),
    ],
)
def test_transaction_file(layout, expected):
    assert transaction_file(layout, DAY) == expected


def test_accounts_file():
    assert accounts_file(Layout.SINGLE) == MAIN_FILE
    assert accounts_file(Layout.YEARLY) == "accounts.beancount"


def test_quote_escapes():
    assert quote('a "b" \\') == '"a \\"b\\" \\\\"'


def test_initial_files_single_and_split():
    single = initial_files(Layout.SINGLE, "Book", ["USD"], DAY)
    assert list(single) == [MAIN_FILE]
    assert 'option "operating_currency" "USD"' in single[MAIN_FILE]

    split = initial_files(Layout.MONTHLY, None, [], DAY)
    assert set(split) == {MAIN_FILE, "accounts.beancount", "transactions/2026-03.beancount"}
    assert 'include "transactions/*.beancount"' in split[MAIN_FILE]


def write(root, names):
    for name in names:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("")


def test_structure_problems(tmp_path):
    write(tmp_path, ["main.beancount", "accounts.beancount", "transactions/2026.beancount"])
    assert structure_problems(tmp_path, Layout.YEARLY) == []
    assert structure_problems(tmp_path, Layout.MONTHLY) != []
    assert structure_problems(tmp_path, Layout.SINGLE) != []


def test_structure_ignores_sidecar_and_other_files(tmp_path):
    write(tmp_path, ["main.beancount", ".sidecar/stale.beancount", "notes.txt"])
    assert structure_problems(tmp_path, Layout.SINGLE) == []
