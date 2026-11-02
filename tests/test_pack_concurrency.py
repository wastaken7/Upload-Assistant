# ruff: noqa: S101

import asyncio
import tarfile
from pathlib import Path

import pytest

from src import trackerhandle
from src.get_desc import DescriptionBuilder
from src.meta import Meta
from src.rehostimages import ImageHostPolicy, check_tracker_image_hosts
from src.release_locks import release_image_lock, release_language_lock
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

    async def edit_desc(self, _meta):
        self.events.append(("describe", self.tracker))


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


def _run_tracker_stage(meta, *, bandwidth_control=False, trackers=("ALPHA", "BETA"), api_trackers=("ALPHA", "BETA"), http_trackers=()):
    meta.trackers = list(trackers)
    meta.tracker_status = {"ALPHA": {"upload": True}, "BETA": {"upload": True}}
    config = {"DEFAULT": {"multiScreens": 2, "smart_image_host_selection": False}, "TRACKERS": {}}
    asyncio.run(
        trackerhandle.process_trackers(
            meta,
            config,
            _Client(),
            list(api_trackers),
            {"ALPHA": _Alpha, "BETA": _Beta},
            list(http_trackers),
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


@pytest.mark.parametrize("bandwidth_control", [False, True])
def test_manual_packaging_runs_after_the_uploads(tmp_path, tracker_stage, monkeypatch, bandwidth_control):
    # Packaging deletes the per-tracker .torrent files the uploads read.
    class _Packager:
        def __init__(self, config):
            self.config = config

        async def package(self, _meta):
            tracker_stage.append(("package", "MANUAL"))
            return "files"

    monkeypatch.setattr(trackerhandle, "ManualPackageManager", _Packager)
    meta = _pack_meta(tmp_path, discs=[], unattended=True)

    _run_tracker_stage(meta, bandwidth_control=bandwidth_control, trackers=("MANUAL", "ALPHA", "BETA"), api_trackers=(), http_trackers=("ALPHA", "BETA"))

    assert tracker_stage[-1] == ("package", "MANUAL")
    assert {("end", "ALPHA"), ("end", "BETA")} <= set(tracker_stage[: tracker_stage.index(("describe", "ALPHA"))])


def test_rehost_takes_the_release_image_lock(tmp_path):
    meta = _pack_meta(tmp_path)
    held = []

    class _Rehosting:
        async def check_image_hosts(self, current_meta):
            held.append(release_image_lock(current_meta).locked())

    asyncio.run(check_tracker_image_hosts(meta, _Rehosting()))

    assert held == [True]


def test_trackers_without_host_rules_do_not_wait_for_image_work(tmp_path):
    meta = _pack_meta(tmp_path)

    class _Plain:
        tracker = "PLAIN"

    async def check_while_locked():
        async with release_image_lock(meta):
            await asyncio.wait_for(check_tracker_image_hosts(meta, _Plain()), timeout=1)

    asyncio.run(check_while_locked())


def test_ptp_reuses_only_pack_images_on_hosts_it_accepts(tmp_path):
    ptp = PassThePopcorn({"DEFAULT": {}, "TRACKERS": {"PASSTHEPOPCORN": {}}})
    assert isinstance(ptp.image_host_policy, ImageHostPolicy)
    accepted = {"img_url": "https://img.pixhost.to/a.png", "raw_url": "https://img.pixhost.to/a.png", "web_url": "https://pixhost.to/a"}
    rejected = {"img_url": "https://other-host.example/b.png", "raw_url": "https://other-host.example/b.png", "web_url": "https://other-host.example/b"}
    meta = _pack_meta(tmp_path, new_images_file_1=[accepted, rejected], new_images_file_2=[rejected], new_images_file_3=[accepted, accepted])

    assert ptp._approved_pack_images(meta, "new_images_file_1", 1) == [accepted]
    # Too few accepted images left: the group is regenerated instead.
    assert ptp._approved_pack_images(meta, "new_images_file_1", 2) == []
    assert ptp._approved_pack_images(meta, "new_images_file_2", 1) == []
    assert ptp._approved_pack_images(meta, "new_images_file_3", 2) == [accepted, accepted]
    assert ptp._approved_pack_images(meta, "new_images_file_4", 1) == []


def test_manual_archive_leaves_out_torrents_with_tracker_credentials(tmp_path):
    from src.manualpackage import _write_archive

    release = tmp_path / "tmp" / "pack"
    for relative in (
        "[ALPHA].torrent",
        "BASE.torrent",
        "Show.S01.torrent",
        "GENERIC_INFO.txt",
        "screenshots/FILE_1-0.png",
        "torrents/.client/0123abcd.torrent",
        "torrents/16777216/0123abcd.torrent",
    ):
        (release / relative).parent.mkdir(parents=True, exist_ok=True)
        (release / relative).write_bytes(b"x")
    archive = release / "Show.tar"
    archive.write_bytes(b"previous archive")
    # Archives from earlier runs may predate the filter. A title with no ASCII
    # characters produces ".tar", a name Path.suffix does not recognise.
    (release / "Old.Title.tar").write_bytes(b"older archive")
    (release / ".tar").write_bytes(b"untitled archive")
    (release / ".torrent").write_bytes(b"untitled torrent")

    _write_archive(str(archive), release, {"Show.S01.torrent"})

    with tarfile.open(archive) as tar:
        names = {Path(name).as_posix() for name in tar.getnames()}
    assert {"BASE.torrent", "Show.S01.torrent", "GENERIC_INFO.txt", "screenshots/FILE_1-0.png", "torrents/16777216/0123abcd.torrent"} <= names
    assert not {"[ALPHA].torrent", "torrents/.client/0123abcd.torrent", "Show.tar", "Old.Title.tar", ".tar", ".torrent"} & names
    # The tracker torrents stay available for the client and for manual adding.
    assert (release / "[ALPHA].torrent").exists()
    assert (release / "torrents/.client/0123abcd.torrent").exists()


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


def test_ptp_description_holds_the_release_image_lock(tmp_path, monkeypatch):
    meta = _pack_meta(tmp_path)
    ptp = PassThePopcorn({"DEFAULT": {}, "TRACKERS": {"PASSTHEPOPCORN": {}}})
    held = []

    async def write_description(_meta):
        held.append(release_image_lock(meta).locked())

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


def test_filebrowser_share_holds_only_shareable_files(tmp_path):
    from src.manualpackage import _stage_share, _write_archive

    release = tmp_path / "tmp" / "pack"
    for relative in ("[ALPHA].torrent", "Show.S01.torrent", "GENERIC_INFO.txt", "screenshots/FILE_1-0.png", "torrents/.client/0123abcd.torrent", "Old.Title.tar"):
        (release / relative).parent.mkdir(parents=True, exist_ok=True)
        (release / relative).write_bytes(b"x")
    share = tmp_path / "tmp" / "manual_packages" / "pack"
    (share / "stale.txt").parent.mkdir(parents=True)
    (share / "stale.txt").write_bytes(b"from an earlier run")
    archive = release / "Show.tar"
    _write_archive(str(archive), release, {"Show.S01.torrent"})

    _stage_share(share, release, {"Show.S01.torrent"}, str(archive))

    shared = {path.relative_to(share).as_posix() for path in share.rglob("*") if path.is_file()}
    assert shared == {"Show.S01.torrent", "GENERIC_INFO.txt", "screenshots/FILE_1-0.png", "Show.tar"}
    assert (release / "[ALPHA].torrent").exists()


def test_concurrent_trackers_detect_languages_once(tmp_path, monkeypatch):
    from src.languages import languages_manager

    meta = _pack_meta(tmp_path, language_checked=False)
    active = []
    detections = []

    async def detect(current_meta, tracker):
        active.append(tracker)
        assert len(active) == 1
        await asyncio.sleep(0.01)
        if not current_meta.language_checked:
            detections.append(tracker)
            current_meta.language_checked = True
        active.remove(tracker)

    monkeypatch.setattr(languages_manager, "_process_desc_language", detect)

    async def describe_both():
        await asyncio.gather(languages_manager.process_desc_language(meta, "ALPHA"), languages_manager.process_desc_language(meta, "BETA"))
        return release_language_lock(meta).locked()

    assert asyncio.run(describe_both()) is False
    assert len(detections) == 1
