# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
from typing import Any

from src.meta import Meta
from src.trackers.common import Common
from src.trackers.UNIT3D import UNIT3D

Config = dict[str, Any]


class PeerGarden(UNIT3D):
    """
    PeerGarden is a UNIT3D-based tracker
    """

    tracker = "PEERGARDEN"
    display_name = "PeerGarden"
    base_url = "https://peergarden.org"
    banned_groups: tuple[str, ...] = ()
    id_url = f"{base_url}/api/torrents/"
    upload_url = f"{base_url}/api/torrents/upload"
    requests_url = f"{base_url}/api/requests/filter"
    search_url = f"{base_url}/api/torrents/filter"
    torrent_url = f"{base_url}/torrents/"
    supported_categories = (
        "TV",
        "MOVIE",
        "GAME",
        "BOOK",
        "MUSIC",
    )
    tracker_urls = ("peergarden",)
    allows_dupes = True
    exact_match_only = True

    def __init__(self, config: Config) -> None:
        """Initialize the PeerGarden tracker adapter."""
        super().__init__(config, tracker_name="PEERGARDEN")
        self.config = config
        self.common = Common(config)

    async def get_category_id(
        self,
        meta: Meta,
        category: str = "",
        reverse: bool = False,
        mapping_only: bool = False,
    ) -> dict[str, str]:
        """Resolve Upload Assistant categories to PeerGarden category IDs."""
        category_id = {
            "MOVIE": "1",
            "TV": "2",
            "GAME": "4",
            "MUSIC": "5",
            "BOOK": "6",
            "AUDIOBOOK": "7",
            "ANIME": "11",
        }
        if mapping_only:
            return category_id
        if reverse:
            return {
                "1": "MOVIE",
                "2": "TV",
                "4": "GAME",
                "5": "MUSIC",
                "6": "BOOK",
                "7": "AUDIOBOOK",
                "11": "ANIME",
            }
        resolved_category = category if category else meta.category
        if resolved_category == "BOOK":
            resolved_category = "AUDIOBOOK" if meta.audiobook else "BOOK"
        if meta.anime and resolved_category == "TV":
            resolved_category = "ANIME"

        return {"category_id": category_id.get(resolved_category, "0")}

    async def get_type_id(
        self,
        meta: Meta,
        type: str | None = None,
        reverse: bool = False,
        mapping_only: bool = False,
    ) -> dict[str, str]:
        """Resolve Upload Assistant release types to PeerGarden type IDs."""
        type_id = {
            "DISC": "1",
            "REMUX": "2",
            "ENCODE": "3",
            "WEBDL": "4",
            "WEBRIP": "5",
            "HDTV": "6",
            "FLAC": "7",
            "ALAC": "8",
            "AC3": "9",
            "AAC": "10",
            "MP3": "11",
            "MAC": "12",
            "WINDOWS": "13",
            "BLURAY": "14",
            "ANDET": "15",
            "OTHER": "15",
            "XVID": "16",
            "MP4": "17",
            "DVDRIP": "18",
            "UHD": "19",
            "M4A": "20",
            "WAV": "21",
            "WAW": "21",
            "WMA": "22",
            "3D": "23",
            "ANDROID": "24",
            "IOS": "25",
            "H.264": "26",
            "H264": "26",
            "X264": "27",
            "PDF": "28",
            "EPUB": "29",
            "BOXSET": "30",
            "CAM": "31",
            "TS": "31",
            "CONSOLE": "32",
            "4K": "33",
            "VR": "34",
            "PODCAST": "35",
            "X265": "36",
            "H265": "36",
            "HEVC": "36",
            "VC1": "37",
            "SUBS": "38",
        }
        if mapping_only:
            return type_id
        if reverse:
            return {
                "1": "DISC",
                "2": "REMUX",
                "3": "ENCODE",
                "4": "WEBDL",
                "5": "WEBRIP",
                "6": "HDTV",
                "7": "FLAC",
                "8": "ALAC",
                "9": "AC3",
                "10": "AAC",
                "11": "MP3",
                "12": "MAC",
                "13": "WINDOWS",
                "14": "BLURAY",
                "15": "OTHER",
                "16": "XVID",
                "17": "MP4",
                "18": "DVDRIP",
                "19": "UHD",
                "20": "M4A",
                "21": "WAV",
                "22": "WMA",
                "23": "3D",
                "24": "ANDROID",
                "25": "IOS",
                "26": "H264",
                "27": "X264",
                "28": "PDF",
                "29": "EPUB",
                "30": "BOXSET",
                "31": "CAM",
                "32": "CONSOLE",
                "33": "4K",
                "34": "VR",
                "35": "PODCAST",
                "36": "X265",
                "37": "VC1",
                "38": "SUBS",
            }

        def normalize(value: object) -> str:
            """Normalize tracker mapping inputs for lookup."""
            return str(value or "").upper().strip().lstrip(".")

        # An explicit type is used by search/edit callers and must not be
        # replaced by metadata inferred for a particular category.
        if type is not None and type.strip():
            return {"type_id": type_id.get(normalize(type), "15")}

        category = normalize(meta.category)
        resolved_type = normalize(meta.type)

        if category == "MUSIC":
            resolved_type = normalize(meta.format)
        elif category == "GAME":
            platform = normalize(meta.platform)
            if meta.console_game:
                resolved_type = "CONSOLE"
            elif "ANDROID" in platform:
                resolved_type = "ANDROID"
            elif "IOS" in platform or "IPHONE" in platform or "IPAD" in platform:
                resolved_type = "IOS"
            elif "MAC" in platform:
                resolved_type = "MAC"
            elif "WINDOWS" in platform or platform == "PC":
                resolved_type = "WINDOWS"
            else:
                resolved_type = "OTHER"
        elif category == "BOOK" and resolved_type not in type_id:
            resolved_type = "OTHER"

        return {"type_id": type_id.get(resolved_type, "15")}

    async def get_resolution_id(
        self,
        meta: Meta,
        resolution: str = "",
        reverse: bool = False,
        mapping_only: bool = False,
    ) -> dict[str, str]:
        """Resolve video resolutions to PeerGarden resolution IDs."""
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
            "8640p": "10",
            "1440p": "10",
            "OTHER": "10",
        }
        if mapping_only:
            return resolution_id
        if reverse:
            return {
                "1": "4320p",
                "2": "2160p",
                "3": "1080p",
                "4": "1080i",
                "5": "720p",
                "6": "576p",
                "7": "576i",
                "8": "480p",
                "9": "480i",
                "10": "OTHER",
                "11": "OTHER",
            }
        resolved_res = resolution if resolution else meta.resolution
        if isinstance(resolved_res, str):
            resolved_res = resolved_res.strip().lower()
        return {"resolution_id": resolution_id.get(resolved_res or "", "10")}

    async def get_additional_data(self, meta: Meta) -> dict[str, Any]:
        """Build PeerGarden-specific upload flags."""
        return {
            "mod_queue_opt_in": await self.get_flag(meta, "modq"),
        }

    async def get_data(self, meta: Meta) -> dict[str, Any]:
        """Build PeerGarden-specific upload payload, filtering out prohibited fields."""
        data = await super().get_data(meta)

        # Pop prohibited administrative flags
        for field in ("free", "featured", "doubleup", "sticky"):
            data.pop(field, None)

        return data
