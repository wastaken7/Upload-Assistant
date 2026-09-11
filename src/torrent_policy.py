"""Central torrent acceptance and piece-size policies."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from torf import Torrent

if TYPE_CHECKING:
    from src.meta import Meta

KIB = 1024
MIB = KIB**2
GIB = KIB**3
TIB = KIB**4
PIECE_SIZE_MIN = 32 * KIB
PIECE_SIZE_MAX = 128 * MIB


@dataclass(frozen=True)
class TorrentStats:
    piece_size: int
    piece_count: int
    content_size: int
    metainfo_size: int

    @classmethod
    def from_path(cls, path: str | Path) -> TorrentStats:
        torrent = Torrent.read(path)
        return cls(
            piece_size=int(torrent.piece_size or 0),
            piece_count=int(torrent.pieces or 0),
            content_size=int(torrent.size or 0),
            metainfo_size=Path(path).stat().st_size,
        )


Validator = Callable[[TorrentStats], bool]
PieceSizeSelector = Callable[[int], int]


@dataclass(frozen=True)
class TorrentPolicy:
    """Declarative tracker limits plus optional exceptional rule functions."""

    max_piece_size: int | None = None
    max_metainfo_size: int | None = None
    required_piece_size: int | None = None
    validator: Validator | None = None
    piece_size_selector: PieceSizeSelector | None = None

    def accepts(self, stats: TorrentStats) -> bool:
        if stats.piece_size < PIECE_SIZE_MIN:
            return False
        if self.max_piece_size is not None and stats.piece_size > self.max_piece_size:
            return False
        if self.max_metainfo_size is not None and stats.metainfo_size > self.max_metainfo_size:
            return False
        return self.validator(stats) if self.validator is not None else True

    def choose_piece_size(self, content_size: int, default_piece_size: int) -> int:
        if self.piece_size_selector is not None:
            return self.piece_size_selector(content_size)
        if self.required_piece_size is not None:
            return self.required_piece_size
        if self.max_piece_size is not None:
            return min(default_piece_size, self.max_piece_size)
        return default_piece_size


def hdbits_pieces_allowed(piece_size: int, pieces: int, total_size: int) -> bool:
    if piece_size <= 0 or piece_size & (piece_size - 1) or pieces <= 0:
        return False
    if piece_size <= 2 * MIB:
        return pieces <= 4000
    if piece_size in (4 * MIB, 8 * MIB):
        return pieces <= 30000
    return piece_size == 16 * MIB or (piece_size == 32 * MIB and total_size > TIB)


def hdbits_piece_size(total_size: int) -> int:
    if total_size > 8 * GIB:
        return 16 * MIB
    piece_size = PIECE_SIZE_MIN
    while not hdbits_pieces_allowed(piece_size, max(1, (total_size + piece_size - 1) // piece_size), total_size):
        piece_size *= 2
    return piece_size


def _hdbits_validator(stats: TorrentStats) -> bool:
    return hdbits_pieces_allowed(stats.piece_size, stats.piece_count, stats.content_size)


HDBITS_POLICY = TorrentPolicy(validator=_hdbits_validator, piece_size_selector=hdbits_piece_size)
PASSTHEPOPCORN_POLICY = TorrentPolicy(max_piece_size=16 * MIB)
ANTHELION_POLICY = TorrentPolicy(max_metainfo_size=250 * KIB, required_piece_size=128 * MIB)


def generic_reuse_allowed(stats: TorrentStats, meta: Meta) -> bool:
    """Preserve the historical client-reuse thresholds in one responsible layer."""
    max_piece_size = meta.max_piece_size
    if stats.piece_count >= 5000 and stats.piece_size < 4_294_304 and (max_piece_size is None or max_piece_size >= 4):
        return False
    if stats.piece_count >= 8000 and stats.piece_size < 8_488_608 and (max_piece_size is None or max_piece_size >= 8) and not meta.prefer_small_pieces:
        return False
    if "max_piece_size" not in meta and stats.piece_count >= 12000:
        return False
    if stats.piece_size < PIECE_SIZE_MIN:
        return False
    return not ("max_piece_size" not in meta and stats.metainfo_size > 250 * KIB)
