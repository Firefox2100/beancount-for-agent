import pytest
from fastapi.testclient import TestClient

from beancount_mcp.api.app import create_app
from beancount_mcp.config import Settings

AGENT = {"X-Actor": "agent", "X-Client-Id": "mcp"}
CHECKING = "Assets:Bank:Checking"

FEE = {
    "title": "Bank fee", "description": "A fee the bank took from this account.", "kinds": ["checking"],
    "params": {"fee": {"type": "amount", "description": "What was taken."}},
    "narration": "Bank fee",
    "postings": [{"account": "@self", "amount": "-$fee"}, {"account": "Expenses:Fees", "amount": "$fee"}],
}


def define(client, rid="bank_fee", definition=None, headers=None):
    return client.put(f"/ledgers/wide/recipe-definitions/{rid}", json=definition or FEE, headers=headers or {})


def propose(client, item, item_id, value, version=None):
    version = version or client.get("/ledgers/wide").json()["version"]
    return client.post("/agent/setup", headers=AGENT, json={"item": item, "id": item_id, "value": value, "note": "drafted for you"})


def test_a_user_defines_a_recipe_and_it_is_offered_and_performed_like_a_built_in_one(client, wide_ledger):
    assert define(client).status_code == 200
    listed = {r["id"]: r for r in client.get("/ledgers/wide/recipes", params={"account": CHECKING}).json()}
    assert "bank_fee" in listed and "spend" in listed
    assert listed["bank_fee"]["params_schema"]["required"] == ["fee"]
    assert "bank_fee" not in {r["id"] for r in client.get("/ledgers/wide/recipes", params={"account": "Assets:Wallet"}).json()}

    done = client.post(f"/ledgers/wide/accounts/{CHECKING}/actions/bank_fee", json={"fee": "5.30 USD", "date": "2026-02-03"})
    assert done.status_code == 200, done.text
    (transaction,) = client.get("/ledgers/wide/transactions").json()["items"]
    assert [(p["account"], p["units"]["number"]) for p in transaction["postings"]] == [(CHECKING, "-5.30"), ("Expenses:Fees", "5.30")]
    assert client.get("/ledgers/wide").json()["errors"] == []
    assert client.get("/ledgers/wide/recipe-definitions").json()["bank_fee"]["title"] == "Bank fee"


def test_a_definition_that_clashes_or_cannot_work_is_refused_and_agents_cannot_write_one_directly(client, wide_ledger):
    assert "built-in recipe" in define(client, "spend").json()["detail"]
    broken = {**FEE, "postings": [{"account": "@self", "amount": "-$nope"}, {"account": "Expenses:Fees"}]}
    assert define(client, "x", broken).status_code == 422
    assert define(client, headers=AGENT).status_code == 403
    assert client.delete("/ledgers/wide/recipe-definitions/bank_fee", headers=AGENT).status_code == 403


def test_preview_shows_the_transaction_without_saving_or_writing(client, wide_ledger):
    shown = client.post("/ledgers/wide/recipe-definitions/bank_fee/preview", json={"definition": FEE, "account": CHECKING, "params": {"fee": "4 USD"}})
    assert shown.status_code == 200, shown.text
    postings = shown.json()["transaction"]["postings"]
    assert [(p["account"], p["units"]["number"]) for p in postings] == [(CHECKING, "-4"), ("Expenses:Fees", "4")]
    assert client.get("/ledgers/wide/recipe-definitions").json() == {}
    assert client.get("/ledgers/wide/transactions").json()["total"] == 0
    missing = client.post("/ledgers/wide/recipe-definitions/bank_fee/preview", json={"account": CHECKING, "params": {"fee": "4 USD"}})
    assert missing.status_code == 422 and "send its definition" in missing.json()["detail"]
    wrong = client.post("/ledgers/wide/recipe-definitions/bank_fee/preview", json={"definition": FEE, "account": "Assets:Wallet", "params": {"fee": "4 USD"}})
    assert wrong.status_code == 422 and "is for checking" in wrong.json()["detail"]


def test_an_agent_drafts_a_recipe_tests_it_proposes_it_and_it_works_only_after_approval(client, wide_ledger):
    description = client.get("/agent/setup/recipe", params={"ledger": "wide"}, headers=AGENT).json()
    assert description["item"] == "recipe" and description["current"] == {} and "postings" in description["schema"]["properties"]

    preview = client.post("/agent/recipes/preview", headers=AGENT, json={"ledger": "wide", "id": "bank_fee", "definition": FEE, "account": "Checking", "params": {"fee": "3 USD"}})
    assert preview.status_code == 200 and preview.json()["transaction"]["postings"][1]["units"]["number"] == "3"

    proposal = client.post("/agent/setup", headers=AGENT, json={"ledger": "wide", "item": "recipe", "id": "bank_fee", "value": FEE, "note": "for the monthly fee"})
    assert proposal.status_code == 201, proposal.text
    assert proposal.json()["operation"]["kind"] == "set_profile_item" and proposal.json()["status"] == "pending"
    assert client.get("/ledgers/wide/recipe-definitions").json() == {}
    unusable = client.post("/agent/actions", headers=AGENT, json={"ledger": "wide", "account": "Checking", "recipe": "bank_fee", "params": {"fee": "3 USD"}})
    assert unusable.status_code == 404 or unusable.status_code == 422

    approved = client.post(f"/ledgers/wide/changes/{proposal.json()['id']}/approve", json={})
    assert approved.status_code == 200, approved.text
    assert "bank_fee" in client.get("/ledgers/wide/recipe-definitions").json()
    used = client.post("/agent/actions", headers=AGENT, json={"ledger": "wide", "account": "Checking", "recipe": "bank_fee", "params": {"fee": "3 USD", "date": "2026-02-03"}})
    assert used.status_code == 201 and used.json()["status"] == "pending"
    assert client.get("/ledgers/wide/transactions").json()["total"] == 0


def test_a_proposal_that_could_not_be_saved_is_refused_up_front_and_nothing_waits_for_approval(client, wide_ledger):
    for item, item_id, value, fragment in [
        ("recipe", "spend", FEE, "built-in recipe"),
        ("recipe", "x", {**FEE, "postings": [{"account": "@self", "amount": "$a + $b"}, {"account": "Expenses:Fees"}]}, "not valid"),
        ("budget", "b", {"account": "Assets:Bank:Checking", "amount": {"number": "1", "currency": "USD"}}, "under Expenses"),
        ("goal", "g", {"title": "x", "accounts": ["Expenses:Food"], "target": {"number": "1", "currency": "USD"}}, "under Assets"),
        ("recurring", "Bad Id", {}, "not a valid recurring id"),
    ]:
        response = propose(client, item, item_id, value)
        assert response.status_code == 422 and fragment in response.json()["detail"], (item, response.text)
    assert client.get("/ledgers/wide/changes").json() == []


def test_budgets_goals_and_recurring_items_are_proposed_approved_and_removed_the_same_way(client, wide_ledger):
    budget = {"account": "Expenses:Food", "amount": {"number": "300", "currency": "USD"}}
    goal = {"title": "Holiday", "accounts": ["Assets:Bank:Fixed"], "target": {"number": "1000", "currency": "USD"}}
    recurring = {"title": "Rent", "from_account": CHECKING, "to_account": "Expenses:Tax", "amount": {"number": "900", "currency": "USD"}, "start": "2026-01-01"}
    for item, item_id, value in (("budget", "food", budget), ("goal", "holiday", goal), ("recurring", "rent", recurring)):
        made = propose(client, item, item_id, value)
        assert made.status_code == 201, made.text
        assert client.post(f"/ledgers/wide/changes/{made.json()['id']}/approve", json={}).status_code == 200
    profile = client.get("/ledgers/wide/profile").json()["profile"]
    assert profile["budgets"]["food"]["account"] == "Expenses:Food" and "holiday" in profile["goals"] and "rent" in profile["recurring"]

    gone = propose(client, "budget", "food", None)
    assert gone.status_code == 201
    assert client.post(f"/ledgers/wide/changes/{gone.json()['id']}/approve", json={}).status_code == 200
    assert "food" not in client.get("/ledgers/wide/profile").json()["profile"]["budgets"]
    withdrawn = propose(client, "goal", "other", goal)
    assert client.post(f"/agent/proposals/{withdrawn.json()['id']}/withdraw", headers=AGENT, json={}).status_code == 200
    assert "other" not in client.get("/ledgers/wide/profile").json()["profile"]["goals"]


def test_setup_is_never_applied_without_a_person_even_when_agent_changes_otherwise_are(tmp_path):
    app = create_app(Settings(data_dir=tmp_path / "d", agent_approval_required=False, _env_file=None))
    client = TestClient(app)
    client.post("/ledgers", json={"id": "wide"})
    client.post("/ledgers/wide/accounts", json={"account": "Expenses:Food", "date": "2026-01-01"})
    ledger_change = client.post("/ledgers/wide/changes", headers={**AGENT, "If-Match": client.get("/ledgers/wide").json()["version"]},
                                json={"operation": {"kind": "open_account", "account": "Expenses:Fun", "date": "2026-01-01"}})
    assert ledger_change.json()["status"] == "approved"
    budget = client.post("/agent/setup", headers=AGENT, json={"item": "budget", "id": "food", "value": {"account": "Expenses:Food", "amount": {"number": "5", "currency": "USD"}}})
    assert budget.status_code == 201 and budget.json()["status"] == "pending"
    assert client.get("/ledgers/wide/profile").json()["profile"]["budgets"] == {}


def test_the_profile_warns_about_a_recipe_naming_an_account_that_is_not_open(client, wide_ledger):
    define(client, "ghost", {**FEE, "postings": [{"account": "@self", "amount": "-$fee"}, {"account": "Expenses:Missing", "amount": "$fee"}]})
    assert any("recipe ghost: Expenses:Missing is not open" in w for w in client.get("/ledgers/wide/profile").json()["warnings"])


def test_a_saved_recipe_that_a_built_in_later_shadows_loses_and_a_removed_one_disappears(client, wide_ledger):
    define(client)
    assert client.delete("/ledgers/wide/recipe-definitions/bank_fee").status_code == 204
    assert "bank_fee" not in {r["id"] for r in client.get("/ledgers/wide/recipes", params={"account": CHECKING}).json()}
    gone = client.post(f"/ledgers/wide/accounts/{CHECKING}/actions/bank_fee", json={"fee": "1 USD"})
    assert gone.status_code == 404
