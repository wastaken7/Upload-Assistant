import asyncio
import json

import httpx

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


def test_btn_name_puts_hdr_formats_before_resolution() -> None:
    meta = Meta(name="Example Show S01E01 2160p WEB-DL DDP 5.1 Atmos DV HDR H.265-GRP", hdr="DV HDR", resolution="2160p", tag="-GRP")

    assert asyncio.run(tracker().get_name(meta)) == "Example.Show.S01E01.DV.HDR.2160p.WEB-DL.DDPA5.1.H.265-GRP"  # noqa: S101


def test_btn_name_removes_foreign_aka_title() -> None:
    meta = Meta(
        name="English Title AKA Foreign Title S01E01 1080p WEB-DL AAC 2.0 H.264-GRP",
        aka="AKA Foreign Title",
        resolution="1080p",
        tag="-GRP",
    )

    assert asyncio.run(tracker().get_name(meta)) == "English.Title.S01E01.1080p.WEB-DL.AAC2.0.H.264-GRP"  # noqa: S101


def test_btn_form_fields_keeps_autofilled_values() -> None:
    fields = tracker()._form_fields(
        '<input name="seriesid" value="42"><input name="artist" value="Example Show">'
        '<textarea name="album_desc">Episode description</textarea>'
        '<select name="media"><option value="HDTV" selected>HDTV</option></select>'
    )

    assert fields == {"seriesid": "42", "artist": "Example Show", "album_desc": "Episode description", "media": "HDTV"}  # noqa: S101


def test_btn_dupe_search_projects_api_rows(monkeypatch) -> None:
    async def fake_api(method: str, params: dict[str, object]) -> dict[str, object]:
        if method != "getTorrents" or params != {"search": {"category": "Episode", "tvdb": "123"}, "results": 100, "offset": 0}:
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
    async def fake_api(method: str, params: dict[str, object]) -> dict[str, object]:
        if method != "getTorrents" or params != {"search": {"category": "Season", "tvdb": "123"}, "results": 100, "offset": 0}:
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


def test_btn_group_page_does_not_identify_an_older_torrent() -> None:
    group_id, torrent_id = tracker()._upload_ids(
        "https://backup.landof.tv/torrents.php?id=123",
        '<a href="torrents.php?id=123&amp;torrentid=789">Older 720p torrent</a>',
    )

    assert (group_id, torrent_id) == ("123", "")  # noqa: S101


def test_btn_finds_uploaded_release_in_its_group(monkeypatch) -> None:
    async def fake_api(method: str, params: dict[str, object]) -> dict[str, object]:
        assert method == "getTorrents"  # noqa: S101
        assert params == {"search": {"tvdb": "42"}, "results": 1000, "offset": 0}  # noqa: S101
        return {
            "result": {
                "torrents": {
                    "789": {"GroupID": "123", "ReleaseName": "Show.S01E01.720p-GRP"},
                    "456": {"GroupID": "123", "ReleaseName": "Show.S01E01.1080p-GRP"},
                    "999": {"GroupID": "999", "ReleaseName": "Show.S01E01.1080p-GRP"},
                }
            }
        }

    btn = tracker()
    monkeypatch.setattr(btn, "_api", fake_api)

    assert asyncio.run(btn._uploaded_torrent_id("Show.S01E01.1080p-GRP", "123", Meta(tvdb_id=42))) == "456"  # noqa: S101


def test_btn_api_sends_named_search_parameters(monkeypatch) -> None:
    requests: list[dict[str, object]] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"result": {"torrents": {}}})

    original_client = httpx.AsyncClient
    transport = httpx.MockTransport(respond)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original_client(transport=transport, **kwargs))

    asyncio.run(tracker().search_existing(Meta(category="TV", tvdb_id=42)))

    assert requests[0]["id"] == "upload-assistant-btn"  # noqa: S101
    assert requests[0]["method"] == "getTorrents"  # noqa: S101
    assert "jsonrpc" not in requests[0]  # noqa: S101
    assert requests[0]["params"] == {"key": "token", "search": {"category": "Episode", "tvdb": "42"}, "results": 100, "offset": 0}  # noqa: S101


def test_btn_dupe_search_uses_documented_text_filter(monkeypatch) -> None:
    async def fake_api(method: str, params: dict[str, object]) -> dict[str, object]:
        assert method == "getTorrents"  # noqa: S101
        assert params["search"] == {"category": "Episode", "search": "Example Show"}  # noqa: S101
        return {"result": {"torrents": {}}}

    btn = tracker()
    monkeypatch.setattr(btn, "_api", fake_api)

    assert asyncio.run(btn.search_existing(Meta(category="TV", title="Example Show"))) == []  # noqa: S101
