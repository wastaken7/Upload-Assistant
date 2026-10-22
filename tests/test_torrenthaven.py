import asyncio

import pytest

from src.meta import Meta
from src.trackersetup import tracker_class_map


def _tracker():
    return tracker_class_map["TORRENTHAVEN"]({"DEFAULT": {}, "TRACKERS": {"TORRENTHAVEN": {}}})


@pytest.mark.parametrize(("release_type", "expected"), [("DVDRIP", "19"), ("ENCODE", "3"), ("WEBDL", "4"), ("UNKNOWN", "0")])
def test_torrenthaven_type_ids(release_type: str, expected: str):
    assert asyncio.run(_tracker().get_type_id(Meta(type=release_type))) == {"type_id": expected}


def test_torrenthaven_reverse_type_ids():
    assert asyncio.run(_tracker().get_type_id(Meta(), reverse=True))["19"] == "DVDRIP"
