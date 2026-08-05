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


class NameManager:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.common = Common(config=config)

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
        type = str(meta.type).upper()
        title = meta.title
        alt_title = meta.aka
        year = str(meta.year) if meta.year is not None else ""
        manual_year_value = meta.manual_year
        if manual_year_value is not None and manual_year_value > 0:
            year = str(manual_year_value)
        resolution = meta.resolution
        if resolution == "OTHER":
            resolution = ""
        audio = meta.audio
        service = str(meta.service)
        season = str(meta.season)
        episode = meta.episode
        part = meta.part
        repack = meta.repack
        three_d = meta.three_d
        tag = meta.tag or ""
        source = str(meta.source)
        uhd = str(meta.uhd)
        hdr = meta.hdr
        hybrid = "Hybrid" if meta.webdv else ""
        if meta.manual_episode_title:
            episode_title = meta.manual_episode_title
        elif meta.daily_episode_title:
            episode_title = meta.daily_episode_title
        else:
            episode_title = ""
        video_codec = ""
        video_encode = ""
        region = ""
        dvd_size = ""
        if meta.is_disc == "BDMV":  # Disk
            video_codec = meta.video_codec
            region = str(meta.region or "")
        elif meta.is_disc == "DVD":
            region = str(meta.region or "")
            dvd_size = meta.dvd_size
        else:
            video_codec = meta.video_codec
            video_encode = meta.video_encode
        edition = meta.edition
        if "hybrid" in edition.upper():
            edition = edition.replace("Hybrid", "").strip()

        if meta.category == "TV":
            year = str(meta.year) if (meta.year is not None and meta.search_year != "") else ""
            if meta.manual_date:
                # Ignore season and year for --daily flagged shows, just use manual date stored in episode_name
                season = ""
                episode = ""
        if meta.no_season is True:
            season = ""
        if meta.no_year is True:
            year = ""
        if meta.no_aka is True:
            alt_title = ""
        if meta.debug:
            logger.debug("[cyan]get_name cat/type")
            logger.debug(f"CATEGORY: {meta.category}")
            logger.debug(f"TYPE: {meta.type}")
            logger.debug("[cyan]get_name meta:")
            # logger.debug(meta)

        # YAY NAMING FUN
        name = ""
        potential_missing: list[str] = []
        if meta.category == "MOVIE":  # MOVIE SPECIFIC
            if type == "DISC":  # Disk
                if meta.is_disc == "BDMV":
                    name = f"{title} {alt_title} {year} {three_d} {edition} {hybrid} {repack} {resolution} {region} {uhd} {source} {hdr} {video_codec} {audio}"
                    potential_missing = ["edition", "region", "distributor"]
                elif meta.is_disc == "DVD":
                    name = f"{title} {alt_title} {year} {repack} {edition} {region} {source} {dvd_size} {audio}"
                    potential_missing = ["edition", "distributor"]
                elif meta.is_disc == "HDDVD":
                    name = f"{title} {alt_title} {year} {edition} {repack} {resolution} {source} {video_codec} {audio}"
                    potential_missing = ["edition", "region", "distributor"]
            elif type == "REMUX" and source in ("BluRay", "HDDVD"):  # BluRay/HDDVD Remux
                name = f"{title} {alt_title} {year} {three_d} {edition} {hybrid} {repack} {resolution} {uhd} {source} REMUX {hdr} {video_codec} {audio}"
                potential_missing = ["edition", "description"]
            elif type == "REMUX" and source in ("PAL DVD", "NTSC DVD", "DVD"):  # DVD Remux
                name = f"{title} {alt_title} {year} {edition} {repack} {source} REMUX  {audio}"
                potential_missing = ["edition", "description"]
            elif type == "ENCODE":  # Encode
                name = f"{title} {alt_title} {year} {edition} {hybrid} {repack} {resolution} {uhd} {source} {audio} {hdr} {video_encode}"
                potential_missing = ["edition", "description"]
            elif type == "WEBDL":  # WEB-DL
                name = f"{title} {alt_title} {year} {edition} {hybrid} {repack} {resolution} {uhd} {service} WEB-DL {audio} {hdr} {video_encode}"
                potential_missing = ["edition", "service"]
            elif type == "WEBRIP":  # WEBRip
                name = f"{title} {alt_title} {year} {edition} {hybrid} {repack} {resolution} {uhd} {service} WEBRip {audio} {hdr} {video_encode}"
                potential_missing = ["edition", "service"]
            elif type == "HDTV":  # HDTV
                name = f"{title} {alt_title} {year} {edition} {repack} {resolution} {source} {audio} {video_encode}"
                potential_missing = []
            elif type == "DVDRIP":
                name = f"{title} {alt_title} {year} {source} {video_encode} DVDRip {audio}"
                potential_missing = []
        elif meta.category == "TV":  # TV SPECIFIC
            if type == "DISC":  # Disk
                if meta.is_disc == "BDMV":
                    name = (
                        f"{title} {year} {alt_title} {season}{episode} {three_d} {edition} {hybrid} {repack} {resolution} {region} {uhd} {source} {hdr} {video_codec} {audio}"
                    )
                    potential_missing = ["edition", "region", "distributor"]
                if meta.is_disc == "DVD":
                    name = f"{title} {year} {alt_title} {season}{episode}{three_d} {repack} {edition} {region} {source} {dvd_size} {audio}"
                    potential_missing = ["edition", "distributor"]
                elif meta.is_disc == "HDDVD":
                    name = f"{title} {alt_title} {year} {edition} {repack} {resolution} {source} {video_codec} {audio}"
                    potential_missing = ["edition", "region", "distributor"]
            elif type == "REMUX" and source in ("BluRay", "HDDVD"):  # BluRay Remux
                name = f"{title} {year} {alt_title} {season}{episode} {episode_title} {part} {three_d} {edition} {hybrid} {repack} {resolution} {uhd} {source} REMUX {hdr} {video_codec} {audio}"  # SOURCE
                potential_missing = ["edition", "description"]
            elif type == "REMUX" and source in ("PAL DVD", "NTSC DVD", "DVD"):  # DVD Remux
                name = f"{title} {year} {alt_title} {season}{episode} {episode_title} {part} {edition} {repack} {source} REMUX {audio}"  # SOURCE
                potential_missing = ["edition", "description"]
            elif type == "ENCODE":  # Encode
                name = f"{title} {year} {alt_title} {season}{episode} {episode_title} {part} {edition} {hybrid} {repack} {resolution} {uhd} {source} {audio} {hdr} {video_encode}"  # SOURCE
                potential_missing = ["edition", "description"]
            elif type == "WEBDL":  # WEB-DL
                name = f"{title} {year} {alt_title} {season}{episode} {episode_title} {part} {edition} {hybrid} {repack} {resolution} {uhd} {service} WEB-DL {audio} {hdr} {video_encode}"
                potential_missing = ["edition", "service"]
            elif type == "WEBRIP":  # WEBRip
                name = f"{title} {year} {alt_title} {season}{episode} {episode_title} {part} {edition} {hybrid} {repack} {resolution} {uhd} {service} WEBRip {audio} {hdr} {video_encode}"
                potential_missing = ["edition", "service"]
            elif type == "HDTV":  # HDTV
                name = f"{title} {year} {alt_title} {season}{episode} {episode_title} {part} {edition} {repack} {resolution} {source} {audio} {video_encode}"
                potential_missing = []
            elif type == "DVDRIP":
                name = f"{title} {year} {alt_title} {season} {source} DVDRip {audio} {video_encode}"
                potential_missing = []
        elif meta.category == "BOOK":
            name = self.extract_book_name(meta)
            potential_missing = []
        elif meta.category == "GAME":
            name = self.extract_game_name(meta)
            potential_missing = []
        elif meta.category == "MUSIC":
            name = self.extract_music_name(meta)
            potential_missing = []
        elif meta.category == "PODCAST":
            name = meta.podcast_title or meta.name or meta.title
            potential_missing = []

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

        name = name_notag + tag

        clean_name = await self.clean_filename(name)
        return name_notag, name, clean_name, potential_missing

    def extract_book_name(self, meta: Meta) -> str:
        comic = meta.comic
        manga = meta.manga
        magazine = meta.magazine
        newspaper = meta.newspaper
        audiobook = meta.audiobook

        author = meta.author.strip()
        publisher = meta.publisher.strip()
        title = meta.title.strip()
        year = str(meta.year).strip() if meta.year is not None else ""

        # Edition/Issue logic
        edition = str(meta.manual_edition or meta.edition or "").strip()
        if edition and not any(x in edition.lower() for x in ["edition", "ed.", "ed"]) and not audiobook:
            edition = f"{edition} Edition"

        volume = str(meta.manual_season or meta.season or "").strip()
        issue = str(meta.manual_episode or meta.episode or "").strip()

        # Language logic (needed for non-English only)
        book_language = meta.book_language.strip()
        book_language_iso = meta.book_language_iso.strip()
        lang_display = book_language or book_language_iso
        lang_display = "" if lang_display.lower() in ("english", "eng", "en") else lang_display.upper().replace("I", "i")

        # Source logic: RETAiL, SCAN, HYBRiD
        source = meta.source or "".strip().upper()
        manual_source = str(meta.manual_source or "").strip().upper()
        if manual_source in ("RETAIL", "SCAN", "HYBRID"):
            source = manual_source

        if source not in ("RETAIL", "SCAN", "HYBRID"):
            filename_lower = (meta.uuid + " " + meta.title).lower()
            if "scan" in filename_lower:
                source = "SCAN"
            elif "hybrid" in filename_lower:
                source = "HYBRiD"
            elif "retail" in filename_lower:
                source = "RETAiL"
            else:
                ext = str(meta.type).upper()
                source = "SCAN" if ext == "PDF" else "RETAiL"
        else:
            if source == "RETAIL":
                source = "RETAiL"
            elif source == "HYBRID":
                source = "HYBRiD"
            elif source == "SCAN":
                source = "SCAN"

        # Format logic
        ebook_type = str(meta.type).strip()
        if ebook_type.upper() == "EPUB":
            ebook_type = "ePUB"
        elif ebook_type.upper() == "PDF":
            ebook_type = ""  # PDF format tag is omitted per rules.txt
        else:
            ebook_type = ebook_type.upper()

        # Construct final string parts based on subtype
        parts = []

        if audiobook:
            parts.extend([author, "-", title, edition, year, lang_display, "AUDIOBOOK"])
        elif comic:
            vol_str = f"Vol {volume}" if volume else ""
            no_str = f"No {issue}" if issue else ""
            parts.extend([title, vol_str, no_str, year, lang_display, source, ebook_type, "COMiC", "eBOOK"])
        elif manga:
            vol_str = f"Vol {volume}" if volume else ""
            parts.extend([title, vol_str, year, lang_display, source, ebook_type, "MANGA", "eBOOK"])
        elif magazine:
            no_str = f"No {issue}" if issue else ""
            parts.extend([title, no_str, year, lang_display, source, ebook_type, "MAGAZiNE", "eBOOK"])
        elif newspaper:
            parts.extend([title, year, lang_display, source, ebook_type, "eBOOK"])
        else:
            author_or_publisher = author or publisher
            parts.extend([author_or_publisher, "-", title, edition, year, lang_display, source, ebook_type, "eBOOK"])

        cleaned_parts = [p for p in parts if p]
        base_name = " ".join(cleaned_parts)
        return " ".join(base_name.split())

    def extract_game_name(self, meta: Meta) -> str:
        """Build a game release name losely based on the SCENE 2021_GAMEiSO ruleset."""
        title = meta.title.strip()
        edition = str(meta.manual_edition or meta.edition or "").strip()
        year = str(meta.manual_year or meta.year or "").strip()
        platform = str(meta.manual_platform or meta.platform or "").strip().upper()
        game_version = meta.game_version or "".strip()
        repack = meta.repack or "".strip().upper()
        force_multi = bool(meta.manual_multi)

        #  language / MULTI tag
        languages: dict[str, Any] | list[Any] = meta.languages or {}
        lang_names: list[str] = [k for k in languages if k]
        lang_count = len(lang_names)

        # Detect "multi" in the original source directory/file name
        source_path = str(meta.path or meta.uuid or "")
        source_basename = Path(source_path).name.lower()
        source_has_multi = "multi" in source_basename

        lang_tag = ""
        if lang_count > 1 and (source_has_multi or force_multi):
            # MULTI<N> — only when the source name explicitly declares MULTI
            lang_tag = f"MULTI{lang_count}"
        elif force_multi:
            lang_tag = "MULTI"
        elif lang_count == 1:
            single = lang_names[0].upper()
            # Scene only tags non-English single-language releases
            if single not in ("ENGLISH", "ENG", "EN"):
                lang_tag = single

        # build ordered token list
        tokens: list[str] = [title]

        # Edition (e.g. "Definitive Edition", "GOTY")
        if edition:
            tokens.append(edition)

        # Version / Update tag  →  "Update v1.2.3"
        if game_version:
            # Normalise: ensure leading 'v'
            ver = game_version if game_version.lower().startswith("v") else f"v{game_version}"
            tokens.append(ver)

        # Year - scene rarely includes year in the dirname, but keep it if present
        if year:
            tokens.append(year)

        # Language tag (MULTI<N> or LANGUAGE)
        if lang_tag:
            tokens.append(lang_tag)

        # Platform tag - only for non-PC releases (PC is implicit for GAMEiSO)
        if platform and platform not in ("PC", "WINDOWS", "WIN"):
            tokens.append(platform)

        # REPACK / PROPER / etc.
        if repack:
            tokens.append(repack)

        base_name = " ".join(t for t in tokens if t)
        # Final safety: collapse any double spaces
        return re.sub(r"\.{2,}", " ", base_name)

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

    def extract_music_name(self, meta: Meta) -> str:
        """Build MUSIC names with the LST Discogs-based naming convention."""
        release = meta.music_release if isinstance(meta.music_release, dict) else {}
        artist = self._music_release_field(release, "artist", meta.artist)
        title = self._music_release_field(release, "album", meta.title)
        year = self._music_release_field(release, "release_year", self._music_release_field(release, "year", meta.year))
        source = self._music_source(self._music_release_field(release, "media", meta.source))
        tracks = release.get("tracks", []) if isinstance(release.get("tracks"), list) else []
        first_track = tracks[0] if tracks and isinstance(tracks[0], dict) else {}
        codec = self._music_codec(first_track.get("codec") or first_track.get("format") or meta.format or meta.type)
        parts = [str(artist), "-", str(title), str(year), source, codec]

        # LST omits technical PCM fields for lossy codecs.
        if codec in {"FLAC", "ALAC"}:
            depth = first_track.get("bit_depth") or self._music_release_field(release, "nfo_bit_depth")
            rate = first_track.get("sample_rate") or self._music_release_field(release, "nfo_sample_rate")
            if depth:
                parts.append(f"{depth}-bit")
            if rate:
                parts.append(f"{int(rate) / 1000:g} kHz")
        return " ".join(part.strip() for part in parts if str(part or "").strip())

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
