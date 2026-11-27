import datetime as dt

AGENT = {"X-Actor": "agent", "X-Client-Id": "mcp"}


def book(client, day, amount, income=False):
    other = "Assets:Bank"
    postings = [{"account": "Expenses:Food", "units": {"number": amount, "currency": "USD"}}, {"account": other}]
    client.post("/ledgers/main/transactions", json={"date": day, "narration": "x", "postings": postings})


def test_the_income_statement_defaults_to_this_month_and_is_reachable_by_agents(client, ledger):
    today = dt.date.today()
    book(client, today.isoformat(), "12.50")
    book(client, (today.replace(day=1) - dt.timedelta(days=3)).isoformat(), "40")
    report = client.get("/agent/reports/income-statement", headers=AGENT).json()
    assert report["start"] == today.replace(day=1).isoformat() and report["end"] == today.isoformat()
    assert report["expenses"] == [{"account": "Expenses:Food", "totals": {"USD": "12.50"}, "previous": None}]
    assert report["net"] == {"USD": "-12.50"} and report["savings_rate"] is None

    wider = client.get("/ledgers/main/reports/income-statement", params={"start": "2000-01-01", "compare": "true", "interval": "month"}).json()
    assert wider["expense_total"] == {"USD": "52.50"} and wider["periods"] and wider["previous_end"] == "1999-12-31"


def test_group_names_are_matched_loosely_and_bad_input_says_why(client, ledger):
    book(client, "2026-02-03", "10")
    ok = client.get("/agent/reports/income-statement", params={"start": "2026-02-01", "end": "2026-02-28", "account": "Food"}, headers=AGENT)
    assert ok.status_code == 200 and ok.json()["expense_total"] == {"USD": "10"}
    assert client.get("/agent/reports/income-statement", params={"account": "Nonsense"}, headers=AGENT).status_code == 422
    backwards = client.get("/ledgers/main/reports/income-statement", params={"start": "2026-03-01", "end": "2026-02-01"})
    assert backwards.status_code == 422 and "starts after it ends" in backwards.json()["detail"]
