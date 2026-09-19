# ruff: noqa: S101

import asyncio

from src.get_desc import DescriptionBuilder
from src.meta import Meta

HEADER = "[h2]Screenshots[/h2]"
SIGNATURE = "Shared with Upload-Assistant 1.2.3 (fork)"
IMAGE = {
    "web_url": "https://example.test/page",
    "raw_url": "https://example.test/image.jpg",
}

DISABLED_SECTIONS = {
    "audio_spectrogram": False,
    "bluray": False,
    "book": False,
    "custom_header": False,
    "custom_signature": False,
    "dynamic_hdr_plot": False,
    "game": False,
    "languages": False,
    "logo": False,
    "mediainfo": False,
    "menu_screenshots": False,
    "music": False,
    "nfo": False,
    "tonemapped_header": False,
    "tv_info": False,
    "user_description": False,
}


def _render(tmp_path, *, hide_header: bool, description: str = "") -> str:
    async def run() -> str:
        (tmp_path / "tmp" / "release").mkdir(parents=True, exist_ok=True)
        config = {
            "DEFAULT": {
                "screenshot_header": HEADER,
                "hide_screenshot_header_if_only_section": hide_header,
            },
            "TRACKERS": {"TEST": {}},
        }
        meta = Meta(
            base_dir=str(tmp_path),
            uuid="release",
            category="MOVIE",
            filelist=["movie.mkv"],
            image_list=[IMAGE],
            screens=1,
            description=description,
            ua_signature=SIGNATURE,
        )
        return await DescriptionBuilder("TEST", config).general_description_generator(
            meta,
            description=bool(description),
            **DISABLED_SECTIONS,
        )

    return asyncio.run(run())


def test_true_hides_header_when_screenshots_are_the_only_content_section(tmp_path):
    result = _render(tmp_path, hide_header=True)

    assert HEADER not in result
    assert IMAGE["raw_url"] in result
    assert SIGNATURE in result


def test_false_keeps_header_when_screenshots_are_the_only_content_section(tmp_path):
    result = _render(tmp_path, hide_header=False)

    assert HEADER in result


def test_true_keeps_header_when_another_content_section_exists(tmp_path):
    result = _render(tmp_path, hide_header=True, description="Release notes")

    assert HEADER in result
    assert "Release notes" in result
