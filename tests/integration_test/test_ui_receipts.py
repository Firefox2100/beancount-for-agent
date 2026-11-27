import re

from integration_test.helpers import lunch

AGENT = {"X-Actor": "agent", "X-Client-Id": "mcp"}
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 40 + b"lunch"


def csrf_of(page: str) -> str:
    return re.search(r'name="csrf" content="([0-9a-f]+)"', page).group(1)


def followed(client, response):
    assert response.status_code == 303, response.text
    return client.get(response.headers["location"]).text


def test_receipts_are_uploaded_linked_viewed_and_shown_beside_a_proposal(client, ledger):
    page = client.get("/ui/ledgers/main/receipts")
    assert page.status_code == 200 and "No receipts yet." in page.text and "cannot read receipts here" in page.text
    ident = client.post("/ledgers/main/transactions", json=lunch("2026-02-03")).json()["transaction"]["id"]
    assert ident in client.get("/ui/ledgers/main/receipts").text

    sent = client.post("/ui/ledgers/main/receipts", data={"csrf": csrf_of(page.text), "transaction": ident},
                       files={"file": ("lunch.jpg", JPEG)}, follow_redirects=False)
    assert "and linked it." in followed(client, sent)
    listing = client.get("/ui/ledgers/main/receipts").text
    assert "lunch.jpg" in listing and ">linked<" in listing
    path = re.search(r"documents/receipts/\d{4}/[0-9a-f]{10}-lunch\.jpg", listing).group(0)
    shown = client.get("/ui/ledgers/main/receipts/file", params={"path": path})
    assert shown.content == JPEG and shown.headers["content-type"] == "image/jpeg"
    assert client.get("/ui/ledgers/main/receipts/file", params={"path": "../main.beancount"}).status_code == 404

    bad = client.post("/ui/ledgers/main/receipts", data={"csrf": csrf_of(page.text)}, files={"file": ("x.exe", b"MZ")}, follow_redirects=False)
    assert "not a supported receipt" in followed(client, bad)
    assert client.post("/ui/ledgers/main/receipts", data={"csrf": "wrong"}, files={"file": ("a.jpg", JPEG)}).status_code == 403

    proposal = client.post("/agent/expenses", headers=AGENT, json={
        "from_account": "Bank", "expense_account": "Food", "amount": "7 USD", "date": "2026-02-04", "receipt": path.rsplit("/", 1)[-1]})
    assert proposal.status_code == 201, proposal.text
    inbox = client.get("/ui/").text
    assert "Attach receipt" in inbox and 'alt="The receipt"' in inbox
    assert "/ui/ledgers/main/receipts/file?path=documents/receipts/" in inbox
