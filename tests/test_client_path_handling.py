# ruff: noqa: S101

import asyncio
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import bencode

from src.clients import Clients
from src.meta import Meta
from src.torrent_clients.path_utils import coerce_str_list, is_path_under, map_save_path, tracker_directory
from src.torrent_clients.qbittorrent import create_cross_seed_links


def test_qbittorrent_coerce_str_list_parses_stringified_paths() -> None:
    assert coerce_str_list("['/local', '/remote']") == ["/local", "/remote"]
    assert coerce_str_list("/local") == ["/local"]


def test_qbittorrent_map_save_path_accepts_path_objects() -> None:
    mapped_path = map_save_path(Path("/local/links/AMIGOSSHARE"), Path("/local"), Path("/remote"))

    assert mapped_path == "/remote/links/AMIGOSSHARE/"


def test_map_save_path_does_not_rewrite_sibling_paths() -> None:
    mapped_path = map_save_path("/locality/release", "/local", "/remote")

    assert mapped_path == "/locality/release/"


def test_map_save_path_preserves_case_insensitive_mapping_and_client_format() -> None:
    assert map_save_path("/Local/Release", "/local", "/remote") == "/remote/Release/"
    assert map_save_path("/local/Release", "/local", "/remote", trailing_slash=False) == "/remote/Release"


def test_clients_remote_path_map_parses_stringified_path_lists() -> None:
    async def exercise() -> tuple[str, str]:
        clients = Clients({"TORRENT_CLIENTS": {}})
        meta = Meta({"path": "/local/content/release"})
        return await clients.remote_path_map(
            meta,
            {"local_path": "['/local', '/other']", "remote_path": "['/remote', '/elsewhere']"},
        )

    assert asyncio.run(exercise()) == (os.path.normpath("/local"), os.path.normpath("/remote"))


def test_rtorrent_coerce_str_list_parses_stringified_paths() -> None:
    assert coerce_str_list("['/local', '/remote']") == ["/local", "/remote"]


def test_rtorrent_keeps_multifile_release_directory_as_base(tmp_path: Path) -> None:
    for category in ("BOOK", "GAME"):
        release_dir = tmp_path / category
        release_dir.mkdir()
        filelist = [release_dir / "part1.bin", release_dir / "part2.bin"]
        for file_path in filelist:
            file_path.write_bytes(b"x")

        torrent_path = tmp_path / f"{category}.torrent"
        bencode.bwrite(
            {
                "announce": "https://tracker.invalid/announce",
                "info": {
                    "files": [
                        {"length": 1, "path": ["part1.bin"]},
                        {"length": 1, "path": ["part2.bin"]},
                    ],
                    "name": category,
                    "piece length": 1,
                    "pieces": b"0" * 40,
                },
            },
            str(torrent_path),
        )

        start_verbose = Mock()
        rtorrent_server = SimpleNamespace(load=SimpleNamespace(start_verbose=start_verbose))
        meta = Meta(
            {
                "category": category,
                "filelist": [str(file_path) for file_path in filelist],
                "path": str(release_dir),
            }
        )
        with (
            patch("src.torrent_clients.rtorrent.xmlrpc.client.Server", return_value=rtorrent_server),
            patch("src.torrent_clients.rtorrent.time.sleep"),
        ):
            Clients({}).rtorrent(
                str(release_dir),
                str(torrent_path),
                SimpleNamespace(),
                meta,
                str(tmp_path),
                str(tmp_path),
                {"linking": None, "rtorrent_label": None, "rtorrent_url": "https://rtorrent.invalid"},
                "TRACKER",
            )

        assert start_verbose.call_args.args[2] == f"d.directory_base.set={release_dir}"


def test_tracker_directory_falls_back_to_tracker_name() -> None:
    assert tracker_directory("/links", "", "AMIGOSSHARE") == Path("/links/AMIGOSSHARE")


def test_tracker_directory_rejects_paths_outside_link_root() -> None:
    for directory_name in (
        "/outside/exposed",
        "../exposed",
        "nested/exposed",
        "C:tmp",
        "C:",
        "C:/tmp",
        "C:\\tmp",
        "CON",
        "NUL",
        "AUX",
        "COM1",
        "LPT1",
        "CON.txt",
        "CON.foo.bar",
        "NUL.tar.gz",
        "COM1.backup.txt",
        "LPT9.archive.part",
    ):
        try:
            tracker_directory("/links", directory_name, "AMIGOSSHARE")
        except ValueError:
            continue
        raise AssertionError(f"accepted unsafe tracker directory: {directory_name}")


def test_automatic_management_paths_require_path_boundaries() -> None:
    assert is_path_under("/media/local/release", "/media/local")
    assert not is_path_under("/media/locality/release", "/media/local")


def test_cross_seed_links_normalize_component_paths(tmp_path: Path) -> None:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "episode.mkv").write_bytes(b"episode")
    torrent = SimpleNamespace(
        metainfo={
            "info": {
                "name": "Release",
                "files": [{"path": ["Season 1", "episode.mkv"], "length": 7}],
            }
        },
        name="Release",
    )
    meta = Meta({"path": str(source_dir), "filelist": [str(source_dir / "episode.mkv")]})

    async def exercise() -> bool:
        with patch("src.torrent_clients.qbittorrent.async_link_directory", new=AsyncMock(return_value=True)):
            return await create_cross_seed_links(meta, torrent, str(tmp_path / "tracker"), use_hardlink=False)

    assert asyncio.run(exercise())
