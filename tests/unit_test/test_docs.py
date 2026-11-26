import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "generate_docs.py"


def test_generated_reference_pages_are_current():
    spec = importlib.util.spec_from_file_location("generate_docs", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.main(["--check"]) == 0, "run `uv run python scripts/generate_docs.py` and commit the result"
