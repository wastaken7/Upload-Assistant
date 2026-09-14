# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import re
from typing import Any, cast

import langcodes
from rich.markup import escape

from src.console import logger
from src.languages import languages_manager
from src.meta import Meta
from src.release_name import NameContext, NameRule, NameSelector, TrackerNameProfile, template
from src.trackers.common import Common
from src.trackers.UNIT3D import UNIT3D

Config = dict[str, Any]


class LastDigitalUnderground(UNIT3D):
    """
    Last Digital Underground (LDU) is a Private Torrent Tracker for MOVIES / TV / GENERAL
    """

    tracker = "LASTDIGITALUNDERGROUND"
    name_profile = TrackerNameProfile(rules=(NameRule(NameSelector(), template("base_name", "audio_label", "subtitle_label")),))

    async def get_name_overrides(self, context: NameContext) -> dict[str, str]:
        meta = context.meta
        category_id = (await self.get_category_id(meta))["category_id"]
        non_english = str(meta.original_language) != "en"
        non_english_audio = False
        audio_label = ""
        subtitle_label = ""
        if isinstance(meta.audio_languages, list):
            for item in meta.audio_languages:
                language = str(item).strip()
                if not language:
                    continue
                try:
                    audio_label = f"[{langcodes.find(language).to_alpha3().upper()}]"
                    non_english_audio = not await languages_manager.has_english_language(language)
                    break
                except (LookupError, AttributeError, ValueError) as error:
                    logger.info(f"{self.tracker}: [bold red]Error extracting audio language: {escape(str(error))}[/bold red]")
        if meta.no_subs:
            subtitle_label = "[NoSubs]"
        elif isinstance(meta.subtitle_languages, list):
            for item in meta.subtitle_languages:
                language = str(item).strip()
                if not language:
                    continue
                try:
                    subtitle_label = f"[Subs {langcodes.find(language).to_alpha3().upper()}]"
                    break
                except (LookupError, AttributeError, ValueError) as error:
                    logger.info(f"{self.tracker}: [bold red]Error extracting subtitle language: {escape(str(error))}[/bold red]")
        if category_id == "18":
            audio_label = ""
        elif not (non_english or non_english_audio):
            audio_label = ""
            subtitle_label = ""
        return {"audio_label": audio_label, "subtitle_label": subtitle_label}
    display_name = "LastDigitalUnderground"
    allows_bloated_audio = True
    base_url = "https://theldu.to"
    banned_groups = ()
    id_url = f"{base_url}/api/torrents/"
    upload_url = f"{base_url}/api/torrents/upload"
    search_url = f"{base_url}/api/torrents/filter"
    torrent_url = f"{base_url}/torrents/"
    supported_categories = ("TV", "MOVIE", "BOOK")
    tracker_urls = ("theldu.to",)

    def __init__(self, config: Config) -> None:
        super().__init__(config, tracker_name="LASTDIGITALUNDERGROUND")
        self.config: Config = config
        self.common = Common(config)

    async def get_category_id(self, meta: Meta, category: str | None = None, reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        genres = f"{', '.join(meta.keywords)} {meta.combined_genres}"
        adult_keywords = ["xxx", "erotic", "porn", "adult", "orgy"]
        sound_mixes_value = meta.imdb_info.get("sound_mixes", [])
        sound_mixes = cast(list[Any], sound_mixes_value) if isinstance(sound_mixes_value, list) else []

        cat_map = {
            "MOVIE": "1",
            "TV": "2",
            "Anime": "8",
            "FANRES": "12",
            "MUSIC": "3",
            "EBOOK": "7",
            "AUDIOBOOK": "34",
        }
        if mapping_only:
            return cat_map
        if reverse:
            return {v: k for k, v in cat_map.items()}

        resolved_category = category if category is not None else meta.category
        if resolved_category == "BOOK":
            resolved_category = "AUDIOBOOK" if meta.audiobook else "EBOOK"

        category_id = cat_map.get(resolved_category, "0")

        if "hentai" in genres.lower():
            category_id = "10"
        elif any(re.search(rf"(^|,\s*){re.escape(keyword)}(\s*,|$)", genres, re.IGNORECASE) for keyword in adult_keywords):
            category_id = "45" if not await languages_manager.has_english_language(meta.subtitle_languages or []) else "6"

        if meta.category == "MOVIE":
            if meta.three_d or "3D" in meta.edition:
                category_id = "21"
            elif any(x in meta.edition.lower() for x in ["fanedit", "fanres"]):
                category_id = "12"
            elif meta.anime or meta.mal_id != 0:
                category_id = "8"
            elif any("silent film" in mix.lower() for mix in sound_mixes if isinstance(mix, str)) or meta.silent:
                category_id = "18"
            elif "musical" in genres.lower():
                category_id = "25"
            elif any(x in genres.lower() for x in ["holiday", "easter", "christmas", "halloween", "thanksgiving"]):
                category_id = "24"
            elif "documentary" in genres.lower():
                category_id = "17"
            elif any(x in genres.lower() for x in ["stand-up", "standup"]):
                category_id = "20"
            elif "short film" in genres.lower() or int(meta.imdb_info.get("runtime", 0) or 0) < 5:
                category_id = "19"
            elif not await languages_manager.has_english_language(meta.audio_languages or []) and not await languages_manager.has_english_language(
                meta.subtitle_languages or []
            ):
                category_id = "22"
            elif "dubbed" in meta.audio.lower():
                category_id = "27"
            else:
                category_id = "1"
        elif meta.category == "TV":
            if meta.anime or meta.mal_id != 0:
                category_id = "9"
            elif "documentary" in genres.lower():
                category_id = "40"
            elif not await languages_manager.has_english_language(meta.audio_languages or []) and not await languages_manager.has_english_language(
                meta.subtitle_languages or []
            ):
                category_id = "29"
            elif meta.tv_pack:
                category_id = "2"
            elif "dubbed" in meta.audio.lower():
                category_id = "31"
            else:
                category_id = "41"

        return {"category_id": category_id}

    async def get_type_id(self, meta: Meta, type: str | None = None, reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
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
            "OTHER": "14",
            "EPUB": "17",
            "CBR": "18",
            "CBZ": "19",
            "CB7": "20",
            "CBT": "21",
            "CBA": "22",
            "PDP": "23",
            "AZW": "24",
            "AZW3": "25",
            "PDF": "26",
        }
        if mapping_only:
            return type_id
        if reverse:
            return {v: k for k, v in type_id.items()}

        resolved_type = type if type is not None else meta.type
        if isinstance(resolved_type, str):
            resolved_type = resolved_type.upper().lstrip(".")

        val = "14" if meta.category == "BOOK" and resolved_type not in type_id else type_id.get(resolved_type or "", "0")

        if any(x in meta.edition.lower() for x in ["fanedit", "fanres"]):
            val = "16"

        return {"type_id": val}
