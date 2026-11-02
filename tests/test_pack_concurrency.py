# ruff: noqa: S101

import asyncio

import pytest

from src import trackerhandle
from src.get_desc import DescriptionBuilder
from src.meta import Meta
from src.pack_images import pack_image_lock
from src.trackers.GAZELLE.passthepopcorn import PassThePopcorn
from src.trackers.UNIT3D.utopia import Utopia, UtopiaDescriptionBuilder


def _pack_meta(tmp_path, **overrides):
    (tmp_path / "tmp" / "pack").mkdir(parents=True, exist_ok=True)
    values = {
        "base_dir": str(tmp_path),
        "uuid": "pack",
        "category": "TV",
        "tv_pack": True,
        "filelist": ["Show.S01E01.mkv", "Show.S01E02.mkv", "Show.S01E03.mkv"],
        "screens": 1,
        "image_list": [{"img_url": "https://img.example/first.md.png", "raw_url": "https://img.example/first.png", "web_url": "https://img.example/first"}],
    }
    values.update(overrides)
    return Meta(**values)


class _FakeTracker:
    events: list[tuple[str, str]] = []

    def __init__(self, config):
        self.config = config
        self.tracker = type(self).__name__.removeprefix("_").upper()

    async def upload(self, _meta):
        self.events.append(("start", self.tracker))
        await asyncio.sleep(0.02)
        self.events.append(("end", self.tracker))
        return True


class _Alpha(_FakeTracker):
    pass


class _Beta(_FakeTracker):
    pass


class _Client:
    async def add_to_client(self, _meta, _tracker):
        return None


@pytest.fixture
def tracker_stage(monkeypatch):
    _FakeTracker.events = []

    class _Setup:
        def __init__(self, config):
            self.config = config

        def trackers_enabled(self, meta):
            return list(meta.trackers)

    async def _noop(*_args, **_kwargs):
        return None

    class _Wait:
        def __init__(self, config):
            self.config = config

    monkeypatch.setattr(trackerhandle, "TrackerSetup", _Setup)
    monkeypatch.setattr(trackerhandle, "Wait", _Wait)
    monkeypatch.setattr(trackerhandle, "provision_tracker_torrents", _noop)
    monkeypatch.setattr(trackerhandle, "check_tracker_image_hosts", _noop)
    monkeypatch.setattr(trackerhandle, "record_event_async", _noop)
    return _FakeTracker.events


def _run_tracker_stage(meta, *, bandwidth_control=False):
    meta.trackers = ["ALPHA", "BETA"]
    meta.tracker_status = {"ALPHA": {"upload": True}, "BETA": {"upload": True}}
    config = {"DEFAULT": {"multiScreens": 2, "smart_image_host_selection": False}, "TRACKERS": {}}
    asyncio.run(
        trackerhandle.process_trackers(
            meta,
            config,
            _Client(),
            ["ALPHA", "BETA"],
            {"ALPHA": _Alpha, "BETA": _Beta},
            [],
            [],
            bandwidth_control=bandwidth_control,
        )
    )


def test_pack_uploads_run_concurrently(tmp_path, tracker_stage):
    meta = _pack_meta(tmp_path, discs=[])

    _run_tracker_stage(meta)

    assert [event for event, _tracker in tracker_stage[:2]] == ["start", "start"]
    assert meta.tracker_status["ALPHA"]["upload_success"] is True
    assert meta.tracker_status["BETA"]["upload_success"] is True


def test_multi_disc_uploads_run_concurrently(tmp_path, tracker_stage):
    meta = _pack_meta(tmp_path, tv_pack=False, discs=[{"type": "BDMV"}, {"type": "BDMV"}])

    _run_tracker_stage(meta)

    assert [event for event, _tracker in tracker_stage[:2]] == ["start", "start"]


def test_bandwidth_control_keeps_tracker_order(tmp_path, tracker_stage):
    meta = _pack_meta(tmp_path, discs=[])

    _run_tracker_stage(meta, bandwidth_control=True)

    assert tracker_stage == [("start", "ALPHA"), ("end", "ALPHA"), ("start", "BETA"), ("end", "BETA")]


def test_concurrent_trackers_create_each_pack_file_image_once(tmp_path, monkeypatch):
    meta = _pack_meta(tmp_path)
    config = {"DEFAULT": {"multiScreens": 1, "processLimit": 3, "fileLimit": 3}, "TRACKERS": {"ALPHA": {}, "BETA": {}}}
    builders = [DescriptionBuilder("ALPHA", config), DescriptionBuilder("BETA", config)]
    captured = {}
    captures = []
    uploads = []

    async def screenshots(_path, group, *_args, **_kwargs):
        captures.append(group)
        await asyncio.sleep(0.01)
        captured[group] = [tmp_path / f"{group}-0.png"]

    async def upload_screens(_meta, *args, **_kwargs):
        name = args[4][0]
        uploads.append(name)
        await asyncio.sleep(0.01)
        return [{"img_url": name, "raw_url": name, "web_url": name}], 1

    async def save_image_links(*_args, **_kwargs):
        return None

    for builder in builders:
        monkeypatch.setattr(builder.takescreens_manager, "screenshots", screenshots)
        monkeypatch.setattr(builder.uploadscreens_manager, "upload_screens", upload_screens)
        monkeypatch.setattr(builder.common, "save_image_links", save_image_links)
    monkeypatch.setattr("src.get_desc.manifest_files", lambda _base, _uuid, group: captured.get(group, []))
    monkeypatch.setattr("src.get_desc.MediaInfo.parse", lambda *_args, **_kwargs: "General\nDuration : 42 min\n")

    async def render_both():
        return await asyncio.gather(*(builder._handle_discs_and_screenshots(meta, [], meta.image_list, 1) for builder in builders))

    descriptions = asyncio.run(render_both())

    assert sorted(captures) == ["FILE_1", "FILE_2"]
    assert sorted(uploads) == ["FILE_1-0.png", "FILE_2-0.png"]
    for description in descriptions:
        assert "FILE_1-0.png" in description
        assert "FILE_2-0.png" in description


def test_ptp_description_holds_the_pack_image_lock(tmp_path, monkeypatch):
    meta = _pack_meta(tmp_path)
    ptp = PassThePopcorn({"DEFAULT": {}, "TRACKERS": {"PASSTHEPOPCORN": {}}})
    held = []

    async def write_description(_meta):
        held.append(pack_image_lock(meta).locked())

    monkeypatch.setattr(ptp, "_write_description", write_description)

    asyncio.run(ptp.edit_desc(meta))

    assert held == [True]


def test_utopia_screenshots_link_full_image_and_show_medium_image():
    builder = UtopiaDescriptionBuilder("UTOPIA", {"DEFAULT": {}, "TRACKERS": {"UTOPIA": {}}})

    rendered = builder.format_screenshot("https://img.example/page", "https://img.example/full.png", "https://img.example/medium.png", 350)

    assert rendered == "[url=https://img.example/full.png][img=350]https://img.example/medium.png[/img][/url] "


def test_utopia_description_leaves_shared_metadata_unchanged(tmp_path, monkeypatch):
    meta = _pack_meta(tmp_path, new_images_file_1=[{"img_url": "m1", "raw_url": "f1", "web_url": "p1"}])
    original_images = [dict(image) for image in meta.image_list]
    original_pack_images = [dict(image) for image in meta.new_images_file_1]
    seen = []

    async def general_description_generator(self, current_meta, **_kwargs):
        assert isinstance(self, UtopiaDescriptionBuilder)
        seen.append((current_meta.image_list, current_meta.new_images_file_1))
        return "description"

    monkeypatch.setattr(UtopiaDescriptionBuilder, "general_description_generator", general_description_generator)

    result = asyncio.run(Utopia({"DEFAULT": {}, "TRACKERS": {"UTOPIA": {}}}).get_description(meta))

    assert result == {"description": "description"}
    assert seen == [(original_images, original_pack_images)]
    assert meta.image_list == original_images
    assert meta.new_images_file_1 == original_pack_images
