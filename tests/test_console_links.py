# ruff: noqa: S101
import asyncio
from io import StringIO

from rich.console import Console

from src.console import ansi_to_html, prompt_in_thread


def test_ansi_to_html_preserves_osc8_hyperlinks() -> None:
    stream = StringIO()
    Console(file=stream, force_terminal=True, color_system="truecolor", legacy_windows=False).print("[link=https://example.test]link[/link]")

    html = ansi_to_html(stream.getvalue())

    assert '<a href="https://example.test">link</a>' in html


def test_prompt_in_thread_returns_prompt_result() -> None:
    async def ask() -> str:
        return await prompt_in_thread(lambda prefix, value: f"{prefix}{value}", "answer-", 42)

    assert asyncio.run(ask()) == "answer-42"
