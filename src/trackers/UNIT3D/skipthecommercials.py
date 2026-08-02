# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import re
from typing import Any

import cli_ui

from src.console import logger
from src.get_desc import DescriptionBuilder
from src.meta import Meta
from src.rehostimages import ImageHostPolicy, RehostImagesManager
from src.trackers.common import Common
from src.trackers.UNIT3D import UNIT3D

Config = dict[str, Any]


class SkipTheCommercials(UNIT3D):
    """
    SkipTheCommercials (STC) is a Private Torrent Tracker for TV
    """

    tracker = "SKIPTHECOMMERCIALS"
    display_name = "SkipTheCommercials"
    allows_bloated_audio = True
    base_url = "https://skipthecommercials.xyz"
    banned_groups = ("",)
    approved_image_hosts = ("imgbox", "imgbb")
    image_host_policy = ImageHostPolicy({"ibb.co": "imgbb", "imgbox.com": "imgbox"}, approved_image_hosts)
    id_url = f"{base_url}/api/torrents/"
    upload_url = f"{base_url}/api/torrents/upload"
    search_url = f"{base_url}/api/torrents/filter"
    torrent_url = f"{base_url}/torrents/"
    supported_categories = ("TV", "MOVIE")
    tracker_urls = ("https://skipthecommercials.xyz",)

    def __init__(self, config: Config) -> None:
        super().__init__(config, tracker_name="SKIPTHECOMMERCIALS")
        self.config: Config = config
        self.common = Common(config)
        self.rehost_images_manager = RehostImagesManager(config)

    async def get_type_id(
        self,
        meta: Meta,
        type: str | None = None,
        reverse: bool = False,
        mapping_only: bool = False,
    ) -> dict[str, str]:
        _ = (type, reverse, mapping_only)
        type_value = str(meta.type)
        type_id = {"DISC": "1", "REMUX": "2", "WEBDL": "4", "WEBRIP": "5", "HDTV": "6", "ENCODE": "3"}.get(type_value, "0")
        if meta.tv_pack:
            is_web = type_value in ["WEBDL", "WEBRIP"]
            type_id = ("17" if not is_web else "14") if meta.sd else ("18" if not is_web else "13")

        return {"type_id": type_id}

    async def get_additional_checks(self, meta: Meta) -> bool:
        if str(meta.category) != "TV":
            if not meta.unattended:
                logger.info(f"{self.tracker}: [bold red]Only TV uploads allowed at {self.tracker}.[/bold red]")
            return False

        genres = f"{', '.join(meta.keywords)} {meta.combined_genres}"
        adult_keywords = ["xxx", "erotic", "porn", "adult", "orgy", "hentai", "adult animation", "softcore"]
        if any(re.search(rf"(^|,\s*){re.escape(keyword)}(\s*,|$)", genres, re.IGNORECASE) for keyword in adult_keywords):
            if not meta.unattended or (bool(meta.unattended) and meta.unattended_confirm):
                logger.info(f"{self.tracker}: [bold red]Porn is not allowed at {self.tracker}.[/bold red]")
                if cli_ui.ask_yes_no("Do you want to upload anyway?", default=False):
                    pass
                else:
                    return False
            else:
                return False

        return True

    async def get_description(self, meta: Meta) -> dict[str, str]:
        return {
            "description": await DescriptionBuilder(self.tracker, self.config).unit3d_edit_desc(
                meta,
                approved_image_hosts=self.approved_image_hosts,
            )
        }
