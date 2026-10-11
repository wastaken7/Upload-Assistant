# ruff: noqa: S101
import asyncio

import pytest

from src.get_desc import DescriptionBuilder
from src.meta import Meta


@pytest.mark.parametrize(
    ("tracker", "default_size", "tracker_size", "expected"),
    [
        ("TORRENTLEECH", None, "", '<center><img src="https://example.test/logo.png?a=1&amp;b=2" width="300"></center>'),
        ("TORRENTLEECH", "420", "", '<center><img src="https://example.test/logo.png?a=1&amp;b=2" width="420"></center>'),
        ("TORRENTLEECH", "300", "500", '<center><img src="https://example.test/logo.png?a=1&amp;b=2" width="500"></center>'),
        ("TEST", "300", "500", "[center][img=500]https://example.test/logo.png?a=1&b=2[/img][/center]"),
    ],
)
def test_logo_width_survives_description_generation(tracker, default_size, tracker_size, expected):
    defaults = {"add_logo": True}
    if default_size is not None:
        defaults["logo_size"] = default_size
    builder = DescriptionBuilder(tracker, {"DEFAULT": defaults, "TRACKERS": {tracker: {"logo_size": tracker_size}}})
    sections = dict.fromkeys(
        (
            "audio_spectrogram",
            "bluray",
            "book",
            "custom_header",
            "custom_signature",
            "description",
            "dynamic_hdr_plot",
            "game",
            "languages",
            "mediainfo",
            "menu_screenshots",
            "music",
            "nfo",
            "screenshots",
            "tonemapped_header",
            "tv_info",
            "ua_signature",
            "user_description",
        ),
        False,
    )
    result = asyncio.run(builder.general_description_generator(Meta(logo="https://example.test/logo.png?a=1&b=2"), **sections))
    assert result.strip() == expected


def test_torrentleech_uses_original_ua_screenshot_layout() -> None:
    config = {
        "DEFAULT": {"screens_per_row": 4, "thumbnail_size": 450},
        "TRACKERS": {"TORRENTLEECH": {"screens_per_row": 3, "thumbnail_size": 450}},
    }
    builder = DescriptionBuilder("TORRENTLEECH", config)

    assert asyncio.run(builder.get_screens_per_row()) == 2
    assert builder.format_screenshot("https://example.com/page", "https://example.com/raw.png", "https://example.com/thumb.png") == (
        '<a href="https://example.com/page"><img src="https://example.com/thumb.png" style="max-width: 350px;"></a>  '
    )

    parts: list[str] = []
    assert builder._append_screenshot_row_separator(parts, 0, 2) == ""
    assert parts == []
    assert builder._append_screenshot_row_separator(parts, 1, 2) == "<br><br>"
    assert parts == ["<br><br>"]


def test_other_trackers_keep_configured_screenshot_layout() -> None:
    config = {
        "DEFAULT": {"screens_per_row": 2, "thumbnail_size": 350},
        "TRACKERS": {"TEST": {"screens_per_row": 4, "thumbnail_size": 450}},
    }
    builder = DescriptionBuilder("TEST", config)

    assert asyncio.run(builder.get_screens_per_row()) == 4
    assert builder.format_screenshot("https://example.com/page", "https://example.com/raw.png", "https://example.com/thumb.png") == (
        "[url=https://example.com/page][img=450]https://example.com/raw.png[/img][/url] "
    )

    parts: list[str] = []
    assert builder._append_screenshot_row_separator(parts, 3, 4) == "\n"
    assert parts == ["\n"]
