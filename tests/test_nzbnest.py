import asyncio
from pathlib import Path
from typing import Any, ClassVar

from src.meta import Meta
from src.trackers.USENET.nzbnest import NzbNest
from src.trackersetup import tracker_class_map


class _Response:
    status_code = 201
    text = '{"guid":"release-guid"}'

    def json(self) -> dict[str, str]:
        return {"guid": "release-guid"}

    def raise_for_status(self) -> None:
        return None


class _Client:
    request: ClassVar[dict[str, Any]] = {}
    response: ClassVar[_Response] = _Response()

    async def __aenter__(self) -> _Client:
        return self

    async def __aexit__(self, *_args: Any) -> None:
        return None

    async def post(self, url: str, **kwargs: Any) -> _Response:
        type(self).request = {"url": url, **kwargs}
        return self.response


class _SearchResponse(_Response):
    text = """<?xml version="1.0" encoding="UTF-8"?>
<rss xmlns:newznab="http://www.newznab.com/DTD/2010/feeds/attributes/">
  <channel>
    <item>
      <title>Movie.Name.2026.1080p</title>
      <guid>release-guid</guid>
      <newznab:attr name="size" value="12345" />
    </item>
  </channel>
</rss>"""


class _SearchClient(_Client):
    async def get(self, url: str, **kwargs: Any) -> _SearchResponse:
        type(self).request = {"url": url, **kwargs}
        return _SearchResponse()


def test_nzbnest_is_registered() -> None:
    assert tracker_class_map["NZBNEST"] is NzbNest  # noqa: S101
    assert NzbNest.is_usenet  # noqa: S101


def test_nzbnest_uses_documented_upload_fields(monkeypatch: Any, tmp_path: Path) -> None:
    nzb_path = tmp_path / "Release.Name.nzb"
    nzb_path.write_text("<nzb />", encoding="utf-8")
    nfo_dir = tmp_path / "tmp" / "test"
    nfo_dir.mkdir(parents=True)
    (nfo_dir / "MEDIAINFO_CLEANPATH.txt").write_text("MediaInfo", encoding="utf-8")
    meta = Meta(
        nzb_path=str(nzb_path),
        base_dir=str(tmp_path),
        uuid="test",
        category="MOVIE",
        basename_no_ext="Release.Name",
        tracker_status={},
    )
    tracker = NzbNest({"TRACKERS": {"NZBNEST": {"api_key": "secret"}}, "USENET": {}})
    monkeypatch.setattr("src.trackers.USENET.nzbnest.httpx.AsyncClient", lambda **_kwargs: _Client())

    assert asyncio.run(tracker.upload(meta)) is True  # noqa: S101
    assert _Client.request["url"] == "https://nzbnest.com/v1/upload"  # noqa: S101
    assert _Client.request["params"] == {"apikey": "secret"}  # noqa: S101
    assert set(_Client.request["files"]) == {"file", "nfo"}  # noqa: S101
    assert _Client.request["files"]["nfo"][0] == "Release.Name.nfo"  # noqa: S101
    assert meta.tracker_status["NZBNEST"] == {  # noqa: S101
        "status_message": "Upload successful",
        "torrent_id": "release-guid",
    }
    assert (nfo_dir / "NZBNEST_upload_ok").is_file()  # noqa: S101


def test_nzbnest_requires_guid(monkeypatch: Any, tmp_path: Path) -> None:
    class ResponseWithoutGuid(_Response):
        text = "{}"

        def json(self) -> dict[str, str]:
            return {}

    monkeypatch.setattr(_Client, "response", ResponseWithoutGuid())
    monkeypatch.setattr("src.trackers.USENET.nzbnest.httpx.AsyncClient", lambda **_kwargs: _Client())
    nzb_path = tmp_path / "release.nzb"
    nzb_path.write_text("<nzb />", encoding="utf-8")
    meta = Meta(nzb_path=str(nzb_path), base_dir=str(tmp_path), uuid="test", tracker_status={})

    assert asyncio.run(NzbNest({"TRACKERS": {"NZBNEST": {"api_key": "secret"}}}).upload(meta)) is False  # noqa: S101
    assert meta.tracker_status["NZBNEST"]["status_message"] == "data error: NzbNest did not return a release guid."  # noqa: S101


def test_nzbnest_searches_with_newznab_movie_parameters(monkeypatch: Any, tmp_path: Path) -> None:
    meta = Meta(
        base_dir=str(tmp_path),
        uuid="test",
        category="MOVIE",
        resolution="1080p",
        imdb_tt="tt1234567",
        basename_no_ext="Movie.Name.2026.1080p",
    )
    tracker = NzbNest({"TRACKERS": {"NZBNEST": {"api_key": "secret", "daily_api_hit_limit": 5}}})
    monkeypatch.setattr("src.trackers.USENET.nzbnest.httpx.AsyncClient", lambda **_kwargs: _SearchClient())

    dupes = asyncio.run(tracker.search_existing(meta))

    assert _SearchClient.request["url"] == "https://nzbnest.com/api"  # noqa: S101
    assert _SearchClient.request["params"] == {  # noqa: S101
        "apikey": "secret",
        "limit": "100",
        "extended": "1",
        "cat": "2040",
        "t": "movie",
        "imdbid": "tt1234567",
    }
    assert dupes == [  # noqa: S101
        {
            "name": "Movie.Name.2026.1080p",
            "files": "Movie.Name.2026.1080p",
            "size": 12345,
            "link": "https://nzbnest.com/account/releases/release-guid",
        }
    ]


def test_nzbnest_searches_xxx_without_unsupported_category_filter(monkeypatch: Any, tmp_path: Path) -> None:
    meta = Meta(base_dir=str(tmp_path), uuid="test", category="XXX", basename_no_ext="Release.Name")
    tracker = NzbNest({"TRACKERS": {"NZBNEST": {"api_key": "secret", "daily_api_hit_limit": 5}}})
    monkeypatch.setattr("src.trackers.USENET.nzbnest.httpx.AsyncClient", lambda **_kwargs: _SearchClient())

    asyncio.run(tracker.search_existing(meta))

    assert _SearchClient.request["params"]["t"] == "search"  # noqa: S101
    assert _SearchClient.request["params"]["q"] == "Release.Name"  # noqa: S101
    assert "cat" not in _SearchClient.request["params"]  # noqa: S101
