import aiohttp
import requests
from data.config import config
from src.console import console
from src.trackermeta import update_metadata_from_tracker, check_images_concurrently
from src.btnid import get_btn_torrents, get_bhd_torrents
from src.clients import Clients
from src.trackersetup import tracker_class_map

client = Clients(config=config)


async def get_tracker_data(video, meta, search_term=None, search_file_folder=None, cat=None):
    only_id = config['DEFAULT'].get('only_id', False) if not meta.get('only_id') else False
    found_match = False

    if search_term:
        # Check if a specific tracker is already set in meta
        tracker_keys = {
            'ptp': 'PTP',
            'btn': 'BTN',
            'bhd': 'BHD',
            'huno': 'HUNO',
            'hdb': 'HDB',
            'blu': 'BLU',
            'aither': 'AITHER',
            'lst': 'LST',
            'oe': 'OE',
            'ulcx': 'ULCX',
        }

        specific_tracker = [tracker_keys[key] for key in tracker_keys if meta.get(key) is not None]

        async def process_tracker(tracker_name, meta, only_id):
            nonlocal found_match
            if tracker_class_map is None:
                print(f"Tracker class for {tracker_name} not found.")
                return meta

            tracker_instance = tracker_class_map[tracker_name](config=config)
            try:
                updated_meta, match = await update_metadata_from_tracker(
                    tracker_name, tracker_instance, meta, search_term, search_file_folder, only_id
                )
                if match:
                    found_match = True
                    console.print(f"[green]Match found on tracker: {tracker_name}[/green]")
                return updated_meta
            except aiohttp.ClientSSLError:
                print(f"{tracker_name} tracker request failed due to SSL error.")
            except requests.exceptions.ConnectionError as conn_err:
                print(f"{tracker_name} tracker request failed due to connection error: {conn_err}")
            return meta

        # If a specific tracker is found, process only that tracker
        for tracker in specific_tracker:
            if tracker == "BTN":
                btn_id = meta.get('btn')
                btn_api = config['DEFAULT'].get('btn_api')
                await get_btn_torrents(btn_api, btn_id, meta)
                if meta.get('imdb_id') != 0:
                    found_match = True
                    break
            elif tracker == "BHD":
                bhd_api = config['DEFAULT'].get('bhd_api')
                bhd_rss_key = config['DEFAULT'].get('bhd_rss_key')
                if meta.get('bhd'):
                    if len(str(meta['bhd'])) > 8:
                        if not meta.get('infohash'):
                            meta['infohash'] = meta['bhd']
                        await get_bhd_torrents(bhd_api, bhd_rss_key, meta, only_id, info_hash=meta['infohash'])
                        if meta.get('imdb_id') != 0 or meta.get('tmdb_id') != 0:
                            found_match = True
                            break
                        if meta.get('image_list'):
                            valid_images = await check_images_concurrently(meta.get('image_list'), meta)
                            if valid_images:
                                meta['image_list'] = valid_images
                    else:
                        await get_bhd_torrents(bhd_api, bhd_rss_key, meta, only_id, torrent_id=meta['bhd'])
                        if meta.get('imdb_id') != 0 or meta.get('tmdb_id') != 0:
                            found_match = True
                            break
                        if meta.get('image_list'):
                            valid_images = await check_images_concurrently(meta.get('image_list'), meta)
                            if valid_images:
                                meta['image_list'] = valid_images
                else:
                    console.print("[yellow]No BHD ID found, skipping BHD tracker update.[/yellow]")
            else:
                meta = await process_tracker(tracker, meta, only_id)
                if found_match:
                    break
        else:
            # Process all trackers with API = true if no specific tracker is set in meta
            tracker_order = ["PTP", "BHD", "BLU", "AITHER", "LST", "OE", "HDB", "HUNO", "ULCX"]

            if cat == "TV" or meta.get('category') == "TV":
                if meta['debug']:
                    console.print("[yellow]Detected TV content, skipping PTP tracker check")
                tracker_order = [tracker for tracker in tracker_order if tracker != "PTP"]

            for tracker_name in tracker_order:
                if not found_match:  # Stop checking once a match is found
                    tracker_config = config['TRACKERS'].get(tracker_name, {})
                    if str(tracker_config.get('useAPI', 'false')).lower() == "true":
                        meta = await process_tracker(tracker_name, meta, only_id)

        if not found_match:
            console.print("[yellow]No matches found on any trackers.[/yellow]")

    else:
        console.print("[yellow]Warning: No valid search term available, skipping tracker updates.[/yellow]")
