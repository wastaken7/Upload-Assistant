# Upload Assistant © 2026 Audionut & wastaken7 — Licensed under UAPL v1.0
import asyncio
import json
import re
import uuid
from functools import cache
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import aiofiles
from bs4 import BeautifulSoup
from PIL import Image

from src import payload_preview
from src.app_paths import CODE_DIR
from src.cogs.redaction import Redaction
from src.console import logger
from src.manual_input import Question, ask, choices_from, confirm_override, has_answer
from src.meta import Meta
from src.screenshot_manifest import files as manifest_files
from src.trackers.AVISTAZ import AZTrackerBase
from src.xxx_platforms import XXX_PLATFORM_KEYWORDS

# https://exoticaz.to/rules/upload-rules
CATEGORY_IDS = {
    "Video Clips": "1",
    "Video Pack": "2",
    "Siterip Pack": "3",
    "Pornstar Pack": "4",
    "DVD": "5",
    "BluRay": "6",
}
PACK_CATEGORY_IDS = frozenset({"2", "3", "4"})
RESOLUTION_IDS = {
    "240p": "1",
    "360p": "2",
    "480p": "3",
    "480i": "3",
    "576p": "3",
    "576i": "3",
    "720p": "4",
    "1080p": "5",
    "1080i": "5",
    "1440p": "10",
    "2160p": "6",
    "4320p": "7",
}
VIDEO_EXTENSIONS = frozenset({".avi", ".flv", ".m2ts", ".m4v", ".mkv", ".mov", ".mp4", ".mpeg", ".mpg", ".ogv", ".ogm", ".qt", ".ts", ".vob", ".webm", ".wmv", ".asf", ".mts"})
DISC_EXTENSIONS = {"5": frozenset({".vob", ".iso", ".mkv", ".avi", ".mp4"}), "6": frozenset({".m2ts", ".iso", ".mkv", ".mp4"})}
ARCHIVE_EXTENSIONS = frozenset({".zip", ".rar", ".7z", ".tar", ".gz"})
# Extra flags are dedicated search filters, so the upload rules keep them out of tags.
EXTRA_KEYWORDS = {
    "asian": frozenset({"asian", "jav"}),
    "softcore": frozenset({"softcore"}),
    "censored": frozenset({"censored"}),
    "transexual": frozenset({"trans", "transgender", "transsexual", "transexual", "shemale", "tranny"}),
    "gay": frozenset({"gay"}),
}
EXTRA_LABELS = {"asian": "Asian", "softcore": "Softcore", "censored": "Censored", "transexual": "Transexual", "gay": "Gay"}
MINIMUM_TORRENT_SIZE = 20 * 1024 * 1024
MAXIMUM_MEDIAINFO_SIZE = 50 * 1024
MAXIMUM_TAGS = 10
# Refresh with scripts/update_exoticaz_tags.py.
TAG_CATALOG_PATH = CODE_DIR / "data" / "exoticaz_tags.json"
IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".webp", ".gif"})


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def _validate_extras(selected: list[str]) -> str | None:
    # The site treats Gay, Transexual and straight as a single choice.
    if "gay" in selected and "transexual" in selected:
        return "Choose either Gay or Transexual, not both."
    return None


def _tag_key(value: str) -> str:
    """Spell a keyword the way site tags are written, with periods between words."""
    return re.sub(r"[\s_.-]+", ".", value.strip().casefold()).strip(".")


@cache
def load_tag_catalog() -> dict[str, tuple[str, int]]:
    """Map every tag name and synonym in data/exoticaz_tags.json to its tag ID and usage."""
    try:
        catalog = json.loads(TAG_CATALOG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        logger.warning(f"EXOTICAZ: Unable to read the tag catalog: {e}", extra={"markup": False})
        return {}

    lookup: dict[str, tuple[str, int]] = {}
    for tag in catalog.get("tags", []):
        entry = (str(tag["id"]), int(tag.get("usage") or 0))
        lookup[_tag_key(tag["tag"])] = entry
        for synonym in tag.get("synonyms", []):
            lookup.setdefault(_tag_key(synonym), entry)
    return lookup


class ExoticaZ(AZTrackerBase):
    """
    ExoticaZ (AvistaZ network) adult video tracker.
    """

    tracker = "EXOTICAZ"
    display_name = "ExoticaZ"
    source_flag = "ExoticaZ"
    banned_groups = ("",)
    base_url = "https://exoticaz.to"
    torrent_url = f"{base_url}/torrent/"
    requests_url = ""
    supported_categories = ("XXX",)
    tracker_urls = ("tracker.exoticaz.to",)
    default_announce = "https://tracker.exoticaz.to/announce"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config, tracker_name="EXOTICAZ")
        self.category_id = ""

    async def validate_credentials(self, meta: Meta):
        cookie_jar = await self.cookie_validator.load_session_cookies(meta, self.tracker)
        if cookie_jar:
            self.session.cookies = cookie_jar
            return await self.cookie_validator.cookie_validation(
                meta=meta,
                tracker=self.tracker,
                test_url=f"{self.base_url}/upload",
                success_text=f"{self.base_url}/logout",
                token_pattern=r'name="csrf-token" content="([^"]+)"',  # noqa: S106
            )
        return False

    def _video_files(self, meta: Meta) -> list[Path]:
        return [Path(path) for path in meta.filelist or [] if Path(path).suffix.casefold() in VIDEO_EXTENSIONS]

    async def get_category_id(self, meta: Meta) -> str:
        if self.category_id:
            return self.category_id

        if meta.is_disc == "DVD":
            self.category_id = CATEGORY_IDS["DVD"]
        elif meta.is_disc == "BDMV":
            self.category_id = CATEGORY_IDS["BluRay"]
        elif meta.is_disc:
            return ""
        elif len(self._video_files(meta)) <= 1:
            self.category_id = CATEGORY_IDS["Video Clips"]
        else:
            # Several videos may be clips of one title or a themed, siterip or pornstar pack.
            choice = await ask(
                meta,
                Question(
                    key="exoticaz.category",
                    kind="choice",
                    prompt=f"{self.tracker}: Select the category for this multi-video upload",
                    title="ExoticaZ category",
                    choices=choices_from(["Video Clips", "Video Pack", "Siterip Pack", "Pornstar Pack"]),
                    hint="Video Clips are clips of a single title; packs are themed, single-site or single-performer collections.",
                    summary={"Tracker": self.tracker, "Release": meta.name, "Videos": str(len(self._video_files(meta)))},
                    tracker=self.tracker,
                ),
            )
            self.category_id = CATEGORY_IDS.get(str(choice), "")

        return self.category_id

    def video_dimensions(self, meta: Meta) -> tuple[int, int]:
        if meta.video_width and meta.video_height:
            return int(meta.video_width), int(meta.video_height)
        # XXX preparation does not always fill the dimensions, so read the first video track.
        for track in (meta.mediainfo or {}).get("media", {}).get("track", []):
            if isinstance(track, dict) and track.get("@type") == "Video":
                try:
                    return int(float(track.get("Width", 0))), int(float(track.get("Height", 0)))
                except TypeError, ValueError:
                    return 0, 0
        return 0, 0

    def get_resolution_ids(self, meta: Meta) -> list[str]:
        resolution_id = RESOLUTION_IDS.get(str(meta.resolution or "").casefold())
        if resolution_id:
            return [resolution_id]

        height = self.video_dimensions(meta)[1]
        for limit, fallback_id in ((240, "1"), (360, "2"), (576, "3"), (720, "4"), (1080, "5"), (1440, "10"), (2160, "6"), (4320, "7")):
            if height and height <= limit:
                return [fallback_id]
        return []

    def get_extras(self, meta: Meta) -> list[str]:
        keywords = {keyword.strip().casefold() for keyword in meta.keywords or [] if keyword.strip()}
        extras = [extra for extra, terms in EXTRA_KEYWORDS.items() if keywords & terms]
        if "censored" in extras and "uncensored" in keywords:
            extras.remove("censored")
        return extras

    async def confirm_extras(self, meta: Meta) -> list[str]:
        """Let attended uploads review the flags, since keywords rarely reveal them and Asian is mandatory."""
        extras = self.get_extras(meta)
        detected = ", ".join(EXTRA_LABELS[extra] for extra in extras) or "None"
        context = {"Tracker": self.tracker, "Release": meta.name, **{label: "Yes" if extra in extras else "No" for extra, label in EXTRA_LABELS.items()}}
        # A quick yes keeps the detected flags; the list is only shown to change them.
        if not has_answer(meta, "exoticaz.flags"):
            confirmed = await ask(
                meta,
                Question(
                    key="exoticaz.flags_detected",
                    kind="confirm",
                    prompt=f"{self.tracker}: Flags detected: {detected}. Are these correct?",
                    title=f"{self.tracker} flags",
                    default=True,
                    hint="Asian torrents must be marked as Asian. Leave Censored unmarked for uncensored videos.",
                    summary=context,
                    tracker=self.tracker,
                    unattended="default",
                ),
            )
            if confirmed:
                return extras

        selected = await ask(
            meta,
            Question(
                key="exoticaz.flags",
                kind="multi_choice",
                prompt=f"{self.tracker}: Select the flags that apply, or leave empty for none",
                title=f"{self.tracker} flags",
                choices=choices_from(EXTRA_LABELS),
                hint="Asian torrents must be marked as Asian. Leave Censored unmarked for uncensored videos.",
                summary=context,
                tracker=self.tracker,
                unattended="fail",
                empty_ok=True,
                validate=_validate_extras,
            ),
        )
        if selected is None:
            return extras
        return [extra for extra in EXTRA_LABELS if extra in selected]

    async def _api_search(self, endpoint: str, term: str) -> list[dict[str, Any]]:
        headers = {"Referer": f"{self.base_url}/upload", "X-Requested-With": "XMLHttpRequest", "Accept": "application/json"}
        try:
            response = await self.session.get(f"{self.base_url}/api/v1/{endpoint}", params={"term": term}, headers=headers)
            response.raise_for_status()
            data = response.json().get("data", [])
            return data if isinstance(data, list) else []
        except Exception as e:
            logger.info(f"{self.tracker}: Unable to search {endpoint} for '{term}': {e}", extra={"markup": False})
            return []

    def get_tag_words(self, meta: Meta) -> list[str]:
        # Studios and extra flags have their own search filters, so they must not be tags.
        excluded = {_normalize(keyword) for keyword in XXX_PLATFORM_KEYWORDS}
        for terms in EXTRA_KEYWORDS.values():
            excluded.update(terms)
        excluded.update({"uncensored", _normalize(meta.publisher or "")})

        words: list[str] = []
        for keyword in meta.keywords or []:
            word = _tag_key(keyword)
            if word and _normalize(word) not in excluded and word not in words:
                words.append(word)
        return words

    async def resolve_tags(self, words: list[str]) -> list[str]:
        # Resolve names and synonyms from the bundled catalog; the rules ask for the most common tags first.
        catalog = load_tag_catalog()
        known = sorted({catalog[word] for word in words if word in catalog}, key=lambda tag: -tag[1])
        tag_ids = [tag_id for tag_id, _usage in known][:MAXIMUM_TAGS]

        # Tags added to the site after the catalog was updated are still found through the site search.
        for word in (word for word in words if word not in catalog):
            if len(tag_ids) >= MAXIMUM_TAGS:
                break
            for tag in await self._api_search("tags", word):
                if str(tag.get("tag", "")).casefold() == word:
                    tag_id = str(tag.get("id", ""))
                    if tag_id and tag_id not in tag_ids:
                        tag_ids.append(tag_id)
                    break
        return tag_ids

    async def get_tags(self, meta: Meta) -> list[str]:
        tag_ids = await self.resolve_tags(self.get_tag_words(meta))
        if tag_ids:
            return tag_ids

        # ExoticaZ requires tags, so ask for them before anything is sent to the site.
        logger.info(f"{self.tracker}: [yellow]No site tags were found for this release. ExoticaZ requires at least one tag.[/yellow]")

        async def known_tags(words: list[str]) -> str | None:
            nonlocal tag_ids
            tag_ids = await self.resolve_tags([word for word in (_tag_key(word) for word in words) if word])
            return None if tag_ids else f"None of these tags exist on ExoticaZ: {', '.join(words)}"

        words = await ask(
            meta,
            Question(
                key="xxx.tags",
                kind="list",
                prompt=f"{self.tracker}: Enter tags separated by commas (leave empty to cancel)",
                title=f"{self.tracker} tags",
                hint="Comma-separated tags in English, such as the ones listed at https://exoticaz.to/tags. Leave empty to cancel the upload.",
                placeholder="e.g. blowjob, big tits",
                summary={"Tracker": self.tracker, "Release": meta.name, "Keywords": ", ".join(meta.keywords or []) or "None"},
                tracker=self.tracker,
                validate=known_tags,
            ),
        )
        if not words:
            logger.info(f"{self.tracker}: No tags were given. The upload was cancelled.")
            return []
        return tag_ids

    async def get_studio_ids(self, meta: Meta) -> list[str]:
        publisher = _normalize(meta.publisher or "")
        if not publisher:
            return []
        for studio in await self._api_search("studios", meta.publisher):
            website = re.sub(r"^(?:https?://)?(?:www\.)?", "", str(studio.get("website") or "").casefold()).split(".")[0]
            if publisher in (_normalize(str(studio.get("name", ""))), _normalize(website)):
                return [str(studio.get("id"))]
        return []

    def is_full_size_screenshot(self, meta: Meta, path: Path) -> bool:
        """Tell single frames from video sheets, whose grid changes the aspect ratio."""
        video_width, video_height = self.video_dimensions(meta)
        if not video_width or not video_height:
            return False
        try:
            with Image.open(path) as image:
                width, height = image.size
        except OSError, ValueError:
            return False
        video_ratio = video_width / video_height
        return height > 0 and abs(width / height - video_ratio) <= video_ratio * 0.05 and width >= video_width * 0.9

    def get_image_paths(self, meta: Meta, category_id: str) -> list[Path]:
        limit = 40 if category_id in PACK_CATEGORY_IDS else 10
        images = [path for path in manifest_files(meta.base_dir, meta.uuid, "main") if path.suffix.casefold() in IMAGE_EXTENSIONS]
        # Every video needs its video sheet, so keep the sheets ahead of individual frames.
        images.sort(key=lambda path: self.is_full_size_screenshot(meta, path))
        return images[:limit]

    async def get_name(self, meta: Meta) -> str:
        if meta.manual_name is not None:
            return meta.manual_name.strip()
        return re.sub(r"\s{2,}", " ", meta.name or "").strip()

    def rules(self, meta: Meta) -> str:
        warnings: list[str] = []
        files = [Path(path) for path in meta.filelist or []]
        video_files = self._video_files(meta)

        if meta.category != "XXX":
            warnings.append("The only allowed content to be uploaded is porn.")
        if meta.anime:
            warnings.append("No Hentai or animated porn of any kind. Hentai should be posted at AnimeZ.")
        if meta.source_size and meta.source_size < MINIMUM_TORRENT_SIZE:
            warnings.append("ExoticaZ rejects torrents smaller than 20 MB.")

        if not meta.is_disc:
            if archives := sorted({path.suffix.casefold() for path in files if path.suffix.casefold() in ARCHIVE_EXTENSIONS}):
                warnings.append(f"Archived files are not allowed: {', '.join(archives)}.")
            if junk := sorted({path.suffix.casefold() or path.name for path in files if path.suffix.casefold() not in VIDEO_EXTENSIONS | ARCHIVE_EXTENSIONS}):
                warnings.append(f"Only video files are allowed in video torrents; found: {', '.join(junk)}.")
            if any(re.search(r"(?:^|[.\-_\s])sample$", path.stem, re.IGNORECASE) for path in video_files):
                warnings.append("Sample files are not allowed in uploads.")

        images = [path for path in manifest_files(meta.base_dir, meta.uuid, "main") if path.suffix.casefold() in IMAGE_EXTENSIONS]
        full_size = [path for path in images if self.is_full_size_screenshot(meta, path)]
        sheet_count = len(images) - len(full_size)
        if not sheet_count:
            warnings.append("Every video must have a video sheet (contact sheet).")
        elif len(video_files) > sheet_count:
            warnings.append(
                f"Every video must have a video sheet, but only {sheet_count} of {len(video_files)} videos have one. Raise 'xxx_contact_sheet_max_videos' if needed."
            )
        if len(video_files) == 1 and not full_size:
            warnings.append("Video clips must also have a full size screenshot. Set 'xxx_single_file_screens' to at least 1.")

        return "\n\n".join(warnings)

    async def get_additional_checks(self, meta: Meta) -> bool:
        if self.config["TRACKERS"][self.tracker].get("check_for_rules", True):
            warnings = self.rules(meta)
            if warnings:
                logger.info(f"{self.tracker}: [red]Rule check returned the following warning(s):[/red]\n\n{warnings}")
                if not await confirm_override(meta, "Do you want to continue anyway?"):
                    return False

        media_info = await self.get_file_info(meta)
        if len(media_info.encode("utf-8")) > MAXIMUM_MEDIAINFO_SIZE:
            logger.info(f"{self.tracker}: [red]MediaInfo is larger than 50 KB and would be rejected.[/red]")
            return False

        # Tags are required. Attended uploads are asked for them before the upload starts; unattended ones are skipped here.
        if meta.unattended and not meta.unattended_confirm and not has_answer(meta, "xxx.tags") and not await self.resolve_tags(self.get_tag_words(meta)):
            logger.info(f"{self.tracker}: [yellow]Unattended mode: no site tags were found for this release. Skipping {self.tracker} upload.[/yellow]")
            return False

        return True

    async def search_existing(self, meta: Meta) -> list[dict[str, str]]:
        duplicates: list[dict[str, str]] = []
        cookie_jar = await self.cookie_validator.load_session_cookies(meta, self.tracker)
        if cookie_jar:
            self.session.cookies = cookie_jar

        search_term = " ".join(part for part in (meta.publisher, meta.title) if part) or meta.name
        page_url = f"{self.base_url}/torrents"
        params: dict[str, str] | None = {"in": "1", "search": search_term}
        visited_urls: set[str] = set()

        # Keep the duplicate search to a few pages so a broad title does not crawl the site.
        while page_url and page_url not in visited_urls and len(visited_urls) < 3:
            visited_urls.add(page_url)
            try:
                response = await self.session.get(page_url, params=params)
                response.raise_for_status()
            except Exception as e:
                logger.info(f"{self.tracker}: Unable to search for duplicates: {e}", extra={"markup": False})
                break
            params = None

            soup = BeautifulSoup(response.text, "html.parser")
            table = soup.find("table", class_="table-bordered")
            tbody = table.find("tbody") if table else None
            if not tbody:
                break

            for row in tbody.find_all("tr", recursive=False):
                name_tag = row.find("a", class_="torrent-link")
                if not name_tag:
                    continue
                cells = row.find_all("td", recursive=False)
                href = name_tag.get("href")
                duplicates.append(
                    {
                        "name": name_tag.get_text(strip=True),
                        "size": cells[4].get_text(strip=True) if len(cells) > 4 else "",
                        "link": href if isinstance(href, str) else "",
                    }
                )

            next_page = soup.select_one("a[rel='next']")
            next_href = next_page.get("href") if next_page else ""
            page_url = next_href if isinstance(next_href, str) else ""

        return duplicates

    async def get_secret_token(self) -> str:
        token = str(getattr(self.az_class, "secret_token", "") or "")
        if token:
            return token
        response = await self.session.get(f"{self.base_url}/upload")
        match = re.search(r'name="csrf-token" content="([^"]+)"', response.text)
        token = match.group(1) if match else ""
        self.az_class.secret_token = token
        return token

    async def fetch_data(self, meta: Meta, preview: bool = False) -> dict[str, Any]:
        """Build the upload form; a ``preview`` asks nothing, sends no request and leaves out the description and reports."""
        category_id = await self.get_category_id(meta)
        data: dict[str, Any] = {
            "file_name": await self.get_name(meta),
            "category_id": category_id,
            "extra[]": None if preview else await self.confirm_extras(meta),
            "resolution_ids[]": self.get_resolution_ids(meta),
            "performer_ids[]": [],
            # Studio and tag IDs are looked up on the site.
            "studio_ids[]": None if preview else await self.get_studio_ids(meta),
            "tag_ids[]": None if preview else await self.get_tags(meta),
            "description": None if preview else await self.edit_desc(meta),
            "media_info": None if preview else await self.get_file_info(meta),
        }
        anon = not (meta.anon == 0 and not self.config["TRACKERS"][self.tracker].get("anon", False))
        if anon:
            data["options"] = "anon_upload"
        return data

    async def get_payload_preview(self, meta: Meta) -> payload_preview.TrackerPreview:
        """The upload form as it is known before screenshots, for the Web UI to show and edit."""
        specs = {
            "file_name": payload_preview.text("Name"),
            "category_id": payload_preview.choice(
                "Category", [("1", "Video Clips"), ("2", "Video Pack"), ("3", "Siterip Pack"), ("4", "Pornstar Pack"), ("5", "DVD"), ("6", "BluRay")]
            ),
            "resolution_ids[]": payload_preview.readonly("Resolutions"),
            "performer_ids[]": payload_preview.readonly("Performers"),
            "options": payload_preview.flag("Anonymous", on="anon_upload", off=None),
        }
        deferred = {
            "extra[]": "Confirmed in a question after this one",
            "studio_ids[]": "Looked up on the tracker at upload time",
            "tag_ids[]": "Looked up on the tracker at upload time",
            "description": payload_preview.DESCRIPTION_NOTE,
            "media_info": "Read from the MediaInfo/BDInfo report at upload time",
        }
        return payload_preview.describe(self.tracker, await self.fetch_data(meta, preview=True), specs, deferred=deferred, name_key="file_name")

    def check_data(self, meta: Meta, data: dict[str, Any]) -> str:
        meta = meta
        if not data.get("category_id"):
            return "UPLOAD FAILED: Unable to determine the ExoticaZ category for this upload."
        if not data.get("tag_ids[]"):
            return "UPLOAD FAILED: ExoticaZ requires at least one tag."
        if not data.get("resolution_ids[]"):
            return "UPLOAD FAILED: Unable to determine the resolution for this upload."
        if not data.get("media_info"):
            return "UPLOAD FAILED: MediaInfo/BDInfo is required."
        return ""

    def extract_error(self, html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        messages: list[str] = []
        for element in soup.select(".alert-danger, .invalid-feedback, .text-danger"):
            message = " ".join(element.get_text(" ", strip=True).replace("00d7", " ").split())
            if message and message not in messages:
                messages.append(message)
        return " | ".join(messages)

    async def save_failure(self, meta: Meta, html: str, name: str) -> str:
        failure_path = Path(meta.base_dir) / "tmp" / meta.uuid / f"[{self.tracker}]{name}.html"
        failure_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(failure_path, "w", encoding="utf-8") as f:
            await f.write(html)
        return str(failure_path)

    async def create_draft(self, meta: Meta, data: dict[str, Any], token: str) -> str:
        await self.common.create_torrent_for_upload(meta, self.tracker, self.source_flag, announce_url=self.default_announce)
        torrent_path = Path(meta.base_dir) / "tmp" / meta.uuid / f"[{self.tracker}].torrent"
        async with aiofiles.open(torrent_path, "rb") as torrent_file:
            torrent_bytes = await torrent_file.read()

        step1_data = {"_token": token, "file_name": data["file_name"], "category_id": data["category_id"], "media_info": data["media_info"]}
        files = {"torrent_file": (torrent_path.name, torrent_bytes, "application/x-bittorrent")}
        response = await self.session.post(f"{self.base_url}/upload", data=step1_data, files=files, headers={"Referer": f"{self.base_url}/upload"})
        location = response.headers.get("Location", "")
        match = re.search(r"/edit/torrent/(\d+)", location)
        if response.status_code == 302 and match:
            return match.group(1)

        html = response.text
        if response.status_code == 302 and location:
            await asyncio.sleep(1)
            html = (await self.session.get(urljoin(self.base_url, location))).text
        failure_path = await self.save_failure(meta, html, "FailedUpload_Step1")
        error = self.extract_error(html) or f"status {response.status_code}"
        meta.tracker_status[self.tracker]["status_message"] = (
            f"data error - Step 1 of upload to {self.tracker} failed: {error}\nThe HTML response was saved to '{failure_path}'."
        )
        return ""

    async def upload_screenshots(self, torrent_id: str, token: str, image_paths: list[Path]) -> list[str]:
        """Upload screenshots to the draft and return the image IDs that publishing must list."""
        file_ids: list[str] = []
        edit_url = f"{self.base_url}/edit/torrent/{torrent_id}"
        headers = {"Referer": edit_url, "X-Requested-With": "XMLHttpRequest", "Accept": "application/json", "Origin": self.base_url}
        for path in image_paths:
            try:
                async with aiofiles.open(path, "rb") as f:
                    image_bytes = await f.read()
                content_type = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif"}.get(path.suffix.casefold(), "image/png")
                form = {"_token": token, "qquuid": str(uuid.uuid4()), "qqfilename": path.name, "qqtotalfilesize": str(len(image_bytes))}
                response = await self.session.post(
                    f"{self.base_url}/add/image/torrent/{torrent_id}", data=form, files={"qqfile": (path.name, image_bytes, content_type)}, headers=headers
                )
                result = response.json() if response.is_success else {}
                if result.get("success") and result.get("fileId"):
                    file_ids.append(str(result["fileId"]))
                else:
                    logger.info(f"{self.tracker}: Error uploading {path.name}: {result.get('error') or response.status_code}", extra={"markup": False})
            except Exception as e:
                logger.info(f"{self.tracker}: Exception when uploading {path.name}: {e}", extra={"markup": False})
        return file_ids

    async def save_draft(self, torrent_id: str, form: dict[str, Any]) -> None:
        headers = {"Referer": f"{self.base_url}/edit/torrent/{torrent_id}", "X-Requested-With": "XMLHttpRequest", "Accept": "application/json"}
        try:
            await self.session.post(f"{self.base_url}/edit/draft/{torrent_id}", data=form, headers=headers)
        except Exception as e:
            logger.info(f"{self.tracker}: Unable to save the draft: {e}", extra={"markup": False})

    async def download_site_torrent(self, meta: Meta, torrent_url: str) -> bool:
        # The site rewrites the uploaded torrent, so seed the copy it serves.
        try:
            response = await self.session.get(torrent_url)
            response.raise_for_status()
            link = BeautifulSoup(response.text, "html.parser").select_one("a[href*='/download/torrent/']")
            href = link.get("href") if link else ""
            if not isinstance(href, str) or not href:
                return False
            downloaded = await self.common.download_tracker_torrent(meta, self.tracker, headers=dict(self.session.headers), downurl=urljoin(self.base_url, href))
            return bool(downloaded)
        except Exception as e:
            logger.info(f"{self.tracker}: Unable to download the torrent file: {e}", extra={"markup": False})
            return False

    async def upload(self, meta: Meta) -> bool:
        cookie_jar = await self.cookie_validator.load_session_cookies(meta, self.tracker)
        if cookie_jar:
            self.session.cookies = cookie_jar

        data = await self.fetch_data(meta)
        if getattr(meta, "skipping", None) == self.tracker:
            return False
        data = payload_preview.apply_payload_edits(meta, self.tracker, data)
        if issue := self.check_data(meta, data):
            meta.tracker_status[self.tracker]["status_message"] = f"data error - {issue}"
            return False

        image_paths = self.get_image_paths(meta, data["category_id"])
        if meta.debug:
            logger.info(f"{self.tracker}: Request Data:")
            logger.info(Redaction.redact_private_info({**data, "screenshots": [path.name for path in image_paths]}))
            if not data["extra[]"]:
                logger.info(f"{self.tracker}: [yellow]No Asian/Softcore/Censored/Transexual/Gay flag was detected; Asian torrents must be marked as Asian.[/yellow]")
            meta.tracker_status[self.tracker]["status_message"] = "Debug mode enabled, not uploading."
            await self.common.create_torrent_for_upload(meta, f"{self.tracker}_DEBUG", f"{self.tracker}_DEBUG", announce_url="https://fake.tracker")
            return True

        if not image_paths:
            meta.tracker_status[self.tracker]["status_message"] = "data error - ExoticaZ requires a video sheet, but no local screenshots were found."
            return False

        token = await self.get_secret_token()
        torrent_id = await self.create_draft(meta, data, token)
        if not torrent_id:
            return False

        edit_url = f"{self.base_url}/edit/torrent/{torrent_id}"
        form = {"_token": token, **data}
        file_ids = await self.upload_screenshots(torrent_id, token, image_paths)
        if not file_ids:
            await self.save_draft(torrent_id, form)
            meta.tracker_status[self.tracker]["status_message"] = f"data error - No screenshots were accepted. The upload was kept as a draft: {edit_url}"
            return False

        # The edit form lists the draft's images as file_ids[]; without them publishing fails with "Screenshots are required".
        form["file_ids[]"] = file_ids
        response = await self.session.post(edit_url, data=form, headers={"Referer": edit_url})
        location = response.headers.get("Location", "")
        # A failed publish redirects back to /edit/torrent/<id>, which must not count as success.
        match = re.search(r"^(?:https?://[^/]+)?/torrent/(\d+)$", location)
        if response.status_code != 302 or not match:
            html = response.text
            if response.status_code == 302 and location:
                html = (await self.session.get(urljoin(self.base_url, location))).text
            failure_path = await self.save_failure(meta, html, "FailedUpload_Step2")
            error = self.extract_error(html) or f"status {response.status_code}"
            meta.tracker_status[self.tracker]["status_message"] = (
                f"data error - Publishing to {self.tracker} failed: {error}\nThe draft is kept at {edit_url}\nThe HTML response was saved to '{failure_path}'."
            )
            return False

        torrent_url = urljoin(self.base_url, location)
        meta.tracker_status[self.tracker]["torrent_id"] = match.group(1)
        if not await self.download_site_torrent(meta, torrent_url):
            meta.tracker_status[self.tracker]["status_message"] = (
                f"data error - Uploaded, but the torrent file could not be downloaded. Download it from {torrent_url} before seeding."
            )
            return False

        meta.tracker_status[self.tracker]["status_message"] = f"{self.tracker} torrent uploaded successfully: {torrent_url}"
        return True
