"""Duplicate review totals follow real prompts without changing their decisions."""
import asyncio
import json
import threading
from datetime import date

import pytest

from src import webui_events
from src.meta import Meta
from src.slot_rules.models import SlotDecision, Verdict
from src.uphelper import UploadHelper


@pytest.fixture
def gui(monkeypatch):
    """Enable nonce-bound events without real tracker or keyboard access."""
    monkeypatch.setenv(webui_events.GUI_EVENTS_ENV, "1")
    monkeypatch.setenv(webui_events.GUI_EVENT_NONCE_ENV, "review-progress-test")
    monkeypatch.setattr(webui_events, "_current_item", None)


def events(capsys):
    """Read progress events alongside the prompts they describe."""
    prefix = webui_events.event_prefix("review-progress-test")
    return [json.loads(line[len(prefix):]) for line in capsys.readouterr().out.splitlines() if line.startswith(prefix)]


class Tracker:
    """A local tracker stub with the existing season-pack rejection policy."""
    reject_episode_if_season_pack_exists = True

    async def get_name(self, meta):
        """Keep the synthetic release name unchanged."""
        return meta.name


def helper_with_answers(monkeypatch, ask=None):
    """Use real helper decisions while announcing fake keyboard responses."""
    helper = UploadHelper({"DEFAULT": {}})
    helper.tracker_class_map = {name: lambda **_kwargs: Tracker() for name in ("FIRST", "SECOND", "CLEAR")}

    def answer(question, default=False):
        """Announce and close the same prompt a keyboard response would answer."""
        prompt = webui_events.prompt_open("yes_no", question, default=default)
        try:
            return ask(question) if ask else False
        finally:
            webui_events.prompt_close(prompt)

    monkeypatch.setattr("src.uphelper.cli_ui.ask_yes_no", answer)
    return helper


@pytest.mark.asyncio
async def test_slow_searches_update_the_total_while_the_first_review_waits(gui, monkeypatch, capsys):
    """Count queued manual reviews, exclude clear trackers, and keep real order."""
    waiting = threading.Event()
    resume = threading.Event()

    def answer(question):
        """Hold the first prompt while later synthetic searches finish."""
        if "FIRST" in question:
            waiting.set()
            assert resume.wait(3)
        return False

    helper = helper_with_answers(monkeypatch, answer)
    meta = Meta(category="MOVIE", name="Example")
    webui_events.begin_item("Example.mkv", 1, 1)
    with webui_events.dupe_review_scope(["FIRST", "SECOND", "CLEAR"]):
        first = asyncio.create_task(helper.dupe_check(["First existing release"], meta.copy(), "FIRST"))
        try:
            assert await asyncio.to_thread(waiting.wait, 3)
            initial = [event for event in events(capsys) if event["kind"] == "dupe_review"][-1]
            assert initial["trackers"] == ["FIRST"]
            assert initial["started"] == ["FIRST"]
            assert initial["checking"] == 2
            second = asyncio.create_task(helper.dupe_check(["Second existing release"], meta.copy(), "SECOND"))
            clear = asyncio.create_task(helper.dupe_check([], meta.copy(), "CLEAR"))
            await asyncio.sleep(0)
            discovered = [event for event in events(capsys) if event["kind"] == "dupe_review"][-1]
            assert discovered["trackers"] == ["FIRST", "SECOND"]
            assert discovered["started"] == ["FIRST"]
            assert discovered["checking"] == 0
        finally:
            resume.set()
        assert [result[0] for result in await asyncio.gather(first, second, clear)] == [True, True, False]
        final = [event for event in events(capsys) if event["kind"] == "dupe_review"][-1]
        assert final["started"] == ["FIRST", "SECOND"]


@pytest.mark.asyncio
@pytest.mark.parametrize("mode,dupes,manual", [
    ({}, [], False),
    ({}, ["existing release"], True),
    ({"unattended": True}, ["existing release"], False),
    ({"unattended": True, "unattended_confirm": True}, ["existing release"], True),
    ({"dupe": True}, ["existing release"], False),
    ({"ask_dupe": True}, ["existing release"], False),
    ({"season_pack_exists": True}, ["existing season"], False),
    ({"dupe": True, "filename_match": "exact", "file_count_match": True}, ["existing release"], True),
])
async def test_only_trackers_with_manual_prompts_are_counted(gui, monkeypatch, capsys, mode, dupes, manual):
    """Automatic approvals, unattended decisions and season-pack skips add no reviews."""
    helper = helper_with_answers(monkeypatch)
    with webui_events.dupe_review_scope(["FIRST"]):
        await helper.dupe_check(dupes, Meta(category="TV", name="Example", **mode), "FIRST")
        webui_events.dupe_review_ready("FIRST", finished=True)
    output = events(capsys)
    progress = [event for event in output if event["kind"] == "dupe_review"][-1]
    prompts = [event for event in output if event["kind"] == "prompt" and event["action"] == "open"]
    assert bool(prompts) is manual
    assert progress["trackers"] == (["FIRST"] if manual else [])
    assert progress["started"] == (["FIRST"] if manual else [])
    assert progress["checking"] == 0


@pytest.mark.asyncio
async def test_slot_override_and_two_trump_questions_count_once_per_tracker(gui, monkeypatch, capsys):
    """A slot-only conflict and a multi-question trump flow are both manual reviews."""
    helper = helper_with_answers(monkeypatch)
    slot = SlotDecision(Verdict.BLOCK, "Slot filled", "FIRST", date(2026, 10, 15))
    with webui_events.dupe_review_scope(["FIRST", "SECOND"]):
        await helper.dupe_check([], Meta(category="MOVIE", name="Example"), "FIRST", slot)
        await helper.dupe_check([{"name": "Trumpable release", "trumpable": True}], Meta(category="MOVIE", name="Example", trumpable_id=1), "SECOND")
    output = events(capsys)
    prompts = [event for event in output if event["kind"] == "prompt" and event["action"] == "open"]
    assert len(prompts) == 3
    final = [event for event in output if event["kind"] == "dupe_review"][-1]
    assert final["started"] == ["FIRST", "SECOND"]
    assert final["trackers"] == ["FIRST", "SECOND"]


@pytest.mark.asyncio
async def test_concurrent_batches_keep_their_review_lists_separate(gui, capsys):
    """Context propagation never mixes independent tracker batches."""
    async def batch(tracker):
        """Interleave one independent batch with another on the event loop."""
        with webui_events.dupe_review_scope([tracker]):
            await asyncio.sleep(0)
            webui_events.dupe_review_ready(tracker, needs_review=True)
            with webui_events.prompt_context(kind="dupes", tracker=tracker):
                webui_events.prompt_close(webui_events.prompt_open("yes_no", "Upload anyway?"))

    await asyncio.gather(batch("FIRST"), batch("SECOND"))
    progress = [event for event in events(capsys) if event["kind"] == "dupe_review"]
    assert all(len(event["trackers"]) <= 1 for event in progress)
    assert [event["started"] for event in progress if event["started"]] == [["FIRST"], ["SECOND"]]


def test_progress_is_silent_outside_gui(monkeypatch, capsys):
    """The ordinary CLI does not emit or build review progress."""
    monkeypatch.delenv(webui_events.GUI_EVENTS_ENV, raising=False)
    with webui_events.dupe_review_scope(["FIRST"]):
        webui_events.dupe_review_ready("FIRST", needs_review=True)
    assert capsys.readouterr().out == ""
