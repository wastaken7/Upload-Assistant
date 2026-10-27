# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import re
from typing import Any

from src.meta import Meta
from src.trackers.NEXUSPHP import NEXUSPHP

Config = dict[str, Any]


class ZmPT(NEXUSPHP):
    """ZmPT (织梦) is a CHINESE Private Torrent Tracker for MOVIES / TV / GENERAL."""

    display_name = "ZmPT"
    base_url = "https://zmpt.cc"
    source_flag = "[zmpt.cc] 织梦"
    torrent_url = f"{base_url}/details.php?id="
    supported_categories = ("TV", "MOVIE")
    tracker_urls = ("https://zmpt.cc",)

    def __init__(self, config: Config) -> None:
        super().__init__(config, "ZMPT")

    def get_category(self, meta: Meta) -> int:
        genres = ", ".join(meta.genres).lower()
        keywords = ", ".join(meta.keywords).lower()

        if "documentary" in genres or "documentary" in keywords:
            return 422
        if meta.anime or "animation" in genres or "animation" in keywords:
            return 417
        if meta.category.upper() == "TV":
            game_show_keywords = [
                "award show",
                "competition",
                "game show",
                "music show",
                "performance",
                "reality television",
                "reality tv",
                "reality",
                "stand-up",
                "talk show",
                "tv show",
                "variety",
            ]
            variety_terms = f"{genres}, {keywords}"
            if any(re.search(rf"(^|,\s*){re.escape(keyword)}(\s*,|$)", variety_terms, re.IGNORECASE) for keyword in game_show_keywords):
                return 403
            return 402
        return 401

    def get_type(self, meta: Meta) -> int:
        is_disc = (meta.is_disc or "").lower()
        mtype = str(meta.type).lower()

        if is_disc == "bdmv":
            return 1
        if "dvd" in is_disc:
            return 6
        if mtype == "remux":
            return 3
        if mtype == "hdtv":
            return 5
        if mtype == "webdl":
            return 10
        if mtype in ("encode", "webrip", "dvdrip"):
            return 7
        return 12

    def get_codec(self, meta: Meta) -> int:
        codec = meta.video_codec.lower()

        if "265" in codec or "hevc" in codec:
            return 6
        if "264" in codec or "avc" in codec:
            return 1
        if "vc1" in codec or "vc-1" in codec:
            return 2
        if "xvid" in codec:
            return 3
        if "mpeg" in codec:
            return 4
        return 5

    def get_resolution(self, meta: Meta) -> int:
        resolution = meta.resolution.lower()
        resolution_map = {
            "1080p": 1,
            "1080i": 1,
            "2160p": 5,
            "1440p": 6,
            "480p": 7,
            "480i": 7,
            "576p": 7,
            "576i": 7,
            "720p": 8,
            "4320p": 9,
        }
        return resolution_map.get(resolution, 7 if meta.sd else 0)

    def get_audio_codec(self, meta: Meta) -> int:
        audio_codec = meta.audio.lower()

        for name, value in (("flac", 1), ("ape", 2), ("dts", 3), ("mp3", 4), ("ogg", 5), ("aac", 6), ("alac", 9), ("wav", 10)):
            if name in audio_codec:
                return value
        if "dd" in audio_codec or "ac3" in audio_codec or "ac-3" in audio_codec:
            return 8
        return 7

    def get_group_tag(self, meta: Meta) -> int:
        group_tag = {
            "-zmpt": 6,
            "-zmweb": 7,
            "-zmmusic": 8,
            "-dyz-movie": 9,
            "-goddramas": 10,
            "-zmaudio": 11,
            "-rl": 12,
            "-rl4b": 12,
        }
        return group_tag.get(meta.tag.lower() if meta.tag else "", 5)

    def get_checkboxes(self, meta: Meta) -> list[str]:
        checkboxes: list[str] = []
        chinese_languages = ("Chinese", "Mandarin", "Cantonese")

        if meta.exclusive:
            checkboxes.append("1")
        if meta.diy_disc:
            checkboxes.append("4")
        if any(language in (meta.audio_languages or []) for language in chinese_languages):
            checkboxes.append("5")
        if any(language in (meta.subtitle_languages or []) for language in chinese_languages):
            checkboxes.append("6")
        if "HDR" in meta.hdr.upper():
            checkboxes.append("7")
        if meta.is_disc == "BDMV" and not meta.diy_disc:
            checkboxes.append("10")
        return checkboxes
