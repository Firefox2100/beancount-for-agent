from integration_test.helpers import lunch

AGENT = {"X-Actor": "agent", "X-Client-Id": "harness-a", "X-Session-Id": "s1"}


def propose(client, ledger, day="2026-02-03", version=None, **overrides):
    version = version or client.get(ledger).json()["version"]
    operation = {"kind": "add_transaction", "transaction": lunch(day, **overrides)}
    return client.post(
        f"{ledger}/changes",
        json={"operation": operation, "note": "from receipt"},
        headers={**AGENT, "If-Match": version},
    )


def transaction_count(client, ledger):
    return client.get(f"{ledger}/transactions").json()["total"]


def test_agent_direct_write_is_refused(client, ledger):
    response = client.post(f"{ledger}/transactions", json=lunch(), headers=AGENT)
    assert response.status_code == 403
    assert transaction_count(client, ledger) == 0


def test_propose_then_approve(client, ledger):
    response = propose(client, ledger)
    assert response.status_code == 201
    change = response.json()
    assert change["status"] == "pending" and change["caller"]["client_id"] == "harness-a"
    assert transaction_count(client, ledger) == 0

    listed = client.get(f"{ledger}/changes", params={"status": "pending"}).json()
    assert [c["id"] for c in listed] == [change["id"]]

    approved = client.post(f"{ledger}/changes/{change['id']}/approve", json={})
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved" and approved.json()["result_version"]
    assert transaction_count(client, ledger) == 1
    assert client.post(f"{ledger}/changes/{change['id']}/approve", json={}).status_code == 409


def test_reject_and_withdraw(client, ledger):
    first = propose(client, ledger).json()
    second = propose(client, ledger).json()
    rejected = client.post(f"{ledger}/changes/{first['id']}/reject", json={"note": "wrong"})
    assert rejected.json()["status"] == "rejected" and rejected.json()["resolution_note"] == "wrong"
    assert client.post(f"{ledger}/changes/{second['id']}/withdraw", json={}).json()["status"] == "withdrawn"
    assert client.post(f"{ledger}/changes/{first['id']}/approve", json={}).status_code == 409
    assert transaction_count(client, ledger) == 0


def test_submission_needs_latest_version(client, ledger):
    stale = client.get(ledger).json()["version"]
    client.post(f"{ledger}/transactions", json=lunch())
    assert propose(client, ledger, version=stale).status_code == 412
    missing = client.post(
        f"{ledger}/changes",
        json={"operation": {"kind": "add_transaction", "transaction": lunch()}},
        headers=AGENT,
    )
    assert missing.status_code == 428


def test_invalid_change_is_refused_at_submission(client, ledger):
    bad = propose(client, ledger, postings=[
        {"account": "Assets:Bank", "units": {"number": "-5", "currency": "USD"}},
        {"account": "Expenses:Food", "units": {"number": "4", "currency": "USD"}},
    ])
    assert bad.status_code == 422
    assert client.get(f"{ledger}/changes").json() == []


def test_independent_changes_both_approve(client, ledger):
    first = propose(client, ledger, narration="One").json()
    second = propose(client, ledger, narration="Two").json()
    assert client.post(f"{ledger}/changes/{first['id']}/approve", json={}).status_code == 200
    assert client.post(f"{ledger}/changes/{second['id']}/approve", json={}).status_code == 200
    assert transaction_count(client, ledger) == 2


def test_approval_fails_when_target_changed(client, ledger):
    created = client.post(f"{ledger}/transactions", json=lunch()).json()["transaction"]
    version = client.get(ledger).json()["version"]
    proposed = client.post(
        f"{ledger}/changes",
        json={"operation": {"kind": "delete_transaction", "id": created["id"]}},
        headers={**AGENT, "If-Match": version},
    ).json()
    client.put(f"{ledger}/transactions/{created['id']}", json=lunch(narration="Edited by human"))
    response = client.post(f"{ledger}/changes/{proposed['id']}/approve", json={})
    assert response.status_code == 409
    assert transaction_count(client, ledger) == 1
    assert client.get(f"{ledger}/changes/{proposed['id']}").json()["status"] == "pending"


def test_approval_revalidates_against_current_state(client, ledger):
    change = propose(client, ledger, "2026-07-01").json()
    client.post(f"{ledger}/accounts/Expenses:Food/close", json={"date": "2026-06-01"})
    response = client.post(f"{ledger}/changes/{change['id']}/approve", json={})
    assert response.status_code == 422
    assert transaction_count(client, ledger) == 0


def test_amend_before_approval(client, ledger):
    change = propose(client, ledger, narration="Draft").json()
    amended = client.put(
        f"{ledger}/changes/{change['id']}",
        json={"operation": {"kind": "add_transaction", "transaction": lunch(narration="Final")}},
    )
    assert amended.status_code == 200
    client.post(f"{ledger}/changes/{change['id']}/approve", json={})
    assert client.get(f"{ledger}/transactions").json()["items"][0]["narration"] == "Final"


def test_agent_changes_apply_at_once_when_approval_disabled(tmp_path):
    from fastapi.testclient import TestClient

    from beancount_mcp.api.app import create_app
    from beancount_mcp.config import Settings

    client = TestClient(create_app(Settings(data_dir=tmp_path / "d", agent_approval_required=False)))
    client.post("/ledgers", json={"id": "m"})
    for account in ("Assets:Bank", "Expenses:Food"):
        client.post("/ledgers/m/accounts", json={"account": account, "date": "2026-01-01"})
    version = client.get("/ledgers/m").json()["version"]
    change = client.post(
        "/ledgers/m/changes",
        json={"operation": {"kind": "add_transaction", "transaction": lunch()}},
        headers={**AGENT, "If-Match": version},
    ).json()
    assert change["status"] == "approved"
    assert client.get("/ledgers/m/transactions").json()["total"] == 1
