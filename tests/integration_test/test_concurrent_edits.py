"""A person editing the ledger in Fava while a change is being applied: the change is computed again on what is there."""

import pytest
from fastapi.testclient import TestClient
from integration_test.helpers import lunch

from beancount_mcp.api.app import create_app
from beancount_mcp.config import Settings
from beancount_mcp.ledger.errors import StaleVersion
from beancount_mcp.ledger.engine import Ledger
from beancount_mcp.models import AddTransaction, TransactionInput

HUMAN = '\n2026-02-10 * "Fava" "Typed in by hand"\n  Expenses:Food  9.99 USD\n  Assets:Bank   -9.99 USD\n'


@pytest.fixture
def app_and_ledger(tmp_path):
    app = create_app(Settings(data_dir=tmp_path / "data", _env_file=None))
    client = TestClient(app)
    client.post("/ledgers", json={"id": "main", "operating_currencies": ["USD"]})
    for account in ("Assets:Bank", "Expenses:Food"):
        client.post("/ledgers/main/accounts", json={"account": account, "date": "2026-01-01"})
    client.post("/ledgers/main/transactions", json=lunch("2026-02-03"))
    return client, app.state.ledger_service._store.open("main")


def edit_while_staging(monkeypatch, times=1):
    """After the change has been staged, append to the real ledger file the way an editor saving would."""
    original = Ledger._copy_to
    state = {"left": times}

    def copy_then_edit(self, stage):
        original(self, stage)
        if state["left"] > 0:
            state["left"] -= 1
            target = next(p for p in self.ledger_files() if p.parent.name == "transactions")
            target.write_text(target.read_text() + HUMAN)

    monkeypatch.setattr(Ledger, "_copy_to", copy_then_edit)


def add(narration):
    return AddTransaction(transaction=TransactionInput(**lunch("2026-02-04", narration=narration)))


def test_a_change_applied_while_the_file_changes_is_computed_again_and_keeps_both(app_and_ledger, monkeypatch):
    client, ledger = app_and_ledger
    edit_while_staging(monkeypatch)
    ledger.apply(add("Ours"))
    narrations = [t["narration"] for t in client.get("/ledgers/main/transactions").json()["items"]]
    assert "Typed in by hand" in narrations and "Ours" in narrations and "Lunch" in narrations
    assert client.get("/ledgers/main").json()["errors"] == []


def test_an_edit_that_deletes_by_position_still_hits_the_right_entry_after_the_file_shifted(app_and_ledger, monkeypatch):
    client, ledger = app_and_ledger
    ident = client.get("/ledgers/main/transactions").json()["items"][0]["id"]
    target = next(p for p in ledger.ledger_files() if p.parent.name == "transactions")
    target.write_text(HUMAN + target.read_text())
    from beancount_mcp.models import DeleteTransaction
    ledger.apply(DeleteTransaction(id=ident))
    narrations = [t["narration"] for t in client.get("/ledgers/main/transactions").json()["items"]]
    assert narrations == ["Typed in by hand"]


def test_a_caller_that_pinned_a_version_gets_the_conflict_instead(app_and_ledger, monkeypatch):
    _, ledger = app_and_ledger
    version = ledger.version()
    edit_while_staging(monkeypatch)
    with pytest.raises(StaleVersion):
        ledger.apply(add("Ours"), expected_version=version)


def test_a_ledger_that_keeps_changing_gives_up_after_a_few_tries_and_writes_nothing_of_ours(app_and_ledger, monkeypatch):
    client, ledger = app_and_ledger
    edit_while_staging(monkeypatch, times=10)
    with pytest.raises(StaleVersion, match="changed while"):
        ledger.apply(add("Ours"))
    monkeypatch.undo()
    assert "Ours" not in [t["narration"] for t in client.get("/ledgers/main/transactions").json()["items"]]


def test_approving_a_pending_change_survives_an_edit_made_meanwhile(app_and_ledger, monkeypatch):
    client, _ = app_and_ledger
    version = client.get("/ledgers/main").json()["version"]
    proposed = client.post("/ledgers/main/changes", headers={"X-Actor": "agent", "X-Client-Id": "t", "If-Match": version},
                           json={"operation": {"kind": "add_transaction", "transaction": lunch("2026-02-05", narration="Proposed")}})
    assert proposed.status_code == 201
    edit_while_staging(monkeypatch)
    approved = client.post(f"/ledgers/main/changes/{proposed.json()['id']}/approve", json={})
    assert approved.status_code == 200, approved.text
    narrations = [t["narration"] for t in client.get("/ledgers/main/transactions").json()["items"]]
    assert {"Proposed", "Typed in by hand"} <= set(narrations)
