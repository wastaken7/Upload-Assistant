"""Regression tests for Seedpool mappings and release names."""
# ruff: noqa: S101

import asyncio

import pytest

from src.meta import Meta
from src.trackers.UNIT3D.seedpool import Seedpool


def _tracker() -> Seedpool:
    return Seedpool({"DEFAULT": {}, "TRACKERS": {"SEEDPOOL": {}}})


def test_seedpool_supports_music_game_and_book_categories():
    tracker = _tracker()

    assert {"MUSIC", "GAME", "BOOK"}.issubset(tracker.supported_categories)
    assert asyncio.run(tracker.get_category_id(Meta(category="MUSIC"))) == {"category_id": "5"}
    assert asyncio.run(tracker.get_category_id(Meta(category="GAME"))) == {"category_id": "3"}
    assert asyncio.run(tracker.get_category_id(Meta(category="BOOK"))) == {"category_id": "7"}
    assert asyncio.run(tracker.get_category_id(Meta(category="BOOK", audiobook=True))) == {"category_id": "9"}
    assert asyncio.run(tracker.get_category_id(Meta(category="GAME", name="Sample Game 26"))) == {"category_id": "3"}


def test_seedpool_maps_music_book_and_game_types_to_current_site_ids():
    tracker = _tracker()

    assert asyncio.run(tracker.get_type_id(Meta(category="MUSIC", format="FLAC"))) == {"type_id": "11"}
    assert asyncio.run(tracker.get_type_id(Meta(category="BOOK", comic=True, type="CBZ"))) == {"type_id": "40"}
    assert asyncio.run(tracker.get_type_id(Meta(category="BOOK", audiobook=True, format="MP3"))) == {"type_id": "13"}
    assert asyncio.run(tracker.get_type_id(Meta(category="GAME", platform="Nintendo Switch"))) == {"type_id": "15"}


@pytest.mark.parametrize("single_file", [False, True])
def test_seedpool_preserves_original_filename_spacing_and_punctuation(single_file):
    release_name = "Fictional Voyage (2022) (2160p NF WEB-DL H265 SDR DDP Atmos 5.1 English - NOGRP)"
    meta = Meta(
        category="MOVIE",
        name="Fictional Voyage 2022 2160p NF WEB-DL DDP 5.1 Atmos H.265-NOGRP",
        uuid="Fictional Voyage (2022)",
        basename_no_ext="Fictional Voyage (2022)" if single_file else release_name,
        filelist=[f"D:/Movies/Fictional Voyage (2022)/{release_name}.mkv"] if single_file else [],
    )

    assert asyncio.run(_tracker().get_name(meta)) == {"name": release_name}


@pytest.mark.parametrize("extension", [".mkv", ".MKV", ".mp4", ".avi", ".ts", ""])
def test_seedpool_strips_only_media_extensions_from_single_file_names(extension):
    release_name = "Movie.2025.1080p.WEB-DL.DDP.5.1-GROUP"
    meta = Meta(category="MOVIE", basename_no_ext="Containing folder", filelist=[f"D:/Movies/{release_name}{extension}"])

    assert asyncio.run(_tracker().get_name(meta)) == {"name": release_name}


@pytest.mark.parametrize("filelist", [[], ["D:/TV/Show S01E01.mkv", "D:/TV/Show S01E02.mkv"]])
def test_seedpool_preserves_folder_name_when_no_single_media_file(filelist):
    release_name = "Show S01 1080p WEB-DL DDP 5.1"
    meta = Meta(category="TV", basename_no_ext=release_name, filelist=filelist)

    assert asyncio.run(_tracker().get_name(meta)) == {"name": release_name}


def test_seedpool_prefers_confirmed_scene_release_name():
    scene_name = "Movie.2025.1080p.WEB.h264-SCENE"
    meta = Meta(
        category="MOVIE",
        scene=True,
        scene_name=scene_name,
        basename_no_ext="Containing folder",
        filelist=["D:/Movies/movie.mkv"],
    )

    assert asyncio.run(_tracker().get_name(meta)) == {"name": scene_name}


def test_seedpool_scene_without_confirmed_name_uses_original_filename():
    release_name = "Movie (2025) 1080p WEB-DL-GROUP"
    meta = Meta(category="MOVIE", scene=True, basename_no_ext="Containing folder", filelist=[f"D:/Movies/{release_name}.mkv"])

    assert asyncio.run(_tracker().get_name(meta)) == {"name": release_name}


@pytest.mark.parametrize("overrides", [{"is_disc": "BDMV"}, {"mal_id": 123}])
def test_seedpool_retains_generated_names_for_discs_and_anime(overrides):
    meta = Meta(
        category="MOVIE",
        name="Movie 2025 1080p BluRay DDP 5.1-GROUP",
        basename_no_ext="Containing folder",
        filelist=["D:/Movies/movie.mkv"],
        **overrides,
    )

    assert asyncio.run(_tracker().get_name(meta)) == {"name": "Movie.2025.1080p.BluRay.DDP.5.1-GROUP"}
