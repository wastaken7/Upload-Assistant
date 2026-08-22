import asyncio

from src.meta import Meta
from src.trackers.UNIT3D.rockethd import RocketHD
from src.trackersetup import tracker_class_map


def _tracker() -> RocketHD:
    return RocketHD({"TRACKERS": {"ROCKETHD": {"use_german_title": True}}})


def test_rockethd_is_registered_with_full_tracker_name():
    assert tracker_class_map["ROCKETHD"] is RocketHD  # noqa: S101
    assert RocketHD.display_name == "RocketHD"  # noqa: S101


def test_rockethd_uses_release_directory_for_markers_and_group():
    tracker = _tracker()
    meta = Meta(
        isdir=True,
        path="/releases/Movie.2024.1080p.VU1080",
        filelist=["/releases/Movie.2024.1080p.VU1080/video.mkv"],
    )
    assert tracker.get_basename(meta) == "Movie.2024.1080p.VU1080"  # noqa: S101
    assert tracker._extract_clean_release_group(meta) == "VU1080"  # noqa: S101


def test_rockethd_get_name_handles_german_title_and_audio():
    tracker = _tracker()
    meta = Meta(
        title="Original Title",
        year=2024,
        resolution="1080p",
        source="WEB-DL",
        type="WEBDL",
        audio="DD+ 5.1",
        audio_languages=["German", "English"],
        language_checked=True,
        imdb_info={"akas": [{"country": "Germany", "title": "Deutscher Titel"}]},
        mediainfo={"media": {"track": [{"@type": "Audio", "Language": "German"}]}},
    )
    name = asyncio.run(tracker.get_name(meta))["name"]
    assert name.startswith("Deutscher Titel 2024")  # noqa: S101
    assert "GERMAN DL" in name  # noqa: S101


def test_rockethd_rejects_unattended_prohibited_release():
    tracker = _tracker()
    meta = Meta(
        path="/releases/Movie.2024.CAM-GRP/movie.mkv",
        filelist=["/releases/Movie.2024.CAM-GRP/movie.mkv"],
        unattended=True,
        requested_release=True,
    )
    assert not asyncio.run(tracker.get_additional_checks(meta))  # noqa: S101
