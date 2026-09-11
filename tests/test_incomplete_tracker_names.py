# ruff: noqa: S101
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.meta import Meta
from src.trackers.naming import add_incomplete_pack_marker
from src.trackersetup import tracker_class_map

TRACKERS = (
    "LST", "AITHER", "HDBITS", "ULCX", "HAWKEUNO", "YUSCENE", "OLDTOONSWORLD",
    "ONLYENCODES", "PRIVATEHD", "CINEMAZ", "AVISTAZ", "HDTORRENTS", "RASTASTUGAN",
    "DARKPEERS", "IPTORRENTS", "HDSPACE", "TORRENTLEECH",
)


def make_meta(**overrides):
    fields = dict(
        category="TV", tv_pack=True, season_pack_incomplete=True, season="S03", season_int=3,
        title="Car S.O.S.", name="Car S.O.S. S03 1080p DSNP WEB-DL DDP 5.1 H.264-Group",
        clean_name="Car.S.O.S.S03.1080p.DSNP.WEB-DL.DDP.5.1.H.264-Group",
        type="WEBDL", source="Web", resolution="1080p", video_codec="H.264", video_encode="H.264",
        audio="DDP 5.1", tag="-Group", service="DSNP", language_checked=True,
    )
    fields.update(overrides)
    return Meta(**fields)


def make_tracker(name):
    tracker = tracker_class_map[name]({"DEFAULT": {"tmdb_api": "test-key"}, "TRACKERS": {name: {}}})
    if name == "DARKPEERS":
        tracker._tv_title_needs_year = AsyncMock(return_value=False)
    return tracker


@pytest.mark.asyncio
@pytest.mark.parametrize("tracker_name", TRACKERS)
@pytest.mark.parametrize("confirmed", [True, False])
async def test_requested_tracker_marks_only_confirmed_packs(tracker_name, confirmed):
    tracker = make_tracker(tracker_name)
    meta = make_meta(season_pack_incomplete=confirmed)
    original = (meta.name, meta.clean_name, meta.season, meta.season_int)
    try:
        result = await tracker.get_name(meta)
        name = result["name"] if isinstance(result, dict) else result
        if confirmed:
            assert "S03 INCOMPLETE " in name or "S03.INCOMPLETE." in name
            assert name.count("INCOMPLETE") == 1
            assert add_incomplete_pack_marker(name, meta, tracker_name) == name
        else:
            assert "INCOMPLETE" not in name
        assert (meta.name, meta.clean_name, meta.season, meta.season_int) == original
    finally:
        session = getattr(tracker, "session", None)
        if session is not None:
            await session.aclose()


@pytest.mark.parametrize("name,expected", [
    ("Show S03 1080p", "Show S03 INCOMPLETE 1080p"),
    ("Show.S03.1080p", "Show.S03.INCOMPLETE.1080p"),
    ("Show S03 INCOMPLETE 1080p", "Show S03 INCOMPLETE 1080p"),
    ("Show S03 incomplete INCOMPLETE 1080p", "Show S03 INCOMPLETE 1080p"),
    ("Show.S03.INCOMPLETE.1080p", "Show.S03.INCOMPLETE.1080p"),
    ("Show S030 1080p", "Show S030 1080p"),
    ("Show S03E02 1080p", "Show S03E02 1080p"),
    ("Show 1080p", "Show 1080p"),
])
def test_marker_placement_boundaries_and_idempotence(name, expected):
    meta = make_meta()
    result = add_incomplete_pack_marker(name, meta, "LST")
    assert result == expected
    assert add_incomplete_pack_marker(result, meta, "LST") == result


@pytest.mark.parametrize("overrides", [{"category": "MOVIE"}, {"tv_pack": False}, {"season_pack_incomplete": False}])
def test_non_pack_and_unconfirmed_names_are_unchanged(overrides):
    meta = make_meta(**overrides)
    assert add_incomplete_pack_marker(meta.name, meta, "LST") == meta.name


def test_unlisted_tracker_is_unchanged():
    meta = make_meta()
    assert add_incomplete_pack_marker(meta.name, meta, "BLUTOPIA") == meta.name


@pytest.mark.asyncio
async def test_iptorrents_post_upload_edit_preserves_marker():
    tracker = make_tracker("IPTORRENTS")
    await tracker.session.aclose()
    tracker.session = SimpleNamespace(post=AsyncMock(return_value=SimpleNamespace(status_code=302)))
    tracker.generate_description = AsyncMock(return_value="Description")
    tracker.get_is_freeleech = AsyncMock(return_value=False)
    meta = make_meta(tracker_status={"IPTORRENTS": {"torrent_id": "123"}})
    data = await tracker.get_data(meta)
    assert "S03 INCOMPLETE " in data["name"]
    await tracker.edit_post_upload(meta)
    assert "S03 INCOMPLETE " in tracker.session.post.call_args.kwargs["data"]["name"]


@pytest.mark.asyncio
async def test_hawkeuno_payload_and_torrent_filename_include_marker(tmp_path):
    tracker = make_tracker("HAWKEUNO")
    tracker.get_description = AsyncMock(return_value={})
    tracker.common.create_torrent_for_upload = AsyncMock()
    meta = make_meta(base_dir=str(tmp_path), uuid="pack", tmdb=123, repack="REPACK")
    folder = tmp_path / "tmp" / "pack"
    folder.mkdir(parents=True)
    for filename in ("[HAWKEUNO].torrent", "[HAWKEUNO]DESCRIPTION.txt", "MEDIAINFO_CLEANPATH.txt"):
        (folder / filename).write_bytes(b"fixture")
    data = await tracker.get_data(meta)
    files = await tracker.get_files(meta)
    assert "S03 INCOMPLETE " in data["name"]
    assert data["season_number"] == 3
    assert data["release_tag"] == "REPACK"
    assert "S03.INCOMPLETE." in files["torrent"][0]
    assert files["torrent"][1] == b"fixture"
