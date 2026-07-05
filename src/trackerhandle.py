# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import asyncio
import sys
import time
import traceback
from collections.abc import Mapping, Sequence
from typing import Any, TypeAlias, cast

import cli_ui

from cogs.redaction import Redaction
from src.cleanup import cleanup_manager
from src.console import logger
from src.dupe_checking import DupeChecker
from src.get_desc import DescriptionBuilder
from src.manualpackage import ManualPackageManager
from src.meta import Meta
from src.qbitwait import Wait
from src.trackers.PTP import PTP
from src.trackers.THR import THR
from src.trackersetup import TRACKER_SETUP

StatusDict: TypeAlias = dict[str, Any]


async def check_mod_q_and_draft(
    tracker_class: Any,
    meta: Meta,
) -> tuple[str | None, str | None, dict[str, Any]]:
    tracker_capabilities = {
        'A4K': {'mod_q': True, 'draft': False},
        'AITHER': {'mod_q': True, 'draft': False},
        'BHD': {'draft_live': True},
        'BLU': {'mod_q': True, 'draft': False},
        'LST': {'mod_q': True, 'draft': True},
        'LT': {'mod_q': True, 'draft': False},
        'LUME': {'mod_q': True, 'draft': False},
    }

    modq, draft = None, None
    tracker_caps = tracker_capabilities.get(tracker_class.tracker, {})
    if tracker_class.tracker == 'BHD' and tracker_caps.get('draft_live'):
        draft_int = await tracker_class.get_live(meta)
        draft = "Draft" if draft_int == 0 else "Live"

    else:
        if tracker_caps.get('mod_q'):
            modq_flag = await tracker_class.get_flag(meta, 'modq')
            modq_enabled = str(modq_flag).lower() in ["1", "true", "yes"]
            modq = 'Yes' if modq_enabled else 'No'
        if tracker_caps.get('draft'):
            draft_flag = await tracker_class.get_flag(meta, 'draft')
            draft_enabled = str(draft_flag).lower() in ["1", "true", "yes"]
            draft = 'Yes' if draft_enabled else 'No'

    return modq, draft, tracker_caps


async def process_trackers(
    meta: Meta,
    config: dict[str, Any],
    client: Any,
    console: Any,
    api_trackers: Sequence[str],
    tracker_class_map: Mapping[str, Any],
    http_trackers: Sequence[str],
    other_api_trackers: Sequence[str],
) -> None:
    tracker_setup = TRACKER_SETUP(config=config)
    tracker_setup_any = cast(Any, tracker_setup)
    enabled_trackers = list(cast(Sequence[str], tracker_setup_any.trackers_enabled(meta)))
    manual_packager = ManualPackageManager(config)

    def print_tracker_result(
        tracker: str,
        tracker_class: Any,
        status: Mapping[str, Any],
        is_success: bool,
    ) -> None:
        """Print tracker upload result immediately after upload completes."""
        try:
            # Check config settings for what to print
            print_links = meta.print_tracker_links
            print_messages = meta.print_tracker_messages

            # If neither option is enabled, don't print anything
            if not print_links and not print_messages:
                return

            message = None
            if is_success:
                if tracker == "MTV" and 'status_message' in status and "data error" not in str(status['status_message']):
                    if print_links:
                        message = f"[green]{str(status['status_message'])}[/green]"
                elif 'torrent_id' in status and print_links:
                    torrent_url = str(getattr(tracker_class, "torrent_url", ""))
                    message = f"[green]{torrent_url}{status['torrent_id']}[/green]"
                elif (
                    'status_message' in status
                    and "data error" not in str(status['status_message'])
                    and (print_messages or (print_links and 'torrent_id' not in status))
                ):
                    message = f"{tracker}: {Redaction.redact_private_info(status['status_message'])}"
            else:
                if 'status_message' in status and "data error" in str(status['status_message']):
                    logger.info(f"[red]{tracker}: {str(status['status_message'])}[/red]")
                    return

            if message is not None:
                if config["DEFAULT"].get("show_upload_duration", True) or meta.upload_timer:
                    duration = meta.get(f'{tracker}_upload_duration')
                    if duration and isinstance(duration, (int, float)):
                        color = "#21ff00" if duration < 5 else "#9fd600" if duration < 10 else "#cfaa00" if duration < 15 else "#f17100" if duration < 20 else "#ff0000"
                        message += f" [[{color}]{duration:.2f}s[/{color}]]"
                logger.info(message)
        except Exception as e:
            logger.error(f"[red]Error printing {tracker} result: {e}[/red]")

    async def process_single_tracker(tracker: str) -> None:
        """
        try:
            _ = meta.base64.b64decode(b"dWFfc2lnbmF0dXJl").decode("utf-8")
        except KeyError:
            sys.exit()
        """

        tracker_class: Any = None
        if tracker not in {"MANUAL", "THR", "PTP"}:
            tracker_class = tracker_class_map[tracker](config=config)
        if meta.name.endswith("DUPE?"):
            meta.name = meta.name.replace(" DUPE?", "")

        tracker = tracker.replace(" ", "").upper().strip()

        async def check_bandwidth_and_dupes(tracker_name: str, t_class: Any) -> bool:
            if t_class and getattr(t_class, "is_usenet", False):
                return True
            qbit_bw_control = meta.qbit_bandwidth_control or config["DEFAULT"].get("qbit_bandwidth_control", False)
            if qbit_bw_control:
                logger.info(f"\n[yellow]{tracker_name}: Checking bandwidth...[/yellow]")
                waiter = Wait(config)
                bw_thresh = meta.qbit_bandwidth_threshold or config["DEFAULT"].get("qbit_bandwidth_threshold", 0)
                bw_time = meta.qbit_bandwidth_time or config["DEFAULT"].get("qbit_bandwidth_time", 0)
                try:
                    bw_thresh = int(bw_thresh)
                    bw_time = int(bw_time)
                except (ValueError, TypeError) as e:
                    logger.info(f"[red]Invalid bandwidth settings: {e}, skipping bandwidth wait.[/red]")
                    bw_thresh = 0
                    bw_time = 0

                if bw_thresh > 0 and bw_time > 0:
                    waited = await waiter.wait_for_bandwidth(bw_thresh, bw_time)
                    if waited:
                        logger.info(f"[yellow]{tracker_name}: Redoing dupe check after bandwidth wait...[/yellow]")
                        try:
                            if tracker_name not in {"PTP"}:
                                new_dupes = cast(list[Any], await t_class.search_existing(meta))
                            else:
                                ptp = PTP(config=config)
                                groupID = meta.ptp_groupID
                                new_dupes = cast(list[Any], await ptp.search_existing(groupID or "", meta))
                        except Exception as e:
                            logger.info(f"[bold red]{tracker_name}: Error redoing duplicate check after bandwidth wait: {e}[/bold red]")
                            status = meta.tracker_status.setdefault(tracker_name, {})
                            status["status_message"] = f"Skipped: Error redoing dupe check after bandwidth wait: {e}"
                            return False

                        initial_dupes = meta.initial_dupes.get(tracker_name, [])

                        def is_in_initial(dupe: Any) -> bool:
                            for initial_dupe in initial_dupes:
                                if isinstance(dupe, dict) and isinstance(initial_dupe, dict):
                                    if dupe.get("name") == initial_dupe.get("name") and dupe.get("size") == initial_dupe.get("size"):
                                        return True
                                elif isinstance(dupe, str) and isinstance(initial_dupe, str) and dupe == initial_dupe:
                                    return True
                            return False

                        real_new_dupes = [d for d in new_dupes if not is_in_initial(d)]

                        if real_new_dupes:
                            dupe_checker = DupeChecker(config)
                            real_new_dupes = cast(list[Any], await dupe_checker.filter_dupes(real_new_dupes, meta, tracker_name))
                            if real_new_dupes:
                                logger.info(f"[red]New dupe found on {tracker_name} during wait! Automatically skipping upload.[/red]")
                                return False
            return True

        if tracker in api_trackers:
            tracker_status = meta.tracker_status
            upload_status = cast(Mapping[str, Any], tracker_status.get(tracker, {})).get('upload', False)
            if upload_status:
                try:
                    modq, draft, tracker_caps = await check_mod_q_and_draft(tracker_class, meta)
                    if tracker_caps.get('mod_q') and modq == "Yes":
                        logger.info(f"{tracker} (modq: {modq})")
                    if (tracker_caps.get('draft') or tracker_caps.get('draft_live')) and draft in ["Yes", "Draft"]:
                        logger.info(f"{tracker} (draft: {draft})")
                    is_uploaded = False
                    try:
                        if not await check_bandwidth_and_dupes(tracker, tracker_class):
                            status = meta.tracker_status.setdefault(tracker_class.tracker, {})
                            status["status_message"] = "Skipped due to new dupe found after bandwidth wait"
                            print_tracker_result(tracker, tracker_class, status, False)
                            return
                        upload_start_time = time.time()
                        is_uploaded = await tracker_class.upload(meta)
                        upload_duration = time.time() - upload_start_time
                        meta[f'{tracker}_upload_duration'] = upload_duration
                    except Exception as e:
                        logger.info(f"[red]Upload failed: {e}")
                        logger.info(traceback.format_exc())
                        return
                except Exception:
                    logger.info(traceback.format_exc())
                    return

                if is_uploaded is None:
                    logger.warning(f"[yellow]Warning: {tracker_class.tracker} upload method returned None instead of boolean. Treating as failed upload.[/yellow]")
                    is_uploaded = False

                status = meta.tracker_status.setdefault(tracker_class.tracker, {})
                if is_uploaded and "data error" not in str(status.get("status_message", "")):
                    if not getattr(tracker_class, 'is_usenet', False):
                        await client.add_to_client(meta, tracker_class.tracker)
                    print_tracker_result(tracker, tracker_class, status, True)
                else:
                    print_tracker_result(tracker, tracker_class, status, False)
                    logger.info(f"[red]{tracker} upload failed or returned data error.[/red]")

        elif tracker in other_api_trackers:
            tracker_status = meta.tracker_status
            upload_status = cast(Mapping[str, Any], tracker_status.get(tracker, {})).get('upload', False)
            if upload_status:
                try:
                    is_uploaded = False
                    try:
                        if not await check_bandwidth_and_dupes(tracker, tracker_class):
                            status = meta.tracker_status.setdefault(tracker_class.tracker, {})
                            status["status_message"] = "Skipped due to new dupe found after bandwidth wait"
                            print_tracker_result(tracker, tracker_class, status, False)
                            return
                        upload_start_time = time.time()
                        is_uploaded = await tracker_class.upload(meta)
                        upload_duration = time.time() - upload_start_time
                        meta[f'{tracker}_upload_duration'] = upload_duration
                    except Exception as e:
                        logger.info(f"[red]Upload failed: {e}")
                        logger.info(traceback.format_exc())
                        return
                    if tracker == 'SN':
                        await asyncio.sleep(16)
                except Exception:
                    logger.info(traceback.format_exc())
                    return

                # Detect and handle None return value from upload method
                if is_uploaded is None:
                    logger.warning(f"[yellow]Warning: {tracker_class.tracker} upload method returned None instead of boolean. Treating as failed upload.[/yellow]")
                    is_uploaded = False

                status = meta.tracker_status.setdefault(tracker_class.tracker, {})
                if is_uploaded and "data error" not in str(status.get("status_message", "")):
                    if not getattr(tracker_class, 'is_usenet', False):
                        await client.add_to_client(meta, tracker_class.tracker)
                    print_tracker_result(tracker, tracker_class, status, True)
                else:
                    print_tracker_result(tracker, tracker_class, status, False)
                    logger.info(f"[red]{tracker} upload failed or returned data error.[/red]")

        elif tracker in http_trackers:
            tracker_status = meta.tracker_status
            upload_status = cast(Mapping[str, Any], tracker_status.get(tracker, {})).get('upload', False)
            if upload_status:
                try:
                    is_uploaded = False
                    try:
                        if not await check_bandwidth_and_dupes(tracker, tracker_class):
                            status = meta.tracker_status.setdefault(tracker_class.tracker, {})
                            status["status_message"] = "Skipped due to new dupe found after bandwidth wait"
                            print_tracker_result(tracker, tracker_class, status, False)
                            return
                        upload_start_time = time.time()
                        is_uploaded = await tracker_class.upload(meta)
                        upload_duration = time.time() - upload_start_time
                        meta[f'{tracker}_upload_duration'] = upload_duration
                    except Exception as e:
                        logger.info(f"[red]Upload failed: {e}")
                        logger.info(traceback.format_exc())
                        return

                except Exception:
                    logger.info(traceback.format_exc())
                    return

                # Detect and handle None return value from upload method
                if is_uploaded is None:
                    logger.warning(f"[yellow]Warning: {tracker_class.tracker} upload method returned None instead of boolean. Treating as failed upload.[/yellow]")
                    is_uploaded = False

                status = meta.tracker_status.setdefault(tracker_class.tracker, {})
                if is_uploaded and "data error" not in str(status.get("status_message", "")):
                    if not getattr(tracker_class, 'is_usenet', False):
                        await client.add_to_client(meta, tracker_class.tracker)
                    print_tracker_result(tracker, tracker_class, status, True)
                else:
                    print_tracker_result(tracker, tracker_class, status, False)
                    logger.info(f"[red]{tracker} upload failed or returned data error.[/red]")

        elif tracker == "MANUAL":
            if meta.unattended:
                do_manual = True
            else:
                try:
                    do_manual = cli_ui.ask_yes_no("Get files for manual upload?", default=True)
                except EOFError:
                    logger.info("\n[red]Exiting on user request (Ctrl+C)[/red]")
                    await cleanup_manager.cleanup()
                    cleanup_manager.reset_terminal()
                    sys.exit(1)
            if do_manual:
                for manual_tracker in enabled_trackers:
                    if manual_tracker != 'MANUAL':
                        manual_tracker = manual_tracker.replace(" ", "").upper().strip()
                        tracker_class = tracker_class_map[manual_tracker](config=config)
                        if manual_tracker in api_trackers:
                            await DescriptionBuilder(manual_tracker, config).unit3d_edit_desc(meta, manual_tracker)
                        else:
                            await tracker_class.edit_desc(meta)
                url = await manual_packager.package(meta)
                if url is False:
                    logger.info(f"[yellow]Unable to upload prep files, they can be found at `tmp/{meta.uuid}")
                else:
                    logger.info(f"[green]{meta.name}")
                    logger.info(f"[green]Files can be found at: [yellow]{url}[/yellow]")

        elif tracker == "THR":
            tracker_status = meta.tracker_status or {}
            upload_status = cast(Mapping[str, Any], tracker_status.get(tracker, {})).get('upload', False)
            if upload_status:
                thr = THR(config=config)
                thr_any = cast(Any, thr)
                is_uploaded = False
                try:
                    upload_start_time = time.time()
                    is_uploaded = await thr_any.upload(meta)
                    upload_duration = time.time() - upload_start_time
                    meta[f'{tracker}_upload_duration'] = upload_duration
                except Exception as e:
                    logger.info(f"[red]Upload failed: {e}")
                    logger.info(traceback.format_exc())
                    return
                if is_uploaded:
                    await client.add_to_client(meta, "THR")
                    status = meta.tracker_status.setdefault("THR", {})
                    print_tracker_result(tracker, thr, status, True)
                else:
                    status = meta.tracker_status.setdefault("THR", {})
                    print_tracker_result(tracker, thr, status, False)
                    logger.info(f"[red]{tracker} upload failed or returned data error.[/red]")

        elif tracker == "PTP":
            tracker_status = meta.tracker_status
            upload_status = cast(Mapping[str, Any], tracker_status.get(tracker, {})).get('upload', False)
            if upload_status:
                try:
                    ptp = PTP(config=config)
                    groupID = meta.ptp_groupID
                    ptpUrl, ptpData = await ptp.fill_upload_form(groupID, meta)
                    is_uploaded = False
                    try:
                        upload_start_time = time.time()
                        is_uploaded = await ptp.upload(meta, ptpUrl, ptpData)
                        upload_duration = time.time() - upload_start_time
                        meta[f'{tracker}_upload_duration'] = upload_duration
                    except Exception as e:
                        logger.info(f"[red]Upload failed: {e}")
                        logger.info(traceback.format_exc())
                        return
                    status = meta.tracker_status.setdefault(ptp.tracker, {})
                    if is_uploaded and "data error" not in str(status.get("status_message", "")):
                        await client.add_to_client(meta, "PTP")
                        print_tracker_result(tracker, ptp, status, True)
                    else:
                        print_tracker_result(tracker, ptp, status, False)
                        logger.info(f"[red]{tracker} upload failed or returned data error.[/red]")
                except Exception:
                    logger.info(traceback.format_exc())
                    return

    multi_screens = int(config['DEFAULT'].get('multiScreens', 2))
    discs = meta.discs or []
    one_disc = True
    if discs and len(discs) == 1:
        one_disc = True
    elif discs and len(discs) > 1:
        one_disc = False

    bandwidth_control = meta.qbit_bandwidth_control or config["DEFAULT"].get("qbit_bandwidth_control", False)

    if ((not meta.tv_pack and one_disc) or multi_screens == 0) and not bandwidth_control:
        # Run all tracker tasks concurrently with individual error handling
        tasks: list[tuple[str, asyncio.Task[None]]] = []
        for tracker in enabled_trackers:
            task = asyncio.create_task(process_single_tracker(tracker))
            tasks.append((tracker, task))

        # Wait for all tasks to complete, but don't let one tracker's failure stop others
        results = await asyncio.gather(*[task for _, task in tasks], return_exceptions=True)

        # Log any exceptions that occurred
        for (tracker, _), result in zip(tasks, results):
            if isinstance(result, Exception):
                logger.info(f"[red]{tracker} encountered an error: {result}[/red]")
                if meta.debug:
                    logger.debug(traceback.format_exception(type(result), result, result.__traceback__))
    else:
        # Process each tracker sequentially
        for tracker in enabled_trackers:
            await process_single_tracker(tracker)

    logger.info("[green]All tracker uploads processed.[/green]")
