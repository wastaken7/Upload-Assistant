# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import asyncio
import json
import re
import stat
import time
import urllib.parse
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

import cli_ui
import httpx
from bs4 import BeautifulSoup
from bs4.element import AttributeValueList
from rich.markup import escape

from src.console import logger, prompt_in_thread
from src.meta import Meta
from src.stats import record_event_async


class SceneFileMismatchError(ValueError):
    """The user has not approved differences from the archived scene file."""


class SceneManager:
    def __init__(self, config: Mapping[str, Any]) -> None:
        self.default_config = cast(Mapping[str, Any], config.get("DEFAULT", {}))
        if not isinstance(self.default_config, dict):
            raise ValueError("'DEFAULT' config section must be a dict")

    def _attr_to_string(self, value: Any) -> str:
        if isinstance(value, str):
            return value
        if isinstance(value, AttributeValueList):
            return " ".join(value)
        if value is None:
            return ""
        return str(value)

    async def _cached_srrdb_request(self, client: httpx.AsyncClient, url: str, cache_file: Path, operation: str = "search") -> dict[str, Any] | None:
        if cache_file.exists():
            try:
                cached = json.loads(await asyncio.to_thread(cache_file.read_text, encoding="utf-8"))
                if isinstance(cached, dict):
                    logger.debug(f"[cyan]SRRDB: Using cached response from {cache_file.name}")
                    return cached
            except (OSError, ValueError) as e:
                logger.debug(f"[yellow]SRRDB: Could not read cache: {e}")

        logger.debug(f"Using SRRDB url: {url}")
        try:
            response = await self._srrdb_get(client, url, operation, 30.0)
            if response.status_code == 200:
                payload = response.json()
                if isinstance(payload, dict):
                    if not payload.get("warnings"):
                        try:
                            await asyncio.to_thread(cache_file.parent.mkdir, parents=True, exist_ok=True)
                            await asyncio.to_thread(cache_file.write_text, json.dumps(payload), encoding="utf-8")
                        except OSError as e:
                            logger.warning(f"[yellow]SRRDB: Could not save cache: {e}[/yellow]")
                    return payload
        except Exception as e:
            logger.info(f"[yellow]SRRDB: Request failed: {e}")
        return None

    async def _release_details(self, client: httpx.AsyncClient, release: str, cache_dir: Path) -> dict[str, Any] | None:
        safe_release = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(release).name).strip("._") or "scene_release"
        return await self._cached_srrdb_request(
            client, f"https://api.srrdb.com/v1/details/{urllib.parse.quote(release, safe='')}", cache_dir / f"{safe_release}.json", operation="details",
        )

    def _archived_files(self, details: dict[str, Any]) -> list[dict[str, Any]]:
        files = details.get("archived-files", [])
        if not isinstance(files, list):
            return []
        return [file for file in files if isinstance(file, dict) and isinstance(file.get("name"), str)]

    def _archived_basename(self, file: dict[str, Any]) -> str:
        return Path(file["name"].replace("\\", "/")).name

    async def _search_archived_filename(
        self, client: httpx.AsyncClient, filename: str, cache_dir: Path, details_cache_dir: Path,
    ) -> dict[str, Any] | None:
        # Stored sample names can identify a release when the media name differs.
        base = Path(filename).stem.lower()
        ext = Path(filename).suffix.lower()
        sample_ext = ".m2ts" if ext == ".iso" else ext
        names = [filename, f"{base}.sample{sample_ext}", f"{base}-sample{sample_ext}",
                 f"sample-{base}{sample_ext}", f"sample.{base}{sample_ext}"]
        prefix, separator, group = base.rpartition("-")
        if separator:
            names.extend([f"{prefix}.sample-{group}{sample_ext}", f"{prefix}-sample-{group}{sample_ext}"])

        for name in names:
            quoted_name = urllib.parse.quote(name, safe="")
            response = await self._cached_srrdb_request(
                client, f"https://api.srrdb.com/v1/search/store-real-filename:{quoted_name}", cache_dir / f"{quoted_name}.json",
            )
            if response is None or response.get("warnings"):
                continue
            candidates = response.get("results")
            count = response.get("resultsCount")
            if isinstance(count, bool) or not isinstance(count, (int, str)):
                return None
            try:
                count = int(count)
            except ValueError:
                return None
            if not isinstance(candidates, list) or any(
                not isinstance(candidate, dict)
                or not isinstance(candidate.get("release"), str)
                or not candidate["release"].strip()
                for candidate in candidates
            ):
                return None
            # Do not guess from truncated results or fan out over broad searches.
            if count != len(candidates) or len(candidates) > 10:
                return None
            if not candidates:
                continue

            matches = {}
            for candidate in candidates:
                release = candidate["release"]
                details = await self._release_details(client, release, details_cache_dir)
                if details is None:
                    return None
                if any(self._archived_basename(file).casefold() == filename.casefold() for file in self._archived_files(details)):
                    matches[release] = candidate

            if matches:
                return next(iter(matches.values())) if len(matches) == 1 else None
        return None

    async def _warn_file_differences(self, video: str, release: str, details: dict[str, Any] | None) -> bool:
        if not details:
            return False
        path = Path(video)
        try:
            local_stat = await asyncio.to_thread(path.stat)
        except OSError as e:
            logger.debug(f"[yellow]SRRDB: Could not check local file: {e}")
            return False
        if not stat.S_ISREG(local_stat.st_mode):
            return False

        # Compressed volumes are stored files; archived-files lists their contents.
        extension = path.suffix.lower()
        if extension in {".rar", ".zip", ".7z", ".tar", ".gz"} or re.fullmatch(r"\.r\d{2,3}", extension):
            stored = details.get("files", [])
            archived = [file for file in stored if isinstance(file, dict) and isinstance(file.get("name"), str)] if isinstance(stored, list) else []
        else:
            archived = self._archived_files(details)
        matches = [file for file in archived if self._archived_basename(file).casefold() == path.name.casefold()]
        # A release-named file can be compared to the sole archived file even if renamed.
        if not matches and len(archived) == 1 and path.stem.casefold() == release.casefold():
            matches = archived
        if len(matches) != 1:
            if archived and not matches:
                logger.warning(
                    f"[yellow]SRRDB: Filename '{escape(path.name)}' is not listed in '{escape(release)}'. "
                    "Please confirm whether the file was renamed. File size could not be verified.[/yellow]"
                )
                return True
            return False

        original_name = self._archived_basename(matches[0])
        filename_differs = path.name != original_name
        if filename_differs:
            logger.warning(
                f"[yellow]SRRDB: Filename differs from the archive: local '{escape(path.name)}', "
                f"original '{escape(original_name)}'. Please confirm whether the file was renamed.[/yellow]"
            )
        expected_size = matches[0].get("size")
        if isinstance(expected_size, str) and expected_size.isdigit():
            expected_size = int(expected_size)
        size_differs = isinstance(expected_size, int) and not isinstance(expected_size, bool) and expected_size >= 0 and local_stat.st_size != expected_size
        if size_differs:
            logger.warning(
                f"[yellow]SRRDB: File size mismatch for '{escape(path.name)}': local {local_stat.st_size} bytes, "
                f"archived {expected_size} bytes ('{escape(original_name)}'). Please verify the file before uploading.[/yellow]"
            )
        return filename_differs or size_differs

    async def _confirm_file_differences(self, video: str, release: str, details: dict[str, Any] | None, meta: Meta) -> None:
        if not await self._warn_file_differences(video, release, details):
            return
        message = "Upload cancelled: srrDB filename or file size differences were not approved."
        if meta.unattended and not meta.unattended_confirm:
            raise SceneFileMismatchError(f"{message} Run with interactive confirmation to review them.")
        try:
            approved = await prompt_in_thread(
                cli_ui.ask_yes_no,
                f"SRRDB: Continue with '{Path(video).name}' despite the filename or file size differences shown above?",
                default=False,
            )
        except EOFError as e:
            raise SceneFileMismatchError(message) from e
        if not approved:
            raise SceneFileMismatchError(message)

    async def _srrdb_get(self, client: httpx.AsyncClient, url: str, operation: str, request_timeout: float) -> httpx.Response:
        started = time.monotonic()
        try:
            response = await client.get(url, timeout=request_timeout)
        except Exception:
            await record_event_async("api", service="srrdb", operation=operation, outcome="error", duration_ms=(time.monotonic() - started) * 1000)
            raise
        await record_event_async(
            "api", service="srrdb", operation=operation, outcome="success" if response.status_code == 200 else "error", duration_ms=(time.monotonic() - started) * 1000
        )
        return response

    async def is_scene(self, video: str, meta: Meta, imdb: int | None = None, lower: bool = False) -> tuple[str, bool, int | None]:
        scene_start_time = 0.0
        if meta.debug:
            scene_start_time = time.time()

        scene = False
        is_all_lowercase = False
        base = Path(video).name
        match = re.match(r"^(.+)\.[a-zA-Z0-9]{3,4}$", Path(video).name)

        if match and (not meta.is_disc or meta.keep_folder):
            base = match.group(1)
            is_all_lowercase = base.islower()

        # For games uploaded from a folder, prefer the release folder name
        # instead of a split archive part or generic installer name.
        if meta.category == "GAME" and meta.isdir:
            folder_name = Path(str(meta.path)).name
            if folder_name:
                base = folder_name
                is_all_lowercase = base.islower()

        quoted_base = urllib.parse.quote(base)

        # Define cache directories
        cache_dir = Path(meta.base_dir) / "tmp" / meta.uuid / "srrdb"
        search_cache_dir = Path(cache_dir) / "search"
        details_cache_dir = Path(cache_dir) / "details"

        async with httpx.AsyncClient() as client:
            if not meta.scene and not lower:
                # Cache file for search
                search_cache_file = Path(search_cache_dir) / f"{quoted_base}.json"
                response_json = await self._cached_srrdb_request(
                    client, f"https://api.srrdb.com/v1/search/r:{quoted_base}", search_cache_file,
                )

                if (
                    response_json is not None and int(response_json.get("resultsCount", 0)) == 0
                    and match and (not meta.is_disc or meta.keep_folder)
                    and not (meta.category == "GAME" and meta.isdir)
                ):
                    archived_result = await self._search_archived_filename(
                        client, Path(video).name, cache_dir / "stored-filename-search", details_cache_dir,
                    )
                    if archived_result:
                        response_json = {"resultsCount": 1, "results": [archived_result]}

                if response_json and int(response_json.get("resultsCount", 0)) > 0:
                    first_result = response_json["results"][0]
                    release = str(first_result["release"])
                    release_details_dict = await self._release_details(client, release, details_cache_dir)
                    await self._confirm_file_differences(video, release, release_details_dict, meta)
                    meta.scene_name = first_result["release"]
                    video = f"{first_result['release']}.mkv"
                    scene = True
                    if is_all_lowercase and not meta.tag:
                        meta.we_need_tag = True
                    if first_result.get("imdbId") and not meta.imdb_manual:
                        imdb_str = str(first_result["imdbId"])
                        if imdb_str.isdigit() and int(imdb_str) != 0:
                            imdb = int(imdb_str)

                    # NFO Download Handling
                    if not meta.nfo and first_result.get("hasNFO") == "yes":
                        try:
                            release = str(first_result["release"])
                            safe_release = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(release).name).strip("._") or "scene_release"
                            release_lower = safe_release.lower()

                            if release_details_dict:
                                try:
                                    for file in release_details_dict.get("files", []):
                                        if file["name"].endswith(".nfo"):
                                            release_lower = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(file["name"]).stem).strip("._") or release_lower
                                except KeyError, ValueError:
                                    pass

                            nfo_url = f"https://www.srrdb.com/download/file/{release}/{release_lower}.nfo"
                            save_path = Path(meta.base_dir) / "tmp" / meta.uuid
                            Path(save_path).mkdir(parents=True, exist_ok=True)
                            nfo_file_path = Path(save_path) / f"{release_lower}.nfo"
                            meta.scene_nfo_file = nfo_file_path

                            # Check if NFO already exists (Local Cache)
                            if Path(nfo_file_path).exists():
                                meta.nfo = True
                                meta.auto_nfo = True
                            else:
                                nfo_response = await self._srrdb_get(client, nfo_url, "nfo_download", 30.0)
                                if nfo_response.status_code == 200:
                                    await asyncio.to_thread(Path(nfo_file_path).write_bytes, nfo_response.content)
                                    meta.nfo = True
                                    meta.auto_nfo = True
                                    logger.debug(f"[green]NFO downloaded to {nfo_file_path}")
                                else:
                                    logger.info("[yellow]NFO file not available for download.")
                        except Exception as e:
                            logger.info(f"[yellow]Failed to download NFO file: {e}")
                else:
                    if meta.debug and response_json:
                        logger.info("[yellow]SRRDB: No match found")

            elif not scene and lower:
                release_name: str = ""
                name_value = meta.filename
                name = name_value.replace(" ", ".") if isinstance(name_value, str) else None
                tag_value = meta.tag
                tag = tag_value.replace("-", "") if isinstance(tag_value, str) else None
                if name and tag:
                    url = f"https://api.srrdb.com/v1/search/start:{name}/group:{tag}"

                    logger.debug(f"Using SRRDB url: {url}")

                    try:
                        response = await self._srrdb_get(client, url, "search", 10.0)
                        response_json = response.json()

                        if int(response_json.get("resultsCount", 0)) > 0:
                            first_result = response_json["results"][0]
                            imdb_str = first_result.get("imdbId")
                            if imdb_str and imdb_str == str(meta.imdb_id).zfill(7) and meta.imdb_id != 0:
                                release_name = first_result["release"]
                                release_details_dict = await self._release_details(client, release_name, details_cache_dir)
                                await self._confirm_file_differences(video, release_name, release_details_dict, meta)
                                meta.scene = True

                                if not meta.nfo and first_result.get("hasNFO") == "yes":
                                    try:
                                        release = first_result["release"]
                                        release_lower = release.lower()
                                        nfo_url = f"https://www.srrdb.com/download/file/{release}/{quoted_base}.nfo"
                                        save_path = Path(meta.base_dir) / "tmp" / meta.uuid
                                        Path(save_path).mkdir(parents=True, exist_ok=True)
                                        nfo_file_path = Path(save_path) / f"{release_lower}.nfo"

                                        if not Path(nfo_file_path).exists():
                                            nfo_response = await self._srrdb_get(client, nfo_url, "nfo_download", 30.0)
                                            if nfo_response.status_code == 200:
                                                await asyncio.to_thread(Path(nfo_file_path).write_bytes, nfo_response.content)
                                                meta.nfo = True
                                                meta.auto_nfo = True
                                                logger.info(f"[green]NFO downloaded to {nfo_file_path}")
                                        else:
                                            meta.nfo = True
                                            meta.auto_nfo = True
                                    except Exception as e:
                                        logger.info(f"[yellow]Failed to download NFO file: {e}")

                                video = release_name
                                scene = True
                        else:
                            logger.debug("[yellow]SRRDB: No match found with lower/tag search")

                    except SceneFileMismatchError:
                        raise
                    except Exception as e:
                        logger.info(f"[yellow]SRRDB search failed: {e}")
                else:
                    logger.debug("[yellow]SRRDB: Missing name or tag for lower/tag search")

        check_predb = bool(self.default_config.get("check_predb", False))
        if not scene and check_predb:
            logger.debug("[yellow]SRRDB: No scene match found, checking predb")
            scene = await self.predb_check(meta, video)

        if meta.debug:
            scene_end_time = time.time()
            logger.debug(f"Scene data processed in {scene_end_time - scene_start_time:.2f} seconds")

        return video, scene, imdb

    async def predb_check(self, meta: Meta, video: str) -> bool:
        url = f"https://predb.pw/search.php?search={urllib.parse.quote(Path(video).name)}"
        logger.debug(f"Using predb url: {url}")
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=10.0)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, "lxml")
                found = False
                video_base = Path(video).name.lower()
                for row in soup.select("table.zebra-striped tbody tr"):
                    tds = row.find_all("td")
                    if len(tds) >= 3:
                        # The 3rd <td> contains the release name link
                        release_a = tds[2].find("a", title=True)
                        if release_a:
                            release_attr = self._attr_to_string(release_a.get("title")).strip()
                            if not release_attr:
                                continue
                            release_name = release_attr.lower()
                            logger.debug(f"[yellow]Predb: Checking {release_name} against {video_base}")
                            if release_name == video_base:
                                found = True
                                meta.scene_name = release_attr
                                logger.info("[green]Predb: Match found")
                                # The 4th <td> contains the group
                                if len(tds) >= 4:
                                    group_a = tds[3].find("a")
                                    if group_a:
                                        group = self._attr_to_string(group_a.get_text()).strip()
                                        meta.tag = f"-{group}" if group and not group.startswith("-") else group
                                return True
                if not found:
                    logger.info("[yellow]Predb: No match found")
                    return False
            else:
                logger.info(f"[red]Predb: Error {response.status_code} while checking")
                return False
        except httpx.RequestError as e:
            logger.info(f"[red]Predb: Request failed: {e}")
            return False
        except Exception as e:
            logger.info(f"[yellow]Predb error: {e}")
            return False
        return False
