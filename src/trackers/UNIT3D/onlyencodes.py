# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
from dataclasses import replace
from typing import Any

from src.console import logger
from src.get_desc import DescriptionBuilder
from src.get_name import build_name_components
from src.meta import Meta
from src.rehostimages import ImageHostPolicy, RehostImagesManager
from src.tracker_images import get_tracker_image_collection
from src.trackers.common import Common
from src.trackers.naming import BLU_NAME_RULES, add_incomplete_pack_marker, build_video_name
from src.trackers.UNIT3D import UNIT3D

Config = dict[str, Any]
# OnlyEncodes adds the audio language after the season/episode when no English audio exists.
ONLYENCODES_NAME_RULES = replace(BLU_NAME_RULES, language_slot="before_cut")


class OnlyEncodes(UNIT3D):
    """
    OnlyEncodes+ is a Private Tracker for MOVIES / TV
    """

    tracker = "ONLYENCODES"
    display_name = "OnlyEncodes+"
    allows_bloated_audio = True
    base_url = "https://onlyencodes.cc"
    approved_image_hosts = ("imgbox", "imgbb", "onlyimage", "ptscreens", "passtheimage", "lostimg")
    image_host_policy = ImageHostPolicy(
        {
            "ibb.co": "imgbb",
            "imgbox.com": "imgbox",
            "onlyimage.org": "onlyimage",
            "imagebam.com": "bam",
            "ptscreens.com": "ptscreens",
            "img.passtheima.ge": "passtheimage",
            "lostimg.cc": "lostimg",
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

        if int(meta.screens or 0) < 3:
            logger.info(f"{self.tracker}: [bold yellow]At least 3 full-screen screenshots are required. Skipping upload.[/bold yellow]")
            return False

        return not (
            meta.is_disc != "BDMV"
            and not await self.common.check_language_requirements(meta, self.tracker, languages_to_check=["english"], check_audio=True, check_subtitle=True)
        )

    async def get_description(self, meta: Meta) -> dict[str, str]:
        screenshots = get_tracker_image_collection(meta, self.tracker, "screenshots") or []
        linked_screenshots = [image for image in screenshots if isinstance(image, dict) and image.get("web_url") and (image.get("raw_url") or image.get("img_url"))]
        if len(linked_screenshots) < 3:
            raise ValueError(f"{self.tracker}: At least 3 hosted, linked screenshots are required")

        builder = DescriptionBuilder(self.tracker, self.config)
        # OnlyEncodes requires linked medium thumbnails from the first episode or
        # movie. Keep these overrides local so other trackers retain user settings.
        builder.tracker_config = {
            **builder.tracker_config,
            "add_logo": False,
            "multiScreens": 0,
            "thumbnail_size": 350,
            "pack_thumb_size": 350,
        }
        return {
            "description": await builder.general_description_generator(
                meta,
                logo=False,
                mediainfo=False,
                nfo=False,
                approved_image_hosts=list(self.approved_image_hosts),
            )
        }

    async def get_name(self, meta: Meta) -> dict[str, str]:
        # Keep the TMDB title and year from the generated name for OnlyEncodes.
        components = build_name_components(meta)
        scale_source = meta.basename_no_ext.upper()
        scale = "DS4K" if "DS4K" in scale_source else "RM4K" if "RM4K" in scale_source else ""
        if scale and components.type in ("ENCODE", "WEBDL", "WEBRIP") and components.resolution:
            components = replace(components, resolution=f"{components.resolution} {scale}")

        tag_lower = components.tag.lower()
        if not components.tag or any(invalid_tag in tag_lower for invalid_tag in ("nogrp", "nogroup", "unknown", "-unk-")):
            components = replace(components, tag="-NOGRP")

        oe_name = await build_video_name(meta, ONLYENCODES_NAME_RULES, self.tracker, components) or meta.name
        return {"name": add_incomplete_pack_marker(oe_name, meta, self.tracker)}

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
