import asyncio
import importlib.util
import io
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest
from PIL import Image

from src.meta import Meta
from src.screenshot_manifest import register
from src.trackers.AVISTAZ.exoticaz import ExoticaZ

LISTING_HTML = """
<table class="table table-sm table-bordered"><tbody>
<tr><td></td><td><a class="torrent-link" href="https://exoticaz.to/torrent/11">Fictional Studio Sample Scene XXX 1080p</a></td>
<td></td><td>1 day</td><td>1.20 GB</td><td>3</td><td>0</td><td>5</td></tr>
</tbody></table>
"""


def make_tracker(**tracker_config) -> ExoticaZ:
    tracker = ExoticaZ({"DEFAULT": {}, "TRACKERS": {"EXOTICAZ": tracker_config}})
    tracker.cookie_validator.load_session_cookies = AsyncMock(return_value=None)
    return tracker


def make_meta(tmp_path: Path, **overrides) -> Meta:
    values = {
        "base_dir": str(tmp_path),
        "uuid": "exz-uuid",
        "category": "XXX",
        "name": "Fictional Studio 26 01 01 Sample Scene XXX 1080p",
        "title": "Sample Scene",
        "publisher": "FictionalStudio",
        "resolution": "1080p",
        "video_width": 1920,
        "video_height": 1080,
        "filelist": [str(tmp_path / "Fictional.Studio.Sample.Scene.XXX.1080p.mp4")],
        "keywords": ["big tits", "fictionalstudio", "asian", "uncensored"],
        "source_size": 500 * 1024 * 1024,
        "tracker_status": {"EXOTICAZ": {}},
        "unattended": True,
    }
    values.update(overrides)
    return Meta(**values)


def png_bytes(size: tuple[int, int]) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size).save(buffer, format="PNG")
    return buffer.getvalue()


FRAME = png_bytes((1920, 1080))
SHEET = png_bytes((1000, 2400))


def register_images(tmp_path: Path, images: dict[str, bytes]) -> None:
    screens_dir = tmp_path / "tmp" / "exz-uuid" / "screenshots"
    screens_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, content in images.items():
        path = screens_dir / name
        path.write_bytes(content)
        paths.append(path)
    register(tmp_path, "exz-uuid", paths, "main")


def test_category_and_resolution_ids(tmp_path: Path) -> None:
    tracker = make_tracker()

    assert asyncio.run(tracker.get_category_id(make_meta(tmp_path))) == "1"  # noqa: S101
    assert asyncio.run(make_tracker().get_category_id(make_meta(tmp_path, is_disc="BDMV"))) == "6"  # noqa: S101
    assert tracker.get_resolution_ids(make_meta(tmp_path, resolution="2160p")) == ["6"]  # noqa: S101
    assert tracker.get_resolution_ids(make_meta(tmp_path, resolution="OTHER", video_height=540)) == ["3"]  # noqa: S101


def test_unattended_multi_video_upload_is_skipped(tmp_path: Path) -> None:
    files = [str(tmp_path / f"Fictional.Scene.{index}.mp4") for index in range(2)]
    meta = make_meta(tmp_path, filelist=files)

    assert asyncio.run(make_tracker().get_category_id(meta)) == ""  # noqa: S101
    assert meta.skipping == "EXOTICAZ"  # noqa: S101


def test_extras_and_tags_exclude_filters_and_studios(tmp_path: Path) -> None:
    tracker = make_tracker()
    searched: list[str] = []

    async def fake_search(_endpoint: str, term: str):
        searched.append(term)
        return [{"id": 41, "tag": "big.tits"}]

    tracker._api_search = fake_search  # type: ignore[method-assign]
    meta = make_meta(tmp_path)

    assert tracker.get_extras(meta) == ["asian"]  # noqa: S101
    assert asyncio.run(tracker.get_tags(meta)) == ["41"]  # noqa: S101
    assert searched == []  # noqa: S101


def test_studio_matches_name_or_website(tmp_path: Path) -> None:
    tracker = make_tracker()
    tracker._api_search = AsyncMock(return_value=[{"id": 7, "name": "Other", "website": "https://www.fictionalstudio.com"}])  # type: ignore[method-assign]

    assert asyncio.run(tracker.get_studio_ids(make_meta(tmp_path))) == ["7"]  # noqa: S101


def test_rules_require_sheet_full_screenshot_and_minimum_size(tmp_path: Path) -> None:
    register_images(tmp_path, {"sheet.png": SHEET})
    meta = make_meta(tmp_path, source_size=10 * 1024 * 1024)

    warnings = make_tracker().rules(meta)

    assert "smaller than 20 MB" in warnings  # noqa: S101
    assert "full size screenshot" in warnings  # noqa: S101
    assert "video sheet (contact sheet)" not in warnings  # noqa: S101
    assert "Sample files" not in warnings  # noqa: S101


def test_rules_report_missing_video_sheet(tmp_path: Path) -> None:
    register_images(tmp_path, {"frame.png": FRAME})

    warnings = make_tracker().rules(make_meta(tmp_path))

    assert "video sheet (contact sheet)" in warnings  # noqa: S101
    assert "full size screenshot" not in warnings  # noqa: S101


def test_search_existing_parses_listing(tmp_path: Path) -> None:
    tracker = make_tracker()
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, text=LISTING_HTML)

    tracker.session = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    dupes = asyncio.run(tracker.search_existing(make_meta(tmp_path)))

    assert dupes == [{"name": "Fictional Studio Sample Scene XXX 1080p", "size": "1.20 GB", "link": "https://exoticaz.to/torrent/11"}]  # noqa: S101
    assert requests[0].url.params["search"] == "FictionalStudio Sample Scene"  # noqa: S101


def test_upload_creates_draft_uploads_images_and_publishes(tmp_path: Path) -> None:
    register_images(tmp_path, {"frame.png": FRAME, "sheet.png": SHEET})
    torrent_path = tmp_path / "tmp" / "exz-uuid" / "[EXOTICAZ].torrent"
    torrent_path.write_bytes(b"torrent")
    (tmp_path / "tmp" / "exz-uuid" / "MEDIAINFO_CLEANPATH.txt").write_text("General\n", encoding="utf-8")

    tracker = make_tracker(anon=False)
    ExoticaZ.secret_token = "token"  # type: ignore[attr-defined]  # noqa: S105
    tracker.edit_desc = AsyncMock(return_value="<p>Fictional</p>")  # type: ignore[method-assign]
    tracker._api_search = AsyncMock(return_value=[])  # type: ignore[method-assign]
    tracker.common.create_torrent_for_upload = AsyncMock()  # type: ignore[method-assign]
    tracker.common.download_tracker_torrent = AsyncMock(return_value=str(torrent_path))  # type: ignore[method-assign]
    calls: list[tuple[str, str, bytes]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.read()
        calls.append((request.method, request.url.path, body))
        if request.url.path == "/upload":
            return httpx.Response(302, headers={"Location": "https://exoticaz.to/edit/torrent/99"})
        if request.url.path == "/add/image/torrent/99":
            return httpx.Response(200, json={"success": True, "fileId": 500 + len(calls)})
        if request.url.path == "/edit/torrent/99":
            return httpx.Response(302, headers={"Location": "https://exoticaz.to/torrent/99"})
        return httpx.Response(200, text='<a href="https://exoticaz.to/download/torrent/99.abc.torrent">Download</a>')

    tracker.session = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    meta = make_meta(tmp_path)

    assert asyncio.run(tracker.upload(meta)) is True  # noqa: S101
    assert [path for _, path, _ in calls] == ["/upload", "/add/image/torrent/99", "/add/image/torrent/99", "/edit/torrent/99", "/torrent/99"]  # noqa: S101
    assert SHEET in calls[1][2]  # noqa: S101
    assert FRAME in calls[2][2]  # noqa: S101
    publish_body = calls[3][2]
    assert b"extra%5B%5D=asian" in publish_body  # noqa: S101
    assert b"resolution_ids%5B%5D=5" in publish_body  # noqa: S101
    assert b"file_ids%5B%5D=502&file_ids%5B%5D=503" in publish_body  # noqa: S101
    assert b"anon_upload" not in publish_body  # noqa: S101
    assert meta.tracker_status["EXOTICAZ"]["torrent_id"] == "99"  # noqa: S101
    tracker.common.download_tracker_torrent.assert_awaited_once()


def test_publish_redirect_back_to_edit_is_failure(tmp_path: Path) -> None:
    register_images(tmp_path, {"frame.png": FRAME, "sheet.png": SHEET})
    (tmp_path / "tmp" / "exz-uuid" / "[EXOTICAZ].torrent").write_bytes(b"torrent")
    (tmp_path / "tmp" / "exz-uuid" / "MEDIAINFO_CLEANPATH.txt").write_text("General\n", encoding="utf-8")

    tracker = make_tracker()
    ExoticaZ.secret_token = "token"  # type: ignore[attr-defined]  # noqa: S105
    tracker.edit_desc = AsyncMock(return_value="")  # type: ignore[method-assign]
    tracker._api_search = AsyncMock(return_value=[])  # type: ignore[method-assign]
    tracker.common.create_torrent_for_upload = AsyncMock()  # type: ignore[method-assign]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/upload":
            return httpx.Response(302, headers={"Location": "https://exoticaz.to/edit/torrent/99"})
        if request.url.path == "/add/image/torrent/99":
            return httpx.Response(200, json={"success": True, "fileId": 7})
        if request.method == "POST":
            return httpx.Response(302, headers={"Location": "https://exoticaz.to/edit/torrent/99"})
        return httpx.Response(200, text='<div class="alert alert-danger">The tag ids field is required.</div>')

    tracker.session = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    meta = make_meta(tmp_path)

    assert asyncio.run(tracker.upload(meta)) is False  # noqa: S101
    assert "The tag ids field is required." in meta.tracker_status["EXOTICAZ"]["status_message"]  # noqa: S101
    assert "torrent_id" not in meta.tracker_status["EXOTICAZ"]  # noqa: S101


def test_dimensions_fall_back_to_mediainfo_and_hyphenated_keywords_become_tags(tmp_path: Path) -> None:
    register_images(tmp_path, {"frame.png": png_bytes((1280, 720)), "sheet.webp": png_bytes((1600, 1080))})
    meta = make_meta(
        tmp_path,
        video_width=None,
        video_height=None,
        resolution="OTHER",
        keywords=["big-tits"],
        mediainfo={"media": {"track": [{"@type": "Video", "Width": "1280", "Height": "720"}]}},
    )
    tracker = make_tracker()
    tracker._api_search = AsyncMock(return_value=[{"id": 41, "tag": "big.tits"}])  # type: ignore[method-assign]

    assert tracker.get_resolution_ids(meta) == ["4"]  # noqa: S101
    assert "full size screenshot" not in tracker.rules(meta)  # noqa: S101
    assert asyncio.run(tracker.get_tags(meta)) == ["41"]  # noqa: S101


def test_bundled_catalog_resolves_synonyms_by_usage_and_searches_unknown_tags(tmp_path: Path) -> None:
    tracker = make_tracker()
    tracker._api_search = AsyncMock(return_value=[{"id": 9001, "tag": "fictional.new.tag"}])  # type: ignore[method-assign]
    meta = make_meta(tmp_path, keywords=["busty", "Japanese", "fictional new tag"])

    assert asyncio.run(tracker.get_tags(meta)) == ["2", "41", "9001"]  # noqa: S101
    tracker._api_search.assert_awaited_once_with("tags", "fictional.new.tag")


def test_update_script_parses_tags_with_synonyms() -> None:
    spec = importlib.util.spec_from_file_location("update_exoticaz_tags", Path(__file__).resolve().parent.parent / "scripts" / "update_exoticaz_tags.py")
    assert spec and spec.loader  # noqa: S101
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    html = """
    <table><tbody>
    <tr class="table-primary"><td><div class="tag">fictional.tag</div><a href="https://exoticaz.to/torrents?tags[]=7">s</a></td><td>2</td><td>1,234</td><td>x</td></tr>
    <tr class="table-secondary"><td><div class="tag">fictional.alias</div></td><td>-</td><td>-</td><td>x</td></tr>
    </tbody></table>
    <a href="https://exoticaz.to/tags?order=tag&amp;page=3">3</a>
    """

    assert script.parse_page(html) == ([{"id": 7, "tag": "fictional.tag", "usage": 1234, "synonyms": ["fictional.alias"]}], 3)  # noqa: S101


def test_missing_tags_are_asked_until_a_site_tag_is_entered(tmp_path: Path, monkeypatch) -> None:
    answers = iter(["fictional unknown tag", "Blowjob"])
    prompts: list[str] = []

    def fake_ask_string(question, *_args, **_kwargs):
        prompts.append(question)
        return next(answers)

    monkeypatch.setattr("src.manual_input.cli_ui.ask_string", fake_ask_string)
    tracker = make_tracker()
    tracker._api_search = AsyncMock(return_value=[])  # type: ignore[method-assign]
    meta = make_meta(tmp_path, keywords=[], unattended=False)

    assert asyncio.run(tracker.get_tags(meta)) == ["1905"]  # noqa: S101
    assert len(prompts) == 2  # noqa: S101
    assert meta.manual_answers["xxx.tags"] == ["Blowjob"]  # noqa: S101


def test_empty_tag_answer_cancels_the_upload(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("src.manual_input.cli_ui.ask_string", lambda *_args, **_kwargs: "")
    tracker = make_tracker()
    meta = make_meta(tmp_path, keywords=[], unattended=False)
    tags = asyncio.run(tracker.get_tags(meta))

    assert tags == []  # noqa: S101
    assert "at least one tag" in tracker.check_data(meta, {"category_id": "1", "tag_ids[]": tags, "resolution_ids[]": ["5"], "media_info": "General"})  # noqa: S101


def test_pre_answered_tags_are_not_asked(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("src.manual_input.cli_ui.ask_string", lambda *_args, **_kwargs: pytest.fail("asked"))
    meta = make_meta(tmp_path, keywords=[], answers={"xxx.tags": "blowjob"})

    assert asyncio.run(make_tracker().get_tags(meta)) == ["1905"]  # noqa: S101


def test_unattended_upload_without_tags_is_skipped_before_upload(tmp_path: Path) -> None:
    tracker = make_tracker(check_for_rules=False)
    tracker._api_search = AsyncMock(return_value=[])  # type: ignore[method-assign]

    assert asyncio.run(tracker.get_additional_checks(make_meta(tmp_path, keywords=["fictional unknown tag"]))) is False  # noqa: S101
    assert asyncio.run(tracker.get_additional_checks(make_meta(tmp_path, keywords=["blowjob"]))) is True  # noqa: S101
    assert asyncio.run(tracker.get_additional_checks(make_meta(tmp_path, keywords=[], answers={"xxx.tags": "blowjob"}))) is True  # noqa: S101


def fake_prompts(monkeypatch, confirmed: bool, selections: list[list[str] | None]) -> list[str]:
    queue = iter(selections)
    questions: list[str] = []

    def ask_yes_no(question, *_args, **_kwargs):
        questions.append(question)
        return confirmed

    def select_choices(question, *_args, **_kwargs):
        questions.append(question)
        return next(queue)

    monkeypatch.setattr("src.manual_input.cli_ui.ask_yes_no", ask_yes_no)
    monkeypatch.setattr("src.manual_input.cli_ui.select_choices", select_choices)
    return questions


def test_confirmed_flags_keep_the_detected_ones(tmp_path: Path, monkeypatch) -> None:
    questions = fake_prompts(monkeypatch, True, [])

    assert asyncio.run(make_tracker().confirm_extras(make_meta(tmp_path, unattended=False))) == ["asian"]  # noqa: S101
    assert "Flags detected: Asian" in questions[0]  # noqa: S101


def test_rejected_flags_are_asked_again_until_valid(tmp_path: Path, monkeypatch) -> None:
    questions = fake_prompts(monkeypatch, False, [["Gay", "Transexual"], ["Censored", "Asian"]])

    assert asyncio.run(make_tracker().confirm_extras(make_meta(tmp_path, unattended=False))) == ["asian", "censored"]  # noqa: S101
    assert len(questions) == 3  # noqa: S101


def test_empty_flag_answer_clears_flags(tmp_path: Path, monkeypatch) -> None:
    fake_prompts(monkeypatch, False, [None])

    assert asyncio.run(make_tracker().confirm_extras(make_meta(tmp_path, unattended=False))) == []  # noqa: S101


def test_unattended_flags_are_not_asked(tmp_path: Path, monkeypatch) -> None:
    questions = fake_prompts(monkeypatch, True, [])

    assert asyncio.run(make_tracker().confirm_extras(make_meta(tmp_path))) == ["asian"]  # noqa: S101
    assert questions == []  # noqa: S101
