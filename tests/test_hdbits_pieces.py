from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from torf import Torrent

from src.clients import Clients
from src.meta import Meta
from src.torrentcreate import TorrentCreator, hdbits_pieces_allowed
from src.trackers.hdbits import HDBits

MIB = 1024**2
GIB = 1024**3
TIB = 1024**4


def write_torrent(path, piece_size, size, name="release.mkv"):
    torrent = Torrent()
    count = (size + piece_size - 1) // piece_size
    torrent.metainfo["info"] = {"name": name, "length": size, "piece length": piece_size, "pieces": b"x" * (20 * count)}
    torrent.write(path, overwrite=True)
    return torrent


@pytest.mark.parametrize(
    ("piece_size", "count", "size", "allowed"),
    [
        (32768, 4000, 4000 * 32768, True),
        (32768, 4001, 4001 * 32768, False),
        (2 * MIB, 4000, 8000 * MIB, True),
        (2 * MIB, 4001, 8002 * MIB, False),
        (4 * MIB, 30000, 120000 * MIB, True),
        (4 * MIB, 30001, 120004 * MIB, False),
        (8 * MIB, 30000, 240000 * MIB, True),
        (8 * MIB, 30001, 240008 * MIB, False),
        (16 * MIB, 65536, TIB, True),
        (32 * MIB, 32768, TIB, False),
        (32 * MIB, 32769, TIB + 1, True),
        (64 * MIB, 32768, 2 * TIB, False),
    ],
)
def test_hdbits_piece_limits(piece_size, count, size, allowed):
    assert hdbits_pieces_allowed(piece_size, count, size) is allowed


@pytest.mark.parametrize("size", [1, 4000 * 32768, 4000 * 32768 + 1, 8 * GIB, 8 * GIB + 1, TIB + 1])
def test_hashing_uses_compliant_recommendation_even_with_small_configured_max(size):
    chosen = TorrentCreator.calculate_piece_size(size, 32768, 128 * MIB, Meta(trackers=["HDBITS"]), piece_size=1)
    assert hdbits_pieces_allowed(chosen, (size + chosen - 1) // chosen, size)
    if size > 8 * GIB:
        assert chosen == 16 * MIB


@pytest.fixture
def setup_release(tmp_path, monkeypatch):
    directory = tmp_path / "tmp" / "release"
    directory.mkdir(parents=True)
    media = tmp_path / "release.mkv"
    media.touch()
    meta = Meta(base_dir=str(tmp_path), uuid="release", path=str(media), filelist=[str(media)], trackers=["HDBITS"], category="MOVIE")
    meta.debug = True
    meta.video = str(media)
    meta.tracker_status = {"HDBITS": {}}
    for filename in ("[HDBITS]DESCRIPTION.txt", "MEDIAINFO_CLEANPATH.txt"):
        (directory / filename).write_text("")
    for method in ("edit_desc", "get_name", "get_type_category_id", "get_type_codec_id", "get_type_medium_id", "get_tags"):
        monkeypatch.setattr(HDBits, method, AsyncMock(return_value=1))
    config = {"DEFAULT": {"default_torrent_client": "none"}, "TORRENT_CLIENTS": {}, "TRACKERS": {"HDBITS": {}}}
    return directory, meta, config


@pytest.mark.asyncio
@pytest.mark.parametrize(("piece_size", "size"), [(2 * MIB, 4000 * 2 * MIB), (4 * MIB, 30000 * 4 * MIB), (8 * MIB, 30000 * 8 * MIB), (32 * MIB, TIB + 1)])
async def test_upload_reuses_allowed_base_without_search_or_hash(setup_release, monkeypatch, piece_size, size):
    directory, meta, config = setup_release
    original = write_torrent(directory / "BASE.torrent", piece_size, size)
    search = AsyncMock(side_effect=AssertionError("must not search"))
    create = AsyncMock(side_effect=AssertionError("must not rehash"))
    monkeypatch.setattr(Clients, "find_existing_torrent", search)
    monkeypatch.setattr(TorrentCreator, "create_torrent", create)
    assert await HDBits(config).upload(meta) is True
    result = Torrent.read(directory / "[HDBITS].torrent")
    assert result.piece_size == piece_size
    assert result.metainfo["info"]["pieces"] == original.metainfo["info"]["pieces"]


@pytest.mark.asyncio
async def test_upload_finds_alternative_before_rehash(setup_release, tmp_path, monkeypatch):
    directory, meta, config = setup_release
    size = 10 * GIB
    write_torrent(directory / "BASE.torrent", 2 * MIB, size)
    alternative = tmp_path / "alternative.torrent"
    write_torrent(alternative, 4 * MIB, size)
    search = AsyncMock(return_value=str(alternative))
    monkeypatch.setattr(Clients, "find_existing_torrent", search)
    monkeypatch.setattr(TorrentCreator, "create_torrent", AsyncMock(side_effect=AssertionError("must not rehash")))
    assert await HDBits(config).upload(meta) is True
    assert Torrent.read(directory / "[HDBITS].torrent").piece_size == 4 * MIB
    search.assert_awaited_once()
    assert Torrent.read(directory / "BASE.torrent").piece_size == 2 * MIB


@pytest.mark.asyncio
@pytest.mark.parametrize("nohash", [False, True])
async def test_upload_forces_rehash_only_after_failed_search(setup_release, monkeypatch, nohash):
    directory, meta, config = setup_release
    meta.nohash = nohash
    size = 10 * GIB
    write_torrent(directory / "BASE.torrent", 2 * MIB, size)
    search = AsyncMock(return_value=None)
    monkeypatch.setattr(Clients, "find_existing_torrent", search)

    async def create(hash_meta, path, output, **kwargs):
        search.assert_awaited_once()
        assert hash_meta.trackers == ["HDBITS"]
        write_torrent(directory / f"{output}.torrent", 16 * MIB, size)

    hashing = AsyncMock(side_effect=create)
    monkeypatch.setattr(TorrentCreator, "create_torrent", hashing)
    assert await HDBits(config).upload(meta) is True
    hashing.assert_awaited_once()
    assert Torrent.read(directory / "[HDBITS].torrent").piece_size == 16 * MIB


@pytest.mark.asyncio
async def test_client_search_skips_invalid_hash_and_uses_next_client(setup_release, tmp_path):
    directory, meta, config = setup_release
    meta.torrenthash = "abc"
    size = 120000 * MIB
    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir()
    second.mkdir()
    write_torrent(first / "abc.torrent", 2 * MIB, size)
    write_torrent(second / "abc.torrent", 4 * MIB, size)
    config["DEFAULT"].update(default_torrent_client="first", searching_client_list=["first", "second"])
    config["TORRENT_CLIENTS"] = {name: {"torrent_client": "qbit", "torrent_storage_dir": str(path)} for name, path in [("first", first), ("second", second)]}
    assert await Clients(config).find_existing_torrent(meta) == str(second / "abc.torrent")
    assert meta.reuse_torrent_client == "second"
    assert (first / "abc.torrent").exists()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("trackers", "piece_size", "pieces", "max_piece_size", "expected"),
    [
        (["HDBITS"], 16 * MIB, 12001, None, True),
        (["OTHER"], 16 * MIB, 12001, None, False),
        (["HDBITS", "OTHER"], 16 * MIB, 12001, None, False),
        (["OTHER", "HDBITS"], 16 * MIB, 12000, None, False),
        (["HDBITS", "OTHER"], 16 * MIB, 11999, None, True),
        (["HDBITS", "OTHER"], 16 * MIB, 12001, 0, True),
        (["OTHER"], 2 * MIB, 4001, None, True),
        (["HDBITS", "OTHER"], 2 * MIB, 4001, None, False),
        ("HDBITS", 16 * MIB, 12001, None, True),
        ("HDBITS,OTHER", 16 * MIB, 12001, None, False),
    ],
)
async def test_mixed_tracker_reuse_preserves_generic_and_hdbits_limits(setup_release, trackers, piece_size, pieces, max_piece_size, expected):
    directory, meta, config = setup_release
    path = directory / "candidate.torrent"
    torrent = write_torrent(path, piece_size, pieces * piece_size)
    meta.trackers = trackers
    meta.max_piece_size = max_piece_size
    valid, _ = await Clients(config).is_valid_torrent(meta, str(path), torrent.infohash, "qbit", {})
    assert valid is expected


@pytest.mark.asyncio
async def test_mkbrr_gets_recommended_size_even_with_tracker_url(setup_release, monkeypatch):
    directory, meta, config = setup_release
    with Path(meta.path).open("wb") as media:
        media.truncate(8 * GIB + 1)
    meta.mkbrr = True
    monkeypatch.setattr(TorrentCreator, "get_mkbrr_path", lambda _: meta.path)
    commands = []

    def process(command, **kwargs):
        commands.append(command)
        write_torrent(directory / "BASE.torrent", 16 * MIB, 8 * GIB + 1)
        return SimpleNamespace(stdout=[], wait=lambda: 0)

    monkeypatch.setattr("src.torrentcreate.subprocess.Popen", process)
    await TorrentCreator.create_torrent(meta, meta.path, "BASE", tracker_url="https://fake.tracker", piece_size=1)
    assert commands[0][commands[0].index("-l") + 1] == "24"
    assert meta.mkbrr
