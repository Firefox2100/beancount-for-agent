import hashlib
import os
import tomllib
from pathlib import Path

import tomli_w

from beancount_mcp.ledger.errors import StaleVersion
from beancount_mcp.ledger.sidecar import sidecar_dir
from beancount_mcp.models import Profile

PROFILE_FILE = "profile.toml"


class ProfileStore:
    """The service-side configuration of one ledger, kept in its sidecar."""

    def __init__(self, ledger_root: Path):
        self._path = sidecar_dir(ledger_root) / PROFILE_FILE

    def load(self) -> tuple[Profile, str]:
        data = self._path.read_bytes() if self._path.is_file() else b""
        profile = Profile.model_validate(tomllib.loads(data.decode())) if data else Profile()
        return profile, hashlib.sha256(data).hexdigest()

    def save(self, profile: Profile, expected_version: str | None) -> str:
        _, current = self.load()
        if expected_version is not None and expected_version != current:
            raise StaleVersion(f"profile is at version {current}, not {expected_version}")
        content = tomli_w.dumps(profile.model_dump(mode="json", exclude_none=True)).encode()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temp = self._path.with_suffix(".tmp")
        temp.write_bytes(content)
        os.replace(temp, self._path)
        return hashlib.sha256(content).hexdigest()
