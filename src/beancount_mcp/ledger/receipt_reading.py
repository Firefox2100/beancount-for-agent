"""Reading the text of a receipt: a PDF's own text layer where it has one, OCR of the picture where it does not.

Each page of a PDF is judged on its own, so a scanned page inside an otherwise digital PDF is still read. Results are
cached by the file's content, so a receipt is read once however often it is asked for, and a file put in the documents
folder by hand is read the same way as one that was uploaded.
"""

import hashlib
import io
import json
import os
import re
import statistics
from pathlib import Path

from beancount_mcp.ledger import receipts
from beancount_mcp.ledger.errors import ReceiptRefused
from beancount_mcp.ledger.sidecar import sidecar_dir
from beancount_mcp.models.receipts import ReceiptLine, ReceiptPage, ReceiptReading
from beancount_mcp.ocr import OcrRegistry
from beancount_mcp.ocr.base import OcrBackend, OcrBox, OcrUnavailable

LOW_CONFIDENCE = 0.85
RENDER_DPI = 200
IMAGE_EDGE = 1600
_WORD = re.compile(r"[A-Za-z0-9一-鿿]")
_BROKEN = re.compile(r"�|\(cid:\d+\)")


def usable_text(text: str) -> bool:
    """Is this a PDF page's real text? A scan has none, and some PDFs carry unreadable placeholders instead."""
    stripped = text.strip()
    if len(_WORD.findall(stripped)) < 15:
        return False
    return len(_BROKEN.findall(stripped)) <= len(stripped) * 0.02


def rows(boxes: list[OcrBox]) -> list[ReceiptLine]:
    """Pieces of text grouped into the rows a person reads, left to right, so an item and its price stay together."""
    if not boxes:
        return []
    height = statistics.median(b.bottom - b.top for b in boxes) or 1
    grouped: list[list[OcrBox]] = []
    for box in sorted(boxes, key=lambda b: (b.top + b.bottom) / 2):
        middle = (box.top + box.bottom) / 2
        if grouped and abs(middle - statistics.mean((b.top + b.bottom) / 2 for b in grouped[-1])) <= height * 0.6:
            grouped[-1].append(box)
        else:
            grouped.append([box])
    lines = []
    for row in grouped:
        row.sort(key=lambda b: b.left)
        parts, previous = [], None
        for box in row:
            if previous is not None:
                parts.append("  " if box.left - previous.right > height else " ")
            parts.append(box.text)
            previous = box
        scores = [b.confidence for b in row if b.confidence is not None]
        lines.append(ReceiptLine(text="".join(parts), confidence=round(min(scores), 3) if scores else None))
    return lines


def _page_from_ocr(number: int, backend: OcrBackend, image) -> ReceiptPage:
    lines = rows(backend.recognise(image))
    return ReceiptPage(
        number=number, source="ocr" if lines else "none", text="\n".join(line.text for line in lines), lines=lines,
        uncertain=[line.text for line in lines if line.confidence is not None and line.confidence < LOW_CONFIDENCE],
        note=None if lines else "No text was recognised on this page.",
    )


def _open_image(content: bytes):
    try:
        from PIL import Image, ImageOps
    except ImportError as error:
        raise OcrUnavailable("reading receipts needs the optional packages: install beancount-mcp with the `receipts` extra") from error
    image = Image.open(io.BytesIO(content))
    image.load()
    return ImageOps.exif_transpose(image)


def _open_pdf(content: bytes):
    try:
        import pypdfium2
    except ImportError as error:
        raise OcrUnavailable("reading PDF receipts needs the optional packages: install beancount-mcp with the `receipts` extra") from error
    try:
        return pypdfium2.PdfDocument(content)
    except pypdfium2.PdfiumError as error:
        raise ReceiptRefused("this PDF cannot be opened: it is damaged or protected with a password") from error


def read(content: bytes, path: str, ocr: OcrRegistry, backend_id: str, max_pages: int, ocr_enabled: bool = True) -> ReceiptReading:
    """Read a receipt's text. Raises `ReceiptRefused` or `OcrUnavailable` with what to do about it."""
    kind = receipts.sniff(content)
    if kind is None:
        raise ReceiptRefused(f"{path} is not an image or PDF")
    backend = ocr.get(backend_id) if ocr_enabled else None
    if kind != "pdf":
        if backend is None:
            raise OcrUnavailable("this receipt is a picture and OCR is switched off")
        page = _page_from_ocr(1, backend, _open_image(content))
        return ReceiptReading(path=path, kind="image", engine=backend.id, pages=[page])
    document = _open_pdf(content)
    pages, used_ocr = [], False
    total = len(document)
    for index in range(min(total, max_pages)):
        page = document[index]
        text = page.get_textpage().get_text_range()
        if usable_text(text):
            lines = [ReceiptLine(text=line.strip()) for line in text.splitlines() if line.strip()]
            pages.append(ReceiptPage(number=index + 1, source="text", text="\n".join(line.text for line in lines), lines=lines))
        elif backend is None:
            pages.append(ReceiptPage(number=index + 1, source="none", note="This page is a picture and OCR is switched off."))
        else:
            pages.append(_page_from_ocr(index + 1, backend, page.render(scale=RENDER_DPI / 72).to_pil()))
            used_ocr = True
    if total > max_pages and pages:
        pages[-1].note = (pages[-1].note + " " if pages[-1].note else "") + f"Only the first {max_pages} of {total} pages were read."
    return ReceiptReading(path=path, kind="pdf", engine=backend.id if used_ocr and backend else None, pages=pages)


def pictures(content: bytes, max_pages: int = 3) -> list[tuple[bytes, str]]:
    """The receipt as pictures an agent's model can look at: the image itself, or the first pages of a PDF. Capped in size."""
    kind = receipts.sniff(content)
    if kind is None:
        return []
    media = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}
    try:
        if kind == "pdf":
            document = _open_pdf(content)
            images = [document[i].render(scale=RENDER_DPI / 72).to_pil() for i in range(min(len(document), max_pages))]
        else:
            image = _open_image(content)
            if max(image.size) <= IMAGE_EDGE:
                return [(content, media[kind])]
            images = [image]
    except OcrUnavailable:
        return [] if kind == "pdf" else [(content, media[kind])]
    out = []
    for image in images:
        image.thumbnail((IMAGE_EDGE, IMAGE_EDGE))
        buffer = io.BytesIO()
        image.convert("RGB").save(buffer, "JPEG", quality=85)
        out.append((buffer.getvalue(), "image/jpeg"))
    return out


class ReadingCache:
    """Readings kept beside the ledger by the file's content, so a file is read once however often it is asked for."""

    def __init__(self, ledger_root: Path):
        self._dir = sidecar_dir(ledger_root) / "receipts"

    @staticmethod
    def key(content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    def get(self, key: str, path: str) -> ReceiptReading | None:
        target = self._dir / f"{key}.json"
        if not target.is_file():
            return None
        try:
            return ReceiptReading.model_validate(json.loads(target.read_text())).model_copy(update={"path": path})
        except ValueError:
            return None

    def put(self, key: str, reading: ReceiptReading) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        target = self._dir / f"{key}.json"
        temp = target.with_suffix(".tmp")
        temp.write_text(reading.model_dump_json(indent=2))
        os.replace(temp, target)
