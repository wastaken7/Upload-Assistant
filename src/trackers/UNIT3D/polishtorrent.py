# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
from typing import Any

from src.meta import Meta
from src.trackers.common import Common
from src.trackers.UNIT3D import UNIT3D

Config = dict[str, Any]


class PolishTorrent(UNIT3D):
    """
    Polish Torrent (PTT) is a POLISH Private Torrent Tracker for MOVIES / TV / GENERAL
    """

    tracker = "POLISHTORRENT"
    display_name = "PolishTorrent"
    allows_bloated_audio = True
    base_url = "https://polishtorrent.top"
    banned_groups = ("ViP", "BiRD", "M@RTiNU$", "inTGrity", "CiNEMAET", "MusicET", "TeamET", "R2D2")
    id_url = f"{base_url}/api/torrents/"
    upload_url = f"{base_url}/api/torrents/upload"
    search_url = f"{base_url}/api/torrents/filter"
    torrent_url = f"{base_url}/torrents/"
    supported_categories = ("TV", "MOVIE")

    def __init__(self, config: Config) -> None:
        super().__init__(config, tracker_name="POLISHTORRENT")
        self.config: Config = config
        self.common = Common(config)

    async def get_category_id(self, meta: Meta, category: str = "", reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        category_id = {
            "MOVIE": "1",
            "TV": "9",
        }
        if mapping_only:
            return category_id
        if reverse:
            return {v: k for k, v in category_id.items()}
        if category:
            return {"category_id": category_id.get(category, "0")}
        meta_category = meta.category
        resolved_id = category_id.get(meta_category, "0")
        return {"category_id": resolved_id}

    async def get_name(self, meta: Meta) -> dict[str, str]:
        ptt_name = meta.name
        imdb_info = meta.imdb_info
        if meta.original_language == "pl" and imdb_info:
            ptt_name = ptt_name.replace(meta.aka, "")
            ptt_name = ptt_name.replace(meta.title, str(imdb_info.get("aka", "")))
        return {"name": ptt_name.strip()}
