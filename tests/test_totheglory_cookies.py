import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

import src.trackers.totheglory as ttg_module
from src.trackers.totheglory import ToTheGlory


@pytest.fixture
def site():
    return ToTheGlory({"DEFAULT": {}, "TRACKERS": {"TOTHEGLORY": {}}})


def write_cookies(tmp_path, payload, suffix=".json"):
    path = tmp_path / "data" / "cookies" / f"TOTHEGLORY{suffix}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


@pytest.fixture(params=["browser", "internal"])
def cookie_payload(request):
    data = {"value": "fictional-session", "domain": ".totheglory.im", "path": "/", "secure": True}
    if request.param == "browser":
        return [{"name": "session", **data}]
    return {"session": data}


def mock_http(monkeypatch, handler):
    real_client = httpx.AsyncClient
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(ttg_module.httpx, "AsyncClient", lambda **kwargs: real_client(transport=transport, **kwargs))
    monkeypatch.setattr(ttg_module.asyncio, "sleep", AsyncMock())


def test_cookie_scope_and_metadata(site, tmp_path):
    path = write_cookies(
        tmp_path,
        [
            {"name": "session", "value": "root", "domain": ".totheglory.im", "path": "/", "secure": True, "expirationDate": 4102444800},
            {"name": "session", "value": "upload", "domain": ".totheglory.im", "path": "/upload", "secure": True},
            {"name": "other", "value": "unrelated", "domain": "example.test", "path": "/"},
        ],
    )
    jar = site._load_cookies(str(path))
    assert len(jar) == 3
    root = next(cookie for cookie in jar if cookie.value == "root")
    assert root.secure is True
    assert root.expires == 4102444800
    with httpx.Client(cookies=jar) as client:
        assert client.build_request("GET", "https://totheglory.im/browse.php").headers["cookie"] == "session=root"
        assert client.build_request("GET", "https://totheglory.im/upload/form").headers["cookie"] == "session=upload; session=root"
        assert "cookie" not in client.build_request("GET", "http://totheglory.im/browse.php").headers
        assert "cookie" not in client.build_request("GET", "https://unrelated.test/").headers


@pytest.mark.parametrize("payload", [None, "invalid", ["invalid"], [{}], {"session": "invalid"}])
def test_invalid_cookie_shapes(site, tmp_path, payload):
    path = write_cookies(tmp_path, payload)
    with pytest.raises(ValueError, match="Invalid cookie JSON format"):
        site._load_cookies(str(path))


def test_cookie_file_compatibility(site, tmp_path):
    meta = SimpleNamespace(base_dir=str(tmp_path))
    json_path = tmp_path / "data" / "cookies" / "TOTHEGLORY.json"
    assert site._cookie_file(meta) == str(json_path.resolve())
    legacy = write_cookies(tmp_path, {"session": {"value": "legacy"}}, suffix=".pkl")
    assert site._cookie_file(meta) == str(legacy.resolve())
    assert next(iter(site._load_cookies(str(legacy)))).value == "legacy"
    write_cookies(tmp_path, {"session": {"value": "new"}})
    assert site._cookie_file(meta) == str(json_path.resolve())


def test_legacy_file_is_read_as_json_only(site, tmp_path):
    path = write_cookies(tmp_path, {}, suffix=".pkl")
    path.write_bytes(b"\x80\x04not-json")
    with pytest.raises((UnicodeDecodeError, json.JSONDecodeError)):
        site._load_cookies(str(path))


@pytest.mark.parametrize("suffix", [".json", ".pkl"])
def test_validation_and_search_use_exported_cookies(site, tmp_path, cookie_payload, monkeypatch, suffix):
    write_cookies(tmp_path, cookie_payload, suffix=suffix)
    requests = []

    def handler(request):
        requests.append(request)
        assert request.headers["cookie"] == "session=fictional-session"
        if request.url.path == "/":
            return httpx.Response(200, text='<a href="/logout.php">Logout</a>')
        return httpx.Response(200, text='<a href="/t/123"><b>Fictional.Release<br></b></a>')

    mock_http(monkeypatch, handler)
    site.login = AsyncMock()
    meta = SimpleNamespace(base_dir=str(tmp_path), imdb_id="", is_disc="", resolution="1080p")
    assert asyncio.run(site.validate_credentials(meta)) is True
    site.login.assert_not_awaited()
    assert asyncio.run(site.search_existing(meta)) == ["Fictional.Release"]
    assert [request.url.path for request in requests] == ["/", "/browse.php"]


def test_upload_uses_exported_cookies(site, tmp_path, cookie_payload, monkeypatch):
    write_cookies(tmp_path, cookie_payload)
    work_dir = tmp_path / "tmp" / "test"
    work_dir.mkdir(parents=True)
    (work_dir / "[TOTHEGLORY]DESCRIPTION.txt").write_text("Fictional description", encoding="utf-8")
    (work_dir / "MEDIAINFO.txt").write_text("Fictional media info", encoding="utf-8")
    torrent = work_dir / "[TOTHEGLORY].torrent"
    torrent.write_bytes(b"fictional-torrent")
    common = SimpleNamespace(create_torrent_for_upload=AsyncMock())
    monkeypatch.setattr(ttg_module, "Common", lambda **kwargs: common)
    site.edit_desc = AsyncMock()
    site.get_name = AsyncMock(return_value="Fictional.Release")
    site.get_type_id = AsyncMock(return_value=53)
    site.download_new_torrent = AsyncMock()
    requests = []

    def handler(request):
        requests.append(request)
        assert request.headers["cookie"] == "session=fictional-session"
        assert request.method == "POST"
        assert b"fictional-torrent" in request.content
        return httpx.Response(302, headers={"location": "https://totheglory.im/details.php?id=123"})

    def redirect_handler(request):
        if request.url.path == "/takeupload.php":
            return handler(request)
        return httpx.Response(200)

    mock_http(monkeypatch, redirect_handler)
    meta = SimpleNamespace(
        base_dir=str(tmp_path),
        uuid="test",
        anon=0,
        bdinfo=None,
        filelist=["Fictional.Release.mkv"],
        video="Fictional.Release.mkv",
        imdb_tt="",
        debug=False,
        tracker_status={},
    )
    assert asyncio.run(site.upload(meta)) is True
    assert len(requests) == 1
    site.download_new_torrent.assert_awaited_once()
    torrent_id, downloaded_path = site.download_new_torrent.await_args.args
    assert torrent_id == "123"
    assert Path(downloaded_path) == torrent
    assert meta.tracker_status[site.tracker]["status_message"] == "https://totheglory.im/details.php?id=123"


def test_login_creates_the_file_used_by_other_operations(site, tmp_path, monkeypatch):
    meta = SimpleNamespace(base_dir=str(tmp_path))
    cookiefile = Path(site._cookie_file(meta))
    cookiefile.parent.mkdir(parents=True)

    def handler(request):
        if request.url.path == "/takelogin.php":
            return httpx.Response(302, headers={"location": "/my.php", "set-cookie": "session=logged-in; Path=/; Secure"})
        return httpx.Response(200)

    mock_http(monkeypatch, handler)
    asyncio.run(site.login(str(cookiefile), meta))
    assert cookiefile.suffix == ".json"
    assert next(iter(site._load_cookies(site._cookie_file(meta)))).value == "logged-in"
