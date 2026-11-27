"""Receipt files: stored and linked by a person. What an agent may read of one is decided separately."""

from typing import Annotated

from fastapi import APIRouter, File, Form, Response, UploadFile, status

from beancount_mcp.api.deps import CallerDep, ReceiptServiceDep
from beancount_mcp.models.receipts import Receipt
from beancount_mcp.services.ledgers import WriteResult

router = APIRouter(prefix="/ledgers/{ledger_id}", tags=["receipts"])


@router.get("/receipts")
async def list_receipts(ledger_id: str, service: ReceiptServiceDep) -> list[Receipt]:
    """Every image and PDF in the ledger's documents folder, uploaded or put there by hand, and whether the ledger links it."""
    return await service.listing(ledger_id)


@router.post("/receipts", status_code=status.HTTP_201_CREATED)
async def upload_receipt(
    ledger_id: str,
    service: ReceiptServiceDep,
    caller: CallerDep,
    file: Annotated[UploadFile, File(description="A JPEG, PNG or WebP image, or a PDF.")],
    transaction: Annotated[str | None, Form(description="Link it to this transaction at once.")] = None,
) -> Receipt:
    content = await file.read(service.max_bytes + 1)
    receipt = await service.upload(ledger_id, file.filename or "receipt", content, caller)
    if transaction:
        await service.attach(ledger_id, transaction, receipt.path, caller)
        receipt = receipt.model_copy(update={"linked": True})
    return receipt


@router.post("/receipts/attach")
async def attach_receipt(ledger_id: str, transaction: str, path: str, service: ReceiptServiceDep, caller: CallerDep) -> WriteResult:
    """Link a stored receipt to a transaction."""
    return await service.attach(ledger_id, transaction, path, caller)


@router.get("/receipts/file")
async def receipt_file(ledger_id: str, path: str, service: ReceiptServiceDep) -> Response:
    """The receipt itself, for a person to look at."""
    content, media_type = await service.file(ledger_id, path)
    return Response(content, media_type=media_type, headers={"X-Content-Type-Options": "nosniff", "Content-Security-Policy": "sandbox"})
