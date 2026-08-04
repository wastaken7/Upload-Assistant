#!/usr/bin/env python3
# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import ast
import asyncio
import contextlib
import filecmp
import gc
import json
import os
import platform
import re
import shlex
import shutil
import signal
import sys
import threading
import time
import traceback
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, Protocol, cast
from urllib.parse import urljoin, urlparse

from src.check_requirements import check_dependencies

check_dependencies()

import logging

import aiofiles
import cli_ui  # pyright: ignore[reportMissingImports]
import requests
from torf import Torrent as _Torrent  # pyright: ignore[reportMissingImports,reportUnknownVariableType]

from bin.get_mkbrr import MkbrrBinaryManager
from src.add_comparison import ComparisonManager
from src.args import Args, read_paths_from_stdin
from src.artwork import is_public_http_url, is_valid_cover_image
from src.audio_spectrogram import process_audio_spectrograms
from src.book_prep import detect_newspaper, is_valid_book_language, resolve_book_language
from src.cleanup import cleanup_manager
from src.clients import Clients
from src.cogs.redaction import PathAwareEncoder, Redaction
from src.config_helpers import format_terminal_link
from src.console import current_release_log_path, logger  # pyright: ignore[reportUnknownVariableType]
from src.console import rich_handler as _rich_handler
from src.disc_menus import process_disc_menus
from src.dupe_checking import DupeChecker
from src.early_tasks import cancel_and_drain_early_artifact_tasks, get_early_artifact_tasks, start_early_artifact_tasks
from src.early_tasks import is_usenet_only as _is_usenet_only
from src.get_desc import gen_desc
from src.get_name import NameManager
from src.get_tracker_data import TrackerDataManager
from src.qbitwait import Wait
from src.queuemanage import QueueManager
from src.rehostimages import check_tracker_image_hosts
from src.takescreens import TakeScreensManager, download_artwork_from_meta
from src.temp_paths import artwork_dir, screenshots_dir
from src.torrentcreate import TorrentCreator
from src.trackerhandle import process_trackers
from src.trackers.alpharatio import AlphaRatio
from src.trackers.common import Common
from src.trackers.digitalcore import DigitalCore
from src.trackers.passthepopcorn import PassThePopcorn
from src.trackersetup import TrackerSetup, api_trackers, http_trackers, other_api_trackers, tracker_class_map
from src.trackerstatus import TrackerStatusManager
from src.uphelper import UploadHelper
from src.uploadscreens import UploadScreensManager

base_dir = str(Path(__file__).resolve().parent)
CLI_UI: Any = cli_ui
TORF_Torrent: Any = cast(Any, _Torrent)
RICH_HANDLER: Any = cast(Any, _rich_handler)
TORRENT_CREATOR: Any = cast(Any, TorrentCreator)
CLI_UI.setup(color="always", title="Upload Assistant")


def _parse_version_tuple(value: str) -> tuple[int, ...]:
    """Parse a dotted version string into a tuple for comparison."""
    cleaned = value.strip().lstrip("vV")
    parts: list[int] = []
    for part in cleaned.split("."):
        if not part.isdigit():
            break
        parts.append(int(part))
    return tuple(parts)


class WebUIServer(Protocol):
    def run(self) -> None: ...
    def close(self) -> None: ...


# Global state for shutdown handling (reset via _reset_shutdown_state() for in-process runs)
_shutdown_requested = False
_is_webui_mode = False
_webui_server: WebUIServer | None = None  # Reference to waitress server for graceful shutdown
_shutdown_event = threading.Event()  # Event for coordinating graceful shutdown
_webui_session_id: str | None = None
_webui_run_token: str | None = None


def _reset_shutdown_state() -> None:
    """Reset global shutdown state for clean in-process runs from web UI."""
    global _shutdown_requested, _is_webui_mode, _webui_server, _webui_session_id, _webui_run_token
    _shutdown_requested = False
    _is_webui_mode = False
    _webui_server = None
    _webui_session_id = None
    _webui_run_token = None
    _shutdown_event.clear()


def set_webui_session_id(session_id: str | None, run_token: str | None = None) -> None:
    """Store the active Web UI execution session for in-process preview updates."""
    global _webui_session_id, _webui_run_token
    cleaned = (session_id or "").strip()
    _webui_session_id = cleaned or None
    cleaned_run_token = (run_token or "").strip()
    _webui_run_token = cleaned_run_token or None


def _publish_webui_preview_target(path: str, meta_uuid: str | None = None) -> None:
    """Push the current queue item to the Web UI execution preview, when active."""
    if not _is_webui_mode or not _webui_session_id or not _webui_run_token or not path:
        return
    try:
        from web_ui.server import set_execution_preview_target

        set_execution_preview_target(_webui_session_id, _webui_run_token, path, meta_uuid)
    except Exception:
        return


def _handle_shutdown_signal(signum: int, _frame: Any) -> None:
    """Handle SIGTERM/SIGINT for graceful shutdown."""
    global _shutdown_requested, _webui_server
    signal_name = "SIGTERM" if signum == signal.SIGTERM else "SIGINT"

    if not _shutdown_requested:
        _shutdown_requested = True
        logger.info(f"\n[yellow]Received {signal_name}, shutting down gracefully...[/yellow]")

        # Signal shutdown event (for webui thread coordination)
        _shutdown_event.set()

        # If running webui, close the server (main thread handles exit via event)
        if _webui_server is not None:
            with contextlib.suppress(Exception):
                _webui_server.close()
        else:
            # Non-webui mode: raise to let asyncio handle task cancellation
            raise KeyboardInterrupt
    else:
        # Second signal = force exit
        logger.info("[red]Forced exit[/red]")
        sys.exit(1)


# ── Restore built-in data/ files when a Docker volume mount hides them ──
# The Dockerfile copies the original data/ tree to defaults/data/ so that
# volume mounts over /Upload-Assistant/data/ don't lose critical files
# (__init__.py, version.py, example_config.py, templates/).
_data_dir = Path(base_dir) / "data"
_defaults_data_dir = Path(base_dir) / "defaults" / "data"

# Directories that should never be copied into user-facing data/
_SKIP_DIRS = {"__pycache__", ".mypy_cache", ".ruff_cache"}

# Built-in metadata files that should track the image version even when
# /Upload-Assistant/data is a persistent volume from an older container.
_ALWAYS_SYNC_ROOT_FILES = {"version.py"}

if Path(_defaults_data_dir).is_dir():
    Path(_data_dir).mkdir(parents=True, exist_ok=True)
    _restored_count = 0
    _synced_count = 0
    _restore_errors: list[str] = []
    # Walk the defaults tree and copy anything missing in the live data dir.
    # Never overwrite user files (config.py, cookies/, tags.json, etc.).
    # Root version.py is image metadata, not user config, so keep it current.
    for dirpath, dirnames, filenames in os.walk(_defaults_data_dir):
        # Prune unwanted directories in-place so os.walk skips them entirely
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]

        rel_dir = os.path.relpath(dirpath, _defaults_data_dir)
        target_dir = Path(_data_dir) / rel_dir if rel_dir != "." else _data_dir
        try:
            Path(target_dir).mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            _restore_errors.append(f"mkdir {rel_dir}: {exc}")
            continue  # skip this subtree if we can't create the directory
        for fname in filenames:
            # Skip bytecode and cache files
            if fname.endswith((".pyc", ".pyo")):
                continue
            target_file = Path(target_dir) / fname
            src_file = Path(dirpath) / fname
            should_sync = False
            if rel_dir == "." and fname in _ALWAYS_SYNC_ROOT_FILES and Path(target_file).exists():
                try:
                    should_sync = not filecmp.cmp(src_file, target_file, shallow=False)
                except OSError:
                    should_sync = True
            if not Path(target_file).exists() or should_sync:
                try:
                    shutil.copy2(src_file, target_file)
                    if should_sync:
                        _synced_count += 1
                    else:
                        _restored_count += 1
                except OSError as exc:
                    _restore_errors.append(f"{Path(rel_dir) / fname}: {exc}")
    if _restored_count:
        logger.info(f"Restored {_restored_count} built-in file(s) into data/ from defaults.", extra={"markup": False})
    if _synced_count:
        logger.info(f"Synced {_synced_count} built-in metadata file(s) into data/ from defaults.", extra={"markup": False})
    if _restore_errors:
        logger.warning(f"[red]Warning: failed to restore {len(_restore_errors)} file(s) into data/:[/red]")
        for _err in _restore_errors[:5]:
            logger.info(f"[red]  {_err}[/red]")
        if len(_restore_errors) > 5:
            logger.info(f"[red]  ... and {len(_restore_errors) - 5} more[/red]")
        logger.info("[yellow]Hint: ensure the mounted data/ directory is writable by the container user.[/yellow]")
        logger.info("[yellow]  e.g. on the host: chown -R 1000:1000 /path/to/data[/yellow]")

_config_path = Path(_data_dir) / "config.py"

# Detect -webui or --webui forms, including --webui=host:port
_is_webui_arg = any((arg == "-webui" or arg == "--webui" or arg.startswith("-webui=") or arg.startswith("--webui=")) for arg in sys.argv)
# Auto-create config.py from example on first WebUI start
if _is_webui_arg and not Path(_config_path).exists():
    _example_config_path = Path(_data_dir) / "example_config.py"
    if Path(_example_config_path).exists():
        logger.info("No config.py found. Creating default config from example_config.py...", extra={"markup": False})
        try:
            shutil.copy2(_example_config_path, _config_path)
            logger.info("Default config created successfully!", extra={"markup": False})
        except Exception as e:
            logger.info(f"Failed to create default config: {e}", extra={"markup": False})
            logger.info("Continuing without config file...", extra={"markup": False})

from src.book_prep import sanitize_book_author, sanitize_book_language
from src.meta import Meta
from src.prep import Prep

# Enable ANSI colors on Windows
_use_colors = True
if sys.platform == "win32":
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        # Enable VIRTUAL_TERMINAL_PROCESSING
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
    except Exception:
        _use_colors = False

# Color codes (empty strings if colors not supported)
_RED = "\033[91m" if _use_colors else ""
_YELLOW = "\033[93m" if _use_colors else ""
_GREEN = "\033[92m" if _use_colors else ""
_RESET = "\033[0m" if _use_colors else ""


def _print_config_error(error_type: str, message: str, lineno: int | None = None, text: str | None = None, offset: int | None = None, suggestion: str | None = None) -> None:
    """Print a formatted config error message."""
    logger.info(f"{_RED}{error_type} in config.py:{_RESET}", extra={"markup": False})
    if lineno:
        logger.info(f"{_RED}  Line {lineno}: {message}{_RESET}", extra={"markup": False})
        if text:
            logger.info(f"{_YELLOW}    {text.rstrip()}{_RESET}", extra={"markup": False})
            if offset:
                logger.info(f"{_YELLOW}    {' ' * (offset - 1)}^{_RESET}", extra={"markup": False})
    else:
        logger.info(f"{_RED}  {message}{_RESET}", extra={"markup": False})
    if suggestion:
        logger.info(f"{_GREEN}  Suggestion: {suggestion}{_RESET}", extra={"markup": False})
    logger.info(f"\n{_RED}Reference: https://github.com/Audionut/Upload-Assistant/blob/master/data/example_config.py{_RESET}", extra={"markup": False})


config: dict[str, Any]

if Path(_config_path).exists():
    try:
        from data.config import config as _imported_config  # pyright: ignore[reportMissingImports,reportUnknownVariableType]

        config = cast(dict[str, Any], _imported_config)
        parser: Any = Args(config)
        client = Clients(config)
        name_manager = NameManager(config)
        tracker_data_manager = TrackerDataManager(config)
        takescreens_manager = TakeScreensManager(config)
        uploadscreens_manager = UploadScreensManager(config)
    except SyntaxError as e:
        _print_config_error("Syntax error", e.msg if e.msg else "Invalid syntax", lineno=e.lineno, text=e.text, offset=e.offset)
        logger.info(f"\n{_RED}Common syntax issues:{_RESET}", extra={"markup": False})
        logger.info(f"{_YELLOW}  - Missing comma between dictionary items{_RESET}", extra={"markup": False})
        logger.info(f"{_YELLOW}  - Missing closing bracket, brace, quote or comma{_RESET}", extra={"markup": False})
        logger.info(f"{_YELLOW}  - Unclosed string (missing quote at end){_RESET}", extra={"markup": False})
        sys.exit(1)
    except NameError as e:
        # Extract line number from traceback
        import traceback

        tb = traceback.extract_tb(sys.exc_info()[2])
        lineno = tb[-1].lineno if tb else None
        text = tb[-1].line if tb else None

        # Check for common mistakes
        suggestion = None
        error_str = str(e)
        if "'true'" in error_str.lower():
            suggestion = "Use 'True' (capital T) instead of 'true'"
        elif "'false'" in error_str.lower():
            suggestion = "Use 'False' (capital F) instead of 'false'"
        elif "'null'" in error_str.lower() or "'none'" in error_str.lower():
            suggestion = "Use 'None' (capital N) instead of 'null' or 'none'"
        elif "is not defined" in error_str:
            # Extract the undefined name from the error message
            import re as _re

            match = _re.search(r"name '([^']+)' is not defined", error_str)
            if match:
                undefined_name = match.group(1)
                suggestion = f"Did you forget quotes? Try \"{undefined_name}\" instead of '{undefined_name}'"

        _print_config_error("Name error", str(e), lineno=lineno, text=text, suggestion=suggestion)
        sys.exit(1)
    except TypeError as e:
        import traceback

        tb = traceback.extract_tb(sys.exc_info()[2])
        lineno = tb[-1].lineno if tb else None
        text = tb[-1].line if tb else None

        _print_config_error("Type error", str(e), lineno=lineno, text=text)
        logger.info(f"\n{_RED}Common type issues:{_RESET}", extra={"markup": False})
        logger.info(f"{_YELLOW}  - Using unhashable type as dictionary key{_RESET}", extra={"markup": False})
        logger.info(f"{_YELLOW}  - Incorrect data structure nesting{_RESET}", extra={"markup": False})
        sys.exit(1)
    except Exception as e:
        import traceback

        tb = traceback.extract_tb(sys.exc_info()[2])
        lineno = tb[-1].lineno if tb else None
        text = tb[-1].line if tb else None

        _print_config_error("Error", str(e), lineno=lineno, text=text)
        sys.exit(1)
else:
    logger.info(f"{_RED}Configuration file 'config.py' not found.{_RESET}", extra={"markup": False})
    logger.info(f"{_RED}Please ensure the file is located at: {_YELLOW}{_config_path}{_RESET}", extra={"markup": False})
    logger.info(f"{_RED}Follow the setup instructions: https://github.com/Audionut/Upload-Assistant{_RESET}", extra={"markup": False})
    sys.exit(1)


async def merge_meta(meta: Meta, saved_meta: dict[str, Any]) -> dict[str, Any]:
    """Merges saved metadata with the current meta, respecting overwrite rules."""
    overwrite_list = [
        "anon",
        "asin",
        "audiobook_bitrate",
        "audiobook_duration_formatted",
        "audiobook_duration",
        "author",
        "blu",
        "book_asin",
        "book_author",
        "book_isbn",
        "book_language_iso",
        "book_language",
        "book_publisher",
        "book_title",
        "category",
        "client",
        "comic",
        "debug",
        "desc",
        "description_file",
        "description_link",
        "draft",
        "dual_audio",
        "dupe",
        "freeleech",
        "game_region",
        "game_subcategory",
        "game_system",
        "game_version",
        "hardcoded_subs",
        "hdb",
        "igdb_manual",
        "imdb",
        "imghost",
        "isbn",
        "keywords",
        "magazine",
        "mal",
        "manga",
        "manual_edition",
        "manual_episode",
        "manual_platform",
        "manual_season",
        "manual_source",
        "manual_type",
        "manual_year",
        "manual",
        "modq",
        "narrator",
        "newspaper",
        "no_aka",
        "no_dub",
        "no_season",
        "no_seed",
        "no_tag",
        "no_year",
        "nohash",
        "openlibrary",
        "personalrelease",
        "platform",
        "ptp",
        "qbit_cat",
        "qbit_tag",
        "region",
        "screens",
        "skip_imghost_upload",
        "steam_manual",
        "title",
        "tmdb_manual",
        "torrent_creation",
        "trackers",
        "tvmaze_manual",
        "type",
        "unattended",
        "webdv",
        "year",
    ]
    sanitized_saved_meta: dict[str, Any] = {}
    for key, value in saved_meta.items():
        clean_key = key.strip().strip("'").strip('"')
        if clean_key in overwrite_list:
            if clean_key in meta and getattr(meta, clean_key, None) is not None:
                sanitized_saved_meta[clean_key] = meta[clean_key]
                logger.debug(f"Overriding {clean_key} with meta value: {meta[clean_key]}")
            else:
                sanitized_saved_meta[clean_key] = value
        else:
            sanitized_saved_meta[clean_key] = value
    meta.update(sanitized_saved_meta)
    sanitize_book_language(meta)
    sanitize_book_author(meta)
    return sanitized_saved_meta


async def print_progress(message: str, interval: int = 10) -> None:
    """Prints a progress message every `interval` seconds until cancelled."""
    try:
        while True:
            await asyncio.sleep(interval)
            logger.info(message)
    except asyncio.CancelledError:
        pass


def update_oeimg_to_onlyimage() -> None:
    """Update all img_host_* values from 'oeimg' to 'onlyimage' in the config file."""
    config_path = f"{base_dir}/data/config.py"
    with Path(config_path).open(encoding="utf-8") as f:
        content = f.read()

    new_content = re.sub(r"(['\"]img_host_\d+['\"]\s*:\s*)['\"]oeimg['\"]", r"\1'onlyimage'", content)
    new_content = re.sub(r"(['\"])(oeimg_api)(['\"]\s*:)", r"\1onlyimage_api\3", new_content)

    if new_content != content:
        with Path(config_path).open("w", encoding="utf-8") as f:
            f.write(new_content)
        logger.info("[green]Updated 'oeimg' to 'onlyimage' and 'oeimg_api' to 'onlyimage_api' in config.py[/green]")
    else:
        logger.info("[yellow]No 'oeimg' or 'oeimg_api' found to update in config.py[/yellow]")


async def validate_tracker_logins(meta: Meta, trackers: list[str] | str | None = None) -> None:
    if "tracker_status" not in meta:
        meta.tracker_status = {}

    if not trackers:
        return

    # Filter trackers that are in both the list and tracker_class_map
    valid_trackers = [tracker for tracker in trackers if tracker in tracker_class_map and tracker in http_trackers]
    # RETROFLIX/PASSTHEPOPCORN are not HTTP trackers but need validation
    if "RETROFLIX" in trackers:
        valid_trackers.append("RETROFLIX")
    if "PASSTHEPOPCORN" in trackers:
        valid_trackers.append("PASSTHEPOPCORN")

    if valid_trackers:

        async def validate_single_tracker(tracker_name: str) -> tuple[str, bool]:
            """Validate credentials for a single tracker."""
            try:
                status_dict = meta.tracker_status
                if tracker_name not in status_dict:
                    status_dict[tracker_name] = {}

                tracker_class = tracker_class_map[tracker_name](config=config)
                logger.debug(f"[cyan]Validating {tracker_name} credentials...[/cyan]")
                if tracker_name == "RETROFLIX":
                    login = await tracker_class.api_test(meta)
                elif tracker_name == "PASSTHEPOPCORN":
                    login = await tracker_class.get_anti_csrf_token(meta)
                else:
                    login = await tracker_class.validate_credentials(meta)

                if not login:
                    status_dict[tracker_name]["skipped"] = True

                return tracker_name, login
            except Exception as e:
                status_dict = meta.tracker_status
                logger.error(f"[red]Error validating {tracker_name}: {e}[/red]")
                status_dict[tracker_name]["skipped"] = True
                return tracker_name, False

        # Run all tracker validations concurrently
        await asyncio.gather(*[validate_single_tracker(tracker) for tracker in valid_trackers])


async def _prompt_book_meta(meta: Meta) -> None:
    """Prompt the user to fill in missing BOOK metadata fields (title, author, year, language).

    Runs only in interactive (attended) mode.  When any field is filled in the
    torrent name is rebuilt so the confirmation screen and the per-tracker
    uploads reflect the new values.
    """
    book_required_fields = ["title", "author", "year", "book_language"]
    if meta.audiobook and ("CAPYBARABR" in meta.trackers or "ZENITH" in meta.trackers):
        book_required_fields.append("narrator")
    book_missing: list[str] = []
    for f in book_required_fields:
        val = getattr(meta, f, None)
        if not val or str(val).strip().lower() in ("", "none", "null"):
            book_missing.append(f)
        elif f == "book_language":
            iso = meta.book_language_iso
            if not is_valid_book_language(str(val), iso):
                book_missing.append(f)
    has_artwork = bool(is_valid_cover_image(meta.artwork_path) or _is_http_url(meta.artwork_url))
    if not has_artwork:
        book_missing.append("artwork")

    if not book_missing:
        return

    if meta.unattended:
        logger.info(
            f"[yellow]BOOK upload: the following required fields are missing: "
            f"{', '.join(book_missing)}. "
            f"Re-run with -btitle / -author / -year / -blang / --book-cover to supply them, "
            f"or trackers that require them will be skipped.[/yellow]"
        )
        return

    logger.info("\n[bold yellow]The following fields are required:[/bold yellow]")
    name_needs_rebuild = False
    try:
        for field in book_missing:
            prompt_label = "language" if field == "book_language" else ("cover artwork (path to image file or URL)" if field == "artwork" else field)
            if field == "book_language":
                while True:
                    value = (CLI_UI.ask_string("Enter language (leave blank to skip): ") or "").strip()
                    if not value:
                        break

                    full, iso = resolve_book_language(value)
                    if is_valid_book_language(full, iso):
                        meta.book_language = full
                        meta.book_language_iso = iso
                        name_needs_rebuild = True
                        break
                    logger.info("[red]Invalid language. Please try again.[/red]")
            elif field == "year":
                while True:
                    value = (CLI_UI.ask_string("Enter year (leave blank to skip): ") or "").strip()
                    if not value:
                        break
                    if value.isdigit() and len(value) == 4 and 1000 <= int(value) <= 3000:
                        meta.year = int(value)
                        meta.search_year = value
                        name_needs_rebuild = True
                        break
                    logger.info("[red]Invalid year (must be a 4-digit number between 1000 and 3000). Please try again.[/red]")
            elif field == "artwork":
                while True:
                    value = (CLI_UI.ask_string("Enter path to cover artwork image (or public image URL) for BOOK: ") or "").strip()
                    if not value:
                        logger.info("[red]Artwork is required for BOOK uploads. Please enter a valid file path or image URL.[/red]")
                        continue
                    if _is_http_url(value):
                        meta.artwork_url = value
                        break
                    path_obj = Path(value).expanduser()
                    if path_obj.is_file():
                        meta.artwork_path = str(path_obj.resolve())
                        break
                    logger.info("[red]Invalid artwork path or URL. The file does not exist or URL is invalid. Please try again.[/red]")
            else:
                value = (CLI_UI.ask_string(f"Enter {prompt_label} (leave blank to skip): ") or "").strip()
                if value:
                    meta[field] = value
                    name_needs_rebuild = True
    except EOFError:
        logger.info("[yellow]Input cancelled — continuing with missing book fields.[/yellow]")
        name_needs_rebuild = False

    sanitize_book_language(meta)
    sanitize_book_author(meta)

    # Rebuild the torrent name so the confirmation screen and upload reflect the new values
    if name_needs_rebuild:
        detect_newspaper(meta)
        meta.name_notag, meta.name, meta.clean_name, meta.potential_missing = await name_manager.get_name(meta)


async def _prompt_game_meta(meta: Meta) -> None:
    """Prompt the user to fill in missing GAME metadata fields (title, year, platform).

    Runs only in interactive (attended) mode. When any field is filled, the
    torrent name is rebuilt so the confirmation screen and the per-tracker
    uploads reflect the new values.
    """
    game_required_fields = ["title", "year", "platform", "game_version", "game_subcategory"]
    game_missing: list[str] = []
    for f in game_required_fields:
        val = getattr(meta, f, None)
        if not val or str(val).strip().lower() in ("", "none", "null") or (f == "platform" and "," in str(val)):
            game_missing.append(f)
    if not game_missing:
        pass
    elif meta.unattended:
        logger.info(
            f"[yellow]GAME upload: the following required fields are missing: "
            f"{', '.join(game_missing)}. "
            f"Re-run with appropriate CLI arguments, "
            f"or trackers that require them will be skipped.[/yellow]"
        )
        return
    else:
        logger.info("\n[bold yellow]The following fields are required:[/bold yellow]")
        name_needs_rebuild = False
        try:
            for field in game_missing:
                if field == "year":
                    while True:
                        value = (CLI_UI.ask_string("Enter year (leave blank to skip): ") or "").strip()
                        if not value:
                            break
                        if value.isdigit() and len(value) == 4 and 1000 <= int(value) <= 3000:
                            meta.year = int(value)
                            meta.search_year = value
                            name_needs_rebuild = True
                            break
                        logger.info("[red]Invalid year (must be a 4-digit number between 1000 and 3000). Please try again.[/red]")
                elif field == "platform":
                    try:
                        value = CLI_UI.ask_choice(
                            "Select target platform: (can be manually set with -plat / --platform)",
                            choices=["pc", "mac", "linux", "ps5", "ps4", "ps3", "ps2", "xbox", "x360", "xone", "xsx", "switch", "3ds", "nds", "wiiu", "wii"],
                            sort=False,
                        )
                    except EOFError:
                        value = ""

                    if value:
                        meta[field] = value
                        name_needs_rebuild = True
                elif field == "game_version":
                    value = (CLI_UI.ask_string("Enter game version (e.g., 1.15) (leave blank to skip): ") or "").strip()
                    if value:
                        from src.prep_game import normalize_version

                        meta[field] = normalize_version(value)
                        name_needs_rebuild = True

                elif field == "game_subcategory":
                    subcategory_choices = ["full_game (Full Game)", "full_game_dlc (Full Game + DLC)", "dlc (DLC only)", "update (Update only)"]
                    subcategory_values = {
                        "full_game (Full Game)": "full_game",
                        "full_game_dlc (Full Game + DLC)": "full_game_dlc",
                        "dlc (DLC only)": "dlc",
                        "update (Update only)": "update",
                    }
                    choice = CLI_UI.ask_choice("Select game subcategory (can be manually set with -gsc / --game-subcategory):", choices=subcategory_choices, sort=False)
                    meta.game_subcategory = subcategory_values.get(choice, "full_game")
                    name_needs_rebuild = True

                else:
                    value = (CLI_UI.ask_string(f"Enter {field} (leave blank to skip): ") or "").strip()
                    if value:
                        meta[field] = value
                        name_needs_rebuild = True
        except EOFError:
            logger.info("[yellow]Input cancelled — continuing with missing game fields.[/yellow]")
            name_needs_rebuild = False

        # Rebuild the torrent name so the confirmation screen and upload reflect the new values
        if name_needs_rebuild:
            meta.name_notag, meta.name, meta.clean_name, meta.potential_missing = await name_manager.get_name(meta)

    # BJSHARE-specific game metadata prompts
    trackers = [t.upper() for t in meta.trackers]
    if "BJSHARE" not in trackers or meta.unattended:
        return

    try:
        # Console-specific fields
        pc_platforms = {"PC", "MAC", "LINUX", "EMULATOR", ""}
        platform = meta.platform.upper().strip()
        is_console = platform not in pc_platforms

        if is_console:
            needs_game_system = platform in {"PS1", "PS2", "PSP", "WII", "WIIU", "X360"}
            needs_game_region = platform in {
                "3DS",
                "NDS",
                "PSVITA",
                "PS1",
                "PS2",
                "PS3",
            }
            needs_container = platform in {"SWITCH", "X360"}

            if needs_game_system and not meta.game_system:
                system_choices = ["PAL", "NTSC-U", "NTSC-J", "Skip"]
                if meta.platform.upper() == "PSP":
                    system_choices = ["FREE", "NTSC", "PAL", "Skip"]
                try:
                    choice = CLI_UI.ask_choice(
                        "BJSHARE: Select game system (TV standard):",
                        choices=system_choices,
                    )
                    if choice != "Skip":
                        meta.game_system = choice
                except EOFError:
                    pass

            if needs_game_region and not meta.game_region:
                region_choices = ["USA", "EUR", "JPN", "Skip"]
                try:
                    choice = CLI_UI.ask_choice(
                        "BJSHARE: Select game region:",
                        choices=region_choices,
                    )
                    if choice != "Skip":
                        meta.game_region = choice
                except EOFError:
                    pass

            if needs_container:
                container_choices = ["NSP", "XCI", "NSZ", "XCZ", "Skip"]
                if meta.game_system == "X360":
                    container_choices = ["LT", "JTAG/RGH", "Skip"]

                if meta.container.upper() not in container_choices:
                    try:
                        choice = CLI_UI.ask_choice(
                            "BJSHARE: Select container format ('Destravamento'):",
                            choices=container_choices,
                        )
                        if choice != "Skip":
                            meta.container = choice
                    except EOFError:
                        pass

    except EOFError:
        logger.info("[yellow]Input cancelled — continuing with current game fields.[/yellow]")


MUSIC_REQUIRED_FIELDS = ("artist", "album", "year", "media", "release_type")
MUSIC_MEDIA_CHOICES = ("CD", "WEB", "Vinyl", "DVD", "BD", "Soundboard", "SACD", "DAT", "Cassette")
MUSIC_RELEASE_TYPE_CHOICES = (
    "Album",
    "Soundtrack",
    "EP",
    "Anthology",
    "Compilation",
    "Sampler",
    "Single",
    "Demo",
    "Live album",
    "Split",
    "Remix",
    "Bootleg",
    "Interview",
    "Mixtape",
    "Concert recording",
    "DJ Mix",
    "Unknown",
)


def _music_field(meta: Meta, field: str) -> Any:
    """Read a normalized release field, falling back to the shared Meta view."""
    release = meta.music_release if isinstance(meta.music_release, dict) else {}
    fields = release.get("fields", {}) if isinstance(release.get("fields", {}), dict) else {}
    entry = fields.get(field, {}) if isinstance(fields.get(field, {}), dict) else {}
    value = entry.get("value")
    if value not in (None, ""):
        return value
    return {"artist": meta.artist, "album": meta.title, "year": meta.year, "media": meta.source, "cover_url": meta.artwork_url}.get(field, "")


def _music_field_source(meta: Meta, field: str) -> str:
    release = meta.music_release if isinstance(meta.music_release, dict) else {}
    fields = release.get("fields", {}) if isinstance(release.get("fields", {}), dict) else {}
    entry = fields.get(field, {}) if isinstance(fields.get(field, {}), dict) else {}
    return str(entry.get("source", ""))


def _set_music_field(meta: Meta, field: str, value: str | int, *, source: str = "user") -> None:
    """Keep prompted values and their provenance available to tracker adapters."""
    if not isinstance(meta.music_release, dict):
        meta.music_release = {"fields": {}}
    fields = meta.music_release.setdefault("fields", {})
    if not isinstance(fields, dict):
        meta.music_release["fields"] = {}
        fields = meta.music_release["fields"]
    fields[field] = {"value": value, "source": source, "confidence": 1.0}
    if field == "artist":
        meta.artist = str(value)
        artists = [part.strip() for part in re.split(r"\s+&\s+", str(value)) if part.strip()]
        fields["artists"] = {"value": artists or [str(value)], "source": source, "confidence": 1.0}
    elif field == "album":
        meta.title = str(value)
    elif field == "year":
        meta.year = int(value)
        meta.search_year = str(value)
    elif field == "media":
        meta.source = str(value)
    elif field == "cover_url":
        meta.artwork_url = str(value)


def _is_http_url(value: Any) -> bool:
    parsed = urlparse(str(value or "").strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


MUSIC_COVER_MAX_BYTES = 10 * 1024 * 1024
MUSIC_COVER_MAX_REDIRECTS = 3


def _is_public_music_cover_url(value: Any) -> bool:
    """Allow artwork downloads only from public HTTP(S) hosts."""
    return is_public_http_url(str(value or ""))


def _download_music_cover(url: str) -> bytes | None:
    """Download a bounded image while validating every redirect destination."""
    current_url = url
    for _ in range(MUSIC_COVER_MAX_REDIRECTS + 1):
        if not _is_public_music_cover_url(current_url):
            logger.warning("[yellow]MUSIC: refused artwork download from a non-public URL.[/yellow]")
            return None
        response: requests.Response | None = None
        try:
            response = requests.get(current_url, timeout=30, allow_redirects=False, stream=True)
            if response.is_redirect:
                location = response.headers.get("Location", "")
                if not location:
                    return None
                current_url = urljoin(current_url, location)
                continue
            response.raise_for_status()
            content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            if not content_type.startswith("image/"):
                logger.warning(f"[yellow]MUSIC: artwork URL returned unsupported content type {content_type or 'unknown'}.[/yellow]")
                return None
            content_length = response.headers.get("Content-Length")
            if content_length and (not content_length.isdigit() or int(content_length) > MUSIC_COVER_MAX_BYTES):
                logger.warning("[yellow]MUSIC: artwork download exceeds the 10 MiB limit.[/yellow]")
                return None
            content = bytearray()
            for chunk in response.iter_content(chunk_size=64 * 1024):
                content.extend(chunk)
                if len(content) > MUSIC_COVER_MAX_BYTES:
                    logger.warning("[yellow]MUSIC: artwork download exceeds the 10 MiB limit.[/yellow]")
                    return None
            return bytes(content)
        except requests.RequestException as error:
            logger.warning(f"[yellow]MUSIC: could not download artwork for image hosting: {error}[/yellow]")
            return None
        finally:
            if response is not None:
                response.close()
    logger.warning("[yellow]MUSIC: artwork URL exceeded the redirect limit.[/yellow]")
    return None


async def _write_music_snapshot(meta: Meta) -> None:
    path = Path(meta.base_dir) / "tmp" / str(meta.uuid) / "music_release.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    async with aiofiles.open(path, "w", encoding="utf-8") as file:
        await file.write(json.dumps(meta.music_release, indent=2, cls=PathAwareEncoder))


def _music_cover_allowed_hosts(config: Mapping[str, Any], trackers: Iterable[Any]) -> list[str]:
    """Return image hosts accepted by DigitalCore and every selected constrained tracker."""
    approved_hosts = set(getattr(DigitalCore(config=config), "approved_image_hosts", ()))
    for tracker_name in trackers:
        tracker_class = tracker_class_map.get(str(tracker_name).upper())
        if tracker_class is None:
            continue
        tracker_hosts = getattr(tracker_class(config=config), "approved_image_hosts", None)
        if tracker_hosts:
            approved_hosts &= {str(host) for host in tracker_hosts}
    return sorted(approved_hosts)


async def _host_music_cover(meta: Meta, uploadscreens_manager: UploadScreensManager, allowed_hosts: list[str] | None = None) -> None:
    """Host MUSIC artwork and publish it through the shared artwork API."""
    if meta.debug:
        logger.info("[yellow]MUSIC debug: image-host upload skipped.[/yellow]")
        return
    if meta.skip_imghost_upload:
        logger.info("[yellow]MUSIC: image-host upload is disabled; provide a hosted artwork URL.[/yellow]")
        return

    cache_path = Path(meta.base_dir) / "tmp" / str(meta.uuid) / "covers.json"
    try:
        if cache_path.is_file():
            cached = json.loads(await asyncio.to_thread(cache_path.read_text, encoding="utf-8"))
            cached_cover = cached[0] if isinstance(cached, list) and cached else {}
            cached_url = cached_cover.get("raw_url", "") if isinstance(cached_cover, dict) else ""
            if _is_http_url(cached_url):
                meta.artwork_url = str(cached_url)
                meta.hosted_artwork = cached
                _set_music_field(meta, "cover_url", meta.artwork_url, source="external")
                return
    except (OSError, ValueError, TypeError) as error:
        logger.debug(f"[yellow]MUSIC: ignored unusable artwork cache: {error}[/yellow]")

    artwork_path = Path(str(meta.artwork_path or ""))
    if not artwork_path.is_file() and _is_http_url(meta.artwork_url):
        artwork_path = artwork_dir(meta.base_dir, str(meta.uuid)) / "music_cover.jpg"
        content = await asyncio.to_thread(_download_music_cover, meta.artwork_url)
        if content is None:
            return

        try:
            artwork_path.parent.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(artwork_path.write_bytes, content)
            meta.artwork_path = str(artwork_path)
        except OSError as error:
            logger.warning(f"[yellow]MUSIC: could not save downloaded artwork for image hosting: {error}[/yellow]")
            return
    if not is_valid_cover_image(artwork_path):
        logger.warning("[yellow]MUSIC: local artwork is not a valid supported image.[/yellow]")
        return

    try:
        uploaded, _ = await uploadscreens_manager.upload_screens(meta, 1, 1, 0, 1, [str(artwork_path)], {}, allowed_hosts=allowed_hosts)
    except Exception as error:
        logger.warning(f"[yellow]MUSIC: artwork host upload failed: {error}[/yellow]")
        return
    if not uploaded or not _is_http_url(uploaded[0].get("raw_url")):
        logger.warning("[yellow]MUSIC: image host did not return a usable artwork URL.[/yellow]")
        return

    meta.artwork_url = str(uploaded[0]["raw_url"])
    meta.hosted_artwork = uploaded
    _set_music_field(meta, "cover_url", meta.artwork_url, source="external")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiofiles.open(cache_path, "w", encoding="utf-8") as file:
        await file.write(json.dumps(uploaded, indent=2))
    await _write_music_snapshot(meta)


async def _ensure_valid_book_artwork(meta: Meta) -> bool:
    """Ensure every BOOK upload has a local, decodable image before tracker checks."""
    if is_valid_cover_image(meta.artwork_path):
        return True

    if not _is_http_url(meta.artwork_url):
        return False

    destination = artwork_dir(meta.base_dir, meta.uuid) / "manual_cover.jpg"
    if await download_artwork_from_meta(meta, str(destination), force=True):
        return is_valid_cover_image(meta.artwork_path)
    return False


async def _prompt_music_meta(meta: Meta) -> None:
    """Ask for minimum Orpheus music metadata, never technical stream fields."""
    required = list(MUSIC_REQUIRED_FIELDS)
    missing = [
        field
        for field in required
        if (field == "cover_url" and not _is_http_url(_music_field(meta, field))) or (field != "cover_url" and not str(_music_field(meta, field) or "").strip())
    ]
    has_artwork = bool(is_valid_cover_image(meta.artwork_path) or (_is_http_url(meta.artwork_url) or _is_http_url(_music_field(meta, "cover_url"))))
    if not has_artwork and "artwork" not in missing:
        missing.append("artwork")

    conflicts = meta.music_release.get("conflicts", {}) if isinstance(meta.music_release, dict) else {}
    contextual: list[str] = []
    if isinstance(conflicts, dict) and conflicts.get("year") and "year" not in missing:
        contextual.append("year")
    if (isinstance(conflicts, dict) and conflicts.get("edition_year") and "edition_year" not in missing) or (
        _music_field(meta, "edition") and (not _music_field(meta, "edition_year") or _music_field_source(meta, "edition_year") == "file_tag")
    ):
        contextual.append("edition_year")
    if isinstance(conflicts, dict) and conflicts.get("artist"):
        contextual.append("artist")
    fields_to_prompt = list(dict.fromkeys([*missing, *contextual]))
    if not fields_to_prompt:
        return
    if meta.unattended:
        logger.info(
            f"[yellow]MUSIC upload: metadata requiring confirmation: {', '.join(fields_to_prompt)}. The tracker upload will be skipped until required values are supplied.[/yellow]"
        )
        return

    logger.info("\n[bold yellow]MUSIC metadata required or requiring confirmation:[/bold yellow]")
    changed = False
    labels = {"artist": "main artist(s), separated by &", "album": "album title", "year": "original release year", "edition_year": "edition/remaster year"}
    try:
        for field in fields_to_prompt:
            if field in labels:
                if field in {"year", "edition_year"}:
                    while True:
                        current = str(_music_field(meta, field) or "")
                        prompt = f"Enter {labels[field]}" + (f" (current: {current})" if current else "") + " (leave blank to keep/skip): "
                        value = (CLI_UI.ask_string(prompt) or "").strip()
                        if not value:
                            break
                        if value.isdigit() and len(value) == 4 and 1000 <= int(value) <= 3000:
                            _set_music_field(meta, field, int(value))
                            changed = True
                            break
                        logger.info("[red]Invalid year (must be a 4-digit number between 1000 and 3000).[/red]")
                else:
                    value = (CLI_UI.ask_string(f"Enter {labels[field]} (leave blank to skip): ") or "").strip()
                    if value:
                        _set_music_field(meta, field, value)
                        changed = True
            elif field == "media":
                value = CLI_UI.ask_choice("Select source media:", choices=list(MUSIC_MEDIA_CHOICES), sort=False)
                if value:
                    _set_music_field(meta, field, value)
                    changed = True
            elif field == "release_type":
                value = CLI_UI.ask_choice("Select release type:", choices=list(MUSIC_RELEASE_TYPE_CHOICES), sort=False)
                if value:
                    _set_music_field(meta, field, value)
                    changed = True
            elif field in ("artwork", "cover_url"):
                while True:
                    value = (CLI_UI.ask_string("Enter path to cover artwork image (or public image URL) for MUSIC: ") or "").strip()
                    if not value:
                        logger.info("[red]Artwork is required for MUSIC uploads. Please enter a valid file path or image URL.[/red]")
                        continue
                    if _is_http_url(value):
                        _set_music_field(meta, "cover_url", value)
                        meta.artwork_url = value
                        changed = True
                        break
                    path_obj = Path(value).expanduser()
                    if is_valid_cover_image(path_obj):
                        meta.artwork_path = str(path_obj.resolve())
                        _set_music_field(meta, "cover_url", meta.artwork_path, source="user")
                        changed = True
                        break
                    logger.info("[red]Invalid artwork path or URL. The file does not exist or URL is invalid. Please try again.[/red]")
    except EOFError:
        logger.info("[yellow]Input cancelled — continuing with missing music fields.[/yellow]")
        return

    if changed:
        await _write_music_snapshot(meta)
        year = f" [{meta.year}]" if meta.year else ""
        media = str(_music_field(meta, "media") or "")
        meta.name_notag = f"{meta.artist} - {meta.title}{year} [{media} {meta.format}]".strip()
        meta.name_notag, meta.name, meta.clean_name, meta.potential_missing = await name_manager.get_name(meta)


def book_screens(meta: Meta, min_successful_uploads: int) -> tuple[int, int]:
    """Count non-poster PNG screenshots for a BOOK upload and cap the upload minimum.

    Args:
        meta: The metadata dictionary (needs ``base_dir`` and ``uuid``).
        min_successful_uploads: The configured minimum number of successful image uploads.

    Returns:
        A ``(actual_screens, capped_min)`` tuple where *actual_screens* is the
        number of non-poster PNGs found and *capped_min* is
        ``min(min_successful_uploads, actual_screens)`` so the upload loop never
        requires more images than actually exist.
    """
    screenshot_files = list(screenshots_dir(meta.base_dir, meta.uuid).glob("*.png"))
    actual_screens = len(screenshot_files)
    capped_min = min(min_successful_uploads, actual_screens)
    return actual_screens, capped_min


async def process_meta(meta: Meta, base_dir: str) -> bool:
    """Process the metadata for each queued path."""
    if not meta.imghost:
        meta.imghost = config["DEFAULT"]["img_host_1"]
        try:
            has_oeimg_config = any(config["DEFAULT"].get(key) == "oeimg" for key in config["DEFAULT"] if key.startswith("img_host_"))
            if has_oeimg_config:
                logger.info("[red]oeimg is now onlyimage, your config is being updated[/red]")
                update_oeimg_to_onlyimage()
        except Exception as e:
            logger.error(f"[red]Error checking image hosts: {e}[/red]")
            return False

    if not meta.unattended:
        ua = config["DEFAULT"].get("auto_mode", False)
        if str(ua).lower() == "true":
            meta.unattended = True
            logger.info("[yellow]Running in Auto Mode")
    prep = Prep(screens=meta.screens, img_host=meta.imghost, config=config)
    try:
        meta = await prep.gather_prep(meta=meta, mode="cli")
    except Exception as e:
        logger.info(f"Error in gather_prep: {e}")
        logger.info(traceback.format_exc())
        return False

    # Load covers.json if it exists and not already present in meta
    covers_file = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/covers.json"
    if Path(covers_file).exists() and not meta.hosted_artwork:
        try:
            async with aiofiles.open(covers_file, encoding="utf-8") as f:
                content = await f.read()
                loaded_covers: list[dict[str, Any]] | None = json.loads(content)
                if isinstance(loaded_covers, list):
                    meta.hosted_artwork = loaded_covers
                    logger.debug(f"[green]Loaded {len(loaded_covers)} hosted artwork records from covers.json")
        except Exception as e:
            logger.debug(f"[red]Error loading covers.json into meta.hosted_artwork: {e}")

    parser: Any = Args(config)
    helper: Any = UploadHelper(config)

    raw_trackers: list[str] | str = meta.trackers
    if isinstance(raw_trackers, list):
        raw_trackers_list = raw_trackers
        trackers = [t.strip().upper() for t in raw_trackers_list if t.strip()]
    else:
        trackers = [t.strip().upper() for t in raw_trackers.split(",") if t.strip()] if raw_trackers != "" else []
    meta.trackers = trackers

    if isinstance(meta.trackers_remove, str) and meta.trackers_remove:
        remove_list = [t.strip().upper() for t in meta.trackers_remove.split(",")]
        for tracker in remove_list:
            if tracker in meta.trackers:
                meta.trackers.remove(tracker)

    # The category is final after gather_prep.  Remove incompatible trackers
    # before generating tracker-specific names, prompting for confirmation, or
    # validating their credentials.  The later status/upload stages retain the
    # same check as a defensive guard for tracker lists changed after this point.
    TrackerSetup(config=config).filter_unsupported_trackers(meta)

    meta.name_notag, meta.name, meta.clean_name, meta.potential_missing = await name_manager.get_name(meta)

    logger.debug(f"Trackers list before editing: {meta.trackers}")
    async with aiofiles.open(f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/meta.json", "w", encoding="utf-8") as f:
        await f.write(json.dumps(meta.to_dict(), indent=4, cls=PathAwareEncoder))
    _publish_webui_preview_target(cast(str, meta.path or ""), meta.uuid or None)

    # For BOOK category, certain trackers (e.g. CAPYBARABR) require title, author, year and language.
    # Prompt here - on the shared meta - so the data flows into every tracker's upload
    # and into get_name (which runs again below if any field was filled in).
    if meta.category == "BOOK":
        await _prompt_book_meta(meta)
        while not await _ensure_valid_book_artwork(meta):
            if meta.unattended:
                logger.info("[yellow]BOOK upload: no valid cover could be obtained. Skipping all selected trackers.[/yellow]")
                meta.trackers = []
                break
            meta.artwork_path = ""
            meta.artwork_url = ""
            await _prompt_book_meta(meta)

    if meta.category == "GAME":
        await _prompt_game_meta(meta)

    if meta.category == "MUSIC":
        await _prompt_music_meta(meta)

    meta = await gen_desc(meta, takescreens_manager, uploadscreens_manager)

    editargs_tracking: tuple[str, ...] = ()
    previous_trackers = meta.trackers
    try:
        confirm = await helper.get_confirmation(meta)
    except EOFError:
        logger.info("\n[red]Exiting on user request (Ctrl+C)[/red]")
        await cleanup_manager.cleanup()
        cleanup_manager.reset_terminal()
        sys.exit(1)
    while confirm is False:
        try:
            editargs_str = CLI_UI.ask_string("Input args that need correction e.g. (--tag NTb --category tv --tmdb 12345)")
        except EOFError:
            logger.info("\n[red]Exiting on user request (Ctrl+C)[/red]")
            await cleanup_manager.cleanup()
            cleanup_manager.reset_terminal()
            sys.exit(1)

        if editargs_str == "continue":
            break

        if not editargs_str or not editargs_str.strip():
            logger.info("[yellow]No input provided. Please enter arguments, type `continue` to continue or press Ctrl+C to exit.[/yellow]")
            continue

        try:
            editargs = tuple(shlex.split(editargs_str))
        except Exception:
            logger.info("[red]Bad input detected[/red]")
            confirm = False
            continue
        # Tracks multiple edits
        editargs_tracking = editargs_tracking + editargs
        # Carry original args over, let parse handle duplicates
        original_args = meta.item_args if meta.item_args is not None else list(sys.argv[1:])
        meta, _help, _before_args = cast(tuple[Meta, Any, Any], parser.parse(list(original_args) + list(editargs_tracking), meta))
        if not meta.trackers:
            meta.trackers = previous_trackers
        if isinstance(meta.trackers, str):
            if "," in meta.trackers:
                meta.trackers = [t.strip().upper() for t in meta.trackers.split(",")]
            else:
                meta.trackers = [meta.trackers.strip().upper()]
        else:
            meta.trackers = [t.strip().upper() for t in meta.trackers if t]
        logger.debug(f"Trackers list during edit process: {meta.trackers}")
        meta.edit = True
        meta = await prep.gather_prep(meta=meta, mode="cli")
        TrackerSetup(config=config).filter_unsupported_trackers(meta)
        meta.name_notag, meta.name, meta.clean_name, meta.potential_missing = await name_manager.get_name(meta)
        async with aiofiles.open(f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/meta.json", "w", encoding="utf-8") as f:
            await f.write(json.dumps(meta.to_dict(), indent=4, cls=PathAwareEncoder))
        _publish_webui_preview_target(cast(str, meta.path or ""), meta.uuid or None)
        try:
            confirm = await helper.get_confirmation(meta)
        except EOFError:
            logger.info("\n[red]Exiting on user request (Ctrl+C)[/red]")
            await cleanup_manager.cleanup()
            cleanup_manager.reset_terminal()
            sys.exit(1)

    if meta.remove_trackers:
        removed: list[str] = []
        remove_trackers_list = [t for t in meta.remove_trackers if t] if isinstance(meta.remove_trackers, list) else [str(meta.remove_trackers)]
        current_trackers = meta.trackers if isinstance(meta.trackers, list) else [meta.trackers]
        for tracker in remove_trackers_list:
            if tracker in current_trackers:
                if meta.debug:
                    logger.debug(f"[DEBUG] Would have removed {tracker} found in client")
                else:
                    current_trackers.remove(tracker)
                    removed.append(tracker)
        meta.trackers = current_trackers
        if removed:
            logger.info(f"[yellow]Removing trackers already in your client: {', '.join(removed)}[/yellow]")
    if not meta.trackers:
        logger.info("[red]No trackers remain after removal.[/red]")
        successful_trackers = 0
        meta.skip_uploading = 10

    else:
        logger.info(f"Processing for upload: [green]{meta.name}[/green]...")

        # reset trackers after any removals
        trackers = meta.trackers

        for tracker in [
            "ASIANCINEMA",
            "AITHER",
            "AMIGOSSHARE",
            "BJSHARE",
            "BRASILTRACKER",
            "CAPYBARABR",
            "CURUPIRA",
            "DARKPEERS",
            "FUNFILE",
            "GREATPOSTERWALL",
            "HAWKEUNO",
            "INFINITYHD",
            "LAJIDUI",
            "LASTDIGITALUNDERGROUND",
            "LONGPT",
            "LATTEAM",
            "MAKINGOFF",
            "ONLYENCODES",
            "PTCAFE",
            "PTGTK",
            "PTSKIT",
            "RAILGUNPT",
            "SAMARITANO",
            "SHAREISLAND",
            "SPEEDAPP",
            "SUIO",
            "TORRENTEROS",
            "TVCHAOSUK",
            "ULCX",
        ]:
            if tracker in trackers:
                status_dict = meta.tracker_status.setdefault(tracker, {})
                status_dict["skip_upload"] = meta.unattended_audio_skip or meta.unattended_subtitle_skip

        await asyncio.sleep(0.2)
        async with aiofiles.open(f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/meta.json", "w", encoding="utf-8") as f:
            await f.write(json.dumps(meta.to_dict(), indent=4, cls=PathAwareEncoder))
        _publish_webui_preview_target(cast(str, meta.path or ""), meta.uuid or None)
        await asyncio.sleep(0.2)

        try:
            await validate_tracker_logins(meta, trackers)
            await asyncio.sleep(0.2)
        except Exception as e:
            logger.warning(f"[yellow]Warning: Tracker validation encountered an error: {e}[/yellow]")

        successful_trackers = await TrackerStatusManager(config=config).process_all_trackers(meta)

        if meta.trackers_pass is not None:
            meta.skip_uploading = meta.trackers_pass
        else:
            tracker_pass_checks = config["DEFAULT"].get("tracker_pass_checks")
            if isinstance(tracker_pass_checks, (int, str)):
                meta.skip_uploading = int(tracker_pass_checks)
            else:
                meta.skip_uploading = 1

    skip_uploading = meta.skip_uploading
    skip_uploading_int = skip_uploading if skip_uploading else 0

    if successful_trackers < skip_uploading_int and not meta.debug:
        logger.info(f"[red]Not enough successful trackers ({successful_trackers}/{skip_uploading_int}). No uploads being processed.[/red]")
        return True

    meta.we_are_uploading = True
    common = Common(config)
    if meta.site_check:
        tracker_status = cast(dict[str, dict[str, Any]], meta.tracker_status)
        for tracker in meta.trackers:
            upload_status = tracker_status.get(tracker, {}).get("upload", False)
            if not upload_status:
                if tracker == "AITHER" and meta.aither_trumpable and len(meta.aither_trumpable) > 0:
                    pass
                else:
                    continue
            if tracker not in tracker_status:
                continue

            log_path = f"{base_dir}{'/' + 'tmp' + '/'}{tracker}_search_results.json"
            if not await common.path_exists(log_path):
                await common.makedirs(str(Path(log_path).parent))

            search_data: list[dict[str, Any]] = []
            if Path(log_path).exists():
                try:
                    async with aiofiles.open(log_path, encoding="utf-8") as f:
                        content = await f.read()
                        loaded: Any = json.loads(content) if content.strip() else []
                        search_data = [e for e in loaded if isinstance(e, dict)] if isinstance(loaded, list) else []
                except Exception:
                    search_data = []

            existing_uuids = {entry.get("uuid") for entry in search_data}

            if meta.uuid not in existing_uuids:
                search_entry: dict[str, Any] = {
                    "uuid": meta.uuid,
                    "path": meta.path,
                    "imdb_id": meta.imdb_id,
                    "tmdb_id": meta.tmdb_id,
                    "tvdb_id": meta.tvdb_id,
                    "mal_id": meta.mal_id,
                    "tvmaze_id": meta.tvmaze_id,
                }
                if tracker == "AITHER":
                    search_entry["trumpable"] = meta.aither_trumpable
                search_data.append(search_entry)

                async with aiofiles.open(log_path, "w", encoding="utf-8") as f:
                    await f.write(json.dumps(search_data, indent=4))
        meta.we_are_uploading = False
        return True

    # Prep normally starts these while metadata and screenshots are being
    # generated. Keep this fallback for paths which bypass normal prep.
    early_artifact_tasks = get_early_artifact_tasks(meta.uuid) or start_early_artifact_tasks(meta, client, config)
    early_base_torrent_task, early_usenet_prepare_task = early_artifact_tasks

    filename: str = meta.title
    bdmv_filename = meta.filename
    bdinfo = meta.bdinfo
    file_list = [str(p) for p in meta.filelist if str(p)]
    videopath: str = ""
    if file_list:
        videopath = file_list[0]
    elif meta.is_disc == "HDDVD" and meta.discs:
        videopath = meta.discs[0].get("largest_evo", "")
    logger.debug(f"Processing {filename} for upload.....")

    meta.frame_overlay = config["DEFAULT"].get("frame_overlay", False)
    tracker_status_map = cast(dict[str, dict[str, Any]], meta.tracker_status)
    for tracker in ["AVISTAZ", "CINEMAZ", "PRIVATEHD"]:
        upload_status = tracker_status_map.get(tracker, {}).get("upload", False)
        if tracker in meta.trackers and meta.frame_overlay and upload_status is True:
            meta.frame_overlay = False
            logger.info("[yellow]AVISTAZ, CINEMAZ, and PRIVATEHD do not allow frame overlays. Frame overlay will be disabled for this upload.[/yellow]")

    bdmv_mi_created = False
    for tracker in ["ANTHELION", "DIGITALCORE", "HAWKEUNO", "LOCADORA"]:
        upload_status = tracker_status_map.get(tracker, {}).get("upload", False)
        if tracker in trackers and upload_status is True and not bdmv_mi_created:
            await common.get_bdmv_mediainfo(meta)
            bdmv_mi_created = True

    progress_task = asyncio.create_task(print_progress("[yellow]Still processing, please wait...", interval=10))
    try:
        if not meta.manual_frames:
            meta.manual_frames = ""
        manual_frames = meta.manual_frames

        if meta.comparison:
            await ComparisonManager(meta, config).add_comparison()

        else:
            image_data_file = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/image_data.json"
            if Path(image_data_file).exists() and not meta.image_list:
                try:
                    async with aiofiles.open(image_data_file, encoding="utf-8") as img_file:
                        content = await img_file.read()
                        image_data = cast(dict[str, Any], json.loads(content)) if content.strip() else {}

                        if "image_list" in image_data and not meta.image_list:
                            meta.image_list = image_data["image_list"]
                            logger.debug(f"[cyan]Loaded {len(image_data['image_list'])} previously saved image links")

                        if "image_sizes" in image_data and not meta.image_sizes:
                            meta.image_sizes = image_data["image_sizes"]
                            logger.debug("[cyan]Loaded previously saved image sizes")

                        if "tonemapped" in image_data and not meta.tonemapped:
                            meta.tonemapped = image_data["tonemapped"]
                            logger.debug("[cyan]Loaded previously saved tonemapped status[/cyan]")

                except Exception as e:
                    logger.info(f"[yellow]Could not load saved image data: {e!s}")

            if meta.is_disc:
                menus_data_file = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/menu_images.json"
                if Path(menus_data_file).exists():
                    try:
                        async with aiofiles.open(menus_data_file, encoding="utf-8") as menus_file:
                            content = await menus_file.read()
                            menu_image_file = cast(dict[str, Any], json.loads(content)) if content.strip() else {}

                            if "menu_images" in menu_image_file and not meta.menu_images:
                                meta.menu_images = menu_image_file["menu_images"]
                                logger.debug(f"[cyan]Loaded {len(menu_image_file['menu_images'])} previously saved disc menus")

                    except Exception as e:
                        logger.info(f"[yellow]Could not load saved menu image data: {e!s}")
                elif meta.path_to_menu_screenshots or config["DEFAULT"].get("auto_dvd_menus", False):
                    await process_disc_menus(meta, config)

            if meta.audio_spectrogram or meta.audio_spectrogram_tracks or config["DEFAULT"].get("add_audio_spectrogram", False):
                try:
                    await process_audio_spectrograms(meta, config, uploadscreens_manager)
                except Exception as e:
                    logger.error(f"[red]Error processing audio spectrograms: {e}[/red]")

            # Take Screenshots
            try:
                # Keep the later upload count in sync with screenshots removed
                # through the Web UI review while this run awaited confirmation.
                from src.screenshot_review import target_count

                meta.screens = target_count(Path(meta.base_dir) / "tmp" / meta.uuid, meta.screens)
                if meta.category == "MUSIC":
                    logger.debug("[cyan]MUSIC: skipping video screenshots and MediaInfo-dependent image processing.[/cyan]")
                elif meta.is_disc == "BDMV":
                    use_vs = meta.vapoursynth
                    try:
                        await takescreens_manager.disc_screenshots(
                            meta,
                            bdmv_filename,
                            bdinfo,
                            meta.uuid,
                            base_dir,
                            use_vs,
                            meta.image_list,
                            meta.ffdebug,
                            0,
                            cleanup_after_capture=False,
                        )
                    except asyncio.CancelledError as e:
                        await cleanup_screenshot_temp_files(meta)
                        await asyncio.sleep(0.1)
                        await cleanup_manager.cleanup()
                        gc.collect()
                        cleanup_manager.reset_terminal()
                        raise Exception("Error during screenshot capture") from e
                    except Exception as e:
                        await cleanup_screenshot_temp_files(meta)
                        await asyncio.sleep(0.1)
                        await cleanup_manager.cleanup()
                        gc.collect()
                        cleanup_manager.reset_terminal()
                        raise Exception(f"Error during screenshot capture: {e}") from e

                elif meta.is_disc == "DVD":
                    try:
                        await takescreens_manager.dvd_screenshots(
                            meta,
                            disc_num=0,
                            num_screens=0,
                            retry_cap=False,
                            cleanup_after_capture=False,
                        )
                    except asyncio.CancelledError as e:
                        await cleanup_screenshot_temp_files(meta)
                        await asyncio.sleep(0.1)
                        await cleanup_manager.cleanup()
                        gc.collect()
                        cleanup_manager.reset_terminal()
                        raise Exception("Error during screenshot capture") from e
                    except Exception as e:
                        await cleanup_screenshot_temp_files(meta)
                        await asyncio.sleep(0.1)
                        await cleanup_manager.cleanup()
                        gc.collect()
                        cleanup_manager.reset_terminal()
                        raise Exception(f"Error during screenshot capture: {e}") from e

                elif meta.category != "MUSIC":
                    try:
                        logger.debug(f"videopath: {videopath}, filename: {filename}, meta: {meta.uuid}, base_dir: {base_dir}, manual_frames: {manual_frames}")

                        await takescreens_manager.screenshots(
                            videopath,
                            filename,
                            meta.uuid,
                            base_dir,
                            meta,
                            manual_frames=manual_frames,  # Pass additional kwargs directly
                            cleanup_after_capture=False,
                        )
                    except asyncio.CancelledError as e:
                        await cleanup_screenshot_temp_files(meta)
                        await asyncio.sleep(0.1)
                        await cleanup_manager.cleanup()
                        gc.collect()
                        cleanup_manager.reset_terminal()
                        raise Exception("Error during screenshot capture") from e
                    except Exception as e:
                        logger.info(traceback.format_exc())
                        await cleanup_screenshot_temp_files(meta)
                        await asyncio.sleep(0.1)
                        await cleanup_manager.cleanup()
                        gc.collect()
                        cleanup_manager.reset_terminal()
                        if "workers" in str(e):
                            logger.info("[red]max workers issue, see https://github.com/wastaken7/Upload-Assistant/blob/development/docs/ffmpeg-max-workers-issues.md[/red]")
                        raise Exception(f"Error during screenshot capture: {e}") from e

            except asyncio.CancelledError as e:
                await cleanup_screenshot_temp_files(meta)
                await asyncio.sleep(0.1)
                await cleanup_manager.cleanup()
                gc.collect()
                cleanup_manager.reset_terminal()
                raise Exception("Error during screenshot capture") from e
            except Exception as e:
                await cleanup_screenshot_temp_files(meta)
                await asyncio.sleep(0.1)
                await cleanup_manager.cleanup()
                gc.collect()
                cleanup_manager.reset_terminal()
                raise Exception("Error during screenshot capture") from e
            finally:
                await asyncio.sleep(0.1)
                gc.collect()
                cleanup_manager.reset_terminal()

            if "image_list" not in meta:
                meta.image_list = []
            if meta.category == "MUSIC":
                allowed_hosts = _music_cover_allowed_hosts(config, cast(list[Any], meta.trackers))
                if not allowed_hosts:
                    logger.warning("[yellow]MUSIC: no image host is approved by all selected trackers.[/yellow]")
                    return False
                await _host_music_cover(meta, uploadscreens_manager, allowed_hosts)
            manual_frames_str = meta.manual_frames
            if isinstance(manual_frames_str, str):
                manual_frames_list = [f.strip() for f in manual_frames_str.split(",") if f.strip()]
                manual_frames_count = len(manual_frames_list)
                logger.debug(f"Manual frames entered: {manual_frames_count}")
            else:
                manual_frames_count = 0
            if manual_frames_count > 0:
                meta.screens = manual_frames_count
            cutoff = meta.cutoff
            # Remote images can be reviewed in the WebUI.  Replacements and
            # additions remain local until this normal hosting stage, even if
            # the original remote list already satisfies the cutoff.
            from src.screenshot_review import staged_remote_uploads

            reviewed_uploads = staged_remote_uploads(Path(meta.base_dir) / "tmp" / meta.uuid, cast(list[dict[str, Any]], meta.image_list or []))
            if (len(meta.image_list) < cutoff or reviewed_uploads) and meta.skip_imghost_upload is False and meta.category not in ("GAME", "MUSIC"):
                # Validate and (if needed) rehost images to tracker-approved hosts before uploading any new screenshots.
                trackers_with_image_host_requirements = {
                    "AURA4K",
                    "BEYONDHD",
                    "DIGITALCORE",
                    "GREATPOSTERWALL",
                    "HAWKEUNO",
                    "MORETHANTV",
                    "ONLYENCODES",
                    "PASSTHEPOPCORN",
                    "SKIPTHECOMMERCIALS",
                    "TVCHAOSUK",
                }

                relevant_trackers = [t for t in cast(list[Any], meta.trackers) if isinstance(t, str) and t in trackers_with_image_host_requirements and t in tracker_class_map]

                # Prefer a configured host accepted by all relevant trackers.  If that is
                # not possible, keep processing the compatible trackers and skip only
                # those for which the user has no acceptable configured host.
                allowed_hosts: list[str] | None = None
                if relevant_trackers:
                    try:
                        tracker_instances = {tracker_name: tracker_class_map[tracker_name](config=config) for tracker_name in relevant_trackers}

                        logger.debug(f"[cyan]Image host debug: meta.imghost={meta.imghost} img_host_1={config['DEFAULT'].get('img_host_1')}[/cyan]")
                        logger.debug(f"[cyan]Image host debug: relevant_trackers={relevant_trackers}[/cyan]")

                        default_cfg_obj = config.get("DEFAULT", {})
                        default_cfg: dict[str, Any] = cast(dict[str, Any], default_cfg_obj) if isinstance(default_cfg_obj, dict) else {}
                        configured_hosts: list[str] = []
                        for host_index in range(1, 10):
                            host_key = f"img_host_{host_index}"
                            if host_key in default_cfg:
                                host = default_cfg.get(host_key)
                                if host and host not in configured_hosts:
                                    configured_hosts.append(str(host))

                        logger.debug(f"[cyan]Image host debug: configured_hosts={configured_hosts}[/cyan]")

                        approved_sets: list[set[str]] = []
                        all_known = True
                        for tracker_name in relevant_trackers:
                            tracker_instance = tracker_instances[tracker_name]
                            approved_hosts = getattr(tracker_instance, "approved_image_hosts", None)
                            if not approved_hosts:
                                all_known = False
                                break
                            if isinstance(approved_hosts, (list, set, tuple)):
                                approved_hosts_list = [str(host) for host in cast(Iterable[Any], approved_hosts)]
                                approved_host_set = set(approved_hosts_list)
                                # GreatPosterWall can import any public URL with its tracker API,
                                # then serves it from its approved KShare host.  Its configured
                                # image hosts are therefore valid sources, not final destinations.
                                if getattr(tracker_instance, "can_rehost_unapproved_images", False) and getattr(tracker_instance, "api_key", ""):
                                    approved_host_set.update(configured_hosts)
                                approved_sets.append(approved_host_set)
                            else:
                                all_known = False
                                break

                            logger.debug(f"[cyan]Image host debug: {tracker_name}.approved_image_hosts={approved_hosts_list}[/cyan]")

                        if all_known and approved_sets and configured_hosts:
                            common_hosts: set[str] = set()
                            for host_set in approved_sets:
                                if not common_hosts:
                                    common_hosts = set(host_set)
                                else:
                                    common_hosts &= host_set
                            common_configured_hosts = [h for h in configured_hosts if h in common_hosts]

                            logger.debug(f"[cyan]Image host debug: common_hosts={sorted(common_hosts)}[/cyan]")
                            logger.debug(f"[cyan]Image host debug: common_configured_hosts={common_configured_hosts}[/cyan]")

                            # A shared configured host is ideal: upload the common image
                            # list once and use it for every compatible tracker.
                            if common_configured_hosts:
                                allowed_hosts = common_configured_hosts
                            else:
                                configured_host_set = set(configured_hosts)
                                incompatible_trackers = [
                                    tracker_name
                                    for tracker_name, approved_hosts in zip(relevant_trackers, approved_sets, strict=True)
                                    if not approved_hosts & configured_host_set
                                ]

                                if incompatible_trackers:
                                    logger.warning(
                                        "[yellow]Skipping tracker(s) with no compatible configured image host: "
                                        f"{', '.join(incompatible_trackers)}. Configured hosts: {', '.join(configured_hosts)}.[/yellow]"
                                    )
                                    for tracker_name in incompatible_trackers:
                                        status = meta.tracker_status.setdefault(tracker_name, {})
                                        status["upload"] = False
                                        status["skipped"] = True
                                        status["status_message"] = "No compatible configured image host"
                                    meta.trackers = [tracker_name for tracker_name in meta.trackers if tracker_name not in incompatible_trackers]
                                    relevant_trackers = [tracker_name for tracker_name in relevant_trackers if tracker_name not in incompatible_trackers]

                                if relevant_trackers:
                                    logger.info(
                                        "[yellow]No single configured image host supports every remaining tracker. "
                                        "Compatible trackers will use their own configured image-host fallback when needed.[/yellow]"
                                    )

                            # Prefer the user-selected host if it's valid for all relevant trackers; otherwise
                            # fall back to the first common configured host by config priority (img_host_1..img_host_9).
                            current_img_host = str(meta.imghost or config["DEFAULT"].get("img_host_1") or "")
                            preferred_host: str | None = None

                            if common_configured_hosts and current_img_host not in common_configured_hosts:
                                preferred_host = common_configured_hosts[0]

                            if preferred_host and preferred_host != meta.imghost:
                                logger.debug(
                                    f"[cyan]Image host debug: current host '{current_img_host}' is not common to all trackers; "
                                    f"switching meta.imghost from '{meta.imghost}' to '{preferred_host}'.[/cyan]"
                                )
                                meta.imghost = preferred_host
                        else:
                            logger.debug(
                                f"[cyan]Image host debug: cannot compute common host (all_known={all_known}, approved_sets={len(approved_sets)}, configured_hosts={len(configured_hosts)}).[/cyan]"
                            )

                    except Exception as e:
                        logger.debug(f"[yellow]Could not determine a common approved image host: {e}[/yellow]")

                if meta.debug:
                    image_list_for_debug = cast(list[Any], meta.image_list or [])
                    logger.debug(
                        f"[cyan]Image host debug: pre-upload_screens meta.imghost={meta.imghost} image_list={len(image_list_for_debug)} cutoff={meta.cutoff} screens={meta.screens}[/cyan]"
                    )
                return_dict: dict[str, Any] = {}
                try:
                    default_cfg_obj = config.get("DEFAULT", {})
                    default_cfg = cast(dict[str, Any], default_cfg_obj) if isinstance(default_cfg_obj, dict) else {}
                    min_successful_uploads = int(default_cfg.get("min_successful_image_uploads", 3))
                    if meta.category == "BOOK":
                        meta.screens, min_successful_uploads = book_screens(meta, min_successful_uploads)

                    host_order: list[str] = []
                    for host_index in range(1, 10):
                        host_key = f"img_host_{host_index}"
                        host = default_cfg.get(host_key)
                        if host and host not in host_order:
                            host_str = str(host)
                            if allowed_hosts is None or host_str in allowed_hosts:
                                host_order.append(host_str)

                    current_img_host = str(meta.imghost or default_cfg.get("img_host_1") or "")
                    if current_img_host and current_img_host not in host_order and (allowed_hosts is None or current_img_host in allowed_hosts):
                        host_order.insert(0, current_img_host)

                    if not host_order and allowed_hosts:
                        host_order = list(allowed_hosts)

                    start_index = host_order.index(current_img_host) if current_img_host in host_order else 0
                    image_list_count = 0

                    for idx in range(start_index, len(host_order)):
                        meta.imghost = host_order[idx]
                        await uploadscreens_manager.upload_screens(meta, meta.screens, 1, 0, meta.screens, [], return_dict=return_dict, allowed_hosts=allowed_hosts)
                        image_list_count = len(meta.image_list or [])
                        logger.debug(f"[cyan]Image host debug: post-upload_screens image_list={image_list_count}[/cyan]")

                        if image_list_count >= min_successful_uploads:
                            break

                        if idx + 1 < len(host_order):
                            logger.info(
                                f"[yellow]Only {image_list_count} images uploaded; minimum is {min_successful_uploads}. Switching to next host: {host_order[idx + 1]}[/yellow]"
                            )

                    if image_list_count < min_successful_uploads:
                        raise Exception(f"Minimum of {min_successful_uploads} successful image uploads required, but only {image_list_count} were uploaded.")

                    if reviewed_uploads:
                        from src.screenshot_review import apply_staged_remote_uploads

                        review_files = [str(path) for _index, path in reviewed_uploads]
                        uploaded_review_images, uploaded_count = await uploadscreens_manager.upload_screens(
                            meta,
                            len(review_files),
                            1,
                            0,
                            len(review_files),
                            review_files,
                            {},
                            allowed_hosts=allowed_hosts,
                        )
                        if uploaded_count != len(review_files):
                            raise Exception("Could not upload every reviewed screenshot")
                        meta.image_list = apply_staged_remote_uploads(
                            Path(meta.base_dir) / "tmp" / meta.uuid,
                            cast(list[dict[str, Any]], meta.image_list or []),
                            uploaded_review_images,
                            reviewed_uploads,
                        )

                    # Now that image_list exists, populate tracker-specific keys (and only reupload if required)
                    for tracker_name in relevant_trackers:
                        tracker_instance = tracker_class_map[tracker_name](config=config)
                        if meta.debug:
                            key = f"{tracker_name}_images_key"
                            logger.debug(
                                f"[cyan]Image host debug: post-upload before {tracker_name}.check_image_hosts() image_list={len(meta.image_list or [])} {key}={len(getattr(meta, key, []) or [])}[/cyan]"
                            )
                        await check_tracker_image_hosts(meta, tracker_instance)
                        if meta.debug:
                            key = f"{tracker_name}_images_key"
                            logger.debug(
                                f"[cyan]Image host debug: post-upload after  {tracker_name}.check_image_hosts() image_list={len(meta.image_list or [])} {key}={len(getattr(meta, key, []) or [])}[/cyan]"
                            )
                except asyncio.CancelledError:
                    logger.info("\n[red]Upload process interrupted! Cancelling tasks...[/red]")
                    return False
                except Exception as e:
                    raise e
                finally:
                    cleanup_manager.reset_terminal()
                    logger.debug("[yellow]Cleaning up resources...[/yellow]")
                    gc.collect()

            elif meta.skip_imghost_upload is True and not meta.image_list:
                meta.image_list = []

            # Host book cover if it's a BOOK and save to covers.json
            if meta.category == "BOOK":
                artwork_path = meta.artwork_path
                artwork_url = meta.artwork_url
                if not artwork_path and artwork_url:
                    if Path(artwork_url).exists():
                        artwork_path = artwork_url
                    else:
                        poster_jpg_path = str(artwork_dir(meta.base_dir, meta.uuid) / "poster.jpg")
                        try:
                            import urllib.parse
                            import urllib.request

                            parsed_url = urllib.parse.urlparse(artwork_url)
                            if parsed_url.scheme in ("http", "https"):
                                Path(poster_jpg_path).parent.mkdir(parents=True, exist_ok=True)
                                await asyncio.to_thread(urllib.request.urlretrieve, artwork_url, poster_jpg_path)
                                artwork_path = poster_jpg_path
                                meta.artwork_path = artwork_path
                        except Exception as e:
                            logger.error(f"[red]Error downloading artwork from {artwork_url}: {e}[/red]")

                if artwork_path and Path(artwork_path).exists():
                    covers_file = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/covers.json"
                    use_cached_cover = False
                    if Path(covers_file).exists():
                        try:
                            async with aiofiles.open(covers_file, encoding="utf-8") as f:
                                content = await f.read()
                                loaded_covers = json.loads(content)
                                if isinstance(loaded_covers, list) and len(loaded_covers) > 0 and loaded_covers[0].get("raw_url"):
                                    use_cached_cover = True
                                    meta.hosted_artwork = loaded_covers
                                    raw_url = loaded_covers[0]["raw_url"]
                                    meta.artwork_url = raw_url
                                    meta.rehosted_artwork_url = raw_url
                                    logger.debug(f"[green]Using cached cover from covers.json: {raw_url}")
                        except Exception as e:
                            logger.debug(f"[red]Error reading covers.json cache: {e}")

                    if not use_cached_cover:
                        try:
                            uploaded_cover, _ = await uploadscreens_manager.upload_screens(meta, 1, 1, 0, 1, [artwork_path], {})
                            if uploaded_cover and len(uploaded_cover) > 0:
                                Path(covers_file).parent.mkdir(parents=True, exist_ok=True)
                                async with aiofiles.open(covers_file, "w", encoding="utf-8") as f:
                                    await f.write(json.dumps(uploaded_cover, indent=4))
                                meta.hosted_artwork = uploaded_cover
                                raw_url = uploaded_cover[0].get("raw_url", uploaded_cover[0].get("img_url", ""))
                                if raw_url:
                                    meta.artwork_url = raw_url
                                    meta.rehosted_artwork_url = raw_url
                                logger.debug(f"[green]Successfully uploaded book cover and saved to covers.json: {raw_url}")
                            else:
                                logger.error("[red]Failed to upload book cover: upload_screens returned empty result")
                        except Exception as e:
                            logger.error(f"[red]Error uploading book cover: {e}[/red]")

            async with aiofiles.open(f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/meta.json", "w", encoding="utf-8") as f:
                await f.write(json.dumps(meta.to_dict(), indent=4, cls=PathAwareEncoder))
            _publish_webui_preview_target(cast(str, meta.path or ""), meta.uuid or None)

            if "image_list" in meta and meta.image_list:
                try:
                    image_list = cast(list[Any], meta.image_list or [])
                    image_data = {"image_list": image_list, "image_sizes": meta.image_sizes, "tonemapped": meta.tonemapped}

                    async with aiofiles.open(f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/image_data.json", "w", encoding="utf-8") as img_file:
                        await img_file.write(json.dumps(image_data, indent=4))

                    logger.debug(f"[cyan]Saved {len(image_list)} images to image_data.json")
                except Exception as e:
                    logger.info(f"[yellow]Failed to save image data: {e!s}")
    finally:
        progress_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await progress_task

    has_local_subs = bool(meta.subtitle_files)
    torrent_path = str(Path(f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/BASE.torrent").resolve())
    subs_torrent_path = str(Path(f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/BASE_SUBS.torrent").resolve())

    try:
        await asyncio.gather(early_base_torrent_task, early_usenet_prepare_task)
    finally:
        await cancel_and_drain_early_artifact_tasks(meta.uuid)

    if meta.force_recheck:
        waiter = Wait(config)
        await waiter.select_and_recheck_best_torrent(meta, cast(str, meta.path), check_interval=5)

    # 1. Reuse existing torrent from client if possible
    reuse_torrent = meta.reuse_torrent_path
    base_reuse_torrent = meta.base_reuse_torrent_path
    trackers_list = [t.strip().upper() for t in meta.trackers.split(",")] if isinstance(meta.trackers, str) else [t.strip().upper() for t in meta.trackers]

    is_usenet_only = _is_usenet_only(meta)
    if not is_usenet_only:
        if meta.rehash is False and not Path(torrent_path).exists() and not meta.base_torrent_created and not meta.we_checked_them_all:
            if not reuse_torrent or not Path(reuse_torrent).exists():
                reuse_torrent = await client.find_existing_torrent(meta)
            if reuse_torrent is not None:
                await TORRENT_CREATOR.create_base_from_existing_torrent(reuse_torrent, meta.base_dir, meta.uuid)

        # 2. Re-create base torrents if rehash is True
        if meta.rehash is True and meta.nohash is False:
            await TORRENT_CREATOR.create_torrent(meta, Path(cast(str, meta.path)), "BASE")
            if has_local_subs:
                await TORRENT_CREATOR.create_torrent(meta, Path(cast(str, meta.path)), "BASE_SUBS")

        # 3. Otherwise generate if missing
        else:
            if (
                not Path(torrent_path).exists()
                and base_reuse_torrent
                and Path(base_reuse_torrent).exists()
                and (not has_local_subs or client._torrent_has_no_subtitles(base_reuse_torrent))
            ):
                await TORRENT_CREATOR.create_base_from_existing_torrent(base_reuse_torrent, meta.base_dir, meta.uuid)
            if not Path(torrent_path).exists() and meta.nohash is False:
                await TORRENT_CREATOR.create_torrent(meta, Path(cast(str, meta.path)), "BASE")
            if has_local_subs and not Path(subs_torrent_path).exists() and meta.nohash is False:
                await TORRENT_CREATOR.create_torrent(meta, Path(cast(str, meta.path)), "BASE_SUBS")

    if meta.nohash:
        meta.client = "none"

    if Path(torrent_path).exists():
        raw_trackers = meta.trackers
        trackers_list = [raw_trackers] if isinstance(raw_trackers, str) else [t for t in raw_trackers if t.strip()]
        trackers_normalized = [t.strip().upper() for t in trackers_list]

        base_piece_mb: int | None = cast(int | None, meta.base_torrent_piece_mb)
        if base_piece_mb is None and any(t in {"HDBITS", "MORETHANTV", "PASSTHEPOPCORN"} for t in trackers_normalized):
            try:
                torrent = await asyncio.to_thread(TORF_Torrent.read, torrent_path)
                base_piece_mb = torrent.piece_size // (1024 * 1024)
                if base_piece_mb is not None:
                    meta.base_torrent_piece_mb = base_piece_mb
            except Exception as e:
                logger.debug(f"[yellow]Unable to cache BASE.torrent piece size: {e}")
                base_piece_mb = None

        if "MORETHANTV" in trackers_normalized:
            mtv_cfg = config.get("TRACKERS", {}).get("MORETHANTV", {})
            if str(mtv_cfg.get("skip_if_rehash", "false")).lower() == "true" and base_piece_mb and base_piece_mb > 8:
                meta.trackers = [t for t in trackers_list if t.strip().upper() != "MORETHANTV"]
                trackers_list = [str(t) for t in cast(list[Any], meta.trackers or []) if str(t).strip()]
                trackers_normalized = [t.strip().upper() for t in trackers_list]
                logger.debug("[yellow]Removed MORETHANTV from trackers due to skip_if_rehash config and 8 MiB limit.[/yellow]")
                if not meta.trackers:
                    logger.info("[red]No trackers remain after removing MORETHANTV for skip_if_rehash.[/red]")
                    meta.we_are_uploading = False
                    return True

    if meta.randomized >= 1 and not meta.mkbrr and not is_usenet_only:
        TORRENT_CREATOR.create_random_torrents(meta.base_dir, meta.uuid, meta.randomized, cast(str, meta.path))

    async with aiofiles.open(f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/meta.json", "w", encoding="utf-8") as f:
        await f.write(json.dumps(meta.to_dict(), indent=4, cls=PathAwareEncoder))
    _publish_webui_preview_target(cast(str, meta.path or ""), meta.uuid or None)
    return True


async def cleanup_screenshot_temp_files(meta: Meta) -> None:
    """Cleanup temporary screenshot files to prevent orphaned files in case of failures."""
    screenshot_path = screenshots_dir(meta.base_dir, meta.uuid)
    if screenshot_path.exists():
        try:
            for file in (p.name for p in screenshot_path.iterdir()):
                file_path = screenshot_path / file
                if file_path.is_file() and file.endswith((".png", ".jpg")):
                    file_path.unlink()
                    logger.debug(f"[yellow]Removed temporary screenshot file: {file_path}[/yellow]")
        except Exception as e:
            logger.error(f"[red]Error cleaning up temporary screenshot files: {e}[/red]", extra={"highlighter": None})


async def save_processed_file(log_file: str, file_path: str) -> None:
    """
    Adds a processed file to the log, deduplicating and always appending it to the end.
    """
    processed_files: list[str] = []

    log_path = Path(log_file)

    if log_path.exists():
        try:
            async with aiofiles.open(log_path, encoding="utf-8") as f:
                loaded = json.loads(await f.read())

                if isinstance(loaded, list):
                    loaded = cast(list[object], loaded)
                    processed_files = [str(item) for item in loaded]
                else:
                    logger.warning(
                        f"Log file {log_file} does not contain a JSON list.",
                        extra={"highlighter": None},
                    )

        except Exception as e:
            logger.error(
                f"[red]Error reading log file {log_file}: {e}[/red]",
                extra={"highlighter": None},
            )

    processed_files = [entry for entry in processed_files if entry != file_path]
    processed_files.append(file_path)

    async with aiofiles.open(log_path, "w", encoding="utf-8") as f:
        await f.write(json.dumps(processed_files, indent=4))


def get_local_version(version_file: str | Path) -> str | None:
    """Extracts the local version from the version.py file."""
    try:
        with Path(version_file).open(encoding="utf-8") as f:
            content = f.read()
        match = re.search(r'__version__\s*=\s*"([^"]+)"', content)
        if match:
            return match.group(1)
        logger.info("[red]Version not found in local file.")
        return None
    except FileNotFoundError:
        logger.info("[red]Version file not found.")
        return None


def get_remote_version(url: str) -> tuple[str | None, str | None]:
    """Fetches the latest version information from the remote repository."""
    try:
        response = requests.get(url, timeout=30)
        if response.status_code == 200:
            content = response.text
            match = re.search(r'__version__\s*=\s*"([^"]+)"', content)
            if match:
                return match.group(1), content
            logger.info("[red]Version not found in remote file.")
            return None, None
        logger.error(f"[red]Failed to fetch remote version file. Status code: {response.status_code}")
        return None, None
    except requests.RequestException as e:
        logger.info(f"[red]An error occurred while fetching the remote version file: {e}")
        return None, None


def extract_changelog(content: str, to_version: str) -> str | None:
    """Extracts the changelog entries between the specified versions."""
    try:
        module = ast.parse(content)
        for index, node in enumerate(module.body[:-1]):
            if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                continue
            target = node.targets[0]
            if not isinstance(target, ast.Name) or target.id != "__version__":
                continue
            if not isinstance(node.value, ast.Constant) or node.value.value not in (to_version, to_version.lstrip("v")):
                continue
            notes_node = module.body[index + 1]
            if isinstance(notes_node, ast.Expr) and isinstance(notes_node.value, ast.Constant) and isinstance(notes_node.value.value, str):
                changelog = notes_node.value.value.strip()
                return re.sub(r"^# ", "", changelog, flags=re.MULTILINE)
    except SyntaxError:
        # Keep compatibility with malformed legacy version files handled below.
        pass

    # Try to find the to_version with 'v' prefix first (current format)
    patterns_to_try = [
        rf'__version__\s*=\s*"{re.escape(to_version)}"\s*\n\s*"""\s*(.*?)\s*"""',  # Try with 'v' prefix
        rf'__version__\s*=\s*"{re.escape(to_version.lstrip("v"))}"\s*\n\s*"""\s*(.*?)\s*"""',  # Try without 'v' prefix
    ]

    for pattern in patterns_to_try:
        match = re.search(pattern, content, re.DOTALL)
        if match:
            changelog = match.group(1).strip()
            # Remove the comment markers (# ) that were added by the GitHub Action
            return re.sub(r"^# ", "", changelog, flags=re.MULTILINE)

    return None


async def update_notification(base_dir: str) -> str:
    version_file = Path(base_dir) / "data" / "version.py"
    remote_version_url = "https://raw.githubusercontent.com/wastaken7/Upload-Assistant/master/data/version.py"

    notice = config["DEFAULT"].get("update_notification", True)
    verbose = config["DEFAULT"].get("verbose_notification", False)

    local_version = get_local_version(version_file)
    if not local_version:
        return ""

    if not notice:
        return local_version

    remote_version, remote_content = get_remote_version(remote_version_url)
    if not remote_version:
        return local_version

    if _parse_version_tuple(remote_version) > _parse_version_tuple(local_version):
        logger.info(f"[red][NOTICE] [green]Update available: [/green][yellow]{remote_version}")
        logger.info(f"[red][NOTICE] [green]Current version: [/green][yellow]{local_version}")
        await asyncio.sleep(1)
        if verbose and remote_content:
            changelog = extract_changelog(remote_content, remote_version)
            if changelog:
                await asyncio.sleep(1)
                logger.info(f"{changelog}")
            else:
                logger.info("[yellow]Changelog not found between versions.[/yellow]")

    return local_version


async def do_the_thing(base_dir: str) -> None:
    # Reload config from disk so that changes made via the WebUI config
    # editor (or manual file edits between runs) are picked up.  The
    # module-level ``config`` dict is imported once at startup and would
    # otherwise remain stale for the lifetime of the process.  Updating
    # in-place (clear + update) keeps all existing references (Args,
    # Clients, managers, etc.) pointing at the same dict object.
    try:
        import importlib

        import data.config as _cfg_mod  # may already be cached

        importlib.reload(_cfg_mod)
        _reloaded = _cfg_mod.config  # may raise AttributeError
        if not isinstance(_reloaded, dict):
            raise TypeError(f"Expected dict, got {type(_reloaded).__name__}")
        config.clear()
        config.update(_reloaded)
    except Exception as exc:
        logger.warning(f"[yellow]Warning: could not reload config from disk: {exc}[/yellow]")

    await asyncio.sleep(0.1)  # Ensure it's not racing

    tmp_dir = Path(base_dir) / "tmp"
    if not Path(tmp_dir).exists():
        if os.name != "nt":
            Path(tmp_dir).mkdir(parents=True, mode=0o700, exist_ok=True)
        else:
            Path(tmp_dir).mkdir(parents=True, exist_ok=True)
    else:
        # Ensure existing directory has secure permissions
        if os.name != "nt":
            Path(tmp_dir).chmod(0o700)

    def ensure_secure_tmp_subdir(subdir_path: str | Path) -> None:
        """Ensure tmp subdirectories are created with secure permissions (0o700)"""
        if not Path(subdir_path).exists():
            if os.name != "nt":
                Path(subdir_path).mkdir(parents=True, mode=0o700, exist_ok=True)
            else:
                Path(subdir_path).mkdir(parents=True, exist_ok=True)
        else:
            if os.name != "nt":
                Path(subdir_path).chmod(0o700)

    meta = Meta()
    try:
        remaining_args, pasted_paths = read_paths_from_stdin(sys.argv[1:], sys.stdin)
    except ValueError as exc:
        logger.error(f"[red]Error: {exc}.[/red]")
        raise SystemExit(2) from exc

    if pasted_paths:
        missing_paths = [path for path in pasted_paths if not Path(path).expanduser().exists()]
        if missing_paths:
            logger.error("[red]Error: The following pasted paths do not exist:[/red]")
            for missing_path in missing_paths:
                logger.error(f"[red]  - {missing_path}[/red]")
            raise SystemExit(2)
        resolved_pasted_paths = [str(Path(path).expanduser().resolve()) for path in pasted_paths]
        sys.argv[1:] = [*resolved_pasted_paths, *remaining_args]

    paths: list[str] = []
    for each in sys.argv[1:]:
        if Path(each).exists():
            paths.append(str(Path(each).resolve()))
        else:
            break

    meta.ua_name = "Upload-Assistant"
    meta.current_version = await update_notification(base_dir)

    signature = f"Shared with {meta.ua_name}"
    if meta.current_version:
        signature += f" {meta.current_version}"
    signature += " (fork)"
    meta.ua_signature = signature
    meta.base_dir = base_dir

    cleanup_only = any(arg in ("--cleanup", "-cleanup") for arg in sys.argv) and len(sys.argv) <= 2
    sanitize_meta = config["DEFAULT"].get("sanitize_meta", True)

    try:
        # If cleanup is the only operation, use a dummy path to satisfy the parser
        if cleanup_only:
            args_list = [*sys.argv[1:], "dummy_path"]
            meta, _help, _before_args = cast(tuple[Meta, Any, Any], parser.parse(args_list, meta))
            meta.path = None  # Clear the dummy path after parsing
        else:
            meta, _help, _before_args = cast(tuple[Meta, Any, Any], parser.parse(sys.argv[1:], meta))

        # Dynamically set logging level to DEBUG if debug argument is passed or enabled in config
        if meta.debug or bool(config["DEFAULT"].get("debug", False)):
            meta.debug = True
            logger.setLevel(logging.DEBUG)
            # Update RichHandler settings for debug mode

            RICH_HANDLER._log_render.show_time = bool(config["DEFAULT"].get("console_debug_show_time", True))
            RICH_HANDLER._log_render.show_level = bool(config["DEFAULT"].get("console_debug_show_level", True))
            RICH_HANDLER._log_render.show_path = bool(config["DEFAULT"].get("console_debug_show_path", True))
            RICH_HANDLER.markup = bool(config["DEFAULT"].get("console_debug_markup", True))

        # Start web UI if requested (exclusive mode - doesn't continue with uploads)
        if meta.webui:
            global _is_webui_mode, _webui_server
            _is_webui_mode = True

            webui_addr = meta.webui
            if ":" not in webui_addr:
                logger.info("[red]Invalid web UI address format. Use HOST:PORT[/red]")
                sys.exit(1)

            try:
                host, port_str = webui_addr.split(":", 1)
                port = int(port_str)
            except ValueError:
                logger.info("[red]Invalid port number in web UI address[/red]")
                sys.exit(1)

            from waitress import create_server  # type: ignore[attr-defined]

            from web_ui.server import app, set_runtime_browse_roots

            # Set browse roots for web UI
            browse_roots = os.environ.get("UA_BROWSE_ROOTS", "").strip()
            if not browse_roots and paths:
                # Use the paths from command line as browse roots
                browse_roots = ",".join(paths)
            elif not browse_roots and meta.path:
                # Use the path from command line as browse roots
                path_value = meta.path
                browse_roots = ",".join(str(p) for p in path_value) if isinstance(path_value, list) else (path_value)
            if not browse_roots:
                raise SystemExit("No browse roots specified. Please set UA_BROWSE_ROOTS environment variable or provide explicit paths.")

            set_runtime_browse_roots(browse_roots)

            try:
                _webui_server = cast(WebUIServer, create_server(app, host=host, port=port))

                # Build clickable URL (use localhost for 0.0.0.0 display)
                display_host = "localhost" if host == "0.0.0.0" else host  # noqa: S104
                url = f"http://{display_host}:{port}"

                logger.info("")
                logger.info("[green]Web UI server started[/green]")
                logger.info(f"[bold]Access at: {format_terminal_link(url, url, config['DEFAULT'])}[/bold]")
                logger.info("[dim]Press Ctrl+C to stop the server[/dim]")
                logger.info("")

                # Run server in daemon thread so main thread can handle signals
                server_thread = threading.Thread(target=_webui_server.run, daemon=True)
                server_thread.start()

                # Wait for shutdown signal or unexpected thread death
                while not _shutdown_event.is_set():
                    if not server_thread.is_alive():
                        raise RuntimeError("Web UI server thread exited unexpectedly")
                    _shutdown_event.wait(timeout=1.0)

                # Close server gracefully
                _webui_server.close()
                server_thread.join(timeout=5.0)

            except Exception as e:
                if not _shutdown_requested:
                    logger.info(f"[red]Web UI server error: {e}[/red]")
                    sys.exit(1)
            finally:
                logger.info("[yellow]Web UI server stopped[/yellow]")

            return  # Exit early when running web UI only

        # Validate config structure and types (after args parsed so we have trackers list)
        from src.configvalidator import group_warnings, validate_config

        # Get active trackers from meta (parsed from command line) or fall back to config default
        active_trackers: list[str] | None = None
        if meta.trackers:
            if isinstance(meta.trackers, str):
                active_trackers = [t.strip().upper() for t in meta.trackers.split(",") if t.strip()]
            elif isinstance(meta.trackers, list):
                trackers_list = meta.trackers
                active_trackers = [t.strip().upper() for t in trackers_list if (t).strip()]

        # Get active imghost from meta (parsed from command line)
        active_imghost: str | None = None
        if meta.imghost:
            imghost_val = meta.imghost.strip()
            if imghost_val:
                active_imghost = imghost_val

        is_valid, config_errors, config_warnings = validate_config(config, active_trackers, active_imghost)

        if not is_valid:
            logger.info("[bold red]Configuration validation failed:[/bold red]")
            for error in config_errors:
                logger.info(f"[red]  ✗ {error}[/red]")
            logger.info("[red]\nPlease fix the above errors in your config.py[/red]")
            logger.info("[yellow]Reference: https://github.com/Audionut/Upload-Assistant/blob/master/data/example_config.py[/yellow]")
            raise SystemExit(1)

        if config_warnings:
            suppress_warnings = config.get("DEFAULT", {}).get("suppress_warnings", False)
            if not suppress_warnings:
                grouped = group_warnings(config_warnings)
                logger.info(f"[yellow]Config validation passed with {len(grouped)} warning(s):[/yellow]")
                for warning_str in grouped:
                    logger.info(f"[yellow]  ⚠ {warning_str}[/yellow]")
                logger.info("")  # Blank line after warnings

        if meta.cleanup:
            if Path(f"{base_dir}{'/' + 'tmp'}").exists():
                shutil.rmtree(f"{base_dir}{'/' + 'tmp'}")
                logger.info("[yellow]Successfully emptied tmp directory[/yellow]")
                logger.info("")
            if not meta.path or cleanup_only:
                exit(0)

        if not meta.path:
            exit(0)

        path = meta.path
        path = str(Path(path).resolve())
        if path.endswith('"'):
            path = path[:-1]

        is_binary = await get_mkbrr_path(base_dir)
        if not meta.mkbrr:
            try:
                meta.mkbrr = config["DEFAULT"].get("mkbrr", False)
            except ValueError:
                logger.debug("[yellow]Invalid mkbrr config value, defaulting to False[/yellow]")
                meta.mkbrr = False
        if meta.mkbrr and not is_binary:
            logger.info("[bold red]mkbrr binary is not available. Please ensure it is installed correctly.[/bold red]")
            logger.info("[bold red]Reverting to Torf[/bold red]")
            logger.info("")
            meta.mkbrr = False

        queue, log_file = await QueueManager.handle_queue(path, meta, paths, base_dir)
        queue_list = cast(list[Any], queue)

        processed_files_count = 0
        skipped_files_count = 0
        base_meta = meta.copy()

        for queue_item in queue_list:
            total_files = len(queue_list)
            current_item_path: str = ""
            tmp_path = ""
            current_release_log_path.set(None)
            try:
                meta = base_meta.copy()

                if meta.site_upload_queue:
                    # Extract path and metadata from site upload queue item
                    queue_item_mapping = cast(Mapping[str, Any], queue_item)
                    path = await QueueManager.process_site_upload_item(queue_item_mapping, meta)
                    current_item_path = path  # Store for logging
                    meta.item_args = [path]
                elif meta.args_line_queue and isinstance(queue_item, dict) and "args" in queue_item:
                    # Extract path and arguments from custom args queue item
                    queue_item_mapping = cast(Mapping[str, Any], queue_item)
                    args_list = cast(list[str], queue_item_mapping["args"])
                    # We parse the arguments for this specific item using the parser, updating the cloned meta dict.
                    meta, parser_obj, _before_args = cast(tuple[Meta, Any, Any], parser.parse(args_list, meta))

                    # Preserve global defaults from base_meta if they were not explicitly overridden in args_list
                    dest_to_options: dict[str, list[str]] = {}
                    if parser_obj and hasattr(parser_obj, "_actions"):
                        for action in parser_obj._actions:
                            if action.dest and action.option_strings:
                                dest_to_options[action.dest] = action.option_strings

                    for key, val in cast(dict[str, Any], base_meta).items():
                        if val not in (None, False, []):
                            option_strings = dest_to_options.get(key, [])
                            if option_strings and not any(arg == opt or arg.startswith(opt + "=") for opt in option_strings for arg in args_list):
                                meta[key] = val

                    # QueueManager already resolved the first positional
                    # argument into the queue item.  Use that authoritative
                    # value for the preview and processing target instead of
                    # relying on a partially parsed Meta copy.
                    path = str(queue_item_mapping.get("path") or meta.path or "")
                    current_item_path = str(queue_item_mapping.get("line") or path or "")
                    meta.item_args = args_list
                else:
                    # Regular queue processing
                    path = queue_item if isinstance(queue_item, str) else str(queue_item)
                    current_item_path = path
                    if meta.queue:
                        meta.item_args = [path]
                    else:
                        meta.item_args = list(sys.argv[1:])

                meta.path = path
                meta.uuid = ""
                _publish_webui_preview_target(path)

                if not path:
                    raise ValueError("The 'path' variable is not defined or is empty.")

                tmp_path = Path(base_dir) / "tmp" / Path(path).name

                # Ensure tmp subdirectory exists with secure permissions
                ensure_secure_tmp_subdir(tmp_path)
                current_release_log_path.set(str(Path(tmp_path) / f"upload_{int(time.time())}.log"))

                if meta.delete_tmp and Path(tmp_path).exists():
                    try:
                        shutil.rmtree(tmp_path)
                        if os.name != "nt":
                            Path(tmp_path).mkdir(parents=True, mode=0o700, exist_ok=True)
                        else:
                            Path(tmp_path).mkdir(parents=True, exist_ok=True)
                        logger.debug(f"[yellow]Successfully cleaned temp directory for {Path(path).name}[/yellow]")
                        logger.debug("")
                    except Exception as e:
                        logger.info(f"[bold red]Failed to delete temp directory: {e!s}")

                meta_file = Path(base_dir) / "tmp" / Path(path).name / "meta.json"

                keep_meta = config["DEFAULT"].get("keep_meta", False)

                if not keep_meta or meta.delete_meta:
                    if Path(meta_file).exists():
                        try:
                            meta_file.unlink()
                            logger.debug(f"[bold yellow]Found and deleted existing metadata file: {meta_file}")
                        except Exception as e:
                            logger.info(f"[bold red]Failed to delete metadata file {meta_file}: {e!s}")
                    else:
                        logger.debug(f"[yellow]No metadata file found at {meta_file}")

                if keep_meta and Path(meta_file).exists():
                    async with aiofiles.open(meta_file, encoding="utf-8") as f:
                        content = await f.read()
                        saved_meta = cast(dict[str, Any], json.loads(content)) if content.strip() else {}
                        logger.info("[yellow]Existing metadata file found, it holds cached values")
                        await merge_meta(meta, saved_meta)
                        _publish_webui_preview_target(path, meta.uuid or None)

            except Exception as e:
                logger.info(f"[red]Exception: '{path}': {e}")
                cleanup_manager.reset_terminal()

            start_time = time.time()

            logger.info(f"[green]Gathering info for {Path(path).name}")

            try:
                meta_success = await process_meta(meta, base_dir)
            finally:
                await cancel_and_drain_early_artifact_tasks(meta.uuid)
            if not meta_success:
                if "queue" in meta and meta.queue is not None:
                    processed_files_count += 1
                    skipped_files_count += 1
                    logger.info(f"[cyan]Processed {processed_files_count}/{total_files} files with {skipped_files_count} skipped uploading.\n\n")
                    if log_file and (not meta.debug or "debug" in Path(log_file).name):
                        if meta.site_upload_queue:
                            await QueueManager.save_processed_path(log_file, current_item_path)
                        else:
                            await save_processed_file(log_file, current_item_path)
                await cleanup_manager.cleanup()
                gc.collect()
                cleanup_manager.reset_terminal()
                continue

            tracker_setup = TrackerSetup(config=config)
            if "we_are_uploading" not in meta or not meta.we_are_uploading:
                if config["DEFAULT"].get("cross_seeding", True):
                    await process_cross_seeds(meta)
                if not meta.site_check:
                    logger.info("we are not uploading.......")
                    if "queue" in meta and meta.queue is not None:
                        processed_files_count += 1
                        skipped_files_count += 1
                        logger.info(f"[cyan]Processed {processed_files_count}/{total_files} files with {skipped_files_count} skipped uploading.\n\n")
                        if log_file and (not meta.debug or "debug" in Path(log_file).name):
                            if meta.site_upload_queue:
                                await QueueManager.save_processed_path(log_file, current_item_path)
                            else:
                                await save_processed_file(log_file, current_item_path)

            else:
                meta = meta
                if meta.were_trumping:
                    trump_trackers = [t for t in cast(list[Any], meta.trackers) if isinstance(t, str)]
                    logger.info("[yellow]Checking for existing trump reports.....")
                    tracker_status = cast(dict[str, dict[str, Any]], meta.tracker_status or {})
                    trumping_trackers: list[str] = []
                    for tracker in trump_trackers:
                        is_trumping = await tracker_setup.process_trumpables(meta, tracker=tracker)
                        skip_upload_trackers = set(meta.skip_upload_trackers or [])

                        # Apply any per-tracker skip decisions made during trumpable processing

                        if skip_upload_trackers:
                            for t in skip_upload_trackers:
                                per_tracker = tracker_status.setdefault(t, {})
                                per_tracker["upload"] = False
                                per_tracker["skipped"] = True

                            meta.trackers = [t for t in meta.trackers if t not in skip_upload_trackers]
                            logger.debug(f"[yellow]Skipping trackers due to trump report selection: {', '.join(sorted(skip_upload_trackers))}[/yellow]")
                            if not meta.trackers:
                                logger.info("[bold red]No trackers left to upload after trump checking.[/bold red]")
                        if is_trumping and not skip_upload_trackers.__contains__(tracker):
                            trumping_trackers.append(tracker)

                    meta.trumping_trackers = trumping_trackers

                # allowing the skip uploading feature to only apply when double dupe checking is enabled
                successful_trackers = 10
                if meta.dupe_again:
                    logger.info("[yellow]Performing double dupe check on trackers that passed initial upload checks.....[/yellow]")
                    raw_trackers_list = meta.trackers
                    trackers_list: list[str]
                    if isinstance(raw_trackers_list, list):
                        trackers_list = [t for t in raw_trackers_list if isinstance(t, str)]
                    else:
                        trackers_list = []
                        meta.trackers = trackers_list

                    tracker_status_map = meta.tracker_status
                    for tracker in list(trackers_list):
                        tracker_status = tracker_status_map.get(tracker, {})
                        if tracker_status.get("upload") is not True:
                            logger.debug(f"[yellow]{tracker} was previously marked to skip upload. Skipping double dupe check.[/yellow]")
                            trackers_list.remove(tracker)
                            tracker_status_map.pop(tracker, None)
                            continue

                    if trackers_list:
                        successful_trackers = await TrackerStatusManager(config=config).process_all_trackers(meta)
                    else:
                        successful_trackers = 0

                skip_uploading = meta.skip_uploading
                skip_uploading_int = int(skip_uploading) if isinstance(skip_uploading, (int, str)) else 0

                if successful_trackers < skip_uploading_int and not meta.debug:
                    logger.info(f"[red]Not enough successful trackers ({successful_trackers}/{skip_uploading_int}). No uploads being processed.[/red]")
                else:
                    trackers_upper = [(t).upper() for t in meta.trackers]
                    # Partition trackers into torrent trackers and Usenet indexers
                    torrent_trackers: list[str] = []
                    usenet_trackers: list[str] = []
                    for tracker in meta.trackers:
                        t_upper = (tracker).upper().strip()
                        if t_upper == "USENET":
                            continue
                        tracker_class = tracker_class_map.get(t_upper)
                        if tracker_class and getattr(tracker_class, "is_usenet", False):
                            usenet_trackers.append(tracker)
                            continue
                        torrent_trackers.append(tracker)

                    explicit_usenet_post = "USENET" in trackers_upper or meta.usenet
                    eligible_usenet_trackers = [tracker for tracker in usenet_trackers if cast(Mapping[str, Any], meta.tracker_status.get(tracker, {})).get("upload", False)]
                    need_usenet_post = explicit_usenet_post or len(eligible_usenet_trackers) > 0

                    async def upload_usenet_flow(meta: Meta, usenet_trackers: list[str], need_usenet_post: bool, has_usenet_trackers: bool) -> None:
                        if need_usenet_post:
                            from src.usenetcreate import prepare_and_upload_usenet

                            try:
                                nzb_path = await prepare_and_upload_usenet(meta, config)
                                if nzb_path:
                                    meta.nzb_path = nzb_path
                                    logger.info("[bold green]Usenet upload completed successfully!")
                                    if usenet_trackers:
                                        meta_usenet = meta.copy()
                                        meta_usenet["trackers"] = usenet_trackers
                                        # Meta.copy() is deep; keep results on the queue item's
                                        # status map so its final summary can see this flow.
                                        meta_usenet.tracker_status = meta.tracker_status
                                        logger.info(f"[yellow]Processing uploads to Usenet indexers: {', '.join(usenet_trackers)}.....")
                                        await process_trackers(
                                            meta_usenet,
                                            config,
                                            client,
                                            list(api_trackers),
                                            tracker_class_map,
                                            list(http_trackers),
                                            list(other_api_trackers),
                                            upload_target="usenet indexer",
                                        )
                                else:
                                    logger.info("[bold red]Usenet upload failed.[/bold red]")
                                    status_map = meta.tracker_status
                                    for t in usenet_trackers:
                                        status_map.setdefault(t, {})["status_message"] = "data error: Usenet upload failed, NZB missing"
                                        status_map[t]["upload"] = False
                            except Exception as e:
                                logger.info(f"[bold red]Error in Usenet upload pipeline: {e}[/bold red]")
                                import traceback

                                logger.info(traceback.format_exc())
                                status_map = meta.tracker_status
                                for t in usenet_trackers:
                                    status_map.setdefault(t, {})["status_message"] = f"data error: Usenet upload failed: {e}"
                                    status_map[t]["upload"] = False
                        elif has_usenet_trackers:
                            logger.info("[yellow]Skipping NNTP Usenet post because no Usenet indexers passed the upload checks.[/yellow]")

                    async def upload_torrent_flow(meta: Meta, torrent_trackers: list[str]) -> None:
                        if torrent_trackers:
                            meta_torrent = meta.copy()
                            meta_torrent["trackers"] = torrent_trackers
                            # The final queue result is evaluated against ``meta``, not this
                            # per-flow copy, including when both flows run concurrently.
                            meta_torrent.tracker_status = meta.tracker_status
                            await process_trackers(
                                meta_torrent,
                                config,
                                client,
                                list(api_trackers),
                                tracker_class_map,
                                list(http_trackers),
                                list(other_api_trackers),
                            )

                    upload_order = meta.upload_order or config["DEFAULT"].get("upload_order", "concurrent")
                    upload_order = upload_order.strip().lower() if isinstance(upload_order, str) else "concurrent"

                    if upload_order == "usenet":
                        await upload_usenet_flow(meta, eligible_usenet_trackers, need_usenet_post, bool(usenet_trackers))
                        await upload_torrent_flow(meta, torrent_trackers)
                    elif upload_order == "tracker":
                        await upload_torrent_flow(meta, torrent_trackers)

                        if need_usenet_post and torrent_trackers:
                            logger.info("\n[yellow]Torrent uploads completed. Checking bandwidth before starting Usenet upload...[/yellow]")
                            from src.qbitwait import Wait

                            try:
                                waiter = Wait(config)
                                bw_thresh = meta.qbit_bandwidth_threshold or config["DEFAULT"].get("qbit_bandwidth_threshold", 0)
                                bw_time = meta.qbit_bandwidth_time or config["DEFAULT"].get("qbit_bandwidth_time", 0)
                                try:
                                    bw_thresh = int(bw_thresh)
                                    bw_time = int(bw_time)
                                except (ValueError, TypeError) as e:
                                    logger.info(f"[red]Invalid bandwidth settings: {e}, skipping bandwidth wait before Usenet upload.[/red]")
                                    bw_thresh = 0
                                    bw_time = 0
                                if bw_thresh > 0 and bw_time > 0:
                                    await waiter.wait_for_bandwidth(bw_thresh, bw_time)
                                else:
                                    logger.info("[yellow]Bandwidth control threshold or time is 0 or not configured. Skipping bandwidth check.[/yellow]")
                            except Exception as e:
                                logger.info(f"[red]Error initializing bandwidth check: {e}, skipping bandwidth wait before Usenet upload.[/red]")

                        await upload_usenet_flow(meta, eligible_usenet_trackers, need_usenet_post, bool(usenet_trackers))
                    else:
                        await asyncio.gather(
                            upload_usenet_flow(meta, eligible_usenet_trackers, need_usenet_post, bool(usenet_trackers)),
                            upload_torrent_flow(meta, torrent_trackers),
                        )
                    if config["DEFAULT"].get("cross_seeding", True):
                        await process_cross_seeds(meta)

                    if "queue" in meta and meta.queue is not None:
                        processed_files_count += 1
                        tracker_statuses = [status for status in meta.tracker_status.values() if isinstance(status, Mapping)]
                        upload_succeeded = any(status.get("upload_success") is True for status in tracker_statuses)
                        if not upload_succeeded and not meta.debug:
                            skipped_files_count += 1
                            logger.info(f"[yellow]Processed {processed_files_count}/{total_files} files; no tracker upload succeeded.[/yellow]")
                        elif meta.debug:
                            logger.info(f"[cyan]Processed {processed_files_count}/{total_files} files in debug mode; no tracker upload was attempted.[/cyan]")
                        elif "limit_queue" in meta and meta.limit_queue > 0:
                            logger.info(f"[cyan]Successfully uploaded {processed_files_count - skipped_files_count} of {meta.limit_queue} in limit with {total_files} files.")
                        else:
                            logger.info(f"[cyan]Successfully uploaded {processed_files_count - skipped_files_count}/{total_files} files.")
                        if log_file and (not meta.debug or "debug" in Path(log_file).name):
                            if meta.site_upload_queue:
                                await QueueManager.save_processed_path(log_file, current_item_path)
                            else:
                                await save_processed_file(log_file, current_item_path)

            finish_time = time.time()
            logger.debug(f"Uploads processed in {finish_time - start_time:.4f} seconds")

            for tracker in meta.trumping_trackers:
                logger.info(f"[yellow]Submitting trumpable report to {tracker}.....")
                await tracker_setup.make_trumpable_report(meta, tracker)

            find_requests = config["DEFAULT"].get("search_requests", False) if meta.search_requests is None else meta.search_requests
            if find_requests and meta.trackers not in ([], None, "") and not (meta.site_check and not meta.is_disc):
                logger.info("[green]Searching for requests on supported trackers.....")
                if meta.site_check:
                    trackers = meta.requested_trackers if meta.requested_trackers is not None else []
                    logger.debug(f"[cyan]Using requested trackers for site check: {trackers}[/cyan]")
                else:
                    trackers = [t for t in cast(list[Any], meta.trackers) if isinstance(t, str)]
                    logger.debug(f"[cyan]Using trackers for request search: {trackers}[/cyan]")
                await tracker_setup.tracker_request(meta, trackers)

            if meta.site_check and "queue" in meta and meta.queue is not None:
                processed_files_count += 1
                skipped_files_count += 1
                logger.info(f"[cyan]Processed {processed_files_count}/{total_files} files.")
                if log_file and (not meta.debug or "debug" in Path(log_file).name):
                    if meta.site_upload_queue:
                        await QueueManager.save_processed_path(log_file, current_item_path)
                    else:
                        await save_processed_file(log_file, current_item_path)

            if "limit_queue" in meta and meta.limit_queue > 0 and (processed_files_count - skipped_files_count) >= meta.limit_queue:
                if sanitize_meta:
                    try:
                        await asyncio.sleep(0.2)  # We can't race the status prints
                        meta = await Redaction.clean_meta_for_export(meta)
                    except Exception as e:
                        logger.error(f"[red]Error cleaning meta for export: {e}")
                await cleanup_manager.cleanup()
                gc.collect()
                cleanup_manager.reset_terminal()
                break

            if sanitize_meta:
                try:
                    await asyncio.sleep(0.2)
                    meta = await Redaction.clean_meta_for_export(meta)
                except Exception as e:
                    logger.error(f"[red]Error cleaning meta for export: {e}")
            await cleanup_manager.cleanup()
            gc.collect()
            cleanup_manager.reset_terminal()
        current_release_log_path.set(None)

    except Exception as e:
        logger.info(f"[bold red]An unexpected error occurred: {e}")
        if sanitize_meta:
            meta = await Redaction.clean_meta_for_export(meta)
        logger.info(traceback.format_exc())
        cleanup_manager.reset_terminal()

    finally:
        current_release_log_path.set(None)
        if not sys.stdin.closed:
            cleanup_manager.reset_terminal()


async def process_cross_seeds(meta: Meta) -> None:
    all_trackers: set[str] = set(api_trackers) | set(http_trackers) | set(other_api_trackers)

    # Get list of trackers to exclude (already in client)
    remove_list: list[str] = []
    if meta.remove_trackers:
        if isinstance(meta.remove_trackers, str):
            remove_list = [t.strip().upper() for t in meta.remove_trackers.split(",")]
        elif isinstance(meta.remove_trackers, list):
            remove_list = [t.strip().upper() for t in meta.remove_trackers if isinstance(t, str)]

    # Check for trackers that haven't been dupe-checked yet
    dupe_checked_trackers = [t for t in meta.dupe_checked_trackers if isinstance(t, str)]

    # Validate tracker configs and build list of valid unchecked trackers
    valid_unchecked_trackers: list[str] = []
    for tracker in all_trackers:
        if tracker in dupe_checked_trackers or meta.get(f"{tracker}_cross_seed", None) is not None or tracker in remove_list:
            continue

        tracker_config = config.get("TRACKERS", {}).get(tracker, {})
        if not tracker_config:
            logger.debug(f"[yellow]Tracker {tracker} not found in config, skipping[/yellow]")
            continue

        api_key = tracker_config.get("api_key", "")
        announce_url = tracker_config.get("announce_url", "")

        # Ensure both values are strings and strip whitespace
        api_key = str(api_key).strip() if api_key else ""
        announce_url = str(announce_url).strip() if announce_url else ""

        # Skip if both api_key and announce_url are empty
        if not api_key and not announce_url:
            logger.debug(f"[yellow]Tracker {tracker} has no api_key or announce_url set, skipping[/yellow]")
            continue

        # Skip trackers with placeholder announce URLs
        placeholder_patterns = ["<PASSKEY>", "customannounceurl", "get from upload page", "Custom_Announce_URL", "PASS_KEY", "insertyourpasskeyhere"]
        announce_url_lower = announce_url.lower()
        if any(pattern.lower() in announce_url_lower for pattern in placeholder_patterns):
            logger.debug(f"[yellow]Tracker {tracker} has placeholder announce_url, skipping[/yellow]")
            continue

        valid_unchecked_trackers.append(tracker)

    # Search for cross-seeds on unchecked trackers
    if valid_unchecked_trackers and config["DEFAULT"].get("cross_seed_check_everything", False):
        logger.info(f"[cyan]Checking for cross-seeds on unchecked trackers: {valid_unchecked_trackers}[/cyan]")

        try:
            await validate_tracker_logins(meta, valid_unchecked_trackers)
            await asyncio.sleep(0.2)
        except Exception as e:
            logger.warning(f"[yellow]Warning: Tracker validation encountered an error: {e}[/yellow]")

        # Store original unattended value
        original_unattended = meta.unattended
        meta.unattended = True

        helper: Any = UploadHelper(config)
        dupe_checker = DupeChecker(config)

        async def check_tracker_for_dupes(tracker: str) -> None:
            try:
                tracker_class = tracker_class_map[tracker](config=config)

                # Search for existing torrents
                if tracker != "PASSTHEPOPCORN":
                    if hasattr(tracker_class, "get_additional_checks"):
                        import inspect

                        if inspect.iscoroutinefunction(tracker_class.get_additional_checks):
                            should_continue = await tracker_class.get_additional_checks(meta)
                        else:
                            should_continue = tracker_class.get_additional_checks(meta)
                        if not should_continue:
                            meta.skipping = tracker
                            return
                    dupes = await tracker_class.search_existing(meta)
                else:
                    ptp = PassThePopcorn(config=config)
                    if hasattr(ptp, "get_additional_checks"):
                        import inspect

                        if inspect.iscoroutinefunction(ptp.get_additional_checks):
                            should_continue = await ptp.get_additional_checks(meta)
                        else:
                            should_continue = ptp.get_additional_checks(meta)
                        if not should_continue:
                            meta.skipping = tracker
                            return
                    group_id = meta.ptp_groupid
                    if not group_id and meta.imdb:
                        group_id = await ptp.get_group_by_imdb(meta.imdb)
                        meta.ptp_groupid = group_id
                    if group_id is None:
                        return
                    dupes = await ptp.search_existing(group_id, meta)

                if dupes:
                    dupes = await dupe_checker.filter_dupes(dupes, meta, tracker)
                    _is_dupe, updated_meta = await helper.dupe_check(cast(list[Any], dupes), meta, tracker)
                    # Persist any updates from dupe_check (defensive in case it returns a copy)
                    if updated_meta is not meta:
                        meta.update(updated_meta)

            except Exception as e:
                logger.warning(f"[yellow]Warning: Failed to check duplicates for cross-seed on {tracker}: {e}[/yellow]")

        # Run all dupe checks concurrently
        await asyncio.gather(*[check_tracker_for_dupes(tracker) for tracker in valid_unchecked_trackers], return_exceptions=True)

        # Restore original unattended value
        meta.unattended = original_unattended

    # Filter to only trackers with cross-seed data
    valid_trackers = [tracker for tracker in all_trackers if meta.get(f"{tracker}_cross_seed", None) is not None]

    if not valid_trackers:
        logger.debug("[yellow]No trackers found with cross-seed data[/yellow]")
        return

    logger.info(f"[cyan]Valid trackers for cross-seed check: {valid_trackers}[/cyan]")

    common = Common(config)
    try:
        concurrency_limit = int(config.get("DEFAULT", {}).get("cross_seed_concurrency", 8))
    except TypeError, ValueError:
        concurrency_limit = 8
    semaphore = asyncio.Semaphore(max(1, concurrency_limit))

    async def handle_cross_seed(tracker: str) -> None:
        cross_seed_key = f"{tracker}_cross_seed"
        cross_seed_value = getattr(meta, cross_seed_key, False)

        logger.debug(f"[cyan]Debug: {tracker} - cross_seed: {Redaction.redact_private_info(cross_seed_value)}")

        if not cross_seed_value:
            return

        logger.debug(f"[green]Found cross-seed for {tracker}!")

        download_url = ""
        if isinstance(cross_seed_value, str) and cross_seed_value.startswith("http"):
            download_url = cross_seed_value
        else:
            logger.debug(f"[yellow]Invalid cross-seed URL for {tracker}, skipping[/yellow]")
            return

        headers = None
        if tracker == "RETROFLIX":
            headers = {
                "accept": "application/json",
                "Authorization": config["TRACKERS"][tracker]["api_key"].strip(),
            }

        if tracker == "ALPHARATIO" and download_url:
            try:
                ar = AlphaRatio(config=config)
                auth_key = await ar.get_auth_key(meta)

                # Extract torrent_pass from announce_url
                announce_url = config["TRACKERS"]["ALPHARATIO"].get("announce_url", "")
                # Pattern: http://tracker.alpharatio.cc:2710/PASSKEY/announce
                match = re.search(r":\d+/([^/]+)/announce", announce_url)
                torrent_pass = match.group(1) if match else None

                if auth_key and torrent_pass:
                    # Append auth_key and torrent_pass to download_url
                    separator = "&" if "?" in download_url else "?"
                    download_url += f"{separator}authkey={auth_key}&torrent_pass={torrent_pass}"
                    logger.debug("[cyan]Added ALPHARATIO auth_key and torrent_pass to download URL[/cyan]")
            except Exception as e:
                logger.debug(f"[yellow]Error getting ALPHARATIO auth credentials: {e}[/yellow]")

        async with semaphore:
            await common.download_tracker_torrent(meta, tracker, headers=headers, params=None, downurl=download_url, hash_is_id=False, cross=True)
            await client.add_to_client(meta, tracker, cross=True)

    tasks = [(tracker, asyncio.create_task(handle_cross_seed(tracker))) for tracker in valid_trackers]

    results = await asyncio.gather(*(task for _, task in tasks), return_exceptions=True)
    for (tracker, _), result in zip(tasks, results, strict=False):
        if isinstance(result, Exception):
            logger.info(f"[red]Cross-seed handling failed for {tracker}: {result}[/red]")


async def get_mkbrr_path(base_dir: str | None = None) -> str | None:
    try:
        resolved_base_dir = base_dir or str(Path(__file__).resolve().parent)
        mkbrr_path = await MkbrrBinaryManager.ensure_mkbrr_binary(resolved_base_dir, version="v1.24.0")
        return mkbrr_path if mkbrr_path else None
    except Exception as e:
        logger.error(f"[red]Error setting up mkbrr binary: {e}[/red]")
        return None


def check_python_version() -> None:
    pyver = platform.python_version_tuple()
    if int(pyver[0]) != 3 or int(pyver[1]) < 9:
        logger.info("[bold red]Python version is too low. Please use Python 3.9 or higher.")
        sys.exit(1)


async def main() -> None:
    # Reset global state for clean in-process runs (when called from web UI)
    pending_webui_session_id = _webui_session_id
    pending_webui_run_token = _webui_run_token
    _reset_shutdown_state()
    if pending_webui_session_id and pending_webui_run_token:
        global _is_webui_mode
        _is_webui_mode = True
        set_webui_session_id(pending_webui_session_id, pending_webui_run_token)

    try:
        await do_the_thing(base_dir)
    except asyncio.CancelledError:
        if not _shutdown_requested:
            logger.info("[red]Tasks were cancelled. Exiting safely.[/red]")
    except EOFError:
        pass  # Web UI cancellation - handled silently
    except KeyboardInterrupt:
        pass  # Handled by signal handler
    except Exception as e:
        if not _shutdown_requested:
            logger.error(f"[bold red]Unexpected error: {e}[/bold red]")


if __name__ == "__main__":
    check_python_version()

    # Register signal handlers only when run as main script (not when imported)
    signal.signal(signal.SIGINT, _handle_shutdown_signal)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _handle_shutdown_signal)

    try:
        asyncio.run(main())
    except KeyboardInterrupt, SystemExit:
        if not _shutdown_requested:
            logger.info("\n[yellow]Shutting down...[/yellow]")
    except BaseException as e:
        if not _shutdown_requested:
            logger.info(f"[bold red]Critical error: {e}[/bold red]")
    finally:
        # Only run async cleanup for non-webui mode (webui doesn't use asyncio)
        if not _is_webui_mode:
            with contextlib.suppress(Exception):
                # Run cleanup with timeout to prevent hanging on shutdown
                async def _cleanup_with_timeout() -> None:
                    try:
                        await asyncio.wait_for(cleanup_manager.cleanup(), timeout=10.0)
                    except TimeoutError, asyncio.CancelledError:
                        logger.info("[yellow]Cleanup timed out or was cancelled, forcing exit...[/yellow]")

                asyncio.run(_cleanup_with_timeout())

        gc.collect()
        cleanup_manager.reset_terminal()

        if _shutdown_requested or _is_webui_mode:
            logger.info("[green]Shutdown complete[/green]")

        sys.exit(0)
