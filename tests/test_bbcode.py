# ruff: noqa: S101
from src.bbcode import BBCODE
from src.get_desc import DescriptionBuilder


def test_clamp_size_tags_preserves_supported_sizes_and_other_markup() -> None:
    description = "[b][size=1]Small[/size] [SIZE=10]Large[/SIZE][/b]"

    assert BBCODE().clamp_size_tags(description) == description


def test_clamp_size_tags_clamps_oversized_nested_tags() -> None:
    description = "[size=11]Large [SIZE=24]Larger[/SIZE][/size]"

    assert BBCODE().clamp_size_tags(description) == "[size=10]Large [size=10]Larger[/SIZE][/size]"


def test_clamp_size_tags_preserves_malformed_or_non_integer_values() -> None:
    description = "[size=large]Text[/size] [size=11.5]Text[/size] [size= 12]Text[/size]"

    assert BBCODE().clamp_size_tags(description) == description


def test_convert_named_colors_to_hex() -> None:
    description = "[color=SkyBlue]Text[/color] [color=red]Red[/color]"

    assert BBCODE().convert_named_colors(description) == "[color=#87ceeb]Text[/color] [color=#ff0000]Red[/color]"


def test_convert_named_colors_preserves_hex_and_unknown_values() -> None:
    description = "[color=#123456]Hex[/color] [color=not-a-color]Unknown[/color]"

    assert BBCODE().convert_named_colors(description) == description


def test_convert_hex_colors_to_named() -> None:
    description = "[color=#87CEEB]Text[/color] [color=#f00]Red[/color]"

    assert BBCODE().convert_hex_colors_to_named(description) == "[color=skyblue]Text[/color] [color=red]Red[/color]"


def test_convert_hex_colors_to_named_preserves_unknown_values() -> None:
    description = "[color=#123456]Unknown[/color] [color=skyblue]Named[/color]"

    assert BBCODE().convert_hex_colors_to_named(description) == description


def test_tracker_specific_formats_only_clamps_gazelle_descriptions() -> None:
    builder = object.__new__(DescriptionBuilder)

    assert builder.tracker_specific_formats("ANTHELION", "[size=16]Text[/size]") == "[size=10]Text[/size]"
    assert builder.tracker_specific_formats("HDTORRENTS", "[size=16]Text[/size]") == "[size=16]Text[/size]"


def test_tracker_specific_formats_converts_colors_for_gazelle_trackers() -> None:
    builder = object.__new__(DescriptionBuilder)
    description = "[color=skyblue]Text[/color]"

    for tracker in ("ANTHELION", "BJSHARE", "BRASILTRACKER", "GREATPOSTERWALL"):
        assert builder.tracker_specific_formats(tracker, description) == "[color=#87ceeb]Text[/color]"

    assert builder.tracker_specific_formats("HDTORRENTS", description) == description


def test_tracker_specific_formats_converts_colors_for_hdspace() -> None:
    builder = object.__new__(DescriptionBuilder)
    description = "[color=#87ceeb]Text[/color]"

    assert builder.tracker_specific_formats("HDSPACE", description) == "[color=skyblue]Text[/color]"


def test_tracker_specific_formats_removes_image_resize_for_nexusphp_trackers() -> None:
    builder = object.__new__(DescriptionBuilder)
    description = "[img=450]https://example.test/image.jpg[/img]"

    for tracker in (
        "1PTBA",
        "LAJIDUI",
        "LEMONHD",
        "LONGPT",
        "PTCAFE",
        "PTFANS",
        "PTGTK",
        "PTSKIT",
        "PTZONE",
        "RAILGUNPT",
        "XINGYUNGEPT",
    ):
        assert builder.tracker_specific_formats(tracker, description) == "[img]https://example.test/image.jpg[/img]"


def test_tracker_specific_formats_cleans_ptskit_descriptions() -> None:
    builder = object.__new__(DescriptionBuilder)
    description = """[hide]Details[/hide]
[img=450]https://example.test/image.jpg[/img]
[comparison=Source A, Source B]
https://example.test/a.jpg
https://example.test/b.jpg
[/comparison]"""

    formatted = builder.tracker_specific_formats("PTSKIT", description)

    assert "[hide]" not in formatted
    assert "[img=450]" not in formatted
    assert "[img]https://example.test/image.jpg[/img]" in formatted
    assert "[comparison=" not in formatted
    assert "[center]Source A | Source B" in formatted


def test_clean_unit3d_description_removes_line_wrapped_align_center_signature() -> None:
    description = """Release notes
[align=center]
[url=https://github.com/wastaken7/Upload-Assistant]
[size=4]
Shared with Upload-Assistant v3.3 (fork)
[/size]
[/url]
[/align]"""

    cleaned, _ = BBCODE().clean_unit3d_description(description, "https://example.test")

    assert cleaned == "Release notes"


def test_clean_unit3d_description_preserves_non_version_suffix() -> None:
    description = "[right][url=https://github.com/wastaken7/Upload-Assistant]Shared with Upload Assistant release[/url][/right]"

    cleaned, _ = BBCODE().clean_unit3d_description(description, "https://example.test")

    assert cleaned == description
