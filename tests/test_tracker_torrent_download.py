"""Tracker downloads preserve the client torrent until a valid file is ready."""

import asyncio
import hashlib
from pathlib import Path

import bencodepy
import httpx
import pytest

from src.meta import Meta
from src.trackers.common import Common

TORRENT = bencodepy.encode({b"info": {b"name": b"test", b"length": 1, b"piece length": 16384, b"pieces": b"x" * 20}})


def _target(tmp_path, cross=False):
    meta = Meta(base_dir=str(tmp_path), uuid="download")
    path = tmp_path / "tmp" / meta.uuid / ("[TEST_cross].torrent" if cross else "[TEST].torrent")
    path.parent.mkdir(parents=True)
    path.write_bytes(b"existing local torrent")
    return meta, path


def _serve(monkeypatch, response):
    client = httpx.AsyncClient
    monkeypatch.setattr(
        "src.trackers.common.httpx.AsyncClient",
        lambda **kwargs: client(transport=httpx.MockTransport(lambda request: response), **kwargs),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("content", [b"", b'{"status":"failure"}', b"d4:info", b"le", b"de", b"d4:info4:nopee", b"d4:infodee"])
async def test_invalid_download_preserves_existing_file(tmp_path, monkeypatch, content):
    meta, path = _target(tmp_path)
    original = path.read_bytes()
    _serve(monkeypatch, httpx.Response(200, content=content))

    assert await Common({}).download_tracker_torrent(meta, "TEST", downurl="https://example.invalid/download") is None
    assert path.read_bytes() == original
    assert list(path.parent.iterdir()) == [path]


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True])
async def test_interrupted_download_preserves_existing_file(tmp_path, monkeypatch, cancel):
    meta, path = _target(tmp_path)
    original = path.read_bytes()

    class InterruptedStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield TORRENT[:20]
            assert path.read_bytes() == original
            if cancel:
                raise asyncio.CancelledError
            raise httpx.ReadError("stream interrupted")

    _serve(monkeypatch, httpx.Response(200, stream=InterruptedStream()))
    download = Common({}).download_tracker_torrent(meta, "TEST", downurl="https://example.invalid/download")
    if cancel:
        with pytest.raises(asyncio.CancelledError):
            await download
    else:
        assert await download is None
    assert path.read_bytes() == original
    assert list(path.parent.iterdir()) == [path]


@pytest.mark.asyncio
@pytest.mark.parametrize("cross,hash_is_id", [(False, False), (True, False), (False, True)])
async def test_valid_download_replaces_file_and_preserves_return_contract(tmp_path, monkeypatch, cross, hash_is_id):
    meta, path = _target(tmp_path, cross)
    original = path.read_bytes()

    class TorrentStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield TORRENT[:20]
            assert path.read_bytes() == original
            yield TORRENT[20:]

    _serve(monkeypatch, httpx.Response(200, stream=TorrentStream()))
    result = await Common({}).download_tracker_torrent(meta, "TEST", downurl="https://example.invalid/download", cross=cross, hash_is_id=hash_is_id)
    info_hash = hashlib.sha1(bencodepy.encode(bencodepy.decode(TORRENT)[b"info"]), usedforsecurity=False).hexdigest()
    assert result == (None if cross else info_hash if hash_is_id else f"{tmp_path}/tmp/download/[TEST].torrent")
    assert path.read_bytes() == TORRENT
    assert list(path.parent.iterdir()) == [path]


@pytest.mark.asyncio
async def test_replacement_error_preserves_existing_file(tmp_path, monkeypatch):
    meta, path = _target(tmp_path)
    original = path.read_bytes()
    _serve(monkeypatch, httpx.Response(200, content=TORRENT))

    def fail_replace(self, target):
        assert self.parent == path.parent
        assert self.read_bytes() == TORRENT
        raise OSError("replacement denied")

    monkeypatch.setattr(Path, "replace", fail_replace)
    assert await Common({}).download_tracker_torrent(meta, "TEST", downurl="https://example.invalid/download") is None
    assert path.read_bytes() == original
    assert list(path.parent.iterdir()) == [path]
