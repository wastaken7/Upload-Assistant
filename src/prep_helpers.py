# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import asyncio
import contextlib
import ntpath
import os
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlparse

import aiofiles
import cli_ui
import guessit
from torf import Torrent

from src.bluray_com import get_bluray_releases
from src.book_prep import AUDIOBOOK_EXTENSIONS, BOOK_EXTENSIONS
from src.cleanup import cleanup_manager
from src.clients import Clients
from src.console import logger
from src.edition import get_edition
from src.exceptions import NoAudioMediaError
from src.exportmi import export_info, get_conformance_error, mi_resolution, validate_mediainfo
from src.get_source import get_source
from src.imdb import imdb_manager
from src.languages import languages_manager
from src.meta import Meta
from src.region import get_distributor, get_region, get_service
from src.tags import get_tag, tag_override
from src.tvmaze import tvmaze_manager
from src.video import video_manager

guessit_module: Any = cast(Any, guessit)

_URL_TOKEN_RE = re.compile(r"https?://[^\s<>'\"()]+", re.IGNORECASE)


def _is_igdb_url(url: str) -> bool:
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return False
    return host == "igdb.com" or host.endswith(".igdb.com")


def _is_steam_app_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    host = (parsed.hostname or "").lower()
    path = parsed.path or ""
    return host == "store.steampowered.com" and path.startswith("/app/")


def _nfo_has_store_link(content: str) -> bool:
    for match in _URL_TOKEN_RE.finditer(content):
        url = match.group(0)
        if _is_steam_app_url(url) or _is_igdb_url(url):
            return True
    return False


def guessit_fn(value: str, options: dict[str, Any] | None = None) -> dict[str, Any]:
    return cast(dict[str, Any], guessit_module.guessit(value, options))


def _normalize_search_year(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, (str, int)):
        return str(value)
    return str(value)


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except TypeError, ValueError:
        return default


def _title_without_leading_article(title: str) -> str:
    return re.sub(r"^(the|a|an)\s+", "", title.strip().lower(), flags=re.IGNORECASE)


def _tvdb_title_drops_existing_leading_article(current_title: Any, tvdb_title: str) -> bool:
    if not isinstance(current_title, str) or not current_title.strip() or not tvdb_title.strip():
        return False

    current = current_title.strip().lower()
    tvdb = tvdb_title.strip().lower()
    current_has_article = re.match(r"^(the|a|an)\s+", current, flags=re.IGNORECASE) is not None
    return current_has_article and current != tvdb and _title_without_leading_article(current) == tvdb


def init_meta(prep_instance: Any, meta: Meta, mode: str) -> tuple[bool, bool, Clients, bool, list[str], list[str]]:
    meta.cutoff = int(prep_instance.config["DEFAULT"].get("cutoff_screens", 1))

    meta.mode = mode
    meta.isdir = Path(meta.path or "").is_dir()
    base_dir = meta.base_dir
    meta.saved_description = False
    client = Clients(config=prep_instance.config)
    meta.skip_auto_torrent = meta.skip_auto_torrent or prep_instance.config["DEFAULT"].get("skip_auto_torrent", False)
    hash_ids = ["infohash", "torrent_hash", "skip_auto_torrent"]
    from src.trackersetup import api_trackers

    tracker_ids = [t.lower() for t in api_trackers] + ["ptp", "btn", "hdb", "orpheus"]
    use_sonarr = prep_instance.config["DEFAULT"].get("use_sonarr", False)
    use_radarr = prep_instance.config["DEFAULT"].get("use_radarr", False)
    meta.print_tracker_messages = prep_instance.config["DEFAULT"].get("print_tracker_messages", False)
    meta.print_tracker_links = prep_instance.config["DEFAULT"].get("print_tracker_links", True)
    from src.tracker_descriptions import resolve_description_mode

    description_mode = resolve_description_mode(prep_instance.config["DEFAULT"].get("tracker_description_mode", "text"))
    if meta.only_id:
        description_mode = resolve_description_mode("ids")
    meta.tracker_description_mode = description_mode.value
    meta.keep_images = description_mode.imports_images
    meta.skip_tracker_descriptions = not description_mode.imports_text
    mkbrr_threads = prep_instance.config["DEFAULT"].get("mkbrr_threads", "0")
    meta.mkbrr_threads = mkbrr_threads

    # make sure these are set in meta
    meta.we_checked_tvdb = False
    meta.we_checked_tmdb = False
    meta.we_asked_tvmaze = False
    meta.audio_languages = None
    meta.subtitle_languages = None
    meta.aither_trumpable = None
    meta.anime = False
    meta.not_anime = False
    meta.subtitle_files = cast(list[str], [])
    meta.adult_media = False

    folder_id = Path(meta.path or "").name
    if not meta.uuid:
        meta.uuid = folder_id
    if meta.isdir:
        meta.basename_no_ext = folder_id
    else:
        meta.basename_no_ext = Path(folder_id).stem
    if not Path(f"{base_dir}{'/' + 'tmp' + '/'}{meta.uuid}").exists():
        Path(f"{base_dir}{'/' + 'tmp' + '/'}{meta.uuid}").mkdir(parents=True, mode=0o700, exist_ok=True)

    logger.debug(f"[cyan]ID: {meta.uuid}")

    return use_sonarr, use_radarr, client, meta.skip_tracker_descriptions, hash_ids, tracker_ids


async def detect_disc_and_category(prep_instance: Any, meta: Meta) -> tuple[str, dict[str, Any]]:
    try:
        meta.is_disc, videoloc, bdinfo, meta.discs = await prep_instance.disc_info_manager.get_disc(meta)
    except Exception:
        raise
    logger.debug(f"[blue]is_disc: [yellow]{meta.is_disc}[/yellow][/blue]")

    # A CLI category is an explicit instruction, not only a signal to skip
    # automatic detection.  Content-specific preparation below routes on
    # ``meta.category``, so normalise the manual value before that routing.
    if isinstance(meta.manual_category, str) and meta.manual_category.strip():
        meta.category = meta.manual_category.strip().upper()

    # If category is manually set to BOOK, ensure meta.audiobook is set if audio files are present
    if meta.category == "BOOK" and not meta.audiobook:
        path_to_check = Path(meta.path) if meta.path else None
        if path_to_check and path_to_check.exists():
            from src.audio_classifier import AUDIOBOOK_CONTAINER_EXTENSIONS, SHARED_AUDIO_EXTENSIONS

            audio_exts = SHARED_AUDIO_EXTENSIONS | AUDIOBOOK_CONTAINER_EXTENSIONS
            if path_to_check.is_file() and path_to_check.suffix.lower() in audio_exts:
                meta.audiobook = True
            elif path_to_check.is_dir():
                for item in path_to_check.rglob("*"):
                    if item.is_file() and item.suffix.lower() in audio_exts:
                        meta.audiobook = True
                        break

    # Auto-detect audio release category (BOOK audiobook vs MUSIC) if category/manual_category is not already set and it's not a disc
    if not meta.category and not meta.manual_category and not meta.is_disc:
        path_to_check = Path(meta.path) if meta.path else None
        if path_to_check and path_to_check.exists():
            from src.audio_classifier import detect_audio_category

            audio_res = await detect_audio_category(meta, path_to_check)
            if audio_res.category in ("BOOK", "MUSIC"):
                meta.category = audio_res.category
                meta.audiobook = audio_res.is_audiobook
                logger.debug(f"[cyan]Auto-detected category: {meta.category}[/cyan]")
                if audio_res.is_audiobook:
                    logger.debug("[cyan]Subtype: AUDIOBOOK[/cyan]")
                if audio_res.evidence:
                    logger.debug("[cyan]Evidence:[/cyan]")
                    for ev in audio_res.evidence:
                        logger.debug(f"[cyan]- {ev}[/cyan]")
            elif audio_res.category == "AMBIGUOUS":
                unattended = getattr(meta, "unattended", False)
                unattended_confirm = getattr(meta, "unattended_confirm", False)

                logger.warning("[yellow]Audio category is ambiguous: could not confidently determine whether this is MUSIC or an AUDIOBOOK.[/yellow]")
                if audio_res.evidence:
                    logger.warning("[yellow]Evidence evaluated:[/yellow]")
                    for ev in audio_res.evidence:
                        logger.warning(f"[yellow]- {ev}[/yellow]")

                if not unattended or (unattended and unattended_confirm):
                    try:
                        choice = cli_ui.ask_choice(
                            "Choose category for audio release:",
                            choices=["1. Music", "2. Audiobook"],
                        )
                    except EOFError, KeyboardInterrupt:
                        logger.error("[bold red]Category selection cancelled or failed.[/bold red]")
                        sys.exit(1)
                    if choice is None:
                        logger.error("[bold red]Category selection cancelled or failed.[/bold red]")
                        sys.exit(1)
                    if choice.startswith("1") or choice.lower() == "music":
                        meta.category = "MUSIC"
                        meta.audiobook = False
                    else:
                        meta.category = "BOOK"
                        meta.audiobook = True
                    logger.info(f"[cyan]Category selected interactively: {meta.category}[/cyan]")
                else:
                    logger.error("[bold red]Could not confidently distinguish MUSIC from AUDIOBOOK in unattended mode.[/bold red]")
                    logger.error("[yellow]Specify one of: -c book or -c music[/yellow]")
                    logger.error("[yellow]Skipping this release instead of assigning an unsafe category.[/yellow]")
                    sys.exit(1)

    # Fallback auto-detect BOOK category if category/manual_category is not already set and it's not a disc
    if not meta.category and not meta.manual_category and not meta.is_disc:
        is_book = False
        video_extensions = {".mkv", ".mp4", ".ts"}

        path_to_check = meta.path
        if path_to_check and Path(path_to_check).exists():
            if Path(path_to_check).is_dir():
                has_books = False
                has_audio = False
                has_video = False
                for _root, _, files in os.walk(path_to_check):
                    for file in files:
                        ext = Path(file).suffix.lower()
                        if ext in BOOK_EXTENSIONS:
                            has_books = True
                        elif ext in AUDIOBOOK_EXTENSIONS:
                            has_audio = True
                        elif ext in video_extensions:
                            has_video = True
                # If we have books/audio files and NO video files, classify as BOOK
                if (has_books or has_audio) and not has_video:
                    is_book = True
            else:
                ext = Path(path_to_check).suffix.lower()
                if ext in BOOK_EXTENSIONS or ext in AUDIOBOOK_EXTENSIONS:
                    is_book = True

        if is_book:
            meta.category = "BOOK"
            logger.debug("[cyan]Auto-detected category: BOOK[/cyan]")

    # Auto-detect GAME category if category/manual_category is not already set and it's not a disc
    if not meta.category and not meta.manual_category and not meta.is_disc:
        is_game = False
        game_extensions = {
            ".3ds",
            ".3dsx",
            ".cci",
            ".cdi",
            ".chd",
            ".cia",
            ".cso",
            ".exe",
            ".gcm",
            ".gdi",
            ".hdf",
            ".iso",
            ".nca",
            ".nds",
            ".nsp",
            ".nsz",
            ".pbp",
            ".pkg",
            ".rap",
            ".rar",
            ".srl",
            ".szs",
            ".vpk",
            ".wbfs",
            ".wud",
            ".wux",
            ".xbe",
            ".xci",
            ".xcz",
            ".xex",
        }
        video_extensions = {".mkv", ".mp4", ".ts"}
        game_groups = {"tenoke", "rune", "flt", "plaza", "codex", "skidrow", "prophet", "gog", "darkzer0", "doge", "tinyiso", "razor1911", "outlaws", "alias", "simplex"}

        path_to_check = meta.path
        if path_to_check and Path(path_to_check).exists():
            has_game_ext = False
            has_video = False
            has_steam_link = False
            has_game_group = False

            base_name_lower = Path(path_to_check).name.lower()
            for group in game_groups:
                if f"-{group}" in base_name_lower or base_name_lower.endswith(group):
                    has_game_group = True
                    break

            if Path(path_to_check).is_dir():
                for root, _, files in os.walk(path_to_check):
                    for file in files:
                        file_lower = file.lower()
                        ext = Path(file_lower).suffix
                        if ext in game_extensions:
                            has_game_ext = True
                        elif ext in video_extensions:
                            has_video = True
                        elif ext == ".nfo":
                            nfo_path = Path(root) / file
                            try:
                                async with aiofiles.open(nfo_path, encoding="utf-8", errors="ignore") as nf:
                                    nfo_content = await nf.read()
                                    if _nfo_has_store_link(nfo_content):
                                        has_steam_link = True
                            except Exception:
                                with contextlib.suppress(Exception):
                                    async with aiofiles.open(nfo_path, encoding="latin-1", errors="ignore") as nf:
                                        nfo_content = await nf.read()
                                        if _nfo_has_store_link(nfo_content):
                                            has_steam_link = True
            else:
                ext = Path(base_name_lower).suffix
                if ext in game_extensions:
                    has_game_ext = True

            if has_steam_link or ((has_game_ext or has_game_group) and not has_video):
                is_game = True

        if is_game:
            meta.category = "GAME"
            logger.debug("[cyan]Auto-detected category: GAME[/cyan]")

    return videoloc, bdinfo


async def process_media_files(prep_instance: Any, meta: Meta, videoloc: str, bdinfo: dict[str, Any]) -> tuple[str, str, str, str, str, dict[str, Any] | None, str]:
    filename = ""
    untouched_filename = ""
    videopath = ""
    search_term = ""
    search_file_folder = ""
    mi: dict[str, Any] | None = None
    video = ""
    base_dir = meta.base_dir
    meta_path: str = meta.path or ""

    if meta.is_disc == "BDMV":
        video, meta.scene, meta.imdb_id = await prep_instance.scene_manager.is_scene(meta_path, meta, meta.imdb_id)
        meta.filelist = []  # No filelist for discs, use path
        search_term = Path(meta_path).name
        search_file_folder = "folder"
        try:
            title, secondary_title, extracted_year = await prep_instance.name_manager.extract_title_and_year(meta, video)
            logger.debug(f"Title: {title}, Secondary Title: {secondary_title}, Year: {extracted_year}")
            if secondary_title:
                meta.secondary_title = secondary_title
            if extracted_year and not meta.year:
                meta.year = int(extracted_year)
            if title:
                filename = title
                untouched_filename = search_term
            else:
                guess_name = bdinfo["title"].replace("-", " ")
                untouched_filename = bdinfo["title"]
                filename = str(guessit_fn(re.sub(r"[^0-9a-zA-Z\[\\]]+", " ", guess_name), {"excludes": ["country", "language"]}).get("title", ""))

            try:
                is_hfr = bdinfo["video"][0]["fps"].split()[0] if bdinfo["video"] else "25"
                if int(float(is_hfr)) > 30:
                    meta.hfr = True
                else:
                    meta.hfr = False
            except Exception:
                meta.hfr = False

            try:
                meta.search_year = guessit_fn(bdinfo["title"])["year"]
            except Exception:
                meta.search_year = ""
        except Exception:
            guess_name = bdinfo["label"].replace("-", " ")
            filename = str(guessit_fn(re.sub(r"[^0-9a-zA-Z\[\\]]+", " ", guess_name), {"excludes": ["country", "language"]}).get("title", ""))
            untouched_filename = bdinfo["label"]
            try:
                meta.search_year = guessit_fn(bdinfo["label"])["year"]
            except Exception:
                meta.search_year = ""

        if not meta.resolution or meta.resolution is None:
            meta.resolution = await mi_resolution(
                bdinfo["video"][0]["res"],
                guessit_fn(video),
                width="OTHER",
                scan="p",
            )

        meta.sd = await video_manager.is_sd(meta.resolution)
        mi = None

    elif meta.is_disc == "DVD":
        video, meta.scene, meta.imdb_id = await prep_instance.scene_manager.is_scene(meta_path, meta, meta.imdb_id)
        meta.filelist = []
        search_term = Path(meta_path).name
        search_file_folder = "folder"
        title, secondary_title, extracted_year = await prep_instance.name_manager.extract_title_and_year(meta, video)
        logger.debug(f"Title: {title}, Secondary Title: {secondary_title}, Year: {extracted_year}")
        if secondary_title:
            meta.secondary_title = secondary_title
        if extracted_year and not meta.year:
            meta.year = int(extracted_year)
        if title:
            filename = title
            untouched_filename = search_term
        else:
            guess_name = meta.discs[0]["path"].replace("-", " ")
            filename = str(guessit_fn(guess_name, {"excludes": ["country", "language"]}).get("title", ""))
            untouched_filename = Path(meta.discs[0]["path"]).parent.name
        try:
            meta.search_year = guessit_fn(meta.discs[0]["path"])["year"]
        except Exception:
            meta.search_year = ""
        if not meta.edit:
            mi = await export_info(
                f"{meta.discs[0]['path']}/VTS_{meta.discs[0]['main_set'][0][:2]}_0.IFO",
                False,
                meta.uuid,
                meta.base_dir,
                is_dvd=True,
            )
            meta.mediainfo = mi
        else:
            mi = meta.mediainfo

        meta.dvd_size = await prep_instance.disc_info_manager.get_dvd_size(meta.discs, meta.manual_dvds)
        meta.resolution, meta.hfr = await video_manager.get_resolution(guessit_fn(video), meta.uuid, base_dir, meta)
        meta.sd = await video_manager.is_sd(meta.resolution)

    elif meta.is_disc == "HDDVD":
        video, meta.scene, meta.imdb_id = await prep_instance.scene_manager.is_scene(meta_path, meta, meta.imdb_id)
        meta.filelist = []
        search_term = Path(meta_path).name
        search_file_folder = "folder"
        guess_name = meta.discs[0]["path"].replace("-", "")
        filename = str(guessit_fn(guess_name, {"excludes": ["country", "language"]}).get("title", ""))
        untouched_filename = Path(meta.discs[0]["path"]).name
        videopath = meta.discs[0]["largest_evo"]
        try:
            meta.search_year = guessit_fn(meta.discs[0]["path"])["year"]
        except Exception:
            meta.search_year = ""
        if not meta.edit:
            mi = await export_info(meta.discs[0]["largest_evo"], False, meta.uuid, meta.base_dir)
            meta.mediainfo = mi
        else:
            mi = meta.mediainfo
        meta.resolution, meta.hfr = await video_manager.get_resolution(guessit_fn(video), meta.uuid, base_dir, meta)
        meta.sd = await video_manager.is_sd(meta.resolution)

    else:
        if meta.category == "BOOK" or (meta.manual_category or "").upper() == "BOOK":
            videopath, filelist, search_term, search_file_folder = prep_instance._resolve_book_filelist(meta, videoloc)
            video = videopath
        elif meta.category == "GAME" or (meta.manual_category or "").upper() == "GAME":
            videopath, filelist, search_term, search_file_folder = prep_instance._resolve_game_filelist(meta, videoloc)
            video = videopath
        else:
            videopath, meta.filelist = await video_manager.get_video(videoloc, (meta.mode if meta.mode is not None else "non_cli"), meta.sorted_filelist)
            filelist = meta.filelist
            meta.filelist = filelist
            search_term = Path(filelist[0]).name if filelist else ""
            search_file_folder = "file"

            # Scan for external subtitle files
            meta.subtitle_files = cast(list[str], [])
            subtitle_exts = {".srt", ".sub", ".vtt", ".ssa", ".ass", ".idx"}
            if meta.isdir:
                for root, _, files in os.walk(meta_path):
                    if any(x in root.upper() for x in ["BDMV", "VIDEO_TS", "HVDVD_TS"]):
                        continue
                    for file in files:
                        ext = Path(file).suffix.lower()
                        if ext in subtitle_exts:
                            meta.subtitle_files.append(str(Path(Path(root) / file).resolve()))
            else:
                parent_dir = str(Path(meta_path).parent)
                if parent_dir and Path(parent_dir).exists():
                    base_name = Path(meta_path).stem
                    for file in (p.name for p in Path(parent_dir).iterdir()):
                        if (Path(parent_dir) / file).is_file():
                            ext = Path(file).suffix.lower()
                            if ext in subtitle_exts and file.lower().startswith(base_name.lower()):
                                meta.subtitle_files.append(str(Path(Path(parent_dir) / file).resolve()))
            meta.subtitle_files = sorted(set(meta.subtitle_files))

        video, meta.scene, meta.imdb_id = await prep_instance.scene_manager.is_scene(videopath, meta, meta.imdb_id)
        if meta.category == "BOOK" or (meta.manual_category or "").upper() == "BOOK":
            orig_ext = Path(videopath).suffix
            if video.endswith(".mkv") and not videopath.endswith(".mkv"):
                video = video[:-4] + orig_ext

        try:
            title, secondary_title, extracted_year = await prep_instance.name_manager.extract_title_and_year(meta, video)
            logger.debug(f"Title: {title}, Secondary Title: {secondary_title}, Year: {extracted_year}")
            if secondary_title:
                meta.secondary_title = secondary_title
            if extracted_year and not meta.year:
                meta.year = int(extracted_year)

            guess_name = (Path(meta.path).name.replace("_", "").replace("-", "") if meta.path else "") if meta.isdir else ntpath.basename(video).replace("-", " ")
        except Exception as e:
            logger.error(f"[red]Error extracting title and year: {e}[/red]")
            raise Exception(f"Error extracting title and year: {e}") from e

        try:
            if title:
                filename = title
                meta.regex_title = title
                meta.regex_secondary_title = secondary_title
                meta.regex_year = extracted_year
            else:
                try:
                    filename = str(
                        guessit_fn(re.sub(r"[^0-9a-zA-Z\[\\]]+", " ", guess_name), {"excludes": ["country", "language"]}).get(
                            "title", str(guessit_fn(re.sub("[^0-9a-zA-Z]+", " ", guess_name), {"excludes": ["country", "language"]}).get("title", ""))
                        )
                    )
                except Exception:
                    try:
                        guess_name = ntpath.basename(video).replace("-", " ")
                        filename = str(
                            guessit_fn(re.sub(r"[^0-9a-zA-Z\[\\]]+", " ", guess_name), {"excludes": ["country", "language"]}).get(
                                "title", str(guessit_fn(re.sub("[^0-9a-zA-Z]+", " ", guess_name), {"excludes": ["country", "language"]}).get("title", ""))
                            )
                        )
                    except Exception as e:
                        logger.error(f"[red]Error extracting title from video name: {e}[/red]")
                        raise Exception(f"Error extracting title from video name: {e}") from e

            untouched_filename = Path(video).name
        except Exception as e:
            logger.error(f"[red]Error processing filename: {e}[/red]")
            raise Exception(f"Error processing filename: {e}") from e

        try:
            if meta.category == "BOOK" or (meta.manual_category or "").upper() == "BOOK":
                await prep_instance._gather_book_prep(meta, videopath, base_dir)
            elif meta.category == "GAME" or (meta.manual_category or "").upper() == "GAME":
                meta.filename = filename
                await prep_instance._gather_game_prep(meta, videopath, base_dir)
            else:
                # rely only on guessit for search_year for tv matching
                try:
                    meta.search_year = guessit_fn(video)["year"]
                except Exception:
                    meta.search_year = ""

                if not meta.edit:
                    mi = await export_info(videopath, (meta.isdir), meta.uuid, base_dir, is_dvd=(meta.is_disc == "DVD"))
                    meta.mediainfo = mi
                else:
                    mi = meta.mediainfo

                if not meta.resolution or meta.resolution is None:
                    meta.resolution, meta.hfr = await video_manager.get_resolution(guessit_fn(video), meta.uuid, base_dir, meta)

                meta.sd = await video_manager.is_sd(meta.resolution)
        except Exception as e:
            logger.error(f"[red]Error processing Mediainfo: {e}[/red]")
            raise Exception(f"Error processing Mediainfo: {e}") from e

    filename = str(filename)
    untouched_filename = str(untouched_filename)
    if " AKA " in filename.replace(".", " "):
        filename = filename.split("AKA")[0]
    meta.filename = filename
    meta.bdinfo = bdinfo

    return filename, untouched_filename, videopath, search_term, search_file_folder, mi, video


def calculate_source_size(_prep_instance: Any, meta: Meta, videopath: str) -> None:
    source_size = 0
    if not meta.is_disc:
        # Sum every non-disc file so downstream steps know the total payload size
        filelist = cast(list[str], meta.filelist or [])
        files_to_measure = filelist if filelist else ([videopath] if videopath else [])
        for file_path in files_to_measure:
            if not Path(file_path).is_file():
                logger.debug(f"[yellow]Skipping size check for missing file: {file_path}")
                continue
            try:
                source_size += Path(file_path).stat().st_size
            except OSError as exc:
                logger.debug(f"[yellow]Unable to stat {file_path}: {exc}")

    else:
        # Disc structures can span many files; walk the tree rooted at meta.path
        disc_root = meta.path
        disc_root_str = disc_root if isinstance(disc_root, str) else ""
        if disc_root_str and Path(disc_root_str).exists():
            for root, _, files in os.walk(disc_root_str):
                for name in files:
                    file_path = Path(root) / name
                    try:
                        source_size += Path(file_path).stat().st_size
                    except OSError as exc:
                        logger.debug(f"[yellow]Unable to stat {file_path}: {exc}")
                        continue
        else:
            logger.debug(f"[yellow]Disc path missing, source size set to 0: {disc_root_str}")

    meta.source_size = source_size
    logger.debug(f"[cyan]Calculated source size: {meta.source_size} bytes")


async def validate_media(_prep_instance: Any, meta: Meta) -> None:
    conform_issues = await get_conformance_error(meta)
    if conform_issues:
        upload = False
        if not meta.unattended or (meta.unattended and meta.unattended_confirm):
            try:
                upload = cli_ui.ask_yes_no(
                    "Found Conformance errors in mediainfo (possible cause: corrupted file, incomplete download, new codec, etc...), proceed to upload anyway?", default=False
                )
            except EOFError:
                logger.info("\n[red]Exiting on user request (Ctrl+C)[/red]")
                await cleanup_manager.cleanup()
                cleanup_manager.reset_terminal()
                sys.exit(1)
        if upload is False:
            logger.info("[red]Not uploading. Check if the file has finished downloading and can be played back properly (uncorrupted).")
            tmp_dir = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}"
            # Cleanup meta so we don't reuse it later
            if Path(tmp_dir).exists():
                try:
                    for file in (p.name for p in Path(tmp_dir).iterdir()):
                        file_path = Path(tmp_dir) / file
                        if file_path.is_file() and file.endswith((".txt", ".json")):
                            file_path.unlink()
                            logger.debug(f"[yellow]Removed temporary metadata file: {file_path}[/yellow]")
                except Exception as e:
                    logger.error(f"[red]Error cleaning up temporary metadata files: {e}[/red]", extra={"highlighter": None})
            logger.info("[red]Not uploading due to conformance errors.[/red]")
            raise Exception("Conformance errors found in mediainfo")

    meta.valid_mi = True
    if not meta.is_disc and meta.category not in ("BOOK", "GAME"):
        try:
            valid_mi = validate_mediainfo(meta)
        except NoAudioMediaError as e:
            logger.info(f"[red]MediaInfo validation failed: {e!s}[/red]")
            raise NoAudioMediaError(f"{meta.ua_name} does not support no audio media. Details: {e!s}") from e
        except Exception as e:
            logger.info(f"[red]MediaInfo validation failed: {e!s}[/red]")
            raise
        if not valid_mi:
            logger.info("[red]MediaInfo validation failed. This file does not contain (Unique ID).")
            meta.valid_mi = False
            await asyncio.sleep(2)

    mediainfo_tracks = meta.mediainfo.get("media", {}).get("track") or []
    meta.has_multiple_default_subtitle_tracks = len([track for track in mediainfo_tracks if track["@type"] == "Text" and track["Default"] == "Yes"]) > 1

    # Check if there's a language restriction
    if meta.has_languages:
        try:
            parsed_info = await languages_manager.parsed_mediainfo(meta)
            audio_languages = [audio_track["language"].lower() for audio_track in parsed_info.get("audio", []) if audio_track.get("language")]
            any_of_languages = meta.has_languages.lower().split(",")
            if all(len(lang.strip()) == 2 for lang in any_of_languages):
                raise Exception(f"Warning: Languages should be full names, not ISO codes. Found: {any_of_languages}")
            # We need to have user input languages and file must have audio tracks.
            if len(any_of_languages) > 0 and len(audio_languages) > 0 and not set(any_of_languages).intersection(set(audio_languages)):
                logger.info(f"[red] None of the required languages ({meta.has_languages}) is available on the file {audio_languages}")
                raise Exception("No matching languages")
        except Exception as e:
            logger.info(f"[red]{e}[/red]")
            raise Exception("Language check failed") from e


async def process_trackers_and_torrent(
    prep_instance: Any, meta: Meta, client: Clients, hash_ids: list[str], tracker_ids: list[str], _search_term: str, _search_file_folder: str
) -> None:
    if "description" not in meta or meta.description is None:
        meta.description = ""

    meta.skip_trackers = False

    if meta.trackers:
        trackers = meta.trackers
    else:
        default_trackers = prep_instance.config["TRACKERS"].get("default_trackers", "")
        trackers = [tracker.strip() for tracker in default_trackers.split(",")]

    if isinstance(trackers, str):
        trackers = [t.strip().upper() for t in trackers.split(",")] if "," in trackers else [trackers.strip().upper()]
    else:
        trackers = [t.strip().upper() for t in trackers]
    meta.trackers = cast(list[str], trackers)
    meta.requested_trackers = cast(list[str], trackers)

    # Find one reusable torrent while all local files (including external
    # subtitles) are known. Its path is cached for the upload stage, which
    # prevents a second full client search later in the run.
    if not any(meta.get(id_type) for id_type in hash_ids + tracker_ids) and not meta.skip_trackers and not meta.edit:
        reuse_torrent_path = await client.find_existing_torrent(meta)
        if reuse_torrent_path:
            meta.reuse_torrent_path = reuse_torrent_path
            if meta.subtitle_files and client._torrent_includes_all_local_subtitles(reuse_torrent_path, meta):
                meta.subs_reuse_torrent_path = reuse_torrent_path
            else:
                meta.base_reuse_torrent_path = reuse_torrent_path
            try:
                meta.infohash = Torrent.read(reuse_torrent_path).infohash
            except Exception as e:
                logger.debug(f"[yellow]Unable to read infohash from cached torrent: {e}")
            # Fetch properties only: this preserves comment/tracker-ID discovery
            # without running another name-based torrent search or exporting it.
            await client.get_ptp_from_hash(meta, pathed=True, client_name=meta.reuse_torrent_client)


async def search_metadata(
    prep_instance: Any,
    meta: Meta,
    filename: str,
    untouched_filename: str,
    videopath: str,
    search_term: str,
    search_file_folder: str,
    use_sonarr: bool,
    use_radarr: bool,
    skip_tracker_descriptions: bool,
    client: Clients,
    _bdinfo: dict[str, Any],
    mi: dict[str, Any] | None,
) -> None:
    # Ensure all manual IDs have proper default values
    meta.tmdb_manual = meta.tmdb_manual or 0
    meta.imdb_manual = meta.imdb_manual or 0
    meta.mal_manual = meta.mal_manual or 0
    meta.tvdb_manual = meta.tvdb_manual or 0
    meta.tvmaze_manual = meta.tvmaze_manual or 0

    # Set tmdb_id
    try:
        if meta.tmdb_manual:
            meta.tmdb_id = int(meta.tmdb_manual)
        elif not meta.tmdb_id:
            meta.tmdb_id = 0
    except ValueError, TypeError:
        if not meta.tmdb_id:
            meta.tmdb_id = 0

    # Set imdb_id with proper handling for 'tt' prefix
    try:
        if not meta.imdb_id:
            imdb_value = meta.imdb_manual
            if imdb_value:
                if str(imdb_value).startswith("tt"):
                    meta.imdb_id = int(str(imdb_value)[2:])
                else:
                    meta.imdb_id = int(imdb_value)
            else:
                meta.imdb_id = 0
    except ValueError, TypeError:
        meta.imdb_id = 0

    # Set mal_id
    try:
        if meta.mal_manual:
            meta.mal_id = int(meta.mal_manual)
        elif not meta.mal_id:
            meta.mal_id = 0
    except ValueError, TypeError:
        if not meta.mal_id:
            meta.mal_id = 0

    # Set tvdb_id
    try:
        if meta.tvdb_manual:
            meta.tvdb_id = int(meta.tvdb_manual)
        elif not meta.tvdb_id:
            meta.tvdb_id = 0
    except ValueError, TypeError:
        if not meta.tvdb_id:
            meta.tvdb_id = 0

    try:
        if meta.tvmaze_manual:
            meta.tvmaze_id = meta.tvmaze_manual
        elif not meta.tvmaze_id:
            meta.tvmaze_id = 0
    except ValueError, TypeError:
        if not meta.tvmaze_id:
            meta.tvmaze_id = 0

    # Auto-detect category from video name if category is still missing
    if not meta.category:
        meta.category = await prep_instance.get_cat(videopath, meta)
    else:
        meta.category = meta.category.upper()

    ids = None
    if not meta.skip_trackers:
        if meta.category == "TV" and use_sonarr and meta.tvdb_id == 0:
            ids = await prep_instance.sonarr_manager.get_sonarr_data(filename=meta.path, title=meta.filename)
            if ids:
                logger.debug(f"TVDB ID: {ids['tvdb_id']}")
                logger.debug(f"IMDB ID: {ids['imdb_id']}")
                logger.debug(f"TVMAZE ID: {ids['tvmaze_id']}")
                logger.debug(f"TMDB ID: {ids['tmdb_id']}")
                logger.debug(f"Genres: {ids['genres']}")
                logger.debug(f"Release Group: {ids['release_group']}")
                logger.debug(f"Year: {ids['year']}")
                if "anime" not in [genre.lower() for genre in ids["genres"]]:
                    meta.not_anime = True
                if meta.tvdb_id == 0 and ids["tvdb_id"] is not None:
                    meta.tvdb_id = ids["tvdb_id"]
                if meta.imdb_id == 0 and ids["imdb_id"] is not None:
                    meta.imdb_id = ids["imdb_id"]
                if meta.tvmaze_id == 0 and ids["tvmaze_id"] is not None:
                    meta.tvmaze_id = ids["tvmaze_id"]
                if meta.tmdb_id == 0 and ids["tmdb_id"] is not None:
                    meta.tmdb_id = ids["tmdb_id"]
                if meta.manual_year == 0 and ids["year"] is not None:
                    meta.manual_year = ids["year"]
            else:
                ids = None

        if meta.category == "MOVIE" and use_radarr and meta.tmdb_id == 0:
            ids = await prep_instance.radarr_manager.get_radarr_data(filename=meta.uuid)
            if ids:
                logger.debug(f"IMDB ID: {ids['imdb_id']}")
                logger.debug(f"TMDB ID: {ids['tmdb_id']}")
                logger.debug(f"Genres: {ids['genres']}")
                logger.debug(f"Year: {ids['year']}")
                logger.debug(f"Release Group: {ids['release_group']}")
                if meta.imdb_id == 0 and ids["imdb_id"] is not None:
                    meta.imdb_id = ids["imdb_id"]
                if meta.tmdb_id == 0 and ids["tmdb_id"] is not None:
                    meta.tmdb_id = ids["tmdb_id"]
                if meta.manual_year == 0 and ids["year"] is not None:
                    meta.manual_year = ids["year"]
            else:
                ids = None

        # check if we've already searched torrents
        if "base_torrent_created" not in meta:
            meta.base_torrent_created = False
        if "we_checked_them_all" not in meta:
            meta.we_checked_them_all = False

        # if not auto qbittorrent search, this also checks with the infohash if passed.
        if meta.infohash is not None and not meta.base_torrent_created and not meta.we_checked_them_all and not ids:
            meta = await client.get_ptp_from_hash(meta)

        if not meta.edit and not ids:
            # Reuse information from trackers with fallback
            await prep_instance.tracker_data_manager.get_tracker_data(
                videopath, meta, search_term, search_file_folder, meta.category, skip_tracker_descriptions=skip_tracker_descriptions
            )

        if meta.category == "TV" and use_sonarr and meta.tvdb_id != 0 and ids is None and not meta.matched_tracker:
            ids = await prep_instance.sonarr_manager.get_sonarr_data(tvdb_id=meta.tvdb_id)
            if ids:
                logger.debug(f"TVDB ID: {ids['tvdb_id']}")
                logger.debug(f"IMDB ID: {ids['imdb_id']}")
                logger.debug(f"TVMAZE ID: {ids['tvmaze_id']}")
                logger.debug(f"TMDB ID: {ids['tmdb_id']}")
                logger.debug(f"Genres: {ids['genres']}")
                if "anime" not in [genre.lower() for genre in ids["genres"]]:
                    meta.not_anime = True
                if meta.tvdb_id == 0 and ids["tvdb_id"] is not None:
                    meta.tvdb_id = ids["tvdb_id"]
                if meta.imdb_id == 0 and ids["imdb_id"] is not None:
                    meta.imdb_id = ids["imdb_id"]
                if meta.tvmaze_id == 0 and ids["tvmaze_id"] is not None:
                    meta.tvmaze_id = ids["tvmaze_id"]
                if meta.tmdb_id == 0 and ids["tmdb_id"] is not None:
                    meta.tmdb_id = ids["tmdb_id"]
                if meta.manual_year == 0 and ids["year"] is not None:
                    meta.manual_year = ids["year"]
            else:
                ids = None

        if meta.category == "MOVIE" and use_radarr and meta.tmdb_id != 0 and ids is None and not meta.matched_tracker:
            ids = await prep_instance.radarr_manager.get_radarr_data(tmdb_id=meta.tmdb_id)
            if ids:
                logger.debug(f"IMDB ID: {ids['imdb_id']}")
                logger.debug(f"TMDB ID: {ids['tmdb_id']}")
                logger.debug(f"Genres: {ids['genres']}")
                logger.debug(f"Year: {ids['year']}")
                logger.debug(f"Release Group: {ids['release_group']}")
                if meta.imdb_id == 0 and ids["imdb_id"] is not None:
                    meta.imdb_id = ids["imdb_id"]
                if meta.tmdb_id == 0 and ids["tmdb_id"] is not None:
                    meta.tmdb_id = ids["tmdb_id"]
                if meta.manual_year == 0 and ids["year"] is not None:
                    meta.manual_year = ids["year"]
            else:
                ids = None

    # if there's no region/distributor info, lets ping some unit3d trackers and see if we get it
    ping_unit3d_config = prep_instance.config["DEFAULT"].get("ping_unit3d", False)
    if (not meta.region or not meta.distributor) and meta.is_disc in ("BDMV", "DVD") and ping_unit3d_config and not meta.edit and not meta.site_check:
        await prep_instance.tracker_data_manager.ping_unit3d(meta)

    # the first user override check that allows to set metadata ids.
    # it relies on imdb or tvdb already being set.
    user_overrides = prep_instance.config["DEFAULT"].get("user_overrides", False)
    if user_overrides and (meta.imdb_id != 0 or meta.tvdb_id != 0):
        meta = await prep_instance.overrides.get_source_override(meta, other_id=True)
        category = meta.category
        meta.category = str(category).upper() if category is not None else ""
        # set a flag so that the other check later doesn't run
        meta.no_override = True

    logger.debug("ID inputs into prep")
    logger.debug(f"Category: {meta.category}")
    logger.debug(f"Raw TVDB ID: {meta.tvdb_id} (type: {type(meta.tvdb_id).__name__})")
    logger.debug(f"Raw IMDb ID: {meta.imdb_id} (type: {type(meta.imdb_id).__name__})")
    logger.debug(f"Raw TMDb ID: {meta.tmdb_id} (type: {type(meta.tmdb_id).__name__})")
    logger.debug(f"Raw TVMAZE ID: {meta.tvmaze_id} (type: {type(meta.tvmaze_id).__name__})")
    logger.debug(f"Raw MAL ID: {meta.mal_id} (type: {type(meta.mal_id).__name__})")

    if meta.mal_id != 0:
        meta.anime = True
        meta.not_anime = True

    logger.info("[yellow]Building meta data.....")

    manual_language = meta.manual_language
    if isinstance(manual_language, str) and manual_language:
        meta.original_language = manual_language.lower()

    if meta.category == "BOOK":
        meta.type = Path(videopath).suffix.lstrip(".").upper()
        if meta.type in ("CBR", "CBZ"):
            meta.comic = True
    elif meta.category == "GAME":
        meta.type = "GAME"
    else:
        meta.type = await video_manager.get_type(videopath, meta.scene, meta.is_disc, meta)

    # if it's not an anime, we can run season/episode checks now to speed the process
    if meta.not_anime and meta.category == "TV":
        meta = await prep_instance.season_episode_manager.get_season_episode(videopath, meta)

    mi_data: dict[str, Any] = mi or {}

    # Run a check against mediainfo to see if it has tmdb/imdb
    if (meta.tmdb_id == 0 or meta.imdb_id == 0) and meta.category not in ("BOOK", "GAME"):
        meta.category, meta.tmdb_id, meta.imdb_id, meta.tvdb_id = await prep_instance.tmdb_manager.get_tmdb_imdb_from_mediainfo(mi_data, meta)

    meta.video_duration = await video_manager.get_video_duration(meta)
    duration = meta.video_duration

    unattended = not (not meta.unattended or (meta.unattended and meta.unattended_confirm))
    debug = bool(meta.debug)

    # run a search to find tmdb and imdb ids if we don't have them
    if int(meta.tmdb_id or 0) == 0 and int(meta.imdb_id or 0) == 0 and meta.category not in ("BOOK", "GAME"):
        year = meta.manual_year or meta.search_year or meta.year if meta.category == "TV" else meta.manual_year or meta.year or meta.search_year
        year_value = _normalize_search_year(year)
        category_pref = meta.category or ""
        tmdb_task: asyncio.Task[tuple[int, str]] = asyncio.create_task(
            prep_instance.tmdb_manager.get_tmdb_id(
                filename,
                year_value,
                category_pref,
                untouched_filename,
                attempted=0,
                debug=debug,
                secondary_title=meta.secondary_title,
                unattended=unattended,
            )
        )
        imdb_task: asyncio.Task[int] = asyncio.create_task(
            imdb_manager.search_imdb(
                filename,
                year_value,
                quickie=True,
                category=category_pref,
                secondary_title=meta.secondary_title,
                untouched_filename=untouched_filename,
                duration=duration,
                unattended=unattended,
            )
        )
        tmdb_result, imdb_result = await asyncio.gather(tmdb_task, imdb_task)
        tmdb_id, category = tmdb_result
        meta.category = category
        meta.tmdb_id = _to_int(tmdb_id)
        meta.imdb_id = _to_int(imdb_result)
        meta.quickie_search = True
        meta.no_ids = True

    # If we have an IMDb ID but no TMDb ID, fetch TMDb ID from IMDb
    if int(meta.imdb_id or 0) != 0 and int(meta.tmdb_id or 0) == 0 and meta.category not in ("BOOK", "GAME"):
        imdb_id_value = _to_int(meta.imdb_id)
        tvdb_id_value = _to_int(meta.tvdb_id)
        search_year_value = _normalize_search_year(meta.search_year)
        category, tmdb_id, original_language, filename_search = await prep_instance.tmdb_manager.get_tmdb_from_imdb(
            imdb_id_value,
            tvdb_id_value if tvdb_id_value else None,
            search_year_value,
            filename,
            debug=meta.debug,
            mode=(meta.mode if meta.mode is not None else "non_cli"),
            category_preference=meta.category,
            imdb_info=meta.imdb_info,
        )

        meta.category = category
        meta.tmdb_id = _to_int(tmdb_id)
        meta.original_language = original_language
        meta.no_ids = filename_search

    no_original_language = False
    if meta.original_language is None:
        no_original_language = True

    # if we have all of the ids, search everything all at once
    if int(meta.imdb_id or 0) != 0 and int(meta.tvdb_id or 0) != 0 and int(meta.tmdb_id or 0) != 0 and int(meta.tvmaze_id or 0) != 0:
        meta = await prep_instance.metadata_searching_manager.all_ids(meta)

    # Check if IMDb, TMDb, and TVDb IDs are all present
    elif int(meta.imdb_id or 0) != 0 and int(meta.tvdb_id or 0) != 0 and int(meta.tmdb_id or 0) != 0 and not meta.quickie_search:
        meta = await prep_instance.metadata_searching_manager.imdb_tmdb_tvdb(meta, filename)

    # Check if both IMDb and TVDB IDs are present
    elif int(meta.imdb_id or 0) != 0 and int(meta.tvdb_id or 0) != 0 and not meta.quickie_search:
        meta = await prep_instance.metadata_searching_manager.imdb_tvdb(meta, filename)

    # Check if both IMDb and TMDb IDs are present
    elif int(meta.imdb_id or 0) != 0 and int(meta.tmdb_id or 0) != 0 and not meta.quickie_search:
        meta = await prep_instance.metadata_searching_manager.imdb_tmdb(meta, filename)

    # we should have tmdb id one way or another, so lets get data if needed
    if int(meta.tmdb_id or 0) != 0:
        await prep_instance.tmdb_manager.set_tmdb_metadata(meta, filename)

    # If there was no original language set before the combined metadata searching, tvdb changes mean we might have set a bad tvdb series name
    # Now that we have original language, we can safely kill the tvdb series name if it was en original to account for the change
    if meta.tvdb_series_name and (meta.original_language if meta.original_language is not None else "en") == "en" and meta.tmdb_id != 0 and no_original_language:
        meta.tvdb_series_name = None

    # If there's a mismatch between IMDb and TMDb IDs, try to resolve it
    if meta.imdb_mismatch and "subsplease" not in meta.uuid.lower():
        logger.debug("[yellow]IMDb ID mismatch detected, attempting to resolve...[/yellow]")
        # with refactored tmdb, it quite likely to be correct
        meta.imdb_id = meta.mismatched_imdb_id
        meta.imdb_info = {}

    # Get IMDb ID if not set
    if meta.imdb_id == 0 and meta.category not in ("BOOK", "GAME"):
        try:
            search_year_value = _normalize_search_year(meta.search_year)
            meta.imdb_id = await imdb_manager.search_imdb(
                filename,
                search_year_value,
                quickie=False,
                category=meta.category,
                secondary_title=meta.secondary_title,
                untouched_filename=untouched_filename,
                attempted=0,
                duration=duration,
                unattended=unattended,
            )
        except Exception as e:
            logger.error(f"[red]Error searching IMDb: {e}[/red]")
            raise Exception(f"Error searching IMDb: {e}") from e

    # user might have skipped tmdb earlier, lets double check
    if meta.imdb_id != 0 and meta.tmdb_id == 0 and meta.category not in ("BOOK", "GAME"):
        logger.info("[yellow]No TMDB ID found, attempting to fetch from IMDb...[/yellow]")
        imdb_id_value = _to_int(meta.imdb_id)
        tvdb_id_value = _to_int(meta.tvdb_id)
        search_year_value = _normalize_search_year(meta.search_year)
        category, tmdb_id, original_language, filename_search = await prep_instance.tmdb_manager.get_tmdb_from_imdb(
            imdb_id_value,
            tvdb_id_value if tvdb_id_value else None,
            search_year_value,
            filename,
            debug=meta.debug,
            mode=(meta.mode if meta.mode is not None else "non_cli"),
            category_preference=meta.category,
            imdb_info=meta.imdb_info,
        )

        meta.category = category
        meta.tmdb_id = _to_int(tmdb_id)
        meta.original_language = original_language
        meta.no_ids = filename_search

    tmdb_id_value = _to_int(meta.tmdb_id)
    if tmdb_id_value != 0 and meta.category not in ("BOOK", "GAME"):
        await prep_instance.tmdb_manager.set_tmdb_metadata(meta, filename)

    # Ensure IMDb info is retrieved if it wasn't already fetched or was cleared.
    imdb_id_value = _to_int(meta.imdb_id)
    if not meta.imdb_info and imdb_id_value != 0 and meta.category not in ("BOOK", "GAME"):
        imdb_info = await imdb_manager.get_imdb_info_api(imdb_id_value, manual_language=meta.manual_language, base_dir=meta.base_dir, config=prep_instance.config)
        meta.imdb_info = imdb_info


async def finalize_metadata(
    prep_instance: Any, meta: Meta, videopath: str, bdinfo: dict[str, Any], mi: dict[str, Any] | None, filename: str, _untouched_filename: str, video: str
) -> None:
    check_valid_data = meta.imdb_info.get("title", "")
    if check_valid_data:
        try:
            title = meta.title.lower().strip()
        except KeyError:
            logger.info("[red]Title is missing from TMDB....")
            sys.exit(1)
        aka = meta.imdb_info.get("title", "").strip().lower()
        imdb_aka = meta.imdb_info.get("aka", "").strip().lower()
        year = str(meta.imdb_info.get("year", ""))

        if aka and not meta.aka:
            aka_trimmed = aka[4:].strip().lower() if aka.lower().startswith("aka") else aka.lower()
            difference = SequenceMatcher(None, title, aka_trimmed).ratio()
            if difference >= 0.7 or not aka_trimmed or aka_trimmed in title:
                aka = None

            difference = SequenceMatcher(None, title, imdb_aka).ratio()
            if difference >= 0.7 or not imdb_aka or imdb_aka in title:
                imdb_aka = None

            if aka is not None:
                aka = meta.imdb_info.get("title", "").replace(f"({year})", "").strip() if f"({year})" in aka else meta.imdb_info.get("title", "").strip()
                meta.aka = f"AKA {aka.strip()}"
                meta.title = meta.title.strip()
            elif imdb_aka is not None:
                imdb_aka = meta.imdb_info.get("aka", "").replace(f"({year})", "").strip() if f"({year})" in imdb_aka else meta.imdb_info.get("aka", "").strip()
                meta.aka = f"AKA {imdb_aka.strip()}"
                meta.title = meta.title.strip()

    if not meta.aka or meta.aka is None:
        meta.aka = ""

    # if it was skipped earlier, make sure we have the season/episode data
    if not meta.not_anime and meta.category == "TV":
        meta = await prep_instance.season_episode_manager.get_season_episode(video, meta)

    if meta.category == "TV" and meta.tv_pack:
        await prep_instance.season_episode_manager.check_season_pack_completeness(meta)

    # lets check for tv movies
    meta.tv_movie = False
    if meta.imdb_id != 0:
        is_tv_movie = meta.imdb_info.get("type", "")
        if is_tv_movie:
            tv_movie_keywords = ["tv movie", "tv special", "tvmovie"]
            if any(re.search(rf"(^|,\s*){re.escape(keyword)}(\s*,|$)", is_tv_movie, re.IGNORECASE) for keyword in tv_movie_keywords):
                logger.debug(f"[yellow]Identified as TV Movie based on IMDb type: {is_tv_movie}[/yellow]")
                meta.tv_movie = True

    if (meta.category == "TV" or meta.tv_movie) and meta.category not in ("BOOK", "GAME"):
        both_ids_searched = False
        search_year_value = _normalize_search_year(meta.search_year)
        if meta.tvmaze_id == 0 and meta.tvdb_id == 0:
            tvmaze, tvdb, tvdb_data, tvdb_name = await prep_instance.metadata_searching_manager.get_tvmaze_tvdb(
                filename,
                search_year_value or "",
                meta.imdb_id,
                meta.tmdb_id,
                meta.manual_date,
                meta.tvmaze_manual,
                year=meta.year,
                tv_movie=meta.tv_movie,
                base_dir=meta.base_dir,
            )
            both_ids_searched = True
            if tvmaze:
                meta.tvmaze_id = tvmaze
                logger.debug(f"[blue]Found TVMAZE ID from search: {tvmaze}[/blue]")
            if tvdb:
                meta.tvdb_id = tvdb
                logger.debug(f"[blue]Found TVDB ID from search: {tvdb}[/blue]")
            if tvdb_data:
                meta.tvdb_search_results = tvdb_data
                logger.debug("[blue]Found TVDB search results from search.[/blue]")
            if tvdb_name:
                meta.tvdb_series_name = tvdb_name
                logger.debug(f"[blue]Found TVDB series name from search: {tvdb_name}[/blue]")
        if meta.tvmaze_id == 0 and not both_ids_searched:
            logger.debug("[yellow]No TVMAZE ID found, attempting to fetch...[/yellow]")
            tvmaze_res = await tvmaze_manager.search_tvmaze(
                filename,
                search_year_value or "",
                meta.imdb_id,
                meta.tvdb_id,
                manual_date=meta.manual_date,
                tvmaze_manual=meta.tvmaze_manual,
                return_full_tuple=False,
                base_dir=meta.base_dir,
                config=prep_instance.config,
            )
            meta.tvmaze_id = tvmaze_res if isinstance(tvmaze_res, int) else tvmaze_res[0]
        if meta.tvdb_id == 0:
            logger.debug("[yellow]No TVDB ID found, attempting to fetch...[/yellow]")
            try:
                series_results, series_id = await prep_instance.tvdb_handler.search_tvdb_series(filename=filename, year=meta.year)
                if series_id:
                    meta.tvdb_id = series_id
                    logger.info(f"[blue]Found TVDB series ID from search: {series_id}[/blue]")
                if series_results:
                    meta.tvdb_search_results = series_results
            except Exception as e:
                logger.error(f"[red]Error searching TVDB: {e}[/red]")

        # all your episode data belongs to us
        meta = await prep_instance.metadata_searching_manager.get_tv_data(meta)

        if meta.tvdb_imdb_id:
            imdb = meta.tvdb_imdb_id.replace("tt", "")
            if imdb.isdigit() and imdb != meta.imdb_id:
                episode_info = await imdb_manager.get_imdb_from_episode(imdb)
                if episode_info:
                    series_id = episode_info.get("series", {}).get("series_id", None)
                    if series_id:
                        series_imdb = series_id.replace("tt", "")
                        if series_imdb.isdigit() and int(series_imdb) != meta.imdb_id:
                            logger.debug(f"[yellow]Updating IMDb ID from episode data: {series_imdb}")
                            meta.imdb_id = int(series_imdb)
                            imdb_info = await imdb_manager.get_imdb_info_api(
                                meta.imdb_id, manual_language=meta.manual_language, base_dir=meta.base_dir, config=prep_instance.config
                            )
                            meta.imdb_info = imdb_info
                            check_valid_data = meta.imdb_info.get("title", "")
                            if check_valid_data:
                                title_val = meta.title.strip()
                                aka_val = meta.imdb_info.get("aka", "").strip()
                                year_val = str(meta.imdb_info.get("year", ""))

                                if aka_val:
                                    aka_trimmed = aka_val[4:].strip().lower() if aka_val.lower().startswith("aka") else aka_val.lower()
                                    difference = SequenceMatcher(None, title_val.lower(), aka_trimmed).ratio()
                                    if difference >= 0.7 or not aka_trimmed or aka_trimmed in title_val:
                                        aka_val = None

                                    if aka_val is not None:
                                        if f"({year_val})" in aka_val:
                                            aka_val = meta.imdb_info.get("aka", "").replace(f"({year_val})", "").strip()
                                        else:
                                            aka_val = meta.imdb_info.get("aka", "").strip()
                                        meta.aka = f"AKA {aka_val.strip()}"
                                    else:
                                        meta.aka = ""
                                else:
                                    meta.aka = ""

        if meta.tvdb_series_name and meta.category == "TV":
            series_name = meta.tvdb_series_name
            if series_name and meta.title != series_name:
                logger.debug(f"[yellow]tvdb series name: {series_name}")
                year_match = re.search(r"\b(19|20)\d{2}\b", series_name)
                if year_match:
                    year_match.group(0)
                    series_name = re.sub(r"\s*\b(19|20)\d{2}\b\s*", "", series_name).strip()
                series_name = series_name.replace("(", "").replace(")", "").strip()
                should_use_tvdb_series_name = series_name and not _tvdb_title_drops_existing_leading_article(meta.title, series_name)
                if should_use_tvdb_series_name:
                    meta.title = series_name

    # bluray.com data if config
    get_bluray_info = prep_instance.config["DEFAULT"].get("get_bluray_info", False)
    meta.bluray_score = int(float(prep_instance.config["DEFAULT"].get("bluray_score", 100)))
    meta.bluray_single_score = int(float(prep_instance.config["DEFAULT"].get("bluray_single_score", 100)))
    meta.use_bluray_images = prep_instance.config["DEFAULT"].get("use_bluray_images", False)
    if (
        meta.is_disc in ("BDMV", "DVD")
        and get_bluray_info
        and (meta.distributor is None or meta.region is None)
        and meta.imdb_id != 0
        and not meta.edit
        and not meta.site_check
    ):
        releases = await get_bluray_releases(meta)

        if releases and meta.is_disc in ("BDMV", "DVD") and meta.use_bluray_images:
            # and if we getting bluray/dvd images, we'll rehost them
            url_host_mapping = {
                "ibb.co": "imgbb",
                "pixhost.to": "pixhost",
                "imgbox.com": "imgbox",
                "lostimg.cc": "lostimg",
            }

            approved_image_hosts = ["imgbox", "imgbb", "pixhost"]
            await prep_instance.rehost_images_manager.check_hosts(
                meta,
                "covers",
                url_host_mapping=url_host_mapping,
                img_host_index=1,
                approved_image_hosts=approved_image_hosts,
            )

    # user override check that only sets data after metadata setting
    user_overrides = prep_instance.config["DEFAULT"].get("user_overrides", False)
    if user_overrides and not meta.no_override:
        meta = await prep_instance.overrides.get_source_override(meta)

    meta.video = video

    mi_data: dict[str, Any] = mi or {}
    base_dir = meta.base_dir
    folder_id = Path(str(meta.path)).name

    if meta.category in ("TV", "MOVIE"):
        meta.container = await video_manager.get_container(meta)

        meta.audio, meta.channels, meta.has_commentary = await prep_instance.audio_manager.get_audio_v2(mi_data, meta, bdinfo)

        meta.three_d = await video_manager.is_3d(bdinfo)

        is_disc_value = str(meta.is_disc or "")
        meta.source, meta.type = await get_source(meta.type or "", video, str(meta.path or ""), is_disc_value, meta, folder_id, base_dir)

        meta.uhd = await video_manager.get_uhd(
            meta.type,
            guessit_fn(str(meta.path or "")),
            str(meta.resolution),
            str(meta.path or ""),
        )
        meta.hdr = await video_manager.get_hdr(mi_data, bdinfo)

        # Extract video bitrate
        meta.video_bitrate = None
        if meta.is_disc == "BDMV":
            bd_data = bdinfo
            if not bd_data and meta.discs:
                bd_data = meta.discs[0].get("bdinfo", {})
            if not bd_data and meta.bdinfo:
                bd_data = meta.bdinfo
            if bd_data and bd_data.get("video"):
                raw_bitrate = bd_data["video"][0].get("bitrate")
                if raw_bitrate:
                    match = re.search(r"\d+", str(raw_bitrate).replace(".", "").replace(",", ""))
                    if match:
                        meta.video_bitrate = int(match.group())
        else:
            if mi_data and mi_data.get("media", {}).get("track"):
                tracks = mi_data["media"]["track"]
                video_track = next((track for track in tracks if track.get("@type") == "Video"), None)
                if video_track:
                    raw_bitrate = video_track.get("BitRate") or video_track.get("NominalBitRate") or video_track.get("BitRate_Maximum")
                    if not raw_bitrate or isinstance(raw_bitrate, dict):
                        general_track = next((track for track in tracks if track.get("@type") == "General"), None)
                        if general_track:
                            raw_bitrate = general_track.get("OverallBitRate")
                    if raw_bitrate and not isinstance(raw_bitrate, dict):
                        with contextlib.suppress(ValueError, TypeError):
                            meta.video_bitrate = int(raw_bitrate) // 1000

        # Extract audio bitrate
        meta.audio_bitrate = None
        if meta.is_disc == "BDMV":
            bd_data = bdinfo
            if not bd_data and meta.discs:
                bd_data = meta.discs[0].get("bdinfo", {})
            if not bd_data and meta.bdinfo:
                bd_data = meta.bdinfo
            if bd_data and bd_data.get("audio"):
                raw_bitrate = bd_data["audio"][0].get("bitrate")
                if raw_bitrate:
                    match = re.search(r"\d+", str(raw_bitrate).replace(".", "").replace(",", ""))
                    if match:
                        meta.audio_bitrate = int(match.group())
        else:
            if mi_data and mi_data.get("media", {}).get("track"):
                tracks = mi_data["media"]["track"]
                audio_track = next((track for track in tracks if track.get("@type") == "Audio"), None)
                if audio_track:
                    raw_bitrate = audio_track.get("BitRate") or audio_track.get("NominalBitRate") or audio_track.get("BitRate_Maximum")
                    if raw_bitrate and not isinstance(raw_bitrate, dict):
                        with contextlib.suppress(ValueError, TypeError):
                            meta.audio_bitrate = int(raw_bitrate) // 1000

        # Extract frame rate
        meta.frame_rate = None
        if meta.is_disc == "BDMV":
            bd_data = bdinfo
            if not bd_data and meta.discs:
                bd_data = meta.discs[0].get("bdinfo", {})
            if not bd_data and meta.bdinfo:
                bd_data = meta.bdinfo
            if bd_data and bd_data.get("video"):
                raw_fps = bd_data["video"][0].get("fps")
                if raw_fps:
                    match = re.search(r"\d+(\.\d+)?", str(raw_fps))
                    if match:
                        with contextlib.suppress(ValueError, TypeError):
                            meta.frame_rate = float(match.group())
        else:
            if mi_data and mi_data.get("media", {}).get("track"):
                tracks = mi_data["media"]["track"]
                video_track = next((track for track in tracks if track.get("@type") == "Video"), None)
                if video_track:
                    raw_fps = video_track.get("FrameRate")
                    if not raw_fps or isinstance(raw_fps, dict):
                        general_track = next((track for track in tracks if track.get("@type") == "General"), None)
                        if general_track:
                            raw_fps = general_track.get("FrameRate")
                    if raw_fps and not isinstance(raw_fps, dict):
                        with contextlib.suppress(ValueError, TypeError):
                            meta.frame_rate = float(raw_fps)

        # Extract video resolution width/height
        meta.video_width = None
        meta.video_height = None
        if meta.is_disc == "BDMV":
            if meta.resolution:
                resolution_str = meta.resolution
                with contextlib.suppress(ValueError, TypeError):
                    h = int(resolution_str.lower().replace("p", "").replace("i", ""))
                    meta.video_height = h
                    meta.video_width = round((16 / 9) * h)
        else:
            if mi_data and mi_data.get("media", {}).get("track"):
                tracks = mi_data["media"]["track"]
                video_track = next((track for track in tracks if track.get("@type") == "Video"), None)
                if video_track:
                    with contextlib.suppress(ValueError, TypeError):
                        meta.video_width = int(float(video_track.get("Width", 0)))
                        meta.video_height = int(float(video_track.get("Height", 0)))

        meta.distributor = await get_distributor(meta.distributor)
        if meta.distributor is None:
            meta.distributor = ""

        if meta.is_disc == "BDMV":  # Blu-ray Specific
            meta.region = await get_region(bdinfo, meta.region)
            meta.video_codec = await video_manager.get_video_codec(bdinfo)
        else:
            meta.video_encode, meta.video_codec, meta.has_encode_settings, meta.bit_depth = await video_manager.get_video_encode(mi_data, meta.type, bdinfo)

        if meta.region is None:
            meta.region = ""

        if meta.no_edition is False:
            manual_edition = meta.manual_edition or ""
            meta.edition, meta.repack, meta.webdv = await get_edition(meta.uuid, bdinfo, meta.filelist, manual_edition, meta)
            if "REPACK" in meta.edition:
                repack_match = re.search(r"REPACK[\d]?", meta.edition)
                if repack_match:
                    meta.repack = repack_match.group(0)
                meta.edition = re.sub(r"REPACK[\d]?", "", meta.edition).strip().replace("  ", " ")
        else:
            meta.edition = ""

        meta.valid_mi_settings = True
        if not meta.is_disc and meta.type in ["ENCODE"] and meta.video_codec not in ["AV1"]:
            valid_mi_settings = validate_mediainfo(meta, settings=True)
            if not valid_mi_settings:
                logger.info("[red]MediaInfo validation failed. This file does not contain encode settings.")
                meta.valid_mi_settings = False
                await asyncio.sleep(2)

        meta.stream = await prep_instance.stream_optimized(meta.stream)

        if meta.tag == "-SubsPlease":  # SubsPlease-specific
            tracks = meta.mediainfo.get("media", {}).get("track", [])  # Get all tracks
            bitrate = tracks[1].get("BitRate", "") if len(tracks) > 1 and not isinstance(tracks[1].get("BitRate", ""), dict) else ""  # Check that bitrate is not a dict
            bitrate_old_mediainfo = (
                tracks[0].get("OverallBitRate", "") if len(tracks) > 0 and not isinstance(tracks[0].get("OverallBitRate", ""), dict) else ""
            )  # Check for old MediaInfo
            meta.episode_title = ""
            if (bitrate.isdigit() and int(bitrate) >= 8000000) or (
                (bitrate_old_mediainfo.isdigit() and int(bitrate_old_mediainfo) >= 8000000) and meta.resolution == "1080p"
            ):  # 8Mbps for 1080p
                meta.service = "CR"
            elif (
                bitrate.isdigit() or bitrate_old_mediainfo.isdigit()
            ) and meta.resolution == "1080p":  # Only assign if at least one bitrate is present, otherwise leave it to user
                meta.service = "HIDI"
            elif (bitrate.isdigit() and int(bitrate) >= 4000000) or (
                (bitrate_old_mediainfo.isdigit() and int(bitrate_old_mediainfo) >= 4000000) and meta.resolution == "720p"
            ):  # 4Mbps for 720p
                meta.service = "CR"
            elif (bitrate.isdigit() or bitrate_old_mediainfo.isdigit()) and meta.resolution == "720p":
                meta.service = "HIDI"

        if meta.service in (None, ""):
            meta.service, meta.service_longname = await get_service(video, meta.tag, meta.audio, meta.filename)
        elif meta.service:
            services = cast(dict[str, str], await get_service(get_services_only=True))
            service_code = str(meta.service or "")
            meta.service_longname = max((k for k, v in services.items() if v == service_code), key=len, default=service_code)

        # Parse NFO for scene releases to get service
        if meta.scene and not meta.service and meta.category == "TV":
            await prep_instance.parse_scene_nfo(meta)

        # Combine genres from TMDB and IMDb
        tmdb_genres = meta.genres or []
        imdb_genres = str(meta.imdb_info.get("genres") or "")

        all_genres: list[str] = []
        if tmdb_genres:
            all_genres.extend([g.strip() for g in tmdb_genres if g.strip()])
        if imdb_genres:
            all_genres.extend([g.strip() for g in imdb_genres.split(",") if g.strip()])

        seen: set[str] = set()
        unique_genres: list[str] = []
        for genre in all_genres:
            genre_lower = genre.lower()
            if genre_lower not in seen:
                seen.add(genre_lower)
                unique_genres.append(genre)

        meta.combined_genres = ", ".join(unique_genres) if unique_genres else ""
        meta.adult_media = prep_instance.check_adult_media(meta)

    # Process group tag for all categories (TV, MOVIE, BOOK, etc.)
    if meta.tag is None:
        if meta.we_need_tag:
            meta.tag = await get_tag(meta.scene_name, meta)
        else:
            meta.tag = await get_tag(video, meta)
            # all lowercase filenames will have bad group tag, it's probably a scene release.
            # some extracted files do not match release name so lets double check if it really is a scene release
            if not meta.scene and meta.tag:
                base = Path(video).name
                match = re.match(r"^(.+)\.[a-zA-Z0-9]{3,4}$", Path(video).name)
                if match and (not meta.is_disc or meta.keep_folder):
                    base = match.group(1)
                    is_all_lowercase = base.islower()
                    if is_all_lowercase:
                        release_name, _, _ = await prep_instance.scene_manager.is_scene(videopath, meta, meta.imdb_id, lower=True)
                        if release_name:
                            try:
                                meta.scene_name = release_name
                                meta.tag = await get_tag(release_name, meta)
                            except Exception:
                                logger.error("[red]Error getting tag from scene name, check group tag.[/red]")

    else:
        if not meta.tag.startswith("-") and meta.tag != "":
            meta.tag = f"-{meta.tag}"

    meta = await tag_override(meta)

    # Automatically set personalrelease to True if detected release group matches any of the personal_release_groups tags
    personal_groups = prep_instance.config["DEFAULT"].get("personal_release_groups", [])
    if isinstance(personal_groups, list) and meta.tag:
        detected_group = meta.tag.lstrip("-").lower()
        personal_groups_clean = [str(g).lstrip("-").lower() for g in personal_groups if g]
        if detected_group in personal_groups_clean:
            meta.personalrelease = True
            logger.debug(f"[green]Detected release group in personal_release_groups, automatically setting --personalrelease to True - {detected_group}[/green]")

    channels = meta.channels
    if channels and meta.tag is not None and meta.tag[1:].startswith(channels):
        meta.tag = meta.tag.replace(f"-{channels}", "")

    if meta.no_tag:
        meta.tag = ""

    # return duplicate ids so I don't have to catch every site file
    # this has the other advantage of stringing imdb for this object
    meta.tmdb = meta.tmdb_id
    imdb_id_value = _to_int(meta.imdb_id)
    if imdb_id_value != 0:
        imdb_str = str(imdb_id_value).zfill(7)
        meta.imdb = imdb_str
        meta.imdb_tt = f"tt{imdb_str}"
    else:
        meta.imdb = "0"
        meta.imdb_tt = ""
    meta.mal = meta.mal_id
    meta.tvdb = meta.tvdb_id
    meta.tvmaze = meta.tvmaze_id

    if meta.category == "BOOK":
        meta.container = Path(videopath).suffix.lstrip(".").lower()
        meta.audio = ""
        meta.channels = ""
        meta.has_commentary = False
        meta.three_d = ""
        meta.source = "WEB"
        if not meta.type:
            meta.type = Path(videopath).suffix.lstrip(".").upper()
        if meta.type.upper() in ("CBR", "CBZ"):
            meta.comic = True
        meta.uhd = ""
        meta.hdr = ""
        meta.distributor = ""
        meta.region = ""
        meta.video_codec = ""
        meta.video_encode = ""
        meta.has_encode_settings = False
        meta.bit_depth = "0"
        if not meta.edition:
            meta.edition = str(meta.manual_edition or "").strip()
        meta.repack = ""
        meta.webdv = False

        if not meta.title:
            meta.title = ""
        if not meta.year:
            meta.year = None
        if not meta.overview:
            meta.overview = ""
        if not meta.genres:
            meta.genres = []
    elif meta.category == "GAME":
        meta.container = Path(videopath).suffix.lstrip(".").lower()
        meta.audio = ""
        meta.channels = ""
        meta.has_commentary = False
        meta.three_d = ""
        if not meta.source:
            meta.source = ""
        if not meta.type:
            meta.type = "GAME"
        meta.uhd = ""
        meta.hdr = ""
        meta.distributor = ""
        meta.region = ""
        meta.video_codec = ""
        meta.video_encode = ""
        meta.has_encode_settings = False
        meta.bit_depth = "0"
        meta.edition = ""
        meta.repack = ""
        meta.webdv = False

        if not meta.title:
            meta.title = ""
        if not meta.year:
            meta.year = None
        if not meta.overview:
            meta.overview = ""
        if not meta.genres:
            meta.genres = []

    # Fetch TMDB localized data if needed for active trackers
    if (meta.tmdb_id or 0) != 0 and meta.category in ("TV", "MOVIE"):
        try:
            from src.trackersetup import tracker_class_map

            requirements: dict[str, dict[str, str]] = {}
            for tracker_name in meta.trackers:
                tracker_class = tracker_class_map.get(tracker_name)
                if not tracker_class:
                    continue
                reqs = getattr(tracker_class, "tmdb_localization_requirements", None)
                if not reqs:
                    continue
                for lang, types in reqs.items():
                    for data_type, append_to_response in types.items():
                        if (
                            (data_type == "season" and meta.category != "TV")
                            or (data_type == "episode" and (meta.category != "TV" or meta.tv_pack))
                            or (data_type == "episode" and tracker_name in ("BJSHARE", "BRASILTRACKER") and not prep_instance.config["DEFAULT"].get("episode_overview", False))
                            or (data_type == "main" and meta.category not in ("TV", "MOVIE"))
                        ):
                            continue

                        existing = requirements.setdefault(lang, {}).setdefault(data_type, "")
                        merged_tags = set(filter(None, [t.strip() for t in existing.split(",") + append_to_response.split(",")]))
                        requirements[lang][data_type] = ",".join(sorted(merged_tags))

            tasks = []
            for lang, types in requirements.items():
                for data_type, append_to_response in types.items():
                    tasks.append(
                        (lang, data_type, prep_instance.tmdb_manager.get_tmdb_localized_data(meta, data_type=data_type, language=lang, append_to_response=append_to_response))
                    )
            if tasks:
                logger.debug(f"[cyan]Pre-fetching TMDB localized data for languages: {list(requirements.keys())}[/cyan]")
                langs_and_types = [(item[0], item[1]) for item in tasks]
                coroutines = [item[2] for item in tasks]
                results = await asyncio.gather(*coroutines)

                meta.tmdb_localized_data = {}
                for (lang, data_type), result in zip(langs_and_types, results, strict=True):
                    if result:
                        meta.tmdb_localized_data.setdefault(lang, {})[data_type] = result
        except Exception as e:
            logger.error(f"[red]Error pre-fetching TMDB localized data: {e}[/red]")
