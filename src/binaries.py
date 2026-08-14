"""Configuration-backed resolution for optional external executables."""

from __future__ import annotations

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
        return None

    path = Path(path_text).expanduser()
    if not path.is_file():
        raise FileNotFoundError(f"Configured {key} does not exist or is not a file: {path}")
    return str(path)
