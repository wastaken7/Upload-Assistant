# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import re
from typing import Any

from src.meta import Meta
from src.trackers.COMMON import COMMON
from src.trackers.UNIT3D import UNIT3D

Config = dict[str, Any]


class ReelFlix(UNIT3D):
    """
    ReelFLiX (HD4Free, LegacyHD) is a Private Torrent Tracker for HD MOVIES
    """

    tracker = "ReelFlix"
    base_url = "https://reelflix.cc"
    banned_groups = ()
    id_url = f"{base_url}/api/torrents/"
    upload_url = f"{base_url}/api/torrents/upload"
    search_url = f"{base_url}/api/torrents/filter"
    requests_url = f"{base_url}/api/requests/filter"
    torrent_url = f"{base_url}/torrents/"
    supported_categories = ("MOVIE",)
    tracker_urls = ("https://reelflix.xyz", "https://reelflix.cc")

    def __init__(self, config: Config) -> None:
        super().__init__(config, tracker_name="ReelFlix")
        self.config: Config = config
        self.common = COMMON(config)

    async def get_additional_checks(self, meta: Meta) -> bool:
        return self.common.check_and_confirm_adult_media_upload(meta, self.tracker)

    async def get_name(self, meta: Meta) -> dict[str, str]:
        rf_name = meta.name
        tag_value = meta.tag or ""
        tag_lower = tag_value.lower()
        invalid_tags = ["nogrp", "nogroup", "unknown", "-unk-"]

        if tag_value == "" or any(invalid_tag in tag_lower for invalid_tag in invalid_tags):
            for invalid_tag in invalid_tags:
                rf_name = re.sub(f"-{invalid_tag}", "", rf_name, flags=re.IGNORECASE)
            rf_name = f"{rf_name}-NoGroup"

        return {"name": rf_name}

    async def get_type_id(self, meta: Meta, type: str | None = None, reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        type_id = {
            "DISC": "43",
            "REMUX": "40",
            "WEBDL": "42",
            "WEBRIP": "45",
            # 'FANRES': '6',
            "ENCODE": "41",
            "HDTV": "35",
        }
        if mapping_only:
            return type_id
        if reverse:
            return {v: k for k, v in type_id.items()}
        type_value = type if type is not None else str(meta.type)
        return {"type_id": type_id.get(type_value, "0")}

    async def get_resolution_id(self, meta: Meta, resolution: str | None = None, reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        resolution_id = {
            # '8640p':'10',
            "4320p": "1",
            "2160p": "2",
            # '1440p' : '3',
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
            return {v: k for k, v in resolution_id.items()}
        resolution_value = resolution if resolution is not None else meta.resolution
        return {"resolution_id": resolution_id.get(resolution_value, "10")}
