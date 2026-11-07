from src import upload_history
from web_ui import server

RECORD = {
    "started_at": "2026-03-01T10:00:00+00:00",
    "finished_at": "2026-03-01T10:05:00+00:00",
    "source": "cli",
    "path": "/media/Fictional.Movie.2020",
    "name": "Fictional Movie 2020",
    "title": "Fictional Movie",
    "year": 2020,
    "category": "MOVIE",
    "release_type": "",
    "resolution": "",
    "release_group": "",
    "season": "",
    "episode": "",
    "size": 0,
    "fingerprint": "",
    "infohash": "",
    "outcome": "success",
    "reason": "",
    "duration_ms": 0,
    "site_check": False,
    "personal_release": False,
    "artwork_url": "",
    "ids": {},
    "trackers": [{"tracker": "FICT", "status": "success", "message": "", "link": "", "torrent_id": "", "duration": None, "dupes": None, "slot": None}],
    "requests": [],
}


def _authenticated(monkeypatch, tmp_path, config=None):
    monkeypatch.setattr(server, "_is_authenticated", lambda: True)
    monkeypatch.setattr(server, "_verify_csrf_header", lambda: True)
    monkeypatch.setattr(server, "_verify_same_origin", lambda: True)
    monkeypatch.setattr(server, "_get_bearer_from_header", lambda: None)
    monkeypatch.setattr(server, "STATE_DIR", tmp_path)
    monkeypatch.setattr(server, "_load_config_from_file", lambda _path: config or {"DEFAULT": {}})
    return server.app.test_client()


def test_history_page_requires_a_session(monkeypatch):
    monkeypatch.setattr(server, "_is_authenticated", lambda: False)
    response = server.app.test_client().get("/history")
    assert response.status_code == 302


def test_history_page_renders_for_authenticated_session(monkeypatch, tmp_path):
    client = _authenticated(monkeypatch, tmp_path)
    response = client.get("/history")
    assert response.status_code == 200
    assert b"history_app.js" in response.data


def test_history_api_lists_entries_with_tracker_names(monkeypatch, tmp_path):
    client = _authenticated(monkeypatch, tmp_path)
    item_id = upload_history.record_item(RECORD, tmp_path)

    response = client.get("/api/history?q=fictional&limit=10")

    assert response.status_code == 200
    assert response.json["enabled"] is True
    assert [item["id"] for item in response.json["items"]] == [item_id]
    assert response.json["tracker_names"] == {"FICT": "FICT"}
    detail = client.get(f"/api/history/{item_id}")
    assert detail.status_code == 200
    assert detail.json["item"]["name"] == "Fictional Movie 2020"


def test_history_api_reports_disabled_recording_and_bad_filters(monkeypatch, tmp_path):
    client = _authenticated(monkeypatch, tmp_path, {"DEFAULT": {"history_enabled": False}})

    assert client.get("/api/history").json["enabled"] is False
    assert client.get("/api/history?outcome=maybe").status_code == 400
    assert client.get("/api/history?limit=lots").status_code == 400


def test_history_api_rejects_tokens_and_cross_site_requests(monkeypatch, tmp_path):
    client = _authenticated(monkeypatch, tmp_path)
    monkeypatch.setattr(server, "_get_bearer_from_header", lambda: "fictional-token")
    assert client.get("/api/history").status_code == 401
    monkeypatch.setattr(server, "_get_bearer_from_header", lambda: None)
    monkeypatch.setattr(server, "_verify_same_origin", lambda: False)
    assert client.delete("/api/history/1").status_code == 403


def test_history_deletions_require_the_csrf_token(monkeypatch, tmp_path):
    client = _authenticated(monkeypatch, tmp_path)
    item_id = upload_history.record_item(RECORD, tmp_path)
    monkeypatch.setattr(server, "_verify_csrf_header", lambda: False)

    assert client.delete(f"/api/history/{item_id}").status_code == 403
    assert client.delete("/api/history", json={"confirmation": "CLEAR"}).status_code == 403
    monkeypatch.setattr(server, "_verify_csrf_header", lambda: True)
    assert client.get(f"/api/history/{item_id}").status_code == 200


def test_history_api_handles_ids_and_offsets_beyond_sqlite_integers(monkeypatch, tmp_path):
    client = _authenticated(monkeypatch, tmp_path)
    upload_history.record_item(RECORD, tmp_path)
    huge = 2**64

    assert client.get(f"/api/history/{huge}").status_code == 404
    assert client.delete(f"/api/history/{huge}").status_code == 404
    page = client.get(f"/api/history?offset={huge}")
    assert page.status_code == 200
    assert page.json["items"] == []
    assert page.json["total"] == 1


def test_history_page_refreshes_the_csrf_token_through_the_shared_helper():
    history_js = (server.CODE_DIR / "web_ui" / "static" / "js" / "history_app.js").read_text(encoding="utf-8")

    assert "window.uaApiFetch(url" in history_js
    assert "UA_CSRF_TOKEN" not in history_js


def test_history_api_deletes_and_clears_with_confirmation(monkeypatch, tmp_path):
    client = _authenticated(monkeypatch, tmp_path)
    first = upload_history.record_item(RECORD, tmp_path)
    upload_history.record_item(RECORD, tmp_path)

    assert client.delete(f"/api/history/{first}").status_code == 200
    assert client.delete(f"/api/history/{first}").status_code == 404
    assert client.get(f"/api/history/{first}").status_code == 404
    assert client.delete("/api/history", json={"confirmation": "clear"}).status_code == 400
    cleared = client.delete("/api/history", json={"confirmation": "CLEAR"})
    assert cleared.json == {"success": True, "removed": 1}


def test_history_api_reports_an_unreadable_database(monkeypatch, tmp_path):
    client = _authenticated(monkeypatch, tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "upload_assistant.sqlite3").write_bytes(b"fictional invalid database")

    response = client.get("/api/history")

    assert response.status_code == 500
    assert response.json["error"] == "Unable to read the upload history"


def test_every_page_links_to_history():
    js_root = server.CODE_DIR / "web_ui" / "static" / "js"
    for script in ("app.js", "config_app.js", "stats_app.js", "history_app.js"):
        assert "/history" in (js_root / script).read_text(encoding="utf-8"), script
    assert 'history: "archive"' in (js_root / "shared_utils.js").read_text(encoding="utf-8")
