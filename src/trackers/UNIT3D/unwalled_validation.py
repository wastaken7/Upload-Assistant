import hashlib
import re
import warnings
from collections.abc import Callable
from pathlib import Path
from typing import cast
from urllib.parse import urlsplit

import bencodepy
from PIL import Image

from src.console import logger
from src.meta import Meta

bdecode = cast(Callable[[bytes], object], vars(bencodepy)["decode"])


class UnwalledValidationMixin:
    tracker: str

    @staticmethod
    def _has_symlink_component(path: Path) -> bool:
        absolute = path.expanduser().absolute()
        return any(component.is_symlink() for component in (*reversed(absolute.parents), absolute))

    @staticmethod
    def _valid_filename(name: str) -> bool:
        if len(name.encode("utf-8")) > 255 or not name or name != name.strip() or set(name) == {"."} or name.endswith("."):
            return False
        if re.search(r"[\\/?<>:*|\x00-\x1f]", name):
            return False
        lowered = name.casefold()
        if lowered.startswith(".pad") or lowered.startswith("____padding"):
            return False
        stem = name.split(".", 1)[0].upper()
        reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{number}" for number in range(1, 10)), *(f"LPT{number}" for number in range(1, 10))}
        return stem not in reserved

    @staticmethod
    def _image_details(path_value: str) -> tuple[Path, str, tuple[int, int]] | None:
        path = Path(path_value)
        try:
            if UnwalledValidationMixin._has_symlink_component(path) or not path.is_file() or path.stat().st_size >= 1024 * 1024:
                return None
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(path) as image:
                    image_format = str(image.format or "")
                    image_size = image.size
                    if image_size[0] > 3840 or image_size[1] > 3840 or image_size[0] * image_size[1] > 16_000_000:
                        return None
                    image.verify()
                    return path, image_format, image_size
        except OSError, SyntaxError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning:
            return None

    @classmethod
    def _valid_torrent_paths(cls, meta: Meta) -> bool:
        root = Path(str(meta.path or ""))
        if cls._has_symlink_component(root) or not root.exists():
            return False
        base = root if root.is_dir() else root.parent
        try:
            resolved_base = base.resolve(strict=True)
        except OSError:
            return False
        if root.is_dir() and not cls._valid_filename(root.name):
            return False
        for file_value in meta.filelist:
            file_path = Path(str(file_value))
            if cls._has_symlink_component(file_path) or not file_path.is_file():
                return False
            try:
                relative_path = file_path.resolve(strict=True).relative_to(resolved_base)
            except OSError, ValueError:
                return False
            current_path = base
            for component in relative_path.parts:
                current_path /= component
                if current_path.is_symlink() or not cls._valid_filename(component):
                    return False
        return True

    @staticmethod
    def _valid_announce_url(value: str) -> bool:
        try:
            parsed = urlsplit(value)
            token = parsed.path.removeprefix("/announce/")
            return (
                parsed.scheme == "https"
                and parsed.hostname == "unwalled.cc"
                and parsed.port in (None, 443)
                and parsed.username is None
                and parsed.password is None
                and parsed.query == ""
                and parsed.fragment == ""
                and parsed.path == f"/announce/{token}"
                and re.fullmatch(r"[A-Za-z0-9_-]+", token) is not None
            )
        except ValueError:
            return False

    @staticmethod
    def _torrent_metainfo(path: Path) -> tuple[dict[bytes, object], dict[bytes, object]] | None:
        try:
            if path.is_symlink() or not path.is_file() or path.stat().st_size >= 1024 * 1024:
                return None
            decoded = bdecode(path.read_bytes())
        except OSError, RecursionError, ValueError, bencodepy.BencodeDecodeError:
            return None
        if not isinstance(decoded, dict):
            return None
        metainfo = cast(dict[bytes, object], decoded)
        raw_info = metainfo.get(b"info")
        if not isinstance(raw_info, dict):
            return None
        return metainfo, cast(dict[bytes, object], raw_info)

    @classmethod
    def _valid_v1_info(cls, info: dict[bytes, object]) -> bool:
        raw_name = info.get(b"name")
        piece_length = info.get(b"piece length")
        pieces = info.get(b"pieces")
        if (
            not isinstance(raw_name, bytes)
            or not isinstance(piece_length, int)
            or isinstance(piece_length, bool)
            or not 16 * 1024 <= piece_length <= 128 * 1024 * 1024
            or piece_length & (piece_length - 1) != 0
        ):
            return False
        if not isinstance(pieces, bytes) or not pieces or len(pieces) % 20 != 0 or b"meta version" in info or b"file tree" in info:
            return False
        try:
            name = raw_name.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            return False
        if not cls._valid_filename(name):
            return False
        has_length = b"length" in info
        has_files = b"files" in info
        if has_length == has_files:
            return False
        if has_length:
            length = info.get(b"length")
            if not isinstance(length, int) or isinstance(length, bool) or length < 0:
                return False
            return len(pieces) // 20 == (length + piece_length - 1) // piece_length
        raw_files = info.get(b"files")
        if not isinstance(raw_files, list) or not raw_files:
            return False
        total_length = 0
        for raw_file in cast(list[object], raw_files):
            if not isinstance(raw_file, dict):
                return False
            file_entry = cast(dict[bytes, object], raw_file)
            length = file_entry.get(b"length")
            raw_path = file_entry.get(b"path")
            attr = file_entry.get(b"attr", b"")
            if not isinstance(length, int) or isinstance(length, bool) or length < 0 or not isinstance(raw_path, list) or not raw_path:
                return False
            if isinstance(attr, bytes) and b"l" in attr:
                return False
            total_length += length
            for raw_component in cast(list[object], raw_path):
                if not isinstance(raw_component, bytes):
                    return False
                try:
                    component = raw_component.decode("utf-8", errors="strict")
                except UnicodeDecodeError:
                    return False
                if component in {".", ".."} or not cls._valid_filename(component):
                    return False
        return len(pieces) // 20 == (total_length + piece_length - 1) // piece_length

    @classmethod
    def _torrent_matches_files(cls, info: dict[bytes, object], meta: Meta) -> bool:
        root = Path(str(meta.path or ""))
        try:
            if cls._has_symlink_component(root) or not root.exists():
                return False
            raw_name = info.get(b"name")
            if not isinstance(raw_name, bytes) or raw_name.decode("utf-8", errors="strict") != root.name:
                return False
            if root.is_file():
                length = info.get(b"length")
                return len(meta.filelist) == 1 and Path(str(meta.filelist[0])).resolve(strict=True) == root.resolve(strict=True) and length == root.stat().st_size
            expected = {
                tuple(path.resolve(strict=True).relative_to(root.resolve(strict=True)).parts): path.stat().st_size
                for value in meta.filelist
                if (path := Path(str(value))).is_file() and not cls._has_symlink_component(path)
            }
            if len(expected) != len(meta.filelist):
                return False
            actual: dict[tuple[str, ...], int] = {}
            raw_files = info.get(b"files")
            if not isinstance(raw_files, list):
                return False
            for raw_file in cast(list[object], raw_files):
                if not isinstance(raw_file, dict):
                    return False
                entry = cast(dict[bytes, object], raw_file)
                raw_path = entry.get(b"path")
                length = entry.get(b"length")
                if not isinstance(raw_path, list) or not isinstance(length, int):
                    return False
                components = tuple(component.decode("utf-8", errors="strict") for component in cast(list[bytes], raw_path))
                if components in actual:
                    return False
                actual[components] = length
            return actual == expected
        except (OSError, UnicodeDecodeError, ValueError):
            return False

    @classmethod
    def _torrent_is_v1(cls, path: Path) -> bool:
        torrent = cls._torrent_metainfo(path)
        return torrent is not None and cls._valid_v1_info(torrent[1])

    @staticmethod
    def _file_digest(path: Path) -> bytes:
        with path.open("rb") as source:
            return hashlib.file_digest(source, "sha256").digest()

    def _valid_artwork(self, meta: Meta) -> bool:
        cover = self._image_details(meta.artwork_path)
        banner = self._image_details(str(meta.artwork_banner_path or ""))
        if cover is None or cover[1] != "JPEG" or cover[2][0] != cover[2][1] or cover[2][0] < 400:
            logger.info(f"{self.tracker}: [bold red]Cover must be a square JPEG of at least 400x400.[/bold red]")
            return False
        banner_ratio = banner[2][0] / banner[2][1] if banner and banner[2][1] else 0
        if banner is None or banner[1] != "JPEG" or banner[2][0] < 960 or banner[2][1] < 540 or abs(banner_ratio - (16 / 9)) > 0.03:
            logger.info(f"{self.tracker}: [bold red]Banner must be a 16:9 JPEG of at least 960x540.[/bold red]")
            return False
        if cover[0].resolve() == banner[0].resolve() or self._file_digest(cover[0]) == self._file_digest(banner[0]):
            logger.info(f"{self.tracker}: [bold red]Cover and banner must be different images.[/bold red]")
            return False
        return True

    def _valid_upload_bundle(self, meta: Meta, torrent_path: Path) -> bool:
        torrent = self._torrent_metainfo(torrent_path)
        if torrent is None or not self._valid_v1_info(torrent[1]) or not self._torrent_matches_files(torrent[1], meta):
            logger.info(f"{self.tracker}: [bold red]Unwalled requires a valid V1 torrent.[/bold red]")
            return False
        metainfo, info = torrent
        raw_announce = metainfo.get(b"announce", b"")
        try:
            announce = raw_announce.decode("utf-8", errors="strict") if isinstance(raw_announce, bytes) else ""
        except UnicodeDecodeError:
            return False
        expected_announce = announce == "https://fake.tracker" if meta.debug else self._valid_announce_url(announce)
        if info.get(b"private") != 1 or info.get(b"source") != b"Unwalled" or not expected_announce:
            logger.info(f"{self.tracker}: [bold red]The upload torrent is missing required Unwalled private metadata.[/bold red]")
            return False
        if not self._valid_artwork(meta):
            return False
        paths = (torrent_path, Path(meta.artwork_path), Path(str(meta.artwork_banner_path or "")))
        if any(self._has_symlink_component(path) or not path.is_file() for path in paths) or sum(path.stat().st_size for path in paths) >= 1024 * 1024:
            logger.info(f"{self.tracker}: [bold red]Torrent, cover and banner must total less than 1 MiB.[/bold red]")
            return False
        return True
