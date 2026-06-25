# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import asyncio
import ntpath
import os
import re
import sys
from difflib import SequenceMatcher
from typing import Any, Optional, cast

import aiofiles
import cli_ui
import guessit

from src.bluray_com import get_bluray_releases
from src.cleanup import cleanup_manager
from src.clients import Clients
from src.console import console
from src.edition import get_edition
from src.exceptions import NoAudioMediaError
from src.exportmi import exportInfo, get_conformance_error, mi_resolution, validate_mediainfo
from src.get_source import get_source
from src.imdb import imdb_manager
from src.languages import languages_manager
from src.region import get_distributor, get_region, get_service
from src.tags import get_tag, tag_override
from src.tvmaze import tvmaze_manager
from src.video import video_manager

guessit_module: Any = cast(Any, guessit)


def guessit_fn(value: str, options: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    return cast(dict[str, Any], guessit_module.guessit(value, options))


def _normalize_search_year(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    if isinstance(value, (str, int)):
        return str(value)
    return str(value)


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
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


def init_meta(prep_instance: Any, meta: dict[str, Any], mode: str) -> tuple[bool, bool, Clients, bool, list[str], list[str]]:
    meta["cutoff"] = int(prep_instance.config["DEFAULT"].get("cutoff_screens", 1))

    meta["mode"] = mode
    meta["isdir"] = os.path.isdir(meta["path"])
    base_dir = meta["base_dir"]
    meta["saved_description"] = False
    client = Clients(config=prep_instance.config)
    meta["skip_auto_torrent"] = meta.get("skip_auto_torrent", False) or prep_instance.config["DEFAULT"].get("skip_auto_torrent", False)
    hash_ids = ["infohash", "torrent_hash", "skip_auto_torrent"]
    tracker_ids = ["aither", "ulcx", "lst", "blu", "oe", "btn", "bhd", "huno", "hdb", "rf", "otw", "yus", "dp", "sp", "ptp"]
    use_sonarr = prep_instance.config["DEFAULT"].get("use_sonarr", False)
    use_radarr = prep_instance.config["DEFAULT"].get("use_radarr", False)
    meta["print_tracker_messages"] = prep_instance.config["DEFAULT"].get("print_tracker_messages", False)
    meta["print_tracker_links"] = prep_instance.config["DEFAULT"].get("print_tracker_links", True)
    only_id_val = meta.get("onlyID")
    only_id = bool(prep_instance.config["DEFAULT"].get("only_id", False) if only_id_val is None else only_id_val)
    meta["only_id"] = only_id
    meta["keep_images"] = bool(prep_instance.config["DEFAULT"].get("keep_images", True) if not meta.get("keep_images") else True)
    mkbrr_threads = prep_instance.config["DEFAULT"].get("mkbrr_threads", "0")
    meta["mkbrr_threads"] = mkbrr_threads

    # make sure these are set in meta
    meta["we_checked_tvdb"] = False
    meta["we_checked_tmdb"] = False
    meta["we_asked_tvmaze"] = False
    meta["audio_languages"] = None
    meta["subtitle_languages"] = None
    meta["aither_trumpable"] = None
    meta["anime"] = False
    meta["not_anime"] = False
    meta["subtitle_files"] = cast(list[str], [])
    meta["adult_media"] = False

    folder_id = os.path.basename(meta["path"])
    if meta.get("uuid") is None:
        meta["uuid"] = folder_id
    if meta.get("isdir", False):
        meta["basename_no_ext"] = folder_id
    else:
        meta["basename_no_ext"] = os.path.splitext(folder_id)[0]
    if not os.path.exists(f"{base_dir}/tmp/{meta['uuid']}"):
        os.makedirs(f"{base_dir}/tmp/{meta['uuid']}", mode=0o700, exist_ok=True)

    if meta["debug"]:
        console.print(f"[cyan]ID: {meta['uuid']}")

    return use_sonarr, use_radarr, client, only_id, hash_ids, tracker_ids


async def detect_disc_and_category(prep_instance: Any, meta: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    try:
        meta["is_disc"], videoloc, bdinfo, meta["discs"] = await prep_instance.disc_info_manager.get_disc(meta)
    except Exception:
        raise
    if meta.get("debug", False):
        console.print(f"[blue]is_disc: [yellow]{meta['is_disc']}[/yellow][/blue]")

    # Auto-detect BOOK category if category/manual_category is not already set and it's not a disc
    if not meta.get("category") and not meta.get("manual_category") and not meta.get("is_disc"):
        is_book = False
        book_extensions = {".pdf", ".epub", ".mobi", ".cbz", ".cbr"}
        audiobook_extensions = {".mp3", ".m4b", ".flac", ".aac", ".m4a", ".ogg", ".wav"}
        video_extensions = {".mkv", ".mp4", ".ts"}

        path_to_check = meta.get("path")
        if path_to_check and os.path.exists(path_to_check):
            if os.path.isdir(path_to_check):
                has_books = False
                has_audio = False
                has_video = False
                for _root, _, files in os.walk(path_to_check):
                    for file in files:
                        ext = os.path.splitext(file)[1].lower()
                        if ext in book_extensions:
                            has_books = True
                        elif ext in audiobook_extensions:
                            has_audio = True
                        elif ext in video_extensions:
                            has_video = True
                # If we have books/audio files and NO video files, classify as BOOK
                if (has_books or has_audio) and not has_video:
                    is_book = True
            else:
                ext = os.path.splitext(path_to_check)[1].lower()
                if ext in book_extensions or ext in audiobook_extensions:
                    is_book = True

        if is_book:
            meta["category"] = "BOOK"
            if meta.get("debug", False):
                console.print("[cyan]Auto-detected category: BOOK[/cyan]")

    # Auto-detect GAME category if category/manual_category is not already set and it's not a disc
    if not meta.get("category") and not meta.get("manual_category") and not meta.get("is_disc"):
        is_game = False
        game_extensions = {".exe", ".iso", ".rar"}
        video_extensions = {".mkv", ".mp4", ".ts"}
        game_groups = {"tenoke", "rune", "flt", "plaza", "codex", "skidrow", "prophet", "gog", "darkzer0", "doge", "tinyiso", "razor1911", "outlaws", "alias", "simplex"}

        path_to_check = meta.get("path")
        if path_to_check and os.path.exists(path_to_check):
            has_game_ext = False
            has_video = False
            has_steam_link = False
            has_game_group = False

            base_name_lower = os.path.basename(path_to_check).lower()
            for group in game_groups:
                if f"-{group}" in base_name_lower or base_name_lower.endswith(group):
                    has_game_group = True
                    break

            if os.path.isdir(path_to_check):
                for root, _, files in os.walk(path_to_check):
                    for file in files:
                        file_lower = file.lower()
                        ext = os.path.splitext(file_lower)[1]
                        if ext in game_extensions:
                            has_game_ext = True
                        elif ext in video_extensions:
                            has_video = True
                        elif ext == ".nfo":
                            nfo_path = os.path.join(root, file)
                            try:
                                async with aiofiles.open(nfo_path, encoding="utf-8", errors="ignore") as nf:
                                    nfo_content = await nf.read()
                                    if "store.steampowered.com/app/" in nfo_content or "igdb.com" in nfo_content:
                                        has_steam_link = True
                            except Exception:
                                try:
                                    async with aiofiles.open(nfo_path, encoding="latin-1", errors="ignore") as nf:
                                        nfo_content = await nf.read()
                                        if "store.steampowered.com/app/" in nfo_content or "igdb.com" in nfo_content:
                                            has_steam_link = True
                                except Exception:
                                    pass
            else:
                ext = os.path.splitext(base_name_lower)[1]
                if ext in game_extensions:
                    has_game_ext = True

            if has_steam_link or ((has_game_ext or has_game_group) and not has_video):
                is_game = True

        if is_game:
            meta["category"] = "GAME"
            if meta.get("debug", False):
                console.print("[cyan]Auto-detected category: GAME[/cyan]")

    return videoloc, bdinfo


async def process_media_files(prep_instance: Any, meta: dict[str, Any], videoloc: str, bdinfo: dict[str, Any]) -> tuple[str, str, str, str, str, Optional[dict[str, Any]], str]:
    filename = ""
    untouched_filename = ""
    videopath = ""
    search_term = ""
    search_file_folder = ""
    mi: Optional[dict[str, Any]] = None
    video = ""
    base_dir = meta["base_dir"]

    if meta["is_disc"] == "BDMV":
        video, meta["scene"], meta["imdb_id"] = await prep_instance.scene_manager.is_scene(meta["path"], meta, meta.get("imdb_id", 0))
        meta["filelist"] = []  # No filelist for discs, use path
        search_term = os.path.basename(meta["path"])
        search_file_folder = "folder"
        try:
            if meta.get("emby", False):
                title, secondary_title, extracted_year = await prep_instance.name_manager.extract_title_and_year(meta, video)
                if meta["debug"]:
                    console.print(f"Title: {title}, Secondary Title: {secondary_title}, Year: {extracted_year}")
                if secondary_title:
                    meta["secondary_title"] = secondary_title
                if extracted_year and not meta.get("year"):
                    meta["year"] = extracted_year
                if title:
                    filename = title
                    untouched_filename = search_term
                    meta["regex_title"] = title
                    meta["regex_secondary_title"] = secondary_title
                    meta["regex_year"] = extracted_year
                else:
                    guess_name = search_term.replace("-", " ")
                    untouched_filename = search_term
                    filename = str(guessit_fn(guess_name, {"excludes": ["country", "language"]}).get("title", ""))
            else:
                title, secondary_title, extracted_year = await prep_instance.name_manager.extract_title_and_year(meta, video)
                if meta["debug"]:
                    console.print(f"Title: {title}, Secondary Title: {secondary_title}, Year: {extracted_year}")
                if secondary_title:
                    meta["secondary_title"] = secondary_title
                if extracted_year and not meta.get("year"):
                    meta["year"] = extracted_year
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
                        meta["hfr"] = True
                    else:
                        meta["hfr"] = False
                except Exception:
                    meta["hfr"] = False

            try:
                meta["search_year"] = guessit_fn(bdinfo["title"])["year"]
            except Exception:
                meta["search_year"] = ""
        except Exception:
            guess_name = bdinfo["label"].replace("-", " ")
            filename = str(guessit_fn(re.sub(r"[^0-9a-zA-Z\[\\]]+", " ", guess_name), {"excludes": ["country", "language"]}).get("title", ""))
            untouched_filename = bdinfo["label"]
            try:
                meta["search_year"] = guessit_fn(bdinfo["label"])["year"]
            except Exception:
                meta["search_year"] = ""

        if meta.get("resolution") is None and not meta.get("emby", False):
            meta["resolution"] = await mi_resolution(
                bdinfo["video"][0]["res"],
                guessit_fn(video),
                width="OTHER",
                scan="p",
            )

        elif meta.get("emby", False):
            meta["resolution"] = "1080p"

        meta["sd"] = await video_manager.is_sd(str(meta.get("resolution", "")))
        mi = None

    elif meta["is_disc"] == "DVD":
        video, meta["scene"], meta["imdb_id"] = await prep_instance.scene_manager.is_scene(meta["path"], meta, meta.get("imdb_id", 0))
        meta["filelist"] = []
        search_term = os.path.basename(meta["path"])
        search_file_folder = "folder"
        if meta.get("emby", False):
            title, secondary_title, extracted_year = await prep_instance.name_manager.extract_title_and_year(meta, video)
            if meta["debug"]:
                console.print(f"Title: {title}, Secondary Title: {secondary_title}, Year: {extracted_year}")
            if secondary_title:
                meta["secondary_title"] = secondary_title
            if extracted_year and not meta.get("year"):
                meta["year"] = extracted_year
            if title:
                filename = title
                untouched_filename = search_term
                meta["regex_title"] = title
                meta["regex_secondary_title"] = secondary_title
                meta["regex_year"] = extracted_year
            else:
                guess_name = search_term.replace("-", " ")
                filename = guess_name
                untouched_filename = search_term
            meta["resolution"] = "480p"
            meta["search_year"] = ""
        else:
            title, secondary_title, extracted_year = await prep_instance.name_manager.extract_title_and_year(meta, video)
            if meta["debug"]:
                console.print(f"Title: {title}, Secondary Title: {secondary_title}, Year: {extracted_year}")
            if secondary_title:
                meta["secondary_title"] = secondary_title
            if extracted_year and not meta.get("year"):
                meta["year"] = extracted_year
            if title:
                filename = title
                untouched_filename = search_term
            else:
                guess_name = meta["discs"][0]["path"].replace("-", " ")
                filename = str(guessit_fn(guess_name, {"excludes": ["country", "language"]}).get("title", ""))
                untouched_filename = os.path.basename(os.path.dirname(meta["discs"][0]["path"]))
            try:
                meta["search_year"] = guessit_fn(meta["discs"][0]["path"])["year"]
            except Exception:
                meta["search_year"] = ""
            if not meta.get("edit", False):
                mi = await exportInfo(
                    f"{meta['discs'][0]['path']}/VTS_{meta['discs'][0]['main_set'][0][:2]}_0.IFO",
                    False,
                    meta["uuid"],
                    meta["base_dir"],
                    is_dvd=True,
                    debug=meta.get("debug", False),
                )
                meta["mediainfo"] = mi
            else:
                mi = meta["mediainfo"]

            meta["dvd_size"] = await prep_instance.disc_info_manager.get_dvd_size(meta["discs"], meta.get("manual_dvds"))
            meta["resolution"], meta["hfr"] = await video_manager.get_resolution(guessit_fn(video), meta["uuid"], base_dir, meta)
            meta["sd"] = await video_manager.is_sd(meta["resolution"])

    elif meta["is_disc"] == "HDDVD":
        video, meta["scene"], meta["imdb_id"] = await prep_instance.scene_manager.is_scene(meta["path"], meta, meta.get("imdb_id", 0))
        meta["filelist"] = []
        search_term = os.path.basename(meta["path"])
        search_file_folder = "folder"
        guess_name = meta["discs"][0]["path"].replace("-", "")
        filename = str(guessit_fn(guess_name, {"excludes": ["country", "language"]}).get("title", ""))
        untouched_filename = os.path.basename(meta["discs"][0]["path"])
        videopath = meta["discs"][0]["largest_evo"]
        try:
            meta["search_year"] = guessit_fn(meta["discs"][0]["path"])["year"]
        except Exception:
            meta["search_year"] = ""
        if not meta.get("edit", False):
            mi = await exportInfo(meta["discs"][0]["largest_evo"], False, meta["uuid"], meta["base_dir"], debug=meta["debug"])
            meta["mediainfo"] = mi
        else:
            mi = meta["mediainfo"]
        meta["resolution"], meta["hfr"] = await video_manager.get_resolution(guessit_fn(video), meta["uuid"], base_dir, meta)
        meta["sd"] = await video_manager.is_sd(meta["resolution"])

    else:
        if meta.get("category") == "BOOK" or str(meta.get("manual_category") or "").upper() == "BOOK":
            videopath, filelist, search_term, search_file_folder = prep_instance._resolve_book_filelist(meta, videoloc)
            video = videopath
        elif meta.get("category") == "GAME" or str(meta.get("manual_category") or "").upper() == "GAME":
            videopath, filelist, search_term, search_file_folder = prep_instance._resolve_game_filelist(meta, videoloc)
            video = videopath
        else:
            videopath, meta["filelist"] = await video_manager.get_video(videoloc, meta.get("mode", "discord"), meta.get("sorted_filelist", False), meta.get("debug", False))
            filelist = cast(list[str], meta.get("filelist") or [])
            meta["filelist"] = filelist
            search_term = os.path.basename(filelist[0]) if filelist else ""
            search_file_folder = "file"

            # Scan for external subtitle files
            meta["subtitle_files"] = cast(list[str], [])
            subtitle_exts = {".srt", ".sub", ".vtt", ".ssa", ".ass", ".idx"}
            if meta["isdir"]:
                for root, _, files in os.walk(meta["path"]):
                    if any(x in root.upper() for x in ["BDMV", "VIDEO_TS", "HVDVD_TS"]):
                        continue
                    for file in files:
                        ext = os.path.splitext(file)[1].lower()
                        if ext in subtitle_exts:
                            meta["subtitle_files"].append(os.path.abspath(os.path.join(root, file)))
            else:
                parent_dir = os.path.dirname(meta["path"])
                if parent_dir and os.path.exists(parent_dir):
                    base_name = os.path.splitext(os.path.basename(meta["path"]))[0]
                    for file in os.listdir(parent_dir):
                        if os.path.isfile(os.path.join(parent_dir, file)):
                            ext = os.path.splitext(file)[1].lower()
                            if ext in subtitle_exts and file.lower().startswith(base_name.lower()):
                                meta["subtitle_files"].append(os.path.abspath(os.path.join(parent_dir, file)))
            meta["subtitle_files"] = sorted(set(meta["subtitle_files"]))

        video, meta["scene"], meta["imdb_id"] = await prep_instance.scene_manager.is_scene(videopath, meta, meta.get("imdb_id", 0))
        if meta.get("category") == "BOOK" or str(meta.get("manual_category") or "").upper() == "BOOK":
            orig_ext = os.path.splitext(videopath)[1]
            if video.endswith(".mkv") and not videopath.endswith(".mkv"):
                video = video[:-4] + orig_ext

        try:
            title, secondary_title, extracted_year = await prep_instance.name_manager.extract_title_and_year(meta, video)
            if meta["debug"]:
                console.print(f"Title: {title}, Secondary Title: {secondary_title}, Year: {extracted_year}")
            if secondary_title:
                meta["secondary_title"] = secondary_title
            if extracted_year and not meta.get("year"):
                meta["year"] = extracted_year

            if meta.get("isdir", False):
                guess_name = os.path.basename(meta["path"]).replace("_", "").replace("-", "") if meta["path"] else ""
            else:
                guess_name = ntpath.basename(video).replace("-", " ")
        except Exception as e:
            console.print(f"[red]Error extracting title and year: {e}[/red]")
            raise Exception(f"Error extracting title and year: {e}") from e

        try:
            if title:
                filename = title
                meta["regex_title"] = title
                meta["regex_secondary_title"] = secondary_title
                meta["regex_year"] = extracted_year
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
                        console.print(f"[red]Error extracting title from video name: {e}[/red]")
                        raise Exception(f"Error extracting title from video name: {e}") from e

            untouched_filename = os.path.basename(video)
        except Exception as e:
            console.print(f"[red]Error processing filename: {e}[/red]")
            raise Exception(f"Error processing filename: {e}") from e

        try:
            if meta.get("category") == "BOOK" or str(meta.get("manual_category") or "").upper() == "BOOK":
                await prep_instance._gather_book_prep(meta, videopath, base_dir)
            elif meta.get("category") == "GAME" or str(meta.get("manual_category") or "").upper() == "GAME":
                meta["filename"] = filename
                await prep_instance._gather_game_prep(meta, videopath, base_dir)
            elif not meta.get("emby", False):
                # rely only on guessit for search_year for tv matching
                try:
                    meta["search_year"] = guessit_fn(video)["year"]
                except Exception:
                    meta["search_year"] = ""

                if not meta.get("edit", False):
                    mi = await exportInfo(videopath, meta["isdir"], meta["uuid"], base_dir, is_dvd=meta.get("is_disc", False), debug=meta.get("debug", False))
                    meta["mediainfo"] = mi
                else:
                    mi = meta["mediainfo"]

                if meta.get("resolution") is None:
                    meta["resolution"], meta["hfr"] = await video_manager.get_resolution(guessit_fn(video), meta["uuid"], base_dir, meta)

                meta["sd"] = await video_manager.is_sd(meta["resolution"])
            else:
                meta["resolution"] = "1080p"
                meta["search_year"] = ""
        except Exception as e:
            console.print(f"[red]Error processing Mediainfo: {e}[/red]")
            raise Exception(f"Error processing Mediainfo: {e}") from e

    return filename, untouched_filename, videopath, search_term, search_file_folder, mi, video


def calculate_source_size(_prep_instance: Any, meta: dict[str, Any], videopath: str) -> None:
    source_size = 0
    if not meta["is_disc"]:
        # Sum every non-disc file so downstream steps know the total payload size
        filelist = cast(list[str], meta.get("filelist") or [])
        files_to_measure = filelist if filelist else ([videopath] if videopath else [])
        for file_path in files_to_measure:
            if not os.path.isfile(file_path):
                if meta.get("debug"):
                    console.print(f"[yellow]Skipping size check for missing file: {file_path}")
                continue
            try:
                source_size += os.path.getsize(file_path)
            except OSError as exc:
                if meta.get("debug"):
                    console.print(f"[yellow]Unable to stat {file_path}: {exc}")

    else:
        # Disc structures can span many files; walk the tree rooted at meta['path']
        disc_root = meta.get("path")
        disc_root_str = disc_root if isinstance(disc_root, str) else ""
        if disc_root_str and os.path.exists(disc_root_str):
            for root, _, files in os.walk(disc_root_str):
                for name in files:
                    file_path = os.path.join(root, name)
                    try:
                        source_size += os.path.getsize(file_path)
                    except OSError as exc:
                        if meta.get("debug"):
                            console.print(f"[yellow]Unable to stat {file_path}: {exc}")
                        continue
        else:
            if meta.get("debug"):
                console.print(f"[yellow]Disc path missing, source size set to 0: {disc_root_str}")

    meta["source_size"] = source_size
    if meta["debug"]:
        console.print(f"[cyan]Calculated source size: {meta['source_size']} bytes")


async def validate_media(_prep_instance: Any, meta: dict[str, Any]) -> None:
    conform_issues = await get_conformance_error(meta)
    if conform_issues:
        upload = False
        if not meta["unattended"] or (meta["unattended"] and meta.get("unattended_confirm", False)):
            try:
                upload = cli_ui.ask_yes_no(
                    "Found Conformance errors in mediainfo (possible cause: corrupted file, incomplete download, new codec, etc...), proceed to upload anyway?", default=False
                )
            except EOFError:
                console.print("\n[red]Exiting on user request (Ctrl+C)[/red]")
                await cleanup_manager.cleanup()
                cleanup_manager.reset_terminal()
                sys.exit(1)
        if upload is False:
            console.print("[red]Not uploading. Check if the file has finished downloading and can be played back properly (uncorrupted).")
            tmp_dir = f"{meta['base_dir']}/tmp/{meta['uuid']}"
            # Cleanup meta so we don't reuse it later
            if os.path.exists(tmp_dir):
                try:
                    for file in os.listdir(tmp_dir):
                        file_path = os.path.join(tmp_dir, file)
                        if os.path.isfile(file_path) and file.endswith((".txt", ".json")):
                            os.remove(file_path)
                            if meta["debug"]:
                                console.print(f"[yellow]Removed temporary metadata file: {file_path}[/yellow]")
                except Exception as e:
                    console.print(f"[red]Error cleaning up temporary metadata files: {e}[/red]", highlight=False)
            console.print("[red]Not uploading due to conformance errors.[/red]")
            raise Exception("Conformance errors found in mediainfo")

    meta["valid_mi"] = True
    if not meta["is_disc"] and not meta.get("emby", False) and meta.get("category") not in ("BOOK", "GAME"):
        try:
            valid_mi = validate_mediainfo(meta, debug=meta["debug"])
        except NoAudioMediaError as e:
            console.print(f"[red]MediaInfo validation failed: {str(e)}[/red]")
            raise NoAudioMediaError(f"{meta['ua_name']} does not support no audio media. Details: {str(e)}") from e
        except Exception as e:
            console.print(f"[red]MediaInfo validation failed: {str(e)}[/red]")
            raise
        if not valid_mi:
            console.print("[red]MediaInfo validation failed. This file does not contain (Unique ID).")
            meta["valid_mi"] = False
            await asyncio.sleep(2)

    mediainfo_tracks = meta.get("mediainfo", {}).get("media", {}).get("track") or []
    meta["has_multiple_default_subtitle_tracks"] = len([track for track in mediainfo_tracks if track["@type"] == "Text" and track["Default"] == "Yes"]) > 1

    # Check if there's a language restriction
    if meta["has_languages"] is not None and not meta.get("emby", False):
        try:
            parsed_info = await languages_manager.parsed_mediainfo(meta)
            audio_languages = [audio_track["language"].lower() for audio_track in parsed_info.get("audio", []) if "language" in audio_track and audio_track["language"]]
            any_of_languages = meta["has_languages"].lower().split(",")
            if all(len(lang.strip()) == 2 for lang in any_of_languages):
                raise Exception(f"Warning: Languages should be full names, not ISO codes. Found: {any_of_languages}")
            # We need to have user input languages and file must have audio tracks.
            if len(any_of_languages) > 0 and len(audio_languages) > 0 and not set(any_of_languages).intersection(set(audio_languages)):
                console.print(f"[red] None of the required languages ({meta['has_languages']}) is available on the file {audio_languages}")
                raise Exception("No matching languages")
        except Exception as e:
            console.print(f"[red]{e}[/red]")
            raise Exception("Language check failed") from e


async def process_trackers_and_torrent(
    prep_instance: Any, meta: dict[str, Any], client: Clients, hash_ids: list[str], tracker_ids: list[str], _search_term: str, _search_file_folder: str
) -> None:
    if not meta.get("emby", False):
        if "description" not in meta or meta.get("description") is None:
            meta["description"] = ""

        description_text = meta.get("description", "")
        if description_text is None:
            description_text = ""
        async with aiofiles.open(
            f"{meta['base_dir']}/tmp/{meta['uuid']}/DESCRIPTION.txt",
            "w",
            newline="",
            encoding="utf8",
        ) as description:
            if len(description_text):
                await description.write(description_text)

    meta["skip_trackers"] = False
    if meta.get("emby", False):
        meta["only_id"] = True
        meta["keep_images"] = False
        if meta.get("imdb_id", 0) != 0:
            meta["skip_trackers"] = True
    if meta.get("emby_debug", False):
        meta["skip_trackers"] = True

    if not meta.get("emby") and meta.get("trackers"):
        trackers = meta["trackers"]
    else:
        default_trackers = prep_instance.config["TRACKERS"].get("default_trackers", "")
        trackers = [tracker.strip() for tracker in default_trackers.split(",")]

    if isinstance(trackers, str):
        trackers = [t.strip().upper() for t in trackers.split(",")] if "," in trackers else [trackers.strip().upper()]
    else:
        trackers = [t.strip().upper() for t in trackers]
    meta["trackers"] = trackers
    meta["requested_trackers"] = trackers

    # auto torrent searching with qbittorrent that grabs torrent ids for metadata searching
    if not any(meta.get(id_type) for id_type in hash_ids + tracker_ids) and not meta.get("skip_trackers", False) and not meta.get("edit", False):
        await client.get_pathed_torrents(meta["path"], meta)

    # Try to extract metadata from matching client torrent or a local torrent file
    if (
        not any(meta.get(id_type) for id_type in ["imdb_id", "tmdb_id", "tvdb_id", "tvmaze_id", "mal_id", "douban_id", "igdb_id", "asin", "isbn"])
        and not meta.get("skip_trackers", False)
        and not meta.get("edit", False)
    ):
        reuse_torrent = await client.find_existing_torrent(meta)

        # Check local files if not found in client
        if not reuse_torrent:
            search_dir = meta["path"] if meta["isdir"] else os.path.dirname(meta["path"])
            if search_dir and os.path.exists(search_dir):
                torrent_files = [os.path.join(search_dir, f) for f in os.listdir(search_dir) if f.lower().endswith(".torrent")]
                default_torrent_client = prep_instance.config["DEFAULT"].get("default_torrent_client")
                client_config = prep_instance.config.get("TORRENT_CLIENTS", {}).get(default_torrent_client, {}) if default_torrent_client else {}
                for torrent_path in torrent_files:
                    try:
                        valid, _ = await client.is_valid_torrent(meta, torrent_path, "", "local", client_config)
                        if valid:
                            reuse_torrent = torrent_path
                            break
                    except Exception as e:
                        if meta.get("debug"):
                            console.print(f"[yellow]Failed to validate local torrent {torrent_path}: {e}[/yellow]")

        if reuse_torrent and os.path.exists(reuse_torrent):
            try:
                from torf import Torrent

                torrent_data = Torrent.read(reuse_torrent)
                extracted = False
                id_keys_map = {
                    "imdb": "imdb_id",
                    "tmdb": "tmdb_id",
                    "tvdb": "tvdb_id",
                    "tvmaze": "tvmaze_id",
                    "mal": "mal_id",
                    "douban": "douban_id",
                    "igdb": "igdb_id",
                    "asin": "asin",
                    "isbn": "isbn",
                }
                for torrent_key, meta_key in id_keys_map.items():
                    val = cast(Any, torrent_data.metainfo.get(torrent_key))
                    if val is not None and val != 0 and val != "":
                        if torrent_key == "tmdb":
                            if isinstance(val, str) and "/" in val and ("tv" in val.lower() or "movie" in val.lower()):
                                parts = val.split("/")
                                meta["category"] = parts[0].upper()
                                try:
                                    meta["tmdb_id"] = int(parts[1])
                                    extracted = True
                                except (ValueError, TypeError):
                                    pass
                            else:
                                try:
                                    meta["tmdb_id"] = int(val)
                                    extracted = True
                                except (ValueError, TypeError):
                                    pass
                        elif torrent_key in ["isbn", "asin"]:
                            meta[meta_key] = str(val)
                            meta["category"] = "BOOK"
                            extracted = True
                        elif torrent_key == "igdb":
                            try:
                                meta["igdb_id"] = int(val)
                                meta["category"] = "GAME"
                                extracted = True
                            except (ValueError, TypeError):
                                pass
                        elif torrent_key == "imdb":
                            val_str = str(val).strip()
                            if val_str.lower().startswith("tt"):
                                val_str = val_str[2:]
                            try:
                                meta["imdb_id"] = int(val_str)
                                extracted = True
                            except (ValueError, TypeError):
                                pass
                        elif torrent_key in ["tvdb", "tvmaze", "mal", "douban"]:
                            try:
                                meta[meta_key] = int(val)
                                extracted = True
                            except (ValueError, TypeError):
                                pass
                        else:
                            meta[meta_key] = str(val)
                            extracted = True
                        if extracted and meta.get("debug"):
                            console.print(f"[green]Extracted {meta_key} from torrent: {val}[/green]")
                if extracted:
                    console.print("[green]Successfully extracted metadata IDs from matching torrent file.[/green]")
            except Exception as e:
                if meta.get("debug"):
                    console.print(f"[yellow]Failed to extract metadata from existing torrent: {e}[/yellow]")


async def search_metadata(
    prep_instance: Any,
    meta: dict[str, Any],
    filename: str,
    untouched_filename: str,
    videopath: str,
    search_term: str,
    search_file_folder: str,
    use_sonarr: bool,
    use_radarr: bool,
    only_id: bool,
    client: Clients,
    _bdinfo: dict[str, Any],
    mi: Optional[dict[str, Any]],
) -> None:
    # Ensure all manual IDs have proper default values
    meta["tmdb_manual"] = meta.get("tmdb_manual") or 0
    meta["imdb_manual"] = meta.get("imdb_manual") or 0
    meta["mal_manual"] = meta.get("mal_manual") or 0
    meta["tvdb_manual"] = meta.get("tvdb_manual") or 0
    meta["tvmaze_manual"] = meta.get("tvmaze_manual") or 0

    # Set tmdb_id
    try:
        if meta.get("tmdb_manual"):
            meta["tmdb_id"] = int(meta["tmdb_manual"])
        elif not meta.get("tmdb_id"):
            meta["tmdb_id"] = 0
    except (ValueError, TypeError):
        if not meta.get("tmdb_id"):
            meta["tmdb_id"] = 0

    # Set imdb_id with proper handling for 'tt' prefix
    try:
        if not meta.get("imdb_id"):
            imdb_value = meta["imdb_manual"]
            if imdb_value:
                if str(imdb_value).startswith("tt"):
                    meta["imdb_id"] = int(str(imdb_value)[2:])
                else:
                    meta["imdb_id"] = int(imdb_value)
            else:
                meta["imdb_id"] = 0
    except (ValueError, TypeError):
        meta["imdb_id"] = 0

    # Set mal_id
    try:
        if meta.get("mal_manual"):
            meta["mal_id"] = int(meta["mal_manual"])
        elif not meta.get("mal_id"):
            meta["mal_id"] = 0
    except (ValueError, TypeError):
        if not meta.get("mal_id"):
            meta["mal_id"] = 0

    # Set tvdb_id
    try:
        if meta.get("tvdb_manual"):
            meta["tvdb_id"] = int(meta["tvdb_manual"])
        elif not meta.get("tvdb_id"):
            meta["tvdb_id"] = 0
    except (ValueError, TypeError):
        if not meta.get("tvdb_id"):
            meta["tvdb_id"] = 0

    try:
        if meta.get("tvmaze_manual"):
            meta["tvmaze_id"] = int(meta["tvmaze_manual"])
        elif not meta.get("tvmaze_id"):
            meta["tvmaze_id"] = 0
    except (ValueError, TypeError):
        if not meta.get("tvmaze_id"):
            meta["tvmaze_id"] = 0

    # Auto-detect category from video name if category is still missing
    if not meta.get("category"):
        meta["category"] = await prep_instance.get_cat(videopath, meta)
    else:
        meta["category"] = meta["category"].upper()

    ids = None
    if not meta.get("skip_trackers", False):
        if meta.get("category") == "TV" and use_sonarr and meta.get("tvdb_id", 0) == 0:
            ids = await prep_instance.sonarr_manager.get_sonarr_data(filename=meta.get("path", ""), title=meta.get("filename"), debug=meta.get("debug", False))
            if ids:
                if meta["debug"]:
                    console.print(f"TVDB ID: {ids['tvdb_id']}")
                    console.print(f"IMDB ID: {ids['imdb_id']}")
                    console.print(f"TVMAZE ID: {ids['tvmaze_id']}")
                    console.print(f"TMDB ID: {ids['tmdb_id']}")
                    console.print(f"Genres: {ids['genres']}")
                    console.print(f"Release Group: {ids['release_group']}")
                    console.print(f"Year: {ids['year']}")
                if "anime" not in [genre.lower() for genre in ids["genres"]]:
                    meta["not_anime"] = True
                if meta.get("tvdb_id", 0) == 0 and ids["tvdb_id"] is not None:
                    meta["tvdb_id"] = ids["tvdb_id"]
                if meta.get("imdb_id", 0) == 0 and ids["imdb_id"] is not None:
                    meta["imdb_id"] = ids["imdb_id"]
                if meta.get("tvmaze_id", 0) == 0 and ids["tvmaze_id"] is not None:
                    meta["tvmaze_id"] = ids["tvmaze_id"]
                if meta.get("tmdb_id", 0) == 0 and ids["tmdb_id"] is not None:
                    meta["tmdb_id"] = ids["tmdb_id"]
                if meta.get("manual_year", 0) == 0 and ids["year"] is not None:
                    meta["manual_year"] = ids["year"]
            else:
                ids = None

        if meta.get("category") == "MOVIE" and use_radarr and meta.get("tmdb_id", 0) == 0:
            ids = await prep_instance.radarr_manager.get_radarr_data(filename=meta.get("uuid", ""), debug=meta.get("debug", False))
            if ids:
                if meta["debug"]:
                    console.print(f"IMDB ID: {ids['imdb_id']}")
                    console.print(f"TMDB ID: {ids['tmdb_id']}")
                    console.print(f"Genres: {ids['genres']}")
                    console.print(f"Year: {ids['year']}")
                    console.print(f"Release Group: {ids['release_group']}")
                if meta.get("imdb_id", 0) == 0 and ids["imdb_id"] is not None:
                    meta["imdb_id"] = ids["imdb_id"]
                if meta.get("tmdb_id", 0) == 0 and ids["tmdb_id"] is not None:
                    meta["tmdb_id"] = ids["tmdb_id"]
                if meta.get("manual_year", 0) == 0 and ids["year"] is not None:
                    meta["manual_year"] = ids["year"]
            else:
                ids = None

        # check if we've already searched torrents
        if "base_torrent_created" not in meta:
            meta["base_torrent_created"] = False
        if "we_checked_them_all" not in meta:
            meta["we_checked_them_all"] = False

        # if not auto qbittorrent search, this also checks with the infohash if passed.
        if meta.get("infohash") is not None and not meta["base_torrent_created"] and not meta["we_checked_them_all"] and not ids:
            meta = await client.get_ptp_from_hash(meta)

        if not meta.get("edit", False) and not ids:
            # Reuse information from trackers with fallback
            await prep_instance.tracker_data_manager.get_tracker_data(videopath, meta, search_term, search_file_folder, meta["category"], only_id=only_id)

        if meta.get("category", None) == "TV" and use_sonarr and meta.get("tvdb_id", 0) != 0 and ids is None and not meta.get("matched_tracker", None):
            ids = await prep_instance.sonarr_manager.get_sonarr_data(tvdb_id=meta.get("tvdb_id", 0), debug=meta.get("debug", False))
            if ids:
                if meta["debug"]:
                    console.print(f"TVDB ID: {ids['tvdb_id']}")
                    console.print(f"IMDB ID: {ids['imdb_id']}")
                    console.print(f"TVMAZE ID: {ids['tvmaze_id']}")
                    console.print(f"TMDB ID: {ids['tmdb_id']}")
                    console.print(f"Genres: {ids['genres']}")
                if "anime" not in [genre.lower() for genre in ids["genres"]]:
                    meta["not_anime"] = True
                if meta.get("tvdb_id", 0) == 0 and ids["tvdb_id"] is not None:
                    meta["tvdb_id"] = ids["tvdb_id"]
                if meta.get("imdb_id", 0) == 0 and ids["imdb_id"] is not None:
                    meta["imdb_id"] = ids["imdb_id"]
                if meta.get("tvmaze_id", 0) == 0 and ids["tvmaze_id"] is not None:
                    meta["tvmaze_id"] = ids["tvmaze_id"]
                if meta.get("tmdb_id", 0) == 0 and ids["tmdb_id"] is not None:
                    meta["tmdb_id"] = ids["tmdb_id"]
                if meta.get("manual_year", 0) == 0 and ids["year"] is not None:
                    meta["manual_year"] = ids["year"]
            else:
                ids = None

        if meta.get("category", None) == "MOVIE" and use_radarr and meta.get("tmdb_id", 0) != 0 and ids is None and not meta.get("matched_tracker", None):
            ids = await prep_instance.radarr_manager.get_radarr_data(tmdb_id=meta.get("tmdb_id", 0), debug=meta.get("debug", False))
            if ids:
                if meta["debug"]:
                    console.print(f"IMDB ID: {ids['imdb_id']}")
                    console.print(f"TMDB ID: {ids['tmdb_id']}")
                    console.print(f"Genres: {ids['genres']}")
                    console.print(f"Year: {ids['year']}")
                    console.print(f"Release Group: {ids['release_group']}")
                if meta.get("imdb_id", 0) == 0 and ids["imdb_id"] is not None:
                    meta["imdb_id"] = ids["imdb_id"]
                if meta.get("tmdb_id", 0) == 0 and ids["tmdb_id"] is not None:
                    meta["tmdb_id"] = ids["tmdb_id"]
                if meta.get("manual_year", 0) == 0 and ids["year"] is not None:
                    meta["manual_year"] = ids["year"]
            else:
                ids = None

    # if there's no region/distributor info, lets ping some unit3d trackers and see if we get it
    ping_unit3d_config = prep_instance.config["DEFAULT"].get("ping_unit3d", False)
    if (
        (not meta.get("region") or not meta.get("distributor"))
        and meta["is_disc"] == "BDMV"
        and ping_unit3d_config
        and not meta.get("edit", False)
        and not meta.get("emby", False)
        and not meta.get("site_check", False)
    ):
        await prep_instance.tracker_data_manager.ping_unit3d(meta)

    # the first user override check that allows to set metadata ids.
    # it relies on imdb or tvdb already being set.
    user_overrides = prep_instance.config["DEFAULT"].get("user_overrides", False)
    if user_overrides and (meta.get("imdb_id") != 0 or meta.get("tvdb_id") != 0) and not meta.get("emby", False):
        meta = await prep_instance.overrides.get_source_override(meta, other_id=True)
        category = meta.get("category")
        meta["category"] = str(category).upper() if category is not None else ""
        # set a flag so that the other check later doesn't run
        meta["no_override"] = True

    emby_cat = meta.get("emby_cat")
    if emby_cat is not None and str(emby_cat).upper() != str(meta.get("category") or "").upper():
        return

    if meta["debug"]:
        console.print("ID inputs into prep")
        console.print("category:", meta.get("category"))
        console.print(f"Raw TVDB ID: {meta['tvdb_id']} (type: {type(meta['tvdb_id']).__name__})")
        console.print(f"Raw IMDb ID: {meta['imdb_id']} (type: {type(meta['imdb_id']).__name__})")
        console.print(f"Raw TMDb ID: {meta['tmdb_id']} (type: {type(meta['tmdb_id']).__name__})")
        console.print(f"Raw TVMAZE ID: {meta['tvmaze_id']} (type: {type(meta['tvmaze_id']).__name__})")
        console.print(f"Raw MAL ID: {meta['mal_id']} (type: {type(meta['mal_id']).__name__})")

    if meta.get("mal_id", 0) != 0:
        meta["anime"] = True
        meta["not_anime"] = True

    console.print("[yellow]Building meta data.....")

    manual_language = meta.get("manual_language")
    if isinstance(manual_language, str) and manual_language:
        meta["original_language"] = manual_language.lower()

    if meta.get("category") == "BOOK":
        meta["type"] = os.path.splitext(videopath)[1].lstrip(".").upper()
        if meta["type"] in ("CBR", "CBZ"):
            meta["comic"] = True
    elif meta.get("category") == "GAME":
        meta["type"] = "GAME"
    else:
        meta["type"] = await video_manager.get_type(videopath, meta["scene"], meta["is_disc"], meta)

    # if it's not an anime, we can run season/episode checks now to speed the process
    if meta.get("not_anime", False) and meta.get("category") == "TV":
        meta = await prep_instance.season_episode_manager.get_season_episode(videopath, meta)

    mi_data: dict[str, Any] = mi or {}

    # Run a check against mediainfo to see if it has tmdb/imdb
    if (meta.get("tmdb_id") == 0 or meta.get("imdb_id") == 0) and not meta.get("emby", False) and meta.get("category") not in ("BOOK", "GAME"):
        meta["category"], meta["tmdb_id"], meta["imdb_id"], meta["tvdb_id"] = await prep_instance.tmdb_manager.get_tmdb_imdb_from_mediainfo(mi_data, meta)

    # Flag for emby if no IDs were found
    if (
        meta.get("imdb_id", 0) == 0
        and meta.get("tvdb_id", 0) == 0
        and meta.get("tmdb_id", 0) == 0
        and meta.get("tvmaze_id", 0) == 0
        and meta.get("mal_id", 0) == 0
        and meta.get("emby", False)
    ):
        meta["no_ids"] = True

    meta["video_duration"] = await video_manager.get_video_duration(meta)
    duration = meta.get("video_duration", None)

    unattended = not (not meta["unattended"] or meta["unattended"] and meta.get("unattended_confirm", False))
    debug = bool(meta.get("emby_debug", False) or meta["debug"])

    # run a search to find tmdb and imdb ids if we don't have them
    if int(meta.get("tmdb_id") or 0) == 0 and int(meta.get("imdb_id") or 0) == 0 and meta.get("category") not in ("BOOK", "GAME"):
        if meta.get("category") == "TV":
            year = meta.get("manual_year", "") or meta.get("search_year", "") or meta.get("year", "")
        elif meta.get("emby_debug", False):
            year = ""
        else:
            year = meta.get("manual_year", "") or meta.get("year", "") or meta.get("search_year", "")
        year_value = _normalize_search_year(year)
        category_pref = meta.get("category") or ""
        tmdb_task: asyncio.Task[tuple[int, str]] = asyncio.create_task(
            prep_instance.tmdb_manager.get_tmdb_id(
                filename,
                year_value,
                category_pref,
                untouched_filename,
                attempted=0,
                debug=debug,
                secondary_title=meta.get("secondary_title", None),
                unattended=unattended,
            )
        )
        imdb_task: asyncio.Task[int] = asyncio.create_task(
            imdb_manager.search_imdb(
                filename,
                year_value,
                quickie=True,
                category=category_pref,
                debug=debug,
                secondary_title=meta.get("secondary_title", None),
                untouched_filename=untouched_filename,
                duration=duration,
                unattended=unattended,
            )
        )
        tmdb_result, imdb_result = await asyncio.gather(tmdb_task, imdb_task)
        tmdb_id, category = tmdb_result
        meta["category"] = category
        meta["tmdb_id"] = _to_int(tmdb_id)
        meta["imdb_id"] = _to_int(imdb_result)
        meta["quickie_search"] = True
        meta["no_ids"] = True

    # If we have an IMDb ID but no TMDb ID, fetch TMDb ID from IMDb
    if int(meta.get("imdb_id") or 0) != 0 and int(meta.get("tmdb_id") or 0) == 0 and meta.get("category") not in ("BOOK", "GAME"):
        imdb_id_value = _to_int(meta.get("imdb_id"))
        tvdb_id_value = _to_int(meta.get("tvdb_id"))
        search_year_value = _normalize_search_year(meta.get("search_year"))
        category, tmdb_id, original_language, filename_search = await prep_instance.tmdb_manager.get_tmdb_from_imdb(
            imdb_id_value,
            tvdb_id_value if tvdb_id_value else None,
            search_year_value,
            filename,
            debug=meta.get("debug", False),
            mode=meta.get("mode", "discord"),
            category_preference=meta.get("category"),
            imdb_info=meta.get("imdb_info", None),
        )

        meta["category"] = category
        meta["tmdb_id"] = _to_int(tmdb_id)
        meta["original_language"] = original_language
        meta["no_ids"] = filename_search

    no_original_language = False
    if meta.get("original_language", None) is None:
        no_original_language = True

    # if we have all of the ids, search everything all at once
    if int(meta.get("imdb_id") or 0) != 0 and int(meta.get("tvdb_id") or 0) != 0 and int(meta.get("tmdb_id") or 0) != 0 and int(meta.get("tvmaze_id") or 0) != 0:
        meta = await prep_instance.metadata_searching_manager.all_ids(meta)

    # Check if IMDb, TMDb, and TVDb IDs are all present
    elif int(meta.get("imdb_id") or 0) != 0 and int(meta.get("tvdb_id") or 0) != 0 and int(meta.get("tmdb_id") or 0) != 0 and not meta.get("quickie_search", False):
        meta = await prep_instance.metadata_searching_manager.imdb_tmdb_tvdb(meta, filename)

    # Check if both IMDb and TVDB IDs are present
    elif int(meta.get("imdb_id") or 0) != 0 and int(meta.get("tvdb_id") or 0) != 0 and not meta.get("quickie_search", False):
        meta = await prep_instance.metadata_searching_manager.imdb_tvdb(meta, filename)

    # Check if both IMDb and TMDb IDs are present
    elif int(meta.get("imdb_id") or 0) != 0 and int(meta.get("tmdb_id") or 0) != 0 and not meta.get("quickie_search", False):
        meta = await prep_instance.metadata_searching_manager.imdb_tmdb(meta, filename)

    # we should have tmdb id one way or another, so lets get data if needed
    if int(meta.get("tmdb_id") or 0) != 0:
        await prep_instance.tmdb_manager.set_tmdb_metadata(meta, filename)

    # If there was no original language set before the combined metadata searching, tvdb changes mean we might have set a bad tvdb series name
    # Now that we have original language, we can safely kill the tvdb series name if it was en original to account for the change
    if meta.get("tvdb_series_name", None) and meta.get("original_language", "en") == "en" and meta.get("tmdb_id", 0) != 0 and no_original_language:
        meta["tvdb_series_name"] = None

    # If there's a mismatch between IMDb and TMDb IDs, try to resolve it
    if meta.get("imdb_mismatch", False) and "subsplease" not in meta.get("uuid", "").lower():
        if meta["debug"]:
            console.print("[yellow]IMDb ID mismatch detected, attempting to resolve...[/yellow]")
        # with refactored tmdb, it quite likely to be correct
        meta["imdb_id"] = meta.get("mismatched_imdb_id", 0)
        meta["imdb_info"] = None

    # Get IMDb ID if not set
    if meta.get("imdb_id") == 0 and meta.get("category") not in ("BOOK", "GAME"):
        try:
            search_year_value = _normalize_search_year(meta.get("search_year"))
            meta["imdb_id"] = await imdb_manager.search_imdb(
                filename,
                search_year_value,
                quickie=False,
                category=meta.get("category", None),
                debug=debug,
                secondary_title=meta.get("secondary_title", None),
                untouched_filename=untouched_filename,
                attempted=0,
                duration=duration,
                unattended=unattended,
            )
        except Exception as e:
            console.print(f"[red]Error searching IMDb: {e}[/red]")
            raise Exception(f"Error searching IMDb: {e}") from e

    # user might have skipped tmdb earlier, lets double check
    if meta.get("imdb_id") != 0 and meta.get("tmdb_id") == 0 and meta.get("category") not in ("BOOK", "GAME"):
        console.print("[yellow]No TMDB ID found, attempting to fetch from IMDb...[/yellow]")
        imdb_id_value = _to_int(meta.get("imdb_id"))
        tvdb_id_value = _to_int(meta.get("tvdb_id"))
        search_year_value = _normalize_search_year(meta.get("search_year"))
        category, tmdb_id, original_language, filename_search = await prep_instance.tmdb_manager.get_tmdb_from_imdb(
            imdb_id_value,
            tvdb_id_value if tvdb_id_value else None,
            search_year_value,
            filename,
            debug=meta.get("debug", False),
            mode=meta.get("mode", "discord"),
            category_preference=meta.get("category"),
            imdb_info=meta.get("imdb_info", None),
        )

        meta["category"] = category
        meta["tmdb_id"] = _to_int(tmdb_id)
        meta["original_language"] = original_language
        meta["no_ids"] = filename_search

    tmdb_id_value = _to_int(meta.get("tmdb_id"))
    if tmdb_id_value != 0 and meta.get("category") not in ("BOOK", "GAME"):
        await prep_instance.tmdb_manager.set_tmdb_metadata(meta, filename)

    # Ensure IMDb info is retrieved if it wasn't already fetched
    imdb_id_value = _to_int(meta.get("imdb_id"))
    if meta.get("imdb_info", None) is None and imdb_id_value != 0 and meta.get("category") not in ("BOOK", "GAME"):
        imdb_info = await imdb_manager.get_imdb_info_api(imdb_id_value, manual_language=meta.get("manual_language"), debug=meta.get("debug", False))
        meta["imdb_info"] = imdb_info


async def finalize_metadata(
    prep_instance: Any, meta: dict[str, Any], videopath: str, bdinfo: dict[str, Any], mi: Optional[dict[str, Any]], filename: str, _untouched_filename: str, video: str
) -> None:
    check_valid_data = meta.get("imdb_info", {}).get("title", "")
    if check_valid_data:
        try:
            title = meta["title"].lower().strip()
        except KeyError:
            console.print("[red]Title is missing from TMDB....")
            sys.exit(1)
        aka = meta.get("imdb_info", {}).get("title", "").strip().lower()
        imdb_aka = meta.get("imdb_info", {}).get("aka", "").strip().lower()
        year = str(meta.get("imdb_info", {}).get("year", ""))

        if aka and not meta.get("aka"):
            aka_trimmed = aka[4:].strip().lower() if aka.lower().startswith("aka") else aka.lower()
            difference = SequenceMatcher(None, title, aka_trimmed).ratio()
            if difference >= 0.7 or not aka_trimmed or aka_trimmed in title:
                aka = None

            difference = SequenceMatcher(None, title, imdb_aka).ratio()
            if difference >= 0.7 or not imdb_aka or imdb_aka in title:
                imdb_aka = None

            if aka is not None:
                aka = meta.get("imdb_info", {}).get("title", "").replace(f"({year})", "").strip() if f"({year})" in aka else meta.get("imdb_info", {}).get("title", "").strip()
                meta["aka"] = f"AKA {aka.strip()}"
                meta["title"] = meta["title"].strip()
            elif imdb_aka is not None:
                if f"({year})" in imdb_aka:
                    imdb_aka = meta.get("imdb_info", {}).get("aka", "").replace(f"({year})", "").strip()
                else:
                    imdb_aka = meta.get("imdb_info", {}).get("aka", "").strip()
                meta["aka"] = f"AKA {imdb_aka.strip()}"
                meta["title"] = meta["title"].strip()

    if meta.get("aka") is None:
        meta["aka"] = ""

    # if it was skipped earlier, make sure we have the season/episode data
    if not meta.get("not_anime", False) and meta.get("category") == "TV":
        meta = await prep_instance.season_episode_manager.get_season_episode(video, meta)

    if meta["category"] == "TV" and meta.get("tv_pack"):
        await prep_instance.season_episode_manager.check_season_pack_completeness(meta)

    # lets check for tv movies
    meta["tv_movie"] = False
    if meta["imdb_id"] != 0:
        is_tv_movie = meta.get("imdb_info", {}).get("type", "")
        if is_tv_movie:
            tv_movie_keywords = ["tv movie", "tv special", "tvmovie"]
            if any(re.search(rf"(^|,\s*){re.escape(keyword)}(\s*,|$)", is_tv_movie, re.IGNORECASE) for keyword in tv_movie_keywords):
                if meta["debug"]:
                    console.print(f"[yellow]Identified as TV Movie based on IMDb type: {is_tv_movie}[/yellow]")
                meta["tv_movie"] = True

    if (meta["category"] == "TV" or meta.get("tv_movie", False)) and meta.get("category") not in ("BOOK", "GAME"):
        both_ids_searched = False
        search_year_value = _normalize_search_year(meta.get("search_year"))
        if meta.get("tvmaze_id", 0) == 0 and meta.get("tvdb_id", 0) == 0:
            tvmaze, tvdb, tvdb_data, tvdb_name = await prep_instance.metadata_searching_manager.get_tvmaze_tvdb(
                filename,
                search_year_value or "",
                meta.get("imdb_id", 0),
                meta.get("tmdb_id", 0),
                meta.get("manual_data"),
                meta.get("tvmaze_manual", 0),
                year=meta.get("year", ""),
                debug=meta.get("debug", False),
                tv_movie=meta.get("tv_movie", False),
            )
            both_ids_searched = True
            if tvmaze:
                meta["tvmaze_id"] = tvmaze
                if meta["debug"]:
                    console.print(f"[blue]Found TVMAZE ID from search: {tvmaze}[/blue]")
            if tvdb:
                meta["tvdb_id"] = tvdb
                if meta["debug"]:
                    console.print(f"[blue]Found TVDB ID from search: {tvdb}[/blue]")
            if tvdb_data:
                meta["tvdb_search_results"] = tvdb_data
                if meta["debug"]:
                    console.print("[blue]Found TVDB search results from search.[/blue]")
            if tvdb_name:
                meta["tvdb_series_name"] = tvdb_name
                if meta["debug"]:
                    console.print(f"[blue]Found TVDB series name from search: {tvdb_name}[/blue]")
        if meta.get("tvmaze_id", 0) == 0 and not both_ids_searched:
            if meta["debug"]:
                console.print("[yellow]No TVMAZE ID found, attempting to fetch...[/yellow]")
            meta["tvmaze_id"] = await tvmaze_manager.search_tvmaze(
                filename,
                search_year_value or "",
                meta.get("imdb_id", 0),
                meta.get("tvdb_id", 0),
                manual_date=meta.get("manual_date"),
                tvmaze_manual=meta.get("tvmaze_manual"),
                debug=meta.get("debug", False),
                return_full_tuple=False,
            )
        if meta.get("tvdb_id", 0) == 0:
            if meta["debug"]:
                console.print("[yellow]No TVDB ID found, attempting to fetch...[/yellow]")
            try:
                series_results, series_id = await prep_instance.tvdb_handler.search_tvdb_series(filename=filename, year=meta.get("year", ""), debug=meta.get("debug", False))
                if series_id:
                    meta["tvdb_id"] = series_id
                    console.print(f"[blue]Found TVDB series ID from search: {series_id}[/blue]")
                if series_results:
                    meta["tvdb_search_results"] = series_results
            except Exception as e:
                console.print(f"[red]Error searching TVDB: {e}[/red]")

        # all your episode data belongs to us
        meta = await prep_instance.metadata_searching_manager.get_tv_data(meta)

        if meta.get("tvdb_imdb_id", None):
            imdb = meta["tvdb_imdb_id"].replace("tt", "")
            if imdb.isdigit() and imdb != meta.get("imdb_id", 0):
                episode_info = await imdb_manager.get_imdb_from_episode(imdb, debug=True)
                if episode_info:
                    series_id = episode_info.get("series", {}).get("series_id", None)
                    if series_id:
                        series_imdb = series_id.replace("tt", "")
                        if series_imdb.isdigit() and int(series_imdb) != meta.get("imdb_id", 0):
                            if meta["debug"]:
                                console.print(f"[yellow]Updating IMDb ID from episode data: {series_imdb}")
                            meta["imdb_id"] = int(series_imdb)
                            imdb_info = await imdb_manager.get_imdb_info_api(meta["imdb_id"], manual_language=meta.get("manual_language"), debug=meta.get("debug", False))
                            meta["imdb_info"] = imdb_info
                            check_valid_data = meta.get("imdb_info", {}).get("title", "")
                            if check_valid_data:
                                title_val = meta.get("title", "").strip()
                                aka_val = meta.get("imdb_info", {}).get("aka", "").strip()
                                year_val = str(meta.get("imdb_info", {}).get("year", ""))

                                if aka_val:
                                    aka_trimmed = aka_val[4:].strip().lower() if aka_val.lower().startswith("aka") else aka_val.lower()
                                    difference = SequenceMatcher(None, title_val.lower(), aka_trimmed).ratio()
                                    if difference >= 0.7 or not aka_trimmed or aka_trimmed in title_val:
                                        aka_val = None

                                    if aka_val is not None:
                                        if f"({year_val})" in aka_val:
                                            aka_val = meta.get("imdb_info", {}).get("aka", "").replace(f"({year_val})", "").strip()
                                        else:
                                            aka_val = meta.get("imdb_info", {}).get("aka", "").strip()
                                        meta["aka"] = f"AKA {aka_val.strip()}"
                                    else:
                                        meta["aka"] = ""
                                else:
                                    meta["aka"] = ""

        if meta.get("tvdb_series_name") and meta["category"] == "TV":
            series_name = meta.get("tvdb_series_name")
            if series_name and meta.get("title") != series_name:
                if meta["debug"]:
                    console.print(f"[yellow]tvdb series name: {series_name}")
                year_match = re.search(r"\b(19|20)\d{2}\b", series_name)
                if year_match:
                    year_match.group(0)
                    series_name = re.sub(r"\s*\b(19|20)\d{2}\b\s*", "", series_name).strip()
                series_name = series_name.replace("(", "").replace(")", "").strip()
                should_use_tvdb_series_name = series_name and not _tvdb_title_drops_existing_leading_article(meta.get("title"), series_name)
                if should_use_tvdb_series_name:
                    meta["title"] = series_name

    # bluray.com data if config
    get_bluray_info = prep_instance.config["DEFAULT"].get("get_bluray_info", False)
    meta["bluray_score"] = int(float(prep_instance.config["DEFAULT"].get("bluray_score", 100)))
    meta["bluray_single_score"] = int(float(prep_instance.config["DEFAULT"].get("bluray_single_score", 100)))
    meta["use_bluray_images"] = prep_instance.config["DEFAULT"].get("use_bluray_images", False)
    if (
        meta.get("is_disc") in ("BDMV", "DVD")
        and get_bluray_info
        and (meta.get("distributor") is None or meta.get("region") is None)
        and meta.get("imdb_id") != 0
        and not meta.get("emby", False)
        and not meta.get("edit", False)
        and not meta.get("site_check", False)
    ):
        releases = await get_bluray_releases(meta)

        if releases and meta.get("is_disc") in ("BDMV", "DVD") and meta.get("use_bluray_images", False):
            # and if we getting bluray/dvd images, we'll rehost them
            url_host_mapping = {
                "ibb.co": "imgbb",
                "pixhost.to": "pixhost",
                "imgbox.com": "imgbox",
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
    if user_overrides and not meta.get("no_override", False) and not meta.get("emby", False):
        meta = await prep_instance.overrides.get_source_override(meta)

    meta["video"] = video

    mi_data: dict[str, Any] = mi or {}
    base_dir = meta["base_dir"]
    folder_id = os.path.basename(meta["path"])

    if not meta.get("emby", False) and meta.get("category") in ("TV", "MOVIE"):
        meta["container"] = await video_manager.get_container(meta)

        meta["audio"], meta["channels"], meta["has_commentary"] = await prep_instance.audio_manager.get_audio_v2(mi_data, meta, bdinfo)

        meta["3D"] = await video_manager.is_3d(bdinfo)

        is_disc_value = str(meta.get("is_disc") or "")
        meta["source"], meta["type"] = await get_source(meta["type"], video, str(meta.get("path") or ""), is_disc_value, meta, folder_id, base_dir)

        meta["uhd"] = await video_manager.get_uhd(
            meta["type"],
            guessit_fn(str(meta.get("path") or "")),
            str(meta.get("resolution", "")),
            str(meta.get("path") or ""),
        )
        meta["hdr"] = await video_manager.get_hdr(mi_data, bdinfo)

        meta["distributor"] = await get_distributor(meta["distributor"])
        if meta["distributor"] is None:
            meta["distributor"] = ""

        if meta.get("is_disc", None) == "BDMV":  # Blu-ray Specific
            meta["region"] = await get_region(bdinfo, meta.get("region", None))
            meta["video_codec"] = await video_manager.get_video_codec(bdinfo)
        else:
            meta["video_encode"], meta["video_codec"], meta["has_encode_settings"], meta["bit_depth"] = await video_manager.get_video_encode(mi_data, meta["type"], bdinfo)

        if meta["region"] is None:
            meta["region"] = ""

        if meta.get("no_edition") is False:
            manual_edition = meta.get("manual_edition") or ""
            meta["edition"], meta["repack"], meta["webdv"] = await get_edition(meta["uuid"], bdinfo, meta["filelist"], manual_edition, meta)
            if "REPACK" in meta.get("edition", ""):
                repack_match = re.search(r"REPACK[\d]?", meta["edition"])
                if repack_match:
                    meta["repack"] = repack_match.group(0)
                meta["edition"] = re.sub(r"REPACK[\d]?", "", meta["edition"]).strip().replace("  ", " ")
        else:
            meta["edition"] = ""

        meta["valid_mi_settings"] = True
        if not meta["is_disc"] and meta["type"] in ["ENCODE"] and meta["video_codec"] not in ["AV1"]:
            valid_mi_settings = validate_mediainfo(meta, debug=meta["debug"], settings=True)
            if not valid_mi_settings:
                console.print("[red]MediaInfo validation failed. This file does not contain encode settings.")
                meta["valid_mi_settings"] = False
                await asyncio.sleep(2)

        meta.get("stream", False)
        meta["stream"] = await prep_instance.stream_optimized(meta["stream"])

        if meta.get("tag") == "-SubsPlease":  # SubsPlease-specific
            tracks = meta.get("mediainfo", {}).get("media", {}).get("track", [])  # Get all tracks
            bitrate = tracks[1].get("BitRate", "") if len(tracks) > 1 and not isinstance(tracks[1].get("BitRate", ""), dict) else ""  # Check that bitrate is not a dict
            bitrate_oldMediaInfo = (
                tracks[0].get("OverallBitRate", "") if len(tracks) > 0 and not isinstance(tracks[0].get("OverallBitRate", ""), dict) else ""
            )  # Check for old MediaInfo
            meta["episode_title"] = ""
            if (
                (bitrate.isdigit() and int(bitrate) >= 8000000)
                or (bitrate_oldMediaInfo.isdigit() and int(bitrate_oldMediaInfo) >= 8000000)
                and meta.get("resolution") == "1080p"
            ):  # 8Mbps for 1080p
                meta["service"] = "CR"
            elif (bitrate.isdigit() or bitrate_oldMediaInfo.isdigit()) and meta.get(
                "resolution"
            ) == "1080p":  # Only assign if at least one bitrate is present, otherwise leave it to user
                meta["service"] = "HIDI"
            elif (
                (bitrate.isdigit() and int(bitrate) >= 4000000)
                or (bitrate_oldMediaInfo.isdigit() and int(bitrate_oldMediaInfo) >= 4000000)
                and meta.get("resolution") == "720p"
            ):  # 4Mbps for 720p
                meta["service"] = "CR"
            elif (bitrate.isdigit() or bitrate_oldMediaInfo.isdigit()) and meta.get("resolution") == "720p":
                meta["service"] = "HIDI"

        if meta.get("service", None) in (None, ""):
            meta["service"], meta["service_longname"] = await get_service(video, meta.get("tag", ""), meta["audio"], meta["filename"])
        elif meta.get("service"):
            services = cast(dict[str, str], await get_service(get_services_only=True))
            service_code = str(meta.get("service") or "")
            meta["service_longname"] = max((k for k, v in services.items() if v == service_code), key=len, default=service_code)

        # Parse NFO for scene releases to get service
        if meta["scene"] and not meta.get("service") and meta["category"] == "TV":
            await prep_instance.parse_scene_nfo(meta)

        # Combine genres from TMDB and IMDb
        tmdb_genres = str(meta.get("genres") or "")
        imdb_genres = str(meta.get("imdb_info", {}).get("genres") or "")

        all_genres: list[str] = []
        if tmdb_genres:
            all_genres.extend([g.strip() for g in tmdb_genres.split(",") if g.strip()])
        if imdb_genres:
            all_genres.extend([g.strip() for g in imdb_genres.split(",") if g.strip()])

        seen: set[str] = set()
        unique_genres: list[str] = []
        for genre in all_genres:
            genre_lower = genre.lower()
            if genre_lower not in seen:
                seen.add(genre_lower)
                unique_genres.append(genre)

        meta["combined_genres"] = ", ".join(unique_genres) if unique_genres else ""
        meta["adult_media"] = prep_instance.check_adult_media(meta)

    # Process group tag for all categories (TV, MOVIE, BOOK, etc.)
    if meta.get("tag", None) is None:
        if meta.get("we_need_tag", False):
            meta["tag"] = await get_tag(meta["scene_name"], meta)
        else:
            meta["tag"] = await get_tag(video, meta)
            # all lowercase filenames will have bad group tag, it's probably a scene release.
            # some extracted files do not match release name so lets double check if it really is a scene release
            if not meta.get("scene") and meta["tag"]:
                base = os.path.basename(video)
                match = re.match(r"^(.+)\.[a-zA-Z0-9]{3,4}$", os.path.basename(video))
                if match and (not meta["is_disc"] or meta.get("keep_folder", False)):
                    base = match.group(1)
                    is_all_lowercase = base.islower()
                    if is_all_lowercase:
                        release_name, _, _ = await prep_instance.scene_manager.is_scene(videopath, meta, meta.get("imdb_id", 0), lower=True)
                        if release_name:
                            try:
                                meta["scene_name"] = release_name
                                meta["tag"] = await get_tag(release_name, meta)
                            except Exception:
                                console.print("[red]Error getting tag from scene name, check group tag.[/red]")

    else:
        if not meta["tag"].startswith("-") and meta["tag"] != "":
            meta["tag"] = f"-{meta['tag']}"

    meta = await tag_override(meta)

    # Automatically set personalrelease to True if detected release group matches any of the personal_release_groups tags
    personal_groups = prep_instance.config["DEFAULT"].get("personal_release_groups", [])
    if isinstance(personal_groups, list) and meta.get("tag"):
        detected_group = meta["tag"].lstrip("-").lower()
        personal_groups_clean = [str(g).lstrip("-").lower() for g in personal_groups if g]
        if detected_group in personal_groups_clean:
            meta["personalrelease"] = True
            if meta["debug"]:
                console.print(f"[green]Detected release group in personal_release_groups, automatically setting --personalrelease to True - {detected_group}[/green]")

    channels = meta.get("channels", "")
    if channels and meta["tag"][1:].startswith(channels):
        meta["tag"] = meta["tag"].replace(f"-{channels}", "")

    if meta.get("no_tag", False):
        meta["tag"] = ""

    # return duplicate ids so I don't have to catch every site file
    # this has the other advantage of stringing imdb for this object
    meta["tmdb"] = meta.get("tmdb_id")
    imdb_id_value = _to_int(meta.get("imdb_id"))
    if imdb_id_value != 0:
        imdb_str = str(imdb_id_value).zfill(7)
        meta["imdb"] = imdb_str
    else:
        meta["imdb"] = "0"
    meta["mal"] = meta.get("mal_id")
    meta["tvdb"] = meta.get("tvdb_id")
    meta["tvmaze"] = meta.get("tvmaze_id")

    if meta.get("category") == "BOOK":
        meta["container"] = os.path.splitext(videopath)[1].lstrip(".").lower()
        meta["audio"] = ""
        meta["channels"] = ""
        meta["has_commentary"] = False
        meta["3D"] = ""
        meta["source"] = "WEB"
        if not meta.get("type"):
            meta["type"] = os.path.splitext(videopath)[1].lstrip(".").upper()
        if meta.get("type", "").upper() in ("CBR", "CBZ"):
            meta["comic"] = True
        meta["uhd"] = ""
        meta["hdr"] = ""
        meta["distributor"] = ""
        meta["region"] = ""
        meta["video_codec"] = ""
        meta["video_encode"] = ""
        meta["has_encode_settings"] = False
        meta["bit_depth"] = "0"
        if not meta.get("edition"):
            meta["edition"] = str(meta.get("manual_edition") or "").strip()
        meta["repack"] = ""
        meta["webdv"] = False

        if not meta.get("title"):
            meta["title"] = ""
        if not meta.get("year"):
            meta["year"] = ""
        if not meta.get("overview"):
            meta["overview"] = ""
        if not meta.get("genres"):
            meta["genres"] = ""
    elif meta.get("category") == "GAME":
        meta["container"] = os.path.splitext(videopath)[1].lstrip(".").lower()
        meta["audio"] = ""
        meta["channels"] = ""
        meta["has_commentary"] = False
        meta["3D"] = ""
        if not meta.get("source"):
            meta["source"] = ""
        if not meta.get("type"):
            meta["type"] = "GAME"
        meta["uhd"] = ""
        meta["hdr"] = ""
        meta["distributor"] = ""
        meta["region"] = ""
        meta["video_codec"] = ""
        meta["video_encode"] = ""
        meta["has_encode_settings"] = False
        meta["bit_depth"] = "0"
        meta["edition"] = ""
        meta["repack"] = ""
        meta["webdv"] = False

        if not meta.get("title"):
            meta["title"] = ""
        if not meta.get("year"):
            meta["year"] = ""
        if not meta.get("overview"):
            meta["overview"] = ""
        if not meta.get("genres"):
            meta["genres"] = ""
