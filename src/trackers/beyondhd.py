# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import platform
import re
from pathlib import Path
from typing import Any, cast

import aiofiles
import cli_ui
import httpx
from rich.markup import escape

from src.cogs.redaction import Redaction
from src.console import logger
from src.description_review import get_base_description
from src.meta import Meta
from src.rehostimages import ImageHostPolicy, RehostImagesManager
from src.tracker_images import get_tracker_image_collection
from src.trackers.common import Common


class BEYONDHD:
    """
    BHD Private Torrent Tracker
    """

    auth_type = "unit3d_api"
    tracker = "BEYONDHD"
    display_name = "BeyondHD"
    reject_english_original_bloat = True
    source_flag = "BHD"
    banned_groups = (
        "4K4U",
        "AOC",
        "BiTOR",
        "C4K",
        "CRUCiBLE",
        "d3g",
        "EASports",
        "FGT",
        "Flights",
        "iFT",
        "iVy",
        "MeGusta",
        "MezRips",
        "nikt0",
        "OFT",
        "ProRes",
        "QxR",
        "RARBG",
        "ReaLHD",
        "SasukeducK",
        "Sicario",
        "SyncUP",
        "TEKNO3D",
        "Telly",
        "TGS",
        "tigole",
        "TOMMY",
        "WKS",
        "x0r",
        "YIFY",
    )
    approved_image_hosts = ("imgbox", "imgbb", "pixhost", "bhd", "bam")
    image_host_policy = ImageHostPolicy(
        {
            "ibb.co": "imgbb",
            "pixhost.to": "pixhost",
            "imgbox.com": "imgbox",
            "beyondhd.co": "bhd",
            "imagebam.com": "bam",
        },
        approved_image_hosts,
    )
    base_url = "https://beyond-hd.me"
    upload_url = f"{base_url}/api/upload/"
    torrent_url = f"{base_url}/details/"
    tracker_urls = (base_url, "tracker.beyond-hd.me")
    supported_categories = ("TV", "MOVIE")

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.rehost_images_manager = RehostImagesManager(config)
        trackers_cfg = cast(dict[str, Any], self.config.get("TRACKERS", {}))
        self.tracker_config = cast(dict[str, Any], trackers_cfg.get("BEYONDHD", {}))
        api_key = str(self.tracker_config.get("api_key", "")).strip()
        self.requests_url = f"{self.base_url}/api/requests/{api_key}"

    async def upload(self, meta: Meta) -> bool:
        common = Common(config=self.config)
        await common.create_torrent_for_upload(meta, self.tracker, self.source_flag)
        cat_id = await self.get_cat_id(meta.category)
        source_id = await self.get_source(str(meta.source))
        type_id = await self.get_type(meta)
        draft = await self.get_live(meta)
        await self.edit_desc(meta)
        tags = await self.get_tags(meta)
        custom, edition = await self.get_edition(meta, tags)
        bhd_name = await self.get_name(meta)
        anon = 0 if meta.anon == 0 and not self.config["TRACKERS"][self.tracker].get("anon", False) else 1

        mi_dump = None
        if meta.is_disc == "BDMV":
            async with aiofiles.open(f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/BD_SUMMARY_00.txt", encoding="utf-8") as f:
                mi_dump = await f.read()
        else:
            async with aiofiles.open(f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/MEDIAINFO.txt", encoding="utf-8") as f:
                mi_dump = await f.read()

        async with aiofiles.open(f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/[{self.tracker}]DESCRIPTION.txt", encoding="utf-8") as f:
            desc = await f.read()
        torrent_file_path = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/[{self.tracker}].torrent"
        async with aiofiles.open(torrent_file_path, "rb") as f:
            torrent_bytes = await f.read()

        files = {
            "mediainfo": mi_dump,
            "file": ("torrent.torrent", torrent_bytes, "application/x-bittorrent"),
        }

        data: dict[str, Any] = {
            "name": bhd_name,
            "category_id": cat_id,
            "type": type_id,
            "source": source_id,
            "imdb_id": meta.imdb,
            "tmdb_id": meta.tmdb,
            "description": desc,
            "anon": anon,
            "sd": meta.sd,
            "live": draft,
            # 'internal' : 0,
            # 'featured' : 0,
            # 'free' : 0,
            # 'double_up' : 0,
            # 'sticky' : 0,
        }
        # Internal
        if meta.tag and (
            self.config["TRACKERS"][self.tracker].get("internal", False) is True and meta.tag[1:] in self.config["TRACKERS"][self.tracker].get("internal_groups", [])
        ):
            data["internal"] = 1

        if meta.tv_pack == 1:
            data["pack"] = 1
        if meta.season == "S00":
            data["special"] = 1
        allowed_regions = ["AUS", "CAN", "CEE", "CHN", "ESP", "EUR", "FRA", "GBR", "GER", "HKG", "ITA", "JPN", "KOR", "NOR", "NLD", "RUS", "TWN", "USA"]
        if meta.region in allowed_regions:
            data["region"] = meta.region
        if custom is True:
            data["custom_edition"] = edition
        elif edition != "":
            data["edition"] = edition
        if len(tags) > 0:
            data["tags"] = ",".join(tags)
        headers = {
            "User-Agent": f"{meta.ua_name} {(meta.current_version if meta.current_version is not None else 'github.com/wastaken7/Upload-Assistant')} ({platform.system()} {platform.release()})"
        }

        url = self.upload_url + str(self.tracker_config.get("api_key", "")).strip()
        details_link: str | None = None
        if meta.debug is False:
            try:
                async with httpx.AsyncClient(timeout=60) as client:
                    response = await client.post(url=url, files=files, data=data, headers=headers)
                    response_json = cast(dict[str, Any], response.json())
                    if int(response_json["status_code"]) == 0:
                        logger.info(f"{self.tracker}: [red]{escape(response_json['status_message'])}")
                        if response_json["status_message"].startswith("Invalid imdb_id"):
                            logger.info(f"{self.tracker}: [yellow]RETRYING UPLOAD")
                            data["imdb_id"] = 1
                            response = await client.post(url=url, files=files, data=data, headers=headers)
                            response_json = cast(dict[str, Any], response.json())
                        elif response_json["status_message"].startswith("Invalid name value"):
                            logger.info(f"{self.tracker}: [bold yellow]Submitted Name: {escape(bhd_name)}")

                    if "status_message" in response_json:
                        match = re.search(rf"{re.escape(self.base_url)}/torrent/download/.*\.(\d+)\.", response_json["status_message"])
                        if match:
                            torrent_id = match.group(1)
                            meta.tracker_status[self.tracker]["torrent_id"] = torrent_id
                            details_link = f"{self.base_url}/details/{torrent_id}"
                            meta.tracker_status[self.tracker]["status_message"] = response_json
                        else:
                            meta.tracker_status[self.tracker]["status_message"] = "No valid details link found in status_message."
                            return True
                    else:
                        meta.tracker_status[self.tracker]["status_message"] = "data error: No status_message in response."
                        return False

            except Exception as e:
                meta.tracker_status[self.tracker]["status_message"] = f"data error: {e}"
                return False
        else:
            logger.info(f"{self.tracker}: Request Data:")
            logger.info(Redaction.redact_private_info(data))
            meta.tracker_status[self.tracker]["status_message"] = "Debug mode enabled, not uploading."
            await common.create_torrent_for_upload(meta, f"{self.tracker}" + "_DEBUG", f"{self.tracker}" + "_DEBUG", announce_url="https://fake.tracker")
            return True

        if details_link:
            try:
                await common.create_torrent_ready_to_seed(meta, self.tracker, self.source_flag, self.config["TRACKERS"][self.tracker].get("announce_url"), details_link)
                return True
            except Exception as e:
                logger.info(f"{self.tracker}: Error while editing the torrent file: {e}")
                return False
        else:
            return False

    async def get_cat_id(self, category_name: str) -> str:
        return {
            "MOVIE": "1",
            "TV": "2",
        }.get(category_name, "1")

    async def get_source(self, source: str) -> str | None:
        sources = {
            "Blu-ray": "Blu-ray",
            "BluRay": "Blu-ray",
            "HDDVD": "HD-DVD",
            "HD DVD": "HD-DVD",
            "WEB": "WEB",
            "Web": "WEB",
            "HDTV": "HDTV",
            "UHDTV": "HDTV",
            "NTSC": "DVD",
            "NTSC DVD": "DVD",
            "PAL": "DVD",
            "PAL DVD": "DVD",
        }

        return sources.get(source)

    async def get_type(self, meta: Meta) -> str:
        if meta.is_disc == "BDMV":
            bdinfo = meta.bdinfo
            bd_sizes = [25, 50, 66, 100]
            bd_size = 100
            for each in bd_sizes:
                if bdinfo["size"] < each:
                    bd_size = each
                    break
            type_id = f"UHD {bd_size}" if meta.uhd == "UHD" and bd_size != 25 else f"BD {bd_size}"
            if type_id not in ["UHD 100", "UHD 66", "UHD 50", "BD 50", "BD 25"]:
                type_id = "Other"
        elif meta.is_disc == "DVD":
            if "DVD5" in meta.dvd_size:
                type_id = "DVD 5"
            elif "DVD9" in meta.dvd_size:
                type_id = "DVD 9"
            else:
                type_id = "Other"
        else:
            type_id = "Other"
            if meta.type == "REMUX":
                if meta.source == "BluRay":
                    type_id = "BD Remux"
                if meta.source in ("PAL DVD", "NTSC DVD"):
                    type_id = "DVD Remux"
                if meta.uhd == "UHD":
                    type_id = "UHD Remux"
                if meta.source == "HDDVD":
                    type_id = "Other"
            else:
                acceptable_res = ["2160p", "1080p", "1080i", "720p", "576p", "576i", "540p", "480p", "Other"]
                type_id = meta.resolution if meta.resolution in acceptable_res else "Other"
        return type_id

    async def edit_desc(self, meta: Meta) -> None:
        desc_path = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/[{self.tracker}]DESCRIPTION.txt"
        base = get_base_description(meta)
        for collection_name in ("menu_images", "spectrograms_images"):
            original_images = getattr(meta, collection_name, [])
            rehosted_images = get_tracker_image_collection(meta, self.tracker, collection_name)
            if not isinstance(original_images, list) or not isinstance(rehosted_images, list):
                continue
            for original, rehosted in zip(original_images, rehosted_images, strict=False):
                if not isinstance(original, dict) or not isinstance(rehosted, dict):
                    continue
                original_url = original.get("raw_url")
                rehosted_url = rehosted.get("raw_url")
                if isinstance(original_url, str) and isinstance(rehosted_url, str) and original_url != rehosted_url:
                    base = base.replace(original_url, rehosted_url)
        async with aiofiles.open(desc_path, "w", encoding="utf-8") as desc:
            discs = cast(list[dict[str, Any]], meta.discs or [])
            if discs:
                if discs[0]["type"] == "DVD":
                    await desc.write(f"[spoiler=VOB MediaInfo][code]{discs[0]['vob_mi']}[/code][/spoiler]")
                    await desc.write("\n")
                if len(discs) >= 2:
                    for each in discs[1:]:
                        if each["type"] == "BDMV":
                            await desc.write(f"[spoiler={each.get('name', 'BDINFO')}][code]{each['summary']}[/code][/spoiler]")
                            await desc.write("\n")
                        elif each["type"] == "DVD":
                            await desc.write(f"{each['name']}:\n")
                            await desc.write(
                                f"[spoiler={Path(each['vob']).name}][code][{each['vob_mi']}[/code][/spoiler] [spoiler={Path(each['ifo']).name}][code][{each['ifo_mi']}[/code][/spoiler]"
                            )
                            await desc.write("\n")
                        elif each["type"] == "HDDVD":
                            await desc.write(f"{each['name']}:\n")
                            await desc.write(f"[spoiler={Path(each['largest_evo']).name}][code][{each['evo_mi']}[/code][/spoiler]\n")
                            await desc.write("\n")
            await desc.write(base.replace("[img]", "[img width=300]"))
            if meta.comparison and meta.comparison_groups:
                await desc.write("[center]")
                comparison_groups = cast(dict[str, Any], meta.comparison_groups or {})
                sorted_group_indices = sorted(comparison_groups.keys(), key=lambda x: int(str(x)))

                comp_sources: list[str] = []
                for group_idx in sorted_group_indices:
                    group_data = cast(dict[str, Any], comparison_groups.get(group_idx, {}))
                    group_name = str(group_data.get("name", f"Group {group_idx}"))
                    comp_sources.append(group_name)

                sources_string = ", ".join(comp_sources)
                await desc.write(f"[comparison={sources_string}]\n")

                images_per_group = min([len(cast(dict[str, Any], comparison_groups[idx]).get("urls", [])) for idx in sorted_group_indices])

                for img_idx in range(images_per_group):
                    for group_idx in sorted_group_indices:
                        group_data = cast(dict[str, Any], comparison_groups.get(group_idx, {}))
                        urls = cast(list[dict[str, Any]], group_data.get("urls", []))
                        if img_idx < len(urls):
                            img_url = urls[img_idx].get("raw_url", "")
                            if img_url:
                                await desc.write(f"{img_url}\n")

                await desc.write("[/comparison][/center]\n\n")
            try:
                if meta.tonemapped and self.config["DEFAULT"].get("tonemapped_header", None):
                    tonemapped_header = self.config["DEFAULT"].get("tonemapped_header")
                    await desc.write(tonemapped_header)
                    await desc.write("\n\n")
            except Exception as e:
                logger.warning(f"{self.tracker}: [yellow]Warning: Error setting tonemapped header: {escape(str(e))}[/yellow]")
            images = cast(list[dict[str, Any]], get_tracker_image_collection(meta, self.tracker, "screenshots"))
            if len(images) > 0:
                await desc.write("[align=center]")
                for each in range(len(images[: meta.screens])):
                    web_url = images[each]["web_url"]
                    img_url = images[each]["img_url"]
                    if each == len(images) - 1:
                        await desc.write(f"[url={web_url}][img width=350]{img_url}[/img][/url]")
                    elif (each + 1) % 2 == 0:
                        await desc.write(f"[url={web_url}][img width=350]{img_url}[/img][/url]\n")
                        await desc.write("\n")
                    else:
                        await desc.write(f"[url={web_url}][img width=350]{img_url}[/img][/url] ")
                await desc.write("[/align]")
            await desc.write(f"\n[align=right][url=https://github.com/wastaken7/Upload-Assistant][size=10]{meta.ua_signature}[/size][/url][/align]")
            await desc.close()
            return

    async def get_additional_checks(self, meta: Meta) -> bool:
        bhd_name = await self.get_name(meta)
        if any(
            phrase in bhd_name.lower()
            for phrase in (
                "-framestor",
                "-bhdstudio",
                "-bmf",
                "-decibel",
                "-d-zone",
                "-hifi",
                "-ncmt",
                "-tdd",
                "-flux",
                "-crfw",
                "-sonny",
                "-zr-",
                "-mkvultra",
                "-rpg",
                "-w4nk3r",
                "-irobot",
                "-beyondhd",
            )
        ):
            if not meta.unattended or (meta.unattended and meta.unattended_confirm):
                logger.info(f"{self.tracker}: [bold red]This is an internal {self.tracker} release, skipping upload[/bold red]")
                if cli_ui.ask_yes_no("Do you want to upload anyway?", default=False):
                    pass
                else:
                    return False
            else:
                return False

        if not meta.valid_mi_settings:
            logger.info(f"{self.tracker}: [bold red]No encoding settings in mediainfo, skipping {self.tracker} upload.[/bold red]")
            return False

        if meta.type in ["REMUX", "ENCODE", "WEBDL", "WEBRIP"] and meta.container not in ["mkv", "mp4"]:
            logger.info(
                f"{self.tracker}: [bold red]Container '{escape(str(meta.container))}' is not allowed for {escape(str(meta.type))}. Only MKV and MP4 are permitted. Skipping upload.[/bold red]"
            )
            return False

        if meta.type not in ["WEBDL"] and meta.tag and any(x in meta.tag for x in ["EVO"]):
            if not meta.unattended or (meta.unattended and meta.unattended_confirm):
                logger.info(f"{self.tracker}: [bold red]Group {escape(str(meta.tag))} is only allowed for raw type content at {self.tracker}[/bold red]")
                if cli_ui.ask_yes_no("Do you want to upload anyway?", default=False):
                    pass
                else:
                    return False
            else:
                return False

        common = Common(config=self.config)
        return common.check_and_confirm_adult_media_upload(meta, self.tracker)

    async def search_existing(self, meta: Meta) -> list[dict[str, Any]]:
        dupes: list[dict[str, Any]] = []
        category = meta.category
        tmdb_id_type = "movie" if category == "MOVIE" else "tv"
        if category == "MOVIE":
            category = "Movies"
        elif category == "TV":
            category = "TV"
        if meta.is_disc == "DVD":
            type_id: str | None = None
        else:
            type_id = await self.get_type(meta)
        data: dict[str, Any] = {"action": "search", "types": type_id, "categories": category}
        if meta.tmdb:
            data["tmdb_id"] = f"{tmdb_id_type}/{meta.tmdb}"
        if meta.sd == 1:
            data["categories"] = None
            data["types"] = None
        if meta.category == "TV":
            data["search"] = f"{meta.season}"
        rss_key = self.tracker_config.get("bhd_rss_key", "") != ""
        if rss_key:
            data["rsskey"] = str(self.tracker_config.get("bhd_rss_key", "")).strip()

        url = f"{self.base_url}/api/torrents/{str(self.tracker_config.get('api_key', '')).strip()}"
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(url, params=data)
            response.raise_for_status()
            response_data = cast(dict[str, Any], response.json())
            if response_data.get("status_code") != 1:
                raise RuntimeError(f"BEYONDHD API Error: {response_data.get('message', 'Unknown Error')}")

            results = cast(list[dict[str, Any]], response_data.get("results", []))
            for each in results:
                # Extract HDR flags from BEYONDHD data
                flags: list[str] = []
                if each.get("dv") == 1:
                    flags.append("DV")
                if each.get("hdr10") == 1 or each.get("hdr10+") == 1:
                    flags.append("HDR")

                result = {
                    "name": each["name"],
                    "link": each["url"],
                    "size": each["size"],
                    "flags": flags,
                }
                if rss_key:
                    result["download"] = each.get("download_url", None)
                dupes.append(result)

        return dupes

    def _is_true(self, value: Any) -> bool:
        """
        Converts a value to a boolean. Returns True for "true", "1", "yes" (case-insensitive), and False otherwise.
        """
        return str(value).strip().lower() in {"true", "1", "yes"}

    async def get_live(self, meta: Meta) -> int:
        draft_value = self.config["TRACKERS"][self.tracker].get("draft_default", False)
        draft_bool = draft_value if isinstance(draft_value, bool) else self._is_true(str(draft_value).strip())

        return 0 if draft_bool or meta.draft else 1

    async def get_edition(self, meta: Meta, tags: list[str]) -> tuple[bool, str]:
        custom = False
        edition = meta.edition
        if "Hybrid" in tags:
            edition = edition.replace("Hybrid", "").strip()
        editions = ["collector", "cirector", "extended", "limited", "special", "theatrical", "uncut", "unrated"]
        for each in editions:
            if each in meta.edition:
                edition = each
            elif edition == "":
                edition = ""
            else:
                custom = True
        return custom, edition

    async def get_tags(self, meta: Meta) -> list[str]:
        tags: list[str] = []
        if meta.type == "WEBRIP":
            tags.append("WEBRip")
        if meta.type == "WEBDL":
            tags.append("WEBDL")
        if meta.three_d == "3D":
            tags.append("3D")
        if "Dual-Audio" in meta.audio:
            tags.append("DualAudio")
        if "Dubbed" in meta.audio:
            tags.append("EnglishDub")
        if "Open Matte" in meta.edition:
            tags.append("OpenMatte")
        if meta.scene is True:
            tags.append("Scene")
        if meta.personalrelease is True:
            tags.append("Personal")
        if "hybrid" in meta.edition.lower():
            tags.append("Hybrid")
        if meta.has_commentary is True:
            tags.append("Commentary")
        if "DV" in meta.hdr:
            tags.append("DV")
        if "HDR" in meta.hdr:
            if "HDR10+" in meta.hdr:
                tags.append("HDR10+")
            else:
                tags.append("HDR10")
        if "HLG" in meta.hdr:
            tags.append("HLG")
        return tags

    async def get_name(self, meta: Meta) -> str:
        name = meta.name or ""
        if meta.source in ("PAL DVD", "NTSC DVD", "DVD", "NTSC", "PAL"):
            audio = meta.audio
            audio = " ".join(audio.split())
            name = name.replace(audio, f"{meta.video_codec} {audio}")
        return name.replace("DD+", "DDP")
