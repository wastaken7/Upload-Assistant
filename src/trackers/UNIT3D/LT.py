# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import re
from typing import Any, Optional, cast

from src.meta import Meta
from src.trackers.COMMON import COMMON
from src.trackers.UNIT3D import UNIT3D

Config = dict[str, Any]


class LT(UNIT3D):
    supported_categories = ("TV", "MOVIE", "BOOK")

    def __init__(self, config: Config) -> None:
        super().__init__(config, tracker_name='LT')
        self.config: Config = config
        self.common = COMMON(config)
        self.tracker = 'LT'
        self.base_url = 'https://lat-team.com'
        self.id_url = f'{self.base_url}/api/torrents/'
        self.upload_url = f'{self.base_url}/api/torrents/upload'
        self.search_url = f'{self.base_url}/api/torrents/filter'
        self.torrent_url = f'{self.base_url}/torrents/'
        self.banned_groups = ["EVO"]

    async def get_category_id(
        self,
        meta: Meta,
        category: Optional[str] = None,
        reverse: bool = False,
        mapping_only: bool = False
    ) -> dict[str, str]:
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
        elif reverse:
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

        keywords = str(meta.keywords).lower()
        overview = str(meta.overview).lower()
        genres = str(meta.genres).lower()
        soap_keywords = ['telenovela', 'novela', 'soap', 'culebrón', 'culebron']
        origin_countries_value = meta.origin_country
        origin_countries = cast(list[str], origin_countries_value) if isinstance(origin_countries_value, list) else []

        if resolved_category == "TV":
            # Anime
            if meta.anime:
                category_id = '5'
            # Telenovela / Soap
            elif any(kw in keywords for kw in soap_keywords) or any(kw in overview for kw in soap_keywords):
                category_id = '8'
            # Turkish & Asian
            elif 'drama' in genres and any(c in [
                'AE', 'AF', 'AM', 'AZ', 'BD', 'BH', 'BN', 'BT', 'CN', 'CY', 'GE', 'HK', 'ID', 'IL', 'IN',
                'IQ', 'IR', 'JO', 'JP', 'KG', 'KH', 'KP', 'KR', 'KW', 'KZ', 'LA', 'LB', 'LK', 'MM', 'MN',
                'MO', 'MV', 'MY', 'NP', 'OM', 'PH', 'PK', 'PS', 'QA', 'SA', 'SG', 'SY', 'TH', 'TJ', 'TL',
                'TM', 'TR', 'TW', 'UZ', 'VN', 'YE'
            ] for c in origin_countries):
                category_id = '20'

        return {'category_id': category_id}

    async def get_type_id(self, meta: Meta, type: Optional[str] = None, reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
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
        elif reverse:
            return {v: k for k, v in type_id.items()}

        resolved_type = type if type is not None and type != "" else meta.type
        if isinstance(resolved_type, str):
            resolved_type = resolved_type.upper().strip().lstrip(".")
            if resolved_type in ("CBZ", "CBR"):
                resolved_type = "CBZ"
            elif resolved_type in ("AZW3", "MOBI", "KFX"):
                resolved_type = "AZW3"

        val = type_id.get(resolved_type, "0")
        if meta.category == "BOOK" and val == "0":
            val = "21"

        return {"type_id": val}

    async def get_name(self, meta: Meta) -> dict[str, str]:
        if meta.category == "BOOK":
            author = str(meta.author).strip()
            title = str(meta.title).strip()
            fmt = str(meta.type).strip().upper()

            extra_info = []

            # If it's comic/manga/magazine/newspaper, we can add volume, issue/number info if available
            volume = str(meta.manual_season or meta.season or "").strip()
            issue = str(meta.manual_episode or meta.episode or "").strip()

            if volume:
                extra_info.append(f"Vol {volume}")
            if issue:
                extra_info.append(f"No {issue}")

            edition = str(meta.manual_edition or meta.edition or "").strip()
            if edition:
                if not any(x in edition.lower() for x in ["edición", "edicion", "edition", "ed.", "ed"]):
                    extra_info.append(f"{edition} Edition")
                else:
                    extra_info.append(edition)

            if meta.audiobook:
                book_lang = str(meta.book_language).lower()
                if "spain" in book_lang or "castilian" in book_lang or "castellano" in book_lang:
                    extra_info.append("Narración en Castellano")
                elif "latin" in book_lang or "latino" in book_lang:
                    extra_info.append("Narración en Latino")
                elif "portuguese" in book_lang or "português" in book_lang or "portugues" in book_lang:
                    extra_info.append("Narración en Portugués")
                elif book_lang:
                    lang_title = str(meta.book_language).title()
                    extra_info.append(f"Narración en {lang_title}")

            extra_str = ""
            if extra_info:
                extra_str = " " + " ".join(f"({info})" for info in extra_info)

            lt_name = f"{author} - {title}{extra_str} {fmt}" if author else f"{title}{extra_str} {fmt}"

            return {"name": re.sub(r"\s{2,}", " ", lt_name).strip()}

        aka_value = str(meta.aka)
        lt_name = str(meta.name).replace("Dual-Audio", "").replace("Dubbed", "").replace(aka_value, "")

        if meta.type != "DISC":  # DISC don't have mediainfo
            # Check if original language is "es" if true replace title for AKA if available
            title_value = str(meta.title)
            if meta.original_language == "es" and aka_value:
                lt_name = lt_name.replace(title_value, aka_value.replace('AKA', '')).strip()
            # Check if audio Spanish exists

            audio_latino_check = {
                "es-419", "es-mx", "es-ar", "es-cl", "es-ve",
                "es-bo",  "es-co", "es-cr", "es-do", "es-ec",
                "es-sv",  "es-gt", "es-hn", "es-ni", "es-pa",
                "es-py",  "es-pe", "es-pr", "es-uy"}

            audio_castilian_check = ["es", "es-es"]
            # Use keywords instead of massive exact-match lists
            # "latino" matches: "latino", "latinoamérica", "latinoamericano", etc.
            latino_keywords = ["latino", "latin america"]
            # "castellano" matches any title explicitly labeled as such.
            castilian_keywords = ["castellano"]

            audios: list[dict[str, Any]] = []
            has_latino = False
            has_castilian = False

            tracks_value = meta.mediainfo.get("media", {}).get("track", [])
            tracks_list = cast(list[Any], tracks_value) if isinstance(tracks_value, list) else []
            for audio in tracks_list[2:]:
                if not isinstance(audio, dict):
                    continue
                audio_map = cast(dict[str, Any], audio)
                if audio_map.get("@type") != "Audio":
                    continue
                lang = str(audio_map.get("Language", "")).lower()
                title = str(audio_map.get("Title", "")).lower()

                if "commentary" in title:
                    continue

                # Check if title contains keywords
                is_latino_title = any(kw in title for kw in latino_keywords)
                is_castilian_title = any(kw in title for kw in castilian_keywords)

                # 1. Check strict Latino language codes or Edge Case: Language is 'es' but Title contains Latino keywords
                if lang in audio_latino_check or (lang == 'es' and is_latino_title):
                    has_latino = True
                    audios.append(audio_map)

                # 2. Edge Case: Language is 'es' and Title contains Castilian keywords or Fallback: Check strict Castilian codes (includes 'es' as default)
                elif (lang == 'es' and is_castilian_title) or lang in audio_castilian_check:
                    has_castilian = True
                    audios.append(audio_map)

            if len(audios) > 0:  # If there is at least 1 audio spanish
                if not has_latino and has_castilian:
                    tag_value = str(meta.tag)
                    lt_name = lt_name.replace(tag_value, f" [CAST]{tag_value}") if tag_value else f"{lt_name} [CAST]"
                # else: no special tag needed for Latino-only or mixed audio
            # if not audio Spanish exists, add "[SUBS]"
            elif not meta.tag:
                lt_name = lt_name + " [SUBS]"
            else:
                tag_value = str(meta.tag)
                lt_name = lt_name.replace(tag_value, f" [SUBS]{tag_value}")

        return {"name": re.sub(r"\s{2,}", " ", lt_name)}

    async def get_additional_checks(self, meta: Meta) -> bool:
        if meta.category == "BOOK":
            return True
        spanish_languages = ["spanish", "spanish (latin america)"]
        return await self.common.check_language_requirements(meta, self.tracker, languages_to_check=spanish_languages, check_audio=True, check_subtitle=True)

    async def get_additional_data(self, meta: Meta) -> dict[str, Any]:
        data: dict[str, Any] = {
            'mod_queue_opt_in': await self.get_flag(meta, 'modq'),
        }

        return data
