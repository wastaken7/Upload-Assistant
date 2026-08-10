from typing import Any

from src.meta import Meta
from src.trackers.UNIT3D import UNIT3D


class DesiTorrents(UNIT3D):
    """
    DesiTorrents is an INDIAN Private Torrent Tracker for MOVIES / TV
    """

    tracker = "DESITORRENTS"
    display_name = "DesiTorrents"
    allows_bloated_audio = True
    base_url = "https://torrent.desi"
    banned_groups = ("DusIcTv", "PDHM", "Ranvijay", "BWT", "DDH", "Telly", "YTS", "RARBG", "BonsaiHD", "GalaxyRG", "-=!DrSTAR!=-")
    id_url = f"{base_url}/api/v1/torrents/"
    upload_url = f"{base_url}/api/v1/torrents/upload"
    search_url = f"{base_url}/api/v1/torrents/filter"
    supported_categories = ("TV", "MOVIE")

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config, tracker_name="DESITORRENTS")

        # Banned Groups

    async def get_category_id(
        self,
        meta: Meta,
        category: str = "",
        reverse: bool = False,
        mapping_only: bool = False,
    ) -> dict[str, str]:
        """
        Returns the category ID for the release.
        """

        # DesiTorrents Category Map: Movie=1, TV=2, Music=3, Game=4
        category_id = {"MOVIE": "1", "TV": "2", "MUSIC": "3", "GAME": "4"}

        if mapping_only:
            return category_id
        if reverse:
            return {v: k for k, v in category_id.items()}
        if category:
            return {"category_id": category_id.get(category, "0")}
        meta_category = meta.category
        resolved_id = category_id.get(meta_category, "0")
        return {"category_id": resolved_id}

    async def get_type_id(
        self,
        meta: Meta,
        type: str = "",
        reverse: bool = False,
        mapping_only: bool = False,
    ) -> dict[str, str]:
        """
        Returns the type ID (source) for the release.
        """

        # Standard Mapping for reverse lookups
        type_id_map = {
            "DISC": "3",  # Defaulting to BD50
            "REMUX": "5",  # Defaulting to BD Remux
            "ENCODE": "12",  # Defaulting to BD Encode
            "WEBDL": "11",
            "WEBRIP": "12",  # Changed to Encode per tracker rules
            "HDTV": "13",
            "DVD": "8",
        }

        if mapping_only:
            return type_id_map
        if reverse:
            return {v: k for k, v in type_id_map.items()}
        if type:
            return {"type_id": type_id_map.get(type, "0")}
        # Dynamic Logic for DesiTorrents specific IDs (UHD vs 1080p)
        meta_type = meta.type
        is_uhd = meta.uhd

        resolved_id = "0"

        if meta_type == "DISC":
            resolved_id = "3"  # BD50
            if meta.disctype == "BD25":
                resolved_id = "4"
        elif meta_type == "REMUX":
            resolved_id = "2" if is_uhd else "5"
        elif meta_type == "ENCODE":
            resolved_id = "1" if is_uhd else "12"
        elif meta_type == "WEBDL":
            resolved_id = "11"
        elif meta_type == "WEBRIP":
            resolved_id = "12"  # Mapped to Encode
        elif meta_type == "DVD":
            resolved_id = "8"
        elif meta_type == "HDTV":
            resolved_id = "13"

        return {"type_id": resolved_id}

    async def get_resolution_id(
        self,
        meta: Meta,
        resolution: str = "",
        reverse: bool = False,
        mapping_only: bool = False,
    ) -> dict[str, str]:
        """
        Returns the resolution ID for the release.
        """

        # DesiTorrents Specific Resolutions
        resolution_id = {
            "4320p": "9",  # 8k
            "2160p": "8",
            "1080p": "11",
            "1080i": "7",
            "720p": "6",
            "720i": "5",
            "576p": "4",
            "576i": "3",
            "540p": "12",
            "480p": "2",
            "480i": "1",
        }

        if mapping_only:
            return resolution_id
        if reverse:
            return {v: k for k, v in resolution_id.items()}
        if resolution:
            return {"resolution_id": resolution_id.get(resolution, "10")}
        meta_resolution = meta.resolution
        resolved_id = resolution_id.get(meta_resolution, "10")  # 10 is 'Other'
        return {"resolution_id": resolved_id}
