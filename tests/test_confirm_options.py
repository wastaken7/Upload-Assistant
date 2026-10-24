# ruff: noqa: S101
"""Run options offered on the Web UI's "Is this correct?" prompt."""

import json
from typing import Any

import pytest

from src import confirm_options, webui_events
from src.meta import Meta
from src.uphelper import UploadHelper


def keys(options: list[dict]) -> list[str]:
    return [option["key"] for option in options]


def by_key(options: list[dict], key: str) -> dict:
    return next(option for option in options if option["key"] == key)


def test_media_options_follow_the_release() -> None:
    sdr = confirm_options.available(Meta(category="MOVIE"), {"DEFAULT": {}})
    dv = confirm_options.available(Meta(category="MOVIE", hdr="DV HDR10+"), {"DEFAULT": {}})
    dvd = confirm_options.available(Meta(category="MOVIE", is_disc="DVD"), {"DEFAULT": {}})
    game = confirm_options.available(Meta(category="GAME"), {"DEFAULT": {}})

    assert "dynamic_hdr_plot" not in keys(sdr)
    assert by_key(dv, "dynamic_hdr_plot")["value"] is False
    assert "disc_menus" not in keys(sdr)
    assert {"disc_menus", "extras"} <= set(keys(dvd))
    assert "audio_spectrogram" not in keys(game)
    assert "personalrelease" not in keys(game)


def test_moderation_queue_names_trackers_that_already_enable_it() -> None:
    config = {"DEFAULT": {}, "TRACKERS": {"AITHER": {"modq": True}, "BLU": {"modq": False}}}
    option = by_key(confirm_options.available(Meta(category="MOVIE", trackers=["AITHER", "BLU"]), config), "modq")

    assert option["hint"] == "Already on for AITHER in your config"
    # The setting covers only AITHER, so the queue can still be turned on for BLU.
    assert option["value"] is False
    assert "locked" not in option


def test_tracker_specific_options_need_a_tracker_that_reads_them() -> None:
    without = confirm_options.available(Meta(category="MOVIE", trackers=["AITHER"]), {"DEFAULT": {}})
    with_them = confirm_options.available(Meta(category="MOVIE", trackers=["LST", "GREATPOSTERWALL"]), {"DEFAULT": {}})

    assert not {"draft", "extras", "sfx_subtitles"} & set(keys(without))
    assert {"draft", "extras", "sfx_subtitles"} <= set(keys(with_them))


def test_options_enabled_in_the_config_are_locked() -> None:
    config = {"DEFAULT": {"add_dynamic_hdr_plot": True, "add_audio_spectrogram": True}}
    options = confirm_options.available(Meta(category="MOVIE", hdr="DV"), config)

    assert by_key(options, "dynamic_hdr_plot") == {**by_key(options, "dynamic_hdr_plot"), "value": True, "locked": "Enabled in your config"}
    assert by_key(options, "audio_spectrogram")["locked"]
    # A flag passed on the command line can still be turned off.
    assert "locked" not in by_key(confirm_options.available(Meta(category="MOVIE", hdr="DV", dynamic_hdr_plot=True), {"DEFAULT": {}}), "dynamic_hdr_plot")


@pytest.mark.parametrize(
    "config",
    [
        {"DEFAULT": {"add_dynamic_hdr_plot": True}},
        {"DEFAULT": {}, "TRACKERS": {"AITHER": {"add_dynamic_hdr_plot": True}}},
    ],
)
def test_hdr_plots_stay_locked_when_the_flag_and_the_config_both_enable_them(config: dict[str, Any]) -> None:
    meta = Meta(category="MOVIE", hdr="DV", dynamic_hdr_plot=True, trackers=["AITHER"])
    option = by_key(confirm_options.available(meta, config), "dynamic_hdr_plot")

    assert option["value"] is True
    assert option["locked"] == "Enabled in your config"


def test_hdr_plots_are_offered_for_a_spelled_out_dolby_vision() -> None:
    assert "dynamic_hdr_plot" in keys(confirm_options.available(Meta(category="MOVIE", hdr="Dolby Vision"), {"DEFAULT": {}}))


def test_image_host_choice_lists_only_configured_hosts() -> None:
    one = confirm_options.available(Meta(category="MOVIE"), {"DEFAULT": {"img_host_1": "imgbox"}})
    two = confirm_options.available(Meta(category="MOVIE", imghost="imgbox"), {"DEFAULT": {"img_host_1": "imgbox", "img_host_2": "pixhost"}})

    assert "imghost" not in keys(one)
    assert by_key(two, "imghost")["choices"] == ["imgbox", "pixhost"]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("yes", (True, {})),
        ("n", (False, {})),
        ("", (False, {})),
        ('yes {"anon":true}', (True, {"anon": True})),
        ("maybe", (None, {})),
        ("yes {not json", (None, {})),
        ("yes [1]", (None, {})),
    ],
)
def test_parse_answer(text: str, expected: tuple) -> None:
    assert confirm_options.parse_answer(text, default=False) == expected


def test_apply_changes_only_offered_unlocked_values_of_the_right_type() -> None:
    meta = Meta(category="MOVIE", is_disc="DVD", hdr="DV", imghost="imgbox")
    config = {"DEFAULT": {"img_host_1": "imgbox", "img_host_2": "pixhost", "add_audio_spectrogram": True}}
    options = confirm_options.available(meta, config)

    changed = confirm_options.apply(
        meta,
        options,
        {
            "anon": True,
            "no_seed": "yes",
            "disc_menus": True,
            "dynamic_hdr_plot": True,
            "audio_spectrogram": False,
            "imghost": "pixhost",
            "debug": True,
            "draft": True,
        },
    )

    assert meta.anon is True
    assert meta.no_seed is False
    assert meta.path_to_menu_screenshots == "auto"
    assert meta.dynamic_hdr_plot is True
    assert meta.audio_spectrogram is None
    assert meta.imghost == "pixhost"
    assert meta.imghost_from_cli is True
    assert meta.debug is False
    assert meta.draft is None
    assert len(changed) == 4


def test_apply_rejects_an_image_host_that_was_not_offered() -> None:
    meta = Meta(category="MOVIE", imghost="imgbox")
    options = confirm_options.available(meta, {"DEFAULT": {"img_host_1": "imgbox", "img_host_2": "pixhost"}})

    assert confirm_options.apply(meta, options, {"imghost": "catbox"}) == []
    assert meta.imghost == "imgbox"


@pytest.fixture
def gui(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(webui_events.GUI_EVENTS_ENV, "1")
    monkeypatch.setenv(webui_events.GUI_EVENT_NONCE_ENV, "confirm-options-test")
    monkeypatch.setattr(webui_events, "_current_item", None)


def prompt_events(capsys: pytest.CaptureFixture[str]) -> list[dict]:
    prefix = webui_events.event_prefix("confirm-options-test")
    return [event for line in capsys.readouterr().out.splitlines() if line.startswith(prefix) and (event := json.loads(line[len(prefix) :]))["kind"] == "prompt"]


@pytest.mark.usefixtures("gui")
@pytest.mark.parametrize(("answer", "confirmed", "anon"), [('yes {"anon":true,"no_seed":true}', True, True), ('no {"anon":true}', False, False)])
@pytest.mark.asyncio
async def test_gui_confirmation_applies_options_only_on_yes(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], answer: str, confirmed: bool, anon: bool
) -> None:
    monkeypatch.setattr("src.uphelper.cli_ui.read_input", lambda: answer)
    meta = Meta(category="MOVIE", hdr="DV")

    assert await UploadHelper({"DEFAULT": {"sfx_on_prompt": False}, "TRACKERS": {}}).get_confirmation(meta) is confirmed

    assert meta.anon is anon
    assert meta.no_seed is anon
    opened = next(event for event in prompt_events(capsys) if event["action"] == "open")
    assert opened["type"] == "yes_no"
    assert "dynamic_hdr_plot" in keys(opened["context"]["run_options"])


@pytest.mark.asyncio
@pytest.mark.usefixtures("gui")
async def test_gui_confirmation_asks_again_after_an_invalid_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    answers = iter(["yes {broken", "y"])
    monkeypatch.setattr("src.uphelper.cli_ui.read_input", lambda: next(answers))

    assert await UploadHelper({"DEFAULT": {"sfx_on_prompt": False}, "TRACKERS": {}}).get_confirmation(Meta(category="MOVIE")) is True


@pytest.mark.asyncio
async def test_terminal_confirmation_keeps_the_plain_yes_no_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(webui_events.GUI_EVENTS_ENV, raising=False)
    questions: list[str] = []

    def ask_yes_no(question: str, default: bool = False) -> bool:
        del default
        questions.append(question)
        return True

    monkeypatch.setattr("src.uphelper.cli_ui.ask_yes_no", ask_yes_no)
    assert await UploadHelper({"DEFAULT": {"sfx_on_prompt": False}, "TRACKERS": {}}).get_confirmation(Meta(category="MOVIE")) is True
    assert questions == ["Is this correct?"]
