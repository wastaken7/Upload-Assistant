import asyncio

from src.meta import Meta
from src.trackers.UNIT3D.rockethd import RocketHD
from src.trackersetup import TrackerSetup, tracker_class_map

def test_rockethd_is_registered_with_full_tracker_name():
    assert tracker_class_map["ROCKETHD"] is RocketHD  # noqa: S101
    assert RocketHD.display_name == "RocketHD"  # noqa: S101
