# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
from typing import Any

from src.meta import Meta
from src.trackers.common import Common
from src.trackers.UNIT3D import UNIT3D

Config = dict[str, Any]


class TheLeachZone(UNIT3D):
    """
    The Leach Zone (TLZ) is a Private Torrent Tracker for MOVIES / TV / GENERAL
    """

    tracker = "THELEACHZONE"
    display_name = "TheLeachZone"
    allows_bloated_audio = True
    base_url = "https://tlzdigital.com"
    banned_groups = ("",)
    id_url = f"{base_url}/api/torrents/"
    upload_url = f"{base_url}/api/torrents/upload"
    search_url = f"{base_url}/api/torrents/filter"
    torrent_url = f"{base_url}/torrents/"
    supported_categories = ("TV", "MOVIE")
    tracker_urls = ("https://tlzdigital.com/",)

    # TLZ type IDs: 1 = Film, 2 = CAM / pre-release, 3 = Episode, 4 = Pack.
    _pre_release_types = frozenset(
        {
            "CAM",
            "CAMRIP",
            "DCP",
            "DVDSCR",
            "HDCAM",
            "HD CAM",
            "HD-CAM",
            "HD_CAM",
            "HDTS",
            "PDVD",
            "R5",
            "SCR",
            "SCREENER",
            "TC",
            "TELECINE",
            "TELESYNC",
            "TELE SYNC",
            "TELE-SYNC",
            "TELE_SYNC",
            "TS",
            "WORKPRINT",
            "WP",
        }
    )

    def __init__(self, config: Config) -> None:
        super().__init__(config, tracker_name="THELEACHZONE")
        self.config: Config = config
        self.common = Common(config)

    async def get_category_id(self, meta: Meta, category: str | None = None, reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        _ = (category, reverse, mapping_only)
        category_value = str(meta.category or "").strip().upper()
        category_id = {
            "MOVIE": "1",
            "TV": "2",
        }.get(category_value, "0")
        return {"category_id": category_id}

    async def get_type_id(self, meta: Meta, type: str | None = None, reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        _ = (type, reverse, mapping_only)
        type_value = str(meta.type or "").strip().upper()
        source_value = str(meta.source or "").strip().upper()
        category_value = str(meta.category or "").strip().upper()
        type_id = {
            "FILM": "1",
            "EPISODE": "3",
            "PACK": "4",
        }.get(type_value, "0")

        if meta.tv_pack:
            type_id = "4"
        elif meta.pre_release or type_value in self._pre_release_types or source_value in self._pre_release_types:
            type_id = "2"
        elif category_value == "MOVIE":
            type_id = "1"
        elif type_id != "4":
            type_id = "3"

        return {"type_id": type_id}
