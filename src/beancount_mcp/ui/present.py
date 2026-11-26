"""Turn a stored operation into something a person can check before approving it."""

from dataclasses import dataclass, field

from beancount_mcp.models import Operation


@dataclass
class Block:
    title: str
    postings: list[tuple[str, str]] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)


def money(amount) -> str:
    return f"{amount.number} {amount.currency}" if amount is not None else ""


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
