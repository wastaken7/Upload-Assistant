# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import asyncio
import base64
import contextlib
import gc
import math
import os
import re
import time
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path
from typing import Any, cast

import aiofiles
import httpx
import pyimgbox

from src.console import logger
from src.meta import Meta
from src.screenshot_manifest import files as manifest_files
from src.temp_paths import screenshots_dir

type ImageDict = dict[str, Any]


def _build_image_start_limiter(delay: float) -> Callable[[], Awaitable[None]]:
    """Create an async wait function that spaces image-upload starts."""
    start_lock = asyncio.Lock()
    last_start = 0.0

    async def wait_for_start_slot() -> None:
        """Wait until the next upload start interval is available."""
        nonlocal last_start
        if delay <= 0:
            return
        async with start_lock:
            now = time.monotonic()
            wait_time = delay - (now - last_start) if last_start else 0.0
            if wait_time > 0:
                await asyncio.sleep(wait_time)
            last_start = time.monotonic()

    return wait_for_start_slot


class UploadScreensManager:
    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize screenshot uploads with the application configuration."""
        self.config = config

    async def upload_screens(
        self,
        meta: Meta,
        screens: int,
        img_host_num: int,
        i: int,
        total_screens: int,
        custom_img_list: list[str],
        return_dict: dict[str, Any],
        retry_mode: bool = False,
        max_retries: int = 3,
        allowed_hosts: list[str] | None = None,
    ) -> tuple[list[ImageDict], int]:
        """Upload the selected screenshots and return uploaded image metadata."""
        return await _upload_screens(
            self.config,
            meta,
            screens,
            img_host_num,
            i,
            total_screens,
            custom_img_list,
            return_dict,
            retry_mode=retry_mode,
            max_retries=max_retries,
            allowed_hosts=allowed_hosts,
        )


async def upload_image_task(args: Sequence[Any]) -> dict[str, Any]:
    """Upload one image to the selected host and return its generated URLs."""
    image, img_host, config, _meta = args
    try:
        timeout = 60  # Default timeout
        img_url, raw_url, web_url = None, None, None

        if img_host == "imgbox":
            try:
                image_list = await imgbox_upload(Path.cwd(), [image], return_dict={})
                if image_list and all("img_url" in img and "raw_url" in img and "web_url" in img for img in image_list):
                    img_url = image_list[0]["img_url"]
                    raw_url = image_list[0]["raw_url"]
                    web_url = image_list[0]["web_url"]
                else:
                    return {"status": "failed", "reason": "Imgbox upload failed. No valid URLs returned."}
            except Exception as e:
                return {"status": "failed", "reason": f"Error during Imgbox upload: {e!s}"}

        elif img_host == "imgbb":
            url = "https://api.imgbb.com/1/upload"
            try:
                async with aiofiles.open(image, "rb") as img_file:
                    encoded_image = base64.b64encode(await img_file.read()).decode("utf8")

                data = {
                    "key": config["DEFAULT"]["imgbb_api"],
                    "image": encoded_image,
                }

                async with httpx.AsyncClient() as client:
                    response = await client.post(url, data=data, timeout=timeout)
                    response_data = response.json()
                    if response.status_code != 200 or not response_data.get("success"):
                        logger.info("[yellow]imgbb failed, trying next image host")
                        return {"status": "failed", "reason": "imgbb upload failed"}

                    img_url = response_data["data"].get("medium", {}).get("url") or response_data["data"]["thumb"]["url"]
                    raw_url = response_data["data"]["image"]["url"]
                    web_url = response_data["data"]["url_viewer"]

                    logger.debug(f"[green]Image URLs: img_url={img_url}, raw_url={raw_url}, web_url={web_url}")

                    return {"status": "success", "img_url": img_url, "raw_url": raw_url, "web_url": web_url}

            except httpx.TimeoutException:
                logger.info("[red]Request timed out. The server took too long to respond.")
                return {"status": "failed", "reason": "Request timed out"}

            except ValueError as e:  # JSON decoding error
                logger.info(f"[red]Invalid JSON response: {e}")
                return {"status": "failed", "reason": "Invalid JSON response"}

            except httpx.RequestError as e:
                logger.info(f"[red]Request failed with error: {e}")
                return {"status": "failed", "reason": str(e)}

        elif img_host == "dalexni":
            url = "https://dalexni.com/1/upload"
            try:
                async with aiofiles.open(image, "rb") as img_file:
                    encoded_image = base64.b64encode(await img_file.read()).decode("utf8")

                data = {
                    "key": config["DEFAULT"]["dalexni_api"],
                    "image": encoded_image,
                }
                async with httpx.AsyncClient() as client:
                    response = await client.post(url, data=data, timeout=timeout)
                    response_data = response.json()
                    if response.status_code != 200 or not response_data.get("success"):
                        logger.info("[yellow]DALEXNI failed, trying next image host")
                        return {"status": "failed", "reason": "DALEXNI upload failed"}

                    img_url = response_data["data"].get("medium", {}).get("url") or response_data["data"]["thumb"]["url"]
                    raw_url = response_data["data"]["image"]["url"]
                    web_url = response_data["data"]["url_viewer"]

                    logger.debug(f"[green]Image URLs: img_url={img_url}, raw_url={raw_url}, web_url={web_url}")

                    return {"status": "success", "img_url": img_url, "raw_url": raw_url, "web_url": web_url}

            except httpx.TimeoutException:
                logger.info("[red]Request timed out. The server took too long to respond.")
                return {"status": "failed", "reason": "Request timed out"}

            except ValueError as e:  # JSON decoding error
                logger.info(f"[red]Invalid JSON response: {e}")
                return {"status": "failed", "reason": "Invalid JSON response"}

            except httpx.RequestError as e:
                logger.info(f"[red]Request failed with error: {e}")
                return {"status": "failed", "reason": str(e)}

        elif img_host == "ptscreens":
            url = "https://ptscreens.com/api/1/upload"
            try:
                headers = {"X-API-Key": config["DEFAULT"]["ptscreens_api"]}

                async with httpx.AsyncClient() as client, aiofiles.open(image, "rb") as file:
                    files = {"source": ("file-upload[0]", await file.read())}

                    response = await client.post(url, headers=headers, files=files, timeout=timeout)
                    response_data = response.json()

                    if response.status_code != 200:
                        logger.info(f"[yellow]ptscreens upload failed: {response_data.get('error', {}).get('message', 'Unknown error')} {(response.status_code)}")
                        return {"status": "failed", "reason": f"ptscreens upload failed: {response_data.get('error', {}).get('message', 'Unknown error')}"}

                    img_url = response_data["image"]["medium"]["url"]
                    raw_url = response_data["image"]["url"]
                    web_url = response_data["image"]["url_viewer"]

                    logger.debug(f"[green]Image URLs: img_url={img_url}, raw_url={raw_url}, web_url={web_url}")

            except httpx.TimeoutException:
                logger.info("[red]Request timed out. The server took too long to respond.")
                return {"status": "failed", "reason": "Request timed out"}
            except httpx.RequestError as e:
                logger.info(f"[red]Request failed with error: {e}")
                return {"status": "failed", "reason": str(e)}
            except ValueError as e:
                logger.info(f"[red]Invalid JSON response from ptscreens: {e}")
                return {"status": "failed", "reason": "Invalid JSON response"}

        elif img_host == "utppm":
            url = "https://utp.pm/api/1/upload"
            try:
                async with aiofiles.open(image, "rb") as img_file:
                    encoded_image = base64.b64encode(await img_file.read()).decode("utf8")

                data = {"source": encoded_image}
                headers = {
                    "X-API-Key": config["DEFAULT"]["utppm_api"],
                }

                async with httpx.AsyncClient() as client:
                    response = await client.post(url, data=data, headers=headers, timeout=timeout)
                    response_data = response.json()

                    if response.status_code != 200:
                        logger.info("[yellow]utppm failed, trying next image host")
                        return {"status": "failed", "reason": "utppm upload failed"}

                    img_url = response_data["image"]["medium"]["url"]
                    raw_url = response_data["image"]["url"]
                    web_url = response_data["image"]["url_viewer"]

                    logger.debug(f"[green]Image URLs: img_url={img_url}, raw_url={raw_url}, web_url={web_url}")

            except httpx.TimeoutException:
                logger.info("[red]Request timed out. The server took too long to respond.")
                return {"status": "failed", "reason": "Request timed out"}
            except httpx.RequestError as e:
                logger.info(f"[red]Request failed with error: {e}")
                return {"status": "failed", "reason": str(e)}
            except ValueError as e:
                logger.info(f"[red]Invalid JSON response from utppm: {e}")
                return {"status": "failed", "reason": "Invalid JSON response"}

        elif img_host == "onlyimage":
            url = "https://onlyimage.org/api/1/upload"
            try:
                async with aiofiles.open(image, "rb") as img_file:
                    encoded_image = base64.b64encode(await img_file.read()).decode("utf8")

                data = {"image": encoded_image}
                headers = {
                    "X-API-Key": config["DEFAULT"]["onlyimage_api"],
                }

                async with httpx.AsyncClient() as client:
                    response = await client.post(url, data=data, headers=headers, timeout=timeout)
                    response_data = response.json()

                    if response.status_code != 200 or not response_data.get("success"):
                        logger.info("[yellow]OnlyImage failed, trying next image host")
                        return {"status": "failed", "reason": "OnlyImage upload failed"}

                    img_url = response_data["data"]["medium"]["url"]
                    raw_url = response_data["data"]["image"]["url"]
                    web_url = response_data["data"]["url_viewer"]

                    logger.debug(f"[green]Image URLs: img_url={img_url}, raw_url={raw_url}, web_url={web_url}")

            except httpx.TimeoutException:
                logger.info("[red]Request timed out. The server took too long to respond.")
                return {"status": "failed", "reason": "Request timed out"}
            except httpx.RequestError as e:
                logger.info(f"[red]Request failed with error: {e}")
                return {"status": "failed", "reason": str(e)}
            except ValueError as e:
                logger.info(f"[red]Invalid JSON response from OnlyImage: {e}")
                return {"status": "failed", "reason": "Invalid JSON response"}

        elif img_host == "pixhost":
            url = "https://api.pixhost.to/images"
            try:
                data = {"content_type": "0", "max_th_size": 350}

                async with httpx.AsyncClient() as client, aiofiles.open(image, "rb") as file:
                    files = {"img": ("file-upload[0]", await file.read())}

                    response = await client.post(url, data=data, files=files, timeout=timeout)

                    if response.status_code != 200:
                        logger.info(f"[yellow]pixhost failed with status code {response.status_code}, trying next image host")
                        return {"status": "failed", "reason": f"pixhost upload failed with status code {response.status_code}"}

                    try:
                        response_data = response.json()
                        if "th_url" not in response_data:
                            logger.info("[yellow]pixhost failed: Invalid response format")
                            return {"status": "failed", "reason": "Invalid response from pixhost"}

                        raw_url = response_data["th_url"].replace("https://t", "https://img").replace("/thumbs/", "/images/")
                        img_url = response_data["th_url"]
                        web_url = response_data["show_url"]

                        logger.debug(f"[green]Image URLs: img_url={img_url}, raw_url={raw_url}, web_url={web_url}")

                    except ValueError as e:
                        logger.info(f"[red]Invalid JSON response from pixhost: {e}")
                        return {"status": "failed", "reason": "Invalid JSON response"}

            except httpx.TimeoutException:
                logger.info("[red]Request to pixhost timed out. The server took too long to respond.")
                return {"status": "failed", "reason": "Request timed out"}

            except httpx.RequestError as e:
                logger.info(f"[red]pixhost request failed with error: {e}")
                return {"status": "failed", "reason": str(e)}

        elif img_host == "lensdump":
            url = "https://lensdump.com/api/1/upload"
            try:
                async with aiofiles.open(image, "rb") as img_file:
                    data = {"image": base64.b64encode(await img_file.read()).decode("utf8")}
                headers = {"X-API-Key": config["DEFAULT"]["lensdump_api"]}
                async with httpx.AsyncClient() as client:
                    response = await client.post(url, data=data, headers=headers, timeout=timeout)
                    response_data = response.json()
                    if response_data.get("status_code") == 200:
                        img_url = response_data["data"]["image"]["url"]
                        raw_url = response_data["data"]["image"]["url"]
                        web_url = response_data["data"]["url_viewer"]
            except httpx.TimeoutException:
                logger.info("[red]Request timed out. The server took too long to respond.")
                return {"status": "failed", "reason": "Request timed out"}
            except ValueError as e:
                logger.info(f"[red]Invalid JSON response: {e}")
                return {"status": "failed", "reason": "Invalid JSON response"}
            except httpx.RequestError as e:
                logger.info(f"[red]Request failed with error: {e}")
                return {"status": "failed", "reason": str(e)}

        elif img_host in ("zipline", "midnightscene"):
            if img_host == "midnightscene":
                url = "https://img.midnightscene.cc/api/upload"
                api_key = config["DEFAULT"].get("midnightscene_api_key")
                host_name = "MidnightScene"
            else:
                url = config["DEFAULT"].get("zipline_url")
                api_key = config["DEFAULT"].get("zipline_api_key")
                host_name = "Zipline"

            if not url or not api_key:
                logger.error(f"[red]Error: Missing {host_name} URL or API key in config.")
                return {"status": "failed", "reason": f"Missing {host_name} URL or API key"}

            try:
                async with aiofiles.open(image, "rb") as img_file:
                    filename = Path(image).name
                    file_bytes = await img_file.read()
                headers = {
                    "Authorization": f"{api_key}",
                }

                async with httpx.AsyncClient() as client:
                    response = await client.post(url, files={"file": (filename, file_bytes)}, headers=headers, timeout=timeout)
                    if response.status_code == 200:
                        zipline_response_data: object = response.json()
                        zipline_response_mapping = cast(dict[str, Any], zipline_response_data) if isinstance(zipline_response_data, dict) else {}
                        zipline_files_value = zipline_response_mapping.get("files")
                        if not isinstance(zipline_files_value, list) or not zipline_files_value:
                            return {"status": "failed", "reason": f"No valid URL returned from {host_name}"}

                        file_entry: object = cast(list[object], zipline_files_value)[0]
                        zipline_img_url: str | None = None
                        if isinstance(file_entry, dict):
                            file_entry_dict = cast(dict[str, object], file_entry)
                            candidate_url = file_entry_dict.get("url")
                            if isinstance(candidate_url, str):
                                zipline_img_url = candidate_url
                        elif isinstance(file_entry, str):
                            zipline_img_url = file_entry
                        if not zipline_img_url:
                            return {"status": "failed", "reason": f"No valid URL returned from {host_name}"}
                        zipline_raw_url = zipline_img_url.replace("/u/", "/r/")
                        zipline_web_url = zipline_img_url.replace("/u/", "/r/")
                        return {
                            "status": "success",
                            "img_url": zipline_img_url,
                            "raw_url": zipline_raw_url,
                            "web_url": zipline_web_url,
                        }

                    return {"status": "failed", "reason": f"{host_name} upload failed: {response.text}"}
            except httpx.TimeoutException:
                logger.info("[red]Request timed out. The server took too long to respond.")
                return {"status": "failed", "reason": "Request timed out"}

            except ValueError as e:  # JSON decoding error
                logger.info(f"[red]Invalid JSON response: {e}")
                return {"status": "failed", "reason": "Invalid JSON response"}

            except httpx.RequestError as e:
                logger.info(f"[red]Request failed with error: {e}")
                return {"status": "failed", "reason": str(e)}

        elif img_host == "passtheimage":
            url = "https://passtheima.ge/api/1/upload"
            try:
                pass_api_key = config["DEFAULT"].get("passtheima_ge_api")
                if not pass_api_key:
                    logger.info("[red]Passtheimage API key not found in config.")
                    return {"status": "failed", "reason": "Missing Passtheimage API key"}

                headers = {"X-API-Key": pass_api_key}

                async with httpx.AsyncClient() as client, aiofiles.open(image, "rb") as img_file:
                    files = {"source": (Path(image).name, await img_file.read())}
                    response = await client.post(url, headers=headers, files=files, timeout=timeout)

                    if "application/json" in response.headers.get("Content-Type", ""):
                        response_data = response.json()
                    else:
                        logger.info(f"[red]Passtheimage did not return JSON. Status: {response.status_code}, Response: {response.text[:200]}")
                        return {"status": "failed", "reason": f"Non-JSON response from passtheimage: {response.status_code}"}

                    if response.status_code != 200 or response_data.get("status_code") != 200:
                        error_message = response_data.get("error", {}).get("message", "Unknown error")
                        error_code = response_data.get("error", {}).get("code", "Unknown code")
                        logger.info(f"[yellow]Passtheimage failed (code: {error_code}): {error_message}")
                        return {"status": "failed", "reason": f"passtheimage upload failed: {error_message}"}

                    if "image" in response_data:
                        img_url = response_data["image"]["url"]
                        raw_url = response_data["image"]["url"]
                        web_url = response_data["image"]["url_viewer"]

                    if not img_url or not raw_url or not web_url:
                        logger.info(f"[yellow]Incomplete URL data from passtheimage response: {response_data}")
                        return {"status": "failed", "reason": "Incomplete URL data from passtheimage"}

                    return {"status": "success", "img_url": img_url, "raw_url": raw_url, "web_url": web_url, "local_file_path": image}

            except httpx.TimeoutException:
                logger.info("[red]Request to passtheimage timed out after 60 seconds")
                return {"status": "failed", "reason": "Request timed out"}
            except httpx.RequestError as e:
                logger.info(f"[red]Request to passtheimage failed with error: {e}")
                return {"status": "failed", "reason": str(e)}
            except ValueError as e:
                logger.info(f"[red]Invalid JSON response from passtheimage: {e}")
                return {"status": "failed", "reason": "Invalid JSON response"}
            except Exception as e:
                logger.error(f"[red]Unexpected error with passtheimage: {e!s}")
                return {"status": "failed", "reason": f"Unexpected error: {e!s}"}

        elif img_host == "seedpool_cdn":
            url = "https://i.seedpool.org/upload"
            api_key = config["DEFAULT"].get("seedpool_cdn_api")

            if not api_key:
                logger.info("[red]SEEDPOOL CDN API key not found in config.")
                return {"status": "failed", "reason": "Missing SEEDPOOL CDN API key"}

            try:
                headers = {"Authorization": f"Bearer {api_key}"}

                async with httpx.AsyncClient() as client, aiofiles.open(image, "rb") as img_file:
                    files = {"files[]": (Path(image).name, await img_file.read())}

                    response = await client.post(url, headers=headers, files=files, timeout=timeout)

                    if response.status_code not in (200, 201):
                        logger.info(f"[yellow]SEEDPOOL CDN failed with status code {response.status_code}, trying next image host")
                        return {"status": "failed", "reason": f"SEEDPOOL CDN upload failed with status code {response.status_code}"}

                    response_data = response.json()

                    if "files" in response_data and len(response_data["files"]) > 0:
                        file_data = response_data["files"][0]

                        # Use medium variant as primary, fallback to base URL
                        img_url = file_data.get("variants", {}).get("medium", file_data["url"])
                        raw_url = file_data["url"]
                        web_url = file_data["url"]

                        # Use thumbnail_url if available, otherwise use thumb variant
                        if "thumbnail_url" in file_data:
                            img_url = file_data["thumbnail_url"]
                        elif "thumb" in file_data.get("variants", {}):
                            img_url = file_data["variants"]["thumb"]

                        logger.debug(f"[green]SEEDPOOL CDN upload successful: {file_data['cdn_id']}")
                        logger.debug(f"[green]Image URLs: img_url={img_url}, raw_url={raw_url}, web_url={web_url}")

                        return {"status": "success", "img_url": img_url, "raw_url": raw_url, "web_url": web_url}
                    logger.info("[yellow]SEEDPOOL CDN returned empty files array")
                    return {"status": "failed", "reason": "No files in SEEDPOOL CDN response"}

            except httpx.TimeoutException:
                logger.info("[red]Request to SEEDPOOL CDN timed out.")
                return {"status": "failed", "reason": "Request timed out"}
            except httpx.RequestError as e:
                logger.info(f"[red]SEEDPOOL CDN request failed: {e}")
                return {"status": "failed", "reason": str(e)}
            except ValueError as e:
                logger.info(f"[red]Invalid JSON response from SEEDPOOL CDN: {e}")
                return {"status": "failed", "reason": "Invalid JSON response"}
            except Exception as e:
                logger.error(f"[red]Unexpected error with SEEDPOOL CDN: {e}")
                return {"status": "failed", "reason": f"Unexpected error: {e!s}"}

        elif img_host == "sharex":
            # Generic "ShareX-style" image host (IMageHosting and similar).
            url = config["DEFAULT"].get("sharex_url", "https://img.digitalcore.club/api/upload")
            api_key = config["DEFAULT"].get("sharex_api_key")

            if not api_key:
                logger.info("[red]ShareX image host token not found in config (sharex_api_key).[/red]")
                return {"status": "failed", "reason": "Missing ShareX image host token"}

            try:
                headers = {"Authorization": f"{api_key}"}
                data = {"title": "Upload-Assistant screenshot"}

                async with httpx.AsyncClient() as client, aiofiles.open(image, "rb") as img_file:
                    files = {"file": (Path(image).name, await img_file.read())}
                    response = await client.post(url, headers=headers, data=data, files=files, timeout=timeout)

                    content_type = response.headers.get("Content-Type", "")
                    if "application/json" in content_type:
                        response_data = response.json()
                    else:
                        logger.info(f"[red]ShareX image host did not return JSON. Status: {response.status_code}, Response: {response.text[:200]}[/red]")
                        return {"status": "failed", "reason": f"Non-JSON response from sharex image host: {response.status_code}"}

                    if response.status_code not in (200, 201):
                        message = response_data.get("message") or response_data.get("error") or response.text[:200]
                        logger.info(f"[yellow]ShareX image host upload failed ({response.status_code}): {message}[/yellow]")
                        return {"status": "failed", "reason": f"sharex upload failed: {message}"}

                    link = response_data.get("data", {}).get("link") or response_data.get("link")
                    if not link:
                        logger.info(f"[yellow]ShareX image host response missing link: {response_data}[/yellow]")
                        return {"status": "failed", "reason": "No link in sharex response"}

                    img_url = link
                    raw_url = link
                    web_url = link

                    logger.debug(f"[green]ShareX image host upload successful: {link}[/green]")

                    return {"status": "success", "img_url": img_url, "raw_url": raw_url, "web_url": web_url, "local_file_path": image}

            except httpx.TimeoutException:
                logger.info("[red]Request to ShareX image host timed out.[/red]")
                return {"status": "failed", "reason": "Request timed out"}
            except httpx.RequestError as e:
                logger.info(f"[red]Request to ShareX image host failed with error: {e}[/red]")
                return {"status": "failed", "reason": str(e)}
            except ValueError as e:
                logger.info(f"[red]Invalid JSON response from ShareX image host: {e}[/red]")
                return {"status": "failed", "reason": "Invalid JSON response"}
            except Exception as e:
                logger.error(f"[red]Unexpected error with ShareX image host: {e!s}[/red]")
                return {"status": "failed", "reason": f"Unexpected error: {e!s}"}

        elif img_host == "lostimg":
            url = "https://lostimg.cc/api/v1/images"
            try:
                lostimg_api_key = config["DEFAULT"].get("lostimg_api")
                if not lostimg_api_key:
                    logger.info("[red]Lostimg API key not found in config.[/red]")
                    return {"status": "failed", "reason": "Missing Lostimg API key"}

                headers = {"Authorization": f"Bearer {lostimg_api_key}"}

                async with httpx.AsyncClient() as client, aiofiles.open(image, "rb") as img_file:
                    files = {"file[]": (Path(image).name, await img_file.read())}
                    response = await client.post(url, headers=headers, files=files, timeout=timeout)

                    content_type = response.headers.get("Content-Type", "")
                    if "application/json" in content_type:
                        response_data = response.json()
                    else:
                        logger.info(f"[red]Lostimg did not return JSON. Status: {response.status_code}, Response: {response.text[:200]}[/red]")
                        return {"status": "failed", "reason": f"Non-JSON response from lostimg: {response.status_code}"}

                    if response.status_code != 200:
                        error_message = response_data.get("error", "Unknown error")
                        logger.info(f"[yellow]Lostimg failed (status: {response.status_code}): {error_message}[/yellow]")
                        return {"status": "failed", "reason": f"lostimg upload failed: {error_message}"}

                    img_url = response_data.get("url")
                    if not img_url:
                        logger.info(f"[yellow]Incomplete URL data from lostimg response: {response_data}[/yellow]")
                        return {"status": "failed", "reason": "Incomplete URL data from lostimg"}

                    raw_url = img_url
                    web_url = img_url

                    logger.debug(f"[green]Image URLs: img_url={img_url}, raw_url={raw_url}, web_url={web_url}[/green]")

                    return {"status": "success", "img_url": img_url, "raw_url": raw_url, "web_url": web_url, "local_file_path": image}

            except httpx.TimeoutException:
                logger.info("[red]Request to Lostimg timed out.[/red]")
                return {"status": "failed", "reason": "Request timed out"}
            except httpx.RequestError as e:
                logger.info(f"[red]Request to Lostimg failed with error: {e}[/red]")
                return {"status": "failed", "reason": str(e)}
            except ValueError as e:
                logger.info(f"[red]Invalid JSON response from Lostimg: {e}[/red]")
                return {"status": "failed", "reason": "Invalid JSON response"}
            except Exception as e:
                logger.error(f"[red]Unexpected error with Lostimg: {e!s}[/red]")
                return {"status": "failed", "reason": f"Unexpected error: {e!s}"}

        if img_url and raw_url and web_url:
            return {"status": "success", "img_url": img_url, "raw_url": raw_url, "web_url": web_url, "local_file_path": image}
        return {"status": "failed", "reason": f"Failed to upload image to {img_host}. No URLs received."}

    except Exception as e:
        return {"status": "failed", "reason": str(e)}


async def _upload_screens(
    config: dict[str, Any],
    meta: Meta,
    screens: int,
    img_host_num: int,
    i: int,
    total_screens: int,
    custom_img_list: list[str],
    return_dict: dict[str, Any],
    retry_mode: bool = False,
    max_retries: int = 3,
    allowed_hosts: list[str] | None = None,
) -> tuple[list[ImageDict], int]:
    """Select screenshots, throttle uploads, and collect successful results."""
    default_config = config.get("DEFAULT", {})
    if "image_list" not in meta:
        meta.image_list = []
    upload_start_time: float | None = None
    if meta.debug:
        upload_start_time = time.time()

    os.chdir(screenshots_dir(meta.base_dir, meta.uuid))

    initial_img_host = default_config[f"img_host_{img_host_num}"]
    img_host = meta.imghost

    image_list = meta.image_list

    # Treat empty allowed host list as no restriction
    if not allowed_hosts:
        allowed_hosts = None

    # Check if current host is allowed, if not find an approved one
    if allowed_hosts is not None and img_host not in allowed_hosts:
        logger.info(f"[yellow]Current image host '{img_host}' is not in allowed hosts: {allowed_hosts}[/yellow]")

        # Find the first approved host from config
        approved_host = None
        for i in range(1, 10):  # Check img_host_1 through img_host_9
            host_key = f"img_host_{i}"
            if host_key in default_config:
                host = default_config[host_key]
                if host in allowed_hosts:
                    approved_host = host
                    img_host_num = i
                    logger.info(f"[green]Switching to approved image host: {approved_host}[/green]")
                    break

        if approved_host:
            img_host = approved_host
        else:
            logger.info(f"[red]No approved image hosts found in config. Available: {allowed_hosts}[/red]")
            return image_list, len(image_list)

    logger.debug(f"[blue]Using image host: {img_host} (configured: {initial_img_host})[/blue]")
    using_custom_img_list = bool(custom_img_list)

    if "image_sizes" not in meta:
        meta.image_sizes = {}

    existing_raw_urls = {img["raw_url"] for img in image_list}

    def _record_uploaded_image(
        upload_image_list: list[ImageDict],
        upload_meta: Meta,
        upload: dict[str, Any],
        known_raw_urls: set[str],
    ) -> None:
        raw_url = upload["raw_url"]
        if raw_url in known_raw_urls:
            return

        new_image: ImageDict = {
            "img_url": upload["img_url"],
            "raw_url": raw_url,
            "web_url": upload["web_url"],
        }
        upload_image_list.append(new_image)
        known_raw_urls.add(raw_url)
        local_file_path = upload.get("local_file_path")
        if local_file_path:
            upload_meta.image_sizes[raw_url] = Path(local_file_path).stat().st_size

    # Handle image selection

    if using_custom_img_list:
        image_glob: list[str] = custom_img_list
        existing_images: list[ImageDict] = []
        existing_count = 0
    else:
        registered_screens = manifest_files(meta.base_dir, meta.uuid, "main")
        if registered_screens:
            image_glob = [str(path.relative_to(Path.cwd())) for path in registered_screens]
        else:
            image_patterns = ["*.png", ".[!.]*.png"]
            image_glob = []
            for pattern in image_patterns:
                glob_results = await asyncio.to_thread(lambda p=pattern: [str(path.relative_to(Path.cwd())) for path in Path.cwd().glob(p)])
                image_glob.extend(glob_results)

            unwanted_patterns = ["FILE*", "PLAYLIST*", "POSTER*"]
            unwanted_files: set[str] = set()
            for pattern in unwanted_patterns:
                glob_results = await asyncio.to_thread(lambda p=pattern: [str(path.relative_to(Path.cwd())) for path in Path.cwd().glob(p)])
                unwanted_files.update(glob_results)
                if pattern.startswith("FILE") or pattern.startswith("PLAYLIST") or pattern.startswith("POSTER"):
                    hidden_pattern = "." + pattern
                    hidden_glob_results = await asyncio.to_thread(lambda hp=hidden_pattern: [str(path.relative_to(Path.cwd())) for path in Path.cwd().glob(hp)])
                    unwanted_files.update(hidden_glob_results)

            image_glob = [file for file in image_glob if file not in unwanted_files]
            image_glob = list(set(image_glob))

        # Filter out menu screenshots from normal screenshot upload
        menu_basenames = set()
        if hasattr(meta, "menu_images") and meta.menu_images:
            for img in meta.menu_images:
                if isinstance(img, dict):
                    local_path = img.get("local_file_path") or img.get("raw_url")
                    if local_path:
                        menu_basenames.add(Path(local_path).name)

        def is_menu_screenshot(filename: str) -> bool:
            """Return whether filename belongs to a DVD menu screenshot."""
            if filename in menu_basenames:
                return True
            return "-VIDEO_TS-" in filename or "-VTS_" in filename

        image_glob = [file for file in image_glob if not is_menu_screenshot(file)]

        # Sort images by numeric suffix
        def extract_numeric_suffix(filename: str) -> float:
            """Return the numeric screenshot suffix for stable ordering."""
            match = re.search(r"-(\d+)\.png$", filename)
            return int(match.group(1)) if match else float("inf")

        image_glob.sort(key=extract_numeric_suffix)

        logger.debug(f"image globs (sorted): {image_glob}")

        existing_images = [img for img in image_list if img.get("img_url") and img.get("web_url")]
        existing_count = len(existing_images)

        uploaded_image_files = return_dict.get("_uploaded_image_files")
        if isinstance(uploaded_image_files, set):
            image_glob = [file for file in image_glob if str(Path(file).resolve()) not in uploaded_image_files]

    # Determine images needed
    images_needed = max(0, total_screens - existing_count) if not retry_mode else total_screens
    logger.debug(f"[blue]Existing images: {existing_count}, Images needed: {images_needed}, Total screens: {total_screens}[/blue]")

    # Some upload types (notably BOOK) legitimately have no screenshots.  The
    # selected host can differ from img_host_1 when supplied via --imghost, so
    # do not make this no-op conditional on the configured initial host.
    if total_screens <= 0:
        logger.debug("[yellow]Skipping upload: no screenshots required.[/yellow]")
        return image_list, 0

    if existing_count >= total_screens and not retry_mode and img_host == initial_img_host and not using_custom_img_list:
        logger.debug(f"[yellow]Skipping upload: {existing_count} existing, {total_screens} required.")
        return image_list, total_screens

    if images_needed == 0:
        logger.debug("[yellow]Skipping upload: no additional images required.[/yellow]")
        return image_list, total_screens

    if not image_glob:
        logger.debug("[yellow]Skipping upload: no new source images available.[/yellow]")
        return image_list, len(image_list)

    upload_tasks: list[tuple[int, str, str, dict[str, Any], Meta]] = [(index, image, img_host, config, meta) for index, image in enumerate(image_glob[:images_needed])]

    # Concurrency Control
    default_pool_size = len(upload_tasks)
    host_limits = {"onlyimage": 6, "ptscreens": 6, "lensdump": 1, "passtheimage": 6}
    configured_concurrency = default_config.get("image_upload_concurrency", 0)
    try:
        configured_concurrency = int(configured_concurrency)
    except OverflowError, TypeError, ValueError:
        configured_concurrency = 0
    pool_size = configured_concurrency if configured_concurrency > 0 else host_limits.get(img_host, default_pool_size)
    max_workers = min(len(upload_tasks), pool_size)
    semaphore = asyncio.Semaphore(max_workers)

    configured_delay = default_config.get("image_upload_delay", 0)
    try:
        parsed_delay = float(configured_delay)
        image_upload_delay = max(0.0, parsed_delay) if math.isfinite(parsed_delay) else 0.0
    except TypeError, ValueError:
        image_upload_delay = 0.0
    wait_for_image_start_slot = _build_image_start_limiter(image_upload_delay)

    # Track running tasks for cancellation
    running_tasks: set[asyncio.Task[dict[str, Any]]] = set()

    async def async_upload(
        task: tuple[int, str, str, dict[str, Any], Meta],
        max_retries: int = 3,
    ) -> tuple[int, dict[str, Any]] | None:
        """Upload image with concurrency control and retry logic."""
        index, *task_args = task
        retry_count = 0

        async with semaphore:
            while retry_count <= max_retries:
                future: asyncio.Task[dict[str, Any]] | None = None
                try:
                    await wait_for_image_start_slot()
                    future = asyncio.create_task(upload_image_task(task_args))
                    running_tasks.add(future)

                    try:
                        result = await asyncio.wait_for(future, timeout=60.0)
                        running_tasks.discard(future)

                        if result.get("status") == "success":
                            if not using_custom_img_list:
                                uploaded_image_files = return_dict.setdefault("_uploaded_image_files", set())
                                if isinstance(uploaded_image_files, set):
                                    uploaded_image_files.add(str(Path(str(task_args[0])).resolve()))
                            return (index, result)
                        reason = result.get("reason", "Unknown error")
                        if "duplicate" in reason.lower():
                            logger.info(f"[yellow]Skipping host because duplicate image {index}: {reason}[/yellow]")
                            return None
                        if "api key" in reason.lower():
                            logger.info(f"[red]API key error for {img_host}. Aborting further attempts.[/red]")
                            return None
                        if retry_count < max_retries:
                            retry_count += 1
                            logger.info(f"[yellow]Retry {retry_count}/{max_retries} for image {index}: {reason}[/yellow]")
                            await asyncio.sleep(1.1 * retry_count)
                            continue
                        logger.error(f"[red]Failed to upload image {index} after {max_retries} attempts: {reason}[/red]")
                        return None

                    except TimeoutError:
                        logger.info(f"[red]Upload task {index} timed out after 60 seconds[/red]")
                        if future in running_tasks:
                            future.cancel()
                            running_tasks.discard(future)

                        if retry_count < max_retries:
                            retry_count += 1
                            logger.info(f"[yellow]Retry {retry_count}/{max_retries} for image {index} after timeout[/yellow]")
                            await asyncio.sleep(1.1 * retry_count)
                            continue
                        return None

                except asyncio.CancelledError:
                    logger.info(f"[red]Upload task {index} cancelled.[/red]")
                    if future and future in running_tasks:
                        future.cancel()
                        running_tasks.discard(future)
                    return None

                except Exception as e:
                    logger.error(f"[red]Error during upload for image {index}: {e!s}[/red]")
                    if retry_count < max_retries:
                        retry_count += 1
                        logger.info(f"[yellow]Retry {retry_count}/{max_retries} for image {index}: {e!s}[/yellow]")
                        await asyncio.sleep(1.5 * retry_count)
                        continue
                    logger.error(f"[red]Error during upload for image {index} after {max_retries} attempts: {e!s}[/red]")
                    return None

        return None

    try:
        max_retries = 3
        results: list[tuple[int, dict[str, Any]]] = []
        try:
            upload_results = await asyncio.gather(*[async_upload(task, max_retries) for task in upload_tasks])
            results = [res for res in upload_results if res is not None]
            results.sort(key=lambda x: x[0])
        except Exception as e:
            logger.error(f"[red]Error during uploads: {e!s}[/red]")

        successfully_uploaded = [(index, result) for index, result in results if result["status"] == "success"]
        logger.debug(f"[blue]Successfully uploaded {len(successfully_uploaded)} out of {len(upload_tasks)} attempted uploads.[/blue]")

        # Ensure we only switch hosts if necessary
        logger.debug(f"[blue]Double checking current image host: {img_host}, Initial image host: {initial_img_host}[/blue]")
        logger.debug(f"[blue]retry_mode: {retry_mode}, using_custom_img_list: {using_custom_img_list}[/blue]")
        logger.debug(f"[blue]successfully_uploaded={len(successfully_uploaded)}, meta.image_list={len(image_list)}, cutoff={meta.cutoff}[/blue]")
        if len(successfully_uploaded) < len(upload_tasks):
            # Preserve partial successes before recursing so the next host only
            # needs to handle failed source files and the accumulated list is
            # not lost when fallback completes.
            if not using_custom_img_list:
                for _index, upload in successfully_uploaded:
                    _record_uploaded_image(image_list, meta, upload, existing_raw_urls)

            # Keep walking the configured hosts after a fallback also fails. The
            # previous retry_mode guard stopped the chain at img_host_2.
            next_host_num = img_host_num + 1
            while next_host_num <= 9:
                next_host_key = f"img_host_{next_host_num}"
                if next_host_key not in default_config:
                    next_host_num += 1
                    continue

                next_host = str(default_config.get(next_host_key) or "").strip().lower()
                if not next_host or (allowed_hosts is not None and next_host not in allowed_hosts):
                    next_host_num += 1
                    continue

                meta.imghost = next_host
                logger.info(f"[cyan]Switching to the next image host: {meta.imghost}[/cyan]")

                gc.collect()
                return await _upload_screens(
                    config,
                    meta,
                    screens,
                    next_host_num,
                    i,
                    total_screens,
                    custom_img_list,
                    return_dict,
                    retry_mode=True,
                    allowed_hosts=allowed_hosts,
                )
            logger.info("[red]No more image hosts available. Aborting upload process.")
            return image_list, len(image_list)

        # Process and store successfully uploaded images
        new_images: list[ImageDict] = []
        for _index, upload in successfully_uploaded:
            raw_url = upload["raw_url"]
            new_image = {"img_url": upload["img_url"], "raw_url": raw_url, "web_url": upload["web_url"]}
            # Custom uploads (disc menus and spectrograms) are not added to
            # ``meta.image_list``.  Keep their local source so a tracker that
            # rejects the initially selected host can re-upload the same asset.
            local_file_path = upload.get("local_file_path")
            if local_file_path:
                new_image["local_file_path"] = str(local_file_path)
            new_images.append(new_image)
            if not using_custom_img_list:
                if raw_url not in existing_raw_urls:
                    logger.debug(f"[blue]Adding {raw_url} to image_list")
                _record_uploaded_image(image_list, meta, upload, existing_raw_urls)

        if len(new_images) and len(new_images) > 0:
            if not using_custom_img_list:
                logger.info(f"[green]Successfully obtained and uploaded {len(new_images)} images.")
        else:
            raise Exception("No images uploaded. Configure additional image hosts or use a different -ih")

        if meta.debug and upload_start_time is not None:
            logger.info(f"Screenshot uploads processed in {time.time() - upload_start_time:.4f} seconds")

        return (new_images, len(new_images)) if using_custom_img_list else (image_list, len(image_list))

    except asyncio.CancelledError:
        logger.info("\n[red]Upload process interrupted! Cancelling tasks...[/red]")

        # Cancel running tasks
        for task in running_tasks:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

        return image_list, len(image_list)

    finally:
        # Cleanup
        gc.collect()


async def imgbox_upload(
    chdir: str,
    image_glob: list[str],
    return_dict: dict[str, Any],
) -> list[dict[str, str]]:
    """Upload images to Imgbox and store their returned URLs."""
    try:
        os.chdir(chdir)
        image_list: list[dict[str, str]] = []

        async with pyimgbox.Gallery(thumb_width=350, square_thumbs=False) as gallery:

            async def process_image(image: str) -> None:
                """Upload one image through the active Imgbox gallery."""
                try:
                    async for submission in cast(Any, gallery).add([image]):
                        submission_data = cast(dict[str, Any], submission)
                        if not submission_data.get("success"):
                            logger.error(f"[red]Error uploading to imgbox: [yellow]{submission_data.get('error')}[/yellow][/red]")
                        else:
                            web_url = cast(str | None, submission_data.get("web_url"))
                            img_url = cast(str | None, submission_data.get("thumbnail_url"))
                            raw_url = cast(str | None, submission_data.get("image_url"))
                            if web_url and img_url and raw_url:
                                image_dict: dict[str, str] = {"web_url": web_url, "img_url": img_url, "raw_url": raw_url}
                                image_list.append(image_dict)
                            else:
                                logger.info(f"[red]Incomplete URLs received for image: {image}")
                except Exception as e:
                    logger.error(f"[red]Error during upload for {image}: {e!s}")

            for image in image_glob:
                await process_image(image)

        return_dict["image_list"] = image_list
        return image_list

    except Exception as e:
        logger.info(f"[red]An error occurred while uploading images to imgbox: {e!s}")
        return []
