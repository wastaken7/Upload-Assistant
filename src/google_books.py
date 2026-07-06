# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import asyncio
import json
import os
import re
from pathlib import Path
from typing import Any

import httpx

from src.book_prep import _resolve_book_language, is_valid_book_language
from src.console import logger

google_color_str = "[#4285f4]G[/#4285f4][#ea4335]o[/#ea4335][#fbbc05]o[/#fbbc05][#4285f4]g[/#4285f4][#34a853]l[/#34a853][#ea4335]e[/#ea4335] [#4285f4]Books[/#4285f4]"


class GoogleBooksManager:
    def _parse_volume_info(self, data: dict[str, Any], isbn: str, debug: bool = False) -> dict[str, Any] | None:
        """
        Helper to parse raw Google Books API response data uniformly.
        """
        total_items = data.get("totalItems", 0)
        if total_items <= 0 or "items" not in data:
            return None

        volume = data["items"][0]
        volume_id = volume.get("id")
        volume_info = volume.get("volumeInfo", {})
        image_link = volume_info.get("imageLinks", {}).get("thumbnail", "")

        metadata: dict[str, Any] = {}

        # Cover URL (Google Books cover image)
        if volume_id and image_link:
            metadata["poster"] = image_link

        # Title & Subtitle
        title = volume_info.get("title")
        subtitle = volume_info.get("subtitle")
        if title:
            if subtitle:
                metadata["title"] = f"{title}: {subtitle}"
            else:
                metadata["title"] = title

        # Authors -> author
        authors = volume_info.get("authors")
        if authors:
            metadata["author"] = ", ".join(authors)

        # Publisher
        publisher = volume_info.get("publisher")
        if publisher:
            metadata["publisher"] = publisher

        # Description -> overview
        description = volume_info.get("description")
        if description:
            # Clean HTML tags
            cleaned_desc = re.sub(r"<[^>]+>", "", description).strip()
            metadata["overview"] = cleaned_desc

        # Year
        published_date = volume_info.get("publishedDate")
        if published_date:
            year_match = re.search(r"\b\d{4}\b", published_date)
            if year_match:
                year_str = year_match.group(0)
                metadata["year"] = year_str
                metadata["search_year"] = int(year_str)

        # Language
        lang = volume_info.get("language")
        if lang:
            try:
                full, iso3 = _resolve_book_language(lang)
                if is_valid_book_language(full, iso3):
                    metadata["book_language"] = full
                    if iso3:
                        metadata["book_language_iso"] = iso3
            except Exception as ex:
                logger.debug(f"[yellow]Warning: Could not resolve language '{lang}': {ex}[/yellow]")

        # Genre
        categories = volume_info.get("categories")
        if categories:
            metadata["keywords"] = metadata["genres"] = [str(cat) for cat in categories if cat]
            # Detect comic and manga
            if any("comic" in cat.lower() for cat in categories):
                metadata["comic"] = True
            if any("manga" in cat.lower() for cat in categories):
                metadata["manga"] = True
            if any("magazine" in cat.lower() for cat in categories):
                metadata["magazine"] = True
            if any("newspaper" in cat.lower() for cat in categories):
                metadata["newspaper"] = True

        metadata["isbn"] = isbn
        return metadata

    async def search_by_isbn(self, isbn: str, base_dir: str = "", api_key: str = "", debug: bool = False) -> dict[str, Any] | None:
        """
        Search Google Books API by ISBN.
        Returns a dict of metadata or None if not found/error.
        """
        clean_isbn = re.sub(r"[-\s]", "", isbn)
        if not clean_isbn:
            return None

        # Check local cache first
        cache_file = None
        if base_dir:
            cache_dir = os.path.join(base_dir, "tmp", "google_books_cache")
            try:
                os.makedirs(cache_dir, exist_ok=True)
                cache_file = os.path.join(cache_dir, f"{clean_isbn}.json")
                if os.path.exists(cache_file):  # noqa: ASYNC240
                    try:
                        cache_content = await asyncio.to_thread(Path(cache_file).read_text, encoding="utf-8")
                        cached_data = json.loads(cache_content)
                        if cached_data:
                            # Support backwards compatibility if cache is in the old parsed format
                            if "items" in cached_data or "totalItems" in cached_data:
                                if cached_data.get("totalItems", 0) == 0:
                                    logger.info(f"{google_color_str}: ISBN match not found (cached): {clean_isbn}")
                                    return None
                                parsed_meta = self._parse_volume_info(cached_data, isbn, debug)
                                if parsed_meta:
                                    logger.info(f"{google_color_str}: ISBN match found (cached): {clean_isbn}")
                                else:
                                    logger.info(f"{google_color_str}: ISBN match not found (cached): {clean_isbn}")
                                return parsed_meta
                            else:
                                if cached_data.get("not_found"):
                                    logger.info(f"{google_color_str}: ISBN match not found (cached): {clean_isbn}")
                                    return None
                                logger.info(f"{google_color_str}: ISBN match found (cached): {clean_isbn}")
                                return cached_data
                    except Exception as ex:
                        logger.debug(f"[yellow]Warning: Could not read cache file for ISBN '{clean_isbn}': {ex}[/yellow]")
            except Exception as ex:
                logger.debug(f"[yellow]Warning: Could not create cache directory: {ex}[/yellow]")

        url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{clean_isbn}"
        if api_key:
            url += f"&key={api_key}"
        logger.debug(f"[cyan]{google_color_str}: Searching API for ISBN: {clean_isbn}[/cyan]")

        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                resp = await client.get(url, timeout=10.0)
                if resp.status_code == 200:
                    data = resp.json()
                    total_items = data.get("totalItems", 0)
                    if total_items > 0 and "items" in data:
                        metadata = self._parse_volume_info(data, isbn, debug)
                        # Save full response to cache since response was successful
                        if cache_file:
                            try:
                                cache_content = json.dumps(data, indent=4)
                                await asyncio.to_thread(Path(cache_file).write_text, cache_content, encoding="utf-8")
                                logger.debug(f"{google_color_str}: Saved cache for ISBN: {clean_isbn}")
                            except Exception as ex:
                                logger.debug(f"[yellow]Warning: Could not write cache for ISBN '{clean_isbn}': {ex}[/yellow]")
                        if metadata:
                            logger.info(f"{google_color_str}: ISBN match found: {clean_isbn}")
                        return metadata
                    else:
                        logger.info(f"{google_color_str}: No items found for ISBN: {clean_isbn}")
                        if cache_file:
                            try:
                                cache_content = json.dumps(data, indent=4)
                                await asyncio.to_thread(Path(cache_file).write_text, cache_content, encoding="utf-8")
                                logger.debug(f"{google_color_str}: Saved empty cache for ISBN: {clean_isbn}")
                            except Exception as ex:
                                logger.debug(f"[yellow]Warning: Could not write cache for ISBN '{clean_isbn}': {ex}[/yellow]")
                else:
                    if resp.status_code == 429:
                        logger.info(f"{google_color_str}: Rate limited (Status 429) for ISBN: {clean_isbn}")
                    else:
                        logger.info(f"{google_color_str}: API returned error status code {resp.status_code} for ISBN: {clean_isbn}")
                        if resp.status_code == 404 and cache_file:
                            try:
                                cache_content = json.dumps({"not_found": True}, indent=4)
                                await asyncio.to_thread(Path(cache_file).write_text, cache_content, encoding="utf-8")
                            except Exception as ex:
                                logger.debug(f"[yellow]Warning: Could not write cache for ISBN '{clean_isbn}': {ex}[/yellow]")
        except Exception as e:
            logger.info(f"{google_color_str}: Network or query error for ISBN {clean_isbn}: {e}")

        return None


google_books_manager = GoogleBooksManager()
