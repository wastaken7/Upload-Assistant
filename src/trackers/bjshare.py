# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import asyncio
import platform
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar
from urllib.parse import urlparse

import aiofiles
import cli_ui
import httpx
import langcodes
import pycountry
from bs4 import BeautifulSoup, Tag
from langcodes.tag_parser import LanguageTagError
from unidecode import unidecode

from src.console import logger, prompt_in_thread
from src.cookie_auth import CookieAuthUploader, CookieValidator
from src.genre_map import ENG_TO_PTBR_GENRE_MAP
from src.get_desc import DescriptionBuilder
from src.languages import languages_manager
from src.meta import Meta
from src.temp_paths import screenshots_dir
from src.tmdb import TmdbManager
from src.trackers.common import Common

Config = dict[str, Any]


class BJShare:
    """
    BJ-Share is a BRAZILIAN Private Torrent Tracker for MOVIES / TV / GENERAL
    """

    auth_type = "cookies"
    tracker = "BJSHARE"
    display_name = "BJShare"
    banned_groups: tuple[str, ...] = ()
    source_flag = "BJ"
    base_url = "https://bj-share.info"
    auth_token = None
    torrent_url = f"{base_url}/torrents.php?torrentid="
    torrent_download_url = f"{base_url}/torrents.php?action=download&id="
    requests_url = f"{base_url}/requests.php?"
    supported_categories = ("TV", "MOVIE", "BOOK", "GAME")
    tracker_urls = ("tracker.bj-share.info",)
    allows_bloated_audio = True
    secret_token: str = ""
    already_has_the_info: bool = False
    database_title: str = ""
    database_identifier: str = ""
    database_overview: str = ""
    tmdb_localization_requirements: ClassVar = {
        "pt-BR": {
            "main": "credits,videos,content_ratings",
            "episode": "",
        }
    }
    file_extensions: ClassVar = {
        "mkv",
        "mp4",
        "avi",
        "ts",
        "m2ts",
        "wmv",
        "mov",
        "flv",
        "webm",
        "mpg",
        "mpeg",
        "vob",
        "divx",
        "xvid",
        "mp3",
        "m4b",
        "flac",
        "aac",
        "m4a",
        "ogg",
        "wav",
        "opus",
        "wma",
        "ape",
        "cue",
        "m3u",
        "epub",
        "pdf",
        "mobi",
        "azw3",
        "kfx",
        "cbz",
        "cbr",
        "cbt",
        "fb2",
        "ibooks",
        "djvu",
        "txt",
        "html",
        "doc",
        "docx",
        "xls",
        "xlsx",
        "ppt",
        "pptx",
        "zip",
        "rar",
        "7z",
        "tar",
        "gz",
        "bz2",
        "iso",
        "dmg",
        "pkg",
        "exe",
        "bin",
        "msi",
        "apk",
        "srt",
        "ass",
        "vtt",
        "sub",
        "idx",
    }

    def has_extension(self, name: str) -> bool:
        ext = Path(name).suffix
        return ext.lower().lstrip(".") in self.file_extensions

    def __init__(self, config: Config):
        self.config = config
        self.main_tmdb_data: dict[str, Any] = {}
        self.episode_tmdb_data: dict[str, Any] = {}
        self.tmdb_manager = TmdbManager(config)
        self.common = Common(config)
        self.cookie_validator = CookieValidator(config)
        self.cookie_auth_uploader = CookieAuthUploader(config)
        self.session = httpx.AsyncClient(headers={"User-Agent": f"Upload-Assistant ({platform.system()} {platform.release()})"}, timeout=60.0)
        self.semaphore = asyncio.Semaphore(1)

    async def get_additional_checks(self, meta: Meta) -> bool:
        if meta.category == "BOOK":
            if meta.book_language_iso != "por":
                logger.info(f"{self.tracker}: [red]Only books in Portuguese are allowed.[/red]")
                return False
            return True

        if meta.category == "GAME":
            pc_platforms = {"PC", "MAC", "LINUX"}
            platform = meta.platform.upper().strip()
            if platform in pc_platforms:
                builder = DescriptionBuilder(self.tracker, self.config)
                has_install_notes = await builder.get_user_description(meta)
                if not has_install_notes:
                    logger.info(
                        f"{self.tracker}: [red]Installation notes are required for PC game uploads. "
                        "Please provide them using [bold]-df[/bold] (path/to/file.txt) or [bold]-pb[/bold] (link to raw text).[/red]"
                    )
                    return False

            if meta.scene and meta.container in ("rar", "zip", "7z", "tar", "gz"):
                logger.info(f"{self.tracker}: [red]Skipping upload: Scene games must be unpacked (Rule 5.4.1.1).[/red]")
                return False

            return True

        if not bool(meta.subtitle_files):
            return await self.common.check_language_requirements(meta, self.tracker, languages_to_check=["portuguese", "português"], check_audio=True, check_subtitle=True)

        return True

    async def validate_credentials(self, meta: Meta) -> bool:
        cookie_jar = await self.cookie_validator.load_session_cookies(meta, self.tracker)
        if cookie_jar:
            self.session.cookies = cookie_jar
            return True

        return False

    async def load_localized_data(self, meta: Meta) -> None:
        if meta.category in ("MOVIE", "TV"):
            ptbr_data = meta.tmdb_localized_data.get("pt-BR")
            if not ptbr_data or not ptbr_data.get("main"):
                raise RuntimeError(f"{self.tracker}: Missing TMDB localized data (pt-BR).")

            self.main_tmdb_data = ptbr_data["main"]
            self.episode_tmdb_data = ptbr_data.get("episode") or {}
            meta.episode_tmdb_data = self.episode_tmdb_data

    def get_container(self, meta: Meta) -> str:
        container: str = meta.container
        category = meta.category

        if category in ("MOVIE", "TV"):
            if container in ["mkv", "mp4", "avi", "vob", "m2ts", "ts"]:
                return container.upper()
            return "Outro"

        if category == "BOOK":
            if meta.audiobook:
                if container in ["aac", "ac3", "dff", "dsf", "flac", "m4a", "m4b", "mp3", "ogg", "wav", "wma"]:
                    return container.upper()
                return "Outro"
            if container == "pdf":
                return "PDF"
            if container == "epub":
                return "ePub"

        return ""

    def get_type(self, meta: Meta) -> int:
        anime = 13
        audiobook = 10
        comic = 11
        ebook = 9
        game = 3
        magazine = 8
        manga = 4
        movie = 0
        newspaper = 23
        tv = 1

        category = meta.category
        if meta.anime:
            return anime

        if category == "BOOK":
            if meta.audiobook:
                return audiobook
            if meta.manga:
                return manga
            if meta.comic:
                return comic

            if meta.newspaper:
                return newspaper
            if meta.magazine:
                return magazine
            return ebook

        category_map = {"TV": tv, "MOVIE": movie, "GAME": game}

        return category_map.get(category, 0)

    def get_languages(self) -> str:
        possible_languages = {
            "Alemão",
            "Árabe",
            "Argelino",
            "Búlgaro",
            "Cantonês",
            "Chinês",
            "Coreano",
            "Croata",
            "Dinamarquês",
            "Egípcio",
            "Espanhol",
            "Estoniano",
            "Filipino",
            "Finlandês",
            "Francês",
            "Grego",
            "Hebraico",
            "Hindi",
            "Holandês",
            "Húngaro",
            "Indonésio",
            "Inglês",
            "Islandês",
            "Italiano",
            "Japonês",
            "Macedônio",
            "Malaio",
            "Marati",
            "Nigeriano",
            "Norueguês",
            "Persa",
            "Polaco",
            "Polonês",
            "Português",
            "Português (pt)",
            "Romeno",
            "Russo",
            "Sueco",
            "Tailandês",
            "Tamil",
            "Tcheco",
            "Telugo",
            "Turco",
            "Ucraniano",
            "Urdu",
            "Vietnamita",
            "Zulu",
            "Outro",
        }
        lang_code = self.main_tmdb_data.get("original_language")
        origin_countries = self.main_tmdb_data.get("origin_country", [])

        if not lang_code:
            return "Outro"

        language_name = None

        if lang_code == "pt":
            language_name = "Português (pt)" if "PT" in origin_countries else "Português"
        else:
            try:
                language_name = langcodes.Language.make(lang_code).display_name("pt").capitalize()
            except LanguageTagError:
                language_name = lang_code

        if language_name in possible_languages:
            return language_name
        return "Outro"

    def get_game_platform(self, meta: Meta) -> str:
        """Map meta.platform to BJSHARE platform ID for the Jogos category."""
        platform_map: dict[str, str] = {
            "3DS": "13",
            "MOBILE": "2",
            "DS": "12",
            "NDS": "12",
            "EMULATOR": "1",
            "PC": "3",
            "MAC": "3",
            "LINUX": "3",
            "PSVITA": "15",
            "PS1": "4",
            "PS2": "5",
            "PS3": "6",
            "PS4": "7",
            "PS5": "18",
            "PSP": "14",
            "SWITCH": "16",
            "WII": "8",
            "WIIU": "9",
            "XBOX": "17",
            "XONE": "17",
            "X360": "10",
            "XSX": "17",
        }

        platform = meta.platform.upper().strip()
        return platform_map.get(platform, "3")  # Default to PC

    def get_game_language(self, meta: Meta) -> str:
        """Map game languages from IGDB/Steam to BJSHARE idioma field.

        Logic (similar to CBR.py get_name):
        - If Portuguese is present AND there are other languages → "Multilinguagem"
        - If only one language → map to BJSHARE name
        - If multiple languages without Portuguese → use the first match from BJSHARE list
        - Fallback → "Outro"
        """
        language_map: dict[str, str] = {
            "german": "Alemão",
            "spanish": "Espanhol",
            "french": "Francês",
            "english": "Inglês",
            "japanese": "Japonês",
            "portuguese": "Português",
            "russian": "Russo",
        }

        languages = meta.languages
        if not languages:
            return "Outro"

        # Get unique language names (keys of the languages dict from IGDB)
        lang_names: list[str] = list(languages.keys()) if isinstance(languages, dict) else []
        if not lang_names:
            return "Outro"

        lang_names_lower = [ln.lower() for ln in lang_names]

        has_portuguese = any("portuguese" in ln or "português" in ln for ln in lang_names_lower)

        if has_portuguese and len(lang_names) > 1:
            return "Multilinguagem"

        if len(lang_names) == 1:
            for key, bjs_value in language_map.items():
                if key in lang_names_lower[0]:
                    return bjs_value
            return "Outro"

        # Multiple languages, no Portuguese → try to find first matching BJSHARE language
        for ln in lang_names_lower:
            for key, bjs_value in language_map.items():
                if key in ln:
                    return bjs_value

        return "Outro"

    def get_game_subcategory(self, meta: Meta) -> str:
        """Get the game subcategory for BJSHARE."""
        subcategory = meta.game_subcategory
        subcategory_values = {"full_game": "1", "full_game_dlc": "2", "dlc": "3", "update": "4"}
        return subcategory_values.get(subcategory, "1")

    def get_sistema(self, meta: Meta) -> str:
        available_platforms = meta.available_platforms
        amount_available_platforms = len(available_platforms)
        if amount_available_platforms > 0:
            if amount_available_platforms > 1:
                return "Multiplataforma"
            if amount_available_platforms == 1:
                platform = available_platforms[0].lower()
                if "pc" in platform or "windows" in platform:
                    return "Windows"
                if "mac" in platform:
                    return "Mac"
                if "linux" in platform:
                    return "Linux"
        return ""

    async def get_audio(self, meta: Meta) -> str:
        if not meta.language_checked:
            await languages_manager.process_desc_language(meta, tracker=self.tracker)

        audio_languages = set(meta.audio_languages) if meta.audio_languages is not None else ""

        portuguese_languages = ["Portuguese", "Português", "pt"]

        has_pt_audio = any(lang in portuguese_languages for lang in audio_languages)

        original_lang = str(meta.original_language).lower()
        is_original_pt = original_lang in portuguese_languages

        if has_pt_audio:
            if is_original_pt:
                return "Nacional"
            if len(audio_languages) > 1:
                return "Dual Áudio"
            return "Dublado"

        return "Legendado"

    async def get_subtitle(self, meta: Meta) -> str:
        if not meta.language_checked:
            await languages_manager.process_desc_language(meta, tracker=self.tracker)
        found_language_strings = meta.subtitle_languages

        subtitle_type = "Nenhuma"

        if found_language_strings is not None and "Portuguese" in found_language_strings:
            subtitle_type = "Embutida"

        return subtitle_type

    def get_resolution(self, meta: Meta) -> tuple[str, str]:
        width, height = "0", "0"

        if meta.is_disc == "BDMV":
            resolution_str = meta.resolution
            try:
                height_num = int(resolution_str.lower().replace("p", "").replace("i", ""))
                height = str(height_num)

                width_num = round((16 / 9) * height_num)
                width = str(width_num)
            except ValueError, TypeError:
                pass

        else:
            video_mi = meta.mediainfo["media"]["track"][1]
            width = video_mi["Width"]
            height = video_mi["Height"]

        return width, height

    def get_video_codec(self, meta: Meta) -> str:
        codec_map = {
            "x265": "x265",
            "h.265": "H.265",
            "x264": "x264",
            "h.264": "H.264",
            "av1": "AV1",
            "divx": "DivX",
            "h.263": "H.263",
            "kvcd": "KVCD",
            "mpeg-1": "MPEG-1",
            "mpeg-2": "MPEG-2",
            "realvideo": "RealVideo",
            "vc-1": "VC-1",
            "vp6": "VP6",
            "vp8": "VP8",
            "vp9": "VP9",
            "windows media video": "Windows Media Video",
            "xvid": "XviD",
            "hevc": "H.265",
            "avc": "H.264",
        }

        video_encode = meta.video_encode.lower()
        video_codec = meta.video_codec

        search_text = f"{video_encode} {video_codec.lower()}"

        for key, value in codec_map.items():
            if key in search_text:
                return value

        return video_codec if video_codec else "Outro"

    def get_audio_codec(self, meta: Meta) -> str:
        priority_order = ["DTS-X", "E-AC-3 JOC", "TrueHD", "DTS-HD", "LPCM", "PCM", "FLAC", "DTS-ES", "DTS", "E-AC-3", "AC3", "AAC", "Opus", "Vorbis", "MP3", "MP2"]

        codec_map = {
            "DTS-X": ["DTS:X", "DTS-X"],
            "E-AC-3 JOC": ["E-AC-3 JOC", "DD+ JOC"],
            "TrueHD": ["TRUEHD"],
            "DTS-HD": ["DTS-HD", "DTSHD"],
            "LPCM": ["LPCM"],
            "PCM": ["PCM"],
            "FLAC": ["FLAC"],
            "DTS-ES": ["DTS-ES"],
            "DTS": ["DTS"],
            "E-AC-3": ["E-AC-3", "DD+"],
            "AC3": ["AC3", "DD"],
            "AAC": ["AAC"],
            "Opus": ["OPUS"],
            "Vorbis": ["VORBIS"],
            "MP2": ["MP2"],
            "MP3": ["MP3"],
        }

        audio_description = meta.audio

        if not audio_description or not isinstance(audio_description, str):
            return "Outro"

        audio_upper = audio_description.upper()

        for codec_name in priority_order:
            search_terms = codec_map.get(codec_name, [])

            for term in search_terms:
                if term.upper() in audio_upper:
                    return codec_name

        return "Outro"

    async def get_name(self, meta: Meta) -> str:
        """This is for the terminal display of the name only, not the actual upload name."""
        original_title, brazilian_title = self.get_titles(meta)
        if not brazilian_title:
            return original_title
        return f"{brazilian_title} [{original_title}]"

    def get_titles(self, meta: Meta) -> tuple[str, str]:
        if meta.category == "BOOK":
            return self.common.portuguese_title_capitalization(meta.title), ""

        if meta.category == "GAME":
            return meta.title, ""

        if meta.category in ("TV", "MOVIE"):
            original_title = meta.imdb_info.get("title") or meta.title
            brazilian_title = ""

            if BJShare.database_title:
                original_title = BJShare.database_title

            main_tmdb_data = dict(meta.tmdb_localized_data.get("pt-BR", {}).get("main")) or {}
            tmdb_title = main_tmdb_data.get("name") or main_tmdb_data.get("title")

            original_titles_to_compare = (
                meta.title,
                meta.imdb_info.get("title"),
                main_tmdb_data.get("original_name"),
                main_tmdb_data.get("original_title"),
            )

            if tmdb_title and (tmdb_title not in original_titles_to_compare):
                brazilian_title = tmdb_title

            return original_title, brazilian_title

        return "", ""

    async def build_description(self, meta: Meta) -> str:
        builder = DescriptionBuilder(self.tracker, self.config)
        meta.episode_tmdb_data = self.episode_tmdb_data

        return await builder.general_description_generator(
            meta,
            audio_spectrogram=True,
            bluray=True,
            book=True,
            custom_header=True,
            custom_signature=True,
            description=True,
            game=True,
            languages=False,
            logo=True,
            mediainfo=True,
            menu_screenshots=False,
            nfo=False,
            screenshots=False,
            tonemapped_header=True,
            tv_info=True,
            ua_signature=True,
            user_description=True,
            signature=f"[align=right][url=https://github.com/wastaken7/Upload-Assistant][size=1]Compartilhado com {meta.ua_name} {meta.current_version} (fork)[/size][/url][/align]",
        )

    def get_trailer(self, meta: Meta) -> str:
        video_results: list[dict[str, Any]] = dict(self.main_tmdb_data.get("videos", {})).get("results", [])
        youtube_code = video_results[-1].get("key", "") if video_results else ""
        return f"http://www.youtube.com/watch?v={youtube_code}" if youtube_code else meta.youtube or ""

    def get_rating(self) -> str:
        ratings: list[dict[str, Any]] = dict(self.main_tmdb_data.get("content_ratings", {})).get("results", [])

        if not ratings:
            return ""

        valid_br_ratings = {"L", "10", "12", "14", "16", "18"}

        br_rating = ""
        us_rating = ""

        for item in ratings:
            if item.get("iso_3166_1") == "BR" and item.get("rating") in valid_br_ratings:
                br_rating = item["rating"]
                br_rating = "Livre" if br_rating == "L" else f"{br_rating} anos"
                break

            # Use US rating as fallback
            if item.get("iso_3166_1") == "US" and not us_rating:
                us_rating = item.get("rating", "")

        return br_rating or us_rating or ""

    async def get_tags(self, meta: Meta) -> str:
        """Map genres from meta.genres or TMDB to Portuguese tags."""
        matched_tags: list[str] = []

        genres_list = meta.genres or meta.keywords or []
        for genre in genres_list:
            genre_lower = genre.strip().lower()
            mapped = ENG_TO_PTBR_GENRE_MAP.get(genre_lower)

            if not mapped and genre_lower in ENG_TO_PTBR_GENRE_MAP.values():
                mapped = genre_lower

            if mapped and mapped not in matched_tags:
                matched_tags.append(mapped)

        if meta.category in ("TV", "MOVIE") and not matched_tags:
            genres_data: list[dict[str, Any]] = self.main_tmdb_data.get("genres", [])
            for g in genres_data:
                name = str(g.get("name", "")).lower()
                if name.strip():
                    mapped = ENG_TO_PTBR_GENRE_MAP.get(name)
                    if mapped and mapped not in matched_tags:
                        matched_tags.append(mapped)

        # If we have matched tags, return them
        if matched_tags:
            return unidecode(", ".join(matched_tags))

        # Final fallback: ask user
        if meta.unattended and not meta.unattended_confirm:
            logger.info(f"{self.tracker}: [yellow]Unattended mode: Gêneros não encontrados. Plando upload para {self.tracker}.[/yellow]")
            meta.skipping = f"{self.tracker}"
            return ""

        tags_raw = await prompt_in_thread(cli_ui.ask_string, f"Digite os gêneros (no formato do {self.tracker}): ")
        return unidecode((tags_raw or "").strip())

    def get_database_title(self, soup: BeautifulSoup) -> str:
        """
        Extracts the original title to ensure consistency with the BJSHARE database.
        Since BJSHARE treats different titles as unique entries regardless of IMDb parity,
        this value is used to match existing records.
        """
        original_title = ""
        info_boxes = soup.find_all("div", class_="box")
        target_box = None

        for box in info_boxes:
            header_div = box.find("div", class_="head")
            if header_div and "Informações" in header_div.get_text():
                target_box = box
                break

        if target_box:
            rows = target_box.find_all("tr")
            for row in rows:
                cells = row.find_all("td")
                if len(cells) >= 2:
                    label_text = cells[0].get_text(strip=True)
                    if "Título Original:" in label_text or "Título:" in label_text:
                        original_title = cells[1].get_text(strip=True)
                        break

        return original_title

    def get_database_identifier(self, soup: BeautifulSoup) -> str:
        """Return the IMDb or TMDb identifier used by an existing BJShare group."""
        for box in soup.find_all("div", class_="box"):
            header = box.find("div", class_="head")
            if not header or "Informações" not in header.get_text():
                continue

            for row in box.find_all("tr"):
                cells = row.find_all("td")
                if len(cells) < 2:
                    continue

                label = cells[0].get_text(" ", strip=True).lower()
                link = cells[1].find("a", href=True)
                href = str(link.get("href", "")) if link else ""

                if "imdb" in label:
                    match = re.search(r"tt\d+", href, re.IGNORECASE)
                    if match:
                        return match.group(0).lower()

                if "tmdb" in label:
                    match = re.search(r"themoviedb\.org/(movie|tv)/(\d+)", href, re.IGNORECASE)
                    if match:
                        return f"{match.group(1).lower()}/{match.group(2)}"

        return ""

    def get_database_overview(self, soup: BeautifulSoup) -> str:
        """Extract the existing overview/synopsis from a BJShare group details page."""
        desc_box = soup.find("div", class_="torrent_description")
        if not desc_box:
            return ""

        for bq in desc_box.find_all("blockquote"):
            if bq.find("iframe") or "center" in bq.get("class", []):
                continue
            text = bq.get_text(strip=True)
            if text:
                return text

        body = desc_box.find("div", class_="body") or desc_box
        for tag in body.find_all(["iframe", "script", "style"]):
            tag.decompose()
        return body.get_text(strip=True)

    async def search_existing(self, meta: Meta) -> list[dict[str, str | list[str]]]:
        dupes: list[dict[str, str | list[str]]] = []
        category = meta.category
        title = meta.title
        if category == "BOOK" and meta.title:
            title = self.common.portuguese_title_capitalization(meta.title)
        search_url = f"{self.base_url}/torrents.php"
        params = {"searchstr": title}

        media_search_terms: list[str] = []
        if category in ("TV", "MOVIE"):
            imdb_id = str(dict(meta.imdb_info).get("imdbID", "")).strip()
            if imdb_id:
                media_search_terms.append(imdb_id)

            tmdb_id = str(meta.tmdb_id or "").strip()
            if tmdb_id:
                media_search_terms.append(f"{category.lower()}/{tmdb_id}")

        elif category == "BOOK":
            filter_cat = "11" if meta.audiobook else "10"
            params = {
                "searchstr": title,
                f"filter_cat[{filter_cat}]": "1",
                "action": "basic",
                "searchsubmit": "1",
            }

        elif category == "GAME":
            params = {
                "searchstr": title,
                "filter_cat[4]": "1",
                "plataforma": self.get_game_platform(meta),
                "action": "basic",
                "searchsubmit": "1",
            }

        else:
            params = {
                "searchstr": title,
            }

        cookie_jar = await self.cookie_validator.load_session_cookies(meta, self.tracker)
        if cookie_jar:
            self.session.cookies = cookie_jar

        BJShare.already_has_the_info = False
        BJShare.database_title = ""
        BJShare.database_identifier = ""
        BJShare.database_overview = ""

        search_params = [params]
        title_already_queried = False
        if category in ("TV", "MOVIE"):
            # Query both exact IDs. The first group page found is retained, while
            # a title search remains available for older groups lacking either ID.
            search_params = [{"searchstr": term} for term in dict.fromkeys(media_search_terms)]
            title_already_queried = not search_params
            if not search_params:
                search_params.append({"searchstr": title})

        response: httpx.Response | None = None
        fallback_response: httpx.Response | None = None
        for query_params in search_params:
            candidate = await self.session.get(search_url, params=query_params, follow_redirects=True)
            candidate.raise_for_status()
            if "login.php" in str(candidate.url) or "login.php" in candidate.text:
                await self.cookie_validator.handle_validation_failure(meta, self.tracker, candidate.text)
                meta.skipping = f"{self.tracker}"
                return dupes

            auth_match = re.search(r"logout\.php\?auth=([a-f0-9]+)", candidate.text)
            if not auth_match:
                logger.info(f"{self.tracker}: [bold red]Failed to find auth token on page.[/bold red]")
                meta.skipping = f"{self.tracker}"
                return dupes
            BJShare.secret_token = auth_match.group(1)

            fallback_response = candidate
            if response is None and BeautifulSoup(candidate.text, "html.parser").find("div", class_="main_column"):
                response = candidate

        if category in ("TV", "MOVIE") and response is None and title and not title_already_queried and title not in media_search_terms:
            candidate = await self.session.get(search_url, params={"searchstr": title}, follow_redirects=True)
            candidate.raise_for_status()
            if "login.php" in str(candidate.url) or "login.php" in candidate.text:
                await self.cookie_validator.handle_validation_failure(meta, self.tracker, candidate.text)
                meta.skipping = f"{self.tracker}"
                return dupes

            auth_match = re.search(r"logout\.php\?auth=([a-f0-9]+)", candidate.text)
            if not auth_match:
                logger.info(f"{self.tracker}: [bold red]Failed to find auth token on page.[/bold red]")
                meta.skipping = f"{self.tracker}"
                return dupes
            BJShare.secret_token = auth_match.group(1)
            fallback_response = candidate
            if BeautifulSoup(candidate.text, "html.parser").find("div", class_="main_column"):
                response = candidate

        response = response or fallback_response
        if response is None:
            return dupes

        soup = BeautifulSoup(response.text, "html.parser")

        # Check if we were redirected to a details page (it contains class "main_column")
        torrent_details_table: Tag | None = soup.find("div", class_="main_column")
        # Or if we remained on the search results page (it contains id "torrent_table")
        torrent_search_table: Tag | None = soup.find("table", id="torrent_table")

        if torrent_details_table:
            BJShare.already_has_the_info = True
            BJShare.database_title = self.get_database_title(soup)
            BJShare.database_identifier = self.get_database_identifier(soup)
            BJShare.database_overview = self.get_database_overview(soup)

            for row in torrent_details_table.find_all("tr"):
                row_id = row.get("id")
                if isinstance(row_id, str) and row_id.startswith("torrent") and not row_id.startswith("torrent_"):
                    torrent_id = row_id.replace("torrent", "")
                    if not torrent_id:
                        continue

                    name = row.get("data-torrentname", "")
                    if not name:
                        continue
                    name = str(name).strip()

                    size_tag = row.find("td", class_="number_column nobr")
                    size = size_tag.get_text(strip=True) if size_tag else ""

                    link = f"{self.torrent_url}{torrent_id}"

                    row_type = "ebook"
                    if category == "BOOK":
                        if meta.audiobook:
                            row_type = "audiobook"
                        else:
                            fmt_attr = row.get("data-format")
                            if fmt_attr:
                                fmt_attr = str(fmt_attr).lower().strip()
                                if fmt_attr in ["epub", "pdf", "mobi", "azw3", "cbr", "cbz"]:
                                    row_type = fmt_attr
                            if row_type == "ebook":
                                name_lower = name.lower()
                                for fmt in ["epub", "pdf", "mobi", "azw3", "cbr", "cbz"]:
                                    if fmt in name_lower:
                                        row_type = fmt
                                        break

                    names: list[Any] = []
                    if name:
                        names.append(name)
                    if category in ("BOOK", "GAME") and BJShare.database_title:
                        names.append(BJShare.database_title.strip())

                    for n in names:
                        dupe_entry: dict[str, str | list[str]] = {
                            "name": n,
                            "size": size,
                            "link": link,
                            "download": f"{self.torrent_download_url}{torrent_id}",
                            "id": torrent_id,
                        }
                        if self.has_extension(n):
                            dupe_entry["files"] = [n]
                        if category == "BOOK":
                            dupe_entry["type"] = row_type
                        dupes.append(dupe_entry)

        elif torrent_search_table:
            for row in torrent_search_table.find_all("tr", class_="torrent"):
                title_link_tag = row.find("a", href=re.compile(r"torrentid=\d+"))
                torrent_id = None
                if title_link_tag and isinstance(title_link_tag, Tag):
                    href = title_link_tag.get("href", "")
                    if isinstance(href, str):
                        match = re.search(r"torrentid=(\d+)", href)
                        if match:
                            torrent_id = match.group(1)

                if not torrent_id:
                    download_link_tag = row.find("a", href=re.compile(r"action=download&id=\d+"))
                    if download_link_tag and isinstance(download_link_tag, Tag):
                        href = download_link_tag.get("href", "")
                        if isinstance(href, str):
                            match = re.search(r"id=(\d+)", href)
                            if match:
                                torrent_id = match.group(1)

                if not torrent_id:
                    continue

                link = f"{self.torrent_url}{torrent_id}"

                torrent_info_div = row.find("div", class_="torrent_info")
                data_name = ""
                if torrent_info_div and isinstance(torrent_info_div, Tag):
                    data_name = torrent_info_div.get("data-torrentname", "") or torrent_info_div.get("data-name", "")

                site_name = ""
                if title_link_tag:
                    site_name = title_link_tag.get_text(strip=True)

                row_type = "ebook"
                if category == "BOOK":
                    if meta.audiobook:
                        row_type = "audiobook"
                    else:
                        fmt_attr = ""
                        if torrent_info_div and isinstance(torrent_info_div, Tag):
                            fmt_attr = torrent_info_div.get("data-format", "")
                        if fmt_attr:
                            fmt_attr = str(fmt_attr).lower().strip()
                            if fmt_attr in ["epub", "pdf", "mobi", "azw3", "cbr", "cbz"]:
                                row_type = fmt_attr
                        if row_type == "ebook":
                            name_to_check = data_name or site_name
                            name_lower = str(name_to_check).lower()
                            for fmt in ["epub", "pdf", "mobi", "azw3", "cbr", "cbz"]:
                                if fmt in name_lower:
                                    row_type = fmt
                                    break

                names = []
                if category == "BOOK":
                    if data_name:
                        names.append(str(data_name).strip())
                    if site_name:
                        names.append(site_name.strip())
                else:
                    name = data_name or site_name
                    if name:
                        names.append(str(name).strip())

                if not names:
                    continue

                size = ""
                tds = row.find_all("td")
                if len(tds) >= 5:
                    size_candidates = [
                        td.get_text(strip=True) for td in tds if re.search(r"\d+(\.\d+)?\s*(B|KiB|MiB|GiB|TiB|KB|MB|GB|TB)", td.get_text(strip=True), re.IGNORECASE)
                    ]
                    size = size_candidates[0] if size_candidates else tds[4].get_text(strip=True)

                for n in names:
                    dupe_entry = {"name": n, "size": size, "link": link, "download": f"{self.torrent_download_url}{torrent_id}", "id": torrent_id}
                    if self.has_extension(n):
                        dupe_entry["files"] = [n]
                    if category == "BOOK":
                        dupe_entry["type"] = row_type
                    dupes.append(dupe_entry)

        return dupes

    def get_edition(self, meta: Meta) -> str:
        edition_str = meta.edition.lower()
        if not edition_str:
            return ""

        edition_map = {
            "director's cut": "Director's Cut",
            "extended": "Extended Edition",
            "imax": "IMAX",
            "open matte": "Open Matte",
            "noir": "Noir Edition",
            "theatrical": "Theatrical Cut",
            "uncut": "Uncut",
            "unrated": "Unrated",
            "uncensored": "Uncensored",
        }

        for keyword, label in edition_map.items():
            if keyword in edition_str:
                return label

        return ""

    def get_bitrate(self, meta: Meta) -> str:
        if meta.type == "DISC":
            is_disc_type = meta.is_disc

            if is_disc_type == "BDMV":
                disctype = meta.disctype
                if disctype in ["BD100", "BD66", "BD50", "BD25"]:
                    return disctype

                try:
                    size_in_gb = meta.bdinfo["size"]
                except KeyError, IndexError, TypeError:
                    size_in_gb = 0

                if size_in_gb > 66:
                    return "BD100"
                if size_in_gb > 50:
                    return "BD66"
                if size_in_gb > 25:
                    return "BD50"
                return "BD25"

            if is_disc_type == "DVD":
                dvd_size = meta.dvd_size
                if dvd_size in ["DVD9", "DVD5"]:
                    return dvd_size
                return "DVD9"

        source_type = meta.type

        if not source_type or not isinstance(source_type, str):
            return "Outro"

        keyword_map = {
            "webdl": "WEB-DL",
            "webrip": "WEBRip",
            "web": "WEB",
            "remux": "Blu-ray",
            "encode": "Blu-ray",
            "bdrip": "BDRip",
            "brrip": "BRRip",
            "hdtv": "HDTV",
            "sdtv": "SDTV",
            "dvdrip": "DVDRip",
            "hd-dvd": "HD DVD",
            "dvdscr": "DVDScr",
            "hdrip": "HDRip",
            "hdtc": "HDTC",
            "pdtv": "PDTV",
            "tc": "TC",
            "uhdtv": "UHDTV",
            "vhsrip": "VHSRip",
            "tvrip": "TVRip",
        }

        return keyword_map.get(source_type.lower(), "Outro")

    def get_audiobook_bitrate(self, meta: Meta) -> str:
        """
        Extracts the audiobook bitrate from metadata, finds the closest option
        from [64, 128, 192, 256, 320] within a threshold, otherwise returns 'Outro'.
        """
        avg_bitrate = meta.audiobook_bitrate
        if avg_bitrate is None:
            return "Outro"

        options = [64, 128, 192, 256, 320]

        # Find option with the minimum absolute difference
        closest_option = min(options, key=lambda opt: abs(opt - avg_bitrate))
        distance = abs(closest_option - avg_bitrate)

        # If distance is greater than 32 (meaning beyond midpoints), return "Outro"
        if distance > 32:
            return "Outro"

        return str(closest_option)

    async def img_host(self, image_bytes: bytes, filename: str) -> str | None:
        upload_url = f"{self.base_url}/ajax.php?action=screen_up"
        headers = {
            "Referer": f"{self.base_url}/upload.php",
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json",
        }
        files = {"file": (filename, image_bytes, "image/png")}

        try:
            response = await self.session.post(upload_url, headers=headers, files=files, timeout=120)
            response.raise_for_status()
            data: dict[str, Any] = response.json()

            img_url = None
            if data.get("url") and str(data.get("url", "")).startswith("http"):
                img_url = str(data.get("url", "")).replace("\\/", "/")
            else:
                logger.info(f"{self.tracker}: [bold red]The image host appears to be down.[/bold red]")

            return img_url
        except Exception as e:
            logger.info(f"Exceção no upload de {filename}: {e}", extra={"markup": False})
            return None

    async def get_cover(self, meta: Meta):
        category = meta.category

        if category in ("MOVIE", "TV"):
            cover_path = self.main_tmdb_data.get("poster_path") or meta.tmdb_poster_path
            if not cover_path:
                logger.info(f"{self.tracker}: Nenhum poster_path encontrado nos dados do TMDB.", extra={"markup": False})
                return None

            cover_tmdb_url = f"https://image.tmdb.org/t/p/w500{cover_path}"
            if BJShare.already_has_the_info:
                return cover_tmdb_url

            try:
                response = await self.session.get(cover_tmdb_url, timeout=120)
                response.raise_for_status()
                image_bytes = response.content
                filename = Path(cover_path).name

                return await self.img_host(image_bytes, filename)
            except Exception as e:
                logger.info(f"{self.tracker}: Falha ao processar pôster da URL {cover_tmdb_url}: {e}", extra={"markup": False})
                return None

        if category in ("BOOK", "GAME"):
            cover_path = meta.artwork_path
            if not cover_path or not await self.common.path_exists(cover_path):
                logger.info("Nenhum cover_path válido encontrado.", extra={"markup": False})
                return None

            try:
                async with aiofiles.open(cover_path, "rb") as f:
                    image_bytes = await f.read()
                filename = Path(cover_path).name

                return await self.img_host(image_bytes, filename)
            except Exception as e:
                logger.info(f"{self.tracker}: Falha ao ler ou enviar capa {cover_path}: {e}", extra={"markup": False})
                return None
        return None

    async def get_screenshots(self, meta: Meta) -> list[str]:
        screens_dir = screenshots_dir(meta.base_dir, meta.uuid)
        local_files = sorted(screens_dir.glob("*.png"))

        disc_menu_links = [img.get("raw_url") for img in meta.menu_images if img.get("raw_url")][:3]

        async def upload_local_file(path: Path):
            async with aiofiles.open(path, "rb") as f:
                image_bytes = await f.read()
            return await self.img_host(image_bytes, Path(path).name)

        async def upload_remote_file(url: str):
            try:
                response = await self.session.get(url, timeout=120)
                response.raise_for_status()
                image_bytes = response.content
                filename = Path(urlparse(url).path).name or "screenshot.png"
                return await self.img_host(image_bytes, filename)
            except Exception as e:
                logger.info(f"{self.tracker}: Failed to process screenshot from URL {url}: {e}", extra={"markup": False})
                return None

        results: list[str] = []

        # Upload menu images
        for url in disc_menu_links:
            result = await upload_remote_file(url)
            if result:
                results.append(result)

        # Use existing files
        if local_files:
            paths: list[Path] = local_files[: 6 - len(results)]

            for coro in asyncio.as_completed([upload_local_file(p) for p in paths]):
                result = await coro
                if result:
                    results.append(result)

        else:
            image_links = [str(img.get("raw_url")) for img in meta.image_list if img.get("raw_url")][: 6 - len(results)]

            for coro in asyncio.as_completed([upload_remote_file(url) for url in image_links]):
                result = await coro
                if result:
                    results.append(result)

        return results

    def get_runtime(self, meta: Meta) -> tuple[int, int]:
        """
        Extracts runtime from metadata and converts total minutes into hours and minutes.
        """
        total_minutes = meta.video_duration if meta.video_duration is not None else 60
        hours, minutes = divmod(total_minutes, 60)

        return hours, minutes

    def get_release_date(self) -> str:
        raw_date_string = self.main_tmdb_data.get("first_air_date") or self.main_tmdb_data.get("release_date")

        if not raw_date_string:
            return ""

        try:
            date_object = datetime.strptime(raw_date_string, "%Y-%m-%d").replace(tzinfo=UTC)
            return date_object.strftime("%d %b %Y")

        except ValueError:
            return ""

    def find_remaster_tags(self, meta: Meta) -> set[str]:
        found_tags: set[str] = set()

        edition = self.get_edition(meta)
        if edition:
            found_tags.add(edition)

        audio_string = meta.audio
        if "Atmos" in audio_string:
            found_tags.add("Dolby Atmos")

        is_10_bit = False
        if meta.is_disc == "BDMV":
            try:
                bit_depth_str = meta.discs[0]["bdinfo"]["video"][0]["bit_depth"]
                if "10" in bit_depth_str:
                    is_10_bit = True
            except KeyError, IndexError, TypeError:
                pass
        else:
            if meta.bit_depth == "10":
                is_10_bit = True

        if is_10_bit:
            found_tags.add("10-bit")

        hdr_string = meta.hdr.upper()
        if "DV" in hdr_string:
            found_tags.add("Dolby Vision")
        if "HDR10+" in hdr_string:
            found_tags.add("HDR10+")
        if "HDR" in hdr_string and "HDR10+" not in hdr_string:
            found_tags.add("HDR10")

        if meta.type == "REMUX":
            found_tags.add("Remux")
        if meta.extras:
            found_tags.add("Com extras")
        if meta.has_commentary or meta.manual_commentary:
            found_tags.add("Com comentários")

        return found_tags

    def build_remaster_title(self, meta: Meta) -> str:
        tag_priority = [
            "Dolby Atmos",
            "Remux",
            "Director's Cut",
            "Extended Edition",
            "IMAX",
            "Open Matte",
            "Noir Edition",
            "Theatrical Cut",
            "Uncut",
            "Unrated",
            "Uncensored",
            "10-bit",
            "Dolby Vision",
            "HDR10+",
            "HDR10",
            "Com extras",
            "Com comentários",
        ]
        available_tags = self.find_remaster_tags(meta)

        ordered_tags = [tag for tag in tag_priority if tag in available_tags]

        return " / ".join(ordered_tags)

    def _normalize_credit_name(self, name: str) -> str:
        normalized = re.sub(r"\s+", " ", unidecode(name).strip())
        normalized = re.sub(r"[^A-Za-z0-9 .'\-]", "", normalized)
        return re.sub(r"\s+", " ", normalized).strip()

    def _collect_credit_names(self, raw_names: list[Any], limit: int) -> list[str]:
        normalized_names: list[str] = []
        seen: set[str] = set()

        for raw_name in raw_names:
            if not isinstance(raw_name, str):
                continue

            normalized_name = self._normalize_credit_name(raw_name)
            if not normalized_name:
                continue

            dedupe_key = normalized_name.casefold()
            if dedupe_key in seen:
                continue

            seen.add(dedupe_key)
            normalized_names.append(normalized_name)

            if len(normalized_names) >= limit:
                break

        return normalized_names

    async def get_credits(self, meta: Meta, role: str) -> str:
        if BJShare.already_has_the_info:
            return "N/A"

        role_map = {
            "director": ("directors", "tmdb_directors"),
            "creator": ("creators", "tmdb_creators"),
            "cast": ("stars", "tmdb_cast"),
        }

        prompt_labels = {
            "director": "Diretor",
            "creator": "Criador",
            "cast": "Elenco",
        }

        if role not in role_map:
            return "N/A"

        imdb_key, tmdb_key = role_map[role]

        imdb_data: dict[str, Any] = meta.imdb_info
        imdb_names = imdb_data.get(imdb_key, [])
        tmdb_names = meta.get(tmdb_key, [])
        names = imdb_names + tmdb_names

        limit = 1 if role in ("director", "creator") else 5
        unique_names = self._collect_credit_names(names, limit)

        if unique_names:
            return ", ".join(unique_names)

        display_name = prompt_labels.get(role, role.capitalize())
        if meta.unattended and not meta.unattended_confirm:
            logger.info(f"{self.tracker}: [yellow]Unattended mode: {display_name} não encontrado(s). Plando upload para {self.tracker}.[/yellow]")
            meta.skipping = f"{self.tracker}"
            return "skipped"

        suffix = " (apenas uma pessoa)" if role in ("director", "creator") else " (separados por vírgula)"
        prompt_message = f"{display_name} não encontrado(s).\nPor favor, insira manualmente{suffix}: "

        user_input_raw = await prompt_in_thread(cli_ui.ask_string, f"{prompt_message}")
        user_input = (user_input_raw or "").strip()
        if user_input:
            entered_names = [name.strip() for name in user_input.split(",")]
            normalized_input = self._collect_credit_names(entered_names, limit)
            if normalized_input:
                return ", ".join(normalized_input)

        return "skipped"

    def get_imdb_rating(self, meta: Meta):
        imdb_info = dict(meta.imdb_info)
        rating = imdb_info.get("rating")

        if not rating:
            return "N/A"

        return str(rating)

    async def get_requests(self, meta: Meta) -> list[dict[str, str]]:
        results: list[dict[str, str]] = []
        title = meta.title
        if meta.category == "BOOK":
            title = self.common.portuguese_title_capitalization(meta.title)
        if not self.config["DEFAULT"].get("search_requests", False) and not meta.search_requests:
            return results
        try:
            cookie_jar = await self.cookie_validator.load_session_cookies(meta, self.tracker)
            if cookie_jar:
                self.session.cookies = cookie_jar
            cat = meta.category
            if cat == "TV":
                cat = 2
            if cat == "MOVIE":
                cat = 1
            if meta.anime:
                cat = 14

            query = title

            search_url = f"{self.requests_url}submit=true&search={query}&showall=on&filter_cat[{cat}]=1"

            response = await self.session.get(search_url)
            response.raise_for_status()
            response_results_text = response.text

            soup = BeautifulSoup(response_results_text, "html.parser")

            request_rows = soup.select("#torrent_table tr.torrent")

            for row in request_rows:
                all_tds = row.find_all("td")
                if not all_tds or len(all_tds) < 5:
                    continue

                info_cell = all_tds[1]

                link_element = info_cell.select_one('a[href*="requests.php?action=view"]')
                quality_element = info_cell.select_one("b")

                if not isinstance(link_element, Tag) or not isinstance(quality_element, Tag):
                    continue

                name: str = link_element.text.strip()
                quality: str = quality_element.text.strip()
                url = link_element.get("href")
                if isinstance(url, str):
                    link: str = url
                else:
                    link = ""

                reward_td = all_tds[3]
                reward_parts = [td.text.replace("\xa0", " ").strip() for td in reward_td.select("tr > td:first-child")]
                reward = " / ".join(reward_parts)

                results.append(
                    {
                        "Name": name,
                        "Quality": quality,
                        "Reward": reward,
                        "Link": link,
                    }
                )

            if results:
                message = f"\n{self.tracker}: [bold yellow]Seu upload pode atender o(s) seguinte(s) pedido(s), confira:[/bold yellow]\n\n"
                for r in results:
                    message += f"[bold green]Nome:[/bold green] {r['Name']}\n"
                    message += f"[bold green]Qualidade:[/bold green] {r['Quality']}\n"
                    message += f"[bold green]Recompensa:[/bold green] {r['Reward']}\n"
                    message += f"[bold green]Link:[/bold green] {self.base_url}/{r['Link']}\n\n"
                logger.info(message)

            return results

        except Exception as e:
            logger.info(f"{self.tracker}: [bold red]Ocorreu um erro ao buscar pedido(s) no {self.tracker}: {e}[/bold red]")
            import traceback

            logger.info(traceback.format_exc())
            return results

    async def get_data(self, meta: Meta) -> dict[str, Any]:
        await self.load_localized_data(meta)  #  keep this line FIRST to ensure localized data is loaded before proceeding
        cookie_jar = await self.cookie_validator.load_session_cookies(meta, self.tracker)
        if cookie_jar:
            self.session.cookies = cookie_jar
        category = meta.category
        original_title, brazilian_title = self.get_titles(meta)

        # These fields are common across all upload types
        data: dict[str, Any] = {
            "submit": "true",
            "auth": BJShare.secret_token,
            "formato": self.get_container(meta),
            "type": str(self.get_type(meta)),
            "year": self.get_year(meta),
        }

        if category == "BOOK":
            b_lang = meta.book_language_iso
            data.update(
                {
                    "title": original_title,
                    "diretor": meta.author,
                    "idioma": "Português" if b_lang == "por" else "Espanhol" if b_lang == "spa" else "Inglês" if b_lang == "eng" else "Outro",
                    "release_desc": await self.build_description(meta),
                }
            )
            if meta.audiobook:
                audiobook_bitrate = self.get_audiobook_bitrate(meta)
                data.update(
                    {
                        "bitrateTypes": audiobook_bitrate,
                        "bitrate": audiobook_bitrate,
                    }
                )

        elif category == "GAME":
            localized_overviews = meta.localized_overviews
            pt_br_overview = localized_overviews.get("brazilian", "") if isinstance(localized_overviews, dict) else ""
            release_desc = pt_br_overview or meta.overview

            data.update(
                {
                    "title": original_title,
                    "plataforma": self.get_game_platform(meta),
                    "idioma": self.get_game_language(meta),
                    "tags": await self.get_tags(meta),
                    "adulto": self.get_adulto(meta),
                    "release_desc": release_desc,
                    "fichatecnica": await self.build_description(meta),
                    "traileryoutube": meta.youtube,
                    "subcategoria": self.get_game_subcategory(meta),
                }
            )

            if meta.platform == "PC":
                tag = meta.tag
                if tag:
                    data["release"] = tag.lstrip("-")
                game_version = meta.game_version
                if game_version:
                    data["versao"] = game_version

            sistema = self.get_sistema(meta)
            if sistema:
                data["sistema"] = sistema

            # Repack
            if meta.repack:
                data["repack"] = "on"

            # Console-specific fields
            if meta.platform.upper().strip() not in ("PC", "MAC", "LINUX", "EMULATOR"):
                game_system = meta.game_system
                game_region = meta.game_region
                destravamento = meta.container.upper() if meta.container.upper() in ("NSP", "XCI", "NSZ", "XCZ", "LT", "JTAG/RGH") else ""
                if game_system:
                    data["sistema"] = game_system
                if game_region:
                    data["regiao"] = game_region
                if destravamento:
                    data["destravamento"] = destravamento

        elif category in ("MOVIE", "TV"):
            width, height = self.get_resolution(meta)
            hours, minutes = self.get_runtime(meta)

            data.update(
                {
                    "audio": await self.get_audio(meta),
                    "codecaudio": self.get_audio_codec(meta),
                    "codecvideo": self.get_video_codec(meta),
                    "duracaoHR": str(hours),
                    "duracaoMIN": str(minutes),
                    "duracaotipo": "selectbox",
                    "fichatecnica": await self.build_description(meta),
                    "idioma": self.get_languages(),
                    "imdblink": self.get_imdblink(meta),
                    "qualidade": self.get_bitrate(meta),
                    "release": meta.service_longname,
                    "remaster_title": self.build_remaster_title(meta),
                    "resolucaoh": height,
                    "resolucaow": width,
                    "sinopse": await self.get_overview(meta),
                    "tags": await self.get_tags(meta),
                    "tipolegenda": await self.get_subtitle(meta),
                    "title": original_title,
                    "titulobrasileiro": brazilian_title,
                    "traileryoutube": self.get_trailer(meta),
                }
            )

            # These fields are common in movies and TV shows, even if it's anime
            if category == "MOVIE":
                data.update(
                    {
                        "adulto": self.get_adulto(meta),
                        "diretor": await self.get_credits(meta, "director"),
                    }
                )

            if category == "TV":
                data.update(
                    {
                        "diretor": await self.get_credits(meta, "creator"),
                        "tipo": "episode" if meta.tv_pack == 0 else "season",
                        "season": meta.season_int,
                        "episode": meta.episode_int,
                    }
                )

            # These fields are common in movies and TV shows, if not Anime
            if not meta.anime:
                data.update(
                    {
                        "validimdb": "yes",
                        "imdbrating": self.get_imdb_rating(meta),
                        "elenco": await self.get_credits(meta, "cast"),
                    }
                )
                if category == "MOVIE":
                    data.update(
                        {
                            "datalancamento": self.get_release_date(),
                        }
                    )

                if category == "TV":
                    # Convert country code to name
                    country_list = [country.name for code in self.main_tmdb_data.get("origin_country", []) if (country := pycountry.countries.get(alpha_2=code))]
                    series_directors = self._collect_credit_names(list(meta.tmdb_directors or meta.imdb_info.get("directors", [])), 1)
                    data.update(
                        {
                            "network": ", ".join([p.get("name", "") for p in self.main_tmdb_data.get("networks", [])]) or "",  # Optional
                            "numtemporadas": self.main_tmdb_data.get("number_of_seasons", ""),  # Optional
                            "datalancamento": self.get_release_date(),
                            "pais": ", ".join(country_list),  # Optional
                            "diretorserie": ", ".join(series_directors),  # Optional
                            "avaliacao": self.get_rating(),  # Optional
                        }
                    )

            # Anime-specific data
            if meta.anime:
                if category == "MOVIE":
                    data.update(
                        {
                            "tipo": "movie",
                        }
                    )
                if category == "TV":
                    data.update(
                        {
                            "adulto": self.get_adulto(meta),
                        }
                    )

        # Anon
        anon = not (meta.anon == 0 and not self.config["TRACKERS"][self.tracker].get("anon", False))
        if anon:
            data.update({"anonymous": "on"})
            if self.config["TRACKERS"][self.tracker].get("show_group_if_anon", False):
                data.update({"anonymousshowgroup": "on"})

        # Internal
        if meta.tag and (
            self.config["TRACKERS"][self.tracker].get("internal", False) is True and meta.tag[1:] in self.config["TRACKERS"][self.tracker].get("internal_groups", [])
        ):
            data.update(
                {
                    "internalrel": 1,
                }
            )

        # Repack
        if meta.repack:
            data.update({"repack": "on"})

        # Only upload images if not debugging
        if not meta.debug:
            data.update(
                {
                    "image": await self.get_cover(meta),
                }
            )
            if not meta.audiobook:
                data.update(
                    {
                        "screenshots[]": await self.get_screenshots(meta),
                    }
                )

        return data

    def get_year(self, meta: Meta) -> str:
        """
        Returns the year of the release.

        For Movies:
            - Standard year
        For TV Shows:
            - The year the episode/season aired.
        """
        year = str(meta.year) if meta.year is not None else "N/A"
        if meta.category == "MOVIE":
            return year

        imdb_info: dict[str, Any] = meta.imdb_info
        imdb_tv_year = imdb_info.get("tv_year", "")
        tvdb_episode_year = meta.tvdb_episode_year

        if tvdb_episode_year and tvdb_episode_year.isdigit():
            return tvdb_episode_year

        if imdb_tv_year and str(imdb_tv_year).isdigit():
            return str(imdb_tv_year)

        return year

    def get_adulto(self, meta: Meta) -> str:
        """
        Check for adult classification eligibility.

        Adheres to upload guidelines where:
        - Movies: Classified as adult only if pornographic.
        - Anime TV Shows: Classified as adult only if hentai.
        """
        adult_yes = "1"
        adult_no = "2"

        if meta.adult_media:
            return adult_yes

        keywords_str = ", ".join(meta.keywords)
        genres = f"{keywords_str} {meta.combined_genres}"
        adult_keywords = ["xxx", "erotic", "porn", "adult", "orgy"]

        if meta.anime and "hentai" in genres.lower():
            return adult_yes

        if any(re.search(rf"(^|,\s*){re.escape(keyword)}(\s*,|$)", genres, re.IGNORECASE) for keyword in adult_keywords):
            return adult_yes

        return adult_no

    def get_imdblink(self, meta: Meta) -> str:
        """
        Get the media identifier for the upload.
        Uses the identifier from an existing BJShare group when available, then
        falls back to IMDb and TMDb metadata.

        Accepted formats:
            IMDb: tt12345
            TMDb: movie/12345 or tv/12345
        """
        if BJShare.database_identifier:
            return BJShare.database_identifier

        imdb_info = dict(meta.imdb_info)
        imdbid = str(imdb_info.get("imdbID", ""))
        if imdbid:
            return imdbid

        category = (meta.category).upper()
        tmdb_id = meta.tmdb_id

        if category in ["MOVIE", "TV"] and tmdb_id:
            return f"{category}/{tmdb_id}".lower()

        return ""

    async def get_overview(self, meta: Meta | None = None) -> str:
        database_overview = BJShare.database_overview
        if database_overview:
            logger.debug(f"{self.tracker}: Using database overview: {database_overview[:50]}...")
            return database_overview

        overview = self.main_tmdb_data.get("overview", "")
        if isinstance(overview, str) and overview.strip():
            return overview

        if meta and meta.unattended and not meta.unattended_confirm:
            logger.info(f"{self.tracker}: [yellow]Sinopse não encontrada em modo unattended. Plando upload para {self.tracker}.[/yellow]")
            meta.skipping = f"{self.tracker}"
            return ""

        logger.info(f"{self.tracker}: [bold red]Sinopse não encontrada no TMDb. Por favor, insira manualmente.[/bold red]")
        user_input_raw = await prompt_in_thread(cli_ui.ask_string, f'"{self.tracker}: [green]Digite a sinopse:[/green]"')
        user_input = (user_input_raw or "").strip()
        if user_input:
            return user_input
        return "N/A"

    def check_data(self, meta: Meta, data: dict[str, Any]) -> str:
        category = meta.category
        if category in ("TV", "MOVIE"):
            if not meta.debug and len(data["screenshots[]"]) < 2:
                return "The number of successful screenshots uploaded is less than 2."

            if any(value == "skipped" for value in (data.get("diretor"), data.get("elenco"), data.get("creators"))):
                return "Missing required credits information (director/cast/creator)."

            if not data.get("imdblink"):
                return "Missing IMDb or TMDb identifier."

        if category == "GAME":
            if not data.get("plataforma"):
                return "Missing game platform."
            if not meta.debug and len(data.get("screenshots[]", [])) < 2:
                return "The number of successful screenshots uploaded is less than 2."

        if category == "BOOK" and not data.get("formato"):
            return "Missing compatible ebook format."

        return ""

    async def upload(self, meta: Meta):
        if getattr(meta, "skipping", None) == self.tracker:
            return False

        data = await self.get_data(meta)
        if getattr(meta, "skipping", None) == self.tracker:
            return False

        issue = self.check_data(meta, data)
        if issue:
            meta.tracker_status[self.tracker]["status_message"] = f"data error - {issue}"
            return False
        return await self.cookie_auth_uploader.handle_upload(
            meta=meta,
            tracker=self.tracker,
            source_flag=self.source_flag,
            torrent_url=self.torrent_url,
            data=data,
            torrent_field_name="file_input",
            upload_cookies=self.session.cookies,
            upload_url=f"{self.base_url}/upload.php",
            id_pattern=r"torrentid=(\d+)",
            success_text="action=download&id=",
        )
