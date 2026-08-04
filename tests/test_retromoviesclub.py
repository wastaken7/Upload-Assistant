import asyncio

from src.meta import Meta
from src.trackers.UNIT3D.retromoviesclub import RetroMoviesClub
from src.trackersetup import TrackerSetup, tracker_class_map


def _tracker() -> RetroMoviesClub:
    return RetroMoviesClub({"DEFAULT": {}, "TRACKERS": {"RETROMOVIESCLUB": {}}})


def test_retromoviesclub_is_registered_with_full_tracker_name():
    assert tracker_class_map["RETROMOVIESCLUB"] is RetroMoviesClub  # noqa: S101
    assert RetroMoviesClub.display_name == "RetroMoviesClub"  # noqa: S101


def test_retromoviesclub_filters_non_movie_categories():
    meta = Meta(category="TV", trackers=["RETROMOVIESCLUB"])
    setup = TrackerSetup({"TRACKERS": {"RETROMOVIESCLUB": {"api_key": "token"}}})

    setup.filter_unsupported_trackers(meta)

    assert meta.trackers == []  # noqa: S101
    assert meta.tracker_status["RETROMOVIESCLUB"] == {"upload": False, "skipped": True}  # noqa: S101


def test_retromoviesclub_accepts_movies_released_in_2000_or_earlier():
    assert asyncio.run(_tracker().get_additional_checks(Meta(category="MOVIE", year=2000))) is True  # noqa: S101
    assert asyncio.run(_tracker().get_additional_checks(Meta(category="MOVIE", year=2001))) is False  # noqa: S101


def test_retromoviesclub_uses_tracker_specific_type_ids():
    tracker = _tracker()

    assert asyncio.run(tracker.get_type_id(Meta(category="MOVIE", is_disc="BDMV"))) == {"type_id": "1"}  # noqa: S101
    assert asyncio.run(tracker.get_type_id(Meta(category="MOVIE", type="REMUX", source="BluRay"))) == {"type_id": "2"}  # noqa: S101
    assert asyncio.run(tracker.get_type_id(Meta(category="MOVIE", type="REMUX", source="PAL DVD"))) == {"type_id": "4"}  # noqa: S101
    assert asyncio.run(tracker.get_type_id(Meta(category="MOVIE", type="WEBDL"))) == {"type_id": "7"}  # noqa: S101


def test_retromoviesclub_sanitizes_upload_name_and_removes_aka():
    meta = Meta(name="Le Fabuleux Amélie [Amélie] (2001)!", aka="[Amélie]")

    assert asyncio.run(_tracker().get_name(meta)) == {"name": "Le Fabuleux Amlie 2001"}  # noqa: S101


def test_retromoviesclub_includes_mod_queue_flag():
    data = asyncio.run(RetroMoviesClub({"DEFAULT": {}, "TRACKERS": {"RETROMOVIESCLUB": {"modq": True}}}).get_additional_data(Meta()))

    assert data == {"mod_queue_opt_in": "1"}  # noqa: S101
