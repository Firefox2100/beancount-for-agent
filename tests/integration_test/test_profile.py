CARD = "Liabilities:Card:Main"


def test_empty_profile_and_roundtrip(client, card_ledger):
    empty = client.get(f"{card_ledger}/profile").json()
    assert empty["profile"] == {"accounts": {}, "pools": {}, "recurring": {}, "budgets": {}, "goals": {}, "recipes": {}} and empty["warnings"] == []

    profile = {
        "accounts": {CARD: {"description": "Main dual-currency card", "statement_day": 5, "pool": "shared"}},
        "pools": {"shared": {"limit": {"number": "10000", "currency": "USD"}}},
    }
    saved = client.put(f"{card_ledger}/profile", json=profile, headers={"If-Match": empty["version"]})
    assert saved.status_code == 200
    assert saved.json()["profile"]["pools"]["shared"]["limit"]["number"] == "10000"
    assert client.get(f"{card_ledger}/profile").json() == saved.json()

    account = next(a for a in client.get(f"{card_ledger}/accounts").json() if a["name"] == CARD)
    assert account["description"] == "Main dual-currency card"


def test_stale_profile_version_rejected(client, card_ledger):
    version = client.get(f"{card_ledger}/profile").json()["version"]
    client.put(f"{card_ledger}/profile", json={"accounts": {CARD: {"description": "one"}}})
    stale = client.put(f"{card_ledger}/profile", json={"accounts": {}}, headers={"If-Match": version})
    assert stale.status_code == 412


def test_agent_cannot_change_profile(client, card_ledger):
    response = client.put(f"{card_ledger}/profile", json={"accounts": {}}, headers={"X-Actor": "agent"})
    assert response.status_code == 403


def test_dangling_references_become_warnings(client, card_ledger):
    profile = {
        "accounts": {
            "Liabilities:Card:Gone": {"description": "x"},
            CARD: {"autopay_from": "Assets:Missing", "pool": "nowhere", "recipes": ["purchase", "mystery"]},
        }
    }
    view = client.put(f"{card_ledger}/profile", json=profile).json()
    assert len(view["warnings"]) == 4
    assert client.get(f"{card_ledger}/accounts").status_code == 200


def test_profile_does_not_change_ledger_version(client, card_ledger):
    before = client.get(card_ledger).json()["version"]
    client.put(f"{card_ledger}/profile", json={"accounts": {CARD: {"description": "x"}}})
    assert client.get(card_ledger).json()["version"] == before


def test_recipe_allow_list(client, card_ledger):
    client.put(f"{card_ledger}/profile", json={"accounts": {CARD: {"recipes": ["purchase"]}}})
    recipes = client.get(f"{card_ledger}/recipes", params={"account": CARD}).json()
    assert [r["id"] for r in recipes] == ["purchase"]
    blocked = client.post(f"{card_ledger}/accounts/{CARD}/actions/pay_card", json={})
    assert blocked.status_code == 422
