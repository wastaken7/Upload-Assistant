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
