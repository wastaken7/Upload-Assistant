# ruff: noqa: S101
import asyncio
import json
import runpy
from pathlib import Path
from typing import Any

import httpx
import pytest

from src.meta import Meta
from src.trackers.GAZELLE import simurg as simurg_module
from src.trackers.GAZELLE.simurg import Answers, Simurg
from src.trackersetup import STATIC_AUTH_TYPES, TrackerSetup, tracker_class_map

CONFIG: dict[str, Any] = {
    "DEFAULT": {},
    "TRACKERS": {"SIMURG": {"api_key": "test-token", "announce_url": "https://tracker.example.invalid/key/announce"}},
}


@pytest.fixture(autouse=True)
def no_pacing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Simurg, "min_request_interval", 0.0)
    monkeypatch.setattr(Simurg, "rate_limit_pause", 0.0)


def _book(tmp_path: Path, name: str = "Fictional Author - The Glass Orchard.epub", **values: Any) -> Meta:
    path = tmp_path / name
    path.write_bytes(b"fictional")
    defaults: dict[str, Any] = {
        "category": "BOOK",
        "title": "The Glass Orchard",
        "author": "Fictional Author",
        "year": 2019,
        "book_language": "English",
        "publisher": "Imaginary Press",
        "isbn": "978-0-00-000000-2",
        "overview": "<p>A fictional synopsis that is long enough.</p>",
        "genres": ["Fiction / Fantasy", "EPUB"],
        "path": str(path),
        "filelist": [str(path)],
        "base_dir": str(tmp_path),
        "uuid": "fictional",
        "trackers": ["SIMURG"],
        "unattended": True,
        "ua_name": "Upload Assistant",
        "current_version": "1.0",
    }
    defaults.update(values)
    meta = Meta(**defaults)
    meta.tracker_status = {"SIMURG": {}}
    return meta


def _mock_client(monkeypatch: pytest.MonkeyPatch, handler: Any) -> list[httpx.Request]:
    requests: list[httpx.Request] = []
    real_client = httpx.AsyncClient

    def recording_handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return handler(request)

    def factory(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = httpx.MockTransport(recording_handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(simurg_module.httpx, "AsyncClient", factory)
    return requests


def _ok(response: Any) -> httpx.Response:
    return httpx.Response(200, json={"status": "success", "response": response})


BROWSE: dict[str, Any] = {
    "results": [
        {
            "groupId": 11,
            "groupName": "The Glass Orchard",
            "artist": "Fictional Author",
            "groupYear": 2019,
            "category": "E-Books",
            "torrents": [{"torrentId": 21, "format": "PDF", "encoding": "Scan", "fileCount": 1, "size": 1000}],
        },
        {"groupId": "12", "groupName": "The Glass Orchard", "torrentId": 22, "category": "E-Books", "size": 2000, "fileCount": 1},
        {"groupId": 13, "groupName": "The Glass Orchard", "category": "Audiobooks", "torrents": [{"torrentId": 23, "format": "M4B", "encoding": "64"}]},
    ]
}


def test_registration_and_config() -> None:
    example_config = runpy.run_path(str(Path(__file__).resolve().parents[1] / "data" / "example_config.py"))["config"]
    assert tracker_class_map["SIMURG"] is Simurg
    assert STATIC_AUTH_TYPES["SIMURG"] == "other_api"
    assert example_config["TRACKERS"]["SIMURG"]["cli_alias"] == "SMG"


@pytest.mark.parametrize(("category", "kept"), [("BOOK", True), ("MOVIE", False), ("MUSIC", False)])
def test_supported_categories(category: str, kept: bool) -> None:
    meta = Meta(category=category, trackers=["SIMURG"])
    TrackerSetup(CONFIG).filter_unsupported_trackers(meta)
    assert (meta.trackers == ["SIMURG"]) is kept


@pytest.mark.parametrize(
    ("name", "values", "kind", "format_name"),
    [
        ("Book.epub", {}, "ebook", "EPUB"),
        ("Book.djvu", {}, "ebook", "DJVU"),
        ("Comic 001.cbz", {}, "comic", "CBZ"),
        ("Volume 1.pdf", {"manga": True}, "comic", "PDF"),
        ("Chapter 01.m4b", {"audiobook": True}, "audiobook", "M4B"),
        ("Chapter 01.m4a", {"audiobook": True}, "audiobook", "Other"),
    ],
)
def test_kind_and_format(tmp_path: Path, name: str, values: dict[str, Any], kind: str, format_name: str) -> None:
    meta = _book(tmp_path, name, **values)
    tracker = Simurg(CONFIG)
    assert tracker._kind(meta) == kind
    assert tracker._format(meta, kind) == (format_name, "")


def test_problems_explain_what_simurg_refuses(tmp_path: Path) -> None:
    tracker = Simurg(CONFIG)
    docx = _book(tmp_path, "Book.docx", book_language="Portuguese", author="")
    problems = tracker._problems(docx)
    assert any("accept only EPUB, PDF, MOBI, AZW3, DJVU" in problem for problem in problems)
    assert any("language 'Portuguese'" in problem for problem in problems)
    assert any("author is required" in problem for problem in problems)

    second = tmp_path / "Book.pdf"
    second.write_bytes(b"x")
    mixed = _book(tmp_path)
    mixed.filelist = [*mixed.filelist, str(second)]
    assert any("single format" in problem for problem in tracker._problems(mixed))

    assert "Magazine" in tracker._problems(_book(tmp_path, magazine=True))[0]
    assert tracker._problems(_book(tmp_path)) == []


def test_tags_drop_format_words_and_use_dotted_form(tmp_path: Path) -> None:
    meta = _book(tmp_path, genres=["Fiction / Science Fiction", "EPUB", "Retail"], keywords=["Action & Adventure", "fiction"])
    assert Simurg(CONFIG)._tags(meta) == ["fiction", "science.fiction", "action.and.adventure"]


@pytest.mark.parametrize(
    ("credit", "names"),
    [("Fictional Author", ["Fictional Author"]), ("Author, Fictional", ["Author, Fictional"]), ("Ann Example & Bo Sample", ["Ann Example", "Bo Sample"])],
)
def test_contributor_names(credit: str, names: list[str]) -> None:
    assert Simurg._names(credit) == names


def test_search_existing_lists_torrents_of_the_same_category(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "token test-token"
        action = request.url.params["action"]
        if action == "browse":
            assert request.url.params["searchstr"] == "The Glass Orchard"
            return _ok(BROWSE)
        assert action == "torrentgroup"
        group_id = request.url.params["id"]
        files = "Fictional Author - The Glass Orchard.epub{{{2000}}}"
        torrents: list[dict[str, Any]] = [{"id": 22, "format": "EPUB", "encoding": "Retail", "fileList": files, "size": 2000, "fileCount": 1}] if group_id == "12" else []
        return _ok({"group": {"id": int(group_id), "year": 2019}, "torrents": torrents})

    requests = _mock_client(monkeypatch, handler)
    dupes = asyncio.run(Simurg(CONFIG).search_existing(_book(tmp_path)))

    # The audiobook Release is a different category; the first group falls back to its browse torrents.
    assert [request.url.params["action"] for request in requests] == ["browse", "torrentgroup", "torrentgroup"]
    assert [(dupe["id"], dupe["type"]) for dupe in dupes] == [(21, "pdf"), (22, "epub")]
    assert dupes[1]["files"] == ["Fictional Author - The Glass Orchard.epub"]
    assert dupes[1]["link"] == "https://simurg.world/torrents.php?id=12&torrentid=22"
    assert dupes[0]["name"].startswith("The Glass Orchard by Fictional Author [2019]")


def test_search_error_is_raised_for_the_dupe_review(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_client(monkeypatch, lambda _request: httpx.Response(200, json={"status": "failure", "error": "invalid token"}))
    with pytest.raises(RuntimeError, match="invalid token"):
        asyncio.run(Simurg(CONFIG).search_existing(_book(tmp_path)))


def test_rate_limit_is_retried_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    replies = iter([httpx.Response(200, json={"status": "failure", "error": "Rate limit exceeded"}), _ok({"results": []})])
    requests = _mock_client(monkeypatch, lambda _request: next(replies))
    assert asyncio.run(Simurg(CONFIG).search_existing(_book(tmp_path))) == []
    assert len(requests) == 2


def test_new_publication_payload(tmp_path: Path) -> None:
    meta = _book(tmp_path, book_translator="Tran Slator")
    data = Simurg(CONFIG).build_upload_payload(meta, Answers(source="Retail"))

    assert data["type"] == 2
    assert data["format"] == "EPUB"
    assert data["bitrate"] == "Retail"
    assert data["language"] == "English"
    assert data["book_title"] == data["title"] == "The Glass Orchard"
    assert data["year"] == "2019"
    assert data["artists[]"] == ["Fictional Author", "Tran Slator"]
    assert data["importance[]"] == [1, 3]
    assert data["tags"] == "fiction, fantasy"
    assert data["catalogue_number"] == "9780000000002"
    assert data["record_label"] == "Imaginary Press"
    assert "A fictional synopsis" in data["book_desc"]
    assert "<p>" not in data["book_desc"]
    assert "Format: EPUB" in data["release_desc"]
    assert "publicationid" not in data
    assert Simurg._missing_fields(data) == []


def test_existing_publication_and_release_payloads(tmp_path: Path) -> None:
    tracker = Simurg(CONFIG)
    meta = _book(tmp_path)
    existing = tracker.build_upload_payload(meta, Answers(source="Retail", publication_id="77"))
    assert existing["publicationid"] == "77"
    assert "book_title" not in existing
    assert "book_desc" not in existing

    another_format = tracker.build_upload_payload(meta, Answers(source="Retail", group_id="12"))
    assert another_format["groupid"] == "12"
    assert set(another_format) == {"type", "format", "bitrate", "release_desc", "groupid"}


def test_missing_synopsis_and_tags_block_a_new_publication(tmp_path: Path) -> None:
    data = Simurg(CONFIG).build_upload_payload(_book(tmp_path, overview="", genres=[]), Answers(source="Retail"))
    missing = Simurg._missing_fields(data)
    assert any("--genres" in item for item in missing)
    assert any("--overview" in item for item in missing)


def test_audiobook_payload(tmp_path: Path) -> None:
    meta = _book(
        tmp_path,
        "Chapter 01.mp3",
        audiobook=True,
        narrator="Nara Tor",
        audiobook_duration=3 * 3600 + 25 * 60 + 10,
        audiobook_bitrate=127,
        edition="Unabridged",
    )
    meta.mediainfo = {"media": {"track": [{"@type": "General"}, {"@type": "Audio", "Format": "MPEG Audio"}]}}
    data = Simurg(CONFIG).build_upload_payload(meta, Answers(source="WEB", audiobook_type="Unabridged"))

    assert data["type"] == 3
    assert (data["format"], data["bitrate"], data["media"], data["audio_codec"]) == ("MP3", "128", "WEB", "MP3")
    assert (data["duration_hours"], data["duration_minutes"]) == (3, 25)
    assert data["audiobook_type"] == "Unabridged"
    assert data["artists[]"] == ["Fictional Author", "Nara Tor"]
    assert data["importance[]"] == [1, 5]
    assert "page_count" not in data


def test_uncommon_audio_bitrate_is_sent_as_other(tmp_path: Path) -> None:
    meta = _book(tmp_path, "Chapter 01.m4b", audiobook=True, audiobook_bitrate=110)
    assert Simurg(CONFIG)._audio_bitrate(meta, "M4B") == ("Other", "110 kbps")


def test_cover_never_hotlinks_a_source_tracker(tmp_path: Path) -> None:
    tracker = Simurg(CONFIG)
    assert tracker._cover_url(_book(tmp_path, artwork_url="https://cdn.myanonamouse.net/covers/1.jpg")) == ""
    hosted = _book(tmp_path, artwork_url="https://cdn.myanonamouse.net/covers/1.jpg", hosted_artwork=[{"raw_url": "https://images.example.invalid/c.jpg"}])
    assert tracker._cover_url(hosted) == "https://images.example.invalid/c.jpg"


def _upload_handler(posted: list[httpx.Request], suggestions: list[dict[str, Any]]) -> Any:
    def handler(request: httpx.Request) -> httpx.Response:
        action = request.url.params["action"]
        if action == "publication_autocomplete":
            return httpx.Response(200, json={"query": request.url.params["query"], "suggestions": suggestions})
        if action == "browse":
            return _ok({"results": []})
        if action == "upload":
            posted.append(request)
            return _ok({"groupId": 31, "torrentId": 41, "private": True, "source": True, "warnings": []})
        raise AssertionError(f"unexpected {request.url}")

    return handler


def test_unattended_upload_reuses_the_matching_publication(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    suggestions: list[dict[str, Any]] = [
        {"data": 501, "value": "Series 2: The Glass Orchard — Fictional Author", "canonical_title": "Series 2: The Glass Orchard", "authors": "Fictional Author"},
        {"data": 502, "value": "The Glass Orchard Companion — Someone Else", "canonical_title": "The Glass Orchard Companion", "authors": "Someone Else"},
    ]
    posted: list[httpx.Request] = []
    _mock_client(monkeypatch, _upload_handler(posted, suggestions))

    async def fake_torrent(meta: Meta, *_args: Any, **_kwargs: Any) -> None:
        folder = Path(meta.base_dir) / "tmp" / meta.uuid
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "[SIMURG].torrent").write_bytes(b"d4:infod4:name4:testee")

    downloads: list[dict[str, Any]] = []

    async def fake_download(_meta: Meta, _tracker: str, **kwargs: Any) -> str:
        downloads.append(kwargs)
        return "downloaded"

    tracker = Simurg(CONFIG)
    monkeypatch.setattr(tracker.common, "create_torrent_for_upload", fake_torrent)
    monkeypatch.setattr(tracker.common, "download_tracker_torrent", fake_download)
    meta = _book(tmp_path, answers={"simurg.source": "Retail"})

    assert asyncio.run(tracker.upload(meta)) is True
    assert len(posted) == 1
    body = posted[0].content.decode("utf-8", "replace")
    assert 'name="publicationid"\r\n\r\n501' in body
    assert 'name="book_title"' not in body
    assert body.count('name="artists[]"') == 1
    assert 'name="file_input"; filename="[SIMURG].torrent"' in body
    status = meta.tracker_status["SIMURG"]
    assert (status["torrent_id"], status["group_id"], status["torrent_source"]) == (41, 31, "site")
    assert downloads[0]["params"] == {"action": "download", "id": "41"}


def test_unattended_upload_skips_when_the_publication_is_unclear(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    suggestions: list[dict[str, Any]] = [{"data": 601, "value": "The Glass Orchard — Other Writer", "canonical_title": "The Glass Orchard", "authors": "Other Writer"}]
    posted: list[httpx.Request] = []
    _mock_client(monkeypatch, _upload_handler(posted, suggestions))
    meta = _book(tmp_path, answers={"simurg.source": "Retail"})

    assert asyncio.run(Simurg(CONFIG).upload(meta)) is False
    assert posted == []
    assert "Publication" in meta.tracker_status["SIMURG"]["status_message"]


def test_debug_upload_prepares_the_payload_without_posting(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    posted: list[httpx.Request] = []
    _mock_client(monkeypatch, _upload_handler(posted, []))
    meta = _book(tmp_path, debug=True, answers={"simurg.source": "Scan"})

    assert asyncio.run(Simurg(CONFIG).upload(meta)) is True
    assert posted == []
    payload = meta.tracker_status["SIMURG"]["debug_payload"]
    assert payload["bitrate"] == "Scan"
    assert payload["book_title"] == "The Glass Orchard"
    json.dumps(payload)


def test_source_is_never_guessed_unattended(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    requests = _mock_client(monkeypatch, _upload_handler([], []))
    meta = _book(tmp_path, debug=True)

    assert asyncio.run(Simurg(CONFIG).upload(meta)) is False
    assert requests == []


def test_rejected_upload_reports_the_site_error(tmp_path: Path) -> None:
    meta = _book(tmp_path)
    assert Simurg(CONFIG)._record_upload_response(meta, {"status": "failure", "error": "Invalid format"}) is False
    assert meta.tracker_status["SIMURG"]["status_message"] == "Simurg rejected the upload: Invalid format"


def test_changed_torrent_is_not_seeded_from_the_local_copy(tmp_path: Path) -> None:
    tracker = Simurg(CONFIG)
    meta = _book(tmp_path)
    assert tracker._record_upload_response(meta, _ok({"groupId": 1, "torrentId": 2, "private": True, "source": False}).json()) is True
    asyncio.run(tracker._write_torrent_comment(meta))
    assert "download it from https://simurg.world/torrents.php?id=1&torrentid=2" in meta.tracker_status["SIMURG"]["status_message"]
