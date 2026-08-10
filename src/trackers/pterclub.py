# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import glob
import json
import re
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlparse

import aiofiles
import httpx
from bs4 import BeautifulSoup
from unidecode import unidecode

from src.cogs.redaction import Redaction
from src.console import logger
from src.cookie_auth import CookieValidator
from src.exceptions import *  # noqa E403
from src.meta import Meta
from src.temp_paths import screenshots_dir
from src.trackers.common import Common

Config = dict[str, Any]


class PTerClub:
    """
    PTERCLUB (PT之友俱乐部) is a CHINESE Private Torrent Tracker for HD MUSIC VIDEOS / MOVIES / TV / ANIME
    """

    base_url = "https://pterclub.net"

    auth_type = "cookies"
    tracker = "PTERCLUB"
    display_name = "PTerClub"
    allows_bloated_audio = True
    source_flag = "PTER"
    ptgen_retry = 3
    signature: str | None = None
    banned_groups: tuple[str, ...] = ("",)
    supported_categories = ("TV", "MOVIE")

    def __init__(self, config: Config) -> None:
        self.config: Config = config
        self.passkey = str(config["TRACKERS"][self.tracker].get("passkey", "")).strip()
        self.username = str(config["TRACKERS"][self.tracker].get("username", "")).strip()
        self.password = str(config["TRACKERS"][self.tracker].get("password", "")).strip()
        self.rehost_images = bool(config["TRACKERS"][self.tracker].get("img_rehost", False))
        self.ptgen_api = str(config["TRACKERS"][self.tracker].get("ptgen_api", "")).strip()
        self.cookie_validator = CookieValidator(config)

    def _extract_auth_token(self, text: str, pattern: str) -> str:
        match = re.search(pattern, text)
        if match is None:
            raise LoginError("Unable to locate auth token for Pterimg.")  # noqa: F405
        return match.group(1)

    async def validate_credentials(self, meta: Meta) -> bool:
        vcookie = await self.validate_cookies(meta)
        if vcookie is not True:
            logger.error(f"{self.tracker}: [red]Failed to validate cookies. Please confirm that the site is up and your passkey is valid.")
            return False
        return True

    async def validate_cookies(self, meta: Meta) -> bool:
        common = Common(config=self.config)
        url = f"{self.base_url}"
        from src.cookie_auth import find_cookie_file

        cookiefile = find_cookie_file(meta.base_dir, self.tracker, self.config)
        if Path(cookiefile).exists():
            cookies = await common.parse_cookie_file(cookiefile)
            async with httpx.AsyncClient(cookies=cookies, timeout=30.0, follow_redirects=True) as client:
                resp = await client.get(url=url)

                return resp.text.find("""<a href="#" data-url="logout.php" id="logout-confirm">""") != -1
        else:
            logger.info(f"{self.tracker}: [bold red]Missing Cookie File. (data/cookies/PTERCLUB.txt)")
            return False

    async def search_existing(self, meta: Meta) -> list[str] | bool:
        dupes: list[str] = []
        common = Common(config=self.config)
        from src.cookie_auth import find_cookie_file

        cookiefile = find_cookie_file(meta.base_dir, self.tracker, self.config)
        if not Path(cookiefile).exists():
            logger.info(f"{self.tracker}: [bold red]Missing Cookie File. (data/cookies/PTERCLUB.txt)")
            return False
        cookies = await common.parse_cookie_file(cookiefile)
        imdb_id = meta.imdb_id or 0
        imdb = f"tt{meta.imdb}" if imdb_id != 0 else ""
        source = await self.get_type_medium_id(meta)
        search_url = f"{self.base_url}/torrents.php?search={imdb}&incldead=0&search_mode=0&source{source}=1"

        async with httpx.AsyncClient(cookies=cookies, timeout=10.0, follow_redirects=True) as client:
            response = await client.get(search_url)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "lxml")
            rows = soup.select("table.torrents > tr:has(table.torrentname)")
            for row in rows:
                text = row.select_one('a[href^="details.php?id="]')
                if text is not None:
                    release_value = text.attrs.get("title", "")
                    release = str(release_value)
                    if release:
                        dupes.append(release)

        return dupes

    async def get_type_category_id(self, meta: Meta) -> str:
        cat_id = "EXIT"
        category = meta.category

        if category == "MOVIE":
            cat_id = "401"

        if category == "TV":
            cat_id = "404"
        genres = ", ".join(meta.genres)
        keywords = ", ".join(meta.keywords)
        if "documentary" in genres.lower() or "documentary" in keywords.lower():
            cat_id = "402"

        if "animation" in genres.lower() or "animation" in keywords.lower():
            cat_id = "403"

        return cat_id

    async def get_area_id(self, meta: Meta) -> int:

        area_id = 8
        area_map = {  # To do
            "中国大陆": 1,
            "中国香港": 2,
            "中国台湾": 3,
            "美国": 4,
            "日本": 6,
            "韩国": 5,
            "印度": 7,
            "法国": 4,
            "意大利": 4,
            "德国": 4,
            "西班牙": 4,
            "葡萄牙": 4,
            "英国": 4,
            "阿根廷": 8,
            "澳大利亚": 4,
            "比利时": 4,
            "巴西": 8,
            "加拿大": 4,
            "瑞士": 4,
            "智利": 8,
        }
        ptgen = meta.ptgen
        regions_value = ptgen.get("region", [])
        regions = cast(list[str], regions_value) if isinstance(regions_value, list) else []
        for area in area_map:
            if area in regions:
                return area_map[area]
        return area_id

    async def get_type_medium_id(self, meta: Meta) -> str:
        medium_id = "EXIT"
        # 1 = UHD Discs
        if meta.is_disc in ("BDMV", "HD DVD"):
            medium_id = "1" if meta.resolution == "2160p" else "2"  # BD Discs

        if meta.is_disc == "DVD":
            medium_id = "7"

        # 4 = HDTV
        if meta.type == "HDTV":
            medium_id = "4"

        # 6 = Encode
        if meta.type in ("ENCODE", "WEBRIP"):
            medium_id = "6"

        # 3 = Remux
        if meta.type == "REMUX":
            medium_id = "3"

        # 5 = WEB-DL
        if meta.type == "WEBDL":
            medium_id = "5"

        return medium_id

    async def edit_desc(self, meta: Meta) -> None:
        from src.description_review import get_base_description

        base = get_base_description(meta)

        from src.bbcode import BBCODE
        from src.trackers.common import Common

        common = Common(config=self.config)

        parts: list[str] = []

        if meta.imdb_id or 0 != 0:
            ptgen = await common.ptgen(meta, self.ptgen_api, self.ptgen_retry)
            if ptgen.strip() != "":
                parts.append(ptgen)

        bbcode = BBCODE()
        if meta.discs != []:
            discs = cast(list[dict[str, Any]], meta.discs)
            for each in discs:
                if each["type"] == "BDMV":
                    parts.append(f"[hide=BDInfo]{each['summary']}[/hide]\n")
                    parts.append("\n")
                if each["type"] == "DVD":
                    parts.append(f"{each['name']}:\n")
                    parts.append(f"[hide=mediainfo]{each['vob_mi']}[/hide] [hide=mediainfo]{each['ifo_mi']}[/hide]\n")
                    parts.append("\n")
        else:
            async with aiofiles.open(f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/MEDIAINFO_CLEANPATH.txt", encoding="utf-8") as mi_file:
                mi = await mi_file.read()
            parts.append(f"[hide=mediainfo]{mi}[/hide]")
            parts.append("\n")
        desc = base
        desc = bbcode.convert_code_to_quote(desc)
        desc = bbcode.convert_spoiler_to_hide(desc)
        desc = bbcode.convert_comparison_to_centered(desc, 1000)
        desc = desc.replace("[img]", "[img]")
        desc = re.sub(r"(\[img=\d+)]", "[img]", desc, flags=re.IGNORECASE)
        parts.append(desc)

        if self.rehost_images is True:
            logger.info(f"{self.tracker}: [green]Rehosting Images...")
            images = await self.pterimg_upload(meta)
            if len(images) > 0:
                parts.append("[center]")
                for each in range(len(images[: meta.screens])):
                    web_url = images[each]["web_url"]
                    img_url = images[each]["img_url"]
                    parts.append(f"[url={web_url}][img]{img_url}[/img][/url]")
                parts.append("[/center]")
        else:
            images = meta.image_list
            if len(images) > 0:
                parts.append("[center]")
                for each in range(len(images[: meta.screens])):
                    web_url = images[each]["web_url"]
                    img_url = images[each]["img_url"]
                    parts.append(f"[url={web_url}][img]{img_url}[/img][/url]")
                parts.append("[/center]")

        if self.signature is not None:
            parts.append("\n\n")
            parts.append(self.signature)

        async with aiofiles.open(f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/[{self.tracker}]DESCRIPTION.txt", "w", encoding="utf-8") as descfile:
            await descfile.write("".join(parts))

    async def get_auth_token(self, meta: Meta) -> str:
        if not Path(f"{meta.base_dir}/data/cookies").exists():
            Path(f"{meta.base_dir}/data/cookies").mkdir(parents=True, exist_ok=True)
        from src.cookie_auth import find_cookie_file

        cookiefile = find_cookie_file(meta.base_dir, "Pterimg", self.config)
        logged_in = False
        response: httpx.Response | None = None
        cookies: dict[str, str] = {}
        if Path(cookiefile).exists():
            raw_cookies = self.cookie_validator._load_cookies_dict_secure(cookiefile)  # pyright: ignore[reportPrivateUsage]
            cookies = {name: str(data.get("value", "")) for name, data in raw_cookies.items()}
            async with httpx.AsyncClient(cookies=cookies, timeout=30.0, follow_redirects=True) as client:
                response = await client.get("https://s3.pterclub.com")
                logged_in = await self.validate_login(response)
                if logged_in is True:
                    return self._extract_auth_token(response.text, r'auth_token.*?"(\w+)"')
        else:
            logger.info(f"{self.tracker}: [yellow]Pterimg Cookies not found. Creating new session.")

        data = {"login-subject": self.username, "password": self.password, "keep-login": 1}
        async with httpx.AsyncClient(cookies=cookies, timeout=30.0, follow_redirects=True) as client:
            response = await client.get("https://s3.pterclub.com")
            data["auth_token"] = self._extract_auth_token(response.text, r'auth_token.*?"(\w+)"')
            loginresponse = await client.post(url="https://s3.pterclub.com/login", data=data)
            if not loginresponse.is_success:
                raise LoginError("Failed to login to Pterimg. ")  # noqa #F405
            auth_token = self._extract_auth_token(loginresponse.text, r'auth_token = *?"(\w+)"')
            self.cookie_validator._save_cookies_secure(client.cookies.jar, cookiefile)  # pyright: ignore[reportPrivateUsage]

        return auth_token

    async def validate_login(self, response: httpx.Response) -> bool:
        return response.text.find("""<a href="https://s3.pterclub.com/logout/?""") != -1

    async def pterimg_upload(self, meta: Meta) -> list[dict[str, str]]:
        images = [str(p) for p in screenshots_dir(meta.base_dir, meta.uuid).glob(f"{glob.escape(meta.filename)}-*.png")]
        url = "https://s3.pterclub.com"
        image_list: list[dict[str, str]] = []
        data: dict[str, Any] = {"type": "file", "action": "upload", "nsfw": 0, "auth_token": await self.get_auth_token(meta)}
        from src.cookie_auth import find_cookie_file

        cookiefile = find_cookie_file(meta.base_dir, "Pterimg", self.config)
        if Path(cookiefile).exists():
            raw_cookies = self.cookie_validator._load_cookies_dict_secure(cookiefile)  # pyright: ignore[reportPrivateUsage]
            cookies = {name: str(data.get("value", "")) for name, data in raw_cookies.items()}
            async with httpx.AsyncClient(cookies=cookies, timeout=60.0, follow_redirects=True) as client:
                for image_path in images:
                    async with aiofiles.open(image_path, "rb") as f:
                        file_bytes = await f.read()
                    req = await client.post(
                        f"{url}/json",
                        data=data,
                        files={"source": (Path(image_path).name, file_bytes)},
                    )

                    res: Any = None
                    try:
                        res = req.json()
                    except json.decoder.JSONDecodeError:
                        res = None

                    message = None
                    if isinstance(res, dict):
                        res_dict = cast(dict[str, Any], res)
                        error = cast(dict[str, Any], res_dict.get("error", {}))
                        message = error.get("message")
                    if not message:
                        message = (req.reason_phrase or "").strip() or (req.text or "").strip()

                    if not req.is_success:
                        if message in ("重复上传", "Duplicated upload"):
                            continue
                        raise Exception(f"HTTP {req.status_code}, reason: {message}")

                    if not isinstance(res, dict):
                        raise ValueError("Unexpected response payload while uploading to Pterimg.")
                    res_dict = cast(dict[str, Any], res)
                    image_data = res_dict.get("image")
                    if not isinstance(image_data, dict):
                        raise ValueError("Missing image data in Pterimg response.")
                    image_data_dict = cast(dict[str, Any], image_data)
                    image_url = image_data_dict.get("url")
                    if not isinstance(image_url, str):
                        raise ValueError("Missing image url in Pterimg response.")
                    image_dict = {
                        "web_url": image_url,
                        "img_url": image_url,
                    }
                    image_list.append(image_dict)
        return image_list

    async def get_name(self, meta: Meta) -> str:
        pter_name = meta.name

        remove_list = ["Dubbed", "Dual-Audio"]
        for each in remove_list:
            pter_name = pter_name.replace(each, "")

        pter_name = pter_name.replace(meta.aka, "")
        pter_name = pter_name.replace("PQ10", "HDR")

        if meta.type == "WEBDL" and meta.has_encode_settings is True:
            pter_name = pter_name.replace("H.264", "x264")

        return pter_name

    async def is_zhongzi(self, meta: Meta) -> str | None:
        if meta.is_disc != "BDMV":
            mi = meta.mediainfo
            media = cast(dict[str, Any], mi.get("media", {}))
            tracks = cast(list[dict[str, Any]], media.get("track", []))
            for track in tracks:
                if track["@type"] == "Text":
                    language = track.get("Language")
                    if language == "zh":
                        return "yes"
        else:
            bdinfo = meta.bdinfo
            subtitles = cast(list[str], bdinfo.get("subtitles", []))
            for language in subtitles:
                if language == "Chinese":
                    return "yes"
        return None

    async def upload(self, meta: Meta) -> bool:

        common = Common(config=self.config)
        await common.create_torrent_for_upload(meta, self.tracker, self.source_flag)

        desc_file = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/[{self.tracker}]DESCRIPTION.txt"
        if not Path(desc_file).exists():
            await self.edit_desc(meta)

        anon = "no" if meta.anon == 0 and not self.config["TRACKERS"][self.tracker].get("anon", False) else "yes"

        pter_name = await self.get_name(meta)

        mi_path = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/BD_SUMMARY_00.txt" if meta.bdinfo else f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/MEDIAINFO.txt"
        async with aiofiles.open(mi_path, encoding="utf-8") as mi_dump:
            _ = await mi_dump.read()
        async with aiofiles.open(desc_file, encoding="utf-8") as desc_handle:
            pter_desc = await desc_handle.read()
        torrent_path = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/[{self.tracker}].torrent"

        async with aiofiles.open(torrent_path, "rb") as torrent_file_handle:
            torrent_bytes = await torrent_file_handle.read()
        filelist = meta.filelist
        torrent_file_name = unidecode(Path(meta.video).name.replace(" ", ".")) if len(filelist) == 1 else unidecode(Path(str(meta.path)).name.replace(" ", "."))
        files = {
            "file": (f"{torrent_file_name}.torrent", torrent_bytes, "application/x-bittorent"),
        }

        # use chinese small_descr
        ptgen = meta.ptgen
        trans_title = cast(list[str], ptgen.get("trans_title", []))
        genres = cast(list[str], ptgen.get("genre", []))
        if trans_title != [""]:
            small_descr = ""
            for title_ in trans_title:
                small_descr += f"{title_} / "
            genre_value = genres[0] if genres else ""
            small_descr += "| 类别:" + genre_value
            small_descr = small_descr.replace("/ |", "|")
        else:
            small_descr = meta.title
        data: dict[str, Any] = {
            "name": pter_name,
            "small_descr": small_descr,
            "descr": pter_desc,
            "type": await self.get_type_category_id(meta),
            "source_sel": await self.get_type_medium_id(meta),
            "team_sel": await self.get_area_id(meta),
            "uplver": anon,
            "zhongzi": await self.is_zhongzi(meta),
        }
        if meta.personalrelease is True:
            data["pr"] = "yes"

        url = f"{self.base_url}/takeupload.php"

        # Submit
        if meta.debug:
            logger.debug(url)
            logger.debug(Redaction.redact_private_info(data))
            meta.tracker_status[self.tracker]["status_message"] = "Debug mode enabled, not uploading."
            await common.create_torrent_for_upload(meta, f"{self.tracker}" + "_DEBUG", f"{self.tracker}" + "_DEBUG", announce_url="https://fake.tracker")
            return True  # Debug mode - simulated success
        from src.cookie_auth import find_cookie_file

        cookiefile = find_cookie_file(meta.base_dir, self.tracker, self.config)
        if Path(cookiefile).exists():
            cookies = await common.parse_cookie_file(cookiefile)
            async with httpx.AsyncClient(cookies=cookies, timeout=30.0, follow_redirects=True) as client:
                up = await client.post(url=url, data=data, files=files)

                if str(up.url).startswith(f"{self.base_url}/details.php?id="):
                    logger.info(f"{self.tracker}: [green]Uploaded to: [yellow]{str(up.url).replace('&uploaded=1', '')}[/yellow][/green]")
                    id_match = re.search(r"(id=)(\d+)", urlparse(str(up.url)).query)
                    if id_match is None:
                        raise UploadError("Upload succeeded but torrent id was not present in the redirect URL.", "red")  # noqa: F405
                    torrent_id = id_match.group(2)
                    await self.download_new_torrent(torrent_id, torrent_path)
                    meta.tracker_status[self.tracker]["status_message"] = str(up.url).replace("&uploaded=1", "")
                    meta.tracker_status[self.tracker]["torrent_id"] = torrent_id
                    return True
                logger.info(data)
                logger.info(f"{self.tracker}: \n\n")
                raise UploadError(f"Upload to Pter Failed: result URL {up.url} ({up.status_code}) was not expected", "red")  # noqa #F405
        return False

    async def download_new_torrent(self, id: str, torrent_path: str) -> None:
        download_url = f"{self.base_url}/download.php?id={id}&passkey={self.passkey}"
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            r = await client.get(url=download_url)
        if r.status_code == 200:
            async with aiofiles.open(torrent_path, "wb") as tor:
                await tor.write(r.content)
        else:
            logger.info(f"{self.tracker}: [red]There was an issue downloading the new .torrent from pter")
            logger.info(r.text)
