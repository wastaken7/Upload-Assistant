import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.meta import Meta
from src.screenshot_manifest import register
from src.temp_paths import screenshots_dir
from src.tracker_images import set_tracker_image_collection
from src.trackers.GAZELLE.passthepopcorn import PassThePopcorn


@pytest.mark.parametrize("prepared", [False, True])
def test_dvd_description_uses_registered_disc_screenshots(tmp_path, monkeypatch, prepared):
    directory = screenshots_dir(tmp_path, "release")
    (directory / "Example.Disc.1-0.png").write_bytes(b"stray")
    registered = []

    def capture(*_args):
        screenshot = directory / "extra.png"
        screenshot.write_bytes(b"png")
        registered.extend(register(tmp_path, "release", [screenshot], "FILE_1"))

    if prepared:
        capture()
    image = {"raw_url": "https://imgbox.com/extra.png", "web_url": "https://imgbox.com/extra", "img_url": "https://imgbox.com/extra.png"}
    hosting = AsyncMock(return_value=([image], 1))
    capture_mock = AsyncMock(side_effect=capture)
    tracker = object.__new__(PassThePopcorn)
    tracker.config = {"DEFAULT": {"multiScreens": 2}}
    tracker.approved_image_hosts = ["imgbox"]
    tracker.uploadscreens_manager = SimpleNamespace(upload_screens=hosting)
    tracker.takescreens_manager = SimpleNamespace(dvd_screenshots=capture_mock)
    tracker.save_image_links = AsyncMock()
    monkeypatch.setattr("src.description_review.get_base_description", lambda _meta: "Example description")
    meta = Meta(
        base_dir=str(tmp_path),
        uuid="release",
        is_disc="DVD",
        discs=[{"type": "DVD", "name": f"Example.Disc.{index}", "ifo_mi_full": "IFO", "vob_mi_full": "VOB"} for index in range(2)],
    )

    asyncio.run(tracker.edit_desc(meta))

    assert capture_mock.await_count == (0 if prepared else 1)  # noqa: S101
    hosting.assert_awaited_once()
    assert hosting.await_args.args[5] == [registered[0].name]  # noqa: S101
    assert image["raw_url"] in (directory.parent / "[PASSTHEPOPCORN]DESCRIPTION.txt").read_text(encoding="utf-8")  # noqa: S101


def test_convert_bbcode_removes_unsupported_font_tags() -> None:
    tracker = object.__new__(PassThePopcorn)

    converted = tracker.convert_bbcode("Before [font=Courier New]formatted text[/font] after")

    assert converted == "Before formatted text after"  # noqa: S101


def test_convert_bbcode_clamps_unsupported_size_tags() -> None:
    tracker = object.__new__(PassThePopcorn)

    converted = tracker.convert_bbcode("[size=4]Normal[/size] [size=16]Oversized[/size]")

    assert converted == "[size=4]Normal[/size] [size=10]Oversized[/size]"  # noqa: S101


def test_disc_menu_images_precede_movie_screenshots_in_description() -> None:
    tracker = object.__new__(PassThePopcorn)
    meta = Meta(
        is_disc="DVD",
        image_list=[{"raw_url": "https://imgbox.com/movie.png"}],
        menu_images=[{"raw_url": "https://imgbox.com/original-menu.png"}],
    )
    rehosted_menu = {"raw_url": "https://imgbox.com/menu.png"}
    set_tracker_image_collection(meta, tracker.tracker, "menu_images", [rehosted_menu])

    assert tracker._description_images(meta) == [rehosted_menu, meta.image_list[0]]  # noqa: S101
    assert tracker._description_image_limit(meta, 6) == 7  # noqa: S101


def test_successful_upload_records_torrent_link(tmp_path, monkeypatch):
    import httpx

    import src.trackers.GAZELLE.passthepopcorn as ptp_module
    from src.trackers.common import Common

    meta = Meta(base_dir=str(tmp_path), uuid="release")
    meta.debug = False
    meta.tracker_status = {"PASSTHEPOPCORN": {}}
    torrent_dir = tmp_path / "tmp" / "release"
    torrent_dir.mkdir(parents=True)
    (torrent_dir / "[PASSTHEPOPCORN].torrent").write_bytes(b"torrent")

    tracker = object.__new__(PassThePopcorn)
    tracker.config = {}
    tracker.announce_url = "https://please.passthepopcorn.me/example/announce"
    tracker.user_agent = "test"
    tracker.cookie_validator = SimpleNamespace(_load_cookies_dict_secure=lambda _path: {})
    monkeypatch.setattr("src.cookie_auth.find_cookie_file", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(Common, "create_torrent_for_upload", AsyncMock())
    ready_to_seed = AsyncMock()
    monkeypatch.setattr(Common, "create_torrent_ready_to_seed", ready_to_seed)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(303, headers={"Location": "https://passthepopcorn.me/torrents.php?id=12&torrentid=345"}, request=request)
        return httpx.Response(200, text="uploaded", request=request)

    original_async_client = httpx.AsyncClient

    def make_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return original_async_client(*args, **kwargs)

    monkeypatch.setattr(ptp_module.httpx, "AsyncClient", make_client)

    assert asyncio.run(tracker.upload(meta, "https://passthepopcorn.me/upload.php", {})) is True  # noqa: S101
    status = meta.tracker_status["PASSTHEPOPCORN"]
    link = "https://passthepopcorn.me/torrents.php?id=12&torrentid=345"
    assert status["torrent_id"] == "345"  # noqa: S101
    assert status["torrent_link"] == link  # noqa: S101
    assert ready_to_seed.await_args.args[-1] == link  # noqa: S101
