from types import SimpleNamespace

from src.trackers.AVISTAZ.cinemaz import CinemaZ


def make_meta(**overrides):
    values = {
        "category": "MOVIE",
        "anime": False,
        "is_disc": "",
        "video_codec": "H.264",
        "video_encode": "H.264",
        "type": "WEBDL",
        "source": "WEB",
        "container": "mkv",
        "resolution": "1080p",
        "video_width": 1920,
        "video_bitrate": 5000,
        "audio_bitrate": 192,
        "mediainfo": {"media": {"track": [{"@type": "Audio", "Format": "AAC", "BitRate": "192000"}]}},
        "origin_country": ["FR"],
        "year": 2020,
        "sd": False,
        "edition": "",
        "webdv": False,
        "debug": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def tracker():
    return CinemaZ({"TRACKERS": {"CINEMAZ": {}}})


def test_sd_content_from_major_english_country_is_allowed():
    meta = make_meta(origin_country=["US"], resolution="480p", video_width=640, video_bitrate=1200, sd=True)

    warnings = tracker().rules(meta)

    assert warnings == ""  # noqa: S101


def test_vp9_is_an_allowed_video_codec():
    meta = make_meta(video_codec="VP9", video_encode="VP9")

    warnings = tracker().rules(meta)

    assert warnings == ""  # noqa: S101


def test_low_video_bitrate_is_reported():
    meta = make_meta(video_bitrate=2999)

    warnings = tracker().rules(meta)

    assert "at least 3000 kbit/s" in warnings  # noqa: S101


def test_raw_remux_and_4k_uploads_require_six_screenshots():
    meta = make_meta(type="REMUX")
    cinema = tracker()
    cinema.upload_url_step2 = "https://cinemaz.to/upload"
    data = {"screenshots[]": ["a", "b", "c", "d", "e"], "task_id": "1", "info_hash": "hash", "rip_type_id": "2", "type_id": "1", "video_quality_id": "3"}

    issue = cinema.check_data(meta, data)

    assert issue == "UPLOAD FAILED: CinemaZ requires at least 6 screenshots for this upload."  # noqa: S101
