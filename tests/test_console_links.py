# ruff: noqa: S101
from io import StringIO

from rich.console import Console

from src.console import ansi_to_html


def test_ansi_to_html_preserves_osc8_hyperlinks() -> None:
    stream = StringIO()
    Console(file=stream, force_terminal=True, color_system="truecolor", legacy_windows=False).print("[link=https://example.test]link[/link]")

    html = ansi_to_html(stream.getvalue())

    assert '<a href="https://example.test">link</a>' in html
