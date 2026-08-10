import asyncio
import contextlib
import json
import platform
import re
from collections.abc import Mapping, MutableMapping, Sequence
from pathlib import Path
from typing import Any, cast

from PIL import Image
from pymediainfo import MediaInfo

from src.console import logger
from src.meta import Meta
from src.takescreens import screenshot_par_scale_factors, should_scale_screenshots_for_par
from src.temp_paths import menu_screenshots_dir
from src.uploadscreens import UploadScreensManager


def select_evenly_spaced(items: list[Any], num_to_select: int) -> list[Any]:
    if len(items) <= num_to_select:
        return items
    if num_to_select <= 0:
        return []
    if num_to_select == 1:
        return [items[0]]

    indices = [(round(i * (len(items) - 1) / (num_to_select - 1))) for i in range(num_to_select)]
    # Ensure indices are unique and sorted
    unique_indices = sorted(set(indices))

    # Fill in any missing slots in rare rounding edge cases
    if len(unique_indices) < num_to_select:
        all_indices = set(range(len(items)))
        needed = num_to_select - len(unique_indices)
        available = sorted(all_indices - set(unique_indices))
        unique_indices.extend(available[:needed])
        unique_indices.sort()

    return [items[idx] for idx in unique_indices]


def discard_previous_menu_capture_files(image_pattern: Path) -> None:
    """Remove only prior output for the menu VOB about to be captured."""
    glob_name = image_pattern.name.replace("%03d", "*")
    for image_path in image_pattern.parent.glob(glob_name):
        with contextlib.suppress(OSError):
            image_path.unlink()


class DiscMenus:
    """
    Handles the processing and uploading of disc menu images.
    """

    def __init__(self, meta: Meta, config: MutableMapping[str, Any]):
        self.config = config
        self.path_to_menu_screenshots = meta.path_to_menu_screenshots or ""
        self.uploadscreens_manager = UploadScreensManager(cast(dict[str, Any], config))

    async def get_disc_menu_images(self, meta: Meta) -> None:
        """
        Processes disc menu images from a local directory and uploads them.
        """
        if not self.path_to_menu_screenshots:
            default_section = self.config.get("DEFAULT", {})
            if hasattr(default_section, "get") and default_section.get("auto_dvd_menus", False):
                self.path_to_menu_screenshots = "auto"
            else:
                return

        if self.path_to_menu_screenshots.lower() == "auto":
            await self.auto_capture_dvd_menus(meta)
        elif Path(self.path_to_menu_screenshots).is_dir():
            await self.get_local_images(meta)
        else:
            logger.info(f"[red]Invalid disc menus path: {self.path_to_menu_screenshots}[/red]")

    async def auto_capture_dvd_menus(self, meta: Meta) -> None:
        """
        Automatically captures screenshots of DVD menus from VOB files and uploads them.
        HD-DVD menus are skipped and warning is logged.
        """
        # Check if there are any supported discs in metadata
        has_supported_discs = any(disc.get("type") in ("DVD", "HDDVD") for disc in meta.discs)
        if not has_supported_discs:
            logger.debug("No supported DVD/HDDVD discs found in metadata; skipping menu auto-capture.")
            return

        # Load max_menu_screens from config
        default_section = self.config.get("DEFAULT", {})
        try:
            max_menu_screens = int(default_section.get("max_menu_screens", 6))
        except ValueError, TypeError:
            max_menu_screens = 6
        screenshot_config = cast(Mapping[str, Any], default_section) if isinstance(default_section, Mapping) else {}
        scale_for_par = should_scale_screenshots_for_par(screenshot_config)

        captured_images = []
        output_dir = menu_screenshots_dir(meta.base_dir, meta.uuid)

        # Get ffmpeg path
        ffmpeg_path = "ffmpeg"
        if platform.system() == "Linux":
            ff_bin_dir = Path(meta.base_dir) / "bin" / "ffmpeg"
            machine = platform.machine().lower()
            arch = "amd" if machine in ("x86_64", "amd64") else ("arm" if machine in ("aarch64", "arm64") else None)
            if arch:
                candidate = Path(ff_bin_dir) / arch / "ffmpeg"
                if Path(candidate).exists():
                    ffmpeg_path = candidate

        def round_to_even(value: float) -> int:
            rounded = round(value)
            if rounded % 2 != 0:
                rounded += 1
            return rounded

        for disc in meta.discs:
            disc_type = disc.get("type")
            if disc_type == "HDDVD":
                logger.warning(f"[yellow]HD-DVD menu capture is not supported. Skipping HD-DVD: {disc.get('name', 'Unknown')}[/yellow]")
                continue
            if disc_type != "DVD":
                continue

            disc_path = disc.get("path")
            if not disc_path or not Path(disc_path).is_dir():
                continue

            # List and filter menu files
            menu_files = []
            try:
                for file in (p.name for p in Path(disc_path).iterdir()):
                    file_lower = file.lower()
                    if disc_type == "DVD" and file_lower.endswith(".vob"):
                        file_name = file.upper()
                        if file_name == "VIDEO_TS.VOB" or re.match(r"^VTS_\d{2}_0\.VOB$", file_name):
                            file_path = Path(disc_path) / file
                            if file_path.is_file() and Path(file_path).stat().st_size > 50000:
                                menu_files.append((file, file_path))
            except Exception as e:
                logger.error(f"[red]Error scanning directory {disc_path} for menus: {e}[/red]")
                continue

            # Sort alphabetically to process deterministically
            menu_files.sort(key=lambda x: x[0].upper())

            for file, file_path in menu_files:
                try:
                    mi = MediaInfo.parse(file_path)
                    video_track = None
                    for track in mi.tracks:
                        if track.track_type == "Video":
                            video_track = track
                            break
                    if not video_track:
                        logger.debug(f"Skipping {file} because it does not have a video track.")
                        continue

                    # Extract details
                    width = int(video_track.width) if video_track.width else 720
                    height = int(video_track.height) if video_track.height else 480
                    par = float(video_track.pixel_aspect_ratio) if video_track.pixel_aspect_ratio else 1.0
                    dar = float(video_track.display_aspect_ratio) if video_track.display_aspect_ratio else 1.3333
                    duration_ms = video_track.duration
                except Exception as e:
                    logger.error(f"[red]Error parsing MediaInfo for {file}: {e}[/red]")
                    width, height, par, dar, duration_ms = 720, 480, 1.0, 1.3333, None

                w_sar, h_sar = screenshot_par_scale_factors(width, height, par, dar, scale_for_par)

                # Determine duration
                duration_sec = 0.0
                if duration_ms:
                    with contextlib.suppress(ValueError, TypeError):
                        duration_sec = float(duration_ms) / 1000.0

                vf_filters = []
                if duration_sec < 2.0:
                    vf_filters.append("mpdecimate")

                if w_sar != 1 or h_sar != 1:
                    scaled_w = round_to_even(width * w_sar)
                    scaled_h = round_to_even(height * h_sar)
                    vf_filters.append(f"scale={scaled_w}:{scaled_h}")

                vf_filters.append("format=rgb24")
                vf_chain = ",".join(vf_filters)

                # Setup output file patterns
                sanitized_disc_name = re.sub(r'[<>:"/\\|?*]', "_", disc.get("name", "dvd"))
                vob_base = Path(file).stem
                image_pattern = Path(output_dir) / f"{sanitized_disc_name}-{vob_base}-%03d.png"
                discard_previous_menu_capture_files(image_pattern)

                # Run ffmpeg
                if duration_sec < 2.0:
                    # Static menu: extract all distinct frames up to a safety limit
                    limit = max(10, max_menu_screens)
                    cmd = [ffmpeg_path, "-y", "-t", "5.0", "-i", str(file_path), "-vf", vf_chain, "-fps_mode", "passthrough", "-vframes", str(limit), str(image_pattern)]
                    logger.info(f"Extracting static menu frames from {file} (limit: {limit})...")
                else:
                    # Motion menu: try scene detection first
                    limit = max(30, max_menu_screens * 3)
                    scene_vf_chain = ",".join(["select='gt(scene,0.25)'", *vf_filters])
                    cmd = [ffmpeg_path, "-y", "-i", str(file_path), "-vf", scene_vf_chain, "-fps_mode", "vfr", "-vframes", str(limit), str(image_pattern)]
                    logger.info(f"Extracting motion menu frames via scene detection from {file} (limit: {limit})...")

                logger.debug(f"FFmpeg command: {' '.join(cmd)}")

                try:
                    process = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                    try:
                        _stdout, _stderr = await asyncio.wait_for(process.communicate(), timeout=30.0)
                    except TimeoutError:
                        with contextlib.suppress(Exception):
                            process.kill()
                        _stdout, _stderr = await process.communicate()
                        logger.error(f"[red]FFmpeg timed out processing {file}[/red]")

                    # Gather generated screenshots
                    glob_pattern = Path(output_dir) / f"{sanitized_disc_name}-{vob_base}-*.png"
                    found_images = sorted(str(p) for p in glob_pattern.parent.glob(glob_pattern.name)) if process.returncode == 0 else []
                    if process.returncode != 0:
                        logger.error(f"[red]FFmpeg failed processing {file}: {_stderr.decode(errors='replace')}[/red]")
                        discard_previous_menu_capture_files(image_pattern)

                    # Filter out blank/black frames
                    valid_images = []
                    for img_path in found_images:
                        try:
                            with Image.open(img_path) as img:
                                extrema = img.convert("L").getextrema()
                                if extrema and isinstance(extrema[1], (int, float)) and extrema[1] < 10:
                                    logger.debug(f"Skipping {Path(img_path).name} because it is a blank/black frame.")
                                    Path(img_path).unlink()
                                    continue
                            valid_images.append(img_path)
                        except Exception as e:
                            logger.debug(f"Failed to check if {img_path} is black: {e}")
                            valid_images.append(img_path)
                    found_images = valid_images

                    # Fallback to interval sampling if scene detection yielded nothing for motion menus
                    if duration_sec >= 2.0 and not found_images:
                        logger.info(f"Scene detection returned no valid frames for {file}. Falling back to interval sampling...")
                        fallback_vf_chain = ",".join(["fps=1/5", *vf_filters])
                        cmd_fallback = [
                            ffmpeg_path,
                            "-y",
                            "-ss",
                            "2.0",
                            "-i",
                            str(file_path),
                            "-vf",
                            fallback_vf_chain,
                            "-fps_mode",
                            "vfr",
                            "-vframes",
                            str(max_menu_screens),
                            str(image_pattern),
                        ]
                        logger.debug(f"Fallback FFmpeg command: {' '.join(cmd_fallback)}")
                        discard_previous_menu_capture_files(image_pattern)
                        process_fallback = await asyncio.create_subprocess_exec(*cmd_fallback, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                        try:
                            _fallback_stdout, fallback_stderr = await asyncio.wait_for(process_fallback.communicate(), timeout=30.0)
                        except TimeoutError:
                            with contextlib.suppress(Exception):
                                process_fallback.kill()
                            _fallback_stdout, fallback_stderr = await process_fallback.communicate()
                            logger.error(f"[red]FFmpeg fallback timed out processing {file}[/red]")

                        found_images = sorted(str(p) for p in glob_pattern.parent.glob(glob_pattern.name)) if process_fallback.returncode == 0 else []
                        if process_fallback.returncode != 0:
                            logger.error(f"[red]FFmpeg fallback failed processing {file}: {fallback_stderr.decode(errors='replace')}[/red]")
                            discard_previous_menu_capture_files(image_pattern)
                        valid_images = []
                        for img_path in found_images:
                            try:
                                with Image.open(img_path) as img:
                                    extrema = img.convert("L").getextrema()
                                    if extrema and isinstance(extrema[1], (int, float)) and extrema[1] < 10:
                                        logger.debug(f"Skipping fallback frame {Path(img_path).name} because it is a blank/black frame.")
                                        Path(img_path).unlink()
                                        continue
                                valid_images.append(img_path)
                            except Exception as e:
                                logger.debug(f"Failed to check if fallback frame {img_path} is black: {e}")
                                valid_images.append(img_path)
                        found_images = valid_images

                    # Final retry: if still no images, retry from seek_time = 0
                    if not found_images and duration_sec >= 2.0:
                        logger.debug(f"FFmpeg fallback/scene detection failed for {file}. Retrying from start (seek_time=0).")
                        image_path = Path(output_dir) / f"{sanitized_disc_name}-{vob_base}-001.png"
                        cmd_retry = [ffmpeg_path, "-y", "-i", str(file_path), "-vframes", "1", "-vf", vf_chain, "-update", "1", str(image_path)]
                        process_retry = await asyncio.create_subprocess_exec(*cmd_retry, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                        try:
                            await asyncio.wait_for(process_retry.communicate(), timeout=15.0)
                        except TimeoutError:
                            with contextlib.suppress(Exception):
                                process_retry.kill()
                            await process_retry.communicate()
                            logger.error(f"[red]FFmpeg retry timed out processing {file}[/red]")

                        found_images = sorted(str(p) for p in glob_pattern.parent.glob(glob_pattern.name))
                        valid_images = []
                        for img_path in found_images:
                            try:
                                with Image.open(img_path) as img:
                                    extrema = img.convert("L").getextrema()
                                    if extrema and isinstance(extrema[1], (int, float)) and extrema[1] < 10:
                                        logger.debug(f"Skipping retry frame {Path(img_path).name} because it is a blank/black frame.")
                                        Path(img_path).unlink()
                                        continue
                                valid_images.append(img_path)
                            except Exception as e:
                                logger.debug(f"Failed to check if retry frame {img_path} is black: {e}")
                                valid_images.append(img_path)
                        found_images = valid_images

                    if found_images:
                        logger.info(f"[green]Successfully captured {len(found_images)} menu screenshot(s) for {file}[/green]")
                        captured_images.extend(found_images)
                    else:
                        logger.info(f"[yellow]No valid menu frames captured for {file} (file may contain only blank/black placeholder screens)[/yellow]")
                except Exception as e:
                    logger.error(f"[red]Error running ffmpeg for {file}: {e}[/red]")

        # Apply configurable limit using even spacing
        if len(captured_images) > max_menu_screens:
            logger.info(f"[yellow]Captured {len(captured_images)} screenshots, limiting to {max_menu_screens} (configured by max_menu_screens) using even spacing.[/yellow]")
            keep_images = select_evenly_spaced(captured_images, max_menu_screens)
            keep_set = set(keep_images)
            for img in captured_images:
                if img not in keep_set:
                    with contextlib.suppress(Exception):
                        Path(img).unlink()
            captured_images = keep_images

        if not captured_images:
            logger.info("[yellow]No disc menu images could be auto-captured.[/yellow]")
            return

        # Upload captured images
        logger.info(f"[cyan]Uploading {len(captured_images)} auto-captured disc menu screenshots...[/cyan]")
        uploaded_images, _ = await self.uploadscreens_manager.upload_screens(
            meta, screens=len(captured_images), img_host_num=1, i=0, total_screens=len(captured_images), custom_img_list=captured_images, return_dict={}, retry_mode=False
        )
        meta.menu_images = uploaded_images

        await self.save_images_to_json(meta, uploaded_images)

    async def get_local_images(self, meta: Meta) -> None:
        """
        Uploads disc menu images from a local directory.
        """
        image_paths = [p for p in Path(self.path_to_menu_screenshots).iterdir() if p.name.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))]

        if not image_paths:
            logger.info("[yellow]No local menu images found to upload.[/yellow]")
            return

        uploaded_images, _ = await self.uploadscreens_manager.upload_screens(
            meta, screens=len(image_paths), img_host_num=1, i=0, total_screens=len(image_paths), custom_img_list=image_paths, return_dict={}, retry_mode=False
        )
        meta.menu_images = uploaded_images

        await self.save_images_to_json(meta, uploaded_images)

    async def save_images_to_json(self, meta: Meta, image_list: Sequence[dict[str, Any]]) -> None:
        """
        Saves the uploaded disc menu images to a JSON file.
        """
        if not image_list:
            logger.info("[yellow]No menu images found.[/yellow]")
            return

        menu_images = {"menu_images": list(image_list)}

        base_dir = meta.base_dir
        uuid_value = meta.uuid
        json_path = Path(base_dir) / "tmp" / uuid_value / "menu_images.json"
        json_path.parent.mkdir(parents=True, exist_ok=True)

        menu_json = json.dumps(menu_images, indent=4)
        await asyncio.to_thread(Path(json_path).write_text, menu_json)

        logger.info(f"[green]Saved {len(image_list)} menu images to {json_path}[/green]")


async def process_disc_menus(meta: Meta, config: MutableMapping[str, Any]) -> None:
    """
    Main function to process disc menu images.
    """
    disc_menus = DiscMenus(meta, config)
    await disc_menus.get_disc_menu_images(meta)
