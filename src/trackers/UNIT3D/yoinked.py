# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
from typing import Any

from src.trackers.COMMON import COMMON
from src.trackers.UNIT3D import UNIT3D

Config = dict[str, Any]


class Yoinked(UNIT3D):
    """
    YOINK Private Torrent Tracker
    """

    tracker = "Yoinked"
    base_url = "https://yoinked.org"
    banned_groups = ("YTS", "YiFY", "LAMA", "MeGUSTA", "NAHOM", "GalaxyRG", "RARBG", "INFINITY")
    id_url = f"{base_url}/api/torrents/"
    upload_url = f"{base_url}/api/torrents/upload"
    search_url = f"{base_url}/api/torrents/filter"
    requests_url = f"{base_url}/api/requests/filter"
    torrent_url = f"{base_url}/torrents/"
    supported_categories = ("TV", "MOVIE")
    tracker_urls = ("yoinked.org",)

    def __init__(self, config: Config) -> None:
        super().__init__(config, tracker_name="Yoinked")
        self.config = config
        self.common = COMMON(config)
