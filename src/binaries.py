"""Configuration-backed resolution for optional external executables."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any


def configured_binary(key: str, config: Mapping[str, Any] | None = None) -> str | None:
    """Return an explicitly configured executable, if any.

    A configured path is an override, not a hint: fail clearly when it no
    longer points at a file instead of silently running a different binary.
    """
    if config is None:
        from data import config as data_config

        config = data_config.config

    default = config.get("DEFAULT", {}) if isinstance(config, Mapping) else {}
    value = default.get(key, "") if isinstance(default, Mapping) else ""
    path_text = str(value or "").strip()
    if not path_text:
        if key == "ffmpeg_path":
            managed_path = os.environ.get("UA_FFMPEG_PATH", "").strip()
            if managed_path:
                path_text = managed_path
            else:
                return None
        else:
            return None

    path = Path(path_text).expanduser()
    if not path.is_file():
        raise FileNotFoundError(f"Configured {key} does not exist or is not a file: {path}")
    if os.name != "nt" and not os.access(path, os.X_OK):
        raise FileNotFoundError(f"Configured {key} is not executable: {path}")
    return str(path) if path_text.startswith("~") else path_text
