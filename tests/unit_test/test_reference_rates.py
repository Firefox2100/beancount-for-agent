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
