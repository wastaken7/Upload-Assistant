# -*- coding: utf-8 -*-
# import discord
import asyncio
import platform

import requests
from src.console import console
from src.trackers.COMMON import COMMON


class ULCX:
    def __init__(self, config):
        self.config = config
        self.tracker = "ULCX"
        self.source_flag = "ULCX"
        self.upload_url = "https://upload.cx/api/torrents/upload"
        self.search_url = "https://upload.cx/api/torrents/filter"
        self.signature = "\n[center][url=https://github.com/Audionut/Upload-Assistant]Created by L4G's Upload Assistant[/url][/center]"
        self.banned_groups = [
            "Tigole",
            "x0r",
            "Judas",
            "SPDVD",
            "MeGusta",
            "YIFY",
            "SWTYBLZ",
            "TAoE",
            "TSP",
            "TSPxL",
            "LAMA",
            "4K4U",
            "ION10",
            "Will1869",
            "TGx",
            "Sicario",
            "QxR",
            "Hi10",
            "EMBER",
            "FGT",
            "AROMA",
            "d3g",
            "nikt0",
            "Grym",
            "RARBG",
            "iVy",
            "NuBz",
            "NAHOM",
            "EDGE2020",
            "FnP",
        ]

    async def get_cat_id(self, category_name):
        category_id = {
            "MOVIE": "1",
            "TV": "2",
        }.get(category_name, "0")
        return category_id

    async def get_type_id(self, type):
        type_id = {
            "DISC": "1",
            "REMUX": "2",
            "WEBDL": "4",
            "WEBRIP": "5",
            "HDTV": "6",
            "ENCODE": "3",
        }.get(type, "0")
        return type_id

    async def get_res_id(self, resolution):
        resolution_id = {
            "8640p": "10",
            "4320p": "1",
            "2160p": "2",
            "1440p": "3",
            "1080p": "3",
            "1080i": "4",
            "720p": "5",
            "576p": "6",
            "576i": "7",
            "480p": "8",
            "480i": "9",
        }.get(resolution, "10")
        return resolution_id

    async def upload(self, meta):
        common = COMMON(config=self.config)
        await common.edit_torrent(meta, self.tracker, self.source_flag)
        cat_id = await self.get_cat_id(meta["category"])
        type_id = await self.get_type_id(meta["type"])
        resolution_id = await self.get_res_id(meta["resolution"])
        await common.unit3d_edit_desc(meta, self.tracker, signature=self.signature)
        region_id = await common.unit3d_region_ids(meta.get("region"))
        distributor_id = await common.unit3d_distributor_ids(meta.get("distributor"))
        if meta["anon"] != 0 or self.config["TRACKERS"][self.tracker].get(
            "anon", False
        ):
            anon = 1
        else:
            anon = 0

        modq = await self.get_flag(meta, "modq")

        if meta["bdinfo"] is not None:
            mi_dump = None
            bd_dump = open(
                f"{meta['base_dir']}/tmp/{meta['uuid']}/BD_SUMMARY_00.txt",
                "r",
                encoding="utf-8",
            ).read()
        else:
            mi_dump = open(
                f"{meta['base_dir']}/tmp/{meta['uuid']}/MEDIAINFO.txt",
                "r",
                encoding="utf-8",
            ).read()
            bd_dump = None
        desc = open(
            f"{meta['base_dir']}/tmp/{meta['uuid']}/[{self.tracker}]DESCRIPTION.txt",
            "r",
        ).read()
        open_torrent = open(
            f"{meta['base_dir']}/tmp/{meta['uuid']}/[{self.tracker}]{meta['clean_name']}.torrent",
            "rb",
        )
        files = {"torrent": open_torrent}
        data = {
            "name": meta["name"],
            "description": desc,
            "mediainfo": mi_dump,
            "bdinfo": bd_dump,
            "category_id": cat_id,
            "type_id": type_id,
            "resolution_id": resolution_id,
            "tmdb": meta["tmdb"],
            "imdb": meta["imdb_id"].replace("tt", ""),
            "tvdb": meta["tvdb_id"],
            "mal": meta["mal_id"],
            "igdb": 0,
            "anonymous": anon,
            "stream": meta["stream"],
            "sd": meta["sd"],
            "keywords": meta["keywords"],
            "personal_release": int(meta.get("personalrelease", False)),
            "internal": 0,
            "featured": 0,
            "free": 0,
            "doubleup": 0,
            "sticky": 0,
            "mod_queue_opt_in": modq,
        }
        # Internal
        if self.config["TRACKERS"][self.tracker].get("internal", False):
            if meta["tag"] != "" and (
                meta["tag"][1:]
                in self.config["TRACKERS"][self.tracker].get("internal_groups", [])
            ):
                data["internal"] = 1

        if region_id != 0:
            data["region_id"] = region_id
        if distributor_id != 0:
            data["distributor_id"] = distributor_id
        if meta.get("category") == "TV":
            data["season_number"] = meta.get("season_int", "0")
            data["episode_number"] = meta.get("episode_int", "0")
        headers = {
            "User-Agent": f"Upload Assistant/2.1 ({platform.system()} {platform.release()})"
        }
        params = {"api_token": self.config["TRACKERS"][self.tracker]["api_key"].strip()}

        if not meta["debug"]:
            success = "Unknown"
            try:
                response = requests.post(
                    url=self.upload_url,
                    files=files,
                    data=data,
                    headers=headers,
                    params=params,
                )
                response.raise_for_status()
                response_json = response.json()
                success = response_json.get("success", False)
                data = response_json.get("data", {})
            except Exception as e:
                console.print(
                    f"[red]Encountered Error: {e}[/red]\n[bold yellow]May have uploaded, please go check.."
                )

            if success == "Unknown":
                console.print(
                    "[bold yellow]Status of upload is unknown, please go check.."
                )
                success = False
            elif success:
                console.print("[bold green]Torrent uploaded successfully!")
            else:
                console.print("[bold red]Torrent upload failed.")

            if data:
                if (
                    "name" in data
                    and "The name has already been taken." in data["name"]
                ):
                    console.print("[red]Name has already been taken.")
                if (
                    "info_hash" in data
                    and "The info hash has already been taken." in data["info_hash"]
                ):
                    console.print("[red]Info hash has already been taken.")
            else:
                console.print("[cyan]Request Data:")
                console.print(data)

            try:
                open_torrent.close()
            except Exception as e:
                console.print(f"[red]Failed to close torrent file: {e}[/red]")

            return success

    async def get_flag(self, meta, flag_name):
        config_flag = self.config["TRACKERS"][self.tracker].get(flag_name)
        if config_flag is not None:
            return 1 if config_flag else 0

        return 1 if meta.get(flag_name, False) else 0

    async def search_existing(self, meta):
        dupes = {}
        console.print("[yellow]Searching for existing torrents on site...")
        params = {
            "api_token": self.config["TRACKERS"][self.tracker]["api_key"].strip(),
            "tmdbId": meta["tmdb"],
            "categories[]": await self.get_cat_id(meta["category"]),
            "types[]": await self.get_type_id(meta["type"]),
            "resolutions[]": await self.get_res_id(meta["resolution"]),
            "name": "",
        }
        if meta.get("edition", "") != "":
            params["name"] = params["name"] + f" {meta['edition']}"
        try:
            response = requests.get(url=self.search_url, params=params)
            response = response.json()
            for each in response["data"]:
                result = each["attributes"]["name"]
                size = each["attributes"]["size"]
                dupes[result] = size
        except Exception as e:
            console.print(
                f"[bold red]Unable to search for existing torrents on site. Either the site is down or your API key is incorrect. Error: {e}"
            )
            await asyncio.sleep(5)

        return dupes
