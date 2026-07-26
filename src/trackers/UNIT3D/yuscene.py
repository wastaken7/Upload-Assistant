# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import re
from typing import Any

import cli_ui

from src.console import logger
from src.meta import Meta
from src.trackers.common import Common
from src.trackers.UNIT3D import UNIT3D

Config = dict[str, Any]


class YUSCENE(UNIT3D):
    """
    YUSCENE is a Private Tracker for MOVIES / TV
    """

    tracker = "YUSCENE"
    display_name = "YUSCENE"
    allows_bloated_audio = True
    base_url = "https://yu-scene.net"
    banned_groups = (
        "ADDICTION",
        "B3LLUM",
        "BANDOLEROS",
        "BigEasy",
        "CINEMAXIS",
        "d3g",
        "D3US",
        "DUMMESCHWEDEN",
        "FGT",
        "GRANiTEN",
        "KiNGDOM",
        "Lama",
        "MeGusta",
        "MezRips",
        "mHD",
        "mRS",
        "msd",
        "NeXus",
        "NhaNc3",
        "nHD",
        "NorTekst",
        "NORViNE",
        "PANDEMONiUM",
        "PiTBULL",
        "Radarr",
        "RAPiDCOWS",
        "RARBG",
        "RCDiVX",
        "RDN",
        "ROCKETRACCOON",
        "SANTi",
        "SHOWTiME",
        "SOOSi",
        "SUXWIC",
        "TOXVIO",
        "TWA",
        "VXT",
        "Will1869",
        "x0r",
        "XS",
        "YIFY",
        "YOLAND",
        "YTS",
        "ZKBL",
        "ZmN",
        "ZMNT",
    )
    id_url = f"{base_url}/api/torrents/"
    upload_url = f"{base_url}/api/torrents/upload"
    search_url = f"{base_url}/api/torrents/filter"
    torrent_url = f"{base_url}/torrents/"
    supported_categories = ("TV", "MOVIE", "BOOK", "GAME", "MUSIC")
    tracker_urls = ("https://yu-scene.net",)

    def __init__(self, config: Config) -> None:
        super().__init__(config, tracker_name="YUSCENE")
        self.config = config
        self.common = Common(config)

    async def get_additional_checks(self, meta: Meta) -> bool:
        genres = f"{', '.join(meta.keywords)} {meta.combined_genres}"
        adult_keywords = ["xxx", "erotic", "porn", "adult", "orgy", "hentai", "adult animation", "softcore"]
        if any(re.search(rf"(^|,\s*){re.escape(keyword)}(\s*,|$)", genres, re.IGNORECASE) for keyword in adult_keywords):
            if not meta.unattended or (meta.unattended and meta.unattended_confirm):
                logger.info(f"{self.tracker}: [bold red]Porn/xxx is not allowed at {self.tracker}.[/bold red]")
                if cli_ui.ask_yes_no("Do you want to upload anyway?", default=False):
                    pass
                else:
                    return False
            else:
                return False

        return True

    async def get_category_id(
        self,
        meta: Meta,
        category: str | None = None,
        reverse: bool = False,
        mapping_only: bool = False,
    ) -> dict[str, str]:
        cat_map = {
            "MOVIE": "1",
            "TV": "2",
            "GAME": "7",
            "MUSIC": "8",
            "APPS": "9",
            "MUSIC_VIDEO": "10",
            "SPORT": "11",
            "EBOOK": "12",
            "AUDIOBOOK": "13",
        }
        if mapping_only:
            return cat_map
        if reverse:
            return {v: k for k, v in cat_map.items()}

        resolved_category = category if category is not None and category != "" else meta.category
        if resolved_category == "BOOK":
            resolved_category = "AUDIOBOOK" if meta.audiobook else "EBOOK"

        category_id = cat_map.get(resolved_category, "0")
        return {"category_id": category_id}

    async def get_type_id(
        self,
        meta: Meta,
        type: str | None = None,
        reverse: bool = False,
        mapping_only: bool = False,
    ) -> dict[str, str]:
        type_id = {
            "DISC": "17",
            "REMUX": "2",
            "WEBDL": "4",
            "WEBRIP": "5",
            "HDTV": "6",
            "ENCODE": "3",
            "MP3": "9",
            "FLAC": "16",
            "M4B": "23",
            "PDF": "21",
            "RAR": "22",
            "EPUB": "24",
            "MOBI": "25",
            "FB2": "26",
            "CBR": "27",
            "CBZ": "27",
            "AZW3": "28",
            "LIT": "29",
            "RTF": "30",
            "M4A": "31",
        }
        if mapping_only:
            return type_id
        if reverse:
            return {v: k for k, v in type_id.items()}

        resolved_type = type if type is not None and type != "" else meta.type
        if isinstance(resolved_type, str):
            resolved_type = resolved_type.upper().strip().lstrip(".")

        if meta.category == "MUSIC":
            resolved_type = meta.format.upper()

        val = type_id.get(resolved_type or "", "0")
        if meta.category == "BOOK" and val == "0":
            val = "21"  # Default to PDF for unknown book types

        return {"type_id": val}
