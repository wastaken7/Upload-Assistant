# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import asyncio
import contextlib
import json
import re
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from difflib import SequenceMatcher
from typing import Any
from typing import cast as typing_cast

import anitopy
import cli_ui
import guessit
import httpx

from src.args import Args
from src.cleanup import cleanup_manager
from src.console import logger, prompt_in_thread
from src.imdb import imdb_manager
from src.meta import Meta
from src.metadata_cache import cache_for, is_cache_miss

default_config: dict[str, Any] = {}
tmdb_api_key: str | None = None
TMDB_BASE_URL = "https://api.themoviedb.org/3"
parser: Args | None = None


def _apply_config(config: dict[str, Any]) -> None:
    global tmdb_api_key, parser, default_config
    default_cfg = typing_cast(dict[str, Any], config.get("DEFAULT", {}))
    default_config = default_cfg
    api_key_value = default_cfg.get("tmdb_api", False)
    if not api_key_value or not isinstance(api_key_value, str) or not api_key_value.strip():
        raise ValueError("TMDB API key is missing or invalid. Please set 'tmdb_api' in your config under DEFAULT section.")
    tmdb_api_key = api_key_value
    parser = Args(config=config)


def _get_parser() -> Args:
    if parser is None:
        raise RuntimeError("TMDb parser is not initialized. Create TmdbManager with config first.")
    return parser


anitopy_parse_fn: Any = typing_cast(Any, anitopy).parse
guessit_module: Any = typing_cast(Any, guessit)
GuessitFn = Callable[[str, dict[str, Any] | None], dict[str, Any]]


def guessit_fn(value: str, options: dict[str, Any] | None = None) -> dict[str, Any]:
    return typing_cast(dict[str, Any], guessit_module.guessit(value, options))


class TmdbManager:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        _apply_config(config)

    async def normalize_title(self, title: str) -> str:
        return await normalize_title(title)

    async def get_tmdb_from_imdb(
        self,
        imdb_id: str | int | None,
        tvdb_id: int | None = None,
        search_year: str | int | None = None,
        filename: str | None = None,
        debug: bool = False,
        mode: str = "non_cli",
        category_preference: str | None = None,
        imdb_info: dict[str, Any] | None = None,
    ) -> tuple[str, int | str, str, bool]:
        return await get_tmdb_from_imdb(
            imdb_id=imdb_id,
            tvdb_id=tvdb_id,
            search_year=search_year,
            filename=filename,
            debug=debug,
            mode=mode,
            category_preference=category_preference,
            imdb_info=imdb_info,
        )

    async def get_tmdb_id(
        self,
        filename: str,
        search_year: str | int | None,
        category: str | dict[str, Any],
        untouched_filename: str | None = "",
        attempted: int = 0,
        debug: bool = False,
        secondary_title: str | None = None,
        path: str | None = None,
        final_attempt: bool | None = None,
        new_category: str | None = None,
        unattended: bool = False,
    ) -> tuple[int, str]:
        return await get_tmdb_id(
            filename=filename,
            search_year=search_year,
            category=category,
            untouched_filename=untouched_filename,
            attempted=attempted,
            debug=debug,
            secondary_title=secondary_title,
            path=path,
            final_attempt=final_attempt,
            new_category=new_category,
            unattended=unattended,
        )

    async def tmdb_other_meta(
        self,
        tmdb_id: int | None,
        path: str | None = None,
        search_year: str | int | None = None,
        category: str | None = None,
        imdb_id: int | str | None = 0,
        manual_language: str | None = None,
        anime: bool = False,
        mal_manual: int | None = None,
        aka: str = "",
        original_language: str | None = None,
        poster: str | None = None,
        debug: bool = False,
        mode: str = "non_cli",
        tvdb_id: int | None = 0,
        quickie_search: bool = False,
        filename: str | None = None,
        base_dir: str = "",
    ) -> dict[str, Any]:
        return await tmdb_other_meta(
            tmdb_id=tmdb_id,
            path=path,
            search_year=search_year,
            category=category,
            imdb_id=imdb_id,
            manual_language=manual_language,
            anime=anime,
            mal_manual=mal_manual,
            aka=aka,
            original_language=original_language,
            poster=poster,
            debug=debug,
            mode=mode,
            tvdb_id=tvdb_id,
            quickie_search=quickie_search,
            filename=filename,
            base_dir=base_dir,
            config=self.config,
        )

    async def get_keywords(self, tmdb_id: int, category: str) -> list[str]:
        return await get_keywords(tmdb_id=tmdb_id, category=category)

    async def get_genres(self, response_data: dict[str, Any] | None) -> dict[str, Any]:
        return await get_genres(response_data=response_data)

    async def get_directors(self, tmdb_id: int, category: str) -> list[str]:
        return await get_directors(tmdb_id=tmdb_id, category=category)

    async def get_anime(
        self,
        response: dict[str, Any],
        meta: Meta,
    ) -> tuple[int, str, bool, str]:
        return await get_anime(response=response, meta=meta)

    async def get_romaji(
        self,
        tmdb_name: str,
        mal: int | None,
        meta: Meta,
    ) -> tuple[str, int, str, str, int, str]:
        return await get_romaji(tmdb_name=tmdb_name, mal=mal, meta=meta)

    async def get_tmdb_imdb_from_mediainfo(
        self,
        mediainfo: dict[str, Any],
        meta: Meta,
    ) -> tuple[str, int, int | None, int | None]:
        category_value = meta.category or "MOVIE"
        is_disc = bool(meta.is_disc)
        tmdbid = meta.tmdb_id or 0
        imdbid = meta.imdb_id or 0
        tvdbid = meta.tvdb_id or 0
        return await get_tmdb_imdb_from_mediainfo(
            mediainfo=mediainfo,
            category=category_value,
            is_disc=is_disc,
            tmdbid=tmdbid,
            imdbid=imdbid,
            tvdbid=tvdbid,
        )

    def extract_imdb_id(self, value: str) -> int | None:
        return extract_imdb_id(value=value)

    async def daily_to_tmdb_season_episode(
        self,
        tmdbid: int,
        date: str | datetime,
    ) -> tuple[int, int]:
        return await daily_to_tmdb_season_episode(tmdbid=tmdbid, date=date)

    async def get_episode_details(
        self,
        tmdb_id: int,
        season_number: int,
        episode_number: int,
    ) -> dict[str, Any]:
        return await get_episode_details(
            tmdb_id=tmdb_id,
            season_number=season_number,
            episode_number=episode_number,
        )

    async def get_season_details(
        self,
        tmdb_id: int,
        season_number: int,
    ) -> dict[str, Any]:
        return await get_season_details(tmdb_id=tmdb_id, season_number=season_number)

    async def get_logo(
        self,
        tmdb_id: int,
        category: str,
        logo_languages: list[str] | str | None = None,
        tmdb_api_key: str | None = None,
        tmdb_base_url: str | None = None,
        logo_json: dict[str, Any] | None = None,
    ) -> str:
        return await get_logo(
            tmdb_id=tmdb_id,
            category=category,
            logo_languages=logo_languages,
            tmdb_api_key=tmdb_api_key,
            tmdb_base_url=tmdb_base_url,
            logo_json=logo_json,
        )

    async def get_tmdb_translations(
        self,
        tmdb_id: int,
        category: str,
        target_language: str = "en",
    ) -> str:
        return await get_tmdb_translations(
            tmdb_id=tmdb_id,
            category=category,
            target_language=target_language,
        )

    async def set_tmdb_metadata(self, meta: Meta, filename: str | None = None) -> None:
        return await set_tmdb_metadata(meta=meta, filename=filename)

    async def get_tmdb_localized_data(
        self,
        meta: Meta,
        data_type: str,
        language: str,
        append_to_response: str,
    ) -> dict[str, Any]:
        return await get_tmdb_localized_data(
            meta=meta,
            data_type=data_type,
            language=language,
            append_to_response=append_to_response,
        )


async def normalize_title(title: str) -> str:
    return title.lower().replace("&", "and").replace("  ", " ").strip()


async def get_tmdb_from_imdb(
    imdb_id: str | int | None,
    tvdb_id: int | None = None,
    search_year: str | int | None = None,
    filename: str | None = None,
    debug: bool = False,
    mode: str = "non_cli",
    category_preference: str | None = None,
    imdb_info: dict[str, Any] | None = None,
) -> tuple[str, int | str, str, bool]:
    """Fetches TMDb ID using IMDb or TVDb ID.

    - Returns `(category, tmdb_id, original_language)`
    - If TMDb fails, prompts the user (if in CLI mode).
    """
    if imdb_id is None or imdb_id == 0 or str(imdb_id).strip() == "":
        return "", 0, "", False
    if not str(imdb_id).startswith("tt"):
        if isinstance(imdb_id, str) and imdb_id.isdigit():
            imdb_id = f"tt{int(imdb_id):07d}"
        elif isinstance(imdb_id, int):
            imdb_id = f"tt{imdb_id:07d}"
    filename_search = False

    async def _tmdb_find_by_external_source(external_id: str | int, source: str) -> dict[str, Any]:
        """Helper function to find a movie or TV show on TMDb by external ID."""
        url = f"{TMDB_BASE_URL}/find/{external_id}"
        params = {"api_key": tmdb_api_key, "external_source": source}

        async with httpx.AsyncClient() as client:
            response: httpx.Response | None = None
            try:
                response = await client.get(url, params=params, timeout=10)
                response.raise_for_status()
                return typing_cast(dict[str, Any], response.json())
            except Exception:
                status_code = response.status_code if response is not None else "unknown"
                logger.info(f"[bold red]Failed to fetch TMDb data: {status_code}[/bold red]")
                return {}

    # Run a search by IMDb ID
    info = await _tmdb_find_by_external_source(imdb_id, "imdb_id")

    # Check if both movie and TV results exist
    has_movie_results = bool(info.get("movie_results"))
    has_tv_results = bool(info.get("tv_results"))

    # If we have results in multiple categories but a category preference is set, respect that preference
    if category_preference and has_movie_results and has_tv_results:
        if category_preference == "MOVIE" and has_movie_results:
            logger.debug("[green]Found both movie and TV results, using movie based on preference")
            return "MOVIE", info["movie_results"][0]["id"], info["movie_results"][0].get("original_language"), filename_search
        if category_preference == "TV" and has_tv_results:
            logger.debug("[green]Found both movie and TV results, using TV based on preference")
            return "TV", info["tv_results"][0]["id"], info["tv_results"][0].get("original_language"), filename_search

    # If no preference or preference doesn't match available results, proceed with normal logic
    if has_movie_results:
        logger.debug(f"Movie INFO: {info}")
        return "MOVIE", info["movie_results"][0]["id"], info["movie_results"][0].get("original_language"), filename_search

    if has_tv_results:
        logger.debug(f"TV INFO: {info}")
        return "TV", info["tv_results"][0]["id"], info["tv_results"][0].get("original_language"), filename_search

    logger.debug("[yellow]TMDb was unable to find anything with that IMDb ID, checking TVDb...")

    # Check TVDb for an ID if TVDb and still no results
    if tvdb_id:
        info_tvdb = await _tmdb_find_by_external_source(str(tvdb_id), "tvdb_id")
        logger.debug(f"TVDB INFO: {info_tvdb}")
        if info_tvdb.get("tv_results"):
            return "TV", info_tvdb["tv_results"][0]["id"], info_tvdb["tv_results"][0].get("original_language"), filename_search

    filename_search = True

    # If both TMDb and TVDb fail, fetch IMDb info and attempt a title search
    imdb_id_str = str(imdb_id)
    imdb_id_clean = imdb_id_str.replace("tt", "")
    imdb_id = int(imdb_id_clean) if imdb_id_clean.isdigit() else 0
    imdb_info = imdb_info or await imdb_manager.get_imdb_info_api(imdb_id, {})
    title = str(imdb_info.get("title") or filename or "")
    year = imdb_info.get("year") or search_year
    original_language = imdb_info.get("original_language") or imdb_info.get("original language") or "en"

    logger.info(f"[yellow]TMDb was unable to find anything from external IDs, searching TMDb for {title} ({year})[/yellow]")

    # Try as movie first
    fallback_movie_title = str(imdb_info.get("original title") or imdb_info.get("localized title") or "")
    tmdb_id, category = await get_tmdb_id(title, year, "MOVIE", secondary_title=fallback_movie_title, debug=debug)

    # If no results, try as TV
    if tmdb_id == 0:
        tmdb_id, category = await get_tmdb_id(title, year, "TV", secondary_title=fallback_movie_title, debug=debug)

    # Extract necessary values from the result
    tmdb_id = tmdb_id or 0
    category = category or "MOVIE"

    # **User Prompt for Manual TMDb ID Entry**
    if tmdb_id in ("None", "", None, 0, "0") and mode == "cli":
        logger.info("[yellow]Unable to find a matching TMDb entry[/yellow]")
        tmdb_input = await prompt_in_thread(cli_ui.ask_string, "Please enter TMDb ID (format: tv/12345 or movie/12345): ", default="") or ""
        category, tmdb_id = _get_parser().parse_tmdb_id(tmdb_input, category)

    return category, tmdb_id, original_language, filename_search


async def get_tmdb_id(
    filename: str,
    search_year: str | int | None,
    category: str | dict[str, Any],
    untouched_filename: str | None = "",
    attempted: int = 0,
    debug: bool = False,
    secondary_title: str | None = None,
    path: str | None = None,
    final_attempt: bool | None = None,
    new_category: str | None = None,
    unattended: bool = False,
) -> tuple[int, str]:
    search_results: dict[str, Any] = {"results": []}
    category_value = category.get("category", "MOVIE") if isinstance(category, dict) else category
    category_str: str = str(new_category or category_value or "MOVIE")
    original_category: str = category_str
    category = category_str
    if final_attempt is None:
        final_attempt = False
    if attempted:
        await asyncio.sleep(1)  # Whoa baby, slow down

    async def search_tmdb_id(
        filename: str,
        search_year: str | int | None,
        category: str,
        untouched_filename: str | None = "",
        attempted: int = 0,
        debug: bool = False,
        secondary_title: str | None = None,
        path: str | None = None,
        final_attempt: bool | None = None,
        new_category: str | None = None,
        unattended: bool = False,
    ) -> tuple[int, str]:
        _ = untouched_filename
        _ = path
        search_results: dict[str, Any] = {"results": []}
        original_category = category
        category = new_category or original_category
        if final_attempt is None:
            final_attempt = False
        if attempted:
            await asyncio.sleep(1)  # Whoa baby, slow down
        async with httpx.AsyncClient() as client:
            try:
                # Primary search attempt with year
                if category == "MOVIE":
                    logger.debug(f"[green]Searching TMDb for movie:[/] [cyan]{filename}[/cyan] (Year: {search_year})")

                    params = {"api_key": tmdb_api_key, "query": filename, "language": "en-US", "include_adult": "true"}

                    if search_year:
                        params["year"] = str(search_year)

                    response = await client.get(f"{TMDB_BASE_URL}/search/movie", params=params)
                    try:
                        response.raise_for_status()
                        search_results = typing_cast(dict[str, Any], response.json())
                    except Exception:
                        logger.info(f"[bold red]Failure with primary movie search: {response.status_code}[/bold red]")

                elif category == "TV":
                    logger.debug(f"[green]Searching TMDb for TV show:[/] [cyan]{filename}[/cyan] (Year: {search_year})")

                    params = {"api_key": tmdb_api_key, "query": filename, "language": "en-US", "include_adult": "true"}

                    if search_year:
                        params["first_air_date_year"] = str(search_year)

                    response = await client.get(f"{TMDB_BASE_URL}/search/tv", params=params)
                    try:
                        response.raise_for_status()
                        search_results = typing_cast(dict[str, Any], response.json())
                    except Exception:
                        logger.info(f"[bold red]Failed with primary TV search: {response.status_code}[/bold red]")

                logger.debug(f"[yellow]TMDB search results (primary): {json.dumps(search_results.get('results', [])[:4], indent=2)}[/yellow]")

                # Check if results were found
                results = typing_cast(list[dict[str, Any]], search_results.get("results", []))
                if results:
                    # Filter results by year if search_year is provided
                    if search_year:

                        def get_result_year(result: dict[str, Any]) -> int:
                            return int((result.get("release_date") or result.get("first_air_date") or "0000")[:4] or 0)

                        filtered_results: list[dict[str, Any]] = [r for r in results if abs(get_result_year(r) - int(search_year)) <= 2]
                        limited_results: list[dict[str, Any]] = (filtered_results if filtered_results else results)[:8]
                    else:
                        limited_results = results[:8]

                    if len(limited_results) == 1:
                        tmdb_id = int(limited_results[0]["id"])
                        return tmdb_id, category
                    if len(limited_results) > 1:
                        filename_norm = await normalize_title(filename)
                        secondary_norm = await normalize_title(secondary_title) if secondary_title else None
                        search_year_int = int(search_year) if search_year else 0

                        # Find all exact matches (title and year)
                        exact_matches: list[dict[str, Any]] = []
                        for r in limited_results:
                            if r.get("title"):
                                result_title = await normalize_title(str(r.get("title", "")))
                            else:
                                result_title = await normalize_title(str(r.get("name", "")))
                            if r.get("original_title"):
                                original_title = await normalize_title(str(r.get("original_title", "")))
                            else:
                                original_title = await normalize_title(str(r.get("original_name", "")))
                            result_year = int((r.get("release_date") or r.get("first_air_date") or "0")[:4] or 0)
                            # Only count as exact match if both years are present and non-zero
                            if secondary_norm and (
                                secondary_norm == original_title
                                and search_year_int > 0
                                and result_year > 0
                                and (result_year == search_year_int or result_year == search_year_int + 1)
                            ):
                                exact_matches.append(r)

                            if (
                                filename_norm == result_title
                                and search_year_int > 0
                                and result_year > 0
                                and (result_year == search_year_int or result_year == search_year_int + 1)
                            ):
                                exact_matches.append(r)

                            if secondary_norm and (
                                secondary_norm == result_title
                                and search_year_int > 0
                                and result_year > 0
                                and (result_year == search_year_int or result_year == search_year_int + 1)
                            ):
                                exact_matches.append(r)

                        summary_exact_matches: set[int] = {int(r["id"]) for r in exact_matches if "id" in r}

                        if len(summary_exact_matches) == 1:
                            tmdb_id = summary_exact_matches.pop()
                            return tmdb_id, category

                        # If no exact matches, calculate similarity for all results and sort them
                        results_with_similarity: list[tuple[dict[str, Any], float]] = []
                        for r in limited_results:
                            if r.get("title"):
                                result_title = await normalize_title(str(r.get("title", "")))
                            else:
                                result_title = await normalize_title(str(r.get("name", "")))

                            if r.get("original_title"):
                                original_title = await normalize_title(str(r.get("original_title", "")))
                            else:
                                original_title = await normalize_title(str(r.get("original_name", "")))

                            # Calculate similarity for both main title and original title
                            main_similarity = SequenceMatcher(None, filename_norm, result_title).ratio()
                            original_similarity = SequenceMatcher(None, filename_norm, original_title).ratio()

                            # Try getting TMDb translation for original title if it's different
                            translated_title = ""
                            translated_similarity = 0.0
                            secondary_best = 0.0

                            if original_title and original_title != result_title:
                                translated_title = await get_tmdb_translations(r["id"], category, "en")
                                if translated_title:
                                    translated_title_norm = await normalize_title(translated_title)
                                    translated_similarity = SequenceMatcher(None, filename_norm, translated_title_norm).ratio()

                                    logger.debug(f"[cyan]  TMDb translation: '{translated_title}' (similarity: {translated_similarity:.3f})[/cyan]")

                            # Also calculate secondary title similarity if available
                            if secondary_norm is not None:
                                secondary_main_sim = SequenceMatcher(None, secondary_norm, result_title).ratio()
                                secondary_orig_sim = SequenceMatcher(None, secondary_norm, original_title).ratio()
                                secondary_trans_sim = 0.0

                                if translated_title:
                                    translated_title_norm = await normalize_title(translated_title)
                                    secondary_trans_sim = SequenceMatcher(None, secondary_norm, translated_title_norm).ratio()

                                secondary_best = max(secondary_main_sim, secondary_orig_sim, secondary_trans_sim)

                            if translated_similarity == 0.0:
                                if secondary_best == 0.0:
                                    similarity = (main_similarity * 0.5) + (original_similarity * 0.5)
                                else:
                                    similarity = (main_similarity * 0.3) + (original_similarity * 0.3) + (secondary_best * 0.4)
                            else:
                                similarity = main_similarity * 0.5 + translated_similarity * 0.5 if secondary_best == 0.0 else main_similarity * 0.5 + secondary_best * 0.5

                            result_year = int((r.get("release_date") or r.get("first_air_date") or "0")[:4] or 0)

                            logger.debug(f"[cyan]ID {r['id']}: '{result_title}' vs '{filename_norm}'[/cyan]")
                            logger.debug(f"[cyan]  Main similarity: {main_similarity:.3f}[/cyan]")
                            logger.debug(f"[cyan]  Original similarity: {original_similarity:.3f}[/cyan]")
                            if translated_similarity > 0:
                                logger.debug(f"[cyan]  Translated similarity: {translated_similarity:.3f}[/cyan]")
                            if secondary_best > 0:
                                logger.debug(f"[cyan]  Secondary similarity: {secondary_best:.3f}[/cyan]")
                            logger.debug(f"[cyan]  Final similarity: {similarity:.3f}[/cyan]")

                            # Boost similarity if we have exact matches with year validation
                            if similarity >= 0.9 and search_year_int > 0 and result_year > 0:
                                if result_year == search_year_int:
                                    similarity += 0.1  # Full boost for exact year match
                                elif result_year == search_year_int + 1:
                                    similarity += 0.1  # Boost for +1 year (handles TMDB/IMDb differences)

                            results_with_similarity.append((r, similarity))

                        # Give a slight boost to the first result for TV shows (often the main series)
                        if category == "TV" and results_with_similarity:
                            first_result = results_with_similarity[0]
                            # Boost the first result's similarity by 0.05 (5%)
                            boosted_similarity = first_result[1] + 0.05
                            results_with_similarity[0] = (first_result[0], boosted_similarity)

                            logger.debug(f"[cyan]Boosted first TV result similarity from {first_result[1]:.3f} to {boosted_similarity:.3f}[/cyan]")

                        # Sort by similarity (highest first)
                        results_with_similarity.sort(key=lambda x: x[1], reverse=True)
                        sorted_results: list[dict[str, Any]] = [r[0] for r in results_with_similarity]

                        # Filter results: if we have high similarity matches (>= 0.90), hide low similarity ones (< 0.75)
                        best_similarity = results_with_similarity[0][1]
                        if best_similarity >= 0.90:
                            # Filter out results with similarity < 0.75
                            filtered_results_with_similarity: list[tuple[dict[str, Any], float]] = [(result, sim) for result, sim in results_with_similarity if sim >= 0.75]
                            results_with_similarity = filtered_results_with_similarity
                            sorted_results = [r[0] for r in results_with_similarity]

                            logger.debug(f"[yellow]Filtered out low similarity results (< 0.70) since best match has {best_similarity:.2f} similarity[/yellow]")
                        else:
                            sorted_results = [r[0] for r in results_with_similarity]

                        # Check if the best match is significantly better than others
                        best_similarity = results_with_similarity[0][1]
                        similarity_threshold = 0.70

                        if best_similarity >= similarity_threshold:
                            # Check that no other result is close to the best match
                            second_best = results_with_similarity[1][1] if len(results_with_similarity) > 1 else 0.0
                            if best_similarity >= 0.75 and best_similarity - second_best >= 0.10:
                                logger.debug(
                                    f"[green]Auto-selecting best match: {sorted_results[0].get('title') or sorted_results[0].get('name')} (similarity: {best_similarity:.2f}[/green]"
                                )
                                tmdb_id = int(sorted_results[0]["id"])
                                return tmdb_id, category

                        # Check for "The" prefix handling
                        if len(results_with_similarity) > 1:
                            the_results: list[tuple[dict[str, Any], float]] = []
                            non_the_results: list[tuple[dict[str, Any], float]] = []

                            for result_tuple in results_with_similarity:
                                result, similarity = result_tuple
                                if result.get("title"):
                                    title = await normalize_title(str(result.get("title", "")))
                                else:
                                    title = await normalize_title(str(result.get("name", "")))
                                if title.startswith("the "):
                                    the_results.append(result_tuple)
                                else:
                                    non_the_results.append(result_tuple)

                            # If exactly one result starts with "The", check if similarity improves
                            if len(the_results) == 1 and len(non_the_results) > 0:
                                the_result, the_similarity = the_results[0]
                                if the_result.get("title"):
                                    the_title = await normalize_title(str(the_result.get("title", "")))
                                else:
                                    the_title = await normalize_title(str(the_result.get("name", "")))
                                the_title_without_the = the_title[4:]
                                new_similarity = SequenceMatcher(None, filename_norm, the_title_without_the).ratio()

                                logger.debug(f"[cyan]Checking 'The' prefix: '{the_title}' -> '{the_title_without_the}'[/cyan]")
                                logger.debug(f"[cyan]Original similarity: {the_similarity:.3f}, New similarity: {new_similarity:.3f}[/cyan]")

                                # If similarity improves significantly, update and resort
                                if new_similarity > the_similarity + 0.05:
                                    logger.debug("[green]'The' prefix removal improved similarity, updating results[/green]")

                                    updated_results: list[tuple[dict[str, Any], float]] = []
                                    for result_tuple in results_with_similarity:
                                        result, similarity = result_tuple
                                        if result["id"] == the_result["id"]:
                                            updated_results.append((result, new_similarity))
                                        else:
                                            updated_results.append(result_tuple)

                                    # Resort by similarity
                                    updated_results.sort(key=lambda x: x[1], reverse=True)
                                    results_with_similarity = updated_results
                                    sorted_results = [r[0] for r in results_with_similarity]
                                    best_similarity = results_with_similarity[0][1]
                                    second_best = results_with_similarity[1][1] if len(results_with_similarity) > 1 else 0.0

                                    if best_similarity >= 0.75 and best_similarity - second_best >= 0.10:
                                        logger.debug(
                                            f"[green]Auto-selecting 'The' prefixed match: {sorted_results[0].get('title') or sorted_results[0].get('name')} (similarity: {best_similarity:.2f})[/green]"
                                        )
                                        tmdb_id = int(sorted_results[0]["id"])
                                        return tmdb_id, category

                        # Put unattended handling here, since it will work based on the sorted results
                        if unattended and not debug:
                            tmdb_id = int(sorted_results[0]["id"])
                            return tmdb_id, category

                        # Show sorted results to user
                        logger.info("")
                        logger.info("[bold yellow]Multiple TMDb results found. Please select the correct entry:[/bold yellow]")
                        tmdb_url = "https://www.themoviedb.org/movie/" if category == "MOVIE" else "https://www.themoviedb.org/tv/"

                        for idx, result in enumerate(sorted_results):
                            title = result.get("title") or result.get("name", "")
                            year = (result.get("release_date") or result.get("first_air_date") or "")[:4]
                            overview = result.get("overview", "")
                            similarity_score = results_with_similarity[idx][1]

                            logger.info(
                                f"[cyan]{idx + 1}.[/cyan] [bold]{title}[/bold] ({year}) [yellow]ID:[/yellow] {tmdb_url}{result['id']} [dim](similarity: {similarity_score:.2f})[/dim]"
                            )
                            if overview:
                                logger.info(f"[green]Overview:[/green] {overview[:200]}{'...' if len(overview) > 200 else ''}")
                            logger.info("")

                        selection: str = ""
                        while True:
                            logger.info("Enter the number of the correct entry, or manual TMDb ID (tv/12345 or movie/12345):")
                            try:
                                selection = await prompt_in_thread(cli_ui.ask_string, "Or push enter to try a different search: ") or ""
                            except EOFError:
                                logger.info("\n[red]Exiting on user request (Ctrl+C)[/red]")
                                await cleanup_manager.cleanup()
                                cleanup_manager.reset_terminal()
                                sys.exit(1)
                            if not selection.strip():
                                break
                            try:
                                # Check if it's a manual TMDb ID entry
                                if "/" in selection and (selection.lower().startswith("tv/") or selection.lower().startswith("movie/")):
                                    try:
                                        parsed_category, parsed_tmdb_id = _get_parser().parse_tmdb_id(selection, category)
                                        if parsed_tmdb_id and parsed_tmdb_id != 0:
                                            logger.info(f"[green]Using manual TMDb ID: {parsed_tmdb_id} and category: {parsed_category}[/green]")
                                            return parsed_tmdb_id, parsed_category
                                        logger.info("[bold red]Invalid TMDb ID format. Please try again.[/bold red]")
                                        continue
                                    except Exception as e:
                                        logger.info(f"[bold red]Error parsing TMDb ID: {e}. Please try again.[/bold red]")
                                        continue
                                    except KeyboardInterrupt:
                                        logger.info("\n[bold red]Search cancelled by user.[/bold red]")
                                        sys.exit(0)

                                # Handle numeric selection
                                selection_int = int(selection)
                                if 1 <= selection_int <= len(sorted_results):
                                    tmdb_id = int(sorted_results[selection_int - 1]["id"])
                                    return tmdb_id, category
                                logger.info("[bold red]Selection out of range. Please try again.[/bold red]")
                            except ValueError:
                                logger.info("[bold red]Invalid input. Please enter a number or TMDb ID (tv/12345 or movie/12345).[/bold red]")
                            except KeyboardInterrupt:
                                logger.info("\n[bold red]Search cancelled by user.[/bold red]")
                                sys.exit(0)

            except Exception:
                search_results = {"results": []}  # Reset search_results on exception

        return 0, category

    # TMDb doesn't do roman
    if not search_results.get("results"):
        try:
            words = filename.split()
            roman_numerals = {"II": "2", "III": "3", "IV": "4", "V": "5", "VI": "6", "VII": "7", "VIII": "8", "IX": "9", "X": "10"}

            converted = False
            for i, word in enumerate(words):
                if word.upper() in roman_numerals:
                    words[i] = roman_numerals[word.upper()]
                    converted = True

            if converted:
                converted_title = " ".join(words)
                logger.debug(f"[bold yellow]Trying with roman numerals converted: {converted_title}[/bold yellow]")
                result = await search_tmdb_id(
                    converted_title,
                    search_year,
                    original_category,
                    untouched_filename,
                    attempted + 1,
                    debug=debug,
                    secondary_title=secondary_title,
                    path=path,
                    unattended=unattended,
                )
                if result and result != (0, category):
                    return result
        except Exception as e:
            logger.info(f"[bold red]Roman numeral conversion error:[/bold red] {e}")
            search_results = {"results": []}

    # If we have a secondary title, try searching with that
    if secondary_title:
        logger.debug(f"[yellow]Trying secondary title: {secondary_title}[/yellow]")
        result = await search_tmdb_id(
            secondary_title, search_year, category, untouched_filename, debug=debug, secondary_title=secondary_title, path=path, unattended=unattended
        )
        if result and result != (0, category):
            return result

    # Try searching with the primary filename
    logger.debug(f"[yellow]Trying primary filename: {filename}[/yellow]")
    if not search_results.get("results"):
        result = await search_tmdb_id(filename, search_year, category, untouched_filename, debug=debug, secondary_title=secondary_title, path=path, unattended=unattended)
        if result and result != (0, category):
            return result

    # Try searching with year + 1 if search_year is provided
    if not search_results.get("results"):
        try:
            year_int = int(search_year) if search_year is not None else 0
        except Exception:
            year_int = 0

        if year_int > 0:
            imdb_year = year_int + 1
            logger.debug("[yellow]Retrying with year +1...[/yellow]")
            result = await search_tmdb_id(
                filename, imdb_year, category, untouched_filename, attempted + 1, debug=debug, secondary_title=secondary_title, path=path, unattended=unattended
            )
            if result and result != (0, category):
                return result

    # Try switching category
    if not search_results.get("results"):
        new_category = "TV" if category == "MOVIE" else "MOVIE"
        logger.debug(f"[bold yellow]Switching category to {new_category} and retrying...[/bold yellow]")
        result = await search_tmdb_id(
            filename,
            search_year,
            category,
            untouched_filename,
            attempted + 1,
            debug=debug,
            secondary_title=secondary_title,
            path=path,
            new_category=new_category,
            unattended=unattended,
        )
        if result and result != (0, category):
            return result

    # try anime name parsing
    if not search_results.get("results"):
        try:
            parsed_guess = guessit_fn(untouched_filename or "", {"excludes": ["country", "language"]})
            parsed_title_data = typing_cast(dict[str, Any], anitopy_parse_fn(parsed_guess.get("title", "")) or {})
            parsed_title = str(parsed_title_data.get("anime_title", ""))
            logger.debug(f"[bold yellow]Trying parsed anime title: {parsed_title}[/bold yellow]")
            result = await search_tmdb_id(
                parsed_title, search_year, original_category, untouched_filename, attempted + 1, debug=debug, secondary_title=secondary_title, path=path, unattended=unattended
            )
            if result and result != (0, category):
                return result
        except KeyError:
            logger.info("[bold red]Failed to parse title for TMDb search.[/bold red]")
            search_results = {"results": []}

    # Try with less words in the title
    if not search_results.get("results"):
        try:
            words = filename.split()
            extensions = ["mp4", "mkv", "avi", "webm", "mov", "wmv"]
            words_lower = [word.lower() for word in words]

            for ext in extensions:
                if ext in words_lower:
                    ext_index = words_lower.index(ext)
                    words.pop(ext_index)
                    words_lower.pop(ext_index)
                    break

            if len(words) >= 2:
                title = " ".join(words[:-1])
                logger.debug(f"[bold yellow]Trying reduced name: {title}[/bold yellow]")
                result = await search_tmdb_id(
                    title, search_year, original_category, untouched_filename, attempted + 1, debug=debug, secondary_title=secondary_title, path=path, unattended=unattended
                )
                if result and result != (0, category):
                    return result
        except Exception as e:
            logger.info(f"[bold red]Reduced name search error:[/bold red] {e}")
            search_results = {"results": []}

    # Try with even less words
    if not search_results.get("results"):
        try:
            words = filename.split()
            extensions = ["mp4", "mkv", "avi", "webm", "mov", "wmv"]
            words_lower = [word.lower() for word in words]

            for ext in extensions:
                if ext in words_lower:
                    ext_index = words_lower.index(ext)
                    words.pop(ext_index)
                    words_lower.pop(ext_index)
                    break

            if len(words) >= 3:
                title = " ".join(words[:-2])
                logger.debug(f"[bold yellow]Trying further reduced name: {title}[/bold yellow]")
                result = await search_tmdb_id(
                    title, search_year, original_category, untouched_filename, attempted + 1, debug=debug, secondary_title=secondary_title, path=path, unattended=unattended
                )
                if result and result != (0, category):
                    return result
        except Exception as e:
            logger.info(f"[bold red]Reduced name search error:[/bold red] {e}")
            search_results = {"results": []}

    # No match found, prompt user if in CLI mode
    logger.info("[bold red]Unable to find TMDb match using any search[/bold red]")
    try:
        tmdb_input = await prompt_in_thread(cli_ui.ask_string, "Please enter TMDb ID in this format: tv/12345 or movie/12345")
    except EOFError:
        logger.info("\n[red]Exiting on user request (Ctrl+C)[/red]")
        await cleanup_manager.cleanup()
        cleanup_manager.reset_terminal()
        sys.exit(1)
    if tmdb_input is None:
        tmdb_input = ""
    category, tmdb_id = _get_parser().parse_tmdb_id(tmdb_input, category)

    return tmdb_id, category


async def tmdb_other_meta(
    tmdb_id: int | None,
    path: str | None = None,
    search_year: str | int | None = None,
    category: str | None = None,
    imdb_id: int | str | None = 0,
    manual_language: str | None = None,
    anime: bool = False,
    mal_manual: int | None = None,
    aka: str = "",
    original_language: str | None = None,
    poster: str | None = None,
    debug: bool = False,
    mode: str = "non_cli",
    tvdb_id: int | None = 0,
    quickie_search: bool = False,
    filename: str | None = None,
    base_dir: str = "",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Fetch metadata from TMDB for a movie or TV show.
    Returns a dictionary containing metadata that can be used to update the meta object.
    """
    tmdb_id = tmdb_id or 0
    imdb_id = imdb_id or 0
    tvdb_id = tvdb_id or 0
    _ = aka

    # Initialize variables that might not be set in all code paths
    adult_media = False
    backdrop = ""
    cast: list[str] = []
    certification = ""
    creators: list[str] = []
    demographic = ""
    directors: list[str] = []
    genre_ids = ""
    genres = ""
    imdb_mismatch = False
    keywords = ""
    logo_path = ""
    tmdb_logo = ""
    mal_id = 0
    mismatched_imdb_id = 0
    origin_country = []
    original_title = ""
    overview = ""
    poster_path = ""
    retrieved_aka = ""
    runtime = 60
    title = None
    tmdb_type = ""
    year = None
    release_date = None
    first_air_date = None
    last_air_date = None
    youtube = None
    networks = []

    if tmdb_id == 0:
        try:
            guessed = guessit_fn(path or "", {"excludes": ["country", "language"]})
            title = str(guessed.get("title", "")).lower()
            title = title.split("aka")[0]
            tmdb_id, _ = await get_tmdb_id(
                str(guessit_fn(title, {"excludes": ["country", "language"]}).get("title", "")),
                search_year,
                {"tmdb_id": 0, "search_year": search_year, "debug": debug, "category": category, "mode": mode},
                category,
            )

            if tmdb_id == 0:
                tmdb_id, _ = await get_tmdb_id(title, "", {"tmdb_id": 0, "search_year": "", "debug": debug, "category": category, "mode": mode}, category)

            if tmdb_id == 0:
                if mode == "cli":
                    logger.info("[bold red]Unable to find tmdb entry. Exiting.")
                    exit()
                else:
                    logger.info("[bold red]Unable to find tmdb entry")
                    return {}
        except Exception:
            if mode == "cli":
                logger.info("[bold red]Unable to find tmdb entry. Exiting.")
                exit()
            else:
                logger.info("[bold red]Unable to find tmdb entry")
                return {}

    youtube = None
    title = None
    year = None
    original_imdb_id = imdb_id

    cache = cache_for(base_dir, config)
    async with httpx.AsyncClient() as client:
        # Get main media details first (movie or TV show)
        main_url = f"{TMDB_BASE_URL}/{('movie' if category == 'MOVIE' else 'tv')}/{tmdb_id}"

        cache_key = json.dumps({"category": category, "id": tmdb_id}, sort_keys=True)
        cached_media = await cache.get("tmdb", "main", cache_key)
        if not is_cache_miss(cached_media) and isinstance(cached_media, dict):
            media_data = cached_media
        else:
            response = await client.get(main_url, params={"api_key": tmdb_api_key})
            try:
                response.raise_for_status()
                media_data = typing_cast(dict[str, Any], response.json())
            except Exception:
                logger.info(f"[bold red]Failed to fetch media data: {response.status_code}[/bold red]")
                return {}
            await cache.set("tmdb", "main", cache_key, media_data)

        logger.debug(f"[cyan]TMDB Response: {json.dumps(media_data, indent=2)[:1200]}...")

        # Extract basic info from media_data
        if category == "MOVIE":
            title = media_data["title"]
            original_title = media_data.get("original_title", title)
            year = datetime.strptime(media_data["release_date"], "%Y-%m-%d").replace(tzinfo=UTC).year if media_data["release_date"] else search_year
            runtime = media_data.get("runtime", 60)
            if media_data.get("release_date"):
                release_date = media_data["release_date"]
            if quickie_search or not imdb_id:
                imdb_id_str = str(media_data.get("imdb_id", "")).replace("tt", "")
                if imdb_id_str and imdb_id_str.isdigit():
                    if imdb_id and int(imdb_id_str) != imdb_id:
                        imdb_mismatch = True
                        mismatched_imdb_id = int(imdb_id_str)
                        imdb_id = original_imdb_id
                else:
                    imdb_id = original_imdb_id

            tmdb_type = "Movie"
        else:  # TV show
            title = media_data["name"]
            original_title = media_data.get("original_name", title)
            year = datetime.strptime(media_data["first_air_date"], "%Y-%m-%d").replace(tzinfo=UTC).year if media_data["first_air_date"] else search_year
            if not year:
                year_pattern = r"(18|19|20)\d{2}"
                year_match = re.search(year_pattern, title)
                if year_match:
                    year = int(year_match.group(0))
            if not year:
                year = datetime.strptime(media_data["last_air_date"], "%Y-%m-%d").replace(tzinfo=UTC).year if media_data["last_air_date"] else 0
            first_air_date = media_data.get("first_air_date", None)
            last_air_date = media_data.get("last_air_date", None)
            runtime_list = media_data.get("episode_run_time", [60])
            runtime = runtime_list[0] if runtime_list else 60
            tmdb_type = media_data.get("type", "Scripted")
            networks = media_data.get("networks", [])

        adult_media = media_data.get("adult", False)

        production_companies = media_data.get("production_companies", [])
        production_countries = media_data.get("production_countries", [])

        overview = media_data["overview"]
        original_language_from_tmdb = str(media_data.get("original_language", ""))

        poster_path = media_data.get("poster_path", "")
        if poster is None and poster_path:
            poster = f"https://image.tmdb.org/t/p/original{poster_path}"

        backdrop = media_data.get("backdrop_path", "")
        if backdrop:
            backdrop = f"https://image.tmdb.org/t/p/original{backdrop}"

        # Prepare all API endpoints for concurrent requests
        endpoints = [
            # External IDs
            client.get(f"{main_url}/external_ids", params={"api_key": tmdb_api_key}),
            # Videos
            client.get(f"{main_url}/videos", params={"api_key": tmdb_api_key}),
            # Keywords
            client.get(f"{main_url}/keywords", params={"api_key": tmdb_api_key}),
            # Credits
            client.get(f"{main_url}/credits", params={"api_key": tmdb_api_key}),
        ]

        # Add logo request if needed
        if default_config.get("add_logo", False):
            endpoints.append(client.get(f"{TMDB_BASE_URL}/{('movie' if category == 'MOVIE' else 'tv')}/{tmdb_id}/images", params={"api_key": tmdb_api_key}))

        # Make all requests concurrently
        results = await asyncio.gather(*endpoints, return_exceptions=True)

        # Process results with the correct indexing
        external_data, videos_data, keywords_data, credits_data, *rest = results
        idx = 0
        logo_data = None

        # Get logo data if it was requested
        if default_config.get("add_logo", False):
            logo_data = rest[idx]
            idx += 1

        # Process external IDs
        if isinstance(external_data, Exception):
            logger.info("[bold red]Failed to fetch external IDs[/bold red]")
        else:
            try:
                external = typing_cast(dict[str, Any], external_data.json())  # type: ignore
                # Process IMDB ID
                if quickie_search or imdb_id == 0:
                    external_imdb_id = external.get("imdb_id", None)
                    if isinstance(external_imdb_id, str) and external_imdb_id not in ["", " ", "None", "null"]:
                        imdb_id_clean = external_imdb_id.lstrip("t")
                        if imdb_id_clean.isdigit():
                            imdb_id_clean_int = int(imdb_id_clean)
                            if imdb_id_clean_int != int(original_imdb_id) and quickie_search and original_imdb_id != 0:
                                imdb_mismatch = True
                                mismatched_imdb_id = imdb_id_clean_int
                            else:
                                imdb_id = int(imdb_id_clean)
                        else:
                            imdb_id = original_imdb_id
                    else:
                        imdb_id = original_imdb_id
                else:
                    external_imdb_id = external.get("imdb_id", None)
                    if isinstance(external_imdb_id, str) and external_imdb_id not in ["", " ", "None", "null"]:
                        imdb_id_clean = external_imdb_id.lstrip("t")
                        if imdb_id_clean.isdigit():
                            imdb_id_clean_int = int(imdb_id_clean)
                            if imdb_id_clean_int != int(original_imdb_id):
                                logger.warning(
                                    f"[yellow]Warning: TMDb IMDb ID ({imdb_id_clean_int}) does not match provided IMDb ID ({original_imdb_id}). Using original IMDb ID.[/yellow]"
                                )

                    imdb_id = original_imdb_id

                # Process TVDB ID
                if tvdb_id == 0:
                    tvdb_id_str = external.get("tvdb_id", None)
                    tvdb_id = (int(tvdb_id_str) if tvdb_id_str.isdigit() else 0) if isinstance(tvdb_id_str, str) and tvdb_id_str not in ["", " ", "None", "null"] else 0
            except Exception:
                logger.info("[bold red]Failed to process external IDs[/bold red]")

        # Process videos
        if isinstance(videos_data, Exception):
            logger.info("[yellow]Unable to grab videos from TMDb.[/yellow]")
        else:
            try:
                videos = typing_cast(dict[str, Any], videos_data.json())  # type: ignore
                for each in videos.get("results", []):
                    if each.get("site", "") == "YouTube" and each.get("type", "") == "Trailer":
                        youtube = f"https://www.youtube.com/watch?v={each.get('key')}"
                        break
            except Exception:
                logger.info("[yellow]Unable to process videos from TMDb.[/yellow]")

        # Process keywords
        if isinstance(keywords_data, Exception):
            logger.info("[bold red]Failed to fetch keywords[/bold red]")
            keywords = []
        else:
            try:
                kw_json = typing_cast(dict[str, Any], keywords_data.json())  # type: ignore
                if category == "MOVIE":
                    keywords = [keyword["name"].replace(",", " ") for keyword in kw_json.get("keywords", [])]
                else:  # TV
                    keywords = [keyword["name"].replace(",", " ") for keyword in kw_json.get("results", [])]
            except Exception:
                logger.info("[bold red]Failed to process keywords[/bold red]")
                keywords = []

        origin_country = list(media_data.get("origin_country", []))

        # Process credits
        creators = []
        for each in media_data.get("created_by", []):
            name = each.get("original_name") or each.get("name")
            if name:
                creators.append(name)
        # Limit to the first 5 unique names
        creators = list(dict.fromkeys(creators))[:5]

        if isinstance(credits_data, Exception):
            logger.info("[bold red]Failed to fetch credits[/bold red]")
            directors = []
            cast = []
        else:
            try:
                credits = typing_cast(dict[str, Any], credits_data.json())  # type: ignore
                directors = []
                cast = []
                for each in credits.get("cast", []) + credits.get("crew", []):
                    if each.get("known_for_department", "") == "Directing" or each.get("job", "") == "Director":
                        directors.append(each.get("original_name", each.get("name")))
                    elif each.get("known_for_department", "") == "Acting" or each.get("job", "") in {"Actor", "Actress"}:
                        cast.append(each.get("original_name", each.get("name")))
                # Limit to the first 5 unique names
                directors = list(dict.fromkeys(directors))[:5]
                cast = list(dict.fromkeys(cast))[:5]
            except Exception:
                logger.info("[bold red]Failed to process credits[/bold red]")
                directors = []
                cast = []

        # Process genres
        genres_data = await get_genres(media_data)
        genres = genres_data["genre_names"]
        genre_ids = genres_data["genre_ids"]

        # Process logo if needed
        if default_config.get("add_logo", False) and logo_data and not isinstance(logo_data, Exception):
            try:
                logo_json = typing_cast(dict[str, Any], logo_data.json())  # type: ignore
                logo_path = await get_logo(tmdb_id, category or "MOVIE", tmdb_api_key=tmdb_api_key, tmdb_base_url=TMDB_BASE_URL, logo_json=logo_json)
                tmdb_logo = logo_path.split("/")[-1]
            except Exception:
                logger.info("[yellow]Failed to process logo[/yellow]")
                logo_path = ""
                tmdb_logo = ""

    # Use retrieved original language or fallback to TMDB's value
    original_language = manual_language or original_language_from_tmdb

    # Get anime information if applicable
    filename = filename if category == "MOVIE" else path
    mal_id, retrieved_aka, anime, demographic = await get_anime(media_data, Meta({"title": title, "aka": retrieved_aka, "mal_id": 0, "filename": filename}))

    if mal_manual is not None and mal_manual != 0:
        mal_id = mal_manual

    # Check if AKA is too similar to title and clear it if needed
    if retrieved_aka:
        difference = SequenceMatcher(None, title.lower(), retrieved_aka[5:].lower()).ratio()
        if difference >= 0.7 or retrieved_aka[5:].strip() == "" or retrieved_aka[5:].strip().lower() in title.lower():
            retrieved_aka = ""
        if year and f"({year})" in retrieved_aka:
            retrieved_aka = retrieved_aka.replace(f"({year})", "").strip()

    # Build the metadata dictionary
    return {
        "tmdb_adult_media": adult_media,
        "title": title,
        "year": year,
        "release_date": release_date,
        "first_air_date": first_air_date,
        "last_air_date": last_air_date,
        "imdb_id": imdb_id,
        "tvdb_id": tvdb_id,
        "origin_country": origin_country,
        "original_language": original_language,
        "original_title": original_title,
        "keywords": keywords,
        "genres": genres,
        "genre_ids": genre_ids,
        "tmdb_creators": creators,
        "tmdb_directors": directors,
        "tmdb_cast": cast,
        "mal_id": mal_id,
        "anime": anime,
        "demographic": demographic,
        "retrieved_aka": retrieved_aka,
        "artwork_url": poster,
        "tmdb_poster_path": poster_path,
        "logo": logo_path,
        "tmdb_logo": tmdb_logo,
        "backdrop": backdrop,
        "overview": overview,
        "tmdb_type": tmdb_type,
        "runtime": runtime,
        "youtube": youtube,
        "certification": certification,
        "production_companies": production_companies,
        "production_countries": production_countries,
        "networks": networks,
        "imdb_mismatch": imdb_mismatch,
        "mismatched_imdb_id": mismatched_imdb_id,
    }


async def get_keywords(tmdb_id: int, category: str) -> list[str]:
    """Get keywords for a movie or TV show using httpx"""
    endpoint = "movie" if category == "MOVIE" else "tv"
    url = f"{TMDB_BASE_URL}/{endpoint}/{tmdb_id}/keywords"

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, params={"api_key": tmdb_api_key})
            try:
                response.raise_for_status()
                data = response.json()
            except Exception:
                logger.info(f"[bold red]Failed to fetch keywords: {response.status_code}[/bold red]")
                return []

            if category == "MOVIE":
                keywords = [keyword["name"].replace(",", " ") for keyword in data.get("keywords", [])]
            else:  # TV
                keywords = [keyword["name"].replace(",", " ") for keyword in data.get("results", [])]

            return keywords
        except Exception as e:
            logger.info(f"[yellow]Failed to get keywords: {e!s}")
            return []


async def get_genres(response_data: dict[str, Any] | None) -> dict[str, Any]:
    """Extract genres from TMDB response data"""
    if response_data is not None:
        tmdb_genres = response_data.get("genres", [])

        if tmdb_genres:
            # Extract genre names and IDs
            genre_names = [genre["name"].replace(",", " ") for genre in tmdb_genres]
            genre_ids = [str(genre["id"]) for genre in tmdb_genres]

            # Create and return both strings/lists
            return {"genre_names": genre_names, "genre_ids": ", ".join(genre_ids)}

    # Return empty values if no genres found
    return {"genre_names": [], "genre_ids": ""}


async def get_directors(tmdb_id: int, category: str) -> list[str]:
    """Get directors for a movie or TV show using httpx"""
    endpoint = "movie" if category == "MOVIE" else "tv"
    url = f"{TMDB_BASE_URL}/{endpoint}/{tmdb_id}/credits"

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, params={"api_key": tmdb_api_key})
            try:
                response.raise_for_status()
                data = response.json()
            except Exception:
                logger.info(f"[bold red]Failed to fetch credits: {response.status_code}[/bold red]")
                return []

            return [
                each.get("original_name", each.get("name"))
                for each in data.get("cast", []) + data.get("crew", [])
                if each.get("known_for_department", "") == "Directing" or each.get("job", "") == "Director"
            ]
        except Exception as e:
            logger.info(f"[yellow]Failed to get directors: {e!s}")
            return []


async def get_anime(response: dict[str, Any], meta: Meta) -> tuple[int, str, bool, str]:
    tmdb_name = meta.title
    alt_name = "" if meta.aka == "" else meta.aka
    anime = False
    demographic = ""
    genres = typing_cast(list[dict[str, Any]], response.get("genres", []))
    original_language = str(response.get("original_language", "")).lower()
    origin_country = [str(country).upper() for country in typing_cast(list[Any], response.get("origin_country", []))]
    production_countries = [
        str(country.get("iso_3166_1", "")).upper() for country in typing_cast(list[dict[str, Any]], response.get("production_countries", [])) if isinstance(country, dict)
    ]

    is_animation = any(each.get("id") == 16 or str(each.get("name", "")).lower() == "animation" for each in genres)
    is_japanese_production = "JP" in origin_country or "JP" in production_countries
    is_japanese_animation = is_animation and (original_language == "ja" or is_japanese_production)

    if is_japanese_animation:
        romaji, mal_id, _eng_title, _season_year, _episodes, demographic = await get_romaji(
            tmdb_name,
            meta.mal_id,
            meta,
        )
        alt_name = f"AKA {romaji}"
        anime = True
        # mal = AnimeSearch(romaji)
        # mal_id = mal.results[0].mal_id
    else:
        mal_id = 0
    if meta.mal_id != 0:
        mal_id = meta.mal_id
        anime = True
    return mal_id, alt_name, anime, demographic


async def get_romaji(tmdb_name: str, mal: int | None, meta: Meta) -> tuple[str, int, str, str, int, str]:
    media: list[dict[str, Any]] = []
    demographic = "Mina"  # Default to Mina if no tags are found

    # Try AniList query with tmdb_name first, then fallback to meta.filename if no results
    for search_term in [tmdb_name, meta.filename]:
        if not search_term:
            continue
        if mal is None or mal == 0:
            cleaned_name = search_term.replace("-", "").replace("The Movie", "")
            cleaned_name = " ".join(cleaned_name.split())
            query = """
                query ($search: String) {
                    Page (page: 1) {
                        pageInfo {
                            total
                        }
                    media (search: $search, type: ANIME, sort: SEARCH_MATCH) {
                        id
                        idMal
                        title {
                            romaji
                            english
                            native
                        }
                        seasonYear
                        episodes
                        tags {
                            name
                        }
                        externalLinks {
                            id
                            url
                            site
                            siteId
                        }
                    }
                }
            }
            """
            variables: dict[str, str | int] = {"search": cleaned_name}
        else:
            query = """
                query ($search: Int) {
                    Page (page: 1) {
                        pageInfo {
                            total
                        }
                    media (idMal: $search, type: ANIME, sort: SEARCH_MATCH) {
                        id
                        idMal
                        title {
                            romaji
                            english
                            native
                        }
                        seasonYear
                        episodes
                        tags {
                            name
                        }
                    }
                }
            }
            """
            variables = {"search": mal}

        url = "https://graphql.anilist.co"
        anilist_cache = cache_for(meta.base_dir, {"DEFAULT": default_config})
        anilist_key = json.dumps({"search": variables["search"], "mode": "mal" if mal not in (None, 0) else "title"}, sort_keys=True)
        cached_anilist = await anilist_cache.get("anilist", "media", anilist_key)
        if not is_cache_miss(cached_anilist) and isinstance(cached_anilist, dict):
            cached_media = cached_anilist.get("media")
            if isinstance(cached_media, list):
                media = typing_cast(list[dict[str, Any]], cached_media)
                demographic = str(cached_anilist.get("demographic", demographic))
                if media:
                    break
                continue
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(url, json={"query": query, "variables": variables})
                json_data = typing_cast(dict[str, Any], response.json())

                demographics = ["Shounen", "Seinen", "Shoujo", "Josei", "Kodomo", "Mina"]
                for tag in demographics:
                    if tag in response.text:
                        demographic = tag
                        break

                page_data = typing_cast(dict[str, Any], json_data.get("data", {}).get("Page", {}))
                media = typing_cast(list[dict[str, Any]], page_data.get("media", []))
                await anilist_cache.set("anilist", "media", anilist_key, {"media": media, "demographic": demographic}, negative=not bool(media))
                break  # Success - exit retry loop
            except httpx.ReadTimeout, httpx.TimeoutException:
                if attempt < 2:
                    logger.info(f"[yellow]AniList request timed out, retrying ({attempt + 2}/3)...[/yellow]")
                else:
                    logger.error("[red]Failed to get anime specific info from anilist. Continuing without it...")
                    media = []
            except Exception:
                logger.error("[red]Failed to get anime specific info from anilist. Continuing without it...")
                media = []
                break
        if media not in (None, []):
            break  # Found results, stop search_term loop
    search_name = meta.filename.lower() if "subsplease" in meta.filename.lower() else re.sub(r"[^0-9a-zA-Z\[\\]]+", "", tmdb_name.lower().replace(" ", ""))

    # Extract expected season number from various sources
    expected_season = None

    # Try manual_season first
    if meta.manual_season:
        season_match = re.search(r"S?(\d+)", str(meta.manual_season), re.IGNORECASE)
        if season_match:
            expected_season = int(season_match.group(1))

    # Try parsing the filename with anitopy
    if expected_season is None and meta.filename:
        with contextlib.suppress(Exception):
            parsed = typing_cast(dict[str, Any], anitopy_parse_fn(meta.filename) or {})
            if parsed.get("anime_season"):
                expected_season = int(parsed["anime_season"])

    # Fall back to meta.season if available
    if expected_season is None and meta.season:
        season_match = re.search(r"S?(\d+)", str(meta.season), re.IGNORECASE)
        if season_match:
            expected_season = int(season_match.group(1))

    if media not in (None, []):
        result: dict[str, Any] = {"title": {}}
        difference: float = 0.0
        best_match_with_season: dict[str, Any] | None = None
        best_season_similarity = 0.0

        for anime in media:
            anime_title = typing_cast(dict[str, Any], anime.get("title", {}))
            # Extract season number from AniList title if present
            anime_season = None
            for title_value in anime_title.values():
                title_value_str = str(title_value) if title_value else ""
                if title_value_str:
                    season_match = re.search(r"Season (\d+)", title_value_str, re.IGNORECASE)
                    if season_match:
                        anime_season = int(season_match.group(1))
                        break

            # Calculate title similarity
            for title in anime_title.values():
                if title is not None:
                    title_clean = re.sub(
                        "[\u3000-\u303f\u3040-\u309f\u30a0-\u30ff\uff00-\uff9f\u4e00-\u9faf\u3400-\u4dbf]+ (?=[A-Za-z ]+–)",  # noqa: RUF001
                        "",
                        str(title).lower().replace(" ", ""),
                        flags=re.U,
                    )
                    diff = SequenceMatcher(None, title_clean, search_name).ratio()

                    # Prioritize season match if expected_season is set
                    if (
                        expected_season is not None
                        and anime_season is not None
                        and anime_season == expected_season
                        and diff > difference * 0.8
                        and (best_match_with_season is None or diff > best_season_similarity)
                    ):
                        # If season matches and title similarity is reasonable, prefer this
                        best_match_with_season = anime
                        best_season_similarity = diff

                    # Keep track of best overall match
                    if diff > difference:
                        result = anime
                        difference = diff

        # Use season-matched result if found, otherwise use best title match
        if best_match_with_season is not None:
            result = best_match_with_season

        result_title = typing_cast(dict[str, Any], result.get("title", {}))
        romaji = str(result_title.get("romaji") or result_title.get("english") or "")
        mal_id = int(result.get("idMal", 0) or 0)
        eng_title = str(result_title.get("english") or result_title.get("romaji") or "")
        season_year_value = result.get("seasonYear", "")
        season_year = str(season_year_value) if season_year_value is not None else ""
        episodes = int(result.get("episodes", 0) or 0)
    else:
        romaji = eng_title = season_year = ""
        episodes = mal_id = 0
    if mal not in (None, 0):
        mal_id = mal
    if not episodes:
        episodes = 0
    return romaji, mal_id, eng_title, season_year, episodes, demographic


async def get_tmdb_imdb_from_mediainfo(
    mediainfo: dict[str, Any],
    category: str,
    is_disc: bool,
    tmdbid: int,
    imdbid: int | None,
    tvdbid: int | None,
) -> tuple[str, int, int | None, int | None]:
    if not is_disc and mediainfo["media"]["track"][0].get("extra"):
        extra = mediainfo["media"]["track"][0]["extra"]
        for each in extra:
            if each.lower().startswith("tmdb") and not tmdbid:
                with contextlib.suppress(Exception):
                    category, tmdbid = _get_parser().parse_tmdb_id(extra[each], category)
            if each.lower().startswith("imdb") and not imdbid:
                with contextlib.suppress(Exception):
                    imdb_id = extract_imdb_id(extra[each])
                    if imdb_id:
                        imdbid = imdb_id
            if each.lower().startswith("tvdb") and not tvdbid:
                with contextlib.suppress(Exception):
                    tvdb_id = int(extra[each])
                    if tvdb_id:
                        tvdbid = tvdb_id

    return category, tmdbid, imdbid, tvdbid


def extract_imdb_id(value: str) -> int | None:
    """Extract IMDb ID from various formats"""
    patterns = [
        r"/title/(tt\d+)",  # URL format
        r"^(tt\d+)$",  # Direct tt format
        r"^(\d+)$",  # Plain number
    ]

    for pattern in patterns:
        match = re.search(pattern, value)
        if match:
            imdb_id = match.group(1)
            if not imdb_id.startswith("tt"):
                imdb_id = f"tt{imdb_id}"
            return int(imdb_id.replace("tt", ""))

    return None


async def daily_to_tmdb_season_episode(tmdbid: int, date: str | datetime) -> tuple[int, int]:
    date = datetime.fromisoformat(str(date))

    async with httpx.AsyncClient() as client:
        # Get TV show information to get seasons
        response = await client.get(f"{TMDB_BASE_URL}/tv/{tmdbid}", params={"api_key": tmdb_api_key})
        try:
            response.raise_for_status()
            tv_data = response.json()
            seasons = tv_data.get("seasons", [])
        except Exception:
            logger.info(f"[bold red]Failed to fetch TV data: {response.status_code}[/bold red]")
            return 0, 0

        # Find the latest season that aired before or on the target date
        season = 1
        for each in seasons:
            if not each.get("air_date"):
                continue

            air_date = datetime.fromisoformat(each["air_date"])
            if air_date <= date:
                season = int(each["season_number"])

        # Get the specific season information
        season_response = await client.get(f"{TMDB_BASE_URL}/tv/{tmdbid}/season/{season}", params={"api_key": tmdb_api_key})
        try:
            season_response.raise_for_status()
            season_data = season_response.json()
            season_info = season_data.get("episodes", [])
        except Exception:
            logger.info(f"[bold red]Failed to fetch season data: {season_response.status_code}[/bold red]")
            return 0, 0

        # Find the episode that aired on the target date
        episode = 1
        for each in season_info:
            if str(each.get("air_date", "")) == str(date.date()):
                episode = int(each["episode_number"])
                break
        else:
            logger.info(f"[yellow]Unable to map the date ([bold yellow]{date!s}[/bold yellow]) to a Season/Episode number")

    return season, episode


async def get_episode_details(
    tmdb_id: int,
    season_number: int,
    episode_number: int,
) -> dict[str, Any]:
    logger.debug(f"[cyan]Fetching episode details for TMDb ID: {tmdb_id}, Season: {season_number}, Episode: {episode_number}[/cyan]")
    async with httpx.AsyncClient() as client:
        try:
            # Get episode details
            response = await client.get(
                f"{TMDB_BASE_URL}/tv/{tmdb_id}/season/{season_number}/episode/{episode_number}",
                params={"api_key": tmdb_api_key, "append_to_response": "images,credits,external_ids"},
            )
            try:
                response.raise_for_status()
                episode_data = typing_cast(dict[str, Any], response.json())
            except Exception:
                logger.info(f"[bold red]Failed to fetch episode data: {response.status_code}[/bold red]")
                return {}

            logger.debug(f"[cyan]Episode Data: {json.dumps(episode_data, indent=2)[:600]}...")

            # Extract relevant information
            crew_list: list[dict[str, Any]] = []
            guest_stars_list: list[dict[str, Any]] = []
            episode_info: dict[str, Any] = {
                "name": episode_data.get("name", ""),
                "overview": episode_data.get("overview", ""),
                "air_date": episode_data.get("air_date", ""),
                "still_path": episode_data.get("still_path", ""),
                "vote_average": episode_data.get("vote_average", 0),
                "episode_number": episode_data.get("episode_number", 0),
                "season_number": episode_data.get("season_number", 0),
                "runtime": episode_data.get("runtime", 0),
                "crew": crew_list,
                "guest_stars": guest_stars_list,
                "director": "",
                "writer": "",
                "imdb_id": episode_data.get("external_ids", {}).get("imdb_id", ""),
            }

            # Extract crew information
            for crew_member in episode_data.get("crew", []):
                crew_list.append({"name": crew_member.get("name", ""), "job": crew_member.get("job", ""), "department": crew_member.get("department", "")})

                # Extract director and writer specifically
                if crew_member.get("job") == "Director":
                    episode_info["director"] = crew_member.get("name", "")
                elif crew_member.get("job") == "Writer":
                    episode_info["writer"] = crew_member.get("name", "")

            # Extract guest stars
            guest_stars_list.extend(
                [
                    {"name": guest.get("name", ""), "character": guest.get("character", ""), "profile_path": guest.get("profile_path", "")}
                    for guest in episode_data.get("guest_stars", [])
                ]
            )

            # Get full image URLs
            if episode_info["still_path"]:
                episode_info["still_url"] = f"https://image.tmdb.org/t/p/original{episode_info['still_path']}"

            return episode_info

        except Exception:
            logger.error(f"[red]Error fetching episode details for {tmdb_id}[/red]")
            logger.info(f"[red]Season: {season_number}, Episode: {episode_number}[/red]")
            return {}


async def get_season_details(
    tmdb_id: int,
    season_number: int,
) -> dict[str, Any]:
    logger.debug(f"[cyan]Fetching season details for TMDb ID: {tmdb_id}, Season: {season_number}[/cyan]")
    async with httpx.AsyncClient() as client:
        try:
            # Get season details
            response = await client.get(f"{TMDB_BASE_URL}/tv/{tmdb_id}/season/{season_number}", params={"api_key": tmdb_api_key, "append_to_response": "images,credits"})
            try:
                response.raise_for_status()
                season_data = typing_cast(dict[str, Any], response.json())

                # Extract only relevant information
                episodes_list: list[dict[str, Any]] = []
                season_info: dict[str, Any] = {
                    "_id": season_data.get("_id"),
                    "air_date": season_data.get("air_date"),
                    "name": season_data.get("name"),
                    "overview": season_data.get("overview"),
                    "id": season_data.get("id"),
                    "poster_path": season_data.get("poster_path"),
                    "season_number": season_data.get("season_number"),
                    "vote_average": season_data.get("vote_average"),
                    "vote_count": season_data.get("vote_count"),
                    "episodes": episodes_list,
                }

                # Extract minimal episode information
                episodes_list.extend(
                    [
                        {
                            "air_date": episode.get("air_date"),
                            "episode_number": episode.get("episode_number"),
                            "episode_type": episode.get("episode_type"),
                            "id": episode.get("id"),
                            "name": episode.get("name"),
                            "overview": episode.get("overview"),
                            "runtime": episode.get("runtime"),
                            "season_number": episode.get("season_number"),
                            "still_path": episode.get("still_path"),
                            "vote_average": episode.get("vote_average"),
                            "vote_count": episode.get("vote_count"),
                        }
                        for episode in season_data.get("episodes", [])
                    ]
                )

                # Include poster images if available
                if "images" in season_data and "posters" in season_data["images"]:
                    season_info["images"] = {"posters": season_data["images"]["posters"]}

                # Include main cast/crew if available (top-level only, not per-episode)
                if "credits" in season_data and "cast" in season_data["credits"]:
                    season_info["credits"] = {"cast": season_data["credits"]["cast"]}

                logger.debug(f"[cyan]Extracted season data: {json.dumps(season_info, indent=2)[:600]}...[/cyan]")
                return season_info

            except Exception:
                logger.info(f"[bold red]Failed to fetch season data: {response.status_code}[/bold red]")
                return {}

        except Exception:
            logger.error(f"[red]Error fetching season details for {tmdb_id}[/red]")
            logger.info(f"[red]Season: {season_number}[/red]")
            return {}


async def get_logo(
    tmdb_id: int,
    category: str,
    logo_languages: list[str] | str | None = None,
    tmdb_api_key: str | None = None,
    tmdb_base_url: str | None = None,
    logo_json: dict[str, Any] | None = None,
) -> str:
    logo_path = ""
    if logo_languages and isinstance(logo_languages, str) and "," in logo_languages:
        logo_languages = [lang.strip() for lang in logo_languages.split(",")]
        logger.debug(f"[cyan]Parsed logo languages from comma-separated string: {logo_languages}[/cyan]")

    elif logo_languages is None:
        # Get preferred languages in order (from config, then 'en' as fallback)
        logo_languages = [default_config.get("logo_language", "en"), "en"]
    elif isinstance(logo_languages, str):
        logo_languages = [logo_languages, "en"]

    # Remove duplicates while preserving order
    logo_languages = list(dict.fromkeys(logo_languages))

    logger.debug(f"[cyan]Looking for logos in languages (in order): {logo_languages}[/cyan]")

    try:
        # Use provided logo_json if available, otherwise fetch it
        image_data = None
        if logo_json:
            image_data = logo_json
            logger.debug("[cyan]Using provided logo_json data instead of making an HTTP request[/cyan]")
        else:
            # Make HTTP request only if logo_json is not provided
            async with httpx.AsyncClient() as client:
                endpoint = "tv" if category == "TV" else "movie"
                # Fall back to module-level values when caller did not supply overrides
                resolved_api_key = tmdb_api_key if tmdb_api_key is not None else globals()["tmdb_api_key"]
                resolved_base_url = tmdb_base_url if tmdb_base_url is not None else TMDB_BASE_URL
                image_response = await client.get(f"{resolved_base_url}/{endpoint}/{tmdb_id}/images", params={"api_key": resolved_api_key})
                try:
                    image_response.raise_for_status()
                    image_data = image_response.json()
                except Exception:
                    logger.info(f"[bold red]Failed to fetch image data: {image_response.status_code}[/bold red]")
                    return ""

        if image_data:
            logger.debug(f"[cyan]Image Data: {json.dumps(image_data, indent=2)[:500]}...")

        image_data = typing_cast(dict[str, Any], image_data)
        logos = image_data.get("logos", [])

        # Only look for logos that match our specified languages
        for language in logo_languages:
            matching_logo = next((logo for logo in logos if logo.get("iso_639_1") == language), None)
            if matching_logo is not None:
                logo_path = f"https://image.tmdb.org/t/p/original{matching_logo['file_path']}"
                logger.debug(f"[cyan]Found logo in language '{language}': {logo_path}[/cyan]")
                break

        # fallback to getting logo with null language if no match found, especially useful for movies it seems
        if not logo_path:
            null_language_logo = next((logo for logo in logos if logo.get("iso_639_1") is None or logo.get("iso_639_1") == ""), None)
            if null_language_logo:
                logo_path = f"https://image.tmdb.org/t/p/original{null_language_logo['file_path']}"
                logger.debug(f"[cyan]Found logo with null language: {logo_path}[/cyan]")

        if not logo_path:
            logger.debug("[yellow]No suitable logo found in preferred languages or null language[/yellow]")

    except Exception as e:
        logger.error(f"[red]Error fetching logo: {e}[/red]")

    return logo_path


async def get_tmdb_translations(
    tmdb_id: int,
    category: str,
    target_language: str = "en",
) -> str:
    """Get translations from TMDb API"""
    endpoint = "movie" if category == "MOVIE" else "tv"
    url = f"{TMDB_BASE_URL}/{endpoint}/{tmdb_id}/translations"

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, params={"api_key": tmdb_api_key})
            response.raise_for_status()
            data = response.json()

            # Look for target language translation
            for translation in data.get("translations", []):
                if translation.get("iso_639_1") == target_language:
                    translated_data = translation.get("data", {})
                    translated_title = translated_data.get("title") or translated_data.get("name")

                    if translated_title:
                        logger.debug(f"[cyan]Found TMDb translation: '{translated_title}'[/cyan]")

                    return translated_title or ""

            logger.debug(f"[yellow]No {target_language} translation found in TMDb[/yellow]")
            return ""

        except Exception as e:
            logger.debug(f"[yellow]TMDb translation fetch failed: {e}[/yellow]")
            return ""


async def set_tmdb_metadata(meta: Meta, filename: str | None = None) -> None:
    if not meta.edit:
        # if we have these fields already, we probably got them from a multi id searching
        # and don't need to fetch them again
        essential_fields = ["title", "year", "genres", "overview"]
        tmdb_metadata_populated = all(meta.get(field) is not None for field in essential_fields) and bool(meta.get("title"))
    else:
        # if we're in that blasted edit mode, ignore any previous set data and get fresh
        tmdb_metadata_populated = False

    if not tmdb_metadata_populated:
        max_attempts = 2
        delay_seconds = 5
        for attempt in range(1, max_attempts + 1):
            try:
                tmdb_metadata = await tmdb_other_meta(
                    tmdb_id=meta.tmdb_id,
                    path=meta.path,
                    search_year=meta.search_year,
                    category=meta.category,
                    imdb_id=meta.imdb_id,
                    manual_language=meta.manual_language if isinstance(meta.manual_language, str) else None,
                    anime=meta.anime,
                    mal_manual=int(meta.mal_manual) if isinstance(meta.mal_manual, int) or (isinstance(meta.mal_manual, str) and meta.mal_manual.isdigit()) else None,
                    aka=meta.aka,
                    original_language=meta.original_language,
                    poster=meta.artwork_url,
                    debug=meta.debug,
                    mode=(meta.mode if meta.mode is not None else "cli"),
                    tvdb_id=meta.tvdb_id,
                    quickie_search=meta.quickie_search,
                    filename=filename,
                    base_dir=meta.base_dir,
                    config=default_config,
                )

                if tmdb_metadata and all(tmdb_metadata.get(field) for field in ["title", "year"]):
                    meta.update(tmdb_metadata)
                    if meta.retrieved_aka is not None:
                        meta.aka = meta.retrieved_aka
                    break
                error_msg = f"Failed to retrieve essential metadata from TMDB ID: {meta.tmdb_id}"
                logger.debug(f"[bold red]{error_msg}[/bold red]")
                if attempt < max_attempts:
                    logger.info(f"[yellow]Retrying TMDB metadata fetch in {delay_seconds} seconds... (Attempt {attempt + 1}/{max_attempts})[/yellow]")
                    await asyncio.sleep(delay_seconds)
                else:
                    raise ValueError(error_msg)
            except Exception as e:
                error_msg = f"TMDB metadata retrieval failed for ID {meta.tmdb_id}: {e!s}"
                logger.debug(f"[bold red]{error_msg}[/bold red]")
                if attempt < max_attempts:
                    logger.info(f"[yellow]Retrying TMDB metadata fetch in {delay_seconds} seconds... (Attempt {attempt + 1}/{max_attempts})[/yellow]")
                    await asyncio.sleep(delay_seconds)
                else:
                    logger.info(f"[red]Catastrophic error getting TMDB data using ID {meta.tmdb_id}[/red]")
                    logger.info(f"[red]Check category is set correctly, UA was using {meta.category}[/red]")
                    raise RuntimeError(error_msg) from e


async def get_tmdb_localized_data(meta: Meta, data_type: str, language: str, append_to_response: str) -> dict[str, Any]:
    tmdb_data: dict[str, Any] = {}
    if meta.tmdb is None:
        return tmdb_data
    endpoint = None
    if data_type == "main":
        endpoint = f"/{meta.category.lower()}/{meta.tmdb}"
    elif data_type == "season":
        season = meta.season_int
        if season is None:
            return tmdb_data
        endpoint = f"/tv/{meta.tmdb}/season/{season}"
    elif data_type == "episode":
        season = meta.season_int
        episode = meta.episode_int
        if season is None or episode is None:
            return tmdb_data
        endpoint = f"/tv/{meta.tmdb}/season/{season}/episode/{episode}"

    url = f"{TMDB_BASE_URL}{endpoint}"
    params = {"api_key": tmdb_api_key, "language": language}
    if append_to_response:
        params.update({"append_to_response": append_to_response})

    logger.debug(
        "[green]Requesting localized data from TMDB.\n"
        f"Type: '{data_type}'.\n"
        f"Language: '{language}'\n"
        f"Append to response: '{append_to_response}'\n"
        f"Endpoint: '{endpoint}'[/green]\n"
    )

    cache = cache_for(meta.base_dir, {"DEFAULT": default_config})
    cache_key = json.dumps({"id": meta.tmdb, "category": meta.category, "type": data_type, "language": language, "append": append_to_response}, sort_keys=True)
    cached_result = await cache.get("tmdb", "localized", cache_key)
    if not is_cache_miss(cached_result) and isinstance(cached_result, dict):
        return cached_result

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, params=params)
            if response.status_code == 200:
                tmdb_data = response.json()
                if isinstance(tmdb_data, dict):
                    await cache.set("tmdb", "localized", cache_key, tmdb_data)
                    return tmdb_data
            logger.info(f"[red]Request failed for {url}: Status code {response.status_code}[/red]")
    except httpx.RequestError as e:
        logger.info(f"[red]Request failed for {url}: {e}[/red]")
    return tmdb_data
