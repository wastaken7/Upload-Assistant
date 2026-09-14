# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import re
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, cast

import anitopy
import cli_ui
import guessit

from src.cleanup import cleanup_manager
from src.console import logger
from src.meta import Meta
from src.release_name import (
    NameBuildResult,
    NameRule,
    NameSelector,
    ReleaseNameBuilder,
    TrackerNameProfile,
    collapse_whitespace,
    dots_to_spaces,
    literal,
    regex_sub,
    template,
)
from src.trackers.common import Common

guessit_module: Any = cast(Any, guessit)
GuessitFn = Callable[[str, dict[str, Any] | None], dict[str, Any]]


def guessit_fn(value: str, options: dict[str, Any] | None = None) -> dict[str, Any]:
    return cast(dict[str, Any], guessit_module.guessit(value, options))


TRACKER_DISC_REQUIREMENTS = {
    "ULCX": {"region": "mandatory", "distributor": "mandatory"},
    "SHAREISLAND": {"region": "mandatory", "distributor": "optional"},
    "OLDTOONSWORLD": {"region": "mandatory", "distributor": "optional"},
}


DEFAULT_NAME_PROFILE = TrackerNameProfile(
    rules=(
        NameRule(NameSelector(category="XXX"), template("source_name", transforms=(dots_to_spaces, collapse_whitespace))),
        NameRule(
            NameSelector(category="BOOK", subtype="AUDIOBOOK"),
            template("author", "dash", "book_series", "title", "book_series_index", "edition", "year", "book_language", "audiobook_label"),
        ),
        NameRule(
            NameSelector(category="BOOK", subtype="COMIC"),
            template("title", "volume_label", "issue_label", "year", "book_language", "book_source", "book_format", "comic_label", "ebook_label"),
        ),
        NameRule(
            NameSelector(category="BOOK", subtype="MANGA"),
            template("title", "volume_label", "year", "book_language", "book_source", "book_format", "manga_label", "ebook_label"),
        ),
        NameRule(
            NameSelector(category="BOOK", subtype="MAGAZINE"),
            template("title", "issue_label", "year", "book_language", "book_source", "book_format", "magazine_label", "ebook_label"),
        ),
        NameRule(NameSelector(category="BOOK", subtype="NEWSPAPER"), template("title", "year", "book_language", "book_source", "book_format", "ebook_label")),
        NameRule(
            NameSelector(category="BOOK", subtype="EBOOK"),
            template(
                "author_or_publisher", "dash", "book_series", "title", "book_series_index", "edition", "year", "book_language", "book_source", "book_format", "ebook_label"
            ),
        ),
        NameRule(
            NameSelector(category="GAME"),
            template(
                "title",
                "edition",
                "game_version",
                "year",
                "game_language",
                "game_platform",
                "repack",
                transforms=(regex_sub(r"\.{2,}", " "),),
            ),
        ),
        NameRule(NameSelector(category="MUSIC"), template("artist", "dash", "title", "year", "music_source", "music_codec", "bit_depth", "sample_rate")),
        NameRule(
            NameSelector(category="MOVIE", type="DISC", is_disc="BDMV"),
            template(
                "title",
                "alt_title",
                "year",
                "three_d",
                "edition",
                "hybrid",
                "repack",
                "resolution",
                "region",
                "uhd",
                "source",
                "hdr",
                "video_codec",
                "audio",
                potential_missing=("edition", "region", "distributor"),
            ),
        ),
        NameRule(
            NameSelector(category="MOVIE", type="DISC", is_disc="DVD"),
            template(
                "title",
                "alt_title",
                "year",
                "repack",
                "edition",
                "region",
                "source",
                "dvd_size",
                "audio",
                potential_missing=("edition", "distributor"),
            ),
        ),
        NameRule(
            NameSelector(category="MOVIE", type="DISC", is_disc="HDDVD"),
            template(
                "title",
                "alt_title",
                "year",
                "edition",
                "repack",
                "resolution",
                "source",
                "video_codec",
                "audio",
                potential_missing=("edition", "region", "distributor"),
            ),
        ),
        NameRule(
            NameSelector(category="TV", type="DISC", is_disc="BDMV"),
            template(
                "title",
                "year",
                "alt_title",
                "season_episode",
                "three_d",
                "edition",
                "hybrid",
                "repack",
                "resolution",
                "region",
                "uhd",
                "source",
                "hdr",
                "video_codec",
                "audio",
                potential_missing=("edition", "region", "distributor"),
            ),
        ),
        NameRule(
            NameSelector(category="TV", type="DISC", is_disc="DVD"),
            template(
                "title",
                "year",
                "alt_title",
                "season_episode_three_d",
                "repack",
                "edition",
                "region",
                "source",
                "dvd_size",
                "audio",
                potential_missing=("edition", "distributor"),
            ),
        ),
        NameRule(
            NameSelector(category="TV", type="DISC", is_disc="HDDVD"),
            template(
                "title",
                "alt_title",
                "year",
                "edition",
                "repack",
                "resolution",
                "source",
                "video_codec",
                "audio",
                potential_missing=("edition", "region", "distributor"),
            ),
        ),
        NameRule(
            NameSelector(category="MOVIE", type="REMUX", source=("BLURAY", "HDDVD")),
            template(
                "title",
                "alt_title",
                "year",
                "three_d",
                "edition",
                "hybrid",
                "repack",
                "resolution",
                "uhd",
                "source",
                literal("REMUX"),
                "hdr",
                "video_codec",
                "audio",
                potential_missing=("edition", "description"),
            ),
        ),
        NameRule(
            NameSelector(category="MOVIE", type="REMUX", source=("PAL DVD", "NTSC DVD", "DVD")),
            template(
                "title",
                "alt_title",
                "year",
                "edition",
                "repack",
                "source",
                literal("REMUX"),
                "audio",
                potential_missing=("edition", "description"),
            ),
        ),
        NameRule(
            NameSelector(category="TV", type="REMUX", source=("BLURAY", "HDDVD")),
            template(
                "title",
                "year",
                "alt_title",
                "season_episode",
                "episode_title",
                "part",
                "three_d",
                "edition",
                "hybrid",
                "repack",
                "resolution",
                "uhd",
                "source",
                literal("REMUX"),
                "hdr",
                "video_codec",
                "audio",
                potential_missing=("edition", "description"),
            ),
        ),
        NameRule(
            NameSelector(category="TV", type="REMUX", source=("PAL DVD", "NTSC DVD", "DVD")),
            template(
                "title",
                "year",
                "alt_title",
                "season_episode",
                "episode_title",
                "part",
                "edition",
                "repack",
                "source",
                literal("REMUX"),
                "audio",
                potential_missing=("edition", "description"),
            ),
        ),
        NameRule(
            NameSelector(category="MOVIE", type="ENCODE"),
            template(
                "title",
                "alt_title",
                "year",
                "edition",
                "hybrid",
                "repack",
                "resolution",
                "uhd",
                "source",
                "audio",
                "hdr",
                "video_encode",
                potential_missing=("edition", "description"),
            ),
        ),
        NameRule(
            NameSelector(category="TV", type="ENCODE"),
            template(
                "title",
                "year",
                "alt_title",
                "season_episode",
                "episode_title",
                "part",
                "edition",
                "hybrid",
                "repack",
                "resolution",
                "uhd",
                "source",
                "audio",
                "hdr",
                "video_encode",
                potential_missing=("edition", "description"),
            ),
        ),
        NameRule(
            NameSelector(category="MOVIE", type="WEBDL"),
            template(
                "title",
                "alt_title",
                "year",
                "edition",
                "hybrid",
                "repack",
                "resolution",
                "uhd",
                "service",
                literal("WEB-DL"),
                "hardcoded_subs",
                "audio",
                "hdr",
                "video_encode",
                potential_missing=("edition", "service"),
            ),
        ),
        NameRule(
            NameSelector(category="TV", type="WEBDL"),
            template(
                "title",
                "year",
                "alt_title",
                "season_episode",
                "episode_title",
                "part",
                "edition",
                "hybrid",
                "repack",
                "resolution",
                "uhd",
                "service",
                literal("WEB-DL"),
                "hardcoded_subs",
                "audio",
                "hdr",
                "video_encode",
                potential_missing=("edition", "service"),
            ),
        ),
        NameRule(
            NameSelector(category="MOVIE", type="WEBRIP"),
            template(
                "title",
                "alt_title",
                "year",
                "edition",
                "hybrid",
                "repack",
                "resolution",
                "uhd",
                "service",
                literal("WEBRip"),
                "hardcoded_subs",
                "audio",
                "hdr",
                "video_encode",
                potential_missing=("edition", "service"),
            ),
        ),
        NameRule(
            NameSelector(category="TV", type="WEBRIP"),
            template(
                "title",
                "year",
                "alt_title",
                "season_episode",
                "episode_title",
                "part",
                "edition",
                "hybrid",
                "repack",
                "resolution",
                "uhd",
                "service",
                literal("WEBRip"),
                "hardcoded_subs",
                "audio",
                "hdr",
                "video_encode",
                potential_missing=("edition", "service"),
            ),
        ),
        NameRule(
            NameSelector(category="MOVIE", type="HDTV"),
            template("title", "alt_title", "year", "edition", "repack", "resolution", "source", "audio", "video_encode"),
        ),
        NameRule(
            NameSelector(category="TV", type="HDTV"),
            template("title", "year", "alt_title", "season_episode", "episode_title", "part", "edition", "repack", "resolution", "source", "audio", "video_encode"),
        ),
        NameRule(
            NameSelector(category="MOVIE", type="DVDRIP"),
            template("title", "alt_title", "year", "source", "video_encode", literal("DVDRip"), "audio"),
        ),
        NameRule(
            NameSelector(category="TV", type="DVDRIP"),
            template("title", "year", "alt_title", "season", "source", literal("DVDRip"), "audio", "video_encode"),
        ),
        NameRule(NameSelector(), template(literal(""))),
    ),
    transforms=(collapse_whitespace,),
)


class NameManager:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.common = Common(config=config)
        self.release_name_builder = ReleaseNameBuilder()

    async def get_name(self, meta: Meta) -> tuple[str, str, str, list[str]]:
        active_trackers: list[str] = [tracker for tracker in TRACKER_DISC_REQUIREMENTS if tracker in meta.trackers]
        if active_trackers:
            region, distributor, trackers_to_remove = await self.missing_disc_info(meta, active_trackers)
            for tracker in trackers_to_remove:
                if tracker in meta.trackers:
                    if meta.unattended:
                        logger.info("")
                        logger.info(f"[yellow]Removing tracker {tracker} due to missing distributor/region info.[/yellow]")
                    meta.trackers.remove(tracker)
            if distributor and "SKIPPED" not in distributor:
                meta.distributor = distributor
            if region and "SKIPPED" not in region:
                meta.region = region
        tag = meta.tag or ""
        if meta.debug:
            logger.debug("[cyan]get_name cat/type")
            logger.debug(f"CATEGORY: {meta.category}")
            logger.debug(f"TYPE: {meta.type}")
            logger.debug("[cyan]get_name meta:")
            # logger.debug(meta)

        name = ""
        potential_missing: list[str] = []
        if meta.manual_name is not None:
            name = str(meta.manual_name).strip()
        else:
            name, missing = await self.release_name_builder.render(
                meta,
                DEFAULT_NAME_PROFILE,
                lambda _context: self._default_name_overrides(meta),
            )
            potential_missing = list(missing)

        try:
            name = " ".join(name.split())
        except Exception:
            logger.info("[bold red]Unable to generate name. Please re-run and correct any of the following args if needed.")
            logger.info(f"--category [yellow]{meta.category}")
            logger.info(f"--type [yellow]{meta.type}")
            logger.info(f"--source [yellow]{meta.source}")
            logger.info("[bold green]If you specified type, try also specifying source")

            exit()
        name_notag = name

        tag_already_present = meta.category == "XXX" and bool(tag) and name_notag.casefold().endswith(tag.casefold())
        name = name_notag if meta.manual_name is not None or tag_already_present else name_notag + tag

        clean_name = await self.clean_filename(name)
        result = NameBuildResult(name_notag=name_notag, name=name, clean_name=clean_name, potential_missing=tuple(potential_missing))
        return result.name_notag, result.name, result.clean_name, list(result.potential_missing)

    def _default_name_overrides(self, meta: Meta) -> dict[str, str]:
        if meta.category == "BOOK":
            author = meta.author.strip()
            publisher = meta.publisher.strip()
            edition = str(meta.manual_edition or meta.edition or "").strip()
            if edition and not any(value in edition.lower() for value in ("edition", "ed.", "ed")) and not meta.audiobook:
                edition = f"{edition} Edition"
            language = meta.book_language.strip() or meta.book_language_iso.strip()
            language = "" if language.lower() in ("english", "eng", "en") else language.upper().replace("I", "i")
            source = meta.source or "".strip().upper()
            manual_source = str(meta.manual_source or "").strip().upper()
            if manual_source in ("RETAIL", "SCAN", "HYBRID"):
                source = manual_source
            if source not in ("RETAIL", "SCAN", "HYBRID"):
                source_name = (meta.uuid + " " + meta.title).lower()
                source = (
                    "SCAN"
                    if "scan" in source_name
                    else "HYBRiD"
                    if "hybrid" in source_name
                    else "RETAiL"
                    if "retail" in source_name
                    else "SCAN"
                    if str(meta.type).upper() == "PDF"
                    else "RETAiL"
                )
            else:
                source = {"RETAIL": "RETAiL", "HYBRID": "HYBRiD", "SCAN": "SCAN"}[source]
            book_format = str(meta.type).strip()
            book_format = "ePUB" if book_format.upper() == "EPUB" else "" if book_format.upper() == "PDF" else book_format.upper()
            volume = str(meta.manual_season or meta.season or "").strip()
            issue = str(meta.manual_episode or meta.episode or "").strip()
            return {
                "author": author,
                "author_or_publisher": author or publisher,
                "dash": "-",
                "title": meta.title.strip(),
                "book_series": f"{meta.book_series.strip()}:" if meta.book_series else "",
                "book_series_index": meta.book_series_index,
                "edition": edition,
                "year": str(meta.year).strip() if meta.year is not None else "",
                "book_language": language,
                "book_source": str(source),
                "book_format": book_format,
                "volume_label": f"Vol {volume}" if volume else "",
                "issue_label": f"No {issue}" if issue else "",
                "audiobook_label": "AUDIOBOOK",
                "comic_label": "COMiC",
                "manga_label": "MANGA",
                "magazine_label": "MAGAZiNE",
                "ebook_label": "eBOOK",
            }
        if meta.category == "GAME":
            languages = meta.languages or {}
            names = [name for name in languages if name]
            source_name = Path(str(meta.path or meta.uuid or "")).name.lower()
            force_multi = bool(meta.manual_multi)
            language = (
                f"MULTI{len(names)}"
                if len(names) > 1 and ("multi" in source_name or force_multi)
                else "MULTI"
                if force_multi
                else names[0].upper()
                if len(names) == 1 and names[0].upper() not in ("ENGLISH", "ENG", "EN")
                else ""
            )
            version = str(meta.game_version or "")
            if version and not version.lower().startswith("v"):
                version = f"v{version}"
            platform = str(meta.manual_platform or meta.platform or "").strip().upper()
            return {
                "title": meta.title.strip(),
                "edition": str(meta.manual_edition or meta.edition or "").strip(),
                "game_version": version,
                "year": str(meta.manual_year or meta.year or "").strip(),
                "game_language": language,
                "game_platform": platform if platform not in ("PC", "WINDOWS", "WIN") else "",
                "repack": str(meta.repack or ""),
            }
        if meta.category == "MUSIC":
            release = meta.music_release if isinstance(meta.music_release, dict) else {}
            tracks = release.get("tracks", []) if isinstance(release.get("tracks"), list) else []
            first = tracks[0] if tracks and isinstance(tracks[0], dict) else {}
            codec = self._music_codec(first.get("codec") or first.get("format") or meta.format or meta.type)
            depth = first.get("bit_depth") or self._music_release_field(release, "nfo_bit_depth")
            rate = first.get("sample_rate") or self._music_release_field(release, "nfo_sample_rate")
            return {
                "artist": str(self._music_release_field(release, "artist", meta.artist)),
                "dash": "-",
                "title": str(self._music_release_field(release, "album", meta.title)),
                "year": str(self._music_release_field(release, "release_year", self._music_release_field(release, "year", meta.year))),
                "music_source": self._music_source(self._music_release_field(release, "media", meta.source)),
                "music_codec": codec,
                "bit_depth": f"{depth}-bit" if depth and codec in {"FLAC", "ALAC"} else "",
                "sample_rate": f"{int(rate) / 1000:g} kHz" if rate and codec in {"FLAC", "ALAC"} else "",
            }
        return {}

    @staticmethod
    def _music_release_field(release: dict[str, Any], name: str, default: Any = "") -> Any:
        """Read a serialized MusicRelease field without its provenance."""
        fields = release.get("fields", {})
        value = fields.get(name, {}) if isinstance(fields, dict) else {}
        return value.get("value", default) if isinstance(value, dict) else default

    @staticmethod
    def _music_codec(value: Any) -> str:
        codec = str(value or "").upper().strip()
        aliases = {
            "OGG VORBIS": "VORBIS",
            "OGG": "VORBIS",
            "MPEG AUDIO": "MP3",
            "MPEG-4 AAC": "AAC",
            "M4A": "AAC",
        }
        return aliases.get(codec, codec)

    @staticmethod
    def _music_source(value: Any) -> str:
        source = str(value or "").strip().casefold()
        aliases = {
            "cd": "CD",
            "hdcd": "HDCD",
            "dts-cd": "DTS-CD",
            "dts cd": "DTS-CD",
            "8-track": "8-Track",
            "8 track": "8-Track",
            "vinyl": "Vinyl",
            "web": "WEB",
            "cassette": "Cassette",
        }
        return aliases.get(source, str(value or "").strip())

    async def clean_filename(self, name: str) -> str:
        invalid = '<>:"/\\|?*'
        for char in invalid:
            name = name.replace(char, "-")
        return name

    async def extract_title_and_year(self, meta: Meta, filename: str) -> tuple[str | None, str | None, str | None]:
        basename = Path(filename).stem

        secondary_title: str | None = None
        year: str | None = None

        # Check for AKA patterns first
        aka_patterns = [" AKA ", ".aka.", " aka ", ".AKA."]
        for pattern in aka_patterns:
            if pattern in basename:
                aka_parts = basename.split(pattern, 1)
                if len(aka_parts) > 1:
                    primary_title = aka_parts[0].strip()
                    secondary_part = aka_parts[1].strip()

                    # Look for a year in the primary title
                    year_match_primary = re.search(r"\b(19|20)\d{2}\b", primary_title)
                    if year_match_primary:
                        year = year_match_primary.group(0)

                    # Process secondary title
                    secondary_match = re.match(r"^(\d+)", secondary_part)
                    if secondary_match:
                        secondary_title = secondary_match.group(1)
                    else:
                        # Catch everything after AKA until it hits a year or release info
                        year_or_release_match = re.search(r"\b(19|20)\d{2}\b|\bBluRay\b|\bREMUX\b|\b\d+p\b|\bDTS-HD\b|\bAVC\b", secondary_part)
                        if year_or_release_match and re.match(r"\b(19|20)\d{2}\b", year_or_release_match.group(0)) and not year:
                            # If no year was found in primary title, or we want to override
                            year = year_or_release_match.group(0)

                            secondary_title = secondary_part[: year_or_release_match.start()].strip()
                        else:
                            secondary_title = secondary_part

                    primary_title = primary_title.replace(".", " ")
                    if secondary_title is not None:
                        secondary_title = secondary_title.replace(".", " ")
                    return primary_title, secondary_title, year

        # if not AKA, catch titles that begin with a year
        year_start_match = re.match(r"^(19|20)\d{2}", basename)
        if year_start_match:
            title = year_start_match.group(0)
            rest = basename[len(title) :].lstrip(". _-")
            # Look for another year in the rest of the title
            year_match = re.search(r"\b(19|20)\d{2}\b", rest)
            year = year_match.group(0) if year_match else None
            if year:
                return title, None, year

        folder_name = Path(meta.uuid).name if meta.uuid else ""
        logger.debug(f"[cyan]Extracting title and year from folder name: {folder_name}[/cyan]")
        # lets do some subsplease handling
        if "subsplease" in folder_name.lower():
            guess_data = guessit_fn(folder_name, {"excludes": ["country", "language"]})
            parsed = cast(dict[str, Any] | None, cast(Any, anitopy).parse(cast(str, guess_data.get("title", ""))))
            parsed_title = parsed.get("anime_title") if parsed else None
            if parsed_title:
                return str(parsed_title), None, None

        year_pattern = r"(18|19|20)\d{2}"
        res_pattern = r"\b(480|576|720|1080|2160)[pi]\b"
        type_pattern = r"(WEBDL|BluRay|REMUX|HDRip|Blu-Ray|Web-DL|webrip|web-rip|DVD|BD100|BD50|BD25|HDTV|UHD|HDR|DOVI|REPACK|Season)(?=[._\-\s]|$)"
        season_pattern = r"\bS(\d{1,3})\b"
        season_episode_pattern = r"\bS(\d{1,3})E(\d{1,3})\b"
        date_pattern = r"\b(20\d{2})\.(\d{1,2})\.(\d{1,2})\b"
        extension_pattern = r"\.(mkv|mp4)$"

        # Check for the specific pattern: year.year (e.g., "1970.2014")
        double_year_pattern = r"\b(18|19|20)\d{2}\.(18|19|20)\d{2}\b"
        double_year_match = re.search(double_year_pattern, folder_name)
        actual_year: str | None = None

        if double_year_match:
            full_match = double_year_match.group(0)
            years = full_match.split(".")
            first_year = years[0]
            second_year = years[1]

            logger.debug(f"[cyan]Found double year pattern: {full_match}, using {second_year} as year[/cyan]")

            modified_folder_name = folder_name.replace(full_match, first_year)
            year_match = None
            res_match = re.search(res_pattern, modified_folder_name, re.IGNORECASE)
            season_pattern_match = re.search(season_pattern, modified_folder_name, re.IGNORECASE)
            season_episode_match = re.search(season_episode_pattern, modified_folder_name, re.IGNORECASE)
            extension_match = re.search(extension_pattern, modified_folder_name, re.IGNORECASE)
            type_match = re.search(type_pattern, modified_folder_name, re.IGNORECASE)

            # If the folder starts with YYYY.YYYY (e.g. "1917.2019..."), the first year is the title.
            # Otherwise, treat the match as a delimiter after a normal title (e.g. "Some.Movie.1982.2011...").
            year_boundary = double_year_match.start() + len(first_year) if double_year_match.start() == 0 else double_year_match.start()
            indices: list[tuple[str, int, str]] = [("year", year_boundary, second_year)]
            if res_match:
                indices.append(("res", res_match.start(), res_match.group()))
            if season_pattern_match:
                indices.append(("season", season_pattern_match.start(), season_pattern_match.group()))
            if season_episode_match:
                indices.append(("season_episode", season_episode_match.start(), season_episode_match.group()))
            if extension_match:
                indices.append(("extension", extension_match.start(), extension_match.group()))
            if type_match:
                indices.append(("type", type_match.start(), type_match.group()))

            folder_name_for_title = modified_folder_name
            actual_year = second_year

        else:
            date_match = re.search(date_pattern, folder_name)
            year_match = re.search(year_pattern, folder_name)
            res_match = re.search(res_pattern, folder_name, re.IGNORECASE)
            season_pattern_match = re.search(season_pattern, folder_name, re.IGNORECASE)
            season_episode_match = re.search(season_episode_pattern, folder_name, re.IGNORECASE)
            extension_match = re.search(extension_pattern, folder_name, re.IGNORECASE)
            type_match = re.search(type_pattern, folder_name, re.IGNORECASE)

            indices: list[tuple[str, int, str]] = []
            if date_match:
                indices.append(("date", date_match.start(), date_match.group()))
            if year_match and not date_match:
                indices.append(("year", year_match.start(), year_match.group()))
            if res_match:
                indices.append(("res", res_match.start(), res_match.group()))
            if season_pattern_match:
                indices.append(("season", season_pattern_match.start(), season_pattern_match.group()))
            if season_episode_match:
                indices.append(("season_episode", season_episode_match.start(), season_episode_match.group()))
            if extension_match:
                indices.append(("extension", extension_match.start(), extension_match.group()))
            if type_match:
                indices.append(("type", type_match.start(), type_match.group()))

            folder_name_for_title = folder_name
            actual_year = year_match.group() if year_match and not date_match else None

        if indices:
            indices.sort(key=lambda x: x[1])
            _first_type, first_index, _first_value = indices[0]
            title_part = folder_name_for_title[:first_index]
            title_part = re.sub(r"[\.\-_ ]+$", "", title_part)
            # Handle unmatched opening parenthesis
            if title_part.count("(") > title_part.count(")"):
                paren_pos = title_part.rfind("(")
                content_after_paren = folder_name_for_title[paren_pos + 1 : first_index].strip()

                if content_after_paren:
                    secondary_title = content_after_paren

                title_part = title_part[:paren_pos].rstrip()
        else:
            title_part = folder_name

        replacements = {
            "_": " ",
            ".": " ",
            "DVD9": "",
            "DVD5": "",
            "DVDR": "",
            "BDR": "",
            "HDDVD": "",
            "WEB-DL": "",
            "WEBRip": "",
            "WEB": "",
            "BluRay": "",
            "Blu-ray": "",
            "HDTV": "",
            "DVDRip": "",
            "REMUX": "",
            "HDR": "",
            "UHD": "",
            "4K": "",
            "DVD": "",
            "HDRip": "",
            "BDMV": "",
            "R1": "",
            "R2": "",
            "R3": "",
            "R4": "",
            "R5": "",
            "R6": "",
            "Director's Cut": "",
            "Extended Edition": "",
            "directors cut": "",
            "director cut": "",
            "itunes": "",
        }
        filename = re.sub(r"\s+", " ", filename)
        filename = await self.multi_replace(title_part, replacements)
        processed_secondary = await self.multi_replace(secondary_title or "", replacements)
        secondary_title = processed_secondary if processed_secondary else None
        if filename:
            # Look for content in parentheses
            bracket_pattern = r"\s*\(([^)]+)\)\s*"
            bracket_match = re.search(bracket_pattern, filename)

            if bracket_match:
                bracket_content = bracket_match.group(1).strip()
                bracket_content = await self.multi_replace(bracket_content, replacements)

                # Only add to secondary_title if we don't already have one
                if not secondary_title and bracket_content:
                    secondary_title = bracket_content
                    secondary_title = re.sub(r"[\.\-_ ]+$", "", secondary_title)

                filename = re.sub(bracket_pattern, " ", filename)
                filename = re.sub(r"\s+", " ", filename).strip()

        if filename:
            return filename, secondary_title, actual_year

        # If no pattern match works but there's still a year in the filename, extract it
        year_match = re.search(r"(?<!\d)(19|20)\d{2}(?!\d)", basename)
        if year_match:
            year = year_match.group(0)
            return None, None, year

        return None, None, None

    async def multi_replace(self, text: str, replacements: dict[str, str]) -> str:
        for old, new in replacements.items():
            text = re.sub(re.escape(old), new, text, flags=re.IGNORECASE)
        return text

    async def missing_disc_info(self, meta: Meta, active_trackers: Sequence[str]) -> tuple[str, str, list[str]]:
        distributor_id = await self.common.unit3d_distributor_ids(meta.distributor)
        region_id = await self.common.unit3d_region_ids(str(meta.region))
        region_name = str(meta.region)
        distributor_name = meta.distributor
        trackers_to_remove: list[str] = []

        if meta.is_disc == "BDMV":
            strictest = {"region": "optional", "distributor": "optional"}
            for tracker in active_trackers:
                requirements = TRACKER_DISC_REQUIREMENTS.get(tracker, {})
                if requirements.get("region") == "mandatory":
                    strictest["region"] = "mandatory"
                if requirements.get("distributor") == "mandatory":
                    strictest["distributor"] = "mandatory"
            if not region_id:
                region_name = await self._prompt_for_field(meta, "Region code", strictest["region"] == "mandatory")
                if region_name and region_name != "SKIPPED":
                    region_id = await self.common.unit3d_region_ids(region_name)
            if not distributor_id:
                distributor_name = await self._prompt_for_field(meta, "Distributor", strictest["distributor"] == "mandatory")
                if distributor_name and distributor_name != "SKIPPED":
                    logger.info(f"Looking up distributor ID for: {distributor_name}")
                    distributor_id = await self.common.unit3d_distributor_ids(distributor_name)
                    logger.info(f"Found distributor ID: {distributor_id}")

            for tracker in active_trackers:
                requirements = TRACKER_DISC_REQUIREMENTS.get(tracker, {})
                if (requirements.get("region") == "mandatory" and region_name == "SKIPPED") or (
                    requirements.get("distributor") == "mandatory" and distributor_name == "SKIPPED"
                ):
                    trackers_to_remove.append(tracker)

        return region_name, distributor_name, trackers_to_remove

    async def _prompt_for_field(self, meta: Meta, field_name: str, is_mandatory: bool) -> str:
        """Prompt user for disc field with appropriate mandatory/optional text."""
        if meta.unattended and not meta.unattended_confirm:
            return "SKIPPED"
        suffix = " (MANDATORY): " if is_mandatory else " (optional, press Enter to skip): "
        prompt = f"{field_name} not found for disc. Please enter it manually{suffix}"
        try:
            value = cli_ui.ask_string(prompt)
            return value.upper() if value else "SKIPPED"
        except EOFError:
            logger.info("\n[red]Exiting on user request (Ctrl+C)[/red]")
            await cleanup_manager.cleanup()
            cleanup_manager.reset_terminal()
            sys.exit(1)
