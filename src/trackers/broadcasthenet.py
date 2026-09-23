# Upload Assistant © 2026 Audionut & wastaken7 — Licensed under UAPL v1.0
"""BroadcasTheNet (BTN) tracker adapter.

BTN's upload form is deliberately not treated as a static API: it must first
autofill the series data and then receive the final torrent and MediaInfo.
This adapter keeps that transaction on one authenticated cookie session and
replaces the locally-created torrent with BTN's registered torrent afterwards.
"""

import asyncio
import re
import unicodedata
from pathlib import Path
from typing import Any, ClassVar, cast
from urllib.parse import parse_qs, urlparse

import aiofiles
import httpx
from torf import TorfError, Torrent

from src.console import logger
from src.exceptions import UploadError
from src.mediainfo import strip_report_by_line
from src.meta import Meta
from src.trackers.common import Common

Config = dict[str, Any]


class BroadcasTheNet:
    """
    BTN TV uploader using its JSON-RPC lookup API and cookie upload form.
    https://apidocs.broadcasthe.net/
    """

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
    _country_map: ClassVar[dict[str, str]] = {
        "se": "1",
        "swe": "1",
        "sweden": "1",
        "us": "2",
        "usa": "2",
        "united states": "2",
        "united states of america": "2",
        "ru": "3",
        "rus": "3",
        "russia": "3",
        "russian federation": "3",
        "fi": "4",
        "fin": "4",
        "finland": "4",
        "ca": "5",
        "can": "5",
        "canada": "5",
        "fr": "6",
        "fra": "6",
        "france": "6",
        "de": "7",
        "deu": "7",
        "germany": "7",
        "cn": "8",
        "chn": "8",
        "china": "8",
        "it": "9",
        "ita": "9",
        "italy": "9",
        "dk": "10",
        "dnk": "10",
        "denmark": "10",
        "no": "11",
        "nor": "11",
        "norway": "11",
        "gb": "12",
        "uk": "12",
        "gbr": "12",
        "united kingdom": "12",
        "ie": "13",
        "irl": "13",
        "ireland": "13",
        "pl": "14",
        "pol": "14",
        "poland": "14",
        "nl": "15",
        "nld": "15",
        "netherlands": "15",
        "be": "16",
        "bel": "16",
        "belgium": "16",
        "jp": "17",
        "jpn": "17",
        "japan": "17",
        "br": "18",
        "bra": "18",
        "brazil": "18",
        "ar": "19",
        "arg": "19",
        "argentina": "19",
        "au": "20",
        "aus": "20",
        "australia": "20",
        "nz": "21",
        "nzl": "21",
        "new zealand": "21",
        "es": "22",
        "esp": "22",
        "spain": "22",
        "pt": "23",
        "prt": "23",
        "portugal": "23",
        "mx": "24",
        "mex": "24",
        "mexico": "24",
        "sg": "25",
        "sgp": "25",
        "singapore": "25",
        "za": "26",
        "zaf": "26",
        "south africa": "26",
        "kr": "27",
        "kor": "27",
        "south korea": "27",
        "jm": "28",
        "jam": "28",
        "jamaica": "28",
        "lu": "29",
        "lux": "29",
        "luxembourg": "29",
        "hk": "30",
        "hkg": "30",
        "hong kong": "30",
        "bz": "31",
        "blz": "31",
        "belize": "31",
        "dz": "32",
        "dza": "32",
        "algeria": "32",
        "ao": "33",
        "ago": "33",
        "angola": "33",
        "at": "34",
        "aut": "34",
        "austria": "34",
        "yu": "35",
        "yug": "35",
        "yugoslavia": "35",
        "ws": "36",
        "wsm": "36",
        "western samoa": "36",
        "my": "37",
        "mys": "37",
        "malaysia": "37",
        "do": "38",
        "dom": "38",
        "dominican republic": "38",
        "gr": "39",
        "grc": "39",
        "greece": "39",
        "gt": "40",
        "gtm": "40",
        "guatemala": "40",
        "il": "41",
        "isr": "41",
        "israel": "41",
        "pk": "42",
        "pak": "42",
        "pakistan": "42",
        "cz": "43",
        "cze": "43",
        "czech republic": "43",
        "czechia": "43",
        "rs": "44",
        "srb": "44",
        "serbia": "44",
        "sc": "45",
        "syc": "45",
        "seychelles": "45",
        "tw": "46",
        "twn": "46",
        "taiwan": "46",
        "pr": "47",
        "pri": "47",
        "puerto rico": "47",
        "cl": "48",
        "chl": "48",
        "chile": "48",
        "cu": "49",
        "cub": "49",
        "cuba": "49",
        "cg": "50",
        "cog": "50",
        "congo": "50",
        "af": "51",
        "afg": "51",
        "afghanistan": "51",
        "tr": "52",
        "tur": "52",
        "turkey": "52",
        "uz": "53",
        "uzb": "53",
        "uzbekistan": "53",
        "ch": "54",
        "che": "54",
        "switzerland": "54",
        "ki": "55",
        "kir": "55",
        "kiribati": "55",
        "ph": "56",
        "phl": "56",
        "philippines": "56",
        "bf": "57",
        "bfa": "57",
        "burkina faso": "57",
        "ng": "58",
        "nga": "58",
        "nigeria": "58",
        "is": "59",
        "isl": "59",
        "iceland": "59",
        "nr": "60",
        "nru": "60",
        "nauru": "60",
        "si": "61",
        "svn": "61",
        "slovenia": "61",
        "al": "62",
        "alb": "62",
        "albania": "62",
        "tm": "63",
        "tkm": "63",
        "turkmenistan": "63",
        "ba": "64",
        "bih": "64",
        "bosnia herzegovina": "64",
        "bosnia and herzegovina": "64",
        "ad": "65",
        "and": "65",
        "andorra": "65",
        "lt": "66",
        "ltu": "66",
        "lithuania": "66",
        "in": "67",
        "ind": "67",
        "india": "67",
        "an": "68",
        "ant": "68",
        "netherlands antilles": "68",
        "ua": "69",
        "ukr": "69",
        "ukraine": "69",
        "ve": "70",
        "ven": "70",
        "venezuela": "70",
        "hu": "71",
        "hun": "71",
        "hungary": "71",
        "ro": "72",
        "rou": "72",
        "romania": "72",
        "vu": "73",
        "vut": "73",
        "vanuatu": "73",
        "vn": "74",
        "vnm": "74",
        "vietnam": "74",
        "tt": "75",
        "tto": "75",
        "trinidad": "75",
        "trinidad and tobago": "75",
        "hn": "76",
        "hnd": "76",
        "honduras": "76",
        "kg": "77",
        "kgz": "77",
        "kyrgyzstan": "77",
        "ec": "78",
        "ecu": "78",
        "ecuador": "78",
        "bs": "79",
        "bhs": "79",
        "bahamas": "79",
        "pe": "80",
        "per": "80",
        "peru": "80",
        "kh": "81",
        "khm": "81",
        "cambodia": "81",
        "bb": "82",
        "brb": "82",
        "barbados": "82",
        "bd": "83",
        "bgd": "83",
        "bangladesh": "83",
        "la": "84",
        "lao": "84",
        "laos": "84",
        "uy": "85",
        "ury": "85",
        "uruguay": "85",
        "ag": "86",
        "atg": "86",
        "antigua barbuda": "86",
        "antigua and barbuda": "86",
        "py": "87",
        "pry": "87",
        "paraguay": "87",
        "su": "88",
        "sun": "88",
        "soviet": "88",
        "soviet union": "88",
        "ussr": "88",
        "union of soviet socialist repu": "88",
        "th": "89",
        "tha": "89",
        "thailand": "89",
        "sn": "90",
        "sen": "90",
        "senegal": "90",
        "tg": "91",
        "tgo": "91",
        "togo": "91",
        "kp": "92",
        "prk": "92",
        "north korea": "92",
        "hr": "93",
        "hrv": "93",
        "croatia": "93",
        "ee": "94",
        "est": "94",
        "estonia": "94",
        "co": "95",
        "col": "95",
        "colombia": "95",
        "lb": "96",
        "lbn": "96",
        "lebanon": "96",
        "lv": "97",
        "lva": "97",
        "latvia": "97",
        "cr": "98",
        "cri": "98",
        "costa rica": "98",
        "eg": "99",
        "egy": "99",
        "egypt": "99",
        "bg": "100",
        "bgr": "100",
        "bulgaria": "100",
        "isle de muerte": "101",
        "fj": "102",
        "fji": "102",
        "fiji": "102",
        "mk": "103",
        "mkd": "103",
        "macedonia": "103",
        "kw": "104",
        "kwt": "104",
        "kuwait": "104",
        "lk": "105",
        "lka": "105",
        "sri lanka": "105",
        "ir": "106",
        "irn": "106",
        "iran": "106",
        "arab league": "107",
        "sa": "108",
        "sau": "108",
        "saudi arabia": "108",
        "scotland": "109",
        "sk": "110",
        "svk": "110",
        "slovakia": "110",
        "id": "111",
        "idn": "111",
        "indonesia": "111",
        "wales": "112",
        "bn": "113",
        "brn": "113",
        "brunei": "113",
    }

    def __init__(self, config: Config) -> None:
        self.config = config
        self.common = Common(config)
        trackers: dict[str, Any] = cast(dict[str, Any], config.get("TRACKERS", {}))
        settings = trackers.get(self.tracker, trackers.get("BTN", {}))
        self.settings: dict[str, Any] = cast(dict[str, Any], settings) if isinstance(settings, dict) else {}
        defaults = cast(dict[str, Any], config.get("DEFAULT", {}))
        self.api_key = str(self.settings.get("api_key") or defaults.get("btn_api") or "").strip()
        self.api_url = str(self.settings.get("api_url") or self.api_url).strip()
        self.base_url = str(self.settings.get("base_url") or self.base_url).rstrip("/")
        self.upload_url = f"{self.base_url}/upload.php"

    async def edit_desc(self, _meta: Meta) -> None:
        # BTN consumes MediaInfo in release_desc; it does not use UA's generic description.
        return

    async def get_additional_checks(self, meta: Meta) -> bool:
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
        logger.debug(f"{self.tracker}: Loaded {len(cookies)} cookies from {cookie_file}")
        try:
            async with httpx.AsyncClient(cookies=cookies, follow_redirects=True, timeout=30.0) as client:
                response = await client.get(self.upload_url)
        except httpx.HTTPError as exc:
            logger.info(f"{self.tracker}: [red]Cookie validation failed: {exc}[/red]")
            return False
        # The initial GET may expose either the upload control or the autofill control.
        form_fields = self._form_fields(response.text)
        has_file_input = "file_input" in form_fields
        has_autofill = "autofill" in form_fields
        valid = response.is_success and "login.php" not in str(response.url).lower() and (has_file_input or has_autofill)
        if not valid:
            logger.debug(
                f"{self.tracker}: Validation details - is_success: {response.is_success}, url: {response.url}, has_file_input: {has_file_input}, has_autofill: {has_autofill}"
            )
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
        if not meta.scene_name:
            aka = self._clean_name(str(meta.aka or ""))
            if aka:
                name = re.sub(rf"(?i)(?:^|\.){re.escape(aka)}(?=\.|$)", ".", name, count=1)

            hdr = self._clean_name(str(meta.hdr or ""))
            resolution = self._clean_name(str(meta.resolution or ""))
            if hdr and resolution:
                hdr_pattern = rf"(?i)(?:^|\.){re.escape(hdr)}(?=\.|$)"
                resolution_pattern = rf"(?i)(?:^|\.){re.escape(resolution)}(?=\.|$)"
                if re.search(hdr_pattern, name) and re.search(resolution_pattern, name):
                    name = re.sub(hdr_pattern, ".", name, count=1)
                    name = re.sub(resolution_pattern, f".{hdr}.{resolution}", name, count=1)

            name = re.sub(r"\.{2,}", ".", name).strip(".")
        if str(meta.resolution).lower() in {"sd", "480i", "480p", "576i", "576p"}:
            name = re.sub(r"(?i)(?:^|\.)(?:sd|\d{3,4}[pi])(?=\.|$)", ".", name)
            name = re.sub(r"\.{2,}", ".", name).strip(".")
        tag = str(meta.tag or "").lstrip("-")
        if tag and not re.search(r"-[^.\-]+$", name):
            name += f"-{tag}"
        elif not tag and not re.search(r"-(?:nogrp|nogroup|unknown|unk)$", name, re.I):
            name += "-NOGRP"
        return name

    async def _api(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        payload: dict[str, Any] = {"id": "upload-assistant-btn", "method": method, "params": {"key": self.api_key, **params}}
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(self.api_url, json=payload)
        response.raise_for_status()
        try:
            data: Any = response.json()
        except ValueError as exc:
            raise UploadError("BTN API returned an invalid JSON response", "red") from exc
        if not isinstance(data, dict):
            raise UploadError("BTN API error: invalid response", "red")
        data_dict = cast(dict[str, Any], data)
        if data_dict.get("error"):
            error = data_dict["error"]
            if isinstance(error, dict) and error.get("code") == -32004:
                raise UploadError("BTN API rejected this host IP. Approve the IP in your BTN notices, then retry.", "red")
            raise UploadError(f"BTN API error: {error}", "red")
        return data_dict

    async def search_existing(self, meta: Meta) -> list[dict[str, Any]]:
        if not self.api_key:
            raise UploadError("BTN API key is required to check for duplicate torrents", "red")
        filters: dict[str, Any] = {"category": "Season" if meta.tv_pack else "Episode"}
        if int(meta.tvdb_id or 0):
            filters["tvdb"] = str(meta.tvdb_id)
        elif int(meta.imdb_id or 0):
            filters["imdb"] = str(meta.imdb_id)
        else:
            title = str(meta.title).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            filters["search"] = f"%{title}%"
        dupes: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        offset = 0
        page_size = 1000
        try:
            for _ in range(100):
                result = await self._api("getTorrents", {"search": filters, "results": page_size, "offset": offset})
                payload = result.get("result")
                if not isinstance(payload, dict):
                    raise UploadError("BTN duplicate lookup returned no result", "red")
                total = int(payload["results"])
                torrents = payload.get("torrents", {})
                if not isinstance(torrents, dict):
                    raise UploadError("BTN duplicate lookup returned invalid torrents", "red")
                if not torrents and offset < total:
                    raise UploadError("BTN duplicate lookup stopped before all results were returned", "red")
                for torrent_id, item in torrents.items():
                    if torrent_id in seen_ids or not isinstance(item, dict):
                        raise UploadError("BTN duplicate lookup returned repeated or invalid torrents", "red")
                    seen_ids.add(torrent_id)
                    group_id = str(item.get("GroupID") or item.get("groupId") or "")
                    dupes.append(
                        {
                            "name": str(item.get("ReleaseName") or item.get("releaseName") or ""),
                            "size": int(item.get("Size") or item.get("size") or 0),
                            "files": "",
                            "file_count": 0,
                            "link": f"{self.base_url}/torrents.php?id={group_id}&torrentid={torrent_id}",
                        }
                    )
                offset += len(torrents)
                if offset >= total:
                    return dupes
            raise UploadError("BTN duplicate lookup exceeded the page limit", "red")
        except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
            raise UploadError(f"BTN duplicate lookup failed: {exc}", "red") from exc

    async def _uploaded_torrent_id(self, release_name: str, group_id: str) -> str:
        if not self.api_key:
            raise UploadError("BTN needs an API key to identify the uploaded torrent on a group page", "red")
        for attempt in range(4):
            if attempt:
                await asyncio.sleep(2)
            result = await self._api("getTorrents", {"search": {"group_id": group_id, "release": release_name}, "results": 1000, "offset": 0})
            payload = result.get("result")
            torrents = payload.get("torrents") if isinstance(payload, dict) else None
            if not isinstance(torrents, dict):
                continue
            matches = [
                str(torrent_id)
                for torrent_id, item in torrents.items()
                if isinstance(item, dict)
                and str(item.get("GroupID") or item.get("groupId") or "") == group_id
                and str(item.get("ReleaseName") or item.get("releaseName") or "").casefold() == release_name.casefold()
            ]
            if len(matches) == 1:
                return matches[0]
            if len(matches) > 1:
                raise UploadError("BTN returned multiple torrents matching the uploaded release", "red")
        raise UploadError("BTN did not return the uploaded torrent ID after four API checks", "red")

    @staticmethod
    def _upload_ids(response_url: str, response_html: str) -> tuple[str, str]:
        parsed = urlparse(response_url)
        if parsed.path.endswith("/torrents.php"):
            query = parse_qs(parsed.query)
            group_id = query.get("id", [""])[0]
            torrent_id = query.get("torrentid", [""])[0]
            if group_id.isdigit():
                return group_id, torrent_id if torrent_id.isdigit() else ""
        match = re.search(r"torrents\.php\?id=(\d+)", response_html)
        return (match.group(1), "") if match else ("", "")

    @staticmethod
    def _registered_torrent(content: bytes) -> bytes:
        try:
            Torrent.read_stream(content)
        except (TorfError, ValueError) as exc:
            raise UploadError("BTN returned an invalid torrent after upload", "red") from exc
        return content

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
            else "x264-Hi10P"
            if any(x in codec_text for x in ("avc", "h.264", "x264")) and (str(meta.get("bit_depth") or getattr(meta, "bit_depth", "")) == "10" or "hi10p" in codec_text)
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

        fields: dict[str, str] = {}
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
        work_dir = torrent_path.parent
        if meta.debug:
            meta.tracker_status[self.tracker]["status_message"] = "Debug mode enabled; BTN upload not submitted."
            return True
        cookie_file = self._cookie_file(meta)
        cookies = await self.common.parse_cookie_file(cookie_file)
        release_name = await self.get_name(meta)
        upload_type = "Season" if int(meta.tv_pack or 0) else "Episode"
        if meta.title:
            autofill_data: dict[str, str] = {
                "type": upload_type,
                "tvdb": "Get Info",
                "scene_yesno": "No",
                "auto_series": str(meta.title),
            }
            if upload_type == "Episode":
                autofill_data["auto_title"] = f"S{int(meta.season_int or 0):02d}E{int(meta.episode_int or 0):02d}"
            else:
                autofill_data["auto_season"] = f"S{int(meta.season_int or 0):02d}"
        else:
            autofill_data = {"type": upload_type, "tvdb": "Get Info", "scene_yesno": "Yes", "autofill": release_name}
        async with aiofiles.open(work_dir / "MEDIAINFO_CLEANPATH.txt", encoding="utf-8") as handle:
            mediainfo = strip_report_by_line(await handle.read())
        async with aiofiles.open(torrent_path, "rb") as handle:
            torrent = await handle.read()
        container, codec, source, resolution = self._mapping(meta)
        try:
            async with httpx.AsyncClient(cookies=cookies, follow_redirects=True, timeout=60.0) as client:
                autofill = await client.post(self.upload_url, data=autofill_data)
                autofill.raise_for_status()
                data = self._form_fields(autofill.text)
                tag = str(meta.tag or "").lstrip("-")
                is_no_group = not tag or bool(re.search(r"^(?:nogrp|nogroup|unknown|unk)$", tag, re.I))
                origin = "Scene" if meta.scene else "None" if is_no_group else "P2P"

                payload = {
                    "submit": "true",
                    "type": upload_type,
                    "scenename": release_name,
                    "format": container,
                    "bitrate": codec,
                    "resolution": resolution,
                    "release_desc": mediainfo,
                    "tvdb": "autofilled",
                    "origin": origin,
                }

                if self.settings.get("fast_torrent") or self.settings.get("fasttorrent"):
                    payload["fasttorrent"] = "on"

                original_language = str(meta.get("original_language") or getattr(meta, "original_language", "") or "en").lower()
                if original_language and original_language not in ("en", "eng", "english"):
                    payload["foreign"] = "on"
                    origin_countries: Any = getattr(meta, "origin_country", []) or getattr(meta, "origin_country_code", [])
                    if isinstance(origin_countries, list) and origin_countries:
                        first_country = str(origin_countries[0])
                    elif isinstance(origin_countries, str):
                        first_country = origin_countries
                    else:
                        first_country = ""
                    country_id = self._country_map.get(str(first_country).lower().strip())
                    if country_id:
                        payload["country"] = country_id

                if source != "Unknown":
                    payload["media"] = source

                data.update(payload)
                data = {key: value for key, value in data.items() if value or key == "release_desc"}
                response = await client.post(self.upload_url, data=data, files={"file_input": ("upload.torrent", torrent, "application/x-bittorrent")})
                response.raise_for_status()
                group_id, torrent_id = self._upload_ids(str(response.url), response.text)
                if not group_id:
                    failure_path = work_dir / f"[{self.tracker}]BTN_upload_failure.html"
                    async with aiofiles.open(failure_path, "w", encoding="utf-8") as f:
                        await f.write(response.text)
                    raise UploadError(f"BTN upload did not return a registered torrent ID. See {failure_path}", "red")

                if not torrent_id:
                    torrent_id = await self._uploaded_torrent_id(release_name, group_id)

                download = await client.get(f"{self.base_url}/torrents.php?action=download&id={torrent_id}")
                download.raise_for_status()
                async with aiofiles.open(torrent_path, "wb") as handle:
                    await handle.write(self._registered_torrent(download.content))
        except (httpx.HTTPError, OSError, UploadError) as exc:
            meta.tracker_status[self.tracker]["status_message"] = f"data error: {exc}"
            logger.info(f"{self.tracker}: [red]{exc}[/red]")
            return False
        meta.tracker_status[self.tracker].update(
            {"status_message": f"{self.base_url}/torrents.php?id={group_id}&torrentid={torrent_id}", "torrent_id": torrent_id, "group_id": group_id}
        )
        return True
