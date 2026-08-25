# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
"""Book and Audiobook preparation helpers.

This module contains the logic that was previously inlined inside the
``Prep`` class in ``prep.py``.  It is intentionally kept free of any
``Prep``-specific imports so it can be tested and extended in isolation.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import os
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import langcodes

from src.book_extractors import (
    extract_audiobook_series_from_title as _extract_audiobook_series_from_title,
)
from src.book_extractors import (
    extract_cbr_cbz_metadata as _extract_cbr_cbz_metadata,
)
from src.book_extractors import (
    extract_epub_metadata as _extract_epub_metadata,
)
from src.book_extractors import (
    extract_isbn_from_pdf as _extract_isbn_from_pdf,
)
from src.book_extractors import (
    extract_mobi_metadata as _extract_mobi_metadata,
)
from src.book_extractors import (
    extract_series_from_filename as _extract_series_from_filename,
)
from src.book_extractors import (
    get_epubmeta_output as _get_epubmeta_output,
)
from src.book_extractors import (
    normalize_series_index as _normalize_series_index,
)
from src.console import logger
from src.exportmi import export_info
from src.genre_map import map_audiobook_keywords
from src.meta import Meta

# ---------------------------------------------------------------------------
# File-list resolution
# ---------------------------------------------------------------------------

BOOK_EXTENSIONS = frozenset(
    {".pdf", ".epub", ".mobi", ".azw", ".azw3", ".fb2", ".html", ".htm", ".chm", ".djvu", ".doc", ".docx", ".kfx", ".lit", ".pdb", ".txt", ".rtf", ".cbz", ".cbr"}
)
AUDIOBOOK_EXTENSIONS = frozenset(
    {
        ".mp3",
        ".m4b",
        ".flac",
        ".alac",
        ".aac",
        ".m4a",
        ".ogg",
        ".opus",
        ".wav",
        ".ac3",
        ".dts",
        ".aiff",
        ".ape",
        ".wv",
        ".wma",
        ".aax",
        ".aaxc",
    }
)
_TEXT_SIDECAR_STEMS = frozenset({"cover", "folder", "index", "info", "readme"})


def resolve_book_filelist(
    meta: Meta,
    videoloc: str,
) -> tuple[str, list[str], str, str]:
    """Scan *videoloc* for book/audiobook files and update *meta* in-place.

    Populates ``meta.filelist``, ``meta.scene``, ``meta.imdb_id``,
    and ``meta.audiobook``.

    Returns:
        A 4-tuple ``(videopath, filelist, search_term, search_file_folder)``
        where *videopath* is the primary file used as the "video" reference
        for downstream processing (the largest audio file for audiobooks).
    """
    allowed_extensions = BOOK_EXTENSIONS | AUDIOBOOK_EXTENSIONS

    filelist: list[str] = []
    if Path(videoloc).is_dir():
        for root, _, files in os.walk(videoloc):
            for file in files:
                ext = Path(file).suffix.lower()
                if ext in allowed_extensions:
                    filelist.append(str(Path(Path(root) / file).resolve()))
        filelist = sorted(filelist)
        if not filelist:
            logger.info("[bold red]No Book or Audiobook files found!")
            sys.exit(1)
        richer_book_files = [file for file in filelist if Path(file).suffix.lower() in BOOK_EXTENSIONS - {".txt", ".html", ".htm"}]
        if richer_book_files:
            filelist = [file for file in filelist if not (Path(file).suffix.lower() in {".txt", ".html", ".htm"} and Path(file).stem.casefold() in _TEXT_SIDECAR_STEMS)]
    else:
        filelist.append(videoloc)

    meta.filelist = filelist
    meta.imdb_id = 0

    audio_files = [file for file in filelist if Path(file).suffix.lower() in AUDIOBOOK_EXTENSIONS]
    meta.audiobook = bool(meta.audiobook or audio_files)
    videopath = max(audio_files if meta.audiobook and audio_files else filelist, key=os.path.getsize)

    search_term = Path(filelist[0]).name if filelist else ""
    search_file_folder = "file"
    return videopath, filelist, search_term, search_file_folder


# ---------------------------------------------------------------------------
# Language resolution helper
# ---------------------------------------------------------------------------


def resolve_book_language(raw: str) -> tuple[str, str]:
    """Return ``(full_english_name, iso_639_3_alpha3)`` for any language input."""
    raw = raw.strip()
    with contextlib.suppress(Exception):
        lc = langcodes.get(raw.lower())
        full_name = lc.display_name("en") or raw.title()
        alpha3 = lc.to_alpha3() or ""
        if full_name and full_name.lower() != raw.lower():
            return full_name, alpha3
    try:
        lc = langcodes.find(raw)
        return lc.display_name("en") or raw.title(), lc.to_alpha3() or ""
    except Exception:
        return raw.title(), ""


def is_valid_book_language(full: str, iso: str) -> bool:
    """Return True if the language is valid (not undefined, unknown, or empty)."""
    if not full or not iso:
        return False
    full_lower = full.strip().lower()
    iso_lower = iso.strip().lower()
    if full_lower in ("", "unknown", "unknown language", "undetermined", "und", "none", "null"):
        return False
    return iso_lower not in ("", "und", "zxx")


def sanitize_book_language(meta: Meta) -> None:
    """Validate and sanitize book_language and book_language_iso in meta. Clear them if invalid."""
    lang = meta.book_language
    if not lang:
        meta.book_language = ""
        meta.book_language_iso = ""
        return

    full, iso = resolve_book_language(lang.strip())
    if is_valid_book_language(full, iso):
        meta.book_language = full
        meta.book_language_iso = iso
    else:
        meta.book_language = ""
        meta.book_language_iso = ""


# ---------------------------------------------------------------------------
# MediaInfo metadata extraction
# ---------------------------------------------------------------------------


def _mi_extra(general_track: dict[str, Any], name: str) -> str:
    """Case-insensitive lookup of a freeform tag in a MediaInfo General track's extra dict."""
    extra = general_track.get("extra")
    if not isinstance(extra, dict):
        return ""
    for key, val in extra.items():
        if key.lower() == name.lower() and val and not isinstance(val, dict):
            text = str(val).strip()
            if text:
                return text
    return ""


def _unescape_meta_val(val: Any) -> str | None:
    if val is None or isinstance(val, (dict, list)):
        return None
    import html

    return html.unescape(str(val)).strip()


def _is_chapter_title(value: str | None) -> bool:
    """Return whether a MediaInfo title is only an audiobook chapter label."""
    return bool(value and re.fullmatch(r"(?:cap[ií]tulo|chapter)\s+\d+(?:\.\d+)?", value.strip(), re.IGNORECASE))


async def gather_book_prep(
    meta: Meta,
    videopath: str,
    base_dir: str,
    config: dict[str, Any] | None = None,
) -> None:
    """Set up BOOK/Audiobook category fields and extract embedded MediaInfo metadata.

    Sets ``meta.category``, ``meta.resolution``, ``meta.search_year``,
    ``meta.hfr``, ``meta.sd``, and ``meta.mediainfo``, then attempts
    to populate title, author, narrator, publisher, ISBN, overview, year,
    keywords, and language from the file's embedded tags.
    """
    meta.category = "BOOK"
    meta.search_year = ""
    meta.resolution = "Other"
    meta.hfr = False
    meta.sd = 0
    meta.valid_mi_settings = True

    # Warn if Google Books API key is missing
    api_key = ""
    if config and "DEFAULT" in config:
        api_key = config["DEFAULT"].get("google_books_api_key", "").strip()
    if not api_key:
        logger.warning("[bold red]Warning: Google Books API key is not configured. Book metadata searches will be limited and incomplete.[/bold red]")

    # Check if the file format is CBR or CBZ and automatically set comic to True
    file_ext = Path(videopath).suffix.lstrip(".").upper()
    if file_ext in ("CBR", "CBZ"):
        meta.comic = True

    # Identify CLI overrides at the very start
    cli_overrides = {
        "title": bool(meta.book_title),
        "author": bool(meta.book_author),
        "publisher": bool(meta.book_publisher),
        "isbn": bool(meta.book_isbn),
        "asin": bool(meta.book_asin),
        "book_language": bool(meta.book_language),
        "year": "manual_year" in meta and (meta.manual_year or 0) > 0,
        "keywords": bool(meta.keywords),
        "overview": bool(meta.overview),
    }

    # Extract EPUB metadata directly if the file is an EPUB
    if videopath.lower().endswith(".epub") and Path(videopath).is_file():
        meta.epubmeta_output = _get_epubmeta_output(videopath)
        epub_meta = _extract_epub_metadata(videopath)
        if epub_meta:
            logger.debug(f"[cyan]EPUB metadata extracted: {epub_meta}[/cyan]")
            for key, val in epub_meta.items():
                if key == "book_language_raw":
                    full, iso3 = resolve_book_language(val)
                    if is_valid_book_language(full, iso3) and not meta.book_language:
                        meta.book_language = full
                        meta.book_language_iso = iso3
                else:
                    if not meta.get(key) and val:
                        if key == "year":
                            meta[key] = int(val)
                        else:
                            meta[key] = val
                        if key == "year":
                            meta.search_year = int(val)

    # Extract CBR/CBZ metadata directly if the file is a CBR/CBZ
    if videopath.lower().endswith((".cbr", ".cbz")) and Path(videopath).is_file():
        cbr_cbz_meta = _extract_cbr_cbz_metadata(videopath)
        if cbr_cbz_meta:
            logger.debug(f"[cyan]CBR/CBZ metadata extracted: {cbr_cbz_meta}[/cyan]")
            for key, val in cbr_cbz_meta.items():
                if key == "book_language_raw":
                    full, iso3 = resolve_book_language(val)
                    if is_valid_book_language(full, iso3) and not meta.book_language:
                        meta.book_language = full
                        meta.book_language_iso = iso3
                else:
                    if not meta.get(key) and val:
                        if key == "year":
                            meta[key] = int(val)
                        else:
                            meta[key] = val
                        if key == "year":
                            meta.search_year = int(val)

    # AZW and AZW3 are Kindle variants of the MOBI family.  The extractor may
    # not support every DRM/KFX variant, but it safely returns no metadata then.
    if videopath.lower().endswith((".mobi", ".azw", ".azw3")) and Path(videopath).is_file():
        mobi_meta = _extract_mobi_metadata(videopath)
        if mobi_meta:
            logger.debug(f"[cyan]MOBI metadata extracted: {mobi_meta}[/cyan]")
            for key, val in mobi_meta.items():
                if key == "book_language_raw":
                    full, iso3 = resolve_book_language(val)
                    if is_valid_book_language(full, iso3) and not meta.book_language:
                        meta.book_language = full
                        meta.book_language_iso = iso3
                else:
                    if not meta.get(key) and val:
                        if key == "year":
                            meta[key] = int(val)
                        else:
                            meta[key] = val
                        if key == "year":
                            meta.search_year = int(val)

    # Extract ISBN from PDF directly if the file is a PDF
    if videopath.lower().endswith(".pdf") and Path(videopath).is_file():
        pdf_isbn = _extract_isbn_from_pdf(videopath)
        if pdf_isbn and not meta.isbn:
            meta.isbn = pdf_isbn
            logger.debug(f"[cyan]PDF ISBN extracted: {pdf_isbn}[/cyan]")

    if not meta.edit:
        try:
            mi = await export_info(
                videopath,
                meta.isdir,
                meta.uuid,
                base_dir,
                is_dvd=(meta.is_disc == "DVD"),
            )
            meta.mediainfo = mi
        except Exception as e:
            logger.info(f"[yellow]Warning: MediaInfo export failed for book: {e}[/yellow]")
            meta.mediainfo = {}
    else:
        pass  # meta.mediainfo already populated from a previous run

    if meta.mediainfo:
        try:
            tracks = meta.mediainfo.get("media", {}).get("track", [])
            if not isinstance(tracks, list):
                tracks = []
            # Filter to only dictionary entries to prevent errors when calling .get() later
            tracks = [t for t in tracks if isinstance(t, dict)]
            general_track = next((t for t in tracks if t.get("@type") == "General"), None)
            if general_track:
                # 1. Title/Album
                album = _unescape_meta_val(general_track.get("Album") or general_track.get("album"))
                track_name = _unescape_meta_val(general_track.get("Track_name") or general_track.get("track_name"))
                title_tag = _unescape_meta_val(general_track.get("Title") or general_track.get("title"))
                if _is_chapter_title(title_tag) and album and not _is_chapter_title(album):
                    title_tag = album

                # Detect if the audiobook is Unabridged or Abridged from file metadata
                detected_edition = None
                for val in (title_tag, track_name, album):
                    if val:
                        match = re.search(r"\b(unabridged|abridged)\b", val, re.IGNORECASE)
                        if match:
                            detected_edition = match.group(1).capitalize()
                            break
                if detected_edition and not meta.edition:
                    meta.edition = detected_edition

                if not meta.title:
                    meta.title = title_tag or track_name or album or ""

                # Clean the edition from the title if it's not a CLI override
                if not cli_overrides["title"] and meta.title:
                    original_title = meta.title
                    # Remove brackets like [...] and their content
                    cleaned_title = re.sub(r"\s*\[[^\]]*\]", "", original_title)
                    cleaned_title = re.sub(r"\s*[\(\[\{-]?\s*\b(unabridged|abridged)\b\s*[\)\]\}]?\s*", " ", cleaned_title, flags=re.IGNORECASE)
                    cleaned_title = re.sub(r"\s+", " ", cleaned_title).strip()
                    cleaned_title = cleaned_title.strip("-").strip()
                    meta.title = cleaned_title

                # 2. Author
                performer = _unescape_meta_val(general_track.get("Performer") or general_track.get("performer"))
                album_performer = _unescape_meta_val(general_track.get("Album_Performer") or general_track.get("album_performer"))
                if not meta.author:
                    if performer:
                        meta.author = performer
                    elif album_performer:
                        meta.author = album_performer

                # 3. Narrator
                composer = _unescape_meta_val(general_track.get("Composer") or general_track.get("composer"))
                if composer and not meta.narrator:
                    meta.narrator = composer

                # 4. Publisher
                publisher = _unescape_meta_val(general_track.get("Publisher") or general_track.get("publisher"))
                if publisher and not meta.publisher:
                    meta.publisher = publisher

                # 5. ISBN
                isbn_val = general_track.get("ISBN") or general_track.get("isbn")
                if not isbn_val and isinstance(general_track.get("extra"), dict):
                    isbn_val = general_track["extra"].get("ISBN") or general_track["extra"].get("isbn")
                isbn_val = _unescape_meta_val(isbn_val)
                if isbn_val and not meta.isbn:
                    meta.isbn = isbn_val

                # 5b. ASIN
                asin_val = general_track.get("ASIN") or general_track.get("asin")
                if not asin_val and isinstance(general_track.get("extra"), dict):
                    asin_val = general_track["extra"].get("ASIN") or general_track["extra"].get("asin")
                asin_val = _unescape_meta_val(asin_val)
                if asin_val and not meta.asin:
                    meta.asin = asin_val

                # Series from extra.SERIES / extra.SERIESPART
                if not meta.book_series:
                    series_val = _mi_extra(general_track, "SERIES")
                    if series_val:
                        meta.book_series = series_val
                        part_val = _mi_extra(general_track, "SERIESPART")
                        if part_val and not meta.book_series_index:
                            meta.book_series_index = _normalize_series_index(part_val)

                if not cli_overrides["title"] and meta.title:
                    original_title = meta.title
                    parsed_title, parsed_series, parsed_index = _extract_audiobook_series_from_title(original_title)
                    if parsed_series:
                        meta.title = parsed_title
                        localized_history_series = re.search(r":\s*Hist[oó]ria\s+\d+(?:\.\d+)?\s+de\s+.+$", original_title, re.IGNORECASE)
                        if localized_history_series or not meta.book_series:
                            meta.book_series = parsed_series
                        if parsed_index and (localized_history_series or not meta.book_series_index):
                            meta.book_series_index = parsed_index

                # 6. Overview/Comment
                comment = _unescape_meta_val(general_track.get("Comment") or general_track.get("comment"))
                description = _unescape_meta_val(general_track.get("Description") or general_track.get("description"))
                if not meta.overview:
                    if comment:
                        meta.overview = comment
                    elif description:
                        meta.overview = description

                # 7. Year (extract 4-digit number)
                rec_date = _unescape_meta_val(general_track.get("Recorded_Date") or general_track.get("recorded_date"))
                if rec_date and not meta.year:
                    match = re.search(r"\b\d{4}\b", rec_date)
                    if match:
                        meta.year = int(match.group(0))
                        meta.search_year = int(match.group(0))

                # 8. Genre -> Keywords
                genre = _unescape_meta_val(general_track.get("Genre") or general_track.get("genre"))
                if genre:
                    cleaned_words = map_audiobook_keywords(genre)
                    if cleaned_words:
                        existing_keywords = meta.keywords
                        existing_list: list[str] = []
                        if existing_keywords:
                            # existing_keywords is guaranteed to be a list of strings
                            existing_list.extend([x.strip().lower() for x in existing_keywords if x.strip()])
                        for cw in cleaned_words:
                            if cw not in existing_list:
                                existing_list.append(cw)
                        meta.keywords = existing_list

                # 9. Language
                if not meta.book_language:
                    lang_val = _unescape_meta_val(general_track.get("Language") or general_track.get("language"))
                    if lang_val:
                        full, iso3 = resolve_book_language(lang_val)
                        if is_valid_book_language(full, iso3):
                            meta.book_language = full
                            meta.book_language_iso = iso3

                if not meta.book_language:
                    # Fallback: Audio track language (audiobooks)
                    for t in tracks:
                        if t.get("@type") == "Audio":
                            lang_val = _unescape_meta_val(t.get("Language") or t.get("language"))
                            if lang_val:
                                full, iso3 = resolve_book_language(lang_val)
                                if is_valid_book_language(full, iso3):
                                    meta.book_language = full
                                    meta.book_language_iso = iso3
                                    break

                if not meta.book_language:
                    # Fallback: Text track language (ebooks like PDF/EPUB)
                    for t in tracks:
                        if t.get("@type") == "Text":
                            lang_val = _unescape_meta_val(t.get("Language") or t.get("language"))
                            if lang_val:
                                full, iso3 = resolve_book_language(lang_val)
                                if is_valid_book_language(full, iso3):
                                    meta.book_language = full
                                    meta.book_language_iso = iso3
                                    break
        except Exception as ex:
            logger.debug(f"[yellow]Warning: Error extracting embedded book metadata: {ex}[/yellow]")

    # Series fallback from filename (embedded Calibre/MediaInfo tags take precedence)
    if not meta.book_series:
        fname_series, fname_index = _extract_series_from_filename(Path(videopath).name)
        if fname_series:
            meta.book_series = fname_series
            if fname_index and not meta.book_series_index:
                meta.book_series_index = fname_index

    # MyAnonamouse API search using torrent client comments (online lookup takes precedence)
    if not meta.torrent_comments and not meta.skip_auto_torrent and not meta.edit and config:
        from src.clients import Clients

        try:
            client = Clients(config=config)
            await client.get_pathed_torrents((meta.path if meta.path is not None else videopath), meta)
        except Exception as e:
            logger.debug(f"[yellow]Warning: Could not search client for book torrent comments: {e}[/yellow]")

    mam_id = None
    if meta.torrent_comments:
        for comment_data in meta.torrent_comments:
            trackers = str(comment_data.get("trackers", ""))
            comment = str(comment_data.get("comment", ""))

            def _is_mam_host(url_or_host: str) -> bool:
                value = (url_or_host or "").strip()
                if not value:
                    return False
                parsed = urlparse(value)
                host = parsed.hostname
                if not host and "://" not in value:
                    host = urlparse(f"//{value}").hostname
                if not host:
                    return False
                host = host.lower().rstrip(".")
                return host == "myanonamouse.net" or host.endswith(".myanonamouse.net")

            is_mam = _is_mam_host(trackers)
            if not is_mam and comment_data.get("tracker_urls"):
                for tu in comment_data["tracker_urls"]:
                    if (isinstance(tu, dict) and _is_mam_host(str(tu.get("url", "")))) or (isinstance(tu, str) and _is_mam_host(tu)):
                        is_mam = True
                        break

            if is_mam:
                match = re.search(r"\bMID=(\d+)", comment)
                if match:
                    mam_id = match.group(1)
                    logger.debug(f"[cyan]Found MyAnonamouse ID {mam_id} in torrent comment[/cyan]")
                    break

    mam_data = None
    if mam_id:
        try:
            api_key = ""
            if config and "DEFAULT" in config:
                api_key = config["DEFAULT"].get("mam_api_key", "").strip() or config["DEFAULT"].get("mam_id", "").strip()
            api_key = api_key or os.environ.get("MAM_API_KEY", "").strip() or os.environ.get("MAM_ID", "").strip()

            from src.myanonamouse import myanonamouse_manager

            mam_data = await myanonamouse_manager.search_by_id(mam_id, base_dir=base_dir, api_key=api_key)
            if mam_data:
                for key, val in mam_data.items():
                    if val:
                        # Enforce priority: CLI override > MAM > local metadata
                        is_override = False
                        if (
                            (key == "title" and cli_overrides["title"])
                            or (key == "author" and cli_overrides["author"])
                            or (key == "publisher" and cli_overrides["publisher"])
                            or (key == "isbn" and cli_overrides["isbn"])
                            or (key == "asin" and cli_overrides["asin"])
                            or (key in ("book_language", "book_language_iso") and cli_overrides["book_language"])
                            or (key in ("year", "search_year") and cli_overrides["year"])
                            or (key == "keywords" and cli_overrides["keywords"])
                            or (key == "overview" and cli_overrides["overview"])
                        ):
                            is_override = True

                        if not is_override:
                            if key == "year":
                                meta[key] = int(val)
                            else:
                                meta[key] = val
                            if key == "year" and "search_year" not in mam_data:
                                meta.search_year = int(val)
        except Exception as ex:
            logger.debug(f"[yellow]Warning: MyAnonamouse API lookup failed: {ex}[/yellow]")

    # Google Books API search using ISBN (online lookup takes precedence)
    google_books_data = None
    isbn = meta.isbn
    if isbn:
        try:
            api_key = ""
            if config and "DEFAULT" in config:
                api_key = config["DEFAULT"].get("google_books_api_key", "").strip()
            from src.google_books import google_books_manager

            google_books_data = await google_books_manager.search_by_isbn(isbn, base_dir=base_dir, api_key=api_key)
            if google_books_data:
                for key, val in google_books_data.items():
                    if val:
                        # Enforce priority: CLI override > MAM > Google Books > local metadata
                        is_override = False
                        if (
                            (key == "title" and cli_overrides["title"])
                            or (key == "author" and cli_overrides["author"])
                            or (key == "publisher" and cli_overrides["publisher"])
                            or (key == "isbn" and cli_overrides["isbn"])
                            or (key == "asin" and cli_overrides["asin"])
                            or (key in ("book_language", "book_language_iso") and cli_overrides["book_language"])
                            or (key in ("year", "search_year") and cli_overrides["year"])
                            or (key == "keywords" and cli_overrides["keywords"])
                            or (key == "overview" and cli_overrides["overview"])
                        ):
                            is_override = True

                        # Do not overwrite fields already populated by MAM, except for artwork (prefer Google Books cover)
                        if (
                            key != "artwork_url"
                            and mam_data
                            and (key in mam_data or (key == "book_language_iso" and "book_language" in mam_data) or (key == "search_year" and "year" in mam_data))
                        ):
                            is_override = True

                        if not is_override:
                            if key == "year":
                                meta[key] = int(val)
                            else:
                                meta[key] = val
                            if key == "year" and "search_year" not in google_books_data:
                                meta.search_year = int(val)
        except Exception as ex:
            logger.debug(f"[yellow]Warning: Google Books API lookup failed: {ex}[/yellow]")

    # OpenLibrary API search (online lookup takes precedence)
    openlibrary_data = None
    openlibrary_id = meta.openlibrary
    if openlibrary_id:
        from src.openlibrary import openlibrary_manager

        openlibrary_data = await openlibrary_manager.search_by_work_id(openlibrary_id, base_dir=base_dir)
    elif meta.isbn:
        from src.openlibrary import openlibrary_manager

        openlibrary_data = await openlibrary_manager.search_by_isbn(meta.isbn, base_dir=base_dir)

    if openlibrary_data:
        for key, val in openlibrary_data.items():
            if val:
                # Enforce priority: CLI override > MAM > Google Books > OpenLibrary > local metadata
                is_override = False
                if (
                    (key == "title" and cli_overrides["title"])
                    or (key == "author" and cli_overrides["author"])
                    or (key == "publisher" and cli_overrides["publisher"])
                    or (key == "isbn" and cli_overrides["isbn"])
                    or (key == "asin" and cli_overrides["asin"])
                    or (key in ("book_language", "book_language_iso") and cli_overrides["book_language"])
                    or (key in ("year", "search_year") and cli_overrides["year"])
                    or (key == "keywords" and cli_overrides["keywords"])
                    or (key == "overview" and cli_overrides["overview"])
                ):
                    is_override = True

                # Do not overwrite fields already populated by MAM
                if mam_data and (key in mam_data or (key == "book_language_iso" and "book_language" in mam_data) or (key == "search_year" and "year" in mam_data)):
                    is_override = True

                # Do not overwrite fields already populated by Google Books
                if google_books_data and (
                    key in google_books_data or (key == "book_language_iso" and "book_language" in google_books_data) or (key == "search_year" and "year" in google_books_data)
                ):
                    is_override = True

                if not is_override:
                    if key == "year":
                        meta[key] = int(val)
                    else:
                        meta[key] = val
                    if key == "year" and "search_year" not in openlibrary_data:
                        meta.search_year = int(val)

    if meta.audiobook:
        filelist = meta.filelist
        total_duration, duration_formatted = await get_audiobook_duration(filelist)
        meta.audiobook_duration = total_duration
        meta.audiobook_duration_formatted = duration_formatted

        avg_bitrate = await get_audiobook_bitrate(filelist)
        if avg_bitrate is not None:
            meta.audiobook_bitrate = avg_bitrate

        if meta.keywords:
            meta.keywords = map_audiobook_keywords(meta.keywords)

    if meta.audiobook:
        meta.title = normalize_audiobook_title(meta.title, meta.book_series)

    detect_newspaper(meta)
    sanitize_book_language(meta)
    sanitize_book_author(meta)


def normalize_audiobook_title(title: str, series: str) -> str:
    """Remove a repeated series name from the beginning or end of an audiobook title."""
    title = title.strip()
    series = series.strip()
    if not series:
        return title
    if len(title) > len(series):
        if title.casefold().endswith(series.casefold()):
            return title[: -len(series)].rstrip(" :-\u2013\u2014")
        if title.casefold().startswith(series.casefold()):
            return title[len(series) :].lstrip(" :-\u2013\u2014")
    return title


def detect_newspaper(meta: Meta) -> None:
    np_names = [
        # Brazil
        "Zm9saGEgZGUgcy5wYXVsbw==",
        "Zm9saGEgZGUgcy4gcGF1bG8=",
        "Zm9saGEgZGUgc2FvIHBhdWxv",
        "Zm9saGEgZGUgc8OjbyBwYXVsbw==",
        "ZXN0YWRhbw==",
        "ZXN0YWTDo28=",
        "byBlc3RhZG8gZGUgcy4gcGF1bG8=",
        "byBlc3RhZG8gZGUgcy5wYXVsbw==",
        "byBlc3RhZG8gZGUgc8OjbyBwYXVsbw==",
        "byBnbG9ibw==",
        "dmFsb3IgZWNvbm9taWNv",
        "dmFsb3IgZWNvbsO0bWljbw==",
        "Y29ycmVpbyBicmF6aWxpZW5zZQ==",
        "Y29ycmVpbyBicmFzaWxpZW5zZQ==",
        "emVybyBob3Jh",
        "ZXN0YWRvIGRlIG1pbmFz",
        "ZGlhcmlvIGRvIG5vcmRlc3Rl",
        "ZGnDoXJpbyBkbyBub3JkZXN0ZQ==",
        "Z2F6ZXRhIGRvIHBvdm8=",
        "am9ybmFsIGRvIGJyYXNpbA==",
        "am9ybmFsIGRvIGNvbWVyY2lv",
        "am9ybmFsIGRvIGNvbW1lcmNpbw==",
        "YSB0cmlidW5hIGRhIGltcHJlbnNh",
        "Zm9saGEgZGlyaWdpZGE=",
        "YSB2b3ogZGEgc2VycmE=",
        "dHJpYnVuYSBkZSBwZXRyb3BvbGlz",
        "dHJpYnVuYSBkZSBwZXRyw7Nwb2xpcw==",
        "aW52ZXJ0YSAtIGpvcm5hbCBwcmEgdmVyZGFkZQ==",
        "am9ybmFsIGRlIGJyYXNpbGlh",
        "am9ybmFsIGRlIGJyYXPDrWxpYQ==",
        "YnJhc2lsIGVtIHRlbXBvIHJlYWw=",
        "Y29ycmVpbyBkbyBwb3Zv",
        "am9ybmFsIG5o",
        "am9ybmFsIHZz",
        "ZGlhcmlvIGRlIGNhbm9hcw==",
        "ZGnDoXJpbyBkZSBjYW5vYXM=",
        "am9ybmFsIGRvIHR1cmZl",
        "YnJhc2lsIGRlIGZhdG8=",
        "am9ybmFsIGdhemV0YSBkbyBvZXN0ZQ==",
        "cG9ydGFsIGRvIHRyaWFuZ3Vsbw==",
        "cG9ydGFsIGRvIHRyacOibmd1bG8=",
        "Z2F6ZXRhIG9ubGluZQ==",
        "ZGlhcmlvIGRlIGN1aWFiYQ==",
        "ZGnDoXJpbyBkZSBjdWlhYsOh",
        "YSBjcml0aWNhIGRlIGNhbXBvIGdyYW5kZQ==",
        "YSBjcsOtdGljYSBkZSBjYW1wbyBncmFuZGU=",
        "Y29ycmVpbyBkbyBlc3RhZG8=",
        "ZGlhcmlvIGRlIHBlcm5hbWJ1Y28=",
        "ZGnDoXJpbyBkZSBwZXJuYW1idWNv",
        "Zm9saGEgZGUgcGVybmFtYnVjbw==",
        "am9ybmFsIGltcHJlbnNhIGRvIGFncmVzdGU=",
        "ZGlhcmlvIGRhIGJvcmJvcmVtYQ==",
        "ZGnDoXJpbyBkYSBib3Jib3JlbWE=",
        "am9ybmFsIGRhIHBhcmFpYmE=",
        "am9ybmFsIGRhIHBhcmHDrWJh",
        "dmFsZSBwYXJhaWJhbm8=",
        "Y29ycmVpbyBkYSBwYXJhaWJh",
        "Y29ycmVpbyBkYSBwYXJhw61iYQ==",
        "dHJpYnVuYSBkbyBub3J0ZQ==",
        "Z2F6ZXRhIGRlIG1hY2F1",
        "ZGlhcmlvIGRlIG5hdGFs",
        "ZGnDoXJpbyBkZSBuYXRhbA==",
        "YXJhY2F0aSBvbmxpbmU=",
        "ZGlhcmlvIGRlIHNvcm9jYWJh",
        "ZGnDoXJpbyBkZSBzb3JvY2FiYQ==",
        "ZGlhcmlvIGRvIGdyYW5kZSBhYmM=",
        "ZGnDoXJpbyBkbyBncmFuZGUgYWJj",
        "bm90aWNpYXMgcG9wdWxhcmVz",
        "bm90w61jaWFzIHBvcHVsYXJlcw==",
        "Zm9saGEgdW5pdmVyc2Fs",
        "ZGlhcmlvIG9maWNpYWwgZG8gZXN0YWRvIGRlIHNhbyBwYXVsbw==",
        "ZGnDoXJpbyBvZmljaWFsIGRvIGVzdGFkbyBkZSBzw6NvIHBhdWxv",
        "Z2F6ZXRhIGRlIHByYWlhIGdyYW5kZQ==",
        "YWdvcmEgc2FvIHBhdWxv",
        "YWdvcmEgc8OjbyBwYXVsbw==",
        "am9ybmFsIGRlIHNhbnRhIGNhdGFyaW5h",
        "ZGlhcmlvIGNhdGFyaW5lbnNl",
        "ZGnDoXJpbyBjYXRhcmluZW5zZQ==",
        "dHJpYnVuYSBjYXRhcmluZW5zZQ==",
        "Zm9saGEgZGUgbG9uZHJpbmE=",
        "dHJpYnVuYSBkbyBwYXJhbmE=",
        "dHJpYnVuYSBkbyBwYXJhbsOh",
        "byBlc3RhZG8gZG8gcGFyYW5h",
        "byBlc3RhZG8gZG8gcGFyYW7DoQ==",
        "Z2F6ZXRhIGRvIHBhcmFuYQ==",
        "Z2F6ZXRhIGRvIHBhcmFuw6E=",
        "am9ybmFsIGRlIGxvbmRyaW5h",
        "Z2F6ZXRhIGRvIGlndWFjdQ==",
        "Z2F6ZXRhIGRvIGlndWHDp3U=",
        "Y29ycmVpbyBkYSBiYWhpYQ==",
        "dHJpYnVuYSBkYSBiYWhpYQ==",
        "am9ybmFsIGdyYXBpdW5h",
        "am9ybmFsIGdyYXBpw7puYQ==",
        "Z2F6ZXRhIGRlIHNlcmdpcGU=",
        "Z2F6ZXRhIGRlIGFsYWdvYXM=",
        "am9ybmFsIGRlIGFsYWdvYXM=",
        "dHJpYnVuYSBkZSBhbGFnb2Fz",
        "ZGlhcmlvIGRhIGFtYXpvbmlh",
        "ZGnDoXJpbyBkYSBhbWF6w7RuaWE=",
        "am9ybmFsIG1laW8gbm9ydGU=",
        "byBlc3RhZG8gZG8gbWFyYW5oYW8=",
        "byBlc3RhZG8gZG8gbWFyYW5ow6Nv",
    ]
    title_lower = meta.title.lower()
    for encoded in np_names:
        with contextlib.suppress(Exception):
            decoded = base64.b64decode(encoded).decode("utf-8")
            if decoded in title_lower:
                meta.newspaper = True
                break


async def get_audiobook_duration(filelist: list[str]) -> tuple[float, str]:
    """Calculate the sum of durations of all audio files in the file list using MediaInfo."""
    from src.mediainfo import MediaInfo

    audio_files = [f for f in filelist if Path(f).suffix.lower() in AUDIOBOOK_EXTENSIONS]

    if not audio_files:
        return 0.0, ""

    def _get_file_duration(file_path: str) -> float:
        with contextlib.suppress(Exception):
            if not Path(file_path).is_file():
                return 0.0
            media_info = MediaInfo.parse(file_path)
            for track in media_info.tracks:
                if track.track_type == "General":
                    duration_ms = track.duration
                    if duration_ms is not None:
                        return float(duration_ms) / 1000.0
        return 0.0

    tasks = [asyncio.to_thread(_get_file_duration, f) for f in audio_files]
    durations = await asyncio.gather(*tasks)
    total_seconds = float(sum(durations))

    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    seconds = int(total_seconds % 60)

    # Format as HH:MM:SS if hours > 0, otherwise MM:SS
    duration_formatted = f"{hours:02d}h {minutes:02d}m {seconds:02d}s" if hours > 0 else f"{minutes:02d}m {seconds:02d}s"

    return total_seconds, duration_formatted


async def get_audiobook_bitrate(filelist: list[str]) -> int | None:
    """Calculate the average bitrate (in kbps) of a sample of audio files (max 5) in the file list using MediaInfo."""
    from src.mediainfo import MediaInfo

    audio_files = [f for f in filelist if Path(f).suffix.lower() in AUDIOBOOK_EXTENSIONS]

    # Limit to a maximum of 5 files to optimize performance
    audio_files = audio_files[:5]

    if not audio_files:
        return None

    def _get_file_bitrate(file_path: str) -> int | None:
        with contextlib.suppress(Exception):
            if not Path(file_path).is_file():
                return None
            media_info = MediaInfo.parse(file_path)
            for track in media_info.tracks:
                if track.track_type == "Audio":
                    track_data = track.to_data()
                    br = track_data.get("bit_rate") or track_data.get("BitRate")
                    if br is not None:
                        match = re.search(r"\d+", str(br))
                        if match:
                            return int(match.group(0))
            # Fallback to General track
            for track in media_info.tracks:
                if track.track_type == "General":
                    track_data = track.to_data()
                    br = track_data.get("overall_bit_rate") or track_data.get("OverallBitRate")
                    if br is not None:
                        match = re.search(r"\d+", str(br))
                        if match:
                            return int(match.group(0))
        return None

    tasks = [asyncio.to_thread(_get_file_bitrate, f) for f in audio_files]
    bitrates = await asyncio.gather(*tasks)

    valid_bitrates = [br for br in bitrates if br is not None]
    if not valid_bitrates:
        return None

    avg_bps = sum(valid_bitrates) / len(valid_bitrates)
    return round(avg_bps / 1000) if avg_bps >= 1000 else round(avg_bps)


def sanitize_book_author(meta: Meta) -> None:
    """Validate and sanitize author in meta by detecting and removing translators."""
    author = meta.author
    if not author:
        # Check if book_author is present and copy it if needed
        book_author = meta.book_author
        if book_author:
            author = book_author
        else:
            meta.author = ""
            return

    author = author
    has_underscores = "_" in author and " " not in author
    normalized_author = author.replace("_", " ") if has_underscores else author

    manual_translator = meta.book_translator
    if manual_translator:
        # Also replace underscores in manual translator names in case they entered underscores
        manual_translator_str = manual_translator
        names_to_remove = [n.replace("_", " ").strip() for n in manual_translator_str.split(",") if n.strip()]
        for name in names_to_remove:
            pattern = r"\b" + re.escape(name) + r"\b"
            normalized_author = re.sub(pattern, "", normalized_author, flags=re.IGNORECASE)

        # Clean up delimiters and extra whitespace left behind
        normalized_author = re.sub(r"\s*[,;/&]+\s*$", "", normalized_author)
        normalized_author = re.sub(r"^\s*[,;/&]+\s*", "", normalized_author)
        normalized_author = re.sub(r"\b(?:and|e)\b\s*$", "", normalized_author, flags=re.IGNORECASE)
        normalized_author = re.sub(r"^\s*\b(?:and|e)\b\s*", "", normalized_author, flags=re.IGNORECASE)
        normalized_author = re.sub(r"\s*-\s*$", "", normalized_author)
        normalized_author = re.sub(r"^\s*-\s*", "", normalized_author)
        normalized_author = re.sub(r"\s+", " ", normalized_author).strip()
        normalized_author = re.sub(r"\(\s*\)|\[\s*\]", "", normalized_author).strip()

    if has_underscores:
        normalized_author = normalized_author.replace(" ", "_")

    cleaned_author, translator = clean_translator_from_author(normalized_author)
    meta.author = extract_first_author(cleaned_author)
    if translator and not meta.book_translator:
        meta.book_translator = translator


def extract_first_author(author: str) -> str:
    """Extract only the first author from a potentially multi-author string."""
    if not author:
        return ""

    # Check if underscores format is used (e.g. Rosa_Montero_Jane_Doe)
    has_underscores = "_" in author and " " not in author
    normalized = author.replace("_", " ") if has_underscores else author

    # Split by common delimiters: comma, semicolon, ampersand, slash, plus, and, e, y, with, and space-hyphen-space
    split_pattern = r"\s*(?:,|;|&|/|\+|\band\b|\be\b|\by\b|\bwith\b|\s+-\s+)\s*"
    parts = re.split(split_pattern, normalized, flags=re.IGNORECASE)

    first_author = parts[0].strip() if parts else ""

    if has_underscores:
        first_author = first_author.replace(" ", "_")

    return first_author


def clean_translator_from_author(author: str) -> tuple[str, str]:
    """Detect if a name is a translator, remove it from the author field and return both."""
    if not author:
        return author, ""

    # If it contains underscores and no spaces, e.g. "Rosa_Montero_Mariana_Sanchez_tradutor"
    # we normalize underscores to spaces for processing.
    has_underscores = "_" in author and " " not in author
    normalized = author.replace("_", " ") if has_underscores else author

    # Translator keywords (case-insensitive)
    keywords = [
        r"tradutor\w*",  # tradutor, tradutora, tradutores, tradutoras
        r"translator\w*",  # translator, translators
        r"traduzido\b",  # traduzido, traduzida
        r"trad\b\.?",  # trad, trad.
        r"trans\b\.?",  # trans, trans.
        r"tradu[cç]ao\b",  # tradução, traducao
        r"translated\b",  # translated
    ]
    pattern_keywords = "(?:" + "|".join(keywords) + ")"

    # Pattern 1: [Name] followed by translator keyword (e.g. "Mariana Sanchez (tradutor)" or "Mariana Sanchez - tradutor")
    # Limit to matching at most 2 capitalized words to prevent greedily matching the author name if no delimiter is present.
    pattern1 = (
        r"\b([A-Z][A-Za-zÀ-ÿ]+(?:\s+(?:de|da|do|dos|das|e))\s+[A-Z][A-Za-zÀ-ÿ]+|"  # 2 words with particle
        r"[A-Z][A-Za-zÀ-ÿ]+(?:\s+[A-Z][A-Za-zÀ-ÿ]+)?)"  # 1 or 2 capitalized words
        r"\s*(?:\(|\[|-|\s_)*" + pattern_keywords + r"\)?\]?(?!\s+[A-ZÀ-ÿ])"
    )

    # Pattern 2: Translator keyword followed by [Name] (e.g. "translated by John Doe" or "traduzido por John Doe")
    pattern2 = (
        r"\b(?:translated\s+by|traduzido\s+por|tradutor\w*|translator\w*|tradu[cç]ao)\s*:?\s*"
        r"([A-Z][A-Za-zÀ-ÿ]+(?:\s+[A-Z][A-Za-zÀ-ÿ]+)*)"
    )

    translators = [match.group(1).strip() for match in re.finditer(pattern1, normalized, flags=re.IGNORECASE)]

    # Find all matches for pattern2 to extract translator name(s)
    translators.extend(match.group(1).strip() for match in re.finditer(pattern2, normalized, flags=re.IGNORECASE))

    # Apply pattern 1
    normalized, count1 = re.subn(pattern1, "", normalized, flags=re.IGNORECASE)

    # Apply pattern 2
    normalized, count2 = re.subn(pattern2, "", normalized, flags=re.IGNORECASE)

    # If neither pattern matched but a bare keyword is present, fallback to word-based stripping
    if count1 == 0 and count2 == 0:
        match = re.search(r"\b" + pattern_keywords + r"\b", normalized, re.IGNORECASE)
        if match:
            before_keyword = normalized[: match.start()].strip()
            before_keyword = before_keyword.rstrip(" _-,;([/")
            words = before_keyword.split()
            if len(words) >= 2:
                translators.append(" ".join(words[-2:]))
                normalized = " ".join(words[:-2])
            elif len(words) == 1:
                translators.append(words[0])
                normalized = ""
            else:
                normalized = ""

    # Clean up delimiters and extra whitespace left behind (anchored to start/end of the string)
    normalized = re.sub(r"\s*[,;/&]+\s*$", "", normalized)
    normalized = re.sub(r"^\s*[,;/&]+\s*", "", normalized)
    normalized = re.sub(r"\b(?:and|e)\b\s*$", "", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"^\s*\b(?:and|e)\b\s*", "", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\s*-\s*$", "", normalized)
    normalized = re.sub(r"^\s*-\s*", "", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()

    # Remove any empty brackets/parentheses left behind
    normalized = re.sub(r"\(\s*\)|\[\s*\]", "", normalized).strip()

    if has_underscores:
        normalized = normalized.replace(" ", "_")

    # Format the translator list as a comma-separated string
    unique_translators = []
    for t in translators:
        t_clean = t.strip()
        t_clean = re.sub(r"\s*[,;/&]+\s*$", "", t_clean)
        t_clean = re.sub(r"^\s*[,;/&]+\s*", "", t_clean)
        t_clean = re.sub(r"\b(?:and|e)\b\s*$", "", t_clean, flags=re.IGNORECASE)
        t_clean = re.sub(r"^\s*\b(?:and|e)\b\s*", "", t_clean, flags=re.IGNORECASE)
        t_clean = re.sub(r"\s*-\s*$", "", t_clean)
        t_clean = re.sub(r"^\s*-\s*", "", t_clean)
        t_clean = re.sub(r"\s+", " ", t_clean).strip()
        t_clean = re.sub(r"\(\s*\)|\[\s*\]", "", t_clean).strip()

        if t_clean and t_clean not in unique_translators:
            unique_translators.append(t_clean)

    translator_name = ", ".join(unique_translators)

    return normalized, translator_name
