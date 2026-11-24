import re
from datetime import date
from pathlib import Path

from beancount_mcp.models import Layout

MAIN_FILE = "main.beancount"
ACCOUNTS_FILE = "accounts.beancount"
TRANSACTIONS_DIR = "transactions"
SIDECAR_DIR = ".sidecar"

_YEARLY_NAME = re.compile(r"^\d{4}\.beancount$")
_MONTHLY_NAME = re.compile(r"^\d{4}-(0[1-9]|1[0-2])\.beancount$")


def accounts_file(layout: Layout) -> str:
    return MAIN_FILE if layout is Layout.SINGLE else ACCOUNTS_FILE


def quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def transaction_file(layout: Layout, day: date) -> str:
    """Relative path of the file that holds transactions dated `day`."""
    match layout:
        case Layout.SINGLE:
            return MAIN_FILE
        case Layout.YEARLY:
            return f"{TRANSACTIONS_DIR}/{day:%Y}.beancount"
        case Layout.MONTHLY:
            return f"{TRANSACTIONS_DIR}/{day:%Y-%m}.beancount"


def initial_files(
    layout: Layout, title: str | None, operating_currencies: list[str], today: date
) -> dict[str, str]:
    """Files a new ledger starts with, keyed by relative path."""
    header = ""
    if title:
        header += f"option \"title\" {quote(title)}\n"
    for currency in operating_currencies:
        header += f"option \"operating_currency\" {quote(currency)}\n"

    if layout is Layout.SINGLE:
        return {MAIN_FILE: header}

    main = header + f'\ninclude "{ACCOUNTS_FILE}"\ninclude "{TRANSACTIONS_DIR}/*.beancount"\n'
    return {
        MAIN_FILE: main,
        ACCOUNTS_FILE: "",
        transaction_file(layout, today): "",
    }


def structure_problems(root: Path, layout: Layout) -> list[str]:
    """Reasons the directory does not match `layout`; empty when it does."""
    problems: list[str] = []
    found = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*.beancount")
        if SIDECAR_DIR not in path.relative_to(root).parts
    }

    if MAIN_FILE not in found:
        problems.append(f"missing {MAIN_FILE}")
    if layout is Layout.SINGLE:
        problems += [f"unexpected file {name}" for name in sorted(found - {MAIN_FILE})]
        return problems

    if ACCOUNTS_FILE not in found:
        problems.append(f"missing {ACCOUNTS_FILE}")
    name_pattern = _YEARLY_NAME if layout is Layout.YEARLY else _MONTHLY_NAME
    for name in sorted(found - {MAIN_FILE, ACCOUNTS_FILE}):
        parent, _, leaf = name.rpartition("/")
        if parent != TRANSACTIONS_DIR or not name_pattern.match(leaf):
            problems.append(f"unexpected file {name}")
    return problems
