# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import asyncio
import json
import os
import platform
import subprocess
from pathlib import Path
from typing import Any, cast

import aiofiles

from src.binaries import configured_binary
from src.console import logger
from src.exceptions import NoAudioMediaError
from src.mediainfo import MediaInfo
from src.meta import Meta


def validate_file_path(file_path: str) -> str:
    if not file_path:
        raise ValueError("File path cannot be empty")

    # Convert to Path object for safer handling
    try:
        path = Path(file_path).resolve()
    except (OSError, ValueError) as e:
        raise ValueError(f"Invalid file path: {e}") from e

    # Check if path exists
    if not path.exists():
        raise ValueError(f"File does not exist: {path}")

    # Ensure it's a file (not a directory, unless specifically allowed)
    # Allow directories for DVD/Blu-ray structures
    if not path.is_file() and not path.is_dir():
        raise ValueError(f"Path is neither a file nor directory: {path}")

    # Convert back to string
    return str(path)


def find_dvd_mediainfo(base_dir: str | Path) -> dict[str, Any] | None:
    """Return the MediaInfo components installed for DVD processing."""
    if configured := configured_binary("dvd_mediainfo_path"):
        return {"cli": Path(configured), "lib": None, "lib_dir": None}
    system = platform.system().lower()
    binary_root = Path(base_dir) / "bin" / "MI"

    if system == "windows":
        cli_path = binary_root / "windows" / "dvd" / "MediaInfo.exe"
        if cli_path.exists():
            logger.debug(f"[blue]Windows MediaInfo CLI: {cli_path} (found)[/blue]")
            return {
                "cli": cli_path,
                "lib": None,  # Windows uses CLI only
                "lib_dir": None,
            }
        logger.debug(f"[yellow]Windows MediaInfo CLI: {cli_path} (not found)[/yellow]")
        return None

    if system == "linux":
        lib_dir = binary_root / "linux" / "dvd"

        mediainfo_lib = Path(lib_dir) / "libmediainfo.so.0"
        mediainfo_cli = Path(lib_dir) / "mediainfo"
        cli_available = Path(mediainfo_cli).exists()
        lib_available = Path(mediainfo_lib).exists()

        logger.debug(f"[blue]MediaInfo CLI binary: {mediainfo_cli} ({'found' if cli_available else 'not found'})[/blue]")
        logger.debug(f"[blue]MediaInfo library: {mediainfo_lib} ({'found' if lib_available else 'not found'})[/blue]")

        if lib_available:
            # Set library directory for LD_LIBRARY_PATH
            lib_dir_str = str(lib_dir)
            current_ld_path = os.environ.get("LD_LIBRARY_PATH", "")
            current_paths = current_ld_path.split(os.pathsep) if current_ld_path else []
            if lib_dir_str not in current_paths:
                if current_ld_path:
                    os.environ["LD_LIBRARY_PATH"] = f"{lib_dir_str}{os.pathsep}{current_ld_path}"
                else:
                    os.environ["LD_LIBRARY_PATH"] = lib_dir_str
                logger.debug(f"[blue]Updated LD_LIBRARY_PATH to include: {lib_dir_str}[/blue]")

        return {"cli": mediainfo_cli if cli_available else None, "lib": mediainfo_lib if lib_available else None, "lib_dir": lib_dir}
    return None


async def mi_resolution(
    res: str,
    guess: dict[str, Any],
    width: str | int,
    scan: str,
) -> str:
    res_map = {
        "3840x2160p": "2160p",
        "2160p": "2160p",
        "2560x1440p": "1440p",
        "1440p": "1440p",
        "1920x1080p": "1080p",
        "1080p": "1080p",
        "1920x1080i": "1080i",
        "1080i": "1080i",
        "1280x720p": "720p",
        "720p": "720p",
        "1280x540p": "720p",
        "1280x576p": "720p",
        "1024x576p": "576p",
        "576p": "576p",
        "1024x576i": "576i",
        "576i": "576i",
        "960x540p": "540p",
        "540p": "540p",
        "960x540i": "540i",
        "540i": "540i",
        "854x480p": "480p",
        "480p": "480p",
        "854x480i": "480i",
        "480i": "480i",
        "720x576p": "576p",
        "720x576i": "576i",
        "720x480p": "480p",
        "720x480i": "480i",
        "15360x8640p": "8640p",
        "8640p": "8640p",
        "7680x4320p": "4320p",
        "4320p": "4320p",
        "OTHER": "OTHER",
    }
    resolution = res_map.get(res)
    if resolution is None:
        width_map = {
            "3840p": "2160p",
            "2560p": "1550p",
            "1920p": "1080p",
            "1920i": "1080i",
            "1280p": "720p",
            "1024p": "576p",
            "1024i": "576i",
            "960p": "540p",
            "960i": "540i",
            "854p": "480p",
            "854i": "480i",
            "720p": "576p",
            "720i": "576i",
            "15360p": "4320p",
            "OTHERp": "OTHER",
        }
        try:
            resolution = guess["screen_size"]
            # Check if the resolution from guess exists in our map
            if resolution not in res_map:
                # If not in the map, use width-based mapping
                resolution = width_map.get(f"{width}{scan}", "OTHER")
        except Exception:
            # If we can't get from guess, use width-based mapping
            resolution = width_map.get(f"{width}{scan}", "OTHER")

    # Final check to ensure we have a valid resolution
    if resolution not in res_map:
        resolution = "OTHER"

    return resolution


async def export_info(
    video: str,
    isdir: bool,
    folder_id: str,
    base_dir: str,
    is_dvd: bool = False,
) -> dict[str, Any]:
    def filter_mediainfo(data: dict[str, Any]) -> dict[str, Any]:
        media = data.get("media")
        if not isinstance(media, dict):
            return {
                "creatingLibrary": data.get("creatingLibrary"),
                "media": {"@ref": "", "track": []},
            }

        media_dict = cast(dict[str, Any], media)
        raw_tracks = media_dict.get("track", [])
        tracks: list[dict[str, Any]] = cast(list[dict[str, Any]], raw_tracks) if isinstance(raw_tracks, list) else []

        media_tracks: list[dict[str, Any]] = []
        media_section: dict[str, Any] = {
            "@ref": media_dict.get("@ref", ""),
            "track": media_tracks,
        }
        filtered: dict[str, Any] = {
            "creatingLibrary": data.get("creatingLibrary"),
            "media": media_section,
        }

        for track in tracks:
            track_type = track.get("@type")
            if track_type == "General":
                general_track = {
                    "@type": track_type,
                    "UniqueID": track.get("UniqueID", {}),
                    "VideoCount": track.get("VideoCount", {}),
                    "AudioCount": track.get("AudioCount", {}),
                    "TextCount": track.get("TextCount", {}),
                    "MenuCount": track.get("MenuCount", {}),
                    "FileExtension": track.get("FileExtension", {}),
                    "Format": track.get("Format", {}),
                    "Format_Version": track.get("Format_Version", {}),
                    "FileSize": track.get("FileSize", {}),
                    "Duration": track.get("Duration", {}),
                    "OverallBitRate": track.get("OverallBitRate", {}),
                    "FrameRate": track.get("FrameRate", {}),
                    "FrameCount": track.get("FrameCount", {}),
                    "StreamSize": track.get("StreamSize", {}),
                    "IsStreamable": track.get("IsStreamable", {}),
                    "File_Created_Date": track.get("File_Created_Date", {}),
                    "File_Created_Date_Local": track.get("File_Created_Date_Local", {}),
                    "File_Modified_Date": track.get("File_Modified_Date", {}),
                    "File_Modified_Date_Local": track.get("File_Modified_Date_Local", {}),
                    "Encoded_Application": track.get("Encoded_Application", {}),
                    "Encoded_Library": track.get("Encoded_Library", {}),
                    "extra": track.get("extra", {}),
                }
                # Preserve standard audio / book tags if present
                for tag in [
                    "Album",
                    "Album_Performer",
                    "Track_name",
                    "Title",
                    "Performer",
                    "Composer",
                    "Publisher",
                    "Genre",
                    "Recorded_Date",
                    "ISBN",
                    "Comment",
                    "Description",
                    "album",
                    "album_performer",
                    "track_name",
                    "title",
                    "performer",
                    "composer",
                    "publisher",
                    "genre",
                    "recorded_date",
                    "isbn",
                    "comment",
                    "description",
                ]:
                    if tag in track:
                        general_track[tag] = track[tag]
                media_tracks.append(general_track)
            elif track_type == "Video":
                media_tracks.append(
                    {
                        "@type": track_type,
                        "StreamOrder": track.get("StreamOrder", {}),
                        "ID": track.get("ID", {}),
                        "UniqueID": track.get("UniqueID", {}),
                        "Format": track.get("Format", {}),
                        "Format_Profile": track.get("Format_Profile", {}),
                        "Format_Version": track.get("Format_Version", {}),
                        "Format_Level": track.get("Format_Level", {}),
                        "Format_Tier": track.get("Format_Tier", {}),
                        "HDR_Format": track.get("HDR_Format", {}),
                        "HDR_Format_Version": track.get("HDR_Format_Version", {}),
                        "HDR_Format_String": track.get("HDR_Format_String", {}),
                        "HDR_Format_Profile": track.get("HDR_Format_Profile", {}),
                        "HDR_Format_Level": track.get("HDR_Format_Level", {}),
                        "HDR_Format_Settings": track.get("HDR_Format_Settings", {}),
                        "HDR_Format_Compression": track.get("HDR_Format_Compression", {}),
                        "HDR_Format_Compatibility": track.get("HDR_Format_Compatibility", {}),
                        "CodecID": track.get("CodecID", {}),
                        "CodecID_Hint": track.get("CodecID_Hint", {}),
                        "Duration": track.get("Duration", {}),
                        "BitRate": track.get("BitRate", {}),
                        "Width": track.get("Width", {}),
                        "Height": track.get("Height", {}),
                        "Stored_Height": track.get("Stored_Height", {}),
                        "Sampled_Width": track.get("Sampled_Width", {}),
                        "Sampled_Height": track.get("Sampled_Height", {}),
                        "PixelAspectRatio": track.get("PixelAspectRatio", {}),
                        "DisplayAspectRatio": track.get("DisplayAspectRatio", {}),
                        "FrameRate_Mode": track.get("FrameRate_Mode", {}),
                        "FrameRate": track.get("FrameRate", {}),
                        "FrameRate_Original": track.get("FrameRate_Original", {}),
                        "FrameRate_Num": track.get("FrameRate_Num", {}),
                        "FrameRate_Den": track.get("FrameRate_Den", {}),
                        "FrameCount": track.get("FrameCount", {}),
                        "Standard": track.get("Standard", {}),
                        "ColorSpace": track.get("ColorSpace", {}),
                        "ChromaSubsampling": track.get("ChromaSubsampling", {}),
                        "ChromaSubsampling_Position": track.get("ChromaSubsampling_Position", {}),
                        "BitDepth": track.get("BitDepth", {}),
                        "ScanType": track.get("ScanType", {}),
                        "ScanOrder": track.get("ScanOrder", {}),
                        "Delay": track.get("Delay", {}),
                        "Delay_Source": track.get("Delay_Source", {}),
                        "StreamSize": track.get("StreamSize", {}),
                        "Language": track.get("Language", {}),
                        "Default": track.get("Default", {}),
                        "Forced": track.get("Forced", {}),
                        "colour_description_present": track.get("colour_description_present", {}),
                        "colour_description_present_Source": track.get("colour_description_present_Source", {}),
                        "colour_range": track.get("colour_range", {}),
                        "colour_range_Source": track.get("colour_range_Source", {}),
                        "colour_primaries": track.get("colour_primaries", {}),
                        "colour_primaries_Source": track.get("colour_primaries_Source", {}),
                        "transfer_characteristics": track.get("transfer_characteristics", {}),
                        "transfer_characteristics_Source": track.get("transfer_characteristics_Source", {}),
                        "transfer_characteristics_Original": track.get("transfer_characteristics_Original", {}),
                        "matrix_coefficients": track.get("matrix_coefficients", {}),
                        "matrix_coefficients_Source": track.get("matrix_coefficients_Source", {}),
                        "MasteringDisplay_ColorPrimaries": track.get("MasteringDisplay_ColorPrimaries", {}),
                        "MasteringDisplay_ColorPrimaries_Source": track.get("MasteringDisplay_ColorPrimaries_Source", {}),
                        "MasteringDisplay_Luminance": track.get("MasteringDisplay_Luminance", {}),
                        "MasteringDisplay_Luminance_Source": track.get("MasteringDisplay_Luminance_Source", {}),
                        "MaxCLL": track.get("MaxCLL", {}),
                        "MaxCLL_Source": track.get("MaxCLL_Source", {}),
                        "MaxFALL": track.get("MaxFALL", {}),
                        "MaxFALL_Source": track.get("MaxFALL_Source", {}),
                        "Encoded_Library_Settings": track.get("Encoded_Library_Settings", {}),
                        "Encoded_Library": track.get("Encoded_Library", {}),
                        "Encoded_Library_Name": track.get("Encoded_Library_Name", {}),
                    }
                )
            elif track_type == "Audio":
                media_tracks.append(
                    {
                        "@type": track_type,
                        "StreamOrder": track.get("StreamOrder", {}),
                        "ID": track.get("ID", {}),
                        "UniqueID": track.get("UniqueID", {}),
                        "Format": track.get("Format", {}),
                        "Format_Version": track.get("Format_Version", {}),
                        "Format_Profile": track.get("Format_Profile", {}),
                        "Format_Settings": track.get("Format_Settings", {}),
                        "Format_Commercial_IfAny": track.get("Format_Commercial_IfAny", {}),
                        "Format_Settings_Endianness": track.get("Format_Settings_Endianness", {}),
                        "Format_AdditionalFeatures": track.get("Format_AdditionalFeatures", {}),
                        "CodecID": track.get("CodecID", {}),
                        "Duration": track.get("Duration", {}),
                        "BitRate_Mode": track.get("BitRate_Mode", {}),
                        "BitRate": track.get("BitRate", {}),
                        "Channels": track.get("Channels", {}),
                        "ChannelPositions": track.get("ChannelPositions", {}),
                        "ChannelLayout": track.get("ChannelLayout", {}),
                        "Channels_Original": track.get("Channels_Original", {}),
                        "ChannelLayout_Original": track.get("ChannelLayout_Original", {}),
                        "SamplesPerFrame": track.get("SamplesPerFrame", {}),
                        "SamplingRate": track.get("SamplingRate", {}),
                        "SamplingCount": track.get("SamplingCount", {}),
                        "FrameRate": track.get("FrameRate", {}),
                        "FrameCount": track.get("FrameCount", {}),
                        "Compression_Mode": track.get("Compression_Mode", {}),
                        "Delay": track.get("Delay", {}),
                        "Delay_Source": track.get("Delay_Source", {}),
                        "Video_Delay": track.get("Video_Delay", {}),
                        "StreamSize": track.get("StreamSize", {}),
                        "Title": track.get("Title", {}),
                        "Language": track.get("Language", {}),
                        "ServiceKind": track.get("ServiceKind", {}),
                        "Default": track.get("Default", {}),
                        "Forced": track.get("Forced", {}),
                        "extra": track.get("extra", {}),
                    }
                )
            elif track_type == "Text":
                media_tracks.append(
                    {
                        "@type": track_type,
                        "@typeorder": track.get("@typeorder", {}),
                        "StreamOrder": track.get("StreamOrder", {}),
                        "ID": track.get("ID", {}),
                        "UniqueID": track.get("UniqueID", {}),
                        "Format": track.get("Format", {}),
                        "CodecID": track.get("CodecID", {}),
                        "Duration": track.get("Duration", {}),
                        "BitRate": track.get("BitRate", {}),
                        "FrameRate": track.get("FrameRate", {}),
                        "FrameCount": track.get("FrameCount", {}),
                        "ElementCount": track.get("ElementCount", {}),
                        "StreamSize": track.get("StreamSize", {}),
                        "Title": track.get("Title", {}),
                        "Language": track.get("Language", {}),
                        "Default": track.get("Default", {}),
                        "Forced": track.get("Forced", {}),
                    }
                )
            elif track_type == "Menu":
                media_tracks.append(
                    {
                        "@type": track_type,
                        "extra": track.get("extra", {}),
                    }
                )
        return filtered

    mediainfo_cmd = None

    if is_dvd:
        logger.debug("[bold yellow]DVD detected, using specialized MediaInfo...")

        current_platform = platform.system().lower()

        if current_platform in ["linux", "windows"]:
            mediainfo_config = find_dvd_mediainfo(base_dir)
            if mediainfo_config:
                if mediainfo_config["cli"]:
                    mediainfo_cmd = mediainfo_config["cli"]
                else:
                    logger.debug("[yellow]DVD MediaInfo CLI not available[/yellow]")
            else:
                logger.debug("[yellow]No specialized MediaInfo components found, using system MediaInfo[/yellow]")
        else:
            logger.debug(f"[yellow]DVD processing on {current_platform} not supported with specialized MediaInfo[/yellow]")

    logger.debug("[bold yellow]Exporting MediaInfo...")
    if not isdir:
        os.chdir(Path(video).parent)

    media_info_json = ""
    if mediainfo_cmd and is_dvd:
        result: subprocess.CompletedProcess[str] | None = None
        try:
            # Validate and sanitize the video path
            safe_video_path = validate_file_path(video)
            safe_mediainfo_cmd = validate_file_path(mediainfo_cmd)
            cmd = [safe_mediainfo_cmd, safe_video_path]
            result = cast(subprocess.CompletedProcess[str], await asyncio.to_thread(subprocess.run, cmd, capture_output=True, text=True, timeout=30))

            if result.returncode == 0 and result.stdout:
                media_info = result.stdout
            else:
                raise subprocess.CalledProcessError(result.returncode, cmd, result.stdout, result.stderr)

        except subprocess.TimeoutExpired:
            logger.info("[bold red]Specialized MediaInfo timed out (30s) - falling back to standard MediaInfo[/bold red]")
            media_info = MediaInfo.parse(video, output="STRING", full=False)
        except ValueError as e:
            logger.info(f"[bold red]Path validation error: {e}[/bold red]")
            logger.info("[bold yellow]Falling back to standard MediaInfo for text...")
            media_info = MediaInfo.parse(video, output="STRING", full=False)
        except (subprocess.CalledProcessError, Exception) as e:
            logger.info(f"[bold red]Error getting text from specialized MediaInfo: {e}")
            if result is not None:
                logger.debug(f"[red]Subprocess stderr: {result.stderr}[/red]")
                logger.debug(f"[red]Subprocess returncode: {result.returncode}[/red]")
            logger.info("[bold yellow]Falling back to standard MediaInfo for text...")
            media_info = MediaInfo.parse(video, output="STRING", full=False)
    else:
        media_info = cast(str, MediaInfo.parse(video, output="STRING", full=False))

    # Keep the CLI footer so every exported text report identifies its MediaInfo version.
    filtered_media_info = media_info

    async with aiofiles.open(f"{base_dir}{'/' + 'tmp' + '/'}{folder_id}/MEDIAINFO.txt", "w", newline="", encoding="utf-8") as export:
        await export.write(filtered_media_info.replace(video, Path(video).name))
    async with aiofiles.open(f"{base_dir}{'/' + 'tmp' + '/'}{folder_id}/MEDIAINFO_CLEANPATH.txt", "w", newline="", encoding="utf-8") as export_cleanpath:
        await export_cleanpath.write(filtered_media_info.replace(video, Path(video).name))
    logger.debug("[bold green]MediaInfo Exported.")

    if mediainfo_cmd and is_dvd:
        result: subprocess.CompletedProcess[str] | None = None
        result2: subprocess.CompletedProcess[str] | None = None
        try:
            # Validate and sanitize the video path
            safe_video_path = validate_file_path(video)
            safe_mediainfo_cmd = validate_file_path(mediainfo_cmd)
            cmd = [safe_mediainfo_cmd, "--Output=JSON", safe_video_path]
            result2 = cast(subprocess.CompletedProcess[str], await asyncio.to_thread(subprocess.run, cmd, capture_output=True, text=True, timeout=30))

            if result2.returncode == 0 and result2.stdout:
                media_info_json = result2.stdout
                media_info_dict = json.loads(media_info_json)
            else:
                raise subprocess.CalledProcessError(result2.returncode, cmd, result2.stdout, result2.stderr)

        except ValueError as e:
            logger.info(f"[bold red]Path validation error: {e}[/bold red]")
            logger.info("[bold yellow]Falling back to standard MediaInfo for JSON...")
            media_info_json = MediaInfo.parse(video, output="JSON")
            media_info_dict = json.loads(media_info_json)
        except subprocess.TimeoutExpired:
            logger.info("[bold red]Specialized MediaInfo timed out (30s) - falling back to standard MediaInfo[/bold red]")
            media_info_json = MediaInfo.parse(video, output="JSON")
            media_info_dict = json.loads(media_info_json)
        except (subprocess.CalledProcessError, json.JSONDecodeError, Exception) as e:
            logger.info(f"[bold red]Error getting JSON from specialized MediaInfo: {e}")
            if result2 is not None:
                logger.debug(f"[red]Subprocess stderr: {result2.stderr}[/red]")
                logger.debug(f"[red]Subprocess returncode: {result2.returncode}[/red]")
                if result2.stdout:
                    logger.debug(f"[red]Subprocess stdout preview: {result2.stdout[:200]}...[/red]")
            logger.info("[bold yellow]Falling back to standard MediaInfo for JSON...[/bold yellow]")
            media_info_json = MediaInfo.parse(video, output="JSON")
            media_info_dict = json.loads(media_info_json)
    else:
        media_info_json = cast(str, MediaInfo.parse(video, output="JSON"))
        media_info_dict = json.loads(media_info_json)

    filtered_info = filter_mediainfo(media_info_dict)

    async with aiofiles.open(f"{base_dir}{'/' + 'tmp' + '/'}{folder_id}/MediaInfo.json", "w", encoding="utf-8") as export:
        await export.write(json.dumps(filtered_info, indent=4))
        logger.debug(f"[green]JSON file written to: {base_dir}{'/' + 'tmp' + '/'}{folder_id}/MediaInfo.json[/green]")

    async with aiofiles.open(f"{base_dir}{'/' + 'tmp' + '/'}{folder_id}/MediaInfo.json", encoding="utf-8") as f:
        mi = cast(dict[str, Any], json.loads(await f.read()))

        logger.debug("[blue]Reset MediaInfo library configuration[/blue]")

    return mi


def validate_mediainfo(meta: Meta, settings: bool = False) -> bool:
    if not any(str(f).lower().endswith(".mkv") for f in meta.filelist):
        logger.debug(f"[yellow]Skipping {meta.path} (not an .mkv file)[/yellow]")
        return True

    unique_id = None
    valid_settings = False

    logger.debug("[cyan]Validating MediaInfo")

    mediainfo_data = meta.mediainfo

    if "media" in mediainfo_data and "track" in mediainfo_data["media"]:
        tracks = mediainfo_data["media"]["track"]
        track_names = [str(track.get("@type", "Unknown")) for track in tracks]
        logger.debug(f"[cyan]MediaInfo tracks: {', '.join(track_names)}[/cyan]")
        has_audio = any(track.get("@type", "") == "Audio" for track in tracks)

        if not has_audio:
            raise NoAudioMediaError(f"{meta.ua_name} does not support no audio media.")

        for track in tracks:
            track_type = track.get("@type", "")

            if settings and track_type == "Video":
                encoding_settings = track.get("Encoded_Library_Settings")
                if encoding_settings and encoding_settings != {} and str(encoding_settings).strip():
                    valid_settings = True
                    logger.debug(f"[green]Found encoding settings: {encoding_settings}[/green]")
                    break

            elif not settings and track_type == "General":
                unique_id_value = track.get("UniqueID")
                if unique_id_value and unique_id_value != {} and str(unique_id_value).strip():
                    unique_id = str(unique_id_value)
                    logger.debug(f"[green]Found Unique ID: {unique_id}[/green]")
                    break

    if settings and not valid_settings:
        logger.debug("[yellow]Mediainfo failed validation (no encoding settings)[/yellow]")
    elif not settings and not unique_id:
        logger.debug("[yellow]Mediainfo failed validation (no unique ID)[/yellow]")

    return valid_settings if settings else bool(unique_id)


async def get_conformance_error(meta: Meta) -> bool:
    if meta.is_disc != "BDMV" and meta.mediainfo.get("media", {}).get("track"):
        general_track = next((track for track in meta.mediainfo["media"]["track"] if track.get("@type") == "General"), None)
        if general_track and general_track.get("extra", {}).get("ConformanceErrors", {}):
            return True
        logger.debug("[green]No Conformance errors found in MediaInfo General track[/green]")
        return False
    return False
