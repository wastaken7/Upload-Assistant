"""Local, non-destructive music release analysis.

Only metadata is read.  No tag, filename, folder or audio content is changed.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

import mutagen

from src.media_extensions import ARTWORK_EXTENSIONS, AUDIO_EXTENSIONS
from src.music.models import AudioTrack, MetadataSource, MusicRelease

LINEAGE_NAMES = ("lineage", "equipment", "transfer", "rip", "source")
DISC_RE = re.compile(r"(?:^|[ _.-])(?:cd|disc|disk)[ _.-]?(\d{1,2})(?:$|[ _.-])", re.I)
YEAR_RE = re.compile(r"(?:^|[^0-9])((?:19|20)\d{2})(?:[^0-9]|$)")
LEADING_YEAR_RE = re.compile(r"^\s*[\[(]?\s*((?:19|20)\d{2})\b")
EDITION_RE = re.compile(r"(?:\[|\()([^\]\)]*(?:deluxe|remaster|anniversary|reissue|expanded|edition)[^\]\)]*)(?:\]|\))", re.I)
EDITION_WITH_YEAR_RE = re.compile(r"(?:\[|\()\s*((?:19|20)\d{2})[\s,.-]+([^\]\)]+)(?:\]|\))", re.I)
BRACKET_RE = re.compile(r"\[([^\]]+)\]|\{([^\}]+)\}")
# Subsequent catalogue components must have an actual separator.  Allowing an
# optional separator before another ``\d+`` creates many equivalent ways to
# partition a long run of digits and can backtrack exponentially.
CATALOGUE_RE = re.compile(r"\b(?:[A-Z]{1,8}[- ]?\d{2,}(?:[- ]\d+)*|\d{1,2}[- ]\d{3,}(?:[- ]\d+)*|\d{5,})\b", re.I)


def _clean(value: Any) -> str:
    # Word joiners and other Unicode format controls are invisible but make
    # tracker titles compare differently.  Preserve visible artistic casing.
    text = "".join(char for char in str(value or "").replace("\x00", " ") if unicodedata.category(char) != "Cf")
    return re.sub(r"\s+", " ", text).strip()


def _first(tags: dict[str, list[str]], *keys: str) -> str:
    for key in keys:
        for candidate in (key, key.upper(), key.lower()):
            values = tags.get(candidate)
            if values:
                return _clean(values[0])
    return ""


def _values(tags: dict[str, list[str]], *keys: str) -> list[str]:
    """Return all values for equivalent tag keys, preserving tag order."""
    values: list[str] = []
    for key in keys:
        for candidate in (key, key.upper(), key.lower()):
            for value in tags.get(candidate, []):
                cleaned = _clean(value)
                if cleaned and cleaned not in values:
                    values.append(cleaned)
    return values


def _split_main_artists(values: list[str]) -> list[str]:
    """Split only the common explicit collaboration separator.

    Tags with multiple values remain authoritative.  `` & `` is split only
    when it has whitespace around it, which avoids damaging names such as
    AC/DC.  Ambiguous aliases are intentionally left untouched.
    """
    artists: list[str] = []
    for value in values:
        parts = re.split(r"\s+&\s+", value)
        for part in parts:
            cleaned = _clean(part)
            if cleaned and cleaned not in artists:
                artists.append(cleaned)
    return artists


def _number(value: str) -> int | None:
    match = re.search(r"\d+", value or "")
    return int(match.group()) if match else None


def _format_for(path: Path, audio: Any) -> tuple[str, str]:
    ext = path.suffix.lower()
    class_name = audio.__class__.__name__.lower()
    if ext == ".flac" or "flac" in class_name:
        return "FLAC", "FLAC"
    if ext == ".mp3" or "mp3" in class_name:
        return "MP3", "MP3"
    if ext in {".m4a", ".aac"} or "mp4" in class_name or "aac" in class_name:
        return "AAC", "AAC"
    if ext == ".ogg" or "vorbis" in class_name:
        return "Ogg Vorbis", "Vorbis"
    if ext == ".ac3":
        return "AC3", "AC-3"
    if ext == ".dts":
        return "DTS", "DTS"
    return ext.removeprefix(".").upper(), audio.__class__.__name__


def _bitrate_mode(info: Any) -> str | None:
    mode = getattr(info, "bitrate_mode", None)
    if mode is not None:
        text = str(mode).upper()
        if "VBR" in text or "VARIABLE" in text:
            return "VBR"
        if "ABR" in text or "AVERAGE" in text:
            return "ABR"
        if "CBR" in text or "CONSTANT" in text:
            return "CBR"
    return None


class MusicReleaseAnalyzer:
    """Build a normalized release from tags, sidecars and file structure."""

    def analyze(self, path: str | Path) -> MusicRelease:
        supplied = Path(path).expanduser()
        root = supplied if supplied.is_dir() else supplied.parent
        release = MusicRelease(root=str(root.resolve()))
        if not supplied.exists():
            release.warnings.append(f"Release path does not exist: {supplied}")
            return release

        files = [supplied] if supplied.is_file() else sorted((entry for entry in supplied.rglob("*") if entry.is_file()), key=lambda entry: str(entry).casefold())
        for file in files:
            if file.suffix.lower() in AUDIO_EXTENSIONS:
                track = self._read_track(file, root)
                if track:
                    release.tracks.append(track)
            else:
                self._classify_auxiliary(release, file, root)

        self._derive_release_fields(release, supplied.name)
        return release

    def _read_track(self, path: Path, root: Path) -> AudioTrack | None:
        try:
            audio = mutagen.File(path, easy=True)
            technical = mutagen.File(path)
        except mutagen.MutagenError, OSError:
            return None
        if audio is None and technical is None:
            return None
        source = audio or technical
        if source is None:
            return None
        tags: dict[str, list[str]] = {}
        for key, value in (getattr(audio, "tags", None) or {}).items():
            values = value if isinstance(value, list) else [value]
            tags[str(key)] = [_clean(item) for item in values if _clean(item)]

        info = getattr(technical or source, "info", None)
        format_name, codec = _format_for(path, source)
        tagged_disc = _number(_first(tags, "discnumber", "disknumber", "disc"))
        folder_disc = self._disc_from_path(path, root)
        # Release tags are frequently copied wholesale to bonus discs.  A clear
        # ``Disc 2`` folder is stronger structural evidence than a stale tag of 1.
        disc = folder_disc if folder_disc and folder_disc != tagged_disc else tagged_disc or folder_disc
        return AudioTrack(
            path=str(path.resolve()),
            relative_path=str(path.relative_to(root)),
            format=format_name,
            codec=codec,
            bitrate=getattr(info, "bitrate", None),
            bitrate_mode=_bitrate_mode(info),
            bit_depth=getattr(info, "bits_per_sample", None),
            sample_rate=getattr(info, "sample_rate", None),
            channels=getattr(info, "channels", None),
            duration=getattr(info, "length", None),
            disc_number=disc,
            track_number=_number(_first(tags, "tracknumber", "track")),
            artist=_first(tags, "artist", "performer"),
            album_artist=_first(tags, "albumartist", "album artist"),
            album=_first(tags, "album"),
            title=_first(tags, "title"),
            date=_first(tags, "date", "year", "originaldate"),
            label=_first(tags, "organization", "label", "publisher"),
            catalogue_number=_first(tags, "catalognumber", "cataloguenumber", "catalog", "catalogue"),
            genre=tags.get("genre", []),
            isrc=_first(tags, "isrc"),
            tags=tags,
        )

    def _classify_auxiliary(self, release: MusicRelease, path: Path, root: Path) -> None:
        relative = str(path.relative_to(root))
        ext, stem = path.suffix.lower(), path.stem.lower()
        if ext == ".log":
            release.auxiliary.logs.append(relative)
        elif ext == ".cue":
            release.auxiliary.cues.append(relative)
        elif ext == ".nfo":
            release.auxiliary.nfos.append(relative)
        elif ext == ".sfv":
            release.auxiliary.sfvs.append(relative)
        elif ext in {".m3u", ".m3u8"}:
            release.auxiliary.playlists.append(relative)
        elif ext in ARTWORK_EXTENSIONS:
            (release.auxiliary.scans if any(word in stem for word in ("scan", "booklet", "back", "tray", "obi", "inlay")) else release.auxiliary.artwork).append(relative)
        elif ext in {".txt", ".md", ".pdf"} and any(word in stem for word in LINEAGE_NAMES):
            release.auxiliary.lineage.append(relative)
        else:
            release.auxiliary.other.append(relative)

    @staticmethod
    def _disc_from_path(path: Path, root: Path) -> int | None:
        for parent in (path.parent, *path.parents):
            if parent == root.parent:
                break
            match = DISC_RE.search(parent.name)
            if match:
                return int(match.group(1))
        return None

    def _derive_release_fields(self, release: MusicRelease, folder_name: str) -> None:
        if not release.tracks:
            release.warnings.append("No supported audio files found")
            return
        # A leading folder year conventionally denotes the original album group;
        # audio DATE tags normally identify the particular release in hand.
        self._derive_from_directory(release, folder_name)
        self._set_artists(release)
        self._set_consensus(release, "album", [self._clean_album_tag(track.album) for track in release.tracks], MetadataSource.FILE_TAG, 1.0)
        tag_years = [track.date[:4] for track in release.tracks if re.fullmatch(r"(?:19|20)\d{2}.*", track.date)]
        directory_year = release.get("year") if release.fields.get("year", None) and release.fields["year"].source == MetadataSource.DIRECTORY else ""
        # When the path explicitly identifies an edition but does not supply a
        # leading original year (for example, ``Coda [2015 Deluxe Edition]``),
        # the tag DATE is the release/edition date, not reliable evidence for
        # the album group's initial year.  Leave ``year`` absent so the normal
        # MUSIC prompt asks for the required original year.
        if not directory_year and not (release.get("edition") or release.get("edition_year")):
            self._set_consensus(release, "year", tag_years, MetadataSource.FILE_TAG, 1.0)
        # A date, imprint and catalogue number identify a *release*.  Per the
        # Orpheus edition guidelines, none establishes a distinct edition by
        # itself; only explicit edition information belongs in ``edition_*``.
        self._set_consensus(release, "release_year", tag_years, MetadataSource.FILE_TAG, 0.9)
        self._set_consensus(release, "release_label", [track.label for track in release.tracks], MetadataSource.FILE_TAG, 0.95)
        self._set_consensus(release, "release_catalogue_number", [track.catalogue_number for track in release.tracks], MetadataSource.FILE_TAG, 0.95)
        # Legacy neutral aliases retain compatibility for consumers other than
        # the Orpheus adapter; tracker mapping uses the explicit release names.
        self._set_consensus(release, "label", [track.label for track in release.tracks], MetadataSource.FILE_TAG, 0.95)
        self._set_consensus(release, "catalogue_number", [track.catalogue_number for track in release.tracks], MetadataSource.FILE_TAG, 0.95)
        genres = sorted({genre for track in release.tracks for genre in track.genre if genre})
        release.set_field("genres", genres, MetadataSource.FILE_TAG, 0.8)
        release.set_field("format", ", ".join(sorted(release.formats)), MetadataSource.INFERRED, 1.0)
        release.set_field("track_count", len(release.tracks), MetadataSource.INFERRED, 1.0)
        release.set_field("disc_count", release.disc_count, MetadataSource.INFERRED, 1.0)
        release.set_field("has_log", bool(release.auxiliary.logs), MetadataSource.AUXILIARY, 1.0)
        release.set_field("has_cue", bool(release.auxiliary.cues), MetadataSource.AUXILIARY, 1.0)
        release.set_field("has_nfo", bool(release.auxiliary.nfos), MetadataSource.AUXILIARY, 1.0)
        release.set_field("has_sfv", bool(release.auxiliary.sfvs), MetadataSource.AUXILIARY, 1.0)
        release.set_field("has_playlist", bool(release.auxiliary.playlists), MetadataSource.AUXILIARY, 1.0)
        release.set_field(
            "scene",
            bool(release.auxiliary.nfos) and bool(re.search(r"[-_][a-z0-9]{2,}(?:_[a-z0-9]+)?$", folder_name, re.I)),
            MetadataSource.INFERRED,
            0.7,
        )
        self._extract_nfo_metadata(release)
        self._inspect_playlists(release)
        self._inspect_sfvs(release)
        self._infer_media_from_logs(release)
        self._derive_release_type(release)

    @staticmethod
    def _read_sidecar(path: Path) -> str:
        """Read a small text sidecar using common scene encodings."""
        try:
            data = path.read_bytes()[:262_144]
        except OSError:
            return ""
        for encoding in ("utf-8-sig", "utf-16", "cp1252", "latin-1"):
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                continue
        return ""

    def _extract_nfo_metadata(self, release: MusicRelease) -> None:
        """Use structured scene NFO fields only as lower-priority evidence."""
        values: dict[str, list[str]] = {}
        for relative in release.auxiliary.nfos:
            text = self._read_sidecar(release.path / relative)
            for line in text.splitlines():
                # Scene NFO box art often uses a legacy encoding around an
                # otherwise ASCII key/value pair.  Labels are ASCII by design;
                # discarding the artwork bytes avoids treating prose such as
                # "quality or value" as metadata.
                line = line.encode("ascii", "ignore").decode("ascii")
                match = re.search(
                    r"(?:^|\s)(artist|album|label|publisher|genre|source|quality|url|www|retail\s*date|rel\s*date|release\s*date|rip\s*date)\s*[.:|]+\s*(.+?)\s*$",
                    line,
                    re.I,
                )
                if not match:
                    continue
                key, value = match.group(1).casefold().replace(" ", "_"), _clean(match.group(2).strip(" |.:-"))
                if value and value not in values.setdefault(key, []):
                    values[key].append(value)

        def first(*keys: str) -> str:
            return next((value for key in keys for value in values.get(key, []) if value), "")

        release.set_field("artist", first("artist"), MetadataSource.AUXILIARY, 0.7)
        release.set_field("album", first("album"), MetadataSource.AUXILIARY, 0.7)
        release.set_field("release_label", first("label", "publisher"), MetadataSource.AUXILIARY, 0.75)
        release.set_field("label", first("label", "publisher"), MetadataSource.AUXILIARY, 0.75)
        genre = first("genre")
        if genre:
            release.set_field("genres", [part.strip() for part in re.split(r"[,;/]", genre) if part.strip()], MetadataSource.AUXILIARY, 0.75)
        source = first("source").upper()
        if source.startswith("WEB"):
            release.set_field("media", "WEB", MetadataSource.AUXILIARY, 0.75)
        store_url = first("url", "www")
        if re.match(r"https?://", store_url, re.I):
            release.set_field("store_url", store_url, MetadataSource.AUXILIARY, 0.75)
            release.external_ids["store_url"] = store_url
        retail_date = first("retail_date", "rel_date", "release_date")
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", retail_date):
            release.set_field("retail_date", retail_date, MetadataSource.AUXILIARY, 0.8)
            release.set_field("release_year", retail_date[:4], MetadataSource.AUXILIARY, 0.8)
        rip_date = first("rip_date")
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", rip_date):
            release.set_field("rip_date", rip_date, MetadataSource.AUXILIARY, 0.7)
        quality = first("quality")
        if quality:
            release.set_field("nfo_quality", quality, MetadataSource.AUXILIARY, 0.7)
            bit_depth = re.search(r"\b(16|24)\s*bit\b", quality, re.I)
            sample_rate = re.search(r"\b(44\.1|48|88\.2|96|176\.4|192)\s*k(?:hz|hertz)\b", quality, re.I)
            if bit_depth:
                release.set_field("nfo_bit_depth", int(bit_depth.group(1)), MetadataSource.AUXILIARY, 0.7)
            if sample_rate:
                release.set_field("nfo_sample_rate", int(float(sample_rate.group(1)) * 1000), MetadataSource.AUXILIARY, 0.7)
            declared_depth = int(bit_depth.group(1)) if bit_depth else None
            declared_rate = int(float(sample_rate.group(1)) * 1000) if sample_rate else None
            if declared_depth and any(track.bit_depth and track.bit_depth != declared_depth for track in release.tracks):
                release.warnings.append("NFO bit depth conflicts with the audio stream metadata.")
            if declared_rate and any(track.sample_rate and track.sample_rate != declared_rate for track in release.tracks):
                release.warnings.append("NFO sample rate conflicts with the audio stream metadata.")

    def _inspect_playlists(self, release: MusicRelease) -> None:
        """Check playlist membership only; no playlist content is modified."""
        known = {Path(track.relative_path).name.casefold() for track in release.tracks}
        entries: list[str] = []
        for relative in release.auxiliary.playlists:
            for line in self._read_sidecar(release.path / relative).splitlines():
                value = line.strip()
                if value and not value.startswith("#"):
                    entries.append(Path(value.replace("\\", "/")).name.casefold())
        if entries:
            missing = sorted({entry for entry in entries if entry not in known})
            release.set_field("playlist_tracks", len(entries), MetadataSource.AUXILIARY, 0.9)
            release.set_field("playlist_missing_files", missing, MetadataSource.AUXILIARY, 0.9)
            if missing:
                release.warnings.append(f"Playlist references {len(missing)} file(s) not present in the release.")

    def _inspect_sfvs(self, release: MusicRelease) -> None:
        """Validate SFV membership without the expensive/destructive hash pass."""
        known = {Path(track.relative_path).name.casefold() for track in release.tracks}
        entries: list[str] = []
        for relative in release.auxiliary.sfvs:
            for line in self._read_sidecar(release.path / relative).splitlines():
                match = re.match(r"(.+?)\s+[A-F0-9]{8}\s*$", line.strip(), re.I)
                if match:
                    entries.append(Path(match.group(1)).name.casefold())
        if entries:
            missing = sorted({entry for entry in entries if entry not in known})
            release.set_field("sfv_entries", len(entries), MetadataSource.AUXILIARY, 0.9)
            release.set_field("sfv_missing_files", missing, MetadataSource.AUXILIARY, 0.9)
            if missing:
                release.warnings.append(f"SFV references {len(missing)} file(s) not present in the release.")

    @staticmethod
    def _set_artists(release: MusicRelease) -> None:
        per_track: list[tuple[str, ...]] = []
        for track in release.tracks:
            values = _values(track.tags, "albumartist", "album artist") or _values(track.tags, "artist", "performer")
            artists = _split_main_artists(values or [track.album_artist or track.artist])
            if artists:
                per_track.append(tuple(artists))
        if not per_track:
            return
        selected, count = Counter(per_track).most_common(1)[0]
        artists = list(selected)
        release.set_field("artists", artists, MetadataSource.FILE_TAG, count / len(per_track))
        release.set_field("artist", " & ".join(artists), MetadataSource.FILE_TAG, count / len(per_track))
        unique = sorted({" & ".join(item) for item in per_track})
        if len(unique) > 1:
            release.conflicts["artist"] = unique

    @staticmethod
    def _set_consensus(release: MusicRelease, name: str, values: list[str], source: MetadataSource, confidence: float) -> None:
        cleaned = [_clean(value) for value in values if _clean(value)]
        if not cleaned:
            return
        selected, count = Counter(cleaned).most_common(1)[0]
        release.set_field(name, selected, source, confidence * count / len(cleaned))
        unique = sorted(set(cleaned))
        if len(unique) > 1:
            release.conflicts[name] = unique

    @staticmethod
    def _clean_album_tag(value: str) -> str:
        """Remove obvious scene source/format suffixes from otherwise valid tags."""
        return re.sub(r"(?:[ _.-]+)(?:WEB|CD|FLAC|MP3|AAC)$", "", _clean(value), flags=re.I).strip()

    @staticmethod
    def _derive_from_directory(release: MusicRelease, name: str) -> None:
        normalized = name.replace("_", " ")
        match = LEADING_YEAR_RE.search(normalized)
        if match:
            release.set_field("year", match.group(1), MetadataSource.DIRECTORY, 1.0)
        if not release.get("artist") or not release.get("album"):
            name_without_metadata = re.sub(r"(?:\s*(?:\[[^\]]+\]|\{[^\}]+\}))*$", "", normalized)
            match = re.search(r"(?:^|\d{4}\s*-?\s*)(.+?)\s+-\s+(.+?)$", name_without_metadata)
            if match:
                release.set_field("artist", match.group(1).strip(), MetadataSource.DIRECTORY, 0.55)
                release.set_field("album", match.group(2).strip(), MetadataSource.DIRECTORY, 0.55)
        upper = normalized.upper()
        for media, markers in {"WEB": ("WEB", "DIGITAL"), "CD": (" CD", "CD-", "EAC"), "Vinyl": ("VINYL", "LP"), "SACD": ("SACD",), "BD": ("BLURAY", "BLU-RAY")}.items():
            if any(marker in upper for marker in markers):
                release.set_field("media", media, MetadataSource.DIRECTORY, 0.45)
                break
        edition_with_year = EDITION_WITH_YEAR_RE.search(normalized)
        edition_markers = ("remaster", "deluxe", "reissue", "expanded", "anniversary", "bonus tracks")
        if edition_with_year and any(word in edition_with_year.group(2).casefold() for word in edition_markers):
            release.set_field("edition_year", edition_with_year.group(1), MetadataSource.DIRECTORY, 0.95)
            release.set_field("release_year", edition_with_year.group(1), MetadataSource.DIRECTORY, 0.95)
            detail = edition_with_year.group(2).strip(" ,.-")
            release.set_field("edition", detail, MetadataSource.DIRECTORY, 0.65)
        elif edition_with_year:
            detail = edition_with_year.group(2).strip(" ,.-")
            release.set_field("release_year", edition_with_year.group(1), MetadataSource.DIRECTORY, 0.95)
            catalogue = CATALOGUE_RE.search(detail)
            if catalogue:
                release.set_field("release_catalogue_number", catalogue.group(0), MetadataSource.DIRECTORY, 0.65)
        edition = EDITION_RE.search(normalized)
        if edition and not edition_with_year:
            detail = edition.group(1).strip()
            # Regional pressings are release information.  The guide requires
            # the country name (for example, Japan), not a fabricated edition.
            if re.search(r"\b(?:Japan|US|USA|UK|Europe|Germany|France|Canada|Australia)\b", detail, re.I):
                release.set_field("release_title", detail, MetadataSource.DIRECTORY, 0.6)
            else:
                release.set_field("edition", detail, MetadataSource.DIRECTORY, 0.55)

        # Common WEB naming places release information in adjacent brackets,
        # for example ``[2014 WEB FLAC][Label Name][886444460446]``.  A WEB
        # release date, label and catalogue number do not by themselves prove
        # an audio-distinct edition, so retain them as ``release_*`` fields.
        brackets = [_clean(value) for match in BRACKET_RE.findall(normalized) for value in match if value]
        source_markers = ("WEB", "DIGITAL", "CD", "VINYL", "LP", "SACD", "BLU-RAY", "BLURAY")
        format_markers = ("FLAC", "MP3", "AAC", "ALAC", "M4A", "OGG", "OPUS", "WAV", "AIFF")
        edition_markers_upper = tuple(marker.upper() for marker in edition_markers)
        edition_bracket_indexes: set[int] = set()
        for index, detail in enumerate(brackets):
            year_match = LEADING_YEAR_RE.search(detail)
            upper_detail = detail.upper()
            if year_match and any(marker in upper_detail for marker in (*source_markers, *format_markers, *edition_markers_upper)):
                if any(marker in upper_detail for marker in (*source_markers, *format_markers)):
                    release.set_field("release_year", year_match.group(1), MetadataSource.DIRECTORY, 0.95)
                edition_bracket_indexes.add(index)
        for index, detail in enumerate(brackets):
            if index in edition_bracket_indexes:
                continue
            if CATALOGUE_RE.fullmatch(detail):
                release.set_field("release_catalogue_number", detail, MetadataSource.DIRECTORY, 0.65)
                release.set_field("directory_catalogue_number", detail, MetadataSource.DIRECTORY, 0.7)
                continue
            catalogue = CATALOGUE_RE.search(detail)
            if catalogue:
                release.set_field("release_catalogue_number", catalogue.group(0), MetadataSource.DIRECTORY, 0.65)
                release.set_field("directory_catalogue_number", catalogue.group(0), MetadataSource.DIRECTORY, 0.7)
                # A scene-style block may combine imprint, catalogue and
                # medium, e.g. ``{Roc-A-Fella B001219802 CD}``.
                label = re.sub(r"\b(?:CD|WEB|DIGITAL|VINYL|LP|SACD|DVD|BD|BLU-?RAY)\b", "", CATALOGUE_RE.sub("", detail), flags=re.I)
                label = re.sub(r"[|,;/]+", " ", label)
                label = re.sub(r"^[\s._-]+|[\s._-]+$", "", label)
                if label and re.search(r"[A-Za-z]", label):
                    release.set_field("release_label", label, MetadataSource.DIRECTORY, 0.6)
                continue
            upper_detail = detail.upper()
            if not any(marker in upper_detail for marker in (*source_markers, *format_markers, *edition_markers_upper)) and re.search(r"[A-Za-z]", detail):
                release.set_field("release_label", detail, MetadataSource.DIRECTORY, 0.6)

    @staticmethod
    def _infer_media_from_logs(release: MusicRelease) -> None:
        """Identify a CD rip from a rip log, never from a bare .log suffix."""
        if release.get("media") or not release.auxiliary.logs:
            return
        root = release.path
        for relative in release.auxiliary.logs:
            try:
                data = (root / relative).read_bytes()[:262_144]
            except OSError:
                continue
            text = data.decode("utf-16", errors="ignore") if data.startswith((b"\xff\xfe", b"\xfe\xff")) or b"\x00" in data[:256] else data.decode("utf-8", errors="ignore")
            if re.search(r"\b(?:Exact Audio Copy|X Lossless Decoder|CUERipper|whipper|CD-DA|CD-ROM)\b", text, re.I):
                release.set_field("media", "CD", MetadataSource.AUXILIARY, 0.9)
                release.warnings.append("Source media inferred as CD from the rip log.")
                return

    @staticmethod
    def _derive_release_type(release: MusicRelease) -> None:
        album = str(release.get("album", "")).lower()
        count = len(release.tracks)
        # Track ARTIST tags credit performers on that specific song.  They are
        # not reliable evidence that the *release* is a compilation: a normal
        # artist album can feature a different guest on every track.  Prefer
        # ALBUMARTIST (including its aliases) for the release-level decision.
        album_artist_credits: set[tuple[str, ...]] = set()
        track_artists: set[str] = set()
        for track in release.tracks:
            album_artists = _split_main_artists(_values(track.tags, "albumartist", "album artist") or [track.album_artist])
            if album_artists:
                album_artist_credits.add(tuple(artist.casefold() for artist in album_artists))
            if track.artist:
                track_artists.add(track.artist.casefold())

        has_explicit_various_artists = any(credit in {"various artists", "various", "va", "v.a."} for artists in album_artist_credits for credit in artists)
        has_stable_album_artist = len(album_artist_credits) == 1 and not has_explicit_various_artists
        # Without ALBUMARTIST at all, many unrelated track artists are the
        # best remaining signal.  Do not apply this fallback when an explicit,
        # stable album artist exists.
        inferred_from_tracks = not album_artist_credits and len(track_artists) > max(3, count // 2)
        explicit_compilation = "compilation" in album
        # ``OST`` and ``live`` are release-type markers only as standalone
        # words.  A substring check would classify titles such as
        # ``NOSTALGIA`` as a soundtrack or ``Olive`` as a live album.
        if "soundtrack" in album or re.search(r"(?:^|[^\w])ost(?:$|[^\w])", album):
            value = "Soundtrack"
        elif re.search(r"\blive\b", album):
            value = "Live album"
        elif explicit_compilation or has_explicit_various_artists or len(album_artist_credits) > 1 or inferred_from_tracks:
            value = "Compilation"
            # Orpheus uses the multiple-artist feature for actual Various
            # Artists/VA compilations.  Do not overwrite a stable album-artist
            # credit merely because its tracks have featured performers.
            if has_explicit_various_artists or (not has_stable_album_artist and len(track_artists) > 3):
                # The Orpheus form explicitly requires its multiple-artist
                # feature instead of a literal "Various Artists" credit.
                # Keep the track-tag order and never synthesize an artist.
                compilation_artists: list[str] = []
                for track in release.tracks:
                    for artist in _split_main_artists(_values(track.tags, "artist", "performer") or [track.artist]):
                        if artist not in compilation_artists:
                            compilation_artists.append(artist)
                if compilation_artists:
                    release.set_field("artists", compilation_artists, MetadataSource.INFERRED, 1.0, force=True)
                    release.set_field("artist", " & ".join(compilation_artists), MetadataSource.INFERRED, 1.0, force=True)
        elif count == 1:
            value = "Single"
        elif "ep" in album.split() or 2 <= count <= 6:
            value = "EP"
        else:
            value = "Album"
        release.set_field("release_type", value, MetadataSource.INFERRED, 0.65)
