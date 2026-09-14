"""Shared release-name profiles, policies, and tracker mixins."""

import re
import unicodedata
from collections.abc import Mapping

from src.meta import Meta
from src.release_name import (
    NameContext,
    NameRule,
    NameSelector,
    ReleaseNameBuilder,
    TrackerNameProfile,
    conditional,
    replace_context_value_with,
    replace_text,
    template,
)

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


def add_incomplete_pack_marker_transform(name: str, context: NameContext) -> str:
    return add_incomplete_pack_marker(name, context.meta, context.values.get("tracker", ""))


BASE_NAME_PROFILE = TrackerNameProfile(rules=(NameRule(NameSelector(), template("base_name")),))
BASE_NAME_WITH_INCOMPLETE_PROFILE = TrackerNameProfile(
    rules=(NameRule(NameSelector(), template("base_name")),),
    transforms=(add_incomplete_pack_marker_transform,),
)
TITLE_NAME_PROFILE = TrackerNameProfile(rules=(NameRule(NameSelector(), template("title")),))
SOURCE_NAME_PROFILE = TrackerNameProfile(rules=(NameRule(NameSelector(), template("source_name")),))
SCENE_OR_BASENAME_PROFILE = TrackerNameProfile(rules=(NameRule(NameSelector(), template("scene_or_basename")),))


def normalize_release_name(*, append_unrar: bool = False):
    def transform(name: str, context: NameContext) -> str:
        scene_name = context.values.get("scene_name", "")
        name = name.replace("DD+", "DDP").replace("DTS:", "DTS-").replace("HDR10+", "HDR10P")
        name = unicodedata.normalize("NFD", name)
        name = "".join(char for char in name if char.isascii() and (char.isalnum() or char in (" ", ".", "-")))
        name = name.replace("!", "")
        return f"{name} [UNRAR]" if append_unrar and scene_name else name

    return transform


def configured_metadata_name(*, append_unrar: bool = False):
    normalized = normalize_release_name(append_unrar=append_unrar)

    def transform(name: str, context: NameContext) -> str:
        return normalized(name, context) if context.values.get("use_metadata_name") == "1" else name

    return transform


def _dvd_source(context: NameContext) -> bool:
    return context.values.get("source", "") in {"PAL DVD", "NTSC DVD", "DVD", "NTSC", "PAL"}


INSERT_VIDEO_CODEC_BEFORE_DVD_AUDIO = conditional(
    _dvd_source,
    replace_context_value_with(
        "audio",
        lambda context: " ".join(part for part in (context.values.get("video_codec", ""), " ".join(context.values.get("audio", "").split())) if part),
    ),
)
DVD_CODEC_NAME_PROFILE = TrackerNameProfile(
    rules=(NameRule(NameSelector(), template("base_name")),),
    transforms=(INSERT_VIDEO_CODEC_BEFORE_DVD_AUDIO, replace_text(("DD+", "DDP"))),
)


class TrackerNameMixin:
    name_profile: TrackerNameProfile = BASE_NAME_PROFILE
    tracker = ""

    async def get_name_overrides(self, _context: NameContext) -> Mapping[str, str]:
        return {}

    async def render_name(self, meta: Meta) -> str:
        builder = ReleaseNameBuilder()

        async def overrides(context: NameContext) -> Mapping[str, str]:
            values = {"tracker": str(getattr(self, "tracker", ""))}
            values.update(await self.get_name_overrides(context))
            return values

        name, _missing = await builder.render(meta, self.name_profile, overrides)
        return name


class StringTrackerNameMixin(TrackerNameMixin):
    async def get_name(self, meta: Meta) -> str:
        return await self.render_name(meta)
