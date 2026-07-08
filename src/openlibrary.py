# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import asyncio
import contextlib
import json
import os
import re
from pathlib import Path
from typing import Any

import httpx

from src.console import logger

openlibrary_color_str = "[#e1d8c1]OpenLibrary[/#e1d8c1]"


class OpenLibraryManager:
    async def get_author_name(self, author_key: str, client: httpx.AsyncClient, cache_dir: str | None) -> str:
        """Fetch author name from key like /authors/OL26320A."""
        author_id = author_key.split("/")[-1]
        author_cache_file = None
        if cache_dir:
            author_cache_file = os.path.join(cache_dir, f"author_{author_id}.json")
            if author_cache_file and os.path.exists(author_cache_file):
                try:
                    cache_content = await asyncio.to_thread(Path(author_cache_file).read_text, encoding="utf-8")
                    cached_data = json.loads(cache_content)
                    if cached_data and "name" in cached_data:
                        return cached_data["name"]
                except Exception as ex:
                    logger.debug(f"[yellow]Warning: Could not read author cache for '{author_id}': {ex}[/yellow]")

        url = f"https://openlibrary.org/authors/{author_id}.json"
        try:
            resp = await client.get(url, timeout=10.0)
            if resp.status_code == 200:
                data = resp.json()
                name = data.get("name") or data.get("personal_name") or ""
                if name and cache_dir and author_cache_file:
                    with contextlib.suppress(Exception):
                        await asyncio.to_thread(Path(author_cache_file).write_text, json.dumps(data, indent=4), encoding="utf-8")
                return name
        except Exception as e:
            logger.debug(f"[yellow]Warning: Error fetching author name for {author_id}: {e}[/yellow]")
        return ""

    async def search_by_work_id(self, work_id: str, base_dir: str = "") -> dict[str, Any] | None:
        """Search OpenLibrary by Work ID (e.g. OL45883W)."""
        work_id = work_id.strip()
        if not work_id:
            return None
        cache_dir = None
        cache_file = None
        if base_dir:
            cache_dir = os.path.join(base_dir, "tmp", "openlibrary_cache")
            try:
                os.makedirs(cache_dir, exist_ok=True)
                cache_file = os.path.join(cache_dir, f"{work_id}.json")
                if os.path.exists(cache_file):
                    try:
                        cache_content = await asyncio.to_thread(Path(cache_file).read_text, encoding="utf-8")
                        cached_data = json.loads(cache_content)
                        if cached_data:
                            if cached_data.get("not_found"):
                                logger.info(f"{openlibrary_color_str}: Work match not found (cached): {work_id}")
                                return None
                            logger.info(f"{openlibrary_color_str}: Work match found (cached): {work_id}")
                            return cached_data
                    except Exception as ex:
                        logger.debug(f"[yellow]Warning: Could not read cache file for Work ID '{work_id}': {ex}[/yellow]")
            except Exception as ex:
                logger.debug(f"[yellow]Warning: Could not create cache directory: {ex}[/yellow]")

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

                        # Description
                        desc_val = data.get("description")
                        if desc_val:
                            desc = desc_val.get("value", "") if isinstance(desc_val, dict) else str(desc_val)
                            metadata["overview"] = re.sub(r"<[^>]+>", "", desc).strip()

                        # Cover
                        covers = data.get("covers")
                        if covers and isinstance(covers, list) and covers[0] > 0:
                            metadata["poster"] = f"https://covers.openlibrary.org/b/id/{covers[0]}-L.jpg"

                        # Authors
                        authors_list = data.get("authors", [])
                        author_names = []
                        for author_entry in authors_list:
                            author_obj = author_entry.get("author")
                            if author_obj and "key" in author_obj:
                                author_name = await self.get_author_name(author_obj["key"], client, cache_dir)
                                if author_name:
                                    author_names.append(author_name)
                        if author_names:
                            metadata["author"] = ", ".join(author_names)

                        # Subjects / Keywords
                        subjects = data.get("subjects")
                        if subjects and isinstance(subjects, list):
                            metadata["keywords"] = metadata["genres"] = [str(s) for s in subjects[:10] if s]

                        metadata["openlibrary"] = work_id

                        if cache_file:
                            try:
                                await asyncio.to_thread(Path(cache_file).write_text, json.dumps(metadata, indent=4), encoding="utf-8")
                            except Exception as ex:
                                logger.debug(f"[yellow]Warning: Could not write cache for Work ID '{work_id}': {ex}[/yellow]")

                        return metadata
                    else:
                        logger.info(f"{openlibrary_color_str}: No metadata found for Work ID: {work_id}")
                        if cache_file:
                            with contextlib.suppress(Exception):
                                await asyncio.to_thread(Path(cache_file).write_text, json.dumps({"not_found": True}, indent=4), encoding="utf-8")
                else:
                    logger.info(f"{openlibrary_color_str}: API returned error status code {resp.status_code} for Work ID: {work_id}")
                    if resp.status_code == 404 and cache_file:
                        with contextlib.suppress(Exception):
                            await asyncio.to_thread(Path(cache_file).write_text, json.dumps({"not_found": True}, indent=4), encoding="utf-8")
        except Exception as e:
            logger.info(f"{openlibrary_color_str}: Network or query error for Work ID {work_id}: {e}")

        return None

    async def search_by_isbn(self, isbn: str, base_dir: str = "") -> dict[str, Any] | None:
        """Search OpenLibrary by ISBN."""
        clean_isbn = re.sub(r"[-\s]", "", isbn)
        if not clean_isbn:
            return None

        cache_dir = None
        cache_file = None
        if base_dir:
            cache_dir = os.path.join(base_dir, "tmp", "openlibrary_cache")
            try:
                os.makedirs(cache_dir, exist_ok=True)
                cache_file = os.path.join(cache_dir, f"isbn_{clean_isbn}.json")
                if os.path.exists(cache_file):
                    try:
                        cache_content = await asyncio.to_thread(Path(cache_file).read_text, encoding="utf-8")
                        cached_data = json.loads(cache_content)
                        if cached_data:
                            if cached_data.get("not_found"):
                                logger.info(f"{openlibrary_color_str}: ISBN match not found (cached): {clean_isbn}")
                                return None
                            logger.info(f"{openlibrary_color_str}: ISBN match found (cached): {clean_isbn}")
                            return cached_data
                    except Exception as ex:
                        logger.debug(f"[yellow]Warning: Could not read cache file for ISBN '{clean_isbn}': {ex}[/yellow]")
            except Exception as ex:
                logger.debug(f"[yellow]Warning: Could not create cache directory: {ex}[/yellow]")

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

                        # Find the Work ID if present
                        work_key = ""
                        works = details.get("works", [])
                        if works and isinstance(works, list) and "key" in works[0]:
                            work_key = works[0]["key"]

                        if work_key:
                            work_id = work_key.split("/")[-1]
                            metadata = await self.search_by_work_id(work_id, base_dir)
                            if metadata:
                                # Add any details fields that might not be in the work info
                                publishers = details.get("publishers")
                                if publishers and isinstance(publishers, list) and not metadata.get("publisher"):
                                    metadata["publisher"] = ", ".join(publishers)

                                publish_date = details.get("publish_date")
                                if publish_date and not metadata.get("year"):
                                    year_match = re.search(r"\b\d{4}\b", str(publish_date))
                                    if year_match:
                                        year_str = year_match.group(0)
                                        metadata["year"] = year_str
                                        metadata["search_year"] = int(year_str)

                                metadata["isbn"] = clean_isbn

                                # Cache the ISBN-to-metadata association
                                if cache_file:
                                    with contextlib.suppress(Exception):
                                        await asyncio.to_thread(Path(cache_file).write_text, json.dumps(metadata, indent=4), encoding="utf-8")
                                return metadata
                            else:
                                if cache_file:
                                    with contextlib.suppress(Exception):
                                        await asyncio.to_thread(Path(cache_file).write_text, json.dumps({"not_found": True}, indent=4), encoding="utf-8")
                                return None
                        else:
                            # Parse metadata directly from details if no work key
                            metadata = {}
                            title = details.get("title")
                            if title:
                                subtitle = details.get("subtitle")
                                metadata["title"] = f"{title}: {subtitle}" if subtitle else title

                                authors = details.get("authors", [])
                                author_names = [a.get("name") for a in authors if a.get("name")]
                                if author_names:
                                    metadata["author"] = ", ".join(author_names)

                                publishers = details.get("publishers")
                                if publishers and isinstance(publishers, list):
                                    metadata["publisher"] = ", ".join(publishers)

                                publish_date = details.get("publish_date")
                                if publish_date:
                                    year_match = re.search(r"\b\d{4}\b", str(publish_date))
                                    if year_match:
                                        year_str = year_match.group(0)
                                        metadata["year"] = year_str
                                        metadata["search_year"] = int(year_str)

                                thumbnail_url = book_data.get("thumbnail_url")
                                if thumbnail_url:
                                    metadata["poster"] = thumbnail_url.replace("-S.jpg", "-L.jpg")

                                metadata["isbn"] = clean_isbn

                                if metadata and cache_file:
                                    with contextlib.suppress(Exception):
                                        await asyncio.to_thread(Path(cache_file).write_text, json.dumps(metadata, indent=4), encoding="utf-8")
                                return metadata
                            else:
                                if cache_file:
                                    with contextlib.suppress(Exception):
                                        await asyncio.to_thread(Path(cache_file).write_text, json.dumps({"not_found": True}, indent=4), encoding="utf-8")
                                return None
                    else:
                        logger.info(f"{openlibrary_color_str}: No items found for ISBN: {clean_isbn}")
                        if cache_file:
                            with contextlib.suppress(Exception):
                                await asyncio.to_thread(Path(cache_file).write_text, json.dumps({"not_found": True}, indent=4), encoding="utf-8")
                else:
                    logger.info(f"{openlibrary_color_str}: API returned error status code {resp.status_code} for ISBN: {clean_isbn}")
                    if resp.status_code == 404 and cache_file:
                        with contextlib.suppress(Exception):
                            await asyncio.to_thread(Path(cache_file).write_text, json.dumps({"not_found": True}, indent=4), encoding="utf-8")
        except Exception as e:
            logger.info(f"{openlibrary_color_str}: Network or query error for ISBN {clean_isbn}: {e}")

        return None


openlibrary_manager = OpenLibraryManager()
