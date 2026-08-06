# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import re
from typing import Any

import aiofiles
import httpx
from rich.markup import escape

from src.cogs.redaction import Redaction
from src.console import logger
from src.get_desc import DescriptionBuilder
from src.languages import languages_manager
from src.meta import Meta
from src.rehostimages import ImageHostPolicy, RehostImagesManager
from src.trackers.common import Common
from src.trackers.UNIT3D import UNIT3D


class HawkeUno(UNIT3D):
    """
    hawke-uno (HUNO) is a Private Torrent Tracker for HD MOVIES / TV
    """

    tracker = "HAWKEUNO"
    display_name = "HawkeUno"
    allows_bloated_audio = True
    source_flag = "HUNO"
    base_url = "https://hawke.uno"
    banned_groups = (
        "4K4U",
        "Bearfish",
        "BiTOR",
        "BONE",
        "D3FiL3R",
        "d3g",
        "DTR",
        "ELiTE",
        "EVO",
        "eztv",
        "EzzRips",
        "FGT",
        "HashMiner",
        "HETeam",
        "HEVCBay",
        "HiQVE",
        "HR-DR",
        "iFT",
        "ION265",
        "iVy",
        "JATT",
        "Joy",
        "LAMA",
        "m3th",
        "MeGusta",
        "MRN",
        "Musafirboy",
        "OEPlus",
        "Pahe.in",
        "PHOCiS",
        "PSA",
        "RARBG",
        "RMTeam",
        "ShieldBearer",
        "SiQ",
        "TBD",
        "Telly",
        "TSP",
        "VXT",
        "WKS",
        "YAWNiX",
        "YIFY",
        "YTS",
    )
    approved_image_hosts = (
        "imgbox",
        "imgbb",
        "pixhost",
        "bam",
        "onlyimage",
        "ptscreens",
        "passtheimage",
        "hawke.pics",
    )
    image_host_policy = ImageHostPolicy(
        {
            "ibb.co": "imgbb",
            "pixhost.to": "pixhost",
            "imgbox.com": "imgbox",
            "imagebam.com": "bam",
            "hawke.pics": "hawke.pics",
            "onlyimage.org": "onlyimage",
            "ptscreens.com": "ptscreens",
            "passtheimage.me": "passtheimage",
        },
        approved_image_hosts,
    )
    id_url = f"{base_url}/api/torrents/"
    upload_url = f"{base_url}/api/torrents/upload"
    search_url = f"{base_url}/api/torrents/filter"
    torrent_url = f"{base_url}/torrents/"
    requests_url = f"{base_url}/api/requests/filter"
    tracker_urls = ("https://hawke.uno",)
    supported_categories = ("TV", "MOVIE")

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config, "HAWKEUNO")
        self.config = config
        self.common = Common(config)
        self.rehost_images_manager = RehostImagesManager(config)
        self.announce_url = str(self.config.get("TRACKERS", {}).get(self.tracker, {}).get("announce_url", "")).strip()

    async def get_additional_checks(self, meta: Meta) -> bool:
        should_continue = True

        # No WEBRIPs allowed
        if meta.type == "WEBRIP":
            logger.info(f"{self.tracker}: [bold red]WEB-RIP is not allowed, skipping upload.[/bold red]")
            return False

        # Check language requirements
        if not meta.language_checked:
            await languages_manager.process_desc_language(meta, tracker=self.tracker)
        audio_languages = meta.audio_languages
        if not audio_languages:
            logger.info(f"{self.tracker}: [bold red]No audio languages found, skipping upload.[/bold red]")
            return False

        # Check if mediainfo is valid
        if not meta.valid_mi_settings:
            logger.info(f"{self.tracker}: [bold red]No encoding settings in mediainfo, skipping upload.[/bold red]")
            return False

        # Check if x265 or HEVC is used
        if not meta.is_disc and meta.type in ["ENCODE", "DVDRIP", "HDTV"] and ("x265" in meta.video_encode or "HEVC" in meta.video_codec):
            tracks = meta.mediainfo.get("media", {}).get("track", [])
            for track in tracks:
                if track.get("@type") == "Video":
                    encoding_settings = track.get("Encoded_Library_Settings", {})

                    if encoding_settings:
                        crf_match = re.search(r"crf[ =:]+([\d.]+)", encoding_settings, re.IGNORECASE)
                        if crf_match:
                            logger.debug(f"{self.tracker}: Found CRF value: {crf_match.group(1)}")
                            crf_value = float(crf_match.group(1))
                            if crf_value > 22:
                                if not meta.unattended:
                                    logger.info(f"{self.tracker}: CRF value too high: {crf_value} for HawkeUno")
                                return False
                        else:
                            logger.debug(f"{self.tracker}: No CRF value found in encoding settings.")
                            bit_rate = track.get("BitRate")
                            if bit_rate and "Animation" not in meta.genre:
                                try:
                                    bit_rate_num = int(bit_rate)
                                except ValueError, TypeError:
                                    bit_rate_num = None

                                if bit_rate_num is not None:
                                    bit_rate_kbps = bit_rate_num / 1000

                                    if bit_rate_kbps < 3000:
                                        if not meta.unattended:
                                            logger.info(f"{self.tracker}: Video bitrate too low: {bit_rate_kbps:.0f} kbps for HawkeUno")
                                        return False

        return should_continue

    async def get_description(self, meta: Meta) -> None:
        desc = await DescriptionBuilder(self.tracker, self.config).unit3d_edit_desc(
            meta,
            approved_image_hosts=self.approved_image_hosts,
            signature=f"[right][url=https://github.com/wastaken7/Upload-Assistant][size=8]{meta.ua_signature}[/size][/url][/right]",
        )
        async with aiofiles.open(f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/[{self.tracker}]DESCRIPTION.txt", "w", encoding="utf-8") as f:
            await f.write(desc)

    async def get_internal(self, meta: Meta) -> int:
        internal = 0
        # Internal
        if meta.tag and (
            self.config["TRACKERS"][self.tracker].get("internal", False) is True and meta.tag[1:] in self.config["TRACKERS"][self.tracker].get("internal_groups", [])
        ):
            internal = 1

        return internal

    async def get_resolution_id(self, meta: Meta, resolution: str = "", reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        resolution_id = {
            "Other": "10",
            "4320p": "1",
            "2160p": "2",
            "1080p": "3",
            "1080i": "4",
            "720p": "5",
            "576p": "6",
            "576i": "7",
            "540p": "11",
            # no mapping for 540i
            "540i": "11",
            "480p": "8",
            "480i": "9",
        }
        if mapping_only:
            return resolution_id
        if reverse:
            return {v: k for k, v in resolution_id.items()}
        if resolution:
            return {"resolution_id": resolution_id.get(resolution, "10")}
        meta_resolution = meta.resolution
        resolved_id = resolution_id.get(meta_resolution, "10")
        return {"resolution_id": resolved_id}

    async def get_type_id(self, meta: Meta, media_type: str = "", reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        type_id = {
            "DISC": "1",
            "REMUX": "2",
            "WEBDL": "3",
            "WEBRIP": "15",
            "HDTV": "15",
            "ENCODE": "15",
            "DVDRIP": "15",
        }
        if mapping_only:
            return type_id
        if reverse:
            return {v: k for k, v in type_id.items()}
        if media_type:
            return {"type_id": type_id.get(media_type, "0")}
        meta_type = meta.type or ""
        resolved_id = type_id.get(meta_type, "0")
        return {"type_id": resolved_id}

    async def get_data(self, meta: Meta) -> dict[str, Any]:
        await self.get_description(meta)

        data: dict[str, Any] = {
            "category_id": 1 if meta.category == "MOVIE" else 2,
            "type_id": (await self.get_type_id(meta))["type_id"],
            "tmdb": meta.tmdb,
            "anonymous": int(bool(meta.anon) or self.tracker_config.get("anon", False)),
            "imdb": meta.imdb_id,
        }

        internal = await self.get_internal(meta)
        if internal == 1:
            data["internal"] = 1

        data["edition"] = meta.edition
        if meta.repack:
            data["release_tag"] = meta.repack

        if meta.is_disc:
            region = meta.region
            distributor = meta.distributor
            if region:
                data["region"] = region
            if distributor:
                data["distributor"] = distributor

        if meta.category == "TV":
            season_int = meta.season_int
            episode_int = meta.episode_int
            tvdb = meta.tvdb_id
            mal_id = meta.mal_id

            if season_int:
                data["season_number"] = season_int
            if episode_int:
                data["episode_number"] = episode_int
            if tvdb:
                data["tvdb"] = tvdb
            if mal_id:
                data["mal"] = mal_id
            data["season_pack"] = meta.tv_pack

        return data

    async def get_files(self, meta: Meta) -> dict[str, tuple[str, bytes, str]]:
        files: dict[str, tuple[str, bytes, str]] = {}
        await self.common.create_torrent_for_upload(meta, self.tracker, self.source_flag, announce_url=self.announce_url)
        torrent_path = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/[{self.tracker}].torrent"
        async with aiofiles.open(torrent_path, "rb") as f:
            files["torrent"] = (f"{meta.clean_name}.torrent", await f.read(), "application/x-bittorrent")

        desc_path = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/[{self.tracker}]DESCRIPTION.txt"
        async with aiofiles.open(desc_path, "rb") as f:
            files["description"] = ("description.txt", await f.read(), "text/plain")

        if meta.is_disc == "BDMV":
            bdinfo_path = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/BD_SUMMARY_00.txt"
            async with aiofiles.open(bdinfo_path, "rb") as f:
                files["bdinfo"] = ("bdinfo.txt", await f.read(), "text/plain")
        else:
            mediainfo_path = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/MEDIAINFO_CLEANPATH.txt"
            async with aiofiles.open(mediainfo_path, "rb") as f:
                files["mediainfo"] = ("mediainfo.txt", await f.read(), "text/plain")

        return files

    async def upload(self, meta: Meta) -> bool:
        data = await self.get_data(meta)

        # Initialize tracker status
        meta.tracker_status.setdefault(self.tracker, {})
        status_dict = meta.tracker_status[self.tracker]

        api_token = str(self.config["TRACKERS"][self.tracker].get("api_key", ""))
        url = f"{self.upload_url}?api_token={api_token}"

        if meta.debug:
            logger.debug(f"{self.tracker}: [cyan]Request Data:")
            logger.debug(Redaction.redact_private_info(data))
            status_dict["status_message"] = "Debug mode enabled, not uploading."
            await self.common.create_torrent_for_upload(meta, f"{self.tracker}_DEBUG", f"{self.tracker}_DEBUG", announce_url="https://fake.tracker")
            return True

        try:
            files = await self.get_files(meta)

            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.post(url=url, data=data, files=files)
                response.raise_for_status()
                response_json = response.json()

                if response_json.get("success") is True:
                    response_data = response_json.get("data", {})
                    moderation_status = response_data.get("moderation_status", "")
                    warnings = response_data.get("warnings", [])
                    name_issues = response_data.get("name_issues", [])
                    status_message = f"{response_json.get('message')}\nModeration Status: {moderation_status}\nWarnings: {warnings}\nName Issues: {name_issues}"
                    status_dict["status_message"] = status_message
                    return True
                error_msg = response_json.get("message", "Unknown error")
                status_dict["status_message"] = f"data error: API error: {error_msg}"
                logger.info(f"{self.tracker}: [yellow]Upload to {self.tracker} failed: {error_msg}[/yellow]")
                return False

        except httpx.HTTPStatusError as e:
            msg = f"HTTP {e.response.status_code} - {e.response.text}"
            status_dict["status_message"] = f"data error: {msg}"
            logger.info(f"{self.tracker}: [bold red]Upload error: {escape(str(msg))}[/bold red]")
            return False
        except (httpx.RequestError, ValueError, KeyError) as e:
            status_dict["status_message"] = f"data error: {e}"
            logger.info(f"{self.tracker}: [bold red]Upload connection/parsing error: {escape(str(e))}[/bold red]")
            return False
        except Exception as e:
            status_dict["status_message"] = f"data error: {e}"
            logger.info(f"{self.tracker}: [bold red]Upload unexpected error: {escape(str(e))}[/bold red]")
            raise
