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
