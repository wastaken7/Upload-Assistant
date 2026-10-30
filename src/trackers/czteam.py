# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import base64
import platform
from pathlib import Path
from typing import Any, ClassVar, cast

import aiofiles
import httpx

from src import payload_preview
from src.cogs.redaction import Redaction
from src.console import logger
from src.get_desc import DescriptionBuilder
from src.languages import languages_manager
from src.meta import Meta
from src.trackers.common import Common

Config = dict[str, Any]


class CZTeam:
    """
    CZTeam is a Romanian Private Torrent Tracker
    """

    base_url = "https://czteam.me"

    auth_type = "other_api"
    tracker = "CZTEAM"
    display_name = "CZTeam"
    source_flag = "CZTeam"
    banned_groups: tuple[str, ...] = ()
    announce_url = "https://tracker.czteam.me/announce"
    upload_url = f"{base_url}/takeupload_api.php"
    search_url = f"{base_url}/api.php"
    torrent_url = f"{base_url}/details.php?id="
    tracker_urls = ("czteam.me",)
    supported_categories = ("MOVIE", "TV", "GAME", "MUSIC", "XXX")
    allows_bloated_audio = True

    # Values accepted by the optional upload fields; anything else is left out.
    resolutions = ("480p", "576p", "720p", "1080p", "2160p")
    codecs = ("H.264", "H.265", "x264", "x265", "XviD", "AV1")
    containers = ("MKV", "AVI", "MP4", "TS", "ISO")
    lossless_formats = ("FLAC", "ALAC", "WAV", "AIFF", "DSD")
    # Category ids searched for duplicates of non-video releases.
    search_categories: ClassVar[dict[str, str]] = {"GAME": "12,4,21,31", "MUSIC": "6,35,30"}

    def __init__(self, config: Config) -> None:
        self.config: Config = config
        self.common = Common(config)
        self.tracker_config: dict[str, Any] = cast(dict[str, Any], config.get("TRACKERS", {}).get(self.tracker, {}))
        self.username = str(self.tracker_config.get("username", "")).strip()
        self.passkey = str(self.tracker_config.get("passkey", "")).strip()

    def _headers(self, meta: Meta) -> dict[str, str]:
        return {
            "User-Agent": f"{meta.ua_name} {meta.current_version} ({platform.system()} {platform.release()})",
            "Accept": "application/json",
        }

    @staticmethod
    def _error_message(response: httpx.Response) -> str:
        try:
            body = response.json()
        except ValueError:
            return f"HTTP {response.status_code}: {response.text[:500]}"
        if isinstance(body, dict) and (error := cast(dict[str, Any], body).get("error")):
            return f"HTTP {response.status_code}: {error}"
        return f"HTTP {response.status_code}: {str(body)[:500]}"

    async def has_romanian(self, meta: Meta) -> bool:
        if not meta.language_checked:
            await languages_manager.process_desc_language(meta, tracker=self.tracker)
        subtitle_langs = meta.subtitle_languages if isinstance(meta.subtitle_languages, list) else []
        audio_langs = meta.audio_languages or []
        return any(str(lang).lower() == "romanian" for lang in [*subtitle_langs, *audio_langs])

    def is_video(self, meta: Meta) -> bool:
        return str(meta.category).upper() in ("MOVIE", "TV", "XXX")

    async def get_category_id(self, meta: Meta) -> int:
        category = str(meta.category).upper()
        if category == "XXX":
            return 1  # XxX
        if category == "GAME":
            if meta.console_game:
                return 12  # Games/Consoles
            if str(meta.platform).upper() == "MAC":
                return 31  # MAC
            has_iso = any(str(path).lower().endswith(".iso") for path in meta.filelist)
            return 4 if has_iso else 21  # Games/PC ISO, Games/PC Rips
        if category == "MUSIC":
            return 35 if str(meta.format).upper() in self.lossless_formats else 6  # Music/Lossless, Music/Audio

        if meta.anime:
            return 23  # Anime
        romanian = await self.has_romanian(meta)

        if "documentary" in str(meta.genres).lower() or "documentary" in str(meta.keywords).lower():
            return 25  # Docs

        if category == "TV":
            if meta.sd:
                return 7  # TvEps
            return 34 if romanian else 5  # TvEps/HD-RO, TvEps/HD

        if meta.is_disc == "BDMV":
            return 36  # Full BluRay-RO
        if meta.is_disc == "DVD":
            return 28 if romanian else 20  # Movies/DVD-RO, Movies/DVD-R
        if meta.sd:
            return 19  # Movies/XviD
        if meta.type == "HDTV" and romanian:
            return 33  # Movies/HDTV-RO
        return 38 if romanian else 29  # Movies-RO, Movies/HD

    def get_resolution(self, meta: Meta) -> str:
        return meta.resolution if meta.resolution in self.resolutions else ""

    def get_codec(self, meta: Meta) -> str:
        encode = str(meta.video_encode).strip()
        if encode in self.codecs:
            return encode
        codec = str(meta.video_codec).upper()
        if codec in ("AVC", "H.264"):
            return "H.264"
        if codec in ("HEVC", "H.265"):
            return "H.265"
        if codec == "AV1":
            return "AV1"
        return ""

    def get_container(self, meta: Meta) -> str:
        if meta.is_disc:
            return "ISO" if meta.is_disc == "DVD" else ""
        container = str(meta.container).upper()
        if container == "M2TS":
            return "TS"
        return container if container in self.containers else ""

    def get_source(self, meta: Meta) -> str:
        release_type = str(meta.type or "").upper()
        if meta.is_disc == "BDMV" or (release_type == "REMUX" and "BluRay" in str(meta.source)):
            return "BluRay"
        if meta.is_disc == "DVD":
            return "DVD"
        source_map = {"WEBDL": "WEB-DL", "WEBRIP": "WEBRip", "HDTV": "HDTV"}
        if release_type in source_map:
            return source_map[release_type]
        if release_type == "ENCODE":
            source = str(meta.source)
            if "BluRay" in source or "Blu-ray" in source:
                return "BDRip"
            if "DVD" in source:
                return "DVDRip"
        return ""

    async def get_mediainfo(self, meta: Meta) -> str:
        tmp_dir = Path(meta.base_dir) / "tmp" / meta.uuid
        if meta.is_disc == "BDMV":
            # The site renders this field as MediaInfo tabs, so send MediaInfo for discs too.
            return await self.common.get_bdmv_mediainfo(meta)
        mi_path = tmp_dir / "MEDIAINFO_CLEANPATH.txt"
        if not mi_path.is_file():
            return ""
        async with aiofiles.open(mi_path, encoding="utf-8") as mi_file:
            return await mi_file.read()

    async def generate_description(self, meta: Meta) -> str:
        builder = DescriptionBuilder(self.tracker, self.config)
        signature = f"[right][url=https://github.com/wastaken7/Upload-Assistant]{meta.ua_signature}[/url][/right]"
        description = await builder.general_description_generator(meta, book=False, mediainfo=False, signature=signature)

        # Blu-ray discs carry their BDInfo summary in the description, above the signature.
        bdinfo = await builder.get_bdinfo_section(meta)
        if not bdinfo:
            return description
        bdinfo_block = f"[pre]{bdinfo.strip()}[/pre]"
        head, found, tail = description.rpartition(signature)
        if found:
            return f"{head.rstrip()}\n\n{bdinfo_block}\n\n{signature}{tail}"
        return f"{description.rstrip()}\n\n{bdinfo_block}"

    async def search_existing(self, meta: Meta) -> list[dict[str, Any]]:
        dupes: list[dict[str, Any]] = []
        params: dict[str, Any] = {"action": "search-torrents", "username": self.username, "passkey": self.passkey, "output": "json"}
        category = str(meta.category).upper()
        if meta.imdb_tt and self.is_video(meta):
            params.update({"type": "imdb", "query": meta.imdb_tt})
        elif category == "MUSIC" and meta.music_artist and meta.music_album:
            params.update({"type": "name", "query": f"{meta.music_artist} {meta.music_album}"})
        elif category == "GAME" and meta.game_title:
            params.update({"type": "name", "query": meta.game_title})
        else:
            params.update({"type": "name", "query": meta.title})
        if category in self.search_categories:
            params["category"] = self.search_categories[category]
        if str(meta.category).upper() == "TV" and str(meta.season or "").upper().startswith("S") and str(meta.season)[1:].isdigit():
            params["season"] = int(str(meta.season)[1:])

        async with httpx.AsyncClient(headers=self._headers(meta), timeout=30.0) as client:
            response = await client.get(self.search_url, params=params)
        if response.status_code != 200:
            raise RuntimeError(f"{self.tracker}: duplicate search failed: {self._error_message(response)}")

        try:
            results: Any = response.json()
        except ValueError as e:
            raise RuntimeError(f"{self.tracker}: unexpected search response: {response.text[:200]}") from e
        if isinstance(results, dict):
            results_dict = cast(dict[str, Any], results)
            if results_dict.get("error"):
                raise RuntimeError(f"{self.tracker}: duplicate search failed: {results_dict['error']}")
            results = results_dict.get("torrents") or results_dict.get("results") or []

        for item in cast(list[Any], results):
            if not isinstance(item, dict):
                continue
            torrent = cast(dict[str, Any], item)
            name = torrent.get("name")
            if not name:
                continue
            torrent_id = torrent.get("id")
            dupes.append(
                {
                    "name": str(name),
                    "size": torrent.get("size"),
                    "files": [],
                    "file_count": torrent.get("files"),
                    "link": torrent.get("url") or (f"{self.torrent_url}{torrent_id}" if torrent_id else None),
                    "id": torrent_id,
                }
            )
        return dupes

    async def get_name(self, meta: Meta) -> str:
        if meta.scene_name:
            return meta.scene_name

        return meta.basename_no_ext

    async def get_data(self, meta: Meta, preview: bool = False) -> dict[str, Any]:
        """Build the upload form; a ``preview`` leaves out the description and MediaInfo."""
        data: dict[str, Any] = {
            "name": await self.get_name(meta),
            "category": await self.get_category_id(meta),
            "user_descr": None if preview else await self.generate_description(meta),
        }
        genres = meta.music_genres if str(meta.category).upper() == "MUSIC" else ", ".join(str(genre) for genre in meta.genres)
        optional: dict[str, Any] = {
            "poster": meta.artwork_url if str(meta.artwork_url or "").startswith(("http://", "https://")) else "",
            "tube": meta.youtube or "",
            "genre": genres,
        }
        # MediaInfo, IMDb and the video format fields only apply to video releases.
        if self.is_video(meta):
            optional.update(
                {
                    "descr": "" if preview else await self.get_mediainfo(meta),
                    "imdb_id": meta.imdb_tt,
                    "resolution": self.get_resolution(meta),
                    "codec": self.get_codec(meta),
                    "container": self.get_container(meta),
                    "source": self.get_source(meta),
                }
            )
        data.update({key: value for key, value in optional.items() if value})
        return data

    async def get_payload_preview(self, meta: Meta) -> payload_preview.TrackerPreview:
        """The upload form as it is known before screenshots, for the Web UI to show and edit."""
        specs = {
            "name": payload_preview.text("Name"),
            "category": payload_preview.choice(
                "Category",
                [
                    (1, "XXX"),
                    (4, "Games/PC ISO"),
                    (5, "TvEps/HD"),
                    (6, "Music/Audio"),
                    (7, "TvEps"),
                    (12, "Games/Consoles"),
                    (19, "Movies/XviD"),
                    (20, "Movies/DVD-R"),
                    (21, "Games/PC Rips"),
                    (23, "Anime"),
                    (25, "Docs"),
                    (28, "Movies/DVD-RO"),
                    (29, "Movies/HD"),
                    (31, "MAC"),
                    (33, "Movies/HDTV-RO"),
                    (34, "TvEps/HD-RO"),
                    (35, "Music/Lossless"),
                    (36, "Full BluRay-RO"),
                    (38, "Movies-RO"),
                ],
            ),
            "poster": payload_preview.text("Poster URL", max_length=1000),
            "tube": payload_preview.text("Trailer URL", max_length=1000),
            "genre": payload_preview.text("Genre"),
            "imdb_id": payload_preview.text("IMDb ID"),
            "resolution": payload_preview.choice("Resolution", self.resolutions),
            "codec": payload_preview.choice("Codec", self.codecs),
            "container": payload_preview.choice("Container", self.containers),
            "source": payload_preview.choice("Source", ["BluRay", "DVD", "WEB-DL", "WEBRip", "HDTV", "BDRip", "DVDRip"]),
        }
        deferred = {"user_descr": payload_preview.DESCRIPTION_NOTE}
        if self.is_video(meta):
            deferred["descr"] = "Read from the MediaInfo report at upload time"
        return payload_preview.describe(self.tracker, await self.get_data(meta, preview=True), specs, deferred=deferred)

    async def upload(self, meta: Meta) -> bool:
        tracker_status = meta.tracker_status.setdefault(self.tracker, {})
        data = payload_preview.apply_payload_edits(meta, self.tracker, await self.get_data(meta))

        if meta.debug:
            logger.info(f"{self.tracker}: Request Data:")
            logger.info(Redaction.redact_private_info({**data, "descr": "...[DEBUG MODE]" if data.get("descr") else ""}))
            tracker_status["status_message"] = "Debug mode enabled, not uploading."
            await self.common.create_torrent_for_upload(meta, f"{self.tracker}_DEBUG", f"{self.tracker}_DEBUG", announce_url="https://fake.tracker")
            return True

        # The site replaces the announce with the passkey one and returns the registered torrent.
        await self.common.create_torrent_for_upload(meta, self.tracker, self.source_flag, announce_url=self.announce_url)
        torrent_path = Path(meta.base_dir) / "tmp" / meta.uuid / f"[{self.tracker}].torrent"
        async with aiofiles.open(torrent_path, "rb") as torrent_file:
            files = {"file": (f"{meta.name}.torrent", await torrent_file.read(), "application/x-bittorrent")}

        try:
            async with httpx.AsyncClient(headers=self._headers(meta), timeout=120.0) as client:
                response = await client.post(self.upload_url, data={**data, "passkey": self.passkey}, files=files)
        except httpx.TimeoutException:
            tracker_status["status_message"] = "data error: Request timed out; check the site before retrying."
            return False
        except httpx.RequestError as e:
            tracker_status["status_message"] = f"data error: Unable to upload: {e!r}"
            return False

        try:
            parsed: Any = response.json()
        except ValueError:
            parsed = None
        # Anything other than a JSON object is reported through the error branch below.
        result: dict[str, Any] = cast(dict[str, Any], parsed) if isinstance(parsed, dict) else {}

        if response.status_code == 409:
            existing = result.get("id")
            tracker_status["status_message"] = (
                f"data error: A torrent with this name already exists: {self.torrent_url}{existing}" if existing else "data error: A torrent with this name already exists."
            )
            return False
        if response.status_code not in (200, 201) or not result:
            tracker_status["status_message"] = f"data error: {self._error_message(response)}"
            return False

        torrent_id = str(result.get("id") or "")
        if not torrent_id:
            tracker_status["status_message"] = f"data error: No torrent id in response, check the site manually: {Redaction.redact_private_info(result)}"
            return False
        tracker_status["torrent_id"] = torrent_id
        details_url = f"{self.torrent_url}{torrent_id}"

        torrent_b64 = result.get("torrent_b64")
        if not torrent_b64:
            tracker_status["status_message"] = f"data error: Uploaded, but the registered .torrent was not returned. Download it from {details_url}"
            return False
        try:
            torrent_bytes = base64.b64decode(str(torrent_b64), validate=True)
        except ValueError:
            tracker_status["status_message"] = f"data error: Uploaded, but the registered .torrent could not be decoded. Download it from {details_url}"
            return False
        async with aiofiles.open(torrent_path, "wb") as torrent_file:
            await torrent_file.write(torrent_bytes)

        # The upload stays hidden on the site until a seeder connects.
        tracker_status["status_message"] = "Uploaded; visible after seeding starts."
        return True
