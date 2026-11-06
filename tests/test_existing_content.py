# ruff: noqa: S101

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from qbittorrentapi import TorrentFilesList, TorrentInfoList
from torf import Torrent

from src.clients import Clients
from src.meta import Meta
from src.torrent_clients.existing_content import (
    ExistingContentMatch,
    existing_content_mode,
    join_client_path,
    match_content_layout,
    MAX_CANDIDATES,
    select_candidates,
    torrent_file_entries,
)
from src.torrent_clients.qbittorrent import QbitAccess

PROXY_URL = "https://qui.invalid/proxy/fictionalproxykey123"
GIB = 1024**3


def _file(name: str, size: int, progress: float = 1.0) -> dict[str, object]:
    return {"name": name, "size": size, "progress": progress}


def _release(tmp_path: Path, *, subtitle: bool = True) -> tuple[Path, Path, Torrent]:
    release = tmp_path / "Fictional.Movie.2025-GROUP"
    release.mkdir()
    video = release / "fictional.mkv"
    video.write_bytes(b"fictional video")
    if subtitle:
        (release / "fictional.srt").write_text("fictional subtitle", encoding="utf-8")
    torrent = Torrent(path=release)
    torrent.generate()
    return release, video, torrent


@pytest.mark.parametrize(
    ("value", "expected"),
    [("prefer", "prefer"), (" Require ", "require"), (True, "prefer"), ("", ""), (None, ""), (False, ""), ("always", "")],
)
def test_existing_content_mode(value: object, expected: str) -> None:
    assert existing_content_mode({"match_existing_content": value}) == expected


def test_torrent_file_entries_use_the_original_layout(tmp_path: Path) -> None:
    _release_dir, _video, torrent = _release(tmp_path)
    assert sorted(torrent_file_entries(torrent)) == [
        ("Fictional.Movie.2025-GROUP/fictional.mkv", 15),
        ("Fictional.Movie.2025-GROUP/fictional.srt", 18),
    ]


def test_match_same_layout_ignores_extra_files() -> None:
    expected = [("Fictional.Movie/movie.mkv", 100), ("Fictional.Movie/movie.srt", 5)]
    files = [_file("Fictional.Movie/movie.mkv", 100), _file("Fictional.Movie/movie.srt", 5), _file("Fictional.Movie/movie.nfo", 1)]
    assert match_content_layout(expected, True, files) == ("", "Original")


def test_match_single_file_inside_a_client_folder() -> None:
    files = [_file("Fictional.Movie/movie.mkv", 100), _file("Fictional.Movie/movie.nfo", 1)]
    assert match_content_layout([("movie.mkv", 100)], False, files) == ("Fictional.Movie", "Original")


def test_match_multi_file_under_another_root_uses_no_subfolder() -> None:
    expected = [("Fictional.Movie/movie.mkv", 100), ("Fictional.Movie/movie.srt", 5)]
    files = [_file("Other.Name/movie.mkv", 100), _file("Other.Name/movie.srt", 5)]
    assert match_content_layout(expected, True, files) == ("Other.Name", "NoSubfolder")


def test_match_prefers_the_shortest_folder() -> None:
    files = [_file("Extras/movie.mkv", 100), _file("movie.mkv", 100)]
    assert match_content_layout([("movie.mkv", 100)], False, files) == ("", "Original")


@pytest.mark.parametrize(
    "files",
    [
        [_file("Fictional.Movie/movie.mkv", 101), _file("Fictional.Movie/movie.srt", 5)],
        [_file("Fictional.Movie/movie.mkv", 100, progress=0.5), _file("Fictional.Movie/movie.srt", 5)],
        [_file("Fictional.Movie/movie.mkv", 100)],
        [_file("Fictional.Movie/movie.mkv", 100), _file("Elsewhere/movie.srt", 5)],
    ],
)
def test_match_rejects_missing_incomplete_or_resized_files(files: list[dict[str, object]]) -> None:
    expected = [("Fictional.Movie/movie.mkv", 100), ("Fictional.Movie/movie.srt", 5)]
    assert match_content_layout(expected, True, files) is None


def test_select_candidates_keeps_complete_torrents_of_a_compatible_size() -> None:
    torrents = [
        {"hash": "a", "name": "Other", "save_path": "/data", "total_size": 10 * GIB + 1024, "progress": 1, "state": "stalledUP"},
        {"hash": "b", "name": "Fictional", "save_path": "/data", "total_size": 10 * GIB, "progress": 1, "state": "uploading"},
        {"hash": "c", "name": "Fictional", "save_path": "/data", "total_size": 10 * GIB, "progress": 0.9, "state": "downloading"},
        {"hash": "d", "name": "Fictional", "save_path": "/data", "total_size": 10 * GIB, "progress": 1, "state": "missingFiles"},
        {"hash": "e", "name": "Fictional", "save_path": "/data", "total_size": 9 * GIB, "progress": 1, "state": "stalledUP"},
        {"hash": "f", "name": "Fictional", "save_path": "/data", "total_size": 12 * GIB, "progress": 1, "state": "stalledUP"},
        {"hash": "g", "name": "Fictional", "save_path": "", "total_size": 10 * GIB, "progress": 1, "state": "stalledUP"},
    ]
    assert [info["hash"] for info in select_candidates(torrents, 10 * GIB, "Fictional")] == ["b", "a"]


def test_select_candidates_checks_same_name_copies_before_the_limit() -> None:
    crowd = [
        {"hash": f"other{i}", "name": f"Other.{i}", "save_path": "/data", "total_size": 10 * GIB + i, "progress": 1, "state": "stalledUP"}
        for i in range(MAX_CANDIDATES + 5)
    ]
    # Our copy also holds a sample, so it is bigger than every unrelated torrent.
    copy = {"hash": "mine", "name": "Fictional", "save_path": "/data", "total_size": 10 * GIB + 200 * 1024**2, "progress": 1, "state": "stalledUP"}
    selected = select_candidates([*crowd, copy], 10 * GIB, "Fictional")
    assert len(selected) == MAX_CANDIDATES
    assert selected[0]["hash"] == "mine"


@pytest.mark.parametrize(
    ("save_path", "prefix", "expected"),
    [
        ("/data/seed/", "", "/data/seed/"),
        ("/data/seed/", "Folder/Sub", "/data/seed/Folder/Sub"),
        ("D:\\Seed\\", "Folder/Sub", "D:\\Seed\\Folder\\Sub"),
        ("D:/Seed", "Folder", "D:/Seed/Folder"),
    ],
)
def test_join_client_path_keeps_the_client_separator(save_path: str, prefix: str, expected: str) -> None:
    assert join_client_path(save_path, prefix) == expected


class _FakeQbit:
    """Answers with qbittorrentapi's own list types, which are UserLists rather than lists."""

    def __init__(self, torrents: list[dict[str, object]], files: dict[str, list[dict[str, object]]]) -> None:
        self._torrents = torrents
        self._files = files
        self.files_requested: list[str] = []

    def torrents_info(self, torrent_hashes: str | None = None) -> TorrentInfoList:
        return TorrentInfoList([info for info in self._torrents if torrent_hashes in (None, info["hash"])])

    def torrents_files(self, torrent_hash: str) -> TorrentFilesList:
        self.files_requested.append(torrent_hash)
        return TorrentFilesList(self._files[torrent_hash])


@pytest.mark.asyncio
async def test_find_existing_content_through_the_webui(tmp_path: Path) -> None:
    _release_dir, _video, torrent = _release(tmp_path)
    qbit = _FakeQbit(
        [
            # Same name and closer in size, but holding other files: checked first and rejected.
            {"hash": "other", "name": "Fictional.Movie.2025-GROUP", "save_path": "/seed", "total_size": torrent.size, "progress": 1, "state": "stalledUP"},
            {"hash": "copy", "name": "Fictional.Movie.2025-GROUP", "save_path": "/seed/movies", "total_size": torrent.size + 7, "progress": 1, "state": "stalledUP"},
        ],
        {
            "other": [_file("Unrelated/fictional.mkv", 15), _file("Unrelated/other.srt", 18)],
            "copy": [
                _file("Fictional.Movie.2025-GROUP/fictional.mkv", 15),
                _file("Fictional.Movie.2025-GROUP/fictional.srt", 18),
                _file("Fictional.Movie.2025-GROUP/fictional.nfo", 7),
            ],
        },
    )
    clients = Clients({})
    access = QbitAccess({}, qbt_client=qbit)

    match = await clients._find_existing_content(access, torrent)

    assert match == ExistingContentMatch("copy", "Fictional.Movie.2025-GROUP", "/seed/movies", "Original")
    assert qbit.files_requested == ["other", "copy"]


@pytest.mark.asyncio
async def test_find_existing_content_through_qui(tmp_path: Path) -> None:
    _release_dir, video, torrent = _release(tmp_path, subtitle=False)
    torrent = Torrent(path=video)
    torrent.generate()

    async def get(url: str, params: dict[str, str]) -> httpx.Response:
        if url == f"{PROXY_URL}/api/v2/torrents/info":
            body = [{"hash": "copy", "name": "Folder", "save_path": "/seed", "size": torrent.size, "progress": 1, "state": "uploading"}]
        else:
            assert params == {"hash": "copy"}
            body = [_file("Folder/fictional.mkv", 15)]
        return httpx.Response(200, json=body, request=httpx.Request("GET", url))

    access = QbitAccess({"qui_proxy_url": PROXY_URL}, PROXY_URL, SimpleNamespace(get=get))
    match = await Clients({})._find_existing_content(access, torrent)

    assert match == ExistingContentMatch("copy", "Folder", "/seed/Folder", "Original")


def _qbit_patches(clients: Clients, add: AsyncMock, qbit: object):
    return (
        patch.object(clients, "init_qbittorrent_client", AsyncMock(return_value=qbit)),
        patch.object(clients, "_add_torrent_direct", add),
        patch.object(clients, "_report_added_torrent_state", AsyncMock()),
    )


@pytest.mark.asyncio
async def test_matched_client_seeds_from_its_own_copy_without_linking_or_mapping(tmp_path: Path) -> None:
    release, video, torrent = _release(tmp_path)
    meta = Meta({"path": str(release), "filelist": [str(video)]})
    clients = Clients({"TRACKERS": {"EXAMPLE": {}}})
    match = ExistingContentMatch("copy", "Other.Name", "/seed/Other.Name", "NoSubfolder")
    config = {"match_existing_content": "require", "linking": "hardlink", "linked_folder": [str(tmp_path / "links")], "content_layout": "Original"}
    add = AsyncMock()
    qbit = _FakeQbit([{"hash": torrent.infohash}], {})
    init, add_patch, report = _qbit_patches(clients, add, qbit)

    with init, add_patch, report, patch.object(clients, "_find_existing_content", AsyncMock(return_value=match)):
        result = await clients.qbittorrent(str(release), torrent, str(tmp_path), "/mapped", config, "", meta.filelist, meta, "EXAMPLE", client_name="seedbox")

    assert result is True
    kwargs = add.call_args.args[2]
    assert kwargs["save_path"] == "/seed/Other.Name"
    assert kwargs["content_layout"] == "NoSubfolder"
    assert kwargs["use_auto_torrent_management"] is False
    assert not (tmp_path / "links").exists()


@pytest.mark.asyncio
async def test_require_skips_a_client_without_a_copy(tmp_path: Path) -> None:
    release, video, torrent = _release(tmp_path)
    meta = Meta({"path": str(release), "filelist": [str(video)]})
    clients = Clients({"TRACKERS": {"EXAMPLE": {}}})
    add = AsyncMock()
    init, add_patch, report = _qbit_patches(clients, add, object())

    with init, add_patch, report, patch.object(clients, "_find_existing_content", AsyncMock(return_value=None)):
        result = await clients.qbittorrent(
            str(release), torrent, str(tmp_path), str(tmp_path), {"match_existing_content": "require"}, "", meta.filelist, meta, "EXAMPLE"
        )

    assert result is None
    add.assert_not_awaited()


@pytest.mark.asyncio
async def test_prefer_falls_back_to_the_path_mapping(tmp_path: Path) -> None:
    release, video, torrent = _release(tmp_path)
    meta = Meta({"path": str(release), "filelist": [str(video)]})
    clients = Clients({"TRACKERS": {"EXAMPLE": {}}})
    add = AsyncMock()
    qbit = _FakeQbit([{"hash": torrent.infohash}], {})
    init, add_patch, report = _qbit_patches(clients, add, qbit)

    with init, add_patch, report, patch.object(clients, "_find_existing_content", AsyncMock(return_value=None)):
        result = await clients.qbittorrent(
            str(release), torrent, str(tmp_path), "/remote", {"match_existing_content": "prefer"}, "", meta.filelist, meta, "EXAMPLE"
        )

    assert result is True
    assert add.call_args.args[2]["save_path"] == "/remote/"


@pytest.mark.asyncio
@pytest.mark.parametrize("allow_fallback", [True, False])
async def test_missing_linked_folder_follows_allow_fallback(tmp_path: Path, allow_fallback: bool) -> None:
    release, video, torrent = _release(tmp_path)
    meta = Meta({"path": str(release), "filelist": [str(video)]})
    clients = Clients({"TRACKERS": {"EXAMPLE": {}}})
    config = {"linking": "hardlink", "linked_folder": [], "allow_fallback": allow_fallback}
    add = AsyncMock()
    init, add_patch, report = _qbit_patches(clients, add, _FakeQbit([{"hash": torrent.infohash}], {}))

    with init, add_patch, report:
        if allow_fallback:
            assert await clients.qbittorrent(str(release), torrent, str(tmp_path), str(tmp_path), config, "", meta.filelist, meta, "EXAMPLE") is True
            assert Path(add.call_args.args[2]["save_path"]) == tmp_path
        else:
            with pytest.raises(ValueError, match="No suitable linked folder"):
                await clients.qbittorrent(str(release), torrent, str(tmp_path), str(tmp_path), config, "", meta.filelist, meta, "EXAMPLE")
            add.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(("states", "warned"), [(["checkingResumeData", "missingFiles"], True), (["error"], True), (["stalledUP"], False)])
async def test_added_torrent_state_warns_about_missing_files(states: list[str], warned: bool) -> None:
    replies = iter([[{"hash": "abc", "state": state, "save_path": "/seed"}] for state in states])
    qbit = SimpleNamespace(torrents_info=lambda torrent_hashes: next(replies))
    clients = Clients({})

    with patch("src.torrent_clients.qbittorrent.logger") as log, patch("src.torrent_clients.qbittorrent.asyncio.sleep", AsyncMock()):
        await clients._report_added_torrent_state(QbitAccess({}, qbt_client=qbit), "abc", "/seed/", "EXAMPLE")

    messages = [str(call.args[0]) for call in log.info.call_args_list]
    assert any(f"'{states[-1]}'" in message and "/seed/" in message for message in messages) is warned


def test_skipped_client_is_neither_counted_nor_failed(tmp_path: Path) -> None:
    qbit = {"torrent_client": "qbit"}
    clients = Clients(
        {"DEFAULT": {"injecting_client_list": ["local", "seedbox"]}, "TRACKERS": {"TEST": {}}, "TORRENT_CLIENTS": {"local": qbit, "seedbox": dict(qbit)}}
    )
    meta = Meta(base_dir=str(tmp_path), uuid="fictional-release", path=str(tmp_path / "video.mkv"), client=None)
    torrent_path = tmp_path / "tmp" / meta.uuid / "[TEST].torrent"
    torrent_path.parent.mkdir(parents=True)
    torrent_path.touch()

    with (
        patch("src.clients.Torrent.read"),
        patch.object(clients, "remote_path_map", new=AsyncMock(return_value=(None, None))),
        patch.object(clients, "inject_delay", new=AsyncMock()),
        patch.object(clients, "qbittorrent", new=AsyncMock(side_effect=[True, None])) as add,
        patch("src.clients.record_event_async", new_callable=AsyncMock) as recorder,
    ):
        asyncio.run(clients.add_to_client(meta, "TEST"))

    assert [call.kwargs["client_name"] for call in add.await_args_list] == ["local", "seedbox"]
    assert [(call.kwargs["service"], call.kwargs["outcome"]) for call in recorder.await_args_list] == [("local", "success")]
