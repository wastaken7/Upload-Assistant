from src.languages import LanguagesManager
from src.meta import Meta


def test_detects_hardcoded_subtitle_marker_in_filename():
    assert LanguagesManager._has_hardcoded_subtitle_marker(Meta(path="Beanpole.2019.1080p.WEB-DL.HC.AAC2.0.mkv"))  # noqa: S101
    assert not LanguagesManager._has_hardcoded_subtitle_marker(Meta(path="The.Chronic.2015.1080p.WEB-DL.mkv"))  # noqa: S101
