import asyncio
from typing import Any

import pytest

from src.meta import Meta
from src.trackers.UNIT3D.aither import Aither
from src.trackers.UNIT3D.samaritano import Samaritano
from src.trackers.UNIT3D.torrentdesi import DesiTorrents


class FakeResponse:
    status_code = 200

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict[str, list[object]]:
        return {"data": []}


class FakeAsyncClient:
    def __init__(self, requests: list[list[tuple[str, Any]]], **_kwargs: Any) -> None:
        self.requests = requests

    async def __aenter__(self) -> FakeAsyncClient:
        return self

    async def __aexit__(self, *_args: Any) -> None:
        pass

    async def get(self, *, url: str, headers: dict[str, str], params: list[tuple[str, Any]]) -> FakeResponse:
        _ = (url, headers)
        self.requests.append(params)
        return FakeResponse()


def test_desitorrents_declares_metadata_id_endpoint() -> None:
    tracker = DesiTorrents({"TRACKERS": {"DESITORRENTS": {}}})

    assert tracker.id_url == "https://torrent.desi/api/v1/torrents/"  # noqa: S101


@pytest.mark.parametrize("tracker_class", [Aither, Samaritano])
def test_tmdb_duplicate_search_omits_category_filter(monkeypatch: pytest.MonkeyPatch, tracker_class: type[Aither] | type[Samaritano]) -> None:
    requests: list[list[tuple[str, Any]]] = []

    def factory(**kwargs: Any) -> FakeAsyncClient:
        return FakeAsyncClient(requests, **kwargs)

    monkeypatch.setattr("src.trackers.UNIT3D.httpx.AsyncClient", factory)

    tracker = tracker_class({"TRACKERS": {tracker_class.tracker: {"api_key": "test-key"}}})
    meta = Meta(category="TV", tmdb=123, season="S01", resolution="1080p", type="WEBDL")

    asyncio.run(tracker.search_existing(meta))

    assert len(requests) == 1  # noqa: S101
    assert ("tmdbId", "123") in requests[0]  # noqa: S101
    assert not any(key == "categories[]" for key, _value in requests[0])  # noqa: S101


def test_missing_tmdb_keeps_category_filter(monkeypatch: pytest.MonkeyPatch) -> None:
    requests: list[list[tuple[str, Any]]] = []

    def factory(**kwargs: Any) -> FakeAsyncClient:
        return FakeAsyncClient(requests, **kwargs)

    monkeypatch.setattr("src.trackers.UNIT3D.httpx.AsyncClient", factory)

    tracker = Aither({"TRACKERS": {"AITHER": {"api_key": "test-key"}}})
    meta = Meta(category="TV", tmdb=None, season="S01", resolution="1080p", type="WEBDL")

    asyncio.run(tracker.search_existing(meta))

    assert ("categories[]", "2") in requests[0]  # noqa: S101


class DetailFakeClient:
    """Search results without MediaInfo (newer UNIT3D), with a per-torrent detail endpoint."""

    def __init__(self, calls: list[str], **_kwargs: Any) -> None:
        self.calls = calls

    async def __aenter__(self) -> DetailFakeClient:
        return self

    async def __aexit__(self, *_args: Any) -> None:
        pass

    async def get(self, url: str, headers: dict[str, str], params: list[tuple[str, Any]] | None = None) -> Any:
        _ = (headers, params)
        self.calls.append(url)
        if url.endswith("/filter"):
            data = [
                {"id": "1", "attributes": {"name": "Fictional Film 2021 1080p Blu-ray AVC", "type": "Full Disc", "resolution": "1080p", "size": 1}},
                {"id": "2", "attributes": {"name": "Fictional Film 2021 2160p WEB-DL H.265-NOGRPA", "type": "WEB-DL", "resolution": "2160p", "size": 1}},
                {"id": "3", "attributes": {"name": "Fictional Film 2021 1080p WEB-DL H.264-NOGRPB", "type": "WEB-DL", "resolution": "1080p", "size": 1}},
            ]
            return DetailResponse({"data": data})
        torrent_id = url.rsplit("/", 1)[1]
        return DetailResponse({"type": "torrent", "id": torrent_id, "attributes": {"media_info": f"Video\nFormat : AVC ({torrent_id})", "bd_info": "", "description": ""}})


class DetailResponse:
    status_code = 200

    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict[str, Any]:
        return self.payload


def test_missing_mediainfo_is_fetched_per_torrent(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr("src.trackers.UNIT3D.httpx.AsyncClient", lambda **kwargs: DetailFakeClient(calls, **kwargs))

    async def no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr("src.trackers.UNIT3D.asyncio.sleep", no_sleep)

    tracker = Samaritano({"DEFAULT": {}, "TRACKERS": {"SAMARITANO": {"api_key": "test-key"}}})
    meta = Meta(category="MOVIE", tmdb=123, resolution="1080p", type="WEBDL")
    dupes = asyncio.run(tracker.search_existing(meta))

    detail_calls = [call for call in calls if not call.endswith("/filter")]
    # The full disc is skipped and the upload's resolution is fetched first.
    assert [call.rsplit("/", 1)[1] for call in detail_calls] == ["3", "2"]  # noqa: S101
    by_id = {dupe["id"]: dupe for dupe in dupes}
    assert by_id["3"]["media_info"] == "Video\nFormat : AVC (3)"  # noqa: S101
    assert by_id["1"]["media_info"] is None  # noqa: S101


def test_missing_mediainfo_is_not_fetched_without_slot_rules(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr("src.trackers.UNIT3D.httpx.AsyncClient", lambda **kwargs: DetailFakeClient(calls, **kwargs))

    tracker = Samaritano({"DEFAULT": {"slot_rules": False}, "TRACKERS": {"SAMARITANO": {"api_key": "test-key"}}})
    asyncio.run(tracker.search_existing(Meta(category="MOVIE", tmdb=123, resolution="1080p", type="WEBDL")))

    assert all(call.endswith("/filter") for call in calls)  # noqa: S101


def test_whole_title_search_keeps_basic_results_filtered(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.trackers.UNIT3D.capybarabr import CapybaraBR

    requests: list[list[tuple[str, Any]]] = []

    class TitleClient(FakeAsyncClient):
        async def get(self, *, url: str, headers: dict[str, str], params: list[tuple[str, Any]]) -> Any:
            _ = (url, headers)
            self.requests.append(params)
            data = [
                {"id": "1", "attributes": {"name": "Fictional Film 2021 1080p WEB-DL DUAL-NOGRPA", "type_id": 4, "resolution_id": 3, "media_info": "x"}},
                {"id": "2", "attributes": {"name": "Fictional Film 2021 1080p BluRay REMUX-NOGRPB", "type_id": 3, "resolution_id": 3, "media_info": "x"}},
                {"id": "3", "attributes": {"name": "Fictional Film 2021 2160p BluRay REMUX-NOGRPC", "type_id": 3, "resolution_id": 2, "media_info": "x"}},
            ]
            return DetailResponse({"data": data})

    monkeypatch.setattr("src.trackers.UNIT3D.httpx.AsyncClient", lambda **kwargs: TitleClient(requests, **kwargs))
    tracker = CapybaraBR({"DEFAULT": {}, "TRACKERS": {"CAPYBARABR": {"api_key": "test-key"}}})
    meta = Meta(category="MOVIE", tmdb=123, resolution="1080p", type="REMUX")
    monkeypatch.setattr(tracker, "get_type_id", AsyncMockValue({"type_id": "3"}))
    monkeypatch.setattr(tracker, "get_resolution_id", AsyncMockValue({"resolution_id": "3"}))

    dupes = asyncio.run(tracker.search_existing(meta))

    assert not any(key in ("types[]", "resolutions[]") for key, _value in requests[0])  # noqa: S101
    assert [dupe["id"] for dupe in dupes] == ["2"]  # noqa: S101
    assert [release["id"] for release in meta["CAPYBARABR_title_releases"]] == ["1", "2", "3"]  # noqa: S101


class AsyncMockValue:
    def __init__(self, value: Any) -> None:
        self.value = value

    async def __call__(self, *_args: Any, **_kwargs: Any) -> Any:
        return self.value


def test_search_clears_title_list_from_an_earlier_search(monkeypatch: pytest.MonkeyPatch) -> None:
    requests: list[list[tuple[str, Any]]] = []
    monkeypatch.setattr("src.trackers.UNIT3D.httpx.AsyncClient", lambda **kwargs: FakeAsyncClient(requests, **kwargs))
    tracker = Samaritano({"DEFAULT": {}, "TRACKERS": {"SAMARITANO": {"api_key": "test-key"}}})
    meta = Meta(category="MOVIE", tmdb=123, resolution="1080p", type="WEBDL")
    meta["SAMARITANO_title_releases"] = [{"name": "stale"}]

    asyncio.run(tracker.search_existing(meta))

    assert meta.get("SAMARITANO_title_releases") is None  # noqa: S101


def test_empty_mediainfo_in_search_results_is_fetched(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    class EmptyFieldClient(DetailFakeClient):
        async def get(self, url: str, headers: dict[str, str], params: list[tuple[str, Any]] | None = None) -> Any:
            if url.endswith("/filter"):
                self.calls.append(url)
                data = [{"id": "7", "attributes": {"name": "Fictional Film 2021 1080p WEB-DL H.264-NOGRPB", "type": "WEB-DL", "resolution": "1080p", "media_info": None}}]
                return DetailResponse({"data": data})
            return await super().get(url, headers, params)

    async def no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr("src.trackers.UNIT3D.httpx.AsyncClient", lambda **kwargs: EmptyFieldClient(calls, **kwargs))
    monkeypatch.setattr("src.trackers.UNIT3D.asyncio.sleep", no_sleep)
    tracker = Samaritano({"DEFAULT": {}, "TRACKERS": {"SAMARITANO": {"api_key": "test-key"}}})
    dupes = asyncio.run(tracker.search_existing(Meta(category="MOVIE", tmdb=123, resolution="1080p", type="WEBDL")))

    assert dupes[0]["media_info"] == "Video\nFormat : AVC (7)"  # noqa: S101


class TypeIdOnlyClient(DetailFakeClient):
    async def get(self, url: str, headers: dict[str, str], params: list[tuple[str, Any]] | None = None) -> Any:
        if url.endswith("/filter"):
            self.calls.append(url)
            data = [{"id": "9", "attributes": {"name": "Fictional Film 2021 1080p Blu-ray AVC", "type_id": 1, "resolution": "1080p", "size": 1}}]
            return DetailResponse({"data": data})
        return await super().get(url, headers, params)


def test_disc_without_type_label_uses_type_id(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr("src.trackers.UNIT3D.httpx.AsyncClient", lambda **kwargs: TypeIdOnlyClient(calls, **kwargs))
    tracker = Samaritano({"DEFAULT": {}, "TRACKERS": {"SAMARITANO": {"api_key": "test-key"}}})
    disc_meta = Meta(category="MOVIE", tmdb=123, resolution="1080p", type="DISC", is_disc="BDMV")

    asyncio.run(tracker.search_existing(disc_meta))

    assert any(call.endswith("/9") for call in calls)  # noqa: S101


def test_type_mapping_errors_do_not_break_the_search(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr("src.trackers.UNIT3D.httpx.AsyncClient", lambda **kwargs: TypeIdOnlyClient(calls, **kwargs))
    tracker = Samaritano({"DEFAULT": {}, "TRACKERS": {"SAMARITANO": {"api_key": "test-key"}}})
    real_get_type_id = tracker.get_type_id

    async def failing_mapping(meta: Meta, type: str = "", reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        if mapping_only:
            raise ValueError("mapping not supported")
        return await real_get_type_id(meta, type, reverse)

    monkeypatch.setattr(tracker, "get_type_id", failing_mapping)
    disc_meta = Meta(category="MOVIE", tmdb=123, resolution="1080p", type="DISC", is_disc="BDMV")

    dupes = asyncio.run(tracker.search_existing(disc_meta))

    assert len(dupes) == 1  # noqa: S101


def test_disc_detected_by_upload_type_id_when_mapping_has_no_disc(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr("src.trackers.UNIT3D.httpx.AsyncClient", lambda **kwargs: TypeIdOnlyClient(calls, **kwargs))
    tracker = Samaritano({"DEFAULT": {}, "TRACKERS": {"SAMARITANO": {"api_key": "test-key"}}})

    async def upload_type_only(meta: Meta, type: str = "", reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:  # noqa: ARG001
        return {"type_id": "1"}

    monkeypatch.setattr(tracker, "get_type_id", upload_type_only)
    asyncio.run(tracker.search_existing(Meta(category="MOVIE", tmdb=123, resolution="1080p", type="DISC", is_disc="BDMV")))

    assert any(call.endswith("/9") for call in calls)  # noqa: S101
