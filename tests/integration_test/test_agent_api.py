import pytest
from fastapi.testclient import TestClient

from beancount_mcp.api.app import create_app
from beancount_mcp.config import Settings

CLIENT = {"X-Client-Id": "dsh", "X-Session-Id": "s1"}


@pytest.fixture
def api(client):
    """The agent surface over a ledger with a bank account and a food expense account."""
    client.post("/ledgers", json={"id": "home", "operating_currencies": ["GBP"]})
    for account, kind, currencies in (("Assets:Bank:Current", "checking", ["GBP"]), ("Expenses:Food", None, [])):
        body = {"account": account, "date": "2026-01-01", "currencies": currencies, "type": kind}
        assert client.post("/ledgers/home/accounts", json=body).status_code == 201
    return client


def approve(client, change):
    done = client.post(f"/ledgers/home/changes/{change['id']}/approve", json={})
    assert done.status_code == 200, done.text


def test_a_purchase_is_proposed_with_loose_names_and_the_ledger_is_optional(api):
    response = api.post("/agent/expenses", json={"from_account": "Current", "expense_account": "food", "amount": "12.50",
                                                "date": "2026-02-01", "narration": "Lunch"}, headers=CLIENT)
    assert response.status_code == 201, response.text
    change = response.json()
    assert change["status"] == "pending" and change["caller"] == {"actor": "agent", "client_id": "dsh", "session_id": "s1"}
    assert change["source"]["recipe"] == "spend"
    assert api.get("/ledgers/home/balances").json() == []
    approve(api, change)
    assert {b["account"]: b["balances"] for b in api.get("/agent/balances").json()}["Expenses:Food"] == {"GBP": "12.50"}


def test_this_surface_can_only_propose_whatever_the_actor_header_says(api):
    response = api.post("/agent/expenses", json={"from_account": "Current", "expense_account": "Food", "amount": "5"},
                        headers={**CLIENT, "X-Actor": "user"})
    assert response.json()["status"] == "pending" and response.json()["caller"]["actor"] == "agent"
    assert api.get("/ledgers/home/balances").json() == []


def test_mistakes_come_back_as_readable_errors(api):
    response = api.post("/agent/expenses", json={"from_account": "Nowhere", "expense_account": "Food", "amount": "5"})
    assert response.status_code == 422 and "no open account matches" in response.json()["detail"]
    assert api.post("/agent/expenses", json={"from_account": "Current", "expense_account": "Food"}).status_code == 422


def test_reads_filter_by_account_and_prefix(api):
    spent = api.post("/agent/expenses", json={"from_account": "Current", "expense_account": "Food", "amount": "7",
                                              "date": "2026-02-02", "payee": "Cafe"}).json()
    approve(api, spent)
    assert [b["account"] for b in api.get("/agent/balances", params={"account": "Expenses"}).json()] == ["Expenses:Food"]
    found = api.get("/agent/transactions", params={"text": "cafe", "account": "Food"}).json()
    assert len(found) == 1 and found[0]["payee"] == "Cafe" and "id" in found[0]
    assert api.get("/agent/transactions", params={"text": "nothing"}).json() == []
    assert {a["name"] for a in api.get("/agent/accounts").json()} == {"Assets:Bank:Current", "Expenses:Food"}
    assert any(k["name"] == "checking" for k in api.get("/agent/account-types").json())
    recipes = api.get("/agent/recipes", params={"account": "Current"}).json()
    assert {"spend", "transfer"} <= {r["id"] for r in recipes}
    position = api.get("/agent/financial-position", params={"points": 1}).json()
    assert position["base_currency"] == "GBP" and len(position["points"]) == 1
    assert api.get("/agent/reference-rates/status").json()["state"] == "disabled"


def test_proposals_are_private_to_the_client_and_can_be_withdrawn(api):
    mine = api.post("/agent/accounts/open", json={"account": "Assets:Cash", "type": "cash", "currencies": ["GBP"]}, headers=CLIENT).json()
    other = {"X-Client-Id": "someone-else"}
    assert [p["id"] for p in api.get("/agent/proposals", headers=CLIENT).json()] == [mine["id"]]
    assert api.get("/agent/proposals", headers=other).json() == []
    withdrawn = api.post(f"/agent/proposals/{mine['id']}/withdraw", json={})
    assert withdrawn.json()["status"] == "withdrawn"
    assert api.get("/agent/proposals", headers=CLIENT).json() == []


def test_recipe_action_amend_and_delete_are_proposals(api):
    action = api.post("/agent/actions", json={"account": "Current", "recipe": "spend",
                                              "params": {"expense_account": "Food", "amount": "9", "date": "2026-03-01"}})
    assert action.status_code == 201 and action.json()["operation"]["kind"] == "add_transaction"
    approve(api, action.json())
    transaction = api.get("/agent/transactions").json()[0]
    amended = api.post(f"/agent/transactions/{transaction['id']}/amend", json={"narration": "Brunch", "date": "2026-03-02"})
    assert amended.status_code == 201, amended.text
    empty = api.post(f"/agent/transactions/{transaction['id']}/amend", json={})
    assert empty.status_code == 422 and "say what to change" in empty.json()["detail"]
    approve(api, amended.json())
    assert api.get("/agent/transactions").json()[0]["narration"] == "Brunch"
    deletion = api.post(f"/agent/transactions/{transaction['id']}/deletion", json={})
    assert deletion.status_code == 201
    approve(api, deletion.json())
    assert api.get("/agent/transactions").json() == []
    assert api.get("/ledgers/home").json()["errors"] == []


def test_bank_details_are_masked_on_this_surface(api):
    api.put("/ledgers/home/accounts/Assets:Bank:Current/details", json={"set": {"bank_name": "Barclays", "account_number": "12345678"}})
    shown = next(a for a in api.get("/agent/accounts").json() if a["name"] == "Assets:Bank:Current")["details"]
    assert shown == {"bank_name": "Barclays", "account_number": "••••5678"}


def test_the_ledger_must_be_named_when_there_are_several(api):
    api.post("/agent/ledgers", json={"id": "other"})
    response = api.get("/agent/accounts")
    assert response.status_code == 422 and "name the ledger" in response.json()["detail"]
    assert api.get("/agent/accounts", params={"ledger": "other"}).json() == []


def test_the_token_guards_this_surface_too(tmp_path):
    secured = TestClient(create_app(Settings(data_dir=tmp_path / "data", auth_token="t0ken")))
    assert secured.get("/agent/ledgers").status_code == 401
    assert secured.get("/agent/ledgers", headers={"Authorization": "Bearer t0ken"}).status_code == 200
