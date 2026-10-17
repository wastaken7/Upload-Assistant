import asyncio
import json

import httpx
import pytest

from src.exceptions import UploadError
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
        if method != "getTorrents" or params != {"search": {"category": "Episode", "tvdb": "123"}, "results": 1000, "offset": 0}:
            raise AssertionError("unexpected BTN API request")
        return {"result": {"results": "1", "torrents": {"456": {"GroupID": "789", "ReleaseName": "Show.S01E01", "Size": "1024"}}}}

    btn = tracker()
    monkeypatch.setattr(btn, "_api", fake_api)
    dupes = asyncio.run(btn.search_existing(Meta(category="TV", tvdb_id=123)))

    assert dupes == [{"name": "Show.S01E01", "size": 1024, "files": "", "file_count": 0, "link": "https://backup.landof.tv/torrents.php?id=789&torrentid=456"}]  # noqa: S101


def test_btn_requires_tvdb_or_imdb_id_before_upload() -> None:
    assert asyncio.run(tracker().get_additional_checks(Meta(category="TV"))) is False  # noqa: S101
    assert asyncio.run(tracker().get_additional_checks(Meta(category="TV", tvdb_id=123))) is True  # noqa: S101
    assert asyncio.run(tracker().get_additional_checks(Meta(category="TV", imdb_id=456))) is True  # noqa: S101


def test_btn_dupe_search_uses_season_category_for_packs(monkeypatch) -> None:
    async def fake_api(method: str, params: dict[str, object]) -> dict[str, object]:
        if method != "getTorrents" or params != {"search": {"category": "Season", "tvdb": "123"}, "results": 1000, "offset": 0}:
            raise AssertionError("unexpected BTN API request")
        return {"result": {"results": "0"}}

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
        assert params == {"search": {"group_id": "123", "tvdb": "42"}, "results": 1000, "offset": 0}  # noqa: S101
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

    assert asyncio.run(btn._uploaded_torrent_id("Show.S01E01.1080p-GRP", "123", Meta(category="TV", tvdb_id=42))) == "456"  # noqa: S101


def test_btn_uploaded_release_lookup_falls_back_to_imdb_and_prefers_newest(monkeypatch) -> None:
    async def fake_api(_method: str, params: dict[str, object]) -> dict[str, object]:
        assert params["search"] == {"group_id": "123", "imdb": "77"}  # noqa: S101
        return {
            "result": {
                "torrents": {
                    "100": {"GroupID": "123", "ReleaseName": "Show.S01E01.1080p-GRP"},
                    "200": {"groupId": "123", "releaseName": "show.s01e01.1080p-grp"},
                }
            }
        }

    btn = tracker()
    monkeypatch.setattr(btn, "_api", fake_api)

    assert asyncio.run(btn._uploaded_torrent_id("Show.S01E01.1080p-GRP", "123", Meta(category="TV", imdb_id=77))) == "200"  # noqa: S101


def test_btn_uploaded_release_lookup_matches_cleaned_name_and_falls_back_to_group_newest(monkeypatch) -> None:
    async def fake_api(_method: str, params: dict[str, object]) -> dict[str, object]:
        assert params["search"] == {"group_id": "123"}  # noqa: S101
        return {
            "result": {
                "torrents": {
                    "300": {"GroupID": "123", "ReleaseName": "Show.S01E01.1080p.WEB-DL.DDP5.1.Atmos.x265-GRP"},
                }
            }
        }

    btn = tracker()
    monkeypatch.setattr(btn, "_api", fake_api)

    assert asyncio.run(btn._uploaded_torrent_id("Show S01E01 1080p WEB-DL DDP 5.1 Atmos x265-GRP", "123", Meta(category="TV"))) == "300"  # noqa: S101


def test_btn_uploaded_release_lookup_falls_back_to_release_name_and_tvdb(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    async def fake_api(_method: str, params: dict[str, object]) -> dict[str, object]:
        calls.append(params["search"])
        if params["search"] == {"release": "%Show.S01E01.1080p-GRP%", "tvdb": "42"}:
            return {
                "result": {
                    "torrents": {
                        "500": {"GroupID": "999", "ReleaseName": "Show.S01E01.1080p-GRP"},
                    }
                }
            }
        return {"result": {"results": "0"}}

    btn = tracker()
    monkeypatch.setattr(btn, "_api", fake_api)

    assert asyncio.run(btn._uploaded_torrent_id("Show.S01E01.1080p-GRP", "wrong_id", Meta(category="TV", tvdb_id=42))) == "500"  # noqa: S101
    assert {"release": "%Show.S01E01.1080p-GRP%", "tvdb": "42"} in calls  # noqa: S101


def test_btn_api_sends_named_search_parameters(monkeypatch) -> None:
    requests: list[dict[str, object]] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"result": {"results": "0"}})

    original_client = httpx.AsyncClient
    transport = httpx.MockTransport(respond)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original_client(transport=transport, **kwargs))

    asyncio.run(tracker().search_existing(Meta(category="TV", tvdb_id=42)))

    assert requests[0]["id"] == "upload-assistant-btn"  # noqa: S101
    assert requests[0]["method"] == "getTorrents"  # noqa: S101
    assert "jsonrpc" not in requests[0]  # noqa: S101
    assert requests[0]["params"] == {"key": "token", "search": {"category": "Episode", "tvdb": "42"}, "results": 1000, "offset": 0}  # noqa: S101


def test_btn_dupe_search_uses_documented_text_filter(monkeypatch) -> None:
    async def fake_api(method: str, params: dict[str, object]) -> dict[str, object]:
        assert method == "getTorrents"  # noqa: S101
        assert params["search"] == {"category": "Episode", "search": "%Example Show%"}  # noqa: S101
        return {"result": {"results": "0"}}

    btn = tracker()
    monkeypatch.setattr(btn, "_api", fake_api)

    assert asyncio.run(btn.search_existing(Meta(category="TV", title="Example Show"))) == []  # noqa: S101


def test_btn_dupe_search_reads_all_pages(monkeypatch) -> None:
    offsets: list[int] = []

    async def fake_api(_method: str, params: dict[str, object]) -> dict[str, object]:
        offset = int(params["offset"])
        offsets.append(offset)
        torrent_id = str(offset + 1)
        return {"result": {"results": "2", "torrents": {torrent_id: {"GroupID": "123", "ReleaseName": f"Show.S01E0{torrent_id}", "Size": "1024"}}}}

    btn = tracker()
    monkeypatch.setattr(btn, "_api", fake_api)

    dupes = asyncio.run(btn.search_existing(Meta(category="TV", tvdb_id=42)))

    assert offsets == [0, 1]  # noqa: S101
    assert [dupe["name"] for dupe in dupes] == ["Show.S01E01", "Show.S01E02"]  # noqa: S101


def test_btn_dupe_search_does_not_report_api_failure_as_no_dupes(monkeypatch) -> None:
    async def fake_api(_method: str, _params: dict[str, object]) -> dict[str, object]:
        raise UploadError("Unauthorized IP address", "red")

    btn = tracker()
    monkeypatch.setattr(btn, "_api", fake_api)

    with pytest.raises(UploadError, match="Unauthorized IP address"):
        asyncio.run(btn.search_existing(Meta(category="TV", tvdb_id=42)))


def test_btn_dupe_search_escapes_like_characters_in_title(monkeypatch) -> None:
    async def fake_api(_method: str, params: dict[str, object]) -> dict[str, object]:
        assert params["search"] == {"category": "Episode", "search": "%Show\\_50\\%%"}  # noqa: S101
        return {"result": {"results": "0"}}

    btn = tracker()
    monkeypatch.setattr(btn, "_api", fake_api)

    assert asyncio.run(btn.search_existing(Meta(category="TV", title="Show_50%"))) == []  # noqa: S101


def test_btn_api_reports_ip_authorization_hint(monkeypatch) -> None:
    def respond(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"id": "upload-assistant-btn", "result": None, "error": {"code": -32004, "message": "Unauthorized IP address"}})

    original_client = httpx.AsyncClient
    transport = httpx.MockTransport(respond)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original_client(transport=transport, **kwargs))

    with pytest.raises(UploadError, match="Approve the IP in your BTN notices"):
        asyncio.run(tracker().search_existing(Meta(category="TV", tvdb_id=42)))


def test_btn_rejects_bencoded_error_instead_of_seeding_it() -> None:
    with pytest.raises(UploadError, match="invalid torrent"):
        tracker()._registered_torrent(b"d5:error14:login requirede")


def test_btn_get_name_uses_disambiguation_from_btn_series_name(monkeypatch) -> None:
    btn = tracker()

    async def fake_get_series_name(_meta: Meta) -> str:
        return "The Office (US)"

    monkeypatch.setattr(btn, "get_series_name", fake_get_series_name)
    meta = Meta(name="The Office 2005 S01E01 1080p WEB-DL DDP 5.1 x264-GRP", title="The Office", year=2005, resolution="1080p", tag="-GRP")

    assert asyncio.run(btn.get_name(meta)) == "The.Office.US.S01E01.1080p.WEB-DL.DDP5.1.x264-GRP"  # noqa: S101


def test_btn_get_name_removes_year_when_btn_series_has_no_year(monkeypatch) -> None:
    btn = tracker()

    async def fake_get_series_name(_meta: Meta) -> str:
        return "Breaking Bad"

    monkeypatch.setattr(btn, "get_series_name", fake_get_series_name)
    meta = Meta(name="Breaking Bad 2008 S01E01 1080p WEB-DL DDP 5.1 x264-GRP", title="Breaking Bad", year=2008, resolution="1080p", tag="-GRP")

    assert asyncio.run(btn.get_name(meta)) == "Breaking.Bad.S01E01.1080p.WEB-DL.DDP5.1.x264-GRP"  # noqa: S101


def test_btn_get_name_preserves_year_when_btn_series_has_year(monkeypatch) -> None:
    btn = tracker()

    async def fake_get_series_name(_meta: Meta) -> str:
        return "Doctor Who (2005)"

    monkeypatch.setattr(btn, "get_series_name", fake_get_series_name)
    meta = Meta(name="Doctor Who 2005 S01E01 1080p WEB-DL DDP 5.1 x264-GRP", title="Doctor Who", year=2005, resolution="1080p", tag="-GRP")

    assert asyncio.run(btn.get_name(meta)) == "Doctor.Who.2005.S01E01.1080p.WEB-DL.DDP5.1.x264-GRP"  # noqa: S101


def test_btn_get_series_name_fetches_and_caches(monkeypatch) -> None:
    api_calls = 0

    async def fake_api(method: str, params: dict[str, object]) -> dict[str, object]:
        nonlocal api_calls
        api_calls += 1
        assert method == "getTorrents"  # noqa: S101
        assert params["search"] == {"tvdb": "73244"}  # noqa: S101
        return {"result": {"torrents": {"1": {"Series": "The Office (US)"}}}}

    btn = tracker()
    monkeypatch.setattr(btn, "_api", fake_api)
    meta = Meta(tvdb_id=73244)

    assert asyncio.run(btn.get_series_name(meta)) == "The Office (US)"  # noqa: S101
    assert asyncio.run(btn.get_series_name(meta)) == "The Office (US)"  # noqa: S101
    assert api_calls == 1  # noqa: S101


def test_btn_get_series_name_falls_back_to_tvdb_episode_data_when_btn_empty(monkeypatch) -> None:
    async def fake_api(_method: str, _params: dict[str, object]) -> dict[str, object]:
        return {"result": {"torrents": {}}}

    btn = tracker()
    monkeypatch.setattr(btn, "_api", fake_api)
    meta = Meta(
        tvdb_id=73244,
        tvdb_episode_data={"series_name": "The Office (US)"},
        name="The Office 2005 S01E01 1080p WEB-DL DDP 5.1 x264-GRP",
        title="The Office",
        year=2005,
        resolution="1080p",
        tag="-GRP",
    )

    assert asyncio.run(btn.get_series_name(meta)) == "The Office (US)"  # noqa: S101
    assert asyncio.run(btn.get_name(meta)) == "The.Office.US.S01E01.1080p.WEB-DL.DDP5.1.x264-GRP"  # noqa: S101


def test_btn_get_series_name_falls_back_to_tvdb_client(monkeypatch) -> None:
    async def fake_api(_method: str, _params: dict[str, object]) -> dict[str, object]:
        return {"result": {"torrents": {}}}

    class FakeTVDBClient:
        async def get_series_extended(self, series_id: int) -> dict[str, object]:
            assert series_id == 78804  # noqa: S101
            return {"name": "Doctor Who (2005)"}

    monkeypatch.setattr("src.tvdb._get_tvdb_or_warn", lambda _cfg: FakeTVDBClient())

    btn = tracker()
    monkeypatch.setattr(btn, "_api", fake_api)
    meta = Meta(
        tvdb_id=78804,
        name="Doctor Who 2005 S01E01 1080p WEB-DL DDP 5.1 x264-GRP",
        title="Doctor Who",
        year=2005,
        resolution="1080p",
        tag="-GRP",
    )

    assert asyncio.run(btn.get_series_name(meta)) == "Doctor Who (2005)"  # noqa: S101
    assert asyncio.run(btn.get_name(meta)) == "Doctor.Who.2005.S01E01.1080p.WEB-DL.DDP5.1.x264-GRP"  # noqa: S101


def test_btn_verify_autofill_success() -> None:
    btn = tracker()
    meta = Meta(season_int=1, episode_int=2, year=2005)
    data = {"artist": "The Office (US)", "title": "S01E02", "year": "2005"}

    assert btn._verify_autofill(data, meta, "The Office (US)", "Episode") == []  # noqa: S101


def test_btn_verify_autofill_detects_mismatches() -> None:
    btn = tracker()
    meta = Meta(season_int=1, episode_int=2, year=2005)
    data = {"artist": "The Office", "title": "S01E03", "year": "2001"}

    errors = btn._verify_autofill(data, meta, "The Office (US)", "Episode")
    assert any("artist" in e for e in errors)  # noqa: S101
    assert any("title" in e for e in errors)  # noqa: S101
    assert any("year" in e for e in errors)  # noqa: S101


def test_btn_verify_autofill_season_pack_accepts_valid_formats() -> None:
    btn = tracker()
    meta = Meta(season_int=3, tv_pack=True, year=2010)

    for valid_title in ("S03", "s03", "Season 3", "Season 03"):
        data = {"artist": "Breaking Bad", "title": valid_title, "year": "2010"}
        assert btn._verify_autofill(data, meta, "Breaking Bad", "Season") == []  # noqa: S101

    invalid_data = {"artist": "Breaking Bad", "title": "S04", "year": "2010"}
    assert len(btn._verify_autofill(invalid_data, meta, "Breaking Bad", "Season")) == 1  # noqa: S101


def test_btn_verify_autofill_uses_season_year_over_series_year() -> None:
    btn = tracker()
    # Series began in 2005, but Season 3 aired in 2006
    meta = Meta(
        season_int=3,
        episode_int=1,
        year=2005,
        tvdb_episode_data={
            "episodes": [
                {"seasonNumber": 1, "number": 1, "year": "2005"},
                {"seasonNumber": 3, "number": 1, "year": "2006"},
            ]
        },
    )

    valid_data = {"artist": "The Office (US)", "title": "S03E01", "year": "2006"}
    assert btn._verify_autofill(valid_data, meta, "The Office (US)", "Episode") == []  # noqa: S101

    series_year_data = {"artist": "The Office (US)", "title": "S03E01", "year": "2005"}
    errors = btn._verify_autofill(series_year_data, meta, "The Office (US)", "Episode")
    assert errors == ["year '2005' != expected '2006'"]  # noqa: S101
