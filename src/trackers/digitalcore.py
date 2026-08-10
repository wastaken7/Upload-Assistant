# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import unicodedata
from typing import Any, cast

import aiofiles
import httpx

from src.cogs.redaction import Redaction
from src.console import logger
from src.get_desc import DescriptionBuilder
from src.meta import Meta
from src.rehostimages import ImageHostPolicy, RehostImagesManager
from src.trackers.common import Common

Config = dict[str, Any]


class DigitalCore:
    """
    DIGITALCORE (DC) is a Private Torrent Tracker for 0DAY / GENERAL
    """

    auth_type = "other_api"
    tracker = "DIGITALCORE"
    display_name = "DigitalCore"
    base_url = "https://digitalcore.club"
    api_base_url = f"{base_url}/api/v1/torrents"
    banned_groups = ("",)
    approved_image_hosts = ("imgbox", "imgbb", "bhd", "imgur", "postimg", "sharex")
    image_host_policy = ImageHostPolicy(
        {
            "ibb.co": "imgbb",
            "imgbox.com": "imgbox",
            "beyondhd.co": "bhd",
            "imgur.com": "imgur",
            "postimg.cc": "postimg",
            "digitalcore.club": "sharex",
            "img.digitalcore.club": "sharex",
        },
        approved_image_hosts,
    )
    torrent_url = f"{base_url}/torrent/"
    supported_categories = ("TV", "MOVIE", "BOOK", "GAME", "MUSIC")
    tracker_urls = ("tracker.digitalcore.club", "trackerprxy.digitalcore.club")
    allows_bloated_audio = True

    def __init__(self, config: Config):
        self.config = config
        self.common = Common(config)
        self.rehost_images_manager = RehostImagesManager(config)
        self.api_key = self.config["TRACKERS"][self.tracker].get("api_key")
        self.session = httpx.AsyncClient(headers={"X-API-KEY": self.api_key}, timeout=30.0)

    async def mediainfo(self, meta: Meta) -> str:
        mediainfo = ""
        if meta.category in ("TV", "MOVIE", "MUSIC") or meta.audiobook:
            if meta.is_disc == "BDMV":
                mediainfo = await self.common.get_bdmv_mediainfo(meta, remove=["File size", "Overall bit rate"])
            else:
                mi_path = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/MEDIAINFO_CLEANPATH.txt"
                async with aiofiles.open(mi_path, encoding="utf-8") as f:
                    mediainfo = await f.read()

        return mediainfo

    async def generate_description(self, meta: Meta) -> str:
        builder = DescriptionBuilder(self.tracker, self.config)
        return await builder.general_description_generator(
            meta,
            approved_image_hosts=self.approved_image_hosts,
            audio_spectrogram=True,
            bluray=False,
            book=True,
            custom_header=True,
            custom_signature=False,
            description=True,
            game=True,
            languages=False,
            logo=False,
            mediainfo=True,
            menu_screenshots=True,
            music=True,
            nfo=True,
            screenshots=True,
            tonemapped_header=True,
            tv_info=True,
            ua_signature=True,
            user_description=True,
            signature=f"[center][url=https://github.com/wastaken7/Upload-Assistant]{meta.ua_signature}[/url][/center]",
        )

    def get_category_id(self, meta: Meta) -> int | None:
        resolution = meta.resolution
        category = meta.category
        is_disc = meta.is_disc
        tv_pack = meta.tv_pack
        sd = meta.sd

        if is_disc == "BDMV":
            if resolution == "1080p" and category == "MOVIE":
                return 3
            if resolution == "2160p" and category == "MOVIE":
                return 38
            if category == "TV":
                return 14
        if is_disc == "DVD":
            if category == "MOVIE":
                return 1
            if category == "TV":
                return 11
        if category == "TV" and tv_pack == 1:
            return 12

        if category == "BOOK":
            if meta.audiobook:
                return 44
            return 28

        if category == "GAME":
            platform = meta.platform
            if platform == "PC":
                return 25
            if platform == "MAC":
                return 27
            return 26  # Console

        if category == "MUSIC":
            if meta.format.upper() == "FLAC":
                return 23
            if meta.format.upper() == "MP3":
                return 22

        if sd == 1:
            if category == "MOVIE":
                return 2
            if category == "TV":
                return 10
        category_map = {
            "MOVIE": {"2160p": 4, "1080p": 6, "1080i": 6, "720p": 5},
            "TV": {"2160p": 13, "1080p": 9, "1080i": 9, "720p": 8},
        }
        if category in category_map:
            return category_map[category].get(resolution)
        return None

    async def search_existing(self, meta: Meta) -> list[dict[str, Any]]:
        imdb_id = meta.imdb_info.get("imdbID")
        category_id = self.get_category_id(meta)

        search_params = {"search": meta.title}
        if imdb_id:
            search_params = {"searchText": imdb_id}

        search_results: list[Any] = []
        dupes: list[dict[str, Any]] = []
        response = await self.session.get(self.api_base_url, params=search_params, headers=self.session.headers, timeout=15)
        response.raise_for_status()

        if response.text and response.text != "[]":
            json_data = response.json()
            if isinstance(json_data, list):
                search_results = json_data
            for each in search_results:
                if not isinstance(each, dict):
                    continue
                each_dict = cast(dict[str, Any], each)
                if each_dict.get("category") == category_id:
                    name = each_dict.get("name")
                    torrent_id = each_dict.get("id")
                    size = each_dict.get("size")
                    torrent_link = f"{self.torrent_url}{torrent_id}/" if torrent_id else None
                    numfiles = each_dict.get("numfiles", "")
                    dupe_entry: dict[str, Any] = {
                        "id": torrent_id,
                        "download": f"{self.api_base_url}/download/{torrent_id}",
                        "file_count": numfiles,
                        "name": name,
                        "size": size,
                        "link": torrent_link,
                    }
                    dupes.append(dupe_entry)

            return dupes

        return []

    async def get_name(self, meta: Meta) -> str:
        """
        Edits the name according to DIGITALCORE's naming conventions.
        Scene uploads should use the scene name.
        Scene uploads should also have "[UNRAR]" in the name, as the UA only uploads unzipped files, which are considered "altered".
        https://digitalcore.club/forum/17/topic/1051/uploading-for-beginners

        Mod mentioned that adding [UNRAR] is unnecessary, but according to my tests, their system does not accept it if there is already a release with the same title.
        Mod also mentioned that metadata-based titles are acceptable.
        https://digitalcore.club/forum/6/topic/2810/clarification-needed-p2p-non-scene-torrent-naming-conventions
        """
        tracker_name = meta.basename_no_ext
        scene_name = meta.scene_name or ""

        use_metadata_name = self.config["TRACKERS"][self.tracker].get("use_metadata_name", False)
        if use_metadata_name:
            clean_name = meta.clean_name or ""
            tracker_name = scene_name if scene_name else clean_name
            # T1)  Acceptable characters are as follows:
            #         ABCDEFGHIJKLMNOPQRSTUVWXYZ
            #         abcdefghijklmnopqrstuvwxyz
            #         0123456789 . -
            # https://scenerules.org/html/2014_BLURAY.html
            tracker_name = tracker_name.replace("DD+", "DDP").replace("DTS:", "DTS-").replace("HDR10+", "HDR10P")
            tracker_name = unicodedata.normalize("NFD", tracker_name)
            tracker_name = "".join(c for c in tracker_name if c.isascii() and (c.isalnum() or c in (" ", ".", "-")))
            tracker_name = tracker_name.replace("!", "")
            if scene_name:
                tracker_name += " [UNRAR]"

        else:
            tracker_name = f"{scene_name} [UNRAR]" if scene_name else meta.basename_no_ext

        return tracker_name

    async def get_firstpic(self, meta: Meta) -> str:
        if meta.category in ("BOOK", "MUSIC"):
            covers = meta.hosted_artwork
            if isinstance(covers, list) and len(covers) > 0:
                raw_url = covers[0].get("raw_url")
                if raw_url:
                    return str(raw_url)
        return ""

    async def fetch_data(self, meta: Meta) -> dict[str, Any]:
        anon = "1" if meta.anon or self.config["TRACKERS"][self.tracker].get("anon", False) else "0"

        return {
            "category": self.get_category_id(meta),
            "imdbId": meta.imdb_tt,
            "nfo": await self.generate_description(meta),
            "mediainfo": await self.mediainfo(meta),
            "reqid": "0",
            "section": "new",
            "frileech": "1",
            "anonymousUpload": anon,
            "p2p": "0",
            "unrar": "1",
            "firstpic": await self.get_firstpic(meta),
            "language": meta.book_language,
        }

    async def upload(self, meta: Meta) -> bool:
        data = await self.fetch_data(meta)
        torrent_title = await self.get_name(meta)
        response = None

        if not meta.debug:
            try:
                upload_url = f"{self.api_base_url}/upload"
                await self.common.create_torrent_for_upload(meta, self.tracker, "DigitalCore.club")
                torrent_path = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/[{self.tracker}].torrent"

                async with aiofiles.open(torrent_path, "rb") as torrent_file:
                    torrent_bytes = await torrent_file.read()
                files = {"file": (torrent_title + ".torrent", torrent_bytes, "application/x-bittorrent")}

                response = await self.session.post(upload_url, data=data, files=files, headers=dict(self.session.headers), timeout=90)
                response.raise_for_status()
                response_json = response.json()
                response_data: dict[str, Any] = cast(dict[str, Any], response_json) if isinstance(response_json, dict) else {}

                if response.status_code == 200 and response_data.get("id"):
                    torrent_id = str(response_data["id"])
                    meta.tracker_status[self.tracker]["torrent_id"] = torrent_id + "/"
                    meta.tracker_status[self.tracker]["status_message"] = response_data.get("message")

                    await self.common.download_tracker_torrent(meta, self.tracker, headers=dict(self.session.headers), downurl=f"{self.api_base_url}/download/{torrent_id}")
                    return True

                meta.tracker_status[self.tracker]["status_message"] = f"data error: {response_data.get('message', 'Unknown API error.')}"
                return False

            except httpx.HTTPStatusError as e:
                meta.tracker_status[self.tracker]["status_message"] = f"data error: HTTP {e.response.status_code} - {e.response.text}"
                return False
            except httpx.TimeoutException:
                meta.tracker_status[self.tracker]["status_message"] = f"data error: Request timed out after {self.session.timeout.write} seconds"
                return False
            except httpx.RequestError as e:
                resp_text = getattr(getattr(e, "response", None), "text", "No response received")
                meta.tracker_status[self.tracker]["status_message"] = f"data error: Unable to upload. Error: {e}.\nResponse: {resp_text}"
                return False
            except Exception as e:
                resp_text = response.text if response is not None else "No response received"
                meta.tracker_status[self.tracker]["status_message"] = f"data error: It may have uploaded, go check. Error: {e}.\nResponse: {resp_text}"
                return False

        else:
            logger.info(f"{self.tracker}: Request Data:")
            logger.info(Redaction.redact_private_info(data))
            meta.tracker_status[self.tracker]["status_message"] = "Debug mode enabled, not uploading"
            await self.common.create_torrent_for_upload(meta, f"{self.tracker}" + "_DEBUG", f"{self.tracker}" + "_DEBUG", announce_url="https://fake.tracker")
            return True  # Debug mode - simulated success
