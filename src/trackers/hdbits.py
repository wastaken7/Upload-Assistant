# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import asyncio
import json
import re
from pathlib import Path
from typing import Any, cast
from urllib.parse import quote, urlparse

import aiofiles
import httpx
from rich.markup import escape
from unidecode import unidecode

from src.bbcode import BBCODE
from src.cogs.redaction import Redaction
from src.console import console, logger
from src.description_review import get_base_description
from src.exceptions import *  # noqa F403
from src.meta import Meta
from src.torrentcreate import TorrentCreator
from src.trackers.common import Common

Config = dict[str, Any]


class HDBits:
    """
    HDB Private Torrent Tracker
    """

    auth_type = "cookies"
    tracker = "HDBITS"
    display_name = "HDBits"
    allows_bloated_audio = True
    source_flag = "HDBits"
    signature: str | None = None
    banned_groups: tuple[str, ...] = ("",)
    base_url = "https://hdbits.org"
    supported_categories = ("TV", "MOVIE")
    tracker_urls = ("https://tracker.hdbits.org",)

    def __init__(self, config: Config) -> None:
        self.config: Config = config
        tracker_config = config.get("TRACKERS", {}).get("HDBITS", {})
        tracker_config_dict = cast(dict[str, Any], tracker_config) if isinstance(tracker_config, dict) else {}
        self.username = str(tracker_config_dict.get("username", "")).strip()
        self.passkey = str(tracker_config_dict.get("passkey", "")).strip()
        self.rehost_images = bool(tracker_config_dict.get("img_rehost", True))

    async def get_type_category_id(self, meta: Meta) -> int:
        cat_id = 0
        # 6 = Audio Track
        # 8 = Misc/Demo
        # 4 = Music
        # 5 = Sport
        # 7 = PORN
        # 1 = Movie
        if meta.category == "MOVIE":
            cat_id = 1
        # 2 = TV
        if meta.category == "TV":
            cat_id = 2
        # 3 = Documentary
        if "documentary" in [g.lower() for g in meta.genres] or "documentary" in [k.lower() for k in meta.keywords]:
            cat_id = 3
        imdb_info = meta.imdb_info
        imdb_type = imdb_info.get("type")
        imdb_genres = imdb_info.get("genres")
        if imdb_type is not None and imdb_genres is not None:
            imdb_type_lower = str(imdb_type).lower()
            imdb_genres_lower = str(imdb_genres).lower()
            if "concert" in imdb_type_lower or ("video" in imdb_type_lower and "music" in imdb_genres_lower):
                cat_id = 4
        return cat_id

    async def get_type_codec_id(self, meta: Meta) -> int:
        codecmap = {"AVC": 1, "H.264": 1, "HEVC": 5, "H.265": 5, "MPEG-2": 2, "VC-1": 3, "XviD": 4, "VP9": 6}
        searchcodec = meta.video_codec or meta.video_encode or ""
        return codecmap.get(searchcodec, 0)

    async def get_type_medium_id(self, meta: Meta) -> int:
        medium_id = 0
        # 1 = Blu-ray / HD DVD
        if meta.is_disc in ("BDMV", "HD DVD"):
            medium_id = 1
        # 4 = Capture
        if meta.type == "HDTV":
            medium_id = 4
            if meta.has_encode_settings is True:
                medium_id = 3
        # 3 = Encode
        if meta.type in ("ENCODE", "WEBRIP"):
            medium_id = 3
        # 5 = Remux
        if meta.type == "REMUX":
            medium_id = 5
        # 6 = WEB-DL
        if meta.type == "WEBDL":
            medium_id = 6
        return medium_id

    async def get_res_id(self, resolution: str) -> str:
        return {
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

    async def get_tags(self, meta: Meta) -> list[int]:
        tags: list[int] = []

        # Web Services:
        service_dict = {
            "AMZN": 28,
            "NF": 29,
            "HULU": 34,
            "DSNP": 33,
            "HMAX": 30,
            "ATVP": 27,
            "iT": 38,
            "iP": 56,
            "STAN": 32,
            "PCOK": 31,
            "CR": 72,
            "PMTP": 69,
            "MA": 77,
            "SHO": 76,
            "BCORE": 66,
            "CORE": 66,
            "CRKL": 73,
            "FUNI": 74,
            "HLMK": 71,
            "HTSR": 79,
            "CRAV": 80,
            "MAX": 88,
        }
        service_key = meta.service or ""
        service_id = service_dict.get(service_key)
        if service_id is not None:
            tags.append(service_id)

        # Collections
        # Masters of Cinema, The Criterion Collection, Warner Archive Collection
        distributor_dict = {
            "WARNER ARCHIVE": 68,
            "WARNER ARCHIVE COLLECTION": 68,
            "WAC": 68,
            "CRITERION": 18,
            "CRITERION COLLECTION": 18,
            "CC": 18,
            "MASTERS OF CINEMA": 19,
            "MOC": 19,
            "KINO LORBER": 55,
            "KINO": 55,
            "BFI VIDEO": 63,
            "BFI": 63,
            "BRITISH FILM INSTITUTE": 63,
            "STUDIO CANAL": 65,
            "ARROW": 64,
        }
        distributor_key = meta.distributor or ""
        distributor_id = distributor_dict.get(distributor_key)
        if distributor_id is not None:
            tags.append(distributor_id)

        # 4K Remaster,
        if "IMAX" in meta.edition:
            tags.append(14)
        if "OPEN MATTE" in meta.edition.upper():
            tags.append(58)

        # Audio
        # DTS:X, Dolby Atmos, Auro-3D, Silent
        audio = meta.audio
        if "DTS:X" in audio:
            tags.append(7)
        if "Atmos" in audio:
            tags.append(5)
        if meta.silent is True:
            logger.info(f"{self.tracker}: [yellow]zxx audio track found, suggesting you tag as silent")  # 57

        # Video Metadata
        # HDR10, HDR10+, Dolby Vision, 10-bit,
        hdr_value = meta.hdr
        if "HDR" in hdr_value:
            if "HDR10+" in hdr_value:
                tags.append(25)  # HDR10+
            else:
                tags.append(9)  # HDR10
        if "DV" in hdr_value:
            tags.append(6)  # DV
        if "HLG" in hdr_value:
            tags.append(10)  # HLG

        return tags

    async def get_name(self, meta: Meta) -> str:
        hdb_name = meta.name
        audio = meta.audio
        hdb_name = hdb_name.replace("H.265", "HEVC")
        if meta.source or ("".upper() == "WEB" and meta.service) or "".strip() != "":
            hdb_name = hdb_name.replace(f"{meta.service} ", "", 1)
        if "DV" in meta.hdr:
            hdb_name = hdb_name.replace(" DV ", " DoVi ")
        if "HDR" in meta.hdr and "HDR10+" not in meta.hdr:
            hdb_name = hdb_name.replace("HDR", "HDR10")
        if meta.type in ("WEBDL", "WEBRIP", "ENCODE"):
            hdb_name = hdb_name.replace(audio, audio.replace(" ", "", 1).replace(" Atmos", ""))
        else:
            hdb_name = hdb_name.replace(audio, audio.replace(" Atmos", ""))
        hdb_name = hdb_name.replace(meta.aka, "")
        if meta.imdb_info:
            hdb_name = hdb_name.replace(meta.title, meta.imdb_info["aka"])
            meta_year_str = str(meta.year) if meta.year is not None else ""
            imdb_year_str = str(meta.imdb_info.get("year", meta_year_str))
            if meta_year_str != imdb_year_str and meta_year_str != "":
                hdb_name = hdb_name.replace(meta_year_str, imdb_year_str)
        # Remove Dubbed/Dual-Audio from title
        hdb_name = hdb_name.replace("PQ10", "HDR")
        hdb_name = hdb_name.replace("Dubbed", "").replace("Dual-Audio", "")
        hdb_name = hdb_name.replace("REMUX", "Remux")
        hdb_name = hdb_name.replace("BluRay Remux", "Remux")
        hdb_name = hdb_name.replace("UHD Remux", "Remux")
        hdb_name = hdb_name.replace("DTS-HD HRA", "DTS-HD HR")
        hdb_name = " ".join(hdb_name.split())
        hdb_name = re.sub(r"[^0-9a-zA-ZÀ-ÿ. :&+'\-\[\]]+", "", hdb_name)
        return hdb_name.replace(" .", ".").replace("..", ".")

    async def upload(self, meta: Meta) -> bool | None:
        common = Common(config=self.config)
        await self.edit_desc(meta)
        hdb_name = await self.get_name(meta)
        cat_id = await self.get_type_category_id(meta)
        codec_id = await self.get_type_codec_id(meta)
        medium_id = await self.get_type_medium_id(meta)
        hdb_tags = await self.get_tags(meta)

        for each in (cat_id, codec_id, medium_id):
            if each == 0:
                logger.info(f"{self.tracker}: [bold red]Something didn't map correctly, or this content is not allowed on {self.tracker}")
                return None
        if "Dual-Audio" in meta.audio and not (meta.anime or not meta.is_disc):
            logger.info(f"{self.tracker}: [bold red]Dual-Audio Encodes are not allowed for non-anime and non-disc content")
            return None

        async with aiofiles.open(f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/[{self.tracker}]DESCRIPTION.txt", encoding="utf-8") as desc_file:
            hdb_desc = await desc_file.read()

        base_piece_mb = meta.base_torrent_piece_mb or 0
        torrent_file_path = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/[{self.tracker}].torrent"

        # Check if the piece size exceeds 16 MiB and regenerate the torrent if needed
        if base_piece_mb > 16 and not meta.nohash:
            logger.info(f"{self.tracker}: [red]Piece size is OVER 16M and does not work on {self.tracker}. Generating a new .torrent")
            hdb_config = self.config.get("TRACKERS", {}).get("HDBITS", {})
            hdb_config_dict = cast(dict[str, Any], hdb_config) if isinstance(hdb_config, dict) else {}
            tracker_url = str(hdb_config_dict.get("announce_url", "https://fake.tracker")).strip()
            piece_size = 16
            torrent_create = f"[{self.tracker}]"
            try:
                cooldown = int(self.config.get("DEFAULT", {}).get("rehash_cooldown", 0) or 0)
            except ValueError, TypeError:
                cooldown = 0
            if cooldown > 0:
                await asyncio.sleep(cooldown)  # Small cooldown before rehashing

            await TorrentCreator.create_torrent(meta, str(meta.path), torrent_create, tracker_url=tracker_url, piece_size=piece_size)
            await common.create_torrent_for_upload(meta, self.tracker, self.source_flag, torrent_filename=torrent_create)
        else:
            await common.create_torrent_for_upload(meta, self.tracker, self.source_flag)

        # Proceed with the upload process
        async with aiofiles.open(torrent_file_path, "rb") as torrent_file:
            torrent_bytes = await torrent_file.read()
        torrent_file_name = unidecode(Path(meta.video).name.replace(" ", ".")) if len(meta.filelist) == 1 else unidecode(Path(str(meta.path)).name.replace(" ", "."))
        files = {"file": (f"{torrent_file_name}.torrent", torrent_bytes, "application/x-bittorrent")}
        data: dict[str, Any] = {
            "name": hdb_name,
            "category": cat_id,
            "codec": codec_id,
            "medium": medium_id,
            "origin": 0,
            "descr": hdb_desc.rstrip(),
            "techinfo": "",
            "tags[]": hdb_tags,
        }

        # Internal
        if meta.tag and (
            self.config["TRACKERS"][self.tracker].get("internal", False) is True and meta.tag[1:] in self.config["TRACKERS"][self.tracker].get("internal_groups", [])
        ):
            data["origin"] = 1
        # If not BDMV fill mediainfo
        if meta.is_disc != "BDMV":
            mediainfo_path = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/MEDIAINFO_CLEANPATH.txt"
            async with aiofiles.open(mediainfo_path, encoding="utf-8") as mediainfo_file:
                data["techinfo"] = await mediainfo_file.read()
        # If tv, submit tvdb_id/season/episode
        if meta.tvdb_id != 0:
            data["tvdb"] = meta.tvdb_id
        if meta.imdb_id != 0:
            data["imdb"] = str(meta.imdb_info.get("imdb_url", "")) + "/"
        else:
            data["imdb"] = 0
        if meta.category == "TV":
            data["tvdb_season"] = meta.season_int
            data["tvdb_episode"] = meta.episode_int
        # aniDB

        url = f"{self.base_url}/upload/upload"
        # Submit
        if meta.debug:
            logger.debug(url)
            logger.debug(Redaction.redact_private_info(data))
            meta.tracker_status[self.tracker]["status_message"] = "Debug mode enabled, not uploading."
            await common.create_torrent_for_upload(meta, f"{self.tracker}" + "_DEBUG", f"{self.tracker}" + "_DEBUG", announce_url="https://fake.tracker")
            return True  # Debug mode - simulated success
        from src.cookie_auth import find_cookie_file

        cookiefile = find_cookie_file(meta.base_dir, self.tracker, self.config)
        cookies = await common.parse_cookie_file(cookiefile)
        async with httpx.AsyncClient(cookies=cookies, timeout=30.0, follow_redirects=True) as client:
            up = await client.post(url=url, data=data, files=files)

        # Match url to verify successful upload
        match = re.match(rf".*?{re.escape(self.base_url.replace('https://', ''))}/details\.php\?id=(\d+)&uploaded=(\d+)", str(up.url))
        if match:
            meta.tracker_status[self.tracker]["status_message"] = match.group(0)
            if id_match := re.search(r"(id=)(\d+)", urlparse(str(up.url)).query):
                id = id_match.group(2)
                await self.download_new_torrent(id, torrent_file_path)
            return True
        logger.info(data)
        logger.info(f"{self.tracker}: \n\n")
        logger.info(up.text)
        raise UploadError(f"Upload to HDBITS Failed: result URL {up.url} ({up.status_code}) was not expected", "red")  # noqa F405

    async def search_existing(self, meta: Meta) -> list[dict[str, Any]]:
        dupes: list[dict[str, Any]] = []

        url = f"{self.base_url}/api/torrents"
        data: dict[str, Any] = {
            "username": self.username,
            "passkey": self.passkey,
            "category": await self.get_type_category_id(meta),
            "codec": await self.get_type_codec_id(meta),
            "medium": await self.get_type_medium_id(meta),
        }

        if meta.imdb_id or 0 != 0:
            data["imdb"] = {"id": meta.imdb}
        if meta.tvdb_id or 0 != 0:
            data["tvdb"] = {"id": meta.tvdb_id}

        # Build search_terms list
        search_terms: list[str] = []
        has_valid_ids = (meta.category == "TV" and meta.tvdb_id == 0 and meta.imdb_id == 0) or (meta.category == "MOVIE" and meta.imdb_id == 0)

        if has_valid_ids:
            logger.info(f"{self.tracker}: [yellow]No IMDb or TVDB ID found, trying other options...")
            logger.info(f"{self.tracker}: [yellow]Double check that the upload does not already exist...")
            if meta.filename:
                search_terms.append(meta.filename)
            if meta.aka:
                aka_clean = meta.aka.replace("AKA ", "").strip()
                if aka_clean:
                    search_terms.append(aka_clean)
            if meta.basename_no_ext:
                search_terms.append(meta.basename_no_ext)

        # We have ids
        if not search_terms:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(url, json=data)
                if response.status_code == 200:
                    response_data = response.json()
                    results = response_data.get("data", [])
                    if results:
                        for each in results:
                            result = {
                                "name": each["name"],
                                "size": each["size"],
                                "files": each["filename"][:-8] if each["filename"].endswith(".torrent") else each["filename"],
                                "filecount": each["numfiles"],
                                "link": f"{self.base_url}/details.php?id={each['id']}",
                                "download": f"{self.base_url}/download.php/{quote(each['filename'])}?id={each['id']}&passkey={self.passkey}",
                            }
                            dupes.append(result)
                else:
                    logger.info(f"{self.tracker}: [bold red]HTTP request failed. Status: {response.status_code}")
            return dupes

        # Otherwise, search for each term
        for search_term in search_terms:
            logger.info(f"{self.tracker}: [yellow]Searching {self.tracker} for: {escape(str(search_term))}")
            data["search"] = search_term

            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(url, json=data)
                if response.status_code == 200:
                    response_data = response.json()
                    results = response_data.get("data", [])
                    if results:
                        for each in results:
                            result = {
                                "name": each["name"],
                                "size": each["size"],
                                "files": each["filename"][:-8] if each["filename"].endswith(".torrent") else each["filename"],
                                "filecount": each["numfiles"],
                                "link": f"{self.base_url}/details.php?id={each['id']}",
                                "download": f"{self.base_url}/download.php/{quote(each['filename'])}?id={each['id']}&passkey={self.passkey}",
                            }
                            dupes.append(result)
                else:
                    logger.info(f"{self.tracker}: [bold red]HTTP request failed. Status: {response.status_code}")

        return dupes

    async def validate_credentials(self, meta: Meta) -> bool:
        vcookie = await self.validate_cookies(meta)
        if vcookie is not True:
            logger.error(f"{self.tracker}: [red]Failed to validate cookies. Please confirm that the site is up and your passkey is valid.")
            return False
        return True

    async def validate_cookies(self, meta: Meta) -> bool:
        common = Common(config=self.config)
        url = self.base_url
        from src.cookie_auth import find_cookie_file

        cookiefile = find_cookie_file(meta.base_dir, self.tracker, self.config)
        if Path(cookiefile).exists():
            cookies = await common.parse_cookie_file(cookiefile)
            async with httpx.AsyncClient(cookies=cookies, timeout=30.0) as client:
                resp = await client.get(url=url)
            return resp.text.find("""<a href="/logout.php">Logout</a>""") != -1
        logger.info(f"{self.tracker}: [bold red]Missing Cookie File. (data/cookies/HDBITS.txt)")
        return False

    async def download_new_torrent(self, id: str, torrent_path: str) -> None:
        # Get HDBITS .torrent filename
        api_url = f"{self.base_url}/api/torrents"
        data = {"username": self.username, "passkey": self.passkey, "id": id}
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(url=api_url, json=data)
        r.raise_for_status()
        try:
            r_json = r.json()
        except json.JSONDecodeError as e:
            raise Exception(f"Failed to parse JSON response from {api_url}. Response content: {r.text}. Data: {data}. Error: {e}") from e

        if "data" not in r_json or not isinstance(r_json["data"], list) or len(r_json["data"]) == 0:
            raise Exception(f"Invalid JSON response from {api_url}: 'data' key missing, not a list, or empty. Response: {r_json}. Data: {data}")

        try:
            filename = r_json["data"][0]["filename"]
        except (KeyError, IndexError) as e:
            raise Exception(f"Failed to access filename in response from {api_url}. Response: {r_json}. Data: {data}. Error: {e}") from e

        # Download new .torrent
        download_url = f"{self.base_url}/download.php/{quote(filename)}"
        params = {"passkey": self.passkey, "id": id}

        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(url=download_url, params=params)
        r.raise_for_status()

        # Validate content-type
        content_type = r.headers.get("content-type", "").lower()
        if "bittorrent" not in content_type and "octet-stream" not in content_type:
            raise Exception(f"Unexpected content-type for torrent download: {content_type}. URL: {download_url}. Params: {params}")

        # Basic validation: check if content looks like bencoded data (starts with 'd')
        if not r.content.startswith(b"d"):
            raise Exception(f"Downloaded content does not appear to be a valid torrent file (does not start with 'd'). URL: {download_url}. Params: {params}")

        async with aiofiles.open(torrent_path, "wb") as tor:
            await tor.write(r.content)
        return

    async def edit_desc(self, meta: Meta) -> None:
        base = get_base_description(meta)

        desc_parts: list[str] = []
        # Add This line for all web-dls
        if meta.type == "WEBDL" and meta.service_longname and meta.description:
            desc_parts.append(f"[center][quote]This release is sourced from {meta.service_longname}[/quote][/center]")

        bbcode = BBCODE()
        if meta.discs != []:
            discs = meta.discs
            if discs[0]["type"] == "DVD":
                desc_parts.append(f"[quote=VOB MediaInfo]{discs[0]['vob_mi']}[/quote]\n\n")
            if discs[0]["type"] == "BDMV":
                desc_parts.append(f"[quote]{discs[0]['summary'].strip()}[/quote]\n\n")
            if len(discs) >= 2:
                for each in discs[1:]:
                    if each["type"] == "BDMV":
                        desc_parts.append(f"[quote={each.get('name', 'BDINFO')}]{each['summary']}[/quote]\n\n")
                    if each["type"] == "DVD":
                        desc_parts.append(f"{each['name']}:\n")
                        desc_parts.append(f"[quote={Path(each['vob']).name}][{each['vob_mi']}[/quote] [quote={Path(each['ifo']).name}][{each['ifo_mi']}[/quote]\n\n")

        desc = base
        # desc = bbcode.convert_code_to_quote(desc)
        desc = desc.replace("[code]", "[font=monospace]").replace("[/code]", "[/font]")
        desc = desc.replace("[user]", "").replace("[/user]", "")
        desc = desc.replace("[left]", "").replace("[/left]", "")
        desc = desc.replace("[align=left]", "").replace("[/align]", "")
        desc = desc.replace("[right]", "").replace("[/right]", "")
        desc = desc.replace("[align=right]", "").replace("[/align]", "")
        desc = desc.replace("[sup]", "").replace("[/sup]", "")
        desc = desc.replace("[sub]", "").replace("[/sub]", "")
        desc = desc.replace("[alert]", "").replace("[/alert]", "")
        desc = desc.replace("[note]", "").replace("[/note]", "")
        desc = desc.replace("[hr]", "").replace("[/hr]", "")
        desc = desc.replace("[h1]", "[u][b]").replace("[/h1]", "[/b][/u]")
        desc = desc.replace("[h2]", "[u][b]").replace("[/h2]", "[/b][/u]")
        desc = desc.replace("[h3]", "[u][b]").replace("[/h3]", "[/b][/u]")
        desc = desc.replace("[ul]", "").replace("[/ul]", "")
        desc = desc.replace("[ol]", "").replace("[/ol]", "")
        desc = desc.replace("[*]", "* ")
        desc = bbcode.convert_spoiler_to_hide(desc)
        desc = bbcode.convert_comparison_to_centered(desc, 1000)
        desc = re.sub(r"(\[img=\d+)]", "[img]", desc, flags=re.IGNORECASE)
        desc = re.sub(r"\[/size\]|\[size=\d+\]", "", desc, flags=re.IGNORECASE)
        desc_parts.append(desc)

        if self.rehost_images is True:
            logger.info(f"{self.tracker}: [green]Rehosting Images...")
            hdbimg_bbcode = await self.hdbimg_upload(meta)
            if hdbimg_bbcode is not None:
                if meta.comparison:
                    desc_parts.append("[center]")
                    desc_parts.append("[b]")
                    comparison_groups = meta.comparison_groups
                    if isinstance(comparison_groups, dict):
                        comparison_groups_dict = cast(dict[str, Any], comparison_groups)
                        group_names: list[str] = []
                        sorted_group_indices = sorted(comparison_groups_dict.keys(), key=lambda x: int(x))

                        for group_idx in sorted_group_indices:
                            group_data = comparison_groups_dict.get(group_idx, {})
                            group_data_dict = cast(dict[str, Any], group_data) if isinstance(group_data, dict) else {}
                            group_name = str(group_data_dict.get("name", f"Group {group_idx}"))
                            group_names.append(group_name)

                        comparison_header = " vs ".join(group_names)
                        desc_parts.append(f"Screenshot comparison[/b]\n\n{comparison_header}")
                    else:
                        desc_parts.append("Screenshot comparison")

                    desc_parts.append("\n\n")
                    desc_parts.append(f"{hdbimg_bbcode}")
                    desc_parts.append("[/center]")
                else:
                    desc_parts.append(f"[center]{hdbimg_bbcode}[/center]")
        else:
            images_value = meta.image_list
            images_list: list[dict[str, Any]] = []
            if isinstance(images_value, list):
                images_value_list = cast(list[Any], images_value)
                images_list.extend([cast(dict[str, Any], item) for item in images_value_list if isinstance(item, dict)])
            if images_list:
                desc_parts.append("[center]")
                screen_limit = meta.screens or 0
                for each in range(len(images_list[:screen_limit])):
                    img_url = str(images_list[each].get("img_url", ""))
                    web_url = str(images_list[each].get("web_url", ""))
                    desc_parts.append(f"[url={web_url}][img]{img_url}[/img][/url]")
                desc_parts.append("[/center]")

        if self.signature is not None:
            desc_parts.append(self.signature)

        async with aiofiles.open(f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/[{self.tracker}]DESCRIPTION.txt", "w", encoding="utf-8") as descfile:
            await descfile.write("".join(desc_parts))

        return

    async def hdbimg_upload(self, meta: Meta) -> str | None:
        bbcode = ""
        response: httpx.Response | None = None
        upload_success = False
        sorted_group_indices: list[str] = []
        if meta.comparison:
            comparison_path = meta.comparison
            if not comparison_path or not Path(comparison_path).is_dir():
                logger.info(f"{self.tracker}: [red]Comparison path not found: {comparison_path}")
                return None

            logger.info(f"{self.tracker}: [green]Uploading comparison images from {escape(str(comparison_path))} to {self.tracker} Image Host")

            group_images: dict[str, list[str]] = {}
            max_images_per_group = 0

            comparison_groups = meta.comparison_groups
            if isinstance(comparison_groups, dict):
                comparison_groups_dict = cast(dict[str, Any], comparison_groups)
                for group_idx, group_data in comparison_groups_dict.items():
                    group_data_dict = cast(dict[str, Any], group_data) if isinstance(group_data, dict) else {}
                    files_list_value = group_data_dict.get("files", [])
                    if isinstance(files_list_value, list):
                        files_list_value_list = cast(list[Any], files_list_value)
                        files_list = [str(item) for item in files_list_value_list]
                    else:
                        files_list = []
                    filename_pattern = re.compile(r"(\d+)-")

                    def _sort_key(filename: str, pattern: re.Pattern[str] = filename_pattern) -> int:
                        match = pattern.match(filename)
                        return int(match.group(1)) if match else 0

                    sorted_files = sorted(files_list, key=_sort_key)

                    group_images[group_idx] = []
                    for filename in sorted_files:
                        file_path = Path(comparison_path) / filename
                        if Path(file_path).exists():
                            group_images[group_idx].append(file_path)

                    max_images_per_group = max(max_images_per_group, len(group_images[group_idx]))
            else:
                comparison_files: list[str] = [p.name for p in Path(comparison_path).iterdir() if p.name.lower().endswith(".png")]
                filename_pattern = re.compile(r"(\d+)-(\d+)-(.+)\.png", re.IGNORECASE)
                unsorted_groups: dict[str, list[tuple[int, str]]] = {}

                for file_name in comparison_files:
                    match = filename_pattern.match(file_name)
                    if match:
                        first, second, _ = match.groups()
                        file_path = Path(comparison_path) / file_name
                        unsorted_groups.setdefault(second, []).append((int(first), file_path))

                for group_idx, entries in unsorted_groups.items():
                    sorted_entries = sorted(entries, key=lambda x: x[0])
                    group_images[group_idx] = [path for _, path in sorted_entries]
                    max_images_per_group = max(max_images_per_group, len(group_images[group_idx]))

            # Interleave images for correct ordering
            all_image_files: list[str] = []
            sorted_group_indices = sorted(group_images.keys(), key=lambda x: int(x))
            if len(sorted_group_indices) < 3:
                thumb_size = "w350"
            elif len(sorted_group_indices) == 3:
                thumb_size = "w300"
            elif len(sorted_group_indices) == 4:
                thumb_size = "w200"
            elif len(sorted_group_indices) == 5:
                thumb_size = "w150"
            else:
                thumb_size = "w100"

            for image_idx in range(max_images_per_group):
                all_image_files.extend(group_images[group_idx][image_idx] for group_idx in sorted_group_indices if image_idx < len(group_images[group_idx]))

            logger.debug(f"{self.tracker}: [cyan]Images will be uploaded in this order:")
            for i, path in enumerate(all_image_files):
                logger.debug(f"{self.tracker}: [cyan]{i}: {Path(path).name}")
        else:
            thumb_size = "w300"
            screenshot_dir = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}"
            # similar to uploadscreens.py L546
            image_patterns = ["*.png", ".[!.]*.png"]
            image_glob: list[str] = []
            for image_pattern in image_patterns:
                glob_results = await asyncio.to_thread(lambda pat=image_pattern: [str(p) for p in Path(screenshot_dir).glob(pat)])
                image_glob.extend(glob_results)
            unwanted_patterns = ["FILE*", "PLAYLIST*", "POSTER*"]
            unwanted_files: set[str] = set()
            for unwanted_pattern in unwanted_patterns:
                glob_results = await asyncio.to_thread(lambda pat=unwanted_pattern: [str(p) for p in Path(screenshot_dir).glob(pat)])
                unwanted_files.update(glob_results)
                hidden_glob_results = await asyncio.to_thread(lambda pat=unwanted_pattern: [str(p) for p in Path(screenshot_dir).glob(f".{pat}")])
                unwanted_files.update(hidden_glob_results)
            image_glob = [file for file in image_glob if file not in unwanted_files]
            all_image_files = list(set(image_glob))

        # At this point, all_image_files contains paths to all images we want to upload
        if not all_image_files:
            logger.info(f"{self.tracker}: [red]No images found for upload")
            return None

        url = "https://img.hdbits.org/upload_api.php"
        data: dict[str, Any] = {"username": self.username, "passkey": self.passkey, "galleryoption": "1", "galleryname": meta.name, "thumbsize": thumb_size}

        if meta.comparison:
            # Use everything
            upload_count = len(all_image_files)
        else:
            # Set max screenshots to 3 for TV singles, 6 otherwise
            upload_count = 3 if meta.category == "TV" and meta.tv_pack == 0 else 6
            upload_count = min(len(all_image_files), upload_count)

        logger.debug(f"{self.tracker}: [cyan]Uploading {upload_count} images to {self.tracker} Image Host")

        upload_files: dict[str, tuple[str, bytes, str]] = {}
        for i in range(upload_count):
            file_path = all_image_files[i]
            try:
                filename = Path(file_path).name
                async with aiofiles.open(file_path, "rb") as file_handle:
                    file_bytes = await file_handle.read()
                upload_files[f"images_files[{i}]"] = (filename, file_bytes, "image/png")
                logger.debug(f"{self.tracker}: [cyan]Added file {escape(str(filename))} as images_files[{i}]")
            except (OSError, ValueError) as e:
                logger.error(f"{self.tracker}: [red]Failed to open {escape(str(file_path))}: {escape(str(e))}")
                continue

        try:
            if not upload_files:
                logger.info(f"{self.tracker}: [red]No files to upload")
                return None

            logger.debug(f"{self.tracker}: [green]Uploading {len(upload_files)} images to {self.tracker}...")

            upload_success = True
            if meta.comparison:
                num_groups = len(sorted_group_indices) if sorted_group_indices else 3
                max_chunk_size = 100 * 1024 * 1024  # 100 MiB in bytes
                bbcode = ""

                chunks: list[list[tuple[str, tuple[str, bytes, str]]]] = []
                current_chunk: list[tuple[str, tuple[str, bytes, str]]] = []
                current_chunk_size = 0

                files_list = list(upload_files.items())
                for i in range(0, len(files_list), num_groups):
                    row_items = files_list[i : i + num_groups]
                    row_size = sum(Path(all_image_files[i + j]).stat().st_size for j in range(len(row_items)))

                    # If adding this row would exceed chunk size and we already have items, start new chunk
                    if current_chunk and current_chunk_size + row_size > max_chunk_size:
                        chunks.append(current_chunk)
                        current_chunk = []
                        current_chunk_size = 0

                    current_chunk.extend(row_items)
                    current_chunk_size += row_size

                if current_chunk:
                    chunks.append(current_chunk)

                logger.debug(f"{self.tracker}: [cyan]Split into {len(chunks)} chunks based on 100 MiB limit")

                # Upload each chunk
                for chunk_idx, chunk in enumerate(chunks):
                    file_list: dict[str, tuple[str, bytes, str]] = {}
                    for j, (_key, value) in enumerate(chunk):
                        file_list[f"images_files[{j}]"] = value

                    if meta.debug:
                        chunk_size_mb = sum(Path(all_image_files[int(key.split("[")[1].split("]")[0])]).stat().st_size for key, _ in chunk) / (1024 * 1024)
                        logger.debug(f"{self.tracker}: [cyan]Uploading chunk {chunk_idx + 1}/{len(chunks)} ({len(file_list)} images, {chunk_size_mb:.2f} MiB)")

                    async with httpx.AsyncClient(timeout=30.0) as client:
                        response = await client.post(url, data=data, files=file_list)
                    if response.status_code == 200:
                        logger.info(f"{self.tracker}: [green]Chunk {chunk_idx + 1}/{len(chunks)} upload successful!")
                        bbcode += response.text
                    else:
                        logger.info(f"{self.tracker}: [red]Chunk {chunk_idx + 1}/{len(chunks)} upload failed with status code {response.status_code}")
                        upload_success = False
                        break
            else:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(url, data=data, files=upload_files)
                if response.status_code == 200:
                    logger.info(f"{self.tracker}: [green]Upload successful!")
                    bbcode = response.text
                else:
                    upload_success = False

            if upload_success is True:
                if meta.comparison:
                    matches = re.findall(r"\[url=.*?\]\[img\].*?\[/img\]\[/url\]", bbcode)
                    formatted_bbcode = ""
                    num_groups = len(sorted_group_indices) if sorted_group_indices else 3

                    for i in range(0, len(matches), num_groups):
                        line = " ".join(matches[i : i + num_groups])
                        if i + num_groups < len(matches):
                            formatted_bbcode += line + "\n"
                        else:
                            formatted_bbcode += line

                    bbcode = formatted_bbcode

                    logger.debug(f"{self.tracker}: [cyan]Response formatted with {num_groups} images per line")

                return bbcode
            if response is None:
                logger.info(f"{self.tracker}: [red]Upload failed without a response")
            else:
                logger.info(f"{self.tracker}: [red]Upload failed with status code {response.status_code}")
            return None
        except httpx.RequestError as e:
            logger.info(f"{self.tracker}: [red]HTTP Request failed: {e}")
            return None

    async def get_info_from_torrent_id(self, hdb_id: int) -> tuple[int | None, int | None, str | None, str | None, str | None]:
        hdb_imdb = hdb_tvdb = hdb_name = hdb_torrenthash = hdb_description = None
        url = f"{self.base_url}/api/torrents"
        data = {"username": self.username, "passkey": self.passkey, "id": hdb_id}

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, json=data)
            if response.is_success:
                response_json = response.json()

                if response_json.get("status") == 0 and response_json.get("data"):
                    first_entry = response_json["data"][0]

                    hdb_imdb = int(first_entry.get("imdb", {}).get("id") or 0)
                    hdb_tvdb = int(first_entry.get("tvdb", {}).get("id") or 0)
                    hdb_name = first_entry.get("name", None)
                    hdb_torrenthash = first_entry.get("hash", None)
                    hdb_description = first_entry.get("descr")

                else:
                    status_code = response_json.get("status", "unknown")
                    message = response_json.get("message", "No error message provided")
                    logger.info(f"{self.tracker}: [red]API returned error status {status_code}: {message}[/red]")

        except httpx.RequestError as e:
            logger.info(f"{self.tracker}: [red]Request error: {escape(str(e))}[/red]")
        except (ValueError, KeyError, IndexError, TypeError) as e:
            logger.error(f"{self.tracker}: [red]Failed to parse HDBITS response. Error: {escape(str(e))}[/red]")
        except Exception as e:
            logger.error(f"{self.tracker}: [red]Unexpected error: {escape(str(e))}[/red]")
            console.print_exception()
            raise

        return hdb_imdb, hdb_tvdb, hdb_name, hdb_torrenthash, hdb_description

    async def search_filename(self, search_term: str, search_file_folder: str, meta: Meta) -> tuple[int | None, int | None, str | None, str | None, str | None, int | None]:
        hdb_imdb = hdb_tvdb = hdb_name = hdb_torrenthash = hdb_description = hdb_id = None
        url = f"{self.base_url}/api/torrents"

        # Handle disc case
        if search_file_folder == "folder" and meta.is_disc:
            bd_summary_path = Path(meta.base_dir) / "tmp" / meta.uuid / "BD_SUMMARY_00.txt"
            bd_summary = None

            # Parse the BD_SUMMARY_00.txt file to extract the Disc Title
            try:
                async with aiofiles.open(bd_summary_path, encoding="utf-8") as file:
                    for line in await file.readlines():
                        if "Disc Title:" in line:
                            bd_summary = line.split("Disc Title:")[1].strip()
                            break

                if not bd_summary:
                    bd_summary = meta.basename_no_ext

                if bd_summary:
                    data = {
                        "username": self.username,
                        "passkey": self.passkey,
                        "limit": 100,
                        "search": bd_summary,  # Using the Disc Title for search with uuid fallback
                    }
                    logger.info(f"{self.tracker}: [green]Searching {self.tracker} for title: [bold yellow]{escape(str(bd_summary))}[/bold yellow]")
                    # console.print(f"[yellow]Using this data: {data}")
                else:
                    return hdb_imdb, hdb_tvdb, hdb_name, hdb_torrenthash, hdb_description, hdb_id

            except FileNotFoundError:
                logger.error(f"{self.tracker}: [red]Error: File not found at {bd_summary_path}[/red]")
                return hdb_imdb, hdb_tvdb, hdb_name, hdb_torrenthash, hdb_description, hdb_id

        else:  # Handling non-disc case
            data = {"username": self.username, "passkey": self.passkey, "limit": 100, "file_in_torrent": Path(search_term).name}
            logger.info(f"{self.tracker}: [green]Searching {self.tracker} for file: [bold yellow]{escape(str(Path(search_term).name))}[/bold yellow]")
            # console.print(f"[yellow]Using this data: {data}")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, json=data)
            if response.is_success:
                try:
                    response_json = response.json()
                    # console.print(f"[green]HDBITS API response: {response_json}[/green]")

                    if "data" not in response_json:
                        logger.error(
                            f"{self.tracker}: [red]Error: 'data' key not found or empty in {self.tracker} API response. Full response: {escape(str(response_json))}[/red]"
                        )
                        return hdb_imdb, hdb_tvdb, hdb_name, hdb_torrenthash, hdb_description, hdb_id

                    for each in response_json["data"]:
                        hdb_imdb = int(each.get("imdb", {}).get("id") or 0)
                        hdb_tvdb = int(each.get("tvdb", {}).get("id") or 0)
                        hdb_name = each.get("name", None)
                        hdb_torrenthash = each.get("hash", None)
                        hdb_id = each.get("id", None)
                        hdb_description = each.get("descr")

                        logger.info(
                            f"{self.tracker}: [bold green]Matched release with {self.tracker} ID: [yellow]{self.base_url}/details.php?id={hdb_id}[/yellow][/bold green]"
                        )

                        return hdb_imdb, hdb_tvdb, hdb_name, hdb_torrenthash, hdb_description, hdb_id

                    logger.info(f"{self.tracker}: [yellow]No data found in the {self.tracker} API response[/yellow]")

                except (ValueError, KeyError, TypeError) as e:
                    console.print_exception()
                    logger.error(f"{self.tracker}: [red]Failed to parse {self.tracker} API response. Error: {escape(str(e))}[/red]")
            else:
                logger.error(
                    f"{self.tracker}: [red]Failed to get info from {self.tracker}. Status code: {response.status_code}, Reason: {escape(str(response.reason_phrase))}[/red]"
                )

        except httpx.RequestError as e:
            logger.info(f"{self.tracker}: [red]Request error: {escape(str(e))}[/red]")

        logger.info(f"{self.tracker}: [yellow]Could not find a matching release on {self.tracker}[/yellow]")
        return hdb_imdb, hdb_tvdb, hdb_name, hdb_torrenthash, hdb_description, hdb_id
