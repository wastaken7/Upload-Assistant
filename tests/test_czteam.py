# ruff: noqa: S101
import asyncio
import base64
import runpy
from pathlib import Path
from typing import Any

import httpx
import pytest

from src.meta import Meta
from src.trackers import czteam as czteam_module
from src.trackers.czteam import CZTeam
from src.trackersetup import STATIC_AUTH_TYPES, TrackerSetup, tracker_class_map

CONFIG = {"DEFAULT": {}, "TRACKERS": {"CZTEAM": {"username": "tester", "passkey": "abc123"}}}


def _mock_client(monkeypatch: pytest.MonkeyPatch, handler: Any) -> list[httpx.Request]:
    """Route every client the tracker creates through a mock transport."""
    requests: list[httpx.Request] = []
    real_client = httpx.AsyncClient

    def recording_handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return handler(request)

    def factory(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = httpx.MockTransport(recording_handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(czteam_module.httpx, "AsyncClient", factory)
    return requests


def _tracker(romanian: bool = False) -> CZTeam:
    tracker = CZTeam(CONFIG)

    async def fake_romanian(_meta: Meta) -> bool:
        return romanian

    tracker.has_romanian = fake_romanian  # type: ignore[method-assign]
    return tracker


def test_registration_and_config() -> None:
    example_config = runpy.run_path(str(Path(__file__).resolve().parents[1] / "data" / "example_config.py"))["config"]
    assert tracker_class_map["CZTEAM"] is CZTeam
    assert STATIC_AUTH_TYPES["CZTEAM"] == "other_api"
    assert example_config["TRACKERS"]["CZTEAM"]["cli_alias"] == "CZT"


@pytest.mark.parametrize(("category", "kept"), [("MOVIE", True), ("TV", True), ("GAME", True), ("MUSIC", True), ("XXX", True), ("BOOK", False)])
def test_supported_categories(category: str, kept: bool) -> None:
    meta = Meta(category=category, trackers=["CZTEAM"])
    TrackerSetup(CONFIG).filter_unsupported_trackers(meta)
    assert (meta.trackers == ["CZTEAM"]) is kept


@pytest.mark.parametrize(
    ("values", "romanian", "expected"),
    [
        ({"category": "MOVIE", "resolution": "1080p"}, False, 29),
        ({"category": "MOVIE", "resolution": "1080p"}, True, 38),
        ({"category": "MOVIE", "sd": 1}, False, 19),
        ({"category": "MOVIE", "is_disc": "BDMV"}, False, 36),
        ({"category": "MOVIE", "is_disc": "DVD"}, True, 28),
        ({"category": "MOVIE", "type": "HDTV"}, True, 33),
        ({"category": "TV", "resolution": "1080p"}, False, 5),
        ({"category": "TV", "resolution": "1080p"}, True, 34),
        ({"category": "TV", "sd": 1}, False, 7),
        ({"category": "TV", "anime": True}, False, 23),
        ({"category": "MOVIE", "genres": ["Documentary"]}, False, 25),
        ({"category": "XXX"}, False, 1),
        ({"category": "GAME", "platform": "SWITCH", "console_game": True}, False, 12),
        ({"category": "GAME", "platform": "MAC"}, False, 31),
        ({"category": "GAME", "platform": "PC", "filelist": ["Fictional Game/game.iso"]}, False, 4),
        ({"category": "GAME", "platform": "PC", "filelist": ["Fictional Game/setup.exe"]}, False, 21),
        ({"category": "MUSIC", "format": "FLAC"}, False, 35),
        ({"category": "MUSIC", "format": "MP3"}, False, 6),
    ],
)
def test_category_id(values: dict[str, Any], romanian: bool, expected: int) -> None:
    assert asyncio.run(_tracker(romanian).get_category_id(Meta(**values))) == expected


def test_form_fields_only_use_accepted_values() -> None:
    tracker = CZTeam(CONFIG)
    meta = Meta(resolution="1080p", video_encode="x264", container="mkv", type="WEBDL")
    assert (tracker.get_resolution(meta), tracker.get_codec(meta), tracker.get_container(meta), tracker.get_source(meta)) == ("1080p", "x264", "MKV", "WEB-DL")

    remux = Meta(resolution="1080i", video_codec="HEVC", container="m2ts", type="REMUX", source="BluRay")
    assert (tracker.get_resolution(remux), tracker.get_codec(remux), tracker.get_container(remux), tracker.get_source(remux)) == ("", "H.265", "TS", "BluRay")

    encode = Meta(type="ENCODE", source="DVD", video_codec="MPEG-4 Visual")
    assert (tracker.get_codec(encode), tracker.get_source(encode)) == ("", "DVDRip")


def test_search_existing_uses_imdb_and_maps_results(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api.php"
        params = request.url.params
        assert params["action"] == "search-torrents"
        assert params["type"] == "imdb"
        assert params["query"] == "tt0000001"
        assert params["season"] == "2"
        assert params["username"] == "tester"
        assert params["passkey"] == "abc123"
        return httpx.Response(200, json=[{"id": 9, "name": "Fictional.Show.S02.1080p.WEB-DL.x264-NOGRP", "size": 1000, "files": 8}, {"id": 10}])

    _mock_client(monkeypatch, handler)
    dupes = asyncio.run(CZTeam(CONFIG).search_existing(Meta(category="TV", imdb_tt="tt0000001", season="S02")))

    assert dupes == [{"name": "Fictional.Show.S02.1080p.WEB-DL.x264-NOGRP", "size": 1000, "files": [], "file_count": 8, "link": "https://czteam.me/details.php?id=9", "id": 9}]


def test_search_existing_falls_back_to_name_and_raises_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["type"] == "name"
        assert request.url.params["query"] == "Fictional Film"
        return httpx.Response(403, json={"error": "Invalid passkey"})

    _mock_client(monkeypatch, handler)
    with pytest.raises(RuntimeError, match="Invalid passkey"):
        asyncio.run(CZTeam(CONFIG).search_existing(Meta(category="MOVIE", title="Fictional Film")))


def _upload_meta(tmp_path: Path) -> Meta:
    (tmp_path / "tmp" / "abc").mkdir(parents=True)
    (tmp_path / "tmp" / "abc" / "MEDIAINFO_CLEANPATH.txt").write_text("General\n", encoding="utf-8")
    return Meta(
        category="MOVIE",
        base_dir=str(tmp_path),
        uuid="abc",
        name="Fictional Film 2001 1080p WEB-DL x264-FAKEGRP",
        imdb_tt="tt0000002",
        resolution="1080p",
        video_encode="x264",
        container="mkv",
        type="WEBDL",
    )


def _prepare_upload(tracker: CZTeam, monkeypatch: pytest.MonkeyPatch, torrent_path: Path) -> None:
    async def fake_create(_meta: Meta, tracker_name: str, _source_flag: str, **kwargs: Any) -> None:
        assert tracker_name == "CZTEAM"
        assert kwargs["announce_url"] == "https://tracker.czteam.me/announce"
        torrent_path.write_bytes(b"d4:infod4:name4:testee")

    async def fake_description(_meta: Meta) -> str:
        return "[b]Fictional description[/b]"

    monkeypatch.setattr(tracker.common, "create_torrent_for_upload", fake_create)
    monkeypatch.setattr(tracker, "generate_description", fake_description)


def test_upload_posts_form_and_saves_returned_torrent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    meta = _upload_meta(tmp_path)
    torrent_path = tmp_path / "tmp" / "abc" / "[CZTEAM].torrent"
    registered = b"d8:announce40:https://tracker.czteam.me/announce?pk=xe"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/takeupload_api.php"
        body = request.content
        assert b'name="passkey"\r\n\r\nabc123' in body
        assert b'name="category"\r\n\r\n29' in body
        assert b'name="descr"\r\n\r\nGeneral' in body
        assert b'name="imdb_id"\r\n\r\ntt0000002' in body
        assert b'name="source"\r\n\r\nWEB-DL' in body
        assert b'name="file"; filename="Fictional Film 2001 1080p WEB-DL x264-FAKEGRP.torrent"' in body
        return httpx.Response(201, json={"id": 77, "name": meta.name, "torrent_b64": base64.b64encode(registered).decode()})

    _mock_client(monkeypatch, handler)
    tracker = _tracker()
    _prepare_upload(tracker, monkeypatch, torrent_path)

    assert asyncio.run(tracker.upload(meta)) is True
    assert meta.tracker_status["CZTEAM"]["torrent_id"] == "77"
    assert torrent_path.read_bytes() == registered


def test_upload_reports_existing_name(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    meta = _upload_meta(tmp_path)
    _mock_client(monkeypatch, lambda _request: httpx.Response(409, json={"id": 5, "torrent_b64": ""}))
    tracker = _tracker()
    _prepare_upload(tracker, monkeypatch, tmp_path / "tmp" / "abc" / "[CZTEAM].torrent")

    assert asyncio.run(tracker.upload(meta)) is False
    assert "details.php?id=5" in meta.tracker_status["CZTEAM"]["status_message"]


@pytest.mark.parametrize(
    ("values", "query", "category"),
    [
        ({"category": "GAME", "game_title": "Fictional Quest", "title": "fictional quest repack", "imdb_tt": "tt0000003"}, "Fictional Quest", "12,4,21,31"),
        ({"category": "MUSIC", "music_artist": "Fake Band", "music_album": "Imaginary Album", "title": "x"}, "Fake Band Imaginary Album", "6,35,30"),
    ],
)
def test_search_existing_non_video_uses_name_and_category(monkeypatch: pytest.MonkeyPatch, values: dict[str, Any], query: str, category: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["type"] == "name"
        assert request.url.params["query"] == query
        assert request.url.params["category"] == category
        return httpx.Response(200, json=[])

    _mock_client(monkeypatch, handler)
    assert asyncio.run(CZTeam(CONFIG).search_existing(Meta(**values))) == []


def test_non_video_data_omits_video_fields(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "tmp" / "abc").mkdir(parents=True)
    (tmp_path / "tmp" / "abc" / "MEDIAINFO_CLEANPATH.txt").write_text("General\n", encoding="utf-8")
    tracker = _tracker()

    async def fake_description(_meta: Meta) -> str:
        return "Fictional description"

    monkeypatch.setattr(tracker, "generate_description", fake_description)
    meta = Meta(
        category="MUSIC",
        base_dir=str(tmp_path),
        uuid="abc",
        name="Fake Band - Imaginary Album (2020) [FLAC]",
        format="FLAC",
        music_genres="Rock, Pop",
        imdb_tt="tt0000004",
        resolution="1080p",
        container="mkv",
        artwork_url="https://img.example/cover.jpg",
    )

    data = asyncio.run(tracker.get_data(meta))

    assert data["category"] == 35
    assert data["genre"] == "Rock, Pop"
    assert data["poster"] == "https://img.example/cover.jpg"
    assert not {"descr", "imdb_id", "resolution", "codec", "container", "source"} & data.keys()


@pytest.mark.parametrize("with_signature", [True, False])
def test_bdmv_description_includes_bdinfo_before_signature(monkeypatch: pytest.MonkeyPatch, with_signature: bool) -> None:
    from src.get_desc import DescriptionBuilder

    meta = Meta(category="MOVIE", is_disc="BDMV", discs=[{"summary": "Disc Title: Fictional Film\n"}, {"summary": "Disc Title: Fictional Film Extras"}])
    signature = f"[right][url=https://github.com/wastaken7/Upload-Assistant]{meta.ua_signature}[/url][/right]"

    async def fake_generator(_self: DescriptionBuilder, _meta: Meta, **kwargs: Any) -> str:
        assert kwargs["mediainfo"] is False
        return f"[b]Fictional description[/b]\n{signature if with_signature else ''}"

    monkeypatch.setattr(DescriptionBuilder, "general_description_generator", fake_generator)
    description = asyncio.run(CZTeam(CONFIG).generate_description(meta))

    bdinfo_block = "[pre]Disc Title: Fictional Film\n\n\nDisc Title: Fictional Film Extras[/pre]"
    assert bdinfo_block in description
    assert description.startswith("[b]Fictional description[/b]")
    if with_signature:
        assert description.endswith(f"{bdinfo_block}\n\n{signature}")
    else:
        assert description.endswith(bdinfo_block)


def test_non_disc_description_has_no_bdinfo(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.get_desc import DescriptionBuilder

    async def fake_generator(_self: DescriptionBuilder, _meta: Meta, **_kwargs: Any) -> str:
        return "Fictional description"

    monkeypatch.setattr(DescriptionBuilder, "general_description_generator", fake_generator)
    assert asyncio.run(CZTeam(CONFIG).generate_description(Meta(category="MOVIE"))) == "Fictional description"


def test_description_images_drop_size_parameter() -> None:
    from src.get_desc import DescriptionBuilder

    builder = DescriptionBuilder("CZTEAM", CONFIG)
    formatted = builder.tracker_specific_formats("CZTEAM", "[url=https://img.example/a.png][img=350]https://img.example/a.png[/img][/url]")
    assert formatted == "[url=https://img.example/a.png][img]https://img.example/a.png[/img][/url]"


def test_description_converts_unsupported_bbcode() -> None:
    from src.get_desc import DescriptionBuilder

    builder = DescriptionBuilder("CZTEAM", CONFIG)
    source = (
        "[h2]Screenshots[/h2]\n"
        "[center][spoiler=Scene NFO:][code]  aligned  text[/code][/spoiler][/center]\n"
        "[hide=Extras]hidden[/hide]\n"
        "[align=center]centered[/align][align=left]left[/align][left]plain[/left]\n"
        "[size=20]big[/size][hr][note]note[/note][alert]alert[/alert]x[sup]2[/sup]"
    )

    formatted = builder.tracker_specific_formats("CZTEAM", source)

    assert formatted == (
        "[size=5][b]Screenshots[/b][/size]\n"
        "[center][b]Scene NFO:[/b]\n[spoiler][pre]  aligned  text[/pre][/spoiler][/center]\n"
        "[b]Extras[/b]\n[spoiler]hidden[/spoiler]\n"
        "[center]centered[/center]leftplain\n"
        "[size=7]big[/size]notealertx2"
    )


def test_description_comparison_becomes_centered_images() -> None:
    from src.get_desc import DescriptionBuilder

    builder = DescriptionBuilder("CZTEAM", CONFIG)
    source = "[comparison=Source, Encode]\nhttps://img.example/a.png\nhttps://img.example/b.png\n[/comparison]"

    formatted = builder.tracker_specific_formats("CZTEAM", source)

    assert "[comparison" not in formatted
    assert formatted.startswith("[center]Source | Encode\n")
    assert "[url=https://img.example/a.png][img]https://img.example/a.png[/img][/url]" in formatted


@pytest.mark.parametrize("tracker", ["CZTEAM", "AITHER"])
def test_game_section_drops_tables_only_for_czteam(tracker: str) -> None:
    from src.get_desc import DescriptionBuilder

    meta = Meta(category="GAME", platform="PC", game_version="1.0")
    config = {"DEFAULT": {}, "TRACKERS": {tracker: {}}}
    section = DescriptionBuilder(tracker, config)._build_game_desc_section(meta)  # pyright: ignore[reportPrivateUsage]

    assert ("[table]" in section) is (tracker != "CZTEAM")
    assert "PC" in section


@pytest.mark.parametrize("status", [201, 409])
def test_upload_handles_non_object_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, status: int) -> None:
    meta = _upload_meta(tmp_path)
    _mock_client(monkeypatch, lambda _request: httpx.Response(status, json=["unexpected"]))
    tracker = _tracker()
    _prepare_upload(tracker, monkeypatch, tmp_path / "tmp" / "abc" / "[CZTEAM].torrent")

    assert asyncio.run(tracker.upload(meta)) is False
    assert meta.tracker_status["CZTEAM"]["status_message"].startswith("data error:")
