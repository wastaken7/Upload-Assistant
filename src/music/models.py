"""Typed, tracker-neutral representation of a music release.

The model deliberately carries provenance for every value.  Tracker adapters can
therefore make conservative decisions without silently replacing file-tag data
with a lower-confidence directory or remote-service guess.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, TypeIs


def _is_str_dict(val: object) -> TypeIs[dict[str, Any]]:
    return isinstance(val, dict)


class MetadataSource(StrEnum):
    USER = "user"
    FILE_TAG = "file_tag"
    AUXILIARY = "auxiliary"
    DIRECTORY = "directory"
    EXTERNAL = "external"
    TRACKER = "tracker"
    INFERRED = "inferred"


@dataclass(frozen=True)
class MetadataValue:
    value: Any
    source: MetadataSource
    confidence: float


@dataclass
class AudioTrack:
    path: str
    relative_path: str
    format: str
    codec: str
    bitrate: int | None = None
    bitrate_mode: str | None = None
    bit_depth: int | None = None
    sample_rate: int | None = None
    channels: int | None = None
    duration: float | None = None
    disc_number: int | None = None
    track_number: int | None = None
    artist: str = ""
    album_artist: str = ""
    album: str = ""
    title: str = ""
    date: str = ""
    label: str = ""
    catalogue_number: str = ""
    genre: list[str] = field(default_factory=list[str])
    isrc: str = ""
    tags: dict[str, list[str]] = field(default_factory=dict[str, list[str]])
    # Encoder evidence (LAME header for MP3) used to label presets such as V0.
    encoder_info: str = ""
    encoder_settings: str = ""
    # Bytes used by embedded pictures plus metadata padding.  Trackers limit
    # this per file, so it is measured without changing the file.
    embedded_image_bytes: int = 0
    # True when an ID3 header or ID3v1 footer is wrapped around a FLAC stream.
    has_id3_tags: bool = False


@dataclass
class AuxiliaryFiles:
    logs: list[str] = field(default_factory=list[str])
    cues: list[str] = field(default_factory=list[str])
    nfos: list[str] = field(default_factory=list[str])
    sfvs: list[str] = field(default_factory=list[str])
    playlists: list[str] = field(default_factory=list[str])
    artwork: list[str] = field(default_factory=list[str])
    scans: list[str] = field(default_factory=list[str])
    lineage: list[str] = field(default_factory=list[str])
    other: list[str] = field(default_factory=list[str])


@dataclass
class MusicRelease:
    root: str
    tracks: list[AudioTrack] = field(default_factory=list[AudioTrack])
    auxiliary: AuxiliaryFiles = field(default_factory=AuxiliaryFiles)
    fields: dict[str, MetadataValue] = field(default_factory=dict[str, MetadataValue])
    conflicts: dict[str, list[str]] = field(default_factory=dict[str, list[str]])
    warnings: list[str] = field(default_factory=list[str])
    external_ids: dict[str, str] = field(default_factory=dict[str, str])

    @staticmethod
    def _source_tier(source: MetadataSource) -> int:
        """Return the provenance priority used when deciding real conflicts."""
        return {
            MetadataSource.USER: 4,
            MetadataSource.FILE_TAG: 3,
            MetadataSource.AUXILIARY: 2,
            MetadataSource.DIRECTORY: 1,
            MetadataSource.EXTERNAL: 0,
            MetadataSource.TRACKER: 0,
            MetadataSource.INFERRED: 0,
        }[source]

    def set_field(self, name: str, value: Any, source: MetadataSource, confidence: float, *, force: bool = False) -> None:
        if value in (None, "", [], {}):
            return
        existing = self.fields.get(name)
        if force or existing is None or confidence > existing.confidence:
            self.fields[name] = MetadataValue(value=value, source=source, confidence=confidence)
        elif existing.value != value and self._source_tier(source) == self._source_tier(existing.source):
            values = self.conflicts.setdefault(name, [str(existing.value)])
            if str(value) not in values:
                values.append(str(value))

    def get(self, name: str, default: Any = "") -> Any:
        item = self.fields.get(name)
        return item.value if item else default

    @property
    def formats(self) -> set[str]:
        return {track.format for track in self.tracks}

    @property
    def is_lossless(self) -> bool:
        return bool(self.tracks) and self.formats == {"FLAC"}

    @property
    def disc_count(self) -> int:
        return max((track.disc_number or 1 for track in self.tracks), default=1)

    @property
    def technical_variants(self) -> set[tuple[str, int | None, int | None, int | None, str | None]]:
        return {(t.format, t.bit_depth, t.sample_rate, t.channels, t.bitrate_mode) for t in self.tracks}

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MusicRelease:
        release = cls(root=str(data.get("root", "")))
        release.tracks = [AudioTrack(**track) for track in data.get("tracks", [])]
        release.auxiliary = AuxiliaryFiles(**data.get("auxiliary", {}))
        for key, value in data.get("fields", {}).items():
            if _is_str_dict(value):
                release.fields[key] = MetadataValue(
                    value=value.get("value"),
                    source=MetadataSource(value.get("source", "inferred")),
                    confidence=float(value.get("confidence", 0)),
                )
        release.conflicts = {str(k): list(v) for k, v in data.get("conflicts", {}).items()}
        release.warnings = list(data.get("warnings", []))
        release.external_ids = {str(k): str(v) for k, v in data.get("external_ids", {}).items()}
        return release

    @property
    def path(self) -> Path:
        return Path(self.root)
