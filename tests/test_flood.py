import asyncio

from src.meta import Meta
from src.trackers.flood import Flood
from src.trackersetup import tracker_class_map


def test_flood_is_registered_with_full_tracker_name():
    assert tracker_class_map["FLOOD"] is Flood  # noqa: S101
    assert Flood.display_name == "Flood"  # noqa: S101
    assert Meta.canonical_tracker_name("FLD") == "FLOOD"  # noqa: S101
    assert Meta.canonical_tracker_name("BTN") == "BROADCASTHENET"  # noqa: S101


def test_flood_multi_disc_dvd_description_has_valid_code_tags(tmp_path, monkeypatch):
    monkeypatch.setattr("src.description_review.get_base_description", lambda _meta: "base")
    (tmp_path / "tmp" / "test").mkdir(parents=True)
    meta = Meta(
        base_dir=str(tmp_path),
        uuid="test",
        image_list=[{"web_url": "https://img.host/1", "img_url": "https://img.host/1.png"}],
        screens=1,
        discs=[
            {"type": "DVD", "vob_mi": "disc 1"},
            {"type": "DVD", "name": "Disc 2", "vob": "VIDEO_TS/VTS_01_1.VOB", "vob_mi": "vob info", "ifo": "VIDEO_TS/VTS_01_0.IFO", "ifo_mi": "ifo info"},
        ],
        comparison="path/to/comp",
        comparison_groups={
            "0": {"name": "Source 1", "urls": [{"raw_url": "https://img.host/c1.png"}]},
            "1": {"name": "Source 2", "urls": [{"raw_url": "https://img.host/c2.png"}]},
        },
    )

    asyncio.run(Flood({"TRACKERS": {}}).edit_desc(meta))

    description = (tmp_path / "tmp" / "test" / "[FLOOD]DESCRIPTION.txt").read_text(encoding="utf-8")
    assert "[code][vob info" not in description  # noqa: S101
    assert "[code]vob info[/code]" in description  # noqa: S101
    assert "[code]ifo info[/code]" in description  # noqa: S101
    assert "[comparison=Source 1, Source 2]" in description  # noqa: S101
    assert "https://img.host/1.png" in description  # noqa: S101


def test_flood_get_media_type():
    tracker = Flood({"TRACKERS": {}})
    assert asyncio.run(tracker.get_media_type(Meta(category="MOVIE"))) == "movie"  # noqa: S101
    assert asyncio.run(tracker.get_media_type(Meta(category="TV", tv_pack=0))) == "show_episode"  # noqa: S101
    assert asyncio.run(tracker.get_media_type(Meta(category="TV", tv_pack=1))) == "show_season"  # noqa: S101


def test_flood_get_prefixed_tmdb_id():
    tracker = Flood({"TRACKERS": {}})
    assert asyncio.run(tracker.get_prefixed_tmdb_id(Meta(category="MOVIE", tmdb="12345"))) == "movie/12345"  # noqa: S101
    assert asyncio.run(tracker.get_prefixed_tmdb_id(Meta(category="TV", tmdb="67890"))) == "tv/67890"  # noqa: S101


def test_flood_get_name():
    tracker = Flood({"TRACKERS": {}})
    meta_dvd = Meta(
        name="Movie.Title.2000.NTSC.DVD.DD+ 2.0-GRP",
        source="NTSC DVD",
        audio="DD+ 2.0",
        video_codec="MPEG-2",
    )
    assert asyncio.run(tracker.get_name(meta_dvd)) == "Movie.Title.2000.NTSC.DVD.MPEG-2 DDP 2.0-GRP"  # noqa: S101

    meta_bluray = Meta(
        name="Movie.Title.2000.1080p.BluRay.DD+5.1-GRP",
        source="BluRay",
    )
    assert asyncio.run(tracker.get_name(meta_bluray)) == "Movie.Title.2000.1080p.BluRay.DDP5.1-GRP"  # noqa: S101
