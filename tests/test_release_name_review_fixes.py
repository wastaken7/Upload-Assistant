# ruff: noqa: S101

import asyncio
from types import SimpleNamespace

from src.get_name import NameManager
from src.languages import languages_manager
from src.meta import Meta
from src.torrentcreate import TorrentCreator
from src.trackers.funfile import FunFile
from src.trackers.hdbits import HDBits
from src.trackers.tvchaosuk import TVChaosUK
from src.trackers.UNIT3D import UNIT3D
from src.trackers.UNIT3D.onlyencodes import OnlyEncodes
from src.trackers.UNIT3D.polishtorrent import PolishTorrent
from src.trackers.UNIT3D.samaritano import Samaritano
from src.trackers.UNIT3D.theoldschool import TheOldSchool
from src.trackers.UNIT3D.znth import Zenith


def test_default_book_name_normalizes_source_without_leading_dash() -> None:
    meta = Meta(category="BOOK", title="Book", type="EPUB", source=" Scan ")

    name_notag, *_ = asyncio.run(NameManager({}).get_name(meta))

    assert name_notag == "Book SCAN ePUB eBOOK"


def test_default_music_name_omits_dash_without_artist() -> None:
    meta = Meta(category="MUSIC", title="Album", year=2026, source="WEB", type="AAC")

    name_notag, *_ = asyncio.run(NameManager({}).get_name(meta))

    assert name_notag == "Album 2026 WEB AAC"


def test_funfile_preserves_scene_name_spaces_but_dots_scene_fallback() -> None:
    tracker = FunFile({"TRACKERS": {"FUNFILE": {}}})
    scene_name = Meta(scene=True, scene_name="Scene Release Name", basename_no_ext="Fallback Release Name")
    scene_fallback = Meta(scene=True, basename_no_ext="Fallback Release Name")

    assert asyncio.run(tracker.get_name(scene_name)) == "Scene Release Name"
    assert asyncio.run(tracker.get_name(scene_fallback)) == "Fallback.Release.Name"


def test_hdbits_preserves_title_when_imdb_aka_is_missing() -> None:
    meta = SimpleNamespace(
        name="Movie Title 2026 1080p WEB-DL DD 5.1 H.264-GROUP",
        audio="DD 5.1",
        service="",
        hdr="",
        aka="",
        imdb_info={"year": 2026},
        title="Movie Title",
        year=2026,
        type="WEBDL",
    )

    assert asyncio.run(HDBits({}).get_name(meta)).startswith("Movie Title 2026")


def test_onlyencodes_uses_languages_populated_during_name_render(monkeypatch) -> None:
    async def process(meta: Meta, tracker: str) -> None:
        assert tracker == "ONLYENCODES"
        meta.audio_languages = ["French"]
        meta.language_checked = True

    monkeypatch.setattr(languages_manager, "process_desc_language", process)
    meta = Meta(
        category="MOVIE",
        type="WEBRIP",
        resolution="1080p",
        name="Movie 2026 1080p WEBRip x265-GROUP",
        tag="GROUP",
        language_checked=False,
    )

    name = asyncio.run(OnlyEncodes({"DEFAULT": {}, "TRACKERS": {"ONLYENCODES": {}}}).get_name(meta))["name"]

    assert "FRENCH 1080p" in name


def test_polishtorrent_preserves_title_when_imdb_aka_is_missing() -> None:
    meta = Meta(
        category="MOVIE",
        name="Polish Title 2026 1080p WEB-DL",
        title="Polish Title",
        original_language="pl",
        imdb_info={"year": 2026},
    )

    name = asyncio.run(PolishTorrent({"TRACKERS": {"POLISHTORRENT": {}}}).get_name(meta))["name"]

    assert name.startswith("Polish Title 2026")


def test_samaritano_does_not_apply_capybara_dvdrip_rebuild() -> None:
    meta = Meta(
        category="MOVIE",
        name="Example Movie 2001 DVD x264 DVDRip DD 2.0-DDOS",
        title="Example Movie",
        year=2001,
        type="DVDRIP",
        resolution="480p",
        audio="DD 2.0",
        video_encode="x264",
        tag="-DDOS",
    )

    name = asyncio.run(Samaritano({"TRACKERS": {}}).get_name(meta))["name"]

    assert name == "Example Movie 2001 DVD x264 DVDRip DD2.0-DDOS"


def test_oldschool_rehashes_only_at_upload_boundary(monkeypatch) -> None:
    calls: list[str] = []

    async def create_torrent(meta: Meta, *_args, **_kwargs) -> None:
        calls.append(str(meta.path))

    async def upload(_self, _meta: Meta) -> bool:
        return True

    monkeypatch.setattr(TorrentCreator, "create_torrent", create_torrent)
    monkeypatch.setattr(UNIT3D, "upload", upload)
    tracker = TheOldSchool({"DEFAULT": {}, "TRACKERS": {"THEOLDSCHOOL": {}}})
    meta = Meta(keep_nfo=True, path="release", basename_no_ext="Release Name")

    assert asyncio.run(tracker.get_name(meta)) == {"name": "Release.Name"}
    assert calls == []
    assert asyncio.run(tracker.upload(meta)) is True
    assert calls == ["release"]


def test_zenith_audiobook_does_not_inherit_book_series() -> None:
    meta = Meta(
        category="BOOK",
        audiobook=True,
        author="Author",
        title="Title",
        book_series="Unwanted Series",
        year=2026,
        type="MP3",
    )

    name = asyncio.run(Zenith({"DEFAULT": {}, "TRACKERS": {"ZENITH": {}}}).get_name(meta))["name"]

    assert name == "Author - Title (2026) [WEB] MP3"


def test_tvchaosuk_uses_first_supported_country_code() -> None:
    tracker = object.__new__(TVChaosUK)
    meta = Meta(
        category="TV",
        title="Show",
        year=2026,
        season="S01",
        episode="E01",
        type="WEBDL",
        resolution="1080p",
        video="mkv",
        original_language="en",
        origin_country_code=["XX", "IE", "AU"],
    )

    name = asyncio.run(tracker.get_name(meta))

    assert name == "Show (2026) S01E01 [1080p WEB-DL MKV] [IRL]"
