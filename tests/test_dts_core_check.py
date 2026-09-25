import pytest

from src.audio import LossyDtsDuplicateError, dts_core_additional_check
from src.meta import Meta


def _tracks(lossy_overrides=None):
    shared = {"@type": "Audio", "Duration": "600000", "FrameRate": "93.750", "FrameCount": "56250", "Language": "en"}
    hd = {**shared, "Format": "DTS", "Format_Commercial_IfAny": "DTS-HD Master Audio"}
    lossy = {**shared, "Format": "DTS", **(lossy_overrides or {})}
    return hd, lossy


@pytest.mark.parametrize("commentary_field", ["Title", "title", "TrackTitle", "ServiceKind"])
@pytest.mark.parametrize("reverse_order", [False, True])
def test_commentary_dts_is_not_treated_as_hd_core(commentary_field, reverse_order):
    hd, lossy = _tracks({commentary_field: "Director Commentary"})
    tracks = [lossy, hd] if reverse_order else [hd, lossy]
    dts_core_additional_check(Meta(mediainfo={"media": {"track": tracks}}, unattended=True))


def test_matching_non_commentary_dts_still_raises():
    hd, lossy = _tracks()
    with pytest.raises(LossyDtsDuplicateError):
        dts_core_additional_check(Meta(mediainfo={"media": {"track": [hd, lossy]}}, unattended=True))


@pytest.mark.parametrize("service_kind", ["C", "CM / C", "C / O / C"])
def test_commentary_service_kind_without_title_is_excluded(service_kind):
    hd, lossy = _tracks({"ServiceKind": service_kind})
    dts_core_additional_check(Meta(mediainfo={"media": {"track": [hd, lossy]}}, unattended=True))


def test_complete_main_service_kind_is_not_commentary():
    hd, lossy = _tracks({"ServiceKind": "CM"})
    with pytest.raises(LossyDtsDuplicateError):
        dts_core_additional_check(Meta(mediainfo={"media": {"track": [hd, lossy]}}, unattended=True))


def test_commentary_does_not_hide_a_separate_duplicate():
    hd, lossy = _tracks()
    commentary = {**lossy, "Title": "Director Commentary"}
    with pytest.raises(LossyDtsDuplicateError):
        dts_core_additional_check(Meta(mediainfo={"media": {"track": [hd, commentary, lossy]}}, unattended=True))
