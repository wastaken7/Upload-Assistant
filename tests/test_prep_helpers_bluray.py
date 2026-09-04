# ruff: noqa: S101

from src.meta import Meta
from src.prep_helpers import _should_fetch_bluray_info


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
