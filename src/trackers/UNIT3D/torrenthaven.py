# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
from typing import Any

from src.meta import Meta
from src.trackers.common import Common
from src.trackers.UNIT3D import UNIT3D


class TorrentHaven(UNIT3D):
    """TorrentHaven (THN) is a UNIT3D tracker for movies and TV."""

    tracker = "TORRENTHAVEN"
    display_name = "TorrentHaven"
    base_url = "https://torrenthaven.org"
    banned_groups: tuple[str, ...] = ()
    id_url = f"{base_url}/api/torrents/"
    upload_url = f"{base_url}/api/torrents/upload"
    requests_url = f"{base_url}/api/requests/filter"
    search_url = f"{base_url}/api/torrents/filter"
    torrent_url = f"{base_url}/torrents/"
    supported_categories = ("MOVIE", "TV")
    tracker_urls = ("torrenthaven.org",)

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config, tracker_name=self.tracker)
        self.common = Common(config)

    # Same as the UNIT3D defaults except DVDRip, which is 19.
    async def get_type_id(self, meta: Meta, type: str | None = None, reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        type_id = {
            "DISC": "1",
            "REMUX": "2",
            "ENCODE": "3",
            "WEBDL": "4",
            "WEBRIP": "5",
            "HDTV": "6",
            "DVDRIP": "19",
        }
        if mapping_only:
            return type_id
        if reverse:
            return {value: key for key, value in type_id.items()}
        type_value = type if type is not None and type != "" else meta.type or ""
        return {"type_id": type_id.get(type_value, "0")}
