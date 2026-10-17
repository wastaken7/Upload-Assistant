"""Read-only MediaInfo/BDInfo reports for the WebUI execution panel."""

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

# Reports are display-only; cap each one so a malformed file cannot exhaust memory.
MAX_REPORT_CHARS = 2_000_000

_BD_SUMMARY_RE = re.compile(r"^BD_SUMMARY_(?P<ext>EXT_)?(?P<disc>\d{2})(?:_(?P<playlist>\d+))?\.txt$")
_COMPLETE_NAME_RE = re.compile(r"^(?P<label>Complete name\s*:\s*)(?P<path>.+)$", re.MULTILINE)


def _read_report(path: Path) -> str | None:
    try:
        with path.open(encoding="utf-8", errors="replace") as handle:
            content = handle.read(MAX_REPORT_CHARS + 1)
    except OSError:
        return None
    if len(content) > MAX_REPORT_CHARS:
        content = content[:MAX_REPORT_CHARS] + "\n\n[Report truncated]"
    return content if content.strip() else None


def _strip_complete_name_paths(content: str) -> str:
    """Keep only file names in MediaInfo ``Complete name`` lines."""
    return _COMPLETE_NAME_RE.sub(lambda match: match["label"] + re.split(r"[\\/]", match["path"].strip())[-1], content)


def _bdinfo_reports(temp_dir: Path) -> list[dict[str, str]]:
    entries: list[tuple[tuple[int, int, int], dict[str, str]]] = []
    for path in temp_dir.iterdir():
        match = _BD_SUMMARY_RE.match(path.name)
        if not match or not path.is_file():
            continue
        content = _read_report(path)
        if content is None:
            continue
        disc = int(match["disc"])
        playlist = int(match["playlist"] or 0)
        is_extended = bool(match["ext"])
        label = "Extended summary" if is_extended else "Summary"
        if disc:
            label += f" · Disc {disc + 1}"
        if playlist:
            label += f" · Playlist {playlist + 1}"
        entries.append(((disc, playlist, int(is_extended)), {"key": path.stem, "label": label, "content": content}))
    entries.sort(key=lambda entry: entry[0])
    return [entry[1] for entry in entries]


def _disc_mediainfo_reports(discs: object, fields: tuple[tuple[str, str], ...]) -> list[dict[str, str]]:
    if not isinstance(discs, list):
        return []
    disc_items = [cast(Mapping[str, Any], disc) for disc in cast(list[object], discs) if isinstance(disc, Mapping)]
    reports: list[dict[str, str]] = []
    for index, disc in enumerate(disc_items):
        for field, label in fields:
            content = disc.get(field)
            if not isinstance(content, str) or not content.strip():
                continue
            if len(disc_items) > 1:
                label = f"{label} · {disc.get('name') or f'Disc {index + 1}'}"
            reports.append({"key": f"{field}_{index}", "label": label, "content": _strip_complete_name_paths(content[:MAX_REPORT_CHARS])})
    return reports


def report_items(meta: Mapping[str, Any], temp_dir: Path) -> tuple[str, list[dict[str, str]]]:
    """Return the report kind and the reports available for one release."""
    is_disc = meta.get("is_disc")
    if is_disc == "BDMV":
        return "bdinfo", _bdinfo_reports(temp_dir)
    if is_disc == "DVD":
        return "mediainfo", _disc_mediainfo_reports(meta.get("discs"), (("ifo_mi", "IFO"), ("vob_mi", "VOB")))
    if is_disc == "HDDVD":
        return "mediainfo", _disc_mediainfo_reports(meta.get("discs"), (("evo_mi", "EVO"),))
    # The clean-path export omits the server's directory layout from the report.
    content = _read_report(temp_dir / "MEDIAINFO_CLEANPATH.txt")
    return "mediainfo", [{"key": "mediainfo", "label": "MediaInfo", "content": content}] if content else []
