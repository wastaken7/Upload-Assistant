# ruff: noqa: S101
import asyncio

from src.meta import Meta
from src.trackers.UNIT3D.onlyencodes import OnlyEncodes


def _name(meta: Meta) -> str:
    config = {"DEFAULT": {}, "TRACKERS": {"ONLYENCODES": {}}}
    return asyncio.run(OnlyEncodes(config).get_name(meta))["name"]


def test_onlyencodes_adds_resolution_before_ds4k() -> None:
    meta = Meta(
        category="MOVIE",
        type="WEBRIP",
        resolution="1080p",
        basename_no_ext="Movie.Title.2025.1080p.DS4K.WEBRip.DDP5.1.x265-RlsGrp",
        name="Movie Title 2025 1080p WEBRip DDP 5.1 x265-RlsGrp",
        tag="RlsGrp",
        audio_languages=["English"],
        language_checked=True,
    )

    assert _name(meta) == "Movie Title 2025 1080p DS4K WEBRip DDP 5.1 x265-RlsGrp"


def test_onlyencodes_adds_resolution_before_rm4k() -> None:
    meta = Meta(
        category="MOVIE",
        type="ENCODE",
        resolution="1080p",
        basename_no_ext="Movie.Title.2025.1080p.RM4K.BluRay.x264-RlsGrp",
        name="Movie Title 2025 1080p BluRay x264-RlsGrp",
        tag="RlsGrp",
        audio_languages=["English"],
        language_checked=True,
    )

    assert _name(meta) == "Movie Title 2025 1080p RM4K BluRay x264-RlsGrp"


def test_onlyencodes_fixes_ds4k_without_resolution() -> None:
    meta = Meta(
        category="MOVIE",
        type="WEBRIP",
        resolution="1080p",
        basename_no_ext="Movie.Title.2025.1080p.DS4K.WEBRip.DDP5.1.x265-RlsGrp",
        name="Movie Title 2025 DS4K WEBRip DDP 5.1 x265-RlsGrp",
        tag="RlsGrp",
        audio_languages=["English"],
        language_checked=True,
    )

    assert _name(meta) == "Movie Title 2025 1080p DS4K WEBRip DDP 5.1 x265-RlsGrp"


def test_onlyencodes_does_not_duplicate_existing_resolution_ds4k() -> None:
    meta = Meta(
        category="MOVIE",
        type="WEBRIP",
        resolution="1080p",
        basename_no_ext="Movie.Title.2025.1080p.DS4K.WEBRip.DDP5.1.x265-RlsGrp",
        name="Movie Title 2025 1080p DS4K WEBRip DDP 5.1 x265-RlsGrp",
        tag="RlsGrp",
        audio_languages=["English"],
        language_checked=True,
    )

    assert _name(meta) == "Movie Title 2025 1080p DS4K WEBRip DDP 5.1 x265-RlsGrp"


def test_onlyencodes_normal_name_without_scale_tag() -> None:
    meta = Meta(
        category="MOVIE",
        type="WEBRIP",
        resolution="1080p",
        basename_no_ext="Movie.Title.2025.1080p.WEBRip.DDP5.1.x265-RlsGrp",
        name="Movie Title 2025 1080p WEBRip DDP 5.1 x265-RlsGrp",
        tag="RlsGrp",
        audio_languages=["English"],
        language_checked=True,
    )

    assert _name(meta) == "Movie Title 2025 1080p WEBRip DDP 5.1 x265-RlsGrp"


def test_onlyencodes_foreign_language_with_ds4k() -> None:
    meta = Meta(
        category="MOVIE",
        type="WEBRIP",
        resolution="1080p",
        basename_no_ext="Movie.Title.2025.1080p.DS4K.WEBRip.DDP5.1.x265-RlsGrp",
        name="Movie Title 2025 1080p WEBRip DDP 5.1 x265-RlsGrp",
        tag="RlsGrp",
        audio_languages=["French"],
        language_checked=True,
    )

    assert _name(meta) == "Movie Title 2025 FRENCH 1080p DS4K WEBRip DDP 5.1 x265-RlsGrp"
