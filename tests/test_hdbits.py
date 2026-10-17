import pytest

from src.meta import Meta
from src.trackers.hdbits import HDBits

pytestmark = pytest.mark.asyncio


def make_meta(**overrides):
    return Meta({
        "name": "Example Title 2015 1080p WEB-DL DD+ 5.1 H.264-GROUP",
        "title": "Example Title",
        "category": "MOVIE",
        "audio": "DD+ 5.1",
        "year": 2015,
        "type": "WEBDL",
    }, **overrides)


async def test_hdbits_preserves_title_spacing_without_service():
    name = await HDBits({}).get_name(make_meta())

    assert name == "Example Title 2015 1080p WEB-DL DD+5.1 H.264-GROUP"  # noqa: S101


@pytest.mark.parametrize("custom_name", ["Example Title... 1080p", "Example Title ... 1080p"])
async def test_hdbits_preserves_custom_title_ellipsis(custom_name):
    meta = make_meta(title="Example! Title", name=custom_name, manual_name=custom_name)

    name = await HDBits({}).get_name(meta)

    assert name == custom_name  # noqa: S101


@pytest.mark.parametrize("custom_name,expected_name", [
    ("Example Title", "Original Title"),
    ("Example Title 2015 1080p", "Original Title 2015 1080p"),
    ("Example Titles 2015 1080p", "Example Titles 2015 1080p"),
    ("Example Title... 2015 1080p", "Example Title... 2015 1080p"),
])
async def test_hdbits_requires_complete_title_prefix(custom_name, expected_name):
    meta = make_meta(name=custom_name, manual_name=custom_name, imdb_info={"aka": "Original Title"})

    name = await HDBits({}).get_name(meta)

    assert name == expected_name  # noqa: S101


@pytest.mark.parametrize("use_imdb_title", [False, True])
async def test_hdbits_preserves_title_commas(use_imdb_title):
    expected_title = "Example Chronicles: Dawn, Noon, Dusk"
    title = expected_title.replace(",", "") if use_imdb_title else expected_title
    meta = make_meta(
        category="TV",
        name=f"{title} S01 2160p WEB-DL AAC 2.0 H.264",
        title=title,
        audio="AAC 2.0",
        imdb_info={"aka": expected_title} if use_imdb_title else {},
    )

    name = await HDBits({}).get_name(meta)

    assert name == f"{expected_title} S01 2160p WEB-DL AAC2.0 H.264"  # noqa: S101


@pytest.mark.parametrize("title", [
    "Przykładowy świat: Dokąd? / 架空示例",
    'Example "Story" (Part II) — What\'s Next...?!',
])
async def test_hdbits_preserves_imdb_original_title(title):
    meta = make_meta(imdb_info={"aka": title, "title": "Localized Title"})

    name = await HDBits({}).get_name(meta)

    assert name == f"{title} 2015 1080p WEB-DL DD+5.1 H.264-GROUP"  # noqa: S101


@pytest.mark.parametrize("imdb_info,expected_title", [
    ({"aka": "", "title": "IMDb's Display Title?"}, "IMDb's Display Title?"),
    ({"type": "movie"}, "Example Title"),
])
async def test_hdbits_title_fallback(imdb_info, expected_title):
    meta = make_meta(imdb_info=imdb_info)

    name = await HDBits({}).get_name(meta)

    assert name == f"{expected_title} 2015 1080p WEB-DL DD+5.1 H.264-GROUP"  # noqa: S101


async def test_hdbits_formats_only_release_details():
    title = "Example HDR REMUX: Dual-Audio H.265...?"
    meta = make_meta(
        name=f"{title} AKA Other Title 2015 1080p NF WEB-DL DD+ 5.1 HDR H.265-GROUP",
        title=title,
        aka="AKA Other Title",
        service="NF",
        hdr="HDR",
    )

    name = await HDBits({}).get_name(meta)

    assert name == f"{title} 2015 1080p WEB-DL DD+5.1 HDR10 HEVC-GROUP"  # noqa: S101


@pytest.mark.parametrize("imdb_type", ["tvMiniSeries", "tv mini series"])
@pytest.mark.parametrize("numbering,expected_numbering", [
    ("S01", "2019"),
    ("2015 S01", "2019"),
    ("2019 S01", "2019"),
    ("2019", "2019"),
    ("S010", "2019 S010"),
    ("S01-S02", "2019 S01-S02"),
])
async def test_hdbits_miniseries_uses_imdb_year(imdb_type, numbering, expected_numbering):
    meta = make_meta(
        category="TV",
        tv_pack=True,
        title="Example Series",
        name=f"Example Series {numbering} 2160p WEB-DL AAC 2.0 H.264",
        audio="AAC 2.0",
        imdb_info={"aka": "Example's Miniseries: Why?", "type": imdb_type, "year": 2019},
    )
    original = meta.copy()

    name = await HDBits({}).get_name(meta)

    assert name == f"Example's Miniseries: Why? {expected_numbering} 2160p WEB-DL AAC2.0 H.264"  # noqa: S101
    assert meta == original  # noqa: S101


@pytest.mark.parametrize("imdb_type", ["tvMiniSeries", "tv mini series"])
@pytest.mark.parametrize("numbering,expected_numbering", [
    ("S01E02", "S01E02"),
    ("2015 S01E02", "2019 S01E02"),
    ("2019 S01E02", "2019 S01E02"),
])
async def test_hdbits_miniseries_loose_episode_keeps_season(imdb_type, numbering, expected_numbering):
    meta = make_meta(
        category="TV",
        tv_pack=False,
        title="Example Series",
        name=f"Example Series {numbering} 1080p WEB-DL DD+ 5.1 H.264",
        season="S01",
        episode="E02",
        imdb_info={"type": imdb_type, "year": 2019},
    )

    name = await HDBits({}).get_name(meta)

    assert name == f"Example Series {expected_numbering} 1080p WEB-DL DD+5.1 H.264"  # noqa: S101


@pytest.mark.parametrize("imdb_type", ["tvSeries", "movie", None])
async def test_hdbits_other_imdb_types_keep_season(imdb_type):
    meta = make_meta(
        category="TV",
        name="Example Series S01 1080p WEB-DL DD+ 5.1 H.264",
        title="Example Series",
        imdb_info={"type": imdb_type, "year": 2019},
    )

    name = await HDBits({}).get_name(meta)

    assert name == "Example Series S01 1080p WEB-DL DD+5.1 H.264"  # noqa: S101


@pytest.mark.parametrize("meta_year,expected", [
    (2015, "2015"),
    (None, "S01"),
])
async def test_hdbits_miniseries_with_missing_year(meta_year, expected):
    meta = make_meta(
        category="TV",
        tv_pack=True,
        name="Example Series S01 1080p WEB-DL DD+ 5.1 H.264",
        title="Example Series",
        year=meta_year,
        imdb_info={"type": "tvMiniSeries", "year": None},
    )

    name = await HDBits({}).get_name(meta)

    assert name == f"Example Series {expected} 1080p WEB-DL DD+5.1 H.264"  # noqa: S101


async def test_hdbits_miniseries_keeps_incomplete_marker():
    meta = make_meta(
        category="TV",
        name="Example Series S01 1080p WEB-DL DD+ 5.1 H.264",
        title="Example Series",
        imdb_info={"aka": "Example S01: 2015?", "type": "tvMiniSeries", "year": 2019},
        tv_pack=True,
        season="S01",
        season_pack_incomplete=True,
    )

    name = await HDBits({}).get_name(meta)

    assert name == "Example S01: 2015? 2019 INCOMPLETE 1080p WEB-DL DD+5.1 H.264"  # noqa: S101


async def test_hdbits_imdb_year_does_not_change_title():
    meta = make_meta(
        name="Example 2015 2015 1080p WEB-DL DD+ 5.1 H.264",
        title="Example 2015",
        imdb_info={"aka": "Example 2015?", "year": 2019},
    )

    name = await HDBits({}).get_name(meta)

    assert name == "Example 2015? 2019 1080p WEB-DL DD+5.1 H.264"  # noqa: S101


async def test_hdbits_miniseries_keeps_custom_title_at_start():
    custom_name = "Custom Title S01 1080p WEB-DL DD+ 5.1 H.264"
    meta = make_meta(
        category="TV",
        tv_pack=True,
        name=custom_name,
        manual_name=custom_name,
        imdb_info={"aka": "Example Series", "type": "tvMiniSeries", "year": 2019},
    )

    name = await HDBits({}).get_name(meta)

    assert name == "Custom Title S01 1080p WEB-DL DD+5.1 H.264"  # noqa: S101
