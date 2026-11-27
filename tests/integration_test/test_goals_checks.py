import datetime as dt

import pytest

AGENT = {"X-Actor": "agent", "X-Client-Id": "mcp"}
TODAY = dt.date.today()


@pytest.fixture
def saver(client, ledger):
    assert client.post("/ledgers/main/accounts", json={"account": "Assets:Savings", "date": "2025-01-01", "type": "savings", "currencies": ["USD"]}).status_code == 201
    client.post("/ledgers/main/transactions", json={"date": TODAY.isoformat(), "narration": "saved", "postings": [
        {"account": "Assets:Savings", "units": {"number": "400", "currency": "USD"}}, {"account": "Assets:Bank"}]})
    return ledger


def goal(**overrides):
    return {"title": "Holiday", "accounts": ["Assets:Savings"], "target": {"number": "1000", "currency": "USD"}, **overrides}


def test_only_the_user_sets_goals_and_the_agent_reads_progress(client, saver):
    assert client.put("/ledgers/main/goals/holiday", json=goal()).status_code == 200
    assert client.put("/ledgers/main/goals/holiday", json=goal(), headers=AGENT).status_code == 403
    assert client.delete("/ledgers/main/goals/holiday", headers=AGENT).status_code == 403
    (status,) = client.get("/agent/goals", headers=AGENT).json()
    assert (status["saved"], status["remaining"], status["percent"], status["state"]) == ("400.00", "600.00", "40.00", "open")
    by = (TODAY.replace(day=1) + dt.timedelta(days=200)).isoformat()
    client.put("/ledgers/main/goals/holiday", json=goal(by=by, monthly={"number": "50", "currency": "USD"}))
    (planned,) = client.get("/ledgers/main/goals").json()
    assert planned["state"] == "behind" and planned["needed_monthly"] and planned["projected"]
    assert client.delete("/ledgers/main/goals/holiday").status_code == 204 and client.get("/ledgers/main/goals").json() == []


def test_a_goal_outside_assets_is_refused_and_a_missing_account_warns(client, saver):
    assert client.put("/ledgers/main/goals/x", json=goal(accounts=["Expenses:Food"])).status_code == 422
    client.put("/ledgers/main/goals/ghost", json=goal(accounts=["Assets:Nowhere"]))
    assert any("no open account under Assets:Nowhere" in w for w in client.get("/ledgers/main/profile").json()["warnings"])


def test_checks_find_an_overdrawn_account_and_a_duplicate_for_agents_too(client, ledger):
    client.post("/ledgers/main/accounts", json={"account": "Assets:Wallet", "date": "2025-01-01", "type": "cash"})
    entry = {"date": TODAY.isoformat(), "payee": "Cafe", "narration": "Lunch", "postings": [
        {"account": "Expenses:Food", "units": {"number": "9", "currency": "USD"}}, {"account": "Assets:Wallet", "units": {"number": "-9", "currency": "USD"}}]}
    client.post("/ledgers/main/transactions", json=entry)
    client.post("/ledgers/main/transactions", json=entry)
    found = client.get("/agent/checks", headers=AGENT).json()
    assert [f["kind"] for f in found if f["severity"] == "warning"] == ["duplicate", "overdrawn"]
    assert next(f for f in found if f["kind"] == "duplicate")["transactions"]
    assert client.get("/ledgers/main/checks", params={"stale_days": 1}).status_code == 200
