from __future__ import annotations

import re
import unicodedata
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol

from src.meta import Meta


@dataclass(frozen=True)
class NameSelector:
    category: str | None = None
    type: str | tuple[str, ...] | None = None
    subtype: str | None = None
    is_disc: str | None = None
    source: str | tuple[str, ...] | None = None

    @classmethod
    def from_meta(cls, meta: Meta) -> NameSelector:
        category = str(getattr(meta, "category", "") or "").upper()
        subtype = ""
        if category == "BOOK":
            subtype = next(
                (
                    name
                    for name, active in (
                        ("AUDIOBOOK", getattr(meta, "audiobook", False)),
                        ("COMIC", getattr(meta, "comic", False)),
                        ("MANGA", getattr(meta, "manga", False)),
                        ("MAGAZINE", getattr(meta, "magazine", False)),
                        ("NEWSPAPER", getattr(meta, "newspaper", False)),
                    )
                    if active
                ),
                "EBOOK",
            )
        return cls(
            category=category,
            type=str(getattr(meta, "type", "") or "").upper(),
            subtype=subtype,
            is_disc=str(getattr(meta, "is_disc", "") or "").upper(),
            source=str(getattr(meta, "source", "") or "").upper(),
        )

    def matches(self, actual: NameSelector) -> bool:
        def matches_value(expected: str | tuple[str, ...] | None, value: str | tuple[str, ...] | None) -> bool:
            if expected is None:
                return True
            if not isinstance(value, str):
                return False
            return value in expected if isinstance(expected, tuple) else expected == value

        return all(
            matches_value(expected, value)
            for expected, value in (
                (self.category, actual.category),
                (self.type, actual.type),
                (self.subtype, actual.subtype),
                (self.is_disc, actual.is_disc),
                (self.source, actual.source),
            )
        )

    @property
    def specificity(self) -> int:
        return sum(value is not None for value in (self.category, self.type, self.subtype, self.is_disc, self.source))


@dataclass(frozen=True)
class NameField:
    name: str


@dataclass(frozen=True)
class NameLiteral:
    value: str


type NamePart = NameField | NameLiteral


class NameTransform(Protocol):
    def __call__(self, value: str, context: NameContext) -> str: ...


class NamePredicate(Protocol):
    def __call__(self, context: NameContext) -> bool: ...


class NameSuffixPolicy(StrEnum):
    NONE = "none"
    APPEND_TAG = "append_tag"


@dataclass(frozen=True)
class NameTemplate:
    parts: tuple[NamePart, ...]
    separator: str = " "
    potential_missing: tuple[str, ...] = ()
    transforms: tuple[NameTransform, ...] = ()
    suffix_policy: NameSuffixPolicy = NameSuffixPolicy.NONE


@dataclass(frozen=True)
class NameRule:
    selector: NameSelector
    template: NameTemplate


@dataclass(frozen=True)
class TrackerNameProfile:
    rules: tuple[NameRule, ...]
    overrides: Mapping[str, str] = field(default_factory=dict)
    transforms: tuple[NameTransform, ...] = ()


@dataclass(frozen=True)
class NameContext:
    meta: Meta
    selector: NameSelector
    values: Mapping[str, str]

    def with_overrides(self, *overrides: Mapping[str, str]) -> NameContext:
        values = dict(self.values)
        for replacement in overrides:
            values.update({key: str(value or "") for key, value in replacement.items()})
        selector = NameSelector(
            category=values.get("category", self.selector.category or "").upper(),
            type=values.get("type", self.selector.type or "").upper(),
            subtype=values.get("subtype", self.selector.subtype or "").upper(),
            is_disc=values.get("is_disc", self.selector.is_disc or "").upper(),
            source=values.get("source", self.selector.source or "").upper(),
        )
        return NameContext(meta=self.meta, selector=selector, values=values)


@dataclass(frozen=True)
class NameBuildResult:
    name_notag: str
    name: str
    clean_name: str
    potential_missing: tuple[str, ...] = ()


DynamicNameOverrides = Callable[[NameContext], Mapping[str, str] | Awaitable[Mapping[str, str]]]


def collapse_whitespace(value: str, _context: NameContext) -> str:
    return " ".join(value.split())


def spaces_to_dots(value: str, _context: NameContext) -> str:
    return re.sub(r"\.+", ".", value.replace(" ", ".")).strip(".")


def dots_to_spaces(value: str, _context: NameContext) -> str:
    return value.replace(".", " ")


def strip_name(value: str, _context: NameContext) -> str:
    return value.strip()


def strip_characters(characters: str) -> NameTransform:
    def transform(value: str, _context: NameContext) -> str:
        return value.strip(characters)

    return transform


def replace_text(*replacements: tuple[str, str]) -> NameTransform:
    def transform(value: str, _context: NameContext) -> str:
        for old, new in replacements:
            value = value.replace(old, new)
        return value

    return transform


def regex_sub(pattern: str, replacement: str | Callable[[re.Match[str]], str], *, flags: int = 0, count: int = 0) -> NameTransform:
    def transform(value: str, _context: NameContext) -> str:
        return re.sub(pattern, replacement, value, count=count, flags=flags)

    return transform


def conditional(predicate: NamePredicate, *transforms: NameTransform) -> NameTransform:
    def transform(value: str, context: NameContext) -> str:
        if predicate(context):
            for operation in transforms:
                value = operation(value, context)
        return value

    return transform


def remove_context_value(field_name: str, *, ignore_case: bool = False) -> NameTransform:
    def transform(value: str, context: NameContext) -> str:
        target = context.values.get(field_name, "")
        if not target:
            return value
        if ignore_case:
            return re.sub(re.escape(target), "", value, count=1, flags=re.IGNORECASE)
        return value.replace(target, "", 1)

    return transform


def replace_context_value_with(field_name: str, replacement: Callable[[NameContext], str]) -> NameTransform:
    def transform(value: str, context: NameContext) -> str:
        target = context.values.get(field_name, "")
        return value.replace(target, replacement(context), 1) if target else value

    return transform


def strip_diacritics(value: str, _context: NameContext) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(char for char in normalized if not unicodedata.combining(char))


class ReleaseNameBuilder:
    def context_from_meta(self, meta: Meta) -> NameContext:
        def value(name: str, default: Any = "") -> Any:
            return getattr(meta, name, default)

        category = str(value("category") or "")
        year = str(value("year")) if value("year") is not None else ""
        manual_year = value("manual_year")
        if manual_year not in (None, "") and manual_year > 0:
            year = str(manual_year)
        if category == "TV":
            year = str(value("year") or "") if value("search_year") != "" else ""
        if value("no_year", False):
            year = ""

        title = str(value("title") or "")
        alt_title = "" if value("no_aka", False) else str(value("aka") or "")
        season = "" if value("no_season", False) else str(value("season") or "")
        episode = str(value("episode") or "")
        if category == "TV" and value("manual_date"):
            season = ""
            episode = ""
        episode_title = str(value("manual_episode_title") or value("daily_episode_title") or "")
        resolution = "" if value("resolution") == "OTHER" else str(value("resolution") or "")
        edition = str(value("edition") or "")
        if "HYBRID" in edition.upper():
            edition = edition.replace("Hybrid", "").strip()

        values = {
            "base_name": str(value("name") or ""),
            "name_notag": str(value("name_notag") or ""),
            "clean_name": str(value("clean_name") or ""),
            "scene_name": str(value("scene_name") or ""),
            "basename_no_ext": str(value("basename_no_ext") or ""),
            "source_name": str(value("scene_name") or value("basename_no_ext") or value("uuid") or title),
            "scene_or_basename": str(value("scene_name") or value("basename_no_ext") or ""),
            "title": title,
            "alt_title": alt_title,
            "year": year,
            "season": season,
            "episode": episode,
            "season_episode": f"{season}{episode}",
            "season_episode_three_d": f"{season}{episode}{value('three_d') or ''}",
            "episode_title": episode_title,
            "metadata_episode_title": str(value("episode_title") or ""),
            "part": str(value("part") or ""),
            "three_d": str(value("three_d") or ""),
            "edition": edition,
            "hybrid": "Hybrid" if value("webdv", False) else "",
            "repack": str(value("repack") or ""),
            "resolution": resolution,
            "region": str(value("region") or ""),
            "distributor": str(value("distributor") or ""),
            "uhd": str(value("uhd") or ""),
            "source": str(value("source") or ""),
            "service": str(value("service") or ""),
            "hardcoded_subs": "HC" if value("hardcoded_subs", False) else "",
            "audio": str(value("audio") or ""),
            "hdr": str(value("hdr") or ""),
            "video_codec": str(value("video_codec") or ""),
            "video_encode": str(value("video_encode") or ""),
            "dvd_size": str(value("dvd_size") or ""),
            "disctype": str(value("disctype") or ""),
            "tag": str(value("tag") or ""),
            "type": str(value("type") or ""),
            "category": category,
            "is_disc": str(value("is_disc") or ""),
            "platform": str(value("platform") or ""),
            "format": str(value("format") or ""),
            "author": str(value("author") or ""),
            "publisher": str(value("publisher") or ""),
            "narrator": str(value("narrator") or ""),
            "original_title": str(value("original_title") or ""),
            "language": str(value("language") or ""),
            "book_language": str(value("book_language") or ""),
            "book_language_iso": str(value("book_language_iso") or ""),
            "book_series": str(value("book_series") or ""),
            "book_series_index": str(value("book_series_index") or ""),
            "game_version": str(value("game_version") or ""),
        }
        return NameContext(meta=meta, selector=NameSelector.from_meta(meta), values=values)

    @staticmethod
    def select_template(profile: TrackerNameProfile, selector: NameSelector) -> NameTemplate:
        matches = [rule for rule in profile.rules if rule.selector.matches(selector)]
        if not matches:
            raise ValueError(f"No release-name template matches {selector}")
        return max(matches, key=lambda rule: rule.selector.specificity).template

    async def render(
        self,
        meta: Meta,
        profile: TrackerNameProfile,
        dynamic_overrides: DynamicNameOverrides | None = None,
    ) -> tuple[str, tuple[str, ...]]:
        context = self.context_from_meta(meta).with_overrides(profile.overrides)
        if dynamic_overrides is not None:
            resolved = dynamic_overrides(context)
            if isinstance(resolved, Awaitable):
                resolved = await resolved
            context = context.with_overrides(resolved)

        template = self.select_template(profile, context.selector)
        rendered: list[str] = []
        for part in template.parts:
            value = part.value if isinstance(part, NameLiteral) else context.values.get(part.name, "")
            if value:
                rendered.append(value)

        name = template.separator.join(rendered)
        for transform in (*template.transforms, *profile.transforms):
            name = transform(name, context)
        if template.suffix_policy == NameSuffixPolicy.APPEND_TAG:
            name += context.values.get("tag", "")
        return name, template.potential_missing


def field(name: str) -> NameField:
    return NameField(name)


def literal(value: str) -> NameLiteral:
    return NameLiteral(value)


def template(*parts: str | NamePart, **kwargs: Any) -> NameTemplate:
    normalized = tuple(field(part) if isinstance(part, str) else part for part in parts)
    return NameTemplate(parts=normalized, **kwargs)
