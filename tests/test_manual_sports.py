# ruff: noqa: S101
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.args import Args
from src.meta import Meta
from src.prep import Prep
from src.prep_helpers import detect_disc_and_category
from src.sports import detect_sports
from src.trackermeta import update_meta_with_unit3d_data
from src.trackers.UNIT3D.aither import Aither


@pytest.mark.asyncio
@pytest.mark.parametrize("title,flags,override,is_sports", [
    ("Example Tournament", [], None, False),
    ("Example Tournament", ["--category", "sports"], "sports", True),
    ("Example Boxing Event", [], None, False),
    ("UFC 123 Example Event", [], None, True),
    ("UFC 123 Example Event", ["--category", "tv"], "tv", False),
    ("UFC 123 Example Event", ["--category", "movie"], "movie", False),
    ("Example The Impossible Formula 1 Story", [], None, False),
])
async def test_cli_sports_override_reaches_aither_payload(tmp_path, monkeypatch, title, flags, override, is_sports):
    video = tmp_path / "Example.Release.S01E03.mkv"
    video.touch()
    config = {"DEFAULT": {"screens": 1}, "TRACKERS": {"AITHER": {}}}
    meta = Meta(title=title, name=f"{title} S01E03 1080p WEB-DL-GROUP", season_int=1, episode_int=3, language_checked=True)
    meta, _, unknown = Args(config).parse([str(video), *flags], meta)

    assert unknown == []
    assert meta.manual_category == override
    prep = SimpleNamespace(disc_info_manager=SimpleNamespace(get_disc=AsyncMock(return_value=("", str(video), {}, []))))
    await detect_disc_and_category(prep, meta)
    if not meta.category:
        meta.category = await Prep.get_cat(prep, str(video), meta)
    meta = Meta(meta.to_dict())
    meta.is_sports = detect_sports(meta)
    assert meta.is_sports is is_sports
    expected_category = "MOVIE" if override == "movie" else "TV"
    assert meta.category == expected_category

    tracker = Aither(config)
    for method in ("get_description", "get_mediainfo", "get_bdinfo"):
        monkeypatch.setattr(tracker, method, AsyncMock(return_value={}))
    data = await tracker.get_data(meta)

    assert data["category_id"] == ("9" if is_sports else "1" if expected_category == "MOVIE" else "2")
    if is_sports or expected_category == "MOVIE":
        assert "season_number" not in data
        assert "episode_number" not in data
    else:
        assert data["season_number"] == "1"
        assert data["episode_number"] == "3"


@pytest.mark.asyncio
async def test_sports_override_allows_movie_metadata_detection(tmp_path):
    video = tmp_path / "Example.Tournament.2099.mkv"
    video.touch()
    meta, _, _ = Args({"DEFAULT": {"screens": 1}}).parse([str(video), "--category", "sports"], Meta())

    assert await Prep.get_cat(SimpleNamespace(), str(video), meta) == "MOVIE"
    assert detect_sports(meta)


@pytest.mark.asyncio
@pytest.mark.parametrize("manual_category,base_category,tracker_category,expected", [
    ("sports", "", "TV", "TV"),
    ("sports", "", "MOVIE", "MOVIE"),
    ("tv", "TV", "MOVIE", "TV"),
    ("movie", "MOVIE", "TV", "MOVIE"),
])
async def test_sports_override_allows_tracker_media_category(manual_category, base_category, tracker_category, expected):
    meta = Meta(manual_category=manual_category, category=base_category, tracker_description_mode="ids")
    tracker_data = (None, None, None, None, None, tracker_category, None, [], None)

    await update_meta_with_unit3d_data(meta, tracker_data, "AITHER")

    assert meta.category == expected
    assert detect_sports(meta) is (manual_category == "sports")
