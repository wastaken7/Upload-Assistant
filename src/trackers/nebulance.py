# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import json
import re
from typing import Any, cast
from urllib.parse import urlencode

import aiofiles
import cli_ui
import httpx

from src.cogs.redaction import Redaction
from src.console import logger
from src.meta import Meta
from src.trackers.common import Common

Config = dict[str, Any]


class Nebulance:
    """
    NBL Private Torrent Tracker
    """

    auth_type = "other_api"
    tracker = "NEBULANCE"
    display_name = "Nebulance"
    allows_bloated_audio = True
    source_flag = "NBL"
    banned_groups = (
        "[Oj]",
        "0neshot",
        "3LTON",
        "4yEo",
        "AFG",
        "AkihitoSubs",
        "AniHLS",
        "Anime Time",
        "AnimeRG",
        "AniURL",
        "ASW",
        "BakedFish",
        "bonkai77",
        "Cleo",
        "DeadFish",
        "DeeJayAhmed",
        "ELiTE",
        "EMBER",
        "eSc",
        "EVO",
        "FGT",
        "FUM",
        "GERMini",
        "HAiKU",
        "Hi10",
        "ION10",
        "JacobSwaggedUp",
        "JIVE",
        "Judas",
        "LOAD",
        "MeGusta",
        "Mr.Deadpool",
        "mSD",
        "NemDiggers",
        "neoHEVC",
        "NhaNc3",
        "NOIVTC",
        "PlaySD",
        "playXD",
        "project-gxs",
        "PSA",
        "QaS",
        "Ranger",
        "RAPiDCOWS",
        "Raze",
        "Reaktor",
        "REsuRRecTioN",
        "RMTeam",
        "ROBOTS",
        "SpaceFish",
        "SPASM",
        "SSA",
        "Telly",
        "Tenrai-Sensei",
        "TM",
        "Trix",
        "URANiME",
        "VipapkStudios",
        "ViSiON",
        "Wardevil",
        "xRed",
        "XS",
        "YakuboEncodes",
        "YuiSubs",
        "ZKBL",
        "ZmN",
        "ZMNT",
    )
    base_url = "https://nebulance.io"
    upload_url = f"{base_url}/api.php"
    search_url = f"{base_url}/api.php"
    torrent_url = f"{base_url}/torrents.php?id="
    supported_categories = ("TV",)
    tracker_urls = ("tracker.nebulance",)

    def __init__(self, config: Config) -> None:
        self.config: Config = config
        self.common = Common(config)
        self.api_key = str(self.config["TRACKERS"][self.tracker]["api_key"]).strip()

    async def get_cat_id(self, meta: Meta) -> int:
        return 3 if meta.tv_pack == 1 else 1

    async def edit_desc(self, _meta: Meta) -> None:
        # Leave this in so manual works
        return

    async def upload(self, meta: Meta) -> bool:
        await self.common.create_torrent_for_upload(meta, self.tracker, self.source_flag)

        if meta.bdinfo:
            async with aiofiles.open(f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/BD_SUMMARY_00.txt", encoding="utf-8") as f:
                mi_dump = await f.read()
        else:
            async with aiofiles.open(f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/MEDIAINFO.txt", encoding="utf-8") as f:
                mi_dump = await f.read()
        torrent_file_path = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/[{self.tracker}].torrent"
        async with aiofiles.open(torrent_file_path, "rb") as f:
            torrent_bytes = await f.read()
        files: dict[str, tuple[str, bytes, str]] = {"file_input": ("torrent.torrent", torrent_bytes, "application/x-bittorrent")}
        data: dict[str, Any] = {
            "action": "upload",
            "api_key": self.api_key,
            "tvmazeid": "" if not meta.tvmaze_id else int(meta.tvmaze_id),
            "mediainfo": mi_dump,
            "category": await self.get_cat_id(meta),
            "ignoredupes": "1",
        }

        try:
            if not meta.debug:
                async with httpx.AsyncClient(timeout=30) as client:
                    response = await client.post(url=self.upload_url, files=files, data=data)
                    if response.status_code in [200, 201]:
                        try:
                            response_data = response.json()
                            meta.tracker_status[self.tracker]["status_message"] = response_data
                            match = re.search(rf"{re.escape(self.base_url)}/torrents\.php\?id=(\d+)", response_data.get("link", ""))
                            if match:
                                torrent_id = match.group(1)
                                meta.tracker_status[self.tracker]["torrent_id"] = torrent_id
                            return True
                        except json.JSONDecodeError:
                            meta.tracker_status[self.tracker]["status_message"] = f"data error: {self.tracker} json decode error, the API is probably down"
                            return False
                    else:
                        response_data = {"error": f"Unexpected status code: {response.status_code}", "response_content": response.text}
                        meta.tracker_status[self.tracker]["status_message"] = response_data
                    return False
            else:
                logger.info(f"{self.tracker}: Request Data:")
                logger.info(Redaction.redact_private_info(data))
                meta.tracker_status[self.tracker]["status_message"] = "Debug mode enabled, not uploading."
                await self.common.create_torrent_for_upload(meta, f"{self.tracker}" + "_DEBUG", f"{self.tracker}" + "_DEBUG", announce_url="https://fake.tracker")
                return True  # Debug mode - simulated success
        except Exception as e:
            meta.tracker_status[self.tracker]["status_message"] = f"data error: Upload failed: {e}"
            return False

    async def get_additional_checks(self, meta: Meta) -> bool:
        if meta.category != "TV":
            if meta.tvmaze_id != 0:
                if not meta.unattended or (meta.unattended and meta.unattended_confirm):
                    logger.info(f"{self.tracker}: [red]Only TV or TV Movies are allowed at {self.tracker}, this has a tvmaze ID[/red]")
                    if cli_ui.ask_yes_no("Do you want to upload it?", default=False):
                        pass
                    else:
                        return False
                else:
                    return False
            else:
                if not meta.unattended:
                    logger.info(f"{self.tracker}: [red]Only TV Is allowed at {self.tracker}[/red]")
                return False

        if meta.is_disc != "BDMV" and not await self.common.check_language_requirements(
            meta, self.tracker, languages_to_check=["english"], check_audio=True, check_subtitle=True, original_language=True
        ):
            return False

        if meta.valid_mi is False:
            logger.info(f"{self.tracker}: [bold red]No unique ID in mediainfo, skipping {self.tracker} upload.")
            return False

        if meta.is_disc:
            if not meta.unattended:
                logger.info(f"{self.tracker}: [bold red]does not allow raw discs[/bold red]")
            return False

        return True

    async def search_existing(self, meta: Meta) -> list[dict[str, Any]] | bool:
        dupes: list[dict[str, Any]] = []

        season = meta.season_int
        tvmaze_data = meta.tvmaze_episode_data
        if tvmaze_data:
            season = tvmaze_data.get("season_number", season)

        params: dict[str, Any] = {
            "action": "search",
            "api_key": self.api_key,
        }

        season_int = int(season) if season is not None else 0

        if season_int > 0:
            params["season"] = season_int

        if int(meta.tvmaze_id or 0) != 0:
            params["tvmaze"] = meta.tvmaze_id
        elif meta.imdb_id or 0 != 0:
            params["imdb"] = meta.imdb_id
        else:
            params["series"] = meta.title

        params["tags"] = [meta.resolution]
        params["per_page"] = 100

        response: httpx.Response | None = None
        max_pages = int(self.config["TRACKERS"][self.tracker].get("search_max_pages", 10))
        async with httpx.AsyncClient(timeout=10.0) as client:
            for page in range(max_pages):
                page_params = dict(params)
                page_params["page"] = page
                search_url_with_query = f"{self.search_url}?{urlencode(page_params, doseq=True)}"

                response = await client.get(search_url_with_query)
                if response.status_code != 200:
                    if response.status_code == 400 and page > 0:
                        try:
                            error_data = cast(dict[str, Any], response.json())
                        except json.JSONDecodeError:
                            error_data = {}
                        error = error_data.get("error", {})
                        message = str(error.get("message", "")) if isinstance(error, dict) else ""
                        if "out of range" in message.lower() and "valid pages" in message.lower():
                            break
                    response.raise_for_status()

                data = cast(dict[str, Any], response.json())

                items_value = data.get("items")
                if not isinstance(items_value, list):
                    result = cast(dict[str, Any], data.get("result", {}))
                    items_value = result.get("items", [])
                items = cast(list[dict[str, Any]], items_value) if isinstance(items_value, list) else []
                if not items:
                    break

                for each in items:
                    tags_value = each.get("tags", [])
                    tags = cast(list[Any], tags_value) if isinstance(tags_value, list) else []
                    if meta.resolution in tags:
                        file_list_value = each.get("file_list", [])
                        file_list = cast(list[Any], file_list_value) if isinstance(file_list_value, list) else []
                        files_str = ", ".join(str(item) for item in file_list) if file_list else str(cast(Any, file_list_value))
                        result = {
                            "name": str(each.get("rls_name", "")),
                            "files": files_str,
                            "size": int(each.get("size", 0)),
                            "link": f"{self.base_url}/torrents.php?id={each.get('group_id', '')}",
                            "file_count": len(file_list) if file_list else 1,
                            "download": str(each.get("download", "")),
                        }
                        dupes.append(result)

        return dupes

    async def get_name(self, meta: Meta) -> str:
        return meta.title
