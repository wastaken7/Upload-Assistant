# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import asyncio
import json
import os
import platform
import re
import unicodedata
import zipfile
from typing import Any, Optional, cast

import aiofiles
import cli_ui
import fitz
import httpx
import langcodes
import rarfile
from bs4 import BeautifulSoup
from langcodes.tag_parser import LanguageTagError

from src.bbcode import BBCODE
from src.console import console
from src.cookie_auth import CookieAuthUploader, CookieValidator
from src.get_desc import DescriptionBuilder, html_to_bbcode
from src.languages import languages_manager
from src.tmdb import TmdbManager
from src.trackers.COMMON import COMMON


class BT:
    supported_categories = ('TV', 'MOVIE', 'BOOK', 'GAME')
    secret_token: str = ''

    def __init__(self, config: dict[str, Any]) -> None:
        self.config: dict[str, Any] = config
        self.tmdb_manager = TmdbManager(config)
        self.common = COMMON(config)
        self.cookie_validator = CookieValidator(config)
        self.cookie_auth_uploader = CookieAuthUploader(config)
        self.tracker = 'BT'
        self.banned_groups: list[str] = []
        self.source_flag = 'BT'
        self.base_url = 'https://brasiltracker.org'
        self.torrent_url = f'{self.base_url}/torrents.php?id='
        self.auth_token: Optional[str] = None
        self.main_tmdb_data: dict[str, Any] = {}
        self.episode_tmdb_data: dict[str, Any] = {}
        self.session = httpx.AsyncClient(headers={
            'User-Agent': f'Upload Assistant ({platform.system()} {platform.release()})'
        }, timeout=60.0)

        target_site_ids = {
            'arabic': '22', 'bulgarian': '29', 'chinese': '14', 'croatian': '23',
            'czech': '30', 'danish': '10', 'dutch': '9', 'english - forçada': '50',
            'english': '3', 'estonian': '38', 'finnish': '15', 'french': '5',
            'german': '6', 'greek': '26', 'hebrew': '40', 'hindi': '41',
            'hungarian': '24', 'icelandic': '28', 'indonesian': '47', 'italian': '16',
            'japanese': '8', 'korean': '19', 'latvian': '37', 'lithuanian': '39',
            'norwegian': '12', 'persian': '52', 'polish': '17', 'português': '49',
            'romanian': '13', 'russian': '7', 'serbian': '31', 'slovak': '42',
            'slovenian': '43', 'spanish': '4', 'swedish': '11', 'thai': '20',
            'turkish': '18', 'ukrainian': '34', 'vietnamese': '25',
        }

        source_alias_map = {
            ('Arabic', 'ara', 'ar'): 'arabic',
            ('Brazilian Portuguese', 'Brazilian', 'Portuguese-BR', 'pt-br', 'pt-BR', 'Portuguese', 'por', 'pt', 'pt-PT', 'Português Brasileiro', 'Português'): 'português',
            ('Bulgarian', 'bul', 'bg'): 'bulgarian',
            ('Chinese', 'chi', 'zh', 'Chinese (Simplified)', 'Chinese (Traditional)', 'cmn-Hant', 'cmn-Hans', 'yue-Hant', 'yue-Hans'): 'chinese',
            ('Croatian', 'hrv', 'hr', 'scr'): 'croatian',
            ('Czech', 'cze', 'cz', 'cs'): 'czech',
            ('Danish', 'dan', 'da'): 'danish',
            ('Dutch', 'dut', 'nl'): 'dutch',
            ('English - Forced', 'English (Forced)', 'en (Forced)', 'en-US (Forced)'): 'english - forçada',
            ('English', 'eng', 'en', 'en-US', 'en-GB', 'English (CC)', 'English - SDH'): 'english',
            ('Estonian', 'est', 'et'): 'estonian',
            ('Finnish', 'fin', 'fi'): 'finnish',
            ('French', 'fre', 'fr', 'fr-FR', 'fr-CA'): 'french',
            ('German', 'ger', 'de'): 'german',
            ('Greek', 'gre', 'el'): 'greek',
            ('Hebrew', 'heb', 'he'): 'hebrew',
            ('Hindi', 'hin', 'hi'): 'hindi',
            ('Hungarian', 'hun', 'hu'): 'hungarian',
            ('Icelandic', 'ice', 'is'): 'icelandic',
            ('Indonesian', 'ind', 'id'): 'indonesian',
            ('Italian', 'ita', 'it'): 'italian',
            ('Japanese', 'jpn', 'ja'): 'japanese',
            ('Korean', 'kor', 'ko'): 'korean',
            ('Latvian', 'lav', 'lv'): 'latvian',
            ('Lithuanian', 'lit', 'lt'): 'lithuanian',
            ('Norwegian', 'nor', 'no'): 'norwegian',
            ('Persian', 'fa', 'far'): 'persian',
            ('Polish', 'pol', 'pl'): 'polish',
            ('Romanian', 'rum', 'ro'): 'romanian',
            ('Russian', 'rus', 'ru'): 'russian',
            ('Serbian', 'srp', 'sr', 'scc'): 'serbian',
            ('Slovak', 'slo', 'sk'): 'slovak',
            ('Slovenian', 'slv', 'sl'): 'slovenian',
            ('Spanish', 'spa', 'es', 'es-ES', 'es-419'): 'spanish',
            ('Swedish', 'swe', 'sv'): 'swedish',
            ('Thai', 'tha', 'th'): 'thai',
            ('Turkish', 'tur', 'tr'): 'turkish',
            ('Ukrainian', 'ukr', 'uk'): 'ukrainian',
            ('Vietnamese', 'vie', 'vi'): 'vietnamese',
        }

        self.ultimate_lang_map: dict[str, str] = {}
        for aliases_tuple, canonical_name in source_alias_map.items():
            if canonical_name in target_site_ids:
                correct_id = target_site_ids[canonical_name]
                for alias in aliases_tuple:
                    self.ultimate_lang_map[alias.lower()] = correct_id

    async def validate_credentials(self, meta: dict[str, Any]) -> bool:
        cookie_jar = await self.cookie_validator.load_session_cookies(meta, self.tracker)
        if cookie_jar is None:
            return False
        self.session.cookies = cast(Any, cookie_jar)
        return True

    async def load_localized_data(self, meta: dict[str, Any]) -> None:
        localized_data_file = f'{meta["base_dir"]}/tmp/{meta["uuid"]}/tmdb_localized_data.json'
        main_ptbr_data: dict[str, Any] = {}
        episode_ptbr_data: dict[str, Any] = {}
        data: dict[str, Any] = {}

        if os.path.isfile(localized_data_file):
            try:
                async with aiofiles.open(localized_data_file, encoding='utf-8') as f:
                    content = await f.read()
                    loaded_data = json.loads(content)
                    data = cast(dict[str, Any], loaded_data) if isinstance(loaded_data, dict) else {}
            except json.JSONDecodeError:
                console.print(f'Warning: Could not decode JSON from {localized_data_file}', markup=False)
                data = {}
            except Exception as e:
                console.print(f'Error reading file {localized_data_file}: {e}', markup=False)
                data = {}

        ptbr_data = data.get('pt-BR')
        ptbr_dict: dict[str, Any] = {}
        if isinstance(ptbr_data, dict):
            ptbr_dict = cast(dict[str, Any], ptbr_data)
        main_ptbr_data = cast(dict[str, Any], ptbr_dict.get('main') or {})

        if not main_ptbr_data:
            localized_main = await self.tmdb_manager.get_tmdb_localized_data(
                meta,
                data_type='main',
                language='pt-BR',
                append_to_response='credits,videos,content_ratings'
            )
            main_ptbr_data = localized_main or {}

        if self.config['DEFAULT']['episode_overview'] and meta['category'] == 'TV' and not meta.get('tv_pack'):
            episode_ptbr_data = cast(dict[str, Any], ptbr_dict.get('episode') or {})
            if not episode_ptbr_data:
                localized_episode = await self.tmdb_manager.get_tmdb_localized_data(
                    meta,
                    data_type='episode',
                    language='pt-BR',
                    append_to_response=''
                )
                episode_ptbr_data = localized_episode or {}

        self.main_tmdb_data = main_ptbr_data or {}
        self.episode_tmdb_data = episode_ptbr_data or {}

        return

    async def get_container(self, meta: dict[str, Any]) -> str:
        container = meta.get('container', '')
        container_str = str(container) if container is not None else ''
        container_lower = container_str.lower()

        if meta.get("category") == "BOOK":
            if meta.get("audiobook", False):
                audio_format_map = {
                    "acc": "ACC",
                    "aac": "ACC",
                    "ac3": "AC3",
                    "dff": "DFF",
                    "mp2": "MP2",
                    "dsf": "DSF",
                    "flac": "FLAC",
                    "m4a": "M4A",
                    "mp3": "MP3",
                    "ogg": "OGG",
                    "wav": "WAV",
                    "wma": "WMA",
                }
                return audio_format_map.get(container_lower, "Outro")
            elif meta.get("magazine", False) or meta.get("comic", False):
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
            else:
                ebook_format_map = {"azw3": "AZW3", "mobi": "MOBI", "pdf": "PDF", "epub": "ePub", "kfx": "KFX"}
                return ebook_format_map.get(container_lower, "")

        if container_str in ['avi', 'm2ts', 'm4v', 'mkv', 'mp4', 'ts', 'vob', 'wmv', 'mkv']:
            return container_str.upper()

        return 'Outro'

    async def get_additional_checks(self, meta: dict[str, Any]) -> bool:
        if meta.get("category") == "GAME":
            pc_platforms = {"PC", "MAC", "LINUX"}
            platform = str(meta.get("platform", "")).upper().strip()
            if platform in pc_platforms:
                builder = DescriptionBuilder(self.tracker, self.config)
                has_install_notes = await builder.get_user_description(meta)
                if not has_install_notes:
                    console.print(
                        f"{self.tracker}: [red]Installation notes are required for PC game uploads. "
                        "Please provide them using [bold]-df[/bold] (path/to/file.txt) or [bold]-pb[/bold] (link to raw text).[/red]"
                    )
                    return False
        return True

    async def get_type(self, meta: dict[str, Any]) -> Optional[str]:
        if meta.get('anime'):
            return '5'

        category = meta.get("category")
        if category == "BOOK":
            if meta.get("audiobook", False):
                return "15"
            if meta.get("magazine", False):
                return "9"
            if meta.get("comic", False):
                return "11"
            return "12"

        category_map = {
            "TV": "1",
            "MOVIE": "0",
            "GAME": "8",
        }

        return category_map.get(category) if isinstance(category, str) else None

    def get_game_language(self, meta: dict[str, Any]) -> str:
        """Map game languages from IGDB to BT idioma_ori field (same logic as BJS)."""
        language_map: dict[str, str] = {
            "german": "Alemão",
            "spanish": "Espanhol",
            "french": "Francês",
            "english": "Inglês",
            "japanese": "Japonês",
            "portuguese": "Português",
            "russian": "Russo",
        }

        languages = meta.get("languages", {})
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

    def get_game_genre(self, meta: dict[str, Any]) -> str:
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

        genres_str = meta.get("genres", "") or meta.get("keywords", "")
        if not genres_str:
            return ""

        for genre in [g.strip() for g in str(genres_str).split(",") if g.strip()]:
            genre_lower = genre.lower()
            for key, value in genre_map.items():
                if key in genre_lower:
                    return value

        return ""

    def get_game_platform_bt(self, meta: dict[str, Any]) -> str:
        """Map meta['platform'] to BT plataforma_jogo dropdown value."""
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
            "SWITCH": "Nintendo Switch",
            "WII": "Wii",
            "WIIU": "Wii U",
            "XBOX": "Xbox Clássico",
            "X360": "Xbox 360",
            "XONE": "Multiplataforma",
            "XSX": "Multiplataforma",
        }

        platform = str(meta.get("platform", "")).upper().strip()
        return platform_map.get(platform, "")

    def get_game_os(self, meta: dict[str, Any]) -> str:
        """Map meta['platform'] to BT sys_jogo dropdown value."""
        platform = str(meta.get("platform", "")).upper().strip()
        if platform == "PC":
            return "Windows"
        elif platform == "MAC":
            return "Mac"
        elif platform == "LINUX":
            return "Linux"
        elif platform == "MOBILE":
            return "Android"
        elif platform in {"PS1", "PS2", "PS3", "PS4", "PS5", "PSVITA", "SWITCH", "WII", "WIIU", "XBOX", "X360", "XONE", "XSX"}:
            return "Console"
        return ""

    def get_game_format(self, meta: dict[str, Any]) -> str:
        """Map game container/type to BT formato_jogo dropdown value."""
        platform = str(meta.get("platform", "")).upper().strip()
        container = str(meta.get("container", "")).lower()

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

    async def get_languages(self, _meta: dict[str, Any]) -> Optional[str]:
        lang_code = self.main_tmdb_data.get('original_language')

        if not isinstance(lang_code, str) or not lang_code:
            return None

        try:
            return langcodes.Language.make(lang_code).display_name('pt').capitalize()

        except LanguageTagError:
            return lang_code

    async def get_audio(self, meta: dict[str, Any]) -> str:
        if not meta.get('language_checked', False):
            await languages_manager.process_desc_language(meta, tracker=self.tracker)

        raw_audio_languages = meta.get('audio_languages')
        audio_languages_raw: list[Any] = []
        if isinstance(raw_audio_languages, list):
            audio_languages_raw = raw_audio_languages
        audio_languages: set[str] = set()
        for lang in audio_languages_raw:
            if isinstance(lang, str):
                audio_languages.add(lang)
        audio_languages_lower = {lang.lower() for lang in audio_languages}

        portuguese_languages = {'portuguese', 'português', 'pt'}

        has_pt_audio = bool(audio_languages_lower.intersection(portuguese_languages))

        original_lang = str(meta.get('original_language', '')).lower()
        is_original_pt = original_lang in portuguese_languages

        if has_pt_audio:
            if is_original_pt:
                return 'Nacional'
            elif len(audio_languages) > 1:
                return 'Dual Audio'
            else:
                return 'Dublado'

        return 'Legendado'

    async def get_subtitle(self, meta: dict[str, Any]) -> tuple[str, list[str]]:
        if not meta.get('language_checked', False):
            await languages_manager.process_desc_language(meta, tracker=self.tracker)

        raw_subtitle_languages = meta.get('subtitle_languages')
        subtitle_languages_raw: list[Any] = []
        if isinstance(raw_subtitle_languages, list):
            subtitle_languages_raw = raw_subtitle_languages
        found_language_strings = [lang for lang in subtitle_languages_raw if isinstance(lang, str)]

        subtitle_ids: set[str] = set()
        for lang_str in found_language_strings:
            target_id = self.ultimate_lang_map.get(lang_str.lower())
            if target_id:
                subtitle_ids.add(target_id)

        has_pt_subtitles = 'Sim' if '49' in subtitle_ids else 'Nao'

        subtitle_id_list = sorted(subtitle_ids)

        if not subtitle_id_list:
            subtitle_id_list.append('44')

        return has_pt_subtitles, subtitle_id_list

    async def get_resolution(self, meta: dict[str, Any]) -> tuple[str, str]:
        width = ''
        height = ''
        if meta.get('is_disc') == 'BDMV':
            resolution_str = meta.get('resolution', '')
            try:
                height_num = int(resolution_str.lower().replace('p', '').replace('i', ''))
                height = str(height_num)

                width_num = round((16 / 9) * height_num)
                width = str(width_num)
            except (ValueError, TypeError):
                pass

        else:
            video_mi = meta['mediainfo']['media']['track'][1]
            width = str(video_mi.get('Width', ''))
            height = str(video_mi.get('Height', ''))

        return width, height

    async def get_video_codec(self, meta: dict[str, Any]) -> str:
        video_encode = meta.get('video_encode', '').strip().lower()
        codec_final = meta.get('video_codec', '')
        is_hdr = bool(meta.get('hdr'))

        encode_map = {
            'x265': 'x265',
            'h.265': 'H.265',
            'x264': 'x264',
            'h.264': 'H.264',
            'vp9': 'VP9',
            'xvid': 'XviD',
        }

        for key, value in encode_map.items():
            if key in video_encode:
                if value in ['x265', 'H.265'] and is_hdr:
                    return f'{value} HDR'
                return value

        codec_lower = codec_final.lower()

        codec_map = {
            'hevc': 'x265',
            'avc': 'x264',
            'mpeg-2': 'MPEG-2',
            'vc-1': 'VC-1',
        }

        for key, value in codec_map.items():
            if key in codec_lower:
                return f"{value} HDR" if value == "x265" and is_hdr else value

        return codec_final if codec_final else "Outro"

    async def get_audio_codec(self, meta: dict[str, Any]) -> str:
        priority_order = [
            'DTS-X', 'E-AC-3 JOC', 'TrueHD', 'DTS-HD', 'PCM', 'FLAC', 'DTS-ES',
            'DTS', 'E-AC-3', 'AC3', 'AAC', 'Opus', 'Vorbis', 'MP3', 'MP2'
        ]

        codec_map = {
            'DTS-X': ['DTS:X'],
            'E-AC-3 JOC': ['DD+ 5.1 Atmos', 'DD+ 7.1 Atmos'],
            'TrueHD': ['TrueHD'],
            'DTS-HD': ['DTS-HD'],
            'PCM': ['LPCM'],
            'FLAC': ['FLAC'],
            'DTS-ES': ['DTS-ES'],
            'DTS': ['DTS'],
            'E-AC-3': ['DD+'],
            'AC3': ['DD'],
            'AAC': ['AAC'],
            'Opus': ['Opus'],
            'Vorbis': ['VORBIS'],
            'MP2': ['MP2'],
            'MP3': ['MP3']
        }

        audio_description = meta.get('audio')

        if not audio_description or not isinstance(audio_description, str):
            return 'Outro'

        for codec_name in priority_order:
            search_terms = codec_map.get(codec_name, [])

            for term in search_terms:
                if term in audio_description:
                    return codec_name

        return 'Outro'

    async def get_title(self, meta: dict[str, Any]) -> str:
        title_value = self.main_tmdb_data.get('name') or self.main_tmdb_data.get('title') or ''
        title = title_value if isinstance(title_value, str) else ''
        original_name_title = self.main_tmdb_data.get("original_name") or self.main_tmdb_data.get("original_title") or ""

        if title and title != meta.get("title") and (not original_name_title or title.lower() != original_name_title.lower()):
            return title
        return ""

    async def get_description(self, meta: dict[str, Any]) -> str:
        builder = DescriptionBuilder(self.tracker, self.config)
        desc_parts: list[str] = []

        # Custom Header
        custom_header = await builder.get_custom_header()
        desc_parts.append(custom_header)

        if meta.get("category") == "BOOK":
            custom_header = await builder.get_custom_header()
            if custom_header:
                desc_parts.append(custom_header)

            book_desc = self.build_book_desc(meta)
            if book_desc:
                desc_parts.append(book_desc)

            user_desc = await builder.get_user_description(meta)
            if user_desc:
                desc_parts.append(user_desc)

            audiobook = bool(meta.get("audiobook", False))
            magazine = bool(meta.get("magazine", False))
            comic = bool(meta.get("comic", False))

            if audiobook or not (magazine or comic):  # audiobook or eBook
                audio_spectrograms = meta.get("spectrograms_images", [])
                if audio_spectrograms:
                    spectrograms_header = self.config["DEFAULT"].get("audio_spectrogram_header", "[center][b]Audio Spectrogram[/b][/center]")
                    spectrograms_block = ""
                    for image in audio_spectrograms:
                        web_url = image.get("web_url")
                        img_url = image.get("img_url")
                        if isinstance(web_url, str) and isinstance(img_url, str) and web_url and img_url:
                            spectrograms_block += f"[url={web_url}][img]{img_url}[/img][/url] "
                    if spectrograms_block:
                        desc_parts.append(f"\n\n{spectrograms_header}\n[center]{spectrograms_block}[/center]")

        # Game
        game_section = builder._build_game_desc_section(meta, header_size=3)
        if game_section:
            desc_parts.append(game_section)

        # Logo
        logo_resize_url = meta.get("tmdb_logo", "")
        if logo_resize_url:
            desc_parts.append(f"[center][img]https://image.tmdb.org/t/p/w300/{logo_resize_url}[/img][/center]")

        # TV
        title_value = self.episode_tmdb_data.get("name")
        title = title_value if isinstance(title_value, str) else ""

        episode_image_value = self.episode_tmdb_data.get("still_path")
        episode_image = episode_image_value if isinstance(episode_image_value, str) else ""

        episode_overview_value = self.episode_tmdb_data.get("overview")
        episode_overview = episode_overview_value if isinstance(episode_overview_value, str) else ""

        if episode_overview:
            desc_parts.append(f"[center]{title}[/center]")

            if episode_image:
                desc_parts.append(f"[center][img]https://image.tmdb.org/t/p/w300{episode_image}[/img][/center]")

            desc_parts.append(f"[center]{episode_overview}[/center]")

        # User description
        user_description = await builder.get_user_description(meta)
        desc_parts.append(user_description)

        # Tonemapped Header
        tonemapped_header = await builder.get_tonemapped_header(meta)
        desc_parts.append(tonemapped_header)

        # Signature
        desc_parts.append(f"[center][url=https://github.com/wastaken7/Upload-Assistant]Compartilhado com {meta['ua_name']} {meta['current_version']}[/url][/center]")

        description = "\n\n".join(part for part in desc_parts if part.strip())

        bbcode = BBCODE()
        description = bbcode.remove_img_resize(description)
        description = bbcode.remove_list(description)
        description = bbcode.remove_extra_lines(description)

        async with aiofiles.open(f"{meta['base_dir']}/tmp/{meta['uuid']}/[{self.tracker}]DESCRIPTION.txt", 'w', encoding='utf-8') as description_file:
            await description_file.write(description)

        return description

    async def get_trailer(self, meta: dict[str, Any]) -> str:
        video_results: list[dict[str, Any]] = []
        videos = self.main_tmdb_data.get('videos')
        if isinstance(videos, dict):
            videos_dict = cast(dict[str, Any], videos)
            results = videos_dict.get('results')
            if isinstance(results, list):
                results_list = results
                video_results.extend(
                    [cast(dict[str, Any], result) for result in results_list if isinstance(result, dict)]
                )

        youtube = ''

        if video_results:
            last_result = video_results[-1]
            youtube_value = last_result.get('key', '')
            youtube = youtube_value if isinstance(youtube_value, str) else ''

        if not youtube:
            meta_trailer = meta.get('youtube', '')
            if meta_trailer:
                youtube = meta_trailer.replace('https://www.youtube.com/watch?v=', '').replace('/', '')

        return youtube

    async def get_tags(self, meta: dict[str, Any]) -> str:
        tags = ''

        if meta.get("category") in ("BOOK", "GAME"):
            keywords_str = meta.get("keywords") or meta.get("genres") or ""
            if keywords_str:
                keyword_list = [k.strip() for k in keywords_str.split(",") if k.strip()]
                tags = ", ".join(unicodedata.normalize("NFKD", name).encode("ASCII", "ignore").decode("utf-8").replace(" ", ".").lower() for name in keyword_list)
        else:
            genres = self.main_tmdb_data.get("genres")
            if isinstance(genres, list):
                genre_names: list[str] = []
                genres_list_raw = genres
                genres_list: list[dict[str, Any]] = [cast(dict[str, Any], genre) for genre in genres_list_raw if isinstance(genre, dict)]
                for genre in genres_list:
                    name = genre.get("name")
                    if isinstance(name, str) and name.strip():
                        genre_names.append(name)

                if genre_names:
                    tags = ", ".join(unicodedata.normalize("NFKD", name).encode("ASCII", "ignore").decode("utf-8").replace(" ", ".").lower() for name in genre_names)

            if not tags:
                tags_raw = await asyncio.to_thread(cli_ui.ask_string, f"Digite os gêneros (no formato do {self.tracker}): ")
                tags = (tags_raw or "").strip()

        return tags

    async def search_existing(self, meta: dict[str, Any], _disctype: str) -> list[dict[str, Any]]:
        dupes: list[dict[str, Any]] = []
        is_book = meta.get("category") == "BOOK"
        is_game = meta.get("category") == "GAME"

        if is_book or is_game:
            searchstr = meta["title"]
        else:
            imdb_info: dict[str, Any] = meta.get("imdb_info", {})
            if not imdb_info.get("imdbID") and not meta.get("anime"):
                console.print(f"{self.tracker}: [bold red]Ignorando upload devido à ausência de IMDb.[/bold red]")
                meta["skipping"] = f"{self.tracker}"
                return dupes
            searchstr = meta["title"] if meta.get("anime") else imdb_info.get("imdbID")

        if is_game:
            should_continue = await self.get_additional_checks(meta)
            if not should_continue:
                meta["skipping"] = f"{self.tracker}"
                return dupes

        is_tv_pack = bool(meta.get("tv_pack"))

        search_url = f"{self.base_url}/torrents.php?searchstr={searchstr}"
        try:
            cookie_jar = await self.cookie_validator.load_session_cookies(meta, self.tracker)
            if cookie_jar is None:
                return []
            self.session.cookies = cast(Any, cookie_jar)

            response = await self.session.get(search_url)
            if "login.php" in str(response.url) or "login.php" in response.text:
                await self.cookie_validator.handle_validation_failure(meta, self.tracker, response.text)
                meta["skipping"] = f"{self.tracker}"
                return dupes

            # Extract auth token if present
            auth_match = re.search(r"logout\.php\?auth=([a-f0-9]+)", response.text)
            if auth_match:
                BT.secret_token = auth_match.group(1)
            else:
                console.print(f"{self.tracker}: [bold red]Failed to find auth token on page.[/bold red]")
                meta["skipping"] = f"{self.tracker}"
                return dupes

            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')

            torrent_table = soup.find('table', id='torrent_table')
            if not torrent_table:
                return []

            group_links: set[str] = set()
            for group_row in torrent_table.find_all('tr'):
                link = group_row.find('a', href=re.compile(r'torrents\.php\?id=\d+'))
                href_value = link.get('href') if link else None
                if isinstance(href_value, str) and 'torrentid' not in href_value:
                    group_links.add(href_value)

            if not group_links:
                return []

            for group_link in group_links:
                group_url = f'{self.base_url}/{group_link}'
                group_response = await self.session.get(group_url)
                group_response.raise_for_status()
                group_soup = BeautifulSoup(group_response.text, 'html.parser')

                for torrent_row in group_soup.find_all('tr', id=re.compile(r'^torrent\d+$')):
                    desc_link = torrent_row.find('a', onclick=re.compile(r'gtoggle'))
                    if not desc_link:
                        continue
                    description_text = ' '.join(desc_link.get_text(strip=True).split())

                    row_id = torrent_row.get('id')
                    if not isinstance(row_id, str):
                        continue
                    torrent_id = row_id.replace('torrent', '')
                    file_div = group_soup.find('div', id=f'files_{torrent_id}')
                    if not file_div:
                        continue

                    # Parse all files
                    files = []
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
                    is_existing_torrent_a_disc = any(keyword in description_text.lower() for keyword in ['bd25', 'bd50', 'bd66', 'bd100', 'dvd5', 'dvd9', 'm2ts'])

                    if is_existing_torrent_a_disc or is_tv_pack or is_game:
                        path_div = file_div.find('div', class_='filelist_path')
                        if path_div:
                            folder_name = path_div.get_text(strip=True).strip('/')
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

                    dupe_entry = {
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

        except Exception as e:
            console.print(f'[bold red]Ocorreu um erro inesperado ao processar a busca: {e}[/bold red]')
            return []

        return dupes

    async def get_media_info(self, meta: dict[str, Any]) -> str:
        info_file_path = ''
        if meta.get('is_disc') == 'BDMV':
            info_file_path = f"{meta.get('base_dir')}/tmp/{meta.get('uuid')}/BD_SUMMARY_00.txt"
        else:
            info_file_path = f"{meta.get('base_dir')}/tmp/{meta.get('uuid')}/MEDIAINFO_CLEANPATH.txt"

        if os.path.exists(info_file_path):
            try:
                async with aiofiles.open(info_file_path, encoding='utf-8') as f:
                    return await f.read()
            except Exception as e:
                console.print(f'[bold red]Erro ao ler o arquivo de info em {info_file_path}: {e}[/bold red]')
                return ''
        else:
            console.print(f'[bold red]Arquivo de info não encontrado: {info_file_path}[/bold red]')
            return ''

    async def get_edition(self, meta: dict[str, Any]) -> str:
        edition_str = meta.get('edition', '').lower()
        if not edition_str:
            return ''

        edition_map = {
            "director's cut": "Director's Cut",
            'theatrical': 'Theatrical Cut',
            'extended': 'Extended',
            'uncut': 'Uncut',
            'unrated': 'Unrated',
            'imax': 'IMAX',
            'noir': 'Noir',
            'remastered': 'Remastered',
        }

        for keyword, label in edition_map.items():
            if keyword in edition_str:
                return label

        return ''

    async def get_bitrate(self, meta: dict[str, Any]) -> str:
        if meta.get('type') == 'DISC':
            is_disc_type = meta.get('is_disc')

            if is_disc_type == 'BDMV':
                disctype = meta.get('disctype')
                if isinstance(disctype, str) and disctype in ['BD100', 'BD66', 'BD50', 'BD25']:
                    return disctype

                try:
                    size_in_gb = meta['bdinfo']['size']
                except (KeyError, IndexError, TypeError):
                    size_in_gb = 0

                if size_in_gb > 66:
                    return 'BD100'
                elif size_in_gb > 50:
                    return 'BD66'
                elif size_in_gb > 25:
                    return 'BD50'
                else:
                    return 'BD25'

            elif is_disc_type == 'DVD':
                dvd_size = meta.get('dvd_size')
                if isinstance(dvd_size, str) and dvd_size in ['DVD9', 'DVD5']:
                    return dvd_size
                return 'DVD9'

        source_type = meta.get('type')

        if not source_type or not isinstance(source_type, str):
            return 'Outro'

        keyword_map = {
            'remux': 'Remux',
            'webdl': 'WEB-DL',
            'webrip': 'WEBRip',
            'web': 'WEB',
            'encode': 'Blu-ray',
            'bdrip': 'BDRip',
            'brrip': 'BRRip',
            'hdtv': 'HDTV',
            'sdtv': 'SDTV',
            'dvdrip': 'DVDRip',
            'hd-dvd': 'HD-DVD',
            'tvrip': 'TVRip',
        }

        return keyword_map.get(source_type.lower(), 'Outro')

    async def get_screens(self, meta: dict[str, Any]) -> list[str]:
        menu_images = meta.get('menu_images')
        image_list = meta.get('image_list')
        spectrograms_images = meta.get("spectrograms_images", [])

        combined_images: list[dict[str, Any]] = []
        if isinstance(menu_images, list):
            menu_images_list = menu_images
            combined_images.extend(
                [cast(dict[str, Any], img) for img in menu_images_list if isinstance(img, dict)]
            )
        if isinstance(image_list, list):
            image_list_items = image_list
            combined_images.extend(
                [cast(dict[str, Any], img) for img in image_list_items if isinstance(img, dict)]
            )
        if isinstance(spectrograms_images, list):
            spectrograms_images_list = spectrograms_images
            combined_images.extend([cast(dict[str, Any], img) for img in spectrograms_images_list if isinstance(img, dict)])

        urls: list[str] = []
        for image in combined_images:
            raw_url = image.get('raw_url')
            if isinstance(raw_url, str) and raw_url:
                urls.append(raw_url)

        return urls

    async def get_credits(self, meta: dict[str, Any]) -> str:
        director_entries: list[str] = []

        imdb_directors = meta.get('imdb_info', {}).get('directors')
        imdb_directors_list: list[Any] = []
        if isinstance(imdb_directors, list):
            imdb_directors_list = cast(list[Any], imdb_directors)
        director_entries.extend([name for name in imdb_directors_list if isinstance(name, str)])

        tmdb_directors = meta.get('tmdb_directors')
        tmdb_directors_list: list[Any] = []
        if isinstance(tmdb_directors, list):
            tmdb_directors_list = tmdb_directors
        director_entries.extend([name for name in tmdb_directors_list if isinstance(name, str)])

        if director_entries:
            unique_names = list(dict.fromkeys(director_entries))[:5]
            return ', '.join(unique_names)

        return 'N/A'

    async def get_data(self, meta: dict[str, Any]) -> dict[str, Any]:
        description = await self.get_description(meta)
        tags = await self.get_tags(meta)

        data: dict[str, Any] = {
            "submit": "true",
            "auth": BT.secret_token,
            "year": str(meta.get("year", "")),
            "title": meta["title"],
            "type": await self.get_type(meta),
        }

        if meta.get("category") == "GAME":
            overview = ""
            localized_overviews = meta.get("localized_overviews", {})
            if isinstance(localized_overviews, dict):
                overview = localized_overviews.get("brazilian", "") or meta.get("overview", "")
            if not overview:
                overview = meta.get("overview", "")

            # Cover image
            cover_url = ""
            cover_path = meta.get("cover_path", "")
            if isinstance(cover_path, str) and cover_path.startswith(("http://", "https://")):
                cover_url = cover_path
            elif meta.get("poster", "") and str(meta.get("poster", "")).startswith(("http://", "https://")):
                cover_url = str(meta.get("poster", ""))

            data.update({
                "idioma_ori": self.get_game_language(meta),
                "genero_jogo": self.get_game_genre(meta),
                "plataforma_jogo": self.get_game_platform_bt(meta),
                "sys_jogo": self.get_game_os(meta),
                "format": self.get_game_format(meta),
                "tags": tags,
                "image": cover_url,
                "sinopse": overview,
                "especificas": description,
                "screen[]": await self.get_screens(meta),
                "releasedate": meta.get("igdb_first_release_date", ""),
                "vote": str(meta.get("igdb_rating_count", "")),
                "rating": str(meta.get("igdb_rating", "")),
            })

            platform = str(meta.get("platform", "")).upper().strip()
            if platform == "PC":
                tag = str(meta.get("tag", ""))
                if tag:
                    data["versaoapp"] = tag.lstrip("-")

            youtube = meta.get("youtube", "")
            if youtube:
                data["youtube"] = youtube

        elif meta.get("category") == "BOOK":
            cover_url = await self.get_book_cover(meta)
            resolved_lang = await self.get_book_language(meta)
            resolved_format = await self.get_container(meta)

            audiobook = bool(meta.get("audiobook", False))
            magazine = bool(meta.get("magazine", False))
            comic = bool(meta.get("comic", False))

            data["title"] = self.common.portuguese_title_capitalization(meta["title"])
            data.update({
                "idioma_ori": resolved_lang,
                "format": resolved_format,
                "image": cover_url,
            })

            if audiobook:
                data.update({
                    "banda": meta.get("author", ""),
                    "bitrate": self.get_audiobook_bitrate(meta),
                    "especificas": description,
                })

            elif magazine or comic:
                edicao = str(meta.get("manual_edition") or meta.get("edition") or meta.get("episode") or meta.get("manual_episode") or "")
                edicao_str = "".join(c for c in edicao if c.isdigit())

                data.update({
                    "diretor": meta.get("publisher", "") or meta.get("author", ""),
                    "edicao": edicao_str,
                    "paginas": self.get_book_pages(meta),
                    "tags": tags,
                    "desc": html_to_bbcode(str(meta.get("overview", ""))),
                    "especificas": description,
                    "screen[]": await self.get_screens(meta),
                })

                if magazine:
                    data["adulto"] = "1" if meta.get("xxx") or meta.get("nsfw") else "0"

                    months_pt = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
                    months_en = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
                    text_to_search = (meta.get("title", "") + " " + meta.get("uuid", "")).lower()
                    found_month = ""
                    for m_pt, m_en in zip(months_pt, months_en):
                        if m_pt.lower() in text_to_search or m_en.lower() in text_to_search:
                            found_month = m_pt
                            break
                    if found_month:
                        data.update({"mensal": "on", "mes_resvista": found_month})
            else:
                # eBook
                data.update({
                    "diretor": meta.get("author", ""),
                    "tags": tags,
                    "desc": html_to_bbcode(str(meta.get("overview", ""))),
                    "screen[]": await self.get_screens(meta),
                })
        else:
            await self.load_localized_data(meta)
            has_pt_subtitles, subtitle_ids = await self.get_subtitle(meta)
            resolution_width, resolution_height = await self.get_resolution(meta)
            data = {
                "audio_c": await self.get_audio_codec(meta),
                "audio": await self.get_audio(meta),
                "bitrate": await self.get_bitrate(meta),
                "desc": "",
                "diretor": await self.get_credits(meta),
                "duracao": f"{str(meta.get('runtime', ''))} min",
                "especificas": description,
                "format": await self.get_container(meta),
                "idioma_ori": await self.get_languages(meta) or meta.get("original_language", ""),
                "image": f"https://image.tmdb.org/t/p/w500{self.main_tmdb_data.get('poster_path', '') or meta.get('tmdb_poster', '')}",
                "legenda": has_pt_subtitles,
                "mediainfo": await self.get_media_info(meta),
                "resolucao_1": resolution_width,
                "resolucao_2": resolution_height,
                "screen[]": await self.get_screens(meta),
                "sinopse": self.main_tmdb_data.get("overview", "Nenhuma sinopse disponível."),
                "subtitles[]": subtitle_ids,
                "tags": tags,
                "video_c": await self.get_video_codec(meta),
                "youtube": await self.get_trailer(meta),
            }

            # Common data MOVIE/TV
            if not meta.get("anime"):
                if meta["category"] in ("MOVIE", "TV"):
                    data.update({
                        "3d": "Sim" if meta.get("3d") else "Nao",
                        "adulto": "0",
                        "imdb_input": meta.get("imdb_info", {}).get("imdbID", ""),
                        "nota_imdb": str(meta.get("imdb_info", {}).get("rating", "")),
                        "title_br": await self.get_title(meta),
                    })
                if meta.get("scene", False):
                    data["scene"] = "on"

            # Common data TV/Anime
            tv_pack = bool(meta.get("tv_pack"))
            if meta["category"] == "TV" or meta.get("anime"):
                data.update({
                    "episodio": meta.get("episode", ""),
                    "ntorrent": f"{meta.get('season', '')}{meta.get('episode', '')}",
                    "temporada_e": meta.get("season", "") if not tv_pack else "",
                    "temporada": meta.get("season", "") if tv_pack else "",
                    "tipo": "ep_individual" if not tv_pack else "completa",
                })

            # Specific
            if meta["category"] == "MOVIE":
                data["versao"] = await self.get_edition(meta)
            elif meta.get("anime"):
                data.update({
                    "fundo_torrent": meta.get("backdrop"),
                    "horas": "",
                    "minutos": "",
                    "rating": str(meta.get("imdb_info", {}).get("rating", "")),
                    "releasedate": str(meta["year"]),
                    "vote": "",
                })

        # Anon
        anon = not (meta['anon'] == 0 and not self.config['TRACKERS'][self.tracker].get('anon', False))
        if anon:
            data['anonymous'] = '1'

        # Internal
        if (
            self.config['TRACKERS'][self.tracker].get('internal', False) is True
            and meta['tag'] != ''
            and (meta['tag'][1:] in self.config['TRACKERS'][self.tracker].get('internal_groups', []))
        ):
            data.update({
                'internal': 1,
            })

        return data

    def get_audiobook_bitrate(self, meta: dict[str, Any]) -> str:
        container_lower = str(meta.get("container", "")).lower()
        if container_lower in ("flac", "wav", "alac", "ape", "dsf", "dff"):
            return "Lossless"

        avg_bitrate = meta.get("audiobook_bitrate")
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

    def build_book_desc(self, meta: dict[str, Any]) -> str:
        """Build the BBCode table for BOOK-category uploads."""
        builder = DescriptionBuilder(self.tracker, self.config)
        return builder._build_book_desc_section(meta, header_size=3, table=False)

    async def get_book_cover(self, meta: dict[str, Any]) -> str:
        covers = meta.get("covers")
        if isinstance(covers, list) and len(covers) > 0:
            raw_url = covers[0].get("raw_url")
            if raw_url:
                return str(raw_url)

        # Fallback to poster URL if remote
        poster_url = meta.get("poster")
        if isinstance(poster_url, str) and poster_url.startswith(("http://", "https://")):
            return poster_url

        return ""

    async def get_book_language(self, meta: dict[str, Any]) -> str:
        book_lang_code = meta.get("book_language_iso")
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
        if meta.get("audiobook", False) and resolved_lang == "Japonês":
            resolved_lang = "Outro"
        return resolved_lang

    def get_book_pages(self, meta: dict[str, Any]) -> str:
        if meta.get("audiobook", False):
            return ""

        file_path = meta["filelist"][0] if meta.get("filelist") else meta.get("path", "")
        if not file_path or not os.path.exists(file_path):
            return ""

        ext = os.path.splitext(file_path)[1].lower()
        if ext == ".pdf":
            try:
                doc = fitz.open(file_path)
                return str(len(doc))
            except Exception:
                pass
        elif ext in (".cbz", ".cbr"):
            try:
                if ext == ".cbz":
                    with zipfile.ZipFile(file_path) as z:
                        return str(len([f for f in z.namelist() if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))]))
                else:
                    with rarfile.RarFile(file_path) as r:
                        return str(len([f for f in r.namelist() if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))]))
            except Exception:
                pass
        return ""

    async def upload(self, meta: dict[str, Any], _disctype: str) -> bool:
        cookie_jar = await self.cookie_validator.load_session_cookies(meta, self.tracker)
        if cookie_jar is None:
            return False
        self.session.cookies = cast(Any, cookie_jar)
        data = await self.get_data(meta)

        is_uploaded = await self.cookie_auth_uploader.handle_upload(
            meta=meta,
            tracker=self.tracker,
            source_flag=self.source_flag,
            torrent_url=self.torrent_url,
            data=data,
            torrent_field_name='file_input',
            upload_cookies=self.session.cookies,
            upload_url=f"{self.base_url}/upload.php",
            id_pattern=r'groupid=(\d+)',
            success_status_code="200, 302, 303",
        )

        return is_uploaded
