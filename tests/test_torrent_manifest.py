import asyncio
import json
from pathlib import Path

import pytest
from torf import Torrent

from src.torrent_manifest import TorrentEntry, TorrentManifest
from src.torrent_policy import ANTHELION_POLICY, MIB, PASSTHEPOPCORN_POLICY, TorrentPolicy, TorrentStats, generic_reuse_allowed
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


def test_client_infohash_survives_normalization_and_managed_reregistration(tmp_path):
    source = tmp_path / "fictional-release.torrent"
    torrent = write_torrent(source)
    torrent.source = "CLIENT"
    torrent.write(source, overwrite=True)
    original_hash = torrent.infohash
    manifest = TorrentManifest(tmp_path, "fictional-release")

    entry = manifest.register(source, "base", "client:fictional-qbit", client_infohash=original_hash)
    assert entry.infohash != original_hash
    assert entry.client_infohash == original_hash

    managed = manifest.entry_path(entry)
    repeated = manifest.register(managed, "base", "client")
    assert repeated.client_infohash == original_hash
    assert repeated.origin == "client:fictional-qbit"


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


def _register_two_variants(tmp_path, first_piece_size: int, second_piece_size: int):
    first = tmp_path / "first.torrent"
    second = tmp_path / "second.torrent"
    write_torrent(first, first_piece_size, 64 * MIB)
    write_torrent(second, second_piece_size, 64 * MIB)
    manifest = TorrentManifest(tmp_path, "release")
    first_entry = manifest.register(first, "base", "client:first")
    second_entry = manifest.register(second, "base", "client:second")
    return manifest, first_entry, second_entry


def test_selection_keeps_the_preferred_variant_over_a_smaller_one(tmp_path):
    manifest, small, large = _register_two_variants(tmp_path, 16 * MIB, 32 * MIB)

    selected = manifest.select("TEST", "base", preferred=[manifest.entry_path(large)])

    assert selected == large
    assert manifest.selected_path("TEST") == manifest.entry_path(large)
    assert small.piece_size < large.piece_size


def test_selection_keeps_the_preferred_variant_when_the_policy_accepts_it(tmp_path):
    manifest, _small, large = _register_two_variants(tmp_path, 8 * MIB, 16 * MIB)

    selected = manifest.select("PASSTHEPOPCORN", "base", PASSTHEPOPCORN_POLICY, preferred=[manifest.entry_path(large)])

    assert selected == large


def test_selection_falls_back_to_the_smallest_variant_when_the_policy_rejects_the_preferred_one(tmp_path):
    manifest, small, large = _register_two_variants(tmp_path, 16 * MIB, 32 * MIB)

    selected = manifest.select("PASSTHEPOPCORN", "base", PASSTHEPOPCORN_POLICY, preferred=[None, manifest.entry_path(large)])

    assert selected == small


class _TrackerWithoutPolicy:
    pass


@pytest.mark.asyncio
async def test_provision_keeps_the_torrent_chosen_for_the_run(tmp_path):
    from src.meta import Meta

    manifest, _small, large = _register_two_variants(tmp_path, 16 * MIB, 32 * MIB)
    media = tmp_path / "release.mkv"
    media.touch()
    meta = Meta(base_dir=str(tmp_path), uuid="release", path=str(media), filelist=[str(media)], trackers=["TEST"])
    meta.reuse_torrent_path = str(manifest.entry_path(large))

    blocked = await provision_tracker_torrents(meta, {"TRACKERS": {"TEST": {}}}, ["TEST"], {"TEST": _TrackerWithoutPolicy})

    assert blocked == set()
    assert manifest.selected_path("TEST") == manifest.entry_path(large)


@pytest.mark.asyncio
async def test_provision_uses_the_default_base_when_the_run_chose_none(tmp_path):
    from src.meta import Meta

    manifest, large, _small = _register_two_variants(tmp_path, 32 * MIB, 16 * MIB)
    media = tmp_path / "release.mkv"
    media.touch()
    meta = Meta(base_dir=str(tmp_path), uuid="release", path=str(media), filelist=[str(media)], trackers=["TEST"])

    blocked = await provision_tracker_torrents(meta, {"TRACKERS": {"TEST": {}}}, ["TEST"], {"TEST": _TrackerWithoutPolicy})

    assert blocked == set()
    assert manifest.default_path("base") == manifest.entry_path(large)
    assert manifest.selected_path("TEST") == manifest.entry_path(large)


@pytest.mark.asyncio
async def test_provision_still_picks_a_compliant_variant_for_a_tracker_with_a_piece_limit(tmp_path):
    from src.meta import Meta

    manifest, small, large = _register_two_variants(tmp_path, 16 * MIB, 32 * MIB)
    media = tmp_path / "release.mkv"
    media.touch()
    meta = Meta(base_dir=str(tmp_path), uuid="release", path=str(media), filelist=[str(media)], trackers=["PASSTHEPOPCORN"], nohash=True)
    meta.reuse_torrent_path = str(manifest.entry_path(large))

    blocked = await provision_tracker_torrents(meta, {"TRACKERS": {"PASSTHEPOPCORN": {}}}, ["PASSTHEPOPCORN"], {"PASSTHEPOPCORN": PassThePopcorn})

    assert blocked == set()
    assert manifest.selected_path("PASSTHEPOPCORN") == manifest.entry_path(small)


def _default_meta(tmp_path, **overrides):
    from src.meta import Meta

    return Meta(base_dir=str(tmp_path), uuid="release", path=str(tmp_path / "release.mkv"), **overrides)


@pytest.mark.parametrize(
    ("piece_size", "pieces", "metainfo_size", "expected"),
    [
        (4 * MIB, 5000, 100 * 1024, False),  # 5000+ pieces at 4 MiB or below
        (4 * MIB, 4999, 100 * 1024, True),
        (8 * MIB, 8000, 163 * 1024, False),  # 8000+ pieces at 8 MiB or below
        (8 * MIB, 7999, 163 * 1024, True),
        (16 * MIB, 12000, 240 * 1024, False),  # 12000+ pieces
        (16 * MIB, 11999, 240 * 1024, True),
        (16 * MIB, 100, 250 * 1024 + 1, False),  # metainfo above 250 KiB
        (16 * MIB, 100, 250 * 1024, True),
    ],
)
def test_generic_reuse_limits_apply_when_no_max_piece_size_was_requested(tmp_path, piece_size, pieces, metainfo_size, expected):
    meta = _default_meta(tmp_path)

    assert generic_reuse_allowed(TorrentStats(piece_size, pieces, piece_size * pieces, metainfo_size), meta) is expected


def test_requested_max_piece_size_lifts_the_piece_count_and_metainfo_limits(tmp_path):
    meta = _default_meta(tmp_path, max_piece_size=16)

    assert generic_reuse_allowed(TorrentStats(16 * MIB, 12001, 16 * MIB * 12001, 300 * 1024), meta)
    assert not generic_reuse_allowed(TorrentStats(2 * MIB, 5000, 2 * MIB * 5000, 100 * 1024), meta)


def test_torrent_at_the_largest_piece_size_is_reused_despite_its_piece_count(tmp_path):
    meta = _default_meta(tmp_path)

    # Rehashing cannot reduce the piece count any further at 128 MiB.
    assert generic_reuse_allowed(TorrentStats(128 * MIB, 12089, 128 * MIB * 12089, 270 * 1024), meta)


@pytest.mark.parametrize("max_piece_size", [None, 128])
def test_client_torrent_above_the_largest_supported_piece_size_is_not_reused(tmp_path, max_piece_size):
    meta = _default_meta(tmp_path, max_piece_size=max_piece_size)

    assert not generic_reuse_allowed(TorrentStats(256 * MIB, 6045, 256 * MIB * 6045, 160 * 1024), meta)
    assert generic_reuse_allowed(TorrentStats(128 * MIB, 6045, 128 * MIB * 6045, 160 * 1024), meta)


def test_tracker_policies_reject_piece_sizes_above_the_largest_supported_one():
    assert not TorrentPolicy().accepts(TorrentStats(256 * MIB, 1, 256 * MIB, 100))
    assert TorrentPolicy().accepts(TorrentStats(128 * MIB, 1, 128 * MIB, 100))


def test_selection_never_returns_a_variant_above_the_largest_supported_piece_size(tmp_path):
    oversized = tmp_path / "oversized.torrent"
    usable = tmp_path / "usable.torrent"
    write_torrent(oversized, 256 * MIB, 512 * MIB)
    write_torrent(usable, 32 * MIB, 512 * MIB)
    manifest = TorrentManifest(tmp_path, "release")
    oversized_entry = manifest.register(oversized, "base", "client:first")
    usable_entry = manifest.register(usable, "base", "client:second")

    selected = manifest.select("TEST", "base", preferred=[manifest.entry_path(oversized_entry)])

    assert selected == usable_entry


@pytest.mark.asyncio
async def test_provision_hashes_a_new_torrent_when_only_an_oversized_variant_exists(tmp_path, monkeypatch):
    from src.meta import Meta

    oversized = tmp_path / "oversized.torrent"
    write_torrent(oversized, 256 * MIB, 512 * MIB)
    manifest = TorrentManifest(tmp_path, "release")
    manifest.register(oversized, "base", "client:first")
    media = tmp_path / "release.mkv"
    media.touch()
    meta = Meta(base_dir=str(tmp_path), uuid="release", path=str(media), filelist=[str(media)], trackers=["TEST"])
    created: list[int] = []

    async def create_torrent(_hash_meta, _path, _output, **kwargs):
        created.append(kwargs["piece_size"])
        generated = tmp_path / "generated.torrent"
        write_torrent(generated, 64 * MIB, 512 * MIB)
        manifest.register(generated, "base", "generated")

    monkeypatch.setattr(TorrentCreator, "create_torrent", create_torrent)

    blocked = await provision_tracker_torrents(meta, {"TRACKERS": {"TEST": {}}}, ["TEST"], {"TEST": _TrackerWithoutPolicy})

    assert blocked == set()
    assert len(created) == 1
    selected = manifest.selected_path("TEST")
    assert selected is not None
    assert Torrent.read(selected).piece_size == 64 * MIB


@pytest.mark.asyncio
async def test_provision_blocks_a_tracker_when_only_an_oversized_variant_exists_and_hashing_is_off(tmp_path):
    from src.meta import Meta

    oversized = tmp_path / "oversized.torrent"
    write_torrent(oversized, 256 * MIB, 512 * MIB)
    manifest = TorrentManifest(tmp_path, "release")
    manifest.register(oversized, "base", "client:first")
    media = tmp_path / "release.mkv"
    media.touch()
    meta = Meta(base_dir=str(tmp_path), uuid="release", path=str(media), filelist=[str(media)], trackers=["TEST"], nohash=True)

    blocked = await provision_tracker_torrents(meta, {"TRACKERS": {"TEST": {}}}, ["TEST"], {"TEST": _TrackerWithoutPolicy})

    assert blocked == {"TEST"}
    assert manifest.selected_path("TEST") is None


def _persist_selection(manifest: TorrentManifest, tracker: str, entry: TorrentEntry) -> None:
    data = json.loads(manifest.path.read_text(encoding="utf-8"))
    data["selections"][tracker] = entry.id
    manifest.path.write_text(json.dumps(data), encoding="utf-8")


def test_selection_from_an_earlier_run_is_cleared_when_no_variant_is_acceptable(tmp_path):
    oversized = tmp_path / "oversized.torrent"
    write_torrent(oversized, 256 * MIB, 512 * MIB)
    manifest = TorrentManifest(tmp_path, "release")
    entry = manifest.register(oversized, "base", "client:first")
    _persist_selection(manifest, "TEST", entry)
    assert manifest.selected_path("TEST") == manifest.entry_path(entry)

    assert manifest.select("TEST", "base") is None
    assert manifest.selected_path("TEST") is None


@pytest.mark.asyncio
async def test_provision_drops_an_earlier_oversized_selection_when_hashing_is_off(tmp_path):
    from src.meta import Meta

    oversized = tmp_path / "oversized.torrent"
    write_torrent(oversized, 256 * MIB, 512 * MIB)
    manifest = TorrentManifest(tmp_path, "release")
    entry = manifest.register(oversized, "base", "client:first")
    _persist_selection(manifest, "TEST", entry)
    media = tmp_path / "release.mkv"
    media.touch()
    meta = Meta(base_dir=str(tmp_path), uuid="release", path=str(media), filelist=[str(media)], trackers=["TEST"], nohash=True)

    blocked = await provision_tracker_torrents(meta, {"TRACKERS": {"TEST": {}}}, ["TEST"], {"TEST": _TrackerWithoutPolicy})

    assert blocked == {"TEST"}
    assert manifest.selected_path("TEST") is None


async def _provision_with_fake_hashing(tmp_path, monkeypatch, stored_piece_size, tracker_class, new_piece_size):
    from src.meta import Meta

    stored = tmp_path / "stored.torrent"
    write_torrent(stored, stored_piece_size, 512 * MIB)
    manifest = TorrentManifest(tmp_path, "release")
    stored_entry = manifest.register(stored, "base", "client:first")
    media = tmp_path / "release.mkv"
    media.touch()
    meta = Meta(base_dir=str(tmp_path), uuid="release", path=str(media), filelist=[str(media)], trackers=["TEST"])

    async def create_torrent(_hash_meta, _path, _output, **kwargs):
        generated = tmp_path / "generated.torrent"
        write_torrent(generated, new_piece_size, 512 * MIB)
        manifest.register(generated, "base", "generated", make_default=kwargs.get("make_default", False))

    monkeypatch.setattr(TorrentCreator, "create_torrent", create_torrent)
    blocked = await provision_tracker_torrents(meta, {"TRACKERS": {"TEST": {}}}, ["TEST"], {"TEST": tracker_class})
    assert blocked == set()
    return manifest, stored_entry


@pytest.mark.asyncio
async def test_replacement_for_an_oversized_default_becomes_the_default(tmp_path, monkeypatch):
    manifest, oversized_entry = await _provision_with_fake_hashing(tmp_path, monkeypatch, 256 * MIB, _TrackerWithoutPolicy, 64 * MIB)

    default = manifest.default_path("base")
    assert default is not None
    assert default != manifest.entry_path(oversized_entry)
    assert Torrent.read(default).piece_size == 64 * MIB
    assert default == manifest.selected_path("TEST")


@pytest.mark.asyncio
async def test_tracker_specific_replacement_leaves_a_usable_default_alone(tmp_path, monkeypatch):
    manifest, usable_entry = await _provision_with_fake_hashing(tmp_path, monkeypatch, 32 * MIB, PassThePopcorn, 16 * MIB)

    assert manifest.default_path("base") == manifest.entry_path(usable_entry)
    selected = manifest.selected_path("TEST")
    assert selected is not None
    assert Torrent.read(selected).piece_size == 16 * MIB


def test_default_moves_to_a_usable_variant_when_it_is_oversized(tmp_path):
    oversized = tmp_path / "oversized.torrent"
    small = tmp_path / "small.torrent"
    large = tmp_path / "large.torrent"
    write_torrent(oversized, 256 * MIB, 512 * MIB)
    write_torrent(small, 16 * MIB, 512 * MIB)
    write_torrent(large, 64 * MIB, 512 * MIB)
    manifest = TorrentManifest(tmp_path, "release")
    oversized_entry = manifest.register(oversized, "base", "client:first")
    manifest.register(small, "base", "client:second")
    large_entry = manifest.register(large, "base", "client:third")
    data = json.loads(manifest.path.read_text(encoding="utf-8"))
    # A manifest written before the piece-size bound existed still points at the oversized variant.
    data["defaults"]["base"] = oversized_entry.id
    manifest.path.write_text(json.dumps(data), encoding="utf-8")

    default = manifest.default_path("base")

    assert default == manifest.entry_path(large_entry)
    # The choice is stored, so later readers such as randomized torrents see the same base.
    assert json.loads(manifest.path.read_text(encoding="utf-8"))["defaults"]["base"] == large_entry.id


def test_oversized_default_without_a_usable_variant_counts_as_no_base(tmp_path):
    oversized = tmp_path / "oversized.torrent"
    write_torrent(oversized, 256 * MIB, 512 * MIB)
    manifest = TorrentManifest(tmp_path, "release")
    manifest.register(oversized, "base", "client:first")

    assert manifest.default_path("base") is None


def test_new_usable_variant_replaces_an_oversized_default(tmp_path):
    oversized = tmp_path / "oversized.torrent"
    usable = tmp_path / "usable.torrent"
    write_torrent(oversized, 256 * MIB, 512 * MIB)
    write_torrent(usable, 64 * MIB, 512 * MIB)
    manifest = TorrentManifest(tmp_path, "release")
    manifest.register(oversized, "base", "client:first")

    usable_entry = manifest.register(usable, "base", "generated")

    assert manifest.default_path("base") == manifest.entry_path(usable_entry)


def test_randomized_torrents_never_copy_an_oversized_default(tmp_path):
    oversized = tmp_path / "oversized.torrent"
    usable = tmp_path / "usable.torrent"
    write_torrent(oversized, 256 * MIB, 512 * MIB)
    write_torrent(usable, 64 * MIB, 512 * MIB)
    manifest = TorrentManifest(tmp_path, "release")
    oversized_entry = manifest.register(oversized, "base", "client:first")
    manifest.register(usable, "base", "client:second")
    data = json.loads(manifest.path.read_text(encoding="utf-8"))
    data["defaults"]["base"] = oversized_entry.id
    manifest.path.write_text(json.dumps(data), encoding="utf-8")

    TorrentCreator.create_random_torrents(str(tmp_path), "release", 1, str(tmp_path / "release.mkv"))

    randomized = next((tmp_path / "tmp" / "release").glob("[[]RAND-1[]]*.torrent"))
    assert Torrent.read(randomized).piece_size == 64 * MIB


def test_nohash_run_without_a_usable_base_skips_randomized_torrents(tmp_path):
    import upload
    from src.meta import Meta

    oversized = tmp_path / "oversized.torrent"
    write_torrent(oversized, 256 * MIB, 512 * MIB)
    manifest = TorrentManifest(tmp_path, "release")
    manifest.register(oversized, "base", "client:first")
    base = manifest.default_path("base")

    assert base is None
    assert upload._randomized_torrents_possible(Meta(nohash=True), base) is False
    # A hashing run with no base is a real error and must still reach it.
    assert upload._randomized_torrents_possible(Meta(nohash=False), base) is True


def test_nohash_run_with_a_usable_base_keeps_randomized_torrents(tmp_path):
    import upload
    from src.meta import Meta

    usable = tmp_path / "usable.torrent"
    write_torrent(usable, 64 * MIB, 512 * MIB)
    manifest = TorrentManifest(tmp_path, "release")
    manifest.register(usable, "base", "client:first")

    assert upload._randomized_torrents_possible(Meta(nohash=True), manifest.default_path("base")) is True
