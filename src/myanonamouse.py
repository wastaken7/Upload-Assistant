# Upload Assistant © 2026 Audionut & wastaken7 — Licensed under UAPL v1.0
import html
import json
import re
from typing import Any

import httpx

from src.book_prep import is_valid_book_language, resolve_book_language
from src.console import logger
from src.metadata_cache import cache_for, is_cache_miss

mam_color = "[#eac117]MyAnonamouse[/#eac117]"


class MyAnonamouseManager:
    def _parse_torrent_info(self, item: dict[str, Any]) -> dict[str, Any]:
        logger.debug(f"{mam_color} raw item: {item}")

        metadata: dict[str, Any] = {}

        # Title & Name
        title = item.get("title") or item.get("name")
        if title:
            metadata["title"] = html.unescape(str(title)).strip()

        # Authors
        author_info = item.get("author_info")
        if author_info:
            try:
                if isinstance(author_info, str):
                    author_dict = json.loads(author_info)
                elif isinstance(author_info, dict):
                    author_dict = author_info
                else:
                    author_dict = {}
                authors = [html.unescape(str(name)).strip() for name in author_dict.values()]
                if authors:
                    metadata["author"] = ", ".join(authors)
            except Exception as e:
                logger.debug(f"{mam_color}: [yellow]Warning: Could not parse MAM authors: {e}[/yellow]")

        # Narrator
        narrator_info = item.get("narrator_info")
        if narrator_info:
            try:
                if isinstance(narrator_info, str):
                    narrator_dict = json.loads(narrator_info)
                elif isinstance(narrator_info, dict):
                    narrator_dict = narrator_info
                else:
                    narrator_dict = {}
                narrators = [html.unescape(str(name)).strip() for name in narrator_dict.values()]
                if narrators:
                    metadata["narrator"] = ", ".join(narrators)
            except Exception as e:
                logger.debug(f"[yellow]Warning: Could not parse MAM narrators: {e}[/yellow]")

        # Description -> overview
        description = item.get("description")
        if description:
            # Unescape html entities
            unescaped_desc = html.unescape(str(description)).strip()
            metadata["overview"] = unescaped_desc

        # ISBN
        isbn = item.get("isbn")
        if isbn:
            cleaned_isbn = re.sub(r"[-\s]", "", str(isbn))
            if cleaned_isbn:
                metadata["isbn"] = cleaned_isbn

        # ASIN
        asin = item.get("asin") or item.get("ASIN")
        if asin:
            cleaned_asin = str(asin).strip()
            if cleaned_asin:
                metadata["asin"] = cleaned_asin

        # Language
        lang = item.get("lang_code")
        if lang:
            try:
                full, iso3 = resolve_book_language(str(lang))
                if is_valid_book_language(full, iso3):
                    metadata["book_language"] = full
                    if iso3:
                        metadata["book_language_iso"] = iso3
            except Exception as ex:
                logger.debug(f"[yellow]Warning: Could not resolve language '{lang}': {ex}[/yellow]")

        """ Not useful for now, too polluted
        # Tags -> keywords
        tags = item.get("tags")
        if tags:
            words = str(tags).split()
            cleaned_words = [w.strip().lower() for w in words if w.strip()]
            if cleaned_words:
                metadata["keywords"] = ", ".join(cleaned_words)
        """

        # Cover
        mam_id = item.get("id")
        poster_type = item.get("poster_type")
        if mam_id and poster_type:
            ext = "jpeg"
            if "png" in str(poster_type).lower():
                ext = "png"
            elif "gif" in str(poster_type).lower():
                ext = "gif"
            metadata["artwork_url"] = f"https://cdn.myanonamouse.net/t/p/large/{mam_id}.{ext}"

        # Comic / Manga detection
        catname = str(item.get("catname") or "").lower()
        tags = str(item.get("tags") or "").lower()
        categories = str(item.get("categories") or "").lower()

        if "comic" in catname or "comic" in tags or "comic" in categories:
            metadata["comic"] = True
        if "manga" in catname or "manga" in tags or "manga" in categories:
            metadata["manga"] = True
        if "magazine" in catname or "magazine" in tags or "magazine" in categories:
            metadata["magazine"] = True
        if "newspaper" in catname or "newspaper" in tags or "newspaper" in categories:
            metadata["newspaper"] = True

        return metadata

    async def search_by_id(self, torrent_id: str, base_dir: str = "", api_key: str = "") -> dict[str, Any] | None:
        """
        Search MyAnonamouse API by torrent ID.
        Returns a dict of metadata or None if not found/error.
        """
        clean_id = torrent_id.strip()
        if not clean_id or not clean_id.isdigit():
            return None

        cache = cache_for(base_dir)
        cached_data = await cache.get("myanonamouse", "torrent", clean_id)
        if not is_cache_miss(cached_data) and isinstance(cached_data, dict):
            if cached_data.get("not_found"):
                return None
            logger.info(f"{mam_color}: ID match found (cached): {clean_id}")
            return cached_data

        if not api_key:
            logger.debug(f"{mam_color}: [yellow]API key/session cookie not configured, skipping search[/yellow]")
            return None

        url = "https://www.myanonamouse.net/tor/js/loadSearchJSONbasic.php"
        payload = {"tor": {"id": int(clean_id)}, "description": "", "isbn": ""}
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Content-Type": "application/json",
        }
        cookies = {"mam_id": api_key}

        logger.debug(f"{mam_color}: Searching API for ID: {clean_id}")

        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                resp = await client.post(url, json=payload, headers=headers, cookies=cookies, timeout=15.0)
                if resp.status_code == 200:
                    data = resp.json()
                    if "data" in data and isinstance(data["data"], list) and data["data"]:
                        metadata = self._parse_torrent_info(data["data"][0])
                        if metadata:
                            logger.info(f"{mam_color}: match found: {metadata.get('title')}")

                            await cache.set("myanonamouse", "torrent", clean_id, metadata)

                            return metadata
                    else:
                        logger.info(f"{mam_color}: [yellow]No items found for ID: {clean_id}[/yellow]")
                        await cache.set("myanonamouse", "torrent", clean_id, {"not_found": True}, negative=True)
                elif resp.status_code in (401, 403):
                    logger.info(
                        f"{mam_color}: [bold red]API: Unauthorized/Forbidden (Status {resp.status_code}). Check your mam_api_key/mam_id and IP locked session cookie setting on the website.[/bold red]"
                    )
                else:
                    logger.info(f"{mam_color}: [red]API returned error status code {resp.status_code} for ID: {clean_id}[/red]")
        except Exception as e:
            logger.info(f"{mam_color}: [red]API: Network or query error for ID {clean_id}: {e}[/red]")

        return None


myanonamouse_manager = MyAnonamouseManager()
