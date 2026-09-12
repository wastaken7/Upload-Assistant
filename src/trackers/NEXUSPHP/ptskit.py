# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
from typing import Any, cast

from bs4 import BeautifulSoup

from src.get_desc import DescriptionBuilder
from src.meta import Meta
from src.trackers.NEXUSPHP import NEXUSPHP

Config = dict[str, Any]


class Ptskit(NEXUSPHP):
    """
    PTSKIT is a CHINESE Private Torrent Tracker for MOVIES / TV / GENERAL
    """

    auth_type = "cookies"
    tracker = "PTSKIT"
    display_name = "PTSKIT"
    allows_bloated_audio = True
    banned_groups = ()
    source_flag = "[www.ptskit.org] PTSKIT"
    base_url = "https://www.ptskit.org"
    auth_token: str | None = None
    torrent_url = "https://www.ptskit.org/details.php?id="
    supported_categories = ("TV", "MOVIE")
    tracker_urls = ("tracker.ptskit.com",)

    def __init__(self, config: Config) -> None:
        super().__init__(config, "PTSKIT")

    def get_type(self, meta: Meta) -> int:
        if meta.anime:
            return 407

        category_map = {"TV": "405", "MOVIE": "404"}

        return int(category_map.get(meta.category, "404"))

    async def generate_description(self, meta: Meta) -> str:
        builder = DescriptionBuilder(self.tracker, self.config)
        return await builder.general_description_generator(
            meta,
            book=False,
            game=False,
            nfo=False,
            signature=f"[right][url=https://github.com/wastaken7/Upload-Assistant][size=1]{meta.ua_signature}[/size][/url][/right]",
        )

    async def get_additional_checks(self, meta: Meta) -> bool:
        return await self.common.check_language_requirements(meta, self.tracker, languages_to_check=["mandarin", "chinese"], check_audio=True, check_subtitle=True)

    async def search_existing(self, meta: Meta) -> list[dict[str, str]]:
        search_url = f"{self.base_url}/torrents.php"
        params: dict[str, Any] = {"incldead": 1, "search": meta.imdb_tt, "search_area": 4}
        found_items: list[dict[str, str]] = []

        response = await self.session.get(search_url, params=params, cookies=self.session.cookies)
        if "login.php" in str(response.url) or "login.php" in response.text:
            await self.cookie_validator.handle_validation_failure(meta, self.tracker, response.text)
            meta.skipping = f"{self.tracker}"
            return found_items
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        torrents_table = soup.find("table", class_="torrents")

        if torrents_table:
            torrent_name_tables = torrents_table.find_all("table", class_="torrentname")

            for torrent_table in torrent_name_tables:
                name_tag = torrent_table.find("b")
                if name_tag:
                    torrent_name = name_tag.get_text(strip=True)
                    found_items.append({"name": torrent_name})

        return found_items

    async def get_data(self, meta: Meta) -> dict[str, Any]:
        data: dict[str, Any] = {
            "name": (await self.get_name(meta))["name"],
            "url": str(meta.imdb_info.get("imdb_url", "")),
            "descr": await self.generate_description(meta),
            "type": self.get_type(meta),
        }

        return data

    async def upload(self, meta: Meta) -> bool:
        cookies = await self.cookie_validator.load_session_cookies(meta, self.tracker)
        self.session.cookies = cast(Any, cookies)
        data = await self.get_data(meta)

        return await self.cookie_auth_uploader.handle_upload(
            meta=meta,
            tracker=self.tracker,
            source_flag=self.source_flag,
            torrent_url=self.torrent_url,
            data=data,
            torrent_field_name="file",
            upload_cookies=self.session.cookies,
            upload_url=f"{self.base_url}/takeupload.php",
            id_pattern=r"download\.php\?id=([^&]+)",
            success_status_code="302, 303",
        )

    async def get_name(self, meta: Meta) -> dict[str, str]:
        return {"name": meta.name}
