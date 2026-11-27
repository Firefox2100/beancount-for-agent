"""Receipts: stored by a person, linked to transactions, shown wherever a change is checked against its source, and,
when the deployment allows it, read for an agent."""

import asyncio
import re
from dataclasses import dataclass

from beancount_mcp.ledger import receipt_reading, receipts
from beancount_mcp.ledger.errors import ApprovalRequired, ReceiptRefused
from beancount_mcp.ledger.store import LedgerStore
from beancount_mcp.models import AttachReceipt, Caller
from beancount_mcp.models.receipts import Receipt, ReceiptReading
from beancount_mcp.ocr import OcrRegistry
from beancount_mcp.ocr.base import OcrUnavailable
from beancount_mcp.services.ledgers import LedgerService, WriteResult

MEDIA_TYPES = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp", "pdf": "application/pdf"}
_TRANSACTION_ID = re.compile(r"^[0-9a-f]{32}$")


@dataclass(frozen=True)
class ReceiptAccess:
    """What an agent may do with a receipt in this deployment. With neither, it cannot read one and is not told to."""

    text: bool = False
    images: bool = False

    @property
    def enabled(self) -> bool:
        return self.text or self.images


class ReceiptService:
    def __init__(
        self, store: LedgerStore, ledgers: LedgerService, max_bytes: int, ocr: OcrRegistry | None = None,
        access: ReceiptAccess = ReceiptAccess(), backend: str = "rapidocr", max_pages: int = 10,
    ):
        self._store = store
        self._ledgers = ledgers
        self._max_bytes = max_bytes
        self._ocr = ocr or OcrRegistry()
        self.access = access
        self._backend = backend
        self._max_pages = max_pages

    @property
    def max_bytes(self) -> int:
        return self._max_bytes

    async def upload(self, ledger_id: str, filename: str, content: bytes, caller: Caller) -> Receipt:
        """Store a file. Only a person does this: a file is not something an agent can supply."""
        if caller.actor == "agent":
            raise ApprovalRequired("receipts are uploaded by the user")

        def run() -> Receipt:
            ledger = self._store.open(ledger_id)
            path = receipts.save(ledger.root, filename, content, self._max_bytes)
            return receipts.describe(ledger.root, ledger.root / path, receipts.linked_paths(ledger.load()[0], ledger.root))

        return await asyncio.to_thread(run)

    async def listing(self, ledger_id: str) -> list[Receipt]:
        def run() -> list[Receipt]:
            ledger = self._store.open(ledger_id)
            return receipts.listing(ledger.root, ledger.load()[0])

        return await asyncio.to_thread(run)

    async def file(self, ledger_id: str, path: str) -> tuple[bytes, str]:
        """A receipt's bytes and media type, for the pages a person checks a change on."""
        def run() -> tuple[bytes, str]:
            root = self._store.open(ledger_id).root
            content = receipts.resolve(root, path).read_bytes()
            extension = receipts.sniff(content)
            if extension is None:
                raise ReceiptRefused(f"{path} is not an image or PDF")
            return content, MEDIA_TYPES[extension]

        return await asyncio.to_thread(run)

    async def attach(self, ledger_id: str, transaction_id: str, path: str, caller: Caller) -> WriteResult:
        """Link a stored receipt to an existing transaction. A person's edit, applied at once."""
        if caller.actor == "agent":
            raise ApprovalRequired("receipts are attached by the user")
        await asyncio.to_thread(lambda: receipts.resolve(self._store.open(ledger_id).root, path))
        return await self._ledgers.apply(ledger_id, AttachReceipt(id=transaction_id, path=path), caller, None)

    async def find(self, ledger_id: str, reference: str) -> str:
        """The path a loose reference names: a path, a file name, or the id of a transaction with one receipt."""
        if reference.strip().lower() == "attached":
            raise ReceiptRefused(
                "\"attached\" means the image the user attached to the chat, which only a harness plugin can store. "
                "Ask the user to upload the receipt in the web interface (Receipts) and use its path or file name"
            )
        known = await self.listing(ledger_id)
        if reference.startswith(receipts.DOCUMENTS_DIR + "/"):
            return reference
        if _TRANSACTION_ID.match(reference):
            transaction = await self._ledgers.get_transaction(ledger_id, reference)
            names = [value for key, value in transaction.meta.items() if key.startswith("document")]
            matches = [r.path for r in known if r.name in names or r.path.rsplit("/", 1)[-1] in names]
            if not matches:
                raise ReceiptRefused("that transaction has no receipt")
            if len(matches) > 1:
                raise ReceiptRefused(f"that transaction has {len(matches)} receipts ({', '.join(matches)}): name one")
            return matches[0]
        matches = [r.path for r in known if r.name == reference]
        if len(matches) == 1:
            return matches[0]
        if not matches:
            raise ReceiptRefused(f"no receipt called {reference!r}. Use the path from the transaction's document note")
        raise ReceiptRefused(f"several receipts are called {reference!r}: {', '.join(matches)}")

    async def read(self, ledger_id: str, reference: str, with_pictures: bool) -> tuple[ReceiptReading, list[tuple[bytes, str]]]:
        """What an agent may see of a receipt: its text (read on first use, then kept) and/or its picture, as configured."""
        if not self.access.enabled:
            raise ReceiptRefused("reading receipts is switched off here: ask the user what the receipt says")
        path = await self.find(ledger_id, reference)

        def run() -> tuple[ReceiptReading, list[tuple[bytes, str]]]:
            root = self._store.open(ledger_id).root
            content = receipts.resolve(root, path).read_bytes()
            kind = receipts.sniff(content)
            pictures = receipt_reading.pictures(content) if with_pictures and self.access.images else []
            if not self.access.text:
                reading = ReceiptReading(path=path, kind="pdf" if kind == "pdf" else "image", pages=[])
            else:
                cache = receipt_reading.ReadingCache(root)
                key = cache.key(content)
                reading = cache.get(key, path)
                if reading is None:
                    try:
                        reading = receipt_reading.read(content, path, self._ocr, self._backend, self._max_pages)
                    except OcrUnavailable as error:
                        raise ReceiptRefused(str(error)) from None
                    cache.put(key, reading)
            return reading.model_copy(update={"images_sent": bool(pictures)}), pictures

        return await asyncio.to_thread(run)
