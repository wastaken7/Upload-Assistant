# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import base64
import glob
import os
import re
import unicodedata
from typing import Any, Optional, cast

import aiofiles
import httpx

from cogs.redaction import Redaction
from src.console import console
from src.get_desc import DescriptionBuilder, html_to_bbcode
from src.languages import languages_manager

from .COMMON import COMMON

Meta = dict[str, Any]
Config = dict[str, Any]


class SPD:
    supported_categories = ('TV', 'MOVIE', 'BOOK', 'GAME')

    def __init__(self, config: Config) -> None:
        self.url = "https://speedapp.io"
        self.config: Config = config
        self.common = COMMON(config)
        self.tracker = 'SPD'
        self.upload_url = 'https://speedapp.io/api/upload'
        self.torrent_url = 'https://speedapp.io/browse/'
        self.banned_groups = []
        self.banned_url = 'https://speedapp.io/api/torrent/release-group/blacklist'
        api_key = str(self.config['TRACKERS'][self.tracker]['api_key'])
        self.session = httpx.AsyncClient(headers={
            'User-Agent': "Upload Assistant",
            'accept': 'application/json',
            'Authorization': api_key,
        }, timeout=30.0)

    async def get_cat_id(self, meta: Meta) -> Optional[str]:
        if not meta.get('language_checked', False):
            await languages_manager.process_desc_language(meta, tracker=self.tracker)

        subtitle_langs = cast(list[Any], meta.get("subtitle_languages") or [])
        audio_langs = cast(list[Any], meta.get("audio_languages") or [])
        langs = [str(lang).lower() for lang in (subtitle_langs + audio_langs)]
        romanian = 'romanian' in langs

        origin_countries = cast(list[Any], meta.get('origin_country', []))
        category = str(meta.get('category', ''))
        if 'RO' in origin_countries:
            if category == 'TV':
                return '60'
            elif category == 'MOVIE':
                return '59'

        # documentary
        genres = str(meta.get("genres", ""))
        keywords = str(meta.get("keywords", ""))
        if 'documentary' in genres.lower() or 'documentary' in keywords.lower():
            return '63' if romanian else '9'

        # anime
        if meta.get('anime'):
            return '3'

        # TV
        if category == 'TV':
            if meta.get('tv_pack'):
                return '66' if romanian else '41'
            elif meta.get('sd'):
                return '46' if romanian else '45'
            return '44' if romanian else '43'

        # MOVIE
        if category == 'MOVIE':
            resolution = str(meta.get('resolution', ''))
            media_type = str(meta.get('type', ''))
            if resolution == '2160p' and media_type != 'DISC':
                return '57' if romanian else '61'
            if media_type in ('REMUX', 'WEBDL', 'WEBRIP', 'HDTV', 'ENCODE'):
                return '29' if romanian else '8'
            if media_type == 'DISC':
                return '24' if romanian else '17'
            if media_type == 'SD':
                return '35' if romanian else '10'

        # BOOK/EBOOK category
        if category == "BOOK":
            return "6"

        # Game
        if category == "GAME":
            if meta.get("console_game", False):
                return "52"
            return "11"

        return None

    async def get_file_info(self, meta: Meta) -> tuple[Optional[str], Optional[str]]:
        base_path = f"{meta['base_dir']}/tmp/{meta['uuid']}"
        if meta.get("bdinfo"):
            async with aiofiles.open(
                f"{base_path}/BD_SUMMARY_00.txt",
                encoding="utf-8",
            ) as bd_file:
                bd_info = await bd_file.read()
            return None, bd_info
        else:
            async with aiofiles.open(
                f"{base_path}/MEDIAINFO_CLEANPATH.txt",
                encoding="utf-8",
            ) as mi_file:
                media_info = await mi_file.read()
            return media_info, None

    async def get_screenshots(self, meta: Meta) -> list[str]:
        images = cast(list[dict[str, Any]], meta.get('menu_images', [])) + cast(
            list[dict[str, Any]], meta.get('image_list', [])
        )
        return [image['raw_url'] for image in images if image.get('raw_url')]

    async def search_existing(self, meta: Meta, _disctype: str) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        search_url = 'https://speedapp.io/api/torrent'

        params: dict[str, str] = {}
        if int(meta.get('imdb_id', 0) or 0) != 0:
            imdb_info = cast(dict[str, Any], meta.get('imdb_info', {}))
            params['imdbId'] = str(imdb_info.get('imdbID', ''))
        else:
            search_title = str(meta.get('title', '')).replace(':', '').replace("'", '').replace(',', '')
            params['search'] = search_title

        try:
            response = await self.session.get(url=search_url, params=params, headers=self.session.headers)

            if response.status_code == 200:
                data = cast(list[dict[str, Any]], response.json())
                for each in data:
                    name = each.get('name')
                    size = each.get('size')
                    link = f'{self.torrent_url}{each.get("id")}/'

                    if name:
                        results.append({
                            'name': str(name),
                            'size': size,
                            'link': link
                        })
                return results
            else:
                console.print(f'[bold red]HTTP request failed. Status: {response.status_code}')

        except Exception as e:
            console.print(f'[bold red]Unexpected error: {e}')
            console.print_exception()

        return results

    async def search_channel(self, meta: Meta) -> Optional[int]:
        spd_channel = meta.get('spd_channel', '') or self.config['TRACKERS'][self.tracker].get('channel', '')

        # if no channel is specified, use the default
        if not spd_channel:
            return 1

        # return the channel as int if it's already an integer
        if isinstance(spd_channel, int):
            return spd_channel

        # if user enters id as a string number
        if isinstance(spd_channel, str):
            if spd_channel.isdigit():
                return int(spd_channel)
            # if user enter tag then it will use API to search
            else:
                pass

        params: dict[str, str] = {
            'search': str(spd_channel)
        }

        try:
            response = await self.session.get(url=self.url + '/api/channel', params=params, headers=self.session.headers)

            if response.status_code == 200:
                data = cast(list[dict[str, Any]], response.json())
                for entry in data:
                    channel_id = entry.get('id')
                    tag = entry.get('tag')

                    if channel_id and tag:
                        if tag != spd_channel:
                            console.print(f'[{self.tracker}]: Unable to find a matching channel based on your input. Please check if you entered it correctly.')
                            return
                        else:
                            return int(channel_id)
                    else:
                        console.print(f'[{self.tracker}]: Could not find the channel ID. Please check if you entered it correctly.')

                else:
                    console.print(f"[bold red]HTTP request failed. Status: {response.status_code}")

        except Exception as e:
            console.print(f"[bold red]Unexpected error: {e}")
            console.print_exception()

    async def edit_desc(self, meta: Meta) -> str:
        builder = DescriptionBuilder(self.tracker, self.config)

        description = await builder.general_description_generator(
            meta,
            audio_spectrogram=False,
            bluray=False,
            book=False,
            custom_header=True,
            custom_signature=False,
            description=False,
            game=False,
            languages=False,
            logo=True,
            mediainfo=False,
            menu_screenshots=False,
            nfo=False,
            screenshots=False,
            tonemapped_header=True,
            tv_info=True,
            ua_signature=True,
            user_description=True,
            signature=f"[url=https://github.com/wastaken7/Upload-Assistant]{meta.get('ua_signature', '')}[/url]",
        )

        return description

    async def edit_name(self, meta: Meta) -> str:
        tracker_name = meta["uuid"]
        scene_name = meta.get("scene_name") or ""

        use_metadata_name = self.config["TRACKERS"][self.tracker].get("use_metadata_name", False)
        if use_metadata_name:
            clean_name = meta.get("clean_name") or ""
            tracker_name = scene_name if scene_name else clean_name
            tracker_name = tracker_name.replace("DD+", "DDP").replace("DTS:", "DTS-").replace("HDR10+", "HDR10P")
            tracker_name = unicodedata.normalize("NFD", tracker_name)
            tracker_name = "".join(c for c in tracker_name if c.isascii() and (c.isalnum() or c in (" ", ".", "-")))
            tracker_name = tracker_name.replace("!", "")

        else:
            if scene_name:
                tracker_name = scene_name
            else:
                tracker_name = meta["uuid"]
                base, ext = os.path.splitext(tracker_name)
                if ext.lower() in {".mkv", ".mp4", ".avi", ".ts"}:
                    tracker_name = base

        return tracker_name

    async def encode_to_base64(self, file_path: str) -> str:
        async with aiofiles.open(file_path, 'rb') as binary_file:
            binary_file_data = await binary_file.read()
            base64_encoded_data = base64.b64encode(binary_file_data)
            return base64_encoded_data.decode('utf-8')

    async def get_nfo(self, meta: Meta) -> Optional[str]:
        nfo_dir = os.path.join(meta['base_dir'], "tmp", meta['uuid'])
        nfo_files = glob.glob(os.path.join(nfo_dir, "*.nfo"))

        if nfo_files:
            nfo = await self.encode_to_base64(nfo_files[0])
            return nfo

        return None

    def get_requirements(self, meta: Meta) -> str:
        requirements_minimum = html_to_bbcode(meta.get("requirements_minimum", ""))
        requirements_recommended = html_to_bbcode(meta.get("requirements_recommended", ""))
        requirements = ""

        if requirements_minimum:
            requirements += requirements_minimum
        if requirements_recommended:
            requirements += f"\n{requirements_recommended}"

        requirements = re.sub(r"\[.+?\]", "", requirements)

        return requirements

    async def fetch_data(self, meta: Meta) -> dict[str, Any]:
        data: dict[str, Any] = {
            "coverPhotoUrl": str(meta.get("backdrop", "")),
            "description": str(meta.get("genres", "")),
            "name": await self.edit_name(meta),
            "nfo": await self.get_nfo(meta),
            "poster": str(meta.get("poster", "")),
            "technicalDetails": await self.edit_desc(meta),
            "screenshots": await self.get_screenshots(meta),
            "type": await self.get_cat_id(meta),
        }
        if meta["category"] in ("MOVIE", "TV"):
            media_info, bd_info = await self.get_file_info(meta)
            data["plot"] = (str(meta.get("overview_meta", "") or meta.get("overview", "")),)
            data["bdInfo"] = bd_info
            data["media_info"] = media_info
            data["url"] = str(cast(dict[str, Any], meta.get("imdb_info", {})).get("imdb_url", ""))

        elif meta["category"] == "GAME" and meta.get("console_game", False) is False:
            requirements = self.get_requirements(meta)
            if requirements:
                data["systemRequirements"] = requirements

        tracker_config = self.config.get("TRACKERS", {}).get(self.tracker, {})
        torrent_filename = await self.common.get_torrent_filename(meta, tracker_config)
        data["file"] = await self.encode_to_base64(f"{meta['base_dir']}/tmp/{meta['uuid']}/{torrent_filename}.torrent")
        if meta.get('debug') is True:
            data['file'] = str(data['file'])[:50] + '...[DEBUG MODE]'
            if data.get('nfo'):
                data['nfo'] = str(data['nfo'])[:50] + '...[DEBUG MODE]'

        return data

    async def upload(self, meta: Meta, _disctype: str) -> Optional[bool]:
        data = await self.fetch_data(meta)
        tracker_status = cast(dict[str, Any], meta.get('tracker_status', {}))
        tracker_status.setdefault(self.tracker, {})

        channel = await self.search_channel(meta)
        if channel is None:
            meta['skipping'] = f"{self.tracker}"
            return
        channel = str(channel)
        data['channel'] = channel

        torrent_id = ''

        if not bool(meta.get('debug')):
            response = None
            try:
                response = await self.session.post(url=self.upload_url, json=data, headers=self.session.headers)
                response.raise_for_status()
                response = response.json()
                if response.get('status') is True and response.get('error') is False:
                    tracker_status[self.tracker]['status_message'] = "Torrent uploaded successfully."

                    if 'downloadUrl' in response:
                        torrent_id = str(response.get('torrent', {}).get('id', ''))
                        if torrent_id:
                            tracker_status[self.tracker]['torrent_id'] = torrent_id

                        download_url = f"{self.url}/api/torrent/{torrent_id}/download"
                        await self.common.download_tracker_torrent(
                            meta,
                            tracker=self.tracker,
                            headers={'Authorization': str(self.config['TRACKERS'][self.tracker]['api_key'])},
                            downurl=download_url
                        )
                        return True

                    else:
                        tracker_status[self.tracker]['status_message'] = (
                            'data error: No downloadUrl in response, check manually if it uploaded. '
                            f'Response: \n{response}'
                        )
                        return False

                else:
                    tracker_status[self.tracker]['status_message'] = f'data error: {response}'
                    return False

            except httpx.HTTPStatusError as e:
                tracker_status[self.tracker]['status_message'] = f'data error: HTTP {e.response.status_code} - {e.response.text}'
                return False
            except httpx.TimeoutException:
                tracker_status[self.tracker]['status_message'] = f'data error: Request timed out after {self.session.timeout.write} seconds'
                return False
            except httpx.RequestError as e:
                response_info = "no response"
                if response is not None:
                    response_info = getattr(response, 'text', str(response))
                tracker_status[self.tracker]['status_message'] = f'data error: Unable to upload. Error: {e!r}.\nResponse: {response_info}'
                return False
            except Exception as e:
                response_info = "no response"
                if response is not None:
                    response_info = getattr(response, 'text', str(response))
                tracker_status[self.tracker]['status_message'] = f'data error: It may have uploaded, go check. Error: {e!r}.\nResponse: {response_info}'
                return False

        else:
            console.print("[cyan]SPD Request Data:")
            console.print(Redaction.redact_private_info(data))
            tracker_status[self.tracker]['status_message'] = "Debug mode enabled, not uploading."
            await self.common.create_torrent_for_upload(meta, f"{self.tracker}" + "_DEBUG", f"{self.tracker}" + "_DEBUG", announce_url="https://fake.tracker")
            return True  # Debug mode - simulated success
