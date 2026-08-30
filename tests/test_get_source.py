"""Regression tests for release source detection."""

import pytest

from src.get_name import NameManager
from src.get_source import get_source
from src.meta import Meta


@pytest.mark.asyncio
async def test_release_group_named_vhs_does_not_override_remux_source(tmp_path):
    filename = "Example Movie 1995 (Alternate Title) 1080p Remux AVC FLAC 2.0-VHS.mkv"
    meta = Meta(category="MOVIE", uuid=filename)

    source, release_type = await get_source("REMUX", filename, filename, "", meta, "case", str(tmp_path))

    assert source == "BluRay"
    assert release_type == "REMUX"

    name_meta = Meta(
        category="MOVIE",
        type=release_type,
        source=source,
        title="Example Movie",
        aka="AKA Alternate Title",
        year=1995,
        resolution="1080p",
        uhd="",
        video_codec="AVC",
        audio="FLAC 2.0",
        tag="-VHS",
    )
    _name_notag, name, _clean_name, _potential_missing = await NameManager({}).get_name(name_meta)

    assert name == "Example Movie AKA Alternate Title 1995 1080p BluRay REMUX AVC FLAC 2.0-VHS"


@pytest.mark.asyncio
async def test_vhs_source_before_a_distinct_release_group_is_preserved(tmp_path):
    filename = "Movie.1995.1080p.VHS.Remux.AVC.FLAC.2.0-GROUP.mkv"
    meta = Meta(category="MOVIE", uuid=filename)

    source, release_type = await get_source("REMUX", filename, filename, "", meta, "case", str(tmp_path))

    assert source == "VHS"
    assert release_type == "REMUX"


@pytest.mark.asyncio
async def test_vhs_title_token_alongside_the_real_source_resolves_to_the_real_source(tmp_path):
    filename = "VHS.85.2023.1080p.BluRay.x264-GROUP.mkv"
    meta = Meta(category="MOVIE", uuid=filename)

    source, release_type = await get_source("ENCODE", filename, filename, "", meta, "case", str(tmp_path))

    assert source == "BluRay"
    assert release_type == "ENCODE"
