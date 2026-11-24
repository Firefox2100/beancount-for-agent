import shutil
import tempfile
import threading
from datetime import date
from pathlib import Path

from beancount_mcp.ledger import sidecar
from beancount_mcp.ledger.engine import Ledger
from beancount_mcp.ledger.errors import (
    InvalidLedgerId,
    LedgerExists,
    LedgerNotFound,
    UnsupportedStructure,
)
from beancount_mcp.ledger.layout import MAIN_FILE, initial_files, structure_problems
from beancount_mcp.models import LEDGER_ID_RE, CreateLedgerRequest, Layout


class LedgerStore:
    """Ledgers on the file system: one directory per ledger under `data_dir`."""

    def __init__(self, data_dir: Path, layout: Layout):
        self.data_dir = data_dir
        self.layout = layout
        self._locks: dict[str, threading.RLock] = {}
        self._locks_guard = threading.RLock()

    def list_ids(self) -> list[str]:
        if not self.data_dir.is_dir():
            return []
        return sorted(
            path.name
            for path in self.data_dir.iterdir()
            if LEDGER_ID_RE.match(path.name) and (path / MAIN_FILE).is_file()
        )

    def create(self, request: CreateLedgerRequest, today: date | None = None) -> Ledger:
        root = self._root(request.id)
        if root.exists():
            raise LedgerExists(request.id)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        staging = Path(tempfile.mkdtemp(prefix=".creating-", dir=self.data_dir))
        try:
            files = initial_files(
                self.layout,
                request.title,
                request.operating_currencies,
                today or date.today(),
            )
            for name, content in files.items():
                target = staging / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content)
            sidecar.write_layout(staging, self.layout)
            staging.rename(root)
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        return Ledger(request.id, root, self.layout, self._lock_for(request.id))

    def open(self, ledger_id: str) -> Ledger:
        root = self._root(ledger_id)
        if not (root / MAIN_FILE).is_file():
            raise LedgerNotFound(ledger_id)

        layout = sidecar.read_layout(root)
        if layout is None:
            layout = self._detect_layout(ledger_id, root)
            sidecar.write_layout(root, layout)
        return Ledger(ledger_id, root, layout, self._lock_for(ledger_id))

    def _detect_layout(self, ledger_id: str, root: Path) -> Layout:
        candidates = [self.layout, *(item for item in Layout if item is not self.layout)]
        reasons = []
        for candidate in candidates:
            problems = structure_problems(root, candidate)
            if not problems:
                return candidate
            reasons.append(f"{candidate}: {'; '.join(problems)}")
        raise UnsupportedStructure(f"{ledger_id} matches no supported layout ({' | '.join(reasons)})")

    def _lock_for(self, ledger_id: str) -> threading.RLock:
        with self._locks_guard:
            return self._locks.setdefault(ledger_id, threading.RLock())

    def _root(self, ledger_id: str) -> Path:
        if not LEDGER_ID_RE.match(ledger_id):
            raise InvalidLedgerId(ledger_id)
        return self.data_dir / ledger_id
