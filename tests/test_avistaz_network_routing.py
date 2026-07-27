from types import SimpleNamespace

import pytest

from src.trackers.AVISTAZ.routing import AvistaZNetworkRouter
from src.trackerstatus import merge_tracker_status


class FakeTracker:
    cookie_valid = True

    def __init__(self, config):
        self.config = config

    async def validate_credentials(self, _meta):
        return self.cookie_valid


def make_meta(**overrides):
    values = {
        "origin_country": ["US"],
        "year": 2020,
        "sd": False,
        "resolution": "1080p",
        "trackers": ["PRIVATEHD"],
        "tracker_status": {},
        "unattended": True,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def router():
    return AvistaZNetworkRouter({"DEFAULT": {"avistaz_network_auto_redirect": True}}, {"AVISTAZ": FakeTracker, "CINEMAZ": FakeTracker, "PRIVATEHD": FakeTracker})


@pytest.mark.asyncio
async def test_old_privatehd_content_is_redirected_after_cookie_validation():
    meta = make_meta(year=1970)

    await router().apply(meta)

    assert meta.trackers == ["CINEMAZ"]  # noqa: S101
    assert meta.tracker_status["PRIVATEHD"]["redirected_to"] == "CINEMAZ"  # noqa: S101
    assert meta.tracker_status["CINEMAZ"]["redirected_from"] == ["PRIVATEHD"]  # noqa: S101


@pytest.mark.asyncio
async def test_redirect_keeps_source_when_destination_cookie_is_invalid():
    meta = make_meta(year=1970)
    FakeTracker.cookie_valid = False
    try:
        await router().apply(meta)
    finally:
        FakeTracker.cookie_valid = True

    assert meta.trackers == ["PRIVATEHD"]  # noqa: S101
    assert "routing_error" in meta.tracker_status["PRIVATEHD"]  # noqa: S101


@pytest.mark.asyncio
async def test_conflicting_rules_require_manual_review():
    meta = make_meta(year=1970, origin_country=["JP"])

    await router().apply(meta)

    assert meta.trackers == ["PRIVATEHD"]  # noqa: S101
    assert meta.tracker_status["PRIVATEHD"]["routing_suggested_to"] is None  # noqa: S101


@pytest.mark.asyncio
async def test_asian_privatehd_content_is_redirected_to_avistaz():
    meta = make_meta(origin_country=["JP"])

    await router().apply(meta)

    assert meta.trackers == ["AVISTAZ"]  # noqa: S101


@pytest.mark.asyncio
async def test_recent_english_content_on_cinemaz_is_only_suggested():
    meta = make_meta(trackers=["CINEMAZ"])

    await router().apply(meta)

    assert meta.trackers == ["CINEMAZ"]  # noqa: S101
    assert meta.tracker_status["CINEMAZ"]["routing_suggested_to"] == "PRIVATEHD"  # noqa: S101


@pytest.mark.asyncio
async def test_sd_resolution_prevents_cinemaz_to_privatehd_suggestion():
    meta = make_meta(trackers=["CINEMAZ"], resolution="480p", sd=False)

    await router().apply(meta)

    assert meta.tracker_status == {}  # noqa: S101


def test_merge_tracker_status_preserves_routing_metadata():
    merged = merge_tracker_status(
        {"CINEMAZ": {"upload": True, "skipped": False}},
        {"PRIVATEHD": {"redirected_to": "CINEMAZ", "skipped": True}, "CINEMAZ": {"redirected_from": ["PRIVATEHD"]}},
    )

    assert merged["PRIVATEHD"]["redirected_to"] == "CINEMAZ"  # noqa: S101
    assert merged["CINEMAZ"] == {"redirected_from": ["PRIVATEHD"], "upload": True, "skipped": False}  # noqa: S101
