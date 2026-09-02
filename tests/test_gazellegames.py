import asyncio
from typing import ClassVar
from unittest.mock import AsyncMock, Mock

import httpx

from src.gazellegames import GazelleGamesManager, gazellegames_manager
from src.meta import Meta
from src.prep_game import apply_gazelle_metadata, apply_igdb_extended_metadata, gather_game_prep, select_gazelle_candidate


def _cache_config(tmp_path, *, enabled=True):
    return {
        "DEFAULT": {
            "metadata_cache_enabled": enabled,
            "metadata_cache_dir": str(tmp_path / "cache"),
            "metadata_cache_services": {"gazellegames": {"ttl_hours": 24}},
        }
    }


def test_extracts_only_canonical_gazellegames_torrent_urls():
    comments = [
        {"comment": "https://example.com/torrents.php?torrentid=1"},
        {"comment": "Source: https://gazellegames.net/torrents.php?torrentid=46720"},
    ]

    assert GazelleGamesManager.extract_torrent_id(comments) == "46720"  # noqa: S101
    assert GazelleGamesManager.extract_torrent_id([{"comment": "https://gazellegames.net/forums.php?torrentid=42"}]) is None  # noqa: S101
    assert GazelleGamesManager.extract_torrent_id([{"comment": "https://notgazellegames.net/torrents.php?torrentid=42"}]) is None  # noqa: S101


def test_normalizes_group_and_exact_torrent_metadata():
    payload = {
        "group": {
            "name": "The Troma Project",
            "year": 2015,
            "platform": "Windows",
            "Artists": [{"name": "Linux"}],
            "wikiBody": "<p>A strategy game.</p>",
            "TagList": "turn.based comedy",
            "tags": ["controller.support"],
            "rating": "M",
            "trailer": "[inlineurl]https://www.youtube.com/watch?v=abc123[/inlineurl]",
            "metaRating": {"score": "81", "link": "https%3A%2F%2Fexample.com%2Freview"},
            "weblinks": {
                "Steam": "[inlineurl]https%3A%2F%2Fstore.steampowered.com%2Fapp%2F279640%2F[/inlineurl]",
                "GamesWebsite": "https://example.com/game",
            },
            "specialCollections": {
                "Developer": [{"Name": "Studio One"}, {"Name": "Studio Two"}],
                "Publisher": [{"Name": "Publisher"}],
                "Designer": [{"Name": "Designer"}],
                "Composer": [{"Name": "Composer"}],
                "Engine": [{"Name": "Engine"}],
                "Feature": [{"Name": "Controller Support"}],
                "Franchise": [{"Name": "Series"}],
            },
        },
        "torrent": {
            "releaseType": "Full ISO",
            "gameDOXType": "",
            "gameDOXVersion": "1.2a",
            "language": "English",
            "region": "World",
            "remastered": True,
            "remasterYear": 2020,
            "remasterTitle": "Definitive Edition",
            "scene": True,
            "releaseTitle": "Game.Definitive-SCENE",
            "bbDescription": "[b]Nothing[/b] ripped.<br>Includes DLC.",
        },
    }

    metadata = GazelleGamesManager.normalize_metadata(payload, exact_torrent=True)

    assert metadata["title"] == "The Troma Project"  # noqa: S101
    assert metadata["platform"] == "Windows"  # noqa: S101
    assert metadata["available_platforms"] == ["Windows", "Linux"]  # noqa: S101
    assert metadata["genres"] == ["Turn Based", "Comedy"]  # noqa: S101
    assert metadata["keywords"] == ["Controller Support"]  # noqa: S101
    assert metadata["developer"] == "Studio One, Studio Two"  # noqa: S101
    assert metadata["publisher"] == "Publisher"  # noqa: S101
    assert metadata["steam_url"] == "https://store.steampowered.com/app/279640/"  # noqa: S101
    assert metadata["game_age_ratings"] == {"ESRB": "M"}  # noqa: S101
    assert metadata["game_ratings"]["Metacritic"] == {"score": 81.0, "max": 100, "url": "https://example.com/review"}  # noqa: S101
    assert metadata["game_official_url"] == "https://example.com/game"  # noqa: S101
    assert metadata["youtube"] == "https://www.youtube.com/watch?v=abc123"  # noqa: S101
    assert metadata["game_engines"] == ["Engine"]  # noqa: S101
    assert metadata["game_franchises"] == ["Series"]  # noqa: S101
    assert metadata["game_version"] == "1.2a"  # noqa: S101
    assert metadata["game_subcategory"] == "full_game"  # noqa: S101
    assert metadata["languages"] == {"English": []}  # noqa: S101
    assert metadata["game_region"] == "World"  # noqa: S101
    assert metadata["game_release_edition"] == "Definitive Edition"  # noqa: S101
    assert metadata["game_release_edition_year"] == 2020  # noqa: S101
    assert metadata["game_release_scene"] is True  # noqa: S101
    assert metadata["game_release_notes"] == "Nothing ripped.\nIncludes DLC."  # noqa: S101
    assert "artwork_url" not in metadata  # noqa: S101
    assert "image_list" not in metadata  # noqa: S101


def test_maps_only_supported_gamedox_subcategories():
    base = {"group": {"name": "Game"}}
    dlc = GazelleGamesManager.normalize_metadata({**base, "torrent": {"releaseType": "GameDOX", "gameDOXType": "DLC"}}, exact_torrent=True)
    update = GazelleGamesManager.normalize_metadata({**base, "torrent": {"releaseType": "GameDOX", "gameDOXType": "Update", "gameDOXVersion": "Unknown"}}, exact_torrent=True)
    trainer = GazelleGamesManager.normalize_metadata({**base, "torrent": {"releaseType": "GameDOX", "gameDOXType": "Trainer"}}, exact_torrent=True)

    assert dlc["game_subcategory"] == "dlc"  # noqa: S101
    assert update["game_subcategory"] == "update"  # noqa: S101
    assert "game_version" not in update  # noqa: S101
    assert "game_subcategory" not in trainer  # noqa: S101


def test_title_only_gazelle_metadata_omits_release_specific_fields():
    payload = {
        "group": {"name": "Game", "gameInfo": {"rating": "16+", "trailer": "https://www.youtube.com/watch?v=abc"}},
        "torrent": {"region": "Europe", "releaseTitle": "Game-SCENE", "bbDescription": "Release notes"},
    }

    metadata = GazelleGamesManager.normalize_metadata(payload, exact_torrent=False)

    assert metadata["game_age_ratings"] == {"PEGI": "16"}  # noqa: S101
    assert metadata["youtube"].endswith("abc")  # noqa: S101
    assert "game_region" not in metadata  # noqa: S101
    assert "game_release_notes" not in metadata  # noqa: S101


def test_ignores_zero_or_invalid_group_years():
    assert "year" not in GazelleGamesManager.normalize_metadata({"name": "Game", "year": "0"}, exact_torrent=False)  # noqa: S101
    assert "year" not in GazelleGamesManager.normalize_metadata({"name": "Game", "year": "unknown"}, exact_torrent=False)  # noqa: S101


def test_fetch_torrent_enriches_with_group_and_reuses_cache(tmp_path, monkeypatch):
    manager = GazelleGamesManager()
    request = AsyncMock(
        side_effect=[
            {"group": {"id": 21390, "name": "Basic"}, "torrent": {"id": 46720}},
            {"group": {"id": 21390, "name": "Detailed", "specialCollections": {}}},
        ]
    )
    monkeypatch.setattr(manager, "_request", request)
    config = _cache_config(tmp_path)

    first = asyncio.run(manager.fetch_torrent("46720", base_dir=str(tmp_path), api_key="secret", config=config))
    second = asyncio.run(manager.fetch_torrent("46720", base_dir=str(tmp_path), api_key="secret", config=config))

    assert first == second  # noqa: S101
    assert first["group"]["name"] == "Detailed"  # type: ignore[index]  # noqa: S101
    assert request.await_count == 2  # noqa: S101


def test_transient_group_failure_is_not_negative_cached(tmp_path, monkeypatch):
    manager = GazelleGamesManager()
    request = AsyncMock(return_value=None)
    monkeypatch.setattr(manager, "_request", request)
    config = _cache_config(tmp_path)

    assert asyncio.run(manager.fetch_group("21390", base_dir=str(tmp_path), api_key="secret", config=config)) is None  # noqa: S101
    assert asyncio.run(manager.fetch_group("21390", base_dir=str(tmp_path), api_key="secret", config=config)) is None  # noqa: S101
    assert request.await_count == 2  # noqa: S101


def test_search_filters_non_game_results(tmp_path, monkeypatch):
    manager = GazelleGamesManager()
    monkeypatch.setattr(
        manager,
        "_request",
        AsyncMock(return_value={"1": {"ID": "1", "Name": "Game", "CategoryID": "1"}, "2": {"ID": "2", "Name": "Book", "CategoryID": "3"}}),
    )

    results = asyncio.run(manager.search_groups("Game", base_dir=str(tmp_path), api_key="secret", config=_cache_config(tmp_path, enabled=False)))

    assert [result["ID"] for result in results] == ["1"]  # noqa: S101


def test_request_handles_rejected_and_malformed_responses(monkeypatch):
    class FakeClient:
        responses: ClassVar[list[httpx.Response]] = [
            httpx.Response(403),
            httpx.Response(200, json={"status": "success", "response": []}),
            httpx.Response(200, json={"status": "success", "response": "invalid"}),
        ]

        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, *_args, **_kwargs):
            return self.responses.pop(0)

    manager = GazelleGamesManager()
    monkeypatch.setattr("src.gazellegames.httpx.AsyncClient", FakeClient)
    monkeypatch.setattr(manager, "_wait_for_rate_slot", AsyncMock())

    assert asyncio.run(manager._request({"request": "torrent"}, "secret")) is None  # noqa: S101
    assert asyncio.run(manager._request({"request": "torrent"}, "secret")) == {}  # noqa: S101
    assert asyncio.run(manager._request({"request": "torrent"}, "secret")) is None  # noqa: S101


def test_rate_limiter_waits_after_five_requests(monkeypatch):
    manager = GazelleGamesManager()
    manager._request_times.extend([100.0] * 5)
    times = iter([100.0, 111.0])
    sleep = AsyncMock()
    monkeypatch.setattr("src.gazellegames._monotonic", lambda: next(times))
    monkeypatch.setattr("src.gazellegames.asyncio.sleep", sleep)

    asyncio.run(manager._wait_for_rate_slot())

    sleep.assert_awaited_once_with(10.0)
    assert list(manager._request_times) == [111.0]  # noqa: S101


def test_unattended_selection_requires_one_nonconflicting_exact_match():
    meta = Meta(unattended=True, year=2015, platform="PC")
    exact = {"ID": "1", "Name": "The Troma Project", "Year": "2015", "Artists": [{"name": "Windows"}]}
    wrong_year = {"ID": "2", "Name": "The Troma Project", "Year": "2024", "Artists": [{"name": "Windows"}]}

    assert select_gazelle_candidate([wrong_year, exact], "The Troma Project", meta) == exact  # noqa: S101
    assert select_gazelle_candidate([exact, {**exact, "ID": "3"}], "The Troma Project", meta) is None  # noqa: S101


def test_attended_selection_prompts_for_ambiguous_matches(monkeypatch):
    meta = Meta(unattended=False, year=2015, platform="PC")
    candidates = [
        {"ID": "1", "Name": "Game", "Year": "2015", "Artists": [{"name": "Windows"}]},
        {"ID": "2", "Name": "Game", "Year": "2015", "Artists": [{"name": "Linux"}]},
    ]
    monkeypatch.setattr("src.prep_game.cli_ui.ask_choice", lambda _prompt, choices: choices[1])

    assert select_gazelle_candidate(candidates, "Game", meta)["ID"] == "2"  # type: ignore[index]  # noqa: S101


def test_attended_selection_prompts_for_one_fuzzy_match(monkeypatch):
    meta = Meta(unattended=False)
    candidate = {"ID": "1", "Name": "A Different Game", "Year": "2015", "Artists": [{"name": "Windows"}]}
    ask = Mock(return_value="Skip - Don't use a GazelleGames match")
    monkeypatch.setattr("src.prep_game.cli_ui.ask_choice", ask)

    assert select_gazelle_candidate([candidate], "Game", meta) is None  # noqa: S101
    ask.assert_called_once()


def test_apply_preserves_manual_game_fields():
    meta = Meta(title="Manual", manual_year=2024, year=2024, manual_platform="PS5", platform="PS5", game_version="v9", game_subcategory="dlc")
    metadata = {
        "title": "GGN",
        "year": 2015,
        "search_year": 2015,
        "platform": "Windows",
        "game_version": "1.2",
        "game_subcategory": "full_game",
        "overview": "GGN overview",
    }

    applied = apply_gazelle_metadata(meta, metadata, {"title": True, "year": True, "platform": True, "version": True, "subcategory": True})

    assert (meta.title, meta.year, meta.platform, meta.game_version, meta.game_subcategory) == ("Manual", 2024, "PS5", "v9", "dlc")  # noqa: S101
    assert meta.overview == "GGN overview"  # noqa: S101
    assert applied == {"overview"}  # noqa: S101


def test_apply_preserves_explicit_steam_id():
    meta = Meta(steam_manual="123")

    applied = apply_gazelle_metadata(meta, {"steam_url": "https://store.steampowered.com/app/456/"}, {"steam": True})

    assert meta.steam_url is None  # noqa: S101
    assert "steam_url" not in applied  # noqa: S101


def test_merges_rich_igdb_metadata_without_replacing_gazelle_values():
    meta = Meta(game_engines=["GGN Engine"], game_age_ratings={"ESRB": "M"}, game_ratings={"Metacritic": {"score": 90, "max": 100}})
    game = {
        "alternative_names": [{"name": "Alternate"}],
        "age_ratings": [{"organization": {"name": "ESRB"}, "rating_category": {"rating": "T"}}, {"organization": {"name": "PEGI"}, "rating_category": {"rating": "18"}}],
        "rating": 85.5,
        "rating_count": 123,
        "aggregated_rating": 80,
        "aggregated_rating_count": 10,
        "franchises": [{"name": "Franchise"}],
        "collections": [{"name": "Series"}],
        "game_engines": [{"name": "IGDB Engine"}],
        "game_modes": [{"name": "Single player"}, {"name": "Multiplayer"}],
        "player_perspectives": [{"name": "Third person"}],
        "themes": [{"name": "Fantasy"}],
        "keywords": [{"name": "Dragons"}],
        "multiplayer_modes": [{"platform": {"name": "PC"}, "onlinecoop": True, "onlinecoopmax": 4, "splitscreen": True}],
        "release_dates": [{"human": "Nov 11, 2011", "platform": {"name": "PC"}, "release_region": {"region": "Worldwide"}}],
        "parent_game": {"name": "Base Game"},
        "game_type": {"type": "Expanded Game"},
        "game_status": {"status": "Released"},
        "version_title": "Gold Edition",
        "websites": [{"type": 1, "url": "https://example.com"}],
        "videos": [{"name": "Launch Trailer", "video_id": "abc123"}],
    }

    apply_igdb_extended_metadata(meta, game)

    assert meta.game_engines == ["GGN Engine", "IGDB Engine"]  # noqa: S101
    assert meta.game_age_ratings == {"ESRB": "M", "PEGI": "18"}  # noqa: S101
    assert set(meta.game_ratings) == {"Metacritic", "IGDB Users", "IGDB Critics"}  # noqa: S101
    assert meta.game_multiplayer_modes["PC"] == ["Online co-op (up to 4)", "Split-screen"]  # noqa: S101
    assert meta.game_release_dates == [{"date": "Nov 11, 2011", "platform": "PC", "region": "Worldwide"}]  # noqa: S101
    assert meta.game_franchises == ["Franchise", "Series"]  # noqa: S101
    assert meta.game_official_url == "https://example.com"  # noqa: S101
    assert meta.youtube == "https://www.youtube.com/watch?v=abc123"  # noqa: S101


def test_gazelle_enrichment_works_without_twitch_credentials(tmp_path, monkeypatch):
    payload = {
        "group": {
            "name": "The Troma Project",
            "year": 2015,
            "platform": "Windows",
            "wikiBody": "GGN overview",
            "tags": ["strategy"],
            "weblinks": {"Steam": "https://store.steampowered.com/app/279640/"},
        },
        "torrent": {"releaseType": "Full ISO", "language": "English"},
    }
    monkeypatch.setattr(gazellegames_manager, "fetch_torrent", AsyncMock(return_value=payload))
    monkeypatch.setattr(gazellegames_manager, "search_groups", AsyncMock())

    class FakeSteamClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, *_args, **_kwargs):
            data = {
                "279640": {
                    "success": True,
                    "data": {
                        "short_description": "<b>Descrição Steam</b>",
                        "pc_requirements": {"minimum": "Minimum specs", "recommended": "Recommended specs"},
                    },
                }
            }
            return type("Response", (), {"status_code": 200, "json": lambda _self: data})()

    monkeypatch.setattr("src.prep_game.httpx.AsyncClient", FakeSteamClient)
    meta = Meta(
        path=str(tmp_path / "The.Troma.Project-HI2U"),
        filename="The Troma Project",
        filelist=[],
        torrent_comments=[{"comment": "https://gazellegames.net/torrents.php?torrentid=46720"}],
        unattended=True,
        trackers=["BJSHARE"],
    )
    config = {"DEFAULT": {"ggn_api_key": "secret", "metadata_cache_enabled": False}}

    asyncio.run(gather_game_prep(meta, str(meta.path), str(tmp_path), config))

    assert meta.title == "The Troma Project"  # noqa: S101
    assert meta.year == 2015  # noqa: S101
    assert meta.platform == "PC"  # noqa: S101
    assert meta.overview == "GGN overview"  # noqa: S101
    assert meta.game_subcategory == "full_game"  # noqa: S101
    assert meta.languages == {"English": []}  # noqa: S101
    assert meta.requirements_minimum == "Minimum specs"  # noqa: S101
    assert meta.requirements_recommended == "Recommended specs"  # noqa: S101
    assert meta.localized_overviews == {"brazilian": "Descrição Steam"}  # noqa: S101
    gazellegames_manager.search_groups.assert_not_awaited()  # type: ignore[attr-defined]


def test_exact_comment_lookup_does_not_require_a_search_title(tmp_path, monkeypatch):
    payload = {"group": {"name": "Comment Match", "year": 2000, "platform": "Windows"}, "torrent": {"releaseType": "Full ISO"}}
    monkeypatch.setattr(gazellegames_manager, "fetch_torrent", AsyncMock(return_value=payload))
    search = AsyncMock()
    monkeypatch.setattr(gazellegames_manager, "search_groups", search)
    meta = Meta(filelist=[], torrent_comments=[{"comment": "https://gazellegames.net/torrents.php?torrentid=46720"}], unattended=True)

    asyncio.run(gather_game_prep(meta, "", str(tmp_path), {"DEFAULT": {"ggn_api_key": "secret"}}))

    assert (meta.title, meta.year, meta.platform) == ("Comment Match", 2000, "PC")  # noqa: S101
    search.assert_not_awaited()


def test_title_fallback_fetches_selected_gazelle_group(tmp_path, monkeypatch):
    candidate = {"ID": "21390", "Name": "The Troma Project", "Year": "2015", "Artists": [{"name": "Windows"}], "CategoryID": "1"}
    group = {"id": 21390, "name": "The Troma Project", "year": 2015, "platform": "Windows", "wikiBody": "Group overview"}
    search = AsyncMock(return_value=[candidate])
    fetch_group = AsyncMock(return_value=group)
    monkeypatch.setattr(gazellegames_manager, "search_groups", search)
    monkeypatch.setattr(gazellegames_manager, "fetch_group", fetch_group)
    meta = Meta(path=str(tmp_path / "The.Troma.Project-HI2U"), filename="The Troma Project", filelist=[], unattended=True, skip_auto_torrent=True)

    asyncio.run(gather_game_prep(meta, str(meta.path), str(tmp_path), {"DEFAULT": {"ggn_api_key": "secret"}}))

    assert (meta.title, meta.year, meta.platform, meta.overview) == ("The Troma Project", 2015, "PC", "Group overview")  # noqa: S101
    search.assert_awaited_once()
    fetch_group.assert_awaited_once_with("21390", base_dir=str(tmp_path), api_key="secret", config={"DEFAULT": {"ggn_api_key": "secret"}})


def test_ambiguous_unattended_gazelle_search_falls_back_to_igdb(tmp_path, monkeypatch):
    candidates = [
        {"ID": "1", "Name": "Game", "Year": "2015", "Artists": [{"name": "Windows"}], "CategoryID": "1"},
        {"ID": "2", "Name": "Game", "Year": "2015", "Artists": [{"name": "Windows"}], "CategoryID": "1"},
    ]
    fetch_group = AsyncMock()
    monkeypatch.setattr(gazellegames_manager, "search_groups", AsyncMock(return_value=candidates))
    monkeypatch.setattr(gazellegames_manager, "fetch_group", fetch_group)

    class FakeIGDB:
        def __init__(self, *_args):
            pass

        async def fetch_game_by_id(self, _game_id):
            return None

        async def fetch_game_by_steam_id(self, _steam_id):
            return None

        async def search_game(self, title):
            assert title == "Game"  # noqa: S101
            return [{"id": 7, "name": "IGDB Game", "summary": "IGDB overview"}]

        async def cache_game_details(self, _game):
            return None

        async def fetch_time_to_beat(self, _game_id):
            return {}

    monkeypatch.setattr("src.prep_game.IGDBAPI", FakeIGDB)
    meta = Meta(path=str(tmp_path / "Game"), filename="Game", filelist=[], unattended=True, skip_auto_torrent=True)
    config = {"DEFAULT": {"ggn_api_key": "secret", "twitch_client_id": "id", "twitch_client_secret": "secret"}}

    asyncio.run(gather_game_prep(meta, str(meta.path), str(tmp_path), config))

    fetch_group.assert_not_awaited()
    assert (meta.title, meta.overview, meta.igdb_id) == ("IGDB Game", "IGDB overview", 7)  # noqa: S101


def test_igdb_search_hydrates_selected_game_and_time_to_beat(tmp_path, monkeypatch):
    class FakeIGDB:
        def __init__(self, *_args):
            pass

        async def search_game(self, _title):
            return [{"id": 7, "name": "Game", "platforms": [{"name": "PC (Microsoft Windows)"}]}]

        async def fetch_game_by_id(self, game_id):
            assert game_id == "7"  # noqa: S101
            return {"id": 7, "name": "Game", "summary": "Detailed overview", "game_modes": [{"name": "Single player"}], "platforms": [{"name": "PC (Microsoft Windows)"}]}

        async def fetch_game_by_steam_id(self, _steam_id):
            return None

        async def cache_game_details(self, _game):
            return None

        async def fetch_time_to_beat(self, game_id):
            assert game_id == 7  # noqa: S101
            return {"hastily": 3600}

    monkeypatch.setattr("src.prep_game.IGDBAPI", FakeIGDB)
    meta = Meta(path=str(tmp_path / "Game"), filename="Game", filelist=[], unattended=True, skip_auto_torrent=True)
    config = {"DEFAULT": {"twitch_client_id": "id", "twitch_client_secret": "secret"}}

    asyncio.run(gather_game_prep(meta, str(meta.path), str(tmp_path), config))

    assert meta.overview == "Detailed overview"  # noqa: S101
    assert meta.game_modes == ["Single player"]  # noqa: S101
    assert meta.game_time_to_beat == {"hastily": 3600}  # noqa: S101


def test_igdb_fills_missing_artwork_without_overwriting_gazelle(tmp_path, monkeypatch):
    payload = {
        "group": {
            "name": "GGN Name",
            "year": 2015,
            "platform": "Windows",
            "wikiBody": "GGN overview",
            "tags": ["strategy"],
            "weblinks": {"Steam": "https://store.steampowered.com/app/279640/"},
            "specialCollections": {"Developer": [{"Name": "GGN Dev"}], "Publisher": [{"Name": "GGN Pub"}]},
        },
        "torrent": {"releaseType": "Full ISO", "language": "English"},
    }
    monkeypatch.setattr(gazellegames_manager, "fetch_torrent", AsyncMock(return_value=payload))

    class FakeIGDB:
        def __init__(self, *_args):
            pass

        async def fetch_game_by_id(self, _game_id):
            return None

        async def fetch_game_by_steam_id(self, steam_id):
            assert steam_id == "279640"  # noqa: S101
            return {
                "id": 99,
                "name": "IGDB Name",
                "first_release_date": 1577836800,
                "summary": "IGDB overview",
                "cover": {"url": "//images.igdb.com/t_thumb/cover.jpg"},
                "genres": [{"name": "Action"}],
                "platforms": [{"name": "PC (Microsoft Windows)"}],
                "involved_companies": [{"developer": True, "publisher": True, "company": {"name": "IGDB Company"}}],
                "language_supports": [{"language": {"name": "German"}, "language_support_type": {"name": "Subtitles"}}],
                "screenshots": [{"url": "//images.igdb.com/t_thumb/screen.jpg"}],
                "rating": 88.1,
                "rating_count": 10,
            }

        async def search_game(self, _title):
            return []

        async def cache_game_details(self, _game):
            return None

        async def fetch_time_to_beat(self, _game_id):
            return {}

    class FakeHttpClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, *_args, **_kwargs):
            return type("Response", (), {"status_code": 404})()

    monkeypatch.setattr("src.prep_game.IGDBAPI", FakeIGDB)
    monkeypatch.setattr("src.prep_game.httpx.AsyncClient", FakeHttpClient)
    meta = Meta(
        path=str(tmp_path / "Game"),
        filename="Game",
        filelist=[],
        torrent_comments=[{"comment": "https://gazellegames.net/torrents.php?torrentid=46720"}],
        unattended=True,
        uuid="game",
    )
    config = {"DEFAULT": {"ggn_api_key": "secret", "twitch_client_id": "id", "twitch_client_secret": "secret", "metadata_cache_enabled": False}}

    asyncio.run(gather_game_prep(meta, str(meta.path), str(tmp_path), config))

    assert (meta.title, meta.year, meta.platform) == ("GGN Name", 2015, "PC")  # noqa: S101
    assert (meta.overview, meta.developer, meta.publisher) == ("GGN overview", "GGN Dev", "GGN Pub")  # noqa: S101
    assert meta.genres == ["Action"]  # noqa: S101
    assert meta.keywords == ["Strategy"]  # noqa: S101
    assert meta.languages == {"English": []}  # noqa: S101
    assert meta.steam_url == "https://store.steampowered.com/app/279640/"  # noqa: S101
    assert meta.artwork_url == "https://images.igdb.com/t_cover_big/cover.jpg"  # noqa: S101
    assert meta.image_list[0]["raw_url"] == "https://images.igdb.com/t_1080p/screen.jpg"  # noqa: S101
    assert meta.igdb_rating == 88.1  # noqa: S101


def test_missing_gazelle_credentials_preserves_existing_no_igdb_behavior(tmp_path, monkeypatch):
    fetch = AsyncMock()
    monkeypatch.setattr(gazellegames_manager, "fetch_torrent", fetch)
    meta = Meta(path=str(tmp_path / "Game"), filename="Game", filelist=[], unattended=True)

    asyncio.run(gather_game_prep(meta, str(meta.path), str(tmp_path), {"DEFAULT": {}}))

    fetch.assert_not_awaited()
    assert meta.title == ""  # noqa: S101
