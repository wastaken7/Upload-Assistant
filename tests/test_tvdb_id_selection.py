from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

import src.tmdb as tmdb
import src.tvdb as tvdb
from src.meta import Meta
from src.prep_helpers import finalize_metadata

pytestmark = pytest.mark.asyncio


class StopAfterLookup(Exception):
    pass


@pytest.fixture
def prep():
    return SimpleNamespace(
        config={"DEFAULT": {}},
        tvdb_handler=SimpleNamespace(
            get_tvdb_by_external_id=AsyncMock(return_value=(None, None)),
            search_tvdb_series=AsyncMock(return_value=([], 789)),
        ),
        metadata_searching_manager=SimpleNamespace(get_tv_data=AsyncMock(side_effect=StopAfterLookup)),
    )


@pytest.fixture
def tmdb_external_ids(monkeypatch):
    external_ids = {}

    async def get(_client, url, **_kwargs):
        if url.endswith("/external_ids"):
            data = external_ids
        elif url.endswith("/345"):
            data = {"name": "Example Show", "first_air_date": "2025-01-01", "overview": "Example overview", "genres": []}
        else:
            data = {}
        return httpx.Response(200, json=data, request=httpx.Request("GET", url))

    monkeypatch.setattr(tmdb.httpx.AsyncClient, "get", get)
    monkeypatch.setattr(tmdb, "get_anime", AsyncMock(return_value=(0, "", False, "")))
    monkeypatch.setattr(tmdb, "default_config", {})
    return external_ids


@pytest.mark.parametrize(
    ("external_id", "expected"),
    [(456, 456), ("456", 456), (None, 0), ("", 0), ("null", 0), ("invalid", 0), (0, 0), (-1, 0), (True, 0), (456.5, 0)],
)
async def test_tmdb_accepts_numeric_and_string_tvdb_ids(tmp_path, tmdb_external_ids, external_id, expected):
    tmdb_external_ids["tvdb_id"] = external_id

    result = await tmdb.tmdb_other_meta(345, category="TV", base_dir=str(tmp_path))

    assert result["tvdb_id"] == expected


async def test_tmdb_preserves_provided_tvdb_id(tmp_path, tmdb_external_ids):
    tmdb_external_ids["tvdb_id"] = 456

    result = await tmdb.tmdb_other_meta(345, category="TV", tvdb_id=789, base_dir=str(tmp_path))

    assert result["tvdb_id"] == 789


async def test_tmdb_link_prevents_title_search_after_tvmaze_was_selected(tmp_path, tmdb_external_ids, prep):
    tmdb_external_ids["tvdb_id"] = 456
    meta = Meta(category="TV", tmdb_id=345, tvdb_id=0, tvmaze_id=123, base_dir=str(tmp_path), not_anime=True)

    await tmdb.set_tmdb_metadata(meta, "Example Show")
    with pytest.raises(StopAfterLookup):
        await finalize_metadata(prep, meta, "", {}, None, "Example Show", "", "")

    assert meta.tvdb_id == 456
    prep.tvdb_handler.get_tvdb_by_external_id.assert_not_awaited()
    prep.tvdb_handler.search_tvdb_series.assert_not_awaited()


@pytest.mark.parametrize("external_id", [456, None, RuntimeError("TVDB unavailable")])
async def test_missing_tvdb_tries_external_ids_before_title_search(prep, external_id):
    meta = Meta(category="TV", tmdb_id=345, imdb_id=1234567, tvdb_id=0, tvmaze_id=123, not_anime=True)
    external_lookup = prep.tvdb_handler.get_tvdb_by_external_id
    if isinstance(external_id, Exception):
        external_lookup.side_effect = external_id
    else:
        external_lookup.return_value = (external_id, "Example Show" if external_id else None)

    with pytest.raises(StopAfterLookup):
        await finalize_metadata(prep, meta, "", {}, None, "Example Show", "", "")

    external_lookup.assert_awaited_once_with(imdb=1234567, tmdb=345, tv_movie=False)
    if external_id == 456:
        assert meta.tvdb_id == 456
        assert meta.tvdb_series_name == "Example Show"
        prep.tvdb_handler.search_tvdb_series.assert_not_awaited()
    else:
        assert meta.tvdb_id == 789
        prep.tvdb_handler.search_tvdb_series.assert_awaited_once_with(filename="Example Show", year=meta.year)


@pytest.fixture
def tvdb_search(monkeypatch, tmp_path):
    search = AsyncMock()
    monkeypatch.setattr(tvdb, "_get_tvdb_or_warn", lambda _config: SimpleNamespace(search=search))
    handler = tvdb.TvdbData({"DEFAULT": {"metadata_cache_dir": str(tmp_path / "cache")}})
    return handler, search


@pytest.mark.parametrize("year", [2025, "2025"])
async def test_tvdb_does_not_choose_unrelated_title_with_matching_year(tvdb_search, year):
    handler, search = tvdb_search
    search.return_value = [
        {"tvdb_id": "999", "name": "Unrelated Show", "year": "2025"},
        {"tvdb_id": "456", "name": "Example Show", "year": "2025"},
    ]

    results, selected_id = await handler.search_tvdb_series("Example Show", year)

    assert selected_id == 456
    assert results == search.return_value


@pytest.mark.parametrize(
    "candidate",
    [
        {"name": "Unrelated Show", "year": "2025"},
        {"name": "Unrelated Show", "aliases": ["Unrelated Show (2025)"]},
        {"name": "Example Show", "year": "2010"},
        {"name": "Example Show", "year": "2010", "aliases": ["Unrelated Show (2025)"]},
    ],
)
async def test_tvdb_leaves_id_unset_without_matching_title_and_year(tvdb_search, candidate):
    handler, search = tvdb_search
    search.return_value = [{"tvdb_id": "999", **candidate}]

    results, selected_id = await handler.search_tvdb_series("Example Show", "2025")

    assert selected_id is None
    assert results == search.return_value


@pytest.mark.parametrize(
    "candidate",
    [
        {"name": "EXÁMPLE: Show (2025)", "year": "2025"},
        {"name": "Translated Title", "name_translated": "Example Show", "year": 2025},
        {"name": "Translated Title", "aliases": ["Example Show (2025)"]},
        {"name": "Translated Title", "aliases": [{"name": "Example Show (2025)", "language": "eng"}]},
        {"name": "Translated Title", "translations": {"eng": "Example Show"}, "year": "2025"},
    ],
)
async def test_tvdb_matches_normalized_names_aliases_and_translations(tvdb_search, candidate):
    handler, search = tvdb_search
    search.return_value = [{"tvdb_id": "456", **candidate}]

    _, selected_id = await handler.search_tvdb_series("Example Show", "2025")

    assert selected_id == 456


@pytest.mark.parametrize("year", [None, "2025"])
async def test_tvdb_does_not_select_ambiguous_title(tvdb_search, year):
    handler, search = tvdb_search
    search.return_value = [
        {"tvdb_id": "456", "name": "Example Show", "year": "2025"},
        {"tvdb_id": "789", "name": "Example Show", "year": "2025"},
    ]

    _, selected_id = await handler.search_tvdb_series("Example Show", year)

    assert selected_id is None


@pytest.mark.parametrize("query", ["Example Show", "示例节目"])
async def test_tvdb_matches_without_year(tvdb_search, query):
    handler, search = tvdb_search
    search.return_value = [{"tvdb_id": "456", "name": query}]

    _, selected_id = await handler.search_tvdb_series(query)

    assert selected_id == 456


@pytest.mark.parametrize(
    ("query", "name"),
    [
        ("Examples Show", "Example's Show"),
        ("Examples Show", "Example\u2019s Show"),
        ("Example's Show", "Examples Show"),
    ],
)
async def test_tvdb_matches_titles_without_apostrophes(tvdb_search, query, name):
    handler, search = tvdb_search
    search.return_value = [{"tvdb_id": "456", "name": name, "year": "2025"}]

    _, selected_id = await handler.search_tvdb_series(query, "2025")

    assert selected_id == 456
