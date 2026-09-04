import asyncio
from types import SimpleNamespace

import pytest

from src.trackers.AVISTAZ.avistaz import AvistaZ
from src.trackers.AVISTAZ.cinemaz import CinemaZ
from src.trackers.AVISTAZ.privatehd import PrivateHD

TRACKERS = (
    (AvistaZ, "AVISTAZ", "3773", "943"),
    (CinemaZ, "CINEMAZ", "1594", "938"),
    (PrivateHD, "PRIVATEHD", "1448", "415"),
)


async def get_tags(tracker, meta):
    try:
        return await tracker.get_tags(meta)
    finally:
        await tracker.session.aclose()


@pytest.mark.parametrize(("tracker_class", "tracker_name", "personal_tag", "_internal_tag"), TRACKERS)
def test_personal_release_tag_is_added_without_keywords(tracker_class, tracker_name, personal_tag, _internal_tag):
    tracker = tracker_class({"TRACKERS": {tracker_name: {}}})
    meta = SimpleNamespace(keywords=[], personalrelease=True)

    tags = asyncio.run(get_tags(tracker, meta))

    assert tags == [personal_tag]  # noqa: S101


@pytest.mark.parametrize(("tracker_class", "tracker_name", "_personal_tag", "internal_tag"), TRACKERS)
def test_internal_release_tag_is_added_without_keywords(tracker_class, tracker_name, _personal_tag, internal_tag):
    tracker = tracker_class({"TRACKERS": {tracker_name: {"internal": True}}})
    meta = SimpleNamespace(keywords=[], personalrelease=False)

    tags = asyncio.run(get_tags(tracker, meta))

    assert tags == [internal_tag]  # noqa: S101
