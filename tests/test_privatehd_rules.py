from types import SimpleNamespace

from src.trackers.AVISTAZ.privatehd import PrivateHD


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
        "bit_depth": "8",
        "video_bitrate": 5000,
        "mediainfo": {"media": {"track": [{"@type": "Video", "BitRate": "5000000"}, {"@type": "Audio", "Format": "AAC", "Language": "en"}]}},
        "original_language": "en",
        "origin_country": ["US"],
        "year": 2020,
        "tag": "GROUP",
        "sd": False,
        "name": "Example 2020 1080p WEB-DL H.264-GROUP",
        "bloated": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def tracker():
    return PrivateHD({"TRACKERS": {"PRIVATEHD": {}}})


def test_hdtv_transport_stream_is_allowed():
    meta = make_meta(type="HDTV", source="HDTV", container="ts")

    warnings = tracker().rules(meta)

    assert warnings == ""  # noqa: S101


def test_eac3_audio_is_allowed_when_format_commercial_name_is_missing():
    meta = make_meta(mediainfo={"media": {"track": [{"@type": "Video", "BitRate": "5000000"}, {"@type": "Audio", "Format": "E-AC-3", "Language": "en"}]}})

    warnings = tracker().rules(meta)

    assert warnings == ""  # noqa: S101


def test_crf_above_twenty_is_reported():
    meta = make_meta(
        type="ENCODE",
        source="BluRay",
        video_encode="x264",
        video_bitrate=6000,
        mediainfo={
            "media": {
                "track": [{"@type": "Video", "BitRate": "6000000", "Encoded_Library_Settings": "cabac=1 / crf=21.5"}, {"@type": "Audio", "Format": "AAC", "Language": "en"}]
            }
        },
    )

    warnings = tracker().rules(meta)

    assert "CRF 21.5 exceeds" in warnings  # noqa: S101
