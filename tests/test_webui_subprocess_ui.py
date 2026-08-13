# ruff: noqa: S101
import subprocess
import sys

import web_ui.server as server


def test_subprocess_yes_no_prompt_is_classified_for_dedicated_buttons() -> None:
    assert server._subprocess_prompt_type(":: Continue? (y/N)\n") == "yes_no"
    assert server._subprocess_prompt_type("\x1b[1;31mContinue? (Y/n)\x1b[0m") == "yes_no"
    assert server._subprocess_prompt_type("Enter a new title:") == "text"


def test_webui_child_environment_overrides_no_color(monkeypatch) -> None:
    monkeypatch.setenv("NO_COLOR", "1")

    env = server._webui_subprocess_env()
    result = subprocess.run(
        [sys.executable, "-u", "-c", "from src.console import console; console.print('[red]color[/red]')"],
        text=True,
        capture_output=True,
        env=env,
        check=True,
    )

    assert "NO_COLOR" not in env
    assert "\x1b[" in result.stdout
    assert "31m" in result.stdout
