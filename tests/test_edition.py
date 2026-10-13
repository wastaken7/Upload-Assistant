"""Regression coverage for release-marker detection in edition handling."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src import prep_helpers
from src.edition import _has_release_token, _strip_release_tokens, get_edition
from src.meta import Meta


@pytest.mark.parametrize(
    ("value", "token"),
    [
        ("Show.V2.1080p", "V2"),
        ("Show-V3-1080p", "V3"),
        ("Show V4 1080p", "V4"),
        ("Show.REPACK.1080p", "REPACK"),
        ("Show-REPACK2-1080p", "REPACK2"),
        ("Show REPACK3 1080p", "REPACK3"),
        ("Show.PROPER.1080p", "PROPER"),
        ("Show-PROPER2-1080p", "PROPER2"),
        ("Show PROPER3 1080p", "PROPER3"),
        ("Show.RERIP.1080p", "RERIP"),
    ],
)
def test_release_marker_matches_standalone_tokens(value: str, token: str) -> None:
    assert _has_release_token(value, token)


@pytest.mark.parametrize(
    ("value", "token"),
    [
        ("TV2", "V2"),
        ("TV3", "V3"),
        ("TV4", "V4"),
        ("REPACKAGED", "REPACK"),
        ("REPACK2X", "REPACK2"),
        ("REPACK3X", "REPACK3"),
        ("PROPERLY", "PROPER"),
        ("PROPER2X", "PROPER2"),
        ("PROPER3X", "PROPER3"),
        ("RERIPPED", "RERIP"),
    ],
)
def test_release_marker_does_not_match_inside_other_tokens(value: str, token: str) -> None:
    assert not _has_release_token(value, token)


def test_strip_release_tokens_uses_non_alphanumeric_boundaries() -> None:
    assert _strip_release_tokens("Director_PROPER2") == "Director_"


def test_get_edition_detects_repack_between_hyphens() -> None:
    edition, repack, hybrid = asyncio.run(get_edition("Movie-REPACK-1080p", None, [], "", Meta(category="TV")))

    assert edition == ""
    assert repack == "REPACK"
    assert not hybrid


@pytest.mark.parametrize("prefix", ["REPACK", "PROPER"])
@pytest.mark.parametrize("suffix", ["", "2", "3", "4", "5", "6", "7", "8", "9"])
def test_get_edition_detects_release_marker_numbers(prefix: str, suffix: str) -> None:
    marker = f"{prefix}{suffix}"
    edition, repack, hybrid = asyncio.run(get_edition(f"Example.Movie.2025.{marker}.1080p.WEB-DL-GROUP", None, [], "", Meta(category="TV")))

    assert edition == ""
    assert repack == marker
    assert not hybrid


@pytest.mark.parametrize("separator", [".", "-", "_", " "])
@pytest.mark.parametrize("marker", ["repack6", "pRoPeR9"])
def test_get_edition_detects_release_markers_with_common_separators(separator: str, marker: str) -> None:
    video = separator.join(["Example", "Movie", "2025", marker, "1080p", "WEB-DL"]) + "-GROUP"
    _, repack, _ = asyncio.run(get_edition(video, None, [], "", Meta(category="TV")))

    assert repack == marker.upper()


@pytest.mark.parametrize(
    "marker",
    [
        "REPACK0",
        "PROPER0",
        "REPACK1",
        "PROPER1",
        "REPACK00",
        "PROPER00",
        "REPACK01",
        "PROPER01",
        "REPACK10",
        "PROPER10",
        "REPACK123",
        "PROPER123",
        "REPACK6X",
        "PROPER9X",
        "XREPACK6",
        "XPROPER9",
        "REPACKAGED",
        "PROPERLY",
    ],
)
def test_invalid_release_markers_are_not_detected_or_stripped(marker: str) -> None:
    video = f"Example.Movie.2025.{marker}.1080p.WEB-DL-GROUP"
    _, repack, _ = asyncio.run(get_edition(video, None, [], "", Meta(category="TV")))

    assert repack == ""
    assert _strip_release_tokens(f"Extended {marker}") == f"Extended {marker}"


@pytest.mark.parametrize("marker", ["REPACK6", "REPACK9", "proper9", "RERIP"])
def test_get_edition_strips_detected_release_markers_from_edition(monkeypatch: pytest.MonkeyPatch, marker: str) -> None:
    monkeypatch.setattr("src.edition.guessit_fn", lambda _video: {"edition": f"Extended {marker}", "release_group": "GROUP"})

    edition, repack, _ = asyncio.run(get_edition("Example.Movie.2025.1080p.WEB-DL-GROUP", None, [], "", Meta(category="TV")))

    assert edition == "Extended"
    assert repack == marker.upper()


@pytest.mark.parametrize("marker", ["REPACK6", "REPACK9", "proper9", "RERIP"])
@pytest.mark.parametrize("as_list", [False, True])
def test_get_edition_preserves_manual_release_markers(marker: str, as_list: bool) -> None:
    manual_edition = ["Extended", marker] if as_list else f"Extended {marker}"
    edition, repack, _ = asyncio.run(get_edition("Example.Movie.2025.1080p.WEB-DL-GROUP", None, [], manual_edition, Meta(category="TV")))

    assert edition == f"Extended {marker}"
    assert repack == marker.upper()


@pytest.mark.parametrize(
    ("markers", "expected"),
    [
        ("V2", "REPACK"),
        ("V3", "REPACK2"),
        ("V4", "REPACK3"),
        ("V5", "REPACK4"),
        ("V6", "REPACK5"),
        ("V7", "REPACK6"),
        ("V8", "REPACK7"),
        ("V9", "REPACK8"),
        ("V10", "REPACK9"),
        ("v10", "REPACK9"),
        ("V1", ""),
        ("V11", ""),
        ("V100", ""),
        ("TV10", ""),
        ("V10X", ""),
        ("TV2.TV3.TV4", ""),
        ("REPACK2.V4", "REPACK3"),
        ("REPACK6.V4", "REPACK6"),
        ("REPACK6.V10", "REPACK9"),
        ("V10.PROPER6", "PROPER6"),
        ("REPACK6.REPACK9", "REPACK9"),
        ("REPACK9.REPACK6", "REPACK9"),
        ("PROPER6.PROPER9", "PROPER9"),
        ("REPACK9.PROPER", "PROPER"),
        ("REPACK9.PROPER6.RERIP", "RERIP"),
    ],
)
def test_get_edition_preserves_release_marker_priority(markers: str, expected: str) -> None:
    _, repack, _ = asyncio.run(get_edition(f"Example.Movie.2025.{markers}.1080p.WEB-DL-GROUP", None, [], "", Meta(category="TV")))

    assert repack == expected


@pytest.mark.parametrize(
    ("markers", "manual_edition", "expected_repack", "expected_edition"),
    [
        ("REPACK9", "", "REPACK9", ""),
        ("proper9", "", "PROPER9", ""),
        ("", "Extended REPACK9", "REPACK9", "Extended"),
        ("", ["Extended", "proper9"], "PROPER9", "Extended"),
        ("", "REPACK6 PROPER9 RERIP Extended", "RERIP", "Extended"),
        ("", "Extended REPACK6 PROPER9 RERIP Extras", "RERIP", "Extended Extras"),
        ("", "Extended REPACK10", "", "Extended REPACK10"),
        ("", "Extended XREPACK9", "", "Extended XREPACK9"),
        ("RERIP", "Extended REPACK9", "RERIP", "Extended"),
    ],
)
def test_finalize_metadata_separates_release_markers_from_edition(
    monkeypatch: pytest.MonkeyPatch, markers: str, manual_edition: str | list[str], expected_repack: str, expected_edition: str
) -> None:
    video = f"Example.Movie.2025.{markers}.1080p.WEB-DL-GROUP"
    meta = Meta(category="MOVIE", type="WEBDL", path=video, uuid=video, tag="-GROUP", manual_edition=manual_edition)
    prep = SimpleNamespace(
        config={"DEFAULT": {}},
        audio_manager=SimpleNamespace(get_audio_v2=AsyncMock(return_value=("", "", False))),
        stream_optimized=AsyncMock(return_value=False),
        check_adult_media=lambda _meta: False,
    )
    monkeypatch.setattr(
        prep_helpers,
        "video_manager",
        SimpleNamespace(
            get_container=AsyncMock(return_value="mkv"),
            is_3d=AsyncMock(return_value=""),
            get_uhd=AsyncMock(return_value=""),
            get_hdr=AsyncMock(return_value=""),
            get_video_encode=AsyncMock(return_value=("x264", "AVC", False, "8")),
        ),
    )
    monkeypatch.setattr(prep_helpers, "get_source", AsyncMock(return_value=("WEB", "WEBDL")))
    monkeypatch.setattr(prep_helpers, "tag_override", AsyncMock(side_effect=lambda current: current))

    asyncio.run(prep_helpers.finalize_metadata(prep, meta, video, {}, None, video, video, video))

    assert meta.repack == expected_repack
    assert meta.edition == expected_edition
