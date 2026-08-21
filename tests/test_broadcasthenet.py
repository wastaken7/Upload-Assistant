import asyncio

from src.meta import Meta
from src.trackers.broadcasthenet import BroadcasTheNet
from src.trackersetup import TrackerSetup, tracker_class_map


def tracker() -> BroadcasTheNet:
    return BroadcasTheNet({"DEFAULT": {}, "TRACKERS": {"BROADCASTHENET": {"api_key": "token"}}})


def test_btn_is_registered_and_tv_only() -> None:
    assert tracker_class_map["BROADCASTHENET"] is BroadcasTheNet  # noqa: S101
    assert tracker().tracker == "BROADCASTHENET"  # noqa: S101
    assert tracker().supported_categories == ("TV",)  # noqa: S101


def test_btn_name_normalizes_audio_and_no_group_suffix() -> None:
    meta = Meta(name="Lé Série S01E01 1080p WEB-DL DDP.5.1.Atmos x265", tag="", resolution="1080p")

    assert asyncio.run(tracker().get_name(meta)) == "Le.Serie.S01E01.1080p.WEB-DL.DDPA5.1.x265-NOGRP"  # noqa: S101


def test_btn_form_fields_keeps_autofilled_values() -> None:
    fields = tracker()._form_fields(
        '<input name="seriesid" value="42"><input name="artist" value="Example Show">'
        '<textarea name="album_desc">Episode description</textarea>'
        '<select name="media"><option value="HDTV" selected>HDTV</option></select>'
    )

    assert fields == {"seriesid": "42", "artist": "Example Show", "album_desc": "Episode description", "media": "HDTV"}  # noqa: S101


def test_btn_dupe_search_projects_api_rows(monkeypatch) -> None:
    async def fake_api(method: str, params: list[object]) -> dict[str, object]:
        if method != "getTorrents" or params[0] != {"category": "Episode", "tvdb": "123"}:
            raise AssertionError("unexpected BTN API request")
        return {"result": {"torrents": {"456": {"GroupID": "789", "ReleaseName": "Show.S01E01", "Size": "1024", "FileCount": "2"}}}}

    btn = tracker()
    monkeypatch.setattr(btn, "_api", fake_api)
    dupes = asyncio.run(btn.search_existing(Meta(category="TV", tvdb_id=123)))

    assert dupes == [{"name": "Show.S01E01", "size": 1024, "files": "", "file_count": 2, "link": "https://backup.landof.tv/torrents.php?id=789&torrentid=456"}]  # noqa: S101


def test_btn_requires_tvdb_or_imdb_id_before_upload() -> None:
    assert asyncio.run(tracker().get_additional_checks(Meta(category="TV"))) is False  # noqa: S101
    assert asyncio.run(tracker().get_additional_checks(Meta(category="TV", tvdb_id=123))) is True  # noqa: S101
    assert asyncio.run(tracker().get_additional_checks(Meta(category="TV", imdb_id=456))) is True  # noqa: S101


def test_btn_dupe_search_uses_season_category_for_packs(monkeypatch) -> None:
    async def fake_api(method: str, params: list[object]) -> dict[str, object]:
        if method != "getTorrents" or params[0] != {"category": "Season", "tvdb": "123"}:
            raise AssertionError("unexpected BTN API request")
        return {"result": {"torrents": {}}}

    btn = tracker()
    monkeypatch.setattr(btn, "_api", fake_api)

    assert asyncio.run(btn.search_existing(Meta(category="TV", tv_pack=True, tvdb_id=123))) == []  # noqa: S101


def test_btn_preserves_legacy_default_api_key_during_tracker_filtering() -> None:
    meta = Meta(category="TV", trackers=["BTN"])
    setup = TrackerSetup({"DEFAULT": {"btn_api": "legacy-token"}, "TRACKERS": {"BTN": {"announce_url": "https://tracker.example/announce"}}})

    setup.trackers_enabled(meta)

    assert meta.trackers == ["BROADCASTHENET"]  # noqa: S101
