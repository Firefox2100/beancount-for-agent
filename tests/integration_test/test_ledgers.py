import pytest

from beancount_mcp.models import Layout


@pytest.mark.parametrize("layout", list(Layout))
def test_create_and_list(tmp_path, make_client, layout):
    client = make_client(layout)
    assert client.get("/ledgers").json() == []

    response = client.post("/ledgers", json={"id": "personal", "operating_currencies": ["USD"]})
    assert response.status_code == 201
    body = response.json()
    assert body["layout"] == layout
    assert body["errors"] == []
    assert (tmp_path / "data/personal/.sidecar/layout.json").is_file()
    assert [item["id"] for item in client.get("/ledgers").json()] == ["personal"]
    assert client.get("/ledgers/personal").json()["version"] == body["version"]


def test_duplicate_and_bad_id(client):
    assert client.post("/ledgers", json={"id": "a"}).status_code == 201
    assert client.post("/ledgers", json={"id": "a"}).status_code == 409
    assert client.post("/ledgers", json={"id": "../x"}).status_code == 422
    assert client.get("/ledgers/missing").status_code == 404


def test_adopts_matching_directory_and_writes_sidecar(tmp_path, client):
    root = tmp_path / "data/copied"
    (root / "transactions").mkdir(parents=True)
    (root / "main.beancount").write_text('include "accounts.beancount"\ninclude "transactions/*.beancount"\n')
    (root / "accounts.beancount").write_text("")
    (root / "transactions/2026.beancount").write_text("")

    assert client.get("/ledgers/copied").status_code == 200
    assert (root / ".sidecar/layout.json").is_file()


def test_rejects_foreign_structure(tmp_path, client):
    root = tmp_path / "data/odd"
    root.mkdir(parents=True)
    (root / "main.beancount").write_text("")
    (root / "extra.beancount").write_text("")
    assert client.get("/ledgers/odd").status_code == 409


def test_sidecar_layout_wins_over_settings(make_client):
    make_client(Layout.SINGLE).post("/ledgers", json={"id": "a"})
    reopened = make_client(Layout.YEARLY).get("/ledgers/a")
    assert reopened.status_code == 200 and reopened.json()["layout"] == "single"


def test_version_changes_with_content(tmp_path, client):
    before = client.post("/ledgers", json={"id": "a"}).json()["version"]
    (tmp_path / "data/a/accounts.beancount").write_text("2026-01-01 open Assets:Cash\n")
    assert client.get("/ledgers/a").json()["version"] != before


def test_adopts_other_layouts_regardless_of_settings(tmp_path, make_client):
    single = tmp_path / "data/imported"
    single.mkdir(parents=True)
    (single / "main.beancount").write_text("2026-01-01 open Assets:Cash\n")
    response = make_client(Layout.MONTHLY).get("/ledgers/imported")
    assert response.status_code == 200
    assert response.json()["layout"] == "single"
