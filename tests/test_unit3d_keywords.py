"""Regression tests for the shared UNIT3D keywords payload field."""

from __future__ import annotations

import asyncio

from src.meta import Meta
from src.trackers.UNIT3D.asiancinema import AsianCinema
from src.trackers.UNIT3D.peergarden import PeerGarden


def _tracker() -> PeerGarden:
    return PeerGarden({"DEFAULT": {}, "TRACKERS": {"PEERGARDEN": {}}})


def test_music_album_genres_map_to_keywords():
    meta = Meta()
    meta.category = "MUSIC"
    meta.genres = ["Synthwave", "Dream Pop"]

    assert asyncio.run(_tracker().get_keywords(meta)) == {"keywords": "Synthwave, Dream Pop"}


def test_music_genres_lead_and_dedupe_existing_keywords():
    meta = Meta()
    meta.category = "MUSIC"
    meta.genres = ["Synthwave", " ", "Dream Pop"]
    meta.keywords = ["dream pop", "Neon Coast"]

    assert asyncio.run(_tracker().get_keywords(meta)) == {"keywords": "Synthwave, Dream Pop, Neon Coast"}


def test_music_genres_respect_255_limit():
    meta = Meta()
    meta.category = "MUSIC"
    meta.genres = ["Ambient", "g" * 250]

    assert asyncio.run(_tracker().get_keywords(meta)) == {"keywords": "Ambient"}


def test_video_ignores_genres_for_keywords():
    meta = Meta()
    meta.category = "MOVIE"
    meta.genres = ["Drama"]
    meta.keywords = ["lighthouse"]

    assert asyncio.run(_tracker().get_keywords(meta)) == {"keywords": "lighthouse"}


def test_asiancinema_music_genres_map_to_keywords():
    tracker = AsianCinema({"DEFAULT": {}, "TRACKERS": {"AZ": {}}})
    meta = Meta()
    meta.category = "MUSIC"
    meta.genres = ["City Pop", "Funk"]
    meta.keywords = ["funk"]

    assert asyncio.run(tracker.get_keywords(meta)) == {"keywords": "City Pop, Funk"}


def test_asiancinema_keywords_cap_terms_and_length():
    tracker = AsianCinema({"DEFAULT": {}, "TRACKERS": {"AZ": {}}})
    meta = Meta()
    meta.keywords = [f"{i}{'k' * 39}" for i in range(12)]

    keywords = asyncio.run(tracker.get_keywords(meta))["keywords"]

    assert len(keywords) <= 255
    assert keywords.split(", ") == meta.keywords[:6]

    meta.keywords = [f"tag{i}" for i in range(12)]
    assert asyncio.run(tracker.get_keywords(meta))["keywords"].split(", ") == meta.keywords[:10]
