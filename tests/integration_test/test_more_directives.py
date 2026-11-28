import pytest
from beancount import loader

AGENT = {"X-Actor": "agent", "X-Client-Id": "mcp"}
MAIN = "main.beancount"


def add(client, body):
    return client.post("/ledgers/main/directives", json=body)


def kinds(client, kind):
    return client.get("/ledgers/main/directives", params={"kind": kind}).json()["items"]


def test_a_saved_query_is_stored_listed_and_left_for_fava_to_run(client, ledger, ledger_dir):
    query = "SELECT account, sum(position) WHERE account ~ 'Food' GROUP BY account"
    created = add(client, {"kind": "query", "date": "2026-02-01", "name": "food", "query": query})
    assert created.status_code == 201, created.text
    (record,) = kinds(client, "query")
    assert record["directive"] == {"kind": "query", "date": "2026-02-01", "name": "food", "query": query}
    entries, errors, _ = loader.load_file(str(ledger_dir / MAIN))
    assert errors == [] and any(type(e).__name__ == "Query" and e.name == "food" for e in entries)
    assert client.delete(f"/ledgers/main/directives/{record['id']}").status_code in (200, 204)
    assert kinds(client, "query") == []


def test_a_custom_entry_keeps_every_kind_of_value(client, ledger, ledger_dir):
    body = {"kind": "custom", "date": "2026-02-01", "type": "budget", "values": [
        {"type": "account", "value": "Expenses:Food"}, {"type": "amount", "value": {"number": "300.00", "currency": "USD"}},
        {"type": "string", "value": "monthly"}, {"type": "bool", "value": True},
        {"type": "date", "value": "2026-03-01"}, {"type": "number", "value": "12.5"}]}
    assert add(client, body).status_code == 201
    (record,) = kinds(client, "custom")
    assert record["directive"]["values"] == body["values"] or [v["type"] for v in record["directive"]["values"]] == ["account", "amount", "string", "bool", "date", "number"]
    shown = record["directive"]["values"]
    assert shown[1]["value"] == {"number": "300.00", "currency": "USD"} and shown[3]["value"] is True and shown[4]["value"] == "2026-03-01"
    assert loader.load_file(str(ledger_dir / MAIN))[1] == []


def test_a_custom_entry_naming_an_unopened_account_is_judged_by_beancount_not_us(client, ledger):
    refused = add(client, {"kind": "custom", "date": "2026-02-01", "type": "x", "values": [{"type": "account", "value": "Assets:Nowhere"}]})
    assert refused.status_code in (201, 422)
    assert add(client, {"kind": "custom", "date": "2026-02-01", "type": "x", "values": [{"type": "color", "value": "red"}]}).status_code == 422


def read_options(client):
    return client.get("/ledgers/main/options").json()


def test_options_are_read_and_the_title_is_set_replaced_and_cleared(client, ledger, ledger_dir):
    assert read_options(client)["operating_currency"] == ["USD"] and read_options(client)["booking_method"] == "STRICT"
    assert client.put("/ledgers/main/options/title", json={"value": "Home"}).status_code == 200
    assert client.put("/ledgers/main/options/title", json={"value": "House"}).status_code == 200
    text = (ledger_dir / MAIN).read_text()
    assert text.count('option "title"') == 1 and 'option "title" "House"' in text
    assert read_options(client)["title"] == "House"
    assert client.put("/ledgers/main/options/title", json={"value": "House", "remove": True}).status_code == 200
    assert read_options(client)["title"] == "Beancount"  # Beancount's own default once the option is gone


def test_operating_currencies_are_added_once_and_removed_by_name(client, ledger):
    assert client.put("/ledgers/main/options/operating_currency", json={"value": "GBP"}).status_code == 200
    client.put("/ledgers/main/options/operating_currency", json={"value": "GBP"})
    assert read_options(client)["operating_currency"] == ["USD", "GBP"]
    assert client.put("/ledgers/main/options/operating_currency", json={"value": "USD", "remove": True}).status_code == 200
    assert read_options(client)["operating_currency"] == ["GBP"]
    missing = client.put("/ledgers/main/options/operating_currency", json={"value": "EUR", "remove": True})
    assert missing.status_code == 404 and "not set" in missing.json()["detail"]


@pytest.mark.parametrize("name,value,fragment", [
    ("render_commas", "yes", "TRUE or FALSE"),
    ("booking_method", "RANDOM", "booking_method is one of"),
    ("operating_currency", "pounds", "currency code"),
    ("title", 'say "hi"', "pattern"),
])
def test_bad_option_values_are_refused_with_the_reason(client, ledger, name, value, fragment):
    response = client.put(f"/ledgers/main/options/{name}", json={"value": value})
    assert response.status_code == 422 and fragment in response.text
    assert client.put("/ledgers/main/options/plugin", json={"value": "x"}).status_code == 422


def test_booking_and_commas_options_take_effect_and_an_agent_must_propose(client, ledger):
    assert client.put("/ledgers/main/options/booking_method", json={"value": "FIFO"}).status_code == 200
    assert client.put("/ledgers/main/options/render_commas", json={"value": "TRUE"}).status_code == 200
    assert read_options(client)["booking_method"] == "FIFO" and read_options(client)["render_commas"] is True
    assert client.put("/ledgers/main/options/title", json={"value": "X"}, headers=AGENT).status_code == 403
    version = client.get("/ledgers/main").json()["version"]
    proposal = client.post("/ledgers/main/changes", headers={**AGENT, "If-Match": version}, json={"operation": {"kind": "set_option", "name": "title", "value": "Proposed"}})
    assert proposal.status_code == 201 and read_options(client)["title"] == "Beancount"
    assert client.post(f"/ledgers/main/changes/{proposal.json()['id']}/approve", json={}).status_code == 200
    assert read_options(client)["title"] == "Proposed"


def test_other_lines_of_the_entry_file_are_left_alone(client, ledger, ledger_dir):
    path = ledger_dir / MAIN
    path.write_text("; my note\n" + path.read_text() + "\n; trailing comment\n")
    client.put("/ledgers/main/options/title", json={"value": "Kept"})
    text = path.read_text()
    assert text.startswith("; my note\n") and text.rstrip().endswith("; trailing comment")
