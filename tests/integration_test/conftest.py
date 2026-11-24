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
