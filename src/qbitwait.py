# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import asyncio
import os
import traceback
from collections import deque
from typing import Any, cast

import httpx
import qbittorrentapi

from src.console import console, logger
from src.meta import Meta


class Wait:

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.proxy_url: str | None = None
        self.qbt_proxy_url: str | None = None
        self.qbt_session: httpx.AsyncClient | None = None
        self.qbt_client: qbittorrentapi.Client | None = None
        self.qbt_client = self._connect_qbittorrent()

    def _connect_qbittorrent(self) -> qbittorrentapi.Client | None:
        config_map = self.config
        default_section = cast(dict[str, Any], config_map.get('DEFAULT', {}))
        clients_section = cast(dict[str, Any], config_map.get('TORRENT_CLIENTS', {}))

        default_torrent_client = default_section.get('default_torrent_client', '')
        if not isinstance(default_torrent_client, str) or not default_torrent_client:
            raise ValueError("DEFAULT.default_torrent_client is not configured")

        client_obj = clients_section.get(default_torrent_client)
        if not isinstance(client_obj, dict):
            raise ValueError(f"No torrent client configuration for '{default_torrent_client}'")
        client = cast(dict[str, Any], client_obj)

        proxy_value = client.get('qui_proxy_url')
        self.proxy_url = proxy_value if isinstance(proxy_value, str) and proxy_value else None
        self.qbt_session = None
        self.qbt_client = None

        if self.proxy_url:
            # Use qui proxy URL format
            self.qbt_proxy_url = self.proxy_url.rstrip('/')
            return None  # No traditional client needed for proxy
        else:
            # Use traditional qbittorrent API client
            if "qbit_api_key" in client and client["qbit_api_key"]:
                required_keys = ["qbit_url", "qbit_port", "qbit_api_key"]
            else:
                required_keys = ["qbit_url", "qbit_port", "qbit_user", "qbit_pass"]

            missing_keys = [key for key in required_keys if key not in client]
            if missing_keys:
                raise ValueError(f"Missing required qBittorrent config keys: {', '.join(missing_keys)}")

            verify_cert_value = client.get('VERIFY_WEBUI_CERTIFICATE', True)
            verify_cert = verify_cert_value.strip().lower() in {'1', 'true', 'yes'} if isinstance(verify_cert_value, str) else bool(verify_cert_value)

            host = str(client.get('qbit_url', '')).strip()
            if not host:
                raise ValueError("qbit_url is not configured")
            port_value = client.get('qbit_port')
            if isinstance(port_value, (int, str)):
                port: int | str | None = port_value
            elif port_value is None:
                port = None
            else:
                port = str(port_value)

            if "qbit_api_key" in client and client["qbit_api_key"]:
                api_key_value = client.get("qbit_api_key")
                api_key = str(api_key_value) if api_key_value is not None else None
                qbt_client = qbittorrentapi.Client(host=host, port=port, api_key=api_key, VERIFY_WEBUI_CERTIFICATE=verify_cert)
                try:
                    qbt_client.app_version()
                    return qbt_client
                except Exception as e:
                    raise RuntimeError(f"qBittorrent API Key verification failed: {e}") from e
            else:
                username_value = client.get("qbit_user")
                password_value = client.get("qbit_pass")
                username = str(username_value) if username_value is not None else None
                password = str(password_value) if password_value is not None else None

                qbt_client = qbittorrentapi.Client(host=host, port=port, username=username, password=password, VERIFY_WEBUI_CERTIFICATE=verify_cert)

                try:
                    qbt_client.auth_log_in()
                    return qbt_client
                except qbittorrentapi.LoginFailed as e:
                    raise RuntimeError(f"qBittorrent login failed: {e}") from e

    async def wait_for_completion(self, infohash: str, check_interval: int = 3) -> None:
        if not self.proxy_url and not self.qbt_client:
            raise Exception("[ERROR] qBittorrent is not configured.")

        logger.info(f"Waiting for torrent {infohash} to complete...", extra={"markup": False})

        if self.proxy_url:
            self.qbt_session = httpx.AsyncClient()

        try:
            while True:
                if self.proxy_url:
                    if self.qbt_session is None:
                        raise RuntimeError("qbt_session is not initialized")
                    response = await self.qbt_session.get(
                        f"{self.qbt_proxy_url}/api/v2/torrents/info" if hasattr(self, "self") else f"{self.qbt_proxy_url}/api/v2/torrents/info", params={"hashes": infohash}
                    )
                    if response.status_code == 200:
                        torrents_data = cast(list[dict[str, Any]], response.json())
                        target_torrent = torrents_data[0] if torrents_data else None
                    else:
                        logger.info(f"[ERROR] Failed to get torrent info via proxy: {response.status_code}", extra={"markup": False})
                        break
                else:
                    if self.qbt_client is None:
                        raise RuntimeError("qbt_client is not initialized")
                    torrents = self.qbt_client.torrents_info(hashes=infohash)
                    target_torrent = next((t for t in torrents if t.hash == infohash), None)

                if target_torrent:
                    if self.proxy_url:
                        target_dict = cast(dict[str, Any], target_torrent)
                        state_value = target_dict.get('state')
                    else:
                        state_value = getattr(target_torrent, 'state', None)
                    state_str = str(state_value) if state_value is not None else 'unknown'
                    logger.info(f"[DEBUG] Torrent {infohash} state: {state_str}", extra={"markup": False})

                    if state_str in {'pausedUP', 'seeding', 'completed', 'stalledUP', 'uploading'}:
                        logger.info(f"[INFO] Torrent {infohash} has completed!", extra={"markup": False})
                        return
                else:
                    logger.info(f"[ERROR] Torrent with hash {infohash} not found!", extra={"markup": False})
                    break

                await asyncio.sleep(check_interval)
        finally:
            if self.qbt_session:
                await self.qbt_session.aclose()

    async def wait_for_bandwidth(self, threshold_kb: int, wait_time: int) -> bool:
        if not self.proxy_url and not self.qbt_client:
            return False

        if threshold_kb <= 0 or wait_time <= 0:
            logger.info("[yellow]Bandwidth control enabled but threshold or time is 0. Skipping bandwidth check.[/yellow]")
            return False

        threshold_bytes = threshold_kb * 1024
        check_interval = 5
        max_samples = max(1, wait_time // check_interval)
        speeds: deque[int] = deque(maxlen=max_samples)

        if self.proxy_url:
            self.qbt_session = httpx.AsyncClient()

        try:
            while True:
                up_speed = 0
                if self.proxy_url:
                    if self.qbt_session is None:
                        raise RuntimeError("qbt_session is not initialized")
                    response = await self.qbt_session.get(f"{self.qbt_proxy_url}/api/v2/transfer/info")
                    if response.status_code == 200:
                        data = response.json()
                        up_speed = int(data.get("up_info_speed", 0))
                    else:
                        logger.info(f"[ERROR] Failed to get transfer info via proxy: {response.status_code}", extra={"markup": False})
                        logger.info("[yellow]Retrying in 10 seconds...[/yellow]", extra={"markup": False})
                        await asyncio.sleep(10)
                        continue
                else:
                    if self.qbt_client is None:
                        raise RuntimeError("qbt_client is not initialized")
                    data = self.qbt_client.transfer_info()
                    up_speed_raw = data.get("up_info_speed", 0) if hasattr(data, "get") else getattr(data, "up_info_speed", 0)
                    up_speed = int(cast(int | str | float, up_speed_raw))

                speeds.append(up_speed)
                avg_speed = sum(speeds) / len(speeds)
                current_samples = len(speeds)
                avg_speed_kbs = avg_speed / 1024
                total_seconds = current_samples * check_interval
                avg_speed_color = "green" if avg_speed <= threshold_bytes else "red"
                if current_samples >= max_samples and avg_speed <= threshold_bytes:
                    console.print(
                        f"[yellow]Average speed of [{avg_speed_color}]{avg_speed_kbs:.0f}/{threshold_kb:.0f}[/{avg_speed_color}] KB/s in the last {total_seconds} seconds. [/yellow]"
                    )
                    break
                else:
                    console.print(
                        f"[yellow]Average speed of [{avg_speed_color}]{avg_speed_kbs:.0f}[/{avg_speed_color}]/[green]{threshold_kb:.0f}[/green] KB/s in the last {total_seconds} seconds. [/yellow]",
                        end="\r",
                    )

                await asyncio.sleep(check_interval)
            return True
        except Exception as e:
            logger.error(f"\n[red]Error checking bandwidth: {e}[/red]")
            return False
        finally:
            if self.proxy_url and self.qbt_session:
                await self.qbt_session.aclose()
                self.qbt_session = None

    async def select_and_recheck_best_torrent(self, meta: Meta, path: str, check_interval: int = 5) -> bool:
        if not self.proxy_url and not self.qbt_client:
            logger.info("[red]qBittorrent is not configured.[/red]")
            return False

        torrent_comments = meta.torrent_comments
        if not isinstance(torrent_comments, list):
            logger.info("[red]No torrent comments found in metadata[/red]")
            return False
        torrent_comments_list: list[dict[str, Any]] = [
            cast(dict[str, Any], tc)
            for tc in torrent_comments
            if isinstance(tc, dict)
        ]

        target_path = path
        if not target_path:
            logger.info("[red]No target path available for matching torrents[/red]")
            return False

        matching_torrents: list[dict[str, Any]] = []
        hash_used = meta.hash_used
        if isinstance(hash_used, str) and hash_used:
            torrent_hash = hash_used.lower()
        else:
            meta_name = meta.name
            meta_name_lower = meta_name.lower() if isinstance(meta_name, str) else None
            for tc in torrent_comments_list:
                content_path = str(tc.get('content_path', '') or '')

                if not tc.get('has_working_tracker', False):
                    continue
                tc_name = tc.get('name')
                matches_path = bool(content_path) and os.path.normpath(content_path).lower() == os.path.normpath(target_path).lower()
                matches_name = isinstance(tc_name, str) and meta_name_lower is not None and tc_name.lower() == meta_name_lower
                if matches_path or matches_name:
                    matching_torrents.append(tc)

            if not matching_torrents:
                logger.info("[yellow]No matching torrents with working trackers found in qBittorrent[/yellow]")
                return True

            matching_torrents.sort(key=lambda x: int(x.get('seeders', 0) or 0), reverse=True)
            best_torrent = matching_torrents[0]

            best_hash = best_torrent.get('hash')
            if not isinstance(best_hash, str):
                logger.info("[red]Best torrent is missing a valid hash[/red]")
                return False
            torrent_hash = best_hash.lower()
            logger.info(
                f"[green]Selected best torrent: {best_torrent.get('name')} with {best_torrent.get('seeders', 0)} seeders[/green]"
                f"[yellow] Tracker: {str(best_torrent.get('trackers', 'unknown'))[:20]}[/yellow]"
            )

        if self.proxy_url:
            self.qbt_session = httpx.AsyncClient()

        try:
            # Recheck the torrent
            if self.proxy_url:
                if self.qbt_session is None:
                    logger.info("[bold red]qbt_session is not initialized")
                    return False
                if self.qbt_proxy_url is None:
                    logger.info("[bold red]Proxy URL is not configured correctly")
                    return False
                response = await self.qbt_session.post(f"{self.qbt_proxy_url}/api/v2/torrents/recheck", data={"hashes": torrent_hash})
                if response.status_code != 200:
                    logger.info(f"[bold red]Failed to recheck torrent via proxy: {response.status_code}")
                    return False
            else:
                if self.qbt_client is None:
                    logger.info("[bold red]qbt_client is not initialized")
                    return False
                self.qbt_client.torrents_recheck(torrent_hashes=torrent_hash)

            await asyncio.sleep(3)
        except Exception as e:
            logger.info(f"[bold red]Failed to recheck torrent: {e}")
            return False

        try:
            while True:
                if self.proxy_url:
                    if self.qbt_session is None:
                        logger.info("[bold red]qbt_session is not initialized")
                        return False
                    if self.qbt_proxy_url is None:
                        logger.info("[bold red]Proxy URL is not configured correctly")
                        return False
                    response = await self.qbt_session.get(f"{self.qbt_proxy_url}/api/v2/torrents/info", params={"hashes": torrent_hash})
                    if response.status_code == 200:
                        torrents_data = cast(list[dict[str, Any]], response.json())
                        if torrents_data:
                            torrent = torrents_data[0]
                            state = torrent.get("state")
                            progress = torrent.get("progress", 0)
                            state_str = str(state) if state is not None else "unknown"
                            try:
                                progress_float = float(progress or 0)
                            except TypeError, ValueError:
                                progress_float = 0.0
                        else:
                            raise Exception("No torrents found in response")
                    else:
                        logger.info(f"[bold red]Failed to get torrent info via proxy: {response.status_code}")
                        return False
                else:
                    if self.qbt_client is None:
                        logger.info("[bold red]qbt_client is not initialized")
                        return False
                    torrent_list_raw = cast(Any, self.qbt_client.torrents_info(hashes=torrent_hash))
                    if torrent_list_raw is None:
                        raise Exception("qBittorrent returned no torrent info")
                    if isinstance(torrent_list_raw, list):
                        torrent_candidates = torrent_list_raw
                    elif isinstance(torrent_list_raw, tuple):
                        torrent_candidates = list(torrent_list_raw)
                    else:
                        torrent_candidates = [torrent_list_raw]
                    if not torrent_candidates:
                        raise Exception("No torrents found in TorrentInfoList")
                    torrent = torrent_candidates[0]
                    state = getattr(torrent, 'state', None)
                    progress = getattr(torrent, 'progress', 0)
                    state_str = str(state) if state is not None else 'unknown'
                    progress_float = float(progress or 0)

                logger.info(f"\r[INFO] Torrent is at {progress_float * 100:.2f}% progress of {state_str}...", extra={"markup": False})

                if state_str not in ('checkingUP', 'checkingDL', 'checkingResumeData'):
                    logger.info("", extra={"markup": False})
                    break

                await asyncio.sleep(check_interval)

            # Get final torrent info
            if self.proxy_url:
                if self.qbt_session is None:
                    logger.info("[bold red]qbt_session is not initialized")
                    return False
                if self.qbt_proxy_url is None:
                    logger.info("[bold red]Proxy URL is not configured correctly")
                    return False
                response = await self.qbt_session.get(f"{self.qbt_proxy_url}/api/v2/torrents/info", params={"hashes": torrent_hash})
                if response.status_code == 200:
                    torrents_data = cast(list[dict[str, Any]], response.json())
                    if torrents_data:
                        torrent = torrents_data[0]
                        final_state = torrent.get("state")
                        final_progress = torrent.get("progress", 0)
                    else:
                        raise Exception("No torrents found in response")
                else:
                    logger.info(f"[bold red]Failed to get final torrent info via proxy: {response.status_code}")
                    return False
            else:
                if self.qbt_client is None:
                    logger.info("[bold red]qbt_client is not initialized")
                    return False
                torrent_list_raw = cast(Any, self.qbt_client.torrents_info(hashes=torrent_hash))
                if torrent_list_raw is None:
                    raise Exception("qBittorrent returned no torrent info")
                if isinstance(torrent_list_raw, list):
                    torrent_candidates = torrent_list_raw
                elif isinstance(torrent_list_raw, tuple):
                    torrent_candidates = list(torrent_list_raw)
                else:
                    torrent_candidates = [torrent_list_raw]
                if not torrent_candidates:
                    raise Exception("No torrents found in TorrentInfoList")
                torrent = torrent_candidates[0]
                final_state = getattr(torrent, 'state', 'unknown')
                final_progress = float(getattr(torrent, 'progress', 0) or 0)

            logger.info(f"[green]Recheck completed. State: {final_state}, Progress: {final_progress*100:.2f}%[/green]")
            meta.we_rechecked_torrent = True

            if final_state not in {'pausedUP', 'seeding', 'completed', 'stalledUP', 'uploading'}:
                logger.info("[yellow]Torrent needs to download missing data. Waiting for completion...[/yellow]")
                await self.wait_for_completion(torrent_hash, check_interval)

            return True

        except Exception as e:
            logger.info(f"[bold red]Error while waiting for recheck: {e}")
            traceback.print_exc()
            return False
        finally:
            if self.qbt_session:
                await self.qbt_session.aclose()
