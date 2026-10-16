# ruff: noqa: S101

import asyncio
import os
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import bencode
import pytest
from torf import Torrent

from src.clients import Clients
from src.meta import Meta
from src.torrent_clients.path_utils import coerce_str_list, is_path_under, map_save_path, tracker_directory
from src.torrent_clients.qbittorrent import _link_torrent_files, create_cross_seed_links


@pytest.mark.asyncio
async def test_qbittorrent_rejects_mismatched_loose_file_root_without_linking(tmp_path):
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    video = downloads / "fictional.mkv"
    video.write_bytes(b"fictional video")
    torrent = Torrent(path=downloads)
    torrent.name = "Fictional.Movie.2025"
    torrent.generate()
    meta = Meta({"path": str(video), "filelist": [str(video)], "isdir": False})
    client = Clients({})
    with patch.object(client, "init_qbittorrent_client", AsyncMock()) as init_client, pytest.raises(ValueError, match="does not match source directory"):
        await client.qbittorrent(str(video), torrent, str(tmp_path), str(tmp_path), {}, "", meta.filelist, meta, "EXAMPLE")
    init_client.assert_not_awaited()


@pytest.mark.asyncio
async def test_shared_directory_links_only_torrent_files_with_different_root_name(tmp_path):
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    video = downloads / "fictional.mkv"
    subtitle = downloads / "fictional.srt"
    unrelated = downloads / "unrelated.mkv"
    for file in (video, subtitle, unrelated):
        file.write_bytes(file.name.encode())
    torrent = Torrent(path=downloads, exclude_globs=["*unrelated*"])
    torrent.name = "Fictional.Movie.2025"
    torrent.generate()
    links = tmp_path / "links"
    assert await _link_torrent_files(torrent, downloads, links, use_hardlink=True)
    assert await _link_torrent_files(torrent, downloads, links, use_hardlink=True)
    assert sorted(file.name for file in (links / torrent.name).iterdir()) == sorted([video.name, subtitle.name])
    for file in (video, subtitle):
        assert (links / torrent.name / file.name).read_bytes() == file.read_bytes()


@pytest.mark.asyncio
async def test_torrent_links_validate_all_sources_before_creating_links(tmp_path):
    release = tmp_path / "release"
    release.mkdir()
    video = release / "fictional.mkv"
    subtitle = release / "fictional.srt"
    video.write_bytes(b"video")
    subtitle.write_bytes(b"subtitle")
    torrent = Torrent(path=release)
    torrent.generate()
    subtitle.unlink()
    with patch("src.torrent_clients.qbittorrent.async_link_directory", AsyncMock()) as link:
        assert not await _link_torrent_files(torrent, release, tmp_path / "links", use_hardlink=True)
    link.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("file_path", ["release/../outside.mkv", "../outside.mkv"])
async def test_torrent_links_reject_paths_outside_roots(tmp_path, file_path):
    release = tmp_path / "release"
    release.mkdir()
    (tmp_path / "outside.mkv").write_bytes(b"outside")
    torrent = SimpleNamespace(name="release", files=[file_path])
    with patch("src.torrent_clients.qbittorrent.async_link_directory", AsyncMock()) as link:
        assert not await _link_torrent_files(torrent, release, tmp_path / "links", use_hardlink=True)
    link.assert_not_awaited()


@pytest.mark.asyncio
async def test_torrent_links_reject_existing_different_file(tmp_path):
    release = tmp_path / "release"
    release.mkdir()
    video = release / "fictional.mkv"
    video.write_bytes(b"source")
    torrent = Torrent(path=release)
    torrent.generate()
    links = tmp_path / "links"
    destination = links / release.name / video.name
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"different file")
    with patch("src.torrent_clients.qbittorrent.async_link_directory", AsyncMock()) as link:
        assert not await _link_torrent_files(torrent, release, links, use_hardlink=True)
    link.assert_not_awaited()
    assert destination.read_bytes() == b"different file"


@pytest.mark.asyncio
@pytest.mark.parametrize("layout", ["singlefile", "multifile-video", "multifile-subtitles"])
@pytest.mark.parametrize("file_input", [False, True])
@pytest.mark.parametrize("keep_folder", [False, True])
@pytest.mark.parametrize("linking", [None, "hardlink", "symlink"])
@pytest.mark.parametrize("use_proxy", [False, True])
@pytest.mark.parametrize("content_layout", ["Original", "NoSubfolder"])
async def test_qbittorrent_destination_matches_torrent_layout(tmp_path, layout, file_input, keep_folder, linking, use_proxy, content_layout):
    release = tmp_path / "Fictional.Movie.2025-GROUP"
    release.mkdir()
    video = release / "fictional.mkv"
    subtitle = release / "fictional.pt-BR.srt"
    video.write_bytes(b"fictional video")
    subtitle.write_text("fictional subtitle", encoding="utf-8")
    unrelated = release / "unrelated.txt"
    unrelated.write_text("not part of this torrent", encoding="utf-8")
    torrent = Torrent(
        path=video if layout == "singlefile" else release,
        exclude_globs=["*.txt", "*.srt"] if layout == "multifile-video" else ["*.txt"],
    )
    torrent.generate()
    input_path = video if file_input else release
    meta = Meta({"path": str(input_path), "filelist": [str(video)], "subtitle_files": [str(subtitle)], "keep_folder": keep_folder})
    client = Clients({"TRACKERS": {"EXAMPLE": {}}})
    add = AsyncMock()
    link = AsyncMock(return_value=True)
    session = SimpleNamespace(
        get=AsyncMock(return_value=SimpleNamespace(status_code=200, json=lambda: [{"hash": torrent.infohash}])),
        post=AsyncMock(return_value=SimpleNamespace(status_code=200)),
        aclose=AsyncMock(),
    )
    config = {"linking": linking, "linked_folder": [str(tmp_path / "links")], "content_layout": content_layout}
    if use_proxy:
        config["qui_proxy_url"] = "https://qbit.invalid"
    with (
        patch.object(client, "init_qbittorrent_client", AsyncMock(return_value=object())),
        patch.object(client, "_add_torrent_direct", add),
        patch.object(client, "_add_torrent_via_proxy", add),
        patch.object(client, "retry_qbt_operation", AsyncMock(return_value=[object()])),
        patch.object(client, "create_ssl_context_for_client", return_value=None),
        patch("src.torrent_clients.qbittorrent.httpx.AsyncClient", return_value=session),
        patch("src.torrent_clients.qbittorrent.async_link_directory", link) if linking == "symlink" else nullcontext(),
    ):
        await client.qbittorrent(
            str(input_path),
            torrent,
            str(tmp_path),
            str(tmp_path),
            config,
            "",
            meta.filelist,
            meta,
            "EXAMPLE",
        )

    add.assert_awaited_once()
    save_path = Path(add.call_args.args[3]["savepath"] if use_proxy else add.call_args.args[2]["save_path"])
    expected = tmp_path / "links" / "EXAMPLE" if linking else release if layout == "singlefile" else tmp_path
    link_base = tmp_path / "links" / "EXAMPLE"
    if layout != "singlefile" and content_layout == "NoSubfolder":
        expected = link_base / torrent.name if linking else release
    assert save_path == expected
    if linking == "symlink":
        assert link.await_count == len(torrent.files)
        for file in torrent.files:
            source = release / Path(str(file)).relative_to(torrent.name) if layout != "singlefile" else video
            link.assert_any_await(src=str(source), dst=link_base / str(file), use_hardlink=False)
    else:
        # The actual file layout must be usable by the client, including subtitles.
        for file in torrent.files:
            relative_file = Path(str(file)).relative_to(torrent.name) if layout != "singlefile" and content_layout == "NoSubfolder" else Path(str(file))
            destination = save_path / relative_file
            source = release / Path(str(file)).relative_to(torrent.name) if layout != "singlefile" else video
            assert destination.read_bytes() == source.read_bytes()
        if linking:
            assert not (link_base / release.name / unrelated.name).exists()


def test_qbittorrent_coerce_str_list_parses_stringified_paths() -> None:
    assert coerce_str_list("['/local', '/remote']") == ["/local", "/remote"]
    assert coerce_str_list("/local") == ["/local"]


def test_qbittorrent_map_save_path_accepts_path_objects() -> None:
    mapped_path = map_save_path(Path("/local/links/EXAMPLE"), Path("/local"), Path("/remote"))

    assert mapped_path == "/remote/links/EXAMPLE/"


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
    assert tracker_directory("/links", "", "EXAMPLE") == Path("/links/EXAMPLE")


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
            tracker_directory("/links", directory_name, "EXAMPLE")
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
