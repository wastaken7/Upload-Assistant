"""Derive one canonical media-content duration without rescanning prepared media."""

from __future__ import annotations

import asyncio
import contextlib
import json
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from src.binaries import configured_binary
from src.console import logger
from src.media_extensions import VIDEO_EXTENSIONS

_MAX_VIDEO_PROBES = 8


def content_duration_category(meta: Any) -> str:
    """Return the stable Stats category for content that has a meaningful runtime."""
    category = str(getattr(meta, "category", "") or "").upper()
    if bool(getattr(meta, "is_sports", False)):
        return "Sports"
    if category == "XXX":
        return "XXX"
    if category == "BOOK":
        return "Audiobook" if bool(getattr(meta, "audiobook", False)) else ""
    if category == "MUSIC":
        return "Music"
    if category == "TV":
        return "TV"
    if category in {"MOVIE", "FANRES"}:
        return "Movie"
    return ""


def _positive_number(value: object) -> float:
    if not isinstance(value, int | float | str):
        return 0.0
    with contextlib.suppress(TypeError, ValueError):
        number = float(value)
        return number if number > 0 else 0.0
    return 0.0


def _mapping(value: object) -> Mapping[str, object]:
    return cast(Mapping[str, object], value) if isinstance(value, Mapping) else {}


def _list(value: object) -> list[object]:
    return cast(list[object], value) if isinstance(value, list) else []


def _clock_seconds(value: object) -> float:
    parts = str(value or "").strip().split(":")
    if len(parts) != 3:
        return 0.0
    with contextlib.suppress(TypeError, ValueError):
        hours, minutes, seconds = (float(part) for part in parts)
        total = hours * 3600 + minutes * 60 + seconds
        return total if total > 0 else 0.0
    return 0.0


def _mediainfo_seconds(meta: Any) -> float:
    mediainfo = _mapping(cast(object, getattr(meta, "mediainfo", {})))
    media = _mapping(mediainfo.get("media", {}))
    tracks = (_mapping(track) for track in _list(media.get("track", [])))
    general = next((track for track in tracks if track.get("@type") == "General"), None)
    return _positive_number(general.get("Duration")) if general else 0.0


def _disc_seconds(meta: Any) -> float:
    discs = _list(cast(object, getattr(meta, "discs", [])))
    if discs:
        durations: list[float] = []
        for disc in discs:
            bdinfo = _mapping(_mapping(disc).get("bdinfo", {}))
            durations.append(_clock_seconds(bdinfo.get("length")))
        return sum(durations) if durations and all(duration > 0 for duration in durations) else 0.0
    bdinfo = _mapping(cast(object, getattr(meta, "bdinfo", {})))
    return _clock_seconds(bdinfo.get("length"))


def _music_seconds(meta: Any) -> float:
    release = _mapping(cast(object, getattr(meta, "music_release", {})))
    tracks = (_mapping(track) for track in _list(release.get("tracks", [])))
    return sum(_positive_number(track.get("duration")) for track in tracks)


def existing_content_duration(meta: Any) -> float:
    """Read duration already produced by the category-specific preparation path."""
    existing = _positive_number(getattr(meta, "content_duration_seconds", None))
    if existing:
        return existing
    category = content_duration_category(meta)
    if category == "Audiobook":
        return _positive_number(getattr(meta, "audiobook_duration", None))
    if category == "Music":
        return _music_seconds(meta)
    if getattr(meta, "is_disc", ""):
        return _disc_seconds(meta)
    return _mediainfo_seconds(meta)


def prepared_content_duration(meta: Any) -> float:
    """Return only the canonical value set by ``populate_content_duration``."""
    return _positive_number(getattr(meta, "content_duration_seconds", None))


def _probe_video_duration(path: str, executable: str) -> float:
    try:
        result = subprocess.run(  # noqa: S603
            [executable, "-v", "error", "-show_entries", "format=duration", "-of", "json", path],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=120,
        )
        if result.returncode != 0:
            return 0.0
        payload = _mapping(cast(object, json.loads(result.stdout)))
        format_data = _mapping(payload.get("format", {}))
        return _positive_number(format_data.get("duration"))
    except OSError, subprocess.SubprocessError, json.JSONDecodeError, TypeError, ValueError:
        return 0.0


async def _probe_video_pack(paths: list[str], executable: str) -> float:
    semaphore = asyncio.Semaphore(_MAX_VIDEO_PROBES)

    async def probe(path: str) -> float:
        async with semaphore:
            return await asyncio.to_thread(_probe_video_duration, path, executable)

    durations = await asyncio.gather(*(probe(path) for path in paths))
    return sum(durations) if durations and all(duration > 0 for duration in durations) else 0.0


async def populate_content_duration(meta: Any, config: Mapping[str, Any] | None = None) -> float:
    """Populate one duration during prep, probing only multi-file video releases."""
    category = content_duration_category(meta)
    meta.content_duration_category = category
    if not category:
        meta.content_duration_seconds = None
        return 0.0
    existing = _positive_number(getattr(meta, "content_duration_seconds", None))
    if existing:
        return existing

    filelist = _list(cast(object, getattr(meta, "filelist", [])))
    files = [str(path) for path in filelist if Path(str(path)).suffix.lower() in VIDEO_EXTENSIONS and Path(str(path)).is_file()]
    if not getattr(meta, "is_disc", "") and category in {"Movie", "TV", "XXX", "Sports"} and len(files) > 1:
        try:
            executable = configured_binary("ffprobe_path", config) or "ffprobe"
        except FileNotFoundError as exc:
            logger.debug(f"[yellow]Unable to resolve ffprobe for content duration: {exc}[/yellow]")
            executable = ""
        duration = await _probe_video_pack(files, executable) if executable else 0.0
    else:
        duration = existing_content_duration(meta)

    meta.content_duration_seconds = duration or None
    if not duration:
        logger.debug(f"[yellow]No local content duration available for Stats category {category}[/yellow]")
    return duration
