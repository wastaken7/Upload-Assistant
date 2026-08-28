# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import re
from pathlib import Path
from typing import Any, cast

import cli_ui

from src.console import logger
from src.meta import Meta
from src.trackers.common import Common
from src.trackers.UNIT3D import UNIT3D

Config = dict[str, Any]


class Seedpool(UNIT3D):
    """
    seedpool is a Private Torrent Tracker for 0-DAY MOVIES / TV / GENERAL
    """

    tracker = "SEEDPOOL"
    display_name = "Seedpool"
    base_url = "https://seedpool.org"
    banned_groups = ()
    id_url = f"{base_url}/api/torrents/"
    upload_url = f"{base_url}/api/torrents/upload"
    search_url = f"{base_url}/api/torrents/filter"
    torrent_url = f"{base_url}/torrents/"
    supported_categories = ("TV", "MOVIE", "BOOK", "GAME", "MUSIC")
    tracker_urls = ("https://seedpool.org",)
    allows_bloated_audio = True
    exact_match_only = False

    def __init__(self, config: Config) -> None:
        super().__init__(config, tracker_name="SEEDPOOL")
        self.config: Config = config
        self.common = Common(config)

    async def get_category_id(self, meta: Meta, category: str | None = None, reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        category_id = {
            "MOVIE": "1",
            "TV": "2",
            "GAME": "3",
            "MUSIC": "5",
            "EBOOK": "7",
            "BOOK": "7",
            "AUDIOBOOK": "9",
        }
        if mapping_only:
            return category_id
        if reverse:
            return {value: key for key, value in category_id.items()}

        category_name = str(category or meta.category).upper()
        if category_name == "BOOK" and meta.audiobook:
            return {"category_id": "9"}

        release_title = meta.name
        mal_id = meta.mal_id or 0

        # Custom SEEDPOOL category logic
        # Anime TV go in the Anime category
        if mal_id != 0 and category_name == "TV":
            return {"category_id": "6"}

        # Sports
        if category_name in {"MOVIE", "TV"} and self.contains_sports_patterns(release_title):
            return {"category_id": "8"}

        return {"category_id": category_id.get(category_name, "0")}

    # New function to check for sports releases in a title
    def contains_sports_patterns(self, release_title: str) -> bool:
        patterns = [
            r"EFL.*",
            r".*mlb.*",
            r".*formula1.*",
            r".*nascar.*",
            r".*nfl.*",
            r".*wrc.*",
            r".*wwe.*",
            r".*fifa.*",
            r".*boxing.*",
            r".*rally.*",
            r".*ufc.*",
            r".*ppv.*",
            r".*uefa.*",
            r".*nhl.*",
            r".*nba.*",
            r".*motogp.*",
            r".*moto2.*",
            r".*moto3.*",
            r".*gamenight.*",
            r".*darksport.*",
            r".*overtake.*",
        ]

        return any(re.search(pattern, release_title, re.IGNORECASE) for pattern in patterns)

    async def get_type_id(self, meta: Meta, media_type: str | None = None, reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        type_id = {
            "DISC": "1",
            "REMUX": "2",
            "ENCODE": "3",
            "DVDRIP": "3",
            "WEBDL": "4",
            "WEBRIP": "5",
            "HDTV": "6",
            "FLAC": "11",
            "FLAC PACK": "30",
            "FLAC_PACK": "30",
            "MP3": "13",
            "MP3 PACK": "31",
            "MP3_PACK": "31",
            "KARAOKE": "43",
            "MUSIC VIDEO": "55",
            "MUSIC VIDEOS": "55",
            "SAMPLES & SFX": "48",
            "SAMPLES_AND_SFX": "48",
            "BOOK": "20",
            "COMIC": "40",
            "DOCUMENT": "49",
            "MAGAZINE": "41",
            "NEWSPAPER": "42",
            "NES": "45",
            "NINTENDO SWITCH": "15",
            "SWITCH": "15",
            "PS1": "50",
            "PS2": "51",
            "PS3": "52",
            "PS4": "28",
            "WII": "44",
            "XBOX": "35",
            "XBOX 360": "53",
            "XBOX ONE": "54",
            "OTHER": "17",
        }
        if mapping_only:
            return type_id
        if reverse:
            return {value: key for key, value in type_id.items()}

        def normalise(value: object) -> str:
            return str(value or "").upper().strip().lstrip(".")

        if media_type:
            return {"type_id": type_id.get(normalise(media_type), "0")}

        if meta.category == "GAME":
            platform = normalise(meta.platform)
            if "XBOX 360" in platform:
                type_value = "XBOX 360"
            elif "XBOX ONE" in platform:
                type_value = "XBOX ONE"
            elif "XBOX" in platform:
                type_value = "XBOX"
            elif "PLAYSTATION 4" in platform or "PS4" in platform:
                type_value = "PS4"
            elif "PLAYSTATION 3" in platform or "PS3" in platform:
                type_value = "PS3"
            elif "PLAYSTATION 2" in platform or "PS2" in platform:
                type_value = "PS2"
            elif "PLAYSTATION" in platform or "PS1" in platform:
                type_value = "PS1"
            elif "SWITCH" in platform:
                type_value = "SWITCH"
            elif "WII" in platform:
                type_value = "WII"
            elif "NES" in platform:
                type_value = "NES"
            else:
                type_value = "OTHER"
        elif meta.category == "MUSIC":
            type_value = meta.format.upper()
        elif meta.category == "BOOK":
            if meta.audiobook:
                type_value = normalise(meta.format or meta.type)
            elif meta.comic or normalise(meta.type) in {"CBR", "CBZ"}:
                type_value = "COMIC"
            else:
                type_value = "BOOK"
        else:
            type_value = normalise(meta.type)

        return {"type_id": type_id.get(type_value, "17" if meta.category in {"BOOK", "GAME", "MUSIC"} else "0")}

    async def get_name(self, meta: Meta) -> dict[str, str]:
        known_extensions = {".mkv", ".mp4", ".avi", ".ts"}
        if meta.scene:
            scene_name = meta.scene_name
            name = scene_name if scene_name != "" else meta.basename_no_ext.replace(" ", ".")
        elif bool(meta.is_disc):
            name = meta.name.replace(" ", ".")
        else:
            base_name = meta.name.replace(" ", ".")
            uuid_name = meta.basename_no_ext.replace(" ", ".")
            name = base_name if meta.mal_id or 0 != 0 else uuid_name
        p = Path(name)
        base, ext = p.stem, p.suffix
        if ext.lower() in known_extensions:
            name = base.replace(" ", ".")

        return {"name": name}

    async def get_additional_checks(self, meta: Meta) -> bool:
        resolution = meta.resolution
        if meta.category in {"MOVIE", "TV"} and resolution not in ["8640p", "4320p", "2160p", "1440p", "1080p", "1080i"]:
            logger.info(f"{self.tracker}: [bold red]Only 1080 or higher resolutions allowed at {self.tracker}.[/bold red]")
            if not meta.unattended or (bool(meta.unattended) and meta.unattended_confirm):
                if cli_ui.ask_yes_no("Do you want to upload anyway?", default=False):
                    pass
                else:
                    return False
            else:
                return False

        disallowed_keywords = {"xxx", "erotic", "porn"}
        disallowed_genres = {"adult", "erotica"}
        keywords = [k.strip() for k in meta.keywords if k.strip()]
        combined_genres_val = meta.combined_genres
        if isinstance(combined_genres_val, str):
            combined_genres = [g.strip() for g in combined_genres_val.split(",") if g.strip()]
        else:
            combined_genres = [str(g) for g in cast(list[Any], combined_genres_val)]
        if any(keyword.lower() in disallowed_keywords for keyword in keywords) or any(genre.lower() in disallowed_genres for genre in combined_genres):
            if not meta.unattended or (bool(meta.unattended) and meta.unattended_confirm):
                logger.info(f"{self.tracker}: [bold red]Porn/xxx is not allowed at {self.tracker}.[/bold red]")
                if cli_ui.ask_yes_no("Do you want to upload anyway?", default=False):
                    pass
                else:
                    return False
            else:
                return False

        return True

    async def get_additional_data(self, meta: Meta) -> dict[str, Any]:
        return {
            "mod_queue_opt_in": await self.get_flag(meta, "modq"),
        }
