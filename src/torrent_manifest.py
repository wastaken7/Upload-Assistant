"""Manifest-backed storage for reusable per-release torrent hashes."""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal, cast

from torf import TorfError, Torrent

from src.temp_paths import release_temp_dir
from src.torrent_policy import TorrentPolicy, TorrentStats

TorrentLayout = Literal["base", "base_subs"]


@dataclass(frozen=True)
class TorrentEntry:
    id: str
    file: str
    layout: TorrentLayout
    origin: str
    infohash: str
    piece_size: int
    piece_count: int
    content_size: int
    metainfo_size: int

    @property
    def stats(self) -> TorrentStats:
        return TorrentStats(self.piece_size, self.piece_count, self.content_size, self.metainfo_size)


_locks: dict[str, threading.RLock] = {}
_locks_guard = threading.Lock()


class TorrentManifest:
    VERSION = 1

    def __init__(self, base_dir: str | Path | None, release_id: str) -> None:
        self.root = release_temp_dir(base_dir, release_id)
        self.path = self.root / "torrent_manifest.json"
        key = str(self.path.resolve()).casefold()
        with _locks_guard:
            self._lock = _locks.setdefault(key, threading.RLock())

    def _empty(self) -> dict[str, Any]:
        return {"version": self.VERSION, "torrents": {}, "defaults": {}, "selections": {}}

    def _load(self) -> dict[str, Any]:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except OSError, json.JSONDecodeError:
            return self._empty()
        if not isinstance(value, dict) or value.get("version") != self.VERSION:
            return self._empty()
        for key in ("torrents", "defaults", "selections"):
            if not isinstance(value.get(key), dict):
                value[key] = {}
        return value

    def _save(self, value: dict[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
        temporary.replace(self.path)

    def _resolve(self, relative: str) -> Path:
        path = (self.root / relative).resolve()
        if self.root.resolve() not in path.parents:
            raise ValueError(f"Torrent manifest path escapes release directory: {relative}")
        return path

    @staticmethod
    def _normalize(source: str | Path) -> Torrent:
        torrent = Torrent.read(source)
        torrent.trackers = ["https://fake.tracker"]
        torrent.comment = "Upload-Assistant (fork)"
        torrent.created_by = "Upload-Assistant (fork)"
        info = torrent.metainfo["info"]
        valid_info = {"name", "piece length", "pieces", "private", "source", "files", "length"}
        for key in list(info):
            if key not in valid_info:
                info.pop(key, None)
        valid_root = {
            "announce",
            "comment",
            "creation date",
            "created by",
            "encoding",
            "info",
            "imdb",
            "tmdb",
            "tvdb",
            "tvmaze",
            "mal",
            "douban",
            "igdb",
            "asin",
            "isbn",
        }
        for key in list(torrent.metainfo):
            if key not in valid_root:
                torrent.metainfo.pop(key, None)
        torrent.source = "L4G"
        torrent.private = True
        return torrent

    def register(self, source: str | Path, layout: TorrentLayout, origin: str, *, make_default: bool = False) -> TorrentEntry:
        with self._lock:
            torrent = self._normalize(source)
            infohash = str(torrent.infohash)
            entry_id = f"{layout}:{infohash}"
            relative = Path("torrents") / str(int(torrent.piece_size)) / f"{infohash}.torrent"
            output = self._resolve(relative.as_posix())
            output.parent.mkdir(parents=True, exist_ok=True)
            temporary = output.with_suffix(".tmp")
            Torrent.copy(torrent).write(temporary, overwrite=True)
            temporary.replace(output)
            stats = TorrentStats.from_path(output)
            entry = TorrentEntry(
                id=entry_id,
                file=relative.as_posix(),
                layout=layout,
                origin=origin,
                infohash=infohash,
                piece_size=stats.piece_size,
                piece_count=stats.piece_count,
                content_size=stats.content_size,
                metainfo_size=stats.metainfo_size,
            )
            manifest = self._load()
            torrents = cast(dict[str, Any], manifest["torrents"])
            torrents[entry_id] = asdict(entry)
            defaults = cast(dict[str, Any], manifest["defaults"])
            if make_default or layout not in defaults:
                defaults[layout] = entry_id
            self._save(manifest)
            return entry

    def entries(self, layout: TorrentLayout | None = None) -> list[TorrentEntry]:
        manifest = self._load()
        result: list[TorrentEntry] = []
        for value in cast(dict[str, Any], manifest["torrents"]).values():
            if not isinstance(value, dict):
                continue
            try:
                entry = TorrentEntry(**value)
                path = self._resolve(entry.file)
            except TypeError, ValueError:
                continue
            if not path.is_file():
                continue
            try:
                torrent = Torrent.read(path)
                current = TorrentStats(
                    piece_size=int(torrent.piece_size or 0),
                    piece_count=int(torrent.pieces or 0),
                    content_size=int(torrent.size or 0),
                    metainfo_size=path.stat().st_size,
                )
            except OSError, TorfError, TypeError, ValueError:
                continue
            if current != entry.stats or str(torrent.infohash) != entry.infohash:
                continue
            if layout is None or entry.layout == layout:
                result.append(entry)
        return result

    def entry_path(self, entry: TorrentEntry) -> Path:
        return self._resolve(entry.file)

    def entry_for_path(self, path: str | Path) -> TorrentEntry | None:
        resolved = Path(path).resolve()
        return next((entry for entry in self.entries() if self.entry_path(entry).resolve() == resolved), None)

    def select(self, tracker: str, layout: TorrentLayout, policy: TorrentPolicy | None = None) -> TorrentEntry | None:
        candidates = [entry for entry in self.entries(layout) if policy is None or policy.accepts(entry.stats)]
        if not candidates:
            return None
        candidates.sort(key=lambda entry: (entry.piece_size, entry.metainfo_size, entry.id))
        entry = candidates[0]
        with self._lock:
            manifest = self._load()
            cast(dict[str, Any], manifest["selections"])[tracker.upper()] = entry.id
            self._save(manifest)
        return entry

    def selected_path(self, tracker: str) -> Path | None:
        manifest = self._load()
        entry_id = cast(dict[str, Any], manifest["selections"]).get(tracker.upper())
        value = cast(dict[str, Any], manifest["torrents"]).get(entry_id)
        if not isinstance(value, dict):
            return None
        try:
            entry = TorrentEntry(**value)
            path = self.entry_path(entry)
        except TypeError, ValueError:
            return None
        return path if path.is_file() else None

    def default_path(self, layout: TorrentLayout = "base") -> Path | None:
        manifest = self._load()
        entry_id = cast(dict[str, Any], manifest["defaults"]).get(layout)
        value = cast(dict[str, Any], manifest["torrents"]).get(entry_id)
        if not isinstance(value, dict):
            return None
        try:
            path = self.entry_path(TorrentEntry(**value))
        except TypeError, ValueError:
            return None
        return path if path.is_file() else None
