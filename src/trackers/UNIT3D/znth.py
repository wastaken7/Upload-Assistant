import re
import unicodedata
from typing import Any, cast

from src.book_prep import extract_first_author as _primary_name
from src.console import logger
from src.meta import Meta
from src.trackers.common import Common
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

    async def get_name(self, meta: Meta) -> dict[str, str]:
        category = meta.category
        audiobook = meta.audiobook

        if category == "MUSIC":
            return {"name": self._music_name(meta)}

        if category == "BOOK":
            if _is_misc(meta):
                return {"name": meta.name}

            author = _primary_name(meta.author or "")
            title = (meta.title or meta.name or "").strip()
            year = str(meta.year) if meta.year is not None else ""
            format_val = _book_format(meta)
            # get_tag returns "" for books, so this is only a user-supplied --tag ("-Group")
            tag = (meta.tag or "").strip()

            if audiobook:
                # AudioBook: Author - Title (Year) LANG [Edition] {Narrator} [Source] [Container] Codec Bitrate
                language = _iso_639_2_code(meta.book_language_iso)
                edition = str(meta.manual_edition or meta.edition or "").strip()
                narrator = _primary_name(meta.narrator or "")
                source = ((meta.manual_source or "").strip() or (meta.source or "").strip() or "WEB").upper()

                audio_map = {
                    "FLAC": ("", "FLAC"),
                    "MP3": ("", "MP3"),
                    "M4B": ("M4B", "AAC"),
                }
                container, codec = audio_map.get(format_val, ("", format_val))

                bitrate_val = f"{meta.audiobook_bitrate}kbps" if meta.audiobook_bitrate else ""

                parts: list[str] = []
                if author:
                    parts.append(author)
                if title:
                    if parts:
                        parts.append("-")
                    parts.append(title)
                if year:
                    parts.append(f"({year})")
                if language:
                    parts.append(language)
                if edition:
                    parts.append(edition)
                if narrator:
                    parts.append(f"{{{narrator}}}")
                if source:
                    parts.append(f"[{source}]")
                if container:
                    parts.append(container)
                if codec:
                    parts.append(codec)
                if bitrate_val:
                    parts.append(bitrate_val)

                base_name = " ".join(parts)
                base_name = " ".join(base_name.split())
                znth_name = f"{base_name}{tag}"

            else:
                # eBook: Author - [Series #N -] Title [Year] LANG [Edition] Format [Retail]
                language = _iso_639_2_code(meta.book_language_iso)
                series = (meta.book_series or "").strip()
                series_index = (meta.book_series_index or "").strip()
                series_part = ""
                if series:
                    series_part = f"{series} #{series_index}" if series_index else series
                edition = str(meta.manual_edition or meta.edition or "").strip()
                if edition:
                    edition_lower = edition.lower()
                    if "1st" in edition_lower or "first" in edition_lower:
                        edition = ""
                    elif not any(t in ("edition", "ed") for t in edition_lower.replace(".", " ").split()):
                        edition = f"{edition} Edition"

                source = (meta.source or "").strip().upper()
                manual_source = (meta.manual_source or "").strip().upper()
                if manual_source in ("RETAIL", "SCAN", "HYBRID"):
                    source = manual_source
                if source not in ("RETAIL", "SCAN", "HYBRID"):
                    filename_lower = (meta.basename_no_ext + " " + meta.title).lower()
                    if "scan" in filename_lower:
                        source = "SCAN"
                    elif "hybrid" in filename_lower:
                        source = "HYBRID"
                    elif "retail" in filename_lower:
                        source = "RETAIL"
                    else:
                        source = "SCAN" if format_val == "PDF" else "RETAIL"
                is_retail = source == "RETAIL" or "retail" in meta.basename_no_ext.lower()

                parts = []
                if author:
                    parts.append(author)
                if series_part:
                    if parts:
                        parts.append("-")
                    parts.append(series_part)
                if title:
                    if parts:
                        parts.append("-")
                    parts.append(title)
                if year:
                    parts.append(year)
                if language:
                    parts.append(language)
                if edition:
                    parts.append(edition)
                if format_val:
                    parts.append(format_val)
                if is_retail:
                    parts.append("Retail")

                base_name = " ".join(parts)
                base_name = " ".join(base_name.split())
                znth_name = f"{base_name}{tag}"

            return {"name": znth_name}

        if category in ("TV", "MOVIE"):
            znth_name = meta.name
            if meta.category == "TV" and meta.episode_title != "":
                znth_name = znth_name.replace(f"{meta.episode_title} {meta.resolution}", f"{meta.resolution}", 1)
            imdb_year = str(meta.imdb_info.get("year", ""))
            year = str(meta.year) if meta.year is not None else ""
            if meta.category != "TV" and imdb_year and imdb_year.strip() and year and year.strip() and imdb_year != year:
                znth_name = znth_name.replace(f"{year}", imdb_year, 1)
            return {"name": znth_name}

        return {"name": meta.name}

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

    @classmethod
    def _music_name(cls, meta: Meta) -> str:
        """Format MUSIC as ``Artist - Album (Year) - [Format]`` for Zenith."""
        release = cast(dict[str, Any], meta.music_release) if isinstance(meta.music_release, dict) else {}
        artist_value = cls._music_field(release, "artist", meta.artist)
        artist = str(artist_value).strip() if isinstance(artist_value, str) else ""
        if not artist:
            artists = cls._music_field(release, "artists", [])
            artist_list = cast(list[Any], artists) if isinstance(artists, list) else []
            artist = " & ".join(str(item).strip() for item in artist_list if str(item).strip()) if artist_list else str(artists or "").strip()
        album = cls._music_field(release, "album", meta.title or meta.name)
        year = cls._music_field(release, "release_year", cls._music_field(release, "year", meta.year))
        source = cls._music_source(cls._music_field(release, "media", meta.source))
        tracks_raw = release.get("tracks")
        tracks = cast(list[Any], tracks_raw) if isinstance(tracks_raw, list) else []
        first_track: dict[str, Any] = {}
        if tracks and isinstance(tracks[0], dict):
            first_track = cast(dict[str, Any], tracks[0])
        codec = str(cls._music_field(release, "format", first_track.get("codec") or first_track.get("format") or meta.format or meta.type) or "").upper().strip()

        format_parts: list[str] = [part for part in (source, codec) if part]
        bit_depth = first_track.get("bit_depth") or cls._music_field(release, "nfo_bit_depth")
        sample_rate = first_track.get("sample_rate") or cls._music_field(release, "nfo_sample_rate")
        bit_depth_name = f"{bit_depth}bit" if bit_depth else ""
        sample_rate_name = cls._music_sample_rate(sample_rate) if sample_rate else ""
        if bit_depth_name and sample_rate_name:
            format_parts.append(f"{bit_depth_name}-{sample_rate_name}")
        elif bit_depth_name or sample_rate_name:
            format_parts.append(bit_depth_name or sample_rate_name)
        bitrate = first_track.get("bitrate")
        if bitrate and codec not in {"FLAC", "ALAC", "WAV", "AIFF"}:
            try:
                bitrate_kbps = round(float(bitrate) / 1000)
                bitrate_mode = str(first_track.get("bitrate_mode") or "").upper().strip()
                format_parts.append(f"{bitrate_kbps} {bitrate_mode}".strip())
            except TypeError, ValueError:
                pass
        release_type = str(cls._music_field(release, "release_type", "")).casefold()
        if release_type == "single":
            format_parts.append("Single")

        title_parts = [str(artist or "").strip(), "-", str(album or "").strip()]
        if year:
            title_parts.append(f"({year})")
        if format_parts:
            title_parts.extend(["-", f"[{' '.join(part for part in format_parts if part)}]"])
        name = " ".join(part for part in title_parts if part)
        name = " ".join(name.split())
        return f"{name}{str(meta.tag or '').strip()}"

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
