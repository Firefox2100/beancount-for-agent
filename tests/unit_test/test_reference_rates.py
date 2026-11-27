import datetime as dt
import io
import json
from decimal import Decimal

from beancount_mcp.services.reference_rates import ReferenceRateService


class Answer(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def test_frankfurter_quotes_are_inverted_and_cached(tmp_path, monkeypatch):
    calls = []

    def open_request(request, timeout):
        calls.append((request.full_url, timeout))
        return Answer(json.dumps([{"date": "2026-03-02", "base": "USD", "quote": "CNY", "rate": 8}]).encode())

    monkeypatch.setattr("urllib.request.urlopen", open_request)
    service = ReferenceRateService(tmp_path / "rates.json", True, "https://rates.test/v2")
    first = service.rates("USD", {"USD", "CNY"}, dt.date(2026, 3, 2))
    second = service.rates("USD", {"CNY"}, dt.date(2026, 3, 2))

    assert first.rates == {"CNY": Decimal("0.125")}
    assert second.rates == first.rates and len(calls) == 1
    assert first.status.covered_currencies == ["CNY"] and first.status.state == "fresh"


def test_many_dates_come_back_from_one_request(tmp_path, monkeypatch):
    calls = []

    def open_request(request, timeout):
        calls.append(request.full_url)
        body = [{"date": f"2026-03-{day:02d}", "base": "USD", "quote": "CNY", "rate": 8} for day in (1, 2, 3)]
        return Answer(json.dumps(body).encode())

    monkeypatch.setattr("urllib.request.urlopen", open_request)
    service = ReferenceRateService(tmp_path / "rates.json", True, "https://rates.test/v2")
    dates = [dt.date(2026, 3, day) for day in (1, 2, 3)]
    results = service.rates_for("USD", {"CNY"}, dates)

    assert len(calls) == 1
    assert "from=2026-03-01" in calls[0] and "to=2026-03-03" in calls[0]
    assert {on: result.rates for on, result in results.items()} == {on: {"CNY": Decimal("0.125")} for on in dates}
    service.rates_for("USD", {"CNY"}, dates)
    assert len(calls) == 1


def test_only_currency_codes_and_dates_leave_the_service(tmp_path, monkeypatch):
    sent = []

    def open_request(request, timeout):
        sent.append(request.full_url)
        return Answer(json.dumps([{"date": "2026-03-02", "base": "GBP", "quote": "CNY", "rate": 9}]).encode())

    monkeypatch.setattr("urllib.request.urlopen", open_request)
    ReferenceRateService(tmp_path / "rates.json", True, "https://rates.test/v2").rates("GBP", {"CNY"}, dt.date(2026, 3, 2))

    assert sent == ["https://rates.test/v2/rates?base=GBP&quotes=CNY&date=2026-03-02"]


def test_rows_for_another_base_or_currency_and_zero_rates_are_ignored(tmp_path, monkeypatch):
    body = [
        {"date": "2026-03-02", "base": "EUR", "quote": "CNY", "rate": 7},
        {"date": "2026-03-02", "base": "GBP", "quote": "JPY", "rate": 190},
        {"date": "2026-03-02", "base": "GBP", "quote": "USD", "rate": 0},
        {"date": "2026-03-02", "base": "GBP", "quote": "CNY", "rate": 8},
        "not a row",
    ]
    monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout: Answer(json.dumps(body).encode()))
    result = ReferenceRateService(tmp_path / "rates.json", True, "https://rates.test/v2").rates(
        "GBP", {"CNY", "USD"}, dt.date(2026, 3, 2)
    )

    assert result.rates == {"CNY": Decimal("0.125")}
    assert result.status.missing_currencies == ["USD"]


def test_an_unexpected_answer_or_a_failure_is_reported_not_raised(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout: Answer(b'{"message": "nope"}'))
    service = ReferenceRateService(tmp_path / "rates.json", True, "https://rates.test/v2")
    result = service.rates("GBP", {"CNY"}, dt.date(2026, 3, 2))
    assert result.rates == {} and result.status.state == "unavailable" and "unexpected" in result.status.message

    def refuse(request, timeout):
        raise OSError("no route")

    monkeypatch.setattr("urllib.request.urlopen", refuse)
    assert service.rates("GBP", {"CNY"}, dt.date(2026, 3, 3)).status.state == "unavailable"


def test_nothing_is_fetched_while_the_feature_is_off(tmp_path, monkeypatch):
    def fail(request, timeout):
        raise AssertionError("no request may be made")

    monkeypatch.setattr("urllib.request.urlopen", fail)
    result = ReferenceRateService(tmp_path / "rates.json", False, "https://rates.test/v2").rates("GBP", {"CNY"}, dt.date(2026, 3, 2))
    assert result.rates == {} and result.status.state == "disabled"
