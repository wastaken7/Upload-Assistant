# ruff: noqa: S101
import re
from pathlib import Path

from src.args import WEBUI_UNSUPPORTED_OPTIONS, Args, cli_argument_catalog
from src.meta import Meta
from web_ui import server


def test_webui_catalog_uses_cli_flags_and_help() -> None:
    catalog = {item["label"]: item for item in cli_argument_catalog()}
    _, parser, _ = Args({"DEFAULT": {"screens": 1}}).parse(["--webui"], Meta())

    for action in parser._actions:
        for option in action.option_strings:
            if option.startswith("--") and option not in WEBUI_UNSUPPORTED_OPTIONS:
                assert option in catalog
                if action.help != "==SUPPRESS==":
                    assert catalog[option]["description"] == action.help

    assert not WEBUI_UNSUPPORTED_OPTIONS.intersection(catalog)
    assert catalog["--developer"]["description"] == "GAME developer (overrides auto-detected value)"
    assert catalog["--tracker-id"]["placeholder"] == "TRACKER=ID|URL"
    assert "Example: --tracker-id AITHER=1234" in catalog["--tracker-id"]["description"]
    assert "--overview" in catalog
    assert "--genres" in catalog
    assert "--game-overview" not in catalog
    assert "--book-genres" not in catalog


def test_webui_grouped_flags_exist_in_cli() -> None:
    source = (Path(__file__).resolve().parents[1] / "web_ui" / "static" / "js" / "app.js").read_text(encoding="utf-8")
    categories = source.split("let argumentCategories = [", 1)[1].split("const cliArguments =", 1)[0]
    grouped_flags = set(re.findall(r'label: "(--[\w-]+)"', categories))
    available_flags = {item["label"] for item in cli_argument_catalog()}

    assert grouped_flags <= available_flags
    assert "--tracker-id" in grouped_flags
    assert "--ptp" not in grouped_flags
    assert "Other CLI options" in source
    for item in re.findall(r'\{[^{}]*label: "(--[^\"]+)"[^{}]*\}', categories):
        if item not in {"--unattended", "--unattended_confirm"}:
            block = re.search(r'\{[^{}]*label: "' + re.escape(item) + r'"[^{}]*\}', categories)
            assert block is not None and "description:" not in block.group()


def test_webui_template_receives_cli_catalog() -> None:
    with server.app.test_request_context("/"):
        html = server.index()

    assert "window.UA_CLI_ARGUMENTS = [{" in html
    assert '"label": "--developer"' in html
    assert '"label": "--tracker-id"' in html
