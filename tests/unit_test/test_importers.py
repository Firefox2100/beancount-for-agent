from decimal import Decimal
from pathlib import Path

import pytest

from beancount_mcp.imports import default_importers
from beancount_mcp.imports.base import ImportFailed, Importer
from beancount_mcp.imports.registry import ImporterRegistry

SAMPLES = Path(__file__).parents[1] / "samples"
OFX_SGML, OFX_XML, CAMT, MT940 = (
    (SAMPLES / name).read_text() for name in ("checking.ofx", "card.ofx", "checking.camt053.xml", "checking.mt940")
)
REGISTRY = default_importers(load_plugins=False)


def read(text: str, name: str = "statement"):
    return REGISTRY.find(name, text.encode()).parse(text.encode())


def amounts(statement):
    return [(line.date.isoformat(), line.amount) for line in statement.lines]


def test_ofx_sgml_is_read_with_signs_dates_and_references():
    (statement,) = read(OFX_SGML)
    assert statement.format == "ofx" and statement.currency == "USD" and statement.account_id == "00112233"
    assert amounts(statement) == [("2026-03-02", Decimal("-12.50")), ("2026-03-05", Decimal("-1234.56")), ("2026-03-09", Decimal("2500.00"))]
    first = statement.lines[0]
    assert (first.payee, first.description, first.reference) == ("Cafe Nero", "Lunch & coffee", "A1")
    assert statement.lines[1].description == "Landlord"
    assert statement.closing_balance == Decimal("1252.94") and str(statement.end) == "2026-03-10"


def test_ofx_xml_credit_card_is_read():
    (statement,) = read(OFX_XML)
    assert statement.currency == "GBP" and statement.lines[0].amount == Decimal("-30.00") and statement.closing_balance == Decimal("-30.00")


def test_camt053_reads_balances_booked_entries_and_counterparties():
    (statement,) = read(CAMT)
    assert statement.format == "camt053" and statement.account_id == "GB29NWBK60161331926819"
    assert (statement.opening_balance, statement.closing_balance) == (Decimal("1000.00"), Decimal("2252.94"))
    assert amounts(statement) == [("2026-03-02", Decimal("-12.50")), ("2026-03-05", Decimal("-1234.56")), ("2026-03-09", Decimal("2500.00"))]
    assert statement.lines[0].payee == "Cafe Nero" and statement.lines[0].reference == "R1"
    assert statement.lines[1].description == "Rent" and statement.lines[2].payee == "Employer"


def test_mt940_reads_signs_references_and_narratives():
    (statement,) = read(MT940)
    assert statement.format == "mt940" and statement.account_id == "NWBK60161331926819"
    assert (statement.opening_balance, statement.closing_balance) == (Decimal("1000.00"), Decimal("2252.94"))
    assert amounts(statement) == [("2026-03-02", Decimal("-12.50")), ("2026-03-05", Decimal("-1234.56")), ("2026-03-09", Decimal("2500.00"))]
    assert [line.reference for line in statement.lines] == ["R1", "R2", "R3"]
    assert statement.lines[0].payee == "Cafe Nero" and statement.lines[1].description == "Rent for March"


def test_the_same_statement_in_every_format_adds_up_to_its_closing_balance():
    for text in (CAMT, MT940):
        (statement,) = read(text)
        assert statement.opening_balance + sum(line.amount for line in statement.lines) == statement.closing_balance


def test_mt940_reversals_flip_the_sign():
    text = ":20:X\n:60F:C260301GBP10,00\n:61:2603020302RC5,00NTRFNONREF\n:62F:C260302GBP5,00\n"
    (statement,) = read(text)
    assert statement.lines[0].amount == Decimal("-5.00")


def test_camt_with_a_dtd_is_refused():
    bomb = '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><Document><BkToCstmrStmt><Stmt/></BkToCstmrStmt></Document>'
    with pytest.raises(ImportFailed, match="DTD"):
        REGISTRY.get("camt053").parse(bomb.encode())


@pytest.mark.parametrize("name,data,fragment", [
    ("a.ofx", b"OFXHEADER:100\n<OFX><SIGNONMSGSRSV1></SIGNONMSGSRSV1></OFX>", "no bank or credit-card statement"),
    ("a.xml", b"<Document><BkToCstmrStmt></BkToCstmrStmt></Document>", "no statement"),
    ("a.xml", b"<Document", "not valid XML"),
    ("a.sta", b":20:X\n:25:1\n", "no opening or closing balance"),
])
def test_unreadable_files_say_why(name, data, fragment):
    importer = next(i for i in REGISTRY.all() if i.id == {"a.ofx": "ofx", "a.xml": "camt053", "a.sta": "mt940"}[name])
    with pytest.raises(ImportFailed, match=fragment):
        importer.parse(data)


def test_an_unrecognised_file_names_the_formats_available():
    with pytest.raises(ImportFailed, match="ofx"):
        REGISTRY.find("notes.txt", b"hello")
    with pytest.raises(ImportFailed, match="no importer called"):
        REGISTRY.get("nope")


class Csv(Importer):
    id, title = "toy-csv", "Toy bank CSV"

    def identify(self, filename, data):
        return filename.endswith(".toy")

    def parse(self, data):
        from datetime import date

        from beancount_mcp.models.imports import Statement, StatementLine
        day, amount = data.decode().split(",")
        return [Statement(format=self.id, currency="USD", lines=[StatementLine(date=date.fromisoformat(day), amount=Decimal(amount))])]


def test_a_plugin_registers_through_an_entry_point_callable():
    class Point:
        def load(self):
            return lambda registry: registry.register(Csv())

    registry = ImporterRegistry()
    registry.load_plugins([Point()])
    assert registry.find("x.toy", b"").parse(b"2026-01-02,5")[0].lines[0].amount == Decimal("5")
    with pytest.raises(ValueError, match="already registered"):
        registry.register(Csv())


def test_a_plugin_that_cannot_identify_does_not_break_recognition():
    class Broken(Csv):
        id = "broken"

        def identify(self, filename, data):
            raise RuntimeError("boom")

    registry = default_importers(load_plugins=False)
    registry.register(Broken())
    assert registry.find("a.ofx", OFX_SGML.encode()).id == "ofx"
