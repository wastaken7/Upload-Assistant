# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
from typing import Any, cast

import httpx

from src.console import logger
from src.meta import Meta
from src.trackers.common import Common
from src.trackers.UNIT3D import UNIT3D

Config = dict[str, Any]


class Racing4Everyone(UNIT3D):
    """
    RACING4EVERYONE (R4E) is a Private Torrent Tracker for RACING
    """

    tracker = "RACING4EVERYONE"
    display_name = "Racing4Everyone"
    base_url = "https://racing4everyone.eu"
    banned_groups: tuple[str, ...] = ()
    id_url = f"{base_url}/api/torrents/"
    upload_url = f"{base_url}/api/torrents/upload"
    search_url = f"{base_url}/api/torrents/filter"
    torrent_url = f"{base_url}/torrents/"
    supported_categories = ("TV", "MOVIE")

    def __init__(self, config: Config) -> None:
        super().__init__(config, tracker_name="RACING4EVERYONE")
        self.config: Config = config
        self.common = Common(config)

    async def get_category_id(self, meta: Meta, category: str | None = None, reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        _ = (category, reverse, mapping_only)
        category_id = "24"
        # Use stored genre IDs if available
        if meta and meta.genre_ids:
            genre_ids = str(meta.genre_ids).split(",")
            is_docu = "99" in genre_ids

            if meta.category == "MOVIE":
                category_id = "70"  # Motorsports Movie
                if is_docu:
                    category_id = "66"  # Documentary
            elif meta.category == "TV":
                category_id = "79"  # TV Series
                if is_docu:
                    category_id = "2"  # TV Documentary
            else:
                category_id = "24"

        return {"category_id": category_id}

    async def get_type_id(self, meta: Meta, type: str | None = None, reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        _ = (type, reverse, mapping_only)
        type_id = {
            "8640p": "2160p",
            "4320p": "2160p",
            "2160p": "2160p",
            "1440p": "1080p",
            "1080p": "1080p",
            "1080i": "1080i",
            "720p": "720p",
            "576p": "SD",
            "576i": "SD",
            "480p": "SD",
            "480i": "SD",
        }.get(str(meta.type), "10")
        return {"type_id": type_id}

    async def get_personal_release(self, meta: Meta) -> dict[str, str]:
        _ = meta
        return {}

    async def get_internal(self, meta: Meta) -> dict[str, str]:
        _ = meta
        return {}

    async def get_featured(self, meta: Meta) -> dict[str, str]:
        _ = meta
        return {}

    async def get_free(self, meta: Meta) -> dict[str, str]:
        _ = meta
        return {}

    async def get_doubleup(self, meta: Meta) -> dict[str, str]:
        _ = meta
        return {}

    async def get_sticky(self, meta: Meta) -> dict[str, str]:
        _ = meta
        return {}

    async def get_resolution_id(self, meta: Meta, resolution: str | None = None, reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        _ = (meta, resolution, reverse, mapping_only)
        return {}

    async def search_existing(self, meta: Meta) -> list[dict[str, Any]]:
        dupes: list[dict[str, Any]] = []
        url = self.search_url
        params: dict[str, Any] = {
            "api_token": str(self.config["TRACKERS"]["RACING4EVERYONE"]["api_key"]).strip(),
            "tmdb": meta.tmdb,
            "categories[]": (await self.get_category_id(meta))["category_id"],
            "types[]": (await self.get_type_id(meta))["type_id"],
            "name": "",
        }
        if meta.category == "TV":
            params["name"] = f"{meta.season}"
        if meta.edition != "":
            params["name"] = str(params["name"]) + meta.edition
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(url=url, params=params)
            if response.status_code == 200:
                data = cast(dict[str, Any], response.json())
                items = cast(list[dict[str, Any]], data.get("data", []))
                for each in items:
                    attributes = cast(dict[str, Any], each.get("attributes", {}))
                    result_name = str(attributes.get("name", ""))
                    dupes.append({"name": result_name, "files": result_name, "size": 0, "link": "", "file_count": 0, "download": ""})
            else:
                logger.info(f"[bold red]Failed to search torrents. HTTP Status: {response.status_code}")

        return dupes
