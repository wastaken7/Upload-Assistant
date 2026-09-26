import pytest

from src.meta import Meta
from src.region import get_mediainfo_service


def metadata(**overrides):
    values = dict(type='WEBDL', resolution='1080p', mediainfo={'media': {'track': [
        {'@type': 'Audio', 'Format': 'E-AC-3', 'Channels': '2', 'BitRate': '224000'},
        {'@type': 'General'},
        {'@type': 'Video', 'BitRate_Nominal': '10000000'},
    ]}})
    values.update(overrides)
    return Meta(**values)


@pytest.mark.asyncio
@pytest.mark.parametrize('channels,bitrate', [('2', '224000'), ('6', '640000'), (2, 224000), (6, 640000), (2.0, 224000.0)])
@pytest.mark.parametrize('key,nominal', [('BitRate_Nominal', '10000000'), ('NominalBitRate', '10000000'), ('BitRate_Nominal', 10000000), ('BitRate_Nominal', 10000000.0)])
async def test_amazon_signatures(channels, bitrate, key, nominal):
    meta = metadata()
    meta.mediainfo['media']['track'][0].update(Channels=channels, BitRate=bitrate)
    meta.mediainfo['media']['track'][2] = {'@type': 'Video', key: nominal}
    assert await get_mediainfo_service(meta) == ('AMZN', 'Amazon')


@pytest.mark.asyncio
@pytest.mark.parametrize('overrides', [dict(service='NF'), dict(service='AMZN'), dict(resolution='720p'), dict(resolution='2160p'), dict(type='ENCODE'), dict(is_disc='DVD')])
async def test_existing_service_and_source_precedence(overrides):
    assert await get_mediainfo_service(metadata(**overrides)) == ('', '')


@pytest.mark.asyncio
@pytest.mark.parametrize('track,key,value', [
    (0, 'Format', 'AC-3'), (0, 'Channels', '8'), (0, 'BitRate', '640000'),
    (0, 'BitRate', '224001'), (0, 'BitRate', {}), (0, 'BitRate', None),
    (2, 'BitRate_Nominal', '9999999'), (2, 'BitRate_Nominal', '10 Mbps?'),
    (2, 'BitRate_Nominal', None), (2, 'BitRate_Nominal', '10000000.5'),
    (0, 'Channels', '2.1'), (0, 'Channels', True), (0, 'BitRate', []),
    (0, 'BitRate', '224 kb/s'), (0, 'BitRate', '224\u00a0kb/s'),
    (2, 'BitRate_Nominal', '10 000 kb/s'), (2, 'BitRate_Nominal', '10 000 000'),
    (2, 'BitRate_Nominal', 'NaN'), (2, 'BitRate_Nominal', 'Infinity'),
])
async def test_near_misses_and_invalid_fields(track, key, value):
    meta = metadata()
    meta.mediainfo['media']['track'][track][key] = value
    meta.mediainfo['media']['track'][2]['BitRate'] = '10000000'
    assert await get_mediainfo_service(meta) == ('', '')


@pytest.mark.asyncio
@pytest.mark.parametrize('media', [None, [], {}, {'media': None}, {'media': {'track': None}}, {'media': {'track': [None, {}]}}])
async def test_malformed_tracks(media):
    assert await get_mediainfo_service(metadata(mediainfo=media)) == ('', '')
