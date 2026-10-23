import asyncio
from unittest.mock import AsyncMock, Mock

import httpx

from src.meta import Meta
from src.screenshot_manifest import register
from src.temp_paths import screenshots_dir
from src.trackers.NEXUSPHP.pterclub import PTerClub


def tracker() -> PTerClub:
    return PTerClub({"TRACKERS": {"PTERCLUB": {}}})


def test_small_description_falls_back_to_title_when_ptgen_is_missing():
    meta = Meta(title="Fallback title", ptgen={})

    assert tracker().get_small_description(meta) == "Fallback title"  # noqa: S101


def test_small_description_uses_nonempty_ptgen_titles_and_genre():
    meta = Meta(title="Fallback title", ptgen={"trans_title": ["译名", "", "又名"], "genre": ["剧情"]})

    assert tracker().get_small_description(meta) == "译名 / 又名 | 类别:剧情"  # noqa: S101


def test_area_falls_back_to_origin_country_when_ptgen_is_missing():
    assert asyncio.run(tracker().get_area_id(Meta(ptgen={}, origin_country=["JP"]))) == 6  # noqa: S101
    assert asyncio.run(tracker().get_area_id(Meta(ptgen={}, production_countries=[{"iso_3166_1": "US"}]))) == 4  # noqa: S101


def test_external_id_urls_match_upload_form_fields():
    meta = Meta(imdb_tt="tt1234567", douban_id=7654321)

    assert tracker().get_imdb_url(meta) == "https://www.imdb.com/title/tt1234567/"  # noqa: S101
    assert tracker().get_douban_url(meta) == "https://movie.douban.com/subject/7654321/"  # noqa: S101


def test_upload_submits_external_urls_and_omits_unchecked_checkboxes(tmp_path, monkeypatch):
    captured = {}

    async def fake_create_torrent(*_args, **_kwargs):
        return None

    def capture_data(data):
        captured.update(data)
        return data

    monkeypatch.setattr("src.trackers.common.Common.create_torrent_for_upload", fake_create_torrent)
    monkeypatch.setattr("src.trackers.NEXUSPHP.pterclub.Redaction.redact_private_info", capture_data)
    work_dir = tmp_path / "tmp" / "test"
    work_dir.mkdir(parents=True)
    (work_dir / "[PTERCLUB]DESCRIPTION.txt").write_text("description", encoding="utf-8")
    (work_dir / "[PTERCLUB].torrent").write_bytes(b"torrent")
    (work_dir / "MEDIAINFO.txt").write_text("media info", encoding="utf-8")
    meta = Meta(
        base_dir=str(tmp_path),
        uuid="test",
        debug=True,
        name="Release",
        title="Fallback title",
        aka="",
        imdb_tt="tt1234567",
        douban_id=7654321,
        type="WEBDL",
        category="MOVIE",
        resolution="1080p",
        filelist=["video.mkv"],
        video=str(tmp_path / "video.mkv"),
        path=str(tmp_path),
        mediainfo={"media": {"track": []}},
        ptgen={},
        tracker_status={"PTERCLUB": {}},
    )

    assert asyncio.run(tracker().upload(meta)) is True  # noqa: S101
    assert captured["url"] == "https://www.imdb.com/title/tt1234567/"  # noqa: S101
    assert captured["douban"] == "https://movie.douban.com/subject/7654321/"  # noqa: S101
    assert captured["small_descr"] == "Fallback title"  # noqa: S101
    assert "uplver" not in captured  # noqa: S101
    assert "zhongzi" not in captured  # noqa: S101


def test_description_uses_full_size_screenshot_url(tmp_path, monkeypatch):
    monkeypatch.setattr("src.description_review.get_base_description", lambda _meta: "base")
    work_dir = tmp_path / "tmp" / "test"
    work_dir.mkdir(parents=True)
    (work_dir / "MEDIAINFO_CLEANPATH.txt").write_text("media info", encoding="utf-8")
    meta = Meta(
        base_dir=str(tmp_path),
        uuid="test",
        title="Title",
        screens=1,
        image_list=[
            {
                "web_url": "https://images.example/view",
                "img_url": "https://images.example/thumbnail.png",
                "raw_url": "https://images.example/full.png",
            }
        ],
    )

    asyncio.run(tracker().edit_desc(meta))

    description = (work_dir / "[PTERCLUB]DESCRIPTION.txt").read_text(encoding="utf-8")
    assert "[img]https://images.example/full.png[/img]" in description  # noqa: S101
    assert "thumbnail.png" not in description  # noqa: S101


def test_rehosting_uploads_registered_main_screenshots(tmp_path, monkeypatch):
    meta = Meta(base_dir=str(tmp_path), uuid="test", filename="Example.Show")
    directory = screenshots_dir(tmp_path, meta.uuid)
    screenshot = directory / f"{meta.filename}-1.png"
    screenshot.write_bytes(b"png")
    screenshot = register(tmp_path, meta.uuid, [screenshot], "main")[0]
    extra = directory / "extra.png"
    extra.write_bytes(b"extra")
    register(tmp_path, meta.uuid, [extra], "FILE_1")

    cookie_file = tmp_path / "cookies.txt"
    cookie_file.touch()
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.post.return_value = httpx.Response(200, json={"image": {"url": "https://images.example/screen.png"}})
    pterclub = tracker()
    monkeypatch.setattr(pterclub, "get_auth_token", AsyncMock(return_value="token"))
    monkeypatch.setattr(pterclub.cookie_validator, "_load_cookies_dict_secure", Mock(return_value={}))
    monkeypatch.setattr("src.cookie_auth.find_cookie_file", lambda *_args: str(cookie_file))
    monkeypatch.setattr("src.trackers.NEXUSPHP.pterclub.httpx.AsyncClient", lambda **_kwargs: client)
    monkeypatch.setattr("src.trackers.NEXUSPHP.pterclub.record_event_async", AsyncMock())

    images = asyncio.run(pterclub.pterimg_upload(meta))

    assert images == [{"web_url": "https://images.example/screen.png", "img_url": "https://images.example/screen.png"}]  # noqa: S101
    client.post.assert_awaited_once()
    assert client.post.await_args.kwargs["files"] == {"source": (screenshot.name, b"png")}  # noqa: S101
