"""Regression tests for release-group extraction."""

import pytest

from src.get_name import NameManager
from src.meta import Meta
from src.tags import get_tag


@pytest.mark.parametrize("season_pack_check", [False, True])
@pytest.mark.asyncio
async def test_zr_terminal_hyphen_preserved(season_pack_check):
    filename = "Example Show S01E01 2005 1080p Bluray REMUX AVC DTS-HD MA 2.0 Dual Audio -ZR-.mkv"
    meta = Meta(category="TV", anime=True, uuid=filename)
    assert await get_tag(filename, meta, season_pack_check=season_pack_check) == "-ZR-"


@pytest.mark.asyncio
async def test_zr_season_file_fallback():
    filename = "Example Show S01E01 2005 1080p Bluray REMUX AVC DTS-HD MA 2.0 Dual Audio -ZR-.mkv"
    meta = Meta(category="TV", anime=True, tv_pack=True, uuid="Example Show S01 USBD Remux")
    assert await get_tag(filename, meta, season_pack_check=True) == "-ZR-"


@pytest.mark.asyncio
async def test_zr_generic_season_folder():
    files = [f"Example Show S01E{n:02} 1080p BluRay -ZR-.mkv" for n in (1, 2)]
    meta = Meta(category="TV", anime=True, tv_pack=True, uuid="Example Show S01 USBD Remux", filelist=files)
    assert await get_tag(files[0], meta) == "-ZR-"
    meta.filelist = [files[0], "Example Show S01E02 1080p BluRay -Other.mkv"]
    assert await get_tag(files[0], meta) == ""
    assert await get_tag(meta.filelist[1], meta, season_pack_check=True) == "-Other"


@pytest.mark.asyncio
async def test_zr_generic_season_folder_ignores_extras():
    files = [f"Another Show S01E{n:02} 2011 1080p Bluray REMUX AVC AAC 2.0 Dual Audio -ZR-.mkv" for n in (1, 2)]
    meta = Meta(category="TV", anime=True, tv_pack=True, uuid="Another Show S01 Remux",
                filelist=[*files, "NCED #02.mkv", "NCOP #02.mkv"])
    assert await get_tag(files[0], meta) == "-ZR-"
    assert await get_tag("NCED #02.mkv", meta, season_pack_check=True) == ""


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


@pytest.mark.asyncio
async def test_long_release_group_is_preserved_without_scene_detection():
    filename = "The.Movie.2011.1080p.WEB-DL.DD2.0.H.264-10GaugeSlugBlaster.mkv"

    tag = await get_tag(filename, Meta(category="MOVIE", uuid=filename))

    assert tag == "-10GaugeSlugBlaster"
