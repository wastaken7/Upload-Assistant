# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import platform
from typing import Any, Optional, cast

import httpx
from bs4 import BeautifulSoup

from src.console import console
from src.cookie_auth import CookieAuthUploader, CookieValidator
from src.get_desc import DescriptionBuilder
from src.meta import Meta
from src.trackers.COMMON import COMMON

Config = dict[str, Any]


class PTS:
    supported_categories = ("TV", "MOVIE")
    tracker_urls = ['https://tracker.ptskit.com']
    def __init__(self, config: Config) -> None:
        self.config: Config = config
        self.common = COMMON(config)
        self.cookie_validator = CookieValidator(config)
        self.cookie_auth_uploader = CookieAuthUploader(config)
        self.tracker = "PTS"
        self.banned_groups = []
        self.source_flag = "[www.ptskit.org] PTSKIT"
        self.base_url = "https://www.ptskit.org"
        self.torrent_url = "https://www.ptskit.org/details.php?id="
        self.announce = str(self.config['TRACKERS'][self.tracker]['announce_url'])
        self.auth_token: Optional[str] = None
        self.session = httpx.AsyncClient(headers={"User-Agent": f"Upload-Assistant/2.3 ({platform.system()} {platform.release()})"}, timeout=60.0)

    async def validate_credentials(self, meta: Meta) -> bool:
        cookies = await self.cookie_validator.load_session_cookies(meta, self.tracker)
        self.session.cookies = cast(Any, cookies)
        return cookies is not None

    async def get_type(self, meta: Meta) -> Optional[str]:
        if meta.anime:
            return '407'

        category_map = {
            'TV': '405',
            'MOVIE': '404'
        }

        return category_map.get(meta.category)

    async def generate_description(self, meta: Meta) -> str:
        builder = DescriptionBuilder(self.tracker, self.config)
        desc = await builder.general_description_generator(
            meta,
            audio_spectrogram=True,
            bluray=True,
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
            signature=f"[right][url=https://github.com/wastaken7/Upload-Assistant][size=1]{meta.ua_signature}[/size][/url][/right]",
        )

        return desc

    async def search_existing(self, meta: Meta) -> Optional[list[str]]:
        mandarin = await self.common.check_language_requirements(
            meta, self.tracker, languages_to_check=['mandarin', 'chinese'], check_audio=True, check_subtitle=True
        )

        if not mandarin:
            user_input = input("Warning: Mandarin subtitle or audio not found. Do you want to continue with the upload anyway? (y/n): ")
            if user_input.lower() not in ['y', 'yes']:
                console.print("Upload cancelled by user.", markup=False)
                meta.skipping = f"{self.tracker}"
                return

        search_url = f"{self.base_url}/torrents.php"
        params: dict[str, Any] = {"incldead": 1, "search": str(meta.imdb_info.get("imdbID", "")), "search_area": 4}
        found_items: list[str] = []

        try:
            response = await self.session.get(search_url, params=params, cookies=self.session.cookies)
            if "login.php" in str(response.url) or "login.php" in response.text:
                await self.cookie_validator.handle_validation_failure(meta, self.tracker, response.text)
                meta.skipping = f"{self.tracker}"
                return found_items
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')

            torrents_table = soup.find('table', class_='torrents')

            if torrents_table:
                torrent_name_tables = torrents_table.find_all('table', class_='torrentname')

                for torrent_table in torrent_name_tables:
                    name_tag = torrent_table.find('b')
                    if name_tag:
                        torrent_name = name_tag.get_text(strip=True)
                        found_items.append(torrent_name)

        except Exception as e:
            console.print(f"An error occurred while searching: {e}", markup=False)

        return found_items

    async def get_data(self, meta: Meta) -> dict[str, Any]:
        data: dict[str, Any] = {
            "name": meta.name,
            "url": str(meta.imdb_info.get("imdb_url", "")),
            "descr": await self.generate_description(meta),
            "type": await self.get_type(meta),
        }

        return data

    async def upload(self, meta: Meta) -> bool:
        cookies = await self.cookie_validator.load_session_cookies(meta, self.tracker)
        self.session.cookies = cast(Any, cookies)
        data = await self.get_data(meta)

        is_uploaded = await self.cookie_auth_uploader.handle_upload(
            meta=meta,
            tracker=self.tracker,
            source_flag=self.source_flag,
            torrent_url=self.torrent_url,
            data=data,
            torrent_field_name='file',
            upload_cookies=self.session.cookies,
            upload_url=f"{self.base_url}/takeupload.php",
            id_pattern=r'download\.php\?id=([^&]+)',
            success_status_code="302, 303",
        )

        return is_uploaded
