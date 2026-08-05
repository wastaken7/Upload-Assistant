# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
from typing import Any, cast

import aiofiles
import httpx

from src.cogs.redaction import Redaction
from src.console import console, logger
from src.meta import Meta
from src.trackers.common import Common

Config = dict[str, Any]


class Swarmazon:
    """
    SWARMAZON is a Private Torrent Tracker for MOVIES / TV / GENERAL
    """

    base_url = "https://swarmazon.club"

    auth_type = "other_api"
    tracker = "SWARMAZON"
    display_name = "Swarmazon"
    allows_bloated_audio = True
    source_flag = "Swarmazon"
    banned_groups = ("",)
    upload_url = f"{base_url}/api/upload.php"
    forum_link = f"{base_url}/php/forum.php?forum_page=2-swarmazon-rules"
    search_url = f"{base_url}/api/search.php"
    supported_categories = ("TV", "MOVIE")

    def __init__(self, config: Config) -> None:
        self.config: Config = config

    async def get_type_id(self, media_type: str) -> str:
        return {"BluRay": "3", "Web": "1", "DVD": "2"}.get(media_type, "0")

    async def upload(self, meta: Meta) -> bool:
        common = Common(config=self.config)
        await common.create_torrent_for_upload(meta, self.tracker, self.source_flag)
        await self.edit_desc(meta)
        cat_id = ""
        sub_cat_id = ""

        # Anime
        if meta.mal_id:
            cat_id = "7"
            sub_cat_id = "47"

            demographics_map = {"Shounen": "27", "Seinen": "28", "Shoujo": "29", "Josei": "30", "Kodomo": "31", "Mina": "47"}

            demographic = meta.demographic if meta.demographic is not None else "Mina"
            sub_cat_id = demographics_map.get(demographic, sub_cat_id)

        category = meta.category
        if category == "MOVIE":
            cat_id = "1"
            # sub cat is source so using source to get
            sub_cat_id = await self.get_type_id(str(meta.source))
        elif category == "TV":
            cat_id = "2"
            sub_cat_id = "6" if meta.tv_pack else "5"
            # todo need to do a check for docs and add as subcat

        mi_dump: str | None
        bd_dump: str | None
        if meta.bdinfo:
            mi_dump = None
            async with aiofiles.open(
                f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/BD_SUMMARY_00.txt",
                encoding="utf-8",
            ) as bd_file:
                bd_dump = await bd_file.read()
        else:
            async with aiofiles.open(
                f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/MEDIAINFO.txt",
                encoding="utf-8",
            ) as mi_file:
                mi_dump = await mi_file.read()
            bd_dump = None
        async with aiofiles.open(
            f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/[{self.tracker}]DESCRIPTION.txt",
            encoding="utf-8",
        ) as desc_file:
            desc = await desc_file.read()

        async with aiofiles.open(f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/[{self.tracker}].torrent", "rb") as f:
            tfile = await f.read()

        # uploading torrent file.
        files = {"torrent": (f"{meta.name}.torrent", tfile)}

        # adding bd_dump to description if it exits and adding empty string to mediainfo
        if bd_dump:
            desc += "\n\n" + bd_dump
            mi_dump = ""

        api_key = str(self.config["TRACKERS"][self.tracker]["api_key"]).strip()
        data: dict[str, Any] = {
            "api_key": api_key,
            "name": await self.get_name(meta),
            "category_id": cat_id,
            "type_id": sub_cat_id,
            "media_ref": f"tt{meta.imdb}",
            "description": desc,
            "media_info": mi_dump,
        }

        if not meta.debug:
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(self.upload_url, data=data, files=files)
            except httpx.RequestError as e:
                logger.info(f"{self.tracker}: [red]Request failed with error: {e}")
                return False

            try:
                if response.json().get("success"):
                    tracker_status = meta.tracker_status
                    tracker_status.setdefault(self.tracker, {})
                    tracker_status[self.tracker]["status_message"] = response.json()["link"]
                    if "link" in response.json():
                        announce_url = str(self.config["TRACKERS"][self.tracker].get("announce_url", ""))
                        await common.create_torrent_ready_to_seed(
                            meta,
                            self.tracker,
                            self.source_flag,
                            announce_url,
                            str(response.json()["link"]),
                        )
                        return True
                    logger.info(f"{self.tracker}: [red]No Link in Response")
                    return False
                logger.info(f"{self.tracker}: [red]Did not upload successfully")
                logger.info(response.json())
                return False
            except Exception:
                logger.error(f"{self.tracker}: [red]Error! It may have uploaded, go check")
                logger.info(Redaction.redact_private_info(data))
                console.print_exception()
                return False
        else:
            logger.info(f"{self.tracker}: Request Data:")
            logger.info(Redaction.redact_private_info(data))
            tracker_status = meta.tracker_status
            tracker_status.setdefault(self.tracker, {})
            tracker_status[self.tracker]["status_message"] = "Debug mode enabled, not uploading."
            await common.create_torrent_for_upload(meta, f"{self.tracker}" + "_DEBUG", f"{self.tracker}" + "_DEBUG", announce_url="https://fake.tracker")
            return True  # Debug mode - simulated success

    async def edit_desc(self, meta: Meta) -> None:
        from src.description_review import get_base_description

        base = get_base_description(meta)

        parts: list[str] = [base]
        images = meta.image_list
        if images:
            parts.append("[center]")
            for image in images:
                web_url = image.get("web_url")
                img_url = image.get("img_url")
                if not web_url or not img_url:
                    continue
                parts.append(f"[url={web_url}][img=720]{img_url}[/img][/url]")
            parts.append("[/center]")
        parts.append(f"\n[center][url={self.forum_link}]Simplicity, Socializing and Sharing![/url][/center]")

        async with aiofiles.open(
            f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/[{self.tracker}]DESCRIPTION.txt",
            "w",
            encoding="utf-8",
        ) as desc:
            await desc.write("".join(parts))
        return

    async def search_existing(self, meta: Meta) -> list[str]:
        dupes: list[str] = []
        api_key = str(self.config["TRACKERS"][self.tracker]["api_key"]).strip()
        params: dict[str, str] = {"api_key": api_key}

        # Determine search parameters based on metadata
        imdb_id = meta.imdb_id or 0
        category = meta.category
        title = meta.title
        if imdb_id == 0:
            if category == "TV":
                params["filter"] = f"{title}{meta.season}"
            else:
                params["filter"] = title
        else:
            params["media_ref"] = f"tt{meta.imdb}"
            if category == "TV":
                params["filter"] = f"{meta.season}"
            else:
                params["filter"] = meta.resolution

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(self.search_url, params=params)
            response.raise_for_status()
            data = cast(dict[str, Any], response.json())
            items = cast(list[dict[str, Any]], data.get("data", []))
            for item in items:
                result = item.get("name")
                if result:
                    dupes.append(str(result))

        return dupes

    async def get_name(self, meta: Meta) -> str:
        return meta.name
