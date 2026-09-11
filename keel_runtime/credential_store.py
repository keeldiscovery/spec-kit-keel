"""Local storage for the runtime's issued credential (spec FR-025).

Uses the optional `keyring` package when it is importable and the configured backend
is not explicitly "file"; otherwise falls back to a `0600` JSON file under `$KEEL_HOME`.
Never logs a token value.
"""
from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

try:
    import keyring  # type: ignore

    _KEYRING_AVAILABLE = True
except ImportError:  # pragma: no cover -- exercised only where keyring is installed
    keyring = None  # type: ignore
    _KEYRING_AVAILABLE = False

_KEYRING_SERVICE = "keel-runtime"
_KEYRING_USERNAME = "agent-credential"


@dataclass
class Credential:
    access_token: str
    refresh_token: str
    expires_at: float  # epoch seconds
    scope: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at,
            "scope": self.scope,
        }

    @staticmethod
    def from_dict(data: dict) -> "Credential":
        return Credential(
            access_token=data["access_token"],
            refresh_token=data["refresh_token"],
            expires_at=data["expires_at"],
            scope=list(data.get("scope") or []),
        )


class CredentialStore:
    """Chooses keyring (if importable and not overridden) or a 0600 file, per backend."""

    def __init__(self, home: Path, backend: str = "auto"):
        self.home = Path(home)
        self.backend = backend
        self._use_keyring = _KEYRING_AVAILABLE and backend != "file"

    @property
    def _file_path(self) -> Path:
        return self.home / "credentials.json"

    def load(self) -> Optional[Credential]:
        if self._use_keyring:
            raw = keyring.get_password(_KEYRING_SERVICE, _KEYRING_USERNAME)  # type: ignore[union-attr]
            if raw is None:
                return None
            return Credential.from_dict(json.loads(raw))

        path = self._file_path
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as handle:
            return Credential.from_dict(json.load(handle))

    def save(self, credential: Credential) -> None:
        raw = json.dumps(credential.to_dict())
        if self._use_keyring:
            keyring.set_password(_KEYRING_SERVICE, _KEYRING_USERNAME, raw)  # type: ignore[union-attr]
            return

        self.home.mkdir(parents=True, exist_ok=True)
        path = self._file_path
        # Create with 0600 from the start (rather than chmod after the fact) so the
        # token is never briefly world-readable between write and chmod.
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(raw)
        finally:
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass  # best-effort on platforms without POSIX permission bits

    def clear(self) -> None:
        if self._use_keyring:
            try:
                keyring.delete_password(_KEYRING_SERVICE, _KEYRING_USERNAME)  # type: ignore[union-attr]
            except Exception:
                pass  # nothing stored is not an error
            return

        path = self._file_path
        if path.exists():
            path.unlink()

    @staticmethod
    def file_mode_is_owner_only(path: Path) -> bool:
        """Test helper: true when `path` is exactly mode 0600."""
        return stat.S_IMODE(os.stat(path).st_mode) == 0o600
