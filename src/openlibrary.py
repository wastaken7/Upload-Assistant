# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import re
from typing import Any

import httpx

from src.console import logger
from src.metadata_cache import MetadataCache, cache_for, is_cache_miss

openlibrary_color_str = "[#e1d8c1]OpenLibrary[/#e1d8c1]"


class OpenLibraryManager:
    async def get_author_name(self, author_key: str, client: httpx.AsyncClient, cache: MetadataCache) -> str:
        """Fetch an author name from a key such as /authors/OL26320A."""
        author_id = author_key.split("/")[-1]
        cached_data = await cache.get("openlibrary", "author", author_id)
        if not is_cache_miss(cached_data) and isinstance(cached_data, dict):
            return str(cached_data.get("name", ""))

        url = f"https://openlibrary.org/authors/{author_id}.json"
        try:
            resp = await client.get(url, timeout=10.0)
            if resp.status_code == 200:
                data = resp.json()
                name = data.get("name") or data.get("personal_name") or ""
                if name:
                    await cache.set("openlibrary", "author", author_id, {"name": name})
                else:
                    await cache.set("openlibrary", "author", author_id, {}, negative=True)
                return name
            if resp.status_code == 404:
                await cache.set("openlibrary", "author", author_id, {}, negative=True)
        except Exception as e:
            logger.debug(f"[yellow]Warning: Error fetching author name for {author_id}: {e}[/yellow]")
        return ""

    async def search_by_work_id(self, work_id: str, base_dir: str = "") -> dict[str, Any] | None:
        """Search OpenLibrary by Work ID (e.g. OL45883W)."""
        work_id = work_id.strip()
        if not work_id:
            return None

        cache = cache_for(base_dir)
        cached_data = await cache.get("openlibrary", "work", work_id)
        if not is_cache_miss(cached_data) and isinstance(cached_data, dict):
            if cached_data.get("not_found"):
                logger.info(f"{openlibrary_color_str}: Work match not found (cached): {work_id}")
                return None
            logger.info(f"{openlibrary_color_str}: Work match found (cached): {work_id}")
            return cached_data

        url = f"https://openlibrary.org/works/{work_id}.json"
        logger.debug(f"[cyan]{openlibrary_color_str}: Searching API for Work ID: {work_id}[/cyan]")

        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                resp = await client.get(url, timeout=10.0)
                if resp.status_code == 200:
                    data = resp.json()
                    metadata: dict[str, Any] = {}

                    title = data.get("title")
                    if title:
                        subtitle = data.get("subtitle")
                        metadata["title"] = f"{title}: {subtitle}" if subtitle else title

                        description = data.get("description")
                        if description:
                            value = description.get("value", "") if isinstance(description, dict) else str(description)
                            metadata["overview"] = re.sub(r"<[^>]+>", "", value).strip()

                        covers = data.get("covers")
                        if covers and isinstance(covers, list) and isinstance(covers[0], int) and covers[0] > 0:
                            metadata["artwork_url"] = f"https://covers.openlibrary.org/b/id/{covers[0]}-L.jpg"

                        author_names = []
                        for author_entry in data.get("authors", []):
                            author_obj = author_entry.get("author")
                            if author_obj and "key" in author_obj:
                                author_name = await self.get_author_name(author_obj["key"], client, cache)
                                if author_name:
                                    author_names.append(author_name)
                        if author_names:
                            metadata["author"] = ", ".join(author_names)

                        subjects = data.get("subjects")
                        if subjects and isinstance(subjects, list):
                            subject_list = [str(subject) for subject in subjects[:10] if subject]
                            metadata["keywords"] = list(subject_list)
                            metadata["genres"] = list(subject_list)

                        metadata["openlibrary"] = work_id
                        await cache.set("openlibrary", "work", work_id, metadata)
                        return metadata

                    logger.info(f"{openlibrary_color_str}: No metadata found for Work ID: {work_id}")
                    await cache.set("openlibrary", "work", work_id, {"not_found": True}, negative=True)
                else:
                    logger.info(f"{openlibrary_color_str}: API returned error status code {resp.status_code} for Work ID: {work_id}")
                    if resp.status_code == 404:
                        await cache.set("openlibrary", "work", work_id, {"not_found": True}, negative=True)
        except Exception as e:
            logger.info(f"{openlibrary_color_str}: Network or query error for Work ID {work_id}: {e}")

        return None

    async def search_by_isbn(self, isbn: str, base_dir: str = "") -> dict[str, Any] | None:
        """Search OpenLibrary by ISBN."""
        clean_isbn = re.sub(r"[-\s]", "", isbn)
        if not clean_isbn:
            return None

        cache = cache_for(base_dir)
        cached_data = await cache.get("openlibrary", "isbn", clean_isbn)
        if not is_cache_miss(cached_data) and isinstance(cached_data, dict):
            if cached_data.get("not_found"):
                logger.info(f"{openlibrary_color_str}: ISBN match not found (cached): {clean_isbn}")
                return None
            logger.info(f"{openlibrary_color_str}: ISBN match found (cached): {clean_isbn}")
            return cached_data

        bibkey = f"ISBN:{clean_isbn}"
        url = f"https://openlibrary.org/api/books?bibkeys={bibkey}&jscmd=details&format=json"
        logger.debug(f"[cyan]{openlibrary_color_str}: Searching API for ISBN: {clean_isbn}[/cyan]")

        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                resp = await client.get(url, timeout=10.0)
                if resp.status_code == 200:
                    res_data = resp.json()
                    book_data = res_data.get(bibkey)
                    if book_data:
                        details = book_data.get("details", {})
                        works = details.get("works", [])
                        work_key = works[0].get("key", "") if works and isinstance(works, list) else ""

                        if work_key:
                            metadata = await self.search_by_work_id(work_key.split("/")[-1], base_dir)
                            if metadata:
                                publishers = details.get("publishers")
                                if publishers and isinstance(publishers, list) and not metadata.get("publisher"):
                                    metadata["publisher"] = ", ".join(publishers)
                                self._add_year(metadata, details.get("publish_date"))
                                metadata["isbn"] = clean_isbn
                                await cache.set("openlibrary", "isbn", clean_isbn, metadata)
                                return metadata

                        metadata = self._metadata_from_book_details(book_data, details, clean_isbn)
                        if metadata:
                            await cache.set("openlibrary", "isbn", clean_isbn, metadata)
                            return metadata
                        await cache.set("openlibrary", "isbn", clean_isbn, {"not_found": True}, negative=True)
                        return None

                    logger.info(f"{openlibrary_color_str}: No items found for ISBN: {clean_isbn}")
                    await cache.set("openlibrary", "isbn", clean_isbn, {"not_found": True}, negative=True)
                else:
                    logger.info(f"{openlibrary_color_str}: API returned error status code {resp.status_code} for ISBN: {clean_isbn}")
                    if resp.status_code == 404:
                        await cache.set("openlibrary", "isbn", clean_isbn, {"not_found": True}, negative=True)
        except Exception as e:
            logger.info(f"{openlibrary_color_str}: Network or query error for ISBN {clean_isbn}: {e}")

        return None

    @staticmethod
    def _add_year(metadata: dict[str, Any], publish_date: Any) -> None:
        if publish_date and not metadata.get("year"):
            year_match = re.search(r"\b\d{4}\b", str(publish_date))
            if year_match:
                year = year_match.group(0)
                metadata["year"] = year
                metadata["search_year"] = int(year)

    def _metadata_from_book_details(self, book_data: dict[str, Any], details: dict[str, Any], isbn: str) -> dict[str, Any]:
        title = details.get("title")
        if not title:
            return {}

        subtitle = details.get("subtitle")
        metadata: dict[str, Any] = {"title": f"{title}: {subtitle}" if subtitle else title, "isbn": isbn}
        author_names = [author.get("name") for author in details.get("authors", []) if author.get("name")]
        if author_names:
            metadata["author"] = ", ".join(author_names)
        publishers = details.get("publishers")
        if publishers and isinstance(publishers, list):
            metadata["publisher"] = ", ".join(publishers)
        self._add_year(metadata, details.get("publish_date"))
        thumbnail_url = book_data.get("thumbnail_url")
        if thumbnail_url:
            metadata["artwork_url"] = thumbnail_url.replace("-S.jpg", "-L.jpg")
        return metadata


openlibrary_manager = OpenLibraryManager()
