import asyncio

import pytest

from src.meta import _TRACKER_ID_ALIASES, Meta
from src.trackers.UNIT3D.dreadvault import DreadVault
from src.trackersetup import TrackerSetup, tracker_class_map


def _tracker() -> DreadVault:
    return DreadVault({"TRACKERS": {"DREADVAULT": {"api_key": ""}}})


def test_dreadvault_is_registered_with_full_tracker_name():
    assert tracker_class_map["DREADVAULT"] is DreadVault  # noqa: S101
    assert DreadVault.display_name == "DreadVault"  # noqa: S101
    assert DreadVault.supported_categories == ("TV", "MOVIE")  # noqa: S101


def test_dreadvault_dvl_alias_resolves_to_the_canonical_name():
    # DVL is the site's own abbreviation, confirmed by DreadVault staff.
    assert _TRACKER_ID_ALIASES["DVL"] == "DREADVAULT"  # noqa: S101
    assert Meta().canonical_tracker_name("dvl") == "DREADVAULT"  # noqa: S101


def test_dreadvault_dvl_cli_alias_is_canonicalized_before_tracker_checks():
    meta = Meta(category="MOVIE", trackers=["DVL"])
    setup = TrackerSetup({"TRACKERS": {"DREADVAULT": {"api_key": "test-token"}}})

    setup.filter_unsupported_trackers(meta)

    assert meta.trackers == ["DREADVAULT"]  # noqa: S101


def test_dreadvault_bans_the_published_groups():
    # Published on the site's rules page 2026-08-24, extended 2026-09-06; DreadVault exposes no
    # /api/bannedReleaseGroups endpoint, so this list is maintained by hand.
    assert set(DreadVault.banned_groups) == {  # noqa: S101
        "AOC",
        "AOS",
        "BONE",
        "EVO",
        "FGT",
        "LAMA",
        "NeoNoir",
        "PSA",
        "RARBG",
        "VXT",
        "YIFY",
        "YTS",
    }


@pytest.mark.parametrize(
    "combined_genres",
    [
        "Horror",
        "Horror, Thriller",
        "Horror, Mystery, Thriller",
        "Thriller, Horror",
        ["Horror"],
        ["Horror", "Thriller"],
    ],
)
def test_dreadvault_accepts_horror_regardless_of_genre_order(combined_genres):
    tracker = _tracker()
    meta = Meta(combined_genres=combined_genres, unattended=True)
    assert asyncio.run(tracker.get_additional_checks(meta))  # noqa: S101


def test_dreadvault_accepts_horror_from_keywords():
    tracker = _tracker()
    meta = Meta(combined_genres="", keywords=["horror"], unattended=True)
    assert asyncio.run(tracker.get_additional_checks(meta))  # noqa: S101


def test_dreadvault_accepts_horror_inside_a_compound_keyword():
    tracker = _tracker()
    meta = Meta(combined_genres="Drama, Thriller", keywords=["psychological horror"], unattended=True)
    assert asyncio.run(tracker.get_additional_checks(meta))  # noqa: S101


def test_dreadvault_accepts_horror_with_incidental_mature_keywords():
    tracker = _tracker()
    meta = Meta(combined_genres="Horror, Thriller", keywords=["adult animation", "orgy", "erotic"], unattended=True)
    assert asyncio.run(tracker.get_additional_checks(meta))  # noqa: S101


def test_dreadvault_rejects_non_horror_when_unattended():
    tracker = _tracker()
    meta = Meta(combined_genres="Action, Comedy", unattended=True)
    assert not asyncio.run(tracker.get_additional_checks(meta))  # noqa: S101


def test_dreadvault_only_blocks_exact_duplicates():
    assert DreadVault.exact_match_only is True  # noqa: S101


def test_dreadvault_adult_keyword_skips_when_unattended():
    tracker = _tracker()
    meta = Meta(combined_genres="Horror", keywords=["porn"], unattended=True)
    assert not asyncio.run(tracker.get_additional_checks(meta))  # noqa: S101


def test_dreadvault_rejects_adult_content():
    tracker = _tracker()
    meta = Meta(combined_genres="Horror", keywords=["porn"], unattended=True)
    assert not asyncio.run(tracker.get_additional_checks(meta))  # noqa: S101


def test_dreadvault_formats_dvdrip_with_resolution_and_encode_after_audio():
    meta = Meta(
        name="Example Movie 2001 PAL DVD x264 DVDRip DD 2.0-GRP",
        type="DVDRIP",
        source="PAL DVD",
        resolution="480p",
        video_encode=" x264",
        audio="DD 2.0",
        language_checked=True,
    )

    name = asyncio.run(_tracker().get_name(meta))["name"]

    assert name == "Example Movie 2001 480p DVDRip DD 2.0 x264-GRP"  # noqa: S101


def test_dreadvault_formats_hi10p_dvdrip_with_encode_after_audio():
    meta = Meta(
        name="Example Movie 2001 PAL DVD Hi10P x264 DVDRip DD 2.0-GRP",
        type="DVDRIP",
        source="PAL DVD",
        resolution="480p",
        video_encode="Hi10P x264",
        audio="DD 2.0",
        language_checked=True,
    )

    name = asyncio.run(_tracker().get_name(meta))["name"]

    assert name == "Example Movie 2001 480p DVDRip DD 2.0 Hi10P x264-GRP"  # noqa: S101


def test_dreadvault_formats_dvd_disc_with_resolution_codec_region_and_source():
    meta = Meta(
        name="Example Movie 2001 R1 NTSC DVD DVD9 DD 5.1-GRP",
        type="DISC",
        is_disc="DVD",
        source="NTSC DVD",
        resolution="480p",
        region="R1",
        video_codec="MPEG-2",
        audio="DD 5.1",
        language_checked=True,
    )

    name = asyncio.run(_tracker().get_name(meta))["name"]

    assert name == "Example Movie 2001 480p R1 NTSC DVD DVD9 MPEG-2 DD 5.1-GRP"  # noqa: S101


def test_dreadvault_formats_dvd_remux_with_resolution_before_source():
    meta = Meta(
        name="Example Movie 2001 PAL DVD REMUX DD 5.1-GRP",
        type="REMUX",
        source="PAL DVD",
        resolution="576p",
        video_codec="MPEG-2",
        audio="DD 5.1",
        language_checked=True,
    )

    name = asyncio.run(_tracker().get_name(meta))["name"]

    assert name == "Example Movie 2001 576p PAL DVD REMUX MPEG-2 DD 5.1-GRP"  # noqa: S101


def test_dreadvault_adds_foreign_audio_language_before_encode_resolution():
    meta = Meta(
        name="Example Movie 2001 1080p BluRay DD 5.1 x264-GRP",
        type="ENCODE",
        source="BluRay",
        resolution="1080p",
        audio_languages=["Japanese"],
        language_checked=True,
    )

    name = asyncio.run(_tracker().get_name(meta))["name"]

    assert name == "Example Movie 2001 JAPANESE 1080p BluRay DD 5.1 x264-GRP"  # noqa: S101


def test_dreadvault_adds_foreign_audio_language_before_source_when_resolution_is_other():
    meta = Meta(
        name="Example Movie 2001 BluRay DD 5.1 x264-GRP",
        type="ENCODE",
        source="BluRay",
        resolution="OTHER",
        audio_languages=["Japanese"],
        language_checked=True,
    )

    name = asyncio.run(_tracker().get_name(meta))["name"]

    assert name == "Example Movie 2001 JAPANESE BluRay DD 5.1 x264-GRP"  # noqa: S101


def test_dreadvault_adds_foreign_audio_language_before_service_when_resolution_is_other():
    meta = Meta(
        name="Example Movie 2001 AMZN WEB-DL DD 5.1 H.264-GRP",
        type="WEBDL",
        source="Web",
        resolution="OTHER",
        service="AMZN",
        audio_languages=["Japanese"],
        language_checked=True,
    )

    name = asyncio.run(_tracker().get_name(meta))["name"]

    assert name == "Example Movie 2001 JAPANESE AMZN WEB-DL DD 5.1 H.264-GRP"  # noqa: S101


def test_dreadvault_omits_foreign_audio_language_from_bdmv_disc():
    meta = Meta(
        name="Example Movie 2001 1080p BluRay AVC DD 5.1-GRP",
        type="DISC",
        is_disc="BDMV",
        source="BluRay",
        resolution="1080p",
        audio_languages=["Japanese"],
        language_checked=True,
    )

    name = asyncio.run(_tracker().get_name(meta))["name"]

    assert name == "Example Movie 2001 1080p BluRay AVC DD 5.1-GRP"  # noqa: S101


def test_dreadvault_omits_language_marker_when_audio_includes_english():
    meta = Meta(
        name="Example Movie 2001 1080p BluRay DD 5.1 x264-GRP",
        type="ENCODE",
        source="BluRay",
        resolution="1080p",
        audio_languages=["Japanese", "English"],
        language_checked=True,
    )

    name = asyncio.run(_tracker().get_name(meta))["name"]

    assert name == "Example Movie 2001 1080p BluRay DD 5.1 x264-GRP"  # noqa: S101


def test_dreadvault_adds_foreign_audio_language_to_a_dvdrip():
    # The DVDRip template carries no resolution of its own, so a language pass that ran before the
    # DVDRip branch had nothing to anchor to and dropped the marker (kainoa 2026-09-09).
    meta = Meta(
        name="Suicide Dolls 1999 NTSC DVD x264 DVDRip DD 2.0-GVXXI",
        type="DVDRIP",
        source="NTSC DVD",
        resolution="480p",
        audio="DD 2.0",
        video_encode=" x264",
        audio_languages=["Japanese"],
        language_checked=True,
    )

    name = asyncio.run(_tracker().get_name(meta))["name"]

    assert name == "Suicide Dolls 1999 JAPANESE 480p DVDRip DD 2.0 x264-GVXXI"  # noqa: S101


def test_dreadvault_adds_foreign_audio_language_to_a_dvd_full_disc():
    meta = Meta(
        name="Hausu 1977 USA NTSC DVD DVD9 LPCM 2.0",
        year=1977,
        type="DISC",
        is_disc="DVD",
        source="NTSC DVD",
        resolution="480p",
        region="USA",
        video_codec="MPEG-2",
        audio="LPCM 2.0",
        audio_languages=["Japanese"],
        language_checked=True,
    )

    name = asyncio.run(_tracker().get_name(meta))["name"]

    assert name.startswith("Hausu 1977 JAPANESE 480p USA NTSC DVD")  # noqa: S101


def test_dreadvault_adds_foreign_audio_language_after_year_for_dvd_remux():
    meta = Meta(
        name="Example Movie 2001 PAL DVD REMUX DD 5.1-GRP",
        year=2001,
        type="REMUX",
        source="PAL DVD",
        resolution="576p",
        video_codec="MPEG-2",
        audio="DD 5.1",
        audio_languages=["Japanese"],
        language_checked=True,
    )

    name = asyncio.run(_tracker().get_name(meta))["name"]

    assert name == "Example Movie 2001 JAPANESE 576p PAL DVD REMUX MPEG-2 DD 5.1-GRP"  # noqa: S101


def test_dreadvault_adds_foreign_audio_language_before_resolution_for_yearless_dvd_remux():
    meta = Meta(
        name="Example Movie PAL DVD REMUX DD 2.0-GRP",
        no_year=True,
        type="REMUX",
        source="PAL DVD",
        resolution="576p",
        video_codec="MPEG-2",
        audio="DD 2.0",
        audio_languages=["Japanese"],
        language_checked=True,
    )

    name = asyncio.run(_tracker().get_name(meta))["name"]

    assert name == "Example Movie JAPANESE 576p PAL DVD REMUX MPEG-2 DD 2.0-GRP"  # noqa: S101


def test_dreadvault_never_adds_trump_suffix_for_exact_match():
    meta = Meta(
        name="Example Movie 2001 1080p BluRay DD 5.1 x264-GRP",
        trump_reason="exact_match",
        language_checked=True,
    )

    name = asyncio.run(_tracker().get_name(meta))["name"]

    assert not name.endswith("- TRUMP")  # noqa: S101


def test_dreadvault_moves_tv_aka_before_year():
    meta = Meta(
        category="TV",
        year=2024,
        search_year=2024,
        name="Example Show 2024 AKA Alternate Show S01 1080p WEB-DL",
        aka="AKA Alternate Show",
        language_checked=True,
    )

    name = asyncio.run(_tracker().get_name(meta))["name"]

    assert name == "Example Show AKA Alternate Show 2024 S01 1080p WEB-DL"  # noqa: S101


def test_dreadvault_moves_tv_aka_before_year_with_foreign_audio_language():
    meta = Meta(
        category="TV",
        year=2024,
        search_year=2024,
        name="Example Show 2024 AKA Alt Show S01 PAL DVD REMUX DD 2.0-GRP",
        aka="AKA Alt Show",
        type="REMUX",
        source="PAL DVD",
        resolution="576p",
        video_codec="MPEG-2",
        audio="DD 2.0",
        audio_languages=["Japanese"],
        language_checked=True,
    )

    name = asyncio.run(_tracker().get_name(meta))["name"]

    assert name == "Example Show AKA Alt Show 2024 JAPANESE S01 576p PAL DVD REMUX MPEG-2 DD 2.0-GRP"  # noqa: S101
