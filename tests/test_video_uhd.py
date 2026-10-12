import pytest
from guessit import guessit

from src.get_name import NameManager
from src.meta import Meta
from src.video import VideoManager


@pytest.mark.asyncio
@pytest.mark.parametrize("group", ["GROUPUHD", "UHDGROUP"])
@pytest.mark.parametrize(("release_type", "source_label", "codec"), [("WEBDL", "WEB-DL", "H.265"), ("WEBRIP", "WEBRip", "x265")])
async def test_uhd_in_release_group_does_not_add_uhd_to_web_title(group, release_type, source_label, codec):
    filename = f"Example Movie (2000) 2160p Netflix {source_label} DD5.1 HEVC-{group}.mkv"
    uhd = await VideoManager().get_uhd(release_type, guessit(filename), "2160p", filename)
    meta = Meta(
        category="MOVIE",
        type=release_type,
        source="Web",
        title="Example Movie",
        year=2000,
        resolution="2160p",
        uhd=uhd,
        service="NF",
        audio="DD 5.1",
        video_encode=codec,
        tag=f"-{group}",
    )

    _name_notag, name, _clean_name, _potential_missing = await NameManager({}).get_name(meta)

    assert name == f"Example Movie 2000 2160p NF {source_label} DD 5.1 {codec}-{group}"


@pytest.mark.asyncio
@pytest.mark.parametrize("separator", [" ", ".", "_", "-"])
async def test_standalone_uhd_marker_is_preserved(separator):
    filename = separator.join(["Example Movie", "2000", "2160p", "UHD", "NF", "WEB-DL", "H.265-GROUP.mkv"])

    assert await VideoManager().get_uhd("WEBDL", guessit(filename), "2160p", filename) == "UHD"


@pytest.mark.asyncio
async def test_1080p_encode_preserves_explicit_uhd_marker():
    filename = "Example.Movie.2000.1080p.UHD.BluRay.x265-GROUP.mkv"

    assert await VideoManager().get_uhd("ENCODE", guessit(filename), "1080p", filename) == "UHD"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("release_type", "resolution", "expected"),
    [
        ("DISC", "2160p", "UHD"),
        ("REMUX", "2160p", "UHD"),
        ("ENCODE", "2160p", "UHD"),
        ("REMUX", "1080p", ""),
        ("WEBDL", "2160p", ""),
        ("WEBRIP", "2160p", ""),
    ],
)
async def test_uhd_resolution_inference(release_type, resolution, expected):
    assert await VideoManager().get_uhd(release_type, {}, resolution, "Example Movie-GROUP") == expected
