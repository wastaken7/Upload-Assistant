"""Upload form previews and edits offered on the Web UI's "Is this correct?" prompt."""

from __future__ import annotations

import json
from typing import Any

import pytest

from src import payload_preview, webui_events
from src.console import PromptBlockedError, check_prompt_allowed, prompts_blocked
from src.meta import Meta
from src.payload_preview import Later, Spec, accept_edits, apply_payload_edits, describe, gui_payloads
from src.trackers.UNIT3D import UNIT3D
from src.uphelper import UploadHelper

SPECS: dict[str, Spec] = {
    "name": payload_preview.text("Name"),
    "type_id": payload_preview.choice("Type", {"REMUX": "2", "WEBDL": "4", "WEBRIP": "5", "ENCODE": "3", "DVDRIP": "3"}, by_label=True),
    "anonymous": payload_preview.flag("Anonymous"),
    "internal": payload_preview.flag("Internal", on="on", off=None),
    "tmdb": payload_preview.number("TMDB ID"),
}


def fields(preview: payload_preview.TrackerPreview) -> dict[str, payload_preview.PayloadField]:
    return {item.key: item for item in preview.fields}


def test_describe_labels_known_fields_and_hides_credentials() -> None:
    data = {
        "name": "Fictional Show S01 1080p WEB-DL-NOGRP",
        "type_id": "3",
        "anonymous": "0",
        "tmdb": 4321,
        "keywords": "drama, mystery",
        "auth": "secret",
        "api_key": "secret",
        "announcekey": "secret",
        "csrfToken": "secret",
        "mediainfo": "General\nFormat : Matroska",
        "tags[]": ["drama", "mystery"],
        "screenshots": Later("Uploaded after this question"),
    }
    preview = describe("FAKE", data, SPECS, deferred={"description": payload_preview.DESCRIPTION_NOTE})
    by_key = fields(preview)

    assert preview.name == "Fictional Show S01 1080p WEB-DL-NOGRP"
    assert not {"auth", "api_key", "announcekey", "csrfToken"} & set(by_key)
    # A field the tracker gave no spec is shown, never typed into: on the site it may be a drop-down.
    assert by_key["keywords"].kind == "readonly"
    assert by_key["type_id"].kind == "choice"
    # Labels that share an ID are one option.
    assert ("3", "ENCODE / DVDRIP") in by_key["type_id"].choices
    assert by_key["anonymous"].kind == "flag"
    assert by_key["tmdb"].kind == "text" and by_key["tmdb"].numeric
    assert by_key["mediainfo"].kind == "readonly"
    assert by_key["tags[]"].kind == "readonly"
    assert by_key["screenshots"].kind == "deferred"
    assert by_key["description"].kind == "deferred"
    # An unchecked checkbox that is left out of the form can still be ticked.
    assert by_key["internal"].kind == "flag" and by_key["internal"].value is None


def test_describe_keeps_a_value_missing_from_the_drop_down() -> None:
    preview = describe("FAKE", {"type_id": "99"}, SPECS)

    assert fields(preview)["type_id"].choices[0] == ("99", "99")


def test_boolean_strings_are_shown_as_flags() -> None:
    preview = describe("FAKE", {"stream": "False"}, {"stream": payload_preview.flag("Stream")})

    item = fields(preview)["stream"]
    assert (item.kind, item.on, item.off) == ("flag", "True", "False")


def test_gui_payloads_share_drop_down_lists_between_trackers() -> None:
    previews = [describe(tracker, {"type_id": "4"}, SPECS) for tracker in ("AAA", "BBB")]

    items, tables, notice = gui_payloads(previews)

    assert notice == ""
    assert len(tables) == 1
    assert items[0]["fields"][0]["choices"] == items[1]["fields"][0]["choices"] == tables[0]["id"]
    assert items[0]["fields"][0]["display"] == "WEBDL (4)"


def test_gui_payloads_drop_the_longest_lists_first(monkeypatch: pytest.MonkeyPatch) -> None:
    long_list = payload_preview.choice("Distributor", [(str(index), f"Distributor {index}") for index in range(400)])
    preview = describe("AAA", {"type_id": "4", "distributor_id": "7"}, {**SPECS, "distributor_id": long_list})
    monkeypatch.setattr(payload_preview, "GUI_BUDGET", 3000)

    items, tables, notice = gui_payloads([preview])

    by_key = {item["key"]: item for item in items[0]["fields"]}
    assert "choices" in by_key["type_id"]
    assert "choices" not in by_key["distributor_id"]
    assert len(tables) == 1
    assert notice


def test_gui_payloads_leave_out_previews_that_do_not_fit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(payload_preview, "GUI_BUDGET", 10)

    assert gui_payloads([describe("AAA", {"name": "Fictional"}, SPECS)]) == ([], [], "The upload data is too large to show here.")


def test_accept_edits_keeps_only_valid_changes_with_their_form_types() -> None:
    preview = describe("FAKE", {"name": "Old Name", "type_id": "4", "anonymous": "0", "tmdb": 4321, "mediainfo": "General\nFormat : Matroska"}, SPECS)
    meta = Meta()

    changes = accept_edits(
        meta,
        {"FAKE": preview},
        {
            "FAKE": {
                "name": "  New Name  ",
                "type_id": "2",
                "anonymous": True,
                "tmdb": "1234",
                "internal": True,
                "mediainfo": "edited",
                "unknown": "x",
            },
            "OTHER": {"name": "x"},
        },
    )

    assert meta.payload_edits == {"FAKE": {"name": "New Name", "type_id": "2", "anonymous": "1", "tmdb": 1234, "internal": "on"}}
    assert "FAKE Type: WEBDL (4) → REMUX (2)" in changes


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("name", "two\nlines"),
        ("name", "x" * 256),
        ("name", "   "),
        ("tmdb", "12a"),
        ("type_id", "77"),
        ("anonymous", "1"),
        ("name", 5),
    ],
)
def test_accept_edits_refuses_invalid_values(key: str, value: Any) -> None:
    preview = describe("FAKE", {"name": "Old Name", "type_id": "4", "anonymous": "0", "tmdb": 4321}, SPECS)
    meta = Meta()

    assert accept_edits(meta, {"FAKE": preview}, {"FAKE": {key: value}}) == []
    assert meta.payload_edits == {}


def test_accept_edits_ignores_unchanged_values_and_bad_shapes() -> None:
    preview = describe("FAKE", {"name": "Same"}, SPECS)
    meta = Meta()

    assert accept_edits(meta, {"FAKE": preview}, {"FAKE": {"name": "Same"}}) == []
    assert accept_edits(meta, {"FAKE": preview}, ["not", "a", "dict"]) == []
    assert meta.payload_edits == {}


def test_apply_payload_edits_sets_values_and_removes_unticked_checkboxes() -> None:
    meta = Meta()
    meta.payload_edits = {"FAKE": {"name": "Edited", "internal": None}}
    data = {"name": "Original", "internal": "on", "type_id": "4"}

    assert apply_payload_edits(meta, "FAKE", data) == {"name": "Edited", "type_id": "4"}
    assert apply_payload_edits(meta, "OTHER", {"name": "Untouched"}) == {"name": "Untouched"}


def test_blocked_prompts_are_refused_before_they_are_asked() -> None:
    check_prompt_allowed()
    with prompts_blocked(), pytest.raises(PromptBlockedError):
        check_prompt_allowed()
    check_prompt_allowed()


@pytest.mark.asyncio
async def test_unit3d_preview_skips_the_description_and_reports() -> None:
    tracker = UNIT3D({"DEFAULT": {}, "TRACKERS": {"FAKE": {}}}, tracker_name="FAKE")

    async def refuse(meta: Meta) -> dict[str, str]:
        raise AssertionError("not built in a preview")

    tracker.get_description = refuse  # type: ignore[method-assign]
    tracker.get_mediainfo = refuse  # type: ignore[method-assign]
    meta = Meta(category="MOVIE", type="WEBDL", resolution="1080p", name="Fictional Film 2001 1080p WEB-DL-NOGRP", tmdb=4321)

    preview = await tracker.get_payload_preview(meta)

    by_key = fields(preview)
    assert preview.name == "Fictional Film 2001 1080p WEB-DL-NOGRP"
    assert (by_key["type_id"].kind, by_key["type_id"].value) == ("choice", "4")
    assert by_key["resolution_id"].kind == "choice"
    assert by_key["description"].kind == by_key["mediainfo"].kind == "deferred"


class FakeTracker:
    tracker = "FAKE"

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    async def get_name(self, meta: Meta) -> dict[str, str]:
        raise AssertionError("the preview already has the name")

    async def get_payload_preview(self, meta: Meta) -> payload_preview.TrackerPreview:
        assert meta.tracker_status["FAKE"] == {}
        return describe("FAKE", {"name": "Fictional Film 2001", "type_id": "4"}, SPECS)


class AskingTracker(FakeTracker):
    tracker = "ASKS"

    async def get_name(self, meta: Meta) -> dict[str, str]:
        return {"name": "Asked Name"}

    async def get_payload_preview(self, meta: Meta) -> payload_preview.TrackerPreview:
        check_prompt_allowed()
        raise AssertionError("unreachable")


@pytest.fixture
def gui(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(webui_events.GUI_EVENTS_ENV, "1")
    monkeypatch.setenv(webui_events.GUI_EVENT_NONCE_ENV, "payload-preview-test")
    monkeypatch.setattr(webui_events, "_current_item", None)


def prompt_context(capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    prefix = webui_events.event_prefix("payload-preview-test")
    events = [json.loads(line[len(prefix) :]) for line in capsys.readouterr().out.splitlines() if line.startswith(prefix)]
    return next(event["context"] for event in events if event["kind"] == "prompt" and event["action"] == "open")


@pytest.mark.usefixtures("gui")
@pytest.mark.asyncio
async def test_gui_confirmation_shows_previews_and_keeps_the_edits(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    answer = 'yes {"anon": true, "payload_edits": {"FAKE": {"type_id": "2", "name": "Fictional Film 2001 REMUX"}, "ASKS": {"name": "x"}}}'
    monkeypatch.setattr("src.uphelper.cli_ui.read_input", lambda: answer)
    config = {"DEFAULT": {"sfx_on_prompt": False}, "TRACKERS": {"FAKE": {}, "ASKS": {}}}
    helper = UploadHelper(config)
    helper.tracker_class_map = {"FAKE": FakeTracker, "ASKS": AskingTracker}
    meta = Meta(category="MOVIE", name="Fictional Film 2001", trackers=["FAKE", "ASKS"])
    meta.payload_edits = {"FAKE": {"name": "left from an earlier answer"}}

    assert await helper.get_confirmation(meta) is True

    context = prompt_context(capsys)
    assert [preview["tracker"] for preview in context["payloads"]] == ["FAKE"]
    # A tracker whose preview needed a question is named, not left out silently.
    assert "ASKS" in context["payload_notice"]
    assert context["release_names"] == {"FAKE": "Fictional Film 2001", "ASKS": "Asked Name"}
    assert context["payload_choices"][0]["choices"][0] == ["2", "REMUX"]
    assert meta.anon is True
    assert meta.payload_edits == {"FAKE": {"type_id": "2", "name": "Fictional Film 2001 REMUX"}}
    # The temporary status entry made for the preview is gone again.
    assert meta.tracker_status == {}


@pytest.mark.usefixtures("gui")
@pytest.mark.asyncio
async def test_gui_confirmation_drops_edits_on_no(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.uphelper.cli_ui.read_input", lambda: 'no {"payload_edits": {"FAKE": {"type_id": "2"}}}')
    helper = UploadHelper({"DEFAULT": {"sfx_on_prompt": False}, "TRACKERS": {"FAKE": {}}})
    helper.tracker_class_map = {"FAKE": FakeTracker}
    meta = Meta(category="MOVIE", name="Fictional Film 2001", trackers=["FAKE"])

    assert await helper.get_confirmation(meta) is False
    assert meta.payload_edits == {}


@pytest.mark.asyncio
async def test_a_getter_that_ignores_mapping_only_is_not_a_drop_down() -> None:
    async def ignores(meta: Meta, mapping_only: bool = False) -> dict[str, str]:
        return {"type_id": "4"}

    async def maps(meta: Meta, mapping_only: bool = False) -> dict[str, str]:
        return {"WEBDL": "4", "REMUX": "2"} if mapping_only else {"type_id": "4"}

    assert await payload_preview.mapping_choice("Type", ignores, Meta(), "type_id") is None
    spec = await payload_preview.mapping_choice("Type", maps, Meta(), "type_id")
    assert spec is not None and spec.choices == (("4", "WEBDL"), ("2", "REMUX"))


def test_a_flag_or_choice_with_an_unexpected_value_is_read_only() -> None:
    preview = describe("FAKE", {"anonymous": "maybe", "type_id": ["4"]}, SPECS)

    assert fields(preview)["anonymous"].kind == fields(preview)["type_id"].kind == "readonly"


def fictional_category(meta: Meta) -> int:
    movies = 401
    tv_series = 402
    unrelated = 99
    del unrelated
    if meta.category == "TV":
        return tv_series
    if "2160" in str(meta.resolution) or "4k" in str(meta.resolution):
        return 6
    codec = {"x264": 1, "x265": 2}.get(str(meta.video_encode), 0)
    if codec:
        return codec
    return movies


def test_code_options_lists_what_a_getter_can_return() -> None:
    options = dict(payload_preview.code_options(fictional_category))

    assert options == {1: "x264", 2: "x265", 6: "2160 / 4k", 401: "movies", 402: "tv series"}


@pytest.mark.asyncio
async def test_unless_asked_leaves_a_refused_question_for_later() -> None:
    async def asks() -> str:
        check_prompt_allowed()
        return "answer"

    with prompts_blocked():
        later = await payload_preview.unless_asked(asks())
    assert isinstance(later, Later) and later.note == payload_preview.ASKED_NOTE
    assert await payload_preview.unless_asked(asks()) == "answer"


def test_fields_carry_the_role_the_web_ui_warns_about() -> None:
    specs = {
        **SPECS,
        "type": payload_preview.choice("Type", [("Feature Film", "Feature Film")], role="none"),
        "title": payload_preview.text("Título", role="title"),
    }
    preview = describe("FAKE", {"name": "Fictional", "tmdb": 4321, "type": "Feature Film", "title": "Fictional", "keywords": "x"}, specs)
    roles = {item.key: item.role for item in preview.fields}

    assert roles["name"] == "name"
    assert roles["tmdb"] == "external_id"
    assert roles["title"] == "title"
    # "type" usually means the category; this tracker's spec says it does not.
    assert roles["type"] == ""
    items = {item["key"]: item for item in gui_payloads([preview])[0][0]["fields"]}
    assert items["tmdb"]["role"] == "external_id"
    # Only editable fields need a role in the Web UI.
    assert "role" not in items["keywords"]


@pytest.mark.asyncio
async def test_a_language_question_refused_in_a_preview_leaves_no_half_found_languages(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.languages import languages_manager

    async def parsed(meta: Meta) -> dict[str, Any]:
        return {"audio": [{"language": "English"}], "text": [{"language": "English"}, {"title": "Untagged"}]}

    monkeypatch.setattr(languages_manager, "parsed_mediainfo", parsed)
    meta = Meta(category="MOVIE", is_disc="", unattended=False)

    with prompts_blocked(), pytest.raises(PromptBlockedError):
        await languages_manager.process_desc_language(meta, tracker="FAKE")

    # The upload finds the languages again and asks about the untagged track.
    assert not meta.audio_languages and not meta.subtitle_languages
    assert not meta.language_checked


class StatusWritingTracker(FakeTracker):
    async def get_payload_preview(self, meta: Meta) -> payload_preview.TrackerPreview:
        meta.tracker_status["FAKE"]["skip_upload"] = True
        return describe("FAKE", {"name": "Fictional Film 2001"}, SPECS)


@pytest.mark.asyncio
async def test_a_preview_leaves_the_tracker_status_as_it_found_it() -> None:
    tracker = StatusWritingTracker({})
    meta = Meta(category="MOVIE")
    assert await UploadHelper._payload_preview(tracker, "FAKE", meta) is not None
    assert meta.tracker_status == {}

    meta.tracker_status["FAKE"] = {"status_message": "kept"}
    assert await UploadHelper._payload_preview(tracker, "FAKE", meta) is not None
    assert meta.tracker_status == {"FAKE": {"status_message": "kept"}}
