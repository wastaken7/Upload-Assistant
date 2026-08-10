# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import re
from typing import Any

from src.console import logger
from src.meta import Meta
from src.music.sources import DiscogsEnricher
from src.trackers.common import Common
from src.trackers.UNIT3D import UNIT3D

Config = dict[str, Any]


class HomieHelpDesk(UNIT3D):
    """
    HHD is a Private Torrent Tracker for MOVIES / TV / GAMES
    """

    tracker = "HOMIEHELPDESK"
    display_name = "HomieHelpDesk"
    allows_bloated_audio = True
    base_url = "https://homiehelpdesk.net"
    banned_groups = (
        "aXXo",
        "BONE",
        "BRrip",
        "CM8",
        "CrEwSaDe",
        "CTFOH",
        "d3g",
        "dAV1nci",
        "DNL",
        "EVO",
        "FaNGDiNG0",
        "GalaxyTV",
        "HD2DVD",
        "HDTime",
        "iHYTECH",
        "ION10",
        "iPlanet",
        "KiNGDOM",
        "LAMA",
        "MeGusta",
        "mHD",
        "mSD",
        "NaNi",
        "NhaNc3",
        "nHD",
        "nikt0",
        "nSD",
        "OFT",
        "PRODJi",
        "PSA",
        "RARBG",
        "Rifftrax",
        "SANTi",
        "SasukeducK",
        "ShAaNiG",
        "Sicario",
        "STUTTERSHIT",
        "TGALAXY",
        "TORRENTGALAXY",
        "TSP",
        "TSPxL",
        "ViSION",
        "VXT",
        "WAF",
        "WKS",
        "x0r",
        "YAWNiX",
        "YIFY",
        "YTS",
    )
    id_url = f"{base_url}/api/torrents/"
    upload_url = f"{base_url}/api/torrents/upload"
    search_url = f"{base_url}/api/torrents/filter"
    requests_url = f"{base_url}/api/requests/filter"
    torrent_url = f"{base_url}/torrents/"
    supported_categories = ("TV", "MOVIE", "BOOK", "GAME", "MUSIC")
    tracker_urls = ("https://homiehelpdesk.net",)

    def __init__(self, config: Config) -> None:
        super().__init__(config, tracker_name="HOMIEHELPDESK")
        self.config: Config = config
        self.common = Common(config)

    async def get_additional_checks(self, meta: Meta) -> bool:
        if meta.type == "DVDRIP":
            logger.info(f"{self.tracker}: [bold red]DVDRIP uploads are not allowed on {self.tracker}.[/bold red]")
            return False

        if meta.category == "MUSIC" and not self._music_upload_data(meta):
            logger.info(f"{self.tracker}: [bold red]Music uploads require a valid MusicBrainz or Discogs ID.[/bold red]")
            return False

        return True

    @staticmethod
    def _music_upload_data(meta: Meta) -> dict[str, str]:
        """Build HomieHelpDesk's music-specific external-ID payload."""
        release = meta.music_release if isinstance(meta.music_release, dict) else {}
        external_ids = release.get("external_ids", {})
        external_ids = external_ids if isinstance(external_ids, dict) else {}

        musicbrainz = str(external_ids.get("musicbrainz_release") or external_ids.get("musicbrainz_release_group") or "").strip()
        if re.fullmatch(r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}", musicbrainz, re.IGNORECASE):
            return {
                "music_exists_on_musicbrainz": "1",
                "musicbrainz": musicbrainz,
            }

        discogs = ""
        if meta.music_discogs_enabled:
            discogs = str(
                external_ids.get("discogs_release_url")
                or external_ids.get("discogs_release")
                or meta.music_discogs_release_id
                or meta.music_discogs_id
                or external_ids.get("discogs_master_url")
                or external_ids.get("discogs_master")
                or meta.music_discogs_master_id
                or ""
            ).strip()
        if DiscogsEnricher.parse_reference(discogs):
            return {
                "music_exists_on_discogs": "1",
                "discogs": discogs,
            }

        return {}

    async def get_additional_data(self, meta: Meta) -> dict[str, str]:
        if meta.category == "MUSIC":
            return self._music_upload_data(meta)
        return {}

    async def get_category_id(self, meta: Meta, category: str = "", reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        category_id = {
            "MOVIE": "1",
            "TV": "2",
            "ANIME": "3",
            "MUSIC": "4",
            "GAME": "5",
            "APPS": "6",
            "BOOKS": "7",
            "AUDIOBOOK": "8",
            "MANGA": "9",
            "ADULT": "10",
            "COMICS": "11",
            "MAGAZINE": "12",
        }
        if mapping_only:
            return category_id
        if reverse:
            return {v: k for k, v in category_id.items()}

        resolved_category = category if category else meta.category
        if resolved_category == "BOOK":
            if meta.audiobook:
                resolved_category = "AUDIOBOOK"
            elif meta.comic:
                resolved_category = "COMICS"
            elif meta.manga:
                resolved_category = "MANGA"
            elif meta.magazine:
                resolved_category = "MAGAZINE"
            else:
                resolved_category = "BOOKS"

        return {"category_id": category_id.get(resolved_category, "0")}

    async def get_type_id(self, meta: Meta, type: str = "", reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        type_id = {
            "DISC": "1",
            "REMUX": "2",
            "ENCODE": "3",
            "DVDRIP": "3",
            "WEBDL": "4",
            "WEBRIP": "5",
            "HDTV": "6",
            "FLAC": "7",
            "AAC": "8",
            "ALAC": "9",
            "M4A": "10",
            "M4B": "11",
            "MP4": "12",
            "MP3": "13",
            "ISO": "14",
            "APK": "15",
            "RAR": "16",
            "7Z": "17",
            "ROM": "18",
            "PDF": "19",
            "EPUB": "20",
            "MOBI": "21",
            "CBZ": "22",
            "CBR": "22",
            "OTHER": "23",
            "PC": "25",
            "WINDOWS": "25",
            "MAC": "26",
            "LINUX": "27",
            "CONSOLE": "28",
        }
        if mapping_only:
            return type_id
        if reverse:
            return {v: k for k, v in type_id.items()}

        resolved_type = type if type else meta.type
        if isinstance(resolved_type, str):
            resolved_type = resolved_type.upper()

        if meta.category == "BOOK" and resolved_type not in type_id:
            resolved_type = "OTHER"

        if meta.category == "GAME":
            resolved_type = "CONSOLE" if meta.console_game else meta.platform.upper()
        elif meta.category == "MUSIC":
            release = meta.music_release if isinstance(meta.music_release, dict) else {}
            fields = release.get("fields", {})
            music_format = fields.get("format", {}) if isinstance(fields, dict) else {}
            resolved_type = music_format.get("value", meta.format) if isinstance(music_format, dict) else meta.format
            resolved_type = str(resolved_type or "").upper()

        return {"type_id": type_id.get(str(resolved_type), "0")}

    async def get_resolution_id(self, meta: Meta, resolution: str | None = None, reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        resolution_id = {"4320p": "1", "2160p": "2", "1440p": "3", "1080p": "3", "1080i": "4", "720p": "5", "576p": "6", "576i": "7", "480p": "8", "480i": "9", "Other": "10"}
        if mapping_only:
            return resolution_id
        if reverse:
            return {v: k for k, v in resolution_id.items()}
        if resolution is not None:
            return {"resolution_id": resolution_id.get(resolution, "10")}
        meta_resolution = meta.resolution
        resolved_id = resolution_id.get(meta_resolution, "10")
        return {"resolution_id": resolved_id}
