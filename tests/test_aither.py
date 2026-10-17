# ruff: noqa: S101
import asyncio
from unittest.mock import AsyncMock

import pytest

from src.meta import Meta
from src.sports import detect_sports
from src.trackers.UNIT3D.aither import Aither


def _name(meta: Meta) -> str:
    config = {"DEFAULT": {}, "TRACKERS": {"AITHER": {}}}
    return asyncio.run(Aither(config).get_name(meta))["name"]


def _category(meta: Meta, **kwargs: object) -> dict[str, str]:
    config = {"DEFAULT": {}, "TRACKERS": {"AITHER": {}}}
    return asyncio.run(Aither(config).get_category_id(meta, **kwargs))


def test_aither_uses_sports_category_for_detected_sports() -> None:
    assert _category(Meta(category="MOVIE", is_sports=True)) == {"category_id": "9"}
    assert _category(Meta(category="TV", is_sports=True)) == {"category_id": "9"}


def test_aither_preserves_regular_categories() -> None:
    assert _category(Meta(category="MOVIE")) == {"category_id": "1"}
    assert _category(Meta(category="TV")) == {"category_id": "2"}


def test_aither_exposes_sports_category_mapping() -> None:
    assert _category(Meta(), mapping_only=True)["SPORTS"] == "9"
    assert _category(Meta(), reverse=True)["9"] == "SPORTS"


@pytest.mark.asyncio
@pytest.mark.parametrize("episode,tv_pack", [(0, True), (3, False)])
@pytest.mark.parametrize("sports_event", [False, True])
async def test_aither_upload_category_and_tv_fields_agree(monkeypatch, episode, tv_pack, sports_event):
    tracker = Aither({"DEFAULT": {}, "TRACKERS": {"AITHER": {}}})
    title = "UFC 123 Example Event" if sports_event else "Example Sports Family"
    meta = Meta(
        category="TV",
        title=title,
        name=f"{title} S01 1080p WEB-DL-GROUP",
        genres=["Reality", "Sport"],
        keywords=["baseball"],
        season_int=1,
        episode_int=episode,
        tv_pack=tv_pack,
        language_checked=True,
    )
    meta.is_sports = detect_sports(meta)
    for method in ("get_description", "get_mediainfo", "get_bdinfo"):
        monkeypatch.setattr(tracker, method, AsyncMock(return_value={}))

    data = await tracker.get_data(meta)

    assert data["category_id"] == ("9" if sports_event else "2")
    if sports_event:
        assert "season_number" not in data
        assert "episode_number" not in data
    else:
        assert data["season_number"] == "1"
        assert data["episode_number"] == str(episode)
    assert (meta.category, meta.season_int, meta.episode_int) == ("TV", 1, episode)


@pytest.mark.asyncio
@pytest.mark.parametrize("category,is_sports", [("MOVIE", False), ("MOVIE", True), ("SPORTS", False)])
async def test_aither_non_tv_categories_omit_tv_fields(category, is_sports):
    tracker = Aither({"DEFAULT": {}, "TRACKERS": {"AITHER": {}}})
    meta = Meta(category=category, is_sports=is_sports, season_int=1, episode_int=3)

    assert await tracker.get_season_number(meta) == {}
    assert await tracker.get_episode_number(meta) == {}


def _movie(**overrides: object) -> Meta:
    fields: dict[str, object] = {
        "category": "MOVIE",
        "type": "WEBDL",
        "title": "Synthetic Feature",
        "year": 2024,
        "resolution": "1080p",
        "service": "NF",
        "source": "WEB",
        "audio": "DD+ 5.1",
        "video_codec": "AVC",
        "video_encode": "H.264",
        "tag": "-TESTGROUP",
        "audio_languages": ["English"],
        "original_language": "en",
        "language_checked": True,
    }
    fields.update(overrides)
    return Meta(**fields)


def _tv(**overrides: object) -> Meta:
    fields: dict[str, object] = {"category": "TV", "title": "Synthetic Show", "season": "S01", "episode": "", "search_year": ""}
    fields.update(overrides)
    return _movie(**fields)


@pytest.mark.parametrize(
    ("meta", "expected"),
    [
        (_movie(), "Synthetic Feature 2024 1080p NF WEB-DL DD+ 5.1 H.264-TESTGROUP"),
        (
            _movie(type="WEBRIP", video_encode="x264", edition="IMAX", webdv=True, repack="REPACK"),
            "Synthetic Feature 2024 IMAX Hybrid REPACK 1080p NF WEBRip DD+ 5.1 x264-TESTGROUP",
        ),
        (
            _movie(type="ENCODE", source="BluRay", uhd="UHD", resolution="2160p", audio="DTS-HD MA 5.1", hdr="DV HDR", video_encode="x265"),
            "Synthetic Feature 2024 2160p UHD BluRay DTS-HD MA 5.1 DV HDR x265-TESTGROUP",
        ),
        (
            _movie(type="REMUX", source="BluRay", audio="TrueHD 7.1 Atmos", edition="Director's Cut"),
            "Synthetic Feature 2024 Director's Cut 1080p BluRay REMUX AVC TrueHD 7.1 Atmos-TESTGROUP",
        ),
        (
            _movie(type="REMUX", source="BluRay", uhd="UHD", resolution="2160p", hdr="DV HDR", video_codec="HEVC", audio="FLAC 2.0", webdv=True, repack="REPACK2"),
            "Synthetic Feature 2024 Hybrid REPACK2 2160p UHD BluRay REMUX DV HDR HEVC FLAC 2.0-TESTGROUP",
        ),
        (
            _movie(type="REMUX", source="PAL DVD", resolution="576i", video_codec="MPEG-2", audio="DD 2.0"),
            "Synthetic Feature 2024 576i PAL DVD REMUX MPEG-2 DD 2.0-TESTGROUP",
        ),
        (
            _movie(type="DVDRIP", source="NTSC", resolution="480p", audio="DD 1.0", video_encode="x264"),
            "Synthetic Feature 2024 480p DVDRip DD 1.0 x264-TESTGROUP",
        ),
        (
            _movie(type="HDTV", source="HDTV", resolution="720p", audio="AAC 2.0", video_encode="x264"),
            "Synthetic Feature 2024 720p HDTV AAC 2.0 x264-TESTGROUP",
        ),
    ],
)
def test_aither_builds_movie_names(meta: Meta, expected: str) -> None:
    assert _name(meta) == expected


@pytest.mark.parametrize(
    ("meta", "expected"),
    [
        (
            _movie(type="DISC", is_disc="BDMV", source="Blu-ray", region="AUS", audio="DTS-HD MA 5.1"),
            "Synthetic Feature 2024 1080p AUS Blu-ray AVC DTS-HD MA 5.1-TESTGROUP",
        ),
        (
            _movie(type="DISC", is_disc="BDMV", source="Blu-ray", uhd="UHD", resolution="2160p", region="USA", hdr="DV HDR", video_codec="HEVC", audio="TrueHD 7.1 Atmos"),
            "Synthetic Feature 2024 2160p USA UHD Blu-ray DV HDR HEVC TrueHD 7.1 Atmos-TESTGROUP",
        ),
        (
            _movie(type="DISC", is_disc="BDMV", source="Blu-ray", region="CEE", three_d="3D", audio="DTS-HD MA 5.1"),
            "Synthetic Feature 2024 1080p CEE 3D Blu-ray AVC DTS-HD MA 5.1-TESTGROUP",
        ),
        (
            _movie(type="DISC", is_disc="DVD", source="NTSC", resolution="480p", dvd_size="DVD5", edition="Censored", video_codec="MPEG-2", audio="DD 2.0"),
            "Synthetic Feature 2024 Censored 480p NTSC DVD5 MPEG-2 DD 2.0-TESTGROUP",
        ),
        (
            _tv(type="DISC", is_disc="DVD", source="PAL", resolution="576i", region="GBR", dvd_size="DVD9", video_codec="MPEG-2", audio="DD 5.1"),
            "Synthetic Show S01 576i GBR PAL DVD9 MPEG-2 DD 5.1-TESTGROUP",
        ),
        (
            _movie(type="DISC", is_disc="HDDVD", source="HDDVD", video_codec="VC-1", audio="DD+ 5.1", audio_languages=["French"]),
            "Synthetic Feature 2024 1080p HDDVD VC-1 DD+ 5.1-TESTGROUP",
        ),
        (
            _movie(type="DISC", is_disc="BDMV", source="Blu-ray", audio="LPCM 2.0", audio_languages=["French"]),
            "Synthetic Feature 2024 1080p Blu-ray AVC LPCM 2.0-TESTGROUP",
        ),
    ],
)
def test_aither_builds_full_disc_names_without_language(meta: Meta, expected: str) -> None:
    assert _name(meta) == expected


@pytest.mark.parametrize(
    ("meta", "expected"),
    [
        (_tv(), "Synthetic Show S01 1080p NF WEB-DL DD+ 5.1 H.264-TESTGROUP"),
        (_tv(search_year="2021", year=2021, episode="E08"), "Synthetic Show 2021 S01E08 1080p NF WEB-DL DD+ 5.1 H.264-TESTGROUP"),
        (
            _tv(episode="E01", manual_episode_title="Imaginary Storm", audio_languages=["French"], original_language="fr", service="ATVP", resolution="720p"),
            "Synthetic Show S01E01 Imaginary Storm FRENCH 720p ATVP WEB-DL DD+ 5.1 H.264-TESTGROUP",
        ),
        (
            _tv(type="REMUX", source="BluRay", audio="DTS-HD MA 5.1"),
            "Synthetic Show S01 1080p BluRay REMUX AVC DTS-HD MA 5.1-TESTGROUP",
        ),
        (
            _tv(type="DVDRIP", source="PAL", resolution="576p", audio="DD 2.0", video_encode="x264", audio_languages=["French"], original_language="fr"),
            "Synthetic Show S01 FRENCH 576p DVDRip DD 2.0 x264-TESTGROUP",
        ),
        (
            _tv(type="DISC", is_disc="BDMV", source="Blu-ray", region="USA", audio="DTS-HD MA 2.0", search_year="2019", year=2019, season="S02"),
            "Synthetic Show 2019 S02 1080p USA Blu-ray AVC DTS-HD MA 2.0-TESTGROUP",
        ),
        (_tv(manual_date="2024-01-02", daily_episode_title="2024-01-02"), "Synthetic Show 2024-01-02 1080p NF WEB-DL DD+ 5.1 H.264-TESTGROUP"),
    ],
)
def test_aither_builds_tv_names(meta: Meta, expected: str) -> None:
    assert _name(meta) == expected


def test_aither_places_aka_before_movie_year() -> None:
    meta = _movie(aka="AKA Alternate Feature")

    assert _name(meta) == "Synthetic Feature AKA Alternate Feature 2024 1080p NF WEB-DL DD+ 5.1 H.264-TESTGROUP"


def test_aither_places_aka_before_tv_year_and_keeps_space_without_year() -> None:
    assert _name(_tv(aka="AKA Alternate Show", search_year="2024", year=2024)) == "Synthetic Show AKA Alternate Show 2024 S01 1080p NF WEB-DL DD+ 5.1 H.264-TESTGROUP"
    assert _name(_tv(aka="AKA Alternate Show", year=2024)) == "Synthetic Show AKA Alternate Show S01 1080p NF WEB-DL DD+ 5.1 H.264-TESTGROUP"


def test_aither_honors_manual_year_for_tv() -> None:
    assert _name(_tv(manual_year=2015)) == "Synthetic Show 2015 S01 1080p NF WEB-DL DD+ 5.1 H.264-TESTGROUP"


def test_aither_places_language_before_cut() -> None:
    meta = _movie(edition="Extended", repack="REPACK", audio_languages=["Japanese"], original_language="ja")

    assert _name(meta) == "Synthetic Feature 2024 JAPANESE Extended REPACK 1080p NF WEB-DL DD+ 5.1 H.264-TESTGROUP"


@pytest.mark.parametrize("language", ["Multiple", "Multiple languages"])
def test_aither_expands_multiple_audio_language(language: str) -> None:
    meta = _movie(audio_languages=[language])

    assert _name(meta) == "Synthetic Feature 2024 MULTIPLE LANGUAGES 1080p NF WEB-DL DD+ 5.1 H.264-TESTGROUP"


def test_aither_does_not_duplicate_multiple_label_from_edition() -> None:
    meta = _movie(edition="Multiple", audio_languages=["Multiple"])

    assert _name(meta) == "Synthetic Feature 2024 MULTIPLE LANGUAGES 1080p NF WEB-DL DD+ 5.1 H.264-TESTGROUP"


def test_aither_preserves_multiple_in_title_and_release_group() -> None:
    meta = _movie(title="MULTIPLE Synthetic Feature", tag="-MULTIPLE", audio_languages=["Multiple"])

    assert _name(meta) == "MULTIPLE Synthetic Feature 2024 MULTIPLE LANGUAGES 1080p NF WEB-DL DD+ 5.1 H.264-MULTIPLE"


def test_aither_preserves_release_group_when_english_audio_skips_label() -> None:
    assert _name(_movie(tag="-MULTIPLE")) == "Synthetic Feature 2024 1080p NF WEB-DL DD+ 5.1 H.264-MULTIPLE"


@pytest.mark.parametrize("language", ["zxx", "No linguistic content"])
def test_aither_labels_no_spoken_language_as_zxx(language: str) -> None:
    meta = _movie(type="REMUX", source="BluRay", audio="FLAC 2.0", audio_languages=[language])

    assert _name(meta) == "Synthetic Feature 2024 ZXX 1080p BluRay REMUX AVC FLAC 2.0-TESTGROUP"


def test_aither_labels_silent_first_track_as_zxx() -> None:
    meta = _movie(type="REMUX", source="BluRay", audio="FLAC 2.0", audio_languages=["No"], silent=True)

    assert _name(meta) == "Synthetic Feature 2024 ZXX 1080p BluRay REMUX AVC FLAC 2.0-TESTGROUP"


def test_aither_replaces_multi_with_dual_audio_when_english_dub_exists() -> None:
    meta = _movie(type="REMUX", source="BluRay", audio="MULTI DTS-HD MA 5.1", original_language="ja", audio_languages=["Japanese", "English", "French"])

    assert _name(meta) == "Synthetic Feature 2024 1080p BluRay REMUX AVC Dual-Audio DTS-HD MA 5.1-TESTGROUP"


def test_aither_drops_dual_audio_without_english_track() -> None:
    meta = _movie(audio="Dual-Audio AAC 2.0", original_language="ja", audio_languages=["Japanese", "French"])

    assert _name(meta) == "Synthetic Feature 2024 JAPANESE 1080p NF WEB-DL AAC 2.0 H.264-TESTGROUP"


def test_aither_drops_dual_audio_for_english_original() -> None:
    meta = _movie(audio="Dual-Audio DD+ 5.1", audio_languages=["English", "French"])

    assert _name(meta) == "Synthetic Feature 2024 1080p NF WEB-DL DD+ 5.1 H.264-TESTGROUP"


def test_aither_keeps_dubbed_label() -> None:
    meta = _movie(audio="Dubbed AAC 2.0", original_language="ja")

    assert _name(meta) == "Synthetic Feature 2024 1080p NF WEB-DL Dubbed AAC 2.0 H.264-TESTGROUP"


def test_aither_moves_edition_terms_out_of_title_and_keeps_cut() -> None:
    meta = _movie(title="Special Feature", edition="Criterion Director's Cut")

    assert _name(meta) == "Special Feature 2024 Director's Cut 1080p NF WEB-DL DD+ 5.1 H.264-TESTGROUP"


def test_aither_keeps_special_edition_as_a_cut() -> None:
    meta = _movie(edition="Special Edition Remastered")

    assert _name(meta) == "Synthetic Feature 2024 Special Edition 1080p NF WEB-DL DD+ 5.1 H.264-TESTGROUP"


def test_aither_removes_edition_only_title_slot() -> None:
    meta = _movie(edition="25th Anniversary Remastered")

    assert _name(meta) == "Synthetic Feature 2024 1080p NF WEB-DL DD+ 5.1 H.264-TESTGROUP"


def test_aither_uses_manual_name_verbatim() -> None:
    meta = _movie(manual_name="Custom Name 2024 1080p WEB-DL", name="Custom Name 2024 1080p WEB-DL", audio_languages=["French"])

    assert _name(meta) == "Custom Name 2024 1080p WEB-DL"


def test_aither_falls_back_to_generic_name_for_unknown_type() -> None:
    meta = _movie(type="", name="Synthetic Feature 2024 Generic Name")

    assert _name(meta) == "Synthetic Feature 2024 Generic Name"


def test_aither_appends_trump_marker() -> None:
    assert _name(_movie(trump_reason="exact_match")) == "Synthetic Feature 2024 1080p NF WEB-DL DD+ 5.1 H.264-TESTGROUP - TRUMP"


@pytest.mark.parametrize(("is_disc", "checked"), [("BDMV", False), ("DVD", False), ("HDDVD", True), ("", True)])
def test_aither_language_requirement_exempts_only_bdmv_and_dvd(monkeypatch: pytest.MonkeyPatch, is_disc: str, checked: bool) -> None:
    tracker = Aither({"DEFAULT": {}, "TRACKERS": {"AITHER": {}}})
    calls: list[str] = []

    async def language_check(*_args: object, **_kwargs: object) -> bool:
        calls.append(is_disc)
        return False

    monkeypatch.setattr(tracker.common, "check_language_requirements", language_check)

    passed = asyncio.run(tracker.get_additional_checks(Meta(is_disc=is_disc, valid_mi=True)))

    assert bool(calls) is checked
    assert passed is not checked
