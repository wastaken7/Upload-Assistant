# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import asyncio
import glob
import json
import re
from pathlib import Path
from typing import Any, cast

import aiofiles
import cli_ui
import httpx
from bs4 import BeautifulSoup
from rich.markup import escape
from unidecode import unidecode

from src.cogs.redaction import Redaction
from src.console import logger, prompt_in_thread
from src.cookie_auth import CookieValidator
from src.description_review import get_base_description
from src.exceptions import *  # noqa F403
from src.meta import Meta
from src.temp_paths import screenshots_dir
from src.trackers.common import Common


class FileList:
    """
    FL Private Torrent Tracker
    """

    auth_type = "cookies"
    tracker = "FILELIST"
    display_name = "FileList"
    allows_bloated_audio = True
    source_flag = "FL"
    signature: str | None = None
    banned_groups = ("",)
    base_url = "https://filelist.io"
    supported_categories = ("TV", "MOVIE")
    tracker_urls = ("reactor.filelist", "reactor.thefl.org")

    def __init__(self, config: dict[str, Any]) -> None:
        self.config: dict[str, Any] = config
        tracker_cfg = config["TRACKERS"][self.tracker]
        self.username: str = str(tracker_cfg.get("username", "")).strip()
        self.password: str = str(tracker_cfg.get("password", "")).strip()
        fltools_raw = tracker_cfg.get("fltools", {})
        self.fltools: dict[str, Any] = cast(dict[str, Any], fltools_raw) if isinstance(fltools_raw, dict) else {}
        uploader_name_raw = tracker_cfg.get("uploader_name")
        self.uploader_name: str | None = str(uploader_name_raw) if uploader_name_raw else None

        self.cookie_validator = CookieValidator(config)

    async def get_category_id(self, meta: Meta) -> int:
        _has_ro_audio, has_ro_sub = await self.get_ro_tracks(meta)
        cat_id = 4
        # 25 = 3D Movie
        if meta.category == "MOVIE":
            # 4 = Movie HD
            cat_id = 4
            if meta.is_disc == "BDMV" or meta.type == "REMUX":
                # 20 = BluRay
                cat_id = 20
                if meta.resolution == "2160p":
                    # 26 = 4k Movie - BluRay
                    cat_id = 26
            elif meta.resolution == "2160p":
                # 6 = 4k Movie
                cat_id = 6
            elif meta.sd == 1:
                # 1 = Movie SD
                cat_id = 1
            if has_ro_sub and meta.sd == 0 and meta.resolution != "2160p":
                # 19 = Movie + RO
                cat_id = 19

        if meta.category == "TV":
            # 21 = TV HD
            cat_id = 21
            if meta.resolution == "2160p":
                # 27 = TV 4k
                cat_id = 27
            elif meta.sd == 1:
                # 23 = TV SD
                cat_id = 23

        if meta.is_disc == "DVD":
            # 2 = DVD
            cat_id = 2
            if has_ro_sub:
                # 3 = DVD + RO
                cat_id = 3

        if meta.anime is True:
            # 24 = Anime
            cat_id = 24
        return cat_id

    async def get_name(self, meta: Meta) -> str:
        fl_name = meta.name
        hdr = meta.hdr
        audio = meta.audio
        if "DV" in hdr:
            fl_name = fl_name.replace(" DV ", " DoVi ")
        if meta.type in ("WEBDL", "WEBRIP", "ENCODE"):
            fl_name = fl_name.replace(audio, audio.replace(" ", "", 1))
        fl_name = fl_name.replace(meta.aka, "")
        imdb_info = meta.imdb_info
        if isinstance(imdb_info, dict):
            imdb_info_dict = imdb_info
            title = meta.title
            imdb_aka = str(imdb_info_dict.get("aka", ""))
            if imdb_aka:
                fl_name = fl_name.replace(title, imdb_aka)
            meta_year = str(meta.year).strip() if meta.year is not None else ""
            imdb_year = str(imdb_info_dict.get("year", meta_year))
            if meta_year and meta_year != imdb_year:
                fl_name = fl_name.replace(meta_year, imdb_year)
        if "DD+" in audio and "DDP" in meta.basename_no_ext:
            fl_name = fl_name.replace("DD+", "DDP")
        if "Atmos" in audio and "Atmos" not in meta.basename_no_ext:
            fl_name = fl_name.replace("Atmos", "")

        fl_name = fl_name.replace("BluRay REMUX", "Remux").replace("BluRay Remux", "Remux").replace("Bluray Remux", "Remux")
        fl_name = fl_name.replace("PQ10", "HDR").replace("HDR10+", "HDR")
        fl_name = fl_name.replace("DoVi HDR HEVC", "HEVC DoVi HDR").replace("HDR HEVC", "HEVC HDR").replace("DoVi HEVC", "HEVC DoVi")
        fl_name = fl_name.replace("DTS7.1", "DTS").replace("DTS5.1", "DTS").replace("DTS2.0", "DTS").replace("DTS1.0", "DTS")
        fl_name = fl_name.replace("Dubbed", "").replace("Dual-Audio", "")
        fl_name = " ".join(fl_name.split())
        fl_name = re.sub(r"[^0-9a-zA-ZÀ-ÿ. &+'\-\[\]]+", "", fl_name)
        return fl_name.replace(" ", ".").replace("..", ".")

    def _is_true(self, value: Any) -> bool:
        return str(value).strip().lower() in {"true", "1", "yes"}

    def _load_cookie_dict(self, cookiefile: str) -> dict[str, str]:
        path = Path(cookiefile)
        if not path.exists():
            return {}

        # If it's a Netscape cookies file (ends with .txt)
        if path.suffix.lower() == ".txt":
            cookies: dict[str, str] = {}
            try:
                with path.open("r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        if line.strip() and not line.startswith(("# ", "#")):
                            line_fields = re.split(r"\s+", line.strip())
                            if len(line_fields) >= 7:
                                cookies[line_fields[5]] = line_fields[6]
            except Exception as e:
                logger.error(f"{self.tracker}: [red]Error parsing {self.tracker} Netscape cookie file: {escape(str(e))}[/red]")
            return cookies

        # If it's a pickle file (ends with .pkl or .pickle)
        if path.suffix.lower() in [".pkl", ".pickle"]:
            try:
                import pickle

                with path.open("rb") as f:
                    session_cookies = pickle.load(f)  # noqa: S301
                # Save it as JSON with same name but .json extension (standard migration)
                json_path = path.with_suffix(".json")
                self.cookie_validator._save_cookies_secure(session_cookies, str(json_path))  # pyright: ignore[reportPrivateUsage]
                return {cookie.name: cookie.value for cookie in session_cookies}
            except Exception as e:
                logger.error(f"{self.tracker}: [red]Failed to migrate legacy cookies from pickle: {e}[/red]")
                return {}

        # Default to loading as JSON
        try:
            raw_cookies = self.cookie_validator._load_cookies_dict_secure(str(path))  # pyright: ignore[reportPrivateUsage]
            return {name: str(data.get("value", "")) for name, data in raw_cookies.items()}
        except Exception:
            # Maybe it's a raw JSON dict of {name: value} or {name: {"value": val}}?
            try:
                with path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    if data:
                        first_val = next(iter(data.values()))
                        if isinstance(first_val, dict) and "value" in first_val:
                            return {name: str(item.get("value", "")) for name, item in data.items()}
                    return {name: str(val) for name, val in data.items()}
            except Exception as e:
                logger.error(f"{self.tracker}: [yellow]Warning: Error parsing cookie file: {e}[/yellow]")
            return {}

    async def upload(self, meta: Meta) -> bool:
        common = Common(config=self.config)
        await common.create_torrent_for_upload(meta, self.tracker, self.source_flag)
        await self.edit_desc(meta)
        fl_name = await self.get_name(meta)
        cat_id = await self.get_category_id(meta)
        has_ro_audio, _has_ro_sub = await self.get_ro_tracks(meta)

        # Confirm the correct naming order for FILELIST
        cli_ui.info(f"Filelist name: {fl_name}")
        if meta.unattended is False:
            fl_confirm = await prompt_in_thread(cli_ui.ask_yes_no, "Correct?", default=False)
            if fl_confirm is not True:
                fl_name_manually = await prompt_in_thread(cli_ui.ask_string, "Please enter a proper name", default="")
                if fl_name_manually == "":
                    logger.info(f"{self.tracker}: No proper name given")
                    logger.info(f"{self.tracker}: Aborting...")
                    return False
                fl_name = fl_name_manually

        # Torrent File Naming
        # Note: Don't Edit .torrent filename after creation, SubsPlease anime releases (because of their weird naming) are an exception
        torrent_file_name = str(fl_name) if meta.anime is True and meta.tag == "-SubsPlease" else meta.basename_no_ext

        # Download new .torrent from site
        desc_path = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/[{self.tracker}]DESCRIPTION.txt"
        async with aiofiles.open(desc_path, newline="", encoding="utf-8") as desc_file:
            fl_desc = await desc_file.read()
        torrent_path = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/[{self.tracker}].torrent"
        mi_path = (
            f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/BD_SUMMARY_00.txt" if meta.bdinfo else f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/MEDIAINFO_CLEANPATH.txt"
        )
        async with aiofiles.open(mi_path, encoding="utf-8") as mi_file:
            mi_dump = await mi_file.read()
        async with aiofiles.open(torrent_path, "rb") as torrent_file:
            torrent_bytes = await torrent_file.read()
        torrent_file_name = unidecode(torrent_file_name)
        files = {"file": (f"{torrent_file_name}.torrent", torrent_bytes, "application/x-bittorent")}
        data = {"name": fl_name, "type": cat_id, "descr": fl_desc.strip(), "nfo": mi_dump}

        imdb_id_value = str(meta.imdb_id if meta.imdb_id is not None else "0")
        if imdb_id_value.isdigit() and int(imdb_id_value) != 0:
            data["imdbid"] = meta.imdb
            imdb_info = meta.imdb_info
            imdb_info_dict = imdb_info if isinstance(imdb_info, dict) else {}
            data["description"] = imdb_info_dict.get("genres", "")
        if self.uploader_name not in ("", None) and not self._is_true(self.config["TRACKERS"][self.tracker].get("anon", "False")):
            data["epenis"] = self.uploader_name
        if has_ro_audio:
            data["materialro"] = "on"
        if meta.is_disc == "BDMV" or meta.type == "REMUX":
            data["freeleech"] = "on"
        if int(meta.tv_pack if meta.tv_pack is not None else "0") != 0:
            data["freeleech"] = "on"
        if int(meta.freeleech if meta.freeleech is not None else "0") != 0:
            data["freeleech"] = "on"

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
        cookies = self._load_cookie_dict(cookiefile)
        async with httpx.AsyncClient(cookies=cookies, timeout=60.0, follow_redirects=True) as client:
            up = await client.post(url=url, data=data, files=files)

        # Match url to verify successful upload
        match = re.match(rf".*?{re.escape(self.base_url.replace('https://', ''))}/details\.php\?id=(\d+)&uploaded=(\d+)", str(up.url))
        if match:
            meta.tracker_status[self.tracker]["status_message"] = match.group(0)
            torrent_id = match.group(1)
            await self.download_new_torrent(cookies, torrent_id, torrent_path)
            return True
        logger.info(data)
        logger.info(f"{self.tracker}: \n\n")
        logger.info(up.text)
        raise UploadError(f"Upload to FILELIST Failed: result URL {up.url} ({up.status_code}) was not expected", "red")  # noqa F405

    async def search_existing(self, meta: Meta) -> list[str]:
        dupes: list[str] = []
        from src.cookie_auth import find_cookie_file

        cookiefile = find_cookie_file(meta.base_dir, self.tracker, self.config)
        cookies = self._load_cookie_dict(cookiefile)

        search_url = f"{self.base_url}/browse.php"

        imdb_id_value = str(meta.imdb_id if meta.imdb_id is not None else "0")
        if imdb_id_value.isdigit() and int(imdb_id_value) != 0:
            params = {"search": meta.imdb, "cat": await self.get_category_id(meta), "searchin": "3"}
        else:
            params = {"search": meta.title, "cat": await self.get_category_id(meta), "searchin": "0"}

        async with httpx.AsyncClient(cookies=cookies, timeout=10.0) as client:
            response = await client.get(search_url, params=params)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            find = soup.find_all("a", href=True)
            for each in find:
                href_attr = each.get("href")
                title_attr = each.get("title")
                if isinstance(href_attr, str) and href_attr.startswith("details.php?id=") and "&" not in href_attr and isinstance(title_attr, str):
                    dupes.append(title_attr)
            await asyncio.sleep(0.5)

        return dupes

    async def validate_credentials(self, meta: Meta) -> bool:
        from src.cookie_auth import find_cookie_file

        cookiefile = find_cookie_file(meta.base_dir, self.tracker, self.config)

        if not Path(cookiefile).exists():
            await self.login(cookiefile)
        vcookie = await self.validate_cookies(meta, cookiefile)
        if vcookie is not True:
            logger.error(f"{self.tracker}: [red]Failed to validate cookies. Please confirm that the site is up and your passkey is valid.")
            if not meta.unattended or (meta.unattended and meta.unattended_confirm):
                recreate = await prompt_in_thread(cli_ui.ask_yes_no, "Log in again and create new session?")
                if recreate is True:
                    if Path(cookiefile).exists():
                        Path(cookiefile).unlink()
                    await self.login(cookiefile)
                    return await self.validate_cookies(meta, cookiefile)
            return False
        return True

    async def validate_cookies(self, meta: Meta, _cookiefile: str) -> bool:
        url = f"{self.base_url}/index.php"
        from src.cookie_auth import find_cookie_file

        cookiefile = find_cookie_file(meta.base_dir, self.tracker, self.config)
        cookies = self._load_cookie_dict(cookiefile)
        if cookies:
            async with httpx.AsyncClient(cookies=cookies, timeout=30.0) as client:
                resp = await client.get(url=url)
            logger.debug(resp.url)
            return resp.text.find("Logout") != -1
        return False

    async def login(self, cookiefile: str) -> None:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            r = await client.get(f"{self.base_url}/login.php")
            await asyncio.sleep(0.5)
            soup = BeautifulSoup(r.text, "html.parser")
            validator_input = soup.find("input", {"name": "validator"})
            if validator_input is None:
                raise LoginError("Unable to locate validator input on FILELIST login page.")  # noqa: F405
            validator_value = validator_input.get("value")
            if not isinstance(validator_value, str):
                raise LoginError("Validator input missing value attribute on FILELIST login page.")  # noqa: F405
            validator = validator_value
            data = {
                "validator": validator,
                "username": self.username,
                "password": self.password,
                "unlock": "1",
            }
            await client.post(f"{self.base_url}/takelogin.php", data=data)
            index = f"{self.base_url}/index.php"
            response = await client.get(index)
            if response.text.find("Logout") != -1:
                logger.info(f"{self.tracker}: [green]Successfully logged into {self.tracker}")
                self.cookie_validator._save_cookies_secure(client.cookies.jar, cookiefile)  # pyright: ignore[reportPrivateUsage]
            else:
                logger.info(f"{self.tracker}: [bold red]Something went wrong while trying to log into {self.tracker}")
                logger.info(response.url)
        return

    async def download_new_torrent(self, cookies: dict[str, str], id: str, torrent_path: str) -> None:
        download_url = f"{self.base_url}/download.php?id={id}"
        async with httpx.AsyncClient(cookies=cookies, timeout=30.0) as client:
            r = await client.get(url=download_url)
        if r.status_code == 200:
            async with aiofiles.open(torrent_path, "wb") as tor:
                await tor.write(r.content)
        else:
            logger.info(f"{self.tracker}: [red]There was an issue downloading the new .torrent from {self.tracker}")
            logger.info(r.text)
        return

    async def edit_desc(self, meta: Meta) -> None:
        base = get_base_description(meta)
        async with aiofiles.open(f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/[{self.tracker}]DESCRIPTION.txt", "w", newline="", encoding="utf-8") as descfile:
            from src.bbcode import BBCODE

            bbcode = BBCODE()

            desc = base
            desc = bbcode.remove_spoiler(desc)
            desc = bbcode.convert_code_to_quote(desc)
            desc = bbcode.convert_comparison_to_centered(desc, 900)
            desc = desc.replace("[img]", "[img]").replace("[/img]", "[/img]")
            desc = re.sub(r"(\[img=\d+)]", "[img]", desc, flags=re.IGNORECASE)
            if meta.is_disc != "BDMV":
                url = "https://up.img4k.net/api/description"
                mediainfo_path = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/MEDIAINFO_CLEANPATH.txt"
                async with aiofiles.open(mediainfo_path, encoding="utf-8") as mi_file:
                    data = {
                        "mediainfo": await mi_file.read(),
                    }
                if meta.imdb_id:
                    data["imdbURL"] = f"tt{meta.imdb_id}"
                screen_dir = screenshots_dir(meta.base_dir, meta.uuid)
                screen_glob = [f.name for f in screen_dir.glob(f"{glob.escape(meta.filename)}-*.png")]
                files: list[tuple[str, tuple[str, bytes, str]]] = []
                for screen in screen_glob:
                    async with aiofiles.open(screen_dir / screen, "rb") as image_file:
                        image_bytes = await image_file.read()
                    files.append(("images", (Path(screen).name, image_bytes, "image/png")))
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(url, data=data, files=files, auth=(self.fltools["user"], self.fltools["pass"]))
                final_desc = response.text.replace("\r\n", "\n")
            else:
                # BD Description Generator
                bd_summary_path = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/BD_SUMMARY_EXT.txt"
                async with aiofiles.open(bd_summary_path, encoding="utf-8") as bd_file:
                    final_desc = await bd_file.read()
                if final_desc.strip() != "":  # Use BD_SUMMARY_EXT and bbcode format it
                    final_desc = final_desc.replace("[/pre][/quote]", f"[/pre][/quote]\n\n{desc}\n", 1)
                    final_desc = (
                        final_desc.replace("DISC INFO:", "[pre][quote=BD_Info][b][color=#FF0000]DISC INFO:[/color][/b]")
                        .replace("PLAYLIST REPORT:", "[b][color=#FF0000]PLAYLIST REPORT:[/color][/b]")
                        .replace("VIDEO:", "[b][color=#FF0000]VIDEO:[/color][/b]")
                        .replace("AUDIO:", "[b][color=#FF0000]AUDIO:[/color][/b]")
                        .replace("SUBTITLES:", "[b][color=#FF0000]SUBTITLES:[/color][/b]")
                    )
                    final_desc += "[/pre][/quote]\n"  # Closed bbcode tags
                    # Upload screens and append to the end of the description
                    url = "https://up.img4k.net/api/description"
                    screen_dir = screenshots_dir(meta.base_dir, meta.uuid)
                    screen_glob = [f.name for f in screen_dir.glob(f"{glob.escape(meta.filename)}-*.png")]
                    files: list[tuple[str, tuple[str, bytes, str]]] = []
                    for screen in screen_glob:
                        async with aiofiles.open(screen_dir / screen, "rb") as image_file:
                            image_bytes = await image_file.read()
                        files.append(("images", (Path(screen).name, image_bytes, "image/png")))
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        response = await client.post(url, files=files, auth=(self.fltools["user"], self.fltools["pass"]))
                    final_desc += response.text.replace("\r\n", "\n")
            await descfile.write(final_desc)

            if self.signature is not None:
                await descfile.write(self.signature)

    async def get_ro_tracks(self, meta: Meta) -> tuple[bool, bool]:
        has_ro_audio = has_ro_sub = False
        if meta.is_disc != "BDMV":
            mi = meta.mediainfo
            if isinstance(mi, dict):
                mi_dict = mi
                media = mi_dict.get("media")
                if isinstance(media, dict):
                    media_dict = cast(dict[str, Any], media)
                    tracks = media_dict.get("track")
                    if isinstance(tracks, list):
                        tracks_list = tracks
                        for track in tracks_list:
                            if not isinstance(track, dict):
                                continue
                            track_dict = cast(dict[str, Any], track)
                            if track_dict.get("@type") == "Text" and track_dict.get("Language") == "ro":
                                has_ro_sub = True
                            if track_dict.get("@type") == "Audio" and track_dict.get("Audio") == "ro":
                                has_ro_audio = True
        else:
            bdinfo = meta.bdinfo
            if isinstance(bdinfo, dict):
                bdinfo_dict = bdinfo
                subtitles = bdinfo_dict.get("subtitles")
                if isinstance(subtitles, list) and "Romanian" in subtitles:
                    has_ro_sub = True
                audio_tracks = bdinfo_dict.get("audio")
                if isinstance(audio_tracks, list):
                    audio_tracks_list = audio_tracks
                    for audio_track in audio_tracks_list:
                        if isinstance(audio_track, dict):
                            audio_track_dict = cast(dict[str, Any], audio_track)
                        else:
                            continue
                        if audio_track_dict.get("language") == "Romanian":
                            has_ro_audio = True
                            break
        return has_ro_audio, has_ro_sub
