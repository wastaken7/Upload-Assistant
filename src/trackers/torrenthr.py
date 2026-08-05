# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import asyncio
import contextlib
import json
import platform
import re
from pathlib import Path
from typing import Any, cast

import aiofiles
import cli_ui
import httpx
from bs4 import BeautifulSoup
from bs4.element import AttributeValueList
from unidecode import unidecode

from src.bbcode import BBCODE
from src.cogs.redaction import Redaction
from src.console import console, logger
from src.meta import Meta
from src.temp_paths import screenshots_dir
from src.trackers.common import Common

Config = dict[str, Any]


class TorrentHR:
    """
    TORRENTHR is a ratioless CROATIAN Private Torrent Tracker for 0DAY / GENERAL
    """

    base_url = "https://www.torrenthr.org"

    tracker = "TORRENTHR"
    display_name = "TorrentHR"
    allows_bloated_audio = True
    source_flag = f"[{base_url}] TorrentHR.org"
    banned_groups = ("",)
    supported_categories = ("TV", "MOVIE")
    tracker_urls = ("torrenthr",)

    def __init__(self, config: Config) -> None:
        self.config: Config = config
        self.username = str(config["TRACKERS"][self.tracker].get("username", ""))
        self.password = str(config["TRACKERS"][self.tracker].get("password", ""))

    async def upload(self, meta: Meta) -> bool | None:
        common = Common(config=self.config)
        await common.create_torrent_for_upload(meta, self.tracker, self.source_flag)
        cat_id = await self.get_cat_id(meta)
        subs = self.get_subtitles(meta)
        await self.edit_desc(meta)
        thr_name = await self.get_name(meta)
        torrent_name = re.sub(r"[^0-9a-zA-Z. '\-\[\]]+", " ", thr_name)

        mi_file: bytes = b""

        if (meta.is_disc) == "BDMV":
            mi_file = b""
            # bd_file = f"{meta.base_dir}/tmp/{meta.uuid}/BD_SUMMARY_00.txt", 'r', encoding='utf-8'
        else:
            mi_file_path = str(Path(f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/MEDIAINFO_CLEANPATH.txt").resolve())
            async with aiofiles.open(mi_file_path, "rb") as f:
                mi_file = await f.read()
            # bd_file = None

        async with aiofiles.open(
            f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/[TORRENTHR]DESCRIPTION.txt",
            encoding="utf-8",
        ) as f:
            desc = await f.read()

        torrent_path = str(Path(f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/[TORRENTHR].torrent").resolve())
        async with aiofiles.open(torrent_path, "rb") as f:
            tfile = await f.read()

        # Upload Form
        url = f"{self.base_url}/takeupload.php"
        files: dict[str, tuple[str, Any]] = {"tfile": (f"{torrent_name}.torrent", tfile)}
        imdb_info = meta.imdb_info
        payload: dict[str, Any] = {
            "name": thr_name,
            "descr": desc,
            "type": cat_id,
            "url": f"{imdb_info.get('imdb_url', '')}/",
            "tube": str(meta.youtube),
        }
        headers = {
            "User-Agent": f"{meta.ua_name} {(meta.current_version if meta.current_version is not None else 'github.com/wastaken7/Upload-Assistant')} ({platform.system()} {platform.release()})"
        }
        # If pronfo fails, put mediainfo into TORRENTHR parser
        if (meta.is_disc) != "BDMV":
            files["nfo"] = ("MEDIAINFO.txt", mi_file)
        if subs:
            payload["subs[]"] = tuple(subs)

        thr_upload_prompt = (
            True if not meta.debug else (False if (meta.unattended and not meta.unattended_confirm) else cli_ui.ask_yes_no("send to takeupload.php?", default=False))
        )

        if thr_upload_prompt is True:
            await asyncio.sleep(0.5)
            response: httpx.Response | None = None
            try:
                cookies = await self.login(meta)

                if cookies:
                    logger.info(f"{self.tracker}: [green]Using authenticated session for upload")

                    async with httpx.AsyncClient(cookies=cookies, follow_redirects=True) as session:
                        response = await session.post(url=url, files=files, data=payload, headers=headers)

                        logger.debug(f"{self.tracker}: [dim]Response status: {response.status_code}")
                        logger.debug(f"{self.tracker}: [dim]Response URL: {response.url}")
                        logger.debug(response.text[:500] + "...")

                        if "uploaded=1" in str(response.url):
                            tracker_status = meta.tracker_status
                            tracker_status.setdefault(self.tracker, {})
                            tracker_status[self.tracker]["status_message"] = response.url
                            return True
                        logger.info(f"{self.tracker}: [yellow]Upload response didn't contain 'uploaded=1'. URL: {response.url}")
                        soup = BeautifulSoup(response.text, "html.parser")
                        error_text = soup.find("h2", string=re.compile(r"Error"))  # type: ignore

                        if error_text:
                            error_message = cast(Any, error_text).find_next("p")
                            if error_message:
                                logger.info(f"{self.tracker}: [red]Upload error: {error_message.text}")

                        return False
                else:
                    logger.error(f"{self.tracker}: [red]Failed to log in to TORRENTHR for upload")
                    return False

            except Exception as e:
                logger.error(f"{self.tracker}: [red]Error during upload: {e!s}")
                console.print_exception()
                if meta.debug and response is not None:
                    with contextlib.suppress(Exception):
                        logger.info(f"{self.tracker}: [red]Response: {response.text[:500]}...")
                logger.info(f"{self.tracker}: [yellow]It may have uploaded, please check TORRENTHR manually")
                return False
        else:
            logger.info(f"{self.tracker}: Request Data:")
            logger.info(Redaction.redact_private_info(payload))
            tracker_status = meta.tracker_status
            tracker_status.setdefault(self.tracker, {})
            tracker_status[self.tracker]["status_message"] = "Debug mode enabled, not uploading."
            await common.create_torrent_for_upload(meta, f"{self.tracker}" + "_DEBUG", f"{self.tracker}" + "_DEBUG", announce_url="https://fake.tracker")
            return False

    async def get_cat_id(self, meta: Meta) -> str:
        genres = str(meta.genres).lower()
        keywords = str(meta.keywords).lower()
        category = meta.category
        is_disc = meta.is_disc
        sd = int(meta.sd or 0)
        cat = "17"

        if "documentary" in genres or "documentary" in keywords:
            cat = "12"
        elif category == "MOVIE":
            if is_disc == "BDMV":
                cat = "40"
            elif is_disc in {"DVD", "HDDVD"}:
                cat = "14"
            else:
                cat = "4" if sd == 1 else "17"
        elif category == "TV":
            cat = "7" if sd == 1 else "34"
        elif meta.anime:
            cat = "31"
        return cat

    def get_subtitles(self, meta: Meta) -> list[int]:
        subs: list[int] = []
        sub_langs: list[str] = []
        if (meta.is_disc) != "BDMV":
            with Path(f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/MediaInfo.json").open(encoding="utf-8") as f:
                mi = cast(dict[str, Any], json.load(f))
            tracks = cast(list[dict[str, Any]], cast(dict[str, Any], mi.get("media", {})).get("track", []))
            for track in tracks:
                if track["@type"] == "Text":
                    language = track.get("Language")
                    language = language.split("-")[0] if language else language
                    if language in ["hr", "en", "bs", "sr", "sl"] and language not in sub_langs:
                        sub_langs.append(str(language))
        else:
            bdinfo = meta.bdinfo
            for sub in cast(list[Any], bdinfo.get("subtitles", [])):
                if sub not in sub_langs:
                    sub_langs.append(str(sub))
        if sub_langs != []:
            subs = []
            sub_lang_map = {"hr": 1, "en": 2, "bs": 3, "sr": 4, "sl": 5, "Croatian": 1, "English": 2, "Bosnian": 3, "Serbian": 4, "Slovenian": 5}
            for sub in sub_langs:
                language = sub_lang_map.get(sub)
                if language is not None:
                    subs.append(language)
        return subs

    async def edit_desc(self, meta: Meta) -> bool:
        pronfo = False
        bbcode = BBCODE()
        from src.description_review import get_base_description

        base = get_base_description(meta)

        desc_parts: list[str] = []
        tag_value = meta.tag
        tag = "" if not tag_value else f" / {tag_value[1:]}"
        res = str(meta.source) if (meta.is_disc) == "DVD" else meta.resolution
        desc_parts.append("[quote=Info]")
        year_str = str(meta.year) if meta.year is not None else ""
        name_aka = f"{meta.title} {meta.aka} {year_str}"
        name_aka = unidecode(name_aka)
        # name_aka = re.sub("[^0-9a-zA-Z. '\-\[\]]+", " ", name_aka)
        desc_parts.append(f"Name: {' '.join(name_aka.split())}\n\n")
        desc_parts.append(f"Overview: {meta.overview}\n\n")
        desc_parts.append(f"{res} / {meta.type}{tag}\n\n")
        category = meta.category
        desc_parts.append(f"Category: {category}\n")
        if meta.tmdb:
            desc_parts.append(f"TMDB: https://www.themoviedb.org/{category.lower()}/{meta.tmdb}\n")
        if meta.imdb_id or 0 != 0:
            imdb_info = meta.imdb_info
            desc_parts.append(f"IMDb: {imdb_info.get('imdb_url', '')!s}\n")
        if meta.tvdb_id or 0 != 0:
            desc_parts.append(f"TVDB: https://www.thetvdb.com/?id={meta.tvdb_id}&tab=series\n")
        if int(meta.tvmaze_id or 0) != 0:
            desc_parts.append(f"TVMaze: https://www.tvmaze.com/shows/{meta.tvmaze_id}\n")
        if meta.mal_id or 0 != 0:
            desc_parts.append(f"MAL: https://myanimelist.net/anime/{meta.mal_id}\n")
        desc_parts.append("[/quote]")

        image_glob: list[str] = []

        if base:
            # replace unsupported bbcode tags
            base = bbcode.convert_named_spoiler_to_named_hide(base)
            base = bbcode.convert_spoiler_to_hide(base)
            base = bbcode.convert_code_to_pre(base)
            # fix alignment for NFO content inherited from centering the spoiler
            base = re.sub(
                r"(?P<open>\[hide=(Scene|FraMeSToR) NFO:\]\[pre\])(?P<content>.*?)(?P<close>\[/pre\]\[/hide\])",
                r"\g<open>[align=left]\g<content>[/align]\g<close>",
                base,
                flags=re.DOTALL,
            )
            desc_parts.append("\n\n" + base)

        # REHOST IMAGES
        tmp_dir = screenshots_dir(meta.base_dir, meta.uuid)
        image_patterns: list[str] = ["*.png", ".[!.]*.png"]
        for pattern in image_patterns:
            image_glob.extend(str(p) for p in tmp_dir.glob(pattern))

        unwanted_patterns = ["FILE*", "PLAYLIST*"]
        unwanted_files: set[str] = set()
        for pattern in unwanted_patterns:
            unwanted_files.update(str(p) for p in tmp_dir.glob(pattern))
            hidden_pattern = f".{pattern}"
            unwanted_files.update(str(p) for p in tmp_dir.glob(hidden_pattern))

        ordered_images: list[str] = []
        seen_images: set[str] = set()
        for image in image_glob:
            if image in unwanted_files or image in seen_images:
                continue
            seen_images.add(image)
            ordered_images.append(image)

        image_list: list[str] = []
        image_api_key = str(self.config["TRACKERS"]["TORRENTHR"].get("img_api", "")).strip()
        if ordered_images and not image_api_key:
            logger.info(f"{self.tracker}: [yellow]image API key is not configured, skipping screenshot rehost")

        for image in ordered_images:
            if not image_api_key:
                break

            url = "https://img2.torrenthr.org/api/1/upload"
            data: dict[str, Any] = {
                "key": image_api_key,
            }
            async with aiofiles.open(image, "rb") as image_file:
                file_bytes = await image_file.read()
            response: httpx.Response | None = None
            response_data: dict[str, Any] = {}
            try:
                async with httpx.AsyncClient(timeout=30.0) as image_client:
                    response = await image_client.post(
                        url,
                        data=data,
                        files={"source": (Path(image).name, file_bytes)},
                    )
                    response.raise_for_status()
                    response_data = response.json()
                    img_data = cast(dict[str, Any], response_data.get("image", {}))
                    img_url = str(img_data.get("url", "")).strip()
                    if not img_url:
                        raise KeyError("image.url")
                    image_list.append(img_url)
            except httpx.RequestError as exc:
                logger.info(f"{self.tracker}: [yellow]Failed to upload image {Path(image).name}: {exc}")
            except httpx.HTTPStatusError:
                logger.info(f"{self.tracker}: [yellow]Failed to upload image {Path(image).name}")
                if response is not None:
                    logger.info(f"{self.tracker}: [yellow]image host returned HTTP {response.status_code}")
                    logger.info(response.text)
            except json.decoder.JSONDecodeError:
                logger.info(f"{self.tracker}: [yellow]Failed to parse TORRENTHR image host response for {Path(image).name}")
                if response is not None:
                    logger.info(response.text)
            except KeyError:
                logger.info(f"{self.tracker}: [yellow]image host response was missing an image URL for {Path(image).name}")
                logger.info(response_data)
            await asyncio.sleep(1)

        desc_parts.append("[align=center]")
        if (meta.is_disc) == "BDMV":
            async with aiofiles.open(f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/BD_SUMMARY_00.txt") as bd_file:
                desc_parts.append(f"[nfo]{await bd_file.read()}[/nfo]")
        elif self.config["TRACKERS"]["TORRENTHR"].get("pronfo_api_key"):
            # ProNFO
            pronfo_url = f"https://www.pronfo.com/api/v1/access/upload/{self.config['TRACKERS']['TORRENTHR'].get('pronfo_api_key', '')}"
            async with aiofiles.open(f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/MEDIAINFO.txt") as mi_file:
                data = {
                    "content": await mi_file.read(),
                    "theme": self.config["TRACKERS"]["TORRENTHR"].get("pronfo_theme", "gray"),
                    "rapi": self.config["TRACKERS"]["TORRENTHR"].get("pronfo_rapi_id"),
                }
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(pronfo_url, data=data)
            try:
                response_data = response.json()
                if response_data.get("error", True) is False:
                    mi_img = response_data.get("url")
                    desc_parts.append(f"\n[img]{mi_img}[/img]\n")
                    pronfo = True
            except Exception:
                logger.info(f"{self.tracker}: [bold red]Error parsing pronfo response, using TORRENTHR parser instead")
                logger.debug(f"{self.tracker}: {response}")
                logger.debug(response.text)

        screens = meta.screens or 0
        desc_parts.extend([f"\n[img]{each}[/img]\n" for each in image_list[:screens]])
        # if pronfo:
        #     with open(os.path.abspath(f"{meta.base_dir}/tmp/{meta.uuid}/MEDIAINFO.txt"), 'r') as mi_file:
        #         full_mi = mi_file.read()
        #         desc.write(f"[/align]\n[hide=FULL MEDIAINFO]{full_mi}[/hide][align=center]")
        #         mi_file.close()
        desc_parts.append(f"\n\n[size=2][url={self.base_url}/forums.php?action=viewtopic&topicid=8977]{meta.ua_signature}[/url][/size][/align]")
        async with aiofiles.open(
            f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/[TORRENTHR]DESCRIPTION.txt",
            "w",
            encoding="utf-8",
        ) as desc:
            await desc.write("".join(desc_parts))
        return pronfo

    async def search_existing(self, meta: Meta) -> list[str]:
        imdb_id = str(meta.imdb)
        base_search_url = f"{self.base_url}/browse.php?search={imdb_id}&blah=2&incldead=1"
        dupes: list[str] = []

        if not imdb_id:
            logger.info(f"{self.tracker}: [red]No IMDb ID available for search")
            return dupes

        cookies = await self.login(meta)

        client_args: dict[str, Any] = {"timeout": 10.0, "follow_redirects": True}
        if cookies:
            client_args["cookies"] = cookies
        else:
            logger.error(f"{self.tracker}: [red]Failed to log in to TORRENTHR for search")
            return dupes

        async with httpx.AsyncClient(**client_args) as client:
            # Start with first page (page 0 in TORRENTHR's system)
            current_page = 0
            more_pages = True
            page_count = 0
            all_titles_seen: set[str] = set()

            while more_pages:
                page_url = base_search_url
                if current_page > 0:
                    page_url += f"&page={current_page}"

                page_count += 1
                logger.debug(f"{self.tracker}: [dim]Searching page {page_count}...")
                response = await client.get(page_url)
                response.raise_for_status()

                page_dupes, has_next_page, next_page_number = await self._process_search_response(response, current_page)

                for dupe in page_dupes:
                    if dupe not in dupes:
                        dupes.append(dupe)
                        all_titles_seen.add(dupe)

                if has_next_page:
                    logger.debug(f"{self.tracker}: [dim]Next page available: page {next_page_number}")

                if has_next_page:
                    current_page = next_page_number

                    await asyncio.sleep(1)
                else:
                    more_pages = False

        return dupes

    async def _process_search_response(
        self,
        response: httpx.Response,
        current_page: int,
    ) -> tuple[list[str], bool, int]:
        page_dupes: list[str] = []
        has_next_page = False
        next_page_number = current_page

        if response.status_code == 200 or response.status_code == 302:
            html_length = len(response.text)
            logger.debug(f"{self.tracker}: [dim]Response HTML length: {html_length} bytes")

            if html_length < 1000:
                logger.info(f"{self.tracker}: [yellow]Response seems too small ({html_length} bytes), might be an error page")
                logger.debug(f"{self.tracker}: [yellow]Response content: {response.text[:500]}")
                return page_dupes, False, current_page

            soup = BeautifulSoup(response.text, "html.parser")

            result_table = soup.find("table", {"class": "torrentlist"}) or soup.find("table", {"align": "center"})
            if not result_table:
                logger.info(f"{self.tracker}: [yellow]No results table found in HTML - either no results or page structure changed")

            link_count = 0
            onmousemove_count = 0

            for link in soup.find_all("a", href=True):
                href_raw = link.get("href")
                if not href_raw:
                    continue
                href = " ".join(href_raw) if isinstance(href_raw, AttributeValueList) else href_raw

                if href.startswith("details.php"):
                    link_count += 1
                    onmousemove_raw = link.get("onmousemove")
                    if onmousemove_raw:
                        onmousemove_count += 1
                        try:
                            onmousemove = " ".join(onmousemove_raw) if isinstance(onmousemove_raw, AttributeValueList) else onmousemove_raw
                            dupe = onmousemove.split("','/images")[0]
                            dupe = dupe.replace("return overlibImage('", "")
                            page_dupes.append(dupe)
                        except Exception as parsing_error:
                            logger.debug(f"{self.tracker}: [yellow]Error parsing link: {parsing_error}")

            page_number_display = current_page + 1
            logger.debug(f"{self.tracker}: [dim]Page {page_number_display}: Found {link_count} detail links, {onmousemove_count} parsed successfully")

            pagination_text = None
            for p_tag in soup.find_all("p", align="center"):
                if p_tag.text and ("Prev" in p_tag.text or "Next" in p_tag.text):
                    pagination_text = p_tag
                    logger.debug(f"{self.tracker}: [dim]Found pagination: {pagination_text.text.strip()}")
                    break

            if pagination_text:
                next_links = pagination_text.find_all("a")
                for link in next_links:
                    if "Next" in link.text:
                        has_next_page = True
                        href_raw = link.get("href")
                        href = ""
                        if href_raw:
                            href = " ".join(href_raw) if isinstance(href_raw, AttributeValueList) else href_raw

                        logger.debug(f"{self.tracker}: [dim]Next page URL: {href}")

                        page_match = re.search(r"page=(\d+)", href)
                        if page_match:
                            next_page_number = int(page_match.group(1))
                            logger.debug(f"{self.tracker}: [dim]Found next page link: page={next_page_number} (will be displayed as page {next_page_number + 1})")
                            break
        else:
            logger.info(f"{self.tracker}: [bold red]HTTP request failed. Status: {response.status_code}")
            logger.debug(f"{self.tracker}: [red]Response: {response.text[:500]}...")

        return page_dupes, has_next_page, next_page_number

    async def login(self, meta: Meta) -> dict[str, Any] | None:
        logger.info(f"{self.tracker}: [yellow]Logging in to TORRENTHR...")
        url = f"{self.base_url}/takelogin.php"

        if not self.username or not self.password:
            logger.info(f"{self.tracker}: [red]Missing TORRENTHR credentials in config.py")
            return None

        payload: dict[str, Any] = {"username": self.username, "password": self.password, "ssl": "yes"}
        headers = {
            "User-Agent": f"{meta.ua_name} {(meta.current_version if meta.current_version is not None else 'github.com/wastaken7/Upload-Assistant')} ({platform.system()} {platform.release()})",
            "Referer": f"{self.base_url}/login.php",
        }

        async with httpx.AsyncClient(follow_redirects=True) as session:
            try:
                login_page = await session.get(f"{self.base_url}/login.php")
                login_soup = BeautifulSoup(login_page.text, "html.parser")

                for input_tag in login_soup.find_all("input", type="hidden"):
                    name_raw = input_tag.get("name")
                    value_raw = input_tag.get("value")
                    if name_raw and value_raw:
                        name = " ".join(name_raw) if isinstance(name_raw, AttributeValueList) else name_raw
                        value = " ".join(value_raw) if isinstance(value_raw, AttributeValueList) else value_raw
                        payload[name] = value

                resp = await session.post(url, headers=headers, data=payload)

                if "index.php" in str(resp.url) or "logout.php" in resp.text:
                    logger.info(f"{self.tracker}: [green]Successfully logged in to TORRENTHR")
                    return dict(session.cookies)
                logger.error(f"{self.tracker}: [red]Failed to log in to TORRENTHR")
                logger.info(f"{self.tracker}: [red]Login response URL: {resp.url}")
                logger.info(f"{self.tracker}: [red]Login status code: {resp.status_code}")
                return None

            except Exception as e:
                logger.error(f"{self.tracker}: [red]Error during TORRENTHR login: {e!s}")
                console.print_exception()
                return None

    async def get_name(self, meta: Meta) -> str:
        return unidecode(meta.name.replace("DD+", "DDP"))
