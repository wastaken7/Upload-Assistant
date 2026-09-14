# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
from typing import Any

from src.console import logger
from src.meta import Meta
from src.release_name import NameContext, NameRule, NameSelector, TrackerNameProfile, template
from src.trackers.common import Common
from src.trackers.UNIT3D import UNIT3D


def asian_cinema_transform(name: str, context: NameContext) -> str:
    meta = context.meta
    aka = context.values.get("alt_title", "")
    original_title = str(getattr(meta, "original_title", ""))
    title = context.values.get("title", "")
    marker = chr(0x202A)
    if aka:
        name = name.replace(f"{aka} ", f" / {original_title} {marker}")
    elif title != original_title:
        name = name.replace(title, f"{title} / {original_title} {marker}")
    audio = context.values.get("audio", "")
    if "AAC" in audio:
        name = name.replace(audio.strip().replace("  ", " "), audio.replace("AAC ", "AAC"))
    for old, new in (("DD+ ", "DD+"), ("UHD BluRay REMUX", "Remux"), ("BluRay REMUX", "Remux"), ("H.265", "HEVC"), (" Atmos", "")):
        name = name.replace(old, new)
    if context.values.get("is_disc", "") == "DVD":
        source = context.values.get("source", "")
        resolution = context.values.get("resolution", "")
        name = name.replace(f"{source} DVD5", f"{resolution} DVD {source}")
        name = name.replace(f"{source} DVD9", f"{resolution} DVD {source}")
        if audio == str(getattr(meta, "channels", "")):
            name = name.replace(audio, f"MPEG {audio}")
    return name + context.values.get("suffix", "")


class AsianCinema(UNIT3D):
    """
    AsianCinema is a Private Tracker for ASIAN MOVIES / TV / MUSIC
    """

    tracker = "ASIANCINEMA"
    name_profile = TrackerNameProfile(
        rules=(NameRule(NameSelector(), template("base_name")),),
        transforms=(asian_cinema_transform,),
    )

    async def get_name_overrides(self, context: NameContext) -> dict[str, str]:
        return {"suffix": self.get_subs_tag(context.meta)}

    display_name = "AsianCinema"
    allows_bloated_audio = True
    source_flag = "AsianCinema"
    base_url = "https://eiga.moi"
    banned_groups: tuple[str, ...] = ()
    id_url = f"{base_url}/api/torrents/"
    upload_url = f"{base_url}/api/torrents/upload"
    requests_url = f"{base_url}/api/requests/filter"
    search_url = f"{base_url}/api/torrents/filter"
    torrent_url = f"{base_url}/torrents/"
    supported_categories = ("TV", "MOVIE")
    tracker_urls = ("https://eiga.moi",)

    def __init__(self, config: dict[str, Any]):
        super().__init__(config, tracker_name="ASIANCINEMA")
        self.config = config
        self.common = Common(config)

    async def get_additional_checks(self, meta: Meta) -> bool:
        asia = [
            "AE",
            "AF",
            "AM",
            "AZ",
            "BD",
            "BH",
            "BN",
            "BT",
            "CN",
            "CY",
            "GE",
            "HK",
            "ID",
            "IL",
            "IN",
            "IQ",
            "IR",
            "JO",
            "JP",
            "KG",
            "KH",
            "KP",
            "KR",
            "KW",
            "KZ",
            "LA",
            "LB",
            "LK",
            "MM",
            "MN",
            "MO",
            "MV",
            "MY",
            "NP",
            "OM",
            "PH",
            "PK",
            "PS",
            "QA",
            "SA",
            "SG",
            "SY",
            "TH",
            "TJ",
            "TL",
            "TM",
            "TR",
            "TW",
            "UZ",
            "VN",
            "YE",
        ]

        origin_country = meta.origin_country
        if origin_country and any(country not in asia for country in origin_country):
            logger.info(f"{self.tracker}: Origin country is not Asian, skipping upload...")
            return False

        return True

    async def get_resolution_id(self, meta: Meta, resolution: str = "", reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        resolution_id = {
            "2160p": "1",
            "1080p": "2",
            "1080i": "2",
            "720p": "3",
            "576p": "4",
            "576i": "4",
            "480p": "5",
            "480i": "5",
        }
        if mapping_only:
            return resolution_id
        if reverse:
            return {v: k for k, v in resolution_id.items()}
        if resolution:
            return {"resolution_id": resolution_id.get(resolution, "6")}
        meta_resolution = meta.resolution
        resolved_id = resolution_id.get(meta_resolution, "6")
        return {"resolution_id": resolved_id}

    def get_subs_tag(self, meta: Meta) -> str:
        subs = meta.subtitle_languages
        if not subs:
            return " [No subs]"
        if "English" in subs:
            return ""
        if len(subs) > 1:
            return " [No Eng subs]"
        return f" [{subs[0][:3]} subs only]"

    async def get_keywords(self, meta: Meta) -> dict[str, str]:
        keywords_list = [k.strip() for k in meta.keywords if k.strip()]

        return {"keywords": ", ".join(keywords_list[:10])}

    async def get_region_id(self, meta: Meta) -> dict[str, str]:
        region_map = {
            "KOR": "1",
            "JPN": "3",
            "CHN": "2",
            "TWN": "4",
            "SGP": "5",
            "PHI": "6",
            "THA": "7",
            "VIE": "8",
            "MAS": "9",
            "IDN": "10",
            "CAM": "11",
            "LAO": "12",
            "HKG": "13",
            "USA": "14",
            "GBR": "15",
            "ESP": "16",
            "GER": "17",
            "FRA": "18",
            "EUR": "19",
            "MEX": "20",
            "AUS": "21",
            "IND": "22",
            "RUS": "23",
            "AUT": "24",
            "NLD": "25",
            "POL": "26",
        }
        region = meta.region

        return {"region_id": region_map.get(region, "")}
