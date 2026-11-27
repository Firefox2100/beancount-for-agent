"""Write the contract that integrations depend on: the REST OpenAPI schema and the MCP tool schemas.

    uv run python scripts/export_contract.py          # rewrite integrations/contract/
    uv run python scripts/export_contract.py --check  # exit 1 when the files are stale
"""

import argparse
import asyncio
import json
import sys
import tempfile
from pathlib import Path

from beancount_mcp.api.app import create_app
from beancount_mcp.config import Settings

CONTRACT_DIR = Path(__file__).resolve().parent.parent / "integrations" / "contract"


def build_contract() -> dict[str, str]:
    """File name to content. Raw transactions stay off: it is an opt-in extra, not the contract."""
    with tempfile.TemporaryDirectory() as data_dir:
        app = create_app(Settings(data_dir=Path(data_dir), mcp_enabled=True, mcp_raw_transactions=False, receipts_ocr_enabled=True))
        tools = asyncio.run(_tools(app))
        openapi = app.openapi()
    openapi["info"].pop("version", None)
    return {
        "openapi.json": _dump(openapi),
        "mcp-tools.json": _dump(tools),
    }


async def _tools(app) -> list[dict]:
    listed = await app.state.mcp.list_tools()
    return sorted(
        (
            {
                "name": tool.name,
                "description": tool.description,
                "tags": sorted(tool.tags or []),
                "readOnly": bool(tool.annotations and tool.annotations.read_only_hint),
                "inputSchema": tool.parameters,
            }
            for tool in listed
        ),
        key=lambda tool: tool["name"],
    )


def _dump(value) -> str:
    return json.dumps(value, indent=2, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="fail instead of writing when the files are stale")
    args = parser.parse_args(argv)
    contract = build_contract()
    stale = [
        name for name, content in contract.items()
        if not (CONTRACT_DIR / name).exists() or (CONTRACT_DIR / name).read_text() != content
    ]
    if args.check:
        if stale:
            print(f"stale contract files: {', '.join(stale)}. Run scripts/export_contract.py", file=sys.stderr)
            return 1
        return 0
    CONTRACT_DIR.mkdir(parents=True, exist_ok=True)
    for name in stale:
        (CONTRACT_DIR / name).write_text(contract[name])
        print(f"wrote {CONTRACT_DIR / name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
