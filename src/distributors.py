# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import json
from functools import cache
from pathlib import Path

_DISTRIBUTOR_DIR = Path(__file__).resolve().parent.parent / "data" / "distributors"


@cache
def _load_maps(name: str) -> tuple[dict[str, int], dict[int, str]]:
    default = json.loads((_DISTRIBUTOR_DIR / "default.json").read_text(encoding="utf-8"))
    entries = dict(default["distributors"])
    tracker_aliases: dict[str, int] = {}
    excluded_aliases: list[str] = []
    tracker_path = _DISTRIBUTOR_DIR / f"{name}.json"
    if name != "default" and tracker_path.is_file():
        overrides = json.loads(tracker_path.read_text(encoding="utf-8"))
        for id_value in overrides.get("excluded_ids", []):
            entries.pop(str(id_value), None)
        entries.update(overrides["distributors"])
        tracker_aliases = overrides.get("aliases", {})
        excluded_aliases = overrides.get("excluded_aliases", [])
    reverse = {int(id_value): label.upper() for id_value, label in entries.items()}
    canonical = {label: id_value for id_value, label in reverse.items()}
    # Follow distributor identity when a tracker assigns different numeric IDs.
    targets = {
        int(id_value): canonical[label.upper()]
        for id_value, label in default["distributors"].items()
        if label.upper() in canonical
    }
    alias_targets: dict[int, set[int]] = {}
    for alias, id_value in default["aliases"].items():
        if id_value not in targets and alias in canonical:
            alias_targets.setdefault(id_value, set()).add(canonical[alias])
    for id_value, candidates in alias_targets.items():
        if len(candidates) == 1:
            targets[id_value] = next(iter(candidates))
    forward = {alias: targets[id_value] for alias, id_value in default["aliases"].items() if id_value in targets}
    forward.update({label.upper(): targets[int(id_value)] for id_value, label in default["distributors"].items() if int(id_value) in targets})
    forward.update({alias.upper(): id_value for alias, id_value in tracker_aliases.items() if id_value in reverse})
    # Some default aliases combine labels a tracker offers separately.
    for alias in excluded_aliases:
        forward.pop(alias.upper(), None)
    # The tracker's canonical names take precedence over all aliases.
    forward.update(canonical)
    return forward, reverse


def distributor_id(distributor: str, tracker: str = "") -> str:
    forward, _ = _load_maps(tracker.strip().lower() or "default")
    value = forward.get(distributor.strip().upper())
    return str(value) if value is not None else ""


def distributor_name(id_value: int | str | None, tracker: str = "") -> str:
    _, reverse = _load_maps(tracker.strip().lower() or "default")
    try:
        value = int(id_value) if id_value is not None else 0
    except (ValueError, TypeError):
        return ""
    return reverse.get(value, "")
