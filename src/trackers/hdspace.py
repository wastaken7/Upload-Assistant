# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import platform
import re
from pathlib import Path
from typing import Any

import aiofiles
import httpx
from bs4 import BeautifulSoup

from src.console import logger
from src.cookie_auth import CookieAuthUploader, CookieValidator
from src.get_desc import DescriptionBuilder
from src.meta import Meta

Config = dict[str, Any]


class HDSpace:
    """
    HD-Space (HDS) is a Private Torrent Tracker for HD MOVIES / TV
    """

    auth_type = "cookies"
    tracker = "HDSPACE"
    display_name = "HDSpace"
    allows_bloated_audio = True
    source_flag = "HD-Space"
    banned_groups = ("",)
    base_url = "https://hd-space.org"
    torrent_url = f"{base_url}/index.php?page=torrent-details&id="
    requests_url = f"{base_url}/index.php?page=viewrequests"
    supported_categories = ("TV", "MOVIE")
    tracker_urls = ("hd-space.pw",)

    def __init__(self, config: Config) -> None:
        self.config: Config = config
        self.cookie_validator = CookieValidator(config)
        self.cookie_auth_uploader = CookieAuthUploader(config)
        self.session = httpx.AsyncClient(headers={"User-Agent": f"Upload-Assistant/2.3 ({platform.system()} {platform.release()})"}, timeout=30)

    async def validate_credentials(self, meta: Meta) -> bool:
        cookies = await self.cookie_validator.load_session_cookies(meta, self.tracker)
        self.session.cookies.clear()
        if cookies is not None:
            self.session.cookies.update(cookies)
            return True
        return False

    async def generate_description(self, meta: Meta) -> str:
        try:
            builder = DescriptionBuilder(self.tracker, self.config)
            description = await builder.general_description_generator(
                meta,
                bluray=False,
                book=False,
                custom_signature=False,
                game=False,
                nfo=False,
                signature=f"[center][url=https://github.com/wastaken7/Upload-Assistant][size=2]{meta.ua_signature}[/size][/url][/center]",
            )
        except Exception as e:
            logger.info(f"{self.tracker}: Error generating description: {e}")
            description = ""

        return description

    async def get_additional_checks(self, meta: Meta) -> bool:
        if meta.resolution not in ["2160p", "1080p", "1080i", "720p"]:
            logger.info(f"{self.tracker}: The resolution must be at least 720p, skipping the upload...")
            return False
        return True

    async def search_existing(self, meta: Meta) -> list[dict[str, str | None]]:
        dupes: list[dict[str, str | None]] = []

        cookies = await self.cookie_validator.load_session_cookies(meta, self.tracker)
        self.session.cookies.clear()
        if cookies is not None:
            self.session.cookies.update(cookies)

        imdb_id = str(meta.imdb)
        if imdb_id == "0":
            logger.info(f"{self.tracker}: IMDb ID not found, cannot search for duplicates on {self.tracker}.")
            return dupes

        search_url = f"{self.base_url}/index.php"
        current_page = 0

        while True:
            params = {
                "page": "torrents",
                "search": imdb_id,
                "active": "0",
                "options": "2",
                "pages": str(current_page),
            }

            response = await self.session.get(search_url, params=params)
            if "Recover password" in response.text or "page=login" in str(response.url) or "page=login" in response.text:
                await self.cookie_validator.handle_validation_failure(meta, self.tracker, response.text)
                meta.skipping = f"{self.tracker}"
                return dupes
            response.raise_for_status()
            parts = response.text.split("Show/Hide Categories", 1)
            if len(parts) < 2:
                logger.info(f"{self.tracker}: [bold yellow]Unexpected page structure on page {current_page}, stopping search[/bold yellow]")
                break
            relevant_html = parts[1]
            soup = BeautifulSoup(relevant_html, "html.parser")
            rows = soup.select("tr:has(td.lista)")

            if not rows:
                break

            for row in rows:
                name_tag = row.select_one('a[href*="page=torrent-details"]')
                if not name_tag:
                    continue
                name = name_tag.get_text(strip=True)

                if not name and name_tag.has_attr("title"):
                    name = str(name_tag["title"])
                href_value = name_tag.get("href", "")
                link_path = str(href_value).lstrip("/")
                torrent_link = f"{self.base_url.rstrip('/')}/{link_path}"
                cells = row.find_all("td", class_="lista")
                size = None
                if len(cells) >= 5:
                    for cell in cells:
                        txt = cell.get_text(strip=True)
                        if re.search(r"([0-9.]+)\s+(GB|MB|KB|B)", txt, re.I):
                            size = txt
                            break

                if name and torrent_link:
                    dupes.append({"name": name, "size": size, "link": torrent_link})

            next_page = soup.find("a", href=re.compile(r"pages="), text=re.compile(r"Next|>>", re.I))

            if not next_page:
                next_page = soup.find("a", href=re.compile(rf"pages={current_page + 1}"))

            if next_page:
                current_page += 1
                # Prevents infinite loop
                if current_page > 10:
                    break
            else:
                break

        return dupes

    async def get_category_id(self, meta: Meta) -> int:
        resolution = meta.resolution
        category = str(meta.category)
        type_ = str(meta.type)
        is_disc = str(meta.is_disc)
        genres = [g.lower() for g in meta.genres]
        keywords = [k.lower() for k in meta.keywords]
        is_anime = meta.anime

        if is_disc == "BDMV":
            return 15  # Blu-Ray
        if type_ == "REMUX":
            return 40  # Remux

        category_map = {
            "MOVIE": {"2160p": 46, "1080p": 19, "1080i": 19, "720p": 18},
            "TV": {"2160p": 45, "1080p": 22, "1080i": 22, "720p": 21},
            "DOCUMENTARY": {"2160p": 47, "1080p": 25, "1080i": 25, "720p": 24},
            "ANIME": {"2160p": 48, "1080p": 28, "1080i": 28, "720p": 27},
        }

        if "documentary" in genres or "documentary" in keywords:
            return category_map["DOCUMENTARY"].get(resolution, 38)
        if is_anime:
            return category_map["ANIME"].get(resolution, 38)

        if category in category_map:
            return category_map[category].get(resolution, 38)

        return 38

    async def get_requests(self, meta: Meta) -> list[dict[str, str | None]] | bool:
        if not self.config["DEFAULT"].get("search_requests", False) and not meta.search_requests:
            return False
        try:
            cookies = await self.cookie_validator.load_session_cookies(meta, self.tracker)
            self.session.cookies.clear()
            if cookies is not None:
                self.session.cookies.update(cookies)
            query = meta.title
            search_url = f"{self.base_url}/index.php?"

            params: dict[str, str] = {"page": "viewrequests", "search": query, "filter": "true"}

            response = await self.session.get(search_url, params=params, cookies=self.session.cookies)
            response.raise_for_status()
            response_results_text = response.text

            soup = BeautifulSoup(response_results_text, "html.parser")
            request_rows = soup.select('form[action="index.php?page=takedelreq"] table.lista tr')

            results: list[dict[str, str | None]] = []
            for row in request_rows:
                if row.find("td", class_="header"):
                    continue

                name_element = row.select_one("td.lista a b")
                if not name_element:
                    continue

                name = name_element.text.strip()
                link_element = name_element.find_parent("a")
                raw_link = link_element.get("href") if link_element else None
                link = str(raw_link) if raw_link else None

                results.append(
                    {
                        "Name": name,
                        "Link": link,
                    }
                )

            if results:
                message = f"\n{self.tracker}: [bold yellow]Your upload may fulfill the following request(s), check it out:[/bold yellow]\n\n"
                for r in results:
                    message += f"[bold green]Name:[/bold green] {r['Name']}\n"
                    message += f"[bold green]Link:[/bold green] {self.base_url}/{r['Link']}\n\n"
                logger.info(message)

            return results

        except Exception as e:
            logger.info(f"{self.tracker}: An error occurred while fetching requests: {e}", extra={"markup": False})
            return []

    async def get_data(self, meta: Meta) -> dict[str, Any]:
        data: dict[str, Any] = {
            "category": await self.get_category_id(meta),
            "filename": await self.get_name(meta),
            "genre": ", ".join(meta.genres) if meta.genres else "",
            "imdb": str(meta.imdb),
            "info": await self.generate_description(meta),
            "nuk_rea": "",
            "nuk": "false",
            "req": "false",
            "submit": "Send",
            "t3d": "true" if "3D" in meta.three_d else "false",
            "user_id": "",
            "youtube_video": str(meta.youtube),
        }

        # Anon
        anon = not (int(meta.anon or 0) == 0 and not self.config["TRACKERS"][self.tracker].get("anon", False))
        if anon:
            data.update({"anonymous": "true"})
        else:
            data.update({"anonymous": "false"})

        return data

    async def get_nfo(self, meta: Meta) -> dict[str, tuple[str, bytes, str]]:
        nfo_dir = Path(meta.base_dir) / "tmp" / meta.uuid
        nfo_files = list(nfo_dir.glob("*.nfo"))

        if nfo_files:
            nfo_path = nfo_files[0]
            async with aiofiles.open(nfo_path, "rb") as nfo_file:
                nfo_bytes = await nfo_file.read()
            return {"nfo": (nfo_path.name, nfo_bytes, "application/octet-stream")}
        return {}

    async def upload(self, meta: Meta) -> bool:
        cookies = await self.cookie_validator.load_session_cookies(meta, self.tracker)
        self.session.cookies.clear()
        if cookies is not None:
            self.session.cookies.update(cookies)
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
            upload_url="https://hd-space.org/index.php?page=upload",
            hash_is_id=True,
            success_text="download.php?id=",
            additional_files=files,
        )

    async def get_name(self, meta: Meta) -> str:
        return meta.name
