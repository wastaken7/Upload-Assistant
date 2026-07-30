# ruff: noqa: S101
from src.config_helpers import format_terminal_link, should_embed_links


def test_embed_links_controls_terminal_link_formatting() -> None:
    assert should_embed_links({"embed_links": True})
    assert format_terminal_link("Open", "https://example.test", {"embed_links": True}) == "[link=https://example.test]Open[/link]"
    assert format_terminal_link("Open", "https://example.test", {"embed_links": False}) == "Open - https://example.test"


def test_embed_dupe_links_remains_a_backward_compatible_alias() -> None:
    assert not should_embed_links({"embed_dupe_links": False})
    assert should_embed_links({"embed_links": True, "embed_dupe_links": False})
