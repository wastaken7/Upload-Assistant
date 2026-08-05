# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import asyncio
import json
import re
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlparse

import aiofiles
import cli_ui
import httpx

from data.example_config import config as example_config
from src.cleanup import cleanup_manager
from src.console import logger
from src.meta import Meta
from src.trackers.alpharatio import AlphaRatio
from src.trackers.amigosshare import AmigosShare
from src.trackers.anthelion import Anthelion
from src.trackers.AVISTAZ.avistaz import AvistaZ
from src.trackers.AVISTAZ.cinemaz import CinemaZ
from src.trackers.AVISTAZ.privatehd import PrivateHD
from src.trackers.beyondhd import BEYONDHD
from src.trackers.bithdtv import BitHDTV
from src.trackers.bjshare import BJShare
from src.trackers.brasiltracker import BrasilTracker
from src.trackers.cathoderaytube import CathodeRayTube
from src.trackers.common import Common
from src.trackers.digitalcore import DigitalCore
from src.trackers.filelist import FileList
from src.trackers.funfile import FunFile
from src.trackers.greatposterwall import GreatPosterWall
from src.trackers.hdbits import HDBits
from src.trackers.hdspace import HDSpace
from src.trackers.hdtorrents import HDTorrents
from src.trackers.immortalseed import ImmortalSeed
from src.trackers.iptorrents import IPTorrents
from src.trackers.makingoff import MakingOff
from src.trackers.morethantv import MoreThanTV
from src.trackers.mteam import MTeam
from src.trackers.nebulance import Nebulance
from src.trackers.NEXUSPHP.lajidui import Lajidui
from src.trackers.NEXUSPHP.longpt import LongPT
from src.trackers.NEXUSPHP.ptcafe import PTCafe
from src.trackers.NEXUSPHP.ptfans import PTFans
from src.trackers.NEXUSPHP.ptgtk import PTGTK
from src.trackers.NEXUSPHP.railgunpt import RailgunPT
from src.trackers.orpheus import Orpheus
from src.trackers.passthepopcorn import PassThePopcorn
from src.trackers.pterclub import PTerClub
from src.trackers.ptskit import Ptskit
from src.trackers.retroflix import RetroFlix
from src.trackers.speedapp import SpeedApp
from src.trackers.swarmazon import Swarmazon
from src.trackers.torrenthr import TorrentHR
from src.trackers.torrentleech import TorrentLeech
from src.trackers.totheglory import ToTheGlory
from src.trackers.tvchaosuk import TVChaosUK
from src.trackers.UNIT3D.aither import Aither
from src.trackers.UNIT3D.asiancinema import AsianCinema
from src.trackers.UNIT3D.aura4k import Aura4K
from src.trackers.UNIT3D.blutopia import Blutopia
from src.trackers.UNIT3D.capybarabr import CapybaraBR
from src.trackers.UNIT3D.cinematik import Cinematik
from src.trackers.UNIT3D.darkpeers import DarkPeers
from src.trackers.UNIT3D.emuwarez import Emuwarez
from src.trackers.UNIT3D.hawkeuno import HawkeUno
from src.trackers.UNIT3D.homiehelpdesk import HomieHelpDesk
from src.trackers.UNIT3D.infinityhd import InfinityHD
from src.trackers.UNIT3D.itatorrents import ItaTorrents
from src.trackers.UNIT3D.lastdigitalunderground import LastDigitalUnderground
from src.trackers.UNIT3D.latteam import LatTeam
from src.trackers.UNIT3D.locadora import Locadora
from src.trackers.UNIT3D.lst import LST
from src.trackers.UNIT3D.luminarr import Luminarr
from src.trackers.UNIT3D.midnightscene import MidnightScene
from src.trackers.UNIT3D.nordicquality import NordicQuality
from src.trackers.UNIT3D.oldtoonsworld import OldToonsWorld
from src.trackers.UNIT3D.onlyencodes import OnlyEncodes
from src.trackers.UNIT3D.peergarden import PeerGarden
from src.trackers.UNIT3D.polishtorrent import PolishTorrent
from src.trackers.UNIT3D.portugas import Portugas
from src.trackers.UNIT3D.racing4everyone import Racing4Everyone
from src.trackers.UNIT3D.rastastugan import Rastastugan
from src.trackers.UNIT3D.reelflix import ReelFlix
from src.trackers.UNIT3D.retromoviesclub import RetroMoviesClub
from src.trackers.UNIT3D.samaritano import Samaritano
from src.trackers.UNIT3D.seedpool import Seedpool
from src.trackers.UNIT3D.shareisland import ShareIsland
from src.trackers.UNIT3D.skipthecommercials import SkipTheCommercials
from src.trackers.UNIT3D.theoldschool import TheOldSchool
from src.trackers.UNIT3D.tlzdigital import TheLeachZone
from src.trackers.UNIT3D.torrentdesi import DesiTorrents
from src.trackers.UNIT3D.torrenteros import Torrenteros
from src.trackers.UNIT3D.ulcx import ULCX
from src.trackers.UNIT3D.unwalled import Unwalled
from src.trackers.UNIT3D.utopia import Utopia
from src.trackers.UNIT3D.yuscene import YUSCENE
from src.trackers.UNIT3D.znth import Zenith
from src.trackers.USENET.curupira import Curupira
from src.trackers.USENET.drunkenslug import DrunkenSlug
from src.trackers.USENET.suio import Suio

JsonDict = dict[str, Any]
example_config: dict[str, Any]


class TrackerSetup:
    def __init__(self, config: dict[str, Any]):
        self.config: dict[str, Any] = config

    def _create_tracker_instance(self, tracker: str) -> Any | None:
        tracker_class = tracker_class_map.get(tracker.upper())
        if tracker_class is None:
            return None
        return tracker_class(self.config)

    def filter_unsupported_trackers(self, meta: Meta) -> None:
        category = meta.category
        if not category:
            return

        trackers = meta.trackers
        if not trackers:
            return

        supported_trackers: list[str] = []
        for tracker_name in trackers:
            tracker_class = tracker_class_map.get(tracker_name.upper())
            if not tracker_class:
                supported_trackers.append(tracker_name)
                continue

            tracker_config: dict[str, Any] = self.config["TRACKERS"].get(tracker_name, {})
            example_tracker_config = example_config["TRACKERS"].get(tracker_name, {})

            if isinstance(example_tracker_config, dict) and isinstance(tracker_config, dict):
                if "api_key" in example_tracker_config and not tracker_config.get("api_key"):
                    logger.info(f"{tracker_name}: [bold red]Tracker is missing an API key and will be ignored.[/bold red]")
                    if not meta.debug:
                        continue

                if "announce_url" in example_tracker_config and not tracker_config.get("announce_url"):
                    logger.info(f"{tracker_name}: [bold red]Tracker is missing an announce URL and will be ignored.[/bold red]")
                    if not meta.debug:
                        continue

            supported_cats = getattr(tracker_class, "supported_categories", None)
            if supported_cats is None:
                logger.info(f"{tracker_name}: [bold red]Error: Tracker does not have 'supported_categories' defined. Removing from queue.[/bold red]", extra={"markup": False})
                meta.setdefault("tracker_status", {}).setdefault(tracker_name, {})["upload"] = False
                meta.setdefault("tracker_status", {}).setdefault(tracker_name, {})["skipped"] = True
                continue

            # Case-insensitive comparison
            if category.upper() in [c.upper() for c in supported_cats]:
                supported_trackers.append(tracker_name)
            else:
                logger.info(f"{tracker_name}: [bold red]category '{category}' is not supported. Removing from queue.[/bold red]")
                meta.setdefault("tracker_status", {}).setdefault(tracker_name, {})["upload"] = False
                meta.setdefault("tracker_status", {}).setdefault(tracker_name, {})["skipped"] = True

        meta.trackers = supported_trackers

    def trackers_enabled(self, meta: Meta) -> list[str]:
        trackers_value = meta.trackers if meta.trackers is not None else self.config["TRACKERS"]["default_trackers"]

        if isinstance(trackers_value, str):
            trackers_list = trackers_value.split(",")
        elif isinstance(trackers_value, list):
            trackers_list = [str(s) for s in cast(list[Any], trackers_value)]
        else:
            trackers_list = []

        trackers = [str(s).strip().upper() for s in trackers_list]
        meta.trackers = trackers

        self.filter_unsupported_trackers(meta)

        trackers = meta.trackers

        if meta.manual:
            trackers.insert(0, "MANUAL")

        valid_trackers = [t for t in trackers if t in tracker_class_map or t in ("MANUAL", "USENET")]
        removed_trackers = set(trackers) - set(valid_trackers)

        for tracker in removed_trackers:
            logger.warning(f"Warning: Tracker '{tracker}' is not recognized and will be ignored.", extra={"markup": False})

        return valid_trackers

    async def get_banned_groups(self, meta: Meta, tracker: str) -> str | None:
        file_path = Path(meta.base_dir) / "data" / "banned" / f"{tracker}_banned_groups.json"

        tracker_instance = self._create_tracker_instance(tracker)
        if tracker_instance is None:
            return None
        if tracker.upper() == "LUMINARR":
            # LUMINARR doesn't expose a banned_url; sync TRaSH groups and use the file if present
            await self.sync_trash_groups(file_path)
            if Path(file_path).exists():
                return file_path
        banned_url = getattr(tracker_instance, "banned_url", None)
        if not isinstance(banned_url, str):
            return None

        # Check if we need to update
        if not await self.should_update(file_path):
            return file_path

        api_key = self.config["TRACKERS"][tracker]["api_key"].strip()
        auth_mode = getattr(tracker_instance, "banned_groups_auth_mode", "bearer")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if auth_mode == "bearer":
            headers["Authorization"] = f"Bearer {api_key}"

        all_data: list[JsonDict] = []
        next_cursor: str | None = None

        async with httpx.AsyncClient() as client:
            while True:
                try:
                    if auth_mode == "api_token":
                        params: JsonDict = {"api_token": api_key}
                    else:
                        # Add query parameters for pagination.
                        params = {"cursor": next_cursor, "per_page": 100} if next_cursor else {"per_page": 100}
                    response = await client.get(url=banned_url, headers=headers, params=params)

                    if response.status_code == 200:
                        response_json = response.json()

                        if isinstance(response_json, list):
                            # Directly add the list if it's the entire response
                            all_data.extend(cast(list[JsonDict], response_json))
                            break  # No pagination in this case
                        if isinstance(response_json, dict):
                            response_dict = cast(JsonDict, response_json)
                            response_key = getattr(tracker_instance, "banned_groups_response_key", "data")
                            page_data_any = response_dict.get(response_key, [])
                            if not isinstance(page_data_any, list):
                                logger.info(f"[red]Unexpected '{response_key}' format: {type(page_data_any)}[/red]")
                                return None

                            page_data = cast(list[JsonDict], page_data_any)
                            all_data.extend(page_data)
                            meta_info_any = response_dict.get("meta", {})
                            if not isinstance(meta_info_any, dict):
                                logger.info(f"[red]Unexpected 'meta' format: {type(meta_info_any)}[/red]")
                                return None

                            meta_info = cast(JsonDict, meta_info_any)

                            # Check if there is a next page
                            next_cursor_value = cast(str | None, meta_info.get("next_cursor"))
                            next_cursor = next_cursor_value if next_cursor_value else None
                            if not next_cursor:
                                break  # Exit loop if there are no more pages
                        else:
                            logger.info(f"[red]Unexpected response format: {type(response_json)}[/red]")
                            return None
                    elif response.status_code == 404:
                        logger.info(f"Error: Tracker '{tracker}' returned 404 for the banned groups API.")
                        return None
                    else:
                        logger.info(f"Error: Received status code {response.status_code} for tracker '{tracker}'.")
                        return None

                except httpx.RequestError as e:
                    logger.info(f"[red]HTTP Request failed for tracker '{tracker}': {e}[/red]")
                    return None
                except Exception as e:
                    logger.info(f"[red]An unexpected error occurred: {e}[/red]")
                    return None

        logger.debug(f"Total banned groups retrieved: {len(all_data)}")

        if not all_data:
            return "empty"

        await self.write_banned_groups_to_file(file_path, all_data)

        return file_path

    async def write_banned_groups_to_file(self, file_path: str, json_data: list[Any]) -> None:
        try:
            Path(file_path).parent.mkdir(parents=True, exist_ok=True)

            # Extract group names from either object payloads or plain string payloads.
            names: list[str] = []
            for item in json_data:
                if isinstance(item, dict) and "name" in item:
                    names.append(str(item["name"]))
                elif isinstance(item, str):
                    names.append(item)
            names_csv = ", ".join(names)
            file_content: dict[str, Any] = {"last_updated": datetime.now(UTC).strftime("%Y-%m-%d"), "banned_groups": names_csv, "raw_data": json_data}

            await asyncio.to_thread(self._write_file, file_path, file_content)
            logger.debug(f"File '{file_path}' updated successfully with {len(names)} groups.")
        except Exception as e:
            logger.info(f"An error occurred: {e}")

    async def sync_trash_groups(self, file_path: str) -> None:
        """Fetch TRaSH guide JSON and extract release group names to ban file.

        This downloads the TRaSH LQ release-group specifications, extracts
        group names from `ReleaseGroupSpecification` fields, and writes them
        via `write_banned_groups_to_file` into the tracker's banned file.
        """
        url = "https://raw.githubusercontent.com/TRaSH-Guides/Guides/refs/heads/master/docs/json/radarr/cf/lq.json"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url)
                if response.status_code != 200:
                    logger.error(f"[red]Failed to fetch TRaSH groups: HTTP {response.status_code}[/red]")
                    return
                data = response.json()
                data = cast(JsonDict, data)
        except Exception as e:
            logger.error(f"[red]Failed to fetch TRaSH groups: {e}[/red]")
            return

        specs = cast(list[JsonDict], data.get("specifications", []))
        groups: list[str] = []

        for spec in specs:
            try:
                if spec.get("implementation") != "ReleaseGroupSpecification":
                    continue
                fields = cast(JsonDict, spec.get("fields") or {})
                val = str(fields.get("value", "") or "")
                # Prefer a captured group if present: e.g. ^(GROUP)$ or \b(GROUP)\b
                m = re.search(r"\(([^)]+)\)", val)
                if m:
                    name = m.group(1)
                else:
                    # Fallback: strip common regex anchors and escapes
                    name = re.sub(r"[\\\^\$\\b]", "", val)
                    name = re.sub(r"[\(\)\[\]\|]", "", name).strip()

                if not name:
                    continue

                # Handle alternation inside the captured name
                if "|" in name:
                    parts = [p.strip() for p in name.split("|") if p.strip()]
                    for p in parts:
                        if p not in groups:
                            groups.append(p)
                else:
                    if name not in groups:
                        groups.append(name)
            except (KeyError, TypeError, ValueError, AttributeError, re.error) as e:
                logger.debug(f"[yellow]Skipped invalid TRaSH specification: {e}[/yellow]")
                continue

        json_data = [{"name": g} for g in groups]

        if not json_data:
            logger.debug("[yellow]No groups extracted from TRaSH data.[/yellow]")
            return

        await self.write_banned_groups_to_file(file_path, json_data)

    def _write_file(self, file_path: str, data: JsonDict) -> None:
        """Blocking file write operation, runs in a background thread"""
        with Path(file_path).open("w", encoding="utf-8") as file:
            json.dump(data, file, indent=4)

    async def should_update(self, file_path: str) -> bool:
        try:
            content = await asyncio.to_thread(self._read_file, file_path)
            data = cast(JsonDict, json.loads(content))
            last_updated = datetime.strptime(str(data["last_updated"]), "%Y-%m-%d").replace(tzinfo=UTC)
            return datetime.now(UTC) >= last_updated + timedelta(days=1)
        except FileNotFoundError:
            return True
        except Exception as e:
            logger.info(f"Error reading file: {e}")
            return True

    def _read_file(self, file_path: str) -> str:
        """Helper function to read the file in a blocking thread"""
        with Path(file_path).open(encoding="utf-8") as file:
            return file.read()

    async def check_banned_group(self, tracker: str, banned_group_list: list[Any], meta: Meta) -> bool:
        result = False
        if not meta.tag:
            return False

        group_tags = meta.tag[1:].lower()
        if "taoe" in group_tags:
            group_tags = "taoe"

        if tracker.upper() in ("AITHER", "CAPYBARABR", "LST", "LUMINARR", "SPEEDAPP", "ZENITH"):
            file_path = await self.get_banned_groups(meta, tracker)
            if file_path == "empty":
                logger.info(f"[bold red]No banned groups found for '{tracker}'.")
                return False
            if not file_path:
                logger.info(f"[bold red]Failed to load banned groups for '{tracker}'.")
                return False

            # Load the banned groups from the file
            try:
                content = await asyncio.to_thread(self._read_file, file_path)
                data = json.loads(content)
                banned_groups = data.get("banned_groups", "")
                if banned_groups:
                    banned_group_list = banned_groups.split(", ")

            except FileNotFoundError:
                logger.info(f"[bold red]Banned group file for '{tracker}' not found.")
                return False
            except json.JSONDecodeError:
                logger.info(f"[bold red]Failed to parse banned group file for '{tracker}'.")
                return False

        for tag in banned_group_list:
            if isinstance(tag, list):
                tag_list = [str(item) for item in cast(list[Any], tag)]
                if not tag_list:
                    continue
                tag_name = tag_list[0]
                if group_tags == tag_name.lower():
                    logger.info(f"[bold yellow]{meta.tag[1:]}[/bold yellow][bold red] was found on [bold yellow]{tracker}'s[/bold yellow] list of banned groups.")
                    if len(tag_list) > 1:
                        logger.info(f"[bold red]NOTE: [bold yellow]{tag_list[1]}")
                    result = True
            else:
                tag_name = str(tag)
                if group_tags == tag_name.lower():
                    logger.info(f"[bold yellow]{meta.tag[1:]}[/bold yellow][bold red] was found on [bold yellow]{tracker}'s[/bold yellow] list of banned groups.")
                    result = True

        if result:
            if not meta.unattended or meta.unattended_confirm:
                try:
                    if cli_ui.ask_yes_no(cli_ui.red, "Do you want to continue anyway?", default=False):
                        return False
                except EOFError:
                    logger.info("\n[red]Exiting on user request (Ctrl+C)[/red]")
                    await cleanup_manager.cleanup()
                    cleanup_manager.reset_terminal()
                    sys.exit(1)
                return True

            return True

        return False

    async def write_internal_claims_to_file(self, file_path: str, data: list[JsonDict]) -> None:
        try:
            Path(file_path).parent.mkdir(parents=True, exist_ok=True)

            extracted_data: list[JsonDict] = []
            for item in data:
                if "attributes" not in item:
                    logger.info(f"Skipping invalid item: {item}")
                    continue

                attributes = cast(JsonDict, item["attributes"])
                extracted_data.append(
                    {
                        "title": attributes.get("title", "Unknown"),
                        "season": attributes.get("season", "Unknown"),
                        "tmdb_id": attributes.get("tmdb_id", "Unknown"),
                        "resolutions": attributes.get("resolutions", []),
                        "types": attributes.get("types", []),
                    }
                )

            if not extracted_data:
                logger.debug("No valid claims found to write.")
                return

            titles_csv = ", ".join([str(entry.get("title", "")) for entry in extracted_data])

            file_content: dict[str, Any] = {
                "last_updated": datetime.now(UTC).strftime("%Y-%m-%d"),
                "titles_csv": titles_csv,
                "extracted_data": extracted_data,
                "raw_data": data,
            }

            await asyncio.to_thread(self._write_file, file_path, file_content)
            logger.debug(f"File '{file_path}' updated successfully with {len(extracted_data)} claims.")
        except Exception as e:
            logger.info(f"An error occurred: {e}")

    async def get_torrent_claims(self, meta: Meta, tracker: str) -> bool | None:
        file_path = Path(meta.base_dir) / "data" / "banned" / f"{tracker}_claimed_releases.json"
        tracker_instance = self._create_tracker_instance(tracker)
        if tracker_instance is None:
            return None
        claims_url = getattr(tracker_instance, "claims_url", None)
        if not isinstance(claims_url, str):
            return None

        # Check if we need to update
        if not await self.should_update(file_path):
            return await self.check_tracker_claims(meta, tracker)

        headers = {"Authorization": f"Bearer {self.config['TRACKERS'][tracker]['api_key'].strip()}", "Content-Type": "application/json", "Accept": "application/json"}

        all_data: list[JsonDict] = []
        next_cursor: str | None = None

        async with httpx.AsyncClient() as client:
            while True:
                try:
                    # Add query parameters for pagination
                    params: JsonDict = {"cursor": next_cursor, "per_page": 100} if next_cursor else {"per_page": 100}
                    response = await client.get(url=claims_url, headers=headers, params=params)

                    if response.status_code == 200:
                        response_json = response.json()
                        if not isinstance(response_json, dict):
                            logger.info(f"[red]Unexpected response format: {type(response_json)}[/red]")
                            return False
                        response_dict = cast(JsonDict, response_json)
                        page_data_any = response_dict.get("data", [])
                        if not isinstance(page_data_any, list):
                            logger.info(f"[red]Unexpected 'data' format: {type(page_data_any)}[/red]")
                            return False
                        page_data = cast(list[JsonDict], page_data_any)

                        all_data.extend(page_data)
                        meta_info_any = response_dict.get("meta", {})
                        if not isinstance(meta_info_any, dict):
                            logger.info(f"[red]Unexpected 'meta' format: {type(meta_info_any)}[/red]")
                            return False
                        meta_info = cast(JsonDict, meta_info_any)

                        # Check if there is a next page
                        next_cursor = cast(str | None, meta_info.get("next_cursor"))
                        if not next_cursor:
                            break  # Exit loop if there are no more pages
                    else:
                        logger.error(f"[red]Error: Received status code {response.status_code}[/red]")
                        return False

                except httpx.RequestError as e:
                    logger.info(f"[red]HTTP Request failed: {e}[/red]")
                    return False
                except Exception as e:
                    logger.info(f"[red]An unexpected error occurred: {e}[/red]")
                    return False

        logger.debug(f"Total claims retrieved: {len(all_data)}")

        if not all_data:
            return False

        await self.write_internal_claims_to_file(file_path, all_data)

        return await self.check_tracker_claims(meta, tracker)

    async def check_tracker_claims(self, meta: Meta, tracker: str | list[str]) -> bool:
        trackers = [tracker.strip().upper()] if isinstance(tracker, str) else [str(s).upper() for s in cast(list[Any], tracker)]

        async def process_single_tracker(tracker_name: str) -> bool:
            try:
                tracker_instance = self._create_tracker_instance(tracker_name)
                if tracker_instance is None:
                    logger.info(f"[red]Tracker {tracker_name} is not registered in tracker_class_map[/red]")
                    return False

                # Get name-to-ID mappings directly
                type_mapping = cast(JsonDict, await tracker_instance.get_type_id(meta, mapping_only=True))
                type_name = meta.type
                type_ids: list[Any] = [type_mapping.get(type_name)] if type_name else []
                if None in type_ids:
                    logger.warning("[yellow]Warning: Type in meta not found in tracker type mapping.[/yellow]")

                resolution_mapping = cast(JsonDict, await tracker_instance.get_resolution_id(meta, mapping_only=True))
                resolution_name = meta.resolution
                resolution_ids: list[Any] = [resolution_mapping.get(resolution_name)] if resolution_name else []
                if None in resolution_ids:
                    logger.warning("[yellow]Warning: Resolution in meta not found in tracker resolution mapping.[/yellow]")

                tmdb_value = meta.tmdb
                tmdb_id = [] if tmdb_value is None else [tmdb_value]

                seasonint = 0
                metaseason = meta.season_int
                if metaseason:
                    seasonint = metaseason
                file_path = Path(meta.base_dir) / "data" / "banned" / f"{tracker_name}_claimed_releases.json"
                if not Path(file_path).exists():
                    logger.info(f"[red]No claim data file found for {tracker_name}[/red]")
                    return False

                file_content = await asyncio.to_thread(Path(file_path).read_text, encoding="utf-8")
                extracted_data = cast(JsonDict, json.loads(file_content)).get("extracted_data", [])
                extracted_data = cast(list[JsonDict], extracted_data)

                for item in extracted_data:
                    title = item.get("title")
                    season = item.get("season")
                    api_tmdb_id = item.get("tmdb_id")
                    api_resolutions = cast(list[Any], item.get("resolutions", []))
                    api_types = cast(list[Any], item.get("types", []))

                    if (
                        api_tmdb_id in tmdb_id
                        and (meta.category == "MOVIE" or season == seasonint)
                        and all(res in api_resolutions for res in resolution_ids)
                        and all(typ in api_types for typ in type_ids)
                    ):
                        logger.info(f"[green]Claimed match found at [cyan]{tracker}: [yellow]{title}, Season: {season}, TMDB ID: {api_tmdb_id}[/green]")
                        return True

                return False

            except Exception as e:
                logger.error(f"[red]Error processing tracker {tracker_name}: {e}[/red]")
                import traceback

                logger.info(traceback.format_exc())
                return False

        results = await asyncio.gather(*[process_single_tracker(tracker) for tracker in trackers])
        return any(results)

    async def get_tracker_requests(self, meta: Meta, tracker: str, url: str) -> list[JsonDict]:
        logger.debug(f"[bold green]Searching for existing requests on {tracker}[/bold green]")
        requests: list[dict[str, Any]] = []
        headers = {"Authorization": f"Bearer {self.config['TRACKERS'][tracker]['api_key'].strip()}", "Accept": "application/json"}
        if meta.tmdb is None:
            return requests
        params = {"tmdbId": meta.tmdb} if tracker == "HAWKEUNO" else {"tmdb": meta.tmdb}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url=url, headers=headers, params=params)
                if response.status_code == 200:
                    data = response.json()
                    if not isinstance(data, dict):
                        logger.info(f"[bold red]Unexpected response format: {type(data)}[/bold red]")
                        return requests
                    data_dict = cast(JsonDict, data)
                    results_list: list[Any] = []
                    if "data" in data_dict and isinstance(data_dict["data"], list):
                        results_list.extend([item for item in data_dict["data"] if isinstance(item, dict)])
                    elif "results" in data_dict and isinstance(data_dict["results"], list):
                        results_list.extend([item for item in data_dict["results"] if isinstance(item, dict)])
                    else:
                        logger.info("[bold red]Unexpected response format[/bold red]")
                        return requests

                    try:
                        for each in results_list:
                            attributes = each.get("attributes", each) if tracker == "HAWKEUNO" else cast(JsonDict, each)
                            result: JsonDict = {
                                "id": each.get("id") if tracker == "HAWKEUNO" else attributes.get("id"),
                                "name": attributes.get("name"),
                                "description": attributes.get("description"),
                                "category": attributes.get("category_id"),
                                "type": attributes.get("type_id"),
                                "resolution": attributes.get("resolution_id"),
                                "bounty": attributes.get("bounty"),
                                "status": attributes.get("status"),
                                "claimed": attributes.get("claimed"),
                                "season": attributes.get("season_number"),
                                "episode": attributes.get("episode_number"),
                            }
                            requests.append(result)
                    except Exception as e:
                        logger.info(f"[bold red]Error processing response data: {e}[/bold red]")
                        return requests
                else:
                    logger.info(f"[bold red]Failed to search torrents on {tracker}. HTTP Status: {response.status_code}")
        except httpx.TimeoutException:
            logger.info("[bold red]Request timed out after 5 seconds")
        except httpx.RequestError as e:
            logger.info(f"[bold red]Unable to search for existing torrents: {e}")
        except Exception as e:
            logger.error(f"[bold red]Unexpected error: {e}")

        return requests

    async def bhd_request_check(self, meta: Meta, tracker: str, url: str) -> list[JsonDict]:
        if "BEYONDHD" not in self.config["TRACKERS"] or not self.config["TRACKERS"]["BEYONDHD"].get("api_key"):
            logger.info("[red]BEYONDHD API key not configured. Skipping BEYONDHD request check.[/red]")
            return []
        logger.debug(f"[bold green]Searching for existing requests on {tracker}[/bold green]")
        requests: list[dict[str, Any]] = []
        params = {
            "action": "search",
            "tmdb_id": f"{(meta.category or '').lower()}/{meta.tmdb_id}",
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url=url, params=params)
                if response.status_code == 200:
                    data = response.json()
                    if not isinstance(data, dict):
                        logger.info(f"[bold red]Unexpected response format: {type(data)}[/bold red]")
                        return requests
                    data_dict = cast(JsonDict, data)
                    results_list: list[Any] = []
                    if "data" in data_dict and isinstance(data_dict["data"], list):
                        results_list.extend([item for item in data_dict["data"] if isinstance(item, dict)])
                    elif "results" in data_dict and isinstance(data_dict["results"], list):
                        results_list.extend([item for item in data_dict["results"] if isinstance(item, dict)])
                    else:
                        logger.info("[bold red]Unexpected response format[/bold red]")
                        return requests

                    try:
                        for each in results_list:
                            attributes = cast(JsonDict, each)
                            result: JsonDict = {
                                "id": attributes.get("id"),
                                "name": attributes.get("name"),
                                "type": attributes.get("source"),
                                "resolution": attributes.get("type"),
                                "dv": attributes.get("dv"),
                                "hdr": attributes.get("hdr"),
                                "bounty": attributes.get("bounty"),
                                "status": attributes.get("status"),
                                "internal": attributes.get("internal"),
                                "url": attributes.get("url"),
                            }
                            requests.append(result)
                    except Exception as e:
                        logger.info(f"[bold red]Error processing response data: {e}[/bold red]")
                        logger.info(f"[bold red]Response data: {data}[/bold red]")
                        return requests
                else:
                    logger.info(f"[bold red]Failed to search torrents. HTTP Status: {response.status_code}")
        except httpx.TimeoutException:
            logger.info("[bold red]Request timed out after 5 seconds")
        except httpx.RequestError as e:
            logger.info(f"[bold red]Unable to search for existing torrents: {e}")
        except Exception as e:
            logger.error(f"[bold red]Unexpected error: {e}")
        # console.print(f"Debug: BEYONDHD requests found: {requests}")
        return requests

    async def tracker_request(self, meta: Meta, tracker: str | list[str]) -> bool:
        trackers = [tracker.strip().upper()] if isinstance(tracker, str) else [str(s).upper() for s in cast(list[Any], tracker)]

        async def process_single_tracker(tracker_name: str) -> bool | list[JsonDict]:
            tracker_instance = self._create_tracker_instance(tracker_name)
            if tracker_instance is None:
                logger.info(f"[red]Tracker {tracker_name} is not registered in tracker_class_map[/red]")
                return False

            requests: list[JsonDict] = []
            url: str | None = None
            type_ids: list[Any] = []
            resolution_ids: list[Any] = []
            category_ids: list[Any] = []
            try:
                url = tracker_instance.requests_url
            except AttributeError:
                if tracker_name.upper() not in ("AMIGOSSHARE", "BJSHARE", "FUNFILE", "HDSPACE", "AVISTAZ", "CINEMAZ", "PRIVATEHD"):
                    # tracker without requests url not supported
                    return False

            if tracker_name.upper() == "BEYONDHD":
                if not url:
                    return False
                requests = await self.bhd_request_check(meta, tracker_name, url)
            elif tracker_name.upper() in ("AMIGOSSHARE", "BJSHARE", "FUNFILE", "HDSPACE", "AVISTAZ", "CINEMAZ", "PRIVATEHD", "MTEAM", "ORPHEUS"):
                # These trackers have custom request handling
                requests = cast(list[JsonDict], await tracker_instance.get_requests(meta))
                return bool(requests) if tracker_name.upper() == "ORPHEUS" else False
            else:
                if not url:
                    return False
                requests = await self.get_tracker_requests(meta, tracker_name, url)
                type_mapping = cast(JsonDict, await tracker_instance.get_type_id(meta, mapping_only=True))
                type_name = meta.type
                type_ids: list[Any] = [type_mapping.get(type_name)] if type_name else []
                if None in type_ids:
                    logger.warning("[yellow]Warning: Type in meta not found in tracker type mapping.[/yellow]")

                resolution_mapping = cast(JsonDict, await tracker_instance.get_resolution_id(meta, mapping_only=True))
                resolution_name = meta.resolution
                resolution_ids: list[Any] = [resolution_mapping.get(resolution_name)] if resolution_name else []
                if None in resolution_ids:
                    logger.warning("[yellow]Warning: Resolution in meta not found in tracker resolution mapping.[/yellow]")

                category_mapping = cast(JsonDict, await tracker_instance.get_category_id(meta, mapping_only=True))
                category_name = meta.category
                category_ids: list[Any] = [category_mapping.get(category_name)] if category_name else []
                if None in category_ids:
                    logger.warning("[yellow]Warning: Some categories in meta not found in tracker category mapping.[/yellow]")

            # Initialize request log for this tracker
            common = Common(self.config)
            log_path = f"{meta.base_dir}{'/' + 'tmp' + '/'}{tracker_name}_request_results.json"
            if not await common.path_exists(log_path):
                await common.makedirs(str(Path(log_path).parent))

            request_data: list[JsonDict] = []
            try:
                async with aiofiles.open(log_path, encoding="utf-8") as f:
                    content = await f.read()
                    loaded: object = json.loads(content) if content.strip() else []
                    if isinstance(loaded, list):
                        request_data = cast(list[JsonDict], loaded)
            except Exception:
                request_data = []

            existing_uuids = {str(entry.get("uuid")) for entry in request_data}
            uuid_value = meta.uuid
            uuid_str = uuid_value if uuid_value is not None else ""

            for each in requests:
                type_name = False
                resolution = False
                season = False
                episode = False
                double_check = False
                api_id = each.get("id")
                api_category = each.get("category")
                api_name = str(each.get("name") or "")
                api_type = each.get("type")
                api_type_str = str(api_type or "")
                api_bounty = each.get("bounty")
                api_status = each.get("status")
                api_description = str(each.get("description") or "")
                api_resolution = each.get("resolution")
                api_resolution_str = str(api_resolution or "")
                api_resolution_lower = api_resolution_str.lower()
                if "BEYONDHD" not in tracker_name:
                    if str(api_type) in [str(tid) for tid in type_ids]:
                        type_name = True
                    elif api_type is None:
                        type_name = True
                        double_check = True
                    if str(api_resolution) in [str(rid) for rid in resolution_ids]:
                        resolution = True
                    elif api_resolution is None:
                        resolution = True
                        double_check = True
                    api_claimed = each.get("claimed")
                    api_season = 0
                    api_episode = 0
                    if meta.category == "TV":
                        season_value = each.get("season")
                        api_season = int(season_value) if season_value is not None else 0
                        if api_season and meta.season_int and api_season == meta.season_int:
                            season = True
                        episode_value = each.get("episode")
                        api_episode = int(episode_value) if episode_value is not None else 0
                        if api_episode and meta.episode_int and api_episode == meta.episode_int:
                            episode = True
                    if str(api_category) in [str(cid) for cid in category_ids]:
                        new_url = re.sub(r"/api/requests/filter$", f"/requests/{api_id}", cast(str, url))
                        if meta.category == "MOVIE" and type_name and resolution and not api_claimed:
                            logger.info(
                                f"[bold blue]Found exact request match on [bold yellow]{tracker_name}[/bold yellow] with bounty [bold yellow]{api_bounty}[/bold yellow] and with status [bold yellow]{api_status}[/bold yellow][/bold blue]"
                            )
                            logger.info(f"[bold blue]Claimed status:[/bold blue] [bold yellow]{api_claimed}[/bold yellow]")
                            logger.info(f"[bold green]{api_name}:[/bold green] {new_url}")
                            logger.info("")
                            if double_check:
                                logger.info("[bold red]Type and/or resolution was set to ANY, double check any description requirements:[/bold red]")
                                logger.info(f"[bold yellow]Request desc:[/bold yellow] {api_description[:100]}")
                                logger.info("")

                            if uuid_str and uuid_str not in existing_uuids:
                                request_entry = {
                                    "uuid": uuid_str,
                                    "path": meta.path,
                                    "url": new_url,
                                    "name": api_name,
                                    "bounty": api_bounty,
                                    "description": api_description,
                                    "claimed": api_claimed,
                                }
                                request_data.append(request_entry)
                                existing_uuids.add(uuid_str)
                        elif meta.category == "TV" and season and episode and type_name and resolution and not api_claimed:
                            logger.info(
                                f"[bold blue]Found exact request match on [bold yellow]{tracker_name}[/bold yellow] with bounty [bold yellow]{api_bounty}[/bold yellow] and with status [bold yellow]{api_status}[/bold yellow][/bold blue]"
                            )
                            logger.info(f"[bold blue]Claimed status:[/bold blue] [bold yellow]{api_claimed}[/bold yellow]")
                            logger.info(f"[bold yellow]{api_name}[/bold yellow] - [bold yellow]S{api_season:02d} E{api_episode:02d}:[/bold yellow] {new_url}")
                            logger.info("")
                            if double_check:
                                logger.info("[bold red]Type and/or resolution was set to ANY, double check any description requirements:[/bold red]")
                                logger.info(f"[bold yellow]Request desc:[/bold yellow] {api_description[:100]}")
                                logger.info("")

                            if uuid_str and uuid_str not in existing_uuids:
                                request_entry: dict[str, Any] = {
                                    "uuid": uuid_str,
                                    "path": meta.path,
                                    "url": new_url,
                                    "name": api_name,
                                    "bounty": api_bounty,
                                    "description": api_description,
                                    "claimed": api_claimed,
                                }
                                request_data.append(request_entry)
                                existing_uuids.add(uuid_str)
                        else:
                            logger.info(
                                f"[bold blue]Found request on [bold yellow]{tracker_name}[/bold yellow] with bounty [bold yellow]{api_bounty}[/bold yellow] and with status [bold yellow]{api_status}[/bold yellow][/bold blue]"
                            )
                            logger.info(f"[bold blue]Claimed status:[/bold blue] [bold yellow]{api_claimed}[/bold yellow]")
                            if meta.category == "MOVIE":
                                logger.info(f"[bold yellow]{api_name}:[/bold yellow] {new_url}")
                            else:
                                logger.info(f"[bold yellow]{api_name}[/bold yellow] - [bold yellow]S{api_season:02d} E{api_episode:02d}:[/bold yellow] {new_url}")
                            logger.info(f"[bold green]Request desc: {api_description[:100]}[/bold green]")
                            logger.info("")

                            if not api_claimed and uuid_str and uuid_str not in existing_uuids:
                                request_entry = {
                                    "uuid": uuid_str,
                                    "path": meta.path,
                                    "url": new_url,
                                    "name": api_name,
                                    "bounty": api_bounty,
                                    "description": api_description,
                                    "claimed": api_claimed,
                                    "match_type": "partial",
                                }
                                request_data.append(request_entry)
                                existing_uuids.add(uuid_str)
                else:
                    unclaimed = each.get("status") == 1
                    internal = each.get("internal") == 1
                    claimed_status = ""
                    if each.get("status") == 1:
                        claimed_status = "Unfilled"
                    elif each.get("status") == 2:
                        claimed_status = "Claimed"
                    elif each.get("status") == 3:
                        claimed_status = "Pending"
                    dv = False
                    hdr = False
                    season = False
                    meta_hdr = meta.HDR
                    is_season = re.search(r"S\d{2}", api_name)
                    if is_season and is_season == meta.season:
                        season = True
                    if each.get("dv") and meta_hdr == "DV":
                        dv = True
                    if each.get("hdr") and meta_hdr in ("HDR10", "HDR10+", "HDR"):
                        hdr = True
                    if not each.get("dv") and "DV" not in meta_hdr:
                        dv = True
                    if not each.get("hdr") and meta_hdr not in ("HDR10", "HDR10+", "HDR"):
                        hdr = True
                    if "remux" in api_resolution_lower:
                        if ("uhd" in api_resolution_lower and meta.resolution == "2160p" and meta.type == "REMUX") or (
                            "uhd" not in api_resolution_lower and meta.resolution == "1080p" and meta.type == "REMUX"
                        ):
                            resolution = True
                            type_name = True
                    elif "remux" not in api_resolution_lower and meta.is_disc == "BDMV":
                        if ("uhd" in api_resolution_lower and meta.resolution == "2160p") or ("uhd" not in api_resolution_lower and meta.resolution == "1080p"):
                            resolution = True
                            type_name = True
                    elif api_resolution == meta.resolution:
                        resolution = True
                    meta_type = meta.type or ""
                    if ("Blu-ray" in api_type_str and meta_type == "ENCODE") or ("WEB" in api_type_str and "WEB" in meta_type):
                        type_name = True
                    if meta.category == "MOVIE" and type_name and resolution and unclaimed and not internal and dv and hdr:
                        logger.info(
                            f"[bold blue]Found exact request match on [bold yellow]{tracker_name}[/bold yellow] with bounty [bold yellow]{api_bounty}[/bold yellow] and with status [bold yellow]{claimed_status}[/bold yellow][/bold blue]"
                        )
                        logger.info(f"[bold green]{api_name}:[/bold green] {each.get('url')}")
                        logger.info("")

                        if uuid_str and uuid_str not in existing_uuids:
                            request_entry = {"uuid": uuid_str, "path": meta.path, "url": each.get("url", ""), "name": api_name, "bounty": api_bounty, "claimed": claimed_status}
                            request_data.append(request_entry)
                            existing_uuids.add(uuid_str)
                    if meta.category == "MOVIE" and type_name and resolution and unclaimed and not internal and not dv and not hdr and "uhd" in api_resolution_lower:
                        logger.info(
                            f"[bold blue]Found request match on [bold yellow]{tracker_name}[/bold yellow] with bounty [bold yellow]{api_bounty}[/bold yellow] with mismatched HDR or DV[/bold blue]"
                        )
                        logger.info(f"[bold green]{api_name}:[/bold green] {each.get('url')}")
                        logger.info("")

                        if uuid_str and uuid_str not in existing_uuids:
                            request_entry = {"uuid": uuid_str, "path": meta.path, "url": each.get("url", ""), "name": api_name, "bounty": api_bounty, "claimed": claimed_status}
                            request_data.append(request_entry)
                            existing_uuids.add(uuid_str)
                    if meta.category == "TV" and season and type_name and resolution and unclaimed and not internal and dv and hdr:
                        logger.info(
                            f"[bold blue]Found exact request match on [bold yellow]{tracker_name}[/bold yellow] with bounty [bold yellow]{api_bounty}[/bold yellow] and with status [bold yellow]{claimed_status}[/bold yellow][/bold blue]"
                        )
                        logger.info(f"[bold yellow]{api_name}[/bold yellow] - [bold yellow]{meta.season}:[/bold yellow] {each.get('url')}")
                        logger.info("")

                        if uuid_str and uuid_str not in existing_uuids:
                            request_entry = {"uuid": uuid_str, "path": meta.path, "url": each.get("url", ""), "name": api_name, "bounty": api_bounty, "claimed": claimed_status}
                            request_data.append(request_entry)
                            existing_uuids.add(uuid_str)
                    if meta.category == "TV" and season and type_name and resolution and unclaimed and not internal and not dv and not hdr:
                        logger.info(
                            f"[bold blue]Found request match on [bold yellow]{tracker_name}[/bold yellow] with bounty [bold yellow]{api_bounty}[/bold yellow] with mismatched HDR or DV[/bold blue]"
                        )
                        logger.info(f"[bold yellow]{api_name}[/bold yellow] - [bold yellow]{meta.season}:[/bold yellow] {each.get('url')}")
                        logger.info("")

                        if uuid_str and uuid_str not in existing_uuids:
                            request_entry = {"uuid": uuid_str, "path": meta.path, "url": each.get("url", ""), "name": api_name, "bounty": api_bounty, "claimed": claimed_status}
                            request_data.append(request_entry)
                            existing_uuids.add(uuid_str)
                    else:
                        logger.info(
                            f"[bold blue]Found request on [bold yellow]{tracker_name}[/bold yellow] with bounty [bold yellow]{api_bounty}[/bold yellow] and with status [bold yellow]{claimed_status}[/bold yellow][/bold blue]"
                        )
                        if internal:
                            logger.info("[bold red]Request is internal only[/bold red]")
                        logger.info(f"[bold yellow]{api_name}[/bold yellow] - {each.get('url')}")
                        logger.info("")

            # Save all logged requests to file
            if request_data:
                async with aiofiles.open(log_path, "w", encoding="utf-8") as f:
                    await f.write(json.dumps(request_data, indent=4))

            return requests

        results = await asyncio.gather(*[process_single_tracker(tracker) for tracker in trackers])
        return any(results)

    async def process_trumpables(self, meta: Meta, tracker: str) -> bool:
        tracker_instance = self._create_tracker_instance(tracker)
        if tracker_instance is None:
            logger.info(f"[red]Tracker {tracker} is not registered in tracker_class_map[/red]")
            return False

        url = getattr(tracker_instance, "trumping_url", None)
        if not isinstance(url, str):
            logger.info(f"[red]Tracker {tracker} does not support trumping reports.[/red]")
            return False

        reported_torrent_id = f"{meta.get(f'{tracker}_trumpable_id', '')}"
        if not reported_torrent_id:
            # Try tracker-specific matched ID
            reported_torrent_id = f"{meta.get(f'{tracker}_matched_id', '')}"
        if not reported_torrent_id and meta.get(f"{tracker}_matched_episode_ids", []):
            reported_torrent_id = f"{meta[f'{tracker}_matched_episode_ids'][0].get('id', '')}"
        if not reported_torrent_id:
            logger.info(f"[red]No reported torrent ID found in meta for trumpable processing on {tracker}[/red]")
            return False
        # Store per-tracker to avoid overwriting across multiple trackers
        meta[f"{tracker}_reported_torrent_id"] = reported_torrent_id
        if tracker == "LST":
            logger.debug("[bold green]LST does not support searching existing trump reports[/bold green]")
            return True

        if not isinstance(meta.skip_upload_trackers, list):
            meta.skip_upload_trackers = []

        trumping_reports, status = await self.get_tracker_trumps(tracker, url, reported_torrent_id)
        upload = False
        if status != 200:
            logger.info(f"[bold red]Failed to retrieve trumping reports from {tracker}. HTTP Status: {status}[/bold red]")
            # Mark this tracker as failed/skipped and continue to the next tracker
            logger.info(f"[bold red]Marking {tracker} to be skipped due to API failure[/bold red]")
            if tracker not in meta.skip_upload_trackers:
                meta.skip_upload_trackers.append(tracker)
            return False
        if trumping_reports:
            logger.info(f"[bold yellow]Found {len(trumping_reports)} existing trumping report/s on {tracker} for this release[/bold yellow]")
            for report in trumping_reports:
                logger.info(f"  [cyan]Report ID:[/cyan] {report.get('id')} - [cyan]Title:[/cyan] {report.get('title')}")
                if report.get("trumping_torrent"):
                    for torrent in report.get("trumping_torrent", []):
                        torrent_name = torrent.get("name", "Unknown")
                        torrent_id = torrent.get("id", "N/A")
                        logger.info(f"  [bold green]Already being trumped by:[/bold green] {torrent_name} (ID: {torrent_id})")
                else:
                    logger.info("  [yellow]The trumping torrent for this report seems to be in modq.....[/yellow]")
            try:
                upload = cli_ui.ask_yes_no("Do you want to proceed with the upload anyway?", default=False)
            except EOFError, KeyboardInterrupt:
                logger.info("[yellow]Prompt cancelled; treating as 'no' for safety.[/yellow]")
                upload = False

            if not upload:
                logger.info(f"[bold red]Marking {tracker} to be skipped[/bold red]")
                if tracker not in meta.skip_upload_trackers:
                    meta.skip_upload_trackers.append(tracker)
                return False
            logger.info(f"[bold green]Proceeding with upload despite existing trumping reports on {tracker}[/bold green]")
        else:
            logger.debug(f"[bold green]Will make a trumpable report for this upload at {tracker}[/bold green]")

        if not meta.tv_pack:
            logger.info(f"[yellow]{tracker} requires comparisons to be provided for trump reports.\nAre the comparison images in the description or are you adding links?")
            try:
                where_compare = cli_ui.ask_string("Enter 'd' if in description, 'L' if you want to paste links, or press Enter to skip trumping:", default="")
            except EOFError, KeyboardInterrupt:
                logger.info("[yellow]Prompt cancelled; skipping trump report creation.[/yellow]")
                return False

            where_compare = (where_compare or "").strip()
            if where_compare.lower() == "d":
                meta.screenshots_in_description = True
                return True
            if where_compare.upper() == "L":
                try:
                    reported_screenshots = cli_ui.ask_string("Paste screenshot links for the reported torrent (comma-separated):", default="")
                    trumping_screenshots = cli_ui.ask_string("Paste screenshot links for the trumping torrent (comma-separated):", default="")
                except EOFError, KeyboardInterrupt:
                    logger.info("[yellow]Prompt cancelled; skipping trump report creation.[/yellow]")
                    return False

                reported_screenshots = (reported_screenshots or "").strip()
                trumping_screenshots = (trumping_screenshots or "").strip()
                if not reported_screenshots or not trumping_screenshots:
                    logger.info("[yellow]No screenshot links provided. Skipping trump report creation.[/yellow]")
                    return False

                meta.screenshots_reported_torrent = [link.strip() for link in reported_screenshots.split(",") if link.strip()]
                meta.screenshots_trumping_torrent = [link.strip() for link in trumping_screenshots.split(",") if link.strip()]
                if not meta.screenshots_reported_torrent or not meta.screenshots_trumping_torrent:
                    logger.info("[yellow]No valid screenshot links provided. Skipping trump report creation.[/yellow]")
                    return False
                return True
            logger.info("[yellow]Skipping trump report creation as no comparison method provided.[/yellow]")
            return False
        logger.debug(f"[bold green]TV pack upload detected, skipping comparison images for trump report on {tracker}[/bold green]")
        return True

    async def get_tracker_trumps(self, tracker: str, url: str, reported_torrent_id: str) -> tuple[list[JsonDict], int | None]:
        logger.debug(f"[bold green]Searching for trumps on {tracker}[/bold green]")
        requests: list[JsonDict] = []
        status_code: int | None = None
        headers = {"Authorization": f"Bearer {self.config['TRACKERS'][tracker]['api_key'].strip()}", "Accept": "application/json"}

        params: JsonDict = {
            "reported_torrent_id": f"{reported_torrent_id}",
        }

        all_data: list[Any] = []
        next_cursor: str | None = None

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                while True:
                    try:
                        # Add pagination cursor to params if we have one
                        if next_cursor:
                            params["cursor"] = next_cursor

                        response = await client.get(url=url, headers=headers, params=params)
                        status_code = response.status_code

                        if response.status_code == 200:
                            data = response.json()
                            if not isinstance(data, dict):
                                logger.info(f"[bold red]Unexpected response format: {type(data)}[/bold red]")
                                return requests, status_code
                            data_dict = cast(JsonDict, data)
                            page_data: list[Any] = []
                            if "data" in data_dict and isinstance(data_dict["data"], list):
                                page_data.extend([item for item in data_dict["data"] if isinstance(item, dict)])
                            elif "results" in data_dict and isinstance(data_dict["results"], list):
                                page_data.extend([item for item in data_dict["results"] if isinstance(item, dict)])
                            else:
                                logger.info("[bold red]Unexpected response format[/bold red]")
                                return requests, status_code

                            all_data.extend(page_data)

                            # Check for pagination
                            meta_info_any = data_dict.get("meta", {})
                            if not isinstance(meta_info_any, dict):
                                logger.info(f"[bold red]Unexpected 'meta' format: {type(meta_info_any)}[/bold red]")
                                break

                            meta_info = cast(JsonDict, meta_info_any)

                            next_cursor = cast(str | None, meta_info.get("next_cursor"))
                            if not next_cursor:
                                break  # Exit loop if there are no more pages
                            # Rest between page fetches
                            logger.info(f"[cyan]Fetched {len(page_data)} trumping reports, waiting 1 second before next page...[/cyan]")
                            await asyncio.sleep(1)
                        else:
                            logger.info(f"[bold red]Failed to search trumps on {tracker}. HTTP Status: {response.status_code} - {response.text}[/bold red]")
                            break

                    except httpx.RequestError as e:
                        logger.info(f"[bold red]HTTP Request failed: {e}[/bold red]")
                        break

                # Process all collected data
                try:
                    for each in all_data:
                        # Normalize trumping_torrent to always be a list
                        entry = cast(JsonDict, each)
                        trumping_torrent_value = entry.get("trumping_torrent")
                        if trumping_torrent_value is None:
                            trumping_torrent = []
                        elif isinstance(trumping_torrent_value, dict):
                            trumping_torrent = [cast(JsonDict, trumping_torrent_value)]
                        elif isinstance(trumping_torrent_value, list):
                            trumping_torrent = cast(list[JsonDict], trumping_torrent_value)
                        else:
                            trumping_torrent = []

                        result: JsonDict = {
                            "id": entry.get("id"),
                            "type": entry.get("type"),
                            "title": entry.get("title"),
                            "solved": entry.get("solved"),
                            "reported_torrents": entry.get("reported_torrents", []),
                            "trumping_torrent": trumping_torrent,
                        }
                        requests.append(result)

                except Exception as e:
                    logger.info(f"[bold red]Error processing response data: {e}[/bold red]")
                    return requests, status_code

        except httpx.TimeoutException:
            logger.info("[bold red]Request timed out after 10 seconds")
            status_code = None
        except Exception as e:
            logger.error(f"[bold red]Unexpected error: {e}")
            status_code = None

        logger.debug(f"Total trumping reports retrieved: {len(requests)}")

        return requests, status_code

    async def make_trumpable_report(self, meta: Meta, tracker: str) -> bool:
        """Create a trump report by POSTing to the /create endpoint"""
        logger.debug(f"[bold green]Creating trump report on {tracker}[/bold green]")

        tracker_instance = self._create_tracker_instance(tracker)
        if not tracker_instance:
            logger.info(f"[red]Tracker {tracker} is not registered in tracker_class_map[/red]")
            return False

        base_url = getattr(tracker_instance, "trumping_url", None)
        if not isinstance(base_url, str):
            logger.info(f"[red]No trumping URL found for {tracker}[/red]")
            return False

        reported_torrent_id = meta.get(f"{tracker}_reported_torrent_id", "")
        if not reported_torrent_id:
            logger.info(f"[red]No reported torrent ID found in meta for trump report creation on {tracker}[/red]")
            return False
        # Replace /filter with /create. For LST the URL requires a numeric ID segment.
        if tracker == "LST":
            rt = str(reported_torrent_id).strip()
            if not rt.isdigit():
                logger.info(f"[red]Invalid or missing reported torrent ID for LST: {reported_torrent_id}[/red]")
                return False
            try:
                rid_int = int(rt)
            except ValueError:
                logger.info(f"[red]Reported torrent ID for LST is not an integer: {reported_torrent_id}[/red]")
                return False
            create_url = base_url + f"{rid_int}/trump"
        else:
            create_url = base_url.replace("/filter", "/create")

        headers = {"Authorization": f"Bearer {self.config['TRACKERS'][tracker]['api_key'].strip()}", "Content-Type": "application/json", "Accept": "application/json"}

        # Read per-tracker reported_torrent_id, with fallback to legacy key for backwards compatibility
        if not reported_torrent_id:
            logger.info(f"[red]No reported torrent ID found for {tracker}[/red]")
            return False
        reported_torrent_id = str(reported_torrent_id)
        try:
            status_map = meta.tracker_status or {}
            trumping_torrent_id = status_map[tracker]["torrent_id"]
        except KeyError:
            logger.info(f"[red]No torrent ID found in meta for trumping torrent on {tracker}[/red]")
            logger.info("[red]Either the upload failed, or you're in debug[/red]")
            if not meta.debug:
                return False
            # Set fallback for debug mode so payload construction doesn't fail
            trumping_torrent_id: str | None = None

        if meta.tv_pack:
            message = f"{meta.ua_name} season pack trump"
        elif meta.trump_reason == "exact_match":
            message = f"{meta.ua_name} exact filename trump"
        elif meta.trump_reason == "trumpable_release":
            message = f"{meta.ua_name} trumpable release trump"
        else:
            message = f"{meta.ua_name} is trumping this torrent for reasons {meta.ua_name} has not correctly caught. User selected yes at a prompt."

        if tracker != "LST":
            payload: JsonDict = {"reported_torrent_id": reported_torrent_id, "trumping_torrent_id": trumping_torrent_id, "message": message}
            if "screenshots_reported_torrent" in meta:
                payload["screenshots_reported_torrent"] = ",".join(cast(list[str], meta.screenshots_reported_torrent))
            if "screenshots_trumping_torrent" in meta:
                payload["screenshots_trumping_torrent"] = ",".join(cast(list[str], meta.screenshots_trumping_torrent))
            if "screenshots_in_description" in meta and meta.screenshots_in_description:
                payload["message"] = f"{payload.get('message', '')} - User says comparison screenshots are in description."

        else:
            if not meta.tv_pack:
                try:
                    user_message = cli_ui.ask_string("Enter a reason for the trump report on LST:")
                except EOFError, KeyboardInterrupt:
                    logger.info("[yellow]Prompt cancelled; no additional message provided.[/yellow]")
                    user_message = None
                message = message + ": " + user_message if user_message else message + ": No additional message provided by user"
            message = message + ": https://lst.gg/torrents/" + str(trumping_torrent_id)
            payload: JsonDict = {"message": message}

        if not meta.debug:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.post(url=create_url, headers=headers, json=payload)
                    if response.status_code in (200, 201):
                        logger.info(f"[bold green]Successfully created trump report on {tracker}[/bold green]")
                        return True
                    logger.info(f"[bold red]Failed to create trump report. HTTP Status: {response.status_code}[/bold red]")
                    return False

            except httpx.TimeoutException:
                logger.info("[bold red]Request timed out after 10 seconds[/bold red]")
                return False
            except httpx.RequestError as e:
                logger.info(f"[bold red]HTTP Request failed: {e}[/bold red]")
                return False
            except Exception as e:
                logger.error(f"[bold red]Unexpected error: {e}[/bold red]")
                return False
        else:
            logger.info("[bold yellow]Debug mode enabled, skipping actual trump report creation.[/bold yellow]")
            logger.info(f"[cyan]POST URL: {create_url}[/cyan]")
            logger.info(f"[cyan]Payload: {payload}[/cyan]")
            return True


tracker_class_map: dict[str, Any] = {
    "AURA4K": Aura4K,
    "ASIANCINEMA": AsianCinema,
    "AITHER": Aither,
    "ANTHELION": Anthelion,
    "ALPHARATIO": AlphaRatio,
    "AMIGOSSHARE": AmigosShare,
    "AVISTAZ": AvistaZ,
    "BEYONDHD": BEYONDHD,
    "BITHDTV": BitHDTV,
    "BJSHARE": BJShare,
    "BLUTOPIA": Blutopia,
    "BRASILTRACKER": BrasilTracker,
    "CAPYBARABR": CapybaraBR,
    "CATHODERAYTUBE": CathodeRayTube,
    "CURUPIRA": Curupira,
    "CINEMAZ": CinemaZ,
    "DIGITALCORE": DigitalCore,
    "DARKPEERS": DarkPeers,
    "DRUNKENSLUG": DrunkenSlug,
    "DESITORRENTS": DesiTorrents,
    "EMUWAREZ": Emuwarez,
    "FUNFILE": FunFile,
    "FILELIST": FileList,
    "GREATPOSTERWALL": GreatPosterWall,
    "HDBITS": HDBits,
    "HDSPACE": HDSpace,
    "HDTORRENTS": HDTorrents,
    "HOMIEHELPDESK": HomieHelpDesk,
    "HAWKEUNO": HawkeUno,
    "INFINITYHD": InfinityHD,
    "IPTORRENTS": IPTorrents,
    "IMMORTALSEED": ImmortalSeed,
    "ITATORRENTS": ItaTorrents,
    "LAJIDUI": Lajidui,
    "LOCADORA": Locadora,
    "LASTDIGITALUNDERGROUND": LastDigitalUnderground,
    "LONGPT": LongPT,
    "LST": LST,
    "LATTEAM": LatTeam,
    "LUMINARR": Luminarr,
    "MAKINGOFF": MakingOff,
    "MIDNIGHTSCENE": MidnightScene,
    "MTEAM": MTeam,
    "MORETHANTV": MoreThanTV,
    "NEBULANCE": Nebulance,
    "NORDICQUALITY": NordicQuality,
    "ONLYENCODES": OnlyEncodes,
    "OLDTOONSWORLD": OldToonsWorld,
    "ORPHEUS": Orpheus,
    "PRIVATEHD": PrivateHD,
    "PORTUGAS": Portugas,
    "PTCAFE": PTCafe,
    "PTERCLUB": PTerClub,
    "PTFANS": PTFans,
    "PTGTK": PTGTK,
    "PASSTHEPOPCORN": PassThePopcorn,
    "PTSKIT": Ptskit,
    "PEERGARDEN": PeerGarden,
    "POLISHTORRENT": PolishTorrent,
    "RACING4EVERYONE": Racing4Everyone,
    "RASTASTUGAN": Rastastugan,
    "REELFLIX": ReelFlix,
    "RAILGUNPT": RailgunPT,
    "RETROFLIX": RetroFlix,
    "RETROMOVIESCLUB": RetroMoviesClub,
    "SAMARITANO": Samaritano,
    "SHAREISLAND": ShareIsland,
    "SWARMAZON": Swarmazon,
    "SEEDPOOL": Seedpool,
    "SPEEDAPP": SpeedApp,
    "SKIPTHECOMMERCIALS": SkipTheCommercials,
    "SUIO": Suio,
    "TORRENTHR": TorrentHR,
    "CINEMATIK": Cinematik,
    "TORRENTLEECH": TorrentLeech,
    "THELEACHZONE": TheLeachZone,
    "THEOLDSCHOOL": TheOldSchool,
    "TOTHEGLORY": ToTheGlory,
    "TORRENTEROS": Torrenteros,
    "TVCHAOSUK": TVChaosUK,
    "ULCX": ULCX,
    "UNWALLED": Unwalled,
    "UTOPIA": Utopia,
    "YUSCENE": YUSCENE,
    "ZENITH": Zenith,
}


def get_tracker_comment_hosts(config: dict[str, Any]) -> dict[str, tuple[str, ...]]:
    """Return tracker domains usable when parsing torrent-comment URLs.

    Hosts are metadata of the registered tracker classes, so looking up a
    comment never needs to instantiate every tracker. ``comment_hosts`` or
    the existing ``tracker_urls`` class attribute covers additional domains;
    configured ``base_url`` and ``announce_url`` cover runtime overrides.
    """

    def hostname(value: Any) -> str | None:
        if not isinstance(value, str) or not value:
            return None
        parsed = urlparse(value if "://" in value else f"//{value}")
        return parsed.hostname.lower() if parsed.hostname else None

    trackers_config = config.get("TRACKERS", {})
    tracker_config_map = trackers_config if isinstance(trackers_config, dict) else {}
    tracker_hosts: dict[str, tuple[str, ...]] = {}

    for tracker_name, tracker_class in tracker_class_map.items():
        domains = [resolved_host for value in (getattr(tracker_class, "base_url", ""),) if (resolved_host := hostname(value))]

        for attribute_name in ("comment_hosts", "tracker_urls"):
            values = getattr(tracker_class, attribute_name, ())
            if isinstance(values, str):
                values = (values,)
            if isinstance(values, tuple | list):
                domains.extend(resolved_host for value in values if (resolved_host := hostname(value)))

        tracker_config = tracker_config_map.get(tracker_name, {})
        if isinstance(tracker_config, dict):
            domains.extend(resolved_host for key in ("base_url", "announce_url") if (resolved_host := hostname(tracker_config.get(key, ""))))

        if domains:
            tracker_hosts[tracker_name] = tuple(dict.fromkeys(domains))

    return tracker_hosts


api_trackers: set[str] = {name for name, cls in tracker_class_map.items() if getattr(cls, "auth_type", None) == "unit3d_api"}
other_api_trackers: set[str] = {name for name, cls in tracker_class_map.items() if getattr(cls, "auth_type", None) == "other_api"}
http_trackers: set[str] = {name for name, cls in tracker_class_map.items() if getattr(cls, "auth_type", None) == "cookies"}
