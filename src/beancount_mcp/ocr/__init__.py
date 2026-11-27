from collections.abc import Callable, Iterable
from importlib.metadata import entry_points

from beancount_mcp.ocr.base import OcrBackend, OcrUnavailable
from beancount_mcp.ocr.rapid import RapidOcr

ENTRY_POINT_GROUP = "beancount_mcp.ocr"


class OcrRegistry:
    def __init__(self) -> None:
        self._backends: dict[str, OcrBackend] = {}

    def register(self, backend: OcrBackend) -> None:
        if backend.id in self._backends:
            raise ValueError(f"OCR backend {backend.id} is already registered")
        self._backends[backend.id] = backend

    def get(self, backend_id: str) -> OcrBackend:
        try:
            return self._backends[backend_id]
        except KeyError:
            raise OcrUnavailable(f"no OCR backend called {backend_id!r} (available: {', '.join(sorted(self._backends))})") from None

    def load_plugins(self, points: Iterable | None = None) -> None:
        """Let each installed plugin register its backends. An entry point resolves to a callable that receives this registry."""
        for point in entry_points(group=ENTRY_POINT_GROUP) if points is None else points:
            register: Callable[[OcrRegistry], None] = point.load()
            register(self)


def default_ocr(load_plugins: bool = True) -> OcrRegistry:
    registry = OcrRegistry()
    registry.register(RapidOcr())
    if load_plugins:
        registry.load_plugins()
    return registry
