from pathlib import Path

ROOT = Path(__file__).parents[2]
BRAND_ASSETS = (
    ROOT / "src/beancount_mcp/ui/static/brand-mark.svg",
    ROOT / "docs/static/img/brand-mark.svg",
    ROOT / "docs/static/img/favicon.svg",
    ROOT / "integrations/dsh/icon.svg",
)


def test_brand_mark_is_identical_on_every_surface() -> None:
    assets = {path.read_bytes() for path in BRAND_ASSETS}

    assert len(assets) == 1
