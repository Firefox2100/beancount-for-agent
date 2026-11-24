from integration_test.helpers import lunch


def add(client, ledger, directive, **kwargs):
    return client.post(f"{ledger}/directives", json=directive, **kwargs)


def test_balance_assertion_pass_and_fail(client, ledger):
    client.post(f"{ledger}/transactions", json=lunch(amount="10"))
    good = {"kind": "balance", "date": "2026-03-01", "account": "Assets:Bank",
            "amount": {"number": "-10", "currency": "USD"}}
    response = add(client, ledger, good)
    assert response.status_code == 201 and response.json()["record"]["directive"]["kind"] == "balance"

    bad = {**good, "date": "2026-03-02", "amount": {"number": "5", "currency": "USD"}}
    assert add(client, ledger, bad).status_code == 422
    assert client.get(ledger).json()["errors"] == []


def test_reconcile_with_pad(client, ledger):
    client.post(f"{ledger}/accounts", json={"account": "Equity:Opening", "date": "2026-01-01"})
    body = {"date": "2026-01-03", "amount": {"number": "100", "currency": "USD"}, "pad_account": "Equity:Opening"}
    response = client.post(f"{ledger}/accounts/Assets:Bank/reconcile", json=body)
    assert response.status_code == 201
    balances = {b["account"]: b["balances"] for b in client.get(f"{ledger}/balances").json()}
    assert balances["Assets:Bank"] == {"USD": "100"}
    kinds = [r["directive"]["kind"] for r in client.get(f"{ledger}/directives").json()["items"]]
    assert sorted(kinds) == ["balance", "pad"]


def test_reconcile_without_pad_fails_on_mismatch(client, ledger):
    body = {"date": "2026-01-03", "amount": {"number": "100", "currency": "USD"}}
    assert client.post(f"{ledger}/accounts/Assets:Bank/reconcile", json=body).status_code == 422


def test_price_commodity_note_event_roundtrip(client, ledger, ledger_dir):
    directives = [
        {"kind": "commodity", "date": "2026-01-01", "currency": "ABC"},
        {"kind": "price", "date": "2026-02-01", "currency": "ABC", "amount": {"number": "101.5", "currency": "USD"}},
        {"kind": "note", "date": "2026-02-02", "account": "Assets:Bank", "comment": "Called the bank"},
        {"kind": "event", "date": "2026-02-03", "type": "location", "description": "Home"},
    ]
    for directive in directives:
        assert add(client, ledger, directive).status_code == 201
    page = client.get(f"{ledger}/directives").json()
    assert page["total"] == 4
    assert {item["directive"]["kind"] for item in page["items"]} == {"commodity", "price", "note", "event"}
    assert "commodity ABC" in (ledger_dir / "accounts.beancount").read_text()
    assert client.get(f"{ledger}/directives", params={"kind": "price"}).json()["total"] == 1
    assert client.get(ledger).json()["errors"] == []


def test_update_and_delete_directive(client, ledger):
    note = {"kind": "note", "date": "2026-02-02", "account": "Assets:Bank", "comment": "one"}
    record = add(client, ledger, note).json()["record"]
    changed = {**note, "comment": "two"}
    assert client.put(f"{ledger}/directives/{record['id']}", json=changed).json()["record"]["directive"]["comment"] == "two"
    assert client.delete(f"{ledger}/directives/{record['id']}").status_code == 200
    assert client.get(f"{ledger}/directives/{record['id']}").status_code == 404


def test_note_on_unopened_account_rejected(client, ledger):
    note = {"kind": "note", "date": "2026-02-02", "account": "Assets:Missing", "comment": "x"}
    assert add(client, ledger, note).status_code == 422
