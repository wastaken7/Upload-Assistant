# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import contextlib
import platform
import re
import zipfile
from pathlib import Path
from typing import Any, ClassVar, cast

import aiofiles
import cli_ui
import fitz
import httpx
import langcodes
import rarfile
from bs4 import BeautifulSoup
from langcodes.tag_parser import LanguageTagError
from rich.markup import escape
from unidecode import unidecode

from src.console import logger, prompt_in_thread
from src.cookie_auth import CookieAuthUploader, CookieValidator
from src.genre_map import ENG_TO_PTBR_GENRE_MAP
from src.get_desc import DescriptionBuilder, html_to_bbcode
from src.languages import languages_manager
from src.meta import Meta
from src.tmdb import TmdbManager
from src.trackers.common import Common


class BrasilTracker:
    """
    BT Private Torrent Tracker
    """

    auth_type = "cookies"
    tracker = "BRASILTRACKER"
    display_name = "BrasilTracker"
    banned_groups: tuple[str, ...] = ()
    source_flag = "BT"
    base_url = "https://brasiltracker.org"
    auth_token: str | None = None
    torrent_url = f"{base_url}/torrents.php?id="
    ultimate_lang_map: ClassVar[dict[str, str]] = {}
    supported_categories = ("TV", "MOVIE", "BOOK", "GAME")
    tracker_urls = ("t.brasiltracker.org",)
    allows_bloated_audio = True
    secret_token: str = ""
    tmdb_localization_requirements: ClassVar = {
        "pt-BR": {
            "main": "credits,videos,content_ratings",
            "episode": "",
        }
    }

    def __init__(self, config: dict[str, Any]) -> None:
        self.config: dict[str, Any] = config
        self.main_tmdb_data: dict[str, Any] = {}
        self.episode_tmdb_data: dict[str, Any] = {}
        self.tmdb_manager = TmdbManager(config)
        self.common = Common(config)
        self.cookie_validator = CookieValidator(config)
        self.cookie_auth_uploader = CookieAuthUploader(config)
        self.session = httpx.AsyncClient(headers={"User-Agent": f"Upload-Assistant ({platform.system()} {platform.release()})"}, timeout=60.0)

        target_site_ids = {
            "arabic": "22",
            "bulgarian": "29",
            "chinese": "14",
            "croatian": "23",
            "czech": "30",
            "danish": "10",
            "dutch": "9",
            "english - forçada": "50",
            "english": "3",
            "estonian": "38",
            "finnish": "15",
            "french": "5",
            "german": "6",
            "greek": "26",
            "hebrew": "40",
            "hindi": "41",
            "hungarian": "24",
            "icelandic": "28",
            "indonesian": "47",
            "italian": "16",
            "japanese": "8",
            "korean": "19",
            "latvian": "37",
            "lithuanian": "39",
            "norwegian": "12",
            "persian": "52",
            "polish": "17",
            "português": "49",
            "romanian": "13",
            "russian": "7",
            "serbian": "31",
            "slovak": "42",
            "slovenian": "43",
            "spanish": "4",
            "swedish": "11",
            "thai": "20",
            "turkish": "18",
            "ukrainian": "34",
            "vietnamese": "25",
        }

        source_alias_map: dict[tuple[str, ...], str] = {
            ("Arabic", "ara", "ar"): "arabic",
            ("Brazilian Portuguese", "Brazilian", "Portuguese-BR", "pt-br", "pt-BR", "Portuguese", "por", "pt", "pt-PT", "Português Brasileiro", "Português"): "português",
            ("Bulgarian", "bul", "bg"): "bulgarian",
            ("Chinese", "chi", "zh", "Chinese (Simplified)", "Chinese (Traditional)", "cmn-Hant", "cmn-Hans", "yue-Hant", "yue-Hans"): "chinese",
            ("Croatian", "hrv", "hr", "scr"): "croatian",
            ("Czech", "cze", "cz", "cs"): "czech",
            ("Danish", "dan", "da"): "danish",
            ("Dutch", "dut", "nl"): "dutch",
            ("English - Forced", "English (Forced)", "en (Forced)", "en-US (Forced)"): "english - forçada",
            ("English", "eng", "en", "en-US", "en-GB", "English (CC)", "English - SDH"): "english",
            ("Estonian", "est", "et"): "estonian",
            ("Finnish", "fin", "fi"): "finnish",
            ("French", "fre", "fr", "fr-FR", "fr-CA"): "french",
            ("German", "ger", "de"): "german",
            ("Greek", "gre", "el"): "greek",
            ("Hebrew", "heb", "he"): "hebrew",
            ("Hindi", "hin", "hi"): "hindi",
            ("Hungarian", "hun", "hu"): "hungarian",
            ("Icelandic", "ice", "is"): "icelandic",
            ("Indonesian", "ind", "id"): "indonesian",
            ("Italian", "ita", "it"): "italian",
            ("Japanese", "jpn", "ja"): "japanese",
            ("Korean", "kor", "ko"): "korean",
            ("Latvian", "lav", "lv"): "latvian",
            ("Lithuanian", "lit", "lt"): "lithuanian",
            ("Norwegian", "nor", "no"): "norwegian",
            ("Persian", "fa", "far"): "persian",
            ("Polish", "pol", "pl"): "polish",
            ("Romanian", "rum", "ro"): "romanian",
            ("Russian", "rus", "ru"): "russian",
            ("Serbian", "srp", "sr", "scc"): "serbian",
            ("Slovak", "slo", "sk"): "slovak",
            ("Slovenian", "slv", "sl"): "slovenian",
            ("Spanish", "spa", "es", "es-ES", "es-419"): "spanish",
            ("Swedish", "swe", "sv"): "swedish",
            ("Thai", "tha", "th"): "thai",
            ("Turkish", "tur", "tr"): "turkish",
            ("Ukrainian", "ukr", "uk"): "ukrainian",
            ("Vietnamese", "vie", "vi"): "vietnamese",
        }

        for aliases_tuple, canonical_name in source_alias_map.items():
            if canonical_name in target_site_ids:
                correct_id = target_site_ids[canonical_name]
                for alias in aliases_tuple:
                    self.ultimate_lang_map[alias.lower()] = correct_id

    async def validate_credentials(self, meta: Meta) -> bool:
        cookie_jar = await self.cookie_validator.load_session_cookies(meta, self.tracker)
        if not cookie_jar:
            return False
        self.session.cookies = cast(Any, cookie_jar)
        return True

    async def load_localized_data(self, meta: Meta) -> None:
        if meta.category in ("MOVIE", "TV"):
            ptbr_data = meta.tmdb_localized_data.get("pt-BR")
            if not ptbr_data or not ptbr_data.get("main"):
                raise RuntimeError(f"{self.tracker}: Missing TMDB localized data (pt-BR).")

            self.main_tmdb_data = ptbr_data["main"]
            self.episode_tmdb_data = ptbr_data.get("episode") or {}
            meta.episode_tmdb_data = self.episode_tmdb_data

    async def get_container(self, meta: Meta) -> str:
        container = meta.container
        container_str = container if container is not None else ""
        container_lower = container_str.lower()

        if meta.category == "BOOK":
            if meta.audiobook:
                audio_format_map = {
                    "acc": "ACC",
                    "aac": "ACC",
                    "ac3": "AC3",
                    "dff": "DFF",
                    "mp2": "MP2",
                    "dsf": "DSF",
                    "flac": "FLAC",
                    "m4a": "M4A",
                    "m4b": "M4B",
                    "mp3": "MP3",
                    "ogg": "OGG",
                    "wav": "WAV",
                    "wma": "WMA",
                }
                return audio_format_map.get(container_lower, "Outro")
            if meta.magazine or meta.comic:
                mag_comic_format_map = {
                    "cbr": "CBR",
                    "cbz": "CBR",
                    "docx": "DOCX",
                    "doc": "DOC",
                    "epub": "ePUB",
                    "gif": "GIF",
                    "img": "IMG",
                    "iso": "ISO",
                    "jpg": "JPG",
                    "jpeg": "JPG",
                    "mobi": "MOBI",
                    "nrg": "NRG",
                    "pdf": "PDF",
                    "png": "PNG",
                }
                return mag_comic_format_map.get(container_lower, "Outro")
            ebook_format_map = {"azw3": "AZW3", "mobi": "MOBI", "pdf": "PDF", "epub": "ePub", "kfx": "KFX"}
            return ebook_format_map.get(container_lower, "")

        if container_str in ["avi", "m2ts", "m4v", "mkv", "mp4", "ts", "vob", "wmv", "mkv"]:
            return container_str.upper()

        return "Outro"

    async def get_additional_checks(self, meta: Meta) -> bool:
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

        is_book = meta.category == "BOOK"
        is_game = meta.category == "GAME"
        if not is_book and not is_game:
            imdb_info: dict[str, Any] = meta.imdb_info
            if not imdb_info.get("imdbID") and not meta.anime:
                logger.info(f"{self.tracker}: [bold red]Ignorando upload devido à ausência de IMDb.[/bold red]")
                return False

            if meta.category in ("MOVIE", "TV"):
                return await self.common.check_portuguese_video_requirements(meta, self.tracker)

        return True

    async def get_type(self, meta: Meta) -> str | None:
        if meta.anime:
            return "5"

        category = meta.category
        if category == "BOOK":
            if meta.audiobook:
                return "15"
            if meta.magazine:
                return "9"
            if meta.comic:
                return "11"
            return "12"

        category_map = {
            "TV": "1",
            "MOVIE": "0",
            "GAME": "8",
        }

        return category_map.get(category) if isinstance(category, str) else None

    def get_game_language(self, meta: Meta) -> str:
        """Map game languages from IGDB to BRASILTRACKER idioma_ori field (same logic as BJS)."""
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
            return ""

        lang_names: list[str] = list(languages.keys()) if isinstance(languages, dict) else []
        if not lang_names:
            return ""

        lang_names_lower = [ln.lower() for ln in lang_names]

        has_portuguese = any("portuguese" in ln or "português" in ln for ln in lang_names_lower)

        if has_portuguese and len(lang_names) > 1:
            return "Multilinguagem"

        if len(lang_names) == 1:
            for key, value in language_map.items():
                if key in lang_names_lower[0]:
                    return value
            return lang_names[0]

        # Multiple languages, no Portuguese → first matching
        for ln in lang_names_lower:
            for key, value in language_map.items():
                if key in ln:
                    return value

        return lang_names[0] if lang_names else ""

    def get_game_genre(self, meta: Meta) -> str:
        genre_map: dict[str, str] = {
            "action": "Ação",
            "adventure": "Aventura",
            "arcade": "Arcade",
            "card": "Jogos de Cartas e Tabuleiro",
            "board": "Jogos de Cartas e Tabuleiro",
            "racing": "Corrida",
            "driving": "Corrida",
            "sport": "Esporte",
            "sports": "Esporte",
            "strategy": "Estratégia Baseada em Turnos",
            "real time strategy": "RTS - Estratégia em Tempo Real",
            "turn-based strategy": "Estratégia Baseada em Turnos",
            "shooter": "Tiro",
            "fighting": "Luta",
            "moba": "Moba",
            "music": "Musical",
            "rhythm": "Musical",
            "platform": "Plataforma",
            "puzzle": "Puzzle",
            "rpg": "RPG",
            "role-playing": "RPG",
            "simulation": "Simulador",
            "simulator": "Simulador",
            "horror": "Terror",
            "hack and slash": "Hack and Slash Beat em Up",
            "indie": "Indie",
            "point-and-click": "Point and Click",
            "visual novel": "Ficção",
        }

        genres_list = meta.genres or meta.keywords or []
        for genre in genres_list:
            genre_lower = genre.strip().lower()
            for key, value in genre_map.items():
                if key in genre_lower:
                    return value

        return ""

    def get_game_platform_bt(self, meta: Meta) -> str:
        """Map meta.platform to BRASILTRACKER plataforma_jogo dropdown value."""
        nin_term = (bytes([110, 105, 110, 116, 101, 110, 100, 111]).decode()).capitalize()
        platform_map: dict[str, str] = {
            "PC": "PC",
            "MAC": "PC",
            "LINUX": "PC",
            "MOBILE": "Celular/Tablet",
            "EMULATOR": "Emulador",
            "PS1": "PS1",
            "PS2": "PS2",
            "PS3": "PS3",
            "PS4": "PS4",
            "PSVITA": "PS Vita",
            "SWITCH": f"{nin_term} Switch",
            "WII": "Wii",
            "WIIU": "Wii U",
            "XBOX": "Xbox Clássico",
            "X360": "Xbox 360",
            "XONE": "Multiplataforma",
            "XSX": "Multiplataforma",
        }

        platform = meta.platform.upper().strip()
        return platform_map.get(platform, "")

    def get_game_os(self, meta: Meta) -> str:
        """Map meta.platform to BRASILTRACKER sys_jogo dropdown value."""
        platform = meta.platform.upper().strip()
        if platform == "PC":
            return "Windows"
        if platform == "MAC":
            return "Mac"
        if platform == "LINUX":
            return "Linux"
        if platform == "MOBILE":
            return "Android"
        if platform in {"PS1", "PS2", "PS3", "PS4", "PS5", "PSVITA", "SWITCH", "WII", "WIIU", "XBOX", "X360", "XONE", "XSX"}:
            return "Console"
        return ""

    def get_game_format(self, meta: Meta) -> str:
        """Map game container/type to BRASILTRACKER formato_jogo dropdown value."""
        platform = meta.platform.upper().strip()
        container = meta.container.lower()

        if platform == "MOBILE":
            return "APK"
        if container in ("exe", "exe"):
            return "EXE"
        if container in ("iso",):
            return "ISO"
        if container in ("rar", "zip", "7z"):
            return "RAR/ZIP"
        if container in ("bin",):
            return "BIN"
        if container in ("nrg",):
            return "NRG"
        if container in ("ndf",):
            return "NDF"

        # Infer from platform
        if platform in {"PS1", "PS2"}:
            return "ISO"
        if platform in {"PS3", "PS4", "SWITCH"}:
            return "ISO"
        if platform == "PC":
            return "EXE"

        return "Outros"

    async def get_languages(self, _meta: Meta) -> str | None:
        lang_code = self.main_tmdb_data.get("original_language")

        if not isinstance(lang_code, str) or not lang_code:
            return None

        try:
            return langcodes.Language.make(lang_code).display_name("pt").capitalize()

        except LanguageTagError:
            return lang_code

    async def get_audio(self, meta: Meta) -> str:
        if not meta.language_checked:
            await languages_manager.process_desc_language(meta, tracker=self.tracker)

        raw_audio_languages = meta.audio_languages
        audio_languages_raw: list[Any] = []
        if isinstance(raw_audio_languages, list):
            audio_languages_raw = raw_audio_languages
        audio_languages: set[str] = set()
        for lang in audio_languages_raw:
            if isinstance(lang, str):
                audio_languages.add(lang)
        audio_languages_lower = {lang.lower() for lang in audio_languages}

        portuguese_languages = {"portuguese", "português", "pt"}

        has_pt_audio = bool(audio_languages_lower.intersection(portuguese_languages))

        original_lang = str(meta.original_language).lower()
        is_original_pt = original_lang in portuguese_languages

        if has_pt_audio:
            if is_original_pt:
                return "Nacional"
            if len(audio_languages) > 1:
                return "Dual Audio"
            return "Dublado"

        return "Legendado"

    async def get_subtitle(self, meta: Meta) -> tuple[str, list[str]]:
        if not meta.language_checked:
            await languages_manager.process_desc_language(meta, tracker=self.tracker)

        raw_subtitle_languages = meta.subtitle_languages
        subtitle_languages_raw: list[Any] = []
        if isinstance(raw_subtitle_languages, list):
            subtitle_languages_raw = raw_subtitle_languages
        found_language_strings = [lang for lang in subtitle_languages_raw if isinstance(lang, str)]

        subtitle_ids: set[str] = set()
        for lang_str in found_language_strings:
            target_id = self.ultimate_lang_map.get(lang_str.lower())
            if target_id:
                subtitle_ids.add(target_id)

        has_pt_subtitles = "Sim" if "49" in subtitle_ids else "Nao"

        subtitle_id_list = sorted(subtitle_ids)

        if not subtitle_id_list:
            subtitle_id_list.append("44")

        return has_pt_subtitles, subtitle_id_list

    async def get_resolution(self, meta: Meta) -> tuple[str, str]:
        width = ""
        height = ""
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
            width = str(video_mi.get("Width", ""))
            height = str(video_mi.get("Height", ""))

        return width, height

    async def get_video_codec(self, meta: Meta) -> str:
        video_encode = meta.video_encode.strip().lower()
        codec_final = meta.video_codec
        is_hdr = bool(meta.hdr)

        encode_map = {
            "x265": "x265",
            "h.265": "H.265",
            "x264": "x264",
            "h.264": "H.264",
            "vp9": "VP9",
            "xvid": "XviD",
        }

        for key, value in encode_map.items():
            if key in video_encode:
                if value in ["x265", "H.265"] and is_hdr:
                    return f"{value} HDR"
                return value

        codec_lower = codec_final.lower()

        codec_map = {
            "hevc": "x265",
            "avc": "x264",
            "mpeg-2": "MPEG-2",
            "vc-1": "VC-1",
        }

        for key, value in codec_map.items():
            if key in codec_lower:
                return f"{value} HDR" if value == "x265" and is_hdr else value

        return codec_final if codec_final else "Outro"

    async def get_audio_codec(self, meta: Meta) -> str:
        priority_order = ["DTS-X", "E-AC-3 JOC", "TrueHD", "DTS-HD", "PCM", "FLAC", "DTS-ES", "DTS", "E-AC-3", "AC3", "AAC", "Opus", "Vorbis", "MP3", "MP2"]

        codec_map = {
            "DTS-X": ["DTS:X"],
            "E-AC-3 JOC": ["DD+ 5.1 Atmos", "DD+ 7.1 Atmos"],
            "TrueHD": ["TrueHD"],
            "DTS-HD": ["DTS-HD"],
            "PCM": ["LPCM"],
            "FLAC": ["FLAC"],
            "DTS-ES": ["DTS-ES"],
            "DTS": ["DTS"],
            "E-AC-3": ["DD+"],
            "AC3": ["DD"],
            "AAC": ["AAC"],
            "Opus": ["Opus"],
            "Vorbis": ["VORBIS"],
            "MP2": ["MP2"],
            "MP3": ["MP3"],
        }

        audio_description = meta.audio

        if not audio_description or not isinstance(audio_description, str):
            return "Outro"

        for codec_name in priority_order:
            search_terms = codec_map.get(codec_name, [])

            for term in search_terms:
                if term in audio_description:
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
            original_title = meta.title
            brazilian_title = ""

            localized_data = cast(dict[str, Any], meta.tmdb_localized_data.get("pt-BR") or {})
            main_tmdb_data = cast(dict[str, Any], localized_data.get("main") or {})
            original_name_title = main_tmdb_data.get("original_name") or main_tmdb_data.get("original_title")
            tmdb_title = main_tmdb_data.get("name") or main_tmdb_data.get("title")
            if tmdb_title and tmdb_title != meta.title and (not original_name_title or original_name_title != tmdb_title):
                brazilian_title = tmdb_title

            return original_title, brazilian_title

        return "", ""

    async def get_description(self, meta: Meta) -> str:
        builder = DescriptionBuilder(self.tracker, self.config)
        # Set episode_tmdb_data on meta for general_description_generator to pick it up
        meta.episode_tmdb_data = self.episode_tmdb_data

        return await builder.general_description_generator(
            meta,
            audio_spectrogram=False,
            bluray=False,
            book=True,
            custom_header=True,
            custom_signature=False,
            description=False,
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

    async def get_trailer(self, meta: Meta) -> str:
        video_results: list[dict[str, Any]] = []
        videos = self.main_tmdb_data.get("videos")
        if isinstance(videos, dict):
            videos_dict = cast(dict[str, Any], videos)
            results = videos_dict.get("results")
            if isinstance(results, list):
                results_list = cast(list[Any], results)
                video_results.extend(cast(dict[str, Any], result) for result in results_list if isinstance(result, dict))

        youtube = ""

        if video_results:
            last_result = video_results[-1]
            youtube_value = last_result.get("key", "")
            youtube = youtube_value if isinstance(youtube_value, str) else ""

        if not youtube:
            meta_trailer = meta.youtube
            if meta_trailer:
                youtube = meta_trailer.replace("https://www.youtube.com/watch?v=", "").replace("/", "")

        return youtube

    async def get_tags(self, meta: Meta) -> str:
        """Map genres from meta.genres or TMDB to Portuguese tags."""
        if meta.category == "BOOK":
            return ""

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
            logger.info(f"{self.tracker}: [yellow]Gêneros não encontrados em modo unattended. Plando upload para {self.tracker}.[/yellow]")
            meta.skipping = f"{self.tracker}"
            return ""

        tags_raw = await prompt_in_thread(cli_ui.ask_string, f"Digite os gêneros (no formato do {self.tracker}): ")
        return unidecode((tags_raw or "").strip())

    async def search_existing(self, meta: Meta) -> list[dict[str, Any]]:
        dupes: list[dict[str, Any]] = []
        is_book = meta.category == "BOOK"
        is_game = meta.category == "GAME"

        if is_book or is_game:
            searchstr = meta.title
        else:
            imdb_info: dict[str, Any] = meta.imdb_info
            searchstr = meta.title if meta.anime else imdb_info.get("imdbID")

        is_tv_pack = meta.tv_pack

        search_url = f"{self.base_url}/torrents.php?searchstr={searchstr}"
        cookie_jar = await self.cookie_validator.load_session_cookies(meta, self.tracker)
        if cookie_jar is None:
            return []
        self.session.cookies = cast(Any, cookie_jar)

        response = await self.session.get(search_url)
        if "login.php" in str(response.url) or "login.php" in response.text:
            await self.cookie_validator.handle_validation_failure(meta, self.tracker, response.text)
            meta.skipping = f"{self.tracker}"
            return dupes

        # Extract auth token if present
        auth_match = re.search(r"logout\.php\?auth=([a-f0-9]+)", response.text)
        if auth_match:
            BrasilTracker.secret_token = auth_match.group(1)
        else:
            logger.info(f"{self.tracker}: [bold red]Failed to find auth token on page.[/bold red]")
            meta.skipping = f"{self.tracker}"
            return dupes

        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        torrent_table = soup.find("table", id="torrent_table")
        if not torrent_table:
            return []

        group_links: set[str] = set()
        for group_row in torrent_table.find_all("tr"):
            link = group_row.find("a", href=re.compile(r"torrents\.php\?id=\d+"))
            href_value = link.get("href") if link else None
            if isinstance(href_value, str) and "torrentid" not in href_value:
                group_links.add(href_value)

        if not group_links:
            return []

        for group_link in group_links:
            group_url = f"{self.base_url}/{group_link}"
            group_response = await self.session.get(group_url)
            group_response.raise_for_status()
            group_soup = BeautifulSoup(group_response.text, "html.parser")

            for torrent_row in group_soup.find_all("tr", id=re.compile(r"^torrent\d+$")):
                desc_link = torrent_row.find("a", onclick=re.compile(r"gtoggle"))
                if not desc_link:
                    continue
                description_text = " ".join(desc_link.get_text(strip=True).split())

                row_id = torrent_row.get("id")
                if not isinstance(row_id, str):
                    continue
                torrent_id = row_id.replace("torrent", "")
                file_div = group_soup.find("div", id=f"files_{torrent_id}")
                if not file_div:
                    continue

                # Parse all files
                files: list[str] = []
                file_table = file_div.find("table", class_="filelist_table")
                if file_table:
                    for r in file_table.find_all("tr"):
                        class_attr = r.get("class")
                        class_list = []
                        if isinstance(class_attr, str):
                            class_list = [class_attr]
                        elif isinstance(class_attr, list):
                            class_list = list(class_attr)
                        if "colhead_dark" in class_list:
                            continue
                        cell = r.find("td")
                        if cell:
                            fn = cell.get_text(strip=True)
                            if fn:
                                files.append(fn)

                # Determine name (folder or first filename)
                name = ""
                is_existing_torrent_a_disc = any(keyword in description_text.lower() for keyword in ["bd25", "bd50", "bd66", "bd100", "dvd5", "dvd9", "m2ts"])

                if is_existing_torrent_a_disc or is_tv_pack or is_game:
                    path_div = file_div.find("div", class_="filelist_path")
                    if path_div:
                        folder_name = path_div.get_text(strip=True).strip("/")
                        if folder_name:
                            name = folder_name
                else:
                    if files:
                        name = files[0]

                if not name:
                    name = description_text

                # Size
                tds = torrent_row.find_all("td")
                size = tds[1].get_text(strip=True) if len(tds) > 1 else ""

                link = f"{self.base_url}/torrents.php?torrentid={torrent_id}"
                download = f"{self.base_url}/torrents.php?action=download&id={torrent_id}"

                dupe_entry: dict[str, Any] = {
                    "name": name,
                    "size": size,
                    "link": link,
                    "download": download,
                    "id": torrent_id,
                    "files": files,
                }

                if is_book:
                    audio_exts = {".mp3", ".m4b", ".flac", ".m4a", ".wav", ".ogg", ".aac", ".ac3", ".wma", ".opus"}
                    name_lower = name.lower()
                    is_dupe_audiobook = "audiobook" in name_lower or "audio book" in name_lower or any(any(f.lower().endswith(ext) for ext in audio_exts) for f in files)
                    if is_dupe_audiobook:
                        dupe_entry["type"] = "audiobook"
                    else:
                        for fmt in ["epub", "pdf", "mobi", "azw3", "cbr", "cbz"]:
                            if fmt in name_lower:
                                dupe_entry["type"] = fmt
                                break
                        else:
                            dupe_entry["type"] = "ebook"

                dupes.append(dupe_entry)

        return dupes

    async def get_media_info(self, meta: Meta) -> str:
        info_file_path = ""
        info_file_path = (
            f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/BD_SUMMARY_00.txt"
            if meta.is_disc == "BDMV"
            else f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/MEDIAINFO_CLEANPATH.txt"
        )

        if Path(info_file_path).exists():
            try:
                async with aiofiles.open(info_file_path, encoding="utf-8") as f:
                    return await f.read()
            except Exception as e:
                logger.info(f"{self.tracker}: [bold red]Erro ao ler o arquivo de info em {escape(str(info_file_path))}: {escape(str(e))}[/bold red]")
                return ""
        else:
            logger.info(f"{self.tracker}: [bold red]Arquivo de info não encontrado: {escape(str(info_file_path))}[/bold red]")
            return ""

    async def get_edition(self, meta: Meta) -> str:
        edition_str = meta.edition.lower()
        if not edition_str:
            return ""

        edition_map = {
            "director's cut": "Director's Cut",
            "theatrical": "Theatrical Cut",
            "extended": "Extended",
            "uncut": "Uncut",
            "unrated": "Unrated",
            "imax": "IMAX",
            "noir": "Noir",
            "remastered": "Remastered",
        }

        for keyword, label in edition_map.items():
            if keyword in edition_str:
                return label

        return ""

    async def get_bitrate(self, meta: Meta) -> str:
        if meta.type == "DISC":
            is_disc_type = meta.is_disc

            if is_disc_type == "BDMV":
                disctype = meta.disctype
                if isinstance(disctype, str) and disctype in ["BD100", "BD66", "BD50", "BD25"]:
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
                if isinstance(dvd_size, str) and dvd_size in ["DVD9", "DVD5"]:
                    return dvd_size
                return "DVD9"

        source_type = meta.type

        if not source_type or not isinstance(source_type, str):
            return "Outro"

        keyword_map = {
            "remux": "Remux",
            "webdl": "WEB-DL",
            "webrip": "WEBRip",
            "web": "WEB",
            "encode": "Blu-ray",
            "bdrip": "BDRip",
            "brrip": "BRRip",
            "hdtv": "HDTV",
            "sdtv": "SDTV",
            "dvdrip": "DVDRip",
            "hd-dvd": "HD-DVD",
            "tvrip": "TVRip",
        }

        return keyword_map.get(source_type.lower(), "Outro")

    async def get_screens(self, meta: Meta) -> list[str]:
        menu_images = meta.menu_images
        image_list = meta.image_list
        spectrograms_images = meta.spectrograms_images
        dynamic_hdr_plot_images = meta.dynamic_hdr_plot_images

        combined_images: list[dict[str, Any]] = []
        if isinstance(menu_images, list):
            menu_images_list = menu_images
            combined_images.extend([cast(dict[str, Any], img) for img in menu_images_list if isinstance(img, dict)])
        if isinstance(image_list, list):
            image_list_items = image_list
            combined_images.extend([img for img in image_list_items if isinstance(img, dict)])
        if isinstance(spectrograms_images, list):
            spectrograms_images_list = spectrograms_images
            combined_images.extend([cast(dict[str, Any], img) for img in spectrograms_images_list if isinstance(img, dict)])
        if isinstance(dynamic_hdr_plot_images, list):
            combined_images.extend([cast(dict[str, Any], img) for img in dynamic_hdr_plot_images if isinstance(img, dict)])

        urls: list[str] = []
        for image in combined_images:
            raw_url = image.get("raw_url")
            if isinstance(raw_url, str) and raw_url:
                urls.append(raw_url)

        return urls

    async def get_credits(self, meta: Meta) -> str:
        director_entries: list[str] = []

        imdb_directors = meta.imdb_info.get("directors")
        if isinstance(imdb_directors, list):
            director_entries.extend(name for name in cast(list[Any], imdb_directors) if isinstance(name, str))

        tmdb_directors = meta.tmdb_directors
        if isinstance(tmdb_directors, list):
            director_entries.extend(name for name in cast(list[Any], tmdb_directors) if isinstance(name, str))

        if director_entries:
            unique_names = list(dict.fromkeys(director_entries))[:5]
            return ", ".join(unique_names)

        return "N/A"

    async def get_data(self, meta: Meta) -> dict[str, Any]:
        await self.load_localized_data(meta)  #  keep this line FIRST to ensure localized data is loaded before proceeding
        description = await self.get_description(meta)
        original_title, brazilian_title = self.get_titles(meta)

        data: dict[str, Any] = {
            "submit": "true",
            "auth": BrasilTracker.secret_token,
            "year": str(meta.year) if meta.year is not None else "",
            "title": original_title,
            "type": await self.get_type(meta),
        }

        if meta.category == "GAME":
            overview = ""
            localized_overviews = meta.localized_overviews
            if isinstance(localized_overviews, dict):
                overview = localized_overviews.get("brazilian", "") or meta.overview
            if not overview:
                overview = meta.overview

            # Cover image
            cover_url = ""
            cover_path = meta.artwork_path
            if isinstance(cover_path, str) and cover_path.startswith(("http://", "https://")):
                cover_url = cover_path
            elif meta.artwork_url and meta.artwork_url.startswith(("http://", "https://")):
                cover_url = meta.artwork_url

            data.update(
                {
                    "idioma_ori": self.get_game_language(meta),
                    "genero_jogo": self.get_game_genre(meta),
                    "plataforma_jogo": self.get_game_platform_bt(meta),
                    "sys_jogo": self.get_game_os(meta),
                    "format": self.get_game_format(meta),
                    "tags": await self.get_tags(meta),
                    "image": cover_url,
                    "sinopse": overview,
                    "especificas": description,
                    "screen[]": await self.get_screens(meta),
                    "releasedate": meta.igdb_first_release_date,
                    "vote": str(meta.igdb_rating_count),
                    "rating": str(meta.igdb_rating),
                }
            )

            platform = meta.platform.upper().strip()
            if platform == "PC":
                tag = meta.tag
                if tag:
                    data["versaoapp"] = tag.lstrip("-")

            youtube = meta.youtube
            if youtube:
                data["youtube"] = youtube

        elif meta.category == "BOOK":
            cover_url = await self.get_book_cover(meta)
            resolved_lang = await self.get_book_language(meta)
            resolved_format = await self.get_container(meta)

            audiobook = meta.audiobook
            magazine = meta.magazine
            comic = meta.comic

            data["title"] = original_title
            data.update(
                {
                    "idioma_ori": resolved_lang,
                    "format": resolved_format,
                    "image": cover_url,
                }
            )

            if audiobook:
                data.update(
                    {
                        "banda": meta.author,
                        "bitrate": self.get_audiobook_bitrate(meta),
                        "especificas": description,
                    }
                )

            elif magazine or comic:
                edicao = str(meta.manual_edition or meta.edition or meta.episode or meta.manual_episode or "")
                edicao_str = "".join(c for c in edicao if c.isdigit())

                data.update(
                    {
                        "diretor": meta.publisher or meta.author,
                        "edicao": edicao_str,
                        "paginas": self.get_book_pages(meta),
                        "tags": await self.get_tags(meta),
                        "desc": html_to_bbcode(meta.overview),
                        "especificas": description,
                        "screen[]": await self.get_screens(meta),
                    }
                )

                if magazine:
                    data["adulto"] = "1" if meta.xxx or meta.nsfw else "0"

                    months_pt = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
                    months_en = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
                    text_to_search = (meta.title + " " + meta.basename_no_ext).lower()
                    found_month = ""
                    for m_pt, m_en in zip(months_pt, months_en, strict=False):
                        if m_pt.lower() in text_to_search or m_en.lower() in text_to_search:
                            found_month = m_pt
                            break
                    if found_month:
                        data.update({"mensal": "on", "mes_resvista": found_month})
            else:
                # eBook
                data.update(
                    {
                        "diretor": meta.author,
                        "tags": await self.get_tags(meta),
                        "desc": html_to_bbcode(meta.overview),
                        "screen[]": await self.get_screens(meta),
                    }
                )
        elif meta.category in ("MOVIE", "TV"):
            has_pt_subtitles, subtitle_ids = await self.get_subtitle(meta)
            resolution_width, resolution_height = await self.get_resolution(meta)
            data.update(
                {
                    "audio_c": await self.get_audio_codec(meta),
                    "audio": await self.get_audio(meta),
                    "bitrate": await self.get_bitrate(meta),
                    "desc": "",
                    "diretor": await self.get_credits(meta),
                    "duracao": f"{meta.runtime!s} min",
                    "especificas": description,
                    "format": await self.get_container(meta),
                    "idioma_ori": await self.get_languages(meta) or meta.original_language,
                    "image": f"https://image.tmdb.org/t/p/w500{self.main_tmdb_data.get('poster_path', '') or meta.tmdb_poster_path}",
                    "legenda": has_pt_subtitles,
                    "mediainfo": await self.get_media_info(meta),
                    "resolucao_1": resolution_width,
                    "resolucao_2": resolution_height,
                    "screen[]": await self.get_screens(meta),
                    "sinopse": self.main_tmdb_data.get("overview", "Nenhuma sinopse disponível."),
                    "subtitles[]": subtitle_ids,
                    "tags": await self.get_tags(meta),
                    "video_c": await self.get_video_codec(meta),
                    "youtube": await self.get_trailer(meta),
                }
            )

            # Common data MOVIE/TV
            if not meta.anime:
                if meta.category in ("MOVIE", "TV"):
                    data.update(
                        {
                            "3d": "Sim" if meta.three_d else "Nao",
                            "adulto": "0",
                            "imdb_input": meta.imdb_info.get("imdbID", ""),
                            "nota_imdb": str(meta.imdb_info.get("rating", "")),
                            "title_br": brazilian_title,
                        }
                    )
                if meta.scene:
                    data["scene"] = "on"

            # Common data TV/Anime
            tv_pack = meta.tv_pack
            if meta.category == "TV" or meta.anime:
                data.update(
                    {
                        "episodio": meta.episode,
                        "ntorrent": f"{meta.season}{meta.episode}",
                        "temporada_e": meta.season if not tv_pack else "",
                        "temporada": meta.season if tv_pack else "",
                        "tipo": "ep_individual" if not tv_pack else "completa",
                    }
                )

            # Specific
            if meta.category == "MOVIE":
                data["versao"] = await self.get_edition(meta)
            elif meta.anime:
                data.update(
                    {
                        "fundo_torrent": meta.backdrop,
                        "horas": "",
                        "minutos": "",
                        "rating": str(meta.imdb_info.get("rating", "")),
                        "releasedate": str(meta.year) if meta.year is not None else "",
                        "vote": "",
                    }
                )

        # Anon
        anon = not (meta.anon == 0 and not self.config["TRACKERS"][self.tracker].get("anon", False))
        if anon:
            data["anonymous"] = "1"

        # Internal
        if meta.tag and (
            self.config["TRACKERS"][self.tracker].get("internal", False) is True and meta.tag[1:] in self.config["TRACKERS"][self.tracker].get("internal_groups", [])
        ):
            data.update(
                {
                    "internal": 1,
                }
            )

        return data

    def get_audiobook_bitrate(self, meta: Meta) -> str:
        container_lower = meta.container.lower()
        if container_lower in ("flac", "wav", "alac", "ape", "dsf", "dff"):
            return "Lossless"

        avg_bitrate = meta.audiobook_bitrate
        if avg_bitrate is None:
            return "Outro"

        options = [96, 128, 192, 256, 320]

        # Find option with the minimum absolute difference
        closest_option = min(options, key=lambda opt: abs(opt - avg_bitrate))
        distance = abs(closest_option - avg_bitrate)

        # If distance is greater than 32 (meaning beyond midpoints), return "Outro"
        if distance > 32:
            return "Outro"

        return str(closest_option)

    def build_book_desc(self, meta: Meta) -> str:
        """Build the BBCode table for BOOK-category uploads."""
        builder = DescriptionBuilder(self.tracker, self.config)
        return builder._build_book_desc_section(meta, header_size=3, table=False)

    async def get_book_cover(self, meta: Meta) -> str:
        covers = meta.hosted_artwork
        if isinstance(covers, list) and len(covers) > 0:
            raw_url = covers[0].get("raw_url")
            if raw_url:
                return str(raw_url)

        # Fallback to poster URL if remote
        poster_url = meta.artwork_url
        if isinstance(poster_url, str) and poster_url.startswith(("http://", "https://")):
            return poster_url

        return ""

    async def get_book_language(self, meta: Meta) -> str:
        book_lang_code = meta.book_language_iso
        book_lang_code = book_lang_code.lower() if isinstance(book_lang_code, str) else ""

        lang_map = {
            "pt": "Português",
            "por": "Português",
            "en": "Inglês",
            "eng": "Inglês",
            "it": "Italiano",
            "ita": "Italiano",
            "de": "Alemão",
            "deu": "Alemão",
            "ger": "Alemão",
            "es": "Espanhol",
            "spa": "Espanhol",
            "ja": "Japonês",
            "jpn": "Japonês",
        }
        resolved_lang = lang_map.get(book_lang_code, "Outro")
        if meta.audiobook and resolved_lang == "Japonês":
            resolved_lang = "Outro"
        return resolved_lang

    def get_book_pages(self, meta: Meta) -> str:
        if meta.audiobook:
            return ""

        file_path = meta.filelist[0] if meta.filelist else meta.path
        if not file_path or not Path(file_path).exists():
            return ""

        ext = Path(file_path).suffix.lower()
        if ext == ".pdf":
            with contextlib.suppress(Exception):
                doc = fitz.open(file_path)
                return str(len(doc))
        elif ext in (".cbz", ".cbr"):
            with contextlib.suppress(Exception):
                if ext == ".cbz":
                    with zipfile.ZipFile(file_path) as z:
                        return str(len([f for f in z.namelist() if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))]))
                else:
                    with rarfile.RarFile(file_path) as r:
                        names = cast(list[str], r.namelist())
                        return str(len([name for name in names if name.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))]))
        return ""

    async def upload(self, meta: Meta) -> bool:
        if getattr(meta, "skipping", None) == self.tracker:
            return False
        cookie_jar = await self.cookie_validator.load_session_cookies(meta, self.tracker)
        if cookie_jar is None:
            return False
        self.session.cookies = cast(Any, cookie_jar)
        data = await self.get_data(meta)
        if getattr(meta, "skipping", None) == self.tracker:
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
            id_pattern=r"groupid=(\d+)",
            success_status_code="200, 302, 303",
        )
