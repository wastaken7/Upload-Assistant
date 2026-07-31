# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import asyncio
import collections
import contextlib
import os
import platform
import re
import ssl
import subprocess
import time
import traceback
import urllib.parse
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, TypedDict, cast

import httpx
import qbittorrentapi
from torf import Torrent

from cogs.redaction import Redaction
from src.console import logger
from src.meta import Meta
from src.torrentcreate import TorrentCreator

# These have to be global variables to be shared across all instances since a new instance is made every time
qbittorrent_cached_clients: dict[tuple[str, int, str], qbittorrentapi.Client] = {}  # Cache for qbittorrent clients that have been successfully logged into
qbittorrent_locks: collections.defaultdict[tuple[str, int, str], asyncio.Lock] = collections.defaultdict(
    asyncio.Lock
)  # Locks for qbittorrent clients to prevent concurrent logins


class _CandidateEntry(TypedDict):
    path: str
    name: str
    size: int | None
    used: bool


class _TorrentFileEntry(TypedDict):
    relative_path: str
    length: int | None


class _RetryableProxyResponseError(Exception):
    """A qBittorrent proxy response which is safe to retry."""


class _ProxyResponseError(Exception):
    """A non-success qBittorrent proxy response which must not be retried."""


class QbittorrentClientMixin:
    config: dict[str, Any]

    def _extract_tracker_ids_from_comment(self, comment: str) -> dict[str, str]:
        raise NotImplementedError

    async def is_valid_torrent(self, meta: Meta, torrent_path: str, torrenthash: str, torrent_client: str, client: dict[str, Any]) -> tuple[bool, str]:
        raise NotImplementedError

    async def get_ptp_from_hash_qbit(self, meta: Meta, client: dict[str, Any], pathed: bool = False) -> Meta:
        lookup_started = time.perf_counter()
        proxy_url = client.get("qui_proxy_url")
        qbt_proxy_url = ""
        qbt_client: qbittorrentapi.Client | None = None
        qbt_session: httpx.AsyncClient | None = None

        if proxy_url:
            qbt_proxy_url = proxy_url.rstrip("/")
            ssl_context = self.create_ssl_context_for_client(client)
            qbt_session = httpx.AsyncClient(timeout=10.0, verify=ssl_context)
            qbt_proxy_url = proxy_url.rstrip("/")
        else:
            potential_qbt_client = await self.init_qbittorrent_client(client)
            if not potential_qbt_client:
                return meta
            qbt_client = potential_qbt_client

        info_hash_v1 = meta.infohash
        if not isinstance(info_hash_v1, str) or not info_hash_v1 or not meta.path:
            return meta
        logger.debug(f"[cyan]Searching for infohash: {info_hash_v1}")
        logger.debug(f"[cyan]Fetching qBittorrent properties ({'proxy' if proxy_url else 'direct'}, pathed={pathed})[/cyan]")

        class TorrentInfo:
            def __init__(self, properties_data: dict[str, Any]) -> None:
                self.hash = properties_data.get("hash", info_hash_v1)
                self.infohash_v1 = properties_data.get("infohash_v1", info_hash_v1)
                self.name = properties_data.get("name", "")
                self.comment = properties_data.get("comment", "")
                self.tracker = ""
                self.files: list[Any] = []

        try:
            if proxy_url:
                if qbt_session is None:
                    raise RuntimeError("qbt_session should not be None")
                request_started = time.perf_counter()
                response = await qbt_session.get(f"{qbt_proxy_url}/api/v2/torrents/properties", params={"hash": info_hash_v1}, timeout=14.0)
                logger.debug(f"[cyan]qBittorrent properties proxy response: status={response.status_code}, elapsed={time.perf_counter() - request_started:.2f}s[/cyan]")
                if response.status_code == 200:
                    torrent_properties = response.json()
                    logger.debug(f"[cyan]Retrieved torrent properties via proxy for hash: {info_hash_v1}")

                    torrents = [TorrentInfo(torrent_properties)]
                else:
                    logger.info(f"[bold red]Failed to get torrent properties via proxy: {response.status_code}")
                    if qbt_session is not None:
                        await qbt_session.aclose()
                    return meta
            else:
                try:
                    if qbt_client is None:
                        raise RuntimeError("qbt_client should not be None")
                    request_started = time.perf_counter()
                    torrent_properties = await self.retry_qbt_operation(
                        lambda: asyncio.to_thread(qbt_client.torrents_properties, torrent_hash=info_hash_v1),
                        f"Get torrent properties for hash {info_hash_v1}",
                        initial_timeout=14.0,
                    )
                    logger.debug(f"[cyan]qBittorrent properties direct response: elapsed={time.perf_counter() - request_started:.2f}s[/cyan]")
                    logger.debug(f"[cyan]Retrieved torrent properties via client for hash: {info_hash_v1}")

                    torrents = [TorrentInfo(torrent_properties)]
                except Exception as e:
                    logger.info(f"[yellow]Failed to get properties: {e}")
                    return meta
        except TimeoutError:
            logger.info("[bold red]Getting torrents list timed out after retries")
            if qbt_session:
                await qbt_session.aclose()
            return meta
        except Exception as e:
            logger.info(f"[bold red]Error getting torrents list: {e}")
            if qbt_session:
                await qbt_session.aclose()
            return meta
        found = False

        folder_id = Path(meta.path).name
        if not meta.uuid:
            meta.uuid = folder_id

        extracted_torrent_dir = str(Path(meta.base_dir) / "tmp" / meta.uuid)
        Path(extracted_torrent_dir).mkdir(parents=True, exist_ok=True)

        for torrent in torrents:
            try:
                if getattr(torrent, "infohash_v1", "") == info_hash_v1:
                    comment = getattr(torrent, "comment", "")

                    torrent_comments = meta.torrent_comments
                    if not isinstance(torrent_comments, list):
                        torrent_comments = []
                        meta.torrent_comments = torrent_comments

                    comment_data = {
                        "hash": getattr(torrent, "infohash_v1", ""),
                        "name": getattr(torrent, "name", ""),
                        "comment": comment,
                    }
                    cast(list[dict[str, Any]], torrent_comments).append(comment_data)

                    logger.debug(f"[cyan]Stored comment for torrent: {comment[:100]}...")

                    tracker_ids: dict[str, str] = self._extract_tracker_ids_from_comment(comment)
                    meta.update(tracker_ids)

                    if meta.torrent_comments and meta.debug:
                        logger.info(f"[green]Stored {len(meta.torrent_comments)} torrent comments for later use")

                    if not pathed:
                        torrent_storage_dir = client.get("torrent_storage_dir")
                        if not torrent_storage_dir:
                            # Export .torrent file
                            torrent_hash = getattr(torrent, "infohash_v1", "")
                            logger.debug(f"[cyan]Exporting .torrent file for hash: {torrent_hash}")

                            try:
                                if proxy_url:
                                    if qbt_session is None:
                                        raise RuntimeError("qbt_session should not be None")
                                    export_started = time.perf_counter()
                                    response = await qbt_session.post(f"{qbt_proxy_url}/api/v2/torrents/export", data={"hash": torrent_hash})
                                    logger.debug(
                                        f"[cyan]qBittorrent export via proxy: hash={torrent_hash}, status={response.status_code}, elapsed={time.perf_counter() - export_started:.2f}s[/cyan]"
                                    )
                                    if response.status_code == 200:
                                        torrent_file_content = response.content
                                    else:
                                        logger.error(f"[red]Failed to export torrent via proxy: {response.status_code}")
                                        continue
                                else:
                                    if qbt_client is None:
                                        raise RuntimeError("qbt_client should not be None")
                                    export_started = time.perf_counter()
                                    torrent_file_content = await self.retry_qbt_operation(
                                        lambda qbt_client=qbt_client, torrent_hash=torrent_hash: asyncio.to_thread(qbt_client.torrents_export, torrent_hash=torrent_hash),
                                        f"Export torrent {torrent_hash}",
                                    )
                                    logger.debug(f"[cyan]qBittorrent export direct: hash={torrent_hash}, elapsed={time.perf_counter() - export_started:.2f}s[/cyan]")
                                torrent_file_path = Path(extracted_torrent_dir) / f"{torrent_hash}.torrent"

                                await asyncio.to_thread(Path(torrent_file_path).write_bytes, torrent_file_content)

                                # Validate the .torrent file before saving as BASE.torrent
                                valid, _ = await self.is_valid_torrent(meta, torrent_file_path, torrent_hash, "qbit", client)
                                if not valid:
                                    logger.debug(f"[bold red]Validation failed for {torrent_file_path}")
                                    torrent_file_path.unlink()  # Remove invalid file
                                else:
                                    await TorrentCreator.create_base_from_existing_torrent(torrent_file_path, meta.base_dir, meta.uuid)
                            except TimeoutError:
                                logger.info(f"[bold red]Failed to export .torrent for {torrent_hash} after retries")

                    found = True
                    break
            except Exception as e:
                if qbt_session:
                    await qbt_session.aclose()
                logger.info(f"[bold red]Error processing torrent {getattr(torrent, 'name', 'Unknown')}: {e}")
                logger.debug(f"[bold red]Traceback: {traceback.format_exc()}")
                continue

        if not found:
            logger.info("[bold red]Matching site torrent with the specified infohash_v1 not found.")

        if qbt_session:
            await qbt_session.aclose()

        logger.debug(f"[cyan]Completed qBittorrent hash lookup in {time.perf_counter() - lookup_started:.2f}s[/cyan]")
        return meta

    @staticmethod
    def _coerce_str_list(value: Any) -> list[str]:
        if isinstance(value, list):
            value_list = value
            return [str(v) for v in value_list if str(v)]
        return [str(value)] if value is not None else []

    def create_ssl_context_for_client(self, client_config: dict[str, Any]) -> ssl.SSLContext:
        """Create SSL context for qBittorrent client based on VERIFY_WEBUI_CERTIFICATE setting."""
        ssl_context = ssl.create_default_context()
        if not client_config.get("VERIFY_WEBUI_CERTIFICATE", True):
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
        return ssl_context

    async def retry_qbt_operation(
        self,
        operation_func: Callable[[], Awaitable[Any]],
        operation_name: str,
        max_retries: int = 2,
        initial_timeout: float = 10.0,
        retryable_errors: tuple[type[BaseException], ...] = (TimeoutError,),
    ) -> Any:
        for attempt in range(max_retries + 1):
            timeout = initial_timeout * (2**attempt)  # Exponential backoff: 10s, 20s, 40s
            try:
                result = await asyncio.wait_for(operation_func(), timeout=timeout)
                if attempt > 0:
                    logger.info(f"[green]{operation_name} succeeded on attempt {attempt + 1}")
                return result
            except retryable_errors as error:
                if attempt < max_retries:
                    logger.info(f"[yellow]{operation_name} failed ({error}) after {timeout}s (attempt {attempt + 1}/{max_retries + 1}), retrying...")
                    await asyncio.sleep(1)  # Brief pause before retry
                else:
                    logger.info(f"[bold red]{operation_name} failed after {max_retries + 1} attempts (final attempt timeout: {timeout}s)")
                    raise
        return None

    @staticmethod
    def _raise_for_proxy_response(response: httpx.Response) -> None:
        if response.status_code == 200:
            return
        if response.status_code in (502, 503, 504):
            raise _RetryableProxyResponseError(f"proxy returned HTTP {response.status_code}")
        raise _ProxyResponseError(f"proxy returned HTTP {response.status_code}")

    async def _add_torrent_via_proxy(self, qbt_session: httpx.AsyncClient, qbt_proxy_url: str, infohash: str, data: dict[str, str], files: dict[str, Any]) -> None:
        add_attempt = 0

        async def add_via_proxy() -> None:
            nonlocal add_attempt
            # A timeout or 5xx response may mean qBittorrent accepted the first
            # request while the proxy failed to return its response. Check before
            # submitting the same infohash again.
            if add_attempt:
                info_response = await qbt_session.get(f"{qbt_proxy_url}/api/v2/torrents/info", params={"hashes": infohash})
                self._raise_for_proxy_response(info_response)
                if info_response.json():
                    logger.info("[green]Torrent was added to qBittorrent despite the previous proxy failure.")
                    return

            add_attempt += 1
            response = await qbt_session.post(f"{qbt_proxy_url}/api/v2/torrents/add", data=data, files=files)
            self._raise_for_proxy_response(response)

        await self.retry_qbt_operation(
            add_via_proxy,
            "Add torrent to qBittorrent via proxy",
            initial_timeout=14.0,
            retryable_errors=(TimeoutError, httpx.HTTPError, _RetryableProxyResponseError),
        )

    async def init_qbittorrent_client(self, client: dict[str, Any]) -> qbittorrentapi.Client | None:
        # Creates and logs into a qbittorrent client, with caching to avoid redundant logins
        # If login fails, returns None
        if client.get("qbit_api_key"):
            client_key = (client["qbit_url"], client["qbit_port"], "APIKEY:" + client["qbit_api_key"])
        else:
            client_key = (client["qbit_url"], client["qbit_port"], client.get("qbit_user", ""))

        async with qbittorrent_locks[client_key]:
            # We lock to further prevent concurrent logins for the same client. If two clients try to init at the same time, if the first one succeeds, the second one can use the cached client.
            potential_cached_client = qbittorrent_cached_clients.get(client_key)
            if potential_cached_client is not None:
                return potential_cached_client

            if client.get("qbit_api_key"):
                qbt_client = qbittorrentapi.Client(
                    host=client["qbit_url"], port=client["qbit_port"], api_key=client["qbit_api_key"], VERIFY_WEBUI_CERTIFICATE=client.get("VERIFY_WEBUI_CERTIFICATE", True)
                )
                try:
                    await self.retry_qbt_operation(lambda: asyncio.to_thread(qbt_client.app_version), "qBittorrent API Key verification")
                except TimeoutError:
                    logger.info("[bold red]Connection to qBittorrent timed out after retries")
                    return None
                except qbittorrentapi.APIConnectionError:
                    logger.info("[bold red]Failed to connect to qBittorrent - check host/port/API Key")
                    return None
                except Exception as e:
                    logger.info(f"[bold red]Failed to verify qBittorrent API Key: {e}")
                    return None
            else:
                qbt_client = qbittorrentapi.Client(
                    host=client["qbit_url"],
                    port=client["qbit_port"],
                    username=client.get("qbit_user"),
                    password=client.get("qbit_pass"),
                    VERIFY_WEBUI_CERTIFICATE=client.get("VERIFY_WEBUI_CERTIFICATE", True),
                )
                try:
                    await self.retry_qbt_operation(lambda: asyncio.to_thread(qbt_client.auth_log_in), "qBittorrent login")
                except TimeoutError:
                    logger.info("[bold red]Connection to qBittorrent timed out after retries")
                    return None
                except qbittorrentapi.LoginFailed:
                    logger.info("[bold red]Failed to login to qBittorrent - incorrect credentials")
                    return None
                except qbittorrentapi.APIConnectionError:
                    logger.info("[bold red]Failed to connect to qBittorrent - check host/port")
                    return None

            qbittorrent_cached_clients[client_key] = qbt_client
            return qbt_client

    async def search_qbit_for_torrent(
        self,
        meta: Meta,
        client: dict[str, Any],
        qbt_client: qbittorrentapi.Client | None = None,
        qbt_session: httpx.AsyncClient | None = None,
        proxy_url: str | None = None,
    ) -> str | None:
        trackers_config = cast(dict[str, Any], self.config.get("TRACKERS", {}))
        mtv_config_value = trackers_config.get("MORETHANTV", {})
        mtv_config = cast(dict[str, Any], mtv_config_value) if isinstance(mtv_config_value, dict) else {}
        prefer_small_pieces = bool(mtv_config.get("prefer_mtv_torrent", False))
        logger.debug("[green]Searching qBittorrent for an existing .torrent")

        torrent_storage_dir = client.get("torrent_storage_dir")
        extracted_torrent_dir = str(Path(meta.base_dir) / "tmp" / meta.uuid)

        if not extracted_torrent_dir or extracted_torrent_dir.strip() == "tmp/":
            logger.info("[bold red]Invalid extracted torrent directory path. Check `meta.base_dir` and `meta.uuid`.")
            return None

        created_session = False

        try:
            try:
                if qbt_client is None and proxy_url is None:
                    potential_qbt_client = await self.init_qbittorrent_client(client)
                    if potential_qbt_client is None:
                        return None
                    qbt_client = potential_qbt_client
                elif proxy_url and qbt_session is None:
                    ssl_context = self.create_ssl_context_for_client(client)
                    qbt_session = httpx.AsyncClient(timeout=10.0, verify=ssl_context)
                    created_session = True

            except qbittorrentapi.LoginFailed:
                logger.info("[bold red]INCORRECT QBIT LOGIN CREDENTIALS")
                return None
            except qbittorrentapi.APIConnectionError:
                logger.info("[bold red]APIConnectionError: INCORRECT HOST/PORT")
                return None

            if proxy_url and qbt_session is None:
                logger.info("[bold red]Proxy URL configured but session was not created")
                return None
            if not proxy_url and qbt_client is None:
                logger.info("[bold red]qBittorrent client is not initialized")
                return None

            # Ensure extracted torrent directory exists
            Path(extracted_torrent_dir).mkdir(parents=True, exist_ok=True)

            # **Step 1: Find correct torrents using content_path**
            best_match: dict[str, Any] | None = None
            matching_torrents: list[dict[str, Any]] = []

            try:
                if proxy_url:
                    if qbt_session is None:
                        logger.info("[bold red]Proxy session not initialized")
                        return None
                    qbt_proxy_url = proxy_url.rstrip("/")
                    search_term = meta.uuid.replace("[", ".").replace("]", ".")
                    # status is irrelevant here, since we only want an infohash to build from
                    qui_filters: dict[str, list[str]] = {
                        "status": [],
                        "excludeStatus": [],
                        "categories": [],
                        "excludeCategories": [],
                        "tags": [],
                        "excludeTags": [],
                        "trackers": [],
                        "excludeTrackers": [],
                    }
                    url = self._build_proxy_search_url(qbt_proxy_url, search_term, qui_filters)

                    logger.debug(f"[cyan]Searching qBittorrent via proxy: {Redaction.redact_private_info(url)}...")

                    search_started = time.perf_counter()
                    response = await qbt_session.get(url)
                    logger.debug(f"[cyan]qBittorrent proxy search response: status={response.status_code}, elapsed={time.perf_counter() - search_started:.2f}s[/cyan]")
                    if response.status_code == 200:
                        response_data = response.json()

                        torrents_data: list[dict[str, Any]]
                        if isinstance(response_data, dict) and "torrents" in response_data:
                            response_data_dict = cast(dict[str, Any], response_data)
                            torrents_value = response_data_dict.get("torrents", [])
                            torrents_data = cast(list[dict[str, Any]], torrents_value) if isinstance(torrents_value, list) else []
                        elif isinstance(response_data, list):
                            torrents_data = cast(list[dict[str, Any]], response_data)
                        else:
                            torrents_data = []

                        if meta.debug:
                            if torrents_data:
                                logger.debug(f"[cyan]qBittorrent proxy search returned {len(torrents_data)} torrents for '{search_term}'")
                            else:
                                logger.debug("[cyan]No matching torrents found via proxy search")

                        torrents = self._build_mock_torrents(torrents_data)
                    else:
                        if response.status_code == 404:
                            logger.debug(f"[yellow]No torrents found via proxy search for '[green]{search_term}' [yellow]Maybe tracker errors?")
                        else:
                            logger.info(f"[bold red]Failed to get torrents list via proxy: {response.status_code}")
                        return None
                else:
                    if qbt_client is None:
                        logger.info("[bold red]qBittorrent client not initialized")
                        return None
                    torrents = await self.retry_qbt_operation(lambda: asyncio.to_thread(qbt_client.torrents_info), "Get torrents list", initial_timeout=14.0)
            except TimeoutError:
                logger.info("[bold red]Getting torrents list timed out after retries")
                return None
            except Exception as e:
                logger.info(f"[bold red]Error getting torrents list: {e}")
                return None

            torrent_count = 0
            for torrent in torrents:
                try:
                    torrent_path = torrent.name
                    torrent_count += 1
                except AttributeError:
                    continue  # Ignore torrents with missing attributes

                if meta.uuid.lower() != torrent_path.lower():
                    continue

                logger.debug(f"[cyan]Matched Torrent: {torrent.hash}")
                logger.debug(f"Name: {torrent.name}")
                logger.debug(f"Save Path: {torrent.save_path}")
                logger.debug(f"Content Path: {torrent_path}")

                # The early cached-search path must retain the same tracker
                # discovery side effect as the former get_pathed_torrents flow.
                # Otherwise a tracker already present in the client is not added
                # to meta.remove_trackers and can be uploaded again.
                tracker_urls: list[str] = []
                primary_tracker = str(getattr(torrent, "tracker", "") or "")
                if primary_tracker:
                    tracker_urls.append(primary_tracker)
                raw_trackers = getattr(torrent, "trackers", []) or []
                if isinstance(raw_trackers, list):
                    for tracker in raw_trackers:
                        if isinstance(tracker, dict):
                            url = tracker.get("url")
                            if url:
                                tracker_urls.append(str(url))
                        elif tracker:
                            tracker_urls.append(str(tracker))
                if tracker_urls:
                    await match_tracker_url(tracker_urls, meta)

                matching_torrents.append({"hash": torrent.hash, "name": torrent.name})

            logger.debug(f"[cyan]DEBUG: Checked {torrent_count} total torrents in qBittorrent[/cyan]")
            if not matching_torrents:
                logger.debug("[yellow]No matching torrents found in qBittorrent.")
                return None

            logger.debug(f"[green]Total Matching Torrents: {len(matching_torrents)}")

            # **Step 2: Extract and Save .torrent Files**
            processed_hashes: set[str] = set()
            best_match = None
            video_only_fallback: str | None = None
            torrent_hash: str | None = None
            for matching_torrent in matching_torrents:
                try:
                    torrent_hash = str(matching_torrent["hash"])
                    if torrent_hash in processed_hashes:
                        continue  # Avoid processing duplicates

                    processed_hashes.add(torrent_hash)

                except Exception as e:
                    logger.error(f"[bold red]Unexpected error while handling torrent{f' {torrent_hash}' if torrent_hash else ''}: {e}")
                    torrent_hash = None

                if not torrent_hash:
                    continue

                # **Use `torrent_storage_dir` if available**
                if torrent_storage_dir:
                    torrent_file_path = Path(torrent_storage_dir) / f"{torrent_hash}.torrent"
                    if not Path(torrent_file_path).exists():
                        logger.info(f"[yellow]Torrent file not found in storage directory: {torrent_file_path}")
                        continue
                else:
                    # **Fetch from qBittorrent API if no `torrent_storage_dir`**
                    logger.debug(f"[cyan]Exporting .torrent file for {torrent_hash}")

                    torrent_file_content = None
                    if proxy_url:
                        if qbt_session is None:
                            logger.info("[bold red]Proxy session not initialized")
                            continue
                        qbt_proxy_url = proxy_url.rstrip("/")
                        try:
                            export_started = time.perf_counter()
                            response = await qbt_session.post(f"{qbt_proxy_url}/api/v2/torrents/export", data={"hash": torrent_hash})
                            logger.debug(
                                f"[cyan]qBittorrent proxy export: hash={torrent_hash}, status={response.status_code}, elapsed={time.perf_counter() - export_started:.2f}s[/cyan]"
                            )
                            if response.status_code == 200:
                                torrent_file_content = response.content
                            else:
                                logger.error(f"[red]Failed to export torrent via proxy: {response.status_code}")
                        except Exception as e:
                            logger.error(f"[red]Error exporting torrent via proxy: {e}")
                    else:
                        if qbt_client is None:
                            logger.info("[bold red]qBittorrent client not initialized")
                            continue
                        torrent_file_content = await self.retry_qbt_operation(
                            lambda qbt_client=qbt_client, torrent_hash=torrent_hash: asyncio.to_thread(qbt_client.torrents_export, torrent_hash=torrent_hash),
                            f"Export torrent {torrent_hash}",
                        )

                    if torrent_file_content is not None:
                        torrent_file_path = Path(extracted_torrent_dir) / f"{torrent_hash}.torrent"

                        await asyncio.to_thread(Path(torrent_file_path).write_bytes, torrent_file_content)
                        logger.debug(f"[green]Successfully saved .torrent file: {torrent_file_path}")
                    else:
                        logger.info(f"[bold red]Failed to export .torrent for {torrent_hash} after retries")
                        continue  # Skip this torrent if unable to fetch

                # **Validate the .torrent file**
                try:
                    validation_started = time.perf_counter()
                    valid, torrent_path = await self.is_valid_torrent(meta, torrent_file_path, torrent_hash, "qbit", client)
                    logger.debug(f"[cyan]Validated exported torrent: hash={torrent_hash}, valid={valid}, elapsed={time.perf_counter() - validation_started:.2f}s[/cyan]")
                except Exception as e:
                    logger.info(f"[bold red]Error validating torrent {torrent_hash}: {e}")
                    valid = False
                    torrent_path = None

                if valid:
                    if meta.subtitle_files and not self._torrent_includes_all_local_subtitles(str(torrent_file_path), meta):
                        if self._torrent_has_no_subtitles(str(torrent_file_path)):
                            video_only_fallback = torrent_hash
                            meta.base_reuse_torrent_path = str(torrent_path or torrent_file_path)
                            logger.debug(f"[yellow]Keeping video-only torrent as fallback: {torrent_hash}")
                        else:
                            logger.debug(f"[yellow]Skipping partial-subtitle torrent as fallback: {torrent_hash}")
                        continue
                    if prefer_small_pieces:
                        # **Track best match based on piece size**
                        try:
                            torrent_data = Torrent.read(torrent_file_path)
                            piece_size = torrent_data.piece_size
                            best_piece_size_raw_value: Any = best_match.get("piece_size") if best_match else None
                            best_piece_size: int | None = best_piece_size_raw_value if isinstance(best_piece_size_raw_value, int) else None
                            if best_match is None or (best_piece_size is not None and piece_size < best_piece_size):
                                best_match = {"hash": torrent_hash, "torrent_path": torrent_path if torrent_path else torrent_file_path, "piece_size": piece_size}
                                logger.info(f"[green]Updated best match: {best_match}")
                        except Exception as e:
                            logger.info(f"[bold red]Error reading torrent data for {torrent_hash}: {e}")
                            continue
                    else:
                        # If `prefer_small_pieces` is False, return first valid torrent
                        logger.debug(f"[green]Returning first valid torrent: {torrent_hash}")
                        return torrent_hash
                else:
                    logger.debug(f"[bold red]{torrent_hash} failed validation")
                    torrent_file_path.unlink()

            # **Return the best match if `prefer_small_pieces` is enabled**
            if best_match:
                logger.info(f"[green]Using best match torrent with hash: {best_match['hash']}")
                result = str(best_match["hash"]) if "hash" in best_match else None
            elif video_only_fallback:
                logger.info(f"[yellow]No matching torrent with all local subtitles found; using video-only fallback: {video_only_fallback}")
                result = video_only_fallback
            else:
                logger.info("[yellow]No valid torrents found.")
                result = None

            return result
        finally:
            if created_session and qbt_session is not None:
                await qbt_session.aclose()

    async def qbittorrent(
        self,
        path: str,
        torrent: Torrent,
        local_path: str,
        remote_path: str,
        client: dict[str, Any],
        _is_disc: str,
        filelist: list[str],
        meta: Meta,
        tracker: str,
        cross: bool = False,
    ) -> None:
        qbt_proxy_url = ""
        if meta.keep_folder:
            path = str(Path(path).parent)
        else:
            isdir = Path(path).is_dir()
            if len(filelist) != 1 or not isdir:
                path = str(Path(path).parent)

        # Get the appropriate source path
        src = meta.filelist[0] if len(meta.filelist) == 1 and Path(meta.filelist[0]).is_file() and not meta.keep_folder else meta.path

        if not src:
            error_msg = "[red]No source path found in meta."
            logger.info(f"[bold red]{error_msg}")
            raise ValueError(error_msg)

        # Determine linking method
        linking_method = client.get("linking")  # "symlink", "hardlink", or None
        logger.debug(f"Linking method: {linking_method}")
        use_symlink = linking_method == "symlink"
        use_hardlink = linking_method == "hardlink"

        # Get linked folder for this drive
        linked_folder = self._coerce_str_list(client.get("linked_folder", []))
        logger.debug(f"Linked folders: {linked_folder}")

        # Determine drive letter (Windows) or root (Linux)
        src_drive: str
        if platform.system() == "Windows":
            src_drive = os.path.splitdrive(src)[0]
        else:
            # On Unix/Linux, use the full mount point path for more accurate matching
            src_drive = "/"

            # Get all mount points on the system to find the most specific match
            mounted_volumes: list[str] = []
            try:
                # Read mount points from /proc/mounts or use 'mount' command output
                if Path("/proc/mounts").exists():
                    mounts_text = await asyncio.to_thread(Path("/proc/mounts").read_text)
                    for line in mounts_text.splitlines():
                        parts = line.split()
                        if len(parts) >= 2:
                            mount_point = parts[1]
                            mounted_volumes.append(mount_point)
                else:
                    # Fall back to mount command if /proc/mounts doesn't exist
                    output = str(await asyncio.to_thread(subprocess.check_output, ["mount"], text=True))
                    for line in output.splitlines():
                        parts = line.split()
                        if len(parts) >= 3:
                            mount_point = parts[2]
                            mounted_volumes.append(mount_point)
            except Exception as e:
                logger.debug(f"[yellow]Error getting mount points: {e!s}")

            # Sort mount points by length (descending) to find most specific match first
            mounted_volumes.sort(key=len, reverse=True)

            # Find the most specific mount point that contains our source path
            for mount_point in mounted_volumes:
                if src.startswith(mount_point):
                    src_drive = mount_point
                    logger.debug(f"[cyan]Found mount point: {mount_point} for path: {src}")
                    break

            # If we couldn't find a specific mount point, fall back to linked folder matching
            if src_drive == "/":
                # Extract the first directory component for basic matching
                src_parts = src.strip("/").split("/")
                if src_parts:
                    src_root_dir = "/" + src_parts[0]
                    # Check if any linked folder contains this root
                    for folder in linked_folder:
                        if src_root_dir in folder or folder in src_root_dir:
                            src_drive = src_root_dir
                            break

        # Find a linked folder that matches the drive
        link_target: str | None = None
        if platform.system() == "Windows":
            # Windows matching based on drive letters
            for folder in linked_folder:
                folder_drive = os.path.splitdrive(folder)[0]
                if folder_drive == src_drive:
                    link_target = folder
                    break
        else:
            # Unix/Linux matching based on path containment
            for folder in linked_folder:
                # Check if the linked folder starts with the mount point
                if folder.startswith(src_drive) or src.startswith(folder):
                    link_target = folder
                    break

                # Also check if this is a sibling mount point with the same structure
                folder_parts = folder.split("/")
                src_drive_parts = src_drive.split("/")

                # Check if both are mounted under the same parent directory
                if len(folder_parts) >= 2 and len(src_drive_parts) >= 2 and folder_parts[1] == src_drive_parts[1]:
                    potential_match = Path(src_drive) / folder_parts[-1]
                    if Path(potential_match).exists():
                        link_target = potential_match
                        logger.debug(f"[cyan]Found sibling mount point linked folder: {link_target}")
                        break

        logger.debug(f"Source drive: {src_drive}")
        logger.debug(f"Link target: {link_target}")
        # If using symlinks and no matching drive folder, allow any available one
        if use_symlink and not link_target and linked_folder:
            link_target = linked_folder[0]

        if (use_symlink or use_hardlink) and not link_target:
            error_msg = f"No suitable linked folder found for drive {src_drive}"
            logger.info(f"[bold red]{error_msg}")
            raise ValueError(error_msg)

        tracker_dir = None
        if use_symlink or use_hardlink:
            tracker_cfg = self.config["TRACKERS"].get(tracker.upper(), {})
            link_dir_name = str(tracker_cfg.get("link_dir_name", "")).strip()
            if link_target is None:
                raise RuntimeError("link_target cannot be None")
            tracker_dir = Path(link_target) / link_dir_name or tracker
            await asyncio.to_thread(os.makedirs, tracker_dir, exist_ok=True)

            if cross:
                linking_success = await create_cross_seed_links(meta=meta, torrent=torrent, tracker_dir=tracker_dir, use_hardlink=use_hardlink)
            else:
                src_name = Path(src.rstrip(os.sep)).name
                dst = Path(tracker_dir) / src_name
                linking_success = await async_link_directory(src=src, dst=dst, use_hardlink=use_hardlink)

            allow_fallback = client.get("allow_fallback", True)
            if not linking_success and allow_fallback:
                logger.info(f"[yellow]Using original path without linking: {src}")
                use_hardlink = False
                use_symlink = False
            elif not linking_success:
                logger.info("[bold red]Linking failed and fallback is disabled; aborting qBittorrent add")
                return
        elif cross:
            logger.info("[yellow]Cross seed requested, but no linking method is configured. Proceeding with original path naming.")

        proxy_url = client.get("qui_proxy_url")
        qbt_client = None
        qbt_session = None

        if proxy_url:
            ssl_context = self.create_ssl_context_for_client(client)
            qbt_session = httpx.AsyncClient(timeout=10.0, verify=ssl_context)
            qbt_proxy_url = proxy_url.rstrip("/")
        else:
            potential_qbt_client = await self.init_qbittorrent_client(client)
            if not potential_qbt_client:
                return
            qbt_client = potential_qbt_client

        logger.debug("[bold yellow]Adding and rechecking torrent")

        # Apply remote pathing to `tracker_dir` before assigning `save_path`
        if use_symlink or use_hardlink:
            if tracker_dir is None:
                raise ValueError("Linking enabled but tracker_dir was not set")
            save_path = str(tracker_dir)  # Default to linked directory
        else:
            save_path = str(path)  # Default to the original path

        # Handle remote path mapping
        if local_path and remote_path and local_path.lower() != remote_path.lower():
            # Normalize paths for comparison
            norm_save_path = os.path.normpath(save_path).lower()
            norm_local_path = os.path.normpath(local_path).lower()

            # Check if the save_path starts with local_path
            if norm_save_path.startswith(norm_local_path):
                # Get the relative part of the path
                rel_path = os.path.relpath(save_path, local_path)
                # Combine remote path with relative path while keeping a string path
                save_path = str(Path(remote_path) / rel_path)

            # For direct replacement if the above approach doesn't work
            elif local_path.lower() in save_path.lower():
                save_path = save_path.replace(local_path, remote_path, 1)  # Replace only at the beginning

        # Always normalize separators for qBittorrent (it expects forward slashes)
        save_path = save_path.replace(os.sep, "/")

        # Ensure qBittorrent save path is formatted correctly
        if not save_path.endswith("/"):
            save_path += "/"

        logger.debug(f"[cyan]Original path: {path}")
        logger.debug(f"[cyan]Mapped save path: {save_path}")

        # Automatic management
        auto_management = False
        if not use_symlink and not use_hardlink:
            am_config = client.get("automatic_management_paths", "")
            logger.debug(f"AM Config: {am_config}")
            if isinstance(am_config, list):
                for each in self._coerce_str_list(am_config):
                    if os.path.normpath(each).lower() in os.path.normpath(path).lower():
                        auto_management = True
            else:
                am_config_str = str(am_config)
                if os.path.normpath(am_config_str).lower() in os.path.normpath(path).lower() and am_config_str.strip() != "":
                    auto_management = True

        qbt_category = client["qbit_cross_cat"] if cross and client.get("qbit_cross_cat") else client.get("qbit_cat") if not meta.qbit_cat else meta.qbit_cat
        content_layout = client.get("content_layout", "Original")
        logger.debug(f"qbt_category: {qbt_category}")
        logger.debug(f"Content Layout: {content_layout}")
        logger.debug(f"[bold yellow]qBittorrent save path: {save_path}")

        if cross:
            skip_checking = True
            paused_on_add = True
        else:
            skip_checking = True
            paused_on_add = False
        tag = None
        if cross and client.get("qbit_cross_tag"):
            tag = client["qbit_cross_tag"]
        else:
            if meta.qbit_tag:
                tag = meta.qbit_tag
            elif client.get("use_tracker_as_tag", False) and tracker:
                tag = tracker
            elif client.get("qbit_tag"):
                tag = client["qbit_tag"]

        try:
            if proxy_url:
                if qbt_session is None:
                    raise RuntimeError("qbt_session cannot be None")
                # Create files and data for multipart/form-data request
                files = {"torrents": ("torrent.torrent", torrent.dump(), "application/x-bittorrent")}
                data = {
                    "savepath": save_path,
                    "autoTMM": str(auto_management).lower(),
                    "skip_checking": str(skip_checking).lower(),
                    "paused": str(paused_on_add).lower(),
                    "contentLayout": content_layout,
                }
                if qbt_category:
                    data["category"] = qbt_category
                if tag:
                    data["tags"] = tag
                logger.debug(
                    f"[cyan]POSTing to {Redaction.redact_private_info(qbt_proxy_url)}/api/v2/torrents/add with data: savepath={save_path}, autoTMM={auto_management}, skip_checking={skip_checking}, paused={paused_on_add}, contentLayout={content_layout}, category={qbt_category}, tags={tag}"
                )

                await self._add_torrent_via_proxy(qbt_session, qbt_proxy_url, torrent.infohash, data, files)
            else:
                if qbt_client is None:
                    raise RuntimeError("qbt_client cannot be None")
                await self.retry_qbt_operation(
                    lambda: asyncio.to_thread(
                        qbt_client.torrents_add,
                        torrent_files=torrent.dump(),
                        save_path=save_path,
                        use_auto_torrent_management=auto_management,
                        is_skip_checking=skip_checking,
                        paused=paused_on_add,
                        content_layout=content_layout,
                        category=qbt_category,
                        tags=tag,
                    ),
                    "Add torrent to qBittorrent",
                    initial_timeout=14.0,
                )
        except _ProxyResponseError as e:
            logger.info(f"[bold red]Failed to add torrent via proxy: {e}")
            if qbt_session:
                await qbt_session.aclose()
            return
        except TimeoutError, httpx.HTTPError, qbittorrentapi.APIConnectionError:
            logger.info("[bold red]Failed to add torrent to qBittorrent")
            if qbt_session:
                await qbt_session.aclose()
            return
        except Exception as e:
            logger.info(f"[bold red]Error adding torrent: {e}")
            if qbt_session:
                await qbt_session.aclose()
            return

        # Wait for torrent to be added
        timeout = 30
        for _ in range(timeout):
            try:
                if proxy_url:
                    if qbt_session is None:
                        raise RuntimeError("qbt_session cannot be None")
                    response = await qbt_session.get(f"{qbt_proxy_url}/api/v2/torrents/info", params={"hashes": torrent.infohash})
                    if response.status_code == 200:
                        torrents_info = response.json()
                        if len(torrents_info) > 0:
                            logger.debug(f"[green]Found {tracker} torrent in qBittorrent.")
                            break
                    else:
                        pass  # Continue waiting
                else:
                    if qbt_client is None:
                        raise RuntimeError("qbt_client cannot be None")
                    torrents_info = await self.retry_qbt_operation(
                        lambda: asyncio.to_thread(qbt_client.torrents_info, torrent_hashes=torrent.infohash), "Check torrent addition", max_retries=1, initial_timeout=10.0
                    )
                    if len(torrents_info) > 0:
                        break
            except TimeoutError:
                pass  # Continue waiting
            except Exception:  # noqa: S110
                pass  # Continue waiting
            await asyncio.sleep(1)
        else:
            logger.info("[red]Torrent addition timed out.")
            if qbt_session:
                await qbt_session.aclose()
            return

        if not cross:
            try:
                if proxy_url:
                    if qbt_session is None:
                        raise RuntimeError("qbt_session cannot be None")
                    response = await qbt_session.post(f"{qbt_proxy_url}/api/v2/torrents/start", data={"hashes": torrent.infohash})
                    if response.status_code == 404:
                        logger.debug("[cyan]Start endpoint returned 404, trying legacy resume endpoint (pre-v5.0.0)...")
                        resume_response = await qbt_session.post(f"{qbt_proxy_url}/api/v2/torrents/resume", data={"hashes": torrent.infohash})
                        if resume_response.status_code != 200:
                            logger.info(f"[yellow]Failed to resume torrent via proxy (resume): {resume_response.status_code}")
                    elif response.status_code != 200:
                        logger.info(f"[yellow]Failed to resume torrent via proxy: {response.status_code}")
                else:
                    if qbt_client is None:
                        raise RuntimeError("qbt_client cannot be None")
                    await self.retry_qbt_operation(lambda: asyncio.to_thread(qbt_client.torrents_resume, torrent.infohash), "Resume torrent")
            except TimeoutError:
                logger.info("[yellow]Failed to resume torrent after retries")
            except Exception as e:
                logger.info(f"[yellow]Error resuming torrent: {e}")

        if tracker in client.get("super_seed_trackers", []) and not cross:
            try:
                logger.debug(f"{tracker}: Setting super-seed mode.")
                if proxy_url:
                    if qbt_session is None:
                        raise RuntimeError("qbt_session cannot be None")
                    response = await qbt_session.post(f"{qbt_proxy_url}/api/v2/torrents/setSuperSeeding", data={"hashes": torrent.infohash, "value": "true"})
                    if response.status_code != 200:
                        logger.info(f"{tracker}: Failed to set super-seed via proxy: {response.status_code}")
                else:
                    if qbt_client is None:
                        raise RuntimeError("qbt_client cannot be None")
                    await self.retry_qbt_operation(
                        lambda: asyncio.to_thread(qbt_client.torrents_set_super_seeding, torrent_hashes=torrent.infohash), "Set super-seed mode", initial_timeout=10.0
                    )
            except TimeoutError:
                logger.info(f"{tracker}: Super-seed request timed out")
            except Exception as e:
                logger.info(f"{tracker}: Super-seed error: {e}")

        if meta.debug:
            try:
                if proxy_url:
                    if qbt_session is None:
                        raise RuntimeError("qbt_session should not be None")
                    response = await qbt_session.get(f"{qbt_proxy_url}/api/v2/torrents/info", params={"hashes": torrent.infohash})
                    if response.status_code == 200:
                        info = response.json()
                        if info:
                            logger.debug(f"[cyan]Actual qBittorrent save path: {info[0].get('save_path', 'Unknown')}")
                        else:
                            logger.debug("[yellow]No torrent info returned from proxy")
                    else:
                        logger.debug(f"[yellow]Failed to get torrent info via proxy: {response.status_code}")
                else:
                    if qbt_client is None:
                        raise RuntimeError("qbt_client should not be None")
                    info = await self.retry_qbt_operation(
                        lambda: asyncio.to_thread(qbt_client.torrents_info, torrent_hashes=torrent.infohash), "Get torrent info for debug", initial_timeout=10.0
                    )
                    if info:
                        logger.debug(f"[cyan]Actual qBittorrent save path: {info[0].save_path}")
                    else:
                        logger.debug("[yellow]No torrent info returned from qBittorrent")
            except TimeoutError:
                logger.debug("[yellow]Failed to get torrent info for debug after retries")
            except Exception as e:
                logger.debug(f"[yellow]Error getting torrent info for debug: {e}")

        logger.debug(f"Added to: {save_path}")

        if qbt_session:
            await qbt_session.aclose()

    async def get_pathed_torrents(self, path: str, meta: Meta) -> None:
        try:
            matching_torrents = await self.find_qbit_torrents_by_path(path, meta)

            # If we found matches, use the hash from the first exact match
            if matching_torrents:
                exact_matches = list(matching_torrents)
                if exact_matches:
                    meta.infohash = exact_matches[0]["hash"]
                    logger.debug(f"[green]Found exact torrent match with hash: {meta.infohash}")

            else:
                logger.debug("[yellow]No matching torrents for the path found in qBittorrent[/yellow]")

        except TimeoutError:
            raise
        except Exception as e:
            logger.error(f"[red]Error searching for torrents: {e!s}[/red]")
            logger.info(f"[dim]{traceback.format_exc()}[/dim]")

    async def find_qbit_torrents_by_path(self, content_path: str, meta: Meta) -> list[dict[str, Any]]:
        start_time = time.time()
        logger.debug(f"[yellow]Searching for torrents in qBittorrent for path: {content_path}[/yellow]")
        try:
            trackers_config = cast(dict[str, Any], self.config.get("TRACKERS", {}))
            mtv_config_value = trackers_config.get("MORETHANTV", {})
            mtv_config = cast(dict[str, Any], mtv_config_value) if isinstance(mtv_config_value, dict) else {}
            piece_limit = bool(self.config["DEFAULT"].get("prefer_max_16_torrent", False))
            mtv_torrent = bool(mtv_config.get("prefer_mtv_torrent", False))
            piece_size_constraints_enabled: str | bool
            # MORETHANTV preference takes priority as it's more restrictive (8 MiB vs 16 MiB)
            if mtv_torrent:
                piece_size_constraints_enabled = "MORETHANTV"
            elif piece_limit:
                piece_size_constraints_enabled = "16MiB"
            else:
                piece_size_constraints_enabled = False

            meta.piece_size_constraints_enabled = piece_size_constraints_enabled

            # Determine which clients to search
            clients_to_search: list[str] = []
            meta_client = meta.client
            if isinstance(meta_client, str) and meta_client != "none":
                clients_to_search = [meta_client]
            else:
                # Use searching_client_list if available, otherwise default client
                searching_list = self.config["DEFAULT"].get("searching_client_list", [])
                searching_list_values = self._coerce_str_list(searching_list)
                if searching_list_values:
                    clients_to_search = [c for c in searching_list_values if c and c != "none"]

                if not clients_to_search:
                    default_client = self.config["DEFAULT"].get("default_torrent_client")
                    if isinstance(default_client, str) and default_client != "none":
                        clients_to_search = [default_client]

            if not clients_to_search:
                logger.debug("[yellow]No clients configured for searching")
                end_time = time.time()
                logger.debug(f"Searching qBittorrent client data processed in {end_time - start_time:.2f} seconds")
                return []

            all_matching_torrents: list[dict[str, Any]] = []
            for client_name in clients_to_search:
                client_config = self.config["TORRENT_CLIENTS"].get(client_name)
                if not client_config:
                    logger.debug(f"[yellow]Client {client_name} not found in config")
                    continue

                torrent_client_type = client_config.get("torrent_client")

                if torrent_client_type != "qbit":
                    logger.debug(f"[yellow]Client {client_name} is not qBittorrent")
                    continue

                logger.debug(f"[cyan]Searching qBittorrent client: {client_name}")

                torrents = await self._search_single_qbit_client(client_config, content_path, meta, client_name)

                if torrents:
                    # Found matching torrents in this client
                    all_matching_torrents.extend(torrents)

                    # Check if we should stop searching additional clients
                    found_piece_size = meta.found_preferred_piece_size
                    constraints_enabled = meta.piece_size_constraints_enabled

                    stop_due_to_constraints = (
                        not constraints_enabled
                        or found_piece_size == "no_constraints"
                        or found_piece_size == "MORETHANTV"
                        or (found_piece_size == "16MiB" and constraints_enabled == "16MiB")
                    )
                    should_stop = stop_due_to_constraints

                    if should_stop:
                        logger.debug("[green]Stopping search after finding preferred torrent")
                        break
                else:
                    logger.debug(f"[yellow]No matches in client {client_name}")

            # Deduplicate by hash (in case same torrent exists in multiple clients)
            seen_hashes: set[str] = set()
            unique_torrents: list[dict[str, Any]] = []
            for torrent in all_matching_torrents:
                if torrent["hash"] not in seen_hashes:
                    seen_hashes.add(torrent["hash"])
                    unique_torrents.append(torrent)

            end_time = time.time()
            duration = end_time - start_time
            if meta.debug:
                if len(all_matching_torrents) != len(unique_torrents):
                    logger.debug(f"[cyan]Deduplicated {len(all_matching_torrents)} torrents to {len(unique_torrents)} unique torrents")
                logger.debug(f"Searching qBittorrent client data processed in {duration:.2f} seconds")

            return unique_torrents

        except TimeoutError:
            raise
        except Exception as e:
            logger.info(f"[bold red]Error finding torrents: {e!s}")
            logger.debug(traceback.format_exc())
            end_time = time.time()
            logger.debug(f"Searching qBittorrent client data processed in {end_time - start_time:.2f} seconds")
            return []

    def _build_proxy_search_url(self, qbt_proxy_url: str, search_term: str, qui_filters: dict[str, list[str]]) -> str:
        query_parts = [f"search={urllib.parse.quote(search_term)}", "sort=added_on", "reverse=true", "limit=100"]

        if qui_filters.get("excludeStatus"):
            filter_value = ",".join(qui_filters["excludeStatus"])
            query_parts.append(f"filter={urllib.parse.quote(filter_value)}")

        if qui_filters.get("categories"):
            category_value = ",".join(qui_filters["categories"])
            query_parts.append(f"category={urllib.parse.quote(category_value)}")

        if qui_filters.get("tags"):
            tag_value = ",".join(qui_filters["tags"])
            query_parts.append(f"tag={urllib.parse.quote(tag_value)}")

        query_string = "&".join(query_parts)
        return f"{qbt_proxy_url}/api/v2/torrents/search?{query_string}"

    def _build_mock_torrents(self, torrents_data: list[dict[str, Any]]) -> list[Any]:
        class MockTorrent:
            def __init__(self, data: dict[str, Any]):
                for key, value in data.items():
                    setattr(self, key, value)
                if not hasattr(self, "files"):
                    self.files: list[Any] = []
                if not hasattr(self, "tracker"):
                    self.tracker = ""
                if not hasattr(self, "comment"):
                    self.comment = ""

            def __getattr__(self, name: str) -> Any:
                return None

        return [MockTorrent(torrent) for torrent in torrents_data]

    def _torrent_name_matches(self, torrent_name: str, meta: Meta) -> bool:
        is_disc = meta.is_disc
        if is_disc in ("", None) and len(meta.filelist) == 1:
            file_path = meta.filelist[0]
            file_name = Path(file_path).name
            parent_dir = Path(file_path).parent.name
            return torrent_name.lower() == file_name.lower() or torrent_name.lower() == meta.uuid.lower() or (parent_dir and torrent_name.lower() == parent_dir.lower())
        return torrent_name.lower() == meta.uuid.lower()

    def _extract_tracker_matches(
        self, torrent: Any, tracker_patterns: dict[str, dict[str, str]], tracker_priority: list[str], has_working_tracker: bool, meta: Meta
    ) -> tuple[list[dict[str, Any]], bool]:
        tracker_found = False
        tracker_id_matches: list[dict[str, Any]] = []

        for tracker_id in tracker_priority:
            tracker_info = tracker_patterns.get(tracker_id)
            if not tracker_info:
                continue

            if tracker_info["url"] in torrent.comment and has_working_tracker:
                match = re.search(tracker_info["pattern"], torrent.comment)
                if match:
                    tracker_id_value = match.group(1)
                    tracker_id_matches.append({"id": tracker_id, "tracker_id": tracker_id_value})
                    meta[tracker_id] = tracker_id_value
                    tracker_found = True

        if torrent.tracker and "hawke.uno" in torrent.tracker and has_working_tracker:
            huno_id = None
            if "/torrents/" in torrent.comment:
                match = re.search(r"/torrents/(\d+)", torrent.comment)
                if match:
                    huno_id = match.group(1)

            if huno_id:
                tracker_id_matches.append(
                    {
                        "id": "huno",
                        "tracker_id": huno_id,
                    }
                )
                meta.huno = huno_id
                tracker_found = True

        if torrent.tracker and "tracker.anthelion.me" in torrent.tracker:
            ant_id = 1
            if has_working_tracker:
                tracker_id_matches.append(
                    {
                        "id": "ant",
                        "tracker_id": ant_id,
                    }
                )
                meta.ant = ant_id
                tracker_found = True

        return tracker_id_matches, tracker_found

    def _sort_matching_torrents(self, matching_torrents: list[dict[str, Any]], tracker_priority: list[str]) -> None:
        def get_priority_score(torrent: dict[str, Any]) -> tuple[bool, int, bool]:
            priority_score = 100
            if torrent.get("tracker_urls"):
                for tracker_url in torrent["tracker_urls"]:
                    tracker_id = tracker_url.get("id")
                    if tracker_id in tracker_priority:
                        score = tracker_priority.index(tracker_id)
                        priority_score = min(priority_score, score)

            return (not torrent["has_working_tracker"], priority_score, not torrent["has_tracker"])

        matching_torrents.sort(key=get_priority_score)

    def _setup_tracker_patterns(self) -> tuple[dict[str, dict[str, str]], list[str]]:
        from src.trackersetup import tracker_class_map

        tracker_patterns = {}
        for name in set(tracker_class_map.keys()) | {"PASSTHEPOPCORN", "BEYONDHD", "BTN", "HDBITS"}:
            # Determine URL
            url = ""
            if name in tracker_class_map:
                with contextlib.suppress(Exception):
                    tracker_instance = tracker_class_map[name](self.config)
                    url = getattr(tracker_instance, "base_url", "")
            if not url:
                url = self.config.get("TRACKERS", {}).get(name, {}).get("announce_url", "")
            if not url:
                # Hardcoded fallback
                hardcoded_urls = {
                    "PASSTHEPOPCORN": "passthepopcorn.me",
                    "AITHER": "https://aither.cc",
                    "LST": "https://lst.gg",
                    "ONLYENCODES": "https://onlyencodes.cc",
                    "BLUTOPIA": "https://blutopia.cc",
                    "ULCX": "https://upload.cx",
                    "HDBITS": "https://hdbits.org",
                    "BTN": "https://broadcasthe.net",
                    "BEYONDHD": "https://beyond-hd.me",
                    "HAWKEUNO": "https://hawke.uno",
                    "REELFLIX": "https://reelflix.xyz",
                    "OLDTOONSWORLD": "https://oldtoons.world",
                    "YUSCENE": "https://yu-scene.net",
                    "DARKPEERS": "https://darkpeers.org",
                    "SEEDPOOL": "https://seedpool.org",
                }
                url = hardcoded_urls.get(name, "")

            if url:
                # Determine pattern
                if name == "PASSTHEPOPCORN":
                    pattern = r"torrentid=(\d+)"
                elif name in ("HDBITS", "BTN"):
                    pattern = r"id=(\d+)"
                elif name == "BEYONDHD":
                    pattern = r"details/(\d+)"
                else:
                    pattern = r"/(\d+)$"

                tracker_patterns[name.lower()] = {"url": url, "pattern": pattern}

        prioritized = ["aither", "ulcx", "lst", "blu", "oe", "btn", "bhd", "huno", "hdb", "rf", "otw", "yus", "dp", "sp", "ptp"]
        all_known = sorted(tracker_patterns.keys())
        tracker_priority = prioritized + [t for t in all_known if t not in prioritized]
        return tracker_patterns, tracker_priority

    async def _fetch_torrents(
        self, proxy_url: str, qbt_proxy_url: str, qbt_session: httpx.AsyncClient | None, qbt_client: qbittorrentapi.Client | None, search_term: str
    ) -> list[Any]:
        try:
            if proxy_url:
                if qbt_session is None:
                    return []
                # Build qui's enhanced filter options with expression support
                qui_filters = {
                    "status": [],  # Empty = all statuses, or specify like ["downloading","seeding"]
                    # Reuse is determined by the local file layout and piece
                    # hashes, not by the health of the torrent's old tracker.
                    # Keeping this empty also makes this early lookup use the
                    # same query semantics as the upload-stage fallback.
                    "excludeStatus": [],
                    "categories": [],
                    "excludeCategories": [],
                    "tags": [],
                    "excludeTags": [],
                    "trackers": [],
                    "excludeTrackers": [],
                }

                url = self._build_proxy_search_url(qbt_proxy_url, search_term, qui_filters)

                logger.debug(f"[cyan]Searching qBittorrent via proxy: {Redaction.redact_private_info(url)}...")

                response_start_time = time.perf_counter()
                try:
                    response = await qbt_session.get(url)
                finally:
                    self._log_slow_client_response(time.perf_counter() - response_start_time, using_proxy=True)
                if response.status_code == 200:
                    response_data = response.json()

                    # The qui proxy returns {'torrents': [...]} while standard API returns [...]
                    torrents_data: list[dict[str, Any]]
                    if isinstance(response_data, dict) and "torrents" in response_data:
                        response_data_dict = cast(dict[str, Any], response_data)
                        torrents_value = response_data_dict.get("torrents", [])
                        torrents_data = cast(list[dict[str, Any]], torrents_value) if isinstance(torrents_value, list) else []
                    elif isinstance(response_data, list):
                        torrents_data = cast(list[dict[str, Any]], response_data)
                    else:
                        torrents_data = []

                    if torrents_data:
                        logger.debug(f"[cyan]qBittorrent proxy search returned {len(torrents_data)} torrents for '{search_term}'")
                    else:
                        logger.debug("[cyan]No matching torrents found via proxy search")

                    return self._build_mock_torrents(torrents_data)
                if response.status_code == 404:
                    logger.debug(f"[yellow]No torrents found via proxy search for '[green]{search_term}' [yellow]Maybe tracker errors?")
                else:
                    logger.debug(f"[bold red]Failed to get torrents list via proxy: {response.status_code}")
                return []
            if qbt_client is None:
                return []
            response_start_time = time.perf_counter()
            try:
                return await self.retry_qbt_operation(lambda: asyncio.to_thread(qbt_client.torrents_info), "Get torrents list", initial_timeout=14.0)
            finally:
                self._log_slow_client_response(time.perf_counter() - response_start_time, using_proxy=False)
        except TimeoutError:
            logger.info("[bold red]Getting torrents list timed out after retries")
            return []
        except Exception as e:
            logger.info(f"[bold red]Error getting torrents list: {e}")
            return []

    @staticmethod
    def _log_slow_client_response(duration: float, using_proxy: bool) -> None:
        if duration <= 5:
            return

        logger.info(f"[yellow]qBittorrent client response took {duration:.1f} seconds.[/yellow]")
        if not using_proxy:
            logger.info("[yellow]For faster searches, consider configuring 'qui_proxy_url' in your config.[/yellow]")

    async def _process_torrent_matches(
        self,
        torrents: list[Any],
        tracker_patterns: dict[str, dict[str, str]],
        tracker_priority: list[str],
        proxy_url: str,
        qbt_proxy_url: str,
        qbt_session: httpx.AsyncClient | None,
        qbt_client: qbittorrentapi.Client | None,
        meta: Meta,
    ) -> list[dict[str, Any]]:
        matching_torrents: list[dict[str, Any]] = []

        # First collect exact path matches
        for torrent in torrents:
            try:
                torrent_name = torrent.name
                if not torrent_name:
                    logger.debug("[yellow]Skipping torrent with missing name attribute")
                    continue

                if not self._torrent_name_matches(torrent_name, meta):
                    continue

                torrent_properties: dict[str, Any] = {}

                tracker_url = str(torrent.tracker or "")
                tracker_url_list = [tracker_url] if tracker_url else []
                torrent_trackers: list[dict[str, Any]] = []
                try:
                    if proxy_url and not torrent.comment:
                        logger.debug(f"[cyan]Fetching torrent properties via proxy for torrent: {torrent.name}")
                        if qbt_session is None:
                            raise RuntimeError("qbt_session should not be None")
                        response = await qbt_session.get(f"{qbt_proxy_url}/api/v2/torrents/properties", params={"hash": torrent.hash})
                        if response.status_code == 200:
                            torrent_properties = response.json()
                            torrent.comment = torrent_properties.get("comment", "")
                        else:
                            logger.debug(f"[yellow]Failed to get properties for torrent {torrent.name} via proxy: {response.status_code}")
                            continue
                    elif not proxy_url:
                        if qbt_client is None:
                            raise RuntimeError("qbt_client should not be None")
                        torrent_trackers = await self.retry_qbt_operation(
                            lambda qbt_client=qbt_client, torrent_hash=torrent.hash: asyncio.to_thread(qbt_client.torrents_trackers, torrent_hash=torrent_hash),
                            f"Get trackers for torrent {torrent.name}",
                        )
                except TimeoutError, qbittorrentapi.APIError:
                    logger.debug(f"[yellow]Failed to get trackers for torrent {torrent.name} after retries")
                    continue
                except Exception as e:
                    logger.debug(f"[yellow]Error getting trackers for torrent {torrent.name}: {e}")
                    continue

                if proxy_url:
                    proxy_trackers = getattr(torrent, "trackers", []) or []
                    torrent_trackers = cast(list[dict[str, Any]], proxy_trackers) if isinstance(proxy_trackers, list) else []
                    has_working_tracker = True
                else:
                    try:
                        display_trackers: list[dict[str, Any]] = []

                        # Filter out DHT, PEX, LSD "trackers"
                        for tracker in torrent_trackers or []:
                            if tracker.get("url", "").startswith(("** [DHT]", "** [PeX]", "** [LSD]")):
                                continue
                            display_trackers.append(tracker)

                        # Now process the filtered trackers
                        has_working_tracker = False
                        for display_tracker in display_trackers:
                            url = display_tracker.get("url", "Unknown URL")
                            status_code = display_tracker.get("status", 0)
                            status_text = {0: "Disabled", 1: "Not contacted", 2: "Working", 3: "Updating", 4: "Error"}.get(status_code, f"Unknown ({status_code})")

                            if status_code == 2:
                                has_working_tracker = True
                                logger.debug(f"[green]Tracker working: {url[:15]} - {status_text}")
                            else:
                                display_tracker.get("msg", "")

                    except qbittorrentapi.APIError as e:
                        logger.debug(f"[red]Error fetching trackers for torrent {torrent.name}: {e}")
                        continue

                torrent_comments = meta.torrent_comments
                if not isinstance(torrent_comments, list):
                    torrent_comments = []
                    meta.torrent_comments = torrent_comments
                torrent_comments = cast(list[dict[str, Any]], torrent_comments)

                await match_tracker_url(tracker_url_list, meta)

                match_info: dict[str, Any] = {
                    "hash": torrent.hash,
                    "name": torrent.name,
                    "save_path": torrent.save_path,
                    "content_path": os.path.normpath(Path(str(torrent.save_path)) / str(torrent.name)),
                    "size": torrent.size,
                    "category": torrent.category,
                    "seeders": torrent.num_complete,
                    "trackers": tracker_url,
                    "has_working_tracker": has_working_tracker,
                    "comment": torrent.comment,
                }

                tracker_id_matches, tracker_found = self._extract_tracker_matches(torrent, tracker_patterns, tracker_priority, has_working_tracker, meta)

                match_info["tracker_urls"] = tracker_id_matches
                match_info["has_tracker"] = tracker_found

                if tracker_found:
                    meta.found_tracker_match = True

                logger.debug(f"[cyan]Stored comment for torrent: {torrent.comment[:100]}...")

                torrent_comments.append(match_info)
                matching_torrents.append(match_info)

            except Exception as e:
                logger.debug(f"[yellow]Error processing torrent {torrent.name}: {e!s}")
                continue

        return matching_torrents

    async def _export_torrent_file(
        self,
        torrent_hash: str,
        proxy_url: str,
        qbt_proxy_url: str,
        qbt_session: httpx.AsyncClient | None,
        qbt_client: qbittorrentapi.Client | None,
        torrent_storage_dir: str | None,
        extracted_torrent_dir: str,
        is_alternative: bool = False,
    ) -> str | None:
        torrent_file_path = None
        prefix = "alternative " if is_alternative else ""

        if torrent_storage_dir:
            potential_path = Path(torrent_storage_dir) / f"{torrent_hash}.torrent"
            if Path(potential_path).exists():
                torrent_file_path = potential_path
                logger.debug(f"[cyan]Found existing {prefix}.torrent file: {torrent_file_path}")

        if not torrent_file_path:
            logger.debug(f"[cyan]Exporting {prefix}.torrent file for hash: {torrent_hash}")

            torrent_file_content = None
            if proxy_url:
                if qbt_session is None:
                    logger.info("[bold red]Proxy session not initialized")
                    return None
                qbt_proxy_url = proxy_url.rstrip("/")
                try:
                    response = await qbt_session.post(f"{qbt_proxy_url}/api/v2/torrents/export", data={"hash": torrent_hash})
                    if response.status_code == 200:
                        torrent_file_content = response.content
                    else:
                        logger.error(f"[red]Failed to export {prefix}torrent via proxy: {response.status_code}")
                except Exception as e:
                    logger.error(f"[red]Error exporting {prefix}torrent via proxy: {e}")
            else:
                if qbt_client is None:
                    logger.info("[bold red]qBittorrent client not initialized")
                    return None
                torrent_file_content = await self.retry_qbt_operation(
                    lambda: asyncio.to_thread(qbt_client.torrents_export, torrent_hash=torrent_hash), f"Export {prefix}torrent {torrent_hash}"
                )

            if torrent_file_content is not None:
                torrent_file_path = Path(extracted_torrent_dir) / f"{torrent_hash}.torrent"
                await asyncio.to_thread(Path(torrent_file_path).write_bytes, torrent_file_content)
                logger.debug(f"[green]Exported {prefix}.torrent file to: {torrent_file_path}")
            else:
                logger.info(f"[bold red]Failed to export {prefix}.torrent for {torrent_hash} after retries")

        return str(torrent_file_path) if torrent_file_path else None

    async def _process_base_torrent_creation(
        self,
        matching_torrents: list[dict[str, Any]],
        client_config: dict[str, Any],
        proxy_url: str,
        qbt_proxy_url: str,
        qbt_session: httpx.AsyncClient | None,
        qbt_client: qbittorrentapi.Client | None,
        meta: Meta,
    ) -> None:
        if not meta.base_torrent_created:
            torrent_storage_dir = client_config.get("torrent_storage_dir")

            extracted_torrent_dir = str(Path(meta.base_dir) / "tmp" / meta.uuid)
            Path(extracted_torrent_dir).mkdir(parents=True, exist_ok=True)

            # Set up piece size preference logic
            mtv_config = self.config.get("TRACKERS", {}).get("MORETHANTV", {})
            prefer_small_pieces = mtv_config.get("prefer_mtv_torrent", False)
            piece_limit = self.config["DEFAULT"].get("prefer_max_16_torrent", False)

            # Use piece preference if MORETHANTV preference is true, otherwise use general piece limit
            use_piece_preference = prefer_small_pieces or piece_limit
            piece_size_best_match: dict[str, Any] | None = None  # Track the best match for fallback if piece preference is enabled
            subtitle_fallback: dict[str, str] | None = None
            found_valid_torrent = False

            # Try the best match first (from the sorted matching torrents)
            best_torrent_match = matching_torrents[0]
            torrent_hash = best_torrent_match["hash"]

            torrent_file_path = await self._export_torrent_file(
                torrent_hash, proxy_url, qbt_proxy_url, qbt_session, qbt_client, torrent_storage_dir, extracted_torrent_dir, is_alternative=False
            )

            if torrent_file_path:
                valid, torrent_path = await self.is_valid_torrent(meta, torrent_file_path, torrent_hash, "qbit", client_config)
                if valid:
                    if meta.subtitle_files and not self._torrent_includes_all_local_subtitles(torrent_file_path, meta):
                        if self._torrent_has_no_subtitles(torrent_file_path):
                            subtitle_fallback = {"hash": torrent_hash, "torrent_path": torrent_path or torrent_file_path}
                            logger.debug(f"[yellow]Keeping video-only torrent as fallback: {torrent_hash}")
                        else:
                            logger.debug(f"[yellow]Skipping partial-subtitle torrent as fallback: {torrent_hash}")
                    elif use_piece_preference:
                        # **Track best match based on piece size**
                        try:
                            torrent_data = Torrent.read(torrent_file_path)
                            piece_size = torrent_data.piece_size
                            # For prefer_small_pieces: prefer smallest pieces
                            # For piece_limit: prefer torrents with piece size <= 16 MiB (16777216 bytes)
                            is_better_match = False
                            if prefer_small_pieces:
                                # MORETHANTV preference: always prefer smaller pieces
                                is_better_match = True if piece_size_best_match is None else piece_size < piece_size_best_match["piece_size"]
                            elif piece_limit and piece_size <= 16777216:
                                # General preference: prefer <= 16 MiB pieces, then smaller within that range
                                if piece_size_best_match is None:
                                    is_better_match = True
                                else:
                                    is_better_match = piece_size_best_match["piece_size"] > 16777216 or piece_size < piece_size_best_match["piece_size"]

                            if is_better_match:
                                piece_size_best_match = {"hash": torrent_hash, "torrent_path": torrent_path if torrent_path else torrent_file_path, "piece_size": piece_size}
                                logger.debug(f"[green]Updated best match: {piece_size_best_match}")
                        except Exception as e:
                            logger.info(f"[bold red]Error reading torrent data for {torrent_hash}: {e}")
                            if Path(torrent_file_path).exists() and torrent_file_path.startswith(extracted_torrent_dir):
                                Path(torrent_file_path).unlink()
                    else:
                        # If piece preference is disabled, return first valid torrent
                        try:
                            await TorrentCreator.create_base_from_existing_torrent(torrent_file_path, meta.base_dir, meta.uuid)
                            logger.debug(f"[green]Created BASE.torrent from first valid torrent: {torrent_hash}")
                            meta.base_torrent_created = True
                            meta.hash_used = torrent_hash
                            found_valid_torrent = True
                        except Exception as e:
                            logger.info(f"[bold red]Error creating BASE.torrent: {e}")
                else:
                    logger.debug(f"[bold red]{torrent_hash} failed validation")
                    if Path(torrent_file_path).exists() and torrent_file_path.startswith(extracted_torrent_dir):
                        Path(torrent_file_path).unlink()

                    # If first torrent fails validation, continue to try other matches
                    if not found_valid_torrent and meta.debug:
                        logger.info("[yellow]First torrent failed validation, trying other torrent matches...")

            # Try other matches if the best match isn't valid or if we need to find all valid torrents for piece preference
            if not found_valid_torrent or (use_piece_preference and not piece_size_best_match):
                logger.debug("[yellow]Trying other torrent matches...")
                for torrent_match in matching_torrents[1:]:  # Skip the first one since we already tried it
                    alt_torrent_hash = torrent_match["hash"]
                    alt_torrent_file_path = await self._export_torrent_file(
                        alt_torrent_hash, proxy_url, qbt_proxy_url, qbt_session, qbt_client, torrent_storage_dir, extracted_torrent_dir, is_alternative=True
                    )

                    # Validate the alternative torrent
                    if alt_torrent_file_path:
                        alt_valid, alt_torrent_path = await self.is_valid_torrent(meta, alt_torrent_file_path, alt_torrent_hash, "qbit", client_config)

                        if alt_valid:
                            if meta.subtitle_files and not self._torrent_includes_all_local_subtitles(alt_torrent_file_path, meta):
                                if self._torrent_has_no_subtitles(alt_torrent_file_path):
                                    subtitle_fallback = {"hash": alt_torrent_hash, "torrent_path": alt_torrent_path or alt_torrent_file_path}
                                    logger.debug(f"[yellow]Keeping video-only alternative as fallback: {alt_torrent_hash}")
                                else:
                                    logger.debug(f"[yellow]Skipping partial-subtitle alternative as fallback: {alt_torrent_hash}")
                            elif use_piece_preference:
                                # **Track best match based on piece size**
                                try:
                                    torrent_data = Torrent.read(alt_torrent_file_path)
                                    piece_size = torrent_data.piece_size
                                    # For prefer_small_pieces: prefer smallest pieces
                                    # For piece_limit: prefer torrents with piece size <= 16 MiB (16777216 bytes)
                                    is_better_match = False
                                    if prefer_small_pieces:
                                        # MORETHANTV preference: always prefer smaller pieces
                                        is_better_match = True if piece_size_best_match is None else piece_size < piece_size_best_match["piece_size"]
                                    elif piece_limit and piece_size <= 16777216:
                                        # General preference: prefer <= 16 MiB pieces, then smaller within that range
                                        if piece_size_best_match is None:
                                            is_better_match = True
                                        else:
                                            is_better_match = piece_size_best_match["piece_size"] > 16777216 or piece_size < piece_size_best_match["piece_size"]

                                    if is_better_match:
                                        piece_size_best_match = {
                                            "hash": alt_torrent_hash,
                                            "torrent_path": alt_torrent_path if alt_torrent_path else alt_torrent_file_path,
                                            "piece_size": piece_size,
                                        }
                                        logger.debug(f"[green]Updated best match: {piece_size_best_match}")
                                except Exception as e:
                                    logger.info(f"[bold red]Error reading torrent data for {alt_torrent_hash}: {e}")
                            else:
                                # If piece preference is disabled, return first valid torrent
                                try:
                                    await TorrentCreator.create_base_from_existing_torrent(alt_torrent_file_path, meta.base_dir, meta.uuid)
                                    logger.debug(f"[green]Created BASE.torrent from alternative torrent {alt_torrent_hash}")
                                    meta.infohash = alt_torrent_hash
                                    meta.base_torrent_created = True
                                    meta.hash_used = alt_torrent_hash
                                    found_valid_torrent = True
                                    break
                                except Exception as e:
                                    logger.info(f"[bold red]Error creating BASE.torrent for alternative: {e}")
                        else:
                            logger.debug(f"[bold red]{alt_torrent_hash} failed validation")
                            if Path(alt_torrent_file_path).exists() and alt_torrent_file_path.startswith(extracted_torrent_dir):
                                Path(alt_torrent_file_path).unlink()

                if subtitle_fallback and not found_valid_torrent and not piece_size_best_match:
                    try:
                        await TorrentCreator.create_base_from_existing_torrent(subtitle_fallback["torrent_path"], meta.base_dir, meta.uuid)
                        meta.infohash = subtitle_fallback["hash"]
                        meta.hash_used = subtitle_fallback["hash"]
                        meta.base_torrent_created = True
                        found_valid_torrent = True
                        logger.info(f"[yellow]No torrent with all local subtitles found; using video-only fallback: {subtitle_fallback['hash']}")
                    except Exception as e:
                        logger.info(f"[bold red]Error creating BASE.torrent from video-only fallback: {e}")

                if not found_valid_torrent:
                    logger.debug("[bold red]No valid torrents found after checking all matches, falling back to a best match if preference is set")
                    meta.we_checked_them_all = True

            # **Return the best match if piece preference is enabled**
            if use_piece_preference and piece_size_best_match and not found_valid_torrent:
                try:
                    preference_type = "MORETHANTV preference" if prefer_small_pieces else "16 MiB piece limit"
                    logger.info(f"[green]Using best match torrent ({preference_type}) with hash: {piece_size_best_match['hash']}")
                    await TorrentCreator.create_base_from_existing_torrent(piece_size_best_match["torrent_path"], meta.base_dir, meta.uuid)
                    if meta.debug:
                        piece_size_mib = piece_size_best_match["piece_size"] / 1024 / 1024
                        logger.debug(f"[green]Created BASE.torrent from best match torrent: {piece_size_best_match['hash']} (piece size: {piece_size_mib:.1f} MiB)")
                    meta.infohash = piece_size_best_match["hash"]
                    meta.base_torrent_created = True
                    meta.hash_used = piece_size_best_match["hash"]
                    found_valid_torrent = True

                    # Check if the best match actually meets the piece size constraint
                    piece_size = piece_size_best_match["piece_size"]
                    if prefer_small_pieces and piece_size <= 8388608:  # 8 MiB
                        meta.found_preferred_piece_size = "MORETHANTV"
                    elif piece_limit and piece_size <= 16777216:  # 16 MiB
                        meta.found_preferred_piece_size = "16MiB"
                    else:
                        # Found a torrent but it doesn't meet the constraint
                        meta.found_preferred_piece_size = None
                except Exception as e:
                    logger.info(f"[bold red]Error creating BASE.torrent from best match: {e}")
            elif use_piece_preference and not piece_size_best_match:
                logger.info("[yellow]No preferred torrents found matching piece size preferences.")
                meta.we_checked_them_all = True
                meta.found_preferred_piece_size = None

            # If piece preference is not enabled, set flag to indicate we can stop searching
            if not use_piece_preference and found_valid_torrent:
                meta.found_preferred_piece_size = "no_constraints"

    async def _search_single_qbit_client(self, client_config: dict[str, Any], _content_path: str, meta: Meta, client_name: str) -> list[dict[str, Any]]:
        """Search a single qBittorrent client for matching torrents."""
        qbt_session: httpx.AsyncClient | None = None
        qbt_client: qbittorrentapi.Client | None = None
        qbt_proxy_url = ""
        proxy_url = client_config.get("qui_proxy_url", "").strip()
        try:
            tracker_patterns, tracker_priority = self._setup_tracker_patterns()

            if proxy_url:
                try:
                    ssl_context = self.create_ssl_context_for_client(client_config)
                    qbt_session = httpx.AsyncClient(timeout=10.0, verify=ssl_context)
                    qbt_proxy_url = proxy_url.rstrip("/")

                except Exception as e:
                    logger.info(f"[bold red]Failed to connect to qBittorrent proxy: {e}")
                    return []
            else:
                potential_qbt_client = await self.init_qbittorrent_client(client_config)
                if not potential_qbt_client:
                    return []
                qbt_client = potential_qbt_client

            search_term = meta.uuid.replace("[", ".").replace("]", ".")
            torrents = await self._fetch_torrents(proxy_url, qbt_proxy_url, qbt_session, qbt_client, search_term)

            if not torrents:
                return []

            matching_torrents = await self._process_torrent_matches(torrents, tracker_patterns, tracker_priority, proxy_url, qbt_proxy_url, qbt_session, qbt_client, meta)

            if matching_torrents:
                self._sort_matching_torrents(matching_torrents, tracker_priority)

                if matching_torrents:
                    # Extract tracker IDs to meta for the best match (first one after sorting)
                    best_match = matching_torrents[0]
                    meta.infohash = best_match["hash"]

                    # Always extract tracker IDs from the best match
                    if best_match["has_tracker"]:
                        for tracker in best_match["tracker_urls"]:
                            if tracker.get("id") and tracker.get("tracker_id"):
                                meta[tracker["id"]] = tracker["tracker_id"]
                                logger.debug(f"[bold cyan]Found {tracker['id'].upper()} ID: {tracker['tracker_id']} in torrent comment")

                    await self._process_base_torrent_creation(matching_torrents, client_config, proxy_url, qbt_proxy_url, qbt_session, qbt_client, meta)

            # Display results summary
            if meta.debug:
                if matching_torrents:
                    logger.debug(f"[green]Found {len(matching_torrents)} matching torrents in {client_name}")
                    logger.debug(f"[green]Torrents with working trackers: {sum(1 for t in matching_torrents if t.get('has_working_tracker', False))}")
                else:
                    logger.debug(f"[yellow]No matching torrents found in {client_name}")

            return matching_torrents

        except TimeoutError:
            raise
        except Exception as e:
            logger.info(f"[bold red]Error finding torrents in {client_name}: {e!s}")
            logger.debug(traceback.format_exc())
            return []
        finally:
            if qbt_session is not None:
                await qbt_session.aclose()


_cached_tracker_url_patterns: dict[str, list[str]] | None = None


async def match_tracker_url(tracker_urls: list[str], meta: Meta) -> None:
    global _cached_tracker_url_patterns
    if _cached_tracker_url_patterns is None:
        from src.trackersetup import tracker_class_map

        patterns = {}
        for name, tracker_class in tracker_class_map.items():
            urls = getattr(tracker_class, "tracker_urls", None)
            if urls:
                patterns[name.lower()] = urls
        patterns.setdefault("btn", ["https://broadcasthe.net"])
        _cached_tracker_url_patterns = patterns

    tracker_url_patterns = _cached_tracker_url_patterns
    found_ids: set[str] = set()
    for tracker in tracker_urls:
        for tracker_id, patterns in tracker_url_patterns.items():
            for pattern in patterns:
                if pattern in tracker:
                    found_ids.add(tracker_id.upper())
                    logger.debug(f"[bold cyan]Matched {tracker_id.upper()} in tracker URL: {Redaction.redact_private_info(tracker)}")
                    if tracker_id.upper() == "PASSTHEPOPCORN" and "passthepopcorn.me" in tracker and tracker.startswith("http://"):
                        logger.info("[red]Found PASSTHEPOPCORN announce URL using plaintext HTTP.\n")
                        logger.info(
                            "[red]PASSTHEPOPCORN is turning off their plaintext HTTP tracker soon. You must update your announce URLS. See PASSTHEPOPCORN/forums.php?page=1&action=viewthread&threadid=46663"
                        )

    if "remove_trackers" not in meta or not isinstance(meta.remove_trackers, list):
        meta.remove_trackers = []
    remove_trackers = meta.remove_trackers

    for tracker_id in found_ids:
        if tracker_id not in remove_trackers:
            remove_trackers.append(tracker_id)
    logger.debug(f"[bold cyan]Storing matched tracker IDs for later removal: {remove_trackers}")


async def create_cross_seed_links(meta: Meta, torrent: Torrent, tracker_dir: str, use_hardlink: bool) -> bool:
    metainfo_raw = getattr(torrent, "metainfo", {})
    metainfo: dict[str, Any] = cast(dict[str, Any], metainfo_raw) if isinstance(metainfo_raw, dict) else cast(dict[str, Any], {})
    info_raw = metainfo.get("info")
    info = cast(dict[str, Any], info_raw) if isinstance(info_raw, dict) else {}
    raw_torrent_name = info.get("name.utf-8") or info.get("name") or getattr(torrent, "name", None)
    torrent_name = str(raw_torrent_name) if raw_torrent_name else None
    if not torrent_name:
        logger.info("[bold red]Cross-seed torrent is missing an info name; cannot build link structure")
        return False

    multi_file = bool(info.get("files"))
    torrent_files: list[_TorrentFileEntry] = []

    def decode_component(value: Any) -> str:
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="ignore")
        return str(value)

    if multi_file:
        files_raw = info.get("files", [])
        files_list = cast(list[dict[str, Any]], files_raw) if isinstance(files_raw, list) else []
        for file_entry in files_list:
            raw_path: Any = file_entry.get("path.utf-8") or file_entry.get("path") or []
            if isinstance(raw_path, (list, tuple)):
                raw_path_list = cast(list[Any], raw_path)
                components = [decode_component(part) for part in raw_path_list]
                rel_path = Path(*components) if components else ""
            else:
                rel_path = decode_component(raw_path)
            rel_path = rel_path.replace("/", os.sep)
            rel_path = rel_path.replace("\\", os.sep)
            rel_path = os.path.normpath(rel_path)
            if rel_path.startswith(".."):
                rel_path = rel_path.lstrip(".\\/")
            length_value = file_entry.get("length")
            torrent_files.append({"relative_path": rel_path, "length": length_value if isinstance(length_value, int) else None})
    else:
        length_value = info.get("length")
        torrent_files.append({"relative_path": torrent_name, "length": length_value if isinstance(length_value, int) else None})

    destination_root = Path(tracker_dir) / torrent_name if multi_file else tracker_dir
    if multi_file:
        await asyncio.to_thread(os.makedirs, destination_root, exist_ok=True)
    else:
        await asyncio.to_thread(os.makedirs, tracker_dir, exist_ok=True)

    release_root_value = meta.path
    release_root = release_root_value if isinstance(release_root_value, str) else None
    candidate_paths: list[str] = []
    if release_root and Path(release_root).is_dir():
        for root, _, files in os.walk(release_root):
            candidate_paths.extend([Path(root) / file for file in files])
    else:
        filelist_value = meta.filelist
        if isinstance(filelist_value, list):
            filelist_raw = filelist_value
            filelist = [str(path) for path in filelist_raw if path]
        elif filelist_value:
            filelist = [str(filelist_value)]
        else:
            filelist = []
        if filelist:
            candidate_paths.extend(filelist)
            parent_guess = str(Path(filelist[0]).parent)
        else:
            parent_guess = str(Path(release_root or "").parent)
        if parent_guess and Path(parent_guess).is_dir():
            for root, _, files in os.walk(parent_guess):
                candidate_paths.extend([Path(root) / file for file in files])

    unique_candidates: list[_CandidateEntry] = []
    seen: set[str] = set()
    tracker_abs = str(Path(tracker_dir).resolve()) if tracker_dir else None
    for candidate in candidate_paths:
        if not candidate:
            continue
        abs_candidate = str(Path(candidate).resolve())
        if abs_candidate in seen:
            continue
        seen.add(abs_candidate)
        if not Path(abs_candidate).is_file():
            continue
        if tracker_abs:
            try:
                if os.path.commonpath([abs_candidate, tracker_abs]) == tracker_abs:
                    continue
            except ValueError:
                pass
        try:
            size = Path(abs_candidate).stat().st_size
        except OSError:
            size = None
        unique_candidates.append({"path": abs_candidate, "name": Path(abs_candidate).name.lower(), "size": size, "used": False})

    if not unique_candidates:
        logger.info("[bold red]Unable to find source files for cross-seed linking")
        return False

    def pick_candidate(filename: str | None, length: int | None) -> tuple[str | None, str | None]:
        lower_name = (filename or "").lower()

        if lower_name:
            for entry in unique_candidates:
                if entry["used"]:
                    continue
                if entry["name"] == lower_name and length is not None and entry["size"] == length:
                    entry["used"] = True
                    return entry["path"], "name_size"

        if lower_name:
            for entry in unique_candidates:
                if entry["used"]:
                    continue
                if entry["name"] == lower_name:
                    entry["used"] = True
                    return entry["path"], "name_only"

        if length is not None:
            for entry in unique_candidates:
                if entry["used"]:
                    continue
                if entry["size"] == length:
                    entry["used"] = True
                    return entry["path"], "size_only"

        for entry in unique_candidates:
            if entry["used"]:
                continue
            entry["used"] = True
            return entry["path"], "fallback"

        return None, None

    for torrent_file in torrent_files:
        relative_path = torrent_file["relative_path"]
        dest_file_path = Path(tracker_dir) / torrent_name / relative_path if multi_file else Path(tracker_dir) / torrent_name
        dest_file_path = os.path.normpath(dest_file_path)
        tracker_root = str(Path(tracker_dir).resolve())
        try:
            if os.path.commonpath([tracker_root, str(Path(dest_file_path).resolve())]) != tracker_root:
                logger.info(f"[bold red]Refusing to create link outside tracker directory: {dest_file_path}")
                return False
        except ValueError:
            logger.info(f"[bold red]Refusing to create link outside tracker directory: {dest_file_path}")
            return False

        source_file, match_reason = pick_candidate(Path(relative_path).name, torrent_file.get("length"))
        if not source_file:
            logger.info(f"[bold red]Failed to map cross-seed file: {relative_path}")
            return False
        if match_reason == "fallback":
            logger.debug(f"[yellow]Cross-seed mapping fallback used for: {relative_path}")

        dest_parent = str(Path(dest_file_path).parent)
        if dest_parent:
            await asyncio.to_thread(os.makedirs, dest_parent, exist_ok=True)
        if await asyncio.to_thread(os.path.exists, dest_file_path):
            logger.debug(f"[yellow]Cross-seed link already exists, keeping: {dest_file_path}")
            continue

        linked = await async_link_directory(source_file, dest_file_path, use_hardlink=use_hardlink)
        if not linked:
            logger.info(f"[bold red]Linking failed for cross-seed file: {relative_path}")
            return False

    logger.debug(f"[green]Prepared cross-seed link tree at {Path(tracker_dir) / torrent_name if multi_file else tracker_dir}")
    return True


async def async_link_directory(src: str, dst: str, use_hardlink: bool = True) -> bool:
    try:
        # Create destination directory
        await asyncio.to_thread(os.makedirs, str(Path(dst).parent), exist_ok=True)

        # Check if destination already exists
        if await asyncio.to_thread(os.path.exists, dst):
            logger.debug(f"[yellow]Skipping linking, path already exists: {dst}")
            return True

        # Handle file linking
        if await asyncio.to_thread(os.path.isfile, src):
            if use_hardlink:
                try:
                    await asyncio.to_thread(os.link, src, dst)
                    logger.debug(f"[green]Hard link created: {dst} -> {src}")
                    return True
                except OSError as e:
                    logger.info(f"[yellow]Hard link failed: {e}")
                    return False
            else:  # Use symlink
                try:
                    if platform.system() == "Windows":
                        await asyncio.to_thread(os.symlink, src, dst, target_is_directory=False)
                    else:
                        await asyncio.to_thread(os.symlink, src, dst)

                    logger.debug(f"[green]Symbolic link created: {dst} -> {src}")
                    return True
                except OSError as e:
                    logger.info(f"[yellow]Symlink failed: {e}")
                    return False

        # Handle directory linking
        else:
            if use_hardlink:
                # For hardlinks, we need to recreate the directory structure
                await asyncio.to_thread(os.makedirs, dst, exist_ok=True)

                # Get all files in the source directory
                def _collect_files(src: str, dst: str) -> list[tuple[str, str, str]]:
                    items: list[tuple[str, str, str]] = []
                    for root, _dirs, files in os.walk(src):
                        for file in files:
                            src_path = Path(root) / file
                            rel_path = os.path.relpath(src_path, src)
                            items.append((src_path, Path(dst) / rel_path, rel_path))
                    return items

                all_items = await asyncio.to_thread(_collect_files, src, dst)

                # Create subdirectories first (to avoid race conditions)
                subdirs: set[str] = set()
                for _, dst_path, _ in all_items:
                    subdir = str(Path(dst_path).parent)
                    if subdir and subdir not in subdirs:
                        subdirs.add(subdir)
                        await asyncio.to_thread(os.makedirs, subdir, exist_ok=True)

                def _try_hardlink(src_path: str, dst_path: str, rel_path: str) -> bool:
                    try:
                        os.link(src_path, dst_path)
                        if rel_path == os.path.relpath(all_items[0][0], src):
                            logger.debug(f"[green]Hard link created for file: {dst_path} -> {src_path}")
                        return True
                    except OSError as e:
                        logger.info(f"[yellow]Hard link failed for file {rel_path}: {e}")
                        return False

                # Create hardlinks for all files
                success = True
                for src_path, dst_path, rel_path in all_items:
                    if not await asyncio.to_thread(_try_hardlink, src_path, dst_path, rel_path):
                        success = False
                        break

                return success
            # For symlinks, just link the directory itself
            try:
                if platform.system() == "Windows":
                    await asyncio.to_thread(os.symlink, src, dst, target_is_directory=True)
                else:
                    await asyncio.to_thread(os.symlink, src, dst)

                logger.debug(f"[green]Symbolic link created: {dst} -> {src}")
                return True
            except OSError as e:
                logger.info(f"[yellow]Symlink failed: {e}")
                return False

    except Exception as e:
        logger.info(f"[bold red]Error during linking: {e}")
        return False
