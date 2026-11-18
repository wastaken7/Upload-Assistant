"""Regression tests for DigitalCore description formatting and torrent download."""

import contextlib

import bencodepy
import pytest

from src.get_desc import DescriptionBuilder
from src.meta import Meta
from src.trackers.common import Common


def test_digitalcore_rewrites_sized_img_tags_to_plain_img():
    builder = DescriptionBuilder("DIGITALCORE", {"DEFAULT": {}, "TRACKERS": {"DIGITALCORE": {}}})
    description = "[url=https://img.example/1][img=350]https://img.example/1.png[/img][/url]"

    formatted = builder.tracker_specific_formats("DIGITALCORE", description)

    assert "[img=350]" not in formatted
    assert "[img]https://img.example/1.png[/img]" in formatted


def test_digitalcore_converts_unsupported_tags():
    builder = object.__new__(DescriptionBuilder)
    cases = {
        "[strike]old[/strike] x[sup]2[/sup] [note]n[/note]": "[s]old[/s] x2 n",
        "[h1]Title[/h1] [H6]Small[/H6]": "[u][b]Title[/b][/u] [u][b]Small[/b][/u]",
        '[url="https://example.test"]link[/url]': "[url=https://example.test]link[/url]",
        "[align=center]a[/align][right]b[/right][align=justify]c[/align][indent]d[/indent]": "[center]a[/center]bcd",
        "[hide=Menu]x[/hide][collapse]y[/collapse][spoiler=BDInfo]z[/spoiler]": "[spoiler=Menu]x[/spoiler][spoiler]y[/spoiler][spoiler=BDInfo]z[/spoiler]",
        "[list][*]a[/list] [hr]": "[list][*]a[/list] [hr]",
        "[youtube]abcdefghijk[/youtube] [youtube]https://youtu.be/abcdefghijk[/youtube]": "[video]https://www.youtube.com/watch?v=abcdefghijk[/video] [video]https://youtu.be/abcdefghijk[/video]",
    }

    for description, expected in cases.items():
        assert builder.tracker_specific_formats("DIGITALCORE", description) == expected


def _patch_client(monkeypatch, fail):
    class Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        @contextlib.asynccontextmanager
        async def stream(self, method, url):
            yield self

        def raise_for_status(self):
            if fail:
                raise RuntimeError("404")

        async def aiter_bytes(self):
            yield bencodepy.encode({b"info": {b"name": b"test", b"length": 1, b"piece length": 16384, b"pieces": b"x" * 20}})

    monkeypatch.setattr("src.trackers.common.httpx.AsyncClient", Client)


@pytest.mark.asyncio
async def test_download_tracker_torrent_returns_the_path_only_on_success(tmp_path, monkeypatch):
    meta = Meta(base_dir=str(tmp_path), uuid="case")
    (tmp_path / "tmp" / "case").mkdir(parents=True)
    torrent_path = tmp_path / "tmp" / "case" / "[TESTTRK].torrent"
    torrent_path.write_bytes(b"stale")
    common = Common({})

    _patch_client(monkeypatch, fail=True)
    assert await common.download_tracker_torrent(meta, "TESTTRK", downurl="https://example.invalid/dl") is None
    assert torrent_path.read_bytes() == b"stale"

    _patch_client(monkeypatch, fail=False)
    assert await common.download_tracker_torrent(meta, "TESTTRK", downurl="https://example.invalid/dl")
    assert bencodepy.decode(torrent_path.read_bytes())[b"info"][b"name"] == b"test"
