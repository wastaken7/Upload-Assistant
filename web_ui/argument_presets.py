"""Shared Web UI argument presets storage."""

import json
import threading

from src.app_paths import DATA_DIR
from web_ui import context as context_mod
from web_ui.flask_compat import _is_obj_list, _is_str_mapping

ARGUMENT_PRESETS_PATH = DATA_DIR / "argument_presets.json"
LEGACY_ARGUMENT_PRESETS_PATH = context_mod.CODE_DIR / "data" / "argument_presets.json"
MAX_ARGUMENT_PRESETS = 50
_argument_presets_lock = threading.Lock()


def _load_argument_presets() -> list[dict[str, str]]:
    """Load the shared Web UI argument presets from the data directory."""
    try:
        read_path = ARGUMENT_PRESETS_PATH
        if not read_path.exists() and LEGACY_ARGUMENT_PRESETS_PATH.exists():
            read_path = LEGACY_ARGUMENT_PRESETS_PATH
        if not read_path.exists():
            return []
        raw: object = json.loads(read_path.read_text(encoding="utf-8"))
        if not _is_obj_list(raw):
            return []
        presets: list[dict[str, str]] = []
        for item in raw:
            if not _is_str_mapping(item):
                continue
            name = item.get("name")
            arguments = item.get("arguments")
            if isinstance(name, str) and isinstance(arguments, str) and name.strip() and arguments.strip():
                presets.append({"name": name.strip(), "arguments": arguments.strip()})
        return presets[-MAX_ARGUMENT_PRESETS:]
    except OSError, TypeError, ValueError:
        return []


def _save_argument_presets(presets: list[dict[str, str]]) -> None:
    """Persist shared Web UI argument presets with an atomic file replacement."""
    ARGUMENT_PRESETS_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = ARGUMENT_PRESETS_PATH.with_suffix(".json.tmp")
    temp_path.write_text(json.dumps(presets, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp_path.replace(ARGUMENT_PRESETS_PATH)
