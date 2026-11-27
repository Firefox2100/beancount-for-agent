"""ISO 20022 camt.053 (bank-to-customer statement); camt.052 reports read the same way.

Names are matched without their namespace, so every version of the message reads alike. Files that declare a
DTD or entities are refused, which closes the usual XML expansion attacks without a further dependency.
"""

import datetime as dt
import xml.etree.ElementTree as ET
from decimal import Decimal

from beancount_mcp.imports.base import ImportFailed, Importer, clean, decode, number
from beancount_mcp.models.imports import Statement, StatementLine

Element = ET.Element


def _name(element: Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _child(element: Element | None, *path: str) -> Element | None:
    for name in path:
        if element is None:
            return None
        element = next((c for c in element if _name(c) == name), None)
    return element


def _children(element: Element | None, name: str) -> list[Element]:
    return [c for c in element if _name(c) == name] if element is not None else []


def _text(element: Element | None, *path: str) -> str | None:
    found = _child(element, *path)
    return found.text.strip() if found is not None and found.text and found.text.strip() else None


def _date(element: Element | None) -> dt.date | None:
    text = _text(element, "Dt") or _text(element, "DtTm")
    if not text:
        return None
    try:
        return dt.date.fromisoformat(text[:10])
    except ValueError:
        return None


def _signed(element: Element, what: str) -> tuple[Decimal, str]:
    amount = _child(element, "Amt")
    if amount is None or not amount.text:
        raise ImportFailed(f"a camt entry has no {what} amount")
    value = number(amount.text)
    return (-value if _text(element, "CdtDbtInd") == "DBIT" else value), (amount.get("Ccy") or "")


class Camt053Importer(Importer):
    id = "camt053"
    title = "ISO 20022 camt.053"

    def identify(self, filename: str, data: bytes) -> bool:
        head = data[:4096].decode("latin-1")
        return "camt.05" in head or ("<BkToCstmrStmt" in head)

    def parse(self, data: bytes) -> list[Statement]:
        lowered = data[:65536].lower()
        if b"<!doctype" in lowered or b"<!entity" in lowered:
            raise ImportFailed("the XML declares a DTD or entities, which are not accepted")
        try:
            root = ET.fromstring(decode(data))
        except ET.ParseError as error:
            raise ImportFailed(f"not valid XML: {error}") from None
        reports = [e for e in root.iter() if _name(e) in ("Stmt", "Rpt")]
        if not reports:
            raise ImportFailed("no statement (Stmt) in this camt file")
        return [self._statement(report) for report in reports]

    def _statement(self, report: Element) -> Statement:
        account = _child(report, "Acct")
        currency = _text(account, "Ccy")
        opening = closing = None
        end = None
        for balance in _children(report, "Bal"):
            kind = _text(balance, "Tp", "CdOrPrtry", "Cd")
            value, balance_currency = _signed(balance, "balance")
            currency = currency or balance_currency
            if kind == "OPBD" or (kind == "PRCD" and opening is None):
                opening = value
            elif kind == "CLBD":
                closing, end = value, _date(_child(balance, "Dt"))
        lines = [line for entry in _children(report, "Ntry") if (line := self._line(entry)) is not None]
        currency = currency or next((_signed(e, "entry")[1] for e in _children(report, "Ntry")), None)
        if not currency:
            raise ImportFailed("the camt statement does not say its currency")
        began = _text(report, "FrToDt", "FrDtTm")
        return Statement(
            format=self.id, account_id=_text(account, "Id", "IBAN") or _text(account, "Id", "Othr", "Id"),
            currency=currency, opening_balance=opening, closing_balance=closing, lines=lines,
            start=dt.date.fromisoformat(began[:10]) if began else None, end=end,
        )

    def _line(self, entry: Element) -> StatementLine | None:
        if (_text(entry, "Sts") or _text(entry, "Sts", "Cd") or "BOOK") not in ("BOOK", "BOOKED"):
            return None
        amount, _ = _signed(entry, "entry")
        if _text(entry, "RvslInd") == "true":
            amount = -amount
        posted = _date(_child(entry, "BookgDt")) or _date(_child(entry, "ValDt"))
        if posted is None:
            raise ImportFailed("a camt entry has no booking date")
        details = [d for d in entry.iter() if _name(d) == "TxDtls"]
        debit = _text(entry, "CdtDbtInd") == "DBIT"
        party = "Cdtr" if debit else "Dbtr"
        payee = next((p for d in details if (p := _text(d, "RltdPties", party, "Nm") or _text(d, "RltdPties", party, "Pty", "Nm"))), None)
        remittance = [clean(t.text) for d in details for t in d.iter() if _name(t) == "Ustrd" and t.text]
        description = " ".join(part for part in (*remittance, clean(_text(entry, "AddtlNtryInf"))) if part)
        references = [_text(entry, "AcctSvcrRef"), _text(entry, "NtryRef")]
        references += [_text(d, "Refs", "TxId") or _text(d, "Refs", "EndToEndId") for d in details]
        reference = next((r for r in references if r and r != "NOTPROVIDED"), None)
        return StatementLine(date=posted, amount=amount, payee=clean(payee) or None, description=description or clean(payee), reference=reference)
