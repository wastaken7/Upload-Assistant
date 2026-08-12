# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import re
from typing import Any

from src.meta import Meta
from src.trackers.NEXUSPHP import NEXUSPHP

Config = dict[str, Any]


class PTZone(NEXUSPHP):
    """
    PTZone is a CHINESE Private Torrent Tracker for MOVIES / TV / GENERAL
    """

    banned_groups = ()
    display_name = "PTZone"
    base_url = "https://ptzone.xyz"
    source_flag = "[ptzone.xyz] PTzone"
    torrent_url = f"{base_url}/details.php?id="
    supported_categories = ("TV", "MOVIE")
    tracker_urls = ("https://ptzone.xyz",)
    allows_bloated_audio = True

    def __init__(self, config: Config) -> None:
        super().__init__(config, "PTZONE")

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
        hdtv = 5
        remux = 3
        uhd = 10
        web_dl = 4

        is_disc = (meta.is_disc or "").lower()
        mtype = str(meta.type).lower()
        resolution = meta.resolution.lower()

        if is_disc == "bdmv":
            if resolution == "2160p":
                return uhd
            return blu_ray

        if "dvd" in is_disc:
            return dvd

        if mtype == "remux":
            return remux

        if "web" in mtype:
            return web_dl

        if mtype == "hdtv":
            return hdtv

        if mtype == "encode":
            return encode

        return encode

    def get_codec(self, meta: Meta) -> int:
        h264 = 1
        h265 = 6
        mpeg2 = 3
        mpeg4 = 4
        other = 5
        vc1 = 2

        codec = meta.video_codec.lower()

        if "h265" in codec or "x265" in codec or "hevc" in codec or "265" in codec:
            return h265
        if "h264" in codec or "x264" in codec or "avc" in codec or "264" in codec:
            return h264
        if "vc1" in codec or "vc-1" in codec:
            return vc1
        if "mpeg2" in codec or "mpeg-2" in codec:
            return mpeg2
        if "mpeg4" in codec or "mpeg-4" in codec:
            return mpeg4

        return other

    def get_resolution(self, meta: Meta) -> int:
        resolution = meta.resolution.lower()

        if "4320" in resolution or "8k" in resolution:
            return 5
        if "2160" in resolution or "4k" in resolution:
            return 6
        if "1080p" in resolution:
            return 1
        if "1080i" in resolution:
            return 2
        if "1080" in resolution:
            return 1
        if "720" in resolution:
            return 3
        if meta.sd:
            return 4

        return 1

    def get_audio_codec(self, meta: Meta) -> int:
        audio_codec = meta.audio.lower()

        if "flac" in audio_codec:
            return 1
        if "ape" in audio_codec:
            return 2
        if "dts-hd ma" in audio_codec or "dtshd ma" in audio_codec:
            return 10
        if "dts-hd" in audio_codec:
            return 13
        if "dts" in audio_codec:
            return 3
        if "mp3" in audio_codec:
            return 4
        if "ogg" in audio_codec:
            return 5
        if "aac" in audio_codec:
            return 6
        if "ddp" in audio_codec or "eac3" in audio_codec or "e-ac-3" in audio_codec:
            return 12
        if "dd" in audio_codec or "ac3" in audio_codec or "ac-3" in audio_codec:
            return 11
        if "true" in audio_codec:
            return 14
        if "wav" in audio_codec:
            return 15

        return 7

    def get_group_tag(self, meta: Meta) -> int:
        group_tag = {
            "-chd": 2,
            "-hds": 1,
            "-mysilu": 3,
            "-ptzweb": 6,
            "-wiki": 4,
        }

        group = meta.tag.lower() if meta.tag else ""
        return group_tag.get(group, 5)

    def get_checkboxes(self, meta: Meta) -> list[str]:
        chinese_audio = 5
        chinese_subtitle = 6
        diy = 4
        episode = 8
        hdr = 7
        pack = 9
        reposting_prohibited = 1

        audio_tracks = meta.audio_languages or []
        subtitle_tracks = meta.subtitle_languages or []
        mhdr = meta.hdr

        checkboxes = []

        if meta.exclusive:
            checkboxes.append(str(reposting_prohibited))

        if "Chinese" in audio_tracks or "Mandarin" in audio_tracks:
            checkboxes.append(str(chinese_audio))

        if "Chinese" in subtitle_tracks or "Mandarin" in subtitle_tracks:
            checkboxes.append(str(chinese_subtitle))

        if meta.diy_disc:
            checkboxes.append(str(diy))

        if "HDR" in mhdr.upper():
            checkboxes.append(str(hdr))

        if meta.tv_pack:
            checkboxes.append(str(pack))
        elif meta.category == "TV":
            checkboxes.append(str(episode))

        return checkboxes

    def get_douban_url(self, meta: Meta) -> str:
        return super().get_douban_url(meta)

    def get_imdb_url(self, meta: Meta) -> str:
        _ = meta
        return ""

    async def get_anonymous_data(self, meta: Meta) -> dict[str, str]:
        anonymous = not (meta.anon == 0 and not self.tracker_config.get("anon", False))
        return {"anonymous": "1"} if anonymous else {}
