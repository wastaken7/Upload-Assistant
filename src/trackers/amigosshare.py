# Upload Assistant © 2026 Audionut & wastaken7 — Licensed under UAPL v1.0
import asyncio
import json
import platform
import re
import unicodedata
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from io import BytesIO
from pathlib import Path
from typing import Any, cast
from urllib.parse import unquote, urljoin, urlparse

import aiofiles
import httpx
import langcodes
from langcodes import tag_parser
from PIL import Image

from src import language_names, payload_preview
from src.artwork import download_public_image, is_valid_cover_image
from src.cogs.redaction import Redaction
from src.console import logger
from src.cookie_auth import CookieValidator
from src.description_review import get_base_description
from src.genre_map import ENG_TO_PTBR_GENRE_MAP
from src.get_desc import DescriptionBuilder
from src.languages import languages_manager
from src.manual_input import Question, ask, choices_from
from src.manual_questions import game_platform
from src.meta import Meta
from src.screenshot_manifest import files as manifest_files
from src.trackers.common import Common

type Page = dict[str, Any]
type Profile = dict[str, Any]

# Parent categories of the upload form; the profile of each one lists the fields it asks for.
CATEGORY_IDS = {"series": 3, "filmes": 4, "ebook": 5, "jogos": 7, "adultos": 2, "anime": 11}
ANIME_SERIES_ID = 61
ADULT_ID = 42
HENTAI_ID = 48
BOOK_CATEGORY_IDS = {"audiobook": 56, "comic": 20, "manga": 57, "magazine": 62, "book": 58}
GAME_PLATFORM_IDS = {
    "ANDROID": 49,
    "MOBILE": 49,
    "DREAMCAST": 40,
    "EMULATOR": 31,
    "MAC": 36,
    "NDS": 46,
    "DS": 46,
    "SWITCH": 32,
    "SWITCH2": 65,
    "PC": 34,
    "PS1": 37,
    "PS2": 38,
    "PS3": 39,
    "PS4": 33,
    "PS5": 64,
    "PSP": 50,
    "WII": 45,
    "X360": 41,
    "XBOX": 43,
    "XONE": 53,
}
# Console games are titled "Name [Year]"; PC games "Name [Release]" (rule 6.4).
COMPUTER_PLATFORMS = frozenset({"PC", "MAC"})

# Answer keys for characteristics the site and the release metadata could not fill in.
ATTRIBUTE_QUESTION_KEYS = {
    "genre": "amigosshare.genre",
    "language": "amigosshare.language",
    "dub_language": "amigosshare.dub_language",
    "resolution": "amigosshare.resolution",
    "audio_channels": "amigosshare.audio_channels",
    "container": "amigosshare.container",
    "video_codec": "amigosshare.video_codec",
    "audio_codec": "amigosshare.audio_codec",
}
# The upload form reads these from MediaInfo, and only these.
MEDIAINFO_ATTRIBUTES = ("resolution", "container", "video_codec", "audio_codec")

GAME_GENRES = {
    "shooter": "FPS",
    "role-playing (rpg)": "Rpg",
    "role-playing": "Rpg",
    "rpg": "Rpg",
    "puzzle": "Quebra-Cabeça",
    "racing": "Corrida",
    "sport": "Esportes",
    "sports": "Esportes",
    "simulator": "Simulador",
    "simulation": "Simulador",
    "strategy": "Estratégia",
    "real time strategy (rts)": "Estratégia",
    "turn-based strategy (tbs)": "Estratégia",
    "tactical": "Estratégia",
    "platform": "Ação",
    "music": "Musical",
    "kids": "Infantis",
    "point-and-click": "Aventura",
    "visual novel": "Aventura",
}
BOOK_CONTAINERS = {
    ".cbr": "CBR",
    ".cbz": "CBZ",
    ".doc": "DOC",
    ".docx": "DOCX",
    ".epub": "EPUB",
    ".html": "HTML",
    ".htm": "HTML",
    ".mobi": "MOBI",
    ".mp3": "MP3",
    ".pdf": "PDF",
}
VIDEO_EXTENSIONS = frozenset({".mkv", ".mp4", ".avi", ".m2ts", ".ts", ".m4v", ".mov", ".mpg", ".mpeg", ".vob", ".wmv", ".flv", ".asf", ".rmvb", ".rm", ".divx"})
SUBTITLE_EXTENSIONS = frozenset({".srt", ".ass"})
ARCHIVE_EXTENSIONS = frozenset({".rar", ".zip", ".7z", ".tar", ".gz"})
IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
REMOTE_IMAGE_FORMATS = {"PNG": ".png", "JPEG": ".jpg", "WEBP": ".webp"}


def normalize_option(value: str) -> str:
    """Compare option names the way the upload form does: without accents or case."""
    decomposed = unicodedata.normalize("NFD", str(value))
    return "".join(char for char in decomposed if not unicodedata.combining(char)).casefold().strip()


def parse_page(html: str) -> Page | None:
    """Read the Inertia page object the site embeds in each HTML page."""
    match = re.search(r"<script[^>]*\bdata-page=\"app\"[^>]*>(.*?)</script>", html, re.DOTALL)
    if not match:
        return None
    try:
        page = json.loads(match.group(1))
    except ValueError:
        return None
    return cast(Page, page) if isinstance(page, dict) else None


def find_options(attribute: Mapping[str, Any], names: Iterable[str]) -> list[int]:
    """IDs of the options named in ``names``, in that order."""
    options = {normalize_option(str(option.get("name", ""))): int(option["id"]) for option in cast(list[dict[str, Any]], attribute.get("options") or [])}
    found: list[int] = []
    for name in names:
        option_id = options.get(normalize_option(name))
        if option_id is not None and option_id not in found:
            found.append(option_id)
    return found


def site_choices(profile: Profile, lookup: Mapping[str, Any] | None, mediainfo: Mapping[str, Any] | None) -> dict[str, list[int]]:
    """Choose characteristics as the upload form does: IMDb genres and language first, then MediaInfo."""
    attributes = {str(attribute["type"]): attribute for attribute in profile.get("attributes", [])}
    chosen: dict[str, list[int]] = {}
    if lookup:
        if "genre" in attributes and (genres := find_options(attributes["genre"], cast(list[str], lookup.get("genres") or []))):
            chosen["genre"] = genres if attributes["genre"].get("multiple") else genres[:1]
        if "language" in attributes and (language := find_options(attributes["language"], [str(lookup.get("language") or "")])):
            chosen["language"] = language
    suggestions = cast(dict[str, list[str]], (mediainfo or {}).get("attributes") or {})
    for kind, names in suggestions.items():
        if kind in attributes and kind not in chosen and (found := find_options(attributes[kind], names)):
            # Each MediaInfo suggestion lists the closest option first.
            chosen[kind] = found[:1]
    return chosen


def language_code(value: str) -> str:
    """The two-letter code of a language name or code, or '' when unknown."""
    value = str(value or "").strip()
    if not value:
        return ""
    try:
        is_code = re.fullmatch(r"[A-Za-z]{2,3}(?:[-_][A-Za-z0-9]+)*", value)
        language = str((langcodes.Language.get(value) if is_code else language_names.find(value)).language or "")
    except tag_parser.LanguageTagError, LookupError, ValueError:
        return ""
    return "no" if language in ("nb", "nn") else language


def portuguese_language_name(value: str) -> str:
    """A language as the site names it, in Portuguese."""
    code = language_code(value)
    if not code:
        return ""
    return language_names.language_name(langcodes.Language.get(code), "pt")


def format_description(description: str, base_url: str) -> str:
    """Adapt BBCode to what the site renders, dropping images hosted elsewhere (they are refused)."""
    host = urlparse(base_url).netloc

    def is_site_image(url: str) -> bool:
        parsed = urlparse(url.strip())
        return parsed.netloc == host or (not parsed.netloc and parsed.path.startswith("/storage/"))

    def keep_image(match: re.Match[str]) -> str:
        return f"[img]{match.group(2).strip()}[/img]" if is_site_image(match.group(2)) else ""

    sizes = {"1": 22, "2": 20, "3": 18, "4": 16, "5": 14, "6": 12}
    description = re.sub(r"\[img(=[^\]]*)?\](.*?)\[/img\]", keep_image, description, flags=re.IGNORECASE | re.DOTALL)
    description = re.sub(r"\[url=[^\]]*\]\s*\[/url\]", "", description, flags=re.IGNORECASE)
    description = re.sub(r"\[h([1-6])\](.*?)\[/h\1\]", lambda m: f"[size={sizes[m.group(1)]}][b]{m.group(2)}[/b][/size]", description, flags=re.IGNORECASE | re.DOTALL)
    # The site only accepts sizes from 8 to 36.
    description = re.sub(r"\[size=(\d+)\]", lambda m: f"[size={min(max(int(m.group(1)), 8), 36)}]", description, flags=re.IGNORECASE)
    description = re.sub(r"\[align=center\](.*?)\[/align\]", r"[center]\1[/center]", description, flags=re.IGNORECASE | re.DOTALL)
    description = re.sub(r"\[pre\](.*?)\[/pre\]", r"[code]\1[/code]", description, flags=re.IGNORECASE | re.DOTALL)
    description = re.sub(r"\[/td\]", " ", description, flags=re.IGNORECASE)
    description = re.sub(r"\[/?(?:align(?:=[^\]]*)?|font(?:=[^\]]*)?|table|tr|td|th|user|note|alert|left|right)\]", "", description, flags=re.IGNORECASE)
    return re.sub(r"\n{3,}", "\n\n", description).strip()


def resolution_from_dimensions(text: str) -> str:
    """Name a resolution from the site's "width x height" spec, allowing for cropped video."""
    numbers = [int(number) for number in re.findall(r"\d+", text)]
    if len(numbers) < 2:
        return ""
    width, height = numbers[0], numbers[1]
    if width >= 3200 or height >= 1800:
        return "2160p"
    if width >= 1700 or height >= 950:
        return "1080p"
    if width >= 1100 or height >= 650:
        return "720p"
    return "576p" if height > 480 else "480p"


def retry_after_seconds(value: str | None, default: float = 5.0, maximum: float = 60.0) -> float:
    """Seconds to wait from a Retry-After header, which holds either seconds or an HTTP date."""
    value = str(value or "").strip()
    if not value:
        return default
    try:
        seconds = float(value)
    except ValueError:
        try:
            seconds = (parsedate_to_datetime(value) - datetime.now(UTC)).total_seconds()
        except TypeError, ValueError:
            return default
    return min(max(seconds, 0.0), maximum)


def error_text(body: Any, fallback: str) -> str:
    """Laravel validation errors ({"message", "errors": {field: [..]}}) as one line."""
    if not isinstance(body, dict):
        return fallback
    errors = cast(dict[str, Any], body).get("errors")
    if isinstance(errors, dict) and errors:
        parts: list[str] = []
        for field, messages in cast(dict[str, Any], errors).items():
            text = " ".join(str(message) for message in cast(list[Any], messages)) if isinstance(messages, list) else str(messages)
            parts.append(f"{field}: {text}")
        return "; ".join(parts)
    return str(cast(dict[str, Any], body).get("message") or fallback)


class AmigosShare:
    """
    Amigos Share Club (ASC) is a Brazilian private tracker for movies, TV, anime, books, games and adult content.
    The site has no API: it is a Laravel/Inertia app, so pages carry their data as JSON and the
    upload form posts to the same endpoints the browser uses. Rules: https://amigos-share.club/regras
    """

    auth_type = "cookies"
    tracker = "AMIGOSSHARE"
    display_name = "Amigos Share Club"
    source_flag = "ASC"
    banned_groups: tuple[str, ...] = ()
    base_url = "https://amigos-share.club"
    upload_url = f"{base_url}/torrents/upload"
    torrent_url = f"{base_url}/torrents/"
    requests_url = f"{base_url}/pedidos"
    supported_categories = ("MOVIE", "TV", "BOOK", "GAME", "XXX")
    tracker_urls = ("amigos-share.club",)
    allows_bloated_audio = True

    # Rule 5.5 (all torrents), 5.12 (books) and 5.16 (adult videos).
    minimum_size = 20 * 1024 * 1024
    minimum_book_size = 1024 * 1024
    minimum_adult_size = 100 * 1024 * 1024
    upload_timeout = 180.0

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.tracker_config: dict[str, Any] = cast(dict[str, Any], config.get("TRACKERS", {}).get(self.tracker, {}))
        self.common = Common(config)
        self.cookie_validator = CookieValidator(config)
        self.session = httpx.AsyncClient(headers={"User-Agent": f"Upload-Assistant ({platform.system()} {platform.release()})"}, timeout=60.0)
        self.cookies_loaded = False
        self.form: Page | None = None

    # Session and pages

    async def load_cookies(self, meta: Meta) -> bool:
        if self.cookies_loaded:
            return True
        cookie_jar = await self.cookie_validator.load_session_cookies(meta, self.tracker)
        if cookie_jar is None:
            return False
        self.session.cookies = cast(Any, cookie_jar)
        self.cookies_loaded = True
        return True

    async def get_page(self, meta: Meta, url: str, params: dict[str, Any] | None = None) -> Page | None:
        """Fetch a page and return its Inertia data; a redirect to the login page means the cookies expired."""
        try:
            response = await self.session.get(url, params=params, headers={"Accept": "text/html"})
        except httpx.HTTPError as e:
            logger.info(f"{self.tracker}: Unable to open {url}: {e!r}", extra={"markup": False})
            return None
        page = parse_page(response.text) if response.status_code == 200 else None
        if page is None:
            if response.is_redirect and "/login" in response.headers.get("Location", ""):
                await self.cookie_validator.handle_validation_failure(meta, self.tracker, response.text)
            else:
                logger.info(f"{self.tracker}: Unexpected response from {url} (HTTP {response.status_code}).", extra={"markup": False})
        return page

    def xsrf_token(self) -> str:
        # Laravel checks the X-XSRF-TOKEN header against the URL-decoded XSRF-TOKEN cookie.
        token = ""
        for cookie in self.session.cookies.jar:
            if cookie.name == "XSRF-TOKEN" and cookie.domain.lstrip(".").endswith(urlparse(self.base_url).netloc):
                token = unquote(cookie.value or "")
        return token

    def ajax_headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "X-Requested-With": "XMLHttpRequest",
            "X-XSRF-TOKEN": self.xsrf_token(),
            "Origin": self.base_url,
            "Referer": self.upload_url,
        }

    async def post_json(self, path: str, payload: dict[str, Any]) -> tuple[int, Any]:
        response = await self.session.post(f"{self.base_url}{path}", json=payload, headers=self.ajax_headers())
        try:
            return response.status_code, response.json()
        except ValueError:
            return response.status_code, None

    async def load_form(self, meta: Meta) -> Page | None:
        """The upload page lists the categories and, per category, the fields and options it accepts."""
        if self.form is None and await self.load_cookies(meta):
            page = await self.get_page(meta, self.upload_url)
            if page and page.get("component") == "torrents/create":
                self.form = cast(Page, page.get("props") or {})
        return self.form

    async def validate_credentials(self, meta: Meta) -> bool:
        if not await self.load_form(meta):
            return False
        await self.cookie_validator.save_session_cookies(self.tracker, cast(Any, self.session.cookies.jar))
        return True

    # Category and fields

    def get_profile_key(self, meta: Meta) -> str:
        if meta.category == "BOOK":
            return "ebook"
        if meta.category == "GAME":
            return "jogos"
        if meta.category == "XXX":
            return "adultos"
        if meta.category == "MOVIE":
            # The form takes movie IMDb IDs only in the movie category, anime included.
            return "filmes"
        return "anime" if meta.anime else "series"

    async def get_category_id(self, meta: Meta) -> int:
        key = self.get_profile_key(meta)
        if key == "anime":
            return ANIME_SERIES_ID
        if key == "adultos":
            return HENTAI_ID if meta.anime else ADULT_ID
        if key == "ebook":
            kind = next((kind for kind in ("audiobook", "comic", "manga", "magazine") if getattr(meta, kind, False)), "book")
            return BOOK_CATEGORY_IDS[kind]
        if key == "jogos":
            platform_code = await game_platform(meta, tracker=self.tracker, supported=GAME_PLATFORM_IDS, default="PC")
            return GAME_PLATFORM_IDS.get(platform_code, GAME_PLATFORM_IDS["PC"])
        return CATEGORY_IDS[key]

    def get_profile(self, key: str) -> Profile | None:
        profiles = cast(dict[str, Any], (self.form or {}).get("profiles") or {})
        profile = profiles.get(key)
        return cast(Profile, profile) if isinstance(profile, dict) else None

    async def get_name(self, meta: Meta, lookup: Mapping[str, Any] | None = None) -> str:
        """The post title is the work's name (rule 6), not the release name, which stays in the files."""
        if meta.manual_name is not None:
            return meta.manual_name.strip()
        if meta.category == "BOOK":
            return " - ".join(part for part in (meta.author.strip(), meta.title.strip()) if part)
        if meta.category == "GAME":
            if (meta.platform or "PC").upper() in COMPUTER_PLATFORMS:
                release = (meta.tag or "").lstrip("-").strip()
                return f"{meta.title} [{release}]" if release else meta.title
            return f"{meta.title} [{meta.year}]" if meta.year else meta.title
        if meta.category == "XXX":
            return " - ".join(part for part in (str(meta.publisher or "").strip(), meta.title.strip()) if part)
        title = str((lookup or {}).get("title") or meta.title).strip()
        if meta.category == "TV":
            identifier = f"{meta.season or ''}{'' if meta.tv_pack else meta.episode or ''}".strip()
            return f"{title} - {identifier}" if identifier else title
        return title

    def file_paths(self, meta: Meta) -> list[Path]:
        return [Path(str(path)) for path in meta.filelist or []]

    def get_audio_channels(self, meta: Meta) -> str:
        """Portuguese audio decides the audio type (rule 16.12); without it, Portuguese subtitles mean "Legendado"."""
        # Names and codes ("Portuguese", "por", "pt-BR") all reduce to one language code.
        audio = {language_code(str(language)) or str(language).casefold() for language in meta.audio_languages or []}
        if "pt" in audio:
            if language_code(meta.original_language or "") == "pt":
                return "Nacional"
            others = audio - {"pt"}
            if len(others) > 1:
                return "Multi-Audio"
            return "Dual-Audio" if others else "Dublado"
        return "Legendado" if self.has_portuguese_subtitles(meta) else "Original"

    def has_portuguese_subtitles(self, meta: Meta) -> bool:
        subtitles = meta.subtitle_languages if isinstance(meta.subtitle_languages, list) else [meta.subtitle_languages or ""]
        return any(language_code(str(language)) == "pt" for language in subtitles)

    async def get_subtitle(self, meta: Meta, site_value: str | None) -> str:
        if site_value in ("embedded", "separate", "none"):
            return site_value
        if self.has_portuguese_subtitles(meta):
            return "embedded"
        return "separate" if await self.common.has_portuguese_external_subtitle(meta) else "none"

    def disc_quality(self, meta: Meta) -> str:
        if meta.is_disc == "BDMV":
            if meta.disctype in ("BD25", "BD50", "BD66", "BD100"):
                return meta.disctype
            size = float(meta.bdinfo.get("size") or 0)
            return "BD100" if size > 66 else "BD66" if size > 50 else "BD50" if size > 25 else "BD25"
        if meta.is_disc == "DVD":
            return meta.dvd_size if meta.dvd_size in ("DVD5", "DVD9") else "DVD"
        return "HD-DVD" if meta.is_disc == "HDDVD" else ""

    def local_suggestions(self, meta: Meta) -> dict[str, list[str]]:
        """Option names derived from the release, used where the site's own suggestions are missing."""
        suggestions: dict[str, list[str]] = {"audio_channels": [self.get_audio_channels(meta)]}
        if meta.is_disc:
            suggestions["resolution"] = [self.disc_quality(meta)]
            suggestions["container"] = ["M2TS" if meta.is_disc == "BDMV" else "VOB" if meta.is_disc == "DVD" else "Outros"]
        else:
            from_bluray = "bluray" in str(meta.source or "").casefold().replace("-", "")
            qualities = {
                "WEBDL": ["WEB-DL"],
                "WEBRIP": ["WEBRip", "WEB-RIP"],
                "REMUX": ["BD-REMUX", "Remux"] if from_bluray else ["Remux"],
                "ENCODE": ["BDRip", "Encode"] if from_bluray else ["Encode"],
                "HDTV": ["HDTV"],
                "DVDRIP": ["DVDrip"],
            }
            suggestions["resolution"] = qualities.get(str(meta.type or "").upper(), [])
            video = next((path for path in self.file_paths(meta) if path.suffix.casefold() in VIDEO_EXTENSIONS), None)
            suggestions["container"] = [video.suffix.lstrip(".").upper()] if video else []

        codec = f"{meta.video_codec} {meta.video_encode}".upper()
        hdr = str(meta.hdr or "").upper()
        if any(term in codec for term in ("HEVC", "265")):
            suggestions["video_codec"] = (["H265 - HDR 10", "H265 - HDR"] if "HDR10" in hdr else ["H265 - HDR"] if "HDR" in hdr else ["H265 - SDR"]) + ["H265", "HEVC"]
        elif any(term in codec for term in ("AVC", "264")):
            suggestions["video_codec"] = (["AVC-HDR"] if "HDR" in hdr else []) + ["H264", "AVC"]
        else:
            suggestions["video_codec"] = [term for term in ("AV1", "VC-1", "MPEG-2", "VP9", "XviD", "DivX") if term.upper() in codec]

        audio = str(meta.audio or "").upper()
        audio_codecs = (
            ("TRUEHD", "TrueHD"),
            ("DTS:X", "DTS-X"),
            ("DTS-HD MA", "DTS-HD-MA"),
            ("DTS-HD", "DTS-HD"),
            ("DTS", "DTS"),
            ("DD+", "E-AC-3"),
            ("DD", "AC3"),
            ("AAC", "AAC"),
            ("FLAC", "FLAC"),
            ("LPCM", "LPCM"),
            ("PCM", "PCM"),
            ("OPUS", "OPUS"),
            ("MP3", "MPEG Layer-3 (MP3)"),
        )
        suggestions["audio_codec"] = [name for term, name in audio_codecs if term in audio][:1]

        if language := portuguese_language_name(meta.original_language or ""):
            suggestions["language"] = [language]
        genres = [str(genre).strip().casefold() for genre in meta.genres or [] if str(genre).strip()]
        suggestions["genre"] = [GAME_GENRES.get(genre) or ENG_TO_PTBR_GENRE_MAP.get(genre) or genre for genre in genres]
        suggestions["dub_language"] = [self.get_dub_language(meta)]
        if meta.category == "BOOK":
            suffix = Path(str(meta.filelist[0] if meta.filelist else meta.path or "")).suffix.casefold()
            suggestions["container"] = [BOOK_CONTAINERS.get(suffix, "Outros")]
        return suggestions

    def get_dub_language(self, meta: Meta) -> str:
        """Content language of books, games and apps."""
        if meta.category == "BOOK":
            languages = [meta.book_language_iso or meta.book_language]
        elif isinstance(meta.languages, dict):
            languages = list(meta.languages)
        else:
            languages = [str(language) for language in meta.languages or []]
        codes = list(dict.fromkeys(code for code in (language_code(str(language)) for language in languages) if code))
        if len(codes) > 1 and "pt" in codes:
            return "Multilinguagem"
        return portuguese_language_name(codes[0]) if codes else "Outros"

    async def choose_attributes(self, meta: Meta, profile: Profile, chosen: dict[str, list[int]]) -> list[int] | None:
        """Fill what the site left out from the release, then ask for any required field still empty."""
        local = self.local_suggestions(meta)
        for attribute in profile.get("attributes", []):
            kind = str(attribute["type"])
            # Discs are not described by MediaInfo: their quality and container come from the disc itself.
            if meta.is_disc and kind in ("resolution", "container") and (found := find_options(attribute, local.get(kind, []))):
                chosen[kind] = found[:1]
            if kind not in chosen and (found := find_options(attribute, local.get(kind, []))):
                chosen[kind] = found if attribute.get("multiple") else found[:1]
            if kind in chosen or not attribute.get("required"):
                continue
            answer = await self.ask_attribute(meta, attribute)
            if not answer:
                return None
            chosen[kind] = answer
        return [option_id for ids in chosen.values() for option_id in ids]

    async def ask_attribute(self, meta: Meta, attribute: Mapping[str, Any]) -> list[int]:
        kind = str(attribute["type"])
        names = [str(option["name"]) for option in attribute.get("options", [])]
        multiple = bool(attribute.get("multiple"))
        answer = await ask(
            meta,
            Question(
                key=ATTRIBUTE_QUESTION_KEYS.get(kind, "amigosshare.genre"),
                kind="multi_choice" if multiple else "choice",
                prompt=f"{self.tracker}: Select {attribute.get('label', kind)}",
                title=f"{self.display_name}: {attribute.get('label', kind)}",
                choices=choices_from(names),
                hint="The site and the release metadata did not fill in this required field.",
                summary={"Tracker": self.tracker, "Release": meta.name or meta.title},
                tracker=self.tracker,
            ),
        )
        if not answer:
            return []
        return find_options(attribute, answer if isinstance(answer, list) else [str(answer)])

    # Site helpers

    async def lookup_imdb(self, meta: Meta, profile_key: str) -> dict[str, Any] | None:
        """The site's IMDb lookup returns its title convention, genres, language, cover and a description."""
        status, body = await self.post_json("/torrents/lookup", {"imdb_id": meta.imdb_tt})
        if status != 200 or not isinstance(body, dict):
            logger.info(f"{self.tracker}: IMDb lookup failed: {error_text(body, f'HTTP {status}')}", extra={"markup": False})
            return None
        lookup = cast(dict[str, Any], body)
        if (profile_key == "filmes") != (lookup.get("type") == "movie"):
            kind = "a movie" if lookup.get("type") == "movie" else "a series or episode"
            logger.info(f"{self.tracker}: {meta.imdb_tt} is {kind} on IMDb, which does not match the {meta.category} category.", extra={"markup": False})
            return None
        return lookup

    async def read_mediainfo(self, text: str) -> dict[str, Any] | None:
        """The site reads MediaInfo with the parser its moderators use and suggests the matching options."""
        if not text:
            return None
        status, body = await self.post_json("/torrents/mediainfo", {"mediainfo": text})
        if status != 200 or not isinstance(body, dict):
            logger.info(f"{self.tracker}: The site could not read the MediaInfo: {error_text(body, f'HTTP {status}')}", extra={"markup": False})
            return None
        return cast(dict[str, Any], body)

    async def get_mediainfo_text(self, meta: Meta) -> str:
        if meta.is_disc == "BDMV":
            return await self.common.get_bdmv_mediainfo(meta)
        mediainfo_path = Path(meta.base_dir) / "tmp" / meta.uuid / "MEDIAINFO_CLEANPATH.txt"
        if not mediainfo_path.is_file():
            return ""
        async with aiofiles.open(mediainfo_path, encoding="utf-8") as mediainfo_file:
            return await mediainfo_file.read()

    async def get_bdinfo_summary(self, meta: Meta) -> str:
        summary_path = Path(meta.base_dir) / "tmp" / meta.uuid / "BD_SUMMARY_00.txt"
        if meta.is_disc != "BDMV" or not summary_path.is_file():
            return ""
        async with aiofiles.open(summary_path, encoding="utf-8") as summary_file:
            return (await summary_file.read()).strip()

    async def get_screenshots(self, meta: Meta, limit: int) -> list[tuple[str, bytes, str]]:
        """Local screenshots, or the release's remote images (game screenshots) when none were taken."""
        max_bytes = int(cast(dict[str, Any], (self.form or {}).get("limits") or {}).get("imageKb") or 51200) * 1024
        images: list[tuple[str, bytes, str]] = []
        for path in manifest_files(meta.base_dir, meta.uuid, "main"):
            if len(images) >= limit:
                return images
            content_type = IMAGE_TYPES.get(path.suffix.casefold())
            if content_type and 0 < path.stat().st_size <= max_bytes:
                async with aiofiles.open(path, "rb") as image_file:
                    images.append((path.name, await image_file.read(), content_type))
        if images:
            return images

        for index, image in enumerate(meta.image_list or []):
            if len(images) >= limit:
                break
            # Checks every redirect target and stops reading at the artwork size limit.
            content = await download_public_image(str(image.get("raw_url") or image.get("img_url") or ""))
            if not content:
                continue
            with Image.open(BytesIO(content)) as decoded:
                extension = REMOTE_IMAGE_FORMATS.get(str(decoded.format))
            if extension:
                images.append((f"screenshot_{index + 1}{extension}", content, IMAGE_TYPES[extension]))
        return images

    async def upload_screenshots(self, images: list[tuple[str, bytes, str]]) -> list[str]:
        """Screenshots are stored by the site before the form is sent; the form lists their paths."""
        paths: list[str] = []
        for name, content, content_type in images:
            for _attempt in range(5):
                response = await self.session.post(f"{self.base_url}/torrents/screenshots", files={"image": (name, content, content_type)}, headers=self.ajax_headers())
                if response.status_code != 429:
                    break
                await asyncio.sleep(retry_after_seconds(response.headers.get("Retry-After")))
            try:
                body: Any = response.json()
            except ValueError:
                body = None
            path = cast(dict[str, Any], body).get("path") if isinstance(body, dict) else None
            if response.is_success and path:
                paths.append(str(path))
            else:
                logger.info(f"{self.tracker}: Screenshot {name} was not accepted: {error_text(body, f'HTTP {response.status_code}')}", extra={"markup": False})
        return paths

    async def get_cover_file(self, meta: Meta) -> tuple[str, bytes, str] | None:
        path = Path(meta.artwork_path) if meta.artwork_path else None
        if path is None or path.suffix.casefold() not in IMAGE_TYPES or not await asyncio.to_thread(is_valid_cover_image, path):
            return None
        async with aiofiles.open(path, "rb") as cover_file:
            return (path.name, await cover_file.read(), IMAGE_TYPES[path.suffix.casefold()])

    def signature(self, meta: Meta) -> str:
        return f"[center][url=https://github.com/wastaken7/Upload-Assistant][size=13]Compartilhado com {meta.ua_name} {meta.current_version} (fork)[/size][/url][/center]"

    async def build_description(self, meta: Meta) -> str:
        """Videos need no description of their own (rule 6.7); other categories need one in Portuguese (6.8)."""
        builder = DescriptionBuilder(self.tracker, self.config, "pt-BR")
        parts: list[str] = []
        if meta.category == "BOOK":
            parts.append(builder._build_book_desc_section(meta, table=False))
        elif meta.category == "GAME":
            parts.append(builder._build_game_desc_section(meta, table=False))

        user_description = get_base_description(meta).strip() or (await builder.get_user_description(meta)).strip()
        if user_description:
            parts.append(user_description)
        if bdinfo := await self.get_bdinfo_summary(meta):
            parts.append(f"[spoiler=BDInfo][code]{bdinfo}[/code][/spoiler]")
        parts.append(self.signature(meta))
        return format_description("\n\n".join(part for part in parts if part.strip()), self.base_url)

    # Upload form

    async def get_data(self, meta: Meta) -> dict[str, Any] | None:
        """Build the upload form, asking the site for the IMDb data and the MediaInfo reading; None when it cannot be completed."""
        tracker_status = meta.tracker_status.setdefault(self.tracker, {})
        if not await self.load_form(meta):
            tracker_status["status_message"] = "data error - Could not open the upload page; check the cookies."
            return None
        profile_key = self.get_profile_key(meta)
        profile = self.get_profile(profile_key)
        if profile is None:
            tracker_status["status_message"] = f"data error - The upload page has no '{profile_key}' category."
            return None

        lookup = await self.lookup_imdb(meta, profile_key) if profile.get("imdb") and meta.imdb_tt else None
        if profile.get("imdb") and not lookup:
            tracker_status["status_message"] = "data error - The site's IMDb lookup failed; every movie and series must be linked to IMDb (rule 6.3)."
            return None

        mediainfo_text = await self.get_mediainfo_text(meta) if profile.get("mediainfo") or meta.category == "XXX" else ""
        if profile.get("mediainfo") and not mediainfo_text:
            tracker_status["status_message"] = "data error - MediaInfo is required."
            return None
        mediainfo = await self.read_mediainfo(mediainfo_text)
        if mediainfo and mediainfo.get("report"):
            mediainfo_text = str(mediainfo["report"])

        attribute_ids = await self.choose_attributes(meta, profile, site_choices(profile, lookup, mediainfo))
        if attribute_ids is None:
            tracker_status["status_message"] = "data error - A required characteristic was not chosen."
            return None

        year = (lookup or {}).get("year") or meta.year
        anonymous = bool(meta.anon) or bool(self.tracker_config.get("anon", False))
        data: dict[str, Any] = {
            "category_id": str(await self.get_category_id(meta)),
            "name": await self.get_name(meta, lookup),
            "year": str(year or ""),
            "anonymous": "1" if anonymous else "0",
            "description": await self.build_description(meta),
            "attribute_ids[]": [str(option_id) for option_id in attribute_ids],
        }
        if lookup:
            data["imdb_id"] = str(lookup.get("imdbId") or meta.imdb_tt)
            if cover := cast(dict[str, Any], lookup.get("cover") or {}).get("path"):
                data["cover_path"] = str(cover)
        if mediainfo_text and (profile.get("mediainfo") or mediainfo):
            data["mediainfo"] = mediainfo_text
        if profile.get("dimensions"):
            width = (mediainfo or {}).get("width") or meta.video_width
            height = (mediainfo or {}).get("height") or meta.video_height
            if width and height:
                data["width"], data["height"] = str(width), str(height)
        if profile.get("trailer") and meta.youtube:
            data["trailer_url"] = str(meta.youtube)
        # The form only sends the subtitle when the audio is not dubbed-only or original.
        if profile.get("subtitle") and set(attribute_ids) & {int(option_id) for option_id in profile.get("subtitleWhen", [])}:
            data["subtitle"] = await self.get_subtitle(meta, cast(str | None, (mediainfo or {}).get("subtitle")))
        return data

    async def get_payload_preview(self, meta: Meta) -> payload_preview.TrackerPreview:
        """The upload form as it is known before the site is asked for IMDb and MediaInfo data."""
        video = meta.category in ("MOVIE", "TV")
        anonymous = bool(meta.anon) or bool(self.tracker_config.get("anon", False))
        category_id = await payload_preview.unless_asked(self.get_category_id(meta))
        data: dict[str, Any] = {
            "category_id": category_id if isinstance(category_id, payload_preview.Later) else str(category_id),
            "name": payload_preview.Later(payload_preview.FROM_TRACKER_NOTE) if video and meta.manual_name is None else await self.get_name(meta),
            "year": str(meta.year or ""),
            "anonymous": "1" if anonymous else "0",
        }
        if video:
            data["imdb_id"] = meta.imdb_tt
            if meta.youtube:
                data["trailer_url"] = str(meta.youtube)
        specs = {
            "category_id": payload_preview.readonly("Category"),
            "name": payload_preview.text("Name"),
            "year": payload_preview.text("Year", numeric=True),
            "anonymous": payload_preview.flag("Anonymous"),
            "imdb_id": payload_preview.readonly("IMDb"),
            "trailer_url": payload_preview.text("Trailer (YouTube)"),
        }
        deferred = {
            "attribute_ids[]": "Chosen from the site's IMDb and MediaInfo reading at upload time",
            "description": payload_preview.DESCRIPTION_NOTE,
            "screenshot_paths[]": payload_preview.SCREENSHOTS_NOTE,
        }
        return payload_preview.describe(self.tracker, data, specs, deferred=deferred)

    # Checks, duplicates and requests

    def rules(self, meta: Meta) -> list[str]:
        warnings: list[str] = []
        files = self.file_paths(meta)
        if meta.source_size and meta.source_size < self.minimum_size:
            warnings.append("Torrents smaller than 20 MB are only approved when the staff finds them relevant (rule 5.5).")
        if meta.category in ("MOVIE", "TV") and not meta.is_disc:
            extra = sorted({path.suffix.casefold() or path.name for path in files if path.suffix.casefold() not in VIDEO_EXTENSIONS | SUBTITLE_EXTENSIONS})
            if extra:
                warnings.append(f"Video torrents may only hold the video and .srt/.ass subtitles; found: {', '.join(extra)} (rule 15.2.16).")
            if str(meta.type or "").upper() in ("ENCODE", "WEBRIP") and "AV1" in f"{meta.video_codec} {meta.video_encode}".upper():
                warnings.append("AV1 encodes are not accepted (rule 15.2.4).")
            if str(meta.type or "").upper() == "REMUX" and self.get_audio_channels(meta) not in ("Dual-Audio", "Multi-Audio", "Nacional"):
                warnings.append("REMUX is only accepted with the official Brazilian Portuguese dub (DUAL or MULTi), unless it never had one (rule 15.2.6).")
        if meta.category != "GAME" and (archives := sorted({path.suffix.casefold() for path in files if path.suffix.casefold() in ARCHIVE_EXTENSIONS})):
            warnings.append(f"Archived files are only allowed in games; found: {', '.join(archives)} (rule 15.1.6).")
        return warnings

    async def get_additional_checks(self, meta: Meta) -> bool:
        if meta.category in ("MOVIE", "TV") and not meta.imdb_id:
            logger.info(f"{self.tracker}: [bold red]Every movie and series must be linked to IMDb (rule 6.3).[/bold red]")
            return False
        if meta.category == "BOOK" and meta.source_size <= self.minimum_book_size:
            logger.info(f"{self.tracker}: [bold red]Books, manuals and e-books must be larger than 1 MB (rule 5.12).[/bold red]")
            return False
        if meta.category == "XXX" and meta.source_size < self.minimum_adult_size:
            logger.info(f"{self.tracker}: [bold red]Adult videos must be at least 100 MB (rule 5.16).[/bold red]")
            return False
        passed = True
        if self.tracker_config.get("check_for_rules", True) and (warnings := self.rules(meta)):
            logger.info(f"{self.tracker}: [red]Rule check returned the following warning(s):[/red]\n\n" + "\n\n".join(warnings))
            passed = False
        if meta.category in ("MOVIE", "TV"):
            if not meta.language_checked:
                await languages_manager.process_desc_language(meta, tracker=self.tracker)
            # Foreign content needs Brazilian Portuguese audio or subtitles (rule 15.2.11).
            if not await self.common.check_portuguese_video_requirements(meta, self.tracker):
                passed = False
        return passed

    def search_params(self, meta: Meta) -> dict[str, str]:
        key = self.get_profile_key(meta)
        if key in ("filmes", "series", "anime"):
            query = meta.imdb_tt or meta.title
        elif key == "ebook":
            query = meta.title
        else:
            query = meta.title or str(meta.name)
        return {"q": query, "category": str(CATEGORY_IDS[key])}

    async def search_existing(self, meta: Meta) -> list[dict[str, Any]]:
        if not await self.load_cookies(meta):
            meta.skipping = self.tracker
            return []
        duplicates: list[dict[str, Any]] = []
        params: dict[str, Any] = self.search_params(meta)
        # Keep the search to a few pages so a broad title does not crawl the site.
        for page_number in range(1, 4):
            page = await self.get_page(meta, f"{self.base_url}/torrents", params={**params, "page": page_number})
            if page is None:
                if page_number == 1:
                    meta.skipping = self.tracker
                break
            torrents = cast(dict[str, Any], cast(dict[str, Any], page.get("props") or {}).get("torrents") or {})
            for item in cast(list[dict[str, Any]], torrents.get("data") or []):
                # Titles are the work's name, so the badges (resolution, source, codec, HDR) stand in for the release name.
                badges = [cast(dict[str, Any], badge) for badge in item.get("badges") or [] if isinstance(badge, dict)]
                labels = ["2160p" if str(badge.get("label", "")).upper() == "4K" else str(badge.get("label", "")) for badge in badges]
                duplicates.append(
                    {
                        "name": " ".join(str(part) for part in (item.get("name"), item.get("year"), *labels) if part),
                        "size": item.get("size"),
                        "link": f"{self.torrent_url}{item.get('id')}",
                        "id": item.get("id"),
                        "has_resolution": any(badge.get("kind") == "resolution" for badge in badges),
                    }
                )
            if not torrents.get("next_page_url"):
                break
            await asyncio.sleep(1)

        # Without a resolution the duplicate check would drop a video result, so read it from the torrent's files.
        # Video searches are by IMDb ID, which keeps the number of results (and of these lookups) small.
        lookups = 0
        for duplicate in duplicates:
            if duplicate.pop("has_resolution") or meta.category not in ("MOVIE", "TV"):
                continue
            if lookups:
                await asyncio.sleep(1)
            lookups += 1
            files, file_count, resolution = await self.get_release_files(meta, duplicate["id"])
            if files:
                duplicate.update({"files": files, "file_count": file_count})
            if resolution:
                duplicate["name"] = f"{duplicate['name']} {resolution}"
        return duplicates

    async def get_release_files(self, meta: Meta, torrent_id: Any) -> tuple[list[str], int, str]:
        """File names, file count and resolution from a torrent's page."""
        page = await self.get_page(meta, f"{self.torrent_url}{torrent_id}")
        props = cast(dict[str, Any], (page or {}).get("props") or {})
        listing = cast(dict[str, Any], props.get("files") or {})
        files = [str(item.get("path", "")) for item in cast(list[dict[str, Any]], listing.get("data") or []) if item.get("path")]
        file_count = int(props.get("filesTotal") or len(files))
        for name in files:
            if match := re.search(r"(?<![0-9])(2160|1080|720|576|480)[pi](?![0-9])", name):
                return files, file_count, f"{match.group(1)}p"
        for spec in cast(list[dict[str, Any]], props.get("specs") or []):
            if normalize_option(str(spec.get("label", ""))) == "resolucao":
                return files, file_count, resolution_from_dimensions(str(spec.get("value", "")))
        return files, file_count, ""

    async def get_requests(self, meta: Meta) -> list[dict[str, str]]:
        if not self.config["DEFAULT"].get("search_requests", False) and not meta.search_requests:
            return []
        try:
            if not await self.load_cookies(meta):
                return []
            page = await self.get_page(meta, self.requests_url, params={"q": meta.title, "status": "open"})
            requests = cast(dict[str, Any], cast(dict[str, Any], (page or {}).get("props") or {}).get("requests") or {})
            results = [
                {"Name": str(item.get("title", "")), "Reward": str(item.get("bountyTotal", "")), "Link": f"{self.requests_url}/{item.get('id')}"}
                for item in cast(list[dict[str, Any]], requests.get("data") or [])
            ]
        except httpx.HTTPError as e:
            logger.info(f"{self.tracker}: Unable to search requests: {e}", extra={"markup": False})
            return []
        if results:
            message = f"\n{self.tracker}: [bold yellow]Seu upload pode atender o(s) seguinte(s) pedido(s), confira:[/bold yellow]\n\n"
            for result in results:
                message += f"[bold green]Nome:[/bold green] {result['Name']}\n[bold green]Recompensa:[/bold green] {result['Reward']}\n[bold green]Link:[/bold green] {result['Link']}\n\n"
            logger.info(message)
        return results

    # Upload

    async def save_failure(self, meta: Meta, html: str, name: str) -> str:
        failure_path = Path(meta.base_dir) / "tmp" / meta.uuid / f"[{self.tracker}]{name}.html"
        failure_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(failure_path, "w", encoding="utf-8") as failure_file:
            await failure_file.write(html)
        return str(failure_path)

    async def send_form(self, meta: Meta, data: dict[str, Any], files: dict[str, tuple[str, bytes, str]]) -> str:
        """Post the form and return the new torrent ID; a failure is recorded in the tracker status."""
        tracker_status = meta.tracker_status[self.tracker]
        headers = self.ajax_headers()
        response = await self.session.post(f"{self.base_url}/torrents", data=data, files=files, headers=headers, timeout=self.upload_timeout)
        location = response.headers.get("Location", "")
        if response.is_redirect and (match := re.search(r"/torrents/(\d+)(?:[/?#]|$)", location)):
            return match.group(1)

        if response.status_code == 422:
            try:
                body: Any = response.json()
            except ValueError:
                body = None
            tracker_status["status_message"] = f"data error - {error_text(body, 'The site refused the upload.')}"
            return ""
        if response.status_code == 419:
            tracker_status["status_message"] = "data error - The session expired (HTTP 419). Export the cookies again."
            return ""

        html = response.text
        if response.is_redirect and location:
            # Validation errors of a non-JSON request come back on the upload page.
            page_response = await self.session.get(urljoin(self.base_url, location), headers={"Accept": "text/html"})
            html = page_response.text
            if (page := parse_page(html)) and (errors := cast(dict[str, Any], page.get("props") or {}).get("errors")):
                tracker_status["status_message"] = f"data error - {error_text({'errors': errors}, 'The site refused the upload.')}"
                return ""
        failure_path = await self.save_failure(meta, html, "FailedUpload")
        tracker_status["status_message"] = f"data error - Unexpected response (HTTP {response.status_code}). The response was saved to '{failure_path}'."
        return ""

    async def upload(self, meta: Meta) -> bool:
        tracker_status = meta.tracker_status.setdefault(self.tracker, {})
        data = await self.get_data(meta)
        if data is None or getattr(meta, "skipping", None) == self.tracker:
            return False
        data = payload_preview.apply_payload_edits(meta, self.tracker, data)
        profile = self.get_profile(self.get_profile_key(meta)) or {}

        cover = None if data.get("cover_path") else await self.get_cover_file(meta)
        if profile.get("coverRequired") and not data.get("cover_path") and cover is None:
            tracker_status["status_message"] = "data error - A cover is required; set one with --poster."
            return False
        minimum, maximum = int(profile.get("screenshotsMin") or 0), int(profile.get("screenshotsMax") or 6)
        images = await self.get_screenshots(meta, maximum)
        if len(images) < minimum:
            tracker_status["status_message"] = f"data error - At least {minimum} screenshot(s) are required; found {len(images)}."
            return False

        if meta.debug:
            logger.info(f"{self.tracker}: Request Data:")
            logger.info(Redaction.redact_private_info({**data, "mediainfo": "...[DEBUG MODE]" if data.get("mediainfo") else ""}))
            logger.info(f"{self.tracker}: {len(images)} screenshot(s) and {'a cover file' if cover else 'no cover file'} would be uploaded.")
            tracker_status["status_message"] = "Debug mode enabled, not uploading."
            await self.common.create_torrent_for_upload(meta, f"{self.tracker}_DEBUG", f"{self.tracker}_DEBUG", announce_url="https://fake.tracker")
            return True

        screenshot_paths = await self.upload_screenshots(images)
        if len(screenshot_paths) < minimum:
            tracker_status["status_message"] = f"data error - Only {len(screenshot_paths)} of {len(images)} screenshot(s) were accepted by the site."
            return False
        data["screenshot_paths[]"] = screenshot_paths

        # A private torrent keeps its info hash; the site only rewrites public ones.
        await self.common.create_torrent_for_upload(meta, self.tracker, self.source_flag)
        torrent_path = Path(meta.base_dir) / "tmp" / meta.uuid / f"[{self.tracker}].torrent"
        async with aiofiles.open(torrent_path, "rb") as torrent_file:
            torrent_bytes = await torrent_file.read()
        files = {"torrent": (f"{data['name']}.torrent", torrent_bytes, "application/x-bittorrent")}
        if cover:
            files["cover"] = cover

        try:
            torrent_id = await self.send_form(meta, data, files)
        except httpx.TimeoutException:
            tracker_status["status_message"] = "data error - The upload timed out; check the waiting queue on the site before retrying."
            return False
        if not torrent_id:
            return False

        tracker_status["torrent_id"] = torrent_id
        torrent_url = f"{self.torrent_url}{torrent_id}"
        user_agent = {"User-Agent": str(self.session.headers.get("User-Agent", ""))}
        if not await self.common.download_tracker_torrent(meta, self.tracker, headers=user_agent, downurl=f"{torrent_url}/download"):
            # The announce URL is required (trackersetup skips the tracker without it), so the local torrent can be seeded.
            tracker_status["status_message"] = f"Uploaded to {torrent_url}, but the site's .torrent could not be downloaded; seeding the local private torrent."
            return True
        tracker_status["status_message"] = f"{self.tracker} torrent uploaded successfully: {torrent_url}"
        return True
