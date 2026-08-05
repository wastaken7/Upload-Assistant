# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import asyncio
import io
import sys
from collections.abc import Mapping, Sequence
from io import BytesIO
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlparse

import cli_ui
import click
import httpx
from PIL import Image

from src.bbcode import BBCODE
from src.btnid import BtnIdManager
from src.console import buffer_console_logs, logger
from src.meta import Meta
from src.temp_paths import screenshots_dir
from src.tracker_descriptions import DescriptionCandidate, add_candidate, description_fingerprint, resolve_description_mode, score_release_name
from src.trackers.common import Common
from src.trackersetup import api_trackers
from src.type_utils import to_int

config: dict[str, Any] = {}
default_config: Mapping[str, Any] = {}
trackers_config: Mapping[str, Any] = {}

type ImageDict = dict[str, Any]


expected_images = 0


def _apply_config(next_config: dict[str, Any]) -> None:
    global config, default_config, trackers_config, expected_images
    config = next_config
    default_config = cast(Mapping[str, Any], next_config.get("DEFAULT", {}))
    trackers_config = cast(Mapping[str, Any], next_config.get("TRACKERS", {}))
    expected_images = to_int(default_config.get("screens", 0))


class TrackerMetaManager:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        _apply_config(config)

    async def prompt_user_for_confirmation(self, message: str, meta: Meta | None = None) -> bool:
        return await prompt_user_for_confirmation(message, meta)

    async def check_images_concurrently(self, imagelist: Sequence[ImageDict], meta: Meta) -> list[ImageDict]:
        return await check_images_concurrently(imagelist, meta)

    async def check_image_link(self, url: str, timeout: httpx.Timeout | None = None) -> bool:  # noqa: ASYNC109
        return await check_image_link(url, timeout)

    async def update_meta_with_unit3d_data(self, meta: Meta, tracker_data: Sequence[Any], tracker_name: str, skip_tracker_descriptions: bool = False) -> bool:
        return await update_meta_with_unit3d_data(meta, tracker_data, tracker_name, skip_tracker_descriptions)

    async def update_metadata_from_tracker(
        self,
        tracker_name: str,
        tracker_instance: Any,
        meta: Meta,
        search_term: str,
        search_file_folder: str,
        skip_tracker_descriptions: bool = False,
    ) -> tuple[Meta, bool]:
        return await update_metadata_from_tracker(
            tracker_name,
            tracker_instance,
            meta,
            search_term,
            search_file_folder,
            skip_tracker_descriptions,
        )

    async def handle_image_list(self, meta: Meta, tracker_name: str, valid_images: Sequence[ImageDict] | None = None) -> None:
        await handle_image_list(meta, tracker_name, valid_images)


async def prompt_user_for_confirmation(message: str, meta: Meta | None = None) -> bool:
    if meta and meta.unattended and not meta.unattended_confirm:
        return False
    try:
        async with buffer_console_logs():
            return cli_ui.ask_yes_no(message, default=True)
    except EOFError:
        sys.exit(1)


async def check_images_concurrently(imagelist: Sequence[ImageDict], meta: Meta) -> list[ImageDict]:
    # Ensure meta.image_sizes exists
    if "image_sizes" not in meta:
        meta.image_sizes = {}

    seen_urls: set[str] = set()
    unique_images: list[ImageDict] = []

    for img in imagelist:
        img_url = cast(str | None, img.get("raw_url"))
        if img_url and img_url not in seen_urls:
            seen_urls.add(img_url)
            unique_images.append(img)
        elif img_url:
            logger.debug(f"[yellow]Removing duplicate image URL: {img_url}[/yellow]")

    if len(unique_images) < len(imagelist) and meta.debug:
        logger.info(f"[yellow]Removed {len(imagelist) - len(unique_images)} duplicate images from the list.[/yellow]")

    # Map fixed resolution names to vertical resolutions
    resolution_map = {
        "8640p": 8640,
        "4320p": 4320,
        "2160p": 2160,
        "1440p": 1440,
        "1080p": 1080,
        "1080i": 1080,
        "720p": 720,
        "576p": 576,
        "576i": 576,
        "480p": 480,
        "480i": 480,
    }

    # Get expected vertical resolution
    expected_resolution_name = cast(str | None, meta.resolution)
    expected_vertical_resolution = resolution_map.get(expected_resolution_name or "")

    # If no valid resolution is found, skip processing
    if expected_vertical_resolution is None:
        logger.info("[red]Meta resolution is invalid or missing. Skipping all images.[/red]")
        return []

    # Function to check each image's URL, host, and log resolution
    save_directory = Path(meta.base_dir) / "tmp" / meta.uuid

    timeout = httpx.Timeout(15.0, connect=5.0, read=5.0)

    async def check_and_collect(image_dict: ImageDict) -> ImageDict | None:
        img_url = cast(str | None, image_dict.get("raw_url"))
        if not img_url:
            return None

        # Handle when pixhost url points to web_url and convert to raw_url
        if img_url.startswith("https://pixhost.to/show/"):
            img_url = img_url.replace("https://pixhost.to/show/", "https://img1.pixhost.to/images/", 1)

        parsed_host = (urlparse(img_url).hostname or "").lower()
        if parsed_host == "tmdb.org" or parsed_host.endswith(".tmdb.org"):
            return None

        # Verify the image link
        try:
            if await check_image_link(img_url, timeout):
                try:
                    async with httpx.AsyncClient(timeout=timeout) as session:
                        try:
                            response = await session.get(img_url)
                            if response.status_code == 200:
                                image_content = response.content

                                try:
                                    image = Image.open(BytesIO(image_content))
                                    vertical_resolution = image.height
                                    lower_bound = expected_vertical_resolution * 0.70
                                    upper_bound = expected_vertical_resolution * (1.30 if meta.is_disc == "DVD" else 1.00)

                                    if not (lower_bound <= vertical_resolution <= upper_bound):
                                        logger.info(
                                            f"[red]Image {img_url} resolution ({vertical_resolution}p) "
                                            f"is outside the allowed range ({int(lower_bound)}-{int(upper_bound)}p). Skipping.[/red]"
                                        )
                                        return None

                                    # Save image
                                    Path(save_directory).mkdir(parents=True, exist_ok=True)
                                    image_filename = Path(save_directory) / Path(img_url).name
                                    await asyncio.to_thread(Path(image_filename).write_bytes, image_content)

                                    logger.info(f"Saved {img_url} as {image_filename}")

                                    meta.image_sizes[img_url] = len(image_content)

                                    logger.debug(f"Valid image {img_url} with resolution {image.width}x{image.height} and size {len(image_content) / 1024:.2f} KiB")
                                    return image_dict
                                except Exception as e:
                                    logger.error(f"[red]Failed to process image {img_url}: {e}")
                                    return None
                            else:
                                logger.error(f"[red]Failed to fetch image {img_url}. Status: {response.status_code}. Skipping.")
                                return None
                        except TimeoutError:
                            logger.info(f"[red]Timeout downloading image: {img_url}")
                            return None
                        except httpx.HTTPError as e:
                            logger.info(f"[red]Client error downloading image: {img_url} - {e}")
                            return None
                except Exception as e:
                    logger.info(f"[red]Session error for image: {img_url} - {e}")
                    return None
            else:
                return None
        except Exception as e:
            logger.error(f"[red]Error checking image: {img_url} - {e}")
            return None

    # Run image verification concurrently but with a limit to prevent too many simultaneous connections
    semaphore = asyncio.Semaphore(2)  # Limit concurrent requests to 2

    async def bounded_check(image_dict: ImageDict) -> ImageDict | None:
        async with semaphore:
            return await check_and_collect(image_dict)

    tasks = [bounded_check(image_dict) for image_dict in unique_images]

    try:
        results = await asyncio.gather(*tasks, return_exceptions=False)
    except Exception as e:
        logger.error(f"[red]Error during image processing: {e}")
        results = []

    # Collect valid images and limit to amount set in config
    valid_images = [image for image in results if image is not None]
    if expected_images < len(valid_images):
        valid_images = valid_images[:expected_images]

    return valid_images


async def check_image_link(url: str, timeout: httpx.Timeout | None = None) -> bool:  # noqa: ASYNC109
    # Handle when pixhost url points to web_url and convert to raw_url
    if url.startswith("https://pixhost.to/show/"):
        url = url.replace("https://pixhost.to/show/", "https://img1.pixhost.to/images/", 1)
    if timeout is None:
        timeout = httpx.Timeout(20.0, connect=10.0)

    try:
        async with httpx.AsyncClient(timeout=timeout, verify=False) as session:  # noqa: S501
            try:
                response = await session.get(url)
                if response.status_code == 200:
                    content_type = response.headers.get("Content-Type", "").lower()
                    if "image" in content_type:
                        # Attempt to load the image
                        image_data = response.content
                        try:
                            image = Image.open(io.BytesIO(image_data))
                            image.verify()  # This will check if the image is broken
                            return True
                        except (OSError, SyntaxError) as e:
                            logger.info(f"[red]Image verification failed (corrupt image): {url} {e}[/red]")
                            return False
                    else:
                        logger.info(f"[red]Content type is not an image: {url}[/red]")
                        return False
                else:
                    logger.error(f"[red]Failed to retrieve image: {url} (status code: {response.status_code})[/red]")
                    return False
            except TimeoutError:
                logger.info(f"[red]Timeout checking image link: {url}[/red]")
                return False
            except Exception as e:
                logger.info(f"[red]Exception occurred while checking image: {url} - {e!s}[/red]")
                return False
    except Exception as e:
        logger.info(f"[red]Session creation failed for: {url} - {e!s}[/red]")
        return False


async def update_meta_with_unit3d_data(meta: Meta, tracker_data: Sequence[Any], tracker_name: str, _skip_tracker_descriptions: bool = False) -> bool:
    # Unpack the expected 9 elements, ignoring any additional ones
    tmdb, imdb, tvdb, mal, desc, category, _infohash, imagelist, filename, *_rest = tracker_data
    if tmdb:
        meta.tmdb_id = tmdb
        logger.debug(f"set TMDB ID: {meta.tmdb_id}")
    if imdb:
        meta.imdb_id = int(imdb)
        logger.debug(f"set IMDB ID: {meta.imdb_id}")
    if tvdb:
        meta.tvdb_id = tvdb
        logger.debug(f"set TVDB ID: {meta.tvdb_id}")
    if mal:
        meta.mal_id = mal
        logger.debug(f"set MAL ID: {meta.mal_id}")
    mode = resolve_description_mode(meta.tracker_description_mode)
    if desc:
        raw_descriptions = getattr(meta, "tracker_description_raw", {}) or {}
        raw_description = str(raw_descriptions.get(tracker_name, desc))
        candidate = DescriptionCandidate(
            source=tracker_name,
            release_id=str(meta.get(tracker_name.lower(), "") or ""),
            release_name=str(filename or ""),
            raw_description=raw_description,
            cleaned_description=str(desc),
            image_count=len(imagelist or []),
            score=score_release_name(
                getattr(meta, "tracker_search_term", ""),
                filename,
                explicit_id=bool(meta.get(tracker_name.lower())),
            ),
        )
        add_candidate(meta, candidate, selected=mode.imports_text)
    if desc and mode.imports_text:
        meta.description = desc
        meta.saved_description = True
    if category and not meta.manual_category:
        cat_upper = category.upper()
        if "MOVIE" in cat_upper:
            meta.category = "MOVIE"
        elif "TV" in cat_upper:
            meta.category = "TV"
        logger.debug(f"set Category: {meta.category}")

    imagelist_typed = cast(list[ImageDict] | None, imagelist)
    if imagelist_typed and mode.imports_images:  # Ensure imagelist is not empty before setting
        valid_images = await check_images_concurrently(imagelist_typed, meta)
        if valid_images:
            meta.image_list = valid_images
            if meta.image_list and (not any(meta.get(t.lower()) for t in api_trackers) or meta.unattended):
                await handle_image_list(meta, tracker_name, valid_images)

    if desc and mode.imports_text:
        meta.description_fingerprint = description_fingerprint(meta, tracker_name)

    if filename:
        meta[f"{tracker_name.lower()}_filename"] = filename

    logger.debug(f"[green]{tracker_name} data successfully updated in meta[/green]")
    return True


async def update_metadata_from_tracker(
    tracker_name: str,
    tracker_instance: Any,
    meta: Meta,
    search_term: str,
    search_file_folder: str,
    skip_tracker_descriptions: bool = False,
) -> tuple[Meta, bool]:
    tracker_key = tracker_name.lower()
    meta.tracker_search_term = search_term
    manual_key = f"{tracker_key}_manual"
    found_match = False

    if tracker_name == "PASSTHEPOPCORN":
        imdb_id: int = 0
        ptp_imagelist: list[ImageDict] = []
        if meta.ptp is None:
            ptp_result = await tracker_instance.get_ptp_id_imdb(search_term, search_file_folder, meta)
            imdb_id, ptp_torrent_id, meta.ext_torrenthash = cast(tuple[int, int | None, str | None], ptp_result)
            if ptp_torrent_id:
                if imdb_id:
                    logger.info(f"[green]{tracker_name} IMDb ID found: tt{str(imdb_id).zfill(7)}[/green]")

                if not meta.unattended:
                    if await prompt_user_for_confirmation("Do you want to use this ID data from PASSTHEPOPCORN?"):
                        meta.imdb_id = imdb_id
                        found_match = True
                        meta.ptp = ptp_torrent_id

                        if not skip_tracker_descriptions or meta.keep_images:
                            ptp_imagelist = cast(
                                list[ImageDict],
                                await tracker_instance.get_ptp_description(ptp_torrent_id, meta, meta.is_disc),
                            )
                        if ptp_imagelist:
                            valid_images = await check_images_concurrently(ptp_imagelist, meta)
                            if valid_images:
                                meta.image_list = valid_images
                                await handle_image_list(meta, tracker_name, valid_images)

                    else:
                        found_match = False
                        meta.imdb_id = meta.imdb_id if meta.imdb_id else 0
                        meta.ptp = None
                        meta.description = ""
                        meta.image_list = []

                else:
                    found_match = True
                    meta.imdb_id = imdb_id
                    if not skip_tracker_descriptions or meta.keep_images:
                        ptp_imagelist = cast(
                            list[ImageDict],
                            await tracker_instance.get_ptp_description(ptp_torrent_id, meta, meta.is_disc),
                        )
                    if ptp_imagelist:
                        valid_images = await check_images_concurrently(ptp_imagelist, meta)
                        if valid_images:
                            meta.image_list = valid_images
            else:
                logger.debug("[yellow]Skipping PASSTHEPOPCORN as no match found[/yellow]")
                found_match = False

        else:
            ptp_torrent_id = cast(int, meta.ptp)
            ptp_imdb_result = await tracker_instance.get_imdb_from_torrent_id(ptp_torrent_id)
            imdb_id, meta.ext_torrenthash = cast(tuple[int, str | None], ptp_imdb_result)
            if imdb_id:
                meta.imdb_id = imdb_id
                logger.debug(f"[green]IMDb ID found: tt{str(meta.imdb_id).zfill(7)}[/green]")
                found_match = True
                meta.skipit = True
                if not skip_tracker_descriptions or meta.keep_images:
                    ptp_imagelist = cast(
                        list[ImageDict],
                        await tracker_instance.get_ptp_description(meta.ptp, meta, meta.is_disc),
                    )
                if ptp_imagelist:
                    valid_images = await check_images_concurrently(ptp_imagelist, meta)
                    if valid_images:
                        meta.image_list = valid_images
                        logger.info("[green]PASSTHEPOPCORN images added to metadata.[/green]")
            else:
                logger.info(f"[yellow]Could not find IMDb ID using PASSTHEPOPCORN ID: {ptp_torrent_id}[/yellow]")
                found_match = False

    elif tracker_name == "BEYONDHD":
        trackers_cfg = cast(Mapping[str, Any], config.get("TRACKERS", {}))
        tracker_cfg = cast(dict[str, Any], trackers_cfg.get("BEYONDHD", {}))
        bhd_api = tracker_cfg.get("api_key")
        bhd_api = bhd_api if isinstance(bhd_api, str) else None
        if bhd_api and len(bhd_api) < 25:
            bhd_api = None

        bhd_rss_key = tracker_cfg.get("bhd_rss_key")
        bhd_rss_key = bhd_rss_key if isinstance(bhd_rss_key, str) else None
        if bhd_rss_key and len(bhd_rss_key) < 25:
            bhd_rss_key = None

        if not bhd_api or not bhd_rss_key:
            logger.info("[red]BEYONDHD API or RSS key not found. Please check your configuration.[/red]")
            return meta, False
        use_foldername = bool(meta.is_disc) or meta.keep_folder is True or meta.isdir is True

        if meta.bhd:
            imdb, tmdb = cast(
                tuple[int | None, int | None],
                await BtnIdManager.get_bhd_torrents(bhd_api, bhd_rss_key, meta, skip_tracker_descriptions=skip_tracker_descriptions, torrent_id=int(meta.bhd)),
            )
        elif use_foldername:
            # Use folder name from path if available, fall back to UUID
            folder_path = meta.path
            foldername = Path(folder_path).name if folder_path else meta.uuid
            imdb, tmdb = cast(
                tuple[int | None, int | None],
                await BtnIdManager.get_bhd_torrents(bhd_api, bhd_rss_key, meta, skip_tracker_descriptions=skip_tracker_descriptions, foldername=foldername),
            )
        else:
            # Only use filename if none of the folder conditions are met
            filelist = cast(list[str], meta.filelist or [])
            filename = Path(filelist[0]).name if filelist else None
            imdb, tmdb = cast(
                tuple[int | None, int | None],
                await BtnIdManager.get_bhd_torrents(bhd_api, bhd_rss_key, meta, skip_tracker_descriptions=skip_tracker_descriptions, filename=filename),
            )

        if to_int(imdb) != 0 or to_int(tmdb) != 0:
            if not meta.unattended:
                logger.info(f"[green]{tracker_name} data found: IMDb ID: {imdb}, TMDb ID: {tmdb}[/green]")
                if await prompt_user_for_confirmation(f"Do you want to use the ID's found on {tracker_name}?"):
                    found_match = True
                    meta.imdb_id = to_int(imdb, to_int(meta.imdb_id))
                    meta.tmdb_id = to_int(tmdb, to_int(meta.tmdb_id))
                    description_value = meta.description
                    if isinstance(description_value, str) and description_value:
                        description = description_value
                        logger.info("[bold green]Successfully grabbed description from BEYONDHD")
                        logger.info(f"Description after cleaning:\n{description[:1000]}...", extra={"markup": False})

                        if not meta.skipit:
                            logger.info("[cyan]Do you want to edit, discard or keep the description?[/cyan]")
                            edit_choice = cli_ui.ask_string("Enter 'e' to edit, 'd' to discard, or press Enter to keep it as is: ")

                            if (edit_choice or "").lower() == "e":
                                # pyrefly: ignore [bad-argument-type]
                                edited_description = str(click.edit(text=description) or "")
                                if edited_description:
                                    desc = edited_description.strip()
                                    meta.description = desc
                                    meta.saved_description = True
                                logger.info(f"[green]Final description after editing:[/green] {meta.description}", extra={"markup": False})
                            elif (edit_choice or "").lower() == "d":
                                meta.description = ""
                                meta.image_list = []
                                logger.info("[yellow]Description discarded.[/yellow]")
                            else:
                                logger.info("[green]Keeping the original description.[/green]")
                                meta.description = description
                                meta.saved_description = True
                        else:
                            meta.description = description
                            meta.saved_description = True
                    elif meta.bhd_nfo:
                        if not meta.skipit:
                            nfo_file_path = Path(meta.base_dir) / "tmp" / meta.uuid / "bhd.nfo"
                            if Path(nfo_file_path).exists():
                                nfo_content = await asyncio.to_thread(Path(nfo_file_path).read_text, encoding="utf-8")
                                logger.info("[bold green]Successfully grabbed FraMeSToR description")
                                logger.info(f"Description content:\n{nfo_content[:1000]}...", extra={"markup": False})
                                logger.info("[cyan]Do you want to discard or keep the description?[/cyan]")
                                edit_choice = cli_ui.ask_string("Enter 'd' to discard, or press Enter to keep it as is: ")

                                if (edit_choice or "").lower() == "d":
                                    meta.description = ""
                                    meta.image_list = []
                                    nfo_file_path = Path(meta.base_dir) / "tmp" / meta.uuid / "bhd.nfo"

                                    try:
                                        import gc

                                        gc.collect()  # Force garbage collection to close any lingering handles
                                        for attempt in range(3):
                                            try:
                                                nfo_file_path.unlink()
                                                logger.info("[yellow]NFO file successfully deleted.[/yellow]")
                                                break
                                            except Exception as e:
                                                if attempt < 2:
                                                    logger.info(f"[yellow]Attempt {attempt + 1}: Could not delete file, retrying in 1 second...[/yellow]")
                                                    await asyncio.sleep(1)
                                                else:
                                                    logger.error(f"[red]Failed to delete BEYONDHD NFO file after 3 attempts: {e}[/red]")
                                    except Exception as e:
                                        logger.error(f"[red]Error during file cleanup: {e}[/red]")
                                    meta.nfo = False
                                    meta.bhd_nfo = False
                                    logger.info("[yellow]Description discarded.[/yellow]")
                                else:
                                    logger.info("[green]Keeping the original description.[/green]")

                    image_list = cast(Sequence[ImageDict] | None, meta.image_list)
                    if image_list:
                        valid_images = await check_images_concurrently(image_list, meta)
                        if valid_images:
                            meta.image_list = valid_images
                            await handle_image_list(meta, tracker_name, valid_images)
                        else:
                            meta.image_list = []

                else:
                    logger.info(f"[yellow]{tracker_name} data discarded.[/yellow]")
                    meta[tracker_key] = None
                    meta.imdb_id = meta.imdb_id if meta.imdb_id else 0
                    meta.tmdb_id = meta.tmdb_id if meta.tmdb_id else 0
                    meta.framestor = False
                    meta.flux = False
                    meta.description = ""
                    meta.image_list = []
                    meta.nfo = False
                    meta.bhd_nfo = False
                    save_path = Path(meta.base_dir) / "tmp" / meta.uuid
                    nfo_file_path = Path(save_path) / "bhd.nfo"
                    if Path(nfo_file_path).exists():
                        try:
                            nfo_file_path.unlink()
                        except Exception as e:
                            logger.error(f"[red]Failed to delete BEYONDHD NFO file: {e}[/red]")
                    found_match = False
            else:
                # Only treat as match if we actually got valid IDs
                meta.imdb_id = to_int(imdb, to_int(meta.imdb_id))
                meta.tmdb_id = to_int(tmdb, to_int(meta.tmdb_id))
                if to_int(meta.imdb_id) != 0 or to_int(meta.tmdb_id) != 0:
                    logger.info(f"[green]{tracker_name} data found: IMDb ID: {meta.imdb_id}, TMDb ID: {meta.tmdb_id}[/green]")
                    found_match = True
                    image_list = cast(Sequence[ImageDict] | None, meta.image_list)
                    if image_list:
                        valid_images = await check_images_concurrently(image_list, meta)
                        if valid_images:
                            meta.image_list = valid_images
                        else:
                            meta.image_list = []
                else:
                    logger.debug(f"[yellow]{tracker_name} returned invalid IDs (both 0), not using as match[/yellow]")
                    found_match = False
        else:
            logger.debug(f"[yellow]{tracker_name} returned invalid IDs (both 0)[/yellow]")
            found_match = False

    elif tracker_name in api_trackers:
        if meta.get(tracker_key) is not None:
            logger.debug(f"[cyan]{tracker_name} ID found in meta, reusing existing ID: {meta[tracker_key]}[/cyan]")
            tracker_data = cast(
                Sequence[Any],
                await Common(config).unit3d_torrent_info(
                    tracker_name,
                    tracker_instance.id_url,
                    tracker_instance.search_url,
                    meta,
                    id=meta[tracker_key],
                    skip_tracker_descriptions=skip_tracker_descriptions,
                ),
            )
        else:
            logger.debug(f"[yellow]No ID found in meta for {tracker_name}, searching by file name[/yellow]")
            tracker_data = cast(
                Sequence[Any],
                await Common(config).unit3d_torrent_info(
                    tracker_name,
                    tracker_instance.id_url,
                    tracker_instance.search_url,
                    meta,
                    file_name=search_term,
                    skip_tracker_descriptions=skip_tracker_descriptions,
                ),
            )

        if any(item not in [None, 0] for item in tracker_data[:3]):  # Check for valid tmdb, imdb, or tvdb
            logger.debug(f"[green]Valid data found on {tracker_name}[/green]")
            selected = await update_meta_with_unit3d_data(meta, tracker_data, tracker_name, skip_tracker_descriptions)
            found_match = selected
        else:
            logger.debug(f"[yellow]No valid data found on {tracker_name}[/yellow]")
            found_match = False

    elif tracker_name == "HDBITS":
        bbcode = BBCODE()
        if meta.hdb is not None:
            meta[manual_key] = meta[tracker_key]
            logger.info(f"[cyan]{tracker_name} ID found in meta, reusing existing ID: {meta[tracker_key]}[/cyan]")

            # Use get_info_from_torrent_id function if ID is found in meta
            hdb_info = await tracker_instance.get_info_from_torrent_id(meta[tracker_key])
            imdb, tvdb_id, hdb_name, meta.ext_torrenthash, meta.hdb_description = cast(
                tuple[int | None, int | None, str | None, str | None, str | None],
                hdb_info,
            )

            if imdb or tvdb_id or meta.hdb_description:
                meta.imdb_id = imdb if imdb else meta.imdb_id
                meta.tvdb_id = tvdb_id if tvdb_id else meta.tvdb_id
                meta.hdb_name = hdb_name
                found_match = True
                description_source = meta.hdb_description or ""
                description, image_list = cast(
                    tuple[str | None, list[ImageDict]],
                    bbcode.clean_hdb_description(description_source),
                )
                if description and len(description) > 0 and not skip_tracker_descriptions:
                    logger.info(f"Description content:\n{description[:500]}...", extra={"markup": False})
                    meta.description = description
                    meta.saved_description = True
                else:
                    logger.info("[yellow]HDBITS description empty[/yellow]")
                if image_list and meta.keep_images:
                    valid_images = await check_images_concurrently(image_list, meta)
                    if valid_images:
                        meta.image_list = valid_images
                        await handle_image_list(meta, tracker_name, valid_images)
                else:
                    meta.image_list = []

                logger.info(f"[green]{tracker_name} data found: IMDb ID: {imdb}, TVDb ID: {meta.tvdb_id}, HDBITS Name: {meta.hdb_name}[/green]")
            else:
                logger.info(f"[yellow]{tracker_name} data not found for ID: {meta[tracker_key]}[/yellow]")
                found_match = False
        else:
            logger.debug("[yellow]No ID found in meta for HDBITS, searching by file name[/yellow]")

            # Use search_filename function if ID is not found in meta
            hdb_search = await tracker_instance.search_filename(search_term, search_file_folder, meta)
            imdb, tvdb_id, hdb_name, meta.ext_torrenthash, meta.hdb_description, tracker_id = cast(
                tuple[int | None, int | None, str | None, str | None, str | None, int | None],
                hdb_search,
            )
            meta.hdb_name = hdb_name
            if tracker_id:
                meta[tracker_key] = tracker_id

            if imdb or tvdb_id or meta.hdb_description:
                if not meta.unattended:
                    logger.info(f"[green]{tracker_name} data found: IMDb ID: {imdb}, TVDb ID: {meta.tvdb_id}, HDBITS Name: {meta.hdb_name}[/green]")
                    if await prompt_user_for_confirmation(f"Do you want to use the ID's found on {tracker_name}?"):
                        logger.info(f"[green]{tracker_name} data retained.[/green]")
                        meta.imdb_id = imdb if imdb else meta.imdb_id
                        meta.tvdb_id = tvdb_id if tvdb_id else meta.tvdb_id
                        found_match = True
                        description_source = meta.hdb_description or ""
                        description, image_list = cast(
                            tuple[str | None, list[ImageDict]],
                            bbcode.clean_hdb_description(description_source),
                        )
                        if description and len(description) > 0 and not skip_tracker_descriptions:
                            logger.info("[bold green]Successfully grabbed description from HDBITS")
                            logger.info(f"HDBITS Description content:\n{description[:1000]}.....", extra={"markup": False})
                            logger.info("[cyan]Do you want to edit, discard or keep the description?[/cyan]")
                            edit_choice_raw = cli_ui.ask_string("Enter 'e' to edit, 'd' to discard, or press Enter to keep it as is: ")
                            edit_choice = (edit_choice_raw or "").strip().lower()

                            if edit_choice.lower() == "e":
                                # pyrefly: ignore [bad-argument-type]
                                edited_description = str(click.edit(text=description) or "")
                                if edited_description:
                                    description = edited_description.strip()
                                    meta.description = description
                                    meta.saved_description = True
                                logger.info(f"[green]Final description after editing:[/green] {description}", extra={"markup": False})
                            elif edit_choice.lower() == "d":
                                meta.hdb_description = ""
                                logger.info("[yellow]Description discarded.[/yellow]")
                            else:
                                logger.info("[green]Keeping the original description.[/green]")
                                meta.description = description
                                meta.saved_description = True
                        else:
                            logger.info("[yellow]HDBITS description empty[/yellow]")
                        if image_list and meta.keep_images:
                            valid_images = await check_images_concurrently(image_list, meta)
                            if valid_images:
                                meta.image_list = valid_images
                                await handle_image_list(meta, tracker_name, valid_images)
                    else:
                        logger.info(f"[yellow]{tracker_name} data discarded.[/yellow]")
                        meta[tracker_key] = None
                        meta.tvdb_id = meta.tvdb_id if meta.tvdb_id else 0
                        meta.imdb_id = meta.imdb_id if meta.imdb_id else 0
                        meta.hdb_name = None
                        meta.hdb_description = ""
                        found_match = False
                else:
                    meta.imdb_id = imdb if imdb else meta.imdb_id
                    meta.tvdb_id = tvdb_id if tvdb_id else meta.tvdb_id
                    description_source = meta.hdb_description or ""
                    description, image_list = cast(
                        tuple[str | None, list[ImageDict]],
                        bbcode.clean_hdb_description(description_source),
                    )
                    if description and len(description) > 0 and not skip_tracker_descriptions:
                        logger.info(f"HDBITS Description content:\n{description[:500]}.....", extra={"markup": False})
                        meta.description = description
                        meta.saved_description = True
                    if image_list and meta.keep_images:
                        valid_images = await check_images_concurrently(image_list, meta)
                        if valid_images:
                            meta.image_list = valid_images
                            await handle_image_list(meta, tracker_name, valid_images)
                    logger.info(f"[green]{tracker_name} data found: IMDb ID: {imdb}, TVDb ID: {meta.tvdb_id}, HDBITS Name: {hdb_name}[/green]")
                    found_match = True
            else:
                meta.hdb_name = None
                meta.hdb_description = ""
                meta[tracker_key] = None
                found_match = False

    return meta, found_match


async def handle_image_list(meta: Meta, tracker_name: str, valid_images: Sequence[ImageDict] | None = None) -> None:
    if meta.image_list:
        valid_count = len(valid_images) if valid_images is not None else 0
        logger.info(f"[cyan]Selected the following {valid_count} valid images from {tracker_name}:")
        for img in meta.image_list:
            logger.info(f"Image:[green]'{img.get('img_url')}'[/green]")

        if meta.unattended:
            keep_images = True
        else:
            keep_images = await prompt_user_for_confirmation(f"Do you want to keep the images found on {tracker_name}?")
            if not keep_images:
                meta.image_list = []
                meta.image_sizes = {}
                save_path = screenshots_dir(meta.base_dir, meta.uuid)
                try:
                    png_files = list(Path(save_path).glob("*.png"))
                    for png_file in png_files:
                        png_file.unlink()

                    if png_files:
                        logger.info(f"[yellow]Successfully deleted {len(png_files)} image files.[/yellow]")
                    else:
                        logger.info("[yellow]No image files found to delete.[/yellow]")
                except Exception as e:
                    logger.error(f"[red]Failed to delete image files: {e}[/red]")
                logger.info(f"[yellow]Images discarded from {tracker_name}.")
            else:
                logger.info(f"[green]Images retained from {tracker_name}.")
