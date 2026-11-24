CARD = "Liabilities:Card:Main"


def act(client, ledger, recipe, params, account=CARD, **kwargs):
    return client.post(f"{ledger}/accounts/{account}/actions/{recipe}", json=params, **kwargs)


def amount(number, currency):
    return {"number": number, "currency": currency}


def balances(client, ledger):
    return {b["account"]: b["balances"] for b in client.get(f"{ledger}/balances").json()}


def purchase(client, ledger, spent, **extra):
    body = {"date": "2026-02-01", "expense_account": "Expenses:Food", "amount": spent, **extra}
    return act(client, ledger, "purchase", body)


def test_accounts_list_recipes_and_type(client, card_ledger):
    accounts = {a["name"]: a for a in client.get(f"{card_ledger}/accounts").json()}
    assert accounts[CARD]["type"] == "credit_card"
    assert accounts[CARD]["recipes"] == ["close_statement", "pay_card", "purchase", "refund"]
    assert accounts["Expenses:Food"]["recipes"] == []

    recipes = client.get(f"{card_ledger}/recipes", params={"account": CARD}).json()
    assert [r["id"] for r in recipes] == ["close_statement", "pay_card", "purchase", "refund"]
    assert "amount" in recipes[2]["params_schema"]["properties"]


def test_purchase_billing_modes(client, card_ledger):
    assert purchase(client, card_ledger, amount("100", "GBP")).status_code == 200
    assert purchase(client, card_ledger, amount("50", "CNY")).status_code == 200
    converted = purchase(client, card_ledger, amount("20", "GBP"), billed_amount=amount("26", "USD"))
    assert converted.json()["transaction"]["meta"]["original-amount"] == "20 GBP"

    result = balances(client, card_ledger)
    assert result["Liabilities:Card:Main:Unbilled"] == {"GBP": "-100"}
    assert result[CARD] == {"CNY": "-50", "USD": "-26"}
    assert client.get(card_ledger).json()["errors"] == []


def test_statement_converts_unbilled_and_asserts_balances(client, card_ledger):
    purchase(client, card_ledger, amount("100", "GBP"))
    purchase(client, card_ledger, amount("50", "CNY"))
    close = act(client, card_ledger, "close_statement", {
        "date": "2026-03-01",
        "conversions": [{"unbilled": amount("100", "GBP"), "billed": amount("130.37", "USD")}],
        "statement_balances": [amount("130.37", "USD"), amount("50", "CNY")],
    })
    assert close.status_code == 200, close.text
    result = balances(client, card_ledger)
    assert result[CARD] == {"CNY": "-50", "USD": "-130.37"}
    assert "Liabilities:Card:Main:Unbilled" not in result or result["Liabilities:Card:Main:Unbilled"] == {}
    assert client.get(card_ledger).json()["errors"] == []


def test_wrong_statement_balance_is_rejected(client, card_ledger):
    purchase(client, card_ledger, amount("100", "GBP"))
    before = client.get(card_ledger).json()["version"]
    close = act(client, card_ledger, "close_statement", {
        "date": "2026-03-01",
        "conversions": [{"unbilled": amount("100", "GBP"), "billed": amount("130", "USD")}],
        "statement_balances": [amount("131", "USD")],
    })
    assert close.status_code == 422
    assert client.get(card_ledger).json()["version"] == before


def test_cannot_convert_more_than_unbilled(client, card_ledger):
    purchase(client, card_ledger, amount("10", "GBP"))
    close = act(client, card_ledger, "close_statement", {
        "date": "2026-03-01",
        "conversions": [{"unbilled": amount("11", "GBP"), "billed": amount("14", "USD")}],
    })
    assert close.status_code == 422 and "unbilled" in close.json()["detail"]


def test_payment_in_other_currency_and_in_both(client, card_ledger):
    purchase(client, card_ledger, amount("100", "USD"))
    purchase(client, card_ledger, amount("50", "CNY"))
    pay = act(client, card_ledger, "pay_card", {
        "date": "2026-03-10",
        "from_account": "Assets:Bank:Debit",
        "payments": [
            {"paid": amount("720", "CNY"), "cleared": amount("100", "USD")},
            {"paid": amount("50", "CNY"), "cleared": amount("50", "CNY")},
        ],
    })
    assert pay.status_code == 200, pay.text
    result = balances(client, card_ledger)
    assert result["Assets:Bank:Debit"] == {"CNY": "-770.00"}
    assert result[CARD] == {}
    assert client.get(card_ledger).json()["errors"] == []


def test_payment_defaults_to_configured_autopay_account(client, card_ledger):
    purchase(client, card_ledger, amount("50", "CNY"))
    profile = {"accounts": {CARD: {"autopay_from": "Assets:Bank:Debit", "due_day": 25}}}
    assert client.put(f"{card_ledger}/profile", json=profile).status_code == 200
    pay = act(client, card_ledger, "pay_card", {
        "date": "2026-03-10", "payments": [{"paid": amount("50", "CNY"), "cleared": amount("50", "CNY")}],
    })
    assert pay.status_code == 200
    assert act(client, card_ledger, "pay_card", {
        "date": "2026-03-10", "from_account": "Assets:Bank:Debit",
        "payments": [{"paid": amount("49", "CNY"), "cleared": amount("50", "CNY")}],
    }).status_code == 422


def test_invalid_recipe_use(client, card_ledger):
    bad_currency = purchase(client, card_ledger, amount("10", "GBP"), billed_amount=amount("9", "EUR"))
    assert bad_currency.status_code == 422
    assert act(client, card_ledger, "purchase", {"date": "2026-02-01"}).status_code == 422
    assert act(client, card_ledger, "nope", {}).status_code == 404
    on_expense = act(client, card_ledger, "purchase", {}, account="Expenses:Food")
    assert on_expense.status_code == 422


def test_missing_unbilled_account_is_reported(client, card_ledger):
    client.post(f"{card_ledger}/accounts/Liabilities:Card:Main:Unbilled/close", json={"date": "2026-01-02"})
    response = purchase(client, card_ledger, amount("10", "GBP"))
    assert response.status_code == 422 and "not open" in response.json()["detail"]


def test_agent_proposes_action_and_human_approves(client, card_ledger):
    agent = {"X-Actor": "agent", "X-Client-Id": "harness"}
    direct = act(client, card_ledger, "purchase", {
        "date": "2026-02-01", "expense_account": "Expenses:Food", "amount": amount("5", "USD"),
    }, headers=agent)
    assert direct.status_code == 403

    version = client.get(card_ledger).json()["version"]
    proposed = client.post(f"{card_ledger}/changes", headers={**agent, "If-Match": version}, json={
        "action": {"account": CARD, "recipe": "purchase", "params": {
            "date": "2026-02-01", "expense_account": "Expenses:Food", "amount": amount("5", "USD"),
        }},
    })
    assert proposed.status_code == 201
    change = proposed.json()
    assert change["source"]["recipe"] == "purchase" and change["operation"]["kind"] == "add_transaction"
    assert client.post(f"{card_ledger}/changes/{change['id']}/approve", json={}).status_code == 200
    assert balances(client, card_ledger)[CARD] == {"USD": "-5"}


def test_submission_needs_exactly_one_of_operation_or_action(client, card_ledger):
    version = client.get(card_ledger).json()["version"]
    response = client.post(f"{card_ledger}/changes", json={}, headers={"X-Actor": "agent", "If-Match": version})
    assert response.status_code == 422
