# ruff: noqa: S101

import asyncio

import pytest

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


def _render(tmp_path, *, hide_header: bool, description: str = "", settings=None, sections=None, metadata=None) -> str:
    async def run() -> str:
        (tmp_path / "tmp" / "release").mkdir(parents=True, exist_ok=True)
        config = {
            "DEFAULT": {
                "screenshot_header": HEADER,
                "hide_screenshot_header_if_only_section": hide_header,
                **(settings or {}),
            },
            "TRACKERS": {"TEST": {}},
        }
        meta_values = {
            "base_dir": str(tmp_path),
            "uuid": "release",
            "category": "MOVIE",
            "filelist": ["Fictional.Movie.mkv"],
            "image_list": [IMAGE],
            "screens": 1,
            "description": description,
            "ua_signature": SIGNATURE,
        }
        meta_values.update(metadata or {})
        meta = Meta(**meta_values)
        return await DescriptionBuilder("TEST", config).general_description_generator(
            meta,
            description=bool(description),
            **(DISABLED_SECTIONS | (sections or {})),
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


def test_true_hides_header_when_text_is_also_present(tmp_path):
    result = _render(tmp_path, hide_header=True, description="Release notes")

    assert HEADER not in result
    assert "Release notes" in result


def test_logo_and_signatures_do_not_keep_lone_header(tmp_path):
    result = _render(
        tmp_path,
        hide_header=True,
        settings={"add_logo": True, "custom_signature": "[img]https://example.test/signature.png[/img]"},
        sections={"logo": True, "custom_signature": True},
        metadata={"logo": "https://example.test/logo.png"},
    )

    assert HEADER not in result
    assert "https://example.test/logo.png" in result
    assert "https://example.test/signature.png" in result
    assert IMAGE["raw_url"] in result
    assert SIGNATURE in result


@pytest.mark.parametrize(
    ("section", "header_key", "metadata"),
    [
        ("menu_screenshots", "disc_menu_header", {"is_disc": "DVD", "menu_images": [IMAGE]}),
        ("audio_spectrogram", "audio_spectrogram_header", {"audio_spectrogram": True, "spectrograms_images": [IMAGE]}),
        ("dynamic_hdr_plot", "dynamic_hdr_plot_header", {"dynamic_hdr_plot": True, "dynamic_hdr_plot_images": [IMAGE]}),
    ],
)
@pytest.mark.parametrize("hide_header", [True, False])
def test_optional_image_section_lone_header(tmp_path, section, header_key, metadata, hide_header):
    other_header = "[h2]Other images[/h2]"
    result = _render(
        tmp_path,
        hide_header=hide_header,
        settings={header_key: other_header},
        sections={section: True, "screenshots": False},
        metadata=metadata,
    )

    assert (other_header in result) is not hide_header
    assert IMAGE["raw_url"] in result


@pytest.mark.parametrize("other_header", ["[h2]Spectrograms[/h2]", ""])
def test_counts_rendered_headers_rather_than_enabled_sections(tmp_path, other_header):
    result = _render(
        tmp_path,
        hide_header=True,
        settings={"audio_spectrogram_header": other_header},
        sections={"audio_spectrogram": True},
        metadata={"audio_spectrogram": True, "spectrograms_images": [IMAGE]},
    )

    assert (HEADER in result) is bool(other_header)
    if other_header:
        assert other_header in result


def test_empty_image_section_does_not_count_and_tonemapping_notice_is_preserved(tmp_path):
    notice = "Images adapted for SDR viewing."
    result = _render(
        tmp_path,
        hide_header=True,
        settings={"tonemapped_header": notice},
        sections={"audio_spectrogram": True, "tonemapped_header": True},
        metadata={"audio_spectrogram": True, "tonemapped": True},
    )

    assert HEADER not in result
    assert notice in result
