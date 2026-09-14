# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import re
from typing import Any, ClassVar

from src.console import logger
from src.meta import Meta
from src.release_name import NameContext, NameRule, NameSelector, TrackerNameProfile, collapse_whitespace, template
from src.music.sources import DiscogsEnricher
from src.trackers.common import Common
from src.trackers.naming import lst_name
from src.trackers.UNIT3D import UNIT3D

Config = dict[str, Any]


class LST(UNIT3D):
    """
    LST is an ENGLISH Private Torrent Tracker for MOVIES / TV / GENERAL
    """

    tracker = "LST"
    name_profile = TrackerNameProfile(
        rules=(
            NameRule(NameSelector(category="MUSIC"), template("author", "dash", "title", "year", "effective_source", "effective_codec", "bit_depth", "sample_rate")),
            NameRule(NameSelector(category="BOOK"), template("author", "dash", "title", "book_edition", "year", "effective_source", "effective_codec", "bit_depth", "sample_rate", "scan_type", "isbn")),
            NameRule(NameSelector(), template("base_name")),
        ),
        transforms=(collapse_whitespace, lst_name),
    )

    async def get_name_overrides(self, context: NameContext) -> dict[str, str]:
        meta = context.meta
        if meta.category == "MUSIC":
            release = meta.music_release if isinstance(meta.music_release, dict) else {}
            tracks = release.get("tracks", []) if isinstance(release.get("tracks"), list) else []
            first = tracks[0] if tracks and isinstance(tracks[0], dict) else {}
            codec = self._codec(first.get("codec") or first.get("format") or meta.format or meta.type)
            depth = first.get("bit_depth") or self._release_field(release, "nfo_bit_depth")
            rate = first.get("sample_rate") or self._release_field(release, "nfo_sample_rate")
            rate_label = ""
            if rate:
                match = re.search(r"\d+(?:[.,]\d+)?", str(rate))
                if match:
                    value = float(match.group().replace(",", "."))
                    rate_label = f"{value / 1000:g} kHz" if value >= 1000 else f"{value:g} kHz"
            tag = str(meta.tag or "").strip().lstrip("-").strip()
            return {"author": str(self._release_field(release, "artist", meta.artist)), "dash": "-", "title": str(self._release_field(release, "album", meta.title)), "year": str(self._release_field(release, "release_year", self._release_field(release, "year", meta.year))), "effective_source": self._source(self._release_field(release, "media", meta.source)), "effective_codec": codec, "bit_depth": f"{depth}-bit" if depth and codec in {"FLAC", "ALAC"} else "", "sample_rate": rate_label if codec in {"FLAC", "ALAC"} else "", "group_suffix": f"-{tag}" if tag else ""}
        if meta.category == "BOOK":
            author = str(meta.author or meta.publisher or "")
            codec = self._codec(meta.type)
            source = self._source(meta.source)
            depth_label = rate_label = ""
            if meta.audiobook and codec in {"FLAC", "ALAC"}:
                audio = next((track for track in meta.mediainfo.get("media", {}).get("track", []) if track.get("@type") == "Audio"), {})
                depth = re.search(r"\d+", str(audio.get("BitDepth") or audio.get("BitDepth_String") or ""))
                rate = re.search(r"\d+(?:[.,]\d+)?", str(audio.get("SamplingRate") or audio.get("SamplingRate_String") or ""))
                depth_label = f"{depth.group()}-bit" if depth else ""
                if rate:
                    value = float(rate.group().replace(",", "."))
                    rate_label = f"{value / 1000:g} kHz" if value >= 1000 else f"{value:g} kHz"
            tag = str(meta.tag or "").strip().lstrip("-").strip()
            return {"author": author, "dash": "-", "title": str(meta.title or ""), "book_edition": "" if meta.audiobook else str(meta.manual_edition or meta.edition or ""), "year": str(meta.year or ""), "effective_source": source if meta.audiobook else "", "effective_codec": codec, "bit_depth": depth_label, "sample_rate": rate_label, "scan_type": "" if meta.audiobook else "OCR" if meta.ocr else "SCAN" if source.upper() == "SCAN" else "", "isbn": "" if meta.audiobook else re.sub(r"[^0-9Xx]", "", str(meta.isbn or "")), "group_suffix": f"-{tag}" if tag else ""}
        return {}
    display_name = "LST"
    allows_bloated_audio = True
    base_url = "https://lst.gg"
    banned_groups = ()
    banned_url = f"{base_url}/api/bannedReleaseGroups"
    id_url = f"{base_url}/api/torrents/"
    upload_url = f"{base_url}/api/torrents/upload"
    search_url = f"{base_url}/api/torrents/filter"
    torrent_url = f"{base_url}/torrents/"
    trumping_url = f"{base_url}/api/reports/torrents/"
    supported_categories = ("TV", "MOVIE", "BOOK", "MUSIC", "XXX")
    tracker_urls = ("https://lst.gg",)
    REGION_IDS: ClassVar[dict[str, str]] = {
        "CZE": "244",
        "FIN": "245",
        "SWE": "246",
    }

    def __init__(self, config: Config) -> None:
        super().__init__(config, tracker_name="LST")
        self.config: Config = config
        self.common = Common(config)

    async def get_additional_checks(self, meta: Meta) -> bool:
        if meta.category not in ("MOVIE", "TV"):
            return True

        should_continue = True
        if not meta.valid_mi_settings:
            logger.info(f"{self.tracker}: [bold red]No encoding settings in mediainfo, skipping {self.tracker} upload.[/bold red]")
            return False

        if meta.is_disc not in ["BDMV", "DVD"] and not await self.common.check_language_requirements(
            meta, self.tracker, languages_to_check=["english"], check_audio=True, check_subtitle=True, original_language=True
        ):
            return False

        return should_continue

    async def get_category_id(self, meta: Meta, category: str | None = None, reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        category_id = {
            "MOVIE": "1",
            "TV": "2",
            "MUSIC": "3",
            "BOOK": "9",
            "XXX": "8",
        }
        if mapping_only:
            return category_id
        if reverse:
            return {v: k for k, v in category_id.items()}

        resolved_category = category if category is not None and category != "" else meta.category
        return {"category_id": category_id.get(resolved_category, "0")}

    async def get_type_id(self, meta: Meta, media_type: str | None = None, reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        type_id = {
            "DISC": "1",
            "REMUX": "2",
            "ENCODE": "3",
            "DVDRIP": "3",
            "WEBDL": "4",
            "WEBRIP": "5",
            "HDTV": "6",
            "SDTV": "16",
            "FLAC": "7",
            "ALAC": "8",
            "AC3": "9",
            "AAC": "10",
            "MP3": "11",
            "MAC": "12",
            "WINDOWS": "13",
            "LINUX": "14",
            "OTHER": "15",
        }
        if mapping_only:
            return type_id
        if reverse:
            return {v: k for k, v in type_id.items()}

        resolved_type = media_type if media_type is not None and media_type != "" else meta.type

        if meta.category == "MUSIC" and not resolved_type:
            resolved_type = meta.format.upper()

        if isinstance(resolved_type, str):
            resolved_type = resolved_type.upper().strip().lstrip(".")

        val = type_id.get(resolved_type or "", "0")
        if meta.category == "BOOK" and resolved_type not in type_id:
            val = "15"

        return {"type_id": val}

    async def get_additional_data(self, meta: Meta) -> dict[str, Any]:
        data: dict[str, Any] = {
            "mod_queue_opt_in": await self.get_flag(meta, "modq"),
            "draft_queue_opt_in": await self.get_flag(meta, "draft"),
        }

        # Only add edition_id if we have a valid edition
        edition_id = await self.get_edition(meta)
        if edition_id is not None:
            data["edition_id"] = edition_id

        if meta.category == "BOOK":
            openlibrary_id = meta.openlibrary or meta.openlibrary_id or meta.openlibrary_book_id or ""
            isbn = meta.isbn or ""

            data["book_exists_on_openlibrary"] = "1"
            data["openlibrary_book_id"] = openlibrary_id
            data["openlibrary_isbn"] = isbn
            data["extra_openlibrary_ids"] = meta.extra_openlibrary_ids or ""

        if meta.category == "MUSIC" and meta.music_discogs_enabled:
            release = meta.music_release if isinstance(meta.music_release, dict) else {}
            external_ids: dict[str, Any] = release.get("external_ids", {}) if isinstance(release.get("external_ids"), dict) else {}
            release_reference = external_ids.get("discogs_release") or meta.music_discogs_release_id or meta.music_discogs_id
            master_reference = external_ids.get("discogs_master") or meta.music_discogs_master_id
            release_id = DiscogsEnricher.parse_reference(str(release_reference or ""), "release")
            master_id = DiscogsEnricher.parse_reference(str(master_reference or ""), "master")

            data.update(
                {
                    "discogs": release_id[1] if release_id and release_id[0] == "release" else "",
                    "discogs_master_id": master_id[1] if master_id and master_id[0] == "master" else "",
                    "extra_discogs_master_ids": "",
                    "extra_discogs_ids": "",
                }
            )
            if release_id or master_id:
                data["release_exists_on_discogs"] = "1"

        return data

    async def get_region_id(self, meta: Meta) -> dict[str, str]:
        region_id = self.REGION_IDS.get(str(meta.region or "").upper())
        if region_id:
            return {"region_id": region_id}
        return await super().get_region_id(meta)

    async def get_region_name(self, region_id: int | str | None) -> str:
        region_name = {value: key for key, value in self.REGION_IDS.items()}.get(str(region_id), "")
        if region_name:
            return region_name
        try:
            normalized_id = int(region_id) if region_id is not None else 0
        except TypeError, ValueError:
            return ""
        return await self.common.unit3d_region_ids(reverse=True, region_id=normalized_id)

    async def get_edition(self, meta: Meta) -> int | None:
        edition_mapping = {
            "Alternative Cut": 12,
            "Collector's Edition": 1,
            "Director's Cut": 2,
            "Extended Cut": 3,
            "Extended Uncut": 4,
            "Extended Unrated": 5,
            "Limited Edition": 6,
            "Special Edition": 7,
            "Theatrical Cut": 8,
            "Uncut": 9,
            "Unrated": 10,
            "X Cut": 11,
            "Other": 0,  # Default value for "Other"
        }
        edition = meta.edition
        if edition in edition_mapping:
            return edition_mapping[edition]
        return None

    @staticmethod
    def _release_field(release: dict[str, Any], name: str, default: Any = "") -> Any:
        """Read a JSON-serialized MusicRelease field without its provenance."""
        fields = release.get("fields", {})
        value = fields.get(name, {}) if isinstance(fields, dict) else {}
        return value.get("value", default) if isinstance(value, dict) else default

    @staticmethod
    def _codec(value: Any) -> str:
        codec = str(value or "").upper().strip()
        aliases = {
            "OGG VORBIS": "VORBIS",
            "OGG": "VORBIS",
            "MPEG AUDIO": "MP3",
            "MPEG-4 AAC": "AAC",
            "M4A": "AAC",
            "M4B": "M4B",
            "MOBI": "KINDLE",
            "AZW": "KINDLE",
            "AZW3": "KINDLE",
            "CBR": "CBA",
            "CBZ": "CBA",
        }
        return aliases.get(codec, codec)

    @staticmethod
    def _source(value: Any) -> str:
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
