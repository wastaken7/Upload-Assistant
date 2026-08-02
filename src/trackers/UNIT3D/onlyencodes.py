# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import re
from typing import Any, cast

from src.languages import languages_manager
from src.meta import Meta
from src.rehostimages import ImageHostPolicy, RehostImagesManager
from src.trackers.common import Common
from src.trackers.UNIT3D import UNIT3D

Config = dict[str, Any]


class OnlyEncodes(UNIT3D):
    """
    OnlyEncodes+ is a Private Tracker for MOVIES / TV
    """

    tracker = "ONLYENCODES"
    display_name = "OnlyEncodes"
    allows_bloated_audio = True
    base_url = "https://onlyencodes.cc"
    approved_image_hosts = ("imgbox", "imgbb", "onlyimage", "ptscreens", "passtheimage")
    image_host_policy = ImageHostPolicy(
        {
            "ibb.co": "imgbb",
            "imgbox.com": "imgbox",
            "onlyimage.org": "onlyimage",
            "imagebam.com": "bam",
            "ptscreens.com": "ptscreens",
            "img.passtheima.ge": "passtheimage",
        },
        approved_image_hosts,
    )
    banned_groups = (
        "[Oj]",
        "$andra",
        "0neshot",
        "3LT0N",
        "4K4U",
        "4yEo",
        "AFG",
        "AkihitoSubs",
        "Alcaide_Kira",
        "AniHLS",
        "Anime Time",
        "AnimeRG",
        "AniURL",
        "AOC",
        "AR",
        "AROMA",
        "ASW",
        "aXXo",
        "BakedFish",
        "BiTOR",
        "bonkai",
        "BRrip",
        "C4K",
        "Cleo",
        "CM8",
        "core",
        "CrEwSaDe",
        "d3g",
        "DDR",
        "DE3PM",
        "DeadFish",
        "DeeJayAhmed",
        "DNL",
        "ELiTE",
        "EMBER",
        "eSc",
        "EVO",
        "EZTV",
        "FaNGDiNG0",
        "fenix",
        "FGT",
        "FRDS",
        "FROZEN",
        "FUM",
        "GalaxyRG",
        "GalaxyRG265",
        "GalaxyTV",
        "GERMini",
        "Grym",
        "GrymLegacy",
        "HAiKU",
        "HD2DVD",
        "HDTime",
        "Hi10",
        "HiQVE",
        "ION10",
        "iPlanet",
        "iVy",
        "JacobSwaggedUp",
        "JIVE",
        "Judas",
        "KiNGDOM",
        "LAMA",
        "Leffe",
        "LiGaS",
        "LOAD",
        "LycanHD",
        "MeGusta",
        "MezRips",
        "mHD",
        "Mr.Deadpool",
        "mSD",
        "NemDiggers",
        "neoHEVC",
        "NeXus",
        "NhaNc3",
        "nHD",
        "nikt0",
        "NOIVTC",
        "nSD",
        "pahe.in",
        "PlaySD",
        "playXD",
        "PRODJi",
        "project-gxs",
        "ProRes",
        "PSA",
        "QaS",
        "Ranger",
        "RAPiDCOWS",
        "RARBG",
        "Raze",
        "RCDiVX",
        "RDN",
        "Reaktor",
        "REsuRRecTioN",
        "RMTeam",
        "ROBOTS",
        "rubix",
        "SANTi",
        "SHUTTERSHIT",
        "SM737",
        "SpaceFish",
        "SPASM",
        "SSA",
        "TBS",
        "Telly",
        "Tenrai-Sensei",
        "TERMiNAL",
        "TGx",
        "TM",
        "topaz",
        "ToVaR",
        "TSP",
        "TSPxL",
        "UnKn0wn",
        "URANiME",
        "UTR",
        "VipapkSudios",
        "ViSION",
        "WAF",
        "Wardevil",
        "x0r",
        "xRed",
        "XS",
        "YakuboEncodes",
        "YAWNiX",
        "YAWNTiC",
        "YIFY",
        "YTS",
        "YuiSubs",
        "ZKBL",
        "ZmN",
        "ZMNT",
    )
    id_url = f"{base_url}/api/torrents/"
    upload_url = f"{base_url}/api/torrents/upload"
    search_url = f"{base_url}/api/torrents/filter"
    torrent_url = f"{base_url}/torrents/"
    supported_categories = ("TV", "MOVIE")
    tracker_urls = ("https://onlyencodes.cc",)

    def __init__(self, config: Config) -> None:
        super().__init__(config, tracker_name="ONLYENCODES")
        self.config: Config = config
        self.common = Common(config)
        self.rehost_images_manager = RehostImagesManager(config)

    async def get_additional_checks(self, meta: Meta) -> bool:
        if not self.common.check_and_confirm_adult_media_upload(meta, self.tracker):
            return False

        return not (
            meta.is_disc != "BDMV"
            and not await self.common.check_language_requirements(meta, self.tracker, languages_to_check=["english"], check_audio=True, check_subtitle=True)
        )

    async def get_name(self, meta: Meta) -> dict[str, str]:
        oe_name = meta.name
        resolution = meta.resolution
        video_encode = meta.video_encode
        name_type = str(meta.type)
        source = str(meta.source)
        audio = meta.audio
        video_codec = meta.video_codec

        imdb_info = cast(dict[str, Any], meta.imdb_info)
        imdb_name = str(imdb_info.get("title", ""))
        imdb_year = str(imdb_info.get("year", ""))
        imdb_aka = str(imdb_info.get("aka", ""))
        year = str(meta.year) if meta.year is not None else ""
        aka = meta.aka
        if imdb_name and imdb_name.strip():
            if aka:
                oe_name = oe_name.replace(f"{aka} ", "", 1)
            oe_name = oe_name.replace(f"{meta.title}", imdb_name, 1)

            if imdb_aka and imdb_aka.strip() and imdb_aka != imdb_name and not meta.no_aka:
                oe_name = oe_name.replace(f"{imdb_name}", f"{imdb_name} AKA {imdb_aka}", 1)

        if meta.category != "TV" and imdb_year and imdb_year.strip() and year and year.strip() and imdb_year != year:
            oe_name = oe_name.replace(f"{year}", imdb_year, 1)

        if name_type == "DVDRIP":
            if meta.category == "MOVIE":
                oe_name = oe_name.replace(f"{source}{video_encode}", f"{resolution}", 1)
                oe_name = oe_name.replace((audio), f"{audio}{video_encode}", 1)
            else:
                oe_name = oe_name.replace(f"{source}", f"{resolution}", 1)
                oe_name = oe_name.replace(f"{video_codec}", f"{audio} {video_codec}", 1)

        if not meta.audio_languages:
            await languages_manager.process_desc_language(meta, tracker=self.tracker)
        elif meta.audio_languages:
            audio_languages_value = meta.audio_languages
            audio_languages = cast(list[str], audio_languages_value) if isinstance(audio_languages_value, list) else []
            if audio_languages and not await languages_manager.has_english_language(audio_languages) and meta.is_disc != "BDMV":
                foreign_lang = str(audio_languages[0]).upper()
                oe_name = oe_name.replace(f"{resolution}", f"{foreign_lang} {resolution}", 1)

        uuid_value = meta.basename_no_ext
        scale = "DS4K" if "DS4K" in uuid_value.upper() else "RM4K" if "RM4K" in uuid_value.upper() else ""
        if name_type in ["ENCODE", "WEBDL", "WEBRIP"] and scale != "":
            oe_name = oe_name.replace(f"{resolution}", f"{scale}", 1)

        tag_value = meta.tag or ""
        tag_lower = tag_value.lower()
        invalid_tags = ["nogrp", "nogroup", "unknown", "-unk-"]
        if tag_value == "" or any(invalid_tag in tag_lower for invalid_tag in invalid_tags):
            for invalid_tag in invalid_tags:
                oe_name = re.sub(f"-{invalid_tag}", "", oe_name, flags=re.IGNORECASE)
            oe_name = f"{oe_name}-NOGRP"

        return {"name": oe_name}

    async def get_type_id(self, meta: Meta, type: str | None = None, reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        video_codec = meta.video_codec if meta.video_codec is not None else "N/A"
        type_mapping = {
            "DISC": "19",
            "REMUX": "20",
            "WEBDL": "21",
            "WEBRIP": "16",
            "ENCODE": "16",
            "DVDRIP": "16",
        }
        if mapping_only:
            return type_mapping
        if reverse:
            return {v: k for k, v in type_mapping.items()}

        type_value = str(type if type is not None and type != "" else meta.type).upper()
        if type_value == "DVDRIP":
            type_value = "ENCODE"

        type_id = type_mapping.get(type_value, "16")
        if type_value in {"WEBRIP", "ENCODE"}:
            if video_codec == "HEVC":
                type_id = "10"
            if video_codec == "AV1":
                type_id = "14"
            if video_codec == "AVC":
                type_id = "15"
        return {"type_id": type_id}
