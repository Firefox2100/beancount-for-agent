def act(client, ledger, account, recipe, params):
    return client.post(f"{ledger}/accounts/{account}/actions/{recipe}", json=params)


def balances(client, ledger):
    return {b["account"]: b["balances"] for b in client.get(f"{ledger}/balances").json()}


def ok(response):
    assert response.status_code == 200, response.text
    return response.json()


def healthy(client, ledger):
    assert client.get(ledger).json()["errors"] == []


CHECKING = "Assets:Bank:Checking"
YUAN = "Assets:Bank:Yuan"


def test_kinds_are_discoverable_with_their_recipes(client, wide_ledger):
    kinds = {k["name"]: k for k in client.get(f"{wide_ledger}/kinds").json()}
    assert set(kinds) >= {"checking", "savings", "cash", "ewallet", "credit_card", "loan",
                          "receivable", "payable", "brokerage"}
    assert "salary" in kinds["checking"]["recipes"] and "buy" in kinds["brokerage"]["recipes"]


def test_salary_from_gross_or_from_net(client, wide_ledger):
    deductions = [{"account": "Expenses:Tax", "amount": "250"}]
    ok(act(client, wide_ledger, CHECKING, "salary",
           {"date": "2026-02-01", "income_account": "Income:Salary", "gross": "1000", "deductions": deductions}))
    ok(act(client, wide_ledger, CHECKING, "salary",
           {"date": "2026-03-01", "income_account": "Income:Salary", "net": "750 USD", "deductions": deductions}))
    result = balances(client, wide_ledger)
    assert result[CHECKING] == {"USD": "1500"}
    assert result["Income:Salary"] == {"USD": "-2000"}
    healthy(client, wide_ledger)


def test_salary_with_inconsistent_gross_and_net_is_refused(client, wide_ledger):
    response = act(client, wide_ledger, CHECKING, "salary", {
        "income_account": "Income:Salary", "gross": "1000", "net": "800",
        "deductions": [{"account": "Expenses:Tax", "amount": "250"}],
    })
    assert response.status_code == 422


def test_actions_default_to_today(client, wide_ledger):
    created = ok(act(client, wide_ledger, CHECKING, "receive",
                     {"from_account": "Income:Salary", "amount": "5 USD"}))
    assert created["transaction"]["date"]


def test_spend_in_a_foreign_currency_accepts_amount_or_rate(client, wide_ledger):
    ok(act(client, wide_ledger, CHECKING, "receive",
           {"date": "2026-02-01", "from_account": "Income:Salary", "amount": 500}))
    ok(act(client, wide_ledger, CHECKING, "spend", {
        "date": "2026-02-02", "expense_account": "Expenses:Food", "amount": "100 GBP", "charged": "130 USD"}))
    ok(act(client, wide_ledger, CHECKING, "spend", {
        "date": "2026-02-03", "expense_account": "Expenses:Food", "amount": "10 GBP", "rate": "1.3"}))
    result = balances(client, wide_ledger)
    assert result[CHECKING] == {"USD": "357.00"}
    assert result["Expenses:Food"] == {"GBP": "110.00"}
    healthy(client, wide_ledger)


def test_bare_number_needs_a_single_currency_account(client, wide_ledger):
    response = act(client, wide_ledger, "Assets:Wallet", "receive",
                   {"from_account": "Income:Salary", "amount": "20"})
    assert response.status_code == 422 and "currency" in response.json()["detail"]
    ok(act(client, wide_ledger, "Assets:Wallet", "receive",
           {"from_account": "Income:Salary", "amount": "20 CNY"}))


def test_negative_amounts_are_read_as_magnitudes(client, wide_ledger):
    ok(act(client, wide_ledger, CHECKING, "receive", {"from_account": "Income:Salary", "amount": "-40"}))
    assert balances(client, wide_ledger)[CHECKING] == {"USD": "40"}


def test_transfer_between_currencies_by_rate(client, wide_ledger):
    ok(act(client, wide_ledger, CHECKING, "receive", {"from_account": "Income:Salary", "amount": "100"}))
    ok(act(client, wide_ledger, CHECKING, "transfer",
           {"to_account": YUAN, "amount": "100", "rate": "7.2"}))
    result = balances(client, wide_ledger)
    assert result[YUAN] == {"CNY": "720.00"}
    assert not result.get(CHECKING)
    healthy(client, wide_ledger)


def test_transfer_needs_a_rate_across_currencies(client, wide_ledger):
    response = act(client, wide_ledger, CHECKING, "transfer", {"to_account": YUAN, "amount": "10"})
    assert response.status_code == 422 and "rate" in response.json()["detail"]


def test_interest_with_tax_withheld(client, wide_ledger):
    fixed = "Assets:Bank:Fixed"
    client.put(f"{wide_ledger}/profile", json={"accounts": {fixed: {"interest_account": "Income:Interest"}}})
    ok(act(client, wide_ledger, fixed, "interest",
           {"date": "2026-06-30", "amount": "80", "tax_withheld": "20", "tax_account": "Expenses:Tax"}))
    result = balances(client, wide_ledger)
    assert result[fixed] == {"USD": "80"} and result["Income:Interest"] == {"USD": "-100"}
    healthy(client, wide_ledger)


def test_loan_repayment_from_total_or_from_principal(client, wide_ledger):
    loan = "Liabilities:Loan:Car"
    ok(act(client, wide_ledger, CHECKING, "receive", {"from_account": "Income:Salary", "amount": "1000"}))
    ok(act(client, wide_ledger, loan, "drawdown", {"to_account": CHECKING, "amount": "5000"}))
    ok(act(client, wide_ledger, loan, "repay", {
        "from_account": CHECKING, "payment": "300", "interest": "20", "interest_account": "Expenses:Interest",
        "fees": [{"account": "Expenses:Fees", "amount": "5"}]}))
    ok(act(client, wide_ledger, loan, "repay", {
        "from_account": CHECKING, "principal": "100", "interest": "10", "interest_account": "Expenses:Interest"}))
    result = balances(client, wide_ledger)
    assert result[loan] == {"USD": "-4625"}
    assert result[CHECKING] == {"USD": "5590"}
    healthy(client, wide_ledger)


def test_reimbursement_claim_is_linked_and_settled(client, wide_ledger):
    friend = "Assets:Owed:Friend"
    opened = ok(act(client, wide_ledger, friend, "lend", {
        "date": "2026-02-01", "counter_account": CHECKING, "amount": "60", "payee": "Sam"}))
    link = opened["transaction"]["links"][0]
    assert link.startswith("claim-")
    ok(act(client, wide_ledger, CHECKING, "receive", {"from_account": "Income:Salary", "amount": "200"}))
    settled = ok(act(client, wide_ledger, friend, "collect", {
        "date": "2026-02-10", "counter_account": CHECKING, "link": link,
        "amount": "50", "adjustment": "10", "adjustment_account": "Expenses:WrittenOff"}))
    assert settled["transaction"]["links"] == [link]
    result = balances(client, wide_ledger)
    assert not result.get(friend)
    assert result["Expenses:WrittenOff"] == {"USD": "10"}
    healthy(client, wide_ledger)


def test_collect_defaults_to_everything_open(client, wide_ledger):
    friend = "Assets:Owed:Friend"
    ok(act(client, wide_ledger, friend, "invoice", {"counter_account": "Income:Salary", "amount": "300"}))
    ok(act(client, wide_ledger, friend, "collect", {"counter_account": CHECKING}))
    result = balances(client, wide_ledger)
    assert result[CHECKING] == {"USD": "300"}
    healthy(client, wide_ledger)


def test_bills_are_recorded_and_paid(client, wide_ledger):
    supplier = "Liabilities:Payable:Supplier"
    ok(act(client, wide_ledger, CHECKING, "receive", {"from_account": "Income:Salary", "amount": "500"}))
    ok(act(client, wide_ledger, supplier, "receive_bill", {"counter_account": "Expenses:Food", "amount": "120"}))
    ok(act(client, wide_ledger, supplier, "pay_bill", {"counter_account": CHECKING}))
    result = balances(client, wide_ledger)
    assert result[CHECKING] == {"USD": "380"}
    assert result["Expenses:Food"] == {"USD": "120"}
    healthy(client, wide_ledger)


def test_buy_sell_and_dividend(client, wide_ledger):
    invest, cash = "Assets:Invest", "Assets:Invest:Cash"
    client.put(f"{wide_ledger}/profile", json={"accounts": {
        invest: {"cash_account": cash, "gains_account": "Income:Gains"}}})
    ok(act(client, wide_ledger, cash, "receive", {"from_account": "Income:Salary", "amount": "5000"}))
    ok(act(client, wide_ledger, invest, "buy", {
        "date": "2026-02-01", "commodity": "AAPL", "units": "10", "price": "150 USD",
        "fee": "5", "fee_account": "Expenses:Fees"}))
    ok(act(client, wide_ledger, invest, "buy", {
        "date": "2026-02-02", "commodity": "AAPL", "units": "10", "total": "1600 USD"}))
    ok(act(client, wide_ledger, invest, "sell", {
        "date": "2026-03-01", "commodity": "AAPL", "units": "10", "price": "170 USD"}))
    ok(act(client, wide_ledger, invest, "dividend", {
        "date": "2026-03-15", "amount": "8", "income_account": "Income:Dividends"}))
    result = balances(client, wide_ledger)
    assert result[invest] == {"AAPL": "10"}
    assert result[cash] == {"USD": "3603.00"}
    assert result["Expenses:Fees"] == {"USD": "5"}
    assert result["Income:Gains"] == {"USD": "-200.00"}
    healthy(client, wide_ledger)


def test_sell_without_gains_account_is_explained(client, wide_ledger):
    response = act(client, wide_ledger, "Assets:Invest", "sell", {
        "commodity": "AAPL", "units": "1", "price": "1 USD", "cash_account": "Assets:Invest:Cash"})
    assert response.status_code == 422 and "gains" in response.json()["detail"]


def test_card_refund_reverses_a_purchase(client, card_ledger):
    card = "Liabilities:Card:Main"
    for params in ({"date": "2026-02-01", "expense_account": "Expenses:Food", "amount": "30 USD"}, ):
        assert client.post(f"{card_ledger}/accounts/{card}/actions/purchase", json=params).status_code == 200
    refund = client.post(f"{card_ledger}/accounts/{card}/actions/refund", json={
        "date": "2026-02-05", "expense_account": "Expenses:Food", "amount": "30 USD"})
    assert refund.status_code == 200, refund.text
    result = {b["account"]: b["balances"] for b in client.get(f"{card_ledger}/balances").json()}
    assert not result.get(card)


def test_card_payment_and_statement_accept_rates(client, card_ledger):
    card = "Liabilities:Card:Main"
    client.post(f"{card_ledger}/accounts/{card}/actions/purchase",
                json={"date": "2026-02-01", "expense_account": "Expenses:Food", "amount": "100 GBP"})
    close = client.post(f"{card_ledger}/accounts/{card}/actions/close_statement", json={
        "date": "2026-03-01", "conversions": [{"unbilled": "100 GBP", "rate": "1.3", "billed": "130 USD"}]})
    assert close.status_code == 200, close.text
    pay = client.post(f"{card_ledger}/accounts/{card}/actions/pay_card", json={
        "date": "2026-03-10", "from_account": "Assets:Bank:Debit", "payments": [{"paid": "936 CNY", "cleared": "130 USD"}]})
    assert pay.status_code == 200, pay.text
    assert client.get(card_ledger).json()["errors"] == []
