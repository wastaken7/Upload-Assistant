import asyncio
from types import SimpleNamespace

import pytest

from src.trackers.common import Common


@pytest.mark.parametrize("tracker_name", ["BJShare", "BrasilTracker"])
def test_get_tags_removes_accents_from_mapped_tags(tracker_name):
    common = Common(config={})
    meta = SimpleNamespace(category="MOVIE", genres=["Action", "Mystery"], keywords=[], unattended=False, unattended_confirm=False)

    tags = asyncio.run(common.get_portuguese_tags(meta, tracker=tracker_name, tmdb_data={}))

    assert tags == "acao, misterio"  # noqa: S101
    assert tags.isascii()  # noqa: S101


@pytest.mark.parametrize("tracker_name", ["BJShare", "BrasilTracker"])
def test_get_tags_limits_to_maximum_5_tags(tracker_name):
    common = Common(config={})
    meta = SimpleNamespace(
        category="MOVIE",
        genres=["Action", "Mystery", "Comedy", "Drama", "Horror", "Thriller", "Adventure"],
        keywords=[],
        unattended=False,
        unattended_confirm=False,
    )

    tags = asyncio.run(common.get_portuguese_tags(meta, tracker=tracker_name, tmdb_data={}))

    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    assert len(tag_list) == 5  # noqa: S101

