import os
from pathlib import Path

from pydantic import BaseModel, ValidationError

from beancount_mcp.ledger.layout import SIDECAR_DIR
from beancount_mcp.models import Layout

LAYOUT_FILE = "layout.json"
SCHEMA_VERSION = 1


class LayoutRecord(BaseModel):
    schema_version: int = SCHEMA_VERSION
    layout: Layout


def sidecar_dir(root: Path) -> Path:
    return root / SIDECAR_DIR


def read_layout(root: Path) -> Layout | None:
    path = sidecar_dir(root) / LAYOUT_FILE
    if not path.is_file():
        return None
    try:
        return LayoutRecord.model_validate_json(path.read_text()).layout
    except ValidationError:
        return None


def write_layout(root: Path, layout: Layout) -> None:
    directory = sidecar_dir(root)
    directory.mkdir(exist_ok=True)
    target = directory / LAYOUT_FILE
    temp = target.with_suffix(".tmp")
    temp.write_text(LayoutRecord(layout=layout).model_dump_json(indent=2))
    os.replace(temp, target)
