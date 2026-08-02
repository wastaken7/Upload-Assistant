# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import contextlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, cast

import aiofiles
import cli_ui

from src.cleanup import cleanup_manager
from src.console import logger
from src.exportmi import mi_resolution
from src.meta import Meta


class VideoManager:
    async def get_uhd(self, type: str, guess: Any, resolution: str, path: str) -> str:
        guess_dict = cast(dict[str, Any], guess)
        source = str(guess_dict.get("Source", ""))
        other = str(guess_dict.get("Other", ""))
        uhd = ""
        if (source == "Blu-ray" and other == "Ultra HD") or source == "Ultra HD Blu-ray" or "UHD" in path:
            uhd = "UHD"
        elif type in ("DISC", "REMUX", "ENCODE", "WEBRIP"):
            uhd = ""

        if type in ("DISC", "REMUX", "ENCODE") and resolution == "2160p":
            uhd = "UHD"

        return uhd

    async def get_hdr(self, mi: Any, bdinfo: Any | None) -> str:
        hdr = ""
        dv = ""
        if bdinfo is not None:  # Disks
            bdinfo_dict = cast(dict[str, Any], bdinfo)
            for track in bdinfo_dict.get("video", []):
                hdr_mi = track.get("hdr_dv", "")
                if "HDR10+" in hdr_mi:
                    hdr = "HDR10+"
                elif "HDR10" in hdr_mi and hdr != "HDR10+":
                    hdr = "HDR"
                if "Dolby Vision" in hdr_mi:
                    dv = "DV"
        else:
            mi_dict = cast(dict[str, Any], mi)
            video_track = mi_dict["media"]["track"][1]
            with contextlib.suppress(Exception):
                hdr_mi = video_track["colour_primaries"]
                if hdr_mi in ("BT.2020", "REC.2020"):
                    hdr = ""
                    hdr_fields = [video_track.get("HDR_Format_Compatibility", ""), video_track.get("HDR_Format_String", ""), video_track.get("HDR_Format", "")]
                    hdr_format_string = next((v for v in hdr_fields if isinstance(v, str) and v.strip()), "")
                    if "HDR10+" in hdr_format_string:
                        hdr = "HDR10+"
                    elif "HDR10" in hdr_format_string or "SMPTE ST 2094 App 4" in hdr_format_string:
                        hdr = "HDR"
                    if hdr_format_string and "HLG" in hdr_format_string:
                        hdr = f"{hdr} HLG"
                    if hdr_format_string == "" and "PQ" in (video_track.get("transfer_characteristics"), video_track.get("transfer_characteristics_Original", None)):
                        hdr = "PQ10"
                    transfer_characteristics = video_track.get("transfer_characteristics_Original") or ""
                    if "HLG" in transfer_characteristics:
                        hdr = "HLG"
                    if hdr != "HLG" and "BT.2020 (10-bit)" in transfer_characteristics:
                        hdr = "WCG"

            with contextlib.suppress(Exception):
                if "Dolby Vision" in video_track.get("HDR_Format", "") or "Dolby Vision" in video_track.get("HDR_Format_String", ""):
                    dv = "DV"

        return f"{dv} {hdr}".strip()

    async def get_video_codec(self, bdinfo: Any) -> str:
        codecs = {"MPEG-2 Video": "MPEG-2", "MPEG-4 AVC Video": "AVC", "MPEG-H HEVC Video": "HEVC", "VC-1 Video": "VC-1"}
        bdinfo_dict = cast(dict[str, Any], bdinfo)
        return codecs.get(bdinfo_dict["video"][0]["codec"], "")

    async def get_video_encode(self, mi: Any, type: str, bdinfo: Any) -> tuple[str, str, bool, str]:
        video_encode = ""
        codec = ""
        bit_depth = "0"
        has_encode_settings = False
        try:
            mi_dict = cast(dict[str, Any], mi)
            format = mi_dict["media"]["track"][1]["Format"]
            format_profile = mi_dict["media"]["track"][1].get("Format_Profile", format)
            if mi_dict["media"]["track"][1].get("Encoded_Library_Settings", None):
                has_encode_settings = True
            bit_depth = mi_dict["media"]["track"][1].get("BitDepth", "0")
            encoded_library_name = mi_dict["media"]["track"][1].get("Encoded_Library_Name", None)
        except Exception:
            bdinfo_dict = cast(dict[str, Any], bdinfo)
            format = bdinfo_dict["video"][0]["codec"]
            format_profile = bdinfo_dict["video"][0]["profile"]
            encoded_library_name = None
        if format in ("AV1", "VP9", "VC-1"):
            codec = format
        elif type in ("ENCODE", "WEBRIP", "DVDRIP"):  # ENCODE or WEBRIP or DVDRIP
            if format == "AVC":
                codec = "x264"
            elif format == "HEVC":
                codec = "x265"
            elif format == "MPEG-4 Visual" and encoded_library_name:
                if "xvid" in encoded_library_name.lower():
                    codec = "XviD"
                elif "divx" in encoded_library_name.lower():
                    codec = "DivX"
        elif type in ("WEBDL", "HDTV"):  # WEB-DL
            if format == "AVC":
                codec = "H.264"
            elif format == "HEVC":
                codec = "H.265"

            if type == "HDTV" and has_encode_settings is True:
                codec = codec.replace("H.", "x")
        profile = "Hi10P" if format_profile == "High 10" else ""
        video_encode = f"{profile} {codec}"
        video_codec = format
        if video_codec == "MPEG Video":
            mi_dict = cast(dict[str, Any], mi)
            video_codec = f"MPEG-{mi_dict['media']['track'][1].get('Format_Version')}"
        return video_encode, video_codec, has_encode_settings, bit_depth

    async def get_video(self, videoloc: str, mode: str, sorted_filelist: bool = False) -> tuple[str, list[str]]:
        filelist: list[str] = []
        videoloc = str(Path(videoloc).resolve())
        logger.debug(f"[blue]Video location: [yellow]{videoloc}[/yellow][/blue]")
        video = ""
        if Path(videoloc).is_dir():
            logger.debug("[blue]Scanning directory for video files...[/blue]")
            try:
                entries = [p.name for p in Path(videoloc).iterdir() if p.is_file()]
            except Exception:
                entries = []

            video_exts = {".mkv", ".mp4", ".ts"}
            for file in entries:
                fname_lower = file.lower()
                ext = Path(file).suffix.lower()
                if ext not in video_exts:
                    continue

                # Skip obvious sample files unless explicitly marked with !sample
                if "sample" in fname_lower and "!sample" not in fname_lower:
                    continue

                filelist.append(str(Path(Path(videoloc) / file).resolve()))

            filelist = sorted(filelist)
            if filelist:
                logger.debug(f"[blue]Found {len(filelist)} video files in directory.[/blue]")
            if len(filelist) > 1:
                for f in list(filelist):
                    if "sample" in Path(f).name.lower() and "!sample" not in Path(f).name.lower():
                        logger.info("[green]Filelist:[/green]")
                        for tf in filelist:
                            logger.info(f"[cyan]{tf}")
                        logger.info(f"[bold red]Possible sample file detected in filelist!: [yellow]{f}")
                        try:
                            if cli_ui.ask_yes_no("Do you want to remove it?", default=True):
                                filelist.remove(f)
                        except EOFError:
                            logger.info("\n[red]Exiting on user request (Ctrl+C)[/red]")
                            await cleanup_manager.cleanup()
                            cleanup_manager.reset_terminal()
                            sys.exit(1)
            for file in filelist:
                if any(tag in file for tag in ["{tmdb-", "{imdb-", "{tvdb-"]):
                    logger.info(f"[bold red]This looks like some *arr renamed file which is not allowed: [yellow]{file}")
                    try:
                        if cli_ui.ask_yes_no("Do you want to upload with this file?", default=False):
                            pass
                        else:
                            logger.info("[red]Exiting on user request[/red]")
                            await cleanup_manager.cleanup()
                            cleanup_manager.reset_terminal()
                            sys.exit(1)
                    except EOFError:
                        logger.info("\n[red]Exiting on user request (Ctrl+C)[/red]")
                        await cleanup_manager.cleanup()
                        cleanup_manager.reset_terminal()
                        sys.exit(1)
            try:
                video = sorted(filelist, key=os.path.getsize, reverse=True)[0] if sorted_filelist else sorted(filelist)[0]
            except IndexError:
                logger.info("[bold red]No Video files found")
                if mode == "cli":
                    raise SystemExit(1) from None
                return "", []
        else:
            video = videoloc
            filelist.append(videoloc)
            if any(tag in videoloc for tag in ["{tmdb-", "{imdb-", "{tvdb-"]):
                logger.info(f"[bold red]This looks like some *arr renamed file which is not allowed: [yellow]{videoloc}")
                try:
                    if cli_ui.ask_yes_no("Do you want to upload with this file?", default=False):
                        pass
                    else:
                        logger.info("[red]Exiting on user request[/red]")
                        await cleanup_manager.cleanup()
                        cleanup_manager.reset_terminal()
                        sys.exit(1)
                except EOFError:
                    logger.info("\n[red]Exiting on user request (Ctrl+C)[/red]")
                    await cleanup_manager.cleanup()
                    cleanup_manager.reset_terminal()
                    sys.exit(1)
        filelist = sorted(filelist, key=os.path.getsize, reverse=True) if sorted_filelist else sorted(filelist)
        return video, filelist

    async def get_resolution(self, guess: Any, folder_id: str, base_dir: str, meta: Meta) -> tuple[str, bool]:
        hfr = False
        mi: dict[str, Any] = {}
        dvd_mi_text = ""
        if meta.is_disc == "DVD":
            meta_discs = meta.discs
            if meta_discs and isinstance(meta_discs, list) and isinstance(meta_discs[0], dict):
                disc = cast(dict[str, Any], meta_discs[0])
                disc_mi = disc.get("ifo_mi_json", {})
                if isinstance(disc_mi, dict):
                    mi = disc_mi
                elif isinstance(disc_mi, str):
                    try:
                        loaded = json.loads(disc_mi)
                        if isinstance(loaded, dict):
                            mi = loaded
                    except Exception:
                        mi = {}
                dvd_mi_text = str(disc.get("vob_mi", "") or disc.get("ifo_mi", ""))
        else:
            async with aiofiles.open(f"{base_dir}{'/' + 'tmp' + '/'}{folder_id}/MediaInfo.json", encoding="utf-8") as f:
                mi = cast(dict[str, Any], json.loads(await f.read()))

        tracks = mi.get("media", {}).get("track", []) if isinstance(mi, dict) else []
        video_track = tracks[1] if isinstance(tracks, list) and len(tracks) > 1 and isinstance(tracks[1], dict) else {}

        try:
            width = int(float(video_track.get("Width", 0)))
            height = int(float(video_track.get("Height", 0)))
        except Exception:
            width = 0
            height = 0

        if (width == 0 or height == 0) and dvd_mi_text:
            width_match = re.search(r"Width\s*:\s*(\d+)", dvd_mi_text, re.IGNORECASE)
            height_match = re.search(r"Height\s*:\s*(\d+)", dvd_mi_text, re.IGNORECASE)
            if width_match and height_match:
                try:
                    width = int(width_match.group(1))
                    height = int(height_match.group(1))
                except Exception:
                    width = 0
                    height = 0

        framerate = video_track.get("FrameRate")
        if not framerate or framerate == "0":
            framerate = video_track.get("FrameRate_Original")
        if not framerate or framerate == "0":
            framerate = video_track.get("FrameRate_Num")
        if (not framerate or framerate == "0") and dvd_mi_text:
            frame_match = re.search(r"Frame rate\s*:\s*([\d.]+)", dvd_mi_text, re.IGNORECASE)
            if frame_match:
                framerate = frame_match.group(1)
        if framerate:
            try:
                if int(float(framerate)) > 30:
                    hfr = True
            except Exception:
                hfr = False
        else:
            framerate = "24.000"

        scan = str(video_track.get("ScanType", ""))
        if not scan and dvd_mi_text:
            scan_match = re.search(r"Scan type\s*:\s*([^\r\n]+)", dvd_mi_text, re.IGNORECASE)
            if scan_match:
                scan = scan_match.group(1).strip()
        if scan == "Progressive":
            scan = "p"
        elif scan == "Interlaced":
            scan = "i"
        else:
            match = re.search(r"\b(1080i|576i|480i)\b", folder_id, re.IGNORECASE)
            scan = "i" if match else "p"
        width_list = [3840, 2560, 1920, 1280, 1024, 854, 720, 15360, 7680, 0]
        height_list = [2160, 1440, 1080, 720, 576, 540, 480, 8640, 4320, 0]
        width = self.closest(width_list, width)
        height = self.closest(height_list, height)
        res = f"{width}x{height}{scan}"
        resolution = await mi_resolution(res, guess, width, scan)
        return resolution, hfr

    def closest(self, lst: list[int], k: int) -> int:
        # Get closest, but not over
        lst = sorted(lst)
        mi_input = k
        res = 0
        for each in lst:
            if mi_input > each:
                pass
            else:
                res = each
                break
        return res

    async def get_type(self, video: str, _scene: bool, is_disc: str, meta: Meta) -> str:
        if meta.manual_type:
            type = meta.manual_type
        else:
            filename = Path(video).name.lower()
            if "remux" in filename:
                type = "REMUX"
            elif any(word in filename for word in [" web ", ".web.", "web-dl", "webdl"]):
                type = "WEBDL"
            elif "webrip" in filename:
                type = "WEBRIP"
            # elif scene == True:
            # type = "ENCODE"
            elif "hdtv" in filename:
                type = "HDTV"
            elif is_disc:
                type = "DISC"
            elif "dvdrip" in filename:
                type = "DVDRIP"
                # exit()
            else:
                type = "ENCODE"
        return type

    async def is_3d(self, bdinfo: Any | None) -> str:
        if bdinfo is not None:
            if bdinfo["video"][0]["3d"] != "":
                return "3D"
            return ""
        return ""

    async def is_sd(self, resolution: str) -> int:
        return 1 if resolution in ("480i", "480p", "576i", "576p", "540p") else 0

    async def get_video_duration(self, meta: Meta) -> int | None:
        if meta.category in ("BOOK", "GAME"):
            return None
        if meta.is_disc != "BDMV" and meta.mediainfo.get("media", {}).get("track"):
            general_track = next((track for track in meta.mediainfo["media"]["track"] if track.get("@type") == "General"), None)

            if general_track and general_track.get("Duration"):
                try:
                    media_duration_seconds = float(general_track["Duration"])
                    return int(media_duration_seconds // 60)
                except ValueError:
                    logger.debug(f"[red]Invalid duration value: {general_track['Duration']}[/red]")
                    return None
            else:
                logger.debug("[red]No valid duration found in MediaInfo General track[/red]")
                return None
        else:
            length = meta.bdinfo.get("length", "")
            if length:
                try:
                    hours, minutes, _seconds = length.split(":")
                    return int(hours) * 60 + int(minutes)
                except ValueError:
                    logger.debug(f"[red]Invalid duration value: {length}[/red]")
                    return None
            else:
                logger.debug("[red]No valid duration found in BDInfo[/red]")
                return None

    async def get_container(self, meta: Meta) -> str:
        if meta.is_disc == "BDMV":
            return "m2ts"
        if meta.is_disc == "HDDVD":
            return "evo"
        if meta.is_disc == "DVD":
            return "vob"
        file_list = meta.filelist

        if not file_list:
            logger.info("[red]No files found to determine container[/red]")
            return ""

        try:
            largest_file_path = max(file_list, key=os.path.getsize)
        except (OSError, ValueError) as e:
            logger.error(f"[red]Error getting container for file: {e}[/red]")
            return ""

        extension = Path(str(largest_file_path)).suffix
        return extension.lstrip(".").lower() if extension else ""


video_manager = VideoManager()
