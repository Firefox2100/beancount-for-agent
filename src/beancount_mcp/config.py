import os
from pathlib import Path

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from beancount_mcp.models import Layout

ENV_FILE_VAR = "BEANCOUNT_MCP_ENV_FILE"
SECRETS_DIR_VAR = "BEANCOUNT_MCP_SECRETS_DIR"
DEFAULT_ENV_FILE = ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BEANCOUNT_MCP_", extra="ignore")

    data_dir: Path = Path("data")
    layout: Layout = Layout.YEARLY
    host: str = "127.0.0.1"
    port: int = 8000
    mcp_enabled: bool = False
    mcp_raw_transactions: bool = False
    agent_approval_required: bool = True
    auth_token: SecretStr | None = None

    @field_validator("auth_token", mode="after")
    @classmethod
    def _blank_means_unset(cls, value: SecretStr | None) -> SecretStr | None:
        return value if value is not None and value.get_secret_value().strip() else None


def load_settings() -> Settings:
    """Build settings from the environment, an env file and optional secrets.

    The env file defaults to `.env` in the working directory and can be moved
    with BEANCOUNT_MCP_ENV_FILE. Secrets are read from BEANCOUNT_MCP_SECRETS_DIR
    when set, as Docker mounts them.
    """
    env_file = Path(os.environ.get(ENV_FILE_VAR, DEFAULT_ENV_FILE))
    secrets_dir = os.environ.get(SECRETS_DIR_VAR)
    return Settings(_env_file=env_file, _secrets_dir=secrets_dir)
