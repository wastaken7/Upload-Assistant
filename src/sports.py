# Upload Assistant © 2026 Audionut & wastaken7 — Licensed under UAPL v1.0
"""Sports upload detection from prepared metadata."""

import re
import unicodedata

from src.meta import Meta

_SPORTS_RELEASE_PATTERN = re.compile(
    r"\b(?:aew|efl|fifa|formula 1|formula one|mlb|motogp|moto[23]|nascar|nba|nfl|nhl|olympics?|olimpiadas|ppv|ufc|uefa|"
    r"ultimate fighting championship|wrc|wwe)\b|\bgrand prix\b",
    re.IGNORECASE,
)
_SPORTS_EVENT_PATTERN = re.compile(
    r"\b(?:boxing|boxe|combat sports?|mixed martial arts|artes marciais mistas|motorsports?|sporting|sports?|esportivo|esportiva|wrestling) "
    r"(?:event|evento)\b",
    re.IGNORECASE,
)


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    normalized = normalized.casefold()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", normalized)).strip()


def detect_sports(meta: Meta) -> bool:
    """Detect sports events without classifying stories about sports as events."""
    category = _normalize(str(meta.category or ""))
    if category in {"sport", "sports", "esporte", "esportes"}:
        return True
    if category == "game":
        return False

    # Genres, keywords, synopses and producers can describe a sports-themed
    # series or movie. Require event naming rather than subject matter alone.
    for field_name in ("title", "original_title", "name", "name_notag", "regex_title"):
        value = _normalize(str(getattr(meta, field_name, "") or ""))
        if _SPORTS_RELEASE_PATTERN.search(value) or _SPORTS_EVENT_PATTERN.search(value):
            return True

    return False
