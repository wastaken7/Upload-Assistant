"""GUI debug details reflect parsed skip flags without exposing unrelated settings."""
import json
from pathlib import Path

import pytest

from src import webui_events
from src.args import Args
from src.meta import Meta
from src.uphelper import UploadHelper


@pytest.fixture
def gui(monkeypatch):
    """Enable isolated GUI events without a WebUI session or real uploads."""
    monkeypatch.setenv(webui_events.GUI_EVENTS_ENV, "1")
    monkeypatch.setenv(webui_events.GUI_EVENT_NONCE_ENV, "debug-details-test")
    monkeypatch.setattr(webui_events, "_current_item", None)


def item_events(capsys):
    """Read item updates while ignoring ordinary console output."""
    prefix = webui_events.event_prefix("debug-details-test")
    return [event for line in capsys.readouterr().out.splitlines() if line.startswith(prefix) and (event := json.loads(line[len(prefix):]))["kind"] == "item"]


@pytest.mark.parametrize("no_seed", [False, True])
@pytest.mark.parametrize("skip_images", [False, True])
def test_parsed_skip_flags_reach_the_debug_details(gui, tmp_path, capsys, no_seed, skip_images):
    """Single-hyphen skip aliases retain their actual enabled/disabled values."""
    flags = ["--debug", *(["-ns"] if no_seed else []), *(["-siu"] if skip_images else [])]
    meta, _, _ = Args({"DEFAULT": {"screens": 1}, "TRACKERS": {}}).parse([str(tmp_path), *flags], Meta())
    webui_events.begin_item(str(tmp_path), 1, 1)
    webui_events.update_item(run_options=meta)
    options = item_events(capsys)[-1]["run_options"]
    assert options["debug"] is True
    assert options["no_seed"] is no_seed
    assert options["skip_imghost_upload"] is skip_images


@pytest.mark.asyncio
async def test_unattended_confirmation_refreshes_options_and_prep_folder(gui, tmp_path, capsys):
    """Resolved preparation details are available even without a confirmation prompt."""
    webui_events.begin_item("Example.mkv", 1, 1)
    webui_events.update_item(personal_release=True, run_options=Meta(debug=True))
    meta = Meta(category="MOVIE", unattended=True, debug=True, personalrelease=True, no_seed=True,
                skip_imghost_upload=True, nohash=True, ffdebug=True, base_dir=str(tmp_path), uuid="prepared-release")
    assert await UploadHelper({"DEFAULT": {}}).get_confirmation(meta)
    first, early, prepared = item_events(capsys)
    assert "run_options" not in first
    assert early["run_options"]["debug"] is True
    assert early["run_options"]["prep_directory"] == ""
    assert prepared["personal_release"] is True
    assert prepared["run_options"]["prep_directory"].endswith(str(Path("tmp") / "prepared-release"))
    assert all(prepared["run_options"][key] is True for key in ("no_seed", "skip_imghost_upload", "nohash", "ffdebug"))


def test_run_options_are_whitelisted_and_reset_for_the_next_release(gui, capsys):
    """Do not forward API keys or retain debug options on the next queue item."""
    webui_events.begin_item("First.mkv", 1, 2)
    webui_events.update_item(personal_release=True, run_options={"debug": True, "client": "none", "api_key": "secret-value", "category": "MOVIE"})
    webui_events.update_item(personal_release=False)
    webui_events.begin_item("Second.mkv", 2, 2)
    _, updated, corrected, second = item_events(capsys)
    assert updated["run_options"]["client_disabled"] is True
    assert "secret-value" not in json.dumps(updated)
    assert set(updated["run_options"]) == {"debug", "no_seed", "skip_imghost_upload", "nohash", "ffdebug", "client_disabled", "category", "prep_directory"}
    assert corrected["run_options"] == updated["run_options"]
    assert corrected["personal_release"] is False
    assert "run_options" not in second


def test_run_options_do_no_work_outside_gui(monkeypatch, capsys):
    """Ordinary CLI runs neither emit details nor read the supplied metadata."""
    monkeypatch.delenv(webui_events.GUI_EVENTS_ENV, raising=False)

    class Unreadable(dict):
        """Detect accidental metadata reads outside GUI mode."""
        def get(self, *args, **kwargs):
            """Fail if the no-op helper inspects metadata."""
            raise AssertionError("metadata read outside GUI mode")

    webui_events.update_item(run_options=Unreadable())
    assert capsys.readouterr().out == ""
