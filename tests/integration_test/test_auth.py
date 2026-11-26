from fastapi.testclient import TestClient

from beancount_mcp.api.app import create_app
from beancount_mcp.config import Settings

INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}}
ACCEPT = {"Accept": "application/json, text/event-stream"}


def secured(tmp_path):
    return create_app(Settings(data_dir=tmp_path / "data", mcp_enabled=True, auth_token="s3cret"))


def test_requests_without_the_token_are_refused(tmp_path):
    with TestClient(secured(tmp_path)) as client:
        for response in (client.get("/ledgers"), client.post("/mcp", json=INIT, headers=ACCEPT),
                         client.get("/ledgers", headers={"Authorization": "Bearer wrong"}),
                         client.get("/ledgers", headers={"Authorization": "Basic s3cret"})):
            assert response.status_code == 401
            assert response.headers["www-authenticate"] == "Bearer"


def test_the_token_opens_both_api_and_mcp(tmp_path):
    with TestClient(secured(tmp_path), headers={"Authorization": "Bearer s3cret"}) as client:
        assert client.get("/ledgers").status_code == 200
        assert client.post("/mcp", json=INIT, headers=ACCEPT).status_code == 200


def test_no_token_configured_means_open(tmp_path):
    assert TestClient(create_app(Settings(data_dir=tmp_path / "data"))).get("/ledgers").status_code == 200


def test_the_token_is_never_printed(tmp_path):
    assert "s3cret" not in repr(Settings(auth_token="s3cret"))


def test_a_blank_token_does_not_open_a_back_door(tmp_path):
    assert Settings(auth_token="  ").auth_token is None
