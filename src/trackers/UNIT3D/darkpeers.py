# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import re
from contextlib import suppress
from pathlib import Path
from typing import Any, ClassVar, cast

import httpx

from src.console import logger
from src.get_desc import DescriptionBuilder
from src.languages import languages_manager
from src.meta import Meta
from src.music.models import MusicRelease
from src.music.validation import MusicValidator, ValidationLevel
from src.tmdb import TmdbManager
from src.trackers.UNIT3D import UNIT3D


class DarkPeers(UNIT3D):
    """
    Darkpeers is a Private Torrent Tracker for MOVIES / TV / GENERAL
    """

    tracker = "DARKPEERS"
    display_name = "DarkPeers"
    allows_bloated_audio = True
    reject_episode_if_season_pack_exists = True
    base_url = "https://darkpeers.org"
    banned_groups = (
        "ARCADE",
        "aXXo",
        "BANDOLEROS",
        "BONE",
        "BRrip",
        "CM8",
        "CrEwSaDe",
        "CTFOH",
        "dAV1nci",
        "DNL",
        "eranger2",
        "FaNGDiNG0",
        "FGT",
        "FiSTER",
        "flower",
        "GalaxyTV",
        "Goki",
        "H4XO",
        "HD2DVD",
        "HDTime",
        "HorribleSubs",
        "iHYTECH",
        "ION10",
        "iPlanet",
        "KiNGDOM",
        "LAMA",
        "MeGusta",
        "mHD",
        "mSD",
        "NaNi",
        "NhaNc3",
        "nHD",
        "nikt0",
        "nSD",
        "OFT",
        "PiTBULL",
        "PRODJi",
        "PSA",
        "RARBG",
        "Rifftrax",
        "ROCKETRACCOON",
        "SANTi",
        "SARTRE",
        "SasukeducK",
        "SEEDSTER",
        "ShAaNiG",
        "Sicario",
        "STUTTERSHIT",
        "Subsplease",
        "SyncUp",
        "TAoE",
        "TGALAXY",
        "TGx",
        "TORRENTGALAXY",
        "ToVaR",
        "Trix",
        "TSP",
        "TSPxL",
        "ViSION",
        "VXT",
        "WAF",
        "WKS",
        "X0r",
        "YIFY",
        "YTS",
    )
    id_url = f"{base_url}/api/torrents/"
    upload_url = f"{base_url}/api/torrents/upload"
    requests_url = f"{base_url}/api/requests/filter"
    search_url = f"{base_url}/api/torrents/filter"
    torrent_url = f"{base_url}/torrents/"
    supported_categories = ("TV", "MOVIE", "BOOK", "GAME", "MUSIC")
    tracker_urls = ("https://darkpeers.org",)

    def __init__(self, config: dict[str, Any]):
        super().__init__(config, tracker_name="DARKPEERS")
        self.config = config
        self.tmdb_manager = TmdbManager(config)

    async def get_description(self, meta: Meta) -> dict[str, str]:
        audio_spectrogram = str(meta.category or "").strip().upper() == "MUSIC"
        description = await DescriptionBuilder(self.tracker, self.config).unit3d_edit_desc(meta, audio_spectrogram=audio_spectrogram)
        return {"description": description}

    async def get_additional_checks(self, meta: Meta) -> bool:
        group = str(meta.tag or "").lstrip("-").strip().upper()
        release_type = str(meta.type or "").strip().upper()
        category = str(meta.category or "").strip().upper()

        if category in {"MOVIE", "TV"}:
            if not await self.validate_video_languages(meta):
                return False
            if not await self.validate_video_resolution(meta):
                return False
            if not self.validate_video_files(meta):
                return False
            if (
                meta.keep_folder
                and (category == "MOVIE" or not self._is_single_tv_season(meta))
                and not await self._confirm_or_skip("does not allow an individual video file in an unnecessary folder.", meta)
            ):
                return False

        if category == "TV" and not self.validate_tv_scope(meta):
            return False

        if category == "BOOK" and not await self.validate_book(meta):
            return False

        if category == "MUSIC" and not self.validate_music(meta):
            return False

        if category == "GAME" and not await self.validate_game(meta):
            return False

        if group == "EVO" and release_type != "WEBDL":
            logger.info(f"{self.tracker}: [bold red]only allows EVO releases when they are WEB-DLs. Skipping upload.")
            return False

        if group == "HDT" and release_type != "REMUX":
            logger.info(f"{self.tracker}: [bold red]only allows HDT releases when they are Remuxes. Skipping upload.")
            return False

        if category in {"MOVIE", "TV"} and meta.hardcoded_subs:
            logger.info(f"{self.tracker}: [bold red]does not allow Movies or TV releases with hardcoded subtitles. Skipping upload.")
            return False

        return True

    _NORDIC_LANGUAGES: ClassVar[set[str]] = {
        "danish",
        "finnish",
        "icelandic",
        "norwegian bokmal",
        "norwegian nynorsk",
        "norwegian",
        "swedish",
    }
    _LANGUAGE_ALIASES: ClassVar[dict[str, str]] = {
        "da": "danish",
        "dan": "danish",
        "de": "german",
        "deu": "german",
        "en": "english",
        "eng": "english",
        "es": "spanish",
        "fi": "finnish",
        "fin": "finnish",
        "fr": "french",
        "fra": "french",
        "fre": "french",
        "ger": "german",
        "ice": "icelandic",
        "is": "icelandic",
        "isl": "icelandic",
        "ja": "japanese",
        "jpn": "japanese",
        "no": "norwegian",
        "nor": "norwegian",
        "por": "portuguese",
        "pt": "portuguese",
        "spa": "spanish",
        "sv": "swedish",
        "swe": "swedish",
    }
    _BOOK_FORMATS: ClassVar[set[str]] = {
        "AZW",
        "AZW3",
        "CBR",
        "CBZ",
        "CHM",
        "DJVU",
        "DOC",
        "DOCX",
        "EPUB",
        "FB2",
        "HTM",
        "HTML",
        "KFX",
        "LIT",
        "MOBI",
        "PDB",
        "PDF",
        "RTF",
        "TXT",
    }
    _AUDIOBOOK_FORMATS: ClassVar[set[str]] = {
        "AAC",
        "ALAC",
        "FLAC",
        "M4B",
        "MP3",
        "OPUS",
        "PCM",
        "VORBIS",
    }

    @classmethod
    def _normalise_language(cls, value: Any) -> str:
        language = re.sub(r"\s+", " ", str(value or "").strip().casefold())
        language = re.sub(r"\s*\([^)]*\)", "", language).strip()
        return cls._LANGUAGE_ALIASES.get(language, language)

    @classmethod
    def _languages(cls, value: list[str] | str | None) -> set[str]:
        values = [value] if isinstance(value, str) else (value or [])
        return {norm for item in values if (norm := cls._normalise_language(item))}

    @classmethod
    def _accepted_languages(cls) -> set[str]:
        return {"english", *cls._NORDIC_LANGUAGES}

    async def validate_video_languages(self, meta: Meta) -> bool:
        """Apply DP's audio/original-audio-and-subtitles rule, not the generic OR helper."""
        if not meta.language_checked:
            await languages_manager.process_desc_language(meta, tracker=self.tracker)
        audio = self._languages(meta.audio_languages)
        subtitles = self._languages(meta.subtitle_languages)
        original = self._normalise_language(meta.original_language)
        accepted = self._accepted_languages()
        valid = bool(audio & accepted) or (bool(original) and original in audio and bool(subtitles & accepted))
        if not valid:
            logger.info(f"{self.tracker}: [bold red]requires English/Nordic audio, or original audio with English/Nordic subtitles. Skipping upload.")
        return valid

    async def validate_video_resolution(self, meta: Meta) -> bool:
        resolution = str(meta.resolution or "")
        allowed = {"480i", "480p", "576i", "576p", "720p", "1080i", "1080p", "2160p", "4320p"}
        if resolution in allowed:
            return True
        if resolution == "360p":
            return await self._confirm_or_skip("only permits 360p when no official higher-resolution release exists.", meta)
        logger.info(f"{self.tracker}: [bold red]does not support {resolution or 'an unknown'} video resolution. Skipping upload.")
        return False

    def validate_video_files(self, meta: Meta) -> bool:
        archive = next((Path(str(item)).name for item in meta.filelist or [] if Path(str(item)).suffix.lower() in {".rar", ".zip", ".7z"}), "")
        if archive:
            logger.info(f"{self.tracker}: [bold red]does not permit archives in Movie/TV uploads: {archive}. Skipping upload.")
            return False
        return True

    def validate_tv_scope(self, meta: Meta) -> bool:
        name = " ".join((str(meta.name or ""), Path(str(meta.path or "")).name)).casefold()
        if re.search(r"\b(?:complete[ ._-]*series|all[ ._-]*seasons?|seasons?[ ._-]*\d+[ ._-]*(?:-|to)[ ._-]*\d+|s\d{1,2}[ ._-]*-[ ._-]*s?\d{1,2})\b", name):
            logger.info(f"{self.tracker}: [bold red]only individual seasons or episodes are allowed. Skipping multi-season/complete-series upload.")
            return False
        seasons = {match.casefold() for item in meta.filelist or [] for match in re.findall(r"\bS(\d{1,2})(?:E\d{1,3})?\b", Path(str(item)).name, re.IGNORECASE)}
        if len(seasons) > 1:
            logger.info(f"{self.tracker}: [bold red]torrent contains files from multiple seasons. Skipping upload.")
            return False
        return True

    def _is_single_tv_season(self, meta: Meta) -> bool:
        if meta.episode:
            return False
        seasons = {match for item in meta.filelist or [] for match in re.findall(r"\bS(\d{1,2})(?:E\d{1,3})?\b", Path(str(item)).name, re.IGNORECASE)}
        return len(seasons) == 1 or bool(meta.season)

    async def validate_book(self, meta: Meta) -> bool:
        author = str(meta.author or meta.book_author or "").strip()
        if not author:
            return await self._missing_required("author", meta)
        format_name = self._book_format(meta)
        allowed = self._AUDIOBOOK_FORMATS if meta.audiobook else self._BOOK_FORMATS
        if format_name not in allowed:
            logger.info(f"{self.tracker}: [bold red]does not support {format_name or 'an unspecified'} book format. Skipping upload.")
            return False
        identifier = self._book_identifier(meta)
        is_collection = len(meta.filelist or []) > 1 or "collection" in str(meta.name or "").casefold()
        if not identifier and not is_collection:
            return await self._missing_required("a valid ISBN/ASIN", meta)
        publisher = str(meta.publisher or meta.book_publisher or "").strip()
        if not publisher:
            return await self._missing_required("publisher", meta)
        if meta.audiobook and not str(meta.narrator or "").strip():
            return await self._missing_required("audiobook narrator", meta)
        if not meta.audiobook and format_name == "PDF" and not bool(meta.get("page_count", None) or meta.get("book_page_count", None)):
            return await self._missing_required("PDF page count", meta)
        return True

    @staticmethod
    def _book_format(meta: Meta) -> str:
        """Resolve container aliases from MediaInfo when the codec is available."""
        format_name = str(meta.type or meta.format or "").upper().strip()
        if not meta.audiobook or format_name not in {"M4A", "OGG", "WAV"}:
            return format_name
        media = (meta.mediainfo if isinstance(meta.mediainfo, dict) else {}).get("media")
        raw_tracks = (media if isinstance(media, dict) else {}).get("track")
        tracks = raw_tracks if isinstance(raw_tracks, list) else []
        audio_text = " ".join(
            str(track.get("Format") or track.get("format") or track.get("CodecID") or track.get("codec") or "")
            for track_value in tracks
            if (track := track_value if isinstance(track_value, dict) else {}) and str(track.get("@type") or track.get("type") or "").casefold() == "audio"
        ).casefold()
        if format_name == "M4A":
            return "ALAC" if "alac" in audio_text else "AAC" if "aac" in audio_text else format_name
        if format_name == "OGG":
            return "OPUS" if "opus" in audio_text else "VORBIS" if "vorbis" in audio_text else format_name
        return "PCM" if "pcm" in audio_text else format_name

    @staticmethod
    def _book_identifier(meta: Meta) -> str:
        isbn = str(meta.isbn or meta.book_isbn or "").strip()
        if isbn:
            cleaned = re.sub(r"[^0-9Xx]", "", isbn)
            return cleaned[:-1] + cleaned[-1:].upper() if cleaned else ""
        asin = str(meta.asin or meta.book_asin or "").strip()
        return re.sub(r"[^0-9A-Za-z]", "", asin).upper()

    def validate_music(self, meta: Meta) -> bool:
        release_data = meta.music_release if isinstance(meta.music_release, dict) else {}
        release = MusicRelease.from_dict(release_data) if release_data else MusicRelease(root=str(meta.path or ""))
        errors = [issue.message for issue in MusicValidator().validate(release) if issue.level == ValidationLevel.ERROR]
        if errors:
            logger.info(f"{self.tracker}: [bold red]{' '.join(errors)} Skipping upload.")
            return False
        audio_suffixes = {".flac", ".mp3", ".m4a", ".aac", ".ogg", ".opus", ".wav", ".alac"}
        paths = [track.relative_path for track in release.tracks] or [str(item) for item in meta.filelist or [] if Path(str(item)).suffix.lower() in audio_suffixes]
        for path in paths:
            relative = str(path).replace("\\", "/")
            filename = Path(relative).name
            if len(relative) > 180 or filename.startswith(" ") or any(part.startswith(" ") for part in relative.split("/")):
                logger.info(f"{self.tracker}: [bold red]invalid music path: {relative}. Skipping upload.")
                return False
            if re.search(r"\b\w+\.\w+\.\d{1,2}\.\w+", filename) or not re.match(r"(?:\d{1,2}|\d{1,2}-\d{1,2})\s+-\s+.+", filename):
                logger.info(f"{self.tracker}: [bold red]music filename must include a track number and title: {filename}. Skipping upload.")
                return False
        return True

    async def validate_game(self, meta: Meta) -> bool:
        files = [Path(str(item)) for item in meta.filelist or []]
        rar_files = [item for item in files if item.suffix.lower() == ".rar" or re.search(r"\.r\d{2}$", item.name, re.IGNORECASE)]
        prohibited = next((item.name for item in files if item.suffix.lower() in {".iso", ".zip", ".7z"}), "")
        if prohibited or not rar_files or not meta.scene or not str(meta.scene_nfo_file or "").strip() or str(meta.repack or "").strip():
            logger.info(f"{self.tracker}: [bold red]Games/Apps must be an original RAR'd scene release with its NFO, not a repack or ISO. Skipping upload.")
            return False
        instructions = " ".join(str(value or "") for value in (meta.description, meta.description_file_content, meta.description_link_content, meta.description_nfo_content))
        if not re.search(r"\b(?:install(?:ation)?|setup|usage|instructions?)\b", instructions, re.IGNORECASE):
            return await self._missing_required("installation and usage instructions", meta)
        return True

    async def _missing_required(self, field: str, meta: Meta) -> bool:
        if meta.unattended and not meta.unattended_confirm:
            logger.info(f"{self.tracker}: [bold red]missing required {field}. Skipping unattended upload.")
            return False
        return await self._confirm_or_skip(f"is missing required {field}; confirm it is present in the final description.", meta)

    async def _confirm_or_skip(self, message: str, meta: Meta) -> bool:
        logger.info(f"{self.tracker}: [bold red]{message}[/bold red]")
        if meta.unattended:
            return bool(meta.unattended_confirm)
        return await self.common.prompt_user_for_confirmation("Do you want to upload anyway?", meta)

    async def get_additional_data(self, meta: Meta) -> dict[str, Any]:
        return {
            "mod_queue_opt_in": await self.get_flag(meta, "modq"),
        }

    async def get_audio(self, meta: Meta) -> str:
        if not meta.language_checked:
            await languages_manager.process_desc_language(meta, tracker=self.tracker)
        if meta.is_disc:
            return "SKIPPED"

        audio = self._languages(meta.audio_languages)
        original = self._normalise_language(meta.original_language)
        accepted = self._accepted_languages()
        if not audio or (len(audio) == 1 and original in audio):
            return "SKIPPED"
        if audio == {"english"} and original and original != "english":
            return "Dubbed"
        if len(audio) == 1:
            only = next(iter(audio))
            if original and only != original and only in self._NORDIC_LANGUAGES:
                return f"{only.title()} Dubbed"
            return "SKIPPED"
        if original and original in audio:
            if "english" in audio and len(audio) == 2:
                return "Dual-Audio"
            if len(audio) >= 3:
                return "MULTi"
            other = next(iter(audio - {original}), "")
            return f"{other.title()} MULTi" if other else "SKIPPED"
        if "english" in audio:
            other = audio - {"english"}
            if len(other) == 1:
                return f"{next(iter(other)).title()} MULTi"
            return "MULTi"
        # A Nordic original plus one non-original track follows the same
        # Language MULTi convention; other ambiguous combinations retain the
        # original release name instead of inventing a label.
        other = audio - accepted
        return f"{next(iter(other)).title()} MULTi" if len(other) == 1 and len(audio) == 2 else "SKIPPED"

    async def get_name(self, meta: Meta) -> dict[str, str]:
        if meta.category == "MUSIC":
            return {"name": self._music_name(meta)}

        if meta.category == "BOOK":
            return {"name": self._book_name(meta)}

        # DP prohibits retags.  When the preparation stage identified a scene
        # release, submit its recorded release name rather than rebuilding it.
        dp_name = str(meta.scene_name or meta.name or "")

        if meta.category == "TV":
            dp_name = await self._tv_name(meta, dp_name)

        audio = await self.get_audio(meta)
        if audio and audio != "SKIPPED" and "Dual-Audio" in dp_name:
            dp_name = dp_name.replace("Dual-Audio", audio)

        return {"name": dp_name}

    async def _tv_name(self, meta: Meta, name: str) -> str:
        title = str(meta.title or "").strip()
        year = str(meta.year or "").strip()
        if year and not await self._tv_title_needs_year(meta):
            name = re.sub(rf"^({re.escape(title)})\s+{re.escape(year)}(?=\s|$)", r"\1", name, count=1, flags=re.IGNORECASE)
        return " ".join(name.split())

    async def _tv_title_needs_year(self, meta: Meta) -> bool:
        title = str(meta.title or "").strip()
        api_key = str(self.config.get("DEFAULT", {}).get("tmdb_api", "")).strip()
        if not title or not api_key:
            return False
        try:
            logger.info(f"{self.tracker}: Checking if TMDb has multiple shows with the title '{title}'...")
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://api.themoviedb.org/3/search/tv",
                    params={"api_key": api_key, "query": title, "language": "en-US", "include_adult": "true"},
                )
                response.raise_for_status()
                payload_raw: Any = response.json()
        except httpx.HTTPError, ValueError, TypeError:
            return False

        title_key = " ".join(title.casefold().split())
        current_id = str(meta.tmdb_id or "")
        payload = cast(dict[str, Any], payload_raw) if isinstance(payload_raw, dict) else {}
        results_raw: Any = payload.get("results", [])
        results = cast(list[Any], results_raw) if isinstance(results_raw, list) else []
        matching_ids: set[str] = set()
        for result_raw in results:
            if not isinstance(result_raw, dict):
                continue
            result = cast(dict[str, Any], result_raw)
            result_id = str(result.get("id", ""))
            names = (result.get("name"), result.get("original_name"))
            if any(" ".join(str(candidate or "").casefold().split()) == title_key for candidate in names):
                matching_ids.add(result_id)
        matching_ids.discard("")
        return bool(matching_ids - {current_id}) if current_id else len(matching_ids) > 1

    @classmethod
    def _release_field(cls, release: dict[str, Any], name: str, default: Any = "") -> Any:
        """Read a value from the serialized music release model."""
        fields = release.get("fields") if isinstance(release, dict) else {}
        value = fields.get(name) if isinstance(fields, dict) else {}
        return value.get("value", default) if isinstance(value, dict) else default

    @classmethod
    def _music_name(cls, meta: Meta) -> str:
        """Format music as ``Artist - Album (Year) - Format`` for DarkPeers."""
        release = meta.music_release if isinstance(meta.music_release, dict) else {}
        artist = str(cls._release_field(release, "artist", meta.artist)).strip()
        album = str(cls._release_field(release, "album", meta.title)).strip()
        year = str(cls._release_field(release, "release_year", cls._release_field(release, "year", meta.year or ""))).strip()
        media = str(cls._release_field(release, "media", meta.source)).strip()
        raw_tracks = release.get("tracks")
        tracks = raw_tracks if isinstance(raw_tracks, list) else []
        first_track = tracks[0] if tracks and isinstance(tracks[0], dict) else {}
        codec = str(first_track.get("codec") or first_track.get("format") or meta.format or meta.type).upper().strip()

        format_parts = [media, codec]
        if codec in {"FLAC", "ALAC", "PCM"}:
            depth = first_track.get("bit_depth") or cls._release_field(release, "nfo_bit_depth")
            rate = first_track.get("sample_rate") or cls._release_field(release, "nfo_sample_rate")
            if depth is not None and rate is not None:
                with suppress(TypeError, ValueError):
                    format_parts.append(f"{int(depth)}-{int(rate) / 1000:g}")
        elif codec in {"MP3", "AAC", "OPUS", "VORBIS"}:
            bitrate = first_track.get("bitrate") or meta.audio_bitrate
            if bitrate is not None:
                with suppress(TypeError, ValueError):
                    b = int(bitrate)
                    bitrate_kbps = b // 1000 if b >= 1000 else b
                    format_parts.append(str(bitrate_kbps))
            bitrate_mode = str(first_track.get("bitrate_mode") or "").upper().strip()
            if bitrate_mode:
                format_parts.append(bitrate_mode)

        format_name = " ".join(part for part in format_parts if part)
        title = " - ".join(part for part in (artist, album) if part)
        if year:
            title = f"{title} ({year})" if title else f"({year})"
        return f"{title} - {format_name}" if format_name else title

    @staticmethod
    def _book_name(meta: Meta) -> str:
        """Format eBooks and audiobooks according to DarkPeers' book rules."""
        # Publisher is a description field, never a substitute for the author.
        author = str(meta.author or meta.book_author or "").strip()
        title = str(meta.title or "").strip()
        year = str(meta.year or "").strip()
        edition = str(meta.manual_edition or meta.edition or "").strip()
        format_name = DarkPeers._book_format(meta)
        identifier = DarkPeers._book_identifier(meta)

        parts = [part for part in (author, "-" if author and title else "", title, year) if part]
        if not meta.audiobook and edition and not re.search(r"\b(?:1st|first)\b", edition, re.IGNORECASE):
            parts.append(edition)
        if format_name:
            parts.append(format_name)

        if meta.audiobook:
            if format_name in {"MP3", "AAC", "OPUS", "VORBIS"} and meta.audiobook_bitrate:
                parts.append(str(meta.audiobook_bitrate))
            if identifier:
                parts.append(identifier)
            base_name = " ".join(parts)
            tag = str(meta.tag or "").strip()
            if tag:
                return f"{base_name}{tag if tag.startswith('-') else f'-{tag}'}"
            return base_name

        if identifier:
            parts.append(identifier)
        source = str(meta.manual_source or meta.source or "").upper().strip()
        if source == "RETAIL":
            parts.append("Retail")
        if source == "SCAN":
            parts.append("Scan")
        if meta.ocr:
            parts.append("OCR")
        return " ".join(parts)

    async def get_category_id(self, meta: Meta, category: str = "", reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        category_id = {
            "MOVIE": "1",
            "TV": "2",
            "BOOK": "8",
            "GAME": "4",
            "MUSIC": "3",
        }
        if mapping_only:
            return category_id
        if reverse:
            return {v: k for k, v in category_id.items()}
        return {"category_id": category_id.get(category or meta.category, "0")}

    async def get_type_id(self, meta: Meta, type: str = "", reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        type_id = {
            "DISC": "1",
            "REMUX": "2",
            "WEBDL": "4",
            "WEBRIP": "5",
            "HDTV": "6",
            "ENCODE": "3",
            "DVDRIP": "3",
            "AUDIOBOOK": "15",
            "COMIC": "17",
            "EBOOK": "18",
            "PC": "9",
            "LINUX": "14",
            "MAC": "11",
            "CONSOLE": "10",
            "FLAC": "8",
            "MP3": "7",
        }
        if mapping_only:
            return type_id
        if reverse:
            return {v: k for k, v in type_id.items()}

        meta_type = "" if not meta.type else meta.type.upper()

        # Book
        if meta.category == "BOOK":
            if type:
                t_upper = type.upper()
                if t_upper in ("CBR", "CBZ"):
                    t_upper = "COMIC"
                elif t_upper in (
                    "EPUB",
                    "PDF",
                    "MOBI",
                    "AZW",
                    "AZW3",
                    "KFX",
                    "FB2",
                    "HTML",
                    "HTM",
                    "CHM",
                    "DJVU",
                    "DOC",
                    "DOCX",
                    "LIT",
                    "PDB",
                    "TXT",
                    "RTF",
                ):
                    t_upper = "EBOOK"
                elif t_upper in ("MP3", "M4B", "FLAC", "AAC", "M4A", "OGG", "WAV", "OPUS", "ALAC", "VORBIS", "PCM"):
                    t_upper = "AUDIOBOOK"
                return {"type_id": type_id.get(t_upper, type_id.get(type, "0"))}
            if meta.audiobook:
                meta_type = "AUDIOBOOK"
            elif meta.comic or meta_type in ("CBR", "CBZ"):
                meta_type = "COMIC"
            else:
                meta_type = "EBOOK"

        if meta.category == "GAME":
            meta_type = "CONSOLE" if meta.console_game else meta.platform.upper()

        if meta.category == "MUSIC":
            meta_type = meta.format.upper()

        resolved_id = type_id.get(meta_type, "0")
        return {"type_id": resolved_id}
