# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
from collections.abc import Mapping
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

from rich.markup import escape


def should_embed_links(default_config: Mapping[str, Any]) -> bool:
    """Return whether terminal URLs should use Rich OSC 8 hyperlinks.

    ``embed_dupe_links`` is retained as a fallback for existing user configs.
    """
    if "embed_links" in default_config:
        return bool(default_config["embed_links"])
    return bool(default_config.get("embed_dupe_links", True))


def format_terminal_link(text: str, url: str, default_config: Mapping[str, Any]) -> str:
    """Format a terminal link according to the configured output style."""
    if should_embed_links(default_config):
        try:
            parsed_url = urlsplit(url)
            safe_url = urlunsplit(
                (
                    parsed_url.scheme,
                    quote(parsed_url.netloc, safe=":@!$&'()*+,;=%"),
                    quote(parsed_url.path, safe="/:@!$&'()*+,;=%"),
                    quote(parsed_url.query, safe="/:@!$&'()*+,;=%"),
                    quote(parsed_url.fragment, safe="/:@!$&'()*+,;=%"),
                )
            )
        except ValueError:
            safe_url = quote(url, safe=":/?#@!$&'()*+,;=%")
        return f"[link={safe_url}]{escape(text)}[/link]"
    return escape(url)
