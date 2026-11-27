import re

import pytest
from fastapi.testclient import TestClient
from integration_test.helpers import lunch

from beancount_mcp.api.app import create_app
from beancount_mcp.config import Settings

AGENT = {"X-Actor": "agent", "X-Client-Id": "mcp"}
TOKEN = "s3cret-token"


def csrf_of(page: str) -> str:
    return re.search(r'name="csrf" content="([0-9a-f]+)"', page).group(1)


def propose(client, ledger="/ledgers/main", **overrides):
    version = client.get(ledger).json()["version"]
    operation = {"kind": "add_transaction", "transaction": lunch("2026-02-03", **overrides)}
    response = client.post(f"{ledger}/changes", json={"operation": operation, "note": "from receipt"},
                           headers={**AGENT, "If-Match": version})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def post(client, path, **fields):
    page = client.get("/ui/")
    return client.post(path, data={"csrf": csrf_of(page.text), **fields}, follow_redirects=False)


def followed(client, response):
    assert response.status_code == 303, response.text
    return client.get(response.headers["location"]).text


def test_inbox_shows_the_exact_postings_and_approving_commits(client, ledger):
    change_id = propose(client)
    page = client.get("/ui/").text
    assert "Waiting for your approval" in page and "from receipt" in page
    assert "Expenses:Food" in page and "Assets:Bank" in page
    assert client.get(f"{ledger}/transactions").json()["total"] == 0

    done = post(client, f"/ui/ledgers/main/changes/{change_id}/approve", note="ok")
    assert "Approved" in followed(client, done)
    assert client.get(f"{ledger}/transactions").json()["total"] == 1
    assert "Waiting for your approval" in client.get("/ui/").text and "Nothing waiting." in client.get("/ui/").text
    history = client.get("/ui/ledgers/main/history").text
    assert "approved" in history and "Lunch" in history


def test_rejecting_leaves_the_ledger_alone(client, ledger):
    change_id = propose(client)
    done = post(client, f"/ui/ledgers/main/changes/{change_id}/reject", note="wrong")
    assert "Rejected" in followed(client, done)
    assert client.get(f"{ledger}/transactions").json()["total"] == 0
    assert "rejected" in client.get("/ui/ledgers/main/history").text


def test_a_conflict_is_shown_as_an_error(client, ledger):
    change_id = propose(client)
    client.post(f"/ui/ledgers/main/changes/{change_id}/approve", data={})  # no form token: refused
    assert post(client, f"/ui/ledgers/main/changes/{change_id}/approve").status_code == 303
    again = followed(client, post(client, f"/ui/ledgers/main/changes/{change_id}/approve"))
    assert "Could not approve" in again and 'class="flash error"' in again


def test_forms_need_the_page_token_and_the_same_origin(client, ledger):
    change_id = propose(client)
    url = f"/ui/ledgers/main/changes/{change_id}/approve"
    assert client.post(url, data={}, follow_redirects=False).status_code == 403
    assert client.post(url, data={"csrf": "x" * 64}, follow_redirects=False).status_code == 403
    token = csrf_of(client.get("/ui/").text)
    cross = client.post(url, data={"csrf": token}, headers={"Origin": "http://evil.example"}, follow_redirects=False)
    assert cross.status_code == 403
    assert client.get(f"{ledger}/transactions").json()["total"] == 0


def test_bank_details_are_edited_in_full_and_validated(client, ledger):
    account = "Assets:Bank"
    page = client.get(f"/ui/ledgers/main/accounts/{account}").text
    assert "Bank details" in page and "Sort code" in page
    done = post(client, f"/ui/ledgers/main/accounts/{account}/details",
                bank_name="Barclays", sort_code="20 12 34", account_number="12345678", card_expiry="8/28")
    assert "saved" in followed(client, done)
    shown = client.get(f"/ui/ledgers/main/accounts/{account}").text
    assert 'value="20-12-34"' in shown and 'value="12345678"' in shown and 'value="08/28"' in shown
    info = next(a for a in client.get(f"{ledger}/accounts").json() if a["name"] == account)
    assert info["details"]["bank_name"] == "Barclays"

    bad = followed(client, post(client, f"/ui/ledgers/main/accounts/{account}/details", bank_name="Barclays", sort_code="12"))
    assert 'class="flash error"' in bad
    cleared = post(client, f"/ui/ledgers/main/accounts/{account}/details", bank_name="Barclays", sort_code="20 12 34")
    followed(client, cleared)
    info = next(a for a in client.get(f"{ledger}/accounts").json() if a["name"] == account)
    assert set(info["details"]) == {"bank_name", "sort_code"}
    assert client.get(ledger).json()["errors"] == []


def test_profile_and_pools_are_saved_through_forms(client, ledger):
    pools = followed(client, post(client, "/ui/ledgers/main/pools", name0="family", limit0="5000", currency0="gbp"))
    assert "Pools saved" in pools and 'value="family"' in pools
    account = "Assets:Bank"
    done = post(client, f"/ui/ledgers/main/accounts/{account}/profile",
                description="Everyday account", statement_day="3", due_day="20", pool="family",
                profile_version=client.get(f"{ledger}/profile").json()["version"])
    assert "Profile saved" in followed(client, done)
    saved = client.get(f"{ledger}/profile").json()["profile"]
    assert saved["accounts"][account]["description"] == "Everyday account"
    assert saved["accounts"][account]["statement_day"] == 3
    assert saved["pools"]["family"]["limit"] == {"number": "5000", "currency": "GBP"}

    bad = followed(client, post(client, f"/ui/ledgers/main/accounts/{account}/profile", statement_day="40",
                                profile_version=client.get(f"{ledger}/profile").json()["version"]))
    assert 'class="flash error"' in bad


def test_unknown_account_is_404(client, ledger):
    assert client.get("/ui/ledgers/main/accounts/Assets:Nope").status_code == 404


@pytest.fixture
def secured(tmp_path):
    app = create_app(Settings(data_dir=tmp_path / "data", auth_token=TOKEN))
    client = TestClient(app)
    auth = {"Authorization": f"Bearer {TOKEN}"}
    client.post("/ledgers", json={"id": "main", "operating_currencies": ["USD"]}, headers=auth)
    return client, auth


def test_the_interface_asks_for_the_token_and_keeps_a_session(secured):
    client, auth = secured
    first = client.get("/ui/", follow_redirects=False)
    assert first.status_code == 303 and first.headers["location"].startswith("/ui/login")
    assert client.get("/ui/login").status_code == 200
    # The API token alone does not open the interface, and the interface session does not open the API.
    assert client.get("/ui/", headers=auth, follow_redirects=False).status_code == 303

    refused = client.post("/ui/login", data={"token": "wrong"})
    assert refused.status_code == 401 and "not the service token" in refused.text

    accepted = client.post("/ui/login", data={"token": TOKEN, "next": "/ui/"}, follow_redirects=False)
    assert accepted.status_code == 303 and accepted.headers["location"] == "/ui/"
    cookie = accepted.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=strict" in cookie and TOKEN not in cookie
    assert client.get("/ui/").status_code == 200
    assert client.get("/ledgers").status_code == 401


def test_login_never_redirects_off_site(secured):
    client, _ = secured
    for target in ("https://evil.example/", "//evil.example/"):
        response = client.post("/ui/login", data={"token": TOKEN, "next": target}, follow_redirects=False)
        assert response.headers["location"] == "/ui/"


def test_signing_out_ends_the_session(secured):
    client, _ = secured
    client.post("/ui/login", data={"token": TOKEN})
    page = client.get("/ui/").text
    out = client.post("/ui/logout", data={"csrf": csrf_of(page)}, follow_redirects=False)
    assert out.status_code == 303
    assert client.get("/ui/", follow_redirects=False).status_code == 303


def test_a_forged_session_is_refused(secured):
    client, _ = secured
    client.cookies.set("bm_session", "9999999999.abcd.deadbeef", path="/ui")
    assert client.get("/ui/", follow_redirects=False).status_code == 303


def test_overview_shows_accounts_balances_and_the_position(client, ledger):
    change_id = propose(client, amount="1234567.80")
    post(client, f"/ui/ledgers/main/changes/{change_id}/approve")
    page = client.get("/ui/ledgers/main/overview")
    assert page.status_code == 200
    for text in ("Financial position", "Accounts", "Assets", "Expenses"):
        assert text in page.text
    assert "1,234,567.80" in page.text and "1234567.80" not in page.text
    assert "Overview" in client.get("/ui/").text


def test_overview_needs_a_session_when_a_token_is_set(tmp_path):
    from fastapi.testclient import TestClient
    app = create_app(Settings(data_dir=tmp_path, auth_token=TOKEN, _env_file=None))
    with TestClient(app) as bare:
        response = bare.get("/ui/ledgers/main/overview", follow_redirects=False)
        assert response.status_code == 303 and "/ui/login" in response.headers["location"]
