"""
gemma/config.py
===============
Configuration and persistence for Gemma LLM settings.
Saves settings to %LOCALAPPDATA%\\OmniStore\\settings.json.

SECURITY CONSTRAINT:
Only local providers are permitted in this version. Any host that is not
localhost or 127.0.0.1 is rejected.
No PySide6 or Qt imports allowed.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlparse

log = logging.getLogger(__name__)

_ALLOWED_LOCAL_HOSTNAMES = {"localhost", "127.0.0.1", "::1"}


@dataclass
class GemmaSettings:
    """Settings for the local Gemma model provider."""
    provider: str = "ollama"
    host: str = "http://localhost:11434"
    model: str = "gemma4:e2b"
    num_ctx: int = 8192
    temperature: float = 0.2
    timeout_s: int = 60
    enabled: bool = True
    fast_mode: bool = False


def validate_local_host(host: str) -> None:
    """Ensure host resolves strictly to localhost/127.0.0.1."""
    if not host or not isinstance(host, str):
        raise ValueError("Host URL must be a non-empty string.")

    cleaned = host.strip()
    if not cleaned.startswith(("http://", "https://")):
        cleaned = "http://" + cleaned

    parsed = urlparse(cleaned)
    hostname = (parsed.hostname or "").lower().strip()

    if hostname not in _ALLOWED_LOCAL_HOSTNAMES:
        raise ValueError(
            f"Security restriction: Only local providers (localhost/127.0.0.1) are permitted in OmniStore. "
            f"Remote host '{hostname}' was rejected."
        )


def _settings_path() -> Path:
    local_app = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
    d = Path(local_app) / "OmniStore"
    d.mkdir(parents=True, exist_ok=True)
    return d / "settings.json"


def load_settings() -> GemmaSettings:
    """Load settings from JSON file or return defaults if absent/corrupted."""
    path = _settings_path()
    if not path.is_file():
        return GemmaSettings()

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        gemma_data = data.get("gemma", data)

        settings = GemmaSettings(
            provider=str(gemma_data.get("provider", "ollama")),
            host=str(gemma_data.get("host", "http://localhost:11434")),
            model=str(gemma_data.get("model", "gemma4:e2b")),
            num_ctx=int(gemma_data.get("num_ctx", 8192)),
            temperature=float(gemma_data.get("temperature", 0.2)),
            timeout_s=int(gemma_data.get("timeout_s", 60)),
            enabled=bool(gemma_data.get("enabled", True)),
            fast_mode=bool(gemma_data.get("fast_mode", False)),
        )
        validate_local_host(settings.host)
        return settings
    except Exception as exc:
        log.warning("Could not read settings from %s (%s). Using defaults.", path, exc)
        return GemmaSettings()


def save_settings(settings: GemmaSettings) -> None:
    """Validate and write settings to settings.json."""
    validate_local_host(settings.host)

    path = _settings_path()
    try:
        existing: dict = {}
        if path.is_file():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                existing = {}

        existing["gemma"] = asdict(settings)
        path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    except Exception as exc:
        log.error("Failed to save settings to %s: %s", path, exc)
        raise
