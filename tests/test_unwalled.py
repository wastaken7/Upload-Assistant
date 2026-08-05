import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from PIL import Image
from torf import Torrent

from src.args import Args
from src.meta import Meta
from src.podcast_prep import gather_podcast_prep
from src.torrentcreate import TorrentCreator
from src.trackers.UNIT3D.unwalled import Unwalled
from src.trackersetup import tracker_class_map


def _tracker(**settings: object) -> Unwalled:
    config = {
        "DEFAULT": {"screens": 0, "img_host_1": "imgbox"},
        "TRACKERS": {"UNWALLED": {"api_key": "token", **settings}},
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


def test_unwalled_discovers_category_and_type_ids_from_unit3d_results() -> None:
    payload = {
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
    meta = Meta(
        category="PODCAST",
        name="Example Show [2026/MP3 - 128kbps]",
        filelist=[str(tmp_path / "001 - Pilot.mp3")],
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
    meta = Meta(
        category="PODCAST",
        name="Example Show [2026/MP3 - 128kbps]",
        filelist=[str(tmp_path / "bad:name.mp3")],
        artwork_path=str(cover),
        artwork_banner_path=str(banner),
        unwalled_category="14",
        unwalled_type="3",
    )

    assert asyncio.run(_tracker().get_additional_checks(meta)) is False  # noqa: S101


@pytest.mark.asyncio
async def test_unwalled_builds_private_v1_torrent_with_source_and_announce(tmp_path: Path) -> None:
    episode = tmp_path / "001 - Pilot.mp3"
    episode.write_bytes(b"audio data")
    release_dir = tmp_path / "tmp" / "podcast-torrent"
    release_dir.mkdir(parents=True)
    meta = Meta(
        base_dir=str(tmp_path),
        uuid="podcast-torrent",
        path=str(episode),
        filelist=[str(episode)],
        category="PODCAST",
        isdir=False,
        max_piece_size=1,
        trackers=["UNWALLED"],
    )
    announce = "https://tracker.invalid/announce/example"

    await TorrentCreator.create_torrent(meta, episode, "BASE")
    filename = await _tracker(announce_url=announce).get_upload_torrent_filename(meta)
    torrent = Torrent.read(release_dir / f"{filename}.torrent")

    assert filename == "[UNWALLED]"  # noqa: S101
    assert torrent.metainfo.get("announce") == announce  # noqa: S101
    assert torrent.metainfo["info"].get("private") == 1  # noqa: S101
    assert torrent.metainfo["info"].get("source") == "Unwalled"  # noqa: S101
    assert "file tree" not in torrent.metainfo["info"]  # noqa: S101
