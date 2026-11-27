from pathlib import Path

import pytest
from integration_test.helpers import lunch

SAMPLES = Path(__file__).parents[1] / "samples"
AGENT = {"X-Actor": "agent", "X-Client-Id": "mcp"}


@pytest.fixture
def banked(client, ledger):
    for account in ("Expenses:Rent", "Income:Salary"):
        assert client.post("/ledgers/main/accounts", json={"account": account, "date": "2026-01-01"}).status_code == 201
    return ledger


def upload(client, name="checking.ofx", account="Assets:Bank", headers=None, **fields):
    return client.post(
        "/ledgers/main/imports", data={"account": account, **fields}, headers=headers or {},
        files={"file": (name, (SAMPLES / name).read_bytes(), "application/octet-stream")},
    )


CATEGORIES = {"1": "Food", "2": "Rent", "3": "Salary"}


def test_upload_review_propose_approve_and_the_same_file_is_then_known(client, banked):
    created = upload(client)
    assert created.status_code == 201, created.text
    (summary,) = created.json()
    assert (summary["lines"], summary["new"], summary["format"], summary["warnings"]) == (3, 3, "ofx", [])

    listed = client.get("/agent/imports", headers=AGENT).json()
    assert [i["id"] for i in listed] == [summary["id"]]
    review = client.get(f"/agent/imports/{summary['id']}", headers=AGENT).json()
    assert [(i["number"], i["amount"], i["status"]) for i in review["items"]] == [(1, "-12.50", "new"), (2, "-1234.56", "new"), (3, "2500.00", "new")]

    refused = client.post(f"/agent/imports/{summary['id']}/proposal", json={"categories": {"1": "Food"}}, headers=AGENT)
    assert refused.status_code == 422 and "line 2, 3" in refused.json()["detail"] and "default_account" in refused.json()["detail"]
    assert client.get("/ledgers/main/changes").json() == []

    proposal = client.post(
        f"/agent/imports/{summary['id']}/proposal", json={"categories": CATEGORIES, "assert_balance": True}, headers=AGENT,
    )
    assert proposal.status_code == 201, proposal.text
    assert proposal.json()["note"].startswith("Import checking.ofx: 3 of 3")
    assert client.get("/ledgers/main/transactions").json()["total"] == 0

    approved = client.post(f"/ledgers/main/changes/{proposal.json()['id']}/approve", json={})
    assert approved.status_code == 200, approved.text
    transactions = client.get("/ledgers/main/transactions").json()["items"]
    assert len(transactions) == 3
    rent = next(t for t in transactions if t["payee"] == "Landlord")
    assert rent["meta"]["bank-ref"] == "A2" and [p["account"] for p in rent["postings"]] == ["Assets:Bank", "Expenses:Rent"]
    assert rent["postings"][0]["units"]["number"] == "-1234.56"

    again = client.get(f"/agent/imports/{summary['id']}", headers=AGENT, params={"only_new": False}).json()
    assert {i["status"] for i in again["items"]} == {"imported"} and again["new"] == 0 and again["change_ids"]
    nothing = client.post(f"/agent/imports/{summary['id']}/proposal", json={"default_account": "Food"}, headers=AGENT)
    assert nothing.status_code == 422 and "nothing to import" in nothing.json()["detail"]
    # uploading the file a second time finds everything already there
    assert upload(client).json()[0]["new"] == 0


def test_a_hand_entered_transaction_is_a_possible_duplicate_until_included(client, banked):
    client.post("/ledgers/main/transactions", json=lunch("2026-03-03"))
    (summary,) = upload(client).json()
    assert summary["new"] == 2
    review = client.get(f"/ledgers/main/imports/{summary['id']}").json()
    assert review["items"][0]["status"] == "possible_duplicate" and review["items"][0]["matches"]
    proposal = client.post(
        f"/agent/imports/{summary['id']}/proposal", json={"default_account": "Food", "include": [1]}, headers=AGENT,
    )
    assert proposal.status_code == 201 and "3 of 3" in proposal.json()["note"]
    skipped = client.post(f"/agent/imports/{summary['id']}/proposal", json={"default_account": "Food", "skip": [2]}, headers=AGENT)
    assert skipped.status_code == 201 and "1 of 3" in skipped.json()["note"]


def test_a_line_that_is_not_in_the_statement_is_named(client, banked):
    (summary,) = upload(client).json()
    response = client.post(f"/agent/imports/{summary['id']}/proposal", json={"categories": {"9": "Food"}, "default_account": "Rent"}, headers=AGENT)
    assert response.status_code == 422 and "no line 9" in response.json()["detail"]


def test_only_the_user_uploads_or_deletes(client, banked):
    assert upload(client, headers=AGENT).status_code == 403
    (summary,) = upload(client).json()
    assert client.delete(f"/ledgers/main/imports/{summary['id']}", headers=AGENT).status_code == 403
    assert client.delete(f"/ledgers/main/imports/{summary['id']}").status_code == 204
    assert client.get(f"/ledgers/main/imports/{summary['id']}").status_code == 404
    assert client.get("/ledgers/main/imports").json() == []


@pytest.mark.parametrize("name,fmt", [("checking.camt053.xml", "camt053"), ("checking.mt940", "mt940")])
def test_other_standards_arrive_the_same_way(client, banked, name, fmt):
    (summary,) = upload(client, name).json()
    assert summary["format"] == fmt and summary["lines"] == 3 and summary["warnings"] == []


def test_a_file_that_does_not_fit_the_account_warns(client, banked):
    client.post("/ledgers/main/accounts", json={"account": "Assets:Pounds", "date": "2026-01-01", "currencies": ["GBP"]})
    (summary,) = upload(client, account="Assets:Pounds").json()
    assert "holds GBP" in summary["warnings"][0]


def test_unreadable_unknown_and_oversized_uploads_are_refused_with_a_reason(client, banked):
    assert "not an open account" in upload(client, account="Assets:Nowhere").json()["detail"]
    assert "no importer called" in upload(client, format="nope").json()["detail"]
    page = client.post("/ledgers/main/imports", data={"account": "Assets:Bank"}, files={"file": ("n.txt", b"hello")})
    assert page.status_code == 422 and "no importer recognises" in page.json()["detail"]
    assert [f["id"] for f in client.get("/ledgers/main/import-formats").json()] == ["camt053", "mt940", "ofx"]


def test_the_size_limit_is_enforced(tmp_path):
    from fastapi.testclient import TestClient

    from beancount_mcp.api.app import create_app
    from beancount_mcp.config import Settings
    with TestClient(create_app(Settings(data_dir=tmp_path / "d", import_max_bytes=100, _env_file=None))) as small:
        small.post("/ledgers", json={"id": "main"})
        small.post("/ledgers/main/accounts", json={"account": "Assets:Bank", "date": "2026-01-01"})
        response = upload(small)
        assert response.status_code == 422 and "at most 100" in response.json()["detail"]
