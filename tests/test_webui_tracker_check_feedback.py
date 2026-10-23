import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src import trackerstatus, webui_events
from src.console import logger
from src.meta import Meta
from src.trackers.UNIT3D.retromoviesclub import RetroMoviesClub
from src.trackers.UNIT3D.skipthecommercials import SkipTheCommercials
from src.trackersetup import TrackerSetup


@pytest.fixture
def gui(monkeypatch):
    monkeypatch.setenv(webui_events.GUI_EVENTS_ENV, "1")
    monkeypatch.setenv(webui_events.GUI_EVENT_NONCE_ENV, "check-feedback-test")
    monkeypatch.setattr(webui_events, "_current_item", None)
    monkeypatch.setattr(trackerstatus.sys, "stdin", SimpleNamespace(closed=False))


def events(capsys):
    prefix = webui_events.event_prefix("check-feedback-test")
    return [json.loads(line[len(prefix):]) for line in capsys.readouterr().out.splitlines() if line.startswith(prefix)]


def answering(answer=False):
    async def prompt(question, **kwargs):
        prompt_id = webui_events.prompt_open("yes_no", question, **kwargs)
        webui_events.prompt_close(prompt_id)
        return answer
    return SimpleNamespace(prompt_yes_no=AsyncMock(side_effect=prompt))


@pytest.mark.asyncio
@pytest.mark.parametrize("tracker_class,reason", [
    (RetroMoviesClub, "Only movies released in 2000 or earlier are allowed."),
    (SkipTheCommercials, "Only TV and documentary movie uploads are allowed at SKIPTHECOMMERCIALS."),
])
@pytest.mark.parametrize("answer", [False, True])
async def test_real_tracker_reasons_are_shown_before_deciding_and_retained_only_when_skipped(gui, capsys, tracker_class, reason, answer):
    tracker = tracker_class.__new__(tracker_class)
    meta = Meta(category="MOVIE", year=2026, genres=["Crime"])
    helper = answering(answer)
    assert await trackerstatus.TrackerStatusManager({})._run_additional_checks(tracker.tracker, tracker, meta, helper) is answer
    opened = next(event for event in events(capsys) if event["kind"] == "prompt" and event["action"] == "open")
    assert opened["context"] == {"tracker": tracker.tracker, "check_messages": [reason]}
    assert opened["default"] is False
    if answer:
        assert "status_message" not in meta.tracker_status.get(tracker.tracker, {})
    else:
        assert meta.tracker_status[tracker.tracker]["status_message"] == reason


@pytest.mark.asyncio
async def test_no_reason_is_reported_honestly_without_inventing_a_failure(gui, capsys):
    helper = answering()
    tracker = SimpleNamespace(get_additional_checks=AsyncMock(return_value=False))
    meta = Meta()
    assert not await trackerstatus.TrackerStatusManager({})._run_additional_checks("FAKE", tracker, meta, helper)
    opened = next(event for event in events(capsys) if event["kind"] == "prompt" and event["action"] == "open")
    assert opened["context"]["check_messages"] == ["The tracker did not report a specific reason for this failed check."]
    assert meta.tracker_status["FAKE"]["status_message"] == "Upload checks failed"


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["unattended", "closed", "eof"])
async def test_skip_reason_survives_when_override_cannot_be_answered(gui, monkeypatch, mode):
    meta = Meta(category="MOVIE", year=2026, unattended=mode == "unattended")
    monkeypatch.setattr(trackerstatus.sys, "stdin", SimpleNamespace(closed=mode == "closed"))
    helper = SimpleNamespace(prompt_yes_no=AsyncMock(side_effect=EOFError))
    tracker = RetroMoviesClub.__new__(RetroMoviesClub)
    assert not await trackerstatus.TrackerStatusManager({})._run_additional_checks(tracker.tracker, tracker, meta, helper)
    assert meta.tracker_status[tracker.tracker]["status_message"] == "Only movies released in 2000 or earlier are allowed."
    assert helper.prompt_yes_no.await_count == (1 if mode == "eof" else 0)


@pytest.mark.asyncio
async def test_concurrent_checks_keep_their_own_messages_and_restore_handlers(gui, capsys):
    handlers = list(logger.handlers)
    started = 0
    both_started = asyncio.Event()

    async def run(name):
        async def check(_meta):
            nonlocal started
            logger.info(f"{name}: [red]{name} first reason[/red]")
            started += 1
            if started == 2:
                both_started.set()
            await both_started.wait()
            await asyncio.to_thread(logger.info, f"{name}: {name} final reason")
            return False
        meta = Meta()
        await trackerstatus.TrackerStatusManager({})._run_additional_checks(name, SimpleNamespace(get_additional_checks=check), meta, answering())
        return meta

    await asyncio.gather(run("FIRST"), run("SECOND"))
    opened = [event for event in events(capsys) if event["kind"] == "prompt" and event["action"] == "open"]
    assert len(opened) == 2
    for event in opened:
        name = event["context"]["tracker"]
        assert event["context"]["check_messages"] == [f"{name} first reason", f"{name} final reason"]
    assert logger.handlers == handlers
    assert webui_events._tracker_check.get() is None


@pytest.mark.asyncio
async def test_prompts_inside_a_check_receive_the_same_redacted_context(gui, capsys):
    with webui_events.capture_tracker_checks("FAKE", logger):
        logger.info('FAKE: [red]Rejected {"api_key":"hidden-secret"} at https://example.invalid/api?token=url-secret[/red]')
        await asyncio.to_thread(webui_events.prompt_open, "yes_no", "Continue anyway?", default=False)
    opened = next(event for event in events(capsys) if event["kind"] == "prompt")
    context = opened["context"]
    assert context["tracker"] == "FAKE"
    assert "hidden-secret" not in str(context)
    assert "url-secret" not in str(context)
    assert "[REDACTED]" in str(context)
    assert not context["check_messages"][0].startswith("FAKE:")


def test_capture_is_bounded_and_keeps_the_latest_reason(gui):
    with webui_events.capture_tracker_checks("FAKE", logger) as messages:
        for index in range(30):
            logger.info(f"FAKE: Reason {index}")
        logger.info("FAKE: " + "x" * 2000)
        logger.info("FAKE: Final rejection")
        logger.info("FAKE: Final rejection")
    assert len(messages) == webui_events.MAX_CHECK_MESSAGES
    assert messages[-1] == "Final rejection"
    assert len(messages[-2]) <= webui_events.MAX_TEXT_LENGTH
    assert messages[0] != "Reason 0"


def test_capture_is_disabled_for_console_only_runs(gui, monkeypatch):
    monkeypatch.delenv(webui_events.GUI_EVENTS_ENV)
    handlers = list(logger.handlers)
    with webui_events.capture_tracker_checks("FAKE", logger) as messages:
        logger.info("FAKE: Console-only explanation")
    assert messages == []
    assert logger.handlers == handlers


def test_explicit_skip_reason_does_not_turn_into_a_dupe_status(gui, capsys):
    webui_events.publish_tracker_statuses({"FAKE": {"skipped": True, "status_message": "Duplicate sources are not permitted by this rule"}}, final=True)
    result, = events(capsys)
    assert result["status"] == "skipped"
    assert result["message"] == "Duplicate sources are not permitted by this rule"


@pytest.mark.asyncio
async def test_real_checks_and_claim_reasons_reach_final_results(gui, monkeypatch, capsys):
    async def claimed(meta, name):
        if name != "AITHER":
            return False
        meta.tracker_status[name]["status_message"] = "Claimed match found: Synthetic Show, Season: 1, TMDB ID: 123"
        return True
    setup = SimpleNamespace(filter_unsupported_trackers=lambda _meta: None, check_banned_group=AsyncMock(return_value=False), get_torrent_claims=claimed)
    monkeypatch.setattr(trackerstatus, "TrackerSetup", lambda **_kwargs: setup)
    monkeypatch.setattr(trackerstatus, "AvistaZNetworkRouter", lambda *_args: SimpleNamespace(apply=AsyncMock()))
    monkeypatch.setattr(trackerstatus, "UploadHelper", lambda _config: answering())
    trackers = [RetroMoviesClub.__new__(RetroMoviesClub), SkipTheCommercials.__new__(SkipTheCommercials), SimpleNamespace(tracker="AITHER", banned_groups=[])]
    monkeypatch.setattr(trackerstatus, "tracker_class_map", {tracker.tracker: (lambda tracker=tracker, **_kwargs: tracker) for tracker in trackers})
    meta = Meta(name="Synthetic Feature", title="Synthetic Feature", category="MOVIE", year=2026, genres=["Crime"], imdb_id=123, trackers=[tracker.tracker for tracker in trackers])
    assert await trackerstatus.TrackerStatusManager({}).process_all_trackers(meta) == 0
    webui_events.publish_tracker_statuses(meta.tracker_status, final=True)
    results = {event["tracker"]: event for event in events(capsys) if event["kind"] == "tracker"}
    assert results["RETROMOVIESCLUB"]["message"] == "Only movies released in 2000 or earlier are allowed."
    assert "Only TV and documentary" in results["SKIPTHECOMMERCIALS"]["message"]
    assert "Claimed match found: Synthetic Show" in results["AITHER"]["message"]
    assert {event["status"] for event in results.values()} == {"skipped"}


@pytest.mark.asyncio
async def test_claim_match_stores_the_actual_title_season_and_tmdb(gui, tmp_path, monkeypatch):
    tracker = SimpleNamespace(get_type_id=AsyncMock(return_value={"WEBDL": "4"}), get_resolution_id=AsyncMock(return_value={"1080p": "3"}))
    setup = TrackerSetup(config={})
    monkeypatch.setattr(setup, "_create_tracker_instance", lambda _name: tracker)
    path = tmp_path / "data" / "banned" / "AITHER_claimed_releases.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"extracted_data": [{"title": "Synthetic [Duplicate] Show", "season": 1, "tmdb_id": 123, "resolutions": ["3"], "types": ["4"]}]}))
    meta = Meta(base_dir=str(tmp_path), type="WEBDL", resolution="1080p", category="TV", tmdb=123, season_int=1)
    assert await setup.check_tracker_claims(meta, "AITHER")
    assert meta.tracker_status["AITHER"]["status_message"] == "Claimed match found: Synthetic [Duplicate] Show, Season: 1, TMDB ID: 123"
