from pathlib import Path

from beancount_mcp.config import ENV_FILE_VAR, SECRETS_DIR_VAR, load_settings
from beancount_mcp.models import Layout


def test_defaults(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    for name in ("BEANCOUNT_MCP_DATA_DIR", "BEANCOUNT_MCP_LAYOUT", ENV_FILE_VAR, SECRETS_DIR_VAR):
        monkeypatch.delenv(name, raising=False)
    settings = load_settings()
    assert settings.data_dir == Path("data") and settings.layout is Layout.YEARLY
    assert settings.agent_approval_required is True


def test_env_file_from_working_directory(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("BEANCOUNT_MCP_LAYOUT", raising=False)
    (tmp_path / ".env").write_text("BEANCOUNT_MCP_LAYOUT=monthly\n")
    assert load_settings().layout is Layout.MONTHLY


def test_env_file_path_override_and_precedence(monkeypatch, tmp_path):
    custom = tmp_path / "custom.env"
    custom.write_text("BEANCOUNT_MCP_LAYOUT=single\nBEANCOUNT_MCP_PORT=9000\n")
    monkeypatch.setenv(ENV_FILE_VAR, str(custom))
    monkeypatch.setenv("BEANCOUNT_MCP_PORT", "9100")
    settings = load_settings()
    assert settings.layout is Layout.SINGLE and settings.port == 9100


def test_secrets_dir(monkeypatch, tmp_path):
    secrets = tmp_path / "secrets"
    secrets.mkdir()
    (secrets / "beancount_mcp_port").write_text("9200")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("BEANCOUNT_MCP_PORT", raising=False)
    monkeypatch.setenv(SECRETS_DIR_VAR, str(secrets))
    assert load_settings().port == 9200
