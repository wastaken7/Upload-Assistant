# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import re
from typing import Any

from src.console import logger
from src.languages import languages_manager
from src.meta import Meta
from src.trackers.COMMON import COMMON
from src.trackers.UNIT3D import UNIT3D

Config = dict[str, Any]


class ItaTorrents(UNIT3D):
    """
    ItaTorrents is an ITALIAN Private tracker for MOVIES / TV / GENERAL
    """

    tracker = "ItaTorrents"
    base_url = "https://itatorrents.xyz"
    banned_groups = ()
    id_url = f"{base_url}/api/torrents/"
    upload_url = f"{base_url}/api/torrents/upload"
    requests_url = f"{base_url}/api/requests/filter"
    search_url = f"{base_url}/api/torrents/filter"
    torrent_url = f"{base_url}/torrents/"
    supported_categories = ("TV", "MOVIE")
    tracker_urls = ("https://itatorrents.xyz",)

    def __init__(self, config: Config) -> None:
        super().__init__(config, tracker_name="ItaTorrents")
        self.config: Config = config
        self.common = COMMON(config)

    async def get_type_name(self, meta: Meta) -> str | None:
        type_name: str | None = None

        uuid_string = meta.basename_no_ext
        if uuid_string:
            lower_uuid = uuid_string.lower()

            if "dlmux" in lower_uuid:
                type_name = "DLMux"
            elif "bdmux" in lower_uuid:
                type_name = "BDMux"
            elif "webmux" in lower_uuid:
                type_name = "WEBMux"
            elif "dvdmux" in lower_uuid:
                type_name = "DVDMux"
            elif "bdrip" in lower_uuid:
                type_name = "BDRip"

        if type_name is None:
            type_value = meta.type
            type_name = str(type_value) if type_value else None

        return type_name

    async def get_type_id(self, meta: Meta, type: str | None = None, reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        type_id_map = {
            "DISC": "1",
            "REMUX": "2",
            "WEBDL": "4",
            "WEBRIP": "5",
            "HDTV": "6",
            "ENCODE": "3",
            "DLMux": "27",
            "BDMux": "29",
            "WEBMux": "26",
            "DVDMux": "39",
            "BDRip": "25",
            "DVDRIP": "24",
            "Cinema-MD": "14",
        }
        if mapping_only:
            return type_id_map
        if reverse:
            return {v: k for k, v in type_id_map.items()}
        if type is not None:
            return {"type_id": type_id_map.get(type, "0")}

        resolved_type = await self.get_type_name(meta)
        type_id = type_id_map.get(resolved_type or "", "0")

        return {"type_id": type_id}

    async def get_name(self, meta: Meta) -> dict[str, str]:
        type_name = await self.get_type_name(meta) or ""
        title = meta.title
        year = str(meta.year) if meta.year is not None else ""
        if meta.manual_year or 0 > 0:
            year = str(meta.manual_year)
        resolution = meta.resolution
        if resolution == "OTHER":
            resolution = ""
        audio = meta.audio
        season = str(meta.season or "")
        episode = meta.episode or ""
        repack = meta.repack
        three_d = meta.three_d
        tag = meta.tag or ""
        source = str(meta.source)
        hdr = meta.hdr
        video_codec = meta.video_codec
        region = str(meta.region)
        if meta.is_disc == "BDMV":
            video_codec = meta.video_codec
            region = str(meta.region)
        elif meta.is_disc == "DVD":
            region = str(meta.region)
        edition = meta.edition
        if "hybrid" in edition.upper():
            edition = edition.replace("Hybrid", "").strip()

        if meta.category == "TV":
            year = str(meta.year) if (meta.year is not None and meta.search_year != "") else ""
            if meta.manual_date:
                season = ""
                episode = ""
        if meta.no_season is True:
            season = ""
        if meta.no_year is True:
            year = ""

        dubs = await self.get_dubs(meta)

        """
        From https://itatorrents.xyz/wikis/20

        Struttura Titolo per: Full Disc, Remux
        Name Year S##E## Cut REPACK Resolution Edition Region 3D SOURCE TYPE Hi10P HDR VCodec Dub ACodec Channels Object-Tag

        Struttura Titolo per: Encode, WEB-DL, WEBRip, HDTV, DLMux, BDMux, WEBMux, DVDMux, BDRip, DVDRip
        Name Year S##E## Cut REPACK Resolution Edition 3D SOURCE TYPE Dub ACodec Channels Object Hi10P HDR VCodec-Tag
        """

        if type_name == "DISC" or type_name == "REMUX":
            itt_name = f"{title} {year} {season}{episode} {repack} {resolution} {edition} {region} {three_d} {source} {'REMUX' if type_name == 'REMUX' else ''} {hdr} {video_codec} {dubs} {audio}"

        else:
            type_name = type_name.replace("WEBDL", "WEB-DL").replace("WEBRIP", "WEBRip").replace("DVDRIP", "DVDRip").replace("ENCODE", "BluRay")
            itt_name = f"{title} {year} {season}{episode} {repack} {resolution} {edition} {three_d} {type_name} {dubs} {audio} {hdr} {video_codec}"

        try:
            itt_name = " ".join(itt_name.split())
        except Exception:
            logger.info("[bold red]Unable to generate name. Please re-run and correct any of the following args if needed.")
            logger.info(f"--category [yellow]{meta.category}")
            logger.info(f"--type [yellow]{meta.type}")
            logger.info(f"--source [yellow]{meta.source}")
            logger.info("[bold green]If you specified type, try also specifying source")

            exit()
        name_notag = itt_name
        itt_name = name_notag + tag
        itt_name = itt_name.replace("Dubbed", "").replace("Dual-Audio", "")

        return {"name": re.sub(r"\s{2,}", " ", itt_name)}

    async def get_dubs(self, meta: Meta) -> str:
        if not meta.language_checked:
            await languages_manager.process_desc_language(meta, tracker=self.tracker)
        dubs = ""
        audio_languages_value = meta.audio_languages
        audio_languages: set[str] = set()
        if isinstance(audio_languages_value, list):
            audio_languages_list = audio_languages_value
            audio_languages = {str(lang) for lang in audio_languages_list}
        if audio_languages:
            dubs = " ".join(lang[:3].upper() for lang in audio_languages)
        return dubs

    async def get_additional_checks(self, meta: Meta) -> bool:
        # From rules:
        # "Non sono ammessi film e serie tv che non comprendono il doppiaggio in italiano."
        # Translates to "Films and TV series that do not include Italian dubbing are not permitted."
        italian_languages = ["italian", "italiano"]
        if not await self.common.check_language_requirements(meta, self.tracker, languages_to_check=italian_languages, check_audio=True):
            logger.info("Upload Rules: https://itatorrents.xyz/wikis/5")
            return False
        return True
