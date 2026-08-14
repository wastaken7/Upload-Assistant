# Upload Assistant © 2026 Audionut & wastaken7 — Licensed under UAPL v1.0
import asyncio
import contextlib
import hashlib
import io
import re
import unicodedata
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import aiofiles
import httpx
from PIL import Image

from src.cogs.redaction import Redaction
from src.console import logger
from src.meta import Meta
from src.temp_paths import artwork_dir
from src.trackers.common import Common
from src.trackers.USENET.search_helpers import (
    build_newznab_search_query,
    get_daily_api_hit_limit,
    get_newznab_search_category_id,
    parse_newznab_dupes,
    reserve_daily_api_hit,
)

Config = dict[str, Any]


class Suio:
    """
    SUIO Private Torrent Tracker
    """

    auth_type = "other_api"
    tracker = "SUIO"
    display_name = "Suio"
    allows_bloated_audio = True
    banned_groups: tuple[str, ...] = ()
    upload_url: str | None = None
    torrent_url: str | None = None
    search_url: str | None = None
    base_url = "https://suio.cc"
    supported_categories = ("MOVIE", "TV", "GAME", "BOOK", "XXX")
    is_usenet = True

    def __init__(self, config: Config) -> None:
        self.config = config
        self.common = Common(config)
        self.tracker_cfg = config.get("TRACKERS", {}).get(self.tracker, {})
        self.api_key = str(self.tracker_cfg.get("api_key", "")).strip()
        self.daily_api_hit_limit = get_daily_api_hit_limit(self.tracker_cfg)
        base_url = str(self.tracker_cfg.get("base_url", "")).strip().rstrip("/")
        if base_url:
            # Verify the domain matches the expected indexer domain hash to prevent credentials leak
            url_to_parse = base_url if base_url.startswith(("http://", "https://")) else "https://" + base_url
            try:
                hostname = urlparse(url_to_parse).netloc.lower().split(":")[0]
                parts = hostname.split(".")
                main_domain = ".".join(parts[-2:]) if len(parts) >= 2 else hostname
                domain_hash = hashlib.sha256(main_domain.encode("utf-8")).hexdigest()
                # SHA-256 hash of the allowed indexer domain
                if domain_hash == "a0fcf409be81cbcec4e212cb69331960e5d709449c0e9cad40e36369d8da8f3c":
                    self.upload_url = f"{base_url}/api-upload"
                    self.torrent_url = f"{base_url}/details.php?id="
                    parsed_url = urlparse(url_to_parse)
                    scheme = parsed_url.scheme or "https"
                    hostname = parsed_url.netloc or parsed_url.path
                    self.search_url = f"{scheme}://api.{hostname.split('@')[-1]}/api"
                else:
                    self.upload_url = None
                    self.torrent_url = None
                    self.search_url = None
                    logger.info(f"{self.tracker}: [red]base_url from config.py does not match the expected domain. Skipping...[/red]")
            except Exception:
                self.upload_url = None
                self.torrent_url = None
                self.search_url = None
        else:
            self.upload_url = None
            self.torrent_url = None
            self.search_url = None

    def get_search_query(self, meta: Meta) -> str:
        return build_newznab_search_query(meta)

    async def get_search_name(self, meta: Meta) -> str:
        return await self.get_name(meta)

    def _parse_dupes_from_response(self, response_text: str) -> list[dict[str, Any]]:
        return parse_newznab_dupes(response_text, self.torrent_url, use_guid_attr_as_id=True)

    async def search_existing(self, meta: Meta) -> list[Any]:
        release_name = await self.get_name(meta)
        cache_file = Path(meta.base_dir) / "tmp" / meta.uuid / f"{self.tracker}_upload_ok"
        if release_name and Path(cache_file).exists():
            logger.info(f"{self.tracker}: [yellow]Found local upload cache.[/yellow]")
            return [release_name]

        if not self.search_url:
            return []
        if self.daily_api_hit_limit <= 0:
            logger.info(f"{self.tracker}: [yellow]Duplicate search via API is disabled because daily_api_hit_limit is 0.[/yellow]")
            return []

        params_list: list[dict[str, str]] = []
        exact_name = await self.get_search_name(meta)
        if exact_name:
            params_list.append(
                {
                    "t": "search",
                    "q": exact_name,
                    "pw": "0",
                }
            )

        params: dict[str, str] = {
            "cat": get_newznab_search_category_id(meta),
        }

        category = meta.category.upper()
        if category == "TV":
            params["t"] = "tvsearch"
            if meta.tvdb_id and str(meta.tvdb_id).isdigit() and int(meta.tvdb_id) > 0:
                params["tvdbid"] = str(meta.tvdb_id)
            else:
                params["q"] = self.get_search_query(meta)

            if meta.season_int > 0:
                params["season"] = str(meta.season_int)
            if meta.episode_int > 0:
                params["ep"] = str(meta.episode_int)
        elif category == "MOVIE":
            params["t"] = "movie"
            if meta.imdb_tt:
                params["imdbid"] = meta.imdb_tt
            else:
                params["q"] = self.get_search_query(meta)
        else:
            params["t"] = "search"
            params["q"] = self.get_search_query(meta)

        params_list.append(params)

        dupes: list[dict[str, Any]] = []
        seen_keys: set[str] = set()
        async with httpx.AsyncClient(timeout=10.0) as client:
            for query_params in params_list:
                allowed, used_hits = await reserve_daily_api_hit(meta.base_dir, self.tracker, self.daily_api_hit_limit)
                if not allowed:
                    logger.info(f"{self.tracker}: [yellow]Duplicate search stopped because the 24-hour API hit limit ({self.daily_api_hit_limit}) has been reached.[/yellow]")
                    break
                request_params = {
                    "apikey": self.api_key,
                    "limit": "100",
                    "extended": "1",
                    "pw": "2",
                    **query_params,
                }
                response = await client.get(self.search_url, params=request_params)
                logger.debug(f"{self.tracker}: Duplicate search used API hit {used_hits}/{self.daily_api_hit_limit} in the last 24 hours.")
                response.raise_for_status()

                if not response.text.strip():
                    continue

                for dupe in self._parse_dupes_from_response(response.text):
                    key = str(dupe.get("link") or dupe.get("name") or "")
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)
                    dupes.append(dupe)

        return dupes

    async def get_additional_checks(self, _meta: Meta) -> bool:
        tracker_cfg = self.config.get("TRACKERS", {}).get(self.tracker, {})
        username = tracker_cfg.get("username", "").strip()
        if not (username and self.upload_url and self.torrent_url):
            logger.info(f"{self.tracker}: [red]Skipping due to missing Username or base_url.[/red]")
            return False
        return True

    def get_category_id(self, meta: Meta) -> str:
        category = meta.category.upper()
        resolution = meta.resolution.lower()
        uhd_resolutions = {"2160p", "4320p", "8640p"}
        hd_resolutions = {"1080p", "1080i", "720p", "1440p"}
        if category == "MOVIE":
            if resolution in uhd_resolutions:
                return "31"  # Movies: UHD
            if resolution in hd_resolutions:
                return "16"  # Movies: HD
            if "SD" in resolution or "480p" in resolution or "576p" in resolution:
                return "15"  # Movies: SD
            if meta.is_disc == "BDMV":
                return "35"  # Movies: Full BR
            if "DVD" in str(meta.source).upper():
                return "17"  # Movies: DVD
            return "movie"  # Movies: Auto fallback
        if category == "TV":
            if resolution in uhd_resolutions:
                return "30"  # TV: UHD
            if resolution in hd_resolutions:
                return "20"  # TV: HD
            if "SD" in resolution or "480p" in resolution or "576p" in resolution:
                return "19"  # TV: SD
            return "tv"  # TV: Auto fallback
        if category == "XXX":
            if resolution in uhd_resolutions:
                return "33"  # XXX: MOVIES-UHD
            if resolution in hd_resolutions:
                return "27"  # XXX: MOVIES-HD
            return "xxx"  # XXX: Auto fallback
        if category == "GAME":
            platform = meta.platform.upper()
            if "PC" in platform or "WINDOWS" in platform:
                return "12"  # Games: PC
            if "MAC" in platform:
                return "13"  # Games: MAC
            return "14"  # Games: Other
        if category == "MUSIC":
            fmt = meta.format.upper()
            if "FLAC" in fmt or "LOSSLESS" in fmt:
                return "22"  # Music: FLAC
            if "MP3" in fmt:
                return "7"  # Music: MP3
            return "3"  # Music: Other
        if category == "BOOK":
            if meta.audiobook:
                return "29"  # Other: Audiobook
            return "9"  # Other: E-Books
        return "video"  # fallback

    def _map_single_language_to_id(self, lang: str) -> str:
        lang = lang.lower().strip()
        if "english" in lang or "eng" in lang or lang == "en":
            return "11"
        if "danish" in lang or "dan" in lang or lang == "da":
            return "1"
        if "dutch" in lang or "dut" in lang or "nld" in lang or lang == "nl":
            return "2"
        if "finnish" in lang or "fin" in lang or lang == "fi":
            return "3"
        if "french" in lang or "fre" in lang or "fra" in lang or lang == "fr":
            return "4"
        if "german" in lang or "ger" in lang or "deu" in lang or lang == "de":
            return "5"
        if "norwegian" in lang or "nor" in lang or lang == "no":
            return "6"
        if "spanish" in lang or "spa" in lang or "esp" in lang or lang == "es":
            return "7"
        if "swedish" in lang or "swe" in lang or lang == "sv":
            return "8"
        if "hebrew" in lang or "heb" in lang or lang == "he":
            return "12"
        if "portuguese" in lang or "por" in lang or lang == "pt":
            return "13"
        if "multi" in lang:
            return "9"
        if lang:
            logger.info(f"{self.tracker}: Could not find language {lang} ID, setting to Other ([red]10[/red])")
            return "10"
        logger.info(f"{self.tracker}: No audio languages found, setting to Auto ([red]0[/red])")
        return "0"

    def _is_same_language(self, lang_str: str, orig_code: str | None) -> bool:
        if not orig_code:
            return False
        lang_str = lang_str.lower().strip()
        orig_code = orig_code.lower().strip()
        if lang_str == orig_code:
            return True
        with contextlib.suppress(Exception):
            import langcodes

            orig_name = langcodes.Language.get(orig_code).display_name().lower()
            if orig_name in lang_str or lang_str in orig_name:
                return True
        # Common code to name mapping fallbacks
        common_codes = {
            "en": ["english", "eng"],
            "pt": ["portuguese", "português", "por"],
            "es": ["spanish", "español", "spa", "esp"],
            "fr": ["french", "français", "fre", "fra"],
            "de": ["german", "deutsch", "ger", "deu"],
            "it": ["italian", "italiano", "ita"],
            "da": ["danish", "dansk", "dan"],
            "nl": ["dutch", "nederlands", "dut", "nld"],
            "fi": ["finnish", "suomi", "fin"],
            "no": ["norwegian", "norsk", "nor"],
            "sv": ["swedish", "svenska", "swe"],
            "he": ["hebrew", "עברית", "heb"],
        }
        if orig_code in common_codes:
            for val in common_codes[orig_code]:
                if val in lang_str or lang_str in val:
                    return True
        return False

    def get_language_id(self, meta: Meta) -> str:
        resolve_language = self.config.get("TRACKERS", {}).get(self.tracker, {}).get("resolve_language", True)
        if not resolve_language:
            return "0"
        audio_languages = meta.audio_languages or meta.book_language_iso or []
        if isinstance(audio_languages, str):
            audio_languages = [audio_languages]
        audio_languages = [lang for lang in audio_languages if lang]
        num_langs = len(audio_languages)
        if num_langs == 1:
            return self._map_single_language_to_id(audio_languages[0])
        if num_langs == 2:
            orig_code = meta.original_language
            if self._is_same_language(audio_languages[0], orig_code):
                return self._map_single_language_to_id(audio_languages[1])
            return self._map_single_language_to_id(audio_languages[0])
        if num_langs >= 3:
            return "9"  # Multi
        logger.info(f"{self.tracker}: No audio languages found, setting to Auto ([red]0[/red])")
        return "0"  # Auto

    async def _prepare_files(self, meta: Meta) -> dict[str, Any] | None:
        nzb_path = meta.nzb_path
        if not nzb_path or not await self.common.check_nzb_file(self.tracker, meta):
            return None

        # Prepare multipart/form-data
        async with aiofiles.open(nzb_path, "rb") as f:
            nzb_content = await f.read()
        files = {"nzb": (Path(nzb_path).name, nzb_content, "application/x-nzb")}
        # NFO file (optional)
        nfo_dir = Path(meta.base_dir) / "tmp" / meta.uuid
        nfo_content = None
        nfo_filename = None
        if meta.scene:
            nfo_files = list(nfo_dir.glob("*.nfo"))
            nfo_path = nfo_files[0] if nfo_files else None
            if nfo_path and nfo_path.exists():
                async with aiofiles.open(nfo_path, "rb") as f:
                    nfo_content = await f.read()
                nfo_filename = nfo_path.name
        else:
            if meta.is_disc == "BDMV":
                bdinfo_path = Path(nfo_dir) / "BD_SUMMARY_00.txt"
                if Path(bdinfo_path).exists():
                    async with aiofiles.open(bdinfo_path, "rb") as f:
                        nfo_content = await f.read()
                    nfo_filename = "BDInfo.nfo"
            else:
                mediainfo_path = Path(nfo_dir) / "MEDIAINFO_CLEANPATH.txt"
                if Path(mediainfo_path).exists():
                    async with aiofiles.open(mediainfo_path, "rb") as f:
                        nfo_content = await f.read()
                    nfo_filename = "MediaInfo.nfo"
            if not nfo_content:
                nfo_files = list(nfo_dir.glob("*.nfo"))
                nfo_path = nfo_files[0] if nfo_files else None
                if nfo_path and nfo_path.exists():
                    async with aiofiles.open(nfo_path, "rb") as f:
                        nfo_content = await f.read()
                    nfo_filename = nfo_path.name
        if nfo_content and nfo_filename:
            files["nfo"] = (nfo_filename, nfo_content, "application/octet-stream")
        # Cover image file (optional)
        if meta.category not in ("TV", "MOVIE"):
            cover_jpg_path = artwork_dir(meta.base_dir, meta.uuid) / "POSTER.jpg"
            cover_png_path = artwork_dir(meta.base_dir, meta.uuid) / "POSTER.png"
            cover_path = None
            if Path(cover_jpg_path).exists():
                cover_path = cover_jpg_path
            elif Path(cover_png_path).exists():
                cover_path = cover_png_path
            if cover_path:
                if cover_path.suffix.lower() in {".jpg", ".jpeg"}:
                    async with aiofiles.open(cover_path, "rb") as f:
                        cover_content = await f.read()
                    filename = cover_path.name
                else:

                    def _convert_to_jpg(path: str | Path) -> bytes:
                        with Image.open(path) as img:
                            if img.mode in ("RGBA", "LA"):
                                background = Image.new("RGB", img.size, (255, 255, 255))
                                alpha = img.split()[-1]
                                background.paste(img, mask=alpha)
                                img = background
                            elif img.mode != "RGB":
                                img = img.convert("RGB")
                            buf = io.BytesIO()
                            img.save(buf, format="JPEG", quality=95)
                            return buf.getvalue()

                    cover_content = await asyncio.to_thread(_convert_to_jpg, cover_path)
                    filename = cover_path.stem + ".jpg"
                files["cover"] = (filename, cover_content, "image/jpeg")
        return files

    async def get_name(self, meta: Meta) -> str:
        name = meta.scene_name or meta.basename_no_ext or ""
        normalized = unicodedata.normalize("NFKD", name)
        return "".join(char for char in normalized if not unicodedata.combining(char))

    async def _prepare_data(self, meta: Meta) -> dict[str, Any]:
        return {
            "rlsname": await self.get_name(meta),
            "catid": self.get_category_id(meta),
            "upload": "Post NZB",
            "language": self.get_language_id(meta),
            "tag": "0",
        }

    async def upload(self, meta: Meta) -> bool | None:
        status_map = meta.tracker_status
        if self.tracker not in status_map:
            status_map[self.tracker] = {}
        status_dict = status_map[self.tracker]

        if not self.upload_url:
            logger.info(f"{self.tracker}: [red]base_url missing. Cannot upload.[/red]")
            status_dict["status_message"] = "data error: base_url missing"
            return False

        username = self.tracker_cfg.get("username", "").strip()

        files = await self._prepare_files(meta)
        if not files:
            status_dict["status_message"] = "data error: NZB file missing or password missing in header"
            return False

        data = await self._prepare_data(meta)
        if meta.debug:
            logger.debug(f"{self.tracker}: [cyan]Upload (DEBUG MODE):[/cyan]")
            logger.debug(f"{self.tracker}: User: {username}")
            logger.debug(f"{self.tracker}: Fields:")
            logger.debug(Redaction.redact_private_info(data))
            logger.debug(f"{self.tracker}: Files:")
            logger.debug({k: v[0] for k, v in files.items()})
            status_dict["status_message"] = "Debug mode enabled, skipping upload."
            return True

        params = {
            "user": str(username),
            "api": self.api_key,
        }

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    self.upload_url,
                    files=files,
                    data=data,
                    params=params,
                    headers={"User-Agent": f"{meta.ua_name} {(meta.current_version if meta.current_version is not None else 'github.com/Audionut/Upload-Assistant')}"},
                    follow_redirects=True,
                )
            final_url = str(response.url)
            is_error = False
            err_msg = ""
            # Check if final URL indicates redirect to an error/404 page
            if "inf=err" in final_url or "/404" in final_url:
                is_error = True
            # Scan the HTML body for commented XML response status
            comment_match = re.search(r"<!--\s*<response>(.*?)</response>\s*-->", response.text, re.IGNORECASE | re.DOTALL)
            if comment_match:
                resp_text = comment_match.group(1).strip().lower()
                if any(x in resp_text for x in ("invalid", "error", "did not select", "fail")):
                    is_error = True
                    err_msg = re.sub(r"\s+", " ", comment_match.group(1).strip())
            # Attempt to retrieve a more specific/descriptive error message from font elements
            font_match = re.search(r'<font[^>]*color=["\']?red["\']?[^>]*>(.*?)</font>', response.text, re.IGNORECASE | re.DOTALL)
            if font_match:
                font_text = font_match.group(1)
                font_text = re.sub(r"<[^>]+>", " ", font_text)
                font_text = re.sub(r"\s+", " ", font_text).strip()
                if font_text:
                    is_error = True
                    err_msg = font_text
            if response.status_code not in (200, 201) or is_error:
                if not err_msg:
                    err_msg = f"HTTP {response.status_code}" if response.status_code not in (200, 201) else "Unknown upload failure"
                # Redact username / release name from error message
                nzb_filename = Path(meta.nzb_path).name
                if nzb_filename:
                    err_msg = re.sub(re.escape(nzb_filename), "[redacted]", err_msg, flags=re.IGNORECASE)
                rlsname = data.get("rlsname", "")
                if rlsname:
                    err_msg = re.sub(re.escape(rlsname), "[redacted]", err_msg, flags=re.IGNORECASE)
                if username:
                    err_msg = re.sub(re.escape(username), "[redacted]", err_msg, flags=re.IGNORECASE)
                status_dict["status_message"] = f"data error: {err_msg}"
                return False
            success_msg = "Upload successful"
            if comment_match:
                success_msg = re.sub(r"\s+", " ", comment_match.group(1).strip())
                # Redact username / release name from success message
                nzb_filename = Path(meta.nzb_path).name
                if nzb_filename:
                    success_msg = re.sub(re.escape(nzb_filename), "[redacted]", success_msg, flags=re.IGNORECASE)
                rlsname = data.get("rlsname", "")
                if rlsname:
                    success_msg = re.sub(re.escape(rlsname), "[redacted]", success_msg, flags=re.IGNORECASE)
                if username:
                    success_msg = re.sub(re.escape(username), "[redacted]", success_msg, flags=re.IGNORECASE)
            status_dict["status_message"] = success_msg

            cache_dir = Path(meta.base_dir) / "tmp" / meta.uuid
            Path(cache_dir).mkdir(parents=True, exist_ok=True)
            async with aiofiles.open(Path(cache_dir) / f"{self.tracker}_upload_ok", "w", encoding="utf-8") as cache_handle:
                await cache_handle.write("ok")

            # Parse NZB release/post ID from the response text or final URL if present
            with contextlib.suppress(Exception):
                id_match = re.search(r"ID:\s*([a-zA-Z0-9]+)", response.text, re.IGNORECASE)
                if not id_match:
                    id_match = re.search(r"(?:details\.php\?id=|details/|id=)([a-zA-Z0-9]+)", response.text, re.IGNORECASE)
                if not id_match:
                    id_match = re.search(r"(?:details\.php\?id=|details/|id=)([a-zA-Z0-9]+)", final_url, re.IGNORECASE)
                if id_match:
                    status_dict["torrent_id"] = str(id_match.group(1))
            return True
        except httpx.TimeoutException:
            status_dict["status_message"] = "data error: Request timed out after 60 seconds"
            return False
        except httpx.RequestError as e:
            status_dict["status_message"] = f"data error: Unable to upload. Error: {e}"
            return False
        except Exception as e:
            status_dict["status_message"] = f"data error: Unexpected error. Error: {e}"
            return False
