# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import re
from typing import Any

import aiofiles

from src.get_desc import DescriptionBuilder
from src.meta import Meta
from src.trackers.common import Common
from src.trackers.UNIT3D import UNIT3D

Config = dict[str, Any]


class Locadora(UNIT3D):
    """
    LOCADORA is a BRAZILIAN Private Torrent Tracker for MOVIES / TV / ANIME
    """

    tracker = "LOCADORA"
    display_name = "Locadora"
    base_url = "https://locadora.cc"
    banned_groups = ()
    id_url = f"{base_url}/api/torrents/"
    upload_url = f"{base_url}/api/torrents/upload"
    search_url = f"{base_url}/api/torrents/filter"
    torrent_url = f"{base_url}/torrents/"
    supported_categories = ("TV", "MOVIE")
    tracker_urls = ("locadora.cc",)
    allows_bloated_audio = True

    def __init__(self, config: Config) -> None:
        super().__init__(config, tracker_name="LOCADORA")
        self.config: Config = config
        self.common = Common(config)

    async def get_name(self, meta: Meta) -> dict[str, str]:
        name_value = meta.name if meta.is_disc == "BDMV" else meta.basename_no_ext
        name = name_value

        replacements = {
            ".mkv": "",
            ".mp4": "",
            ".": " ",
            "DDP2 0": "DDP2.0",
            "DDP5 1": "DDP5.1",
            "H 264": "H.264",
            "H 265": "H.265",
            "DD+7 1": "DDP7.1",
            "AAC2 0": "AAC2.0",
            "DD5 1": "DD5.1",
            "DD2 0": "DD2.0",
            "TrueHD 7 1": "TrueHD 7.1",
            "TrueHD 5 1": "TrueHD 5.1",
            "DTS-HD MA 7 1": "DTS-HD MA 7.1",
            "DTS-HD MA 5 1": "DTS-HD MA 5.1",
            "DTS-X 7 1": "DTS-X 7.1",
            "DTS-X 5 1": "DTS-X 5.1",
            "FLAC 2 0": "FLAC 2.0",
            "FLAC 5 1": "FLAC 5.1",
            "DD1 0": "DD1.0",
            "DTS ES 5 1": "DTS ES 5.1",
            "DTS5 1": "DTS 5.1",
            "AAC1 0": "AAC1.0",
            "DD+5 1": "DDP5.1",
            "DD+2 0": "DDP2.0",
            "DD+1 0": "DDP1.0",
        }

        for old, new in replacements.items():
            name = name.replace(old, new)

        tag_lower = meta.tag.lower() if meta.tag else ""
        invalid_tags = ["nogrp", "nogroup", "unknown", "-unk-"]
        if meta.tag == "" or any(invalid_tag in tag_lower for invalid_tag in invalid_tags):
            for invalid_tag in invalid_tags:
                name = re.sub(f"-{invalid_tag}", "", name, flags=re.IGNORECASE)
            name = f"{name}-NoGroup"

        return {"name": name}

    async def get_region_id(self, meta: Meta) -> dict[str, str]:
        if meta.region == "EUR":
            return {}

        region_value = str(meta.region)
        region_id = await self.common.unit3d_region_ids(region_value)
        if region_id:
            return {"region_id": region_id}

        return {}

    async def get_mediainfo(self, meta: Meta) -> dict[str, str]:
        if meta.is_disc == "BDMV":
            mediainfo = await self.common.get_bdmv_mediainfo(meta, remove=["File size", "Overall bit rate"], char_limit=20000)
        else:
            async with aiofiles.open(f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/MEDIAINFO_CLEANPATH.txt", encoding="utf-8") as f:
                mediainfo = await f.read()

        return {"mediainfo": mediainfo}

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

    async def get_category_id(self, meta: Meta, category: str | None = None, reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        _ = (category, reverse, mapping_only)
        category_id = {"MOVIE": "1", "TV": "2", "ANIMES": "6"}.get(meta.category, "0")
        if meta.anime is True and category_id == "2":
            category_id = "6"
        return {"category_id": category_id}

    async def get_type_id(self, meta: Meta, type: str | None = None, reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        _ = (type, reverse, mapping_only)
        type_id = {"DISC": "1", "REMUX": "2", "ENCODE": "3", "WEBDL": "4", "WEBRIP": "5", "HDTV": "6"}.get(meta.type or "", "0")
        return {"type_id": type_id}

    async def get_resolution_id(self, meta: Meta, resolution: str | None = None, reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        _ = (resolution, reverse, mapping_only)
        resolution_id = {
            "4320p": "1",
            "2160p": "2",
            "1080p": "3",
            "1080i": "4",
            "720p": "5",
            "576p": "6",
            "576i": "7",
            "480p": "8",
            "480i": "9",
            "Other": "10",
        }.get(meta.resolution, "10")
        return {"resolution_id": resolution_id}

    async def get_additional_checks(self, meta: Meta) -> bool:
        return await self.common.check_portuguese_video_requirements(meta, self.tracker)
