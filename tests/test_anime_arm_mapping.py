# ruff: noqa: S101
import asyncio
import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.meta import Meta
from src.tmdb import _expected_anime_season, _get_arm_mal_id, get_romaji, tmdb_other_meta


def mapping(mal=123, season=2, **extra):
    return {"myanimelist": mal, "themoviedb-season": season, "thetvdb": 456, "imdb": "tt0000789", **extra}


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ([mapping(), mapping(234, 1)], 123),
        ([mapping(), mapping(234)], 0),
        ([mapping(), mapping()], 0),
        ([mapping(season=0)], 0),
        ([mapping(season=None)], 0),
        ([mapping(season="2")], 0),
        ([mapping(mal=None)], 0),
        ([mapping(mal=True)], 0),
        ([mapping(mal=-1)], 0),
        ([mapping(thetvdb=999)], 0),
        ([mapping(imdb="tt9999999")], 0),
        ([mapping(imdb=None)], 0),
        ([None], 0),
        (None, 0),
        ([], 0),
        ({"error": "unavailable"}, 0),
    ],
)
def test_arm_selects_only_unambiguous_matching_tv_ids(tmp_path, payload, expected):
    meta = Meta(base_dir=str(tmp_path), category="TV", tmdb_id=345, tvdb_id=456, imdb_id=789)
    response = httpx.Response(200, content=json.dumps(payload), request=httpx.Request("GET", "https://arm.haglund.dev"))
    with patch("src.tmdb.httpx.AsyncClient.get", new=AsyncMock(return_value=response)):
        assert asyncio.run(_get_arm_mal_id(meta, 2)) == expected


@pytest.mark.parametrize(("category", "tmdb_id", "season"), [("MOVIE", 345, 2), ("TV", 0, 2), ("TV", 345, None)])
def test_arm_skips_unsupported_or_unknown_context(tmp_path, category, tmdb_id, season):
    meta = Meta(base_dir=str(tmp_path), category=category, tmdb_id=tmdb_id)
    with patch("src.tmdb.httpx.AsyncClient.get", new=AsyncMock()) as get:
        assert asyncio.run(_get_arm_mal_id(meta, season)) == 0
    get.assert_not_called()


@pytest.mark.parametrize("payload", [[mapping()], [], None])
def test_arm_caches_success_and_missing_mappings(tmp_path, payload):
    meta = Meta(base_dir=str(tmp_path), category="TV", tmdb_id=345)
    response = httpx.Response(200, content=json.dumps(payload), request=httpx.Request("GET", "https://arm.haglund.dev"))
    with patch("src.tmdb.httpx.AsyncClient.get", new=AsyncMock(return_value=response)) as get:
        first = asyncio.run(_get_arm_mal_id(meta, 2))
        assert asyncio.run(_get_arm_mal_id(meta, 2)) == first
    assert get.await_count == 1


def test_arm_network_failure_does_not_cache_a_missing_mapping(tmp_path):
    meta = Meta(base_dir=str(tmp_path), category="TV", tmdb_id=345)
    with patch("src.tmdb.httpx.AsyncClient.get", new=AsyncMock(side_effect=httpx.ReadTimeout("timeout"))) as get:
        assert asyncio.run(_get_arm_mal_id(meta, 2)) == 0
        assert asyncio.run(_get_arm_mal_id(meta, 2)) == 0
    assert get.await_count == 2


@pytest.mark.parametrize("status", [429, 500])
def test_arm_http_errors_are_not_cached(tmp_path, status):
    meta = Meta(base_dir=str(tmp_path), category="TV", tmdb_id=345)
    response = httpx.Response(status, json=[mapping()], request=httpx.Request("GET", "https://arm.haglund.dev"))
    with patch("src.tmdb.httpx.AsyncClient.get", new=AsyncMock(return_value=response)) as get:
        assert asyncio.run(_get_arm_mal_id(meta, 2)) == 0
        assert asyncio.run(_get_arm_mal_id(meta, 2)) == 0
    assert get.await_count == 2


def anime_response(mal=123, title="Astral Journey"):
    return httpx.Response(
        200,
        json={
            "data": {
                "Page": {
                    "media": [
                        {
                            "idMal": mal,
                            "title": {"romaji": title, "english": title},
                            "episodes": 12,
                            "seasonYear": 2025,
                        }
                    ]
                }
            }
        },
    )


def test_arm_enriches_using_exact_mal_query(tmp_path):
    meta = Meta(base_dir=str(tmp_path), category="TV", tmdb_id=345, filename="Astral.Journey.S02E01.mkv")
    with (
        patch("src.tmdb._get_arm_mal_id", new=AsyncMock(return_value=123)) as arm,
        patch("src.tmdb.httpx.AsyncClient.post", new=AsyncMock(return_value=anime_response())) as post,
    ):
        result = asyncio.run(get_romaji("Astral Journey", 0, meta))
    assert result[:5] == ("Astral Journey", 123, "Astral Journey", "2025", 12)
    arm.assert_awaited_once_with(meta, 2)
    assert post.call_args.kwargs["json"]["variables"] == {"search": 123}


def test_manual_mal_bypasses_arm(tmp_path):
    meta = Meta(base_dir=str(tmp_path), category="TV", tmdb_id=345)
    with (
        patch("src.tmdb._get_arm_mal_id", new=AsyncMock()) as arm,
        patch("src.tmdb.httpx.AsyncClient.post", new=AsyncMock(return_value=anime_response(mal=234))) as post,
    ):
        result = asyncio.run(get_romaji("Astral Journey", 234, meta))
    assert result[1] == 234
    arm.assert_not_called()
    assert post.call_args.kwargs["json"]["variables"] == {"search": 234}


@pytest.mark.parametrize("arm_mal", [0, 123])
def test_missing_arm_or_anilist_mapping_falls_back_to_title(tmp_path, arm_mal):
    meta = Meta(base_dir=str(tmp_path), category="TV", tmdb_id=345, filename="Astral.Journey.S02E01.mkv")
    empty = httpx.Response(200, json={"data": {"Page": {"media": []}}})
    responses = [empty, anime_response(mal=234)] if arm_mal else [anime_response(mal=234)]
    with (
        patch("src.tmdb._get_arm_mal_id", new=AsyncMock(return_value=arm_mal)),
        patch("src.tmdb.httpx.AsyncClient.post", new=AsyncMock(side_effect=responses)) as post,
    ):
        result = asyncio.run(get_romaji("Astral Journey", 0, meta))
    assert result[1] == 234
    assert post.call_args.kwargs["json"]["variables"] == {"search": "Astral Journey"}


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ({"manual_season": "S03", "filename": "Astral.Journey.S02E01.mkv"}, 3),
        ({"manual_season": 0}, 0),
        ({"manual_season": "1-3", "filename": "Astral.Journey.S02E01.mkv"}, None),
        ({"filename": "Astral.Journey.S02E01.mkv"}, 2),
        ({"filename": "Astral.Journey.14.mkv"}, None),
        ({"season": "S04"}, 4),
        ({}, None),
    ],
)
def test_season_requires_explicit_evidence(values, expected):
    assert _expected_anime_season(Meta(**values)) == expected


@pytest.mark.parametrize("manual_mal", [None, 234])
def test_tmdb_metadata_uses_manual_season_and_preserves_manual_mal(tmp_path, manual_mal):
    urls = []

    async def get(_client, url, **_kwargs):
        urls.append(url)
        if "arm.haglund.dev" in url:
            payload = [mapping()]
        elif url.endswith("/external_ids"):
            payload = {"imdb_id": "tt0000789", "tvdb_id": 456}
        elif url.endswith("/tv/345"):
            payload = {
                "name": "Astral Journey",
                "first_air_date": "2025-01-01",
                "overview": "A fictional voyage.",
                "genres": [{"id": 16, "name": "Animation"}],
                "original_language": "ja",
            }
        else:
            payload = {}
        return httpx.Response(200, json=payload, request=httpx.Request("GET", url))

    with (
        patch("src.tmdb.httpx.AsyncClient.get", new=get),
        patch("src.tmdb.httpx.AsyncClient.post", new=AsyncMock(return_value=anime_response(mal=manual_mal or 123))) as post,
    ):
        result = asyncio.run(
            tmdb_other_meta(
                345,
                path="Astral.Journey.S01E01.mkv",
                category="TV",
                manual_season=2,
                mal_manual=manual_mal,
                base_dir=str(tmp_path),
            )
        )
    assert result["mal_id"] == (manual_mal or 123)
    assert post.call_args.kwargs["json"]["variables"] == {"search": manual_mal or 123}
    assert any("arm.haglund.dev" in url for url in urls) is (manual_mal is None)
