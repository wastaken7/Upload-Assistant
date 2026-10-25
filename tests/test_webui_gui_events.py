import io
import json
import logging
import subprocess
import sys
import time

import pytest

import web_ui.server as server
from src import webui_events
from src.console import GuiNoticeHandler

TEST_NONCE = "fictional-nonce"


def _events(output: str, nonce: str = TEST_NONCE) -> list[dict[str, object]]:
    prefix = webui_events.event_prefix(nonce)
    return [json.loads(line.removeprefix(prefix)) for line in output.splitlines() if line.startswith(prefix)]


@pytest.fixture
def gui_env(monkeypatch):
    monkeypatch.setenv(webui_events.GUI_EVENTS_ENV, "1")
    monkeypatch.setenv(webui_events.GUI_EVENT_NONCE_ENV, TEST_NONCE)
    monkeypatch.setattr(webui_events, "_current_item", None)
    monkeypatch.setattr(webui_events, "_active_stage", None)
    monkeypatch.setattr(webui_events, "_started_stages", set())


def test_events_are_silent_outside_the_web_ui(monkeypatch, capsys) -> None:
    monkeypatch.delenv(webui_events.GUI_EVENTS_ENV, raising=False)

    webui_events.stage("prep", "start")
    webui_events.notice("error", "Something failed")
    webui_events.tracker_result("FAKE", "success")

    assert capsys.readouterr().out == ""


def test_payload_helpers_do_no_work_outside_the_web_ui(monkeypatch) -> None:
    monkeypatch.delenv(webui_events.GUI_EVENTS_ENV, raising=False)

    def fail(*_args, **_kwargs):
        raise AssertionError("payload built outside the Web UI")

    monkeypatch.setattr(webui_events, "plain_text", fail)
    monkeypatch.setattr(webui_events, "_release_entries", fail)

    webui_events.notice("error", "x")
    webui_events.notice_group("confirm", [{"level": "error", "text": "x"}])
    webui_events.dupes("FAKE", [{"name": "x"}])
    webui_events.slot("FAKE", "review", "t", "r", conflicts=[{"name": "x"}])
    webui_events.tracker_result("FAKE", "success")
    webui_events.request_match("FAKE", "x")


def test_events_carry_the_item_and_plain_redacted_text(gui_env, capsys) -> None:
    webui_events.begin_item("/media/Fictional.Movie.2020.mkv", 2, 3)
    webui_events.notice("error", "[bold red]Upload failed for https://tracker.invalid/upload?passkey=abc123[/bold red]", tracker="FAKE")

    item, notice = _events(capsys.readouterr().out)

    assert item == {"kind": "item", "ts": item["ts"], "index": 2, "total": 3, "name": "Fictional.Movie.2020.mkv"}
    assert notice["item"] == 2
    assert notice["text"] == "Upload failed for https://tracker.invalid/upload?passkey=[REDACTED]"
    assert notice["tracker"] == "FAKE"


def test_tracker_results_drop_non_http_links_and_unknown_statuses(gui_env, capsys) -> None:
    webui_events.tracker_result("FAKE", "success", link="javascript:alert(1)", torrent_id=7, duration=1.234)
    webui_events.tracker_result("FAKE", "exploded")  # type: ignore[arg-type]

    (event,) = _events(capsys.readouterr().out)

    assert "link" not in event
    assert event["torrent_id"] == "7"
    assert event["duration"] == 1.23


def test_personal_release_flag_updates_the_current_item_and_resets_for_the_next(gui_env, capsys) -> None:
    """Resolved flags retain the release identity without leaking to another item."""
    webui_events.update_item(personal_release=True)
    assert capsys.readouterr().out == ""
    webui_events.begin_item("/media/Personal.mkv", 1, 2)
    webui_events.update_item(personal_release=True)
    webui_events.begin_item("/media/Other.mkv", 2, 2)

    started, updated, other = _events(capsys.readouterr().out)
    assert {key: value for key, value in updated.items() if key != "ts"} == {
        "kind": "item", "index": 1, "total": 2, "name": "Personal.mkv", "personal_release": True,
    }
    assert "personal_release" not in started
    assert "personal_release" not in other


@pytest.mark.asyncio
@pytest.mark.parametrize("personal_release", [False, True])
async def test_unattended_confirmation_publishes_the_resolved_personal_release_flag(gui_env, capsys, personal_release) -> None:
    """Unattended runs publish the badge even though they do not open a prompt."""
    from src.meta import Meta
    from src.uphelper import UploadHelper

    webui_events.begin_item("/media/Example.mkv", 1, 1)
    assert await UploadHelper({"DEFAULT": {}}).get_confirmation(Meta(category="MOVIE", unattended=True, personalrelease=personal_release)) is True

    updates = [event for event in _events(capsys.readouterr().out) if event["kind"] == "item" and "personal_release" in event]
    assert len(updates) == 1
    assert updates[0]["personal_release"] is personal_release


def test_oversized_events_are_not_written(gui_env, capsys, monkeypatch) -> None:
    monkeypatch.setattr(webui_events, "MAX_EVENT_BYTES", 200)

    webui_events.notice("error", "x" * 500)

    assert capsys.readouterr().out == ""


def test_stages_remember_which_one_to_fail(gui_env, capsys) -> None:
    webui_events.stage("screens", "start")
    webui_events.fail_active_stage()
    webui_events.fail_active_stage()

    events = _events(capsys.readouterr().out)

    assert [(event["key"], event["status"]) for event in events] == [("screens", "start"), ("screens", "fail")]


@pytest.mark.parametrize(
    ("status", "final", "expected"),
    [
        ({"banned": True, "upload": False}, False, "banned"),
        ({"upload": True, "upload_success": True}, True, "success"),
        ({"upload": True, "upload_success": False, "status_message": "data error: rejected"}, True, "failed"),
        ({"dupe": True, "upload": False}, False, "dupe"),
        ({"skipped": True, "upload": False}, False, "skipped"),
        ({"upload": True}, False, "pending"),
        ({"upload": True}, True, "failed"),
        ({"upload": False}, False, "skipped"),
    ],
)
def test_tracker_status_classification(status, final, expected) -> None:
    assert webui_events.tracker_status_from_meta(status, final=final) == expected


def test_approved_trackers_are_skipped_when_the_upload_stage_never_ran(gui_env, capsys) -> None:
    webui_events.begin_item("/media/Fictional.Movie.2020.mkv", 1, 1)
    webui_events.stage("dupes", "start")
    webui_events.publish_tracker_statuses({"FAKE": {"upload": True}}, final=True)
    webui_events.stage("upload", "start")
    webui_events.publish_tracker_statuses({"FAKE": {"upload": True}}, final=True)

    statuses = [event["status"] for event in _events(capsys.readouterr().out) if event["kind"] == "tracker"]

    assert statuses == ["skipped", "failed"]


def test_prompt_context_is_attached_to_prompts(gui_env, capsys) -> None:
    with webui_events.prompt_context(kind="dupes", tracker="FAKE"):
        prompt_id = webui_events.prompt_open("yes_no", "Upload to FAKE anyway?", default=False)
    webui_events.prompt_close(prompt_id)

    opened, closed = _events(capsys.readouterr().out)

    assert opened["context"] == {"kind": "dupes", "tracker": "FAKE"}
    assert opened["default"] is False
    assert closed == {"kind": "prompt", "ts": closed["ts"], "action": "close", "id": prompt_id}


def _record(level: int, message: str, **extra: object) -> logging.LogRecord:
    record = logging.LogRecord("UploadAssistant", level, __file__, 1, message, None, None)
    for key, value in extra.items():
        setattr(record, key, value)
    return record


@pytest.mark.parametrize(
    ("level", "message", "extra", "expected"),
    [
        (logging.INFO, "[red]Upload failed: timeout[/red]", {}, ("error", "Upload failed: timeout")),
        (logging.INFO, "[bold red]Something broke[/bold red]", {}, ("error", "Something broke")),
        (logging.ERROR, "plain error", {}, ("error", "plain error")),
        (logging.WARNING, "[yellow]Careful[/yellow]", {}, ("warning", "Careful")),
        (logging.INFO, "[yellow]Searching for existing torrents...", {}, None),
        (logging.INFO, "[red]│[/red]", {}, None),
        (logging.INFO, "[red]Shown as a result row[/red]", {"ua_gui": False}, None),
        (logging.DEBUG, "[red]debug only[/red]", {}, None),
        (logging.INFO, "[red]a [literal] bracket[/red]", {"markup": False}, ("error", "[red]a [literal] bracket[/red]")),
    ],
)
def test_notice_handler_classifies_records(monkeypatch, level, message, extra, expected) -> None:
    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(webui_events, "notice", lambda notice_level, text, **_kwargs: sent.append((notice_level, text)))
    handler = GuiNoticeHandler()

    if level >= handler.level:
        handler.handle(_record(level, message, **extra))

    assert sent == ([expected] if expected else [])


def test_notice_handler_stops_after_its_limit(monkeypatch) -> None:
    sent: list[str] = []
    monkeypatch.setattr(webui_events, "notice", lambda _level, text, **_kwargs: sent.append(text))
    monkeypatch.setattr("src.console._MAX_GUI_NOTICES", 2)
    handler = GuiNoticeHandler()

    for index in range(5):
        handler.handle(_record(logging.ERROR, f"error number {index}"))

    assert sent == ["error number 0", "error number 1"]


def test_notice_handler_limit_restarts_for_each_queue_item(monkeypatch) -> None:
    sent: list[str] = []
    monkeypatch.setattr(webui_events, "notice", lambda _level, text, **_kwargs: sent.append(text))
    monkeypatch.setattr("src.console._MAX_GUI_NOTICES", 1)
    handler = GuiNoticeHandler()

    for item in (1, 2):
        monkeypatch.setattr(webui_events, "_current_item", {"index": item, "total": 2})
        for index in range(3):
            handler.handle(_record(logging.ERROR, f"item {item} error {index}"))

    assert sent == ["item 1 error 0", "item 2 error 0"]


def test_cli_ui_prompts_are_announced_and_still_answered_from_stdin() -> None:
    code = (
        "import src.console\n"
        "src.console.install_gui_prompt_events()\n"
        "import cli_ui\n"
        "print('YES=' + str(cli_ui.ask_yes_no('Continue?', default=False)), flush=True)\n"
        "print('PICK=' + str(cli_ui.ask_choice('Pick one', choices=['zeta', 'alpha'])), flush=True)\n"
        "print('TEXT=' + str(cli_ui.ask_string('Title?', default='Fallback')), flush=True)\n"
        "print('MULTI=' + str(cli_ui.select_choices('Pick any', choices=['zeta', 'alpha', 'beta'])), flush=True)\n"
    )
    result = subprocess.run(  # noqa: S603 - fixed Python prompt fixture
        [sys.executable, "-u", "-c", code],
        input="y\n1\n\n1,3\n",
        text=True,
        encoding="utf-8",
        capture_output=True,
        env=server._webui_subprocess_env(),
        check=True,
        timeout=60,
    )

    prompts = [event for event in _events(result.stdout, server._GUI_EVENT_NONCE) if event["kind"] == "prompt"]
    opened = [event for event in prompts if event["action"] == "open"]

    assert [event["type"] for event in opened] == ["yes_no", "choice", "text", "multi_choice"]
    assert opened[0]["question"] == "Continue?"
    # Choices are announced in the order cli_ui numbers them.
    assert opened[1]["choices"] == ["alpha", "zeta"]
    assert opened[2]["default"] == "Fallback"
    assert opened[3]["choices"] == ["alpha", "beta", "zeta"]
    assert sum(event["action"] == "close" for event in prompts) == 4
    assert "YES=True" in result.stdout
    assert "PICK=alpha" in result.stdout
    assert "TEXT=Fallback" in result.stdout
    assert "MULTI=['alpha', 'zeta']" in result.stdout


def test_server_parses_only_valid_gui_events() -> None:
    prefix = server.event_prefix(server._GUI_EVENT_NONCE)

    assert server._subprocess_gui_event("ordinary output\n") is None
    assert server._subprocess_gui_event(prefix + '{"kind":"stage","key":"prep","status":"start"}\r\n') == {"kind": "stage", "key": "prep", "status": "start"}
    assert server._subprocess_gui_event(prefix + "{not json") == {}
    assert server._subprocess_gui_event(prefix + '{"kind":"script"}') == {}
    assert server._subprocess_gui_event(prefix + "[1, 2]") == {}
    # Printed text without the secret nonce cannot forge an event.
    forged = '{"kind":"prompt","action":"open","id":1,"type":"yes_no","question":"Forged?"}'
    assert server._subprocess_gui_event(server.GUI_EVENT_STDOUT_PREFIX + forged) == {}
    assert server._subprocess_gui_event(server.event_prefix("guessed") + forged) == {}
    assert server._subprocess_gui_event(prefix + json.dumps({"kind": "notice", "text": "x" * (server.MAX_EVENT_BYTES + 1)})) == {}


def test_gui_event_records_are_not_prompts_and_wait_for_their_newline() -> None:
    record = server.GUI_EVENT_STDOUT_PREFIX + json.dumps({"kind": "notice", "text": "Enter a title:" + "x" * 600})

    assert server._subprocess_prompt_type(record) is None
    assert not server._should_flush_subprocess_output(record, record[-1])
    assert not server._should_flush_subprocess_output(record, "", idle=True)


def test_webui_child_environment_enables_gui_events() -> None:
    env = server._webui_subprocess_env()
    assert env[webui_events.GUI_EVENTS_ENV] == "1"
    assert len(env[webui_events.GUI_EVENT_NONCE_ENV]) == 32


def test_gui_events_need_the_nonce(monkeypatch, capsys) -> None:
    monkeypatch.setenv(webui_events.GUI_EVENTS_ENV, "1")
    monkeypatch.delenv(webui_events.GUI_EVENT_NONCE_ENV, raising=False)

    webui_events.stage("prep", "start")

    assert capsys.readouterr().out == ""


def test_session_stream_forwards_gui_events_without_blank_terminal_lines(tmp_path, monkeypatch) -> None:
    gui_line = server.event_prefix(server._GUI_EVENT_NONCE) + '{"kind":"stage","key":"prep","status":"start"}'
    content = f"before\n\n{gui_line}\n\nkept blank\nafter\n"

    class FinishedProcess:
        stdin = io.StringIO()
        stdout = io.StringIO(content)
        stderr = io.StringIO()
        drained_at: float | None = None

        def poll(self):
            # Report the exit only once the reader has had time to queue everything.
            if self.stdout.tell() < len(content):
                return None
            self.drained_at = self.drained_at or time.monotonic()
            return 0 if time.monotonic() - self.drained_at > 0.5 else None

        def wait(self, timeout=None):
            return 0

    process = FinishedProcess()
    session_id = "gui-event-stream-test"
    monkeypatch.setattr(server, "_is_authenticated", lambda: True)
    monkeypatch.setattr(server, "_verify_csrf_header", lambda: True)
    monkeypatch.setattr(server, "_verify_same_origin", lambda: True)
    monkeypatch.setattr(server, "_validate_execution_path", lambda *_args, **_kwargs: str(tmp_path))
    monkeypatch.setattr(server, "_assert_safe_resolved_path", lambda _: None)
    monkeypatch.setattr(server, "_validate_upload_assistant_args", lambda args: args)
    monkeypatch.setattr(server, "_spawn_webui_upload_process", lambda *_args: (process, "subprocess"))
    monkeypatch.setattr(server, "_terminate_process_tree", lambda _process: True)
    response = server.app.test_client().post("/api/execute", json={"path": str(tmp_path), "session_id": session_id}, buffered=False)
    try:
        assert response.status_code == 200
        received: list[dict[str, object]] = []
        deadline = time.monotonic() + 10
        for chunk in response.response:
            assert time.monotonic() < deadline, "Session never finished"
            event = json.loads(chunk.decode().removeprefix("data: "))
            if event["type"] in {"html", "gui"}:
                received.append(event)
            if event["type"] in {"exit", "finished"}:
                break
    finally:
        response.close()
        server.active_processes.pop(session_id, None)

    kinds = [event["type"] for event in received]
    html = [str(event["data"]) for event in received if event["type"] == "html"]
    assert kinds.count("gui") == 1
    assert received[kinds.index("gui")]["data"] == {"kind": "stage", "key": "prep", "status": "start"}
    assert "UA_GUI_EVENT_JSON" not in "".join(html)
    # The newline written before the record is dropped; a real blank line is kept.
    assert len(html) == 4
    assert "before" in html[0] and "kept blank" in html[2] and "after" in html[3]


def test_slot_events_carry_the_terminal_details(gui_env, capsys) -> None:
    from datetime import date

    webui_events.slot(
        "FAKE",
        "review",
        "Check before uploading",
        "A release in the same slot exists.",
        slot_name="1080p WEB",
        why="One release per group and resolution.",
        conflicts=[{"name": "Fictional.Movie.2020-OTHERGRP", "link": "https://tracker.invalid/t/1", "size": "4 GiB"}],
        notes=["Check the audio tracks."],
        rules_date=date(2020, 1, 1),
        source_size=4 * 1024**3,
    )

    (event,) = _events(capsys.readouterr().out)

    assert event["slot"] == "1080p WEB"
    assert event["why"] == "One release per group and resolution."
    assert event["notes"] == ["Check the audio tracks."]
    assert event["rules"].startswith("Rules as of 2020-01-01 (")
    (conflict,) = event["conflicts"]
    assert conflict["diff_pct"] == 0
    # Same size as the upload: the terminal's red end of the scale.
    assert conflict["color"] == "#f43d3d"


def test_dupe_colours_follow_the_size_difference(gui_env, capsys) -> None:
    webui_events.dupes("FAKE", [{"name": "Close", "size": "4 GiB"}, {"name": "Far", "size": "2 GiB"}, {"name": "No size"}], source_size=4 * 1024**3)

    (event,) = _events(capsys.readouterr().out)

    close, far, unknown = event["entries"]
    assert close["color"] == "#f43d3d"
    assert far["color"] == "#3df43d"
    assert "color" not in unknown


def test_trackers_that_passed_the_dupe_check_say_so(gui_env, capsys) -> None:
    webui_events.publish_tracker_statuses({"FAKE": {"upload": True, "dupe": False}, "OTHER": {"upload": True}})

    fake, other = _events(capsys.readouterr().out)

    assert fake["status"] == "pending"
    assert fake["message"] == "No potential dupes found"
    assert "message" not in other


def test_numbered_options_reach_the_prompt_in_order(gui_env, capsys) -> None:
    with webui_events.numbered_options(["Fictional Album (2020)", "Fictional Album (2021)"], actions=[("0", "Skip")]):
        webui_events.prompt_open("text", "Release (1-2, 0 to skip):")

    (opened,) = _events(capsys.readouterr().out)

    assert opened["context"] == {
        "kind": "options",
        "options": ["Fictional Album (2020)", "Fictional Album (2021)"],
        "actions": [["0", "Skip"]],
        "start": "1",
    }


def test_long_dupe_lists_are_sent_whole(gui_env, capsys) -> None:
    entries = [{"name": f"Fictional.Album.{index}.FLAC-GROUP" * 4, "link": f"https://tracker.invalid/t/{index}", "size": "1 GiB"} for index in range(120)]

    webui_events.dupes("FAKE", entries, source_size=2**30)

    (event,) = _events(capsys.readouterr().out)
    assert len(event["entries"]) == 120


@pytest.mark.parametrize(
    ("webui", "question", "answers"),
    [
        (
            False,
            "Enter 'e' to edit, 'd' to discard, or press Enter to keep it as is: ",
            [["", "Keep it as is"], ["e", "Edit"], ["d", "Discard"]],
        ),
        # A Web UI run has no editor on the server, so editing is never offered.
        (
            True,
            "Enter 'd' to discard, or press Enter to keep it as is: ",
            [["", "Keep it as is"], ["d", "Discard"]],
        ),
    ],
)
def test_letter_prompts_offer_edit_only_where_an_editor_exists(gui_env, capsys, monkeypatch, webui, question, answers) -> None:
    if webui:
        monkeypatch.setenv("UA_WEBUI_ACTIVE", "1")
    else:
        monkeypatch.delenv("UA_WEBUI_ACTIVE", raising=False)

    asked, buttons = webui_events.letter_prompt([("e", "edit"), ("d", "discard")], "keep it as is")
    with webui_events.answer_buttons(buttons):
        webui_events.prompt_open("text", asked)

    (opened,) = _events(capsys.readouterr().out)
    assert asked == question
    assert webui_events.editor_available() is not webui
    assert opened["context"]["actions"] == answers
    assert opened["context"]["options"] == []


def test_numbered_options_can_count_from_zero(gui_env, capsys) -> None:
    with webui_events.numbered_options(["00800.mpls", "00801.mpls"], start=0):
        webui_events.prompt_open("text", "Select playlists: ")

    (opened,) = _events(capsys.readouterr().out)
    assert opened["context"]["start"] == "0"


def test_webui_child_runs_without_a_terminal_editor() -> None:
    assert server._webui_subprocess_env()["UA_WEBUI_ACTIVE"] == "1"


def test_option_and_release_labels_keep_bracketed_text(gui_env, capsys) -> None:
    label = "fictional band - album [remastered] [web]"
    with webui_events.numbered_options([label], actions=[("", "keep [as is]")]):
        webui_events.prompt_open("choice", "Pick one", choices=[label])
    webui_events.dupes("FAKE", [{"name": label}])

    opened, dupes = _events(capsys.readouterr().out)
    assert opened["context"]["options"] == [label]
    assert opened["context"]["actions"] == [["", "keep [as is]"]]
    assert opened["choices"] == [label]
    assert dupes["entries"][0]["name"] == label


def test_numbered_options_carry_only_web_thumbnails(gui_env, capsys) -> None:
    images = ["https://image.tmdb.org/t/p/w92/fictional.jpg", "", "javascript:alert(1)"]
    with webui_events.numbered_options(["First (2020)", "Second (2021)", "Third (2022)"], images=images):
        webui_events.prompt_open("text", "Enter the number of the correct entry:")
    with webui_events.numbered_options(["No posters"], images=["", ""]):
        webui_events.prompt_open("text", "Pick one:")

    with_images, without_images = _events(capsys.readouterr().out)
    assert with_images["context"]["images"] == ["https://image.tmdb.org/t/p/w92/fictional.jpg", "", ""]
    assert "images" not in without_images["context"]


def test_numbered_options_carry_structured_details(gui_env, capsys) -> None:
    details = [
        {"meta": "TMDb 1 · similarity 0.40", "text": "A fictional synopsis.", "link": "https://www.themoviedb.org/movie/1", "link_label": "TMDb"},
        {"meta": "TMDb 2", "link": "javascript:alert(1)", "link_label": "TMDb"},
    ]
    with webui_events.numbered_options(["Fictional Film (2020)", "Other Film (2021)"], details=details):
        webui_events.prompt_open("text", "Enter the number of the correct entry:")

    (opened,) = _events(capsys.readouterr().out)
    first, second = opened["context"]["details"]
    assert first == {"meta": "TMDb 1 · similarity 0.40", "text": "A fictional synopsis.", "link": "https://www.themoviedb.org/movie/1", "link_label": "TMDb", "flag": ""}
    assert second["link"] == ""


def test_field_prompts_show_the_values_a_question_is_about(gui_env, capsys) -> None:
    summary = {"Artist": "Fictional Band", "Album": "", "Year": 2020, "Tracks": ["One", "Two"], "Edition": None}
    with webui_events.field_prompt("Music release", summary, focus="Album", hint="The album title.", actions=[("", "Skip")], placeholder="Album"):
        webui_events.prompt_open("text", "Enter album title (leave blank to skip): ")

    (opened,) = _events(capsys.readouterr().out)
    assert opened["context"] == {
        "kind": "field",
        "title": "Music release",
        # Empty values are left out, except the one being asked for.
        "summary": {"Artist": "Fictional Band", "Album": "", "Year": "2020", "Tracks": "One, Two"},
        "actions": [["", "Skip"]],
        "focus": "Album",
        "hint": "The album title.",
        "placeholder": "Album",
    }


def test_numbered_options_carry_a_hint_and_only_country_flag_codes(gui_env, capsys) -> None:
    details = [{"meta": "Country: Fictionland", "flag": "us"}, {"flag": "../evil"}, {"flag": "gb-eng"}]
    with webui_events.numbered_options(["One", "Two", "Three"], details=details, hint="Why this matters.\nWhat a and n do."):
        webui_events.prompt_open("text", "Pick one:")

    (opened,) = _events(capsys.readouterr().out)
    assert [detail["flag"] for detail in opened["context"]["details"]] == ["us", "", ""]
    assert opened["context"]["hint"] == "Why this matters.\nWhat a and n do."
