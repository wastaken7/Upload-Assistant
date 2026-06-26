# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import os
import platform
import re
from typing import Any, Optional, cast

import aiofiles
import httpx

from cogs.redaction import Redaction
from src.console import console
from src.get_desc import DescriptionBuilder
from src.trackers.COMMON import COMMON

Meta = dict[str, Any]
Config = dict[str, Any]


class TL:
    supported_categories = ('TV', 'MOVIE', 'BOOK', 'GAME')

    def __init__(self, config: Config) -> None:
        self.config: Config = config
        self.common = COMMON(config)
        self.tracker = 'TL'
        self.source_flag = 'TorrentLeech.org'
        self.base_url = 'https://www.torrentleech.org'
        self.http_upload_url = f'{self.base_url}/torrents/upload/'
        self.api_upload_url = f'{self.base_url}/torrents/upload/apiupload'
        self.torrent_url = f'{self.base_url}/torrent/'
        self.banned_groups = []
        self.session = httpx.AsyncClient(timeout=60.0)
        self.tracker_config: dict[str, Any] = self.config['TRACKERS'][self.tracker]
        self.api_upload: bool = bool(self.tracker_config.get('api_upload', False))
        self.passkey: str = str(self.tracker_config.get('passkey', ''))
        self.announce_list = [
            f'https://tracker.torrentleech.org/a/{self.passkey}/announce',
            f'https://tracker.tleechreload.org/a/{self.passkey}/announce'
        ]
        self.session.headers.update({
            'User-Agent': f'Upload Assistant ({platform.system()} {platform.release()})'
        })

    async def get_additional_checks(self, meta: Meta) -> bool:
        return self.common.check_and_confirm_adult_media_upload(meta, self.tracker)

    async def login(self, meta: Meta, force: bool = False) -> bool:
        if self.api_upload and not force:
            return True

        cookies_file = os.path.abspath(f"{meta['base_dir']}/data/cookies/TL.txt")

        cookie_path = os.path.abspath(cookies_file)
        if not os.path.exists(cookie_path):
            console.print(f"[bold red]'{self.tracker}' Cookies not found at: {cookie_path}[/bold red]")
            return False

        self.session.cookies.update(await self.common.parseCookieFile(cookies_file))

        try:
            if force:
                response = await self.session.get('https://www.torrentleech.org/torrents/browse/index', timeout=10)
                if response.status_code == 301 and 'torrents/browse' in str(response.url):
                    if meta.get('debug'):
                        console.print(f"[bold green]Logged in to '{self.tracker}' with cookies.[/bold green]")
                    return True
            elif not force:
                response = await self.session.get(self.http_upload_url, timeout=10)
                if response.status_code == 200 and 'torrents/upload' in str(response.url):
                    if meta.get('debug'):
                        console.print(f"[bold green]Logged in to '{self.tracker}' with cookies.[/bold green]")
                    return True
            else:
                console.print(f"[bold red]Login to '{self.tracker}' with cookies failed. Please check your cookies.[/bold red]")
                return False

        except httpx.RequestError as e:
            console.print(f"[bold red]Error while validating credentials for '{self.tracker}': {e}[/bold red]")
            return False

        return False

    async def generate_description(self, meta: Meta) -> str:
        builder = DescriptionBuilder(self.tracker, self.config)
        process_screenshot = not self.tracker_config.get("img_rehost", True) or self.tracker_config.get("api_upload", True)
        description = await builder.general_description_generator(
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
            nfo=True,
            screenshots=process_screenshot,
            tonemapped_header=True,
            tv_info=True,
            ua_signature=True,
            user_description=True,
            signature=f"""<div style="text-align: right; font-size: 11px;"><a href="https://github.com/wastaken7/Upload-Assistant">{meta["ua_signature"]}</a></div>""",
        )

        return description

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

        if meta.get("anime", 0):
            return anime

        category = str(meta.get("category", ""))

        if category == "MOVIE":
            if str(meta.get("original_language", "")) != "en":
                return movie_foreign
            elif "Documentary" in str(meta.get("genres", "")):
                return movie_documentary
            elif str(meta.get("resolution", "")) == "2160p":
                return movie_4k
            elif str(meta.get("is_disc", "")) in ("BDMV", "HDDVD") or (str(meta.get("type", "")) == "REMUX" and str(meta.get("source", "")) in ("BluRay", "HDDVD")):
                return movie_bluray
            elif str(meta.get("type", "")) == "ENCODE" and str(meta.get("source", "")) in (
                "BluRay",
                "HDDVD",
            ):
                return movie_bluray_rip
            elif str(meta.get("is_disc", "")) == "DVD" or (str(meta.get("type", "")) == "REMUX" and "DVD" in str(meta.get("source", ""))):
                return movie_dvd
            elif (str(meta.get("type", "")) == "ENCODE" and "DVD" in str(meta.get("source", ""))) or str(meta.get("type", "")) == "DVDRIP":
                return movie_dvd_rip
            elif "WEB" in str(meta.get("type", "")):
                return movie_webrip
            elif str(meta.get("type", "")) == "HDTV":
                return movie_hd_rip

        elif category == "TV":
            if str(meta.get("original_language", "")) != "en":
                return tv_foreign
            elif meta.get("tv_pack", 0):
                return tv_boxsets
            elif meta.get("sd"):
                return tv_episodes
            else:
                return tv_episodes_hd

        elif category == "BOOK":
            if meta.get("comic", False) or meta.get("manga", False):
                return comics
            return ebook

        elif category == "GAME":
            plat = str(meta.get("platform", "")).lower()

            if plat == "x360":  # noqa: SIM116
                return games_xbox360
            elif plat == "xone":
                return games_xboxone
            elif plat == "xbox":
                return games_xbox
            elif plat == "pc":
                return games_pc
            elif plat == "ps5":
                return games_ps5
            elif plat == "ps4":
                return games_ps4
            elif plat == "ps3":
                return games_ps3
            elif plat == "ps2":
                return games_ps2
            elif plat == "psp":
                return games_psp
            elif plat == "wii":
                return games_wii
            elif plat == "nds":
                return games_nds
            elif plat == "switch":
                return games_switch
            elif plat == "mac":
                return games_mac

            return games_pc

        return 0

    def get_screens(self, meta: Meta) -> list[str]:
        images = cast(list[dict[str, Any]], meta.get("menu_images", [])) + cast(list[dict[str, Any]], meta.get("image_list", []) + meta.get("spectrograms_images", []))
        return [image['raw_url'] for image in images if image.get('raw_url')]

    async def get_name(self, meta):
        tl_name = meta.get('name').replace(meta['aka'], '')
        tl_name = re.sub(r"\s{2,}", " ", tl_name)

        return tl_name

    async def search_existing(self, meta: Meta) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        should_continue = await self.get_additional_checks(meta)
        if not should_continue:
            meta["skipping"] = f"{self.tracker}"
            return results

        login = await self.login(meta, force=True)
        if not login:
            meta['skipping'] = "TL"
            if meta.get('debug'):
                console.print(f"[bold red]Skipping upload to '{self.tracker}' as login failed.[/bold red]")
            return []
        cat_id = self.get_category(meta)

        search_name = str(meta.get("title", ""))
        resolution = str(meta.get("resolution", ""))
        year = str(meta.get('year', ''))
        episode = str(meta.get('episode', ''))
        season = str(meta.get('season', ''))
        season_episode = f"{season}{episode}" if season or episode else ''

        forbidden_keywords: list[str] = []

        is_disc = str(meta.get("is_disc", "") or "").strip().lower()
        _type = str(meta.get("type", "") or "").strip().lower()

        if is_disc == 'bdmv':
            forbidden_keywords.extend(['remux', 'x264', 'x265'])

        if _type == 'webdl':
            forbidden_keywords.extend(['webrip', 'bluray', 'blu-ray'])

        search_urls: list[str] = []

        if meta['category'] == 'TV':
            if meta.get('tv_pack', False):
                param = f"{cat_id}/query/{search_name} {season} {resolution}"
                search_urls.append(f"{self.base_url}/torrents/browse/list/categories/{param}")
            else:
                episode_param = f"{cat_id}/query/{search_name} {season_episode} {resolution}"
                search_urls.append(f"{self.base_url}/torrents/browse/list/categories/{episode_param}")

                # Also check for season packs
                pack_cat_id = 44 if cat_id == 44 else 27  # Foreign TV shows do not have a separate cat_id for season/episodes
                pack_param = f"{pack_cat_id}/query/{search_name} {season} {resolution}"
                search_urls.append(f"{self.base_url}/torrents/browse/list/categories/{pack_param}")

        elif meta['category'] == 'MOVIE':
            param = f"{cat_id}/query/{search_name} {year} {resolution}"
            search_urls.append(f"{self.base_url}/torrents/browse/list/categories/{param}")

        elif meta["category"] in ("BOOK", "GAME"):
            param = f"{cat_id}/query/{search_name}"
            search_urls.append(f"{self.base_url}/torrents/browse/list/categories/{param}")

        for url in search_urls:
            results.extend(await self._search_url(url, forbidden_keywords))

        return results

    async def _search_url(self, url: str, forbidden_keywords: list[str]) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        try:
            response = await self.session.get(url, timeout=20)
            response.raise_for_status()

            data = cast(dict[str, Any], response.json())
            torrents = cast(list[dict[str, Any]], data.get("torrentList", []))

            for torrent in torrents:
                name = str(torrent.get('name', ''))
                link = f"{self.torrent_url}{torrent.get('fid')}"
                size = torrent.get('size')
                if not any(keyword in name.lower() for keyword in forbidden_keywords):
                    results.append({
                        'name': name,
                        'size': size,
                        'link': link
                    })

        except Exception as e:
            console.print(f"[bold red]Error searching for duplicates on {self.tracker} ({url}): {e}[/bold red]")

        return results

    async def upload(self, meta: Meta) -> Optional[bool]:
        await self.common.create_torrent_for_upload(meta, self.tracker, self.source_flag)

        if self.api_upload:
            is_uploaded = await self.upload_api(meta)
            return is_uploaded
        else:
            is_uploaded = await self.cookie_upload(meta)
            return is_uploaded

    async def upload_api(self, meta: Meta) -> bool:
        torrent_path = f"{meta['base_dir']}/tmp/{meta['uuid']}/[{self.tracker}].torrent"

        async with aiofiles.open(torrent_path, 'rb') as open_torrent:
            torrent_bytes = await open_torrent.read()
        files: dict[str, tuple[Any, Any, str]] = {
            "torrent": (f"{await self.get_name(meta)}.torrent", torrent_bytes, "application/x-bittorrent"),
        }

        data: dict[str, Any] = {
            "announcekey": self.passkey,
            "category": self.get_category(meta),
            "description": await self.generate_description(meta),
            "name": await self.get_name(meta),
            "nonscene": "on" if not meta.get("scene") else "off",
        }

        if meta.get('anime', False) and meta.get('mal_id', 0) != 0:
            data.update({'animeid': f"https://anilist.co/anime/{meta.get('mal_id')}"})

        else:
            if meta.get('category') == 'MOVIE':
                imdb_info = cast(dict[str, Any], meta.get('imdb_info', {}))
                data.update({'imdb': imdb_info.get('imdbID', '')})

            if meta.get('category') == 'TV':
                data.update({
                    'tvmazeid': meta.get('tvmaze_id', ''),
                    'tvmazetype': meta.get('tv_pack', ''),
                })

        anon = not (meta.get('anon') == 0 and not self.tracker_config.get('anon', False))
        if anon:
            data.update({'is_anonymous_upload': 'on'})

        if not meta.get('debug'):
            response = await self.session.post(
                url=self.api_upload_url,
                files=files,
                data=data
            )

            if not response.text.isnumeric():
                tracker_status = cast(dict[str, Any], meta.get('tracker_status', {}))
                tracker_status.setdefault(self.tracker, {})
                tracker_status[self.tracker]['status_message'] = 'data error: ' + response.text

            if response.text.isnumeric():
                torrent_id = response.text
                tracker_status = cast(dict[str, Any], meta.get('tracker_status', {}))
                tracker_status.setdefault(self.tracker, {})
                tracker_status[self.tracker]['status_message'] = 'Torrent uploaded successfully.'
                tracker_status[self.tracker]['torrent_id'] = torrent_id
                await self.common.create_torrent_ready_to_seed(meta, self.tracker, self.source_flag, self.announce_list, self.torrent_url + torrent_id)
                return True

        else:
            console.print("[cyan]TL Request Data:")
            console.print(Redaction.redact_private_info(data))
            await self.common.create_torrent_for_upload(meta, f"{self.tracker}" + "_DEBUG", f"{self.tracker}" + "_DEBUG", announce_url="https://fake.tracker")
            return True  # Debug mode - simulated success
        return False

    async def get_cookie_upload_data(self, meta: Meta) -> dict[str, Any]:
        tvMazeURL = ''
        if meta.get('category') == 'TV' and meta.get("tvmaze_id"):
            tvMazeURL = f"https://www.tvmaze.com/shows/{meta.get('tvmaze_id')}"

        data: dict[str, Any] = {
            "name": await self.get_name(meta),
            "category": self.get_category(meta),
            "nonscene": "on" if not meta.get("scene") else "off",
            "imdbURL": str(cast(dict[str, Any], meta.get("imdb_info", {})).get("imdb_url", "")),
            "tvMazeURL": tvMazeURL,
            "igdbURL": "",
            "torrentNFO": "0",
            "torrentDesc": "1",
            "nfotextbox": "",
            "torrentComment": "0",
            "uploaderComments": "",
            "is_anonymous_upload": "off",
            "screenshots[]": self.get_screens(meta) if self.tracker_config.get("img_rehost", True) else "",
        }

        anon = not (meta.get('anon') == 0 and not self.tracker_config.get('anon', False))
        if anon:
            data.update({'is_anonymous_upload': 'on'})

        return data

    async def cookie_upload(self, meta: Meta) -> Optional[bool]:
        await self.generate_description(meta)
        async with aiofiles.open(f"{meta['base_dir']}/tmp/{meta['uuid']}/[{self.tracker}]DESCRIPTION.txt", encoding='utf-8') as f:
            description_content = await f.read()
        login = await self.login(meta)
        if not login:
            tracker_status = cast(dict[str, Any], meta.get('tracker_status', {}))
            tracker_status.setdefault(self.tracker, {})
            tracker_status[self.tracker]['status_message'] = "data error: Login with cookies failed."
            return None

        data = await self.get_cookie_upload_data(meta)

        if meta.get('debug'):
            console.print("[cyan]TL Request Data:")
            console.print(Redaction.redact_private_info(data))
            await self.common.create_torrent_for_upload(meta, f"{self.tracker}" + "_DEBUG", f"{self.tracker}" + "_DEBUG", announce_url="https://fake.tracker")
            return True  # Debug mode - simulated success
        else:
            try:
                async with aiofiles.open(f"{meta['base_dir']}/tmp/{meta['uuid']}/[{self.tracker}].torrent", 'rb') as f:
                    torrent_bytes = await f.read()
                files = {
                    'torrent': ('torrent.torrent', torrent_bytes, 'application/x-bittorrent'),
                    'nfo': ('description.txt', description_content, 'text/plain'),
                }

                response = await self.session.post(url=self.http_upload_url, files=files, data=data)

                if response.status_code == 302 and 'location' in response.headers:
                    torrent_id = response.headers['location'].replace('/successfulupload?torrentID=', '')
                    torrent_url = f"{self.base_url}/torrent/{torrent_id}"
                    meta['tracker_status'][self.tracker]['status_message'] = 'Torrent uploaded successfully.'
                    meta['tracker_status'][self.tracker]['torrent_id'] = torrent_id

                    await self.common.create_torrent_ready_to_seed(meta, self.tracker, self.source_flag, self.announce_list, torrent_url)
                    return True

                else:
                    meta["tracker_status"][self.tracker]["status_message"] = "data error - Upload failed: No success redirect found."
                    failure_path = await self.common.save_html_file(meta, self.tracker, response.text, "Failed_Upload")
                    console.print(f"{self.tracker}: Failed upload. The HTML response saved to {failure_path}")
                    return False

            except httpx.RequestError as e:
                status_message = f"data error - {str(e)}"

            meta["tracker_status"][self.tracker]["status_message"] = status_message
