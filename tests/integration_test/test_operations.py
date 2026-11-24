from integration_test.helpers import lunch


def post(client, ledger, **kwargs):
    return client.post(f"{ledger}/transactions", **kwargs)


def test_add_and_read_transaction(client, ledger, ledger_dir):
    response = post(client, ledger, json=lunch())
    assert response.status_code == 201
    created = response.json()["transaction"]
    assert created["payee"] == "Cafe" and created["tags"] == ["trip"]
    assert created["postings"][1]["units"] == {"number": "12.50", "currency": "USD"}

    assert (ledger_dir / "transactions/2026.beancount").read_text().count("Cafe") == 1
    fetched = client.get(f"{ledger}/transactions/{created['id']}").json()
    assert fetched == created
    assert client.get(f"{ledger}").json()["errors"] == []


def test_filters_and_pages(client, ledger):
    post(client, ledger, json=lunch("2026-02-03"))
    post(client, ledger, json=lunch("2026-03-04", narration="Dinner", payee="Bistro"))
    page = client.get(f"{ledger}/transactions", params={"start": "2026-03-01"}).json()
    assert page["total"] == 1 and page["items"][0]["payee"] == "Bistro"
    assert client.get(f"{ledger}/transactions", params={"text": "lunch"}).json()["total"] == 1
    assert client.get(f"{ledger}/transactions", params={"account": "Expenses"}).json()["total"] == 2
    assert client.get(f"{ledger}/transactions", params={"limit": 1}).json()["total"] == 2


def test_balances(client, ledger):
    post(client, ledger, json=lunch(amount="12.50"))
    post(client, ledger, json=lunch("2026-03-04", amount="7.50"))
    balances = {b["account"]: b["balances"] for b in client.get(f"{ledger}/balances").json()}
    assert balances["Assets:Bank"] == {"USD": "-20.00"}
    as_of = client.get(f"{ledger}/balances", params={"as_of": "2026-02-28"}).json()
    assert {b["account"]: b["balances"] for b in as_of}["Expenses:Food"] == {"USD": "12.50"}


def test_unbalanced_and_unopened_rejected_without_writing(client, ledger, ledger_dir):
    before = client.get(ledger).json()["version"]
    unbalanced = lunch(postings=[
        {"account": "Assets:Bank", "units": {"number": "-5", "currency": "USD"}},
        {"account": "Expenses:Food", "units": {"number": "4", "currency": "USD"}},
    ])
    response = post(client, ledger, json=unbalanced)
    assert response.status_code == 422 and response.json()["errors"]

    unopened = lunch(postings=[
        {"account": "Assets:Bank", "units": {"number": "-5", "currency": "USD"}},
        {"account": "Expenses:Nope"},
    ])
    assert post(client, ledger, json=unopened).status_code == 422
    assert client.get(ledger).json()["version"] == before


def test_update_moves_between_files_and_keeps_id(client, ledger, ledger_dir):
    created = post(client, ledger, json=lunch("2026-02-03")).json()["transaction"]
    response = client.put(f"{ledger}/transactions/{created['id']}", json=lunch("2027-01-05", narration="Moved"))
    assert response.status_code == 200
    assert response.json()["transaction"]["id"] == created["id"]
    assert "Cafe" not in (ledger_dir / "transactions/2026.beancount").read_text()
    assert "Moved" in (ledger_dir / "transactions/2027.beancount").read_text()


def test_update_in_place_preserves_neighbours(client, ledger, ledger_dir):
    first = post(client, ledger, json=lunch(narration="First")).json()["transaction"]
    post(client, ledger, json=lunch(narration="Second"))
    path = ledger_dir / "transactions/2026.beancount"
    path.write_text("; hand-written note\n" + path.read_text())
    client.put(f"{ledger}/transactions/{first['id']}", json=lunch(narration="Changed"))
    text = path.read_text()
    assert "; hand-written note" in text and "Changed" in text and "Second" in text
    assert "First" not in text


def test_delete(client, ledger):
    created = post(client, ledger, json=lunch()).json()["transaction"]
    assert client.delete(f"{ledger}/transactions/{created['id']}").status_code == 200
    assert client.get(f"{ledger}/transactions/{created['id']}").status_code == 404
    assert client.delete(f"{ledger}/transactions/{created['id']}").status_code == 404
    assert client.get(ledger).json()["errors"] == []


def test_stale_version_rejected(client, ledger):
    version = client.get(ledger).json()["version"]
    assert post(client, ledger, json=lunch(), headers={"If-Match": version}).status_code == 201
    assert post(client, ledger, json=lunch(), headers={"If-Match": version}).status_code == 412


def test_close_account_and_reject_later_use(client, ledger):
    assert client.post(f"{ledger}/accounts/Expenses:Food/close", json={"date": "2026-06-01"}).status_code == 200
    accounts = {a["name"]: a for a in client.get(f"{ledger}/accounts").json()}
    assert accounts["Expenses:Food"]["close_date"] == "2026-06-01"
    assert post(client, ledger, json=lunch("2026-07-01")).status_code == 422


def test_open_account_twice_rejected(client, ledger):
    response = client.post(f"{ledger}/accounts", json={"account": "Assets:Bank", "date": "2026-01-02"})
    assert response.status_code == 422


def test_quotes_and_injection_are_contained(client, ledger, ledger_dir):
    assert post(client, ledger, json=lunch(narration='say "hi"\n2026-01-01 open Assets:Evil')).status_code == 422
    assert post(client, ledger, json=lunch(narration='say "hi" \\ ok')).status_code == 201
    assert "Evil" not in (ledger_dir / "transactions/2026.beancount").read_text()
    names = {a["name"] for a in client.get(f"{ledger}/accounts").json()}
    assert "Assets:Evil" not in names


def test_cost_and_price(client, ledger):
    client.post(f"{ledger}/accounts", json={"account": "Assets:Broker", "date": "2026-01-01"})
    buy = lunch(
        narration="Buy",
        postings=[
            {"account": "Assets:Broker", "units": {"number": "3", "currency": "ABC"},
             "cost": {"number": "100", "currency": "USD"}},
            {"account": "Assets:Bank", "units": {"number": "-300", "currency": "USD"}},
        ],
    )
    response = post(client, ledger, json=buy)
    assert response.status_code == 201
    assert response.json()["transaction"]["postings"][0]["cost"]["number"] == "100"


def test_single_layout_writes_into_main(make_client, tmp_path):
    from beancount_mcp.models import Layout

    client = make_client(Layout.SINGLE)
    client.post("/ledgers", json={"id": "solo"})
    client.post("/ledgers/solo/accounts", json={"account": "Assets:Bank", "date": "2026-01-01"})
    client.post("/ledgers/solo/accounts", json={"account": "Expenses:Food", "date": "2026-01-01"})
    assert client.post("/ledgers/solo/transactions", json=lunch()).status_code == 201
    assert "Cafe" in (tmp_path / "data/solo/main.beancount").read_text()
    assert client.get("/ledgers/solo").json()["errors"] == []
