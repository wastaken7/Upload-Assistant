# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import datetime
import re
from pathlib import Path
from typing import Any, ClassVar, cast

import aiofiles
import httpx
from bs4 import BeautifulSoup

from cogs.redaction import Redaction
from src.console import logger
from src.cookie_auth import CookieValidator, extract_upload_error
from src.get_desc import DescriptionBuilder
from src.meta import Meta
from src.rehostimages import RehostImagesManager
from src.trackers.common import Common


class CathodeRayTube:
    """Cathode-Ray.Tube (CRT) is a Private Torrent Tracker for CLASSIC MOVIES / TV"""

    auth_type = "cookies"
    tracker = "CATHODERAYTUBE"
    display_name = "Cathode-Ray.Tube"
    source_flag = "CRT"
    base_url = "https://www.cathode-ray.tube"
    upload_url = f"{base_url}/upload.php"
    torrent_url = f"{base_url}/torrents.php"
    tracker_urls = ("signal.cathode-ray.tube",)
    supported_categories = ("MOVIE", "TV", "GAME")
    allows_bloated_audio = True
    banned_groups: tuple[str, ...] = ()
    auth_token: ClassVar[str] = ""
    approved_image_hosts = ("ptpimg", "catbox", "imgbb", "postimages", "freeimage", "imgbox")
    image_host_mapping: ClassVar = {
        "ptpimg.me": "ptpimg",
        "catbox.moe": "catbox",
        "ibb.co": "imgbb",
        "postimg.cc": "postimages",
        "iili.io": "freeimage",
        "imgbox.com": "imgbox",
    }

    category_map: ClassVar = {"MOVIE": "1", "TV": "2", "GAME": "13"}

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.common = Common(config)
        self.cookie_validator = CookieValidator(config)
        self.rehost_images_manager = RehostImagesManager(config)
        self.session = httpx.AsyncClient(timeout=60.0, follow_redirects=True)

    async def check_image_hosts(self, meta: Meta) -> None:
        """Reuse CRT-approved images or rehost them through a configured approved host."""
        await self.rehost_images_manager.check_hosts(
            meta,
            self.tracker,
            url_host_mapping=self.image_host_mapping,
            img_host_index=1,
            approved_image_hosts=list(self.approved_image_hosts),
        )

    async def validate_credentials(self, meta: Meta) -> bool:
        cookie_jar = await self.cookie_validator.load_session_cookies(meta, self.tracker)
        if cookie_jar:
            self.session.cookies = cookie_jar
            return True

        return False

    @staticmethod
    def _extract_auth_token(html: str) -> str:
        """Read the auth token exposed by CRT forms and authenticated page scripts."""
        auth_input = BeautifulSoup(html, "html.parser").select_one('input[name="auth"]')
        if auth_input and (auth := auth_input.get("value", "")):
            return str(auth)
        match = re.search(r"\bauthkey\s*=\s*['\"]([^'\"]+)['\"]", html)
        return match.group(1) if match else ""

    async def get_name(self, meta: Meta) -> str:
        """Format CRT titles according to its category-specific upload rules."""
        name = str(meta.title or meta.name).strip()
        year = str(meta.year or "").strip()
        edition = str(meta.edition or "").strip()
        category = str(meta.category).upper()

        if category == "MOVIE":
            return " ".join(part for part in (name, f"({year})" if year else "", edition) if part)

        if category == "TV":
            season = str(meta.season or "").strip()
            season_label = self._season_label(season)
            suffix = " ".join(part for part in (f"({year})" if year else "", edition) if part)
            return f"{name} - {season_label}{f' {suffix}' if suffix else ''}" if season_label else " ".join(part for part in (name, suffix) if part)

        if category == "GAME":
            platform = str(meta.platform or "").strip()
            return " ".join(part for part in (name, f"({year})" if year else "", platform) if part)

        return name

    @staticmethod
    def _season_label(season: str) -> str:
        """Convert Upload Assistant season tokens into CRT's human-readable labels."""
        if not season:
            return ""
        season_str = str(season).strip()
        if season_str.upper() == "S00":
            return "Specials"
        match = re.fullmatch(r"S(\d{1,2})", season_str, re.IGNORECASE)
        if match:
            return f"Season {int(match.group(1))}"
        if season_str.isdigit():
            return f"Season {int(season_str)}"
        return season_str

    def get_cover(self, meta: Meta) -> str:
        """Return the first cover image URL from the metadata."""
        if meta.tmdb_poster:
            return f"https://image.tmdb.org/t/p/w500{meta.tmdb_poster}"

        if meta.poster:
            return meta.poster

        if isinstance(meta.covers, list) and len(meta.covers) > 0:
            raw_url = meta.covers[0].get("raw_url")
            return str(raw_url) if raw_url else ""

        return ""

    @staticmethod
    def _has_english(values: list[str] | str | None) -> bool:
        if isinstance(values, str):
            values = [values]
        return any(str(value).strip().lower() in {"en", "eng", "english"} for value in values or [])

    def get_tags(self, meta: Meta) -> str:
        """Build common CRT tags from the available release metadata."""
        category = str(meta.category).upper()
        tags: list[str] = {"MOVIE": ["movies"], "TV": ["tv"], "GAME": ["games"]}.get(category, []).copy()
        year = str(meta.year or "")
        if re.fullmatch(r"\d{4}", year):
            tags.extend((year, f"{year[:3]}0s"))

        genre_tags = {
            "action": "action",
            "adventure": "adventure",
            "animation": "animation",
            "comedy": "comedy",
            "crime": "crime",
            "documentary": "documentary",
            "drama": "drama",
            "family": "family",
            "fantasy": "fantasy",
            "history": "history",
            "horror": "horror",
            "music": "music",
            "musical": "musical",
            "mystery": "mystery",
            "romance": "romance",
            "science fiction": "scifi",
            "sci-fi": "scifi",
            "short": "short",
            "thriller": "thriller",
            "war": "war",
            "western": "western",
        }
        genres = meta.genres or [meta.genre]
        tags.extend(genre_tags[genre.lower().strip()] for genre in genres if genre.lower().strip() in genre_tags)

        if category == "GAME":
            platform = meta.platform.lower()
            if "windows" in platform:
                tags.extend(("pc", "windows"))
            elif "pc" in platform:
                tags.append("pc")
            elif "dos" in platform:
                tags.append("dos")
            elif "nintendo" in platform:
                tags.append("nintendo")
            elif "atari" in platform:
                tags.append("atari")
            if meta.scene:
                tags.append("scene")
            return ", ".join(dict.fromkeys(tags))

        resolution = meta.resolution.lower()
        if re.fullmatch(r"\d{3,4}[pi]", resolution):
            tags.append(resolution)
        if meta.sd:
            tags.append("sd")

        release = f"{meta.type or ''} {meta.source or ''}".lower().replace("-", "")
        for value, tag in (("webdl", "webdl"), ("webrip", "webrip"), ("bluray", "bluray"), ("dvdrip", "dvdrip"), ("remux", "remux"), ("dvd", "dvd"), ("encode", "encode")):
            if value in release:
                tags.append(tag)

        if meta.is_disc:
            tags.append("full.disc")

        if meta.three_d:
            tags.append("3d")

        if meta.extras:
            tags.append("extras")

        if meta.has_commentary:
            tags.append("commentary")

        video_codec = meta.video_codec.lower()
        if any(codec in video_codec for codec in ("avc", "h264", "x264")):
            tags.append("h.264")
        elif any(codec in video_codec for codec in ("hevc", "h265", "x265")):
            tags.append("h.265")

        audio = meta.audio.lower()
        if "ddp" in audio or "dd+" in audio:
            tags.append("ddp")
        elif "ac3" in audio or "ac-3" in audio:
            tags.append("ac3")
        elif "dolby digital" in audio or re.search(r"\bdd\b", audio):
            tags.append("dd")
        elif "aac" in audio:
            tags.append("aac")
        elif "flac" in audio:
            tags.append("flac")
        if "stereo" in audio or "2.0" in audio or meta.channels == "2.0":
            tags.append("stereo")
        if "5.1" in audio or meta.channels == "5.1":
            tags.append("5.1")
        if self._has_english(meta.audio_languages):
            tags.append("english.audio")
        if self._has_english(meta.subtitle_languages):
            tags.append("english.sub")

        return ", ".join(dict.fromkeys(tags))

    @staticmethod
    def _metadata_links(meta: Meta) -> str:
        """Return the relevant canonical metadata links for CRT's info section."""
        links: list[str] = []
        if meta.imdb_tt:
            links.append(f"https://www.imdb.com/title/{meta.imdb_tt}/")
        tmdb_id = meta.tmdb or meta.tmdb_id
        if tmdb_id:
            tmdb_type = "tv" if meta.category == "TV" else "movie"
            links.append(f"https://www.themoviedb.org/{tmdb_type}/{tmdb_id}")
        if meta.category == "TV" and meta.tvdb:
            links.append(f"https://thetvdb.com/?tab=series&id={meta.tvdb}")
        if meta.category == "GAME" and meta.steam_url:
            links.append(meta.steam_url)
        return "\n".join(dict.fromkeys(links))

    async def generate_description(self, meta: Meta) -> str:
        """Render CRT's category-specific upload template from prepared metadata."""
        builder = DescriptionBuilder(self.tracker, self.config)
        category = meta.category.upper()
        links = self._metadata_links(meta)
        overview = meta.overview or meta.overview_meta
        notes = "\n\n".join(part for part in (meta.description.strip(), await builder.get_user_description(meta)) if part)
        images = meta.get(f"{self.tracker}_images_key", meta.image_list)
        screenshots = "\n".join(image["raw_url"] for image in (meta.menu_images + images + meta.spectrograms_images) if image.get("raw_url"))

        sections: list[str] = []
        if links:
            sections.append(f"[info]\n{links}\n[/info]")
        if overview:
            sections.append(f"[plot]\n{overview}\n[/plot]")
        if notes:
            sections.append(f"[notes]\n{notes}\n[/notes]")
        if screenshots:
            sections.append(f"[screens]\n{screenshots}\n[/screens]")

        if category in ("MOVIE", "TV"):
            media_info = await builder.get_bdinfo_section(meta) or await builder.get_mediainfo_section(meta)
            if media_info:
                sections.append(f"[details]\n[mediainfo]\n{media_info}\n[/mediainfo]\n[/details]")

        sections.append(f"\n[align=right][url=https://github.com/wastaken7/Upload-Assistant][size=1]{meta.ua_signature}[/size][/url][/align]")

        description_str: str = "\n".join(part for part in sections if part.strip())

        if meta.debug:
            desc_file = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/[{self.tracker}]DESCRIPTION.txt"
            logger.debug(f"DEBUG: Saving final description to [yellow]{desc_file}[/yellow]")
            async with aiofiles.open(desc_file, "w", encoding="utf-8") as description_file:
                await description_file.write(description_str)

        return description_str

    async def get_upload_data(self, meta: Meta, auth: str) -> dict[str, str]:
        """Build CRT form fields, including its category-specific description template."""
        category = self.category_map.get(str(meta.category).upper())
        if not category:
            raise ValueError(f"Unsupported Cathode-Ray category: {meta.category}")
        return {
            "submit": "true",
            "auth": auth,
            "category": category,
            "MAX_FILE_SIZE": "2097152",
            "title": await self.get_name(meta),
            "taglist": self.get_tags(meta),
            "image": self.get_cover(meta),
            "desc": await self.generate_description(meta),
            "anonymous": "1" if (meta.anon or self.config.get("TRACKERS", {}).get(self.tracker, {}).get("anon", False)) else "0",
        }

    async def get_additional_checks(self, meta: Meta) -> bool:
        """Enforce Cathode-Ray.Tube upload rules and guidelines."""
        category = str(meta.category).upper()

        # Explicit pornography is forbidden for all categories
        if meta.adult_media or meta.tmdb_adult_media or meta.nsfw:
            logger.warning(f"{self.tracker}: [red]Explicit pornography is forbidden.[/red]")
            return False

        # Sports and news broadcasts are forbidden in TV category (allowed in WOC category)
        if category == "TV":
            genres = [g.lower().strip() for g in (meta.genres or [meta.genre]) if g]
            if any(forbidden in genres for forbidden in ("sports", "news")):
                logger.warning(f"{self.tracker}: [red]Sports and News broadcasts are forbidden in the TV category (must be in WOC).[/red]")
                return False

        # Archive file restrictions
        if category != "GAME":
            archives = {".zip", ".rar", ".7z"}
            archive = next((Path(str(item)).name for item in meta.filelist if Path(str(item)).suffix.lower() in archives), "")
            if archive:
                logger.warning(f"{self.tracker}: [red]Archives are not allowed outside Games: {archive}[/red]")
                return False

            # Disc images in ISO format are NOT allowed, with the exception of 3D Blu-ray images
            is_iso = any(Path(str(item)).suffix.lower() == ".iso" for item in meta.filelist) or (isinstance(meta.is_disc, str) and meta.is_disc.upper() == "ISO")
            if is_iso and not meta.three_d:
                logger.warning(f"{self.tracker}: [red]ISO disc images are not allowed outside 3D Blu-ray on CRT.[/red]")
                return False

        # English language requirement & screenshot guidelines for Movies and TV
        if category in ("MOVIE", "TV"):
            if not self._has_english(meta.audio_languages) and not self._has_english(meta.subtitle_languages):
                logger.warning(f"{self.tracker}: [red]CRT requires English audio or English subtitles.[/red]")
                return False

            # Minimum 6 screenshots requirement
            images = list(meta.get(f"{self.tracker}_images_key", meta.image_list)) or []
            screens_count = len(meta.menu_images or []) + len(images) + len(meta.spectrograms_images or [])
            if screens_count == 0 and hasattr(meta, "screens"):
                try:
                    screens_count = int(meta.screens or 0)
                except ValueError, TypeError:
                    screens_count = 0

            if screens_count < 6:
                logger.warning(f"{self.tracker}: [red]CRT requires at least 6 screenshots for video content (found {screens_count}).[/red]")
                return False
            if screens_count > 6 and screens_count % 3 != 0:
                logger.warning(f"{self.tracker}: [yellow]CRT guidelines state screenshot count above 6 should be in multiples of 3 (found {screens_count}).[/yellow]")

            # MediaInfo / BDInfo check
            if getattr(meta, "valid_mi", None) is False:
                logger.warning(f"{self.tracker}: [red]Invalid or missing MediaInfo/BDInfo data.[/red]")
                return False

        # 10-Year Age Limit Rule (release date for movies, last air date for TV must be at least 10 years old)
        is_exempt = bool(meta.edition or (category == "GAME" and getattr(meta, "extras", False)))
        if not is_exempt:
            today = datetime.datetime.now(datetime.UTC).date()
            ten_years_ago = today.replace(year=today.year - 10)
            date_to_check: datetime.date | None = None

            if category == "MOVIE" and getattr(meta, "release_date", None):
                try:
                    date_to_check = datetime.date.fromisoformat(str(meta.release_date).strip()[:10])
                except ValueError, TypeError:
                    date_to_check = None
            elif category == "TV" and (getattr(meta, "last_air_date", None) or getattr(meta, "release_date", None)):
                raw_date = getattr(meta, "last_air_date", None) or getattr(meta, "release_date", None)
                try:
                    date_to_check = datetime.date.fromisoformat(str(raw_date).strip()[:10])
                except ValueError, TypeError:
                    date_to_check = None

            if date_to_check is not None:
                if date_to_check > ten_years_ago:
                    logger.warning(f"{self.tracker}: [red]Content must be at least 10 years old relative to current date (Release/Air date: {date_to_check}).[/red]")
                    return False
            else:
                year_str = str(meta.year or "").strip()
                if year_str.isdigit():
                    year = int(year_str)
                    current_year = datetime.datetime.now(datetime.UTC).year
                    if (current_year - year) < 10:
                        logger.warning(f"{self.tracker}: [red]Content must be at least 10 years old relative to current date (Release year: {year}).[/red]")
                        return False

        return True

    def get_search_params(self, meta: Meta) -> dict[str, str]:
        """Build CRT's advanced-search query."""
        category = self.category_map.get(str(meta.category).upper())
        if not category:
            raise ValueError(f"Unsupported Cathode-Ray category: {meta.category}")

        return {
            "action": "advanced",
            f"filter_cat[{category}]": "1",
            "title": meta.title,
        }

    @staticmethod
    def get_imdb_search_params(meta: Meta) -> dict[str, str]:
        """Build CRT's standalone IMDb search without title or category filters."""
        return {"action": "advanced", "searchtext": meta.imdb_tt}

    @staticmethod
    def _content_name(html: str) -> str:
        """Extract the torrent's top-level directory or sole file name."""
        file_table = BeautifulSoup(html, "html.parser").select_one("div[id^='files_'] table")
        if not file_table:
            return ""

        directory = file_table.select_one("tr.smallhead td")
        if directory and (name := directory.get_text(" ", strip=True).strip("/")):
            return name

        for row in file_table.select("tr"):
            cells = row.select("td")
            if len(cells) >= 2 and (name := cells[0].get_text(" ", strip=True)) != "File Name":
                return name
        return ""

    @staticmethod
    def _bd_info(html: str) -> str:
        """Extract CRT's plain-text BDInfo block from a torrent details page."""
        details = BeautifulSoup(html, "html.parser").select_one("div.section-details")
        details = details.get_text("\n", strip=True) if details else ""
        if "disc title:" not in details.lower() or "disc size:" not in details.lower():
            return ""
        return details

    async def search_existing(self, meta: Meta) -> list[dict[str, str]]:
        """Search CRT's advanced form for existing torrents matching the release metadata."""
        cookie_jar = await self.cookie_validator.load_session_cookies(meta, self.tracker)
        if not cookie_jar:
            return []
        self.session.cookies = cast(Any, cookie_jar)

        results: list[dict[str, str]] = []
        seen_links: set[str] = set()
        searches = [self.get_search_params(meta)]
        if meta.imdb_tt:
            searches.append(self.get_imdb_search_params(meta))
        for params in searches:
            response = await self.session.get(f"{self.base_url}/torrents.php", params=params)
            response.raise_for_status()

            if response.status_code != 200 or "login.php" in str(response.url):
                raise RuntimeError(f"{self.tracker}: [yellow]Could not perform duplicate search; cookies may be expired.[/yellow]")
            if auth := self._extract_auth_token(response.text):
                CathodeRayTube.auth_token = auth
            else:
                raise RuntimeError(f"{self.tracker}: [yellow]Advanced-search response did not contain an auth token.[/yellow]")

            for row in BeautifulSoup(response.text, "html.parser").select("table#torrent_table tr.torrent"):
                download_link = row.select_one('a[href*="action=download"]')
                if not download_link:
                    continue
                title = row.select_one('a[href^="/torrents.php?id="], a[href^="torrents.php?id="]')
                if not title:
                    continue
                href = title.get("href", "")
                if not href:
                    continue
                link = str(httpx.URL(str(response.url)).join(str(href)))
                if link in seen_links:
                    continue
                seen_links.add(link)

                detail_response = await self.session.get(link)
                detail_response.raise_for_status()
                name = self._content_name(detail_response.text)
                if not name:
                    continue
                size_cells = row.select("td.nobr")
                size = size_cells[-1].get_text(" ", strip=True) if size_cells else ""
                download_href = download_link.get("href", "")
                download = str(httpx.URL(str(response.url)).join(str(download_href))) if download_href else ""
                dupe = {
                    "name": name,
                    "size": size,
                    "link": link,
                    "download": download,
                }
                if meta.is_disc == "BDMV" and (bd_info := self._bd_info(detail_response.text)):
                    dupe["bd_info"] = bd_info
                results.append(dupe)

        return results

    @staticmethod
    def _uploaded_torrent_url(response: httpx.Response) -> str:
        url = str(response.url)
        if re.search(r"/torrents\.php\?(?:[^#]*&)?id=\d+", url):
            return url
        for link in BeautifulSoup(response.text, "html.parser").select('a[href*="torrents.php?id="]'):
            href = link.get("href", "")
            if href:
                return str(httpx.URL(url).join(str(href)))
        return ""

    async def upload(self, meta: Meta) -> bool:
        await self.check_image_hosts(meta)
        await self.common.create_torrent_for_upload(meta, self.tracker, self.source_flag)
        torrent_path = Path(meta.base_dir) / "tmp" / meta.uuid / f"[{self.tracker}].torrent"
        if meta.debug:
            logger.info(f"{self.tracker}: [cyan]Request Data:[/cyan]")
            logger.info(Redaction.redact_private_info(await self.get_upload_data(meta, "DEBUG_AUTH")))
            meta.tracker_status[self.tracker]["status_message"] = "Debug mode enabled, not uploading."
            return True

        auth = CathodeRayTube.auth_token
        if not auth:
            meta.tracker_status[self.tracker]["status_message"] = "data error: Failed to load authenticated upload form."
            return False
        try:
            async with aiofiles.open(torrent_path, "rb") as torrent_file:
                files = {"file_input": (torrent_path.name, await torrent_file.read(), "application/x-bittorrent")}
            response = await self.session.post(self.upload_url, data=await self.get_upload_data(meta, auth), files=files)
        except (OSError, httpx.HTTPError) as error:
            meta.tracker_status[self.tracker]["status_message"] = f"data error: CRT upload request failed: {error}"
            return False

        torrent_url = self._uploaded_torrent_url(response)
        if torrent_url:
            meta.tracker_status[self.tracker]["status_message"] = "Upload successful"
            meta.tracker_status[self.tracker]["torrent_id"] = torrent_url
            announce_url = self.config.get("TRACKERS", {}).get(self.tracker, {}).get("announce_url", "")
            await self.common.create_torrent_ready_to_seed(meta, self.tracker, self.source_flag, str(announce_url), torrent_url)
            return True
        error = extract_upload_error(response.text) or f"HTTP {response.status_code}; CRT did not return a torrent URL."
        meta.tracker_status[self.tracker]["status_message"] = f"Upload failed: {error}"
        return False
