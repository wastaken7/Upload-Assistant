# Upload Assistant © 2026 Audionut & wastaken7 — Licensed under UAPL v1.0
import asyncio
import platform
import re
from pathlib import Path
from typing import Any, ClassVar, cast

import aiofiles
import httpx

from src import payload_preview
from src.artwork import is_valid_image_bytes
from src.cogs.redaction import Redaction
from src.console import logger
from src.get_desc import DescriptionBuilder
from src.meta import Meta
from src.screenshot_manifest import files as manifest_files
from src.trackers.common import Common

Config = dict[str, Any]


class DirtyBytes:
    """
    DirtyBytes is a private adult torrent tracker.
    API reference: https://dirtybytes.net/faq#48 to #55
    """

    auth_type = "other_api"
    tracker = "DIRTYBYTES"
    display_name = "DirtyBytes"
    source_flag = "DirtyBytes"
    base_url = "https://dirtybytes.net"
    api_base_url = f"{base_url}/api/v1/torrents"
    torrent_url = f"{base_url}/torrent/"
    banned_groups: tuple[str, ...] = ()
    supported_categories = ("XXX",)
    tracker_urls = ("dirtybytes.net",)

    # Release categories from GET /api/v1/catalog (release_categories).
    scene_ids: ClassVar[dict[str, int]] = {"SD": 7, "720p": 8, "1080p": 9, "1440p": 10, "2160p": 11, "4320p": 12}
    movie_ids: ClassVar[dict[str, int]] = {"SD": 1, "720p": 2, "1080p": 3, "1440p": 4, "2160p": 5, "4320p": 6}
    vr_scene_ids: ClassVar[dict[int, int]] = {1080: 19, 1440: 20, 2160: 21, 2880: 22, 3456: 29, 3600: 23, 3840: 30, 4320: 24}
    vr_movie_ids: ClassVar[dict[int, int]] = {1080: 13, 1440: 14, 2160: 15, 2880: 16, 3456: 27, 3600: 17, 3840: 28, 4320: 18}
    pack_id = 26

    _vr_re = re.compile(r"\b(?:vr|vr180|vr 180|180x180|3dh|virtual reality|oculus|quest)\b")
    _movie_re = re.compile(r"\b(?:movie|feature|full movie|dvdrip)\b")
    _pack_re = re.compile(r"\b(?:pack|megapack|boxset|box set|siterip|site rip|collection)\b")

    # Upload limits from the API documentation.
    max_images = 10
    max_image_size = 10 * 1024 * 1024
    max_images_total = 80 * 1024 * 1024

    def __init__(self, config: Config) -> None:
        self.config = config
        self.common = Common(config)
        self.tracker_config: dict[str, Any] = cast(dict[str, Any], config.get("TRACKERS", {}).get(self.tracker, {}))
        self.api_key = str(self.tracker_config.get("api_key", "")).strip()

    def _headers(self, meta: Meta) -> dict[str, str]:
        return {
            "X-API-KEY": self.api_key,
            "User-Agent": f"{meta.ua_name} {meta.current_version} ({platform.system()} {platform.release()})",
            "Accept": "application/json",
        }

    @staticmethod
    def _error_message(response: httpx.Response) -> str:
        try:
            body = response.json()
        except ValueError:
            return f"HTTP {response.status_code}: {response.text[:500]}"
        if isinstance(body, dict):
            body_dict = cast(dict[str, Any], body)
            message = body_dict.get("message") or body_dict.get("error")
            if message:
                return f"HTTP {response.status_code}: {message}"
        return f"HTTP {response.status_code}: {str(body)[:500]}"

    def _normalized_name(self, meta: Meta) -> str:
        text = " ".join([str(meta.basename_no_ext or ""), *(str(keyword) for keyword in meta.keywords or [])])
        return re.sub(r"[^a-z0-9]+", " ", text.casefold())

    def _video_height(self, meta: Meta) -> int:
        if meta.video_height:
            return int(meta.video_height)
        match = re.match(r"(\d{3,4})[pi]$", str(meta.resolution or ""))
        return int(match.group(1)) if match else 0

    def get_category_id(self, meta: Meta) -> int:
        name = self._normalized_name(meta)
        if self._pack_re.search(name):
            return self.pack_id

        is_movie = meta.is_disc == "DVD" or bool(self._movie_re.search(name))
        height = self._video_height(meta)

        if self._vr_re.search(name):
            vr_ids = self.vr_movie_ids if is_movie else self.vr_scene_ids
            # VR frames rarely match a standard resolution; use the closest listed height.
            closest = min(vr_ids, key=lambda value: abs(value - height)) if height else 2160
            return vr_ids[closest]

        ids = self.movie_ids if is_movie else self.scene_ids
        resolution = str(meta.resolution or "")
        if resolution == "1080i":
            resolution = "1080p"
        if meta.sd or resolution in ("480p", "480i", "540p", "540i", "576p", "576i"):
            return ids["SD"]
        if resolution in ids:
            return ids[resolution]
        # Non-standard sizes: pick the largest category not above the frame height.
        for label, minimum in (("4320p", 4320), ("2160p", 2160), ("1440p", 1440), ("1080p", 1080), ("720p", 720)):
            if height >= minimum:
                return ids[label]
        return ids["SD"]

    async def get_name(self, meta: Meta) -> str:
        if meta.manual_name is not None:
            return meta.manual_name.strip()
        return str(meta.scene_name or meta.basename_no_ext)

    async def get_mediainfo(self, meta: Meta) -> str:
        if meta.is_disc == "BDMV":
            return await self.common.get_bdmv_mediainfo(meta)
        mi_path = Path(meta.base_dir) / "tmp" / meta.uuid / "MEDIAINFO_CLEANPATH.txt"
        if not mi_path.is_file():
            return ""
        async with aiofiles.open(mi_path, encoding="utf-8") as mi_file:
            return await mi_file.read()

    async def _read_image(self, path: str | Path) -> tuple[str, bytes, str] | None:
        image_path = Path(path)
        try:
            if not image_path.is_file() or image_path.stat().st_size > self.max_image_size:
                return None
            async with aiofiles.open(image_path, "rb") as image_file:
                image_bytes = await image_file.read()
        except OSError as e:
            logger.info(f"{self.tracker}: [yellow]Failed to read image {image_path}: {e}[/yellow]")
            return None
        if not is_valid_image_bytes(image_bytes):
            return None
        if image_bytes.startswith(b"\xff\xd8\xff"):
            return (f"{image_path.stem}.jpg", image_bytes, "image/jpeg")
        if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
            return (f"{image_path.stem}.png", image_bytes, "image/png")
        if image_bytes.startswith((b"GIF87a", b"GIF89a")):
            return (f"{image_path.stem}.gif", image_bytes, "image/gif")
        if image_bytes.startswith(b"RIFF") and image_bytes[8:12] == b"WEBP":
            return (f"{image_path.stem}.webp", image_bytes, "image/webp")
        return None

    async def get_images(self, meta: Meta) -> tuple[list[tuple[str, bytes, str]], bool]:
        """Collect the local cover and contact sheets that DirtyBytes hosts through images[].

        Returns the images and whether any screenshot was attached.
        """
        paths: list[tuple[str | Path, bool]] = []
        # Without a public cover URL, the first attached image becomes the listing preview.
        if not self.get_firstpic(meta) and meta.artwork_path:
            paths.append((meta.artwork_path, False))
        paths.extend((path, True) for path in manifest_files(meta.base_dir, meta.uuid, "main"))

        images: list[tuple[str, bytes, str]] = []
        has_screenshots = False
        total = 0
        for path, is_screenshot in paths:
            if len(images) >= self.max_images:
                break
            image = await self._read_image(path)
            if image is None or total + len(image[1]) > self.max_images_total:
                continue
            images.append(image)
            total += len(image[1])
            has_screenshots = has_screenshots or is_screenshot
        return images, has_screenshots

    @staticmethod
    def get_firstpic(meta: Meta) -> str:
        artwork_url = str(meta.artwork_url or "")
        return artwork_url if artwork_url.startswith(("http://", "https://")) else ""

    async def generate_description(self, meta: Meta, attach_screenshots: bool) -> str:
        builder = DescriptionBuilder(self.tracker, self.config)
        return await builder.general_description_generator(
            meta,
            bluray=False,
            logo=False,
            mediainfo=False,
            screenshots=not attach_screenshots,
            signature=f"[center][url=https://github.com/wastaken7/Upload-Assistant]{meta.ua_signature}[/url][/center]",
        )

    async def search_existing(self, meta: Meta) -> list[dict[str, Any]]:
        params = {"name": await self.get_name(meta)}
        async with httpx.AsyncClient(headers=self._headers(meta), timeout=30.0) as client:
            response = await client.get(f"{self.api_base_url}/dupe-search", params=params)
        if response.status_code != 200:
            raise RuntimeError(f"{self.tracker}: duplicate search failed: {self._error_message(response)}")

        try:
            results: Any = response.json()
        except ValueError as e:
            raise RuntimeError(f"{self.tracker}: unexpected search response: {response.text[:200]}") from e
        if isinstance(results, dict):
            results_dict = cast(dict[str, Any], results)
            results = results_dict.get("data") or results_dict.get("torrents") or results_dict.get("results") or []

        dupes: list[dict[str, Any]] = []
        for item in cast(list[Any], results) if isinstance(results, list) else []:
            if not isinstance(item, dict):
                continue
            torrent = cast(dict[str, Any], item)
            name = torrent.get("name")
            if not name:
                continue
            torrent_id = torrent.get("id")
            dupes.append(
                {
                    "id": torrent_id,
                    "name": str(name),
                    "size": torrent.get("size"),
                    "files": [],
                    "file_count": torrent.get("numfiles", ""),
                    "link": f"{self.torrent_url}{torrent_id}" if torrent_id else None,
                    "download": f"{self.api_base_url}/download/{torrent_id}" if torrent_id else None,
                }
            )
        return dupes

    async def get_data(self, meta: Meta, attach_screenshots: bool, preview: bool = False) -> dict[str, Any]:
        """Build the upload form; a ``preview`` leaves out the description and MediaInfo."""
        anon = meta.anon or self.tracker_config.get("anon", False)
        data: dict[str, Any] = {
            "category": self.get_category_id(meta),
            "anonymousUpload": "1" if anon else "0",
            "nfo": "" if preview else await self.generate_description(meta, attach_screenshots),
            # UA uploads unpacked files; mark scene releases as unpacked from their RARs.
            "unrar": "1" if meta.scene else "0",
        }
        performers = [str(name).strip()[:120] for name in (meta.cast or meta.manual_cast or []) if str(name).strip()]
        tags = [str(tag).strip()[:64] for tag in meta.keywords or [] if str(tag).strip()]
        languages = [str(language).strip().lower() for language in meta.audio_languages or [] if str(language).strip()]
        year = meta.year if isinstance(meta.year, int) and meta.year >= 1888 else None
        optional: dict[str, Any] = {
            "studio": str(meta.publisher or "").strip()[:120],
            "performers": ", ".join(performers[:100]),
            "content_tags": ", ".join(tags[:12]),
            "language": ", ".join(dict.fromkeys(languages)),
            "release_year": str(year) if year else "",
            "mediainfo": "" if preview else await self.get_mediainfo(meta),
            "firstpic": self.get_firstpic(meta),
        }
        data.update({key: value for key, value in optional.items() if value})
        return data

    async def get_payload_preview(self, meta: Meta) -> payload_preview.TrackerPreview:
        """The upload form as it is known before screenshots, for the Web UI to show and edit."""
        specs = {
            "category": payload_preview.choice(
                "Category",
                [
                    (1, "Movie SD"),
                    (2, "Movie 720p"),
                    (3, "Movie 1080p"),
                    (4, "Movie 1440p"),
                    (5, "Movie 2160p"),
                    (6, "Movie 4320p"),
                    (7, "Scene SD"),
                    (8, "Scene 720p"),
                    (9, "Scene 1080p"),
                    (10, "Scene 1440p"),
                    (11, "Scene 2160p"),
                    (12, "Scene 4320p"),
                    (13, "VR movie 1080"),
                    (14, "VR movie 1440"),
                    (15, "VR movie 2160"),
                    (16, "VR movie 2880"),
                    (27, "VR movie 3456"),
                    (17, "VR movie 3600"),
                    (28, "VR movie 3840"),
                    (18, "VR movie 4320"),
                    (19, "VR scene 1080"),
                    (20, "VR scene 1440"),
                    (21, "VR scene 2160"),
                    (22, "VR scene 2880"),
                    (29, "VR scene 3456"),
                    (23, "VR scene 3600"),
                    (30, "VR scene 3840"),
                    (24, "VR scene 4320"),
                    (26, "Pack"),
                ],
            ),
            "anonymousUpload": payload_preview.flag("Anonymous"),
            "unrar": payload_preview.flag("Unpacked from RARs"),
            "studio": payload_preview.text("Studio", max_length=120),
            "performers": payload_preview.text("Performers", max_length=1000),
            "content_tags": payload_preview.text("Tags", max_length=1000),
            "language": payload_preview.text("Language"),
            "release_year": payload_preview.number("Year"),
            "firstpic": payload_preview.text("Cover URL", max_length=1000),
        }
        deferred = {"nfo": payload_preview.DESCRIPTION_NOTE, "mediainfo": "Read from the MediaInfo report at upload time"}
        data = await self.get_data(meta, attach_screenshots=False, preview=True)
        return payload_preview.describe(self.tracker, data, specs, deferred=deferred, name=await self.get_name(meta))

    async def upload(self, meta: Meta) -> bool:
        tracker_status = meta.tracker_status.setdefault(self.tracker, {})
        images, attach_screenshots = await self.get_images(meta)
        data = payload_preview.apply_payload_edits(meta, self.tracker, await self.get_data(meta, attach_screenshots))

        if meta.debug:
            logger.info(f"{self.tracker}: Request Data:")
            logger.info(Redaction.redact_private_info({**data, "mediainfo": "...[DEBUG MODE]" if data.get("mediainfo") else ""}))
            logger.info(f"{self.tracker}: {len(images)} image(s) would be attached.")
            tracker_status["status_message"] = "Debug mode enabled, not uploading."
            await self.common.create_torrent_for_upload(meta, f"{self.tracker}_DEBUG", f"{self.tracker}_DEBUG", announce_url="https://fake.tracker")
            return True

        # The site sets its own announce and source; the copy downloaded afterwards is the one to seed.
        await self.common.create_torrent_for_upload(meta, self.tracker, self.source_flag, announce_url="https://fake.tracker")
        torrent_path = Path(meta.base_dir) / "tmp" / meta.uuid / f"[{self.tracker}].torrent"
        async with aiofiles.open(torrent_path, "rb") as torrent_file:
            torrent_bytes = await torrent_file.read()
        # The release title is taken from the .torrent filename.
        files: list[tuple[str, tuple[str, bytes, str]]] = [("file", (f"{await self.get_name(meta)}.torrent", torrent_bytes, "application/x-bittorrent"))]
        files.extend(("images[]", image) for image in images)

        headers = self._headers(meta)
        try:
            async with httpx.AsyncClient(headers=headers, timeout=180.0) as client:
                response = await client.post(f"{self.api_base_url}/upload", data=data, files=files)
        except httpx.TimeoutException:
            tracker_status["status_message"] = "data error: Request timed out; check for a duplicate on the site before retrying."
            return False
        except httpx.RequestError as e:
            tracker_status["status_message"] = f"data error: Unable to upload: {e!r}"
            return False

        try:
            parsed: Any = response.json()
        except ValueError:
            parsed = None
        result: dict[str, Any] = cast(dict[str, Any], parsed) if isinstance(parsed, dict) else {}

        if response.status_code == 409:
            existing = result.get("torrent_id")
            tracker_status["status_message"] = (
                f"data error: Duplicate upload: {self.torrent_url}{existing}/" if existing else f"data error: Duplicate upload: {self._error_message(response)}"
            )
            return False
        torrent_id = str(result.get("id") or "")
        if response.status_code not in (200, 201) or not torrent_id:
            tracker_status["status_message"] = f"data error: {self._error_message(response)}"
            return False

        tracker_status["torrent_id"] = f"{torrent_id}/"
        tracker_status["status_message"] = result.get("message") or "Upload successful"
        # The tracker generates the .torrent asynchronously; an immediate download can 404.
        for attempt in range(4):
            if await self.common.download_tracker_torrent(meta, self.tracker, headers=headers, downurl=f"{self.api_base_url}/download/{torrent_id}"):
                return True
            if attempt < 3:
                await asyncio.sleep(10 * (attempt + 1))
        tracker_status["status_message"] = f"Uploaded, but the registered .torrent could not be downloaded. Download it from {self.torrent_url}{torrent_id}/ before seeding."
        return True
