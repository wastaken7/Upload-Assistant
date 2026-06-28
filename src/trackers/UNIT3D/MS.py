# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
from typing import Any

from src.meta import Meta
from src.trackers.COMMON import COMMON
from src.trackers.UNIT3D import UNIT3D

Config = dict[str, Any]


class MS(UNIT3D):
    supported_categories = ("TV", "MOVIE", "GAME")
    tracker_urls = ["midnightscene.cc"]

    def __init__(self, config: Config) -> None:
        super().__init__(config, tracker_name="MS")
        self.config: Config = config
        self.common = COMMON(config)
        self.tracker = "MS"
        self.base_url = "https://midnightscene.cc"
        self.id_url = f"{self.base_url}/api/torrents/"
        self.upload_url = f"{self.base_url}/api/torrents/upload"
        self.search_url = f"{self.base_url}/api/torrents/filter"
        self.torrent_url = f"{self.base_url}/torrents/"
        self.requests_url = f"{self.base_url}/api/requests/filter"
        self.banned_groups = []

    async def get_category_id(
        self,
        meta: Meta,
        category: str | None = None,
        reverse: bool = False,
        mapping_only: bool = False,
    ) -> dict[str, str]:
        category_id = {
            "MOVIE": "1",
            "TV": "2",
            "GAME": "4",
        }
        if mapping_only:
            return category_id
        elif reverse:
            return {v: k for k, v in category_id.items()}

        resolved_category = category if category is not None and category != "" else meta.category
        resolved_id = category_id.get(resolved_category, "0")
        return {"category_id": resolved_id}

    async def get_type_id(
        self,
        meta: Meta,
        type: str | None = None,
        reverse: bool = False,
        mapping_only: bool = False,
    ) -> dict[str, str]:
        type_id = {
            "DISC": "1",
            "REMUX": "2",
            "ENCODE": "3",
            "WEBDL": "4",
            "WEBRIP": "5",
            "HDTV": "6",
            "MP3": "7",
            "FLAC": "8",
            "PC": "9",
            "PLAYSTATION": "10",
            "NINTENDO": "11",
            "XBOX": "12",
            "DOCUMENTARY": "13",
            "TTRPG": "14",
            "3DPRINT": "15",
            "3D_PRINT": "15",
            "3D PRINT": "15",
            "OTHER": "16",
        }
        if mapping_only:
            return type_id
        elif reverse:
            return {v: k for k, v in type_id.items()}

        if type:
            resolved_type = type.upper().strip().lstrip(".")
            if resolved_type in type_id:
                return {"type_id": type_id[resolved_type]}

        # Fallbacks
        genres = str(meta.genres or "").lower()
        keywords = str(meta.keywords or "").lower()

        if "documentary" in genres or "documentary" in keywords:
            val = "13"
        elif meta.category == "GAME":
            platform = meta.platform.lower()
            nin_term = bytes([110, 105, 110, 116, 101, 110, 100, 111]).decode()

            if any(word in platform for word in ["playstation", "ps5", "ps4", "ps3", "ps2", "ps1", "psp", "vita"]):
                val = "10"
            elif "xbox" in platform:
                val = "12"
            elif any(word in platform for word in [f"{nin_term}", "switch", "wii", "3ds", "nds", "ds"]):
                val = "11"
            else:
                val = "9"  # PC
        elif "FLAC" in (meta.audio or "").upper():
            val = "8"
        elif "MP3" in (meta.audio or "").upper():
            val = "7"
        else:
            meta_type = (meta.type or "").upper().strip().lstrip(".")
            val = type_id.get(meta_type, "0")

        return {"type_id": val}
