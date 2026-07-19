import asyncio
import contextlib
import gettext
import json
import mimetypes
import platform
import re
import shutil
import zipfile
from pathlib import Path
from typing import Any, ClassVar, cast

import aiofiles
import httpx
import langcodes
import pycountry
from bs4 import BeautifulSoup

from cogs.redaction import Redaction
from src.console import logger
from src.cookie_auth import CookieValidator
from src.genre_map import ENG_TO_PTBR_GENRE_MAP
from src.languages import languages_manager
from src.meta import Meta
from src.trackers.common import Common

Config = dict[str, Any]


class MakingOff:
    """
    Making Off is a BRAZILIAN Private Torrent Tracker for MOVIES / TV / GENERAL
    """

    auth_type = "cookies"
    tracker = "MAKINGOFF"
    display_name = "MakingOff"
    source_flag = ""
    base_url = "https://www.makingoff.org"
    banned_groups: tuple[str, ...] = ()
    index_url = "https://www.makingoff.org/"
    torrent_url = ""
    supported_categories = ("MOVIE",)
    allows_bloated_audio = True
    tmdb_localization_requirements: ClassVar = {
        "pt-BR": {
            "main": "credits,translations",
        },
        "en-US": {
            "main": "translations",
        },
    }

    # HMediaInfo constants
    VIDEO_CODEC_MAP: ClassVar[list[tuple[list[str], str]]] = [
        (["avc", "h.264", "h264"], "H.264"),
        (["hevc", "h.265", "h265"], "H.265 (HEVC)"),
        (["av1"], "AV1"),
        (["vp9"], "VP9"),
        (["xvid"], "XviD"),
        (["divx"], "DivX"),
        (["mpeg-4"], "MPEG-4"),
        (["mpeg"], "MPEG-2"),
    ]

    AUDIO_CODEC_MAP: ClassVar[list[tuple[list[str], str]]] = [
        (["aac"], "AAC"),
        (["e-ac-3", "eac3"], "E-AC-3 (Dolby Digital Plus)"),
        (["ac-3", "ac3"], "AC-3 (Dolby Digital)"),
        (["truehd"], "Dolby TrueHD"),
        (["dts"], "DTS"),
        (["mp3", "mpeg audio"], "MP3"),
        (["flac"], "FLAC"),
        (["opus"], "Opus"),
    ]

    def __init__(self, config: Config):
        self.config = config
        self.common = Common(config)
        self.cookie_validator = CookieValidator(config)

        # Cache for the resolved PT-BR display title, keyed by meta.uuid.
        self._display_title_cache: dict[str, str] = {}
        self._csrf_token: str = ""

        tracker_config = dict(dict(config.get("TRACKERS", {})).get("MAKINGOFF", {}))
        public_trackers_raw = tracker_config.get("trackers", [])
        if isinstance(public_trackers_raw, str):
            self._public_trackers: list[str] = [t.strip() for t in public_trackers_raw.splitlines() if t.strip()]
        else:
            self._public_trackers = list(public_trackers_raw)

        self.session = httpx.AsyncClient(
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
                "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7"),
                "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
                "Accept-Encoding": "gzip, deflate",
                "Sec-Ch-Ua": '"Google Chrome";v="149", "Chromium";v="149", "Not)A;Brand";v="24"',
                "Sec-Ch-Ua-Mobile": "?0",
                "Sec-Ch-Ua-Platform": '"Windows"',
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1",
            },
            timeout=60.0,
            follow_redirects=True,
        )

    def _normalize_codec(self, fmt: str, mapping: list[tuple[list[str], str]]) -> str:
        f = fmt.lower()
        for keys, label in mapping:
            if any(k in f for k in keys):
                return label
        return fmt

    def _mediainfo_video_codec(self, meta: Meta, video_track: dict[str, Any]) -> str:
        """Return the normalised video codec label."""
        fmt = video_track.get("Format", "").strip()
        if not fmt:
            fmt = (meta.video_encode or meta.video_codec or "").strip()
        return self._normalize_codec(fmt, self.VIDEO_CODEC_MAP) if fmt else ""

    def _mediainfo_audio_codec(self, meta: Meta, audio_track: dict[str, Any]) -> str:
        """Return the normalised audio codec label."""
        fmt = audio_track.get("Format", "").strip()
        if not fmt:
            fmt = (meta.audio or "").strip()
        return self._normalize_codec(fmt, self.AUDIO_CODEC_MAP) if fmt else ""

    def _mediainfo_container(self, general_track: dict[str, Any], fallback: str = "") -> str:
        """Return the container format, preferring mediainfo General track."""
        fmt = (general_track.get("Format", "") or "").lower()
        if "matroska" in fmt:
            return "MKV"
        if "avi" in fmt:
            return "AVI"
        if "mp4" in fmt or "mpeg-4" in fmt:
            return "MP4"
        if fmt:
            return general_track.get("Format", fallback)
        return fallback

    def _mediainfo_filesize(self, meta: Meta) -> str:
        """Return a human-readable file size (GB or MB)."""
        try:
            gb = meta.source_size / 1024**3
            return f"{gb:.2f} GB" if gb >= 1 else f"{meta.source_size / 1024**2:.0f} MB"
        except TypeError, ValueError:
            return "N/A"

    def _mediainfo_duration(self, general_track: dict[str, Any], video_track: dict[str, Any]) -> str:
        """Return duration in minutes from mediainfo General track."""
        raw = general_track.get("Duration") or video_track.get("Duration") or ""
        try:
            return str(int(float(raw)) // 60)
        except TypeError, ValueError:
            return ""

    def _aspect_ratio(self, width: Any, height: Any) -> str:
        """Return an aspect ratio category from video dimensions matching MakingOff options."""
        try:
            r = int(width) / int(height)
            if r < 1.45:
                return "Tela Cheia (4x3)"
            if r < 1.85:
                return "Widescreen (16x9)"
            return "Scope (2.35:1)"
        except TypeError, ValueError, ZeroDivisionError:
            return "Widescreen (16x9)"

    def _html_encode(self, text: str) -> str:
        """Return the text unchanged (XenForo supports native UTF-8)."""
        return text

    def _screen_rows(self, image_urls: list[str]) -> str:
        """Pair screenshot URLs into two-column BBCode rows matching makingoff structure."""
        scr = [image_urls[i] if i < len(image_urls) else "" for i in range(max(4, len(image_urls)))]

        # Row 4 already opened in _build_bbcode with [tr][poster]...[tableScreen]Screenshots[/tableScreen]
        cg = f"[screenLeft][screenIma]{scr[0]}[/screenIma][/screenLeft][screenRight][screenIma]{scr[1]}[/screenIma][/screenRight][/tr]"
        cg += f"[tr][screenLeft][screenIma]{scr[2]}[/screenIma][/screenLeft][screenRight][screenIma]{scr[3]}[/screenIma][/screenRight]"

        # Check if we have additional screens (5 & 6)
        if len(scr) >= 5 and scr[4]:
            scr5 = scr[4]
            scr6 = scr[5] if len(scr) > 5 else ""
            cg += f"[/tr][tr][screenLeft][screenIma]{scr5}[/screenIma][/screenLeft][screenRight][screenIma]{scr6}[/screenIma][/screenRight]"
            # Check if we have 7 & 8
            if len(scr) >= 7 and scr[6]:
                scr7 = scr[6]
                scr8 = scr[7] if len(scr) > 7 else ""
                cg += f"[/tr][tr][screenLeft][screenIma]{scr7}[/screenIma][/screenLeft][screenRight][screenIma]{scr8}[/screenIma][/screenRight]"

        cg += "[closeTab][/closeTab][/tr]"
        return cg

    def _get_ffmpeg_path(self, meta: Meta) -> str:

        base_dir = getattr(meta, "base_dir", "") or str(Path(__file__).parent.parent.parent)

        if platform.system() == "Linux":
            ff_bin_dir = Path(base_dir) / "bin" / "ffmpeg"
            machine = platform.machine().lower()
            if machine in ("x86_64", "amd64"):
                arch = "amd"
            elif machine in ("aarch64", "arm64"):
                arch = "arm"
            else:
                arch = None
            if arch:
                candidate = Path(ff_bin_dir) / arch / "ffmpeg"
                if candidate.exists():
                    return str(candidate)
        elif platform.system() == "Windows":
            candidate = Path(base_dir) / "bin" / "ffmpeg.exe"
            if candidate.exists():
                return str(candidate)

        return "ffmpeg"

    def _is_subtitle_in_portuguese(self, file_path: str) -> bool:
        # Common Portuguese words
        pt_words = {"que", "não", "uma", "com", "mais", "para", "está", "estou", "você", "como", "mas", "bem", "ele", "ela", "vocês", "estavam", "fazer"}
        # Common English words
        en_words = {"the", "and", "you", "that", "was", "for", "are", "with", "have", "this", "what", "they", "here", "know"}

        encodings = ["utf-8", "latin-1", "cp1252", "utf-16"]
        content = ""
        for enc in encodings:
            try:
                with Path(file_path).open(encoding=enc, errors="ignore") as f:
                    content = f.read(4096).lower()
                if content:
                    break
            except Exception as e:
                logger.debug(f"Failed to read file {file_path} with encoding {enc}: {e}")
                continue

        if not content:
            return False

        words = re.findall(r"\b\w+\b", content)
        pt_count = sum(1 for w in words if w in pt_words)
        en_count = sum(1 for w in words if w in en_words)
        return pt_count > en_count

    async def _get_portuguese_subtitles(self, meta: Meta) -> list[str]:
        """
        Find and extract Portuguese subtitles for this release.

        1. Checks external files (meta.subtitle_files) and matches files that contain
           Portuguese keywords in filename or content.
        2. Checks embedded tracks in the video and extracts them if they are Portuguese.

        Returns:
            list[str]: Paths to Portuguese subtitle files to upload.
        """
        pt_subs: list[str] = []

        # 1. Check external subtitle files
        for sub_file in getattr(meta, "subtitle_files", []):
            if not Path(sub_file).exists():
                continue
            name_lower = Path(sub_file).name.lower()
            if any(term in name_lower for term in (".pt", ".pt-br", ".por", "portuguese", "ptbr", "pt_br")):
                pt_subs.append(sub_file)
                logger.info(f"[cyan]{self.tracker}:[/cyan] [green]Found external Portuguese subtitle:[/green] {Path(sub_file).name}")
            elif self._is_subtitle_in_portuguese(sub_file):
                pt_subs.append(sub_file)
                logger.info(f"[cyan]{self.tracker}:[/cyan] [green]Found external Portuguese subtitle (content-matched):[/green] {Path(sub_file).name}")

        # 2. Check embedded subtitle tracks (if it is a file upload, not a BD/DVD folder/disc structure)
        if not meta.is_disc and meta.filelist and len(meta.filelist) > 0:
            video_file = meta.filelist[0]
            if Path(video_file).is_file() and video_file.lower().endswith((".mkv", ".mp4", ".m4v")):
                tracks = meta.mediainfo.get("media", {}).get("track", [])
                text_tracks = [t for t in tracks if t.get("@type") == "Text"]

                for idx, track in enumerate(text_tracks):
                    lang = str(track.get("Language", "")).lower()
                    title = str(track.get("Title", "")).lower()

                    is_pt = any(term in lang for term in ("portuguese", "pt", "por")) or any(
                        term in title for term in ("portuguese", "português", "pt-br", "ptbr", "pt_br", "pt-pt", "ptpt")
                    )

                    if is_pt:
                        # Extract it
                        fmt = str(track.get("Format", "")).upper()
                        ext = ".srt"
                        if "ASS" in fmt or "SSA" in fmt:
                            ext = ".ass"
                        elif "VTT" in fmt:
                            ext = ".vtt"
                        elif "PGS" in fmt or "SUP" in fmt:
                            ext = ".sup"

                        temp_dir = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}"
                        Path(temp_dir).mkdir(parents=True, exist_ok=True)
                        release_name = meta.basename_no_ext or meta.name or meta.uuid
                        release_filename = release_name.replace(" ", ".")

                        title_slug = ""
                        if track.get("Title"):
                            title_clean = re.sub(r"[^a-zA-Z0-9_-]", "_", str(track.get("Title")))
                            title_slug = f"-{title_clean}"

                        output_name = f"{release_filename}.pt-{idx}{title_slug}{ext}"
                        output_path = str(Path(temp_dir) / output_name)

                        ffmpeg_path = self._get_ffmpeg_path(meta)
                        cmd: list[str] = [ffmpeg_path, "-y", "-i", video_file, "-map", f"0:s:{idx}", output_path]

                        logger.info(f"[cyan]{self.tracker}:[/cyan] Extracting embedded Portuguese subtitle (stream {idx}) to {output_name}...")
                        try:
                            process = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                            _, stderr = await process.communicate()
                            if process.returncode == 0 and Path(output_path).exists() and Path(output_path).stat().st_size > 0:
                                pt_subs.append(output_path)
                                logger.info(f"[cyan]{self.tracker}:[/cyan] [green]Successfully extracted embedded Portuguese subtitle.[/green]")
                            else:
                                logger.warning(f"[cyan]{self.tracker}:[/cyan] [yellow]Failed to extract subtitle stream {idx}. ffmpeg exit code: {process.returncode}[/yellow]")
                                if stderr:
                                    logger.debug(f"[cyan]{self.tracker}:[/cyan] ffmpeg stderr: {stderr.decode('utf-8', errors='ignore')}")
                        except Exception as e:
                            logger.error(f"[cyan]{self.tracker}:[/cyan] [red]Error running ffmpeg to extract subtitle: {e}[/red]")

        return sorted(set(pt_subs))

    def _build_bbcode(
        self,
        *,
        title_br: str,
        title_orig: str,
        release: str,
        poster_url: str,
        overview: str,
        image_urls: list[str],
        cast_text: str,
        genres: str,
        directors: str,
        duration: str,
        year: str,
        countries: str,
        audio: str,
        subs: str,
        imdb_url: str,
        homepage_url: str,
        quality: str,
        container: str,
        video_codec: str,
        video_brate: str,
        audio_codec: str,
        audio_brate: str,
        res_str: str,
        aspect: str,
        fps_str: str,
        filesize: str,
        awards: str = "",
        trivia: str = "",
        critic: str = "",
    ) -> str:
        """Render and return the complete BBCode post body matching MakingOff's JavaScript generator."""
        s_rows = self._screen_rows(image_urls)

        bbcode = "[tablePrinc][tr][titMasc]Título do Filme[/titMasc][/tr]"
        bbcode += f"[tr][titTrad]{title_br}[/titTrad][titOri]{title_orig}[/titOri]"
        if release:
            bbcode += f"[release]{release}[/release][/tr]"
        else:
            bbcode += "[release]Release não informado[/release][/tr]"

        bbcode += "[tr][posterMasc]Poster[/posterMasc][sinopseMasc]Sinopse[/sinopseMasc][/tr]"
        bbcode += f"[tr][poster][posterIma]{poster_url}[/posterIma][/poster][sinopse]{overview}[/sinopse]"
        bbcode += "[tableScreen]Screenshots[/tableScreen]"
        bbcode += f"{s_rows}[/tablePrinc]"

        bbcode += "[tablePrinc][tr][posterMasc]Elenco[/posterMasc]"
        bbcode += "[infoMasc]Informações sobre o filme[/infoMasc]"
        bbcode += "[infoMasc]Informações sobre o release[/infoMasc][/tr]"
        bbcode += f"[tr][elenco]{cast_text}[/elenco]"

        bbcode += f"[info][b]Gênero: [/b]{genres}\n"
        bbcode += f"[b]Diretor: [/b]{directors}\n"
        if duration:
            bbcode += f"[b]Duração: [/b]{duration} minutos\n"
        bbcode += f"[b]Ano de Lançamento: [/b]{year}\n"
        bbcode += f"[b]País de Origem: [/b]{countries}\n"
        bbcode += f"[b]Idioma do Áudio: [/b]{audio}\n"
        if imdb_url:
            bbcode += f"[b]IMDB: [/b][url={imdb_url}]{imdb_url}[/url]\n"
        if homepage_url:
            bbcode += f"[b]Site Oficial: [/b][url={homepage_url}]{homepage_url}[/url]\n"
        bbcode += "[/info]"

        bbcode += f"[info][b]Qualidade de Vídeo: [/b]{quality}\n"
        if container:
            bbcode += f"[b]Container: [/b]{container}\n"
        if video_codec:
            bbcode += f"[b]Vídeo Codec: [/b]{video_codec}\n"
        if video_brate and video_brate != "None":
            bbcode += f"[b]Vídeo Bitrate: [/b]{video_brate} Kbps\n"
        if audio_codec:
            bbcode += f"[b]Áudio Codec: [/b]{audio_codec}\n"
        if audio_brate and audio_brate != "None":
            bbcode += f"[b]Áudio Bitrate: [/b]{audio_brate} Kbps\n"
        if res_str and "x0" not in res_str and "0x" not in res_str:
            bbcode += f"[b]Resolução: [/b]{res_str}\n"
        if aspect:
            bbcode += f"[b]Formato de Tela: [/b]{aspect}\n"
        if fps_str:
            bbcode += f"[b]Frame Rate: [/b]{fps_str}\n"
        bbcode += f"[b]Tamanho: [/b]{filesize}\n"
        bbcode += f"[b]Legendas: [/b]{subs}[/info]"

        if awards:
            bbcode += f"[/tr][tr][infoExtraMasc]Premiações[/infoExtraMasc][/tr][tr][infoExtra]{awards}[/infoExtra]"
        if trivia:
            bbcode += f"[/tr][tr][infoExtraMasc]Curiosidades[/infoExtraMasc][/tr][tr][infoExtra]{trivia}[/infoExtra]"
        if critic:
            bbcode += f"[/tr][tr][infoExtraMasc]Crítica[/infoExtraMasc][/tr][tr][infoExtra]{critic}[/infoExtra]"

        bbcode += "[/tr][tr][rodape]Coopere, deixe semeando ao menos duas vezes o tamanho do arquivo que baixar.[/rodape][/tr][/tablePrinc]"

        return self._html_encode(bbcode)

    def _get_lang_name(self, lang_string: str) -> str:
        with contextlib.suppress(Exception):
            lang = langcodes.find(lang_string)
            if lang and lang.is_valid():
                return lang.display_name("pt").capitalize()
        return lang_string.capitalize()

    def _localizer_countries(self, meta: Meta) -> str:
        """Convert the first production country code to PT-BR name, matching the JS generator."""
        try:
            pt_normal = gettext.translation("iso3166-1", pycountry.LOCALES_DIR, languages=["pt_BR"])
            pt_historic = gettext.translation("iso3166-3", pycountry.LOCALES_DIR, languages=["pt_BR"])
        except OSError:
            pt_normal = None
            pt_historic = None

        custom_country_mapping: dict[str, str] = {
            "XC": "Checoslováquia",
        }

        prod_countries = meta.production_countries
        origin_countries = meta.origin_country

        codes = [c.get("iso_3166_1", "") for c in prod_countries if c.get("iso_3166_1")] if prod_countries else [c for c in origin_countries if c]

        if not codes or not codes[0]:
            return "Desconhecido"

        code_upper = codes[0].upper()
        if code_upper in custom_country_mapping:
            return custom_country_mapping[code_upper]

        # Tenta encontrar no pycountry (países ativos)
        country = pycountry.countries.get(alpha_2=code_upper)
        if country:
            return pt_normal.gettext(country.name) if pt_normal else country.name

        # Tenta encontrar no pycountry (países históricos, ex: SU)
        historic_country = pycountry.historic_countries.get(alpha_2=code_upper)
        if historic_country:
            return pt_historic.gettext(historic_country.name) if pt_historic else historic_country.name

        return codes[0]

    def _localizer_genres(self, meta: Meta) -> str:
        """Convert genre names to PT-BR.

        Accepts both a comma-separated string and a list, as the Meta
        object may expose genres in either form depending on UA version.
        """
        genres_raw = meta.genres or meta.combined_genres or ""
        if not genres_raw:
            return "Desconhecido"
        genre_list = [g.strip() for g in genres_raw if g.strip()] if isinstance(genres_raw, list) else [g.strip() for g in genres_raw.split(",") if g.strip()]
        if not genre_list:
            return "Desconhecido"

        translated_genres: list[str] = []
        for g in genre_list:
            translated = ENG_TO_PTBR_GENRE_MAP.get(g.lower(), g)
            if translated is not None and translated != g:
                translated = translated.title()
            translated_genres.append(translated)
        return ", ".join(translated_genres)

    def _localizer_audio_language(self, meta: Meta) -> str:
        """
        Determine audio language(s) in PT-BR.

        Resolution order: meta audio_languages, mediainfo audio tracks,
        then meta original_language as last resort.
        """
        return "Desconhecido" if not meta.audio_languages else ", ".join(self._get_lang_name(lang.strip()) for lang in meta.audio_languages)

    def _localizer_video_quality(self, meta: Meta) -> str:
        """Convert release type to a localised video quality label matching MakingOff options."""
        type_raw = (meta.type or "").upper()

        video_quality_ptbr: dict[str, str] = {
            "WEBDL": "Web DL",
            "WEBRIP": "Web DL",
            "BLURAY": "BDRip",
            "REMUX": "BR Remux",
            "ENCODE": "BDRip",
            "DISC": "Blu-Ray Full",
            "DVDRIP": "DVD Rip",
            "HDTV": "HDTV Rip",
            "TVRIP": "TV Rip",
            "VHSRIP": "VHS Rip",
            "CAM": "Outro",
        }

        return video_quality_ptbr.get(type_raw, "Outro")

    # -- IPB client methods

    def _get_csrf_token(self, html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        html_tag = soup.find("html")
        if html_tag and html_tag.has_attr("data-csrf"):
            token = html_tag["data-csrf"]
            if token:
                return str(token).strip()

        token_input = soup.find("input", {"name": "_xfToken"})
        if token_input and token_input.has_attr("value"):
            token = token_input["value"]
            if token:
                return str(token).strip()

        match = re.search(r'csrf:\s*["\']([^"\']+)["\']', html)
        if match:
            return match.group(1).strip()

        return ""

    async def refresh_session(self) -> bool:
        try:
            resp = await self.session.get(f"{self.base_url}/")
            if resp.status_code == 403:
                html = resp.text
            else:
                resp.raise_for_status()
                html = resp.text
        except httpx.HTTPError as e:
            response = getattr(e, "response", None)
            if response is not None:
                html = cast(httpx.Response, response).text
            else:
                logger.error(f"[cyan]{self.tracker}:[/cyan] Error validating session: {e}")
                return False

        soup = BeautifulSoup(html, "html.parser")
        html_tag = soup.find("html")
        logged_in = html_tag.get("data-logged-in") == "true" if html_tag else False

        if not logged_in:
            logger.warning(f"[cyan]{self.tracker}:[/cyan] The session is unauthenticated. Check the cookie file.")
            return False

        self._csrf_token = self._get_csrf_token(html)
        await self.cookie_validator.save_session_cookies(self.tracker, cast(Any, self.session.cookies.jar))
        return True

    async def get_new_post_tokens(self, forum_id: int) -> tuple[str, str, str]:
        """
        Retrieve tokens required to create a new forum topic.

        Args:
            forum_id (int): Target forum ID.

        Returns:
            tuple[str, str, str]: csrf_token, attachment_hash, attachment_hash_combined.
        """
        url = f"{self.base_url}/forums/{forum_id}/post-thread"
        try:
            resp = await self.session.get(url)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.error(f"[cyan]{self.tracker}:[/cyan] Failed loading topic new page: {e}")
            return "", "", ""

        soup = BeautifulSoup(resp.text, "html.parser")

        html_tag = soup.find("html")
        logged_in = html_tag.get("data-logged-in") == "true" if html_tag else False
        if not logged_in:
            logger.warning(f"[cyan]{self.tracker}:[/cyan] Unauthenticated session detected on this page.")
            return "", "", ""

        csrf_token = self._get_csrf_token(resp.text)

        attachment_hash = ""
        hash_tag = soup.find("input", {"name": "attachment_hash"})
        if hash_tag:
            attachment_hash = str(hash_tag.get("value", "")).strip()

        attachment_hash_combined = ""
        combined_tag = soup.find("input", {"name": "attachment_hash_combined"})
        if combined_tag:
            attachment_hash_combined = str(combined_tag.get("value", "")).strip()

        if not csrf_token:
            logger.warning(f"[cyan]{self.tracker}:[/cyan] It wasn't possible to extract xfToken. Check if the session is valid.")

        return csrf_token, attachment_hash, attachment_hash_combined

    async def get_post_resolution(self, topic_url: str) -> int:
        """
        Fetches the topic resolution

        Returns:
            int: its resolution.
        """
        topic_url = re.sub(r"^https?://(www\.)?makingoff\.org", "https://makingoff.org", topic_url)

        try:
            resp = await self.session.get(topic_url, follow_redirects=True)
            resp.raise_for_status()
        except httpx.HTTPError:
            return 0

        soup = BeautifulSoup(resp.content, "html.parser")

        resolution = ""
        first_post = soup.find(class_="bbWrapper") or soup.find("div", attrs={"itemprop": "commentText"})
        if first_post:
            text = first_post.get_text(" ", strip=True)
            m = re.search(r"Resolu[^\s:]*[:\s]+(\d{3,4})\s*[xX×]\s*(\d{3,4})", text)  # noqa: RUF001
            if m:
                resolution = f"{m.group(1)}x{m.group(2)}"

        return int(resolution.split("x")[1]) if resolution else 0

    async def upload_attachment(
        self,
        file_path: str,
        csrf_token: str,
        attachment_hash: str,
        attachment_hash_combined: str,
        forum_id: int,
    ) -> bool:
        """
        Upload a file (torrent, subtitle, etc.) as a forum attachment.

        Args:
            file_path (str): Path to the file.
            csrf_token (str): Active CSRF token.
            attachment_hash (str): Attachment hash.
            attachment_hash_combined (str): JSON string containing type, context, and hash.
            forum_id (int): Target forum ID.

        Returns:
            bool: True if the upload succeeded.
        """
        url = f"{self.base_url}/attachments/upload"

        attachment_type = "post"
        context = {"node_id": forum_id}
        if attachment_hash_combined:
            try:
                combined_data = json.loads(attachment_hash_combined)
                attachment_type = combined_data.get("type", "post")
                context = combined_data.get("context", {})
            except Exception as e:
                logger.debug(f"Failed to parse attachment_hash_combined: {e}")

        payload: dict[str, str] = {
            "_xfToken": csrf_token,
            "_xfResponseType": "json",
            "hash": attachment_hash,
            "type": attachment_type,
        }
        for k, v in context.items():
            payload[f"context[{k}]"] = str(v)

        try:
            async with aiofiles.open(file_path, "rb") as f:
                data = await f.read()
            filename = Path(file_path).name

            mime_type, _ = mimetypes.guess_type(file_path)
            if not mime_type:
                mime_type = "application/x-bittorrent" if filename.endswith(".torrent") else "application/octet-stream"

            resp = await self.session.post(
                url,
                data=payload,
                files={"upload": (filename, data, mime_type)},
                headers={"X-Requested-With": "XMLHttpRequest"},
            )
            resp.raise_for_status()
            res_data = resp.json()
        except FileNotFoundError:
            logger.error(f"[cyan]{self.tracker}:[/cyan] [bold red]File not found[/bold red]: {file_path}")
            return False
        except httpx.HTTPError as e:
            logger.error(f"[cyan]{self.tracker}:[/cyan] [bold red]Failed uploading attachment:[/bold red] {e}")
            response = getattr(e, "response", None)
            if response is not None:
                logger.debug(f"[cyan]{self.tracker}:[/cyan] Response: {cast(httpx.Response, response).text}")
            return False
        except Exception as e:
            logger.error(f"[cyan]{self.tracker}:[/cyan] [bold red]Failed to process upload response:[/bold red] {e}")
            return False

        if res_data.get("status") == "ok" or "attachment" in res_data:
            logger.info(f"[cyan]{self.tracker}:[/cyan] [green]Attachment sent successfully: {filename}[/green]")
            return True

        errors = res_data.get("errors", {})
        error_msg = res_data.get("errorHtml", {}).get("content", "") or str(errors)
        logger.error(f"[cyan]{self.tracker}:[/cyan] [bold red]Unwanted response while uploading attachment {filename}:[/bold red]\n{error_msg}")
        return False

    async def search_candidate(
        self,
        phrase: str,
        forum_id: int | None = None,
        title_only: bool = True,
    ) -> dict[str, str] | None:
        """
        Performs a search on the forum.

        Args:
            phrase (str): The text to be searched.
            forum_id (int | None): Optional forum node ID to restrict search.
            title_only (bool): If True, search only in thread titles. Default is True.

        Returns:
            dict[str, str]: A dictionary mapping title -> topic URL.
            None: if the search results nothing.
        """
        if not self._csrf_token:
            await self.refresh_session()
            if not self._csrf_token:
                logger.error(f"[cyan]{self.tracker}:[/cyan] Cannot search, no CSRF token available.")
                return None

        search_url = f"{self.base_url}/search/search"
        payload = {
            "keywords": phrase,
            "_xfToken": self._csrf_token,
            "_xfResponseType": "json",
        }
        if title_only:
            payload["c[title_only]"] = "1"
        if forum_id is not None:
            payload["c[nodes][0]"] = str(forum_id)
            payload["c[child_nodes]"] = "1"

        try:
            resp = await self.session.post(
                search_url,
                data=payload,
                headers={"X-Requested-With": "XMLHttpRequest"},
            )
            resp.raise_for_status()
            res_data = resp.json()
        except httpx.HTTPError as e:
            logger.error(f"[cyan]{self.tracker}:[/cyan] [bold red]Error on the search POST:[/bold red] {e}")
            return None
        except Exception as e:
            logger.error(f"[cyan]{self.tracker}:[/cyan] [bold red]Unwanted response while searching POST:[/bold red] {e}")
            return None

        redirect_url = res_data.get("redirect")
        if not redirect_url:
            errors = res_data.get("errors", {})
            if errors:
                logger.debug(f"[cyan]{self.tracker}:[/cyan] Search errors: {errors}")
            return None

        if redirect_url.startswith("/"):
            redirect_url = f"{self.base_url.rstrip('/')}/{redirect_url.lstrip('/')}"

        try:
            resp = await self.session.get(redirect_url)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.error(f"[cyan]{self.tracker}:[/cyan] [bold red]Error fetching search results page:[/bold red] {e}")
            return None

        soup = BeautifulSoup(resp.text, "html.parser")
        items = soup.find_all(class_="contentRow-title")

        results: dict[str, str] = {}
        for item in items:
            a_tag = item.find("a")
            if not a_tag:
                continue
            title = a_tag.get_text(" ", strip=True)
            href_val = a_tag.get("href", "")
            href = " ".join(href_val) if isinstance(href_val, list) else str(href_val)
            href = href.strip()
            if href:
                if href.startswith("/"):
                    href = f"{self.base_url.rstrip('/')}/{href.lstrip('/')}"
                if title in results:
                    # Append topic ID from URL to avoid title duplication conflicts
                    topic_id = href.rstrip("/").split(".")[-1]
                    title = f"{title} ({topic_id})"
                results[title] = href

        return results or None

    def get_topic_fields(
        self,
        forum_id: int,
        csrf_token: str,
        attachment_hash: str,
        attachment_hash_combined: str,
        topic_title: str,
        post_body: str,
    ) -> dict[str, str]:
        """
        Build the dictionary of form fields for creating a new XenForo topic.
        """
        return {
            "_xfToken": csrf_token,
            "prefix_id": "0",
            "title": topic_title,
            "discussion_type": "discussion",
            "message": post_body,
            "attachment_hash": attachment_hash,
            "attachment_hash_combined": attachment_hash_combined,
            "_xfSet[watch_thread]": "1",
            "_xfResponseType": "json",
            "_xfWithData": "1",
            "_xfRequestUri": f"/forums/{forum_id}/post-thread",
        }

    async def create_topic(
        self,
        forum_id: int,
        csrf_token: str,
        attachment_hash: str,
        attachment_hash_combined: str,
        topic_title: str,
        post_body: str,
    ) -> str:
        """
        Create a new forum topic and return its URL.

        Args:
            forum_id (int): Target forum ID.
            csrf_token (str): XenForo CSRF token.
            attachment_hash (str): Attachment hash.
            attachment_hash_combined (str): Attachment hash combined.
            topic_title (str): Topic title.
            post_body (str): Topic content (BBCode).

        Returns:
            str: Topic URL, or an empty string if creation failed.
        """
        fields = self.get_topic_fields(
            forum_id=forum_id,
            csrf_token=csrf_token,
            attachment_hash=attachment_hash,
            attachment_hash_combined=attachment_hash_combined,
            topic_title=topic_title,
            post_body=post_body,
        )

        url = f"{self.base_url}/forums/{forum_id}/post-thread"

        try:
            resp = await self.session.post(
                url,
                data=fields,
                headers={"X-Requested-With": "XMLHttpRequest"},
            )
            resp.raise_for_status()
            res_data = resp.json()
        except httpx.HTTPError as e:
            logger.error(f"[cyan]{self.tracker}:[/cyan] Failed creating topic: {e}")
            response = getattr(e, "response", None)
            if response is not None:
                logger.debug(f"[cyan]{self.tracker}:[/cyan] Response: {cast(httpx.Response, response).text}")
            return ""
        except Exception as e:
            logger.error(f"[cyan]{self.tracker}:[/cyan] Failed to parse response: {e}")
            return ""

        if res_data.get("status") == "ok" and "redirect" in res_data:
            topic_url = res_data["redirect"]
            if topic_url.startswith("/"):
                topic_url = f"{self.base_url.rstrip('/')}/{topic_url.lstrip('/')}"
            return topic_url

        errors = res_data.get("errors", {})
        error_msg = res_data.get("errorHtml", {}).get("content", "") or str(errors)
        logger.error(f"[cyan]{self.tracker}:[/cyan] [bold red]Failed creating topic:[/bold red]\n{error_msg}")
        return ""

    async def validate_credentials(self, meta: Meta) -> bool:
        """
        Validate tracker credentials and configure the authenticated session.

        Loads session cookies using CookieValidator.

        Args:
            meta: Release metadata.

        Returns:
            bool: True if the credentials are valid.
        """
        cookie_jar = await self.cookie_validator.load_session_cookies(meta, self.tracker)
        if not cookie_jar:
            return False

        self.session.cookies = cast(Any, cookie_jar)

        if not await self.refresh_session():
            logger.error(f"[cyan]{self.tracker}:[/cyan] [bold red]Session couldn't be validated.[/bold red] Cookies may be expired.")
            return False

        return True

    async def search_existing(self, meta: Meta) -> list[dict[str, str]]:
        """
        Search for existing releases on the forum before uploading.

        Args:
            meta: Release metadata.

        Returns:
            list[dict[str, str]]: Detected duplicate entries.
        """
        duplicates: list[dict[str, str]] = []

        if not await self.validate_credentials(meta):
            return duplicates

        hidef_resolutions = {"720p", "1080i", "1080p", "2160p", "4320p"}
        resolution_str = meta.resolution
        uploading_hidef = resolution_str in hidef_resolutions
        upload_year = str(meta.year)

        title_ptbr = await self._resolve_display_title(meta)
        title_orig = meta.original_title
        title_en = meta.title

        candidates: list[str] = []
        if self._is_brazilian(meta):
            candidates = [title_ptbr]
        else:
            for t in [title_ptbr, title_en, title_orig]:
                if t and t not in candidates:
                    candidates.append(t)

        forum_id = await self.get_forum_id(meta)
        results: dict[str, str] = {}

        # 1. Search by IMDB ID (without title_only, as it is in the post description)
        if meta.imdb_tt:
            logger.info(f"[cyan]{self.tracker}:[/cyan] [yellow]Searching by IMDB ID:[/yellow] {meta.imdb_tt}")
            found = await self.search_candidate(meta.imdb_tt, forum_id=forum_id, title_only=False)
            if found:
                results.update(found)

        # 2. Search by title candidates (with title_only=True)
        for candidate in candidates:
            phrase = candidate.strip()
            logger.info(f"[cyan]{self.tracker}:[/cyan] [yellow]Searching for title:[/yellow] {phrase}")
            found = await self.search_candidate(phrase, forum_id=forum_id, title_only=True)
            if found:
                results.update(found)

        if not results:
            return duplicates

        for title, url in results.items():
            existing_hidef = title.strip().startswith("[Hidef]")

            if upload_year:
                year_int = int(upload_year)
                if not any(f"({y})" in title for y in (year_int - 1, year_int, year_int + 1)):
                    logger.info(f"[cyan]{self.tracker}:[/cyan] [yellow]Skipping: different year in existing release:[/yellow] {title}")
                    continue

            # Uploading SD while a Hidef exists → block immediately.
            if not uploading_hidef and existing_hidef:
                logger.warning(f"[cyan]{self.tracker}:[/cyan] [bold red]Aborting: A Hidef release exists:[/bold red] {title}")
                meta.skipping = self.tracker
                duplicates.append({"name": title, "size": "", "link": url})
                continue

            # Uploading Hidef over an existing SD → allowed.
            if uploading_hidef and not existing_hidef:
                continue

            # Same tier (SD vs SD or Hidef vs Hidef) → compare resolution.
            resolution = await self.get_post_resolution(url)

            try:
                upload_height = int(resolution_str.replace("p", "").replace("i", ""))
            except TypeError, ValueError:
                upload_height = 0

            if resolution >= upload_height:
                logger.warning(f"[cyan]{self.tracker}:[/cyan] [bold red]Aborting: A better or equivalent Hidef release exists:[/bold red] {title}")
                meta.skipping = self.tracker
                duplicates.append({"name": title, "size": str(resolution), "link": url})
                continue

        return duplicates

    async def get_forum_id(self, meta: Meta) -> int:
        """
        Determine the target forum ID based on content type and country of origin.

        Args:
            meta: Release metadata.

        Returns:
            int: Selected forum ID.
        """
        # https://en.wikipedia.org/wiki/List_of_ISO_3166_country_codes
        africa = [
            "DZ",
            "AO",
            "BJ",
            "BW",
            "BF",
            "BI",
            "CM",
            "CV",
            "CF",
            "TD",
            "KM",
            "CD",
            "CG",
            "CI",
            "DJ",
            "EG",
            "GQ",
            "ER",
            "ET",
            "GA",
            "GM",
            "GH",
            "GN",
            "GW",
            "KE",
            "LS",
            "LR",
            "LY",
            "MG",
            "MW",
            "ML",
            "MR",
            "MU",
            "MA",
            "MZ",
            "NA",
            "NE",
            "NG",
            "RW",
            "ST",
            "SN",
            "SC",
            "SL",
            "SO",
            "ZA",
            "SS",
            "SD",
            "SZ",
            "TZ",
            "TG",
            "TN",
            "UG",
            "ZM",
            "ZW",
        ]

        asia = [
            "AF",
            "AM",
            "AZ",
            "BD",
            "BT",
            "BN",
            "KH",
            "CN",
            "GE",
            "IN",
            "ID",
            "JP",
            "KZ",
            "KG",
            "LA",
            "MY",
            "MV",
            "MN",
            "MM",
            "NP",
            "KP",
            "KR",
            "PK",
            "PH",
            "SG",
            "LK",
            "TW",
            "TJ",
            "TH",
            "TL",
            "TM",
            "UZ",
            "VN",
        ]

        europe = [
            "AL",
            "XC",
            "AD",
            "AT",
            "BY",
            "BE",
            "BA",
            "BG",
            "HR",
            "SU",
            "CY",
            "CZ",
            "DK",
            "EE",
            "FI",
            "FR",
            "DE",
            "GR",
            "HU",
            "IS",
            "IE",
            "IT",
            "XK",
            "LV",
            "LI",
            "LT",
            "LU",
            "MT",
            "MD",
            "MC",
            "ME",
            "MK",
            "NL",
            "NO",
            "PL",
            "PT",
            "RO",
            "RU",
            "SM",
            "RS",
            "SK",
            "SI",
            "ES",
            "SE",
            "CH",
            "UA",
            "GB",
            "VA",
        ]

        latin_america = ["AR", "BO", "CL", "CO", "CR", "CU", "DO", "EC", "SV", "GT", "HN", "MX", "NI", "PA", "PY", "PE", "UY", "VE"]

        brasil = ["BR"]
        north_america = ["US", "CA"]

        oceania = ["AU", "FJ", "KI", "MH", "FM", "NR", "NZ", "PW", "PG", "WS", "SB", "TO", "TV", "VU"]

        middle_east = ["BH", "IR", "IQ", "IL", "JO", "KW", "LB", "OM", "QA", "SA", "SY", "AE", "YE"]

        forum_id_by_country: dict[str, int] = {}
        for code in africa:
            forum_id_by_country[code] = 461
        for code in asia:
            forum_id_by_country[code] = 24
        for code in europe:
            forum_id_by_country[code] = 25
        for code in latin_america:
            forum_id_by_country[code] = 29
        for code in brasil:
            forum_id_by_country[code] = 27
        for code in north_america:
            forum_id_by_country[code] = 26
        for code in oceania:
            forum_id_by_country[code] = 31
        for code in middle_east:
            forum_id_by_country[code] = 30

        genres_raw = meta.genres or meta.combined_genres
        genres_str = ", ".join(genres_raw) if isinstance(genres_raw, list) else genres_raw
        if "documentary" in genres_str.lower() or "documentário" in genres_str.lower():
            return 28

        if 0 < meta.runtime < 40:
            return 77

        origin_countries: list[str] = meta.origin_country
        if not origin_countries:
            prod_countries = meta.production_countries
            origin_countries = [c.get("iso_3166_1", "") for c in prod_countries if c.get("iso_3166_1")]

        for code in origin_countries:
            if code in forum_id_by_country:
                return forum_id_by_country[code]

        logger.info(
            f"[cyan]{self.tracker}:[/cyan] [bold yellow]Unmapped origin country [/bold yellow]({origin_countries}). [bold yellow]Select the subforum manually:[/bold yellow]"
        )
        forum_options = {
            "1": (461, "África"),
            "2": (24, "Asiático"),
            "3": (77, "Curtas"),
            "4": (28, "Documentários"),
            "5": (25, "Europeu"),
            "6": (29, "Latino Americano"),
            "7": (27, "Nacional (Brasil)"),
            "8": (26, "Norte-Americano"),
            "9": (31, "Oceania"),
            "10": (30, "Oriente Médio"),
        }
        for k, (fid, name) in forum_options.items():
            logger.info(f"  {k}) {name} (ID: {fid})")

        choice = (await asyncio.to_thread(input, "Escolha: ")).strip()
        if choice in forum_options:
            return forum_options[choice][0]

        logger.warning(f"[cyan]{self.tracker}:[/cyan] [yellow]Invalid option, using North-American (26) as default.[/yellow]")
        return 26

    # -- title resolution

    def _is_brazilian(self, meta: Meta) -> bool:
        """
        Detect whether the release is a Brazilian production.

        Checks origin_country and production_countries first; falls back to
        original_language == 'pt' for older/regional titles.

        Args:
            meta: Release metadata.

        Returns:
            bool: True if the release is considered Brazilian.
        """
        origin_countries: list[str] = meta.origin_country
        prod_codes = [c.get("iso_3166_1", "") for c in meta.production_countries if c.get("iso_3166_1")]
        if "BR" in origin_countries or "BR" in prod_codes:
            return True
        return str(meta.original_language).lower() == "pt"

    def _find_translation_title(self, ptbr_main_or_en_main: dict[str, Any], iso_639_1: str, iso_3166_1: str | None = None) -> str:
        translations = ptbr_main_or_en_main.get("translations", {}).get("translations", [])
        primary: dict[str, Any] | None = next(
            (t for t in translations if t.get("iso_639_1") == iso_639_1 and (iso_3166_1 is None or t.get("iso_3166_1") == iso_3166_1)),
            None,
        )
        if not primary and iso_3166_1:
            primary = next(
                (t for t in translations if t.get("iso_639_1") == iso_639_1),
                None,
            )
        return (primary or {}).get("data", {}).get("title", "") or ""

    async def _resolve_display_title(self, meta: Meta) -> str:
        """
        Resolve the display title, preferring PT-BR.

        For Brazilian films, tries PT-BR first then falls back to
        original_title. For foreign films, tries PT-BR then English
        when the native and original titles are identical.

        The resolved title is cached on the tracker instance (keyed by
        ``meta.uuid``) so that repeated calls within the same upload do
        not trigger extra TMDB requests.

        Args:
            meta: Release metadata.

        Returns:
            str: Resolved display title.
        """
        cache_key: str = meta.uuid
        if cache_key and cache_key in self._display_title_cache:
            return self._display_title_cache[cache_key]

        title_native = meta.title
        title_orig = meta.original_title

        ptbr_main = meta.tmdb_localized_data.get("pt-BR", {}).get("main", {})
        en_main = meta.tmdb_localized_data.get("en-US", {}).get("main", {})

        if self._is_brazilian(meta):
            if ptbr_main:
                ptbr = self._find_translation_title(ptbr_main, "pt", "BR")
                if ptbr:
                    title_native = ptbr
                elif title_orig:
                    title_native = title_orig
        else:
            if ptbr_main:
                ptbr = self._find_translation_title(ptbr_main, "pt", "BR")
                if ptbr and ptbr.lower() != title_orig.lower():
                    title_native = ptbr
                elif title_native.lower() == title_orig.lower() and en_main:
                    en = self._find_translation_title(en_main, "en", "US")
                    if en and en.lower() != title_orig.lower():
                        title_native = en

        if cache_key:
            self._display_title_cache[cache_key] = title_native
        return title_native

    # -- topic title

    async def get_topic_title(self, meta: Meta) -> str:
        """
        Generate the forum topic title.

        Format for Brazilian films:  [Hidef] PT-BR Title (Year)
        Format for foreign films:    [Hidef] PT-BR Title / Original Title (Year)

        Args:
            meta (dict[str, Any]): Release metadata.

        Returns:
            str: Formatted topic title.
        """
        hidef_resolutions = {"720p", "1080i", "1080p", "2160p", "4320p"}
        prefix = "[Hidef] " if meta.resolution in hidef_resolutions else ""

        title_ptbr = await self._resolve_display_title(meta)
        year: str = str(meta.year) if meta.year else ""

        if self._is_brazilian(meta):
            title_part = title_ptbr
        else:
            title_orig = meta.original_title
            title_part = f"{title_ptbr} / {title_orig}" if title_orig and title_orig.lower() != title_ptbr.lower() else title_ptbr

        return f"{prefix}{title_part} ({year})" if year else f"{prefix}{title_part}"

    # -- description generation

    def _extract_image_urls(self, meta: Meta) -> list[str]:
        """
        Extract screenshot URLs from meta image_list.

        Handles both plain URL strings and dict entries produced by
        various image host modules.

        Args:
            meta (dict[str, Any]): Release metadata.

        Returns:
            list[str]: Resolved image URLs.
        """
        urls: list[str] = []
        for img in meta.image_list:
            if isinstance(img, str):
                urls.append(img)
            elif isinstance(img, dict):
                url = img.get("raw_url") or img.get("img_url") or img.get("url") or img.get("web_url") or ""
                if url:
                    urls.append(url)
        return urls

    async def _subtitles_ptbr(self, meta: Meta) -> str:
        """
        Prompt the user to select a subtitle type.

        Returns:
            str: Selected subtitle type label.
        """
        if not meta.language_checked:
            await languages_manager.process_desc_language(meta, tracker=self.tracker)
        portuguese_languages = {"portuguese", "português", "pt"}

        meta_subtitle_languages = meta.subtitle_languages if meta.subtitle_languages else []
        found_languages = {lang.lower() for lang in meta_subtitle_languages}

        # Check if we have external Portuguese subtitles or embedded ones.
        # If we have external Portuguese subtitle files, they will be uploaded as attachments ("Anexas").
        has_external_pt_sub = False
        for sub_file in getattr(meta, "subtitle_files", []):
            if not Path(sub_file).exists():
                continue
            name_lower = Path(sub_file).name.lower()
            if any(term in name_lower for term in (".pt", ".pt-br", ".por", "portuguese", "ptbr", "pt_br")) or self._is_subtitle_in_portuguese(sub_file):
                has_external_pt_sub = True
                break

        if has_external_pt_sub:
            return "Anexas"

        if any(lang in portuguese_languages for lang in found_languages):
            return "Embutidas"

        # Fallback to asking
        options = {
            "1": "No torrent",
            "2": "Anexas",
            "3": "Embutidas",
            "4": "Fixas",
            "5": "Sem Legenda",
        }
        logger.info(f"[cyan]{self.tracker}:[/cyan] [yellow]Any subtitles?[/yellow]")
        for k, v in options.items():
            logger.info(f"  {k}) {v}")
        selection = (await asyncio.to_thread(input, "Choose: ")).strip()
        return options.get(selection, "Sem Legenda")

    async def generate_description(self, meta: Meta) -> str:
        """
        Generate the BBCode description for the forum post.

        Args:
            meta (dict[str, Any]): Release metadata.

        Returns:
            str: Formatted BBCode description.
        """
        title_br = await self._resolve_display_title(meta)
        title_orig = title_br if self._is_brazilian(meta) else meta.original_title or title_br

        release_name = meta.basename_no_ext or meta.name or meta.uuid
        release = release_name.replace(" ", ".")

        # Prefer TMDB PT-BR overview already cached by the UA; fall back to
        # translation details from the pre-fetched translations list.
        ptbr_main = dict(meta.tmdb_localized_data.get("pt-BR", {})).get("main", {})
        en_main = dict(meta.tmdb_localized_data.get("en-US", {})).get("main", {})

        poster_raw = ptbr_main.get("poster_path") or meta.tmdb_poster
        poster_url = poster_raw if poster_raw.startswith("http") else f"https://image.tmdb.org/t/p/original{poster_raw}" if poster_raw else ""

        pt_overview = ""
        if ptbr_main:
            translations = ptbr_main.get("translations", {}).get("translations", [])
            for iso_3166_1 in ("BR", None):
                match = next(
                    (t for t in translations if t.get("iso_639_1") == "pt" and (iso_3166_1 is None or t.get("iso_3166_1") == iso_3166_1)),
                    None,
                )
                if match:
                    pt_overview = match.get("data", {}).get("overview", "")
                    if pt_overview:
                        break

        overview = ptbr_main.get("overview") or pt_overview or meta.overview

        # Romanize cast names by pulling from en-US main data, slice to 10 and join with comma, matching the JS generator
        cast_list: list[dict[str, Any]] = cast(list[dict[str, Any]], en_main.get("credits", {}).get("cast", [])[:10]) if en_main else []
        cast_names: list[str] = [cast(str, member.get("name")) for member in cast_list if member.get("name")]
        cast_text = ", ".join(cast_names)

        # Romanize director name
        tmdb_dirs: list[str] = (
            [
                cast(str, member.get("name"))
                for member in cast(list[dict[str, Any]], en_main.get("credits", {}).get("crew", []))
                if member.get("job") == "Director" and member.get("name")
            ]
            if en_main
            else []
        )
        imdb_dirs: list[str] = [name for name in cast(list[Any], meta.imdb_info.get("directors", []) or []) if isinstance(name, str)]
        directors = ", ".join(tmdb_dirs if tmdb_dirs else imdb_dirs)

        imdb_url = ""
        if meta.imdb_id or meta.imdb_info.get("imdb_url"):
            imdb_url = meta.imdb_info.get("imdb_url") or f"https://www.imdb.com/title/tt{str(meta.imdb_id).zfill(7)}/"

        homepage_url = ptbr_main.get("homepage") or en_main.get("homepage") or ""

        # Extract tracks from meta.mediainfo
        tracks: list[dict[str, Any]] = cast(list[dict[str, Any]], meta.mediainfo.get("media", {}).get("track", []))
        video_track: dict[str, Any] = next((track for track in tracks if track.get("@type") == "Video"), {})
        audio_track: dict[str, Any] = next((track for track in tracks if track.get("@type") == "Audio"), {})
        general_track: dict[str, Any] = next((track for track in tracks if track.get("@type") == "General"), {})

        width, height = meta.video_width or 0, meta.video_height or 0

        # Optional fields from meta
        awards = getattr(meta, "awards", "") or getattr(meta, "premiacoes", "") or ""
        trivia = getattr(meta, "trivia", "") or getattr(meta, "curiosidades", "") or ""
        critic = getattr(meta, "critic", "") or getattr(meta, "critica", "") or ""

        return self._build_bbcode(
            title_br=title_br,
            title_orig=title_orig,
            release=release,
            poster_url=poster_url,
            overview=overview,
            image_urls=self._extract_image_urls(meta),
            cast_text=cast_text,
            genres=self._localizer_genres(meta),
            directors=directors,
            duration=str(meta.runtime or self._mediainfo_duration(general_track, video_track) or ""),
            year=str(getattr(meta, "year", "") or ""),
            countries=self._localizer_countries(meta),
            audio=self._localizer_audio_language(meta),
            subs=await self._subtitles_ptbr(meta),
            imdb_url=imdb_url,
            homepage_url=homepage_url,
            quality=self._localizer_video_quality(meta),
            container=self._mediainfo_container(general_track, fallback=(getattr(meta, "container", "") or "").upper()),
            video_codec=self._mediainfo_video_codec(meta, video_track),
            video_brate=str(meta.video_bitrate),
            audio_codec=self._mediainfo_audio_codec(meta, audio_track),
            audio_brate=str(meta.audio_bitrate),
            res_str=f"{width}x{height}",
            aspect=self._aspect_ratio(width, height),
            fps_str=f"{meta.frame_rate:.3f} FPS" if meta.frame_rate else "23.976 FPS",
            filesize=self._mediainfo_filesize(meta),
            awards=awards,
            trivia=trivia,
            critic=critic,
        )

    async def get_additional_checks(self, meta: Meta) -> bool:
        """
        Validate tracker-specific requirements before uploading.

        Args:
            meta (dict[str, Any]): Release metadata.

        Returns:
            bool: True if the release meets all requirements.
        """
        if meta.resolution == "2160p":
            logger.warning(f"[cyan]{self.tracker}:[/cyan] [bold red]4K Resolution (2160p) isn't allowed on this forum.[/bold red]")
            return False

        video = meta.video_codec.upper()
        if not any(c in video for c in ("H264", "H.264", "AVC")):
            logger.warning(f"[cyan]{self.tracker}:[/cyan] [bold red]Only H.264 codec is allowed on this forum.[/bold red]")
            return False

        if not meta.is_disc and meta.container.upper() not in ("MKV", "AVI"):
            logger.warning(f"[cyan]{self.tracker}:[/cyan] [bold red]Only MKV/AVI containers are allowed on this forum.[/bold red]")
            return False

        return True

    async def upload(self, meta: Meta) -> bool:
        """
        Upload a release by creating a forum topic with the torrent as attachment.

        Args:
            meta (dict[str, Any]): Release metadata.

        Returns:
            bool: True if the upload succeeded.
        """
        forum_id = await self.get_forum_id(meta)
        logger.info(f"[cyan]{self.tracker}:[/cyan] [green]Selected subforum:[/green] {forum_id} ")
        await self.common.create_torrent_for_upload(
            meta=meta,
            tracker=self.tracker,
            source_flag=self.source_flag,
            is_public=True,
            public_trackers=self._public_trackers,
        )
        torrent_path = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/[{self.tracker}].torrent"

        # Creates a copy of the torrent with the media filename,
        # this one should be attached to the topic.
        release_name = meta.basename_no_ext or meta.name or meta.uuid
        release_filename = release_name.replace(" ", ".")
        named_torrent_path = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/{release_filename}.torrent"
        shutil.copy2(torrent_path, named_torrent_path)

        # Get Portuguese subtitles (external or extracted)
        sub_files = await self._get_portuguese_subtitles(meta)

        # Zip subtitles to comply with MakingOff allowed formats (.torrent, .rar, .zip)
        if sub_files:
            temp_dir = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}"
            zip_path = str(Path(temp_dir) / f"{release_filename}.legendas.zip")
            try:
                with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
                    for sub_file in sub_files:
                        zipf.write(sub_file, arcname=Path(sub_file).name)
                logger.info(f"[cyan]{self.tracker}:[/cyan] [green]Zipped {len(sub_files)} subtitles to {Path(zip_path).name}[/green]")
                sub_files = [zip_path]
            except Exception as e:
                logger.error(f"[cyan]{self.tracker}:[/cyan] [red]Failed to create zip file for subtitles: {e}[/red]")
                sub_files = []

        if meta.debug:
            topic_title = await self.get_topic_title(meta)
            post_body = await self.generate_description(meta)

            fields = self.get_topic_fields(
                forum_id=forum_id,
                csrf_token="DEBUG_CSRF",  # noqa: S106
                attachment_hash="DEBUG_HASH",
                attachment_hash_combined="DEBUG_COMBINED",
                topic_title=topic_title,
                post_body=post_body,
            )

            logger.info(f"[cyan]{self.tracker} Request Data:[/cyan]")
            logger.info(Redaction.redact_private_info(fields))

            if sub_files:
                logger.info(f"[cyan]{self.tracker} Debug Subtitles to upload:[/cyan] {sub_files}")

            txt_path = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/[{self.tracker}]DESCRIPTION.txt"
            async with aiofiles.open(txt_path, "w", encoding="utf-8") as f:
                await f.write(f"TITULO: {topic_title}\n\n")
                await f.write(post_body)
            logger.info(f"[cyan]{self.tracker}:[/cyan] [yellow]BBCode saved.[/yellow] {txt_path}")
            meta["tracker_status"][self.tracker]["status_message"] = "Debug mode enabled, not uploading (simulated successfully)"
            return True

        # The UA instantiates a fresh tracker object for the upload step,
        # so credentials must be loaded again here.
        if not await self.validate_credentials(meta):
            meta["tracker_status"][self.tracker]["status_message"] = "data error: Failed to validate credentials before upload."
            return False

        csrf_token, attachment_hash, attachment_hash_combined = await self.get_new_post_tokens(forum_id)
        if not csrf_token or not attachment_hash:
            meta["tracker_status"][self.tracker]["status_message"] = "data error: Failed to retrieve XenForo tokens."
            return False

        if not await self.upload_attachment(named_torrent_path, csrf_token, attachment_hash, attachment_hash_combined, forum_id):
            meta["tracker_status"][self.tracker]["status_message"] = "data error: Failed to upload .torrent attachment."
            return False

        # Upload Portuguese subtitles if any
        for sub_file in sub_files:
            logger.info(f"[cyan]{self.tracker}:[/cyan] [yellow]Uploading Portuguese subtitle as attachment:[/yellow] {Path(sub_file).name}")
            await self.upload_attachment(sub_file, csrf_token, attachment_hash, attachment_hash_combined, forum_id)

        topic_title = await self.get_topic_title(meta)
        post_body = await self.generate_description(meta)

        topic_url = await self.create_topic(
            forum_id=forum_id,
            csrf_token=csrf_token,
            attachment_hash=attachment_hash,
            attachment_hash_combined=attachment_hash_combined,
            topic_title=topic_title,
            post_body=post_body,
        )

        if topic_url:
            meta["tracker_status"][self.tracker]["status_message"] = "Upload successful"
            meta["tracker_status"][self.tracker]["torrent_id"] = topic_url
            return True

        meta["tracker_status"][self.tracker]["status_message"] = "data error: Failed creating the forum topic."
        return False
