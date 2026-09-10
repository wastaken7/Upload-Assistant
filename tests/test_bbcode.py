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


def test_tracker_specific_formats_only_clamps_gazelle_descriptions() -> None:
    builder = object.__new__(DescriptionBuilder)

    assert builder.tracker_specific_formats("ANTHELION", "[size=16]Text[/size]") == "[size=10]Text[/size]"
    assert builder.tracker_specific_formats("HDTORRENTS", "[size=16]Text[/size]") == "[size=16]Text[/size]"


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
        "PTZONE",
        "RAILGUNPT",
        "XINGYUNGEPT",
    ):
        assert builder.tracker_specific_formats(tracker, description) == "[img]https://example.test/image.jpg[/img]"


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
