# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import asyncio
import contextlib
import json
import os
import shutil
import time
import uuid
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Any, cast
from urllib.parse import urlparse

import cli_ui
import click
import httpx
import requests

from src.btnid import BtnIdManager
from src.console import logger, prompt_in_thread
from src.meta import Meta
from src.metadata_cache import is_cache_miss, tracker_metadata_cache_for
from src.tracker_descriptions import description_fingerprint
from src.trackermeta import TrackerMetaManager
from src.trackersetup import tracker_class_map

_TRACKER_ID_FIELDS = {
    "AITHER": "aither",
    "ANTHELION": "ant",
    "BEYONDHD": "bhd",
    "BLUTOPIA": "blu",
    "BTN": "btn",
    "DARKPEERS": "dp",
    "HAWKEUNO": "huno",
    "HDBITS": "hdb",
    "LASTDIGITALUNDERGROUND": "ldu",
    "LST": "lst",
    "OLDTOONSWORLD": "otw",
    "ONLYENCODES": "oe",
    "PASSTHEPOPCORN": "ptp",
    "REELFLIX": "rf",
    "SEEDPOOL": "sp",
    "ULCX": "ulcx",
    "YUSCENE": "yus",
}


class TrackerDataManager:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        trackers_cfg = cast(Mapping[str, Mapping[str, Any]], config.get("TRACKERS", {}))
        if not isinstance(trackers_cfg, dict):
            raise ValueError("'TRACKERS' config section must be a dict")
        default_cfg = cast(Mapping[str, Any], config.get("DEFAULT", {}))
        if not isinstance(default_cfg, dict):
            raise ValueError("'DEFAULT' config section must be a dict")
        self.trackers_config = trackers_cfg
        self.default_config = default_cfg
        self.tracker_meta_manager = TrackerMetaManager(config)

    def get_tracker_config(self, tracker_name: str) -> Mapping[str, Any]:
        return self.trackers_config.get(tracker_name, MappingProxyType({}))

    async def update_metadata_from_explicit_tracker(
        self,
        tracker_name: str,
        tracker_instance: Any,
        meta: Meta,
        search_term: str,
        search_file_folder: str,
        skip_tracker_descriptions: bool,
        *,
        use_cache: bool = True,
    ) -> tuple[Meta, bool]:
        """Reuse a cached tracker response only when the user supplied a torrent ID."""
        tracker_field = _TRACKER_ID_FIELDS.get(tracker_name, tracker_name.lower())
        tracker_id = str(meta.get(tracker_field, "") or meta.get(tracker_name.lower(), "") or "").strip()
        if not tracker_id:
            return await self.tracker_meta_manager.update_metadata_from_tracker(
                tracker_name, tracker_instance, meta, search_term, search_file_folder, skip_tracker_descriptions
            )

        cache = tracker_metadata_cache_for(meta.base_dir, self.config)
        cache_key = json.dumps(
            {
                "id": tracker_id,
                "is_disc": bool(meta.is_disc),
                "keep_images": bool(meta.keep_images),
                "skip_descriptions": skip_tracker_descriptions,
            },
            sort_keys=True,
        )
        cached = await cache.get(tracker_name.lower(), "torrent", cache_key) if use_cache else None
        if use_cache and not is_cache_miss(cached) and isinstance(cached, dict):
            cached_metadata = cached.get("metadata")
            if isinstance(cached_metadata, dict):
                meta.update(cached_metadata)
            match = bool(cached.get("match", False))
            logger.debug(f"[cyan]{tracker_name}: using cached metadata for torrent ID {tracker_id}.[/cyan]")
            return meta, match

        before = meta.to_dict()
        updated_meta, match = await self.tracker_meta_manager.update_metadata_from_tracker(
            tracker_name, tracker_instance, meta, search_term, search_file_folder, skip_tracker_descriptions, torrent_id=tracker_id
        )
        after = updated_meta.to_dict()
        metadata_patch = {key: value for key, value in after.items() if before.get(key) != value}
        if use_cache:
            await cache.set(
                tracker_name.lower(),
                "torrent",
                cache_key,
                {"match": match, "metadata": metadata_patch},
                negative=not match,
            )
        return updated_meta, match

    def _search_enabled(self, tracker_name: str) -> bool:
        tracker_config = self.get_tracker_config(tracker_name)
        use_search = tracker_config.get("use_for_search")
        if use_search is None:
            use_search = tracker_config.get("useAPI", "false")
        return str(use_search).lower() == "true"

    @staticmethod
    def _candidate_score(original: Meta, candidate: Meta) -> int:
        score = 0
        for field in ("tmdb_id", "imdb_id", "tvdb_id", "mal_id"):
            if candidate.get(field) and candidate.get(field) != original.get(field):
                score += 20
        provenance = candidate.description_provenance
        if provenance:
            score += int(provenance.get("score", 0)) + 10
        if candidate.description and candidate.description != original.description:
            score += 10
        score += min(len(candidate.image_list), 10)
        return score

    async def _collect_explicit_tracker_candidate(
        self,
        tracker_name: str,
        meta: Meta,
        search_term: str,
        search_file_folder: str,
        skip_tracker_descriptions: bool,
    ) -> tuple[str, Meta, int] | None:
        """Fetch one candidate without allowing it to mutate the live release."""
        candidate = meta.copy()
        candidate.uuid = f"{meta.uuid}-candidate-{tracker_name.lower()}-{uuid.uuid4().hex}"
        candidate.unattended = True
        candidate.unattended_confirm = False
        candidate.persist_description = False
        candidate_dir = Path(meta.base_dir) / "tmp" / candidate.uuid
        await asyncio.to_thread(candidate_dir.mkdir, mode=0o700, parents=True, exist_ok=True)
        try:
            if tracker_name == "BTN":
                btn_id = str(candidate.btn or "")
                btn_api = self.default_config.get("btn_api")
                if not isinstance(btn_api, str) or len(btn_api) <= 25:
                    return None
                imdb, tvdb = await BtnIdManager.get_btn_torrents(btn_api, btn_id)
                if not (imdb or tvdb):
                    return None
                candidate.imdb_id = imdb or candidate.imdb_id
                candidate.tvdb_id = tvdb or candidate.tvdb_id
                return tracker_name, candidate, self._candidate_score(meta, candidate)

            if tracker_name == "ANTHELION":
                data = await tracker_class_map[tracker_name](config=self.config).get_data_from_files(candidate)
                if not data:
                    return None
                for values in data:
                    candidate.update(values)
                return tracker_name, candidate, self._candidate_score(meta, candidate)

            factory = tracker_class_map.get(tracker_name)
            if factory is None:
                return None
            candidate, match = await self.update_metadata_from_explicit_tracker(
                tracker_name,
                factory(config=self.config),
                candidate,
                search_term,
                search_file_folder,
                skip_tracker_descriptions,
                use_cache=True,
            )
            if not match:
                return None
            return tracker_name, candidate, self._candidate_score(meta, candidate)
        except (httpx.ConnectError, requests.exceptions.ConnectionError) as error:
            logger.info(f"{tracker_name} tracker request failed due to connection error: {error}", extra={"markup": False})
            return None
        except Exception as error:
            logger.info(f"{tracker_name} tracker metadata candidate failed: {error}", extra={"markup": False})
            return None
        finally:
            await asyncio.to_thread(shutil.rmtree, candidate_dir, True)

    async def _choose_explicit_tracker_candidate(
        self,
        meta: Meta,
        candidates: list[tuple[str, Meta, int]],
    ) -> tuple[str, Meta] | None:
        if not candidates:
            return None
        ranked = sorted(candidates, key=lambda item: (-item[2], item[0]))
        if len(ranked) > 1 and not meta.unattended:
            logger.info("[cyan]Tracker metadata candidates:[/cyan]")
            for index, (tracker_name, candidate, score) in enumerate(ranked, start=1):
                logger.info(f"  {index}. {tracker_name}: score {score}, {candidate.name or candidate.filename}")
            choice = await prompt_in_thread(cli_ui.ask_string, f"Choose a tracker candidate [1-{len(ranked)}] (Enter for best): ")
            if choice and choice.strip().isdigit():
                selected = int(choice.strip()) - 1
                if 0 <= selected < len(ranked):
                    return ranked[selected][0], ranked[selected][1]
            elif choice and choice.strip():
                logger.warning("[yellow]Invalid candidate selection; using the best score.[/yellow]")
        return ranked[0][0], ranked[0][1]

    async def _apply_explicit_tracker_candidate(self, meta: Meta, tracker_name: str, candidate: Meta) -> None:
        """Apply the selected isolated result without leaking worker-only state."""
        excluded = {"uuid", "unattended", "unattended_confirm", "base_dir", "persist_description"}
        for key, value in candidate.to_dict().items():
            if key not in excluded and meta.get(key) != value:
                meta[key] = value
        meta.matched_tracker = tracker_name

    async def _review_explicit_tracker_description(self, meta: Meta, tracker_name: str, candidate: Meta) -> None:
        """Allow an interactive run to edit the selected tracker description."""
        if meta.unattended or not candidate.description:
            return
        if os.environ.get("UA_WEBUI_ACTIVE"):
            from src.description_review import load_review, save_review

            temp_dir = Path(meta.base_dir) / "tmp" / meta.uuid
            review = load_review(temp_dir)
            if not isinstance(review.get("content"), str):
                try:
                    version = int(review.get("version", 0) or 0) + 1
                except TypeError, ValueError:
                    version = 1
                await asyncio.to_thread(save_review, temp_dir, candidate.description, version)
            return
        logger.info(f"[cyan]Selected description from {tracker_name}:[/cyan]\n{candidate.description[:1000]}", extra={"markup": False})
        choice = await prompt_in_thread(cli_ui.ask_string, "\nEnter 'e' to edit, 'd' to discard the description, or press Enter to keep it: ")
        choice = (choice or "").strip().lower()
        if choice == "e":
            edited = await asyncio.to_thread(click.edit, candidate.description)
            if edited is not None:
                candidate.description = str(edited).strip()
                candidate.saved_description = bool(candidate.description)
                candidate.description_fingerprint = description_fingerprint(candidate, tracker_name)
                candidate.description_provenance = {**candidate.description_provenance, "edited": True}
        elif choice == "d":
            candidate.description = ""
            candidate.saved_description = False
            candidate.description_provenance = {**candidate.description_provenance, "discarded": True}

    async def get_tracker_timestamps(self, base_dir: str | None = None) -> dict[str, float]:
        """Get tracker timestamps from the log file"""
        timestamp_file = Path(f"{base_dir}") / "data" / "banned" / "tracker_timestamps.json"
        try:
            if Path(timestamp_file).exists():
                timestamps_text = await asyncio.to_thread(Path(timestamp_file).read_text)
                return cast(dict[str, float], json.loads(timestamps_text))
            return {}
        except Exception as e:
            logger.warning(f"[yellow]Warning: Could not load tracker timestamps: {e}[/yellow]")
            return {}

    async def save_tracker_timestamp(self, tracker_name: str, base_dir: str | None = None) -> None:
        """Save timestamp for when tracker was processed"""
        timestamp_file = Path(f"{base_dir}") / "data" / "banned" / "tracker_timestamps.json"
        try:
            Path(f"{base_dir}/data/banned").mkdir(parents=True, exist_ok=True)

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
            cooldown_seconds = 60 if tracker == "PASSTHEPOPCORN" else 15
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
            specific_tracker = sorted(tracker_name for tracker_name, tracker_key in _TRACKER_ID_FIELDS.items() if meta.get(tracker_key) is not None)

            # Filter out trackers that don't have valid config or api_key/announce_url
            if specific_tracker:
                valid_trackers: list[str] = []
                for tracker in specific_tracker:
                    if not self._search_enabled(tracker):
                        logger.debug(f"[yellow]Tracker {tracker} is not enabled for metadata search, skipping[/yellow]")
                        continue

                    valid_trackers.append(tracker)

                specific_tracker = valid_trackers

            logger.debug(f"[blue]Specific trackers to check: {specific_tracker}[/blue]")

            if specific_tracker:
                if meta.is_disc and "ANTHELION" in specific_tracker:
                    specific_tracker.remove("ANTHELION")
                if meta.category == "MOVIE" and "BTN" in specific_tracker:
                    specific_tracker.remove("BTN")

                meta_trackers_raw = meta.trackers
                meta_trackers: list[str]
                if isinstance(meta_trackers_raw, str):
                    meta_trackers = [t.strip().upper() for t in meta_trackers_raw.split(",")]
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

                available_trackers, waiting_trackers = await self.get_available_trackers(specific_tracker, base_dir, debug=meta.debug)
                if waiting_trackers and not available_trackers:
                    wait_time = max(wait for _tracker, wait in waiting_trackers)
                    waiting_names = ", ".join(f"{tracker} ({wait:.1f}s)" for tracker, wait in waiting_trackers)
                    logger.info(f"[yellow]Waiting for tracker metadata candidate cooldowns: {waiting_names}[/yellow]")
                    await asyncio.sleep(wait_time)
                    available_trackers, waiting_trackers = await self.get_available_trackers(specific_tracker, base_dir, debug=meta.debug)
                    if waiting_trackers:
                        logger.warning("[yellow]Some tracker metadata candidates remain in cooldown and will not be queried.[/yellow]")

                search_limit = self.default_config.get("tracker_search_concurrency", 4)
                try:
                    semaphore = asyncio.Semaphore(max(1, int(search_limit)))
                except TypeError, ValueError:
                    semaphore = asyncio.Semaphore(4)

                async def collect(tracker_name: str) -> tuple[str, Meta, int] | None:
                    async with semaphore:
                        return await self._collect_explicit_tracker_candidate(
                            tracker_name,
                            meta,
                            search_term_value,
                            search_file_folder_value,
                            skip_tracker_descriptions,
                        )

                results = await asyncio.gather(*(collect(tracker_name) for tracker_name in available_trackers))
                candidates = [result for result in results if result is not None]
                for tracker_name in available_trackers:
                    await self.save_tracker_timestamp(tracker_name, base_dir=base_dir)

                selected_candidate = await self._choose_explicit_tracker_candidate(meta, candidates)
                if selected_candidate:
                    tracker_name, candidate_meta = selected_candidate
                    await self._review_explicit_tracker_description(meta, tracker_name, candidate_meta)
                    await self._apply_explicit_tracker_candidate(meta, tracker_name, candidate_meta)
                    found_match = True
                    logger.debug(f"[green]Selected tracker metadata candidate: {tracker_name}[/green]")

                if found_match:
                    logger.debug(f"[green]Successfully found match using tracker: {(meta.matched_tracker if meta.matched_tracker is not None else 'Unknown')}[/green]")
                else:
                    logger.debug("[yellow]No matches found on any available specific trackers.[/yellow]")

            else:
                # Process all trackers with API = true if no specific tracker is set in meta
                from src.trackersetup import api_trackers

                other_api = sorted(api_trackers - {"BEYONDHD"})
                tracker_order = ["PASSTHEPOPCORN", "HDBITS", "BEYONDHD", *other_api]

                if cat == "TV" or meta.category == "TV":
                    logger.debug("[yellow]Detected TV content, skipping PASSTHEPOPCORN tracker check")
                    tracker_order = [tracker for tracker in tracker_order if tracker != "PASSTHEPOPCORN"]

                async def process_tracker(tracker_name: str, meta: Meta, skip_tracker_descriptions: bool) -> Meta:
                    nonlocal found_match
                    tracker_factory = tracker_class_map.get(tracker_name)
                    if tracker_factory is None:
                        logger.info(f"[red]Tracker class for {tracker_name} not found.[/red]")
                        return meta

                    tracker_instance = tracker_factory(config=self.config)
                    try:
                        updated_meta, match = await self.update_metadata_from_explicit_tracker(
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
                    if not found_match and self._search_enabled(tracker_name):  # Stop checking once a match is found
                        meta = await process_tracker(tracker_name, meta, skip_tracker_descriptions)

                if not found_match:
                    meta.no_tracker_match = True
                    logger.debug("[yellow]No matches found on any trackers.[/yellow]")

        else:
            logger.warning("[yellow]Warning: No valid search term available, skipping tracker updates.[/yellow]")

        return meta

    async def ping_unit3d(self, meta: Meta) -> None:
        import re

        from src.trackers.common import Common

        common = Common(self.config)

        # Prioritize trackers in this order
        from src.trackersetup import api_trackers

        prioritized = ["BLUTOPIA", "AITHER", "ULCX", "LST", "ONLYENCODES"]
        tracker_order = prioritized + sorted(api_trackers - set(prioritized) - {"BEYONDHD"})

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
                    comment = str(comment_data.get("comment", ""))
                    # Dynamically build tracker hosts
                    tracker_hosts = {}
                    for name in api_trackers:
                        hostname = ""
                        if name in tracker_class_map:
                            with contextlib.suppress(Exception):
                                tracker_instance = tracker_class_map[name](self.config)
                                base_url = getattr(tracker_instance, "base_url", "")
                                if base_url:
                                    hostname = urlparse(base_url).hostname or ""
                        if not hostname:
                            announce_url = self.config.get("TRACKERS", {}).get(name, {}).get("announce_url", "")
                            if announce_url:
                                hostname = urlparse(announce_url).hostname or ""
                        if hostname:
                            tracker_hosts[name] = hostname.lower()

                    # Fallbacks for safety
                    for k, v in {
                        "BLUTOPIA": "blutopia.cc",
                        "AITHER": "aither.cc",
                        "LST": "lst.gg",
                        "ONLYENCODES": "onlyencodes.cc",
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
                        match = re.search(r"/(\d+)$", comment)
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
                    previous_region = meta.region
                    previous_distributor = meta.distributor
                    cache = tracker_metadata_cache_for(meta.base_dir, self.config)
                    cache_key = json.dumps({"id": tracker_id}, sort_keys=True)
                    cached = await cache.get(tracker_name.lower(), "region_distributor", cache_key)
                    if not is_cache_miss(cached) and isinstance(cached, dict):
                        cached_metadata = cached.get("metadata")
                        if isinstance(cached_metadata, dict):
                            meta.update(cached_metadata)
                        logger.debug(f"[cyan]{tracker_name}: using cached region/distributor data for torrent ID {tracker_id}.[/cyan]")
                    else:
                        # Store initial state to detect changes
                        await common.unit3d_region_distributor(meta, tracker_name, tracker_instance.torrent_url, str(tracker_id))
                        metadata_patch: dict[str, Any] = {}
                        if meta.region != previous_region:
                            metadata_patch["region"] = meta.region
                        if meta.distributor != previous_distributor:
                            metadata_patch["distributor"] = meta.distributor
                        await cache.set(
                            tracker_name.lower(),
                            "region_distributor",
                            cache_key,
                            {"metadata": metadata_patch},
                            negative=not bool(metadata_patch),
                        )

                    if meta.region and not previous_region and meta.debug:
                        logger.info(f"[green]Found region '{meta.region}' from {tracker_name}[/green]")

                    if meta.distributor and not previous_distributor and meta.debug:
                        logger.info(f"[green]Found distributor '{meta.distributor}' from {tracker_name}[/green]")
