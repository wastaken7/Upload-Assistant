# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
# Restricted-use credential — permitted only under UAPL v1.0 and associated service provider terms
import asyncio
import contextlib
import json
import os
import re
import ssl
from pathlib import Path
from typing import Any, cast
from urllib.error import URLError

import httpx

from src.console import logger
from src.metadata_cache import cache_for, is_cache_miss

YEAR_PATTERN = re.compile(r"\((19\d\d|20[0-3]\d)\)")


tvdb: TVDB | None = None
_tvdb_init_error: Exception | None = None
_tvdb_error_reported = False


def _coerce_int(value: Any) -> int | None:
    try:
        return int(value)
    except TypeError, ValueError:
        return None


def _as_dict_list(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [cast(dict[str, Any], item) for item in value if isinstance(item, dict)]
    return []


def _english_alias_names(aliases: list[dict[str, Any]]) -> list[str]:
    return [str(alias.get("name", "")).strip() for alias in aliases if alias.get("language") == "eng" and str(alias.get("name", "")).strip()]


def _pick_eng_alias(
    aliases: list[dict[str, Any]],
) -> str | None:
    if not aliases:
        return None

    eng_aliases = _english_alias_names(aliases)
    if not eng_aliases:
        return None

    eng_alias = eng_aliases[-1]
    logger.debug(f"[blue]English alias: {eng_alias}[/blue]")
    return eng_alias


def _extract_year_from_text(value: Any) -> str | None:
    if not isinstance(value, (str, int)):
        return None

    match = re.search(r"(19\d\d|20[0-3]\d)", str(value))
    return match.group(1) if match else None


def _best_effort_series_year(series_info: dict[str, Any] | None) -> str | None:
    if not series_info:
        return None

    return _extract_year_from_text(series_info.get("year")) or _extract_year_from_text(series_info.get("slug"))


async def _series_translation_metadata(
    client: Any,
    series_id: int,
    aliases: list[dict[str, Any]],
    _series_info: dict[str, Any] | None = None,
) -> dict[str, str | None]:
    translation_name: str | None = None
    translation_aliases: list[str] = []

    try:
        translation = await client.get_series_translation(series_id, "eng")
        name = translation.get("name")
        if isinstance(name, str) and name.strip():
            translation_name = name.strip()
        aliases_value = translation.get("aliases")
        if isinstance(aliases_value, list):
            translation_aliases = [str(alias).strip() for alias in aliases_value if str(alias).strip()]
    except Exception as translation_error:
        logger.debug(f"[yellow]Could not retrieve TVDB English series translation: {translation_error}[/yellow]")

    extended_eng_aliases = _english_alias_names(aliases)
    english_aliases = translation_aliases + extended_eng_aliases
    fallback_title = translation_aliases[-1] if translation_aliases else _pick_eng_alias(aliases)
    title = translation_name or fallback_title
    year = None
    for alias in english_aliases:
        year = _extract_year_from_text(alias)
        if year:
            break
    if not english_aliases:
        year = _best_effort_series_year(_series_info)

    if title:
        logger.debug(f"[blue]TVDB English series title: {title}" + (f" ({year})" if year else "") + "[/blue]")

    return {
        "series_title": title,
        "series_year": year,
    }


class TVDB:
    def __init__(self, apikey: str):
        self.apikey = apikey
        self.token = None
        self.base_url = "https://api4.thetvdb.com/v4"
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=15.0)
        self._login_lock = asyncio.Lock()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def login(self) -> bool:
        async with self._login_lock:
            try:
                resp = await self._client.post("/login", json={"apikey": self.apikey})
                resp.raise_for_status()
                data = resp.json()
                self.token = data.get("data", {}).get("token")
                if self.token:
                    self._client.headers.update({"Authorization": f"Bearer {self.token}"})
                    return True
                return False
            except Exception as e:
                logger.error(f"[red]TVDB login failed: {e}[/red]")
                return False

    async def _request(self, method: str, endpoint: str, **kwargs) -> Any:
        if not self.token:
            success = await self.login()
            if not success:
                raise RuntimeError("TVDB authentication failed")

        try:
            resp = await self._client.request(method, endpoint, **kwargs)
            if resp.status_code == 401:
                logger.debug("[yellow]TVDB token expired. Refreshing...[/yellow]")
                success = await self.login()
                if not success:
                    raise RuntimeError("TVDB authentication refresh failed")
                resp = await self._client.request(method, endpoint, **kwargs)

            resp.raise_for_status()
            payload = resp.json()
            if not isinstance(payload, dict) or "data" not in payload:
                raise ValueError("TVDB response did not contain data")
            return payload["data"]
        except Exception as e:
            logger.debug(f"[red]TVDB API request failed: {e}[/red]")
            raise

    async def search(self, query, **kwargs) -> list[dict[str, Any]]:
        # Handle the case where `{filename}` is passed as a set
        if isinstance(query, set):
            query = next(iter(query))
        params = {"query": query}
        params.update(kwargs)
        res = await self._request("GET", "/search", params=params)
        if not isinstance(res, list):
            raise TypeError("TVDB search response data was not a list")
        return res

    async def search_by_remote_id(self, remoteid: str) -> list[dict[str, Any]]:
        res = await self._request("GET", f"/search/remoteid/{remoteid}")
        if not isinstance(res, list):
            raise TypeError("TVDB remote ID search response data was not a list")
        return res

    async def get_series_extended(self, id: int, **kwargs) -> dict[str, Any]:
        res = await self._request("GET", f"/series/{id}/extended", params=kwargs)
        if not isinstance(res, dict):
            raise TypeError("TVDB extended series response data was not a dictionary")
        return res

    async def get_series_episodes(self, id: int, season_type="default", page=0, lang=None, **kwargs) -> dict[str, Any]:
        url = f"/series/{id}/episodes/{season_type}"
        if lang:
            url += f"/{lang}"
        params = {"page": page}
        params.update(kwargs)
        res = await self._request("GET", url, params=params)
        if not isinstance(res, dict):
            raise TypeError("TVDB series episodes response data was not a dictionary")
        return res

    async def get_episode_extended(self, id: int, **kwargs) -> dict[str, Any]:
        res = await self._request("GET", f"/episodes/{id}/extended", params=kwargs)
        if not isinstance(res, dict):
            raise TypeError("TVDB extended episode response data was not a dictionary")
        return res

    async def get_series_translation(self, id: int, lang: str, **kwargs) -> dict[str, Any]:
        res = await self._request("GET", f"/series/{id}/translations/{lang}", params=kwargs)
        if not isinstance(res, dict):
            raise TypeError("TVDB series translation response data was not a dictionary")
        return res


async def close_tvdb() -> None:
    global tvdb

    client = tvdb
    tvdb = None
    if client is not None:
        await client.aclose()


def _get_tvdb_or_warn(config: dict[str, Any] | None = None) -> TVDB | None:
    global tvdb, _tvdb_error_reported, _tvdb_init_error

    if tvdb is not None:
        return tvdb

    # Extract key from passed config
    tvdb_api_key = ""
    if isinstance(config, dict):
        tvdb_api_key = config.get("DEFAULT", {}).get("tvdb_api", "")

    # Fallback to importing data.config if not found in the passed config
    if not tvdb_api_key:
        with contextlib.suppress(Exception):
            from data.config import config as imported_config

            if isinstance(imported_config, dict):
                tvdb_api_key = imported_config.get("DEFAULT", {}).get("tvdb_api", "")

    if not isinstance(tvdb_api_key, str) or not tvdb_api_key.strip():
        if not _tvdb_error_reported:
            _tvdb_error_reported = True
            logger.info("[yellow]TVDB API key is missing in config.py under DEFAULT section. Continuing without TVDB.[/yellow]")
        return None

    try:
        tvdb = TVDB(tvdb_api_key.strip())
    except (ssl.SSLError, URLError) as e:
        _tvdb_init_error = e
    except Exception as e:
        _tvdb_init_error = e

    if tvdb is not None:
        return tvdb

    if not _tvdb_error_reported:
        _tvdb_error_reported = True
        if _tvdb_init_error:
            logger.info(f"[yellow]TVDB login failed; continuing without TVDB. Reason: {_tvdb_init_error}[/yellow]")
            logger.info(
                "[yellow]This is usually a local Python CA/cert issue. "
                "Fix options: install/update Windows roots, or set SSL_CERT_FILE to certifi's bundle "
                '(e.g. `python -c "import certifi; print(certifi.where())"`).[/yellow]'
            )
        else:
            logger.info("[yellow]TVDB unavailable; continuing without TVDB.[/yellow]")

    return None


class TvdbData:
    def __init__(self, config: Any) -> None:
        self.config = config

    async def search_tvdb_series(
        self,
        filename: str,
        year: str | None = None,
    ) -> tuple[list[dict[str, Any]] | None, int | None]:
        logger.debug(f"filename for TVDB search: {filename} year: {year}")
        client = _get_tvdb_or_warn(self.config)
        if client is None:
            return None, None

        cache = cache_for(base_dir="", config=self.config)
        cache_key = f"{filename}_{year}" if year else filename
        cached = await cache.get("tvdb", "search", cache_key)
        if not is_cache_miss(cached) and (cached is None or isinstance(cached, list)):
            results = cached
        else:
            results = await client.search(filename, year=year, type="series", lang="eng")
            await cache.set("tvdb", "search", cache_key, results, negative=not bool(results))

        try:
            if results and len(results) > 0:
                # Try to find the best match based on year
                best_match: dict[str, Any] | None = None
                search_year = year if year else ""

                if search_year:
                    # First, try to find exact year match
                    for result in results:
                        if result.get("year") == search_year:
                            best_match = result
                            break

                # If no exact match, check aliases for year-based names
                if not best_match and search_year:
                    for result in results:
                        aliases_raw = result.get("aliases", [])
                        aliases = aliases_raw if isinstance(aliases_raw, list) else []
                        if aliases:
                            # Check if any alias contains the year in parentheses
                            for alias in aliases:
                                alias_name = str(cast(dict[str, Any], alias).get("name", "")) if isinstance(alias, dict) else str(alias)
                                if f"({search_year})" in alias_name:
                                    best_match = result
                                    break
                            if best_match:
                                break

                # If still no match, use first result
                if not best_match:
                    best_match = results[0]

                series_id = best_match["tvdb_id"] if best_match else None
                logger.debug(f"[blue]TVDB series ID: {series_id}[/blue]")
                return results, _coerce_int(series_id)
            logger.info("[yellow]No TVDB results found[/yellow]")
            return None, None
        except Exception as e:
            logger.error(f"[red]Error: {e}[/red]")
            return None, None

    async def get_tvdb_episodes(
        self,
        series_id: int | str,
        base_dir: str | bool | None = None,
        season: int | str | None = None,
        episode: int | str | None = None,
        absolute_number: int | str | None = None,
        aired_date: str | None = None,
        original_language: str | None = None,
    ) -> tuple[dict[str, Any] | None, str | None]:
        # Backward compat: older call sites used (series_id, debug)
        if isinstance(base_dir, bool):
            base_dir = None

        def _episode_is_present(episodes: list[dict[str, Any]]) -> bool:
            if not episodes:
                return False

            # If no specific episode requested, any cached payload is acceptable.
            if season is None and episode is None and absolute_number is None and not aired_date:
                return True

            aired_norm = None
            if aired_date:
                aired_norm = aired_date.strip().replace(".", "-")

            # Normalize numeric inputs
            try:
                season_int = int(season) if season is not None else None
            except TypeError, ValueError:
                season_int = None

            try:
                episode_int = int(episode) if episode is not None else None
            except TypeError, ValueError:
                episode_int = None

            try:
                absolute_int = int(absolute_number) if absolute_number is not None else None
            except TypeError, ValueError:
                absolute_int = None

            # For daily-style episodes, match by aired date.
            if aired_norm:
                for ep in episodes:
                    if ep.get("aired") == aired_norm:
                        return True

            # Treat episode==0/None as "no specific episode" (season packs, etc.)
            if episode_int in (None, 0) and absolute_int is None and not aired_norm:
                return True

            for ep in episodes:
                if absolute_int is not None and ep.get("absoluteNumber") == absolute_int:
                    return True

                if season_int is not None and episode_int not in (None, 0) and ep.get("seasonNumber") == season_int and ep.get("number") == episode_int:
                    return True

            return False

        series_id_int = _coerce_int(series_id)
        if series_id_int is None:
            logger.debug(f"[yellow]Invalid TVDB series ID: {series_id}[/yellow]")
            return None, None

        cache_path = None
        if isinstance(base_dir, str) and base_dir:
            try:
                cache_dir = Path(base_dir) / "data" / "tvdb"
                cache_path = cache_dir / f"{series_id_int}.json"

                if cache_path.exists():
                    with cache_path.open("r", encoding="utf-8") as f:
                        cached = json.load(f)

                    if isinstance(cached, dict):
                        cached_dict = cast(dict[str, Any], cached)
                        cached_episodes = _as_dict_list(cached_dict.get("episodes", []))
                        if not cached_episodes and not isinstance(cached_dict.get("episodes", []), list):
                            cached_episodes = []
                        if not _episode_is_present(cached_episodes):
                            logger.debug(f"[yellow]Cached TVDB data for {series_id_int} does not include requested episode; refreshing from TVDB[/yellow]")
                        else:
                            logger.debug(f"[cyan]Using cached TVDB episodes for {series_id_int}[/cyan]")

                            episodes_data: dict[str, Any] = {
                                "episodes": cached_episodes,
                                "aliases": cached_dict.get("aliases", []) if isinstance(cached_dict.get("aliases", []), list) else [],
                                "slug": cached_dict.get("slug") if isinstance(cached_dict.get("slug"), str) else None,
                                "series_title": cached_dict.get("series_title") if isinstance(cached_dict.get("series_title"), str) else None,
                                "series_year": cached_dict.get("series_year") if isinstance(cached_dict.get("series_year"), str) else None,
                            }

                            if not episodes_data.get("series_title") and not episodes_data.get("series_year"):
                                client = _get_tvdb_or_warn(self.config)
                                if client is not None:
                                    try:
                                        series_info = await client.get_series_extended(series_id_int)
                                        aliases_list = _as_dict_list(series_info.get("aliases", episodes_data.get("aliases")))
                                        series_metadata = await _series_translation_metadata(
                                            client,
                                            series_id_int,
                                            aliases_list,
                                            _series_info=series_info,
                                        )
                                        episodes_data.update(series_metadata)
                                    except Exception as series_error:
                                        logger.debug(f"[yellow]Could not refresh cached TVDB series metadata: {series_error}[/yellow]")

                            specific_alias = episodes_data.get("series_title") if isinstance(episodes_data.get("series_title"), str) else None
                            if original_language and original_language == "en":
                                specific_alias = None

                            return episodes_data, specific_alias
            except Exception as cache_error:
                logger.debug(f"[yellow]Failed to read TVDB cache for {series_id}: {cache_error}[/yellow]")

        try:
            client = _get_tvdb_or_warn(self.config)
            if client is None:
                return None, None

            # Get all episodes for the series with pagination
            all_episodes: list[dict[str, Any]] = []
            page = 0
            max_pages = 20  # Safety limit to prevent infinite loops
            pages_fetched = 0
            series_slug: str | None = None

            while page < max_pages:
                if page > 0:
                    logger.debug(f"[cyan]Fetching TVDB episodes page {page + 1}[/cyan]")

                try:
                    episodes_response = await client.get_series_episodes(series_id_int, season_type="default", page=page, lang="eng")

                    # Handle both dict response and direct episodes list
                    if isinstance(episodes_response, dict):
                        episodes_response_dict = cast(dict[str, Any], episodes_response)
                        if page == 0:
                            slug_value = episodes_response_dict.get("slug")
                            if isinstance(slug_value, str):
                                series_slug = slug_value
                        current_episodes = _as_dict_list(episodes_response_dict.get("episodes", []))
                    else:
                        # Fallback for direct list response
                        current_episodes = _as_dict_list(episodes_response)

                    if not current_episodes:
                        logger.debug(f"[yellow]No episodes found on page {page + 1}, stopping pagination[/yellow]")
                        break

                    all_episodes.extend(current_episodes)
                    pages_fetched += 1

                    logger.debug(f"[cyan]Retrieved {len(current_episodes)} episodes from page {page + 1} (total: {len(all_episodes)})[/cyan]")

                    # If we got fewer than 500 results, we've reached the end
                    if len(current_episodes) < 500:
                        logger.debug(f"[cyan]Page {page + 1} returned {len(current_episodes)} episodes (< 500), pagination complete[/cyan]")
                        break

                    page += 1
                    await asyncio.sleep(0.1)  # Rate limiting

                except Exception as page_error:
                    logger.debug(f"[yellow]Error fetching page {page + 1}: {page_error}[/yellow]")
                    # If first page fails, re-raise; otherwise, stop pagination
                    if page == 0:
                        raise page_error
                    break

            logger.debug(f"[green]Total episodes retrieved: {len(all_episodes)} across {page + 1} page(s)[/green]")

            # Create the response structure
            episodes_data: dict[str, Any] = {
                "episodes": all_episodes,
                "aliases": [],  # Will be populated if available from first response
                "slug": series_slug,
                "series_title": None,
                "series_year": None,
            }

            # Try to get aliases from series info (may need separate call)
            try:
                if all_episodes:
                    # Get series details for aliases
                    series_info = await client.get_series_extended(series_id_int)
                    if "aliases" in series_info:
                        episodes_data["aliases"] = series_info["aliases"]
                    aliases_list = _as_dict_list(episodes_data["aliases"])
                    episodes_data.update(
                        await _series_translation_metadata(
                            client,
                            series_id_int,
                            aliases_list,
                            _series_info=series_info,
                        )
                    )
            except Exception as alias_error:
                logger.debug(f"[yellow]Could not retrieve series aliases: {alias_error}[/yellow]")

            # If this was a multi-page series and we have a base_dir, cache results for next time.
            if cache_path and pages_fetched > 1:
                try:
                    # Ensure cache dir exists; on POSIX explicitly apply typical dir perms.
                    if os.name == "posix":
                        cache_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                        with contextlib.suppress(Exception):
                            Path(cache_path.parent).chmod(0o700)
                    else:
                        cache_path.parent.mkdir(parents=True, exist_ok=True)

                    with cache_path.open("w", encoding="utf-8") as f:
                        json.dump(episodes_data, f, ensure_ascii=False)

                    if os.name == "posix":
                        with contextlib.suppress(Exception):
                            Path(cache_path).chmod(0o644)
                    logger.debug(f"[green]Cached TVDB episodes to {cache_path}[/green]")
                except Exception as cache_write_error:
                    logger.debug(f"[yellow]Failed to write TVDB cache for {series_id}: {cache_write_error}[/yellow]")

            specific_alias = episodes_data.get("series_title") if isinstance(episodes_data.get("series_title"), str) else None
            if original_language and original_language == "en":
                specific_alias = None

            return episodes_data, specific_alias

        except Exception as e:
            logger.error(f"[red]Error getting episodes: {e}[/red]")
            return None, None

    async def get_tvdb_by_external_id(
        self,
        imdb: int | str | None,
        tmdb: int | str | None,
        tv_movie: bool = False,
    ) -> tuple[int | None, str | None]:
        client = _get_tvdb_or_warn(self.config)
        if client is None:
            return None, None

        async def _translated_series_name(series_id_value: Any, fallback: Any) -> str | None:
            series_id_int = _coerce_int(series_id_value)
            fallback_name = str(fallback).strip() if fallback else None
            if series_id_int is None:
                return fallback_name
            cache = cache_for(base_dir="", config=self.config)
            cache_key = f"translation_{series_id_int}"
            cached = await cache.get("tvdb", "series_extended", cache_key)
            if not is_cache_miss(cached) and isinstance(cached, dict):
                return cached.get("series_title") or fallback_name

            try:
                series_info = await client.get_series_extended(series_id_int)
                aliases = _as_dict_list(series_info.get("aliases", []))
                series_metadata = await _series_translation_metadata(
                    client,
                    series_id_int,
                    aliases,
                    _series_info=series_info,
                )
                title = series_metadata.get("series_title")
                await cache.set("tvdb", "series_extended", cache_key, {"series_title": title})
                return title or fallback_name
            except Exception as series_error:
                logger.debug(f"[yellow]Could not retrieve translated TVDB series name: {series_error}[/yellow]")
                return fallback_name

        # Try IMDB first if available
        if imdb:
            try:
                if isinstance(imdb, str) and imdb.startswith("tt"):
                    imdb_formatted = imdb
                elif isinstance(imdb, str) and imdb.isdigit():
                    imdb_formatted = f"tt{int(imdb):07d}"
                elif isinstance(imdb, int):
                    imdb_formatted = f"tt{imdb:07d}"
                else:
                    imdb_formatted = imdb

                logger.debug(f"[cyan]Trying TVDB lookup with IMDB ID: {imdb_formatted}[/cyan]")

                results = await client.search_by_remote_id(imdb_formatted)

                if results and len(results) > 0:
                    logger.debug(f"[blue]results: {results}[/blue]")

                    # Look for series results first
                    for result in results:
                        if "series" in result and isinstance(result.get("series"), dict):
                            series_id = result["series"]["id"]
                            series_name = await _translated_series_name(series_id, result["series"].get("name"))
                            logger.debug(f"[blue]TVDB series ID from IMDB: {series_id}[/blue]")
                            return _coerce_int(series_id), series_name

                    # If tv_movie is True, check for episode with seriesId first, then movie
                    if tv_movie:
                        # Check if any result has an episode with a seriesId
                        for result in results:
                            if "episode" in result and isinstance(result.get("episode"), dict) and result["episode"].get("seriesId"):
                                series_id = result["episode"]["seriesId"]
                                series_name = await _translated_series_name(series_id, result["episode"].get("seriesName"))
                                logger.debug(f"[blue]TVDB series ID from episode entry (tv_movie): {series_id}[/blue]")
                                return _coerce_int(series_id), series_name

                        # If no episode with seriesId, accept movie results
                        for result in results:
                            if "movie" in result and isinstance(result.get("movie"), dict):
                                movie_id = result["movie"]["id"]
                                movie_name = result["movie"].get("name")
                                logger.debug(f"[blue]TVDB movie ID from IMDB (tv_movie): {movie_id}[/blue]")
                                return _coerce_int(movie_id), movie_name

                    result_types = [next(iter(result.keys())) for result in results if result]
                    logger.debug(f"[yellow]IMDB search returned results but no {'series or movie' if tv_movie else 'series'} found (got: {result_types})[/yellow]")
                else:
                    logger.debug("[yellow]No TVDB series found for IMDB ID[/yellow]")
            except Exception as e:
                logger.debug(f"[red]Error getting TVDB by IMDB ID: {e}[/red]")

        if tmdb:
            try:
                tmdb_str = str(tmdb)

                logger.debug(f"[cyan]Trying TVDB lookup with TMDB ID: {tmdb_str}[/cyan]")

                results = await client.search_by_remote_id(tmdb_str)

                if results and len(results) > 0:
                    logger.debug(f"[blue]results: {results}[/blue]")

                    # Look for series results first
                    for result in results:
                        if "series" in result and isinstance(result.get("series"), dict):
                            series_id = result["series"]["id"]
                            series_name = await _translated_series_name(series_id, result["series"].get("name"))
                            logger.debug(f"[blue]TVDB series ID from TMDB: {series_id}[/blue]")
                            return _coerce_int(series_id), series_name

                    # If tv_movie is True, check for episode with seriesId first, then movie
                    if tv_movie:
                        # Check if any result has an episode with a seriesId
                        for result in results:
                            if "episode" in result and isinstance(result.get("episode"), dict) and result["episode"].get("seriesId"):
                                series_id = result["episode"]["seriesId"]
                                series_name = await _translated_series_name(series_id, result["episode"].get("seriesName"))
                                logger.debug(f"[blue]TVDB series ID from episode entry (tv_movie): {series_id}[/blue]")
                                return _coerce_int(series_id), series_name

                        # If no episode with seriesId, accept movie results
                        for result in results:
                            if "movie" in result and isinstance(result.get("movie"), dict):
                                movie_id = result["movie"]["id"]
                                movie_name = result["movie"].get("name")
                                logger.debug(f"[blue]TVDB movie ID from TMDB (tv_movie): {movie_id}[/blue]")
                                return _coerce_int(movie_id), movie_name

                    result_types = [next(iter(result.keys())) for result in results if result]
                    logger.debug(f"[yellow]TMDB search returned results but no {'series or movie' if tv_movie else 'series'} found (got: {result_types})[/yellow]")
                else:
                    logger.debug("[yellow]No TVDB series found for TMDB ID[/yellow]")
            except Exception as e:
                logger.debug(f"[red]Error getting TVDB by TMDB ID: {e}[/red]")

        result_type_str = "series or movie" if tv_movie else "series"
        logger.info(f"[yellow]No TVDB {result_type_str} found for any available external ID[/yellow]")
        return None, None

    async def get_imdb_id_from_tvdb_episode_id(
        self,
        episode_id: int | str,
    ) -> str | None:
        try:
            client = _get_tvdb_or_warn(self.config)
            if client is None:
                return None

            episode_id_int = _coerce_int(episode_id)
            if episode_id_int is None:
                logger.debug(f"[yellow]Invalid TVDB episode ID: {episode_id}[/yellow]")
                return None

            cache = cache_for(base_dir="", config=self.config)
            cache_key = f"episode_imdb_{episode_id_int}"
            cached = await cache.get("tvdb", "episode_extended", cache_key)
            if not is_cache_miss(cached) and (cached is None or isinstance(cached, str)):
                return cached

            episode_data = await client.get_episode_extended(episode_id_int)
            logger.debug(f"[yellow]Episode data retrieved for episode ID {episode_id}[/yellow]")

            remote_ids = _as_dict_list(episode_data.get("remoteIds", []))
            imdb_id = None

            for remote_id in remote_ids:
                if remote_id.get("type") == 2 or remote_id.get("sourceName") == "IMDB":
                    imdb_id = remote_id.get("id")
                    break

            await cache.set("tvdb", "episode_extended", cache_key, imdb_id, negative=not bool(imdb_id))

            if imdb_id:
                logger.debug(f"[blue]TVDB episode ID: {episode_id} maps to IMDB ID: {imdb_id}[/blue]")
            else:
                logger.debug(f"[yellow]No IMDB ID found for TVDB episode ID: {episode_id}[/yellow]")

            return imdb_id
        except Exception as e:
            logger.error(f"[red]Error getting IMDB ID from TVDB episode ID: {e}[/red]")
            return None

    async def get_specific_episode_data(
        self,
        data: Any,
        season: int | str | None,
        episode: int | str | None,
        aired_date: str | None = None,
    ) -> tuple[
        Any | None,
        Any | None,
        Any | None,
        Any | None,
        Any | None,
        Any | None,
        Any | None,
    ]:
        logger.debug("[yellow]Getting specific episode data from TVDB data[/yellow]")

        # Handle both dict (full series data) and list (episodes only) formats
        if isinstance(data, dict):
            data_dict = cast(dict[str, Any], data)
            episodes = _as_dict_list(data_dict.get("episodes", []))
        elif isinstance(data, list):
            episodes = _as_dict_list(data)
        else:
            logger.info("[red]No episode data available or invalid format[/red]")
            return None, None, None, None, None, None, None

        if not episodes:
            logger.info("[red]No episodes found in data[/red]")
            return None, None, None, None, None, None, None

        # Convert season and episode to int for comparison
        try:
            season_int = int(season) if season is not None else None
            episode_int = int(episode) if episode is not None and episode != 0 else None
        except (ValueError, TypeError) as e:
            logger.info(f"[red]Invalid season or episode format: season={season}, episode={episode}, error={e}[/red]")
            return None, None, None, None, None, None, None

        if season_int is None:
            logger.info(f"[red]Season is None after conversion: season_int={season_int}[/red]")
            return None, None, None, None, None, None, None

        logger.debug(f"[blue]Total episodes retrieved from TVDB: {len(episodes)}[/blue]")
        logger.debug(f"[blue]Looking for Season: {season_int}, Episode: {episode_int}[/blue]")

        # For daily shows, match by air date if provided.
        if aired_date:
            aired_norm = aired_date.strip().replace(".", "-")
            for ep in episodes:
                if ep.get("aired") == aired_norm:
                    logger.debug(f"[green]Matched daily episode by air date {aired_norm}: S{ep.get('seasonNumber'):02d}E{ep.get('number'):02d} - {ep.get('name')}[/green]")
                    return (ep.get("seasonName"), ep.get("name"), ep.get("overview"), ep.get("seasonNumber"), ep.get("number"), ep.get("year"), ep.get("id"))

        # If episode_int is None or 0, return first episode of the season
        if episode_int is None or episode_int == 0:
            for ep in episodes:
                if ep.get("seasonNumber") == season_int:
                    logger.debug(f"[green]Found first episode of season {season_int}: S{season_int:02d}E{ep.get('number'):02d} - {ep.get('name')}[/green]")
                    return (ep.get("seasonName"), ep.get("name"), ep.get("overview"), ep.get("seasonNumber"), ep.get("number"), ep.get("year"), ep.get("id"))

        # Try to find exact season/episode match
        for ep in episodes:
            if ep.get("seasonNumber") == season_int and ep.get("number") == episode_int:
                logger.debug(f"[green]Found exact match: S{season_int:02d}E{episode_int:02d} - {ep.get('name')}[/green]")
                return (ep.get("seasonName"), ep.get("name"), ep.get("overview"), ep.get("seasonNumber"), ep.get("number"), ep.get("year"), ep.get("id"))

        # Try to find an episode with this absolute number directly
        logger.info("[yellow]No exact match found, trying absolute number mapping...[/yellow]")
        for ep in episodes:
            if ep.get("absoluteNumber") == episode_int:
                mapped_season = ep.get("seasonNumber")
                mapped_episode = ep.get("number")
                logger.debug(f"[green]Mapped absolute #{episode_int} -> S{mapped_season:02d}E{mapped_episode:02d} - {ep.get('name')}[/green]")
                return (ep.get("seasonName"), ep.get("name"), ep.get("overview"), ep.get("seasonNumber"), ep.get("number"), ep.get("year"), ep.get("id"))

        logger.info(f"[red]Could not find episode for S{season_int:02d}E{episode_int:02d} or absolute #{episode_int}[/red]")
        return None, None, None, None, None, None, None
