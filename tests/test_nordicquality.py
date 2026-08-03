import asyncio

from src.meta import Meta
from src.trackers.UNIT3D.nordicquality import NordicQuality
from src.trackersetup import TrackerSetup, tracker_class_map


def _tracker() -> NordicQuality:
    return NordicQuality({"DEFAULT": {}, "TRACKERS": {"NORDICQUALITY": {}}})


def test_nordicquality_is_registered_with_its_full_tracker_name():
    assert tracker_class_map["NORDICQUALITY"] is NordicQuality  # noqa: S101
    assert NordicQuality.display_name == "NordicQuality"  # noqa: S101


def test_nordicquality_filters_unsupported_categories():
    meta = Meta(category="BOOK", trackers=["NORDICQUALITY"])
    setup = TrackerSetup({"TRACKERS": {"NORDICQUALITY": {"api_key": "token"}}})

    setup.filter_unsupported_trackers(meta)

    assert meta.trackers == []  # noqa: S101
    assert meta.tracker_status["NORDICQUALITY"] == {"upload": False, "skipped": True}  # noqa: S101


def test_nordicquality_accepts_nordic_subtitles_when_unattended():
    meta = Meta(category="MOVIE", language_checked=True, subtitle_languages=["English", "Norwegian"], unattended=True)

    assert asyncio.run(_tracker().get_additional_checks(meta)) is True  # noqa: S101


def test_nordicquality_rejects_movie_without_nordic_subtitles():
    meta = Meta(category="MOVIE", language_checked=True, subtitle_languages=["English"], unattended=True)

    assert asyncio.run(_tracker().get_additional_checks(meta)) is False  # noqa: S101


def test_nordicquality_sanitizes_upload_name():
    meta = Meta(uuid="\u00c6r\u00f8sk\u00f8bing \u00c5r 2025 HDR10+ DD+ DTS:X &.mkv")

    assert asyncio.run(_tracker().get_name(meta)) == {"name": "AEroskobing.Ar.2025.HDR10P.DDP.DTS-X.and"}  # noqa: S101
