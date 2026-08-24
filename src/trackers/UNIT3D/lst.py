# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import re
from typing import Any, ClassVar

from src.console import logger
from src.meta import Meta
from src.music.sources import DiscogsEnricher
from src.trackers.common import Common
from src.trackers.UNIT3D import UNIT3D

Config = dict[str, Any]


class LST(UNIT3D):
    """
    LST is an ENGLISH Private Torrent Tracker for MOVIES / TV / GENERAL
    """

    tracker = "LST"
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

    async def get_name(self, meta: Meta) -> dict[str, str]:
        if meta.category == "MUSIC":
            return {"name": self._append_trump(self._music_name(meta), meta)}

        if meta.category == "BOOK":
            return {"name": self._append_trump(self._book_name(meta), meta)}

        lst_name = meta.name
        resolution = meta.resolution
        video_encode = meta.video_encode
        name_type = meta.type

        if name_type == "DVDRIP":
            if meta.category == "MOVIE":
                lst_name = lst_name.replace(f"{meta.source}{meta.video_encode}", f"{resolution}", 1)
                lst_name = lst_name.replace(meta.audio, f"{meta.audio}{video_encode}", 1)
            else:
                lst_name = lst_name.replace(str(meta.source), f"{resolution}", 1)
                lst_name = lst_name.replace(meta.video_codec, f"{meta.audio} {meta.video_codec}", 1)

        if meta.trump_reason == "exact_match":
            lst_name = lst_name + " - TRUMP"

        return {"name": lst_name}

    @staticmethod
    def _with_tag(parts: list[str], tag: str | None) -> str:
        """Join a LST title and append the release-group tag once."""
        name = " ".join(part.strip() for part in parts if str(part or "").strip())
        name = " ".join(name.split())
        normalized_tag = str(tag or "").strip().lstrip("-").strip()
        return f"{name}-{normalized_tag}" if normalized_tag else name

    @staticmethod
    def _append_trump(name: str, meta: Meta) -> str:
        return f"{name} - TRUMP" if meta.trump_reason == "exact_match" else name

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

    @classmethod
    def _music_name(cls, meta: Meta) -> str:
        """Format music using LST's Discogs-based naming convention."""
        release = meta.music_release if isinstance(meta.music_release, dict) else {}
        artist = cls._release_field(release, "artist", meta.artist)
        title = cls._release_field(release, "album", meta.title)
        year = cls._release_field(release, "release_year", cls._release_field(release, "year", meta.year))
        source = cls._source(cls._release_field(release, "media", meta.source))
        tracks = release.get("tracks", []) if isinstance(release.get("tracks"), list) else []
        first_track = tracks[0] if tracks and isinstance(tracks[0], dict) else {}
        codec = cls._codec(first_track.get("codec") or first_track.get("format") or meta.format or meta.type)
        parts = [str(artist), "-", str(title), str(year), source, codec]

        # LST omits technical PCM fields for lossy codecs.
        if codec in {"FLAC", "ALAC"}:
            depth = first_track.get("bit_depth") or cls._release_field(release, "nfo_bit_depth")
            rate = first_track.get("sample_rate") or cls._release_field(release, "nfo_sample_rate")
            if depth:
                parts.append(f"{depth}-bit")
            if rate:
                match = re.search(r"\d+(?:[.,]\d+)?", str(rate))
                if match:
                    value = float(match.group().replace(",", "."))
                    parts.append(f"{value / 1000:g} kHz" if value >= 1000 else f"{value:g} kHz")
        return cls._with_tag(parts, meta.tag)

    @classmethod
    def _book_name(cls, meta: Meta) -> str:
        """Format LST audiobooks and eBooks according to their category rules."""
        author, title, year = str(meta.author or meta.publisher or ""), str(meta.title or ""), str(meta.year or "")
        if meta.audiobook:
            codec = cls._codec(meta.type)
            source = cls._source(meta.source)
            parts = [author, "-", title, year, source, codec]
            if codec in {"FLAC", "ALAC"}:
                audio = next((track for track in meta.mediainfo.get("media", {}).get("track", []) if track.get("@type") == "Audio"), {})
                depth = audio.get("BitDepth") or audio.get("BitDepth_String")
                rate = audio.get("SamplingRate") or audio.get("SamplingRate_String")
                if depth:
                    match = re.search(r"\d+", str(depth))
                    if match:
                        parts.append(f"{match.group()}-bit")
                if rate:
                    match = re.search(r"\d+(?:[.,]\d+)?", str(rate))
                    if match:
                        value = float(match.group().replace(",", "."))
                        parts.append(f"{value / 1000:g} kHz" if value >= 1000 else f"{value:g} kHz")
            return cls._with_tag(parts, meta.tag)

        edition = str(meta.manual_edition or meta.edition or "")
        format_name = cls._codec(meta.type)
        scan_type = "OCR" if meta.ocr else "SCAN" if cls._source(meta.source).upper() == "SCAN" else ""
        isbn = re.sub(r"[^0-9Xx]", "", str(meta.isbn or ""))
        return cls._with_tag([author, "-", title, edition, year, format_name, scan_type, isbn], meta.tag)
