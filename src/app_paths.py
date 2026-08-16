"""Locations for files created by Upload Assistant at runtime.

The source checkout is intentionally treated as read-only. ``UA_DATA_DIR`` is
the supported override for containers, portable installs, and test runs.
"""

import os
from pathlib import Path

CODE_DIR = Path(__file__).resolve().parent.parent


def _default_data_dir() -> Path:
    override = os.environ.get("UA_DATA_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "Upload-Assistant"
    xdg_data_home = os.environ.get("XDG_DATA_HOME", "").strip()
    base = Path(xdg_data_home).expanduser() if xdg_data_home else Path.home() / ".local" / "share"
    primary = base / "Upload-Assistant"
    legacy = base / "upload-assistant"
    if not primary.exists() and legacy.exists():
        return legacy
    return primary


STATE_DIR = _default_data_dir()
# Keep the historic data/ and tmp/ layout, but place the whole tree below a
# user-owned state root. This avoids a broad, fragile rewrite of path consumers.
DATA_DIR = STATE_DIR / "data"
TMP_DIR = STATE_DIR / "tmp"
CONFIG_PATH = DATA_DIR / "config.py"
LEGACY_CONFIG_PATH = CODE_DIR / "data" / "config.py"


def ensure_data_dir() -> Path:
    """Create and return the user-owned runtime directory."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return STATE_DIR
