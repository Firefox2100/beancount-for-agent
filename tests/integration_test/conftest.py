import pytest
from fastapi.testclient import TestClient

from beancount_mcp.api.app import create_app
from beancount_mcp.config import Settings
from beancount_mcp.models import Layout


@pytest.fixture
def make_client(tmp_path):
    def build(layout: Layout = Layout.YEARLY) -> TestClient:
        return TestClient(create_app(Settings(data_dir=tmp_path / "data", layout=layout)))

    return build


@pytest.fixture
def client(make_client) -> TestClient:
    return make_client()


@pytest.fixture
def ledger_dir(tmp_path):
    return tmp_path / "data" / "main"


@pytest.fixture
def ledger(client):
    """A ledger with two open accounts; returns its API prefix."""
    client.post("/ledgers", json={"id": "main", "operating_currencies": ["USD"]})
    for account in ("Assets:Bank", "Expenses:Food"):
        response = client.post(
            "/ledgers/main/accounts", json={"account": account, "date": "2026-01-01"}
        )
        assert response.status_code == 201
    return "/ledgers/main"


@pytest.fixture
def card_ledger(client):
    """A ledger with a dual-currency card, its unbilled account and a debit account."""
    client.post("/ledgers", json={"id": "cards"})
    opens = [
        {"account": "Liabilities:Card:Main", "currencies": ["USD", "CNY"], "type": "credit_card"},
        {"account": "Liabilities:Card:Main:Unbilled"},
        {"account": "Assets:Bank:Debit", "currencies": ["CNY"]},
        {"account": "Expenses:Food"},
    ]
    for item in opens:
        response = client.post("/ledgers/cards/accounts", json={"date": "2026-01-01", **item})
        assert response.status_code == 201, response.text
    return "/ledgers/cards"


@pytest.fixture
def wide_ledger(client):
    """One account of every type, plus the income, expense and equity accounts they use."""
    client.post("/ledgers", json={"id": "wide"})
    opens = [
        {"account": "Assets:Bank:Checking", "currencies": ["USD"], "type": "checking"},
        {"account": "Assets:Bank:Yuan", "currencies": ["CNY"], "type": "checking"},
        {"account": "Assets:Bank:Fixed", "currencies": ["USD"], "type": "savings"},
        {"account": "Assets:Wallet", "type": "cash"},
        {"account": "Assets:Owed:Friend", "currencies": ["USD"], "type": "receivable"},
        {"account": "Liabilities:Payable:Supplier", "currencies": ["USD"], "type": "payable"},
        {"account": "Liabilities:Loan:Car", "currencies": ["USD"], "type": "loan"},
        {"account": "Assets:Invest", "type": "brokerage", "booking": "FIFO"},
        {"account": "Assets:Invest:Cash", "currencies": ["USD"], "type": "checking"},
        {"account": "Income:Salary"},
        {"account": "Income:Interest"},
        {"account": "Income:Gains"},
        {"account": "Income:Dividends"},
        {"account": "Expenses:Food"},
        {"account": "Expenses:Tax"},
        {"account": "Expenses:Interest"},
        {"account": "Expenses:Fees"},
        {"account": "Expenses:WrittenOff"},
    ]
    for item in opens:
        response = client.post("/ledgers/wide/accounts", json={"date": "2026-01-01", **item})
        assert response.status_code == 201, response.text
    return "/ledgers/wide"
