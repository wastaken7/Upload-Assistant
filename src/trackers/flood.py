# Upload Assistant © 2026 Audionut & wastaken7 — Licensed under UAPL v1.0
import asyncio
import os
import platform
from typing import Any, cast

import aiofiles
import bencodepy
import httpx

from src.console import logger
from src.meta import Meta
from src.trackers.common import Common


class Flood:
    """
    Flood Private Torrent Tracker
    """

    tracker = "FLOOD"
    auth_type = "other_api"
    display_name = "Flood"
    source_flag = "FLD"
    banned_groups = (
        "4K4U",
        "AOC",
        "C4K",
        "CRUCiBLE",
        "d3g",
        "EASports",
        "FGT",
        "MeGusta",
        "MezRips",
        "nikt0",
        "ProRes",
        "RARBG",
        "ReaLHD",
        "SasukeducK",
        "Sicario",
        "TEKNO3D",
        "Telly",
        "tigole",
        "TOMMY",
        "WKS",
        "x0r",
        "YIFY",
    )
    base_url = "https://flood.st"
    upload_url = f"{base_url}/api/torrents/upload"
    search_url = f"{base_url}/api/torrents"
    supported_categories = ("MOVIE", "TV")
    signature = "\n[align=center][size=1][url=https://github.com/Audionut/Upload-Assistant]Created by Audionut's Upload Assistant[/url][/size][/align]"

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.common = Common(config)
        self.api_key = self.config["TRACKERS"].get(self.tracker, {}).get("api_key", "").strip()

    async def upload(self, meta: Meta) -> bool:
        announce_url = self.config["TRACKERS"].get(self.tracker, {}).get("announce_url", "")
        await self.common.create_torrent_for_upload(meta, self.tracker, self.source_flag, announce_url=announce_url)
        media_type = await self.get_media_type(meta)
        await self.edit_desc(meta)
        fld_name = await self.get_name(meta)
        tmdb_id = await self.get_prefixed_tmdb_id(meta)

        anon = "checked" if self.config["TRACKERS"].get(self.tracker, {}).get("anon", False) else ""

        if meta.bdinfo:
            mi_file_path = f"{meta.base_dir}/tmp/{meta.uuid}/BD_SUMMARY_00.txt"
        else:
            mi_file_path = f"{meta.base_dir}/tmp/{meta.uuid}/MEDIAINFO.txt"

        async with aiofiles.open(mi_file_path, encoding="utf-8") as f:
            mi_dump = await f.read()

        async with aiofiles.open(f"{meta.base_dir}/tmp/{meta.uuid}/[{self.tracker}]DESCRIPTION.txt", encoding="utf-8") as f:
            desc = await f.read()

        torrent_file = f"{meta.base_dir}/tmp/{meta.uuid}/[{self.tracker}].torrent"
        files = {}
        if os.path.exists(torrent_file):
            # We read binary for httpx
            with open(torrent_file, "rb") as open_torrent:
                files["meta_info"] = open_torrent.read()

        data = {
            "name": fld_name,
            "imdb_id": meta.imdb,
            "tmdb_id": tmdb_id,
            "anonymous": anon,
            "description": desc,
            "media_info": mi_dump,
            "media_type": media_type,
            "edition": meta.get("edition") or "",
        }

        headers = {"User-Agent": f"Upload Assistant/2.2 ({platform.system()} {platform.release()})", "Authorization": f"Bearer {self.api_key}"}

        if not meta.debug:
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(url=self.upload_url, files=files, data=data, headers=headers)
                response.raise_for_status()
                response_data = response.json()
            except httpx.RequestError as e:
                logger.info(f"{self.tracker}: [red]Upload failed (Request Error): {e}")
                return False
            except httpx.HTTPStatusError as e:
                logger.info(f"{self.tracker}: [red]Upload failed (HTTP Error): {e}")
                return False
            except Exception as e:
                logger.info(f"{self.tracker}: [red]Upload failed (JSON Decode Error or other): {e}")
                return False

            meta.tracker_status[self.tracker]["status_message"] = response_data

            if not response_data.get("success"):
                logger.info(f"{self.tracker}: [red]Upload failed: {response_data.get('message')}[/red]")
                return False
        else:
            logger.info(f"{self.tracker}: [cyan]Request Data:[/cyan]")
            logger.info(str(data))
            response_data = {"success": True, "torrent_url": "https://flood.st/torrent/12345"}

        try:
            with open(torrent_file, "rb") as f:
                torrent_data = f.read()
            torrent = bencodepy.decode(torrent_data)
            if "torrent_url" in response_data:
                torrent[b"comment"] = response_data["torrent_url"].encode("utf-8")
            with open(torrent_file, "wb") as f:
                f.write(bencodepy.encode(torrent))

            if meta.debug:
                logger.info(f"{self.tracker}: Torrent file updated with comment: {response_data.get('torrent_url')}")
        except Exception as e:
            logger.info(f"{self.tracker}: Error while editing the torrent file: {e}")

        return True

    async def get_media_type(self, meta: Meta) -> str:
        is_tv_pack = meta.tv_pack == 1
        if meta.category == "TV":
            return "show_season" if is_tv_pack else "show_episode"
        return "movie"

    async def get_prefixed_tmdb_id(self, meta: Meta) -> str:
        if meta.category == "TV":
            return f"tv/{meta.tmdb}"
        return f"movie/{meta.tmdb}"

    async def edit_desc(self, meta: Meta) -> None:
        from src.description_review import get_base_description

        base = get_base_description(meta)
        base = base.replace("[user]", "").replace("[/user]", "")

        output = []
        discs = meta.get("discs", [])
        if discs:
            if discs[0].get("type") == "DVD":
                output.append(f"[spoiler=VOB MediaInfo][code]{discs[0].get('vob_mi', '')}[/code][/spoiler]\n")
            if len(discs) >= 2:
                for each in discs[1:]:
                    disc_type = each.get("type")
                    if disc_type == "BDMV":
                        output.append(f"[spoiler={each.get('name', 'BDINFO')}][code]{each.get('summary', '')}[/code][/spoiler]\n")
                    elif disc_type == "DVD":
                        output.append(f"{each.get('name', '')}:\n")
                        output.append(
                            f"[spoiler={os.path.basename(each.get('vob', ''))}][code]{each.get('vob_mi', '')}[/code][/spoiler] [spoiler={os.path.basename(each.get('ifo', ''))}][code]{each.get('ifo_mi', '')}[/code][/spoiler]\n"
                        )
                    elif disc_type == "HDDVD":
                        output.append(f"{each.get('name', '')}:\n")
                        output.append(f"[spoiler={os.path.basename(each.get('largest_evo', ''))}][code][{each.get('evo_mi', '')}[/code][/spoiler]\n\n")

        output.append(base.replace("[img]", "[img width=300]"))

        if meta.get("comparison") and meta.get("comparison_groups"):
            output.append("[center]")
            comparison_groups = meta.get("comparison_groups", {})
            sorted_group_indices = sorted(comparison_groups.keys(), key=lambda x: int(x))

            comp_sources = []
            for group_idx in sorted_group_indices:
                group_data = comparison_groups[group_idx]
                group_name = group_data.get("name", f"Group {group_idx}")
                comp_sources.append(group_name)

            sources_string = ", ".join(comp_sources)
            output.append(f"[comparison={sources_string}]\n")

            images_per_group = min([len(comparison_groups[idx].get("urls", [])) for idx in sorted_group_indices]) if sorted_group_indices else 0

            for img_idx in range(images_per_group):
                for group_idx in sorted_group_indices:
                    group_data = comparison_groups[group_idx]
                    urls = group_data.get("urls", [])
                    if img_idx < len(urls):
                        img_url = urls[img_idx].get("raw_url", "")
                        if img_url:
                            output.append(f"{img_url}\n")

            output.append("[/comparison][/center]\n\n")

        images = meta.get(f"{self.tracker}_images_key") or meta.image_list
        if images:
            output.append("[align=center]")
            screens = int(meta.get("screens", len(images)))
            for each in range(len(images[:screens])):
                web_url = images[each].get("web_url", "")
                img_url = images[each].get("img_url", "")
                if each == len(images) - 1:
                    output.append(f"[url={web_url}][img width=350]{img_url}[/img][/url]")
                elif (each + 1) % 2 == 0:
                    output.append(f"[url={web_url}][img width=350]{img_url}[/img][/url]\n\n")
                else:
                    output.append(f"[url={web_url}][img width=350]{img_url}[/img][/url] ")
            output.append("[/align]")

        output.append(self.signature)

        async with aiofiles.open(f"{meta.base_dir}/tmp/{meta.uuid}/[{self.tracker}]DESCRIPTION.txt", "w", encoding="utf-8") as f:
            await f.write("".join(output))

    async def search_existing(self, meta: Meta) -> list[dict[str, Any]]:
        search_params = {}
        if meta.category == "MOVIE":
            search_params["tmdb_id"] = f"movie/{meta.tmdb}"
        elif meta.category == "TV":
            search_params["tmdb_id"] = f"tv/{meta.tmdb}"

            if season_int := meta.get("season_int"):
                search_params["show_season_number"] = season_int

            if meta.get("episode_int") and meta.get("episode_int") != 0:
                search_params["show_episode_number"] = meta.get("episode_int")
        else:
            logger.info(f"{self.tracker}: [bold red]Unknown media type, could not check for dupes[/bold red]")
            return []

        dupes: list[dict[str, Any]] = []
        headers = {"User-Agent": f"Upload Assistant/2.2 ({platform.system()} {platform.release()})", "Authorization": f"Bearer {self.api_key}"}
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(self.search_url, params=search_params, headers=headers, timeout=5.0)
            if response.status_code == 200:
                response_data = cast(dict[str, Any], response.json())
                items = cast(list[dict[str, Any]], response_data.get("items", []))
                for item in items:
                    result = {
                        "id": item.get("id"),
                        "name": item.get("name"),
                        "type": item.get("media_type"),
                        "link": item.get("main_url"),
                        "download": f"{item.get('download_url')}?api_key={self.api_key}",
                        "size": item.get("size"),
                        "files": [file.get("name") for file in item.get("files", [])],
                        "file_count": len(item.get("files", [])),
                    }
                    dupes.append(result)
            else:
                logger.info(f"{self.tracker}: [bold red]HTTP request failed. Status: {response.status_code}[/bold red]")
        except httpx.TimeoutException:
            logger.info(f"{self.tracker}: [bold red]request timed out after 5 seconds[/bold red]")
        except httpx.RequestError as e:
            logger.info(f"{self.tracker}: [bold red]unable to search for existing torrents: {e}[/bold red]")
        except Exception as e:
            logger.info(f"{self.tracker}: [bold red]unexpected error: {e}[/bold red]")
            await asyncio.sleep(5)

        return dupes

    async def get_name(self, meta: Meta) -> str:
        name = str(meta.name)
        if meta.get("source", "") in ("PAL DVD", "NTSC DVD", "DVD", "NTSC", "PAL"):
            audio = str(meta.get("audio", ""))
            audio = " ".join(audio.split())
            name = name.replace(audio, f"{meta.get('video_codec', '')} {audio}")
        name = name.replace("DD+", "DDP")
        return name
