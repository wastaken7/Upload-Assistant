# ruff: noqa: S101
import asyncio

import pytest

from src.get_desc import DescriptionBuilder
from src.meta import Meta
from src.trackers.UNIT3D.onlyencodes import OnlyEncodes


def _name(meta: Meta) -> str:
    config = {"DEFAULT": {}, "TRACKERS": {"ONLYENCODES": {}}}
    return asyncio.run(OnlyEncodes(config).get_name(meta))["name"]


def _config() -> dict:
    return {
        "DEFAULT": {
            "add_logo": True,
            "multiScreens": 4,
            "thumbnail_size": 500,
            "pack_thumb_size": 500,
        },
        "TRACKERS": {"ONLYENCODES": {}},
    }


def _screens(count: int = 3) -> list[dict[str, str]]:
    return [
        {
            "web_url": f"https://onlyimage.org/view/{index}",
            "raw_url": f"https://onlyimage.org/image/{index}.png",
            "img_url": f"https://onlyimage.org/image/{index}.png",
        }
        for index in range(count)
    ]


@pytest.mark.parametrize("screens", [None, 0, 1, 2])
def test_onlyencodes_requires_three_screenshots(monkeypatch: pytest.MonkeyPatch, screens: int | None) -> None:
    tracker = OnlyEncodes(_config())
    monkeypatch.setattr(tracker.common, "check_and_confirm_adult_media_upload", lambda *_args: True)
    meta = Meta(screens=screens, is_disc="", audio_languages=["English"])

    assert asyncio.run(tracker.get_additional_checks(meta)) is False


def test_onlyencodes_accepts_three_screenshots(monkeypatch: pytest.MonkeyPatch) -> None:
    tracker = OnlyEncodes(_config())
    monkeypatch.setattr(tracker.common, "check_and_confirm_adult_media_upload", lambda *_args: True)

    async def language_check(*_args, **_kwargs) -> bool:
        return True

    monkeypatch.setattr(tracker.common, "check_language_requirements", language_check)
    meta = Meta(screens=3, is_disc="", audio_languages=["English"])

    assert asyncio.run(tracker.get_additional_checks(meta)) is True


def test_onlyencodes_description_uses_first_title_screens_and_linked_medium_format(monkeypatch: pytest.MonkeyPatch) -> None:
    config = _config()
    tracker = OnlyEncodes(config)
    captured: dict = {}

    async def description(builder: DescriptionBuilder, _meta: Meta, **kwargs) -> str:
        captured["tracker_config"] = dict(builder.tracker_config)
        captured["kwargs"] = kwargs
        return "description"

    monkeypatch.setattr(DescriptionBuilder, "general_description_generator", description)

    result = asyncio.run(tracker.get_description(Meta(category="TV", tv_pack=True, screens=3, image_list=_screens())))

    assert result == {"description": "description"}
    assert captured["tracker_config"] == {
        "add_logo": False,
        "multiScreens": 0,
        "thumbnail_size": 350,
        "pack_thumb_size": 350,
    }
    assert captured["kwargs"]["logo"] is False
    assert captured["kwargs"]["mediainfo"] is False
    assert captured["kwargs"]["nfo"] is False
    assert captured["kwargs"]["approved_image_hosts"] == list(tracker.approved_image_hosts)
    assert config["DEFAULT"] == {
        "add_logo": True,
        "multiScreens": 4,
        "thumbnail_size": 500,
        "pack_thumb_size": 500,
    }


def test_onlyencodes_disallows_banned_image_hosts() -> None:
    assert {"imgur", "postimg", "pixhost"}.isdisjoint(OnlyEncodes.approved_image_hosts)


@pytest.mark.parametrize("screenshots", [[], _screens(2), [{"web_url": "https://onlyimage.org/view/1"}]])
def test_onlyencodes_description_requires_three_hosted_linked_screenshots(screenshots: list[dict[str, str]]) -> None:
    tracker = OnlyEncodes(_config())

    with pytest.raises(ValueError, match="At least 3 hosted, linked screenshots"):
        asyncio.run(tracker.get_description(Meta(category="MOVIE", screens=3, image_list=screenshots)))


def test_onlyencodes_medium_screenshot_bbcode_links_to_full_image() -> None:
    builder = DescriptionBuilder("ONLYENCODES", _config())
    builder.tracker_config = {"thumbnail_size": 350}

    assert builder.format_screenshot("https://onlyimage.org/view/123", "https://onlyimage.org/image/123.png") == (
        "[url=https://onlyimage.org/view/123][img=350]https://onlyimage.org/image/123.png[/img][/url] "
    )


def test_onlyencodes_adds_resolution_before_ds4k() -> None:
    meta = Meta(
        category="MOVIE",
        type="WEBRIP",
        resolution="1080p",
        basename_no_ext="Movie.Title.2025.1080p.DS4K.WEBRip.DDP5.1.x265-RlsGrp",
        name="Movie Title 2025 1080p WEBRip DDP 5.1 x265-RlsGrp",
        tag="RlsGrp",
        audio_languages=["English"],
        language_checked=True,
    )

    assert _name(meta) == "Movie Title 2025 1080p DS4K WEBRip DDP 5.1 x265-RlsGrp"


def test_onlyencodes_adds_resolution_before_rm4k() -> None:
    meta = Meta(
        category="MOVIE",
        type="ENCODE",
        resolution="1080p",
        basename_no_ext="Movie.Title.2025.1080p.RM4K.BluRay.x264-RlsGrp",
        name="Movie Title 2025 1080p BluRay x264-RlsGrp",
        tag="RlsGrp",
        audio_languages=["English"],
        language_checked=True,
    )

    assert _name(meta) == "Movie Title 2025 1080p RM4K BluRay x264-RlsGrp"


def test_onlyencodes_fixes_ds4k_without_resolution() -> None:
    meta = Meta(
        category="MOVIE",
        type="WEBRIP",
        resolution="1080p",
        basename_no_ext="Movie.Title.2025.1080p.DS4K.WEBRip.DDP5.1.x265-RlsGrp",
        name="Movie Title 2025 DS4K WEBRip DDP 5.1 x265-RlsGrp",
        tag="RlsGrp",
        audio_languages=["English"],
        language_checked=True,
    )

    assert _name(meta) == "Movie Title 2025 1080p DS4K WEBRip DDP 5.1 x265-RlsGrp"


def test_onlyencodes_does_not_duplicate_existing_resolution_ds4k() -> None:
    meta = Meta(
        category="MOVIE",
        type="WEBRIP",
        resolution="1080p",
        basename_no_ext="Movie.Title.2025.1080p.DS4K.WEBRip.DDP5.1.x265-RlsGrp",
        name="Movie Title 2025 1080p DS4K WEBRip DDP 5.1 x265-RlsGrp",
        tag="RlsGrp",
        audio_languages=["English"],
        language_checked=True,
    )

    assert _name(meta) == "Movie Title 2025 1080p DS4K WEBRip DDP 5.1 x265-RlsGrp"


def test_onlyencodes_normal_name_without_scale_tag() -> None:
    meta = Meta(
        category="MOVIE",
        type="WEBRIP",
        resolution="1080p",
        basename_no_ext="Movie.Title.2025.1080p.WEBRip.DDP5.1.x265-RlsGrp",
        name="Movie Title 2025 1080p WEBRip DDP 5.1 x265-RlsGrp",
        tag="RlsGrp",
        audio_languages=["English"],
        language_checked=True,
    )

    assert _name(meta) == "Movie Title 2025 1080p WEBRip DDP 5.1 x265-RlsGrp"


def test_onlyencodes_foreign_language_with_ds4k() -> None:
    meta = Meta(
        category="MOVIE",
        type="WEBRIP",
        resolution="1080p",
        basename_no_ext="Movie.Title.2025.1080p.DS4K.WEBRip.DDP5.1.x265-RlsGrp",
        name="Movie Title 2025 1080p WEBRip DDP 5.1 x265-RlsGrp",
        tag="RlsGrp",
        audio_languages=["French"],
        language_checked=True,
    )

    assert _name(meta) == "Movie Title 2025 FRENCH 1080p DS4K WEBRip DDP 5.1 x265-RlsGrp"
