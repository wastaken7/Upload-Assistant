import asyncio
from unittest.mock import AsyncMock

from src.meta import Meta
from src.trackers.UNIT3D.nordicquality import NordicQuality
from src.trackersetup import TrackerSetup, tracker_class_map


def _tracker() -> NordicQuality:
    return NordicQuality({"DEFAULT": {}, "TRACKERS": {"NORDICQUALITY": {}}})


def test_nordicquality_is_registered_with_its_full_tracker_name():
    assert tracker_class_map["NORDICQUALITY"] is NordicQuality  # noqa: S101
    assert NordicQuality.display_name == "NordicQuality"  # noqa: S101


def test_nordicquality_filters_unsupported_categories():
    meta = Meta(category="XXX", trackers=["NORDICQUALITY"])
    setup = TrackerSetup({"TRACKERS": {"NORDICQUALITY": {"api_key": "token"}}})

    setup.filter_unsupported_trackers(meta)

    assert meta.trackers == []  # noqa: S101
    assert meta.tracker_status["NORDICQUALITY"] == {"upload": False, "skipped": True}  # noqa: S101


def test_nordicquality_accepts_book_music_and_game_categories():
    setup = TrackerSetup({"TRACKERS": {"NORDICQUALITY": {"api_key": "token"}}})

    for category in ("BOOK", "MUSIC", "GAME"):
        meta = Meta(category=category, trackers=["NORDICQUALITY"])
        setup.filter_unsupported_trackers(meta)

        assert meta.trackers == ["NORDICQUALITY"]  # noqa: S101


def test_nordicquality_category_ids():
    tracker = _tracker()

    assert asyncio.run(tracker.get_category_id(Meta(category="BOOK"))) == {"category_id": "7"}  # noqa: S101
    assert asyncio.run(tracker.get_category_id(Meta(category="BOOK", audiobook=True))) == {"category_id": "8"}  # noqa: S101
    assert asyncio.run(tracker.get_category_id(Meta(category="MUSIC"))) == {"category_id": "3"}  # noqa: S101
    assert asyncio.run(tracker.get_category_id(Meta(category="GAME"))) == {"category_id": "4"}  # noqa: S101


def test_nordicquality_type_ids_for_music_books_and_games():
    tracker = _tracker()

    assert asyncio.run(tracker.get_type_id(Meta(category="MUSIC", format="MP3"))) == {"type_id": "7"}  # noqa: S101
    assert asyncio.run(tracker.get_type_id(Meta(category="MUSIC", format="FLAC"))) == {"type_id": "8"}  # noqa: S101
    assert asyncio.run(tracker.get_type_id(Meta(category="BOOK", format="EPUB"))) == {"type_id": "9"}  # noqa: S101
    assert asyncio.run(tracker.get_type_id(Meta(category="BOOK", format="PDF"))) == {"type_id": "10"}  # noqa: S101
    assert asyncio.run(tracker.get_type_id(Meta(category="GAME", platform="Windows"))) == {"type_id": "11"}  # noqa: S101
    assert asyncio.run(tracker.get_type_id(Meta(category="GAME", platform="Linux"))) == {"type_id": "17"}  # noqa: S101
    assert asyncio.run(tracker.get_type_id(Meta(category="GAME", platform="macOS"))) == {"type_id": "12"}  # noqa: S101
    assert asyncio.run(tracker.get_type_id(Meta(category="GAME", platform="Android"))) == {"type_id": "13"}  # noqa: S101
    assert asyncio.run(tracker.get_type_id(Meta(category="GAME", platform="iOS"))) == {"type_id": "14"}  # noqa: S101
    assert asyncio.run(tracker.get_type_id(Meta(category="GAME", console_game=True))) == {"type_id": "18"}  # noqa: S101
    assert asyncio.run(tracker.get_type_id(Meta(category="GAME"))) == {"type_id": "15"}  # noqa: S101


def test_nordicquality_accepts_nordic_subtitles_when_unattended():
    meta = Meta(category="MOVIE", language_checked=True, subtitle_languages=["English", "Norwegian"], unattended=True)

    assert asyncio.run(_tracker().get_additional_checks(meta)) is True  # noqa: S101


def test_nordicquality_accepts_nordic_subtitle_language_codes_when_unattended():
    meta = Meta(category="MOVIE", language_checked=True, subtitle_languages=["nor"], unattended=True)

    assert asyncio.run(_tracker().get_additional_checks(meta)) is True  # noqa: S101


def test_nordicquality_rejects_nordic_audio_without_nordic_subtitles():
    meta = Meta(category="MOVIE", language_checked=True, audio_languages=["Norwegian"], subtitle_languages=["English"], unattended=True)

    assert asyncio.run(_tracker().get_additional_checks(meta)) is False  # noqa: S101


def test_nordicquality_rejects_movie_without_nordic_subtitles():
    meta = Meta(category="MOVIE", language_checked=True, subtitle_languages=["English"], unattended=True)

    assert asyncio.run(_tracker().get_additional_checks(meta)) is False  # noqa: S101


def test_nordicquality_allows_attended_confirmation_after_missing_subtitles():
    meta = Meta(category="MOVIE", language_checked=True, subtitle_languages=["English"])
    tracker = _tracker()
    tracker.common.prompt_user_for_confirmation = AsyncMock(return_value=True)

    assert asyncio.run(tracker.get_additional_checks(meta)) is True  # noqa: S101
    tracker.common.prompt_user_for_confirmation.assert_awaited_once()


def test_nordicquality_sanitizes_upload_name():
    meta = Meta(uuid="\u00c6r\u00f8sk\u00f8bing \u00c5r 2025 HDR10+ DD+ DTS:X &.mkv")

    assert asyncio.run(_tracker().get_name(meta)) == {"name": "AEroskobing.Ar.2025.HDR10P.DDP.DTS-X.and"}  # noqa: S101


def test_nordicquality_removes_parentheses_around_release_year():
    meta = Meta(
        category="MOVIE",
        filelist=["D:/Movies/Congo (1995) 1080p UHD BluRay OPUS 5.1 SDR AV1-WhiskeyJack.mkv"],
    )
    assert asyncio.run(_tracker().get_name(meta)) == {  # noqa: S101
        "name": "Congo.1995.1080p.UHD.BluRay.OPUS.5.1.SDR.AV1-WhiskeyJack"
    }


def test_nordicquality_preserves_release_suffix_in_extensionless_uuid():
    meta = Meta(category="MOVIE", uuid="Snatched.2017.UHD.BluRay.2160p.DTS-HD.MA.7.1.HEVC.REMUX-FraMeSToR")

    assert asyncio.run(_tracker().get_name(meta)) == {  # noqa: S101
        "name": "Snatched.2017.UHD.BluRay.2160p.DTS-HD.MA.7.1.HEVC.REMUX-FraMeSToR"
    }


def test_nordicquality_prefers_single_media_filename_over_folder_uuid():
    meta = Meta(
        category="MOVIE",
        uuid="Snatched.2017.UHD.BluRay.2160p.DTS-HD.MA.7.1.HEVC",
        filelist=["D:/Movies/Snatched/Snatched.2017.UHD.BluRay.2160p.DTS-HD.MA.7.1.HEVC.REMUX-FraMeSToR.mkv"],
    )

    assert asyncio.run(_tracker().get_name(meta)) == {  # noqa: S101
        "name": "Snatched.2017.UHD.BluRay.2160p.DTS-HD.MA.7.1.HEVC.REMUX-FraMeSToR"
    }


def test_nordicquality_strips_only_known_media_extensions():
    meta = Meta(category="MOVIE", uuid="unused-folder-name", filelist=["D:/Movies/Movie.2025.1080p.BluRay.REMUX-GROUP.MKV"])

    assert asyncio.run(_tracker().get_name(meta)) == {"name": "Movie.2025.1080p.BluRay.REMUX-GROUP"}  # noqa: S101


def test_nordicquality_falls_back_to_generated_name():
    meta = Meta(category="MOVIE", name="Movie 2025 1080p BluRay REMUX DTS-HD MA 7.1-GROUP")

    assert asyncio.run(_tracker().get_name(meta)) == {"name": "Movie.2025.1080p.BluRay.REMUX.DTS-HD.MA.7.1-GROUP"}  # noqa: S101
