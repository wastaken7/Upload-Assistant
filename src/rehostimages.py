# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import asyncio
import glob
import json
import os
import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlparse

import aiofiles
from aiofiles import os as aio_os

from src.console import logger
from src.meta import Meta
from src.takescreens import TakeScreensManager
from src.type_utils import to_int
from src.uploadscreens import UploadScreensManager


def _as_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _safe_remove(path: str) -> bool:
    try:
        if Path(path).exists():
            Path(path).unlink()
            return True
    except Exception as e:
        logger.info(f"[yellow]Failed to delete file {path}: {e!s}[/yellow]")
    return False


async def match_host(hostname: str, approved_hosts: Iterable[str]) -> str:
    for approved_host in approved_hosts:
        if hostname == approved_host or hostname.endswith(f".{approved_host}"):
            return approved_host
    return hostname


async def sanitize_filename(filename: str) -> str:
    # Replace invalid characters like colons with an underscore
    return re.sub(r'[<>:"/\\|?*]', "_", filename)


class RehostImagesManager:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.default_config = cast(dict[str, Any], config.get("DEFAULT", {}))
        self.takescreens_manager = TakeScreensManager(config)
        self.uploadscreens_manager = UploadScreensManager(config)

    async def check_hosts(
        self,
        meta: Meta,
        tracker: str,
        url_host_mapping: dict[str, str],
        img_host_index: int = 1,
        approved_image_hosts: list[str] | None = None,
    ) -> tuple[list[dict[str, str]], bool, bool]:
        return await _check_hosts(
            meta,
            tracker,
            url_host_mapping,
            img_host_index=img_host_index,
            approved_image_hosts=approved_image_hosts,
            default_config=self.default_config,
            takescreens_manager=self.takescreens_manager,
            uploadscreens_manager=self.uploadscreens_manager,
        )

    async def handle_image_upload(
        self,
        meta: Meta,
        tracker: str,
        url_host_mapping: dict[str, str],
        approved_image_hosts: list[str] | None = None,
        img_host_index: int = 1,
        file: str | None = None,
    ) -> tuple[list[dict[str, str]], bool, bool]:
        return await _handle_image_upload(
            meta,
            tracker,
            url_host_mapping,
            approved_image_hosts=approved_image_hosts,
            img_host_index=img_host_index,
            file=file,
            default_config=self.default_config,
            takescreens_manager=self.takescreens_manager,
            uploadscreens_manager=self.uploadscreens_manager,
        )


async def _check_hosts(
    meta: Meta,
    tracker: str,
    url_host_mapping: dict[str, str],
    img_host_index: int = 1,
    approved_image_hosts: list[str] | None = None,
    default_config: Mapping[str, Any] | None = None,
    takescreens_manager: TakeScreensManager | None = None,
    uploadscreens_manager: UploadScreensManager | None = None,
) -> tuple[list[dict[str, str]], bool, bool]:
    if default_config is None:
        raise ValueError("default_config is required")
    if takescreens_manager is None:
        raise ValueError("takescreens_manager is required")
    if uploadscreens_manager is None:
        raise ValueError("uploadscreens_manager is required")
    if approved_image_hosts is None:
        approved_image_hosts = []
    new_images_key = f"{tracker}_images_key"
    if meta.skip_imghost_upload:
        logger.debug(f"[yellow]Skipping image host upload for {tracker} as per meta.skip_imghost_upload setting.")
        return meta.get(new_images_key, []), False, False
    if new_images_key not in meta:
        meta[new_images_key] = []

    logger.debug(
        f"[cyan]check_hosts debug: tracker={tracker} meta.imghost={meta.imghost} approved_image_hosts={approved_image_hosts} "
        f"image_list={len(meta.image_list or [])} {new_images_key}={len(meta.get(new_images_key, []) or [])}[/cyan]"
    )

    # Check if we have main image_list but no tracker-specific images yet
    if meta.image_list and not meta.get(new_images_key):
        logger.debug(f"[yellow]Checking if existing images in meta.image_list can be used for {tracker}...")
        # Check if the URLs in image_list are from approved hosts
        approved_images: list[dict[str, str]] = []
        need_reupload = False

        image_list_entries = cast(list[dict[str, str]], meta.image_list)
        for image in image_list_entries:
            raw_url = _as_str(image.get("raw_url"))
            if not raw_url:
                continue

            parsed_url = urlparse(raw_url)
            hostname = parsed_url.netloc
            mapped_host = await match_host(hostname, url_host_mapping.keys())

            if mapped_host:
                mapped_host = url_host_mapping.get(mapped_host, mapped_host)
                if mapped_host in approved_image_hosts:
                    approved_images.append(image)
                    logger.debug(f"[green]URL '{raw_url}' is from approved host '{mapped_host}'.")
                else:
                    need_reupload = True
                    logger.debug(f"[yellow]URL '{raw_url}' is not from an approved host for {tracker}.")
            else:
                need_reupload = True

        # If all images are approved, use them directly
        if approved_images and len(approved_images) == len(meta.image_list) and not need_reupload:
            meta[new_images_key] = approved_images.copy()
            logger.debug(f"[green]All existing images are from approved hosts for {tracker}.")
            return meta[new_images_key], False, False

    if tracker == "covers":
        reuploaded_images_path = Path(meta.base_dir) / "tmp" / meta.uuid / "covers.json"
    else:
        reuploaded_images_path = Path(meta.base_dir) / "tmp" / meta.uuid / "reuploaded_images.json"
    reuploaded_images: list[dict[str, str]] = []

    if Path(reuploaded_images_path).exists():
        try:
            async with aiofiles.open(reuploaded_images_path, encoding="utf-8") as f:
                content = await f.read()
                loaded = json.loads(content)
                if isinstance(loaded, list):
                    reuploaded_images = cast(list[dict[str, str]], loaded)
        except Exception as e:
            logger.error(f"[red]Failed to load reuploaded images: {e}")

    valid_reuploaded_images: list[dict[str, str]] = []
    for image in reuploaded_images:
        raw_url = _as_str(image.get("raw_url"))
        if not raw_url:
            continue

        # For covers, verify the release_url matches
        if tracker == "covers" and "release_url" in meta and ("release_url" not in image or image["release_url"] != meta.release_url):
            if meta.debug:
                if "release_url" not in image:
                    logger.debug(f"[yellow]Skipping image without release_url: {raw_url}")
                else:
                    logger.debug(f"[yellow]Skipping image with mismatched release_url: {image['release_url']} != {meta.release_url}")
            continue

        parsed_url = urlparse(raw_url)
        hostname = parsed_url.netloc
        mapped_host = await match_host(hostname, url_host_mapping.keys())

        if mapped_host:
            mapped_host = url_host_mapping.get(mapped_host, mapped_host)
            if mapped_host in approved_image_hosts:
                valid_reuploaded_images.append(image)
            elif meta.debug:
                logger.info(f"[red]URL '{raw_url}' from reuploaded_images.json is not recognized as an approved host.")

    if valid_reuploaded_images:
        meta[new_images_key] = valid_reuploaded_images
        if tracker == "covers":
            logger.info("[green]Using valid images from covers.json.")
        else:
            logger.info("[green]Using valid images from reuploaded_images.json.")
        return meta[new_images_key], False, False

    # Check if the tracker-specific key has valid images
    has_valid_images = False
    if meta.get(new_images_key):
        valid_hosts: list[bool] = []
        tracker_images = cast(list[dict[str, str]], meta.get(new_images_key, []))
        for image in tracker_images:
            raw_url = _as_str(image.get("raw_url")) or ""
            netloc = urlparse(raw_url).netloc
            matched_host = await match_host(netloc, url_host_mapping.keys())
            mapped_host = url_host_mapping.get(matched_host, matched_host)
            valid_hosts.append(mapped_host in approved_image_hosts)

        # Then check if all are valid
        if all(valid_hosts) and meta[new_images_key]:
            has_valid_images = True

    if has_valid_images:
        logger.info(f"[green]Using valid images from {new_images_key}.")
        return meta[new_images_key], False, False

    logger.debug(f"[yellow]No valid images found for {tracker}, will attempt to reupload...")

    images_reuploaded = False
    configured_indices = sorted(int(match.group(1)) for key in default_config if (match := re.fullmatch(r"img_host_(\d+)", key)) and _as_str(default_config.get(key)))
    if not configured_indices:
        return [], True, images_reuploaded

    max_retries = configured_indices[-1]

    while img_host_index <= max_retries:
        image_list, retry_mode, images_reuploaded = await _handle_image_upload(
            meta,
            tracker,
            url_host_mapping,
            approved_image_hosts,
            img_host_index=img_host_index,
            default_config=default_config,
            takescreens_manager=takescreens_manager,
            uploadscreens_manager=uploadscreens_manager,
        )

        if image_list:
            meta[new_images_key] = image_list

        if retry_mode:
            logger.info(f"[yellow]Switching to the next image host. Current index: {img_host_index}")
            img_host_index += 1
            continue  # Retry with next host

        break

    if not meta.get(new_images_key):
        logger.info("[red]All image hosts failed. Please check your configuration.")

    logger.debug(f"[cyan]check_hosts debug: done tracker={tracker} image_list={len(meta.image_list or [])} {new_images_key}={len(meta.get(new_images_key, []) or [])}[/cyan]")

    return meta.get(new_images_key, []), False, images_reuploaded


async def _handle_image_upload(
    meta: Meta,
    tracker: str,
    url_host_mapping: dict[str, str],
    approved_image_hosts: list[str] | None = None,
    img_host_index: int = 1,
    file: str | None = None,
    default_config: Mapping[str, Any] | None = None,
    takescreens_manager: TakeScreensManager | None = None,
    uploadscreens_manager: UploadScreensManager | None = None,
) -> tuple[list[dict[str, str]], bool, bool]:
    if default_config is None:
        raise ValueError("default_config is required")
    if takescreens_manager is None:
        raise ValueError("takescreens_manager is required")
    if uploadscreens_manager is None:
        raise ValueError("uploadscreens_manager is required")
    if approved_image_hosts is None:
        approved_image_hosts = []
    original_imghost = meta.imghost
    retry_mode = False
    images_reuploaded = False
    new_images_key = f"{tracker}_images_key"
    filelist: list[str] = []
    filelist_value = meta.video
    if isinstance(filelist_value, str):
        filelist = [filelist_value]
    elif isinstance(filelist_value, list):
        filelist = [str(item) for item in filelist_value if item]
    filename = meta.title
    if meta.is_disc == "HDDVD":
        path = str(meta.discs[0].get("largest_evo", ""))
    else:
        path_list = meta.filelist
        path = str(path_list[0]) if path_list else ""

    default_screens = to_int(default_config.get("screens", 6), 6)
    multi_screens = to_int(meta.screens, default_screens)
    base_dir = meta.base_dir
    folder_id = meta.uuid
    meta[new_images_key] = []

    screenshots_dir = Path(base_dir) / "tmp" / folder_id
    logger.debug(f"[yellow]Searching for screenshots in {screenshots_dir}...")
    all_screenshots: list[str] = []

    # First check if there are any saved screenshots matching those in the image_list
    if meta.image_list and isinstance(meta.image_list, list):
        # Get all PNG files in the screenshots directory
        all_png_files: list[str] = [str(screenshots_dir / name) for name in await aio_os.listdir(screenshots_dir) if name.endswith(".png")]
        if all_png_files and meta.debug:
            logger.info(f"[cyan]Found {len(all_png_files)} PNG files in screenshots directory")

        # Extract filenames from the image_list
        image_filenames: list[str] = []
        for image in cast(list[dict[str, str]], meta.image_list):
            for url_key in ["raw_url", "img_url", "web_url"]:
                url_value = _as_str(image.get(url_key))
                if url_value:
                    parsed_url = urlparse(url_value)
                    filename_from_url = Path(parsed_url.path).name
                    if filename_from_url and filename_from_url.lower().endswith(".png"):
                        image_filenames.append(filename_from_url)
                        break

        if image_filenames and meta.debug:
            logger.info(f"[cyan]Extracted {len(image_filenames)} filenames from image_list URLs: {image_filenames}")

        # Check if any of the extracted filenames match the actual files in the directory
        if all_png_files and image_filenames:
            for png_file in all_png_files:
                basename = Path(png_file).name
                if basename in image_filenames:
                    # Found a match for this filename
                    all_screenshots.append(png_file)
                    logger.debug(f"[green]Found existing screenshot matching URL: {basename}")

        # Also check for any screenshots that match the title pattern as a fallback
        if filename and len(all_screenshots) < multi_screens:
            sanitized_title = await sanitize_filename(filename)
            title_pattern_files = [f for f in all_png_files if Path(f).name.startswith(sanitized_title)]
            logger.debug(f"[yellow]Searching for screenshots with pattern: {sanitized_title}*.png")
            if title_pattern_files:
                # Only add title pattern files that aren't already in all_screenshots
                for file in title_pattern_files:
                    if file not in all_screenshots:
                        all_screenshots.append(file)

                logger.debug(f"[green]Found {len(title_pattern_files)} screenshots matching title pattern")

    # If we haven't found enough screenshots yet, search for files in the normal way
    if len(all_screenshots) < multi_screens:
        for _file in filelist:
            sanitized_title = await sanitize_filename(filename)
            filename_pattern = f"{glob.escape(sanitized_title)}*.png"
            logger.debug(f"[yellow]Searching for screenshots with pattern: {filename_pattern}")

            if meta.is_disc == "DVD":
                existing_screens = await asyncio.to_thread(
                    lambda: [str(p) for p in (Path(meta.base_dir) / "tmp" / meta.uuid).glob(f"{glob.escape(meta.discs[0]['name'])}-*.png")]
                )
            else:
                existing_screens = await asyncio.to_thread(lambda fp=filename_pattern: [str(p) for p in Path(screenshots_dir).glob(fp)])

            # Add any new screenshots to our list
            for screen in existing_screens:
                if screen not in all_screenshots:
                    all_screenshots.append(screen)

    # Fallback: glob for indexed screenshots if still not enough
    if len(all_screenshots) < multi_screens:
        os.chdir(f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}")
        image_patterns = ["*.png", ".[!.]*.png"]
        image_glob: list[str] = []
        for pattern in image_patterns:
            glob_results = await asyncio.to_thread(lambda p=pattern: [str(path.relative_to(Path.cwd())) for path in Path.cwd().glob(p)])
            image_glob.extend(glob_results)
            logger.debug(f"[cyan]Found {len(image_glob)} files matching pattern: {pattern}")

        unwanted_patterns = ["FILE*", "PLAYLIST*", "POSTER*"]
        unwanted_files: set[str] = set()
        for pattern in unwanted_patterns:
            glob_results = await asyncio.to_thread(lambda p=pattern: [str(path.relative_to(Path.cwd())) for path in Path.cwd().glob(p)])
            unwanted_files.update(glob_results)
            if pattern.startswith("FILE") or pattern.startswith("PLAYLIST") or pattern.startswith("POSTER"):
                hidden_pattern = "." + pattern
                hidden_glob_results = await asyncio.to_thread(lambda hp=hidden_pattern: [str(path.relative_to(Path.cwd())) for path in Path.cwd().glob(hp)])
                unwanted_files.update(hidden_glob_results)

        # Remove unwanted files
        image_glob = [file for file in image_glob if file not in unwanted_files]
        image_glob = list(set(image_glob))
        logger.debug(f"[cyan]Filtered out {len(unwanted_files)} unwanted files, remaining: {len(image_glob)}")

        # Only keep files that match the indexed pattern: xxx-0.png, xxx-1.png, etc.
        indexed_pattern = re.compile(r".*-\d+\.png$")
        indexed_files: list[str] = [file for file in image_glob if indexed_pattern.match(Path(file).name)]
        logger.debug(f"[cyan]Found {len(indexed_files)} indexed files matching pattern")

        # Add any new indexed screenshots to our list
        for screen in indexed_files:
            if screen not in all_screenshots:
                all_screenshots.append(screen)
                logger.debug(f"[green]Found indexed screenshot: {Path(screen).name}")

    if tracker == "covers":
        all_screenshots = []
        existing_screens = await asyncio.to_thread(lambda: [str(p) for p in (Path(meta.base_dir) / "tmp" / meta.uuid).glob("cover_*.jpg")])
        for screen in existing_screens:
            if screen not in all_screenshots:
                all_screenshots.append(screen)

    # Ensure we have unique screenshots
    all_screenshots = list(set(all_screenshots))

    if tracker == "covers":
        multi_screens = len(all_screenshots)

    # If we still don't have enough screenshots, generate new ones
    if len(all_screenshots) < multi_screens:
        # Calculate how many more screenshots we need
        needed_screenshots = multi_screens - len(all_screenshots)

        logger.debug(f"[yellow]Found {len(all_screenshots)} screenshots, need {needed_screenshots} more to reach {multi_screens} total.")

        try:
            if meta.is_disc == "BDMV":
                await takescreens_manager.disc_screenshots(meta, filename, meta.bdinfo, folder_id, base_dir, meta.vapoursynth, [], meta.ffdebug, needed_screenshots, True)
            elif meta.is_disc == "DVD":
                await takescreens_manager.dvd_screenshots(meta, disc_num=0, retry_cap=True)
            else:
                if path:
                    await takescreens_manager.screenshots(
                        path,
                        filename,
                        meta.uuid,
                        base_dir,
                        meta,
                        needed_screenshots,
                        True,
                        "",
                    )
                else:
                    logger.info("[red]No valid path available for screenshot generation.[/red]")

            if meta.is_disc == "DVD":
                new_screens = await asyncio.to_thread(lambda: [str(p) for p in (Path(meta.base_dir) / "tmp" / meta.uuid).glob(f"{glob.escape(meta.discs[0]['name'])}-*.png")])
            else:
                # Use a more generic pattern to find any PNG files that aren't already in all_screenshots
                new_screens = await asyncio.to_thread(lambda: [str(p) for p in Path(screenshots_dir).glob("*.png")])
                indexed_pattern = re.compile(r".*-\d+\.png$")
                new_screens = [s for s in new_screens if indexed_pattern.match(Path(s).name)]

                # Filter out files we already have
                new_screens = [screen for screen in new_screens if screen not in all_screenshots]

            # Add any new screenshots to our list (only those not already in all_screenshots)
            if new_screens and meta.debug:
                logger.info(f"[green]Found {len(new_screens)} new screenshots after generation")

            for screen in new_screens:
                if screen not in all_screenshots:
                    all_screenshots.append(screen)
                    logger.debug(f"[green]Added new screenshot: {Path(screen).name}")

        except Exception as e:
            logger.error(f"[red]Error during screenshot capture: {e}")
            import traceback

            logger.info(f"[dim]{traceback.format_exc()}[/dim]")

    if not all_screenshots:
        logger.info("[red]No screenshots were generated or found. Please check the screenshot generation process.")
        return [], True, images_reuploaded

    all_screenshots.sort()
    existing_from_image_list: list[str] = []
    other_screenshots: list[str] = []

    # First separate the screenshots into two categories
    image_list_entries = cast(list[dict[str, str]], meta.image_list)
    for screenshot in all_screenshots:
        basename = Path(screenshot).name
        # Check if this is from the image_list we extracted earlier
        if image_list_entries and any(Path(urlparse(_as_str(img.get("raw_url")) or "").path).name == basename for img in image_list_entries):
            existing_from_image_list.append(screenshot)
        else:
            other_screenshots.append(screenshot)

    # First take all existing screenshots from image_list
    final_screenshots: list[str] = existing_from_image_list.copy()

    # Then fill up to multi_screens with other screenshots
    remaining_needed = multi_screens - len(final_screenshots)
    if remaining_needed > 0 and other_screenshots:
        final_screenshots.extend(other_screenshots[:remaining_needed])

    # If we still don't have enough, just use whatever we have
    if len(final_screenshots) < multi_screens and len(all_screenshots) >= multi_screens:
        # Fill with any remaining screenshots not yet included
        remaining: list[str] = [s for s in all_screenshots if s not in final_screenshots]
        final_screenshots.extend(remaining[: multi_screens - len(final_screenshots)])

    all_screenshots = all_screenshots if tracker == "covers" else final_screenshots[:multi_screens]

    logger.debug(f"[green]Using {len(all_screenshots)} screenshots:")
    for i, screenshot in enumerate(all_screenshots):
        logger.debug(f"  {i + 1}. {Path(screenshot).name}")

    if not meta.skip_imghost_upload:
        uploaded_images: list[dict[str, str]] = []

        # Add a max retry limit to prevent infinite loop
        configured_indices = sorted(int(match.group(1)) for key in default_config if (match := re.fullmatch(r"img_host_(\d+)", key)) and _as_str(default_config.get(key)))
        if not configured_indices:
            return [], True, images_reuploaded

        max_retries = configured_indices[-1]
        while img_host_index <= max_retries:
            current_img_host_key = f"img_host_{img_host_index}"
            current_img_host = _as_str(default_config.get(current_img_host_key))

            if not current_img_host:
                logger.info("[red]No more image hosts left to try.")
                return [], True, images_reuploaded

            if current_img_host not in approved_image_hosts:
                logger.info(f"[red]Your preferred image host '{current_img_host}' is not supported at {tracker}, trying next host.")
                retry_mode = True
                images_reuploaded = True
                img_host_index += 1
                continue
            meta.imghost = current_img_host
            logger.debug(f"[green]Uploading to approved host '{current_img_host}'.")
            break

        if not meta.imghost:
            logger.info("[red]No approved image host was selected; skipping upload.")
            return [], True, images_reuploaded

        uploaded_images, _ = await uploadscreens_manager.upload_screens(
            meta, multi_screens, img_host_index, 0, multi_screens, all_screenshots, {new_images_key: meta[new_images_key]}, retry_mode
        )
        if uploaded_images:
            meta[new_images_key] = uploaded_images

        logger.debug(f"[debug] Updated {new_images_key} with {len(uploaded_images)} images.")
        for image in uploaded_images:
            logger.debug(f"[debug] Response in upload_image_task: {image['img_url']}, {image['raw_url']}, {image['web_url']}")

        for image in cast(list[dict[str, str]], meta.get(new_images_key, [])):
            raw_url = image["raw_url"]
            parsed_url = urlparse(raw_url)
            hostname = parsed_url.netloc
            mapped_host = await match_host(hostname, url_host_mapping.keys())
            mapped_host = url_host_mapping.get(mapped_host, mapped_host)

            if mapped_host not in approved_image_hosts:
                logger.info(f"[red]Unsupported image host detected in URL '{raw_url}'. Please use one of the approved image hosts.")
                if original_imghost:
                    meta.imghost = original_imghost
                return meta[new_images_key], True, images_reuploaded  # Trigger retry_mode if switching hosts

        # Ensure all uploaded images are valid
        valid_hosts: list[bool] = []
        for image in cast(list[dict[str, str]], meta.get(new_images_key, [])):
            netloc = urlparse(image["raw_url"]).netloc
            matched_host = await match_host(netloc, url_host_mapping.keys())
            mapped_host = url_host_mapping.get(matched_host, matched_host)
            valid_hosts.append(mapped_host in approved_image_hosts)
        if uploaded_images and all(valid_hosts) and new_images_key in meta and isinstance(meta[new_images_key], list):
            output_file = Path(meta.base_dir) / "tmp" / meta.uuid / "covers.json" if tracker == "covers" else Path(screenshots_dir) / "reuploaded_images.json"

            existing_data: list[dict[str, str]] = []
            try:
                async with aiofiles.open(output_file, encoding="utf-8") as f:
                    existing_data_raw = await f.read()
                    loaded_value: object = json.loads(existing_data_raw) if existing_data_raw else []
                    if isinstance(loaded_value, list):
                        existing_data = cast(list[dict[str, str]], loaded_value)
                    else:
                        logger.info(f"[red]Existing data in {output_file} is not a list. Resetting to an empty list.")
            except Exception:
                existing_data = []

            updated_data = existing_data + meta[new_images_key]
            updated_data = [dict(s) for s in {tuple(d.items()) for d in updated_data}]

            if tracker == "covers" and "release_url" in meta:
                for image in updated_data:
                    if "release_url" not in image:
                        image["release_url"] = meta.release_url
                logger.info(f"[green]Added release URL to {len(updated_data)} cover images: {meta.release_url}")

            try:
                async with aiofiles.open(output_file, "w", encoding="utf-8") as f:
                    await f.write(json.dumps(updated_data, indent=4))
                logger.debug(f"[green]Successfully updated reuploaded images in {output_file}.")

                if tracker == "covers":
                    deleted_count = 0
                    for screenshot in all_screenshots:
                        if _safe_remove(screenshot):
                            deleted_count += 1
                            logger.debug(f"[dim]Deleted cover image file: {screenshot}[/dim]")

                    if deleted_count > 0 and meta.debug:
                        logger.info(f"[green]Cleaned up {deleted_count} cover image files after successful upload[/green]")

            except Exception as e:
                logger.error(f"[red]Failed to save reuploaded images: {e}")
        else:
            logger.info("[red]new_images_key is not a valid key in meta or is not a list.")

        if original_imghost:
            meta.imghost = original_imghost
        return meta[new_images_key], False, images_reuploaded
    if original_imghost:
        meta.imghost = original_imghost
    return meta[new_images_key], False, images_reuploaded
