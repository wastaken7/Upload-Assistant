# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import asyncio
import platform
from typing import Any, ClassVar

import aiofiles
import httpx
from bs4 import BeautifulSoup

from src.console import logger
from src.cookie_auth import CookieAuthUploader, CookieValidator
from src.get_desc import DescriptionBuilder
from src.meta import Meta
from src.tmdb import TmdbManager
from src.trackers.common import Common

Config = dict[str, Any]


class NEXUSPHP:
    auth_type = "cookies"
    supported_categories: tuple[str, ...] = ("TV", "MOVIE")
    tracker: str = ""
    source_flag: str = ""
    banned_groups: tuple[str, ...] = ()
    base_url: str = ""
    search_url: str = ""
    torrent_url: str = ""
    upload_url: str = ""
    tmdb_localization_requirements: ClassVar = {
        "zh-cn": {
            "main": "credits",
        }
    }

    def __init__(self, config: dict[str, Any], tracker_name: str):
        self.common = Common(config)
        self.config = config
        self.cookie_auth_uploader = CookieAuthUploader(config)
        self.cookie_validator = CookieValidator(config)
        self.tmdb_manager = TmdbManager(config)
        self.tracker = tracker_name
        self.tracker_config: dict[str, Any] = self.config["TRACKERS"].get(self.tracker, {})

        # Normalize announce_url: must be a non-empty string after stripping
        raw_announce = self.tracker_config.get("announce_url")
        self.announce_url = raw_announce.strip() if isinstance(raw_announce, str) else ""

        self.session = httpx.AsyncClient(headers={"User-Agent": f"Upload-Assistant ({platform.system()} {platform.release()})"}, timeout=60.0)

    async def load_localized_data(self, meta: Meta) -> None:
        data = meta.tmdb_localized_data
        zh_cn_data = data.get("zh-cn")
        if not zh_cn_data or not zh_cn_data.get("main"):
            raise RuntimeError(f"{self.tracker}: Missing TMDB localized data (zh-cn).")

        self.tmdb_data = zh_cn_data.get("main") or {}
        return

    async def search_existing(self, meta: Meta) -> list[dict[str, str]]:
        if not self.announce_url:
            logger.info(f"{self.tracker}: [red]Announce URL is not set for {self.tracker}[/red]", extra={"markup": True})
            meta.skipping = self.tracker
            return []

        base_url = f"{self.base_url}/torrents.php"
        params = {
            f"cat{self.get_category(meta)}": "1",
            f"medium{self.get_type(meta)}": "1",
            f"standard{self.get_resolution(meta)}": "1",
            "incldead": "0",
        }

        search_name = meta.title
        year = str(meta.year) if meta.year is not None else ""
        episode = meta.episode
        season = str(meta.season)
        season_episode = f"{season}{episode}" if season or episode else ""

        if meta.category == "MOVIE":
            params["search"] = f"{search_name} {year}"
        else:
            if meta.tv_pack:
                params["search"] = f"{search_name} {season}"
            else:
                params["search"] = f"{search_name} {season_episode}"

        cookies = await self.cookie_validator.load_session_cookies(meta, self.tracker)
        if cookies:
            self.session.cookies.update(cookies)

        response = await self.session.get(base_url, params=params)
        if "login.php" in str(response.url) or "login.php" in response.text:
            await self.cookie_validator.handle_validation_failure(meta, self.tracker, response.text)
            meta.skipping = self.tracker
            return []
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        table = soup.find("table", class_="torrents")
        if not table:
            return []

        rows = table.find_all("tr")[1:]  # Skip header row
        results = []
        for row in rows:
            name_link = row.find("table", class_="torrentname")
            if not name_link:
                continue

            a_tag = name_link.find("a", href=lambda x: bool(x and "details.php?id=" in x))
            if a_tag:
                name_val = a_tag.get("title")
                name = " ".join(name_val) if isinstance(name_val, list) else name_val or a_tag.get_text(strip=True)

                href = a_tag.get("href")
                if isinstance(href, list):
                    href = href[0]

                if isinstance(href, str):
                    torrent_id = href.split("id=")[1].split("&")[0]
                    link = f"{self.base_url}/details.php?id={torrent_id}"
                    base_entry = {"name": name, "link": link}

                    if meta.is_disc == "BDMV":
                        bdinfo = await self.get_dupe_bdinfo(torrent_id)
                        if bdinfo:
                            base_entry["bd_info"] = bdinfo

                    results.append(base_entry)

        return results

    async def get_dupe_bdinfo(self, torrent_id: str) -> str:
        try:
            bdinfo_url = f"{self.base_url}/details.php?id={torrent_id}"
            response = await self.session.get(bdinfo_url)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")
            bdinfo_div = soup.find("div", class_="nexus-media-info-raw")
            if bdinfo_div:
                pre_tag = bdinfo_div.find("pre")
                if pre_tag:
                    return pre_tag.get_text(strip=True)

            return ""

        except Exception as e:
            logger.info(f"{self.tracker}: Error getting BDInfo for torrent {torrent_id}: {e}", extra={"markup": False})
            return ""

    async def validate_credentials(self, meta: Meta) -> bool:
        cookies = await self.cookie_validator.load_session_cookies(meta, self.tracker)
        if cookies:
            self.session.cookies.update(cookies)
            return True
        return False

    async def standard_desc(self, meta: Meta) -> str:
        data = getattr(self, "tmdb_data", {})
        if not data:
            return ""

        desc_parts: list[str] = []

        # Cover
        poster_path = data.get("poster_path")
        if poster_path:
            desc_parts.append(f"[img]https://image.tmdb.org/t/p/w500{poster_path}[/img]")
            desc_parts.append("")

        name = data.get("name", "")
        original_name = data.get("original_name", "")

        # Season info for TV
        season_num = meta.season
        is_tv = meta.category == "TV"

        if is_tv and season_num:
            season_info = next((s for s in data.get("seasons", []) if s.get("season_number") == season_num), {})
            season_name = season_info.get("name", "")
            if not season_name or season_name == f"第 {season_num} 季":
                if f"第 {season_num} 季" not in name:
                    name = f"{name} 第 {season_num} 季"
            else:
                if season_name not in name:
                    name = f"{name} {season_name}"

        desc_parts.append(f"◎片　　名　{name}")

        aka = []
        if original_name and original_name != name:
            aka.append(original_name)
        if aka:
            desc_parts.append(f"◎译　　名　{' / '.join(aka)}")

        release_date = data.get("first_air_date") or data.get("release_date", "")
        year = release_date[:4] if release_date else meta.year
        if year:
            desc_parts.append(f"◎年　　代　{year}")

        countries = [c.get("name") for c in data.get("production_countries", [])]
        if countries:
            desc_parts.append(f"◎产　　地　{' / '.join(countries)}")

        genres = [g.get("name") for g in data.get("genres", [])]
        if genres:
            desc_parts.append(f"◎类　　别　{' / '.join(genres)}")

        languages = [lang.get("name") for lang in data.get("spoken_languages", [])]
        if languages:
            desc_parts.append(f"◎语　　言　{' / '.join(languages)}")

        if release_date:
            country_name = countries[0] if countries else ""
            date_str = f"{release_date}({country_name})" if country_name else release_date
            desc_parts.append(f"◎上映日期　{date_str}")

        imdb_info = meta.imdb_info
        imdb_rating = imdb_info.get("rating")
        imdb_votes = imdb_info.get("votes")
        imdb_url = imdb_info.get("imdb_url")

        if imdb_rating:
            votes_str = f" ({imdb_votes} 人评价)" if imdb_votes else ""
            desc_parts.append(f"◎IMDb评分  {imdb_rating}/10{votes_str}")
        if imdb_url:
            desc_parts.append(f"◎IMDb链接  {imdb_url}/")

        # Douban info from meta if available
        douban_rating = meta.douban_rating
        douban_votes = meta.douban_votes
        douban_id = meta.douban_id
        if douban_rating:
            votes_str = f" ({douban_votes} 人评价)" if douban_votes else ""
            desc_parts.append(f"◎豆瓣评分　{douban_rating}/10{votes_str}")
        if douban_id:
            desc_parts.append(f"◎豆瓣链接　https://movie.douban.com/subject/{douban_id}/")

        if is_tv:
            if season_num:
                season_info = next((s for s in data.get("seasons", []) if s.get("season_number") == season_num), {})
                ep_count = season_info.get("episode_count")
                if ep_count:
                    desc_parts.append(f"◎集　　数　{ep_count}")

            desc_parts.append(f"◎季　　数　{season_num}")

            runtime = data.get("episode_run_time", [])
            if not runtime and data.get("last_episode_to_air"):
                runtime = [data["last_episode_to_air"].get("runtime")]
            if runtime and runtime[0]:
                desc_parts.append(f"◎片　　长　{runtime[0]}分钟")
        else:
            runtime = data.get("runtime") or meta.runtime
            if runtime:
                desc_parts.append(f"◎片　　长　{runtime}分钟")

        credits = data.get("credits", {})
        crew = credits.get("crew", [])

        directors = [f"{c.get('name')} {c.get('original_name')}" for c in crew if c.get("job") == "Director"]
        if directors:
            desc_parts.append(f"◎导　　演　{' / '.join(directors)}")

        writers = [f"{c.get('name')} {c.get('original_name')}" for c in crew if c.get("job") in ("Writer", "Screenplay", "Author")]
        writers = list(dict.fromkeys(writers))
        if writers:
            desc_parts.append(f"◎编　　剧　{' / '.join(writers)}")

        cast = credits.get("cast", [])
        if cast:
            first_actor = cast[0]
            actor_str = f"{first_actor.get('name')} {first_actor.get('original_name')}"
            if first_actor.get("character"):
                actor_str += f" (饰 {first_actor.get('character')})"
            desc_parts.append(f"◎主　　演　{actor_str}")

            for actor in cast[1:25]:
                actor_str = f"{actor.get('name')} {actor.get('original_name')}"
                if actor.get("character"):
                    actor_str += f" (饰 {actor.get('character')})"
                desc_parts.append(f"　　　　　　{actor_str}")

        overview = data.get("overview", "")
        if overview:
            desc_parts.append("")
            desc_parts.append("◎简　　介")
            desc_parts.append("")
            desc_parts.append(f"　　{overview}")

        return "\n".join(desc_parts)

    async def get_description(self, meta: Meta) -> dict[str, str]:
        builder = DescriptionBuilder(self.tracker, self.config)
        meta.nexusphp_description = await self.standard_desc(meta)

        description = await builder.general_description_generator(
            meta,
            logo=False,
            mediainfo=False,
            nfo=False,
            signature=f"[right][url=https://github.com/wastaken7/Upload-Assistant][size=1]{meta.ua_signature}[/size][/url][/right]",
        )
        return {"descr": description}

    def get_category(self, meta: Meta) -> int:
        meta = meta
        raise NotImplementedError

    def get_type(self, meta: Meta) -> int:
        meta = meta
        raise NotImplementedError

    def get_codec(self, meta: Meta) -> int:
        meta = meta
        raise NotImplementedError

    def get_resolution(self, meta: Meta) -> int:
        meta = meta
        raise NotImplementedError

    def get_group_tag(self, meta: Meta) -> int:
        meta = meta
        return 0

    def get_checkboxes(self, meta: Meta) -> list[str]:
        meta = meta
        return []

    def get_audio_codec(self, meta: Meta) -> int:
        meta = meta
        return 0

    def get_douban_url(self, meta: Meta) -> str:
        if meta.douban_id:
            return f"https://movie.douban.com/subject/{meta.douban_id}/"
        return ""

    def get_imdb_url(self, meta: Meta) -> str:
        if meta.imdb_id:
            return f"{meta.imdb_info.get('imdb_url', '')}"
        return ""

    def get_region(self, meta: Meta) -> int:
        meta = meta
        return 0

    def get_container(self, meta: Meta) -> int:
        meta = meta
        return 0

    async def get_technical_info(self, meta: Meta) -> dict[str, str]:
        file = "BD_SUMMARY_00" if meta.is_disc == "BDMV" else "MEDIAINFO_CLEANPATH"
        async with aiofiles.open(f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/{file}.txt", encoding="utf-8") as f:
            return {"technical_info": await f.read()}

    async def get_name(self, meta: Meta) -> dict[str, str]:
        return {"name": meta.name}

    async def get_category_data(self, meta: Meta) -> dict[str, int]:
        return {"type": self.get_category(meta)}

    async def get_type_data(self, meta: Meta) -> dict[str, int]:
        return {"medium_sel[4]": self.get_type(meta)}

    async def get_codec_data(self, meta: Meta) -> dict[str, int]:
        return {"codec_sel[4]": self.get_codec(meta)}

    async def get_resolution_data(self, meta: Meta) -> dict[str, int]:
        return {"standard_sel[4]": self.get_resolution(meta)}

    async def get_group_tag_data(self, meta: Meta) -> dict[str, int]:
        group_tag = self.get_group_tag(meta)
        return {"team_sel[4]": group_tag} if group_tag else {}

    async def get_checkboxes_data(self, meta: Meta) -> dict[str, list[str]]:
        checkboxes = self.get_checkboxes(meta)
        return {"tags[4][]": checkboxes} if checkboxes else {}

    async def get_anonymous_data(self, meta: Meta) -> dict[str, str]:
        anonymous = not (meta.anon == 0 and not self.tracker_config.get("anon", False))
        return {"uplver": "yes"} if anonymous else {}

    async def get_imdb_data(self, meta: Meta) -> dict[str, str]:
        imdb_url = self.get_imdb_url(meta)
        return {"url": imdb_url} if imdb_url else {}

    async def get_douban_data(self, meta: Meta) -> dict[str, str]:
        douban_url = self.get_douban_url(meta)
        return {"pt_gen": douban_url} if douban_url else {}

    async def get_audio_codec_data(self, meta: Meta) -> dict[str, int]:
        audio = self.get_audio_codec(meta)
        return {"audiocodec_sel[4]": audio} if audio else {}

    async def get_region_data(self, meta: Meta) -> dict[str, int]:
        region = self.get_region(meta)
        return {"source_sel[4]": region} if region else {}

    async def get_container_data(self, meta: Meta) -> dict[str, int]:
        container = self.get_container(meta)
        return {"processing_sel[4]": container} if container else {}

    async def get_data(self, meta: Meta) -> dict[str, Any]:
        await self.load_localized_data(meta)
        results = await asyncio.gather(
            self.get_name(meta),
            self.get_description(meta),
            self.get_technical_info(meta),
            self.get_category_data(meta),
            self.get_type_data(meta),
            self.get_codec_data(meta),
            self.get_resolution_data(meta),
            self.get_group_tag_data(meta),
            self.get_checkboxes_data(meta),
            self.get_anonymous_data(meta),
            self.get_imdb_data(meta),
            self.get_douban_data(meta),
            self.get_audio_codec_data(meta),
            self.get_region_data(meta),
            self.get_container_data(meta),
        )

        data: dict[str, Any] = {
            "color": 0,
            "font": 0,
            "size": 0,
            "small_descr": self.common.get_small_description(meta),
        }
        for result in results:
            data.update(result)
        return data

    async def upload(self, meta: Meta) -> bool:
        cookies = await self.cookie_validator.load_session_cookies(meta, self.tracker)
        self.session.cookies.clear()
        if cookies is not None:
            self.session.cookies.update(cookies)
        data = await self.get_data(meta)

        return await self.cookie_auth_uploader.handle_upload(
            meta=meta,
            tracker=self.tracker,
            source_flag=self.source_flag,
            torrent_url=self.torrent_url,
            id_pattern=r"download\.php\?id=(\d+)",
            data=data,
            torrent_field_name="file",
            upload_cookies=self.session.cookies,
            upload_url=f"{self.base_url}/takeupload.php",
            success_text="download.php?id=",
        )
