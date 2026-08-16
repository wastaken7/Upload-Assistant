# ruff: noqa: S101

import asyncio

from src.get_tracker_data import TrackerDataManager
from src.meta import Meta


class _FakeTrackerMetadataManager:
    def __init__(self) -> None:
        self.calls = 0

    async def update_metadata_from_tracker(
        self,
        _tracker,
        _instance,
        meta,
        _search_term,
        _search_file_folder,
        _skip_descriptions,
        *,
        torrent_id="",
    ):
        self.calls += 1
        assert torrent_id == "12345"
        meta.imdb_id = 1602620
        meta.description = "Cached tracker description"
        return meta, True


def test_explicit_tracker_id_reuses_cached_metadata(tmp_path):
    async def run():
        config = {
            "DEFAULT": {
                "tracker_metadata_cache_enabled": True,
                "tracker_metadata_cache_dir": "tracker-cache",
                "tracker_metadata_cache_ttl_hours": 24,
            },
            "TRACKERS": {},
        }
        first_manager = TrackerDataManager(config)
        first_fake = _FakeTrackerMetadataManager()
        first_manager.tracker_meta_manager = first_fake
        first_meta = Meta({"base_dir": str(tmp_path), "tracker_ids": {"PASSTHEPOPCORN": "12345"}})
        _, first_match = await first_manager.update_metadata_from_explicit_tracker("PASSTHEPOPCORN", object(), first_meta, "Amour", "Amour", False)

        second_manager = TrackerDataManager(config)
        second_fake = _FakeTrackerMetadataManager()
        second_manager.tracker_meta_manager = second_fake
        second_meta = Meta({"base_dir": str(tmp_path), "tracker_ids": {"PASSTHEPOPCORN": "12345"}})
        _, second_match = await second_manager.update_metadata_from_explicit_tracker("PASSTHEPOPCORN", object(), second_meta, "Amour", "Amour", False)

        assert first_match and second_match
        assert first_fake.calls == 1
        assert second_fake.calls == 0
        assert second_meta.imdb_id == 1602620
        assert second_meta.description == "Cached tracker description"

    asyncio.run(run())
