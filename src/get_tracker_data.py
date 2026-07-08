# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import asyncio
import json
import os
import sys
import time
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Any, cast
from urllib.parse import urlparse

import cli_ui
import httpx
import requests

from src.btnid import BtnIdManager
from src.cleanup import cleanup_manager
from src.console import logger
from src.meta import Meta
from src.trackermeta import TrackerMetaManager
from src.trackersetup import tracker_class_map


class TrackerDataManager:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        trackers_cfg = cast(Mapping[str, Mapping[str, Any]], config.get('TRACKERS', {}))
        if not isinstance(trackers_cfg, dict):
            raise ValueError("'TRACKERS' config section must be a dict")
        default_cfg = cast(Mapping[str, Any], config.get('DEFAULT', {}))
        if not isinstance(default_cfg, dict):
            raise ValueError("'DEFAULT' config section must be a dict")
        self.trackers_config = trackers_cfg
        self.default_config = default_cfg
        self.tracker_meta_manager = TrackerMetaManager(config)

    def get_tracker_config(self, tracker_name: str) -> Mapping[str, Any]:
        return self.trackers_config.get(tracker_name, MappingProxyType({}))

    async def get_tracker_timestamps(self, base_dir: str | None = None) -> dict[str, float]:
        """Get tracker timestamps from the log file"""
        timestamp_file = os.path.join(f"{base_dir}", "data", "banned", "tracker_timestamps.json")
        try:
            if os.path.exists(timestamp_file):
                timestamps_text = await asyncio.to_thread(Path(timestamp_file).read_text)
                return cast(dict[str, float], json.loads(timestamps_text))
            return {}
        except Exception as e:
            logger.warning(f"[yellow]Warning: Could not load tracker timestamps: {e}[/yellow]")
            return {}

    async def save_tracker_timestamp(self, tracker_name: str, base_dir: str | None = None) -> None:
        """Save timestamp for when tracker was processed"""
        timestamp_file = os.path.join(f"{base_dir}", "data", "banned", "tracker_timestamps.json")
        try:
            os.makedirs(f"{base_dir}/data/banned", exist_ok=True)

            timestamps = await self.get_tracker_timestamps(base_dir)
            timestamps[tracker_name] = time.time()

            timestamps_text = json.dumps(timestamps, indent=2)
            await asyncio.to_thread(Path(timestamp_file).write_text, timestamps_text)

            logger.debug(f"[yellow]Saved timestamp for {tracker_name} - will be available again in 60 seconds[/yellow]")

        except Exception as e:
            logger.error(f"[red]Error saving tracker timestamp: {e}[/red]")

    async def get_available_trackers(
        self,
        specific_trackers: list[str],
        base_dir: str | None = None,
        debug: bool = False,
    ) -> tuple[list[str], list[tuple[str, float]]]:
        """Get trackers that are available (60+ seconds since last processed)"""
        _ = debug
        timestamps = await self.get_tracker_timestamps(base_dir)
        current_time = time.time()
        available: list[str] = []
        waiting: list[tuple[str, float]] = []

        for tracker in specific_trackers:
            cooldown_seconds = 60 if tracker == "PTP" else 15
            last_processed = timestamps.get(tracker, 0)
            time_since_last = current_time - last_processed

            if time_since_last >= cooldown_seconds:
                available.append(tracker)
            else:
                wait_time = cooldown_seconds - time_since_last
                waiting.append((tracker, wait_time))

        return available, waiting

    async def get_tracker_data(
        self,
        _video: Any,
        meta: Meta,
        search_term: str | None = None,
        search_file_folder: str | None = None,
        cat: str | None = None,
        skip_tracker_descriptions: bool = False,
    ) -> Meta:
        found_match = False
        base_dir = meta.base_dir
        search_term_value = search_term or ""
        search_file_folder_value = search_file_folder or ""
        if search_term:
            # Check if a specific tracker is already set in meta
            tracker_keys = {
                # preference some unit3d based trackers first
                # since they can return tmdb/imdb/tvdb ids
                'aither': 'AITHER',
                'blu': 'BLU',
                'lst': 'LST',
                'ulcx': 'ULCX',
                'oe': 'OE',
                'huno': 'HUNO',
                'ant': 'ANT',
                'btn': 'BTN',
                'bhd': 'BHD',
                'hdb': 'HDB',
                'sp': 'SP',
                'rf': 'RF',
                'otw': 'OTW',
                'yus': 'YUS',
                'dp': 'DP',
                'ptp': 'PTP',
            }

            specific_tracker: list[str] = [tracker_keys[key] for key in tracker_keys if meta.get(key) is not None]

            # Filter out trackers that don't have valid config or api_key/announce_url
            if specific_tracker:
                valid_trackers: list[str] = []
                for tracker in specific_tracker:
                    if "BTN" in tracker:
                        valid_trackers.append(tracker)
                        continue
                    tracker_config = self.get_tracker_config(tracker)
                    api_key = tracker_config.get('api_key', '')
                    announce_url = tracker_config.get('announce_url', '')

                    if not tracker_config:
                        logger.debug(f"[yellow]Tracker {tracker} not found in config, skipping[/yellow]")
                        continue

                    has_api_key = isinstance(api_key, str) and api_key.strip() != ""
                    has_announce_url = isinstance(announce_url, str) and announce_url.strip() != ""

                    if not has_api_key and not has_announce_url:
                        logger.debug(f"[yellow]Tracker {tracker} has no api_key or announce_url set, skipping[/yellow]")
                        continue

                    valid_trackers.append(tracker)

                specific_tracker = valid_trackers

            logger.debug(f"[blue]Specific trackers to check: {specific_tracker}[/blue]")

            if specific_tracker:
                if meta.is_disc and "ANT" in specific_tracker:
                    specific_tracker.remove("ANT")
                if meta.category == "MOVIE" and "BTN" in specific_tracker:
                    specific_tracker.remove("BTN")

                meta_trackers_raw = meta.trackers
                meta_trackers: list[str]
                if isinstance(meta_trackers_raw, str):
                    meta_trackers = [t.strip().upper() for t in meta_trackers_raw.split(',')]
                elif isinstance(meta_trackers_raw, list):
                    meta_trackers_list = meta_trackers_raw
                    meta_trackers = [t.upper() for t in meta_trackers_list]
                else:
                    meta_trackers = []

                # for just searching, remove any specific trackers already in meta.trackers
                # since that tracker was found in client, and remove it from meta.trackers
                for tracker in list(specific_tracker):
                    if tracker in meta_trackers and meta.site_check:
                        specific_tracker.remove(tracker)
                        meta_trackers.remove(tracker)

                # Update meta.trackers preserving list format
                if meta_trackers:
                    meta.trackers = meta_trackers
                else:
                    meta.trackers = []

                async def process_tracker(tracker_name: str, meta: Meta, skip_tracker_descriptions: bool) -> Meta:
                    nonlocal found_match
                    tracker_factory = tracker_class_map.get(tracker_name)
                    if tracker_factory is None:
                        logger.info(f"[red]Tracker class for {tracker_name} not found.[/red]")
                        return meta

                    tracker_instance = tracker_factory(config=self.config)
                    try:
                        updated_meta, match = await self.tracker_meta_manager.update_metadata_from_tracker(
                            tracker_name,
                            tracker_instance,
                            meta,
                            search_term_value,
                            search_file_folder_value,
                            skip_tracker_descriptions,
                        )
                        if match:
                            found_match = True
                            logger.debug(f"[green]Match found on tracker: {tracker_name}[/green]")
                            meta.matched_tracker = tracker_name
                        await self.save_tracker_timestamp(tracker_name, base_dir=base_dir)
                        return updated_meta
                    except httpx.ConnectError:
                        await self.save_tracker_timestamp(tracker_name, base_dir=base_dir)
                        logger.info(f"{tracker_name} tracker request failed due to SSL/Connection error.", extra={"markup": False})
                    except requests.exceptions.ConnectionError as conn_err:
                        await self.save_tracker_timestamp(tracker_name, base_dir=base_dir)
                        logger.info(f"{tracker_name} tracker request failed due to connection error: {conn_err}", extra={"markup": False})
                    return meta

                while not found_match and specific_tracker:
                    meta_trackers_raw = meta.trackers
                    if isinstance(meta_trackers_raw, str):
                        meta_trackers = [t.strip().upper() for t in meta_trackers_raw.split(',')]
                    elif isinstance(meta_trackers_raw, list):
                        meta_trackers_list = cast(list[Any], meta_trackers_raw)
                        meta_trackers = [str(t).upper() for t in meta_trackers_list]
                    else:
                        meta_trackers = []

                    available_trackers, waiting_trackers = await self.get_available_trackers(specific_tracker, base_dir, debug=meta.debug)

                    if available_trackers:
                        logger.debug(f"[green]Available trackers: {', '.join(available_trackers)}[/green]")
                        tracker_to_process = available_trackers[0]
                    else:
                        if waiting_trackers:
                            waiting_trackers.sort(key=lambda x: x[1])
                            tracker_to_process, wait_time = waiting_trackers[0]

                            cooldown_info = ", ".join(
                                f"{tracker} ({wait_time:.1f}s)" for tracker, wait_time in waiting_trackers
                            )
                            for remaining in range(int(wait_time), -1, -1):
                                msg = (
                                    f"[yellow]All specific trackers in cooldown. "
                                    f"Waiting {remaining:.1f} seconds for {tracker_to_process}. "
                                    f"Cooldowns: {cooldown_info}[/yellow]"
                                )
                                logger.info(msg)
                                await asyncio.sleep(1)
                            logger.info("")

                        else:
                            logger.debug("[red]No specific trackers available[/red]")
                            break

                    # Process the selected tracker
                    if tracker_to_process == "BTN":
                        btn_id_value = meta.btn
                        btn_id = str(btn_id_value) if btn_id_value is not None else ""
                        btn_api = self.default_config.get('btn_api')
                        if isinstance(btn_api, str) and len(btn_api) > 25:
                            imdb, tvdb = await BtnIdManager.get_btn_torrents(btn_api, btn_id)
                            if imdb != 0 or tvdb != 0:
                                if not meta.unattended or (meta.unattended and meta.unattended_confirm):
                                    logger.info(f"[green]Found BTN IDs: IMDb={imdb}, TVDb={tvdb}[/green]")
                                    try:
                                        if cli_ui.ask_yes_no("Do you want to use these ids?", default=True):
                                            if imdb != 0:
                                                meta.imdb_id = imdb
                                            if tvdb != 0:
                                                meta.tvdb_id = tvdb
                                            found_match = True
                                            meta.matched_tracker = "BTN"
                                    except EOFError:
                                        logger.info("\n[red]Exiting on user request (Ctrl+C)[/red]")
                                        await cleanup_manager.cleanup()
                                        cleanup_manager.reset_terminal()
                                        sys.exit(1)
                                else:
                                    if imdb != 0:
                                        meta.imdb_id = imdb
                                    if tvdb != 0:
                                        meta.tvdb_id = tvdb
                                    found_match = True
                                    meta.matched_tracker = "BTN"
                            await self.save_tracker_timestamp("BTN", base_dir=base_dir)
                    elif tracker_to_process == "ANT":
                        imdb_tmdb_list = await tracker_class_map['ANT'](config=self.config).get_data_from_files(meta)
                        if imdb_tmdb_list:
                            logger.info(f"[green]Found ANT IDs: {imdb_tmdb_list}[/green]")
                            if not meta.unattended or (meta.unattended and meta.unattended_confirm):
                                try:
                                    if cli_ui.ask_yes_no("Do you want to use these ids?", default=True):
                                        for d in imdb_tmdb_list:
                                            meta.update(d)
                                        found_match = True
                                        meta.matched_tracker = "ANT"
                                except EOFError:
                                    logger.info("\n[red]Exiting on user request (Ctrl+C)[/red]")
                                    await cleanup_manager.cleanup()
                                    cleanup_manager.reset_terminal()
                                    sys.exit(1)
                            else:
                                for d in imdb_tmdb_list:
                                    meta.update(d)
                                found_match = True
                                meta.matched_tracker = "ANT"
                        await self.save_tracker_timestamp("ANT", base_dir=base_dir)
                    else:
                        meta = await process_tracker(tracker_to_process, meta, skip_tracker_descriptions)

                    if not found_match:
                        if tracker_to_process in specific_tracker:
                            specific_tracker.remove(tracker_to_process)
                        remaining_available, remaining_waiting = await self.get_available_trackers(specific_tracker, base_dir, debug=meta.debug)

                        if remaining_available or remaining_waiting:
                            logger.debug(f"[yellow]No match found with {tracker_to_process}. Checking remaining trackers...[/yellow]")
                        else:
                            logger.debug(f"[yellow]No match found with {tracker_to_process}. No more trackers available to check.[/yellow]")
                            break

                if found_match:
                    logger.debug(f"[green]Successfully found match using tracker: {(meta.matched_tracker if meta.matched_tracker is not None else 'Unknown')}[/green]")
                else:
                    logger.debug("[yellow]No matches found on any available specific trackers.[/yellow]")

            else:
                # Process all trackers with API = true if no specific tracker is set in meta
                from src.trackersetup import api_trackers
                other_api = sorted(api_trackers - {"BHD"})
                tracker_order = ["PTP", "HDB", "BHD"] + other_api

                if cat == "TV" or meta.category == "TV":
                    logger.debug("[yellow]Detected TV content, skipping PTP tracker check")
                    tracker_order = [tracker for tracker in tracker_order if tracker != "PTP"]

                async def process_tracker(tracker_name: str, meta: Meta, skip_tracker_descriptions: bool) -> Meta:
                    nonlocal found_match
                    tracker_factory = tracker_class_map.get(tracker_name)
                    if tracker_factory is None:
                        logger.info(f"[red]Tracker class for {tracker_name} not found.[/red]")
                        return meta

                    tracker_instance = tracker_factory(config=self.config)
                    try:
                        updated_meta, match = await self.tracker_meta_manager.update_metadata_from_tracker(
                            tracker_name,
                            tracker_instance,
                            meta,
                            search_term_value,
                            search_file_folder_value,
                            skip_tracker_descriptions,
                        )
                        if match:
                            found_match = True
                            logger.debug(f"[green]Match found on tracker: {tracker_name}[/green]")
                            meta.matched_tracker = tracker_name
                        return updated_meta
                    except httpx.ConnectError:
                        logger.info(f"{tracker_name} tracker request failed due to SSL/Connection error.", extra={"markup": False})
                    except requests.exceptions.ConnectionError as conn_err:
                        logger.info(f"{tracker_name} tracker request failed due to connection error: {conn_err}", extra={"markup": False})
                    return meta

                for tracker_name in tracker_order:
                    if not found_match:  # Stop checking once a match is found
                        tracker_config = self.get_tracker_config(tracker_name)
                        use_search = tracker_config.get('use_for_search')
                        if use_search is None:
                            use_search = tracker_config.get('useAPI', 'false')
                        if str(use_search).lower() == "true":
                            meta = await process_tracker(tracker_name, meta, skip_tracker_descriptions)

                if not found_match:
                    meta.no_tracker_match = True
                    logger.debug("[yellow]No matches found on any trackers.[/yellow]")

        else:
            logger.warning("[yellow]Warning: No valid search term available, skipping tracker updates.[/yellow]")

        return meta

    async def ping_unit3d(self, meta: Meta) -> None:
        import re

        from src.trackers.COMMON import COMMON

        common = COMMON(self.config)

        # Prioritize trackers in this order
        from src.trackersetup import api_trackers
        prioritized = ["BLU", "AITHER", "ULCX", "LST", "OE"]
        tracker_order = prioritized + sorted(api_trackers - set(prioritized) - {"BHD"})

        # Check if we have stored torrent comments
        if meta.torrent_comments:
            # Try to extract tracker IDs from stored comments
            for tracker_name in tracker_order:
                # Skip if we already have region and distributor
                if meta.region and meta.distributor:
                    logger.debug(f"[green]Both region ({meta.region}) and distributor ({meta.distributor}) found - no need to check more trackers[/green]")
                    break

                tracker_id: str = ""
                tracker_key = tracker_name.lower()
                # Check each stored comment for matching tracker URL
                for comment_data in meta.torrent_comments:
                    is_tracker_comment = False
                    comment = str(comment_data.get('comment', ''))
                    # Dynamically build tracker hosts
                    tracker_hosts = {}
                    for name in api_trackers:
                        hostname = ""
                        if name in tracker_class_map:
                            try:
                                tracker_instance = tracker_class_map[name](self.config)
                                base_url = getattr(tracker_instance, 'base_url', '')
                                if base_url:
                                    hostname = urlparse(base_url).hostname or ""
                            except Exception:
                                pass
                        if not hostname:
                            announce_url = self.config.get('TRACKERS', {}).get(name, {}).get('announce_url', '')
                            if announce_url:
                                hostname = urlparse(announce_url).hostname or ""
                        if hostname:
                            tracker_hosts[name] = hostname.lower()

                    # Fallbacks for safety
                    for k, v in {
                        "BLU": "blutopia.cc",
                        "AITHER": "aither.cc",
                        "LST": "lst.gg",
                        "OE": "onlyencodes.cc",
                        "ULCX": "upload.cx",
                    }.items():
                        if k not in tracker_hosts:
                            tracker_hosts[k] = v

                    expected_host = tracker_hosts.get(tracker_name)
                    if expected_host and expected_host in comment:
                        candidate_urls: list[str] = re.findall(r"https?://[^\s\"'<>]+", comment)
                        for url in candidate_urls:
                            parsed = urlparse(url)
                            if parsed.scheme in ("http", "https") and parsed.hostname == expected_host:
                                is_tracker_comment = True
                                break

                    if is_tracker_comment:
                        match = re.search(r'/(\d+)$', comment)
                        if match:
                            tracker_id = match.group(1)
                            meta[tracker_key] = tracker_id
                            break

                # If we found a tracker ID, try to get region/distributor data
                if tracker_id:
                    missing_info: list[str] = []
                    if not meta.region:
                        missing_info.append("region")
                    if not meta.distributor:
                        missing_info.append("distributor")

                    logger.debug(f"[cyan]Using {tracker_name} ID {tracker_id} to get {'/'.join(missing_info)} info[/cyan]")

                    tracker_instance = tracker_class_map[tracker_name](config=self.config)

                    # Store initial state to detect changes
                    had_region = bool(meta.region)
                    had_distributor = bool(meta.distributor)
                    await common.unit3d_region_distributor(meta, tracker_name, tracker_instance.torrent_url, str(tracker_id))

                    if meta.region and not had_region and meta.debug:
                        logger.info(f"[green]Found region '{meta.region}' from {tracker_name}[/green]")

                    if meta.distributor and not had_distributor and meta.debug:
                        logger.info(f"[green]Found distributor '{meta.distributor}' from {tracker_name}[/green]")

