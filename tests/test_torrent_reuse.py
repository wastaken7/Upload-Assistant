from types import SimpleNamespace

import pytest

from src.clients import Clients
from src.meta import Meta
from src.torrentcreate import TorrentCreator


@pytest.mark.asyncio
async def test_base_subs_contains_external_subtitle_with_custom_torrent(tmp_path):
    video = tmp_path / "release.mkv"
    subtitle = tmp_path / "release.pt-BR.srt"
    video.write_bytes(b"video data")
    subtitle.write_text("subtitle data", encoding="utf-8")

    meta = Meta(
        {
            "base_dir": str(tmp_path),
            "uuid": "test-release",
            "path": str(video),
            "filelist": [str(video)],
            "subtitle_files": [str(subtitle)],
            "category": "MOVIE",
            "isdir": False,
            "is_disc": "",
            "keep_folder": False,
            "mkbrr": False,
            "max_piece_size": 1,
            "trackers": [],
        }
    )
    (tmp_path / "tmp" / meta.uuid).mkdir(parents=True)

    await TorrentCreator.create_torrent(meta, video, "BASE_SUBS")

    from torf import Torrent

    torrent = Torrent.read(tmp_path / "tmp" / meta.uuid / "BASE_SUBS.torrent")
    assert sorted(path.name for path in torrent.files) == sorted([video.name, subtitle.name])  # noqa: S101


@pytest.mark.asyncio
async def test_reuse_validation_rejects_same_basenames_in_different_layouts(tmp_path, monkeypatch):
    torrent_path = tmp_path / "candidate.torrent"
    torrent_path.write_bytes(b"placeholder")
    local_files = [tmp_path / "release" / "season-01" / "episode.mkv", tmp_path / "release" / "season-02" / "episode.mkv"]
    for path in local_files:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"video")

    fake_torrent = SimpleNamespace(files=["Release/episode.mkv", "Release/bonus/episode.mkv"])
    monkeypatch.setattr("src.clients.Torrent.read", lambda _path: fake_torrent)

    meta = Meta(
        {
            "path": str(tmp_path / "release"),
            "filelist": [str(path) for path in local_files],
            "subtitle_files": [],
            "is_disc": "",
            "keep_folder": False,
            "isdir": True,
            "uuid": "release",
            "debug": False,
        }
    )
    client = Clients({"DEFAULT": {}, "TORRENT_CLIENTS": {}})

    valid, _ = await client.is_valid_torrent(meta, str(torrent_path), "hash", "qbit", {})

    assert not valid  # noqa: S101


@pytest.mark.asyncio
async def test_client_search_prefers_torrent_with_all_local_subtitles(tmp_path, monkeypatch):
    video_only = tmp_path / "video-only.torrent"
    with_subtitles = tmp_path / "with-subtitles.torrent"
    video_only.touch()
    with_subtitles.touch()
    subtitle = tmp_path / "release.srt"
    subtitle.touch()

    torrents = {
        str(video_only): SimpleNamespace(files=["release.mkv"]),
        str(with_subtitles): SimpleNamespace(files=["release.mkv", "release.srt"]),
    }
    monkeypatch.setattr("src.clients.Torrent.read", lambda path: torrents[str(path)])

    async def fake_search(_self, _meta, client_name, *_args):
        return str(video_only) if client_name == "first" else str(with_subtitles)

    monkeypatch.setattr(Clients, "_search_single_client_for_torrent", fake_search)
    config = {
        "DEFAULT": {"default_torrent_client": "first", "searching_client_list": ["first", "second"], "prefer_max_16_torrent": False},
        "TRACKERS": {},
        "TORRENT_CLIENTS": {"first": {}, "second": {}},
    }
    meta = Meta({"client": "none", "subtitle_files": [str(subtitle)]})

    found = await Clients(config).find_existing_torrent(meta)

    assert found == str(with_subtitles)  # noqa: S101
