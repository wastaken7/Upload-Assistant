# Upload Assistant © 2026 Audionut & wastaken7 — Licensed under UAPL v1.0
"""Sports upload detection from prepared metadata."""

import re
import unicodedata

from src.meta import Meta

_SPORTS_RELEASE_PATTERN = re.compile(
    r"^(?:(?P<numbered>ufc|ultimate fighting championship)|"
    r"(?P<formula>f1|formula ?1|formula one)|"
    r"aew|efl|epl|fifa|mlb|motogp|moto[23]|nascar|nba|nfl|nhl|olympics?|olimpiadas|ppv|uefa|"
    r"wrc|wwe|copa libertadores|copa sudamericana|africa cup of nations|australian open|"
    r"davis cup|billie jean king cup|ryder cup|solheim cup|world snooker championship|pdc world darts championship|grand prix)\b",
    re.IGNORECASE,
)
_SPORTS_EVENT_PATTERN = re.compile(
    r"\b(?:round \d{1,2}|(?:semi ?|quarter ?)?finals?|qualifying)\b|\b\w+ (?:vs|versus) \w+\b",
    re.IGNORECASE,
)


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    normalized = normalized.casefold()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", normalized)).strip()


def detect_sports(meta: Meta) -> bool:
    """Detect sports events without classifying stories about sports as events."""
    if meta.manual_category:
        return _normalize(meta.manual_category) in {"sport", "sports", "esporte", "esportes"}

    category = _normalize(str(meta.category or ""))
    if category in {"sport", "sports", "esporte", "esportes"}:
        return True
    if category == "game":
        return False

    # Require a competition prefix and event details in the same title.
    # Competition mentions, years and sports subject metadata are insufficient.
    for field_name in ("title", "original_title", "name", "name_notag", "regex_title"):
        value = _normalize(str(getattr(meta, field_name, "") or ""))
        competition = _SPORTS_RELEASE_PATTERN.match(value)
        if not competition:
            continue
        details = value[competition.end() :]
        if competition.group("numbered") and re.match(r" \d{1,3}\b", details):
            return True
        if competition.group("formula") and re.search(r"\bgrand prix\b", details):
            return True
        if _SPORTS_EVENT_PATTERN.search(details):
            return True

    return False
