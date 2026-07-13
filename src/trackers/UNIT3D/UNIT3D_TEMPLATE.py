# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
from typing import Any

from src.meta import Meta
from src.trackers.common import COMMON
from src.trackers.UNIT3D import UNIT3D

Config = dict[str, Any]


class Unit3dTemplate(UNIT3D):  # EDIT 'Unit3dTemplate' AS ABBREVIATED TRACKER NAME
    tracker = "Abbreviated Tracker Name"
    base_url = "https://domain.tld"
    banned_groups = ("",)
    id_url = f"{base_url}/api/torrents/"
    upload_url = f"{base_url}/api/torrents/upload"
    requests_url = f"{base_url}/api/requests/filter"  # If the site supports requests via API, otherwise remove this line
    search_url = f"{base_url}/api/torrents/filter"
    torrent_url = f"{base_url}/torrents/"
    supported_categories = ("TV", "MOVIE")

    def __init__(self, config: Config) -> None:
        super().__init__(config, tracker_name="Unit3dTemplate")  # EDIT 'Unit3dTemplate' AS ABBREVIATED TRACKER NAME
        self.config = config
        self.common = COMMON(config)

    # The section below can be deleted if no changes are needed, as everything else is handled in UNIT3D.py
    # If advanced changes are required, copy the necessary functions from UNIT3D.py here
    # For example, if you need to modify the description, copy and paste the 'get_description' function and adjust it accordingly

    # If default UNIT3D categories, remove this function
    async def get_category_id(
        self,
        meta: Meta,
        category: str | None = None,
        reverse: bool = False,
        mapping_only: bool = False,
    ) -> dict[str, str]:
        _ = (category, reverse, mapping_only)
        category_id = {
            "MOVIE": "1",
            "TV": "2",
        }.get(meta.category, "0")
        return {"category_id": category_id}

    # If default UNIT3D types, remove this function
    async def get_type_id(
        self,
        meta: Meta,
        type: str | None = None,
        reverse: bool = False,
        mapping_only: bool = False,
    ) -> dict[str, str]:
        _ = (type, reverse, mapping_only)
        type_id = {"DISC": "1", "REMUX": "2", "WEBDL": "4", "WEBRIP": "5", "HDTV": "6", "ENCODE": "3"}.get(meta.type or "", "0")
        return {"type_id": type_id}

    # If default UNIT3D resolutions, remove this function
    async def get_resolution_id(
        self,
        meta: Meta,
        resolution: str | None = None,
        reverse: bool = False,
        mapping_only: bool = False,
    ) -> dict[str, str]:
        _ = (resolution, reverse, mapping_only)
        resolution_id = {
            "8640p": "10",
            "4320p": "1",
            "2160p": "2",
            "1440p": "3",
            "1080p": "3",
            "1080i": "4",
            "720p": "5",
            "576p": "6",
            "576i": "7",
            "480p": "8",
            "480i": "9",
        }.get(meta.resolution, "10")
        return {"resolution_id": resolution_id}

    # If there are tracker specific checks to be done before upload, add them here
    # Is it a movie only tracker? Are concerts banned? Etc.
    # If no checks are necessary, remove this function
    async def get_additional_checks(self, meta: Meta) -> bool:
        meta = meta
        return True

    # If the tracker has modq in the api, otherwise remove this function
    # If no additional data is required, remove this function
    async def get_additional_data(self, meta: Meta) -> dict[str, Any]:
        return {
            "mod_queue_opt_in": await self.get_flag(meta, "modq"),
        }

    # If the tracker has specific naming conventions, add them here; otherwise, remove this function
    async def get_name(self, meta: Meta) -> dict[str, str]:
        return {"name": meta.name}
