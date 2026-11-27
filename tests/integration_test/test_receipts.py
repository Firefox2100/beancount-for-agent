import pytest
from beancount import loader
from beancount.core import data
from integration_test.helpers import lunch

from beancount_mcp.models import Layout

AGENT = {"X-Actor": "agent", "X-Client-Id": "mcp"}
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 40 + b"receipt-one"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 40
PDF = b"%PDF-1.4\n" + b"1 0 obj\n" * 3
MAIN = "main.beancount"


def upload(client, content=JPEG, name="Lunch receipt.jpg", headers=None, **fields):
    return client.post("/ledgers/main/receipts", data=fields, files={"file": (name, content, "application/octet-stream")}, headers=headers or {})


def booked(client):
    response = client.post("/ledgers/main/transactions", json=lunch("2026-02-03"))
    assert response.status_code == 201, response.text
    return response.json()["transaction"]["id"]


def load(ledger_dir):
    return loader.load_file(str(ledger_dir / MAIN))


@pytest.mark.parametrize("layout", [Layout.SINGLE, Layout.YEARLY, Layout.MONTHLY])
def test_a_receipt_is_stored_and_linked_to_a_transaction_in_every_layout(make_client, tmp_path, layout):
    client = make_client(layout)
    client.post("/ledgers", json={"id": "main", "operating_currencies": ["USD"]})
    for account in ("Assets:Bank", "Expenses:Food"):
        client.post("/ledgers/main/accounts", json={"account": account, "date": "2026-01-01"})
    ident = booked(client)
    stored = upload(client, transaction=ident)
    assert stored.status_code == 201, stored.text
    receipt = stored.json()
    assert receipt["path"].startswith("documents/receipts/") and receipt["path"].endswith("-Lunch-receipt.jpg")
    assert receipt["kind"] == "image" and receipt["linked"] is True

    ledger_dir = tmp_path / "data" / "main"
    assert (ledger_dir / receipt["path"]).read_bytes() == JPEG
    entries, errors, _ = load(ledger_dir)
    assert errors == []
    document = next(e for e in entries if isinstance(e, data.Document))
    assert document.account == "Assets:Bank" and document.filename == str(ledger_dir / receipt["path"])
    transaction = client.get(f"/ledgers/main/transactions/{ident}").json()
    assert transaction["meta"] == {"document": receipt["path"].rsplit("/", 1)[-1]}
    records = client.get("/ledgers/main/directives", params={"kind": "document"}).json()["items"]
    assert [r["directive"]["path"] for r in records] == [receipt["path"]]


def test_the_same_file_is_kept_once_and_listed_with_whether_it_is_linked(client, ledger):
    first, second = upload(client).json(), upload(client).json()
    assert first["path"] == second["path"] and len(client.get("/ledgers/main/receipts").json()) == 1
    assert client.get("/ledgers/main/receipts").json()[0]["linked"] is False
    ident = booked(client)
    assert client.post("/ledgers/main/receipts/attach", params={"transaction": ident, "path": first["path"]}).status_code == 200
    assert client.get("/ledgers/main/receipts").json()[0]["linked"] is True


def test_a_second_receipt_on_one_transaction_gets_its_own_note(client, ledger, ledger_dir):
    ident = booked(client)
    one, two = upload(client, JPEG).json(), upload(client, PNG, "second.png").json()
    for item in (one, two):
        client.post("/ledgers/main/receipts/attach", params={"transaction": ident, "path": item["path"]})
    meta = client.get(f"/ledgers/main/transactions/{ident}").json()["meta"]
    assert set(meta) == {"document", "document-2"} and load(ledger_dir)[1] == []
    again = client.post("/ledgers/main/receipts/attach", params={"transaction": ident, "path": one["path"]})
    assert again.status_code == 200 and set(client.get(f"/ledgers/main/transactions/{ident}").json()["meta"]) == {"document", "document-2"}


def test_pdf_is_accepted_and_the_type_comes_from_the_content_not_the_name(client, ledger):
    assert upload(client, PDF, "scan.jpg").json()["kind"] == "pdf"
    refused = upload(client, b"MZ not an image", "evil.jpg")
    assert refused.status_code == 422 and "not a supported receipt" in refused.json()["detail"]


def test_a_file_put_in_the_documents_folder_by_hand_is_listed(client, ledger, ledger_dir):
    folder = ledger_dir / "documents" / "taxi"
    folder.mkdir(parents=True)
    (folder / "ride.png").write_bytes(PNG)
    (folder / "notes.txt").write_text("not a receipt")
    listed = client.get("/ledgers/main/receipts").json()
    assert [(r["path"], r["linked"]) for r in listed] == [("documents/taxi/ride.png", False)]


def test_only_the_user_uploads_or_attaches_and_the_file_is_served_safely(client, ledger):
    assert upload(client).status_code == 201
    assert upload(client, headers=AGENT).status_code == 403
    path = upload(client).json()["path"]
    assert client.post("/ledgers/main/receipts/attach", params={"transaction": "x", "path": path}, headers=AGENT).status_code == 403
    served = client.get("/ledgers/main/receipts/file", params={"path": path})
    assert served.content == JPEG and served.headers["content-type"] == "image/jpeg"
    assert served.headers["x-content-type-options"] == "nosniff" and served.headers["content-security-policy"] == "sandbox"


@pytest.mark.parametrize("path", ["../" + MAIN, "documents/../" + MAIN, "/etc/passwd", "documents/nothing.jpg", MAIN, "documents/", "documents//a.jpg"])
def test_only_files_in_the_documents_folder_can_be_read_back(client, ledger, path):
    assert client.get("/ledgers/main/receipts/file", params={"path": path}).status_code == 422


def test_a_document_that_does_not_exist_cannot_be_linked(client, ledger):
    ident = booked(client)
    missing = client.post("/ledgers/main/receipts/attach", params={"transaction": ident, "path": "documents/receipts/2026/none.jpg"})
    assert missing.status_code == 422 and "no receipt at" in missing.json()["detail"]
    ghost = {"kind": "document", "date": "2026-02-03", "account": "Assets:Bank", "path": "documents/ghost.jpg"}
    assert client.post("/ledgers/main/directives", json=ghost).status_code == 422


def test_the_size_limit_is_enforced(tmp_path):
    from fastapi.testclient import TestClient

    from beancount_mcp.api.app import create_app
    from beancount_mcp.config import Settings
    with TestClient(create_app(Settings(data_dir=tmp_path / "d", receipts_max_bytes=50, _env_file=None))) as small:
        small.post("/ledgers", json={"id": "main"})
        response = upload(small)
        assert response.status_code == 422 and "at most 50" in response.json()["detail"]
