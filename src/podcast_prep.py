from __future__ import annotations

import tarfile
import zipfile
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Protocol, cast

import mutagen
from pymediainfo import MediaInfo

from src.exportmi import export_info
from src.meta import Meta

AUDIO_EXTENSIONS = frozenset({".aac", ".ac3", ".aiff", ".alac", ".ape", ".dts", ".flac", ".m4a", ".m4b", ".mp3", ".ogg", ".opus", ".wav", ".wma", ".wv"})
VIDEO_EXTENSIONS = frozenset({".avi", ".m4v", ".mkv", ".mov", ".mp4", ".ts", ".webm"})
ARCHIVE_EXTENSIONS = frozenset({".7z", ".bz2", ".cbr", ".cbz", ".gz", ".rar", ".tar", ".tbz", ".tbz2", ".tgz", ".txz", ".xz", ".zip", ".zst"})


class _MediaTrack(Protocol):
    track_type: str | None
    internet_media_type: str | None


class _MediaInfoResult(Protocol):
    tracks: list[_MediaTrack]


class _AudioInfo(Protocol):
    bitrate: int | None


class _AudioFile(Protocol):
    info: _AudioInfo | None


mutagen_file = cast(Callable[[str], _AudioFile | None], vars(mutagen)["File"])
mutagen_error = cast(type[Exception], vars(mutagen)["MutagenError"])


def _has_symlink_component(path: Path) -> bool:
    absolute = path.expanduser().absolute()
    return any(component.is_symlink() for component in (*reversed(absolute.parents), absolute))


def _source_files(root: Path) -> list[Path]:
    if _has_symlink_component(root):
        raise ValueError("Podcast uploads cannot contain symbolic links")
    if root.is_file():
        return [root]
    candidates: list[Path] = []
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError("Podcast uploads cannot contain symbolic links")
        if path.is_file():
            candidates.append(path)
    return candidates


def _has_archive_signature(path: Path) -> bool:
    with path.open("rb") as source:
        header = source.read(512)
    has_header = (
        header.startswith(
            (
                b"PK\x03\x04",
                b"PK\x05\x06",
                b"PK\x07\x08",
                b"Rar!\x1a\x07",
                b"7z\xbc\xaf\x27\x1c",
                b"\x1f\x8b",
                b"\x1f\x9d",
                b"BZh",
                b"\xfd7zXZ\x00",
                b"\x28\xb5\x2f\xfd",
                b"\x04\x22\x4d\x18",
                b"MSCF",
                b"LZIP",
                b"xar!",
                b"!<arch>\n",
            )
        )
        or header[257:262] == b"ustar"
    )
    if has_header or zipfile.is_zipfile(path):
        return True
    try:
        return tarfile.is_tarfile(path)
    except OSError:
        return False


def _detected_media_kind(path: Path) -> str | None:
    try:
        media_info = cast(_MediaInfoResult, MediaInfo.parse(str(path)))
    except OSError, RuntimeError, ValueError:
        return None
    general_content_type = ""
    has_audio = False
    for track in media_info.tracks:
        if track.track_type == "Video":
            return "video"
        if track.track_type == "Audio":
            has_audio = True
        elif track.track_type == "General":
            general_content_type = str(track.internet_media_type or "").casefold()
    if general_content_type.startswith("video/"):
        return "video"
    if has_audio or general_content_type.startswith("audio/"):
        return "audio"
    return None


def _media_files(candidates: list[Path]) -> tuple[list[Path], list[Path]]:
    archives = [path for path in candidates if path.suffix.casefold() in ARCHIVE_EXTENSIONS or _has_archive_signature(path)]
    if archives:
        raise ValueError("Podcast uploads cannot contain compressed archive files")
    audio: list[Path] = []
    video: list[Path] = []
    for path in candidates:
        suffix = path.suffix.casefold()
        declared_kind = "audio" if suffix in AUDIO_EXTENSIONS else "video" if suffix in VIDEO_EXTENSIONS else None
        if declared_kind is None:
            continue
        detected_kind = _detected_media_kind(path)
        if detected_kind is None:
            raise ValueError(f"Podcast media content could not be identified: {path.name}")
        if detected_kind != declared_kind:
            raise ValueError(f"Podcast media extension does not match its actual content: {path.name}")
        (audio if declared_kind == "audio" else video).append(path.resolve())
    audio.sort(key=str)
    video.sort(key=str)
    return audio, video


def _dominant_extension(files: list[Path]) -> str:
    counts = Counter(path.suffix.lstrip(".").upper() for path in files)
    return counts.most_common(1)[0][0] if counts else ""


def _audio_bitrate(files: list[Path]) -> int | None:
    bitrates: list[int] = []
    for path in files:
        try:
            audio = mutagen_file(str(path))
            bitrate = int(audio.info.bitrate or 0) if audio is not None and audio.info is not None else 0
        except OSError, TypeError, ValueError, mutagen_error:
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
    if _has_symlink_component(root):
        raise ValueError("Podcast uploads cannot contain symbolic links")
    if not root.exists():
        raise ValueError(f"Podcast path does not exist: {root}")

    source_files = _source_files(root)
    audio_files, video_files = _media_files(source_files)
    if audio_files and video_files:
        raise ValueError("Podcast torrents cannot contain mixed audio and video media")
    media_files = audio_files or video_files
    if not media_files:
        raise ValueError("Podcast upload contains no supported audio or video files")
    torrent_files = sorted((path.resolve() for path in source_files), key=str)

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
        cover = Path(meta.podcast_cover).expanduser()
        if _has_symlink_component(cover):
            raise ValueError("Podcast uploads cannot contain symbolic links")
        meta.artwork_path = str(cover.resolve())
    if meta.podcast_banner:
        banner = Path(meta.podcast_banner).expanduser()
        if _has_symlink_component(banner):
            raise ValueError("Podcast uploads cannot contain symbolic links")
        meta.artwork_banner_path = str(banner.resolve())

    primary = max(media_files, key=lambda path: path.stat().st_size)
    meta.mediainfo = await export_info(str(primary), meta.isdir, meta.uuid, meta.base_dir, is_dvd=False)
    final_title = str(meta.podcast_title or _generated_title(meta, root, media_files, bool(audio_files))).strip()
    meta.title = meta.title or (root.stem if root.is_file() else root.name)
    meta.name_notag = final_title
    meta.name = final_title
    meta.clean_name = final_title
    meta.search_year = ""
