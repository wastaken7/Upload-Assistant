# ruff: noqa: S101
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src import prep_helpers
from src.getseasonep import SeasonEpisodeManager
from src.meta import Meta
from src.tmdb import get_anime


def test_unconfirmed_anime_season_pack_uses_standard_season_parsing() -> None:
    manager = SeasonEpisodeManager({"DEFAULT": {"tmdb_api": "test-key"}})
    manager.tmdb_manager.get_romaji = AsyncMock(return_value=("", 0, "", "", 0, "Mina"))
    meta = Meta(
        category="TV",
        anime=True,
        mal_id=0,
        filelist=[],
        filename="Example Show",
        tmdb_id=12345,
    )

    result = asyncio.run(manager.get_season_episode("Example.Show.S03.PAL.DVD.REMUX-GROUP", meta))

    assert result.season == "S03"
    assert result.season_int == 3
    assert result.episode == ""
    assert result.episode_int == 0
    assert result.tv_pack is True
    assert result.demographic == ""


def test_standard_single_episode_parsing_is_preserved() -> None:
    manager = SeasonEpisodeManager({"DEFAULT": {"tmdb_api": "test-key"}})
    meta = Meta(category="TV", anime=False, filelist=["episode.mkv"])

    result = asyncio.run(manager.get_season_episode("Example.Show.S03E04.1080p.WEB-DL-GROUP.mkv", meta))

    assert result.season == "S03"
    assert result.season_int == 3
    assert result.episode == "E04"
    assert result.episode_int == 4
    assert result.tv_pack is False


@pytest.mark.parametrize(
    ("video", "filelist", "episode", "episode_int", "tv_pack"),
    [
        ("Example.Show.S00E01.Special.Episode.1080p.AMZN.WEB-DL.DDP2.0.H.264.mkv", ["episode.mkv"], "E01", 1, False),
        ("Example.Show.2022.S00E01.1080p.WEB-DL-GROUP.mkv", ["episode.mkv"], "E01", 1, False),
        ("Example.Show.S00.1080p.WEB-DL-GROUP", ["episode1.mkv", "episode2.mkv"], "", 0, True),
    ],
)
def test_standard_season_zero_is_preserved(video: str, filelist: list[str], episode: str, episode_int: int, tv_pack: bool) -> None:
    manager = SeasonEpisodeManager({"DEFAULT": {"tmdb_api": "test-key"}})
    meta = Meta(category="TV", anime=False, filelist=filelist)

    with patch("src.getseasonep.logger.info") as log_info:
        result = asyncio.run(manager.get_season_episode(video, meta))

    assert result.season == "S00"
    assert result.season_int == 0
    assert result.episode == episode
    assert result.episode_int == episode_int
    assert result.tv_pack is tv_pack
    assert not any("error guessing the season number" in str(call) for call in log_info.call_args_list)


@pytest.mark.parametrize("season_data", [{}, {"season": None}, {"season": ""}, {"season": "invalid"}])
def test_missing_or_invalid_season_defaults_to_one(season_data: dict[str, object]) -> None:
    manager = SeasonEpisodeManager({"DEFAULT": {"tmdb_api": "test-key"}})
    meta = Meta(category="TV", anime=False, filelist=["episode.mkv"])

    with patch("src.getseasonep.guessit_fn", return_value={"episode": 1, **season_data}):
        result = asyncio.run(manager.get_season_episode("Example.Show.E01.mkv", meta))

    assert result.season == "S01"
    assert result.season_int == 1
    assert result.episode == "E01"
    assert result.episode_int == 1
    assert result.tv_pack is False


def test_not_anime_cli_value_survives_metadata_initialization(tmp_path) -> None:
    prep = SimpleNamespace(config={"DEFAULT": {}})
    meta = Meta(base_dir=str(tmp_path), path=str(tmp_path), not_anime=True)

    prep_helpers.init_meta(prep, meta, "cli")

    assert meta.not_anime is True


def test_unmatched_japanese_animation_has_no_placeholder_demographic() -> None:
    response = {
        "genres": [{"id": 16, "name": "Animation"}],
        "original_language": "en",
        "origin_country": ["JP"],
    }
    meta = Meta(title="Example Show", filename="Example.Show.S03")

    with patch("src.tmdb.get_romaji", new=AsyncMock(return_value=("", 0, "", "", 0, "Mina"))):
        mal_id, alt_name, anime, demographic = asyncio.run(get_anime(response, meta))

    assert mal_id == 0
    assert alt_name == ""
    assert anime is True
    assert demographic == ""
