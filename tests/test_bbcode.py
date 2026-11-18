# ruff: noqa: S101
import asyncio

from src.bbcode import BBCODE
from src.get_desc import DescriptionBuilder
from src.trackers.NEXUSPHP import NEXUSPHP
from src.trackers.NEXUSPHP.ptskit import Ptskit
from src.trackersetup import get_tracker_framework


def test_tracker_framework_is_derived_from_registered_module_path() -> None:
    assert get_tracker_framework("ANTHELION") == "GAZELLE"
    assert get_tracker_framework("AITHER") == "UNIT3D"
    assert get_tracker_framework("LEMONHD") == "NEXUSPHP"
    assert get_tracker_framework("PTSKIT") == "NEXUSPHP"
    assert get_tracker_framework("UNKNOWN") is None


def test_ptskit_uses_the_nexusphp_base_initializer() -> None:
    tracker = Ptskit({"DEFAULT": {"tmdb_api": "test-key"}, "TRACKERS": {"PTSKIT": {"announce_url": "https://example.test/announce"}}})

    try:
        assert isinstance(tracker, NEXUSPHP)
        assert tracker.tracker == "PTSKIT"
        assert tracker.announce_url == "https://example.test/announce"
    finally:
        asyncio.run(tracker.session.aclose())


def test_clamp_size_tags_preserves_supported_sizes_and_other_markup() -> None:
    description = "[b][size=1]Small[/size] [SIZE=10]Large[/SIZE][/b]"

    assert BBCODE().clamp_size_tags(description) == description


def test_clamp_size_tags_clamps_oversized_nested_tags() -> None:
    description = "[size=11]Large [SIZE=24]Larger[/SIZE][/size]"

    assert BBCODE().clamp_size_tags(description) == "[size=10]Large [size=10]Larger[/SIZE][/size]"


def test_clamp_size_tags_preserves_malformed_or_non_integer_values() -> None:
    description = "[size=large]Text[/size] [size=11.5]Text[/size] [size= 12]Text[/size]"

    assert BBCODE().clamp_size_tags(description) == description


def test_convert_headings_to_sizes_maps_h1_through_h6() -> None:
    description = "\n".join(f"[h{level}]Texto com h{level}[/h{level}]" for level in range(1, 7))
    expected = "\n".join(
        (
            "[size=6][b]Texto com h1[/b][/size]",
            "[size=5][b]Texto com h2[/b][/size]",
            "[size=4][b]Texto com h3[/b][/size]",
            "[size=3][b]Texto com h4[/b][/size]",
            "[size=2][b]Texto com h5[/b][/size]",
            "[size=1][b][color=grey]Texto com h6[/color][/b][/size]",
        )
    )

    assert BBCODE().convert_headings_to_sizes(description) == expected


def test_convert_headings_to_sizes_handles_case_and_multiline_content() -> None:
    description = "[H3]Primeira linha\nSegunda linha[/H3]"

    assert BBCODE().convert_headings_to_sizes(description) == "[size=4][b]Primeira linha\nSegunda linha[/b][/size]"


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
    assert builder.tracker_specific_formats("HDBITS", "[size=16]Text[/size]") == "[size=16]Text[/size]"


def test_tracker_specific_formats_converts_colors_for_gazelle_trackers() -> None:
    builder = object.__new__(DescriptionBuilder)
    description = "[color=skyblue]Text[/color]"

    for tracker in ("ANTHELION", "BJSHARE", "BRASILTRACKER", "GREATPOSTERWALL"):
        assert builder.tracker_specific_formats(tracker, description) == "[color=#87ceeb]Text[/color]"

    assert builder.tracker_specific_formats("HDTORRENTS", description) == description


def test_tracker_specific_formats_converts_headings_for_selected_trackers() -> None:
    builder = object.__new__(DescriptionBuilder)
    description = "[h1]Título[/h1] [h6]Observação[/h6]"
    expected = "[size=6][b]Título[/b][/size] [size=1][b][color=grey]Observação[/color][/b][/size]"

    for tracker in ("ANTHELION", "BJSHARE", "BRASILTRACKER", "GREATPOSTERWALL"):
        assert builder.tracker_specific_formats(tracker, description) == expected

    assert builder.tracker_specific_formats("HDBITS", description) == description


def test_tracker_specific_formats_converts_unsupported_tags_for_brasiltracker() -> None:
    builder = object.__new__(DescriptionBuilder)
    cases = {
        "[url=https://img.example/a][img=350]https://img.example/a.png[/img][/url]": "[url=https://img.example/a][img]https://img.example/a.png[/img][/url]",
        "[code]Video:    1080p[/code]": "[pre]Video:    1080p[/pre]",
        "[strike]old[/strike] x[sup]2[/sup] H[sub]2[/sub]O": "[s]old[/s] x2 H2O",
        "[color=#0A0]green[/color]": "[color=#00aa00]green[/color]",
        "[font=Courier New]mono[/font] [note]note[/note] [indent]in[/indent][hr]": "mono note in",
        "[align=center]a[/align][align=justify]b[/align][align=left]c[/align]": "[center]a[/center]b[left]c[/left]",
        '[url="https://example.test"]link[/url]': "[url=https://example.test]link[/url]",
        "[collapse=Menu]x[/collapse][expand]y[/expand]": "[spoiler=Menu]x[/spoiler][spoiler]y[/spoiler]",
        "[list=1][*]a[/list][ul][li]b[/li][/ul]": "[*]a[*]b",
        "[tr][th]Head[/th][/tr]": "[tr][td][b]Head[/b][/td][/tr]",
        "[youtube]https://www.youtube.com/watch?v=abcdefghijk[/youtube]": "[youtube]abcdefghijk[/youtube]",
        "[video]https://youtu.be/abcdefghijk[/video] [video]https://video.example/clip.mp4[/video]": "[youtube]abcdefghijk[/youtube] [url]https://video.example/clip.mp4[/url]",
    }

    for description, expected in cases.items():
        assert builder.tracker_specific_formats("BRASILTRACKER", description) == expected


def test_tracker_specific_formats_converts_unsupported_tags_for_bjshare() -> None:
    builder = object.__new__(DescriptionBuilder)
    cases = {
        "[url=https://img.example/a][img=350]https://img.example/a.png[/img][/url]": "[url=https://img.example/a][img]https://img.example/a.png[/img][/url]",
        "[code]Video:    1080p[/code] [mediainfo]General[/mediainfo]": "[pre]Video:    1080p[/pre] [pre]General[/pre]",
        "[strike]old[/strike] x[sup]2[/sup] [color=#0A0]green[/color]": "[s]old[/s] x2 [color=#00aa00]green[/color]",
        "[right]a[/right][left]b[/left][align=justify]c[/align]": "[align=right]a[/align]bc",
        "[spoiler=Menu]x[/spoiler][collapse]y[/collapse]": "[hide=Menu]x[/hide][hide]y[/hide]",
        "[list=1][*]a[/list][ul][li]b[/li][/ul]": "[*]a[*]b",
        "[tr][th]Head[/th][/tr]": "[tr][td][b]Head[/b][/td][/tr]",
        "[youtube]abcdefghijk[/youtube]": "[youtube]https://www.youtube.com/watch?v=abcdefghijk[/youtube]",
        "[video]https://youtu.be/abcdefghijk[/video] [video]https://video.example/clip.mp4[/video]": "[video]https://youtu.be/abcdefghijk[/video] [url]https://video.example/clip.mp4[/url]",
    }

    for description, expected in cases.items():
        assert builder.tracker_specific_formats("BJSHARE", description) == expected


def test_tracker_specific_formats_converts_unsupported_tags_for_greatposterwall() -> None:
    builder = object.__new__(DescriptionBuilder)
    comparison = "[comparison=Source, Encode]\nhttps://img.example/1.png\nhttps://img.example/2.png\n[/comparison]"
    cases = {
        "[url=https://img.example/a][img=350]https://img.example/a.png[/img][/url]": "[img]https://img.example/a.png[/img]",
        "[strike]old[/strike] x[sup]2[/sup] [color=#0A0]g[/color] [note]n[/note] [hr]": "[s]old[/s] x2 [color=#00aa00]g[/color] n [hr]",
        "[center]a[/center][right]b[/right][left]c[/left][align=justify]d[/align]": "[align=center]a[/align][align=right]b[/align]cd",
        "[collapse=Menu]x[/collapse][hide]y[/hide]": "[spoiler=Menu]x[/spoiler][hide]y[/hide]",
        "[list=1][*]a[/list][tr][th]Head[/th][/tr]": "[*]a[tr][td][b]Head[/b][/td][/tr]",
        "[youtube]abcdefghijk[/youtube] [video]https://youtu.be/abcdefghijk[/video]": "[url]https://www.youtube.com/watch?v=abcdefghijk[/url] [url]https://youtu.be/abcdefghijk[/url]",
        comparison: comparison,
        "[mediainfo]General[/mediainfo]": "[mediainfo]General[/mediainfo]",
    }

    for description, expected in cases.items():
        assert builder.tracker_specific_formats("GREATPOSTERWALL", description) == expected


def test_tracker_specific_formats_converts_unsupported_tags_for_unit3d() -> None:
    builder = object.__new__(DescriptionBuilder)
    cases = {
        "[strike]old[/strike] [mediainfo]General[/mediainfo]": "[s]old[/s] [code]General[/code]",
        '[url="https://example.test"]link[/url]': "[url=https://example.test]link[/url]",
        "[align=center]a[/align][align=right]b[/align][align=justify]c[/align][indent]d[/indent]": "[center]a[/center][right]b[/right]cd",
        "[hide=Menu]x[/hide][collapse]y[/collapse][expand=More]z[/expand]": "[spoiler=Menu]x[/spoiler][spoiler]y[/spoiler][spoiler=More]z[/spoiler]",
        "[ul][li]a[/li][/ul][ol][li]b[/li][/ol]": "[list][*]a[/list][list=1][*]b[/list]",
        "[youtube]https://www.youtube.com/watch?v=abcdefghijk[/youtube] [video]https://video.example/clip.mp4[/video]": "[youtube]abcdefghijk[/youtube] [url]https://video.example/clip.mp4[/url]",
    }

    for description, expected in cases.items():
        assert builder.tracker_specific_formats("CAPYBARABR", description) == expected


def test_tracker_specific_formats_converts_comparisons_for_brasiltracker() -> None:
    builder = object.__new__(DescriptionBuilder)
    description = "[comparison=Source, Encode]\nhttps://img.example/1.png\nhttps://img.example/2.png\n[/comparison]"

    expected = "[center]Source | Encode\n[url=https://img.example/1.png][img]https://img.example/1.png[/img][/url][url=https://img.example/2.png][img]https://img.example/2.png[/img][/url][/center]"
    assert builder.tracker_specific_formats("BRASILTRACKER", description) == expected


def test_tracker_specific_formats_converts_colors_for_hdspace() -> None:
    builder = object.__new__(DescriptionBuilder)
    description = "[color=#87ceeb]Text[/color]"

    assert builder.tracker_specific_formats("HDSPACE", description) == "[color=skyblue]Text[/color]"


def test_tracker_specific_formats_converts_unsupported_tags_for_hdspace() -> None:
    builder = object.__new__(DescriptionBuilder)
    builder.tracker = "HDSPACE"
    cases = {
        "[code]Video:    1080p[/code] [mediainfo]General[/mediainfo]": "[pre]Video:    1080p[/pre] [pre]General[/pre]",
        "[s]a[/s] [strike]b[/strike] [color=#0a0]c[/color] [font=Mono]d[/font] [size=20]e[/size]": "a b c d [size=7]e[/size]",
        "[h4]Title[/h4] [hr]": "[u][b]Title[/b][/u] ",
        "[align=center]a[/align][right]b[/right][align=justify]c[/align]": "[center]a[/center]bc",
        "[spoiler=BDInfo]x[/spoiler][hide=Menu]y[/hide][collapse]z[/collapse]": "xyz",
        "[ul][li]a[/li][/ul] [list=1][*]b[/list]": "[list][*]a[/list] [list=1][*]b[/list]",
        "[table][tr][th]A[/th][th]B[/th][/tr][/table]": "A | B\n",
        "[youtube]abcdefghijk[/youtube]": "[url]https://www.youtube.com/watch?v=abcdefghijk[/url]",
    }

    for description, expected in cases.items():
        assert builder.tracker_specific_formats("HDSPACE", description) == expected


def test_tracker_specific_formats_converts_unsupported_tags_for_hdtorrents() -> None:
    builder = object.__new__(DescriptionBuilder)
    builder.tracker = "HDTORRENTS"
    cases = {
        "Emoji \U0001f3ac ✅ end": "Emoji  ✅ end",
        "[code]Video:    1080p[/code] [mediainfo]General[/mediainfo]": "[pre]Video:    1080p[/pre] [pre]General[/pre]",
        "[s]a[/s] [strike]b[/strike] [color=#0a0]c[/color] [size=20]d[/size] [hr]": "a b [color=#00aa00]c[/color] [size=7]d[/size] ",
        "[align=center]a[/align][align=right]b[/align][align=justify]c[/align]": "[center]a[/center][right]b[/right]c",
        "[spoiler=BDInfo]x[/spoiler][collapse]y[/collapse]": "[b]BDInfo[/b]\n[hide]x[/hide][hide]y[/hide]",
        "[list][*]a[/list] [ul][li]b[/li][/ul]": "[*]a [*]b",
        "[table][tr][th]A[/th][th]B[/th][/tr][/table]": "A | B\n",
        "[youtube]abcdefghijk[/youtube]": "[url]https://www.youtube.com/watch?v=abcdefghijk[/url]",
    }

    for description, expected in cases.items():
        assert builder.tracker_specific_formats("HDTORRENTS", description) == expected


def test_tracker_specific_formats_converts_unsupported_tags_for_mteam() -> None:
    builder = object.__new__(DescriptionBuilder)
    builder.tracker = "MTEAM"
    cases = {
        "[strike]a[/strike] [h1]T[/h1] [hr]": "[s]a[/s] [size=6][b]T[/b][/size] ",
        "[pre]x[/pre] [mediainfo]General[/mediainfo]": "[code]x[/code] [code]General[/code]",
        '[url="https://example.test"]l[/url] [img width=100]https://img.example/a.png[/img]': "[url=https://example.test]l[/url] [img]https://img.example/a.png[/img]",
        "[align=center]a[/align][align=justify]b[/align][indent]c[/indent]": "[center]a[/center]bc",
        "[spoiler=BDInfo]x[/spoiler][hide]y[/hide]": "[b]BDInfo[/b]\nxy",
        "[list]\n[*]a\n[*] b\n[/list]": "\n• a\n• b\n",
        "[youtube]abcdefghijk[/youtube]": "[url]https://www.youtube.com/watch?v=abcdefghijk[/url]",
    }

    for description, expected in cases.items():
        assert builder.tracker_specific_formats("MTEAM", description) == expected


def test_tracker_specific_formats_converts_unsupported_tags_for_speedapp() -> None:
    builder = object.__new__(DescriptionBuilder)
    builder.tracker = "SPEEDAPP"
    cases = {
        "[url=https://img.example/a][img=350]https://img.example/a.png[/img][/url]": "[url=https://img.example/a][img width=350]https://img.example/a.png[/img][/url]",
        "[strike]a[/strike] [indent]b[/indent] [mediainfo]General[/mediainfo]": "[s]a[/s] b [code]General[/code]",
        "[code]x[/code] [note]n[/note] [list][*]a[/list]": "[code]x[/code] [note]n[/note] [list][*]a[/list]",
        "[spoiler=BDInfo]x[/spoiler][spoiler=Fictional Title]y[/spoiler]": "[spoiler=BDInfo]x[/spoiler][b]Fictional Title[/b]\n[spoiler]y[/spoiler]",
        "[hide]a[/hide][collapse]b[/collapse]": "[spoiler]a[/spoiler][spoiler]b[/spoiler]",
        "[table][tr][th]A[/th][th]B[/th][/tr][/table]": "A | B\n",
        "[youtube]https://www.youtube.com/watch?v=abcdefghijk[/youtube]": "[youtube]abcdefghijk[/youtube]",
    }

    for description, expected in cases.items():
        assert builder.tracker_specific_formats("SPEEDAPP", description) == expected


def test_tracker_specific_formats_converts_unsupported_tags_for_torrentleech() -> None:
    builder = object.__new__(DescriptionBuilder)
    builder.tracker = "TORRENTLEECH"
    comparison = "[comparison=Source, Encode]\nhttps://img.example/1.png\nhttps://img.example/2.png\n[/comparison]"
    cases = {
        "before [hr] after": "before --- after",
        "[center]a[/center][align=center]b[/align][right]c[/right]": "<center>a</center><center>b</center>c",
        comparison: "<center>Source | Encode\n[url=https://img.example/1.png][img]https://img.example/1.png[/img][/url][url=https://img.example/2.png][img]https://img.example/2.png[/img][/url]</center>",
        "[img width=100]https://img.example/a.png[/img]": "[img]https://img.example/a.png[/img]",
        "[quote=Fictional User]q[/quote] [strike]s[/strike]": "[quote]q[/quote] [s]s[/s]",
        "[mediainfo]General[/mediainfo] [hide=Menu]x[/hide] [spoiler=BDInfo]y[/spoiler]": "General x y",
        "[list]\n[*]a\n[*]b\n[/list]": "\n• a\n• b\n",
        "[tr][th]Head[/th][/tr]": "[tr][td][b]Head[/b][/td][/tr]",
        "[video]https://youtu.be/abcdefghijk[/video]": "[youtube]abcdefghijk[/youtube]",
    }

    for description, expected in cases.items():
        assert builder.tracker_specific_formats("TORRENTLEECH", description) == expected


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


def test_release_group_boilerplate_is_removed_before_images_are_extracted(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.bbcode.RELEASE_GROUP_BOILERPLATE",
        {"FictionalGroup": (r"\[img[^\]]*\][^\[]*\[/img\]\s*(?=~~ Shots ~~)", r"~~ Shots ~~", r"More from FictionalGroup")},
    )
    desc = (
        "[center][img=500]https://img.example/banner.png[/img]\n~~ Shots ~~[/center]\n"
        "Fictional notes.\n"
        "[center][url=https://img.example/s1][img=500]https://img.example/s1.png[/img][/url][/center]\n"
        "[center]More from FictionalGroup[/center]"
    )

    cleaned, images = BBCODE().clean_unit3d_description(desc, "https://unit3d.example/api/torrents/1")

    assert cleaned.strip() == "Fictional notes."
    assert [image["img_url"] for image in images] == ["https://img.example/s1.png"]


def test_kitsune_divider_and_banner_are_removed() -> None:
    desc = (
        "[h3][center][img=500]https://img.example/banner.png[/img]\n"
        "    •❅───✧❅✦ [color=#F69047]Screenshots[/color] ✦❅✧───❅•[/center]\n"
        "[center][url=https://img.example/s1][img=500]https://img.example/s1.png[/img][/url][/center][/h3]"
    )

    cleaned, images = BBCODE().clean_unit3d_description(desc, "https://unit3d.example/api/torrents/1")

    assert cleaned == ""
    assert [image["img_url"] for image in images] == ["https://img.example/s1.png"]


def test_clean_unit3d_description_keeps_site_subdomain_image_hosts() -> None:
    desc = "Notes about unit3d.example.\n[url=https://img.example/s1][img]https://files.unit3d.example/u/s1.png[/img][/url]"

    cleaned, images = BBCODE().clean_unit3d_description(desc, "https://unit3d.example/api/torrents/1")

    assert cleaned == "Notes about unit3d."
    assert images[0]["img_url"] == "https://files.unit3d.example/u/s1.png"


def test_clean_unit3d_description_removes_signature_of_a_renamed_fork() -> None:
    desc = "Fictional notes.\n[right][url=https://github.com/fictional-user/fictional-upload-assistant][size=4]Shared with Upload-Assistant v1.2 (fork)[/size][/url][/right]"

    cleaned, _images = BBCODE().clean_unit3d_description(desc, "https://unit3d.example/api/torrents/1")

    assert cleaned == "Fictional notes."


def test_clean_unit3d_description_keeps_links_to_other_github_projects() -> None:
    desc = "[right][url=https://github.com/fictional-user/fictional-tool][size=4]Shared with Upload-Assistant v1.2[/size][/url][/right]"

    cleaned, _images = BBCODE().clean_unit3d_description(desc, "https://unit3d.example/api/torrents/1")

    assert cleaned == desc


def test_known_boilerplate_patterns_compile() -> None:
    import re

    from src.bbcode import RELEASE_GROUP_BOILERPLATE, TONEMAPPED_NOTES, UPLOAD_TOOL_SIGNATURES

    for patterns in (*RELEASE_GROUP_BOILERPLATE.values(), *UPLOAD_TOOL_SIGNATURES.values(), TONEMAPPED_NOTES):
        for pattern in patterns:
            re.compile(pattern)


def _clean_unit3d(desc: str) -> tuple[str, list[str]]:
    cleaned, images = BBCODE().clean_unit3d_description(desc, "https://unit3d.example/api/torrents/1")
    return cleaned.strip(), [image["img_url"] for image in images]


SHOT = "[url=https://img.example/s1][img=350]https://img.example/s1.png[/img][/url]"


def test_upload_tool_signature_in_its_own_block_is_removed() -> None:
    desc = f"Fictional notes.\n[center]{SHOT}[/center]\n[right][url=https://github.com/autobrr/upbrr][size=4]Uploaded by upbrr[/size][/url][/right]"

    assert _clean_unit3d(desc) == ("Fictional notes.", ["https://img.example/s1.png"])


def test_upload_tool_signature_sharing_a_block_with_screenshots_keeps_the_screenshots() -> None:
    desc = f"Fictional notes.\n[center][color=#7760de][size=16]⚡ Uploaded using EASY UPLOAD3R ⚡[/size][/color]\n{SHOT}[/center]"

    assert _clean_unit3d(desc) == ("Fictional notes.", ["https://img.example/s1.png"])


def test_upload_tool_text_and_image_signatures_are_removed() -> None:
    desc = (
        "[center][b][i][url=https://codeberg.org/CvT/Uploadrr]Powered by Uploadrr[/url][/i][/b][/center]\n"
        f"Fictional notes.\n[center]{SHOT}[/center]\n"
        "[center][url=https://codeberg.org/CvT/Uploadrr][img=400]https://img.example/tool-logo.webp[/img][/url][/center]"
    )

    assert _clean_unit3d(desc) == ("Fictional notes.", ["https://img.example/s1.png"])


def test_nfoforge_signature_is_removed_and_the_nfo_kept() -> None:
    desc = "[code]Fictional release notes.\n\n[size=15]Shared with [url=https://github.com/jesterr0/NfoForge]NfoForge v1.0.0[/url][/size]\n[/code]"

    cleaned, _images = _clean_unit3d(desc)

    assert "NfoForge" not in cleaned
    assert "Fictional release notes." in cleaned


def test_upsies_and_ak_automated_uploader_signatures_are_removed() -> None:
    desc = (
        f"Fictional notes.\n[center]{SHOT}[/center]\n"
        "[right][size=1]Shared with [url=https://upsies.readthedocs.io]upsies[/url][/size][/right]\n"
        "[center][small]Uploaded with [url=https://github.com/AQTKU/ak-automated-uploader]AK Automated Uploader[/url][/small][/center]"
    )

    assert _clean_unit3d(desc) == ("Fictional notes.", ["https://img.example/s1.png"])


def test_only_uploader_and_magus_signatures_are_removed() -> None:
    desc = (
        f"Fictional notes.\n[center]{SHOT}[/center]\n"
        "[center][url=https://github.com/edge20200/Only-Uploader]Brought to you by Only-Uploader[/url][/center]"
        "[right][size=4][color=#4DA6FF][url=https://dailyusetools.com/MAGUS]Uploaded with MAGUS v1.0.0[/url][/color][/size][/right]"
    )

    assert _clean_unit3d(desc) == ("Fictional notes.", ["https://img.example/s1.png"])


def test_block_patterns_only_remove_whole_blocks(monkeypatch) -> None:
    from src.bbcode import _block

    monkeypatch.setattr("src.bbcode.RELEASE_GROUP_BOILERPLATE", {"FictionalGroup": (_block(r"SCREENSHOTS"),)})
    desc = "[center][color=#a61805][size=18][font=Arial]SCREENSHOTS[/font][/size][/color][/center]\nThe SCREENSHOTS below are fictional."

    assert _clean_unit3d(desc)[0] == "The SCREENSHOTS below are fictional."


def test_portuguese_tonemapped_note_is_removed() -> None:
    note = (
        "[quote]Foi feito o mapeamento de tonalidade nas screenshots para melhor compatibilidade com telas SDR, "
        "o resultado pode não representar as cores reais do vídeo.[/quote]"
    )

    assert _clean_unit3d(note) == ("", [])
    assert _clean_unit3d(f"Fictional notes.\n{note}\n[center]{SHOT}[/center]") == ("Fictional notes.", ["https://img.example/s1.png"])


def test_tonemapped_note_inside_a_longer_quote_keeps_the_quote_balanced() -> None:
    desc = (
        "[quote]Fictional notes. Foi feito o mapeamento de tonalidade nas screenshots para melhor compatibilidade "
        "com telas SDR, o resultado pode não representar as cores reais do vídeo.[/quote]"
    )

    assert _clean_unit3d(desc)[0] == "[quote]Fictional notes. [/quote]"


def test_upload_tool_signature_does_not_swallow_a_screenshot_in_the_same_block() -> None:
    desc = f"Fictional notes.\n[center][url=https://github.com/autobrr/upbrr][size=4]Uploaded by upbrr[/size][/url]\n{SHOT}[/center]"

    assert _clean_unit3d(desc) == ("Fictional notes.", ["https://img.example/s1.png"])
