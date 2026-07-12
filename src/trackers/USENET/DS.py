# Upload Assistant © 2026 Audionut & wastaken7 — Licensed under UAPL v1.0
import json
import os
from typing import Any

import aiofiles
import httpx

from src.console import logger
from src.meta import Meta
from src.trackers.COMMON import COMMON

Config = dict[str, Any]


class DS:
    tracker = "DS"
    banned_groups = ()
    torrent_url = "https://drunkenslug.com/search/"
    supported_categories = ("TV", "MOVIE", "GAME", "BOOK")
    is_usenet = True

    def __init__(self, config: Config) -> None:
        self.config = config
        self.common = COMMON(config)
        self.upload_url = str(self.config.get("TRACKERS", {}).get(self.tracker, {}).get("upload_url", "").replace("/upload_form", "/upload.php")).strip()

    async def search_existing(self, meta: Meta) -> list[Any]:
        release_name = await self.get_name(meta)
        cache_file = os.path.join(meta.base_dir, "tmp", meta.uuid, f"{self.tracker}_upload_ok")
        if release_name and os.path.exists(cache_file):
            logger.info(f"{self.tracker}: [yellow]Found local upload cache.[/yellow]")
            return [release_name]

        logger.info(f"{self.tracker}: [yellow]Searching for existing releases is not supported.[/yellow]")
        return []

    async def get_name(self, meta: Meta) -> str:
        return meta.scene_name or meta.basename_no_ext

    async def upload(self, meta: Meta) -> bool:
        status_map = meta.tracker_status
        if self.tracker not in status_map:
            status_map[self.tracker] = {}
        status_dict = status_map[self.tracker]

        if not self.upload_url:
            status_dict["status_message"] = "data error: DS upload_url is not configured in config.py under TRACKERS -> DS -> upload_url"
            return False

        nzb_path = meta.nzb_path
        if not nzb_path or not await self.common.check_nzb_file(self.tracker, meta):
            status_dict["status_message"] = "data error: NZB file missing or password missing in header"
            return False

        nzb_name = f"{await self.get_name(meta)}.nzb"

        async with aiofiles.open(nzb_path, 'rb') as f:
            nzb_content = await f.read()

        files = {
            'files[]': (nzb_name, nzb_content, 'application/x-nzb')
        }

        if meta.debug:
            status_dict["status_message"] = "Debug mode enabled, skipping upload."
            return True
        else:
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(self.upload_url, files=files)

                if response.status_code not in (200, 201):
                    status_dict["status_message"] = f"data error: HTTP {response.status_code} - {response.text}"
                    return False

                try:
                    data = response.json()
                    results = data.get("results", [])
                    if not results:
                        status_dict["status_message"] = "data error: No results returned from tracker."
                        return False

                    clean_result = results[0].replace(f"{nzb_name}: ", "")
                    status_dict["status_message"] = clean_result
                    status_dict["torrent_id"] = f"{nzb_name.replace('.nzb', '')} (may take a few minutes to show up)"

                    cache_dir = os.path.join(meta.base_dir, "tmp", meta.uuid)
                    os.makedirs(cache_dir, exist_ok=True)
                    async with aiofiles.open(os.path.join(cache_dir, f"{self.tracker}_upload_ok"), "w", encoding="utf-8") as cache_handle:
                        await cache_handle.write("ok")

                    return True
                except json.JSONDecodeError:
                    status_dict["status_message"] = "data error: Could not decode JSON response."
                    return False

            except httpx.TimeoutException:
                status_dict["status_message"] = "data error: Request timed out after 60 seconds"
                return False
            except httpx.RequestError as e:
                status_dict["status_message"] = f"data error: Unable to upload. Error: {e}"
                return False
            except Exception as e:
                status_dict["status_message"] = f"data error: Unexpected error. Error: {e}"
                return False
