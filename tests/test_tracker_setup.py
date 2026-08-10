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
