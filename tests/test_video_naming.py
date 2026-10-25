# ruff: noqa: S101
import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.meta import Meta
from src.trackers.naming import BLU_NAME_RULES, TMDB_HOMONYM_MAX_PAGES, VideoNameRules, build_video_name, tmdb_tv_title_has_homonym
from src.trackers.UNIT3D.blutopia import Blutopia
from src.trackers.UNIT3D.lst import LST
from src.trackers.UNIT3D.oldtoonsworld import OldToonsWorld
from src.trackers.UNIT3D.ulcx import ULCX


def _meta(**overrides: object) -> Meta:
    fields: dict[str, object] = {
        "category": "MOVIE",
        "type": "WEBDL",
        "title": "Synthetic Feature",
        "year": 2024,
        "resolution": "1080p",
        "service": "AMZN",
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


def _build(meta: Meta, rules: VideoNameRules = BLU_NAME_RULES) -> str:
    return asyncio.run(build_video_name(meta, rules, "TEST"))


def _tracker_name(tracker_class: type, meta: Meta) -> str:
    config = {"DEFAULT": {}, "TRACKERS": {tracker_class.__name__.upper(): {}}}
    return asyncio.run(tracker_class(config).get_name(meta))["name"]


@pytest.mark.parametrize(
    ("meta", "expected"),
    [
        (
            _meta(
                type="DISC",
                is_disc="BDMV",
                source="Blu-ray",
                uhd="UHD",
                resolution="2160p",
                region="USA",
                hdr="DV HDR",
                video_codec="HEVC",
                audio="TrueHD 7.1 Atmos",
                edition="Extended",
            ),
            "Synthetic Feature 2024 Extended 2160p USA UHD Blu-ray DV HDR HEVC TrueHD 7.1 Atmos-TESTGROUP",
        ),
        (
            _meta(
                type="DISC",
                is_disc="BDMV",
                source="Blu-ray",
                region="USA",
                audio="TrueHD 7.1 Atmos",
                category="TV",
                title="Synthetic Show",
                season="S01",
                episode="",
                edition="Criterion",
            ),
            "Synthetic Show S01 1080p USA Blu-ray AVC TrueHD 7.1 Atmos-TESTGROUP",
        ),
        (
            _meta(type="REMUX", source="BluRay", uhd="UHD", resolution="2160p", hdr="DV HDR", video_codec="HEVC", audio="TrueHD 7.1 Atmos"),
            "Synthetic Feature 2024 2160p UHD BluRay REMUX DV HDR HEVC TrueHD 7.1 Atmos-TESTGROUP",
        ),
        (
            _meta(type="REMUX", source="BluRay", three_d="3D", audio="DTS-HD MA 5.1"),
            "Synthetic Feature 2024 1080p 3D BluRay REMUX AVC DTS-HD MA 5.1-TESTGROUP",
        ),
        (
            _meta(type="REMUX", source="NTSC DVD", resolution="480i", video_codec="MPEG-2", audio="DD 5.1"),
            "Synthetic Feature 2024 NTSC DVD REMUX DD 5.1-TESTGROUP",
        ),
        (
            _meta(type="DISC", is_disc="DVD", source="NTSC", region="USA", dvd_size="DVD9", resolution="480i", audio="DD 5.1"),
            "Synthetic Feature 2024 USA NTSC DVD9 DD 5.1-TESTGROUP",
        ),
        (
            _meta(type="ENCODE", source="BluRay", uhd="UHD", audio="DD+ 7.1", hdr="HDR", video_encode="x265"),
            "Synthetic Feature 2024 1080p UHD BluRay DD+ 7.1 HDR x265-TESTGROUP",
        ),
        (
            _meta(type="ENCODE", source="BluRay", audio="Dual-Audio FLAC 2.0", video_encode="Hi10P x264", original_language="ja", audio_languages=["Japanese", "English"]),
            "Synthetic Feature 2024 1080p BluRay Dual-Audio FLAC 2.0 Hi10P x264-TESTGROUP",
        ),
        (
            _meta(type="DVDRIP", source="NTSC", resolution="480p", audio="DD 5.1", video_encode="x264"),
            "Synthetic Feature 2024 DVDRip DD 5.1 x264-TESTGROUP",
        ),
        (
            _meta(
                category="TV",
                title="Synthetic Show",
                season="S01",
                episode="E10",
                search_year="2024",
                resolution="2160p",
                service="PMTP",
                hdr="DV HDR10+",
                video_encode="H.265",
            ),
            "Synthetic Show 2024 S01E10 2160p PMTP WEB-DL DD+ 5.1 DV HDR10+ H.265-TESTGROUP",
        ),
        (
            _meta(
                type="WEBRIP",
                service="NF",
                aka="AKA La Sintetica",
                audio="Dual-Audio DD+ 5.1",
                video_encode="x264",
                original_language="es",
                audio_languages=["Spanish", "English"],
            ),
            "Synthetic Feature AKA La Sintetica 2024 1080p NF WEBRip Dual-Audio DD+ 5.1 x264-TESTGROUP",
        ),
    ],
)
def test_blu_rules_follow_template(meta: Meta, expected: str) -> None:
    assert _build(meta) == expected


def test_blu_rules_keep_cut_and_drop_edition_outside_discs() -> None:
    meta = _meta(type="ENCODE", source="BluRay", edition="Director's Cut 25th Anniversary Edition", video_encode="x264")

    assert _build(meta) == "Synthetic Feature 2024 Director's Cut 1080p BluRay DD+ 5.1 x264-TESTGROUP"


def test_blu_rules_keep_editions_out_of_full_disc_titles() -> None:
    meta = _meta(type="DISC", is_disc="BDMV", source="Blu-ray", region="GBR", edition="Extended 25th Anniversary Remastered", audio="DTS-HD MA 5.1")

    assert _build(meta) == "Synthetic Feature 2024 Extended 1080p GBR Blu-ray AVC DTS-HD MA 5.1-TESTGROUP"


@pytest.mark.parametrize("system", ["NTSC", "PAL"])
def test_dvd_sourced_encode_is_titled_dvdrip(system: str) -> None:
    meta = _meta(type="ENCODE", source=system, resolution="480p", audio="DD 1.0", video_encode="x264")

    assert _build(meta) == "Synthetic Feature 2024 DVDRip DD 1.0 x264-TESTGROUP"
    assert _build(meta, VideoNameRules(dvd_resolution=True)) == "Synthetic Feature 2024 480p DVDRip DD 1.0 x264-TESTGROUP"


def test_blu_rules_fold_multi_into_dual_audio_and_drop_non_english_dual() -> None:
    multi = _meta(audio="MULTI DD+ 5.1", original_language="ja", audio_languages=["Japanese", "English", "French"])
    no_english = _meta(audio="Dual-Audio DD+ 5.1", original_language="ja", audio_languages=["Japanese", "French"])

    assert _build(multi) == "Synthetic Feature 2024 1080p AMZN WEB-DL Dual-Audio DD+ 5.1 H.264-TESTGROUP"
    assert _build(no_english) == "Synthetic Feature 2024 1080p AMZN WEB-DL DD+ 5.1 H.264-TESTGROUP"


def test_build_video_name_defers_manual_names_and_other_categories() -> None:
    assert _build(_meta(manual_name="Custom Name")) == ""
    assert _build(_meta(category="MUSIC")) == ""
    assert _build(_meta(type="")) == ""


def test_language_slot_before_resolution() -> None:
    rules = VideoNameRules(language_slot="before_resolution")
    meta = _meta(edition="Extended", repack="REPACK", audio_languages=["French"], original_language="fr")

    assert _build(meta, rules) == "Synthetic Feature 2024 Extended REPACK FRENCH 1080p AMZN WEB-DL DD+ 5.1 H.264-TESTGROUP"


def test_blutopia_uses_imdb_title_aka_and_year() -> None:
    meta = _meta(type="ENCODE", source="BluRay", video_encode="x264", aka="AKA Tmdb Alternate", imdb_info={"title": "Imdb Feature", "aka": "Imdb Original", "year": 2023})

    assert _tracker_name(Blutopia, meta) == "Imdb Feature AKA Imdb Original 2023 1080p BluRay DD+ 5.1 x264-TESTGROUP"


def test_blutopia_drops_manual_episode_title_and_marks_dvp() -> None:
    meta = _meta(
        category="TV",
        title="Synthetic Show",
        season="S01",
        episode="E02",
        search_year="",
        manual_episode_title="Imaginary Episode",
        episode_title="Imaginary Episode",
        tracker_status={"BLUTOPIA": {"other": True}},
    )

    assert _tracker_name(Blutopia, meta) == "Synthetic Show S01E02 1080p DVP5/DVP8 AMZN WEB-DL DD+ 5.1 H.264-TESTGROUP"


def test_ulcx_omits_hybrid_for_webdl_and_aka_for_anime() -> None:
    meta = _meta(webdv=True, anime=True, imdb_info={"title": "Synthetic Feature", "aka": "Gensaku Taitoru", "year": 2024})

    assert _tracker_name(ULCX, meta) == "Synthetic Feature 2024 1080p AMZN WEB-DL DD+ 5.1 H.264-TESTGROUP"


def test_ulcx_keeps_hybrid_for_remux() -> None:
    meta = _meta(type="REMUX", source="BluRay", webdv=True, audio="TrueHD 7.1 Atmos")

    assert _tracker_name(ULCX, meta) == "Synthetic Feature 2024 Hybrid 1080p BluRay REMUX AVC TrueHD 7.1 Atmos-TESTGROUP"


def test_lst_formats_dvdrip_and_drops_disc_editions() -> None:
    dvdrip = _meta(type="DVDRIP", source="NTSC", resolution="480p", audio="DD 5.1", video_encode="x264")
    disc = _meta(type="DISC", is_disc="BDMV", source="Blu-ray", region="USA", edition="Criterion", audio="LPCM 1.0")

    assert _tracker_name(LST, dvdrip) == "Synthetic Feature 2024 DVDRip DD 5.1 x264-TESTGROUP"
    assert _tracker_name(LST, disc) == "Synthetic Feature 2024 1080p USA Blu-ray AVC LPCM 1.0-TESTGROUP"


def test_lst_appends_trump_marker() -> None:
    assert _tracker_name(LST, _meta(trump_reason="exact_match")) == "Synthetic Feature 2024 1080p AMZN WEB-DL DD+ 5.1 H.264-TESTGROUP - TRUMP"


@pytest.mark.parametrize(
    ("meta", "expected"),
    [
        (
            _meta(category="TV", title="Synthetic Toon", year=2005, season="S01", episode="E01", search_year="", service="DSNP"),
            "Synthetic Toon 2005 S01E01 1080p DSNP WEB-DL DD+ 5.1 H.264-TESTGROUP",
        ),
        (
            _meta(type="DVDRIP", title="Synthetic Toon II", year=2002, source="NTSC", resolution="480p", audio="AAC 2.0", video_encode="x264"),
            "Synthetic Toon II 2002 480p DVDRip AAC 2.0 x264-TESTGROUP",
        ),
        (
            _meta(
                type="DISC",
                is_disc="DVD",
                category="TV",
                title="Synthetic Toon",
                year=1982,
                season="S01",
                episode="",
                search_year="",
                source="NTSC",
                region="USA",
                dvd_size="DVD9",
                resolution="480p",
                video_codec="MPEG-2",
                audio="DD 2.0",
                tag="",
            ),
            "Synthetic Toon 1982 S01 480p USA NTSC DVD9 MPEG-2 DD 2.0",
        ),
        (
            _meta(aka="AKA Gensaku Toon", audio="Dual-Audio AAC 2.0", original_language="ja", audio_languages=["Japanese", "English"]),
            "Synthetic Feature 2024 1080p AMZN WEB-DL Dual Audio AAC 2.0 H.264-TESTGROUP",
        ),
        (
            _meta(audio="MULTI AAC 2.0", original_language="ja", audio_languages=["Japanese", "English", "French"]),
            "Synthetic Feature 2024 1080p AMZN WEB-DL MULTI AAC 2.0 H.264-TESTGROUP",
        ),
    ],
)
def test_oldtoons_follows_its_guide(meta: Meta, expected: str) -> None:
    assert _tracker_name(OldToonsWorld, meta) == expected


@pytest.mark.parametrize("edition", ["Hybrid", "hybrid Extended", "Extended HYBRID"])
def test_hybrid_in_edition_appears_once(edition: str) -> None:
    meta = _meta(type="REMUX", source="BluRay", webdv=True, edition=edition, audio="TrueHD 7.1 Atmos")
    cut = "Extended " if "Extended" in edition else ""

    assert _build(meta) == f"Synthetic Feature 2024 {cut}Hybrid 1080p BluRay REMUX AVC TrueHD 7.1 Atmos-TESTGROUP"


def test_missing_manual_year_keeps_component_year() -> None:
    meta = _meta(manual_year=None)

    assert _build(meta, VideoNameRules(honor_manual_year_on_tv=True)) == "Synthetic Feature 2024 1080p AMZN WEB-DL DD+ 5.1 H.264-TESTGROUP"


def test_ulcx_omits_aka_for_anime_without_imdb_title() -> None:
    meta = _meta(anime=True, aka="AKA Gensaku Taitoru")

    assert _tracker_name(ULCX, meta) == "Synthetic Feature 2024 1080p AMZN WEB-DL DD+ 5.1 H.264-TESTGROUP"


def _show(**overrides: object) -> Meta:
    fields: dict[str, object] = {"category": "TV", "title": "Synthetic Show", "year": 2019, "season": "S01", "episode": "", "search_year": ""}
    fields.update(overrides)
    return _meta(**fields)


@pytest.mark.parametrize(
    ("episode_data", "search_year", "expected_year"),
    [
        # TVDB disambiguates with a year that can differ from the first-aired year.
        ({"series_name": "Synthetic Show (2017)"}, "", "2017 "),
        ({"series_name": "SYNTHETIC SHOW (2017)", "series_title": "Synthetic Show"}, "", "2017 "),
        ({"series_name": "Synthetic Show", "series_title": "Synthetic Show (2017)"}, "", "2017 "),
        # A TVDB name without a year drops a year taken from the filename.
        ({"series_name": "Synthetic Show"}, "2019", ""),
        # Without TVDB data or a TMDB answer the filename decides, as before.
        ({}, "2019", "2019 "),
        ({}, "", ""),
    ],
)
def test_tv_year_follows_tvdb_title(episode_data: dict[str, str], search_year: str, expected_year: str) -> None:
    meta = _show(tvdb_episode_data=episode_data, search_year=search_year)

    assert _build(meta) == f"Synthetic Show {expected_year}S01 1080p AMZN WEB-DL DD+ 5.1 H.264-TESTGROUP"


@pytest.mark.parametrize(
    ("has_homonym", "search_year", "expected_year"),
    [
        # Without a TVDB name, TMDB decides whether another show needs the year.
        (False, "2019", ""),
        (True, "", "2019 "),
        (True, "2019", "2019 "),
        # TMDB could not answer: the filename decides.
        (None, "2019", "2019 "),
        (None, "", ""),
    ],
)
def test_tv_year_falls_back_to_tmdb_homonyms(has_homonym: bool | None, search_year: str, expected_year: str) -> None:
    meta = _show(tvdb_episode_data={}, search_year=search_year)

    with patch("src.trackers.naming.tmdb_tv_title_has_homonym", new=AsyncMock(return_value=has_homonym)) as check:
        assert _build(meta) == f"Synthetic Show {expected_year}S01 1080p AMZN WEB-DL DD+ 5.1 H.264-TESTGROUP"

    assert check.await_args is not None
    assert check.await_args.args[1] == "Synthetic Show"


def _tmdb_pages(*pages: list[dict[str, object]], total_pages: int | None = None) -> AsyncMock:
    responses = []
    for results in pages:
        response = Mock()
        response.json.return_value = {"results": results, "total_pages": total_pages or len(pages)}
        responses.append(response)
    return AsyncMock(side_effect=responses)


def _homonym(get: AsyncMock) -> bool | None:
    meta = _show(tmdb_id=101)
    with patch("src.trackers.naming.httpx.AsyncClient.get", new=get):
        return asyncio.run(tmdb_tv_title_has_homonym(meta, "Synthetic Show", "test-key", "TEST"))


def test_tmdb_homonym_check_reads_later_pages() -> None:
    other = {"id": 202, "name": "Synthetic Show"}
    get = _tmdb_pages([{"id": 101, "name": "Synthetic Show"}], [other], [{"id": 303, "name": "Unrelated"}])

    assert _homonym(get) is True
    assert get.await_count == 2


def test_tmdb_homonym_check_without_match_on_every_page_is_false() -> None:
    get = _tmdb_pages([{"id": 101, "name": "Synthetic Show"}], [{"id": 202, "name": "Synthetic Show Revival"}])

    assert _homonym(get) is False


def test_tmdb_homonym_check_is_inconclusive_past_the_page_limit() -> None:
    pages = [[{"id": 900 + page, "name": "Unrelated"}] for page in range(TMDB_HOMONYM_MAX_PAGES)]
    get = _tmdb_pages(*pages, total_pages=TMDB_HOMONYM_MAX_PAGES + 1)

    assert _homonym(get) is None
    assert get.await_count == TMDB_HOMONYM_MAX_PAGES


def test_tmdb_homonym_check_skipped_when_tvdb_or_manual_year_decides() -> None:
    tvdb = _show(tvdb_episode_data={"series_name": "Synthetic Show"}, search_year="2019")
    manual = _show(tvdb_episode_data={}, manual_year=2015)

    with patch("src.trackers.naming.tmdb_tv_title_has_homonym", new=AsyncMock(return_value=True)) as check:
        assert _build(tvdb) == "Synthetic Show S01 1080p AMZN WEB-DL DD+ 5.1 H.264-TESTGROUP"
        assert _build(manual, VideoNameRules(honor_manual_year_on_tv=True)) == "Synthetic Show 2015 S01 1080p AMZN WEB-DL DD+ 5.1 H.264-TESTGROUP"

    check.assert_not_awaited()


def test_tvdb_year_respects_no_year_and_manual_year() -> None:
    no_year = _show(tvdb_episode_data={"series_name": "Synthetic Show (2017)"}, no_year=True)
    manual = _show(tvdb_episode_data={"series_name": "Synthetic Show"}, manual_year=2015)

    assert _build(no_year) == "Synthetic Show S01 1080p AMZN WEB-DL DD+ 5.1 H.264-TESTGROUP"
    assert _build(manual, VideoNameRules(honor_manual_year_on_tv=True)) == "Synthetic Show 2015 S01 1080p AMZN WEB-DL DD+ 5.1 H.264-TESTGROUP"


def test_oldtoons_keeps_debut_year_instead_of_tvdb_title_year() -> None:
    meta = _show(title="Synthetic Toon", year=2005, tvdb_episode_data={"series_name": "Synthetic Toon"}, service="DSNP")

    assert _tracker_name(OldToonsWorld, meta) == "Synthetic Toon 2005 S01 1080p DSNP WEB-DL DD+ 5.1 H.264-TESTGROUP"
