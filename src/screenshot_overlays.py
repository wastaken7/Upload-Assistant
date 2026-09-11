"""Shared screenshot overlay settings and labels for capture backends."""

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

OVERLAY_KEYS = ("overlay_frame_number", "overlay_frame_type", "overlay_timestamp", "overlay_tonemapped")


def overlay_fontfile() -> str | None:
    """Find a portable font, including Windows without a fontconfig setup."""
    candidates = (
        Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / "arial.ttf",
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/Library/Fonts/Arial.ttf"),
    )
    return next((str(path) for path in candidates if path.is_file()), None)


def _enabled(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "on"}
    return bool(value)


def overlay_options(defaults: Mapping[str, Any]) -> dict[str, bool]:
    """Let explicit switches override the legacy setting independently."""
    legacy = _enabled(defaults.get("frame_overlay", False))
    return {key: _enabled(defaults.get(key, legacy if key != "overlay_timestamp" else False)) for key in OVERLAY_KEYS}


def overlay_enabled(defaults: Mapping[str, Any]) -> bool:
    """Honor the master switch, including configurations from the individual-only UI."""
    if "frame_overlay" in defaults:
        return _enabled(defaults["frame_overlay"])
    return any(overlay_options(defaults).values())


def overlays_active(defaults: Mapping[str, Any]) -> bool:
    """Skip overlay capture processing when the master or every label is off."""
    return overlay_enabled(defaults) and any(overlay_options(defaults).values())


def overlay_text_size(defaults: Mapping[str, Any]) -> int:
    """Return the bounded text size shared by FFmpeg and VapourSynth."""
    try:
        text_size = int(defaults.get("overlay_text_size", 18))
    except (OverflowError, TypeError, ValueError):
        text_size = 18
    return max(1, min(text_size, 100))


def format_timestamp(seconds: float) -> str:
    """Format an elapsed video time with millisecond precision."""
    milliseconds = max(0, round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"


def overlay_lines(
    options: Mapping[str, bool], frame_number: int, frame_type: str, timestamp: str, tonemapped: bool, *, layout: str = "stacked"
) -> list[str]:
    """Build only enabled labels, with the conditional tone-mapping label last."""
    if layout == "single_line":
        candidates = (
            ("overlay_frame_number", f"Frame {frame_number}"),
            ("overlay_timestamp", timestamp),
            ("overlay_frame_type", f"{frame_type}-Frame" if frame_type in {"I", "P", "B"} else "Unknown frame"),
            ("overlay_tonemapped", "Tonemapped" if tonemapped else ""),
        )
        text = " • ".join(text for key, text in candidates if options.get(key, False) and text)
        return [text] if text else []
    candidates = (
        ("overlay_frame_number", f"Frame Number: {frame_number}"),
        ("overlay_frame_type", f"Frame Type: {frame_type}"),
        ("overlay_timestamp", f"Timestamp: {timestamp}"),
        ("overlay_tonemapped", "Tonemapped" if tonemapped else ""),
    )
    return [text for key, text in candidates if options.get(key, False) and text]


def overlay_filters(defaults: Mapping[str, Any], meta: Any, seek_time: str | float, tonemapped: bool, *, dvd: bool = False) -> list[str]:
    """Render compact FFmpeg labels after processing, respecting upload suppression."""
    if not meta.frame_overlay or not overlays_active(defaults):
        return []
    options = overlay_options(defaults)
    frame_info = meta.frame_info_map.get(str(seek_time), {})
    seek_time = float(seek_time)
    frame_rate = meta.frame_rate or 24.0
    frame_time = float(frame_info.get("pts_time", seek_time))
    if frame_time <= 1 or abs(frame_time - seek_time) >= 10:
        frame_time = seek_time
    frame_type = frame_info.get("frame_type", "Unknown")
    if frame_type not in {"I", "P", "B", "?"}:
        frame_type = "Unknown"
    baseline = 576 if dvd else 1080
    resolution = "".join(char for char in (meta.resolution or str(baseline)) if char.isdigit())
    scale = int(resolution or baseline) / baseline
    font_size = max(1, round(overlay_text_size(defaults) * scale))
    border_width = max(1, round(2 * scale))
    padding = max(1, round(10 * scale))
    spacing = max(1, round(font_size * 1.1))
    # Input seeking rebases frame PTS. Add the seek offset to the captured
    # frame's timestamp, rather than deriving time from a nominal frame rate.
    timestamp = f"%{{pts:hms:{seek_time:.6f}}}"
    lines = overlay_lines(options, int(frame_time * frame_rate), frame_type, timestamp, tonemapped, layout=str(defaults.get("overlay_layout", "stacked")))
    x_position = f"w-tw-{padding}" if defaults.get("overlay_position") == "right" else str(padding)
    fontfile = overlay_fontfile()
    font_setting = ""
    if fontfile:
        escaped_font = fontfile.replace("\\", "/").replace(":", "\\:").replace("'", "'\\\\\\''")
        font_setting = f":fontfile='{escaped_font}'"
    filters = []
    for index, line in enumerate(lines):
        escaped = line.replace(":", "\\:")
        filters.append(
            f"drawtext=text='{escaped}'{font_setting}:fontcolor=white:fontsize={font_size}:x={x_position}:y={padding + index * spacing}:borderw={border_width}:bordercolor=black"
        )
    return filters
