# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import json
from typing import Any, cast

import cli_ui
import httpx

from src.console import logger
from src.meta import Meta
from src.metadata_cache import cache_for, is_cache_miss


class TvmazeManager:
    async def search_tvmaze(
        self,
        filename: str,
        year: str,
        imdb_id: int | str | None,
        tvdb_id: int | str | None,
        manual_date: str | None = None,
        tvmaze_manual: int | str | None = None,
        return_full_tuple: bool = False,
        base_dir: str = "",
        config: dict[str, Any] | None = None,
    ) -> int | tuple[int, int, int]:
        """Searches TVMaze for a show using TVDB ID, IMDb ID, or a title query.

        - If `return_full_tuple=True`, returns `(tvmaze_id, imdb_id, tvdb_id)`.
        - Otherwise, only returns `tvmaze_id`.
        """
        logger.debug(f"[cyan]Searching TVMaze for TVDB {tvdb_id} or IMDB {imdb_id} or {filename} ({year}) and returning {return_full_tuple}.[/cyan]")
        # Convert TVDB ID to integer
        if isinstance(tvdb_id, (int, str)) and tvdb_id not in ("", "0"):
            try:
                tvdb_id = int(tvdb_id)
            except ValueError, TypeError:
                logger.error(f"[red]Error: tvdb_id is not a valid integer. Received: {tvdb_id}[/red]")
                tvdb_id = 0
        else:
            tvdb_id = 0

        # Handle IMDb ID - ensure it's an integer without tt prefix
        try:
            if isinstance(imdb_id, str) and imdb_id.startswith("tt"):
                imdb_id = int(imdb_id[2:])
            elif isinstance(imdb_id, (int, str)) and imdb_id not in ("", "0"):
                imdb_id = int(imdb_id)
            else:
                imdb_id = 0
        except ValueError, TypeError:
            logger.error(f"[red]Error: imdb_id is not a valid integer. Received: {imdb_id}[/red]")
            imdb_id = 0

        # If manual selection has been provided, return it directly
        if tvmaze_manual:
            try:
                tvmaze_id = int(tvmaze_manual)
                return (tvmaze_id, imdb_id, tvdb_id) if return_full_tuple else tvmaze_id
            except ValueError, TypeError:
                logger.error(f"[red]Error: tvmaze_manual is not a valid integer. Received: {tvmaze_manual}[/red]")
                tvmaze_id = 0
                return (tvmaze_id, imdb_id, tvdb_id) if return_full_tuple else tvmaze_id

        tvmaze_id = 0
        results: list[dict[str, Any]] = []

        async def fetch_tvmaze_data(url: str, params: dict[str, Any]) -> list[dict[str, Any]]:
            """Helper function to fetch data from TVMaze API."""
            response = await self._make_tvmaze_request(url, params, base_dir, config)
            if response:
                return [response] if isinstance(response, dict) else response
            return []

        if tvdb_id:
            results.extend(await fetch_tvmaze_data("https://api.tvmaze.com/lookup/shows", {"thetvdb": tvdb_id}))

        if not results and imdb_id:
            results.extend(await fetch_tvmaze_data("https://api.tvmaze.com/lookup/shows", {"imdb": f"tt{imdb_id:07d}"}))

        if not results:
            search_resp = await fetch_tvmaze_data("https://api.tvmaze.com/search/shows", {"q": filename})
            results.extend([each["show"] for each in search_resp if "show" in each])

        if not results:
            first_two_words = " ".join(filename.split()[:2])
            if first_two_words and first_two_words != filename:
                search_resp = await fetch_tvmaze_data("https://api.tvmaze.com/search/shows", {"q": first_two_words})
                results.extend([each["show"] for each in search_resp if "show" in each])

        # Deduplicate results by TVMaze ID
        seen: set[int] = set()
        unique_results: list[dict[str, Any]] = []
        for show in results:
            show_id = int(show["id"])
            if show_id not in seen:
                seen.add(show_id)
                unique_results.append(show)

        if not unique_results:
            logger.debug("[yellow]No TVMaze results found.[/yellow]")
            return (tvmaze_id, imdb_id, tvdb_id) if return_full_tuple else tvmaze_id

        # Manual selection process
        if manual_date is not None:
            logger.info("[bold]Search results:[/bold]")
            for idx, show in enumerate(unique_results):
                logger.info(f"[bold red]{idx + 1}[/bold red]. [green]{show.get('name', 'Unknown')} (TVmaze ID:[/green] [bold red]{show['id']}[/bold red])")
                logger.info(f"[yellow]   Premiered: {show.get('premiered', 'Unknown')}[/yellow]")
                logger.info(f"   Externals: {json.dumps(show.get('externals', {}), indent=2)}")

            while True:
                try:
                    choice_raw = cli_ui.ask_string(f"Enter the number of the correct show (1-{len(unique_results)}) or 0 to skip: ")
                    choice = int((choice_raw or "").strip())
                    if choice == 0:
                        logger.info("Skipping selection.")
                        break
                    if 1 <= choice <= len(unique_results):
                        selected_show = unique_results[choice - 1]
                        tvmaze_id = int(selected_show["id"])
                        # set the tvdb id since it's sure to be correct
                        # won't get returned outside manual date since full tuple is not returned
                        if "externals" in selected_show and "thetvdb" in selected_show["externals"]:
                            new_tvdb_id = selected_show["externals"]["thetvdb"]
                            if new_tvdb_id:
                                tvdb_id = int(new_tvdb_id)
                                logger.info(f"[green]Updated TVDb ID to: {tvdb_id}[/green]")
                        logger.info(f"Selected show: {selected_show.get('name')} (TVmaze ID: {tvmaze_id})")
                        break
                    logger.info(f"Invalid choice. Please choose a number between 1 and {len(unique_results)}, or 0 to skip.")
                except ValueError:
                    logger.info("Invalid input. Please enter a number.")
        else:
            selected_show = unique_results[0]
            tvmaze_id = int(selected_show["id"])
            logger.debug(f"[cyan]Automatically selected show: {selected_show.get('name')} (TVmaze ID: {tvmaze_id})[/cyan]")

        if return_full_tuple:
            logger.debug(
                f"[cyan]Returning TVmaze ID: {tvmaze_id} (type: {type(tvmaze_id).__name__}), IMDb ID: {imdb_id} (type: {type(imdb_id).__name__}), TVDB ID: {tvdb_id} (type: {type(tvdb_id).__name__})[/cyan]"
            )
        else:
            logger.debug(f"[cyan]Returning TVmaze ID: {tvmaze_id} (type: {type(tvmaze_id).__name__})[/cyan]")
        return (tvmaze_id, imdb_id, tvdb_id) if return_full_tuple else tvmaze_id

    async def _make_tvmaze_request(
        self,
        url: str,
        params: dict[str, Any],
        base_dir: str = "",
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any] | list[dict[str, Any]] | None:
        """Sync function to make the request inside ThreadPoolExecutor."""
        cache_key = json.dumps({"url": url, "params": params}, sort_keys=True, default=str)
        cache = cache_for(base_dir, config)
        cached = await cache.get("tvmaze", "response", cache_key)
        if not is_cache_miss(cached) and (cached is None or isinstance(cached, (dict, list))):
            return cast(dict[str, Any] | list[dict[str, Any]] | None, cached)
        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                resp = await client.get(url, params=params, timeout=10)
                if resp.status_code == 200:
                    data: Any = resp.json()
                    if isinstance(data, dict):
                        await cache.set("tvmaze", "response", cache_key, data)
                        return cast(dict[str, Any], data)
                    if isinstance(data, list):
                        result = [cast(dict[str, Any], item) for item in data if isinstance(item, dict)]
                        await cache.set("tvmaze", "response", cache_key, result, negative=not bool(result))
                        return result
                    return None
                if resp.status_code == 404:
                    await cache.set("tvmaze", "response", cache_key, None, negative=True)
                    return None
                return None
        except httpx.HTTPStatusError as e:
            logger.info(f"[ERROR] TVmaze API error: {e.response.status_code}", extra={"markup": False})
        except httpx.RequestError as e:
            logger.info(f"[ERROR] Network error while accessing TVmaze: {e}", extra={"markup": False})
        return cast(dict[str, Any], {})

    async def get_tvmaze_episode_data(
        self,
        tvmaze_id: int,
        season: int,
        episode: int,
        meta: Meta | None = None,
    ) -> dict[str, Any] | None:
        url = f"https://api.tvmaze.com/shows/{tvmaze_id}/episodebynumber"
        params = {"season": season, "number": episode}

        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                response = await client.get(url, params=params, timeout=10.0)
                response.raise_for_status()
                data = response.json()

                if data:
                    # Get show data for additional information
                    show_data: dict[str, Any] = {}
                    if "show" in data.get("_links", {}) and "href" in data["_links"]["show"]:
                        show_url = data["_links"]["show"]["href"]
                        show_name = data["_links"]["show"].get("name", "")

                        show_response = await client.get(show_url, timeout=10.0)
                        show_data = show_response.json() if show_response.status_code == 200 else {"name": show_name}

                    # Clean HTML tags from summary
                    summary = data.get("summary", "")
                    if summary:
                        summary = summary.replace("<p>", "").replace("</p>", "").strip()

                    # Format the response in a consistent structure
                    return {
                        "episode_name": data.get("name", ""),
                        "overview": summary,
                        "season_number": data.get("season", season),
                        "episode_number": data.get("number", episode),
                        "air_date": data.get("airdate", ""),
                        "runtime": data.get("runtime", 0),
                        "series_name": show_data.get("name", data.get("_links", {}).get("show", {}).get("name", "")),
                        "series_overview": show_data.get("summary", "").replace("<p>", "").replace("</p>", "").strip(),
                        "image": data.get("image", {}).get("original", None) if data.get("image") else None,
                        "image_medium": data.get("image", {}).get("medium", None) if data.get("image") else None,
                        "series_image": show_data.get("image", {}).get("original", None) if show_data.get("image") else None,
                        "series_image_medium": show_data.get("image", {}).get("medium", None) if show_data.get("image") else None,
                    }

                logger.info(f"[yellow]No episode data found for S{season:02d}E{episode:02d}[/yellow]")
                return None

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404 and meta is not None:
                logger.info("[yellow]Episode not found using season/episode, trying date-based lookup...[/yellow]")

                # Try to get airdate from meta data
                airdate = None

                # First priority: manual_date
                if meta and meta.manual_date:
                    manual_date = meta.manual_date
                    if isinstance(manual_date, str):
                        airdate = manual_date
                    logger.debug(f"[cyan]Using manual_date: {airdate}[/cyan]")

                # Second priority: find airdate from tvdb_episode_data using tvdb_episode_id
                elif meta and meta.tvdb_episode_id and meta.tvdb_episode_data:
                    tvdb_episode_id = meta.tvdb_episode_id
                    tvdb_data = meta.tvdb_episode_data

                    episodes: list[dict[str, Any]] = []
                    if isinstance(tvdb_data, dict):
                        tvdb_data_dict = tvdb_data
                        tvdb_episodes_raw = tvdb_data_dict.get("episodes", [])
                        if isinstance(tvdb_episodes_raw, list):
                            episodes = list(cast(list[dict[str, Any]], tvdb_episodes_raw))
                    elif isinstance(tvdb_data, list):
                        episodes = list(cast(list[dict[str, Any]], tvdb_data))

                    for ep in episodes:
                        if ep.get("id") == tvdb_episode_id:
                            ep_airdate = ep.get("aired")
                            if isinstance(ep_airdate, str):
                                airdate = ep_airdate
                                logger.debug(f"[cyan]Found airdate from TVDB episode data: {airdate}[/cyan]")
                                break

                    if not airdate and meta.debug:
                        logger.info(f"[yellow]Could not find airdate for TVDB episode ID {tvdb_episode_id}[/yellow]")

                # Try date-based lookup if we have an airdate
                if isinstance(airdate, str) and airdate:
                    logger.debug(f"[cyan]Attempting TVMaze lookup by date: {airdate}[/cyan]")
                    return await self.get_tvmaze_episode_data_by_date(tvmaze_id, airdate)
                logger.debug("[yellow]No airdate available for fallback lookup[/yellow]")
                return None
            return None
        except httpx.RequestError as e:
            logger.info(f"[red]TVMaze Request error occurred: {e}[/red]")
            return None
        except Exception as e:
            logger.info(f"[red]TVMaze Error fetching TVMaze episode data: {e}[/red]")
            return None

    async def get_tvmaze_episode_data_by_date(self, tvmaze_id: int, airdate: str) -> dict[str, Any] | None:
        url = f"https://api.tvmaze.com/shows/{tvmaze_id}/episodesbydate"
        params = {"date": airdate}

        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                response = await client.get(url, params=params, timeout=10.0)
                response.raise_for_status()
                data = response.json()

                if data and len(data) > 0:
                    # Take the first episode from the date (in case multiple episodes aired on same date)
                    episode_data = data[0]

                    # Get show data for additional information
                    show_data: dict[str, Any] = {}
                    if "show" in episode_data.get("_links", {}) and "href" in episode_data["_links"]["show"]:
                        show_url = episode_data["_links"]["show"]["href"]
                        show_name = episode_data["_links"]["show"].get("name", "")

                        show_response = await client.get(show_url, timeout=10.0)
                        show_data = show_response.json() if show_response.status_code == 200 else {"name": show_name}

                    # Clean HTML tags from summary
                    summary = episode_data.get("summary", "")
                    if summary:
                        summary = summary.replace("<p>", "").replace("</p>", "").strip()

                    # Format the response in a consistent structure
                    return {
                        "episode_name": episode_data.get("name", ""),
                        "overview": summary,
                        "season_number": episode_data.get("season", 0),
                        "episode_number": episode_data.get("number", 0),
                        "air_date": episode_data.get("airdate", ""),
                        "runtime": episode_data.get("runtime", 0),
                        "series_name": show_data.get("name", episode_data.get("_links", {}).get("show", {}).get("name", "")),
                        "series_overview": show_data.get("summary", "").replace("<p>", "").replace("</p>", "").strip(),
                        "image": episode_data.get("image", {}).get("original", None) if episode_data.get("image") else None,
                        "image_medium": episode_data.get("image", {}).get("medium", None) if episode_data.get("image") else None,
                        "series_image": show_data.get("image", {}).get("original", None) if show_data.get("image") else None,
                        "series_image_medium": show_data.get("image", {}).get("medium", None) if show_data.get("image") else None,
                    }

                logger.info(f"[yellow]No episode data found for date {airdate}[/yellow]")
                return None

        except httpx.HTTPStatusError as e:
            logger.info(f"[red]TVMaze HTTP error occurred in episodesbydate: {e.response.status_code} - {e.response.text}[/red]")
            return None
        except httpx.RequestError as e:
            logger.info(f"[red]TVMaze Request error occurred in episodesbydate: {e}[/red]")
            return None
        except Exception as e:
            logger.info(f"[red]TVMaze Error fetching TVMaze episode data by date: {e}[/red]")
            return None


tvmaze_manager = TvmazeManager()
