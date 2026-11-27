"""What an OCR backend is. The built-in one and plugins implement the same small interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class OcrBox:
    """One piece of recognised text, where it sits on the page, and how sure the engine is (0 to 1)."""

    text: str
    left: float
    top: float
    right: float
    bottom: float
    confidence: float | None = None


class OcrUnavailable(RuntimeError):
    """The backend cannot run here, for example because its package is not installed. The message says what to do."""


class OcrBackend(ABC):
    """Reads text from an image. It only reads: it never sees the ledger, and nothing it returns is written anywhere.

    `recognise` takes a Pillow image and returns the pieces of text it found, in any order. It raises
    `OcrUnavailable` when it cannot run, with a reason a person can act on.
    """

    id: str
    title: str

    @abstractmethod
    def recognise(self, image) -> list[OcrBox]: ...
