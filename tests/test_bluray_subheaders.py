import asyncio
import inspect
import json
from unittest.mock import AsyncMock

import pytest

from src.args import Args
from src.bluray_com import (
    ensure_release_subheader,
    find_bluray_url,
    get_bluray_releases,
    normalize_bluray_url,
    parse_release_details,
    process_all_releases,
    reset_release_subheader_cache,
    set_selected_release,
    use_bluray_url,
)
from src.get_desc import DescriptionBuilder
from src.meta import Meta

URL = 'https://www.blu-ray.com/movies/Example-Series-Blu-ray/123456/'
LABEL = 'Example Studio | 1981 | Season 1 | 159 min | Rated: PG | Sep 07, 2020'
# Generic content using the verified release-page structure, independent of technical specs.
HTML = '''<h1>Example Series Blu-ray</h1>
<span class="subheading grey">
<a class="grey">Example Studio</a> | <a>1981</a> | Season 1 | <span id="runtime">159 min</span> |
Rated: PG | <a>Sep 07, 2020</a></span>'''


def builder(tracker='AITHER', enabled=True):
    return DescriptionBuilder(tracker, {'DEFAULT': {'add_bluray_link': enabled, 'use_bluray_images': False}, 'TRACKERS': {tracker: {}}})


def release(**kwargs):
    return dict(title='Example Series', url=URL, country='United Kingdom', publisher='Example Studio', price='', release_id='123456', **kwargs)


@pytest.fixture
def manual_release_selection(tmp_path, monkeypatch):
    folder = tmp_path / 'tmp' / 'test'
    folder.mkdir(parents=True)
    (folder / 'debug_bluray_BD_123.html').write_text('Cached release list')
    monkeypatch.setattr('src.bluray_com.search_bluray', AsyncMock(return_value='Search results'))
    monkeypatch.setattr('src.bluray_com.extract_bluray_links', lambda _: [{'releases_url': 'https://www.blu-ray.com/Example/123/', 'title': 'Example', 'year': '1981'}])
    releases = AsyncMock()
    monkeypatch.setattr('src.bluray_com.extract_bluray_release_info', releases)
    monkeypatch.setattr('src.bluray_com.cli_ui.ask_string', lambda _: '1')
    return releases


@pytest.fixture
def select_release(request, monkeypatch, selection):
    if selection == 'manual':
        releases = request.getfixturevalue('manual_release_selection')

        async def select(meta, selected):
            releases.return_value = [selected]
            await get_bluray_releases(meta)
    else:
        monkeypatch.setattr('src.bluray_com.fetch_release_details', AsyncMock(side_effect=lambda selected, _: selected))

        async def select(meta, selected):
            await process_all_releases([selected], meta)

    return select


@pytest.mark.asyncio
async def test_subheader_without_specs_and_with_entities():
    result = await parse_release_details(HTML, release(), Meta())
    assert result['subheader'] == LABEL
    result = await parse_release_details(HTML.replace('Example Studio', 'Example Studio &amp; <b>Partners</b>'), release(), Meta())
    assert result['subheader'] == LABEL.replace('Example Studio', 'Example Studio & Partners')
    result = await parse_release_details('<span class="subheading">Video</span>', release(subheader='Old'), Meta())
    assert result['subheader'] == ''


@pytest.mark.asyncio
@pytest.mark.parametrize('tracker', ['AITHER', 'TORRENTLEECH', 'IMMORTALSEED'])
async def test_description_renders_selected_label(tmp_path, monkeypatch, tracker):
    fetched = AsyncMock(return_value=release(subheader=LABEL))
    monkeypatch.setattr('src.bluray_com.fetch_release_details', fetched)
    meta = Meta(is_disc='BDMV', release_url=URL, base_dir=str(tmp_path), uuid='test')
    desc = builder(tracker)
    kwargs = {name: False for name, parameter in inspect.signature(desc.general_description_generator).parameters.items() if parameter.default is True}
    kwargs['bluray'] = True
    output = await desc.general_description_generator(meta, **kwargs)
    if tracker == 'AITHER':
        assert f'[url={URL}]{LABEL}[/url]' in output
    elif tracker == 'TORRENTLEECH':
        assert f'<a href="{URL}">{LABEL}</a>' in output
    else:
        assert f'{LABEL} — {URL}' in output
    await desc.get_bluray_section(meta)
    fetched.assert_awaited_once()


@pytest.mark.asyncio
async def test_disabled_links_do_not_fetch(tmp_path, monkeypatch):
    fetched = AsyncMock()
    monkeypatch.setattr('src.bluray_com.fetch_release_details', fetched)
    assert await builder(enabled=False).get_bluray_section(Meta(is_disc='BDMV', release_url=URL, base_dir=str(tmp_path))) == ('', '')
    fetched.assert_not_awaited()


@pytest.mark.asyncio
async def test_selection_changes_clear_stale_labels(monkeypatch):
    meta = Meta()
    set_selected_release(meta, release(subheader=LABEL))
    assert meta.release_subheader_url == URL
    new_url = URL.replace('123456', '999')
    set_selected_release(meta, {'url': new_url})
    assert meta.release_subheader == meta.release_subheader_url == ''
    monkeypatch.setattr('src.bluray_com.fetch_release_details', AsyncMock(return_value={'url': new_url, 'subheader': 'New release'}))
    await ensure_release_subheader(meta)
    assert meta.release_subheader == 'New release'
    assert meta.release_subheader_url == new_url


@pytest.mark.asyncio
async def test_fetch_failure_keeps_url_fallback(monkeypatch):
    monkeypatch.setattr('src.bluray_com.fetch_release_details', AsyncMock(side_effect=RuntimeError('offline')))
    meta = Meta(release_url=URL, release_subheader='Old label', release_subheader_url='old')
    await ensure_release_subheader(meta)
    assert meta.release_url == URL
    assert meta.release_subheader == ''
    assert builder().format_bluray_link(meta.release_url, meta.release_subheader) == f'[url]{URL}[/url]'


@pytest.mark.asyncio
async def test_absent_subheader_is_not_refetched(monkeypatch):
    fetched = AsyncMock(return_value=release(subheader=''))
    monkeypatch.setattr('src.bluray_com.fetch_release_details', fetched)
    meta = Meta(release_url=URL)
    await ensure_release_subheader(meta)
    await ensure_release_subheader(meta)
    fetched.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize('distributor', ['', 'CUSTOM DISTRIBUTOR'])
@pytest.mark.parametrize('region, expected', [('', 'GBR'), ('USA', 'USA')])
async def test_manual_selection_without_covers_fetches_label_on_demand(tmp_path, monkeypatch, manual_release_selection, region, expected, distributor):
    manual_release_selection.return_value = [release()]
    fetched = AsyncMock(return_value=release(subheader=LABEL))
    monkeypatch.setattr('src.bluray_com.fetch_release_details', fetched)
    meta, _, _ = Args({'DEFAULT': {'screens': 1}}).parse([str(tmp_path)] + (['--region', region.lower()] if region else []) + (['--distributor', distributor.lower()] if distributor else []), Meta(base_dir=str(tmp_path), uuid='test', is_disc='BDMV', use_bluray_images=False))
    await get_bluray_releases(meta)
    assert meta.region == expected
    assert meta.distributor == (distributor or 'EXAMPLE STUDIO')
    assert meta.release_url == URL
    fetched.assert_not_awaited()
    await builder().get_bluray_section(meta)
    assert meta.release_subheader == LABEL
    fetched.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize('distributor', ['', 'CUSTOM DISTRIBUTOR'])
@pytest.mark.parametrize('region, expected', [('', 'GBR'), ('USA', 'USA')])
async def test_automatic_selection_carries_subheader(tmp_path, monkeypatch, region, expected, distributor):
    monkeypatch.setattr('src.bluray_com.fetch_release_details', AsyncMock(return_value=release(subheader=LABEL)))
    meta = Meta(base_dir=str(tmp_path), uuid='test', is_disc='BDMV', unattended=True, bluray_single_score=1, region=region, distributor=distributor)
    await process_all_releases([release()], meta)
    assert meta.region == expected
    assert meta.distributor == (distributor or 'EXAMPLE STUDIO')
    assert meta.release_url == URL
    assert meta.release_subheader == LABEL
    assert meta.release_subheader_url == URL


@pytest.mark.asyncio
@pytest.mark.parametrize('selection', ['manual', 'automatic'])
@pytest.mark.parametrize('region', ['', 'USA'])
@pytest.mark.parametrize('country, code', [
    ('Bulgaria', 'BGR'),
    ('Chinese Taipei', 'TWN'),
    ('Czech Republic', 'CZE'),
    ('Denmark', 'DNK'),
    ('Estonia', 'EST'),
    ('Finland', 'FIN'),
    ('Latvia', 'LVA'),
    ('Lithuania', 'LTU'),
    ('Slovakia', 'SVK'),
    ('Sweden', 'SWE'),
    ('Taiwan', 'TWN'),
])
async def test_release_sets_disc_region(tmp_path, select_release, selection, region, country, code):
    selected = release() | {'country': country}
    meta = Meta(base_dir=str(tmp_path), uuid='test', is_disc='BDMV', unattended=selection == 'automatic', bluray_single_score=1, region=region)

    await select_release(meta, selected)

    assert meta.region == (region or code)
    assert meta.distributor == 'EXAMPLE STUDIO'
    assert meta.release_url == URL


@pytest.mark.asyncio
@pytest.mark.parametrize('selection', ['manual', 'automatic'])
@pytest.mark.parametrize('restore', [False, True])
@pytest.mark.parametrize('overrides', [(), ('region',), ('distributor',), ('region', 'distributor')])
async def test_reselection_refreshes_auto_metadata_and_preserves_cli_overrides(tmp_path, select_release, selection, restore, overrides):
    first = release(subheader=LABEL)
    second = release(subheader='Other Studio | US release') | {
        'url': URL.replace('123456', '999'),
        'release_id': '999',
        'country': 'United States',
        'publisher': 'Other Studio',
    }
    meta = Meta(base_dir=str(tmp_path), uuid='test', is_disc='BDMV', unattended=selection == 'automatic', bluray_single_score=1)
    await select_release(meta, first)
    assert (meta.region, meta.distributor) == ('GBR', 'EXAMPLE STUDIO')

    # An explicit override must be preserved even when it equals the auto-filled value.
    if overrides:
        args = [str(tmp_path)]
        if selection == 'automatic':
            args.append('--unattended')
        for field in overrides:
            args.extend([f'--{field}', getattr(meta, field).lower()])
        meta, _, _ = Args({'DEFAULT': {'screens': 1}}).parse(args, meta)
    if restore:
        meta = Meta(json.loads(json.dumps(meta.to_dict())))
    meta.edit = True
    await select_release(meta, second)

    assert meta.region == ('GBR' if 'region' in overrides else 'USA')
    assert meta.distributor == ('EXAMPLE STUDIO' if 'distributor' in overrides else 'OTHER STUDIO')
    assert meta.release_url == second['url']
    # Manual selection fetches the label on demand; automatic selection carries it.
    await ensure_release_subheader(meta)
    assert meta.release_subheader == second['subheader']
    assert meta.release_subheader_url == second['url']


def test_html_and_bbcode_labels_are_text():
    assert '&amp;' in builder('TORRENTLEECH').format_bluray_link(URL, 'A & B')
    assert '&#91;b&#93;' in builder().format_bluray_link(URL, '[b]Studio')
    assert builder('IMMORTALSEED').format_bluray_link(URL, '') == URL
    assert Meta({'release_url': URL}).release_subheader == ''


@pytest.mark.asyncio
@pytest.mark.parametrize('is_disc', ['BDMV', 'DVD'])
@pytest.mark.parametrize('raises', [True, False])
async def test_failed_subheader_fetch_is_cached_until_next_preparation(tmp_path, monkeypatch, is_disc, raises):
    from src.prep import Prep

    async def fail(release, _meta):
        if raises:
            raise RuntimeError('offline')
        return release

    fetched = AsyncMock(side_effect=fail)
    monkeypatch.setattr('src.bluray_com.fetch_release_details', fetched)
    meta = Meta(is_disc=is_disc, release_url=URL, base_dir=str(tmp_path))
    original_metadata = meta.to_dict()
    for tracker in ('AITHER', 'TORRENTLEECH'):
        assert (await builder(tracker).get_bluray_section(meta))[0] == URL
    fetched.assert_awaited_once()
    assert meta.to_dict() == original_metadata

    # A separately loaded metadata object in this run shares the failure cache.
    restored = Meta(meta.to_dict())
    await builder().get_bluray_section(restored)
    fetched.assert_awaited_once()

    # Exercise the actual run boundary, stopping before unrelated preparation.
    class PreparationStopped(Exception):
        pass

    def stop_preparation(*_args):
        raise PreparationStopped

    monkeypatch.setattr('src.prep.prep_helpers.init_meta', stop_preparation)
    with pytest.raises(PreparationStopped):
        await Prep.__new__(Prep).gather_prep(restored, 'cli')
    fetched.side_effect = None
    fetched.return_value = release(subheader=LABEL)
    await builder().get_bluray_section(restored)
    assert fetched.await_count == 2
    assert restored.release_subheader == LABEL


@pytest.mark.asyncio
async def test_failed_url_does_not_block_another_release(monkeypatch):
    fetched = AsyncMock(side_effect=RuntimeError('offline'))
    monkeypatch.setattr('src.bluray_com.fetch_release_details', fetched)
    meta = Meta(release_url=URL)
    await ensure_release_subheader(meta)
    other_url = URL.replace('123456', '999')
    fetched.side_effect = None
    fetched.return_value = {'url': other_url, 'subheader': 'Another example release'}
    set_selected_release(meta, {'url': other_url})
    await ensure_release_subheader(meta)
    assert fetched.await_count == 2
    assert meta.release_subheader == 'Another example release'
    set_selected_release(meta, {'url': URL})
    await ensure_release_subheader(meta)
    assert fetched.await_count == 2
    assert meta.release_subheader == ''


@pytest.mark.asyncio
async def test_failure_caches_are_isolated_between_concurrent_runs(monkeypatch):
    fetched = AsyncMock(side_effect=[RuntimeError('offline'), release(subheader=LABEL)])
    monkeypatch.setattr('src.bluray_com.fetch_release_details', fetched)
    first_failed = asyncio.Event()
    second_finished = asyncio.Event()

    async def first_run():
        reset_release_subheader_cache()
        await ensure_release_subheader(Meta(release_url=URL))
        first_failed.set()
        await second_finished.wait()
        await ensure_release_subheader(Meta(release_url=URL))

    async def second_run():
        await first_failed.wait()
        reset_release_subheader_cache()
        await ensure_release_subheader(Meta(release_url=URL))
        second_finished.set()

    await asyncio.gather(first_run(), second_run())
    assert fetched.await_count == 2


EDITION_HTML = HTML.replace('</h1>', '</h1>\n<img src="https://images.static-bluray.com/flags/UK.png" width="18" height="12" title="United Kingdom">')


@pytest.mark.parametrize('value, expected', [
    (URL, URL),
    ('http://blu-ray.com/movies/Example-Series-Blu-ray/123456?ref=x#top', URL),
    ('https://www.blu-ray.com/dvd/Example-Series-DVD/654321/', 'https://www.blu-ray.com/dvd/Example-Series-DVD/654321/'),
])
def test_bluray_url_is_normalized(value, expected):
    assert normalize_bluray_url(value) == expected


@pytest.mark.parametrize('value', [
    'https://www.blu-ray.com/Example-Series/20915/',
    'https://www.blu-ray.com/search/?quicksearch_keyword=tt0000001',
    'https://example.com/movies/Example-Series-Blu-ray/123456/',
    'ftp://www.blu-ray.com/movies/Example-Series-Blu-ray/123456/',
    '',
])
def test_bluray_url_rejects_non_edition_pages(value):
    with pytest.raises(ValueError):
        normalize_bluray_url(value)


@pytest.mark.asyncio
async def test_edition_page_fills_only_missing_country_and_publisher():
    parsed = await parse_release_details(EDITION_HTML, {'title': 'Example Series', 'url': URL}, Meta())
    assert (parsed['country'], parsed['publisher']) == ('United Kingdom', 'Example Studio')
    listed = await parse_release_details(EDITION_HTML, release() | {'country': 'Sweden', 'publisher': 'Listed Studio'}, Meta())
    assert (listed['country'], listed['publisher']) == ('Sweden', 'Listed Studio')


def test_bluray_url_argument(tmp_path):
    meta, _, _ = Args({'DEFAULT': {'screens': 1}}).parse([str(tmp_path), '--bluray-url', URL + '?x=1'], Meta())
    assert meta.bluray_url == URL
    with pytest.raises(SystemExit):
        Args({'DEFAULT': {'screens': 1}}).parse([str(tmp_path), '--bluray-url', 'https://www.blu-ray.com/Example/1/'], Meta())


@pytest.mark.asyncio
@pytest.mark.parametrize('html, region, distributor, expected_region, expected_distributor', [
    (EDITION_HTML, '', '', 'GBR', 'EXAMPLE STUDIO'),
    (EDITION_HTML, 'USA', '', 'USA', 'EXAMPLE STUDIO'),
    # Fields missing from the page leave existing values alone.
    (HTML, 'USA', '', 'USA', 'EXAMPLE STUDIO'),
    ('<h1>Example Series Blu-ray</h1>', '', 'KEPT', '', 'KEPT'),
])
async def test_bluray_url_sets_metadata_without_search(tmp_path, monkeypatch, html, region, distributor, expected_region, expected_distributor):
    (tmp_path / 'tmp' / 'test').mkdir(parents=True)
    (tmp_path / 'tmp' / 'test' / 'debug_release_123456.html').write_text(html, encoding='utf-8')
    searched = AsyncMock()
    monkeypatch.setattr('src.bluray_com.search_bluray', searched)
    args = [str(tmp_path), '--bluray-url', URL] + (['--region', region] if region else [])
    meta, _, _ = Args({'DEFAULT': {'screens': 1}}).parse(args, Meta(base_dir=str(tmp_path), uuid='test', is_disc='BDMV', distributor=distributor))
    releases = await use_bluray_url(meta, meta.bluray_url)
    assert releases[0]['url'] == URL
    assert (meta.region, meta.distributor) == (expected_region, expected_distributor)
    assert meta.release_url == URL
    searched.assert_not_awaited()


@pytest.mark.asyncio
async def test_edition_list_accepts_pasted_url(tmp_path, monkeypatch, manual_release_selection):
    manual_release_selection.return_value = [release() | {'country': 'Sweden'}]
    answers = iter(['u', 'not a url', 'u', URL])
    monkeypatch.setattr('src.bluray_com.cli_ui.ask_string', lambda _: next(answers))
    pasted = release(subheader=LABEL)
    monkeypatch.setattr('src.bluray_com.fetch_release_details', AsyncMock(return_value=pasted))
    meta = Meta(base_dir=str(tmp_path), uuid='test', is_disc='BDMV')
    assert await get_bluray_releases(meta) == [pasted]
    assert (meta.region, meta.bluray_url, meta.release_url) == ('GBR', URL, URL)


@pytest.mark.asyncio
async def test_flags_of_other_editions_are_not_used():
    other_edition = HTML + '\n<h3>Other editions</h3><img src="https://images.static-bluray.com/flags/SE.png" width="18" height="12" title="Sweden">'
    parsed = await parse_release_details(other_edition, {'title': 'Example Series', 'url': URL}, Meta())
    assert parsed['country'] == ''


@pytest.mark.asyncio
@pytest.mark.parametrize('search, links', [(None, []), ('Search results', []), ('Search results', None)])
@pytest.mark.parametrize('answer', [URL, ''])
async def test_url_can_be_pasted_when_search_finds_no_edition(tmp_path, monkeypatch, manual_release_selection, search, links, answer):
    monkeypatch.setattr('src.bluray_com.search_bluray', AsyncMock(return_value=search))
    if links is None:
        # The title is listed, but none of its editions match this disc.
        manual_release_selection.return_value = []
    else:
        monkeypatch.setattr('src.bluray_com.extract_bluray_links', lambda _: links)
    answers = iter(['not a url', answer])
    monkeypatch.setattr('src.bluray_com.cli_ui.ask_string', lambda _: next(answers))
    pasted = release(subheader=LABEL)
    monkeypatch.setattr('src.bluray_com.fetch_release_details', AsyncMock(return_value=pasted))
    meta = Meta(base_dir=str(tmp_path), uuid='test', is_disc='BDMV')
    assert await get_bluray_releases(meta) == ([pasted] if answer else [])
    assert meta.release_url == (URL if answer else '')


@pytest.mark.asyncio
async def test_unattended_search_without_results_does_not_ask(tmp_path, monkeypatch):
    monkeypatch.setattr('src.bluray_com.search_bluray', AsyncMock(return_value=None))
    monkeypatch.setattr('src.bluray_com.cli_ui.ask_string', lambda _: pytest.fail('unexpected prompt'))
    assert await get_bluray_releases(Meta(base_dir=str(tmp_path), uuid='test', is_disc='BDMV', unattended=True)) == []


@pytest.mark.parametrize('texts, expected', [
    ([f'[center][url={URL}]Example Studio | 1981 | 159 min[/url][/center]'], URL),
    # The same edition linked by several trackers, in another URL form.
    ([f'[url={URL}]Label[/url]', 'See http://blu-ray.com/movies/Example-Series-Blu-ray/123456 for specs'], URL),
    ([f'[url={URL}]A[/url]', '[url=https://www.blu-ray.com/movies/Example-Series-4K-Blu-ray/999/]B[/url]'], ''),
    (['[url=https://www.blu-ray.com/Example-Series/20915/]Product page[/url]', '', None], ''),
    # A 4K edition page is kept, as it also lists a combo set's 1080p disc.
    (['[url=https://www.blu-ray.com/movies/Example-Series-4K-Blu-ray/999/]4K[/url]'], 'https://www.blu-ray.com/movies/Example-Series-4K-Blu-ray/999/'),
])
def test_find_bluray_url_needs_one_linked_edition(texts, expected):
    assert find_bluray_url(texts, 'BDMV') == expected


DVD_URL = 'https://www.blu-ray.com/dvd/Example-Series-DVD/654321/'


@pytest.mark.parametrize('is_disc, texts, expected', [
    ('BDMV', [f'[url={DVD_URL}]DVD[/url]'], ''),
    ('DVD', [f'[url={URL}]Blu-ray[/url]'], ''),
    ('DVD', [f'[url={DVD_URL}]DVD[/url]'], DVD_URL),
    # Only the edition of this disc's format counts when both are linked.
    ('BDMV', [f'[url={URL}]Blu-ray[/url] [url={DVD_URL}]DVD[/url]'], URL),
    ('DVD', [f'[url={URL}]Blu-ray[/url] [url={DVD_URL}]DVD[/url]'], DVD_URL),
])
def test_find_bluray_url_matches_disc_format(is_disc, texts, expected):
    assert find_bluray_url(texts, is_disc) == expected


@pytest.mark.asyncio
async def test_imported_link_to_the_same_edition_is_not_repeated(tmp_path, monkeypatch):
    monkeypatch.setattr('src.bluray_com.fetch_release_details', AsyncMock(return_value=release(subheader=LABEL)))
    imported = f'[center][url={URL}]{LABEL}[/url][/center]\n\nExample notes from the uploader.'
    meta = Meta(is_disc='BDMV', release_url=URL, description=imported, base_dir=str(tmp_path), uuid='test')
    desc = builder()
    kwargs = {name: False for name, parameter in inspect.signature(desc.general_description_generator).parameters.items() if parameter.default is True}
    kwargs.update(bluray=True, description=True)
    output = await desc.general_description_generator(meta, **kwargs)
    assert output.count(URL) == 1
    assert 'Example notes from the uploader.' in output


@pytest.mark.asyncio
@pytest.mark.parametrize('required', [True, False])
async def test_unreadable_found_edition_is_dropped_but_given_one_is_kept(tmp_path, monkeypatch, required):
    # Exhausted retries return the release unparsed, without a subheader.
    monkeypatch.setattr('src.bluray_com.fetch_release_details', AsyncMock(side_effect=lambda selected, _: selected))
    meta = Meta(base_dir=str(tmp_path), uuid='test', is_disc='BDMV', region='USA')
    releases = await use_bluray_url(meta, URL, required=required)
    assert bool(releases) is required
    assert meta.release_url == (URL if required else '')
    assert meta.region == 'USA'
