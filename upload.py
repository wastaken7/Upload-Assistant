#!/usr/bin/env python3

import requests
from src.args import Args
from src.clients import Clients
from src.trackers.COMMON import COMMON
from src.trackers.HUNO import HUNO
from src.trackers.BLU import BLU
from src.trackers.BHD import BHD
from src.trackers.AITHER import AITHER
from src.trackers.STC import STC
from src.trackers.R4E import R4E
from src.trackers.THR import THR
from src.trackers.STT import STT
from src.trackers.HP import HP
from src.trackers.PTP import PTP
from src.trackers.SN import SN
from src.trackers.ACM import ACM
from src.trackers.HDB import HDB
from src.trackers.LCD import LCD
from src.trackers.TTG import TTG
from src.trackers.LST import LST
from src.trackers.FL import FL
from src.trackers.LT import LT
from src.trackers.NBL import NBL
from src.trackers.ANT import ANT
from src.trackers.PTER import PTER
from src.trackers.MTV import MTV
from src.trackers.JPTV import JPTV
from src.trackers.TL import TL
from src.trackers.HDT import HDT
from src.trackers.RF import RF
from src.trackers.OE import OE
from src.trackers.BHDTV import BHDTV
from src.trackers.RTF import RTF
from src.trackers.OTW import OTW
from src.trackers.FNP import FNP
from src.trackers.CBR import CBR
from src.trackers.UTP import UTP
from src.trackers.AL import AL
from src.trackers.SHRI import SHRI
from src.trackers.TIK import TIK
from src.trackers.TVC import TVC
from src.trackers.PSS import PSS
from src.trackers.ULCX import ULCX
from src.trackers.SPD import SPD
from src.trackers.YOINK import YOINK
from src.trackers.PTT import PTT
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
    with open(f"{meta['base_dir']}/tmp/{meta['uuid']}/meta.json", 'w') as f:
        json.dump(meta, f, indent=4)
    meta['name_notag'], meta['name'], meta['clean_name'], meta['potential_missing'] = await prep.get_name(meta)
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

        console.print(f"[green]Gathering info for {os.path.basename(path)}")
        await process_meta(meta, base_dir)
        prep = Prep(screens=meta['screens'], img_host=meta['imghost'], config=config)
        if meta.get('trackers', None) is not None:
            trackers = meta['trackers']
        else:
            trackers = config['TRACKERS']['default_trackers']
        if "," in trackers:
            trackers = trackers.split(',')
        confirm = get_confirmation(meta)
        while confirm is False:
            editargs = cli_ui.ask_string("Input args that need correction e.g. (--tag NTb --category tv --tmdb 12345)")
            editargs = (meta['path'],) + tuple(editargs.split())
            if meta.get('debug', False):
                editargs += ("--debug",)
            meta, help, before_args = parser.parse(editargs, meta)
            meta['edit'] = True
            meta = await prep.gather_prep(meta=meta, mode='cli')
            with open(f"{meta['base_dir']}/tmp/{meta['uuid']}/meta.json", 'w') as f:
                json.dump(meta, f, indent=4)
            meta['name_notag'], meta['name'], meta['clean_name'], meta['potential_missing'] = await prep.get_name(meta)
            confirm = get_confirmation(meta)

        if isinstance(trackers, str):
            trackers = trackers.split(',')
        trackers = [s.strip().upper() for s in trackers]
        if meta.get('manual', False):
            trackers.insert(0, "MANUAL")
        ####################################
        #######  Upload to Trackers  #######  # noqa #F266
        ####################################
        common = COMMON(config=config)
        api_trackers = [
            'ACM', 'AITHER', 'AL', 'BHD', 'BLU', 'CBR', 'FNP', 'HUNO', 'JPTV', 'LCD', 'LST', 'LT',
            'OE', 'OTW', 'PSS', 'RF', 'R4E', 'SHRI', 'STC', 'STT', 'TIK', 'ULCX', 'UTP', 'YOINK', 'PTT'
        ]
        other_api_trackers = [
            'ANT', 'BHDTV', 'NBL', 'RTF', 'SN', 'SPD', 'TL', 'TVC'
        ]
        http_trackers = [
            'FL', 'HDB', 'HDT', 'MTV', 'PTER', 'TTG'
        ]
        tracker_class_map = {
            'ACM': ACM, 'AITHER': AITHER, 'AL': AL, 'ANT': ANT, 'BHD': BHD, 'BHDTV': BHDTV, 'BLU': BLU, 'CBR': CBR,
            'FNP': FNP, 'FL': FL, 'HDB': HDB, 'HDT': HDT, 'HP': HP, 'HUNO': HUNO, 'JPTV': JPTV, 'LCD': LCD,
            'LST': LST, 'LT': LT, 'MTV': MTV, 'NBL': NBL, 'OE': OE, 'OTW': OTW, 'PSS': PSS, 'PTP': PTP, 'PTER': PTER,
            'R4E': R4E, 'RF': RF, 'RTF': RTF, 'SHRI': SHRI, 'SN': SN, 'SPD': SPD, 'STC': STC, 'STT': STT, 'THR': THR,
            'TIK': TIK, 'TL': TL, 'TVC': TVC, 'TTG': TTG, 'ULCX': ULCX, 'UTP': UTP, 'YOINK': YOINK, 'PTT': PTT,
        }

        tracker_capabilities = {
            'AITHER': {'mod_q': True, 'draft': False},
            'BHD': {'draft_live': True},
            'BLU': {'mod_q': True, 'draft': False},
            'LST': {'mod_q': True, 'draft': True}
        }

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

        for tracker in trackers:
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

                if meta['unattended']:
                    upload_to_tracker = True
                else:
                    try:
                        upload_to_tracker = cli_ui.ask_yes_no(
                            f"Upload to {tracker_class.tracker}? {debug}",
                            default=meta['unattended']
                        )
                    except (KeyboardInterrupt, EOFError):
                        sys.exit(1)  # Exit immediately

                if upload_to_tracker:
                    # Get mod_q, draft, or draft/live depending on the tracker
                    modq, draft = await check_mod_q_and_draft(tracker_class, meta, debug, disctype)

                    # Print mod_q and draft info if relevant
                    if modq is not None:
                        console.print(f"(modq: {modq})")
                    if draft is not None:
                        console.print(f"(draft: {draft})")

                    console.print(f"Uploading to {tracker_class.tracker}")

                    # Check if the group is banned for the tracker
                    if check_banned_group(tracker_class.tracker, tracker_class.banned_groups, meta):
                        continue

                    dupes = await tracker_class.search_existing(meta, disctype)
                    if 'skipping' not in meta or meta['skipping'] is None:
                        dupes = await common.filter_dupes(dupes, meta)
                        meta = dupe_check(dupes, meta)

                        # Proceed with upload if the meta is set to upload
                        if meta.get('upload', False):
                            await tracker_class.upload(meta, disctype)
                            perm = config['DEFAULT'].get('get_permalink', False)
                            if perm:
                                # need a wait so we don't race the api
                                await asyncio.sleep(5)
                                await tracker_class.search_torrent_page(meta, disctype)
                                await asyncio.sleep(0.5)
                            await client.add_to_client(meta, tracker_class.tracker)
                    meta['skipping'] = None

            if tracker in other_api_trackers:
                tracker_class = tracker_class_map[tracker](config=config)

                if meta['unattended']:
                    upload_to_tracker = True
                else:
                    try:
                        upload_to_tracker = cli_ui.ask_yes_no(
                            f"Upload to {tracker_class.tracker}? {debug}",
                            default=meta['unattended']
                        )
                    except (KeyboardInterrupt, EOFError):
                        sys.exit(1)  # Exit immediately

                if upload_to_tracker:
                    # Get mod_q, draft, or draft/live depending on the tracker
                    modq, draft = await check_mod_q_and_draft(tracker_class, meta, debug, disctype)

                    # Print mod_q and draft info if relevant
                    if modq is not None:
                        console.print(f"(modq: {modq})")
                    if draft is not None:
                        console.print(f"(draft: {draft})")

                    console.print(f"Uploading to {tracker_class.tracker}")

                    # Check if the group is banned for the tracker
                    if check_banned_group(tracker_class.tracker, tracker_class.banned_groups, meta):
                        continue

                    # Perform the existing checks for dupes except TL
                    if tracker != "TL":
                        if tracker == "RTF":
                            await tracker_class.api_test(meta)

                        dupes = await tracker_class.search_existing(meta, disctype)
                        if 'skipping' not in meta or meta['skipping'] is None:
                            dupes = await common.filter_dupes(dupes, meta)
                            meta = dupe_check(dupes, meta)

                    if 'skipping' not in meta or meta['skipping'] is None:
                        # Proceed with upload if the meta is set to upload
                        if tracker == "TL" or meta.get('upload', False):
                            await tracker_class.upload(meta, disctype)
                            if tracker == 'SN':
                                await asyncio.sleep(16)
                            await client.add_to_client(meta, tracker_class.tracker)
                    meta['skipping'] = None

            if tracker in http_trackers:
                tracker_class = tracker_class_map[tracker](config=config)

                if meta['unattended']:
                    upload_to_tracker = True
                else:
                    try:
                        upload_to_tracker = cli_ui.ask_yes_no(
                            f"Upload to {tracker_class.tracker}? {debug}",
                            default=meta['unattended']
                        )
                    except (KeyboardInterrupt, EOFError):
                        sys.exit(1)  # Exit immediately

                if upload_to_tracker:
                    console.print(f"Uploading to {tracker}")
                    if check_banned_group(tracker_class.tracker, tracker_class.banned_groups, meta):
                        continue
                    if await tracker_class.validate_credentials(meta) is True:
                        dupes = await tracker_class.search_existing(meta, disctype)
                        dupes = await common.filter_dupes(dupes, meta)
                        meta = dupe_check(dupes, meta)
                        if meta['upload'] is True:
                            await tracker_class.upload(meta, disctype)
                            await client.add_to_client(meta, tracker_class.tracker)

            if tracker == "MANUAL":
                if meta['unattended']:
                    do_manual = True
                else:
                    do_manual = cli_ui.ask_yes_no("Get files for manual upload?", default=True)
                if do_manual:
                    for manual_tracker in trackers:
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
                if meta['unattended']:
                    upload_to_thr = True
                else:
                    try:
                        upload_to_ptp = cli_ui.ask_yes_no(
                            f"Upload to THR? {debug}",
                            default=meta['unattended']
                        )
                    except (KeyboardInterrupt, EOFError):
                        sys.exit(1)  # Exit immediately
                if upload_to_thr:
                    console.print("Uploading to THR")
                    # nable to get IMDB id/Youtube Link
                    if meta.get('imdb_id', '0') == '0':
                        imdb_id = cli_ui.ask_string("Unable to find IMDB id, please enter e.g.(tt1234567)")
                        meta['imdb_id'] = imdb_id.replace('tt', '').zfill(7)
                    if meta.get('youtube', None) is None:
                        youtube = cli_ui.ask_string("Unable to find youtube trailer, please link one e.g.(https://www.youtube.com/watch?v=dQw4w9WgXcQ)")
                        meta['youtube'] = youtube
                    thr = THR(config=config)
                    try:
                        with requests.Session() as session:
                            console.print("[yellow]Logging in to THR")
                            session = thr.login(session)
                            console.print("[yellow]Searching for Dupes")
                            dupes = thr.search_existing(session, disctype, meta.get('imdb_id'))
                            dupes = await common.filter_dupes(dupes, meta)
                            meta = dupe_check(dupes, meta)
                            if meta['upload'] is True:
                                await thr.upload(session, meta, disctype)
                                await client.add_to_client(meta, "THR")
                    except Exception:
                        console.print(traceback.format_exc())

            if tracker == "PTP":
                if meta['unattended']:
                    upload_to_ptp = True
                else:
                    try:
                        upload_to_ptp = cli_ui.ask_yes_no(
                            f"Upload to {tracker}? {debug}",
                            default=meta['unattended']
                        )
                    except (KeyboardInterrupt, EOFError):
                        sys.exit(1)  # Exit immediately

                if upload_to_ptp:  # Ensure the variable is defined before this check
                    console.print(f"Uploading to {tracker}")
                    if meta.get('imdb_id', '0') == '0':
                        imdb_id = cli_ui.ask_string("Unable to find IMDB id, please enter e.g.(tt1234567)")
                        meta['imdb_id'] = imdb_id.replace('tt', '').zfill(7)
                    ptp = PTP(config=config)
                    if check_banned_group("PTP", ptp.banned_groups, meta):
                        continue
                    try:
                        console.print("[yellow]Searching for Group ID")
                        groupID = await ptp.get_group_by_imdb(meta['imdb_id'])
                        if groupID is None:
                            console.print("[yellow]No Existing Group found")
                            if meta.get('youtube', None) is None or "youtube" not in str(meta.get('youtube', '')):
                                youtube = cli_ui.ask_string("Unable to find youtube trailer, please link one e.g.(https://www.youtube.com/watch?v=dQw4w9WgXcQ)", default="")
                                meta['youtube'] = youtube
                            meta['upload'] = True
                        else:
                            console.print("[yellow]Searching for Existing Releases")
                            dupes = await ptp.search_existing(groupID, meta, disctype)
                            dupes = await common.filter_dupes(dupes, meta)
                            meta = dupe_check(dupes, meta)
                        if meta.get('imdb_info', {}) == {}:
                            meta['imdb_info'] = await prep.get_imdb_info(meta['imdb_id'], meta)
                        if meta['upload'] is True:
                            ptpUrl, ptpData = await ptp.fill_upload_form(groupID, meta)
                            await ptp.upload(meta, ptpUrl, ptpData, disctype)
                            await asyncio.sleep(5)
                            await client.add_to_client(meta, "PTP")
                    except Exception:
                        console.print(traceback.format_exc())

        if meta.get('queue') is not None:
            processed_files_count += 1
            console.print(f"[cyan]Processed {processed_files_count}/{total_files} files.")
            if not meta['debug']:
                if log_file:
                    save_processed_file(log_file, path)


def get_confirmation(meta):
    if meta['debug'] is True:
        console.print("[bold red]DEBUG: True")
    console.print(f"Prep material saved to {meta['base_dir']}/tmp/{meta['uuid']}")
    console.print()
    console.print("[bold yellow]Database Info[/bold yellow]")
    console.print(f"[bold]Title:[/bold] {meta['title']} ({meta['year']})")
    console.print()
    console.print(f"[bold]Overview:[/bold] {meta['overview']}")
    console.print()
    console.print(f"[bold]Category:[/bold] {meta['category']}")
    if int(meta.get('tmdb', 0)) != 0:
        console.print(f"[bold]TMDB:[/bold] https://www.themoviedb.org/{meta['category'].lower()}/{meta['tmdb']}")
    if int(meta.get('imdb_id', '0')) != 0:
        console.print(f"[bold]IMDB:[/bold] https://www.imdb.com/title/tt{meta['imdb_id']}")
    if int(meta.get('tvdb_id', '0')) != 0:
        console.print(f"[bold]TVDB:[/bold] https://www.thetvdb.com/?id={meta['tvdb_id']}&tab=series")
    if int(meta.get('tvmaze_id', '0')) != 0:
        console.print(f"[bold]TVMaze:[/bold] https://www.tvmaze.com/shows/{meta['tvmaze_id']}")
    if int(meta.get('mal_id', 0)) != 0:
        console.print(f"[bold]MAL:[/bold] https://myanimelist.net/anime/{meta['mal_id']}")
    console.print()
    if int(meta.get('freeleech', '0')) != 0:
        console.print(f"[bold]Freeleech:[/bold] {meta['freeleech']}")
    if meta['tag'] == "":
        tag = ""
    else:
        tag = f" / {meta['tag'][1:]}"
    if meta['is_disc'] == "DVD":
        res = meta['source']
    else:
        res = meta['resolution']

    console.print(f"{res} / {meta['type']}{tag}")
    if meta.get('personalrelease', False) is True:
        console.print("[bold green]Personal Release![/bold green]")
    console.print()
    if meta.get('unattended', False) is False:
        get_missing(meta)
        ring_the_bell = "\a" if config['DEFAULT'].get("sfx_on_prompt", True) is True else ""  # \a rings the bell
        if ring_the_bell:
            console.print(ring_the_bell)

        # Handle the 'keep_folder' logic based on 'is disc' and 'isdir'
        if meta.get('is disc', False) is True:
            meta['keep_folder'] = False  # Ensure 'keep_folder' is False if 'is disc' is True

        if meta.get('keep_folder'):
            if meta['isdir']:
                console.print("[bold yellow]Uploading with --keep-folder[/bold yellow]")
                kf_confirm = input("You specified --keep-folder. Uploading in folders might not be allowed. Are you sure you want to proceed? [y/N]: ").strip().lower()
                if kf_confirm != 'y':
                    console.print("[bold red]Aborting...[/bold red]")
                    exit()

        console.print("[bold yellow]Is this correct?[/bold yellow]")
        console.print(f"[bold]Name:[/bold] {meta['name']}")
        confirm_input = input("Correct? [y/N]: ").strip().lower()
        confirm = confirm_input == 'y'

    else:
        console.print(f"[bold]Name:[/bold] {meta['name']}")
        confirm = True

    return confirm


def dupe_check(dupes, meta):
    if not dupes:
        console.print("[green]No dupes found")
        meta['upload'] = True
        return meta
    else:
        console.print()
        dupe_text = "\n".join(dupes)
        console.print()
        cli_ui.info_section(cli_ui.bold, "Check if these are actually dupes!")
        cli_ui.info(dupe_text)
        if not meta['unattended'] or (meta['unattended'] and meta.get('unattended-confirm', False)):
            if meta.get('dupe', False) is False:
                upload = cli_ui.ask_yes_no("Upload Anyways?", default=False)
            else:
                upload = True
        else:
            if meta.get('dupe', False) is False:
                console.print("[red]Found potential dupes. Aborting. If this is not a dupe, or you would like to upload anyways, pass --skip-dupe-check")
                upload = False
            else:
                console.print("[yellow]Found potential dupes. --skip-dupe-check was passed. Uploading anyways")
                upload = True
        console.print()
        if upload is False:
            meta['upload'] = False
        else:
            meta['upload'] = True
            for each in dupes:
                if each == meta['name']:
                    meta['name'] = f"{meta['name']} DUPE?"

        return meta


# Return True if banned group
def check_banned_group(tracker, banned_group_list, meta):
    if meta['tag'] == "":
        return False
    else:
        q = False
        for tag in banned_group_list:
            if isinstance(tag, list):
                if meta['tag'][1:].lower() == tag[0].lower():
                    console.print(f"[bold yellow]{meta['tag'][1:]}[/bold yellow][bold red] was found on [bold yellow]{tracker}'s[/bold yellow] list of banned groups.")
                    console.print(f"[bold red]NOTE: [bold yellow]{tag[1]}")
                    q = True
            else:
                if meta['tag'][1:].lower() == tag.lower():
                    console.print(f"[bold yellow]{meta['tag'][1:]}[/bold yellow][bold red] was found on [bold yellow]{tracker}'s[/bold yellow] list of banned groups.")
                    q = True
        if q:
            if not meta['unattended'] or (meta['unattended'] and meta.get('unattended-confirm', False)):
                if not cli_ui.ask_yes_no(cli_ui.red, "Upload Anyways?", default=False):
                    return True
            else:
                return True
    return False


def get_missing(meta):
    info_notes = {
        'edition': 'Special Edition/Release',
        'description': "Please include Remux/Encode Notes if possible (either here or edit your upload)",
        'service': "WEB Service e.g.(AMZN, NF)",
        'region': "Disc Region",
        'imdb': 'IMDb ID (tt1234567)',
        'distributor': "Disc Distributor e.g.(BFI, Criterion, etc)"
    }
    missing = []
    if meta.get('imdb_id', '0') == '0':
        meta['imdb_id'] = '0'
        meta['potential_missing'].append('imdb_id')
    if len(meta['potential_missing']) > 0:
        for each in meta['potential_missing']:
            if str(meta.get(each, '')).replace(' ', '') in ["", "None", "0"]:
                if each == "imdb_id":
                    each = 'imdb'
                missing.append(f"--{each} | {info_notes.get(each)}")
    if missing != []:
        cli_ui.info_section(cli_ui.yellow, "Potentially missing information:")
        for each in missing:
            if each.split('|')[0].replace('--', '').strip() in ["imdb"]:
                cli_ui.info(cli_ui.red, each)
            else:
                cli_ui.info(each)

    console.print()
    return


if __name__ == '__main__':
    pyver = platform.python_version_tuple()
    if int(pyver[0]) != 3 or int(pyver[1]) < 12:
        console.print("[bold red]Python version is too low. Please use Python 3.12 or higher.")
        sys.exit(1)

    try:
        asyncio.run(do_the_thing(base_dir))  # Pass the correct base_dir value here
    except (KeyboardInterrupt):
        console.print("[bold red]Program interrupted. Exiting.")
