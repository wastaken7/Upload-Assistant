import asyncio

from src.meta import Meta
from src.trackers.flood import Flood
from src.trackersetup import TrackerSetup, tracker_class_map

def test_flood_is_registered_with_full_tracker_name():
    assert tracker_class_map["FLOOD"] is Flood  # noqa: S101
    assert Flood.display_name == "Flood"  # noqa: S101
