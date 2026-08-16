# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import re
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlparse

import aiofiles
import httpx
from bs4 import BeautifulSoup

from src.console import logger
from src.cookie_auth import CookieAuthUploader, CookieValidator
from src.get_desc import DescriptionBuilder
from src.meta import Meta

Config = dict[str, Any]


class HDTorrents:
    """
    HD-Torrents (HDT) is a Private Torrent Tracker for HD MOVIES / TV / MUSIC / 3X
    """

    auth_type = "cookies"
    tracker = "HDTORRENTS"
    display_name = "HDTorrents"
    allows_bloated_audio = True
    source_flag = "hd-torrents.org"
    auth_token: str | None = None
    banned_groups = ()
    base_url = "https://hd-torrents.org"
    supported_categories = ("TV", "MOVIE")
    tracker_urls = ("https://hdts-announce.ru",)
    secret_token: str = ""

    def __init__(self, config: Config) -> None:
        self.config: Config = config
        self.cookie_validator = CookieValidator(config)
        self.cookie_auth_uploader = CookieAuthUploader(config)

        tracker_config = self.config.get("TRACKERS", {}).get(self.tracker, {})
        tracker_config_dict = cast(dict[str, Any], tracker_config) if isinstance(tracker_config, dict) else {}
        url_from_config = str(tracker_config_dict.get("url", "")).strip()
        parsed_url = urlparse(url_from_config)
        self.config_url = parsed_url.netloc or parsed_url.path.strip("/")
        self.base_url = f"https://{self.config_url}" if self.config_url else type(self).base_url

        self.torrent_url = f"{self.base_url}/details.php?id="
        self.announce_url = str(tracker_config_dict.get("announce_url", ""))
        self.session = httpx.AsyncClient(
            # HD-Torrents is very strict about User-Agent, so we use a common browser UA to avoid being blocked
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"},
            timeout=60.0,
        )

    async def validate_credentials(self, meta: Meta) -> bool:
        cookie_jar = await self.cookie_validator.load_session_cookies(meta, self.tracker)
        if not cookie_jar:
            return False

        configured_host = (urlparse(self.base_url).hostname or self.config_url).lower().lstrip(".")
        cookie_hosts = {str(cookie.domain).lower().lstrip(".") for cookie in cookie_jar if cookie.domain}
        if configured_host not in cookie_hosts:
            logger.error(f"{self.tracker}: Cookie domain does not match the configured base URL ({configured_host}). Please export cookies from {self.base_url}.")
            return False

        self.session.cookies = cookie_jar
        return True

    async def get_category_id(self, meta: Meta) -> int:
        cat_id = 0
        category = str(meta.category)
        resolution = meta.resolution
        if category == "MOVIE":
            # BDMV
            if meta.is_disc == "BDMV" or meta.type == "DISC":
                if resolution == "2160p":
                    # 70 = Movie/UHD/Blu-Ray
                    cat_id = 70
                if resolution in ("1080p", "1080i"):
                    # 1 = Movie/Blu-Ray
                    cat_id = 1

            # REMUX
            if meta.type == "REMUX":
                cat_id = 71 if meta.uhd == "UHD" and meta.resolution == "2160p" else 2

            # REST OF THE STUFF
            if meta.type not in ("DISC", "REMUX"):
                if resolution == "2160p":
                    # 64 = Movie/2160p
                    cat_id = 64
                elif resolution in ("1080p", "1080i"):
                    # 5 = Movie/1080p/i
                    cat_id = 5
                elif resolution == "720p":
                    # 3 = Movie/720p
                    cat_id = 3

        if category == "TV":
            # BDMV
            if meta.is_disc == "BDMV" or meta.type == "DISC":
                if resolution == "2160p":
                    # 72 = TV Show/UHD/Blu-ray
                    cat_id = 72
                if resolution in ("1080p", "1080i"):
                    # 59 = TV Show/Blu-ray
                    cat_id = 59

            # REMUX
            if meta.type == "REMUX":
                cat_id = 73 if meta.uhd == "UHD" and meta.resolution == "2160p" else 60

            # REST OF THE STUFF
            if meta.type not in ("DISC", "REMUX"):
                if resolution == "2160p":
                    # 65 = TV Show/2160p
                    cat_id = 65
                elif resolution in ("1080p", "1080i"):
                    # 30 = TV Show/1080p/i
                    cat_id = 30
                elif resolution == "720p":
                    # 38 = TV Show/720p
                    cat_id = 38

        return cat_id

    async def get_name(self, meta: Meta) -> str:
        hdt_name = meta.name
        audio = meta.audio
        hdr = meta.hdr
        if meta.type in ("WEBDL", "WEBRIP", "ENCODE"):
            hdt_name = hdt_name.replace(audio, audio.replace(" ", "", 1))
        if "DV" in hdr:
            hdt_name = hdt_name.replace(" DV ", " DoVi ")
        if "BluRay REMUX" in hdt_name:
            hdt_name = hdt_name.replace("BluRay REMUX", "Blu-ray Remux")

        hdt_name = " ".join(hdt_name.split())
        hdt_name = re.sub(r"[^0-9a-zA-ZÀ-ÿ. &+'\-\[\]]+", "", hdt_name)
        return hdt_name.replace(":", "").replace("..", " ").replace("  ", " ")

    async def edit_desc(self, meta: Meta) -> str:
        builder = DescriptionBuilder(self.tracker, self.config)
        return await builder.general_description_generator(
            meta,
            book=False,
            game=False,
            nfo=False,
            signature=f"[right][url=https://github.com/wastaken7/Upload-Assistant][size=1]{meta.ua_signature}[/size][/url][/right]",
        )

    async def get_additional_checks(self, meta: Meta) -> bool:
        if meta.resolution not in ["2160p", "1080p", "1080i", "720p"]:
            logger.info(f"{self.tracker}: The resolution must be at least 720p, skipping the upload...")
            return False
        return True

    async def search_existing(self, meta: Meta) -> list[dict[str, str | None]]:
        cookie_jar = await self.cookie_validator.load_session_cookies(meta, self.tracker)
        if cookie_jar:
            self.session.cookies = cookie_jar

        results: list[dict[str, str | None]] = []

        search_url = f"{self.base_url}/torrents.php?"
        if meta.imdb_id or 0 != 0:
            params: dict[str, str | int] = {
                "csrfToken": self.secret_token,
                "search": meta.imdb_tt,
                "active": "0",
                "options": "2",
                "category[]": await self.get_category_id(meta),
            }
        else:
            params = {"csrfToken": self.secret_token, "search": meta.title, "category[]": await self.get_category_id(meta), "options": "3"}

        response = await self.session.get(search_url, params=params, follow_redirects=True)
        response.raise_for_status()

        if "login.php" in str(response.url) or "login.php" in response.text:
            await self.cookie_validator.handle_validation_failure(meta, self.tracker, response.text)
            meta.skipping = f"{self.tracker}"
            return results

        token_match = re.search(r'name="csrfToken" value="([^"]+)"', response.text)
        if token_match:
            HDTorrents.secret_token = token_match.group(1)
        else:
            logger.info(f"{self.tracker}: [bold red]Failed to find auth token on page.[/bold red]")
            meta.skipping = f"{self.tracker}"
            return results

        soup = BeautifulSoup(response.text, "html.parser")
        rows = soup.find_all("tr")

        for row in rows:
            if row.find(string="Filename", attrs={"class": "mainblockcontent"}) is not None:  # type: ignore
                continue

            name_tag = row.find("a", attrs={"href": re.compile(r"details\.php\?id=")})

            name = name_tag.text.strip() if name_tag else None
            link = f"{self.base_url}/{name_tag['href']}" if name_tag else None
            size = None

            cells = row.find_all("td", class_="mainblockcontent")
            for cell in cells:
                cell_text = cell.text.strip()
                if "GiB" in cell_text or "MiB" in cell_text:
                    size = cell_text
                    break

            if name:
                results.append({"name": name, "size": size, "link": link})

        return results

    async def get_data(self, meta: Meta) -> dict[str, Any]:
        data: dict[str, Any] = {
            "filename": await self.get_name(meta),
            "category": await self.get_category_id(meta),
            "info": await self.edit_desc(meta),
            "csrfToken": self.secret_token,
        }

        # 3D
        if "3D" in meta.three_d:
            data["3d"] = "true"

        # HDR
        hdr_value = meta.hdr
        if "HDR" in hdr_value:
            if "HDR10+" in hdr_value:
                data["HDR10"] = "true"
                data["HDR10Plus"] = "true"
            else:
                data["HDR10"] = "true"
        if "DV" in hdr_value:
            data["DolbyVision"] = "true"

        # IMDB
        if meta.imdb_id or 0 != 0:
            data["infosite"] = f"{meta.imdb_info.get('imdb_url', '')}/"

        # Full Season Pack
        if int((meta.tv_pack if meta.tv_pack is not None else "0") or 0) != 0:
            data["season"] = "true"
        else:
            data["season"] = "false"

        # Anonymous check
        if int(meta.anon or 0) == 0 and not self.config["TRACKERS"][self.tracker].get("anon", False):
            data["anonymous"] = "false"
        else:
            data["anonymous"] = "true"

        return data

    async def get_nfo(self, meta: Meta) -> dict[str, tuple[str, bytes, str]]:
        nfo_dir = Path(meta.base_dir) / "tmp" / meta.uuid
        nfo_files = list(nfo_dir.glob("*.nfo"))

        if nfo_files:
            nfo_path = nfo_files[0]
            async with aiofiles.open(nfo_path, "rb") as nfo_file:
                nfo_bytes = await nfo_file.read()
            return {"nfos": (nfo_path.name, nfo_bytes, "application/octet-stream")}
        return {}

    async def upload(self, meta: Meta) -> bool:
        cookie_jar = await self.cookie_validator.load_session_cookies(meta, self.tracker)
        if cookie_jar:
            self.session.cookies = cookie_jar

        data = await self.get_data(meta)
        files = await self.get_nfo(meta)

        return await self.cookie_auth_uploader.handle_upload(
            meta=meta,
            tracker=self.tracker,
            source_flag=self.source_flag,
            torrent_url=self.torrent_url,
            data=data,
            torrent_field_name="torrent",
            upload_cookies=self.session.cookies,
            upload_url=f"{self.base_url}/upload.php",
            hash_is_id=True,
            success_text="Upload successful!",
            default_announce="https://hdts-announce.ru/announce.php",
            additional_files=files,
        )
