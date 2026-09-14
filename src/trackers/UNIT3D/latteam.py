# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import re
from typing import Any, cast

from src.meta import Meta
from src.release_name import NameContext, NameRule, NameSelector, TrackerNameProfile, template
from src.trackers.common import Common
from src.trackers.UNIT3D import UNIT3D

Config = dict[str, Any]


def latteam_video_name(name: str, context: NameContext) -> str:
    meta = context.meta
    if meta.category == "BOOK":
        return re.sub(r"\s{2,}", " ", name).strip()
    aka = meta.aka
    name = name.replace("Dual-Audio", "").replace("Dubbed", "").replace(aka, "")
    if meta.type != "DISC":
        if meta.original_language == "es" and aka:
            name = name.replace(meta.title, aka.replace("AKA", "")).strip()
        latin_codes = {
            "es-419",
            "es-ar",
            "es-bo",
            "es-cl",
            "es-co",
            "es-cr",
            "es-do",
            "es-ec",
            "es-gt",
            "es-hn",
            "es-mx",
            "es-ni",
            "es-pa",
            "es-pe",
            "es-pr",
            "es-py",
            "es-sv",
            "es-uy",
            "es-ve",
        }
        latin = castilian = False
        found = 0
        for track in meta.mediainfo.get("media", {}).get("track", [])[2:]:
            if not isinstance(track, dict) or track.get("@type") != "Audio":
                continue
            language = str(track.get("Language", "")).lower()
            title = str(track.get("Title", "")).lower()
            if "commentary" in title:
                continue
            if language in latin_codes or (language == "es" and any(word in title for word in ("latino", "latin america"))):
                latin = True
                found += 1
            elif (language == "es" and "castellano" in title) or language in ("es", "es-es"):
                castilian = True
                found += 1
        if found and castilian and not latin:
            name = name.replace(meta.tag, f" [CAST]{meta.tag}") if meta.tag else f"{name} [CAST]"
        elif not found:
            name = name.replace(meta.tag, f" [SUBS]{meta.tag}") if meta.tag else f"{name} [SUBS]"
    return re.sub(r"\s{2,}", " ", name)


class LatTeam(UNIT3D):
    """
    Lat-Team is a SPANISH Private Torrent Tracker for MOVIES / TV
    """

    tracker = "LATTEAM"
    name_profile = TrackerNameProfile(
        rules=(
            NameRule(NameSelector(category="BOOK"), template("author", "author_dash", "title", "book_extras", "book_format")),
            NameRule(NameSelector(), template("base_name")),
        ),
        transforms=(latteam_video_name,),
    )

    async def get_name_overrides(self, context: NameContext) -> dict[str, str]:
        meta = context.meta
        if meta.category != "BOOK":
            return {}
        extras = []
        volume = str(meta.manual_season or meta.season or "").strip()
        issue = str(meta.manual_episode or meta.episode or "").strip()
        if volume:
            extras.append(f"Vol {volume}")
        if issue:
            extras.append(f"No {issue}")
        edition = str(meta.manual_edition or meta.edition or "").strip()
        if edition:
            extras.append(edition if any(word in edition.lower() for word in ("edición", "edicion", "edition", "ed.", "ed")) else f"{edition} Edition")
        if meta.audiobook:
            language = meta.book_language.lower()
            narration = (
                "Castellano"
                if any(word in language for word in ("spain", "castilian", "castellano"))
                else "Latino"
                if any(word in language for word in ("latin", "latino"))
                else "Portugués"
                if any(word in language for word in ("portuguese", "português", "portugues"))
                else meta.book_language.title()
                if language
                else ""
            )
            if narration:
                extras.append(f"Narración en {narration}")
        author = meta.author.strip()
        return {
            "author": author,
            "author_dash": "-" if author else "",
            "title": meta.title.strip(),
            "book_extras": " ".join(f"({item})" for item in extras),
            "book_format": str(meta.type).strip().upper(),
        }

    display_name = "Lat-Team"
    base_url = "https://lat-team.com"
    banned_groups = ("EVO",)
    id_url = f"{base_url}/api/torrents/"
    upload_url = f"{base_url}/api/torrents/upload"
    search_url = f"{base_url}/api/torrents/filter"
    torrent_url = f"{base_url}/torrents/"
    supported_categories = ("TV", "MOVIE", "BOOK")
    tracker_urls = ("https://lat-team.com",)
    allowed_bloated_audio_languages = ("es",)

    def __init__(self, config: Config) -> None:
        super().__init__(config, tracker_name="LATTEAM")
        self.config: Config = config
        self.common = Common(config)

    async def get_category_id(self, meta: Meta, category: str | None = None, reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        cat_map = {
            "MOVIE": "1",
            "TV": "2",
            "EBOOK": "18",
            "AUDIOBOOK": "11",
            "MAGAZINE": "29",
            "COMIC": "30",
        }
        if mapping_only:
            return cat_map
        if reverse:
            return {v: k for k, v in cat_map.items()}

        resolved_category = category if category is not None and category != "" else meta.category
        if resolved_category == "BOOK":
            if meta.audiobook:
                resolved_category = "AUDIOBOOK"
            elif meta.comic or meta.manga:
                resolved_category = "COMIC"
            elif meta.magazine:
                resolved_category = "MAGAZINE"
            else:
                resolved_category = "EBOOK"

        category_id = cat_map.get(resolved_category, "0")

        keywords = [k.lower() for k in meta.keywords]
        overview = meta.overview.lower()
        genres = [g.lower() for g in meta.genres]
        soap_keywords = ["telenovela", "novela", "soap", "culebrón", "culebron"]
        origin_countries_value = meta.origin_country
        origin_countries = cast(list[str], origin_countries_value) if isinstance(origin_countries_value, list) else []

        if resolved_category == "TV":
            # Anime
            if meta.anime:
                category_id = "5"
            # Telenovela / Soap
            elif any(kw in keywords for kw in soap_keywords) or any(kw in overview for kw in soap_keywords):
                category_id = "8"
            # Turkish & Asian
            elif "drama" in genres and any(
                c
                in [
                    "AE",
                    "AF",
                    "AM",
                    "AZ",
                    "BD",
                    "BH",
                    "BN",
                    "BT",
                    "CN",
                    "CY",
                    "GE",
                    "HK",
                    "ID",
                    "IL",
                    "IN",
                    "IQ",
                    "IR",
                    "JO",
                    "JP",
                    "KG",
                    "KH",
                    "KP",
                    "KR",
                    "KW",
                    "KZ",
                    "LA",
                    "LB",
                    "LK",
                    "MM",
                    "MN",
                    "MO",
                    "MV",
                    "MY",
                    "NP",
                    "OM",
                    "PH",
                    "PK",
                    "PS",
                    "QA",
                    "SA",
                    "SG",
                    "SY",
                    "TH",
                    "TJ",
                    "TL",
                    "TM",
                    "TR",
                    "TW",
                    "UZ",
                    "VN",
                    "YE",
                ]
                for c in origin_countries
            ):
                category_id = "20"

        return {"category_id": category_id}

    async def get_type_id(self, meta: Meta, type: str | None = None, reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        type_id = {
            "DISC": "1",
            "REMUX": "2",
            "ENCODE": "3",
            "WEBDL": "4",
            "WEBRIP": "5",
            "HDTV": "6",
            "DVDRIP": "3",
            "FLAC": "7",
            "ALAC": "8",
            "AC3": "9",
            "AAC": "10",
            "MP3": "11",
            "M4A": "18",
            "M4B": "17",
            "EPUB": "14",
            "PDF": "23",
            "CBZ": "25",
            "CBR": "25",
            "AZW3": "26",
            "MOBI": "26",
            "KFX": "26",
            "OTHER": "21",
        }
        if mapping_only:
            return type_id
        if reverse:
            return {v: k for k, v in type_id.items()}

        resolved_type = type if type is not None and type != "" else meta.type
        if isinstance(resolved_type, str):
            resolved_type = resolved_type.upper().strip().lstrip(".")
            if resolved_type in ("CBZ", "CBR"):
                resolved_type = "CBZ"
            elif resolved_type in ("AZW3", "MOBI", "KFX"):
                resolved_type = "AZW3"

        val = type_id.get(resolved_type or "", "0")
        if meta.category == "BOOK" and val == "0":
            val = "21"

        return {"type_id": val}

    async def get_additional_checks(self, meta: Meta) -> bool:
        if meta.category == "BOOK":
            return True
        spanish_languages = ["spanish", "spanish (latin america)"]
        return await self.common.check_language_requirements(meta, self.tracker, languages_to_check=spanish_languages, check_audio=True, check_subtitle=True)

    async def get_additional_data(self, meta: Meta) -> dict[str, Any]:
        data: dict[str, Any] = {
            "mod_queue_opt_in": await self.get_flag(meta, "modq"),
        }

        return data
