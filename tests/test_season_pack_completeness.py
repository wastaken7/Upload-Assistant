# ruff: noqa: S101
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src import getseasonep, prep_helpers
from src.getseasonep import SeasonEpisodeManager
from src.meta import Meta
from src.trackers.UNIT3D import UNIT3D
from src.trackers.UNIT3D.rockethd import RocketHD


def _meta(episodes, **kwargs):
    return Meta(
        category="TV", tv_pack=True, season="S03", season_int=3,
        filelist=[f"Car.S.O.S.S03E{episode:02d}.NORDiC.1080p.DSNP.WEB-DL.H.264-Group.mkv" for episode in episodes],
        **kwargs,
    )


@pytest.fixture
def manager(monkeypatch):
    result = SeasonEpisodeManager({"DEFAULT": {"tmdb_api": "test-key"}})
    result.tvdb_handler.get_season_episode_numbers = AsyncMock(return_value=list(range(1, 11)))
    monkeypatch.setattr(getseasonep, "get_tag", AsyncMock(return_value="-Group"))
    return result


@pytest.mark.parametrize("episodes,missing", [
    (range(2, 11), [(3, 1)]),
    ([1, 2, 4], [(3, 3)]),
    (range(5, 8), [(3, 1), (3, 2), (3, 3), (3, 4)]),
    ([0], [(3, 1)]),
    (range(1, 11), []),
])
def test_local_numbering_requires_episode_one_and_continuity(manager, episodes, missing):
    result = asyncio.run(manager.check_season_pack_detail(_meta(episodes)))
    assert result["missing_episodes"] == missing
    assert result["complete"] is (not missing)
    manager.tvdb_handler.get_season_episode_numbers.assert_not_awaited()


def test_original_car_sos_pack_reports_missing_first_episode(manager):
    meta = _meta(range(2, 11), tvdb_id=123)
    meta.filelist.append("Car.S.O.S.S03.NORDiC.1080p.DSNP.WEB-DL.H.264-Group.nfo")
    result = asyncio.run(manager.check_season_pack_detail(meta))
    assert result["complete"] is False
    assert result["missing_episodes"] == [(3, 1)]
    assert result["tvdb_episode_counts"] == {3: (9, 10)}


def test_tvdb_detects_missing_final_episode(manager):
    result = asyncio.run(manager.check_season_pack_detail(_meta(range(1, 10), tvdb_id=123)))
    assert result["complete"] is False
    assert result["missing_episodes"] == [(3, 10)]
    manager.tvdb_handler.get_season_episode_numbers.assert_awaited_once_with(123, 3)


def test_duplicate_files_do_not_hide_missing_episode(manager):
    result = asyncio.run(manager.check_season_pack_detail(_meta([*range(1, 10), 9], tvdb_id=123)))
    assert result["tvdb_episode_counts"] == {3: (9, 10)}
    assert result["missing_episodes"] == [(3, 10)]


def test_multi_episode_file_counts_both_episodes(manager):
    meta = _meta(range(3, 11), tvdb_id=123)
    meta.filelist.append("Car.S.O.S.S03E01E02.mkv")
    result = asyncio.run(manager.check_season_pack_detail(meta))
    assert result["complete"] is True
    assert result["tvdb_episode_counts"] == {3: (10, 10)}


def test_tvdb_extra_episodes_warn_even_with_no_local_gaps(manager):
    manager.tvdb_handler.get_season_episode_numbers.return_value = list(range(1, 10))
    result = asyncio.run(manager.check_season_pack_detail(_meta(range(1, 11), tvdb_id=123)))
    assert result["complete"] is False
    assert result["missing_episodes"] == []
    assert result["unexpected_episodes"] == [(3, 10)]


def test_equal_counts_with_different_numbers_are_not_complete(manager):
    manager.tvdb_handler.get_season_episode_numbers.return_value = [*range(1, 10), 11]
    result = asyncio.run(manager.check_season_pack_detail(_meta(range(1, 11), tvdb_id=123)))
    assert result["complete"] is False
    assert result["missing_episodes"] == [(3, 11)]
    assert result["unexpected_episodes"] == [(3, 10)]


def test_each_season_is_compared_separately(manager):
    manager.tvdb_handler.get_season_episode_numbers.side_effect = [[1, 2], [1, 2, 3]]
    meta = _meta([1, 2], tvdb_id=123)
    meta.filelist += ["Show.S02E02.mkv"]
    result = asyncio.run(manager.check_season_pack_detail(meta))
    assert result["missing_episodes"] == [(2, 1), (3, 3)]
    assert result["tvdb_episode_counts"] == {2: (1, 2), 3: (2, 3)}


@pytest.mark.parametrize("response,marked", [("y", True), ("yes", True), ("n", False), ("no", False)])
def test_user_decides_whether_to_mark_pack(manager, monkeypatch, response, marked):
    prompt = AsyncMock(return_value=response)
    monkeypatch.setattr(getseasonep, "prompt_in_thread", prompt)
    meta = _meta(range(2, 11), tvdb_id=123)
    asyncio.run(manager.check_season_pack_completeness(meta))
    assert meta.season_pack_incomplete is marked
    assert meta.season == "S03"
    assert meta.season_int == 3
    prompt.assert_awaited_once()


@pytest.mark.parametrize("response", ["q", "", None, " \t ", "invalid"])
def test_quit_or_default_aborts(manager, monkeypatch, response):
    monkeypatch.setattr(getseasonep, "prompt_in_thread", AsyncMock(return_value=response))
    with pytest.raises(SystemExit):
        asyncio.run(manager.check_season_pack_completeness(_meta([2])))


def test_filelist_continue_still_requires_incomplete_confirmation(manager, monkeypatch):
    prompt = AsyncMock(side_effect=["c", "n"])
    monkeypatch.setattr(getseasonep, "prompt_in_thread", prompt)
    meta = _meta(range(2, 22))
    asyncio.run(manager.check_season_pack_completeness(meta))
    assert prompt.await_count == 2
    assert meta.season_pack_incomplete is False


@pytest.mark.parametrize("confirm,marked", [(False, False), (True, True)])
def test_unattended_mode_respects_confirmation_flag(manager, monkeypatch, confirm, marked):
    prompt = AsyncMock(return_value="y")
    monkeypatch.setattr(getseasonep, "prompt_in_thread", prompt)
    meta = _meta([2], unattended=True, unattended_confirm=confirm)
    asyncio.run(manager.check_season_pack_completeness(meta))
    assert meta.season_pack_incomplete is marked
    assert prompt.await_count == int(confirm)


def test_tvdb_failure_warns_but_preserves_local_check(manager, monkeypatch):
    manager.tvdb_handler.get_season_episode_numbers.return_value = None
    prompt = AsyncMock(return_value="n")
    monkeypatch.setattr(getseasonep, "prompt_in_thread", prompt)
    warnings = []
    monkeypatch.setattr(getseasonep.logger, "warning", warnings.append)
    asyncio.run(manager.check_season_pack_completeness(_meta(range(1, 11), tvdb_id=123)))
    assert any("Could not verify S03 against TVDB" in message for message in warnings)
    prompt.assert_not_awaited()
    result = asyncio.run(manager.check_season_pack_detail(_meta([2, 4], tvdb_id=123)))
    assert result["complete"] is False
    assert result["missing_episodes"] == [(3, 1), (3, 3)]


def test_complete_pack_clears_old_marker_and_does_not_prompt(manager, monkeypatch):
    prompt = AsyncMock()
    monkeypatch.setattr(getseasonep, "prompt_in_thread", prompt)
    meta = _meta(range(1, 11), tvdb_id=123, season_pack_incomplete=True)
    asyncio.run(manager.check_season_pack_completeness(meta))
    assert meta.season_pack_incomplete is False
    prompt.assert_not_awaited()


def test_non_pack_does_not_fetch_tvdb(manager):
    meta = _meta([1], tvdb_id=123)
    meta.tv_pack = False
    assert asyncio.run(manager.check_season_pack_detail(meta))["complete"] is True
    manager.tvdb_handler.get_season_episode_numbers.assert_not_awaited()


@pytest.mark.parametrize("release_type", ["WEBDL", "WEBRIP", "ENCODE", "HDTV", "REMUX", "DISC", "DVDRIP"])
def test_confirmed_marker_is_added_only_to_supporting_tracker(manager, monkeypatch, release_type):
    monkeypatch.setattr(getseasonep, "prompt_in_thread", AsyncMock(return_value="y"))
    meta = _meta([2], title="Car S.O.S.", type=release_type, resolution="1080p", language_checked=True, name="Car S.O.S. S03 1080p WEB-DL")
    asyncio.run(manager.check_season_pack_completeness(meta))
    tracker = RocketHD({"TRACKERS": {"ROCKETHD": {}}})
    name = asyncio.run(tracker.get_name(meta))["name"]
    assert "S03 INCOMPLETE " in name
    assert name.count("INCOMPLETE") == 1
    other = UNIT3D({"TRACKERS": {"EXAMPLE": {}}}, "EXAMPLE")
    assert asyncio.run(other.get_name(meta))["name"] == meta.name
    assert meta.season == "S03"


def test_rejected_mismatch_does_not_mark_rockethd(manager, monkeypatch):
    monkeypatch.setattr(getseasonep, "prompt_in_thread", AsyncMock(return_value="n"))
    meta = _meta([2], title="Car S.O.S.", type="WEBDL", language_checked=True)
    asyncio.run(manager.check_season_pack_completeness(meta))
    tracker = RocketHD({"TRACKERS": {"ROCKETHD": {}}})
    assert "INCOMPLETE" not in asyncio.run(tracker.get_name(meta))["name"]


def test_completeness_runs_after_final_tvdb_lookup(monkeypatch):
    class StopAfterCheck(Exception):
        pass

    async def find_tvdb(**kwargs):
        return [], 123

    async def check(meta):
        assert meta.tvdb_id == 123
        raise StopAfterCheck

    prep = SimpleNamespace(
        config={"DEFAULT": {}},
        tvdb_handler=SimpleNamespace(search_tvdb_series=AsyncMock(side_effect=find_tvdb)),
        metadata_searching_manager=SimpleNamespace(get_tv_data=AsyncMock(side_effect=lambda meta: meta)),
        season_episode_manager=SimpleNamespace(check_season_pack_completeness=AsyncMock(side_effect=check)),
    )
    meta = _meta([2], not_anime=True, tvdb_id=0, tvmaze_id=123)
    with pytest.raises(StopAfterCheck):
        asyncio.run(prep_helpers.finalize_metadata(prep, meta, "", {}, None, "Car S.O.S.", "", ""))
    prep.metadata_searching_manager.get_tv_data.assert_awaited_once()


@pytest.mark.parametrize("unattended,confirm", [(False, False), (True, False), (True, True)])
def test_extra_only_pack_warns_about_specials_without_offering_marker(manager, monkeypatch, unattended, confirm):
    prompt = AsyncMock(return_value="y")
    monkeypatch.setattr(getseasonep, "prompt_in_thread", prompt)
    warnings = []
    monkeypatch.setattr(getseasonep.logger, "warning", warnings.append)
    meta = _meta(range(1, 12), tvdb_id=123, unattended=unattended, unattended_confirm=confirm, season_pack_incomplete=True)

    asyncio.run(manager.check_season_pack_completeness(meta))

    assert meta.season_pack_incomplete is False
    assert any("special episodes" in warning and "different numbering" in warning for warning in warnings)
    assert all("incomplete" not in warning.lower() for warning in warnings)
    if not unattended or confirm:
        prompt.assert_awaited_once()
        assert "Continue with these extra episodes" in prompt.call_args.args[1]
        assert "incomplete" not in prompt.call_args.args[1].lower()
    else:
        prompt.assert_not_awaited()


@pytest.mark.parametrize("answer", ["n", "no", "q", "", None, " \t ", "invalid"])
def test_extra_only_pack_can_be_aborted(manager, monkeypatch, answer):
    monkeypatch.setattr(getseasonep, "prompt_in_thread", AsyncMock(return_value=answer))
    meta = _meta(range(1, 12), tvdb_id=123)
    with pytest.raises(SystemExit):
        asyncio.run(manager.check_season_pack_completeness(meta))
    assert meta.season_pack_incomplete is False


def test_pack_with_missing_and_extra_episodes_still_offers_incomplete_confirmation(manager, monkeypatch):
    prompt = AsyncMock(return_value="y")
    monkeypatch.setattr(getseasonep, "prompt_in_thread", prompt)
    meta = _meta([1, *range(3, 13)], tvdb_id=123)
    asyncio.run(manager.check_season_pack_completeness(meta))
    assert "Is this pack really incomplete?" in prompt.call_args.args[1]
    assert meta.season_pack_incomplete is True


@pytest.mark.parametrize("answer", [None, "", " \t "])
def test_empty_filelist_prompt_aborts_without_crashing(manager, monkeypatch, answer):
    prompt = AsyncMock(return_value=answer)
    monkeypatch.setattr(getseasonep, "prompt_in_thread", prompt)
    meta = _meta(range(2, 22))
    with pytest.raises(SystemExit) as error:
        asyncio.run(manager.check_season_pack_completeness(meta))
    assert error.value.code == 1
    assert meta.season_pack_incomplete is False
    prompt.assert_awaited_once()
