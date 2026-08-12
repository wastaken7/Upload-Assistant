# ruff: noqa: S101
import asyncio

from src.get_desc import DescriptionBuilder


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
