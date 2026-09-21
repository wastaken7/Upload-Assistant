# ruff: noqa: S101
from web_ui.server import _extract_preview_media_tracks


def test_extract_preview_media_tracks_from_mediainfo_media_track() -> None:
    meta = {
        "mediainfo": {
            "media": {
                "track": [
                    {"@type": "General", "Format": "Matroska"},
                    {
                        "@type": "Audio",
                        "Language_String": "English",
                        "Title": "English Dolby TrueHD Atmos",
                        "Format": "MLP FBA",
                        "Format_Commercial_IfAny": "Dolby TrueHD with Dolby Atmos",
                        "ChannelLayout": "L R C LFE Ls Rs Lb Rb",
                        "BitRate": "4281000",
                        "Default": "Yes",
                    },
                    {
                        "@type": "Audio",
                        "Language": "Japanese",
                        "Title": "Japanese Stereo",
                        "Format": "FLAC",
                        "Channels": "2",
                        "BitRate_String": "1 438 kb/s",
                    },
                    {
                        "@type": "Text",
                        "Language_String": "English",
                        "Title": "English Forced",
                        "Format": "PGS",
                        "Forced": "Yes",
                    },
                    {
                        "@type": "Text",
                        "Language_String": "English",
                        "Title": "English SDH",
                        "Format": "PGS",
                        "HearingImpaired": "Yes",
                    },
                ]
            }
        }
    }

    audio, subtitles = _extract_preview_media_tracks(meta)

    assert len(audio) == 2
    assert audio[0]["index"] == 1
    assert audio[0]["language"] == "English"
    assert audio[0]["title"] == "English Dolby TrueHD Atmos"
    assert audio[0]["format"] == "Dolby TrueHD with Dolby Atmos"
    assert audio[0]["bitrate"] == "4281 kbps"
    assert audio[0]["default"] is True
    assert audio[1]["language"] == "Japanese"
    assert audio[1]["bitrate"] == "1 438 kb/s"

    assert len(subtitles) == 2
    assert subtitles[0]["forced"] is True
    assert subtitles[1]["hearing_impaired"] is True


def test_extract_preview_media_tracks_supports_alternate_track_layout_and_flags() -> None:
    meta = {
        "mediainfo": {
            "tracks": [
                {
                    "TrackType": "Audio",
                    "language": "English",
                    "title": "Director Commentary",
                    "codec": "AC-3",
                    "channels": "2",
                    "ServiceKind": "Commentary",
                },
                {
                    "type": "subtitle",
                    "language": "Spanish",
                    "format": "UTF-8",
                    "default": "true",
                },
            ]
        }
    }

    audio, subtitles = _extract_preview_media_tracks(meta)

    assert audio == [
        {
            "index": 1,
            "language": "English",
            "title": "Director Commentary",
            "format": "AC-3",
            "channels": "2",
            "bitrate": "",
            "default": False,
            "forced": False,
            "hearing_impaired": False,
            "commentary": True,
        }
    ]
    assert subtitles[0]["language"] == "Spanish"
    assert subtitles[0]["format"] == "UTF-8"
    assert subtitles[0]["default"] is True
