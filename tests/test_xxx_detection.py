"""Regression tests for automatic XXX video category detection."""
# ruff: noqa: S101

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.meta import Meta
from src.prep import Prep
from src.prep_helpers import detect_disc_and_category, extract_xxx_metadata, is_xxx_video_release
from src.trackers.USENET.suio import Suio
from src.xxx_keywords import extract_xxx_keywords
from src.xxx_platforms import XXX_PLATFORM_KEYWORDS


@pytest.mark.parametrize(
    "marker",
    [
        "OnlyFans",
        "ManyVids",
        "Fansly",
        "Clips4Sale",
        "iWantClips",
        "JustForFans",
        "LoyalFans",
        "PornHub",
        "XNXX",
        "CamSoda",
        "Brazzers",
        "AmateurCFNM",
        "BeautyAndTheSenior",
        "BFTP18",
        "Cherry-Candle",
        "Debt4K",
        "Submissed",
        "GoodMorningSex",
        "ClubSweethearts",
        "Gonzo2000",
        "GrandMams",
        "GroupBanged",
        "HollandschePassie",
        "HomeGrownEurope",
        "Manko88",
        "MuchaSexo",
        "MyMilfz",
        "Perfect18",
        "RickysRoom",
        "SinnSage",
        "UltraFilms",
        "FeetishPOV",
        "XXX",
    ],
)
def test_platform_marked_video_is_detected_as_xxx(marker, tmp_path):
    video = tmp_path / f"Studio.{marker}.2026.1080p.WEB-DL.mkv"
    video.write_bytes(b"video")
    meta = Meta(path=str(video))
    prep = SimpleNamespace(disc_info_manager=SimpleNamespace(get_disc=AsyncMock(return_value=("", str(video), {}, []))))

    asyncio.run(detect_disc_and_category(prep, meta))

    assert meta.category == "XXX"


def test_xxx_detection_requires_a_video_file(tmp_path):
    archive = tmp_path / "OnlyFans.Creator.photos.zip"
    archive.write_bytes(b"archive")

    assert not is_xxx_video_release(archive)


def test_xxx_detection_does_not_match_generic_fans(tmp_path):
    video = tmp_path / "Sports.Fans.2026.1080p.WEB-DL.mkv"
    video.write_bytes(b"video")

    assert not is_xxx_video_release(video)


def test_xxx_platform_markers_are_owned_by_the_dedicated_module():
    assert {"onlyfans", "manyvids", "submissed", "goodmorningsex"} <= XXX_PLATFORM_KEYWORDS


def test_get_cat_checks_xxx_before_tv_patterns(tmp_path):
    video = tmp_path / "OnlyFans.Creator.S01E01.1080p.WEB-DL.mkv"
    video.write_bytes(b"video")
    meta = Meta(path=str(video), uuid=video.stem)

    assert asyncio.run(Prep.get_cat(SimpleNamespace(), "", meta)) == "XXX"


def test_xxx_category_is_always_marked_as_adult_media():
    meta = Meta(category="XXX")

    assert Prep.check_adult_media(SimpleNamespace(), meta)


@pytest.mark.parametrize(
    ("name", "date", "year", "title"),
    [
        ("OnlyFans.2026.Sophia.Isabella.XXX.MP4-P0RNL0V3RSD", "2026", 2026, "Sophia Isabella"),
        ("Bellesa.26.08.21.Addison.Vodka.720p.XXX.MP4-P0RNL0V3RSD", "2026-08-21", 2026, "Addison Vodka"),
    ],
)
def test_xxx_release_name_extracts_metadata(name, date, year, title):
    metadata = extract_xxx_metadata(name)
    assert metadata == {
        "publisher": name.split(".")[0],
        "release_date": date,
        "year": year,
        "title": title,
    }


def test_xxx_keywords_extract_platform_and_descriptive_tags_from_release_name():
    keywords = extract_xxx_keywords("Studio.Brazzers.Amateur.Vintage.1080p.WEB-DL", ["custom tag"])

    assert keywords == ["custom tag", "brazzers", "amateur", "vintage"]


def test_xxx_keywords_prefer_specific_phrases_and_normalize_manual_keywords():
    keywords = extract_xxx_keywords("Creator.Double.Penetration.OnlyFans.mp4", "custom tag, OnlyFans")

    assert keywords == ["custom tag", "OnlyFans", "double-penetration"]


def test_suio_advertises_its_existing_xxx_upload_mapping():
    assert "XXX" in Suio.supported_categories
