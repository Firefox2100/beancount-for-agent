from beancount_mcp.imports.camt053 import Camt053Importer
from beancount_mcp.imports.mt940 import Mt940Importer
from beancount_mcp.imports.ofx import OfxImporter
from beancount_mcp.imports.registry import ImporterRegistry


def default_importers(load_plugins: bool = True) -> ImporterRegistry:
    registry = ImporterRegistry()
    for importer in (OfxImporter(), Camt053Importer(), Mt940Importer()):
        registry.register(importer)
    if load_plugins:
        registry.load_plugins()
    return registry
