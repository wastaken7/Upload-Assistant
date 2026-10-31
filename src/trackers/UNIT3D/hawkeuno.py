# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import re
from typing import Any, ClassVar

import aiofiles
import httpx
from rich.markup import escape

from src import payload_preview
from src.cogs.redaction import Redaction
from src.console import logger
from src.distributors import distributor_id
from src.get_desc import DescriptionBuilder
from src.languages import languages_manager
from src.meta import Meta
from src.rehostimages import ImageHostPolicy, RehostImagesManager
from src.trackers.common import Common
from src.trackers.naming import add_incomplete_pack_marker
from src.trackers.UNIT3D import UNIT3D


class HawkeUno(UNIT3D):
    """
    hawke-uno (HUNO) is a Private Torrent Tracker for HD MOVIES / TV
    """

    tracker = "HAWKEUNO"
    display_name = "hawke-uno"
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

    # Attribute IDs from https://hawke.uno/api-docs?section=attributes
    video_codec_ids: ClassVar[dict[str, int]] = {"x265": 1, "x264": 2, "H265": 3, "H264": 4, "HEVC": 5, "AVC": 6, "VC-1": 7, "MPEG-2": 8, "AV1": 9}
    video_format_ids: ClassVar[dict[str, int]] = {"DV HDR10+": 1, "DV HDR": 2, "DV": 3, "HDR10+": 4, "HDR": 5, "PQ10": 6, "HLG": 7, "SDR": 8}
    audio_format_ids: ClassVar[dict[str, int]] = {
        "TrueHD Atmos": 1,
        "TrueHD": 2,
        "DTS-HD MA Auro3D": 3,
        "DTS-HD MA": 4,
        "DTS-HD HRA": 5,
        "DTS:X": 6,
        "DTS": 7,
        "DDP Atmos": 8,
        "DDP": 9,
        "DD": 10,
        "AAC": 11,
        "FLAC": 12,
        "LPCM": 13,
        "MP3": 14,
        "MP2": 15,
        "VORBIS": 16,
        "OPUS": 17,
        "NONE": 18,
    }
    audio_channel_ids: ClassVar[dict[str, int]] = {
        "13.1": 1,
        "12.1": 2,
        "11.1": 3,
        "10.1": 4,
        "9.1": 5,
        "7.1": 6,
        "6.1": 7,
        "5.1": 8,
        "5.0": 9,
        "4.0": 10,
        "2.1": 11,
        "2.0": 12,
        "1.0": 13,
    }
    source_type_ids: ClassVar[dict[str, int]] = {
        "UHD BluRay": 1,
        "UHD BluRay Hybrid": 2,
        "BluRay": 3,
        "BluRay Hybrid": 4,
        "HD-DVD": 5,
        "HD-DVD Hybrid": 6,
        "DVD9": 7,
        "DVD5": 8,
        "WEB-DL": 9,
        "WEB-DL Hybrid": 10,
        "HDTV": 11,
        "SDTV": 12,
        "DVD": 13,
    }
    edition_ids: ClassVar[dict[str, int]] = {
        "IMAX": 1,
        "OPEN MATTE": 2,
        "Extended": 3,
        "Ultimate": 4,
        "Directors Cut": 5,
        "Theatrical": 6,
        "Anniversary": 7,
        "Special": 8,
        "Limited": 9,
        "Collectors": 10,
        "Unrated": 11,
        "Uncut": 12,
        "Criterion": 13,
        "Final Cut": 14,
        "Redux": 15,
        "Restored": 16,
        "3D": 17,
        "Assembly": 18,
        "Remastered": 19,
        "4K Remaster": 20,
        "Superbit": 21,
        "Black and White": 22,
    }
    release_tags = (
        "REPACK",
        "REPACK2",
        "REPACK3",
        "REPACK4",
        "REPACK5",
        "REPACK6",
        "REPACK7",
        "REPACK8",
        "REPACK9",
        "PROPER",
        "PROPER2",
        "PROPER3",
        "PROPER4",
        "PROPER5",
        "INCOMPLETE",
        "DUBBED",
        "SUBBED",
    )
    regions = (
        "PAL", "NTSC", "RA", "RB", "RC", "RF", "USA", "GBR", "DEU", "FRA", "ITA", "ESP", "JPN", "KOR", "CHN",
        "HKG", "TWN", "AUS", "CAN", "NLD", "SWE", "NOR", "DNK", "POL", "RUS", "BRA", "MEX", "IND", "GER",
    )  # fmt: skip
    sd_resolutions = ("576p", "576i", "540p", "540i", "480p", "480i")

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config, "HAWKEUNO")
        self.config = config
        self.common = Common(config)
        self.rehost_images_manager = RehostImagesManager(config)
        self.announce_url = str(self.config.get("TRACKERS", {}).get(self.tracker, {}).get("announce_url", "")).strip()

    async def get_additional_checks(self, meta: Meta) -> bool:
        should_continue = True

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
        if not meta.is_disc and meta.type in ["ENCODE", "DVDRIP", "HDTV", "WEBRIP"] and ("x265" in meta.video_encode or "HEVC" in meta.video_codec):
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

    def _normalize_upload_name(self, name: str, meta: Meta) -> str:
        normalized = name
        if meta.type == "WEBRIP":
            normalized = re.sub(r"\bWEB[ ._-]?RIP\b", "WEB-DL", normalized, flags=re.IGNORECASE)

        separator = "." if " " not in normalized and "." in normalized else " "

        if meta.type in {"WEBDL", "WEBRIP"} and not meta.service and not re.search(r"\bNADA\b", normalized, flags=re.IGNORECASE):
            normalized = re.sub(r"\b(WEB(?:[ ._-]?DL|[ ._-]?RIP))\b", rf"NADA{separator}\1", normalized, count=1, flags=re.IGNORECASE)

        if not str(meta.tag or "").strip("- ") and not re.search(r"-NOGROUP$", normalized, flags=re.IGNORECASE):
            normalized = f"{normalized}-NOGROUP"

        return normalized

    async def get_name(self, meta: Meta) -> dict[str, str]:
        if meta.manual_name is not None:
            return {"name": meta.manual_name.strip()}

        name = self._normalize_upload_name(meta.name, meta)
        return {"name": add_incomplete_pack_marker(name, meta, self.tracker)}

    async def get_description(self, meta: Meta) -> None:
        desc = await DescriptionBuilder(self.tracker, self.config).general_description_generator(
            meta,
            mediainfo=False,
            nfo=False,
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

    def get_video_codec(self, meta: Meta) -> str:
        encode = (meta.video_encode or "").split()
        codec = encode[-1].replace(".", "") if encode else ""
        if codec in self.video_codec_ids:
            return codec
        return meta.video_codec if meta.video_codec in self.video_codec_ids else ""

    def get_video_format(self, meta: Meta) -> str:
        hdr = (meta.hdr or "").split()
        dv = "DV" in hdr
        if "HDR10+" in hdr:
            return "DV HDR10+" if dv else "HDR10+"
        if "HDR" in hdr:
            return "DV HDR" if dv else "HDR"
        if dv:
            return "DV"
        if "HLG" in hdr:
            return "HLG"
        if "PQ10" in hdr:
            return "PQ10"
        return "SDR"

    def get_audio_format(self, meta: Meta) -> str:
        audio = meta.audio or ""
        atmos = "Atmos" in audio
        patterns = (
            (r"\bTrueHD\b", "TrueHD Atmos" if atmos else "TrueHD"),
            (r"DTS:X", "DTS:X"),
            (r"DTS-HD MA", "DTS-HD MA Auro3D" if "Auro3D" in audio else "DTS-HD MA"),
            (r"DTS-HD HRA", "DTS-HD HRA"),
            (r"(?<!\S)DTS(?:-ES)?(?!\S)", "DTS"),
            (r"(?<!\S)(?:DD\+|DDP)(?!\S)", "DDP Atmos" if atmos else "DDP"),
            (r"(?<!\S)DD(?!\S)", "DD"),
            (r"(?<!\S)AAC(?!\S)", "AAC"),
            (r"(?<!\S)FLAC(?!\S)", "FLAC"),
            (r"(?<!\S)L?PCM(?!\S)", "LPCM"),
            (r"(?<!\S)MP3(?!\S)", "MP3"),
            (r"(?<!\S)MP2(?!\S)", "MP2"),
            (r"(?<!\S)VORBIS(?!\S)", "VORBIS"),
            (r"(?<!\S)OPUS(?!\S)", "OPUS"),
        )
        for pattern, audio_format in patterns:
            if re.search(pattern, audio, flags=re.IGNORECASE):
                return audio_format
        return ""

    def get_audio_channels(self, meta: Meta) -> str:
        # HUNO names only the base layer, so Atmos heights (7.1.4) are dropped
        return ".".join(str(meta.channels or "").split(".")[:2])

    def get_source_type(self, meta: Meta) -> str:
        source = str(meta.source or "").upper().replace(" ", "").replace("-", "")
        hybrid = " Hybrid" if meta.webdv else ""
        if meta.type in ("WEBDL", "WEBRIP") or source == "WEB":
            return f"WEB-DL{hybrid}"
        if "HDTV" in source or source == "TV":
            return "SDTV" if meta.resolution in self.sd_resolutions else "HDTV"
        if "HDDVD" in source or meta.is_disc == "HDDVD":
            return f"HD-DVD{hybrid}"
        if meta.is_disc == "DVD":
            return meta.dvd_size if meta.dvd_size in ("DVD9", "DVD5") else "DVD"
        if "DVD" in source or source in ("PAL", "NTSC"):
            return "DVD"
        if "BLURAY" in source or meta.is_disc == "BDMV":
            return f"{'UHD BluRay' if meta.uhd else 'BluRay'}{hybrid}"
        return ""

    def get_media_language(self, meta: Meta) -> str:
        if meta.silent:
            return "No Language"
        languages = [lang for lang in meta.audio_languages or [] if lang]
        if len(languages) >= 3:
            return "MULTI"
        if len(languages) == 2:
            return "DUAL"
        return languages[0] if languages else ""

    def get_edition(self, meta: Meta) -> str:
        edition = re.sub(r"[^a-z0-9+ ]", "", (meta.edition or "").lower())
        for name in self.edition_ids:
            if re.search(rf"(?<!\S){re.escape(name.lower())}(?!\S)", edition):
                return name
        return ""

    def get_release_tag(self, meta: Meta) -> str:
        repack = (meta.repack or "").strip().upper()
        if repack in self.release_tags:
            return repack
        if meta.tv_pack and meta.season_pack_incomplete:
            return "INCOMPLETE"
        if re.search(r"\bDubbed\b", meta.audio or ""):
            return "DUBBED"
        return ""

    def get_region(self, meta: Meta) -> str:
        region = (meta.region or "").strip().upper()
        if region in self.regions:
            return region
        system = str(meta.source or "").split()[0].upper() if meta.source else ""
        return system if system in ("PAL", "NTSC") else ""

    async def get_attributes(self, meta: Meta) -> dict[str, Any]:
        """Explicit attribute overrides, so HUNO does not rely on its filename auto-detection."""
        attributes: dict[str, Any] = {
            "resolution": (await self.get_resolution_id(meta))["resolution_id"],
            "video_format": self.video_format_ids[self.get_video_format(meta)],
            "release_group": str(meta.tag or "").strip().lstrip("-") or "NoGRP",
        }

        lookups = (
            ("video_codec", self.get_video_codec(meta), self.video_codec_ids),
            ("audio_format", self.get_audio_format(meta), self.audio_format_ids),
            ("audio_channels", self.get_audio_channels(meta), self.audio_channel_ids),
            ("source_type", self.get_source_type(meta), self.source_type_ids),
            ("edition", self.get_edition(meta), self.edition_ids),
        )
        for field_name, value, ids in lookups:
            if value in ids:
                attributes[field_name] = ids[value]

        if meta.type in ("WEBDL", "WEBRIP") or meta.service:
            attributes["streaming_service"] = meta.service or "NADA"

        media_language = self.get_media_language(meta)
        if media_language:
            attributes["media_language"] = media_language

        release_tag = self.get_release_tag(meta)
        if release_tag:
            attributes["release_tag"] = release_tag

        if meta.is_disc:
            region = self.get_region(meta)
            if region:
                attributes["region"] = region
        if meta.is_disc or meta.type == "REMUX":
            distributor = distributor_id(meta.distributor, self.tracker)
            if distributor:
                attributes["distributor"] = distributor

        return attributes

    async def get_payload_specs(self, meta: Meta) -> dict[str, payload_preview.Spec]:
        specs = await super().get_payload_specs(meta)
        specs["category_id"] = payload_preview.choice("Category", {"MOVIE": 1, "TV": 2}, by_label=True)
        specs["anonymous"] = payload_preview.flag("Anonymous", on=1, off=0)
        specs["internal"] = payload_preview.flag("Internal", on=1, off=None)
        specs["season_pack"] = payload_preview.flag("Season pack", on=1, off=0)
        specs["release_group"] = payload_preview.text("Release group")
        if "resolution_id" in specs:
            specs["resolution"] = specs["resolution_id"]
        for key, label, ids in (
            ("video_format", "Video format", self.video_format_ids),
            ("video_codec", "Video codec", self.video_codec_ids),
            ("audio_format", "Audio format", self.audio_format_ids),
            ("audio_channels", "Audio channels", self.audio_channel_ids),
            ("source_type", "Source type", self.source_type_ids),
            ("edition", "Edition", self.edition_ids),
        ):
            specs[key] = payload_preview.choice(label, ids, by_label=True)
        specs["region"] = payload_preview.choice("Region", self.regions)
        return specs

    async def get_data(self, meta: Meta, preview: bool = False) -> dict[str, Any]:
        if not preview:
            await self.get_description(meta)

        data: dict[str, Any] = {
            "category_id": 1 if meta.category == "MOVIE" else 2,
            "type_id": (await self.get_type_id(meta))["type_id"],
            "tmdb": meta.tmdb,
            "anonymous": int(bool(meta.anon) or self.tracker_config.get("anon", False)),
        }
        if meta.imdb_id:
            data["imdb"] = meta.imdb_id

        internal = await self.get_internal(meta)
        if internal == 1:
            data["internal"] = 1

        if meta.manual_name is not None or (meta.tv_pack and meta.season_pack_incomplete):
            data.update(await self.get_name(meta))

        data.update(await self.get_attributes(meta))

        if meta.category == "TV":
            season_int = meta.season_int
            episode_int = meta.episode_int
            tvdb = meta.tvdb_id
            mal_id = meta.mal_id

            if season_int:
                data["season_number"] = season_int
            if episode_int and not meta.tv_pack:
                data["episode_number"] = episode_int
            if tvdb:
                data["tvdb"] = tvdb
            if mal_id:
                data["mal"] = mal_id
            data["season_pack"] = int(bool(meta.tv_pack))

        return data

    async def get_files(self, meta: Meta) -> dict[str, tuple[str, bytes, str]]:
        files: dict[str, tuple[str, bytes, str]] = {}
        await self.common.create_torrent_for_upload(meta, self.tracker, self.source_flag, announce_url=self.announce_url)
        torrent_path = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/[{self.tracker}].torrent"
        async with aiofiles.open(torrent_path, "rb") as f:
            if meta.manual_name is not None:
                upload_name = meta.manual_name.strip()
            else:
                upload_name = self._normalize_upload_name(meta.clean_name, meta)
                upload_name = add_incomplete_pack_marker(upload_name, meta, self.tracker)
            files["torrent"] = (f"{upload_name}.torrent", await f.read(), "application/x-bittorrent")

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
        data = payload_preview.apply_payload_edits(meta, self.tracker, await self.get_data(meta))

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
            # 409 (duplicate) and 422 (attribute mismatch) explain the rejection in the JSON envelope
            try:
                error_json = e.response.json()
                details = error_json.get("data") or ""
                if isinstance(details, list):
                    details = "; ".join(str(detail) for detail in details)
                detail_text = f"{error_json.get('message') or ''} {details}".strip()
                if detail_text:
                    msg = f"HTTP {e.response.status_code} - {detail_text}"
            except ValueError, AttributeError:
                pass
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
