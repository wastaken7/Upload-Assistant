# Upload Assistant © 2026 Audionut & wastaken7 — Licensed under UAPL v1.0
"""Shared support for adult trackers that run the Luminance framework.

Luminance is a Gazelle fork. Its sites share one upload form (``upload.php``
with ``file_input``, ``category``, ``title``, ``taglist``, ``image``, ``desc``
and ``anonymous``), an advanced search on ``torrents.php`` and cookie logins
(``sid`` and ``cid``). Sites differ in their categories, approved image hosts
and a few extra fields, which the subclasses declare.
"""

from __future__ import annotations

import http.cookiejar
import platform
import re
import unicodedata
from pathlib import Path
from typing import Any, ClassVar, cast
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from src import payload_preview
from src.bbcode import BBCODE
from src.console import logger
from src.cookie_auth import CookieAuthUploader, CookieValidator
from src.description_review import get_base_description
from src.get_desc import DescriptionBuilder
from src.media_extensions import VIDEO_EXTENSIONS
from src.meta import Meta
from src.rehostimages import ImageHostPolicy, RehostImagesManager
from src.release_locks import release_image_lock
from src.takescreens import download_artwork_from_meta
from src.temp_paths import artwork_dir
from src.trackers.common import Common
from src.xxx_match import XxxRelease, is_pack_name

ARCHIVE_EXTENSIONS = frozenset({".rar", ".zip", ".7z", ".tar", ".gz"})
IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"})
GAME_EXTENSIONS = frozenset({".exe", ".apk", ".dmg"})
# Tags that describe the file rather than the content add nothing to a search.
_GENERIC_TAGS = frozenset({"xxx", "porn", "sex", "adult", "nude", "video", "videos", "hd", "full.hd", "scene", "scenes", "movie", "movies"})
# Picset words in a release name: the whole torrent is a picture set.
_PICSET_NAME = re.compile(r"(?i)(?:^|[._ \-\[(])(?:pics?|picset|photos?|imageset|images|gallery)(?:[._ \-\])]|$)")
_SITERIP_NAME = re.compile(r"(?i)(?:^|[._ \-\[(])(?:siterip|site[._ -]rip)(?:[._ \-\])]|$)")
_MOVIE_NAME = re.compile(r"(?i)(?:^|[._ -])(?:movie|feature|full[._ -]movie|dvdrip|vol(?:ume)?[._ -]?\d+)(?:[._ -]|$)")
_VR_NAME = re.compile(r"\b(?:vr|vr180|vr 180|180x180|3dh|oculus|quest|virtual reality)\b|\b[a-z0-9]{4,}vr\b")
_FANSITE_NAMES = re.compile(r"\b(?:onlyfans|fansly|fanvue|manyvids|fancentro|loyalfans|justforfans|clips4sale|pornhub|chaturbate|patreon)\b")


def normalize_tag(value: Any) -> str:
    """Turn a name into a Luminance tag: lower case, words joined by dots, accents dropped ("Éva" -> "eva")."""
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
    # Apostrophes join a word rather than split it ("Rock'n" -> "rockn"); the ASCII step already dropped typographic ones.
    text = text.casefold().replace("&", " and ").replace("'", "")
    return re.sub(r"[^a-z0-9]+", ".", text).strip(".")


def _words(value: Any) -> str:
    """Lower-case words of a name, for keyword searches."""
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()


class Luminance:
    """Base class for Luminance trackers; subclasses set the site details."""

    auth_type = "cookies"
    tracker = ""
    display_name = ""
    source_flag = ""
    base_url = ""
    tracker_urls: tuple[str, ...] = ()
    supported_categories = ("XXX",)
    banned_groups: tuple[str, ...] = ()
    approved_image_hosts: tuple[str, ...] = ()
    image_host_policy = ImageHostPolicy({}, ())
    # Upload category IDs: label -> value of the site's <select name="category">.
    category_ids: ClassVar[dict[str, str]] = {}
    default_category = ""
    # Whether the upload form has its own MediaInfo field; otherwise MediaInfo goes in the description.
    has_mediainfo_field = False
    min_tags = 1
    max_tags = 40

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.tracker_config: dict[str, Any] = cast(dict[str, Any], config.get("TRACKERS", {}).get(self.tracker, {}))
        self.common = Common(config)
        self.cookie_validator = CookieValidator(config)
        self.cookie_auth_uploader = CookieAuthUploader(config)
        self.rehost_images_manager = RehostImagesManager(config)
        self.upload_url = f"{self.base_url}/upload.php"
        self.torrent_url = f"{self.base_url}/torrents.php?id="
        self.cookie_jar: http.cookiejar.CookieJar | None = None
        self.session = httpx.AsyncClient(
            headers={"User-Agent": f"Upload-Assistant ({platform.system()} {platform.release()})"},
            timeout=60.0,
            follow_redirects=True,
        )

    # ------------------------------------------------------------------
    # Session
    # ------------------------------------------------------------------

    async def _load_cookies(self, meta: Meta) -> bool:
        cookie_jar = await self.cookie_validator.load_session_cookies(meta, self.tracker)
        # None means the file could not be loaded; an empty jar is falsy but valid.
        if cookie_jar is None:
            return False
        # httpx wraps this jar and writes cookies the site sets into it, so saving the jar keeps them.
        self.cookie_jar = cookie_jar
        self.session.cookies = cast(Any, cookie_jar)
        return True

    @staticmethod
    def _is_login_page(response: httpx.Response) -> bool:
        return "/login" in response.url.path or 'name="password"' in response.text

    @staticmethod
    def extract_auth_token(html: str) -> str:
        """Read the ``auth`` value of the upload form."""
        field = BeautifulSoup(html, "html.parser").select_one('form#upload_table input[name="auth"], input[name="auth"]')
        value = field.get("value") if field else ""
        return value if isinstance(value, str) else ""

    async def _upload_form_token(self, meta: Meta) -> str:
        """Open the upload form and return its auth token, or "" when the login is not valid."""
        response = await self.session.get(self.upload_url)
        if response.status_code != 200 or self._is_login_page(response):
            await self.cookie_validator.handle_validation_failure(meta, self.tracker, response.text)
            return ""
        token = self.extract_auth_token(response.text)
        if not token:
            await self.cookie_validator.handle_validation_failure(meta, self.tracker, response.text)
        return token

    async def validate_credentials(self, meta: Meta) -> bool:
        if not await self._load_cookies(meta):
            return False
        try:
            token = await self._upload_form_token(meta)
        except httpx.HTTPError as error:
            logger.info(f"{self.tracker}: could not open the upload page: {error!r}")
            return False
        if token:
            await self.cookie_validator.save_session_cookies(self.tracker, self.cookie_jar)
        return bool(token)

    # ------------------------------------------------------------------
    # Release facts
    # ------------------------------------------------------------------

    @staticmethod
    def _release(meta: Meta) -> XxxRelease | None:
        return XxxRelease.from_dict(meta.xxx_match)

    @staticmethod
    def _files(meta: Meta) -> list[Path]:
        files = [Path(str(path)) for path in meta.filelist or []]
        if not files and meta.path:
            files = [Path(str(meta.path))]
        return files

    def _videos(self, meta: Meta) -> list[Path]:
        return [path for path in self._files(meta) if path.suffix.casefold() in VIDEO_EXTENSIONS]

    def _images(self, meta: Meta) -> list[Path]:
        return [path for path in self._files(meta) if path.suffix.casefold() in IMAGE_EXTENSIONS]

    def _search_text(self, meta: Meta) -> str:
        """Release name and provider tags as plain lower-case words."""
        release = self._release(meta)
        parts = [str(meta.basename_no_ext or ""), *(str(tag) for tag in meta.keywords or [])]
        if release is not None:
            parts.extend((release.studio, release.network, *release.tags))
        return " ".join(_words(part) for part in parts if part)

    def is_pack(self, meta: Meta) -> bool:
        release = self._release(meta)
        if release is not None and release.kind == "movies":
            return False
        return is_pack_name(str(meta.basename_no_ext or "")) or len(self._videos(meta)) >= 3

    def is_siterip(self, meta: Meta) -> bool:
        return bool(_SITERIP_NAME.search(str(meta.basename_no_ext or "")))

    def is_picset(self, meta: Meta) -> bool:
        return not self._videos(meta) and bool(self._images(meta) or _PICSET_NAME.search(str(meta.basename_no_ext or "")))

    def is_vr(self, meta: Meta) -> bool:
        release = self._release(meta)
        tags = [_words(tag) for tag in [*(meta.keywords or []), *(release.tags if release else [])]]
        return bool(_VR_NAME.search(_words(meta.basename_no_ext))) or any(tag in ("vr", "virtual reality") for tag in tags)

    def is_movie(self, meta: Meta) -> bool:
        release = self._release(meta)
        if release is not None:
            return release.kind == "movies"
        return meta.is_disc in ("DVD", "BDMV") or bool(_MOVIE_NAME.search(str(meta.basename_no_ext or "")))

    def is_jav(self, meta: Meta) -> bool:
        release = self._release(meta)
        return (release is not None and release.kind == "jav") or bool(re.search(r"\b(?:jav|japanese)\b", self._search_text(meta)))

    def is_fansite(self, meta: Meta) -> bool:
        release = self._release(meta)
        platform_names = " ".join(_words(value) for value in (release.studio, release.network) if value) if release else ""
        return bool(_FANSITE_NAMES.search(f"{platform_names} {_words(meta.basename_no_ext)}"))

    def has_word(self, meta: Meta, pattern: str) -> bool:
        return bool(re.search(pattern, self._search_text(meta)))

    def get_category_id(self, meta: Meta) -> str:
        """Return the upload category; subclasses map the release to their own categories."""
        _ = meta
        return self.category_ids.get(self.default_category, "")

    @staticmethod
    def _studio(meta: Meta, release: XxxRelease | None) -> str:
        return str(meta.publisher or (release.studio if release else "") or "").strip()

    @staticmethod
    def _performers(meta: Meta, release: XxxRelease | None) -> list[str]:
        names = meta.manual_cast or meta.cast or (release.performers if release else [])
        return [str(name).strip() for name in names if str(name).strip()]

    def resolution_label(self, meta: Meta) -> str:
        """``1080p``-style label, or the ``6K VR`` label that Luminance sites ask for on VR."""
        if self.is_vr(meta):
            width = int(meta.video_width or 0)
            return f"{round(width / 1000)}K VR" if width >= 1900 else "VR"
        resolution = str(meta.resolution or "")
        return "" if resolution.casefold() in ("", "other", "unknown") else resolution

    async def get_name(self, meta: Meta) -> str:
        """``[Studio] Performer - Title (YYYY-MM-DD) [1080p]``, the order these sites ask for."""
        if meta.manual_name is not None:
            return meta.manual_name.strip()
        release = self._release(meta)
        resolution = self.resolution_label(meta)
        if release is None or not release.title:
            name = re.sub(r"\s{2,}", " ", str(meta.name or meta.basename_no_ext or "")).strip()
            # The generic name already ends with a resolution unless it was free-form.
            if resolution and self.is_vr(meta) and resolution.casefold() not in name.casefold():
                name = f"{name} [{resolution}]"
            return name

        title = release.title.strip()
        if release.code and release.code.casefold() not in title.casefold():
            title = f"{release.code} {title}"
        performers = self._performers(meta, release)
        # Skip performers the title already names.
        listed = [name for name in performers[:4] if name.casefold() not in title.casefold()]
        studio = self._studio(meta, release)
        when = release.date if re.fullmatch(r"\d{4}-\d{2}-\d{2}", release.date or "") and release.kind != "movies" else ""
        year = "" if when else str(release.year or (meta.year if isinstance(meta.year, int) and meta.year > 0 else "") or "")

        parts: list[str] = []
        if studio:
            parts.append(f"[{studio}]")
        parts.append(f"{', '.join(listed)} - {title}" if listed else title)
        if when or year:
            parts.append(f"({when or year})")
        name = " ".join(parts)
        if resolution:
            name = f"{name} [{resolution}]"
        return re.sub(r"\s{2,}", " ", name).strip()

    def get_tags(self, meta: Meta) -> str:
        """Space-separated tags: performers, studio, acts, resolution, file type and year."""
        release = self._release(meta)
        tags: list[str] = []
        tags.extend(normalize_tag(name) for name in self._performers(meta, release)[:10])
        studio = self._studio(meta, release)
        if studio:
            tags.append(normalize_tag(studio))
        if release is not None and release.network and release.network.casefold() != studio.casefold():
            tags.append(normalize_tag(release.network))
        content = [*(meta.keywords or []), *(release.tags if release else [])]
        tags.extend(tag for tag in (normalize_tag(value) for value in content) if tag not in _GENERIC_TAGS)
        if self.is_jav(meta):
            tags.extend(("jav", "asian"))
        if self.is_vr(meta):
            tags.append("vr")
            label = self.resolution_label(meta).split(" ")[0]
            if re.fullmatch(r"\d+K", label):
                tags.append(label.casefold())
        elif re.fullmatch(r"\d{3,4}p", str(meta.resolution or "")):
            tags.append(str(meta.resolution))
        if self.is_pack(meta):
            tags.append("siterip" if self.is_siterip(meta) else "megapack")
        container = str(meta.container or "").casefold() or next((path.suffix.lstrip(".").casefold() for path in self._videos(meta)), "")
        if container:
            tags.append(container)
        year = release.year if release and release.year else (meta.year if isinstance(meta.year, int) and meta.year > 0 else None)
        if year:
            tags.append(str(year))
        unique = [tag for tag in dict.fromkeys(tags) if tag and len(tag) <= 64]
        return " ".join(unique[: self.max_tags])

    # ------------------------------------------------------------------
    # Images and description
    # ------------------------------------------------------------------

    def _is_approved_url(self, url: str) -> bool:
        hostname = (urlparse(url).hostname or "").lower()
        return any(hostname == approved or hostname.endswith(f".{approved}") for approved in self.image_host_policy.url_host_mapping)

    def get_cover(self, meta: Meta) -> str:
        """Return the cover URL when it is already on an approved image host."""
        candidates: list[Any] = []
        if isinstance(meta.hosted_artwork, list):
            candidates.extend(entry.get("raw_url") for entry in meta.hosted_artwork if isinstance(entry, dict))
        candidates.extend((meta.rehosted_artwork_url, meta.artwork_url))
        return next((candidate for candidate in candidates if isinstance(candidate, str) and candidate and self._is_approved_url(candidate)), "")

    def configured_image_hosts(self) -> list[int]:
        """Indices of the ``img_host_N`` settings that name an approved host."""
        default_config = self.config.get("DEFAULT", {})
        return sorted(int(match.group(1)) for key, value in default_config.items() if (match := re.fullmatch(r"img_host_(\d+)", key)) and value in self.approved_image_hosts)

    async def host_cover(self, meta: Meta) -> str:
        """Host the release cover on an approved image host; "" when none is available."""
        existing = self.get_cover(meta)
        if existing or meta.skip_imghost_upload:
            return existing

        cover_path = Path(str(meta.artwork_path or ""))
        if not cover_path.is_file():
            cover_path = artwork_dir(meta.base_dir, meta.uuid) / "POSTER.png"
            if not cover_path.is_file() and meta.artwork_url:
                await download_artwork_from_meta(meta, str(cover_path))
        if not cover_path.is_file():
            return ""

        indices = self.configured_image_hosts()
        if not indices:
            logger.warning(f"{self.tracker}: no approved image host is configured for the cover ({', '.join(self.approved_image_hosts)}).")
            return ""
        original_imghost = meta.imghost
        try:
            for img_host_num in indices:
                uploaded, _ = await self.rehost_images_manager.uploadscreens_manager.upload_screens(
                    meta, 1, img_host_num, 0, 1, [str(cover_path)], {}, allowed_hosts=list(self.approved_image_hosts)
                )
                raw_url = uploaded[0].get("raw_url") if uploaded else ""
                if isinstance(raw_url, str) and self._is_approved_url(raw_url):
                    meta.rehosted_artwork_url = raw_url
                    return raw_url
        finally:
            meta.imghost = original_imghost
        logger.warning(f"{self.tracker}: failed to host the cover on an approved image host.")
        return ""

    async def get_mediainfo(self, meta: Meta) -> str:
        if meta.is_disc == "BDMV":
            return await self.common.get_bdmv_mediainfo(meta)
        mi_path = Path(meta.base_dir) / "tmp" / meta.uuid / "MEDIAINFO_CLEANPATH.txt"
        try:
            return mi_path.read_text(encoding="utf-8") if mi_path.is_file() else ""
        except OSError:
            return ""

    async def generate_description(self, meta: Meta) -> str:
        builder = DescriptionBuilder(self.tracker, self.config)
        description = await builder.general_description_generator(
            meta,
            audio_spectrogram=False,
            bluray=False,
            dynamic_hdr_plot=False,
            logo=False,
            mediainfo=False,
            menu_screenshots=False,
            tonemapped_header=False,
            approved_image_hosts=list(self.approved_image_hosts),
            signature=f"[align=right][url=https://github.com/wastaken7/Upload-Assistant][size=1]{meta.ua_signature}[/size][/url][/align]",
        )
        if not self.has_mediainfo_field and (mediainfo := (await self.get_mediainfo(meta)).strip()):
            description = f"{description}\n\n[spoiler=MediaInfo][code]{mediainfo}[/code][/spoiler]"
        return self.format_bbcode(description)

    @staticmethod
    def format_bbcode(description: str) -> str:
        """Luminance has no [center]/[right] or heading tags; use [align] and [size]."""
        bbcode = BBCODE()
        description = bbcode.convert_to_align(description)
        description = bbcode.convert_headings_to_sizes(description)
        description = bbcode.clamp_size_tags(description, 10)
        return re.sub(r"\n{3,}", "\n\n", description).strip()

    def description_text(self, meta: Meta) -> str:
        """The written part of the description: the synopsis or the user's own text.

        Only text the upload renders counts: the synopsis (``meta.overview``, which
        the provider's description fills) and the user's description, including one
        saved in the WebUI editor, which ``get_base_description`` copies into ``meta``.
        """
        parts = [str(meta.overview or ""), get_base_description(meta)]
        return " ".join(re.sub(r"\[[^\]]*\]|<[^>]+>|https?://\S+", " ", part) for part in parts).strip()

    # ------------------------------------------------------------------
    # Rules
    # ------------------------------------------------------------------

    def rule_warnings(self, meta: Meta) -> list[str]:
        """Content the site rules forbid; subclasses add site rules."""
        warnings: list[str] = []
        if meta.category != "XXX":
            warnings.append(f"{self.display_name} only accepts adult content.")
        files = self._files(meta)
        is_game = any(path.suffix.casefold() in GAME_EXTENSIONS for path in files)
        if not is_game and not self.is_picset(meta) and (archives := sorted({path.suffix.casefold() for path in files if path.suffix.casefold() in ARCHIVE_EXTENSIONS})):
            warnings.append(f"Archived video files are not allowed: {', '.join(archives)}.")
        return warnings

    def rule_notes(self, meta: Meta) -> list[str]:
        """Presentation requirements the metadata could not fill in."""
        notes: list[str] = []
        tag_count = len(self.get_tags(meta).split())
        if tag_count < self.min_tags:
            notes.append(f"{self.display_name} asks for at least {self.min_tags} tag(s); only {tag_count} could be built from the metadata.")
        return notes

    async def get_additional_checks(self, meta: Meta) -> bool:
        """Report broken upload rules; whether to upload anyway is asked by the tracker status check."""
        if problems := [*self.rule_warnings(meta), *self.rule_notes(meta)]:
            logger.warning(f"{self.tracker}: [red]Upload rules not met:[/red]\n" + "\n".join(f"- {problem}" for problem in problems))
            return False
        return True

    # ------------------------------------------------------------------
    # Duplicate search
    # ------------------------------------------------------------------

    def get_title_query(self, meta: Meta) -> dict[str, str]:
        """Search the torrent titles for the scene title (or JAV code)."""
        release = self._release(meta)
        title = (release.code or release.title) if release is not None else ""
        if not title:
            title = re.sub(r"[._]+", " ", str(meta.title or meta.basename_no_ext or ""))
            title = re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", title)
        words = [word for word in re.split(r"\s+", title) if len(word) > 1][:6]
        return {"action": "advanced", "title": " ".join(words)} if words else {}

    @staticmethod
    def get_size_query(meta: Meta) -> dict[str, str]:
        """Search for torrents of the same total size, to the 0.01 MiB the site shows.

        The site's own dupe check compares exact file sizes; a wider range
        mostly finds unrelated torrents that happen to be about as large.
        """
        size = int(meta.source_size or 0)
        if size <= 0:
            return {}
        return {"action": "advanced", "sizeall": f"{size / (1024 * 1024):.2f}", "sizetype": "mb", "sizerange": "0.01"}

    @staticmethod
    def parse_search_results(html: str, base_url: str) -> list[dict[str, Any]]:
        """Read the rows of a ``torrents.php`` result table."""
        results: list[dict[str, Any]] = []
        for row in BeautifulSoup(html, "html.parser").select("table#torrent_table tr.torrent"):
            link = row.select_one('a[href^="/torrents.php?id="], a[href^="torrents.php?id="]')
            if not link:
                continue
            href = str(link.get("href") or "")
            match = re.search(r"[?&]id=(\d+)", href)
            if not match:
                continue
            cells = row.find_all("td", recursive=False)
            texts = [cell.get_text(" ", strip=True) for cell in cells]
            # Columns: category, name, files, comments, time, size, snatches, seeders, leechers, uploader.
            results.append(
                {
                    "id": match.group(1),
                    "name": link.get_text(" ", strip=True),
                    "size": texts[5] if len(texts) > 5 else "",
                    "file_count": int(texts[2]) if len(texts) > 2 and texts[2].isdigit() else 0,
                    "files": [],
                    "link": f"{base_url}/torrents.php?id={match.group(1)}",
                }
            )
        return results

    async def search_existing(self, meta: Meta) -> list[dict[str, Any]]:
        if not await self._load_cookies(meta):
            return []
        dupes: dict[str, dict[str, Any]] = {}
        file_count = len(self._files(meta))
        for params, same_size in ((self.get_title_query(meta), False), (self.get_size_query(meta), True)):
            if not params:
                continue
            response = await self.session.get(f"{self.base_url}/torrents.php", params=params)
            if response.status_code != 200 or self._is_login_page(response):
                raise RuntimeError(f"{self.tracker}: could not search for duplicates; the cookies may have expired.")
            for result in self.parse_search_results(response.text, self.base_url):
                # A torrent of the same size only counts when it also has as many files.
                if same_size and result["file_count"] != file_count:
                    continue
                dupes.setdefault(result["link"], result)
        return list(dupes.values())

    # ------------------------------------------------------------------
    # Upload
    # ------------------------------------------------------------------

    def is_anonymous(self, meta: Meta) -> bool:
        return bool(meta.anon or self.tracker_config.get("anon", False))

    async def get_data(self, meta: Meta, auth: str, preview: bool = False) -> dict[str, str]:
        """The upload form fields; a ``preview`` leaves out what is built at upload time."""
        data: dict[str, str] = {
            "submit": "true",
            "auth": auth,
            "MAX_FILE_SIZE": "2097152",
            "category": self.get_category_id(meta),
            "title": await self.get_name(meta),
            "taglist": self.get_tags(meta),
            "image": "" if preview else self.get_cover(meta),
            "desc": "" if preview else await self.generate_description(meta),
            "anonymous": "1" if self.is_anonymous(meta) else "0",
        }
        if self.has_mediainfo_field:
            data["mediainfo"] = "" if preview else await self.get_mediainfo(meta)
        return data

    async def get_payload_preview(self, meta: Meta) -> payload_preview.TrackerPreview:
        """The upload form as it is known before screenshots, for the Web UI to show and edit."""
        specs = {
            "submit": payload_preview.readonly("Submit"),
            "MAX_FILE_SIZE": payload_preview.readonly("Max file size"),
            # A genre within XXX: nothing else is built from it, so it is safe to change here.
            "category": payload_preview.choice("Category", [(value, label) for label, value in self.category_ids.items()], role="none"),
            "title": payload_preview.text("Title"),
            "taglist": payload_preview.text("Tags", max_length=2000),
            "anonymous": payload_preview.flag("Anonymous"),
        }
        deferred = {"image": "Hosted at upload time", "desc": payload_preview.DESCRIPTION_NOTE}
        if self.has_mediainfo_field:
            deferred["mediainfo"] = "Read from the MediaInfo report at upload time"
        data = await self.get_data(meta, "", preview=True)
        data.pop("auth", None)
        return payload_preview.describe(self.tracker, data, specs, deferred=deferred, name_key="title")

    async def upload(self, meta: Meta) -> bool:
        tracker_status = meta.tracker_status.setdefault(self.tracker, {})
        if not await self._load_cookies(meta):
            tracker_status["status_message"] = "data error: The cookie file could not be loaded."
            return False
        # Hosting switches meta.imghost while other trackers may be hosting images.
        async with release_image_lock(meta):
            await self.host_cover(meta)
        auth = await self._upload_form_token(meta)
        if not auth:
            tracker_status["status_message"] = "data error: Failed to load the authenticated upload form."
            return False

        uploaded = await self.cookie_auth_uploader.handle_upload(
            meta=meta,
            tracker=self.tracker,
            source_flag=self.source_flag,
            torrent_url=self.torrent_url,
            data=await self.get_data(meta, auth),
            torrent_field_name="file_input",
            upload_cookies=self.session.cookies,
            upload_url=self.upload_url,
            # The torrent page URL, or the "download it from here" link of the warning page.
            id_pattern=r"torrents\.php\?id=(\d+)",
            # A successful upload redirects to the torrent page, or shows a warning page when the
            # site corrected the .torrent (for example its source tag). A rejected one shows the form again.
            success_list=['id="descbox"', 'id="torrent_tags"', "Your torrent has been uploaded"],
        )
        torrent_id = str(tracker_status.get("torrent_id") or "")
        if uploaded and not meta.debug and torrent_id.isdigit() and not await self.download_site_torrent(meta, torrent_id):
            # The site may have changed the info hash, so the local copy might not seed:
            # keep it out of the torrent client and ask for the site's copy instead.
            tracker_status["skip_client_injection"] = True
            tracker_status["status_message"] = (
                f"Uploaded, but the .torrent could not be downloaded from the site. Download it from {self.torrent_url}{torrent_id} and seed that copy."
            )
        return uploaded

    @staticmethod
    def find_download_url(html: str, page_url: str, torrent_id: str) -> str:
        """The personal download link of a torrent, from its page."""
        for link in BeautifulSoup(html, "html.parser").select('a[href*="action=download"]'):
            href = str(link.get("href") or "")
            if re.search(rf"[?&]id={torrent_id}(?:&|$)", href) and "torrent_pass=" in href:
                return str(httpx.URL(page_url).join(href))
        return ""

    async def download_site_torrent(self, meta: Meta, torrent_id: str) -> bool:
        """Seed the .torrent the site serves, which it may have changed on upload.

        Returns False, keeping the locally built copy, when the download fails.
        """
        try:
            response = await self.session.get(f"{self.torrent_url}{torrent_id}")
            download_url = self.find_download_url(response.text, str(response.url), torrent_id) if response.status_code == 200 else ""
        except httpx.HTTPError as error:
            logger.warning(f"{self.tracker}: could not open the uploaded torrent page: {error!r}")
            return False
        if not download_url:
            logger.warning(f"{self.tracker}: the download link of the uploaded torrent was not found.")
            return False
        return bool(await self.common.download_tracker_torrent(meta, self.tracker, headers=dict(self.session.headers), downurl=download_url))
