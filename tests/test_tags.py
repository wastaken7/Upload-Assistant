"""Regression tests for release-group extraction."""

import pytest

from src.get_name import NameManager
from src.meta import Meta
from src.tags import get_tag


@pytest.mark.parametrize(
    "filename",
    [
        "Movie.2005.1080p.WEB-DL.mkv",
        "Movie.2005.1080p.Blu-ray.mkv",
    ],
)
@pytest.mark.asyncio
async def test_technical_hyphens_are_not_release_group_separators(filename):
    tag = await get_tag(filename, Meta(category="MOVIE", uuid=filename))

    assert tag == ""


@pytest.mark.asyncio
async def test_dts_hd_audio_is_not_treated_as_a_release_group():
    filename = "Example Movie 2005 1080p BluRay REMUX AVC DTS-HD MA 5.1.mkv"
    tag = await get_tag(filename, Meta(category="MOVIE", uuid=filename))

    assert tag == ""

    name_meta = Meta(
        category="MOVIE",
        type="REMUX",
        source="BluRay",
        title="Example Movie",
        year=2005,
        resolution="1080p",
        uhd="",
        video_codec="AVC",
        audio="DTS-HD MA 5.1",
        tag=tag,
    )
    _name_notag, name, _clean_name, _potential_missing = await NameManager({}).get_name(name_meta)

    assert name == "Example Movie 2005 1080p BluRay REMUX AVC DTS-HD MA 5.1"


@pytest.mark.asyncio
async def test_release_group_after_dts_hd_audio_is_preserved():
    filename = "Movie.2005.1080p.BluRay.REMUX.AVC.DTS-HD.MA.5.1-GROUP.mkv"

    tag = await get_tag(filename, Meta(category="MOVIE", uuid=filename))

    assert tag == "-GROUP"
