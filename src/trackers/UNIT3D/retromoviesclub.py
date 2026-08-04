# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import re
from typing import Any

from src.console import logger
from src.meta import Meta
from src.trackers.common import Common
from src.trackers.UNIT3D import UNIT3D

Config = dict[str, Any]


class RetroMoviesClub(UNIT3D):
    """Retro Movies Club (RMC) tracker adapter."""

    tracker = "RETROMOVIESCLUB"
    display_name = "RetroMoviesClub"
    base_url = "https://retro-movies.club"
    banned_groups = (
        "[Oj]",
        "3LTON",
        "4yEo",
        "ADE",
        "AFG",
        "AniHLS",
        "AnimeRG",
        "AniURL",
        "AROMA",
        "aXXo",
        "CM8",
        "CrEwSaDe",
        "DeadFish",
        "DNL",
        "ELiTE",
        "eSc",
        "FaNGDiNG0",
        "FGT",
        "Flights",
        "FRDS",
        "FUM",
        "GalaxyRG",
        "HAiKU",
        "HDS",
        "HDTime",
        "INFINITY",
        "ION10",
        "iPlanet",
        "JIVE",
        "KiNGDOM",
        "LAMA",
        "Leffe",
        "LOAD",
        "mHD",
        "nHD",
        "NOIVTC",
        "nSD",
        "PiRaTeS",
        "RARBG",
        "RDN",
        "REsuRRecTioN",
        "RMTeam",
        "SANTi",
        "SicFoI",
        "SPASM",
        "STUTTERSHIT",
        "Telly",
        "TM",
        "UPiNSMOKE",
        "WAF",
        "xRed",
        "XS",
        "YELLO",
        "YIFY",
        "YTS",
        "ZKBL",
        "ZmN",
    )
    id_url = f"{base_url}/api/torrents/"
    upload_url = f"{base_url}/api/torrents/upload"
    search_url = f"{base_url}/api/torrents/filter"
    torrent_url = f"{base_url}/torrents/"
    supported_categories = ("MOVIE",)
    tracker_urls = ("retro-movies.club",)

    def __init__(self, config: Config) -> None:
        super().__init__(config, tracker_name=self.tracker)
        self.config = config
        self.common = Common(config)

    async def get_category_id(
        self,
        meta: Meta,
        category: str = "",
        reverse: bool = False,
        mapping_only: bool = False,
    ) -> dict[str, str]:
        category_id = {"MOVIE": "1"}
        if mapping_only:
            return category_id
        if reverse:
            return {value: key for key, value in category_id.items()}
        category_value = category or meta.category
        return {"category_id": category_id.get(category_value, "0")}

    async def get_type_id(
        self,
        meta: Meta,
        type: str = "",
        reverse: bool = False,
        mapping_only: bool = False,
    ) -> dict[str, str]:
        type_id = {
            "BDMV": "1",
            "REMUX_BLURAY": "2",
            "DVD": "3",
            "REMUX_DVD": "4",
            "ENCODE": "5",
            "DVDRIP": "6",
            "WEBDL": "7",
            "WEBRIP": "8",
            "UHDTV": "9",
            "HDTV": "10",
            "TV_SD": "11",
        }
        if mapping_only:
            return type_id
        if reverse:
            return {value: key for key, value in type_id.items()}

        source = str(meta.source or "").upper()
        is_disc = str(meta.is_disc or "").upper()
        category = meta.category.upper()
        type_value = (type or str(meta.type or "")).upper()

        if is_disc == "BDMV":
            return {"type_id": "1"}
        if type_value == "REMUX" and source in {"BLURAY", "BLU-RAY"}:
            return {"type_id": "2"}
        if is_disc == "DVD":
            return {"type_id": "3"}
        if type_value == "REMUX" and source in {"DVD", "PAL DVD", "NTSC DVD"}:
            return {"type_id": "4"}
        if type_value == "ENCODE":
            return {"type_id": "5"}
        if type_value == "DVDRIP":
            return {"type_id": "6"}
        if type_value == "WEBDL":
            return {"type_id": "7"}
        if type_value == "WEBRIP" or source == "WEB":
            return {"type_id": "8"}
        if source == "UHDTV":
            return {"type_id": "9"}
        if type_value == "HDTV":
            return {"type_id": "10"}
        if category == "TV" and meta.sd == 1:
            return {"type_id": "11"}
        return {"type_id": "0"}

    async def get_resolution_id(
        self,
        meta: Meta,
        resolution: str = "",
        reverse: bool = False,
        mapping_only: bool = False,
    ) -> dict[str, str]:
        resolution_id = {
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
        }
        if mapping_only:
            return resolution_id
        if reverse:
            return {value: key for key, value in resolution_id.items()}
        resolution_value = resolution or meta.resolution
        return {"resolution_id": resolution_id.get(resolution_value, "11")}

    async def get_additional_checks(self, meta: Meta) -> bool:
        if meta.category != "MOVIE":
            logger.info(f"{self.tracker}: [bold red]Only movies are allowed.[/bold red]")
            return False
        if meta.year is not None and meta.year > 2000:
            logger.info(f"{self.tracker}: [bold red]Only movies released in 2000 or earlier are allowed.[/bold red]")
            return False
        return True

    async def get_additional_data(self, meta: Meta) -> dict[str, str]:
        return {"mod_queue_opt_in": await self.get_flag(meta, "modq")}

    async def get_name(self, meta: Meta) -> dict[str, str]:
        name = meta.name or ""
        aka = meta.aka.strip()
        if aka:
            name = name.replace(f" {aka} ", " ")
        name = re.sub(r"[^A-Za-z0-9 ._+-]+", "", name)
        return {"name": re.sub(r"\s+", " ", name).strip()}
