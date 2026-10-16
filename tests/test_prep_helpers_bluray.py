# ruff: noqa: S101

import pytest

from src.meta import Meta
from src.prep_helpers import _should_add_bluray_link, _should_fetch_bluray_info


def test_bluray_lookup_runs_when_region_and_distributor_are_empty() -> None:
    meta = Meta(is_disc="BDMV", imdb_id=1234567)

    assert _should_fetch_bluray_info(meta, get_bluray_info=True) is True


def test_bluray_lookup_runs_when_only_one_field_is_missing() -> None:
    missing_region = Meta(is_disc="BDMV", imdb_id=1234567, distributor="TEST DISTRIBUTOR")
    missing_distributor = Meta(is_disc="BDMV", imdb_id=1234567, region="B")

    assert _should_fetch_bluray_info(missing_region, get_bluray_info=True) is True
    assert _should_fetch_bluray_info(missing_distributor, get_bluray_info=True) is True


def test_bluray_lookup_skips_when_region_and_distributor_are_present() -> None:
    meta = Meta(is_disc="BDMV", imdb_id=1234567, region="B", distributor="TEST DISTRIBUTOR")

    assert _should_fetch_bluray_info(meta, get_bluray_info=True) is False


@pytest.mark.parametrize("disc", ["BDMV", "DVD"])
@pytest.mark.parametrize("get_info", [False, True])
@pytest.mark.parametrize("region, distributor", [("", ""), ("USA", ""), ("", "BFI"), ("USA", "BFI")])
def test_link_lookup_runs_regardless_of_metadata_options(disc, get_info, region, distributor):
    meta = Meta(is_disc=disc, imdb_id=1234567, region=region, distributor=distributor)
    assert _should_fetch_bluray_info(meta, get_info, add_bluray_link=True)


def test_link_lookup_runs_in_edit_mode():
    assert _should_fetch_bluray_info(Meta(is_disc="BDMV", imdb_id=1234567, edit=True), False, True)


@pytest.mark.parametrize("meta", [Meta(is_disc=""), Meta(is_disc="BDMV", imdb_id=0), Meta(is_disc="BDMV", imdb_id=1234567, site_check=True)])
def test_link_lookup_requires_disc_and_imdb_and_skips_site_checks(meta):
    assert not _should_fetch_bluray_info(meta, True, True)


@pytest.mark.parametrize("default, override, expected", [(True, None, True), (True, False, False), (False, True, True), (False, "true", True), (True, "false", False), (True, "", True)])
@pytest.mark.parametrize("trackers", [["AITHER"], "aither"])
def test_link_lookup_respects_tracker_configuration(default, override, expected, trackers):
    config = {"DEFAULT": {"add_bluray_link": default}, "TRACKERS": {"AITHER": {"add_bluray_link": override}}}
    assert _should_add_bluray_link(Meta(trackers=trackers), config) is expected


def test_link_lookup_uses_configured_default_trackers():
    config = {"DEFAULT": {"add_bluray_link": False}, "TRACKERS": {"default_trackers": "aither, lst", "AITHER": {"add_bluray_link": True}, "LST": {"add_bluray_link": False}}}
    assert _should_add_bluray_link(Meta(), config)
