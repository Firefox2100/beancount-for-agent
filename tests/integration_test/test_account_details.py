import asyncio

from fastapi.testclient import TestClient
from fastmcp import Client

from beancount_mcp.api.app import create_app
from beancount_mcp.config import Settings

ACCOUNT = "Assets:Barclays:Current"
FULL = {"bank_name": "Barclays", "sort_code": "201234", "account_number": "12345678", "card_number": "4929 1234 5678 9012",
        "card_expiry": "08/28", "swift_bic": "BARCGB22", "iban": "GB29NWBK60161331926819"}


def open_account(client, details=None):
    client.post("/ledgers", json={"id": "main", "operating_currencies": ["GBP"]})
    body = {"account": ACCOUNT, "date": "2026-01-01", "currencies": ["GBP"], "type": "checking"}
    if details:
        body["details"] = details
    assert client.post("/ledgers/main/accounts", json=body).status_code == 201


def account(client):
    return next(a for a in client.get("/ledgers/main/accounts").json() if a["name"] == ACCOUNT)


def test_details_given_at_opening_are_stored_in_the_ledger(client, ledger_dir):
    open_account(client, FULL)
    text = (ledger_dir / "accounts.beancount").read_text()
    assert 'sort-code: "20-12-34"' in text and 'type: "checking"' in text
    assert account(client)["details"]["card_number"] == "4929123456789012"
    assert client.get("/ledgers/main").json()["errors"] == []


def test_details_can_be_set_changed_and_cleared_later(client, ledger_dir):
    open_account(client)
    url = f"/ledgers/main/accounts/{ACCOUNT}/details"
    done = client.put(url, json={"set": {"bank_name": "Barclays", "sort_code": "201234"}})
    assert done.status_code == 200, done.text
    client.put(url, json={"set": {"sort_code": "201299"}})
    assert account(client)["details"] == {"bank_name": "Barclays", "sort_code": "20-12-99"}
    client.put(url, json={"clear": ["sort_code"]})
    assert account(client)["details"] == {"bank_name": "Barclays"}
    assert account(client)["type"] == "checking" and account(client)["currencies"] == ["GBP"]
    text = (ledger_dir / "accounts.beancount").read_text()
    assert text.count(f"open {ACCOUNT}") == 1 and "sort-code" not in text
    assert client.get("/ledgers/main").json()["errors"] == []


def test_agents_cannot_set_details_and_bad_values_are_refused(client):
    open_account(client)
    url = f"/ledgers/main/accounts/{ACCOUNT}/details"
    assert client.put(url, json={"set": {"bank_name": "x"}}, headers={"X-Actor": "agent"}).status_code == 403
    assert client.put(url, json={"set": {"card_number": "12"}}).status_code == 422
    assert client.put(url, json={"set": {"cvv": "123"}}).status_code == 422
    assert account(client)["details"] == {}


def test_agents_see_the_sensitive_fields_masked(tmp_path):
    app = create_app(Settings(data_dir=tmp_path / "data", mcp_enabled=True))
    client = TestClient(app)
    open_account(client, FULL)

    async def main():
        async with Client(app.state.mcp) as mcp:
            return (await mcp.call_tool("list_accounts", {})).structured_content

    shown = str(asyncio.run(main()))
    assert "Barclays" in shown and "BARCGB22" in shown
    assert "••••5678" in shown and "••••9012" in shown
    for secret in ("12345678", "4929123456789012", "GB29NWBK60161331926819", "20-12-34"):
        assert secret not in shown
    assert account(client)["details"]["account_number"] == "12345678"
