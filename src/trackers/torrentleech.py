# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import platform
import re
from typing import Any, cast

import aiofiles
import httpx

from src.cogs.redaction import Redaction
from src.console import logger
from src.cookie_auth import CookieValidator
from src.get_desc import DescriptionBuilder
from src.meta import Meta
from src.trackers.common import Common

Config = dict[str, Any]


class TorrentLeech:
    """
    TORRENTLEECH (TL) is a Private Torrent Tracker for 0DAY / GENERAL. not here _ not scene
    """

    auth_type = "other_api"
    tracker = "TORRENTLEECH"
    display_name = "TorrentLeech"
    source_flag = "TorrentLeech.org"
    base_url = "https://www.torrentleech.org"
    banned_groups = ()
    http_upload_url = f"{base_url}/torrents/upload/"
    api_upload_url = f"{base_url}/torrents/upload/apiupload"
    torrent_url = f"{base_url}/torrent/"
    supported_categories = ("TV", "MOVIE", "BOOK", "GAME", "MUSIC")
    tracker_urls = ("tracker.tleechreload", "tracker.torrentleech")
    allows_bloated_audio = True

    def __init__(self, config: Config) -> None:
        self.config: Config = config
        self.common = Common(config)
        self.cookie_validator = CookieValidator(config)
        self.session = httpx.AsyncClient(timeout=60.0)
        self.tracker_config: dict[str, Any] = self.config["TRACKERS"][self.tracker]
        self.api_upload: bool = bool(self.tracker_config.get("api_upload", False))
        self.passkey: str = str(self.tracker_config.get("passkey", ""))
        self.announce_list = [f"https://tracker.torrentleech.org/a/{self.passkey}/announce", f"https://tracker.tleechreload.org/a/{self.passkey}/announce"]
        self.session.headers.update({"User-Agent": f"Upload Assistant ({platform.system()} {platform.release()})"})

    async def get_additional_checks(self, meta: Meta) -> bool:
        return self.common.check_and_confirm_adult_media_upload(meta, self.tracker)

    async def login(self, meta: Meta, force: bool = False) -> bool:
        if self.api_upload and not force:
            return True

        cookie_jar = await self.cookie_validator.load_session_cookies(meta, self.tracker)
        if cookie_jar is None:
            return False

        self.session.cookies = cast(Any, cookie_jar)
        try:
            if force:
                response = await self.session.get(f"{self.base_url}/torrents/browse/index", timeout=10)
                logged_in = response.status_code == 301 and "torrents/browse" in str(response.url)
            else:
                response = await self.session.get(self.http_upload_url, timeout=10)
                logged_in = response.status_code == 200 and "torrents/upload" in str(response.url)

            if logged_in:
                logger.debug(f"{self.tracker}: [bold green]Logged in to '{self.tracker}' with cookies.[/bold green]")
                return True

            logger.info(f"{self.tracker}: [bold red]Login to '{self.tracker}' with cookies failed. Please check your cookies.[/bold red]")
            return False
        except httpx.RequestError as e:
            logger.info(f"{self.tracker}: [bold red]Error while validating credentials for '{self.tracker}': {e}[/bold red]")
            return False

    async def generate_description(self, meta: Meta) -> str:
        builder = DescriptionBuilder(self.tracker, self.config)
        process_screenshot = not self.tracker_config.get("img_rehost", True) or self.tracker_config.get("api_upload", True)
        return await builder.general_description_generator(
            meta,
            audio_spectrogram=process_screenshot,
            bluray=True,
            book=True,
            custom_header=True,
            custom_signature=True,
            description=True,
            game=True,
            languages=False,
            logo=True,
            mediainfo=True,
            menu_screenshots=process_screenshot,
            music=True,
            nfo=True,
            screenshots=process_screenshot,
            tonemapped_header=True,
            tv_info=True,
            ua_signature=True,
            user_description=True,
            signature=f"""<div style="text-align: right; font-size: 11px;"><a href="https://github.com/wastaken7/Upload-Assistant">{meta.ua_signature}</a></div>""",
        )

    def get_category(self, meta: Meta) -> int:
        anime = 34

        movie_4k = 47
        movie_bluray = 13
        movie_bluray_rip = 14
        _movie_cam = 8
        _movie_ts = 9
        movie_documentary = 29
        movie_dvd = 12
        movie_dvd_rip = 11
        movie_foreign = 36
        movie_hd_rip = 43
        movie_webrip = 37

        tv_boxsets = 27
        tv_episodes = 26
        tv_episodes_hd = 32
        tv_foreign = 44

        ebook = 45
        comics = 46

        games_pc = 17
        games_xbox = 18
        games_xbox360 = 19
        games_ps2 = 20
        games_ps3 = 21
        games_psp = 22
        games_wii = 28
        games_nds = 30
        games_ps4 = 39
        games_xboxone = 40
        games_mac = 42
        games_switch = 48
        games_ps5 = 49

        music = 31

        if meta.anime:
            return anime

        category = meta.category

        if category == "MOVIE":
            if str(meta.original_language) != "en":
                return movie_foreign
            if "Documentary" in str(meta.genres):
                return movie_documentary
            if meta.resolution == "2160p":
                return movie_4k
            if meta.is_disc in ("BDMV", "HDDVD") or (str(meta.type) == "REMUX" and str(meta.source) in ("BluRay", "HDDVD")):
                return movie_bluray
            if str(meta.type) == "ENCODE" and str(meta.source) in (
                "BluRay",
                "HDDVD",
            ):
                return movie_bluray_rip
            if meta.is_disc == "DVD" or (str(meta.type) == "REMUX" and "DVD" in str(meta.source)):
                return movie_dvd
            if (str(meta.type) == "ENCODE" and "DVD" in str(meta.source)) or str(meta.type) == "DVDRIP":
                return movie_dvd_rip
            if "WEB" in str(meta.type):
                return movie_webrip
            if str(meta.type) == "HDTV":
                return movie_hd_rip

        elif category == "TV":
            if str(meta.original_language) != "en":
                return tv_foreign
            if meta.tv_pack:
                return tv_boxsets
            if meta.sd:
                return tv_episodes
            return tv_episodes_hd

        elif category == "BOOK":
            if meta.comic or meta.manga:
                return comics
            return ebook

        elif category == "GAME":
            plat = meta.platform.lower()

            if plat == "x360":
                return games_xbox360
            if plat == "xone":
                return games_xboxone
            if plat == "xbox":
                return games_xbox
            if plat == "pc":
                return games_pc
            if plat == "ps5":
                return games_ps5
            if plat == "ps4":
                return games_ps4
            if plat == "ps3":
                return games_ps3
            if plat == "ps2":
                return games_ps2
            if plat == "psp":
                return games_psp
            if plat == "wii":
                return games_wii
            if plat == "nds":
                return games_nds
            if plat == "switch":
                return games_switch
            if plat == "mac":
                return games_mac

            return games_pc

        if category == "MUSIC":
            return music

        return 0

    def get_screens(self, meta: Meta) -> list[str]:
        images = cast(list[dict[str, Any]], meta.menu_images) + meta.image_list + meta.spectrograms_images + meta.dynamic_hdr_plot_images
        return [image["raw_url"] for image in images if image.get("raw_url")]

    async def get_name(self, meta: Meta) -> str:
        tl_name = meta.name.replace(meta.aka, "")
        return re.sub(r"\s{2,}", " ", tl_name)

    async def search_existing(self, meta: Meta) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []

        login = await self.login(meta, force=True)
        if not login:
            meta.skipping = "TORRENTLEECH"
            logger.debug(f"{self.tracker}: [bold red]Skipping upload to '{self.tracker}' as login failed.[/bold red]")
            return []
        cat_id = self.get_category(meta)

        search_name = meta.title
        resolution = meta.resolution
        year = str(meta.year) if meta.year is not None else ""
        episode = meta.episode
        season = str(meta.season)
        season_episode = f"{season}{episode}" if season or episode else ""

        forbidden_keywords: list[str] = []

        is_disc = (meta.is_disc or "").strip().lower()
        _type = (meta.type or "").strip().lower()

        if is_disc == "bdmv":
            forbidden_keywords.extend(["remux", "x264", "x265"])

        if _type == "webdl":
            forbidden_keywords.extend(["webrip", "bluray", "blu-ray"])

        search_urls: list[str] = []

        if meta.category == "TV":
            if meta.tv_pack:
                param = f"{cat_id}/query/{search_name} {season} {resolution}"
                search_urls.append(f"{self.base_url}/torrents/browse/list/categories/{param}")
            else:
                episode_param = f"{cat_id}/query/{search_name} {season_episode} {resolution}"
                search_urls.append(f"{self.base_url}/torrents/browse/list/categories/{episode_param}")

                # Also check for season packs
                pack_cat_id = 44 if cat_id == 44 else 27  # Foreign TV shows do not have a separate cat_id for season/episodes
                pack_param = f"{pack_cat_id}/query/{search_name} {season} {resolution}"
                search_urls.append(f"{self.base_url}/torrents/browse/list/categories/{pack_param}")

        elif meta.category == "MOVIE":
            param = f"{cat_id}/query/{search_name} {year} {resolution}"
            search_urls.append(f"{self.base_url}/torrents/browse/list/categories/{param}")

        elif meta.category in ("BOOK", "GAME", "MUSIC"):
            param = f"{cat_id}/query/{search_name}"
            search_urls.append(f"{self.base_url}/torrents/browse/list/categories/{param}")

        for url in search_urls:
            results.extend(await self._search_url(url, forbidden_keywords))

        return results

    async def _search_url(self, url: str, forbidden_keywords: list[str]) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        response = await self.session.get(url, timeout=20)
        response.raise_for_status()

        data = cast(dict[str, Any], response.json())
        torrents = cast(list[dict[str, Any]], data.get("torrentList", []))

        for torrent in torrents:
            name = str(torrent.get("name", ""))
            link = f"{self.torrent_url}{torrent.get('fid')}"
            size = torrent.get("size")
            if not any(keyword in name.lower() for keyword in forbidden_keywords):
                results.append({"name": name, "size": size, "link": link})

        return results

    async def upload(self, meta: Meta) -> bool | None:
        await self.common.create_torrent_for_upload(meta, self.tracker, self.source_flag)

        if self.api_upload:
            return await self.upload_api(meta)
        return await self.cookie_upload(meta)

    async def upload_api(self, meta: Meta) -> bool:
        torrent_path = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/[{self.tracker}].torrent"

        async with aiofiles.open(torrent_path, "rb") as open_torrent:
            torrent_bytes = await open_torrent.read()
        files: dict[str, tuple[Any, Any, str]] = {
            "torrent": (f"{await self.get_name(meta)}.torrent", torrent_bytes, "application/x-bittorrent"),
        }

        data: dict[str, Any] = {
            "announcekey": self.passkey,
            "category": self.get_category(meta),
            "description": await self.generate_description(meta),
            "name": await self.get_name(meta),
            "nonscene": "on" if not meta.scene else "off",
        }

        if meta.anime and meta.mal_id != 0:
            data.update({"animeid": f"https://anilist.co/anime/{meta.mal_id}"})

        else:
            if meta.category == "MOVIE":
                imdb_info = meta.imdb_info
                data.update({"imdb": imdb_info.get("imdbID", "")})

            if meta.category == "TV":
                data.update(
                    {
                        "tvmazeid": meta.tvmaze_id,
                        "tvmazetype": meta.tv_pack,
                    }
                )

        anon = not (meta.anon == 0 and not self.tracker_config.get("anon", False))
        if anon:
            data.update({"is_anonymous_upload": "on"})

        if not meta.debug:
            response = await self.session.post(url=self.api_upload_url, files=files, data=data)

            if not response.text.isnumeric():
                tracker_status = meta.tracker_status
                tracker_status.setdefault(self.tracker, {})
                tracker_status[self.tracker]["status_message"] = "data error: " + response.text

            if response.text.isnumeric():
                torrent_id = response.text
                tracker_status = meta.tracker_status
                tracker_status.setdefault(self.tracker, {})
                tracker_status[self.tracker]["status_message"] = "Torrent uploaded successfully."
                tracker_status[self.tracker]["torrent_id"] = torrent_id
                await self.common.create_torrent_ready_to_seed(meta, self.tracker, self.source_flag, self.announce_list, self.torrent_url + torrent_id)
                return True

        else:
            logger.info(f"{self.tracker}: Request Data:")
            logger.info(Redaction.redact_private_info(data))
            await self.common.create_torrent_for_upload(meta, f"{self.tracker}" + "_DEBUG", f"{self.tracker}" + "_DEBUG", announce_url="https://fake.tracker")
            return True  # Debug mode - simulated success
        return False

    async def get_cookie_upload_data(self, meta: Meta) -> dict[str, Any]:
        tvmaze_url = ""
        if meta.category == "TV" and meta.tvmaze_id:
            tvmaze_url = f"https://www.tvmaze.com/shows/{meta.tvmaze_id}"

        data: dict[str, Any] = {
            "name": await self.get_name(meta),
            "category": self.get_category(meta),
            "nonscene": "on" if not meta.scene else "off",
            "imdbURL": meta.imdb_info.get("imdb_url", ""),
            "tvMazeURL": tvmaze_url,
            "igdbURL": "",
            "torrentNFO": "0",
            "torrentDesc": "1",
            "nfotextbox": "",
            "torrentComment": "0",
            "uploaderComments": "",
            "is_anonymous_upload": "off",
            "screenshots[]": self.get_screens(meta) if self.tracker_config.get("img_rehost", True) else "",
        }

        anon = not (meta.anon == 0 and not self.tracker_config.get("anon", False))
        if anon:
            data.update({"is_anonymous_upload": "on"})

        return data

    async def cookie_upload(self, meta: Meta) -> bool | None:
        description_content = await self.generate_description(meta)
        login = await self.login(meta)
        if not login:
            tracker_status = meta.tracker_status
            tracker_status.setdefault(self.tracker, {})
            tracker_status[self.tracker]["status_message"] = "data error: Login with cookies failed."
            return None

        data = await self.get_cookie_upload_data(meta)

        if meta.debug:
            logger.debug(f"{self.tracker}: [cyan]Request Data:")
            logger.debug(Redaction.redact_private_info(data))
            await self.common.create_torrent_for_upload(meta, f"{self.tracker}" + "_DEBUG", f"{self.tracker}" + "_DEBUG", announce_url="https://fake.tracker")
            return True  # Debug mode - simulated success
        try:
            async with aiofiles.open(f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/[{self.tracker}].torrent", "rb") as f:
                torrent_bytes = await f.read()
            files: dict[str, tuple[str, bytes | str, str]] = {
                "torrent": ("torrent.torrent", torrent_bytes, "application/x-bittorrent"),
                "nfo": ("description.txt", description_content, "text/plain"),
            }

            response = await self.session.post(url=self.http_upload_url, files=files, data=data)

            if response.status_code == 302 and "location" in response.headers:
                torrent_id = response.headers["location"].replace("/successfulupload?torrentID=", "")
                torrent_url = f"{self.base_url}/torrent/{torrent_id}"
                meta.tracker_status[self.tracker]["status_message"] = "Torrent uploaded successfully."
                meta.tracker_status[self.tracker]["torrent_id"] = torrent_id

                await self.common.create_torrent_ready_to_seed(meta, self.tracker, self.source_flag, self.announce_list, torrent_url)
                return True

            meta.tracker_status[self.tracker]["status_message"] = "data error - Upload failed: No success redirect found."
            failure_path = await self.common.save_html_file(meta, self.tracker, response.text, "Failed_Upload")
            logger.info(f"{self.tracker}: Failed upload. The HTML response saved to {failure_path}")
            return False

        except httpx.RequestError as e:
            status_message = f"data error - {e!s}"

        meta.tracker_status[self.tracker]["status_message"] = status_message
        return None
