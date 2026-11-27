"""Receipt files stored in a ledger's documents folder.

A receipt is any image or PDF under `documents/` that the ledger links with a `document` entry. The service stores
what a person uploads there, and also accepts files put there by hand, so everything is addressed by its path
relative to the ledger folder. The kind of a file is decided by its content, never by its name.
"""

import datetime as dt
import hashlib
import os
import re
from pathlib import Path

from beancount.core import data

from beancount_mcp.ledger.errors import ReceiptRefused
from beancount_mcp.models.receipts import Receipt

DOCUMENTS_DIR = "documents"
RECEIPTS_DIR = "documents/receipts"
EXTENSIONS = {"jpg": "image", "png": "image", "webp": "image", "pdf": "pdf"}
_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def sniff(content: bytes) -> str | None:
    """The extension a file really has, from its first bytes. `None` for anything that is not a supported type."""
    if content.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "webp"
    if content.startswith(b"%PDF-"):
        return "pdf"
    return None


def resolve(root: Path, relative: str) -> Path:
    """The file a receipt path names, once it is known to sit in the documents folder and be a supported type."""
    parts = relative.split("/")
    if parts[0] != DOCUMENTS_DIR or len(parts) < 2 or any(p in ("", ".", "..") for p in parts) or "\\" in relative:
        raise ReceiptRefused(f"{relative!r} is not a receipt path: it lives under {DOCUMENTS_DIR}/, for example {RECEIPTS_DIR}/2026/lunch.jpg")
    path = root / relative
    if not path.is_file() or not path.resolve().is_relative_to((root / DOCUMENTS_DIR).resolve()):
        raise ReceiptRefused(f"there is no receipt at {relative}")
    if path.suffix.lower().lstrip(".").replace("jpeg", "jpg") not in EXTENSIONS:
        raise ReceiptRefused(f"{relative} is not an image or PDF")
    return path


def describe(root: Path, path: Path, linked: set[str]) -> Receipt:
    content = path.read_bytes()
    relative = path.relative_to(root).as_posix()
    extension = sniff(content)
    return Receipt(
        path=relative, name=path.name, size=len(content), sha256=hashlib.sha256(content).hexdigest(),
        kind=EXTENSIONS.get(extension or "", "other"), linked=relative in linked,
        added=dt.datetime.fromtimestamp(path.stat().st_mtime, dt.UTC),
    )


def linked_paths(entries: list, root: Path) -> set[str]:
    return {
        Path(entry.filename).relative_to(root).as_posix()
        for entry in entries if isinstance(entry, data.Document) and Path(entry.filename).is_relative_to(root)
    }


def save(root: Path, filename: str, content: bytes, max_bytes: int, today: dt.date | None = None) -> str:
    """Store an upload and return its path. The same content is stored once."""
    if len(content) > max_bytes:
        raise ReceiptRefused(f"the file is {len(content):,} bytes; at most {max_bytes:,} are accepted")
    extension = sniff(content)
    if extension is None:
        raise ReceiptRefused("that is not a supported receipt: send a JPEG, PNG or WebP image, or a PDF")
    digest = hashlib.sha256(content).hexdigest()[:10]
    existing = next((p for p in (root / RECEIPTS_DIR).rglob(f"{digest}-*") if p.is_file()), None) if (root / RECEIPTS_DIR).is_dir() else None
    if existing is not None:
        return existing.relative_to(root).as_posix()
    stem = _SAFE.sub("-", Path(filename).stem).strip("-.")[:60] or "receipt"
    target = root / RECEIPTS_DIR / str((today or dt.date.today()).year) / f"{digest}-{stem}.{extension}"
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.name + ".tmp")
    temp.write_bytes(content)
    os.replace(temp, target)
    return target.relative_to(root).as_posix()


def attach(operation, paths: list[str], root: Path):
    """Add receipts to a change that records a transaction: the `document` note on it and a document entry for each file."""
    from beancount_mcp.models import AddDirective, AddTransaction, Batch, DocumentDirective

    for path in paths:
        resolve(root, path)
    members = list(operation.operations) if isinstance(operation, Batch) else [operation]
    index = next((i for i, member in enumerate(members) if isinstance(member, AddTransaction)), None)
    if index is None:
        raise ReceiptRefused("a receipt can only be attached to a change that records a transaction")
    transaction = members[index].transaction
    meta = dict(transaction.meta)
    account = next((p.account for p in transaction.postings if p.account.split(":")[0] in ("Assets", "Liabilities")), transaction.postings[0].account)
    extras = []
    for path in paths:
        name = path.rsplit("/", 1)[-1]
        if name not in meta.values():
            key = "document" if "document" not in meta else next(f"document-{n}" for n in range(2, 100) if f"document-{n}" not in meta)
            meta[key] = name
        extras.append(AddDirective(directive=DocumentDirective(date=transaction.date, account=account, path=path)))
    members[index] = AddTransaction(transaction=transaction.model_copy(update={"meta": meta}))
    return Batch(operations=[*members, *extras])


def listing(root: Path, entries: list) -> list[Receipt]:
    folder = root / DOCUMENTS_DIR
    if not folder.is_dir():
        return []
    linked = linked_paths(entries, root)
    files = [p for p in folder.rglob("*") if p.is_file() and p.suffix.lower().lstrip(".").replace("jpeg", "jpg") in EXTENSIONS]
    return sorted((describe(root, p, linked) for p in files), key=lambda r: r.added, reverse=True)
