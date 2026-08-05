import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, patch

import bencodepy
import httpx
import pytest
from PIL import Image
from torf import Torrent

from src.args import Args
from src.meta import Meta
from src.podcast_prep import gather_podcast_prep
from src.torrentcreate import TorrentCreator
from src.trackers.common import Common
from src.trackers.UNIT3D.unwalled import Unwalled
from src.trackersetup import tracker_class_map

bdecode = cast(Callable[[bytes], object], vars(bencodepy)["decode"])
bencode = cast(Callable[[object], bytes], vars(bencodepy)["encode"])


def _tracker(**settings: object) -> Unwalled:
    tracker_settings: dict[str, object] = {"api_key": "token", "announce_url": "https://unwalled.cc/announce/test-token", **settings}
    config: dict[str, object] = {
        "DEFAULT": {"screens": 0, "img_host_1": "imgbox"},
        "TRACKERS": {"UNWALLED": tracker_settings},
    }
    return Unwalled(config)


def _jpg(path: Path, size: tuple[int, int], color: str) -> None:
    Image.new("RGB", size, color).save(path, format="JPEG")


def test_unwalled_is_registered_as_a_podcast_tracker() -> None:
    assert tracker_class_map["UNWALLED"] is Unwalled  # noqa: S101
    assert Unwalled.supported_categories == ("PODCAST",)  # noqa: S101
    assert Unwalled.source_flag == "Unwalled"  # noqa: S101


def test_cli_accepts_podcast_and_unwalled_overrides(tmp_path: Path) -> None:
    meta = Meta()
    cover = tmp_path / "cover.jpg"
    banner = tmp_path / "banner.jpg"

    parsed, _, _ = Args({"DEFAULT": {"screens": 0}}).parse(
        [
            str(tmp_path),
            "--category",
            "podcast",
            "--podcast-title",
            "Example Show [2026/MP3 - 128kbps]",
            "--podcast-cover",
            str(cover),
            "--podcast-banner",
            str(banner),
            "--unwalled-category",
            "Technology",
            "--unwalled-type",
            "Free Audio",
        ],
        meta,
    )

    assert parsed.manual_category == "podcast"  # noqa: S101
    assert parsed.podcast_title == "Example Show [2026/MP3 - 128kbps]"  # noqa: S101
    assert parsed.podcast_cover == str(cover)  # noqa: S101
    assert parsed.podcast_banner == str(banner)  # noqa: S101
    assert parsed.unwalled_category == "Technology"  # noqa: S101
    assert parsed.unwalled_type == "Free Audio"  # noqa: S101


def test_podcast_prep_rejects_mixed_audio_and_video(tmp_path: Path) -> None:
    (tmp_path / "episode.mp3").write_bytes(b"audio")
    (tmp_path / "episode.mp4").write_bytes(b"video")
    meta = Meta(path=str(tmp_path), category="PODCAST", manual_category="podcast")

    try:
        asyncio.run(gather_podcast_prep(meta))
    except ValueError as error:
        assert "mixed audio and video" in str(error).lower()  # noqa: S101
    else:
        raise AssertionError("mixed podcast media must be rejected")


def test_podcast_prep_builds_an_audio_pack_without_tmdb(tmp_path: Path) -> None:
    episode = tmp_path / "001 - Pilot.mp3"
    episode.write_bytes(b"audio")
    meta = Meta(
        path=str(tmp_path),
        base_dir=str(tmp_path),
        uuid="podcast",
        category="PODCAST",
        manual_category="podcast",
        podcast_title="Example Show [2026/MP3 - 128kbps]",
    )

    with patch("src.podcast_prep.export_info", new=AsyncMock(return_value={"media": {"track": []}})):
        asyncio.run(gather_podcast_prep(meta))

    assert meta.category == "PODCAST"  # noqa: S101
    assert meta.filelist == [str(episode.resolve())]  # noqa: S101
    assert meta.name == "Example Show [2026/MP3 - 128kbps]"  # noqa: S101
    assert meta.tmdb_id == 0 and meta.imdb_id == 0  # noqa: S101
    assert meta.resolution == ""  # noqa: S101


def test_podcast_prep_includes_allowed_companion_files(tmp_path: Path) -> None:
    episode = tmp_path / "001 - Pilot.mp3"
    companion = tmp_path / "episode-notes.pdf"
    episode.write_bytes(b"audio")
    companion.write_bytes(b"notes")
    meta = Meta(path=str(tmp_path), base_dir=str(tmp_path), uuid="podcast-companion", category="PODCAST")

    with patch("src.podcast_prep.export_info", new=AsyncMock(return_value={"media": {"track": []}})):
        asyncio.run(gather_podcast_prep(meta))

    assert meta.filelist == [str(episode.resolve()), str(companion.resolve())]  # noqa: S101


def test_podcast_prep_rejects_symlinks_and_disguised_archives(tmp_path: Path) -> None:
    external = tmp_path.parent / f"{tmp_path.name}-external.mp3"
    external.write_bytes(b"audio")
    linked = tmp_path / "linked.mp3"
    linked.symlink_to(external)
    meta = Meta(path=str(tmp_path), base_dir=str(tmp_path), uuid="podcast-symlink", category="PODCAST")

    with pytest.raises(ValueError, match="symbolic links"):
        asyncio.run(gather_podcast_prep(meta))

    linked.unlink()
    (tmp_path / "archive.mp3").write_bytes(b"PK\x03\x04" + b"archive")
    with pytest.raises(ValueError, match="compressed archive"):
        asyncio.run(gather_podcast_prep(meta))


def test_unwalled_discovers_category_and_type_ids_from_unit3d_results() -> None:
    payload: dict[str, object] = {
        "data": [
            {
                "attributes": {
                    "category": "Technology",
                    "category_id": 14,
                    "type": "Free Audio",
                    "type_id": 3,
                }
            }
        ]
    }

    assert _tracker().catalog_from_response(payload) == {"categories": {"technology": "14"}, "types": {"free audio": "3"}}  # noqa: S101


@pytest.mark.asyncio
async def test_unwalled_discovers_options_across_all_result_pages() -> None:
    first_page: list[dict[str, object]] = [{"attributes": {"category": "Technology", "category_id": 14, "type": "Free Audio", "type_id": 3}} for _ in range(100)]
    second_page: list[dict[str, object]] = [{"attributes": {"category": "Science", "category_id": 15, "type": "Premium Audio", "type_id": 4}}]

    async def handler(request: httpx.Request) -> httpx.Response:
        payload: object = first_page if request.url.params["page"] == "1" else second_page
        return httpx.Response(200, json={"data": payload})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with patch("src.trackers.UNIT3D.unwalled.httpx.AsyncClient", return_value=client):
        catalog = await _tracker().discover_options()

    assert catalog == {"categories": {"science": "15", "technology": "14"}, "types": {"free audio": "3", "premium audio": "4"}}  # noqa: S101


def test_unwalled_resolves_names_or_explicit_numeric_ids() -> None:
    tracker = _tracker()
    tracker.option_catalog = {"categories": {"technology": "14"}, "types": {"free audio": "3"}}
    named = Meta(category="PODCAST", unwalled_category="Technology", unwalled_type="Free Audio")
    numeric = Meta(category="PODCAST", unwalled_category="99", unwalled_type="42")

    assert asyncio.run(tracker.get_category_id(named)) == {"category_id": "14"}  # noqa: S101
    assert asyncio.run(tracker.get_type_id(named)) == {"type_id": "3"}  # noqa: S101
    assert asyncio.run(tracker.get_category_id(numeric)) == {"category_id": "99"}  # noqa: S101
    assert asyncio.run(tracker.get_type_id(numeric)) == {"type_id": "42"}  # noqa: S101


def test_unwalled_requires_valid_distinct_jpeg_cover_and_banner(tmp_path: Path) -> None:
    cover = tmp_path / "cover.jpg"
    banner = tmp_path / "banner.jpg"
    _jpg(cover, (500, 500), "red")
    _jpg(banner, (960, 540), "blue")
    episode = tmp_path / "001 - Pilot.mp3"
    episode.write_bytes(b"audio")
    meta = Meta(
        path=str(tmp_path),
        category="PODCAST",
        name="Example Show [2026/MP3 - 128kbps]",
        filelist=[str(episode)],
        artwork_path=str(cover),
        artwork_banner_path=str(banner),
        unwalled_category="14",
        unwalled_type="3",
    )

    assert asyncio.run(_tracker().get_additional_checks(meta)) is True  # noqa: S101
    meta.artwork_banner_path = str(cover)
    assert asyncio.run(_tracker().get_additional_checks(meta)) is False  # noqa: S101


def test_unwalled_rejects_invalid_torrent_file_names(tmp_path: Path) -> None:
    cover = tmp_path / "cover.jpg"
    banner = tmp_path / "banner.jpg"
    _jpg(cover, (500, 500), "red")
    _jpg(banner, (960, 540), "blue")
    invalid_file = tmp_path / "bad:name.mp3"
    invalid_file.write_bytes(b"audio")
    meta = Meta(
        path=str(tmp_path),
        category="PODCAST",
        name="Example Show [2026/MP3 - 128kbps]",
        filelist=[str(invalid_file)],
        artwork_path=str(cover),
        artwork_banner_path=str(banner),
        unwalled_category="14",
        unwalled_type="3",
    )

    assert asyncio.run(_tracker().get_additional_checks(meta)) is False  # noqa: S101


def test_unwalled_rejects_invalid_nested_paths_and_missing_announce(tmp_path: Path) -> None:
    invalid_dir = tmp_path / "bad:name"
    invalid_dir.mkdir()
    episode = invalid_dir / "episode.mp3"
    episode.write_bytes(b"audio")
    cover = tmp_path / "cover.jpg"
    banner = tmp_path / "banner.jpg"
    _jpg(cover, (500, 500), "red")
    _jpg(banner, (960, 540), "blue")
    meta = Meta(
        path=str(tmp_path),
        category="PODCAST",
        name="Example Show [2026/MP3 - 128kbps]",
        filelist=[str(episode)],
        artwork_path=str(cover),
        artwork_banner_path=str(banner),
        unwalled_category="14",
        unwalled_type="3",
    )

    assert asyncio.run(_tracker().get_additional_checks(meta)) is False  # noqa: S101

    valid_episode = tmp_path / "episode.mp3"
    valid_episode.write_bytes(b"audio")
    meta.filelist = [str(valid_episode)]
    assert asyncio.run(_tracker(announce_url="").get_additional_checks(meta)) is False  # noqa: S101


@pytest.mark.asyncio
async def test_unwalled_builds_private_v1_torrent_with_source_and_announce(tmp_path: Path) -> None:
    episode = tmp_path / "001 - Pilot.mp3"
    episode.write_bytes(b"audio data")
    cover = tmp_path / "cover.jpg"
    banner = tmp_path / "banner.jpg"
    _jpg(cover, (500, 500), "red")
    _jpg(banner, (960, 540), "blue")
    release_dir = tmp_path / "tmp" / "podcast-torrent"
    release_dir.mkdir(parents=True)
    meta = Meta(
        base_dir=str(tmp_path),
        uuid="podcast-torrent",
        path=str(episode),
        filelist=[str(episode)],
        category="PODCAST",
        artwork_path=str(cover),
        artwork_banner_path=str(banner),
        isdir=False,
        max_piece_size=1,
        trackers=["UNWALLED"],
    )
    announce = "https://unwalled.cc/announce/example-token"

    await TorrentCreator.create_torrent(meta, episode, "BASE")
    filename = await _tracker(announce_url=announce).get_upload_torrent_filename(meta)
    torrent = Torrent.read(release_dir / f"{filename}.torrent")

    assert filename == "[UNWALLED]"  # noqa: S101
    assert torrent.metainfo.get("announce") == announce  # noqa: S101
    assert torrent.metainfo["info"].get("private") == 1  # noqa: S101
    assert torrent.metainfo["info"].get("source") == "Unwalled"  # noqa: S101
    assert "file tree" not in torrent.metainfo["info"]  # noqa: S101


@pytest.mark.asyncio
async def test_unwalled_rejects_cross_host_torrent_download_redirect(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(302, headers={"location": "https://attacker.invalid/stolen.torrent"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    meta = Meta(base_dir=str(tmp_path), uuid="secure-download")
    (tmp_path / "tmp" / meta.uuid).mkdir(parents=True)
    with patch("src.trackersetup.http_trackers", []), patch("src.trackers.common.httpx.AsyncClient", return_value=client):
        result = await Common({}).download_tracker_torrent(
            meta,
            "UNWALLED",
            headers={"authorization": "Bearer secret"},
            downurl="https://unwalled.cc/torrents/download/1",
            allowed_hosts=("unwalled.cc",),
            max_size=1024,
        )

    assert result is None  # noqa: S101
    assert [request.url.host for request in requests] == ["unwalled.cc"]  # noqa: S101
    assert not (tmp_path / "tmp" / meta.uuid / "[UNWALLED].torrent").exists()  # noqa: S101


@pytest.mark.asyncio
async def test_unwalled_rejects_oversized_torrent_download(tmp_path: Path) -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * 2048)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    meta = Meta(base_dir=str(tmp_path), uuid="bounded-download")
    (tmp_path / "tmp" / meta.uuid).mkdir(parents=True)
    with patch("src.trackersetup.http_trackers", []), patch("src.trackers.common.httpx.AsyncClient", return_value=client):
        result = await Common({}).download_tracker_torrent(
            meta,
            "UNWALLED",
            downurl="https://unwalled.cc/torrents/download/1",
            allowed_hosts=("unwalled.cc",),
            max_size=1024,
        )

    assert result is None  # noqa: S101
    assert not (tmp_path / "tmp" / meta.uuid / "[UNWALLED].torrent").exists()  # noqa: S101


@pytest.mark.asyncio
async def test_unwalled_rejects_v2_base_and_oversized_final_bundle(tmp_path: Path) -> None:
    episode = tmp_path / "episode.mp3"
    episode.write_bytes(b"audio")
    cover = tmp_path / "cover.jpg"
    banner = tmp_path / "banner.jpg"
    _jpg(cover, (500, 500), "red")
    _jpg(banner, (960, 540), "blue")
    release_dir = tmp_path / "tmp" / "v2-check"
    release_dir.mkdir(parents=True)
    meta = Meta(
        base_dir=str(tmp_path),
        uuid="v2-check",
        path=str(episode),
        filelist=[str(episode)],
        category="PODCAST",
        name="Example Show [2026/MP3 - 128kbps]",
        artwork_path=str(cover),
        artwork_banner_path=str(banner),
        unwalled_category="14",
        unwalled_type="3",
        max_piece_size=1,
        trackers=["UNWALLED"],
    )
    await TorrentCreator.create_torrent(meta, episode, "BASE")
    base_path = release_dir / "BASE.torrent"
    metainfo = cast(dict[bytes, object], bdecode(base_path.read_bytes()))
    info = cast(dict[bytes, object], metainfo[b"info"])
    info[b"meta version"] = 2
    info[b"file tree"] = {}
    base_path.write_bytes(bencode(metainfo))

    assert await _tracker().get_additional_checks(meta) is False  # noqa: S101

    await TorrentCreator.create_torrent(meta, episode, "BASE")
    await _tracker().get_upload_torrent_filename(meta)
    upload_path = release_dir / "[UNWALLED].torrent"
    padding = 1024 * 1024 - upload_path.stat().st_size - cover.stat().st_size - banner.stat().st_size
    with banner.open("ab") as banner_file:
        banner_file.write(b"x" * max(padding, 0))
    assert _tracker()._valid_upload_bundle(meta, upload_path) is False  # noqa: S101
    with pytest.raises(ValueError, match="bundle validation"):
        await _tracker().get_upload_torrent_filename(meta)


@pytest.mark.asyncio
async def test_unwalled_debug_torrent_never_contains_personal_announce(tmp_path: Path) -> None:
    episode = tmp_path / "episode.mp3"
    episode.write_bytes(b"audio")
    cover = tmp_path / "cover.jpg"
    banner = tmp_path / "banner.jpg"
    _jpg(cover, (500, 500), "red")
    _jpg(banner, (960, 540), "blue")
    release_dir = tmp_path / "tmp" / "debug-announce"
    release_dir.mkdir(parents=True)
    meta = Meta(
        base_dir=str(tmp_path),
        uuid="debug-announce",
        path=str(episode),
        filelist=[str(episode)],
        category="PODCAST",
        artwork_path=str(cover),
        artwork_banner_path=str(banner),
        max_piece_size=1,
        trackers=["UNWALLED"],
        debug=True,
    )
    await TorrentCreator.create_torrent(meta, episode, "BASE")

    filename = await _tracker(announce_url="https://unwalled.cc/announce/personal-token").get_upload_torrent_filename(meta)
    torrent = Torrent.read(release_dir / f"{filename}.torrent")

    assert torrent.metainfo.get("announce") == "https://fake.tracker"  # noqa: S101


def test_unwalled_rejects_malformed_announce_ports() -> None:
    assert _tracker()._valid_announce_url("https://unwalled.cc:invalid/announce/token") is False  # noqa: S101
