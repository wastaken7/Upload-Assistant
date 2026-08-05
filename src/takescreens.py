# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import asyncio
import contextlib
import gc
import glob
import json
import os
import platform
import random
import re
import sys
import time
import traceback
import urllib.parse
import uuid
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Awaitable, Mapping
from pathlib import Path
from typing import Any, cast

import ffmpeg
from pymediainfo import MediaInfo

from data import config as data_config
from src.artwork import is_public_http_url, is_valid_cover_image, is_valid_image_bytes
from src.cleanup import cleanup_manager
from src.console import logger
from src.meta import Meta
from src.screenshot_manifest import clear_group as clear_screenshot_group
from src.screenshot_manifest import files as manifest_files
from src.screenshot_manifest import register as register_screenshots
from src.temp_paths import artwork_dir, screenshots_dir
from src.webui_progress import complete_progress, publish_progress

default_config: dict[str, Any] = {}
task_limit = 1
cutoff = 1
ffmpeg_limit = False
ffmpeg_is_good = False
use_libplacebo = True
tone_map = False
ffmpeg_compression = "6"


def compile_ffmpeg_command(command: Any) -> list[str]:
    """Compile an ffmpeg-python command into subprocess-safe string arguments."""
    return [str(argument) for argument in command.compile()]


algorithm = "mobius"
desat = 10.0


def _apply_config(config: Mapping[str, Any]) -> None:
    global default_config, task_limit, cutoff
    global ffmpeg_limit, ffmpeg_is_good, use_libplacebo
    global tone_map, ffmpeg_compression, algorithm, desat

    default_section = config.get("DEFAULT", {})
    default_config = cast(dict[str, Any], default_section) if isinstance(default_section, Mapping) else {}

    try:
        task_limit = int(default_config.get("process_limit", 1) or 1)
    except TypeError, ValueError:
        task_limit = 1

    try:
        cutoff = int(default_config.get("cutoff_screens", 1) or 1)
    except TypeError, ValueError:
        cutoff = 1

    ffmpeg_limit = default_config.get("ffmpeg_limit", False)
    ffmpeg_is_good = default_config.get("ffmpeg_is_good", False)
    use_libplacebo = default_config.get("use_libplacebo", True)
    tone_map = default_config.get("tone_map", False)
    ffmpeg_compression = str(default_config.get("ffmpeg_compression", "6"))
    algorithm = str(default_config.get("algorithm", "mobius")).strip()
    try:
        desat = float(default_config.get("desat", 10.0))
    except TypeError, ValueError:
        desat = 10.0


async def run_ffmpeg(command: Any) -> tuple[int | None, bytes, bytes]:
    cmd_list = compile_ffmpeg_command(command)
    process_env = os.environ.copy()

    # FFREPORT defaults to a timestamped file in the current working
    # directory.  Keep each report beside its output, with a unique name so
    # concurrent or repeated runs do not overwrite an earlier report.
    output_path = cmd_list[-1] if cmd_list else ""
    if output_path and output_path not in {"-", "pipe:"} and not output_path.startswith("pipe:"):
        report_path = Path(output_path).resolve().parent / f"ffmpeg-{uuid.uuid4().hex}.log"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        # FFREPORT uses ':' as a field separator, so escape the drive-letter
        # colon in Windows paths after converting separators to '/'.
        report_path_value = report_path.as_posix().replace(":", r"\:")
        process_env["FFREPORT"] = f"file={report_path_value}:level=32"
    else:
        process_env.pop("FFREPORT", None)

    # On Linux prefer bundled amd/arm binary when present; otherwise fall back to system ffmpeg.
    if platform.system() == "Linux":
        base_dir = str(Path(__file__).parent.parent)
        ff_bin_dir = Path(base_dir) / "bin" / "ffmpeg"

        machine = platform.machine().lower()
        if machine in ("x86_64", "amd64"):
            arch = "amd"
        elif machine in ("aarch64", "arm64"):
            arch = "arm"
        else:
            arch = None

        if arch:
            candidate = Path(ff_bin_dir) / arch / "ffmpeg"
            if Path(candidate).exists():
                cmd_list[0] = str(candidate)

    # Spawn the selected bundled binary or the system/default command.
    process = await asyncio.create_subprocess_exec(
        *cmd_list,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=process_env,
    )
    try:
        stdout, stderr = await process.communicate()
    except asyncio.CancelledError:
        if process.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=3)
            except TimeoutError:
                with contextlib.suppress(ProcessLookupError):
                    process.kill()
                await process.wait()
        raise
    return process.returncode, stdout, stderr


async def sanitize_filename(filename: str) -> str:
    # Replace invalid characters like colons with an underscore
    return re.sub(r'[<>:"/\\|?*]', "_", filename)


def round_to_even(value: float) -> int:
    rounded = round(value)
    if rounded % 2 != 0:
        rounded += 1
    return rounded


async def disc_screenshots(
    meta: Meta,
    filename: str,
    bdinfo: dict[str, Any],
    folder_id: str,
    base_dir: str,
    use_vs: bool,
    image_list: list[dict[str, str]] | None = None,
    ffdebug: bool = False,
    num_screens: int = 0,
    force_screenshots: bool = False,
    cleanup_after_capture: bool = True,
    capture_group: str | None = None,
) -> list[Path]:
    img_host = await get_image_host(meta)
    screens = meta.screens
    start_time = time.time() if meta.debug else 0.0
    if "image_list" not in meta:
        meta.image_list = []
    image_list_entries = meta.image_list
    existing_images: list[dict[str, Any]] = [img for img in image_list_entries if str(img.get("img_url", "")).startswith("http")]

    if len(existing_images) >= cutoff and not force_screenshots:
        logger.info(f"[yellow]There are already at least {cutoff} images in the image list. Skipping additional screenshots.")
        return []

    if not num_screens:
        num_screens = screens
    if num_screens == 0 or (image_list and len(image_list) >= num_screens):
        return []

    sanitized_filename = await sanitize_filename(filename)
    length: float = 0.0
    file_path: str = ""
    frame_rate: float | None = None
    bdinfo_files = cast(list[dict[str, Any]], bdinfo.get("files", []))
    bdinfo_path = cast(str, bdinfo.get("path", ""))
    for each in bdinfo_files:
        # Calculate total length in seconds, including fractional part
        length_str = str(each.get("length", "0"))
        int_length = sum(float(x) * 60**i for i, x in enumerate(reversed(length_str.split(":"))))

        if int_length > length:
            length = int_length
            for root, _dirs, files in os.walk(bdinfo_path):
                for name in files:
                    if name.lower() == str(each.get("file", "")).lower():
                        file_path = Path(root) / name
                        break  # Stop searching once the file is found

    if bdinfo.get("video"):
        fps_string = bdinfo["video"][0].get("fps", None)
        if fps_string:
            try:
                frame_rate = float(fps_string.split(" ")[0])  # Extract and convert to float
            except ValueError:
                logger.error("[red]Error: Unable to parse frame rate from bdinfo['video'][0]['fps']")

    file_path = file_path

    keyframe = "nokey" if "VC-1" in bdinfo["video"][0]["codec"] or bdinfo["video"][0]["hdr_dv"] != "" else "none"
    logger.debug(f"File: {file_path}, Length: {length}, Frame Rate: {frame_rate}", extra={"markup": False})
    screenshot_dir = screenshots_dir(base_dir, folder_id)
    existing_screens = [p.name for p in manifest_files(base_dir, folder_id, capture_group or sanitized_filename)]
    total_existing = len(existing_screens) + len(existing_images)
    num_screens = max(0, screens - total_existing) if not force_screenshots else num_screens

    if num_screens == 0 and not force_screenshots:
        logger.info("[bold green]Reusing existing screenshots. No additional screenshots needed.")
        return []

    if meta.debug and not force_screenshots:
        logger.info(f"[bold yellow]Saving Screens... Total needed: {screens}, Existing: {total_existing}, To capture: {num_screens}")

    if tone_map and "HDR" in meta.hdr:
        hdr_tonemap = True
        meta.tonemapped = True
    else:
        hdr_tonemap = False

    ss_times = await valid_ss_time([], num_screens, length, frame_rate or 24.0, meta, retake=force_screenshots)

    if meta.frame_overlay:
        logger.info("[yellow]Getting frame information for overlays...")
        # Build list of (original_index, task) to preserve index correspondence
        frame_info_tasks_with_idx = [
            (i, get_frame_info(file_path, ss_times[i], meta))
            for i in range(num_screens + 1)
            if not (screenshot_dir / f"{sanitized_filename}-{len(existing_screens) + i}.png").exists() or meta.retake
        ]
        frame_info_results = await asyncio.gather(*[task for _, task in frame_info_tasks_with_idx])
        meta.frame_info_map = {}

        # Create a mapping from time to frame info using preserved indices
        for (orig_idx, _), info in zip(frame_info_tasks_with_idx, frame_info_results, strict=False):
            meta.frame_info_map[ss_times[orig_idx]] = info

        logger.debug(f"[cyan]Collected frame information for {len(frame_info_results)} frames")

    num_workers = min(num_screens, task_limit)

    logger.debug(f"Using {num_workers} worker(s) for {num_screens} image(s)")

    capture_tasks: list[Awaitable[tuple[int, str] | None]] = []
    capture_results: list[str] = []
    valid_results: list[str] = []
    remaining_retakes: list[str] = []
    if use_vs:
        from src.vs import vs_screengn

        before = {path.resolve() for path in screenshot_dir.glob("*.png")}
        vs_screengn(source=file_path, encode=None, num=num_screens, dir=f"{screenshot_dir}/")
        valid_results = [str(path) for path in screenshot_dir.glob("*.png") if path.resolve() not in before]
    else:
        loglevel = "verbose" if ffdebug else "quiet"

        existing_indices = set(range(len(existing_screens)))

        # Create semaphore to limit concurrent tasks
        semaphore = asyncio.Semaphore(task_limit)

        async def capture_disc_with_semaphore(
            index: int, file: str, ss_time: str, image_path: str, keyframe: str, loglevel: str, hdr_tonemap: bool, meta: Meta
        ) -> tuple[int, str] | None:
            async with semaphore:
                return await capture_disc_task(index, file, ss_time, image_path, keyframe, loglevel, hdr_tonemap, meta)

        capture_tasks = [
            capture_disc_with_semaphore(
                i,
                file_path,
                ss_times[i],
                str((screenshot_dir / f"{sanitized_filename}-{len(existing_indices) + i}.png").resolve()),
                keyframe,
                loglevel,
                hdr_tonemap,
                meta,
            )
            for i in range(num_screens + 1)
        ]

        results = await asyncio.gather(*capture_tasks)
        filtered_results: list[tuple[int, str]] = [r for r in results if r is not None]

        if len(filtered_results) != len(results):
            logger.warning(f"[yellow]Warning: {len(results) - len(filtered_results)} capture tasks returned invalid results.")

        filtered_results.sort(key=lambda x: x[0])  # Ensure order is preserved
        capture_results = [r[1] for r in filtered_results]

        if capture_results and len(capture_results) > num_screens:
            try:
                smallest: str = min(capture_results, key=os.path.getsize)
                logger.debug(f"[yellow]Removing smallest image: {smallest} ({Path(smallest).stat().st_size} bytes)")
                Path(smallest).unlink()
                capture_results.remove(smallest)
            except Exception as e:
                logger.error(f"[red]Error removing smallest image: {e!s}")

        if not force_screenshots and meta.debug:
            logger.info(f"[green]Successfully captured {len(capture_results)} screenshots.")

        valid_results = []
        remaining_retakes = []
        for image_path in capture_results:
            if "Error" in image_path:
                logger.info(f"[red]{image_path}")
                continue

            retake = False
            image_size = Path(image_path).stat().st_size
            logger.debug(f"[yellow]Checking image {image_path} (size: {image_size} bytes) for image host: {img_host}[/yellow]")
            if image_size <= 75000:
                logger.info(f"[yellow]Image {image_path} is incredibly small, retaking.")
                retake = True
            else:
                if img_host and "imgbb" in img_host:
                    if image_size <= 31000000:
                        logger.debug(f"[green]Image {image_path} meets size requirements for imgbb.[/green]")
                    else:
                        logger.info(f"[red]Image {image_path} with size {image_size} bytes: does not meet size requirements for imgbb, retaking.")
                        retake = True
                elif img_host and img_host in ["imgbox", "pixhost"]:
                    if 75000 < image_size <= 10000000:
                        logger.debug(f"[green]Image {image_path} meets size requirements for {img_host}.[/green]")
                    else:
                        logger.info(f"[red]Image {image_path} with size {image_size} bytes: does not meet size requirements for {img_host}, retaking.")
                        retake = True
                elif img_host and img_host in ["lensdump", "ptscreens", "onlyimage", "dalexni", "zipline", "midnightscene", "passtheimage", "seedpool_cdn", "sharex", "utppm"]:
                    logger.debug(f"[green]Image {image_path} meets size requirements for {img_host}.[/green]")
                else:
                    logger.info(f"[red]Unknown image host or image doesn't meet requirements for host: {img_host}, retaking.")
                    retake = True

            if retake:
                retry_attempts = 3
                for attempt in range(1, retry_attempts + 1):
                    logger.info(f"[yellow]Retaking screenshot for: {image_path} (Attempt {attempt}/{retry_attempts})[/yellow]")
                    try:
                        index = int(image_path.rsplit("-", 1)[-1].split(".")[0])
                        if Path(image_path).exists():
                            Path(image_path).unlink()

                        random_time = random.uniform(0, length)  # nosec B311 - Random screenshot timing, not cryptographic  # noqa: S311
                        screenshot_response = await capture_disc_task(index, file_path, str(random_time), image_path, keyframe, loglevel, hdr_tonemap, meta)
                        new_size = Path(image_path).stat().st_size
                        valid_image = False

                        if img_host and "imgbb" in img_host:
                            if new_size > 75000 and new_size <= 31000000:
                                logger.info(f"[green]Successfully retaken screenshot for: {image_path} ({new_size} bytes)[/green]")
                                valid_image = True
                        elif img_host and img_host in ["imgbox", "pixhost"]:
                            if new_size > 75000 and new_size <= 10000000:
                                logger.info(f"[green]Successfully retaken screenshot for: {image_path} ({new_size} bytes)[/green]")
                                valid_image = True
                        elif (
                            img_host
                            and img_host in ["lensdump", "ptscreens", "onlyimage", "dalexni", "zipline", "midnightscene", "passtheimage", "seedpool_cdn", "sharex", "utppm"]
                            and new_size > 75000
                        ):
                            logger.info(f"[green]Successfully retaken screenshot for: {image_path} ({new_size} bytes)[/green]")
                            valid_image = True

                        if valid_image:
                            valid_results.append(image_path)
                            break
                        logger.info(f"[red]Retaken image {screenshot_response} does not meet the size requirements for {img_host}. Retrying...[/red]")
                    except Exception as e:
                        logger.error(f"[red]Error retaking screenshot for {image_path}: {e}[/red]")
                else:
                    logger.info(f"[red]All retry attempts failed for {image_path}. Skipping.[/red]")
                    remaining_retakes.append(image_path)
            else:
                valid_results.append(image_path)

        if remaining_retakes:
            logger.info(f"[red]The following images could not be retaken successfully: {remaining_retakes}[/red]")

    if not force_screenshots and meta.debug:
        logger.info(f"[green]Successfully captured {len(valid_results)} screenshots.")

    if meta.debug:
        finish_time = time.time()
        logger.debug(f"Screenshots processed in {finish_time - start_time:.4f} seconds")

    # The temporary descriptive names above are only used while capture is in
    # progress.  Publish completed frames under opaque UUID filenames.
    registered = register_screenshots(base_dir, folder_id, valid_results, capture_group or sanitized_filename) if valid_results else []

    multi_screens = int(default_config.get("multiScreens", 2))
    discs = meta.discs
    one_disc = True
    if discs and len(discs) == 1:
        one_disc = True
    elif discs and len(discs) > 1:
        one_disc = False

    if cleanup_after_capture and ((not meta.tv_pack and one_disc) or multi_screens == 0):
        await cleanup_manager.cleanup()
    return registered


async def capture_disc_task(index: int, file: str, ss_time: str, image_path: str, keyframe: str, loglevel: str, hdr_tonemap: bool, meta: Meta) -> tuple[int, str] | None:
    try:
        # Build filter chain
        vf_filters: list[str] = []

        if hdr_tonemap:
            vf_filters.extend(["zscale=transfer=linear", f"tonemap=tonemap={algorithm}:desat={desat}", "zscale=transfer=bt709", "format=rgb24"])

        if meta.frame_overlay:
            # Get frame info from pre-collected data if available
            frame_info = meta.frame_info_map.get(ss_time, {})

            frame_rate = meta.frame_rate if meta.frame_rate is not None else 24.0
            frame_number = int(float(ss_time) * frame_rate)

            # If we have PTS time from frame info, use it to calculate a more accurate frame number
            if "pts_time" in frame_info:
                # Only use PTS time for frame number calculation if it makes sense
                # (sometimes seeking can give us a frame from the beginning instead of where we want)
                pts_time = frame_info.get("pts_time", 0)
                if pts_time > 1.0 and abs(pts_time - ss_time) < 10:
                    frame_number = int(pts_time * frame_rate)

            frame_type = frame_info.get("frame_type", "Unknown")

            text_size = int(default_config.get("overlay_text_size", 18))
            # Get the resolution and convert it to integer
            resol = int("".join(filter(str.isdigit, (meta.resolution if meta.resolution is not None else "1080p"))))
            font_size = round(text_size * resol / 1080)
            border_width = round(2 * resol / 1080)
            x_all = round(10 * resol / 1080)

            # Scale vertical spacing based on font size
            line_spacing = round(font_size * 1.1)
            y_number = x_all
            y_type = y_number + line_spacing
            y_hdr = y_type + line_spacing

            # Frame number
            vf_filters.append(
                f"drawtext=text='Frame Number\\: {frame_number}':fontcolor=white:fontsize={font_size}:x={x_all}:y={y_number}:borderw={border_width}:bordercolor=black"
            )

            # Frame type
            vf_filters.append(f"drawtext=text='Frame Type\\: {frame_type}':fontcolor=white:fontsize={font_size}:x={x_all}:y={y_type}:borderw={border_width}:bordercolor=black")

            # HDR status
            if hdr_tonemap:
                vf_filters.append(f"drawtext=text='Tonemapped HDR':fontcolor=white:fontsize={font_size}:x={x_all}:y={y_hdr}:borderw={border_width}:bordercolor=black")

        # Build command
        # Always ensure at least format filter is present for PNG compression to work
        if not vf_filters:
            vf_filters.append("format=rgb24")
        vf_chain = ",".join(vf_filters)

        # Build ffmpeg-python command and run via run_ffmpeg
        info_command: Any = (
            cast(Any, ffmpeg)
            .input(file, ss=ss_time, skip_frame=keyframe)
            .output(image_path, vframes=1, vf=vf_chain, compression_level=ffmpeg_compression, pred="mixed")
            .global_args("-y", "-loglevel", loglevel, "-hide_banner")
        )

        if loglevel == "verbose" or (meta and meta.debug):
            logger.info(f"[cyan]FFmpeg command: {' '.join(compile_ffmpeg_command(info_command))}[/cyan]")

        returncode, stdout, stderr = await run_ffmpeg(info_command)

        # Print stdout and stderr if in verbose mode
        if loglevel == "verbose":
            if stdout:
                logger.info(f"[blue]FFmpeg stdout:[/blue]\n{stdout.decode('utf-8', errors='replace')}")
            if stderr:
                logger.info(f"[yellow]FFmpeg stderr:[/yellow]\n{stderr.decode('utf-8', errors='replace')}")

        if returncode == 0:
            return (index, image_path)
        logger.info(f"[red]FFmpeg error capturing screenshot: {stderr.decode()}")
        return None  # Ensure tuple format
    except Exception as e:
        logger.error(f"[red]Error capturing screenshot: {e}")
        return None


async def dvd_screenshots(
    meta: Meta,
    disc_num: int,
    num_screens: int = 0,
    retry_cap: bool = False,
    cleanup_after_capture: bool = True,
) -> None:
    screens = meta.screens
    if "image_list" not in meta:
        meta.image_list = []
    image_list_entries = meta.image_list
    existing_images: list[dict[str, Any]] = [img for img in image_list_entries if str(img.get("img_url", "")).startswith("http")]

    if len(existing_images) >= cutoff and not retry_cap:
        logger.info(f"[yellow]There are already at least {cutoff} images in the image list. Skipping additional screenshots.")
        return
    screens = meta.screens if meta.screens is not None else 6
    if not num_screens:
        num_screens = screens - len(existing_images)
    if num_screens == 0 or (len(meta.image_list) >= screens and disc_num == 0):
        return

    sanitized_disc_name = await sanitize_filename(meta.discs[disc_num]["name"])
    screenshot_dir = screenshots_dir(meta.base_dir, meta.uuid)
    existing_screens = [str(p) for p in manifest_files(meta.base_dir, meta.uuid, sanitized_disc_name)]
    normal_screens = existing_screens
    if len(normal_screens) >= num_screens:
        i = num_screens
        logger.info("[bold green]Reusing screenshots")
        return

    ifo_mi = MediaInfo.parse(f"{meta.discs[disc_num]['path']}/VTS_{meta.discs[disc_num]['main_set'][0][:2]}_0.IFO", mediainfo_options={"inform_version": "1"})
    sar = 1.0
    w_sar = 1.0
    h_sar = 1.0
    par: float = 1.0
    dar: float = 1.0
    width: float = 0.0
    height: float = 0.0
    frame_rate: float = 24.0
    tracks: list[Any] = []
    tracks.extend(cast(list[Any], getattr(ifo_mi, "tracks", [])))
    for track in tracks:
        if track.track_type == "Video":
            if isinstance(track.duration, str):
                durations = [float(d) for d in track.duration.split(" / ")]
                _ = max(durations) / 1000  # Use the longest duration (unused)
            else:
                _ = float(track.duration) / 1000  # Convert to seconds (unused)

            par = float(track.pixel_aspect_ratio)
            dar = float(track.display_aspect_ratio)
            width = float(track.width)
            height = float(track.height)
            frame_rate = float(track.frame_rate)
    if par < 1:
        new_height: float = dar * height
        sar = width / new_height
        w_sar = 1.0
        h_sar = sar
    else:
        sar = par
        w_sar = sar
        h_sar = 1.0

    async def _is_vob_good(n: int, loops: int, _num_screens: int) -> tuple[float, float]:
        max_loops = 6
        fallback_duration = 300
        valid_tracks: list[dict[str, Any]] = []

        while loops < max_loops:
            try:
                vob_mi = MediaInfo.parse(f"{meta.discs[disc_num]['path']}/VTS_{main_set[n]}", output="JSON")
                vob_mi = json.loads(vob_mi)

                for track in vob_mi.get("media", {}).get("track", []):
                    duration = float(track.get("Duration", 0))
                    width = track.get("Width")
                    height = track.get("Height")

                    if duration > 1 and width and height:  # Minimum 1-second track
                        valid_tracks.append({"duration": duration, "track_index": n})

                if valid_tracks:
                    # Sort by duration, take longest track
                    longest_track: dict[str, Any] = max(valid_tracks, key=lambda x: x["duration"])
                    return longest_track["duration"], longest_track["track_index"]

            except Exception as e:
                logger.error(f"[red]Error parsing VOB {n}: {e}")

            n = (n + 1) % len(main_set)
            loops += 1

        return fallback_duration, 0.0

    main_set = meta.discs[disc_num]["main_set"][1:] if len(meta.discs[disc_num]["main_set"]) > 1 else meta.discs[disc_num]["main_set"]
    voblength, _vob_index = await _is_vob_good(0, 0, num_screens)
    ss_times = await valid_ss_time([], num_screens, voblength, frame_rate, meta, retake=retry_cap)
    capture_tasks: list[Awaitable[tuple[int, str | None]]] = []
    existing_images_count = 0
    existing_image_paths: list[str] = []

    for i in range(num_screens + 1):
        image = str(screenshot_dir / f"{sanitized_disc_name}-{i}.png")
        input_file = f"{meta.discs[disc_num]['path']}/VTS_{main_set[i % len(main_set)]}"
        if Path(image).exists() and not meta.retake:
            existing_images_count += 1
            existing_image_paths.append(image)

    if existing_images_count == num_screens and not meta.retake:
        logger.debug("[yellow]The correct number of screenshots already exists. Skipping capture process.")
        capture_results: list[str] = existing_image_paths
        return
    capture_tasks = []
    image_paths: list[str] = []
    input_files: list[str] = []

    for i in range(num_screens + 1):
        image = str(screenshot_dir / f"{sanitized_disc_name}-{i}.png")
        input_file = f"{meta.discs[disc_num]['path']}/VTS_{main_set[i % len(main_set)]}"
        image_paths.append(image)
        input_files.append(input_file)

    if meta.frame_overlay:
        logger.debug("[yellow]Getting frame information for overlays...")
        frame_info_tasks = [get_frame_info(input_files[i], ss_times[i], meta) for i in range(num_screens + 1) if not Path(image_paths[i]).exists() or meta.retake]

        frame_info_results = await asyncio.gather(*frame_info_tasks)
        meta.frame_info_map = {}

        for i, info in enumerate(frame_info_results):
            meta.frame_info_map[ss_times[i]] = info

        logger.debug(f"[cyan]Collected frame information for {len(frame_info_results)} frames")

    num_workers = min(num_screens + 1, task_limit)

    logger.debug(f"Using {num_workers} worker(s) for {num_screens} image(s)")

    # Create semaphore to limit concurrent tasks
    semaphore = asyncio.Semaphore(task_limit)

    async def capture_dvd_with_semaphore(args: tuple[int, str, str, str, Meta, float, float, float, float]) -> tuple[int, str | None]:
        async with semaphore:
            return await capture_dvd_screenshot(args)

    for i in range(num_screens + 1):
        if not Path(image_paths[i]).exists() or meta.retake:
            capture_tasks.append(capture_dvd_with_semaphore((i, input_files[i], image_paths[i], ss_times[i], meta, width, height, w_sar, h_sar)))

    capture_results: list[str] = []
    results = await asyncio.gather(*capture_tasks)
    filtered_results: list[tuple[int, str | None]] = list(results)

    if len(filtered_results) != len(results):
        logger.warning(f"[yellow]Warning: {len(results) - len(filtered_results)} capture tasks returned invalid results.")

    filtered_results.sort(key=lambda x: x[0])  # Ensure order is preserved
    capture_results = [r[1] for r in filtered_results if r[1] is not None]

    if capture_results and len(capture_results) > num_screens:
        smallest = None
        smallest_size = float("inf")
        matching_files = [str(p) for p in screenshot_dir.glob(f"{glob.escape(sanitized_disc_name)}-*")]
        normal_screens = [Path(f).name for f in matching_files if re.match(r"^-\d+\.png$", Path(f).name[len(sanitized_disc_name) :])]
        for screens in normal_screens:
            screen_path = screenshot_dir / screens
            try:
                screen_size = Path(screen_path).stat().st_size
                if screen_size < smallest_size:
                    smallest_size = screen_size
                    smallest = screen_path
            except FileNotFoundError:
                logger.info(f"[red]File not found: {screen_path}[/red]")  # Handle potential edge cases
                continue

        if smallest:
            logger.debug(f"[yellow]Removing smallest image: {smallest} ({smallest_size} bytes)[/yellow]")
            Path(smallest).unlink()
            capture_results.remove(smallest)

    valid_results: list[str] = []
    remaining_retakes: list[str] = []

    for image in capture_results:
        if "Error" in image:
            logger.info(f"[red]{image}")
            continue

        retake = False
        image_size = Path(image).stat().st_size
        if image_size <= 120000:
            logger.info(f"[yellow]Image {image} is incredibly small, retaking.")
            retake = True

        if retake:
            retry_attempts = 3
            for attempt in range(1, retry_attempts + 1):
                logger.info(f"[yellow]Retaking screenshot for: {image} (Attempt {attempt}/{retry_attempts})[/yellow]")

                index = int(image.rsplit("-", 1)[-1].split(".")[0])
                input_file = f"{meta.discs[disc_num]['path']}/VTS_{main_set[index % len(main_set)]}"
                adjusted_time = random.uniform(0, voblength)  # nosec B311 - Random screenshot timing, not cryptographic  # noqa: S311

                if Path(image).exists():  # Prevent unnecessary deletion error
                    try:
                        Path(image).unlink()
                    except Exception as e:
                        logger.error(f"[red]Failed to delete {image}: {e}[/red]")
                        break

                try:
                    screenshot_response = await capture_dvd_screenshot((index, input_file, image, str(adjusted_time), meta, width, height, w_sar, h_sar))

                    index, screenshot_result = screenshot_response  # Safe unpacking

                    if screenshot_result is None:
                        logger.error(f"[red]Failed to capture screenshot for {image}. Retrying...[/red]")
                        continue

                    retaken_size = Path(screenshot_result).stat().st_size
                    if retaken_size > 75000:
                        logger.info(f"[green]Successfully retaken screenshot for: {screenshot_result} ({retaken_size} bytes)[/green]")
                        valid_results.append(screenshot_result)
                        break
                    logger.info(f"[red]Retaken image {screenshot_result} is still too small. Retrying...[/red]")
                except Exception as e:
                    logger.error(f"[red]Error capturing screenshot for {input_file} at {adjusted_time}: {e}[/red]")

            else:
                logger.info(f"[red]All retry attempts failed for {image}. Skipping.[/red]")
                remaining_retakes.append(image)
        else:
            valid_results.append(image)
    if remaining_retakes:
        logger.info(f"[red]The following images could not be retaken successfully: {remaining_retakes}[/red]")

    if valid_results:
        register_screenshots(meta.base_dir, meta.uuid, valid_results, sanitized_disc_name)

    if not retry_cap and meta.debug:
        logger.info(f"[green]Successfully captured {len(valid_results)} screenshots.")

    multi_screens = int(default_config.get("multiScreens", 2))
    discs = meta.discs
    one_disc = True
    if discs and len(discs) == 1:
        one_disc = True
    elif discs and len(discs) > 1:
        one_disc = False

    if cleanup_after_capture and ((not meta.tv_pack and one_disc) or multi_screens == 0):
        await cleanup_manager.cleanup()


async def capture_dvd_screenshot(task: tuple[int, str, str, str, Meta, float, float, float, float]) -> tuple[int, str | None]:
    index, input_file, image, seek_time_str, meta, width, height, w_sar, h_sar = task
    seek_time = float(seek_time_str)

    try:
        loglevel = "verbose" if meta.ffdebug else "quiet"
        media_info = MediaInfo.parse(input_file)
        video_duration: float | None = None
        tracks: list[Any] = []
        tracks.extend(cast(list[Any], getattr(media_info, "tracks", [])))
        for track in tracks:
            if track.track_type == "Video":
                try:
                    if track.duration is not None:
                        video_duration = float(track.duration)
                except TypeError, ValueError:
                    video_duration = None
                break

        if video_duration and seek_time > video_duration:
            seek_time = max(0, video_duration - 1)

        # Build filter chain
        vf_filters: list[str] = []
        if w_sar != 1 or h_sar != 1:
            scaled_w = round_to_even(width * w_sar)
            scaled_h = round_to_even(height * h_sar)
            vf_filters.append(f"scale={scaled_w}:{scaled_h}")

        if meta.frame_overlay:
            # Get frame info from pre-collected data if available
            frame_info = meta.frame_info_map.get(str(seek_time), {})

            frame_rate = meta.frame_rate if meta.frame_rate is not None else 24.0
            frame_number = int(seek_time * frame_rate)

            # If we have PTS time from frame info, use it to calculate a more accurate frame number
            if "pts_time" in frame_info:
                # Only use PTS time for frame number calculation if it makes sense
                # (sometimes seeking can give us a frame from the beginning instead of where we want)
                pts_time = frame_info.get("pts_time", 0)
                if pts_time > 1.0 and abs(pts_time - seek_time) < 10:
                    frame_number = int(pts_time * frame_rate)

            frame_type = frame_info.get("frame_type", "Unknown")

            text_size = int(default_config.get("overlay_text_size", 18))
            # Get the resolution and convert it to integer
            resol = int("".join(filter(str.isdigit, (meta.resolution if meta.resolution is not None else "576p"))))
            font_size = round(text_size * resol / 576)
            border_width = round(2 * resol / 576)
            x_all = round(10 * resol / 576)

            # Scale vertical spacing based on font size
            line_spacing = round(font_size * 1.1)
            y_number = x_all
            y_type = y_number + line_spacing

            # Frame number
            vf_filters.append(
                f"drawtext=text='Frame Number\\: {frame_number}':fontcolor=white:fontsize={font_size}:x={x_all}:y={y_number}:borderw={border_width}:bordercolor=black"
            )

            # Frame type
            vf_filters.append(f"drawtext=text='Frame Type\\: {frame_type}':fontcolor=white:fontsize={font_size}:x={x_all}:y={y_type}:borderw={border_width}:bordercolor=black")

        # Build command
        # Always ensure at least format filter is present for PNG compression to work
        if not vf_filters:
            vf_filters.append("format=rgb24")
        vf_chain = ",".join(vf_filters)

        # Build ffmpeg-python command and run via run_ffmpeg
        info_command: Any = (
            cast(Any, ffmpeg)
            .input(input_file, ss=str(seek_time), accurate_seek=None)
            .output(image, vframes=1, vf=vf_chain, compression_level=ffmpeg_compression, pred="mixed")
            .global_args("-y", "-loglevel", loglevel, "-hide_banner")
        )

        if loglevel == "verbose" or (meta and meta.debug):
            logger.info(f"[cyan]FFmpeg command: {' '.join(compile_ffmpeg_command(info_command))}[/cyan]")

        returncode, _stdout, stderr = await run_ffmpeg(info_command)

        if returncode != 0:
            logger.error(f"[red]Error capturing screenshot for {input_file} at {seek_time}s:[/red]\n{stderr.decode()}")
            return (index, None)

        if Path(image).exists():
            return (index, image)
        logger.info(f"[red]Screenshot creation failed for {image}[/red]")
        return (index, None)

    except Exception as e:
        logger.error(f"[red]Error capturing screenshot for {input_file} at {seek_time}s: {e}[/red]")
        return (index, None)


async def load_local_cover_if_exists(path: str, dest_path: str) -> bool:
    import shutil

    def _check_and_copy():
        search_dir = path if Path(path).is_dir() else str(Path(path).parent)
        valid_names = {"cover.png", "cover.jpg", "cover.jpeg", "folder.png", "folder.jpg", "folder.jpeg", "poster.png", "poster.jpg", "poster.jpeg"}
        if Path(search_dir).exists():
            for f in (p.name for p in Path(search_dir).iterdir()):
                if f.lower() in valid_names:
                    local_file = Path(search_dir) / f
                    if not is_valid_cover_image(local_file):
                        continue
                    shutil.copy2(local_file, dest_path)
                    return is_valid_cover_image(dest_path)
        return False

    try:
        return await asyncio.to_thread(_check_and_copy)
    except Exception as e:
        logger.info(f"[yellow]Error checking/copying local cover: {e}[/yellow]")
        return False


async def extract_embedded_cover_from_audiobook(meta: Meta, dest_path: str, confirmed_only: bool = False) -> bool:
    import mutagen

    def _extract():
        filelist = meta.filelist
        if not filelist:
            p = meta.path
            if p and Path(p).is_file():
                filelist = [p]
            else:
                return False

        audio_extensions = {".mp3", ".m4b", ".flac", ".aac", ".m4a", ".ogg", ".wav"}

        for audio_path in filelist:
            ext = Path(audio_path).suffix.lower()
            if ext not in audio_extensions:
                continue
            if not Path(audio_path).exists():
                continue

            try:
                audio = mutagen.File(audio_path)
                if audio is None:
                    continue

                # 1. FLAC / OGG pictures
                if hasattr(audio, "pictures") and audio.pictures:
                    pic = None
                    if confirmed_only:
                        for p in audio.pictures:
                            if getattr(p, "type", None) == 3:
                                pic = p
                                break
                    else:
                        pic = audio.pictures[0]

                    if pic is not None:
                        with Path(dest_path).open("wb") as f:
                            f.write(pic.data)
                        return True

                # 2. MP3 ID3 APIC
                if audio.tags:
                    apic_to_use = None
                    for key in audio.tags:
                        if key.startswith("APIC"):
                            apic = audio.tags[key]
                            if getattr(apic, "type", None) == 3:
                                apic_to_use = apic
                                break

                    if not apic_to_use and not confirmed_only:
                        for key in audio.tags:
                            if key.startswith("APIC"):
                                apic_to_use = audio.tags[key]
                                break

                    if apic_to_use is not None:
                        with Path(dest_path).open("wb") as f:
                            f.write(apic_to_use.data)
                        return True

                # 3. MP4 / M4A / M4B
                if "covr" in audio:
                    covr = audio["covr"]
                    if isinstance(covr, list) and len(covr) > 0:
                        item = covr[0]
                        with Path(dest_path).open("wb") as f:
                            f.write(bytes(item))
                        return True
            except Exception as e:
                logger.debug(f"[yellow]Error extracting from {audio_path}: {e}[/yellow]")
        return False

    try:
        return await asyncio.to_thread(_extract)
    except Exception as e:
        logger.info(f"[yellow]Error extracting embedded cover: {e}[/yellow]")
        return False


async def download_artwork_from_meta(meta: Meta, artwork_path: str, *, force: bool = False) -> bool:
    artwork_url = meta.artwork_url
    if not artwork_url:
        return False

    if not force and is_valid_cover_image(artwork_path):
        meta.artwork_path = artwork_path
        return True
    try:
        import httpx

        cookies = {}
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
        parsed_poster_url = urllib.parse.urlparse(artwork_url)
        poster_host = (parsed_poster_url.hostname or "").lower()
        if poster_host == "myanonamouse.net" or poster_host.endswith(".myanonamouse.net"):
            api_key = (
                default_config.get("mam_api_key", "").strip()
                or default_config.get("mam_id", "").strip()
                or os.environ.get("MAM_API_KEY", "").strip()
                or os.environ.get("MAM_ID", "").strip()
            )
            if api_key:
                cookies["mam_id"] = api_key

        current_url = artwork_url
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=False) as client:
            for _ in range(4):
                if not is_public_http_url(current_url):
                    logger.warning("[yellow]Warning: Artwork download target is not a public HTTP(S) URL.[/yellow]")
                    return False
                response = await client.get(current_url, cookies=cookies, headers=headers)
                if response.is_redirect:
                    location = response.headers.get("Location")
                    if not location:
                        return False
                    current_url = urllib.parse.urljoin(current_url, location)
                    continue
                if response.status_code == 200:
                    if not is_valid_image_bytes(response.content):
                        logger.info("[yellow]Warning: Downloaded artwork is not a valid supported image and will be ignored.[/yellow]")
                        return False
                    await asyncio.to_thread(Path(artwork_path).write_bytes, response.content)
                    if not is_valid_cover_image(artwork_path):
                        return False
                    meta.artwork_path = artwork_path
                    logger.info(f"[green]Successfully downloaded artwork from {current_url}[/green]")
                    return True
                logger.warning(f"[yellow]Warning: Failed to download poster, status code {response.status_code}[/yellow]")
                return False
            logger.warning("[yellow]Warning: Artwork download exceeded the redirect limit.[/yellow]")
    except Exception as e:
        logger.warning(f"[yellow]Warning: Error downloading poster: {e}[/yellow]")
    return False


async def extract_epub_cover(epub_path: str, dest_path: str, confirmed_only: bool = False) -> bool:
    def _extract():
        if not Path(epub_path).is_file() or not zipfile.is_zipfile(epub_path):
            return False
        with contextlib.suppress(Exception), zipfile.ZipFile(epub_path, "r") as z:
            rootfile_path = None
            with contextlib.suppress(Exception):
                container_data = z.read("META-INF/container.xml")
                root = ET.fromstring(container_data)
                for elem in root.iter():
                    if elem.tag.endswith("rootfile"):
                        rootfile_path = elem.attrib.get("full-path")
                        if rootfile_path:
                            break

            if not rootfile_path:
                for name in z.namelist():
                    if name.endswith(".opf"):
                        rootfile_path = name
                        break

            if not rootfile_path:
                return False

            opf_data = z.read(rootfile_path)
            root = ET.fromstring(opf_data)

            manifest_items = {}
            cover_item_id = None
            cover_href_direct = None
            opf_dir = str(Path(rootfile_path).parent)

            for elem in root.iter():
                tag_local = elem.tag.split("}")[-1]
                if tag_local == "item":
                    item_id = elem.attrib.get("id")
                    href = elem.attrib.get("href")
                    properties = elem.attrib.get("properties", "")
                    media_type = elem.attrib.get("media-type", "").lower()
                    if item_id and href:
                        manifest_items[item_id] = {"href": href, "media-type": media_type, "properties": properties}
                        if "cover-image" in properties:
                            cover_href_direct = href
                elif tag_local == "meta":
                    name_attr = elem.attrib.get("name")
                    content_attr = elem.attrib.get("content")
                    if name_attr == "cover" and content_attr:
                        cover_item_id = content_attr

            def resolve_path(base_dir: str, rel_path: str) -> str:
                combined = Path(base_dir) / rel_path.replace("\\", "/") if base_dir else rel_path.replace("\\", "/")
                parts = []
                for part in combined.split("/"):
                    if part == "." or not part:
                        continue
                    if part == "..":
                        if parts:
                            parts.pop()
                    else:
                        parts.append(part)
                return "/".join(parts)

            def is_image_item(href: str, media_type: str) -> bool:
                if media_type.startswith("image/"):
                    return True
                return href.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"))

            def get_image_from_html(html_href: str) -> str | None:
                with contextlib.suppress(Exception):
                    html_zip_path = resolve_path(opf_dir, html_href)
                    zip_names = z.namelist()
                    matched_name = None
                    if html_zip_path in zip_names:
                        matched_name = html_zip_path
                    else:
                        for name in zip_names:
                            if name.lower() == html_zip_path.lower():
                                matched_name = name
                                break
                    if matched_name:
                        html_content = z.read(matched_name).decode("utf-8", errors="ignore")
                        img_match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', html_content, re.IGNORECASE)
                        if img_match:
                            img_src = urllib.parse.unquote(img_match.group(1))
                            html_dir = str(Path(html_zip_path).parent)
                            return resolve_path(html_dir, img_src)
                        svg_match = re.search(r'<image[^>]+(?:xlink:)?href=["\']([^"\']+)["\']', html_content, re.IGNORECASE)
                        if svg_match:
                            img_src = urllib.parse.unquote(svg_match.group(1))
                            html_dir = str(Path(html_zip_path).parent)
                            return resolve_path(html_dir, img_src)
                return None

            cover_zip_path = None

            # 1. Properties has "cover-image"
            if cover_href_direct:
                cover_zip_path = resolve_path(opf_dir, cover_href_direct)

            # 2. Meta cover tag points to an item ID
            if not cover_zip_path and cover_item_id and cover_item_id in manifest_items:
                item = manifest_items[cover_item_id]
                if is_image_item(item["href"], item["media-type"]):
                    cover_zip_path = resolve_path(opf_dir, item["href"])
                elif item["media-type"] in ("application/xhtml+xml", "text/html") or item["href"].lower().endswith((".xhtml", ".html", ".htm")):
                    cover_zip_path = get_image_from_html(item["href"])

            # 3. Item with standard IDs
            if not cover_zip_path:
                for item_id in ("cover", "cover-image", "coverimage"):
                    if item_id in manifest_items:
                        item = manifest_items[item_id]
                        if is_image_item(item["href"], item["media-type"]):
                            cover_zip_path = resolve_path(opf_dir, item["href"])
                            break
                        if item["media-type"] in ("application/xhtml+xml", "text/html") or item["href"].lower().endswith((".xhtml", ".html", ".htm")):
                            cover_zip_path = get_image_from_html(item["href"])
                            if cover_zip_path:
                                break

            if confirmed_only and not cover_zip_path:
                return False

            # 4. Any image item with "cover" in its ID or href
            if not cover_zip_path and not confirmed_only:
                for item_id, item in manifest_items.items():
                    if is_image_item(item["href"], item["media-type"]) and ("cover" in item_id.lower() or "cover" in item["href"].lower()):
                        cover_zip_path = resolve_path(opf_dir, item["href"])
                        break

            # 5. Search zip entries for names containing "cover" and ending with image extensions
            if not cover_zip_path and not confirmed_only:
                for name in z.namelist():
                    base = Path(name).name.lower()
                    if "cover" in base and base.endswith((".jpg", ".jpeg", ".png", ".webp", ".svg")):
                        cover_zip_path = name
                        break

            # 6. First image item in manifest
            if not cover_zip_path and not confirmed_only:
                for item in manifest_items.values():
                    if is_image_item(item["href"], item["media-type"]):
                        cover_zip_path = resolve_path(opf_dir, item["href"])
                        break

            if cover_zip_path:
                zip_names = z.namelist()
                matched_name = None
                if cover_zip_path in zip_names:
                    matched_name = cover_zip_path
                else:
                    cover_zip_path_lower = cover_zip_path.lower()
                    for name in zip_names:
                        if name.lower() == cover_zip_path_lower:
                            matched_name = name
                            break

                if matched_name:
                    with Path(dest_path).open("wb") as dest:
                        dest.write(z.read(matched_name))
                    return True
        return False

    return await asyncio.to_thread(_extract)


async def extract_document_cover(path: str, dest_path: str) -> bool:
    extension = Path(path).suffix.lower().lstrip(".")
    if extension not in {"pdf", "cbr", "cbz"}:
        return False

    output_path = Path(dest_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if extension == "pdf":
        import fitz  # PyMuPDF

        def _render_pdf_cover() -> bool:
            with fitz.open(path) as doc:
                if len(doc) == 0:
                    return False
                page = doc[0]
                pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0))
                pix.save(output_path)
                return True

        try:
            return await asyncio.to_thread(_render_pdf_cover)
        except Exception as e:
            logger.debug(f"[yellow]Warning: PDF cover extraction failed: {e}[/yellow]")
            return False

    import shutil
    import zipfile

    from PIL import Image

    unrar_path = str(data_config.config.get("DEFAULT", {}).get("unrar_path", "") or "").strip()
    if unrar_path:
        import rarfile as _rarfile

        os.environ["UNRAR_TOOL"] = unrar_path
        _rarfile.CURRENT_SETUP = None
        from rarfile import RarFile
    else:
        from rarfile import RarFile

    temp_extract = output_path.parent / "temp_cover_extract"

    def natural_sort_key(s: str) -> list[int | str]:
        return [int(text) if text.isdigit() else text.lower() for text in re.split(r"(\d+)", s)]

    def _extract_comic_cover() -> bool:
        temp_extract.mkdir(parents=True, exist_ok=True)
        compressed_file = None
        try:
            if extension == "cbz":
                try:
                    compressed_file = zipfile.ZipFile(path, "r")
                except Exception:
                    compressed_file = RarFile(path, "r")
            else:
                try:
                    compressed_file = RarFile(path, "r")
                except Exception:
                    compressed_file = zipfile.ZipFile(path, "r")

            if not compressed_file:
                return False

            image_files = [f for f in compressed_file.namelist() if f.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"))]
            if not image_files:
                return False

            image_files.sort(key=natural_sort_key)
            cover_name = image_files[0]
            compressed_file.extract(cover_name, temp_extract)
            extracted_path = temp_extract / cover_name

            if extracted_path.suffix.lower() == ".png":
                shutil.copy2(extracted_path, output_path)
            else:
                with Image.open(extracted_path) as img:
                    img.save(output_path, "PNG")
            return True
        finally:
            if compressed_file is not None:
                compressed_file.close()
            shutil.rmtree(temp_extract, ignore_errors=True)

    try:
        return await asyncio.to_thread(_extract_comic_cover)
    except Exception as e:
        logger.debug(f"[yellow]Warning: Comic cover extraction failed: {e}[/yellow]")
        return False


async def prepare_book_cover(path: str, folder_id: str, base_dir: str, meta: Meta) -> str | None:
    if meta.artwork_path and is_valid_cover_image(meta.artwork_path) and not meta.retake:
        return meta.artwork_path

    output_dir = artwork_dir(base_dir, folder_id)
    artwork_path = output_dir / "POSTER.png"

    if is_valid_cover_image(artwork_path) and not meta.retake:
        meta.artwork_path = str(artwork_path)
        return str(artwork_path)

    if await load_local_cover_if_exists(path, str(artwork_path)):
        meta.artwork_path = str(artwork_path)
        return str(artwork_path)

    if meta.audiobook:
        extracted_confirmed = await extract_embedded_cover_from_audiobook(meta, str(artwork_path), confirmed_only=True)
        if extracted_confirmed:
            meta.artwork_path = str(artwork_path)
            logger.debug("[green]Audiobook confirmed cover extracted. Skipping API download.[/green]")
            return str(artwork_path)

        downloaded_artwork = await download_artwork_from_meta(meta, str(artwork_path), force=meta.retake)
        if downloaded_artwork:
            meta.artwork_path = str(artwork_path)
            return str(artwork_path)

        extracted_unconfirmed = await extract_embedded_cover_from_audiobook(meta, str(artwork_path), confirmed_only=False)
        if extracted_unconfirmed:
            meta.artwork_path = str(artwork_path)
            return str(artwork_path)
        return None

    extension = Path(path).suffix.lower().lstrip(".")
    if extension == "epub":
        extracted_confirmed = await extract_epub_cover(path, str(artwork_path), confirmed_only=True)
        if extracted_confirmed:
            meta.artwork_path = str(artwork_path)
            logger.debug("[green]EPUB confirmed cover extracted. Skipping API download.[/green]")
            return str(artwork_path)

    downloaded_artwork = await download_artwork_from_meta(meta, str(artwork_path), force=meta.retake)
    if downloaded_artwork:
        meta.artwork_path = str(artwork_path)
        return str(artwork_path)

    if extension == "epub":
        extracted_unconfirmed = await extract_epub_cover(path, str(artwork_path), confirmed_only=False)
        if extracted_unconfirmed:
            meta.artwork_path = str(artwork_path)
            return str(artwork_path)
    elif extension in {"pdf", "cbr", "cbz"}:
        extracted_document_cover = await extract_document_cover(path, str(artwork_path))
        if extracted_document_cover:
            meta.artwork_path = str(artwork_path)
            return str(artwork_path)

    return None


async def generate_ebook_screenshots(
    path: str,
    filename: str,
    folder_id: str,
    base_dir: str,
    meta: Meta,
    num_screens: int = 5,
) -> list[str]:
    import random
    import shutil
    import zipfile

    import fitz  # PyMuPDF
    from PIL import Image

    unrar_path = str(data_config.config.get("DEFAULT", {}).get("unrar_path", "") or "").strip()
    if unrar_path:
        import rarfile as _rarfile

        os.environ["UNRAR_TOOL"] = unrar_path
        _rarfile.CURRENT_SETUP = None
        from rarfile import RarFile
    else:
        from rarfile import RarFile

    with contextlib.suppress(Exception):
        fitz.TOOLS.mupdf_display_errors(False)

    output_dir = str(screenshots_dir(base_dir, folder_id).resolve())
    sanitized_filename = await sanitize_filename(filename)

    extension = Path(path).suffix.lower().lstrip(".")
    screenshots = []

    poster_dir = artwork_dir(base_dir, folder_id)
    cover_path = poster_dir / "POSTER.png"
    banner_path = poster_dir / "POSTER_BANNER.png"

    banner_cached = Path(banner_path).exists() and Path(banner_path).stat().st_size > 0 and not meta.retake

    prepared_cover = await prepare_book_cover(path, folder_id, base_dir, meta)
    local_found = bool(prepared_cover)
    prepared_artwork = bool(prepared_cover)

    if extension in ["cbr", "cbz"]:
        temp_extract = Path(output_dir) / "temp_compressed_extract"
        Path(temp_extract).mkdir(parents=True, exist_ok=True)
        try:
            compressed_file = None
            if "cbz" in extension:
                try:
                    compressed_file = zipfile.ZipFile(path, "r")
                except Exception:
                    with contextlib.suppress(Exception):
                        compressed_file = RarFile(path, "r")
            else:
                try:
                    compressed_file = RarFile(path, "r")
                except Exception:
                    with contextlib.suppress(Exception):
                        compressed_file = zipfile.ZipFile(path, "r")

            if not compressed_file:
                logger.info(f"[red]Invalid CBR/CBZ file: {path}[/red]")
                return []

            image_files = [f for f in compressed_file.namelist() if f.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"))]

            def natural_sort_key(s):
                return [int(text) if text.isdigit() else text.lower() for text in re.split(r"(\d+)", s)]

            image_files.sort(key=natural_sort_key)

            if not image_files:
                logger.info("[yellow]CBR/CBZ does not contain images[/yellow]")
                compressed_file.close()
                return []

            num_screens = min(num_screens, len(image_files))
            selected_images = sorted(random.sample(range(len(image_files)), num_screens))

            async def process_compressed_image(img_idx: int, out_name: str) -> str:
                img_name = image_files[img_idx]
                compressed_file.extract(img_name, temp_extract)
                src_path = Path(temp_extract) / img_name
                dest_path = Path(output_dir) / f"{out_name}.png"

                def _convert():
                    img = Image.open(src_path)
                    img.save(dest_path, "PNG")

                if not img_name.lower().endswith(".png"):
                    await asyncio.to_thread(_convert)
                else:
                    shutil.copy2(src_path, dest_path)
                return dest_path

            for i, img_idx in enumerate(selected_images):
                scr_path = await process_compressed_image(img_idx, f"{sanitized_filename}-{i}")
                screenshots.append(scr_path)

            if not local_found and not prepared_artwork:
                await process_compressed_image(0, "POSTER")
            if not banner_cached:
                await process_compressed_image(len(image_files) - 1, "POSTER_BANNER")
            else:
                meta.artwork_banner_path = str(banner_path)

            meta.artwork_path = str(cover_path)
            meta.artwork_banner_path = str(banner_path)

            compressed_file.close()

        finally:
            if Path(temp_extract).exists():
                shutil.rmtree(temp_extract, ignore_errors=True)

    elif extension in ["pdf", "mobi", "epub"]:
        try:
            if extension == "epub" and not local_found and not prepared_artwork:
                try:
                    epub_cover_extracted = await extract_epub_cover(path, cover_path, confirmed_only=False)
                    if epub_cover_extracted:
                        prepared_artwork = True
                        meta.artwork_path = str(cover_path)
                except Exception as e:
                    logger.debug(f"[yellow]Warning: EPUB cover extraction failed: {e}[/yellow]")

            doc = fitz.open(path)
            total_pages = len(doc)

            if total_pages == 0:
                logger.info(f"[yellow]{extension.upper()} does not have pages[/yellow]")
                return []

            num_screens = min(num_screens, total_pages)
            selected_pages = sorted(random.sample(range(total_pages), num_screens))

            async def process_page(page_num: int, out_name: str) -> str:
                def _render():
                    page = doc[page_num]
                    mat = fitz.Matrix(2.0, 2.0)
                    pix = page.get_pixmap(matrix=mat)
                    scr_path = Path(output_dir) / f"{out_name}.png"
                    pix.save(scr_path)
                    return scr_path

                return await asyncio.to_thread(_render)

            for i, page_num in enumerate(selected_pages):
                scr_path = await process_page(page_num, f"{sanitized_filename}-{i}")
                screenshots.append(scr_path)

            if not local_found and not prepared_artwork:
                await process_page(0, "POSTER")
            if not banner_cached:
                await process_page(total_pages - 1, "POSTER_BANNER")
            else:
                meta.artwork_banner_path = str(banner_path)

            meta.artwork_path = str(cover_path)
            meta.artwork_banner_path = str(banner_path)

            doc.close()
        except Exception as e:
            logger.error(f"[red]Error while generating {extension.upper()} screenshots: {e}[/red]")
            import traceback

            logger.info(traceback.format_exc())

    return screenshots


async def screenshots(
    path: str,
    filename: str,
    folder_id: str,
    base_dir: str,
    meta: Meta,
    num_screens: int = 0,
    force_screenshots: bool = False,
    manual_frames: str | list[int] | list[str] = "",
    cleanup_after_capture: bool = True,
    capture_group: str | None = None,
) -> list[str] | None:
    if meta.category == "GAME":
        return []

    if meta.category == "BOOK":
        if meta.audiobook:
            await prepare_book_cover(path, folder_id, base_dir, meta)
            return []
        return await generate_ebook_screenshots(path, filename, folder_id, base_dir, meta, num_screens if num_screens > 0 else meta.screens)

    img_host = await get_image_host(meta)
    screens = meta.screens
    # A Web UI review can remove frames while the run waits for confirmation.
    # Respect that persisted target when this later, normal capture pass runs.
    from src.screenshot_review import target_count

    screens = target_count(Path(base_dir) / "tmp" / folder_id, screens)
    meta.screens = screens
    start_time = time.time() if meta.debug else 0.0
    logger.debug(f"Image Host: {img_host}")
    if "image_list" not in meta:
        meta.image_list = []

    image_list_entries = meta.image_list
    existing_images: list[dict[str, Any]] = [img for img in image_list_entries if str(img.get("img_url", "")).startswith("http")]

    if len(existing_images) >= cutoff and not force_screenshots:
        logger.info(f"[yellow]There are already at least {cutoff} images in the image list. Skipping additional screenshots.")
        return None

    group = capture_group or "main"
    if num_screens:
        requested_screens = num_screens
    elif isinstance(manual_frames, str):
        requested_screens = len([frame for frame in manual_frames.split(",") if frame.strip()]) if manual_frames else screens
    elif manual_frames:
        requested_screens = len(manual_frames)
    else:
        requested_screens = screens
    if meta.retake:
        clear_screenshot_group(base_dir, folder_id, group)
    registered_screens = manifest_files(base_dir, folder_id, group)
    # Metadata enrichment can alter the display title (for example, by adding
    # punctuation). Reuse the logical capture group rather than deriving
    # identity from a display-derived filename. This must happen before reading
    # MediaInfo so an already-complete early capture is a true no-op.
    if not force_screenshots and not meta.retake and len(registered_screens) >= requested_screens:
        logger.debug(f"[yellow]Reusing {len(registered_screens)} registered screenshots from group '{group}'.[/yellow]")
        return [str(screen) for screen in registered_screens[:requested_screens]]

    try:
        mi_text = await asyncio.to_thread(Path(f"{base_dir}{'/' + 'tmp' + '/'}{folder_id}/MediaInfo.json").read_text, encoding="utf-8")
        mi = json.loads(mi_text)
        video_track = mi["media"]["track"][1]

        def safe_float(value: Any, default: float = 0.0, field_name: str = "") -> float:
            if isinstance(value, (int, float)):
                return float(value)
            if isinstance(value, str):
                try:
                    return float(value)
                except ValueError:
                    logger.warning(f"[yellow]Warning: Could not convert string '{value}' to float for {field_name}, using default {default}[/yellow]")
                    return default
            elif isinstance(value, dict):
                for key in ["#value", "value", "duration", "Duration"]:
                    if key in value:
                        return safe_float(value[key], default, field_name)
                logger.warning(f"[yellow]Warning: {field_name} is a dict but no usable value found: {value}, using default {default}[/yellow]")
                return default
            else:
                logger.warning(f"[yellow]Warning: Unable to convert to float: {type(value)} {value} for {field_name}, using default {default}[/yellow]")
                return default

        length = safe_float(video_track.get("Duration"), safe_float(mi["media"]["track"][0].get("Duration"), 3600.0, "General Duration"), "Video Duration")

        width = safe_float(video_track.get("Width"), 1920.0, "Width")
        height = safe_float(video_track.get("Height"), 1080.0, "Height")
        par = safe_float(video_track.get("PixelAspectRatio"), 1.0, "PixelAspectRatio")
        dar = safe_float(video_track.get("DisplayAspectRatio"), 16.0 / 9.0, "DisplayAspectRatio")
        frame_rate = safe_float(video_track.get("FrameRate"), 24.0, "FrameRate")

        if par == 1:
            sar = w_sar = h_sar = 1.0
        elif par < 1:
            new_height = dar * height
            sar = width / new_height
            w_sar = 1.0
            h_sar = sar
        else:
            sar = w_sar = par
            h_sar = 1
    except Exception as e:
        logger.error(f"[red]Error processing MediaInfo.json: {e}")
        if meta.debug:
            import traceback

            logger.debug(traceback.format_exc())
        return None
    meta.frame_rate = frame_rate
    loglevel = "verbose" if meta.ffdebug else "quiet"
    if manual_frames and meta.debug:
        logger.info(f"[yellow]Using manual frames: {manual_frames}")
    ss_times: list[str] = []
    if manual_frames and not force_screenshots:
        try:
            manual_frames_list: list[int]
            if isinstance(manual_frames, str):
                manual_frames_list = [int(frame.strip()) for frame in manual_frames.split(",") if frame.strip()]
            else:
                manual_frames_list = [int(frame) for frame in manual_frames]
            num_screens = len(manual_frames_list)
            if num_screens > 0:
                ss_times = [str(frame / frame_rate) for frame in manual_frames_list]
        except (TypeError, ValueError) as e:
            if meta.debug and manual_frames:
                logger.error(f"[red]Error processing manual frames: {e}[/red]")
                sys.exit(1)

    if num_screens <= 0:
        num_screens = screens - len(existing_images)
    if not force_screenshots and not meta.retake:
        num_screens = max(0, num_screens - len(registered_screens))
    if num_screens <= 0:
        return [str(screen) for screen in registered_screens] or None

    sanitized_filename = await sanitize_filename(filename)
    screenshot_dir = screenshots_dir(base_dir, folder_id)
    test_image_path = str((screenshot_dir / f"{sanitized_filename}-libplacebo-test.png").resolve())

    existing_images_count = 0
    existing_image_paths: list[str] = []
    for i in range(num_screens):
        image_path = str((screenshot_dir / f"{sanitized_filename}-{i}.png").resolve())
        if Path(image_path).exists() and not meta.retake:
            existing_images_count += 1
            existing_image_paths.append(image_path)

    if existing_images_count == num_screens and not meta.retake:
        logger.debug("[yellow]The correct number of screenshots already exists. Skipping capture process.")
        return existing_image_paths

    num_capture = num_screens - existing_images_count

    progress_id = f"screenshots-{folder_id}"
    progress_label = "FFmpeg screenshots"
    completed_captures = 0
    publish_progress(
        progress_id,
        progress_label,
        current=completed_captures,
        total=num_capture,
        detail=f"0/{num_capture} frames completed",
        group="media",
        unit="frames",
    )

    if not ss_times:
        ss_times = await valid_ss_time([], num_capture, length, frame_rate, meta, retake=force_screenshots)

    if meta.frame_overlay:
        logger.debug("[yellow]Getting frame information for overlays...")
        # Build list of (original_index, task) to preserve index correspondence
        frame_info_tasks_with_idx = [
            (i, get_frame_info(path, ss_times[i], meta))
            for i in range(num_capture)
            if not (screenshot_dir / f"{sanitized_filename}-{existing_images_count + i}.png").exists() or meta.retake
        ]
        frame_info_results = await asyncio.gather(*[task for _, task in frame_info_tasks_with_idx])
        meta.frame_info_map = {}

        # Create a mapping from time to frame info using preserved indices
        for (orig_idx, _), info in zip(frame_info_tasks_with_idx, frame_info_results, strict=False):
            meta.frame_info_map[ss_times[orig_idx]] = info

        logger.debug(f"[cyan]Collected frame information for {len(frame_info_results)} frames")

    num_tasks = num_capture
    num_workers = min(num_tasks, task_limit)

    meta.libplacebo = False
    hdr_tonemap: bool = False
    if tone_map and ("HDR" in meta.hdr or "DV" in meta.hdr or "HLG" in meta.hdr):
        if use_libplacebo and not meta.frame_overlay:
            if not ffmpeg_is_good:
                test_time = str(ss_times[0] if ss_times else 0)
                libplacebo, compatible = await check_libplacebo_compatibility(w_sar, h_sar, width, height, path, test_time, test_image_path, loglevel, meta)
                if compatible:
                    hdr_tonemap = True
                    meta.tonemapped = True
                if libplacebo:
                    hdr_tonemap = True
                    meta.tonemapped = True
                    meta.libplacebo = True
                if not compatible and not libplacebo:
                    hdr_tonemap = False
                    logger.info("[yellow]FFMPEG failed tonemap checking.[/yellow]")
                    await asyncio.sleep(2)
                if not libplacebo and "HDR" not in meta.hdr:
                    hdr_tonemap = False
            else:
                hdr_tonemap = True
                meta.tonemapped = True
                meta.libplacebo = True
        else:
            if "HDR" not in meta.hdr:
                hdr_tonemap = False
            else:
                hdr_tonemap = True
                meta.tonemapped = True
    else:
        hdr_tonemap = False

    logger.debug(f"Using {num_workers} worker(s) for {num_capture} image(s)")

    # Create semaphore to limit concurrent tasks
    semaphore = asyncio.Semaphore(num_workers)

    async def capture_with_semaphore(args: tuple[int, str, float, str, float, float, float, float, str, bool, Meta]) -> tuple[int, str | None] | None:
        nonlocal completed_captures
        async with semaphore:
            result = await capture_screenshot(args)
            completed_captures += 1
            publish_progress(
                progress_id,
                progress_label,
                current=completed_captures,
                total=num_capture,
                detail=f"{completed_captures}/{num_capture} frames completed",
                group="media",
                unit="frames",
            )
            return result

    capture_tasks: list[Awaitable[tuple[int, str | None] | None]] = []
    for i in range(num_capture):
        image_index = existing_images_count + i
        image_path = str((screenshot_dir / f"{sanitized_filename}-{image_index}.png").resolve())
        if not Path(image_path).exists() or meta.retake:
            capture_tasks.append(capture_with_semaphore((i, path, float(ss_times[i]), image_path, width, height, w_sar, h_sar, loglevel, hdr_tonemap, meta)))

    try:
        results = cast(list[object], await asyncio.gather(*capture_tasks, return_exceptions=True))
        # Log any error strings that were returned (these indicate exceptions in capture_screenshot)
        for r in results:
            if isinstance(r, Exception):
                logger.info(f"[red]Screenshot capture exception: {r}[/red]")
        capture_result_tuples: list[tuple[int, str | None]] = [cast(tuple[int, str | None], r) for r in results if isinstance(r, tuple)]
        capture_result_tuples.sort(key=lambda x: x[0])
        capture_results: list[str] = [r[1] for r in capture_result_tuples if r[1] is not None]

    except KeyboardInterrupt:
        logger.info("\n[red]CTRL+C detected. Cancelling capture tasks...[/red]")
        await asyncio.sleep(0.1)
        logger.info("[red]All tasks cancelled. Exiting.[/red]")
        gc.collect()
        cleanup_manager.reset_terminal()
        sys.exit(1)
    except asyncio.CancelledError:
        await asyncio.sleep(0.1)
        gc.collect()
        cleanup_manager.reset_terminal()
        sys.exit(1)
    except Exception:
        await asyncio.sleep(0.1)
        gc.collect()
        cleanup_manager.reset_terminal()
        sys.exit(1)
    finally:
        await asyncio.sleep(0.1)
        logger.debug("[yellow]All capture tasks finished. Cleaning up...[/yellow]")

    if not force_screenshots and meta.debug:
        logger.info(f"[green]Successfully captured {len(capture_results)} screenshots.")

    valid_results: list[str] = []
    remaining_retakes: list[str] = []
    for image_path in capture_results:
        retake = False
        image_size = Path(image_path).stat().st_size
        logger.debug(f"[yellow]Checking image {image_path} (size: {image_size} bytes) for image host: {img_host}[/yellow]")
        if not manual_frames:
            if image_size <= 75000:
                logger.info(f"[yellow]Image {image_path} is incredibly small, retaking.")
                retake = True
            else:
                if img_host and "imgbb" in img_host:
                    if image_size <= 31000000:
                        logger.debug(f"[green]Image {image_path} meets size requirements for imgbb.[/green]")
                    else:
                        logger.info(f"[red]Image {image_path} with size {image_size} bytes: does not meet size requirements for imgbb, retaking.")
                        retake = True
                elif img_host and img_host in ["imgbox", "pixhost"]:
                    if 75000 < image_size <= 10000000:
                        logger.debug(f"[green]Image {image_path} meets size requirements for {img_host}.[/green]")
                    else:
                        logger.info(f"[red]Image {image_path} with size {image_size} bytes: does not meet size requirements for {img_host}, retaking.")
                        retake = True
                elif img_host and img_host in ["lensdump", "ptscreens", "onlyimage", "dalexni", "zipline", "midnightscene", "passtheimage", "seedpool_cdn", "sharex", "utppm"]:
                    logger.debug(f"[green]Image {image_path} meets size requirements for {img_host}.[/green]")
                else:
                    logger.info(f"[red]Unknown image host or image doesn't meet requirements for host: {img_host}, retaking.")
                    retake = True

        if retake:
            retry_attempts = 5
            retry_offsets = [5.0, 10.0, -10.0, 100.0, -100.0]
            frame_rate = meta.frame_rate if meta.frame_rate is not None else 24.0
            original_index = int(image_path.rsplit("-", 1)[-1].split(".")[0])
            original_time = ss_times[original_index] if original_index < len(ss_times) else None

            for attempt in range(1, retry_attempts + 1):
                if original_time is not None:
                    for offset in retry_offsets:
                        adjusted_time = max(0, float(original_time) + offset)
                        logger.info(
                            f"[yellow]Retaking screenshot for: {image_path} (Attempt {attempt}/{retry_attempts}) at {adjusted_time:.2f}s (offset {offset:+.2f}s)[/yellow]"
                        )
                        try:
                            if Path(image_path).exists():
                                Path(image_path).unlink()

                            screenshot_response = await capture_screenshot(
                                (original_index, path, adjusted_time, image_path, width, height, w_sar, h_sar, loglevel, hdr_tonemap, meta)
                            )

                            if not isinstance(screenshot_response, tuple) or len(screenshot_response) != 2:
                                continue

                            _, screenshot_path = screenshot_response

                            if not screenshot_path or not Path(screenshot_path).exists():
                                continue

                            new_size = Path(screenshot_path).stat().st_size
                            valid_image = False

                            if img_host and "imgbb" in img_host:
                                if 75000 < new_size <= 31000000:
                                    logger.info(f"[green]Successfully retaken screenshot for: {screenshot_path} ({new_size} bytes)[/green]")
                                    valid_image = True
                            elif img_host and img_host in ["imgbox", "pixhost"]:
                                if 75000 < new_size <= 10000000:
                                    logger.info(f"[green]Successfully retaken screenshot for: {screenshot_path} ({new_size} bytes)[/green]")
                                    valid_image = True
                            elif (
                                img_host
                                and img_host in ["lensdump", "ptscreens", "onlyimage", "dalexni", "zipline", "midnightscene", "passtheimage", "seedpool_cdn", "sharex", "utppm"]
                                and new_size > 75000
                            ):
                                logger.info(f"[green]Successfully retaken screenshot for: {screenshot_path} ({new_size} bytes)[/green]")
                                valid_image = True

                            if valid_image:
                                valid_results.append(screenshot_path)
                                break
                        except Exception as e:
                            logger.error(f"[red]Error retaking screenshot for {image_path} at {adjusted_time:.2f}s: {e}[/red]")
                    else:
                        continue
                    break
                # Fallback: use random time if original_time is not available
                random_time = random.uniform(0, length)  # nosec B311 - Random screenshot timing, not cryptographic  # noqa: S311
                logger.info(f"[yellow]Retaking screenshot for: {image_path} (Attempt {attempt}/{retry_attempts}) at random time {random_time:.2f}s[/yellow]")
                try:
                    if Path(image_path).exists():
                        Path(image_path).unlink()

                    screenshot_response = await capture_screenshot((original_index, path, random_time, image_path, width, height, w_sar, h_sar, loglevel, hdr_tonemap, meta))

                    if not isinstance(screenshot_response, tuple) or len(screenshot_response) != 2:
                        continue

                    _, screenshot_path = screenshot_response

                    if not screenshot_path or not Path(screenshot_path).exists():
                        continue

                    new_size = Path(screenshot_path).stat().st_size
                    valid_image = False

                    if img_host and "imgbb" in img_host:
                        if 75000 < new_size <= 31000000:
                            valid_image = True
                    elif img_host and img_host in ["imgbox", "pixhost"]:
                        if 75000 < new_size <= 10000000:
                            valid_image = True
                    elif (
                        img_host
                        and img_host in ["lensdump", "ptscreens", "onlyimage", "dalexni", "zipline", "midnightscene", "passtheimage", "seedpool_cdn", "sharex", "utppm"]
                        and new_size > 75000
                    ):
                        valid_image = True

                    if valid_image:
                        valid_results.append(screenshot_path)
                        break
                except Exception as e:
                    logger.error(f"[red]Error retaking screenshot for {image_path} at random time {random_time:.2f}s: {e}[/red]")
            else:
                logger.info(f"[red]All retry attempts failed for {image_path}. Skipping.[/red]")
                remaining_retakes.append(image_path)
                gc.collect()

        else:
            valid_results.append(image_path)

    if remaining_retakes:
        logger.info(f"[red]The following images could not be retaken successfully: {remaining_retakes}[/red]")

    logger.debug(f"[green]Successfully processed {len(valid_results)} screenshots.")

    if meta.debug:
        finish_time = time.time()
        logger.debug(f"Screenshots processed in {finish_time - start_time:.4f} seconds")

    multi_screens = int(default_config.get("multiScreens", 2))
    discs = meta.discs
    one_disc = True
    if discs and len(discs) == 1:
        one_disc = True
    elif discs and len(discs) > 1:
        one_disc = False

    if cleanup_after_capture and ((not meta.tv_pack and one_disc) or multi_screens == 0):
        await cleanup_manager.cleanup()

    complete_progress(
        progress_id,
        progress_label,
        current=num_capture,
        total=num_capture,
        detail=f"{len(valid_results)}/{num_capture} frames captured",
        group="media",
        unit="frames",
    )

    new_screens = register_screenshots(base_dir, folder_id, valid_results, group) if valid_results else []
    if not force_screenshots and not meta.retake:
        return [str(screen) for screen in manifest_files(base_dir, folder_id, group)[:requested_screens]]
    return [str(screen) for screen in new_screens] or None


async def capture_screenshot(args: tuple[int, str, float, str, float, float, float, float, str, bool, Meta]) -> tuple[int, str | None] | None:
    index, path, ss_time, image_path, width, height, w_sar, h_sar, loglevel, hdr_tonemap, meta = args

    try:

        def set_ffmpeg_threads() -> list[str]:
            threads_value = "1"
            return ["-threads", threads_value]

        if width <= 0 or height <= 0:
            return None

        if ss_time < 0:
            return None

        scaled_w = round_to_even(width * w_sar)
        scaled_h = round_to_even(height * h_sar)

        # Normalize path for cross-platform compatibility
        path = os.path.normpath(path)

        # If path is a directory and meta has a filelist, use the first file from the filelist
        if Path(path).is_dir():
            error_msg = f"Error: Path is a directory, not a file: {path}"
            logger.info(f"[yellow]{error_msg}[/yellow]")

            # Use meta that's passed directly to the function
            if "filelist" in meta and meta.filelist:
                video_file = meta.filelist[0]
                logger.info(f"[green]Using first file from filelist: {video_file}[/green]")
                path = video_file
            else:
                return None

        # After potential path correction, validate again
        if not Path(path).exists():
            error_msg = f"Error: Input file does not exist: {path}"
            logger.info(f"[red]{error_msg}[/red]")
            return None

        # Debug output showing the exact path being used
        if loglevel == "verbose" or (meta and meta.debug):
            logger.info(f"[cyan]Processing file: {path}[/cyan]")

        if not meta.frame_overlay:
            # Warm-up (only for first screenshot index or if not warmed)
            if use_libplacebo:
                warm_up = default_config.get("ffmpeg_warmup", False)
                if warm_up:
                    meta.libplacebo_warmed = False
                else:
                    meta.libplacebo_warmed = True
                if not meta.libplacebo_warmed:
                    meta.libplacebo_warmed = False
                if hdr_tonemap and meta.libplacebo and not meta.libplacebo_warmed:
                    await libplacebo_warmup(path, meta, loglevel)

            threads_value = set_ffmpeg_threads()
            threads_val = threads_value[1]
            vf_filters: list[str] = []

            if w_sar != 1 or h_sar != 1:
                scaled_w = round_to_even(width * w_sar)
                scaled_h = round_to_even(height * h_sar)
                vf_filters.append(f"scale={scaled_w}:{scaled_h}")
                if loglevel == "verbose" or (meta and meta.debug):
                    logger.info(f"[cyan]Applied PAR scale -> {scaled_w}x{scaled_h}[/cyan]")

            if hdr_tonemap:
                if meta.libplacebo:
                    vf_filters.append("libplacebo=tonemapping=hable:colorspace=bt709:color_primaries=bt709:color_trc=bt709:range=tv")
                    if loglevel == "verbose" or (meta and meta.debug):
                        logger.info("[cyan]Using libplacebo tonemapping[/cyan]")
                else:
                    vf_filters.extend(
                        [
                            "zscale=transfer=linear",
                            f"tonemap=tonemap={algorithm}:desat={desat}",
                            "zscale=transfer=bt709",
                            "format=rgb24",
                        ]
                    )
                    if loglevel == "verbose" or (meta and meta.debug):
                        logger.info(f"[cyan]Using zscale tonemap chain (algo={algorithm}, desat={desat})[/cyan]")

            vf_filters.append("format=rgb24")
            vf_chain = ",".join(vf_filters) if vf_filters else "format=rgb24"

            if loglevel == "verbose" or (meta and meta.debug):
                logger.info(f"[cyan]Final -vf chain: {vf_chain}[/cyan]")

            threads_value = ["-threads", "1"]
            threads_val = threads_value[1]

            def build_cmd(use_libplacebo: bool = True) -> Any:
                inp = cast(Any, ffmpeg).input(path, ss=str(ss_time))
                # Build output and global args
                out_kwargs = {"vframes": 1, "vf": vf_chain, "compression_level": ffmpeg_compression, "pred": "mixed"}
                info_cmd = inp.output(image_path, **out_kwargs)

                global_args = ["-y", "-loglevel", loglevel, "-hide_banner", "-map", "0:v:0", "-an", "-sn"]
                if use_libplacebo and meta.libplacebo:
                    global_args += ["-init_hw_device", "vulkan"]
                if ffmpeg_limit:
                    global_args += ["-threads", threads_val]

                return info_cmd.global_args(*global_args)

            cmd = build_cmd(use_libplacebo=True)

            if loglevel == "verbose" or (meta and meta.debug):
                # Disable emoji translation so 0:v:0 stays literal
                try:
                    compiled = compile_ffmpeg_command(cmd)
                    logger.info(f"[cyan]FFmpeg command: {' '.join(compiled)}[/cyan]")
                except Exception:
                    logger.info("[cyan]FFmpeg command: (unable to render command)[/cyan]")

            # --- Execute with retry/fallback if libplacebo fails ---
            async def run_cmd(info_command: Any, timeout_sec: float) -> tuple[int | None, bytes, bytes]:
                try:
                    return await asyncio.wait_for(run_ffmpeg(info_command), timeout=timeout_sec)
                except TimeoutError:
                    return -1, b"", b"Timeout"

            info_cmd = build_cmd(use_libplacebo=True)
            if loglevel == "verbose" or (meta and meta.debug):
                logger.info(f"[cyan]FFmpeg command: {' '.join(compile_ffmpeg_command(info_cmd))}[/cyan]")

            returncode, stdout, stderr = await run_cmd(info_cmd, 140)  # a bit longer for first pass
            if returncode != 0 and hdr_tonemap and meta.libplacebo:
                # Retry once (shader compile might have delayed first invocation)
                if loglevel == "verbose" or meta.debug:
                    logger.info("[yellow]First libplacebo attempt failed; retrying once...[/yellow]")
                await asyncio.sleep(1.0)
                returncode, stdout, stderr = await run_cmd(info_cmd, 160)

            if returncode != 0 and hdr_tonemap and meta.libplacebo:
                # Fallback: switch to zscale tonemap chain
                if loglevel == "verbose" or meta.debug:
                    logger.info("[red]libplacebo failed twice; falling back to zscale tonemap[/red]")
                meta.libplacebo = False
                # Rebuild chain with zscale
                z_vf_filters: list[str] = []
                if w_sar != 1 or h_sar != 1:
                    z_vf_filters.append(f"scale={scaled_w}:{scaled_h}")
                z_vf_filters.extend(["format=rgb24", "zscale=transfer=linear", f"tonemap=tonemap={algorithm}:desat={desat}", "zscale=transfer=bt709"])
                vf_chain = ",".join(z_vf_filters)
                info_cmd = build_cmd(use_libplacebo=False)
                if loglevel == "verbose" or meta.debug:
                    logger.info(f"[cyan]Fallback FFmpeg command: {' '.join(compile_ffmpeg_command(info_cmd))}[/cyan]")
                returncode, stdout, stderr = await run_cmd(info_cmd, 140)
                cmd = info_cmd  # for logging below

            if returncode == 0 and Path(image_path).exists():
                if loglevel == "verbose" or (meta and meta.debug):
                    logger.info(f"[green]Screenshot captured successfully: {image_path}[/green]")
                return (index, image_path)
            if loglevel == "verbose" or (meta and meta.debug):
                err_txt = (stderr or b"").decode(errors="replace").strip()
                logger.info(f"[red]FFmpeg process failed (final): {err_txt}[/red]")
            return (index, None)

        # Proceed with screenshot capture
        threads_value = set_ffmpeg_threads()
        threads_val = threads_value[1]

        # Build filter chain
        vf_filters: list[str] = []

        if w_sar != 1 or h_sar != 1:
            scaled_w = round_to_even(width * w_sar)
            scaled_h = round_to_even(height * h_sar)
            vf_filters.append(f"scale={scaled_w}:{scaled_h}")

        if hdr_tonemap:
            vf_filters.extend(
                [
                    "zscale=transfer=linear",
                    f"tonemap=tonemap={algorithm}:desat={desat}",
                    "zscale=transfer=bt709",
                    "format=rgb24",
                ]
            )

        if meta.frame_overlay:
            # Get frame info from pre-collected data if available
            frame_info = meta.frame_info_map.get(str(ss_time), {})

            frame_rate = meta.frame_rate if meta.frame_rate is not None else 24.0
            frame_number = int(ss_time * frame_rate)

            # If we have PTS time from frame info, use it to calculate a more accurate frame number
            if "pts_time" in frame_info:
                # Only use PTS time for frame number calculation if it makes sense
                # (sometimes seeking can give us a frame from the beginning instead of where we want)
                pts_time = frame_info.get("pts_time", 0)
                if pts_time > 1.0 and abs(pts_time - ss_time) < 10:
                    frame_number = int(pts_time * frame_rate)

            frame_type = frame_info.get("frame_type", "Unknown")

            text_size = int(default_config.get("overlay_text_size", 18))
            # Get the resolution and convert it to integer
            resol = int("".join(filter(str.isdigit, (meta.resolution if meta.resolution is not None else "1080p"))))
            font_size = round(text_size * resol / 1080)
            border_width = round(2 * resol / 1080)
            x_all = round(10 * resol / 1080)

            # Scale vertical spacing based on font size
            line_spacing = round(font_size * 1.1)
            y_number = x_all
            y_type = y_number + line_spacing
            y_hdr = y_type + line_spacing

            # Frame number
            vf_filters.append(
                f"drawtext=text='Frame Number\\: {frame_number}':fontcolor=white:fontsize={font_size}:x={x_all}:y={y_number}:borderw={border_width}:bordercolor=black"
            )

            # Frame type
            vf_filters.append(f"drawtext=text='Frame Type\\: {frame_type}':fontcolor=white:fontsize={font_size}:x={x_all}:y={y_type}:borderw={border_width}:bordercolor=black")

            # HDR status
            if hdr_tonemap:
                vf_filters.append(f"drawtext=text='Tonemapped HDR':fontcolor=white:fontsize={font_size}:x={x_all}:y={y_hdr}:borderw={border_width}:bordercolor=black")

        # Build command
        # Always ensure at least format filter is present for PNG compression to work
        vf_filters.append("format=rgb24")
        vf_chain = ",".join(vf_filters)

        try:
            info_cmd: Any = (
                cast(Any, ffmpeg)
                .input(path, ss=str(ss_time))
                .output(image_path, vframes=1, vf=vf_chain, compression_level=ffmpeg_compression, pred="mixed")
                .global_args("-y", "-loglevel", loglevel, "-hide_banner", "-map", "0:v:0", "-an", "-sn")
            )
            if ffmpeg_limit:
                info_cmd = info_cmd.global_args("-threads", threads_val)

            if loglevel == "verbose":
                logger.info(f"[cyan]FFmpeg command: {' '.join(compile_ffmpeg_command(info_cmd))}[/cyan]")

            returncode, stdout, stderr = await run_ffmpeg(info_cmd)
            # Print stdout and stderr if in verbose mode
            if loglevel == "verbose":
                if stdout:
                    logger.info(f"[blue]FFmpeg stdout:[/blue]\n{stdout.decode('utf-8', errors='replace')}")
                if stderr:
                    logger.info(f"[yellow]FFmpeg stderr:[/yellow]\n{stderr.decode('utf-8', errors='replace')}")

        except asyncio.CancelledError:
            logger.info(traceback.format_exc())
            raise

        if returncode == 0:
            return (index, image_path)
        stderr_text = (stderr or b"").decode("utf-8", errors="replace")
        if "Error initializing complex filters" in stderr_text:
            logger.info("[red]FFmpeg complex filters error: see https://github.com/Audionut/Upload-Assistant/wiki/ffmpeg---max-workers-issues[/red]")
        else:
            logger.info(f"[red]FFmpeg error capturing screenshot: {stderr_text}[/red]")
        return (index, None)
    except Exception:
        logger.info(traceback.format_exc())
        return None


async def valid_ss_time(ss_times: list[str], num_screens: int, length: float, frame_rate: float, meta: Meta, retake: bool = False) -> list[str]:
    total_screens = num_screens + 1 if meta.is_disc else num_screens
    total_frames = int(length * frame_rate)

    # Track retake calls and adjust start frame accordingly
    retake_offset = 0
    if retake:
        if meta.retake_call_count is None:
            meta.retake_call_count = 0

        meta.retake_call_count += 1
        retake_offset = meta.retake_call_count * 0.01

        logger.debug(f"[cyan]Retake call #{meta.retake_call_count}, adding {retake_offset:.1%} offset[/cyan]")

    # Calculate usable portion (from 1% to 90% of video)
    if meta.category == "TV" and retake:
        start_frame = int(total_frames * (0.1 + retake_offset))
        end_frame = int(total_frames * 0.9)
    elif meta.category == "Movie" and retake:
        start_frame = int(total_frames * (0.05 + retake_offset))
        end_frame = int(total_frames * 0.9)
    else:
        start_frame = int(total_frames * (0.05 + retake_offset))
        end_frame = int(total_frames * 0.9)

    # Ensure start_frame doesn't exceed reasonable bounds
    max_start_frame = int(total_frames * 0.4)  # Don't start beyond 40%
    start_frame = min(start_frame, max_start_frame)

    usable_frames = end_frame - start_frame
    chosen_frames: list[int] = []

    frame_interval = usable_frames // total_screens if total_screens > 1 else usable_frames

    result_times: list[str] = ss_times.copy()

    for i in range(total_screens):
        frame = start_frame + (i * frame_interval)
        chosen_frames.append(frame)
        time = frame / frame_rate
        result_times.append(str(time))

    logger.debug(f"[purple]Screenshots information:[/purple] \n[slate_blue3]Screenshots: [gold3]{total_screens}[/gold3] \nTotal Frames: [gold3]{total_frames}[/gold3]")
    logger.debug(
        f"[slate_blue3]Start frame: [gold3]{start_frame}[/gold3] \nEnd frame: [gold3]{end_frame}[/gold3] \nUsable frames: [gold3]{usable_frames}[/gold3][/slate_blue3]"
    )
    logger.debug(f"[yellow]frame interval: {frame_interval} \n[purple]Chosen Frames[/purple]\n[gold3]{chosen_frames}[/gold3]\n")

    return sorted(result_times)


async def get_frame_info(path: str, ss_time: str | float, meta: Meta) -> dict[str, Any]:
    """Get frame information (type, exact timestamp) for a specific frame"""
    try:
        ss_time_value = float(ss_time)
        ffmpeg_module = cast(Any, ffmpeg)
        info_ff = ffmpeg_module.input(path, ss=ss_time_value)
        # Use video stream selector and apply showinfo filter
        filtered = info_ff["v:0"].filter("showinfo")
        info_command = filtered.output("-", format="null", vframes=1).global_args("-loglevel", "info")

        # Print the actual FFmpeg command for debugging
        cmd = compile_ffmpeg_command(info_command)
        logger.debug(f"[cyan]FFmpeg showinfo command: {' '.join(cmd)}[/cyan]")

        returncode, _, stderr = await run_ffmpeg(info_command)
        # Check if subprocess completed properly
        if returncode is None:
            cmd_str = " ".join(cmd)
            raise RuntimeError(f"FFmpeg subprocess did not complete properly. The process may have been terminated unexpectedly or failed to start. Command: {cmd_str}")
        stderr_text = stderr.decode("utf-8", errors="replace")

        # Calculate frame number based on timestamp and framerate
        frame_rate = meta.frame_rate if meta.frame_rate is not None else 24.0
        calculated_frame = int(ss_time_value * frame_rate)

        # Default values
        frame_info: dict[str, Any] = {"frame_type": "Unknown", "frame_number": calculated_frame}

        pict_type_match = re.search(r"pict_type:(\w)", stderr_text)
        if pict_type_match:
            frame_info["frame_type"] = pict_type_match.group(1)
        else:
            # Try alternative patterns that might appear in newer FFmpeg versions
            alt_match = re.search(r"type:(\w)\s", stderr_text)
            if alt_match:
                frame_info["frame_type"] = alt_match.group(1)

        pts_time_match = re.search(r"pts_time:(\d+\.\d+)", stderr_text)
        if pts_time_match:
            exact_time = float(pts_time_match.group(1))
            frame_info["pts_time"] = exact_time
            # Recalculate frame number based on exact PTS time if available
            frame_info["frame_number"] = int(exact_time * frame_rate)

        return frame_info

    except Exception as e:
        logger.info(f"[yellow]Error getting frame info: {e}. Will use estimated values.[/yellow]")
        logger.debug(traceback.format_exc())
        return {"frame_type": "Unknown", "frame_number": int(float(ss_time) * (meta.frame_rate if meta.frame_rate is not None else 24.0))}


async def check_libplacebo_compatibility(
    w_sar: float, h_sar: float, width: float, height: float, path: str, ss_time: str, image_path: str, loglevel: str, meta: Meta
) -> tuple[bool, bool]:
    test_image_path = image_path.replace(".png", "_test.png")

    async def run_check(
        w_sar: float,
        h_sar: float,
        width: float,
        height: float,
        path: str,
        ss_time: str,
        _image_path: str,
        loglevel: str,
        meta: Meta,
        try_libplacebo: bool = False,
        test_image_path: str = "",
    ) -> bool:
        filter_parts: list[str] = []
        input_label = "[0:v]"
        output_map = "0:v"  # Default output mapping

        if w_sar != 1 or h_sar != 1:
            scaled_w = round_to_even(width * w_sar)
            scaled_h = round_to_even(height * h_sar)
            filter_parts.append(f"{input_label}scale={scaled_w}:{scaled_h}[scaled]")
            input_label = "[scaled]"
            output_map = "[scaled]"

        # Add libplacebo filter with output label
        if try_libplacebo:
            filter_parts.append(f"{input_label}libplacebo=tonemapping=auto:colorspace=bt709:color_primaries=bt709:color_trc=bt709:range=tv[out]")
            output_map = "[out]"
        else:
            # Use -vf for zscale/tonemap chain, no output label or -map needed
            vf_chain = f"zscale=transfer=linear,tonemap=tonemap={algorithm}:desat={desat},zscale=transfer=bt709,format=rgb24"

        # Build ffmpeg-python command and run
        if try_libplacebo:
            info_cmd: Any = (
                cast(Any, ffmpeg)
                .input(path, ss=ss_time)
                .output(test_image_path, vframes=1, pix_fmt="rgb24")
                .global_args("-y", "-loglevel", "quiet", "-init_hw_device", "vulkan", "-filter_complex", ",".join(filter_parts), "-map", output_map)
            )
        else:
            vf_chain = f"zscale=transfer=linear,tonemap=tonemap={algorithm}:desat={desat},zscale=transfer=bt709,format=rgb24"
            info_cmd: Any = cast(Any, ffmpeg).input(path, ss=ss_time).output(test_image_path, vframes=1, vf=vf_chain, pix_fmt="rgb24").global_args("-y", "-loglevel", "quiet")

        if loglevel == "verbose" or (meta and meta.debug):
            logger.info(f"[cyan]libplacebo compatibility test command: {' '.join(compile_ffmpeg_command(info_cmd))}[/cyan]")

        try:
            retcode, _stdout, _stderr = await run_ffmpeg(info_cmd)
            return retcode == 0
        except Exception:
            return False

    if not meta.is_disc:
        is_libplacebo_compatible = await run_check(w_sar, h_sar, width, height, path, ss_time, image_path, loglevel, meta, try_libplacebo=True, test_image_path=test_image_path)
        if is_libplacebo_compatible:
            logger.debug("[green]libplacebo compatibility test succeeded[/green]")
            with contextlib.suppress(Exception):
                if Path(test_image_path).exists():
                    Path(test_image_path).unlink()
            return True, True
        can_hdr = await run_check(w_sar, h_sar, width, height, path, ss_time, image_path, loglevel, meta, try_libplacebo=False, test_image_path=test_image_path)
        if can_hdr:
            logger.debug("[yellow]libplacebo compatibility test failed, but zscale HDR tonemapping is compatible[/yellow]")
            # Clean up the test image regardless of success/failure
            with contextlib.suppress(Exception):
                if Path(test_image_path).exists():
                    Path(test_image_path).unlink()
            return False, True
    return False, False


async def libplacebo_warmup(path: str, meta: Meta, loglevel: str) -> None:
    if not meta.libplacebo or meta.libplacebo_warmed:
        return
    if not Path(path).exists():
        return
    # Use a very small seek (0.1s) to avoid issues at pts 0
    info_cmd: Any = (
        cast(Any, ffmpeg)
        .input(path, ss="0.1")
        .output("-", format="null", vframes=1)
        .global_args(
            "-map",
            "0:v:0",
            "-an",
            "-sn",
            "-init_hw_device",
            "vulkan",
            "-vf",
            "libplacebo=tonemapping=hable:colorspace=bt709:color_primaries=bt709:color_trc=bt709:range=tv,format=rgb24",
            "-loglevel",
            "error",
        )
    )
    if loglevel == "verbose" or meta.debug:
        logger.info("[cyan]Running libplacebo warm-up...[/cyan]")
    try:
        try:
            await run_ffmpeg(info_cmd)
        except Exception:
            # Warmup failures are non-fatal; continue
            if loglevel == "verbose" or meta.debug:
                logger.info("[yellow]libplacebo warm-up failed or errored (continuing anyway)[/yellow]")
        meta.libplacebo_warmed = True
    except Exception as e:
        if loglevel == "verbose" or meta.debug:
            logger.info(f"[yellow]libplacebo warm-up failed: {e} (continuing)[/yellow]")


async def get_image_host(meta: Meta) -> str | None:
    if meta.imghost is not None:
        host = meta.imghost

        if isinstance(host, str):
            return host.lower().strip()

        if isinstance(host, list):
            host_list = cast(list[Any], host)
            for item in host_list:
                if item and isinstance(item, str):
                    return item.lower().strip()
    else:
        img_host_config: list[str] = [str(default_config[key]).lower() for key in sorted(default_config.keys()) if key.startswith("img_host_1") and not key.endswith("0")]
        if img_host_config:
            return img_host_config[0]
    return None


class TakeScreensManager:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        _apply_config(config)

    async def run_ffmpeg(self, command: Any) -> tuple[int | None, bytes, bytes]:
        return await run_ffmpeg(command)

    async def sanitize_filename(self, filename: str) -> str:
        return await sanitize_filename(filename)

    async def disc_screenshots(
        self,
        meta: Meta,
        filename: str,
        bdinfo: dict[str, Any],
        folder_id: str,
        base_dir: str,
        use_vs: bool,
        image_list: list[dict[str, str]] | None = None,
        ffdebug: bool = False,
        num_screens: int = 0,
        force_screenshots: bool = False,
        cleanup_after_capture: bool = True,
        capture_group: str | None = None,
    ) -> list[Path]:
        return await disc_screenshots(
            meta, filename, bdinfo, folder_id, base_dir, use_vs, image_list, ffdebug, num_screens, force_screenshots, cleanup_after_capture, capture_group
        )

    async def capture_disc_task(
        self, index: int, file: str, ss_time: str, image_path: str, keyframe: str, loglevel: str, hdr_tonemap: bool, meta: Meta
    ) -> tuple[int, str] | None:
        return await capture_disc_task(index, file, ss_time, image_path, keyframe, loglevel, hdr_tonemap, meta)

    async def dvd_screenshots(
        self,
        meta: Meta,
        disc_num: int,
        num_screens: int = 0,
        retry_cap: bool = False,
        cleanup_after_capture: bool = True,
    ) -> None:
        await dvd_screenshots(meta, disc_num, num_screens, retry_cap, cleanup_after_capture)

    async def capture_dvd_screenshot(self, task: tuple[int, str, str, str, Meta, float, float, float, float]) -> tuple[int, str | None]:
        return await capture_dvd_screenshot(task)

    async def screenshots(
        self,
        path: str,
        filename: str,
        folder_id: str,
        base_dir: str,
        meta: Meta,
        num_screens: int = 0,
        force_screenshots: bool = False,
        manual_frames: str | list[int] | list[str] = "",
        cleanup_after_capture: bool = True,
        capture_group: str | None = None,
    ) -> list[str] | None:
        return await screenshots(path, filename, folder_id, base_dir, meta, num_screens, force_screenshots, manual_frames, cleanup_after_capture, capture_group)

    async def prepare_book_cover(self, path: str, folder_id: str, base_dir: str, meta: Meta) -> str | None:
        return await prepare_book_cover(path, folder_id, base_dir, meta)

    async def capture_screenshot(self, args: tuple[int, str, float, str, float, float, float, float, str, bool, Meta]) -> tuple[int, str | None] | None:
        return await capture_screenshot(args)

    async def valid_ss_time(self, ss_times: list[str], num_screens: int, length: float, frame_rate: float, meta: Meta, retake: bool = False) -> list[str]:
        return await valid_ss_time(ss_times, num_screens, length, frame_rate, meta, retake)

    async def get_frame_info(self, path: str, ss_time: str, meta: Meta) -> dict[str, Any]:
        return await get_frame_info(path, ss_time, meta)

    async def check_libplacebo_compatibility(
        self, w_sar: float, h_sar: float, width: float, height: float, path: str, ss_time: str, image_path: str, loglevel: str, meta: Meta
    ) -> tuple[bool, bool]:
        return await check_libplacebo_compatibility(w_sar, h_sar, width, height, path, ss_time, image_path, loglevel, meta)

    async def libplacebo_warmup(self, path: str, meta: Meta, loglevel: str) -> None:
        await libplacebo_warmup(path, meta, loglevel)

    async def get_image_host(self, meta: Meta) -> str | None:
        return await get_image_host(meta)
