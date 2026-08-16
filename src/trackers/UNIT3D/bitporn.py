# Upload Assistant © 2026 Audionut & wastaken7 — Licensed under UAPL v1.0
import re
from typing import Any, ClassVar

from src.get_desc import DescriptionBuilder
from src.meta import Meta
from src.screenshot_manifest import files as manifest_files
from src.trackers.UNIT3D import UNIT3D

Config = dict[str, Any]


class BitPorn(UNIT3D):
    """BitPorn is a UNIT3D tracker for adult video releases."""

    tracker = "BITPORN"
    display_name = "BitPorn"
    base_url = "https://bitporn.eu"
    banned_groups: tuple[str, ...] = ()
    id_url = f"{base_url}/api/torrents/"
    upload_url = f"{base_url}/api/torrents/upload"
    search_url = f"{base_url}/api/torrents/filter"
    torrent_url = f"{base_url}/torrents/"
    supported_categories = ("XXX",)
    tracker_urls = ("https://bitporn.eu",)

    category_ids: ClassVar[dict[str, str]] = {
        "Ai Generated": "54",
        "Amateur": "4",
        "Anal": "5",
        "Asian": "6",
        "BBW": "7",
        "BDSM": "8",
        "Big Ass": "9",
        "Big Tits": "10",
        "Black": "11",
        "Cartoon": "12",
        "Casting": "13",
        "Classic": "14",
        "Collection": "15",
        "Creampie": "16",
        "Deepthroat": "18",
        "Extreme": "19",
        "Fansite": "20",
        "Family": "21",
        "Feature": "22",
        "Fetish": "23",
        "Fisting": "24",
        "Gangbang": "25",
        "Game": "26",
        "Gay / Bi": "27",
        "Hair": "28",
        "Hardcore": "29",
        "HiddenCam": "30",
        "Homemade": "31",
        "Interracial": "32",
        "Lesbian": "33",
        "Magyar": "34",
        "Masturbation": "35",
        "Mature": "36",
        "Milf": "37",
        "Movie": "53",
        "Old and Young": "38",
        "Oral": "17",
        "Parody": "39",
        "Pictures": "40",
        "Pissing": "41",
        "POV": "42",
        "Pregnant": "43",
        "Public": "44",
        "Shemale": "45",
        "Softcore": "46",
        "Squirt": "47",
        "Straight": "48",
        "Teen": "49",
        "Threesome": "50",
        "VR": "51",
        "Uncategorized": "52",
    }

    _category_patterns = (
        ("Ai Generated", r"\b(?:ai generated|aigenerated)\b"),
        ("Big Ass", r"\bbig ass\b"),
        ("Big Tits", r"\bbig tits?\b"),
        ("Deepthroat", r"\bdeep ?throat\b"),
        ("Old and Young", r"\bold (?:and|n) young\b"),
        ("Gay / Bi", r"\b(?:gay|bi|bisexual)\b"),
        ("HiddenCam", r"\b(?:hidden ?cam|hiddencam)\b"),
        ("Fansite", r"\b(?:fansite|onlyfans|fansly|fanvue|manyvids|fancentro|loyalfans|justforfans|pocketstars|avnstars|unfiltrd)\b"),
        ("Amateur", r"\bamateur\b"),
        ("Anal", r"\banal\b"),
        ("Asian", r"\basian\b"),
        ("BBW", r"\bbw\b"),
        ("BDSM", r"\bbdsm\b"),
        ("Black", r"\bblack\b"),
        ("Cartoon", r"\b(?:cartoon|animated)\b"),
        ("Casting", r"\bcasting\b"),
        ("Classic", r"\bclassic\b"),
        ("Collection", r"\bcollection\b"),
        ("Creampie", r"\bcreampie\b"),
        ("Extreme", r"\bextreme\b"),
        ("Family", r"\bfamily\b"),
        ("Feature", r"\bfeature\b"),
        ("Fetish", r"\bfetish\b"),
        ("Fisting", r"\bfisting\b"),
        ("Gangbang", r"\bgangbang\b"),
        ("Game", r"\bgame\b"),
        ("Hair", r"\bhairy?\b"),
        ("Hardcore", r"\bhardcore\b"),
        ("Homemade", r"\bhomemade\b"),
        ("Interracial", r"\binterracial\b"),
        ("Lesbian", r"\blesbian\b"),
        ("Magyar", r"\bmagyar\b"),
        ("Masturbation", r"\bmasturbat(?:e|es|ed|ing|ion)\b"),
        ("Mature", r"\bmature\b"),
        ("Milf", r"\bmilf\b"),
        ("Movie", r"\bmovie\b"),
        ("Oral", r"\boral\b"),
        ("Parody", r"\bparody\b"),
        ("Pictures", r"\b(?:picture|pictures|photos?)\b"),
        ("Pissing", r"\bpiss(?:ing)?\b"),
        ("POV", r"\bpov\b"),
        ("Pregnant", r"\bpregnant\b"),
        ("Public", r"\bpublic\b"),
        ("Shemale", r"\bshemale\b"),
        ("Softcore", r"\bsoftcore\b"),
        ("Squirt", r"\bsquirt(?:ing)?\b"),
        ("Straight", r"\bstraight\b"),
        ("Teen", r"\bteen\b"),
        ("Threesome", r"\bthreesome\b"),
        ("VR", r"\b(?:vr|virtual reality)\b"),
    )

    resolution_ids: ClassVar[dict[str, str]] = {
        "OTHER": "11",
        "480i": "12",
        "480p": "12",
        "576i": "12",
        "576p": "12",
        "720p": "17",
        "1080p": "13",
        "2048p": "14",
        "2160p": "18",
        "3160p": "15",
        "4320p": "16",
    }

    def __init__(self, config: Config) -> None:
        super().__init__(config, tracker_name=self.tracker)

    async def get_category_id(self, meta: Meta, category: str | None = None, reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        if mapping_only:
            return self.category_ids
        if reverse:
            return {value: name for name, value in self.category_ids.items()}

        if category:
            return {"category_id": self.category_ids.get(category, self.category_ids["Uncategorized"])}

        basename = str(meta.basename_no_ext or "")
        normalized_basename = re.sub(r"[^a-z0-9]+", " ", basename.casefold())
        for category_name, pattern in self._category_patterns:
            if re.search(pattern, normalized_basename):
                return {"category_id": self.category_ids[category_name]}

        return {"category_id": self.category_ids["Uncategorized"]}

    async def get_type_id(self, meta: Meta, type: str | None = None, reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        _ = meta, type, reverse, mapping_only
        return {"type_id": "1"}

    async def get_resolution_id(self, meta: Meta, resolution: str | None = None, reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        if mapping_only:
            return self.resolution_ids
        if reverse:
            return {value: name for name, value in self.resolution_ids.items()}

        resolved_resolution = resolution if resolution else meta.resolution
        return {"resolution_id": self.resolution_ids.get(str(resolved_resolution), self.resolution_ids["OTHER"])}

    async def _description_image_files(self, meta: Meta) -> list[tuple[str, bytes, str]]:
        """Return local XXX contact sheets for BitPorn to host during upload."""
        images: list[tuple[str, bytes, str]] = []
        for path in manifest_files(meta.base_dir, meta.uuid, "main"):
            image = await self.get_image_file(path, max_size=10 * 1024 * 1024)
            if image:
                images.append(image)
        return images

    async def get_description(self, meta: Meta) -> dict[str, str]:
        """Use BitPorn placeholders so its API, rather than an external host, serves screenshots."""
        description = await DescriptionBuilder(self.tracker, self.config).general_description_generator(
            meta,
            audio_spectrogram=False,
            bluray=False,
            logo=False,
            mediainfo=False,
            menu_screenshots=False,
            nfo=False,
            screenshots=False,
        )
        images = await self._description_image_files(meta)
        if images:
            placeholders = "".join(f"[upimg{index}]" for index in range(1, len(images) + 1))
            description = f"{description}\n[center]{placeholders}[/center]"
        return {"description": description}

    async def get_data(self, meta: Meta) -> dict[str, str]:
        """Build only the documented BitPorn upload fields."""
        data: dict[str, str] = {}
        for getter in (
            self.get_name,
            self.get_description,
            self.get_mediainfo,
            self.get_bdinfo,
            self.get_category_id,
            self.get_type_id,
            self.get_resolution_id,
            self.get_anonymous,
            self.get_keywords,
        ):
            data.update(await getter(meta))

        for index, _ in enumerate(await self._description_image_files(meta), start=1):
            data[f"description_image_widths[{index}]"] = "450"
        return data

    async def get_additional_files(self, meta: Meta) -> dict[str, tuple[str, bytes, str]]:
        """Use BitPorn's multipart names for tracker-hosted artwork and screenshots."""
        files = await super().get_additional_files(meta)
        if cover := files.pop("torrent-cover", None):
            files["cover"] = cover
        if banner := files.pop("torrent-banner", None):
            files["banner"] = banner

        for index, image in enumerate(await self._description_image_files(meta)):
            files[f"description_images[{index}]"] = image
        return files
