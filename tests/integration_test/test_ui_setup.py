AGENT = {"X-Actor": "agent", "X-Client-Id": "mcp"}
FEE = {
    "title": "Bank fee", "description": "A fee the bank took.", "kinds": ["checking"],
    "params": {"fee": {"type": "amount", "description": "What was taken."}}, "narration": "Bank fee",
    "postings": [{"account": "@self", "amount": "-$fee"}, {"account": "Expenses:Fees", "amount": "$fee"}],
}


def test_the_inbox_shows_a_recipe_in_plain_lines_before_anyone_approves_it(client, wide_ledger):
    made = client.post("/agent/setup", headers=AGENT, json={"ledger": "wide", "item": "recipe", "id": "bank_fee", "value": FEE, "note": "for the monthly fee"})
    assert made.status_code == 201
    page = client.get("/ui/").text
    assert "Set recipe bank_fee: Bank fee" in page and "for: checking" in page
    assert "parameter fee (amount; required)" in page and "posting: @self  -$fee" in page and "posting: Expenses:Fees  $fee" in page
    assert "for the monthly fee" in page


def test_a_budget_and_a_removal_and_an_option_read_clearly_in_the_inbox(client, wide_ledger):
    client.post("/agent/setup", headers=AGENT, json={"ledger": "wide", "item": "budget", "id": "food", "value": {"account": "Expenses:Food", "amount": {"number": "1500", "currency": "USD"}}})
    client.post("/agent/setup", headers=AGENT, json={"ledger": "wide", "item": "goal", "id": "gone", "value": None})
    version = client.get("/ledgers/wide").json()["version"]
    client.post("/ledgers/wide/changes", headers={**AGENT, "If-Match": version}, json={"operation": {"kind": "set_option", "name": "title", "value": "Household"}})
    page = client.get("/ui/").text
    assert "Set budget food" in page and "account: Expenses:Food" in page and "amount: 1,500 USD" in page
    assert "Remove goal gone" in page and "only changes how the ledger is treated" in page
    assert "Set the ledger option title: Household" in page
