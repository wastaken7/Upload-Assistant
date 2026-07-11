# Upload Assistant © 2026 Audionut & wastaken7 — Licensed under UAPL v1.0
import json
import os
import time
from typing import Any

import aiofiles
import httpx

from src.console import logger


class IGDBAPI:
    def __init__(self, client_id: str, client_secret: str, base_dir: str = ""):
        self.client_id = client_id
        self.client_secret = client_secret
        self.base_dir = base_dir
        self.token_file = os.path.join(base_dir, "tmp", "igdb_cache", "igdb_token.json") if base_dir else ""
        self.access_token = None

    async def get_access_token(self) -> str | None:
        # Try loading cached token
        if self.token_file and os.path.exists(self.token_file):
            try:
                async with aiofiles.open(self.token_file, encoding="utf-8") as f:
                    content = await f.read()
                    cached = json.loads(content)
                if cached.get("expires_at", 0) > time.time() + 300:
                    self.access_token = cached.get("access_token")
                    return self.access_token
            except Exception:
                pass

        # Request new token
        url = "https://id.twitch.tv/oauth2/token"
        params = {"client_id": self.client_id, "client_secret": self.client_secret, "grant_type": "client_credentials"}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    self.access_token = data.get("access_token")
                    expires_in = data.get("expires_in", 3600)
                    expires_at = time.time() + expires_in

                    if self.token_file:
                        os.makedirs(os.path.dirname(self.token_file), exist_ok=True)
                        async with aiofiles.open(self.token_file, "w", encoding="utf-8") as f:
                            await f.write(json.dumps({"access_token": self.access_token, "expires_at": expires_at}))
                    return self.access_token
                else:
                    logger.info(f"[red]IGDB: Failed to authenticate with Twitch API. Status: {resp.status_code}[/red]")
        except Exception as e:
            logger.info(f"[red]IGDB: Twitch OAuth error: {e}[/red]")
        return None

    async def search_game(self, title: str) -> list[dict[str, Any]] | None:
        import asyncio
        import re
        from pathlib import Path

        clean_title = re.sub(r'[^a-zA-Z0-9_\-]', '_', title).lower()

        # Check local cache first (search results level)
        cache_file = None
        if self.base_dir:
            cache_dir = os.path.join(self.base_dir, "tmp", "igdb_cache", "search")
            try:
                os.makedirs(cache_dir, exist_ok=True)
                cache_file = os.path.join(cache_dir, f"{clean_title}.json")
                if os.path.exists(cache_file):
                    try:
                        cache_content = await asyncio.to_thread(Path(cache_file).read_text, encoding="utf-8")
                        cached_data = json.loads(cache_content)
                        if cached_data is not None:
                            logger.info(f"[cyan]IGDB: Using cached search results for '{title}'[/cyan]")
                            return cached_data
                    except Exception:
                        pass
            except Exception:
                pass

        token = await self.get_access_token()
        if not token:
            return None

        url = "https://api.igdb.com/v4/games"
        headers = {"Client-ID": self.client_id, "Authorization": f"Bearer {token}", "Accept": "application/json", "Content-Type": "text/plain"}

        # Apicalypse query
        query = f'search "{title}"; fields name, summary, storyline, first_release_date, rating, rating_count, cover.url, screenshots.url, genres.name, platforms.name, involved_companies.company.name, involved_companies.developer, involved_companies.publisher, websites.url, websites.type, external_games.url, external_games.external_game_source, external_games.uid, language_supports.language.name, language_supports.language_support_type.name; limit 5;'

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, headers=headers, content=query)
                if resp.status_code == 200:
                    data = resp.json()
                    # Cache successful search results
                    if cache_file and data is not None:
                        try:
                            cache_content = json.dumps(data, indent=4)
                            await asyncio.to_thread(Path(cache_file).write_text, cache_content, encoding="utf-8")
                        except Exception:
                            pass
                    return data
                else:
                    logger.info(f"[red]IGDB: API request failed. Status: {resp.status_code}, Body: {resp.text}[/red]")
        except Exception as e:
            logger.info(f"[red]IGDB: Search error: {e}[/red]")
        return None

    async def fetch_game_by_id(self, igdb_id: str) -> dict[str, Any] | None:
        import asyncio
        from pathlib import Path

        igdb_id_str = igdb_id.strip()
        if not igdb_id_str.isdigit():
            logger.info(f"[red]IGDB: Invalid ID '{igdb_id}'[/red]")
            return None

        # Check local cache first (games details level)
        cache_file = None
        if self.base_dir:
            cache_dir = os.path.join(self.base_dir, "tmp", "igdb_cache", "games")
            try:
                os.makedirs(cache_dir, exist_ok=True)
                cache_file = os.path.join(cache_dir, f"{igdb_id_str}.json")
                if os.path.exists(cache_file):
                    try:
                        cache_content = await asyncio.to_thread(Path(cache_file).read_text, encoding="utf-8")
                        cached_data = json.loads(cache_content)
                        if cached_data is not None:
                            logger.info(f"[cyan]IGDB: Using cached game details for ID '{igdb_id_str}'[/cyan]")
                            return cached_data
                    except Exception:
                        pass
            except Exception:
                pass

        token = await self.get_access_token()
        if not token:
            return None

        url = "https://api.igdb.com/v4/games"
        headers = {
            "Client-ID": self.client_id,
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "text/plain"
        }

        # Apicalypse query by ID
        query = f"where id = {igdb_id_str}; fields name, summary, storyline, first_release_date, rating, rating_count, cover.url, screenshots.url, genres.name, platforms.name, involved_companies.company.name, involved_companies.developer, involved_companies.publisher, websites.url, websites.type, external_games.url, external_games.external_game_source, external_games.uid, language_supports.language.name, language_supports.language_support_type.name;"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, headers=headers, content=query)
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, list) and len(data) > 0:
                        game_data = data[0]
                        # Cache successful game details
                        if cache_file and game_data is not None:
                            try:
                                cache_content = json.dumps(game_data, indent=4)
                                await asyncio.to_thread(Path(cache_file).write_text, cache_content, encoding="utf-8")
                            except Exception:
                                pass
                        return game_data
                    else:
                        logger.info(f"[red]IGDB: No game found with ID {igdb_id_str}[/red]")
                else:
                    logger.info(f"[red]IGDB: API request failed. Status: {resp.status_code}, Body: {resp.text}[/red]")
        except Exception as e:
            logger.info(f"[red]IGDB: Fetch error: {e}[/red]")
        return None

    async def fetch_game_by_steam_id(self, steam_id: str) -> dict[str, Any] | None:
        import asyncio
        from pathlib import Path

        steam_id_str = steam_id.strip()
        if not steam_id_str.isdigit():
            logger.info(f"[red]IGDB: Invalid Steam ID '{steam_id}'[/red]")
            return None

        # Check local cache first (using steam id as cache key)
        cache_file = None
        if self.base_dir:
            cache_dir = os.path.join(self.base_dir, "tmp", "igdb_cache", "steam")
            try:
                os.makedirs(cache_dir, exist_ok=True)
                cache_file = os.path.join(cache_dir, f"{steam_id_str}.json")
                if os.path.exists(cache_file):
                    try:
                        cache_content = await asyncio.to_thread(Path(cache_file).read_text, encoding="utf-8")
                        cached_data = json.loads(cache_content)
                        if cached_data is not None:
                            logger.info(f"[cyan]IGDB: Using cached game details for Steam ID: {steam_id_str}[/cyan]")
                            return cached_data
                    except Exception:
                        pass
            except Exception:
                pass

        token = await self.get_access_token()
        if not token:
            return None

        url = "https://api.igdb.com/v4/games"
        headers = {"Client-ID": self.client_id, "Authorization": f"Bearer {token}", "Accept": "application/json", "Content-Type": "text/plain"}

        # Query games where external_games.external_game_source = 1 (Steam) and external_games.uid = steam_id_str
        query = f'where external_games.external_game_source = 1 & external_games.uid = "{steam_id_str}"; fields name, summary, storyline, first_release_date, rating, rating_count, cover.url, screenshots.url, genres.name, platforms.name, involved_companies.company.name, involved_companies.developer, involved_companies.publisher, websites.url, websites.type, external_games.url, external_games.external_game_source, external_games.uid, language_supports.language.name, language_supports.language_support_type.name;'

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, headers=headers, content=query)
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, list) and len(data) > 0:
                        game_data = data[0]
                        # Cache successful game details for Steam ID
                        if cache_file and game_data is not None:
                            try:
                                cache_content = json.dumps(game_data, indent=4)
                                await asyncio.to_thread(Path(cache_file).write_text, cache_content, encoding="utf-8")
                            except Exception:
                                pass
                        return game_data
                    else:
                        logger.info(f"[red]IGDB: No game found with Steam ID {steam_id_str}[/red]")
                else:
                    logger.info(f"[red]IGDB: API request failed. Status: {resp.status_code}, Body: {resp.text}[/red]")
        except Exception as e:
            logger.info(f"[red]IGDB: Steam Fetch error: {e}[/red]")
        return None

    async def cache_game_details(self, game_data: dict[str, Any]) -> None:
        import asyncio
        from pathlib import Path
        if not self.base_dir or not game_data or "id" not in game_data:
            return
        igdb_id = str(game_data["id"])
        cache_dir = os.path.join(self.base_dir, "tmp", "igdb_cache", "games")
        try:
            os.makedirs(cache_dir, exist_ok=True)
            cache_file = os.path.join(cache_dir, f"{igdb_id}.json")
            cache_content = json.dumps(game_data, indent=4)
            await asyncio.to_thread(Path(cache_file).write_text, cache_content, encoding="utf-8")
        except Exception:
            pass
