"""OFX and QFX: bank and credit-card statements, both the older SGML form and the XML form.

A tolerant tag reader rather than a parser: leaf values run to the next `<`, which is true of both forms.
Investment statements are not supported.
"""

import datetime as dt
import html
import re

from beancount_mcp.imports.base import ImportFailed, Importer, clean, decode, number
from beancount_mcp.models.imports import Statement, StatementLine

_STATEMENT = re.compile(r"<(STMTRS|CCSTMTRS)>(.*?)</\1>", re.DOTALL | re.IGNORECASE)
_TRANSACTION = re.compile(r"<STMTTRN>(.*?)(?:</STMTTRN>|(?=<STMTTRN>)|$)", re.DOTALL | re.IGNORECASE)


def _leaf(block: str, tag: str) -> str | None:
    match = re.search(rf"<{tag}>\s*([^<\r\n]*)", block, re.IGNORECASE)
    return html.unescape(match.group(1).strip()) if match and match.group(1).strip() else None


def _date(text: str | None) -> dt.date | None:
    if not text or not re.match(r"\d{8}", text):
        return None
    try:
        return dt.date(int(text[:4]), int(text[4:6]), int(text[6:8]))
    except ValueError:
        return None


class OfxImporter(Importer):
    id = "ofx"
    title = "OFX / QFX"

    def identify(self, filename: str, data: bytes) -> bool:
        head = data[:4096].decode("latin-1").upper()
        return "OFXHEADER" in head or "<OFX>" in head

    def parse(self, data: bytes) -> list[Statement]:
        text = decode(data)
        statements = []
        for _, body in _STATEMENT.findall(text):
            currency = _leaf(body, "CURDEF")
            if currency is None:
                raise ImportFailed("the OFX statement does not say its currency (CURDEF)")
            lines = []
            for block in _TRANSACTION.findall(body):
                posted, amount = _date(_leaf(block, "DTPOSTED")), _leaf(block, "TRNAMT")
                if posted is None or amount is None:
                    raise ImportFailed("an OFX transaction has no posting date or amount")
                name, memo = clean(_leaf(block, "NAME")), clean(_leaf(block, "MEMO"))
                lines.append(StatementLine(
                    date=posted, amount=number(amount), payee=name or None,
                    description=memo if memo and memo != name else name, reference=_leaf(block, "FITID"),
                ))
            balance = re.search(r"<LEDGERBAL>(.*?)(?:</LEDGERBAL>|$)", body, re.DOTALL | re.IGNORECASE)
            closing = _leaf(balance.group(1), "BALAMT") if balance else None
            end = _date(_leaf(body, "DTEND")) or (_date(_leaf(balance.group(1), "DTASOF")) if balance else None)
            statements.append(Statement(
                format=self.id, account_id=_leaf(body, "ACCTID"), currency=currency.upper(),
                closing_balance=number(closing, "balance") if closing else None,
                start=_date(_leaf(body, "DTSTART")), end=end, lines=lines,
            ))
        if not statements:
            raise ImportFailed("no bank or credit-card statement in this OFX file (investment statements are not supported)")
        return statements
