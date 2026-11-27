import datetime as dt

import pytest

from beancount_mcp.ledger.recurring import add_months

AGENT = {"X-Actor": "agent", "X-Client-Id": "mcp"}
TODAY = dt.date.today()


def rent(**overrides):
    values = {"title": "Rent", "from_account": "Assets:Bank", "to_account": "Expenses:Rent", "amount": {"number": "1200", "currency": "USD"},
              "every": "month", "start": (TODAY.replace(day=1) - dt.timedelta(days=62)).replace(day=1).isoformat(), "payee": "Landlord"}
    return {**values, **overrides}


@pytest.fixture
def home(client, ledger):
    assert client.post("/ledgers/main/accounts", json={"account": "Expenses:Rent", "date": "2025-01-01"}).status_code == 201
    return ledger


def set_item(client, item_id="rent", **overrides):
    return client.put(f"/ledgers/main/recurring/{item_id}", json=rent(**overrides))


def test_only_the_user_sets_the_schedule(client, home):
    assert set_item(client, headers=None).status_code == 200
    denied = client.put("/ledgers/main/recurring/rent", json=rent(), headers=AGENT)
    assert denied.status_code == 403
    assert client.delete("/ledgers/main/recurring/rent", headers=AGENT).status_code == 403
    assert [s["id"] for s in client.get("/ledgers/main/recurring").json()] == ["rent"]
    assert client.get("/ledgers/main/profile").json()["profile"]["recurring"]["rent"]["payee"] == "Landlord"
    assert client.delete("/ledgers/main/recurring/rent").status_code == 204
    assert client.get("/ledgers/main/recurring").json() == []


def test_an_agent_records_an_occurrence_and_it_stops_being_overdue(client, home):
    set_item(client)
    overdue = client.get("/agent/recurring", headers=AGENT).json()[0]["occurrences"]
    assert overdue and overdue[0]["status"] in ("overdue", "due")
    first = overdue[0]["date"]

    proposal = client.post("/agent/recurring/rent/proposal", json={"note": "paid rent"}, headers=AGENT)
    assert proposal.status_code == 201, proposal.text
    assert client.post(f"/ledgers/main/changes/{proposal.json()['id']}/approve", json={}).status_code == 200
    (transaction,) = client.get("/ledgers/main/transactions").json()["items"]
    assert transaction["meta"] == {"recurring": "rent", "due": first} and transaction["payee"] == "Landlord"
    assert [p["account"] for p in transaction["postings"]] == ["Expenses:Rent", "Assets:Bank"]
    after = client.get("/agent/recurring", headers=AGENT).json()[0]
    assert first not in [o["date"] for o in after["occurrences"]] and after["last_paid"] == TODAY.isoformat()


def test_a_payment_entered_by_hand_counts(client, home):
    set_item(client)
    due = client.get("/ledgers/main/recurring").json()[0]["occurrences"][0]["date"]
    day = dt.date.fromisoformat(due) + dt.timedelta(days=1)
    entered = client.post("/ledgers/main/transactions", json={
        "date": day.isoformat(), "payee": "Landlord", "narration": "Rent",
        "postings": [{"account": "Expenses:Rent", "units": {"number": "1200", "currency": "USD"}}, {"account": "Assets:Bank", "units": {"number": "-1200", "currency": "USD"}}],
    })
    assert entered.status_code == 201, entered.text
    assert due not in [o["date"] for o in client.get("/ledgers/main/recurring").json()[0]["occurrences"]]


def test_a_varying_bill_needs_its_amount_and_accepts_a_formula(client, home):
    set_item(client, "power", variable=True, to_account="Expenses:Rent", title="Power")
    missing = client.post("/agent/recurring/power/proposal", json={}, headers=AGENT)
    assert missing.status_code == 422 and "varies" in missing.json()["detail"]
    ok = client.post("/agent/recurring/power/proposal", json={"amount": "40.10 + 38.25"}, headers=AGENT)
    assert ok.status_code == 201 and "78.35" in str(ok.json()["operation"])


def test_an_unknown_item_lists_the_known_ones(client, home):
    set_item(client)
    response = client.post("/agent/recurring/rnt/proposal", json={}, headers=AGENT)
    assert response.status_code == 422 and "known: rent" in response.json()["detail"]


def test_suggestions_come_from_the_history_and_the_user_can_adopt_one(client, home):
    client.post("/ledgers/main/accounts", json={"account": "Expenses:Music", "date": "2025-01-01"})
    for months_ago in (3, 2, 1, 0):
        day = add_months(TODAY.replace(day=5), -months_ago)
        client.post("/ledgers/main/transactions", json={
            "date": day.isoformat(), "payee": "Spotify", "narration": "Premium",
            "postings": [{"account": "Expenses:Music", "units": {"number": "9.99", "currency": "USD"}}, {"account": "Assets:Bank", "units": {"number": "-9.99", "currency": "USD"}}],
        })
    suggestions = client.get("/agent/recurring/suggestions", headers=AGENT).json()
    assert [s["id"] for s in suggestions] == ["spotify"] and suggestions[0]["recurring"]["amount"]["number"] == "9.99"
    adopted = client.put("/ledgers/main/recurring/spotify", json=suggestions[0]["recurring"])
    assert adopted.status_code == 200
    assert client.get("/agent/recurring/suggestions", headers=AGENT).json() == []


def test_a_schedule_naming_a_closed_or_missing_account_warns(client, home):
    set_item(client, to_account="Expenses:Nowhere")
    assert any("Expenses:Nowhere is not open" in w for w in client.get("/ledgers/main/profile").json()["warnings"])
