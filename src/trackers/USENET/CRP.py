# Upload Assistant © 2026 Audionut & wastaken7 — Licensed under UAPL v1.0
import glob
import json
import os
from typing import Any, Optional

import aiofiles
import httpx
import langcodes

from src.console import console
from src.meta import Meta
from src.trackers.COMMON import COMMON

Config = dict[str, Any]


class CRP:
    supported_categories = ("TV", "MOVIE", "GAME", "BOOK")

    def __init__(self, config: Config) -> None:
        self.config = config
        self.common = COMMON(config)
        self.tracker = "CRP"
        self.is_usenet = True
        self.upload_url = "https://curupira.cc/v1/releases"
        self.torrent_url = "https://curupira.cc/releases/"
        self.banned_groups = []

    async def search_existing(self, meta: Meta) -> list[Any]:
        if not await self.get_additional_checks():
            console.print(f"{self.tracker}: [red]Skipping due to missing API Key.[/red]")
            meta.skipping = f"{self.tracker}"
            return []
        console.print(f"{self.tracker}: [yellow]Searching for existing releases is not supported.[/yellow]")
        return []

    async def get_additional_checks(self) -> bool:
        tracker_cfg = self.config.get("TRACKERS", {}).get(self.tracker, {})
        api_key = tracker_cfg.get("api_key", "").strip()
        return api_key

    def get_category_id(self, meta: Meta) -> str:
        # Check if anime
        if meta.anime:
            return "5070"

        category = str(meta.category or "").upper()
        resolution = str(meta.resolution).lower()

        uhd_resolutions = {"2160p", "4320p", "8640p"}
        hd_resolutions = {"1080p", "1080i", "720p", "1440p"}

        if category == "MOVIE":
            if resolution in uhd_resolutions:
                return "2045"
            elif resolution in hd_resolutions:
                return "2040"
            else:
                return "2030"
        elif category == "TV":
            if resolution in uhd_resolutions:
                return "5045"
            elif resolution in hd_resolutions:
                return "5040"
            else:
                return "5030"
        elif category == "BOOK":
            if meta.audiobook:
                return "3030"
            else:
                return "7020"
        elif category == "GAME":
            return "4050"
        elif category == "MUSIC":
            return "3000"

        # Fallback to general TV HD or Movies HD/SD depending on category
        if category == "TV":
            return "5000"
        return "2000"

    async def get_name(self, meta: Meta) -> str:
        return meta.scene_name or meta.basename_no_ext

    def get_iso_639_1(self, lang_name: str) -> Optional[str]:
        try:
            lang = langcodes.find(lang_name)
            if lang and lang.is_valid():
                return lang.language
        except Exception:
            pass
        return None

    def get_source(self, meta: Meta) -> Optional[str]:
        source = meta.source
        if not source:
            return None
        source_upper = str(source).upper()
        if "BLU" in source_upper:
            if meta.is_disc:
                return "Full Disc"
            return "BluRay"
        elif "WEB" in source_upper:
            return "WEBRip" if meta.type == "WEBRIP" else "WEB-DL"
        elif "HDTV" in source_upper:
            return "HDTV"
        elif "DVD" in source_upper:
            return "DVD"
        return str(source)

    async def _prepare_files(self, meta: Meta) -> Optional[dict[str, Any]]:
        nzb_path = meta.nzb_path

        if not nzb_path or not await self.common.check_nzb_file(self.tracker, meta):
            return

        # Prepare multipart/form-data
        async with aiofiles.open(nzb_path, "rb") as f:
            nzb_content = await f.read()

        files = {"nzb_file": (os.path.basename(nzb_path), nzb_content, "application/x-nzb")}

        # NFO file (optional)
        nfo_dir = os.path.join(meta.base_dir, "tmp", meta.uuid)
        nfo_files = glob.glob(os.path.join(nfo_dir, "*.nfo"))
        nfo_path = nfo_files[0] if nfo_files else None
        if nfo_path and os.path.exists(nfo_path):
            async with aiofiles.open(nfo_path, "rb") as f:
                nfo_content = await f.read()
            files["nfo_file"] = (os.path.basename(nfo_path), nfo_content, "application/octet-stream")

        return files

    async def get_media_info(self, meta: Meta) -> str:
        info_file_path = ""
        if meta.is_disc == "BDMV":
            info_file_path = f"{meta.base_dir}/tmp/{meta.uuid}/BD_SUMMARY_00.txt"
        else:
            info_file_path = f"{meta.base_dir}/tmp/{meta.uuid}/MEDIAINFO_CLEANPATH.txt"

        if os.path.exists(info_file_path):
            try:
                async with aiofiles.open(info_file_path, encoding="utf-8") as f:
                    return await f.read()
            except Exception as e:
                console.print(f"[bold red]Erro ao ler o arquivo de info em {info_file_path}: {e}[/bold red]")
                return ""
        else:
            console.print(f"[bold red]Arquivo de info não encontrado: {info_file_path}[/bold red]")
            return ""

    def get_cover(self, meta: Meta) -> str:
        covers = meta.covers
        if isinstance(covers, list) and len(covers) > 0:
            raw_url = covers[0].get("raw_url")
            if raw_url:
                return str(raw_url)

        # Fallback to poster URL if remote
        poster_url = meta.poster
        if isinstance(poster_url, str) and poster_url.startswith(("http://", "https://")):
            return poster_url

        return ""

    async def _prepare_data(self, meta: Meta, tracker_cfg: Config) -> dict[str, Any]:
        data = {
            "name": await self.get_name(meta),
            "category_id": self.get_category_id(meta),
        }

        # Cover
        if meta.category not in ("MOVIE", "TV"):
            cover_url = self.get_cover(meta)
            if cover_url:
                data["custom_cover_url"] = cover_url

        # MediaInfo text (optional)
        if meta.category in ("TV", "MOVIE") or meta.audiobook:
            data["mediainfo_text"] = await self.get_media_info(meta)

        # Quality (optional)
        quality = meta.resolution
        if quality and quality.upper() != "OTHER":
            data["quality"] = str(quality)

        # Source (optional)
        source = self.get_source(meta)
        if source:
            data["source"] = source

        if meta.is_disc:
            # Audio and Subtitles languages (optional, as ISO 639-1 JSON array)
            audio_langs = []
            for lang in meta.audio_languages or []:
                iso = self.get_iso_639_1(lang)
                if iso:
                    audio_langs.append(iso)
            if audio_langs:
                data["audio_langs"] = json.dumps(audio_langs)
            subs_langs = []
            for lang in meta.subtitle_languages or []:
                iso = self.get_iso_639_1(lang)
                if iso:
                    subs_langs.append(iso)
            if subs_langs:
                data["subs_langs"] = json.dumps(subs_langs)

        # TMDb id and type (optional)
        tmdb_id = meta.tmdb_id
        if tmdb_id and str(tmdb_id).isdigit() and int(tmdb_id) > 0:
            data["tmdb_id"] = str(tmdb_id)
            tmdb_type = str(meta.category or "").lower()
            if tmdb_type in ("movie", "tv"):
                data["tmdb_type"] = tmdb_type

        # MyAnimeList id (optional)
        mal_id = meta.mal_id
        if mal_id and str(mal_id).isdigit() and int(mal_id) > 0:
            data["mal_id"] = str(mal_id)

        # Anonymous (optional)
        anon = 0 if meta.anon == 0 and not tracker_cfg.get("anon", False) else 1
        if anon:
            data["anonymous"] = "true"

        return data

    async def upload(self, meta: Meta) -> Optional[bool]:
        if not await self.common.check_nzb_file(self.tracker, meta):
            meta.tracker_status[self.tracker]["status_message"] = "data error: NZB file missing or password missing in header"
            return False

        tracker_cfg = self.config.get("TRACKERS", {}).get(self.tracker, {})
        api_key = tracker_cfg.get("api_key", "").strip()

        files = await self._prepare_files(meta)
        if not files:
            console.print(f"[red]Error: NZB file not found for {self.tracker}.[/red]")
            meta.tracker_status[self.tracker]["status_message"] = "data error: NZB file not found"
            return False

        data = await self._prepare_data(meta, tracker_cfg)

        if meta.debug:
            console.print("[cyan]CRP Upload (DEBUG MODE):[/cyan]")
            console.print(f"URL: {self.upload_url}")
            console.print(f"Category ID: {self.get_category_id(meta)}")
            console.print("Fields:")
            console.print(data)
            console.print("Files:")
            console.print({k: v[0] for k, v in files.items()})

            meta.tracker_status[self.tracker]["status_message"] = "Debug mode enabled, skipping upload."
            return True

        # Perform actual upload
        params = {"apikey": api_key}
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    self.upload_url,
                    files=files,
                    data=data,
                    params=params,
                    headers={"User-Agent": f"Upload-Assistant {(meta.current_version if meta.current_version is not None else 'github.com/wastaken7/Upload-Assistant')}"},
                )

            if response.status_code not in (200, 201):
                meta.tracker_status[self.tracker]["status_message"] = f"data error: HTTP {response.status_code} - {response.text}"
                return False

            response_json = response.json()
            meta.tracker_status[self.tracker]["status_message"] = "Upload successful"

            # Try to grab release ID from response
            release_id = response_json.get("public_id")
            if release_id:
                meta.tracker_status[self.tracker]["torrent_id"] = str(release_id)

            return True

        except httpx.TimeoutException:
            meta.tracker_status[self.tracker]["status_message"] = "data error: Request timed out after 60 seconds"
            return False
        except httpx.RequestError as e:
            meta.tracker_status[self.tracker]["status_message"] = f"data error: Unable to upload. Error: {e}"
            return False
        except Exception as e:
            meta.tracker_status[self.tracker]["status_message"] = f"data error: Unexpected error. Error: {e}"
            return False
