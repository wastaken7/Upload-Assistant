import asyncio
import inspect
from unittest.mock import AsyncMock

import pytest

from src.bluray_com import ensure_release_subheader, get_bluray_releases, parse_release_details, process_all_releases, reset_release_subheader_cache, set_selected_release
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
async def test_manual_selection_without_covers_fetches_label_on_demand(tmp_path, monkeypatch):
    folder = tmp_path / 'tmp' / 'test'
    folder.mkdir(parents=True)
    (folder / 'debug_bluray_BD_123.html').write_text('Cached release list')
    monkeypatch.setattr('src.bluray_com.search_bluray', AsyncMock(return_value='Search results'))
    monkeypatch.setattr('src.bluray_com.extract_bluray_links', lambda _: [{'releases_url': 'https://www.blu-ray.com/Example/123/', 'title': 'Example', 'year': '1981'}])
    monkeypatch.setattr('src.bluray_com.extract_bluray_release_info', AsyncMock(return_value=[release()]))
    monkeypatch.setattr('src.bluray_com.cli_ui.ask_string', lambda _: '1')
    fetched = AsyncMock(return_value=release(subheader=LABEL))
    monkeypatch.setattr('src.bluray_com.fetch_release_details', fetched)
    meta = Meta(base_dir=str(tmp_path), uuid='test', is_disc='BDMV', use_bluray_images=False)
    await get_bluray_releases(meta)
    assert meta.release_url == URL
    fetched.assert_not_awaited()
    await builder().get_bluray_section(meta)
    assert meta.release_subheader == LABEL
    fetched.assert_awaited_once()


@pytest.mark.asyncio
async def test_automatic_selection_carries_subheader(tmp_path, monkeypatch):
    monkeypatch.setattr('src.bluray_com.fetch_release_details', AsyncMock(return_value=release(subheader=LABEL)))
    meta = Meta(base_dir=str(tmp_path), uuid='test', is_disc='BDMV', unattended=True, bluray_single_score=1)
    await process_all_releases([release()], meta)
    assert meta.release_url == URL
    assert meta.release_subheader == LABEL
    assert meta.release_subheader_url == URL


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
