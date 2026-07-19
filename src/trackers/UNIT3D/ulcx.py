# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import re
from typing import Any

import aiofiles
import cli_ui

from src.console import logger
from src.get_desc import DescriptionBuilder
from src.meta import Meta
from src.trackers.UNIT3D import UNIT3D

Config = dict[str, Any]


class ULCX(UNIT3D):
    """
    upload.cx (ULCX) is a Private Torrent Tracker for MOVIES / TV
    """

    tracker = "ULCX"
    display_name = "ULCX"
    reject_english_original_bloat = True
    base_url = "https://upload.cx"
    banned_groups = (
        "4K4U",
        "Alcaide_Kira",
        "AROMA",
        "d3g",
        "EMBER",
        "FGT",
        "FnP",
        "FRDS",
        "Grym",
        "HDT",
        "Hi10",
        "iAHD",
        "INFINITY",
        "ION10",
        "iVy",
        "Judas",
        "LAMA",
        "MeGusta",
        "NAHOM",
        "Niblets",
        "nikt0",
        "OFT",
        "PHOCiS",
        "PiRaTeS",
        "QxR",
        "R&H",
        "RARBG",
        "seedpool",
        "Sicario",
        "SM737",
        "SPDVD",
        "SPx",
        "SWTYBLZ",
        "TAoE",
        "TGx",
        "Tigole",
        "TSP",
        "TSPxL",
        "VXT",
        "Vyndros",
        "Will1869",
        "x0r",
        "YIFY",
    )
    id_url = f"{base_url}/api/torrents/"
    upload_url = f"{base_url}/api/torrents/upload"
    requests_url = f"{base_url}/api/requests/filter"
    search_url = f"{base_url}/api/torrents/filter"
    torrent_url = f"{base_url}/torrents/"
    supported_categories = ("TV", "MOVIE")
    tracker_urls = ("upload.cx",)

    def __init__(self, config: Config) -> None:
        super().__init__(config, tracker_name="ULCX")
        self.config = config

    async def get_additional_checks(self, meta: Meta) -> bool:
        if "concert" in meta.keywords:
            if not meta.unattended or (meta.unattended and meta.unattended_confirm):
                logger.info(f"{self.tracker}: [bold red]Concerts not allowed.[/bold red]")
                if cli_ui.ask_yes_no("Do you want to upload anyway?", default=False):
                    pass
                else:
                    return False
            else:
                return False

        if meta.type == "ENCODE" and meta.tag and meta.tag[1:] in ("EDGE2020", "NuBz", "Ralphy"):
            logger.info(f"{self.tracker}: [bold red]Encodes from {meta.tag} are not allowed.[/bold red]")
            return False

        if meta.video_codec == "HEVC" and meta.resolution != "2160p" and "animation" not in meta.keywords and meta.anime is not True and not meta.uhd:
            if not meta.unattended or (meta.unattended and meta.unattended_confirm):
                logger.info(f"{self.tracker}: [bold red]This content might not fit HEVC rules.[/bold red]")
                if cli_ui.ask_yes_no("Do you want to upload anyway?", default=False):
                    pass
                else:
                    return False
            else:
                return False
        if meta.type in ["ENCODE", "HDTV"] and meta.resolution not in ["8640p", "4320p", "2160p", "1440p", "1080p", "1080i", "720p"]:
            if not meta.unattended:
                logger.info(f"{self.tracker}: [bold red]Encodes must be at least 720p resolution.[/bold red]")
            return False

        if meta.type in ["DVDRIP"]:
            if not meta.unattended:
                logger.info(f"{self.tracker}: [bold red]DVDRIPs are not allowed.[/bold red]")
            return False

        if meta.is_disc != "BDMV" and not await self.common.check_language_requirements(
            meta, self.tracker, languages_to_check=["english"], check_audio=True, check_subtitle=True
        ):
            return False

        if not meta.valid_mi_settings:
            logger.info(f"{self.tracker}: [bold red]No encoding settings in mediainfo, skipping upload.[/bold red]")
            return False

        if meta.personalrelease:
            if meta.has_multiple_default_audio_tracks:
                logger.info(f"{self.tracker}: [bold red]Multiple default audio tracks detected, skipping upload.[/bold red]")
                return False

            if meta.has_multiple_default_subtitle_tracks:
                logger.info(f"{self.tracker}: [bold red]Multiple default subtitle tracks detected, skipping upload.[/bold red]")
                return False

        if meta.non_disc_has_pcm_audio_tracks:
            logger.info(f"{self.tracker}: [bold red]Non-disc source with PCM audio tracks detected, skipping upload.[/bold red]")
            return False

        if meta.discs_missing_certificate:
            logger.info(f"{self.tracker}: [bold red]Disc source(s) missing BD certificate, skipping upload.[/bold red]")
            return False

        return True

    async def get_additional_data(self, meta: Meta) -> dict[str, Any]:
        return {
            "mod_queue_opt_in": await self.get_flag(meta, "modq"),
        }

    async def get_description(self, meta: Meta) -> dict[str, str]:
        desc = await DescriptionBuilder(self.tracker, self.config).unit3d_edit_desc(meta)

        if meta.adult_media:
            pattern = r"(\[center\](?:(?!\[/center\]).)*\[/center\])"

            def wrap_in_spoiler(match: re.Match[str]) -> str:
                center_block = match.group(1)
                if "[img" not in center_block.lower():
                    return center_block
                return f"[center][spoiler=Screenshots]{center_block}[/spoiler][/center]"

            desc = re.sub(pattern, wrap_in_spoiler, desc, flags=re.DOTALL)
            async with aiofiles.open(f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/[{self.tracker}]DESCRIPTION.txt", "w", encoding="utf-8") as f:
                await f.write(desc)

        return {"description": desc}

    async def get_name(self, meta: Meta) -> dict[str, str]:
        ulcx_name = meta.name
        imdb_name = meta.imdb_info.get("title", "")
        imdb_year = str(meta.imdb_info.get("year", ""))
        imdb_aka = meta.imdb_info.get("aka", "")
        year = str(meta.year) if meta.year is not None else ""
        aka = meta.aka
        if imdb_name and imdb_name.strip():
            if aka:
                ulcx_name = ulcx_name.replace(f"{aka} ", "", 1)
            ulcx_name = ulcx_name.replace(f"{meta.title}", imdb_name, 1)
            if imdb_aka and imdb_aka.strip() and imdb_aka != imdb_name and not meta.no_aka and not meta.anime:
                ulcx_name = ulcx_name.replace(f"{imdb_name}", f"{imdb_name} AKA {imdb_aka}", 1)
        if "Hybrid" in ulcx_name and meta.type == "WEBDL":
            ulcx_name = ulcx_name.replace("Hybrid ", "", 1)
        if meta.category != "TV" and imdb_year and imdb_year.strip() and year and year.strip() and imdb_year != year:
            ulcx_name = ulcx_name.replace(f"{year}", imdb_year, 1)

        if meta.type == "WEBDL" and ("hybrid" in meta.edition.lower() or meta.webdv):
            ulcx_name = ulcx_name.replace("Hybrid ", "", 1)

        return {"name": ulcx_name}
