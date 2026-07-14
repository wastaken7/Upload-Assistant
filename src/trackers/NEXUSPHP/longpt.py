# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import re
from typing import Any

from src.meta import Meta
from src.trackers.NEXUSPHP import NEXUSPHP

Config = dict[str, Any]


class LongPT(NEXUSPHP):
    """
    LongPT is a CHINESE Private Torrent Tracker for MOVIES / TV / GENERAL
    """

    banned_groups = ()
    display_name = "LongPT"
    base_url = "https://longpt.org"
    source_flag = "[longpt.org] LongPT"
    torrent_url = f"{base_url}/details.php?id="
    supported_categories = ("TV", "MOVIE")
    tracker_urls = ("https://longpt.org",)

    def __init__(self, config: Config) -> None:
        super().__init__(config, "LONGPT")

    def get_category(self, meta: Meta) -> int:
        animations = 405
        documentaries = 404
        movies = 401
        tv_series = 402
        tv_shows = 403

        category = meta.category.upper()
        genres = ", ".join(meta.genres).lower()
        keywords = ", ".join(meta.keywords).lower()

        if "documentary" in genres or "documentary" in keywords:
            return documentaries
        if meta.anime or "animation" in genres or "animation" in keywords:
            return animations

        if category == "MOVIE":
            return movies
        if category == "TV":
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
            if any(re.search(rf"(^|,\s*){re.escape(keyword)}(\s*,|$)", genres, re.IGNORECASE) for keyword in game_show_keywords):
                return tv_shows
            return tv_series

        return movies

    def get_type(self, meta: Meta) -> int:
        blu_ray = 1
        dvd = 6
        encode = 7
        remux = 3
        tv = 5
        uhd_master_disc = 2
        uhd_remux = 11
        web_dl = 4

        is_disc = (meta.is_disc or "").lower()
        mtype = str(meta.type).lower()
        resolution = meta.resolution.lower()

        if is_disc == "bdmv":
            if resolution == "2160p":
                return uhd_master_disc
            return blu_ray

        if "dvd" in is_disc:
            return dvd

        if mtype == "remux":
            if resolution == "2160p":
                return uhd_remux
            return remux

        if mtype in ("webdl", "webrip"):
            return web_dl

        if "tv" in mtype:
            return tv

        if mtype == "encode":
            return encode

        return encode

    def get_codec(self, meta: Meta) -> int:
        av1 = 5
        h264 = 1
        h265 = 2
        mpeg2 = 4
        other = 6
        vc1 = 3

        codec = meta.video_codec.lower()

        if "h265" in codec or "x265" in codec or "hevc" in codec:
            return h265
        if "h264" in codec or "x264" in codec or "avc" in codec:
            return h264
        if "vc1" in codec or "vc-1" in codec:
            return vc1
        if "mpeg2" in codec or "mpeg-2" in codec:
            return mpeg2
        if "av1" in codec:
            return av1

        return other

    def get_resolution(self, meta: Meta) -> int:
        resolution = meta.resolution.lower()

        if "4320" in resolution:
            return 6
        if "2160" in resolution:
            return 5
        if "1440" in resolution:
            return 1
        if "1080" in resolution:
            return 2
        if "720" in resolution:
            return 3
        if meta.sd:
            return 4

        return 7

    def get_audio_codec(self, meta: Meta) -> int:
        audio_codec = meta.audio.lower()

        if "flac" in audio_codec:
            return 1
        if "dts-hd" in audio_codec:
            return 3
        if "dts:x" in audio_codec:
            return 12
        if "dts" in audio_codec:
            return 13
        if "lpcm" in audio_codec:
            return 14
        if "dd" in audio_codec:
            return 15
        if "alac" in audio_codec:
            return 16
        if "wav" in audio_codec:
            return 17
        if "av3a" in audio_codec:
            return 18
        if "true" in audio_codec:
            return 19
        if "ape" in audio_codec:
            return 2
        if "mp3" in audio_codec:
            return 4
        if "ogg" in audio_codec:
            return 5
        if "aac" in audio_codec:
            return 6
        if "m4a" in audio_codec:
            return 8
        if "atmos" in audio_codec:
            return 9
        if "ddp" in audio_codec:
            return 10

        return 11

    def get_group_tag(self, meta: Meta) -> int:
        group_tag = {
            "-cmct": 7,
            "-hhweb": 8,
            "-longa": 1,
            "-longpt": 3,
            "-longweb": 2,
            "-rl": 6,
            "-wiki": 4,
        }

        group = meta.tag.lower() if meta.tag else ""
        return group_tag.get(group, 5)

    def get_checkboxes(self, meta: Meta) -> list[str]:
        chinese_audio = 5
        chinese_subtitle = 6
        diy = 4
        english_audio = 9
        hdr = 7
        reposting_prohibited = 1

        audio_tracks = meta.audio_languages or []
        subtitle_tracks = meta.subtitle_languages or []
        mhdr = meta.hdr

        checkboxes = []

        if meta.exclusive:
            checkboxes.append(str(reposting_prohibited))

        if "Chinese" in audio_tracks or "Mandarin" in audio_tracks:
            checkboxes.append(str(chinese_audio))

        if "English" in audio_tracks:
            checkboxes.append(str(english_audio))

        if "Chinese" in subtitle_tracks or "Mandarin" in subtitle_tracks:
            checkboxes.append(str(chinese_subtitle))

        if "HDR" in mhdr.upper():
            checkboxes.append(str(hdr))

        if meta.diy_disc:
            checkboxes.append(str(diy))

        return checkboxes

    def get_douban_url(self, meta: Meta) -> str:
        _ = meta
        return ""
