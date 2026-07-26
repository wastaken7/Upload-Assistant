"""Regression coverage for release-marker detection in edition handling."""

import pytest

from src.edition import _has_release_token


@pytest.mark.parametrize("value", ["V2", "Show.S01E01.V2.1080p", "Movie-REPACK-1080p", "Movie PROPER2 1080p"])
def test_release_marker_matches_standalone_tokens(value: str) -> None:
    token = "V2" if "V2" in value else "REPACK" if "REPACK" in value else "PROPER2"
    assert _has_release_token(value, token)


@pytest.mark.parametrize("value", ["TV2", "TV2.WEB-DL", "SV2", "V2GROUP", "REPACKAGED", "PROPERLY"])
def test_release_marker_does_not_match_inside_other_tokens(value: str) -> None:
    assert not _has_release_token(value, "V2")
    assert not _has_release_token(value, "REPACK")
    assert not _has_release_token(value, "PROPER")
