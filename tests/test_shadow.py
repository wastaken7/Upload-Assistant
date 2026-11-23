import asyncio
from email import policy
from email.parser import BytesParser
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest

from src.meta import Meta
from src.payload_preview import accept_edits
from src.trackers.UNIT3D.shadow import Shadow
from src.trackersetup import api_trackers, tracker_class_map


@pytest.fixture
def shadow() -> Shadow:
    return Shadow({"DEFAULT": {}, "TRACKERS": {"SHADOW": {"api_key": "test-key"}}})


@pytest.mark.parametrize(
    ("metadata", "category_id", "type_id", "resolution_id"),
    [
        (Meta(category="MOVIE", type="WEBDL", resolution="2160p"), "14", "4", "2"),
        (Meta(category="MOVIE", type="WEBDL", resolution="2160p", subtitle_languages=["ro-RO"]), "16", "4", "2"),
        (Meta(category="MOVIE", type="ENCODE", resolution="1080p", subtitle_languages="English, Romanian (Forced)"), "2", "3", "3"),
        (Meta(category="MOVIE", type="ENCODE", resolution="1080p", audio_languages=["Romanian"], subtitle_languages=["English"]), "13", "3", "3"),
        (Meta(category="MOVIE", type="DVDRIP", resolution="576p"), "12", "50", "6"),
        (Meta(category="MOVIE", type="DVDRIP", resolution="576p", subtitle_languages=["rum"]), "15", "50", "6"),
        (Meta(category="TV", type="HDTV", resolution="720p", tv_pack=True), "17", "6", "5"),
        (Meta(category="TV", type="HDTV", resolution="720p", tv_pack=True, subtitle_languages=["ron"]), "11", "6", "5"),
        (Meta(category="TV", type="WEBDL", resolution="1080p", hardcoded_subs=True, hardcoded_subs_language="română"), "11", "4", "3"),
        (Meta(category="TV", type="WEBDL", resolution="1080p", genres=["Documentary"], subtitle_languages=["Romanian"]), "22", "4", "3"),
        (Meta(category="MOVIE", type="DISC", resolution="1080p", is_disc="BDMV", bdinfo={"subtitles": ["Romanian"]}), "2", "1", "3"),
        (Meta(category="BOOK", container=".epub"), "23", "30", None),
        (Meta(category="BOOK", audiobook=True), "23", "33", None),
        (Meta(category="GAME", platform="PC"), "19", "15", None),
        (Meta(category="GAME", platform="XSX", console_game=True), "20", "17", None),
        (Meta(category="GAME", platform="SWITCH2", game_subcategory="dlc"), "20", "21", None),
        (Meta(category="MUSIC", music_release={"fields": {"release_type": {"value": "Album"}}}, format="FLAC"), "27", "7", None),
        (Meta(category="MUSIC", format="MP3"), "26", "13", None),
        (Meta(category="XXX", name="Fictional Collection", resolution="1080p"), "33", "42", "3"),
    ],
)
def test_shadow_preview_payload(shadow: Shadow, metadata: Meta, category_id: str, type_id: str, resolution_id: str | None) -> None:
    data = asyncio.run(shadow.get_data(metadata, preview=True))
    assert data["category_id"] == category_id
    assert data["type_id"] == type_id
    assert data.get("resolution_id") == resolution_id


def test_shadow_is_registered_for_unit3d() -> None:
    assert tracker_class_map["SHADOW"] is Shadow
    assert "SHADOW" in api_trackers


def test_shadow_uses_embedded_subtitles_with_a_different_burned_in_language(shadow: Shadow) -> None:
    meta = Meta(
        category="MOVIE",
        resolution="1080p",
        hardcoded_subs=True,
        hardcoded_subs_language="English",
        subtitle_languages=["English"],
        mediainfo={"media": {"track": [{"@type": "Text", "Language": "ro"}]}},
    )
    assert asyncio.run(shadow.get_category_id(meta)) == {"category_id": "2"}


@pytest.mark.parametrize(("torrent_layout", "expected_id"), [("BASE_SUBS", "2"), ("BASE", "13")])
def test_shadow_only_counts_external_subtitles_when_included(shadow: Shadow, monkeypatch: pytest.MonkeyPatch, torrent_layout: str, expected_id: str) -> None:
    meta = Meta(category="MOVIE", resolution="1080p", subtitle_files=["Fictional.Movie.ro.forced.srt"])
    monkeypatch.setattr(shadow.common, "get_torrent_filename", AsyncMock(return_value=torrent_layout))
    assert asyncio.run(shadow.get_category_id(meta)) == {"category_id": expected_id}


@pytest.mark.parametrize("override", [False, True])
def test_shadow_automatic_category_and_preview_override_reach_upload(shadow: Shadow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, override: bool) -> None:
    meta = Meta(category="MOVIE", type="WEBDL", resolution="1080p", name="Fictional Movie", debug=False, tracker_status={"SHADOW": {}}, subtitle_languages=["Romanian"])
    preview = asyncio.run(shadow.get_payload_preview(meta))
    category = preview.find("category_id")
    assert category is not None
    assert ("2", "Filme HD-RO") in category.choices
    assert ("28", "Filme Pack-RO") in category.choices
    assert ("17", "Serial TV") not in category.choices
    assert category.value == "2"
    if override:
        accept_edits(meta, {"SHADOW": preview}, {"SHADOW": {"category_id": "13"}})

    torrent = tmp_path / "base.torrent"
    torrent.write_bytes(b"test torrent")
    monkeypatch.setattr(shadow.common, "get_base_torrent_path", AsyncMock(return_value=torrent))
    monkeypatch.setattr(shadow.common, "download_tracker_torrent", AsyncMock())
    monkeypatch.setattr(shadow, "get_description", AsyncMock(return_value={"description": "Test release"}))
    monkeypatch.setattr(shadow, "get_mediainfo", AsyncMock(return_value={"mediainfo": "Test MediaInfo"}))
    monkeypatch.setattr(shadow, "observe_api_key_expiry", lambda *_: None)

    def upload(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == shadow.upload_url
        assert request.headers["authorization"] == "Bearer test-key"
        form = BytesParser(policy=policy.default).parsebytes(f"Content-Type: {request.headers['content-type']}\r\n\r\n".encode() + request.content)
        fields = {part.get_param("name", header="content-disposition"): part.get_payload(decode=True) for part in form.iter_parts()}
        assert fields["category_id"] == (b"13" if override else b"2")
        assert fields["type_id"] == b"4"
        assert fields["resolution_id"] == b"3"
        return httpx.Response(200, json={"success": True, "data": f"{shadow.base_url}/torrent/download/7.example"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(upload))
    monkeypatch.setattr("src.trackers.UNIT3D.httpx.AsyncClient", lambda **_: client)
    assert asyncio.run(shadow.upload(meta))
    assert meta.tracker_status["SHADOW"]["torrent_id"] == "7"


def test_shadow_dupe_search_covers_both_tv_categories_without_tmdb(shadow: Shadow, monkeypatch: pytest.MonkeyPatch) -> None:
    def search(request: httpx.Request) -> httpx.Response:
        assert request.url.params.get_list("categories[]") == ["11", "17", "22"]
        assert request.url.params["name"] == "Fictional Show S01"
        assert "tmdbId" not in request.url.params
        return httpx.Response(200, json={"data": []})

    client = httpx.AsyncClient(transport=httpx.MockTransport(search))
    monkeypatch.setattr("src.trackers.UNIT3D.httpx.AsyncClient", lambda **_: client)
    monkeypatch.setattr(shadow, "observe_api_key_expiry", lambda *_: None)
    meta = Meta(category="TV", title="Fictional Show", season="S01", tmdb=0, type="WEBDL", resolution="1080p")
    assert asyncio.run(shadow.search_existing(meta)) == []
