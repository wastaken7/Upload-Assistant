# Upload Assistant © 2026 Audionut & wastaken7 — Licensed under UAPL v1.0
"""Provider-neutral XXX metadata: the shared result shape and the matching rules.

ThePornDB (:mod:`src.tpdb`) and BLVCKOUT (:mod:`src.blvckout`) both return an
:class:`XxxRelease`; :mod:`src.xxx_lookup` compares them with what the release
name says and decides whether a result can be used without asking.
"""

from __future__ import annotations

import re
import struct
import unicodedata
from dataclasses import asdict, dataclass, field, replace
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit

from src.xxx_keywords_list import XXX_METADATA_KEYWORDS

# Part of every cache key: raise it when the fields read from a provider change,
# so results cached by an earlier version are fetched again.
RECORD_VERSION = 3


@dataclass
class XxxRelease:
    """One scene or movie as a metadata provider describes it."""

    provider: str
    kind: str
    id: str
    title: str = ""
    date: str = ""
    year: int | None = None
    studio: str = ""
    network: str = ""
    # Other names of the studio, such as a site's short name ("examplestudio").
    aliases: list[str] = field(default_factory=list[str])
    performers: list[str] = field(default_factory=list[str])
    tags: list[str] = field(default_factory=list[str])
    description: str = ""
    poster_url: str = ""
    banner_url: str = ""
    url: str = ""
    duration_minutes: int | None = None
    # A JAV product code (TPDB external_id), such as ABC-123.
    code: str = ""
    via_hash: bool = False

    @property
    def ref(self) -> str:
        """The ID as ``--tpdb`` or ``--blvckout`` accept it."""
        return f"{self.kind}/{self.id}" if self.provider == "tpdb" else self.id

    @property
    def token(self) -> str:
        """The value a remembered ``xxx.match`` answer stores for this result."""
        return f"{self.provider}:{self.ref}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Any) -> XxxRelease | None:
        """Rebuild a cached result, or return None for anything unexpected."""
        if not isinstance(value, dict):
            return None
        data: dict[str, Any] = {str(key): item for key, item in value.items()}  # pyright: ignore[reportUnknownVariableType]
        try:
            release = cls(
                provider=str(data["provider"]),
                kind=str(data["kind"]),
                id=str(data["id"]),
                title=str(data.get("title") or ""),
                date=str(data.get("date") or ""),
                year=_int_or_none(data.get("year")),
                studio=str(data.get("studio") or ""),
                network=str(data.get("network") or ""),
                aliases=_strings(data.get("aliases")),
                performers=_strings(data.get("performers")),
                tags=_strings(data.get("tags")),
                description=str(data.get("description") or ""),
                poster_url=str(data.get("poster_url") or ""),
                banner_url=str(data.get("banner_url") or ""),
                url=str(data.get("url") or ""),
                duration_minutes=_int_or_none(data.get("duration_minutes")),
                code=str(data.get("code") or ""),
            )
        except KeyError, TypeError, ValueError:
            return None
        return release if release.id else None


def _strings(value: Any) -> list[str]:
    items = cast(list[Any], value) if isinstance(value, list) else []
    return [str(item) for item in items if item]


def _int_or_none(value: Any) -> int | None:
    try:
        number = int(value)
    except TypeError, ValueError:
        return None
    return number if number > 0 else None


# --- Text from providers -----------------------------------------------------


class _PlainText(HTMLParser):
    _blocks = frozenset({"p", "div", "section", "article", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "ul", "ol", "li", "tr", "table", "pre"})
    _hidden = frozenset({"script", "style", "iframe", "noscript", "template", "svg"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:  # noqa: ARG002
        if tag in self._hidden:
            self.hidden_depth += 1
        elif not self.hidden_depth and tag in self._blocks:
            self.parts.append("\n\n")
        elif not self.hidden_depth and tag == "br":
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._hidden:
            self.hidden_depth = max(0, self.hidden_depth - 1)
        elif not self.hidden_depth and tag in self._blocks:
            self.parts.append("\n\n")

    def handle_data(self, data: str) -> None:
        if not self.hidden_depth:
            self.parts.append(data)


def plain_text(value: Any, limit: int = 30000) -> str:
    """Return provider HTML as readable text with paragraph breaks; markup is never kept."""
    parser = _PlainText()
    parser.feed(str(value or "")[:100000])
    parser.close()
    text = "".join(parser.parts).replace("\xa0", " ")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    return re.sub(r"\n{3,}", "\n\n", text).strip()[:limit]


def unique_names(values: Any, limit: int = 100, length: int = 120) -> list[str]:
    """Return non-empty names once each (ignoring case), in their first order."""
    names: list[str] = []
    seen: set[str] = set()
    for value in values if isinstance(values, list) else []:  # pyright: ignore[reportUnknownVariableType]
        if value is None:
            # A record without a name; str() would make it "None".
            continue
        name = " ".join(str(value).split())[:length]  # pyright: ignore[reportUnknownArgumentType]
        if name and name.casefold() not in seen:
            seen.add(name.casefold())
            names.append(name)
            if len(names) >= limit:
                break
    return names


# Catalogue labels that describe the product or the shop rather than the content.
_NOT_CONTENT_TAGS = frozenset(
    {
        "feature",
        "movie",
        "movies",
        "collection",
        "appearance",
        "international",
        "language",
        "character",
        "plot oriented",
        "settings",
        "star showcase",
        "niche",
        "age",
        "clothing",
        "prebooks",
        "preorders",
    }
)
_STORE_TAG = re.compile(r"(?i)\bbest\s*sellers?\b|\bclearance\b|\bon sale\b|^(?:dvd|blu[ -]?ray|vod|digital download|4k(?: ultra)? hd|uhd)$|\s[-\u2013/|]\s")


def content_tags(values: Any, limit: int = 60) -> list[str]:
    """Return content tags without shop labels and combined ``A - B`` genres (their parts are usually listed too)."""
    return [tag for tag in unique_names(values, limit=limit * 2, length=64) if tag.casefold() not in _NOT_CONTENT_TAGS and not _STORE_TAG.search(tag)][:limit]


def safe_https_url(value: Any) -> str:
    """Return an HTTPS URL without credentials exactly as given, or ""."""
    if not isinstance(value, str) or not value or any(char.isspace() or char in "[]<>\"'" for char in value):
        return ""
    try:
        parsed = urlsplit(value)
    except ValueError:
        return ""
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        return ""
    return value


def first_image(*candidates: Any) -> str:
    """Return the first usable image URL, reading size dictionaries largest first."""
    for candidate in candidates:
        values: list[Any] = [candidate.get(size) for size in ("large", "full", "medium", "small")] if isinstance(candidate, dict) else [candidate]  # pyright: ignore[reportUnknownMemberType]
        for value in values:
            url = safe_https_url(value)
            if url:
                return url
    return ""


def is_stable_image_url(url: str) -> bool:
    """Whether an image URL can be published as is (no signature or expiring query)."""
    try:
        parsed = urlsplit(url)
    except ValueError:
        return False
    return not parsed.query and parsed.path.casefold().endswith((".jpg", ".jpeg", ".png", ".webp", ".gif"))


# --- Comparing a result with the release name ---------------------------------

_APOSTROPHES = re.compile("['`\u2019]")
_STOPWORDS = frozenset({"the", "a", "an", "and", "of", "vol", "volume", "part", "disc"})


def _tokens(value: str) -> list[str]:
    text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii").casefold()
    text = re.sub(_APOSTROPHES, "", text)
    words = re.sub(r"[^a-z0-9]+", " ", text).split()
    # Single digits stay: "Volume 8" and "Volume 9" are different releases.
    return [word for word in words if (len(word) > 1 or word.isdigit()) and word not in _STOPWORDS]


def title_similarity(left: str, right: str) -> float:
    """Dice similarity of two titles; a different volume number halves it."""
    left_tokens, right_tokens = set(_tokens(left)), set(_tokens(right))
    if not left_tokens or not right_tokens:
        return 0.0
    score = 2 * len(left_tokens & right_tokens) / (len(left_tokens) + len(right_tokens))
    return score * 0.5 if _volumes(left) != _volumes(right) else score


def compact(value: str) -> str:
    """Lowercase letters and digits only, for comparing studio names."""
    text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]", "", text.casefold())


def studio_matches(name: str, release: XxxRelease) -> bool:
    expected = compact(name)
    if not expected:
        return False
    candidates = [compact(value) for value in (release.studio, release.network, *release.aliases)]
    return any(
        expected == candidate or (len(expected) >= 5 and len(candidate) >= 5 and (expected in candidate or candidate in expected)) for candidate in candidates if candidate
    )


@dataclass
class ReleaseFacts:
    """What the release name and files say, to compare provider results with."""

    title: str = ""
    studio: str = ""
    date: str = ""
    year: int | None = None
    duration_minutes: int | None = None
    # A JAV product code such as ABC-123.
    code: str = ""


@dataclass
class MatchScore:
    release: XxxRelease
    title: float
    performer_match: bool
    date_match: bool
    date_conflict: bool
    year_match: bool
    studio_match: bool
    studio_conflict: bool
    duration_conflict: bool
    code_match: bool
    # Set by rank(): no other result of the same kind has (nearly) this title.
    only_title: bool = False
    # How well "performers + title" matches the whole name, without partial coverage.
    combined_title: float = 0.0
    # The name's studio is the initials of the result's studio ("BFTP18": Blast From The Past).
    studio_abbreviated: bool = False

    @property
    def exact(self) -> bool:
        """The same file hash or the same JAV product code."""
        return self.release.via_hash or self.code_match

    @property
    def conflict(self) -> bool:
        return self.date_conflict or self.studio_conflict or self.duration_conflict

    @property
    def total(self) -> float:
        value = self.title + (0.35 if self.date_match else 0) + (0.25 if self.studio_match else 0) + (0.3 if self.performer_match else 0) + (0.15 if self.year_match else 0)
        value -= (1.0 if self.date_conflict else 0) + (0.25 if self.studio_conflict else 0) + (0.3 if self.duration_conflict else 0)
        return value + (2.0 if self.exact else 0)

    @property
    def confident(self) -> bool:
        """Whether this result is the release, without a person confirming it."""
        if self.exact:
            return True
        if self.date_conflict or self.duration_conflict:
            return False
        if self.studio_conflict and not self.studio_abbreviated:
            return False
        # The same title on the same day, also when the name abbreviates the site.
        if self.date_match and self.title >= 0.95:
            return True
        if self.studio_conflict:
            return False
        if self.date_match and self.studio_match and (self.title >= 0.5 or self.performer_match):
            return True
        if self.title >= 0.8 and (self.date_match or self.studio_match):
            return True
        # The name gives a performer and the title of this scene. Partial coverage does
        # not count here: a name with only a performer must not pick one of their scenes.
        if self.performer_match and self.combined_title >= 0.9:
            return True
        # A movie with exactly this title, from the same year, or the only one with this
        # numbered title ("Example Feature 13"); a generic title alone is not enough.
        return self.release.kind == "movies" and self.title >= 0.95 and (self.year_match or (self.only_title and bool(_volumes(self.release.title))))

    @property
    def plausible(self) -> bool:
        if self.exact:
            return True
        return not self.date_conflict and (self.title >= 0.4 or self.performer_match)


def _volumes(value: str) -> list[str]:
    # Only 1-3 digit numbers are volumes; longer runs are years or product IDs.
    return [token for token in _tokens(value) if token.isdigit() and len(token) <= 3]


def _coverage(name: str, candidate: str) -> float:
    """How much of the release name the candidate's title and performers explain."""
    name_tokens = set(_tokens(name))
    if not name_tokens:
        return 0.0
    value = len(name_tokens & set(_tokens(candidate))) / len(name_tokens)
    return value * 0.5 if _volumes(name) != _volumes(candidate) else value


def _performer_named(name: str, performers: list[str]) -> bool:
    name_tokens = set(_tokens(name))
    for performer in performers:
        words = _tokens(performer)
        if words and (len(words) >= 2 or len(words[0]) >= 4) and set(words) <= name_tokens:
            return True
    return False


def score(release: XxxRelease, facts: ReleaseFacts) -> MatchScore:
    left, separator, right = facts.title.partition(" - ")
    if separator and not facts.studio and studio_matches(left, release):
        # "Studio - Title": compare the title alone, and the studio too.
        facts = replace(facts, title=right, studio=left)
    title = combined_title = 0.0
    performer_match = False
    if facts.title:
        title = combined_title = title_similarity(release.title, facts.title)
        if release.performers:
            # Scene names often carry the performers in place of, or before, the title.
            combined = f"{' '.join(release.performers)} {release.title}"
            performer_match = _performer_named(facts.title, release.performers)
            combined_title = max(title, title_similarity(combined, facts.title))
            title = combined_title
            if performer_match:
                # A name listing the performers and a few words of the title.
                title = max(title, 0.9 * _coverage(facts.title, combined))
    date_match = date_conflict = year_match = False
    if facts.date and release.date:
        date_match = facts.date == release.date
        date_conflict = not date_match
    elif facts.year and release.year:
        year_match = facts.year == release.year
        date_conflict = abs(facts.year - release.year) > 1
    studio_match = studio_matches(facts.studio, release)
    studio_conflict = bool(facts.studio and (release.studio or release.network) and not studio_match)
    duration_conflict = False
    if facts.duration_minutes and release.duration_minutes:
        # Encodes and site versions differ a little; a different scene differs a lot.
        duration_conflict = abs(facts.duration_minutes - release.duration_minutes) > max(5, release.duration_minutes * 0.15)
    code_match = bool(facts.code and release.code and compact(facts.code) == compact(release.code))
    return MatchScore(
        release,
        title,
        performer_match,
        date_match,
        date_conflict,
        year_match,
        studio_match,
        studio_conflict,
        duration_conflict,
        code_match,
        combined_title=combined_title,
        studio_abbreviated=studio_conflict and _abbreviates(facts.studio, release),
    )


def _abbreviates(short: str, release: XxxRelease) -> bool:
    """Whether a name's studio is the initials of the result's studio, ignoring digits."""
    letters = re.sub(r"[^a-z]", "", compact(short))
    if len(letters) < 2:
        return False
    for studio in (release.studio, release.network):
        words = re.findall(r"[A-Za-z]+", unicodedata.normalize("NFKD", studio))
        if len(words) >= 2 and "".join(word[0] for word in words).casefold() == letters:
            return True
    return False


def rank(releases: list[XxxRelease], facts: ReleaseFacts) -> list[MatchScore]:
    """Score each distinct result, best first."""
    seen: set[str] = set()
    scores: list[MatchScore] = []
    for release in releases:
        if release.token in seen:
            continue
        seen.add(release.token)
        scores.append(score(release, facts))
    for item in scores:
        item.only_title = item.title >= 0.95 and not any(other is not item and other.release.kind == item.release.kind and other.title >= 0.9 for other in scores)
    return sorted(scores, key=lambda item: item.total, reverse=True)


def confident_choice(scores: list[MatchScore]) -> MatchScore | None:
    """Return the best confident result when no other confident result comes close to it."""
    confident = [item for item in scores if item.confident]
    if not confident:
        return None
    best = confident[0]
    if best.exact:
        return best
    if len(confident) > 1 and best.total - confident[1].total < 0.2:
        return None
    return best


# --- Reading the release name ---------------------------------------------------

_TECHNICAL_TOKEN = re.compile(
    r"(?i)^(?:xxx|web(?:-?dl|-?rip)?|bluray|blu-ray|bdrip|brrip|dvdrip|dvd[59r]?|hdtv|remux|repack|proper|internal|uhd|fhd|hd|sd|"
    r"\d{3,4}[pi]|\d{3,4}x\d{3,4}|[248]k|x26[45]|h\.?26[45]|hevc|avc|av1|vp9|aac(?:2\.0)?|e?ac-?3|dts(?:-hd)?|truehd|atmos|ddp?5\.1|flac|mp3|"
    r"\d{2,3}fps|mkv|mp4|avi|wmv|mov|m4v|torrent|imageset|vr(?:180)?|split[-_ ]?scenes?)$"
)
DATED_NAME = re.compile(r"(?:^|[._ -])(\d{2})[._ -](\d{2})[._ -](\d{2})(?:[._ -]|$)")
_PACK_NAME = re.compile(r"(?i)(?:^|[._ \-\[(])(?:packs?|megapack|siterip|site[._ -]rip|boxset|box[._ -]set|collection|\d+[._ -]?clips)(?:[._ \-\])]|$)")
_MOVIE_NAME = re.compile(r"(?i)(?:^|[._ -])(?:movies?|feature|full[._ -]movie|dvdrip|dvd[59r]?|bdrip|bluray|vol(?:ume)?[._ -]?\d+)(?:[._ -]|$)")


def strip_group(name: str) -> str:
    """Remove a trailing ``-GROUP``, but keep hyphenated title words such as ``Full-Length``.

    A suffix is a group when it follows a technical tag (``…1080p.MP4-GRP``) or is
    written in capitals; a capitalized word after a title word is part of the title.
    """
    head, separator, tail = name.rpartition("-")
    if not separator or not head or not tail or re.search(r"[. ]", tail):
        return name
    last_word = re.split(r"[._ ]+", head.strip("._ "))[-1]
    # Capitals mean at least one capital letter: "Vol-2" or a date's "-21" is no group.
    written_in_capitals = bool(re.search(r"[A-Z]", tail)) and not re.search(r"[a-z]", tail)
    return head if _TECHNICAL_TOKEN.match(last_word) or written_in_capitals else name


def search_title(name: str, *, has_group: bool = True) -> str:
    """The release name without its group, the XXX marker and technical tags."""
    tokens = [token for token in re.split(r"[._ ]+", strip_group(name) if has_group else name) if token]
    kept = [token for token in tokens if not _TECHNICAL_TOKEN.match(token)]
    return re.sub(r"\s+", " ", " ".join(kept)).strip(" -")


def is_pack_name(name: str) -> bool:
    return bool(_PACK_NAME.search(name))


def looks_like_movie(name: str) -> bool:
    """Whether a name looks like a full-length movie rather than one dated scene."""
    return not DATED_NAME.search(name) and bool(_MOVIE_NAME.search(name) or _YEAR_IN_BRACKETS.search(name))


_YEAR_IN_BRACKETS = re.compile(r"[(\[]((?:19|20)\d{2})[)\]]")
_JAV_CODE = re.compile(r"(?i)^(?:\[[^\]]*\]\s*)?([a-z]{2,6})-(\d{2,5})(?=$|[^a-z0-9])")
_SPACED_DATE = re.compile(r"^(?P<studio>[A-Za-z0-9][A-Za-z0-9-]*)[ .](?P<year>\d{2})\.(?P<month>\d{2})\.(?P<day>\d{2})[ .](?P<rest>.+)$")


def jav_code(name: str) -> str:
    """Return a JAV product code (``ABC-123``) a name starts with, or ""."""
    match = _JAV_CODE.search(name.strip())
    return f"{match.group(1).upper()}-{match.group(2)}" if match else ""


def bracketed_year(name: str) -> int | None:
    match = _YEAR_IN_BRACKETS.search(name)
    return int(match.group(1)) if match else None


def dated_name_parts(name: str) -> tuple[str, str, str] | None:
    """Read ``Studio YY.MM.DD Title`` (spaces or dots) as ``(studio, YYYY-MM-DD, title)``."""
    match = _SPACED_DATE.match(strip_group(name).strip())
    if not match:
        return None
    month, day = int(match.group("month")), int(match.group("day"))
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return None
    rest = re.split(r"(?i)[._ ]XXX(?:[._ -]|$)", match.group("rest"))[0]
    date = f"20{match.group('year')}-{match.group('month')}-{match.group('day')}"
    return match.group("studio"), date, search_title(rest, has_group=False)


# Bracket groups that describe the player, language or quality, not the site.
_NOT_A_SITE = re.compile(
    r"(?i)oculus|vive|quest|gear\s?vr|psvr|pico|smartphone|^(?:rus|eng|ger|esp|fr|ita|jap?)$|^\d{3,4}[pi]?$|^[248]k$|^(?:sd|hd|fhd|uhd|4k|8k)$|^(?:19|20)\d{2}(?:-(?:19|20)\d{2})?$"
)
_ISO_DATE = re.compile(r"(?<!\d)((?:19|20)\d{2})[-.](\d{2})[-.](\d{2})(?!\d)")
_US_DATE = re.compile(r"\((\d{1,2})\.(\d{1,2})\.((?:19|20)\d{2})\)")
_LEADING_SHORT_DATE = re.compile(r"^\(?(\d{2})\.(\d{2})\.(\d{2})\)?(?=\s|$)")
_TRAILING_YEAR = re.compile(r"\s*\(?((?:19|20)\d{2})\)?\s*$")


def _site_name(group: str) -> str:
    """The first site of ``Site.com / Network.com``, without its domain suffix."""
    first = re.split(r"\s*[/,|]\s*", group.strip())[0]
    return re.sub(r"(?i)\.(?:com|net|org|xxx|tv)$", "", first).strip()


def _valid_date(year: int, month: int, day: int) -> str:
    return f"{year:04d}-{month:02d}-{day:02d}" if 1 <= month <= 12 and 1 <= day <= 31 else ""


def bracketed_site_parts(name: str) -> tuple[str, str, int | None, str] | None:
    """Read ``[Site.com] YY.MM.DD Performer - Title (2021.01.11) [1080p]`` style names.

    Returns ``(studio, YYYY-MM-DD or "", year, title)``, or None without a site in brackets.
    """
    groups = re.findall(r"\[([^\]]*)\]", name)
    site = next((_site_name(group) for group in groups if group.strip() and not _NOT_A_SITE.search(group.strip())), "")
    if not site:
        return None
    rest = re.sub(r"\[[^\]]*\]", " ", name)
    rest = re.sub(r"\s+", " ", rest).strip(" -")
    date = ""
    for pattern, order in ((_LEADING_SHORT_DATE, "ymd2"), (_ISO_DATE, "ymd"), (_US_DATE, "mdy")):
        match = pattern.search(rest)
        if not match:
            continue
        first, second, third = (int(value) for value in match.groups())
        if order == "ymd2":
            date = _valid_date(2000 + first, second, third)
        elif order == "ymd":
            date = _valid_date(first, second, third)
        else:
            date = _valid_date(third, first, second)
        if date:
            rest = (rest[: match.start()] + " " + rest[match.end() :]).strip()
            break
    year = int(date[:4]) if date else None
    trailing = _TRAILING_YEAR.search(rest)
    if trailing:
        year = year or int(trailing.group(1))
        rest = rest[: trailing.start()]
    title = search_title(re.sub(r"\(\s*\)", " ", rest), has_group=False)
    return site, date, year, title.strip(" -")


_NAME_WORD = re.compile(r"^[A-Z][a-z]+(?:['-][A-Za-z]+)?$")
_PERFORMER_STOPWORDS = frozenset({"a", "an", "the", "and", "of", "in", "on", "at", "to", "for", "with", "her", "his", "my", "your", "our", "their", "its"})


def performers_from_name(name: str) -> list[str]:
    """Guess performers from ``Site.YY.MM.DD.First.Last[.And.First.Last].Title.XXX``.

    Only two-word names written as names (capitalized, no digits, not a known
    content tag) count, so a title that starts right after the date is not
    taken for a performer.
    """
    candidate = strip_group(name)
    date = DATED_NAME.search(candidate)
    if not date:
        return []
    marker = re.search(r"(?i)[._ -]XXX(?:[._ -]|$)", candidate)
    tokens = [token for token in re.split(r"[._ ]+", candidate[date.end() : marker.start() if marker else len(candidate)]) if token]
    performers: list[str] = []
    index = 0
    while index + 1 < len(tokens) and len(performers) < 10:
        first, last = tokens[index], tokens[index + 1]
        words = (first.casefold(), last.casefold())
        if not all(_NAME_WORD.match(word) for word in (first, last)) or any(word in _PERFORMER_STOPWORDS for word in words):
            break
        if any(word in XXX_METADATA_KEYWORDS for word in (*words, "-".join(words), "".join(words))):
            break
        performers.append(f"{first} {last}")
        index += 2
        if index < len(tokens) and tokens[index].casefold() == "and":
            index += 1
        else:
            break
    return performers


# --- Naming a release from a match ---------------------------------------------


def _name_words(value: str) -> list[str]:
    text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    text = re.sub(_APOSTROPHES, "", text).replace("&", " and ")
    return re.sub(r"[^A-Za-z0-9]+", " ", text).split()


def build_release_name(release: XxxRelease, *, resolution: str = "", container: str = "") -> str:
    """Return a scene-style name: ``Studio.YY.MM.DD.Performer.Title.XXX.1080p.MP4``."""
    studio = "".join(word[:1].upper() + word[1:] for word in _name_words(release.studio))
    parts: list[str] = []
    if release.kind == "scenes" and studio and re.fullmatch(r"\d{4}-\d{2}-\d{2}", release.date):
        parts.append(studio)
        parts.append(release.date[2:].replace("-", "."))
        title_words = _name_words(release.title)
        performer_words = [word for name in release.performers[:3] for word in [*_name_words(name), "And"]][:-1]
        # Skip performers the title already starts with.
        if performer_words and [word.casefold() for word in title_words[: len(performer_words)]] != [word.casefold() for word in performer_words]:
            parts.extend(performer_words)
        parts.extend(title_words)
    else:
        parts.extend(_name_words(release.title))
        year = release.year or (int(release.date[:4]) if re.match(r"\d{4}", release.date) else None)
        if year:
            parts.append(str(year))
    if not parts:
        return ""
    parts.append("XXX")
    if resolution and resolution.casefold() not in ("other", "unknown"):
        parts.append(resolution)
    if container:
        parts.append(container.upper())
    return ".".join(parts)


# --- File fingerprint ------------------------------------------------------------

_OSHASH_CHUNK = 64 * 1024


def oshash(path: str | Path) -> str | None:
    """Return the OpenSubtitles hash of a file, or None when it is too small or unreadable."""
    file_path = Path(path)
    try:
        size = file_path.stat().st_size
        if size < _OSHASH_CHUNK * 2:
            return None
        with file_path.open("rb") as stream:
            head = stream.read(_OSHASH_CHUNK)
            stream.seek(size - _OSHASH_CHUNK)
            tail = stream.read(_OSHASH_CHUNK)
    except OSError:
        return None
    if len(head) != _OSHASH_CHUNK or len(tail) != _OSHASH_CHUNK:
        return None
    value = size
    for block in (head, tail):
        for (number,) in struct.iter_unpack("<Q", block):
            value = (value + number) & 0xFFFFFFFFFFFFFFFF
    return f"{value:016x}"
