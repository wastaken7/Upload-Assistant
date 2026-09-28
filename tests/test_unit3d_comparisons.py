import pytest

from src.get_desc import DescriptionBuilder

COMPARISON = '''[comparison=Source, Encode]
https://images.example.com/source.png
https://images.example.com/encode.png
[/comparison]'''


@pytest.mark.parametrize('tracker', ['AITHER', 'BLUTOPIA', 'ONLYENCODES'])
def test_unit3d_keeps_comparisons_verbatim(tracker):
    builder = DescriptionBuilder(tracker, {'DEFAULT': {}, 'TRACKERS': {tracker: {}}})
    second = COMPARISON.replace('comparison', 'COMPARISON').replace('\n', '\n\n\n')
    description = f'[hide=Notes]Notes[/hide]\n{COMPARISON}\n{second}\n[spoiler]Existing[/spoiler]'
    result = builder.tracker_specific_formats(tracker, description)
    assert COMPARISON in result
    assert second in result
    assert '[spoiler=Notes]Notes[/spoiler]' in result
    assert '[spoiler]Existing[/spoiler]' in result


def test_other_trackers_still_convert_comparisons():
    builder = DescriptionBuilder('TORRENTLEECH', {'DEFAULT': {}, 'TRACKERS': {'TORRENTLEECH': {}}})
    result = builder.tracker_specific_formats('TORRENTLEECH', COMPARISON)
    assert '[comparison=' not in result
    assert 'source.png' in result
