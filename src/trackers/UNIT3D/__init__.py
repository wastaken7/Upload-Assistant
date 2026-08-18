# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import asyncio
import contextlib
import functools
import json
import platform
import re
from pathlib import Path
from typing import Any

import aiofiles
import httpx

from src.artwork import is_valid_image_bytes
from src.cogs.redaction import Redaction
from src.console import logger
from src.get_desc import DescriptionBuilder
from src.meta import Meta
from src.trackers.common import Common

type QueryValue = str | int | float | bool | None
type ParamsList = list[tuple[str, QueryValue]]


@functools.lru_cache(maxsize=32)
def get_tracker_unit3d_overrides(tracker_name: str) -> dict[str, dict[str, str]]:
    if not tracker_name:
        return {}
    base_data_dir = Path(__file__).resolve().parent.parent.parent.parent / "data" / "trackers" / "unit3d"
    file_path = base_data_dir / f"{tracker_name.lower()}.json"
    if file_path.exists():
        with contextlib.suppress(Exception), file_path.open(encoding="utf-8") as f:
            return json.load(f)
    return {}


class UNIT3D:
    auth_type = "unit3d_api"
    supported_categories: tuple[str, ...] = ("TV", "MOVIE")
    tracker: str = ""
    banned_groups: tuple[str, ...] = ()
    base_url: str = ""
    pending_url: str = ""
    search_url: str = ""
    upload_url: str = ""

    def __init__(self, config: dict[str, Any], tracker_name: str):
        self.config = config
        self.tracker = tracker_name
        self.common = Common(config)
        self.tracker_config: dict[str, Any] = self.config["TRACKERS"].get(self.tracker, {})

        # Normalize announce_url: must be a non-empty string after stripping
        raw_announce = self.tracker_config.get("announce_url")
        self.announce_url = raw_announce.strip() if isinstance(raw_announce, str) else ""

        # Normalize api_key: must be a non-empty string after stripping
        raw_api_key = self.tracker_config.get("api_key")
        self.api_key = raw_api_key.strip() if isinstance(raw_api_key, str) else ""

    async def get_additional_checks(self, meta: Meta) -> bool:
        _meta = meta
        return True

    async def get_search_urls(self, meta: Meta, request_params: ParamsList) -> list[tuple[str, ParamsList, bool]]:
        _ = meta
        urls: list[tuple[str, ParamsList, bool]] = [(self.search_url, request_params, False)]
        if getattr(self, "pending_url", None):
            urls.append((self.pending_url, request_params, True))
        return urls

    async def search_existing(self, meta: Meta) -> list[dict[str, Any]]:
        dupes: list[dict[str, Any]] = []
        params_list: ParamsList | None = None
        category = meta.category

        # Ensure tracker_status keys exist before any potential writes
        meta.setdefault("tracker_status", {})
        meta.tracker_status.setdefault(self.tracker, {})
        headers = {
            "authorization": f"Bearer {self.api_key}",
            "accept": "application/json",
        }

        if category in ("MOVIE", "TV"):
            params_dict: dict[str, str] = {
                "name": "",
                "perPage": "100",
            }
            if meta.tmdb is not None:
                params_dict["tmdbId"] = str(meta.tmdb)
            else:
                # TMDB identifies the work across tracker subcategories (for
                # example, TV and Anime). Keep the category only as a fallback
                # for manually constructed metadata without a TMDB ID.
                params_dict["categories[]"] = (await self.get_category_id(meta))["category_id"]

            if self.tracker not in ["OLDTOONSWORLD"]:
                resolutions = await self.get_resolution_id(meta)
                resolution_id = resolutions["resolution_id"]
                if resolution_id in ["3", "4"]:
                    # Convert params to list of tuples to support duplicate keys
                    params_list = list(params_dict.items())
                    params_list.append(("resolutions[]", "3"))
                    params_list.append(("resolutions[]", "4"))
                else:
                    params_dict["resolutions[]"] = resolution_id

            if self.tracker not in ["SEEDPOOL", "SKIPTHECOMMERCIALS"]:
                type_id = (await self.get_type_id(meta))["type_id"]
                if params_list is not None:
                    params_list.append(("types[]", type_id))
                else:
                    params_dict["types[]"] = type_id

            if meta.category == "TV":
                season_value = f" {meta.season}"
                if params_list is not None:
                    # Update the 'name' parameter in the list
                    params_list = [(k, (v + season_value if k == "name" and isinstance(v, str) else v)) for k, v in params_list]
                else:
                    params_dict["name"] = params_dict["name"] + season_value

        else:
            params_dict = {
                "name": meta.title or meta.name,
                "categories[]": (await self.get_category_id(meta))["category_id"],
                "perPage": "100",
            }

        request_params: ParamsList
        request_params = params_list if params_list is not None else list(params_dict.items())

        urls_to_check = await self.get_search_urls(meta, request_params)

        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            for url, params, check_pending in urls_to_check:
                logger.debug(f"{self.tracker}: Searching URL: {url} with params: {params} (pending={check_pending})")
                response = await client.get(url=url, headers=headers, params=params)
                response.raise_for_status()

                if response.status_code == 200:
                    data = response.json()
                    for each in data.get("data", []):
                        if check_pending:
                            entry_tmdb = str(each.get("tmdb_id") or "")
                            meta_tmdb = str(meta.tmdb) if meta.tmdb is not None else ""
                            if entry_tmdb != meta_tmdb:
                                continue
                        torrent_id = each.get("id", None)
                        attributes = each if check_pending else each.get("attributes", {})
                        name = attributes.get("name", "")
                        size = attributes.get("size", 0)
                        result: dict[str, Any]
                        if not meta.is_disc:
                            result = {
                                "name": name,
                                "size": size,
                                "files": [file["name"] for file in attributes.get("files", []) if isinstance(file, dict) and "name" in file],
                                "file_count": (len(attributes.get("files", [])) if isinstance(attributes.get("files"), list) else 0),
                                "trumpable": attributes.get("trumpable", False),
                                "link": f"{self.base_url}/torrents/pending" if check_pending else attributes.get("details_link", None),
                                "download": attributes.get("download_link", None),
                                "id": torrent_id,
                                "type": attributes.get("type", None),
                                "res": attributes.get("resolution", None),
                                "internal": attributes.get("internal", False),
                            }
                        else:
                            result = {
                                "name": name,
                                "size": size,
                                "files": [],
                                "file_count": (len(attributes.get("files", [])) if isinstance(attributes.get("files"), list) else 0),
                                "trumpable": attributes.get("trumpable", False),
                                "link": f"{self.base_url}/torrents/pending" if check_pending else attributes.get("details_link", None),
                                "download": attributes.get("download_link", None),
                                "id": torrent_id,
                                "type": attributes.get("type", None),
                                "res": attributes.get("resolution", None),
                                "internal": attributes.get("internal", False),
                                "bd_info": attributes.get("bd_info", ""),
                                "description": attributes.get("description", ""),
                            }
                        dupes.append(result)
                else:
                    logger.info(f"{self.tracker}: [bold red]Failed to search torrents. HTTP Status: {response.status_code}")

        return dupes

    async def get_name(self, meta: Meta) -> dict[str, str]:
        return {"name": meta.name}

    async def get_description(self, meta: Meta) -> Any:
        return {
            "description": await DescriptionBuilder(self.tracker, self.config).general_description_generator(
                meta,
                mediainfo=False,
                nfo=False,
            )
        }

    async def get_mediainfo(self, meta: Meta) -> dict[str, str]:
        if meta.bdinfo or (meta.category in ["GAME", "BOOK"] and not meta.audiobook):
            mediainfo = ""
        else:
            async with aiofiles.open(f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/MEDIAINFO_CLEANPATH.txt", encoding="utf-8") as f:
                mediainfo = await f.read()
        return {"mediainfo": mediainfo}

    async def get_bdinfo(self, meta: Meta) -> dict[str, str]:
        if meta.bdinfo:
            async with aiofiles.open(f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/BD_SUMMARY_00.txt", encoding="utf-8") as f:
                bdinfo = await f.read()
        else:
            bdinfo = ""
        return {"bdinfo": bdinfo}

    async def get_category_id(self, meta: Meta, category: str = "", reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        category_id = {
            "MOVIE": "1",
            "TV": "2",
        }
        if mapping_only:
            return category_id
        if reverse:
            return {v: k for k, v in category_id.items()}
        if category:
            return {"category_id": category_id.get(category, "0")}
        meta_category = meta.category
        resolved_id = category_id.get(meta_category, "0")
        return {"category_id": resolved_id}

    async def get_type_id(self, meta: Meta, type: str = "", reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        type_id = {
            "DISC": "1",
            "REMUX": "2",
            "WEBDL": "4",
            "WEBRIP": "5",
            "HDTV": "6",
            "ENCODE": "3",
            "DVDRIP": "3",
        }
        if mapping_only:
            return type_id
        if reverse:
            return {v: k for k, v in type_id.items()}
        if type:
            return {"type_id": type_id.get(type, "0")}
        meta_type = meta.type
        resolved_id = type_id.get(meta_type or "", "0")
        return {"type_id": resolved_id}

    async def get_resolution_id(self, meta: Meta, resolution: str = "", reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        resolution_id = {
            "8640p": "10",
            "4320p": "1",
            "2160p": "2",
            "1440p": "3",
            "1080p": "3",
            "1080i": "4",
            "720p": "5",
            "576p": "6",
            "576i": "7",
            "480p": "8",
            "480i": "9",
        }

        if mapping_only:
            return resolution_id
        if reverse:
            return {v: k for k, v in resolution_id.items()}
        if resolution:
            return {"resolution_id": resolution_id.get(resolution, "10")}
        meta_resolution = meta.resolution
        resolved_id = resolution_id.get(meta_resolution, "10")
        return {"resolution_id": resolved_id}

    async def get_anonymous(self, meta: Meta) -> dict[str, str]:
        anonymous = "0" if meta.anon == 0 and not self.tracker_config.get("anon", False) else "1"
        return {"anonymous": anonymous}

    async def get_additional_data(self, meta: Meta) -> dict[str, str]:
        # Used to add additional data if needed
        """
        data = {
            'mod_queue_opt_in': await self.get_flag(meta, 'modq'),
            'draft': await self.get_flag(meta, 'draft'),
        }
        """
        _meta = meta
        data: dict[str, str] = {}

        return data

    async def get_flag(self, meta: Meta, flag_name: str) -> str:
        config_flag = self.tracker_config.get(flag_name)
        if meta.get(flag_name, False):
            return "1"
        if config_flag is not None:
            return "1" if config_flag else "0"
        return "0"

    async def get_distributor_id(self, meta: Meta) -> dict[str, str]:
        overrides = get_tracker_unit3d_overrides(self.tracker).get("distributors", {})
        distributor_name = str(meta.distributor or "").upper()
        if distributor_name and distributor_name in overrides:
            return {"distributor_id": str(overrides[distributor_name])}

        distributor_id = await self.common.unit3d_distributor_ids(meta.distributor)
        if distributor_id:
            return {"distributor_id": distributor_id}

        return {}

    async def get_region_id(self, meta: Meta) -> dict[str, str]:
        overrides = get_tracker_unit3d_overrides(self.tracker).get("regions", {})
        region_code = str(meta.region or "").upper()
        if region_code and region_code in overrides:
            return {"region_id": str(overrides[region_code])}

        region_id = await self.common.unit3d_region_ids(meta.region)
        if region_id:
            return {"region_id": region_id}

        return {}

    async def get_region_name(self, region_id: int | str | None) -> str:
        if region_id is None:
            return ""
        target_id = str(region_id).strip()
        overrides = get_tracker_unit3d_overrides(self.tracker).get("regions", {})
        for name, id_val in overrides.items():
            if str(id_val) == target_id:
                return name
        try:
            normalized_id = int(target_id)
        except TypeError, ValueError:
            return ""
        return await self.common.unit3d_region_ids(reverse=True, region_id=normalized_id)

    async def get_tmdb(self, meta: Meta) -> dict[str, str]:
        return {"tmdb": str(meta.tmdb) if meta.tmdb is not None else "0"}

    async def get_imdb(self, meta: Meta) -> dict[str, str]:
        imdb = meta.imdb_id if meta.category in ("TV", "MOVIE") else 0
        return {"imdb": str(imdb or 0)}

    async def get_tvdb(self, meta: Meta) -> dict[str, str]:
        tvdb = meta.tvdb_id if meta.category == "TV" else 0
        return {"tvdb": f"{tvdb}"}

    async def get_mal(self, meta: Meta) -> dict[str, str]:
        return {"mal": f"{meta.mal_id}"}

    async def get_igdb(self, meta: Meta) -> dict[str, str]:
        igdb = meta.igdb_id if meta.category == "GAME" else 0
        return {"igdb": f"{igdb}"}

    async def get_stream(self, meta: Meta) -> dict[str, str]:
        return {"stream": f"{meta.stream}"}

    async def get_sd(self, meta: Meta) -> dict[str, str]:
        return {"sd": f"{meta.sd}"}

    async def get_keywords(self, meta: Meta) -> dict[str, str]:
        """
        Enforces a 255-character limit on the keywords payload without cutting off individual words.
        This complies with the UNIT3D database schema (VARCHAR(255)) and API validation rules
        ('keywords' => 'nullable|string|max:255').
        """
        keywords_list: list[str] = []
        current_len = 0
        for kw in meta.keywords:
            kw_str = kw.strip()
            if not kw_str:
                continue
            needed = len(kw_str) + (2 if keywords_list else 0)
            if current_len + needed > 255:
                if not keywords_list and len(kw_str) > 255:
                    keywords_list.append(kw_str[:255])
                break
            keywords_list.append(kw_str)
            current_len += needed

        return {"keywords": ", ".join(keywords_list)}

    async def get_personal_release(self, meta: Meta) -> dict[str, str]:
        personal_release = "1" if meta.personalrelease else "0"
        return {"personal_release": personal_release}

    async def get_internal(self, meta: Meta) -> Any:
        internal = "0"
        if self.tracker_config.get("internal", False) is True and meta.tag and (meta.tag[1:] in self.tracker_config.get("internal_groups", [])):
            internal = "1"

        return {"internal": internal}

    async def get_season_number(self, meta: Meta) -> dict[str, str]:
        data = {}
        if meta.category == "TV":
            data = {"season_number": f"{(meta.season_int if meta.season_int is not None else '0')}"}

        return data

    async def get_episode_number(self, meta: Meta) -> dict[str, str]:
        data = {}
        if meta.category == "TV":
            data = {"episode_number": f"{(meta.episode_int if meta.episode_int is not None else '0')}"}

        return data

    async def get_featured(self, meta: Meta) -> dict[str, str]:
        _meta = meta
        return {"featured": "0"}

    async def get_free(self, meta: Meta) -> dict[str, str]:
        free = "0"
        if meta.freeleech != 0:
            free = f"{(meta.freeleech if meta.freeleech is not None else '0')}"

        return {"free": free}

    async def get_doubleup(self, meta: Meta) -> dict[str, str]:
        _meta = meta
        return {"doubleup": "0"}

    async def get_sticky(self, meta: Meta) -> dict[str, str]:
        _meta = meta
        return {"sticky": "0"}

    async def get_data(self, meta: Meta) -> dict[str, str]:
        results = await asyncio.gather(
            self.get_name(meta),
            self.get_description(meta),
            self.get_mediainfo(meta),
            self.get_bdinfo(meta),
            self.get_category_id(meta),
            self.get_type_id(meta),
            self.get_resolution_id(meta),
            self.get_tmdb(meta),
            self.get_imdb(meta),
            self.get_tvdb(meta),
            self.get_mal(meta),
            self.get_igdb(meta),
            self.get_anonymous(meta),
            self.get_stream(meta),
            self.get_sd(meta),
            self.get_keywords(meta),
            self.get_personal_release(meta),
            self.get_internal(meta),
            self.get_season_number(meta),
            self.get_episode_number(meta),
            self.get_featured(meta),
            self.get_free(meta),
            self.get_doubleup(meta),
            self.get_sticky(meta),
            self.get_additional_data(meta),
            self.get_region_id(meta),
            self.get_distributor_id(meta),
        )

        merged: dict[str, str] = {}
        for r in results:
            merged.update(r)

        # Handle exclusive flag centrally for all UNIT3D trackers
        # Priority: meta.exclusive > tracker config > default (not set)
        exclusive_flag = None
        if meta.exclusive or self.tracker_config.get("exclusive", False):
            exclusive_flag = "1"
        if exclusive_flag:
            merged["exclusive"] = exclusive_flag

        return merged

    async def get_image_file(self, image_path: str | Path, max_size: int | None = None) -> tuple[str, bytes, str] | None:
        """Read an image unchanged and return it with a content type verified from its signature."""
        path = Path(image_path)
        try:
            if not path.is_file() or (max_size is not None and path.stat().st_size > max_size):
                return None

            async with aiofiles.open(path, "rb") as f:
                image_bytes = await f.read()
        except OSError as e:
            logger.info(f"{self.tracker}: [yellow]Failed to read image {path}: {e}[/yellow]")
            return None

        if not is_valid_image_bytes(image_bytes):
            logger.info(f"{self.tracker}: [yellow]Invalid or unsupported image: {path}[/yellow]")
            return None

        image_type: tuple[str, str] | None = None
        if image_bytes.startswith(b"\xff\xd8\xff"):
            image_type = (".jpg", "image/jpeg")
        elif image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
            image_type = (".png", "image/png")
        elif image_bytes.startswith((b"GIF87a", b"GIF89a")):
            image_type = (".gif", "image/gif")
        elif image_bytes.startswith(b"RIFF") and image_bytes[8:12] == b"WEBP":
            image_type = (".webp", "image/webp")

        if image_type is None:
            logger.info(f"{self.tracker}: [yellow]Unsupported image format: {path}[/yellow]")
            return None

        extension, media_type = image_type
        return (f"{path.stem}{extension}", image_bytes, media_type)

    async def get_additional_files(self, meta: Meta) -> dict[str, tuple[str, bytes, str]]:
        files: dict[str, tuple[str, bytes, str]] = {}
        base_dir = meta.base_dir
        uuid = meta.uuid
        specified_dir = Path(base_dir) / "tmp" / uuid
        nfo_files = [str(p) for p in specified_dir.glob("*.nfo")]
        if not nfo_files and meta.keep_nfo and (meta.keep_folder or meta.isdir):
            search_dir = Path(str(meta.path)).parent
            nfo_files = [str(p) for p in search_dir.glob("*.nfo")]

        if nfo_files:
            async with aiofiles.open(nfo_files[0], "rb") as f:
                nfo_bytes = await f.read()
            files["nfo"] = ("nfo_file.nfo", nfo_bytes, "text/plain")

        if meta.category not in ("MOVIE", "TV", "GAME"):
            cover_path = meta.artwork_path
            if cover_path:
                cover_file = await self.get_image_file(cover_path)
                if cover_file:
                    files["torrent-cover"] = cover_file

            banner_path = meta.artwork_banner_path
            if banner_path:
                banner_file = await self.get_image_file(banner_path)
                if banner_file:
                    files["torrent-banner"] = banner_file

        return files

    async def upload(self, meta: Meta) -> bool:
        data = await self.get_data(meta)
        torrent_filename = await self.common.get_torrent_filename(meta, self.tracker_config)
        torrent_file_path = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/{torrent_filename}.torrent"
        async with aiofiles.open(torrent_file_path, "rb") as f:
            torrent_bytes = await f.read()
        files = {"torrent": ("torrent.torrent", torrent_bytes, "application/x-bittorrent")}
        files.update(await self.get_additional_files(meta))
        headers = {
            "User-Agent": f"{meta.ua_name} {meta.current_version} ({platform.system()} {platform.release()})",
            "authorization": f"Bearer {self.api_key}",
            "accept": "application/json",
        }

        if meta.debug is False:
            response_data = {}
            max_retries = 2
            retry_delay = 5
            timeout = 40.0
            download_url: str | None = None
            post_succeeded = False

            for attempt in range(max_retries):
                try:
                    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                        response = await client.post(url=self.upload_url, files=files, data=data, headers=headers)
                        response.raise_for_status()

                        response_data = response.json()

                        # Verify API success before proceeding
                        if not response_data.get("success"):
                            error_msg = response_data.get("message", "Unknown error")
                            meta.tracker_status[self.tracker]["status_message"] = f"API error: {error_msg}"
                            logger.info(f"{self.tracker}: [yellow]Upload to {self.tracker} failed: {error_msg}[/yellow]")
                            return False

                        meta.tracker_status[self.tracker]["status_message"] = await self.process_response_data(response_data)
                        torrent_id = await self.get_torrent_id(response_data)
                        meta.tracker_status[self.tracker]["torrent_id"] = torrent_id
                        download_url = response_data.get("data")
                        post_succeeded = True
                        break  # POST definitively succeeded

                except httpx.HTTPStatusError as e:
                    if e.response.status_code in [403, 302]:
                        # Don't retry auth/permission errors
                        if e.response.status_code == 403:
                            meta.tracker_status[self.tracker]["status_message"] = (
                                f"data error: Forbidden (403). This may indicate that you do not have upload permission. {e.response.text}"
                            )
                        else:
                            meta.tracker_status[self.tracker]["status_message"] = (
                                f"data error: Redirect (302). This may indicate a problem with authentication. {e.response.text}"
                            )
                        return False  # Auth/permission error
                    if e.response.status_code in [401, 404, 422]:
                        meta.tracker_status[self.tracker]["status_message"] = f"data error: HTTP {e.response.status_code} - {e.response.text}"
                    else:
                        # Retry other HTTP errors
                        if attempt < max_retries - 1:
                            logger.info(
                                f"{self.tracker}: [yellow]HTTP {e.response.status_code} error, retrying in {retry_delay} seconds... (attempt {attempt + 1}/{max_retries})[/yellow]"
                            )
                            await asyncio.sleep(retry_delay)
                            continue
                        # Final attempt failed
                        if e.response.status_code == 520:
                            meta.tracker_status[self.tracker]["status_message"] = "data error: Error (520). This is probably a cloudflare issue on the tracker side."
                        else:
                            meta.tracker_status[self.tracker]["status_message"] = f"data error: HTTP {e.response.status_code} - {e.response.text}"
                        return False  # HTTP error after all retries
                except httpx.TimeoutException:
                    if attempt < max_retries - 1:
                        timeout = timeout * 1.5  # Increase timeout by 50% for next retry
                        logger.info(
                            f"{self.tracker}: [yellow]Request timed out, retrying in {retry_delay} seconds with {timeout}s timeout... (attempt {attempt + 1}/{max_retries})[/yellow]"
                        )
                        await asyncio.sleep(retry_delay)
                        continue
                    meta.tracker_status[self.tracker]["status_message"] = "data error: Request timed out after multiple attempts"
                    return False  # Timeout after all retries
                except httpx.RequestError as e:
                    if attempt < max_retries - 1:
                        logger.info(f"{self.tracker}: [yellow]Request error, retrying in {retry_delay} seconds... (attempt {attempt + 1}/{max_retries})[/yellow]")
                        await asyncio.sleep(retry_delay)
                        continue
                    meta.tracker_status[self.tracker]["status_message"] = f"data error: Unable to upload. Error: {e}.\nResponse: {response_data}"
                    return False  # Request error after all retries
                except json.JSONDecodeError as e:
                    meta.tracker_status[self.tracker]["status_message"] = f"data error: Invalid JSON response from {self.tracker}. Error: {e}"
                    return False  # JSON parsing error

            if post_succeeded:
                # Download is outside the retry loop — a POST timeout/error cannot cause re-submission
                await self.common.download_tracker_torrent(meta, self.tracker, headers=headers, downurl=download_url)
                return True
        else:
            logger.info(f"{self.tracker}: Request Data:")
            logger.info(Redaction.redact_private_info(data))
            meta.tracker_status[self.tracker]["status_message"] = f"Debug mode enabled, not uploading: {self.tracker}."
            await self.common.create_torrent_for_upload(
                meta,
                f"{self.tracker}" + "_DEBUG",
                f"{self.tracker}" + "_DEBUG",
                announce_url="https://fake.tracker",
            )
            return True  # Debug mode - simulated success

        return False

    async def get_torrent_id(self, response_data: dict[str, Any]) -> str:
        """Matches /12345.abcde and returns 12345"""
        torrent_id = ""
        try:
            match = re.search(r"/(\d+)\.", response_data["data"])
            if match:
                torrent_id = match.group(1)
        except IndexError, KeyError:
            logger.info(f"{self.tracker}: Could not parse torrent_id from response data.")
        return torrent_id

    async def process_response_data(self, response_data: dict[str, Any]) -> str:
        """Returns the success message from the response data as a string."""
        if response_data.get("success") is True:
            return str(response_data.get("message", "Upload successful"))

        # For non-success responses, format as string
        error_msg = response_data.get("message", "")
        if error_msg:
            return f"API response: {error_msg}"
        return f"API response: {response_data}"
