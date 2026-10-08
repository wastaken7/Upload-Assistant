import asyncio

import langcodes
import pytest

from src.audio import AudioManager
from src.get_name import NameManager
from src.languages import LanguagesManager
from src.meta import _TRACKER_ID_ALIASES, Meta
from src.trackers.UNIT3D.dreadvault import DreadVault
from src.trackersetup import TrackerSetup, tracker_class_map
from src.video import VideoManager


def _tracker() -> DreadVault:
    return DreadVault({"TRACKERS": {"DREADVAULT": {"api_key": ""}}})


def _build_name(meta: Meta) -> str:
    return asyncio.run(NameManager({}).get_name(meta))[1]


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


@pytest.mark.parametrize("title", ["The x264 Experiment", "The NTSC Experiment", "The DVDRip Murders"])
def test_dreadvault_preserves_movie_dvdrip_title_tokens(title):
    meta = Meta(
        title=title,
        year=2001,
        category="MOVIE",
        type="DVDRIP",
        source="NTSC",
        resolution="480p",
        video_encode=" x264",
        audio="DD 2.0",
        tag="-GRP",
        language_checked=True,
    )
    meta.name = _build_name(meta)
    assert meta.name == f"{title} 2001 NTSC x264 DVDRip DD 2.0-GRP"  # noqa: S101

    name = asyncio.run(_tracker().get_name(meta))["name"]

    assert name == f"{title} 2001 480p DVDRip DD 2.0 x264-GRP"  # noqa: S101


@pytest.mark.parametrize("title", ["The x264 Experiment", "The DD 2.0 Experiment"])
def test_dreadvault_preserves_tv_dvdrip_title_tokens_and_encode_position(title):
    meta = Meta(
        title=title,
        year=2001,
        search_year=2001,
        category="TV",
        season="S01",
        type="DVDRIP",
        source="NTSC",
        resolution="480p",
        video_encode=" x264",
        audio="DD 2.0",
        tag="-GRP",
        language_checked=True,
    )
    meta.name = _build_name(meta)
    assert meta.name == f"{title} 2001 S01 NTSC DVDRip DD 2.0 x264-GRP"  # noqa: S101

    name = asyncio.run(_tracker().get_name(meta))["name"]

    assert name == f"{title} 2001 S01 480p DVDRip DD 2.0 x264-GRP"  # noqa: S101


def test_dreadvault_leaves_a_preformatted_dvdrip_name_unchanged():
    meta = Meta(
        manual_name="Example 2001 480p DVDRip DD 2.0 x264-GRP",
        category="MOVIE",
        type="DVDRIP",
        source="NTSC",
        resolution="480p",
        video_encode=" x264",
        audio="DD 2.0",
        language_checked=True,
    )
    meta.name = _build_name(meta)
    assert meta.name == meta.manual_name  # noqa: S101

    name = asyncio.run(_tracker().get_name(meta))["name"]

    assert name == meta.name  # noqa: S101


@pytest.mark.parametrize(
    ("source", "original_name"),
    [
        ("PAL DVD", "Example Movie 2001 PAL DVD x264 DVDRip-GRP"),
        ("", "Example Movie 2001 x264 DVDRip-GRP"),
    ],
)
def test_dreadvault_formats_dvdrip_with_empty_audio(source, original_name):
    meta = Meta(
        name=original_name,
        type="DVDRIP",
        source=source,
        resolution="480p",
        video_encode=" x264",
        audio="",
        language_checked=True,
    )

    name = asyncio.run(_tracker().get_name(meta))["name"]

    assert name == "Example Movie 2001 480p DVDRip x264-GRP"  # noqa: S101


def test_dreadvault_names_a_dvd_sourced_encode_as_a_dvdrip():
    meta = Meta(
        name="Ghost 1984 480p NTSC DD 2.0 x264-SaL",
        type="ENCODE",
        source="NTSC",
        resolution="480p",
        video_encode="x264",
        audio="DD 2.0",
        language_checked=True,
    )

    name = asyncio.run(_tracker().get_name(meta))["name"]

    assert name == "Ghost 1984 480p DVDRip DD 2.0 x264-SaL"  # noqa: S101


@pytest.mark.parametrize(
    ("title", "edition", "repack", "audio_languages", "expected"),
    [
        ("The 480p Murders", "", "", ["Japanese"], "The 480p Murders 2001 JAPANESE 480p DVDRip DD 2.0 x264-GRP"),
        (
            "The Unrated REPACK 480p NTSC Murders",
            "Unrated",
            "REPACK",
            [],
            "The Unrated REPACK 480p NTSC Murders 2001 480p DVDRip DD 2.0 x264-GRP",
        ),
    ],
)
def test_dreadvault_preserves_dvd_encode_title_tokens(title, edition, repack, audio_languages, expected):
    meta = Meta(
        title=title,
        year=2001,
        category="MOVIE",
        type="ENCODE",
        edition=edition,
        repack=repack,
        source="NTSC",
        resolution="480p",
        uhd="",
        video_encode=" x264",
        audio="DD 2.0",
        audio_languages=audio_languages,
        tag="-GRP",
        language_checked=True,
    )
    meta.name = _build_name(meta)
    assert meta.name == " ".join(f"{title} 2001 {edition} {repack} 480p NTSC DD 2.0 x264-GRP".split())  # noqa: S101

    name = asyncio.run(_tracker().get_name(meta))["name"]

    assert name == expected  # noqa: S101


def test_dreadvault_keeps_the_episode_on_a_dvd_sourced_encode():
    meta = Meta(
        name="Example Show 1989 S04E02 Unrated REPACK 480p PAL DD 2.0 x264-GRP",
        category="TV",
        type="ENCODE",
        source="PAL",
        resolution="480p",
        edition="Unrated",
        repack="REPACK",
        video_encode="x264",
        audio="DD 2.0",
        language_checked=True,
    )

    name = asyncio.run(_tracker().get_name(meta))["name"]

    assert name == "Example Show 1989 S04E02 480p DVDRip DD 2.0 x264-GRP"  # noqa: S101


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


def test_dreadvault_preserves_title_spaces_when_dvdrip_source_and_encode_are_empty():
    meta = Meta(
        name="Example Movie 1990 DVDRip DD 2.0-GRP",
        type="DVDRIP",
        source="",
        resolution="480p",
        video_encode="",
        audio="DD 2.0",
        language_checked=True,
    )

    name = asyncio.run(_tracker().get_name(meta))["name"]

    assert name == "Example Movie 1990 480p DVDRip DD 2.0-GRP"  # noqa: S101


@pytest.mark.parametrize("first_track_language", ["ja", ""])
def test_dreadvault_adds_foreign_audio_language_before_encode_resolution(first_track_language):
    meta = Meta(
        name="Example Movie 2001 1080p BluRay DD 5.1 x264-GRP",
        type="ENCODE",
        source="BluRay",
        resolution="1080p",
        audio_languages=["Japanese"],
        language_checked=True,
        mediainfo={"media": {"track": [{"@type": "Audio", "Language": first_track_language}, {"@type": "Audio", "Language": "ja"}]}},
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

    assert name == "Example Movie 2001 1080p Blu-ray AVC DD 5.1-GRP"  # noqa: S101


def test_dreadvault_omits_language_marker_when_audio_includes_english():
    meta = Meta(
        name="Example Movie 2001 1080p BluRay DD 5.1 x264-GRP",
        type="ENCODE",
        source="BluRay",
        resolution="1080p",
        audio="DD 5.1",
        audio_languages=["Japanese", "English"],
        language_checked=True,
    )

    name = asyncio.run(_tracker().get_name(meta))["name"]

    assert name == "Example Movie 2001 1080p BluRay Dual-Audio DD 5.1 x264-GRP"  # noqa: S101


@pytest.mark.parametrize(
    ("audio_languages", "flag", "expected"),
    [
        (["Japanese", "English"], "no_dual", "Example Movie 2001 1080p BluRay DD 5.1 x264-GRP"),
        (["English"], "no_dub", "Example Movie 2001 1080p BluRay DD 5.1 x264-GRP"),
    ],
)
def test_dreadvault_dub_token_respects_no_dual_and_no_dub(audio_languages, flag, expected):
    meta = Meta(
        name="Example Movie 2001 1080p BluRay DD 5.1 x264-GRP",
        type="ENCODE",
        source="BluRay",
        resolution="1080p",
        audio="DD 5.1",
        audio_languages=audio_languages,
        original_language="ja",
        language_checked=True,
        **{flag: True},
    )

    name = asyncio.run(_tracker().get_name(meta))["name"]

    assert name == expected  # noqa: S101


@pytest.mark.parametrize(("audio_language", "marker"), [("No", "ZXX "), ("zxx", "ZXX "), ("No linguistic content", "ZXX "), ("Undetermined", ""), ("und", ""), ("", "")])
def test_dreadvault_formats_non_linguistic_and_undetermined_audio(audio_language, marker):
    meta = Meta(
        name="Ghost 1984 NTSC x264 DVDRip DD 2.0-SaL",
        type="DVDRIP",
        source="NTSC",
        resolution="480p",
        video_encode=" x264",
        audio="DD 2.0",
        audio_languages=[audio_language],
        language_checked=True,
    )

    name = asyncio.run(_tracker().get_name(meta))["name"]

    assert name == f"Ghost 1984 {marker}480p DVDRip DD 2.0 x264-SaL"  # noqa: S101


@pytest.mark.parametrize(
    ("audio_languages", "original_language", "marker", "dub"),
    [
        (["", "Undetermined", "und", "Japanese"], "ja", "JAPANESE ", ""),
        (["No", "Norwegian"], "no", "NORWEGIAN ", ""),
        (["zxx", "French", "Japanese", "French"], "ja", "FRENCH ", "Dual-Audio "),
        (["No linguistic content", "Italian", "German", "French"], "ja", "ITALIAN ", "Multi-Audio "),
        (["Undetermined", "Japanese", "English"], "ja", "", "Dual-Audio "),
        (["No", "Japanese", "English"], "ja", "", "Dual-Audio "),
        (["zxx", "English"], "ja", "", "Dubbed "),
        (["English"], "no", "", "Dubbed "),
        (["Undetermined", "No"], "ja", "ZXX ", ""),
        ([], "ja", "", "MULTI "),
        (["", "Undetermined", "und"], "ja", "", "MULTI "),
    ],
)
def test_dreadvault_uses_only_linguistic_languages_for_marker_and_dub(audio_languages, original_language, marker, dub):
    meta = Meta(
        name="Example Movie 2001 1080p BluRay MULTI DD 5.1 x264-GRP",
        type="ENCODE",
        source="BluRay",
        resolution="1080p",
        audio="MULTI DD 5.1",
        audio_languages=audio_languages,
        original_language=original_language,
        language_checked=True,
    )

    name = asyncio.run(_tracker().get_name(meta))["name"]

    assert name == f"Example Movie 2001 {marker}1080p BluRay {dub}DD 5.1 x264-GRP"  # noqa: S101


def test_dreadvault_adds_foreign_audio_language_to_a_dvdrip():
    # The DVDRip template carries no resolution of its own, so a language pass that ran before the
    # DVDRip branch had nothing to anchor to and dropped the marker (kainoa 2026-09-09).
    meta = Meta(
        name="Imaginary Dolls 1999 NTSC DVD x264 DVDRip DD 2.0-GVXXI",
        type="DVDRIP",
        source="NTSC DVD",
        resolution="480p",
        audio="DD 2.0",
        video_encode=" x264",
        audio_languages=["Japanese"],
        language_checked=True,
    )

    name = asyncio.run(_tracker().get_name(meta))["name"]

    assert name == "Imaginary Dolls 1999 JAPANESE 480p DVDRip DD 2.0 x264-GVXXI"  # noqa: S101


def test_dreadvault_omits_foreign_audio_language_from_a_dvd_full_disc():
    meta = Meta(
        name="Sample Film 1977 USA NTSC DVD9 LPCM 2.0",
        year=1977,
        type="DISC",
        is_disc="DVD",
        source="NTSC",
        resolution="480p",
        region="USA",
        video_codec="MPEG-2",
        audio="LPCM 2.0",
        audio_languages=["Japanese"],
        language_checked=True,
    )

    name = asyncio.run(_tracker().get_name(meta))["name"]

    assert name == "Sample Film 1977 USA NTSC DVD9 LPCM 2.0"  # noqa: S101


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

    assert name == "Example Movie 2001 JAPANESE 576p DVD REMUX DD 5.1-GRP"  # noqa: S101


def test_dreadvault_adds_dvd_remux_language_after_release_year_when_title_contains_year():
    meta = Meta(
        title="Imaginary Film 2000",
        year=2000,
        category="MOVIE",
        type="REMUX",
        source="PAL DVD",
        resolution="576p",
        video_codec="MPEG-2",
        audio="DD 2.0",
        audio_languages=["Japanese"],
        tag="-GRP",
        language_checked=True,
    )
    meta.name = _build_name(meta)
    assert meta.name == "Imaginary Film 2000 2000 PAL DVD REMUX DD 2.0-GRP"  # noqa: S101

    name = asyncio.run(_tracker().get_name(meta))["name"]

    assert name == "Imaginary Film 2000 2000 JAPANESE 576p DVD REMUX DD 2.0-GRP"  # noqa: S101


def test_dreadvault_adds_foreign_audio_language_before_source_for_yearless_dvd_remux():
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

    assert name == "Example Movie JAPANESE 576p DVD REMUX DD 2.0-GRP"  # noqa: S101


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

    assert name == "Example Show AKA Alt Show 2024 S01 JAPANESE 576p DVD REMUX DD 2.0-GRP"  # noqa: S101


# /wikis/6 rev 2026-09-30, R1-R11: release facts and exact titles.
@pytest.mark.parametrize(
    ("facts", "expected"),
    [
        pytest.param(
            {
                "category": "MOVIE",
                "type": "ENCODE",
                "title": "Kuroko's Basketball",
                "aka": "Kuroko no Basket",
                "year": 2017,
                "resolution": "1080p",
                "source": "BluRay",
                "audio": {"codec": "DD+", "channels": "5.1"},
                "video": "x264",
                "tracks": [{"lang": "Japanese"}],
                "original_language": "ja",
                "tag": "Kitsune",
            },
            "Kuroko's Basketball AKA Kuroko no Basket 2017 JAPANESE 1080p BluRay DD+ 5.1 x264-Kitsune",
            id="lang-basic",
        ),
        pytest.param(
            {
                "category": "MOVIE",
                "type": "ENCODE",
                "title": "The Wailing",
                "year": 2016,
                "hybrid": True,
                "repack": "REPACK",
                "resolution": "1080p",
                "source": "BluRay",
                "audio": {"codec": "DD", "channels": "5.1"},
                "video": "x264",
                "tracks": [{"lang": "Korean"}],
                "original_language": "ko",
                "tag": "GRP",
            },
            "The Wailing 2016 KOREAN Hybrid REPACK 1080p BluRay DD 5.1 x264-GRP",
            id="lang-before-hybrid-repack",
        ),
        pytest.param(
            {
                "category": "TV",
                "type": "WEBDL",
                "title": "Kingdom",
                "season": 1,
                "episode": 1,
                "episode_title": "The Hungry Dead",
                "resolution": "1080p",
                "source": "WEB",
                "service": "NF",
                "audio": {"codec": "DD+", "channels": "5.1"},
                "video": "H.264",
                "tracks": [{"lang": "Korean"}],
                "original_language": "ko",
                "tag": "GRP",
            },
            "Kingdom S01E01 The Hungry Dead KOREAN 1080p NF WEB-DL DD+ 5.1 H.264-GRP",
            id="lang-tv-episode-named",
        ),
        pytest.param(
            {
                "category": "MOVIE",
                "type": "ENCODE",
                "title": "Ringu",
                "year": 1998,
                "resolution": "1080p",
                "source": "BluRay",
                "audio": {"codec": "FLAC", "channels": "2.0"},
                "video": "x264",
                "tracks": [{"lang": "Japanese"}, {"lang": "French"}],
                "original_language": "ja",
                "tag": "GRP",
            },
            "Ringu 1998 JAPANESE 1080p BluRay Dual-Audio FLAC 2.0 x264-GRP",
            id="dual-no-english",
        ),
        pytest.param(
            {
                "category": "MOVIE",
                "type": "ENCODE",
                "title": "Inferno",
                "year": 1980,
                "resolution": "1080p",
                "source": "BluRay",
                "audio": {"codec": "DTS-HD MA", "channels": "1.0"},
                "video": "x264",
                "tracks": [{"lang": "Italian"}, {"lang": "English"}, {"lang": "German"}],
                "original_language": "it",
                "tag": "GRP",
            },
            "Inferno 1980 1080p BluRay Multi-Audio DTS-HD MA 1.0 x264-GRP",
            id="multi-with-english",
        ),
        pytest.param(
            {
                "category": "MOVIE",
                "type": "ENCODE",
                "title": "Zombie Flesh Eaters",
                "year": 1979,
                "resolution": "1080p",
                "source": "BluRay",
                "audio": {"codec": "DTS-HD MA", "channels": "1.0"},
                "video": "x264",
                "tracks": [{"lang": "English"}],
                "original_language": "it",
                "tag": "GRP",
            },
            "Zombie Flesh Eaters 1979 1080p BluRay Dubbed DTS-HD MA 1.0 x264-GRP",
            id="dubbed",
        ),
        pytest.param(
            {
                "category": "MOVIE",
                "type": "ENCODE",
                "title": "Nosferatu",
                "year": 1922,
                "resolution": "1080p",
                "source": "BluRay",
                "audio": {"codec": "FLAC", "channels": "2.0"},
                "video": "x264",
                "tracks": [{"lang": "No linguistic content"}],
                "original_language": "de",
                "tag": "GRP",
            },
            "Nosferatu 1922 ZXX 1080p BluRay FLAC 2.0 x264-GRP",
            id="lang-zxx",
        ),
        pytest.param(
            {
                "category": "MOVIE",
                "type": "ENCODE",
                "title": "Dead Snow",
                "year": 2009,
                "resolution": "1080p",
                "source": "BluRay",
                "audio": {"codec": "DTS", "channels": "5.1"},
                "video": "x264",
                "tracks": [{"lang": "No linguistic content"}, {"lang": "Norwegian"}],
                "original_language": "no",
                "tag": "GRP",
            },
            "Dead Snow 2009 NORWEGIAN 1080p BluRay DTS 5.1 x264-GRP",
            id="zxx-music-track-before-dialogue",
        ),
        pytest.param(
            {
                "category": "MOVIE",
                "type": "REMUX",
                "title": "Alien Abduction: Incident in Lake County",
                "year": 1998,
                "resolution": "576i",
                "source": "PAL DVD",
                "audio": {"codec": "DD", "channels": "2.0"},
                "video": "MPEG-2",
                "tag": "DVL",
            },
            "Alien Abduction: Incident in Lake County 1998 576i DVD REMUX DD 2.0-DVL",
            id="dvd-remux-pal",
        ),
        pytest.param(
            {
                "category": "MOVIE",
                "type": "REMUX",
                "title": "Kuroneko",
                "year": 1968,
                "resolution": "480i",
                "source": "NTSC DVD",
                "audio": {"codec": "DD", "channels": "1.0"},
                "video": "MPEG-2",
                "tracks": [{"lang": "Japanese"}],
                "original_language": "ja",
                "tag": "GRP",
            },
            "Kuroneko 1968 JAPANESE 480i DVD REMUX DD 1.0-GRP",
            id="dvd-remux-foreign",
        ),
        pytest.param(
            {
                "category": "MOVIE",
                "type": "DISC",
                "disc": "DVD",
                "title": "Rabies",
                "year": 2010,
                "resolution": "576i",
                "source": "PAL DVD",
                "dvd_size": "DVD9",
                "audio": {"codec": "DD", "channels": "5.1"},
                "video": "MPEG-2",
                "tracks": [{"lang": "Hebrew"}, {"lang": "French"}],
                "original_language": "he",
                "tag": "GRP",
            },
            "Rabies 2010 PAL DVD9 DD 5.1-GRP",
            id="dvd-disc-foreign-no-marker",
        ),
        pytest.param(
            {
                "category": "MOVIE",
                "type": "ENCODE",
                "title": "The Vampires of Coyoacan",
                "year": 1974,
                "resolution": "480p",
                "source": "NTSC DVD",
                "audio": {"codec": "MP3", "channels": "2.0"},
                "video": "x264",
                "tracks": [{"lang": "Spanish"}],
                "original_language": "es",
                "tag": "GRP",
            },
            "The Vampires of Coyoacan 1974 SPANISH 480p DVDRip MP3 2.0 x264-GRP",
            id="dvdrip-foreign",
        ),
        pytest.param(
            {
                "category": "MOVIE",
                "type": "DISC",
                "disc": "BDMV",
                "title": "Kwaidan",
                "year": 1964,
                "resolution": "1080p",
                "source": "BluRay",
                "region": "JPN",
                "video": "AVC",
                "audio": {"codec": "LPCM", "channels": "1.0"},
                "tracks": [{"lang": "Japanese"}, {"lang": "English"}],
                "original_language": "ja",
                "tag": "GRP",
            },
            "Kwaidan 1964 1080p JPN Blu-ray AVC LPCM 1.0-GRP",
            id="bd-disc-foreign-no-marker",
        ),
        pytest.param(
            {
                "category": "MOVIE",
                "type": "DISC",
                "disc": "BDMV",
                "title": "Night of the Living Dead",
                "year": 1968,
                "edition": "Criterion Director's Cut",
                "resolution": "1080p",
                "source": "BluRay",
                "region": "USA",
                "video": "AVC",
                "audio": {"codec": "LPCM", "channels": "1.0"},
                "tag": "GRP",
            },
            "Night of the Living Dead 1968 Director's Cut 1080p USA Blu-ray AVC LPCM 1.0-GRP",
            id="bd-disc-cut-kept-distributor-dropped",
        ),
    ],
)
def test_dreadvault_naming_guide(facts, expected, tmp_path):
    disc = facts.get("disc", "")
    source = facts["source"]
    if "BluRay" in source:
        source = "Blu-ray" if disc == "BDMV" else "BluRay"
    elif source in ("PAL DVD", "NTSC DVD") and facts["type"] != "REMUX":
        source = source.split()[0]
    elif source == "HD DVD":
        source = "HDDVD"
    elif source == "WEB":
        source = "Web"
    meta = Meta(
        category=facts["category"],
        type=facts["type"],
        title=facts["title"],
        aka=f"AKA {facts['aka']}" if facts.get("aka") else "",
        year=facts.get("year"),
        season=f"S{facts['season']:02d}" if facts.get("season") else "",
        episode=f"E{facts['episode']:02d}" if facts.get("episode") else "",
        tv_pack=facts["category"] == "TV" and not facts.get("episode"),
        auto_episode_title=facts.get("episode_title"),
        resolution=facts["resolution"],
        source=source,
        is_disc=disc or None,
        dvd_size=facts.get("dvd_size", ""),
        region=facts.get("region", ""),
        three_d="3D" if facts.get("three_d") else "",
        uhd="UHD" if facts["source"].startswith("UHD ") else "",
        hdr=facts.get("hdr", ""),
        service=facts.get("service", ""),
        edition=facts.get("edition", ""),
        repack=facts.get("repack", ""),
        webdv=facts.get("hybrid", False),
        hardcoded_subs=facts.get("hc", False),
        original_language=facts.get("original_language", "en"),
        tag=f"-{facts['tag']}" if facts.get("tag") else "",
        base_dir=str(tmp_path),
        uuid="release",
        unattended=True,
    )
    audio = facts["audio"]
    codec = audio["codec"]
    audio_format = {"DD": "AC-3", "DD+": "E-AC-3", "TrueHD": "MLP FBA", "DTS-HD MA": "DTS", "LPCM": "PCM", "MP3": "MPEG Audio"}.get(codec, codec)
    video_format = {"x264": "AVC", "H.264": "AVC", "x265": "HEVC", "H.265": "HEVC", "MPEG-2": "MPEG Video", "XviD": "MPEG-4 Visual"}.get(facts["video"], facts["video"])
    video_track = {
        "@type": "Video",
        "Format": video_format,
        "Format_Version": "2" if video_format == "MPEG Video" else "",
        "Format_Profile": "High 10" if facts.get("hi10p") else "",
        "BitDepth": "10" if facts.get("hi10p") or meta.hdr else "8",
        "Encoded_Library_Name": facts["video"] if facts["video"] in ("x264", "x265", "XviD") else "",
    }
    media_tracks = [{"@type": "General"}, video_track]
    text_tracks = []
    bd_tracks = []
    for index, track in enumerate(facts.get("tracks", [{"lang": "English"}])):
        language = track["lang"]
        title = "Commentary" if track.get("commentary") else ""
        media_tracks.append(
            {
                "@type": "Audio",
                "StreamOrder": str(index + 1),
                "Default": "Yes" if index == 0 else "No",
                "Language": langcodes.find(language).language if language else "",
                "Title": title,
                "Format": audio_format,
                "Format_Profile": "Layer 3" if codec == "MP3" else "",
                "Format_AdditionalFeatures": "XLL" if codec == "DTS-HD MA" else ("16-ch" if codec == "TrueHD" else "JOC") if audio.get("object") == "Atmos" else "",
                "Channels": str(sum(int(part) for part in audio["channels"].split("."))),
            }
        )
        text_tracks.append(f"Audio #{index + 1}\nFormat : {audio_format}\nLanguage : {language}\nTitle : {title}\n")
        bd_codec = {"TrueHD": "Dolby TrueHD Audio", "DTS-HD MA": "DTS-HD Master Audio", "LPCM": "LPCM Audio"}.get(codec, codec)
        bd_tracks.append({"language": language, "codec": bd_codec, "channels": audio["channels"]})
    meta.mediainfo = {"media": {"track": media_tracks}}
    output_dir = tmp_path / "tmp" / meta.uuid
    output_dir.mkdir(parents=True)
    # LanguagesManager reads text exports; AudioManager reads the equivalent JSON/BDInfo.
    (output_dir / "MEDIAINFO.txt").write_text("\n".join(text_tracks), encoding="utf-8")
    (output_dir / "BD_SUMMARY_00.txt").write_text("\n".join(f"Audio: {track['language']} / {track['codec']} / {track['channels']}" for track in bd_tracks), encoding="utf-8")
    bdinfo = None
    if disc == "BDMV":
        bd_video_codec = {"AVC": "MPEG-4 AVC Video", "HEVC": "MPEG-H HEVC Video"}[facts["video"]]
        bdinfo = {"audio": bd_tracks, "video": [{"codec": bd_video_codec}]}
        meta.bdinfo = bdinfo
    meta.audio, meta.channels, meta.has_commentary = asyncio.run(AudioManager({}).get_audio_v2(meta.mediainfo, meta, bdinfo))
    meta.video_encode, meta.video_codec, meta.has_encode_settings, meta.bit_depth = asyncio.run(VideoManager().get_video_encode(meta.mediainfo, meta.type, bdinfo))
    if disc == "BDMV":
        meta.video_encode = ""
        meta.video_codec = asyncio.run(VideoManager().get_video_codec(bdinfo))
    asyncio.run(LanguagesManager().process_desc_language(meta))
    meta.name = _build_name(meta)

    name = asyncio.run(_tracker().get_name(meta))["name"]

    assert name == expected  # noqa: S101
