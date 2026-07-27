from types import SimpleNamespace

from src.trackers.AVISTAZ.avistaz import AvistaZ


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
        "audio": "AAC",
        "untouched": False,
        "mediainfo": {"media": {"track": [{"@type": "Audio", "Format": "AAC", "BitRate": "128000"}]}},
        "origin_country": ["JP"],
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_hdtv_mpeg2_transport_stream_is_allowed():
    meta = make_meta(type="HDTV", container="ts", video_codec="MPEG-2")

    warnings = AvistaZ({"TRACKERS": {"AVISTAZ": {}}}).rules(meta)

    assert warnings == ""  # noqa: S101


def test_eac3_audio_is_allowed():
    meta = make_meta(mediainfo={"media": {"track": [{"@type": "Audio", "Format": "E-AC-3", "BitRate": "768000"}]}})

    warnings = AvistaZ({"TRACKERS": {"AVISTAZ": {}}}).rules(meta)

    assert warnings == ""  # noqa: S101


def test_low_audio_bitrate_is_reported_for_non_webdl():
    meta = make_meta(type="HDTV", mediainfo={"media": {"track": [{"@type": "Audio", "Format": "AAC", "BitRate": "96 kb/s"}]}})

    warnings = AvistaZ({"TRACKERS": {"AVISTAZ": {}}}).rules(meta)

    assert "128 kbit/s" in warnings  # noqa: S101


def test_grouped_and_megabit_audio_bitrates_are_normalized():
    for bitrate in ("1 024 kb/s", "1.5 Mb/s"):
        meta = make_meta(type="HDTV", mediainfo={"media": {"track": [{"@type": "Audio", "Format": "AAC", "BitRate": bitrate}]}})

        warnings = AvistaZ({"TRACKERS": {"AVISTAZ": {}}}).rules(meta)

        assert warnings == ""  # noqa: S101
