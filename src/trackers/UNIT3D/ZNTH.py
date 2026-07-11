import os
from typing import Any

import aiofiles

from src.book_prep import extract_first_author as _primary_name
from src.console import logger
from src.meta import Meta
from src.trackers.COMMON import COMMON
from src.trackers.UNIT3D import UNIT3D, ParamsList

Config = dict[str, Any]


def _iso_639_2_code(iso3: str) -> str:
    """Uppercase 3-letter language code (e.g. 'ENG') from a normalized ISO 639-2 code, or ''."""
    code = (iso3 or "").strip().upper()
    return code if len(code) == 3 else ""


def _is_misc(meta: Meta) -> bool:
    """True for comic/manga/magazine/newspaper (ZNTH Misc, not ebook/audiobook)."""
    return bool(meta.comic or meta.manga or meta.magazine or meta.newspaper)


def _book_format(meta: Meta) -> str:
    """Uppercased format token, e.g. 'EPUB', 'M4B'."""
    return str(meta.type or meta.container or "").strip().upper().lstrip(".")


class ZNTH(UNIT3D):
    supported_categories = ("TV", "MOVIE", "BOOK", "GAME")
    tracker_urls = ['https://znth.cx']

    def __init__(self, config: Config) -> None:
        super().__init__(config, tracker_name="ZNTH")
        self.config = config
        self.common = COMMON(config)
        self.tracker = "ZNTH"
        self.base_url = "https://znth.cx"
        self.id_url = f"{self.base_url}/api/torrents/"
        self.upload_url = f"{self.base_url}/api/torrents/upload"
        self.requests_url = f"{self.base_url}/api/requests/filter"
        self.search_url = f"{self.base_url}/api/torrents/filter"
        self.torrent_url = f"{self.base_url}/torrents/"
        self.banned_url = f"{self.base_url}/api/bannedReleaseGroups"
        self.banned_groups: list[str] = []

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
                source = (str(meta.manual_source or "").strip() or str(meta.source or "").strip() or "WEB").upper()

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

                source = str(meta.source or "").strip().upper()
                manual_source = str(meta.manual_source or "").strip().upper()
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

        elif category in ("TV", "MOVIE"):
            znth_name = meta.name
            if meta.category == "TV" and meta.episode_title != "":
                znth_name = znth_name.replace(f"{meta.episode_title} {meta.resolution}", f"{meta.resolution}", 1)
            imdb_year = str(meta.imdb_info.get("year", ""))
            year = str(meta.year) if meta.year is not None else ""
            if meta.category != "TV" and imdb_year and imdb_year.strip() and year and year.strip() and imdb_year != year:
                znth_name = znth_name.replace(f"{year}", imdb_year, 1)
            return {"name": znth_name}

        else:
            return {"name": meta.name}

    async def get_category_id(self, meta: Meta, category: str = "", reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        category_id = {
            "MOVIE": "1",
            "TV": "2",
            "AUDIOBOOK": "7",
            "BOOK": "6",
            "MISC": "9",
            "GAME": "3",
        }
        if mapping_only:
            return category_id
        elif reverse:
            return {v: k for k, v in category_id.items()}
        elif category:
            return {"category_id": category_id.get(category, "0")}
        else:
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
        elif reverse:
            return {v: k for k, v in type_id.items()}
        elif type:
            resolved_type = type.upper().strip()
            return {"type_id": type_id.get(resolved_type, "0")}
        else:
            category = meta.category
            meta_type = meta.type
            if isinstance(meta_type, str):
                meta_type = meta_type.upper().strip().lstrip(".")

            if category == "GAME":
                resolved_id = "16"
            elif category == "BOOK":
                resolved_id = type_id.get(_book_format(meta) or "", "16")
            else:
                resolved_id = type_id.get(meta_type or "", "0")

            return {"type_id": resolved_id}

    async def get_additional_data(self, meta: Meta) -> dict[str, str]:
        data: dict[str, str] = {}
        if meta.category == "BOOK" and not _is_misc(meta):
            if meta.isbn:
                data["isbn"] = str(meta.isbn)
            if meta.asin:
                data["asin"] = str(meta.asin)
        return data

    async def get_additional_files(self, meta: Meta) -> dict[str, tuple[str, bytes, str]]:
        files = await super().get_additional_files(meta)
        # audiobook: send the original uncropped cover, real format sniffed; base cover if >5MB
        if meta.audiobook and meta.cover_path and os.path.exists(meta.cover_path):
            if os.path.getsize(meta.cover_path) <= 5 * 1024 * 1024:
                async with aiofiles.open(meta.cover_path, "rb") as f:
                    raw = await f.read()
                if raw[:3] == b"\xff\xd8\xff":
                    files["torrent-cover"] = ("cover.jpg", raw, "image/jpeg")
                elif raw[:8] == b"\x89PNG\r\n\x1a\n":
                    files["torrent-cover"] = ("cover.png", raw, "image/png")
        return files
