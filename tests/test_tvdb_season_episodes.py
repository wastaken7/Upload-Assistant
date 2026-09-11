# ruff: noqa: S101
import asyncio

import httpx
import pytest

from src import tvdb as tvdb_module
from src.tvdb import TVDB, TvdbData


def _payload(numbers, next_page=None):
    return {
        "data": {"episodes": [{"seasonNumber": 3, "number": number} for number in numbers]},
        "links": {"next": next_page},
    }


def _fetch(monkeypatch, responses):
    requests = []

    def respond(request):
        requests.append(request)
        response = responses[len(requests) - 1]
        if isinstance(response, int):
            return httpx.Response(response)
        return httpx.Response(200, json=response)

    async def run():
        client = TVDB.__new__(TVDB)
        client.token = "test-token"
        client._client = httpx.AsyncClient(base_url="https://api4.thetvdb.com/v4", transport=httpx.MockTransport(respond))
        monkeypatch.setattr(tvdb_module, "_get_tvdb_or_warn", lambda _config: client)
        try:
            return await TvdbData({}).get_season_episode_numbers(123, 3)
        finally:
            await client.aclose()

    return asyncio.run(run()), requests


def test_season_lookup_uses_links_even_on_short_pages(monkeypatch):
    result, requests = _fetch(monkeypatch, [_payload([1, 2], "?page=1"), _payload([2, 3])])
    assert result == [1, 2, 3]
    assert len(requests) == 2
    for page, request in enumerate(requests):
        assert request.url.path == "/v4/series/123/episodes/default"
        assert dict(request.url.params) == {"page": str(page), "season": "3"}
        assert "include_links" not in request.url.params


def test_season_lookup_ignores_other_seasons_and_deduplicates(monkeypatch):
    payload = _payload([2, 1, 1])
    payload["data"]["episodes"].append({"seasonNumber": 0, "number": 4})
    result, _ = _fetch(monkeypatch, [payload])
    assert result == [1, 2]


def test_failed_later_page_does_not_return_partial_episode_count(monkeypatch):
    result, requests = _fetch(monkeypatch, [_payload([1, 2], "?page=1"), 503])
    assert result is None
    assert len(requests) == 2


@pytest.mark.parametrize("response", [
    401, 503, _payload([]),
    {"data": {"episodes": [{"seasonNumber": 3}]}, "links": {"next": None}},
    {"data": {"episodes": ["bad record"]}, "links": {"next": None}},
    {"data": {"episodes": []}},
    {"data": None, "links": {"next": None}},
    _payload([], "?page=1"),
])
def test_unavailable_or_malformed_data_is_not_a_complete_season(monkeypatch, response):
    result, _ = _fetch(monkeypatch, [response])
    assert result is None


def test_missing_client_skips_tvdb_verification(monkeypatch):
    monkeypatch.setattr(tvdb_module, "_get_tvdb_or_warn", lambda _config: None)
    assert asyncio.run(TvdbData({}).get_season_episode_numbers(123, 3)) is None


def test_pagination_limit_does_not_return_partial_episode_count(monkeypatch):
    result, requests = _fetch(monkeypatch, [_payload([page + 1], f"?page={page + 1}") for page in range(100)])
    assert result is None
    assert len(requests) == 100


def test_existing_episode_api_still_returns_data_only(monkeypatch):
    async def run():
        client = TVDB.__new__(TVDB)
        client.token = "test-token"
        payload = _payload([1, 2])
        client._client = httpx.AsyncClient(
            base_url="https://api4.thetvdb.com/v4", transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload)),
        )
        try:
            assert await client.get_series_episodes(123) == payload["data"]
        finally:
            await client.aclose()

    asyncio.run(run())


@pytest.mark.parametrize("multipage", [False, True])
def test_season_lookup_accepts_final_page_without_next_link(monkeypatch, multipage):
    last_page = _payload([2, 3])
    last_page["links"] = {"self": "?page=1" if multipage else "?page=0"}
    responses = [_payload([1, 2], "?page=1"), last_page] if multipage else [last_page]
    result, requests = _fetch(monkeypatch, responses)
    assert result == ([1, 2, 3] if multipage else [2, 3])
    assert len(requests) == len(responses)
