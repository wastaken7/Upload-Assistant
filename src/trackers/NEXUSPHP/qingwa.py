# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import re
from typing import Any

from src.meta import Meta
from src.trackers.NEXUSPHP import NEXUSPHP


class QingWa(NEXUSPHP):
    display_name = "QingWa"
    base_url = "https://www.qingwapt.com"
    source_flag = "[www.qingwapt.com] 青蛙"
    torrent_url = f"{base_url}/details.php?id="
    tracker_urls = (base_url,)
    allows_bloated_audio = True
    search_type_parameter = "source"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config, "QINGWA")

    @staticmethod
    def _main_audio_count(meta: Meta) -> int:
        count = 0
        for track in meta.mediainfo.get("media", {}).get("track", []) or []:
            if track.get("@type") != "Audio":
                continue
            label = " ".join(str(track.get(field) or "") for field in ("Title", "title", "TrackTitle", "ServiceKind")).lower()
            service_kinds = {kind.strip().upper() for kind in str(track.get("ServiceKind") or "").split("/")}
            if "commentary" in label or "compatibility" in label or "C" in service_kinds:
                continue
            count += 1
        return count

    @staticmethod
    def _title_audio(meta: Meta) -> str:
        audio = re.sub(r"\b(?:Dual[ -]Audio|Dubbed|\d+Audios?)\b", "", meta.audio, flags=re.IGNORECASE)
        audio = re.sub(r"\b(?:DD\+|DDP|E-?AC-?3)(?=\s|$)", "DDP", audio, flags=re.IGNORECASE)
        audio = re.sub(r"\bAC-?3\b", "DD", audio, flags=re.IGNORECASE)
        objects = re.findall(r"\b(?:Atmos|Auro3D)\b", audio, flags=re.IGNORECASE)
        audio = re.sub(r"\b(?:Atmos|Auro3D)\b", "", audio, flags=re.IGNORECASE)
        audio = " ".join(audio.split())
        if meta.channels and not re.search(r"\b\d+\.\d+\b", audio):
            audio = f"{audio} {meta.channels}".strip()
        return " ".join([audio, *objects]).strip()

    async def get_name(self, meta: Meta) -> dict[str, str]:
        if meta.manual_name is not None:
            return {"name": meta.manual_name.strip()}
        if not meta.title:
            return {"name": meta.name}

        media_type = (meta.type or "").upper().replace("-", "")
        is_web = media_type in {"WEBDL", "WEBRIP"}
        year = str(meta.manual_year or meta.year or "") if not meta.no_year else ""
        season_episode = ""
        if meta.category == "TV":
            season = str(meta.season or "")
            if season.isdigit():
                season = f"S{int(season):02d}"
            episode = meta.episode or ""
            if episode.isdigit():
                episode = f"E{int(episode):02d}"
            season_episode = f"{'' if meta.no_season else season}{episode}"
            if meta.manual_date:
                season_episode = ""
                year = meta.manual_date.replace("-", "").replace(".", "")

        source = meta.source or ""
        specification = ""
        distributor = ""
        video = meta.video_encode or meta.video_codec
        if meta.is_disc == "BDMV":
            source = "Blu-ray"
            if meta.diy_disc:
                source = "Custom BluRay"
            distributor = meta.distributor
            video = meta.video_codec
        elif meta.is_disc == "DVD":
            source = f"{source} {meta.dvd_size}".strip()
            distributor = meta.distributor
            video = ""
        elif meta.is_disc == "HDDVD":
            source = "HD DVD"
            video = meta.video_codec
        elif is_web:
            source = ""
            distributor = meta.service or ""
            specification = "WEB-DL" if media_type == "WEBDL" else "WEBRip"
            video = {"AVC": "H.264", "HEVC": "H.265"}.get(video, video)
        elif media_type == "HDTV":
            distributor = meta.service or (source if source.upper() != "HDTV" else "")
            source = ""
            specification = "HDTV"
            video = {"AVC": "H264", "HEVC": "H265", "H.264": "H264", "H.265": "H265", "MPEG-2": "MPEG2"}.get(video, video)
        elif media_type == "REMUX":
            specification = "Remux"
            video = meta.video_codec
        elif media_type == "DVDRIP":
            source = "DVDRip"

        video = re.sub(r"\b(?:8|10|12)[ -]?bits?\b", "", video, flags=re.IGNORECASE).strip()
        if ("264" in video or video == "AVC") and str(meta.bit_depth) == "10" and "Hi10P" not in video:
            video = f"Hi10P {video}"
        hdr = re.sub(r"\bHDR10\b(?!\+)", "HDR", meta.hdr)
        hdr = re.sub(r"\bSDR\b", "", hdr)
        edition = re.sub(r"^Complete$", "", meta.edition, flags=re.IGNORECASE)
        hybrid = "Hybrid" if meta.webdv and "hybrid" not in edition.lower() else ""
        audio_count = self._main_audio_count(meta) if media_type == "ENCODE" else 0
        parts = [
            meta.title,
            season_episode,
            year,
            edition,
            hybrid,
            meta.repack,
            meta.resolution.lower() if meta.resolution.upper() != "OTHER" else "",
            str(meta.region or "") if meta.is_disc else "",
            distributor,
            meta.three_d,
            "UHD" if meta.uhd and not is_web else "",
            source,
            specification,
            hdr,
            video,
            self._title_audio(meta),
            f"{audio_count}Audio" if audio_count > 1 else "",
        ]
        name = " ".join(" ".join(parts).split())
        tag = meta.tag or ""
        return {"name": name + (tag if tag.startswith("-") or not tag else f"-{tag}")}

    async def get_data(self, meta: Meta) -> dict[str, Any]:
        data = await super().get_data(meta)
        localized = getattr(self, "tmdb_data", {})
        candidates = [localized.get("title"), localized.get("name"), meta.aka, meta.original_title]
        names: list[str] = []
        for candidate in candidates:
            if not candidate:
                continue
            name = re.sub(r"^AKA\s+", "", str(candidate).strip(), flags=re.IGNORECASE)
            if name and name.casefold() != meta.title.casefold() and name.casefold() not in {existing.casefold() for existing in names}:
                names.append(name)
        data["small_descr"] = " / ".join(names)
        return data

    def get_category(self, meta: Meta) -> int:
        genres = {genre.lower() for genre in meta.genres}
        keywords = {keyword.lower() for keyword in meta.keywords}
        if "documentary" in genres | keywords:
            return 404
        if meta.anime or "animation" in genres | keywords:
            return 405
        if meta.category == "TV":
            if (genres | keywords) & {"reality", "reality television", "reality tv", "talk show", "game show", "variety", "competition", "tv show"}:
                return 403
            return 402
        return 401

    def get_type(self, meta: Meta) -> int:
        if meta.is_disc == "BDMV":
            return 1 if meta.resolution == "2160p" else 8
        if "DVD" in meta.is_disc.upper():
            return 2
        media_type = (meta.type or "").upper()
        if media_type == "REMUX":
            return 9
        if "WEB" in media_type:
            return 7
        if media_type == "HDTV":
            return 4
        if media_type == "ENCODE":
            return 10
        return 6

    async def get_type_data(self, meta: Meta) -> dict[str, int]:
        # QingWa calls the medium selector "source" and has no region selector.
        return {"source_sel[4]": self.get_type(meta)}

    def get_codec(self, meta: Meta) -> int:
        codec = meta.video_codec.lower().replace("-", "").replace(".", "")
        for names, value in (
            (("av1",), 7),
            (("265", "hevc"), 6),
            (("264", "avc"), 1),
            (("vc1",), 2),
            (("mpeg2",), 4),
            (("mpeg4", "xvid", "divx"), 3),
            (("vp9",), 8),
        ):
            if any(name in codec for name in names):
                return value
        return 5

    def get_resolution(self, meta: Meta) -> int:
        resolution = meta.resolution.lower()
        resolutions = {"4320p": 6, "2160p": 7, "1440p": 8, "1080p": 1, "1080i": 2, "720p": 3}
        return resolutions.get(resolution, 4 if meta.sd else 5)

    def get_audio_codec(self, meta: Meta) -> int:
        audio = meta.audio.lower().replace("-", "").replace(" ", "")
        if "dtsx" in audio or "dts:x" in audio:
            return 9
        if "dtshdma" in audio:
            return 10
        if "dtshdhra" in audio or "dtshdhr" in audio:
            return 21
        if "dts" in audio:
            return 14
        if "truehd" in audio:
            return 11 if "atmos" in audio else 12
        for names, value in (
            (("lpcm", "pcm"), 13),
            (("dd+", "ddp", "eac3"), 16),
            (("dd", "ac3"), 15),
            (("flac",), 1),
            (("aac",), 17),
            (("ape",), 18),
            (("wav",), 19),
            (("mp3",), 4),
            (("m4a",), 8),
            (("opus",), 20),
            (("av3a",), 22),
        ):
            if any(name in audio for name in names):
                return value
        return 7

    def get_group_tag(self, meta: Meta) -> int:
        return {"-frog": 6, "-froge": 7, "-frogweb": 8, "-catedu": 10}.get((meta.tag or "").lower(), 5)

    def get_checkboxes(self, meta: Meta) -> list[str]:
        tags: list[str] = []
        audio_languages = meta.audio_languages or []
        subtitle_languages = meta.subtitle_languages or []
        if meta.exclusive:
            tags.append("1")
        if any(language in audio_languages for language in ("Chinese", "Mandarin")):
            tags.append("5")
        if "Cantonese" in audio_languages:
            tags.append("8")
        if any(language in subtitle_languages for language in ("Chinese", "Mandarin", "Cantonese")):
            tags.append("6")
        if meta.is_disc == "BDMV":
            tags.append("4" if meta.diy_disc else "11")
        if (meta.type or "").upper() == "REMUX":
            tags.append("15")
        hdr = meta.hdr.upper()
        if "DV" in hdr or "DOLBY VISION" in hdr:
            tags.append("12")
        if "HDR10+" in hdr:
            tags.append("13")
        if "HDR" in hdr:
            tags.append("7")
        return tags
