"""Configuration-backed resolution for optional external executables."""

from __future__ import annotations

import importlib
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, TypeIs


def _is_str_mapping(value: object) -> TypeIs[Mapping[str, Any]]:
    return isinstance(value, Mapping)


def configured_binary(key: str, config: Mapping[str, Any] | None = None) -> str | None:
    """Return an explicitly configured executable, if any.

    A configured path is an override, not a hint: fail clearly when it no
    longer points at a file instead of silently running a different binary.
    """
    if config is None:
        data_config = importlib.import_module("data.config")
        raw_config: object = getattr(data_config, "config", None)
        config = raw_config if _is_str_mapping(raw_config) else {}

    default: Mapping[str, Any] = {}
    if _is_str_mapping(config):
        default_obj = config.get("DEFAULT")
        if _is_str_mapping(default_obj):
            default = default_obj
    value = default.get(key, "")
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
