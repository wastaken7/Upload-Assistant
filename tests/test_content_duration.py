from __future__ import annotations

import pytest

from src import content_duration
from src.meta import Meta


@pytest.mark.parametrize(
    ("meta", "expected"),
    [
        (Meta(category="MOVIE"), "Movie"),
        (Meta(category="FANRES"), "Movie"),
        (Meta(category="TV"), "TV"),
        (Meta(category="MOVIE", is_sports=True), "Sports"),
        (Meta(category="XXX"), "XXX"),
        (Meta(category="BOOK", audiobook=True), "Audiobook"),
        (Meta(category="BOOK", audiobook=False), ""),
        (Meta(category="MUSIC"), "Music"),
        (Meta(category="GAME"), ""),
    ],
)
def test_content_duration_category_uses_stats_buckets(meta, expected):
    assert content_duration.content_duration_category(meta) == expected


def test_existing_content_duration_reuses_prepared_metadata():
    assert content_duration.existing_content_duration(Meta(category="BOOK", audiobook=True, audiobook_duration=7_321.5)) == 7_321.5
    assert (
        content_duration.existing_content_duration(Meta(category="MUSIC", music_release={"tracks": [{"duration": 120.5}, {"duration": 180.25}, {"duration": None}]})) == 300.75
    )
    assert (
        content_duration.existing_content_duration(Meta(category="MOVIE", is_disc="BDMV", discs=[{"bdinfo": {"length": "01:30:00"}}, {"bdinfo": {"length": "00:45:30.5"}}]))
        == 8_130.5
    )
    assert content_duration.existing_content_duration(Meta(category="TV", mediainfo={"media": {"track": [{"@type": "General", "Duration": "1512.25"}]}})) == 1_512.25


def test_multi_disc_duration_requires_every_disc_length():
    meta = Meta(category="MOVIE", is_disc="BDMV", discs=[{"bdinfo": {"length": "01:30:00"}}, {"bdinfo": {}}], bdinfo={"length": "01:30:00"})

    assert content_duration.existing_content_duration(meta) == 0.0


@pytest.mark.asyncio
async def test_video_pack_is_probed_once_during_preparation(monkeypatch, tmp_path):
    files = []
    for index in range(3):
        path = tmp_path / f"Fictional.Show.S01E{index + 1:02}.mkv"
        path.write_bytes(b"fictional video")
        files.append(str(path))
    calls = []

    def fake_probe(path, executable):
        calls.append((path, executable))
        return 1_200.0

    monkeypatch.setattr(content_duration, "_probe_video_duration", fake_probe)
    meta = Meta(category="TV", filelist=files)

    result = await content_duration.populate_content_duration(meta, {"DEFAULT": {}})

    assert result == 3_600.0
    assert meta.content_duration_seconds == 3_600.0
    assert meta.content_duration_category == "TV"
    assert sorted(path for path, _executable in calls) == sorted(files)
    assert {executable for _path, executable in calls} == {"ffprobe"}


@pytest.mark.asyncio
async def test_single_video_reuses_mediainfo_without_ffprobe(monkeypatch, tmp_path):
    path = tmp_path / "Fictional.Movie.2026.mkv"
    path.write_bytes(b"fictional video")
    monkeypatch.setattr(content_duration, "_probe_video_duration", lambda *_args: pytest.fail("ffprobe should not run"))
    meta = Meta(
        category="MOVIE",
        filelist=[str(path)],
        mediainfo={"media": {"track": [{"@type": "General", "Duration": "5400.25"}]}},
    )

    assert await content_duration.populate_content_duration(meta, {"DEFAULT": {}}) == 5_400.25
    assert meta.content_duration_seconds == 5_400.25


@pytest.mark.asyncio
async def test_video_pack_does_not_store_a_partial_duration(monkeypatch, tmp_path):
    first = tmp_path / "Fictional.Show.S01E01.mkv"
    second = tmp_path / "Fictional.Show.S01E02.mkv"
    first.write_bytes(b"fictional video")
    second.write_bytes(b"fictional video")
    monkeypatch.setattr(content_duration, "_probe_video_duration", lambda path, _executable: 1_200.0 if path == str(first) else 0.0)
    meta = Meta(category="TV", filelist=[str(first), str(second)])

    assert await content_duration.populate_content_duration(meta, {"DEFAULT": {}}) == 0.0
    assert meta.content_duration_seconds is None
