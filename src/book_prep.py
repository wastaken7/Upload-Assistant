# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
"""Book and Audiobook preparation helpers.

This module contains the logic that was previously inlined inside the
``Prep`` class in ``prep.py``.  It is intentionally kept free of any
``Prep``-specific imports so it can be tested and extended in isolation.
"""
from __future__ import annotations

import asyncio
import base64
import os
import re
import sys
from typing import Any, Optional

import langcodes

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
from src.console import console
from src.exportmi import exportInfo

# ---------------------------------------------------------------------------
# File-list resolution
# ---------------------------------------------------------------------------

def resolve_book_filelist(
    meta: dict[str, Any],
    videoloc: str,
) -> tuple[str, list[str], str, str]:
    """Scan *videoloc* for book/audiobook files and update *meta* in-place.

    Populates ``meta["filelist"]``, ``meta["scene"]``, ``meta["imdb_id"]``,
    and ``meta["audiobook"]``.

    Returns:
        A 4-tuple ``(videopath, filelist, search_term, search_file_folder)``
        where *videopath* is the primary/largest file used as the "video"
        reference for downstream processing.
    """
    book_extensions: set[str] = {".pdf", ".epub", ".mobi", ".cbz", ".cbr"}
    audiobook_extensions: set[str] = {".mp3", ".m4b", ".flac", ".aac", ".m4a", ".ogg", ".wav"}
    allowed_extensions = book_extensions | audiobook_extensions

    filelist: list[str] = []
    if os.path.isdir(videoloc):
        for root, _, files in os.walk(videoloc):
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext in allowed_extensions:
                    filelist.append(os.path.abspath(os.path.join(root, file)))
        filelist = sorted(filelist)
        if not filelist:
            console.print("[bold red]No Book or Audiobook files found!")
            sys.exit(1)
        videopath = sorted(filelist, key=os.path.getsize, reverse=True)[0]
    else:
        videopath = videoloc
        filelist.append(videoloc)

    meta["filelist"] = filelist
    meta["imdb_id"] = 0

    primary_ext = os.path.splitext(videopath)[1].lower()
    meta["audiobook"] = primary_ext in audiobook_extensions

    search_term = os.path.basename(filelist[0]) if filelist else ""
    search_file_folder = "file"
    return videopath, filelist, search_term, search_file_folder


# ---------------------------------------------------------------------------
# Language resolution helper
# ---------------------------------------------------------------------------

def _resolve_book_language(raw: str) -> tuple[str, str]:
    """Return ``(full_english_name, iso_639_3_alpha3)`` for any language input."""
    raw = raw.strip()
    try:
        lc = langcodes.get(raw.lower())
        full_name = lc.display_name("en") or raw.title()
        alpha3 = lc.to_alpha3() or ""
        if full_name and full_name.lower() != raw.lower():
            return full_name, alpha3
    except Exception:
        pass
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


def sanitize_book_language(meta: dict[str, Any]) -> None:
    """Validate and sanitize book_language and book_language_iso in meta. Clear them if invalid."""
    lang = meta.get("book_language")
    if not lang:
        meta["book_language"] = ""
        meta["book_language_iso"] = ""
        return

    full, iso = _resolve_book_language(str(lang).strip())
    if is_valid_book_language(full, iso):
        meta["book_language"] = full
        meta["book_language_iso"] = iso
    else:
        meta["book_language"] = ""
        meta["book_language_iso"] = ""


# ---------------------------------------------------------------------------
# MediaInfo metadata extraction
# ---------------------------------------------------------------------------


async def gather_book_prep(
    meta: dict[str, Any],
    videopath: str,
    base_dir: str,
    config: Optional[dict[str, Any]] = None,
) -> None:
    """Set up BOOK/Audiobook category fields and extract embedded MediaInfo metadata.

    Sets ``meta["category"]``, ``meta["resolution"]``, ``meta["search_year"]``,
    ``meta["hfr"]``, ``meta["sd"]``, and ``meta["mediainfo"]``, then attempts
    to populate title, author, narrator, publisher, ISBN, overview, year,
    keywords, and language from the file's embedded tags.
    """
    meta["category"] = "BOOK"
    meta["search_year"] = ""
    meta["resolution"] = "Other"
    meta["hfr"] = False
    meta["sd"] = 0
    meta["valid_mi_settings"] = True

    # Warn if Google Books API key is missing
    api_key = ""
    if config and "DEFAULT" in config:
        api_key = config["DEFAULT"].get("google_books_api_key", "").strip()
    if not api_key:
        console.print("[bold red]Warning: Google Books API key is not configured. Book metadata searches will be limited and incomplete.[/bold red]")

    # Check if the file format is CBR or CBZ and automatically set comic to True
    file_ext = os.path.splitext(videopath)[1].lstrip(".").upper()
    if file_ext in ("CBR", "CBZ"):
        meta["comic"] = True

    # Identify CLI overrides at the very start
    cli_overrides = {
        "title": bool(meta.get("book_title")),
        "author": bool(meta.get("book_author")),
        "publisher": bool(meta.get("book_publisher")),
        "isbn": bool(meta.get("book_isbn")),
        "book_language": bool(meta.get("book_language")),
        "year": "manual_year" in meta and int(meta.get("manual_year") or 0) > 0,
        "keywords": bool(meta.get("keywords")),
    }

    # Extract EPUB metadata directly if the file is an EPUB
    if videopath.lower().endswith(".epub") and os.path.isfile(videopath):  # noqa: ASYNC240
        epub_meta = _extract_epub_metadata(videopath, debug=meta.get("debug", False))
        if epub_meta:
            if meta.get("debug", False):
                console.print(f"[cyan]EPUB metadata extracted: {epub_meta}[/cyan]")
            for key, val in epub_meta.items():
                if key == "book_language_raw":
                    full, iso3 = _resolve_book_language(val)
                    if is_valid_book_language(full, iso3) and not meta.get("book_language"):
                        meta["book_language"] = full
                        meta["book_language_iso"] = iso3
                else:
                    if not meta.get(key) and val:
                        meta[key] = val
                        if key == "year":
                            meta["search_year"] = int(val)

    # Extract CBR/CBZ metadata directly if the file is a CBR/CBZ
    if videopath.lower().endswith((".cbr", ".cbz")) and os.path.isfile(videopath):  # noqa: ASYNC240
        cbr_cbz_meta = _extract_cbr_cbz_metadata(videopath, debug=meta.get("debug", False))
        if cbr_cbz_meta:
            if meta.get("debug", False):
                console.print(f"[cyan]CBR/CBZ metadata extracted: {cbr_cbz_meta}[/cyan]")
            for key, val in cbr_cbz_meta.items():
                if key == "book_language_raw":
                    full, iso3 = _resolve_book_language(val)
                    if is_valid_book_language(full, iso3) and not meta.get("book_language"):
                        meta["book_language"] = full
                        meta["book_language_iso"] = iso3
                else:
                    if not meta.get(key) and val:
                        meta[key] = val
                        if key == "year":
                            meta["search_year"] = int(val)

    # Extract MOBI metadata directly if the file is a MOBI
    if videopath.lower().endswith(".mobi") and os.path.isfile(videopath):  # noqa: ASYNC240
        mobi_meta = _extract_mobi_metadata(videopath, debug=meta.get("debug", False))
        if mobi_meta:
            if meta.get("debug", False):
                console.print(f"[cyan]MOBI metadata extracted: {mobi_meta}[/cyan]")
            for key, val in mobi_meta.items():
                if key == "book_language_raw":
                    full, iso3 = _resolve_book_language(val)
                    if is_valid_book_language(full, iso3) and not meta.get("book_language"):
                        meta["book_language"] = full
                        meta["book_language_iso"] = iso3
                else:
                    if not meta.get(key) and val:
                        meta[key] = val
                        if key == "year":
                            meta["search_year"] = int(val)

    # Extract ISBN from PDF directly if the file is a PDF
    if videopath.lower().endswith(".pdf") and os.path.isfile(videopath):  # noqa: ASYNC240
        pdf_isbn = _extract_isbn_from_pdf(videopath, debug=meta.get("debug", False))
        if pdf_isbn and not meta.get("isbn"):
            meta["isbn"] = pdf_isbn
            if meta.get("debug", False):
                console.print(f"[cyan]PDF ISBN extracted: {pdf_isbn}[/cyan]")

    if not meta.get("edit", False):
        try:
            mi = await exportInfo(
                videopath,
                meta["isdir"],
                meta["uuid"],
                base_dir,
                is_dvd=meta.get("is_disc", False),
                debug=meta.get("debug", False),
            )
            meta["mediainfo"] = mi
        except Exception as e:
            if meta.get("debug", False):
                console.print(f"[yellow]Warning: MediaInfo export failed for book: {e}[/yellow]")
            meta["mediainfo"] = {}
    else:
        pass  # meta["mediainfo"] already populated from a previous run

    # Parse MediaInfo metadata as local fallback first
    if meta.get("mediainfo"):
        try:
            tracks = meta["mediainfo"].get("media", {}).get("track", [])
            general_track = next((t for t in tracks if t.get("@type") == "General"), None)
            if general_track:
                # 1. Title/Album
                album = general_track.get("Album") or general_track.get("album")
                track_name = general_track.get("Track_name") or general_track.get("track_name")
                if not meta.get("title"):
                    if album and str(album).strip() and not isinstance(album, dict):
                        meta["title"] = str(album).strip()
                    elif track_name and str(track_name).strip() and not isinstance(track_name, dict):
                        meta["title"] = str(track_name).strip()

                # 2. Author
                performer = general_track.get("Performer") or general_track.get("performer")
                album_performer = general_track.get("Album_Performer") or general_track.get("album_performer")
                if not meta.get("author"):
                    if performer and str(performer).strip() and not isinstance(performer, dict):
                        meta["author"] = str(performer).strip()
                    elif album_performer and str(album_performer).strip() and not isinstance(album_performer, dict):
                        meta["author"] = str(album_performer).strip()

                # 3. Narrator
                composer = general_track.get("Composer") or general_track.get("composer")
                if composer and str(composer).strip() and not isinstance(composer, dict) and not meta.get("narrator"):
                    meta["narrator"] = str(composer).strip()

                # 4. Publisher
                publisher = general_track.get("Publisher") or general_track.get("publisher")
                if publisher and str(publisher).strip() and not isinstance(publisher, dict) and not meta.get("publisher"):
                    meta["publisher"] = str(publisher).strip()

                # 5. ISBN
                isbn_val = general_track.get("ISBN") or general_track.get("isbn")
                if isbn_val and str(isbn_val).strip() and not isinstance(isbn_val, dict) and not meta.get("isbn"):
                    meta["isbn"] = str(isbn_val).strip()

                # 6. Overview/Comment
                comment = general_track.get("Comment") or general_track.get("comment")
                description = general_track.get("Description") or general_track.get("description")
                if not meta.get("overview"):
                    if comment and str(comment).strip() and not isinstance(comment, dict):
                        meta["overview"] = str(comment).strip()
                    elif description and str(description).strip() and not isinstance(description, dict):
                        meta["overview"] = str(description).strip()

                # 7. Year (extract 4-digit number)
                rec_date = general_track.get("Recorded_Date") or general_track.get("recorded_date")
                if rec_date and str(rec_date).strip() and not isinstance(rec_date, dict) and not meta.get("year"):
                    match = re.search(r"\b\d{4}\b", str(rec_date))
                    if match:
                        meta["year"] = match.group(0)
                        meta["search_year"] = int(match.group(0))

                # 8. Genre -> Keywords
                genre = general_track.get("Genre") or general_track.get("genre")
                if genre and str(genre).strip() and not isinstance(genre, dict):
                    words = re.split(r"[;,]", str(genre))
                    cleaned_words = [w.strip().lower() for w in words if w.strip()]
                    if cleaned_words:
                        existing_keywords = meta.get("keywords")
                        existing_list: list[str] = []
                        if existing_keywords:
                            if isinstance(existing_keywords, list):
                                for ek in existing_keywords:
                                    existing_list.extend([x.strip().lower() for x in ek.split(",") if x.strip()])
                            elif isinstance(existing_keywords, str):
                                existing_list.extend([x.strip().lower() for x in existing_keywords.split(",") if x.strip()])
                        for cw in cleaned_words:
                            if cw not in existing_list:
                                existing_list.append(cw)
                        meta["keywords"] = ", ".join(existing_list)

                # 9. Language
                if not meta.get("book_language"):
                    lang_val = general_track.get("Language") or general_track.get("language")
                    if lang_val and str(lang_val).strip() and not isinstance(lang_val, dict):
                        full, iso3 = _resolve_book_language(str(lang_val).strip())
                        if is_valid_book_language(full, iso3):
                            meta["book_language"] = full
                            meta["book_language_iso"] = iso3

                if not meta.get("book_language"):
                    # Fallback: Audio track language (audiobooks)
                    for t in tracks:
                        if t.get("@type") == "Audio":
                            lang_val = t.get("Language") or t.get("language")
                            if lang_val and str(lang_val).strip() and not isinstance(lang_val, dict):
                                full, iso3 = _resolve_book_language(str(lang_val).strip())
                                if is_valid_book_language(full, iso3):
                                    meta["book_language"] = full
                                    meta["book_language_iso"] = iso3
                                    break

                if not meta.get("book_language"):
                    # Fallback: Text track language (ebooks like PDF/EPUB)
                    for t in tracks:
                        if t.get("@type") == "Text":
                            lang_val = t.get("Language") or t.get("language")
                            if lang_val and str(lang_val).strip() and not isinstance(lang_val, dict):
                                full, iso3 = _resolve_book_language(str(lang_val).strip())
                                if is_valid_book_language(full, iso3):
                                    meta["book_language"] = full
                                    meta["book_language_iso"] = iso3
                                    break
        except Exception as ex:
            if meta.get("debug", False):
                console.print(f"[yellow]Warning: Error extracting embedded book metadata: {ex}[/yellow]")

    # MyAnonamouse API search using torrent client comments (online lookup takes precedence)
    if not meta.get("torrent_comments") and not meta.get("skip_auto_torrent", False) and not meta.get("edit", False) and config:
        from src.clients import Clients

        try:
            client = Clients(config=config)
            await client.get_pathed_torrents(meta.get("path", videopath), meta)
        except Exception as e:
            if meta.get("debug", False):
                console.print(f"[yellow]Warning: Could not search client for book torrent comments: {e}[/yellow]")

    mam_id = None
    if meta.get("torrent_comments"):
        for comment_data in meta.get("torrent_comments", []):
            trackers = str(comment_data.get("trackers", ""))
            comment = str(comment_data.get("comment", ""))

            is_mam = "myanonamouse.net" in trackers
            if not is_mam and comment_data.get("tracker_urls"):
                for tu in comment_data["tracker_urls"]:
                    if isinstance(tu, dict) and "myanonamouse.net" in str(tu.get("url", "")) or isinstance(tu, str) and "myanonamouse.net" in tu:
                        is_mam = True
                        break

            if is_mam:
                match = re.search(r"\bMID=(\d+)", comment)
                if match:
                    mam_id = match.group(1)
                    if meta.get("debug", False):
                        console.print(f"[cyan]Found MyAnonamouse ID {mam_id} in torrent comment[/cyan]")
                    break

    mam_data = None
    if mam_id:
        try:
            api_key = ""
            if config and "DEFAULT" in config:
                api_key = config["DEFAULT"].get("mam_api_key", "").strip() or config["DEFAULT"].get("mam_id", "").strip()
            api_key = api_key or os.environ.get("MAM_API_KEY", "").strip() or os.environ.get("MAM_ID", "").strip()

            from src.myanonamouse import myanonamouse_manager

            mam_data = await myanonamouse_manager.search_by_id(mam_id, base_dir=base_dir, api_key=api_key, debug=meta.get("debug", False))
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
                            or (key in ("book_language", "book_language_iso") and cli_overrides["book_language"])
                            or (key in ("year", "search_year") and cli_overrides["year"])
                            or (key == "keywords" and cli_overrides["keywords"])
                        ):
                            is_override = True

                        if not is_override:
                            meta[key] = val
                            if key == "year" and "search_year" not in mam_data:
                                meta["search_year"] = int(val)
        except Exception as ex:
            if meta.get("debug", False):
                console.print(f"[yellow]Warning: MyAnonamouse API lookup failed: {ex}[/yellow]")

    # Google Books API search using ISBN (online lookup takes precedence)
    google_books_data = None
    isbn = meta.get("isbn")
    if isbn:
        try:
            api_key = ""
            if config and "DEFAULT" in config:
                api_key = config["DEFAULT"].get("google_books_api_key", "").strip()
            from src.google_books import google_books_manager

            google_books_data = await google_books_manager.search_by_isbn(isbn, base_dir=base_dir, api_key=api_key, debug=meta.get("debug", False))
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
                            or (key in ("book_language", "book_language_iso") and cli_overrides["book_language"])
                            or (key in ("year", "search_year") and cli_overrides["year"])
                            or (key == "keywords" and cli_overrides["keywords"])
                        ):
                            is_override = True

                        # Do not overwrite fields already populated by MAM, except for the poster/cover image (prefer Google Books cover)
                        if key != "poster" and mam_data and (key in mam_data or key == "book_language_iso" and "book_language" in mam_data or key == "search_year" and "year" in mam_data):
                            is_override = True

                        if not is_override:
                            meta[key] = val
                            if key == "year" and "search_year" not in google_books_data:
                                meta["search_year"] = int(val)
        except Exception as ex:
            if meta.get("debug", False):
                console.print(f"[yellow]Warning: Google Books API lookup failed: {ex}[/yellow]")

    # OpenLibrary API search (online lookup takes precedence)
    openlibrary_data = None
    openlibrary_id = meta.get("openlibrary")
    if openlibrary_id:
        try:
            from src.openlibrary import openlibrary_manager

            openlibrary_data = await openlibrary_manager.search_by_work_id(openlibrary_id, base_dir=base_dir, debug=meta.get("debug", False))
        except Exception as ex:
            if meta.get("debug", False):
                console.print(f"[yellow]Warning: OpenLibrary API lookup by Work ID failed: {ex}[/yellow]")
    elif meta.get("isbn"):
        try:
            from src.openlibrary import openlibrary_manager

            openlibrary_data = await openlibrary_manager.search_by_isbn(meta["isbn"], base_dir=base_dir, debug=meta.get("debug", False))
        except Exception as ex:
            if meta.get("debug", False):
                console.print(f"[yellow]Warning: OpenLibrary API lookup by ISBN failed: {ex}[/yellow]")

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
                    or (key in ("book_language", "book_language_iso") and cli_overrides["book_language"])
                    or (key in ("year", "search_year") and cli_overrides["year"])
                    or (key == "keywords" and cli_overrides["keywords"])
                ):
                    is_override = True

                # Do not overwrite fields already populated by MAM
                if mam_data and (key in mam_data or key == "book_language_iso" and "book_language" in mam_data or key == "search_year" and "year" in mam_data):
                    is_override = True

                # Do not overwrite fields already populated by Google Books
                if google_books_data and (
                    key in google_books_data or key == "book_language_iso" and "book_language" in google_books_data or key == "search_year" and "year" in google_books_data
                ):
                    is_override = True

                if not is_override:
                    meta[key] = val
                    if key == "year" and "search_year" not in openlibrary_data:
                        meta["search_year"] = int(val)

    if meta.get("audiobook", False):
        filelist = meta.get("filelist", [])
        total_duration, duration_formatted = await get_audiobook_duration(filelist)
        meta["audiobook_duration"] = total_duration
        meta["audiobook_duration_formatted"] = duration_formatted

        avg_bitrate = await get_audiobook_bitrate(filelist)
        if avg_bitrate is not None:
            meta["audiobook_bitrate"] = avg_bitrate

    detect_newspaper(meta)
    sanitize_book_language(meta)


def detect_newspaper(meta: dict[str, Any]) -> None:
    np_names = [
        # Brazil
        "Zm9saGEgZGUgcy5wYXVsbw==", "Zm9saGEgZGUgcy4gcGF1bG8=", "Zm9saGEgZGUgc2FvIHBhdWxv", "Zm9saGEgZGUgc8OjbyBwYXVsbw==", "ZXN0YWRhbw==", "ZXN0YWTDo28=",
        "byBlc3RhZG8gZGUgcy4gcGF1bG8=", "byBlc3RhZG8gZGUgcy5wYXVsbw==", "byBlc3RhZG8gZGUgc8OjbyBwYXVsbw==", "byBnbG9ibw==", "dmFsb3IgZWNvbm9taWNv",
        "dmFsb3IgZWNvbsO0bWljbw==", "Y29ycmVpbyBicmF6aWxpZW5zZQ==", "Y29ycmVpbyBicmFzaWxpZW5zZQ==", "emVybyBob3Jh", "ZXN0YWRvIGRlIG1pbmFz",
        "ZGlhcmlvIGRvIG5vcmRlc3Rl", "ZGnDoXJpbyBkbyBub3JkZXN0ZQ==", "Z2F6ZXRhIGRvIHBvdm8=", "am9ybmFsIGRvIGJyYXNpbA==", "am9ybmFsIGRvIGNvbWVyY2lv",
        "am9ybmFsIGRvIGNvbW1lcmNpbw==", "YSB0cmlidW5hIGRhIGltcHJlbnNh", "Zm9saGEgZGlyaWdpZGE=", "YSB2b3ogZGEgc2VycmE=", "dHJpYnVuYSBkZSBwZXRyb3BvbGlz",
        "dHJpYnVuYSBkZSBwZXRyw7Nwb2xpcw==", "aW52ZXJ0YSAtIGpvcm5hbCBwcmEgdmVyZGFkZQ==", "am9ybmFsIGRlIGJyYXNpbGlh", "am9ybmFsIGRlIGJyYXPDrWxpYQ==",
        "YnJhc2lsIGVtIHRlbXBvIHJlYWw=", "Y29ycmVpbyBkbyBwb3Zv", "am9ybmFsIG5o", "am9ybmFsIHZz", "ZGlhcmlvIGRlIGNhbm9hcw==", "ZGnDoXJpbyBkZSBjYW5vYXM=",
        "am9ybmFsIGRvIHR1cmZl", "YnJhc2lsIGRlIGZhdG8=", "am9ybmFsIGdhemV0YSBkbyBvZXN0ZQ==", "cG9ydGFsIGRvIHRyaWFuZ3Vsbw==", "cG9ydGFsIGRvIHRyacOibmd1bG8=",
        "Z2F6ZXRhIG9ubGluZQ==", "ZGlhcmlvIGRlIGN1aWFiYQ==", "ZGnDoXJpbyBkZSBjdWlhYsOh", "YSBjcml0aWNhIGRlIGNhbXBvIGdyYW5kZQ==",
        "YSBjcsOtdGljYSBkZSBjYW1wbyBncmFuZGU=", "Y29ycmVpbyBkbyBlc3RhZG8=", "ZGlhcmlvIGRlIHBlcm5hbWJ1Y28=", "ZGnDoXJpbyBkZSBwZXJuYW1idWNv",
        "Zm9saGEgZGUgcGVybmFtYnVjbw==", "am9ybmFsIGltcHJlbnNhIGRvIGFncmVzdGU=", "ZGlhcmlvIGRhIGJvcmJvcmVtYQ==", "ZGnDoXJpbyBkYSBib3Jib3JlbWE=",
        "am9ybmFsIGRhIHBhcmFpYmE=", "am9ybmFsIGRhIHBhcmHDrWJh", "dmFsZSBwYXJhaWJhbm8=", "Y29ycmVpbyBkYSBwYXJhaWJh", "Y29ycmVpbyBkYSBwYXJhw61iYQ==",
        "dHJpYnVuYSBkbyBub3J0ZQ==", "Z2F6ZXRhIGRlIG1hY2F1", "ZGlhcmlvIGRlIG5hdGFs", "ZGnDoXJpbyBkZSBuYXRhbA==", "YXJhY2F0aSBvbmxpbmU=",
        "ZGlhcmlvIGRlIHNvcm9jYWJh", "ZGnDoXJpbyBkZSBzb3JvY2FiYQ==", "ZGlhcmlvIGRvIGdyYW5kZSBhYmM=", "ZGnDoXJpbyBkbyBncmFuZGUgYWJj", "bm90aWNpYXMgcG9wdWxhcmVz",
        "bm90w61jaWFzIHBvcHVsYXJlcw==", "Zm9saGEgdW5pdmVyc2Fs", "ZGlhcmlvIG9maWNpYWwgZG8gZXN0YWRvIGRlIHNhbyBwYXVsbw==",
        "ZGnDoXJpbyBvZmljaWFsIGRvIGVzdGFkbyBkZSBzw6NvIHBhdWxv", "Z2F6ZXRhIGRlIHByYWlhIGdyYW5kZQ==", "YWdvcmEgc2FvIHBhdWxv", "YWdvcmEgc8OjbyBwYXVsbw==",
        "am9ybmFsIGRlIHNhbnRhIGNhdGFyaW5h", "ZGlhcmlvIGNhdGFyaW5lbnNl", "ZGnDoXJpbyBjYXRhcmluZW5zZQ==", "dHJpYnVuYSBjYXRhcmluZW5zZQ==",
        "Zm9saGEgZGUgbG9uZHJpbmE=", "dHJpYnVuYSBkbyBwYXJhbmE=", "dHJpYnVuYSBkbyBwYXJhbsOh", "byBlc3RhZG8gZG8gcGFyYW5h", "byBlc3RhZG8gZG8gcGFyYW7DoQ==",
        "Z2F6ZXRhIGRvIHBhcmFuYQ==", "Z2F6ZXRhIGRvIHBhcmFuw6E=", "am9ybmFsIGRlIGxvbmRyaW5h", "Z2F6ZXRhIGRvIGlndWFjdQ==", "Z2F6ZXRhIGRvIGlndWHDp3U=",
        "Y29ycmVpbyBkYSBiYWhpYQ==", "dHJpYnVuYSBkYSBiYWhpYQ==", "am9ybmFsIGdyYXBpdW5h", "am9ybmFsIGdyYXBpw7puYQ==", "Z2F6ZXRhIGRlIHNlcmdpcGU=",
        "Z2F6ZXRhIGRlIGFsYWdvYXM=", "am9ybmFsIGRlIGFsYWdvYXM=", "dHJpYnVuYSBkZSBhbGFnb2Fz", "ZGlhcmlvIGRhIGFtYXpvbmlh", "ZGnDoXJpbyBkYSBhbWF6w7RuaWE=",
        "am9ybmFsIG1laW8gbm9ydGU=", "byBlc3RhZG8gZG8gbWFyYW5oYW8=", "byBlc3RhZG8gZG8gbWFyYW5ow6Nv",
    ]  # fmt: off
    title_lower = meta.get("title", "").lower()
    for encoded in np_names:
        try:
            decoded = base64.b64decode(encoded).decode("utf-8")
            if decoded in title_lower:
                meta["newspaper"] = True
                break
        except Exception:
            pass


async def get_audiobook_duration(filelist: list[str]) -> tuple[float, str]:
    """Calculate the sum of durations of all audio files in the file list using MediaInfo."""
    from pymediainfo import MediaInfo

    audiobook_extensions = (".mp3", ".m4b", ".flac", ".aac", ".m4a", ".ogg", ".wav")
    audio_files = [f for f in filelist if f.lower().endswith(audiobook_extensions)]

    if not audio_files:
        return 0.0, ""

    def _get_file_duration(file_path: str) -> float:
        try:
            if not os.path.isfile(file_path):
                return 0.0
            media_info = MediaInfo.parse(file_path)
            for track in media_info.tracks:
                if track.track_type == "General":
                    duration_ms = track.duration
                    if duration_ms is not None:
                        return float(duration_ms) / 1000.0
        except Exception:
            pass
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


async def get_audiobook_bitrate(filelist: list[str]) -> Optional[int]:
    """Calculate the average bitrate (in kbps) of a sample of audio files (max 5) in the file list using MediaInfo."""
    from pymediainfo import MediaInfo

    audiobook_extensions = (".mp3", ".m4b", ".flac", ".aac", ".m4a", ".ogg", ".wav")
    audio_files = [f for f in filelist if f.lower().endswith(audiobook_extensions)]

    # Limit to a maximum of 5 files to optimize performance
    audio_files = audio_files[:5]

    if not audio_files:
        return None

    def _get_file_bitrate(file_path: str) -> Optional[int]:
        try:
            if not os.path.isfile(file_path):
                return None
            media_info = MediaInfo.parse(file_path)
            for track in media_info.tracks:
                if track.track_type == "Audio":
                    track_data = track.to_data()
                    br = track_data.get("bit_rate") or track_data.get("BitRate")
                    if br is not None:
                        match = re.search(r'\d+', str(br))
                        if match:
                            return int(match.group(0))
            # Fallback to General track
            for track in media_info.tracks:
                if track.track_type == "General":
                    track_data = track.to_data()
                    br = track_data.get("overall_bit_rate") or track_data.get("OverallBitRate")
                    if br is not None:
                        match = re.search(r'\d+', str(br))
                        if match:
                            return int(match.group(0))
        except Exception:
            pass
        return None

    tasks = [asyncio.to_thread(_get_file_bitrate, f) for f in audio_files]
    bitrates = await asyncio.gather(*tasks)

    valid_bitrates = [br for br in bitrates if br is not None]
    if not valid_bitrates:
        return None

    avg_bps = sum(valid_bitrates) / len(valid_bitrates)
    avg_kbps = int(avg_bps / 1000) if avg_bps >= 1000 else int(avg_bps)
    return avg_kbps
