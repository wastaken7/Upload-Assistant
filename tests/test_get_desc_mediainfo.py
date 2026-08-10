# ruff: noqa: S101
from src.get_desc import DescriptionBuilder


def test_format_short_mediainfo_json() -> None:
    report = {
        "media": {
            "track": [
                {"@type": "General", "Format": "Matroska", "FileSize": "1073741824", "Duration": "5400.123"},
                {"@type": "Video", "Format": "AVC", "Width": "1920", "Height": "1080", "BitRate": "8000000", "FrameRate": "23.976"},
                {"@type": "Audio", "Format_Commercial_IfAny": "Dolby Digital", "Channels": "6", "SamplingRate": "48000", "BitRate": "640000", "Language": "pt-BR"},
                {"@type": "Text", "Format": "UTF-8", "Title": "Forced", "Language": "en"},
            ]
        }
    }

    result = DescriptionBuilder.format_short_mediainfo_json(report, "Movie.mkv")

    assert "Movie" in result
    assert "Duration.......: 01:30:00.123" in result
    assert "Resolution.....: 1920x1080" in result
    assert "Format.........: Dolby Digital" in result
    assert "Language.......: Portuguese (BR)" in result
    assert "Language.......: English (Forced), UTF-8" in result
    assert DescriptionBuilder.format_short_mediainfo_json(None, "x.mkv") == ""
    assert DescriptionBuilder.format_short_mediainfo_json({}, "x.mkv") == ""
