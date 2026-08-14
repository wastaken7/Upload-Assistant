# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
from typing import Any

from src.meta import Meta
from src.trackers.common import Common
from src.trackers.UNIT3D import UNIT3D


class TorrentHR(UNIT3D):
    """TorrentHR (THR) is a Croatian UNIT3D tracker for movies and TV."""

    tracker = "TORRENTHR"
    display_name = "TorrentHR"
    base_url = "https://www.torrenthr.org"
    banned_groups: tuple[str, ...] = ()
    id_url = f"{base_url}/api/torrents/"
    upload_url = f"{base_url}/api/torrents/upload"
    search_url = f"{base_url}/api/torrents/filter"
    torrent_url = f"{base_url}/torrents/"
    supported_categories = ("TV", "MOVIE")
    tracker_urls = ("torrenthr.org",)
    allows_bloated_audio = True

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config, tracker_name=self.tracker)
        self.common = Common(config)

    async def get_category_id(self, meta: Meta, category: str | None = None, reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        category_id = {
            "MOVIE_SD": "4",
            "MOVIE_DVD": "14",
            "MOVIE_HD": "17",
            "ANIMATION": "18",
            "TV_SD": "7",
            "TV_HD": "34",
            "ANIME": "31",
            "MOVIE_BD": "40",
            "DOCUMENTARY": "12",
        }
        if mapping_only:
            return category_id
        if reverse:
            return {value: key for key, value in category_id.items()}

        resolved_category = category if category is not None and category != "" else meta.category
        genres = f"{meta.combined_genres} {meta.keywords}".lower()
        if "documentary" in genres:
            resolved_key = "DOCUMENTARY"
        elif meta.anime:
            resolved_key = "ANIME"
        elif "animation" in genres or "cartoon" in genres:
            resolved_key = "ANIMATION"
        elif resolved_category == "MOVIE":
            if meta.is_disc == "BDMV":
                resolved_key = "MOVIE_BD"
            elif meta.is_disc in {"DVD", "HDDVD"}:
                resolved_key = "MOVIE_DVD"
            else:
                resolved_key = "MOVIE_SD" if meta.sd else "MOVIE_HD"
        elif resolved_category == "TV":
            resolved_key = "TV_SD" if meta.sd else "TV_HD"
        else:
            return {"category_id": "0"}

        return {"category_id": category_id[resolved_key]}
