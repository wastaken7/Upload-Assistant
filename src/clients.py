# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import asyncio
import os
import re
import shutil
import urllib.parse
from pathlib import Path
from typing import Any, cast

import defusedxml.xmlrpc
import httpx
import qbittorrentapi
from torf import Torrent

from src.console import logger
from src.meta import Meta
from src.torrent_clients import DelugeClientMixin, QbittorrentClientMixin, RtorrentClientMixin, TransmissionClientMixin
from src.torrent_clients.path_utils import coerce_str_list, is_path_under
from src.torrentcreate import SUBTITLE_EXTENSIONS

# Secure XML-RPC client using defusedxml to prevent XML attacks
defusedxml.xmlrpc.monkey_patch()


class Clients(QbittorrentClientMixin, RtorrentClientMixin, DelugeClientMixin, TransmissionClientMixin):
    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize torrent-client operations with the application config."""
        self.config = config
        self._tracker_comment_hosts: dict[str, tuple[str, ...]] | None = None

    @staticmethod
    def _matches_tracker_host(host: str, tracker_hosts: dict[str, tuple[str, ...]]) -> str | None:
        for tracker_name, domains in tracker_hosts.items():
            if any(host == domain or host.endswith(f".{domain}") for domain in domains):
                return tracker_name
        return None

    def _get_tracker_comment_hosts(self) -> dict[str, tuple[str, ...]]:
        if self._tracker_comment_hosts is None:
            from src.trackersetup import get_tracker_comment_hosts

            self._tracker_comment_hosts = get_tracker_comment_hosts(self.config)
        return self._tracker_comment_hosts

    def _extract_tracker_ids_from_comment(self, comment: str) -> dict[str, str]:
        """Extract known tracker IDs from a torrent comment URL set."""
        if not comment:
            return {}

        def _last_path_id(path: str) -> str | None:
            """Extract a numeric tracker ID from the end of a URL path."""
            match = re.search(r"/(\d+)$", path)
            return match.group(1) if match else None

        def _query_id(query: str, key: str) -> str | None:
            """Extract the first value for key from a URL query string."""
            values = urllib.parse.parse_qs(query).get(key)
            return values[0] if values else None

        tracker_ids: dict[str, str] = {}
        urls: list[str] = re.findall(r"https?://[^\s\"'<>]+", comment)
        tracker_hosts = self._get_tracker_comment_hosts()
        for url in urls:
            parsed = urllib.parse.urlparse(url)
            host = (parsed.hostname or "").lower()
            path = parsed.path

            matched_tracker = self._matches_tracker_host(host, tracker_hosts)

            if not matched_tracker:
                continue

            # Canonical-class-name → established metadata key mapping
            _tracker_key_aliases: dict[str, str] = {
                "PASSTHEPOPCORN": "ptp",
                "HDBITS": "hdb",
                "BEYONDHD": "bhd",
                "BLUTOPIA": "blu",
                "ONLYENCODES": "oe",
                "BTN": "btn",
            }
            tracker_key = _tracker_key_aliases.get(matched_tracker, matched_tracker.lower())

            if matched_tracker == "PASSTHEPOPCORN":
                ptp_id = _query_id(parsed.query, "torrentid")
                if ptp_id:
                    tracker_ids[tracker_key] = ptp_id
            elif matched_tracker == "HDBITS":
                hdb_id = _query_id(parsed.query, "id")
                if hdb_id:
                    tracker_ids[tracker_key] = hdb_id
            elif matched_tracker == "BTN":
                btn_id = _query_id(parsed.query, "id")
                if btn_id:
                    tracker_ids[tracker_key] = btn_id
            elif matched_tracker in {"BeyondHD", "BEYONDHD"}:
                match = re.search(r"/details/(\d+)", path)
                if match:
                    tracker_ids[tracker_key] = match.group(1)
            elif matched_tracker == "ORPHEUS":
                torrent_id = _query_id(parsed.query, "torrentid")
                if torrent_id:
                    tracker_ids[tracker_key] = torrent_id
            else:
                # UNIT3D style: last path ID
                tracker_id = _last_path_id(path)
                if tracker_id:
                    tracker_ids[tracker_key] = tracker_id

        return tracker_ids

    async def add_to_client(self, meta: Meta, tracker: str, cross: bool = False) -> None:
        """Add the prepared torrent to each configured client."""
        if meta.path is None:
            logger.info("[bold red]meta.path is None, cannot add to client")
            return
        if cross:
            torrent_path = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/[{tracker}_cross].torrent"
        elif meta.debug:
            torrent_path = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/[{tracker}_DEBUG].torrent"
        else:
            torrent_path = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/[{tracker}].torrent"
        if meta.no_seed is True:
            logger.info("[bold red]--no-seed was passed, so the torrent will not be added to the client")
            logger.info("[bold yellow]Add torrent manually to the client")
            return
        if Path(torrent_path).exists():
            torrent = Torrent.read(torrent_path)
        else:
            logger.info(f"[bold red]Torrent file {torrent_path} does not exist, cannot add to client")
            return

        inject_clients: list[str] = []
        client_value = meta.client
        if isinstance(client_value, str) and client_value != "none":
            inject_clients = [client_value]
            logger.debug(f"[cyan]DEBUG: Using client from meta: {inject_clients}[/cyan]")
        elif client_value == "none":
            logger.debug("[cyan]DEBUG: meta client is 'none', skipping adding to client[/cyan]")
            return
        else:
            try:
                inject_clients_config = self.config["DEFAULT"].get("injecting_client_list")
                if isinstance(inject_clients_config, str) and inject_clients_config.strip():
                    inject_clients = [inject_clients_config]
                    logger.debug(f"[cyan]DEBUG: Converted injecting_client_list string to list: {inject_clients}[/cyan]")
                elif isinstance(inject_clients_config, list):
                    # Filter out empty strings and whitespace-only strings
                    inject_clients_list = cast(list[Any], inject_clients_config)
                    inject_clients = [str(c).strip() for c in inject_clients_list if str(c).strip()]
                    logger.debug(f"[cyan]DEBUG: Using injecting_client_list from config: {inject_clients}[/cyan]")
                else:
                    inject_clients = []
            except Exception as e:
                logger.debug(f"[cyan]DEBUG: Error reading injecting_client_list from config: {e}[/cyan]")

            if not inject_clients:
                default_client = self.config["DEFAULT"].get("default_torrent_client")
                if isinstance(default_client, str) and default_client != "none":
                    logger.debug(f"[cyan]DEBUG: Falling back to default_torrent_client: {default_client}[/cyan]")
                    inject_clients = [default_client]

        if not inject_clients:
            logger.debug("[cyan]DEBUG: No clients configured for injecting[/cyan]")
            return

        logger.debug(f"[cyan]DEBUG: Clients to inject into: {inject_clients}[/cyan]")

        for client_name in inject_clients:
            client_to_skip = self.config["TRACKERS"][tracker].get("client_to_skip", [])
            if client_name in client_to_skip:
                logger.debug(f"[cyan]DEBUG: Skipping client '{client_name}' for tracker '{tracker}' as it's in client_to_skip list[/cyan]")
                continue
            if client_name == "none" or not client_name:
                continue

            if client_name not in self.config["TORRENT_CLIENTS"]:
                logger.info(f"[bold red]Torrent client '{client_name}' not found in config.")
                continue

            client = self.config["TORRENT_CLIENTS"][client_name]
            torrent_client = client["torrent_client"]
            await self.inject_delay(meta, tracker, client_name)

            # Must pass client_name to remote_path_map
            local_path, remote_path = await self.remote_path_map(meta, client_name)

            logger.debug(f"[bold green]Adding to {client_name} ({torrent_client})")

            try:
                if torrent_client.lower() == "rtorrent":
                    self.rtorrent(meta.path, torrent_path, torrent, meta, local_path, remote_path, client, tracker)
                elif torrent_client == "qbit":
                    await self.qbittorrent(meta.path, torrent, local_path, remote_path, client, meta.is_disc, meta.filelist, meta, tracker, cross)
                elif torrent_client.lower() == "deluge":
                    self.deluge(meta.path, torrent_path, torrent, local_path, remote_path, client)
                elif torrent_client.lower() == "transmission":
                    self.transmission(meta.path, torrent, local_path, remote_path, client, meta)
                elif torrent_client.lower() == "watch":
                    shutil.copy(torrent_path, client["watch_folder"])
            except Exception as e:
                logger.info(f"[bold red]Failed to add torrent to {client_name}: {e}")
        return

    async def inject_delay(self, meta: Meta, tracker: str, client_name: str) -> None:
        """
        Applies an optional delay before injecting a torrent into the client.

        The delay can be configured either per tracker or globally in the default settings.
        When both are defined, the tracker-specific value takes precedence over the client setting.

        This mechanism exists to handle cases where a tracker requires a short amount
        of time to register the uploaded torrent hash. Injecting the torrent too early
        may cause connectivity issues, such as failing to discover peers even though
        they are already available.

        By waiting before injection, this function helps ensure proper tracker
        synchronization and more reliable peer discovery.
        """
        tracker_cfg = self.config.get("TRACKERS", {}).get(tracker, {})
        has_tracker_delay = isinstance(tracker_cfg, dict) and "inject_delay" in tracker_cfg
        inject_delay = tracker_cfg.get("inject_delay") if has_tracker_delay else self.config["DEFAULT"].get("inject_delay", 0)
        if inject_delay is None or (isinstance(inject_delay, str) and not inject_delay.strip()):
            return

        try:
            inject_delay = int(inject_delay)
        except ValueError, TypeError:
            if has_tracker_delay:
                logger.info(f"{tracker}: [bold red]CONFIG ERROR: 'inject_delay' must be an integer")
            else:
                logger.info("[bold red]CONFIG ERROR: 'inject_delay' must be an integer")
            inject_delay = 0

        if inject_delay < 0:
            logger.info("[bold red]CONFIG ERROR: 'inject_delay' must be >= 0")
            inject_delay = 0
        if inject_delay > 0:
            if meta.debug or inject_delay > 5:
                if has_tracker_delay:
                    logger.info(f"{tracker}: [cyan]Waiting {inject_delay} seconds before adding to client '{client_name}'[/cyan]")
                else:
                    logger.info(f"[cyan]Waiting {inject_delay} seconds before adding to client '{client_name}'[/cyan]")
            await asyncio.sleep(inject_delay)

    async def find_existing_torrent(self, meta: Meta) -> str | None:
        """Find a reusable torrent matching the prepared metadata."""
        if meta.get("skip_auto_torrent", False):
            return None

        # Determine piece size preferences
        piece_limit = bool(self.config["DEFAULT"].get("prefer_max_16_torrent", False))
        prefer_small_pieces = piece_limit
        best_match = None  # Track the best match for fallback if prefer_small_pieces is enabled
        video_only_fallback: tuple[str, str] | None = None

        default_torrent_client = cast(str, self.config["DEFAULT"]["default_torrent_client"])

        clients_to_search: list[str]
        meta_client = meta.client
        if isinstance(meta_client, str) and meta_client != "none":
            clients_to_search = [meta_client]
            logger.debug(f"[cyan]DEBUG: Using client from meta: {clients_to_search}[/cyan]")
        else:
            searching_list = self.config["DEFAULT"].get("searching_client_list", [])
            searching_list_values = cast(list[Any], searching_list) if isinstance(searching_list, list) else []

            if searching_list_values:
                clients_to_search = [str(c) for c in searching_list_values if str(c) and str(c) != "none"]
                logger.debug(f"[cyan]DEBUG: Using searching_client_list from config: {clients_to_search}[/cyan]")
            else:
                clients_to_search = []

            if not clients_to_search:
                if default_torrent_client and default_torrent_client != "none":
                    clients_to_search = [default_torrent_client]
                    logger.debug(f"[cyan]DEBUG: Falling back to default_torrent_client: {default_torrent_client}[/cyan]")
                else:
                    logger.info("[yellow]No clients configured for searching...[/yellow]")
                    return None

        for client_name in clients_to_search:
            if client_name not in self.config["TORRENT_CLIENTS"]:
                logger.info(f"[yellow]Client '{client_name}' not found in TORRENT_CLIENTS config, skipping...")
                continue

            result = await self._search_single_client_for_torrent(meta, client_name, prefer_small_pieces, piece_limit, best_match)

            if result:
                candidate_path = result.get("torrent_path") if isinstance(result, dict) else result
                if meta.subtitle_files and isinstance(candidate_path, str) and not self._torrent_includes_all_local_subtitles(candidate_path, meta):
                    # Only a subtitle-free torrent can safely provide BASE.torrent.
                    # A partially subtitle-bearing torrent would produce an invalid
                    # BASE_SUBS.torrent and omit selected local subtitles.
                    if self._torrent_has_no_subtitles(candidate_path) and (
                        video_only_fallback is None or not prefer_small_pieces or self._is_preferred_piece_size_candidate(candidate_path, video_only_fallback[0], piece_limit)
                    ):
                        video_only_fallback = (candidate_path, client_name)
                    continue
                if isinstance(result, dict):
                    # Got a valid torrent but not ideal piece size
                    best_match = {**result, "client_name": client_name}
                    # If prefer_small_pieces is False, we don't care about piece size optimization
                    # so stop searching after finding the first valid torrent
                    if not prefer_small_pieces:
                        logger.info(f"[green]Found valid torrent in client '{client_name}', stopping search[/green]")
                        torrent_path = best_match.get("torrent_path")
                        meta.reuse_torrent_client = client_name
                        return torrent_path if isinstance(torrent_path, str) else None
                else:
                    # Got a path - this means we found a torrent with ideal piece size
                    logger.debug(f"[green]Found valid torrent with preferred piece size in client '{client_name}', stopping search[/green]")
                    meta.reuse_torrent_client = client_name
                    return result

        if prefer_small_pieces and best_match:
            logger.info(f"[yellow]Using best match torrent with hash: [bold yellow]{best_match['torrenthash']}[/bold yellow]")
            torrent_path = best_match.get("torrent_path")
            meta.reuse_torrent_client = cast(str | None, best_match.get("client_name"))
            return torrent_path if isinstance(torrent_path, str) else None

        if video_only_fallback:
            logger.info("[yellow]No matching torrent with all local subtitles found; using the video-only fallback.[/yellow]")
            meta.reuse_torrent_client = video_only_fallback[1]
            return video_only_fallback[0]

        logger.info("[bold yellow]No Valid .torrent found")
        return None

    async def _search_single_client_for_torrent(
        self, meta: Meta, client_name: str, prefer_small_pieces: bool, piece_limit: bool, best_match: dict[str, Any] | None
    ) -> dict[str, Any] | str | None:
        """Search a single client for an existing torrent by hash or via API search (qbit only)."""

        client = self.config["TORRENT_CLIENTS"][client_name]
        torrent_client = client.get("torrent_client", "").lower()
        torrent_storage_dir = client.get("torrent_storage_dir")
        qbt_client: qbittorrentapi.Client | None = None
        proxy_url: str | None = None

        # Iterate through pre-specified hashes
        for hash_key in ["torrenthash", "ext_torrenthash"]:
            hash_value = meta.get(hash_key)
            if hash_value:
                hash_value_str = str(hash_value)
                # If no torrent_storage_dir defined, use saved torrent from qbit
                extracted_torrent_dir = Path(meta.base_dir) / "tmp" / meta.uuid

                if torrent_storage_dir:
                    torrent_path = Path(torrent_storage_dir) / f"{hash_value_str}.torrent"
                else:
                    if torrent_client != "qbit":
                        return None

                    try:
                        proxy_url = client.get("qui_proxy_url")
                        if proxy_url:
                            qbt_proxy_url = proxy_url.rstrip("/")
                            async with httpx.AsyncClient() as session:
                                try:
                                    response = await session.post(f"{qbt_proxy_url}/api/v2/torrents/export", data={"hash": hash_value_str})
                                    if response.status_code == 200:
                                        torrent_file_content = response.content
                                    else:
                                        logger.error(f"[red]Failed to export torrent via proxy: {response.status_code}")
                                        continue
                                except Exception as e:
                                    logger.error(f"[red]Error exporting torrent via proxy: {e}")
                                    continue
                        else:
                            potential_qbt_client = await self.init_qbittorrent_client(client)
                            if not potential_qbt_client:
                                continue
                            qbt_client = potential_qbt_client

                            qbt_client_local: qbittorrentapi.Client = qbt_client

                            try:
                                torrent_file_content = await self.retry_qbt_operation(
                                    lambda qbt_client_local=qbt_client_local, hash_value_str=hash_value_str: asyncio.to_thread(
                                        qbt_client_local.torrents_export, torrent_hash=hash_value_str
                                    ),
                                    f"Export torrent {hash_value_str}",
                                )
                            except TimeoutError, qbittorrentapi.APIError:
                                continue
                        if not torrent_file_content:
                            logger.info(f"[bold red]qBittorrent returned an empty response for hash {hash_value_str}")
                            continue  # Skip to the next hash

                        # Save the .torrent file
                        Path(extracted_torrent_dir).mkdir(parents=True, exist_ok=True)
                        torrent_path = Path(extracted_torrent_dir) / f"{hash_value_str}.torrent"

                        await asyncio.to_thread(Path(torrent_path).write_bytes, torrent_file_content)

                        logger.info(f"[green]Successfully saved .torrent file: {torrent_path}")

                    except qbittorrentapi.APIError as e:
                        logger.info(f"[bold red]Failed to fetch .torrent from qBittorrent for hash {hash_value_str}: {e}")
                        continue

                # Validate the .torrent file
                valid, resolved_path = await self.is_valid_torrent(meta, torrent_path, hash_value_str, torrent_client, client)

                if valid:
                    return resolved_path

        # Search the client if no pre-specified hash matches
        if torrent_client == "qbit" and client.get("enable_search"):
            qbt_session: httpx.AsyncClient | None = None
            try:
                proxy_url = client.get("qui_proxy_url")

                if proxy_url:
                    ssl_context = self.create_ssl_context_for_client(client)
                    qbt_session = httpx.AsyncClient(timeout=10.0, verify=ssl_context)
                else:
                    qbt_client = await self.init_qbittorrent_client(client)

                found_hash = await self.search_qbit_for_torrent(meta, client, qbt_client, qbt_session, proxy_url)

                # Clean up session if we created one
                if qbt_session:
                    await qbt_session.aclose()

            except KeyboardInterrupt:
                logger.info("[bold red]Search cancelled by user")
                found_hash = None
                if qbt_session:
                    await qbt_session.aclose()
            except TimeoutError:
                if qbt_session:
                    await qbt_session.aclose()
                raise
            except Exception as e:
                logger.info(f"[bold red]Error searching qBittorrent: {e}")
                found_hash = None
                if qbt_session:
                    await qbt_session.aclose()
            if found_hash:
                extracted_torrent_dir = Path(meta.base_dir) / "tmp" / meta.uuid

                if torrent_storage_dir:
                    found_torrent_path = Path(torrent_storage_dir) / f"{found_hash}.torrent"
                else:
                    found_torrent_path = Path(extracted_torrent_dir) / f"{found_hash}.torrent"

                    if not Path(found_torrent_path).exists():
                        logger.info(f"[yellow]Exporting .torrent file from qBittorrent for hash: {found_hash}[/yellow]")

                        torrent_file_content: bytes | None = None

                        try:
                            proxy_url = client.get("qui_proxy_url")
                            if proxy_url:
                                qbt_proxy_url = proxy_url.rstrip("/")
                                async with httpx.AsyncClient() as session:
                                    try:
                                        response = await session.post(f"{qbt_proxy_url}/api/v2/torrents/export", data={"hash": found_hash})
                                        if response.status_code == 200:
                                            torrent_file_content = response.content
                                        else:
                                            logger.error(f"[red]Failed to export torrent via proxy: {response.status_code}")
                                            found_hash = None
                                    except Exception as e:
                                        logger.error(f"[red]Error exporting torrent via proxy: {e}")
                                        found_hash = None
                            else:
                                # Reuse or create qbt_client if needed
                                if qbt_client is None:
                                    qbt_client = await self.init_qbittorrent_client(client)
                                    if qbt_client is None:
                                        logger.info("[bold red]Failed to connect to qBittorrent for export.")
                                        found_hash = None

                                if found_hash and qbt_client is not None:  # Only proceed if we still have a hash
                                    active_qbt = qbt_client
                                    try:
                                        torrent_file_content = await self.retry_qbt_operation(
                                            lambda qbt_client=active_qbt, found_hash=found_hash: asyncio.to_thread(qbt_client.torrents_export, torrent_hash=found_hash),
                                            f"Export torrent {found_hash}",
                                        )
                                    except (TimeoutError, qbittorrentapi.APIError) as e:
                                        logger.error(f"[red]Error exporting torrent: {e}")

                            if found_hash:  # Only proceed if export succeeded
                                if not torrent_file_content:
                                    found_hash = None
                                else:
                                    Path(extracted_torrent_dir).mkdir(parents=True, exist_ok=True)
                                    await asyncio.to_thread(Path(found_torrent_path).write_bytes, torrent_file_content)
                                    logger.info(f"[green]Successfully saved .torrent file: {found_torrent_path}")
                        except Exception as e:
                            logger.error(f"[bold red]Unexpected error fetching .torrent from qBittorrent: {e}")
                            logger.info("[cyan]DEBUG: Skipping found_hash due to unexpected error[/cyan]")
                            found_hash = None
                    else:
                        logger.debug(f"[cyan]DEBUG: .torrent file already exists at {found_torrent_path}[/cyan]")

                # Only validate if we still have a hash (export succeeded or file already existed)
                resolved_path = ""
                if found_hash:
                    valid, resolved_path = await self.is_valid_torrent(meta, found_torrent_path, found_hash, torrent_client, client)
                else:
                    valid = False
                    logger.info("[cyan]DEBUG: Skipping validation because found_hash is None[/cyan]")

                if valid:
                    torrent = Torrent.read(resolved_path)
                    piece_size = torrent.piece_size
                    piece_in_mib = piece_size / 1024 / 1024

                    if not prefer_small_pieces:
                        logger.debug(f"[green]Found a valid torrent from client search with piece size {piece_in_mib} MiB: [bold yellow]{found_hash}")
                        return resolved_path

                    # Track best match for small pieces
                    if piece_size < 16777216 and piece_limit:  # 16 MiB
                        logger.info(f"[green]Found a valid torrent with piece size under 16 MiB from client search: [bold yellow]{found_hash}")
                        return resolved_path

                    if best_match is None or piece_size < best_match["piece_size"]:
                        best_match = {"torrenthash": found_hash, "torrent_path": resolved_path, "piece_size": piece_size}
                        logger.info(f"[yellow]Storing valid torrent from client search as best match: [bold yellow]{found_hash}")

        return best_match

    async def is_valid_torrent(self, meta: Meta, torrent_path: str, torrenthash: str, torrent_client: str, _client: dict[str, Any]) -> tuple[bool, str]:
        """Validate a candidate torrent against files, layout, and piece limits."""
        torrent_path = str(torrent_path)
        valid = False
        wrong_file = False
        filelist = cast(list[str], meta.filelist)
        meta_path = meta.path
        if meta_path is None:
            return False, torrent_path
        meta_uuid = meta.uuid

        # Normalize the torrent hash based on the client
        if torrent_client in ("qbit", "deluge"):
            torrenthash = torrenthash.lower().strip()
            torrent_path = torrent_path.replace(torrenthash.upper(), torrenthash)
        elif torrent_client == "rtorrent":
            torrenthash = torrenthash.upper().strip()
            torrent_path = torrent_path.replace(torrenthash.upper(), torrenthash)

        if meta.debug:
            logger.debug(f"Torrent path after normalization: {torrent_path}")

        # Check if torrent file exists
        if Path(torrent_path).exists():
            try:
                torrent = Torrent.read(torrent_path)
            except Exception as e:
                logger.info(f"[bold red]Error reading torrent file: {e}")
                return valid, torrent_path

            # Reuse if disc and basename matches or --keep-folder was specified
            if (meta.is_disc and meta.is_disc != "") or (meta.keep_folder and meta.isdir):
                torrent_name = torrent.metainfo["info"]["name"]
                if meta_uuid != torrent_name and meta.debug:
                    logger.info("Modified file structure, skipping hash")
                    valid = False
                torrent_filepath = os.path.commonpath(torrent.files)
                if Path(meta_path).name in torrent_filepath:
                    valid = True
                logger.debug(f"Torrent is valid based on disc/basename or keep-folder: {valid}")

            # Otherwise we match either only videos (no subtitles) OR videos + subtitles (if subtitles are present)
            else:
                subtitle_files = meta.subtitle_files
                candidates = [filelist]
                if subtitle_files:
                    candidates.append(filelist + subtitle_files)

                for cand in candidates:
                    # If one file, check for folder
                    if len(torrent.files) == len(cand) == 1:
                        if Path(torrent.files[0]).name == Path(cand[0]).name:
                            if str(torrent.files[0]) == Path(torrent.files[0]).name:
                                valid = True
                                break
                            wrong_file = True
                        logger.debug(f"Single file match status: valid={valid}, wrong_file={wrong_file}")

                    # Check complete relative layouts, not only filenames. Matching
                    # basenames alone can reuse a torrent from a different folder
                    # structure when releases have repeated filenames.
                    elif len(torrent.files) == len(cand):

                        def relative_layout(paths: list[str]) -> list[str]:
                            """Normalize relative file layout for structural comparison."""
                            root = Path(os.path.commonpath(paths))
                            return sorted(str(Path(path).relative_to(root)).replace("\\", "/") for path in paths)

                        torrent_layout = relative_layout([str(file) for file in torrent.files])
                        candidate_layout = relative_layout([str(file) for file in cand])

                        logger.debug(f"Torrent layout: {torrent_layout}")
                        logger.debug(f"Candidate layout: {candidate_layout}")

                        if torrent_layout == candidate_layout:
                            valid = True
                            break
                        logger.debug(f"Multiple file match status: valid={valid}")

        else:
            logger.info(f"[bold yellow]{torrent_path} was not found")

        # Additional checks if the torrent is valid so far
        if valid:
            if Path(torrent_path).exists():
                try:
                    reuse_torrent = Torrent.read(torrent_path)
                    piece_size = reuse_torrent.piece_size
                    piece_in_mib = piece_size / 1024 / 1024
                    torrent_storage_dir_valid = torrent_path
                    torrent_file_size_kib = round(Path(torrent_storage_dir_valid).stat().st_size / 1024, 2)
                    logger.debug(
                        f"Checking piece size, count and size: pieces={reuse_torrent.pieces}, piece_size={piece_in_mib} MiB, .torrent size={torrent_file_size_kib} KiB"
                    )

                    # Piece size and count validations
                    max_piece_size = meta.max_piece_size
                    if reuse_torrent.pieces >= 5000 and reuse_torrent.piece_size < 4294304 and (max_piece_size is None or max_piece_size >= 4):
                        logger.debug("[bold red]Torrent needs to have less than 5000 pieces with a 4 MiB piece size")
                        valid = False
                    elif (
                        reuse_torrent.pieces >= 8000 and reuse_torrent.piece_size < 8488608 and (max_piece_size is None or max_piece_size >= 8) and not meta.prefer_small_pieces
                    ):
                        logger.debug("[bold red]Torrent needs to have less than 8000 pieces with a 8 MiB piece size")
                        valid = False
                    elif "max_piece_size" not in meta and reuse_torrent.pieces >= 12000:
                        logger.debug("[bold red]Torrent needs to have less than 12000 pieces to be valid")
                        valid = False
                    elif reuse_torrent.piece_size < 32768:
                        logger.debug("[bold red]Piece size too small to reuse")
                        valid = False
                    elif "max_piece_size" not in meta and torrent_file_size_kib > 250:
                        logger.debug("[bold red]Torrent file size exceeds 250 KiB")
                        valid = False
                    elif wrong_file:
                        logger.debug("[bold red]Provided .torrent has files that were not expected")
                        valid = False
                    else:
                        logger.debug(f"[bold green]REUSING .torrent with infohash: [bold yellow]{torrenthash}")
                except Exception as e:
                    logger.info(f"[bold red]Error checking reuse torrent: {e}")
                    valid = False

            if meta.debug:
                logger.debug(f"Final validity after piece checks: valid={valid}")
        else:
            if meta.debug:
                logger.debug("[bold yellow]Unwanted Files/Folders Identified")

        return valid, torrent_path

    @staticmethod
    def _torrent_includes_all_local_subtitles(torrent_path: str, meta: Meta) -> bool:
        """Whether a validated torrent includes every subtitle selected locally."""
        if not meta.subtitle_files:
            return True
        try:
            torrent = Torrent.read(torrent_path)
        except Exception:
            return False

        torrent_names = {Path(str(path)).name.casefold() for path in torrent.files}
        subtitle_names = {Path(str(path)).name.casefold() for path in meta.subtitle_files}
        return subtitle_names.issubset(torrent_names)

    @staticmethod
    def _torrent_has_no_subtitles(torrent_path: str) -> bool:
        """Whether a torrent contains no external subtitle files."""
        try:
            torrent = Torrent.read(torrent_path)
        except Exception:
            return False
        return not any(Path(str(path)).suffix.casefold() in SUBTITLE_EXTENSIONS for path in torrent.files)

    @staticmethod
    def _is_preferred_piece_size_candidate(candidate_path: str, current_path: str, piece_limit: bool) -> bool:
        """Whether a candidate outranks the current fallback by configured piece preference."""
        try:
            candidate_piece_size = Torrent.read(candidate_path).piece_size
            current_piece_size = Torrent.read(current_path).piece_size
        except Exception:
            return False

        if piece_limit:
            limit = 16 * 1024 * 1024
            candidate_within_limit = candidate_piece_size <= limit
            current_within_limit = current_piece_size <= limit
            return candidate_within_limit and (not current_within_limit or candidate_piece_size < current_piece_size)
        return False

    async def remote_path_map(self, meta: Meta, torrent_client_name: str | dict[str, Any] | None = None) -> tuple[str, str]:
        """Return the local and remote roots matching the torrent metadata path."""
        if isinstance(torrent_client_name, dict):
            client_config: dict[str, Any] = torrent_client_name
        elif isinstance(torrent_client_name, str) and torrent_client_name:
            try:
                client_config = cast(dict[str, Any], self.config["TORRENT_CLIENTS"][torrent_client_name])
            except KeyError as exc:
                raise KeyError(f"Torrent client '{torrent_client_name}' not found in TORRENT_CLIENTS") from exc
        else:
            raise ValueError("torrent_client_name must be a client name or client config dict")

        local_paths = coerce_str_list(client_config.get("local_path", ["/LocalPath"]))
        remote_paths = coerce_str_list(client_config.get("remote_path", ["/RemotePath"]))
        if not local_paths:
            local_paths = ["/LocalPath"]
        if not remote_paths:
            remote_paths = ["/RemotePath"]

        list_local_path = local_paths[0]
        list_remote_path = remote_paths[0]
        meta_path = str(meta.path)

        for i, local_path_value in enumerate(local_paths):
            if is_path_under(meta_path, local_path_value):
                list_local_path = local_path_value
                list_remote_path = remote_paths[i] if i < len(remote_paths) else remote_paths[0]
                break

        local_path = os.path.normpath(list_local_path)
        remote_path = os.path.normpath(list_remote_path)
        if local_path.endswith(os.sep):
            remote_path = remote_path + os.sep

        return local_path, remote_path

    async def get_ptp_from_hash(self, meta: Meta, pathed: bool = False, client_name: str | None = None) -> Meta:
        """Fetch PTP metadata through the configured torrent client when available."""
        default_config = self.config.get("DEFAULT", {})
        clients_config = self.config.get("TORRENT_CLIENTS", {})
        default_torrent_client = client_name or (default_config.get("default_torrent_client") if isinstance(default_config, dict) else None)
        if not isinstance(default_torrent_client, str) or not default_torrent_client:
            logger.debug("[yellow]Skipping torrent metadata lookup: no default torrent client configured.[/yellow]")
            return meta

        client = clients_config.get(default_torrent_client) if isinstance(clients_config, dict) else None
        if not isinstance(client, dict):
            logger.debug(f"[yellow]Skipping torrent metadata lookup: client '{default_torrent_client}' is not configured.[/yellow]")
            return meta

        torrent_client = client.get("torrent_client")
        if torrent_client == "rtorrent":
            await self.get_ptp_from_hash_rtorrent(meta, pathed, client)
            return meta
        if torrent_client == "qbit":
            return await self.get_ptp_from_hash_qbit(meta, client, pathed)
        return meta
