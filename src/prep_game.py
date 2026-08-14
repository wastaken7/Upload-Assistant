# Upload Assistant © 2026 Audionut & wastaken7 — Licensed under UAPL v1.0
import asyncio
import contextlib
import datetime
import html
import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any

import aiofiles
import cli_ui
import httpx

from src.console import logger
from src.igdb import IGDBAPI
from src.meta import Meta
from src.metadata_cache import cache_for, is_cache_miss


def normalize_version(version_str: str) -> str:
    version_str = version_str.strip()
    if not version_str:
        return ""
    if version_str.lower().startswith("v"):
        return "v" + version_str[1:]
    if version_str[0].isdigit():
        return "v" + version_str
    return version_str


def extract_version_from_text(text: str) -> str | None:
    if not text:
        return None

    # 1. Match version/update/build prefixes:
    m = re.search(r"(?i)(?<![a-zA-Z0-9])(?:update|version|ver|build)[.:=\-_\s]*[vV]?(\d+(?:[.\-]\d+)+)(?![a-zA-Z0-9])", text)
    if m:
        return normalize_version(m.group(1))

    m = re.search(r"(?i)(?<![a-zA-Z0-9])(?:update|version|ver|build)[.:=\-_\s]*[vV]?(\d+)(?![a-zA-Z0-9])", text)
    if m:
        return normalize_version(m.group(1))

    m = re.search(r"(?i)(?<![a-zA-Z0-9])[vV](\d+(?:[.\-]\d+)*)(?![a-zA-Z0-9])", text)
    if m:
        return normalize_version(m.group(1))

    # 2. Match isolated version numbers:
    for m in re.finditer(r"(?i)(?<![a-zA-Z0-9])(\d+(?:[.\-]\d+)+)(?![a-zA-Z0-9])", text):
        candidate = m.group(1)
        # Filter out years
        if len(candidate) == 4 and candidate.isdigit():
            val_int = int(candidate)
            if 1900 <= val_int <= 2100:
                continue
        # Filter out resolutions
        if candidate in ("1080", "2160", "4320", "8640", "720", "576", "480"):
            continue
        return normalize_version(candidate)

    return None


def extract_version_from_nfo(nfo_path: str) -> str | None:
    with contextlib.suppress(Exception):
        content = ""
        try:
            with Path(nfo_path).open(encoding="utf-8") as f:
                content = f.read()
        except Exception:
            with Path(nfo_path).open(encoding="latin-1") as f:
                content = f.read()

        lines = content.splitlines()

        # First pass: look for strong patterns
        for line in lines:
            m = re.search(r"(?i)(?<![a-zA-Z0-9])(?:update|version|ver|build)[.:=\-_\s]*[vV]?(\d+(?:[.\-]\d+)+)(?![a-zA-Z0-9])", line)
            if m:
                return normalize_version(m.group(1))
            m = re.search(r"(?i)(?<![a-zA-Z0-9])(?:update|version|ver|build)[.:=\-_\s]*[vV]?(\d+)(?![a-zA-Z0-9])", line)
            if m:
                return normalize_version(m.group(1))

        # Second pass: look for any vX.Y pattern
        for line in lines:
            m = re.search(r"(?i)(?<![a-zA-Z0-9])[vV](\d+(?:[.\-]\d+)+)(?![a-zA-Z0-9])", line)
            if m:
                return normalize_version(m.group(0))

        # Third pass: look for isolated version numbers in context
        for line in lines:
            for m in re.finditer(r"(?i)(?<![a-zA-Z0-9])(\d+(?:[.\-]\d+)+)(?![a-zA-Z0-9])", line):
                candidate = m.group(1)
                if len(candidate) == 4 and candidate.isdigit():
                    val_int = int(candidate)
                    if 1900 <= val_int <= 2100:
                        continue
                if candidate in ("1080", "2160", "4320", "8640", "720", "576", "480"):
                    continue
                if any(w in line.lower() for w in ("version", "ver", "build", "v.", "v ")):
                    return normalize_version(candidate)
    return None


def map_to_clean_code(p_name: str) -> str:
    p_name_norm = p_name.lower()
    nin_term = bytes([110, 105, 110, 116, 101, 110, 100, 111]).decode()
    reverse_map = {
        "playstation 5": "PS5",
        "playstation 4": "PS4",
        "playstation 3": "PS3",
        "playstation 2": "PS2",
        "playstation": "PS1",
        "xbox series": "XSX",
        "xbox series x|s": "XSX",
        "xbox series x/s": "XSX",
        "xbox one": "XONE",
        "xbox 360": "X360",
        "xbox": "XBOX",
        "switch": "SWITCH",
        f"{nin_term} switch": "SWITCH",
        "3ds": "3DS",
        f"{nin_term} 3ds": "3DS",
        "nds": "NDS",
        f"{nin_term} ds": "NDS",
        "wii u": "WIIU",
        "wiiu": "WIIU",
        "wii": "WII",
        "pc": "PC",
        "windows": "PC",
        "mac": "MAC",
        "linux": "LINUX",
    }
    for key, val in reverse_map.items():
        if key in p_name_norm or p_name_norm in key:
            return val
    return p_name.upper()


async def get_7z_path(base_dir: str, config: dict[str, Any] | None = None) -> str | None:
    # 1. Check config for 7z_path
    if config and "DEFAULT" in config:
        config_path = config["DEFAULT"].get("7z_path", "").strip()
        if config_path and Path(config_path).exists():
            return config_path

    # 2. Check system PATH
    sys_7z = shutil.which("7z") or shutil.which("7z.exe")
    if sys_7z:
        return sys_7z

    # 3. Use manager fallback
    with contextlib.suppress(Exception):
        from bin.get_7z import SevenZipBinaryManager

        binary_path = await SevenZipBinaryManager.ensure_7z_binary(base_dir)
        if binary_path and Path(binary_path).exists():
            return binary_path

    return None


async def list_archive_contents_with_7z(archive_path: str, binary_path: str) -> list[str]:
    contents = []
    try:
        cmd = [binary_path, "l", "-slt", archive_path]
        process = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, _ = await process.communicate()
        if process.returncode == 0:
            for line in stdout.decode("utf-8", errors="replace").splitlines():
                if line.startswith("Path = ") and len(line) > 7:
                    path_val = line[7:].strip()
                    # Skip if it is the archive name itself (7z lists archive header)
                    if path_val and path_val.replace("\\", "/").lower() != archive_path.replace("\\", "/").lower():
                        contents.append(path_val)
    except Exception as e:
        logger.debug(f"[yellow]7-Zip: Failed to list archive contents for {archive_path}: {e}[/yellow]")
    return contents


async def detect_platform_from_files(
    filelist: list[str],
    path_to_check: str | None = None,
    base_dir: str | None = None,
    config: dict[str, Any] | None = None,
) -> str | None:
    # Normalize paths to lowercase and use forward slashes
    files_lower = []
    basenames_lower = []
    for f in filelist:
        p = f.replace("\\", "/").lower()
        files_lower.append(p)
        basenames_lower.append(Path(p).name)

    # --- Pre-check archives and ISO contents using 7z if available ---
    archive_exts = (".zip", ".rar", ".7z", ".iso", ".tar", ".gz")
    archives = [f for f in filelist if f.lower().endswith(archive_exts)]
    if archives and base_dir:
        binary_path = await get_7z_path(base_dir, config)
        if binary_path:
            is_7zr = "7zr" in Path(binary_path).name.lower()
            for archive in archives:
                # 7zr fallback only supports 7z archives
                if is_7zr and not archive.lower().endswith(".7z"):
                    continue

                logger.info(f"[cyan]7-Zip: Inspecting contents of archive/ISO: {Path(archive).name}...[/cyan]")
                archive_contents = await list_archive_contents_with_7z(archive, binary_path)
                for path_val in archive_contents:
                    p = path_val.replace("\\", "/").lower()
                    files_lower.append(p)
                    basenames_lower.append(Path(p).name)

    # --- 1. Extension and specific file/folder pattern checks ---

    # Switch
    switch_exts = (".nsp", ".xci", ".nca", ".szs", ".nsz", ".xcz")
    if any(b.endswith(switch_exts) for b in basenames_lower):
        return "SWITCH"

    # 3DS
    three_ds_exts = (".3ds", ".cia", ".cci", ".3dsx")
    if any(b.endswith(three_ds_exts) for b in basenames_lower):
        return "3DS"

    # DS (NDS)
    nds_exts = (".nds", ".srl")
    if any(b.endswith(nds_exts) for b in basenames_lower):
        return "NDS"

    # Wii U
    wiiu_exts = (".wud", ".wux")
    if any(b.endswith(wiiu_exts) for b in basenames_lower):
        return "WIIU"
    # Wii U folder structure check
    if any("/code/app.xml" in f for f in files_lower) or (any(b == "title.tmd" for b in basenames_lower) and any(b == "title.tik" for b in basenames_lower)):
        return "WIIU"

    # Wii
    wii_exts = (".wbfs", ".gcm")
    if any(b.endswith(wii_exts) for b in basenames_lower):
        return "WII"

    # PlayStation 3 (PS3)
    if any("ps3_game" in f for f in files_lower) or any(b == "param.sfo" and "ps3_game" in f for b, f in zip(basenames_lower, files_lower, strict=False)):
        return "PS3"
    if any(b.endswith(".rap") for b in basenames_lower):
        return "PS3"

    # PlayStation Vita
    if any(b.endswith(".vpk") for b in basenames_lower):
        return "PSVITA"

    # PlayStation Portable (PSP)
    if any(b.endswith(".cso") for b in basenames_lower) or any(b == "eboot.pbp" for b in basenames_lower):
        return "PSP"

    # PlayStation 4 / PlayStation 5 / PlayStation 3 PKG check
    pkg_files = [b for b in basenames_lower if b.endswith(".pkg")]
    if pkg_files:
        if any("cusa" in pkg for pkg in pkg_files):
            return "PS4"
        if any("ppsa" in pkg for pkg in pkg_files):
            return "PS5"
        # Check folders/files in path for hints
        all_paths_str = " ".join(files_lower)
        if "ps4" in all_paths_str or "playstation 4" in all_paths_str:
            return "PS4"
        if "ps5" in all_paths_str or "playstation 5" in all_paths_str:
            return "PS5"
        return "PS3"

    # Xbox 360
    if any(b.endswith(".xex") for b in basenames_lower) or any(b == "default.xex" for b in basenames_lower):
        return "X360"
    if any("$systemupdate" in f for f in files_lower):
        return "X360"

    # Xbox (Original)
    if any(b.endswith(".xbe") for b in basenames_lower) or any(b == "default.xbe" for b in basenames_lower):
        return "XBOX"

    # Sega Dreamcast
    dc_exts = (".gdi", ".cdi")
    if any(b.endswith(dc_exts) for b in basenames_lower):
        return "DREAMCAST"

    # PC (Windows)
    pc_dlls = ("steam_api.dll", "steam_api64.dll", "unityplayer.dll", "galaxy64.dll")
    if any(b in pc_dlls for b in basenames_lower):
        return "PC"
    if any("binaries/win64" in f or "binaries/win32" in f or "engine/binaries" in f for f in files_lower):
        return "PC"

    # --- 2. Basename/Path text keyword checks (if no extensions matched) ---
    path_to_search = path_to_check or (filelist[0] if filelist else "")
    if path_to_search:
        basename = Path(path_to_search).name.lower()
        normalized_basename = basename.replace(".", " ").replace("-", " ").replace("_", " ").replace("[", " ").replace("]", " ")

        nin_term = bytes([110, 105, 110, 116, 101, 110, 100, 111]).decode()
        platform_keywords = {
            "PS5": ["ps5", "playstation 5", "playstation5"],
            "PS4": ["ps4", "playstation 4", "playstation4"],
            "PS3": ["ps3", "playstation 3", "playstation3"],
            "PS2": ["ps2", "playstation 2", "playstation2"],
            "PS1": ["ps1", "psx", "playstation 1", "playstation1"],
            "XSX": ["xsx", "xbox series", "xboxseries"],
            "XONE": ["xone", "xbox one", "xboxone"],
            "X360": ["x360", "xbox 360", "xbox360"],
            "XBOX": ["xbox"],
            "SWITCH": ["nsw", "switch", f"{nin_term} switch", f"{nin_term}switch"],
            "3DS": ["3ds", f"{nin_term} 3ds"],
            "NDS": ["nds", f"{nin_term} ds", f"{nin_term}ds", f"{nin_term} ds"],
            "WIIU": ["wii u", "wiiu"],
            "WII": ["wii"],
            "PC": ["pc", "windows", "win"],
            "MAC": ["mac", "macos", "osx"],
            "LINUX": ["linux"],
            "PSP": ["psp"],
            "PSVITA": ["psvita", "ps vita", "vita"],
        }

        for platform_code, keywords in platform_keywords.items():
            for kw in keywords:
                if re.search(rf"\b{re.escape(kw)}\b", normalized_basename):
                    return platform_code

    return None


def resolve_game_filelist(
    meta: Meta,
    videoloc: str,
) -> tuple[str, list[str], str, str]:
    """Scan *videoloc* for game files and update *meta* in-place.
    Prioritizes .exe, then .iso, then compressed archives (.rar, .zip, .7z, etc.),
    and falls back to the largest file.
    """
    filelist: list[str] = []
    if Path(videoloc).is_dir():
        for root, _, files in os.walk(videoloc):
            for file in files:
                filelist.append(str(Path(Path(root) / file).resolve()))  # noqa: PERF401
        filelist = sorted(filelist)
        if not filelist:
            logger.info("[bold red]No game files found!")
            sys.exit(1)

        exe_files = [f for f in filelist if f.lower().endswith(".exe")]
        iso_files = [f for f in filelist if f.lower().endswith(".iso")]
        archive_exts = (".rar", ".zip", ".7z", ".tar", ".gz")
        archive_files = [f for f in filelist if f.lower().endswith(archive_exts)]

        if exe_files:
            videopath = sorted(exe_files, key=os.path.getsize, reverse=True)[0]
        elif iso_files:
            videopath = sorted(iso_files, key=os.path.getsize, reverse=True)[0]
        elif archive_files:
            videopath = sorted(archive_files, key=os.path.getsize, reverse=True)[0]
        else:
            videopath = sorted(filelist, key=os.path.getsize, reverse=True)[0]
    else:
        videopath = videoloc
        filelist.append(videoloc)

    meta.filelist = filelist
    meta.imdb_id = 0

    search_term = Path(filelist[0]).name if filelist else ""
    search_file_folder = "file"
    return videopath, filelist, search_term, search_file_folder


# ---------------------------------------------------------------------------
# Metadata gathering
# ---------------------------------------------------------------------------


async def gather_game_prep(
    meta: Meta,
    videopath: str,
    base_dir: str,
    config: dict[str, Any] | None = None,
) -> None:
    """Query IGDB API for game metadata and populate meta in-place."""
    meta.category = "GAME"
    meta.search_year = ""
    meta.resolution = "Other"
    meta.hfr = False
    meta.sd = 0
    meta.valid_mi_settings = True

    cli_overrides = {
        "title": bool(meta.title),
        "year": ("manual_year" in meta and meta.manual_year) or 0 > 0,
        "platform": bool(meta.manual_platform),
    }

    # Run platform auto-detection early if platform is not manually specified
    if not cli_overrides["platform"]:
        detected = await detect_platform_from_files(meta.filelist, meta.path or videopath, base_dir, config)
        if detected:
            meta.platform = detected
            logger.info(f"[green]Game platform auto-detected from files: {detected}[/green]")

    # Check console game status
    platform = meta.platform
    if platform:
        platform_lower = platform.lower()
        nin_term = bytes([110, 105, 110, 116, 101, 110, 100, 111]).decode()
        console_words = ["ps", "playstation", "xbox", "switch", "3ds", "nds", "wii", f"{nin_term}"]
        meta.console_game = any(word in platform_lower for word in console_words)
    else:
        meta.console_game = False

    # Version extraction/handling logic
    path_to_check = meta.path or videopath
    version = None

    if meta.game_version:
        version = normalize_version(meta.game_version)
        logger.info(f"[green]Game version (manual override): {version}[/green]")
    else:
        # Attempt to extract from directory name first
        if path_to_check:
            search_dir = path_to_check if Path(path_to_check).is_dir() else str(Path(path_to_check).parent)
            if search_dir:
                folder_name = Path(search_dir).name
                version = extract_version_from_text(folder_name)
                if version and meta.debug:
                    logger.info(f"[green]Game version extracted from directory name: {version}[/green]")

        # Attempt to extract from .nfo file if not found in directory name
        if not version:
            nfo_files = [f for f in meta.filelist if f.lower().endswith(".nfo")]
            if path_to_check:
                search_dir = path_to_check if Path(path_to_check).is_dir() else str(Path(path_to_check).parent)
                if Path(search_dir).is_dir():
                    with contextlib.suppress(Exception):
                        for f in (p.name for p in Path(search_dir).iterdir()):
                            if f.lower().endswith(".nfo"):
                                abs_f = str(Path(Path(search_dir) / f).resolve())
                                if abs_f not in nfo_files:
                                    nfo_files.append(abs_f)

            for nfo_path in nfo_files:
                version = extract_version_from_nfo(nfo_path)
                if version:
                    logger.info(f"[green]Game version extracted from NFO file ({Path(nfo_path).name}): {version}[/green]")
                    break

    if version:
        meta.game_version = version

    # Check for Twitch/IGDB API credentials
    client_id = ""
    client_secret = ""
    if config and "DEFAULT" in config:
        client_id = config["DEFAULT"].get("twitch_client_id", "").strip()
        client_secret = config["DEFAULT"].get("twitch_client_secret", "").strip()

    # Fallback to env variables
    if not client_id:
        client_id = os.environ.get("TWITCH_CLIENT_ID", "").strip()
    if not client_secret:
        client_secret = os.environ.get("TWITCH_CLIENT_SECRET", "").strip()

    if not client_id or not client_secret:
        logger.warning("[bold red]Warning: Twitch Client ID or Secret is not configured. Game metadata search will be skipped.[/bold red]")
        return

    # Use title in meta (cleaned folder/file name) or extract from videopath
    title_query = meta.title or meta.filename
    if not title_query and videopath:
        title_query = Path(videopath).stem

    # Clean game release suffixes to get a clean search term for IGDB
    if title_query:
        # Remove trailing group if there is a hyphen
        if "-" in title_query:
            parts = title_query.split("-")
            if len(parts) > 1:
                last_part = parts[-1].strip()
                if len(last_part) < 15 and " " not in last_part:
                    title_query = "-".join(parts[:-1])

        # Replace separators with spaces first to ensure word boundaries work
        title_query = title_query.replace(".", " ").replace("_", " ").replace("-", " ")
        title_query = re.sub(r"\s+", " ", title_query).strip()

        # Remove Update/Patch/Build/Version and everything after
        title_query = re.sub(r"(?i)\b(?:update|patch|build|version)\b.*", "", title_query)
        # Remove vX.X or vX and everything after
        title_query = re.sub(r"(?i)\bv\d+.*", "", title_query)

        # Loop to strip trailing release/platform/language tags from the end of the query
        tags_to_remove = (
            r"(?:nsw|switch|nds|3ds|ps1|ps2|ps3|ps4|ps5|psp|psvita|vita|wii|wiiu|xbox|xbox360|x360|xone|xsx|pc|"
            r"multi\d*|eng|english|fre|french|ger|german|spa|spanish|ita|italian|jpn|japanese|por|portuguese|bra|brazilian|"
            r"proper|repack|readnfo|internal|dvd|rip|iso|god|jb|psn|eshop|rip|cracked|unlocked|crackfix)"
        )
        while True:
            new_query = re.sub(rf"(?i)\s+{tags_to_remove}$", "", title_query)
            if new_query == title_query:
                break
            title_query = new_query

        title_query = re.sub(r"\s+", " ", title_query).strip()

    if not title_query:
        logger.warning("[bold red]Warning: Could not determine game title for metadata search.[/bold red]")
        return

    igdb = IGDBAPI(client_id, client_secret, base_dir)
    selected_game = None

    igdb_manual = meta.igdb_manual
    steam_manual = meta.steam_manual

    # Auto-detect Steam ID from local NFO files if not manually specified
    if not steam_manual and not igdb_manual:
        nfo_files = []
        # Check files in filelist
        for f in meta.filelist:
            if f.lower().endswith(".nfo"):
                nfo_files.append(f)

        # Also check the input directory or directory containing the file
        path_to_check = meta.path or videopath
        if path_to_check:
            search_dir = path_to_check if Path(path_to_check).is_dir() else str(Path(path_to_check).parent)
            if Path(search_dir).is_dir():
                with contextlib.suppress(Exception):
                    for f in (p.name for p in Path(search_dir).iterdir()):
                        if f.lower().endswith(".nfo"):
                            abs_f = str(Path(Path(search_dir) / f).resolve())
                            if abs_f not in nfo_files:
                                nfo_files.append(abs_f)

        # Search for Steam link in found NFO files
        detected_steam_id = None
        for nfo_path in nfo_files:
            try:
                content = ""
                try:
                    async with aiofiles.open(nfo_path, encoding="utf-8") as f:
                        content = await f.read()
                except Exception:
                    async with aiofiles.open(nfo_path, encoding="latin-1") as f:
                        content = await f.read()

                # Search for Steam App URL/ID
                match = re.search(r"store\.steampowered\.com/app/(\d+)", content)
                if match:
                    detected_steam_id = match.group(1)
                    logger.debug(f"[green]Auto-detected Steam ID {detected_steam_id} from NFO file.[/green]")
                    break
            except Exception as e:
                logger.debug(f"[yellow]Debug: Error reading NFO {nfo_path}: {e}[/yellow]")

        if detected_steam_id:
            steam_manual = detected_steam_id
            meta.steam_manual = detected_steam_id

    if igdb_manual:
        logger.info(f"[cyan]Fetching IGDB metadata for ID: {igdb_manual}...[/cyan]")
        selected_game = await igdb.fetch_game_by_id(igdb_manual)
        if not selected_game:
            logger.info(f"[yellow]IGDB: No game found with manual ID '{igdb_manual}'. Falling back to search.[/yellow]")
    elif steam_manual:
        selected_game = await igdb.fetch_game_by_steam_id(steam_manual)
        if not selected_game:
            logger.info(f"[yellow]IGDB: No game found with Steam ID '{steam_manual}'. Falling back to search.[/yellow]")

    if not selected_game:
        results = await igdb.search_game(title_query)
        if not results:
            logger.info(f"[yellow]IGDB: No games found matching '{title_query}'[/yellow]")
            return

        # Sort results based on platform match if platform is known/detected
        if meta.platform and results:
            target_platform = meta.platform.upper().strip()
            matching_results = []
            other_results = []
            for r in results:
                raw_plats = [p.get("name") for p in r.get("platforms", []) if p.get("name")]
                mapped_plats = [map_to_clean_code(p) for p in raw_plats]
                if target_platform in mapped_plats:
                    matching_results.append(r)
                else:
                    other_results.append(r)
            results = matching_results + other_results

        # Choose the correct game
        if len(results) == 1 or meta.unattended:
            selected_game = results[0]
        else:
            # Prompt user to select
            choices = []
            for r in results:
                release_date = r.get("first_release_date")
                year = ""
                if release_date:
                    year = f" ({datetime.datetime.fromtimestamp(release_date, datetime.UTC).year})"

                platforms = [p.get("name") for p in r.get("platforms", []) if p.get("name")]
                platforms_str = f" [{', '.join(platforms)}]" if platforms else ""

                choices.append(f"{r.get('name')}{year}{platforms_str}")

            choices.append("Skip - Don't select any match")

            try:
                choice = cli_ui.ask_choice("Select the correct game from IGDB:", choices=choices)
                if choice != "Skip - Don't use any of these matches" and choice != "Skip - Don't select any match":
                    idx = choices.index(choice)
                    selected_game = results[idx]
            except KeyboardInterrupt:
                logger.info("[yellow]Selection cancelled. Skipping IGDB metadata.[/yellow]")
                return

    if not selected_game:
        logger.info("[yellow]Skipped IGDB metadata selection.[/yellow]")
        return

    # Cache selected game details
    await igdb.cache_game_details(selected_game)

    # Populate metadata
    name = selected_game.get("name")
    if name and not cli_overrides["title"]:
        meta.title = name

    release_date = selected_game.get("first_release_date")
    if release_date and not cli_overrides["year"]:
        dt = datetime.datetime.fromtimestamp(release_date, datetime.UTC)
        year_val = dt.year
        meta.year = year_val
        meta.search_year = year_val
        meta.igdb_first_release_date = dt.strftime("%d/%m/%Y")

    # IGDB rating data (0-100 scale)
    igdb_rating = selected_game.get("rating")
    igdb_rating_count = selected_game.get("rating_count")
    if igdb_rating is not None:
        meta.igdb_rating = round(float(igdb_rating), 1)
    if igdb_rating_count is not None:
        meta.igdb_rating_count = int(igdb_rating_count)

    # Overview / Storyline
    summary = selected_game.get("summary")
    storyline = selected_game.get("storyline")
    overview = summary or storyline or ""
    if overview:
        meta.overview = overview

    # Cover image (poster)
    cover_info = selected_game.get("cover", {})
    cover_url = cover_info.get("url")
    if cover_url:
        if cover_url.startswith("//"):
            cover_url = "https:" + cover_url
        cover_url = cover_url.replace("t_thumb", "t_cover_big")
        meta.artwork_url = cover_url

    # Genres
    genres = [g.get("name") for g in selected_game.get("genres", []) if g.get("name")]
    if genres:
        meta.genres = genres
        meta.keywords = genres

    # Platforms
    if not cli_overrides["platform"]:
        raw_platforms = [p.get("name") for p in selected_game.get("platforms", []) if p.get("name")]
        platforms_mapped = [map_to_clean_code(p) for p in raw_platforms]
        platforms = list(dict.fromkeys(platforms_mapped))

        # If the platform was already auto-detected (or set) and is supported by the game, keep it!
        if meta.platform and meta.platform.upper() in platforms:
            meta.platform = meta.platform.upper()
        else:
            detected_platform = None
            if raw_platforms:
                nin_term = bytes([110, 105, 110, 116, 101, 110, 100, 111]).decode()

                platform_mapping = {
                    "playstation 5": ["ps5", "playstation 5", "playstation5"],
                    "playstation 4": ["ps4", "playstation 4", "playstation4"],
                    "playstation 3": ["ps3", "playstation 3", "playstation3"],
                    "playstation 2": ["ps2", "playstation 2", "playstation2"],
                    "playstation": ["ps1", "psx", "playstation 1", "playstation1"],
                    "xbox series x|s": ["xsx", "xbox series", "xboxseries"],
                    "xbox series x/s": ["xsx", "xbox series", "xboxseries"],
                    "xbox one": ["xone", "xbox one", "xboxone"],
                    "xbox 360": ["x360", "xbox 360", "xbox360"],
                    "xbox": ["xbox"],
                    f"{nin_term} switch": ["nsw", "switch", f"{nin_term} switch", f"{nin_term}switch"],
                    f"{nin_term} 3ds": ["3ds", f"{nin_term} 3ds"],
                    f"{nin_term} ds": ["nds", f"{nin_term} ds"],
                    "wii u": ["wii u", "wiiu"],
                    "wii": ["wii"],
                    "pc (microsoft windows)": ["pc", "windows", "win", "osx", "mac", "linux"],
                    "mac": ["mac", "macos", "osx"],
                    "linux": ["linux"],
                }
                path_to_check = meta.path or videopath or ""
                basename = Path(path_to_check).name.lower()
                normalized_basename = basename.replace(".", " ").replace("-", " ").replace("_", " ").replace("[", " ").replace("]", " ")
                for idx, p_name in enumerate(raw_platforms):
                    p_name_norm = p_name.lower()
                    aliases = []
                    for map_key, map_aliases in platform_mapping.items():
                        if map_key in p_name_norm or p_name_norm in map_key:
                            aliases.extend(map_aliases)
                    aliases.append(p_name_norm)
                    aliases = list(dict.fromkeys(aliases))
                    for alias in aliases:
                        if re.search(rf"\b{re.escape(alias)}\b", normalized_basename):
                            detected_platform = platforms_mapped[idx]
                            break
                    if detected_platform:
                        break
            if detected_platform:
                meta.platform = detected_platform
                logger.info(f"[green]Game platform auto-detected from folder/file name: {detected_platform}[/green]")
            elif len(platforms) == 1:
                meta.platform = platforms[0]
                logger.debug(f"[green]Game platform set to: {platforms[0]}[/green]")

    # Companies
    developers = []
    publishers = []
    for comp_info in selected_game.get("involved_companies", []):
        company = comp_info.get("company", {})
        comp_name = company.get("name")
        if comp_name:
            if comp_info.get("developer"):
                developers.append(comp_name)
            if comp_info.get("publisher"):
                publishers.append(comp_name)

    if developers:
        meta.developer = ", ".join(developers)
    if publishers:
        meta.publisher = ", ".join(publishers)

    # Extract Steam URL
    steam_url = None
    # 1. Check websites (Type 13 = Steam)
    for web in selected_game.get("websites", []):
        if web.get("type") == 13:
            steam_url = web.get("url")
            break
    # 2. Check external_games (Source 1 = Steam)
    if not steam_url:
        for ext in selected_game.get("external_games", []):
            if ext.get("external_game_source") == 1:
                steam_url = ext.get("url")
                if not steam_url and ext.get("uid"):
                    steam_url = f"https://store.steampowered.com/app/{ext.get('uid')}"
                break
    if steam_url:
        meta.steam_url = steam_url

    # Extract Languages
    languages = {}
    for support in selected_game.get("language_supports", []):
        lang_name = support.get("language", {}).get("name")
        support_type = support.get("language_support_type", {}).get("name")
        if lang_name and support_type:
            if lang_name not in languages:
                languages[lang_name] = []
            if support_type not in languages[lang_name]:
                languages[lang_name].append(support_type)
    if languages:
        meta.languages = languages

    # Extract available platforms
    platforms = []
    for platform in selected_game.get("platforms", []):
        platform_name = platform.get("name")
        if platform_name:
            platforms.append(platform_name)
    meta.available_platforms = platforms

    # Extract Steam App ID
    steam_id = None
    if steam_url:
        match = re.search(r"/app/(\d+)", steam_url)
        if match:
            steam_id = match.group(1)

    # Fetch details from Steam if Steam App ID is present
    if steam_id:
        url = "https://store.steampowered.com/api/appdetails"
        params = {"appids": steam_id}
        trackers = [t.upper() for t in meta.trackers]
        target_trackers = {"AMIGOSSHARE", "BRASILTRACKER", "BJSHARE", "CAPYBARABR", "SAMARITANO"}
        if any(t in target_trackers for t in trackers):
            params["l"] = "brazilian"

        try:
            cache = cache_for(base_dir, config)
            cache_key = json.dumps(params, sort_keys=True)
            res_data = await cache.get("steam", "appdetails", cache_key)
            if is_cache_miss(res_data):
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.get(url, params=params)
                if resp.status_code == 200:
                    res_data = resp.json()
                    if isinstance(res_data, dict):
                        await cache.set("steam", "appdetails", cache_key, res_data, negative=not bool(res_data))
                elif resp.status_code == 404:
                    res_data = {}
                    await cache.set("steam", "appdetails", cache_key, res_data, negative=True)
                else:
                    res_data = {}
            if isinstance(res_data, dict) and res_data and steam_id in res_data and res_data[steam_id].get("success"):
                app_data = res_data[steam_id]["data"]

                # Fetch localized pt-BR description from Steam if target tracker is present
                if any(t in target_trackers for t in trackers):
                    desc = app_data.get("short_description") or app_data.get("about_the_game") or app_data.get("detailed_description") or ""
                    # Strip HTML tags
                    desc_clean = re.sub(r"<[^>]+>", "", desc).strip()
                    desc_unescaped = html.unescape(desc_clean)
                    if desc_unescaped:
                        meta.localized_overviews = {"brazilian": desc_unescaped}

                # Extract PC system requirements
                pc_reqs = app_data.get("pc_requirements", {})
                if isinstance(pc_reqs, dict):
                    minimum = pc_reqs.get("minimum", "")
                    recommended = pc_reqs.get("recommended", "")
                    if minimum:
                        meta.requirements_minimum = minimum
                    if recommended:
                        meta.requirements_recommended = recommended
        except Exception as e:
            logger.info(f"[yellow]Steam: Error fetching app details: {e}[/yellow]")

    # Extract Screenshots from IGDB
    igdb_screenshots = selected_game.get("screenshots", [])
    if igdb_screenshots:
        image_list = []
        for screenshot in igdb_screenshots:
            url = screenshot.get("url")
            if url:
                if url.startswith("//"):
                    url = "https:" + url
                # IGDB screenshot URLs typically contain 't_thumb'
                # Convert 't_thumb' to 't_screenshot_med' for img_url, and 't_1080p' for raw/web_url
                img_url = url.replace("t_thumb", "t_screenshot_med")
                raw_url = url.replace("t_thumb", "t_1080p")
                web_url = url.replace("t_thumb", "t_1080p")
                image_list.append({"img_url": img_url, "raw_url": raw_url, "web_url": web_url})
        if image_list:
            meta.image_list = image_list

            tmp_dir = Path(base_dir) / "tmp" / meta.uuid
            Path(tmp_dir).mkdir(parents=True, exist_ok=True)
            image_data_file = Path(tmp_dir) / "image_data.json"
            image_data = {"image_list": image_list, "image_sizes": {}, "tonemapped": False}
            try:
                async with aiofiles.open(image_data_file, "w", encoding="utf-8") as img_file:
                    await img_file.write(json.dumps(image_data, indent=4))
                logger.debug(f"[green]IGDB: Saved {len(image_list)} screenshots to image_data.json[/green]")
            except Exception as e:
                logger.info(f"[yellow]IGDB: Failed to save screenshots to image_data.json: {e}[/yellow]")

    meta.igdb_id = selected_game.get("id", 0)

    # Re-evaluate console_game in case platform was updated/detected
    platform = meta.platform
    if platform:
        platform_lower = platform.lower()
        nin_term = bytes([110, 105, 110, 116, 101, 110, 100, 111]).decode()
        console_words = ["ps", "playstation", "xbox", "switch", "3ds", "nds", "wii", f"{nin_term}"]
        meta.console_game = any(word in platform_lower for word in console_words)
    else:
        meta.console_game = False

    logger.debug(f"[green]IGDB metadata successfully retrieved for game: {meta.title}[/green]")
