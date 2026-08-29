# Upload Assistant © 2026 Audionut & wastaken7 — Licensed under UAPL v1.0
import json
import re
from pathlib import Path
from typing import Any

import aiofiles
import httpx

from src.console import logger
from src.meta import Meta
from src.trackers.common import Common
from src.trackers.USENET.search_helpers import (
    build_newznab_search_query,
    get_daily_api_hit_limit,
    get_newznab_search_category_id,
    parse_newznab_dupes,
    reserve_daily_api_hit,
)

Config = dict[str, Any]


class DrunkenSlug:
    """
    DS Private Torrent Tracker
    """

    base_url = "https://drunkenslug.com"

    auth_type = "other_api"
    tracker = "DRUNKENSLUG"
    display_name = "DrunkenSlug"
    allows_bloated_audio = True
    banned_groups = ()
    search_url = f"{base_url}/api"
    torrent_url = f"{base_url}/search/"
    supported_categories = ("TV", "MOVIE", "GAME", "BOOK")
    is_usenet = True
    exact_match_only = False

    def __init__(self, config: Config) -> None:
        self.config = config
        self.common = Common(config)
        self.tracker_cfg = self.config.get("TRACKERS", {}).get(self.tracker, {})
        self.api_key = str(self.tracker_cfg.get("api_key", "")).strip()
        self.daily_api_hit_limit = get_daily_api_hit_limit(self.tracker_cfg)

    async def search_existing(self, meta: Meta) -> list[Any]:
        release_name = await self.get_name(meta)
        cache_file = Path(meta.base_dir) / "tmp" / meta.uuid / f"{self.tracker}_upload_ok"
        if release_name and Path(cache_file).exists():
            logger.info(f"{self.tracker}: [yellow]Found local upload cache.[/yellow]")
            return [release_name]

        if self.daily_api_hit_limit <= 0:
            logger.info(f"{self.tracker}: [yellow]Duplicate search via API is disabled because daily_api_hit_limit is 0.[/yellow]")
            return []

        params: dict[str, str] = {
            "cat": get_newznab_search_category_id(meta),
        }
        category = meta.category.upper()
        if category == "TV":
            params["t"] = "tvsearch"
            if meta.tvdb_id and str(meta.tvdb_id).isdigit() and int(meta.tvdb_id) > 0:
                params["tvdbid"] = str(meta.tvdb_id)
            elif meta.tmdb_id and str(meta.tmdb_id).isdigit() and int(meta.tmdb_id) > 0:
                params["tmdbid"] = str(meta.tmdb_id)
            elif meta.imdb_id and int(meta.imdb_id) > 0:
                params["imdbid"] = str(meta.imdb_id)
            else:
                params["q"] = self.get_search_query(meta)

            if meta.season_int > 0:
                params["season"] = str(meta.season_int)
            if meta.episode_int > 0:
                params["ep"] = str(meta.episode_int)
        elif category == "MOVIE":
            params["t"] = "movie"
            if meta.imdb_id and int(meta.imdb_id) > 0:
                params["imdbid"] = str(meta.imdb_id)
            elif meta.tmdb_id and str(meta.tmdb_id).isdigit() and int(meta.tmdb_id) > 0:
                params["tmdbid"] = str(meta.tmdb_id)
            else:
                params["q"] = self.get_search_query(meta)
        else:
            params["t"] = "search"
            params["q"] = self.get_search_query(meta)

        dupes: list[dict[str, Any]] = []
        seen_keys: set[str] = set()
        async with httpx.AsyncClient(timeout=10.0) as client:
            allowed, used_hits = await reserve_daily_api_hit(meta.base_dir, self.tracker, self.daily_api_hit_limit)
            if not allowed:
                logger.info(f"{self.tracker}: [yellow]Duplicate search skipped because the 24-hour API hit limit ({self.daily_api_hit_limit}) has been reached.[/yellow]")
                return []
            request_params = {
                "apikey": self.api_key,
                "limit": "100",
                "extended": "1",
                **params,
            }
            response = await client.get(self.search_url, params=request_params)
            logger.debug(f"{self.tracker}: Duplicate search used API hit {used_hits}/{self.daily_api_hit_limit} in the last 24 hours.")
            response.raise_for_status()

            if not response.text.strip():
                return []

            for dupe in self._parse_dupes_from_response(response.text):
                key = str(dupe.get("link") or dupe.get("name") or "")
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                dupes.append(dupe)

        return dupes

    async def get_name(self, meta: Meta) -> str:
        return meta.scene_name or meta.basename_no_ext

    def get_search_query(self, meta: Meta) -> str:
        return build_newznab_search_query(meta)

    def _parse_dupes_from_response(self, response_text: str) -> list[dict[str, Any]]:
        return parse_newznab_dupes(response_text)

    async def upload(self, meta: Meta) -> bool:
        status_map = meta.tracker_status
        if self.tracker not in status_map:
            status_map[self.tracker] = {}
        status_dict = status_map[self.tracker]

        nzb_path = meta.nzb_path
        if not nzb_path or not await self.common.check_nzb_file(self.tracker, meta):
            status_dict["status_message"] = "data error: NZB file missing or password missing in header"
            return False

        nzb_name = f"{await self.get_name(meta)}.nzb"

        async with aiofiles.open(nzb_path, "rb") as f:
            nzb_content = await f.read()

        files = {"files[]": (nzb_name, nzb_content, "application/x-nzb")}
        headers = {"X-API-Key": self.api_key}

        if meta.debug:
            status_dict["status_message"] = "Debug mode enabled, skipping upload."
            return True
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post("https://nzbs.drunkenslug.com/upload.php", headers=headers, files=files)

            if response.status_code not in (200, 201):
                status_dict["status_message"] = f"data error: HTTP {response.status_code} - {response.text}"
                return False

            try:
                data = response.json()
                results = data.get("results", [])
                if not results:
                    status_dict["status_message"] = "data error: No results returned from tracker."
                    return False

                clean_result = results[0].replace(f"{nzb_name}: ", "[redacted]: ")
                clean_result = re.sub(r"(\buploaded by\s+)\S+", r"\1[redacted]", clean_result, flags=re.IGNORECASE)
                status_dict["status_message"] = clean_result
                status_dict["torrent_id"] = nzb_name.replace(".nzb", "")

                cache_dir = Path(meta.base_dir) / "tmp" / meta.uuid
                Path(cache_dir).mkdir(parents=True, exist_ok=True)
                async with aiofiles.open(Path(cache_dir) / f"{self.tracker}_upload_ok", "w", encoding="utf-8") as cache_handle:
                    await cache_handle.write("ok")

                return True
            except json.JSONDecodeError:
                status_dict["status_message"] = "data error: Could not decode JSON response."
                return False

        except httpx.TimeoutException:
            status_dict["status_message"] = "data error: Request timed out after 60 seconds"
            return False
        except httpx.RequestError as e:
            status_dict["status_message"] = f"data error: Unable to upload. Error: {e}"
            return False
        except Exception as e:
            status_dict["status_message"] = f"data error: Unexpected error. Error: {e}"
            return False
