# ruff: noqa: S101

import asyncio

import pytest

from src.get_desc import DescriptionBuilder
from src.meta import Meta

HEADER = "[center][b]Screenshots[/b][/center]"


def _image(name):
    return {"web_url": f"https://example.com/{name}", "raw_url": f"https://example.com/{name}.png"}


@pytest.fixture
def pack(tmp_path, monkeypatch):
    (tmp_path / "tmp" / "pack").mkdir(parents=True)
    builder = DescriptionBuilder(
        "TEST",
        {"DEFAULT": {"screenshot_header": HEADER, "multiScreens": 1, "processLimit": 1, "fileLimit": 1}, "TRACKERS": {"TEST": {}}},
    )
    meta = Meta(
        base_dir=str(tmp_path),
        uuid="pack",
        category="TV",
        tv_pack=True,
        filelist=["Show.S01E01.mkv", "Show.S01E02.mkv"],
        screens=1,
        image_list=[_image("first")],
        new_images_file_1=[_image("second")],
        description="Release description",
    )
    # Keep real MediaInfo formatting, but avoid running the external binary.
    monkeypatch.setattr("src.get_desc.MediaInfo.parse", lambda *_args, **_kwargs: "General\nDuration : 42 min\n")
    return builder, meta


def _render(builder, meta):
    return asyncio.run(
        builder.general_description_generator(
            meta,
            audio_spectrogram=False,
            bluray=False,
            book=False,
            custom_header=False,
            custom_signature=False,
            game=False,
            languages=False,
            logo=False,
            mediainfo=False,
            menu_screenshots=False,
            nfo=False,
            tonemapped_header=False,
            tv_info=False,
            ua_signature=False,
            user_description=False,
            music=False,
            dynamic_hdr_plot=False,
        )
    )


def test_first_file_has_filename_and_one_screenshot_header(pack):
    result = _render(*pack)

    assert result.count("Show.S01E01") == 1
    assert result.count(HEADER) == 1
    assert result.count(_image("first")["raw_url"]) == 1
    assert "Show.S01E02" not in result


def test_later_file_keeps_mediainfo_screenshots_and_spoilers(pack):
    builder, meta = pack
    builder.config["DEFAULT"]["processLimit"] = 2

    result = _render(builder, meta)

    assert "[spoiler=Other files]" in result
    assert "[spoiler=Show.S01E02]" in result
    assert "[b]Duration:[/b] 42 min" in result
    assert _image("second")["raw_url"] in result


def test_zero_multi_screens_keeps_only_main_screenshots(pack):
    builder, meta = pack
    builder.config["DEFAULT"].update(multiScreens=0, processLimit=2)

    result = _render(builder, meta)

    assert _image("first")["raw_url"] in result
    assert _image("second")["raw_url"] not in result
    assert "Show.S01E" not in result
    assert "42 min" not in result


def test_tracker_override_replaces_main_screenshots_and_keeps_pack_layout(pack):
    builder, meta = pack
    builder.config["DEFAULT"]["processLimit"] = 2
    meta.tracker_image_collections = {"TEST": {"screenshots": [_image("override")]}}

    result = _render(builder, meta)

    assert _image("override")["raw_url"] in result
    assert _image("first")["raw_url"] not in result
    assert "Show.S01E01" in result
    assert "[spoiler=Show.S01E02]" in result
    assert _image("second")["raw_url"] in result
