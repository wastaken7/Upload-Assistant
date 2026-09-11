"""Shared, tracker-specific release title markers."""

import re

from src.meta import Meta

INCOMPLETE_PACK_TRACKERS = frozenset(
    {
        "AITHER",
        "AVISTAZ",
        "CINEMAZ",
        "DARKPEERS",
        "HAWKEUNO",
        "HDBITS",
        "HDSPACE",
        "HDTORRENTS",
        "IPTORRENTS",
        "LST",
        "OLDTOONSWORLD",
        "ONLYENCODES",
        "PRIVATEHD",
        "RASTASTUGAN",
        "TORRENTLEECH",
        "ULCX",
        "YUSCENE",
    }
)


def add_incomplete_pack_marker(name: str, meta: Meta, tracker: str) -> str:
    """Mark confirmed incomplete packs without changing shared season metadata."""
    if tracker not in INCOMPLETE_PACK_TRACKERS or not getattr(meta, "season_pack_incomplete", False) or not meta.tv_pack or meta.category != "TV":
        return name

    season = str(meta.season or "")
    if season.isdigit():
        season = f"S{int(season):02d}"
    if not re.fullmatch(r"S\d+(?:-S?\d+)?", season, flags=re.IGNORECASE):
        return name

    # Match the whole season token, never the prefix of S030 or S03E02.
    # Consume an existing adjacent marker so repeated formatting is idempotent.
    pattern = rf"(?<![A-Za-z0-9])({re.escape(season)})(?![A-Za-z0-9])(?:[ ._-]+INCOMPLETE(?![A-Za-z0-9]))*"

    def insert(match: re.Match[str]) -> str:
        separator = "." if name[match.end() : match.end() + 1] == "." else " "
        return f"{match.group(1)}{separator}INCOMPLETE"

    return re.sub(pattern, insert, name, count=1, flags=re.IGNORECASE)
