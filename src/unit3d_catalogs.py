# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import json
import re
from functools import cache
from pathlib import Path
from typing import Any

_CATALOG_DIR = Path(__file__).resolve().parent.parent / "data" / "unit3d_catalogs"

COMPACT_SECTIONS = ("regions", "distributors")


def expand_catalog_section(catalog: dict[str, Any], default: dict[str, Any], section: str) -> dict[str, str]:
    """Expand only the explicitly referenced default IDs, then apply differences."""
    entries: dict[str, str] = {}
    baseline = default.get(section, {})
    references = catalog.get("default_ids", {}).get(section, [])
    if not isinstance(references, list):
        raise ValueError(f"default_ids.{section} must be a list")
    for reference in references:
        match = re.fullmatch(r"([1-9]\d*)(?:-([1-9]\d*))?", str(reference))
        if not match:
            raise ValueError(f"Invalid default ID reference: {reference!r}")
        start = int(match[1])
        end = int(match[2] or match[1])
        if end < start or end - start + 1 > len(baseline):
            raise ValueError(f"Invalid default ID range: {reference!r}")
        for id_value in range(start, end + 1):
            key = str(id_value)
            if key not in baseline:
                raise ValueError(f"Default {section} ID {key} does not exist")
            if key in entries:
                raise ValueError(f"Repeated default {section} ID {key}")
            entries[key] = baseline[key]
    entries.update(catalog.get(section, {}))
    return entries


def _id_ranges(ids: list[int]) -> list[int | str]:
    ranges: list[int | str] = []
    if not ids:
        return ranges
    start = end = ids[0]
    for id_value in ids[1:]:
        if id_value == end + 1:
            end = id_value
        else:
            ranges.append(start if start == end else f"{start}-{end}")
            start = end = id_value
    ranges.append(start if start == end else f"{start}-{end}")
    return ranges


def compact_catalog(catalog: dict[str, Any], default: dict[str, Any]) -> dict[str, Any]:
    """Replace identical entries with explicit default references, losslessly."""
    compact = dict(catalog)
    default_ids = dict(catalog.get("default_ids", {}))
    for section in COMPACT_SECTIONS:
        if section not in catalog:
            continue
        # Legacy overrides already inherit defaults implicitly. Keep that format.
        if section in ("regions", "distributors") and not catalog.get(f"{section}_complete", False):
            continue
        original = expand_catalog_section(catalog, default, section)
        baseline = default.get(section, {})
        identical = sorted(int(key) for key, value in original.items() if baseline.get(key) == value)
        compact[section] = {key: value for key, value in original.items() if baseline.get(key) != value}
        if identical:
            default_ids[section] = _id_ranges(identical)
        else:
            default_ids.pop(section, None)
    if default_ids:
        compact["default_ids"] = default_ids
    else:
        compact.pop("default_ids", None)
    for section in COMPACT_SECTIONS:
        if section in catalog and expand_catalog_section(compact, default, section) != expand_catalog_section(catalog, default, section):
            raise ValueError(f"Compaction changed {section}")
    return compact


@cache
def _load_distributor_maps(name: str) -> tuple[dict[str, int], dict[int, str]]:
    default = json.loads((_CATALOG_DIR / "default.json").read_text(encoding="utf-8"))
    entries = dict(default["distributors"])
    tracker_aliases: dict[str, int] = {}
    excluded_aliases: list[str] = []
    tracker_path = _CATALOG_DIR / f"{name}.json"
    if name != "default" and tracker_path.is_file():
        overrides = json.loads(tracker_path.read_text(encoding="utf-8"))
        if overrides.get("distributors_complete", False):
            entries = expand_catalog_section(overrides, default, "distributors")
        else:
            entries.update(overrides.get("distributors", {}))
        for id_value in overrides.get("excluded_ids", []):
            entries.pop(str(id_value), None)
        tracker_aliases = overrides.get("aliases", {})
        excluded_aliases = overrides.get("excluded_aliases", [])
    reverse = {int(id_value): label.upper() for id_value, label in entries.items()}
    canonical = {label: id_value for id_value, label in reverse.items()}
    # Follow distributor identity when a tracker assigns different numeric IDs.
    targets = {int(id_value): canonical[label.upper()] for id_value, label in default["distributors"].items() if label.upper() in canonical}
    alias_targets: dict[int, set[int]] = {}
    for alias, id_value in default["aliases"].items():
        if id_value not in targets and alias.upper() in canonical:
            alias_targets.setdefault(id_value, set()).add(canonical[alias.upper()])
    for id_value, candidates in alias_targets.items():
        if len(candidates) == 1:
            targets[id_value] = next(iter(candidates))
    forward = {alias.upper(): targets[id_value] for alias, id_value in default["aliases"].items() if id_value in targets}
    forward.update({label.upper(): targets[int(id_value)] for id_value, label in default["distributors"].items() if int(id_value) in targets})
    forward.update({alias.upper(): id_value for alias, id_value in tracker_aliases.items() if id_value in reverse})
    # Some default aliases combine labels a tracker offers separately.
    for alias in excluded_aliases:
        forward.pop(alias.upper(), None)
    # The tracker's canonical names take precedence over all aliases.
    forward.update(canonical)
    return forward, reverse


def distributor_id(distributor: str | None, tracker: str = "") -> str:
    if not distributor:
        return ""
    forward, _ = _load_distributor_maps(tracker.strip().lower() or "default")
    value = forward.get(distributor.strip().upper())
    return str(value) if value is not None else ""


def distributor_name(id_value: int | str | None, tracker: str = "") -> str:
    _, reverse = _load_distributor_maps(tracker.strip().lower() or "default")
    try:
        value = int(id_value) if id_value is not None else 0
    except ValueError, TypeError:
        return ""
    return reverse.get(value, "")


@cache
def _load_region_maps(name: str) -> tuple[dict[str, int], dict[int, str]]:
    default = json.loads((_CATALOG_DIR / "default.json").read_text(encoding="utf-8"))
    entries = dict(default["regions"])
    tracker_path = _CATALOG_DIR / f"{name}.json"
    if name != "default" and tracker_path.is_file():
        overrides = json.loads(tracker_path.read_text(encoding="utf-8"))
        if overrides.get("regions_complete", False):
            entries = expand_catalog_section(overrides, default, "regions")
        else:
            entries.update(overrides.get("regions", {}))
    reverse = {int(id_value): code.upper() for id_value, code in entries.items()}
    return {code: id_value for id_value, code in reverse.items()}, reverse


def region_id(region: str | None, tracker: str = "") -> str:
    if not region:
        return ""
    forward, _ = _load_region_maps(tracker.strip().lower() or "default")
    value = forward.get(region.strip().upper())
    return str(value) if value is not None else ""


def region_name(id_value: int | str | None, tracker: str = "") -> str:
    _, reverse = _load_region_maps(tracker.strip().lower() or "default")
    try:
        value = int(id_value) if id_value is not None else 0
    except ValueError, TypeError:
        return ""
    return reverse.get(value, "")
