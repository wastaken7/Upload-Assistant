# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import re
import unicodedata
from pathlib import Path
from typing import Any, ClassVar, cast
from urllib.parse import urlparse

import aiofiles
import cli_ui
import httpx
from bs4 import BeautifulSoup
from rich.markup import escape

from src.cogs.redaction import Redaction
from src.console import logger, prompt_in_thread
from src.get_desc import DescriptionBuilder
from src.languages import languages_manager
from src.meta import Meta
from src.rehostimages import RehostImagesManager
from src.tmdb import TmdbManager
from src.trackers.common import Common


class GreatPosterWall:
    """
    GPW Private Torrent Tracker
    """

    auth_type = "other_api"
    tracker = "GREATPOSTERWALL"
    display_name = "GreatPosterWall"
    allows_bloated_audio = True
    source_flag = "GreatPosterWall"
    base_url = "https://greatposterwall.com"
    auth_token = None
    tmdb_data: ClassVar[dict[str, Any]] = {}
    banned_groups = (
        "ALT",
        "aXXo",
        "BATWEB",
        "BitsTV",
        "BlackTV",
        "BMDRu",
        "BRrip",
        "CM8",
        "CrEwSaDe",
        "CTFOH",
        "CTRLHD",
        "DDHDTV",
        "DNL",
        "DreamHD",
        "ENTHD",
        "FaNGDiNG0",
        "FGT",
        "GPTHD",
        "HD2DVD",
        "HDT",
        "HDTime",
        "Huawei",
        "ION10",
        "iPlanet",
        "KiNGDOM",
        "Leffe",
        "mHD",
        "MiniHD",
        "MOMOWEB",
        "Mp4Ba",
        "mSD",
        "NhaNc3",
        "nHD",
        "nikt0",
        "NSBC",
        "nSD",
        "NukeHD",
        "OFT",
        "PRODJi",
        "RARBG",
        "RDN",
        "SANTi",
        "SeeHD",
        "SeeWEB",
        "SM737",
        "SonyHD",
        "STUTTERSHIT",
        "TAGWEB",
        "ViSION",
        "VXT",
        "WAF",
        "x0r",
        "Xiaomi",
        "YIFY",
    )
    approved_image_hosts = ("kshare", "pixhost", "pterclub", "ilikeshots", "imgbox")
    can_rehost_unapproved_images = True
    torrent_url = f"{base_url}/torrents.php?torrentid="
    url_host_mapping: ClassVar = {
        "kshare.club": "kshare",
        "pixhost.to": "pixhost",
        "imgbox.com": "imgbox",
        "img.pterclub.com": "pterclub",
        "yes.ilikeshots.club": "ilikeshots",
    }
    supported_categories = ("MOVIE",)
    tracker_urls = ("https://tracker.greatposterwall.com",)
    group_id: str = ""
    tmdb_localization_requirements: ClassVar = {
        "zh-cn": {
            "main": "credits",
        }
    }

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.rehost_images_manager = RehostImagesManager(config)
        self.common = Common(config)
        self.tmdb_manager = TmdbManager(config)
        self.tracker_config: dict[str, Any] = self.config["TRACKERS"].get(self.tracker, {})
        self.announce = self.tracker_config.get("announce_url", "")
        self.api_key = self.tracker_config.get("api_key", "")

    async def load_cookies(self, meta: Meta) -> Any:
        from src.cookie_auth import find_cookie_file

        cookie_file = find_cookie_file(meta.base_dir, self.tracker, self.config)
        if not Path(cookie_file).exists():
            return False

        return await self.common.parse_cookie_file(cookie_file)

    async def load_localized_data(self, meta: Meta) -> None:
        data = meta.tmdb_localized_data
        zh_cn_data = data.get("zh-cn")
        if not zh_cn_data or not zh_cn_data.get("main"):
            raise RuntimeError(f"{self.tracker}: Missing TMDB localized data (zh-cn).")

        self.tmdb_data = zh_cn_data.get("main") or {}
        return

    def get_container(self, meta: Meta) -> str:
        container_value = meta.container
        container = container_value if isinstance(container_value, str) else ""
        if container == "m2ts":
            return container
        if container == "vob":
            return "VOB IFO"
        if container in ["avi", "mpg", "mp4", "mkv"]:
            return container.upper()

        return "Other"

    async def get_subtitle(self, meta: Meta) -> list[str]:
        if not meta.language_checked:
            await languages_manager.process_desc_language(meta, tracker=self.tracker)

        found_language_strings_raw = meta.subtitle_languages
        if not isinstance(found_language_strings_raw, list):
            return []

        found_language_strings_list = found_language_strings_raw
        found_language_strings = [lang for lang in found_language_strings_list if isinstance(lang, str)]
        return [lang.lower() for lang in found_language_strings]

    async def get_ch_dubs(self, meta: Meta) -> bool:
        if not meta.language_checked:
            await languages_manager.process_desc_language(meta, tracker=self.tracker)

        found_language_strings_raw = meta.audio_languages
        if not isinstance(found_language_strings_raw, list):
            return False
        found_language_strings_list = found_language_strings_raw
        found_language_strings = [lang for lang in found_language_strings_list if isinstance(lang, str)]

        chinese_languages = {"mandarin", "chinese", "zh", "zh-cn", "zh-hans", "zh-hant", "putonghua", "国语", "普通话"}
        return any(lang.strip().lower() in chinese_languages for lang in found_language_strings)

    def get_codec(self, meta: Meta) -> str:
        video_encode = meta.video_encode.strip().lower()
        codec_final = meta.video_codec.strip().lower()

        codec_map = {
            "divx": "DivX",
            "xvid": "XviD",
            "x264": "x264",
            "h.264": "H.264",
            "avc": "H.264",
            "x265": "x265",
            "h.265": "H.265",
            "hevc": "H.265",
        }

        for key, value in codec_map.items():
            if key in video_encode or key in codec_final:
                return value

        return "Other"

    def get_audio_codec(self, meta: Meta) -> str:
        priority_order = ["DTS-X", "E-AC-3 JOC", "TrueHD", "DTS-HD", "PCM", "FLAC", "DTS-ES", "DTS", "E-AC-3", "AC3", "AAC", "Opus", "Vorbis", "MP3", "MP2"]

        codec_map = {
            "DTS-X": ["DTS:X"],
            "E-AC-3 JOC": ["DD+ 5.1 Atmos", "DD+ 7.1 Atmos"],
            "TrueHD": ["TrueHD"],
            "DTS-HD": ["DTS-HD"],
            "PCM": ["LPCM"],
            "FLAC": ["FLAC"],
            "DTS-ES": ["DTS-ES"],
            "DTS": ["DTS"],
            "E-AC-3": ["DD+"],
            "AC3": ["DD"],
            "AAC": ["AAC"],
            "Opus": ["Opus"],
            "Vorbis": ["VORBIS"],
            "MP2": ["MP2"],
            "MP3": ["MP3"],
        }

        audio_description = meta.audio

        if not audio_description or not isinstance(audio_description, str):
            return "Outro"

        for codec_name in priority_order:
            search_terms = codec_map.get(codec_name, [])

            for term in search_terms:
                if term in audio_description:
                    return codec_name

        return "Outro"

    def get_title(self, meta: Meta) -> str:
        title_value = self.tmdb_data.get("name") or self.tmdb_data.get("title") or ""
        title = title_value if isinstance(title_value, str) else ""

        return title if title and title != meta.title else ""

    def is_approved_image_url(self, image_url: str) -> bool:
        hostname = urlparse(image_url).hostname or ""
        for domain, host_name in self.url_host_mapping.items():
            if hostname == domain or hostname.endswith(f".{domain}"):
                return host_name in self.approved_image_hosts
        return False

    async def rehost_unapproved_images(self, meta: Meta) -> None:
        """Import public image URLs to GPW's KShare host before the normal host check."""
        image_list = meta.image_list
        if not isinstance(image_list, list) or not image_list:
            return
        if not self.api_key:
            logger.warning("[yellow]GREATPOSTERWALL: cannot rehost images because no API key is configured.[/yellow]")
            return

        rehosted_images: list[dict[str, str]] = []
        async with httpx.AsyncClient(timeout=60) as client:
            for image in cast(list[dict[str, str]], image_list):
                raw_url = image.get("raw_url", "")
                if not raw_url.startswith(("https://", "http://")) or self.is_approved_image_url(raw_url):
                    rehosted_images.append(image)
                    continue

                try:
                    response = await client.post(
                        f"{self.base_url}/api.php",
                        params={"action": "img_upload", "api_key": self.api_key},
                        data={"urls[]": raw_url},
                    )
                    response_data = response.json()
                    response_body = response_data.get("response", {})
                    files = response_body.get("files", []) if isinstance(response_body, dict) else []
                    hosted_url = files[0].get("name") if files else None
                    if response.status_code != 200 or response_data.get("status") != 200 or not isinstance(hosted_url, str):
                        error = response_body.get("Error", "no image URL returned") if isinstance(response_body, dict) else "no image URL returned"
                        logger.warning(f"[yellow]GREATPOSTERWALL: could not rehost {raw_url}: {error}[/yellow]")
                        rehosted_images.append(image)
                        continue
                except (httpx.HTTPError, TypeError, ValueError) as e:
                    logger.warning(f"[yellow]GREATPOSTERWALL: could not rehost {raw_url}: {e!s}[/yellow]")
                    rehosted_images.append(image)
                    continue

                rehosted_image = image.copy()
                rehosted_image.update({"img_url": hosted_url, "raw_url": hosted_url, "web_url": hosted_url})
                rehosted_images.append(rehosted_image)

        meta.image_list = rehosted_images

    async def check_image_hosts(self, meta: Meta) -> None:
        # Rule: 2.2.1. Screenshots: They have to be saved at kshare.club, pixhost.to, img.pterclub.com, yes.ilikeshots.club, imgbox.com, s3.pterclub.com
        await self.rehost_unapproved_images(meta)
        await self.rehost_images_manager.check_hosts(
            meta,
            self.tracker,
            url_host_mapping=self.url_host_mapping,
            img_host_index=1,
            approved_image_hosts=self.approved_image_hosts,
        )
        return

    async def get_release_desc(self, meta: Meta) -> str:
        builder = DescriptionBuilder(self.tracker, self.config)
        return await builder.general_description_generator(
            meta,
            bluray=False,
            book=False,
            custom_signature=False,
            game=False,
            logo=False,
            mediainfo=False,
            tv_info=False,
            signature=f"[align=right][url=https://github.com/wastaken7/Upload-Assistant][size=1]{meta.ua_signature}[/size][/url][/align]",
        )

    def get_trailer(self, meta: Meta) -> str:
        video_results: list[dict[str, Any]] = []
        videos = self.tmdb_data.get("videos")
        if isinstance(videos, dict):
            videos_dict = cast(dict[str, Any], videos)
            results = videos_dict.get("results")
            if isinstance(results, list):
                results_list = results
                video_results.extend(cast(dict[str, Any], result) for result in results_list if isinstance(result, dict))

        youtube = ""

        if video_results:
            youtube_value = video_results[-1].get("key", "")
            youtube = youtube_value if isinstance(youtube_value, str) else ""

        if not youtube:
            meta_trailer = str(meta.youtube)
            if meta_trailer:
                youtube = meta_trailer.replace("https://www.youtube.com/watch?v=", "").replace("/", "")

        return youtube

    async def get_tags(self, meta: Meta) -> str:
        tags = ""

        genres = meta.genres
        if genres:
            genre_names = [genre.strip() for genre in genres if isinstance(genre, str) and genre.strip()]
            if genre_names:
                tags = ", ".join(unicodedata.normalize("NFKD", name).encode("ASCII", "ignore").decode("utf-8").replace(" ", ".").lower() for name in genre_names)

        if not tags:
            if meta.unattended and not meta.unattended_confirm:
                logger.info(f"{self.tracker}: [yellow]Unattended mode: Enter genres not available. Skipping {self.tracker} upload.[/yellow]")
                meta.skipping = f"{self.tracker}"
                return ""
            tags_raw = await prompt_in_thread(cli_ui.ask_string, f"Enter the genres (in {self.tracker} format): ")
            tags = (tags_raw or "").strip()

        return tags

    async def get_additional_checks(self, meta: Meta) -> bool:
        media_type = str(meta.type).lower()
        tag = "" if not meta.tag else meta.tag.strip().lower()
        if media_type == "remux" and tag in ("-hdt", "-frds"):
            logger.info(f"{self.tracker}: Remuxes from {meta.tag} are not allowed on {self.tracker}")
            return False
        if media_type == "webdl" and tag == "-evo":
            logger.info(f"{self.tracker}: WEB-DLs from {meta.tag} are not allowed on {self.tracker}")
            return False

        return True

    async def search_existing(self, meta: Meta) -> list[dict[str, str]]:
        dupes: list[dict[str, str]] = []

        group_id = await self.get_groupid(meta)
        if not group_id:
            return []

        imdb = dict(meta.imdb_info).get("imdbID", "")
        if not imdb:
            logger.info(f"{self.tracker}: IMDb ID not found in metadata. Skipping search.")
            return []

        cookies = await self.load_cookies(meta)
        if not cookies:
            search_url = f"{self.base_url}/api.php?api_key={self.api_key}&action=torrent&imdbID={imdb}"
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(search_url)
                response.raise_for_status()
                data = response.json()
                data_dict = cast(dict[str, Any], data) if isinstance(data, dict) else {}

                if data_dict.get("status") == 200 and "response" in data_dict:
                    response_list_raw = data_dict.get("response")
                    response_list = cast(list[Any], response_list_raw) if isinstance(response_list_raw, list) else []
                    for item in response_list:
                        if not isinstance(item, dict):
                            continue
                        item_dict = cast(dict[str, Any], item)
                        name = item_dict.get("Name", "")
                        year = item_dict.get("Year", "")
                        resolution = item_dict.get("Resolution", "")
                        source = item_dict.get("Source", "")
                        processing = item_dict.get("Processing", "")
                        remaster = item_dict.get("RemasterTitle", "")
                        codec = item_dict.get("Codec", "")

                        formatted = f"{name} {year} {resolution} {source} {processing} {remaster} {codec}".strip()
                        formatted = re.sub(r"\s{2,}", " ", formatted)
                        dupes.append({"name": formatted})
                    return dupes
                return []

        imdb_value = str(imdb or "")
        search_url = f"{self.base_url}/torrents.php?groupname={imdb_value.upper()}"  # using TT in imdb returns the search page instead of redirecting to the group page
        found_items: list[dict[str, Any]] = []

        async with httpx.AsyncClient(
            cookies=cookies,
            timeout=30,
            headers={"User-Agent": f"{meta.ua_name} {(meta.current_version if meta.current_version is not None else 'github.com/wastaken7/Upload-Assistant')}"},
        ) as client:
            response = await client.get(search_url)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")

            torrent_table = soup.find("table", id="torrent_table")
            if not torrent_table:
                return []

            for torrent_row in torrent_table.find_all("tr", class_="TableTorrent-rowTitle"):
                title_link = torrent_row.find("a", href=re.compile(r"torrentid=\d+"))
                if not title_link:
                    continue

                tooltip_value = title_link.get("data-tooltip")
                if not isinstance(tooltip_value, str):
                    continue

                name = tooltip_value

                size_cell = torrent_row.find("td", class_="TableTorrent-cellStatSize")
                size = size_cell.get_text(strip=True) if size_cell else None

                href_value = title_link.get("href")
                href_text = href_value if isinstance(href_value, str) else ""
                match = re.search(r"torrentid=(\d+)", href_text)
                torrent_link = f"{self.torrent_url}{match.group(1)}" if match else None

                dupe_entry = {"name": name, "size": size, "link": torrent_link}

                found_items.append(dupe_entry)

            if found_items:
                await self.get_slots(meta, client, GreatPosterWall.group_id)

            return found_items

    async def get_slots(self, meta: Meta, client: httpx.AsyncClient, group_id: str) -> None:
        url = f"{self.base_url}/torrents.php?id={group_id}"

        try:
            response = await client.get(url)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.info(f"{self.tracker}: Error on request: {e.response.status_code} - {e.response.reason_phrase}", extra={"markup": False})
            return

        soup = BeautifulSoup(response.text, "html.parser")

        empty_slot_rows = soup.find_all("tr", class_="TableTorrent-rowEmptySlotNote")

        for row in empty_slot_rows:
            edition_id = row.get("edition-id")
            resolution = ""

            if edition_id == "1":
                resolution = "SD"
            elif edition_id == "3":
                resolution = "2160p"

            if not resolution:
                slot_cell = row.find("td", class_="TableTorrent-cellEmptySlotNote")
                slot_type_tag = slot_cell.find("i") if slot_cell else None
                if slot_type_tag:
                    resolution = slot_type_tag.get_text(strip=True).replace("empty slots:", "").strip()

            slot_names: list[str] = []

            i_tags = row.find_all("i")
            for tag in i_tags:
                text = tag.get_text(strip=True)
                if "empty slots:" not in text:
                    slot_names.append(text)

            span_tags = row.find_all("span", class_="tooltipstered")
            for tag in span_tags:
                icon = tag.find("i")
                if icon:
                    slot_names.append(icon.get_text(strip=True))

            final_slots_list = sorted(set(slot_names))
            formatted_slots = [f"- {slot}" for slot in final_slots_list]
            final_slots = "\n".join(formatted_slots)

            if final_slots:
                final_slots = final_slots.replace("Slot", "").replace("Empty slots:", "").strip()
                if resolution == meta.resolution:
                    logger.info(f"{self.tracker}: \n[green]Available Slots for[/green] {resolution}:")
                    logger.info(f"{self.tracker}: {final_slots}\n")

    async def get_media_info(self, meta: Meta) -> str:
        info_file_path = ""
        info_file_path = (
            f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/BD_SUMMARY_00.txt"
            if meta.is_disc == "BDMV"
            else f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/MEDIAINFO_CLEANPATH.txt"
        )

        if Path(info_file_path).exists():
            try:
                async with aiofiles.open(info_file_path, encoding="utf-8") as f:
                    return await f.read()
            except Exception as e:
                logger.info(f"{self.tracker}: [bold red]Error reading info file at {info_file_path}: {e}[/bold red]")
                return ""
        else:
            logger.info(f"{self.tracker}: [bold red]Info file not found: {info_file_path}[/bold red]")
            return ""

    def get_edition(self, meta: Meta) -> str:
        edition_str = meta.edition.lower()
        if not edition_str:
            return ""

        edition_map = {
            "director's cut": "Director's Cut",
            "theatrical": "Theatrical Cut",
            "extended": "Extended",
            "uncut": "Uncut",
            "unrated": "Unrated",
            "imax": "IMAX",
            "noir": "Noir",
            "remastered": "Remastered",
        }

        for keyword, label in edition_map.items():
            if keyword in edition_str:
                return label

        return ""

    def get_processing_other(self, meta: Meta) -> str:
        if meta.type == "DISC":
            is_disc_type = meta.is_disc

            if is_disc_type == "BDMV":
                disctype = meta.disctype
                if isinstance(disctype, str) and disctype in ["BD100", "BD66", "BD50", "BD25"]:
                    return disctype

                try:
                    size_in_gb = meta.bdinfo["size"]
                except KeyError, IndexError, TypeError:
                    size_in_gb = 0

                if size_in_gb > 66:
                    return "BD100"
                if size_in_gb > 50:
                    return "BD66"
                if size_in_gb > 25:
                    return "BD50"
                return "BD25"

            if is_disc_type == "DVD":
                dvd_size = meta.dvd_size
                if isinstance(dvd_size, str) and dvd_size in ["DVD9", "DVD5"]:
                    return dvd_size
                return "DVD9"

        return ""

    def get_screens(self, meta: Meta) -> list[str]:
        images_value = meta.image_list
        images_list: list[Any] = cast(list[Any], images_value) if isinstance(images_value, list) else []
        screenshot_urls: list[str] = []
        for image in images_list:
            if not isinstance(image, dict):
                continue
            image_dict = cast(dict[str, Any], image)
            raw_url = image_dict.get("raw_url")
            if isinstance(raw_url, str) and raw_url:
                screenshot_urls.append(raw_url)

        return screenshot_urls

    def get_credits(self, meta: Meta) -> str:
        director_entries: list[str] = []

        imdb_directors = dict(meta.imdb_info).get("directors")
        if isinstance(imdb_directors, list):
            imdb_directors_list = imdb_directors
            director_entries.extend(name for name in imdb_directors_list if isinstance(name, str))

        tmdb_directors = meta.tmdb_directors
        if isinstance(tmdb_directors, list):
            tmdb_directors_list = tmdb_directors
            director_entries.extend(name for name in tmdb_directors_list if isinstance(name, str))

        if director_entries:
            unique_names = list(dict.fromkeys(director_entries))[:5]
            return ", ".join(unique_names)

        return "N/A"

    def get_remaster_title(self, meta: Meta) -> str:
        found_tags: list[str] = []

        def add_tag(tag_id: str) -> None:
            if tag_id and tag_id not in found_tags:
                found_tags.append(tag_id)

        # Collections
        distributor = meta.distributor.upper()
        if distributor in ("WARNER ARCHIVE", "WARNER ARCHIVE COLLECTION", "WAC"):
            add_tag("warner_archive_collection")
        elif distributor in ("CRITERION", "CRITERION COLLECTION", "CC"):
            add_tag("the_criterion_collection")
        elif distributor in ("MASTERS OF CINEMA", "MOC"):
            add_tag("masters_of_cinema")

        # Editions
        edition = meta.edition.lower()
        if "director's cut" in edition:
            add_tag("director_s_cut")
        elif "extended" in edition:
            add_tag("extended_edition")
        elif "theatrical" in edition:
            add_tag("theatrical_cut")
        elif "rifftrax" in edition:
            add_tag("rifftrax")
        elif "uncut" in edition:
            add_tag("uncut")
        elif "unrated" in edition:
            add_tag("unrated")

        # Audio
        if meta.dual_audio:
            add_tag("dual_audio")

        if meta.extras:
            add_tag("extras")

        # Commentary
        has_commentary = meta.has_commentary or meta.manual_commentary

        # Ensure 'with_commentary' is last if it exists
        if has_commentary:
            add_tag("with_commentary")
            if "with_commentary" in found_tags:
                found_tags.remove("with_commentary")
                found_tags.append("with_commentary")

        if not found_tags:
            return ""

        return " / ".join(found_tags)

    async def get_groupid(self, meta: Meta) -> bool:
        GreatPosterWall.group_id = ""
        search_url = f"{self.base_url}/api.php?api_key={self.api_key}&action=torrent&req=group&imdbID={meta.imdb_info.get('imdbID')}"

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(search_url)
                response.raise_for_status()

        except httpx.RequestError as e:
            logger.info(f"{self.tracker}: [bold red]Network error fetching groupid: {e}[/bold red]")
            return False
        except httpx.HTTPStatusError as e:
            logger.info(f"{self.tracker}: [bold red]HTTP error when fetching groupid: Status {e.response.status_code}[/bold red]")
            return False

        try:
            data: dict[str, Any] = response.json()
        except ValueError as e:
            logger.info(f"{self.tracker}: [bold red]Error decoding JSON from groupid response: {e}[/bold red]")
            return False

        if data.get("status") == 200 and "response" in data and "ID" in data["response"]:
            GreatPosterWall.group_id = str(data["response"]["ID"])
            return True
        return False

    async def get_additional_data(self, meta: Meta) -> dict[str, Any]:
        imdb_identifier = str(meta.imdb_info.get("imdbID") or meta.imdb or "").strip()
        tmdb_identifier = str(meta.tmdb_id or "").strip()
        if imdb_identifier:
            data_source = "imdb"
            identifier = imdb_identifier
        elif tmdb_identifier:
            data_source = "tmdb"
            identifier = tmdb_identifier
        else:
            data_source = "manual"
            identifier = ""

        data = {
            "data_source": data_source,
            "identifier": identifier,
            "desc": self.tmdb_data.get("overview", ""),
            "image": f"https://image.tmdb.org/t/p/original{meta.tmdb_poster_path}",
            "maindesc": meta.overview,
            "name": meta.title,
            "releasetype": self._get_movie_type(meta),
            "subname": self.get_title(meta),
            "tags": await self.get_tags(meta),
            "year": str(meta.year) if meta.year is not None else "",
        }

        # Keep backward-compatible identifiers for sites/APIs that still parse legacy field names.
        if imdb_identifier:
            data["imdb"] = imdb_identifier
        if tmdb_identifier:
            data["tmdb"] = tmdb_identifier

        # GREATPOSTERWALL API still requires explicit main-artist fields for new group creation.
        data.update(await self._get_artist_data(meta))
        data["main_artist_number"] = "1"

        return data

    async def _get_artist_data(self, meta: Meta) -> dict[str, Any]:
        directors: list[str] = []
        directors_id: list[str] = []
        writers: list[str] = []
        writers_id: list[str] = []
        stars: list[str] = []
        stars_id: list[str] = []
        cast_character_map: dict[str, str] = {}
        full_credits: list[dict[str, Any]] = []

        imdb_identifier = str(meta.imdb_info.get("imdbID") or meta.imdb or "").strip()
        full_credits_success = False
        if imdb_identifier:
            movie_info_raw = await self._fetch_gpw_movie_info(meta, "imdb", imdb_identifier)
            movie_info = movie_info_raw
            if isinstance(movie_info_raw, dict) and isinstance(movie_info_raw.get("response"), dict):
                movie_info = cast(dict[str, Any], movie_info_raw.get("response"))
            if isinstance(movie_info, dict):
                full_credits_value = movie_info.get("FullCredits") or movie_info.get("fullCredits")
                if isinstance(full_credits_value, list):
                    full_credits = [item for item in full_credits_value if isinstance(item, dict)]
                    seen_director_ids: set[str] = set()
                    seen_writer_ids: set[str] = set()
                    seen_star_ids: set[str] = set()
                    for credit in full_credits:
                        role = str(credit.get("role") or "").strip().lower()
                        person_id = str(credit.get("imdbId") or credit.get("imdbID") or "").strip()
                        person_name = str(credit.get("name") or "").strip()
                        character = str(credit.get("character") or "").strip()
                        if not person_name or person_name.lower() == "n/a":
                            continue
                        if not re.match(r"^nm\d+$", person_id):
                            continue
                        if role == "director":
                            if person_id in seen_director_ids:
                                continue
                            directors.append(person_name)
                            directors_id.append(person_id)
                            seen_director_ids.add(person_id)
                        elif role == "writer":
                            if person_id in seen_writer_ids:
                                continue
                            writers.append(person_name)
                            writers_id.append(person_id)
                            seen_writer_ids.add(person_id)
                        elif role == "cast":
                            if person_id in seen_star_ids:
                                continue
                            stars.append(person_name)
                            stars_id.append(person_id)
                            if character:
                                cast_character_map[person_id] = character
                            seen_star_ids.add(person_id)
                    full_credits_success = bool(directors and directors_id)

        # Fallback: if FullCredits is unavailable/invalid, use existing imdb_info fields.
        if not full_credits_success:
            imdb_info = meta.imdb_info
            raw_directors = imdb_info.get("directors", [])
            raw_directors_id = imdb_info.get("directors_id", [])
            raw_writers = imdb_info.get("writers", [])
            raw_writers_id = imdb_info.get("writers_id", [])
            raw_stars = imdb_info.get("stars", [])
            raw_stars_id = imdb_info.get("stars_id", [])

            directors = [x.strip() for x in raw_directors if isinstance(x, str) and x.strip()]
            directors_id = [x.strip() for x in raw_directors_id if isinstance(x, str) and re.match(r"^nm\d+$", x.strip())]
            writers = [x.strip() for x in raw_writers if isinstance(x, str) and x.strip()]
            writers_id = [x.strip() for x in raw_writers_id if isinstance(x, str) and re.match(r"^nm\d+$", x.strip())]
            stars = [x.strip() for x in raw_stars if isinstance(x, str) and x.strip()]
            stars_id = [x.strip() for x in raw_stars_id if isinstance(x, str) and re.match(r"^nm\d+$", x.strip())]

        first_director_id = directors_id[0].strip() if isinstance(directors_id, list) and directors_id else ""
        first_director_name = directors[0].strip() if isinstance(directors, list) and directors else ""
        has_valid_director = bool(re.match(r"^nm\d+$", first_director_id)) and bool(first_director_name) and first_director_name.lower() != "n/a"

        if has_valid_director:
            imdb_id = first_director_id
            english_name = first_director_name
            chinese_name = ""
        else:
            if meta.unattended and not meta.unattended_confirm:
                logger.info(f"{self.tracker}: [yellow]Unattended mode: Director details required for movie missing in database. Skipping {self.tracker} upload.[/yellow]")
                meta.skipping = f"{self.tracker}"
                return {}
            logger.info(f"{self.tracker}: This movie is not registered in the {self.tracker} database, please enter the details of 1 director")

            imdb_id = ""
            while not re.match(r"^nm\d+$", imdb_id):
                imdb_id_raw = await prompt_in_thread(cli_ui.ask_string, "Enter Director IMDb ID (e.g., nm0000138): ")
                imdb_id = (imdb_id_raw or "").strip()
                if not re.match(r"^nm\d+$", imdb_id):
                    logger.info(f"{self.tracker}: [red]Invalid IMDb person ID. Format must be like nm0000138.[/red]")

            english_name = ""
            while not english_name:
                english_name_raw = await prompt_in_thread(cli_ui.ask_string, "Enter Director English name: ")
                english_name = (english_name_raw or "").strip()
                if not english_name:
                    logger.info(f"{self.tracker}: [red]Director English name cannot be empty.[/red]")

            chinese_name_raw = await prompt_in_thread(cli_ui.ask_string, "Enter Director Chinese name (optional, press Enter to skip): ")
            chinese_name = (chinese_name_raw or "").strip()

        artists: list[str] = [english_name]
        artist_ids: list[str] = [imdb_id]
        importances: list[str] = ["1"]  # 1 = director (main artist)
        artist_subs: list[str] = [chinese_name if chinese_name else ""]
        characters: list[str] = [""]

        # Add writer entries (best-effort).
        if isinstance(writers, list) and isinstance(writers_id, list):
            for idx, writer_name_value in enumerate(writers):
                writer_name = writer_name_value.strip()
                if not writer_name or writer_name.lower() == "n/a":
                    continue
                writer_id = writers_id[idx].strip() if idx < len(writers_id) else ""
                if not re.match(r"^nm\d+$", writer_id):
                    continue
                if writer_id in artist_ids:
                    continue
                artists.append(writer_name)
                artist_ids.append(writer_id)
                importances.append("2")  # 2 = writer
                artist_subs.append("")
                characters.append("")

        # Add cast entries (best-effort) so new groups include actor info.
        if isinstance(stars, list) and isinstance(stars_id, list):
            for idx, star_name_value in enumerate(stars):
                star_name = star_name_value.strip()
                if not star_name or star_name.lower() == "n/a":
                    continue
                star_id = stars_id[idx].strip() if idx < len(stars_id) else ""
                if not re.match(r"^nm\d+$", star_id):
                    continue
                if star_id in artist_ids:
                    continue
                artists.append(star_name)
                artist_ids.append(star_id)
                importances.append("6")  # 6 = actor
                artist_subs.append("")
                characters.append(cast_character_map.get(star_id, "Unknown"))

        post_data: dict[str, Any] = {
            "artist_ids[]": artist_ids,
            "artists[]": artists,
            "importance[]": importances,
            "characters[]": characters,
            "artists_sub[]": artist_subs,
        }
        return post_data

    async def _fetch_gpw_movie_info(self, meta: Meta, data_source: str, identifier: str) -> dict[str, Any]:
        if not data_source or not identifier:
            return {}

        endpoint_candidates: list[tuple[str, dict[str, str], bool, str]] = [
            (
                f"{self.base_url}/upload.php",
                {
                    "action": "movie_info",
                    "source": data_source,
                    "identifier": identifier,
                },
                True,
                "get",
            ),
            (
                f"{self.base_url}/api.php",
                {
                    "api_key": self.api_key,
                    "action": "movie_info",
                    "imdbid": identifier,
                },
                False,
                "get",
            ),
        ]

        cookies: Any = None
        best_response: dict[str, Any] = {}
        best_score = -1
        for url, params, use_cookies, method in endpoint_candidates:
            try:
                if use_cookies and cookies is None:
                    cookies = await self.load_cookies(meta)

                request_cookies = cookies if use_cookies and cookies else None
                async with httpx.AsyncClient(
                    timeout=15,
                    cookies=request_cookies,
                    headers={"User-Agent": f"{meta.ua_name} {(meta.current_version if meta.current_version is not None else 'github.com/wastaken7/Upload-Assistant')}"},
                ) as client:
                    if method == "post":
                        response = await client.post(url, data=params)
                    else:
                        response = await client.get(url, params=params)
                response.raise_for_status()
                payload: Any = response.json()
                if not isinstance(payload, dict):
                    continue
                status_value = str(payload.get("status", "")).strip().lower()
                if status_value in {"success", "ok", "200"} or payload.get("status") == 200:
                    response_data = payload.get("response")
                    if isinstance(response_data, dict):
                        full_credits_value = response_data.get("FullCredits") or response_data.get("fullCredits")
                        score = len(full_credits_value) if isinstance(full_credits_value, list) else 0
                        if score > best_score:
                            best_response = response_data
                            best_score = score
                        if score >= 10:
                            return response_data
            except (ValueError, KeyError, TypeError, IndexError) as e:
                logger.debug(f"{self.tracker}: Failed to process response payload on {self.tracker}: {escape(str(e))}", exc_info=True)
                continue

        return best_response

    def _get_movie_type(self, meta: Meta) -> str:
        movie_type = ""
        imdb_info = meta.imdb_info
        if imdb_info:
            imdb_type = imdb_info.get("type", "movie").lower()
            if imdb_type in ("movie", "tv movie", "tvmovie", "video"):
                runtime = int(imdb_info.get("runtime", "60"))
                movie_type = "1" if runtime >= 45 or runtime == 0 else "2"  # Feature Film/Short Film

        return movie_type

    def get_source(self, meta: Meta) -> str:
        source_type = str(meta.type).lower()

        if source_type == "disc":
            is_disc = str(meta.is_disc).upper()
            if is_disc == "BDMV":
                return "Blu-ray"
            if is_disc in ("HDDVD", "DVD"):
                return "DVD"
            return "Other"

        keyword_map = {
            "webdl": "WEB",
            "webrip": "WEB",
            "web": "WEB",
            "remux": "Blu-ray",
            "encode": "Blu-ray",
            "bdrip": "Blu-ray",
            "brrip": "Blu-ray",
            "hdtv": "HDTV",
            "sdtv": "TV",
            "dvdrip": "DVD",
            "hd-dvd": "HD-DVD",
            "dvdscr": "DVD",
            "pdtv": "TV",
            "uhdtv": "HDTV",
            "vhs": "VHS",
            "tvrip": "TVRip",
        }

        return keyword_map.get(source_type, "Other")

    def get_processing(self, meta: Meta) -> str:
        type_map = {"ENCODE": "Encode", "REMUX": "Remux", "DIY": "DIY", "UNTOUCHED": "Untouched"}
        release_type = str(meta.type).strip().upper()
        return type_map.get(release_type, "Untouched")

    def get_media_flags(self, meta: Meta) -> dict[str, str]:
        audio = meta.audio.lower()
        hdr = meta.hdr
        bit_depth = meta.bit_depth
        channels = meta.channels

        flags: dict[str, str] = {}

        # audio flags
        if "atmos" in audio:
            flags["dolby_atmos"] = "on"

        if "dts:x" in audio:
            flags["dts_x"] = "on"

        if channels == "5.1":
            flags["audio_51"] = "on"

        if channels == "7.1":
            flags["audio_71"] = "on"

        # video flags
        if not hdr.strip() and bit_depth == "10":
            flags["10_bit"] = "on"

        if "DV" in hdr:
            flags["dolby_vision"] = "on"

            if "HDR" in hdr:
                flags["hdr10plus" if "HDR10+" in hdr else "hdr10"] = "on"

        return flags

    def get_resolution(self, meta: Meta) -> str:
        resolution = meta.resolution.lower()
        source = str(meta.source).upper()

        if source in ["NTSC", "PAL"]:
            return source.upper()
        if resolution.lower() in ["480p", "576p", "720p", "1080i", "1080p", "2160p"]:
            return resolution.lower()
        return "Other"

    async def fetch_data(self, meta: Meta) -> dict[str, Any]:
        await self.load_localized_data(meta)  #  keep this line FIRST to ensure localized data is loaded before proceeding
        await self.get_groupid(meta)
        remaster_title = self.get_remaster_title(meta)
        codec = self.get_codec(meta)
        container = self.get_container(meta)

        data: dict[str, Any] = {}

        if not GreatPosterWall.group_id:
            data.update(await self.get_additional_data(meta))

        data.update(
            {
                "codec_other": meta.video_codec if codec == "Other" else "",
                "codec": codec,
                "container_other": meta.container if container == "Other" else "",
                "container": container,
                "mediainfo[]": await self.get_media_info(meta),
                "movie_edition_information": "on" if remaster_title else "",
                "processing_other": self.get_processing_other(meta) if meta.type == "DISC" else "",
                "processing": self.get_processing(meta),
                "release_desc": await self.get_release_desc(meta),
                "remaster_custom_title": "",
                "remaster_title": remaster_title,
                "remaster_year": "",
                "resolution_height": "",
                "resolution_width": "",
                "resolution": self.get_resolution(meta),
                "source_other": "",
                "source": self.get_source(meta),
                "submit": "true",
                "subtitle_type": ("2" if meta.hardcoded_subs else "1" if meta.subtitle_languages else "3"),
                "subtitles[]": await self.get_subtitle(meta),
            }
        )
        if GreatPosterWall.group_id:
            data["groupid"] = GreatPosterWall.group_id

        if await self.get_ch_dubs(meta):
            data.update({"chinese_dubbed": "on"})

        if meta.sfx_subtitles:
            data.update({"special_effects_subtitles": "on"})

        if meta.scene:
            data.update({"scene": "on"})

        if meta.personalrelease:
            if meta.is_disc:
                data.update({"buy": "on"})
            else:
                data.update({"diy": "on"})

        exclusive_flag = None
        if meta.exclusive or self.tracker_config.get("exclusive", False):
            exclusive_flag = "1"
        if exclusive_flag:
            data.update({"jinzhuan": "on"})

        data.update(self.get_media_flags(meta))

        return data

    async def upload(self, meta: Meta) -> bool:
        if getattr(meta, "skipping", None) == self.tracker:
            return False
        await self.common.create_torrent_for_upload(meta, self.tracker, self.source_flag)
        data = await self.fetch_data(meta)
        if getattr(meta, "skipping", None) == self.tracker:
            return False

        if not meta.debug:
            response_data = ""
            torrent_id = ""
            upload_url = f"{self.base_url}/api.php?api_key={self.api_key}&action=upload"
            torrent_path = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/[{self.tracker}].torrent"

            async with aiofiles.open(torrent_path, "rb") as torrent_file:
                torrent_bytes = await torrent_file.read()
            files = {"file_input": (f"{self.tracker}.placeholder.torrent", torrent_bytes, "application/x-bittorrent")}

            try:
                async with httpx.AsyncClient(timeout=30) as client:

                    def _extract_torrent_id(payload: Any) -> str:
                        if isinstance(payload, dict):
                            torrent_id_value = payload.get("torrent_id")
                            return str(torrent_id_value) if torrent_id_value is not None else ""
                        if isinstance(payload, list) and payload:
                            first_item = payload[0]
                            if isinstance(first_item, dict):
                                torrent_id_value = first_item.get("torrent_id")
                                return str(torrent_id_value) if torrent_id_value is not None else ""
                        return ""

                    response = await client.post(url=upload_url, files=files, data=data)
                    try:
                        response_data = response.json()
                    except Exception as e:
                        logger.info(f"{self.tracker}: Failed to decode JSON response: {e}")
                        return False

                    if not isinstance(response_data, dict):
                        meta.tracker_status[self.tracker]["status_message"] = f"data error: Invalid API response: {response_data}"
                        return False

                    status_value = str(response_data.get("status", "")).strip().lower()
                    response_payload = response_data.get("response")
                    torrent_id_from_payload = _extract_torrent_id(response_payload)

                    success_status = status_value in ("success", "ok", "200")
                    if success_status and torrent_id_from_payload:
                        torrent_id = torrent_id_from_payload
                        meta.tracker_status[self.tracker]["torrent_id"] = torrent_id
                        meta.tracker_status[self.tracker]["status_message"] = "Torrent uploaded successfully."
                        await self.common.create_torrent_ready_to_seed(meta, self.tracker, self.source_flag, self.announce, self.torrent_url + torrent_id)
                        return True

                    error_message = str(response_data.get("error") or response_data.get("message") or "Upload failed")
                    duplicate_phrase = "the exact same torrent file already exists on the site"
                    if duplicate_phrase in error_message.lower():
                        meta.tracker_status[self.tracker]["status_message"] = "data error: Torrent already exists on GREATPOSTERWALL (duplicate file)."
                        return False

                    meta.tracker_status[self.tracker]["status_message"] = f"data error: {error_message}."
                    return False

            except httpx.TimeoutException:
                meta.tracker_status[self.tracker]["status_message"] = "data error: Request timed out after 10 seconds"
                return False
            except httpx.RequestError as e:
                meta.tracker_status[self.tracker]["status_message"] = f"data error: Unable to upload. Error: {e}."
                return False
            except Exception as e:
                meta.tracker_status[self.tracker]["status_message"] = f"data error: It may have uploaded, go check. Error: {e}."
                return False

        else:
            logger.info(f"{self.tracker}: Request Data:")
            logger.info(Redaction.redact_private_info(data))
            meta.tracker_status[self.tracker]["status_message"] = "Debug mode enabled, not uploading."
            await self.common.create_torrent_for_upload(meta, f"{self.tracker}" + "_DEBUG", f"{self.tracker}" + "_DEBUG", announce_url="https://fake.tracker")
            return True

    async def get_name(self, meta: Meta) -> str:
        return meta.title
