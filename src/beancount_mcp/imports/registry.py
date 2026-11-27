from collections.abc import Callable, Iterable
from importlib.metadata import entry_points

from beancount_mcp.imports.base import ImportFailed, Importer

ENTRY_POINT_GROUP = "beancount_mcp.importers"


class ImporterRegistry:
    def __init__(self) -> None:
        self._importers: dict[str, Importer] = {}

    def register(self, importer: Importer) -> None:
        if importer.id in self._importers:
            raise ValueError(f"importer {importer.id} is already registered")
        self._importers[importer.id] = importer

    def all(self) -> list[Importer]:
        return sorted(self._importers.values(), key=lambda importer: importer.id)

    def get(self, importer_id: str) -> Importer:
        try:
            return self._importers[importer_id]
        except KeyError:
            known = ", ".join(i.id for i in self.all())
            raise ImportFailed(f"no importer called {importer_id!r} (available: {known})") from None

    def find(self, filename: str, data: bytes) -> Importer:
        """The one importer that recognises the file. Several, or none, is an error that names them."""
        found = []
        for importer in self.all():
            try:
                if importer.identify(filename, data):
                    found.append(importer)
            except Exception:  # a plugin's identify must not take the upload down
                continue
        if len(found) == 1:
            return found[0]
        known = ", ".join(i.id for i in self.all())
        if not found:
            raise ImportFailed(f"no importer recognises this file; name one of: {known}")
        raise ImportFailed(f"several importers recognise this file ({', '.join(i.id for i in found)}); name one")

    def load_plugins(self, points: Iterable | None = None) -> None:
        """Let each installed plugin register its importers. An entry point resolves to a callable that receives this registry."""
        for point in entry_points(group=ENTRY_POINT_GROUP) if points is None else points:
            register: Callable[[ImporterRegistry], None] = point.load()
            register(self)
