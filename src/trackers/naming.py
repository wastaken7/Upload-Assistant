"""Shared, tracker-specific release title markers and video title builder."""

import re
from dataclasses import dataclass, replace
from typing import Any, Literal, cast

import httpx

from src import tmdb
from src.console import logger
from src.get_name import NameComponents, build_name_components
from src.languages import languages_manager
from src.meta import Meta
from src.tmdb import get_tmdb_localized_data

DVD_SOURCES = ("PAL DVD", "NTSC DVD", "DVD")

# Edition terms the Blutopia-derived guides keep out of the title (cuts such as Special Edition stay).
BLU_EDITION_TERMS = re.compile(
    r"\b(?:\d+(?:st|nd|rd|th)\s+)?anniversary(?:\s+edition)?\b"
    r"|\b(?:4k\s+)?remaster(?:ed)?\b"
    r"|\bcriterion(?:\s+collection)?\b"
    r"|\blimited(?:\s+edition)?\b"
    r"|\bcollector'?s?(?:\s+edition)?\b"
    r"|\bdeluxe(?:\s+edition)?\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class VideoNameRules:
    """How a tracker's naming guide differs from the shared Blutopia-style video template."""

    # Where a foreign-language label goes when no English audio exists ("" disables it).
    language_slot: Literal["", "before_cut", "before_resolution"] = ""
    # Dual-Audio only for a non-English original plus an English dub (Blutopia-style Dub rule).
    english_dub_only: bool = False
    # Keep MULTI for three or more languages instead of folding it into Dual-Audio.
    keep_multi: bool = False
    dual_audio_label: str = "Dual-Audio"
    # Edition words kept out of the title (they belong in the description); cuts stay.
    edition_terms: re.Pattern[str] | None = None
    # DVD-sourced releases: whether resolution and video codec appear (most guides omit both).
    dvd_resolution: bool = False
    dvd_video_codec: bool = False
    # "cut": next to the cut (generic order); "source": right before the source; "source_on_discs": only full discs move.
    three_d_slot: Literal["cut", "source", "source_on_discs"] = "source"
    aka: bool = True
    hybrid_on_webdl: bool = True
    # The generic name drops a manual year on TV unless the year came from the filename.
    honor_manual_year_on_tv: bool = False
    # TV titles carry a year only when TVDB disambiguates the series with one, e.g. "Show (2021)",
    # or, without a TVDB name, when TMDB lists another show with the same title.
    tv_year_from_tvdb: bool = True


# Blutopia-derived guides (Blutopia, ULCX, OnlyEncodes, LST): Dual-Audio/Dubbed only, editions out of the title,
# 3D right before the source, and no resolution or video codec for DVD-sourced releases.
BLU_NAME_RULES = VideoNameRules(english_dub_only=True, edition_terms=BLU_EDITION_TERMS)


# Search pages read before a homonym check gives up as inconclusive (20 results per page).
TMDB_HOMONYM_MAX_PAGES = 5

TVDB_TITLE_YEAR = re.compile(r"\((19\d{2}|20\d{2})\)\s*$")


def tvdb_title_year(meta: Meta) -> str | None:
    """Year TVDB appends to the series name to tell same-named shows apart.

    Returns None when no TVDB series name is known, "" when the name carries no year.
    """
    episode_data = meta.tvdb_episode_data if isinstance(meta.tvdb_episode_data, dict) else {}
    names = [str(name).strip() for name in (episode_data.get("series_name"), episode_data.get("series_title")) if isinstance(name, str) and name.strip()]
    if not names:
        return None
    for name in names:
        match = TVDB_TITLE_YEAR.search(name)
        if match:
            return match.group(1)
    return ""


def with_imdb_title(meta: Meta, components: NameComponents) -> NameComponents:
    """Use the IMDb title, AKA and movie year, as the IMDb-based guides require."""
    imdb_name = str(meta.imdb_info.get("title") or "").strip()
    imdb_year = str(meta.imdb_info.get("year") or "").strip()
    imdb_aka = str(meta.imdb_info.get("aka") or "").strip()
    title, alt_title, year = components.title, components.alt_title, components.year
    if imdb_name:
        title = imdb_name
        alt_title = f"AKA {imdb_aka}" if imdb_aka and imdb_aka != imdb_name and not meta.no_aka else ""
    if meta.category != "TV" and imdb_year and year and imdb_year != year:
        year = imdb_year
    return replace(components, title=title, alt_title=alt_title, year=year)


async def build_video_name(meta: Meta, rules: VideoNameRules, tracker: str, components: NameComponents | None = None) -> str:
    """Build a movie/TV title from components; returns "" when the generic name should be used instead."""
    if meta.manual_name is not None or meta.category not in ("MOVIE", "TV"):
        return ""

    parts = components or build_name_components(meta)
    name_type = parts.type
    source = parts.source
    if name_type == "ENCODE" and source in ("NTSC", "PAL"):
        # get_source reports a DVD-sourced encode as its bare broadcast system; the guides title it DVDRip.
        name_type = "DVDRIP"
    is_disc = name_type == "DISC" and bool(meta.is_disc)
    dvd_sourced = (is_disc and meta.is_disc == "DVD") or (name_type == "REMUX" and source in DVD_SOURCES)

    year = parts.year
    manual_year = meta.manual_year or 0
    if rules.honor_manual_year_on_tv and manual_year > 0 and not meta.no_year:
        year = str(manual_year)
    elif meta.category == "TV" and rules.tv_year_from_tvdb and not meta.no_year:
        tv_year = tvdb_title_year(meta)
        if tv_year is None:
            has_homonym = await tmdb_tv_title_has_homonym(meta, parts.title, tmdb.tmdb_api_key or "", tracker)
            if has_homonym is not None:
                tv_year = str(meta.year or "").strip() if has_homonym else ""
        if tv_year is not None:
            year = tv_year

    language = "" if is_disc or not rules.language_slot else await get_language_label(meta, tracker)
    audio = await _get_audio(meta, parts.audio, rules)
    cut = _cut_from_edition(parts.edition, rules)
    resolution = "" if dvd_sourced and not rules.dvd_resolution else parts.resolution
    hybrid = "" if name_type == "WEBDL" and not rules.hybrid_on_webdl else parts.hybrid
    three_d_near_source = rules.three_d_slot == "source" or (rules.three_d_slot == "source_on_discs" and is_disc)
    three_d_cut = "" if three_d_near_source else parts.three_d
    three_d_source = parts.three_d if three_d_near_source else ""
    language_before_cut = language if rules.language_slot == "before_cut" else ""
    language_before_resolution = language if rules.language_slot == "before_resolution" else ""
    region = meta.region or ""
    video_codec = meta.video_codec
    dvd_video_codec = video_codec if rules.dvd_video_codec else ""
    video_encode = meta.video_encode
    uhd = parts.uhd

    details: list[str]
    if is_disc and meta.is_disc == "BDMV":
        details = [hybrid, parts.repack, language_before_resolution, resolution, region, three_d_source, uhd, source, parts.hdr, video_codec, audio]
    elif is_disc and meta.is_disc == "DVD":
        details = [parts.repack, language_before_resolution, resolution, region, source, meta.dvd_size, dvd_video_codec, audio]
    elif is_disc and meta.is_disc == "HDDVD":
        details = [parts.repack, language_before_resolution, resolution, region, source, video_codec, audio]
    elif name_type == "REMUX" and source in ("BluRay", "HDDVD"):
        details = [hybrid, parts.repack, language_before_resolution, resolution, three_d_source, uhd, source, "REMUX", parts.hdr, video_codec, audio]
    elif name_type == "REMUX" and source in DVD_SOURCES:
        details = [parts.repack, language_before_resolution, resolution, source, "REMUX", dvd_video_codec, audio]
    elif name_type == "ENCODE":
        details = [hybrid, parts.repack, language_before_resolution, resolution, three_d_source, uhd, source, audio, parts.hdr, video_encode]
    elif name_type in ("WEBDL", "WEBRIP"):
        web_type = "WEB-DL" if name_type == "WEBDL" else "WEBRip"
        details = [hybrid, parts.repack, language_before_resolution, resolution, uhd, parts.service, web_type, parts.hardcoded_subs, audio, parts.hdr, video_encode]
    elif name_type == "HDTV":
        details = [parts.repack, language_before_resolution, resolution, source, audio, video_encode]
    elif name_type == "DVDRIP":
        dvdrip_resolution = parts.resolution if rules.dvd_resolution else ""
        details = [parts.repack, language_before_resolution, dvdrip_resolution, "DVDRip", audio, video_encode]
    else:
        return ""

    episode_fields = [f"{parts.season}{parts.episode}", parts.episode_title, parts.part] if meta.category == "TV" else []
    alt_title = parts.alt_title if rules.aka else ""
    fields = [parts.title, alt_title, year, *episode_fields, language_before_cut, three_d_cut, cut, *details]
    return " ".join(" ".join(fields).split()) + parts.tag


async def get_language_label(meta: Meta, tracker: str) -> str:
    """Upper-case audio language, only named when no English audio exists."""
    if not meta.language_checked:
        await languages_manager.process_desc_language(meta, tracker=tracker)
    audio_languages: list[str] = meta.audio_languages or []
    if not audio_languages or await languages_manager.has_english_language(audio_languages):
        return ""

    first_language = audio_languages[0].casefold()
    if meta.silent or first_language in ("zxx", "no linguistic content"):
        return "ZXX"
    if first_language in ("multiple", "multiple languages"):
        return "MULTIPLE LANGUAGES"
    return audio_languages[0].upper()


async def _get_audio(meta: Meta, audio: str, rules: VideoNameRules) -> str:
    label, _, codec = audio.partition(" ")
    if label not in ("Dual-Audio", "MULTI") or not codec:
        return audio
    if not rules.english_dub_only:
        return f"{rules.dual_audio_label} {codec}" if label == "Dual-Audio" else audio

    audio_languages: list[str] = meta.audio_languages or []
    if not audio_languages:
        return f"{rules.dual_audio_label} {codec}" if label == "Dual-Audio" else audio
    if label == "MULTI" and rules.keep_multi:
        return audio
    is_english_original = str(meta.original_language or "").lower().startswith("en")
    has_english_audio = await languages_manager.has_english_language(audio_languages)
    return f"{rules.dual_audio_label} {codec}" if has_english_audio and not is_english_original else codec


def _cut_from_edition(edition: str, rules: VideoNameRules) -> str:
    """Keep the cut from the detected edition, dropping the edition-only terms."""
    edition = " ".join(edition.split())
    if not edition or rules.edition_terms is None:
        return edition
    return " ".join(rules.edition_terms.sub(" ", edition).split())


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


class TmdbTvNaming:
    """TV names as TMDB title, IMDb AKA, then year if another show has the same title."""

    tracker: str
    config: dict[str, Any]

    async def _rebuild_tv_name(self, meta: Meta, name: str) -> str | None:
        """Rebuild everything before the season/episode. Returns None if the name has neither."""
        marker = f"{meta.season or ''}{meta.episode or ''}".strip()
        if not marker or marker not in name:
            return None

        tmdb_title = await self._tmdb_en_title(meta)
        aka = "" if meta.no_aka else self._localized_aka(meta, tmdb_title)
        year = str(meta.year or "").strip() if (not meta.no_year and await self._tv_title_needs_year(meta, tmdb_title)) else ""
        tail = name.partition(marker)[2]
        lead = " ".join(part for part in (tmdb_title, aka, year) if part)
        return " ".join(f"{lead} {marker}{tail}".split())

    async def _tmdb_en_title(self, meta: Meta) -> str:
        # meta.title can be the TVDB name for non-English shows; these sites use the TMDB one.
        try:
            tmdb_main = await get_tmdb_localized_data(meta, data_type="main", language="en-US", append_to_response="")
        except Exception:
            tmdb_main = {}
        data = tmdb_main if isinstance(tmdb_main, dict) else {}
        title = str(data.get("name") or data.get("title") or "").strip()
        return title or str(meta.title or "").strip()

    @staticmethod
    def _localized_aka(meta: Meta, tmdb_title: str) -> str:
        # English shows use the IMDb title, or its original title if that matches TMDB
        # (House -> AKA House M.D.). Other shows use IMDb's romanized original title.
        imdb_info = meta.imdb_info if isinstance(meta.imdb_info, dict) else {}
        original_language = str(meta.original_language or "").strip().lower()
        original_language = original_language.split("-")[0].split("(")[0].strip()
        is_english = original_language in ("en", "eng", "english")
        tmdb_key = tmdb_title.lower()
        for key in ("title", "aka") if is_english else ("aka",):
            aka = str(imdb_info.get(key) or "").strip()
            if aka and aka.lower() != tmdb_key and aka.lower() not in tmdb_key:
                return f"AKA {aka}"
        return ""

    async def _tv_title_needs_year(self, meta: Meta, title: str | None = None) -> bool:
        title = str(title if title is not None else (meta.title or "")).strip()
        api_key = str(self.config.get("DEFAULT", {}).get("tmdb_api", "")).strip()
        return await tmdb_tv_title_has_homonym(meta, title, api_key, self.tracker) is True


async def tmdb_tv_title_has_homonym(meta: Meta, title: str, api_key: str, tracker: str) -> bool | None:
    """Whether TMDB lists another show with exactly this title; None when TMDB cannot tell."""
    title = title.strip()
    api_key = api_key.strip()
    if not title or not api_key:
        return None

    title_key = " ".join(title.casefold().split())
    current_id = str(meta.tmdb_id or "")
    matching_ids: set[str] = set()

    def has_homonym() -> bool:
        return bool(matching_ids - {current_id, ""}) if current_id else len(matching_ids - {""}) > 1

    logger.info(f"{tracker}: Checking if TMDb has multiple shows with the title '{title}'...")
    total_pages = 1
    page = 1
    async with httpx.AsyncClient() as client:
        while page <= min(total_pages, TMDB_HOMONYM_MAX_PAGES):
            try:
                response = await client.get(
                    "https://api.themoviedb.org/3/search/tv",
                    params={"api_key": api_key, "query": title, "language": "en-US", "include_adult": "true", "page": page},
                )
                response.raise_for_status()
                payload_raw: Any = response.json()
            except httpx.HTTPError, ValueError, TypeError:
                return None

            payload = cast(dict[str, Any], payload_raw) if isinstance(payload_raw, dict) else {}
            results_raw: Any = payload.get("results", [])
            results = cast(list[Any], results_raw) if isinstance(results_raw, list) else []
            for result_raw in results:
                if not isinstance(result_raw, dict):
                    continue
                result = cast(dict[str, Any], result_raw)
                names = (result.get("name"), result.get("original_name"))
                if any(" ".join(str(candidate or "").casefold().split()) == title_key for candidate in names):
                    matching_ids.add(str(result.get("id", "")))
            if has_homonym():
                return True
            total_pages_raw: Any = payload.get("total_pages", 1)
            total_pages = total_pages_raw if isinstance(total_pages_raw, int) else 1
            page += 1

    # Unread pages could still hold a same-titled show.
    return None if total_pages > TMDB_HOMONYM_MAX_PAGES else False
