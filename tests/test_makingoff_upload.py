from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from src.meta import Meta
from src.trackers.makingoff import MakingOff


@pytest.mark.asyncio
async def test_upload_allows_release_without_portuguese_subtitle(tmp_path, monkeypatch):
    meta = Meta(
        base_dir=str(tmp_path),
        uuid="release",
        basename_no_ext="Example Movie",
        debug=True,
        tracker_status={"MAKINGOFF": {}},
    )
    (tmp_path / "tmp" / meta.uuid).mkdir(parents=True)

    tracker = MakingOff({"TRACKERS": {"MAKINGOFF": {}}})
    tracker.get_forum_id = AsyncMock(return_value="1")
    tracker._get_portuguese_subtitles = AsyncMock(return_value=[])
    tracker.common.create_torrent_for_upload = AsyncMock()
    tracker.get_name = AsyncMock(return_value="Example Movie")
    tracker.generate_description = AsyncMock(return_value="description")
    tracker._topic_tags = lambda *_args: ""
    tracker.get_topic_fields = lambda **_kwargs: {}
    monkeypatch.setattr("src.trackers.makingoff.shutil.copy2", lambda _source, destination: Path(destination).touch())

    assert await tracker.upload(meta)  # noqa: S101
    assert meta.tracker_status["MAKINGOFF"]["status_message"] == "Debug mode enabled, not uploading (simulated successfully)"  # noqa: S101
