"""Generic and Orpheus-specific validation without mutating a release."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path, PurePath
from typing import ClassVar

from src.music.models import MetadataSource, MusicRelease


class ValidationLevel(StrEnum):
    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True)
class ValidationIssue:
    level: ValidationLevel
    code: str
    message: str


class MusicValidator:
    """Validates portable invariants; tracker subclasses add policy."""

    def validate(self, release: MusicRelease) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        if not release.tracks:
            return [ValidationIssue(ValidationLevel.ERROR, "no_audio", "No supported audio files were found.")]
        issues.extend(
            ValidationIssue(ValidationLevel.ERROR, f"missing_{required}", f"Missing required {required} metadata.")
            for required in ("artist", "album")
            if not release.get(required)
        )
        if len(release.formats) > 1:
            issues.append(ValidationIssue(ValidationLevel.ERROR, "mixed_formats", f"Release mixes formats: {', '.join(sorted(release.formats))}."))
        if release.conflicts.get("album"):
            level = ValidationLevel.WARNING if release.disc_count > 1 else ValidationLevel.ERROR
            issues.append(ValidationIssue(level, "inconsistent_album", "Audio tags do not agree on the album title."))
        if release.conflicts.get("artist") and str(release.get("artist", "")).casefold() != "various artists":
            issues.append(ValidationIssue(ValidationLevel.WARNING, "inconsistent_artist", "Audio tags contain multiple album artists."))
        tracks_by_disc: dict[int, list[int]] = {}
        for track in release.tracks:
            if track.track_number:
                tracks_by_disc.setdefault(track.disc_number or 1, []).append(track.track_number)
            elif not track.title:
                issues.append(ValidationIssue(ValidationLevel.WARNING, "untagged_track", f"{track.relative_path} has neither a title nor a track number."))
        for disc, numbers in tracks_by_disc.items():
            unique = sorted(set(numbers))
            if unique and unique != list(range(1, max(unique) + 1)):
                issues.append(ValidationIssue(ValidationLevel.WARNING, "non_contiguous_tracks", f"Disc {disc} has non-contiguous track numbers."))
        return issues


# --- Orpheus policy -------------------------------------------------------
#
# Values below mirror the Orpheus upload rules and the public Gazelle upload
# handler (``Util\FileChecker`` and ``upload_handle.php``).  A file outside the
# extension whitelist, a forbidden character or a too-long path is rejected by
# the server, so those are errors here rather than surprises after hashing.

ORPHEUS_ALLOWED_EXTENSIONS = frozenset(
    {
        "ac3",
        "accurip",
        "azw3",
        "chm",
        "cue",
        "djv",
        "djvu",
        "doc",
        "docx",
        "dts",
        "epub",
        "ffp",
        "flac",
        "gif",
        "htm",
        "html",
        "jpeg",
        "jpg",
        "json",
        "lit",
        "lrc",
        "log",
        "m3u",
        "m3u8",
        "m4a",
        "m4b",
        "md5",
        "mobi",
        "mp3",
        "mp4",
        "nfo",
        "pdf",
        "pls",
        "png",
        "rtf",
        "sfv",
        "txt",
        "toc",
        "yaml",
        "yml",
    }
)
ORPHEUS_FORBIDDEN_KEYWORDS = (
    "ahashare.com",
    "demonoid.com",
    "demonoid.me",
    "djtunes.com",
    "h33t",
    "housexclusive.net",
    "limetorrents.com",
    "mixesdb.com",
    "mixfiend.blogstop",
    "mixtapetorrent.blogspot",
    "plixid.com",
    "reggaeme.com",
    "scc.nfo",
    "thepiratebay.org",
    "torrentday",
    "incomplete~",
)
ORPHEUS_FORBIDDEN_CHARACTERS = re.compile(r'[\\:?<>*|"]')
ORPHEUS_MAX_PATH_LENGTH = 255
ORPHEUS_MAX_EMBEDDED_IMAGE_BYTES = 1024 * 1024
ORPHEUS_MAX_EDITION_FIELD_LENGTH = 80
# First year a digital source medium was commercially available.  Edition
# years before these are impossible for the medium (rule 2.1.19); the server
# itself rejects CD editions before 1982.
ORPHEUS_MEDIUM_FIRST_YEAR: dict[str, int] = {"CD": 1982, "DVD": 1996, "SACD": 1999, "WEB": 1999, "BD": 2006}
# P2P/scene/seller sources listed on the Do Not Upload list.  The optional
# medium limits a source that is banned only for that medium.
ORPHEUS_BLOCKED_SOURCES: dict[str, tuple[str, str | None]] = {
    "tsx": ("TSX", None),
    "hiphoplossless": ("Hiphoplossless.com", None),
    "bellum": ("BELLUM", "CD"),
    "funkerman": ("Funkerman", None),
    "beatstreetsny": ("BeatstreetsNY", None),
    "midfloridawholesale2015": ("MidFloridaWholesale2015", None),
    "mixunit": ("MixUnit", None),
}
_NUMBER_PREFIX = re.compile(r"^\s*(\d{1,3}(?:\s*[-.]\s*\d{1,3})?)(?!\d)")
_DISC_FOLDER = re.compile(r"^\s*(?:cd|disc|disk|side|lp|vinyl)\b|^\s*\d{1,2}\s*$", re.I)


def _has_track_number(stem: str, track_number: int | None) -> bool:
    """Return whether a file name carries its track number (rule 2.3.13)."""
    if track_number:
        return re.search(rf"(?<!\d)0*{track_number}(?!\d)", stem) is not None
    # Vinyl side positions such as ``A1`` also identify the track.
    return re.search(r"(?<!\d)\d{1,3}(?!\d)|\b[A-Z]\d{1,2}\b", stem) is not None


_LAME_PRESETS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^-V\s*0\b"), "V0 (VBR)"),
    (re.compile(r"^-V\s*1\b"), "V1 (VBR)"),
    (re.compile(r"^-V\s*2\b"), "V2 (VBR)"),
    (re.compile(r"--(?:alt-)?preset\s+(?:fast\s+)?extreme\b"), "APX (VBR)"),
    (re.compile(r"--(?:alt-)?preset\s+(?:fast\s+)?standard\b"), "APS (VBR)"),
    (re.compile(r"--(?:alt-)?preset\s+insane\b"), "320"),
)


def lame_preset(settings: str) -> str | None:
    """Map LAME header settings (as read by Mutagen) to an Orpheus bitrate."""
    value = str(settings or "").strip()
    for pattern, label in _LAME_PRESETS:
        if pattern.search(value):
            return label
    return None


@dataclass(frozen=True)
class OrpheusEdition:
    """Release information sent in Orpheus's edition form fields."""

    unknown: bool
    year: str
    title: str
    label: str
    catalogue_number: str
    # Folder-name text that was not sent because it is unreliable, as
    # ``(field, value)`` pairs for the user to confirm.
    folder_hints: tuple[tuple[str, str], ...] = ()
    # An explicit user year that predates the medium (reported, not sent).
    rejected_user_year: str = ""


def _four_digit_year(value: object) -> str:
    match = re.search(r"\b(\d{4})\b", str(value or ""))
    return match.group(1) if match else ""


# Folder names are parsed heuristically.  Their years are reliable, but their
# label, catalogue and edition text frequently mixes in technical tags or
# neighbouring values, so Orpheus only receives such text from stronger sources.
_UNTRUSTED_TEXT_SOURCES = frozenset({MetadataSource.DIRECTORY, MetadataSource.INFERRED})


def _trusted_text(release: MusicRelease, *names: str) -> tuple[str, str]:
    """Return ``(trusted value, untrusted folder value)`` for the first field set."""
    folder_value = ""
    for name in names:
        item = release.fields.get(name)
        value = str(item.value).strip() if item and item.value not in (None, "") else ""
        if not value or item is None:
            continue
        if item.source in _UNTRUSTED_TEXT_SOURCES:
            folder_value = folder_value or value
            continue
        return value, ""
    return "", folder_value


def resolve_orpheus_edition(release: MusicRelease) -> OrpheusEdition:
    """Resolve Orpheus edition fields without guessing (rule 2.1.19).

    Concrete release evidence wins.  A year that predates the source medium
    is not edition evidence (tag dates usually hold the original year), so it
    is skipped; validation then asks for the pressing year or ``Unknown
    Release``.  Folder-derived text is returned only as a hint.
    """
    if release.get("unknown_release"):
        return OrpheusEdition(True, "", "", "", "")
    first_year = ORPHEUS_MEDIUM_FIRST_YEAR.get(str(release.get("media", "")).upper())
    year = ""
    rejected_user_year = ""
    for name in ("edition_year", "release_year", "retail_date", "year"):
        item = release.fields.get(name)
        candidate = _four_digit_year(item.value if item else "")
        if not candidate:
            continue
        if first_year is not None and int(candidate) < first_year:
            if item is not None and item.source == MetadataSource.USER and name != "year":
                rejected_user_year = rejected_user_year or candidate
            continue
        year = candidate
        break
    label, folder_label = _trusted_text(release, "edition_label", "release_label", "label")
    catalogue, folder_catalogue = _trusted_text(release, "edition_catalogue_number", "release_catalogue_number", "catalogue_number")
    title, folder_title = _trusted_text(release, "edition")
    hints = tuple((field_name, value) for field_name, value in (("label", folder_label), ("catalogue number", folder_catalogue), ("edition title", folder_title)) if value)
    return OrpheusEdition(False, year, title, label, catalogue, hints, rejected_user_year)


def release_files(release: MusicRelease) -> list[str]:
    """Return every file path, relative to the release folder."""
    auxiliary = release.auxiliary
    groups = (
        auxiliary.logs,
        auxiliary.cues,
        auxiliary.nfos,
        auxiliary.sfvs,
        auxiliary.playlists,
        auxiliary.artwork,
        auxiliary.scans,
        auxiliary.lineage,
        auxiliary.other,
    )
    return [track.relative_path for track in release.tracks] + [path for group in groups for path in group]


def blocked_sources(release: MusicRelease, extra_names: tuple[str, ...] = ()) -> list[str]:
    """Return Do-Not-Upload P2P/scene/seller sources named in the release."""
    media = str(release.get("media", "")).upper()
    names = [PurePath(release.root).name, *release_files(release), *extra_names]
    tokens = {token for name in names for token in re.split(r"[^a-z0-9]+", str(name).casefold()) if token}
    joined = " ".join(str(name).casefold() for name in names)
    found: list[str] = []
    for key, (display, only_media) in ORPHEUS_BLOCKED_SOURCES.items():
        if only_media and media != only_media:
            continue
        # "Hiphoplossless.com" is a domain; match it as a substring too.
        if key in tokens or (key == "hiphoplossless" and key in joined.replace(" ", "")):
            found.append(display)
    return found


class OrpheusMusicValidator(MusicValidator):
    """Mechanical checks derived from the Orpheus music upload rules.

    Warnings identify evidence which requires a human/staff decision; only clear
    violations are errors.  This prevents the tool from pretending it can prove
    provenance or detect a transcode from tags alone.
    """

    # Rule 2.1.1: Ogg Vorbis is listed in the form but is not an allowed
    # music format, and the server rejects ``.ogg`` files.
    ALLOWED_FORMATS: ClassVar[set[str]] = {"FLAC", "MP3", "AAC", "AC3", "DTS"}
    ALLOWED_SAMPLE_RATES: ClassVar[set[int]] = {44100, 48000, 88200, 96000, 176400, 192000}

    def validate(self, release: MusicRelease) -> list[ValidationIssue]:
        issues = super().validate(release)
        for required in ("year", "media", "release_type"):
            if not release.get(required):
                issues.append(ValidationIssue(ValidationLevel.ERROR, f"missing_{required}", f"Missing required Orpheus music metadata: {required}."))
        issues.extend(self._track_issues(release))
        issues.extend(self._file_issues(release))
        issues.extend(self._edition_issues(release))
        variants = release.technical_variants
        if len(variants) > 1:
            media = str(release.get("media", "")).upper()
            level = ValidationLevel.WARNING if media == "WEB" else ValidationLevel.ERROR
            issues.append(
                ValidationIssue(
                    level, "hybrid_technical", "Tracks have differing bit depth, sample rate, channels or bitrate mode; Orpheus requires evidence for a hybrid WEB release."
                )
            )
        mp3_settings = {lame_preset(track.encoder_settings) or track.encoder_settings for track in release.tracks if track.format == "MP3" and track.encoder_settings}
        if len(mp3_settings) > 1:
            issues.append(
                ValidationIssue(
                    ValidationLevel.ERROR, "mixed_encoder_settings", f"MP3 files use different encoder settings ({', '.join(sorted(mp3_settings))}); rule 2.1.5 requires one."
                )
            )
        if len(release.tracks) == 1 and str(release.get("release_type", "")) != "Single":
            issues.append(ValidationIssue(ValidationLevel.ERROR, "single_track", "A one-track upload must be an officially released single."))
        if release.get("media") in {"CD", "SACD", "BD"} and release.is_lossless and not release.auxiliary.logs:
            issues.append(ValidationIssue(ValidationLevel.WARNING, "missing_log", "A lossless physical-media rip has no rip log; it may be trumpable or require review."))
        # A single FLAC file can be an official single; local metadata alone
        # cannot prove it is an unsplit album image.  The release type guard
        # above blocks the clear violation and leaves ambiguous cases for review.
        if len(release.tracks) == 1 and release.is_lossless and not release.auxiliary.cues and str(release.get("release_type", "")) != "Single":
            issues.append(ValidationIssue(ValidationLevel.WARNING, "possible_unsplit", "A one-file FLAC without a cue requires confirmation that it is an official single."))
        if not release.get("media"):
            issues.append(
                ValidationIssue(ValidationLevel.WARNING, "unknown_media", "Source media is unknown; do not guess. WEB is appropriate only for verified digital downloads.")
            )
        if str(release.get("media", "")).upper() in {"SACD", "BD", "CASSETTE", "VINYL", "SOUNDBOARD"} and not (release.auxiliary.lineage or release.get("lineage")):
            issues.append(ValidationIssue(ValidationLevel.WARNING, "missing_lineage", "This source type requires or strongly benefits from lineage information."))
        sources = blocked_sources(release)
        if sources:
            issues.append(ValidationIssue(ValidationLevel.ERROR, "blocked_source", f"Do Not Upload list: release is from a blacklisted source ({', '.join(sources)})."))
        return issues

    def _track_issues(self, release: MusicRelease) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        media = str(release.get("media", "")).upper()
        missing_tags: Counter[str] = Counter()
        for track in release.tracks:
            suffix = Path(track.path).suffix.lower()
            if track.format not in self.ALLOWED_FORMATS:
                issues.append(ValidationIssue(ValidationLevel.ERROR, "unsupported_format", f"{track.relative_path}: {track.format} is not an allowed Orpheus music format."))
            if track.format == "FLAC" and suffix != ".flac":
                issues.append(ValidationIssue(ValidationLevel.ERROR, "invalid_container", f"{track.relative_path}: FLAC must use the .flac container."))
            if track.format == "AAC" and suffix not in {".m4a", ".mp4"}:
                issues.append(ValidationIssue(ValidationLevel.ERROR, "invalid_container", f"{track.relative_path}: AAC must use the .m4a or .mp4 container."))
            if track.sample_rate and track.sample_rate not in self.ALLOWED_SAMPLE_RATES:
                issues.append(ValidationIssue(ValidationLevel.ERROR, "sample_rate", f"{track.relative_path}: {track.sample_rate} Hz is not an allowed Orpheus sample rate."))
            if track.format == "FLAC":
                if track.bit_depth and track.bit_depth > 24:
                    issues.append(ValidationIssue(ValidationLevel.ERROR, "bit_depth", f"{track.relative_path}: FLAC depth exceeds 24-bit."))
                if track.bit_depth == 16 and track.sample_rate and track.sample_rate > 48000:
                    issues.append(ValidationIssue(ValidationLevel.ERROR, "16bit_high_rate", f"{track.relative_path}: 16-bit FLAC is limited to 44.1/48 kHz."))
                if track.has_id3_tags:
                    issues.append(
                        ValidationIssue(
                            ValidationLevel.WARNING, "flac_id3", f"{track.relative_path}: FLAC contains ID3 tags; use Vorbis comments only (rule 2.2.10.8, trumpable)."
                        )
                    )
                if any(key.casefold().startswith("mqa") for key in track.tags) or "mqa" in track.encoder_info.casefold():
                    issues.append(ValidationIssue(ValidationLevel.ERROR, "mqa", f"{track.relative_path}: MQA-encoded FLAC is not allowed (rule 1.2.7)."))
            if track.format == "MP3":
                if track.bitrate and track.bitrate > 320_000 and track.bitrate_mode == "CBR":
                    issues.append(ValidationIssue(ValidationLevel.ERROR, "mp3_cbr_limit", f"{track.relative_path}: MP3 CBR bitrate exceeds 320 kbps."))
                if media == "CD" and track.sample_rate and track.sample_rate != 44100:
                    issues.append(ValidationIssue(ValidationLevel.ERROR, "mp3_cd_rate", f"{track.relative_path}: MP3s from CD must be encoded at 44.1 kHz (rule 2.1.23.4)."))
            if track.embedded_image_bytes > ORPHEUS_MAX_EMBEDDED_IMAGE_BYTES:
                issues.append(
                    ValidationIssue(
                        ValidationLevel.ERROR,
                        "embedded_image_size",
                        f"{track.relative_path}: embedded images and padding use {track.embedded_image_bytes // 1024} KiB; the limit is 1024 KiB (rule 2.3.19).",
                    )
                )
            # Rule 2.3.16: AC3/DTS cannot carry reliable tags; their names do.
            if track.format not in {"AC3", "DTS"}:
                for name, present in (
                    ("artist", track.artist or track.album_artist),
                    ("album", track.album),
                    ("title", track.title),
                    ("track number", track.track_number),
                ):
                    if not present:
                        missing_tags[name] += 1
        for name, count in missing_tags.items():
            issues.append(ValidationIssue(ValidationLevel.ERROR, "missing_required_tag", f"{count} file(s) are missing the required {name} tag (rule 2.3.16.4)."))
        return issues

    @staticmethod
    def _file_issues(release: MusicRelease) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        folder = PurePath(release.root).name
        files = release_files(release)
        for relative in files:
            path = PurePath(relative.replace("\\", "/"))
            extension = path.suffix.lower().removeprefix(".")
            if extension not in ORPHEUS_ALLOWED_EXTENSIONS:
                issues.append(
                    ValidationIssue(ValidationLevel.ERROR, "file_extension", f"{relative}: .{extension or '(none)'} files are rejected by Orpheus; remove or convert it.")
                )
            name = f"{folder}/{path.as_posix()}"
            lowered = name.casefold()
            keyword = next((word for word in ORPHEUS_FORBIDDEN_KEYWORDS if word in lowered), None)
            if keyword:
                issues.append(ValidationIssue(ValidationLevel.ERROR, "forbidden_name", f"{relative}: contains the forbidden term '{keyword}'."))
            character = ORPHEUS_FORBIDDEN_CHARACTERS.search(name)
            if character:
                issues.append(ValidationIssue(ValidationLevel.ERROR, "forbidden_character", f"{relative}: the character '{character.group()}' is not allowed in names."))
            if len(path.as_posix()) + len(folder) + 1 > ORPHEUS_MAX_PATH_LENGTH:
                issues.append(ValidationIssue(ValidationLevel.ERROR, "path_length", f"{relative}: path exceeds {ORPHEUS_MAX_PATH_LENGTH} characters (rule 2.3.12)."))
            if any(part != part.lstrip() for part in (folder, *path.parts)):
                issues.append(ValidationIssue(ValidationLevel.WARNING, "leading_space", f"{relative}: names must not start with a space (rule 2.3.20)."))

        audio_paths = [PurePath(track.relative_path.replace("\\", "/")) for track in release.tracks]
        # One sub-folder per disc (or vinyl side) is allowed; anything deeper,
        # or a lone wrapper folder around a single disc, is unnecessary.
        nested = [path for path in audio_paths if len(path.parts) > 2 or (len(path.parts) == 2 and not _DISC_FOLDER.match(path.parts[0]) and release.disc_count == 1)]
        if nested:
            issues.append(ValidationIssue(ValidationLevel.WARNING, "nested_folders", "Audio files are inside unnecessary nested folders (rule 2.3.3, trumpable)."))
        if len(release.tracks) > 1:
            unnumbered = [track.relative_path for track in release.tracks if not _has_track_number(PurePath(track.relative_path).stem, track.track_number)]
            if unnumbered:
                issues.append(
                    ValidationIssue(ValidationLevel.WARNING, "filename_track_number", f"{len(unnumbered)} file name(s) lack a track number (rule 2.3.13, trumpable).")
                )
        # Rule 2.3.15: within one folder, file names must not repeat a number.
        # Disc-prefixed names such as ``1 - 01`` and ``2 - 01`` are distinct.
        prefixes_by_folder: dict[str, Counter[str]] = {}
        for path in audio_paths:
            prefix = _NUMBER_PREFIX.match(path.stem)
            if prefix:
                key = re.sub(r"\D+", "-", prefix.group(1)).lstrip("0") or "0"
                prefixes_by_folder.setdefault(path.parent.as_posix(), Counter())[key] += 1
        if release.disc_count > 1 and any(count > 1 for counter in prefixes_by_folder.values() for count in counter.values()):
            issues.append(
                ValidationIssue(
                    ValidationLevel.ERROR,
                    "duplicate_track_numbers",
                    "Multi-disc tracks with the same number share a folder; use disc folders or disc-prefixed numbers (rule 2.3.15).",
                )
            )
        return issues

    @staticmethod
    def _edition_issues(release: MusicRelease) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        edition = resolve_orpheus_edition(release)
        next_year = datetime.now(UTC).year + 1
        group_year = _four_digit_year(release.get("year"))
        if group_year and int(group_year) > next_year:
            issues.append(ValidationIssue(ValidationLevel.ERROR, "future_year", f"Initial year {group_year} is in the future."))
        if edition.unknown:
            return issues
        media = str(release.get("media", "")).upper()
        first_year = ORPHEUS_MEDIUM_FIRST_YEAR.get(media)
        if edition.rejected_user_year:
            issues.append(
                ValidationIssue(ValidationLevel.ERROR, "edition_predates_medium", f"Edition year {edition.rejected_user_year} predates the {media} medium ({first_year}).")
            )
        elif not edition.year:
            hint = f" The album predates {media} ({first_year}), so the tag year is the original release, not this pressing." if first_year and group_year else ""
            issues.append(
                ValidationIssue(
                    ValidationLevel.ERROR,
                    "missing_edition_year",
                    f"Orpheus needs the year of this pressing.{hint} Provide --music-release-year/--music-edition-year, or --music-unknown-release if it cannot be established (rule 2.1.19).",
                )
            )
        if edition.folder_hints:
            suggestions = ", ".join(f"{name} '{value}'" for name, value in edition.folder_hints)
            issues.append(
                ValidationIssue(
                    ValidationLevel.WARNING,
                    "folder_edition_hint",
                    f"Not sent from the folder name: {suggestions}. Confirm with --music-label, --music-catalogue-number or --edition.",
                )
            )
        if edition.year and int(edition.year) > next_year:
            issues.append(ValidationIssue(ValidationLevel.ERROR, "future_edition_year", f"Edition year {edition.year} is in the future."))
        if edition.title.casefold() == "original release":
            issues.append(ValidationIssue(ValidationLevel.ERROR, "original_release_title", '"Original Release" is not a valid edition title; leave it empty.'))
        for field_name, value in (("edition title", edition.title), ("record label", edition.label), ("catalogue number", edition.catalogue_number)):
            if len(value) > ORPHEUS_MAX_EDITION_FIELD_LENGTH:
                issues.append(ValidationIssue(ValidationLevel.ERROR, "edition_field_length", f"The {field_name} exceeds {ORPHEUS_MAX_EDITION_FIELD_LENGTH} characters."))
        return issues
