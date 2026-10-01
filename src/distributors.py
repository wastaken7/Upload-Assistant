# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import json
from functools import cache
from pathlib import Path

_DISTRIBUTOR_DIR = Path(__file__).resolve().parent.parent / "data" / "distributors"
_TRACKER_FILES = {
    "AITHER": "aither",
    "BLUTOPIA": "blutopia",
    "OLDTOONSWORLD": "oldtoonsworld",
    "ULCX": "ulcx",
}


@cache
def _load_maps(name: str) -> tuple[dict[str, int], dict[int, str]]:
    default = json.loads((_DISTRIBUTOR_DIR / "default.json").read_text(encoding="utf-8"))
    entries = dict(default["distributors"])
    if name != "default":
        overrides = json.loads((_DISTRIBUTOR_DIR / f"{name}.json").read_text(encoding="utf-8"))
        for id_value in overrides.get("excluded_ids", []):
            entries.pop(str(id_value), None)
        entries.update(overrides["distributors"])
    reverse = {int(id_value): label.upper() for id_value, label in entries.items()}
    # Preserve established aliases only for IDs actually offered by this tracker.
    forward = {alias: id_value for alias, id_value in default["aliases"].items() if id_value in reverse}
    # Accept upstream spellings for renamed entries that retain their upstream ID.
    forward.update({label.upper(): int(id_value) for id_value, label in default["distributors"].items() if int(id_value) in reverse})
    # The tracker's canonical names take precedence over inherited aliases.
    forward.update({label: id_value for id_value, label in reverse.items()})
    return forward, reverse


def distributor_id(distributor: str, tracker: str = "") -> str:
    forward, _ = _load_maps(_TRACKER_FILES.get(tracker.strip().upper(), "default"))
    value = forward.get(distributor.strip().upper())
    return str(value) if value is not None else ""


def distributor_name(id_value: int | str | None, tracker: str = "") -> str:
    _, reverse = _load_maps(_TRACKER_FILES.get(tracker.strip().upper(), "default"))
    try:
        value = int(id_value) if id_value is not None else 0
    except (ValueError, TypeError):
        return ""
    return reverse.get(value, "")
