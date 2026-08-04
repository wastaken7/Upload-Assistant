# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import asyncio
import json
import re
import traceback
from pathlib import Path
from typing import Any, cast

import aiofiles
import aiofiles.os
import cli_ui
import httpx
import pyotp
from defusedxml import ElementTree
from rich.markup import escape

from src.cogs.redaction import Redaction
from src.console import console, logger
from src.get_desc import DescriptionBuilder
from src.meta import Meta
from src.rehostimages import ImageHostPolicy, RehostImagesManager
from src.torrentcreate import TorrentCreator
from src.trackers.common import Common

Config = dict[str, Any]


class MoreThanTV:
    """
    MTV Private Torrent Tracker
    """

    auth_type = "cookies"
    tracker = "MORETHANTV"
    display_name = "MoreThanTV"
    reject_english_original_bloat = True
    source_flag = "MTV"
    approved_image_hosts = ("imgbox", "imgbb")
    image_host_policy = ImageHostPolicy({"ibb.co": "imgbb", "imgbox.com": "imgbox"}, approved_image_hosts)
    banned_groups = (
        "[Oj]",
        "3LTON",
        "AFG",
        "aXXo",
        "BDP",
        "BRrip",
        "CM8",
        "CMCT",
        "CrEwSaDe",
        "DeadFish",
        "DNL",
        "ELiTE",
        "FaNGDiNG0",
        "FRDS",
        "FUM",
        "h65",
        "HD2DVD",
        "HDTime",
        "ION10",
        "iPlanet",
        "JIVE",
        "KiNGDOM",
        "LAMA",
        "Leffe",
        "LOAD",
        "mHD",
        "mRS",
        "mSD",
        "NhaNc3",
        "nHD",
        "nikt0",
        "nSD",
        "PandaRG",
        "PRODJi",
        "QxR",
        "RARBG",
        "RDN",
        "SANTi",
        "STUTTERSHIT",
        "TERMiNAL",
        "TM",
        "ViSiON",
        "WAF",
        "x0r",
        "XS",
        "YIFY",
        "ZKBL",
        "ZmN",
        "ZMNT",
    )
    base_url = "https://www.morethantv.me"
    upload_url = f"{base_url}/upload.php"
    forum_link = f"{base_url}/wiki.php?action=article&id=73"
    search_url = f"{base_url}/api/torznab"
    tracker_urls = ("tracker.morethantv",)
    supported_categories = ("TV", "MOVIE")

    def __init__(self, config: Config) -> None:
        self.config: Config = config
        self.rehost_images_manager = RehostImagesManager(config)

    # For loading
    async def async_json_loads(self, data_str: str) -> Any:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, json.loads, data_str)

    # For dumping
    async def async_json_dumps(self, obj: Any) -> str:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, json.dumps, obj)

    async def upload(self, meta: Meta) -> bool | None:
        common = Common(config=self.config)
        from src.cookie_auth import find_cookie_file

        cookiefile = find_cookie_file(meta.base_dir, self.tracker, self.config)
        base_piece_mb = meta.base_torrent_piece_mb or 0
        torrent_file_path = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/[{self.tracker}].torrent"

        if base_piece_mb > 8 and not meta.nohash:
            tracker_config = self.config["TRACKERS"].get(self.tracker, {})
            if str(tracker_config.get("skip_if_rehash", "false")).lower() == "false":
                logger.info(f"{self.tracker}: [red]Piece size is OVER 8M and does not work on {self.tracker}. Generating a new .torrent")
                piece_size = 8
                tracker_url = str(tracker_config.get("announce_url", "https://fake.tracker")).strip()
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
                logger.info(f"{self.tracker}: [red]Piece size is OVER 8M and skip_if_rehash enabled. Skipping upload.")
                return None
        else:
            await common.create_torrent_for_upload(meta, self.tracker, self.source_flag)

        cat_id = await self.get_cat_id(meta)
        resolution_id = await self.get_res_id(meta.resolution)
        source_id = await self.get_source_id(meta)
        origin_id = await self.get_origin_id(meta)
        des_tags = await self.get_tags(meta)
        await self.edit_desc(meta)
        group_desc = await self.edit_group_desc(meta)
        mtv_name = await self.get_name(meta)

        anon = 0 if meta.anon == 0 and not self.config["TRACKERS"][self.tracker].get("anon", False) else 1

        desc_path = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/[{self.tracker}]DESCRIPTION.txt"
        async with aiofiles.open(desc_path, encoding="utf-8") as f:
            desc = await f.read()

        async with aiofiles.open(torrent_file_path, "rb") as f:
            tfile = await f.read()

        files = {"file_input": (f"[{self.tracker}].torrent", tfile)}

        data = {
            "image": "",
            "title": mtv_name,
            "category": cat_id,
            "Resolution": resolution_id,
            "source": source_id,
            "origin": origin_id,
            "taglist": des_tags,
            "desc": desc,
            "groupDesc": group_desc,
            "ignoredupes": "1",
            "genre_tags": "---",
            "autocomplete_toggle": "on",
            "fontfont": "-1",
            "fontsize": "-1",
            "auth": await self.get_auth(cookiefile),
            "anonymous": anon,
            "submit": "true",
        }

        if not meta.debug:
            try:
                async with aiofiles.open(cookiefile, encoding="utf-8") as cf:
                    cookie_data = await cf.read()
                    cookies = await self.async_json_loads(cookie_data)

                headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}

                async with httpx.AsyncClient(cookies=cookies, timeout=10.0, follow_redirects=True, headers=headers) as client:
                    response = await client.post(url=self.upload_url, data=data, files=files)

                    # This is not a header or cookie size issue, but MORETHANTV returns this status.
                    if response.status_code == 400 and ("Request Header" in response.text or "Cookie Too Large" in response.text or "Header Too Large" in response.text):
                        meta.tracker_status[self.tracker]["status_message"] = "data error: Request Header or Cookie Too Large error from server"
                        return False

                    try:
                        if "torrents.php" in str(response.url):
                            meta.tracker_status[self.tracker]["status_message"] = response.url
                            await common.create_torrent_ready_to_seed(
                                meta, self.tracker, self.source_flag, self.config["TRACKERS"][self.tracker].get("announce_url"), str(response.url)
                            )
                            return True
                        if f"{self.base_url}/upload.php" in str(response.url):
                            meta.tracker_status[self.tracker]["status_message"] = "data error - Still on upload page - upload may have failed"
                            if "error" in response.text.lower() or "failed" in response.text.lower():
                                meta.tracker_status[self.tracker]["status_message"] = "data error - Upload failed - check form data"
                            return False
                        if str(response.url) == f"{self.base_url}/" or str(response.url) == f"{self.base_url}/index.php":
                            if "Project Luminance" in response.text:
                                meta.tracker_status[self.tracker]["status_message"] = "data error - Not logged in - session may have expired"
                            if "'GroupID' cannot be null" in response.text:
                                meta.tracker_status[self.tracker]["status_message"] = f"data error - You are hitting this site bug: {self.base_url}/forum/thread/3338?"
                            elif "Integrity constraint violation" in response.text:
                                meta.tracker_status[self.tracker]["status_message"] = "data error - Proper site bug"
                            return False
                        if "authkey.php" in str(response.url):
                            meta.tracker_status[self.tracker]["status_message"] = "data error - No DL link in response, It may have uploaded, check manually."
                        else:
                            logger.info(f"{self.tracker}: response URL: {response.url}")
                            logger.info(f"{self.tracker}: response status: {response.status_code}")
                        return False
                    except Exception:
                        meta.tracker_status[self.tracker]["status_message"] = "data error -It may have uploaded, check manually."
                        traceback.print_exc()
                        return False
            except (httpx.RequestError, Exception) as e:
                meta.tracker_status[self.tracker]["status_message"] = f"data error: {e}"
                return False
        else:
            logger.info(f"{self.tracker}: Request Data:")
            debug_data = data.copy()
            if "auth" in debug_data:
                auth_value = str(debug_data.get("auth", ""))
                debug_data["auth"] = f"{auth_value[:3]}..." if len(auth_value) > 3 else "***"
            logger.info(Redaction.redact_private_info(debug_data))
            meta.tracker_status[self.tracker]["status_message"] = "Debug mode enabled, not uploading."
            await common.create_torrent_for_upload(meta, f"{self.tracker}" + "_DEBUG", f"{self.tracker}" + "_DEBUG", announce_url="https://fake.tracker")
            return True  # Debug mode - simulated success

    async def edit_desc(self, meta: Meta) -> None:
        builder = DescriptionBuilder(self.tracker, self.config)
        description = await builder.general_description_generator(
            meta,
            audio_spectrogram=True,
            bluray=False,
            book=False,
            custom_header=True,
            custom_signature=True,
            description=True,
            game=False,
            languages=False,
            logo=True,
            mediainfo=True,
            menu_screenshots=True,
            nfo=False,
            screenshots=True,
            tonemapped_header=True,
            tv_info=True,
            ua_signature=True,
            user_description=True,
        )

        desc_path = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/[{self.tracker}]DESCRIPTION.txt"
        async with aiofiles.open(desc_path, "w", encoding="utf-8") as f:
            await f.write(description)

        return

    async def edit_group_desc(self, meta: Meta) -> str:
        description = ""
        if meta.imdb_id != 0:
            description += str(meta.imdb_info.get("imdb_url", ""))
        if meta.tmdb:
            description += f"\nhttps://www.themoviedb.org/{(meta.category.lower())}/{meta.tmdb!s}"
        if meta.tvdb_id != 0:
            description += f"\nhttps://www.thetvdb.com/?id={meta.tvdb_id!s}"
        if meta.tvmaze_id != 0:
            description += f"\nhttps://www.tvmaze.com/shows/{meta.tvmaze_id!s}"
        if meta.mal_id != 0:
            description += f"\nhttps://myanimelist.net/anime/{meta.mal_id!s}"

        return description

    async def get_name(self, meta: Meta) -> str:
        prefix_index = -1
        if meta.scene is True:
            scene_name = meta.scene_name
            mtv_name = scene_name or meta.basename_no_ext
        else:
            mtv_name = meta.name
            prefix_removed = False
            replacement_prefix = ""

            # Check for Dual-Audio or Dubbed prefix
            if "Dual-Audio " in mtv_name:
                prefix_removed = True
                prefix_index = mtv_name.find("Dual-Audio ")
                replacement_prefix = "DUAL "
                mtv_name = mtv_name[:prefix_index] + mtv_name[prefix_index + len("Dual-Audio ") :]
            elif "Dubbed " in mtv_name:
                prefix_removed = True
                prefix_index = mtv_name.find("Dubbed ")
                replacement_prefix = "DUBBED "
                mtv_name = mtv_name[:prefix_index] + mtv_name[prefix_index + len("Dubbed ") :]

            audio_str = meta.audio
            if prefix_removed:
                audio_str = audio_str.replace("Dual-Audio ", "").replace("Dubbed ", "")

            if prefix_removed and prefix_index != -1:
                mtv_name = f"{mtv_name[:prefix_index]}{replacement_prefix}{mtv_name[prefix_index:].lstrip()}"

            if meta.type in ("WEBDL", "WEBRIP", "ENCODE") and "DD" in audio_str:
                mtv_name = mtv_name.replace(audio_str, audio_str.replace(" ", "", 1))
            if "DD+" in meta.audio and "DDP" in meta.basename_no_ext:
                mtv_name = mtv_name.replace("DD+", "DDP")

        source_value = str(meta.source)
        if (
            source_value.lower().replace("-", "") in mtv_name.replace("-", "").lower()
            and not meta.isdir
            and "." in mtv_name
            and mtv_name.split(".")[-1].isalpha()
            and len(mtv_name.split(".")[-1]) <= 4
        ):
            mtv_name = Path(mtv_name).stem

        tag_value = meta.tag
        tag_lower = "" if not tag_value else tag_value.lower()
        invalid_tags = ["nogrp", "nogroup", "unknown", "-unk-"]
        if tag_value == "" or any(invalid_tag in tag_lower for invalid_tag in invalid_tags):
            for invalid_tag in invalid_tags:
                mtv_name = re.sub(f"-{invalid_tag}", "", mtv_name, flags=re.IGNORECASE)
            mtv_name = f"{mtv_name}-NOGRP"

        mtv_name = " ".join(mtv_name.split())
        mtv_name = re.sub(r"[^0-9a-zA-ZÀ-ÿ. &+'\-\[\]]+", "", mtv_name)
        return mtv_name.replace(" ", ".").replace("..", ".")

    async def get_res_id(self, resolution: str) -> str:
        return {
            "8640p": "0",
            "4320p": "4000",
            "2160p": "2160",
            "1440p": "1440",
            "1080p": "1080",
            "1080i": "1080",
            "720p": "720",
            "576p": "0",
            "576i": "0",
            "480p": "480",
            "480i": "480",
        }.get(resolution, "10")

    async def get_cat_id(self, meta: Meta) -> int | None:
        if meta.category == "MOVIE":
            if meta.sd == 1:
                return 2
            return 1
        if meta.category == "TV":
            if meta.tv_pack == 1:
                if meta.sd == 1:
                    return 6
                return 5
            if meta.sd == 1:
                return 4
            return 3
        return None

    async def get_source_id(self, meta: Meta) -> str:
        if meta.is_disc == "DVD":
            return "1"
        if meta.is_disc == "BDMV" or meta.type == "REMUX":
            return "7"
        return {
            "DISC": "1",
            "WEBDL": "9",
            "WEBRIP": "10",
            "HDTV": "1",
            "SDTV": "2",
            "TVRIP": "3",
            "DVD": "4",
            "DVDRIP": "5",
            "BDRIP": "8",
            "VHS": "6",
            "MIXED": "11",
            "Unknown": "12",
            "ENCODE": "7",
        }.get(meta.type or "", "0")

    async def get_origin_id(self, meta: Meta) -> str:
        if meta.personalrelease:
            return "4"
        if meta.scene:
            return "2"
        # returning P2P
        return "3"

    async def get_tags(self, meta: Meta) -> str:
        tags: list[str] = []
        # Genres
        # MORETHANTV takes issue with some of the pulled TMDB tags, and I'm not hand checking and attempting
        # to regex however many tags need changing, so they're just getting skipped
        # tags.extend([x.strip(', ').lower().replace(' ', '.') for x in meta.genres.split(',')])
        # Resolution
        tags.append(meta.resolution.lower())
        if meta.sd == 1:
            tags.append("sd")
        elif meta.resolution in ["2160p", "4320p"]:
            tags.append("uhd")
        else:
            tags.append("hd")
        # Streaming Service
        # disney+ should be disneyplus, assume every other service is same.
        # If I'm wrong, then they can either allowing editing tags or service will just get skipped also
        if meta.service_longname != "":
            service_name = meta.service_longname.lower().replace(" ", ".")
            service_name = service_name.replace("+", "plus")  # Replace '+' with 'plus'
            tags.append(f"{service_name}.source")
        # Release Type/Source
        tags.extend(
            each
            for each in ["remux", "WEB.DL", "WEBRip", "HDTV", "BluRay", "DVD", "HDDVD"]
            if (each.lower().replace(".", "") in (meta.type or "").lower()) or (each.lower().replace("-", "") in (meta.source or ""))
        )
        # series tags
        if meta.category == "TV":
            if meta.tv_pack == 0:
                # Episodes
                if meta.sd == 1:
                    tags.extend(["sd.episode"])
                else:
                    tags.extend(["hd.episode"])
            else:
                # Seasons
                if meta.sd == 1:
                    tags.append("sd.season")
                else:
                    tags.append("hd.season")

        # movie tags
        if meta.category == "MOVIE":
            if meta.sd == 1:
                tags.append("sd.movie")
            else:
                tags.append("hd.movie")

        # Audio tags
        audio_tag = ""
        for each in ["dd", "ddp", "aac", "truehd", "mp3", "mp2", "dts", "dts.hd", "dts.x"]:
            if each in meta.audio.replace("+", "p").replace("-", ".").replace(":", ".").replace(" ", ".").lower():
                audio_tag = f"{each}.audio"
        tags.append(audio_tag)
        if "atmos" in meta.audio.lower():
            tags.append("atmos.audio")

        # Video tags
        video_codec = meta.video_codec
        tags.append(video_codec.replace("AVC", "h264").replace("HEVC", "h265").replace("-", ""))

        # Group Tags
        if meta.tag:
            tags.append(f"{meta.tag[1:].replace(' ', '.')}.release")
        else:
            tags.append("NOGRP.release")

        # Scene/P2P
        if meta.scene:
            tags.append("scene.group.release")
        else:
            tags.append("p2p.group.release")

        # Has subtitles
        if meta.is_disc != "BDMV":
            if any(track.get("@type", "") == "Text" for track in meta.mediainfo["media"]["track"]):
                tags.append("subtitles")
        else:
            if len(meta.bdinfo["subtitles"]) >= 1:
                tags.append("subtitles")

        return " ".join(tag for tag in tags if tag)

    async def validate_credentials(self, meta: Meta) -> bool:
        from src.cookie_auth import find_cookie_file

        cookiefile = find_cookie_file(meta.base_dir, self.tracker, self.config)
        if not await aiofiles.os.path.exists(cookiefile):
            await self.login(cookiefile, meta)
        vcookie = await self.validate_cookies(meta, cookiefile)
        if vcookie is not True:
            logger.error(f"{self.tracker}: [red]Failed to validate cookies. Please confirm that the site is up and your username and password is valid.")
            if "mtv_timeout" in meta and meta.mtv_timeout:
                meta.skipping = "MORETHANTV"
                return False
            recreate = cli_ui.ask_yes_no("Log in again and create new session?") if not meta.unattended or (meta.unattended and meta.unattended_confirm) else True
            if recreate is True:
                if await aiofiles.os.path.exists(cookiefile):
                    await aiofiles.os.remove(cookiefile)  # Using async file removal
                await self.login(cookiefile, meta)
                return await self.validate_cookies(meta, cookiefile)
            return False

        return True

    async def validate_cookies(self, meta: Meta, cookiefile: str) -> bool:
        url = f"{self.base_url}/index.php"
        if await aiofiles.os.path.exists(cookiefile):
            try:
                async with aiofiles.open(cookiefile, encoding="utf-8") as cf:
                    data = await cf.read()
                    cookies_dict = await self.async_json_loads(data)

                async with httpx.AsyncClient(cookies=cookies_dict, timeout=10) as client:
                    try:
                        resp = await client.get(url=url)
                        logger.debug(f"{self.tracker}: [cyan]Validating {self.tracker} Cookies:")

                        if "Logout" in resp.text:
                            return True
                        logger.info(f"{self.tracker}: [yellow]Valid session not found in cookies")
                        return False

                    except httpx.TimeoutException:
                        logger.info(f"{self.tracker}: [red]Connection to {url} timed out. The site may be down or unreachable.")
                        meta.mtv_timeout = True
                        return False
                    except httpx.ConnectError:
                        logger.error(f"{self.tracker}: [red]Failed to connect to {url}. The site may be down or your connection is blocked.")
                        meta.mtv_timeout = True
                        return False
                    except httpx.HTTPError as e:
                        logger.error(f"{self.tracker}: [red]HTTP error connecting to {self.tracker}: {escape(str(e))}")
                        return False
            except (OSError, ValueError) as e:
                logger.error(f"{self.tracker}: [red]Error loading cookies: {escape(str(e))}")
                return False
        else:
            logger.info(f"{self.tracker}: [yellow]Cookie file not found")
            return False

    async def get_auth(self, cookiefile: str) -> str:
        url = f"{self.base_url}/index.php"
        try:
            if await aiofiles.os.path.exists(cookiefile):
                async with aiofiles.open(cookiefile, encoding="utf-8") as cf:
                    data = await cf.read()
                    cookies = await self.async_json_loads(data)

                async with httpx.AsyncClient(cookies=cookies, timeout=10) as client:
                    try:
                        resp = await client.get(url=url)
                        if "authkey=" in resp.text:
                            return resp.text.rsplit("authkey=", 1)[1][:32]
                        logger.info(f"{self.tracker}: [yellow]Auth key not found in response")
                        return ""
                    except httpx.RequestError as e:
                        logger.error(f"{self.tracker}: [red]Error getting auth key: {escape(str(e))}")
                        return ""
            else:
                logger.info(f"{self.tracker}: [yellow]Cookie file not found for auth key retrieval")
                return ""
        except (OSError, ValueError) as e:
            logger.error(f"{self.tracker}: [red]Error loading cookies or parsing JSON: {escape(str(e))}")
            return ""

    async def login(self, cookiefile: str, meta: Meta | None = None) -> bool:
        try:
            async with httpx.AsyncClient(timeout=25, follow_redirects=True) as client:
                url = f"{self.base_url}/login"
                payload = {
                    "username": self.config["TRACKERS"][self.tracker].get("username"),
                    "password": self.config["TRACKERS"][self.tracker].get("password"),
                    "keeploggedin": 1,
                    "cinfo": "1920|1080|24|0",
                    "submit": "login",
                    "iplocked": 1,
                }

                try:
                    res = await client.get(url=f"{self.base_url}/login")

                    if 'name="token" value="' not in res.text:
                        logger.info(f"{self.tracker}: [red]Unable to find token in login page")
                        return False

                    token = res.text.rsplit('name="token" value="', 1)[1][:48]

                    payload["token"] = token
                    resp = await client.post(url=url, data=payload)

                    if str(resp.url).endswith("twofactor/login"):
                        otp_uri = self.config["TRACKERS"][self.tracker].get("otp_uri")
                        if otp_uri:
                            try:
                                otp = pyotp.parse_uri(otp_uri)
                                mfa_code = pyotp.TOTP(otp.secret).now()
                            except ValueError, TypeError:
                                if meta and meta.unattended and not meta.unattended_confirm:
                                    logger.error(f"{self.tracker}: [red]Unattended mode: 2FA required. Skipping login.[/red]")
                                    return False
                                mfa_code = console.input(f"[yellow]{self.tracker} 2FA Code: ")
                        else:
                            if meta and meta.unattended and not meta.unattended_confirm:
                                logger.error(f"{self.tracker}: [red]Unattended mode: 2FA required. Skipping login.[/red]")
                                return False
                            mfa_code = console.input(f"[yellow]{self.tracker} 2FA Code: ")

                        two_factor_token = resp.text.rsplit('name="token" value="', 1)[1][:48]
                        two_factor_payload = {"token": two_factor_token, "code": mfa_code, "submit": "login"}
                        resp = await client.post(url=f"{self.base_url}/twofactor/login", data=two_factor_payload)

                    await asyncio.sleep(1)
                    if "authkey=" in resp.text:
                        logger.info(f"{self.tracker}: [green]Successfully logged in to {self.tracker}")
                        cookies_dict = dict(client.cookies)
                        cookies_data = await self.async_json_dumps(cookies_dict)
                        async with aiofiles.open(cookiefile, "w", encoding="utf-8") as cf:
                            await cf.write(cookies_data)
                        logger.info(f"{self.tracker}: [green]Cookies saved to {cookiefile}")
                        return True
                    logger.info(f"{self.tracker}: [bold red]Something went wrong while trying to log into {self.tracker}")
                    logger.info(f"{self.tracker}: [red]Final URL: {resp.url}")
                    return False

                except httpx.TimeoutException:
                    logger.info(f"{self.tracker}: [red]Connection to {self.tracker} timed out. The site may be down or unreachable.")
                    return False
                except httpx.ConnectError:
                    logger.error(f"{self.tracker}: [red]Failed to connect to {self.tracker}. The site may be down or your connection is blocked.")
                    return False
                except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
                    logger.error(f"{self.tracker}: [red]Error during {self.tracker} login: {escape(str(e))}")
                    logger.info(f"{self.tracker}: [dim red]{escape(traceback.format_exc())}[/dim red]")
                    return False
        except Exception as e:
            logger.error(f"{self.tracker}: [red]Unexpected error during login: {escape(str(e))}")
            logger.info(f"{self.tracker}: [dim red]{escape(traceback.format_exc())}[/dim red]")
            raise
        return False

    async def get_additional_checks(self, meta: Meta) -> bool:
        if meta.type not in ["WEBDL"] and meta.tag and any(x in meta.tag for x in ["EVO"]):
            if not meta.unattended or (meta.unattended and meta.unattended_confirm):
                logger.info(f"{self.tracker}: [bold red]Group {meta.tag} is only allowed for raw type content at {self.tracker}[/bold red]")
                if cli_ui.ask_yes_no("Do you want to upload anyway?", default=False):
                    pass
                else:
                    return False
            else:
                return False

        allowed_anime = [
            "Thighs",
            "sam",
            "Vanilla",
            "OZR",
            "Netaro",
            "Datte13",
            "UDF",
            "Baws",
            "ARC",
            "Dae",
            "MTBB",
            "Okay-Subs",
            "hchcsen",
            "Noyr",
            "TTGA",
            "GJM",
            "Kaleido-Subs",
            "GJM-Kaleido",
            "LostYears",
            "Reza",
            "Aergia",
            "Drag",
            "Crow",
            "Arid",
            "JySzE",
            "iKaos",
            "Spirale",
            "CsS",
            "FLE",
            "WSE",
            "Legion",
            "AC",
            "UQW",
            "Commie",
            "Chihiro",
        ]
        if meta.resolution not in ["2160p"] and meta.video_codec in ["HEVC"]:
            if meta.anime and meta.tag and not any(x in meta.tag for x in allowed_anime):
                if not meta.unattended or (meta.unattended and meta.unattended_confirm):
                    logger.info(f"{self.tracker}: [bold red]Only 4K HEVC anime releases from {meta.tag} are allowed at {self.tracker}[/bold red]")
                    if cli_ui.ask_yes_no("Do you want to upload anyway?", default=False):
                        pass
                    else:
                        return False
            else:
                logger.info(f"{self.tracker}: [bold red]Only 4K HEVC releases are allowed at {self.tracker}[/bold red]")
                if not meta.unattended or (meta.unattended and meta.unattended_confirm):
                    if cli_ui.ask_yes_no("Do you want to upload anyway?", default=False):
                        pass
                    else:
                        return False
                else:
                    return False

        disallowed_keywords = {"xxx", "erotic", "porn"}
        disallowed_genres = {"adult", "erotica"}
        keywords_list = list(meta.keywords)
        genres_value = meta.combined_genres
        genres_list: list[str] = []
        if isinstance(genres_value, list):
            genres_list.extend(list(genres_value))
        else:
            genres_list.append(genres_value)
        keywords_lower = {k.lower() for k in keywords_list if k}
        genres_lower = {g.lower() for g in genres_list if g}
        if any(keyword in keywords_lower for keyword in disallowed_keywords) or any(genre in genres_lower for genre in disallowed_genres):
            if not meta.unattended or (meta.unattended and meta.unattended_confirm):
                logger.info(f"{self.tracker}: [bold red]Porn/xxx is not allowed at {self.tracker}.[/bold red]")
                if cli_ui.ask_yes_no("Do you want to upload anyway?", default=False):
                    pass
                else:
                    return False
            else:
                return False

        return True

    async def search_existing(self, meta: Meta) -> list[dict[str, Any]]:
        dupes: list[dict[str, Any]] = []

        # Build request parameters
        params = {"t": "search", "apikey": self.config["TRACKERS"][self.tracker]["api_key"].strip(), "q": "", "limit": "100"}

        if meta.imdb_id != 0:
            params["imdbid"] = "tt" + str(meta.imdb)
        elif meta.tmdb:
            params["tmdbid"] = str(meta.tmdb)
        elif meta.tvdb_id != 0:
            params["tvdbid"] = str(meta.tvdb_id)
        else:
            params["q"] = meta.title.replace(": ", " ").replace("’", "").replace("'", "")  # noqa: RUF001

        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(url=self.search_url, params=params)
            response.raise_for_status()

            # Parse XML response
            loop = asyncio.get_running_loop()
            response_xml = await loop.run_in_executor(None, lambda: ElementTree.fromstring(response.text))
            channel = cast(Any | None, response_xml.find("channel"))
            if channel is not None:
                for each in channel.findall("item"):
                    title = str(each.findtext("title") or "")
                    files_text = str(each.findtext("files") or "0")
                    size_text = str(each.findtext("size") or "0")
                    guid = str(each.findtext("guid") or "")
                    link = str(each.findtext("link") or "")
                    result = {"name": title, "files": title, "file_count": int(files_text), "size": int(size_text), "link": guid, "download": link}
                    dupes.append(result)

        return dupes
