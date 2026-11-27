"""Exact arithmetic on text, for anything that should not be added up by a language model.

A hand-written parser over `Decimal`, with no `eval`, no names and no functions. It is the one place the service
turns a formula such as `18.65 + 6.60 + 7.40` or `(100 - 15) / 2` into a number, and it knows nothing about money,
so a generic calculation tool can use it as it is. Amounts, rates and quantities in the recipes use it through
`models.common.Number`, and currencies are handled one layer up (`amounts.py`).

Grammar, lowest precedence first::

    expression := term (("+" | "-") term)*
    term       := unary (("*" | "/") unary)*
    unary      := ("+" | "-") unary | primary
    primary    := NUMBER | "(" expression ")"

Numbers have digits and an optional decimal point, and may use well-formed thousands commas (`1,200.50`). Exponents,
percent signs, powers and implicit multiplication are refused, so a model never gets a result it did not write.
"""

import re
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal, DivisionByZero, InvalidOperation, localcontext

MAX_LENGTH = 200
MAX_DEPTH = 32
MAX_MAGNITUDE = Decimal(10) ** 15
MINIMUM_PLACES = 2

_NUMBER = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?|\.\d+"
_TOKEN = re.compile(rf"\s*(?:(?P<number>{_NUMBER})|(?P<operator>[-+*/()]))")
_TYPOGRAPHY = str.maketrans({"×": "*", "÷": "/", "−": "-", "–": "-", "（": "(", "）": ")"})
_HINT = "write numbers and + - * / ( ) only"


class CalcError(ValueError):
    """The text is not a formula this module will evaluate. The message says what to send instead."""


@dataclass(frozen=True)
class Evaluation:
    """What a formula came to.

    `value` is the result, rounded half-even to the most decimal places of any number written in the formula, and to
    at least two. `exact` is the unrounded result. A plain number is returned as written, so `12.5` stays `12.5`.
    """

    value: Decimal
    exact: Decimal
    places: int
    expression: str
    is_formula: bool


def _tokens(text: str) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    position = 0
    while position < len(text):
        if text[position:].strip() == "":
            break
        match = _TOKEN.match(text, position)
        if match is None:
            shown = text[position:].lstrip()[:1]
            at = len(text) - len(text[position:].lstrip()) + 1
            raise CalcError(f'cannot read "{shown}" at character {at}: {_HINT}')
        kind = "number" if match.group("number") is not None else "operator"
        found.append((kind, match.group(kind)))
        position = match.end()
    return found


class _Parser:
    def __init__(self, tokens: list[tuple[str, str]]):
        self._tokens = tokens
        self._at = 0
        self._depth = 0
        self.places = 0
        self.operands = 0

    def parse(self) -> Decimal:
        if not self._tokens:
            raise CalcError(f"nothing to calculate: {_HINT}")
        value = self._expression()
        if self._at < len(self._tokens):
            raise CalcError(f'unexpected "{self._tokens[self._at][1]}": write each operator between two numbers, and use * for multiplication')
        return value

    def _peek(self) -> str | None:
        return self._tokens[self._at][1] if self._at < len(self._tokens) else None

    def _expression(self) -> Decimal:
        value = self._term()
        while self._peek() in ("+", "-"):
            operator = self._tokens[self._at][1]
            self._at += 1
            right = self._term()
            value = value + right if operator == "+" else value - right
        return value

    def _term(self) -> Decimal:
        value = self._unary()
        while self._peek() in ("*", "/"):
            operator = self._tokens[self._at][1]
            self._at += 1
            right = self._unary()
            if operator == "*":
                value = value * right
            elif right == 0:
                raise CalcError("division by zero")
            else:
                value = value / right
        return value

    def _unary(self) -> Decimal:
        self._depth += 1
        if self._depth > MAX_DEPTH:
            raise CalcError("too deeply nested")
        try:
            if self._peek() in ("+", "-"):
                sign = self._tokens[self._at][1]
                self._at += 1
                inner = self._unary()
                return -inner if sign == "-" else inner
            return self._primary()
        finally:
            self._depth -= 1

    def _primary(self) -> Decimal:
        if self._at >= len(self._tokens):
            raise CalcError("the formula ends where a number was expected")
        kind, text = self._tokens[self._at]
        self._at += 1
        if kind == "number":
            number = Decimal(text.replace(",", ""))
            self.operands += 1
            self.places = max(self.places, max(0, -number.as_tuple().exponent))  # type: ignore[operator]
            return number
        if text == "(":
            value = self._expression()
            if self._peek() != ")":
                raise CalcError('a "(" is never closed')
            self._at += 1
            return value
        raise CalcError(f'unexpected "{text}": a number was expected here')


def _is_plain_number(tokens: list[tuple[str, str]]) -> bool:
    """One number, with at most signs before it: `40` and `-40` are written values, not calculations."""
    rest = list(tokens)
    while rest and rest[0] in (("operator", "-"), ("operator", "+")):
        rest.pop(0)
    return len(rest) == 1 and rest[0][0] == "number"


def evaluate(expression: str, minimum_places: int = MINIMUM_PLACES) -> Evaluation:
    """Evaluate a formula exactly. Raises `CalcError` with what to send instead."""
    if len(expression) > MAX_LENGTH:
        raise CalcError(f"formula too long ({len(expression)} characters, at most {MAX_LENGTH})")
    text = expression.translate(_TYPOGRAPHY).strip()
    if text.startswith("="):
        text = text[1:]
    parser = _Parser(_tokens(text))
    with localcontext() as context:
        context.prec = 60
        try:
            exact = parser.parse()
        except (InvalidOperation, DivisionByZero) as error:
            raise CalcError("that cannot be calculated") from error
        if abs(exact) >= MAX_MAGNITUDE:
            raise CalcError("the result is too large")
        formula = not _is_plain_number(parser._tokens)
        if not formula:
            return Evaluation(value=exact, exact=exact, places=parser.places, expression=text.strip(), is_formula=False)
        places = max(minimum_places, parser.places)
        value = exact.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_EVEN)
    return Evaluation(value=value, exact=exact, places=places, expression=text.strip(), is_formula=True)
