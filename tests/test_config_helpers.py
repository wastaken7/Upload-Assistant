# ruff: noqa: S101

from rich.text import Text

from src.config_helpers import format_terminal_link, parse_bool, should_embed_links


def test_parse_bool_does_not_enable_false_or_invalid_strings() -> None:
    assert parse_bool(True)
    assert parse_bool("true")
    assert not parse_bool(False)
    assert not parse_bool("False")
    assert not parse_bool("invalid")


def test_embed_links_controls_terminal_link_formatting() -> None:
    assert should_embed_links({"embed_links": True})
    assert format_terminal_link("Open", "https://example.test", {"embed_links": True}) == "[link=https://example.test]Open[/link]"
    assert format_terminal_link("Open", "https://example.test", {"embed_links": False}) == "https://example.test"


def test_embed_links_escapes_url_markup() -> None:
    assert format_terminal_link("Open", "https://example.test/?q=]bold]", {"embed_links": True}) == "[link=https://example.test/?q=%5Dbold%5D]Open[/link]"


def test_embed_links_encodes_ipv6_authority_brackets_for_rich() -> None:
    link = format_terminal_link("Open", "https://[2001:db8::1]/", {"embed_links": True})
    assert link == "[link=https://%5B2001:db8::1%5D/]Open[/link]"
    assert Text.from_markup(link).plain == "Open"


def test_embed_dupe_links_remains_a_backward_compatible_alias() -> None:
    assert not should_embed_links({"embed_dupe_links": False})
    assert should_embed_links({"embed_links": True, "embed_dupe_links": False})
