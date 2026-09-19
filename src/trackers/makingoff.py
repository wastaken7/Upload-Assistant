import asyncio
import contextlib
import gettext
import json
import mimetypes
import platform
import re
import shutil
import unicodedata
import zipfile
from pathlib import Path
from typing import Any, ClassVar, cast
from urllib.parse import urljoin

import aiofiles
import cli_ui
import httpx
import langcodes
import pycountry
from bs4 import BeautifulSoup

from src.binaries import configured_binary
from src.cogs.redaction import Redaction
from src.config_helpers import format_terminal_link
from src.console import logger, prompt_in_thread
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
    banned_groups: tuple[str, ...] = ("aXXo", "CM8", "YIFY", "STUTTERSHIT")
    index_url = "https://www.makingoff.org/"
    torrent_url = ""
    supported_categories = ("MOVIE",)
    max_search_pages = 25
    allows_bloated_audio = True
    tmdb_localization_requirements: ClassVar = {
        "pt-BR": {
            "main": "credits,translations,videos",
        },
        "en-US": {
            "main": "credits,translations,videos",
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
        (["e-ac-3", "eac3"], "E-AC-3"),
        (["ac-3", "ac3"], "AC-3"),
        (["truehd"], "TrueHD"),
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
        self._prefix_ids: dict[str, str] = {}

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

    @staticmethod
    def _slugify_tag(value: str) -> str:
        slug = unicodedata.normalize("NFD", value).encode("ascii", "ignore").decode().lower()
        slug = re.sub("['\u2019]", "", slug)
        return re.sub(r"[^a-z0-9]+", "-", slug).strip("-")

    @classmethod
    def _tag_links(cls, value: str) -> str:
        """Render a comma-separated value as MakingOff's searchable tags."""
        links: list[str] = []
        for item in value.split(","):
            label = item.strip()
            slug = cls._slugify_tag(label)
            if label and slug:
                links.append(f"[TAG={slug}]{label}[/TAG]")
        return ", ".join(links)

    @staticmethod
    def _resolution_quality(res_str: str) -> str:
        """Return the quality label used by the current MakingOff generator."""
        match = re.search(r"(\d{2,5})\s*[x\u00d7]\s*(\d{2,5})", res_str)
        if not match:
            return ""
        width, height = map(int, match.groups())
        if width >= 3600 or height >= 2000:
            return "4K · 2160p"
        if width >= 1700 or height >= 900:
            return "FHD · 1080p"
        if width >= 1150 or height >= 650:
            return "HD · 720p"
        if height >= 550:
            return "SD · 576p"
        return "SD · 480p" if height else ""

    @staticmethod
    def _youtube_id(url: str) -> str:
        match = re.search(r"(?:youtu\.be/|youtube\.com/(?:watch\?v=|embed/|shorts/|live/))([\w-]{6,})", url)
        return match.group(1) if match else ""

    @staticmethod
    def _tmdb_youtube_trailer(*localized_main: dict[str, Any]) -> str:
        """Choose the best localized YouTube trailer using the generator's priorities."""
        candidates: list[dict[str, Any]] = []
        for main in localized_main:
            candidates.extend(cast(list[dict[str, Any]], main.get("videos", {}).get("results", [])))

        def score(video: dict[str, Any]) -> tuple[int, str]:
            name = str(video.get("name", "")).lower()
            value = 100 if video.get("official") is True else 0
            value += 40 if "official trailer" in name or "trailer oficial" in name else 20 if "official" in name else 0
            value += 15 if str(video.get("iso_3166_1", "")).upper() == "BR" else 0
            value += 10 if str(video.get("iso_639_1", "")).lower() == "pt" else 0
            return value, str(video.get("published_at", ""))

        trailers = [video for video in candidates if str(video.get("site", "")).lower() == "youtube" and str(video.get("type", "")).lower() == "trailer" and video.get("key")]
        selected = max(trailers, key=score, default=None)
        return f"https://www.youtube.com/watch?v={selected['key']}" if selected else ""

    @staticmethod
    def _audio_channels(audio_track: dict[str, Any]) -> str:
        raw = str(audio_track.get("Channel(s)") or audio_track.get("Channels") or "")
        match = re.search(r"\d+", raw)
        if not match:
            return raw
        count = int(match.group())
        return {1: "1.0", 2: "2.0", 3: "3.0", 4: "4.0", 5: "5.0", 6: "5.1", 7: "6.1", 8: "7.1"}.get(count, f"{count} canais")

    def _get_ffmpeg_path(self, meta: Meta) -> str:
        if configured := configured_binary("ffmpeg_path", self.config):
            return configured

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
                logger.debug(f"{self.tracker}: Failed to read file {file_path} with encoding {enc}: {e}")
                continue

        if not content:
            return False

        words = re.findall(r"\b\w+\b", content)
        pt_count = sum(1 for w in words if w in pt_words)
        en_count = sum(1 for w in words if w in en_words)
        return pt_count > en_count

    @staticmethod
    def _has_portuguese_language(languages: Any) -> bool:
        """Return whether a MediaInfo/UA language value denotes Portuguese."""
        values = [languages] if isinstance(languages, str) else (languages or [])
        for value in values:
            normalized = str(value).strip().lower()
            if normalized in {"pt", "por", "portuguese", "português", "pt-br", "pt_br", "pt-pt", "pt_pt"}:
                return True
        return False

    def _has_portuguese_subtitle(self, meta: Meta) -> bool:
        """Detect a Portuguese subtitle track, sidecar subtitle, or hard sub."""
        if self._has_portuguese_language(getattr(meta, "subtitle_languages", [])):
            return True

        for sub_file in getattr(meta, "subtitle_files", []):
            path = Path(sub_file)
            if not path.exists():
                continue
            name = path.name.lower()
            if any(term in name for term in (".pt", ".por", "portuguese", "português", "ptbr", "pt_br", "pt-pt", "ptpt")):
                return True
            if self._is_subtitle_in_portuguese(str(path)):
                return True

        tracks = cast(list[dict[str, Any]], getattr(meta, "mediainfo", {}).get("media", {}).get("track", []))
        for track in tracks:
            if track.get("@type") != "Text":
                continue
            if self._has_portuguese_language(track.get("Language", "")):
                return True
            title = str(track.get("Title", "")).lower()
            if any(term in title for term in ("portuguese", "português", "pt-br", "ptbr", "pt_br", "pt-pt", "ptpt")):
                return True

        return bool(getattr(meta, "hardcoded_subs", False))

    @staticmethod
    def _is_hidef(meta: Meta) -> bool:
        """Apply MakingOff's definition of HD, falling back to UA resolution."""
        try:
            if int(meta.video_width or 0) > 1024 or int(meta.video_height or 0) > 576:
                return True
        except TypeError, ValueError:
            pass
        return str(getattr(meta, "resolution", "")).lower() in {"720p", "1080i", "1080p", "1440p", "2160p", "4320p"}

    @staticmethod
    def _release_tokens(meta: Meta) -> str:
        """Return release-identifying text used for deterministic quality checks."""
        fields = (getattr(meta, "name", ""), getattr(meta, "basename_no_ext", ""), getattr(meta, "source", ""), getattr(meta, "type", ""))
        filenames = (str(item) for item in getattr(meta, "filelist", []) or [])
        return " ".join(str(value) for value in (*fields, *filenames) if value).lower()

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
                logger.info(f"{self.tracker}: [green]Found external Portuguese subtitle:[/green] {Path(sub_file).name}")
            elif self._is_subtitle_in_portuguese(sub_file):
                pt_subs.append(sub_file)
                logger.info(f"{self.tracker}: [green]Found external Portuguese subtitle (content-matched):[/green] {Path(sub_file).name}")

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

                        logger.info(f"{self.tracker}: Extracting embedded Portuguese subtitle (stream {idx}) to {output_name}...")
                        try:
                            if meta.debug:
                                logger.debug(f"{self.tracker}: Skipping ffmpeg extraction in debug mode. Command: {' '.join(cmd)}")
                            else:
                                process = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                                _, stderr = await process.communicate()
                                if process.returncode == 0 and Path(output_path).exists() and Path(output_path).stat().st_size > 0:
                                    pt_subs.append(output_path)
                                    logger.info(f"{self.tracker}: [green]Successfully extracted embedded Portuguese subtitle.[/green]")
                                else:
                                    logger.warning(f"{self.tracker}: [yellow]Failed to extract subtitle stream {idx}. ffmpeg exit code: {process.returncode}[/yellow]")
                                    if stderr:
                                        logger.debug(f"{self.tracker}: ffmpeg stderr: {stderr.decode('utf-8', errors='ignore')}")
                        except (OSError, ValueError) as e:
                            logger.error(f"{self.tracker}: [red]Error running ffmpeg to extract subtitle: {e}[/red]")

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
        crew_text: str = "",
        audio_channels: str = "",
        tmdb_id: str = "",
        youtube_url: str = "",
        awards: str = "",
        trivia: str = "",
        critic: str = "",
    ) -> str:
        """Render and return the complete BBCode post body matching MakingOff's JavaScript generator."""
        res_display = res_str.replace("x", "\u00d7")
        video_quality = self._resolution_quality(res_str)
        aspect_tag = re.search(r"\(([^()]+)\)$", aspect)
        aspect_value = aspect_tag.group(1) if aspect_tag else aspect
        video_bitrate = f"{video_brate} Kbps" if video_brate and video_brate != "None" else ""
        audio_bitrate = f"{audio_brate} Kbps" if audio_brate and audio_brate != "None" else ""

        title_info = f"[TITULOBR]{title_br}[/TITULOBR]"
        if year:
            title_info += f" ([ANO]{year}[/ANO])"
        if imdb_url:
            title_info += f'\n[IMDB][URL="{imdb_url}"]IMDb[/URL][/IMDB]'

        details = "\n".join(
            item
            for item in (
                f"[PAIS]{self._tag_links(countries)}[/PAIS]" if countries else "",
                f"[GENERO]{self._tag_links(genres)}[/GENERO]" if genres else "",
                f"[IDIOMA]{audio}[/IDIOMA]" if audio else "",
            )
            if item
        )
        format_line = " · ".join(item for item in (f"[FORMATO]{quality}[/FORMATO]" if quality else "", f"[CONTAINER]{container}[/CONTAINER]" if container else "") if item)
        video_line = " · ".join(
            item
            for item in (
                f"[QUALIDADE]{video_quality}[/QUALIDADE]" if video_quality else "",
                f"[VIDEOCODEC]{video_codec}[/VIDEOCODEC]" if video_codec else "",
                f"[VIDEOBITRATE]{video_bitrate}[/VIDEOBITRATE]" if video_bitrate else "",
                f"[RESOLUCAO]{res_display}[/RESOLUCAO]" if res_display and "0" not in res_display.split("\u00d7") else "",
                f"[ASPECTRATIO]{aspect_value}[/ASPECTRATIO]" if aspect_value else "",
                f"[FRAMERATE]{fps_str}[/FRAMERATE]" if fps_str else "",
            )
            if item
        )
        audio_line = " · ".join(
            item
            for item in (
                f"[AUDIOCODEC]{audio_codec}[/AUDIOCODEC]" if audio_codec else "",
                f"[AUDIOCANAIS]{audio_channels}[/AUDIOCANAIS]" if audio_channels else "",
                f"[AUDIOBITRATE]{audio_bitrate}[/AUDIOBITRATE]" if audio_bitrate else "",
            )
            if item
        )
        subtitle_tooltip = "" if subs == "Sem Legenda" else "pt-BR"
        subtitle_text = "[TAG=legendas-exclusivas]Exclusivas![/TAG]" if subs == "Exclusivas!" else subs
        subtitles = f'[LEGENDAS="{subtitle_tooltip}"]{subtitle_text}[/LEGENDAS]'
        technical = "\n".join(
            item
            for item in (
                format_line,
                f"[DURACAO]{duration} minutos[/DURACAO]" if duration else "",
                f"[TAMANHO]{filesize}[/TAMANHO]" if filesize else "",
                subtitles,
                f"[VIDEO]{video_line}[/VIDEO]" if video_line else "",
                f"[AUDIO]{audio_line}[/AUDIO]" if audio_line else "",
            )
            if item
        )

        info = "\n".join(
            item
            for item in (
                f"[TITULOINFO]\n{title_info}\n[/TITULOINFO]",
                f"[TITULO]{title_orig}[/TITULO]" if title_orig else "",
                f"[DIRECAO]{self._tag_links(directors)}[/DIRECAO]" if directors else "",
                f"[DETALHES]\n{details}\n[/DETALHES]" if details else "",
                f"[RELEASE]{release}[/RELEASE]" if release else "",
                f"[INFOTEC]\n{technical}\n[/INFOTEC]" if technical else "",
            )
            if item
        )
        poster = f"[POSTER][IMG]{poster_url}[/IMG][/POSTER]" if poster_url else "[POSTER][/POSTER]"
        head = f"[PRINCIPAL]\n[DADOS]\n{poster}\n[INFO]\n{info}\n[/INFO]\n[/DADOS]\n[SINOPSE]{overview}[/SINOPSE]\n[/PRINCIPAL]"

        imdb_id = re.search(r"tt\d+", imdb_url)
        credits_links: list[str] = []
        if imdb_id:
            credits_links.append(f'[URL="https://www.imdb.com/title/{imdb_id.group()}/fullcredits/"]IMDb[/URL]')
        if tmdb_id:
            tmdb_path = f"{tmdb_id}-{self._slugify_tag(title_orig)}" if title_orig else tmdb_id
            credits_links.append(f'[URL="https://www.themoviedb.org/movie/{tmdb_path}/cast"]TMDb[/URL]')
        credits_more = f"Mais informações: {', '.join(credits_links)}." if credits_links else ""

        tabs: list[tuple[str, str, str]] = []
        screenshots = "\n".join(f"[SCREENSHOT][IMG]{url}[/IMG][/SCREENSHOT]" for url in image_urls[:8] if url)
        if screenshots:
            tabs.append(("screenshots", "Screenshots", f"[SCREENSHOTSGRID]\n{screenshots}\n[/SCREENSHOTSGRID]"))
        youtube_id = self._youtube_id(youtube_url)
        if youtube_id:
            tabs.append(("trailer", "Trailer", f"[MEDIA=youtube]{youtube_id}[/MEDIA]"))
        if crew_text:
            crew_content = f"{crew_text}\n\n{credits_more}" if credits_more else crew_text
            tabs.append(("equipe", "Equipe", f"[TABTEXTO]{crew_content}[/TABTEXTO]"))
        if cast_text:
            cast_content = cast_text.rstrip(".") + "."
            if credits_more:
                cast_content += f"\n\n{credits_more}"
            tabs.append(("elenco", "Elenco", f"[TABTEXTO]{cast_content}[/TABTEXTO]"))
        if awards:
            awards_content = awards.rstrip(".") + "."
            if imdb_id:
                awards_content += f'\n\nMais informações: [URL="https://www.imdb.com/title/{imdb_id.group()}/awards/"]IMDb[/URL].'
            tabs.append(("premiacoes", "Premiações", f"[TABTEXTO]{awards_content}[/TABTEXTO]"))
        if trivia:
            tabs.append(("curiosidades", "Curiosidades", f"[TABTEXTO][JUSTIFY]{trivia}[/JUSTIFY][/TABTEXTO]"))
        if critic:
            tabs.append(("critica", "Crítica", f"[TABTEXTO][JUSTIFY]{critic}[/JUSTIFY][/TABTEXTO]"))

        extras_links: list[str] = []
        if imdb_url:
            extras_links.append(f'[URL="{imdb_url}"]IMDb[/URL]')
        if tmdb_id:
            extras_links.append(f'[URL="https://www.themoviedb.org/movie/{tmdb_id}"]TMDb[/URL]')
        if imdb_id:
            extras_links.append(f'[URL="https://www.letterboxd.com/imdb/{imdb_id.group()}"]Letterboxd[/URL]')
        if homepage_url:
            extras_links.append(f'[URL="{homepage_url}"]Site Oficial[/URL]')
        if extras_links:
            tabs.append(("extras", "Extras", f"[TABTEXTO]Mais informações: {', '.join(extras_links)}.[/TABTEXTO]"))

        mediainfo_lines = [
            f"Qualidade de Vídeo: {quality}",
            f"Container: {container}",
            f"Vídeo Codec: {video_codec}",
            f"Vídeo Bitrate: {video_bitrate}",
            f"Áudio Codec: {audio_codec}",
            f"Áudio Bitrate: {audio_bitrate}",
            f"Resolução: {res_str}",
            f"Formato de Tela: {aspect}",
            f"Frame Rate: {fps_str}",
            f"Tamanho: {filesize}",
            f"Legendas: {subs}",
        ]
        mediainfo_text = "\n".join(line for line in mediainfo_lines if line.split(": ", 1)[-1])
        tabs.append(("mediainfo", "MediaInfo", f"[MEDIAINFO]{mediainfo_text}[/MEDIAINFO]"))

        nav = "\n".join(f"[{'TABATIVA' if index == 0 else 'TAB'}=id-{key}]{label}[/{'TABATIVA' if index == 0 else 'TAB'}]" for index, (key, label, _) in enumerate(tabs))
        panels = "\n".join(
            f"[{'TABPAINELATIVO' if index == 0 else 'TABPAINEL'}=id-{key}]\n{content}\n[/{'TABPAINELATIVO' if index == 0 else 'TABPAINEL'}]"
            for index, (key, _, content) in enumerate(tabs)
        )
        tabs_block = f"[TABS]\n[TABNAV]\n{nav}\n[/TABNAV]\n[TABPAINEIS]\n{panels}\n[/TABPAINEIS]\n[/TABS]"
        return self._html_encode(f"[FILME]\n{head}\n{tabs_block}\n[/FILME]")

    def _get_lang_name(self, lang_string: str) -> str:
        if not lang_string:
            return ""
        with contextlib.suppress(Exception):
            lang = langcodes.get(lang_string)
            if lang and lang.is_valid():
                return lang.display_name("pt").capitalize()
        with contextlib.suppress(Exception):
            lang = langcodes.find(lang_string)
            if lang and lang.is_valid():
                return lang.display_name("pt").capitalize()
        return lang_string.capitalize()

    def _localizer_countries(self, meta: Meta) -> str:
        """Convert production country codes to PT-BR names, matching the JS generator."""
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

        localized: list[str] = []
        for code in codes:
            code_upper = code.upper()
            if code_upper in custom_country_mapping:
                name = custom_country_mapping[code_upper]
            elif country := pycountry.countries.get(alpha_2=code_upper):
                name = pt_normal.gettext(country.name) if pt_normal else country.name
            elif historic_country := pycountry.historic_countries.get(alpha_2=code_upper):
                name = pt_historic.gettext(historic_country.name) if pt_historic else historic_country.name
            else:
                name = code
            if name not in localized:
                localized.append(name)
        return ", ".join(localized)

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
        Determine original audio language of the film in PT-BR.

        Resolution order: meta.original_language, TMDB / IMDb metadata,
        meta.audio_languages fallback, then "Desconhecido".
        """
        orig_lang = meta.original_language
        if not orig_lang and meta.imdb_info:
            raw_imdb_lang = meta.imdb_info.get("original_language") or meta.imdb_info.get("original language")
            if isinstance(raw_imdb_lang, str):
                orig_lang = raw_imdb_lang

        if orig_lang:
            name = self._get_lang_name(str(orig_lang).strip())
            if name:
                return name

        audio_languages = meta.audio_languages
        if audio_languages:
            return ", ".join(self._get_lang_name(lang.strip()) for lang in audio_languages if self._get_lang_name(lang.strip()))

        return "Desconhecido"

    def _localizer_video_quality(self, meta: Meta) -> str:
        """Convert release type to a localised video quality label matching MakingOff options."""
        release = re.sub(r"[\s._-]+", "", self._release_tokens(meta))
        if str(meta.is_disc).upper() == "DVD":
            return "DVD Full"
        if ("bluray" in release and "remux" in release) or "bdremux" in release:
            return "Blu-ray Remux"
        if ("bluray" in release and "full" in release) or "bdfull" in release:
            return "Blu-ray Full"
        detected_formats = (
            ("bdrip", "BDRip"),
            ("webdl", "WEB-DL"),
            ("webrip", "WEBRip"),
            ("dvdrip", "DVDRip"),
            ("dvdfull", "DVD Full"),
            ("dvd5", "DVD Full"),
            ("dvd9", "DVD Full"),
            ("satrip", "SATRip"),
            ("hdtvrip", "HDTVRip"),
            ("hdtv", "HDTVRip"),
            ("tvrip", "TVRip"),
            ("vhsrip", "VHSRip"),
        )
        for marker, label in detected_formats:
            if marker in release:
                return label

        type_raw = (meta.type or "").upper()

        video_quality_ptbr: dict[str, str] = {
            "WEBDL": "WEB-DL",
            "WEBRIP": "WEBRip",
            "BLURAY": "BDRip",
            "REMUX": "Blu-ray Remux",
            "ENCODE": "BDRip",
            "DISC": "Blu-ray Full",
            "DVDRIP": "DVDRip",
            "HDTV": "HDTVRip",
            "TVRIP": "TVRip",
            "VHSRIP": "VHSRip",
            "SATRIP": "SATRip",
            "CAM": "Indefinido",
        }

        return video_quality_ptbr.get(type_raw, "Indefinido")

    def _topic_prefix_category(self, meta: Meta) -> str:
        release_format = self._localizer_video_quality(meta)
        for category, formats in {
            "Blu-ray": {"BDRip", "Blu-ray Remux", "Blu-ray Full"},
            "WEB": {"WEB-DL", "WEBRip"},
            "DVD": {"DVDRip", "DVD Full"},
            "TV": {"HDTVRip", "TVRip", "SATRip"},
            "VHS": {"VHSRip"},
        }.items():
            if release_format in formats:
                return category
        return "OUTRO"

    def _topic_prefix_id(self, meta: Meta) -> str:
        return self._prefix_ids.get(self._slugify_tag(self._topic_prefix_category(meta)), "")

    @staticmethod
    def _topic_tags(meta: Meta, post_body: str) -> str:
        values = [str(meta.year)] if meta.year else []
        values.extend(re.findall(r"\[TAG=[^\]]+\]([^[]+)\[/TAG\]", post_body, flags=re.IGNORECASE))
        tags: list[str] = []
        seen: set[str] = set()
        for value in values:
            normalized = unicodedata.normalize("NFD", value).encode("ascii", "ignore").decode().casefold()
            if normalized and normalized not in seen:
                seen.add(normalized)
                tags.append(value)
        return ", ".join(tags)

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
                logger.error(f"{self.tracker}: Error validating session: {e}")
                return False

        soup = BeautifulSoup(html, "html.parser")
        html_tag = soup.find("html")
        logged_in = html_tag.get("data-logged-in") == "true" if html_tag else False

        if not logged_in:
            logger.warning(f"{self.tracker}: The session is unauthenticated. Check the cookie file.")
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
            logger.error(f"{self.tracker}: Failed loading topic new page: {e}")
            return "", "", ""

        soup = BeautifulSoup(resp.text, "html.parser")
        self._prefix_ids = self._parse_prefix_ids(soup)

        html_tag = soup.find("html")
        logged_in = html_tag.get("data-logged-in") == "true" if html_tag else False
        if not logged_in:
            logger.warning(f"{self.tracker}: Unauthenticated session detected on this page.")
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
            logger.warning(f"{self.tracker}: It wasn't possible to extract xfToken. Check if the session is valid.")

        return csrf_token, attachment_hash, attachment_hash_combined

    @classmethod
    def _parse_prefix_ids(cls, soup: BeautifulSoup) -> dict[str, str]:
        """Extract current XenForo topic-prefix IDs without hard-coding them."""
        prefix_ids: dict[str, str] = {}
        for option in soup.select('select[name="prefix_id"] option[value]'):
            value = str(option.get("value", "")).strip()
            label = option.get_text(" ", strip=True)
            if value and value != "0" and label:
                prefix_ids[cls._slugify_tag(label)] = value
        for field in soup.select('input[name="prefix_id"][value]'):
            value = str(field.get("value", "")).strip()
            field_id = str(field.get("id", "")).strip()
            label_node = soup.select_one(f'label[for="{field_id}"]') if field_id else field.find_parent("label")
            label = label_node.get_text(" ", strip=True) if label_node else ""
            if value and value != "0" and label:
                prefix_ids[cls._slugify_tag(label)] = value
        return prefix_ids

    @staticmethod
    def _extract_post_height(text: str) -> int:
        """Extract a release height from MakingOff's current or legacy post layout."""
        match = re.search(r"Resolu[^\s:]*[:\s]+(\d{3,4})\s*[xX×]\s*(\d{3,4})", text)  # noqa: RUF001
        if match:
            return int(match.group(2))

        # Older generator posts did not render a ``Resolução`` field.  Their
        # release name still carries the usual 480p/720p/etc. marker.
        match = re.search(r"(?<!\d)(2160|1440|1080|720|576|540|480|432|360|240)[pi]\b", text, re.IGNORECASE)
        return int(match.group(1)) if match else 0

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

        first_post = soup.find(class_="bbWrapper") or soup.find("div", attrs={"itemprop": "commentText"})
        if first_post:
            text = first_post.get_text(" ", strip=True)
            return self._extract_post_height(text)

        return 0

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
                logger.debug(f"{self.tracker}: Failed to parse attachment_hash_combined: {e}")

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
            logger.error(f"{self.tracker}: [bold red]File not found[/bold red]: {file_path}")
            return False
        except httpx.HTTPError as e:
            logger.error(f"{self.tracker}: [bold red]Failed uploading attachment:[/bold red] {e}")
            response = getattr(e, "response", None)
            if response is not None:
                logger.debug(f"{self.tracker}: Response: {cast(httpx.Response, response).text}")
            return False
        except ValueError as e:
            logger.error(f"{self.tracker}: [bold red]Failed to process upload response:[/bold red] {e}")
            return False

        if res_data.get("status") == "ok" or "attachment" in res_data:
            logger.info(f"{self.tracker}: [green]Attachment sent successfully: {filename}[/green]")
            return True

        errors = res_data.get("errors", {})
        error_msg = res_data.get("errorHtml", {}).get("content", "") or str(errors)
        logger.error(f"{self.tracker}: [bold red]Unwanted response while uploading attachment {filename}:[/bold red]\n{error_msg}")
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
                logger.error(f"{self.tracker}: Cannot search, no CSRF token available.")
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
            logger.error(f"{self.tracker}: [bold red]Error on the search POST:[/bold red] {e}")
            return None
        except ValueError as e:
            logger.error(f"{self.tracker}: [bold red]Unwanted response while searching POST:[/bold red] {e}")
            return None

        redirect_url = res_data.get("redirect")
        if not redirect_url:
            errors = res_data.get("errors", {})
            if errors:
                logger.debug(f"{self.tracker}: Search errors: {errors}")
            return None

        if redirect_url.startswith("/"):
            redirect_url = f"{self.base_url.rstrip('/')}/{redirect_url.lstrip('/')}"

        results: dict[str, str] = {}
        page_url = redirect_url
        visited_pages: set[str] = set()

        while page_url and page_url not in visited_pages and len(visited_pages) < self.max_search_pages:
            visited_pages.add(page_url)
            try:
                resp = await self.session.get(page_url)
                resp.raise_for_status()
            except httpx.HTTPError as e:
                logger.error(f"{self.tracker}: [bold red]Error fetching search results page:[/bold red] {e}")
                break

            soup = BeautifulSoup(resp.text, "html.parser")
            for item in soup.find_all(class_="contentRow-title"):
                a_tag = item.find("a")
                if not a_tag:
                    continue
                title = a_tag.get_text(" ", strip=True)
                href_val = a_tag.get("href", "")
                href = " ".join(href_val) if isinstance(href_val, list) else str(href_val)
                href = href.strip()
                if not href:
                    continue
                href = urljoin(f"{self.base_url}/", href)
                if title in results:
                    # Append topic ID from URL to avoid title duplication conflicts.
                    topic_id = href.rstrip("/").split(".")[-1]
                    title = f"{title} ({topic_id})"
                results[title] = href

            next_page = soup.select_one("a.pageNav-jump--next[href]")
            page_url = urljoin(f"{self.base_url}/", str(next_page["href"])) if next_page else ""

        if page_url and len(visited_pages) == self.max_search_pages:
            logger.warning(f"{self.tracker}: [yellow]Stopped duplicate search after {self.max_search_pages} result pages.[/yellow]")

        return results or None

    @staticmethod
    def _parse_index_results(html: str, imdb_tt: str) -> dict[str, str]:
        """Extract only exact IMDb matches from the MakingOff catalogue cards."""
        soup = BeautifulSoup(html, "html.parser")
        results: dict[str, str] = {}
        imdb_pattern = re.compile(rf"/title/{re.escape(imdb_tt)}(?:[/?#]|$)", re.IGNORECASE)

        for card in soup.select(".filme-card"):
            if not any(imdb_pattern.search(str(anchor.get("href", ""))) for anchor in card.select("a[href]")):
                continue

            topic_anchor = card.select_one(".card-title a[href*='/topicos/']") or card.select_one("a[href*='/topicos/']")
            if not topic_anchor:
                continue
            title = topic_anchor.get_text(" ", strip=True)
            href = str(topic_anchor.get("href", "")).strip()
            if not title or not href:
                continue

            year_anchor = card.select_one("a[href^='?ano=']")
            year = year_anchor.get_text(" ", strip=True) if year_anchor else ""
            display_title = f"{title} ({year})" if year.isdigit() else title
            results[display_title] = urljoin(f"{MakingOff.base_url}/", href)

        return results

    async def search_index_by_imdb(self, imdb_tt: str) -> dict[str, str] | None:
        """Search the catalogue, which supports exact IMDb identifiers."""
        try:
            resp = await self.session.get(f"{self.base_url}/indice/", params={"q": imdb_tt})
            resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.error(f"{self.tracker}: [bold red]Error searching the catalogue by IMDb ID:[/bold red] {e}")
            return None

        return self._parse_index_results(resp.text, imdb_tt) or None

    def get_topic_fields(
        self,
        forum_id: int,
        csrf_token: str,
        attachment_hash: str,
        attachment_hash_combined: str,
        topic_title: str,
        post_body: str,
        prefix_id: str,
        topic_tags: str,
    ) -> dict[str, str]:
        """
        Build the dictionary of form fields for creating a new XenForo topic.
        """
        return {
            "_xfToken": csrf_token,
            "prefix_id": prefix_id,
            "title": topic_title,
            "tags": topic_tags,
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
        prefix_id: str,
        topic_tags: str,
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
            prefix_id=prefix_id,
            topic_tags=topic_tags,
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
            logger.error(f"{self.tracker}: Failed creating topic: {e}")
            response = getattr(e, "response", None)
            if response is not None:
                logger.debug(f"{self.tracker}: Response: {cast(httpx.Response, response).text}")
            return ""
        except ValueError as e:
            logger.error(f"{self.tracker}: Failed to parse response: {e}")
            return ""

        if res_data.get("status") == "ok" and "redirect" in res_data:
            topic_url = res_data["redirect"]
            if topic_url.startswith("/"):
                topic_url = f"{self.base_url.rstrip('/')}/{topic_url.lstrip('/')}"
            return topic_url

        errors = res_data.get("errors", {})
        error_msg = res_data.get("errorHtml", {}).get("content", "") or str(errors)
        logger.error(f"{self.tracker}: [bold red]Failed creating topic:[/bold red]\n{error_msg}")
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
            logger.error(f"{self.tracker}: [bold red]Session couldn't be validated.[/bold red] Cookies may be expired.")
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

        resolution_str = meta.resolution
        uploading_hidef = self._is_hidef(meta)
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
        exact_imdb_urls: set[str] = set()

        def merge_results(found: dict[str, str]) -> None:
            """Preserve every topic when separate searches return the same title."""
            for title, url in found.items():
                result_title = title
                if result_title in results and results[result_title] != url:
                    topic_id = url.rstrip("/").split(".")[-1]
                    result_title = f"{title} ({topic_id})"
                    duplicate_number = 2
                    while result_title in results and results[result_title] != url:
                        result_title = f"{title} ({topic_id}-{duplicate_number})"
                        duplicate_number += 1
                results[result_title] = url

        # 1. The catalogue accepts IMDb IDs directly and lets us verify the
        # exact ID in its result card, avoiding false positives from XenForo's
        # full-post text search.
        if meta.imdb_tt:
            logger.info(f"{self.tracker}: [yellow]Searching catalogue by IMDB ID:[/yellow] {meta.imdb_tt}")
            found = await self.search_index_by_imdb(meta.imdb_tt)
            if found:
                merge_results(found)
                exact_imdb_urls.update(found.values())

        # 2. Search by title candidates (with title_only=True)
        for candidate in candidates:
            phrase = candidate.strip()
            logger.info(f"{self.tracker}: [yellow]Searching for title:[/yellow] {phrase}")
            found = await self.search_candidate(phrase, forum_id=forum_id, title_only=True)
            if found:
                merge_results(found)

        if not results:
            return duplicates

        processed_urls: set[str] = set()
        default_config = cast(dict[str, Any], self.config.get("DEFAULT", {}))
        for title, url in results.items():
            if url in processed_urls:
                continue
            processed_urls.add(url)
            resolution = await self.get_post_resolution(url)
            existing_hidef = title.strip().startswith("[Hidef]") or resolution > 576

            if upload_year and url not in exact_imdb_urls:
                year_int = int(upload_year)
                if not any(f"({y})" in title for y in (year_int - 1, year_int, year_int + 1)):
                    logger.info(f"{self.tracker}: [yellow]Skipping: different year in existing release:[/yellow] {format_terminal_link(title, url, default_config)}")
                    continue

            # Uploading SD while a Hidef exists → block immediately.
            if not uploading_hidef and existing_hidef:
                logger.warning(f"{self.tracker}: [bold red]Aborting: A Hidef release exists:[/bold red] {format_terminal_link(title, url, default_config)}")
                if not meta.debug:
                    meta.skipping = self.tracker
                duplicates.append({"name": f"[url={url}]{title}[/url]", "size": "", "link": url})
                continue

            # Uploading Hidef over an existing SD → allowed.
            if uploading_hidef and not existing_hidef:
                continue

            # Same tier (SD vs SD or Hidef vs Hidef) → compare resolution.

            try:
                upload_height = int(resolution_str.replace("p", "").replace("i", ""))
            except TypeError, ValueError:
                upload_height = 0

            if resolution >= upload_height:
                logger.warning(
                    f"{self.tracker}: [bold red]Aborting: A better or equivalent Hidef release exists:[/bold red] {format_terminal_link(title, url, default_config)}"
                )
                if not meta.debug:
                    meta.skipping = self.tracker
                duplicates.append({"name": f"[url={url}]{title}[/url]", "size": str(resolution), "link": url})
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

        logger.info(f"{self.tracker}: [bold yellow]Unmapped origin country [/bold yellow]({origin_countries}). [bold yellow]Select the subforum manually:[/bold yellow]")
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
        if meta.unattended and not meta.unattended_confirm:
            logger.info(f"{self.tracker}: [yellow]Unattended mode: Unmapped origin country ({origin_countries}), using North-American (26) as default.[/yellow]")
            return 26

        for k, (fid, name) in forum_options.items():
            logger.info(f"{self.tracker}:   {k}) {name} (ID: {fid})")

        raw_choice = await prompt_in_thread(cli_ui.ask_string, "Escolha: ")
        choice = (raw_choice or "").strip()
        if choice in forum_options:
            return forum_options[choice][0]

        logger.warning(f"{self.tracker}: [yellow]Invalid option, using North-American (26) as default.[/yellow]")
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

    async def get_name(self, meta: Meta) -> str:
        """
        Generate the forum topic title.

        Format for Brazilian films:  PT-BR Title (Year)
        Format for foreign films:    PT-BR Title / Original Title (Year)

        Args:
            meta (dict[str, Any]): Release metadata.

        Returns:
            str: Formatted topic title.
        """
        title_ptbr = await self._resolve_display_title(meta)
        year: str = str(meta.year) if meta.year else ""

        if self._is_brazilian(meta):
            title_part = title_ptbr
        else:
            title_orig = meta.original_title
            title_part = f"{title_ptbr} / {title_orig}" if title_orig and title_orig.lower() != title_ptbr.lower() else title_ptbr

        return f"{title_part} ({year})" if year else title_part

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
        image_list = cast(list[dict[str, Any]], meta.menu_images) + meta.image_list + meta.spectrograms_images + meta.dynamic_hdr_plot_images
        for img in image_list:
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
        if meta.unattended and not meta.unattended_confirm:
            logger.info(f"{self.tracker}: [yellow]Unattended mode: Subtitles not determined, defaulting to 'Sem Legenda'.[/yellow]")
            return "Sem Legenda"

        options = {
            "1": "No torrent",
            "2": "Anexas",
            "3": "Embutidas",
            "4": "Fixas",
            "5": "Sem Legenda",
        }
        logger.info(f"{self.tracker}: [yellow]Any subtitles?[/yellow]")
        for k, v in options.items():
            logger.info(f"{self.tracker}:   {k}) {v}")
        raw_selection = await prompt_in_thread(cli_ui.ask_string, "Choose: ")
        selection = (raw_selection or "").strip()
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

        release = meta.basename_no_ext or meta.name or meta.uuid

        # Prefer TMDB PT-BR overview already cached by the UA; fall back to
        # translation details from the pre-fetched translations list.
        ptbr_main = dict(meta.tmdb_localized_data.get("pt-BR", {})).get("main", {})
        en_main = dict(meta.tmdb_localized_data.get("en-US", {})).get("main", {})

        poster_raw = ptbr_main.get("poster_path") or meta.tmdb_poster_path
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

        crew_roles = (
            ("Direção", {"Director"}),
            ("Roteiro", {"Screenplay", "Writer", "Teleplay"}),
            ("Produção", {"Producer"}),
            ("Montagem", {"Editor"}),
            ("Composição", {"Original Music Composer"}),
            ("Direção de Fotografia", {"Director of Photography"}),
        )
        crew_list = cast(list[dict[str, Any]], en_main.get("credits", {}).get("crew", [])) if en_main else []
        crew_lines: list[str] = []
        for label, jobs in crew_roles:
            names = list(dict.fromkeys(str(member["name"]) for member in crew_list if member.get("job") in jobs and member.get("name")))
            if names:
                crew_lines.append(f"[B]{label}:[/B] {', '.join(names)}")
        crew_text = "\n".join(crew_lines)

        imdb_url = ""
        if meta.imdb_tt or meta.imdb_info.get("imdb_url"):
            imdb_url = meta.imdb_info.get("imdb_url") or f"https://www.imdb.com/title/{meta.imdb_tt}/"

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
            crew_text=crew_text,
            audio_channels=self._audio_channels(audio_track),
            tmdb_id=str(meta.tmdb_id or ""),
            youtube_url=str(meta.youtube or self._tmdb_youtube_trailer(ptbr_main, en_main)),
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
        if meta.category.upper() != "MOVIE":
            logger.warning(f"{self.tracker}: [bold red]Only films may be uploaded to this forum.[/bold red]")
            return False

        if meta.adult_media or meta.tmdb_adult_media:
            logger.warning(f"{self.tracker}: [bold red]Adult releases are not allowed on this forum.[/bold red]")
            return False

        if meta.is_disc and meta.is_disc != "DVD":
            logger.warning(f"{self.tracker}: [bold red]Only complete DVD structures are allowed; Blu-ray/HDDVD structures must be remuxed to MKV.[/bold red]")
            return False

        if not meta.is_disc and meta.container.upper() not in ("MKV", "AVI"):
            logger.warning(f"{self.tracker}: [bold red]Only MKV/AVI containers are allowed on this forum.[/bold red]")
            return False

        video = f"{meta.video_codec} {meta.video_encode}".upper()
        if any(codec in video for codec in ("HEVC", "H.265", "H265", "X265")):
            logger.warning(f"{self.tracker}: [bold red]HEVC/H.265 video is not allowed on this forum.[/bold red]")
            return False

        if not meta.is_disc and self._is_hidef(meta):
            if not any(codec in video for codec in ("H264", "H.264", "AVC", "X264")):
                logger.warning(f"{self.tracker}: [bold red]High-definition releases must use H.264/AVC video.[/bold red]")
                return False

            try:
                bitrate = int(meta.video_bitrate or 0)
                height = int(meta.video_height or 0)
            except TypeError, ValueError:
                bitrate, height = 0, 0
            minimum = 5000 if height >= 1080 or str(meta.resolution) in {"1080i", "1080p", "1440p", "2160p", "4320p"} else 2200
            if bitrate and bitrate < minimum:
                logger.warning(
                    f"{self.tracker}: [yellow]HD bitrate is {bitrate} kbps; the forum normally requires at least {minimum} kbps. "
                    "TV/internet captures require a manual quality review.[/yellow]"
                )

        release = self._release_tokens(meta)
        prohibited_release = re.search(
            r"(?:^|[. _-])(cam|telesync|ts|telecine|tc|r5|dvdscr(?:eener)?|hdrip|vodrip|axxo|cm8|yify|yts|stuttershit)(?:$|[. _-])", release, re.IGNORECASE
        )
        if prohibited_release:
            logger.warning(f"{self.tracker}: [bold red]Prohibited/low-quality release marker found: {prohibited_release.group(1)}.[/bold red]")
            return False

        prohibited_files = {".zip", ".rar", ".7z", ".exe", ".msi", ".bat", ".cmd", ".com", ".scr", ".ps1", ".sh"}
        bad_file = next((Path(str(item)).name for item in getattr(meta, "filelist", []) or [] if Path(str(item)).suffix.lower() in prohibited_files), "")
        if bad_file:
            logger.warning(f"{self.tracker}: [bold red]Torrent contains prohibited archive/executable file: {bad_file}.[/bold red]")
            return False

        if not self._has_portuguese_subtitle(meta) and str(meta.original_language).lower() != "pt":
            logger.warning(f"{self.tracker}: [bold red]A Portuguese subtitle is required for this forum.[/bold red]")
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
        logger.info(f"{self.tracker}: [green]Selected subforum:[/green] {forum_id} ")
        # Extract before creating the torrent so a non-hardcoded embedded
        # Portuguese subtitle can be included in the torrent as well as
        # attached separately to the forum post.
        sub_files = await self._get_portuguese_subtitles(meta)
        if not sub_files and not getattr(meta, "hardcoded_subs", False) and not meta.debug:
            logger.warning(f"{self.tracker}: [bold red]Unable to provide a separate Portuguese subtitle file.[/bold red]")
            meta["tracker_status"][self.tracker]["status_message"] = "Upload blocked: no separate Portuguese subtitle file."
            return False

        if sub_files:
            existing = list(getattr(meta, "subtitle_files", []) or [])
            meta.subtitle_files = list(dict.fromkeys([*existing, *sub_files]))

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

        # Zip subtitles to comply with MakingOff allowed formats (.torrent, .rar, .zip)
        if sub_files:
            temp_dir = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}"
            zip_path = str(Path(temp_dir) / f"{release_filename}.legendas.zip")
            try:
                with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
                    for sub_file in sub_files:
                        zipf.write(sub_file, arcname=Path(sub_file).name)
                logger.info(f"{self.tracker}: [green]Zipped {len(sub_files)} subtitles to {Path(zip_path).name}[/green]")
                sub_files = [zip_path]
            except (OSError, zipfile.BadZipFile) as e:
                logger.error(f"{self.tracker}: [red]Failed to create zip file for subtitles: {e}[/red]")
                if not meta.debug:
                    meta["tracker_status"][self.tracker]["status_message"] = "data error: Failed to package Portuguese subtitles."
                    return False
                sub_files = []

        if meta.debug:
            topic_title = await self.get_name(meta)
            post_body = await self.generate_description(meta)
            topic_tags = self._topic_tags(meta, post_body)

            fields = self.get_topic_fields(
                forum_id=forum_id,
                csrf_token="DEBUG_CSRF",  # noqa: S106
                attachment_hash="DEBUG_HASH",
                attachment_hash_combined="DEBUG_COMBINED",
                topic_title=topic_title,
                post_body=post_body,
                prefix_id=f"DEBUG:{self._topic_prefix_category(meta)}",
                topic_tags=topic_tags,
            )

            logger.info(f"{self.tracker}: [cyan]Request Data:[/cyan]")
            logger.info(Redaction.redact_private_info(fields), extra={"markup": False})

            if sub_files:
                logger.info(f"{self.tracker}: [cyan]Debug Subtitles to upload:[/cyan] {sub_files}")

            txt_path = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/[{self.tracker}]DESCRIPTION.txt"
            async with aiofiles.open(txt_path, "w", encoding="utf-8") as f:
                await f.write(f"TITULO: {topic_title}\n\n")
                await f.write(post_body)
            logger.info(f"{self.tracker}: [yellow]BBCode saved.[/yellow] {txt_path}")
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

        prefix_id = self._topic_prefix_id(meta)
        if not prefix_id:
            prefix_category = self._topic_prefix_category(meta)
            logger.warning(f"{self.tracker}: [bold red]Unable to resolve the required '{prefix_category}' topic prefix from the forum form.[/bold red]")
            meta["tracker_status"][self.tracker]["status_message"] = f"data error: Missing required topic prefix: {prefix_category}."
            return False

        if not await self.upload_attachment(named_torrent_path, csrf_token, attachment_hash, attachment_hash_combined, forum_id):
            meta["tracker_status"][self.tracker]["status_message"] = "data error: Failed to upload .torrent attachment."
            return False

        # Upload Portuguese subtitles if any
        for sub_file in sub_files:
            logger.info(f"{self.tracker}: [yellow]Uploading Portuguese subtitle as attachment:[/yellow] {Path(sub_file).name}")
            if not await self.upload_attachment(sub_file, csrf_token, attachment_hash, attachment_hash_combined, forum_id):
                meta["tracker_status"][self.tracker]["status_message"] = "data error: Failed to upload Portuguese subtitle attachment."
                return False

        topic_title = await self.get_name(meta)
        post_body = await self.generate_description(meta)
        topic_tags = self._topic_tags(meta, post_body)

        topic_url = await self.create_topic(
            forum_id=forum_id,
            csrf_token=csrf_token,
            attachment_hash=attachment_hash,
            attachment_hash_combined=attachment_hash_combined,
            topic_title=topic_title,
            post_body=post_body,
            prefix_id=prefix_id,
            topic_tags=topic_tags,
        )

        if topic_url:
            meta["tracker_status"][self.tracker]["status_message"] = "Upload successful"
            meta["tracker_status"][self.tracker]["torrent_id"] = topic_url
            return True

        meta["tracker_status"][self.tracker]["status_message"] = "data error: Failed creating the forum topic."
        return False
