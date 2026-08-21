# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import uuid
from typing import Any, cast

import httpx

from src.bbcode import BBCODE
from src.console import logger
from src.meta import Meta


class BtnIdManager:
    @staticmethod
    async def generate_guid() -> str:
        return str(uuid.uuid4())

    @staticmethod
    async def get_btn_torrents(btn_api: str, btn_id: str, api_url: str = "https://api.broadcasthe.net/") -> tuple[int, int]:
        imdb_id = 0
        tvdb_id = 0
        logger.debug("Fetching BTN data...", extra={"markup": False})
        post_query_url = api_url
        post_data = {"jsonrpc": "2.0", "id": (await BtnIdManager.generate_guid())[:8], "method": "getTorrentsSearch", "params": [btn_api, {"id": btn_id}, 50]}
        headers = {"Content-Type": "application/json"}

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(post_query_url, headers=headers, json=post_data, timeout=10)
                response.raise_for_status()
                try:
                    data = cast(dict[str, Any], response.json())
                except ValueError as e:
                    logger.info(f"[ERROR] Failed to parse BTN response as JSON: {e}", extra={"markup": False})
                    logger.info(f"Response content: {response.text[:200]}...", extra={"markup": False})
                    return 0, 0
        except Exception as e:
            logger.info(f"[ERROR] Failed to fetch BTN data: {e}", extra={"markup": False})
            return 0, 0

        if not data:
            logger.info("[ERROR] BTN API response is empty or invalid.", extra={"markup": False})
            return 0, 0

        error = data.get("error")
        if isinstance(error, dict):
            error_map = cast(dict[str, Any], error)
            code = error_map.get("code", "unknown")
            message = str(error_map.get("message", "Unknown BTN API error"))
            if "unauthorized ip" in message.lower():
                logger.info(f"[red]BTN API error: Unauthorized IP address (code {code}).[/red]")
                logger.info("[yellow]Your current public IP isn't whitelisted for your BTN API key.[/yellow]")
            else:
                logger.info(f"[red]BTN API error (code {code}): {message}[/red]")
            logger.debug(data)
            return 0, 0

        logger.debug(f"[green]BTN data fetched successfully for BTN ID {data.get('id')}[/green]")

        result = data.get("result")
        if isinstance(result, dict) and "torrents" in result:
            torrents = cast(dict[str, dict[str, Any]], result["torrents"])
            first_torrent = next(iter(torrents.values()), None)
            if first_torrent:
                imdb_id = first_torrent.get("ImdbID")
                tvdb_id = first_torrent.get("TvdbID")

                if imdb_id or tvdb_id:
                    return int(imdb_id or 0), int(tvdb_id or 0)
        logger.debug("[red]No IMDb or TVDb ID found.")
        return 0, 0

    @staticmethod
    async def get_bhd_torrents(
        bhd_api: str,
        bhd_rss_key: str,
        meta: Meta,
        skip_tracker_descriptions: bool = False,
        info_hash: str | None = None,
        filename: str | None = None,
        foldername: str | None = None,
        torrent_id: int | None = None,
    ) -> tuple[int, int]:
        imdb = 0
        tmdb = 0
        logger.debug("Fetching BEYONDHD data...", extra={"markup": False})
        post_query_url = f"https://beyond-hd.me/api/torrents/{bhd_api}"

        post_data = {"action": "details", "torrent_id": torrent_id} if torrent_id is not None else {"action": "search", "rsskey": bhd_rss_key}

        if info_hash:
            post_data["info_hash"] = info_hash

        if filename:
            post_data["file_name"] = filename

        if foldername:
            post_data["folder_name"] = foldername

        headers = {"Content-Type": "application/json"}

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(post_query_url, headers=headers, json=post_data, timeout=10)
                response.raise_for_status()
                try:
                    data = response.json()
                except ValueError as e:
                    logger.info(f"[ERROR] Failed to parse BEYONDHD response as JSON: {e}", extra={"markup": False})
                    logger.info(f"Response content: {response.text[:200]}...", extra={"markup": False})
                    return 0, 0
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            logger.info(f"[ERROR] Failed to fetch BEYONDHD data: {e}", extra={"markup": False})
            return 0, 0

        if data.get("status_code") == 0 or data.get("success") is False:
            error_message = data.get("status_message", "Unknown BEYONDHD API error")
            logger.info(f"[ERROR] BEYONDHD API error: {error_message}", extra={"markup": False})
            return 0, 0

        # Handle different response formats from BEYONDHD API
        first_result = None

        # For search results that return a list
        if "results" in data and isinstance(data["results"], list) and data["results"]:
            first_result = data["results"][0]

        # For single torrent details that return a dictionary in "result"
        elif "result" in data and isinstance(data["result"], dict):
            first_result = data["result"]

        if not first_result:
            logger.info("No valid results found in BEYONDHD API response.", extra={"markup": False})
            return 0, 0

        name = str(first_result.get("name", "")).lower()
        if not torrent_id:
            torrent_id = first_result.get("id", 0)

        # Check if description is just "1" indicating we need to fetch it separately
        description_value = first_result.get("description")
        if description_value == 1 or description_value == "1":
            desc_post_data = {
                "action": "description",
                "torrent_id": torrent_id,
            }

            try:
                async with httpx.AsyncClient() as client:
                    desc_response = await client.post(post_query_url, headers=headers, json=desc_post_data, timeout=10)
                    desc_response.raise_for_status()
                    desc_data = desc_response.json()

                    if desc_data.get("status_code") == 1 and desc_data.get("success") is True:
                        description = str(desc_data.get("result", ""))
                        logger.info("Successfully retrieved full description", extra={"markup": False})
                    else:
                        description = ""
                        error_message = desc_data.get("status_message", "Unknown BEYONDHD API error")
                        logger.info(f"[ERROR] Failed to fetch description: {error_message}", extra={"markup": False})
            except (httpx.RequestError, httpx.HTTPStatusError) as e:
                logger.info(f"[ERROR] Failed to fetch description: {e}", extra={"markup": False})
                description = ""
        else:
            # Use the description from the initial response
            description = str(description_value) if description_value is not None else ""

        imdb_id = first_result.get("imdb_id", "").replace("tt", "") if first_result.get("imdb_id") else 0
        imdb = int(imdb_id or 0)

        tmdb = 0
        raw_tmdb_id = first_result.get("tmdb_id", "")
        if raw_tmdb_id and raw_tmdb_id != "0":
            parsed_cat, parsed_tmdb_id = await BtnIdManager.parse_tmdb_id(raw_tmdb_id, meta.category)
            if parsed_cat is not None:
                meta.category = parsed_cat
            tmdb = parsed_tmdb_id

        if skip_tracker_descriptions and not meta.keep_images:
            return imdb, tmdb

        bbcode = BBCODE()
        imagelist = []
        if "framestor" in name:
            meta.framestor = True
        elif "flux" in name:
            meta.flux = True
        description, imagelist = bbcode.clean_bhd_description(description, meta)
        if not skip_tracker_descriptions:
            meta.description = description
            meta.image_list = imagelist
        elif meta.keep_images:
            meta.description = ""
            meta.image_list = imagelist

        if (imdb and imdb != 0) or (tmdb and tmdb != 0):
            logger.info(f"[green]Found BEYONDHD IDs: IMDb={imdb}, TMDb={tmdb}")
        elif meta.debug:
            logger.info(f"[yellow]BEYONDHD search returned no valid IDs (IMDb={imdb}, TMDb={tmdb})[/yellow]")

        return imdb, tmdb

    @staticmethod
    async def parse_tmdb_id(tmdb_id: str, category: str | None) -> tuple[str | None, int]:
        """Parses TMDb ID, ensures correct formatting, and assigns category."""
        tmdb_id_str = tmdb_id.strip().lower()

        if tmdb_id_str.startswith("tv/"):
            tmdb_id_str = tmdb_id_str.split("/")[1].split("-")[0]
            category = "TV"
        elif tmdb_id_str.startswith("movie/"):
            tmdb_id_str = tmdb_id_str.split("/")[1].split("-")[0]
            category = "MOVIE"

        parsed_id = int(tmdb_id_str) if tmdb_id_str.isdigit() else 0
        return category, parsed_id


async def generate_guid() -> str:
    return await BtnIdManager.generate_guid()


async def get_btn_torrents(btn_api: str, btn_id: str, api_url: str = "https://api.broadcasthe.net/") -> tuple[int, int]:
    return await BtnIdManager.get_btn_torrents(btn_api, btn_id, api_url)


async def get_bhd_torrents(
    bhd_api: str,
    bhd_rss_key: str,
    meta: Meta,
    skip_tracker_descriptions: bool = False,
    info_hash: str | None = None,
    filename: str | None = None,
    foldername: str | None = None,
    torrent_id: int | None = None,
) -> tuple[int, int]:
    return await BtnIdManager.get_bhd_torrents(
        bhd_api,
        bhd_rss_key,
        meta,
        skip_tracker_descriptions=skip_tracker_descriptions,
        info_hash=info_hash,
        filename=filename,
        foldername=foldername,
        torrent_id=torrent_id,
    )


async def parse_tmdb_id(tmdb_id: str, category: str | None = None) -> tuple[str | None, int]:
    return await BtnIdManager.parse_tmdb_id(tmdb_id, category)
