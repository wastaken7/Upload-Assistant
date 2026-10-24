#!/usr/bin/env python3
"""Group GitHub-generated release notes into Feature/Fix/Maintenance and sort each group alphabetically."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

PR_LINE = re.compile(r"^\* (?P<title>.+?) by @\S+ in https://github\.com/\S+/pull/\d+\s*$")
CONVENTIONAL_TITLE = re.compile(r"^(?P<type>[A-Za-z]+)(?:\((?P<scope>[^)]*)\))?!?:\s*(?P<subject>.*)$")
SECTIONS = (("feat", "Feature"), ("fix", "Fix"))
FALLBACK_SECTION = "Maintenance"


def _sort_key(title: str) -> tuple[str, str, str]:
    match = CONVENTIONAL_TITLE.match(title)
    if not match:
        return ("~", "", title.casefold())
    # Unscoped titles ("fix: ...") come before scoped ones ("fix(webui): ...") of the same type
    return (match["type"].casefold(), (match["scope"] or "").casefold(), match["subject"].casefold())


def _section_for(title: str) -> str:
    match = CONVENTIONAL_TITLE.match(title)
    commit_type = match["type"].casefold() if match else ""
    return next((name for prefix, name in SECTIONS if commit_type == prefix), FALLBACK_SECTION)


def format_release_notes(notes: str) -> str:
    """Rewrite the "What's Changed" list; any other section (New Contributors, Full Changelog) is kept as is."""
    lines = notes.strip().splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == "## What's Changed")
    except StopIteration:
        return notes.strip() + "\n"

    first = start + 1
    while first < len(lines) and not lines[first].strip():
        first += 1
    end = first
    while end < len(lines) and PR_LINE.match(lines[end]):
        end += 1
    if end == first:
        return notes.strip() + "\n"

    grouped: dict[str, list[tuple[tuple[str, str, str], str]]] = {}
    for line in lines[first:end]:
        title = PR_LINE.match(line)["title"]  # type: ignore[index]
        grouped.setdefault(_section_for(title), []).append((_sort_key(title), line))

    body: list[str] = []
    for name in [name for _, name in SECTIONS] + [FALLBACK_SECTION]:
        if name in grouped:
            body.append(f"## {name}")
            body.extend(line for _, line in sorted(grouped[name]))

    return "\n".join([*lines[:start], *body, *lines[end:]]).strip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="Markdown file with the generated release notes, rewritten in place")
    args = parser.parse_args()
    args.path.write_text(format_release_notes(args.path.read_text(encoding="utf-8")), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
