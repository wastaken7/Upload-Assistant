# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
from typing import Any

import cli_ui

from src.console import logger
from src.languages import languages_manager
from src.meta import Meta
from src.rehostimages import ImageHostPolicy, RehostImagesManager
from src.trackers.common import Common
from src.trackers.UNIT3D import UNIT3D

Config = dict[str, Any]


class Aura4K(UNIT3D):
    """
    AURA4K is a Private Torrent Tracker for MOVIES / TV
    """

    tracker = "AURA4K"
    display_name = "Aura4K"
    allows_bloated_audio = True
    base_url = "https://aura4k.net"
    approved_image_hosts = ("onlyimage", "imgbox", "ptscreens", "imgbb", "imgur", "postimg")
    image_host_policy = ImageHostPolicy(
        {
            "ibb.co": "imgbb",
            "imgbox.com": "imgbox",
            "imgur.com": "imgur",
            "postimg.cc": "postimg",
            "ptscreens.com": "ptscreens",
            "onlyimage.org": "onlyimage",
        },
        approved_image_hosts,
    )
    banned_groups = ("BiTOR", "DepraveD", "Flights", "SasukeducK", "SPDVD", "TEKNO3D")
    id_url = f"{base_url}/api/torrents/"
    upload_url = f"{base_url}/api/torrents/upload"
    search_url = f"{base_url}/api/torrents/filter"
    torrent_url = f"{base_url}/torrents/"
    supported_categories = ("TV", "MOVIE")

    def __init__(self, config: Config) -> None:
        super().__init__(config, tracker_name="AURA4K")
        self.config = config
        self.common = Common(config)
        self.rehost_images_manager = RehostImagesManager(config)

    async def get_type_id(
        self,
        meta: Meta,
        type: str | None = None,
        reverse: bool = False,
        mapping_only: bool = False,
    ) -> dict[str, str]:
        type_id = {"DISC": "1", "REMUX": "2", "WEBDL": "4", "ENCODE": "3"}
        if mapping_only:
            return type_id
        if reverse:
            return {v: k for k, v in type_id.items()}
        type_value = type if type is not None and type != "" else meta.type or ""
        return {"type_id": type_id.get(type_value, "0")}

    async def get_resolution_id(
        self,
        meta: Meta,
        resolution: str | None = None,
        reverse: bool = False,
        mapping_only: bool = False,
    ) -> dict[str, str]:
        resolution_id = {
            "4320p": "1",
            "2160p": "2",
        }
        if mapping_only:
            return resolution_id
        if reverse:
            return {v: k for k, v in resolution_id.items()}
        resolution_value = resolution if resolution is not None and resolution != "" else meta.resolution or ""
        return {"resolution_id": resolution_id.get(resolution_value, "10")}

    async def get_additional_checks(self, meta: Meta) -> bool:
        should_continue = True
        if meta.resolution not in ["2160p", "4320p"]:
            if not meta.unattended:
                logger.info(f"{self.tracker}: [red]only accepts 4K uploads.")
            return False

        if meta.type not in ["DISC", "REMUX", "WEBDL", "ENCODE"]:
            if not meta.unattended:
                logger.info(f"{self.tracker}: [red]only accepts DISC, REMUX, WEBDL, and ENCODE uploads.")
            return False

        if meta.is_disc not in ["BDMV", "DVD"] and not await self.common.check_language_requirements(
            meta, self.tracker, languages_to_check=["english"], check_audio=True, check_subtitle=True, original_language=True
        ):
            return False

        # check bitrate requirements for AURA4K uploads, but only if it's not a disc upload since discs can have variable bitrates and AURA4K doesn't specify bitrate requirements for disc uploads
        if not meta.is_disc and meta.type in ["ENCODE", "WEBDL"]:
            tracks = meta.mediainfo.get("media", {}).get("track", [])
            for track in tracks:
                if track.get("@type") == "Video":
                    encoding_settings = track.get("Encoded_Library_Settings", {})

                    if encoding_settings:
                        bit_rate = track.get("BitRate")
                        if bit_rate:
                            try:
                                bit_rate_num = int(bit_rate)
                            except ValueError, TypeError:
                                bit_rate_num = None

                            if bit_rate_num is not None:
                                bit_rate_kbps = bit_rate_num / 1000
                                if meta.category == "MOVIE" and bit_rate_kbps < 15000:
                                    if not meta.unattended:
                                        logger.info(f"{self.tracker}: Video bitrate too low: {bit_rate_kbps:.0f} kbps for AURA4K movie uploads.")
                                    return False
                                if meta.category == "TV" and bit_rate_kbps < 10000:
                                    if not meta.unattended:
                                        logger.info(f"{self.tracker}: Video bitrate too low: {bit_rate_kbps:.0f} kbps for AURA4K TV uploads.")
                                    return False
                            else:
                                if not meta.unattended or (meta.unattended and meta.unattended_confirm):
                                    logger.info(f"{self.tracker}: [bold red]Could not determine video bitrate from mediainfo for {self.tracker} upload.[/bold red]")
                                    logger.info(f"{self.tracker}: [yellow]Bitrate must be above 15000 kbps for movies and 10000 kbps for TV shows.[/yellow]")
                                    if cli_ui.ask_yes_no("Do you want to upload anyway?", default=False):
                                        pass
                                    else:
                                        return False
                                else:
                                    return False
                        else:
                            if not meta.unattended or (meta.unattended and meta.unattended_confirm):
                                logger.info(f"{self.tracker}: [bold red]Could not determine video bitrate from mediainfo for {self.tracker} upload.[/bold red]")
                                logger.info(f"{self.tracker}: [yellow]Bitrate must be above 15000 kbps for movies and 10000 kbps for TV shows.[/yellow]")
                                if cli_ui.ask_yes_no("Do you want to upload anyway?", default=False):
                                    pass
                                else:
                                    return False
                            else:
                                return False
                    else:
                        if not meta.unattended or (meta.unattended and meta.unattended_confirm):
                            logger.info(f"{self.tracker}: [bold red]Could not determine video bitrate from mediainfo for {self.tracker} upload.[/bold red]")
                            logger.info(f"{self.tracker}: [yellow]Bitrate must be above 15000 kbps for movies and 10000 kbps for TV shows.[/yellow]")
                            if cli_ui.ask_yes_no("Do you want to upload anyway?", default=False):
                                pass
                            else:
                                return False
                        else:
                            return False

        return should_continue

    async def get_additional_data(self, meta: Meta) -> dict[str, Any]:
        return {
            "mod_queue_opt_in": await self.get_flag(meta, "modq"),
        }

    async def get_name(self, meta: Meta) -> dict[str, str]:
        a4k_name: str = meta.name
        if not meta.language_checked:
            await languages_manager.process_desc_language(meta, tracker=self.tracker)
        audio_languages: list[str] = [] if not meta.audio_languages else meta.audio_languages
        if audio_languages and not await languages_manager.has_english_language(audio_languages):
            foreign_lang = audio_languages[0].upper()
            if meta.is_disc != "BDMV":
                a4k_name = a4k_name.replace(meta.resolution, f"{foreign_lang} {meta.resolution}", 1)
        return {"name": a4k_name}
