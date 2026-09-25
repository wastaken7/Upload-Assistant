from pathlib import Path

import pytest

from web_ui import server
from web_ui.server import _extract_execution_preview


@pytest.mark.parametrize("category", ["MOVIE", "TV"])
@pytest.mark.parametrize(
    "metadata, expected",
    [
        ({"imdb_id": 98764, "imdb_tt": "tt0098764", "imdb": "0098764"}, "tt0098764"),
        ({"imdb_id": 98764}, "tt0098764"),
        ({"imdb_id": "0098764"}, "tt0098764"),
        ({"imdb_tt": "tt0098764"}, "tt0098764"),
        ({"imdb": "0098764"}, "tt0098764"),
        ({"imdb_id": 0, "imdb_tt": "tt0098764"}, "tt0098764"),
        ({"imdb_id": 12345678}, "tt12345678"),
        ({"imdb_tt": "tt12345678"}, "tt12345678"),
        ({"imdb_id": 98764, "imdb_tt": "tt0111161"}, "tt0098764"),
        ({"imdb_id": None, "imdb": "  tt0098764  "}, "tt0098764"),
    ],
)
def test_execution_preview_preserves_imdb_title_ids(metadata, expected, category):
    original = dict(metadata)
    preview = _extract_execution_preview({"category": category, **metadata}, "sample.mkv")
    source = next(source for source in preview["metadata_sources"] if source["key"] == "imdb")

    assert preview["imdb"] == expected
    assert source["value"] == expected
    assert source["url"] == f"https://www.imdb.com/title/{expected}/"
    assert metadata == original


@pytest.mark.parametrize("value", [None, "", 0, "0000000", "tt0000000", -1, True, "not-an-id"])
def test_execution_preview_omits_missing_or_invalid_imdb_links(value):
    preview = _extract_execution_preview({"category": "MOVIE", "imdb_id": value}, "sample.mkv")

    assert preview["imdb"] == ""
    assert all(source["key"] != "imdb" for source in preview["metadata_sources"])


@pytest.mark.parametrize(
    ("game_url", "expected_url"),
    [
        ("https://www.igdb.com/games/example-adventure", "https://www.igdb.com/games/example-adventure"),
        ("", "https://www.igdb.com/search?type=1&q=285744"),
        ("javascript:alert(1)", "https://www.igdb.com/search?type=1&q=285744"),
    ],
)
def test_execution_preview_links_igdb_id_to_game_url(game_url, expected_url):
    preview = _extract_execution_preview(
        {"category": "GAME", "igdb_id": 285744, "igdb_url": game_url},
        "example-game",
    )

    source = next(source for source in preview["metadata_sources"] if source["key"] == "igdb")
    assert source["value"] == "285744"  # noqa: S101
    assert source["url"] == expected_url  # noqa: S101


def _detail_items(preview, section_key):
    section = next(section for section in preview["detail_sections"] if section["key"] == section_key)
    return {item["key"]: item["value"] for item in section["items"]}


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


@pytest.mark.parametrize(
    ("category", "metadata", "section_key", "expected"),
    [
        (
            "MOVIE",
            {
                "release_date": "2026-08-14",
                "directors": ["Director One"],
                "studios": [{"name": "Studio One"}],
                "cast": ["Actor One", "Actor Two"],
            },
            "movie",
            {"release_date": "2026-08-14", "directors": "Director One", "studios": "Studio One", "cast": "Actor One, Actor Two"},
        ),
        (
            "TV",
            {
                "season": "S02",
                "episode": "E04",
                "episode_title": "The Test",
                "tv_pack": False,
                "networks": [{"name": "Example Network"}],
            },
            "tv",
            {"episode": "S02E04 — The Test", "package": "Single Episode", "networks": "Example Network"},
        ),
        (
            "BOOK",
            {
                "author": "Writer",
                "book_translator": "Translator",
                "book_series": "Series",
                "book_series_index": "3",
                "service_longname": "Storytel",
                "isbn": "9781234567890",
                "audiobook": True,
            },
            "book",
            {"author": "Writer", "translator": "Translator", "series": "Series #3", "service": "Storytel", "isbn": "9781234567890", "format": "Audiobook"},
        ),
        (
            "MUSIC",
            {
                "music_release": {
                    "fields": {
                        "artists": {"value": ["Artist"]},
                        "album": {"value": "Album"},
                        "release_type": {"value": "Album"},
                        "track_count": {"value": 10},
                        "disc_count": {"value": 2},
                    },
                    "tracks": [],
                }
            },
            "music",
            {"artist": "Artist", "album": "Album", "release_type": "Album", "tracks_discs": "10 / 2"},
        ),
        (
            "GAME",
            {
                "platform": "Windows",
                "game_version": "1.2",
                "game_engines": ["Example Engine"],
                "game_modes": ["Single player"],
                "game_age_ratings": {"ESRB": "M"},
            },
            "game",
            {"platform": "Windows", "version": "1.2", "engines": "Example Engine", "modes": "Single player", "age_ratings": "ESRB: M"},
        ),
        (
            "XXX",
            {"publisher": "Studio", "release_date": "2026-08-21", "cast": ["Performer One"]},
            "xxx",
            {"publisher": "Studio", "release_date": "2026-08-21", "performers": "Performer One"},
        ),
    ],
)
def test_execution_preview_builds_curated_category_details(category, metadata, section_key, expected):
    preview = _extract_execution_preview(
        {
            "category": category,
            "title": "Example",
            "type": "WEBDL",
            "source_size": 1_572_864,
            "filelist": ["one", "two"],
            **metadata,
        },
        "C:/media/Example",
    )

    assert [section["key"] for section in preview["detail_sections"]] == ["media", section_key]  # noqa: S101
    assert _detail_items(preview, "media") == {"type": "WEBDL", "size": "1.5 MiB", "files": "2"}  # noqa: S101
    assert expected.items() <= _detail_items(preview, section_key).items()  # noqa: S101


def test_execution_preview_omits_empty_and_zero_media_details():
    preview = _extract_execution_preview({"category": "MOVIE", "title": "Example", "source_size": 0, "filelist": []}, "C:/media/Example")

    assert preview["detail_sections"] == []  # noqa: S101


def test_book_preview_uses_service_when_longname_is_unavailable():
    preview = _extract_execution_preview({"category": "BOOK", "service": "Skeelo"}, "book.epub")

    assert preview["service"] == "Skeelo"  # noqa: S101
    assert _detail_items(preview, "book")["service"] == "Skeelo"  # noqa: S101


@pytest.mark.parametrize(
    ("audible_url", "expected_url"),
    [
        ("https://www.audible.com/pd/example/B0TEST1234", "https://www.audible.com/pd/example/B0TEST1234"),
        ("", None),
        ("javascript:alert(1)", None),
    ],
)
def test_book_preview_exposes_safe_audible_asin_link(audible_url, expected_url):
    preview = _extract_execution_preview(
        {"category": "BOOK", "title": "Example", "asin": "B0TEST1234", "audible_url": audible_url},
        "C:/media/Example",
    )

    audible = next(source for source in preview["metadata_sources"] if source["key"] == "audible")
    assert audible["value"] == "B0TEST1234"  # noqa: S101
    assert audible.get("url") == expected_url  # noqa: S101


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
