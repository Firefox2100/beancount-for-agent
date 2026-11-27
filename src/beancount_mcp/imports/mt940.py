"""SWIFT MT940 customer statements, the format older bank systems still export.

The value date is the line's date. The entry date (`MMDD`) is ignored because it omits the year.
"""

import datetime as dt
import re
from decimal import Decimal

from beancount_mcp.imports.base import ImportFailed, Importer, clean, decode, number
from beancount_mcp.models.imports import Statement, StatementLine

_FIELD = re.compile(r"^:(\d{2}[A-Z]?):", re.MULTILINE)
_BALANCE = re.compile(r"^([CD])(\d{6})([A-Z]{3})([\d,]+)$")
_LINE = re.compile(
    r"^(?P<value>\d{6})(?P<entry>\d{4})?(?P<mark>RC|RD|C|D)(?:[A-Z](?=\d))?(?P<amount>\d+,\d*)"
    r"(?P<type>[NFS][A-Z0-9]{3})(?P<reference>[^\n]*)",
)


def _date(text: str) -> dt.date:
    return dt.date(2000 + int(text[:2]), int(text[2:4]), int(text[4:6]))


def _balance(text: str) -> tuple[Decimal, str, dt.date]:
    match = _BALANCE.match(text.strip())
    if match is None:
        raise ImportFailed(f"cannot read the balance {text.strip()!r}")
    value = number(match.group(4))
    return (-value if match.group(1) == "D" else value), match.group(3), _date(match.group(2))


def _fields(block: str) -> list[tuple[str, str]]:
    marks = list(_FIELD.finditer(block))
    fields = []
    for index, mark in enumerate(marks):
        stop = marks[index + 1].start() if index + 1 < len(marks) else len(block)
        fields.append((mark.group(1), block[mark.end():stop].replace("\r", "").strip("\n").rstrip("-}").strip("\n")))
    return fields


def _narrative(text: str) -> tuple[str | None, str]:
    """The `:86:` text: structured `?NN` subfields when the bank uses them, otherwise free text."""
    if "?" in text and re.search(r"\?\d\d", text):
        parts = dict(re.findall(r"\?(\d\d)([^?]*)", text.replace("\n", "")))
        payee = clean(parts.get("32", "") + parts.get("33", ""))
        return payee or None, clean(" ".join(parts.get(f"2{i}", "") for i in range(10)))
    return None, clean(text.replace("\n", " "))


class Mt940Importer(Importer):
    id = "mt940"
    title = "SWIFT MT940"

    def identify(self, filename: str, data: bytes) -> bool:
        head = data[:8192].decode("latin-1")
        return ":20:" in head and (":60F:" in head or ":60M:" in head)

    def parse(self, data: bytes) -> list[Statement]:
        text = decode(data)
        blocks = re.split(r"(?m)^(?=:20:)", text)
        statements = [self._statement(block) for block in blocks if block.lstrip().startswith(":20:")]
        if not statements:
            raise ImportFailed("no MT940 statement (:20: / :60F:) in this file")
        return statements

    def _statement(self, block: str) -> Statement:
        account = opening = closing = currency = start = end = None
        lines: list[StatementLine] = []
        for tag, body in _fields(block):
            if tag == "25":
                account = clean(body.split("/")[-1])
            elif tag in ("60F", "60M") and opening is None:
                opening, currency, start = _balance(body)
            elif tag in ("62F", "62M"):
                closing, currency, end = _balance(body)
            elif tag == "61":
                match = _LINE.match(body.split("\n")[0].strip())
                if match is None:
                    raise ImportFailed(f"cannot read the statement line {body.splitlines()[0]!r}")
                amount = number(match["amount"])
                negative = match["mark"] in ("D", "RC")
                reference = match["reference"].strip()
                bank_reference = reference.split("//", 1)[1].strip() if "//" in reference else None
                customer = reference.split("//", 1)[0].strip()
                lines.append(StatementLine(
                    date=_date(match["value"]), amount=-amount if negative else amount,
                    reference=bank_reference or (customer if customer and customer.upper() != "NONREF" else None),
                ))
            elif tag == "86" and lines:
                payee, description = _narrative(body)
                lines[-1] = lines[-1].model_copy(update={"payee": payee, "description": description})
        if currency is None:
            raise ImportFailed("the MT940 statement has no opening or closing balance, so its currency is unknown")
        return Statement(format="mt940", account_id=account, currency=currency, opening_balance=opening,
                         closing_balance=closing, start=start, end=end, lines=lines)
