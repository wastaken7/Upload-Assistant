# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import platform
from pathlib import Path
from typing import Any

import aiofiles
import httpx
from bs4 import BeautifulSoup

from src.cookie_auth import CookieAuthUploader, CookieValidator
from src.get_desc import DescriptionBuilder
from src.meta import Meta

Config = dict[str, Any]


class ImmortalSeed:
    """
    IS Private Torrent Tracker
    """

    auth_type = "cookies"
    tracker = "IMMORTALSEED"
    display_name = "ImmortalSeed"
    allows_bloated_audio = True
    source_flag = "https://immortalseed.me"
    banned_groups = ("",)
    base_url = "https://immortalseed.me"
    torrent_url = "https://immortalseed.me/details.php?hash="
    supported_categories = ("TV", "MOVIE", "BOOK", "MUSIC", "GAME")
    tracker_urls = ("https://immortalseed.me",)

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
        builder = DescriptionBuilder(self.tracker, self.config)
        return await builder.general_description_generator(
            meta,
            logo=False,
            nfo=False,
            signature=f"\n{meta.ua_signature} (https://github.com/wastaken7/Upload-Assistant)",
        )

    async def search_existing(self, meta: Meta) -> list[dict[str, str | None]]:
        cookies = await self.cookie_validator.load_session_cookies(meta, self.tracker)
        self.session.cookies.clear()
        if cookies is not None:
            self.session.cookies.update(cookies)
        dupes: list[dict[str, str | None]] = []

        search_type = ""
        search_query = ""
        category = str(meta.category)

        if category == "MOVIE":
            search_type = "t_genre"
            search_query = str(meta.imdb_tt)

        elif category == "TV":
            search_type = "t_name"
            search_query = f"{meta.title} {meta.season}"
        elif category in ("BOOK", "GAME"):
            search_type = "t_name"
            search_query = meta.title
        elif category == "MUSIC":
            search_type = "t_name"
            search_query = f"{meta.artist} {meta.title}"
        else:
            return dupes

        search_url = f"{self.base_url}/browse.php?do=search&keywords={search_query}&search_type={search_type}"

        response = await self.session.get(search_url)
        if "Forget your password" in response.text or "login.php" in str(response.url) or "login.php" in response.text:
            await self.cookie_validator.handle_validation_failure(meta, self.tracker, response.text)
            meta.skipping = self.tracker
            return dupes
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        torrent_table = soup.find("table", id="sortabletable")

        if not torrent_table:
            return dupes

        torrent_rows = torrent_table.select("tbody > tr")[1:]

        for row in torrent_rows:
            name_tag = row.select_one('a[href*="details.php?id="]')
            if not name_tag:
                continue

            name = name_tag.get_text(strip=True)
            href_value = name_tag.get("href")
            torrent_link = href_value if isinstance(href_value, str) else ""

            size_tag = row.select_one("td:nth-of-type(5)")
            size = size_tag.get_text(strip=True) if size_tag else None

            duplicate_entry: dict[str, str | None] = {
                "name": name,
                "size": size,
                "link": torrent_link,
            }
            dupes.append(duplicate_entry)

        return dupes

    def get_category_id(self, meta: Meta) -> int:
        resolution = meta.resolution
        category = str(meta.category)
        genres = [g.lower() for g in meta.genres]
        keywords = [k.lower() for k in meta.keywords]
        is_anime = meta.anime
        non_eng = False
        sd = bool(meta.sd)
        if str(meta.original_language) != "en":
            non_eng = True

        anime = 32
        childrens_cartoons = 31
        documentary_hd = 54
        documentary_sd = 53

        movies_4k = 59
        movies_4k_non_english = 60

        movies_hd = 16
        movies_hd_non_english = 18

        movies_low_def = 17
        movies_low_def_non_english = 34

        movies_sd = 14
        movies_sd_non_english = 33

        tv_480p = 47
        tv_4k = 64
        tv_hd = 8
        tv_sd_x264 = 48
        tv_sd_xvid = 9

        tv_season_packs_4k = 63
        tv_season_packs_hd = 4
        tv_season_packs_sd = 6

        audiobooks = 35
        comics = 41
        ebooks = 22
        magazines = 46

        music_flac = 37
        music_mp3 = 36
        music_other = 39

        game_nin = 61
        game_pc = 26
        game_playstation = 28
        game_xbox = 29

        if category == "MOVIE":
            if "documentary" in genres or "documentary" in keywords:
                if sd:
                    return documentary_sd
                return documentary_hd
            if is_anime:
                return anime
            if resolution == "2160p":
                if non_eng:
                    return movies_4k_non_english
                return movies_4k
            if not sd:
                if non_eng:
                    return movies_hd_non_english
                return movies_hd
            if sd:
                if non_eng:
                    return movies_sd_non_english
                return movies_sd
            if non_eng:
                return movies_low_def_non_english
            return movies_low_def

        if category == "TV":
            if "documentary" in genres or "documentary" in keywords:
                if sd:
                    return documentary_sd
                return documentary_hd
            if is_anime:
                return anime
            if "children" in genres or "cartoons" in genres or "children" in keywords or "cartoons" in keywords or "cartoon" in keywords:
                return childrens_cartoons
            if meta.tv_pack:
                if resolution == "2160p":
                    return tv_season_packs_4k
                if sd:
                    return tv_season_packs_sd
                return tv_season_packs_hd
            if resolution == "2160p":
                return tv_4k
            if resolution in ["1080p", "1080i", "720p"]:
                return tv_hd
            if sd:
                if "xvid" in meta.video_encode.lower():
                    return tv_sd_xvid
                return tv_sd_x264
            return tv_480p

        if category == "BOOK":
            if meta.audiobook:
                return audiobooks
            if meta.comic or meta.manga:
                return comics
            if meta.magazine:
                return magazines
            return ebooks

        if category == "MUSIC":
            if meta.format == "FLAC":
                return music_flac
            if meta.format == "MP3":
                return music_mp3
            return music_other

        if category == "GAME":
            platform = str(meta.platform).upper()
            if platform in {"NDS", "3DS", "SWITCH", "WII", "WIIU"}:
                return game_nin
            if platform in {"PS1", "PS2", "PS3", "PS4", "PS5", "PSP", "PSVITA"}:
                return game_playstation
            if platform in {"XBOX", "X360", "XONE", "XSX"}:
                return game_xbox
            return game_pc

        return 0

    async def get_nfo(self, meta: Meta) -> dict[str, tuple[str, bytes, str]]:
        nfo_dir = Path(meta.base_dir) / "tmp" / meta.uuid
        nfo_files = list(nfo_dir.glob("*.nfo"))

        if nfo_files:
            nfo_path = nfo_files[0]
            async with aiofiles.open(nfo_path, "rb") as nfo_file:
                nfo_bytes = await nfo_file.read()
            return {"nfofile": (nfo_path.name, nfo_bytes, "application/octet-stream")}
        nfo_content = await self.generate_description(meta)
        nfo_bytes = nfo_content.encode("utf-8")
        nfo_filename = f"{(meta.scene_name or meta.basename_no_ext)}.nfo"
        return {"nfofile": (nfo_filename, nfo_bytes, "application/octet-stream")}

    async def get_name(self, meta: Meta) -> str:
        if meta.scene_name:
            return meta.scene_name

        return meta.basename_no_ext

    async def get_cover(self, meta: Meta) -> str:
        covers = meta.hosted_artwork
        if isinstance(covers, list):
            for entry in covers:
                if not isinstance(entry, dict):
                    continue
                raw_url = entry.get("raw_url")
                if isinstance(raw_url, str) and raw_url.startswith("https://"):
                    return raw_url

        artwork_url = meta.artwork_url
        if isinstance(artwork_url, str) and artwork_url.startswith("https://"):
            return artwork_url

        return ""

    async def get_data(self, meta: Meta) -> dict[str, Any]:
        message = f"{meta.overview}\n\n[youtube]{meta.youtube}[/youtube]"
        cover = await self.get_cover(meta)
        if meta.category in ("BOOK", "MUSIC"):
            message = meta.overview

        data: dict[str, Any] = {
            "UseNFOasDescr": "no",
            "message": message,
            "category": self.get_category_id(meta),
            "subject": await self.get_name(meta),
            "nothingtopost": "1",
            "t_image_url": cover,
            "submit": "Upload Torrent",
        }

        if meta.category == "MOVIE":
            data["t_link"] = str(meta.imdb_info.get("imdb_url", ""))

        # Anon
        anon = not (int(meta.anon or 0) == 0 and not self.config["TRACKERS"][self.tracker].get("anon", False))
        data.update({"anonymous": "yes" if anon else "no"})

        return data

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
            hash_is_id=True,
            torrent_field_name="torrentfile",
            torrent_name=f"{(meta.clean_name if meta.clean_name is not None else 'placeholder')}",
            upload_cookies=self.session.cookies,
            upload_url="https://immortalseed.me/upload.php",
            additional_files=files,
            success_list=["Download Torrent (SSL)", "Thank you for uploading"],
        )
