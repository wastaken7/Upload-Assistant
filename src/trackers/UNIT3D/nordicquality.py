# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import re
import unicodedata
from pathlib import Path
from typing import Any, ClassVar

from src.meta import Meta
from src.trackers.UNIT3D import UNIT3D

Config = dict[str, Any]


class NordicQuality(UNIT3D):
    """NordicQuality UNIT3D tracker adapter."""

    tracker = "NORDICQUALITY"
    display_name = "NordicQuality"
    base_url = "https://nordicq.org"
    banned_groups: tuple[str, ...] = ()
    id_url = f"{base_url}/api/torrents/"
    upload_url = f"{base_url}/api/torrents/upload"
    search_url = f"{base_url}/api/torrents/filter"
    torrent_url = f"{base_url}/torrents/"
    supported_categories = ("TV", "MOVIE", "MUSIC", "BOOK", "GAME")
    tracker_urls = (base_url,)
    KNOWN_MEDIA_EXTENSIONS: ClassVar[frozenset[str]] = frozenset({".avi", ".mkv", ".mp4", ".ts"})
    NORDIC_SUBTITLE_LANGUAGES: ClassVar[list[str]] = [
        "da",
        "dan",
        "danish",
        "fi",
        "fin",
        "finnish",
        "ice",
        "icelandic",
        "is",
        "isl",
        "no",
        "nno",
        "nob",
        "nor",
        "norwegian",
        "sv",
        "swe",
        "swedish",
    ]

    def __init__(self, config: Config) -> None:
        super().__init__(config, tracker_name=self.tracker)

    async def get_additional_checks(self, meta: Meta) -> bool:
        if meta.category not in {"MOVIE", "TV"}:
            return True

        return await self.common.check_language_requirements(
            meta,
            self.tracker,
            languages_to_check=self.NORDIC_SUBTITLE_LANGUAGES,
            check_subtitle=True,
        )

    async def get_category_id(self, meta: Meta, category: str = "", reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        category_id = {
            "MOVIE": "1",
            "TV": "2",
            "MUSIC": "3",
            "GAME": "4",
            "BOOK": "7",
            "AUDIOBOOK": "8",
        }
        if mapping_only:
            return category_id
        if reverse:
            return {value: key for key, value in category_id.items()}

        resolved_category = category or meta.category
        if resolved_category == "BOOK" and meta.audiobook:
            resolved_category = "AUDIOBOOK"
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
            "MP3": "7",
            "FLAC": "8",
            "EPUB": "9",
            "PDF": "10",
            "WINDOWS": "11",
            "MAC": "12",
            "MACOS": "12",
            "ANDROID": "13",
            "IOS": "14",
            "OTHER": "15",
            "LINUX": "17",
            "CONSOLE": "18",
        }
        if mapping_only:
            return type_id
        if reverse:
            return {value: key for key, value in type_id.items()}
        if type:
            return {"type_id": type_id.get(type.upper().strip().lstrip("."), "0")}

        if meta.category in {"MUSIC", "BOOK"}:
            resolved_type = meta.format.upper().strip().lstrip(".")
        elif meta.category == "GAME":
            platform = meta.platform.lower()
            if meta.console_game:
                resolved_type = "CONSOLE"
            elif "windows" in platform or "pc" in platform:
                resolved_type = "WINDOWS"
            elif "linux" in platform:
                resolved_type = "LINUX"
            elif "mac" in platform:
                resolved_type = "MAC"
            elif "android" in platform:
                resolved_type = "ANDROID"
            elif "ios" in platform:
                resolved_type = "IOS"
            else:
                resolved_type = "OTHER"
        else:
            resolved_type = meta.type.upper().strip().lstrip(".") if meta.type else ""

        return {"type_id": type_id.get(resolved_type, "15" if meta.category in {"MUSIC", "BOOK", "GAME"} else "0")}

    @classmethod
    def _release_name_source(cls, meta: Meta) -> str:
        if meta.category not in {"MOVIE", "TV"}:
            return Path(meta.uuid or meta.name).stem

        source_name = ""
        if not meta.is_disc and len(meta.filelist) == 1:
            media_path = meta.filelist[0]
            if isinstance(media_path, str) and media_path.strip():
                source_name = Path(media_path).name

        if not source_name:
            source_name = Path(meta.uuid or meta.name).name

        extension = Path(source_name).suffix
        return source_name[: -len(extension)] if extension.casefold() in cls.KNOWN_MEDIA_EXTENSIONS else source_name

    async def get_name(self, meta: Meta) -> dict[str, str]:
        name = self._release_name_source(meta).replace(" ", ".")

        name = name.translate(
            str.maketrans(
                {
                    "\u00c6": "AE",
                    "\u00e6": "ae",
                    "\u00d0": "D",
                    "\u00f0": "d",
                    "\u00d8": "O",
                    "\u00f8": "o",
                    "\u00de": "TH",
                    "\u00fe": "th",
                    "\u00c5": "A",
                    "\u00e5": "a",
                    "\u0152": "OE",
                    "\u0153": "oe",
                    "\u00df": "ss",
                }
            )
        )

        name = name.replace("HDR10+", "HDR10P").replace("DD+", "DDP").replace("DTS:X", "DTS-X").replace("&", "and")
        name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
        name = re.sub(r"\(((?:19|20)\d{2})\)", r"\1", name)
        name = re.sub(r"[^A-Za-z0-9._()\-]+", ".", name)
        name = re.sub(r"\.{2,}", ".", name).strip(".")

        return {"name": name}
