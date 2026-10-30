# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import traceback
from pathlib import Path
from typing import Any, cast

import aiofiles
import httpx

from src import payload_preview
from src.cogs.redaction import Redaction
from src.console import logger
from src.description_review import get_base_description
from src.get_desc import DescriptionBuilder
from src.meta import Meta
from src.trackers.common import Common


class BitHDTV:
    """
    BHDTV Private Torrent Tracker
    """

    auth_type = "other_api"
    tracker = "BITHDTV"
    display_name = "BitHDTV"
    allows_bloated_audio = True
    source_flag = "BIT-HDTV"
    banned_groups = ()
    base_url = "https://www.bit-hdtv.com"
    upload_url = f"{base_url}/takeupload.php"
    supported_categories = ("TV", "MOVIE")

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    async def get_data(self, meta: Meta, preview: bool = False) -> dict[str, Any]:
        """Build the upload form; a ``preview`` leaves out the description and MediaInfo/BDInfo."""
        if not preview:
            await self.edit_desc(meta)
        cat_id = await self.get_cat_id(meta)
        sub_cat_id = ""
        if meta.category == "MOVIE":
            sub_cat_id = await self.get_type_movie_id(meta)
        elif meta.category == "TV" and not meta.tv_pack:
            sub_cat_id = await self.get_type_tv_id(meta.type or "")
        else:
            # must be TV pack
            sub_cat_id = await self.get_type_tv_pack_id(meta.type or "")

        resolution_id = await self.get_res_id(meta.resolution)
        # region_id = await common.unit3d_region_ids(meta.region)
        # distributor_id = await common.unit3d_distributor_ids(meta.distributor)

        desc = mi_dump = bd_dump = None
        if not preview:
            if meta.bdinfo:
                async with aiofiles.open(f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/BD_SUMMARY_00.txt", encoding="utf-8") as bd_file:
                    bd_dump = await bd_file.read()
            else:
                async with aiofiles.open(f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/MEDIAINFO_CLEANPATH.txt", encoding="utf-8") as mi_file:
                    mi_dump = await mi_file.read()
            async with aiofiles.open(f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/[{self.tracker}]DESCRIPTION.txt", encoding="utf-8") as desc_file:
                desc = await desc_file.read()

        media_info = ""
        if meta.is_disc != "BDMV":
            filelist = cast(list[str], meta.filelist or [])
            video = filelist[0] if filelist else (meta.path or "")
            media_info = DescriptionBuilder.format_short_mediainfo_json(meta.mediainfo, video)

        data: dict[str, Any] = {
            "api_key": str(self.config["TRACKERS"][self.tracker]["api_key"]).strip(),
            "name": await self.get_name(meta),
            "mediainfo": mi_dump if bd_dump is None else bd_dump,
            "cat": cat_id,
            "subcat": sub_cat_id,
            "resolution": resolution_id,
            # 'anon': anon,
            # admins asked to remove short description.
            "sdescr": " ",
            "descr": media_info if not meta.bdinfo else "Disc so Check Mediainfo dump ",
            "screen": desc,
            "url": f"https://www.tvmaze.com/shows/{meta.tvmaze_id}" if meta.category == "TV" else str(meta.imdb_info.get("imdb_url", "")),
            "format": "json",
        }
        return data

    async def get_payload_preview(self, meta: Meta) -> payload_preview.TrackerPreview:
        """The upload form as it is known before screenshots, for the Web UI to show and edit."""
        specs = {
            "name": payload_preview.text("Name"),
            "cat": payload_preview.choice("Category", [("7", "Movie"), ("10", "TV episode"), ("12", "TV pack")]),
            "subcat": payload_preview.choice(
                "Subcategory",
                [
                    ("1", "Movie encode"),
                    ("2", "Movie disc / remux"),
                    ("5", "Movie WEB"),
                    ("6", "Movie HDTV"),
                    ("43", "Movie x265 encode"),
                    ("44", "Movie 3D encode"),
                    ("45", "Movie 3D remux"),
                    ("46", "Movie 3D disc"),
                    ("48", "Movie x265 remux"),
                    ("7", "TV HDTV"),
                    ("8", "TV WEB / pack WEBRip"),
                    ("10", "TV encode"),
                    ("11", "TV remux"),
                    ("12", "TV disc"),
                    ("13", "TV pack HDTV"),
                    ("14", "TV pack WEB-DL"),
                    ("16", "TV pack encode"),
                    ("17", "TV pack remux"),
                    ("18", "TV pack disc"),
                ],
            ),
            "resolution": payload_preview.choice("Resolution", [("4", "2160p"), ("3", "1080p"), ("2", "1080i"), ("1", "720p"), ("10", "Other")]),
            "sdescr": payload_preview.readonly("Short description"),
            "descr": payload_preview.readonly("MediaInfo summary"),
            "url": payload_preview.text("Info URL"),
            "format": payload_preview.readonly("Response format"),
        }
        deferred = {"mediainfo": "Read from the MediaInfo/BDInfo report at upload time", "screen": payload_preview.DESCRIPTION_NOTE}
        return payload_preview.describe(self.tracker, await self.get_data(meta, preview=True), specs, deferred=deferred)

    async def upload(self, meta: Meta) -> bool:
        common = Common(config=self.config)
        await common.create_torrent_for_upload(meta, self.tracker, self.source_flag)
        data = payload_preview.apply_payload_edits(meta, self.tracker, await self.get_data(meta))

        torrent_path = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/[{self.tracker}].torrent"
        async with aiofiles.open(torrent_path, "rb") as open_torrent:
            torrent_bytes = await open_torrent.read()
        files = {"file": (Path(torrent_path).name, torrent_bytes, "application/x-bittorrent")}

        if meta.debug is False:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.post(url=self.upload_url, data=data, files=files)
            parsed: Any | None = None
            if response:
                try:
                    parsed = response.json()
                    meta.tracker_status[self.tracker]["status_message"] = parsed
                except Exception:
                    logger.info(f"{self.tracker}: [cyan]It may have uploaded, go check")
                    logger.info(Redaction.redact_private_info(data))
                    traceback.print_exc()

            parsed_data: dict[str, Any] | None = cast(dict[str, Any] | None, parsed) if isinstance(parsed, dict) else None
            data_block: dict[str, Any] | None = parsed_data.get("data") if parsed_data else None
            if isinstance(data_block, dict) and "view" in data_block:
                my_announce_url = self.config["TRACKERS"][self.tracker].get("my_announce_url")
                if my_announce_url:
                    await common.create_torrent_ready_to_seed(meta, self.tracker, self.source_flag, my_announce_url, str(data_block["view"]))
                    return True
            return False

        logger.info(f"{self.tracker}: Request Data:")
        logger.info(Redaction.redact_private_info(data))
        meta.tracker_status[self.tracker]["status_message"] = "Debug mode enabled, not uploading."
        await common.create_torrent_for_upload(meta, f"{self.tracker}" + "_DEBUG", f"{self.tracker}" + "_DEBUG", announce_url="https://fake.tracker")
        return True

    async def get_cat_id(self, meta: Meta) -> str:
        category_id = "0"
        if meta.category == "MOVIE":
            category_id = "7"
        elif meta.tv_pack:
            category_id = "12"
        else:
            # must be tv episode
            category_id = "10"
        return category_id

    async def get_type_movie_id(self, meta: Meta) -> str:
        type_id = "0"
        if meta.type == "DISC":
            type_id = "46" if meta.three_d else "2"
        elif meta.type == "REMUX":
            if meta.name.__contains__("265"):
                type_id = "48"
            elif meta.three_d:
                type_id = "45"
            else:
                type_id = "2"
        elif meta.type == "HDTV":
            type_id = "6"
        elif meta.type == "ENCODE":
            if meta.name.__contains__("265"):
                type_id = "43"
            elif meta.three_d:
                type_id = "44"
            else:
                type_id = "1"
        elif meta.type == "WEBDL" or meta.type == "WEBRIP":
            type_id = "5"

        return type_id

    async def get_type_tv_id(self, type: str) -> str:
        return {
            "HDTV": "7",
            "WEBDL": "8",
            "WEBRIP": "8",
            # 'WEBRIP': '55',
            # 'SD': '59',
            "ENCODE": "10",
            "REMUX": "11",
            "DISC": "12",
        }.get(type, "0")

    async def get_type_tv_pack_id(self, type: str) -> str:
        return {
            "HDTV": "13",
            "WEBDL": "14",
            "WEBRIP": "8",
            # 'WEBRIP': '55',
            # 'SD': '59',
            "ENCODE": "16",
            "REMUX": "17",
            "DISC": "18",
        }.get(type, "0")

    async def get_res_id(self, resolution: str) -> str:
        return {"2160p": "4", "1080p": "3", "1080i": "2", "720p": "1"}.get(resolution, "10")

    async def edit_desc(self, meta: Meta) -> None:
        base = get_base_description(meta)
        parts: list[str] = [base.replace("[img=250]", "[img=250x250]")]
        images = meta.image_list or []
        if len(images) > 0:
            for each in range(len(images)):
                web_url = images[each]["web_url"]
                img_url = images[each]["img_url"]
                parts.append(f"[url={web_url}][img]{img_url}[/img][/url] ")
        async with aiofiles.open(f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/[{self.tracker}]DESCRIPTION.txt", "w", encoding="utf-8") as desc:
            await desc.write("".join(parts))
        return

    async def search_existing(self, _meta: dict[str, Any]) -> list[str]:
        logger.info(f"{self.tracker}: [red]Dupes must be checked Manually")
        return []

    async def get_name(self, meta: Meta) -> str:
        if meta.manual_name is not None:
            return meta.manual_name.strip()

        return meta.name.replace(" ", ".").replace(":.", ".").replace(":", ".").replace("DD+", "DDP")
