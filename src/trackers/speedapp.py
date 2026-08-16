# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import base64
import re
import unicodedata
from pathlib import Path
from typing import Any, cast

import aiofiles
import httpx
from rich.markup import escape

from src.cogs.redaction import Redaction
from src.console import console, logger
from src.get_desc import DescriptionBuilder, html_to_bbcode
from src.languages import languages_manager
from src.meta import Meta
from src.trackers.common import Common

Config = dict[str, Any]


class SpeedApp:
    """
    SPD Private Torrent Tracker
    """

    base_url = "https://speedapp.io"

    auth_type = "other_api"
    url = f"{base_url}"
    tracker = "SPEEDAPP"
    display_name = "SpeedApp"
    banned_groups = ()
    upload_url = f"{base_url}/api/upload"
    torrent_url = f"{base_url}/browse/"
    banned_url = f"{base_url}/api/torrent/release-group/blacklist"
    supported_categories = ("TV", "MOVIE", "BOOK", "GAME", "MUSIC")
    tracker_urls = ("speedapp",)
    allowed_bloated_audio_languages = ("ro",)

    def __init__(self, config: Config) -> None:
        self.config: Config = config
        self.common = Common(config)
        api_key = str(self.config["TRACKERS"][self.tracker]["api_key"])
        self.session = httpx.AsyncClient(
            headers={
                "User-Agent": "Upload-Assistant",
                "accept": "application/json",
                "Authorization": api_key,
            },
            timeout=30.0,
        )

    async def get_cat_id(self, meta: Meta) -> int:
        if not meta.language_checked:
            await languages_manager.process_desc_language(meta, tracker=self.tracker)

        subtitle_langs = cast(list[Any], meta.subtitle_languages or [])
        audio_langs = cast(list[Any], meta.audio_languages or [])
        langs = [str(lang).lower() for lang in (subtitle_langs + audio_langs)]
        romanian = "romanian" in langs

        origin_countries = meta.origin_country
        category = str(meta.category)
        if "RO" in origin_countries:
            if category == "TV":
                return 60
            if category == "MOVIE":
                return 59

        # documentary
        genres = str(meta.genres)
        keywords = str(meta.keywords)
        if "documentary" in genres.lower() or "documentary" in keywords.lower():
            return 63 if romanian else 9

        # anime
        if meta.anime:
            return 3

        # TV
        if category == "TV":
            if meta.tv_pack:
                return 66 if romanian else 41
            if meta.sd:
                return 46 if romanian else 45
            return 44 if romanian else 43

        # MOVIE
        if category == "MOVIE":
            resolution = meta.resolution
            media_type = str(meta.type)
            if resolution == "2160p" and media_type != "DISC":
                return 57 if romanian else 61
            if media_type in ("REMUX", "WEBDL", "WEBRIP", "HDTV", "ENCODE"):
                return 29 if romanian else 8
            if media_type == "DISC":
                return 24 if romanian else 17
            if media_type == "SD":
                return 35 if romanian else 10

        # BOOK/EBOOK category
        if category == "BOOK":
            return 6

        # Game
        if category == "GAME":
            if meta.console_game:
                return 52
            return 11

        if category == "MUSIC":
            return 5

        return 0

    async def get_file_info(self, meta: Meta) -> tuple[str | None, str | None]:
        base_path = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}"
        if meta.bdinfo:
            async with aiofiles.open(
                f"{base_path}/BD_SUMMARY_00.txt",
                encoding="utf-8",
            ) as bd_file:
                bd_info = await bd_file.read()
            return None, bd_info
        async with aiofiles.open(
            f"{base_path}/MEDIAINFO_CLEANPATH.txt",
            encoding="utf-8",
        ) as mi_file:
            media_info = await mi_file.read()
        return media_info, None

    async def get_screenshots(self, meta: Meta) -> list[str]:
        images = cast(list[dict[str, Any]], meta.menu_images) + meta.image_list + meta.spectrograms_images + meta.dynamic_hdr_plot_images
        return [image["raw_url"] for image in images if image.get("raw_url")]

    async def search_existing(self, meta: Meta) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        search_url = f"{self.base_url}/api/torrent"

        params: dict[str, str] = {}
        if meta.imdb_id:
            params["imdbId"] = meta.imdb_tt
        else:
            search_title = meta.title
            if meta.category == "MUSIC":
                search_title = f"{meta.artist} {meta.title}"
            search_title = search_title.replace(":", "").replace("'", "").replace(",", "")
            params["search"] = search_title

        response = await self.session.get(url=search_url, params=params, headers=self.session.headers)
        response.raise_for_status()

        data = cast(list[dict[str, Any]], response.json())
        for each in data:
            name = each.get("name")
            size = each.get("size")
            link = f"{self.torrent_url}{each.get('id')}/"

            if name:
                results.append({"name": str(name), "size": size, "link": link})
        return results

    async def search_channel(self, meta: Meta) -> int | None:
        spd_channel = meta.spd_channel or self.config["TRACKERS"][self.tracker].get("channel", "")

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
            pass

        params: dict[str, str] = {"search": str(spd_channel)}

        try:
            response = await self.session.get(url=self.url + "/api/channel", params=params, headers=self.session.headers)

            if response.status_code == 200:
                data = cast(list[dict[str, Any]], response.json())
                for entry in data:
                    channel_id = entry.get("id")
                    tag = entry.get("tag")

                    if channel_id and tag and tag == spd_channel:
                        return int(channel_id)
                logger.info(f"{self.tracker}: [{self.tracker}]Could not find the channel ID matching your input. Please check if you entered it correctly.")
                return None
            logger.info(f"{self.tracker}: [bold red]HTTP request failed. Status: {response.status_code}[/bold red]")
            return None

        except Exception as e:
            logger.error(f"{self.tracker}: [bold red]Unexpected error: {escape(str(e))}[/bold red]")
            console.print_exception()
            return None

    async def edit_desc(self, meta: Meta) -> str:
        builder = DescriptionBuilder(self.tracker, self.config)

        return await builder.general_description_generator(
            meta,
            audio_spectrogram=False,
            bluray=False,
            book=False,
            custom_signature=False,
            description=False,
            game=False,
            mediainfo=False,
            menu_screenshots=False,
            nfo=False,
            screenshots=False,
            signature=f"\n[url=https://github.com/wastaken7/Upload-Assistant]{meta.ua_signature}[/url]",
        )

    async def get_name(self, meta: Meta) -> str:
        tracker_name = meta.basename_no_ext
        scene_name = meta.scene_name or ""

        use_metadata_name = self.config["TRACKERS"][self.tracker].get("use_metadata_name", False)
        if use_metadata_name:
            clean_name = meta.clean_name or ""
            tracker_name = scene_name if scene_name else clean_name
            tracker_name = tracker_name.replace("DD+", "DDP").replace("DTS:", "DTS-").replace("HDR10+", "HDR10P")
            tracker_name = unicodedata.normalize("NFD", tracker_name)
            tracker_name = "".join(c for c in tracker_name if c.isascii() and (c.isalnum() or c in (" ", ".", "-")))
            tracker_name = tracker_name.replace("!", "")

        else:
            tracker_name = scene_name or meta.basename_no_ext

        return tracker_name

    async def encode_to_base64(self, file_path: str) -> str:
        async with aiofiles.open(file_path, "rb") as binary_file:
            binary_file_data = await binary_file.read()
            base64_encoded_data = base64.b64encode(binary_file_data)
            return base64_encoded_data.decode("utf-8")

    async def get_nfo(self, meta: Meta) -> str | None:
        nfo_dir = Path(meta.base_dir) / "tmp" / meta.uuid
        nfo_files = list(nfo_dir.glob("*.nfo"))

        if nfo_files:
            return await self.encode_to_base64(str(nfo_files[0]))

        return None

    def get_requirements(self, meta: Meta) -> str:
        requirements_minimum = html_to_bbcode(meta.requirements_minimum)
        requirements_recommended = html_to_bbcode(meta.requirements_recommended)
        requirements = ""

        if requirements_minimum:
            requirements += requirements_minimum
        if requirements_recommended:
            requirements += f"\n{requirements_recommended}"

        return re.sub(r"\[.+?\]", "", requirements)

    async def fetch_data(self, meta: Meta) -> dict[str, Any]:
        data: dict[str, Any] = {
            "coverPhotoUrl": meta.backdrop,
            "description": str(meta.genres),
            "name": await self.get_name(meta),
            "nfo": await self.get_nfo(meta),
            "poster": meta.artwork_url,
            "technicalDetails": await self.edit_desc(meta),
            "screenshots": await self.get_screenshots(meta),
            "type": await self.get_cat_id(meta),
        }
        if meta.category in ("MOVIE", "TV"):
            media_info, bd_info = await self.get_file_info(meta)
            data["plot"] = (meta.overview_meta or meta.overview,)
            data["bdInfo"] = bd_info
            data["media_info"] = media_info
            data["url"] = str(cast(dict[str, Any], meta.imdb_info).get("imdb_url", ""))

        elif meta.category == "GAME" and meta.console_game is False:
            requirements = self.get_requirements(meta)
            if requirements:
                data["systemRequirements"] = requirements

        tracker_config = self.config.get("TRACKERS", {}).get(self.tracker, {})
        torrent_filename = await self.common.get_torrent_filename(meta, tracker_config)
        data["file"] = await self.encode_to_base64(f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/{torrent_filename}.torrent")
        if meta.debug is True:
            data["file"] = data["file"][:50] + "...[DEBUG MODE]"
            if data.get("nfo"):
                data["nfo"] = str(data["nfo"])[:50] + "...[DEBUG MODE]"

        return data

    async def upload(self, meta: Meta) -> bool | None:
        data = await self.fetch_data(meta)
        tracker_status = meta.tracker_status
        tracker_status.setdefault(self.tracker, {})

        channel = await self.search_channel(meta)
        if channel is None:
            meta.skipping = f"{self.tracker}"
            return None
        channel = str(channel)
        data["channel"] = channel

        torrent_id = ""

        if not meta.debug:
            response = None
            try:
                response = await self.session.post(url=self.upload_url, json=data, headers=self.session.headers)
                response.raise_for_status()
                response = response.json()
                if response.get("status") is True and response.get("error") is False:
                    tracker_status[self.tracker]["status_message"] = "Torrent uploaded successfully."

                    if "downloadUrl" in response:
                        torrent_id = str(response.get("torrent", {}).get("id", ""))
                        if torrent_id:
                            tracker_status[self.tracker]["torrent_id"] = torrent_id

                        download_url = f"{self.url}/api/torrent/{torrent_id}/download"
                        await self.common.download_tracker_torrent(
                            meta, tracker=self.tracker, headers={"Authorization": str(self.config["TRACKERS"][self.tracker]["api_key"])}, downurl=download_url
                        )
                        return True

                    tracker_status[self.tracker]["status_message"] = f"data error: No downloadUrl in response, check manually if it uploaded. Response: \n{response}"
                    return False

                tracker_status[self.tracker]["status_message"] = f"data error: {response}"
                return False

            except httpx.HTTPStatusError as e:
                tracker_status[self.tracker]["status_message"] = f"data error: HTTP {e.response.status_code} - {e.response.text}"
                return False
            except httpx.TimeoutException:
                tracker_status[self.tracker]["status_message"] = f"data error: Request timed out after {self.session.timeout.write} seconds"
                return False
            except httpx.RequestError as e:
                response_info = "no response"
                if response is not None:
                    response_info = getattr(response, "text", str(response))
                tracker_status[self.tracker]["status_message"] = f"data error: Unable to upload. Error: {e!r}.\nResponse: {response_info}"
                return False
            except Exception as e:
                response_info = "no response"
                if response is not None:
                    response_info = getattr(response, "text", str(response))
                tracker_status[self.tracker]["status_message"] = f"data error: It may have uploaded, go check. Error: {e!r}.\nResponse: {response_info}"
                return False

        else:
            logger.info(f"{self.tracker}: Request Data:")
            logger.info(Redaction.redact_private_info(data))
            tracker_status[self.tracker]["status_message"] = "Debug mode enabled, not uploading."
            await self.common.create_torrent_for_upload(meta, f"{self.tracker}" + "_DEBUG", f"{self.tracker}" + "_DEBUG", announce_url="https://fake.tracker")
            return True  # Debug mode - simulated success
