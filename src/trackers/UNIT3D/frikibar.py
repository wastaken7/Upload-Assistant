# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
from typing import Any

from src.trackers.common import Common
from src.trackers.UNIT3D import UNIT3D


class FrikiBar(UNIT3D):
    """
    FRIKI Private Torrent Tracker
    """

    tracker = "FRIKIBAR"
    display_name = "FrikiBar"
    base_url = "https://frikibar.com"
    banned_groups = ("",)
    id_url = f"{base_url}/api/torrents/"
    upload_url = f"{base_url}/api/torrents/upload"
    search_url = f"{base_url}/api/torrents/filter"
    torrent_url = f"{base_url}/torrents/"
    supported_categories = ("TV", "MOVIE")

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config, tracker_name="FRIKIBAR")
        self.config = config
        self.common = Common(config)
