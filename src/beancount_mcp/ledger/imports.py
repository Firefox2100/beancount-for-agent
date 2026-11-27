import os
import re
import uuid
from pathlib import Path

from beancount_mcp.ledger.errors import ImportNotFound
from beancount_mcp.ledger.sidecar import sidecar_dir
from beancount_mcp.models.imports import StatementImport

_ID_RE = re.compile(r"^[0-9a-f]{32}$")


class ImportStore:
    """Uploaded statements of one ledger, one JSON file each in its sidecar. Only the parsed statement is kept, never the original file."""

    def __init__(self, ledger_root: Path):
        self._dir = sidecar_dir(ledger_root) / "imports"

    @staticmethod
    def new_id() -> str:
        return uuid.uuid4().hex

    def save(self, item: StatementImport) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        target = self._dir / f"{item.id}.json"
        temp = target.with_suffix(".tmp")
        temp.write_text(item.model_dump_json(indent=2))
        os.replace(temp, target)

    def get(self, import_id: str) -> StatementImport:
        path = self._dir / f"{import_id}.json"
        if not _ID_RE.match(import_id) or not path.is_file():
            raise ImportNotFound(import_id)
        return StatementImport.model_validate_json(path.read_text())

    def list(self) -> list[StatementImport]:
        if not self._dir.is_dir():
            return []
        return sorted((StatementImport.model_validate_json(p.read_text()) for p in self._dir.glob("*.json")), key=lambda i: i.created_at)

    def delete(self, import_id: str) -> None:
        self.get(import_id)
        (self._dir / f"{import_id}.json").unlink()
