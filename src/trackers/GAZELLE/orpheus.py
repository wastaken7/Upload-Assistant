from __future__ import annotations

import asyncio
import json
import platform
import re
import unicodedata
from pathlib import Path
from typing import Any, ClassVar, cast
from urllib.parse import urlparse

import bencodepy
import httpx
from rich.markup import escape

from src import payload_preview
from src.console import logger
from src.meta import Meta
from src.music.models import MusicRelease
from src.music.validation import OrpheusEdition, OrpheusMusicValidator, ValidationLevel, lame_preset, resolve_orpheus_edition
from src.slot_rules.models import Verdict
from src.slot_rules.trackers.orpheus import SLOT_DECISION_KEY, MusicEdition, MusicTorrent, OrpheusSlotRules, Outcome, sample_rate_hint
from src.trackers.common import Common
from src.trackers.GAZELLE.orpheus_tags import orpheus_tags


class Orpheus:
    """Orpheus is a Private Torrent Tracker for MUSIC"""

    tracker = "ORPHEUS"
    display_name = "Orpheus"
    auth_type = "other_api"
    supported_categories = ("MUSIC",)
    source_flag = "OPS"
    base_url = "https://orpheus.network"
    # Artwork hosts the upload form rejects; any other host is accepted.
    banned_image_hosts = ("discogs.com", "fbcdn.net", "photobucket.com", "ptpimg.me")
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
    # Gazelle artist "importance" values from the upload form.
    artist_roles: ClassVar[dict[str, int]] = {
        "main": 1,
        "guest": 2,
        "remixer": 3,
        "composer": 4,
        "conductor": 5,
        "dj": 6,
        "compiler": 6,
        "producer": 7,
        "arranger": 8,
    }
    # Bitrates offered by the upload form for a CBR/ABR value.
    form_bitrates = frozenset({320, 256, 192, 160, 128, 96, 64})
    classical_tags = frozenset({"classical", "baroque.era", "classical.era", "romantic", "renaissance", "opera", "chamber.music", "modern.classical", "score"})
    banned_groups = ()
    blocked_music_artists: ClassVar[dict[str, str]] = {
        "vap0rwave": "Vap0rwave",
        "pauldvr": "Paul_DVR",
        "firmensprecher": "Firmensprecher",
        "stretches": "stretches",
        "phyllomedusa": "Phyllomedusa",
        "drizzywap": "Drizzy Wap",
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
    max_tag_length = 200
    max_lineage_characters = 8000

    # Responses worth another try: rate limiting and gateway/server failures.
    retry_status_codes: ClassVar[frozenset[int]] = frozenset({429, 500, 502, 503, 504, 520, 521, 522, 524})
    # The upload POST is retried only when Orpheus certainly did not process it.
    # A 500/502/504 or a read timeout can follow a completed upload, and a
    # second POST would then create a duplicate.
    upload_retry_status_codes: ClassVar[frozenset[int]] = frozenset({429, 503})
    retry_delay_seconds = 5.0

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        settings = config.get("TRACKERS", {}).get(self.tracker, {})
        self.api_key = str(settings.get("api_key", "")).strip()
        self.announce_url = str(settings.get("announce_url", "")).strip()
        self.requests_url = f"{self.base_url}/requests.php"
        self.torrent_url = f"{self.base_url}/torrents.php?torrentid="
        self.common = Common(config)

    def _max_attempts(self) -> int:
        """Attempts per request: ``max_retries`` from the tracker, else DEFAULT, as for UNIT3D."""
        default = self.config.get("DEFAULT", {}).get("max_retries", 2)
        try:
            return max(1, int(self.config.get("TRACKERS", {}).get(self.tracker, {}).get("max_retries", default)))
        except TypeError, ValueError:
            return 2

    @staticmethod
    def _error_text(error: BaseException) -> str:
        # Timeouts and some transport errors have no message; name the error instead.
        return str(error) or type(error).__name__

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

    async def _api_get(self, meta: Meta, params: dict[str, str], timeout_seconds: float, purpose: str) -> dict[str, Any] | None:
        """Run one read-only ``ajax.php`` GET and return its ``response`` object.

        Timeouts, connection failures and rate-limit or server errors are
        retried; a GET changes nothing, so repeating it is safe.
        """
        attempts = self._max_attempts()
        timeout = timeout_seconds
        raw_json: Any = None
        for attempt in range(1, attempts + 1):
            try:
                async with httpx.AsyncClient(timeout=httpx.Timeout(timeout), headers=self._headers(meta)) as client:
                    response = await client.get(f"{self.base_url}/ajax.php", params=params)
                    response.raise_for_status()
                    raw_json = response.json()
                break
            except (httpx.HTTPError, ValueError) as error:
                retryable = isinstance(error, httpx.TransportError) or (isinstance(error, httpx.HTTPStatusError) and error.response.status_code in self.retry_status_codes)
                if not retryable or attempt >= attempts:
                    logger.warning(f"{self.tracker}: [yellow]read-only {purpose} failed: {self._error_text(error)}[/yellow]")
                    return None
                if isinstance(error, httpx.TimeoutException):
                    timeout *= 1.5
                logger.info(
                    f"{self.tracker}: [yellow]{purpose} failed ({self._error_text(error)}), retrying in {self.retry_delay_seconds:g} seconds... (attempt {attempt}/{attempts})[/yellow]"
                )
                await asyncio.sleep(self.retry_delay_seconds)
        if not isinstance(raw_json, dict):
            return None
        payload = cast(dict[str, Any], raw_json)
        response_data = payload.get("response")
        if payload.get("status") != "success" or not isinstance(response_data, dict):
            return None
        return cast(dict[str, Any], response_data)

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
        labels = {
            cls._normalise_artist_name(value)
            for value in (release.get("release_label", ""), release.get("label", ""), release.get("edition_label", ""))
            if str(value or "").strip()
        }
        return [label for label in cls.blocked_music_labels if cls._normalise_artist_name(label) in labels]

    async def get_additional_checks(self, meta: Meta) -> bool:
        """Prevent uploads of artists, releases and labels prohibited by Orpheus."""
        release = self._release(meta)
        blocked_artists = self._blocked_artists(release)
        blocked_releases = self._blocked_releases(release)
        blocked_labels = self._blocked_labels(release)
        not_in_folder = bool(meta.path) and Path(str(meta.path)).is_file()
        if not (blocked_artists or blocked_releases or blocked_labels or not_in_folder):
            return True
        reasons = [
            *(f"artist {artist}" for artist in blocked_artists),
            *(f"blacklisted release {release_name}" for release_name in blocked_releases),
            *(f"blacklisted label {label}" for label in blocked_labels),
        ]
        messages = [f"Orpheus blacklist matched {', '.join(reasons)}"] if reasons else []
        if not_in_folder:
            reasons.append("not in a folder")
            messages.append("music uploads must be inside a folder; select the release folder, not a single file")
        message = f"Upload blocked: {'; '.join(messages)}."
        status = meta.tracker_status.setdefault(self.tracker, {})
        status["status_message"] = message
        status["blocked_reasons"] = reasons
        logger.error(f"{self.tracker}: [red]{message}[/red]")
        return False

    # ------------------------------------------------------------------
    # Duplicate review
    # ------------------------------------------------------------------

    async def search_existing(self, meta: Meta) -> list[dict[str, Any]]:
        """Find the release group with a few narrow, read-only browse queries.

        Group titles and artist credits are often written differently on the
        site ("Bob" vs "Bobby", "&" vs "and", "FL" vs "Florida", "2023-12-31"
        vs "2023 12 31").  Besides the exact query, at most two more search
        by the cleaned title and, for dated concerts, by the date alone, so a
        second group for the same release is also found.  Matching groups are expanded
        per torrent and compared with the planned upload's edition, medium,
        format and encoding so the dupe and trump rules (2.2) can be reviewed.
        """
        release = self._release(meta)
        artist, album = str(release.get("artist", "")), self._strip_type_marker(release.get("album", ""))[0]
        if not artist or not album or not self.api_key:
            return []
        queries: list[dict[str, str]] = [{"artistname": artist, "groupname": album}]
        # The site requires every search word, so drop joining words: "&" in
        # "Patkop & Say" must not become a required "and".
        cleaned = " ".join(token for token in self._title_tokens(album) if token not in self._IGNORED_TOKENS)
        if cleaned and cleaned.casefold() != album.casefold():
            queries.append({"groupname": cleaned})
        concert_date = self._concert_date(album)
        if concert_date:
            queries.append({"groupname": concert_date.replace("-", " ")})

        matched: dict[str, dict[str, Any]] = {}
        unmatched: dict[str, dict[str, Any]] = {}
        for index, query in enumerate(queries):
            if index:
                await asyncio.sleep(1)
            response = await self._api_get(meta, {"action": "browse", **query}, 8.0, "duplicate search")
            results = response.get("results") if response else None
            for group_item in cast(list[Any], results if isinstance(results, list) else []):
                if not isinstance(group_item, dict):
                    continue
                group = cast(dict[str, Any], group_item)
                key = str(group.get("groupId", ""))
                if self._same_group_title(album, group.get("groupName")) and self._shares_artist(release, group.get("artist"), strict=index > 0):
                    matched[key] = group
                elif index == 0:
                    unmatched[key] = group

        upload = await self._upload_profile(meta, release)
        dupes: list[dict[str, Any]] = []
        existing: list[MusicTorrent] = []
        for index, group in enumerate(matched.values()):
            group_id = group.get("groupId")
            group_name = f"{group.get('artist', '')} - {group.get('groupName', '')}".strip(" -")
            if self._normalise_request_text(group.get("groupName")) != self._normalise_request_text(album):
                logger.warning(
                    f"{self.tracker}: [yellow]existing group found with a different title: {escape(group_name)} ({self.base_url}/torrents.php?id={group_id})[/yellow]"
                )
            torrents = [cast(dict[str, Any], torrent) for torrent in cast(list[Any], group.get("torrents") or []) if isinstance(torrent, dict)]
            details = await self._group_details(meta, group_id, torrents, upload) if index < 3 else {}
            for torrent in torrents:
                torrent_id = torrent.get("torrentId")
                entry: dict[str, Any] = {
                    "name": f"{group_name} [{group.get('groupYear', '')}] / {self._describe_torrent(torrent)}",
                    "size": torrent.get("size"),
                    "id": torrent_id,
                    "link": f"{self.base_url}/torrents.php?id={group_id}&torrentid={torrent_id}" if group_id and torrent_id else None,
                    "flags": [],
                    "type": group.get("releaseType"),
                    "trumpable": False,
                }
                dupes.append(entry)
                existing.append(self._existing_profile(torrent, details.get(str(torrent_id), {}), entry))

        rules = OrpheusSlotRules(meta)
        release_type = str(release.get("release_type", ""))
        decision = rules.evaluate_music(upload, existing, release_type=release_type)
        meta[SLOT_DECISION_KEY] = decision
        # A trump is only reported when the upload is recommended at all.
        trumping = decision.verdict is Verdict.ALLOW
        assessment: list[dict[str, Any]] = []
        for torrent, outcome, reason in rules.assess(upload, existing, release_type=release_type)[0]:
            listed = cast(dict[str, Any], torrent.entry)
            listed["flags"] = [f"{self._OUTCOME_LABELS[outcome]}: {reason}" if reason else self._OUTCOME_LABELS[outcome]]
            listed["trumpable"] = trumping and outcome is Outcome.TRUMPS
            assessment.append({"torrent": listed["name"], "verdict": listed["flags"][0], "trumpable": listed["trumpable"]})
        for key, group in unmatched.items():
            if key in matched:
                continue
            group_id = group.get("groupId")
            dupes.append(
                {
                    "name": f"{group.get('artist', '')} - {group.get('groupName', '')}".strip(" -"),
                    "size": group.get("maxSize"),
                    "id": group_id,
                    "link": f"{self.base_url}/torrents.php?id={group_id}" if group_id else None,
                    "flags": ["different release group"],
                    "type": group.get("releaseType"),
                }
            )
        if assessment:
            meta.tracker_status.setdefault(self.tracker, {})["dupe_assessment"] = assessment
        return dupes

    _OUTCOME_LABELS: ClassVar[dict[Outcome, str]] = {
        Outcome.DUPE: "DUPE",
        Outcome.REVIEW: "REVIEW",
        Outcome.TRUMPS: "TRUMP",
        Outcome.COEXIST: "coexists with your upload",
    }
    _CONCERT_DATE = re.compile(r"(?<!\d)((?:19|20)\d{2})[\s._/-]+(\d{1,2})[\s._/-]+(\d{1,2})(?!\d)")
    _IGNORED_TOKENS = frozenset({"and", "the", "feat", "featuring", "with", "presents"})

    @staticmethod
    def _title_tokens(value: Any) -> list[str]:
        text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii").casefold()
        return re.findall(r"[a-z0-9]+", text.replace("&", " and "))

    @classmethod
    def _concert_date(cls, value: Any) -> str:
        """Return ``YYYY-MM-DD`` for a dated concert title, else an empty string."""
        match = cls._CONCERT_DATE.search(str(value or ""))
        if not match:
            return ""
        year, month, day = match.group(1), int(match.group(2)), int(match.group(3))
        return f"{year}-{month:02d}-{day:02d}" if 1 <= month <= 12 and 1 <= day <= 31 else ""

    @classmethod
    def _title_words(cls, value: Any, *, drop_date: bool = False) -> set[str]:
        text = cls._CONCERT_DATE.sub(" ", str(value or "")) if drop_date else value
        return set(cls._title_tokens(text)) - cls._IGNORED_TOKENS

    # A trailing release-type descriptor, e.g. "Title EP", "Title - EP",
    # "Title (Single)" or "Title (Live)".  Bare "Live" is not matched because
    # it is often part of a real title.
    _TYPE_MARKER = re.compile(
        r"(?:\s*[(\[]\s*(?P<bracketed>e\.?p\.?|single|live)\s*[)\]]|\s+-\s+(?P<dashed>e\.?p\.?|single)|\s+(?P<bare>e\.?p\.?))\s*$",
        re.I,
    )
    _MARKER_TYPES: ClassVar[dict[str, set[str]]] = {
        "ep": {"EP"},
        "single": {"Single"},
        "live": {"Live album", "Concert recording"},
    }

    @classmethod
    def _strip_type_marker(cls, title: Any) -> tuple[str, str]:
        """Return ``(title without marker, marker)``; the marker is "ep", "single" or "live"."""
        text = str(title or "").strip()
        match = cls._TYPE_MARKER.search(text)
        # Keep titles such as "The EP", where only an article would remain.
        if not match or not set(cls._title_tokens(text[: match.start()])) - {"the", "a", "an"}:
            return text, ""
        marker = next(group for group in match.groups() if group).replace(".", "").casefold()
        return text[: match.start()].strip(" -"), marker

    def _upload_title(self, meta: Meta, release: MusicRelease) -> str:
        """Drop a trailing marker that only repeats the release type (rule 2.3.6)."""
        album = str(release.get("album", ""))
        stripped, marker = self._strip_type_marker(album)
        if marker and str(release.get("release_type", "")) in self._MARKER_TYPES.get(marker, set()):
            logger.info(f"{self.tracker}: [yellow]title sent as '{escape(stripped)}'; the release type already says {marker.upper()}.[/yellow]")
            meta.tracker_status.setdefault(self.tracker, {})["title_note"] = f"'{album}' -> '{stripped}'"
            return stripped
        return album

    @classmethod
    def _same_group_title(cls, ours: Any, theirs: Any) -> bool:
        """Tolerant title comparison; dated concerts must share the date.

        A trailing release-type marker ("EP", "(Live)") is ignored on both
        sides, since the site keeps that in the release type, not the title.
        """
        ours, theirs = cls._strip_type_marker(ours)[0], cls._strip_type_marker(theirs)[0]
        if cls._normalise_request_text(ours) == cls._normalise_request_text(theirs):
            return True
        our_date, their_date = cls._concert_date(ours), cls._concert_date(theirs)
        if our_date or their_date:
            if our_date != their_date:
                return False
            a, b = cls._title_words(ours, drop_date=True), cls._title_words(theirs, drop_date=True)
            # Measure against the longer title so another venue on the same
            # date ("Live at X" vs "Live at Y Z") does not match.
            return not a or not b or len(a & b) / max(len(a), len(b)) >= 0.6
        a, b = cls._title_words(ours), cls._title_words(theirs)
        return bool(a and b) and len(a & b) / len(a | b) >= 0.85

    @classmethod
    def _shares_artist(cls, release: MusicRelease, group_artist: Any, *, strict: bool = False) -> bool:
        """Return whether the group's artist credit overlaps the release artists.

        The first query is already filtered by artist on the server, so a
        partial credit ("A" vs "A & B") is enough.  Title- or date-only
        queries are not, so they require most of the larger credit to match
        and accept "Various Artists" only for compilations.

        Classical groups are credited as "<composers> performed by
        <performers> [under <conductor>]"; only the performers are compared.
        """
        credit = str(group_artist or "")
        if re.fullmatch(r"\s*various artists\s*", credit, flags=re.I):
            ours_credit = {cls._normalise_request_text(name) for name in cls._artists(release)}
            return "variousartists" in ours_credit or str(release.get("release_type", "")) == "Compilation"
        performers = re.split(r"\bperformed by\b", credit, maxsplit=1, flags=re.I)
        if len(performers) == 2:
            credit = re.split(r"\bunder\b", performers[1], maxsplit=1, flags=re.I)[0]
        theirs = cls._title_words(credit)
        ours = {token for name in cls._artists(release) for token in cls._title_words(name)}
        if not theirs or not ours:
            return False
        overlap = len(ours & theirs)
        return overlap / (max(len(ours), len(theirs)) if strict else min(len(ours), len(theirs))) >= 0.5

    def _planned_upload(self, release: MusicRelease) -> dict[str, Any]:
        format_name = next(iter(release.formats)) if len(release.formats) == 1 else ""
        encoding = ""
        if format_name:
            bitrate, other, vbr = self._encoding(release, format_name)
            encoding = f"{other} (VBR)" if bitrate == "Other" and vbr else (other if bitrate == "Other" else bitrate)
        edition = resolve_orpheus_edition(release)
        return {
            "edition": edition,
            "media": str(release.get("media", "")),
            "format": format_name,
            "encoding": encoding,
            "has_log": bool(release.auxiliary.logs),
            # Folder catalogue numbers are not sent, but they are reliable
            # enough to recognise an existing release of the same pressing.
            "catalogue_number": edition.catalogue_number or dict(edition.folder_hints).get("catalogue number", ""),
        }

    @staticmethod
    def _describe_torrent(torrent: dict[str, Any]) -> str:
        edition_bits = [str(torrent.get(key) or "").strip() for key in ("remasterYear", "remasterRecordLabel", "remasterCatalogueNumber", "remasterTitle")]
        edition = " ".join(bit for bit in edition_bits if bit and bit != "0") or "Unknown/Original release"
        parts = [str(torrent.get(key) or "") for key in ("media", "format", "encoding")]
        if torrent.get("hasLog"):
            parts.append(f"Log ({torrent.get('logScore', 0)}%)")
        if torrent.get("hasCue"):
            parts.append("Cue")
        if torrent.get("scene"):
            parts.append("Scene")
        return f"{edition} / {' '.join(part for part in parts if part)}"

    async def _upload_profile(self, meta: Meta, release: MusicRelease) -> MusicTorrent:
        planned = self._planned_upload(release)
        edition: OrpheusEdition = planned["edition"]
        if planned["format"] == "FLAC" and str(planned["media"]).upper() == "CD":
            # Log trumps depend on the score; this only runs with --music-check-log.
            await self._check_logs(meta, release)
        log_checks = cast(list[dict[str, Any]], meta.tracker_status.get(self.tracker, {}).get("log_checks") or [])
        scores = [int(check["score"]) for check in log_checks if isinstance(check.get("score"), int)]
        return MusicTorrent(
            media=str(planned["media"]),
            format=str(planned["format"]),
            encoding=str(planned["encoding"]),
            edition=MusicEdition(edition.unknown, edition.year, edition.label, str(planned["catalogue_number"]), edition.title),
            sample_rate=max((track.sample_rate or 0 for track in release.tracks), default=0) or None,
            has_log=bool(planned["has_log"]),
            log_score=min(scores) if scores else None,
            has_cue=bool(release.auxiliary.cues),
        )

    async def _group_details(self, meta: Meta, group_id: Any, torrents: list[dict[str, Any]], upload: MusicTorrent) -> dict[str, dict[str, Any]]:
        """Per-torrent details (trumpable flags, folder name) when a torrent may compete with the upload.

        Search results lack the site's trumpable flags and anything that shows
        a sample rate, so one read-only group lookup is made only when needed.
        """
        competing = any(str(torrent.get("format", "")) == upload.format and str(torrent.get("media", "")).casefold() == upload.media.casefold() for torrent in torrents)
        if not competing or not str(group_id or "").isdigit():
            return {}
        await asyncio.sleep(1)
        response = await self._api_get(meta, {"action": "torrentgroup", "id": str(group_id)}, 10.0, f"group details for {group_id}")
        items = response.get("torrents") if response else None
        return {str(item.get("id")): item for item in cast(list[dict[str, Any]], items if isinstance(items, list) else []) if isinstance(item, dict)}

    @staticmethod
    def _trumpable_reasons(details: dict[str, Any]) -> tuple[str, ...]:
        if not details.get("trumpable"):
            return ()
        reasons: list[str] = []
        for reason in cast(list[Any], details.get("trumpable_reasons") or []):
            if isinstance(reason, dict):
                values = cast(dict[str, Any], reason)
                reason = values.get("reason") or values.get("name") or values.get("description") or ""
            if str(reason).strip():
                reasons.append(str(reason).strip())
        return tuple(reasons) or ("marked trumpable",)

    @classmethod
    def _existing_profile(cls, torrent: dict[str, Any], details: dict[str, Any], entry: dict[str, Any]) -> MusicTorrent:
        year = str(torrent.get("remasterYear") or "").strip()
        label, catalogue, title = (str(torrent.get(key) or "").strip() for key in ("remasterRecordLabel", "remasterCatalogueNumber", "remasterTitle"))
        unknown = year in {"", "0"} and not (label or catalogue or title)
        log_score = details.get("logScore", torrent.get("logScore"))
        return MusicTorrent(
            media=str(torrent.get("media") or ""),
            format=str(torrent.get("format") or ""),
            encoding=str(torrent.get("encoding") or ""),
            edition=MusicEdition(unknown, "" if year == "0" else year, label, catalogue, title),
            sample_rate=sample_rate_hint(details.get("filePath"), details.get("description")),
            has_log=bool(torrent.get("hasLog")),
            log_score=int(log_score) if torrent.get("hasLog") and isinstance(log_score, int) else None,
            has_cue=bool(torrent.get("hasCue")),
            scene=bool(torrent.get("scene")),
            trumpable_reasons=cls._trumpable_reasons(details),
            entry=entry,
        )

    async def get_torrent(self, torrent_id: int | str, meta: Meta) -> dict[str, Any] | None:
        """Return one Orpheus torrent's Gazelle metadata using a read-only API call.

        This is deliberately separate from upload and is useful for local
        release audits when a torrent comment already supplies an exact ID.
        """
        identifier = str(torrent_id).strip()
        if not identifier.isdigit() or not self.api_key:
            return None
        return await self._api_get(meta, {"action": "torrent", "id": identifier}, 15.0, f"torrent lookup for {identifier}")

    # ------------------------------------------------------------------
    # Requests
    # ------------------------------------------------------------------

    async def get_requests(self, meta: Meta) -> list[dict[str, Any]]:
        """Search open MUSIC requests with one bounded, read-only API call.

        Title, credited artists and initial year determine the match level;
        the request's format/bitrate/media/log/cue requirements are compared
        with the planned upload and shown for review.  Requests are never
        filled automatically; use ``--music-request-id`` for that.
        """
        if meta.category != "MUSIC" or not self.api_key:
            return []
        release = self._release(meta)
        album = str(release.get("album", "")).strip()
        if not album:
            return []
        # ``filter_cat[]`` is a zero-based category index (0 = Music), and
        # ``show_filled`` is enabled by its mere presence, so it is omitted.
        response = await self._api_get(meta, {"action": "requests", "search": album, "filter_cat[]": "0"}, 10.0, "request search")
        if response is None:
            return []
        records = response.get("results")
        if not isinstance(records, list):
            return []

        planned = self._planned_upload(release)
        matches: list[dict[str, Any]] = []
        for record_item in cast(list[Any], records):
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
            compatible, unmet = self._request_compatibility(record, planned, release)
            matches.append(
                {
                    "id": str(request_id),
                    "name": f"{' & '.join(artists)} - {title}".strip(" -"),
                    "bounty": record.get("bounty", record.get("totalBounty", 0)),
                    "description": str(record.get("bbDescription", record.get("description", ""))),
                    "match_type": match_type,
                    "compatible": compatible,
                    "unmet": unmet,
                    "requirements": {
                        "release_type": record.get("releaseTypeName", record.get("releaseType", "")),
                        "bitrate": record.get("bitrateList", ""),
                        "format": record.get("formatList", ""),
                        "media": record.get("mediaList", ""),
                        "need_log": record.get("needLog", False),
                        "need_cue": record.get("needCue", False),
                        "need_log_checksum": record.get("needLogChecksum", False),
                        "min_log_score": record.get("minLogScore", 0),
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
                if match["compatible"]:
                    logger.info(f"{self.tracker}: [green]This upload meets the request's technical requirements. Fill it with --music-request-id {match['id']}.[/green]")
                else:
                    logger.info(f"{self.tracker}: [yellow]Not compatible: {escape('; '.join(match['unmet']))}[/yellow]")
        meta.tracker_status.setdefault(self.tracker, {})["request_matches"] = matches
        return matches

    @staticmethod
    def _accepts(allowed: Any, value: str) -> bool:
        values = [str(item) for item in cast(list[Any], allowed)] if isinstance(allowed, list) else [item.strip() for item in str(allowed or "").split(",") if item.strip()]
        return not values or "Any" in values or value in values

    @classmethod
    def _request_compatibility(
        cls, record: dict[str, Any], planned: dict[str, Any], release: MusicRelease, log_checks: list[dict[str, Any]] | None = None
    ) -> tuple[bool, list[str]]:
        unmet: list[str] = []
        if not cls._accepts(record.get("formatList"), planned["format"]):
            unmet.append(f"format {planned['format']} not in {record.get('formatList')}")
        if not cls._accepts(record.get("bitrateList"), planned["encoding"]):
            unmet.append(f"bitrate {planned['encoding']} not in {record.get('bitrateList')}")
        if not cls._accepts(record.get("mediaList"), planned["media"]):
            unmet.append(f"media {planned['media']} not in {record.get('mediaList')}")
        if record.get("needLog") and not release.auxiliary.logs:
            unmet.append("a rip log is required")
        if record.get("needCue") and not release.auxiliary.cues:
            unmet.append("a cue sheet is required")
        # A minimum log score cannot be proven locally; when --music-check-log
        # scored the logs, the best score must reach the request's minimum.
        scores = [float(entry["score"]) for entry in log_checks or [] if isinstance(entry.get("score"), int | float)]
        minimum = float(record.get("minLogScore") or 0)
        if minimum and scores and max(scores) < minimum:
            unmet.append(f"log score {max(scores):g}% is below the minimum {minimum:g}%")
        return not unmet, unmet

    @classmethod
    def _artists_overlap(cls, release: MusicRelease, record: dict[str, Any]) -> bool:
        """Return whether a request/group shares an artist with the release."""
        theirs = {cls._normalise_request_text(name) for name in cls._request_artists(record)}
        ours = {cls._normalise_request_text(name) for name in cls._artists(release)}
        return not theirs or bool(theirs & ours)

    @staticmethod
    def _normalise_request_text(value: Any) -> str:
        return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())

    @classmethod
    def _request_artists(cls, record: dict[str, Any]) -> list[str]:
        artists: list[str] = []
        roles: Any = record.get("artists") or record.get("musicInfo") or []
        role_lists = list(cast(dict[str, Any], roles).values()) if isinstance(roles, dict) else cast(list[Any], roles)
        for role in role_lists:
            if not isinstance(role, list):
                continue
            for artist_item in cast(list[Any], role):
                if isinstance(artist_item, dict):
                    name = str(cast(dict[str, Any], artist_item).get("name", "")).strip()
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

    @staticmethod
    def _parse_identifier(value: Any) -> str:
        """Accept a bare ID or an Orpheus URL containing ``id=``."""
        text = str(value or "").strip()
        if text.isdigit():
            return text
        match = re.search(r"[?&](?:id|requestid|groupid)=(\d+)", text)
        return match.group(1) if match else ""

    async def _verify_request_fill(self, meta: Meta, release: MusicRelease, log_checks: list[dict[str, Any]] | None = None) -> tuple[str, str]:
        """Return ``(request_id, error)`` for an explicitly requested fill."""
        request_id = self._parse_identifier(meta.music_request_id)
        if not str(meta.music_request_id or "").strip():
            return "", ""
        if not request_id:
            return "", f"invalid request ID or URL: {meta.music_request_id}"
        record = await self._api_get(meta, {"action": "request", "id": request_id}, 10.0, f"request lookup for {request_id}")
        if record is None:
            return "", f"request {request_id} could not be loaded"
        if record.get("isFilled"):
            return "", f"request {request_id} is already filled"
        if str(record.get("categoryName", "Music")) != "Music":
            return "", f"request {request_id} is not a Music request"
        if self._request_match_type(release, record) is None:
            return "", f"request {request_id} title '{record.get('title', '')}' does not match '{release.get('album', '')}'"
        if not self._artists_overlap(release, record):
            return "", f"request {request_id} artists {self._request_artists(record)} do not match {self._artists(release)}"
        compatible, unmet = self._request_compatibility(record, self._planned_upload(release), release, log_checks)
        if not compatible:
            return "", f"request {request_id} requirements are not met: {'; '.join(unmet)}"
        return request_id, ""

    async def _verify_group(self, meta: Meta, release: MusicRelease) -> tuple[str, str]:
        """Return ``(group_id, error)`` for an explicit existing torrent group."""
        if not str(meta.music_group_id or "").strip():
            return "", ""
        group_id = self._parse_identifier(meta.music_group_id)
        if not group_id:
            return "", f"invalid group ID or URL: {meta.music_group_id}"
        response = await self._api_get(meta, {"action": "torrentgroup", "id": group_id}, 10.0, f"group lookup for {group_id}")
        group = cast(dict[str, Any], response.get("group")) if response and isinstance(response.get("group"), dict) else None
        if group is None:
            return "", f"group {group_id} could not be loaded"
        if self._normalise_request_text(group.get("name")) != self._normalise_request_text(release.get("album")):
            return "", f"group {group_id} is '{group.get('name', '')}', not '{release.get('album', '')}'"
        if not self._artists_overlap(release, group):
            return "", f"group {group_id} artists {self._request_artists(group)} do not match {self._artists(release)}"
        return group_id, ""

    async def _check_logs(self, meta: Meta, release: MusicRelease) -> list[dict[str, Any]]:
        """Score rip logs with Orpheus's logchecker when explicitly enabled.

        The logchecker endpoint only parses the submitted log and returns its
        score; it does not create or change anything on the site.
        """
        if not meta.music_check_log or not release.auxiliary.logs or not self.api_key:
            return []
        results: list[dict[str, Any]] = []
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0), headers=self._headers(meta)) as client:
            for log in release.auxiliary.logs:
                log_path = release.path / log
                if not log_path.is_file():
                    continue
                try:
                    with log_path.open("rb") as handle:
                        response = await client.post(f"{self.base_url}/ajax.php?action=logchecker", files={"log": (log_path.name, handle, "text/plain")})
                    response.raise_for_status()
                    payload = response.json()
                except (httpx.HTTPError, ValueError, OSError) as error:
                    logger.warning(f"{self.tracker}: [yellow]logchecker failed for {escape(log)}: {error}[/yellow]")
                    continue
                body = cast(dict[str, Any], payload) if isinstance(payload, dict) else {}
                data: Any = body.get("response") if body.get("status") == "success" else None
                if not isinstance(data, dict):
                    continue
                result = cast(dict[str, Any], data)
                entry: dict[str, Any] = {
                    "log": log,
                    "score": result.get("score"),
                    "checksum": result.get("checksum"),
                    "ripper": result.get("ripper"),
                    "issues": result.get("issues", []),
                }
                results.append(entry)
                colour = "green" if entry["score"] == 100 else "yellow"
                logger.info(f"{self.tracker}: [{colour}]log {escape(log)}: score {entry['score']}% ({escape(str(entry['ripper']))}, checksum {entry['checksum']})[/{colour}]")
                for issue in cast(list[Any], entry["issues"] or []):
                    logger.info(f"{self.tracker}: [yellow]  - {escape(str(issue))}[/yellow]")
        if results:
            meta.tracker_status.setdefault(self.tracker, {})["log_checks"] = results
        return results

    async def get_name(self, meta: Meta) -> str:
        """For the terminal display only, not for upload."""
        release = self._release(meta)
        return f"{release.get('artist', '')} - {release.get('album', '')} [{release.get('year', '')!s}]".strip(" -")

    async def get_payload_preview(self, meta: Meta) -> payload_preview.TrackerPreview:
        """The upload form as it is known before the tracker checks, for the Web UI to show and edit."""
        specs = {
            "album_desc": payload_preview.readonly("Album description"),
            "artists[]": payload_preview.readonly("Artists"),
            "importance[]": payload_preview.readonly("Artist roles"),
            "release_desc": payload_preview.readonly("Release description"),
            "releasetype": payload_preview.choice("Release type", self.release_types, by_label=True),
            "submit": payload_preview.readonly("Submit"),
            "type": payload_preview.readonly("Type"),
            "vbr": payload_preview.flag("VBR", on=1, off=0),
            "image": payload_preview.text("Cover URL"),
            "unknown": payload_preview.flag("Unknown release", on=1, off=None),
            "scene": payload_preview.flag("Scene", on=1, off=None),
            "vanity_house": payload_preview.flag("Vanity House", on=1, off=None),
        }
        deferred = {
            "groupid": "Found on the tracker at upload time",
            "requestid": "Matched to a request on the tracker at upload time",
            "logfiles[]": "Attached at upload time",
        }
        data = self.build_upload_payload(meta, self._release(meta))
        return payload_preview.describe(self.tracker, data, specs, deferred=deferred, name=await self.get_name(meta))

    async def upload(self, meta: Meta) -> bool:
        release = self._release(meta)
        if not await self.get_additional_checks(meta):
            return False
        status = meta.tracker_status.setdefault(self.tracker, {})
        issues = OrpheusMusicValidator().validate(release)
        errors = [issue.message for issue in issues if issue.level == ValidationLevel.ERROR]
        warnings = [issue.message for issue in issues if issue.level == ValidationLevel.WARNING]
        if warnings:
            status["validation_warnings"] = warnings
            for warning in warnings:
                logger.warning(f"{self.tracker}: [yellow]{escape(warning)}[/yellow]")
        if errors:
            status["status_message"] = "Validation failed: " + " | ".join(errors)
            return False
        # The dupe check may already have scored the logs.
        log_checks = cast(list[dict[str, Any]], status.get("log_checks") or []) or await self._check_logs(meta, release)
        request_id, request_error = await self._verify_request_fill(meta, release, log_checks) if self.api_key else ("", "")
        group_id, group_error = await self._verify_group(meta, release) if self.api_key else ("", "")
        if request_error or group_error:
            status["status_message"] = "Upload blocked: " + " | ".join(error for error in (request_error, group_error) if error)
            return False
        # Keep debug semantics consistent with the other tracker adapters: do
        # not create a tracker torrent and never make a state-changing request.
        # Duplicate searching remains read-only and is performed earlier in the
        # normal tracker-status flow.
        if meta.debug:
            data = self.build_upload_payload(meta, release)
            if request_id:
                data["requestid"] = request_id
            if group_id:
                data["groupid"] = group_id
            data = payload_preview.apply_payload_edits(meta, self.tracker, data)
            debug_payload: dict[str, Any] = {
                **data,
                "file_input": "<not-created in debug mode>",
                "logfiles[]": list(release.auxiliary.logs),
            }
            status["status_message"] = "Debug mode: upload skipped; payload prepared locally. Artwork is optional on Orpheus."
            status["debug_payload_fields"] = sorted(data)
            status["debug_payload"] = debug_payload
            logger.info(f"{self.tracker}: [yellow]debug mode enabled; POST upload skipped. Prepared payload:[/yellow]")
            logger.info(json.dumps(debug_payload, ensure_ascii=False, indent=2), extra={"markup": False})
            return True
        if not self.api_key or not self.announce_url:
            status["status_message"] = "Missing Orpheus API key or announce URL."
            return False
        await self.common.create_torrent_for_upload(meta, self.tracker, self.source_flag, announce_url=self.announce_url)
        torrent_path = Path(meta.base_dir) / "tmp" / str(meta.uuid) / f"[{self.tracker}].torrent"
        if not torrent_path.is_file():
            status["status_message"] = "Tracker torrent was not created."
            return False
        data = self.build_upload_payload(meta, release)
        if request_id:
            data["requestid"] = request_id
        if group_id:
            data["groupid"] = group_id
        data = payload_preview.apply_payload_edits(meta, self.tracker, data)
        payload = await self._post_upload(meta, data, torrent_path, release)
        if payload is None:
            return False
        accepted = self._record_upload_response(meta, payload)
        if accepted and not await self._download_site_torrent(meta):
            await self._write_torrent_comment(meta)
        return accepted

    async def _post_upload(self, meta: Meta, data: dict[str, Any], torrent_path: Path, release: MusicRelease) -> Any:
        """POST the upload and return the decoded JSON, or None after recording why it failed.

        Only failures that prove the upload was not processed are retried: the
        connection was never made, or Orpheus answered 429/503. Any other
        failure may follow a completed upload, so it is reported instead.
        """
        status = meta.tracker_status.setdefault(self.tracker, {})
        attempts = self._max_attempts()
        for attempt in range(1, attempts + 1):
            try:
                async with httpx.AsyncClient(timeout=httpx.Timeout(60.0), headers=self._headers(meta)) as client:
                    # Files are reopened for every attempt; a failed POST may have read them.
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
                    return response.json()
            except (httpx.HTTPError, ValueError, OSError) as error:
                not_processed = isinstance(error, (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout)) or (
                    isinstance(error, httpx.HTTPStatusError) and error.response.status_code in self.upload_retry_status_codes
                )
                if not_processed and attempt < attempts:
                    logger.info(
                        f"{self.tracker}: [yellow]Upload request failed ({self._error_text(error)}), retrying in {self.retry_delay_seconds:g} seconds... (attempt {attempt}/{attempts})[/yellow]"
                    )
                    await asyncio.sleep(self.retry_delay_seconds)
                    continue
                message = f"Upload request failed: {self._error_text(error)}"
                # An unreadable response (ValueError from .json()) can also follow a
                # stored upload; only a local file error (OSError) means nothing was sent.
                if not not_processed and isinstance(error, (httpx.HTTPError, ValueError)):
                    message += ". The upload may still have reached Orpheus; check the site before uploading again."
                status["status_message"] = message
                return None
        return None

    async def _download_site_torrent(self, meta: Meta) -> bool:
        """Replace the client torrent with the one served by Orpheus.

        Seeding the site's own file keeps the client correct even if the site
        changes the torrent after upload (for example its source flag).  The
        file carries the user's announce URL and the torrent link as comment.
        One API request is made; ``usetoken`` is never sent, so no freeleech
        token is spent.

        The API reports errors as JSON with HTTP 200. The shared downloader
        validates the completed download before replacing the local torrent.
        """
        status = meta.tracker_status.setdefault(self.tracker, {})
        torrent_id = status.get("torrent_id")
        if torrent_id is None or not self.api_key:
            return False
        torrent_path = Path(meta.base_dir) / "tmp" / str(meta.uuid) / f"[{self.tracker}].torrent"
        try:
            downloaded = await self.common.download_tracker_torrent(
                meta,
                self.tracker,
                headers=self._headers(meta),
                params={"action": "download", "id": str(torrent_id)},
                downurl=f"{self.base_url}/ajax.php",
            )
            if not downloaded:
                return False
            content = torrent_path.read_bytes()
            decoded = cast(Any, bencodepy).decode(content) if content.startswith(b"d") else None
        except (OSError, bencodepy.BencodeDecodeError) as error:
            logger.warning(f"{self.tracker}: [yellow]could not use the site torrent; seeding the local torrent: {error}[/yellow]")
            return False
        if not isinstance(decoded, dict) or b"info" not in decoded:
            logger.warning(f"{self.tracker}: [yellow]Orpheus did not return a torrent file; seeding the local torrent.[/yellow]")
            return False
        comment = decoded.get(b"comment", b"")
        status["torrent_link"] = comment.decode("utf-8", "replace") if isinstance(comment, bytes) and comment else f"{self.torrent_url}{torrent_id}"
        status["torrent_source"] = "site"
        return True

    async def _write_torrent_comment(self, meta: Meta) -> None:
        """Put the new torrent's link in the comment of the torrent the client seeds.

        The uploaded torrent is created locally with an empty comment.  The
        site does not change its info dictionary, so writing the link keeps the
        info hash and lets later runs recognise the Orpheus ID from the client.
        """
        status = meta.tracker_status.setdefault(self.tracker, {})
        torrent_id, group_id = status.get("torrent_id"), status.get("group_id")
        if torrent_id is None:
            return
        link = f"{self.base_url}/torrents.php?id={group_id}&torrentid={torrent_id}" if group_id is not None else f"{self.torrent_url}{torrent_id}"
        try:
            await self.common.create_torrent_ready_to_seed(meta, self.tracker, self.source_flag, self.announce_url, link)
        except Exception as error:  # the upload already succeeded; never fail it here
            logger.warning(f"{self.tracker}: [yellow]could not write the torrent link into the client torrent: {error}[/yellow]")
            return
        status["torrent_link"] = link

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
        fill = result_dict.get("fillRequest")
        if isinstance(fill, dict):
            status["fill_request"] = fill
            if "requestId" not in fill:
                warnings.append(f"Request fill failed: {cast(dict[str, Any], fill).get('error', fill)}")
        if any(item.get("trumpable") for item in cast(list[dict[str, Any]], status.get("dupe_assessment", []))):
            warnings.append("This upload trumps an existing torrent; report the old torrent with a link to the new one (rule 2.2.3).")
        if warnings:
            status["warnings"] = warnings
            status["status_message"] = f"Upload accepted by Orpheus. Warnings: {' | '.join(warnings)}"
            logger.warning(f"{self.tracker}: [yellow]upload accepted with warning(s): {' | '.join(warnings)}[/yellow]")
        else:
            status["status_message"] = "Upload accepted by Orpheus."
        return True

    # ------------------------------------------------------------------
    # Upload form
    # ------------------------------------------------------------------

    def build_upload_payload(self, meta: Meta, release: MusicRelease) -> dict[str, str | list[str] | list[int] | int]:
        media = str(release.get("media", ""))
        if not media:
            raise ValueError("Orpheus media/source must be provided; the analyzer will not guess it.")
        image_url = self._cover_url(meta)
        if len(release.formats) != 1:
            raise ValueError("Orpheus uploads must contain exactly one audio format.")
        format_name = next(iter(release.formats))
        bitrate, other_bitrate, vbr = self._encoding(release, format_name)
        credits = self._artist_credits(meta, release)
        edition = resolve_orpheus_edition(release)
        tags, unofficial, dropped = self._tags(release)
        if unofficial or dropped:
            meta.tracker_status.setdefault(self.tracker, {})["tag_review"] = {"unofficial": unofficial, "dropped": dropped}
        # Orpheus stores release information only in the remaster_* fields
        # (``record_label``/``catalogue_number``/``remaster`` are ignored by
        # the upload handler).  An Unknown Release sends no edition fields.
        payload: dict[str, str | list[str] | list[int] | int] = {
            "album_desc": self._album_description(release),
            "artists[]": [name for name, _ in credits],
            "bitrate": bitrate,
            "format": format_name,
            "image": image_url,
            "importance[]": [role for _, role in credits],
            "media": media,
            "release_desc": self._release_description(release, meta),
            "releasetype": self.release_types.get(str(release.get("release_type", "Unknown")), 21),
            "submit": 1,
            "tags": tags,
            "title": self._upload_title(meta, release),
            "type": 0,
            "vbr": int(vbr),
            "year": str(release.get("year", "")),
        }
        if edition.unknown:
            payload["unknown"] = 1
        else:
            payload["remaster_year"] = edition.year
            payload["remaster_title"] = edition.title
            payload["remaster_record_label"] = edition.label
            payload["remaster_catalogue_number"] = edition.catalogue_number
        if other_bitrate:
            payload["other_bitrate"] = other_bitrate
        # Gazelle reads these checkboxes with isset(): sending them at all,
        # even as 0, marks the upload as scene/showcase.
        if meta.scene:
            payload["scene"] = 1
        if meta.music_showcase:
            payload["vanity_house"] = 1
        return {key: value for key, value in payload.items() if value not in ("", None, [])}

    def _tags(self, release: MusicRelease) -> tuple[str, list[str], list[str]]:
        """Return comma-separated Orpheus tags within the server's 200 characters."""
        tags, unofficial, dropped = orpheus_tags(cast(list[str], release.get("genres", []) or []))
        selected: list[str] = []
        for tag in tags:
            if len(",".join([*selected, tag])) > self.max_tag_length:
                break
            selected.append(tag)
        return ",".join(selected), unofficial, dropped

    @classmethod
    def _parse_role_overrides(cls, value: Any) -> list[tuple[str, int]]:
        """Parse ``"Name=role; Other=guest"`` CLI credits."""
        credits: list[tuple[str, int]] = []
        for item in re.split(r"\s*;\s*", str(value or "")):
            name, separator, role = item.rpartition("=")
            role_id = cls.artist_roles.get(role.strip().casefold().replace(" ", ""))
            if separator and name.strip() and role_id:
                credits.append((name.strip(), role_id))
            elif item.strip():
                logger.warning(f"[yellow]ORPHEUS: ignoring artist role '{escape(item)}'; use Name=main|guest|composer|conductor|dj|remixer|producer|arranger.[/yellow]")
        return credits

    @classmethod
    def _artist_credits(cls, meta: Meta, release: MusicRelease) -> list[tuple[str, int]]:
        """Build ``(name, importance)`` credits for the multiple-artist form.

        Main artists come from the release; a "feat." part of that credit
        ("A feat. B") becomes a guest instead of part of the main name.
        Guests also come from "feat." credits in track artists, and a named
        "(X Remix)" in the release or track titles makes X the remixer.
        Composers and conductors are added only for classical music and
        soundtracks, where Orpheus uses those roles.
        """
        main: list[str] = []
        featured: list[str] = []
        for credit in cls._artists(release):
            name, guests = cls._split_featuring(credit)
            if name and name not in main:
                main.append(name)
            featured.extend(guests)
        credits: list[tuple[str, int]] = [(name, 1) for name in main]
        main_keys = {cls._normalise_artist_name(name) for name in main}
        release_type = str(release.get("release_type", ""))
        tags, _, _ = orpheus_tags(cast(list[str], release.get("genres", []) or []))
        classical = release_type == "Soundtrack" or bool(cls.classical_tags.intersection(tags))

        def add(name: str, role: int) -> None:
            clean = name.strip()
            if not clean or (role == 2 and cls._normalise_artist_name(clean) in main_keys):
                return
            if all(not (cls._normalise_artist_name(existing) == cls._normalise_artist_name(clean) and existing_role == role) for existing, existing_role in credits):
                credits.append((clean, role))

        remixers = [name for title in (release.get("album", ""), *(track.title for track in release.tracks)) for name in cls._title_remixers(title)]
        remixer_keys = {cls._normalise_artist_name(name) for name in remixers}
        for name in remixers:
            if cls._normalise_artist_name(name) not in main_keys:
                add(name, 3)
        for guest in featured:
            if cls._normalise_artist_name(guest) not in remixer_keys:
                add(guest, 2)
        for track in release.tracks:
            for guest in cls._split_featuring(track.artist)[1]:
                if cls._normalise_artist_name(guest) not in remixer_keys:
                    add(guest, 2)
            if classical:
                for composer in track.tags.get("composer", []):
                    add(composer, 4)
                for conductor in track.tags.get("conductor", []):
                    add(conductor, 5)
            if release_type == "Remix":
                for remixer in track.tags.get("remixer", []):
                    add(remixer, 3)
            if release_type == "DJ Mix":
                for dj in track.tags.get("djmixer", []):
                    add(dj, 6)
        for name, role in cls._parse_role_overrides(meta.music_artist_roles):
            credits = [(existing, existing_role) for existing, existing_role in credits if cls._normalise_artist_name(existing) != cls._normalise_artist_name(name)]
            credits.append((name, role))
        if not any(role == 1 for _, role in credits):
            credits = [(name, 1) for name in main] + credits
        return credits

    _FEATURING = re.compile(r"\s+(?:feat(?:uring)?\.?|ft\.)\s+", re.I)
    _REMIX_CREDIT = re.compile(r"[(\[]\s*([^()\[\]]+?)\s+(?:remix|rework)\s*[)\]]", re.I)
    _GENERIC_MIX_WORDS = frozenset(
        {"extended", "original", "club", "radio", "single", "album", "instrumental", "dub", "vip", "official", "acoustic", "short", "long", "edit", "the"}
    )

    @classmethod
    def _split_featuring(cls, credit: str) -> tuple[str, list[str]]:
        """Split ``"A feat. B & C"`` into ``("A", ["B", "C"])``."""
        parts = cls._FEATURING.split(str(credit or "").strip(), maxsplit=1)
        if len(parts) == 1:
            return parts[0].strip(), []
        guests = [guest.strip() for guest in re.split(r"\s*(?:,|&|\band\b)\s*", parts[1]) if guest.strip()]
        return parts[0].strip(), guests

    @classmethod
    def _title_remixers(cls, title: str) -> list[str]:
        """Return remixer names from titles such as ``"Song (Name Remix)"``."""
        names: list[str] = []
        for match in cls._REMIX_CREDIT.finditer(str(title or "")):
            name = match.group(1).strip()
            if not name or set(re.findall(r"[a-z0-9]+", name.casefold())) <= cls._GENERIC_MIX_WORDS:
                continue
            for part in re.split(r"\s*(?:,|&|\band\b)\s*", name):
                if part.strip() and part.strip() not in names:
                    names.append(part.strip())
        return names

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

    @classmethod
    def _cover_url(cls, meta: Meta) -> str:
        """Return an allowed optional Orpheus artwork URL, never a local path.

        The form accepts optional HTTP(S) artwork, but disallows Discogs,
        Facebook CDN, Photobucket and ptpimg hosts.  Invalid or disallowed
        URLs are omitted rather than being submitted as a local path.
        """
        value = str(meta.artwork_url or "").strip()
        parsed = urlparse(value)
        host = (parsed.hostname or "").casefold()
        if len(value) > 255:
            return ""
        if parsed.scheme in {"http", "https"} and host and not any(host == banned or host.endswith(f".{banned}") for banned in cls.banned_image_hosts):
            return value
        return ""

    @classmethod
    def _encoding(cls, release: MusicRelease, format_name: str) -> tuple[str, str, bool]:
        tracks = release.tracks
        if format_name == "FLAC":
            return ("24bit Lossless" if any((track.bit_depth or 0) > 16 for track in tracks) else "Lossless", "", False)
        if format_name == "MP3":
            presets = {lame_preset(track.encoder_settings) for track in tracks}
            if len(presets) == 1 and None not in presets:
                return cast(str, next(iter(presets))), "", False
        average = round(sum(track.bitrate or 0 for track in tracks) / max(len(tracks), 1) / 1000)
        mode = next((track.bitrate_mode for track in tracks if track.bitrate_mode), None)
        if mode in {"CBR", "ABR"} and average in cls.form_bitrates:
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
    def _technical_label(track: Any) -> str:
        return f"{track.bit_depth or '?'}-bit / {(track.sample_rate or 0) / 1000:g} kHz / {track.channels or '?'}ch"

    @classmethod
    def _lineage_text(cls, meta: Meta, release: MusicRelease) -> str:
        """Read lineage from ``--music-lineage`` or a lineage text file."""
        candidates: list[Path] = []
        if str(meta.music_lineage or "").strip():
            candidates.append(Path(str(meta.music_lineage)).expanduser())
        candidates.extend(release.path / item for item in release.auxiliary.lineage if item.lower().endswith((".txt", ".md")))
        for candidate in candidates:
            try:
                if candidate.is_file():
                    text = candidate.read_text(encoding="utf-8", errors="replace").strip()
                    if text:
                        return text[: cls.max_lineage_characters]
            except OSError as error:
                logger.warning(f"[yellow]ORPHEUS: could not read lineage file {escape(str(candidate))}: {error}[/yellow]")
        return ""

    @classmethod
    def _release_description(cls, release: MusicRelease, meta: Meta | None = None) -> str:
        variants = sorted({cls._technical_label(track) for track in release.tracks})
        parts = [f"Technical audio: {', '.join(variants)}."] if variants else []
        if len(variants) > 1:
            # Rule 2.1.5.2: describe which tracks differ in a hybrid release.
            for variant in variants:
                numbers = [
                    f"{track.disc_number}.{track.track_number}" if release.disc_count > 1 else str(track.track_number or Path(track.relative_path).stem)
                    for track in release.tracks
                    if cls._technical_label(track) == variant
                ]
                parts.append(f"{variant}: tracks {', '.join(numbers)}")
        encoders = sorted(
            {f"{track.encoder_info} {track.encoder_settings}".strip() for track in release.tracks if track.format == "MP3" and (track.encoder_info or track.encoder_settings)}
        )
        if encoders:
            parts.append(f"Encoder: {', '.join(encoders)}.")
        if release.get("retail_date"):
            parts.append(f"Retail date: {release.get('retail_date')}.")
        if release.get("store_url"):
            parts.append(f"[url={release.get('store_url')}]Store listing[/url]")
        if release.auxiliary.cues:
            parts.append("Cue sheet included.")
        if release.auxiliary.logs:
            parts.append("Rip log included.")
        if meta is not None:
            # Rule 1.3.1: scene credit belongs in the release description only.
            if meta.scene and str(meta.scene_name or "").strip():
                parts.append(f"Scene release: {meta.scene_name}")
            if str(meta.music_watermark or "").strip():
                parts.append(f"[b]Watermark / voice-over:[/b] {meta.music_watermark}")
            lineage = cls._lineage_text(meta, release)
            if lineage:
                parts.append(f"[b]Lineage[/b]\n[pre]{lineage}[/pre]")
        return "\n".join(parts)
