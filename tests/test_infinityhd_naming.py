"""Exercise InfinityHD's exact-prefix fallback with actual Meta/shared templates."""
# ruff: noqa: S101
import asyncio
from functools import partial
from unittest.mock import AsyncMock

import httpx
import pytest

from src.get_name import NameManager
from src.meta import Meta
from src.trackers import naming
from src.trackers.UNIT3D.infinityhd import InfinityHD

CONFIG = {'DEFAULT': {'tmdb_api': 'offline-fixture'}, 'TRACKERS': {'INFINITYHD': {}}}


@pytest.fixture(autouse=True)
def isolate_tv_fallback(monkeypatch, request):
    """Isolate fallback cases while retaining explicit real-rebuild integration tests."""
    # Existing ordering fixtures represent a homonymous show; keep the real
    # year policy and TMDB response parsing, substituting only HTTP transport.
    def handle(request):
        title = request.url.params['query']
        return httpx.Response(200, json={'results': [
            {'id': 10, 'name': title}, {'id': 20, 'name': title}], 'total_pages': 1})

    monkeypatch.setattr(naming.httpx, 'AsyncClient', partial(httpx.AsyncClient, transport=httpx.MockTransport(handle)))
    # Upstream now rebuilds normal TV names from TMDB/IMDb. Exercise only the
    # fallback here; separate integration cases below keep that real path intact.
    if request.node.name not in {'test_real_no_marker_fallback', 'test_existing_tv_rebuild_takes_precedence'}:
        monkeypatch.setattr(InfinityHD, '_rebuild_tv_name', AsyncMock(return_value=None))


def test_generated_tv_year_follows_aka():
    """Place the generated TV year after AKA without mutating metadata."""
    meta = Meta(title='Title', aka='AKA Alternate', year=2024,
                category='TV', type='WEBDL', search_year=2024,
                season='S01', episode='E02', episode_title='Pilot',
                resolution='1080p', service='NF', audio='DDP5.1',
                video_encode='H.264', tag='-GROUP',
                language_checked=True, audio_languages=['English'])
    meta.name = asyncio.run(NameManager(CONFIG).get_name(meta))[1]
    assert meta.name == 'Title 2024 AKA Alternate S01E02 1080p NF WEB-DL DDP5.1 H.264-GROUP'
    before = meta.to_dict()
    result = asyncio.run(InfinityHD(CONFIG).get_name(meta))
    assert result == {'name': 'Title AKA Alternate 2024 S01E02 1080p NF WEB-DL DDP5.1 H.264-GROUP'}
    assert meta.to_dict() == before


@pytest.mark.parametrize('title,aka,year', [
    ('1984', 'AKA Nineteen Eighty-Four', 1984),
    ('2001: A Space Odyssey', 'AKA 2001 A Space Odyssey', 1968),
    ('Class of 2024', 'AKA 2024 2024', 2024),
    ('1917', 'AKA 1917', 2019),
    ('[Title] (Part 2)', 'AKA Alternate [2024] (Part 3)', 2024),
    ('Title', 'AKA Alternate AKA Another 2024', 2024),
])
def test_moves_only_metadata_year_preserving_title_and_aka_digits(title, aka, year):
    """Move only the metadata year and preserve numeric titles and suffixes."""
    suffix = ' S02E03 Episode 2024 REPACK Extended 2160p NF WEB-DL DDP5.1 DV H.265-GROUP'
    meta = Meta(title=title, aka=aka, year=year, category='TV', search_year=year,
                name=f'{title} {year} {aka}{suffix}', resolution='2160p',
                language_checked=True, audio_languages=['English'])
    before = meta.to_dict()
    tracker = InfinityHD(CONFIG)
    result = asyncio.run(tracker.get_name(meta))
    assert result == {'name': f'{title} {aka} {year}{suffix}'}
    assert meta.to_dict() == before
    meta.name = result['name']
    assert asyncio.run(tracker.get_name(meta)) == result


@pytest.mark.parametrize('name,overrides', [
    ('Title 2024 1080p WEB-DL-GROUP', {'aka': ''}),
    ('Title AKA Alternate 1080p WEB-DL-GROUP', {'year': None}),
    ('Title AKA Alternate 2024 1080p WEB-DL-GROUP', {}),
    ('Title 2024 AKA Alternate 1080p WEB-DL-GROUP', {'no_aka': True}),
    ('Title 2024 AKA Alternate 1080p WEB-DL-GROUP', {'no_year': True}),
    ('Title 2024 AKA Alternate 1080p WEB-DL-GROUP', {'search_year': ''}),
    ('Custom 2024 AKA Alternate 1080p WEB-DL-GROUP', {}),
    ('Title 2024 AKA AlternateX 1080p WEB-DL-GROUP', {}),
    ('Title 2024 AKA Alternate', {}),
    ('Title 2024 AKA Alternate 1080p WEB-DL-GROUP', {'aka': ''}),
])
def test_unchanged_names_and_exact_aka_boundary(name, overrides):
    """Preserve disabled, unmatched, and already-normalized prefixes."""
    values = {'title': 'Title', 'aka': 'AKA Alternate', 'year': 2024, 'category': 'TV',
              'search_year': 2024, 'name': name, 'resolution': '1080p',
              'language_checked': True, 'audio_languages': ['English']}
    values.update(overrides)
    meta = Meta(**values)
    expected = 'Title AKA Alternate 2024' if name == 'Title 2024 AKA Alternate' else name
    assert asyncio.run(InfinityHD(CONFIG).get_name(meta)) == {'name': expected}


@pytest.mark.parametrize('languages,label', [
    (['French'], 'FRENCH '), (['Japanese', 'French'], 'JAPANESE '),
    (['French', 'English'], ''), (['English'], ''), ([], ''),
])
def test_preserves_existing_language_insertion(languages, label):
    """Keep existing non-English audio language labels in the release suffix."""
    meta = Meta(title='Title', aka='AKA Alternate', year=2024, category='TV',
                search_year=2024, name='Title 2024 AKA Alternate S01E02 1080p WEB-DL-GROUP',
                resolution='1080p', language_checked=True, audio_languages=languages)
    assert asyncio.run(InfinityHD(CONFIG).get_name(meta)) == {
        'name': f'Title AKA Alternate 2024 S01E02 {label}1080p WEB-DL-GROUP'}


@pytest.mark.parametrize('category,release_type,is_disc', [
    ('TV', 'WEBDL', ''), ('TV', 'WEBRIP', ''), ('TV', 'ENCODE', ''),
    ('TV', 'REMUX', ''), ('TV', 'DISC', 'DVD'), ('TV', 'DISC', 'BDMV'),
    ('TV', 'HDTV', ''), ('TV', 'DVDRIP', ''),
    ('MOVIE', 'WEBDL', ''), ('MOVIE', 'REMUX', ''), ('MOVIE', 'DISC', 'BDMV'),
])
def test_real_shared_templates_keep_suffix_and_movie_names(category, release_type, is_disc):
    """Normalize actual shared templates without changing their release suffixes."""
    meta = Meta(title='Title 1984', aka='AKA Alternate 2001', year=2024,
                category=category, type=release_type, is_disc=is_disc,
                search_year=2024, season='S02', episode='E03',
                manual_episode_title='Episode 2024', edition='Extended', repack='REPACK',
                resolution='1080p', source='BluRay', service='NF',
                audio='DDP5.1', video_encode='H.264', video_codec='AVC', tag='-GROUP',
                language_checked=True, audio_languages=['English'])
    meta.name = asyncio.run(NameManager(CONFIG).get_name(meta))[1]
    old_prefix = 'Title 1984 2024 AKA Alternate 2001'
    new_prefix = 'Title 1984 AKA Alternate 2001 2024'
    expected = new_prefix + meta.name[len(old_prefix):] if meta.name.startswith(old_prefix) else meta.name
    assert expected.startswith(new_prefix)
    before = meta.to_dict()
    assert asyncio.run(InfinityHD(CONFIG).get_name(meta)) == {'name': expected}
    assert meta.to_dict() == before


@pytest.mark.parametrize('category,manual_year,effective_year', [
    ('MOVIE', 2025, 2025), ('TV', 2025, 2024),
])
def test_uses_shared_effective_year_rules(category, manual_year, effective_year):
    """Respect existing movie manual-year and TV search-year semantics."""
    meta = Meta(title='Title', aka='AKA Alternate', year=2024,
                manual_year=manual_year, category=category, search_year=2024,
                name=f'Title {effective_year} AKA Alternate S01 1080p-GROUP',
                resolution='1080p', language_checked=True, audio_languages=['English'])
    assert asyncio.run(InfinityHD(CONFIG).get_name(meta)) == {
        'name': f'Title AKA Alternate {effective_year} S01 1080p-GROUP'}


def test_real_no_marker_fallback():
    """Normalize the actual TV fallback when no season marker is present."""
    meta = Meta(title='Title', aka='AKA Alternate', year=2024,
                category='TV', search_year=2024,
                name='Title 2024 AKA Alternate 1080p WEB-DL-GROUP',
                resolution='1080p', language_checked=True, audio_languages=['English'])
    before = meta.to_dict()
    assert asyncio.run(InfinityHD(CONFIG).get_name(meta)) == {
        'name': 'Title AKA Alternate 2024 1080p WEB-DL-GROUP'}
    assert meta.to_dict() == before


def test_existing_tv_rebuild_takes_precedence(monkeypatch):
    """Preserve the localized title produced by the existing TV rebuild."""
    meta = Meta(title='Metadata Title', aka='AKA Metadata Alternate', year=2024,
                category='TV', search_year=2024, season='S01',
                name='Metadata Title 2024 AKA Metadata Alternate S01 1080p WEB-DL-GROUP',
                imdb_info={'title': 'Localized Title', 'aka': 'Localized Alternate'},
                original_language='en', resolution='1080p',
                language_checked=True, audio_languages=['English'])
    adapter = InfinityHD(CONFIG)
    monkeypatch.setattr(naming, 'get_tmdb_localized_data', AsyncMock(return_value={'name': 'Localized Title'}))
    before = meta.to_dict()
    assert asyncio.run(adapter.get_name(meta)) == {
        'name': 'Localized Title AKA Localized Alternate 2024 S01 1080p WEB-DL-GROUP'}
    assert meta.to_dict() == before


def test_manual_name_with_attached_configured_tag_is_verbatim():
    """Keep a manual name verbatim even when its prefix could be reordered."""
    meta = Meta(title='Title', aka='AKA Alternate', year=2024,
                category='TV', search_year=2024,
                manual_name='Title 2024 AKA Alternate-GROUP', tag='-GROUP',
                resolution='1080p', language_checked=True, audio_languages=['English'])
    meta.name = asyncio.run(NameManager(CONFIG).get_name(meta))[1]
    assert meta.name == 'Title 2024 AKA Alternate-GROUP'
    before = meta.to_dict()
    assert asyncio.run(InfinityHD(CONFIG).get_name(meta)) == {
        'name': 'Title 2024 AKA Alternate-GROUP'}
    assert meta.to_dict() == before


@pytest.mark.parametrize('suffix,tag', [
    ('-OTHER', '-GROUP'), ('-GROUP-extra', '-GROUP'), ('-GROUP', ''),
])
def test_rejects_unconfigured_attached_suffix(suffix, tag):
    """Do not treat arbitrary hyphens or partial group matches as boundaries."""
    name = 'Title 2024 AKA Alternate' + suffix
    meta = Meta(title='Title', aka='AKA Alternate', year=2024,
                category='TV', search_year=2024, name=name, tag=tag,
                resolution='1080p', language_checked=True, audio_languages=['English'])
    assert asyncio.run(InfinityHD(CONFIG).get_name(meta)) == {'name': name}


def test_matches_shared_whitespace_normalization():
    """Match metadata prefixes using shared whitespace normalization."""
    meta = Meta(title='Title  Two', aka='AKA  Alternate', year=2024,
                category='TV', search_year=2024,
                name='Title Two 2024 AKA Alternate S01 1080p-GROUP',
                resolution='1080p', language_checked=True)
    assert asyncio.run(InfinityHD(CONFIG).get_name(meta)) == {
        'name': 'Title Two AKA Alternate 2024 S01 1080p-GROUP'}
