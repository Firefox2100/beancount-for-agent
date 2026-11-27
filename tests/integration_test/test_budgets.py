import datetime as dt

import pytest

AGENT = {"X-Actor": "agent", "X-Client-Id": "mcp"}
TODAY = dt.date.today()


@pytest.fixture
def food(client, ledger):
    assert client.post("/ledgers/main/accounts", json={"account": "Expenses:Food:Groceries", "date": "2025-01-01"}).status_code == 201
    return ledger


def spend(client, day, amount, account="Expenses:Food:Groceries"):
    response = client.post("/ledgers/main/transactions", json={"date": day, "narration": "x", "postings": [
        {"account": account, "units": {"number": amount, "currency": "USD"}}, {"account": "Assets:Bank"}]})
    assert response.status_code == 201, response.text


def put(client, name="food", **overrides):
    return client.put(f"/ledgers/main/budgets/{name}", json={"account": "Expenses:Food", "amount": {"number": "100", "currency": "USD"}, **overrides})


def test_only_the_user_sets_budgets_and_the_agent_reads_how_they_are_going(client, food):
    assert put(client).status_code == 200
    assert client.put("/ledgers/main/budgets/food", json={"account": "Expenses:Food", "amount": {"number": "1", "currency": "USD"}}, headers=AGENT).status_code == 403
    assert client.delete("/ledgers/main/budgets/food", headers=AGENT).status_code == 403
    spend(client, TODAY.isoformat(), "130")
    (status,) = client.get("/agent/budgets", headers=AGENT).json()
    assert (status["id"], status["spent"], status["remaining"], status["state"]) == ("food", "130.00", "-30.00", "over")
    assert status["start"] <= TODAY.isoformat() <= status["end"] and len(status["history"]) == 3
    assert client.get("/ledgers/main/profile").json()["profile"]["budgets"]["food"]["account"] == "Expenses:Food"
    assert client.delete("/ledgers/main/budgets/food").status_code == 204 and client.get("/ledgers/main/budgets").json() == []


def test_over_budget_is_listed_before_the_ones_on_track(client, food):
    client.post("/ledgers/main/accounts", json={"account": "Expenses:Fun", "date": "2025-01-01"})
    put(client, "fun", account="Expenses:Fun")
    put(client)
    spend(client, TODAY.isoformat(), "500", "Expenses:Fun")
    assert [s["id"] for s in client.get("/ledgers/main/budgets").json()] == ["fun", "food"]


def test_a_budget_outside_expenses_or_without_accounts_is_refused_or_warned(client, food):
    refused = put(client, account="Assets:Bank")
    assert refused.status_code == 422 and "under Expenses" in refused.text
    put(client, "ghost", account="Expenses:Nowhere")
    assert any("no open account under Expenses:Nowhere" in w for w in client.get("/ledgers/main/profile").json()["warnings"])


def test_suggestions_come_from_whole_months_and_can_be_adopted(client, food):
    first = TODAY.replace(day=1)
    for months_ago in (1, 2, 3):
        month = first.replace(year=first.year + (first.month - months_ago - 1) // 12, month=(first.month - months_ago - 1) % 12 + 1)
        spend(client, month.replace(day=5).isoformat(), "200")
    (suggestion,) = client.get("/agent/budgets/suggestions", headers=AGENT).json()
    assert suggestion["id"] == "food" and suggestion["budget"]["account"] == "Expenses:Food" and suggestion["budget"]["amount"]["number"] == "200"
    assert client.put("/ledgers/main/budgets/food", json=suggestion["budget"]).status_code == 200
    assert client.get("/agent/budgets/suggestions", headers=AGENT).json() == []


def test_a_price_in_the_ledger_converts_other_currencies_and_says_so(client, food):
    put(client)
    spend(client, TODAY.isoformat(), "40")
    client.post("/ledgers/main/transactions", json={"date": TODAY.isoformat(), "narration": "abroad", "postings": [
        {"account": "Expenses:Food:Groceries", "units": {"number": "100", "currency": "EUR"}}, {"account": "Assets:Bank", "units": {"number": "-100", "currency": "EUR"}}]})
    before = client.get("/agent/budgets", headers=AGENT).json()[0]
    assert before["spent"] == "40.00" and before["other_currencies"] == {"EUR": "100.00"} and not before["approximate"]
    assert client.post("/ledgers/main/directives", json={"kind": "price", "date": (TODAY - dt.timedelta(days=1)).isoformat(), "currency": "EUR", "amount": {"number": "1.10", "currency": "USD"}}).status_code == 201
    after = client.get("/agent/budgets", headers=AGENT).json()[0]
    assert after["spent"] == "150.00" and after["approximate"] and after["other_currencies"] == {}
    assert after["converted"] == [{"currency": "EUR", "amount": "100.00", "rate": "1.1", "value": "110.00", "source": "ledger"}]
