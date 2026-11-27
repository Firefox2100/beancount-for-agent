"""Bank statements. A person uploads one for an account; an agent reviews it and proposes the entries.

Uploading and deleting are for users only: a file is the one input in this flow that has not passed through the
approval gate, so an agent cannot add one.
"""

from typing import Annotated

from fastapi import APIRouter, File, Form, Query, Response, UploadFile, status

from beancount_mcp.api.deps import CallerDep, ImportServiceDep
from beancount_mcp.ledger.errors import ApprovalRequired
from beancount_mcp.models.imports import FormatInfo, ImportReview, ImportSummary

router = APIRouter(prefix="/ledgers/{ledger_id}", tags=["imports"])


@router.get("/import-formats")
async def import_formats(ledger_id: str, service: ImportServiceDep) -> list[FormatInfo]:
    """The file formats that can be read: the built-in standards and any installed plugins."""
    return service.formats()


@router.get("/imports")
async def list_imports(ledger_id: str, service: ImportServiceDep) -> list[ImportSummary]:
    return await service.summaries(ledger_id)


@router.post("/imports", status_code=status.HTTP_201_CREATED)
async def upload_statement(
    ledger_id: str,
    service: ImportServiceDep,
    caller: CallerDep,
    file: Annotated[UploadFile, File(description="The statement as the bank exports it.")],
    account: Annotated[str, Form(description="Full name of the account the statement belongs to.")],
    format: Annotated[str | None, Form(description="An importer id. Left out, the file is recognised.")] = None,
) -> list[ImportSummary]:
    if caller.actor == "agent":
        raise ApprovalRequired("statements are uploaded by the user")
    data = await file.read(service.max_bytes + 1)
    created = await service.upload(ledger_id, account, file.filename or "statement", data, format or None)
    ids = {item.id for item in created}
    return [summary for summary in await service.summaries(ledger_id) if summary.id in ids]


@router.get("/imports/{import_id}")
async def get_import(
    ledger_id: str,
    import_id: str,
    service: ImportServiceDep,
    only_new: bool = False,
    limit: Annotated[int, Query(ge=0, le=2000)] = 200,
) -> ImportReview:
    return await service.review(ledger_id, import_id, only_new, limit)


@router.delete("/imports/{import_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_import(ledger_id: str, import_id: str, service: ImportServiceDep, caller: CallerDep) -> Response:
    if caller.actor == "agent":
        raise ApprovalRequired("statements are deleted by the user")
    await service.delete(ledger_id, import_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
