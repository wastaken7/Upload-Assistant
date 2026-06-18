# Upload Assistant © 2026 Audionut & wastaken7 — Licensed under UAPL v1.0
import json
import os
from typing import Any

import aiofiles
import httpx

from src.console import console

Meta = dict[str, Any]
Config = dict[str, Any]


class DS:
    supported_categories = ("TV", "MOVIE", "GAME", "BOOK")

    def __init__(self, config: Config) -> None:
        self.config = config
        self.tracker = "DS"
        self.is_usenet = True
        self.upload_url = "https://nzbs.drunkenslug.com/upload.php"
        self.torrent_url = "https://drunkenslug.com/search/"
        self.banned_groups = []

    async def search_existing(self, _meta: Meta, _disctype: str) -> list[Any]:
        console.print(
            f"{self.tracker}: [yellow]Searching for existing releases is not supported.[/yellow]"
        )
        return []

    async def get_name(self, meta: Meta) -> str:
        return meta["uuid"]

    async def upload(self, meta: Meta, _disctype: str) -> bool:
        nzb_path = meta.get('nzb_path')
        if not nzb_path or not os.path.exists(nzb_path):
            return False

        nzb_name = os.path.basename(nzb_path)

        async with aiofiles.open(nzb_path, 'rb') as f:
            nzb_content = await f.read()

        files = {
            'files[]': (nzb_name, nzb_content, 'application/x-nzb')
        }

        if meta["debug"]:
            meta['tracker_status'][self.tracker]['status_message'] = "Debug mode enabled, skipping upload."
            return True
        else:
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(self.upload_url, files=files)

                if response.status_code not in (200, 201):
                    meta['tracker_status'][self.tracker]['status_message'] = f"data error: HTTP {response.status_code} - {response.text}"
                    return False

                try:
                    data = response.json()
                    results = data.get("results", [])
                    if not results:
                        meta['tracker_status'][self.tracker]['status_message'] = "data error: No results returned from tracker."
                        return False

                    clean_result = results[0].replace(f"{nzb_name}: ", "")
                    meta['tracker_status'][self.tracker]['status_message'] = clean_result
                    meta['tracker_status'][self.tracker]['torrent_id'] = f"{nzb_name.replace('.nzb', '')} (may take a few minutes to show up)"
                    return True
                except json.JSONDecodeError:
                    meta['tracker_status'][self.tracker]['status_message'] = "data error: Could not decode JSON response."
                    return False

            except httpx.TimeoutException:
                meta['tracker_status'][self.tracker]['status_message'] = 'data error: Request timed out after 60 seconds'
                return False
            except httpx.RequestError as e:
                meta['tracker_status'][self.tracker]['status_message'] = f'data error: Unable to upload. Error: {e}'
                return False
            except Exception as e:
                meta['tracker_status'][self.tracker]['status_message'] = f'data error: Unexpected error. Error: {e}'
                return False
