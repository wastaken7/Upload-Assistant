# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
from typing import Any, cast

from src.languages import languages_manager
from src.meta import Meta
from src.rehostimages import ImageHostPolicy, RehostImagesManager
from src.release_name import NameContext, NameRule, NameSelector, TrackerNameProfile, template
from src.trackers.common import Common
from src.trackers.naming import only_encodes_name
from src.trackers.UNIT3D import UNIT3D

Config = dict[str, Any]


class OnlyEncodes(UNIT3D):
    """
    OnlyEncodes+ is a Private Tracker for MOVIES / TV
    """

    tracker = "ONLYENCODES"
    name_profile = TrackerNameProfile(
        rules=(NameRule(NameSelector(), template("base_name")),),
        transforms=(only_encodes_name,),
    )

    async def get_name_overrides(self, context: NameContext) -> dict[str, str]:
        meta = context.meta
        if not meta.language_checked:
            await languages_manager.process_desc_language(meta, tracker=self.tracker)
        languages = cast(list[str], meta.audio_languages) if isinstance(meta.audio_languages, list) else []
        if languages and not await languages_manager.has_english_language(languages):
            return {"foreign_language": str(languages[0]).upper()}
        return {}

    display_name = "OnlyEncodes+"
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
