# Upload Assistant © 2026 Audionut & wastaken7 — Licensed under UAPL v1.0
"""BroadcasTheNet (BTN) tracker adapter.

BTN's upload form is deliberately not treated as a static API: it must first
autofill the series data and then receive the final torrent and MediaInfo.
This adapter keeps that transaction on one authenticated cookie session and
replaces the locally-created torrent with BTN's registered torrent afterwards.
"""

import re
import unicodedata
from pathlib import Path
from typing import Any

import aiofiles
import httpx

from src.console import logger
from src.exceptions import UploadError
from src.mediainfo import strip_report_by_line
from src.meta import Meta
from src.trackers.common import Common

Config = dict[str, Any]


class BroadcasTheNet:
    """BTN TV uploader using its JSON-RPC lookup API and cookie upload form."""

    auth_type = "cookies"
    tracker = "BROADCASTHENET"
    display_name = "BroadcasTheNet"
    source_flag = "BTN"
    base_url = "https://backup.landof.tv"
    api_url = "https://api.broadcasthe.net/"
    upload_url = f"{base_url}/upload.php"
    supported_categories = ("TV",)
    tracker_urls = ("https://broadcasthe.net", "https://backup.landof.tv", "https://landof.tv")
    comment_hosts = ("broadcasthe.net", "backup.landof.tv", "landof.tv")
    banned_groups = ()
    _input_pattern = re.compile(r"(?is)<input\b[^>]*>")
    _textarea_pattern = re.compile(r"(?is)<textarea[^>]*name=[\"']([^\"']+)[\"'][^>]*>(.*?)</textarea>")
    _select_pattern = re.compile(r"(?is)<select[^>]*name=[\"']([^\"']+)[\"'][^>]*>(.*?)</select>")

    def __init__(self, config: Config) -> None:
        self.config = config
        self.common = Common(config)
        trackers = config.get("TRACKERS", {})
        settings = trackers.get(self.tracker, trackers.get("BTN", {})) if isinstance(trackers, dict) else {}
        self.settings = settings if isinstance(settings, dict) else {}
        self.api_key = str(self.settings.get("api_key") or config.get("DEFAULT", {}).get("btn_api") or "").strip()
        self.api_url = str(self.settings.get("api_url") or self.api_url).strip()
        self.base_url = str(self.settings.get("base_url") or self.base_url).rstrip("/")
        self.upload_url = f"{self.base_url}/upload.php"

    async def edit_desc(self, _meta: Meta) -> None:
        # BTN consumes MediaInfo in release_desc; it does not use UA's generic description.
        return

    async def get_additional_checks(self, meta: Meta) -> bool:
        if meta.category != "TV":
            logger.info(f"{self.tracker}: [red]BTN only accepts TV uploads.[/red]")
            return False
        if not self.api_key:
            logger.info(f"{self.tracker}: [red]BTN requires api_key (or legacy DEFAULT.btn_api) for duplicate checks and torrent retrieval.[/red]")
            return False
        if not int(meta.tvdb_id or 0) and not int(meta.imdb_id or 0):
            logger.info(f"{self.tracker}: [red]BTN requires a TVDB or IMDb ID.[/red]")
            return False
        return True

    async def validate_credentials(self, meta: Meta) -> bool:
        cookie_file = self._cookie_file(meta)
        if not Path(cookie_file).exists():
            logger.info(f"{self.tracker}: [red]Missing cookie file (data/cookies/BROADCASTHENET.txt; BTN.txt is also accepted).[/red]")
            return False
        cookies = await self.common.parse_cookie_file(cookie_file)
        try:
            async with httpx.AsyncClient(cookies=cookies, follow_redirects=True, timeout=30.0) as client:
                response = await client.get(self.upload_url)
        except httpx.HTTPError as exc:
            logger.info(f"{self.tracker}: [red]Cookie validation failed: {exc}[/red]")
            return False
        valid = response.is_success and "login.php" not in str(response.url).lower() and "file_input" in response.text.lower()
        if not valid:
            logger.info(f"{self.tracker}: [red]Cookie is expired/invalid or BTN upload access was not confirmed.[/red]")
        return valid

    def _cookie_file(self, meta: Meta) -> str:
        """Prefer the public tracker name while retaining existing BTN exports."""
        from src.cookie_auth import find_cookie_file

        cookie_file = find_cookie_file(meta.base_dir, self.tracker, self.config)
        if Path(cookie_file).exists():
            return cookie_file
        return find_cookie_file(meta.base_dir, "BTN", self.config)

    @staticmethod
    def _clean_name(value: str) -> str:
        value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
        value = value.replace("&", " and ").replace("'", "")
        value = re.sub(r"\s+", ".", value.strip())
        value = re.sub(r"(?i)\.DDP\.(\d(?:\.\d+)?)\.Atmos", r".DDPA\1", value)
        value = re.sub(r"(?i)\.TrueHD\.(\d(?:\.\d+)?)\.Atmos", r".TrueHDA\1", value)
        value = re.sub(r"(?i)\.(DDP|DD|AC3|DTS|AAC|FLAC|TrueHD|PCM|LPCM)\.(\d)", r".\1\2", value)
        value = re.sub(r"[^A-Za-z0-9.\-]+", ".", value)
        return re.sub(r"\.{2,}", ".", value).strip(".-")

    async def get_name(self, meta: Meta) -> str:
        name = str(meta.get("scene_name") or meta.name or meta.basename_no_ext or "")
        name = re.sub(r"(?i)\.(avi|mkv|mp4|ts|m4v|m2ts|wmv|mpeg|mpg|vob)$", "", name)
        name = self._clean_name(name)
        if str(meta.resolution).lower() in {"sd", "480i", "480p", "576i", "576p"}:
            name = re.sub(r"(?i)(?:^|\.)(?:sd|\d{3,4}[pi])(?=\.|$)", ".", name)
            name = re.sub(r"\.{2,}", ".", name).strip(".")
        tag = str(meta.tag or "").lstrip("-")
        if tag and not re.search(r"-[^.\-]+$", name):
            name += f"-{tag}"
        elif not tag and not re.search(r"-(?:nogrp|nogroup|unknown|unk)$", name, re.I):
            name += "-NOGRP"
        return name

    async def _api(self, method: str, params: list[Any]) -> dict[str, Any]:
        payload = {"jsonrpc": "2.0", "id": "upload-assistant-btn", "method": method, "params": [self.api_key, *params]}
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(self.api_url, json=payload)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict) or data.get("error"):
            raise UploadError(f"BTN API error: {data.get('error') if isinstance(data, dict) else 'invalid response'}", "red")
        return data

    async def search_existing(self, meta: Meta) -> list[dict[str, Any]]:
        if not self.api_key:
            return []
        filters: dict[str, Any] = {"category": "Episode"}
        if int(meta.tvdb_id or 0):
            filters["tvdb"] = str(meta.tvdb_id)
        elif int(meta.imdb_id or 0):
            filters["imdb"] = str(meta.imdb_id)
        else:
            filters["searchstr"] = str(meta.title)
        try:
            result = await self._api("getTorrents", [filters, 100, 0])
        except (httpx.HTTPError, ValueError, UploadError) as exc:
            logger.warning(f"{self.tracker}: duplicate lookup failed: {exc}")
            return []
        payload = result.get("result", {})
        torrents = payload.get("torrents", {}) if isinstance(payload, dict) else {}
        if not isinstance(torrents, dict):
            return []
        dupes: list[dict[str, Any]] = []
        for torrent_id, item in torrents.items():
            if not isinstance(item, dict):
                continue
            group_id = str(item.get("GroupID") or item.get("groupId") or "")
            dupes.append(
                {
                    "name": str(item.get("ReleaseName") or item.get("releaseName") or item.get("Name") or ""),
                    "size": int(item.get("Size") or item.get("size") or 0),
                    "files": str(item.get("FileList") or item.get("fileList") or ""),
                    "file_count": int(item.get("FileCount") or item.get("fileCount") or 1),
                    "link": f"{self.base_url}/torrents.php?id={group_id}&torrentid={torrent_id}",
                }
            )
        return dupes

    @staticmethod
    def _mapping(meta: Meta) -> tuple[str, str, str, str]:
        container = {
            "mkv": "MKV",
            "matroska": "MKV",
            "mp4": "MP4",
            "avi": "AVI",
            "ts": "TS",
            "m2ts": "M2TS",
            "m4v": "M4V",
            "wmv": "WMV",
            "mpeg": "MPEG",
            "mpg": "MPEG",
            "vob": "VOB",
        }.get(str(meta.container).lower(), "Mixed")
        codec_text = f"{meta.video_encode} {meta.video_codec}".lower()
        codec = (
            "H.265"
            if any(x in codec_text for x in ("hevc", "h.265", "x265"))
            else "H.264"
            if any(x in codec_text for x in ("avc", "h.264", "x264"))
            else "VP9"
            if "vp9" in codec_text
            else "MPEG2"
            if "mpeg" in codec_text
            else "Mixed"
        )
        source_text = f"{meta.type} {meta.source}".lower()
        source = (
            "WEB-DL"
            if "web-dl" in source_text or "webdl" in source_text
            else "WEBRip"
            if "webrip" in source_text
            else "HDTV"
            if "hdtv" in source_text
            else "Bluray"
            if "bluray" in source_text or "blu-ray" in source_text
            else "BDRip"
            if "bdrip" in source_text
            else "Unknown"
        )
        resolution = (
            "2160p"
            if str(meta.resolution).lower() in {"2160p", "4k", "4320p", "8640p"}
            else str(meta.resolution)
            if str(meta.resolution) in {"1080p", "1080i", "720p"}
            else "SD"
        )
        return container, codec, source, resolution

    def _form_fields(self, html: str) -> dict[str, str]:
        def attribute(tag: str, name: str) -> str:
            match = re.search(rf"(?is)\b{re.escape(name)}\s*=\s*[\"']([^\"']*)[\"']", tag)
            return match.group(1) if match else ""

        fields = {}
        for tag in self._input_pattern.findall(html):
            name = attribute(tag, "name")
            if name:
                fields[name] = attribute(tag, "value")
        fields.update({name: re.sub(r"(?is)<[^>]+>", "", value).strip() for name, value in self._textarea_pattern.findall(html)})
        for name, options in self._select_pattern.findall(html):
            selected = re.search(r"(?is)<option(?=[^>]*\bselected\b)[^>]*\bvalue=[\"']([^\"']*)", options)
            if selected:
                fields[name] = selected.group(1)
        return fields

    async def upload(self, meta: Meta) -> bool:
        await self.common.create_torrent_for_upload(meta, self.tracker, self.source_flag)
        torrent_path = Path(meta.base_dir) / "tmp" / meta.uuid / f"[{self.tracker}].torrent"
        if meta.debug:
            meta.tracker_status[self.tracker]["status_message"] = "Debug mode enabled; BTN upload not submitted."
            return True
        cookie_file = self._cookie_file(meta)
        cookies = await self.common.parse_cookie_file(cookie_file)
        release_name = await self.get_name(meta)
        upload_type = "Season" if int(meta.tv_pack or 0) else "Episode"
        if int(meta.tvdb_id or 0):
            autofill_data: dict[str, str] = {
                "type": upload_type,
                "tvdb": "Get Info",
                "scene_yesno": "No",
                "auto_series": str(meta.tvdb_id),
            }
            if upload_type == "Episode":
                autofill_data["auto_title"] = f"S{int(meta.season_int or 0):02d}E{int(meta.episode_int or 0):02d}"
            else:
                autofill_data["auto_season"] = f"S{int(meta.season_int or 0):02d}"
        else:
            autofill_data = {"type": upload_type, "tvdb": "Get Info", "scene_yesno": "Yes", "autofill": release_name}
        async with aiofiles.open(Path(meta.base_dir) / "tmp" / meta.uuid / "MEDIAINFO.txt", encoding="utf-8") as handle:
            mediainfo = strip_report_by_line(await handle.read())
        async with aiofiles.open(torrent_path, "rb") as handle:
            torrent = await handle.read()
        container, codec, source, resolution = self._mapping(meta)
        try:
            async with httpx.AsyncClient(cookies=cookies, follow_redirects=True, timeout=60.0) as client:
                autofill = await client.post(self.upload_url, data=autofill_data)
                autofill.raise_for_status()
                data = self._form_fields(autofill.text)
                data.update(
                    {
                        "submit": "true",
                        "type": upload_type,
                        "scenename": release_name,
                        "format": container,
                        "bitrate": codec,
                        "media": source,
                        "resolution": resolution,
                        "release_desc": mediainfo,
                        "tvdb": "autofilled",
                    }
                )
                data = {key: value for key, value in data.items() if value or key == "release_desc"}
                response = await client.post(self.upload_url, data=data, files={"file_input": ("upload.torrent", torrent, "application/x-bittorrent")})
                response.raise_for_status()
                match = re.search(r"torrents\.php\?id=(\d+)(?:&(?:amp;)?torrentid=(\d+))?", str(response.url) + response.text)
                if not match or not match.group(2):
                    raise UploadError("BTN upload did not return a registered torrent ID", "red")
                group_id, torrent_id = match.group(1), match.group(2)
                download = await client.get(f"{self.base_url}/torrents.php?action=download&id={torrent_id}")
                download.raise_for_status()
                if not download.content.startswith(b"d"):
                    raise UploadError("BTN returned a non-torrent response after upload", "red")
                async with aiofiles.open(torrent_path, "wb") as handle:
                    await handle.write(download.content)
        except (httpx.HTTPError, OSError, UploadError) as exc:
            meta.tracker_status[self.tracker]["status_message"] = f"data error: {exc}"
            logger.info(f"{self.tracker}: [red]{exc}[/red]")
            return False
        meta.tracker_status[self.tracker].update(
            {"status_message": f"{self.base_url}/torrents.php?id={group_id}&torrentid={torrent_id}", "torrent_id": torrent_id, "group_id": group_id}
        )
        return True
