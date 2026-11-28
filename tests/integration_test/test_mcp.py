import asyncio

import pytest
from fastapi.testclient import TestClient
from fastmcp import Client
from fastmcp.exceptions import ToolError

from beancount_mcp.api.app import create_app
from beancount_mcp.config import Settings


def build(tmp_path, **settings):
    return create_app(Settings(data_dir=tmp_path / "data", mcp_enabled=True, **settings))


def run(app, steps):
    """Run `steps(call)` against the app's MCP server, with `call(tool, **args)` returning data."""

    async def main():
        async with Client(app.state.mcp) as client:
            async def call(tool, **args):
                result = await client.call_tool(tool, args)
                return result.data if result.structured_content is None else result.structured_content.get("result", result.structured_content)

            return await steps(call, client)

    return asyncio.run(main())


def test_mcp_is_off_unless_enabled(tmp_path):
    app = create_app(Settings(data_dir=tmp_path / "data"))
    assert app.state.mcp is None
    assert TestClient(app).post("/mcp", json={}).status_code == 404


def test_mcp_endpoint_is_mounted_beside_the_api(tmp_path):
    app = build(tmp_path)
    with TestClient(app) as client:
        assert client.get("/ledgers").status_code == 200
        response = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize",
                  "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}},
            headers={"Accept": "application/json, text/event-stream"},
        )
        assert response.status_code == 200 and "beancount" in response.text


def test_tool_set_is_curated(tmp_path):
    async def steps(call, client):
        return {tool.name for tool in await client.list_tools()}

    names = run(build(tmp_path), steps)
    assert {"record_expense", "list_recipes", "perform_recipe", "get_due", "get_financial_position", "reconcile_account", "list_imports", "get_import", "propose_import", "get_recurring", "suggest_recurring", "record_recurring", "get_income_statement", "get_budgets", "suggest_budgets", "get_goals", "get_checks", "get_setup", "preview_recipe", "propose_setup"} <= names
    assert not {"approve_change", "propose_transaction", "read_file", "write_file"} & names


def test_raw_transactions_are_opt_in(tmp_path):
    async def steps(call, client):
        return {tool.name for tool in await client.list_tools()}

    assert "propose_transaction" in run(build(tmp_path, mcp_raw_transactions=True), steps)


def test_agent_workflow_proposes_and_user_approves(tmp_path):
    app = build(tmp_path)

    async def steps(call, client):
        await call("create_ledger", id="home", operating_currencies=["USD"])
        for account, kind in (("Assets:Bank", "checking"), ("Expenses:Food", None)):
            proposal = await call("open_account", account=account, type=kind, currencies=["USD"] if kind else [], date="2026-01-01")
            assert proposal["status"] == "pending"
        return [p["id"] for p in await call("list_my_proposals")]

    ids = run(app, steps)
    api = TestClient(app)
    assert len(ids) == 2
    for change_id in ids:
        assert api.post(f"/ledgers/home/changes/{change_id}/approve", json={}).status_code == 200

    async def more(call, client):
        accounts = {a["name"]: a for a in await call("list_accounts")}
        assert "spend" in accounts["Assets:Bank"]["recipes"]
        proposal = await call("record_expense", from_account="Assets:Bank", expense_account="Expenses:Food",
                              amount="12.50", narration="Lunch", date="2026-02-01")
        assert proposal["source"]["recipe"] == "spend"
        return proposal["id"]

    change = run(app, more)
    assert api.get("/ledgers/home/balances").json() == []
    assert api.post(f"/ledgers/home/changes/{change}/approve", json={}).status_code == 200
    balances = {b["account"]: b["balances"] for b in api.get("/ledgers/home/balances").json()}
    assert balances["Expenses:Food"] == {"USD": "12.50"}


def test_unknown_account_gives_a_readable_error(tmp_path):
    app = build(tmp_path)

    async def steps(call, client):
        await call("create_ledger", id="home")
        with pytest.raises(ToolError, match="no open account matches"):
            await call("record_expense", from_account="Assets:Nope", expense_account="Expenses:Food", amount="1 USD")

    run(app, steps)


def test_ledger_must_be_named_when_several_exist(tmp_path):
    app = build(tmp_path)

    async def steps(call, client):
        await call("create_ledger", id="one")
        assert await call("list_accounts") == []
        await call("create_ledger", id="two")
        with pytest.raises(ToolError, match="name the ledger"):
            await call("list_accounts")

    run(app, steps)


def test_proposals_are_private_to_their_client_and_can_be_withdrawn(tmp_path):
    app = build(tmp_path)

    async def steps(call, client):
        await call("create_ledger", id="home")
        proposal = await call("open_account", account="Assets:Bank")
        withdrawn = await call("withdraw_proposal", change_id=proposal["id"])
        assert withdrawn["status"] == "withdrawn"
        assert await call("list_my_proposals") == []

    run(app, steps)


def test_invalid_recipe_is_refused_before_it_is_proposed(tmp_path):
    app = build(tmp_path)

    async def steps(call, client):
        await call("create_ledger", id="home")
        await call("open_account", account="Assets:Bank", type="checking", currencies=["USD"])
        with pytest.raises(ToolError):
            await call("perform_recipe", account="Assets:Bank", recipe="spend", params={"amount": "1"})

    run(app, steps)


def test_tools_carry_groups_annotations_and_a_consistent_ledger_argument(tmp_path):
    async def steps(call, client):
        return await client.list_tools()

    tools = {tool.name: tool for tool in run(build(tmp_path, mcp_raw_transactions=True), steps)}
    groups = {name: set(tool.meta["fastmcp"]["tags"]) for name, tool in tools.items()}
    assert groups["get_balances"] == {"read"} and tools["get_balances"].annotations.read_only_hint is True
    assert groups["record_expense"] == {"propose"} and tools["record_expense"].annotations.read_only_hint is False
    assert groups["perform_recipe"] == {"recipe", "propose"}
    assert groups["create_ledger"] == {"admin"} and groups["propose_transaction"] >= {"raw"}
    assert all(tool.annotations.destructive_hint is False for tool in tools.values())

    without_ledger = {"list_ledgers", "create_ledger", "list_account_types"}
    for name, tool in tools.items():
        properties, required = tool.input_schema["properties"], tool.input_schema.get("required", [])
        if name not in without_ledger:
            assert "ledger" in properties and "ledger" not in required, name
        assert "version" not in properties and "actor" not in properties, name


def set_up_home(call):
    async def go():
        await call("create_ledger", id="home", operating_currencies=["USD"])
        for account, kind in (("Assets:Bank:Checking", "checking"), ("Expenses:Food", None), ("Income:Food", None),
                              ("Income:Salary", None), ("Assets:Cash", "cash")):
            await call("open_account", account=account, type=kind, currencies=["USD"], date="2026-01-01")

    return go()


def approve_all(app):
    api = TestClient(app)
    for change in api.get("/ledgers/home/changes").json():
        assert api.post(f"/ledgers/home/changes/{change['id']}/approve", json={}).status_code == 200


def test_loose_account_names_are_understood(tmp_path):
    app = build(tmp_path)
    run(app, lambda call, client: set_up_home(call))
    approve_all(app)

    async def steps(call, client):
        proposal = await call("record_expense", from_account="checking", expense_account="food", amount="9")
        assert proposal["source"]["account"] == "Assets:Bank:Checking"
        assert proposal["source"]["params"]["expense_account"] == "Expenses:Food"
        salary = await call("perform_recipe", account="bank checking", recipe="salary",
                            params={"income_account": "salary", "gross": "100"})
        assert salary["source"]["params"]["income_account"] == "Income:Salary"
        assert [a["account"] for a in await call("get_balances", account="Assets")] == []

    run(app, steps)


def test_ambiguous_and_unknown_accounts_say_what_to_use(tmp_path):
    app = build(tmp_path)
    run(app, lambda call, client: set_up_home(call))
    approve_all(app)

    async def steps(call, client):
        with pytest.raises(ToolError, match="several accounts"):
            await call("get_balances", account="food")
        with pytest.raises(ToolError, match="Did you mean"):
            await call("record_expense", from_account="Assets:Bank:Chekcing", expense_account="food", amount="1")

    run(app, steps)


def test_closing_an_account_is_proposed(tmp_path):
    app = build(tmp_path)

    async def steps(call, client):
        await call("create_ledger", id="home")
        opened = await call("open_account", account="Assets:Bank", date="2026-01-01")
        TestClient(app).post(f"/ledgers/home/changes/{opened['id']}/approve", json={})
        return await call("close_account", account="Assets:Bank", date="2026-02-01")

    proposal = run(app, steps)
    assert proposal["status"] == "pending" and proposal["operation"]["kind"] == "close_account"


def test_a_recorded_transaction_can_be_corrected_or_removed_by_proposal(tmp_path):
    app = build(tmp_path)
    api = TestClient(app)

    async def setup(call, client):
        await call("create_ledger", id="home", operating_currencies=["USD"])
        for account, kind in (("Assets:Bank", "checking"), ("Expenses:Food", None)):
            opened = await call("open_account", account=account, type=kind, currencies=["USD"] if kind else [], date="2026-01-01")
            api.post(f"/ledgers/home/changes/{opened['id']}/approve", json={})
        for day in ("2026-02-02", "2026-02-03"):
            spent = await call("record_expense", from_account="Assets:Bank", expense_account="Expenses:Food",
                               amount="12.50", date=day, payee="Cafe", narration="Lunch")
            api.post(f"/ledgers/home/changes/{spent['id']}/approve", json={})
        return [t["id"] for t in await call("search_transactions")]

    first, second = run(app, setup)

    async def amend(call, client):
        with pytest.raises(ToolError, match="say what to change"):
            await call("amend_transaction", transaction_id=first)
        with pytest.raises(ToolError):
            await call("amend_transaction", transaction_id="nope", narration="x")
        moved = await call("amend_transaction", transaction_id=first, date="2026-02-01", payee="", narration="Brunch")
        removed = await call("delete_transaction", transaction_id=second)
        return moved, removed

    moved, removed = run(app, amend)
    assert moved["status"] == "pending" and removed["status"] == "pending"
    # Nothing changes until the user approves.
    assert api.get("/ledgers/home/transactions").json()["total"] == 2
    for change in (moved, removed):
        assert api.post(f"/ledgers/home/changes/{change['id']}/approve", json={}).status_code == 200
    items = api.get("/ledgers/home/transactions").json()["items"]
    assert len(items) == 1
    assert items[0]["date"] == "2026-02-01" and items[0]["narration"] == "Brunch" and items[0]["payee"] is None
    assert [p["units"]["number"] for p in items[0]["postings"]] == ["12.50", "-12.50"]
    assert api.get("/ledgers/home").json()["errors"] == []
