# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
from typing import Any

from src.get_desc import DescriptionBuilder
from src.meta import Meta
from src.trackers.common import Common
from src.trackers.UNIT3D import UNIT3D
from src.trackers.UNIT3D.capybarabr import CapybaraBR

Config = dict[str, Any]


class Samaritano(UNIT3D):
    """
    SAMARITANO is a BRAZILIAN Private tracker for MOVIES / TV / GENERAL
    """

    tracker = "SAMARITANO"
    display_name = "Samaritano"
    base_url = "https://samaritano.cc"
    banned_groups = ()
    id_url = f"{base_url}/api/torrents/"
    upload_url = f"{base_url}/api/torrents/upload"
    search_url = f"{base_url}/api/torrents/filter"
    torrent_url = f"{base_url}/torrents/"
    requests_url = f"{base_url}/api/requests/filter"
    supported_categories = ("TV", "MOVIE", "BOOK", "GAME")
    tracker_urls = ("https://samaritano.cc",)
    allows_bloated_audio = True

    def __init__(self, config: Config) -> None:
        super().__init__(config, tracker_name="SAMARITANO")
        self.config: Config = config
        self.common = Common(config)

    async def get_resolution_id(self, meta: Meta, resolution: str = "", reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        resolution_id = {
            "4320p": "1",
            "2160p": "2",
            "1080p": "3",
            "720p": "5",
            "480p": "8",
        }
        if mapping_only:
            return resolution_id
        if reverse:
            return {v: k for k, v in resolution_id.items()}
        if resolution:
            return {"resolution_id": resolution_id.get(resolution, "10")}
        meta_resolution = meta.resolution
        resolved_id = resolution_id.get(meta_resolution, "10")
        return {"resolution_id": resolved_id}

    async def get_name(self, meta: Meta) -> dict[str, str]:
        cbr = CapybaraBR(self.config)
        cbr.tracker = self.tracker
        return await cbr.get_name(meta)

    async def get_category_id(self, meta: Meta, category: str | None = None, reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
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
        if reverse:
            return {v: k for k, v in cat_map.items()}

        resolved_category = category if category is not None and category != "" else meta.category
        if meta.anime is True and resolved_category == "TV":
            resolved_category = "ANIME"

        if resolved_category == "BOOK":
            if meta.audiobook:
                resolved_category = "AUDIOBOOK"
            elif meta.comic or meta.manga:
                resolved_category = "HQS_E_MANGAS"
            else:
                resolved_category = "LIVROS"

        category_id = cat_map.get(resolved_category, "0")
        return {"category_id": category_id}

    async def get_type_id(self, meta: Meta, type: str | None = None, reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        nin_term = (bytes([110, 105, 110, 116, 101, 110, 100, 111]).decode()).upper()
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
            f"{nin_term}": "54",
            "MOBILE": "55",
            "OUTRO": "76",
        }
        if mapping_only:
            return type_id
        if reverse:
            return {v: k for k, v in type_id.items()}

        resolved_type = type if type is not None and type != "" else meta.type
        if isinstance(resolved_type, str):
            resolved_type = resolved_type.upper().strip().lstrip(".")

        if resolved_type == "GAME" or (meta.category == "GAME" and resolved_type not in type_id):
            platform = meta.platform.lower()
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
            val = type_id.get(resolved_type or "", "0")
            if meta.category == "BOOK" and val == "0":
                val = "68"

        return {"type_id": val}

    async def get_additional_data(self, meta: Meta) -> dict[str, Any]:
        data: dict[str, Any] = {
            "mod_queue_opt_in": await self.get_flag(meta, "modq"),
        }

        return data

    async def get_additional_checks(self, meta: Meta) -> bool:
        if meta.category == "BOOK":
            return True

        return await self.common.check_portuguese_video_requirements(meta, self.tracker)

    async def get_description(self, meta: Meta) -> dict[str, str]:
        signature = f"[right][url=https://github.com/wastaken7/Upload-Assistant][size=4]Compartilhado com {meta.ua_name} {meta.current_version} (fork)[/size][/url][/right]"
        return {
            "description": await DescriptionBuilder(self.tracker, self.config, "pt-BR").general_description_generator(
                meta,
                mediainfo=False,
                nfo=False,
                signature=signature,
            )
        }
