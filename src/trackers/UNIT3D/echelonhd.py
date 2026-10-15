# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
from typing import Any

from src.meta import Meta
from src.trackers.common import Common
from src.trackers.UNIT3D import UNIT3D


class EchelonHD(UNIT3D):
    """
    EchelonHD is a Private Torrent Tracker for MOVIES / TV.

    The site runs a Go backend that reimplements the UNIT3D API
    (/api/torrents/filter, /api/torrents/{id}, /api/torrents/upload)
    with the stock UNIT3D category, type and resolution IDs.
    """

    tracker = "ECHELONHD"
    display_name = "EchelonHD"
    base_url = "https://echelonhd.me"
    banned_groups: tuple[str, ...] = ()
    id_url = f"{base_url}/api/torrents/"
    upload_url = f"{base_url}/api/torrents/upload"
    search_url = f"{base_url}/api/torrents/filter"
    torrent_url = f"{base_url}/torrents/"
    supported_categories = ("TV", "MOVIE")
    tracker_urls = ("https://echelonhd.me",)

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config, tracker_name="ECHELONHD")
        self.config = config
        self.common = Common(config)

    async def get_additional_checks(self, meta: Meta) -> bool:
        return self.common.check_and_confirm_adult_media_upload(meta, self.tracker)
