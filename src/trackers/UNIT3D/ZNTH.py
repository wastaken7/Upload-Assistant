from typing import Any

from src.console import logger
from src.meta import Meta
from src.trackers.COMMON import COMMON
from src.trackers.UNIT3D import UNIT3D, ParamsList

Config = dict[str, Any]


class ZNTH(UNIT3D):
    tracker = "ZNTH"
    base_url = "https://znth.cx"
    banned_groups: list[str] = []
    id_url = f"{base_url}/api/torrents/"
    upload_url = f"{base_url}/api/torrents/upload"
    requests_url = f"{base_url}/api/requests/filter"
    search_url = f"{base_url}/api/torrents/filter"
    torrent_url = f"{base_url}/torrents/"
    banned_url = f"{base_url}/api/bannedReleaseGroups"
    supported_categories = ("TV", "MOVIE", "BOOK", "GAME")
    tracker_urls = ['https://znth.cx']

    def __init__(self, config: Config) -> None:
        super().__init__(config, tracker_name="ZNTH")
        self.config = config
        self.common = COMMON(config)

    async def get_additional_checks(self, meta: Meta) -> bool:
        if meta.category == "BOOK":
            if not meta.isbn and not meta.asin:
                logger.info(f"{self.tracker}: [bold red]ISBN or ASIN is required for books. Skipping upload...[/bold red]")
                return False
            if meta.audiobook and not meta.narrator:
                logger.info(f"{self.tracker}: [bold red]Narrator is required for audiobooks. Skipping upload...[/bold red]")
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
            author = meta.author or "".strip()
            title = meta.title or meta.name or "".strip()
            year = str(meta.year) if meta.year is not None else ""
            format_val = (meta.type or meta.container or "").strip().upper()
            tag = meta.tag or "".strip().lstrip("-")

            # Determine source/retail
            source = meta.source or "".strip().upper()
            manual_source = (meta.manual_source or "").strip().upper()
            if manual_source in ("RETAIL", "SCAN", "HYBRID"):
                source = manual_source

            if source not in ("RETAIL", "SCAN", "HYBRID"):
                filename_lower = (meta.basename_no_ext + " " + meta.title).lower()
                if "scan" in filename_lower:
                    source = "SCAN"
                elif "hybrid" in filename_lower:
                    source = "HYBRiD"
                elif "retail" in filename_lower:
                    source = "RETAiL"
                else:
                    ext = format_val.upper()
                    source = "SCAN" if ext == "PDF" else "RETAiL"

            is_retail = source in ("RETAIL", "RETAiL") or "retail" in meta.basename_no_ext.lower()

            if audiobook:
                # AudioBook Naming
                # Required: Author - Name Year Format ISBN-Tag
                # Recommended: Author - Name Year Format Bitrate ISBN Retail-Tag
                lossy_formats = ["MP3", "AAC", "OPUS", "VORBIS", "M4B", "M4A", "OGG"]
                bitrate_val = ""
                if format_val in lossy_formats:
                    bitrate = meta.audiobook_bitrate
                    if bitrate:
                        bitrate_val = f"{bitrate}kbps"

                book_id = meta.isbn or meta.asin

                parts = []
                if author:
                    parts.append(author)
                if title:
                    if parts:
                        parts.append("-")
                    parts.append(title)
                if year:
                    parts.append(year)
                if format_val:
                    parts.append(format_val)
                if bitrate_val:
                    parts.append(bitrate_val)
                if book_id:
                    parts.append(book_id)
                if is_retail:
                    parts.append("Retail")

                base_name = " ".join(parts)
                base_name = " ".join(base_name.split())
                znth_name = f"{base_name}-{tag}" if tag else base_name

            else:
                # eBook Naming
                # Required: Author - Name Year Format ISBN
                # Additional: Author - Name Year Edition Format ISBN Retail Scan OCR
                edition = str(meta.manual_edition or meta.edition or "").strip()
                if edition:
                    edition_lower = edition.lower()
                    if "1st" in edition_lower or "first" in edition_lower:
                        edition = ""
                    else:
                        if not any(x in edition_lower for x in ["edition", "ed.", "ed"]):
                            edition = f"{edition} Edition"

                isbn_val = meta.isbn or "".strip()
                is_scan = source == "SCAN" or "scan" in meta.basename_no_ext.lower() or "scan" in meta.title.lower()
                is_ocr = bool(meta.ocr) or "ocr" in meta.basename_no_ext.lower() or "ocr" in meta.title.lower()

                parts = []
                if author:
                    parts.append(author)
                if title:
                    if parts:
                        parts.append("-")
                    parts.append(title)
                if year:
                    parts.append(year)
                if edition:
                    parts.append(edition)
                if format_val:
                    parts.append(format_val)
                if isbn_val:
                    parts.append(isbn_val)
                if is_retail:
                    parts.append("Retail")
                if is_scan:
                    parts.append("Scan")
                if is_ocr:
                    parts.append("OCR")

                base_name = " ".join(parts)
                base_name = " ".join(base_name.split())
                znth_name = f"{base_name}-{tag}" if tag else base_name

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
            "OTHER": "16",
            "AUDIOBOOK": "10",
            "BOOK": "9",
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

            resolved_id = type_id.get(meta_type or "", "0")

            if category == "GAME":
                resolved_id = "16"
            elif meta.audiobook:
                resolved_id = "10"
            elif category == "BOOK":
                resolved_id = "9"

            return {"type_id": resolved_id}
