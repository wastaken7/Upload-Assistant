"""Generic and Orpheus-specific validation without mutating a release."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import ClassVar

from src.music.models import MusicRelease


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


class OrpheusMusicValidator(MusicValidator):
    """Mechanical checks derived from the Orpheus music upload rules.

    Warnings identify evidence which requires a human/staff decision; only clear
    violations are errors.  This prevents the tool from pretending it can prove
    provenance or detect a transcode from tags alone.
    """

    ALLOWED_FORMATS: ClassVar[set[str]] = {"FLAC", "MP3", "Ogg Vorbis", "AAC", "AC3", "DTS"}
    ALLOWED_SAMPLE_RATES: ClassVar[set[int]] = {44100, 48000, 88200, 96000, 176400, 192000}

    def validate(self, release: MusicRelease) -> list[ValidationIssue]:
        issues = super().validate(release)
        for required in ("year", "media", "release_type"):
            if not release.get(required):
                issues.append(ValidationIssue(ValidationLevel.ERROR, f"missing_{required}", f"Missing required Orpheus music metadata: {required}."))
        for track in release.tracks:
            suffix = Path(track.path).suffix.lower()
            if track.format not in self.ALLOWED_FORMATS:
                issues.append(ValidationIssue(ValidationLevel.ERROR, "unsupported_format", f"{track.relative_path}: {track.format} is not an allowed Orpheus music format."))
            if track.format == "FLAC" and suffix != ".flac":
                issues.append(ValidationIssue(ValidationLevel.ERROR, "invalid_container", f"{track.relative_path}: FLAC must use the .flac container."))
            if track.format == "AAC" and suffix not in {".m4a", ".aac"}:
                issues.append(ValidationIssue(ValidationLevel.ERROR, "invalid_container", f"{track.relative_path}: AAC must use the .m4a or .aac container."))
            if track.format == "FLAC":
                if track.bit_depth and track.bit_depth > 24:
                    issues.append(ValidationIssue(ValidationLevel.ERROR, "bit_depth", f"{track.relative_path}: FLAC depth exceeds 24-bit."))
                if track.sample_rate and track.sample_rate not in self.ALLOWED_SAMPLE_RATES:
                    issues.append(ValidationIssue(ValidationLevel.ERROR, "sample_rate", f"{track.relative_path}: sample rate is not allowed by Orpheus."))
                if track.bit_depth == 16 and track.sample_rate and track.sample_rate > 48000:
                    issues.append(ValidationIssue(ValidationLevel.ERROR, "16bit_high_rate", f"{track.relative_path}: 16-bit FLAC is limited to 44.1/48 kHz."))
            if track.format == "MP3" and track.bitrate and track.bitrate > 320_000 and track.bitrate_mode == "CBR":
                issues.append(ValidationIssue(ValidationLevel.ERROR, "mp3_cbr_limit", f"{track.relative_path}: MP3 CBR bitrate exceeds 320 kbps."))
        variants = release.technical_variants
        if len(variants) > 1:
            media = str(release.get("media", "")).upper()
            level = ValidationLevel.WARNING if media == "WEB" else ValidationLevel.ERROR
            issues.append(
                ValidationIssue(
                    level, "hybrid_technical", "Tracks have differing bit depth, sample rate, channels or bitrate mode; Orpheus requires evidence for a hybrid WEB release."
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
        if str(release.get("media", "")).upper() in {"SACD", "BD", "CASSETTE"} and not release.auxiliary.lineage:
            issues.append(ValidationIssue(ValidationLevel.WARNING, "missing_lineage", "This source type requires or strongly benefits from lineage information."))
        return issues
