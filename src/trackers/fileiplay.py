# Upload Assistant © 2026 Audionut & wastaken7 — Licensed under UAPL v1.0
import asyncio
import io
import platform
import re
import unicodedata
from pathlib import Path
from typing import Any, ClassVar, cast

import aiofiles
import httpx
from defusedxml import ElementTree
from PIL import Image
from torf import Torrent

from src import payload_preview
from src.cogs.redaction import Redaction
from src.console import logger
from src.get_desc import DescriptionBuilder
from src.meta import Meta
from src.screenshot_manifest import files as manifest_files
from src.trackers.common import Common
from src.trackers.USENET.search_helpers import build_newznab_search_query

Config = dict[str, Any]

TORZNAB_ATTR = "{http://torznab.com/schemas/2015/feed}attr"


class FileIPlay:
    """
    FileIPlay is a private general tracker.
    Upload API reference: https://fileiplay.org/settings/api/documentation
    Duplicate search and the published .torrent come from its Torznab feed (https://fileiplay.org/integrations).
    """

    auth_type = "other_api"
    tracker = "FILEIPLAY"
    display_name = "FileIPlay"
    source_flag = "FileIPlay"
    base_url = "https://fileiplay.org"
    api_url = f"{base_url}/api/v1"
    torznab_url = f"{base_url}/torznab/api"
    torrent_url = f"{base_url}/torrents/"
    banned_groups: tuple[str, ...] = ()
    supported_categories = ("MOVIE", "TV", "GAME", "MUSIC", "XXX")
    tracker_urls = ("fileiplay.org",)

    # Category IDs from the upload form (GET /api/v1/categories lists the same).
    category_ids: ClassVar[dict[str, int]] = {
        "Movies: Anime": 1,
        "Movies: BluRay": 5,
        "Movies: DVD": 9,
        "Movies: HD": 11,
        "HDTV Episodes": 13,
        "TV Episodes": 20,
        "Movies: XVID": 24,
        "Movies: XXX": 27,
        "Music": 28,
        "Games: PC-ISO": 30,
        "Movies: 4K": 31,
        "Sport": 42,
    }
    movie_category_ids = frozenset({1, 5, 9, 11, 24, 31})
    tv_category_ids = frozenset({13, 20})

    # Limits from the API documentation.
    max_name_length = 255
    max_text_length = 100_000
    max_genre_length = 1000
    max_images = 10
    max_image_size = 10 * 1024 * 1024
    max_image_width = 4096
    max_image_height = 2160
    image_types: ClassVar[dict[str, str]] = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}

    _no_group_re = re.compile(r"^-(?:nogroup|nogrp|unknown|unk)$", re.IGNORECASE)

    def __init__(self, config: Config) -> None:
        self.config = config
        self.common = Common(config)
        self.tracker_config: dict[str, Any] = cast(dict[str, Any], config.get("TRACKERS", {}).get(self.tracker, {}))
        self.api_key = str(self.tracker_config.get("api_key", "")).strip()
        self.torznab_key = str(self.tracker_config.get("torznab_api_key", "")).strip()

    def _headers(self, meta: Meta, accept: str = "application/json") -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": f"{meta.ua_name} {meta.current_version} ({platform.system()} {platform.release()})",
            "Accept": accept,
        }

    @staticmethod
    def _user_agent(meta: Meta) -> dict[str, str]:
        return {"User-Agent": f"{meta.ua_name} {meta.current_version} ({platform.system()} {platform.release()})"}

    @staticmethod
    def _error_message(response: httpx.Response) -> str:
        """Format FileIPlay's {"error": {"code", "message", "fields"}} responses for the user."""
        try:
            body: Any = response.json()
        except ValueError:
            return f"HTTP {response.status_code}: {response.text[:500]}"
        error = cast(dict[str, Any], body).get("error") if isinstance(body, dict) else None
        if not isinstance(error, dict):
            return f"HTTP {response.status_code}: {str(body)[:500]}"
        error_dict = cast(dict[str, Any], error)
        message = f"HTTP {response.status_code}: {error_dict.get('message') or response.reason_phrase}"
        if code := error_dict.get("code"):
            message += f" ({code})"
        fields = error_dict.get("fields")
        if isinstance(fields, dict):
            details = [
                f"{field}: {' '.join(str(item) for item in cast(list[Any], errors))}" for field, errors in cast(dict[str, Any], fields).items() if isinstance(errors, list)
            ]
            if details:
                message += f" - {'; '.join(details)}"
        if response.status_code == 429 and (retry_after := response.headers.get("Retry-After")):
            message += f" Retry after {retry_after}s."
        return message

    def get_category_id(self, meta: Meta) -> int:
        category = str(meta.category).upper()
        if meta.is_sports:
            return self.category_ids["Sport"]
        if category == "XXX":
            return self.category_ids["Movies: XXX"]
        if category == "MUSIC":
            return self.category_ids["Music"]
        if category == "GAME":
            return self.category_ids["Games: PC-ISO"]
        if category == "TV":
            # The site lists SD episodes under "TV" and 720p and above under "HD TV".
            return self.category_ids["TV Episodes"] if meta.sd else self.category_ids["HDTV Episodes"]

        if meta.anime:
            return self.category_ids["Movies: Anime"]
        if meta.resolution in ("2160p", "4320p"):
            return self.category_ids["Movies: 4K"]
        if meta.is_disc in ("BDMV", "HDDVD"):
            return self.category_ids["Movies: BluRay"]
        dvd_remux = str(meta.type).upper() == "REMUX" and str(meta.source or "") in ("PAL DVD", "NTSC DVD", "DVD")
        if meta.is_disc == "DVD" or str(meta.type).upper() == "DVDRIP" or dvd_remux:
            return self.category_ids["Movies: DVD"]
        if meta.sd:
            return self.category_ids["Movies: XVID"]
        return self.category_ids["Movies: HD"]

    @staticmethod
    def clean_name(name: str) -> str:
        """Apply the naming guide's character rules: dot-separated, ASCII letters, digits, dots, hyphens and HDR10+."""
        name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
        name = name.replace("&", " and ").replace("'", "").replace("DD+", "DDP")
        # Audio codecs sit next to their channels: DDP5.1, AAC2.0, DTS5.1.
        name = re.sub(r"\b(AAC|AC3|DDP|DD|DTS|EAC3|FLAC|LPCM|MP3|Opus|PCM)\s+(\d\.\d)\b", r"\1\2", name)
        name = re.sub(r"(?<!HDR10)\+", " ", name)
        name = re.sub(r"[^A-Za-z0-9.+-]+", ".", name)
        name = re.sub(r"\.-\.", ".", name)
        name = re.sub(r"\.{2,}", ".", name)
        return name.strip(".-")

    async def get_name(self, meta: Meta) -> str:
        if meta.manual_name is not None:
            return self.clean_name(meta.manual_name)
        if meta.scene and meta.scene_name:
            return self.clean_name(meta.scene_name)

        name = str(meta.name)
        if str(meta.category).upper() in ("MOVIE", "TV"):
            if meta.aka:
                name = name.replace(meta.aka, " ")
            tag = meta.tag or ""
            body = name[: -len(tag)] if tag and name.endswith(tag) else name
            if self._no_group_re.match(tag):
                tag = ""
            words = f" {' '.join(body.split())} "
            # The guide orders movies and TV as Title.Year.Resolution.HDR.Source.Codec.Audio-GROUP.
            audio = " ".join(word for word in str(meta.audio).split() if word not in ("Dual-Audio", "Dubbed"))
            if meta.audio and f" {meta.audio} " in words:
                words = words.replace(f" {meta.audio} ", " ", 1) + (f"{audio} " if audio else "")
            hdr, resolution = str(meta.hdr).strip(), str(meta.resolution)
            if hdr and f" {hdr} " in words and f" {resolution} " in words:
                words = words.replace(f" {hdr} ", " ", 1).replace(f" {resolution} ", f" {resolution} {hdr} ", 1)
            name = words.strip() + tag
        return self.clean_name(name)

    async def get_mediainfo(self, meta: Meta) -> str:
        tmp_dir = Path(meta.base_dir) / "tmp" / meta.uuid
        bd_summary_path = tmp_dir / "BD_SUMMARY_00.txt"
        if meta.is_disc == "BDMV" and bd_summary_path.is_file():
            # FileIPlay has no BDInfo field; Blu-ray discs send BDInfo as the MediaInfo.
            async with aiofiles.open(bd_summary_path, encoding="utf-8") as bd_file:
                mediainfo = await bd_file.read()
        elif meta.is_disc == "BDMV":
            mediainfo = await self.common.get_bdmv_mediainfo(meta)
        else:
            mi_path = tmp_dir / "MEDIAINFO_CLEANPATH.txt"
            if not mi_path.is_file():
                return ""
            async with aiofiles.open(mi_path, encoding="utf-8") as mi_file:
                mediainfo = await mi_file.read()
        if len(mediainfo) > self.max_text_length:
            logger.warning(f"{self.tracker}: [yellow]MediaInfo is longer than {self.max_text_length} characters and will not be sent.[/yellow]")
            return ""
        return mediainfo

    async def _read_image(self, path: Path) -> tuple[str, bytes, str] | None:
        try:
            if not path.is_file() or path.stat().st_size > self.max_image_size:
                return None
            async with aiofiles.open(path, "rb") as image_file:
                image_bytes = await image_file.read()
            with Image.open(io.BytesIO(image_bytes)) as image:
                image_format, width, height = str(image.format), image.width, image.height
        except (OSError, ValueError, Image.DecompressionBombError) as e:
            logger.info(f"{self.tracker}: [yellow]Skipping screenshot {path.name}: {e}[/yellow]")
            return None
        content_type = self.image_types.get(image_format)
        if not content_type or width > self.max_image_width or height > self.max_image_height:
            return None
        extension = "jpg" if image_format == "JPEG" else image_format.lower()
        return (f"{path.stem}.{extension}", image_bytes, content_type)

    async def get_images(self, meta: Meta) -> list[tuple[str, bytes, str]]:
        """Collect the local screenshots FileIPlay hosts itself through images[]."""
        images: list[tuple[str, bytes, str]] = []
        for path in manifest_files(meta.base_dir, meta.uuid, "main"):
            if len(images) >= self.max_images:
                break
            if image := await self._read_image(path):
                images.append(image)
        return images

    async def generate_description(self, meta: Meta, attach_screenshots: bool) -> str:
        builder = DescriptionBuilder(self.tracker, self.config)
        # The TMDB logo is left out unless the FILEIPLAY config itself sets add_logo.
        add_logo = str(self.tracker_config.get("add_logo", "")).strip().lower() in ("true", "1", "yes", "on")
        return await builder.general_description_generator(
            meta,
            logo=add_logo,
            mediainfo=False,
            screenshots=not attach_screenshots,
            signature=f"[center][url=https://github.com/wastaken7/Upload-Assistant]{meta.ua_signature}[/url][/center]",
        )

    def _imdb_url(self, meta: Meta) -> str:
        imdb_tt = str(meta.imdb_tt or "")
        if not imdb_tt and meta.imdb_id:
            imdb_tt = f"tt{int(meta.imdb_id):07d}"
        return f"https://www.imdb.com/title/{imdb_tt}/" if re.fullmatch(r"tt\d+", imdb_tt) else ""

    @staticmethod
    def _steam_id(meta: Meta) -> str:
        match = re.search(r"/app/(\d+)", str(meta.steam_url or ""))
        return match.group(1) if match else ""

    async def get_data(self, meta: Meta, attach_screenshots: bool, preview: bool = False) -> dict[str, Any]:
        """Build the multipart upload form; a ``preview`` leaves out the description and MediaInfo."""
        category_id = self.get_category_id(meta)
        anon = bool(meta.anon) or bool(self.tracker_config.get("anon", False))
        data: dict[str, Any] = {
            "category_id": str(category_id),
            "name": await self.get_name(meta),
            "anon": "1" if anon else "0",
        }

        tmdb_id = meta.tmdb_id or meta.tmdb
        # The site rejects a TMDB type that does not match the chosen category.
        tmdb_type = "movie" if category_id in self.movie_category_ids else "tv" if category_id in self.tv_category_ids else ""
        poster = str(meta.artwork_url or "")
        optional: dict[str, Any] = {
            "tmdbid": str(tmdb_id) if tmdb_id and tmdb_type else "",
            "tmdb_type": tmdb_type if tmdb_id else "",
            "tvdbid": str(meta.tvdb_id) if meta.tvdb_id and tmdb_type == "tv" else "",
            "imdb_url": self._imdb_url(meta) if tmdb_type else "",
            "genre": ", ".join(str(genre).strip() for genre in meta.genres or [] if str(genre).strip())[: self.max_genre_length],
            # TMDB enrichment supplies the poster for movies and TV linked to TMDB.
            "poster": poster if not (tmdb_id and tmdb_type) and poster.startswith(("http://", "https://")) else "",
            "steamid": self._steam_id(meta) if str(meta.category).upper() == "GAME" else "",
        }
        if tmdb_type == "tv" and meta.season and 0 <= meta.season_int <= 999:
            optional["season"] = str(meta.season_int)
            if not meta.tv_pack and 1 <= meta.episode_int <= 9999:
                optional["episode"] = str(meta.episode_int)
        data.update({key: value for key, value in optional.items() if value})

        if not preview:
            data["description"] = await self.generate_description(meta, attach_screenshots)
            if mediainfo := await self.get_mediainfo(meta):
                data["mediainfo"] = mediainfo
        return data

    async def get_payload_preview(self, meta: Meta) -> payload_preview.TrackerPreview:
        """The upload form as it is known before screenshots, for the Web UI to show and edit."""
        specs = {
            "category_id": payload_preview.choice("Category", [(str(category_id), label) for label, category_id in self.category_ids.items()]),
            "name": payload_preview.text("Name", max_length=self.max_name_length),
            "anon": payload_preview.flag("Anonymous"),
            "tmdbid": payload_preview.text("TMDB ID", numeric=True),
            "tmdb_type": payload_preview.choice("TMDB type", [("movie", "Movie"), ("tv", "TV")]),
            "tvdbid": payload_preview.text("TVDB ID", numeric=True),
            "imdb_url": payload_preview.text("IMDb URL"),
            "season": payload_preview.number("Season"),
            "episode": payload_preview.number("Episode"),
            "genre": payload_preview.text("Genre", max_length=self.max_genre_length),
            "poster": payload_preview.text("Poster URL", max_length=1000),
            "steamid": payload_preview.text("Steam app ID", numeric=True),
        }
        deferred = {"description": payload_preview.DESCRIPTION_NOTE, "mediainfo": "Read from the MediaInfo report at upload time"}
        data = await self.get_data(meta, attach_screenshots=False, preview=True)
        return payload_preview.describe(self.tracker, data, specs, deferred=deferred)

    async def get_additional_checks(self, meta: Meta) -> bool:
        if not self.api_key:
            logger.warning(f"{self.tracker}: [red]Set api_key to a personal token from {self.base_url}/settings/api.[/red]")
            return False
        if not self.torznab_key:
            # Without it neither the duplicate search nor the published .torrent download can work.
            logger.warning(f"{self.tracker}: [red]Set torznab_api_key to the integration API key from {self.base_url}/integrations.[/red]")
            return False
        if len(await self.get_name(meta)) > self.max_name_length:
            logger.warning(f"{self.tracker}: [red]Release name is longer than {self.max_name_length} characters.[/red]")
            return False
        return True

    async def _torznab_search(self, meta: Meta, query: str) -> list[dict[str, Any]]:
        """Search the Torznab feed; results carry the details link, info hash and keyed download link."""
        if not self.torznab_key:
            raise RuntimeError(f"{self.tracker}: set torznab_api_key to the integration API key from {self.base_url}/integrations.")
        try:
            async with httpx.AsyncClient(headers=self._user_agent(meta), timeout=30.0) as client:
                response = await client.get(self.torznab_url, params={"t": "search", "q": query, "apikey": self.torznab_key})
        except httpx.RequestError as e:
            # The request URL carries the key, so only the error type is reported.
            raise RuntimeError(f"{self.tracker}: Torznab search failed ({type(e).__name__}).") from None
        if response.status_code != 200:
            raise RuntimeError(f"{self.tracker}: Torznab search failed with HTTP {response.status_code}.")

        try:
            root = ElementTree.fromstring(response.text)
        except ElementTree.ParseError:
            raise RuntimeError(f"{self.tracker}: unexpected Torznab response: {response.text[:200]}") from None
        if root.tag == "error":
            raise RuntimeError(f"{self.tracker}: Torznab error {root.attrib.get('code', '')}: {root.attrib.get('description', '')}")

        results: list[dict[str, Any]] = []
        for item in root.iter("item"):
            attrs = {str(attr.attrib.get("name", "")).lower(): str(attr.attrib.get("value", "")) for attr in item.findall(TORZNAB_ATTR)}
            enclosure = item.find("enclosure")
            size = attrs.get("size") or item.findtext("size") or (enclosure.attrib.get("length") if enclosure is not None else "") or ""
            details = str(item.findtext("comments") or item.findtext("guid") or "")
            id_match = re.search(r"/torrents/(\d+)", details)
            results.append(
                {
                    "name": str(item.findtext("title") or ""),
                    "size": int(size) if str(size).isdigit() else 0,
                    "file_count": int(attrs["files"]) if attrs.get("files", "").isdigit() else 0,
                    "link": details,
                    "id": id_match.group(1) if id_match else "",
                    "infohash": attrs.get("infohash", "").lower(),
                    "download": str(item.findtext("link") or (enclosure.attrib.get("url") if enclosure is not None else "") or ""),
                }
            )
        return results

    async def search_existing(self, meta: Meta) -> list[dict[str, Any]]:
        results = await self._torznab_search(meta, build_newznab_search_query(meta))
        # The download link carries the integration key and is not kept with the dupes.
        return [
            {"name": result["name"], "size": result["size"], "files": [], "file_count": result["file_count"], "link": result["link"], "id": result["id"]}
            for result in results
            if result["name"]
        ]

    async def download_published_torrent(self, meta: Meta, name: str, torrent_id: str, info_hash: str) -> bool:
        """Download the torrent FileIPlay published, which carries the passkey announce and may have a new info hash."""
        if not self.torznab_key:
            return False
        for attempt in range(3):
            if attempt:
                await asyncio.sleep(10 * attempt)
            try:
                results = await self._torznab_search(meta, name)
            except RuntimeError as e:
                logger.warning(f"[yellow]{e}[/yellow]")
                continue
            match = next((result for result in results if (info_hash and result["infohash"] == info_hash) or result["id"] == torrent_id), None)
            if not match or not match["download"]:
                continue
            try:
                async with httpx.AsyncClient(headers=self._user_agent(meta), follow_redirects=True, timeout=30.0) as client:
                    response = await client.get(match["download"])
            except httpx.RequestError as e:
                logger.warning(f"{self.tracker}: [yellow]Could not download the published torrent ({type(e).__name__}).[/yellow]")
                continue
            if response.status_code != 200:
                logger.warning(f"{self.tracker}: [yellow]Could not download the published torrent (HTTP {response.status_code}).[/yellow]")
                continue
            try:
                downloaded_hash = Torrent.read_stream(response.content).infohash.lower()
            except Exception:
                logger.warning(f"{self.tracker}: [yellow]The downloaded file is not a valid torrent.[/yellow]")
                continue
            if info_hash and downloaded_hash != info_hash:
                logger.warning(f"{self.tracker}: [yellow]The downloaded torrent does not match the published info hash.[/yellow]")
                continue
            torrent_path = Path(meta.base_dir) / "tmp" / meta.uuid / f"[{self.tracker}].torrent"
            async with aiofiles.open(torrent_path, "wb") as torrent_file:
                await torrent_file.write(response.content)
            return True
        return False

    async def upload(self, meta: Meta) -> bool:
        tracker_status = meta.tracker_status.setdefault(self.tracker, {})
        images = await self.get_images(meta)
        data = payload_preview.apply_payload_edits(meta, self.tracker, await self.get_data(meta, attach_screenshots=bool(images)))

        if meta.debug:
            logger.info(f"{self.tracker}: Request Data:")
            logger.info(Redaction.redact_private_info({**data, "mediainfo": "...[DEBUG MODE]" if data.get("mediainfo") else ""}))
            logger.info(f"{self.tracker}: {len(images)} screenshot(s) would be attached.")
            tracker_status["status_message"] = "Debug mode enabled, not uploading."
            await self.common.create_torrent_for_upload(meta, f"{self.tracker}_DEBUG", f"{self.tracker}_DEBUG", announce_url="https://fake.tracker")
            return True

        # FileIPlay replaces the announce and sets private=1; the published copy is downloaded below.
        await self.common.create_torrent_for_upload(meta, self.tracker, self.source_flag, announce_url="https://fake.tracker")
        torrent_path = Path(meta.base_dir) / "tmp" / meta.uuid / f"[{self.tracker}].torrent"
        async with aiofiles.open(torrent_path, "rb") as torrent_file:
            torrent_bytes = await torrent_file.read()
        # The local copy has a placeholder announce; only the published torrent is left to seed.
        torrent_path.unlink(missing_ok=True)
        files: list[tuple[str, tuple[str, bytes, str]]] = [("torrent", (f"{data['name']}.torrent", torrent_bytes, "application/x-bittorrent"))]
        files.extend(("images[]", image) for image in images)

        try:
            async with httpx.AsyncClient(headers=self._headers(meta), timeout=180.0) as client:
                response = await client.post(f"{self.api_url}/torrents", data=data, files=files)
        except httpx.TimeoutException:
            tracker_status["status_message"] = "data error: Request timed out; check your upload history on the site before retrying (a retry can return 409)."
            return False
        except httpx.RequestError as e:
            tracker_status["status_message"] = f"data error: Unable to upload: {e!r}"
            return False

        if response.status_code != 201:
            tracker_status["status_message"] = f"data error: {self._error_message(response)}"
            return False

        try:
            body: Any = response.json()
        except ValueError:
            body = None
        result_data = cast(dict[str, Any], body).get("data") if isinstance(body, dict) else None
        if not isinstance(result_data, dict):
            tracker_status["status_message"] = f"data error: Unexpected response, check the site manually: {response.text[:500]}"
            return False
        result = cast(dict[str, Any], result_data)

        torrent_id = str(result.get("id") or "")
        if not torrent_id:
            tracker_status["status_message"] = f"data error: No torrent id in response, check the site manually: {result}"
            return False
        tracker_status["torrent_id"] = torrent_id
        details_url = str(result.get("url") or f"{self.torrent_url}{torrent_id}")
        response_meta = cast(dict[str, Any], body).get("meta")
        warnings = cast(list[Any], cast(dict[str, Any], response_meta).get("warnings") or []) if isinstance(response_meta, dict) else []
        warning_text = f" Warnings: {'; '.join(str(warning) for warning in warnings)}" if warnings else ""
        tracker_status["status_message"] = f"Uploaded.{warning_text}"

        published_name = str(result.get("name") or data["name"])
        info_hash = str(result.get("info_hash") or "").lower()
        if not await self.download_published_torrent(meta, published_name, torrent_id, info_hash):
            tracker_status["status_message"] = (
                f"data error: Uploaded, but the published .torrent could not be downloaded. Download it from {details_url} before seeding.{warning_text}"
            )
            return False
        return True
