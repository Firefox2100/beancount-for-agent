import hashlib
import os
import tempfile
import threading
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from beancount import loader

from beancount_mcp.ledger import read
from beancount_mcp.ledger.edit import apply_operation
from beancount_mcp.ledger.errors import ChangeRejected, StaleVersion
from beancount_mcp.ledger.receipts import DOCUMENTS_DIR
from beancount_mcp.ledger.layout import MAIN_FILE, SIDECAR_DIR
from beancount_mcp.models.ledger import LedgerOptions
from beancount_mcp.models import (
    AccountBalance,
    AccountInfo,
    Layout,
    LedgerError,
    LedgerInfo,
    LedgerStatus,
    Operation,
    Record,
    Transaction,
)

# The default loader drops pickle caches next to the ledger files.
loader.initialize(use_cache=False)


@dataclass(frozen=True)
class AppliedChange:
    version: str
    transaction_id: str | None = None
    record_id: str | None = None
    account: str | None = None


APPLY_ATTEMPTS = 3


@dataclass(frozen=True)
class Ledger:
    id: str
    root: Path
    layout: Layout
    lock: threading.RLock = field(default_factory=threading.RLock, compare=False)

    @property
    def main_file(self) -> Path:
        return self.root / MAIN_FILE

    def ledger_files(self) -> list[Path]:
        return sorted(
            path
            for path in self.root.rglob("*.beancount")
            if SIDECAR_DIR not in path.relative_to(self.root).parts
        )

    def version(self) -> str:
        """Hash of every ledger file's path and content, excluding the sidecar."""
        digest = hashlib.sha256()
        for path in self.ledger_files():
            digest.update(path.relative_to(self.root).as_posix().encode())
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
        return digest.hexdigest()

    def info(self) -> LedgerInfo:
        return LedgerInfo(id=self.id, layout=self.layout, version=self.version())

    def load(self) -> tuple[list, list[LedgerError]]:
        entries, errors, _ = loader.load_file(str(self.main_file))
        return entries, [_convert_error(error, self.root) for error in errors]

    def operating_currencies(self) -> list[str]:
        """Configured reporting currencies, without exposing raw ledger options at the service boundary."""
        _, _, options = loader.load_file(str(self.main_file))
        return list(options.get("operating_currency", []))

    def options(self) -> LedgerOptions:
        """The options this service knows how to change."""
        _, _, options = loader.load_file(str(self.main_file))
        return LedgerOptions(
            title=options.get("title") or None,
            operating_currency=list(options.get("operating_currency", [])),
            render_commas=bool(options.get("render_commas", False)),
            booking_method=str(getattr(options.get("booking_method"), "value", "STRICT")),
        )

    def status(self) -> LedgerStatus:
        _, errors = self.load()
        return LedgerStatus(**self.info().model_dump(), errors=errors)

    def accounts(self) -> list[AccountInfo]:
        return read.list_accounts(self.load()[0])

    def balances(self, as_of: date | None) -> list[AccountBalance]:
        return read.balances(self.load()[0], as_of)

    def transactions(self, **filters) -> list[Transaction]:
        return read.list_transactions(self.load()[0], **filters)

    def transaction(self, identifier: str) -> Transaction | None:
        entry = read.find_transaction(self.load()[0], identifier)
        return None if entry is None else read.to_transaction(entry)

    def records(self, **filters) -> list[Record]:
        return read.list_records(self.load()[0], root=self.root, **filters)

    def record(self, identifier: str) -> Record | None:
        entry = read.find_record(self.load()[0], identifier)
        return None if entry is None else read.to_record(entry, self.root)

    def fingerprint(self, identifier: str) -> str | None:
        """Content hash of the transaction or record with this id, if it exists."""
        entries = self.load()[0]
        entry = read.find_transaction(entries, identifier) or read.find_record(entries, identifier)
        return None if entry is None else read.entry_fingerprint(entry)

    def apply(
        self,
        operation: Operation,
        expected_version: str | None = None,
        dry_run: bool = False,
    ) -> AppliedChange:
        """Validate `operation` on a staged copy, then commit it atomically.

        Nothing is written unless the change introduces no new ledger errors and
        the ledger is still at the version the change was computed against. With
        `dry_run` the full validation runs but nothing is committed.
        """
        with self.lock:
            for attempt in range(1, APPLY_ATTEMPTS + 1):
                version = self.version()
                if expected_version is not None and expected_version != version:
                    raise StaleVersion(f"ledger is at version {version}, not {expected_version}")
                try:
                    return self._apply_once(operation, version, dry_run)
                except _ChangedUnderneath:
                    # Someone else (Fava, an editor) wrote a ledger file while this change was being prepared. The
                    # edit is computed from line positions, so it is simply computed again on what is there now.
                    # A caller that pinned a version asked for exactly that state and gets the conflict instead.
                    if expected_version is not None or attempt == APPLY_ATTEMPTS:
                        raise StaleVersion("ledger changed while the change was being prepared") from None
        raise AssertionError("unreachable")

    def _apply_once(self, operation: Operation, version: str, dry_run: bool) -> AppliedChange:
        with tempfile.TemporaryDirectory() as temp:
            stage = Path(temp)
            self._copy_to(stage)
            entries, baseline = loader.load_file(str(stage / MAIN_FILE))[:2]
            touched = apply_operation(stage, self.layout, entries, operation)
            errors = loader.load_file(str(stage / MAIN_FILE))[1]

            introduced = _introduced_errors(baseline, errors)
            if introduced:
                raise ChangeRejected([_convert_error(error, stage) for error in introduced])

            if dry_run:
                return AppliedChange(version=version, **touched)
            if self.version() != version:
                raise _ChangedUnderneath()
            self._commit_from(stage)
        return AppliedChange(version=self.version(), **touched)

    def _copy_to(self, stage: Path) -> None:
        documents = self.root / DOCUMENTS_DIR
        if documents.is_dir():
            # Linked files are not copied: the stage only has to see them, so a missing file is still an error.
            (stage / DOCUMENTS_DIR).symlink_to(documents, target_is_directory=True)
        for path in self.ledger_files():
            target = stage / path.relative_to(self.root)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(path.read_bytes())

    def _commit_from(self, stage: Path) -> None:
        for path in sorted(stage.rglob("*.beancount")):
            relative = path.relative_to(stage)
            target = self.root / relative
            content = path.read_bytes()
            if target.exists() and target.read_bytes() == content:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            temp = target.with_name(target.name + ".tmp")
            temp.write_bytes(content)
            os.replace(temp, target)


class _ChangedUnderneath(Exception):
    """The ledger files changed between staging a change and committing it."""


def _introduced_errors(baseline: list, current: list) -> list:
    allowed = Counter(error.message for error in baseline)
    introduced = []
    for error in current:
        if allowed[error.message] > 0:
            allowed[error.message] -= 1
        else:
            introduced.append(error)
    return introduced


def _convert_error(error, base: Path) -> LedgerError:
    source = error.source or {}
    filename = source.get("filename")
    if filename and Path(filename).is_absolute() and Path(filename).is_relative_to(base):
        filename = Path(filename).relative_to(base).as_posix()
    return LedgerError(message=error.message, filename=filename, lineno=source.get("lineno"))
