# Upload Assistant © 2026 Audionut & wastaken7 — Licensed under UAPL v1.0
"""Read-only GazelleGames metadata access for game preparation."""

from __future__ import annotations

import asyncio
import html
import json
import math
import re
import time
import urllib.parse
from collections import deque
from typing import Any

import httpx

from src.console import logger
from src.metadata_cache import cache_for, is_cache_miss

GGN_COLOR = "[#399cff]GazelleGames[/#399cff]"


def _monotonic() -> float:
    return time.monotonic()


def _decoded_url(value: Any) -> str:
    """Normalize percent-encoded and ``[inlineurl]`` API URL values."""
    text = str(value or "").strip()
    match = re.fullmatch(r"\[inlineurl\](.*?)\[/inlineurl\]", text, flags=re.IGNORECASE | re.DOTALL)
    return urllib.parse.unquote(match.group(1) if match else text).strip()


def _collection_names(group: dict[str, Any], collection_type: str) -> str:
    return ", ".join(_collection_name_list(group, collection_type))


def _collection_name_list(group: dict[str, Any], collection_type: str) -> list[str]:
    collections = group.get("specialCollections")
    if not isinstance(collections, dict):
        return []
    entries = collections.get(collection_type, [])
    if not isinstance(entries, list):
        return []
    names = [str(name).strip() for entry in entries if isinstance(entry, dict) and (name := entry.get("Name")) is not None and str(name).strip()]
    return list(dict.fromkeys(names))


def _clean_release_notes(value: Any) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\[/?(?:align|b|center|code|color|font|h\d|i|img|quote|size|spoiler|u|url)(?:=[^\]]*)?\]", "", text, flags=re.IGNORECASE)
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


def _normalized_age_rating(value: Any) -> dict[str, str]:
    rating = str(value or "").strip().upper()
    pegi_ids = {"1": "3", "3": "7", "5": "12", "7": "16", "9": "18"}
    if rating in pegi_ids:
        return {"PEGI": pegi_ids[rating]}
    if rating in {"3+", "7+", "12+", "16+", "18+"}:
        return {"PEGI": rating.removesuffix("+")}
    if rating in {"EC", "E", "E10", "E10+", "T", "M", "AO", "RP"}:
        return {"ESRB": rating}
    return {}


def _normalized_rating(value: Any, *, maximum: int) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    try:
        score = float(value.get("score"))
    except TypeError, ValueError:
        return None
    if not math.isfinite(score) or score < 0 or score > maximum:
        return None
    result: dict[str, Any] = {"score": score, "max": maximum}
    link = _decoded_url(value.get("link"))
    if link.startswith(("http://", "https://")):
        result["url"] = link
    return result


class GazelleGamesManager:
    """Fetch and normalize metadata without exposing GazelleGames as an upload tracker."""

    base_url = "https://gazellegames.net/api.php"
    provider = "gazellegames"

    def __init__(self) -> None:
        self._rate_lock = asyncio.Lock()
        self._request_times: deque[float] = deque()

    @staticmethod
    def extract_torrent_id(torrent_comments: Any) -> str | None:
        """Return a GGN torrent ID only from a canonical torrent details URL."""
        if not isinstance(torrent_comments, list):
            return None
        for entry in torrent_comments:
            if not isinstance(entry, dict):
                continue
            comment = str(entry.get("comment", "") or "")
            for candidate in re.findall(r"https?://[^\s\"'<>]+", comment, flags=re.IGNORECASE):
                parsed = urllib.parse.urlparse(candidate.rstrip("),.;]"))
                host = (parsed.hostname or "").lower().rstrip(".")
                if host != "gazellegames.net" and not host.endswith(".gazellegames.net"):
                    continue
                if parsed.path.rstrip("/").lower() != "/torrents.php":
                    continue
                torrent_id = (urllib.parse.parse_qs(parsed.query).get("torrentid") or [""])[0]
                if str(torrent_id).isdigit():
                    return str(torrent_id)
        return None

    async def _wait_for_rate_slot(self) -> None:
        """Keep this process within GGN's five-requests-per-ten-seconds rule."""
        async with self._rate_lock:
            while True:
                now = _monotonic()
                while self._request_times and now - self._request_times[0] >= 10.0:
                    self._request_times.popleft()
                if len(self._request_times) < 5:
                    self._request_times.append(now)
                    return
                await asyncio.sleep(max(0.01, 10.0 - (now - self._request_times[0])))

    async def _request(self, params: dict[str, str], api_key: str) -> dict[str, Any] | None:
        if not api_key:
            return None
        await self._wait_for_rate_slot()
        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                response = await client.get(self.base_url, params=params, headers={"X-API-Key": api_key})
            if response.status_code in (401, 403):
                logger.info(f"{GGN_COLOR}: [bold red]API key was rejected (HTTP {response.status_code}).[/bold red]")
                return None
            if response.status_code == 404:
                return {}
            if response.status_code != 200:
                logger.info(f"{GGN_COLOR}: [red]API returned HTTP {response.status_code}.[/red]")
                return None
            payload = response.json()
            if not isinstance(payload, dict) or payload.get("status") != "success":
                logger.debug(f"{GGN_COLOR}: API returned an invalid or unsuccessful response")
                return None
            response_data = payload.get("response")
            if response_data == []:
                return {}
            if not isinstance(response_data, dict):
                logger.debug(f"{GGN_COLOR}: API returned an invalid response body")
                return None
            return response_data
        except (httpx.HTTPError, ValueError, TypeError) as error:
            logger.info(f"{GGN_COLOR}: [yellow]API lookup failed: {error}[/yellow]")
            return None

    async def fetch_group(self, group_id: str | int, *, base_dir: str, api_key: str, config: dict[str, Any] | None = None) -> dict[str, Any] | None:
        clean_id = str(group_id).strip()
        if not clean_id.isdigit():
            return None
        cache = cache_for(base_dir, config)
        cached = await cache.get(self.provider, "group", clean_id)
        if not is_cache_miss(cached) and isinstance(cached, dict):
            return None if cached.get("not_found") else cached

        response = await self._request({"request": "torrentgroup", "id": clean_id}, api_key)
        if response is None:
            return None
        group = response.get("group") if isinstance(response, dict) else None
        if isinstance(group, dict) and group:
            await cache.set(self.provider, "group", clean_id, group)
            return group
        await cache.set(self.provider, "group", clean_id, {"not_found": True}, negative=True)
        return None

    async def fetch_torrent(self, torrent_id: str | int, *, base_dir: str, api_key: str, config: dict[str, Any] | None = None) -> dict[str, Any] | None:
        clean_id = str(torrent_id).strip()
        if not clean_id.isdigit():
            return None
        cache = cache_for(base_dir, config)
        cached = await cache.get(self.provider, "torrent", clean_id)
        if not is_cache_miss(cached) and isinstance(cached, dict):
            return None if cached.get("not_found") else cached

        response = await self._request({"request": "torrent", "id": clean_id}, api_key)
        if response is None:
            return None
        basic_group = response.get("group") if isinstance(response, dict) else None
        torrent = response.get("torrent") if isinstance(response, dict) else None
        if not isinstance(basic_group, dict) or not isinstance(torrent, dict):
            await cache.set(self.provider, "torrent", clean_id, {"not_found": True}, negative=True)
            return None

        group_id = basic_group.get("id")
        detailed_group = await self.fetch_group(group_id, base_dir=base_dir, api_key=api_key, config=config) if group_id else None
        result = {"group": detailed_group or basic_group, "torrent": torrent}
        if detailed_group or not group_id:
            await cache.set(self.provider, "torrent", clean_id, result)
        return result

    async def search_groups(
        self,
        title: str,
        *,
        base_dir: str,
        api_key: str,
        config: dict[str, Any] | None = None,
        year: str | int | None = None,
    ) -> list[dict[str, Any]]:
        clean_title = " ".join(title.split()).strip()
        if not clean_title:
            return []
        params = {
            "request": "search",
            "search_type": "torrents",
            "groupname": clean_title,
            "filter_cat[1]": "1",
            "order_by": "relevance",
        }
        if str(year or "").isdigit():
            params["year"] = str(year)
        cache_key = json.dumps(params, sort_keys=True)
        cache = cache_for(base_dir, config)
        cached = await cache.get(self.provider, "search", cache_key)
        if not is_cache_miss(cached) and isinstance(cached, list):
            return [entry for entry in cached if isinstance(entry, dict)]

        response = await self._request(params, api_key)
        if response is None:
            return []
        results = [entry for entry in response.values() if isinstance(entry, dict) and str(entry.get("CategoryID", entry.get("categoryid", ""))) == "1"] if response else []
        await cache.set(self.provider, "search", cache_key, results, negative=not results)
        return results

    @staticmethod
    def normalize_metadata(payload: dict[str, Any], *, exact_torrent: bool) -> dict[str, Any]:
        """Map GGN's group/torrent response into Upload Assistant game fields."""
        group = payload.get("group") if isinstance(payload.get("group"), dict) else payload
        if not isinstance(group, dict):
            return {}
        metadata: dict[str, Any] = {}

        title = str(group.get("name") or group.get("Name") or "").strip()
        if title:
            metadata["title"] = title
        year = group.get("year") or group.get("Year")
        try:
            normalized_year = int(year)
        except TypeError, ValueError:
            normalized_year = 0
        if normalized_year > 0:
            metadata["year"] = normalized_year
            metadata["search_year"] = normalized_year
        platform = str(group.get("platform") or "").strip()
        artists = group.get("Artists", [])
        artist_platforms = (
            [str(item.get("name", "")).strip() for item in artists if isinstance(item, dict) and str(item.get("name", "")).strip()] if isinstance(artists, list) else []
        )
        if not platform and artist_platforms:
            platform = artist_platforms[0]
        if platform:
            metadata["platform"] = platform
            metadata["available_platforms"] = list(dict.fromkeys([platform, *artist_platforms]))

        overview = str(group.get("wikiBody") or group.get("bbWikiBody") or "").strip()
        if overview:
            metadata["overview"] = overview
        raw_genres = group.get("TagList") or []
        genre_tags = raw_genres.split() if isinstance(raw_genres, str) else raw_genres if isinstance(raw_genres, list) else []
        genres = [str(tag).replace(".", " ").replace("_", " ").strip().title() for tag in genre_tags if str(tag).strip()]
        if genres:
            metadata["genres"] = list(dict.fromkeys(genres))
        raw_tags = group.get("tags") or group.get("FullTagList") or raw_genres or []
        tags = raw_tags.replace("|", " ").split() if isinstance(raw_tags, str) else raw_tags if isinstance(raw_tags, list) else []
        keywords = [str(tag).replace(".", " ").replace("_", " ").strip().title() for tag in tags if str(tag).strip()]
        if keywords:
            metadata["keywords"] = list(dict.fromkeys(keywords))

        developer = _collection_names(group, "Developer")
        publisher = _collection_names(group, "Publisher")
        if developer:
            metadata["developer"] = developer
        if publisher:
            metadata["publisher"] = publisher

        game_info = group.get("gameInfo") if isinstance(group.get("gameInfo"), dict) else group
        aliases = group.get("aliases")
        if isinstance(aliases, list):
            metadata["game_aliases"] = list(dict.fromkeys(str(alias).strip() for alias in aliases if str(alias).strip()))

        rating = game_info.get("rating") or group.get("rating") or group.get("Rating")
        age_ratings = _normalized_age_rating(rating)
        if age_ratings:
            metadata["game_age_ratings"] = age_ratings

        rating_sources = {
            "Metacritic": (game_info.get("metaRating") or group.get("metaRating"), 100),
            "IGN": (game_info.get("ignRating") or group.get("ignRating"), 10),
            "GameSpot": (game_info.get("gamespotRating") or group.get("gamespotRating"), 10),
        }
        game_ratings = {name: normalized for name, (raw, maximum) in rating_sources.items() if (normalized := _normalized_rating(raw, maximum=maximum))}
        if game_ratings:
            metadata["game_ratings"] = game_ratings

        collection_fields = {
            "game_designers": "Designer",
            "game_composers": "Composer",
            "game_engines": "Engine",
            "game_features": "Feature",
            "game_franchises": "Franchise",
        }
        for field, collection_type in collection_fields.items():
            values = _collection_name_list(group, collection_type)
            if values:
                metadata[field] = values

        links = game_info.get("weblinks", {}) if isinstance(game_info, dict) else {}
        if isinstance(links, dict):
            steam_url = _decoded_url(links.get("Steam"))
            if steam_url.startswith(("http://", "https://")):
                metadata["steam_url"] = steam_url
            official_url = _decoded_url(links.get("GamesWebsite"))
            if official_url.startswith(("http://", "https://")):
                metadata["game_official_url"] = official_url
        trailer_url = _decoded_url(game_info.get("trailer") or group.get("trailer"))
        if trailer_url.startswith(("http://", "https://")):
            metadata["youtube"] = trailer_url

        if not exact_torrent:
            return metadata

        torrent = payload.get("torrent")
        if not isinstance(torrent, dict):
            return metadata
        version = str(torrent.get("gameDOXVersion") or torrent.get("GameDOXVers") or "").strip()
        if version and version.casefold() not in {"unknown", "n/a", "none", "0"}:
            metadata["game_version"] = version
        dox_type = str(torrent.get("gameDOXType") or torrent.get("GameDOXType") or "").strip().casefold()
        release_type = str(torrent.get("releaseType") or torrent.get("Miscellaneous") or "").strip()
        if dox_type == "dlc":
            metadata["game_subcategory"] = "dlc"
        elif dox_type == "update":
            metadata["game_subcategory"] = "update"
        elif release_type and release_type.casefold() != "gamedox":
            metadata["game_subcategory"] = "full_game"
        language = str(torrent.get("language") or torrent.get("Language") or "").strip()
        if language and language.casefold() not in {"multi-language", "other"}:
            metadata["languages"] = {language: []}
        region = str(torrent.get("region") or torrent.get("Region") or "").strip()
        if region:
            metadata["game_region"] = region
        release_title = str(torrent.get("releaseTitle") or torrent.get("ReleaseTitle") or "").strip()
        if release_title:
            metadata["game_release_title"] = release_title
        if release_type:
            metadata["game_release_type"] = release_type
        edition = str(torrent.get("remasterTitle") or torrent.get("RemasterTitle") or "").strip()
        if edition:
            metadata["game_release_edition"] = edition
        try:
            edition_year = int(torrent.get("remasterYear") or torrent.get("RemasterYear") or 0)
        except TypeError, ValueError:
            edition_year = 0
        if edition_year > 0:
            metadata["game_release_edition_year"] = edition_year
        scene = torrent.get("scene", torrent.get("Scene"))
        if isinstance(scene, bool):
            metadata["game_release_scene"] = scene
        elif str(scene).strip() in {"0", "1"}:
            metadata["game_release_scene"] = str(scene).strip() == "1"
        notes = _clean_release_notes(torrent.get("bbDescription") or torrent.get("description"))
        if notes:
            metadata["game_release_notes"] = notes
        return metadata


gazellegames_manager = GazelleGamesManager()
