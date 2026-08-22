from pathlib import Path

from web_ui import server
from web_ui.server import _extract_execution_preview


def test_execution_preview_uses_current_movie_tmdb_artwork_field():
    preview = _extract_execution_preview(
        {
            "category": "MOVIE",
            "title": "Example Movie",
            "tmdb_poster_path": "/movie-poster.jpg",
        },
        "C:/media/Example Movie",
    )

    assert preview["poster_url"] == "https://image.tmdb.org/t/p/w500/movie-poster.jpg"  # noqa: S101


def test_execution_preview_prefers_current_tv_artwork_url():
    preview = _extract_execution_preview(
        {
            "category": "TV",
            "title": "Example Show",
            "artwork_url": "https://images.example/show-poster.jpg",
            "tmdb_poster_path": "/fallback-poster.jpg",
            "poster": "https://legacy.example/poster.jpg",
        },
        "C:/media/Example Show",
    )

    assert preview["poster_url"] == "https://images.example/show-poster.jpg"  # noqa: S101


def test_execution_preview_uses_local_cover_for_active_session(tmp_path, monkeypatch):
    cover = tmp_path / "POSTER.png"
    cover.write_bytes(b"png")
    monkeypatch.setattr("web_ui.server._find_execution_preview_cover_file", lambda session_id: cover if session_id == "session-1" else None)

    preview = _extract_execution_preview({"uuid": "release-1", "category": "XXX"}, str(tmp_path), "session-1")

    assert preview["poster_url"].startswith("/api/execution_preview_cover?session_id=session-1&v=release-1%3A")  # noqa: S101
    assert preview["media_id"] == "release-1"  # noqa: S101


def test_cover_regeneration_rejects_a_preview_that_has_moved(monkeypatch):
    monkeypatch.setattr(server, "_webui_auth_ok", lambda: True)
    monkeypatch.setattr(server, "_verify_csrf_header", lambda: True)
    monkeypatch.setattr(server, "_verify_same_origin", lambda: True)
    monkeypatch.setattr(
        server,
        "_resolve_execution_preview_meta",
        lambda _session_id: ("C:/media/second", Path("meta.json"), {"uuid": "second", "category": "XXX"}),
    )

    response = server.app.test_client().post(
        "/api/execution_preview_cover/regenerate",
        json={"session_id": "session-1", "media_id": "first"},
    )

    assert response.status_code == 409  # noqa: S101


def test_cover_regeneration_uses_execution_path_name_when_uuid_is_missing(monkeypatch):
    captured = {}

    async def fake_fallback_cover(_paths, folder_id, _base_dir, _meta, random_frame=False):
        captured["folder_id"] = folder_id
        captured["random_frame"] = random_frame
        return "POSTER.png"

    monkeypatch.setattr(server, "_webui_auth_ok", lambda: True)
    monkeypatch.setattr(server, "_verify_csrf_header", lambda: True)
    monkeypatch.setattr(server, "_verify_same_origin", lambda: True)
    monkeypatch.setattr(
        server,
        "_resolve_execution_preview_meta",
        lambda _session_id: ("C:/media/release-folder", Path("meta.json"), {"base_dir": "C:/state", "category": "XXX", "filelist": []}),
    )
    monkeypatch.setattr("src.takescreens.xxx_fallback_cover", fake_fallback_cover)
    monkeypatch.setattr(server, "_execution_preview_cover_cache_key", lambda _session_id, fallback: fallback)

    response = server.app.test_client().post(
        "/api/execution_preview_cover/regenerate",
        json={"session_id": "session-1", "media_id": "C:/media/release-folder"},
    )

    assert response.status_code == 200  # noqa: S101
    assert captured == {"folder_id": "release-folder", "random_frame": True}  # noqa: S101
