# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import asyncio
import contextlib
import json
import re
import urllib.parse
from pathlib import Path
from typing import Any, cast

import aiofiles
import cli_ui
import httpx
from bs4 import BeautifulSoup
from pymediainfo import MediaInfo

from src.console import logger, prompt_in_thread
from src.cookie_auth import CookieAuthUploader, CookieValidator
from src.exceptions import *  # noqa F403
from src.meta import Meta
from src.trackers.common import Common


class AlphaRatio:
    """
    AR Private Torrent Tracker
    """

    auth_type = "cookies"
    tracker = "ALPHARATIO"
    display_name = "AlphaRatio"
    allows_bloated_audio = True
    source_flag = "AlphaRatio"
    base_url = "https://alpharatio.cc"
    banned_groups = ()
    login_url = f"{base_url}/login.php"
    upload_url = f"{base_url}/upload.php"
    search_url = f"{base_url}/torrents.php"
    test_url = f"{base_url}/torrents.php"
    torrent_url = f"{base_url}/torrents.php?id="
    supported_categories = ("TV", "MOVIE")
    tracker_urls = ("tracker.alpharatio",)

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.cookie_validator = CookieValidator(config)
        self.cookie_uploader = CookieAuthUploader(config)
        trackers_cfg = cast(dict[str, Any], self.config.get("TRACKERS", {}))
        ar_cfg = cast(dict[str, Any], trackers_cfg.get("ALPHARATIO", {}))
        self.username = str(ar_cfg.get("username", "")).strip()
        self.password = str(ar_cfg.get("password", "")).strip()

    async def get_type(self, meta: Meta) -> str:
        if (meta.type == "DISC" or meta.type == "REMUX") and meta.source == "Blu-ray":
            return "14"

        if meta.anime:
            if meta.sd:
                return "15"
            return {
                "8640p": "16",
                "4320p": "16",
                "2160p": "16",
                "1440p": "16",
                "1080p": "16",
                "1080i": "16",
                "720p": "16",
            }.get(meta.resolution, "15")

        if meta.category == "TV":
            if meta.tv_pack:
                if meta.sd:
                    return "4"
                return {
                    "8640p": "6",
                    "4320p": "6",
                    "2160p": "6",
                    "1440p": "5",
                    "1080p": "5",
                    "1080i": "5",
                    "720p": "5",
                }.get(meta.resolution, "4")
            if meta.sd:
                return "0"
            return {
                "8640p": "2",
                "4320p": "2",
                "2160p": "2",
                "1440p": "1",
                "1080p": "1",
                "1080i": "1",
                "720p": "1",
            }.get(meta.resolution, "0")

        if meta.category == "MOVIE":
            if meta.sd:
                return "7"
            if meta.adult_media:
                return "13"
            return {
                "8640p": "9",
                "4320p": "9",
                "2160p": "9",
                "1440p": "8",
                "1080p": "8",
                "1080i": "8",
                "720p": "8",
            }.get(meta.resolution, "7")

        return "7"

    async def validate_credentials(self, meta: Meta) -> bool:
        cookie_jar = await self.cookie_validator.load_session_cookies(meta, self.tracker)
        return cookie_jar is not None

    def get_links(self, movie: Meta, subheading: str, heading_end: str) -> str:
        description = ""
        description += "\n" + subheading + "Links" + heading_end + "\n"
        if "IMAGES" in self.config:
            if movie.imdb_id is not None and movie.imdb_id != 0:
                imdb_url = movie.imdb_info.get("imdb_url", "") if isinstance(movie.imdb_info, dict) else ""
                description += f"[url={imdb_url}][img]{self.config['IMAGES']['imdb_75']}[/img][/url]"
            if movie.tmdb != 0 and movie.tmdb:
                description += f" [url=https://www.themoviedb.org/{str(movie.category).lower()}/{movie.tmdb!s}][img]{self.config['IMAGES']['tmdb_75']}[/img][/url]"
            if movie.tvdb_id is not None and movie.tvdb_id != 0:
                description += f" [url=https://www.thetvdb.com/?id={movie.tvdb_id!s}&tab=series][img]{self.config['IMAGES']['tvdb_75']}[/img][/url]"
            if movie.tvmaze_id is not None and movie.tvmaze_id != 0:
                description += f" [url=https://www.tvmaze.com/shows/{movie.tvmaze_id!s}][img]{self.config['IMAGES']['tvmaze_75']}[/img][/url]"
            if movie.mal_id is not None and movie.mal_id != 0:
                description += f" [url=https://myanimelist.net/anime/{movie.mal_id!s}][img]{self.config['IMAGES']['mal_75']}[/img][/url]"
        else:
            if movie.imdb_id is not None and movie.imdb_id != 0:
                imdb_url = movie.imdb_info.get("imdb_url", "") if isinstance(movie.imdb_info, dict) else ""
                description += f"{imdb_url}"
            if movie.tmdb != 0 and movie.tmdb:
                description += f"\nhttps://www.themoviedb.org/{str(movie.category).lower()}/{movie.tmdb!s}"
            if movie.tvdb_id is not None and movie.tvdb_id != 0:
                description += f"\nhttps://www.thetvdb.com/?id={movie.tvdb_id!s}&tab=series"
            if movie.tvmaze_id is not None and movie.tvmaze_id != 0:
                description += f"\nhttps://www.tvmaze.com/shows/{movie.tvmaze_id!s}"
            if movie.mal_id is not None and movie.mal_id != 0:
                description += f"\nhttps://myanimelist.net/anime/{movie.mal_id!s}"
        return description

    async def edit_desc(self, meta: Meta) -> None:
        heading = "[color=green][size=6]"
        subheading = "[color=red][size=4]"
        heading_end = "[/size][/color]"
        from src.description_review import get_base_description

        base = get_base_description(meta)
        base = re.sub(r"\[center\]\[spoiler=Scene NFO:\].*?\[/center\]", "", base, flags=re.DOTALL)
        base = re.sub(r"\[center\]\[spoiler=FraMeSToR NFO:\].*?\[/center\]", "", base, flags=re.DOTALL)
        description = ""
        if meta.is_disc == "BDMV":
            description += heading + meta.name + heading_end + "\n" + self.get_links(meta, subheading, heading_end) + "\n\n" + subheading + "BDINFO" + heading_end + "\n"
        else:
            description += heading + meta.name + heading_end + "\n" + self.get_links(meta, subheading, heading_end) + "\n\n" + subheading + "MEDIAINFO" + heading_end + "\n"
        discs = cast(list[dict[str, Any]], meta.discs or [])
        if discs:
            if len(discs) >= 2:
                for each in discs[1:]:
                    if each["type"] == "BDMV":
                        description += f"[hide={each.get('name', 'BDINFO')}][code]{each['summary']}[/code][/hide]\n\n"
                    if each["type"] == "DVD":
                        description += f"{each['name']}:\n"
                        description += (
                            f"[hide={Path(each['vob']).name}][code]{each['vob_mi']}[/code][/hide] [hide={Path(each['ifo']).name}][code]{each['ifo_mi']}[/code][/hide]\n\n"
                        )
            # description += common.get_links(movie, "[COLOR=red][size=4]", "[/size][/color]")
            elif discs[0]["type"] == "DVD":
                description += f"[hide][code]{discs[0]['vob_mi']}[/code][/hide]\n\n"
            elif meta.is_disc == "BDMV":
                description += f"[hide][code]{discs[0]['summary']}[/code][/hide]\n\n"
        else:
            # Beautify MediaInfo for ALPHARATIO using custom template
            filelist = cast(list[str], meta.filelist or [])
            video = filelist[0] if filelist else str(meta.path or "")
            # using custom mediainfo template.
            # can not use full media info as sometimes its more than max chars per post.
            mi_template = str(Path(f"{meta.base_dir}/data/templates/summary-mediainfo.csv").resolve())
            if Path(mi_template).exists():
                media_info = await self.parse_mediainfo_async(video, mi_template)
                description += f"""[code]\n{media_info}\n[/code]\n"""
                # adding full mediainfo as spoiler
                async with aiofiles.open(f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/MEDIAINFO_CLEANPATH.txt", encoding="utf-8") as mi_file:
                    full_mediainfo = await mi_file.read()
                description += f"[hide=FULL MEDIAINFO][code]{full_mediainfo}[/code][/hide]\n"
            else:
                logger.info(f"{self.tracker}: [bold red]Couldn't find the MediaInfo template")
                logger.info(f"{self.tracker}: [green]Using normal MediaInfo for the description.")

                async with aiofiles.open(f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/MEDIAINFO_CLEANPATH.txt", encoding="utf-8") as mi_file:
                    cleaned_mediainfo = await mi_file.read()
                    description += f"""[code]\n{cleaned_mediainfo}\n[/code]\n\n"""

            description += "\n\n" + subheading + "PLOT" + heading_end + "\n" + meta.overview
            if meta.genres:
                description += "\n\n" + subheading + "Genres" + heading_end + "\n" + str(meta.genres)

            image_list = meta.image_list or []
            if image_list:
                description += "\n\n" + subheading + "Screenshots" + heading_end + "\n"
                description += "[align=center]"
                for image in image_list:
                    if image["raw_url"] is not None:
                        description += "[url=" + image["raw_url"] + "][img]" + image["img_url"] + "[/img][/url]"
                description += "[/align]"
            if "youtube" in meta:
                description += "\n\n" + subheading + "Youtube" + heading_end + "\n" + str(meta.youtube)

            # adding extra description if passed
            if len(base) > 2:
                description += "\n\n" + subheading + "Notes" + heading_end + "\n" + base

        async with aiofiles.open(f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/[{self.tracker}]DESCRIPTION.txt", "w", encoding="utf8") as descfile:
            await descfile.write(description)
        return

    async def get_language_tag(self, meta: Meta) -> str:
        lang_tag = ""
        has_eng_audio = False
        audio_lang = ""
        if meta.is_disc != "BDMV":
            try:
                async with aiofiles.open(f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/MediaInfo.json", encoding="utf-8") as f:
                    mi_content = await f.read()
                    mi = json.loads(mi_content)
                for track in mi["media"]["track"]:
                    if track["@type"] == "Audio":
                        if track.get("Language", "None").startswith("en"):
                            has_eng_audio = True
                        if not has_eng_audio:
                            audio_lang = mi["media"]["track"][2].get("Language_String", "").upper()
            except Exception as e:
                logger.error(f"{self.tracker}: [red]Error: {e}")
        else:
            for audio in meta.bdinfo["audio"]:
                if audio["language"] == "English":
                    has_eng_audio = True
                if not has_eng_audio:
                    audio_lang = meta.bdinfo["audio"][0]["language"].upper()
        if audio_lang != "":
            lang_tag = audio_lang
        return lang_tag

    async def get_basename(self, meta: Meta) -> str:
        filelist = cast(list[str], meta.filelist or [])
        path = filelist[0] if filelist else str(meta.path or "")
        return Path(path).name

    async def search_existing(self, meta: Meta) -> list[dict[str, str]]:
        dupes: list[dict[str, str]] = []
        cookie_jar = await self.cookie_validator.load_session_cookies(meta, self.tracker)
        if not cookie_jar:
            logger.info(f"{self.tracker}: Cannot search without valid cookies.")
            return dupes

        # Combine title and year
        title = meta.title.strip()
        year = str(meta.year).strip() if meta.year is not None else ""
        if not title:
            logger.info(f"{self.tracker}: [red]Title is missing.")
            return dupes

        search_query = f"{title} {year}".strip()
        search_query_encoded = urllib.parse.quote(search_query)
        search_url = f"{self.base_url}/ajax.php?action=browse&searchstr={search_query_encoded}"

        logger.debug(f"{self.tracker}: [blue]{search_url}")

        headers = {"User-Agent": f"{meta.ua_name} {(meta.current_version if meta.current_version is not None else 'github.com/wastaken7/Upload-Assistant')}"}

        async with httpx.AsyncClient(headers=headers, timeout=30.0, cookies=cookie_jar) as client:
            response = await client.get(search_url)
            response.raise_for_status()

            if "login.php" in str(response.url) or "login.php" in response.text:
                await self.cookie_validator.handle_validation_failure(meta, self.tracker, response.text)
                meta.skipping = f"{self.tracker}"
                return dupes

            json_response = response.json()
            if json_response.get("status") != "success":
                raise RuntimeError(f"{self.tracker}: API returned unsuccessful status: {json_response.get('error', 'unknown error')}")

            results = json_response.get("response", {}).get("results", [])
            if not results:
                return dupes

            for res in results:
                if "groupName" in res:
                    dupe = {
                        "name": res["groupName"],
                        "size": res["size"],
                        "files": res["groupName"],
                        "file_count": res["fileCount"],
                        "link": f"{self.search_url}?id={res['groupId']}&torrentid={res['torrentId']}",
                        "download": f"{self.base_url}/torrents.php?action=download&id={res['torrentId']}",
                    }
                    dupes.append(dupe)

            return dupes

    async def get_auth_key(self, meta: Meta) -> str | None:
        """Retrieve the saved auth key from cookie_auth.py."""
        auth_key = await self.cookie_validator.get_ar_auth_key(meta, self.tracker)
        if auth_key:
            return auth_key

        logger.info(f"{self.tracker}: [yellow]Auth key not found. This may happen if you're using manually exported cookies.[/yellow]")
        logger.info(f"{self.tracker}: [yellow]Attempting to extract auth key from torrents page...[/yellow]")

        # Fallback: extract from torrents page if not saved
        cookie_jar = await self.cookie_validator.load_session_cookies(meta, self.tracker)
        if not cookie_jar:
            return None

        headers = {"User-Agent": f"{meta.ua_name} {(meta.current_version if meta.current_version is not None else 'github.com/wastaken7/Upload-Assistant')}"}

        try:
            async with httpx.AsyncClient(headers=headers, timeout=30.0, cookies=cookie_jar) as client:
                response = await client.get(self.test_url)
                soup = BeautifulSoup(response.text, "html.parser")
                logout_link = soup.find("a", href=True, text="Logout")

                if logout_link:
                    href_value = logout_link.get("href")
                    match = re.search(r"auth=([^&]+)", href_value) if isinstance(href_value, str) else None
                    if match:
                        auth_key = match.group(1)
                        # Save it for next time
                        from src.cookie_auth import find_cookie_file

                        cookie_file = find_cookie_file(meta.base_dir, self.tracker, self.config)
                        auth_file = cookie_file.replace(".txt", "_auth.txt")
                        with contextlib.suppress(Exception):
                            async with aiofiles.open(auth_file, "w", encoding="utf-8") as f:
                                await f.write(auth_key)
                            logger.info(f"{self.tracker}: [green]Auth key saved for future use[/green]")
                        return auth_key
        except Exception as e:
            logger.error(f"{self.tracker}: [red]Error extracting auth key: {e}")

        return None

    async def upload(self, meta: Meta) -> bool:
        """Upload torrent to ALPHARATIO using centralized cookie_upload."""
        # Prepare the data for the upload
        common = Common(config=self.config)
        await common.create_torrent_for_upload(meta, self.tracker, self.source_flag)
        await self.edit_desc(meta)
        type_id = await self.get_type(meta)

        # Read the description
        desc_path = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/[{self.tracker}]DESCRIPTION.txt"
        try:
            async with aiofiles.open(desc_path, encoding="utf-8") as desc_file:
                desc = await desc_file.read()
        except FileNotFoundError:
            meta.tracker_status[self.tracker]["status_message"] = f"data error: Description file not found at {desc_path}"
            return False

        # Handle cover image input
        imdb_info = cast(dict[str, Any], meta.imdb_info or {})
        cover = meta.artwork_url or imdb_info.get("cover", None)
        if cover is None:
            if meta.unattended and not meta.unattended_confirm:
                logger.info(f"{self.tracker}: [yellow]Unattended mode: No cover image found. Skipping {self.tracker} upload.[/yellow]")
                meta.skipping = f"{self.tracker}"
                return False
            while cover is None:
                cover = await prompt_in_thread(cli_ui.ask_string, "No Cover was found. Please input a link to a cover:", default="") or ""
                if not re.match(r"https?://.*\.(jpg|png|gif)$", cover):
                    logger.info(f"{self.tracker}: [red]Invalid image link. Please enter a link that ends with .jpg, .png, or .gif.")
                    cover = None

        # Tag Compilation
        genres_raw = meta.genres
        genres = ""
        if isinstance(genres_raw, list):
            tags_parts = [str(item).strip() for item in genres_raw if str(item).strip()]
            genres = ", ".join(tags_parts)
        elif isinstance(genres_raw, str) and genres_raw.strip():
            tags_parts: list[str] = []
            for item in genres_raw.split(","):
                for subitem in item.split("&"):
                    stripped = subitem.strip()
                    if stripped:
                        tags_parts.append(stripped)
            genres = ", ".join(tags_parts)
        genres = re.sub(r"\.{2,}", ".", genres)

        # adding tags
        tags = ""
        if meta.imdb_id != 0:
            tags += f"tt{meta.imdb}, "
        if genres:
            tags += f"{genres}, "

        # Get auth key
        auth_key = await self.get_auth_key(meta)
        if not auth_key:
            meta.tracker_status[self.tracker]["status_message"] = "data error: Failed to extract auth key"
            return False

        # Prepare upload data
        data: dict[str, Any] = {
            "submit": "true",
            "auth": auth_key,
            "type": type_id,
            "title": await self.get_name(meta),
            "tags": tags,
            "image": cover,
            "desc": desc,
        }

        # Load cookies for upload
        upload_cookies = await self.cookie_validator.load_session_cookies(meta, self.tracker)
        if not upload_cookies:
            meta.tracker_status[self.tracker]["status_message"] = "data error: Failed to load cookies for upload"
            return False

        # Use centralized handle_upload from CookieAuthUploader
        return await self.cookie_uploader.handle_upload(
            meta=meta,
            tracker=self.tracker,
            data=data,
            upload_cookies=upload_cookies,
            upload_url=self.upload_url,
            torrent_field_name="file_input",
            source_flag=self.source_flag,
            torrent_url=self.torrent_url,
            id_pattern=r"torrents\.php\?id=(\d+)",
            success_status_code="200",
        )

    async def parse_mediainfo_async(self, video_path: str, template_path: str) -> str:
        """Parse MediaInfo asynchronously using thread executor"""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: MediaInfo.parse(video_path, output="STRING", full=False, mediainfo_options={"inform": f"file://{template_path}"}))

    async def get_name(self, meta: Meta) -> str:
        # must use scene name if scene release
        known_extensions = {".mkv", ".mp4", ".avi", ".ts"}
        if meta.scene:
            ar_name = meta.scene_name or ""
        else:
            ar_name = meta.uuid
            p = Path(ar_name)
            base, ext = p.stem, p.suffix
            if ext.lower() in known_extensions:
                ar_name = base
            ar_name = (
                ar_name.replace(" ", ".")
                .replace("'", "")
                .replace(":", "")
                .replace("(", ".")
                .replace(")", ".")
                .replace("[", ".")
                .replace("]", ".")
                .replace("{", ".")
                .replace("}", ".")
            )
            ar_name = re.sub(r"\.{2,}", ".", ar_name)

        tag_lower = "" if not meta.tag else meta.tag.lower()
        invalid_tags = ["nogrp", "nogroup", "unknown", "-unk-"]
        if meta.tag == "" or any(invalid_tag in tag_lower for invalid_tag in invalid_tags):
            for invalid_tag in invalid_tags:
                ar_name = re.sub(f"-{invalid_tag}", "", ar_name, flags=re.IGNORECASE)
            ar_name = f"{ar_name}-NoGRP"

        return ar_name
