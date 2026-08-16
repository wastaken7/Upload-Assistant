# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import re
from typing import Any

import aiofiles

from src.console import logger
from src.get_desc import DescriptionBuilder
from src.meta import Meta
from src.trackers.UNIT3D import UNIT3D

Config = dict[str, Any]


class ULCX(UNIT3D):
    """
    upload.cx (ULCX) is a Private Torrent Tracker for MOVIES / TV
    """

    tracker = "ULCX"
    display_name = "ULCX"
    reject_english_original_bloat = True
    base_url = "https://upload.cx"
    banned_groups = (
        "4K4U",
        "Alcaide_Kira",
        "AROMA",
        "d3g",
        "EMBER",
        "FGT",
        "FnP",
        "FRDS",
        "Grym",
        "HDT",
        "Hi10",
        "iAHD",
        "INFINITY",
        "ION10",
        "iVy",
        "Judas",
        "LAMA",
        "MeGusta",
        "NAHOM",
        "Niblets",
        "nikt0",
        "OFT",
        "PHOCiS",
        "PiRaTeS",
        "QxR",
        "R&H",
        "RARBG",
        "seedpool",
        "Sicario",
        "SM737",
        "SPDVD",
        "SPx",
        "SWTYBLZ",
        "TAoE",
        "TGx",
        "Tigole",
        "TSP",
        "TSPxL",
        "VXT",
        "Vyndros",
        "Will1869",
        "x0r",
        "YIFY",
    )
    id_url = f"{base_url}/api/torrents/"
    upload_url = f"{base_url}/api/torrents/upload"
    requests_url = f"{base_url}/api/requests/filter"
    search_url = f"{base_url}/api/torrents/filter"
    torrent_url = f"{base_url}/torrents/"
    supported_categories = ("TV", "MOVIE")
    tracker_urls = ("upload.cx",)

    def __init__(self, config: Config) -> None:
        super().__init__(config, tracker_name="ULCX")
        self.config = config

    async def get_additional_checks(self, meta: Meta) -> bool:
        keywords = [k.lower() for k in (meta.keywords or [])]
        genres = [g.lower() for g in (meta.genres if isinstance(meta.genres, list) else [])]
        forbidden_keywords = ("concert", "live performance", "music video", "musical")
        if any(any(kw in item for item in keywords + genres) for kw in forbidden_keywords):
            logger.info(f"{self.tracker}: [bold red]Concerts, live performances, and music videos are forbidden.[/bold red]")
            return False

        if meta.adult_media or meta.tmdb_adult_media:
            logger.info(f"{self.tracker}: [bold red]Adult / pornographic content is forbidden.[/bold red]")
            return False

        if meta.pre_release:
            logger.info(f"{self.tracker}: [bold red]Camera recordings and pre-release content are forbidden.[/bold red]")
            return False

        # Section 3.1.6 & 4.1.2.1: Disc Structure Checks
        if meta.is_disc == "BDMV" and meta.discs_missing_certificate:
            logger.info(f"{self.tracker}: [bold red]Disc source(s) missing BD certificate, skipping upload.[/bold red]")
            return False

        if meta.is_disc == "DVD" and meta.filelist:
            has_video_ts = any("VIDEO_TS" in str(f).upper() for f in meta.filelist)
            if not has_video_ts:
                logger.info(f"{self.tracker}: [bold red]DVD full-disc must contain a VIDEO_TS folder.[/bold red]")
                return False

        # Section 3.1.7: Container Format Check (.mkv except HDTV .ts)
        if not meta.is_disc and meta.container:
            container = meta.container.lower()
            if meta.type == "HDTV":
                if container not in ("mkv", "ts"):
                    logger.info(f"{self.tracker}: [bold red]HDTV uploads must be .mkv or .ts.[/bold red]")
                    return False
            elif container != "mkv":
                logger.info(f"{self.tracker}: [bold red]All non-disc files must be .mkv (found '.{container}').[/bold red]")
                return False

        # Existing checks & custom group checks
        if meta.type == "ENCODE" and meta.tag and meta.tag[1:].lower() in ("edge2020", "nubz", "ralphy"):
            logger.info(f"{self.tracker}: [bold red]Encodes from {meta.tag} are not allowed.[/bold red]")
            return False

        if meta.type and "dvd" in meta.type.lower() and "rip" in meta.type.lower():
            if not meta.unattended:
                logger.info(f"{self.tracker}: [bold red]DVDRIPs are not allowed.[/bold red]")
            return False

        # Section 4.3.1.1: Encodes min resolution 720p
        if meta.type == "ENCODE":
            height = meta.video_height or 0
            if height > 0 and height < 720:
                logger.info(f"{self.tracker}: [bold red]Encodes must be at least 720p resolution. Standard definition encodes are forbidden.[/bold red]")
                return False

        # Section 4.3.1.6 & 4.3.1.7: Codec Restrictions for Encodes
        if meta.type == "ENCODE":
            is_animation = meta.anime or "animation" in keywords or "animation" in genres
            v_codec = (meta.video_codec or "").upper()
            if v_codec == "HEVC":
                if not is_animation and not meta.uhd and meta.resolution != "2160p" and (meta.video_height or 0) < 2160:
                    logger.info(f"{self.tracker}: [bold red]x265 (HEVC) for live-action encodes is permitted ONLY if source is UHD (2160p).[/bold red]")
                    return False
            elif v_codec == "AV1" and not is_animation:
                logger.info(f"{self.tracker}: [bold red]AV1 codec is permitted ONLY for animated content. Live-action AV1 encodes are forbidden.[/bold red]")
                return False

        # Section 4.2.1, 4.3.1.5, 6.3, 6.6, 6.8, 6.9, 6.12: Audio & Subtitle Mediainfo Checks
        if meta.mediainfo:
            media_tracks = meta.mediainfo.get("media", {}).get("track", [])
            if isinstance(media_tracks, list):
                audio_tracks = [t for t in media_tracks if t.get("@type") == "Audio"]
                sub_tracks = [t for t in media_tracks if t.get("@type") in ("Text", "Subtitle")]

                # Section 6.8: No LPCM on non-disc
                if not meta.is_disc:
                    for a in audio_tracks:
                        fmt = str(a.get("Format", "")).upper()
                        if fmt in ("PCM", "LPCM"):
                            logger.info(f"{self.tracker}: [bold red]LPCM audio tracks are not allowed on non-disc uploads.[/bold red]")
                            return False

                # Helper to get channel count
                def get_channels(t: dict[str, Any]) -> int:
                    c = t.get("Channels_Original") or t.get("Channels") or t.get("Channel(s)") or 0
                    match = re.search(r"\d+", str(c))
                    return int(match.group(0)) if match else 0

                # Helper to determine if audio format is lossless
                def is_lossless_audio(fmt: str, profile: str) -> bool:
                    return fmt in ("PCM", "LPCM", "TRUEHD", "FLAC") or (fmt.startswith("DTS") and "MA" in profile)

                # Section 6.9: FLAC mono/stereo only on non-disc
                if not meta.is_disc:
                    for a in audio_tracks:
                        fmt = str(a.get("Format", "")).upper()
                        if fmt == "FLAC" and get_channels(a) > 2:
                            logger.info(f"{self.tracker}: [bold red]FLAC audio is allowed ONLY for Mono or Stereo (1 or 2 channels) content.[/bold red]")
                            return False

                # Section 4.2.1: Remux Audio Rules
                if meta.type == "REMUX":
                    for a in audio_tracks:
                        fmt = str(a.get("Format", "")).upper()
                        profile = str(a.get("Format_Profile", "")).upper()
                        ch = get_channels(a)
                        is_lossless = is_lossless_audio(fmt, profile)

                        # 4.2.1.1: Lossless stereo must be FLAC 2.0
                        if is_lossless and ch == 2 and fmt != "FLAC":
                            logger.info(f"{self.tracker}: [bold red]Remux lossless stereo track ({fmt}) must be converted to FLAC 2.0.[/bold red]")
                            return False

                        # 4.2.1.2: Lossless mono must be FLAC 1.0 or DTS-HD MA 1.0
                        if is_lossless and ch == 1 and fmt in ("PCM", "LPCM", "TRUEHD"):
                            logger.info(f"{self.tracker}: [bold red]Remux lossless mono track ({fmt}) must be converted to FLAC 1.0 or DTS-HD MA 1.0.[/bold red]")
                            return False

                        # 4.2.1.3: Multi-channel lossless (>2ch) must be DTS-HD MA or TrueHD + core
                        if is_lossless and ch > 2 and fmt in ("FLAC", "PCM", "LPCM"):
                            logger.info(f"{self.tracker}: [bold red]Remux multi-channel lossless track cannot be {fmt} (must be DTS-HD MA or TrueHD).[/bold red]")
                            return False

                # Section 4.3.1.5: No multi-channel lossless audio on <= 1080p encodes
                if meta.type == "ENCODE":
                    res = (meta.resolution or "").lower()
                    height = meta.video_height or 0
                    if res in ("720p", "1080p", "1080i") or (height > 0 and height <= 1080):
                        for a in audio_tracks:
                            fmt = str(a.get("Format", "")).upper()
                            profile = str(a.get("Format_Profile", "")).upper()
                            ch = get_channels(a)
                            is_lossless = is_lossless_audio(fmt, profile)
                            if is_lossless and ch > 2:
                                logger.info(f"{self.tracker}: [bold red]Lossless multi-channel audio is not permitted on 1080p or lower encodes.[/bold red]")
                                return False

                # Section 6.3: TrueHD compatibility track check
                if not meta.is_disc:
                    has_truehd = any(str(a.get("Format", "")).upper() == "TRUEHD" for a in audio_tracks)
                    if has_truehd:
                        has_ac3 = any(str(a.get("Format", "")).upper() in ("AC-3", "AC3") for a in audio_tracks)
                        if not has_ac3:
                            logger.info(f"{self.tracker}: [bold red]TrueHD audio tracks must include an AC3 compatibility track.[/bold red]")
                            return False

                # Section 6.12: Default subtitles on English content.
                # This SHOULD become a MUST for personal releases.
                if meta.personalrelease and not meta.is_disc:
                    orig_lang = (meta.original_language or meta.language or "").lower()
                    if orig_lang in ("en", "eng", "english"):
                        for s in sub_tracks:
                            is_default = str(s.get("Default", "")).lower() == "yes"
                            if is_default:
                                logger.info(f"{self.tracker}: [bold red]Subtitles should not be marked default on English content.[/bold red]")
                                return False

        if not meta.is_disc and not await self.common.check_language_requirements(meta, self.tracker, languages_to_check=["english"], check_audio=True, check_subtitle=True):
            return False

        if not meta.valid_mi_settings:
            logger.info(f"{self.tracker}: [bold red]No encoding settings in mediainfo, skipping upload.[/bold red]")
            return False

        if meta.personalrelease:
            if meta.has_multiple_default_audio_tracks:
                logger.info(f"{self.tracker}: [bold red]Multiple default audio tracks detected, skipping upload.[/bold red]")
                return False

            if meta.has_multiple_default_subtitle_tracks:
                logger.info(f"{self.tracker}: [bold red]Multiple default subtitle tracks detected, skipping upload.[/bold red]")
                return False

        # Section 3.4.1: Hybrid Remux note
        if meta.type == "REMUX" and ("hybrid" in (meta.edition or "").lower() or "hybrid" in (meta.name or "").lower() or meta.webdv):
            logger.info(f"{self.tracker}: [yellow]WEB DV/HDR10+ Hybrid Remuxes require a grade check as per rule 3.4.1.[/yellow]")

        return True

    async def get_additional_data(self, meta: Meta) -> dict[str, Any]:
        return {
            "mod_queue_opt_in": await self.get_flag(meta, "modq"),
        }

    async def get_description(self, meta: Meta) -> dict[str, str]:
        desc = await DescriptionBuilder(self.tracker, self.config).general_description_generator(
            meta,
            mediainfo=False,
            nfo=False,
        )

        if meta.adult_media:
            pattern = r"(\[center\](?:(?!\[/center\]).)*\[/center\])"

            def wrap_in_spoiler(match: re.Match[str]) -> str:
                center_block = match.group(1)
                if "[img" not in center_block.lower():
                    return center_block
                return f"[center][spoiler=Screenshots]{center_block}[/spoiler][/center]"

            desc = re.sub(pattern, wrap_in_spoiler, desc, flags=re.DOTALL)
            async with aiofiles.open(f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/[{self.tracker}]DESCRIPTION.txt", "w", encoding="utf-8") as f:
                await f.write(desc)

        return {"description": desc}

    async def get_name(self, meta: Meta) -> dict[str, str]:
        ulcx_name = meta.name
        imdb_name = meta.imdb_info.get("title", "")
        imdb_year = str(meta.imdb_info.get("year", ""))
        imdb_aka = meta.imdb_info.get("aka", "")
        year = str(meta.year) if meta.year is not None else ""
        aka = meta.aka
        if imdb_name and imdb_name.strip():
            if aka:
                ulcx_name = ulcx_name.replace(f"{aka} ", "", 1)
            ulcx_name = ulcx_name.replace(f"{meta.title}", imdb_name, 1)
            if imdb_aka and imdb_aka.strip() and imdb_aka != imdb_name and not meta.no_aka and not meta.anime:
                ulcx_name = ulcx_name.replace(f"{imdb_name}", f"{imdb_name} AKA {imdb_aka}", 1)
        if "Hybrid" in ulcx_name and meta.type == "WEBDL":
            ulcx_name = ulcx_name.replace("Hybrid ", "", 1)
        if meta.category != "TV" and imdb_year and imdb_year.strip() and year and year.strip() and imdb_year != year:
            ulcx_name = ulcx_name.replace(f"{year}", imdb_year, 1)

        if meta.type == "WEBDL" and ("hybrid" in meta.edition.lower() or meta.webdv):
            ulcx_name = ulcx_name.replace("Hybrid ", "", 1)

        return {"name": ulcx_name}
