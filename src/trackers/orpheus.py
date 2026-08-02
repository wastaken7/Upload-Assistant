from __future__ import annotations

import json
import platform
import re
from pathlib import Path
from typing import Any, ClassVar, cast
from urllib.parse import urlparse

import httpx
from rich.markup import escape

from src.console import logger
from src.meta import Meta
from src.music.models import MusicRelease
from src.music.validation import OrpheusMusicValidator, ValidationLevel
from src.trackers.common import Common


class Orpheus:
    """Orpheus is a Private Torrent Tracker for MUSIC"""

    tracker = "ORPHEUS"
    display_name = "Orpheus"
    auth_type = "other_api"
    supported_categories = ("MUSIC",)
    source_flag = "OPS"
    base_url = "https://orpheus.network"
    release_types: ClassVar[dict[str, int]] = {
        "Album": 1,
        "Soundtrack": 3,
        "EP": 5,
        "Anthology": 6,
        "Compilation": 7,
        "Sampler": 8,
        "Single": 9,
        "Demo": 10,
        "Live album": 11,
        "Split": 12,
        "Remix": 13,
        "Bootleg": 14,
        "Interview": 15,
        "Mixtape": 16,
        "DJ Mix": 17,
        "Concert recording": 18,
        "Concert Recording": 18,
        "Unknown": 21,
    }
    banned_groups = ()
    blocked_music_artists: ClassVar[dict[str, str]] = {
        "vap0rwave": "Vap0rwave",
        "pauldvr": "Paul_DVR",
        "firmensprecher": "Firmensprecher",
        "stretches": "stretches",
        "phyllomedusa": "Phyllomedusa",
    }
    blocked_music_releases: ClassVar[tuple[tuple[str, str], ...]] = (
        ("Bruce Springsteen", "Odds and Sods"),
        ("Dr. Dre", "Detox"),
        ("Green Day", "Cigarettes and Valentines"),
        ("Jean-Michel Jarre", "Music for Supermarkets"),
        ("Michael Jackson", "Super Mix"),
        ("Pink Floyd", "Tree Full of Secrets"),
        ("The Beatles", "Carnival of Light"),
        ("The Upholsterers", "Your Furniture Was Always Dead… I Was Just Afraid To Tell You"),
        ("Various Artists", "The Ultimate 500 CD Jazz Collection"),
        ("Wu-Tang Clan", "Once Upon a Time in Shaolin"),
    )
    blocked_music_labels: ClassVar[tuple[str, ...]] = (
        "Sandero Classic Sound",
        "Sip It & Trip It Records",
    )
    comment_hosts = ("orpheus.network", "home.opsfet.ch")
    tracker_urls = ("home.opsfet.ch",)

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        settings = config.get("TRACKERS", {}).get(self.tracker, {})
        self.api_key = str(settings.get("api_key", "")).strip()
        self.announce_url = str(settings.get("announce_url", "")).strip()
        self.requests_url = f"{self.base_url}/requests.php"
        self.torrent_url = f"{self.base_url}/torrents.php?torrentid="
        self.common = Common(config)

    def _headers(self, meta: Meta) -> dict[str, str]:
        product = str(meta.ua_name or "Upload Assistant").strip() or "Upload Assistant"
        version = str(meta.current_version or "").strip()
        user_agent = f"{product}{f' {version}' if version else ''} ({platform.system()} {platform.release()})"
        return {"Authorization": f"token {self.api_key}", "User-Agent": user_agent}

    @staticmethod
    def _release(meta: Meta) -> MusicRelease:
        if not isinstance(meta.music_release, dict):
            raise ValueError("MUSIC analysis is missing; run preparation before using Orpheus.")
        return MusicRelease.from_dict(meta.music_release)

    @staticmethod
    def _normalise_artist_name(value: Any) -> str:
        """Compare artist names independently of case, spaces and underscores."""
        return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())

    @classmethod
    def _blocked_artists(cls, release: MusicRelease) -> list[str]:
        values = cls._artists(release)
        # A manually supplied credit can contain collaborators in a single
        # value.  Split common credit separators while retaining exact-name
        # matching so an unrelated longer artist name is never blocked.
        candidates: list[str] = []
        for value in values:
            candidates.extend(part.strip() for part in re.split(r"\s*(?:,|&|;|\bfeat(?:uring)?\.?\b|\bwith\b)\s*", value, flags=re.I) if part.strip())
        blocked: list[str] = []
        for candidate in candidates:
            name = cls.blocked_music_artists.get(cls._normalise_artist_name(candidate))
            if name and name not in blocked:
                blocked.append(name)
        return blocked

    @classmethod
    def _blocked_releases(cls, release: MusicRelease) -> list[str]:
        artists = {cls._normalise_artist_name(value) for value in cls._artists(release)}
        title = cls._normalise_artist_name(release.get("album", ""))
        matches: list[str] = []
        for artist, album in cls.blocked_music_releases:
            if cls._normalise_artist_name(artist) in artists and cls._normalise_artist_name(album) == title:
                matches.append(f"{artist} - {album}")
        return matches

    @classmethod
    def _blocked_labels(cls, release: MusicRelease) -> list[str]:
        labels = {cls._normalise_artist_name(value) for value in (release.get("release_label", ""), release.get("label", "")) if str(value or "").strip()}
        return [label for label in cls.blocked_music_labels if cls._normalise_artist_name(label) in labels]

    async def get_additional_checks(self, meta: Meta) -> bool:
        """Prevent uploads of artists explicitly prohibited by Orpheus."""
        release = self._release(meta)
        blocked_artists = self._blocked_artists(release)
        blocked_releases = self._blocked_releases(release)
        blocked_labels = self._blocked_labels(release)
        if not (blocked_artists or blocked_releases or blocked_labels):
            return True
        reasons = [
            *(f"artist {artist}" for artist in blocked_artists),
            *(f"blacklisted release {release_name}" for release_name in blocked_releases),
            *(f"blacklisted label {label}" for label in blocked_labels),
        ]
        message = f"Upload blocked: Orpheus blacklist matched {', '.join(reasons)}."
        status = meta.tracker_status.setdefault(self.tracker, {})
        status["status_message"] = message
        status["blocked_reasons"] = reasons
        logger.error(f"{self.tracker}: [red]{message}[/red]")
        return False

    async def search_existing(self, meta: Meta) -> list[dict[str, Any]]:
        """Perform one narrow, read-only Gazelle browse query for duplicate review."""
        release = self._release(meta)
        artist, album = str(release.get("artist", "")), str(release.get("album", ""))
        if not artist or not album or not self.api_key:
            return []
        params = {"action": "browse", "artistname": artist, "groupname": album}
        payload: dict[str, Any] = {}
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(8.0), headers=self._headers(meta)) as client:
                response = await client.get(f"{self.base_url}/ajax.php", params=params)
                response.raise_for_status()
                raw_json = response.json()
        except (httpx.HTTPError, ValueError) as error:
            logger.warning(f"{self.tracker}: [yellow]read-only duplicate search failed: {error}[/yellow]")
            return []
        if not isinstance(raw_json, dict):
            return []
        payload = cast(dict[str, Any], raw_json)
        if payload.get("status") != "success":
            return []
        response_data = payload.get("response")
        if not isinstance(response_data, dict):
            return []
        response_data_dict = cast(dict[str, Any], response_data)
        results = response_data_dict.get("results")
        if not isinstance(results, list):
            return []
        results_list = cast(list[Any], results)
        dupes: list[dict[str, Any]] = []
        for group_item in results_list:
            if not isinstance(group_item, dict):
                continue
            group = cast(dict[str, Any], group_item)
            group_id = group.get("groupId")
            editions = group.get("torrents")
            if not isinstance(editions, list):
                continue
            editions_list = cast(list[Any], editions)
            encodings = [
                f"{cast(dict[str, Any], torrent).get('media', '')} {cast(dict[str, Any], torrent).get('format', '')} {cast(dict[str, Any], torrent).get('encoding', '')}".strip()
                for torrent in editions_list
                if isinstance(torrent, dict)
            ]
            dupes.append(
                {
                    "name": f"{group.get('artist', '')} - {group.get('groupName', '')}".strip(" -"),
                    "size": group.get("maxSize"),
                    "id": group_id,
                    "link": f"{self.base_url}/torrents.php?id={group_id}" if group_id else None,
                    "flags": encodings,
                    "type": group.get("releaseType"),
                }
            )
        return dupes

    async def get_torrent(self, torrent_id: int | str, meta: Meta) -> dict[str, Any] | None:
        """Return one Orpheus torrent's Gazelle metadata using a read-only API call.

        This is deliberately separate from upload and is useful for local
        release audits when a torrent comment already supplies an exact ID.
        """
        identifier = str(torrent_id).strip()
        if not identifier.isdigit() or not self.api_key:
            return None
        payload: dict[str, Any] = {}
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(15.0), headers=self._headers(meta)) as client:
                response = await client.get(f"{self.base_url}/ajax.php", params={"action": "torrent", "id": identifier})
                response.raise_for_status()
                raw_json = response.json()
        except (httpx.HTTPError, ValueError) as error:
            logger.warning(f"{self.tracker}: [yellow]read-only torrent lookup failed for {identifier}: {error}[/yellow]")
            return None
        if not isinstance(raw_json, dict):
            return None
        payload = cast(dict[str, Any], raw_json)
        response_data = payload.get("response")
        if payload.get("status") == "success" and isinstance(response_data, dict):
            return cast(dict[str, Any], response_data)
        return None

    async def get_requests(self, meta: Meta) -> list[dict[str, Any]]:
        """Search open MUSIC requests with one bounded, read-only API call.

        The API's requested format/media fields use legacy naming, so matching
        is deliberately conservative: title, credited artists and initial year
        determine the match level; source/format requirements are displayed for
        human review and never cause an automatic request fill.
        """
        if meta.category != "MUSIC" or not self.api_key:
            return []
        release = self._release(meta)
        album = str(release.get("album", "")).strip()
        if not album:
            return []
        params = {
            "action": "requests",
            "search": album,
            "show_filled": "false",
            "filter_cat[]": "1",
        }
        payload: dict[str, Any] = {}
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(10.0), headers=self._headers(meta)) as client:
                response = await client.get(f"{self.base_url}/ajax.php", params=params)
                response.raise_for_status()
                raw_json = response.json()
        except (httpx.HTTPError, ValueError) as error:
            logger.warning(f"{self.tracker}: [yellow]read-only request search failed: {error}[/yellow]")
            return []
        if not isinstance(raw_json, dict):
            return []
        payload = cast(dict[str, Any], raw_json)
        if payload.get("status") != "success":
            return []
        response_data = payload.get("response")
        if not isinstance(response_data, dict):
            return []
        response_data_dict = cast(dict[str, Any], response_data)
        records = response_data_dict.get("results")
        if not isinstance(records, list):
            return []
        records_list = cast(list[Any], records)

        matches: list[dict[str, Any]] = []
        for record_item in records_list:
            if not isinstance(record_item, dict):
                continue
            record = cast(dict[str, Any], record_item)
            if record.get("isFilled"):
                continue
            match_type = self._request_match_type(release, record)
            if match_type is None:
                continue
            request_id = record.get("requestId")
            if not isinstance(request_id, int | str):
                continue
            artists = self._request_artists(record)
            title = str(record.get("title", "")).strip()
            matches.append(
                {
                    "id": str(request_id),
                    "name": f"{' & '.join(artists)} - {title}".strip(" -"),
                    "bounty": record.get("bounty", 0),
                    "description": str(record.get("description", "")),
                    "match_type": match_type,
                    "requirements": {
                        "release_type": record.get("releaseType", ""),
                        "bitrate": record.get("bitrateList", ""),
                        "format": record.get("formatList", ""),
                        "media": record.get("mediaList", ""),
                        "log_cue": record.get("logCue", ""),
                    },
                    "url": f"{self.base_url}/requests.php?action=view&id={request_id}",
                    "year": record.get("year", ""),
                }
            )

        if matches:
            logger.info(f"{self.tracker}: [bold yellow]matching open music request(s) found; review requirements before filling:[/bold yellow]")
            for match in matches:
                logger.info(
                    f"{self.tracker}: [bold green]{match['match_type'].title()} match:[/bold green] {escape(str(match['name']))} — bounty: {escape(str(match['bounty']))}"
                )
                logger.info(f"{self.tracker}: [cyan]{match['url']}[/cyan]")
                logger.info(f"{self.tracker}: [yellow]Requested technical fields: {match['requirements']}[/yellow]")
        meta.tracker_status.setdefault(self.tracker, {})["request_matches"] = matches
        return matches

    @staticmethod
    def _normalise_request_text(value: Any) -> str:
        return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())

    @classmethod
    def _request_artists(cls, record: dict[str, Any]) -> list[str]:
        artists: list[str] = []
        role_list = cast(list[Any], record.get("artists") or [])
        for role in role_list:
            if not isinstance(role, list):
                continue
            role_items = cast(list[Any], role)
            for artist_item in role_items:
                if isinstance(artist_item, dict):
                    artist = cast(dict[str, Any], artist_item)
                    name = str(artist.get("name", "")).strip()
                    if name and name not in artists:
                        artists.append(name)
        return artists

    @classmethod
    def _request_match_type(cls, release: MusicRelease, record: dict[str, Any]) -> str | None:
        if cls._normalise_request_text(record.get("title")) != cls._normalise_request_text(release.get("album")):
            return None
        release_artists = {cls._normalise_request_text(item) for item in cls._artists(release)}
        request_artists = {cls._normalise_request_text(item) for item in cls._request_artists(record)}
        artist_match = bool(release_artists & request_artists) if request_artists else False
        request_year = str(record.get("year", "")).strip()
        release_year = str(release.get("year", "")).strip()
        year_match = bool(request_year and release_year and request_year == release_year)
        return "exact" if artist_match and year_match else "partial"

    async def get_name(self, meta: Meta) -> str:
        """For the terminal display only, not for upload."""
        release = self._release(meta)
        return f"{release.get('artist', '')} - {release.get('album', '')} [{release.get('year', '')!s}]".strip(" -")

    async def upload(self, meta: Meta) -> bool:
        release = self._release(meta)
        if not await self.get_additional_checks(meta):
            return False
        issues = OrpheusMusicValidator().validate(release)
        errors = [issue.message for issue in issues if issue.level == ValidationLevel.ERROR]
        if errors:
            meta.tracker_status.setdefault(self.tracker, {})["status_message"] = "Validation failed: " + " | ".join(errors)
            return False
        # Keep debug semantics consistent with the other tracker adapters: do
        # not create a tracker torrent and never make a state-changing request.
        # Duplicate searching remains read-only and is performed earlier in the
        # normal tracker-status flow.
        if meta.debug:
            data = self.build_upload_payload(meta, release)
            debug_payload: dict[str, Any] = {
                **data,
                "file_input": "<not-created in debug mode>",
                "logfiles[]": list(release.auxiliary.logs),
            }
            status = meta.tracker_status.setdefault(self.tracker, {})
            status["status_message"] = "Debug mode: upload skipped; payload prepared locally. Artwork is optional on Orpheus."
            status["debug_payload_fields"] = sorted(data)
            status["debug_payload"] = debug_payload
            logger.info(f"{self.tracker}: [yellow]debug mode enabled; POST upload skipped. Prepared payload:[/yellow]")
            logger.info(json.dumps(debug_payload, ensure_ascii=False, indent=2), extra={"markup": False})
            return True
        if not self.api_key or not self.announce_url:
            meta.tracker_status.setdefault(self.tracker, {})["status_message"] = "Missing Orpheus API key or announce URL."
            return False
        await self.common.create_torrent_for_upload(meta, self.tracker, self.source_flag, announce_url=self.announce_url)
        torrent_path = Path(meta.base_dir) / "tmp" / str(meta.uuid) / f"[{self.tracker}].torrent"
        if not torrent_path.is_file():
            meta.tracker_status.setdefault(self.tracker, {})["status_message"] = "Tracker torrent was not created."
            return False
        data = self.build_upload_payload(meta, release)
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(60.0), headers=self._headers(meta)) as client:
                with torrent_path.open("rb") as torrent_file:
                    files: list[tuple[str, tuple[str, Any, str]]] = [("file_input", (torrent_path.name, torrent_file, "application/x-bittorrent"))]
                    for log in release.auxiliary.logs:
                        log_path = release.path / log
                        if log_path.is_file():
                            files.append(("logfiles[]", (log_path.name, log_path.open("rb"), "text/plain")))
                    try:
                        # httpx AsyncClient requires a mapping here. Passing
                        # the legacy list of repeated tuples makes httpx treat
                        # it as a synchronous raw stream before it can build
                        # its async-compatible multipart encoder.
                        # MultipartStream expands list values into repeated
                        # fields, so artists[] and importance[] keep their
                        # required Gazelle form representation.
                        response = await client.post(f"{self.base_url}/ajax.php?action=upload", data=data, files=files)
                    finally:
                        for _, (_, handle, _) in files[1:]:
                            handle.close()
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError, OSError) as error:
            meta.tracker_status.setdefault(self.tracker, {})["status_message"] = f"Upload request failed: {error}"
            return False
        return self._record_upload_response(meta, payload)

    def _record_upload_response(self, meta: Meta, payload: Any) -> bool:
        """Store the meaningful parts of an Orpheus upload response.

        A successful Gazelle response has ``status: success`` and a response
        object containing the new torrent/group IDs.  Warnings are successful
        upload warnings, not errors: preserving them in tracker status makes
        them visible to the terminal/Web UI without incorrectly marking the
        upload as failed.
        """
        status = meta.tracker_status.setdefault(self.tracker, {})
        if not isinstance(payload, dict):
            status["status_message"] = "Orpheus returned a malformed upload response."
            return False
        response_payload: dict[str, Any] = cast(dict[str, Any], payload)
        if response_payload.get("status") != "success":
            error = str(response_payload.get("error", "")).strip()
            status["status_message"] = f"Orpheus rejected the upload request: {error}" if error else "Orpheus rejected the upload request."
            return False

        result = response_payload.get("response")
        if not isinstance(result, dict):
            status["status_message"] = "Orpheus accepted the request but returned no upload result. Verify it on the tracker."
            return True
        result_dict: dict[str, Any] = cast(dict[str, Any], result)

        torrent_id = result_dict.get("torrentId")
        group_id = result_dict.get("groupId")
        if torrent_id is not None:
            status["torrent_id"] = torrent_id
        if group_id is not None:
            status["group_id"] = group_id
        if "newgroup" in result_dict:
            status["new_group"] = bool(result_dict["newgroup"])
        response_warnings = result_dict.get("warnings")
        warnings: list[str] = (
            [str(warning).strip() for warning in cast(list[Any], response_warnings) if warning is not None and str(warning).strip()]
            if isinstance(response_warnings, list)
            else []
        )
        if warnings:
            status["warnings"] = warnings
            status["status_message"] = f"Upload accepted by Orpheus. Warnings: {' | '.join(warnings)}"
            logger.warning(f"{self.tracker}: [yellow]upload accepted with warning(s): {' | '.join(warnings)}[/yellow]")
        else:
            status["status_message"] = "Upload accepted by Orpheus."
        return True

    def build_upload_payload(self, meta: Meta, release: MusicRelease) -> dict[str, str | list[str] | list[int] | int]:
        media = str(release.get("media", ""))
        if not media:
            raise ValueError("Orpheus media/source must be provided; the analyzer will not guess it.")
        image_url = self._cover_url(meta)
        format_name = next(iter(release.formats))
        bitrate, other_bitrate, vbr = self._encoding(release, format_name)
        year = str(release.get("year", ""))
        artists = self._artists(release)
        release_label = str(release.get("release_label", release.get("label", "")))
        release_catalogue = str(release.get("release_catalogue_number", release.get("catalogue_number", "")))
        edition_label = str(release.get("edition_label", ""))
        edition_catalogue = str(release.get("edition_catalogue_number", ""))
        # Orpheus requires an edition year on every upload, including a first
        # digital issue that is not a remaster.  Keep the generic model's
        # release/edition distinction intact and only derive this tracker form
        # value at the adapter boundary.
        edition_year = self._edition_year_for_upload(release)
        is_remaster = bool(edition_year or release.get("edition"))
        payload: dict[str, str | list[str] | list[int] | int] = {
            "album_desc": self._album_description(release),
            "artists[]": artists,
            "bitrate": bitrate,
            "catalogue_number": release_catalogue,
            "format": format_name,
            "image": image_url,
            "importance[]": [1] * len(artists),
            "media": media,
            "record_label": release_label,
            "release_desc": self._release_description(release),
            "releasetype": self.release_types.get(str(release.get("release_type", "Unknown")), 21),
            "remaster_catalogue_number": edition_catalogue if is_remaster else "",
            "remaster_record_label": edition_label if is_remaster else "",
            "remaster_title": str(release.get("edition", "")),
            "remaster_year": edition_year,
            "remaster": int(bool(is_remaster)),
            "scene": int(bool(meta.scene)),
            "submit": 1,
            "tags": ",".join(str(value).replace(" ", ".").lower() for value in release.get("genres", [])),
            "title": str(release.get("album")),
            "type": 0,
            "vbr": int(vbr),
            "year": year,
        }
        if other_bitrate:
            payload["other_bitrate"] = other_bitrate
        return {key: value for key, value in payload.items() if value not in ("", None, [])}

    @staticmethod
    def _edition_year_for_upload(release: MusicRelease) -> str:
        """Resolve Orpheus's mandatory edition year without mutating metadata."""
        candidates = (release.get("edition_year", ""), release.get("release_year", ""), release.get("retail_date", ""), release.get("year", ""))
        for candidate in candidates:
            match = re.search(r"\b(\d{4})\b", str(candidate or ""))
            if match:
                return match.group(1)
        return ""

    @staticmethod
    def _artists(release: MusicRelease) -> list[str]:
        values = release.get("artists")
        if isinstance(values, list):
            artists = [str(value).strip() for value in cast(list[Any], values) if value is not None and str(value).strip()]
            if artists:
                return artists
        artist = str(release.get("artist", "")).strip()
        return [artist] if artist else []

    @staticmethod
    def _form_data(payload: dict[str, str | int | list[str | int]]) -> list[tuple[str, str | int]]:
        """Encode repeated Gazelle fields as repeated multipart form keys."""
        form: list[tuple[str, str | int]] = []
        for key, value in payload.items():
            if isinstance(value, list):
                form.extend((key, item) for item in value)
            else:
                form.append((key, value))
        return form

    @staticmethod
    def _cover_url(meta: Meta) -> str:
        """Return an allowed optional Orpheus artwork URL, never a local path.

        The form accepts optional HTTP(S) artwork, but disallows Discogs,
        Facebook CDN and Photobucket hosts.  Invalid or disallowed URLs are
        omitted rather than being submitted as a local path.
        """
        value = str(meta.artwork_url or "").strip()
        parsed = urlparse(value)
        host = (parsed.hostname or "").casefold()
        banned_hosts = ("discogs.com", "fbcdn.net", "photobucket.com")
        if parsed.scheme in {"http", "https"} and host and not any(host == banned or host.endswith(f".{banned}") for banned in banned_hosts):
            return value
        return ""

    @staticmethod
    def _encoding(release: MusicRelease, format_name: str) -> tuple[str, str, bool]:
        tracks = release.tracks
        if format_name == "FLAC":
            return ("24bit Lossless" if any((track.bit_depth or 0) > 16 for track in tracks) else "Lossless", "", False)
        average = round(sum(track.bitrate or 0 for track in tracks) / max(len(tracks), 1) / 1000)
        mode = next((track.bitrate_mode for track in tracks if track.bitrate_mode), None)
        if format_name == "MP3" and mode == "CBR" and average in {192, 256, 320}:
            return str(average), "", False
        return "Other", str(average or "VBR"), mode == "VBR"

    @staticmethod
    def _album_description(release: MusicRelease) -> str:
        lines = [f"[b]Tracklist[/b] ({release.disc_count} disc(s))\n"]
        total_duration = 0.0
        for track in release.tracks:
            prefix = f"{track.disc_number}." if release.disc_count > 1 else ""
            number = str(track.track_number) if track.track_number else "--"
            duration = float(track.duration or 0)
            total_duration += duration
            lines.append(f"{prefix}{number}. {track.title or Path(track.relative_path).stem} ({Orpheus._format_duration(duration)})")
        lines.append(f"\nTotal length: {Orpheus._format_duration(total_duration)}")
        return "\n".join(lines)

    @staticmethod
    def _format_duration(seconds: float) -> str:
        total_seconds = max(0, round(seconds))
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes:02d}:{seconds:02d}"

    @staticmethod
    def _release_description(release: MusicRelease) -> str:
        variants = sorted({f"{track.bit_depth or '?'}-bit / {(track.sample_rate or 0) / 1000:g} kHz / {track.channels or '?'}ch" for track in release.tracks})
        parts = [f"Technical audio: {', '.join(variants)}."] if variants else []
        if release.get("retail_date"):
            parts.append(f"Retail date: {release.get('retail_date')}.")
        if release.get("store_url"):
            parts.append(f"[url={release.get('store_url')}]Store listing[/url]")
        if release.auxiliary.cues:
            parts.append("Cue sheet included.")
        if release.auxiliary.logs:
            parts.append("Rip log included.")
        return "\n".join(parts)
