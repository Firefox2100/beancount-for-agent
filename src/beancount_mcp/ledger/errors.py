from beancount_mcp.models import LedgerError


class LedgerStoreError(Exception):
    """Base class for ledger store failures."""


class InvalidLedgerId(LedgerStoreError):
    pass


class LedgerNotFound(LedgerStoreError):
    pass


class LedgerExists(LedgerStoreError):
    pass


class UnsupportedStructure(LedgerStoreError):
    pass


class StaleVersion(LedgerStoreError):
    pass


class TransactionNotFound(LedgerStoreError):
    pass


class NotEditable(LedgerStoreError):
    pass


class ChangeRejected(LedgerStoreError):
    """The change would introduce ledger errors, so nothing was written."""

    def __init__(self, errors: list[LedgerError]):
        super().__init__("; ".join(error.message for error in errors))
        self.errors = errors


class ChangeNotFound(LedgerStoreError):
    pass


class ChangeNotPending(LedgerStoreError):
    pass


class ChangeConflict(LedgerStoreError):
    """The target of a pending change was modified after it was proposed."""


class ApprovalRequired(LedgerStoreError):
    pass


class VersionRequired(LedgerStoreError):
    pass


class RecipeNotFound(LedgerStoreError):
    pass


class RecipeError(LedgerStoreError):
    """The recipe cannot be applied with these parameters to this account."""


class ImportNotFound(LedgerStoreError):
    pass


class ImportRefused(LedgerStoreError):
    """An uploaded statement cannot be read or used, and why."""


class ReceiptRefused(LedgerStoreError):
    """A receipt cannot be stored, found or read, and why."""
