"""Local screenshot-review operations used by the Web UI.

The review state is deliberately kept next to the execution metadata.  This
makes changes made while Upload-Assistant is waiting for confirmation survive
the later screenshot/upload stages without exposing arbitrary local files.
"""

import json
import re
import secrets
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.meta import Meta
from src.takescreens import capture_screenshot, get_frame_info, tone_map

_SCREENSHOT_ID = re.compile(r"^generic-(\d+)$")
_SCREENSHOT_FILE = re.compile(r"^(?P<prefix>.+)-(?P<index>\d+)\.png$", re.IGNORECASE)
_EXCLUDED_NAMES = {"poster.png", "cover.png", "music_cover.png"}
_review_locks: dict[str, threading.Lock] = {}
_review_locks_guard = threading.Lock()


@dataclass(frozen=True)
class ReviewedScreenshot:
    id: str
    path: Path
    index: int


def _lock_for(temp_dir: Path) -> threading.Lock:
    key = str(temp_dir.resolve()).casefold()
    with _review_locks_guard:
        return _review_locks.setdefault(key, threading.Lock())


def _review_file(temp_dir: Path) -> Path:
    return temp_dir / "screenshot_review.json"


def _load_review(temp_dir: Path) -> dict[str, Any]:
    try:
        payload = json.loads(_review_file(temp_dir).read_text(encoding="utf-8"))
    except OSError, json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _save_review(temp_dir: Path, review: Mapping[str, Any]) -> None:
    output = _review_file(temp_dir)
    temporary = output.with_suffix(".tmp")
    temporary.write_text(json.dumps(dict(review), indent=2), encoding="utf-8")
    temporary.replace(output)


def _is_reviewable_file(path: Path) -> bool:
    name = path.name.casefold()
    return path.is_file() and path.suffix.casefold() == ".png" and name not in _EXCLUDED_NAMES and "libplacebo-test" not in name


def list_screenshots(temp_dir: Path, meta_data: Mapping[str, object]) -> list[ReviewedScreenshot]:
    """List the ordinary FFmpeg screenshots for this execution only.

    Disc/menu screenshots have their own capture contracts.  They remain out
    of this review surface rather than being treated as generic video frames.
    """
    if _string(meta_data.get("is_disc")):
        return []
    candidates: list[ReviewedScreenshot] = []
    for path in (temp_dir / "screenshots").glob("*.png"):
        if not _is_reviewable_file(path):
            continue
        match = _SCREENSHOT_FILE.match(path.name)
        if not match:
            continue
        index = int(match.group("index"))
        candidates.append(ReviewedScreenshot(id=f"generic-{index}", path=path, index=index))
    return sorted(candidates, key=lambda item: (item.index, item.path.name.casefold()))


def target_count(temp_dir: Path, fallback: int) -> int:
    """Return the user-reviewed screenshot target, if one exists."""
    value = _load_review(temp_dir).get("target_count")
    try:
        return max(0, int(value))
    except TypeError, ValueError:
        return fallback


def image_version(temp_dir: Path, screenshot_id: str, fallback: int) -> int:
    """Return a monotonic cache-busting version for a reviewed image."""
    generations = _load_review(temp_dir).get("generations")
    if isinstance(generations, dict):
        try:
            if screenshot_id in generations:
                return int(generations[screenshot_id])
        except TypeError, ValueError:
            pass
    return fallback


def delete_screenshot(temp_dir: Path, meta_data: Mapping[str, object], screenshot_id: str) -> list[ReviewedScreenshot]:
    """Delete a frame and compact generic numbering for the normal pipeline."""
    with _lock_for(temp_dir):
        items = list_screenshots(temp_dir, meta_data)
        target = _find_item(items, screenshot_id)
        target.path.unlink()

        # The regular capture step expects a contiguous ``-0.png .. -N.png``
        # sequence.  Compacting preserves the user's removal instead of having
        # that later step silently recreate the removed slot.
        for item in items:
            if item.index <= target.index:
                continue
            replacement = item.path.with_name(f"{item.path.stem.rsplit('-', 1)[0]}-{item.index - 1}.png")
            item.path.replace(replacement)

        remaining = list_screenshots(temp_dir, meta_data)
        _save_review(temp_dir, {"target_count": len(remaining)})
        return remaining


async def add_screenshot(temp_dir: Path, meta_data: Mapping[str, object]) -> ReviewedScreenshot:
    """Capture one additional FFmpeg frame without replacing the reviewed set."""
    with _lock_for(temp_dir):
        items = list_screenshots(temp_dir, meta_data)
        if not items:
            raise FileNotFoundError("Capture the initial screenshots before adding another one")
        last = items[-1]
        index = last.index + 1
        prefix = last.path.stem.rsplit("-", 1)[0]
        target = ReviewedScreenshot(id=f"generic-{index}", path=last.path.with_name(f"{prefix}-{index}.png"), index=index)
        timestamp = await _capture_fresh_frame(temp_dir, meta_data, target)
        _record_capture(temp_dir, target.id, len(items) + 1, timestamp)
        return target


async def replace_screenshot(temp_dir: Path, meta_data: Mapping[str, object], screenshot_id: str) -> ReviewedScreenshot:
    """Capture a new frame atomically at a fresh random point in the source."""
    with _lock_for(temp_dir):
        items = list_screenshots(temp_dir, meta_data)
        target = _find_item(items, screenshot_id)
        timestamp = await _capture_fresh_frame(temp_dir, meta_data, target)
        _record_capture(temp_dir, screenshot_id, len(items), timestamp)
        return target


async def _capture_fresh_frame(temp_dir: Path, meta_data: Mapping[str, object], target: ReviewedScreenshot) -> float:
    """Write a random frame through a staged file, then atomically publish it."""
    meta = Meta(dict(meta_data))
    source = _source_video(meta)
    width, height, w_sar, h_sar, duration, frame_rate = _video_properties(temp_dir)
    lower = max(1.0, duration * 0.10)
    upper = max(lower + 1.0, duration * 0.85)
    timestamp = lower + (upper - lower) * (secrets.randbelow(1_000_000) / 1_000_000)
    meta.frame_rate = frame_rate
    if meta.frame_overlay:
        meta.frame_info_map = {str(timestamp): await get_frame_info(source, timestamp, meta)}

    staged = target.path.with_name(f".{target.path.stem}.capture-{secrets.token_hex(4)}.png")
    hdr_tonemap = bool(tone_map and any(marker in str(meta.hdr) for marker in ("HDR", "DV", "HLG")))
    try:
        result = await capture_screenshot(
            (target.index, source, timestamp, str(staged), width, height, w_sar, h_sar, "verbose" if meta.ffdebug else "quiet", hdr_tonemap, meta)
        )
        if not result or result[1] is None or not staged.is_file():
            raise RuntimeError("FFmpeg did not produce a screenshot")
        staged.replace(target.path)
    finally:
        if staged.exists():
            staged.unlink()
    return timestamp


def _record_capture(temp_dir: Path, screenshot_id: str, count: int, timestamp: float) -> None:
    review = _load_review(temp_dir)
    timestamps = review.get("replacement_times")
    if not isinstance(timestamps, dict):
        timestamps = {}
    generations = review.get("generations")
    if not isinstance(generations, dict):
        generations = {}
    timestamps[screenshot_id] = round(timestamp, 3)
    generations[screenshot_id] = int(generations.get(screenshot_id, 0) or 0) + 1
    review.update({"target_count": count, "replacement_times": timestamps, "generations": generations})
    _save_review(temp_dir, review)


def _find_item(items: list[ReviewedScreenshot], screenshot_id: str) -> ReviewedScreenshot:
    if not _SCREENSHOT_ID.fullmatch(screenshot_id):
        raise ValueError("Invalid screenshot id")
    for item in items:
        if item.id == screenshot_id:
            return item
    raise FileNotFoundError("Screenshot not found")


def _source_video(meta: Meta) -> str:
    for candidate in list(meta.filelist or []):
        if Path(candidate).is_file():
            return str(candidate)
    if meta.path and Path(meta.path).is_file():
        return str(meta.path)
    raise FileNotFoundError("The source video is no longer available")


def _video_properties(temp_dir: Path) -> tuple[float, float, float, float, float, float]:
    try:
        media = json.loads((temp_dir / "MediaInfo.json").read_text(encoding="utf-8"))
        tracks = media["media"]["track"]
        video = next(track for track in tracks if track.get("@type") == "Video")
        general = next(track for track in tracks if track.get("@type") == "General")
    except (OSError, KeyError, StopIteration, TypeError, json.JSONDecodeError) as error:
        raise RuntimeError("Could not read video properties for screenshot replacement") from error

    def number(value: object, fallback: float) -> float:
        try:
            return float(value)
        except TypeError, ValueError:
            return fallback

    duration = number(video.get("Duration"), number(general.get("Duration"), 3600.0))
    width = number(video.get("Width"), 1920.0)
    height = number(video.get("Height"), 1080.0)
    par = number(video.get("PixelAspectRatio"), 1.0)
    dar = number(video.get("DisplayAspectRatio"), 16.0 / 9.0)
    frame_rate = number(video.get("FrameRate"), 24.0)
    if par == 1:
        return width, height, 1.0, 1.0, duration, frame_rate
    if par < 1:
        return width, height, 1.0, width / (dar * height), duration, frame_rate
    return width, height, par, 1.0, duration, frame_rate


def _string(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""
