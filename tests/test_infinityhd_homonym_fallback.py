"""Exercise real tracker/shared naming against a disposable TMDB HTTP boundary."""
# ruff: noqa: S101
import asyncio
from functools import partial

import httpx
import pytest

from src.get_name import NameManager
from src.meta import Meta
from src.trackers import naming
from src.trackers.UNIT3D.infinityhd import InfinityHD

CONFIG = {'DEFAULT': {'tmdb_api': 'offline-fixture'}, 'TRACKERS': {'INFINITYHD': {}}}


@pytest.fixture
def tmdb(monkeypatch):
    calls = []
    state = {'homonym': False, 'failure': False}

    def handle(request):
        calls.append(request)
        assert request.url.path == '/3/search/tv'
        assert request.url.params['query'] == 'Title'
        assert request.url.params['api_key'] == 'offline-fixture'
        if state['failure']:
            return httpx.Response(503)
        results = [{'id': 10, 'name': 'Title'}]
        if state['homonym']:
            results.append({'id': 20, 'name': 'Title'})
        else:
            results.append({'id': 30, 'name': 'Title Again'})
        return httpx.Response(200, json={'results': results, 'total_pages': 1})

    monkeypatch.setattr(naming.httpx, 'AsyncClient', partial(httpx.AsyncClient, transport=httpx.MockTransport(handle)))
    return state, calls


def fallback_meta(**overrides):
    values = {'title': 'Title', 'aka': 'AKA Alternate', 'year': 2024, 'search_year': 2024,
              'tmdb_id': 10, 'category': 'TV', 'resolution': '1080p', 'tag': '-GROUP',
              'language_checked': True, 'audio_languages': ['English'],
              'name': 'Title 2024 AKA Alternate 1080p WEB-DL-GROUP'}
    values.update(overrides)
    return Meta(**values)


@pytest.mark.parametrize('failure,configured', [(False, True), (True, True), (False, False)])
@pytest.mark.parametrize('suffix', [' 1080p WEB-DL-GROUP', '-GROUP', ''])
def test_no_marker_fallback_omits_year_without_exact_homonym(tmdb, failure, configured, suffix):
    tmdb[0]['failure'] = failure
    config = CONFIG if configured else {'DEFAULT': {}, 'TRACKERS': {'INFINITYHD': {}}}
    meta = fallback_meta(name='Title 2024 AKA Alternate' + suffix)
    before = meta.to_dict()
    assert asyncio.run(InfinityHD(config).get_name(meta)) == {
        'name': 'Title AKA Alternate' + suffix}
    assert len(tmdb[1]) == int(configured)
    assert meta.to_dict() == before


@pytest.mark.parametrize('suffix', [' 1080p WEB-DL-GROUP', '-GROUP', ''])
def test_real_homonym_keeps_year_after_aka(tmdb, suffix):
    tmdb[0]['homonym'] = True
    meta = fallback_meta(name='Title 2024 AKA Alternate' + suffix)
    assert asyncio.run(InfinityHD(CONFIG).get_name(meta)) == {
        'name': 'Title AKA Alternate 2024' + suffix}
    assert len(tmdb[1]) == 1


@pytest.mark.parametrize('overrides', [
    {'no_year': True}, {'no_aka': True}, {'aka': ''}, {'search_year': ''},
    {'year': None}, {'category': 'MOVIE'},
    {'name': 'Title 2024 AKA Alternate-OTHER'},
    {'name': 'Title 2024 AKA Alternate-GROUP-extra'},
    {'name': 'Title 2024 AKA AlternateX 1080p'},
    {'name': 'Title 2024 AKA Alternate-GROUP', 'tag': ''},
])
def test_fallback_preserves_disabled_flags_movies_and_exact_boundaries(tmdb, overrides):
    meta = fallback_meta(**overrides)
    expected = meta.name
    if meta.category == 'MOVIE':
        expected = 'Title AKA Alternate 2024 1080p WEB-DL-GROUP'
    assert asyncio.run(InfinityHD(CONFIG).get_name(meta)) == {'name': expected}
    assert tmdb[1] == []


@pytest.mark.parametrize('homonym', [False, True])
def test_real_shared_manual_name_is_verbatim(tmdb, homonym):
    tmdb[0]['homonym'] = homonym
    meta = fallback_meta(manual_name='Title 2024 AKA Alternate-GROUP')
    meta.name = asyncio.run(NameManager(CONFIG).get_name(meta))[1]
    assert meta.name == 'Title 2024 AKA Alternate-GROUP'
    assert asyncio.run(InfinityHD(CONFIG).get_name(meta)) == {
        'name': 'Title 2024 AKA Alternate-GROUP'}
    assert tmdb[1] == []


@pytest.mark.parametrize('homonym', [False, True])
def test_real_rebuild_remains_authoritative(tmdb, monkeypatch, homonym):
    tmdb[0]['homonym'] = homonym

    async def localized_data(meta, **kwargs):
        assert meta.tmdb_id == 10
        assert kwargs == {'data_type': 'main', 'language': 'en-US', 'append_to_response': ''}
        return {'name': 'Title'}

    monkeypatch.setattr(naming, 'get_tmdb_localized_data', localized_data)
    meta = fallback_meta(title='Metadata Title', season='S01', episode='E02',
                         name='Metadata Title 2024 AKA Metadata Alternate S01E02 1080p WEB-DL-GROUP',
                         imdb_info={'title': 'Title', 'aka': 'Localized Alternate'}, original_language='en')
    before = meta.to_dict()
    year = ' 2024' if homonym else ''
    assert asyncio.run(InfinityHD(CONFIG).get_name(meta)) == {
        'name': f'Title AKA Localized Alternate{year} S01E02 1080p WEB-DL-GROUP'}
    assert len(tmdb[1]) == 1
    assert meta.to_dict() == before
