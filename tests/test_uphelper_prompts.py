# ruff: noqa: S101
import asyncio
import threading

import pytest

from src.uphelper import UploadHelper


@pytest.mark.asyncio
async def test_prompt_yes_no_serializes_concurrent_prompts(monkeypatch: pytest.MonkeyPatch) -> None:
    first_started = threading.Event()
    release_first = threading.Event()
    second_started = threading.Event()

    def ask_yes_no(question: str, default: bool = False) -> bool:
        if question == "first":
            first_started.set()
            assert release_first.wait(timeout=1)
        else:
            second_started.set()
        return default

    monkeypatch.setattr("src.uphelper.cli_ui.ask_yes_no", ask_yes_no)
    helper = UploadHelper({"DEFAULT": {}})

    first = asyncio.create_task(helper.prompt_yes_no("first"))
    second = asyncio.create_task(helper.prompt_yes_no("second", default=True))

    assert await asyncio.to_thread(first_started.wait, 1)
    await asyncio.sleep(0)
    assert not second_started.is_set()

    release_first.set()
    assert await asyncio.gather(first, second) == [False, True]
    assert second_started.is_set()


@pytest.mark.asyncio
async def test_bdinfo_comparison_prompt_uses_rich_markup(monkeypatch: pytest.MonkeyPatch) -> None:
    question: str | None = None

    async def prompt_yes_no(value: str, *, default: bool = False) -> bool:
        nonlocal question
        question = value
        return False

    monkeypatch.setattr("src.uphelper.has_bdinfo_content", lambda _entry: True)
    helper = UploadHelper({"DEFAULT": {}})
    monkeypatch.setattr(helper, "prompt_yes_no", prompt_yes_no)

    await helper.ask_bdinfo_comparison({}, [{}], "AITHER")

    assert question == "[bold magenta]Found BDInfo content in potential duplicates.[/bold magenta] Perform a comparison?"
    assert "\033" not in question
