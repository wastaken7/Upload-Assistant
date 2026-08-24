# Upload Assistant © 2026 Audionut & wastaken7 — Licensed under UAPL v1.0
import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any, BinaryIO

try:
    import fcntl
except ImportError:
    fcntl = None

try:
    import msvcrt
except ImportError:
    msvcrt = None

from defusedxml import ElementTree

from src.meta import Meta

API_HIT_WINDOW_SECONDS = 24 * 60 * 60
API_HIT_COUNTER_DIRNAME = "usenet_api_hit_counters"
API_HIT_COUNTER_LOCK_TIMEOUT_SECONDS = 10.0
API_HIT_COUNTER_LOCK_POLL_SECONDS = 0.05


def get_newznab_search_category_id(meta: Meta) -> str:
    category = meta.category.upper()
    resolution = meta.resolution.lower()
    uhd_resolutions = {"2160p", "4320p", "8640p"}
    hd_resolutions = {"1080p", "1080i", "720p", "1440p"}

    if category == "MOVIE":
        if resolution in uhd_resolutions:
            return "2045"
        if resolution in hd_resolutions:
            return "2040"
        return "2030"
    if category == "TV":
        if resolution in uhd_resolutions:
            return "5045"
        if resolution in hd_resolutions:
            return "5040"
        return "5030"
    if category == "BOOK":
        if meta.audiobook:
            return "3030"
        return "7020"
    if category == "GAME":
        return "4050"
    if category == "MUSIC":
        return "3000"
    return "2000"


def build_newznab_search_query(meta: Meta) -> str:
    title = str(meta.title or meta.original_title or "").strip()
    raw_year = meta.year or meta.search_year or 0
    try:
        year = int(raw_year)
    except TypeError, ValueError:
        year = 0

    if meta.category.upper() == "TV":
        if title and meta.season_int > 0 and meta.episode_int > 0:
            return f"{title} S{meta.season_int:02d}E{meta.episode_int:02d}"
        if title and meta.season_int > 0:
            return f"{title} S{meta.season_int:02d}"
        if title:
            return title
    elif meta.category.upper() == "MOVIE":
        if title and year > 0:
            return f"{title} {year}"
        if title:
            return title

    return str(meta.basename_no_ext or title).strip()


def parse_newznab_dupes(
    response_text: str,
    torrent_url: str | None = None,
    *,
    use_guid_attr_as_id: bool = False,
) -> list[dict[str, Any]]:
    dupes: list[dict[str, Any]] = []
    response_xml = ElementTree.fromstring(response_text)
    channel = response_xml.find("channel")
    if channel is None:
        return dupes

    for item in channel.findall("item"):
        title = str(item.findtext("title") or "")
        guid = str(item.findtext("guid") or "")
        item_link = guid
        size_text = "0"

        enclosure = item.find("enclosure")
        if enclosure is not None:
            size_text = str(enclosure.attrib.get("length") or "0")

        for attr in item.findall("{http://www.newznab.com/DTD/2010/feeds/attributes/}attr"):
            attr_name = str(attr.attrib.get("name") or "").lower()
            attr_value = str(attr.attrib.get("value") or "")
            if attr_name == "size" and attr_value:
                size_text = attr_value
            elif use_guid_attr_as_id and attr_name == "guid" and attr_value and not guid:
                guid = attr_value

        item_link = str(item.findtext("link") or item_link)
        if item_link and not item_link.startswith(("http://", "https://")) and guid and torrent_url:
            item_link = f"{torrent_url}{guid}"

        dupes.append(
            {
                "name": title,
                "files": title,
                "size": int(size_text) if size_text.isdigit() else 0,
                "link": item_link,
            }
        )

    return dupes


def get_daily_api_hit_limit(tracker_cfg: dict[str, Any]) -> int:
    try:
        limit = int(tracker_cfg.get("daily_api_hit_limit", 0))
    except TypeError, ValueError:
        return 0
    return max(limit, 0)


def _get_api_hit_counter_filename(tracker: str) -> str:
    safe_tracker = "".join(char if char.isalnum() else "_" for char in tracker.strip().lower())
    safe_tracker = safe_tracker.strip("_") or "default"
    return f"{safe_tracker}.json"


def _get_api_hit_counter_path(base_dir: str, tracker: str) -> Path:
    return Path(base_dir) / "tmp" / API_HIT_COUNTER_DIRNAME / _get_api_hit_counter_filename(tracker)


def _get_api_hit_counter_lock_path(base_dir: str, tracker: str) -> Path:
    return _get_api_hit_counter_path(base_dir, tracker).with_suffix(".lock")


def _lock_api_hit_counter_file(lock_file: BinaryIO) -> None:
    if msvcrt is not None:
        lock_file.seek(0)
        msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
        return
    if fcntl is not None:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)  # type: ignore
        return
    raise RuntimeError("No supported file locking mechanism is available")


def _unlock_api_hit_counter_file(lock_file: BinaryIO) -> None:
    if msvcrt is not None:
        lock_file.seek(0)
        msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
        return
    if fcntl is not None:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)  # type: ignore
        return


def _acquire_api_hit_counter_lock(lock_path: Path) -> BinaryIO:
    deadline = time.monotonic() + API_HIT_COUNTER_LOCK_TIMEOUT_SECONDS
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_file = lock_path.open("a+b")
    lock_file.seek(0, os.SEEK_END)
    if lock_file.tell() == 0:
        lock_file.write(b"\0")
        lock_file.flush()
    while True:
        try:
            _lock_api_hit_counter_file(lock_file)
            return lock_file
        except BlockingIOError, OSError:
            if time.monotonic() >= deadline:
                lock_file.close()
                raise TimeoutError(f"Timed out waiting for API hit counter lock: {lock_path}") from None
            time.sleep(API_HIT_COUNTER_LOCK_POLL_SECONDS)


def _release_api_hit_counter_lock(lock_file: BinaryIO) -> None:
    try:
        _unlock_api_hit_counter_file(lock_file)
    finally:
        lock_file.close()


def _write_api_hit_cache(cache_path: Path, tracker_hits: list[float]) -> None:
    temp_path = cache_path.with_suffix(f"{cache_path.suffix}.tmp.{os.getpid()}")
    temp_path.write_text(json.dumps(tracker_hits, indent=2), encoding="utf-8")
    temp_path.replace(cache_path)


def _reserve_daily_api_hit_sync(base_dir: str, tracker: str, limit: int) -> tuple[bool, int]:
    cache_path = _get_api_hit_counter_path(base_dir, tracker)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = _get_api_hit_counter_lock_path(base_dir, tracker)
    lock_file = _acquire_api_hit_counter_lock(lock_path)
    try:
        tracker_hits: list[Any] = []
        if cache_path.exists():
            try:
                loaded_cache = json.loads(cache_path.read_text(encoding="utf-8"))
                if isinstance(loaded_cache, list):
                    tracker_hits = loaded_cache  # type: ignore
            except OSError, json.JSONDecodeError:
                tracker_hits = []

        now = time.time()
        cutoff = now - API_HIT_WINDOW_SECONDS
        recent_hits: list[float] = []
        for hit in tracker_hits:
            if isinstance(hit, (int, float)):
                hit_value = float(hit)
                if hit_value >= cutoff:
                    recent_hits.append(hit_value)
        if len(recent_hits) >= limit:
            _write_api_hit_cache(cache_path, recent_hits)
            return False, len(recent_hits)

        recent_hits.append(now)
        _write_api_hit_cache(cache_path, recent_hits)
        return True, len(recent_hits)
    finally:
        _release_api_hit_counter_lock(lock_file)


async def reserve_daily_api_hit(base_dir: str, tracker: str, limit: int) -> tuple[bool, int]:
    return await asyncio.to_thread(_reserve_daily_api_hit_sync, base_dir, tracker, limit)
