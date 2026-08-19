import asyncio
from types import SimpleNamespace

from src.trackers.makingoff import MakingOff


def make_meta(**overrides):
    values = {
        "category": "MOVIE",
        "adult_media": False,
        "tmdb_adult_media": False,
        "is_disc": "",
        "container": "MKV",
        "video_codec": "H.264",
        "video_encode": "x264",
        "video_width": 1920,
        "video_height": 1080,
        "video_bitrate": 6000,
        "resolution": "1080p",
        "name": "Example.Movie.2020.WEB-DL",
        "basename_no_ext": "Example Movie 2020 WEB-DL",
        "source": "WEB",
        "type": "WEBDL",
        "filelist": ["Example.Movie.2020.mkv"],
        "image_list": ["https://images.example/screen-1.png"],
        "menu_images": [],
        "spectrograms_images": [],
        "subtitle_languages": ["Portuguese"],
        "subtitle_files": [],
        "mediainfo": {"media": {"track": []}},
        "hardcoded_subs": False,
        "original_language": "en",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def tracker():
    return MakingOff({"TRACKERS": {"MAKINGOFF": {}}})


def test_accepts_a_compliant_hd_movie():
    assert asyncio.run(tracker().get_additional_checks(make_meta()))  # noqa: S101


def test_accepts_sd_non_h264_codec():
    meta = make_meta(video_codec="XviD", video_encode="XviD", resolution="480p", video_width=640, video_height=480, video_bitrate=1200)

    assert asyncio.run(tracker().get_additional_checks(meta))  # noqa: S101


def test_rejects_hevc_and_blu_ray_structures():
    assert not asyncio.run(tracker().get_additional_checks(make_meta(video_codec="HEVC", video_encode="x265")))  # noqa: S101
    assert not asyncio.run(tracker().get_additional_checks(make_meta(is_disc="BDMV")))  # noqa: S101


def test_rejects_missing_subtitles():
    assert not asyncio.run(tracker().get_additional_checks(make_meta(subtitle_languages=[])))  # noqa: S101


def test_accepts_portuguese_original_language_without_subtitles():
    assert asyncio.run(tracker().get_additional_checks(make_meta(subtitle_languages=[], original_language="pt")))  # noqa: S101


def test_accepts_hardcoded_subtitles_without_a_language_tag():
    assert asyncio.run(tracker().get_additional_checks(make_meta(subtitle_languages=[], hardcoded_subs=True)))  # noqa: S101


def test_rejects_prohibited_release_markers_and_archives():
    assert not asyncio.run(tracker().get_additional_checks(make_meta(name="Example.Movie.2020.CAM")))  # noqa: S101
    assert not asyncio.run(tracker().get_additional_checks(make_meta(filelist=["Example.Movie.mkv", "payload.exe"])))  # noqa: S101
