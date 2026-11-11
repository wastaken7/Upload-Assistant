# ruff: noqa: S101

import json
from typing import Any

import pytest

from src.meta import Meta
from src.trackersetup import TrackerSetup


def test_music_trackers_are_filtered_before_tracker_specific_work():
    meta = Meta(category="MUSIC", trackers=["HDBITS", "ORPHEUS", "AITHER"])
    setup = TrackerSetup(
        {
            "TRACKERS": {
                "HDBITS": {"announce_url": "https://hdbits.example/announce"},
                "ORPHEUS": {"api_key": "token", "announce_url": "https://orpheus.example/announce"},
                "AITHER": {"api_key": "token"},
            }
        }
    )

    setup.filter_unsupported_trackers(meta)

    assert meta.trackers == ["ORPHEUS"]
    assert meta.tracker_status["HDBITS"] == {"upload": False, "skipped": True}
    assert meta.tracker_status["AITHER"] == {"upload": False, "skipped": True}


def test_trackers_without_credentials_are_reported_as_skipped():
    meta = Meta(category="MOVIE", trackers=["AITHER"])
    setup = TrackerSetup({"TRACKERS": {"AITHER": {}}})

    setup.filter_unsupported_trackers(meta)

    assert meta.trackers == []
    assert meta.tracker_status["AITHER"] == {
        "upload": False,
        "skipped": True,
        "status_message": "Missing API key in the tracker configuration",
        "skip_reason": "not_configured",
    }


def test_cathoderaytube_is_registered_for_supported_categories():
    meta = Meta(category="GAME", trackers=["CATHODERAYTUBE"])
    setup = TrackerSetup({"TRACKERS": {"CATHODERAYTUBE": {"announce_url": "https://signal.cathode-ray.tube/passkey/announce"}}})

    setup.filter_unsupported_trackers(meta)

    assert meta.trackers == ["CATHODERAYTUBE"]


class _BannedGroupsResponse:
    status_code = 200

    def json(self) -> dict[str, Any]:
        return {"count": 2, "groups": [{"name": "BannedGroup", "reason": "Rule"}, {"name": "AnotherGroup", "reason": "Rule"}], "updated_at": "2026-08-04"}


class _BannedGroupsClient:
    def __init__(self, requests: list[dict[str, Any]]) -> None:
        self.requests = requests

    async def __aenter__(self) -> _BannedGroupsClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        pass

    async def get(self, **kwargs: Any) -> _BannedGroupsResponse:
        self.requests.append(kwargs)
        return _BannedGroupsResponse()


@pytest.mark.asyncio
async def test_capybarabr_fetches_banned_groups_with_api_token(tmp_path, monkeypatch: pytest.MonkeyPatch):
    requests: list[dict[str, Any]] = []
    monkeypatch.setattr("src.trackersetup.httpx.AsyncClient", lambda: _BannedGroupsClient(requests))
    setup = TrackerSetup({"TRACKERS": {"CAPYBARABR": {"api_key": "test-token"}}})

    file_path = await setup.get_banned_groups(Meta(base_dir=str(tmp_path)), "CAPYBARABR")

    assert requests == [
        {
            "url": "https://capybarabr.com/api/banned-groups",
            "headers": {"Content-Type": "application/json", "Accept": "application/json"},
            "params": {"api_token": "test-token"},
        }
    ]
    assert file_path == tmp_path / "data" / "banned" / "CAPYBARABR_banned_groups.json"
    assert json.loads(file_path.read_text(encoding="utf-8"))["banned_groups"] == "BannedGroup, AnotherGroup"


class _UlcxBlockedGroupsResponse:
    status_code = 200

    def json(self) -> dict[str, Any]:
        return {"data": [{"name": "FakeGrp", "reason": "Low quality encodes", "created_at": "2026-11-08T08:03:11.000000Z"}], "updated_at": "2026-11-08T08:03:11.000000Z"}


class _UlcxClient:
    def __init__(self, requests: list[dict[str, Any]], response: Any) -> None:
        self.requests = requests
        self.response = response

    async def __aenter__(self) -> _UlcxClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        pass

    async def get(self, **kwargs: Any) -> Any:
        self.requests.append(kwargs)
        return self.response


class _FailedResponse:
    status_code = 500

    def json(self) -> dict[str, Any]:
        return {}


@pytest.mark.asyncio
async def test_ulcx_fetches_blocked_groups_with_their_reason(tmp_path, monkeypatch: pytest.MonkeyPatch):
    requests: list[dict[str, Any]] = []
    monkeypatch.setattr("src.trackersetup.httpx.AsyncClient", lambda: _UlcxClient(requests, _UlcxBlockedGroupsResponse()))
    monkeypatch.setattr("src.trackersetup.observe_tracker_response", lambda *_args, **_kwargs: None)
    notes: list[str] = []
    monkeypatch.setattr("src.trackersetup.logger.info", lambda message, *_args, **_kwargs: notes.append(str(message)))
    setup = TrackerSetup({"TRACKERS": {"ULCX": {"api_key": "test-token"}}})
    meta = Meta(base_dir=str(tmp_path), tag="-FakeGrp", unattended=True)

    assert await setup.check_banned_group("ULCX", [], meta) is True

    assert requests[0]["url"] == "https://upload.cx/api/blocked-groups"
    assert requests[0]["headers"]["Authorization"] == "Bearer test-token"
    assert any("Low quality encodes" in note for note in notes)
    saved = json.loads((tmp_path / "data" / "banned" / "ULCX_banned_groups.json").read_text(encoding="utf-8"))
    assert saved["banned_groups"] == "FakeGrp"


@pytest.mark.asyncio
async def test_ulcx_falls_back_to_the_built_in_list_when_the_api_fails(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("src.trackersetup.httpx.AsyncClient", lambda: _UlcxClient([], _FailedResponse()))
    monkeypatch.setattr("src.trackersetup.observe_tracker_response", lambda *_args, **_kwargs: None)
    setup = TrackerSetup({"TRACKERS": {"ULCX": {"api_key": "test-token"}}})

    assert await setup.check_banned_group("ULCX", ["FakeGrp"], Meta(base_dir=str(tmp_path), tag="-FakeGrp", unattended=True)) is True
    assert await setup.check_banned_group("ULCX", ["FakeGrp"], Meta(base_dir=str(tmp_path), tag="-OtherGrp", unattended=True)) is False
