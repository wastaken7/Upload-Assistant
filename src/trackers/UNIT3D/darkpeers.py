# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import re
from contextlib import suppress
from typing import Any

import cli_ui

from src.console import logger
from src.languages import languages_manager
from src.meta import Meta
from src.tmdb import TmdbManager
from src.trackers.UNIT3D import UNIT3D


class DarkPeers(UNIT3D):
    """
    Darkpeers is a Private Torrent Tracker for MOVIES / TV / GENERAL
    """

    tracker = "DARKPEERS"
    display_name = "DarkPeers"
    allows_bloated_audio = True
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

    async def get_additional_checks(self, meta: Meta) -> bool:
        should_continue = True
        if meta.keep_folder:
            if not meta.unattended or (meta.unattended and meta.unattended_confirm):
                logger.info(f"{self.tracker}: [bold red]does not allow single files in a folder.")
                if cli_ui.ask_yes_no("Do you want to upload anyway?", default=False):
                    pass
                else:
                    return False
            else:
                return False

        nordic_languages = ["danish", "swedish", "norwegian", "icelandic", "finnish", "english"]
        if not await self.common.check_language_requirements(meta, self.tracker, languages_to_check=nordic_languages, check_audio=True, check_subtitle=True):
            return False

        if meta.type not in ["WEBDL"] and meta.tag in ["EVO"]:
            if not meta.unattended:
                logger.info(f"{self.tracker}: [bold red]does not allow EVO for non-WEBDL types, skipping upload.")
            return False

        if meta.hardcoded_subs and not meta.unattended:
            logger.info(f"{self.tracker}: [bold red]does not allow hardcoded subtitles.")
            return False

        return should_continue

    async def get_additional_data(self, meta: Meta) -> dict[str, Any]:
        return {
            "mod_queue_opt_in": await self.get_flag(meta, "modq"),
        }

    async def get_audio(self, meta: Meta) -> str:
        languages_result = "SKIPPED"

        if not meta.language_checked:
            await languages_manager.process_desc_language(meta, tracker=self.tracker)

        audio_languages = meta.audio_languages
        if isinstance(audio_languages, list):
            audio_languages_list = audio_languages
            normalized_languages = {str(lang).strip() for lang in audio_languages_list if str(lang).strip()}

            if len(normalized_languages) > 2:
                languages_result = "MULTi"
            elif len(normalized_languages) > 1:
                languages_result = "Dual-Audio"
            else:
                languages_result = next(iter(normalized_languages), "SKIPPED")

        return f"{languages_result}"

    async def get_name(self, meta: Meta) -> dict[str, str]:
        if meta.category == "MUSIC":
            return {"name": self._music_name(meta)}

        if meta.category == "BOOK":
            return {"name": self._book_name(meta)}

        dp_name = meta.name

        audio = await self.get_audio(meta)
        if audio and audio != "SKIPPED" and "Dual-Audio" in dp_name:
            dp_name = dp_name.replace("Dual-Audio", audio)

        return {"name": dp_name}

    @staticmethod
    def _release_field(release: dict[str, Any], name: str, default: Any = "") -> Any:
        """Read a value from the serialized music release model."""
        fields = release.get("fields", {})
        value = fields.get(name, {}) if isinstance(fields, dict) else {}
        return value.get("value", default) if isinstance(value, dict) else default

    @classmethod
    def _music_name(cls, meta: Meta) -> str:
        """Format music as ``Artist - Album (Year) - Format`` for DarkPeers."""
        release = meta.music_release if isinstance(meta.music_release, dict) else {}
        artist = str(cls._release_field(release, "artist", meta.artist)).strip()
        album = str(cls._release_field(release, "album", meta.title)).strip()
        year = str(cls._release_field(release, "release_year", cls._release_field(release, "year", meta.year or ""))).strip()
        media = str(cls._release_field(release, "media", meta.source)).strip()
        tracks = release.get("tracks", []) if isinstance(release.get("tracks"), list) else []
        first_track = tracks[0] if tracks and isinstance(tracks[0], dict) else {}
        codec = str(first_track.get("codec") or first_track.get("format") or meta.format or meta.type).upper().strip()

        format_parts = [media, codec]
        if codec in {"FLAC", "ALAC", "PCM"}:
            depth = first_track.get("bit_depth") or cls._release_field(release, "nfo_bit_depth")
            rate = first_track.get("sample_rate") or cls._release_field(release, "nfo_sample_rate")
            if depth and rate:
                with suppress(TypeError, ValueError):
                    format_parts.append(f"{int(depth)}-{int(rate) / 1000:g}")
        elif codec in {"MP3", "AAC", "OPUS", "VORBIS"}:
            bitrate = first_track.get("bitrate") or meta.audio_bitrate
            if bitrate:
                with suppress(TypeError, ValueError):
                    bitrate_kbps = int(bitrate) // 1000 if int(bitrate) >= 1000 else int(bitrate)
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
        author = str(meta.author or meta.publisher or "").strip()
        title = str(meta.title or "").strip()
        year = str(meta.year or "").strip()
        edition = str(meta.manual_edition or meta.edition or "").strip()
        format_name = str(meta.type or meta.format or "").upper().strip()
        identifier = re.sub(r"[^0-9Xx]", "", str(meta.isbn or meta.asin or ""))

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
        if category:
            return {"category_id": category_id.get(category, "0")}
        meta_category = meta.category
        resolved_id = category_id.get(meta_category, "0")
        return {"category_id": resolved_id}

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
                elif t_upper in ("EPUB", "PDF", "MOBI", "AZW3", "KFX"):
                    t_upper = "EBOOK"
                elif t_upper in ("MP3", "M4B", "FLAC", "AAC", "M4A", "OGG", "WAV"):
                    t_upper = "AUDIOBOOK"
                return {"type_id": type_id.get(t_upper, type_id.get(type, "0"))}
            if meta.category == "BOOK":
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
