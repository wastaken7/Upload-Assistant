# Upload Assistant © 2026 Audionut & wastaken7 — Licensed under UAPL v1.0
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


class NzbNest:
    """NzbNest Usenet indexer."""

    base_url = "https://nzbnest.com"
    search_url = f"{base_url}/api"
    upload_url = f"{base_url}/v1/upload"
    torrent_url = f"{base_url}/account/releases/"

    auth_type = "other_api"
    tracker = "NZBNEST"
    display_name = "NzbNest"
    allows_bloated_audio = True
    banned_groups: tuple[str, ...] = ()
    supported_categories = ("TV", "MOVIE", "GAME", "BOOK", "MUSIC")
    is_usenet = True
    exact_match_only = False

    def __init__(self, config: Config) -> None:
        self.config = config
        self.common = Common(config)
        self.tracker_cfg = config.get("TRACKERS", {}).get(self.tracker, {})
        self.api_key = str(self.tracker_cfg.get("api_key", "")).strip()
        self.daily_api_hit_limit = get_daily_api_hit_limit(self.tracker_cfg)

    async def get_name(self, meta: Meta) -> str:
        return meta.scene_name or meta.basename_no_ext

    def get_search_query(self, meta: Meta) -> str:
        return build_newznab_search_query(meta)

    def _parse_dupes_from_response(self, response_text: str) -> list[dict[str, Any]]:
        return parse_newznab_dupes(response_text, self.torrent_url, use_title_as_file=True)

    async def search_existing(self, meta: Meta) -> list[Any]:
        release_name = await self.get_name(meta)
        cache_file = Path(meta.base_dir) / "tmp" / meta.uuid / f"{self.tracker}_upload_ok"
        if release_name and cache_file.exists():
            logger.info(f"{self.tracker}: [yellow]Found local upload cache.[/yellow]")
            return [release_name]

        if self.daily_api_hit_limit <= 0:
            logger.info(f"{self.tracker}: [yellow]Duplicate search via API is disabled because daily_api_hit_limit is 0.[/yellow]")
            return []

        category = meta.category.upper() if not meta.is_sports else "SPORTS"
        params: dict[str, str] = {}
        if category != "XXX":
            params["cat"] = get_newznab_search_category_id(meta)

        if category == "TV":
            params["t"] = "tvsearch"
            if meta.tvdb_id and str(meta.tvdb_id).isdigit():
                params["tvdbid"] = str(meta.tvdb_id)
            elif meta.tmdb_id and str(meta.tmdb_id).isdigit():
                params["tmdbid"] = str(meta.tmdb_id)
            elif meta.imdb_tt:
                params["imdbid"] = meta.imdb_tt
            else:
                params["q"] = self.get_search_query(meta)
            if meta.season_int > 0:
                params["season"] = str(meta.season_int)
            if meta.episode_int > 0:
                params["ep"] = str(meta.episode_int)
        elif category == "MOVIE":
            params["t"] = "movie"
            if meta.imdb_tt:
                params["imdbid"] = meta.imdb_tt
            elif meta.tmdb_id and str(meta.tmdb_id).isdigit():
                params["tmdbid"] = str(meta.tmdb_id)
            else:
                params["q"] = self.get_search_query(meta)
        else:
            params.update(t="search", q=self.get_search_query(meta))

        allowed, used_hits = await reserve_daily_api_hit(meta.base_dir, self.tracker, self.daily_api_hit_limit)
        if not allowed:
            logger.info(f"{self.tracker}: [yellow]Duplicate search skipped because the 24-hour API hit limit ({self.daily_api_hit_limit}) has been reached.[/yellow]")
            return []

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(self.search_url, params={"apikey": self.api_key, "limit": "100", "extended": "1", **params})
        logger.debug(f"{self.tracker}: Duplicate search used API hit {used_hits}/{self.daily_api_hit_limit} in the last 24 hours.")
        response.raise_for_status()
        return self._parse_dupes_from_response(response.text) if response.text.strip() else []

    async def _get_nfo_file(self, meta: Meta, nzb_path: Path) -> tuple[str, bytes, str] | None:
        nfo_dir = Path(meta.base_dir) / "tmp" / meta.uuid
        candidates: list[Path] = []
        if meta.scene:
            candidates.extend(nfo_dir.glob("*.nfo"))
        elif meta.is_disc == "BDMV":
            candidates.append(nfo_dir / "BD_SUMMARY_00.txt")
        else:
            candidates.append(nfo_dir / "MEDIAINFO_CLEANPATH.txt")
        candidates.extend(nfo_dir.glob("*.nfo"))

        for path in candidates:
            if path.exists() and path.is_file():
                async with aiofiles.open(path, "rb") as handle:
                    return f"{nzb_path.stem}.nfo", await handle.read(), "text/plain"
        return None

    async def upload(self, meta: Meta) -> bool:
        status_dict = meta.tracker_status.setdefault(self.tracker, {})
        nzb_path_value = meta.nzb_path
        if not nzb_path_value or not await self.common.check_nzb_file(self.tracker, meta):
            status_dict["status_message"] = "data error: NZB file missing or password missing in header"
            return False

        nzb_path = Path(nzb_path_value)
        async with aiofiles.open(nzb_path, "rb") as handle:
            nzb_content = await handle.read()
        files: dict[str, tuple[str, bytes, str]] = {"file": (nzb_path.name, nzb_content, "application/x-nzb")}
        nfo_file = await self._get_nfo_file(meta, nzb_path)
        if nfo_file:
            files["nfo"] = nfo_file

        if meta.debug:
            status_dict["status_message"] = "Debug mode enabled, skipping upload."
            return True

        try:
            async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
                response = await client.post(self.upload_url, params={"apikey": self.api_key}, files=files)
            if response.status_code not in (200, 201):
                status_dict["status_message"] = f"data error: HTTP {response.status_code} - {response.text}"
                return False

            response_data = response.json()
            guid = response_data.get("guid") if isinstance(response_data, dict) else None
            if not guid:
                status_dict["status_message"] = "data error: NzbNest did not return a release guid."
                return False

            status_dict["status_message"] = "Upload successful"
            status_dict["torrent_id"] = str(guid)
            cache_dir = Path(meta.base_dir) / "tmp" / meta.uuid
            cache_dir.mkdir(parents=True, exist_ok=True)
            async with aiofiles.open(cache_dir / f"{self.tracker}_upload_ok", "w", encoding="utf-8") as handle:
                await handle.write("ok")
            return True
        except httpx.TimeoutException:
            status_dict["status_message"] = "data error: Request timed out after 60 seconds"
        except httpx.RequestError as error:
            status_dict["status_message"] = f"data error: Unable to upload. Error: {error}"
        except Exception as error:
            status_dict["status_message"] = f"data error: Unexpected error. Error: {error}"
        return False
