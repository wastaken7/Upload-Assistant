# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import asyncio
import re
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlparse

import aiofiles
import cli_ui
import httpx
from bs4 import BeautifulSoup
from unidecode import unidecode

from src.cogs.redaction import Redaction
from src.console import console, logger
from src.cookie_auth import CookieValidator
from src.exceptions import *  # noqa #F405
from src.meta import Meta
from src.trackers.common import Common

Config = dict[str, Any]


class ToTheGlory:
    """
    TTG Private Torrent Tracker
    """

    base_url = "https://totheglory.im"

    auth_type = "cookies"
    tracker = "TOTHEGLORY"
    display_name = "ToTheGlory"
    allows_bloated_audio = True
    source_flag = "TTG"
    signature = None
    banned_groups = ("",)
    supported_categories = ("TV", "MOVIE")

    def __init__(self, config: Config) -> None:
        self.config: Config = config
        self.username = str(config["TRACKERS"][self.tracker].get("username", "")).strip()
        self.password = str(config["TRACKERS"][self.tracker].get("password", "")).strip()
        self.passid = str(config["TRACKERS"][self.tracker].get("login_question", "0")).strip()
        self.passan = str(config["TRACKERS"][self.tracker].get("login_answer", "")).strip()
        self.uid = str(config["TRACKERS"][self.tracker].get("user_id", "")).strip()
        self.passkey = str(config["TRACKERS"][self.tracker].get("announce_url", "")).strip().split("/")[-1]
        self.cookie_validator = CookieValidator(config)

    async def get_name(self, meta: Meta) -> str:
        ttg_name = meta.name

        remove_list = ["Dubbed", "Dual-Audio"]
        for each in remove_list:
            ttg_name = ttg_name.replace(each, "")
        ttg_name = ttg_name.replace("PQ10", "HDR")
        return ttg_name.replace(".", "{@}")

    async def get_type_id(self, meta: Meta) -> int:
        type_id = 0
        lang = str(meta.original_language).upper()
        category = meta.category
        resolution = meta.resolution
        if meta.category == "MOVIE":
            # 51 = DVDRip
            if resolution.startswith("720"):
                type_id = 52  # 720p
            if resolution.startswith("1080"):
                type_id = 53  # 1080p/i
            if meta.is_disc == "BDMV":
                type_id = 54  # Blu-ray disc

        elif category == "TV":
            if meta.tv_pack != 1:
                # TV Singles
                if resolution.startswith("720"):
                    type_id = 69  # 720p TV EU/US
                    if lang in ("ZH", "CN", "CMN"):
                        type_id = 76  # Chinese
                if resolution.startswith("1080"):
                    type_id = 70  # 1080 TV EU/US
                    if lang in ("ZH", "CN", "CMN"):
                        type_id = 75  # Chinese
                if lang in ("KR", "KO"):
                    type_id = 75  # Korean
                if lang in ("JA", "JP"):
                    type_id = 73  # Japanese
            else:
                # TV Packs
                type_id = 87  # EN/US
                if lang in ("KR", "KO"):
                    type_id = 99  # Korean
                if lang in ("JA", "JP"):
                    type_id = 88  # Japanese
                if lang in ("ZH", "CN", "CMN"):
                    type_id = 90  # Chinese

        genres_value = str(meta.genres).lower().replace(" ", "").replace("-", "")
        keywords_value = str(meta.keywords).lower().replace(" ", "").replace("-", "")
        if "documentary" in genres_value or "documentary" in keywords_value:
            if resolution.startswith("720"):
                type_id = 62  # 720p
            if resolution.startswith("1080"):
                type_id = 63  # 1080
            if meta.is_disc == "BDMV":
                type_id = 64  # BDMV

        if ("animation" in genres_value or "animation" in keywords_value) and meta.sd == 0:
            type_id = 58

        if resolution in ("2160p"):
            type_id = 108
            if meta.is_disc == "BDMV":
                type_id = 109

        # I guess complete packs?:
        # 103 = TV Shows KR
        # 101 = TV Shows JP
        # 60 = TV Shows
        return type_id

    async def upload(self, meta: Meta) -> bool | None:
        common = Common(config=self.config)
        await common.create_torrent_for_upload(meta, self.tracker, self.source_flag)
        await self.edit_desc(meta)
        ttg_name = await self.get_name(meta)

        # FORM
        # type = category dropdown
        # name = name
        # descr = description
        # anonymity = "yes" / "no"
        # nodistr = "yes" / "no" (exclusive?) not required
        # imdb_c = tt123456
        #
        # POST > upload/upload

        anon = "no" if meta.anon == 0 and not self.config["TRACKERS"][self.tracker].get("anon", False) else "yes"

        mi_path = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/BD_SUMMARY_00.txt" if meta.bdinfo else f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/MEDIAINFO.txt"

        async with aiofiles.open(
            f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/[{self.tracker}]DESCRIPTION.txt",
            encoding="utf-8",
        ) as desc_file:
            ttg_desc = await desc_file.read()
        torrent_path = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/[{self.tracker}].torrent"
        filelist = meta.filelist
        async with aiofiles.open(torrent_path, "rb") as torrent_file:
            torrent_bytes = await torrent_file.read()
        torrent_file_name = unidecode(Path(meta.video).name.replace(" ", ".")) if len(filelist) == 1 else unidecode(Path(str(meta.path)).name.replace(" ", "."))
        async with aiofiles.open(mi_path, encoding="utf-8") as mi_dump:
            mi_text = await mi_dump.read()
        files = {"file": (f"{torrent_file_name}.torrent", torrent_bytes, "application/x-bittorent"), "nfo": ("torrent.nfo", mi_text)}
        data: dict[str, Any] = {
            "MAX_FILE_SIZE": "4000000",
            "team": "",
            "hr": "no",
            "name": ttg_name,
            "type": await self.get_type_id(meta),
            "descr": ttg_desc.rstrip(),
            "anonymity": anon,
            "nodistr": "no",
        }
        url = f"{self.base_url}/takeupload.php"
        if meta.imdb_id or 0 != 0:
            data["imdb_c"] = f"tt{meta.imdb}"

        # Submit
        if meta.debug:
            logger.debug(url)
            logger.debug(Redaction.redact_private_info(data))
            tracker_status = meta.tracker_status
            tracker_status.setdefault(self.tracker, {})
            tracker_status[self.tracker]["status_message"] = "Debug mode enabled, not uploading."
            await common.create_torrent_for_upload(meta, f"{self.tracker}" + "_DEBUG", f"{self.tracker}" + "_DEBUG", announce_url="https://fake.tracker")
            return True  # Debug mode - simulated success
        cookiefile = str(Path(f"{meta.base_dir}/data/cookies/{self.tracker}.json").resolve())
        raw_cookies = self.cookie_validator._load_cookies_dict_secure(cookiefile)  # type: ignore[reportPrivateUsage]
        cookies = {name: str(data.get("value", "")) for name, data in raw_cookies.items()}
        async with httpx.AsyncClient(cookies=cookies, follow_redirects=True, timeout=60.0) as client:
            up = await client.post(url=url, data=data, files=files)

        if str(up.url).startswith(f"{self.base_url}/details.php?id="):
            tracker_status = meta.tracker_status
            tracker_status.setdefault(self.tracker, {})
            tracker_status[self.tracker]["status_message"] = str(up.url)
            id_match = re.search(r"(id=)(\d+)", urlparse(str(up.url)).query)
            if not id_match:
                raise UploadError(  # noqa #F405
                    f"Upload to {self.tracker} succeeded but torrent id missing from URL {up.url}",
                    "red",
                )
            torrent_id = id_match.group(2)
            await self.download_new_torrent(torrent_id, torrent_path)
            return True
        logger.info(data)
        logger.info(f"{self.tracker}: \n\n")
        raise UploadError(f"Upload to {self.tracker} Failed: result URL {up.url} ({up.status_code}) was not expected", "red")  # noqa #F405

    async def search_existing(self, meta: Meta) -> list[str]:
        dupes: list[str] = []
        cookiefile = str(Path(f"{meta.base_dir}/data/cookies/{self.tracker}.json").resolve())
        if not Path(cookiefile).exists():
            logger.info(f"{self.tracker}: [bold red]Cookie file not found: {self.tracker}.json")
            return []
        cookies = self.cookie_validator._load_cookies_dict_secure(cookiefile)  # type: ignore[reportPrivateUsage]

        imdb = f"imdb{meta.imdb}" if meta.imdb_id or 0 != 0 else ""
        if meta.is_disc == "BDMV":
            res_type = f"{meta.resolution} Blu-ray"
        elif meta.is_disc == "DVD":
            res_type = "DVD"
        else:
            res_type = meta.resolution

        search_url = f"{self.base_url}/browse.php?search_field= {imdb} {res_type}"

        async with httpx.AsyncClient(cookies=cookies, timeout=10.0) as client:
            response = await client.get(search_url)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            find = soup.find_all("a", href=True)
            for each in find:
                href_value = each.get("href")
                if isinstance(href_value, str) and href_value.startswith("/t/"):
                    release = re.search(r"(<b>)(<font.*>)?(.*)<br", str(each))
                    if release:
                        dupes.append(release.group(3))

            await asyncio.sleep(0.5)

        return dupes

    async def validate_credentials(self, meta: Meta) -> bool:
        cookiefile = str(Path(f"{meta.base_dir}/data/cookies/{self.tracker}.pkl").resolve())
        if not Path(cookiefile).exists():
            await self.login(cookiefile, meta)
        vcookie = await self.validate_cookies(meta, cookiefile)
        if vcookie is not True:
            logger.error(f"{self.tracker}: [red]Failed to validate cookies. Please confirm that the site is up and your passkey is valid.")
            if not meta.unattended or (meta.unattended and meta.unattended_confirm):
                recreate = cli_ui.ask_yes_no("Log in again and create new session?")
                if recreate is True:
                    if Path(cookiefile).exists():
                        Path(cookiefile).unlink()
                    await self.login(cookiefile, meta)
                    return await self.validate_cookies(meta, cookiefile)
            return False
        return True

    async def validate_cookies(self, meta: Meta, cookiefile: str) -> bool:  # noqa: ARG002
        url = f"{self.base_url}"
        if Path(cookiefile).exists():
            raw_cookies = self.cookie_validator._load_cookies_dict_secure(cookiefile)  # type: ignore[reportPrivateUsage]
            cookies = {name: str(data.get("value", "")) for name, data in raw_cookies.items()}
            async with httpx.AsyncClient(cookies=cookies, timeout=30.0, follow_redirects=True) as client:
                resp = await client.get(url=url)
                logger.debug(f"{self.tracker}: [cyan]Cookies:")
                logger.debug(resp.url)
                return resp.text.find("""<a href="/logout.php">Logout</a>""") != -1
        else:
            return False

    async def login(self, cookiefile: str, meta: Meta | None = None) -> None:
        url = f"{self.base_url}/takelogin.php"
        data: dict[str, Any] = {"username": self.username, "password": self.password, "passid": self.passid, "passan": self.passan}
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.post(url, data=data)
            await asyncio.sleep(0.5)
            if str(response.url).endswith("2fa.php"):
                soup = BeautifulSoup(response.text, "html.parser")
                token_input = soup.find("input", {"name": "authenticity_token"})
                auth_token = token_input.get("value") if token_input else None
                if not auth_token:
                    raise UploadError(f"Missing authenticity token during {self.tracker} login", "red")  # noqa #F405
                if meta and meta.unattended and not meta.unattended_confirm:
                    logger.error(f"{self.tracker}: [red]Unattended mode: 2FA required. Skipping login.[/red]")
                    return
                two_factor_data = {"otp": console.input(f"[yellow]{self.tracker} 2FA Code: "), "authenticity_token": auth_token, "uid": self.uid}
                two_factor_url = f"{self.base_url}/take2fa.php"
                response = await client.post(two_factor_url, data=two_factor_data)
                await asyncio.sleep(0.5)
            if str(response.url).endswith("my.php"):
                logger.info(f"{self.tracker}: [green]Successfully logged into {self.tracker}")
                self.cookie_validator._save_cookies_secure(client.cookies.jar, cookiefile)  # type: ignore[reportPrivateUsage]
            else:
                logger.info(f"{self.tracker}: [bold red]Something went wrong")
                await asyncio.sleep(1)
                logger.info(response.text)
                logger.info(response.url)
        return

    async def edit_desc(self, meta: Meta) -> None:
        from src.description_review import get_base_description

        base = get_base_description(meta)

        from src.bbcode import BBCODE
        from src.trackers.common import Common

        common = Common(config=self.config)

        parts: list[str] = []
        if meta.imdb_id or 0 != 0:
            ptgen = await common.ptgen(meta)
            if ptgen.strip() != "":
                parts.append(ptgen)

        # Add This line for all web-dls
        if meta.type == "WEBDL" and meta.service_longname != "" and not meta.description:
            parts.append(
                f"[center][b][color=#ff00ff][size=3]{meta.service_longname}的无损REMUX片源，没有转码/This release is sourced from {meta.service_longname} and is not transcoded, just remuxed from the direct {meta.service_longname} stream[/size][/color][/b][/center]"  # noqa: RUF001
            )
        bbcode = BBCODE()
        if meta.discs != []:
            discs = cast(list[dict[str, Any]], meta.discs)
            for each in discs:
                if each["type"] == "BDMV":
                    parts.append(f"[quote={each.get('name', 'BDINFO')}]{each['summary']}[/quote]\n")
                    parts.append("\n")
                if each["type"] == "DVD":
                    parts.append(f"{each.get('name', '')}:\n")
                    parts.append(
                        f"[quote={Path(str(each.get('vob', ''))).name}]{each.get('vob_mi', '')}[/quote] "
                        f"[quote={Path(str(each.get('ifo', ''))).name}]{each.get('ifo_mi', '')}[/quote]\n"
                    )
                    parts.append("\n")
        else:
            async with aiofiles.open(
                f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/MEDIAINFO_CLEANPATH.txt",
                encoding="utf-8",
            ) as mi_file:
                mi = await mi_file.read()
            parts.append(f"[quote=MediaInfo]{mi}[/quote]")
            parts.append("\n")
        desc = base
        desc = bbcode.convert_code_to_quote(desc)
        desc = bbcode.convert_spoiler_to_hide(desc)
        desc = bbcode.convert_comparison_to_centered(desc, 1000)
        desc = desc.replace("[img]", "[img]")
        desc = re.sub(r"(\[img=\d+)]", "[img]", desc, flags=re.IGNORECASE)
        parts.append(desc)
        images = meta.image_list
        if images:
            parts.append("[center]")
            screens = meta.screens or 0
            for each in range(len(images[:screens])):
                web_url = images[each].get("web_url")
                img_url = images[each].get("img_url")
                if not web_url or not img_url:
                    continue
                parts.append(f"[url={web_url}][img]{img_url}[/img][/url]")
            parts.append("[/center]")
        if self.signature is not None:
            parts.append("\n\n")
            parts.append(self.signature)

        async with aiofiles.open(
            f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/[{self.tracker}]DESCRIPTION.txt",
            "w",
            encoding="utf-8",
        ) as descfile:
            await descfile.write("".join(parts))

    async def download_new_torrent(self, id: str, torrent_path: str) -> None:
        download_url = f"{self.base_url}/dl/{id}/{self.passkey}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(url=download_url)
        if r.status_code == 200:
            async with aiofiles.open(torrent_path, "wb") as tor:
                await tor.write(r.content)
        else:
            logger.info(f"{self.tracker}: [red]There was an issue downloading the new .torrent from {self.tracker}")
            logger.info(r.text)
