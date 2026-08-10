# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import asyncio
import copy
import sys
from collections.abc import Mapping
from typing import Any, cast

import cli_ui

from src.cleanup import cleanup_manager
from src.console import logger, prompt_in_thread
from src.dupe_checking import DupeChecker
from src.imdb import imdb_manager
from src.meta import Meta
from src.metadata_searching import get_douban_id
from src.trackers.AVISTAZ.routing import AvistaZNetworkRouter
from src.trackers.passthepopcorn import PassThePopcorn
from src.trackersetup import TrackerSetup, tracker_class_map
from src.uphelper import UploadHelper


def merge_tracker_status(processed: dict[str, dict[str, Any]], existing: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Preserve routing metadata while keeping fresh processing results authoritative."""
    merged = {tracker: dict(status) for tracker, status in existing.items()}
    for tracker, status in processed.items():
        merged.setdefault(tracker, {}).update(status)
    return merged


class TrackerStatusManager:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.trackers_config = cast(Mapping[str, Mapping[str, Any]], config.get("TRACKERS", {}))

    async def process_all_trackers(self, meta: Meta) -> int:
        tracker_status: dict[str, dict[str, Any]] = {}
        successful_trackers = 0
        tracker_setup: Any = TrackerSetup(config=self.config)
        tracker_setup.filter_unsupported_trackers(meta)
        await AvistaZNetworkRouter(self.config, tracker_class_map).apply(meta)
        helper: Any = UploadHelper(self.config)
        dupe_checker = DupeChecker(self.config)
        if any(tracker in meta.trackers for tracker in ["MTEAM", "LAJIDUI", "PTFANS", "PTGTK", "RAILGUNPT"]):
            meta.douban_id = await get_douban_id(meta)
        meta_lock = asyncio.Lock()
        status_map = meta.tracker_status
        for tracker in meta.trackers:
            if tracker not in status_map:
                status_map[tracker] = {}

        # Prompt for IMDB ID once if any tracker needs it and it's missing in attended mode
        if not meta.get("unattended", False) and meta.get("imdb_id", 0) == 0:
            needs_imdb = any(t in meta.trackers for t in {"TORRENTHR", "PASSTHEPOPCORN"})
            if needs_imdb:
                while True:
                    try:
                        imdb_id = await prompt_in_thread(
                            cli_ui.ask_string, "Unable to find IMDB id, please enter e.g.(tt1234567) or press Enter to skip uploading to trackers requiring it:"
                        )
                    except EOFError:
                        logger.info("\n[red]Exiting on user request (Ctrl+C)[/red]")
                        await cleanup_manager.cleanup()
                        cleanup_manager.reset_terminal()
                        sys.exit(1)

                    if imdb_id is None or imdb_id.strip() == "":
                        meta["imdb_id"] = 0
                        break

                    imdb_id = imdb_id.strip().lower()
                    if imdb_id.startswith("tt") and imdb_id[2:].isdigit():
                        meta["imdb_id"] = int(imdb_id[2:])
                        meta["imdb"] = imdb_id[2:].zfill(7)
                        meta["imdb_info"] = await imdb_manager.get_imdb_info_api(
                            meta["imdb_id"],
                            manual_language=meta.get("manual_language"),
                        )
                        break
                    cli_ui.error("Invalid IMDB ID format. Expected format: tt1234567")

        async def process_single_tracker(tracker_name: str, shared_meta: Meta) -> tuple[str, dict[str, bool], str | None, Any]:
            local_meta = copy.deepcopy(shared_meta)  # Ensure each task gets its own copy of meta
            local_tracker_status = {"banned": False, "skipped": False, "dupe": False, "upload": False, "other": False}
            display_name = None
            tracker_class = None

            if local_meta["name"].endswith("DUPE?"):
                local_meta["name"] = local_meta["name"].replace(" DUPE?", "")

            if tracker_name in ("MANUAL", "USENET"):
                local_tracker_status["upload"] = True
                return tracker_name, local_tracker_status, None, None

            if tracker_name in tracker_class_map:
                tracker_class = tracker_class_map[tracker_name](config=self.config)
                if tracker_name in {"TORRENTHR", "PASSTHEPOPCORN"} and local_meta.get("imdb_id", 0) == 0:
                    local_tracker_status["skipped"] = True

                if not local_tracker_status["skipped"]:
                    result = await tracker_setup.check_banned_group(tracker_class.tracker, tracker_class.banned_groups, local_meta)
                    local_tracker_status["banned"] = bool(result)

                if local_meta["tracker_status"][tracker_name].get("skip_upload"):
                    local_tracker_status["skipped"] = True
                elif "skipped" not in local_meta and not local_tracker_status["skipped"]:
                    local_tracker_status["skipped"] = False

                # Check for missing required BOOK fields in unattended mode
                if local_meta.get("category") == "BOOK" and local_meta.get("unattended", False):
                    from src.book_prep import is_valid_book_language

                    book_required_fields = ["title", "author", "year", "book_language"]
                    book_missing: list[str] = []
                    for f in book_required_fields:
                        val = local_meta.get(f)
                        if not val or str(val).strip().lower() in ("", "none", "null"):
                            book_missing.append(f)
                        elif f == "book_language":
                            iso = local_meta.get("book_language_iso", "")
                            if not is_valid_book_language(str(val), str(iso)):
                                book_missing.append(f)
                    if book_missing:
                        logger.info(f"[yellow]{tracker_name}: Skipping upload because required BOOK fields are missing: {', '.join(book_missing)}[/yellow]")
                        local_tracker_status["skipped"] = True

                # Check for missing required GAME fields in unattended mode
                elif local_meta.get("category") == "GAME" and local_meta.get("unattended", False):
                    game_required_fields = ["title", "year", "platform", "game_version"]
                    game_missing: list[str] = []
                    for f in game_required_fields:
                        val = local_meta.get(f)
                        if not val or str(val).strip().lower() in ("", "none", "null") or (f == "platform" and "," in str(val)):
                            game_missing.append(f)
                    if game_missing:
                        logger.info(f"[yellow]{tracker_name}: Skipping upload because required GAME fields are missing: {', '.join(game_missing)}[/yellow]")
                        local_tracker_status["skipped"] = True

                if not local_tracker_status["banned"] and not local_tracker_status["skipped"]:
                    claimed = await tracker_setup.get_torrent_claims(local_meta, tracker_name)
                    local_tracker_status["skipped"] = bool(claimed)

                    if tracker_name not in {"PASSTHEPOPCORN"} and not local_tracker_status["skipped"]:
                        if hasattr(tracker_class, "get_additional_checks"):
                            import inspect

                            if inspect.iscoroutinefunction(tracker_class.get_additional_checks):
                                should_continue = await tracker_class.get_additional_checks(local_meta)
                            else:
                                should_continue = tracker_class.get_additional_checks(local_meta)
                            if not should_continue:
                                local_tracker_status["skipped"] = True
                                local_meta.skipping = tracker_name

                        if not local_tracker_status["skipped"]:
                            try:
                                dupes: list[Any] = cast(list[Any], await tracker_class.search_existing(local_meta))
                                # set trackers here so that they are not double checked later with cross seeding
                                async with meta_lock:
                                    meta.setdefault("dupe_checked_trackers", []).append(tracker_name)
                                if local_meta["tracker_status"][tracker_name].get("other", False):
                                    local_tracker_status["other"] = True
                            except Exception as e:
                                logger.info(f"[bold red]Error searching for duplicates on {tracker_name}: {e}[/bold red]")
                                if local_meta.get("unattended", False):
                                    local_tracker_status["skipped"] = True
                                    local_meta.skipping = tracker_name
                                    dupes = []
                                else:
                                    try:
                                        if await helper.prompt_yes_no(
                                            f"Duplicate check failed on {tracker_name}. Do you want to proceed with the upload anyway?", default=False
                                        ):
                                            dupes = []
                                            # set trackers here so that they are not double checked later with cross seeding
                                            async with meta_lock:
                                                meta.setdefault("dupe_checked_trackers", []).append(tracker_name)
                                        else:
                                            local_tracker_status["skipped"] = True
                                            local_meta.skipping = tracker_name
                                            dupes = []
                                    except EOFError:
                                        logger.info("\n[red]Exiting on user request (Ctrl+C)[/red]")
                                        await cleanup_manager.cleanup()
                                        cleanup_manager.reset_terminal()
                                        sys.exit(1)
                        else:
                            dupes = []
                    elif tracker_name == "PASSTHEPOPCORN":
                        ptp: Any = PassThePopcorn(config=self.config)
                        if hasattr(ptp, "get_additional_checks"):
                            import inspect

                            if inspect.iscoroutinefunction(ptp.get_additional_checks):
                                should_continue = await ptp.get_additional_checks(local_meta)
                            else:
                                should_continue = ptp.get_additional_checks(local_meta)
                            if not should_continue:
                                local_tracker_status["skipped"] = True
                                local_meta.skipping = tracker_name

                        if not local_tracker_status["skipped"]:
                            try:
                                group_id = await ptp.get_group_by_imdb(local_meta["imdb"])
                                async with meta_lock:
                                    meta.ptp_groupid = group_id
                                dupes = cast(list[Any], await ptp.search_existing(group_id or "", cast(dict[str, Any], local_meta)))
                            except Exception as e:
                                logger.info(f"[bold red]Error searching for duplicates on {tracker_name}: {e}[/bold red]")
                                if local_meta.get("unattended", False):
                                    local_tracker_status["skipped"] = True
                                    local_meta.skipping = tracker_name
                                    dupes = []
                                else:
                                    try:
                                        if await helper.prompt_yes_no(
                                            f"Duplicate check failed on {tracker_name}. Do you want to proceed with the upload anyway?", default=False
                                        ):
                                            dupes = []
                                        else:
                                            local_tracker_status["skipped"] = True
                                            local_meta.skipping = tracker_name
                                            dupes = []
                                    except EOFError:
                                        logger.info("\n[red]Exiting on user request (Ctrl+C)[/red]")
                                        await cleanup_manager.cleanup()
                                        cleanup_manager.reset_terminal()
                                        sys.exit(1)
                        else:
                            dupes = []
                    else:
                        dupes = []

                    async with meta_lock:
                        if "initial_dupes" not in meta:
                            meta.initial_dupes = {}
                        meta.initial_dupes[tracker_name] = copy.deepcopy(dupes)

                    if tracker_name == "AMIGOSSHARE" and (meta.anon if meta.anon is not None else "false"):
                        logger.info(
                            "PORTUGAS: [yellow]Aviso: Você solicitou um upload anônimo, mas o AMIGOSSHARE não suporta essa opção.[/yellow][red] O envio não será anônimo.[/red]"
                        )
                        logger.warning(
                            "EN: [yellow]Warning: You requested an anonymous upload, but AMIGOSSHARE does not support this option.[/yellow][red] The upload will not be anonymous.[/red]"
                        )

                    if ("skipping" not in local_meta or local_meta["skipping"] is None) and not local_tracker_status["skipped"]:
                        dupes = cast(list[Any], await dupe_checker.filter_dupes(dupes, local_meta, tracker_name))

                        # Run dupe check first so it can modify local_meta (e.g., set cross-seed values)
                        is_dupe, local_meta = await helper.dupe_check(dupes, local_meta, tracker_name)
                        if is_dupe:
                            local_tracker_status["dupe"] = True

                        matched_episode_ids = local_meta.get(f"{tracker_name}_matched_episode_ids", [])
                        trumpable_id = local_meta.get("trumpable_id")
                        cross_seed_key = f"{tracker_name}_cross_seed"
                        cross_seed_value = local_meta.get(cross_seed_key) if cross_seed_key in local_meta else None

                        # Only shared-state writes go under the lock
                        async with meta_lock:
                            if matched_episode_ids:
                                meta[f"{tracker_name}_matched_episode_ids"] = matched_episode_ids
                            if trumpable_id:
                                meta.trumpable_id = trumpable_id
                            if cross_seed_key in local_meta and cross_seed_value:
                                meta[cross_seed_key] = cross_seed_value

                        if tracker_name in ["AITHER", "LST"]:
                            were_trumping = local_meta.get("were_trumping", False)
                            trump_reason = local_meta.get("trump_reason")
                            trumpable_id_after_dupe_check = local_meta.get(f"{tracker_name}_trumpable_id")
                            async with meta_lock:
                                if were_trumping:
                                    meta.were_trumping = were_trumping
                                if trump_reason:
                                    meta.trump_reason = trump_reason
                                if trumpable_id_after_dupe_check:
                                    meta[f"{tracker_name}_trumpable_id"] = trumpable_id_after_dupe_check

                    elif "skipping" in local_meta:
                        local_tracker_status["skipped"] = True

                # Determine name change for display during interactive prompt
                if not local_tracker_status["banned"] and not local_tracker_status["skipped"] and not local_tracker_status["dupe"]:
                    try:
                        tracker_rename = await tracker_class.get_name(local_meta)
                    except Exception:
                        tracker_rename = None

                    if tracker_rename is not None:
                        if isinstance(tracker_rename, dict) and "name" in tracker_rename:
                            display_name = cast(str, tracker_rename["name"])
                        elif isinstance(tracker_rename, str):
                            display_name = tracker_rename

            return tracker_name, local_tracker_status, display_name, tracker_class

        searching_trackers: list[str] = [name for name in meta.trackers if name in tracker_class_map]
        if searching_trackers:
            logger.info("[yellow]Searching for existing torrents on selected trackers...")
        tasks = [process_single_tracker(tracker_name, meta) for tracker_name in meta.trackers]
        results = await asyncio.gather(*tasks)

        # Collect passed trackers and skip reasons
        passed_trackers: list[tuple[str, str | None, Any]] = []
        dupe_trackers: list[str] = []
        skipped_trackers: list[str] = []

        for tracker_name, status, display_name, tracker_class in results:
            tracker_status[tracker_name] = status
            if status["banned"]:
                pass
            elif status["skipped"]:
                skipped_trackers.append(tracker_name)
            elif status["dupe"]:
                dupe_trackers.append(tracker_name)
            else:
                passed_trackers.append((tracker_name, display_name, tracker_class))

        if skipped_trackers:
            logger.info(f"[red]Skipped due to specific tracker conditions: [bold yellow]{', '.join(skipped_trackers)}[/bold yellow].")
        if dupe_trackers:
            logger.info(f"[red]Found potential dupes on: [bold yellow]{', '.join(dupe_trackers)}[/bold yellow].\n")

        # Now handle the confirmation/upload decisions
        if meta.unattended:
            passed_names: list[str] = []
            for tracker_name, _display_name, _tracker_class in passed_trackers:
                tracker_status[tracker_name]["upload"] = True
                successful_trackers += 1
                passed_names.append(tracker_name)
            if passed_names:
                logger.info(f"[bold]{', '.join(passed_names)}[/bold]: [bold green]no potential dupes found.[/bold green]")
        else:
            # Attended mode
            prompt_trackers = [tracker_name for tracker_name, _display_name, _tracker_class in passed_trackers if tracker_name not in ("MANUAL", "USENET")]

            if not meta.get("debug", False) and prompt_trackers:
                if len(prompt_trackers) == 1:
                    tracker_name = prompt_trackers[0]
                    logger.info(f"[bold]{tracker_name}:[/bold] [green]no potential dupes found.[/green]")
                    prompt_msg = "Upload?"
                else:
                    logger.info(f"[bold]{', '.join(prompt_trackers)}:[/bold] [green]no potential dupes found.[/green]")
                    prompt_msg = "Upload to all?"

                try:
                    upload_all = await helper.prompt_yes_no(prompt_msg, default=False)
                except EOFError:
                    logger.info("\n[red]Exiting on user request (Ctrl+C)[/red]")
                    await cleanup_manager.cleanup()
                    cleanup_manager.reset_terminal()
                    sys.exit(1)

                if upload_all:
                    logger.info("[yellow]Processing approved uploads in the background...[/yellow]")

                for tracker_name, _display_name, _tracker_class in passed_trackers:
                    if tracker_name in ("MANUAL", "USENET"):
                        tracker_status[tracker_name]["upload"] = True
                        successful_trackers += 1
                    else:
                        if upload_all:
                            tracker_status[tracker_name]["upload"] = True
                            successful_trackers += 1
                        else:
                            tracker_status[tracker_name]["upload"] = False
            else:
                # No prompt required (either empty passed_trackers/prompt_trackers, or in debug mode)
                for tracker_name, _display_name, _tracker_class in passed_trackers:
                    tracker_status[tracker_name]["upload"] = True
                    successful_trackers += 1

        if meta.debug:
            logger.debug("\n[bold]Tracker Processing Summary:[/bold]")
            for t_name, status in tracker_status.items():
                banned_status = "Yes" if status["banned"] else "No"
                skipped_status = "Yes" if status["skipped"] else "No"
                dupe_status = "Yes" if status["dupe"] else "No"
                upload_status = "Yes" if status["upload"] else "No"
                logger.debug(f"Tracker: {t_name} | Banned: {banned_status} | Skipped: {skipped_status} | Dupe: {dupe_status} | [yellow]Upload:[/yellow] {upload_status}")
            logger.debug(f"\n[bold]Trackers Passed all Checks:[/bold] {successful_trackers}")
            logger.debug("", extra={"markup": False})
            logger.debug("[bold red]DEBUG MODE does not upload to sites")

        meta.tracker_status = merge_tracker_status(tracker_status, status_map)
        return successful_trackers


async def process_all_trackers(meta: Meta, config: dict[str, Any]) -> int:
    return await TrackerStatusManager(config=config).process_all_trackers(meta)
