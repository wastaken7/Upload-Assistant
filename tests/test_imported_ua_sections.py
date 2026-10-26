# ruff: noqa: S101

import asyncio

from src.bbcode import BBCODE
from src.get_desc import DescriptionBuilder
from src.meta import Meta

CUSTOM_HEADER = "[center]Fictional Group Presents[/center]"
SIGNATURE = "[center]Thanks for seeding, from Fictional Group[/center]"


def _shot(name):
    return f"[url=https://img.example/{name}][img=350]https://img.example/{name}.png[/img][/url] "


def _builder(**default):
    config = {
        "screenshot_header": "[h2]Screenshots[/h2]",
        "disc_menu_header": "[h2]Disc Menu Screenshots[/h2]",
        "audio_spectrogram_header": "[h2]Audio Spectrogram[/h2]",
        "dynamic_hdr_plot_header": "[h2]Dynamic HDR Metadata[/h2]",
        "custom_description_header": CUSTOM_HEADER,
        "custom_signature": SIGNATURE,
        **default,
    }
    return DescriptionBuilder("TEST", {"DEFAULT": config, "TRACKERS": {"TEST": {}}})


def _render(meta, builder=None, **sections):
    """Render through the real generator with only the description, header and signature on."""
    builder = builder or _builder()
    off = {
        "audio_spectrogram": False,
        "bluray": False,
        "book": False,
        "game": False,
        "languages": False,
        "logo": False,
        "mediainfo": False,
        "menu_screenshots": False,
        "nfo": False,
        "screenshots": False,
        "tv_info": False,
        "ua_signature": False,
        "user_description": False,
        "music": False,
        "dynamic_hdr_plot": False,
    }
    off.update(sections)
    return asyncio.run(builder.general_description_generator(meta, **off))


# --- image-section headers ---------------------------------------------------


def test_headers_left_without_images_are_removed():
    text = "Release notes.\n[h2]Disc Menu Screenshots[/h2]\n\n[h2]Screenshots[/h2]\n\n[h2]Audio Spectrogram[/h2]\n\n[h2]Dynamic HDR Metadata[/h2]\n"

    assert _builder()._strip_orphan_section_headers(text, Meta()) == "Release notes."


def test_code_default_headers_are_recognised():
    text = "Notes.\n[center][b]Audio Spectrogram[/b][/center]\n[center][b]Dynamic HDR Metadata[/b][/center]"

    assert _builder()._strip_orphan_section_headers(text, Meta()) == "Notes."


def test_a_header_still_followed_by_images_is_kept():
    text = f"[h2]Screenshots[/h2]\n[center]{_shot('a')}[/center]"

    assert _builder()._strip_orphan_section_headers(text, Meta()) == text


def test_a_header_followed_by_a_spoiler_with_images_is_kept():
    text = f"[h2]Screenshots[/h2]\n[spoiler=Episode 1][center]{_shot('a')}[/center][/spoiler]"

    assert _builder()._strip_orphan_section_headers(text, Meta()) == text


def test_only_the_orphan_header_is_removed_from_mixed_sections():
    text = f"[h2]Disc Menu Screenshots[/h2]\n\n[h2]Screenshots[/h2]\n[center]{_shot('a')}[/center]"

    assert _builder()._strip_orphan_section_headers(text, Meta()) == f"[h2]Screenshots[/h2]\n[center]{_shot('a')}[/center]"


def test_plain_prose_is_not_a_header():
    text = "Screenshots\nAudio Spectrogram looks clean."

    assert _builder()._strip_orphan_section_headers(text, Meta()) == text


def test_tag_override_headers_are_recognised():
    builder = _builder(tag_overrides={"FICTGRP": {"screenshot_header": "[b]FICTGRP Shots[/b]"}})

    assert builder._strip_orphan_section_headers("Body.\n[b]FICTGRP Shots[/b]", Meta(tag="-FICTGRP")) == "Body."


def test_untouched_text_keeps_its_spacing():
    text = "Line one.\n\n\n\nLine two.\n"

    assert _builder()._strip_orphan_section_headers(text, Meta()) == text


# --- sections rendered again ---------------------------------------------------


def test_regenerated_language_and_episode_blocks_are_removed():
    parts = ["[code]Audio Languages: English[/code]\n", "[center]S01E01 - Fictional Pilot[/center]\n", "[center]A fictional overview.[/center]\n"]
    text = "[code]Audio Languages: English[/code]\n\n[center]S01E01 - Fictional Pilot[/center]\n\n[center]A fictional overview.[/center]\n\nUploader notes."

    assert _builder()._strip_regenerated_parts(text, parts) == "Uploader notes."


def test_different_imported_blocks_are_kept():
    text = "[code]Audio Languages: German[/code]\nUploader notes."

    assert _builder()._strip_regenerated_parts(text, ["[code]Audio Languages: English[/code]\n"]) == text


def test_custom_header_and_signature_are_not_rendered_twice():
    meta = Meta(description=f"{CUSTOM_HEADER}\n\nUploader notes.\n\n{SIGNATURE}")

    rendered = _render(meta)

    assert rendered.count(CUSTOM_HEADER) == 1
    assert rendered.count(SIGNATURE) == 1
    assert "Uploader notes." in rendered


def test_imported_custom_header_survives_when_the_section_is_disabled():
    meta = Meta(description=f"{CUSTOM_HEADER}\n\nUploader notes.")

    assert _render(meta, custom_header=False, custom_signature=False).count(CUSTOM_HEADER) == 1


def test_imported_ua_upload_is_cleaned_end_to_end():
    imported = "\n".join(
        [
            CUSTOM_HEADER,
            "Uploader notes.",
            f"[h2]Screenshots[/h2]\n[center]{_shot('s1')}{_shot('s2')}[/center]",
            f"[h2]Audio Spectrogram[/h2]\n[center]{_shot('a1')}[/center]",
            SIGNATURE,
        ]
    )
    cleaned, _images = BBCODE().clean_unit3d_description(imported, "https://unit3d.example/torrents/1")

    rendered = _render(Meta(description=cleaned))

    assert rendered == f"{CUSTOM_HEADER}\n\nUploader notes.\n{SIGNATURE}"


# --- extracted images ----------------------------------------------------------


def test_tmdb_artwork_is_not_extracted_as_a_screenshot():
    desc = f"Notes.\n[center][img=300]https://image.tmdb.org/t/p/original/fictional-logo.png[/img][/center]\n[center]{_shot('s1')}[/center]"

    _cleaned, images = BBCODE().clean_unit3d_description(desc, "https://unit3d.example/torrents/1")

    assert [image["img_url"] for image in images] == ["https://img.example/s1.png"]


def test_plain_text_header_and_signature_are_not_rendered_twice():
    builder = _builder(custom_description_header="Fictional Group presents", custom_signature="Thanks for seeding!")
    meta = Meta(description="Fictional Group presents\nUploader notes, thanks for seeding!\n\nThanks for seeding!")

    rendered = _render(meta, builder)

    assert rendered.count("Fictional Group presents") == 1
    assert rendered.count("Thanks for seeding!") == 1
    assert "Uploader notes, thanks for seeding!" in rendered


def test_plain_text_signature_inside_prose_is_kept():
    text = "Thanks for seeding! is what we always say."

    assert DescriptionBuilder._strip_plain_text_edges(text, "", "Thanks for seeding!") == text
