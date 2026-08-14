import re
from collections.abc import Iterable

from src.xxx_keywords_list import XXX_METADATA_KEYWORDS
from src.xxx_platforms import XXX_PLATFORM_KEYWORDS

_WORD_RE = re.compile(r"[a-z0-9]+")
_KEYWORD_TOKENS: dict[tuple[str, ...], str] = {}
for _keyword in sorted(XXX_PLATFORM_KEYWORDS | XXX_METADATA_KEYWORDS):
    _KEYWORD_TOKENS.setdefault(tuple(_WORD_RE.findall(_keyword)), _keyword)
_MAX_KEYWORD_TOKENS = max(map(len, _KEYWORD_TOKENS))


def extract_xxx_keywords(release_name: str, existing_keywords: Iterable[str] | str | None = None) -> list[str]:
    """Add known XXX platform and descriptive tags found in a release name."""
    if isinstance(existing_keywords, str):
        existing = [keyword.strip() for keyword in existing_keywords.split(",") if keyword.strip()]
    else:
        existing = [str(keyword).strip() for keyword in existing_keywords or () if str(keyword).strip()]

    tokens = _WORD_RE.findall(release_name.casefold())
    matches: list[tuple[int, int, str]] = []
    for start in range(len(tokens)):
        for size in range(1, min(_MAX_KEYWORD_TOKENS, len(tokens) - start) + 1):
            keyword = _KEYWORD_TOKENS.get(tuple(tokens[start : start + size]))
            if keyword:
                matches.append((start, start + size, keyword))

    # Prefer the most specific phrase and avoid emitting its component tags too.
    matches.sort(key=lambda match: (-(match[1] - match[0]), -len(match[2]), match[0], match[2]))
    matched: list[tuple[int, str]] = []
    occupied: set[int] = set()
    for start, end, keyword in matches:
        if occupied.isdisjoint(range(start, end)):
            occupied.update(range(start, end))
            matched.append((start, keyword))

    seen = {keyword.casefold() for keyword in existing}
    for _, keyword in sorted(matched):
        if keyword.casefold() not in seen:
            existing.append(keyword)
            seen.add(keyword.casefold())
    return existing
