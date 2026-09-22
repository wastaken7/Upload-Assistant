# ruff: noqa: S101
from unittest.mock import AsyncMock

import pytest

from src.args import Args
from src.book_prep import gather_book_prep
from src.meta import Meta
from src.prep_game import apply_gazelle_metadata, gather_game_prep


def test_book_cli_narrator_and_genres_override_metadata(tmp_path):
    meta, _, _ = Args({"DEFAULT": {"screens": 1}}).parse([str(tmp_path), "--book-narrator", "Jane Reader", "--genres", "Fantasy, Science Fiction"], Meta(category="BOOK"))

    assert meta.book_narrator == meta.narrator == "Jane Reader"
    assert meta.manual_genres == "Fantasy, Science Fiction"
    assert meta.genres == ["Fantasy", "Science Fiction"]


def test_game_cli_uses_publisher_and_new_overrides(tmp_path):
    meta, _, _ = Args({"DEFAULT": {"screens": 1}}).parse(
        [
            str(tmp_path),
            "--game-title",
            "Manual Game",
            "--developer",
            "Manual Studio",
            "--publisher",
            "Manual Publisher",
            "--overview",
            "Manual overview",
            "--genres",
            "Action, RPG",
        ],
        Meta(category="GAME"),
    )

    assert (meta.game_title, meta.title) == ("Manual Game", "Manual Game")
    assert (meta.game_developer, meta.developer) == ("Manual Studio", "Manual Studio")
    assert (meta.book_publisher, meta.publisher) == ("Manual Publisher", "Manual Publisher")
    assert (meta.manual_overview, meta.overview) == ("Manual overview", "Manual overview")
    assert meta.genres == ["Action", "RPG"]


@pytest.mark.asyncio
async def test_book_cli_values_win_over_mam_google_books_and_openlibrary(tmp_path, monkeypatch):
    from src.google_books import google_books_manager
    from src.myanonamouse import myanonamouse_manager
    from src.openlibrary import openlibrary_manager

    monkeypatch.setattr(myanonamouse_manager, "search_by_id", AsyncMock(return_value={"narrator": "MAM Reader", "genres": ["MAM Genre"]}))
    monkeypatch.setattr(google_books_manager, "search_by_isbn", AsyncMock(return_value={"genres": ["Google Genre"]}))
    monkeypatch.setattr(openlibrary_manager, "search_by_work_id", AsyncMock(return_value={"genres": ["OpenLibrary Genre"]}))

    meta = Meta(
        book_narrator="Manual Reader",
        manual_genres="Fantasy, Science Fiction",
        isbn="9781234567890",
        openlibrary="OL123W",
        torrent_comments=[{"trackers": "https://www.myanonamouse.net", "comment": "MID=123"}],
        edit=True,
    )
    await gather_book_prep(meta, "book.m4b", str(tmp_path), {"DEFAULT": {"mam_api_key": "test", "google_books_api_key": "test"}})

    assert meta.narrator == "Manual Reader"
    assert meta.genres == ["Fantasy", "Science Fiction"]


def test_game_cli_values_win_over_gazelle_metadata():
    meta = Meta(title="Manual Game", developer="Manual Studio", publisher="Manual Publisher", overview="Manual overview")
    applied = apply_gazelle_metadata(
        meta,
        {"title": "GGN Game", "developer": "GGN Studio", "publisher": "GGN Publisher", "overview": "GGN overview"},
        {"title": True, "developer": True, "publisher": True, "overview": True},
    )

    assert (meta.title, meta.developer, meta.publisher, meta.overview) == ("Manual Game", "Manual Studio", "Manual Publisher", "Manual overview")
    assert not applied


@pytest.mark.asyncio
async def test_game_cli_values_win_over_igdb(tmp_path, monkeypatch):
    class FakeIGDB:
        def __init__(self, *_args):
            pass

        async def fetch_game_by_id(self, _game_id):
            return {
                "id": 1,
                "name": "IGDB Game",
                "summary": "IGDB overview",
                "involved_companies": [
                    {"developer": True, "publisher": True, "company": {"name": "IGDB Company"}},
                ],
            }

        async def cache_game_details(self, _game):
            return None

        async def fetch_time_to_beat(self, _game_id):
            return {}

    monkeypatch.setattr("src.prep_game.IGDBAPI", FakeIGDB)
    monkeypatch.setattr("src.prep_game.detect_platform_from_files", AsyncMock(return_value=None))

    meta = Meta(
        game_title="Manual Game",
        game_developer="Manual Studio",
        book_publisher="Manual Publisher",
        manual_overview="Manual overview",
        manual_genres="Action, RPG",
        igdb_manual="1",
        filelist=[],
        path=str(tmp_path / "game"),
    )
    await gather_game_prep(meta, str(meta.path), str(tmp_path), {"DEFAULT": {"twitch_client_id": "id", "twitch_client_secret": "secret"}})

    assert (meta.title, meta.developer, meta.publisher, meta.overview) == ("Manual Game", "Manual Studio", "Manual Publisher", "Manual overview")
    assert meta.genres == ["Action", "RPG"]
