# Upload Assistant © 2026 Audionut & wastaken7 — Licensed under UAPL v1.0
"""Simurg: private Gazelle library tracker for e-books, audiobooks and comics.

API reference: https://simurg.world/wiki.php?action=article&name=api
Upload rules: https://simurg.world/rules.php?p=upload
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import platform
import re
import time
import unicodedata
import weakref
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar, cast
from urllib.parse import urlparse

import bencodepy
import httpx
from rich.markup import escape

from src import payload_preview
from src.console import logger
from src.get_desc import book_overview_to_bbcode
from src.manual_input import Question, ask, choices_from
from src.meta import Meta
from src.trackers.common import Common

# Upload category values from the upload form (not the one-based IDs in API results).
UPLOAD_TYPES: dict[str, int] = {"ebook": 2, "audiobook": 3, "comic": 6, "magazine": 7}
KIND_LABELS: dict[str, str] = {"ebook": "E-Books", "audiobook": "Audiobooks", "comic": "Comics & Manga", "magazine": "Magazines"}
LANGUAGES = ("English", "Turkish", "Japanese")
EBOOK_FORMATS: dict[str, str] = {".epub": "EPUB", ".pdf": "PDF", ".mobi": "MOBI", ".azw3": "AZW3", ".djvu": "DJVU"}
COMIC_FORMATS: dict[str, str] = {".cbr": "CBR", ".cbz": "CBZ", ".pdf": "PDF"}
AUDIOBOOK_FORMATS: dict[str, str] = {".mp3": "MP3", ".m4b": "M4B", ".flac": "FLAC"}
# Audio files accepted as the explained "Other" audiobook format.
OTHER_AUDIO_EXTENSIONS = frozenset({".m4a", ".aac", ".ogg", ".opus", ".wav", ".alac"})
TEXT_SOURCES = ("Retail", "Scan", "OCR", "Convert", "Other")
AUDIOBOOK_SOURCES = ("Retail", "Scene", "WEB", "Scan", "Other")
AUDIOBOOK_TYPES = ("Unabridged", "Abridged", "Dramatized")
COMIC_TYPES = ("Comic", "Graphic Novel", "Manga", "Manhwa", "Manhua", "Webtoon")
AUDIO_BITRATES = (320, 256, 192, 160, 128, 96, 64)
AUDIO_CODECS: dict[str, str] = {"aac": "AAC", "mpeg audio": "MP3", "mp3": "MP3", "flac": "FLAC", "alac": "ALAC", "opus": "Opus", "vorbis": "Vorbis", "pcm": "PCM"}
# Gazelle artist "importance" values used by the book forms.
ROLES: dict[str, int] = {"author": 1, "translator": 3, "editor": 4, "narrator": 5, "illustrator": 6}
# Format, source and praise words are not content tags (Uploading Rules, "Tag content, not files").
NON_CONTENT_TAGS = frozenset(
    {
        "abridged",
        "audio.book",
        "audiobook",
        "audiobooks",
        "azw3",
        "best",
        "book",
        "books",
        "cbr",
        "cbz",
        "convert",
        "djvu",
        "e.book",
        "e.books",
        "ebook",
        "ebooks",
        "epub",
        "flac",
        "general",
        "m4b",
        "mobi",
        "mp3",
        "must.read",
        "ocr",
        "pdf",
        "retail",
        "scan",
        "unabridged",
    }
)
MAX_TAGS = 10
_DESTINATION = re.compile(r"^(?:new|\d+|release:\d+)$", re.IGNORECASE)

# One request pacer per event loop, shared by every Simurg instance.
_pacing_locks: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock] = weakref.WeakKeyDictionary()


@dataclass(frozen=True)
class Answers:
    """Facts that cannot be read from the files and are asked at upload time."""

    source: str
    audiobook_type: str = ""
    comic_type: str = ""
    publication_id: str = ""
    group_id: str = ""


def _validate_destination(value: Any) -> str | None:
    return None if _DESTINATION.match(str(value).strip()) else "Type new, a Publication ID, or release:<Release ID>."


class Simurg:
    """Simurg is a private Gazelle tracker for e-books, audiobooks and comics & manga."""

    tracker = "SIMURG"
    display_name = "Simurg"
    auth_type = "other_api"
    supported_categories = ("BOOK",)
    source_flag = "Simurg"
    base_url = "https://simurg.world"
    tracker_urls = ("tracker.simurg.world",)
    banned_groups = ()
    # A Release cover must not hotlink a source tracker.
    banned_image_hosts = ("myanonamouse.net", "simurg.world")

    # The API allows 5 requests in any 10 seconds, and less on some endpoints.
    min_request_interval = 2.5
    rate_limit_pause = 12.0
    _last_request_at: ClassVar[float] = 0.0
    max_expanded_groups = 3

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        settings = config.get("TRACKERS", {}).get(self.tracker, {})
        self.api_key = str(settings.get("api_key", "")).strip()
        self.announce_url = str(settings.get("announce_url", "")).strip()
        self.torrent_url = f"{self.base_url}/torrents.php?torrentid="
        self.common = Common(config)
        self._browse_cache: dict[str, list[dict[str, Any]]] = {}

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------

    def _headers(self, meta: Meta) -> dict[str, str]:
        product = str(meta.ua_name or "Upload Assistant").strip() or "Upload Assistant"
        version = str(meta.current_version or "").strip()
        user_agent = f"{product}{f' {version}' if version else ''} ({platform.system()} {platform.release()})"
        return {"Authorization": f"token {self.api_key}", "User-Agent": user_agent}

    async def _pace(self) -> None:
        """Space every request so all Simurg calls stay well inside the rate limit."""
        loop = asyncio.get_running_loop()
        lock = _pacing_locks.setdefault(loop, asyncio.Lock())
        async with lock:
            wait = Simurg._last_request_at + self.min_request_interval - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            Simurg._last_request_at = time.monotonic()

    async def _api_get(self, meta: Meta, params: dict[str, str], purpose: str) -> dict[str, Any]:
        """Run one read-only ``ajax.php`` GET and return its ``response`` object.

        Raises ``RuntimeError`` with a readable reason. A rate-limit answer is
        retried once after a pause; nothing else is repeated.
        """
        for attempt in range(2):
            await self._pace()
            try:
                async with httpx.AsyncClient(timeout=httpx.Timeout(20.0), headers=self._headers(meta)) as client:
                    response = await client.get(f"{self.base_url}/ajax.php", params=params)
            except httpx.HTTPError as error:
                raise RuntimeError(f"{purpose} failed: {error or type(error).__name__}") from error
            try:
                payload: Any = response.json()
            except ValueError as error:
                raise RuntimeError(f"{purpose} failed: HTTP {response.status_code}, not a JSON reply") from error
            body = cast(dict[str, Any], payload) if isinstance(payload, dict) else {}
            error_text = str(body.get("error") or "").strip()
            limited = response.status_code == 429 or "rate limit" in error_text.casefold()
            if limited and attempt == 0:
                logger.info(f"{self.tracker}: [yellow]rate limited during {purpose}; waiting {self.rate_limit_pause:g} seconds.[/yellow]")
                await asyncio.sleep(self.rate_limit_pause)
                continue
            result = body.get("response")
            if response.status_code != 200 or body.get("status") != "success" or not isinstance(result, dict):
                raise RuntimeError(f"{purpose} failed: {error_text or f'HTTP {response.status_code}'}")
            return cast(dict[str, Any], result)
        raise RuntimeError(f"{purpose} failed: rate limit exceeded")

    async def _browse(self, meta: Meta, query: str) -> list[dict[str, Any]]:
        if query not in self._browse_cache:
            response = await self._api_get(meta, {"action": "browse", "searchstr": query}, "duplicate search")
            results = response.get("results")
            self._browse_cache[query] = [cast(dict[str, Any], item) for item in cast(list[Any], results if isinstance(results, list) else []) if isinstance(item, dict)]
        return self._browse_cache[query]

    # ------------------------------------------------------------------
    # Release facts
    # ------------------------------------------------------------------

    @staticmethod
    def _kind(meta: Meta) -> str:
        if meta.audiobook:
            return "audiobook"
        if meta.newspaper:
            return "newspaper"
        if meta.magazine:
            return "magazine"
        suffixes = {Path(file).suffix.lower() for file in meta.filelist or []}
        if meta.comic or meta.manga or suffixes & {".cbr", ".cbz"}:
            return "comic"
        return "ebook"

    @staticmethod
    def _content_files(meta: Meta, kind: str) -> list[str]:
        files = [str(file) for file in meta.filelist or []]
        if kind == "audiobook":
            return [file for file in files if Path(file).suffix.lower() in {*AUDIOBOOK_FORMATS, *OTHER_AUDIO_EXTENSIONS}] or files
        # Small text sidecars do not decide the format.
        return [file for file in files if Path(file).suffix.lower() not in {".txt", ".html", ".htm", ".nfo"}] or files

    def _format(self, meta: Meta, kind: str) -> tuple[str, str]:
        """Return ``(format, problem)``; one of them is empty."""
        suffixes = sorted({Path(file).suffix.lower() for file in self._content_files(meta, kind)})
        if not suffixes:
            return "", "no book or audiobook files were found"
        if kind == "audiobook":
            names = {AUDIOBOOK_FORMATS.get(suffix) or ("Other" if suffix in OTHER_AUDIO_EXTENSIONS else "") for suffix in suffixes}
            allowed = "MP3, M4B, FLAC or explained Other audio"
        else:
            table = COMIC_FORMATS if kind == "comic" else EBOOK_FORMATS
            names = {table.get(suffix, "") for suffix in suffixes}
            allowed = ", ".join(dict.fromkeys(table.values()))
        if "" in names:
            return "", f"{KIND_LABELS.get(kind, kind)} accept only {allowed}; found {', '.join(suffixes)}"
        if len(names) > 1:
            return "", f"one torrent must hold a single format; found {', '.join(sorted(names))}"
        return names.pop(), ""

    @staticmethod
    def _language(meta: Meta) -> str:
        language = str(meta.book_language or "").strip().casefold()
        return next((name for name in LANGUAGES if name.casefold() == language), "")

    @staticmethod
    def _names(value: Any) -> list[str]:
        """Split a contributor credit only where the parts are full names, never "Surname, Name"."""
        text = str(value or "").strip()
        if not text:
            return []
        parts = [part.strip() for part in re.split(r"\s*(?:;|&|\band\b|,)\s*", text) if part.strip()]
        if len(parts) > 1 and all(" " in part for part in parts):
            return list(dict.fromkeys(parts))
        return [text]

    def _contributors(self, meta: Meta, kind: str) -> list[tuple[str, int]]:
        credits: list[tuple[str, int]] = [(name, ROLES["author"]) for name in self._names(meta.author or meta.book_author)]
        if kind == "audiobook":
            credits.extend((name, ROLES["narrator"]) for name in self._names(meta.narrator or meta.book_narrator))
        credits.extend((name, ROLES["translator"]) for name in self._names(meta.book_translator))
        return list(dict.fromkeys(credits))

    @staticmethod
    def _tag(value: str) -> str:
        text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii").casefold().replace("&", " and ")
        return re.sub(r"[^a-z0-9]+", ".", text).strip(".")

    def _tags(self, meta: Meta) -> list[str]:
        raw: list[str] = []
        for source in (meta.genres, meta.keywords):
            values = source.split(",") if isinstance(source, str) else list(source or [])
            for value in values:
                raw.extend(part for part in re.split(r"[,/;|]", str(value)) if part.strip())
        tags: list[str] = []
        for value in raw:
            tag = self._tag(value)
            if tag and tag not in NON_CONTENT_TAGS and tag not in tags and len(tag) <= 50:
                tags.append(tag)
        return tags[:MAX_TAGS]

    @staticmethod
    def _year(value: Any) -> str:
        text = str(value or "").strip()
        return text if re.fullmatch(r"\d{4}", text) else ""

    @staticmethod
    def _isbn(meta: Meta) -> str:
        digits = re.sub(r"[^0-9Xx]", "", str(meta.isbn or meta.book_isbn or ""))
        return digits.upper() if len(digits) in (10, 13) else ""

    def _cover_url(self, meta: Meta) -> str:
        """A clean direct image link: the hosted artwork, else a public URL not on a tracker."""
        candidates = [str(item.get("raw_url") or "") for item in meta.hosted_artwork or []]
        candidates.append(str(meta.artwork_url or ""))
        for value in candidates:
            parsed = urlparse(value.strip())
            host = (parsed.hostname or "").casefold()
            if parsed.scheme in {"http", "https"} and host and not any(host == banned or host.endswith(f".{banned}") for banned in self.banned_image_hosts):
                return value.strip()
        return ""

    @staticmethod
    def _page_count(kind: str, files: list[str]) -> str:
        if kind == "audiobook" or len(files) != 1:
            return ""
        path = Path(files[0])
        suffix = path.suffix.lower()
        with contextlib.suppress(Exception):
            if suffix == ".pdf":
                import pymupdf

                with pymupdf.open(path) as document:
                    return str(len(document))
            if suffix == ".cbz":
                with zipfile.ZipFile(path) as archive:
                    pages = [name for name in archive.namelist() if name.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".gif"))]
                    return str(len(pages)) if pages else ""
        return ""

    @staticmethod
    def _audio_track(meta: Meta) -> dict[str, Any]:
        mediainfo: Any = meta.mediainfo
        media: Any = cast(dict[str, Any], mediainfo).get("media") if isinstance(mediainfo, dict) else None
        tracks: Any = cast(dict[str, Any], media).get("track") if isinstance(media, dict) else None
        for track in cast(list[Any], tracks if isinstance(tracks, list) else []):
            if isinstance(track, dict) and cast(dict[str, Any], track).get("@type") == "Audio":
                return cast(dict[str, Any], track)
        return {}

    def _audio_codec(self, meta: Meta, format_name: str) -> str:
        codec = AUDIO_CODECS.get(str(self._audio_track(meta).get("Format") or "").strip().casefold(), "")
        return codec or {"MP3": "MP3", "FLAC": "FLAC", "M4B": "AAC"}.get(format_name, "Unknown")

    def _audio_bitrate(self, meta: Meta, format_name: str) -> tuple[str, str]:
        """Return the form bitrate and, for "Other", the free-text value."""
        track = self._audio_track(meta)
        if format_name == "FLAC" or self._audio_codec(meta, format_name) in ("FLAC", "ALAC", "PCM"):
            return ("24bit Lossless" if str(track.get("BitDepth") or "") == "24" else "Lossless"), ""
        kbps = meta.audiobook_bitrate
        if not kbps:
            return "", ""
        closest = min(AUDIO_BITRATES, key=lambda option: abs(option - kbps))
        if abs(closest - kbps) <= closest * 0.05:
            return str(closest), ""
        return "Other", f"{kbps} kbps"

    @staticmethod
    def _duration(meta: Meta) -> tuple[int, int]:
        seconds = float(meta.audiobook_duration or 0)
        if seconds <= 0:
            return 0, 0
        minutes = max(1, round(seconds / 60))
        return minutes // 60, minutes % 60

    # ------------------------------------------------------------------
    # Upload rules
    # ------------------------------------------------------------------

    def _problems(self, meta: Meta) -> list[str]:
        kind = self._kind(meta)
        if kind == "newspaper":
            return ["Newspapers are outside Simurg's Magazines category"]
        if kind == "magazine":
            return ["Magazine uploads need structured issue or pack metadata; upload them with the site's Magazine form"]
        problems: list[str] = []
        format_problem = self._format(meta, kind)[1]
        if format_problem:
            problems.append(format_problem)
        if not self._language(meta):
            problems.append(f"language '{meta.book_language or 'unknown'}' is not offered by Simurg ({', '.join(LANGUAGES)}); set it with --book-language")
        if not str(meta.title or "").strip():
            problems.append("the title is missing")
        if not self._year(meta.year):
            problems.append("the release year is missing")
        if not any(role == ROLES["author"] for _name, role in self._contributors(meta, kind)):
            problems.append("an author is required; set it with --author")
        if kind == "audiobook" and self._duration(meta) == (0, 0):
            problems.append("the audiobook duration could not be read")
        return problems

    async def get_additional_checks(self, meta: Meta) -> bool:
        problems = self._problems(meta)
        if not problems:
            if not self._tags(meta):
                logger.warning(f"{self.tracker}: [yellow]no genre tags were found; a new Release needs them (use --genres).[/yellow]")
            return True
        message = "Upload blocked: " + "; ".join(problems) + "."
        meta.tracker_status.setdefault(self.tracker, {})["status_message"] = message
        logger.error(f"{self.tracker}: [red]{escape(message)}[/red]")
        return False

    # ------------------------------------------------------------------
    # Duplicate review
    # ------------------------------------------------------------------

    @staticmethod
    def _norm(value: Any) -> str:
        text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii").casefold()
        return " ".join(re.findall(r"[a-z0-9]+", text))

    @classmethod
    def _title_matches(cls, ours: Any, theirs: Any) -> bool:
        mine, other = cls._norm(ours), cls._norm(theirs)
        return bool(mine and other) and (mine == other or f" {mine} " in f" {other} " or f" {other} " in f" {mine} ")

    @staticmethod
    def _result_kind(category: Any) -> str:
        text = str(category or "").casefold()
        if "audio" in text:
            return "audiobook"
        if "comic" in text or "manga" in text:
            return "comic"
        if "magazine" in text:
            return "magazine"
        return "ebook"

    @staticmethod
    def _file_names(file_list: Any) -> list[str]:
        """Parse Gazelle's ``name{{{size}}}|||name{{{size}}}`` file list into base names."""
        names: list[str] = []
        for item in str(file_list or "").split("|||"):
            name = re.sub(r"\{\{\{\d+\}\}\}$", "", item).strip()
            if name:
                names.append(Path(name.replace("\\", "/")).name)
        return names

    async def search_existing(self, meta: Meta) -> list[dict[str, Any]]:
        """List the torrents of matching Releases with one browse and a few Release lookups."""
        title = str(meta.title or "").strip()
        kind = self._kind(meta)
        if not title or not self.api_key or kind not in UPLOAD_TYPES:
            return []
        groups = [group for group in await self._browse(meta, title) if self._result_kind(group.get("category")) == kind]

        dupes: list[dict[str, Any]] = []
        expanded = 0
        for group in groups:
            group_id = str(group.get("groupId") or "")
            group_name = str(group.get("groupName") or "")
            details: dict[str, Any] = {}
            if group_id and expanded < self.max_expanded_groups and self._title_matches(title, group_name):
                expanded += 1
                try:
                    details = await self._api_get(meta, {"action": "torrentgroup", "id": group_id}, f"Release lookup for {group_id}")
                except RuntimeError as error:
                    logger.warning(f"{self.tracker}: [yellow]{escape(str(error))}[/yellow]")
            torrents = details.get("torrents") or group.get("torrents") or ([group] if group.get("torrentId") else [])
            artist = str(group.get("artist") or "")
            year = group.get("groupYear") or cast(dict[str, Any], details.get("group") or {}).get("year") or ""
            for item in cast(list[Any], torrents if isinstance(torrents, list) else []):
                if not isinstance(item, dict):
                    continue
                torrent = cast(dict[str, Any], item)
                torrent_id = torrent.get("torrentId") or torrent.get("id")
                format_name = str(torrent.get("format") or "")
                source = str(torrent.get("encoding") or "")
                files = self._file_names(torrent.get("fileList"))
                label = " / ".join(part for part in (format_name, source) if part)
                dupes.append(
                    {
                        "name": " ".join(part for part in (group_name, f"by {artist}" if artist else "", f"[{year}]" if year else "", label) if part),
                        "size": torrent.get("size"),
                        "id": torrent_id,
                        "link": f"{self.base_url}/torrents.php?id={group_id}&torrentid={torrent_id}" if group_id and torrent_id else None,
                        "type": "audiobook" if kind == "audiobook" else format_name.lower(),
                        "files": files,
                        "file_count": torrent.get("fileCount") or len(files) or "",
                    }
                )
        return dupes

    # ------------------------------------------------------------------
    # Questions
    # ------------------------------------------------------------------

    async def _ask_choice(self, meta: Meta, key: str, prompt: str, values: tuple[str, ...], default: str = "", hint: str = "") -> str:
        answer = await ask(
            meta,
            Question(
                key=key,
                kind="choice",
                prompt=f"{self.tracker}: {prompt}",
                title=f"{self.display_name} {prompt.casefold()}",
                choices=choices_from(values),
                default=default or None,
                hint=hint,
                summary={"Tracker": self.tracker, "Release": meta.title or meta.name},
                tracker=self.tracker,
                unattended="default" if default else "skip_tracker",
            ),
        )
        return str(answer or "")

    async def _publication_candidates(self, meta: Meta) -> list[dict[str, Any]] | None:
        """Existing Publications whose canonical title matches, or None when the lookup failed."""
        try:
            await self._pace()
            async with httpx.AsyncClient(timeout=httpx.Timeout(20.0), headers=self._headers(meta)) as client:
                response = await client.get(f"{self.base_url}/ajax.php", params={"action": "publication_autocomplete", "query": str(meta.title)})
            payload: Any = response.json()
        except (httpx.HTTPError, ValueError) as error:
            logger.warning(f"{self.tracker}: [yellow]Publication search failed: {error or type(error).__name__}[/yellow]")
            return None
        suggestions = cast(dict[str, Any], payload).get("suggestions") if isinstance(payload, dict) else None
        if response.status_code != 200 or not isinstance(suggestions, list):
            logger.warning(f"{self.tracker}: [yellow]Publication search failed: HTTP {response.status_code}[/yellow]")
            return None
        return [
            cast(dict[str, Any], item)
            for item in cast(list[Any], suggestions)
            if isinstance(item, dict) and self._title_matches(meta.title, cast(dict[str, Any], item).get("canonical_title") or cast(dict[str, Any], item).get("value"))
        ]

    def _confident_publication(self, meta: Meta, candidates: list[dict[str, Any]]) -> str:
        """The single candidate with the same title and author, if exactly one exists."""
        authors = {self._norm(name) for name, role in self._contributors(meta, self._kind(meta)) if role == ROLES["author"]}
        title = self._norm(meta.title)
        matches: list[str] = []
        for item in candidates:
            canonical = self._norm(item.get("canonical_title"))
            # Series Publications are titled like "Series 2: Title".
            same_title = title in (canonical, re.sub(r"^.*?\d+\s+", "", canonical))
            same_author = bool(authors & {self._norm(name) for name in str(item.get("authors") or "").split(",")})
            if same_title and same_author:
                matches.append(str(item.get("data")))
        return matches[0] if len(matches) == 1 else ""

    async def _destination(self, meta: Meta, format_name: str) -> tuple[str, str] | None:
        """Return ``(publication_id, group_id)``; empty strings create them. None stops the upload.

        Simurg requires reusing the Publication of the same work, so existing
        ones are offered first; an existing Release can take another format.
        """
        kind = self._kind(meta)
        candidates = await self._publication_candidates(meta)
        releases: list[dict[str, Any]] = []
        with contextlib.suppress(RuntimeError):
            for group in await self._browse(meta, str(meta.title)):
                formats = {str(cast(dict[str, Any], torrent).get("format") or "") for torrent in cast(list[Any], group.get("torrents") or []) if isinstance(torrent, dict)}
                if self._result_kind(group.get("category")) == kind and self._title_matches(meta.title, group.get("groupName")) and format_name not in formats:
                    releases.append(group)
        if candidates == [] and not releases:
            return "", ""

        summary: dict[str, Any] = {"Tracker": self.tracker, "Release": meta.title}
        for item in (candidates or [])[:8]:
            summary[f"Publication {item.get('data')}"] = str(item.get("value") or item.get("canonical_title") or "")
        for group in releases[:5]:
            formats = ", ".join(sorted({str(cast(dict[str, Any], t).get("format") or "?") for t in cast(list[Any], group.get("torrents") or []) if isinstance(t, dict)})) or "?"
            summary[f"release:{group.get('groupId')}"] = f"{group.get('groupName')} by {group.get('artist') or '?'} ({formats})"
        default = self._confident_publication(meta, candidates or [])
        lookup_note = "" if candidates is not None else " The Publication search failed; check the site before choosing new."
        answer = await ask(
            meta,
            Question(
                key="simurg.destination",
                kind="text",
                prompt=f"{self.tracker}: Publication for this Release (new, a Publication ID, or release:<ID> to add a format to that Release)",
                title=f"{self.display_name} Publication",
                default=default or None,
                hint="Reuse the Publication of the same work; add to an existing Release only for the same edition in another format." + lookup_note,
                placeholder="new",
                summary=summary,
                tracker=self.tracker,
                unattended="default" if default else "skip_tracker",
                validate=_validate_destination,
            ),
        )
        value = str(answer or "").strip().casefold()
        if not value:
            return None
        if value == "new":
            return "", ""
        if value.startswith("release:"):
            return "", value.removeprefix("release:")
        return value, ""

    async def _answers(self, meta: Meta, format_name: str) -> Answers | None:
        kind = self._kind(meta)
        sources = AUDIOBOOK_SOURCES if kind == "audiobook" else TEXT_SOURCES
        source = await self._ask_choice(
            meta,
            "simurg.source",
            "Source of the files",
            sources,
            hint="Retail only for born-digital files from an authorized retailer; Other needs an explanation in the description.",
        )
        if not source:
            return None
        audiobook_type = comic_type = ""
        if kind == "audiobook":
            detected = str(meta.edition or "").strip().capitalize()
            audiobook_type = await self._ask_choice(meta, "simurg.audiobook_type", "Audiobook type", AUDIOBOOK_TYPES, default=detected if detected in AUDIOBOOK_TYPES else "")
            if not audiobook_type:
                return None
        if kind == "comic":
            comic_type = await self._ask_choice(meta, "simurg.comic_type", "Comic type", COMIC_TYPES, default="Manga" if meta.manga else "")
            if not comic_type:
                return None
        destination = await self._destination(meta, format_name)
        if destination is None:
            return None
        return Answers(source=source, audiobook_type=audiobook_type, comic_type=comic_type, publication_id=destination[0], group_id=destination[1])

    # ------------------------------------------------------------------
    # Upload form
    # ------------------------------------------------------------------

    def _release_notes(self, meta: Meta, kind: str) -> str:
        lines: list[str] = []
        if meta.book_series:
            lines.append(f"Series: {meta.book_series}{f' #{meta.book_series_index}' if meta.book_series_index else ''}")
        if meta.edition and kind != "audiobook":
            lines.append(f"Edition: {meta.edition}")
        if meta.publisher:
            lines.append(f"Publisher: {meta.publisher}")
        if self._isbn(meta):
            lines.append(f"ISBN: {self._isbn(meta)}")
        if kind == "audiobook" and meta.asin:
            lines.append(f"ASIN: {meta.asin}")
        if meta.book_translator:
            lines.append(f"Translator: {meta.book_translator}")
        return "\n".join(lines)

    def _release_description(self, meta: Meta, kind: str, format_name: str, source: str, files: list[str]) -> str:
        lines = [f"Format: {format_name}", f"Source: {source}"]
        if kind == "audiobook":
            hours, minutes = self._duration(meta)
            lines.append(f"Duration: {meta.audiobook_duration_formatted or f'{hours}h {minutes:02d}m'}")
            lines.append(f"Codec: {self._audio_codec(meta, format_name)}")
            if meta.audiobook_bitrate:
                lines.append(f"Average bitrate: {meta.audiobook_bitrate} kbps")
        pages = self._page_count(kind, files)
        if pages:
            lines.append(f"Pages: {pages}")
        root = Path(str(meta.path or ""))
        names: list[str] = []
        for file in files:
            path = Path(file)
            with contextlib.suppress(ValueError):
                path = path.relative_to(root)
            names.append(path.as_posix() if root.is_dir() else path.name)
        lines.append(f"Files ({len(names)}):")
        lines.extend(f"- {name}" for name in names[:200])
        if len(names) > 200:
            lines.append(f"- … and {len(names) - 200} more")
        return "\n".join(lines)

    def build_upload_payload(self, meta: Meta, answers: Answers) -> dict[str, Any]:
        kind = self._kind(meta)
        format_name, _problem = self._format(meta, kind)
        files = self._content_files(meta, kind)
        data: dict[str, Any] = {
            "type": UPLOAD_TYPES[kind],
            "format": format_name,
            "release_desc": self._release_description(meta, kind, format_name, answers.source, files),
        }
        if kind == "audiobook":
            bitrate, other_bitrate = self._audio_bitrate(meta, format_name)
            data.update({"bitrate": bitrate, "media": answers.source, "audio_codec": self._audio_codec(meta, format_name)})
            if other_bitrate:
                data["other_bitrate"] = other_bitrate
        else:
            data["bitrate"] = answers.source
        if answers.group_id:
            # Another torrent of an existing Release only carries torrent-level fields.
            data["groupid"] = answers.group_id
            return {key: value for key, value in data.items() if value not in ("", None)}

        contributors = self._contributors(meta, kind)
        data.update(
            {
                "title": str(meta.title or "").strip(),
                "year": self._year(meta.year),
                "language": self._language(meta),
                "tags": ", ".join(self._tags(meta)),
                "image": self._cover_url(meta),
                "record_label": str(meta.publisher or "").strip(),
                "catalogue_number": self._isbn(meta),
                "album_desc": self._release_notes(meta, kind),
                "artists[]": [name for name, _role in contributors],
                "importance[]": [role for _name, role in contributors],
            }
        )
        if kind == "audiobook":
            hours, minutes = self._duration(meta)
            data.update({"audiobook_type": answers.audiobook_type, "duration_hours": hours, "duration_minutes": minutes})
        else:
            data["page_count"] = self._page_count(kind, files)
        if kind == "comic":
            data["comic_type"] = answers.comic_type
        if answers.publication_id:
            data["publicationid"] = answers.publication_id
        else:
            data["book_title"] = str(meta.title or "").strip()
            data["book_desc"] = book_overview_to_bbcode(str(meta.overview or "")).strip() if meta.overview else ""
        return {key: value for key, value in data.items() if value not in ("", None, [])}

    @staticmethod
    def _missing_fields(data: dict[str, Any]) -> list[str]:
        missing: list[str] = []
        if "groupid" not in data and not data.get("tags"):
            missing.append("genre tags for the new Release (use --genres)")
        if "groupid" not in data and "publicationid" not in data and len(str(data.get("book_desc") or "")) < 10:
            missing.append("a synopsis of at least 10 characters for the new Publication (use --overview)")
        if not data.get("bitrate"):
            missing.append("the audio bitrate")
        return missing

    async def get_name(self, meta: Meta) -> str:
        """For the terminal display only; Simurg names Releases from their fields."""
        kind = self._kind(meta)
        format_name = self._format(meta, kind)[0] if kind in UPLOAD_TYPES else ""
        author = str(meta.author or "").strip()
        year = self._year(meta.year)
        return " ".join(part for part in (f"{author} -" if author else "", str(meta.title or meta.name or "").strip(), f"[{year}]" if year else "", format_name) if part)

    async def get_payload_preview(self, meta: Meta) -> payload_preview.TrackerPreview:
        """The upload form as known before the upload-time questions, for the Web UI to show and edit."""
        asked = payload_preview.Later("Asked at upload time")
        answers = Answers(source=asked, audiobook_type=asked, comic_type=asked)
        specs = {
            "type": payload_preview.choice("Category", {value: KIND_LABELS[kind] for kind, value in UPLOAD_TYPES.items()}),
            "title": payload_preview.text("Release title"),
            "book_title": payload_preview.text("Canonical Publication title"),
            "year": payload_preview.number("Release year"),
            "language": payload_preview.choice("Language", LANGUAGES),
            "format": payload_preview.readonly("Format"),
            "tags": payload_preview.text("Tags", max_length=1000),
            "image": payload_preview.text("Cover URL"),
            "record_label": payload_preview.text("Publisher"),
            "catalogue_number": payload_preview.text("ISBN"),
            "page_count": payload_preview.number("Page count"),
            "artists[]": payload_preview.readonly("Contributors"),
            "importance[]": payload_preview.readonly("Contributor roles"),
            "album_desc": payload_preview.readonly("Release notes"),
            "release_desc": payload_preview.readonly("Release description"),
            "book_desc": payload_preview.readonly("Publication synopsis"),
            "duration_hours": payload_preview.number("Duration (hours)"),
            "duration_minutes": payload_preview.number("Duration (minutes)"),
            "audio_codec": payload_preview.readonly("Audio codec"),
        }
        deferred = {"publicationid": "Chosen from the existing Publications at upload time", "file_input": "Attached at upload time"}
        data = self.build_upload_payload(meta, answers)
        return payload_preview.describe(self.tracker, data, specs, deferred=deferred, name=await self.get_name(meta))

    # ------------------------------------------------------------------
    # Upload
    # ------------------------------------------------------------------

    async def upload(self, meta: Meta) -> bool:
        status = meta.tracker_status.setdefault(self.tracker, {})
        problems = self._problems(meta)
        if problems:
            status["status_message"] = "Upload blocked: " + "; ".join(problems) + "."
            return False
        if not self.api_key or not self.announce_url:
            status["status_message"] = "Missing Simurg API token or announce URL."
            return False
        format_name = self._format(meta, self._kind(meta))[0]
        answers = await self._answers(meta, format_name)
        if answers is None:
            status["status_message"] = "Upload skipped: the source, type or Publication was not chosen."
            return False
        data = payload_preview.apply_payload_edits(meta, self.tracker, self.build_upload_payload(meta, answers))
        missing = self._missing_fields(data)
        if missing:
            status["status_message"] = "Upload blocked: missing " + "; ".join(missing) + "."
            return False

        if meta.debug:
            status["status_message"] = "Debug mode: upload skipped; payload prepared locally."
            status["debug_payload"] = {**data, "file_input": "<not created in debug mode>"}
            logger.info(f"{self.tracker}: [yellow]debug mode enabled; POST upload skipped. Prepared payload:[/yellow]")
            logger.info(json.dumps(status["debug_payload"], ensure_ascii=False, indent=2), extra={"markup": False})
            return True

        await self.common.create_torrent_for_upload(meta, self.tracker, self.source_flag, announce_url=self.announce_url)
        torrent_path = Path(meta.base_dir) / "tmp" / str(meta.uuid) / f"[{self.tracker}].torrent"
        if not torrent_path.is_file():
            status["status_message"] = "Tracker torrent was not created."
            return False
        payload = await self._post_upload(meta, data, torrent_path)
        if payload is None:
            return False
        accepted = self._record_upload_response(meta, payload)
        if accepted and not await self._download_site_torrent(meta):
            await self._write_torrent_comment(meta)
        return accepted

    async def _post_upload(self, meta: Meta, data: dict[str, Any], torrent_path: Path) -> Any:
        """POST the upload once; a failed or uncertain write is reported, never repeated."""
        status = meta.tracker_status.setdefault(self.tracker, {})
        await self._pace()
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(90.0), headers=self._headers(meta)) as client:
                with torrent_path.open("rb") as torrent_file:
                    files = {"file_input": (torrent_path.name, torrent_file, "application/x-bittorrent")}
                    # httpx expands list values into repeated artists[]/importance[] fields.
                    response = await client.post(f"{self.base_url}/ajax.php", params={"action": "upload"}, data=data, files=files)
            return response.json()
        except (httpx.ConnectError, httpx.ConnectTimeout, OSError) as error:
            status["status_message"] = f"Upload request failed before reaching Simurg: {error or type(error).__name__}"
        except (httpx.HTTPError, ValueError) as error:
            status["status_message"] = f"Upload request failed: {error or type(error).__name__}. The upload may still exist; check your uploads on Simurg before trying again."
        return None

    def _record_upload_response(self, meta: Meta, payload: Any) -> bool:
        status = meta.tracker_status.setdefault(self.tracker, {})
        if not isinstance(payload, dict):
            status["status_message"] = "Simurg returned a malformed upload response; check your uploads on the site."
            return False
        body = cast(dict[str, Any], payload)
        if body.get("status") != "success":
            error = str(body.get("error") or "").strip()
            status["status_message"] = f"Simurg rejected the upload: {error}" if error else "Simurg rejected the upload."
            return False
        result = body.get("response")
        if not isinstance(result, dict):
            status["status_message"] = "Simurg accepted the request but returned no upload result. Verify it on the tracker."
            return True
        result_dict = cast(dict[str, Any], result)
        for source_key, target_key in (("torrentId", "torrent_id"), ("groupId", "group_id")):
            if result_dict.get(source_key) is not None:
                status[target_key] = result_dict[source_key]
        warnings = [str(item).strip() for item in cast(list[Any], result_dict.get("warnings") or []) if str(item).strip()]
        # False means Simurg changed the uploaded torrent; only its own file then matches the infohash.
        status["site_changed_torrent"] = result_dict.get("private") is False or result_dict.get("source") is False
        status["warnings"] = warnings
        status["status_message"] = "Upload accepted by Simurg." + (f" Warnings: {' | '.join(warnings)}" if warnings else "")
        if warnings:
            logger.warning(f"{self.tracker}: [yellow]upload accepted with warning(s): {escape(' | '.join(warnings))}[/yellow]")
        return True

    async def _download_site_torrent(self, meta: Meta) -> bool:
        """Seed Simurg's own .torrent; it is the one whose infohash the tracker registered."""
        status = meta.tracker_status.setdefault(self.tracker, {})
        torrent_id = status.get("torrent_id")
        if torrent_id is None:
            return False
        await self._pace()
        downloaded = await self.common.download_tracker_torrent(
            meta, self.tracker, headers=self._headers(meta), params={"action": "download", "id": str(torrent_id)}, downurl=f"{self.base_url}/ajax.php"
        )
        if not downloaded:
            return False
        torrent_path = Path(meta.base_dir) / "tmp" / str(meta.uuid) / f"[{self.tracker}].torrent"
        try:
            decoded: Any = cast(Any, bencodepy).decode(torrent_path.read_bytes())
        except OSError, bencodepy.BencodeDecodeError:
            return False
        if not isinstance(decoded, dict) or b"info" not in decoded:
            return False
        status["torrent_link"] = self._link(status)
        status["torrent_source"] = "site"
        return True

    def _link(self, status: dict[str, Any]) -> str:
        torrent_id, group_id = status.get("torrent_id"), status.get("group_id")
        return f"{self.base_url}/torrents.php?id={group_id}&torrentid={torrent_id}" if group_id is not None else f"{self.torrent_url}{torrent_id}"

    async def _write_torrent_comment(self, meta: Meta) -> None:
        """Fallback when the site torrent could not be fetched: link the local torrent to the upload."""
        status = meta.tracker_status.setdefault(self.tracker, {})
        if status.get("torrent_id") is None:
            return
        link = self._link(status)
        status["torrent_link"] = link
        if status.get("site_changed_torrent"):
            message = f"Uploaded, but Simurg changed the torrent; download it from {link} before seeding."
            status["status_message"] = message
            logger.warning(f"{self.tracker}: [yellow]{message}[/yellow]")
            return
        try:
            await self.common.create_torrent_ready_to_seed(meta, self.tracker, self.source_flag, self.announce_url, link)
        except Exception as error:  # the upload already succeeded; never fail it here
            logger.warning(f"{self.tracker}: [yellow]could not write the torrent link into the client torrent: {error}[/yellow]")
