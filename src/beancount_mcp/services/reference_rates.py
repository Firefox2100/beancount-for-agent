"""Informational exchange rates. These values never enter ledger operations."""

import datetime as dt
import json
import logging
import os
import threading
import urllib.parse
import urllib.request
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from beancount_mcp.models.views import ReferenceRateStatus

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class RateResult:
    rates: dict[str, Decimal]
    status: ReferenceRateStatus


class ReferenceRateService:
    """A small persistent stale-while-revalidate cache around Frankfurter v2."""

    def __init__(self, cache_file: Path, enabled: bool, base_url: str, fresh_hours: int = 24, stale_hours: int = 12):
        self._path = cache_file
        self._enabled = enabled
        self._url = base_url.rstrip("/")
        self._fresh = dt.timedelta(hours=fresh_hours)
        self._grace = dt.timedelta(hours=stale_hours)
        self._lock = threading.RLock()
        self._refreshing: set[str] = set()

    @property
    def enabled(self) -> bool:
        return self._enabled

    def status(self) -> ReferenceRateStatus:
        rows = self._read()
        if not self._enabled:
            return ReferenceRateStatus(enabled=False, state="disabled")
        if not rows:
            return ReferenceRateStatus(enabled=True, state="empty")
        newest = max(rows.values(), key=lambda row: row.get("fetched_at", ""))
        fetched = dt.datetime.fromisoformat(newest["fetched_at"])
        age = dt.datetime.now(dt.UTC) - fetched
        state = "fresh" if age <= self._fresh else "stale" if age <= self._fresh + self._grace else "unavailable"
        return self._status(newest, sorted(newest.get("rates", {})), [], state)

    def rates(self, base: str, quotes: set[str], on: dt.date) -> RateResult:
        quotes = {quote for quote in quotes if quote != base}
        if not quotes:
            return RateResult({}, ReferenceRateStatus(
                enabled=self._enabled, base_currency=base, observed_on=on,
                state="fresh" if self._enabled else "disabled",
            ))
        if not self._enabled:
            return RateResult({}, ReferenceRateStatus(enabled=False, base_currency=base, state="disabled", missing_currencies=sorted(quotes)))
        key = self._key(base, quotes, on)
        cached = self._read().get(key)
        now = dt.datetime.now(dt.UTC)
        stale_allowed = False
        if cached is not None:
            fetched = dt.datetime.fromisoformat(cached["fetched_at"])
            if now - fetched <= self._fresh:
                return self._result(cached, base, quotes, "fresh")
            if now - fetched <= self._fresh + self._grace:
                stale_allowed = True
                self._start_refresh(key, base, quotes, on)
                return self._result(cached, base, quotes, "refreshing" if key in self._refreshing else "stale")
        try:
            row = self._fetch(base, quotes, on)
            self._store(key, row)
            return self._result(row, base, quotes, "fresh")
        except Exception as error:
            log.warning("reference rate refresh failed", extra={"base": base, "date": str(on), "error": str(error)})
            if cached is not None and stale_allowed:
                return self._result(cached, base, quotes, "stale", str(error))
            return RateResult({}, ReferenceRateStatus(enabled=True, base_currency=base, state="unavailable", missing_currencies=sorted(quotes), message=str(error)))

    def rates_for(self, base: str, quotes: set[str], dates: list[dt.date]) -> dict[dt.date, RateResult]:
        """The rates of several dates in as few requests as possible: one range request per gap."""
        quotes = {quote for quote in quotes if quote != base}
        if not quotes or not self._enabled:
            return {on: self.rates(base, quotes, on) for on in dates}
        cached = self._read()
        now = dt.datetime.now(dt.UTC)
        results: dict[dt.date, RateResult] = {}
        missing: list[dt.date] = []
        for on in dates:
            row = cached.get(self._key(base, quotes, on))
            if row is not None and now - dt.datetime.fromisoformat(row["fetched_at"]) <= self._fresh:
                results[on] = self._result(row, base, quotes, "fresh")
            else:
                missing.append(on)
        if len(missing) > 1 and max(missing) > min(missing):
            try:
                rows = self._fetch_range(base, quotes, min(missing), max(missing))
                for on in missing:
                    row = rows.get(on.isoformat())
                    if row is None:
                        continue
                    self._store(self._key(base, quotes, on), row)
                    results[on] = self._result(row, base, quotes, "fresh")
            except Exception as error:  # noqa: BLE001 - a failed batch falls back to single days
                log.warning("reference rate range fetch failed", extra={"base": base, "from": str(min(missing)), "to": str(max(missing)), "error": str(error)})
        for on in missing:
            if on not in results:
                results[on] = self.rates(base, quotes, on)
        return results

    def refresh(self) -> ReferenceRateStatus:
        with self._lock:
            self._write({})
        return ReferenceRateStatus(enabled=self._enabled, state="empty" if self._enabled else "disabled")

    def _start_refresh(self, key: str, base: str, quotes: set[str], on: dt.date) -> None:
        with self._lock:
            if key in self._refreshing:
                return
            self._refreshing.add(key)

        def run() -> None:
            try:
                self._store(key, self._fetch(base, quotes, on))
            except Exception as error:
                log.warning("background reference rate refresh failed", extra={"base": base, "date": str(on), "error": str(error)})
            finally:
                with self._lock:
                    self._refreshing.discard(key)

        threading.Thread(target=run, name="reference-rates", daemon=True).start()

    def _fetch(self, base: str, quotes: set[str], on: dt.date) -> dict:
        body = self._request({"base": base, "quotes": ",".join(sorted(quotes)), "date": on.isoformat()})
        rates: dict[str, str] = {}
        dates: list[str] = []
        for quoted_on, currency, rate in _inverted(base, quotes, body):
            rates[currency] = format(rate, "f")
            dates.append(quoted_on)
        return self._row(base, max(dates) if dates else on.isoformat(), rates)

    def _fetch_range(self, base: str, quotes: set[str], start: dt.date, end: dt.date) -> dict[str, dict]:
        """Every date in one request, so a twelve-point chart costs one round trip instead of twelve."""
        body = self._request({"base": base, "quotes": ",".join(sorted(quotes)), "from": start.isoformat(), "to": end.isoformat()})
        by_date: dict[str, dict[str, str]] = {}
        for quoted_on, currency, rate in _inverted(base, quotes, body):
            by_date.setdefault(quoted_on, {})[currency] = format(rate, "f")
        return {quoted_on: self._row(base, quoted_on, rates) for quoted_on, rates in by_date.items()}

    def _request(self, parameters: dict[str, str]) -> list:
        query = urllib.parse.urlencode(parameters)
        request = urllib.request.Request(
            f"{self._url}/rates?{query}",
            headers={"accept": "application/json", "user-agent": "beancount-mcp"},
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            body = json.load(response)
        if not isinstance(body, list):
            raise ValueError("Frankfurter returned an unexpected response")
        return body

    @staticmethod
    def _row(base: str, quoted_on: str, rates: dict[str, str]) -> dict:
        return {"base": base, "date": quoted_on, "fetched_at": dt.datetime.now(dt.UTC).isoformat(), "rates": rates}

    def _result(self, row: dict, base: str, quotes: set[str], state: str, message: str | None = None) -> RateResult:
        rates = {currency: Decimal(value) for currency, value in row.get("rates", {}).items() if currency in quotes}
        missing = sorted(quotes - rates.keys())
        return RateResult(rates, self._status(row, sorted(rates), missing, state, message))

    def _status(self, row: dict, covered: list[str], missing: list[str], state: str = "fresh", message: str | None = None) -> ReferenceRateStatus:
        return ReferenceRateStatus(provider="frankfurter", enabled=self._enabled, base_currency=row.get("base"), observed_on=dt.date.fromisoformat(row["date"]) if row.get("date") else None, fetched_at=dt.datetime.fromisoformat(row["fetched_at"]) if row.get("fetched_at") else None, state=state, covered_currencies=covered, missing_currencies=missing, message=message)

    @staticmethod
    def _key(base: str, quotes: set[str], on: dt.date) -> str:
        return f"{on.isoformat()}|{base}|{','.join(sorted(quotes))}"

    def _read(self) -> dict[str, dict]:
        with self._lock:
            try:
                value = json.loads(self._path.read_text())
                return value if isinstance(value, dict) else {}
            except (FileNotFoundError, json.JSONDecodeError, OSError):
                return {}

    def _write(self, rows: dict[str, dict]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._path.with_suffix(".tmp")
        temporary.write_text(json.dumps(rows, sort_keys=True))
        os.replace(temporary, self._path)

    def _store(self, key: str, row: dict) -> None:
        with self._lock:
            rows = self._read()
            rows[key] = row
            self._write(rows)


def _inverted(base: str, quotes: set[str], body: list) -> list[tuple[str, str, Decimal]]:
    """The rows that answer this request, as (date, currency, base units per one held unit).

    Frankfurter returns quote units per one base unit; the cache stores the inverse so valuation is a
    multiplication. Rows for another base or a currency nobody asked for are dropped.
    """
    converted = []
    for item in body:
        if not isinstance(item, dict):
            continue
        item_base = str(item.get("base", "")).upper()
        item_quote = str(item.get("quote", "")).upper()
        if item_base != base.upper() or item_quote not in quotes:
            continue
        quoted = Decimal(str(item["rate"]))
        if quoted == 0:
            continue
        converted.append((str(item["date"]), item_quote, Decimal(1) / quoted))
    return converted
