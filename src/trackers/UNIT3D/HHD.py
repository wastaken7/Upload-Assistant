# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
from typing import Any, Optional

from src.console import console
from src.trackers.COMMON import COMMON
from src.trackers.UNIT3D import UNIT3D

Meta = dict[str, Any]
Config = dict[str, Any]


class HHD(UNIT3D):
    supported_categories = ("TV", "MOVIE", "BOOK", "GAME")

    def __init__(self, config: Config) -> None:
        super().__init__(config, tracker_name="HHD")
        self.config: Config = config
        self.common = COMMON(config)
        self.tracker = "HHD"
        self.base_url = "https://homiehelpdesk.net"
        self.id_url = f"{self.base_url}/api/torrents/"
        self.upload_url = f"{self.base_url}/api/torrents/upload"
        self.search_url = f"{self.base_url}/api/torrents/filter"
        self.requests_url = f"{self.base_url}/api/requests/filter"
        self.torrent_url = f"{self.base_url}/torrents/"
        self.banned_groups = [
            'aXXo', 'BONE', 'BRrip', 'CM8', 'CrEwSaDe', 'CTFOH', 'dAV1nci', 'd3g',
            'DNL', 'FaNGDiNG0', 'GalaxyTV', 'HD2DVD', 'HDTime', 'iHYTECH', 'ION10',
            'iPlanet', 'KiNGDOM', 'LAMA', 'MeGusta', 'mHD', 'mSD', 'NaNi', 'NhaNc3',
            'nHD', 'nikt0', 'nSD', 'OFT', 'PRODJi', 'RARBG', 'Rifftrax', 'SANTi',
            'SasukeducK', 'ShAaNiG', 'Sicario', 'STUTTERSHIT', 'TGALAXY', 'TORRENTGALAXY',
            'TSP', 'TSPxL', 'ViSION', 'VXT', 'WAF', 'WKS', 'x0r', 'YAWNiX', 'YIFY', 'YTS', 'PSA', ['EVO', 'WEB-DL only']
        ]  # fmt: off
        pass

    async def get_additional_checks(self, meta: Meta) -> bool:
        should_continue = True
        if meta["type"] == "DVDRIP":
            console.print("[bold red]DVDRIP uploads are not allowed on HHD.[/bold red]")
            return False

        return should_continue

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
        elif reverse:
            return {v: k for k, v in category_id.items()}

        resolved_category = category if category else meta.get("category", "")
        if resolved_category == "BOOK":
            if meta.get("audiobook", False):
                resolved_category = "AUDIOBOOK"
            elif meta.get("comic", False):
                resolved_category = "COMICS"
            elif meta.get("manga", False):
                resolved_category = "MANGA"
            elif meta.get("magazine", False):
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
        elif reverse:
            return {v: k for k, v in type_id.items()}

        resolved_type = type if type else meta.get("type", "")
        if isinstance(resolved_type, str):
            resolved_type = resolved_type.upper()

        if meta.get("category") == "BOOK" and resolved_type not in type_id:
            resolved_type = "OTHER"

        if meta["category"] == "GAME":
            resolved_type = "CONSOLE" if meta.get("console_game", False) else str(meta.get("platform", "")).upper()

        return {"type_id": type_id.get(resolved_type, "0")}

    async def get_resolution_id(
        self,
        meta: Meta,
        resolution: Optional[str] = None,
        reverse: bool = False,
        mapping_only: bool = False
    ) -> dict[str, str]:
        resolution_id = {
            '4320p': '1',
            '2160p': '2',
            '1440p': '3',
            '1080p': '3',
            '1080i': '4',
            '720p': '5',
            '576p': '6',
            '576i': '7',
            '480p': '8',
            '480i': '9',
            'Other': '10'
        }
        if mapping_only:
            return resolution_id
        elif reverse:
            return {v: k for k, v in resolution_id.items()}
        elif resolution is not None:
            return {'resolution_id': resolution_id.get(resolution, '10')}
        else:
            meta_resolution = meta.get('resolution', '')
            resolved_id = resolution_id.get(meta_resolution, '10')
            return {'resolution_id': resolved_id}
