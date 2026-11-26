import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "export_contract.py"


def test_committed_contract_is_current():
    spec = importlib.util.spec_from_file_location("export_contract", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.main(["--check"]) == 0, "run `uv run python scripts/export_contract.py` and commit the result"
