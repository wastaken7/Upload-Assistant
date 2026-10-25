"""Client skips in the final GUI summary reflect actual per-item removals."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

import upload
from src import trackerstatus, webui_events
from src.meta import Meta


@pytest.fixture
def gui(monkeypatch):
    """Use nonce-bound GUI events without a WebUI connection or live services."""
    monkeypatch.setenv(webui_events.GUI_EVENTS_ENV, "1")
    monkeypatch.setenv(webui_events.GUI_EVENT_NONCE_ENV, "client-skip-test")
    monkeypatch.setattr(webui_events, "_current_item", None)


def emitted(capsys):
    """Read only the structured events emitted by this test run."""
    prefix = webui_events.event_prefix("client-skip-test")
    return [json.loads(line[len(prefix):]) for line in capsys.readouterr().out.splitlines() if line.startswith(prefix)]


@pytest.mark.asyncio
@pytest.mark.parametrize("selected,matched,debug,manual_remove,remaining,reported", [
    (["AITHER", "BLUTOPIA"], ["AITHER"], False, "", ["BLUTOPIA"], ["AITHER"]),
    (["AITHER", "BLUTOPIA"], ["AITHER", "AITHER", "UNSELECTED"], False, "", ["BLUTOPIA"], ["AITHER"]),
    (["AITHER", "BLUTOPIA"], ["UNSELECTED"], False, "", ["AITHER", "BLUTOPIA"], []),
    (["AITHER", "BLUTOPIA"], ["AITHER"], True, "", ["AITHER", "BLUTOPIA"], []),
    (["AITHER", "BLUTOPIA"], False, False, "", ["AITHER", "BLUTOPIA"], []),
    (["AITHER", "BLUTOPIA"], ["AITHER"], False, "AITHER", ["BLUTOPIA"], []),
    (["AITHER"], ["AITHER"], False, "", [], ["AITHER"]),
])
async def test_only_actual_client_removals_reach_the_summary(gui, tmp_path, monkeypatch, selected, matched, debug, manual_remove, remaining, reported):
    """Run real removal logic while stopping before tracker checks or uploads."""
    meta = Meta(base_dir=str(tmp_path), uuid="synthetic", path=str(tmp_path / "Synthetic.mkv"), category="MOVIE", title="Synthetic", imghost="ptscreens",
                trackers=list(selected), remove_trackers=matched, debug=debug, trackers_remove=manual_remove, client_skipped_trackers=["STALE_PREVIOUS_ITEM"])

    class ReachedTrackerChecks(Exception):
        """Stop after the removal stage without contacting any tracker."""

    checks = AsyncMock(side_effect=ReachedTrackerChecks)
    monkeypatch.setattr(upload, "config", {"DEFAULT": {"img_host_1": "ptscreens"}, "TRACKERS": {}})
    monkeypatch.setattr(upload, "Prep", lambda **_kwargs: SimpleNamespace(gather_prep=AsyncMock(return_value=meta)))
    monkeypatch.setattr(upload.TrackerSetup, "filter_unsupported_trackers", lambda _self, _meta: None)
    monkeypatch.setattr(upload, "name_manager", SimpleNamespace(get_name=AsyncMock(return_value=("Synthetic", "Synthetic", "Synthetic", []))), raising=False)
    monkeypatch.setattr(upload, "gen_desc", AsyncMock(return_value=meta))
    monkeypatch.setattr(upload.UploadHelper, "get_confirmation", AsyncMock(return_value=True))
    monkeypatch.setattr(upload, "validate_tracker_logins", AsyncMock())
    monkeypatch.setattr(upload.TrackerStatusManager, "process_all_trackers", checks)
    monkeypatch.setattr(upload, "write_meta_file", AsyncMock())
    monkeypatch.setattr(upload, "_publish_webui_preview_target", Mock())
    if remaining:
        with pytest.raises(ReachedTrackerChecks):
            await upload.process_meta(meta, str(tmp_path))
        checks.assert_awaited_once_with(meta)
    else:
        assert await upload.process_meta(meta, str(tmp_path)) is True
        checks.assert_not_awaited()
    assert meta.trackers == remaining
    assert meta.client_skipped_trackers == reported


@pytest.mark.asyncio
@pytest.mark.parametrize("answer", [False, True])
@pytest.mark.parametrize("client_skips", [[], ["AITHER", "HOMIEHELPDESK"], [f"CLIENT_TRACKER_{index:03d}" for index in range(40)]])
async def test_final_confirmation_keeps_client_skips_separate_from_tracker_checks(gui, monkeypatch, capsys, answer, client_skips):
    """The real final prompt preserves group membership, complete lists and decisions."""
    setup = SimpleNamespace(filter_unsupported_trackers=lambda _meta: None, check_banned_group=AsyncMock(return_value=False),
                            get_torrent_claims=AsyncMock(side_effect=lambda _meta, name: name == "RULE"))
    monkeypatch.setattr(trackerstatus, "TrackerSetup", lambda **_kwargs: setup)
    monkeypatch.setattr(trackerstatus, "AvistaZNetworkRouter", lambda *_args: SimpleNamespace(apply=AsyncMock()))
    monkeypatch.setattr(trackerstatus, "evaluate_slots", AsyncMock(return_value=None))
    monkeypatch.setattr(trackerstatus, "DupeChecker", lambda _config: SimpleNamespace(filter_dupes=AsyncMock(side_effect=lambda dupes, *_args: dupes)))

    async def dupe_check(dupes, meta, *_args):
        """Return controlled duplicate decisions without any manual dupe prompts."""
        return bool(dupes), meta

    async def prompt(question, default=False):
        """Announce the final question and return a controlled approval or refusal."""
        prompt_id = webui_events.prompt_open("yes_no", question, default=default)
        webui_events.prompt_close(prompt_id)
        return answer

    monkeypatch.setattr(trackerstatus, "UploadHelper", lambda _config: SimpleNamespace(dupe_check=dupe_check, prompt_yes_no=prompt))
    names = ["FIRST", "SECOND", "RULE", "DUPE"]
    trackers = {name: SimpleNamespace(tracker=name, banned_groups=[], get_name=AsyncMock(return_value="Synthetic"),
                                     search_existing=AsyncMock(return_value=["Existing release"] if name == "DUPE" else [])) for name in names}
    monkeypatch.setattr(trackerstatus, "tracker_class_map", {name: (lambda name=name, **_kwargs: trackers[name]) for name in names})
    meta = Meta(category="MOVIE", name="Synthetic", imdb_id=1, trackers=names, client_skipped_trackers=list(client_skips))
    webui_events.begin_item("Synthetic.mkv", 1, 1)
    count = await trackerstatus.TrackerStatusManager({}).process_all_trackers(meta)
    opened = [event for event in emitted(capsys) if event["kind"] == "prompt" and event["action"] == "open"]
    assert len(opened) == 1
    assert opened[0]["question"] == "Upload to all?"
    assert opened[0]["default"] is False
    context = opened[0]["context"]
    assert context["kind"] == "dupe_clear"
    assert context["clear_trackers"] == "FIRST,SECOND"
    assert context["dupe_trackers"] == "DUPE"
    assert context["skipped_trackers"] == "RULE"
    assert context["client_skipped_trackers"] == client_skips
    assert count == (2 if answer else 0)
    assert all(meta.tracker_status[name]["upload"] is answer for name in ("FIRST", "SECOND"))
    assert set(meta.tracker_status) == set(names)
