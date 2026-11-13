# Upload Assistant © 2026 Audionut & wastaken7 — Licensed under UAPL v1.0
"""Kufirc: private Luminance tracker for adult content.

Upload rules: https://kufirc.com/articles/view/upload
"""

import re
from typing import ClassVar

from src.meta import Meta
from src.rehostimages import ImageHostPolicy
from src.trackers.LUMINANCE import GAME_EXTENSIONS, Luminance
from src.xxx_lookup import is_scene_style_name

MAX_FILES = 10000

# Genre categories chosen from words in the release name, most specific first.
# Provider tags are not used here: almost every scene is tagged with several acts.
_NAME_CATEGORIES: tuple[tuple[str, str], ...] = (
    ("BBW", r"\b(?:bbw|plumpers?|chubby)\b"),
    ("BDSM", r"\b(?:bdsm|bondage)\b"),
    ("Squirt", r"\bsquirt(?:s|ing)?\b"),
    ("Piss", r"\b(?:piss|pissing|golden shower)\b"),
    ("Pregnant / Preggo", r"\b(?:pregnant|preggo)\b"),
    ("Old + Young", r"\bold (?:and|n|&) young\b"),
    ("Mature", r"\b(?:mature|granny|grandma)\b"),
    ("Milf", r"\bmilfs?\b"),
    ("Teen", r"\bteens?\b"),
    ("Orgia / Gang Bang", r"\b(?:gang ?bang|orgy|orgia)\b"),
    ("Creampie", r"\bcreampies?\b"),
    ("Anal", r"\banal\b"),
    ("Pov", r"\bpov\b"),
    ("Big Tits", r"\bbig (?:tits|boobs|breasts)\b"),
    ("Busty", r"\bbusty\b"),
    ("Big Ass", r"\bbig (?:ass|butt|booty)\b"),
    ("Natural Tits", r"\bnatural (?:tits|boobs)\b"),
    ("Latina", r"\blatinas?\b"),
    ("Black", r"\bebony\b"),
    ("Amateur", r"\bamateurs?\b"),
    ("Homemade", r"\bhomemade\b"),
    ("Masturbation", r"\bmasturbat(?:e|es|ed|ing|ion)\b"),
    ("Oral", r"\b(?:blowjob|oral)\b"),
    ("Parody", r"\bparody\b"),
    ("Softcore", r"\bsoftcore\b"),
    ("Fetish", r"\bfetish\b"),
    ("Cumshot", r"\bcumshots?\b"),
)


class Kufirc(Luminance):
    """Kufirc is a private Hungarian adult tracker running Luminance."""

    tracker = "KUFIRC"
    display_name = "Kufirc"
    source_flag = "Kufirc"
    base_url = "https://kufirc.com"
    tracker_urls = ("kufirc.com",)
    # "When uploading new torrents on Kufirc.com, use only: https://luminapix.eu/"
    approved_image_hosts = ("luminapix",)
    image_host_policy = ImageHostPolicy({"luminapix.eu": "luminapix"}, approved_image_hosts)
    category_ids: ClassVar[dict[str, str]] = {
        "Amateur": "30",
        "Anal": "29",
        "Asian": "27",
        "BBW": "26",
        "BDSM": "44",
        "Big Ass": "25",
        "Big Tits": "24",
        "Black": "34",
        "Busty": "35",
        "Classic": "23",
        "Creampie": "33",
        "Cumshot": "22",
        "Feature": "36",
        "Fetish": "21",
        "Film/Cam/Hun": "31",
        "Film/Xvid/hun": "46",
        "Foreign": "37",
        "Gay / Bi": "19",
        "Hardcore": "18",
        "HD porn": "32",
        "Hentai / 3D": "28",
        "Homemade": "17",
        "Image": "11",
        "Interracial": "38",
        "Latina": "48",
        "Lesbian": "16",
        "Magazines": "56",
        "Magyar": "6",
        "Masturbation": "15",
        "Mature": "14",
        "Megapack": "13",
        "Milf": "55",
        "Natural Tits": "49",
        "Old + Young": "39",
        "Oral": "12",
        "Orgia / Gang Bang": "20",
        "Other": "42",
        "Parody": "50",
        "Paysite": "41",
        "Piss": "40",
        "Porn Music Videos": "43",
        "Pov": "54",
        "Pregnant / Preggo": "45",
        "Scat/Puke": "57",
        "Shemale / TS": "10",
        "Siterip": "51",
        "Softcore": "52",
        "Squirt": "53",
        "Straight": "9",
        "Teen": "8",
        "VR": "47",
        "XXX Games": "7",
    }
    default_category = "Hardcore"
    has_mediainfo_field = False
    min_tags = 1

    def category_name(self, meta: Meta) -> str:
        """Pick the Kufirc category: format first, then who is in the release, then the name."""
        if any(path.suffix.casefold() in GAME_EXTENSIONS for path in self._files(meta)):
            return "XXX Games"
        if self.is_picset(meta):
            return "Image"
        if self.is_siterip(meta):
            return "Siterip"
        if self.is_pack(meta):
            return "Megapack"
        if self.is_vr(meta):
            return "VR"
        if self.has_word(meta, r"\b(?:gay|bisexual|twinks?)\b"):
            return "Gay / Bi"
        if self.has_word(meta, r"\b(?:trans|transgender|transsexual|shemale|tgirl|ladyboy)\b"):
            return "Shemale / TS"
        if self.has_word(meta, r"\b(?:hentai|cartoon|animated|3d animation)\b"):
            return "Hentai / 3D"
        if self.is_jav(meta) or self.has_word(meta, r"\b(?:asian|japanese|chinese|korean|thai|filipina)\b"):
            return "Asian"
        if self.has_word(meta, r"\b(?:magyar|hungarian|hungary)\b"):
            return "Magyar"
        if self.has_word(meta, r"\blesbians?\b") and not self.has_word(meta, r"\b(?:blowjob|cumshot|facial|handjob|creampie|ffm|mmf)\b"):
            return "Lesbian"
        if self.has_word(meta, r"\b(?:interracial|bbc|blacked|blackedraw)\b"):
            return "Interracial"
        if self.is_movie(meta):
            release = self._release(meta)
            year = (release.year if release else None) or (meta.year if isinstance(meta.year, int) else None)
            return "Classic" if year and 1900 < year < 1990 else "Feature"
        name = re.sub(r"[^a-z0-9&]+", " ", str(meta.basename_no_ext or "").casefold())
        return next((category for category, pattern in _NAME_CATEGORIES if re.search(pattern, name)), self.default_category)

    async def get_name(self, meta: Meta) -> str:
        """The scene release name when there is one, otherwise the shared title format."""
        if meta.manual_name is None:
            basename = str(meta.basename_no_ext or "")
            scene_name = str(meta.scene_name or "") or (basename if is_scene_style_name(basename) else "")
            if scene_name:
                return scene_name
        return await super().get_name(meta)

    def get_category_id(self, meta: Meta) -> str:
        return self.category_ids[self.category_name(meta)]

    def luminapix_ready(self) -> bool:
        default_config = self.config.get("DEFAULT", {})
        return bool(self.configured_image_hosts()) and bool(str(default_config.get("luminapix_api", "")).strip())

    def rule_warnings(self, meta: Meta) -> list[str]:
        warnings = super().rule_warnings(meta)
        if len(self._files(meta)) > MAX_FILES:
            warnings.append(f"Torrents with more than {MAX_FILES:,} files are not allowed.")
        if not self.luminapix_ready():
            warnings.append(
                "Kufirc only accepts images hosted on luminapix.eu. Add 'luminapix' to an img_host_N setting and set 'luminapix_api' (Settings > API on luminapix.eu)."
            )
        return warnings
