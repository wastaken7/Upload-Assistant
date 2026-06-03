# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import asyncio
import json
import os
import re
from pathlib import Path
from typing import Any, Optional

import httpx

from src.book_prep import _resolve_book_language, is_valid_book_language
from src.console import console


class GoogleBooksManager:
    def _parse_volume_info(self, data: dict[str, Any], isbn: str, debug: bool = False) -> Optional[dict[str, Any]]:
        """
        Helper to parse raw Google Books API response data uniformly.
        """
        total_items = data.get("totalItems", 0)
        if total_items <= 0 or "items" not in data:
            return None

        volume = data["items"][0]
        volume_id = volume.get("id")
        volume_info = volume.get("volumeInfo", {})

        metadata: dict[str, Any] = {}

        # Poster URL (Google Books cover image)
        if volume_id and volume_info.get("imageLinks"):
            metadata["poster"] = f"https://books.google.com/books/content?id={volume_id}&printsec=frontcover&img=1"

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
                if debug:
                    console.print(f"[yellow]Warning: Could not resolve language '{lang}': {ex}[/yellow]")

        metadata["isbn"] = isbn
        return metadata

    async def search_by_isbn(self, isbn: str, base_dir: str = "", api_key: str = "", debug: bool = False) -> Optional[dict[str, Any]]:
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
                            if debug:
                                console.print(f"[cyan]Google Books: Using cached search for ISBN: {clean_isbn}[/cyan]")
                            else:
                                console.print(f"Google Books: Using cached search for ISBN: {clean_isbn}")

                            # Support backwards compatibility if cache is in the old parsed format
                            if "items" in cached_data or "totalItems" in cached_data:
                                return self._parse_volume_info(cached_data, isbn, debug)
                            else:
                                return cached_data
                    except Exception as ex:
                        if debug:
                            console.print(f"[yellow]Warning: Could not read cache file for ISBN '{clean_isbn}': {ex}[/yellow]")
            except Exception as ex:
                if debug:
                    console.print(f"[yellow]Warning: Could not create cache directory: {ex}[/yellow]")

        url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{clean_isbn}"
        if api_key:
            url += f"&key={api_key}"
        if debug:
            console.print(f"[cyan]Searching Google Books API for ISBN: {clean_isbn}[/cyan]")

        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                resp = await client.get(url, timeout=10.0)
                if resp.status_code == 200:
                    data = resp.json()
                    total_items = data.get("totalItems", 0)
                    if total_items > 0 and "items" in data:
                        metadata = self._parse_volume_info(data, isbn, debug)
                        if metadata:
                            if debug:
                                console.print(f"[green]Google Books match found: {metadata.get('title')} by {metadata.get('author')}[/green]")
                            else:
                                console.print(f"Google Books match found: {metadata.get('title')} by {metadata.get('author')}")

                            # Save full response to cache since response was successful
                            if cache_file:
                                try:
                                    cache_content = json.dumps(data, indent=4)
                                    await asyncio.to_thread(Path(cache_file).write_text, cache_content, encoding="utf-8")
                                    if debug:
                                        console.print(f"[cyan]Google Books: Saved cache for ISBN: {clean_isbn}[/cyan]")
                                except Exception as ex:
                                    if debug:
                                        console.print(f"[yellow]Warning: Could not write cache for ISBN '{clean_isbn}': {ex}[/yellow]")

                            return metadata
                    else:
                        console.print(f"[yellow]Google Books: No items found for ISBN: {clean_isbn}[/yellow]")
                else:
                    if resp.status_code == 429:
                        console.print(f"[bold red]Google Books API: Rate limited (Status 429) for ISBN: {clean_isbn}[/bold red]")
                    else:
                        console.print(f"[red]Google Books API returned error status code {resp.status_code} for ISBN: {clean_isbn}[/red]")
        except Exception as e:
            console.print(f"[red]Google Books API: Network or query error for ISBN {clean_isbn}: {e}[/red]")

        return None


google_books_manager = GoogleBooksManager()
