#!/usr/bin/env python3

import requests
from src.args import Args
from src.clients import Clients
from src.trackers.COMMON import COMMON
from src.trackers.THR import THR
from src.trackers.PTP import PTP
import json
from pathlib import Path
import asyncio
import os
import sys
import platform
import shutil
import glob
import cli_ui
import traceback
import click
import re
from src.trackersetup import TRACKER_SETUP, tracker_class_map, api_trackers, other_api_trackers, http_trackers, tracker_capabilities
import time

from src.console import console
from rich.markdown import Markdown
from rich.style import Style


cli_ui.setup(color='always', title="L4G's Upload Assistant")

base_dir = os.path.abspath(os.path.dirname(__file__))

try:
    from data.config import config
except Exception:
    if not os.path.exists(os.path.abspath(f"{base_dir}/data/config.py")):
        cli_ui.info(cli_ui.red, "Configuration file 'config.py' not found.")
        cli_ui.info(cli_ui.red, "Please ensure the file is located at:", cli_ui.yellow, os.path.abspath(f"{base_dir}/data/config.py"))
        cli_ui.info(cli_ui.red, "Follow the setup instructions: https://github.com/Audionut/Upload-Assistant")
        exit()
    else:
        console.print(traceback.print_exc())

from src.prep import Prep  # noqa E402
client = Clients(config=config)
parser = Args(config)


def get_log_file(base_dir, queue_name):
    """
    Returns the path to the log file for the given base directory and queue name.
    """
    safe_queue_name = queue_name.replace(" ", "_")
    return os.path.join(base_dir, "tmp", f"{safe_queue_name}_processed_files.log")


def load_processed_files(log_file):
    """
    Loads the list of processed files from the log file.
    """
    if os.path.exists(log_file):
        with open(log_file, "r") as f:
            return set(json.load(f))
    return set()


def save_processed_file(log_file, file_path):
    """
    Adds a processed file to the log.
    """
    processed_files = load_processed_files(log_file)
    processed_files.add(file_path)
    with open(log_file, "w") as f:
        json.dump(list(processed_files), f, indent=4)


def gather_files_recursive(path, allowed_extensions=None):
    """
    Gather files and first-level subfolders.
    Each subfolder is treated as a single unit, without exploring deeper.
    """
    queue = []
    if os.path.isdir(path):
        for entry in os.scandir(path):
            if entry.is_dir():
                queue.append(entry.path)
            elif entry.is_file() and (allowed_extensions is None or entry.name.lower().endswith(tuple(allowed_extensions))):
                queue.append(entry.path)
    elif os.path.isfile(path):
        if allowed_extensions is None or path.lower().endswith(tuple(allowed_extensions)):
            queue.append(path)
    else:
        console.print(f"[red]Invalid path: {path}")
    return queue


def resolve_queue_with_glob_or_split(path, paths, allowed_extensions=None):
    """
    Handle glob patterns and split path resolution.
    Treat subfolders as single units and filter files by allowed_extensions.
    """
    queue = []
    if os.path.exists(os.path.dirname(path)) and len(paths) <= 1:
        escaped_path = path.replace('[', '[[]')
        queue = [
            file for file in glob.glob(escaped_path)
            if os.path.isdir(file) or (os.path.isfile(file) and (allowed_extensions is None or file.lower().endswith(tuple(allowed_extensions))))
        ]
        if queue:
            display_queue(queue)
    elif os.path.exists(os.path.dirname(path)) and len(paths) > 1:
        queue = [
            file for file in paths
            if os.path.isdir(file) or (os.path.isfile(file) and (allowed_extensions is None or file.lower().endswith(tuple(allowed_extensions))))
        ]
        display_queue(queue)
    elif not os.path.exists(os.path.dirname(path)):
        queue = [
            file for file in resolve_split_path(path)  # noqa F8221
            if os.path.isdir(file) or (os.path.isfile(file) and (allowed_extensions is None or file.lower().endswith(tuple(allowed_extensions))))
        ]
        display_queue(queue)
    return queue


def extract_safe_file_locations(log_file):
    """
    Parse the log file to extract file locations under the 'safe' header.

    :param log_file: Path to the log file to parse.
    :return: List of file paths from the 'safe' section.
    """
    safe_section = False
    safe_file_locations = []

    with open(log_file, 'r') as f:
        for line in f:
            line = line.strip()

            # Detect the start and end of 'safe' sections
            if line.lower() == "safe":
                safe_section = True
                continue
            elif line.lower() in {"danger", "risky"}:
                safe_section = False

            # Extract 'File Location' if in a 'safe' section
            if safe_section and line.startswith("File Location:"):
                match = re.search(r"File Location:\s*(.+)", line)
                if match:
                    safe_file_locations.append(match.group(1).strip())

    return safe_file_locations


def merge_meta(meta, saved_meta, path):
    """Merges saved metadata with the current meta, respecting overwrite rules."""
    with open(f"{base_dir}/tmp/{os.path.basename(path)}/meta.json") as f:
        saved_meta = json.load(f)
        overwrite_list = [
            'trackers', 'dupe', 'debug', 'anon', 'category', 'type', 'screens', 'nohash', 'manual_edition', 'imdb', 'tmdb_manual', 'mal', 'manual',
            'hdb', 'ptp', 'blu', 'no_season', 'no_aka', 'no_year', 'no_dub', 'no_tag', 'no_seed', 'client', 'desclink', 'descfile', 'desc', 'draft',
            'modq', 'region', 'freeleech', 'personalrelease', 'unattended', 'manual_season', 'manual_episode', 'torrent_creation', 'qbit_tag', 'qbit_cat',
            'skip_imghost_upload', 'imghost', 'manual_source', 'webdv', 'hardcoded-subs', 'dual_audio', 'manual_type'
        ]
        sanitized_saved_meta = {}
        for key, value in saved_meta.items():
            clean_key = key.strip().strip("'").strip('"')
            if clean_key in overwrite_list:
                if clean_key in meta and meta.get(clean_key) is not None:
                    sanitized_saved_meta[clean_key] = meta[clean_key]
                    if meta['debug']:
                        console.print(f"Overriding {clean_key} with meta value:", meta[clean_key])
                else:
                    sanitized_saved_meta[clean_key] = value
            else:
                sanitized_saved_meta[clean_key] = value
        meta.update(sanitized_saved_meta)
    f.close()
    return sanitized_saved_meta


def display_queue(queue, base_dir, queue_name, save_to_log=True):
    """Displays the queued files in markdown format and optionally saves them to a log file in the tmp directory."""
    md_text = "\n - ".join(queue)
    console.print("\n[bold green]Queuing these files:[/bold green]", end='')
    console.print(Markdown(f"- {md_text.rstrip()}\n\n", style=Style(color='cyan')))
    console.print("\n\n")

    if save_to_log:
        tmp_dir = os.path.join(base_dir, "tmp")
        os.makedirs(tmp_dir, exist_ok=True)
        log_file = os.path.join(tmp_dir, f"{queue_name}_queue.log")

        try:
            with open(log_file, 'w') as f:
                json.dump(queue, f, indent=4)
            console.print(f"[bold green]Queue successfully saved to log file: {log_file}")
        except Exception as e:
            console.print(f"[bold red]Failed to save queue to log file: {e}")


async def process_meta(meta, base_dir):
    """Process the metadata for each queued path."""

    if meta['imghost'] is None:
        meta['imghost'] = config['DEFAULT']['img_host_1']

    if not meta['unattended']:
        ua = config['DEFAULT'].get('auto_mode', False)
        if str(ua).lower() == "true":
            meta['unattended'] = True
            console.print("[yellow]Running in Auto Mode")

    prep = Prep(screens=meta['screens'], img_host=meta['imghost'], config=config)
    meta = await prep.gather_prep(meta=meta, mode='cli')
    if not meta:
        return
    else:
        meta['cutoff'] = int(config['DEFAULT'].get('cutoff_screens', 3))
        if len(meta.get('image_list', [])) < meta.get('cutoff') and meta.get('skip_imghost_upload', False) is False:
            if 'image_list' not in meta:
                meta['image_list'] = []
            return_dict = {}
            new_images, dummy_var = prep.upload_screens(meta, meta['screens'], 1, 0, meta['screens'], [], return_dict=return_dict)

            with open(f"{meta['base_dir']}/tmp/{meta['uuid']}/meta.json", 'w') as f:
                json.dump(meta, f, indent=4)

        elif meta.get('skip_imghost_upload', False) is True and meta.get('image_list', False) is False:
            meta['image_list'] = []

        torrent_path = os.path.abspath(f"{meta['base_dir']}/tmp/{meta['uuid']}/BASE.torrent")
        if not os.path.exists(torrent_path):
            reuse_torrent = None
            if meta.get('rehash', False) is False:
                reuse_torrent = await client.find_existing_torrent(meta)
                if reuse_torrent is not None:
                    prep.create_base_from_existing_torrent(reuse_torrent, meta['base_dir'], meta['uuid'])

            if meta['nohash'] is False and reuse_torrent is None:
                prep.create_torrent(meta, Path(meta['path']), "BASE")
            if meta['nohash']:
                meta['client'] = "none"

        elif os.path.exists(torrent_path) and meta.get('rehash', False) is True and meta['nohash'] is False:
            prep.create_torrent(meta, Path(meta['path']), "BASE")

        if int(meta.get('randomized', 0)) >= 1:
            prep.create_random_torrents(meta['base_dir'], meta['uuid'], meta['randomized'], meta['path'])


async def do_the_thing(base_dir):
    meta = {'base_dir': base_dir}
    paths = []
    for each in sys.argv[1:]:
        if os.path.exists(each):
            paths.append(os.path.abspath(each))
        else:
            break

    meta, help, before_args = parser.parse(tuple(' '.join(sys.argv[1:]).split(' ')), meta)
    if meta.get('cleanup') and os.path.exists(f"{base_dir}/tmp"):
        shutil.rmtree(f"{base_dir}/tmp")
        console.print("[bold green]Successfully emptied tmp directory")

    if not meta.get('path'):
        exit(0)

    path = meta['path']
    path = os.path.abspath(path)
    if path.endswith('"'):
        path = path[:-1]
    queue = []

    log_file = os.path.join(base_dir, "tmp", f"{meta['queue']}_queue.log")
    allowed_extensions = ['.mkv', '.mp4', '.ts']

    if path.endswith('.txt') and meta.get('unit3d'):
        console.print(f"[bold yellow]Detected a text file for queue input: {path}[/bold yellow]")
        if os.path.exists(path):
            safe_file_locations = extract_safe_file_locations(path)
            if safe_file_locations:
                console.print(f"[cyan]Extracted {len(safe_file_locations)} safe file locations from the text file.[/cyan]")
                queue = safe_file_locations
                meta['queue'] = "unit3d"

                # Save the queue to the log file
                try:
                    with open(log_file, 'w') as f:
                        json.dump(queue, f, indent=4)
                    console.print(f"[bold green]Queue log file saved successfully: {log_file}[/bold green]")
                except IOError as e:
                    console.print(f"[bold red]Failed to save the queue log file: {e}[/bold red]")
                    exit(1)
            else:
                console.print("[bold red]No safe file locations found in the text file. Exiting.[/bold red]")
                exit(1)
        else:
            console.print(f"[bold red]Text file not found: {path}. Exiting.[/bold red]")
            exit(1)

    elif path.endswith('.log') and meta['debug']:
        console.print(f"[bold yellow]Processing debugging queue:[/bold yellow] [bold green{path}[/bold green]")
        if os.path.exists(path):
            log_file = path
            with open(path, 'r') as f:
                queue = json.load(f)
                meta['queue'] = "debugging"

        else:
            console.print(f"[bold red]Log file not found: {path}. Exiting.[/bold red]")
            exit(1)

    elif meta.get('queue'):
        meta, help, before_args = parser.parse(tuple(' '.join(sys.argv[1:]).split(' ')), meta)
        if os.path.exists(log_file):
            with open(log_file, 'r') as f:
                existing_queue = json.load(f)
            console.print(f"[bold yellow]Found an existing queue log file:[/bold yellow] [green]{log_file}[/green]")
            console.print(f"[cyan]The queue log contains {len(existing_queue)} items.[/cyan]")
            console.print("[cyan]Do you want to edit, discard, or keep the existing queue?[/cyan]")
            edit_choice = input("Enter 'e' to edit, 'd' to discard, or press Enter to keep it as is: ").strip().lower()

            if edit_choice == 'e':
                edited_content = click.edit(json.dumps(existing_queue, indent=4))
                if edited_content:
                    try:
                        queue = json.loads(edited_content.strip())
                        console.print("[bold green]Successfully updated the queue from the editor.")
                        with open(log_file, 'w') as f:
                            json.dump(queue, f, indent=4)
                    except json.JSONDecodeError as e:
                        console.print(f"[bold red]Failed to parse the edited content: {e}. Using the original queue.")
                        queue = existing_queue
                else:
                    console.print("[bold red]No changes were made. Using the original queue.")
                    queue = existing_queue
            elif edit_choice == 'd':
                console.print("[bold yellow]Discarding the existing queue log. Creating a new queue.")
                queue = []
            else:
                console.print("[bold green]Keeping the existing queue as is.")
                queue = existing_queue
        else:
            if os.path.exists(path):
                queue = gather_files_recursive(path, allowed_extensions=allowed_extensions)
            else:
                queue = resolve_queue_with_glob_or_split(path, paths, allowed_extensions=allowed_extensions)

            console.print(f"[cyan]A new queue log file will be created:[/cyan] [green]{log_file}[/green]")
            console.print(f"[cyan]The new queue will contain {len(queue)} items.[/cyan]")
            console.print("[cyan]Do you want to edit the initial queue before saving?[/cyan]")
            edit_choice = input("Enter 'e' to edit, or press Enter to save as is: ").strip().lower()

            if edit_choice == 'e':
                edited_content = click.edit(json.dumps(queue, indent=4))
                if edited_content:
                    try:
                        queue = json.loads(edited_content.strip())
                        console.print("[bold green]Successfully updated the queue from the editor.")
                    except json.JSONDecodeError as e:
                        console.print(f"[bold red]Failed to parse the edited content: {e}. Using the original queue.")
                else:
                    console.print("[bold red]No changes were made. Using the original queue.")

            # Save the queue to the log file
            with open(log_file, 'w') as f:
                json.dump(queue, f, indent=4)
            console.print(f"[bold green]Queue log file created: {log_file}[/bold green]")

    elif os.path.exists(path):
        meta, help, before_args = parser.parse(tuple(' '.join(sys.argv[1:]).split(' ')), meta)
        queue = [path]

    else:
        # Search glob if dirname exists
        if os.path.exists(os.path.dirname(path)) and len(paths) <= 1:
            escaped_path = path.replace('[', '[[]')
            globs = glob.glob(escaped_path)
            queue = globs
            if len(queue) != 0:
                md_text = "\n - ".join(queue)
                console.print("\n[bold green]Queuing these files:[/bold green]", end='')
                console.print(Markdown(f"- {md_text.rstrip()}\n\n", style=Style(color='cyan')))
                console.print("\n\n")
            else:
                console.print(f"[red]Path: [bold red]{path}[/bold red] does not exist")

        elif os.path.exists(os.path.dirname(path)) and len(paths) != 1:
            queue = paths
            md_text = "\n - ".join(queue)
            console.print("\n[bold green]Queuing these files:[/bold green]", end='')
            console.print(Markdown(f"- {md_text.rstrip()}\n\n", style=Style(color='cyan')))
            console.print("\n\n")
        elif not os.path.exists(os.path.dirname(path)):
            split_path = path.split()
            p1 = split_path[0]
            for i, each in enumerate(split_path):
                try:
                    if os.path.exists(p1) and not os.path.exists(f"{p1} {split_path[i + 1]}"):
                        queue.append(p1)
                        p1 = split_path[i + 1]
                    else:
                        p1 += f" {split_path[i + 1]}"
                except IndexError:
                    if os.path.exists(p1):
                        queue.append(p1)
                    else:
                        console.print(f"[red]Path: [bold red]{p1}[/bold red] does not exist")
            if len(queue) >= 1:
                md_text = "\n - ".join(queue)
                console.print("\n[bold green]Queuing these files:[/bold green]", end='')
                console.print(Markdown(f"- {md_text.rstrip()}\n\n", style=Style(color='cyan')))
                console.print("\n\n")

        else:
            # Add Search Here
            console.print("[red]There was an issue with your input. If you think this was not an issue, please make a report that includes the full command used.")
            exit()

    if not queue:
        console.print(f"[red]No valid files or directories found for path: {path}")
        exit(1)

    if meta.get('queue'):
        queue_name = meta['queue']
        log_file = get_log_file(base_dir, meta['queue'])
        processed_files = load_processed_files(log_file)
        queue = [file for file in queue if file not in processed_files]
        if not queue:
            console.print(f"[bold yellow]All files in the {meta['queue']} queue have already been processed.")
            exit(0)
        if meta['debug']:
            display_queue(queue, base_dir, queue_name, save_to_log=False)

    processed_files_count = 0
    base_meta = {k: v for k, v in meta.items()}
    for path in queue:
        total_files = len(queue)
        try:
            meta = base_meta.copy()
            meta['path'] = path
            meta['uuid'] = None

            if not path:
                raise ValueError("The 'path' variable is not defined or is empty.")

            meta_file = os.path.join(base_dir, "tmp", os.path.basename(path), "meta.json")

            if os.path.exists(meta_file):
                with open(meta_file, "r") as f:
                    saved_meta = json.load(f)
                    meta.update(merge_meta(meta, saved_meta, path))
            else:
                if meta['debug']:
                    console.print(f"[yellow]No metadata file found at {meta_file}")

        except Exception as e:
            console.print(f"[red]Failed to load metadata for path '{path}': {e}")
        if meta['debug']:
            upload_start_time = time.time()
        console.print(f"[green]Gathering info for {os.path.basename(path)}")
        await process_meta(meta, base_dir)
        if 'we_are_uploading' not in meta:
            console.print("we are not uploading.......")
            if meta.get('queue') is not None:
                processed_files_count += 1
                console.print(f"[cyan]Processed {processed_files_count}/{total_files} files.")
                if not meta['debug']:
                    if log_file:
                        save_processed_file(log_file, path)

        else:
            prep = Prep(screens=meta['screens'], img_host=meta['imghost'], config=config)

            ####################################
            #######  Upload to Trackers  #######  # noqa #F266
            ####################################

            common = COMMON(config=config)
            tracker_setup = TRACKER_SETUP(config=config)
            enabled_trackers = tracker_setup.trackers_enabled(meta)

            async def check_mod_q_and_draft(tracker_class, meta, debug, disctype):
                modq, draft = None, None

                tracker_caps = tracker_capabilities.get(tracker_class.tracker, {})

                # Handle BHD specific draft/live logic
                if tracker_class.tracker == 'BHD' and tracker_caps.get('draft_live'):
                    draft_int = await tracker_class.get_live(meta)
                    draft = "Draft" if draft_int == 0 else "Live"

                # Handle mod_q and draft for other trackers
                else:
                    if tracker_caps.get('mod_q'):
                        modq = await tracker_class.get_flag(meta, 'modq')
                        modq = 'Yes' if modq else 'No'
                    if tracker_caps.get('draft'):
                        draft = await tracker_class.get_flag(meta, 'draft')
                        draft = 'Yes' if draft else 'No'

                return modq, draft

            for tracker in enabled_trackers:
                disctype = meta.get('disctype', None)
                tracker = tracker.replace(" ", "").upper().strip()
                if meta['name'].endswith('DUPE?'):
                    meta['name'] = meta['name'].replace(' DUPE?', '')

                if meta['debug']:
                    debug = "(DEBUG)"
                else:
                    debug = ""

                if tracker in api_trackers:
                    tracker_class = tracker_class_map[tracker](config=config)
                    tracker_status = meta.get('tracker_status', {})
                    upload_status = tracker_status.get(tracker, {}).get('upload', False)
                    console.print(f"[red]Tracker: {tracker}, Upload: {'Yes' if upload_status else 'No'}[/red]")

                    if upload_status:
                        modq, draft = await check_mod_q_and_draft(tracker_class, meta, debug, disctype)

                        if modq is not None:
                            console.print(f"(modq: {modq})")
                        if draft is not None:
                            console.print(f"(draft: {draft})")

                        console.print(f"Uploading to {tracker_class.tracker}")
                        if meta['debug']:
                            upload_finish_time = time.time()
                            console.print(f"Upload from Audionut UA processed in {upload_finish_time - upload_start_time:.2f} seconds")
                        await tracker_class.upload(meta, disctype)
                        await asyncio.sleep(0.5)
                        perm = config['DEFAULT'].get('get_permalink', False)
                        if perm:
                            # need a wait so we don't race the api
                            await asyncio.sleep(5)
                            await tracker_class.search_torrent_page(meta, disctype)
                            await asyncio.sleep(0.5)
                        await client.add_to_client(meta, tracker_class.tracker)

                if tracker in other_api_trackers:
                    tracker_class = tracker_class_map[tracker](config=config)
                    tracker_status = meta.get('tracker_status', {})
                    upload_status = tracker_status.get(tracker, {}).get('upload', False)
                    console.print(f"[yellow]Tracker: {tracker}, Upload: {'Yes' if upload_status else 'No'}[/yellow]")

                    if upload_status:
                        console.print(f"Uploading to {tracker_class.tracker}")

                        if tracker != "TL":
                            if tracker == "RTF":
                                await tracker_class.api_test(meta)
                            if tracker == "TL" or upload_status:
                                await tracker_class.upload(meta, disctype)
                                if tracker == 'SN':
                                    await asyncio.sleep(16)
                                await asyncio.sleep(0.5)
                                await client.add_to_client(meta, tracker_class.tracker)

                if tracker in http_trackers:
                    tracker_class = tracker_class_map[tracker](config=config)
                    tracker_status = meta.get('tracker_status', {})
                    upload_status = tracker_status.get(tracker, {}).get('upload', False)
                    console.print(f"[blue]Tracker: {tracker}, Upload: {'Yes' if upload_status else 'No'}[/blue]")

                    if upload_status:
                        console.print(f"Uploading to {tracker}")

                        if await tracker_class.validate_credentials(meta) is True:
                            await tracker_class.upload(meta, disctype)
                            await asyncio.sleep(0.5)
                            await client.add_to_client(meta, tracker_class.tracker)

                if tracker == "MANUAL":
                    if meta['unattended']:
                        do_manual = True
                    else:
                        do_manual = cli_ui.ask_yes_no("Get files for manual upload?", default=True)
                    if do_manual:
                        for manual_tracker in enabled_trackers:
                            if manual_tracker != 'MANUAL':
                                manual_tracker = manual_tracker.replace(" ", "").upper().strip()
                                tracker_class = tracker_class_map[manual_tracker](config=config)
                                if manual_tracker in api_trackers:
                                    await common.unit3d_edit_desc(meta, tracker_class.tracker, tracker_class.signature)
                                else:
                                    await tracker_class.edit_desc(meta)
                        url = await prep.package(meta)
                        if url is False:
                            console.print(f"[yellow]Unable to upload prep files, they can be found at `tmp/{meta['uuid']}")
                        else:
                            console.print(f"[green]{meta['name']}")
                            console.print(f"[green]Files can be found at: [yellow]{url}[/yellow]")

                if tracker == "THR":
                    tracker_status = meta.get('tracker_status', {})
                    upload_status = tracker_status.get(tracker, {}).get('upload', False)
                    print(f"Tracker: {tracker}, Upload: {'Yes' if upload_status else 'No'}")

                    if upload_status:
                        thr = THR(config=config)
                        try:
                            with requests.Session() as session:
                                console.print("[yellow]Logging in to THR")
                                session = thr.login(session)
                                await thr.upload(session, meta, disctype)
                                await asyncio.sleep(0.5)
                                await client.add_to_client(meta, "THR")
                        except Exception:
                            console.print(traceback.format_exc())

                if tracker == "PTP":
                    tracker_status = meta.get('tracker_status', {})
                    upload_status = tracker_status.get(tracker, {}).get('upload', False)
                    print(f"Tracker: {tracker}, Upload: {'Yes' if upload_status else 'No'}")

                    if upload_status:
                        ptp = PTP(config=config)
                        groupID = meta['ptp_groupID']
                        ptpUrl, ptpData = await ptp.fill_upload_form(groupID, meta)
                        await ptp.upload(meta, ptpUrl, ptpData, disctype)
                        await asyncio.sleep(5)
                        await client.add_to_client(meta, "PTP")

            if meta.get('queue') is not None:
                processed_files_count += 1
                console.print(f"[cyan]Processed {processed_files_count}/{total_files} files.")
                if not meta['debug']:
                    if log_file:
                        save_processed_file(log_file, path)


if __name__ == '__main__':
    pyver = platform.python_version_tuple()
    if int(pyver[0]) != 3 or int(pyver[1]) < 12:
        console.print("[bold red]Python version is too low. Please use Python 3.12 or higher.")
        sys.exit(1)

    try:
        asyncio.run(do_the_thing(base_dir))  # Pass the correct base_dir value here
    except (KeyboardInterrupt):
        console.print("[bold red]Program interrupted. Exiting.")
