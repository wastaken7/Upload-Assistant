import asyncio

from src.meta import _TRACKER_ID_ALIASES, Meta
from src.trackers.UNIT3D.echelonhd import EchelonHD
from src.trackersetup import tracker_class_map


def _tracker() -> EchelonHD:
    return EchelonHD({"TRACKERS": {"ECHELONHD": {"api_key": ""}}})


def test_echelonhd_is_registered_with_full_tracker_name():
    assert tracker_class_map["ECHELONHD"] is EchelonHD  # noqa: S101
    assert EchelonHD.display_name == "EchelonHD"  # noqa: S101
    assert EchelonHD.supported_categories == ("TV", "MOVIE")  # noqa: S101
    assert EchelonHD.search_url == "https://echelonhd.me/api/torrents/filter"  # noqa: S101
    assert EchelonHD.upload_url == "https://echelonhd.me/api/torrents/upload"  # noqa: S101


def test_echelonhd_ehd_alias_resolves_to_the_canonical_name():
    assert _TRACKER_ID_ALIASES["EHD"] == "ECHELONHD"  # noqa: S101
    assert Meta().canonical_tracker_name("ehd") == "ECHELONHD"  # noqa: S101


def test_echelonhd_uses_stock_unit3d_ids():
    # Verified against the live API: Movies -> category_id 1, WEB-DL -> type_id 4, 1080p -> resolution_id 3.
    tracker = _tracker()
    meta = Meta(category="MOVIE", type="WEBDL", resolution="1080p")
    assert asyncio.run(tracker.get_category_id(meta)) == {"category_id": "1"}  # noqa: S101
    assert asyncio.run(tracker.get_type_id(meta)) == {"type_id": "4"}  # noqa: S101
    assert asyncio.run(tracker.get_resolution_id(meta)) == {"resolution_id": "3"}  # noqa: S101
