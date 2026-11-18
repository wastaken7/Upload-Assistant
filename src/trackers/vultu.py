# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import platform
import re
from pathlib import Path
from typing import Any, cast

import aiofiles
import httpx

from src import payload_preview
from src.cogs.redaction import Redaction
from src.console import logger
from src.get_desc import DescriptionBuilder
from src.meta import Meta
from src.music.validation import lame_preset
from src.tracker_images import get_tracker_image_collection
from src.trackers.common import Common
from src.trackers.UNIT3D.capybarabr import CapybaraBR

Config = dict[str, Any]


class Vultu:
    """
    Vultu is a Brazilian Private Torrent Tracker for MOVIES / TV / ANIME / GAMES / MUSIC
    """

    base_url = "https://vultu.org"
    api_url = f"{base_url}/api/v1"

    auth_type = "other_api"
    tracker = "VULTU"
    display_name = "vultu"
    source_flag = "vultu"
    banned_groups: tuple[str, ...] = ()
    banned_url = f"{api_url}/banned-groups"
    banned_groups_response_key = "groups"
    upload_url = f"{api_url}/torrents"
    torrent_url = f"{base_url}/torrents/"
    requests_url = f"{base_url}/pedidos"
    tracker_urls = ("vultu.org",)
    supported_categories = ("MOVIE", "TV", "GAME", "MUSIC")
    allows_bloated_audio = True

    min_screenshots = 3
    max_screenshots = 6
    max_name_length = 255
    max_nfo_size = 64 * 1024
    # BBCode notes are converted to Markdown by the site; the raw text may be this long.
    max_bbcode_notes_length = 131072
    max_duplicate_pages = 5

    def __init__(self, config: Config) -> None:
        self.config: Config = config
        self.common = Common(config)
        self.tracker_config: dict[str, Any] = cast(dict[str, Any], config.get("TRACKERS", {}).get(self.tracker, {}))
        self.api_key = str(self.tracker_config.get("api_key", "")).strip()

    def _headers(self, meta: Meta, accept: str = "application/json") -> dict[str, str]:
        return {
            "User-Agent": f"{meta.ua_name} {meta.current_version} ({platform.system()} {platform.release()})",
            "Authorization": f"Bearer {self.api_key}",
            "Accept": accept,
        }

    @staticmethod
    def _error_message(response: httpx.Response) -> str:
        """Format Vultu's RFC 9457 problem responses for the user."""
        try:
            problem = cast(dict[str, Any], response.json())
        except ValueError:
            return f"HTTP {response.status_code}: {response.text[:500]}"
        detail = str(problem.get("detail") or problem.get("title") or response.reason_phrase)
        code = str(problem.get("code") or "")
        message = f"HTTP {response.status_code}: {detail}{f' ({code})' if code else ''}"
        if response.status_code == 429 and (retry_after := response.headers.get("Retry-After")):
            message += f" Retry after {retry_after}s."
        return message

    @staticmethod
    def _tmdb_kind(meta: Meta) -> str:
        return "tv" if str(meta.category).upper() == "TV" else "movie"

    @staticmethod
    def _music_release(meta: Meta) -> dict[str, Any]:
        return cast(dict[str, Any], meta.music_release) if isinstance(meta.music_release, dict) else {}

    @classmethod
    def _music_work(cls, meta: Meta) -> str:
        """Return the album as MusicBrainz release group, MusicBrainz release, Discogs master or Discogs release."""
        external_ids_raw = cls._music_release(meta).get("external_ids")
        external_ids = cast(dict[str, Any], external_ids_raw) if isinstance(external_ids_raw, dict) else {}
        mbid = re.compile(r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}", re.IGNORECASE)
        group = str(external_ids.get("musicbrainz_release_group") or "").strip()
        if mbid.fullmatch(group):
            return f"musicbrainz:release-group:{group.lower()}"
        release = str(external_ids.get("musicbrainz_release") or "").strip()
        if mbid.fullmatch(release):
            return f"musicbrainz:release:{release.lower()}"
        if meta.music_discogs_enabled:
            master = str(external_ids.get("discogs_master") or meta.music_discogs_master_id or "").strip()
            if master.isdecimal():
                return f"discogs:master:{master}"
            discogs_release = str(external_ids.get("discogs_release") or meta.music_discogs_release_id or meta.music_discogs_id or "").strip()
            if discogs_release.isdecimal():
                return f"discogs:release:{discogs_release}"
        return ""

    async def get_work(self, meta: Meta) -> str:
        """Return Vultu's work identifier (tmdb:movie:ID, tmdb:tv:ID, igdb:ID or a MusicBrainz/Discogs album)."""
        category = str(meta.category).upper()
        if category == "GAME":
            return f"igdb:{meta.igdb_id}" if meta.igdb_id else ""
        if category == "MUSIC":
            return self._music_work(meta)

        tmdb_id = meta.tmdb or meta.tmdb_id
        if tmdb_id:
            return f"tmdb:{self._tmdb_kind(meta)}:{tmdb_id}"

        # Vultu does not accept IMDb as a work, but translates it through the works search.
        if not meta.imdb_tt:
            return ""
        kind = self._tmdb_kind(meta)
        async with httpx.AsyncClient(headers=self._headers(meta), timeout=30.0) as client:
            response = await client.get(f"{self.api_url}/works", params={"imdb": meta.imdb_tt, "kind": kind})
        if response.status_code != 200:
            raise RuntimeError(f"{self.tracker}: work lookup failed: {self._error_message(response)}")
        results = cast(list[dict[str, Any]], cast(dict[str, Any], response.json()).get("results") or [])
        return next((str(result["work"]) for result in results if result.get("kind") == kind and result.get("work")), "")

    @staticmethod
    def _season_number(meta: Meta) -> int | None:
        """Return the single season of a TV release, or None for multi-season packs."""
        if str(meta.category).upper() != "TV":
            return None
        match = re.fullmatch(r"S(\d+)", str(meta.season or "").strip(), re.IGNORECASE)
        return int(match.group(1)) if match else None

    @classmethod
    def _music_encoding(cls, meta: Meta) -> str:
        """Return the lossy encoding (V0, 320...) that Vultu's music names carry after the format."""
        raw_tracks = cls._music_release(meta).get("tracks")
        tracks = [cast(dict[str, Any], track) for track in cast(list[Any], raw_tracks) if isinstance(track, dict)] if isinstance(raw_tracks, list) else []
        if not tracks:
            return ""
        presets = {lame_preset(str(track.get("encoder_settings") or "")) for track in tracks}
        if len(presets) == 1 and (preset := next(iter(presets))):
            # "V0 (VBR)" is written as "V0" in the release name.
            return preset.split()[0]
        if all(track.get("bitrate_mode") in {"CBR", "ABR"} for track in tracks):
            average = round(sum(int(track.get("bitrate") or 0) for track in tracks) / len(tracks) / 1000)
            return str(average) if average else ""
        return ""

    def _music_name(self, meta: Meta) -> str:
        """Artist - Album Year Media Format Encoding-GROUP; lossless keeps the bit depth and rate already in the name."""
        name = str(meta.name or "").strip()
        tag = str(meta.tag or "").strip()
        if not tag or not name.endswith(tag):
            tag = ""
        base = name[: len(name) - len(tag)].rstrip()
        words = base.split()
        # Lossless names end with the sample rate ("44.1 kHz"); only lossy names end with the codec.
        if not words or words[-1].upper() in {"FLAC", "ALAC", "KHZ"} or not (encoding := self._music_encoding(meta)):
            return name
        return f"{base} {encoding}{tag}"

    async def get_name(self, meta: Meta) -> str:
        if str(meta.category).upper() == "MUSIC":
            return (meta.manual_name or self._music_name(meta)).strip()
        # Vultu follows the same naming as CapybaraBR.
        cbr = CapybaraBR(self.config)
        cbr.tracker = self.tracker
        return (await cbr.get_name(meta))["name"].strip()

    def _screenshot_urls(self, meta: Meta) -> list[str]:
        # In Music the screenshots field holds the track spectrograms.
        images = get_tracker_image_collection(meta, self.tracker, "spectrograms_images" if str(meta.category).upper() == "MUSIC" else "screenshots")
        urls: list[str] = []
        for image in images:
            raw_url = image.get("raw_url")
            if isinstance(raw_url, str) and raw_url.startswith("https://") and raw_url not in urls:
                urls.append(raw_url)
        return urls[: self.max_screenshots]

    async def get_mediainfo(self, meta: Meta) -> str:
        # Vultu discards MediaInfo for games and music.
        if str(meta.category).upper() in ("GAME", "MUSIC"):
            return ""
        tmp_dir = Path(meta.base_dir) / "tmp" / meta.uuid
        if meta.is_disc == "BDMV":
            # Vultu accepts BDInfo in the same field as MediaInfo.
            bd_summary_path = tmp_dir / "BD_SUMMARY_00.txt"
            if not bd_summary_path.is_file():
                return await self.common.get_bdmv_mediainfo(meta)
            async with aiofiles.open(bd_summary_path, encoding="utf-8") as bd_file:
                return await bd_file.read()
        mi_path = tmp_dir / "MEDIAINFO_CLEANPATH.txt"
        if not mi_path.is_file():
            return ""
        async with aiofiles.open(mi_path, encoding="utf-8") as mi_file:
            return await mi_file.read()

    async def get_notes(self, meta: Meta) -> str:
        """Build the release notes in BBCode; Vultu converts them to its Markdown (notes_format=bbcode).

        The site drops images and videos from the notes, and MediaInfo, NFO, screenshots and music
        spectrograms have their own fields, so those sections are left out.
        """
        builder = DescriptionBuilder(self.tracker, self.config)
        notes = await builder.general_description_generator(
            meta,
            audio_spectrogram=False,
            logo=False,
            mediainfo=False,
            menu_screenshots=False,
            nfo=False,
            screenshots=False,
            tonemapped_header=False,
        )
        notes = notes.strip()
        if len(notes) > self.max_bbcode_notes_length:
            logger.warning(f"{self.tracker}: [yellow]Release notes are longer than {self.max_bbcode_notes_length} characters and will not be sent.[/yellow]")
            return ""
        return notes

    async def get_nfo(self, meta: Meta) -> tuple[str, bytes, str] | None:
        nfo_files = sorted((Path(meta.base_dir) / "tmp" / meta.uuid).glob("*.nfo"))
        if not nfo_files and meta.keep_nfo and (meta.keep_folder or meta.isdir) and meta.path:
            nfo_files = sorted(Path(str(meta.path)).parent.glob("*.nfo"))
        if not nfo_files:
            return None
        if nfo_files[0].stat().st_size > self.max_nfo_size:
            logger.warning(f"{self.tracker}: [yellow]NFO is larger than 64 KB and will not be sent.[/yellow]")
            return None
        async with aiofiles.open(nfo_files[0], "rb") as nfo_file:
            return (nfo_files[0].name, await nfo_file.read(), "text/plain")

    async def get_additional_checks(self, meta: Meta) -> bool:
        """Enforce Vultu's upload rules that can be checked before uploading."""
        category = str(meta.category).upper()

        if category == "GAME" and not meta.igdb_id:
            logger.warning(f"{self.tracker}: [red]Games must be linked to an IGDB entry.[/red]")
            return False

        if category == "MUSIC" and not self._music_work(meta):
            logger.warning(f"{self.tracker}: [red]Music must be linked to a MusicBrainz or Discogs album.[/red]")
            return False

        if category in ("MOVIE", "TV"):
            if not (meta.tmdb or meta.tmdb_id or meta.imdb_tt):
                logger.warning(f"{self.tracker}: [red]Movies and TV must be linked to a TMDB (or IMDb) entry.[/red]")
                return False
            if int(meta.screens or 0) < self.min_screenshots:
                logger.warning(f"{self.tracker}: [red]Movies, TV and anime require at least {self.min_screenshots} screenshots (configured {meta.screens}).[/red]")
                return False

        if len(await self.get_name(meta)) > self.max_name_length:
            logger.warning(f"{self.tracker}: [red]Release name is longer than {self.max_name_length} characters.[/red]")
            return False

        return True

    async def search_existing(self, meta: Meta) -> list[dict[str, Any]]:
        """Search Vultu's duplicates endpoint, including releases pending moderation."""
        dupes: list[dict[str, Any]] = []
        work = await self.get_work(meta)
        params: dict[str, Any] = {"work": work} if work else {"name": meta.title}
        if work and (season := self._season_number(meta)) is not None:
            params["season"] = season

        async with httpx.AsyncClient(headers=self._headers(meta), timeout=30.0) as client:
            for _ in range(self.max_duplicate_pages):
                response = await client.get(f"{self.api_url}/duplicates", params=params)
                if response.status_code != 200:
                    raise RuntimeError(f"{self.tracker}: duplicate search failed: {self._error_message(response)}")
                data = cast(dict[str, Any], response.json())
                for release in cast(list[dict[str, Any]], data.get("releases") or []):
                    name = release.get("name")
                    if not name:
                        continue
                    files = [str(file.get("path")) for file in cast(list[dict[str, Any]], release.get("files") or []) if file.get("path")]
                    dupes.append(
                        {
                            "name": str(name),
                            "size": release.get("size"),
                            "files": files,
                            "file_count": len(files),
                            "link": release.get("url"),
                            "id": release.get("id"),
                        }
                    )
                next_page = data.get("next")
                if next_page is None:
                    break
                params["before"] = next_page

        return dupes

    async def get_requests(self, meta: Meta) -> list[dict[str, str]]:
        """Show the open requests for this work; filling them is left to the user on the site."""
        if not self.config["DEFAULT"].get("search_requests", False) and not meta.search_requests:
            return []
        try:
            work = await self.get_work(meta)
            if not work:
                return []
            async with httpx.AsyncClient(headers=self._headers(meta), timeout=30.0) as client:
                response = await client.get(f"{self.api_url}/requests", params={"status": "open", "work": work})
        except (httpx.HTTPError, RuntimeError) as e:
            logger.info(f"{self.tracker}: Unable to search requests: {e}", extra={"markup": False})
            return []
        if response.status_code != 200:
            logger.info(f"{self.tracker}: Unable to search requests: {self._error_message(response)}", extra={"markup": False})
            return []

        season = self._season_number(meta)
        results: list[dict[str, str]] = []
        for item in cast(list[dict[str, Any]], cast(dict[str, Any], response.json()).get("requests") or []):
            # A request is for one season at a time; a different season cannot be filled by this upload.
            if season is not None and item.get("season") is not None and item.get("season") != season:
                continue
            results.append(
                {"Name": str(item.get("title") or ""), "Reward": str(item.get("bounty") or ""), "Link": str(item.get("url") or f"{self.requests_url}/{item.get('id')}")}
            )

        if results:
            message = f"\n{self.tracker}: [bold yellow]Seu upload pode atender o(s) seguinte(s) pedido(s), confira:[/bold yellow]\n\n"
            for result in results:
                message += f"[bold green]Nome:[/bold green] {result['Name']}\n[bold green]Recompensa:[/bold green] {result['Reward']}\n[bold green]Link:[/bold green] {result['Link']}\n\n"
            logger.info(message)
        return results

    async def get_data(self, meta: Meta, work: str, preview: bool = False) -> dict[str, Any]:
        """Build the upload form; a ``preview`` leaves out the screenshots, MediaInfo and release notes."""
        anon = bool(meta.anon) or bool(self.tracker_config.get("anon", False))
        data: dict[str, Any] = {
            "work": work,
            "name": await self.get_name(meta),
            "anime": "true" if meta.anime and work.startswith("tmdb:") else "false",
            "anonymous": "true" if anon else "false",
        }
        if preview:
            return data
        if screenshots := self._screenshot_urls(meta):
            data["screenshots"] = screenshots
            if str(meta.category).upper() != "MUSIC":
                # Shown on the site only when the MediaInfo says the video is HDR.
                data["tonemapped"] = "true" if meta.tonemapped else "false"
        if mediainfo := await self.get_mediainfo(meta):
            data["mediainfo"] = mediainfo
        if notes := await self.get_notes(meta):
            data["notes"] = notes
            data["notes_format"] = "bbcode"
        return data

    async def get_payload_preview(self, meta: Meta) -> payload_preview.TrackerPreview:
        """The upload form as it is known before screenshots, for the Web UI to show and edit."""
        deferred = {
            "screenshots": "Uploaded after this question",
            "mediainfo": "Read from the MediaInfo report at upload time",
            "notes": payload_preview.DESCRIPTION_NOTE,
        }
        # Without a TMDB or IGDB ID the work is looked up on Vultu, which only happens at upload time.
        if str(meta.category).upper() in ("GAME", "MUSIC") or meta.tmdb or meta.tmdb_id:
            work = await self.get_work(meta)
        else:
            work = ""
            deferred = {"work": payload_preview.FROM_TRACKER_NOTE, **deferred}
        specs = {
            "work": payload_preview.text("Work"),
            "name": payload_preview.text("Name"),
            "anime": payload_preview.flag("Anime", on="true", off="false"),
            "anonymous": payload_preview.flag("Anonymous", on="true", off="false"),
        }
        data = await self.get_data(meta, work, preview=True)
        return payload_preview.describe(self.tracker, data, specs, deferred=deferred)

    async def upload(self, meta: Meta) -> bool:
        tracker_status = meta.tracker_status.setdefault(self.tracker, {})

        work = await self.get_work(meta)
        if not work:
            tracker_status["status_message"] = "data error: Could not determine the TMDB/IGDB/MusicBrainz/Discogs work required by Vultu."
            return False

        data = payload_preview.apply_payload_edits(meta, self.tracker, await self.get_data(meta, work))
        screenshot_count = len(data.get("screenshots", []))
        if str(meta.category).upper() in ("MOVIE", "TV") and screenshot_count < self.min_screenshots:
            tracker_status["status_message"] = f"data error: Vultu requires at least {self.min_screenshots} https screenshot URLs, found {screenshot_count}."
            return False

        if meta.debug:
            logger.info(f"{self.tracker}: Request Data:")
            logger.info(Redaction.redact_private_info({**data, "mediainfo": "...[DEBUG MODE]" if data.get("mediainfo") else ""}))
            tracker_status["status_message"] = "Debug mode enabled, not uploading."
            await self.common.create_torrent_for_upload(meta, f"{self.tracker}_DEBUG", f"{self.tracker}_DEBUG", announce_url="https://fake.tracker")
            return True

        # The announce is replaced by the passkey one when the registered torrent is downloaded below.
        await self.common.create_torrent_for_upload(meta, self.tracker, self.source_flag, announce_url=f"{self.base_url}/announce")
        torrent_path = Path(meta.base_dir) / "tmp" / meta.uuid / f"[{self.tracker}].torrent"
        async with aiofiles.open(torrent_path, "rb") as torrent_file:
            files: dict[str, tuple[str, bytes, str]] = {"torrent": (f"{data['name']}.torrent", await torrent_file.read(), "application/x-bittorrent")}
        if nfo := await self.get_nfo(meta):
            files["nfo"] = nfo

        try:
            async with httpx.AsyncClient(headers=self._headers(meta), timeout=120.0) as client:
                response = await client.post(self.upload_url, data=data, files=files)
        except httpx.TimeoutException:
            tracker_status["status_message"] = "data error: Request timed out; check the site before retrying (a repeated upload is safe)."
            return False
        except httpx.RequestError as e:
            tracker_status["status_message"] = f"data error: Unable to upload: {e!r}"
            return False

        if response.status_code not in (200, 201):
            tracker_status["status_message"] = f"data error: {self._error_message(response)}"
            return False

        try:
            result = cast(dict[str, Any], response.json())
        except ValueError:
            tracker_status["status_message"] = f"data error: Unexpected response, check the site manually: {response.text[:500]}"
            return False

        torrent_id = str(result.get("id") or "")
        if not torrent_id:
            tracker_status["status_message"] = f"data error: No torrent id in response, check the site manually: {result}"
            return False
        tracker_status["torrent_id"] = torrent_id
        details_url = str(result.get("url") or f"{self.torrent_url}{torrent_id}")
        pending = bool(result.get("pending"))
        tracker_status["status_message"] = "Uploaded; pending moderation." if pending else "Uploaded."

        download_url = str(result.get("downloadUrl") or f"{self.api_url}/torrents/{torrent_id}/download")
        if not await self.common.download_tracker_torrent(meta, self.tracker, headers=self._headers(meta, accept="*/*"), downurl=download_url):
            tracker_status["status_message"] = f"data error: Uploaded, but the registered .torrent could not be downloaded. Download it from {details_url}"
            return False
        return True
