from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, cast

import mutagen

from src.exportmi import export_info
from src.meta import Meta

AUDIO_EXTENSIONS = frozenset({".aac", ".ac3", ".aiff", ".alac", ".ape", ".dts", ".flac", ".m4a", ".m4b", ".mp3", ".ogg", ".opus", ".wav", ".wma", ".wv"})
VIDEO_EXTENSIONS = frozenset({".avi", ".m4v", ".mkv", ".mov", ".mp4", ".ts", ".webm"})
ARCHIVE_EXTENSIONS = frozenset({".7z", ".bz2", ".cbr", ".cbz", ".gz", ".rar", ".tar", ".tbz", ".tbz2", ".tgz", ".txz", ".xz", ".zip", ".zst"})
mutagen_module: Any = cast(Any, mutagen)


def _media_files(root: Path) -> tuple[list[Path], list[Path]]:
    candidates = [root] if root.is_file() else [path for path in root.rglob("*") if path.is_file()]
    archives = [path for path in candidates if path.suffix.casefold() in ARCHIVE_EXTENSIONS]
    if archives:
        raise ValueError("Podcast uploads cannot contain compressed archive files")
    audio = sorted((path.resolve() for path in candidates if path.suffix.casefold() in AUDIO_EXTENSIONS), key=str)
    video = sorted((path.resolve() for path in candidates if path.suffix.casefold() in VIDEO_EXTENSIONS), key=str)
    return audio, video


def _dominant_extension(files: list[Path]) -> str:
    counts = Counter(path.suffix.lstrip(".").upper() for path in files)
    return counts.most_common(1)[0][0] if counts else ""


def _audio_bitrate(files: list[Path]) -> int | None:
    bitrates: list[int] = []
    for path in files:
        try:
            audio = mutagen_module.File(str(path))
            bitrate = int(getattr(getattr(audio, "info", None), "bitrate", 0) or 0)
        except Exception:
            bitrate = 0
        if bitrate > 0:
            bitrates.append(round(bitrate / 1000))
    if not bitrates:
        return None
    counts = Counter(bitrates)
    bitrate, count = counts.most_common(1)[0]
    return bitrate if count / len(bitrates) >= 0.7 else None


def _generated_title(meta: Meta, root: Path, files: list[Path], audio: bool) -> str:
    fallback_title = root.stem if root.is_file() else root.name
    title = str(meta.title or fallback_title).strip()
    year = str(meta.manual_year or meta.year or "").strip()
    media_format = _dominant_extension(files)
    details = [year] if year else []
    if media_format:
        technical = media_format
        bitrate = _audio_bitrate(files) if audio else None
        if bitrate:
            technical = f"{technical} - {bitrate}kbps"
        details.append(technical)
    return f"{title} [{'/'.join(details)}]" if details else title


async def gather_podcast_prep(meta: Meta) -> None:
    root = Path(str(meta.path or ""))
    if not root.exists():
        raise ValueError(f"Podcast path does not exist: {root}")

    audio_files, video_files = _media_files(root)
    if audio_files and video_files:
        raise ValueError("Podcast torrents cannot contain mixed audio and video media")
    media_files = audio_files or video_files
    if not media_files:
        raise ValueError("Podcast upload contains no supported audio or video files")
    torrent_files = [root.resolve()] if root.is_file() else sorted((path.resolve() for path in root.rglob("*") if path.is_file()), key=str)

    meta.category = "PODCAST"
    meta.filelist = [str(path) for path in torrent_files]
    meta.isdir = root.is_dir()
    meta.tmdb_id = 0
    meta.imdb_id = 0
    meta.tvdb_id = 0
    meta.mal_id = 0
    meta.igdb_id = 0
    meta.tmdb = 0
    meta.imdb = "0"
    meta.tvdb = 0
    meta.mal = 0
    meta.type = "AUDIO" if audio_files else "VIDEO"
    meta.container = _dominant_extension(media_files).casefold()
    meta.audio_bitrate = _audio_bitrate(audio_files) if audio_files else None
    meta.resolution = ""
    meta.sd = 0
    meta.valid_mi = True
    meta.valid_mi_settings = True
    meta.source = "WEB"

    if meta.podcast_cover:
        meta.artwork_path = str(Path(meta.podcast_cover).expanduser().resolve())
    if meta.podcast_banner:
        meta.artwork_banner_path = str(Path(meta.podcast_banner).expanduser().resolve())

    primary = max(media_files, key=lambda path: path.stat().st_size)
    meta.mediainfo = await export_info(str(primary), meta.isdir, meta.uuid, meta.base_dir, is_dvd=False)
    final_title = str(meta.podcast_title or _generated_title(meta, root, media_files, bool(audio_files))).strip()
    meta.title = meta.title or (root.stem if root.is_file() else root.name)
    meta.name_notag = final_title
    meta.name = final_title
    meta.clean_name = final_title
    meta.search_year = ""
