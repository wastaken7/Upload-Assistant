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
    layout = source.split("const argumentSections = [", 1)[1].split("const argumentBuilder =", 1)[0]
    grouped_flags = set(re.findall(r'"(--[\w-]+)', layout))
    available_flags = {item["label"] for item in cli_argument_catalog()}

    assert grouped_flags <= available_flags
    assert "--tracker-id" in grouped_flags
    assert "--ptp" not in grouped_flags
    assert "Other CLI options" in source
    # Help text comes from the parser; only these hidden options carry their own.
    described = set(re.findall(r'flag: "(--[\w-]+)",\s*description:', layout))
    assert described == {"--unattended", "--unattended_confirm"}


def test_webui_catalog_describes_value_shapes() -> None:
    catalog = {item["label"]: item for item in cli_argument_catalog()}

    assert catalog["--debug"]["kind"] == "flag"
    assert catalog["--category"]["kind"] == "choice"
    assert catalog["--category"]["choices"] == ["movie", "tv", "sports", "fanres", "book", "game", "music", "xxx"]
    assert "-c" in catalog["--category"]["aliases"]
    assert catalog["--tag"]["kind"] == "multi"
    assert catalog["--tracker-id"]["kind"] == "append"
    assert catalog["--tmdb"]["kind"] == "value"
    assert "--platforms" in catalog["--platform"]["aliases"]
    assert catalog["--music-enrich"]["conflicts"] == ["--no-music-enrich"]
    assert catalog["--no-imdb"]["conflicts"] == ["--imdb"]
    assert "choices" not in catalog["--tmdb"]


def test_webui_template_receives_cli_catalog() -> None:
    with server.app.test_request_context("/"):
        html = server.index()

    assert "window.UA_CLI_ARGUMENTS = [{" in html
    assert '"label": "--developer"' in html
    assert '"label": "--tracker-id"' in html


def test_webui_catalog_marks_lowercased_choices() -> None:
    catalog = {item["label"]: item for item in cli_argument_catalog()}

    for option in ("--platform", "--game-subcategory", "--music-media", "--music-release-type"):
        assert catalog[option]["case_insensitive"] is True
    assert "case_insensitive" not in catalog["--imghost"]
    assert "case_insensitive" not in catalog["--category"]
