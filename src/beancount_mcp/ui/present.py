"""Turn a stored operation into something a person can check before approving it."""

from dataclasses import dataclass, field

from beancount_mcp.models import Operation


@dataclass
class Block:
    title: str
    postings: list[tuple[str, str]] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)


def grouped(value) -> str:
    """A decimal written with commas between thousands (`-1,234,567.80`), digits otherwise as given.

    Works on the text, so no precision is lost to a float.
    """
    text = str(value)
    sign, digits = (text[0], text[1:]) if text[:1] in ("+", "-") else ("", text)
    whole, point, fraction = digits.partition(".")
    if not whole.isdigit():
        return text
    return f"{sign}{int(whole):,}{point}{fraction}"


def money(amount) -> str:
    return f"{grouped(amount.number)} {amount.currency}" if amount is not None else ""


def held(values: dict) -> str:
    """Per-currency amounts on one line: `1,200.00 GBP · 30 USD`."""
    return " · ".join(f"{grouped(number)} {currency}" for currency, number in values.items()) or "—"


def line_chart(points: list, keys: tuple[str, ...]) -> dict:
    """SVG paths for the position chart, scaled to the reference values that exist. `None` when none do."""
    series = {key: [None if getattr(p, key).reference_value is None else float(getattr(p, key).reference_value.number) for p in points] for key in keys}
    known = [v for values in series.values() for v in values if v is not None]
    if not known:
        return {}
    low, high = min(known + [0.0]), max(known + [0.0])
    span = (high - low) or 1.0
    top, bottom, step = 12.0, 128.0, 288 / max(len(points) - 1, 1)
    y = lambda v: round(bottom - (v - low) / span * (bottom - top), 1)  # noqa: E731
    lines = {}
    for key, values in series.items():
        parts, dots = [], []
        for index, v in enumerate(values):
            if v is None:
                continue
            x = round(16 + index * step, 1)
            parts.append(f"{'M' if not parts or values[index - 1] is None else 'L'} {x} {y(v)}")
            dots.append({"x": x, "y": y(v), "title": f"{points[index].date}: {grouped(f'{v:.2f}')}"})
        lines[key] = {"path": " ".join(parts), "dots": dots}
    return {"lines": lines, "zero": y(0.0), "from": str(points[0].date), "to": str(points[-1].date)}


def describe(operation: Operation) -> list[Block]:
    match operation.kind:
        case "add_transaction" | "update_transaction":
            t = operation.transaction
            head = " · ".join(str(part) for part in (t.date, t.payee, t.narration) if part)
            verb = "Add" if operation.kind == "add_transaction" else f"Change {operation.id}"
            postings = []
            for p in t.postings:
                text = money(p.units) + (f" @ {money(p.price)}" if p.price else "")
                postings.append((p.account, text))
            return [Block(f"{verb}: {head}", postings, [f"#{tag}" for tag in t.tags] + [f"^{link}" for link in t.links])]
        case "batch":
            return [block for member in operation.operations for block in describe(member)]
        case "open_account":
            lines = [f"currencies: {', '.join(operation.currencies)}"] if operation.currencies else []
            if operation.type:
                lines.append(f"type: {operation.type}")
            if operation.details:
                lines.append("bank details: " + ", ".join(operation.details.model_dump(exclude_none=True)))
            return [Block(f"Open {operation.account} from {operation.date}", lines=lines)]
        case "close_account":
            return [Block(f"Close {operation.account} on {operation.date}")]
        case "reconcile":
            line = f"Balance of {operation.account} is {money(operation.amount)} on {operation.date}"
            return [Block(line, lines=[f"difference booked against {operation.pad_account}"] if operation.pad_account else [])]
        case "set_account_details":
            changes = [f"set {name}" for name in operation.set.model_dump(exclude_none=True)]
            changes += [f"clear {name}" for name in operation.clear]
            return [Block(f"Bank details of {operation.account}", lines=changes)]
        case "delete_transaction" | "delete_directive":
            return [Block(f"Delete {operation.id}")]
        case _:
            return [Block(operation.kind.replace("_", " "))]
