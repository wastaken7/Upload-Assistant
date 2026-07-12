# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
from typing import Any

from src.console import logger
from src.meta import Meta
from src.trackers.COMMON import COMMON
from src.trackers.UNIT3D import UNIT3D


class ACM(UNIT3D):
    tracker = "ACM"
    source_flag = "AsianCinema"
    base_url = "https://eiga.moi"
    banned_groups: list[str] = []
    id_url = f"{base_url}/api/torrents/"
    upload_url = f"{base_url}/api/torrents/upload"
    requests_url = f"{base_url}/api/requests/filter"
    search_url = f"{base_url}/api/torrents/filter"
    torrent_url = f"{base_url}/torrents/"
    supported_categories = ("TV", "MOVIE")
    tracker_urls = ['https://eiga.moi']

    def __init__(self, config: dict[str, Any]):
        super().__init__(config, tracker_name="ACM")
        self.config = config
        self.common = COMMON(config)

    async def get_additional_checks(self, meta: Meta) -> bool:
        asia = [
            'AE', 'AF', 'AM', 'AZ', 'BD', 'BH', 'BN', 'BT', 'CN', 'CY', 'GE', 'HK', 'ID', 'IL', 'IN',
            'IQ', 'IR', 'JO', 'JP', 'KG', 'KH', 'KP', 'KR', 'KW', 'KZ', 'LA', 'LB', 'LK', 'MM', 'MN',
            'MO', 'MV', 'MY', 'NP', 'OM', 'PH', 'PK', 'PS', 'QA', 'SA', 'SG', 'SY', 'TH', 'TJ', 'TL',
            'TM', 'TR', 'TW', 'UZ', 'VN', 'YE'
        ]  # fmt: off

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
        elif reverse:
            return {v: k for k, v in resolution_id.items()}
        elif resolution:
            return {"resolution_id": resolution_id.get(resolution, "6")}
        else:
            meta_resolution = meta.resolution
            resolved_id = resolution_id.get(meta_resolution, "6")
            return {"resolution_id": resolved_id}

    def get_subs_tag(self, meta: Meta) -> str:
        subs = meta.subtitle_languages
        if not subs:
            return " [No subs]"
        elif "English" in subs:
            return ""
        elif len(subs) > 1:
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

    async def get_name(self, meta: Meta) -> dict[str, str]:
        name: str = meta.name
        aka: str = meta.aka
        original_title: str = meta.original_title
        audio: str = meta.audio
        source: str = meta.source or ""
        is_disc: str = meta.is_disc
        resolution: str = meta.resolution
        if aka != "":
            # ugly fix to remove the extra space in the title
            aka = aka + " "
            name = name.replace(aka, f" / {original_title} {chr(int('202A', 16))}")
        elif aka == "":
            if meta.title != original_title:
                # name = f'{name[:name.find(year)]}/ {original_title} {chr(int("202A", 16))}{name[name.find(year):]}'
                name = name.replace(meta.title, f"{meta.title} / {original_title} {chr(int('202A', 16))}")
        if "AAC" in audio:
            name = name.replace(audio.strip().replace("  ", " "), audio.replace("AAC ", "AAC"))
        name = name.replace("DD+ ", "DD+")
        name = name.replace("UHD BluRay REMUX", "Remux")
        name = name.replace("BluRay REMUX", "Remux")
        name = name.replace("H.265", "HEVC")
        name = name.replace(" Atmos", "")
        if is_disc == "DVD":
            name = name.replace(f"{source} DVD5", f"{resolution} DVD {source}")
            name = name.replace(f"{source} DVD9", f"{resolution} DVD {source}")
            if audio == meta.channels:
                name = name.replace(f"{audio}", f"MPEG {audio}")

        name = name + self.get_subs_tag(meta)
        return {"name": name}
