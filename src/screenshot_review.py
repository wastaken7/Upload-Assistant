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
    path: Path | None
    index: int
    source: str = "local"
    remote_image: dict[str, Any] | None = None


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


def list_review_items(temp_dir: Path, meta_data: Mapping[str, object]) -> list[ReviewedScreenshot]:
    """Return local frames plus remotely hosted frames retained for this run."""
    if _string(meta_data.get("is_disc")):
        return []
    remote_images = _remote_images(meta_data)
    review = _load_review(temp_dir)
    replacements = review.get("remote_replacements") if isinstance(review.get("remote_replacements"), dict) else {}
    additions = review.get("remote_additions") if isinstance(review.get("remote_additions"), list) else []
    if not remote_images:
        return list_screenshots(temp_dir, meta_data)

    items: list[ReviewedScreenshot] = []
    for index, image in enumerate(remote_images):
        item_id = f"remote-{index}"
        local_name = replacements.get(item_id)
        local_path = temp_dir / "screenshots" / local_name if isinstance(local_name, str) else None
        if local_path is not None and not local_path.is_file():
            local_path = None
        items.append(ReviewedScreenshot(item_id, local_path, index, "replacement" if local_path else "remote", image))
    for offset, value in enumerate(additions):
        if not isinstance(value, dict):
            continue
        item_id = _string(value.get("id"))
        filename = _string(value.get("file"))
        path = temp_dir / "screenshots" / filename if filename else None
        if item_id and path is not None and path.is_file():
            items.append(ReviewedScreenshot(item_id, path, len(remote_images) + offset, "addition"))
    return items


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
    """Delete a local frame or discard a pending remote addition."""
    with _lock_for(temp_dir):
        if screenshot_id.startswith("remote-add-"):
            review = _load_review(temp_dir)
            additions = review.get("remote_additions")
            if not isinstance(additions, list):
                raise FileNotFoundError("Pending screenshot addition not found")
            addition_index = next((index for index, value in enumerate(additions) if isinstance(value, dict) and _string(value.get("id")) == screenshot_id), None)
            if addition_index is None:
                raise FileNotFoundError("Pending screenshot addition not found")
            addition = additions.pop(addition_index)
            filename = _string(addition.get("file"))
            addition_file = temp_dir / "screenshots" / filename
            if addition_file.is_file():
                addition_file.unlink()
            for key in ("replacement_times", "generations"):
                values = review.get(key)
                if isinstance(values, dict):
                    values.pop(screenshot_id, None)
                    if not values:
                        review.pop(key, None)
            if additions:
                review["remote_additions"] = additions
            else:
                review.pop("remote_additions", None)
            _save_review(temp_dir, review)
            return list_review_items(temp_dir, meta_data)

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
        if _remote_images(meta_data):
            review = _load_review(temp_dir)
            additions = review.get("remote_additions") if isinstance(review.get("remote_additions"), list) else []
            existing_indices = [
                int(match.group(1)) for value in additions if isinstance(value, dict) and (match := re.fullmatch(r"remote-add-(\d+)", _string(value.get("id"))))
            ]
            item_id = f"remote-add-{max(existing_indices, default=-1) + 1}"
            filename = f"review-{item_id}.png"
            target = ReviewedScreenshot(item_id, temp_dir / "screenshots" / filename, len(_remote_images(meta_data)) + len(additions), "addition")
            timestamp = await _capture_fresh_frame(temp_dir, meta_data, target)
            additions.append({"id": item_id, "file": filename})
            review["remote_additions"] = additions
            _record_capture(temp_dir, item_id, len(_remote_images(meta_data)) + len(additions), timestamp, review)
            return target
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
        if screenshot_id.startswith("remote-"):
            remote_images = _remote_images(meta_data)
            match = re.fullmatch(r"remote-(\d+)", screenshot_id)
            if match is None or int(match.group(1)) >= len(remote_images):
                raise FileNotFoundError("Screenshot not found")
            index = int(match.group(1))
            filename = f"review-{screenshot_id}.png"
            target = ReviewedScreenshot(screenshot_id, temp_dir / "screenshots" / filename, index, "replacement", remote_images[index])
            timestamp = await _capture_fresh_frame(temp_dir, meta_data, target)
            review = _load_review(temp_dir)
            replacements = review.get("remote_replacements") if isinstance(review.get("remote_replacements"), dict) else {}
            replacements[screenshot_id] = filename
            review["remote_replacements"] = replacements
            _record_capture(temp_dir, screenshot_id, len(remote_images), timestamp, review)
            return target
        items = list_screenshots(temp_dir, meta_data)
        target = _find_item(items, screenshot_id)
        timestamp = await _capture_fresh_frame(temp_dir, meta_data, target)
        _record_capture(temp_dir, screenshot_id, len(items), timestamp)
        return target


def undo_remote_replacement(temp_dir: Path, screenshot_id: str) -> None:
    """Discard a pending replacement and restore the original remote image."""
    with _lock_for(temp_dir):
        if re.fullmatch(r"remote-\d+", screenshot_id) is None:
            raise ValueError("Only remote replacements can be undone")
        review = _load_review(temp_dir)
        replacements = review.get("remote_replacements")
        if not isinstance(replacements, dict):
            raise FileNotFoundError("No pending replacement found")
        filename = replacements.pop(screenshot_id, None)
        if not isinstance(filename, str):
            raise FileNotFoundError("No pending replacement found")
        replacement_file = temp_dir / "screenshots" / filename
        if replacement_file.is_file():
            replacement_file.unlink()
        if replacements:
            review["remote_replacements"] = replacements
        else:
            review.pop("remote_replacements", None)
        _save_review(temp_dir, review)


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


def _record_capture(temp_dir: Path, screenshot_id: str, count: int, timestamp: float, review: dict[str, Any] | None = None) -> None:
    review = review if review is not None else _load_review(temp_dir)
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


def staged_remote_uploads(temp_dir: Path, image_list: list[dict[str, Any]]) -> list[tuple[int | None, Path]]:
    """Return replacement/addition files that must be hosted with the normal upload."""
    with _lock_for(temp_dir):
        review = _load_review(temp_dir)
        replacements = review.get("remote_replacements") if isinstance(review.get("remote_replacements"), dict) else {}
        additions = review.get("remote_additions") if isinstance(review.get("remote_additions"), list) else []
        pending: list[tuple[int | None, Path]] = []
        for item_id, filename in replacements.items():
            match = re.fullmatch(r"remote-(\d+)", str(item_id))
            path = temp_dir / "screenshots" / str(filename)
            if match and path.is_file() and int(match.group(1)) < len(image_list):
                pending.append((int(match.group(1)), path))
        for value in additions:
            if isinstance(value, dict):
                path = temp_dir / "screenshots" / _string(value.get("file"))
                if path.is_file():
                    pending.append((None, path))
        return pending


def apply_staged_remote_uploads(
    temp_dir: Path, image_list: list[dict[str, Any]], uploaded: list[dict[str, Any]], pending: list[tuple[int | None, Path]]
) -> list[dict[str, Any]]:
    """Replace remote entries and append additions after their local files are hosted."""
    if len(uploaded) != len(pending):
        raise RuntimeError("Not every reviewed screenshot was uploaded")
    result = list(image_list)
    for (index, _path), image in zip(pending, uploaded, strict=True):
        if index is None:
            result.append(image)
        else:
            result[index] = image
    with _lock_for(temp_dir):
        review = _load_review(temp_dir)
        replacements = review.get("remote_replacements") if isinstance(review.get("remote_replacements"), dict) else {}
        additions = review.get("remote_additions") if isinstance(review.get("remote_additions"), list) else []
        replacement_indices = {index for index, _path in pending if index is not None}
        addition_files = {path.name for index, path in pending if index is None}
        for index in replacement_indices:
            item_id = f"remote-{index}"
            expected_file = next(path.name for pending_index, path in pending if pending_index == index)
            if replacements.get(item_id) == expected_file:
                replacements.pop(item_id, None)
        remaining_additions = [value for value in additions if not isinstance(value, dict) or _string(value.get("file")) not in addition_files]
        if replacements:
            review["remote_replacements"] = replacements
        else:
            review.pop("remote_replacements", None)
        if remaining_additions:
            review["remote_additions"] = remaining_additions
        else:
            review.pop("remote_additions", None)
        _save_review(temp_dir, review)
    return result


def _remote_images(meta_data: Mapping[str, object]) -> list[dict[str, Any]]:
    value = meta_data.get("image_list")
    if not isinstance(value, list):
        return []
    return [dict(image) for image in value if isinstance(image, Mapping) and _string(image.get("raw_url") or image.get("img_url"))]


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
