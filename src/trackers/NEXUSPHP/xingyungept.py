# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import re
from typing import Any

from src.meta import Meta
from src.trackers.NEXUSPHP import NEXUSPHP

Config = dict[str, Any]


class XingyungePT(NEXUSPHP):
    """
    XingyungePT is a CHINESE Private Torrent Tracker for MOVIES / TV / GENERAL
    """

    banned_groups = ()
    display_name = "XingyungePT"
    base_url = "https://pt.xingyungept.org"
    source_flag = "[pt.xingyungept.org] 星陨阁"
    torrent_url = f"{base_url}/details.php?id="
    supported_categories = ("TV", "MOVIE")
    tracker_urls = ("https://pt.xingyungept.org",)
    allows_bloated_audio = True

    def __init__(self, config: Config) -> None:
        super().__init__(config, "XINGYUNGEPT")

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
        uhd_bluray = 2
        web_dl = 4

        is_disc = (meta.is_disc or "").lower()
        mtype = str(meta.type).lower()
        resolution = meta.resolution.lower()

        if is_disc == "bdmv":
            if resolution == "2160p":
                return uhd_bluray
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
        av1 = 5
        h264 = 1
        h265 = 2
        mpeg2 = 4
        other = 6
        vc1 = 3

        codec = meta.video_codec.lower()

        if "h265" in codec or "x265" in codec or "hevc" in codec or "265" in codec:
            return h265
        if "h264" in codec or "x264" in codec or "avc" in codec or "264" in codec:
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

        if "4320" in resolution or "8k" in resolution:
            return 5
        if "2160" in resolution or "4k" in resolution:
            return 4
        if "1080" in resolution:
            return 3
        if "720" in resolution:
            return 2
        if meta.sd or "480" in resolution:
            return 1

        return 6

    def get_audio_codec(self, meta: Meta) -> int:
        audio_codec = meta.audio.lower()

        if "flac" in audio_codec:
            return 1
        if "mp3" in audio_codec:
            return 2
        if "wav" in audio_codec:
            return 3
        if "m4a" in audio_codec:
            return 4
        if "dts:x" in audio_codec or "dtsx" in audio_codec:
            return 7
        if "dts-hd ma" in audio_codec or "dtshd ma" in audio_codec:
            return 6
        if "dts" in audio_codec:
            return 5
        if "atmos" in audio_codec and "true" in audio_codec:
            return 12
        if "true" in audio_codec:
            return 8
        if "lpcm" in audio_codec or "pcm" in audio_codec:
            return 9
        if "ddp" in audio_codec or "eac3" in audio_codec or "e-ac-3" in audio_codec:
            return 11
        if "dd" in audio_codec or "ac3" in audio_codec or "ac-3" in audio_codec:
            return 10
        if "ape" in audio_codec:
            return 13
        if "aac" in audio_codec:
            return 14
        if "alac" in audio_codec:
            return 15
        if "opus" in audio_codec:
            return 17

        return 16

    def get_group_tag(self, meta: Meta) -> int:
        group_tag = {
            "-agsvweb": 9,
            "-chd": 2,
            "-hds": 1,
            "-mysilu": 3,
            "-natureweb": 11,
            "-pure@starfallweb": 12,
            "-rain": 6,
            "-rainweb": 7,
            "-starfall": 10,
            "-starfallweb": 8,
            "-wiki": 4,
        }

        group = meta.tag.lower() if meta.tag else ""
        return group_tag.get(group, 5)

    def get_checkboxes(self, meta: Meta) -> list[str]:
        chinese_audio = 5
        chinese_subtitle = 6
        diy = 4
        dolby_vision = 8
        episode = 10
        hdr = 7
        pack = 11
        reposting_prohibited = 1

        audio_tracks = meta.audio_languages or []
        subtitle_tracks = meta.subtitle_languages or []
        mhdr = meta.hdr

        checkboxes: list[str] = []

        if meta.exclusive:
            checkboxes.append(str(reposting_prohibited))

        if "Chinese" in audio_tracks or "Mandarin" in audio_tracks:
            checkboxes.append(str(chinese_audio))

        if "Chinese" in subtitle_tracks or "Mandarin" in subtitle_tracks:
            checkboxes.append(str(chinese_subtitle))

        if meta.diy_disc:
            checkboxes.append(str(diy))

        if "DV" in mhdr.upper() or "DOLBY" in mhdr.upper():
            checkboxes.append(str(dolby_vision))

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
