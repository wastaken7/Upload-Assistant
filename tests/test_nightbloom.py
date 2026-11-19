"""Nightbloom tracker tests."""

import asyncio

import pytest

from src.meta import Meta
from src.trackers.UNIT3D import UNIT3D
from src.trackers.UNIT3D.nightbloom import Nightbloom
from src.trackersetup import tracker_class_map


def tracker(**options) -> Nightbloom:
    return Nightbloom({"DEFAULT": {}, "TRACKERS": {"NIGHTBLOOM": options}})


def test_registered_under_its_full_name_and_nig_alias():
    assert tracker_class_map["NIGHTBLOOM"] is Nightbloom  # noqa: S101
    assert Nightbloom.display_name == "Nightbloom"  # noqa: S101
    assert Meta().canonical_tracker_name("nig") == "NIGHTBLOOM"  # noqa: S101


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        ({"category": "MOVIE"}, "1"),
        ({"category": "TV"}, "2"),
        ({"category": "TV", "anime": True}, "6"),
        ({"category": "MOVIE", "anime": True}, "6"),
    ],
)
def test_category_ids(fields, expected):
    assert asyncio.run(tracker().get_category_id(Meta(**fields)))["category_id"] == expected  # noqa: S101


@pytest.mark.parametrize(
    ("meta_type", "expected"),
    [("DISC", "1"), ("REMUX", "2"), ("ENCODE", "3"), ("WEBDL", "4"), ("WEBRIP", "5"), ("HDTV", "6")],
)
def test_type_ids(meta_type, expected):
    assert asyncio.run(tracker().get_type_id(Meta(type=meta_type)))["type_id"] == expected  # noqa: S101


@pytest.mark.parametrize(
    ("resolution", "expected"),
    [
        ("4320p", "1"),
        ("2160p", "2"),
        ("1080p", "3"),
        ("1080i", "4"),
        ("720p", "5"),
        ("576p", "6"),
        ("576i", "7"),
        ("480p", "8"),
        ("480i", "9"),
        ("OTHER", "10"),
    ],
)
def test_resolution_ids(resolution, expected):
    assert asyncio.run(tracker().get_resolution_id(Meta(resolution=resolution)))["resolution_id"] == expected  # noqa: S101


def test_upload_sends_only_the_fields_of_the_sites_own_form(monkeypatch):
    async def stock_data(_self, _meta, **_options):
        return {
            "name": "Example 2020 1080p BluRay x264-GRP",
            "category_id": "1",
            "type_id": "3",
            "resolution_id": "3",
            "anonymous": "0",
            "featured": "1",
            "free": "100",
            "doubleup": "1",
            "sticky": "1",
            "internal": "0",
            "stream": "0",
            "sd": "0",
            "exclusive": "1",
            "mod_queue_opt_in": "0",
        }

    monkeypatch.setattr(UNIT3D, "get_data", stock_data)

    data = asyncio.run(tracker(featured=True, free=True).get_data(Meta(category="MOVIE")))

    assert data == {  # noqa: S101
        "name": "Example 2020 1080p BluRay x264-GRP",
        "category_id": "1",
        "type_id": "3",
        "resolution_id": "3",
        "anonymous": "0",
    }


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        (
            {"basename_no_ext": "The.Act.S01.BluRay.1080p.DTS-HD.MA.5.1.AVC.REMUX-FraMeSToR", "tag": "-FraMeSToR"},
            "The Act S01 BluRay 1080p DTS-HD MA 5.1 AVC REMUX-FraMeSToR",
        ),
        (
            {"scene_name": "Example.Show.S01E01.720p.HDTV.x264-SCENE", "basename_no_ext": "example.show.s01e01", "tag": "-SCENE"},
            "Example Show S01E01 720p HDTV x264-SCENE",
        ),
        (
            {"basename_no_ext": "Blade.Runner.2049.2017.2160p.AMZN.WEB-DL.DDP5.1.H.265-GROUP", "tag": "-GROUP"},
            "Blade Runner 2049 2017 2160p AMZN WEB-DL DDP5.1 H.265-GROUP",
        ),
        (
            {"basename_no_ext": "My hero Academia S02 BDREMUX", "tag": "-ZR"},
            "My Hero Academia S02 1080p BluRay REMUX AVC TrueHD 5.1-ZR",
        ),
    ],
)
def test_name_keeps_the_group_release_name(fields, expected):
    meta = Meta(category="TV", name="My Hero Academia S02 1080p BluRay REMUX AVC TrueHD 5.1-ZR", **fields)

    assert asyncio.run(tracker().get_name(meta))["name"] == expected  # noqa: S101


def test_a_single_episode_in_a_season_folder_is_named_after_the_episode_file():
    meta = Meta(
        category="TV",
        name="Day Pass S02E01 2160p NBLA WEB-DL AAC 2.0 H.265-GROUP",
        basename_no_ext="Day.Pass.S02.2160p.NBLA.WEB-DL.AAC2.0.H.265-GROUP",
        isdir=True,
        season="S02",
        episode="E01",
        filelist=["/data/Day.Pass.S02.2160p.NBLA.WEB-DL.AAC2.0.H.265-GROUP/Day.Pass.S02E01.Not.Just.Beef.2160p.NBLA.WEB-DL.AAC2.0.H.265-GROUP.mkv"],
        tag="-GROUP",
    )

    assert asyncio.run(tracker().get_name(meta))["name"] == "Day Pass S02E01 Not Just Beef 2160p NBLA WEB-DL AAC2.0 H.265-GROUP"  # noqa: S101


def test_a_season_pack_keeps_the_folder_name():
    meta = Meta(
        category="TV",
        name="Day Pass S02 2160p NBLA WEB-DL AAC 2.0 H.265-GROUP",
        basename_no_ext="Day.Pass.S02.2160p.NBLA.WEB-DL.AAC2.0.H.265-GROUP",
        isdir=True,
        tv_pack=True,
        season="S02",
        filelist=[f"/data/Day.Pass.S02E0{n}.2160p.NBLA.WEB-DL.AAC2.0.H.265-GROUP.mkv" for n in (1, 2)],
        tag="-GROUP",
    )

    assert asyncio.run(tracker().get_name(meta))["name"] == "Day Pass S02 2160p NBLA WEB-DL AAC2.0 H.265-GROUP"  # noqa: S101
