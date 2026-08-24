# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import asyncio
import json
import re
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar, cast
from urllib.parse import urlparse

import aiofiles
import cli_ui
import httpx
import requests
import tmdbsimple as tmdb

from src.bbcode import BBCODE
from src.cogs.redaction import Redaction
from src.console import logger
from src.meta import Meta
from src.rehostimages import ImageHostPolicy, RehostImagesManager
from src.tracker_images import get_tracker_image_collection
from src.trackers.common import Common

Config = dict[str, Any]


class TVChaosUK:
    """
    TVC Private Torrent Tracker
    """

    base_url = "https://tvchaosuk.com"

    auth_type = "other_api"
    tracker = "TVCHAOSUK"
    display_name = "TVChaosUK"
    allows_bloated_audio = True
    source_flag = "TVCHAOS"
    signature = ""
    banned_groups = ()
    approved_image_hosts = ("imgbb", "imgbox", "pixhost", "bam", "onlyimage")
    image_host_policy = ImageHostPolicy(
        {
            "ibb.co": "imgbb",
            "imgbox.com": "imgbox",
            "pixhost.to": "pixhost",
            "imagebam.com": "bam",
            "onlyimage.org": "onlyimage",
        },
        approved_image_hosts,
    )
    upload_url = f"{base_url}/api/torrents/upload"
    search_url = f"{base_url}/api/torrents/filter"
    torrent_url = f"{base_url}/torrents/"
    tv_type_map: ClassVar = {
        "comedy": "29",
        "current affairs": "45",
        "documentary": "5",
        "drama": "11",
        "entertainment": "14",
        "factual": "19",
        "foreign": "43",
        "holding bin": "53",
        "kids": "32",
        "movies": "44",
        "news": "54",
        "reality": "52",
        "sci-fi": "33",
        "soaps": "30",
        "sport": "42",
    }
    supported_categories = ("TV", "MOVIE")
    tracker_urls = ("https://tvchaosuk.com",)
    # Constants for the class
    DEFAULT_LOGO_SIZE = "300"
    SCREENSHOT_THUMB_SIZE = "350"
    COMPARISON_COLLAPSE_THRESHOLD = 1000
    MIN_SCREENSHOTS_REQUIRED = 2

    def __init__(self, config: Config) -> None:
        self.config: Config = config
        self.rehost_images_manager = RehostImagesManager(config)
        tmdb.API_KEY = config["DEFAULT"]["tmdb_api"]

        # TV type mapping as a dict for clarity and maintainability

    def format_date_ddmmyyyy(self, date_str: str) -> str:
        """
        Convert a date string from 'YYYY-MM-DD' to 'DD-MM-YYYY'.

        Args:
            date_str (str): Input date string.

        Returns:
            str: Reformatted date string, or the original if parsing fails.
        """
        try:
            return datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=UTC).strftime("%d-%m-%Y")
        except ValueError, TypeError:
            return date_str

    async def _read_base_description(self, meta: Meta) -> str:
        """Load a saved base description without blocking the event loop."""
        from src.description_review import get_base_description

        draft_meta = meta.copy()
        description = await asyncio.to_thread(get_base_description, draft_meta)
        for key in ("description", "description_override", "saved_description"):
            meta[key] = draft_meta.get(key)
        return description

    def _ensure_desc_directory(self, meta: Meta, tracker: str) -> str:
        """Create description directory and return file path."""
        desc_dir = Path(meta.base_dir) / "tmp" / meta.uuid
        Path(desc_dir).mkdir(parents=True, exist_ok=True)
        return str(Path(desc_dir) / f"[{tracker}]DESCRIPTION.txt")

    def _build_disc_info(self, discs: list[dict[str, Any]]) -> str:
        """
        Build disc information section.

        Note: TVCHAOSUK does not currently accept BDMV/Blu-ray disc releases (only HDTV and WEB-DL).
        This method exists for code compatibility/future use and will not be called during
        normal TVCHAOSUK uploads due to the disc blocking in search_existing().
        """
        parts: list[str] = []

        # Process all discs uniformly
        for disc in discs:
            if disc["type"] == "BDMV":
                name = disc.get("name", "BDINFO")
                parts.append(f"[center][spoiler={name}][code]{disc['summary']}[/code][/spoiler][/center]\n\n")
            elif disc["type"] == "DVD":
                # For first DVD disc, use VOB MediaInfo label
                if not parts:  # First disc
                    parts.append(f"[center][spoiler=VOB MediaInfo][code]{disc['vob_mi']}[/code][/spoiler][/center]\n\n")
                else:  # Subsequent DVD discs
                    vob_name = Path(disc["vob"]).name
                    ifo_name = Path(disc["ifo"]).name
                    parts.append(
                        f"[center]{disc['name']}:\n"
                        f"[spoiler={vob_name}][code]{disc['vob_mi']}[/code][/spoiler] "
                        f"[spoiler={ifo_name}][code]{disc['ifo_mi']}[/code][/spoiler][/center]\n\n"
                    )

        return "".join(parts)

    def _build_movie_desc(self, meta: Meta, image_list: list[dict[str, Any]]) -> str:
        """Build description for movie releases (multi-block, no pre tags)."""
        parts: list[str] = []

        # Release date info in its own center block
        rd_info = self._get_movie_release_info(meta)
        if rd_info:
            parts.append(f"[center]{rd_info}[/center]\n\n")

        # Logo in its own center block
        if meta.logo:
            logo_size = self.config["DEFAULT"].get("logo_size", self.DEFAULT_LOGO_SIZE)
            parts.append(f"[center][img={logo_size}]{meta.logo}[/img][/center]\n\n")

        # Title - plain text
        parts.append(f"[center][b]Movie Title:[/b] {(meta.title if meta.title is not None else 'Unknown Movie')}[/center]\n\n")

        # Overview - plain text
        overview = meta.overview.strip()
        if overview:
            parts.append(f"[center]{overview}[/center]\n\n")

        # Release date
        if "release_date" in meta:
            formatted_date = self.format_date_ddmmyyyy(meta.release_date)
            parts.append(f"[center][b]Released on:[/b] {formatted_date}[/center]\n\n")

        # External links
        links = self.get_links(meta).strip()
        if links:
            parts.append(f"[center]{links}[/center]\n\n")

        # Screenshots
        screenshots = self._add_screenshots(meta, image_list).strip()
        if screenshots:
            parts.append(f"[center]{screenshots}[/center]\n\n")

        return "".join(parts)

    def _build_tv_pack_desc(self, meta: Meta, image_list: list[dict[str, Any]]) -> str:
        """Build description for TV pack releases (multi-block, no pre tags)."""
        parts: list[str] = []

        # Logo in its own center block
        if meta.logo:
            logo_size = self.config["DEFAULT"].get("logo_size", self.DEFAULT_LOGO_SIZE)
            parts.append(f"[center][img={logo_size}]{meta.logo}[/img][/center]\n\n")

        # Series info (optional - only if season data exists)
        if "season_air_first_date" in meta:
            channel = meta.networks if meta.networks is not None else "N/A"
            airdate = self.format_date_ddmmyyyy(meta.season_air_first_date or "")
            series_name = meta.season_name if meta.season_name is not None else "Unknown Series"

            parts.append(f"[center][b]Series Title:[/b] {series_name}[/center]\n")
            parts.append(f"[center][b]This series premiered on:[/b] {channel} on {airdate}[/center]\n\n")

        # Episode list (optional)
        if meta.episodes:
            episode_list = self._build_episode_list(meta.episodes)
            parts.append(f"[center][b]Episode List[/b]\n{episode_list}[/center]\n\n")

        # External links (always attempt to add)
        links = self.get_links(meta).strip()
        if links:
            parts.append(f"[center]{links}[/center]\n\n")

        # Screenshots (always attempt to add)
        screenshots = self._add_screenshots(meta, image_list).strip()
        if screenshots:
            parts.append(f"[center]{screenshots}[/center]\n\n")

        return "".join(parts)

    def _build_episode_desc(self, meta: Meta, image_list: list[dict[str, Any]]) -> str:
        """Build description for single episode releases (multi-block, no pre tags)."""
        parts: list[str] = []

        # Logo in its own center block
        if meta.logo:
            logo_size = self.config["DEFAULT"].get("logo_size", self.DEFAULT_LOGO_SIZE)
            parts.append(f"[center][img={logo_size}]{meta.logo}[/img][/center]\n\n")

        # Episode title - plain text in center block (optional)
        episode_name = meta.episode_name.strip()
        if episode_name:
            parts.append(f"[center][b]Episode Title:[/b] {episode_name}[/center]\n\n")

        # Overview - plain text in center block (optional)
        overview = meta.episode_overview.strip()
        if overview:
            parts.append(f"[center]{overview}[/center]\n\n")

        # Broadcast info (optional)
        if meta.episode_airdate:
            channel = meta.networks if meta.networks is not None else "N/A"
            formatted_date = self.format_date_ddmmyyyy(meta.episode_airdate)
            parts.append(f"[center][b]Broadcast on:[/b] {channel} on {formatted_date}[/center]\n\n")

        # External links (always attempt to add)
        links = self.get_links(meta).strip()
        if links:
            parts.append(f"[center]{links}[/center]\n\n")

        # Screenshots (always attempt to add)
        screenshots = self._add_screenshots(meta, image_list).strip()
        if screenshots:
            parts.append(f"[center]{screenshots}[/center]\n\n")

        return "".join(parts)

    def _build_fallback_desc(self, meta: Meta) -> str:
        """Build fallback description for other categories."""
        overview = meta.overview.strip()
        if overview:
            return f"[center]{overview}[/center]\n\n"
        return ""

    def _get_movie_release_info(self, meta: Meta) -> str:
        """Extract movie release date information."""
        if not meta.release_dates:
            return meta.release_date

        parts: list[str] = []
        for cc in meta.release_dates["results"]:
            for rd in cc["release_dates"]:
                if rd["type"] == 6:  # TV release
                    channel = rd.get("note") or "N/A Channel"
                    parts.append(f"[color=orange][size=15]{cc['iso_3166_1']} TV Release info [/size][/color]\n{str(rd['release_date'])[:10]} on {channel}\n")

        return "".join(parts)

    def _build_episode_list(self, episodes: list[dict[str, Any]]) -> str:
        """Build formatted episode list."""
        parts: list[str] = []

        for ep in episodes:
            ep_num = ep.get("code", "")
            ep_title = ep.get("title", "").strip()
            ep_date = ep.get("airdate", "")
            ep_overview = ep.get("overview", "").strip()

            # Episode number and title
            parts.append(f"[b]{ep_num}[/b]")
            if ep_title:
                parts.append(f" - {ep_title}")
            if ep_date:
                formatted_date = self.format_date_ddmmyyyy(ep_date)
                parts.append(f" ({formatted_date})")
            parts.append("\n")

            # Overview
            if ep_overview:
                parts.append(f"{ep_overview}\n")

        return "".join(parts)

    def _add_screenshots(self, meta: Meta, image_list: list[dict[str, Any]]) -> str:
        """Add screenshots section if requirements are met."""
        screens_count = meta.screens or 0
        required_count = self.config["TRACKERS"][self.tracker].get("image_count", self.MIN_SCREENSHOTS_REQUIRED)

        if not image_list or screens_count < required_count:
            return ""

        parts = ["[b]Screenshots[/b]\n"]

        for img in image_list[:required_count]:
            web_url = img["web_url"]
            img_url = img["img_url"]
            parts.append(f"[url={web_url}][img={self.SCREENSHOT_THUMB_SIZE}]{img_url}[/img][/url] ")

        return "".join(parts)

    def _build_notes_section(self, base: str) -> str:
        """Build notes/extra info section."""
        return f"[center][b]Notes / Extra Info[/b]\n{base.strip()}[/center]\n\n"

    def _apply_bbcode_transforms(self, desc: str, comparison: bool) -> str:
        """Apply BBCode transformations."""
        bbcode = BBCODE()
        desc = bbcode.convert_pre_to_code(desc)
        desc = bbcode.convert_hide_to_spoiler(desc)

        if not comparison:
            desc = bbcode.convert_comparison_to_collapse(desc, self.COMPARISON_COLLAPSE_THRESHOLD)

        return desc

    def _normalize_tvc_formatting(self, desc: str) -> str:
        """Normalize whitespace for TVCHAOSUK (multi-block style)."""
        # Collapse any run of 3+ newlines into exactly 2 (preserve spacing between blocks)
        return re.sub(r"\n{3,}", "\n\n", desc)

    async def _write_description_file(self, filepath: str, content: str) -> None:
        """Write description content to file asynchronously."""
        try:

            def _write():
                with Path(filepath).open("w", encoding="utf-8") as f:
                    f.write(content)

            await asyncio.to_thread(_write)
        except OSError as e:
            logger.warning(f"{self.tracker}: [yellow]Warning: Failed to write description file: {e}[/yellow]")

    async def get_cat_id(self, genres: list[str]) -> str:
        """
        Determine TVCHAOSUK category ID based on genre list.

        Args:
            genres (list[str]): List of genre names (e.g. ["Drama", "Comedy"]).

        Returns:
            str: Category ID string from tv_type_map. Defaults to "holding bin" if no match.
        """
        # Note sections are based on Genre not type, source, resolution etc..
        # Uses tv_type_map dict for genre → category ID mapping
        if not genres:
            return self.tv_type_map["holding bin"]
        for g in genres:
            g = g.lower().replace(",", "").strip()
            if g and g in self.tv_type_map:
                return self.tv_type_map[g]

        # fallback to holding bin/misc id
        return self.tv_type_map["holding bin"]

    async def get_res_id(self, tv_pack: bool, resolution: str) -> str:
        if tv_pack:
            resolution_id = {
                "1080p": "HD1080p Pack",
                "1080i": "HD1080p Pack",
                "720p": "HD720p Pack",
                "576p": "SD Pack",
                "576i": "SD Pack",
                "540p": "SD Pack",
                "540i": "SD Pack",
                "480p": "SD Pack",
                "480i": "SD Pack",
            }.get(resolution, "SD")
        else:
            resolution_id = {"1080p": "HD1080p", "1080i": "HD1080p", "720p": "HD720p", "576p": "SD", "576i": "SD", "540p": "SD", "540": "SD", "480p": "SD", "480i": "SD"}.get(
                resolution, "SD"
            )
        return resolution_id

    async def append_country_code(self, meta: Meta, name: str) -> str:
        """
        Append ISO country code suffix to release name based on origin_country_code.

        Args:
            meta (dict): Metadata containing 'origin_country_code' list.
            name (str): Base release name.

        Returns:
            str: Release name with appended country code (e.g. "Show Title [IRL]").
        """
        country_map = {
            "AT": "AUT",
            "AU": "AUS",
            "BE": "BEL",
            "CA": "CAN",
            "CH": "CHE",
            "CZ": "CZE",
            "DE": "GER",
            "DK": "DNK",
            "EE": "EST",
            "ES": "SPA",
            "FI": "FIN",
            "FR": "FRA",
            "IE": "IRL",
            "IS": "ISL",
            "IT": "ITA",
            "NL": "NLD",
            "NO": "NOR",
            "NZ": "NZL",
            "PL": "POL",
            "PT": "POR",
            "RU": "RUS",
            "SE": "SWE",
        }

        if meta.origin_country_code:
            for code in meta.origin_country_code:
                if code in country_map:
                    name += f" [{country_map[code]}]"
                    break  # append only the first match

        return name

    async def read_file(self, path: str, encoding: str = "utf-8") -> str:
        """
        Async helper to read a text file safely.
        Uses a with-block to ensure the file handle is closed.
        """

        def _read():
            with Path(path).open(encoding=encoding) as f:
                return f.read()

        return await asyncio.to_thread(_read)

    async def get_name(self, meta: Meta) -> str:
        # Naming logic
        if meta.type == "ENCODE" and ("bluray" in str(meta.path).lower() or "brrip" in str(meta.path).lower() or "bdrip" in str(meta.path).lower()):
            release_type = "BRRip"
        else:
            release_type = str(meta.type).replace("WEBDL", "WEB-DL")

        if meta.category == "MOVIE":
            year_str_val = str(meta.year) if meta.year is not None else ""
            tvc_name = f"{meta.title} ({year_str_val}) [{meta.resolution} {release_type} {str(meta.video[-3:]).upper()}]"
        elif meta.category == "TV":
            # Use safe lookups to avoid KeyError if 'search_year' is missing
            search_year = meta.search_year
            # If search_year is empty, fall back to year
            year = search_year if search_year else (meta.year if meta.year is not None else "")
            if meta.no_year:
                year = ""
            year_str = f" ({year})" if year else ""

            if meta.tv_pack:
                season_first = (meta.season_air_first_date or "")[:4]
                season_year = season_first or year
                tvc_name = f"{meta.title} - Series {meta.season_int} ({season_year}) [{meta.resolution} {release_type} {str(meta.video[-3:]).upper()}]"
            else:
                if meta.episode_airdate:
                    formatted_date = self.format_date_ddmmyyyy(meta.episode_airdate)
                    tvc_name = f"{meta.title}{year_str} {meta.season}{meta.episode} ({formatted_date}) [{meta.resolution} {release_type} {str(meta.video[-3:]).upper()}]"
                else:
                    tvc_name = f"{meta.title}{year_str} {meta.season}{meta.episode} [{meta.resolution} {release_type} {str(meta.video[-3:]).upper()}]"
        else:
            # Defensive guard for unsupported categories
            raise ValueError(f"Unsupported category for TVCHAOSUK: {meta.category}")

        # Add original language title if foreign
        original_lang = str(meta.original_language)
        is_foreign = False
        if original_lang and not original_lang.startswith("en") and original_lang not in ["ga", "gd", "cy"]:
            is_foreign = True
        elif not original_lang:
            mi = meta.mediainfo if not meta.is_disc else meta.bdinfo if meta.bdinfo else {}
            if isinstance(mi, dict) and mi:
                audio_langs = self.get_audio_languages(mi)
                if audio_langs and "English" not in audio_langs:
                    is_foreign = True

        if is_foreign and meta.original_title and meta.original_title != meta.title:
            tvc_name = tvc_name.replace(meta.title, f"{meta.title} ({meta.original_title})")

        if not meta.is_disc:
            # We need to make sure subs are fetched before checking eng_subs/sdh_subs
            mi = meta.mediainfo
            self.get_subs_info(meta, mi)

        if meta.video_codec == "HEVC":
            tvc_name = tvc_name.replace("]", " HEVC]")
        if meta.eng_subs:
            tvc_name = tvc_name.replace("]", " SUBS]")
        if meta.sdh_subs:
            tvc_name = tvc_name.replace(" SUBS]", " (ENG + SDH SUBS)]") if meta.eng_subs else tvc_name.replace("]", " (SDH SUBS)]")

        return await self.append_country_code(meta, tvc_name)

    async def upload(self, meta: Meta) -> bool | None:
        common = Common(config=self.config)

        raw_images = get_tracker_image_collection(meta, self.tracker, "screenshots")
        image_list_seq: list[Any]
        if isinstance(raw_images, list):
            image_list_seq = raw_images
        elif isinstance(raw_images, tuple):
            image_list_seq = list(cast(tuple[Any, ...], raw_images))
        else:
            image_list_seq = []
        image_list = [cast(dict[str, Any], img) for img in image_list_seq]

        await common.create_torrent_for_upload(meta, self.tracker, self.source_flag)
        await self.get_tmdb_data(meta)

        # load MediaInfo.json
        try:
            content = await self.read_file(f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/MediaInfo.json")
            mi = cast(dict[str, Any], json.loads(content))
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.warning(f"{self.tracker}: [yellow]Warning: Could not load MediaInfo.json: {e}")
            mi = {}

        cat_id = await self.get_cat_id(meta.genres) if meta.category == "TV" else "44"
        meta.language_checked = True

        # Foreign category check based on TMDB original_language only
        original_lang = str(meta.original_language)
        if original_lang and not original_lang.startswith("en") and original_lang not in ["ga", "gd", "cy"]:
            cat_id = self.tv_type_map["foreign"]
        elif not original_lang:
            # Fallback: inspect audio languages from MediaInfo if TMDB data is missing
            audio_langs = self.get_audio_languages(mi)
            if audio_langs and "English" not in audio_langs:
                cat_id = self.tv_type_map["foreign"]
        resolution_id = await self.get_res_id(meta.tv_pack, meta.resolution)

        anon = 0 if meta.anon == 0 and not self.config["TRACKERS"][self.tracker].get("anon", False) else 1

        if meta.bdinfo:
            mi_dump = None
            bd_dump = await self.read_file(f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/BD_SUMMARY_00.txt")
        else:
            mi_dump = await self.read_file(f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/MEDIAINFO.txt")
            bd_dump = None

        # build description and capture return instead of reopening file
        descfile_path = Path(meta.base_dir) / "tmp" / meta.uuid / f"[{self.tracker}]DESCRIPTION.txt"
        desc = await self.edit_desc(meta, self.tracker, self.signature, image_list)

        if not desc:
            logger.warning(f"{self.tracker}: [yellow]Warning: tracker-specific description file not found at {descfile_path}")
            desc = ""

        # Naming logic is handled by get_name
        tvc_name = await self.get_name(meta)

        upload_to_tvc = True
        if meta.unattended is False:
            upload_to_tvc = cli_ui.ask_yes_no(f"Upload to {self.tracker} with the name {tvc_name}?", default=False)
            if not upload_to_tvc:
                tvc_name = cli_ui.ask_string("Please enter New Name:") or tvc_name
                upload_to_tvc = cli_ui.ask_yes_no(f"Upload to {self.tracker} with the name {tvc_name}?", default=False)

        data: dict[str, str | int] = {
            "name": tvc_name,
            "description": desc,
            "mediainfo": mi_dump if mi_dump else "",
            "bdinfo": bd_dump if bd_dump else "",
            "category_id": cat_id,
            "type": resolution_id,
            "tmdb": meta.tmdb or 0,
            "imdb": meta.imdb or 0,
            "tvdb": meta.tvdb_id or 0,
            "mal": meta.mal_id or 0,
            "igdb": 0,
            "anonymous": anon,
            "stream": int(meta.stream),
            "sd": int(meta.sd),
            "keywords": ", ".join(meta.keywords),
            "personal_release": int(meta.personalrelease),
            "internal": 0,
            "featured": 0,
            "free": 0,
            "doubleup": 0,
            "sticky": 0,
        }
        if meta.category == "TV":
            data["season_number"] = meta.season_int if meta.season_int is not None else "0"
            data["episode_number"] = meta.episode_int if meta.episode_int is not None else "0"

        if upload_to_tvc is False:
            return None

        torrent_path = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/[{self.tracker}].torrent"

        if meta.debug is False:
            response = None
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    async with aiofiles.open(torrent_path, "rb") as open_torrent:
                        torrent_bytes = await open_torrent.read()
                    files = {"torrent": (Path(torrent_path).name, torrent_bytes)}
                    response = await client.post(
                        self.upload_url,
                        files=files,
                        data=data,
                        headers={"User-Agent": "Mozilla/5.0"},
                        params={"api_token": self.config["TRACKERS"][self.tracker]["api_key"].strip()},
                    )

                if response.status_code != 200:
                    if response.status_code == 403:
                        meta.tracker_status[self.tracker]["status_message"] = "data error: Forbidden (403). This may indicate that you do not have upload permission."
                    elif response.status_code in (301, 302, 303, 307, 308):
                        meta.tracker_status[self.tracker]["status_message"] = f"data error: Redirect ({response.status_code}). Please verify that your API key is valid."
                    else:
                        meta.tracker_status[self.tracker]["status_message"] = f"data error: HTTP {response.status_code} - {response.text}"
                    return None
                # TVCHAOSUK returns "application/x-bittorrent\n{json}" so strip the prefix
                json_data = json.loads(response.text.split("\n", 1)[-1])
                meta.tracker_status[self.tracker]["status_message"] = json_data

                # Extract torrent ID robustly from returned URL
                data_str = json_data.get("data")
                if not isinstance(data_str, str):
                    raise ValueError(f"Invalid TVCHAOSUK response: 'data' missing or not a string: {data_str}")

                parsed = urlparse(data_str)
                segments = [seg for seg in parsed.path.split("/") if seg]
                if not segments:
                    raise ValueError(f"Invalid TVCHAOSUK response format: no path segments in {data_str}")

                # Use last segment as torrent ID
                t_id = segments[-1]
                meta.tracker_status[self.tracker]["torrent_id"] = t_id

                await common.create_torrent_ready_to_seed(
                    meta, self.tracker, self.source_flag, self.config["TRACKERS"][self.tracker].get("announce_url"), f"{self.base_url}/torrents/{t_id}"
                )
                return True

            except httpx.TimeoutException:
                meta.tracker_status[self.tracker]["status_message"] = "data error: Request timed out after 30 seconds"
                return False
            except httpx.RequestError as e:
                meta.tracker_status[self.tracker]["status_message"] = f"data error: Unable to upload. Error: {e}.\nResponse: {(response.text) if response else 'No response'}"
                return False
            except Exception as e:
                meta.tracker_status[self.tracker]["status_message"] = (
                    f"data error: It may have uploaded, go check. Error: {e}.\nResponse: {(response.text) if response else 'No response'}"
                )
                return False

        else:
            logger.info(f"{self.tracker}: Request Data:")
            logger.info(Redaction.redact_private_info(data))
            tracker_status = meta.tracker_status
            tracker_status.setdefault(self.tracker, {})
            tracker_status[self.tracker]["status_message"] = "Debug mode enabled, not uploading."
            await common.create_torrent_for_upload(meta, f"{self.tracker}" + "_DEBUG", f"{self.tracker}" + "_DEBUG", announce_url="https://fake.tracker")
            return True  # Debug mode - simulated success

    def get_audio_languages(self, mi: dict[str, Any]) -> list[str]:
        """
        Parse MediaInfo object and return a list of normalized audio languages.

        Args:
            mi (dict): MediaInfo JSON object.

        Returns:
            list[str]: Sorted list of audio language names (e.g. ["English", "French"]).
        """
        audio_langs: set[str] = set()
        tracks = cast(list[dict[str, Any]], mi.get("media", {}).get("track", []))
        for track in tracks:
            if track.get("@type") != "Audio":
                continue
            lang_val = track.get("Language/String") or track.get("Language/String1") or track.get("Language/String2") or track.get("Language")
            lang = str(lang_val).strip() if lang_val else ""
            if not lang:
                continue
            lowered = lang.lower()
            if lowered in {"en", "eng", "en-us", "en-gb", "en-ie", "en-au"}:
                audio_langs.add("English")
            else:
                audio_langs.add(lang.title())
        return sorted(audio_langs) if audio_langs else []

    async def get_tmdb_data(self, meta: Meta) -> dict[str, Any]:
        # Origin country codes (shared for both movies and TV)
        origin_country_code: list[str] = []
        origin_country = meta.origin_country
        if origin_country:
            if isinstance(origin_country, list):
                origin_country_list = origin_country
                origin_country_code.extend([str(code) for code in origin_country_list])
            else:
                origin_country_code.append(str(origin_country))
        elif len(meta.production_countries):
            production_countries = cast(list[dict[str, Any]], meta.production_countries)
            origin_country_code.extend([str(country["iso_3166_1"]) for country in production_countries if "iso_3166_1" in country])
        elif len(meta.production_companies):
            production_companies = cast(list[dict[str, Any]], meta.production_companies)
            origin_country_code.append(str(production_companies[0].get("origin_country", "")))
        meta.origin_country_code = origin_country_code

        if meta.category == "MOVIE":
            # Everything movie-specific is already handled
            if meta.debug and meta.tmdb is not None:
                logger.info(f"{self.tracker}: [yellow]Fetching TMDb movie details[/yellow]")
                movie = tmdb.Movies(meta.tmdb)
                response = cast(Any, movie).info()
                logger.info(f"{self.tracker}: [cyan]DEBUG: Movie data: {response}[/cyan]")
            return {}

        if meta.category == "TV":
            # TVCHAOSUK-specific extras
            if isinstance(meta.networks, list) and len(meta.networks) != 0 and "name" in meta.networks[0]:
                meta.networks = meta.networks[0]["name"]

            if meta.tmdb is None:
                year_str = str(meta.year) if meta.year is not None else ""
                meta.setdefault("season_air_first_date", f"{year_str}-N/A-N/A")
                meta.setdefault("first_air_date", f"{year_str}-N/A-N/A")
                return {}

            try:
                if not meta.tv_pack:
                    if "tmdb_episode_data" not in meta or not meta.tmdb_episode_data:
                        episode_info = cast(
                            dict[str, Any],
                            cast(Any, tmdb.TV_Episodes(meta.tmdb, meta.season_int, meta.episode_int)).info(),
                        )
                        meta.episode_airdate = episode_info.get("air_date", "")
                        meta.episode_name = episode_info.get("name", "")
                        meta.episode_overview = episode_info.get("overview", "")
                    else:
                        episode_info = cast(dict[str, Any], meta.tmdb_episode_data)
                        meta.episode_airdate = episode_info.get("air_date", "")
                        meta.episode_name = episode_info.get("name", "")
                        meta.episode_overview = episode_info.get("overview", "")
                else:
                    if "tmdb_season_data" not in meta or not meta.tmdb_season_data:
                        season_info = cast(
                            dict[str, Any],
                            cast(Any, tmdb.TV_Seasons(meta.tmdb, meta.season_int)).info(),
                        )
                        air_date = season_info.get("air_date") or ""
                        meta.season_air_first_date = air_date
                        meta.season_name = season_info.get("name", f"Season {meta.season_int}")
                        episodes: list[dict[str, str]] = []
                        for ep in cast(list[dict[str, Any]], season_info.get("episodes", [])):
                            season_num = str(ep.get("season_number", 0))
                            episode_num = str(ep.get("episode_number", 0))
                            code = f"S{season_num.zfill(2)}E{episode_num.zfill(2)}"
                            episodes.append(
                                {"code": code, "title": (ep.get("name") or "").strip(), "airdate": ep.get("air_date") or "", "overview": (ep.get("overview") or "").strip()}
                            )
                        meta.episodes = episodes
                    else:
                        season_info = cast(dict[str, Any], meta.tmdb_season_data)
                        air_date = season_info.get("air_date") or ""
                        meta.season_air_first_date = air_date
                        meta.season_name = season_info.get("name", f"Season {meta.season_int}")
                        episodes = []
                        for ep in cast(list[dict[str, Any]], season_info.get("episodes", [])):
                            season_num = str(ep.get("season_number", 0))
                            episode_num = str(ep.get("episode_number", 0))
                            code = f"S{season_num.zfill(2)}E{episode_num.zfill(2)}"
                            episodes.append(
                                {"code": code, "title": (ep.get("name") or "").strip(), "airdate": ep.get("air_date") or "", "overview": (ep.get("overview") or "").strip()}
                            )
                        meta.episodes = episodes

            except (requests.exceptions.RequestException, KeyError, TypeError) as e:
                logger.info(f"{self.tracker}: [yellow]Expected error while fetching TV episode/season info: {e}")
                logger.info(traceback.format_exc())

                logger.info(
                    f"{self.tracker}: Unable to get episode information, Make sure episode {meta.season}{meta.episode} exists in TMDB.\n"
                    f"https://www.themoviedb.org/tv/{meta.tmdb}/season/{meta.season_int}"
                )
                year_str = str(meta.year) if meta.year is not None else ""
                meta.setdefault("season_air_first_date", f"{year_str}-N/A-N/A")
                meta.setdefault("first_air_date", f"{year_str}-N/A-N/A")

        else:
            raise ValueError(f"Unsupported category for TVCHAOSUK: {meta.category}")

        return {}

    async def get_additional_checks(self, meta: Meta) -> bool:
        # UHD, Discs, remux and non-1080p HEVC are not allowed on TVCHAOSUK.
        if meta.resolution == "2160p" or (meta.is_disc or "REMUX" in str(meta.type)) or (meta.video_codec == "HEVC" and meta.resolution != "1080p"):
            logger.info(f"{self.tracker}: [bold red]No UHD, Discs, Remuxes or non-1080p HEVC allowed at TVCHAOSUK[/bold red]")
            return False
        return True

    async def search_existing(self, meta: Meta) -> list[dict[str, Any]]:  # noqa: ARG002
        # Search on TVCUK has been DISABLED due to issues, but we can still skip uploads based on criteria
        dupes: list[dict[str, Any]] = []

        logger.info(f"{self.tracker}: [red]Cannot search for dupes on TVCHAOSUK at this time.[/red]")
        logger.info(f"{self.tracker}: [red]Please make sure you are not uploading duplicates.")
        await asyncio.sleep(2)

        return dupes

    async def edit_desc(
        self,
        meta: Meta,
        tracker: str,
        signature: str,
        image_list: list[dict[str, Any]],
        comparison: bool = False,
    ) -> str:
        """
        Build and write the tracker-specific debug description file (FNP multi-block style).

        Constructs BBCode-formatted description text for discs, TV packs,
        episodes, or movies using multiple separate [center] blocks.
        Always writes a non-empty description file to tmp/<uuid>/[TVCHAOSUK]DESCRIPTION.txt.
        """
        # Read the authoritative in-memory base description.
        base = await self._read_base_description(meta)

        # Ensure output directory exists
        descfile_path = self._ensure_desc_directory(meta, tracker)

        # Build description content
        desc_parts: list[str] = []

        # Add disc information
        if meta.discs:
            desc_parts.append(self._build_disc_info(meta.discs))

        # Add content-specific sections
        if meta.category == "MOVIE":
            desc_parts.append(self._build_movie_desc(meta, image_list))
        elif meta.category == "TV" and meta.tv_pack == 1:
            desc_parts.append(self._build_tv_pack_desc(meta, image_list))
        elif meta.category == "TV" and meta.tv_pack != 1:
            desc_parts.append(self._build_episode_desc(meta, image_list))
        else:
            desc_parts.append(self._build_fallback_desc(meta))

        # Add notes section
        if base.strip() and base.strip().lower() != "ptp":
            desc_parts.append(self._build_notes_section(base))

        # Combine all parts
        desc = "".join(desc_parts)

        # Apply BBCode transformations
        desc = self._apply_bbcode_transforms(desc, comparison)

        # Remove newline(s) immediately after [center]
        desc = re.sub(r"\[center\]\s+", "[center]", desc)

        # Remove newline(s) immediately before [/center]
        desc = re.sub(r"\s+\[/center\]", "[/center]", desc)

        # Collapse any run of 3+ newlines into exactly 2 (preserve paragraph breaks)
        desc = re.sub(r"\n{3,}", "\n\n", desc)

        # Ensure non-empty description
        if not desc.strip():
            desc = "[center][i]No description available[/i][/center]\n"

        # Add signature
        if signature:
            desc += f"\n{signature}\n"

        # Write to file
        await self._write_description_file(descfile_path, desc)

        return desc

    def get_links(self, meta: Meta) -> str:
        """
        Returns a BBCode string with icon links (for multi-block layout).
        No [center] tags or extra newlines - caller handles layout.
        """
        parts = []

        link_configs = [
            ("imdb_id", lambda m: m.get("imdb_info", {}).get("imdb_url", ""), "imdb_75"),
            ("tmdb_id", lambda m: f"https://www.themoviedb.org/{m.get('category', '').lower()}/{m['tmdb_id']}", "tmdb_75"),
            ("tvdb_id", lambda m: f"https://www.thetvdb.com/?id={m['tvdb_id']}&tab=series", "tvdb_75"),
            ("tvmaze_id", lambda m: f"https://www.tvmaze.com/shows/{m['tvmaze_id']}", "tvmaze_75"),
            ("mal_id", lambda m: f"https://myanimelist.net/anime/{m['mal_id']}", "mal_75"),
        ]

        for id_key, url_func, img_key in link_configs:
            if meta.get(id_key, 0):
                url = url_func(meta)
                img = self.config.get("IMAGES", {}).get(img_key, "")
                if url and img:
                    parts.append(f"[URL={url}][img]{img}[/img][/URL] ")

        if not parts:
            return ""

        parts.insert(0, "[b]External Info Sources:[/b]\n\n")
        return "".join(parts)

    # get subs function
    # used in naming conventions

    def get_subs_info(self, meta: Meta, mi: dict[str, Any]) -> None:
        subs = ""
        subs_num = 0
        media = cast(dict[str, Any], mi.get("media") or {})
        tracks_raw: list[Any] = []
        raw_tracks = media.get("track")
        if isinstance(raw_tracks, list):
            tracks_raw = raw_tracks
        tracks = cast(list[dict[str, Any]], tracks_raw)

        # Count subtitle tracks
        for s in tracks:
            if s.get("@type") == "Text":
                subs_num += 1

        meta.has_subs = 1 if subs_num > 0 else 0
        # Reset flags to avoid stale values
        meta.pop("eng_subs", None)
        meta.pop("sdh_subs", None)

        # Collect languages and flags
        for s in tracks:
            if s.get("@type") == "Text":
                lang = s.get("Language")
                if lang and subs_num > 0:
                    lang_str = str(lang).strip()
                    if lang_str:
                        subs += lang_str + ", "
                        lowered = lang_str.lower()
                        if lowered in {"en", "eng", "en-us", "en-gb", "en-ie", "en-au", "english"}:
                            meta.eng_subs = 1
                # crude SDH detection
                if "sdh" in str(s).lower():
                    meta.sdh_subs = 1
