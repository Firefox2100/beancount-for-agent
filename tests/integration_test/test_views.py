CARD = "Liabilities:Card:Main"
FRIEND = "Assets:Owed:Friend"
CHECKING = "Assets:Bank:Checking"


def act(client, ledger, account, recipe, params):
    response = client.post(f"{ledger}/accounts/{account}/actions/{recipe}", json=params)
    assert response.status_code == 200, response.text
    return response.json()


def test_open_items_follow_links_until_settled(client, wide_ledger):
    act(client, wide_ledger, CHECKING, "receive", {"from_account": "Income:Salary", "amount": "500"})
    first = act(client, wide_ledger, FRIEND, "lend",
                {"date": "2026-02-01", "counter_account": CHECKING, "amount": "60", "payee": "Sam"})
    act(client, wide_ledger, FRIEND, "lend",
        {"date": "2026-02-02", "counter_account": CHECKING, "amount": "40", "payee": "Alex"})
    link = first["transaction"]["links"][0]

    listing = client.get(f"{wide_ledger}/open-items", params={"account": FRIEND}).json()[0]
    assert [i["payee"] for i in listing["items"]] == ["Sam", "Alex"]
    assert listing["balance"] == {"USD": "100"}

    act(client, wide_ledger, FRIEND, "collect",
        {"date": "2026-02-10", "counter_account": CHECKING, "amount": "60", "link": link})
    listing = client.get(f"{wide_ledger}/open-items", params={"account": FRIEND}).json()[0]
    assert [i["payee"] for i in listing["items"]] == ["Alex"]
    assert listing["items"][0]["balances"] == {"USD": "40"}


def test_unlinked_settlement_is_reported_separately(client, wide_ledger):
    act(client, wide_ledger, FRIEND, "invoice", {"counter_account": "Income:Salary", "amount": "100"})
    act(client, wide_ledger, FRIEND, "collect", {"counter_account": CHECKING, "amount": "30"})
    listing = client.get(f"{wide_ledger}/open-items", params={"account": FRIEND}).json()[0]
    assert listing["unlinked"] == {"USD": "-30"} and listing["balance"] == {"USD": "70"}


def test_open_items_without_account_covers_receivables_and_payables(client, wide_ledger):
    names = {entry["account"] for entry in client.get(f"{wide_ledger}/open-items").json()}
    assert names == {FRIEND, "Liabilities:Payable:Supplier"}
    assert client.get(f"{wide_ledger}/open-items", params={"account": "Assets:Nope"}).status_code == 422


def test_due_shows_balances_dates_and_filters(client, card_ledger):
    card_url = f"{card_ledger}/accounts/{CARD}/actions"
    client.put(f"{card_ledger}/profile", json={"accounts": {
        CARD: {"description": "Main card", "statement_day": 1, "due_day": 20, "autopay_from": "Assets:Bank:Debit"}}})
    assert client.get(f"{card_ledger}/due", params={"today": "2026-03-05"}).json()[0]["owed"] == {}
    assert client.get(f"{card_ledger}/due", params={"today": "2026-03-05", "within_days": 30}).json() == []

    client.post(f"{card_url}/purchase", json={"date": "2026-02-01", "expense_account": "Expenses:Food", "amount": "40 USD"})
    client.post(f"{card_url}/purchase", json={"date": "2026-02-02", "expense_account": "Expenses:Food", "amount": "10 GBP"})
    due = client.get(f"{card_ledger}/due", params={"today": "2026-03-05", "within_days": 30}).json()
    assert len(due) == 1
    item = due[0]
    assert item["owed"] == {"USD": "40"} and item["unbilled"] == {"GBP": "10"}
    assert (item["due_date"], item["days_until_due"], item["next_statement"]) == ("2026-03-20", 15, "2026-04-01")
    assert item["autopay_from"] == "Assets:Bank:Debit"
    assert client.get(f"{card_ledger}/due", params={"today": "2026-03-05", "within_days": 10}).json() == []


def test_pool_converts_with_prices_and_reports_the_rest(client, card_ledger):
    second = "Liabilities:Card:Second"
    client.post(f"{card_ledger}/accounts", json={"account": second, "date": "2026-01-01",
                                                  "currencies": ["USD", "CNY"], "type": "credit_card"})
    client.put(f"{card_ledger}/profile", json={
        "accounts": {CARD: {"pool": "shared"}, second: {"pool": "shared"}},
        "pools": {"shared": {"limit": {"number": "1000", "currency": "USD"}}},
    })
    for account, amount in ((CARD, "100 USD"), (second, "720 CNY")):
        client.post(f"{card_ledger}/accounts/{account}/actions/purchase",
                    json={"date": "2026-02-01", "expense_account": "Expenses:Food", "amount": amount})

    pool = client.get(f"{card_ledger}/pools", params={"today": "2026-03-01"}).json()[0]
    assert pool["used"] == "100.00" and pool["unconverted"] == {"CNY": "720"}

    client.post(f"{card_ledger}/directives", json={
        "kind": "price", "date": "2026-02-15", "currency": "CNY", "amount": {"number": "0.14", "currency": "USD"}})
    pool = client.get(f"{card_ledger}/pools", params={"today": "2026-03-01"}).json()[0]
    assert (pool["used"], pool["available"], pool["unconverted"]) == ("200.80", "799.20", {})
    assert {m["account"] for m in pool["members"]} == {CARD, second}
