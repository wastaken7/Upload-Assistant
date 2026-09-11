import asyncio
import json
from pathlib import Path

import pytest
from torf import Torrent

from src.torrent_manifest import TorrentEntry, TorrentManifest
from src.torrent_policy import ANTHELION_POLICY, PASSTHEPOPCORN_POLICY, MIB, TorrentPolicy, TorrentStats
from src.torrent_provision import provision_tracker_torrents
from src.torrentcreate import TorrentCreator
from src.trackers.common import Common
from src.trackers.GAZELLE.anthelion import Anthelion
from src.trackers.GAZELLE.passthepopcorn import PassThePopcorn
from src.trackers.hdbits import HDBits


def write_torrent(path: Path, piece_size: int = 4 * MIB, size: int = 8 * MIB, name: str = "release.mkv") -> Torrent:
    path.parent.mkdir(parents=True, exist_ok=True)
    torrent = Torrent()
    pieces = (size + piece_size - 1) // piece_size
    torrent.metainfo["info"] = {"name": name, "length": size, "piece length": piece_size, "pieces": b"x" * (20 * pieces)}
    torrent.trackers = ["https://private.example/passkey"]
    torrent.comment = "private comment"
    torrent.write(path, overwrite=True)
    return torrent


def test_register_sanitizes_and_places_torrent_under_piece_directory(tmp_path):
    source = tmp_path / "client.torrent"
    write_torrent(source)
    manifest = TorrentManifest(tmp_path, "release")

    entry = manifest.register(source, "base", "client:qbit")
    path = manifest.entry_path(entry)

    assert path.parent.name == str(4 * MIB)
    assert path.name == f"{entry.infohash}.torrent"
    assert Torrent.read(path).infohash == entry.infohash
    assert Torrent.read(path).trackers == [["https://fake.tracker"]]
    assert "private.example" not in path.read_bytes().decode("latin-1")
    default = manifest.default_path("base")
    assert default == path


def test_manifest_keeps_layouts_separate_and_deduplicates(tmp_path):
    base = tmp_path / "base.torrent"
    subs = tmp_path / "subs.torrent"
    write_torrent(base)
    write_torrent(subs, name="release-with-subs.mkv")
    manifest = TorrentManifest(tmp_path, "release")

    first = manifest.register(base, "base", "generated")
    again = manifest.register(base, "base", "client:qbit")
    manifest.register(subs, "base_subs", "generated")

    assert first.id == again.id
    assert len(manifest.entries("base")) == 1
    assert len(manifest.entries("base_subs")) == 1


def test_explicit_default_replaces_the_previous_default(tmp_path):
    first = tmp_path / "first.torrent"
    second = tmp_path / "second.torrent"
    write_torrent(first, MIB)
    write_torrent(second, 2 * MIB)
    manifest = TorrentManifest(tmp_path, "release")
    manifest.register(first, "base", "client:first")
    replacement = manifest.register(second, "base", "generated", make_default=True)
    assert manifest.default_path() == manifest.entry_path(replacement)


def test_corrupt_manifest_is_treated_as_empty(tmp_path):
    manifest = TorrentManifest(tmp_path, "release")
    manifest.path.parent.mkdir(parents=True)
    manifest.path.write_text("not json", encoding="utf-8")
    assert manifest.entries() == []


def test_manifest_rejects_escaping_entry_path(tmp_path):
    manifest = TorrentManifest(tmp_path, "release")
    manifest.path.parent.mkdir(parents=True)
    escaped = TorrentEntry("bad", "../outside.torrent", "base", "test", "bad", 1, 1, 1, 1)
    manifest.path.write_text(
        json.dumps({"version": 1, "torrents": {"bad": escaped.__dict__}, "defaults": {"base": "bad"}, "selections": {}}),
        encoding="utf-8",
    )
    assert manifest.entries() == []
    assert manifest.default_path() is None


def test_manifest_rejects_a_managed_file_changed_after_registration(tmp_path):
    source = tmp_path / "source.torrent"
    replacement = tmp_path / "replacement.torrent"
    write_torrent(source, MIB)
    write_torrent(replacement, 2 * MIB)
    manifest = TorrentManifest(tmp_path, "release")
    entry = manifest.register(source, "base", "generated")
    manifest.entry_path(entry).write_bytes(replacement.read_bytes())

    assert manifest.entries() == []
    assert manifest.select("TEST", "base") is None


def test_policy_selection_records_tracker_choice(tmp_path):
    large = tmp_path / "large.torrent"
    small = tmp_path / "small.torrent"
    write_torrent(large, 32 * MIB, 64 * MIB)
    write_torrent(small, 16 * MIB, 64 * MIB)
    manifest = TorrentManifest(tmp_path, "release")
    manifest.register(large, "base", "client:first")
    manifest.register(small, "base", "client:second")

    selected = manifest.select("PASSTHEPOPCORN", "base", PASSTHEPOPCORN_POLICY)

    assert selected is not None
    assert selected.piece_size == 16 * MIB
    assert manifest.selected_path("PASSTHEPOPCORN") == manifest.entry_path(selected)


@pytest.mark.asyncio
async def test_concurrent_registration_keeps_manifest_valid(tmp_path):
    sources = [tmp_path / f"source-{size}.torrent" for size in (MIB, 2 * MIB, 4 * MIB)]
    for source, piece_size in zip(sources, (MIB, 2 * MIB, 4 * MIB), strict=True):
        write_torrent(source, piece_size, 8 * MIB)
    manifest = TorrentManifest(tmp_path, "release")

    await asyncio.gather(*(asyncio.to_thread(manifest.register, source, "base", "client:test") for source in sources))

    assert len(manifest.entries()) == 3


def test_tracker_policy_boundaries():
    assert PASSTHEPOPCORN_POLICY.accepts(TorrentStats(16 * MIB, 1, 16 * MIB, 100))
    assert not PASSTHEPOPCORN_POLICY.accepts(TorrentStats(32 * MIB, 1, 32 * MIB, 100))
    assert ANTHELION_POLICY.accepts(TorrentStats(4 * MIB, 1, 4 * MIB, 250 * 1024))
    assert not ANTHELION_POLICY.accepts(TorrentStats(4 * MIB, 1, 4 * MIB, 250 * 1024 + 1))
    assert TorrentPolicy(max_piece_size=8 * MIB).choose_piece_size(100, 16 * MIB) == 8 * MIB


def test_trackers_expose_typed_torrent_policies():
    assert HDBits.torrent_policy is not None
    assert PassThePopcorn.torrent_policy is PASSTHEPOPCORN_POLICY
    assert Anthelion.torrent_policy is ANTHELION_POLICY


@pytest.mark.asyncio
async def test_nohash_blocks_tracker_without_compliant_variant(tmp_path):
    source = tmp_path / "large.torrent"
    media = tmp_path / "release.mkv"
    media.touch()
    write_torrent(source, 32 * MIB, 64 * MIB)
    manifest = TorrentManifest(tmp_path, "release")
    manifest.register(source, "base", "client:qbit")
    from src.meta import Meta

    meta = Meta(base_dir=str(tmp_path), uuid="release", path=str(media), filelist=[str(media)], trackers=["PASSTHEPOPCORN"], nohash=True)
    meta.tracker_status = {"PASSTHEPOPCORN": {"upload": True}}

    blocked = await provision_tracker_torrents(meta, {"TRACKERS": {"PASSTHEPOPCORN": {}}}, ["PASSTHEPOPCORN"], {"PASSTHEPOPCORN": PassThePopcorn})

    assert blocked == {"PASSTHEPOPCORN"}
    assert meta.tracker_status["PASSTHEPOPCORN"]["upload"] is False


@pytest.mark.asyncio
async def test_provision_contains_failures_and_reports_accurate_reasons(tmp_path, monkeypatch):
    from src.meta import Meta

    media = tmp_path / "release.mkv"
    media.touch()
    policy = TorrentPolicy(required_piece_size=4 * MIB)
    tracker_class_map = {tracker: type(tracker, (), {"torrent_policy": policy}) for tracker in ("FAIL", "REJECT", "GOOD")}
    meta = Meta(base_dir=str(tmp_path), uuid="release", path=str(media), filelist=[str(media)], trackers=list(tracker_class_map))
    meta.tracker_status = {tracker: {"upload": True} for tracker in tracker_class_map}
    manifest = TorrentManifest(meta.base_dir, meta.uuid)

    async def create_torrent(hash_meta, _path, _output, **_kwargs):
        tracker = hash_meta.trackers[0]
        if tracker == "FAIL":
            raise OSError("disk unavailable")
        if tracker == "GOOD":
            generated = tmp_path / "good.torrent"
            write_torrent(generated)
            manifest.register(generated, "base", "generated")

    monkeypatch.setattr(TorrentCreator, "create_torrent", create_torrent)

    blocked = await provision_tracker_torrents(meta, {"TRACKERS": {}}, list(tracker_class_map), tracker_class_map)

    assert blocked == {"FAIL", "REJECT"}
    assert meta.tracker_status["FAIL"]["status_message"] == "Skipped: torrent provisioning failed: disk unavailable"
    assert meta.tracker_status["REJECT"]["status_message"] == "Skipped: generated torrent does not satisfy the tracker policy"
    assert meta.tracker_status["GOOD"]["upload"] is True
    assert manifest.selected_path("GOOD") is not None


@pytest.mark.asyncio
async def test_create_torrent_for_upload_rejects_missing_manifest_base(tmp_path):
    from src.meta import Meta

    meta = Meta(base_dir=str(tmp_path), uuid="release")

    with pytest.raises(FileNotFoundError, match="TEST: no selected base torrent"):
        await Common({"TRACKERS": {"TEST": {}}}).create_torrent_for_upload(meta, "TEST", "TEST")
