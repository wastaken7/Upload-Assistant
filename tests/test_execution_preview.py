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
