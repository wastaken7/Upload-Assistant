# Upload Assistant © 2026 Audionut & wastaken7 — Licensed under UAPL v1.0
import asyncio
import json
import time
from pathlib import Path
from typing import Any

from defusedxml import ElementTree

from src.meta import Meta

API_HIT_WINDOW_SECONDS = 24 * 60 * 60
API_HIT_COUNTER_FILENAME = "usenet_api_hit_counters.json"


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
    except (TypeError, ValueError):
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

        dupes.append({
            "name": title,
            "files": title,
            "size": int(size_text) if size_text.isdigit() else 0,
            "link": item_link,
        })

    return dupes


def get_daily_api_hit_limit(tracker_cfg: dict[str, Any]) -> int:
    try:
        limit = int(tracker_cfg.get("daily_api_hit_limit", 0))
    except (TypeError, ValueError):
        return 0
    return max(limit, 0)


def _get_api_hit_counter_path(base_dir: str) -> Path:
    return Path(base_dir) / "tmp" / API_HIT_COUNTER_FILENAME


def _reserve_daily_api_hit_sync(base_dir: str, tracker: str, limit: int) -> tuple[bool, int]:
    cache_path = _get_api_hit_counter_path(base_dir)
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    raw_cache: dict[str, Any] = {}
    if cache_path.exists():
        try:
            raw_cache = json.loads(cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raw_cache = {}

    now = time.time()
    cutoff = now - API_HIT_WINDOW_SECONDS
    tracker_hits = raw_cache.get(tracker, [])
    if not isinstance(tracker_hits, list):
        tracker_hits = []

    recent_hits: list[float] = []
    for hit in tracker_hits:
        if isinstance(hit, (int, float)):
            hit_value = float(hit)
            if hit_value >= cutoff:
                recent_hits.append(hit_value)
    if len(recent_hits) >= limit:
        raw_cache[tracker] = recent_hits
        cache_path.write_text(json.dumps(raw_cache, indent=2, sort_keys=True), encoding="utf-8")
        return False, len(recent_hits)

    recent_hits.append(now)
    raw_cache[tracker] = recent_hits
    cache_path.write_text(json.dumps(raw_cache, indent=2, sort_keys=True), encoding="utf-8")
    return True, len(recent_hits)


async def reserve_daily_api_hit(base_dir: str, tracker: str, limit: int) -> tuple[bool, int]:
    return await asyncio.to_thread(_reserve_daily_api_hit_sync, base_dir, tracker, limit)
