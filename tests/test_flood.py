import asyncio
from types import SimpleNamespace

import pytest

from src.meta import Meta
from src.trackers.flood import Flood
from src.trackersetup import TrackerSetup, tracker_class_map


def test_flood_is_registered_with_full_tracker_name():
    assert tracker_class_map["FLOOD"] is Flood  # noqa: S101
    assert Flood.display_name == "Flood"  # noqa: S101


@pytest.mark.asyncio
async def test_flood_multi_disc_dvd_description_has_valid_code_tags(tmp_path, monkeypatch):
    monkeypatch.setattr("src.description_review.get_base_description", lambda _meta: "base")
    (tmp_path / "tmp" / "test").mkdir(parents=True)
    meta = SimpleNamespace(
        base_dir=str(tmp_path),
        uuid="test",
        image_list=[],
        get=lambda key, default=None: {
            "discs": [
                {"type": "DVD", "vob_mi": "disc 1"},
                {"type": "DVD", "name": "Disc 2", "vob": "VIDEO_TS/VTS_01_1.VOB", "vob_mi": "vob info", "ifo": "VIDEO_TS/VTS_01_0.IFO", "ifo_mi": "ifo info"},
            ]
        }.get(key, default),
    )

    await Flood({"TRACKERS": {}}).edit_desc(meta)

    description = (tmp_path / "tmp" / "test" / "[FLOOD]DESCRIPTION.txt").read_text(encoding="utf-8")
    assert "[code][vob info" not in description  # noqa: S101
    assert "[code]vob info[/code]" in description  # noqa: S101
    assert "[code]ifo info[/code]" in description  # noqa: S101
