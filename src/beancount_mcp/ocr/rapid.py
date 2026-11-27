"""RapidOCR: the PaddleOCR models run through ONNX Runtime. The models ship inside the package, so nothing is downloaded."""

import threading

from beancount_mcp.ocr.base import OcrBackend, OcrBox, OcrUnavailable


class RapidOcr(OcrBackend):
    id = "rapidocr"
    title = "RapidOCR (PaddleOCR models)"

    def __init__(self) -> None:
        self._engine = None
        self._lock = threading.Lock()

    def _load(self):
        with self._lock:
            if self._engine is None:
                try:
                    from rapidocr_onnxruntime import RapidOCR
                except ImportError as error:
                    raise OcrUnavailable("OCR needs the optional packages: install beancount-mcp with the `ocr` and `receipts` extras") from error
                self._engine = RapidOCR()
        return self._engine

    def recognise(self, image) -> list[OcrBox]:
        import numpy

        engine = self._load()
        with self._lock:  # the engine is not safe to call from several threads at once
            result, _ = engine(numpy.array(image.convert("RGB")))
        boxes = []
        for points, text, score in result or []:
            xs, ys = [p[0] for p in points], [p[1] for p in points]
            boxes.append(OcrBox(text=str(text), left=min(xs), top=min(ys), right=max(xs), bottom=max(ys), confidence=float(score)))
        return boxes
