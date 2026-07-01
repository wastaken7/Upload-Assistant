# Upload Assistant © 2026 Audionut & wastaken7 — Licensed under UAPL v1.0
import asyncio
import glob
import hashlib
import io
import os
import re
from typing import Any, Optional
from urllib.parse import urlparse

import aiofiles
import httpx
from PIL import Image

from src.console import console
from src.meta import Meta
from src.trackers.COMMON import COMMON

Config = dict[str, Any]

class SUIO:
    supported_categories = ("MOVIE", "TV", "XXX", "GAME", "MUSIC", "BOOK")

    def __init__(self, config: Config) -> None:
        self.config = config
        self.common = COMMON(config)
        self.tracker = "SUIO"
        self.is_usenet = True
        self.upload_url: Optional[str] = None
        self.torrent_url: Optional[str] = None
        tracker_cfg = config.get("TRACKERS", {}).get(self.tracker, {})
        base_url = tracker_cfg.get("base_url", "").strip().rstrip("/")
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
                else:
                    self.upload_url = None
                    self.torrent_url = None
                    console.print(f"{self.tracker} [red]base_url from config.py does not match the expected domain. Skipping...[/red]")
            except Exception:
                self.upload_url = None
                self.torrent_url = None
        else:
            self.upload_url = None
            self.torrent_url = None
        self.banned_groups: list[str] = []

    async def search_existing(self, meta: Meta) -> list[Any]:
        release_name = await self.get_name(meta)
        cache_file = os.path.join(meta.base_dir, "tmp", meta.uuid, f"{self.tracker}_upload_ok")
        if release_name and os.path.exists(cache_file):
            console.print(f"{self.tracker}: [yellow]Found local upload cache.[/yellow]")
            return [release_name]

        console.print(f"{self.tracker}: [yellow]Searching for existing releases is not supported.[/yellow]")
        return []

    async def get_additional_checks(self, _meta: Meta) -> bool:
        tracker_cfg = self.config.get("TRACKERS", {}).get(self.tracker, {})
        username = tracker_cfg.get("username", "").strip()
        if not (username and self.upload_url and self.torrent_url):
            console.print(f"{self.tracker}: [red]Skipping due to missing Username or base_url.[/red]")
            return False
        return True


    def get_category_id(self, meta: Meta) -> str:
        category = str(meta.category or "").upper()
        resolution = meta.resolution.lower()
        uhd_resolutions = {"2160p", "4320p", "8640p"}
        hd_resolutions = {"1080p", "1080i", "720p", "1440p"}
        if category == "MOVIE":
            if resolution in uhd_resolutions:
                return "31"  # Movies: UHD
            elif resolution in hd_resolutions:
                return "16"  # Movies: HD
            elif "SD" in resolution or "480p" in resolution or "576p" in resolution:
                return "15"  # Movies: SD
            elif meta.is_disc == "BDMV":
                return "35"  # Movies: Full BR
            elif "DVD" in str(meta.source).upper():
                return "17"  # Movies: DVD
            return "movie"  # Movies: Auto fallback
        elif category == "TV":
            if resolution in uhd_resolutions:
                return "30"  # TV: UHD
            elif resolution in hd_resolutions:
                return "20"  # TV: HD
            elif "SD" in resolution or "480p" in resolution or "576p" in resolution:
                return "19"  # TV: SD
            return "tv"  # TV: Auto fallback
        elif category == "XXX":
            if resolution in uhd_resolutions:
                return "33"  # XXX: MOVIES-UHD
            elif resolution in hd_resolutions:
                return "27"  # XXX: MOVIES-HD
            return "xxx"  # XXX: Auto fallback
        elif category == "GAME":
            platform = meta.platform.upper()
            if "PC" in platform or "WINDOWS" in platform:
                return "12"  # Games: PC
            elif "MAC" in platform:
                return "13"  # Games: MAC
            return "14"  # Games: Other
        elif category == "MUSIC":
            fmt = meta.format.upper()
            if "FLAC" in fmt or "LOSSLESS" in fmt:
                return "22"  # Music: FLAC
            elif "MP3" in fmt:
                return "7"  # Music: MP3
            return "3"  # Music: Other
        elif category == "BOOK":
            if meta.audiobook:
                return "29"  # Other: Audiobook
            return "9"  # Other: E-Books
        return "video"  # fallback

    def _map_single_language_to_id(self, lang: str) -> str:
        lang = lang.lower().strip()
        if "english" in lang or "eng" in lang or lang == "en":
            return "11"
        elif "danish" in lang or "dan" in lang or lang == "da":
            return "1"
        elif "dutch" in lang or "dut" in lang or "nld" in lang or lang == "nl":
            return "2"
        elif "finnish" in lang or "fin" in lang or lang == "fi":
            return "3"
        elif "french" in lang or "fre" in lang or "fra" in lang or lang == "fr":
            return "4"
        elif "german" in lang or "ger" in lang or "deu" in lang or lang == "de":
            return "5"
        elif "norwegian" in lang or "nor" in lang or lang == "no":
            return "6"
        elif "spanish" in lang or "spa" in lang or "esp" in lang or lang == "es":
            return "7"
        elif "swedish" in lang or "swe" in lang or lang == "sv":
            return "8"
        elif "hebrew" in lang or "heb" in lang or lang == "he":
            return "12"
        elif "portuguese" in lang or "por" in lang or lang == "pt":
            return "13"
        elif "multi" in lang:
            return "9"
        elif lang:
            console.print(f"{self.tracker}: Could not find language {lang} ID, setting to Other ([red]10[/red])")
            return "10"
        console.print(f"{self.tracker}: No audio languages found, setting to Auto ([red]0[/red])")
        return "0"

    def _is_same_language(self, lang_str: str, orig_code: Optional[str]) -> bool:
        if not orig_code:
            return False
        lang_str = lang_str.lower().strip()
        orig_code = orig_code.lower().strip()
        if lang_str == orig_code:
            return True
        try:
            import langcodes

            orig_name = langcodes.Language.get(orig_code).display_name().lower()
            if orig_name in lang_str or lang_str in orig_name:
                return True
        except Exception:
            pass
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
        elif num_langs == 2:
            orig_code = meta.original_language
            if self._is_same_language(audio_languages[0], orig_code):
                return self._map_single_language_to_id(audio_languages[1])
            else:
                return self._map_single_language_to_id(audio_languages[0])
        elif num_langs >= 3:
            return "9"  # Multi
        console.print(f"{self.tracker}: No audio languages found, setting to Auto ([red]0[/red])")
        return "0"  # Auto

    async def _prepare_files(self, meta: Meta) -> Optional[dict[str, Any]]:
        nzb_path = meta.nzb_path
        if not nzb_path or not await self.common.check_nzb_file(self.tracker, meta):
            return None

        # Prepare multipart/form-data
        async with aiofiles.open(nzb_path, "rb") as f:
            nzb_content = await f.read()
        files = {"nzb": (os.path.basename(nzb_path), nzb_content, "application/x-nzb")}
        # NFO file (optional)
        nfo_dir = os.path.join(meta.base_dir, "tmp", meta.uuid)
        nfo_content = None
        nfo_filename = None
        if meta.scene:
            nfo_files = glob.glob(os.path.join(nfo_dir, "*.nfo"))
            nfo_path = nfo_files[0] if nfo_files else None
            if nfo_path and os.path.exists(nfo_path):
                async with aiofiles.open(nfo_path, "rb") as f:
                    nfo_content = await f.read()
                nfo_filename = os.path.basename(nfo_path)
        else:
            if meta.is_disc == "BDMV":
                bdinfo_path = os.path.join(nfo_dir, "BD_SUMMARY_00.txt")
                if os.path.exists(bdinfo_path):
                    async with aiofiles.open(bdinfo_path, "rb") as f:
                        nfo_content = await f.read()
                    nfo_filename = "BDInfo.nfo"
            else:
                mediainfo_path = os.path.join(nfo_dir, "MEDIAINFO_CLEANPATH.txt")
                if os.path.exists(mediainfo_path):
                    async with aiofiles.open(mediainfo_path, "rb") as f:
                        nfo_content = await f.read()
                    nfo_filename = "MediaInfo.nfo"
            if not nfo_content:
                nfo_files = glob.glob(os.path.join(nfo_dir, "*.nfo"))
                nfo_path = nfo_files[0] if nfo_files else None
                if nfo_path and os.path.exists(nfo_path):
                    async with aiofiles.open(nfo_path, "rb") as f:
                        nfo_content = await f.read()
                    nfo_filename = os.path.basename(nfo_path)
        if nfo_content and nfo_filename:
            files["nfo"] = (nfo_filename, nfo_content, "application/octet-stream")
        # Cover image file (optional)
        if meta.category not in ("TV", "MOVIE"):
            cover_jpg_path = os.path.join(nfo_dir, "POSTER.jpg")
            cover_png_path = os.path.join(nfo_dir, "POSTER.png")
            cover_path = None
            if os.path.exists(cover_jpg_path):
                cover_path = cover_jpg_path
            elif os.path.exists(cover_png_path):
                cover_path = cover_png_path
            if cover_path:
                if cover_path.lower().endswith((".jpg", ".jpeg")):
                    async with aiofiles.open(cover_path, "rb") as f:
                        cover_content = await f.read()
                    filename = os.path.basename(cover_path)
                else:

                    def _convert_to_jpg(path: str) -> bytes:
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
                    filename = os.path.splitext(os.path.basename(cover_path))[0] + ".jpg"
                files["cover"] = (filename, cover_content, "image/jpeg")
        return files

    async def get_name(self, meta: Meta) -> str:
        return meta.scene_name or meta.basename_no_ext

    async def _prepare_data(self, meta: Meta) -> dict[str, Any]:
        data = {
            "rlsname": await self.get_name(meta),
            "catid": self.get_category_id(meta),
            "upload": "Post NZB",
            "language": self.get_language_id(meta),
            "tag": "0",
        }
        return data

    async def upload(self, meta: Meta) -> Optional[bool]:
        status_map = meta.tracker_status
        if self.tracker not in status_map:
            status_map[self.tracker] = {}
        status_dict = status_map[self.tracker]

        if not self.upload_url:
            console.print(f"[red]{self.tracker}: base_url missing. Cannot upload.[/red]")
            status_dict["status_message"] = "data error: base_url missing"
            return False

        tracker_cfg = self.config.get("TRACKERS", {}).get(self.tracker, {})
        username = tracker_cfg.get("username", "").strip()
        api_key = tracker_cfg.get("api_key", "").strip()

        files = await self._prepare_files(meta)
        if not files:
            status_dict["status_message"] = "data error: NZB file missing or password missing in header"
            return False

        data = await self._prepare_data(meta)
        if meta.debug:
            console.print(f"[cyan]{self.tracker} Upload (DEBUG MODE):[/cyan]")
            console.print(f"User: {username}")
            console.print("Fields:")
            console.print(data)
            console.print("Files:")
            console.print({k: v[0] for k, v in files.items()})
            status_dict["status_message"] = "Debug mode enabled, skipping upload."
            return True
        params = {
            "user": username,
            "api": api_key,
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
                nzb_filename = os.path.basename(meta.nzb_path)
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
                nzb_filename = os.path.basename(meta.nzb_path)
                if nzb_filename:
                    success_msg = re.sub(re.escape(nzb_filename), "[redacted]", success_msg, flags=re.IGNORECASE)
                rlsname = data.get("rlsname", "")
                if rlsname:
                    success_msg = re.sub(re.escape(rlsname), "[redacted]", success_msg, flags=re.IGNORECASE)
                if username:
                    success_msg = re.sub(re.escape(username), "[redacted]", success_msg, flags=re.IGNORECASE)
            status_dict["status_message"] = success_msg

            cache_dir = os.path.join(meta.base_dir, "tmp", meta.uuid)
            os.makedirs(cache_dir, exist_ok=True)
            async with aiofiles.open(os.path.join(cache_dir, f"{self.tracker}_upload_ok"), "w", encoding="utf-8") as cache_handle:
                await cache_handle.write("ok")

            # Parse NZB release/post ID from the response text or final URL if present
            try:
                id_match = re.search(r"ID:\s*([a-zA-Z0-9]+)", response.text, re.IGNORECASE)
                if not id_match:
                    id_match = re.search(r"(?:details\.php\?id=|details/|id=)([a-zA-Z0-9]+)", response.text, re.IGNORECASE)
                if not id_match:
                    id_match = re.search(r"(?:details\.php\?id=|details/|id=)([a-zA-Z0-9]+)", final_url, re.IGNORECASE)
                if id_match:
                    status_dict["torrent_id"] = str(id_match.group(1))
            except Exception:
                pass
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
