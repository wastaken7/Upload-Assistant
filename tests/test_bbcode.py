# ruff: noqa: S101
from src.bbcode import BBCODE


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
