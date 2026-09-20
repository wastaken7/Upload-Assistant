# Upload Assistant © 2026 Audionut & wastaken7 — Licensed under UAPL v1.0
"""Sports upload detection from prepared metadata."""

import re
import unicodedata
from typing import Any

from src.meta import Meta

_SPORTS_METADATA_PATTERN = re.compile(
    r"\b(?:sport|sports|esporte|esportes|american football|baseball|basketball|basquete|boxing|boxe|cage fighting|combat sports?|"
    r"cricket|cycling|ciclismo|football|futebol|golf|handball|ice hockey|kickboxing|mixed martial arts|artes marciais mistas|mma|"
    r"motorsports?|automobilismo|rugby|soccer|tennis|tenis|volleyball|volei|wrestling)\b",
    re.IGNORECASE,
)
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


def _text_values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [str(value[key]) for key in ("name", "title") if value.get(key)]
    if isinstance(value, list | tuple | set):
        values: list[str] = []
        for item in value:
            values.extend(_text_values(item))
        return values
    return []


def detect_sports(meta: Meta) -> bool:
    """Return whether the available metadata describes a sports upload."""
    category = _normalize(str(meta.category or ""))
    if category in {"sport", "sports", "esporte", "esportes"}:
        return True
    if category == "game":
        return False

    structured_metadata: list[str] = []
    for field_name in ("genres", "keywords", "combined_genres"):
        structured_metadata.extend(_text_values(getattr(meta, field_name, None)))
    if any(_SPORTS_METADATA_PATTERN.search(_normalize(value)) for value in structured_metadata):
        return True

    release_metadata: list[str] = []
    for field_name in ("title", "original_title", "name", "name_notag", "regex_title"):
        release_metadata.extend(_text_values(getattr(meta, field_name, None)))
    if any(_SPORTS_RELEASE_PATTERN.search(_normalize(value)) for value in release_metadata):
        return True

    supporting_metadata = _text_values(meta.production_companies)
    supporting_metadata.extend(_text_values(meta.overview))
    return any(_SPORTS_RELEASE_PATTERN.search(normalized) or _SPORTS_EVENT_PATTERN.search(normalized) for value in supporting_metadata if (normalized := _normalize(value)))
