# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
from typing import Any, ClassVar

import cli_ui

from src.console import logger
from src.meta import Meta
from src.trackers.common import Common
from src.trackers.UNIT3D import UNIT3D


class Blutopia(UNIT3D):
    """
    Blutopia (BLU) is a Private Torrent Tracker for HD MOVIES / TV
    """

    tracker = "BLUTOPIA"
    display_name = "Blutopia"
    base_url = "https://blutopia.cc"
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
        "B3LLUM",
        "BHDStudio",
        "Brrip",
        "CHD",
        "CM8",
        "CrEwSaDe",
        "d3g",
        "DeadFish",
        "DNL",
        "DTLegacy",
        "ELiTE",
        "eSc",
        "EZTV.RE",
        "EZTV",
        "F13",
        "FaNGDiNG0",
        "FGT",
        "Flights",
        "flower",
        "FRDS",
        "FUM",
        "HAiKU",
        "hallowed",
        "HD2DVD",
        "HDS",
        "HDTime",
        "Hi10",
        "ION10",
        "iPlanet",
        "JIVE",
        "KiNGDOM",
        "LAMA",
        "Leffe",
        "LEGi0N",
        "LOAD",
        "MeGusta",
        "mHD",
        "mSD",
        "NhaNc3",
        "nHD",
        "nikt0",
        "NOIVTC",
        "nSD",
        "OFT",
        "PiRaTeS",
        "playBD",
        "PlaySD",
        "playXD",
        "PRODJi",
        "RAPiDCOWS",
        "RARBG",
        "RDN",
        "REsuRRecTioN",
        "RetroPeeps",
        "RMTeam",
        "SANTi",
        "SasukeducK",
        "SicFoI",
        "SPASM",
        "SPDVD",
        "STUTTERSHIT",
        "Telly",
        "TheFarm",
        "TM",
        "TRiToN",
        "UPiNSMOKE",
        "URANiME",
        "VN_Foxcore",
        "WAF",
        "WKS",
        "x0r",
        "xRed",
        "XS",
        "YIFY",
        "ZKBL",
        "ZmN",
        "ZMNT",
    )
    id_url = f"{base_url}/api/torrents/"
    upload_url = f"{base_url}/api/torrents/upload"
    search_url = f"{base_url}/api/torrents/filter"
    requests_url = f"{base_url}/api/requests/filter"
    torrent_url = f"{base_url}/torrents/"
    supported_categories = ("TV", "MOVIE")
    tracker_urls = ("https://blutopia.cc",)
    REGION_IDS: ClassVar[dict[str, str]] = {
        "CZE": "244",
        "SVK": "245",
        "FIN": "246",
        "SWE": "247",
        "BGR": "248",
        "DNK": "249",
    }
    allowed_bloated_audio_languages = ("en",)

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config, tracker_name="BLUTOPIA")
        self.config = config
        self.common = Common(config)

    async def get_additional_checks(self, meta: Meta) -> bool:
        should_continue = True

        if not meta.is_disc:
            container = meta.container.lower()
            type_name = "" if not meta.type else meta.type.upper()
            allowed = ["mkv"]
            if type_name == "HDTV":
                allowed.append("ts")
            if type_name in ["WEBDL", "HDTV"] and "DV" in meta.hdr and "HDR" not in meta.hdr:
                allowed.append("mp4")

            if container not in allowed:
                logger.info(
                    f"{self.tracker}: [bold red]For this release, {self.tracker} requires one of the following containers: {', '.join([a.upper() for a in allowed])}[/bold red]"
                )
                return False

        if meta.type in ["ENCODE", "REMUX"] and "HDR" in meta.hdr and "DV" in meta.hdr and (not meta.unattended or (meta.unattended and meta.unattended_confirm)):
            logger.info(f"{self.tracker}: [bold red]Releases using a Dolby Vision layer from a different source have specific description requirements.[/bold red]")
            logger.info(f"{self.tracker}: [bold red]See rule 12.5. You must have a correct pre-formatted description if this release has a derived layer[/bold red]")
            if not cli_ui.ask_yes_no("Do you want to upload anyway?", default=False):
                return False
            if cli_ui.ask_yes_no("Is this a derived layer release?", default=False):
                meta.tracker_status[self.tracker]["other"] = True

        if meta.type not in ["WEBDL"] and not meta.is_disc and meta.tag in ["AOC", "CMRG", "EVO", "TERMiNAL", "ViSION"]:
            if not meta.unattended or (meta.unattended and meta.unattended_confirm):
                logger.info(f"{self.tracker}: [bold red]Group {meta.tag} is only allowed for raw type content[/bold red]")
                if cli_ui.ask_yes_no("Do you want to upload anyway?", default=False):
                    pass
                else:
                    return False
            else:
                return False

        if not meta.valid_mi_settings:
            logger.info(f"{self.tracker}: [bold red]No encoding settings in mediainfo, skipping {self.tracker} upload.[/bold red]")
            return False

        return should_continue

    async def get_name(self, meta: Meta) -> dict[str, str]:
        blu_name = meta.name
        if meta.category == "TV" and meta.episode_title != "":
            blu_name = blu_name.replace(f"{meta.episode_title} {meta.resolution}", f"{meta.resolution}", 1)
        imdb_name = meta.imdb_info.get("title", "")
        imdb_year = str(meta.imdb_info.get("year", ""))
        imdb_aka = meta.imdb_info.get("aka", "")
        year = str(meta.year) if meta.year is not None else ""
        aka = meta.aka
        webdv = meta.webdv
        if imdb_name and imdb_name.strip():
            if aka:
                blu_name = blu_name.replace(f"{aka} ", "", 1)
            blu_name = blu_name.replace(f"{meta.title}", imdb_name, 1)

            if imdb_aka and imdb_aka.strip() and imdb_aka != imdb_name and not meta.no_aka:
                blu_name = blu_name.replace(f"{imdb_name}", f"{imdb_name} AKA {imdb_aka}", 1)

        if meta.category != "TV" and imdb_year and imdb_year.strip() and year and year.strip() and imdb_year != year:
            blu_name = blu_name.replace(f"{year}", imdb_year, 1)

        if webdv:
            blu_name = blu_name.replace("HYBRID ", "", 1)

        if meta.tracker_status.get(self.tracker, {}).get("other", False):
            blu_name = blu_name.replace(f"{meta.resolution}", f"{meta.resolution} DVP5/DVP8", 1)

        return {"name": blu_name}

    async def get_additional_data(self, meta: Meta) -> dict[str, Any]:
        return {
            "mod_queue_opt_in": await self.get_flag(meta, "modq"),
        }

    async def get_region_id(self, meta: Meta) -> dict[str, str]:
        region_id = self.REGION_IDS.get(str(meta.region or "").upper())
        if region_id:
            return {"region_id": region_id}
        return await super().get_region_id(meta)

    async def get_region_name(self, region_id: int | str | None) -> str:
        region_name = {value: key for key, value in self.REGION_IDS.items()}.get(str(region_id), "")
        if region_name:
            return region_name
        try:
            normalized_id = int(region_id) if region_id is not None else 0
        except TypeError, ValueError:
            return ""
        return await self.common.unit3d_region_ids(reverse=True, region_id=normalized_id)

    async def get_category_id(
        self,
        meta: Meta,
        category: str | None = None,
        reverse: bool = False,
        mapping_only: bool = False,
    ) -> dict[str, str]:
        edition = meta.edition
        category_name = meta.category
        category_id = {"MOVIE": "1", "TV": "2", "FANRES": "3"}

        is_fanres = False

        if category_name == "MOVIE" and "FANRES" in edition:
            is_fanres = True

        if meta.tracker_status[self.tracker].get("other", False):
            is_fanres = True

        if is_fanres:
            return {"category_id": "3"}

        if mapping_only:
            return category_id
        if reverse:
            return {v: k for k, v in category_id.items()}
        if category is not None:
            return {"category_id": category_id.get(category, "0")}
        meta_category = meta.category
        resolved_id = category_id.get(meta_category, "0")
        return {"category_id": resolved_id}

    async def get_type_id(
        self,
        meta: Meta,
        type: str | None = None,
        reverse: bool = False,
        mapping_only: bool = False,
    ) -> dict[str, str]:
        type_id = {"DISC": "1", "REMUX": "3", "WEBDL": "4", "WEBRIP": "5", "HDTV": "6", "ENCODE": "12"}

        if mapping_only:
            return type_id
        if reverse:
            return {v: k for k, v in type_id.items()}
        if type is not None:
            return {"type_id": type_id.get(type, "0")}
        meta_type = meta.type
        resolved_id = type_id.get(meta_type or "", "0")
        return {"type_id": resolved_id}

    async def get_resolution_id(
        self,
        meta: Meta,
        resolution: str | None = None,
        reverse: bool = False,
        mapping_only: bool = False,
    ) -> dict[str, str]:
        resolution_id = {"8640p": "10", "4320p": "11", "2160p": "1", "1440p": "2", "1080p": "2", "1080i": "3", "720p": "5", "576p": "6", "576i": "7", "480p": "8", "480i": "9"}
        if mapping_only:
            return resolution_id
        if reverse:
            return {v: k for k, v in resolution_id.items()}
        if resolution is not None:
            return {"resolution_id": resolution_id.get(resolution, "10")}
        meta_resolution = meta.resolution
        resolved_id = resolution_id.get(meta_resolution, "10")
        return {"resolution_id": resolved_id}
