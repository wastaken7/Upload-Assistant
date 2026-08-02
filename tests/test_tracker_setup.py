from src.meta import Meta
from src.trackersetup import TrackerSetup


def test_music_trackers_are_filtered_before_tracker_specific_work():
    meta = Meta(category="MUSIC", trackers=["HDBITS", "ORPHEUS", "AITHER"])
    setup = TrackerSetup(
        {
            "TRACKERS": {
                "HDBITS": {"announce_url": "https://hdbits.example/announce"},
                "ORPHEUS": {"api_key": "token", "announce_url": "https://orpheus.example/announce"},
                "AITHER": {"api_key": "token"},
            }
        }
    )

    setup.filter_unsupported_trackers(meta)

    assert meta.trackers == ["ORPHEUS"]
    assert meta.tracker_status["HDBITS"] == {"upload": False, "skipped": True}
    assert meta.tracker_status["AITHER"] == {"upload": False, "skipped": True}


def test_cathoderaytube_is_registered_for_supported_categories():
    meta = Meta(category="GAME", trackers=["CATHODERAYTUBE"])
    setup = TrackerSetup({"TRACKERS": {"CATHODERAYTUBE": {"announce_url": "https://signal.cathode-ray.tube/passkey/announce"}}})

    setup.filter_unsupported_trackers(meta)

    assert meta.trackers == ["CATHODERAYTUBE"]  # noqa: S101
