# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
from typing import Any

from src.meta import Meta
from src.tmdb import TmdbManager
from src.trackers.common import Common
from src.trackers.UNIT3D import UNIT3D

Config = dict[str, Any]


class Rastastugan(UNIT3D):
    """
    Rastastugan is a NORDIC Private Torrent Tracker for MOVIES / TV / GENERAL
    """

    tracker = "Rastastugan"
    base_url = "https://rastastugan.org"
    banned_groups = (
        "GalaxyRG",
        "INFINITY",
        "LAMA",
        "MeGUSTA",
        "NAHOM",
        "RARBG",
        "YiFY",
        "YTS",
    )
    id_url = f"{base_url}/api/torrents/"
    upload_url = f"{base_url}/api/torrents/upload"
    search_url = f"{base_url}/api/torrents/filter"
    requests_url = f"{base_url}/api/requests/filter"
    torrent_url = f"{base_url}/torrents/"
    supported_categories = ("TV", "MOVIE", "BOOK", "GAME")
    tracker_urls = ("https://rastastugan.org",)

    def __init__(self, config: Config) -> None:
        super().__init__(config, tracker_name="Rastastugan")
        self.config: Config = config
        self.tmdb_manager = TmdbManager(config)
        self.common = Common(config)

    async def get_additional_checks(self, meta: Meta) -> bool:
        nordic_languages = ["danish", "swedish", "norwegian", "icelandic", "finnish", "english"]
        return await self.common.check_language_requirements(meta, self.tracker, languages_to_check=nordic_languages, check_audio=True, check_subtitle=True)

    async def get_category_id(self, meta: Meta, category: str = "", reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        category_id = {
            "MOVIE": "1",
            "TV": "2",
            "AUDIOBOOK": "7",
            "BOOK": "8",
            "GAME": "5",
        }
        if mapping_only:
            return category_id
        if reverse:
            return {v: k for k, v in category_id.items()}
        if category:
            return {"category_id": category_id.get(category, "0")}
        meta_category = meta.category
        if meta.audiobook:
            meta_category = "AUDIOBOOK"
        resolved_id = category_id.get(meta_category, "0")
        return {"category_id": resolved_id}

    async def get_type_id(self, meta: Meta, type: str = "", reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        type_id = {
            # Video
            "DISC": "1",
            "REMUX": "2",
            "WEBDL": "4",
            "WEBRIP": "5",
            "HDTV": "6",
            "ENCODE": "3",
            "DVDRIP": "3",
            "CAM": "13",
            # Audio
            "FLAC": "7",
            "MP3": "8",
            "M4A": "14",
            "M4B": "20",
            # Game platforms / types
            "MAC": "9",
            "WINDOWS": "10",
            "CONSOLE": "11",
            "LINUX": "18",
            # Book formats
            "EPUB": "15",
            "PDF": "16",
            "MOBI": "17",
            "STL": "21",
            # Other
            "OTHER": "19",
        }
        if mapping_only:
            return type_id
        if reverse:
            return {v: k for k, v in type_id.items()}
        if type:
            resolved_type = type.upper().strip()
            return {"type_id": type_id.get(resolved_type, "0")}
        category = meta.category
        meta_type = meta.type
        if isinstance(meta_type, str):
            meta_type = meta_type.upper().strip().lstrip(".")

        resolved_id = type_id.get(meta_type or "", "0")

        if category == "GAME":
            platform = meta.platform.lower()
            if "mac" in platform:
                resolved_id = "9"
            elif "linux" in platform:
                resolved_id = "18"
            elif any(word in platform for word in ["windows", "pc"]):
                resolved_id = "10"
            elif meta.console_game:
                resolved_id = "11"
            elif meta_type in type_id:
                resolved_id = type_id[meta_type]
            else:
                resolved_id = "19"
        elif category in ("BOOK", "AUDIOBOOK") and resolved_id == "0":
            resolved_id = "19"

        return {"type_id": resolved_id}
