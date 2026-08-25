# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import re
from pathlib import Path
from typing import Any, cast

import cli_ui
import pycountry

from src.console import logger, prompt_in_thread
from src.languages import languages_manager
from src.meta import Meta
from src.trackers.common import Common
from src.trackers.UNIT3D import UNIT3D


class RocketHD(UNIT3D):
    """
    RocketHD (RHD) is a Private Torrent Tracker
    """

    tracker = "ROCKETHD"
    display_name = "RocketHD"
    supported_categories = ("MOVIE", "TV")
    base_url = "https://rocket-hd.cc"
    id_url = f"{base_url}/api/torrents/"
    upload_url = f"{base_url}/api/torrents/upload"
    search_url = f"{base_url}/api/torrents/filter"
    requests_url = f"{base_url}/api/requests/filter"
    torrent_url = f"{base_url}/torrents/"
    tracker_urls = ("https://rocket-hd.cc",)

    banned_groups = (
        "1XBET",
        "MEGA",
        "MTZ",
        "Whistler",
        "WOTT",
        "Taylor.D",
        "HELD",
        "FSX",
        "FuN",
        "MagicX",
        "w00t",
        "PaTroL",
        "BB",
        "266ers",
        "GTF",
        "JellyfinPlex",
        "2BA",
        "FritzBox",
        "FUNXDTV",
    )

    INVALID_TAG_PATTERN = re.compile(r"^(nogrp|nogroup|unknown|unk)$", re.IGNORECASE)
    WHITESPACE_PATTERN = re.compile(r"\s{2,}")
    MARKER_PATTERN = re.compile(r"\b(UNTOUCHED|VU1080|VU720|VU)\b", re.IGNORECASE)

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config, tracker_name=self.tracker)
        self.config = config
        self.common = Common(config)

    async def get_resolution_id(
        self,
        meta: Meta,
        resolution: str = "",
        reverse: bool = False,
        mapping_only: bool = False,
    ) -> dict[str, str]:
        """map each resolution to the correct id on the tracker"""
        resolution_id = {
            "8640p": "10",
            "4320p": "1",
            "2160p": "2",
            "1440p": "3",
            "1080p": "3",
            "1080i": "4",
            "720p": "5",
            "576p": "12",
            "576i": "13",
            "540p": "16",
            "480p": "11",
            "480i": "18",
            "384p": "14",
        }
        if mapping_only:
            return resolution_id
        if reverse:
            return {v: k for k, v in resolution_id.items()}
        if resolution:
            return {"resolution_id": resolution_id.get(resolution, "10")}
        meta_resolution = str(meta.resolution)
        resolved_id = resolution_id.get(meta_resolution, "10")
        return {"resolution_id": resolved_id}

    def get_basename(self, meta: Meta) -> str:
        """Extract basename from first file in filelist or path"""
        path_value = meta.path or "" if meta.isdir else next(iter(meta.filelist), meta.path or "")
        path = path_value if isinstance(path_value, str) else ""
        return Path(path).name

    def _get_language_code(self, track_or_string: Any) -> str:
        """Extract and normalize language to ISO alpha-2 code"""
        if isinstance(track_or_string, dict):
            track_dict = cast(dict[str, Any], track_or_string)
            lang = track_dict.get("Language", "")
            if isinstance(lang, dict):
                lang = cast(dict[str, Any], lang).get("String", "")
        else:
            lang = track_or_string
        if not lang:
            return ""
        lang_str = str(lang).lower()

        # Strip country code if present (e.g., "en-US" → "en")
        if "-" in lang_str:
            lang_str = lang_str.split("-")[0]

        if len(lang_str) == 2:
            return lang_str
        try:
            lang_obj = pycountry.languages.get(name=lang_str.title()) or pycountry.languages.get(alpha_2=lang_str) or pycountry.languages.get(alpha_3=lang_str)
            return lang_obj.alpha_2.lower() if lang_obj else lang_str
        except AttributeError, KeyError, LookupError:
            return lang_str

    def _get_german_title(self, imdb_info: dict[str, Any]) -> str | None:
        """Extract German title from IMDb AKAs with priority"""
        country_match: str | None = None
        language_match: str | None = None

        akas_value = imdb_info.get("akas", [])
        akas = cast(list[dict[str, Any]], akas_value) if isinstance(akas_value, list) else []
        for aka in akas:
            if aka.get("country") == "Germany" and not aka.get("attributes"):
                title = aka.get("title")
                if isinstance(title, str):
                    country_match = title
                    break  # Country match takes priority
            elif aka.get("language") == "German" and not language_match and not aka.get("attributes"):
                title = aka.get("title")
                if isinstance(title, str):
                    language_match = title

        return country_match or language_match

    def _has_german_audio(self, meta: Meta) -> bool:
        """Check for German audio tracks, excluding commentary"""
        mediainfo = meta.mediainfo
        if not mediainfo:
            return False

        tracks = mediainfo.get("media", {}).get("track", [])
        return any(track.get("@type") == "Audio" and self._get_language_code(track) in {"de"} and "commentary" not in str(track.get("Title", "")).lower() for track in tracks)

    def _has_german_subtitles(self, meta: Meta) -> bool:
        """Check for German subtitle tracks"""
        mediainfo = meta.mediainfo
        if not mediainfo:
            return False

        tracks = mediainfo.get("media", {}).get("track", [])
        return any(track.get("@type") == "Text" and self._get_language_code(track) in {"de"} for track in tracks)

    def _get_language_name(self, iso_code: str) -> str:
        """Convert ISO language code to full name (e.g. GERMAN, ENGLISH)"""
        if not iso_code:
            return ""

        iso_lower = iso_code.lower()

        # Try full language name (Italian, English, etc)
        lang = pycountry.languages.get(name=iso_code.title())
        if lang and hasattr(lang, "name"):
            return str(lang.name).upper()

        # Try alpha_2 (IT, EN, etc)
        lang = pycountry.languages.get(alpha_2=iso_lower)
        if lang and hasattr(lang, "name"):
            return str(lang.name).upper()

        # Try alpha_3 (ITA, ENG, etc)
        lang = pycountry.languages.get(alpha_3=iso_lower)
        if lang and hasattr(lang, "name"):
            return str(lang.name).upper()

        return iso_code.upper()

    async def get_name(self, meta: Meta) -> dict[str, str]:
        """
        Rebuild release name from meta components following RocketHD naming rules.
        """
        if not meta.language_checked:
            await languages_manager.process_desc_language(meta, tracker=self.tracker)

        # Title and basic info
        title = meta.title
        german_title = self._get_german_title(meta.imdb_info)
        use_german_title = self.config["TRACKERS"].get(self.tracker, {}).get("use_german_title", False)
        if german_title and use_german_title:
            title = german_title

        year_value: Any = meta.year or ""
        resolution_value: Any = meta.resolution
        source_value: Any = meta.source or ""
        year = str(year_value)
        resolution = str(resolution_value)
        source = (str(cast(Any, source_value[0])) if source_value else "") if isinstance(source_value, list) else str(source_value)
        video_codec = meta.video_codec
        video_encode = meta.video_encode

        # TV specific
        season = str(meta.season or "")
        episode = str(meta.episode or "")

        # Optional fields
        edition = meta.edition
        hdr = meta.hdr
        uhd = str(meta.uhd or "")
        three_d = meta.three_d

        # extract tags from basename for potential later use
        basename_up = self.get_basename(meta).upper()
        internal = "iNTERNAL" if "INTERNAL" in basename_up else ""
        incomplete = "INCOMPLETE" if "INCOMPLETE" in basename_up else ""

        # Clean audio: remove Dual-Audio and trailing language codes
        audio = meta.audio
        if "DD+" in audio:
            audio = audio.replace("DD+", "DDP")

        # Build audio language tag
        audio_lang_str = ""
        if meta.audio_languages:
            # Normalize all to abbreviated ISO 639-3 codes
            audio_langs_value = meta.audio_languages
            audio_langs_raw = cast(list[Any], audio_langs_value) if isinstance(audio_langs_value, list) else []
            audio_langs = [self._get_language_name(str(lang)) for lang in audio_langs_raw]
            audio_langs = [lang for lang in audio_langs if lang]  # Remove empty
            audio_langs = list(dict.fromkeys(audio_langs))  # Dedupe preserving order

            num_langs = len(audio_langs)

            if num_langs == 1:
                # One language (GERMAN or non-GERMAN)
                audio_lang_str = audio_langs[0]

            elif num_langs == 2:
                # Two languages ("GERMAN DL" if GERMAN is present, "[lang] DL" if not)
                if "GERMAN" in audio_langs:
                    audio_lang_str = "GERMAN DL"
                elif "ENGLISH" in audio_langs:
                    audio_lang_str = "ENGLISH DL"
                else:
                    audio_lang_str = f"{audio_langs[0]} DL"

            elif num_langs >= 3:
                # Three or more languages, "GERMAN ML" if GERMAN is present, "MULTI" only if not)
                audio_lang_str = "GERMAN ML" if "GERMAN" in audio_langs else "MULTI"

        # Add [GERMAN SUBBED] for German subtitles without German audio
        if not self._has_german_audio(meta) and self._has_german_subtitles(meta):
            audio_lang_str = "GERMAN SUBBED"

        effective_type = str(meta.type or "")

        source = source.replace("Blu-ray", "BluRay")

        # Detect Hybrid from filename if not in title
        hybrid = ""
        if not edition and (meta.webdv or isinstance(meta.source, list)) and "HYBRID" not in title.upper():
            hybrid = "Hybrid"

        repack = meta.repack.strip()

        name = None
        # Build name per RocketHD type-specific format
        if effective_type == "DISC":
            region = meta.region
            dvd_size = meta.dvd_size
            name = (
                f"{title} {year} {season}{episode} {three_d} {edition} {repack} {resolution} COMPLETE {region} {uhd} {source} {dvd_size} {audio} {hdr} {video_codec} {internal}"
            )
        elif effective_type == "REMUX":
            name = f"{title} {year} {season}{episode} {incomplete} {three_d} {edition} {hybrid} {audio_lang_str} {repack} {resolution} {uhd} {source} REMUX {audio} {hdr} {video_codec} {internal}"
        elif effective_type in ("DVDRIP", "BRRIP"):
            type_str = "DVDRip" if effective_type == "DVDRIP" else "BRRip"
            name = f"{title} {year} {season}{episode} {incomplete} {three_d} {edition} {hybrid} {audio_lang_str} {repack} {resolution} {type_str} {audio} {hdr} {video_encode} {internal}"
        elif effective_type in ("ENCODE", "HDTV"):
            name = f"{title} {year} {season}{episode} {incomplete} {three_d} {edition} {hybrid} {audio_lang_str} {repack} {resolution} {uhd} {source} {audio} {hdr} {video_encode} {internal}"
        elif effective_type in ("WEBDL", "WEBRIP"):
            service = str(meta.service or "")
            type_str = "WEB-DL" if effective_type == "WEBDL" else "WEBRip"
            name = f"{title} {year} {season}{episode} {incomplete} {three_d} {edition} {hybrid} {audio_lang_str} {repack} {resolution} {uhd} {service} {type_str} {audio} {hdr} {video_encode} {internal}"
        else:
            logger.info(f"{self.tracker}: [bold red]Name enrichment failed. Please manually update the name after Uploading.[/bold red]")

        # Ensure name is always a string
        if not name:
            name = meta.name or "UNKNOWN"

        # Remove any leftover "Dual-Audio" markers
        if "Dual-Audio" in name:
            name = name.replace("Dual-Audio", "").strip()

        # Cleanup whitespace
        name = self.WHITESPACE_PATTERN.sub(" ", name).strip()

        # Extract tag and append if valid
        tag = self._extract_clean_release_group(meta)
        if tag:
            name = f"{name}-{tag}"

        return {"name": name}

    def _extract_clean_release_group(self, meta: Meta) -> str:
        """Extract release group - only accepts VU/UNTOUCHED markers from filename"""
        raw_tag = meta.tag or ""
        tag = raw_tag.strip().lstrip("-") if isinstance(raw_tag, str) else ""
        if tag and " " not in tag and not self.INVALID_TAG_PATTERN.search(tag):
            return tag

        basename = self.get_basename(meta)
        # Get extension from mediainfo and remove it
        ext = meta.mediainfo.get("media", {}).get("track", [{}])[0].get("FileExtension", "")
        name_no_ext = basename[: -len(ext) - 1] if ext and basename.endswith(f".{ext}") else basename
        parts = re.split(r"[-.]", name_no_ext)
        if not parts:
            return "NOGRP"

        potential_tag = parts[-1].strip()
        # Handle space-separated components
        if " " in potential_tag:
            potential_tag = potential_tag.split()[-1]

        if not potential_tag or len(potential_tag) > 30 or not potential_tag.replace("_", "").isalnum():
            return "NOGRP"

        # ONLY accept if it's a VU/UNTOUCHED marker
        if not self.MARKER_PATTERN.search(potential_tag):
            return "NOGRP"

        return potential_tag

    async def get_additional_checks(self, meta: Meta) -> bool:
        """make sure the upload complies with the RHD rules"""
        # Uploading MIC, CAM, TS, or LD releases, is prohibited.
        prohib_markers = ["MIC", "CAM", "TS", "TELESYNC", "LD", "LINE"]
        basename = self.get_basename(meta)
        # Split on delimiters (dot, hyphen, underscore) or whitespace so tags like "LD" only match as separate tokens
        basename_up = [tok for tok in re.split(r"[\.\s_-]+", str(basename).upper()) if tok]
        if any(x in basename_up for x in prohib_markers):
            logger.info(f"{self.tracker}: [bold red]Uploading MIC, CAM, TS or LD releases, is prohibited[/bold red]")
            if meta.unattended or not await prompt_in_thread(cli_ui.ask_yes_no, "Do you want to upload anyway?", default=False):
                return False

        # Uploading upscaled releases is prohibited. Exception: The release is from a group on the upscale whitelist
        if "UPSCALE" in basename_up:
            logger.info(f"{self.tracker}: [bold red]Uploading upscaled releases is prohibited, unless the group is is whitelisted {self.base_url}/wikis/17[/bold red]")
            if meta.unattended or not await prompt_in_thread(cli_ui.ask_yes_no, "Do you want to upload anyway?", default=False):
                return False

        # Uploading SD content is not allowed. Exception: No HD version exists. Check release databases beforehand to ensure an HD version doesn't exist
        if meta.resolution in ["384p", "480p", "480i", "540p", "576p", "576i"]:
            logger.info(f"{self.tracker}: [bold red]Uploading SD releases is not allowed on {self.tracker}, unless no HD version exists.[/bold red]")
            logger.info(f"{self.tracker}: [bold red]Please check release databases beforehand to be sure.[/bold red]")
            if meta.unattended or not await prompt_in_thread(cli_ui.ask_yes_no, "Do you want to upload anyway?", default=False):
                return False

        # Uploads must contain a German audio track. Exception: The release was requested in its original language.
        if not self._has_german_audio(meta):
            logger.info(f"{self.tracker}: [bold red]Uploads must contain a German audio track, unless the release was requested in its original language.[/bold red]")
            if meta.unattended or not await prompt_in_thread(cli_ui.ask_yes_no, "Do you want to upload anyway?", default=False):
                return False

        # check for samples, proofs, and images in the upload directory
        filelist = meta.filelist
        if any(
            str(file).lower().endswith((".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tiff", ".pdf")) or "sample" in str(file).lower() or "proof" in str(file).lower()
            for file in filelist
        ):
            logger.info(f"{self.tracker}: [bold red]Uploads containing samples, proofs, and images are prohibited.[/bold red]")
            if meta.unattended or not await prompt_in_thread(cli_ui.ask_yes_no, "Do you want to upload anyway?", default=False):
                return False
        return True
