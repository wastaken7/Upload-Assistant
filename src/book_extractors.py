# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
"""Extractors for book and audiobook files metadata."""

from __future__ import annotations

import contextlib
import os
import re
import shutil
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any

from src.console import logger


def normalize_series_index(value: str) -> str:
    """Drop a trailing .0 from a series index ("5.0" -> "5"), keeping "5.5"/"0.5"."""
    try:
        idx = float(value)
    except TypeError, ValueError:
        return (value).strip()
    return str(int(idx)) if idx.is_integer() else str(idx)


def extract_epub_metadata(epub_path: str) -> dict[str, Any]:
    """Extract metadata from an EPUB zip container's OPF file."""
    metadata: dict[str, Any] = {}
    if not Path(epub_path).is_file() or not zipfile.is_zipfile(epub_path):
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
            series = ""
            series_index = ""

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
                elif tag_local == "meta":
                    meta_name = (elem.attrib.get("name") or "").lower()
                    if meta_name == "calibre:series":
                        series = (elem.attrib.get("content") or "").strip()
                    elif meta_name == "calibre:series_index":
                        series_index = (elem.attrib.get("content") or "").strip()

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
            if series:
                metadata["book_series"] = series
            if series_index:
                metadata["book_series_index"] = normalize_series_index(series_index)

    except Exception as e:
        logger.debug(f"[yellow]Warning: Error parsing EPUB metadata: {e}[/yellow]")

    return metadata


def extract_series_from_filename(filename: str) -> tuple[str, str]:
    """Parse (series, index) from a filename like "Author - Series #5 - Title", or ("", "")."""
    name = Path(filename).stem
    match = re.search(r"[-–]\s*([^-–#\[\]]+?)\s*#\s*(\d+(?:\.\d+)?)", name)  # noqa: RUF001
    if not match:
        return "", ""
    return match.group(1).strip(), normalize_series_index(match.group(2))


def extract_audiobook_series_from_title(title: str) -> tuple[str, str, str]:
    """Split unambiguous audiobook title/series formats."""
    value = title.strip()
    patterns = (
        r"^(?P<title>.+?)\s*:\s*Hist[oó]ria\s+(?P<index>\d+(?:\.\d+)?)\s+de\s+(?P<series>.+)$",
        r"^(?P<title>.+?)\s*:\s*(?P<series>.+?)[,]?\s*(?:livro|book)\s*(?P<index>\d+(?:\.\d+)?)\s*$",
        r"^(?P<title>.+?)\s*:\s*(?P<series>(?:saga|série|serie|trilogia|duologia|antologia|coleção|colecao|universo)\b.+?)\s+(?P<index>\d+(?:\.\d+)?)\s*$",
    )
    for pattern in patterns:
        match = re.match(pattern, value, re.IGNORECASE)
        if match:
            return (
                match.group("title").strip(),
                match.group("series").strip(),
                normalize_series_index(match.group("index")),
            )
    return value, "", ""


def extract_cbr_cbz_metadata(filepath: str) -> dict[str, Any]:
    """Extract metadata from a CBR (RAR) or CBZ (ZIP) container's ComicInfo.xml file."""
    metadata: dict[str, Any] = {}
    if not Path(filepath).is_file():
        return metadata

    ext = Path(filepath).suffix.lower()
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
            import rarfile

            has_rarfile = True
        except ImportError:
            logger.debug("[yellow]Debug: rarfile library not available for CBR metadata extraction.[/yellow]")
            has_rarfile = False

        if has_rarfile:
            try:
                with rarfile.RarFile(filepath, "r") as r:
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


def extract_mobi_metadata(mobi_path: str) -> dict[str, Any]:
    """Extract metadata from a MOBI file using the mobi library and parsing the extracted OPF."""
    metadata: dict[str, Any] = {}
    if not Path(mobi_path).is_file():
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
                    opf_path = Path(root) / file
                    break
            if opf_path:
                break

        if opf_path and Path(opf_path).is_file():
            with Path(opf_path).open("rb") as f:
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
        if tempdir and Path(tempdir).exists():
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


def extract_isbn_from_pdf(pdf_path: str) -> str | None:
    """Search for and extract a valid ISBN from a PDF file using PyMuPDF (fitz)."""
    try:
        import fitz
    except ImportError:
        logger.debug("[yellow]Debug: PyMuPDF (fitz) is not installed. Skipping PDF ISBN extraction.[/yellow]")
        return None

    if not Path(pdf_path).is_file():
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
                candidates = re.findall(r"\b(?:ISBN(?:-1[03])?:?\s*)?((?:97[89][- ]?)?\d(?:[- ]?\d){8,11}[- ]?[\dX])\b", text, re.IGNORECASE)
                for cand in candidates:
                    validated = validate_isbn_checksum(cand)
                    if validated:
                        logger.info(f"[cyan]Found valid ISBN {validated} on PDF page {page_num}[/cyan]")
                        return validated
    except Exception as e:
        logger.debug(f"[yellow]Warning: Error extracting ISBN from PDF: {e}[/yellow]")

    return None


def date_event_from_str(event_str: str | None) -> str | None:
    if not event_str:
        return "Epub"
    val = event_str.strip().lower()
    if val == "dcterms:available":
        return "Available"
    if val in ("dcterms:created", "publication"):
        return "Created"
    if val == "dcterms:date":
        return "Date"
    if val == "dcterms:dateaccepted":
        return "DateAccepted"
    if val == "dcterms:datecopyrighted":
        return "DateCopyrighted"
    if val == "dcterms:datesubmitted":
        return "DateSubmitted"
    if val in ("dcterms:issued", "original-publication"):
        return "Issued"
    if val == "dcterms:modified":
        return "Modified"
    if val == "dcterms:valid":
        return "Valid"
    return None


def get_attr_ignore_ns(elem: ET.Element, attr_name: str) -> str | None:
    if attr_name in elem.attrib:
        return elem.attrib[attr_name]
    for k, v in elem.attrib.items():
        if k.split("}")[-1] == attr_name:
            return v
    return None


def get_epubmeta_output(epub_path: str) -> str | None:
    """Extract format EPUB metadata to match the output of epubmeta."""
    if not Path(epub_path).is_file() or not zipfile.is_zipfile(epub_path):
        return None

    try:
        with zipfile.ZipFile(epub_path, "r") as z:
            rootfile_path = None
            try:
                container_data = z.read("META-INF/container.xml")
                root = ET.fromstring(container_data)
                for elem in root.iter():
                    if elem.tag.split("}")[-1] == "rootfile":
                        rootfile_path = elem.attrib.get("full-path")
                        if rootfile_path:
                            break
            except Exception as e:
                logger.error(f"[yellow]Warning: Error parsing EPUB metadata: {e}[/yellow]")

            if not rootfile_path:
                for name in z.namelist():
                    if name.endswith(".opf"):
                        rootfile_path = name
                        break

            if not rootfile_path or rootfile_path not in z.namelist():
                return None

            opf_data = z.read(rootfile_path)
            root = ET.fromstring(opf_data)

            # Get package tag attributes
            version = get_attr_ignore_ns(root, "version") or ""
            unique_id = get_attr_ignore_ns(root, "unique-identifier") or ""

            metadata_elem = None
            for elem in root.iter():
                if elem.tag.split("}")[-1] == "metadata":
                    metadata_elem = elem
                    break

            if metadata_elem is None:
                return None

            # Collect refinements
            refinements = []
            for child in metadata_elem:
                tag = child.tag.split("}")[-1]
                if tag == "meta":
                    refines = get_attr_ignore_ns(child, "refines")
                    if refines:
                        ref_id = refines.lstrip("#")
                        prop = get_attr_ignore_ns(child, "property") or ""
                        scheme = get_attr_ignore_ns(child, "scheme") or ""
                        text = (child.text or "").strip()
                        refinements.append({"refId": ref_id, "refProp": prop, "refScheme": scheme, "refText": text})

            def find_refinement(ref_id, prop):
                for r in refinements:
                    if r["refId"] == ref_id and r["refProp"] == prop:
                        return r
                return None

            identifiers = []
            titles = []
            languages = []
            contributors = []
            creators = []
            dates_map = {}
            sources = []
            m_type = None
            coverages = []
            descriptions = []
            formats = []
            publishers = []
            relations = []
            rights = []
            subjects = []

            for child in metadata_elem:
                tag = child.tag.split("}")[-1]
                text = (child.text or "").strip()

                if tag == "identifier":
                    id_val = get_attr_ignore_ns(child, "id")
                    scheme_val = get_attr_ignore_ns(child, "scheme")
                    id_type = None
                    if id_val:
                        ref = find_refinement(id_val, "identifier-type")
                        if ref:
                            id_type = ref["refText"]
                            if not scheme_val:
                                scheme_val = ref["refScheme"]
                    identifiers.append({"id": id_val, "identifier_type": id_type, "scheme": scheme_val, "text": text})

                elif tag == "title":
                    id_val = get_attr_ignore_ns(child, "id")
                    lang_val = get_attr_ignore_ns(child, "lang")
                    title_type = None
                    title_seq = None
                    if id_val:
                        ref_type = find_refinement(id_val, "title-type")
                        if ref_type:
                            title_type = ref_type["refText"]
                        ref_seq = find_refinement(id_val, "display-seq")
                        if ref_seq:
                            with contextlib.suppress(ValueError):
                                title_seq = int(ref_seq["refText"])
                    titles.append({"lang": lang_val, "title_type": title_type, "title_seq": title_seq, "text": text})

                elif tag == "language":
                    languages.append(text)

                elif tag in ("contributor", "creator"):
                    id_val = get_attr_ignore_ns(child, "id")
                    role_val = get_attr_ignore_ns(child, "role")
                    file_as_val = get_attr_ignore_ns(child, "file-as")
                    creator_seq = None

                    if id_val:
                        ref_role = find_refinement(id_val, "role")
                        if ref_role:
                            role_val = ref_role["refText"]
                        ref_file = find_refinement(id_val, "file-as")
                        if ref_file:
                            file_as_val = ref_file["refText"]
                        ref_seq = find_refinement(id_val, "display-seq")
                        if ref_seq:
                            with contextlib.suppress(ValueError):
                                creator_seq = int(ref_seq["refText"])

                    item = {"role": role_val, "file_as": file_as_val, "creator_seq": creator_seq, "text": text}
                    if tag == "creator":
                        creators.append(item)
                    else:
                        contributors.append(item)

                elif tag == "date":
                    event_val = get_attr_ignore_ns(child, "event")
                    event_name = date_event_from_str(event_val)
                    if event_name:
                        dates_map[event_name] = text

                elif tag == "meta":
                    refines = get_attr_ignore_ns(child, "refines")
                    if not refines:
                        prop = get_attr_ignore_ns(child, "property")
                        if prop and prop.startswith("dcterms:"):
                            event_name = date_event_from_str(prop)
                            if event_name:
                                dates_map[event_name] = text

                elif tag == "source":
                    id_val = get_attr_ignore_ns(child, "id")
                    id_type = None
                    scheme_val = None
                    source_of = None
                    if id_val:
                        ref_type = find_refinement(id_val, "identifier-type")
                        if ref_type:
                            id_type = ref_type["refText"]
                            scheme_val = ref_type["refScheme"] or None
                        ref_sof = find_refinement(id_val, "source-of")
                        if ref_sof:
                            source_of = ref_sof["refText"]
                    sources.append({"id_type": id_type, "scheme": scheme_val, "source_of": source_of, "text": text})

                elif tag == "type" and m_type is None:
                    m_type = text

                elif tag == "coverage":
                    coverages.append(text)

                elif tag == "description":
                    lang_val = get_attr_ignore_ns(child, "lang")
                    descriptions.append({"lang": lang_val, "text": text})

                elif tag == "format":
                    formats.append(text)

                elif tag == "publisher":
                    publishers.append(text)

                elif tag == "relation":
                    relations.append(text)

                elif tag == "rights":
                    rights.append(text)

                elif tag == "subject":
                    subjects.append(text)

            # Build formatted lines
            lines = []
            lines.append("package")
            lines.append(f"  version: {version}")
            lines.append(f"  unique-identifier: {unique_id}")

            def format_subline(key, val):
                if val is None or val == "":
                    return ""
                return f"  {key}: {val}"

            # 1. Identifiers
            for ident in identifiers:
                lines.append("identifier")
                if ident.get("id"):
                    lines.append(format_subline("id", ident["id"]))
                if ident.get("identifier_type"):
                    lines.append(format_subline("identifier-type", ident["identifier_type"]))
                if ident.get("scheme"):
                    lines.append(format_subline("scheme", ident["scheme"]))
                lines.append(format_subline("text", ident["text"]))

            # 2. Titles
            for title in titles:
                if title.get("lang") is None and title.get("title_type") is None and title.get("title_seq") is None:
                    lines.append(f"title: {title['text']}")
                else:
                    lines.append("title")
                    lines.append(format_subline("text", title["text"]))
                    if title.get("lang"):
                        lines.append(format_subline("lang", title["lang"]))
                    if title.get("title_type"):
                        lines.append(format_subline("title-type", title["title_type"]))
                    if title.get("title_seq") is not None:
                        lines.append(format_subline("display-seq", str(title["title_seq"])))

            # 3. Languages
            lines.extend(f"language: {lang}" for lang in languages)

            # 4. Contributors
            for contributor in contributors:
                if contributor.get("role") is None and contributor.get("file_as") is None and contributor.get("creator_seq") is None:
                    lines.append(f"contributor: {contributor['text']}")
                else:
                    lines.append("contributor")
                    lines.append(format_subline("text", contributor["text"]))
                    if contributor.get("file_as"):
                        lines.append(format_subline("file-as", contributor["file_as"]))
                    if contributor.get("role"):
                        lines.append(format_subline("role", contributor["role"]))
                    if contributor.get("creator_seq") is not None:
                        lines.append(format_subline("display-seq", str(contributor["creator_seq"])))

            # 5. Creators
            for creator in creators:
                if creator.get("role") is None and creator.get("file_as") is None and creator.get("creator_seq") is None:
                    lines.append(f"creator: {creator['text']}")
                else:
                    lines.append("creator")
                    lines.append(format_subline("text", creator["text"]))
                    if creator.get("file_as"):
                        lines.append(format_subline("file-as", creator["file_as"]))
                    if creator.get("role"):
                        lines.append(format_subline("role", creator["role"]))
                    if creator.get("creator_seq") is not None:
                        lines.append(format_subline("display-seq", str(creator["creator_seq"])))

            # 6. Dates
            date_event_order = ["Available", "Created", "Date", "DateAccepted", "DateCopyrighted", "DateSubmitted", "Epub", "Issued", "Modified", "Valid"]
            date_event_strings = {
                "Available": "available",
                "Created": "created",
                "Date": "date",
                "DateAccepted": "dateAccepted",
                "DateCopyrighted": "dateCopyrighted",
                "DateSubmitted": "dateSubmitted",
                "Epub": "EPUB created",
                "Issued": "issued",
                "Modified": "modified",
                "Valid": "valid",
            }
            for event_name in date_event_order:
                if event_name in dates_map:
                    lines.append("date")
                    lines.append(format_subline("event", date_event_strings[event_name]))
                    lines.append(format_subline("text", dates_map[event_name]))

            # 7. Sources
            for source in sources:
                if source.get("id_type") is None and source.get("scheme") is None and source.get("source_of") is None:
                    lines.append(f"source: {source['text']}")
                else:
                    lines.append("source")
                    lines.append(format_subline("text", source["text"]))
                    if source.get("id_type"):
                        lines.append(format_subline("identifier-type", source["id_type"]))
                    if source.get("scheme"):
                        lines.append(format_subline("scheme", source["scheme"]))
                    if source.get("source_of"):
                        lines.append(format_subline("source-of", source["source_of"]))

            # 8. Type
            if m_type:
                lines.append(f"type: {m_type}")

            # 9. Coverage
            lines.extend(f"coverage: {coverage}" for coverage in coverages)

            # 10. Descriptions
            for desc in descriptions:
                if desc.get("lang") is None:
                    lines.append(f"description: {desc['text']}")
                else:
                    lines.append("description")
                    if desc.get("lang"):
                        lines.append(format_subline("lang", desc["lang"]))
                    lines.append(format_subline("text", desc["text"]))

            # 11. Formats
            lines.extend(f"format: {fmt}" for fmt in formats)

            # 12. Publishers
            lines.extend(f"publisher: {pub}" for pub in publishers)

            # 13. Relations
            lines.extend(f"relation: {rel}" for rel in relations)

            # 14. Rights
            lines.extend(f"rights: {right}" for right in rights)

            # 15. Subjects
            lines.extend(f"subject: {subject}" for subject in subjects)

            return "\n".join(lines) + "\n"

    except Exception as e:
        logger.debug(f"[yellow]Warning: Error parsing EPUB for epubmeta output: {e}[/yellow]")
        return None
