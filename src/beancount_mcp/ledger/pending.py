import os
import re
import uuid
from pathlib import Path

from beancount_mcp.ledger.errors import ChangeNotFound
from beancount_mcp.ledger.sidecar import sidecar_dir
from beancount_mcp.models import ChangeStatus, PendingChange

_ID_RE = re.compile(r"^[0-9a-f]{32}$")


class PendingStore:
    """Proposed changes of one ledger, one JSON file each in its sidecar."""

    def __init__(self, ledger_root: Path):
        self._dir = sidecar_dir(ledger_root) / "changes"

    @staticmethod
    def new_id() -> str:
        return uuid.uuid4().hex

    def save(self, change: PendingChange) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        target = self._dir / f"{change.id}.json"
        temp = target.with_suffix(".tmp")
        temp.write_text(change.model_dump_json(indent=2))
        os.replace(temp, target)

    def get(self, change_id: str) -> PendingChange:
        path = self._dir / f"{change_id}.json"
        if not _ID_RE.match(change_id) or not path.is_file():
            raise ChangeNotFound(change_id)
        return PendingChange.model_validate_json(path.read_text())

    def list(self, status: ChangeStatus | None = None) -> list[PendingChange]:
        if not self._dir.is_dir():
            return []
        changes = [PendingChange.model_validate_json(p.read_text()) for p in self._dir.glob("*.json")]
        if status is not None:
            changes = [change for change in changes if change.status is status]
        return sorted(changes, key=lambda change: change.created_at)
