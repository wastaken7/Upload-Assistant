# Upload Assistant © 2026 Audionut & wastaken7 — Licensed under UAPL v1.0
"""Every question key that ``--answer KEY=VALUE`` accepts, and shared questions.

Keys are ``<domain>.<name>`` for facts about the release that several
trackers can use (``game.subcategory``, ``xxx.tags``) and ``<tracker>.<name>``
for a single tracker's field. A test checks that every ``Question.key`` in the
code is listed here.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from src.manual_input import Question, ask, choices_from
from src.meta import Meta


@dataclass(frozen=True)
class KeyInfo:
    description: str
    values: tuple[str, ...] = ()


GAME_SUBCATEGORIES = {"full_game": "Full Game", "full_game_dlc": "Full Game + DLC", "dlc": "DLC", "update": "Update"}

QUESTION_KEYS: dict[str, KeyInfo] = {
    # Shared release facts
    "credits.cast": KeyInfo("Main cast, comma-separated"),
    "credits.creator": KeyInfo("Creator of a TV show"),
    "credits.director": KeyInfo("Director"),
    "douban.url": KeyInfo("Douban link used by PT-Gen"),
    "game.platform": KeyInfo("Game platform code, e.g. PC, PS4, SWITCH"),
    "game.subcategory": KeyInfo("Game subcategory", tuple(GAME_SUBCATEGORIES)),
    "genres.ptbr": KeyInfo("Genres in Portuguese, comma-separated (Brazilian trackers)"),
    "music.genres": KeyInfo("Album genres, comma-separated"),
    "release.audio_languages": KeyInfo("Languages of audio tracks without a language tag, comma-separated"),
    "release.hardcoded_sub_language": KeyInfo("Language of the hardcoded subtitles"),
    "release.subtitle_languages": KeyInfo("Languages of subtitle tracks without a language tag, comma-separated"),
    "xxx.tags": KeyInfo("Adult content tags in English, comma-separated"),
    # Tracker fields
    "alpharatio.cover": KeyInfo("Cover image link (.jpg, .png or .gif)"),
    "anthelion.safe_screens": KeyInfo("Whether the screenshots of adult content are safe (yes/no)"),
    "anthelion.tag": KeyInfo("Tag (genre) from the approved list"),
    "anthelion.type": KeyInfo("Release type", ("Feature Film", "Short Film")),
    "avistaz.audio_languages": KeyInfo("Languages of the audio tracks, comma-separated"),
    "bjshare.synopsis": KeyInfo("Synopsis in Portuguese"),
    "bjshare.title": KeyInfo("Upload title of an adult release"),
    "bjshare.year": KeyInfo("Year of an adult release"),
    "blutopia.derived_layer": KeyInfo("Whether the Dolby Vision layer is derived from another source (yes/no)"),
    "exoticaz.category": KeyInfo("Category of a multi-video upload", ("Video Clips", "Video Pack", "Siterip Pack", "Pornstar Pack")),
    "exoticaz.flags_detected": KeyInfo("Whether the flags detected from the keywords are correct (yes/no)"),
    "exoticaz.flags": KeyInfo("Flags that apply, comma-separated", ("asian", "softcore", "censored", "transexual", "gay")),
    "greatposterwall.director_chinese_name": KeyInfo("Director's name in Chinese"),
    "greatposterwall.director_imdb": KeyInfo("Director's IMDb person ID, e.g. nm0000138"),
    "greatposterwall.director_name": KeyInfo("Director's name in English"),
    "greatposterwall.genres": KeyInfo("Genres in the tracker's format, comma-separated"),
    "passthepopcorn.cover": KeyInfo("Cover image link for a new group (.jpg, .jpeg, .png or .webp)"),
    "passthepopcorn.hc_sub_language": KeyInfo("Language code of non-English hardcoded subtitles"),
    "passthepopcorn.mark_trumpable": KeyInfo("Whether to mark the release trumpable (yes/no)"),
    "passthepopcorn.tags": KeyInfo("Tags for a new group, comma-separated"),
    "passthepopcorn.trailer": KeyInfo("YouTube trailer link for a new group"),
    "passthepopcorn.trumpable": KeyInfo("Trumpable reasons, comma-separated", ("hc_full", "hc_forced", "no_english_subs", "softsubs_mislabeled", "hc_non_english")),
    "passthepopcorn.type": KeyInfo("Release type", ("Feature Film", "Short Film", "Miniseries", "Stand-up Comedy", "Concert", "Movie Collection")),
    "shareisland.distributor": KeyInfo("Disc distributor"),
    "shareisland.region": KeyInfo("Disc region code, e.g. USA"),
    "torrenteros.spanish_variant": KeyInfo("Spanish variant of the Spanish track", ("Castellano", "Latino", "Castellano Latino")),
}


def answer_help() -> str:
    lines = ["Keys accepted by --answer KEY=VALUE:"]
    for key, info in sorted(QUESTION_KEYS.items()):
        values = f" [{', '.join(info.values)}]" if info.values else ""
        lines.append(f"  {key}: {info.description}{values}")
    return "\n".join(lines)


def parse_answer_arg(value: str) -> tuple[str, str]:
    """Split ``KEY=VALUE`` and check the key, so a typo fails before the upload starts."""
    key, separator, answer = value.partition("=")
    key = key.strip().lower()
    if not separator:
        raise ValueError(f"--answer expects KEY=VALUE, got: {value}")
    info = QUESTION_KEYS.get(key)
    if info is None:
        raise ValueError(f"--answer: unknown key '{key}'. Use --answer help to list the keys.")
    answer = answer.strip()
    if info.values and not _known_values(answer, info.values):
        raise ValueError(f"--answer {key}: '{answer}' is not one of: {', '.join(info.values)}")
    return key, answer


def _known_values(answer: str, values: Iterable[str]) -> bool:
    allowed = {value.casefold() for value in values}
    parts = [part.strip().casefold() for part in answer.replace(";", ",").split(",") if part.strip()]
    return all(part in allowed for part in parts)


def _store_subcategory(meta: Meta, value: str) -> None:
    meta.game_subcategory = value


def _store_platform(meta: Meta, value: str) -> None:
    meta.platform = value


async def game_subcategory(meta: Meta, *, tracker: str) -> str:
    """Return the game subcategory, asking when it is unknown (default: Full Game)."""
    if meta.game_subcategory in GAME_SUBCATEGORIES:
        return meta.game_subcategory
    answer = await ask(
        meta,
        Question(
            key="game.subcategory",
            kind="choice",
            prompt=f"{tracker}: Select the game subcategory",
            title="Game subcategory",
            choices=choices_from(GAME_SUBCATEGORIES),
            default="full_game",
            hint="Not found in the game's metadata. Use --game-subcategory or --answer game.subcategory=... to skip this question.",
            summary={"Tracker": tracker, "Release": meta.name or meta.title, "Platform": meta.platform},
            tracker=tracker,
            unattended="default",
            store=_store_subcategory,
        ),
    )
    return answer or "full_game"


async def game_platform(meta: Meta, *, tracker: str, supported: Iterable[str], default: str) -> str:
    """Return ``meta.platform`` when ``supported`` knows it, otherwise ask for one of them."""
    platforms = list(dict.fromkeys(supported))
    current = (meta.platform or "").upper().strip()
    if current in platforms:
        return current
    answer = await ask(
        meta,
        Question(
            key="game.platform",
            kind="choice",
            prompt=f"{tracker}: Select the game platform",
            title="Game platform",
            choices=choices_from(platforms),
            default=default,
            hint=f"The platform '{meta.platform or 'unknown'}' is not supported by {tracker}. Use --platform or --answer game.platform=... to skip this question.",
            summary={"Tracker": tracker, "Release": meta.name or meta.title, "Platform": meta.platform},
            tracker=tracker,
            unattended="default",
            store=_store_platform,
        ),
    )
    return answer or default
