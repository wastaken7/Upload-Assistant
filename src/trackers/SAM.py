# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
from typing import Any, Optional

from src.trackers.CBR import CBR
from src.trackers.COMMON import COMMON
from src.trackers.UNIT3D import UNIT3D

Meta = dict[str, Any]
Config = dict[str, Any]


class SAM(UNIT3D):
    def __init__(self, config: Config) -> None:
        super().__init__(config, tracker_name="SAM")
        self.config: Config = config
        self.common = COMMON(config)
        self.tracker = "SAM"
        self.base_url = "https://samaritano.cc"
        self.id_url = f"{self.base_url}/api/torrents/"
        self.upload_url = f"{self.base_url}/api/torrents/upload"
        self.search_url = f"{self.base_url}/api/torrents/filter"
        self.torrent_url = f"{self.base_url}/torrents/"
        self.requests_url = f"{self.base_url}/api/requests/filter"
        self.banned_groups = []
        pass

    async def get_name(self, meta: Meta) -> dict[str, str]:
        cbr = CBR(self.config)
        cbr.tracker = self.tracker
        return await cbr.get_name(meta)

    async def get_category_id(self, meta: Meta, category: Optional[str] = None, reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        cat_map = {
            "MOVIE": "1",
            "TV": "2",
            "ANIME": "3",
            "CURSOS": "4",
            "GAMES": "5",
            "LIVROS": "6",
            "HQS_E_MANGAS": "7",
            "AUDIOBOOK": "8",
            "PROGRAMAS": "9",
            "MATERIAIS_DE_APOIO": "10",
            "DIVERSOS": "11",
            "MUSIC": "12",
        }
        if mapping_only:
            return cat_map
        elif reverse:
            return {v: k for k, v in cat_map.items()}

        resolved_category = category if category is not None and category != "" else meta.get("category", "")
        if resolved_category == "BOOK":
            if meta.get("audiobook", False):
                resolved_category = "AUDIOBOOK"
            elif meta.get("comic", False) or meta.get("manga", False):
                resolved_category = "HQS_E_MANGAS"
            else:
                resolved_category = "LIVROS"

        category_id = cat_map.get(resolved_category, "0")
        return {"category_id": category_id}

    async def get_type_id(self, meta: Meta, type: Optional[str] = None, reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        type_id = {
            "DISC": "1",
            "REMUX": "2",
            "ENCODE": "3",
            "DVDRIP": "3",
            "WEBDL": "4",
            "WEBRIP": "5",
            "HDTV": "6",
            "AZW3": "57",
            "CBR": "58",
            "CBZ": "59",
            "MOBI": "60",
            "PDF": "61",
            "EPUB": "62",
            "KFX": "63",
            "MP3": "67",
            "FLAC": "78",
            "OTHER": "68",
        }
        if mapping_only:
            return type_id
        elif reverse:
            return {v: k for k, v in type_id.items()}

        resolved_type = type if type is not None and type != "" else meta.get("type", "")
        if isinstance(resolved_type, str):
            resolved_type = resolved_type.upper().strip().lstrip(".")

        val = type_id.get(resolved_type, "0")
        if meta.get("category") == "BOOK" and val == "0":
            val = "68"

        return {"type_id": val}

    async def get_additional_data(self, meta: Meta) -> dict[str, Any]:
        data: dict[str, Any] = {
            "mod_queue_opt_in": await self.get_flag(meta, "modq"),
        }

        return data

    async def get_additional_checks(self, meta: Meta) -> bool:
        if meta.get("category") == "BOOK":
            return True
        return await self.common.check_language_requirements(
            meta, self.tracker, languages_to_check=["portuguese", "português"], check_audio=True, check_subtitle=True
        )
