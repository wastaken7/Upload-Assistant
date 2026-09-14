import contextlib
import re
import unicodedata
from typing import Any, cast

from src.book_prep import extract_first_author as _primary_name
from src.console import logger
from src.meta import Meta
from src.release_name import NameContext, NameRule, NameSelector, TrackerNameProfile, collapse_whitespace, template
from src.trackers.common import Common
from src.trackers.naming import append_context_value, zenith_video_name
from src.trackers.UNIT3D import UNIT3D, ParamsList

Config = dict[str, Any]


def _iso_639_2_code(iso3: str) -> str:
    """Uppercase 3-letter language code (e.g. 'ENG') from a normalized ISO 639-2 code, or ''."""
    code = (iso3 or "").strip().upper()
    return code if len(code) == 3 else ""


def _is_misc(meta: Meta) -> bool:
    """True for comic/manga/magazine/newspaper (Zenith Misc, not ebook/audiobook)."""
    return meta.comic or meta.manga or meta.magazine or meta.newspaper


def _book_format(meta: Meta) -> str:
    """Uppercased format token, e.g. 'EPUB', 'M4B'."""
    return (meta.type or meta.container or "").strip().upper().lstrip(".")


class Zenith(UNIT3D):
    """
    Zenith is an Private Torrent Tracker for MOVIES / TV / GENERAL
    """

    tracker = "ZENITH"
    name_profile = TrackerNameProfile(
        rules=(
            NameRule(NameSelector(category="MUSIC"), template("music_artist", "music_dash", "music_album", "music_year", "format_dash", "music_format")),
            NameRule(
                NameSelector(category="BOOK"),
                template(
                    "book_author",
                    "book_dash",
                    "book_series",
                    "series_dash",
                    "book_title",
                    "book_year",
                    "book_language",
                    "book_edition",
                    "book_narrator",
                    "book_source",
                    "book_container",
                    "book_codec",
                    "book_bitrate",
                    "book_retail",
                ),
            ),
            NameRule(NameSelector(), template("base_name")),
        ),
        transforms=(collapse_whitespace, zenith_video_name, append_context_value("direct_tag")),
    )

    async def get_name_overrides(self, context: NameContext) -> dict[str, str]:
        meta = context.meta
        if meta.category == "MUSIC":
            release = cast(dict[str, Any], meta.music_release) if isinstance(meta.music_release, dict) else {}
            artist_value = self._music_field(release, "artist", meta.artist)
            artist = str(artist_value).strip() if isinstance(artist_value, str) else ""
            if not artist:
                artists = self._music_field(release, "artists", [])
                artist = " & ".join(str(item).strip() for item in artists if str(item).strip()) if isinstance(artists, list) else str(artists or "").strip()
            album = str(self._music_field(release, "album", meta.title or meta.name) or "").strip()
            year = self._music_field(release, "release_year", self._music_field(release, "year", meta.year))
            source = self._music_source(self._music_field(release, "media", meta.source))
            tracks = release.get("tracks") if isinstance(release.get("tracks"), list) else []
            first = tracks[0] if tracks and isinstance(tracks[0], dict) else {}
            codec = str(self._music_field(release, "format", first.get("codec") or first.get("format") or meta.format or meta.type) or "").upper().strip()
            format_parts = [part for part in (source, codec) if part]
            depth = first.get("bit_depth") or self._music_field(release, "nfo_bit_depth")
            rate = first.get("sample_rate") or self._music_field(release, "nfo_sample_rate")
            depth_name = f"{depth}bit" if depth else ""
            rate_name = self._music_sample_rate(rate) if rate else ""
            if depth_name or rate_name:
                format_parts.append(f"{depth_name}-{rate_name}" if depth_name and rate_name else depth_name or rate_name)
            bitrate = first.get("bitrate")
            if bitrate and codec not in {"FLAC", "ALAC", "WAV", "AIFF"}:
                with contextlib.suppress(TypeError, ValueError):
                    format_parts.append(f"{round(float(bitrate) / 1000)} {str(first.get('bitrate_mode') or '').upper().strip()}".strip())
            if str(self._music_field(release, "release_type", "")).casefold() == "single":
                format_parts.append("Single")
            return {
                "music_artist": artist,
                "music_dash": "-",
                "music_album": album,
                "music_year": f"({year})" if year else "",
                "format_dash": "-" if format_parts else "",
                "music_format": f"[{' '.join(format_parts)}]" if format_parts else "",
                "direct_tag": str(meta.tag or "").strip(),
            }
        if meta.category == "BOOK" and _is_misc(meta):
            return {"book_title": meta.name}
        if meta.category != "BOOK":
            return {}
        author = _primary_name(meta.author or "")
        title = (meta.title or meta.name or "").strip()
        year = str(meta.year) if meta.year is not None else ""
        format_name = _book_format(meta)
        language = _iso_639_2_code(meta.book_language_iso)
        edition = str(meta.manual_edition or meta.edition or "").strip()
        if meta.audiobook:
            source = ((meta.manual_source or "").strip() or (meta.source or "").strip() or "WEB").upper()
            container, codec = {"FLAC": ("", "FLAC"), "MP3": ("", "MP3"), "M4B": ("M4B", "AAC")}.get(format_name, ("", format_name))
            narrator = _primary_name(meta.narrator or "")
            return {
                "book_author": author,
                "book_dash": "-" if author and title else "",
                "book_series": "",
                "book_title": title,
                "book_year": f"({year})" if year else "",
                "book_language": language,
                "book_edition": edition,
                "book_narrator": f"{{{narrator}}}" if narrator else "",
                "book_source": f"[{source}]" if source else "",
                "book_container": container,
                "book_codec": codec,
                "book_bitrate": f"{meta.audiobook_bitrate}kbps" if meta.audiobook_bitrate else "",
                "direct_tag": (meta.tag or "").strip(),
            }
        series = (meta.book_series or "").strip()
        index = (meta.book_series_index or "").strip()
        series = f"{series} #{index}" if series and index else series
        if edition and ("1st" in edition.lower() or "first" in edition.lower()):
            edition = ""
        elif edition and not any(token in ("edition", "ed") for token in edition.lower().replace(".", " ").split()):
            edition = f"{edition} Edition"
        source = (meta.source or "").strip().upper()
        manual_source = (meta.manual_source or "").strip().upper()
        if manual_source in ("RETAIL", "SCAN", "HYBRID"):
            source = manual_source
        if source not in ("RETAIL", "SCAN", "HYBRID"):
            source_text = (meta.basename_no_ext + " " + meta.title).lower()
            source = (
                "SCAN"
                if "scan" in source_text
                else "HYBRID"
                if "hybrid" in source_text
                else "RETAIL"
                if "retail" in source_text
                else "SCAN"
                if format_name == "PDF"
                else "RETAIL"
            )
        return {
            "book_author": author,
            "book_dash": "-" if author and (series or title) else "",
            "book_series": series,
            "series_dash": "-" if series and title else "",
            "book_title": title,
            "book_year": year,
            "book_language": language,
            "book_edition": edition,
            "book_codec": format_name,
            "book_retail": "Retail" if source == "RETAIL" or "retail" in meta.basename_no_ext.lower() else "",
            "direct_tag": (meta.tag or "").strip(),
        }

    display_name = "Zenith"
    allows_bloated_audio = True
    base_url = "https://znth.cx"
    banned_groups: tuple[str, ...] = ()
    id_url = f"{base_url}/api/torrents/"
    upload_url = f"{base_url}/api/torrents/upload"
    requests_url = f"{base_url}/api/requests/filter"
    search_url = f"{base_url}/api/torrents/filter"
    torrent_url = f"{base_url}/torrents/"
    banned_url = f"{base_url}/api/bannedReleaseGroups"
    supported_categories = ("TV", "MOVIE", "BOOK", "GAME", "MUSIC")
    tracker_urls = ("https://znth.cx",)

    _banned_authors_raw = (
        "J.R.R. Tolkien",
        "Anne Perry",
        "Simon Scarrow",
        "Sara Gruen",
        "Joan Elliott",
        "Alan Dart",
        "Chris Mead",
        "Paul Moore & Gavin Jones",
        "Noah K Sturdevant",
        "Benedict Brown",
        "Erika T Wurth",
        "Randolph Lalonde",
        "Andrea Sfiligoi",
        "Ana-Maria Babanica",
    )

    def __init__(self, config: Config) -> None:
        super().__init__(config, tracker_name="ZENITH")
        self.config = config
        self.common = Common(config)

        self.banned_author_sets: list[set[str]] = []
        for author in self._banned_authors_raw:
            parts = re.split(r"\s*(?:\&|\band\b)\s*", author, flags=re.IGNORECASE)
            for part in parts:
                norm = self._normalize_author(part)
                if norm:
                    self.banned_author_sets.append(norm)
                # Handle middle initials (e.g. Erika T Wurth)
                words = part.split()
                if len(words) > 2:
                    for idx, w in enumerate(words[1:-1], start=1):
                        if len(w.strip(".")) == 1:
                            without_initial = " ".join(words[:idx] + words[idx + 1 :])
                            norm_without = self._normalize_author(without_initial)
                            if norm_without:
                                self.banned_author_sets.append(norm_without)

    @staticmethod
    def _normalize_author(name: str) -> set[str]:
        if not name:
            return set()
        nfkd_form = unicodedata.normalize("NFKD", name)
        cleaned = "".join(c for c in nfkd_form if not unicodedata.combining(c))
        cleaned = re.sub(r"[^a-zA-Z0-9\s]", " ", cleaned)
        cleaned = cleaned.lower()
        words = cleaned.split()
        conjunctions = {"and", "e", "y", "with", "und", "et"}
        words = [w for w in words if w not in conjunctions]
        merged_words: list[str] = []
        initials_buffer: list[str] = []
        for w in words:
            if len(w) == 1 and w.isalpha():
                initials_buffer.append(w)
            else:
                if initials_buffer:
                    merged_words.append("".join(initials_buffer))
                    initials_buffer = []
                merged_words.append(w)
        if initials_buffer:
            merged_words.append("".join(initials_buffer))
        return set(merged_words)

    @staticmethod
    def _split_authors(author_str: str) -> list[str]:
        if not author_str:
            return []
        major_pattern = r"\s*(?:;|&|/|\+|\band\b|\be\b|\by\b|\bwith\b|\s+-\s+)\s*"
        candidates = re.split(major_pattern, author_str, flags=re.IGNORECASE)

        final_authors: list[str] = []
        for cand in candidates:
            cand = cand.strip()
            if not cand:
                continue
            if "," in cand:
                comma_parts = [p.strip() for p in cand.split(",")]
                if len(comma_parts) == 2:
                    _p1, p2 = comma_parts
                    p2_words = p2.split()
                    is_initials = all(len(w.strip(".")) <= 3 for w in p2_words)
                    if len(p2_words) == 1 or is_initials:
                        final_authors.append(cand)
                    else:
                        final_authors.extend(comma_parts)
                else:
                    final_authors.extend(comma_parts)
            else:
                final_authors.append(cand)
        return final_authors

    def _is_banned_author(self, meta_author: str) -> bool:
        if not meta_author:
            return False
        parts = self._split_authors(meta_author)
        for part in parts:
            part_norm = self._normalize_author(part)
            if not part_norm:
                continue
            for banned in self.banned_author_sets:
                if banned.issubset(part_norm):
                    return True
        return False

    async def get_additional_checks(self, meta: Meta) -> bool:
        if meta.category == "BOOK" and not _is_misc(meta):
            if not meta.isbn and not meta.asin:
                logger.info(f"{self.tracker}: [bold red]ISBN or ASIN is required for ebooks and audiobooks. Skipping upload...[/bold red]")
                return False
            book_format = _book_format(meta)
            if meta.audiobook:
                if not meta.narrator:
                    logger.info(f"{self.tracker}: [bold red]Narrator is required for audiobooks. Skipping upload...[/bold red]")
                    return False
                if book_format not in ("MP3", "FLAC", "M4B"):
                    logger.info(f"{self.tracker}: [bold red]Audiobooks must be MP3, FLAC, or M4B. Skipping upload...[/bold red]")
                    return False
            elif book_format not in ("EPUB", "PDF", "MOBI", "AZW3", "DJVU"):
                logger.info(f"{self.tracker}: [bold red]Ebooks must be EPUB, PDF, MOBI, AZW3, or DJVU. Skipping upload...[/bold red]")
                return False

            if meta.author and self._is_banned_author(meta.author):
                logger.info(f"{self.tracker}: [bold red]Author '{meta.author}' is banned on {self.tracker}. Skipping upload...[/bold red]")
                return False

        return self.common.check_and_confirm_adult_media_upload(meta, self.tracker)

    async def get_search_urls(self, meta: Meta, request_params: ParamsList) -> list[tuple[str, ParamsList, bool]]:
        urls = await super().get_search_urls(meta, request_params)
        if meta.category == "BOOK":
            if meta.isbn:
                urls.append((self.search_url, [("bookId", meta.isbn), ("perPage", "100")], False))
            if meta.asin:
                urls.append((self.search_url, [("bookId", meta.asin), ("perPage", "100")], False))
        return urls

    @staticmethod
    def _music_field(release: dict[str, Any], name: str, default: Any = "") -> Any:
        """Read a serialized MusicRelease field, ignoring its provenance metadata."""
        fields_raw = release.get("fields")
        fields = cast(dict[str, Any], fields_raw) if isinstance(fields_raw, dict) else {}
        field_raw = fields.get(name)
        field = cast(dict[str, Any], field_raw) if isinstance(field_raw, dict) else {}
        return field.get("value", default) if isinstance(field, dict) else default

    @staticmethod
    def _music_source(value: Any) -> str:
        """Use the source spelling prescribed by Zenith's music naming guide."""
        source = str(value or "").strip()
        aliases = {"cd": "CD", "web": "WEB", "vinyl": "Vinyl", "sacd": "SACD", "dvd": "DVD", "bd": "BD", "soundboard": "Soundboard", "dat": "DAT", "cassette": "Cassette"}
        return aliases.get(source.casefold(), source)

    @staticmethod
    def _music_sample_rate(value: Any) -> str:
        try:
            return f"{float(value) / 1000:g}kHz"
        except TypeError, ValueError:
            return ""

    async def get_category_id(self, meta: Meta, category: str = "", reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        category_id = {
            "MOVIE": "1",
            "TV": "2",
            "AUDIOBOOK": "7",
            "BOOK": "6",
            "MISC": "9",
            "GAME": "3",
            "MUSIC": "5",
        }
        if mapping_only:
            return category_id
        if reverse:
            return {v: k for k, v in category_id.items()}
        if category:
            return {"category_id": category_id.get(category, "0")}
        meta_category = meta.category
        if meta.audiobook:
            meta_category = "AUDIOBOOK"
        elif _is_misc(meta):
            meta_category = "MISC"
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
            "DVDRIP": "11",
            "FLAC": "7",
            "MP3": "8",
            "EPUB": "9",
            "M4B": "10",
            "PDF": "19",
            "OTHER": "16",
        }
        if mapping_only:
            return type_id
        if reverse:
            return {v: k for k, v in type_id.items()}
        if type:
            resolved_type = type.upper().strip()
            return {"type_id": type_id.get(resolved_type, "0")}
        category = meta.category
        meta_type = meta.type
        if isinstance(meta_type, str):
            meta_type = meta_type.upper().strip().lstrip(".")

        if category == "GAME":
            resolved_id = "16"
        elif category == "BOOK":
            resolved_id = type_id.get(_book_format(meta) or "", "16")
        elif category == "MUSIC":
            fmt = meta.format
            if not fmt and isinstance(meta.music_release, dict):
                fmt = self._music_field(meta.music_release, "format")
            resolved_id = type_id.get(str(fmt or "").upper(), "0")
        else:
            resolved_id = type_id.get(meta_type or "", "0")

        return {"type_id": resolved_id}

    async def get_additional_data(self, meta: Meta) -> dict[str, str]:
        data: dict[str, str] = {}
        if meta.category == "MUSIC":
            release = cast(dict[str, Any], meta.music_release) if isinstance(meta.music_release, dict) else {}
            external_ids_raw = release.get("external_ids")
            external_ids = cast(dict[str, Any], external_ids_raw) if isinstance(external_ids_raw, dict) else {}

            musicbrainz_release = str(external_ids.get("musicbrainz_release") or "").strip()
            musicbrainz_group = str(external_ids.get("musicbrainz_release_group") or "").strip()
            valid_musicbrainz = re.compile(r"^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$", re.IGNORECASE)
            if valid_musicbrainz.fullmatch(musicbrainz_release) or valid_musicbrainz.fullmatch(musicbrainz_group):
                data["exists_on_musicbrainz"] = "1"
                if valid_musicbrainz.fullmatch(musicbrainz_release):
                    data["musicbrainz_release_id"] = musicbrainz_release
                if valid_musicbrainz.fullmatch(musicbrainz_group):
                    data["musicbrainz_release_group_id"] = musicbrainz_group

            if meta.music_discogs_enabled:
                discogs_release = str(external_ids.get("discogs_release") or meta.music_discogs_release_id or meta.music_discogs_id or "").strip()
                discogs_master = str(external_ids.get("discogs_master") or meta.music_discogs_master_id or "").strip()
                if discogs_release.isdecimal() or discogs_master.isdecimal():
                    data["exists_on_discogs"] = "1"
                    if discogs_release.isdecimal():
                        data["discogs_release_id"] = discogs_release
                    if discogs_master.isdecimal():
                        data["discogs_master_id"] = discogs_master
        if meta.category == "BOOK" and not _is_misc(meta):
            if meta.isbn:
                data["isbn"] = meta.isbn
            if meta.asin:
                data["asin"] = meta.asin
        return data

    async def get_additional_files(self, meta: Meta) -> dict[str, tuple[str, bytes, str]]:
        files = await super().get_additional_files(meta)
        # Zenith only accepts the original audiobook cover when it is at most 5 MiB.
        if meta.audiobook and meta.artwork_path:
            cover_file = await self.get_image_file(meta.artwork_path, max_size=5 * 1024 * 1024)
            if cover_file:
                files["torrent-cover"] = cover_file
        return files
