# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
from typing import Any, Optional

from src.get_desc import DescriptionBuilder
from src.trackers.COMMON import COMMON
from src.trackers.UNIT3D import UNIT3D
from src.trackers.UNIT3D.CBR import CBR

Meta = dict[str, Any]
Config = dict[str, Any]


class SAM(UNIT3D):
    supported_categories = ("TV", "MOVIE", "BOOK", "GAME")

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
            "GAME": "5",
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
            "PC": "50",
            "EMULADORES_E_ROMS": "51",
            "PLAYSTATION": "52",
            "XBOX": "53",
            "NINTENDO": "54",
            "MOBILE": "55",
            "OUTRO": "76",
        }
        if mapping_only:
            return type_id
        elif reverse:
            return {v: k for k, v in type_id.items()}

        resolved_type = type if type is not None and type != "" else meta.get("type", "")
        if isinstance(resolved_type, str):
            resolved_type = resolved_type.upper().strip().lstrip(".")

        if resolved_type == "GAME" or (meta.get("category") == "GAME" and resolved_type not in type_id):
            platform = str(meta.get("platform", "")).lower()
            nin_term = bytes([110, 105, 110, 116, 101, 110, 100, 111]).decode()

            if any(word in platform for word in ["playstation", "ps5", "ps4", "ps3", "ps2", "ps1", "psp", "vita"]):
                val = "52"
            elif "xbox" in platform:
                val = "53"
            elif any(word in platform for word in [f"{nin_term}", "switch", "wii", "3ds", "nds", "ds"]):
                val = "54"
            elif any(word in platform for word in ["android", "ios", "mobile"]):
                val = "55"
            elif any(word in platform for word in ["emulador", "rom", "emulator"]):
                val = "51"
            else:
                val = "50"  # PC
        else:
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

    async def get_description(self, meta: dict[str, Any]) -> dict[str, str]:
        signature = f"[right][url=https://github.com/wastaken7/Upload-Assistant][size=4]Compartilhado com {meta['ua_name']} {meta['current_version']}[/size][/url][/right]"
        return {"description": await DescriptionBuilder(self.tracker, self.config).unit3d_edit_desc(meta, signature=signature)}
