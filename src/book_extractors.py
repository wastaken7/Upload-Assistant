# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
"""Extractors for book and audiobook files metadata."""
from __future__ import annotations

import contextlib
import os
import re
import shutil
import xml.etree.ElementTree as ET
import zipfile
from typing import Any

from src.console import logger


def extract_epub_metadata(epub_path: str, debug: bool = False) -> dict[str, Any]:
    """Extract metadata from an EPUB zip container's OPF file."""
    metadata: dict[str, Any] = {}
    if not os.path.isfile(epub_path) or not zipfile.is_zipfile(epub_path):
        return metadata

    try:
        with zipfile.ZipFile(epub_path, "r") as z:
            # 1. Read META-INF/container.xml to find the .opf file path
            rootfile_path: str | None = None
            try:
                container_data = z.read("META-INF/container.xml")
                root = ET.fromstring(container_data)
                for elem in root.iter():
                    if elem.tag.endswith("rootfile"):
                        rootfile_path = elem.attrib.get("full-path")
                        if rootfile_path:
                            break
            except Exception as e:
                logger.debug(f"[yellow]Debug: META-INF/container.xml not found or unreadable: {e}[/yellow]")

            # Fallback: search for any .opf file in the archive
            if not rootfile_path:
                for name in z.namelist():
                    if name.endswith(".opf"):
                        rootfile_path = name
                        break

            if not rootfile_path:
                logger.debug("[yellow]Debug: No OPF metadata file found in EPUB ZIP[/yellow]")
                return metadata

            # 2. Read and parse the .opf file
            opf_data = z.read(rootfile_path)
            root = ET.fromstring(opf_data)

            title = ""
            author = ""
            language = ""
            date = ""
            identifier = ""
            description = ""
            publisher = ""

            for elem in root.iter():
                tag_local = elem.tag.split("}")[-1]
                if tag_local == "title":
                    title = (elem.text or "").strip()
                elif tag_local == "creator":
                    author = (elem.text or "").strip()
                elif tag_local == "language":
                    language = (elem.text or "").strip()
                elif tag_local == "date":
                    date = (elem.text or "").strip()
                elif tag_local == "identifier":
                    val = (elem.text or "").strip()
                    if val.lower().startswith("urn:isbn:"):
                        identifier = val[9:]
                    elif val.lower().startswith("isbn:"):
                        identifier = val[5:]
                    elif not identifier:
                        identifier = val
                elif tag_local == "description":
                    description = (elem.text or "").strip()
                elif tag_local == "publisher":
                    publisher = (elem.text or "").strip()

            if title:
                metadata["title"] = title
            if author:
                metadata["author"] = author
            if language:
                metadata["book_language_raw"] = language
            if date and not date.startswith("0101-01-01"):  # ignore placeholder date
                match = re.search(r"\b\d{4}\b", date)
                if match:
                    metadata["year"] = match.group(0)
            if identifier:
                cleaned_id = re.sub(r"[^\d]", "", identifier)
                if len(cleaned_id) in (10, 13):
                    metadata["isbn"] = cleaned_id
            if description:
                metadata["overview"] = description
            if publisher:
                metadata["publisher"] = publisher

    except Exception as e:
        logger.debug(f"[yellow]Warning: Error parsing EPUB metadata: {e}[/yellow]")

    return metadata


def extract_cbr_cbz_metadata(filepath: str, debug: bool = False) -> dict[str, Any]:
    """Extract metadata from a CBR (RAR) or CBZ (ZIP) container's ComicInfo.xml file."""
    metadata: dict[str, Any] = {}
    if not os.path.isfile(filepath):
        return metadata

    ext = os.path.splitext(filepath)[1].lower()
    xml_data: bytes | None = None

    if ext == ".cbz" or zipfile.is_zipfile(filepath):
        try:
            with zipfile.ZipFile(filepath, "r") as z:
                # Find ComicInfo.xml (case-insensitive search)
                xml_name = next((name for name in z.namelist() if name.lower().endswith("comicinfo.xml")), None)
                if xml_name:
                    xml_data = z.read(xml_name)
        except Exception as e:
            logger.debug(f"[yellow]Debug: Error reading CBZ zip archive: {e}[/yellow]")
    elif ext == ".cbr":
        try:
            from rarfile import RarFile
        except ImportError:
            logger.debug("[yellow]Debug: rarfile library not available for CBR metadata extraction.[/yellow]")
            RarFile = None

        if RarFile:
            try:
                with RarFile(filepath, "r") as r:
                    xml_name = next((name for name in r.namelist() if name.lower().endswith("comicinfo.xml")), None)
                    if xml_name:
                        xml_data = r.read(xml_name)
            except Exception as e:
                logger.debug(f"[yellow]Debug: Error reading CBR rar archive: {e}[/yellow]")

    if not xml_data:
        return metadata

    try:
        root = ET.fromstring(xml_data)

        series = ""
        title = ""
        writer = ""
        penciller = ""
        publisher = ""
        year = ""
        language_iso = ""
        summary = ""
        genre = ""

        for elem in root.iter():
            tag_local = elem.tag.split("}")[-1]
            if tag_local == "Series":
                series = (elem.text or "").strip()
            elif tag_local == "Title":
                title = (elem.text or "").strip()
            elif tag_local == "Writer":
                writer = (elem.text or "").strip()
            elif tag_local == "Penciller":
                penciller = (elem.text or "").strip()
            elif tag_local == "Publisher":
                publisher = (elem.text or "").strip()
            elif tag_local == "Year":
                year = (elem.text or "").strip()
            elif tag_local == "LanguageISO":
                language_iso = (elem.text or "").strip()
            elif tag_local == "Summary":
                summary = (elem.text or "").strip()
            elif tag_local == "Genre":
                genre = (elem.text or "").strip()

        # Map to common metadata fields
        final_title = series or title
        if final_title:
            metadata["title"] = final_title

        final_author = writer or penciller
        if final_author:
            metadata["author"] = final_author

        if publisher:
            metadata["publisher"] = publisher

        if year:
            match = re.search(r"\b\d{4}\b", year)
            if match:
                metadata["year"] = match.group(0)

        if language_iso:
            metadata["book_language_raw"] = language_iso

        if summary:
            metadata["overview"] = summary

        if genre:
            genres_list = [g.strip() for g in genre.split(",") if g.strip()]
            metadata["keywords"] = metadata["genres"] = genres_list

    except Exception as e:
        logger.debug(f"[yellow]Warning: Error parsing ComicInfo.xml metadata: {e}[/yellow]")

    return metadata


def extract_mobi_metadata(mobi_path: str, debug: bool = False) -> dict[str, Any]:
    """Extract metadata from a MOBI file using the mobi library and parsing the extracted OPF."""
    metadata: dict[str, Any] = {}
    if not os.path.isfile(mobi_path):
        return metadata

    try:
        import mobi
    except ImportError:
        logger.debug("[yellow]Debug: mobi library is not installed. Skipping MOBI metadata extraction.[/yellow]")
        return metadata

    tempdir = None
    try:
        tempdir, _ = mobi.extract(mobi_path)

        # Search for any .opf file in the tempdir
        opf_path = None
        for root, _, files in os.walk(tempdir):
            for file in files:
                if file.endswith(".opf"):
                    opf_path = os.path.join(root, file)
                    break
            if opf_path:
                break

        if opf_path and os.path.isfile(opf_path):
            with open(opf_path, "rb") as f:
                opf_data = f.read()

            try:
                root = ET.fromstring(opf_data)
            except Exception:
                try:
                    decoded = opf_data.decode("utf-8", errors="replace")
                    root = ET.fromstring(decoded.encode("utf-8"))
                except Exception as e:
                    logger.debug(f"[yellow]Debug: Error parsing MOBI XML data: {e}[/yellow]")
                    root = None

            if root is not None:
                title = ""
                author = ""
                language = ""
                date = ""
                identifier = ""
                description = ""
                publisher = ""

                for elem in root.iter():
                    tag_local = elem.tag.split("}")[-1]
                    if tag_local == "title":
                        title = (elem.text or "").strip()
                    elif tag_local == "creator":
                        author = (elem.text or "").strip()
                    elif tag_local == "language":
                        language = (elem.text or "").strip()
                    elif tag_local == "date":
                        date = (elem.text or "").strip()
                    elif tag_local == "identifier":
                        val = (elem.text or "").strip()
                        if val.lower().startswith("urn:isbn:"):
                            identifier = val[9:]
                        elif val.lower().startswith("isbn:"):
                            identifier = val[5:]
                    elif tag_local == "description":
                        description = (elem.text or "").strip()
                    elif tag_local == "publisher":
                        publisher = (elem.text or "").strip()

                if title:
                    metadata["title"] = title
                if author:
                    metadata["author"] = author
                if language:
                    metadata["book_language_raw"] = language
                if date and not date.startswith("0101-01-01"):
                    match = re.search(r"\b\d{4}\b", date)
                    if match:
                        metadata["year"] = match.group(0)
                if identifier:
                    cleaned_id = re.sub(r"[^\d]", "", identifier)
                    if len(cleaned_id) in (10, 13):
                        metadata["isbn"] = cleaned_id
                if description:
                    import html

                    cleaned_description = re.sub(r"<[^>]+>", "", description)
                    cleaned_description = html.unescape(cleaned_description)
                    metadata["overview"] = cleaned_description.strip()
                if publisher:
                    metadata["publisher"] = publisher

    except Exception as e:
        logger.debug(f"[yellow]Warning: Error parsing MOBI metadata: {e}[/yellow]")
    finally:
        if tempdir and os.path.exists(tempdir):
            with contextlib.suppress(Exception):
                shutil.rmtree(tempdir)

    return metadata


def validate_isbn_checksum(candidate: str) -> str | None:
    """Validate and return cleaned ISBN-10 or ISBN-13 if valid, else None."""
    cleaned = re.sub(r"[- ]", "", candidate).upper()

    # Check ISBN-13
    if len(cleaned) == 13 and cleaned.isdigit():
        total = sum(int(cleaned[i]) * (1 if i % 2 == 0 else 3) for i in range(13))
        if total % 10 == 0:
            return cleaned

    # Check ISBN-10
    if len(cleaned) == 10 and cleaned[:9].isdigit() and (cleaned[9].isdigit() or cleaned[9] == "X"):
        total = sum((10 if cleaned[i] == "X" else int(cleaned[i])) * (10 - i) for i in range(10))
        if total % 11 == 0:
            return cleaned

    return None


def extract_isbn_from_pdf(pdf_path: str, debug: bool = False) -> str | None:
    """Search for and extract a valid ISBN from a PDF file using PyMuPDF (fitz)."""
    try:
        import fitz
    except ImportError:
        logger.debug("[yellow]Debug: PyMuPDF (fitz) is not installed. Skipping PDF ISBN extraction.[/yellow]")
        return None

    if not os.path.isfile(pdf_path):
        return None

    try:
        # Disable mupdf display errors to avoid spamming console
        with contextlib.suppress(Exception):
            fitz.TOOLS.mupdf_display_errors(False)

        with fitz.open(pdf_path) as doc:
            num_pages = len(doc)
            if num_pages == 0:
                return None

            # Determine page ranges: check first 30 and last 30 pages first
            front_limit = min(30, num_pages)
            back_limit = max(0, num_pages - 30)

            pages_to_check: list[int] = list(range(front_limit))
            # Last N pages (avoiding duplicates)
            for p in range(back_limit, num_pages):
                if p not in pages_to_check:
                    pages_to_check.append(p)
            # Middle pages as fallback
            for p in range(num_pages):
                if p not in pages_to_check:
                    pages_to_check.append(p)

            for page_num in pages_to_check:
                text = doc[page_num].get_text()
                if not isinstance(text, str) or not text:
                    continue

                # Find ISBN candidates
                candidates = re.findall(
                    r"\b(?:ISBN(?:-1[03])?:?\s*)?((?:97[89][- ]?)?\d(?:[- ]?\d){8,11}[- ]?[\dX])\b",
                    text,
                    re.IGNORECASE
                )
                for cand in candidates:
                    validated = validate_isbn_checksum(cand)
                    if validated:
                        logger.info(f"[cyan]Found valid ISBN {validated} on PDF page {page_num}[/cyan]")
                        return validated
    except Exception as e:
        logger.debug(f"[yellow]Warning: Error extracting ISBN from PDF: {e}[/yellow]")

    return None
