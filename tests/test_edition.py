"""Regression coverage for release-marker detection in edition handling."""

import asyncio

import pytest

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
