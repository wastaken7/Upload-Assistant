# Upload Assistant © 2026 Audionut & wastaken7 — Licensed under UAPL v1.0
import contextlib
import json
import time
from pathlib import Path
from typing import Any

import aiofiles
import httpx

from src.console import logger
from src.metadata_cache import cache_for, is_cache_miss

IGDB_SEARCH_FIELDS = "id, name, first_release_date, platforms.name"
IGDB_GAME_FIELDS = ", ".join(
    (
        "id",
        "name",
        "summary",
        "storyline",
        "first_release_date",
        "rating",
        "rating_count",
        "aggregated_rating",
        "aggregated_rating_count",
        "cover.url",
        "screenshots.url",
        "genres.name",
        "keywords.name",
        "platforms.name",
        "alternative_names.name",
        "age_ratings.organization.name",
        "age_ratings.rating_category.rating",
        "collections.name",
        "franchises.name",
        "game_engines.name",
        "game_modes.name",
        "game_status.status",
        "game_type.type",
        "multiplayer_modes.campaigncoop",
        "multiplayer_modes.dropin",
        "multiplayer_modes.lancoop",
        "multiplayer_modes.offlinecoop",
        "multiplayer_modes.offlinecoopmax",
        "multiplayer_modes.offlinemax",
        "multiplayer_modes.onlinecoop",
        "multiplayer_modes.onlinecoopmax",
        "multiplayer_modes.onlinemax",
        "multiplayer_modes.platform.name",
        "multiplayer_modes.splitscreen",
        "multiplayer_modes.splitscreenonline",
        "parent_game.name",
        "player_perspectives.name",
        "release_dates.date",
        "release_dates.human",
        "release_dates.platform.name",
        "release_dates.release_region.region",
        "release_dates.status.name",
        "themes.name",
        "version_title",
        "videos.name",
        "videos.video_id",
        "involved_companies.company.name",
        "involved_companies.developer",
        "involved_companies.publisher",
        "websites.url",
        "websites.type",
        "external_games.url",
        "external_games.external_game_source",
        "external_games.uid",
        "language_supports.language.name",
        "language_supports.language_support_type.name",
    )
)


class IGDBAPI:
    def __init__(self, client_id: str, client_secret: str, base_dir: str = ""):
        self.client_id = client_id
        self.client_secret = client_secret
        self.base_dir = base_dir
        self.token_file = Path(base_dir) / "tmp" / "igdb_cache" / "igdb_token.json" if base_dir else ""
        self.access_token = None

    async def get_access_token(self) -> str | None:
        # Try loading cached token
        if self.token_file and Path(self.token_file).exists():
            with contextlib.suppress(Exception):
                async with aiofiles.open(self.token_file, encoding="utf-8") as f:
                    content = await f.read()
                    cached = json.loads(content)
                if cached.get("expires_at", 0) > time.time() + 300:
                    self.access_token = cached.get("access_token")
                    return self.access_token

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
                        Path(self.token_file).parent.mkdir(parents=True, exist_ok=True)
                        async with aiofiles.open(self.token_file, "w", encoding="utf-8") as f:
                            await f.write(json.dumps({"access_token": self.access_token, "expires_at": expires_at}))
                    return self.access_token
                logger.info(f"[red]IGDB: Failed to authenticate with Twitch API. Status: {resp.status_code}[/red]")
        except Exception as e:
            logger.info(f"[red]IGDB: Twitch OAuth error: {e}[/red]")
        return None

    async def search_game(self, title: str) -> list[dict[str, Any]] | None:
        import re

        clean_title = re.sub(r"[^a-zA-Z0-9_\-]", "_", title).lower()

        cache = cache_for(self.base_dir)
        cached_data = await cache.get("igdb", "search_v2", clean_title)
        if not is_cache_miss(cached_data) and isinstance(cached_data, list):
            logger.info(f"[cyan]IGDB: Using cached search results for '{title}'[/cyan]")
            return cached_data

        token = await self.get_access_token()
        if not token:
            return None

        url = "https://api.igdb.com/v4/games"
        headers = {"Client-ID": self.client_id, "Authorization": f"Bearer {token}", "Accept": "application/json", "Content-Type": "text/plain"}

        # Apicalypse query
        query = f'search "{title}"; fields {IGDB_SEARCH_FIELDS}; limit 5;'

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, headers=headers, content=query)
                if resp.status_code == 200:
                    data = resp.json()
                    if data is not None:
                        await cache.set("igdb", "search_v2", clean_title, data, negative=not bool(data))
                    return data
                logger.info(f"[red]IGDB: API request failed. Status: {resp.status_code}, Body: {resp.text}[/red]")
        except Exception as e:
            logger.info(f"[red]IGDB: Search error: {e}[/red]")
        return None

    async def fetch_game_by_id(self, igdb_id: str) -> dict[str, Any] | None:

        igdb_id_str = igdb_id.strip()
        if not igdb_id_str.isdigit():
            logger.info(f"[red]IGDB: Invalid ID '{igdb_id}'[/red]")
            return None

        cache = cache_for(self.base_dir)
        cached_data = await cache.get("igdb", "game_v2", igdb_id_str)
        if not is_cache_miss(cached_data) and isinstance(cached_data, dict):
            logger.info(f"[cyan]IGDB: Using cached game details for ID '{igdb_id_str}'[/cyan]")
            return cached_data

        token = await self.get_access_token()
        if not token:
            return None

        url = "https://api.igdb.com/v4/games"
        headers = {"Client-ID": self.client_id, "Authorization": f"Bearer {token}", "Accept": "application/json", "Content-Type": "text/plain"}

        # Apicalypse query by ID
        query = f"where id = {igdb_id_str}; fields {IGDB_GAME_FIELDS};"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, headers=headers, content=query)
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, list) and len(data) > 0:
                        game_data = data[0]
                        if game_data is not None:
                            await cache.set("igdb", "game_v2", igdb_id_str, game_data)
                        return game_data
                    logger.info(f"[red]IGDB: No game found with ID {igdb_id_str}[/red]")
                else:
                    logger.info(f"[red]IGDB: API request failed. Status: {resp.status_code}, Body: {resp.text}[/red]")
        except Exception as e:
            logger.info(f"[red]IGDB: Fetch error: {e}[/red]")
        return None

    async def fetch_game_by_steam_id(self, steam_id: str) -> dict[str, Any] | None:

        steam_id_str = steam_id.strip()
        if not steam_id_str.isdigit():
            logger.info(f"[red]IGDB: Invalid Steam ID '{steam_id}'[/red]")
            return None

        cache = cache_for(self.base_dir)
        cached_data = await cache.get("igdb", "steam_v2", steam_id_str)
        if not is_cache_miss(cached_data) and isinstance(cached_data, dict):
            logger.info(f"[cyan]IGDB: Using cached game details for Steam ID: {steam_id_str}[/cyan]")
            return cached_data

        token = await self.get_access_token()
        if not token:
            return None

        url = "https://api.igdb.com/v4/games"
        headers = {"Client-ID": self.client_id, "Authorization": f"Bearer {token}", "Accept": "application/json", "Content-Type": "text/plain"}

        # Query games where external_games.external_game_source = 1 (Steam) and external_games.uid = steam_id_str
        query = f'where external_games.external_game_source = 1 & external_games.uid = "{steam_id_str}"; fields {IGDB_GAME_FIELDS};'

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, headers=headers, content=query)
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, list) and len(data) > 0:
                        game_data = data[0]
                        if game_data is not None:
                            await cache.set("igdb", "steam_v2", steam_id_str, game_data)
                        return game_data
                    logger.info(f"[red]IGDB: No game found with Steam ID {steam_id_str}[/red]")
                else:
                    logger.info(f"[red]IGDB: API request failed. Status: {resp.status_code}, Body: {resp.text}[/red]")
        except Exception as e:
            logger.info(f"[red]IGDB: Steam Fetch error: {e}[/red]")
        return None

    async def cache_game_details(self, game_data: dict[str, Any]) -> None:

        if not self.base_dir or not game_data or "id" not in game_data:
            return
        igdb_id = str(game_data["id"])
        await cache_for(self.base_dir).set("igdb", "game_v2", igdb_id, game_data)

    async def fetch_time_to_beat(self, game_id: str | int) -> dict[str, int]:
        """Return IGDB's completion-time estimates in seconds."""
        game_id_str = str(game_id).strip()
        if not game_id_str.isdigit():
            return {}

        cache = cache_for(self.base_dir)
        cached_data = await cache.get("igdb", "time_to_beat_v1", game_id_str)
        if not is_cache_miss(cached_data) and isinstance(cached_data, dict):
            return {key: int(value) for key, value in cached_data.items() if key in {"hastily", "normally", "completely"} and isinstance(value, int)}

        token = await self.get_access_token()
        if not token:
            return {}

        url = "https://api.igdb.com/v4/game_time_to_beats"
        headers = {"Client-ID": self.client_id, "Authorization": f"Bearer {token}", "Accept": "application/json", "Content-Type": "text/plain"}
        query = f"where game_id = {game_id_str}; fields hastily, normally, completely, count; limit 1;"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, headers=headers, content=query)
            if resp.status_code != 200:
                logger.info(f"[red]IGDB: Time-to-beat request failed. Status: {resp.status_code}[/red]")
                return {}
            data = resp.json()
            item = data[0] if isinstance(data, list) and data and isinstance(data[0], dict) else {}
            result = {key: int(item[key]) for key in ("hastily", "normally", "completely") if isinstance(item.get(key), int) and item[key] > 0}
            await cache.set("igdb", "time_to_beat_v1", game_id_str, result, negative=not result)
            return result
        except (httpx.HTTPError, ValueError, TypeError) as error:
            logger.info(f"[yellow]IGDB: Time-to-beat lookup failed: {error}[/yellow]")
            return {}
