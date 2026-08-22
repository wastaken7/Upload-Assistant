import asyncio
from types import SimpleNamespace

from src.trackers.hdbits import HDBits


def make_meta(**overrides):
    values = {
        "name": "The Hateful Eight 2015 1080p WEB-DL DD+ 5.1 H.264-GROUP",
        "audio": "DD+ 5.1",
        "service": None,
        "hdr": "",
        "aka": "",
        "imdb_info": {},
        "title": "The Hateful Eight",
        "year": 2015,
        "type": "WEBDL",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_hdbits_preserves_title_spacing_without_service():
    name = asyncio.run(HDBits({}).get_name(make_meta()))

    assert name.startswith("The Hateful Eight 2015")  # noqa: S101
