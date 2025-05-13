# -*- coding: utf-8 -*-
from src.console import console
from src.exceptions import *  # noqa: F403
from src.clients import Clients
from data.config import config
from src.tvmaze import search_tvmaze
from src.imdb import get_imdb_info_api, search_imdb
from src.tmdb import tmdb_other_meta, get_tmdb_imdb_from_mediainfo, get_tmdb_from_imdb, get_tmdb_id
from src.region import get_region, get_distributor, get_service
from src.exportmi import exportInfo, mi_resolution
from src.getseasonep import get_season_episode
from src.get_tracker_data import get_tracker_data, ping_unit3d
from src.bluray_com import get_bluray_releases
from src.metadata_searching import all_ids, imdb_tvdb, imdb_tmdb, get_tv_data, imdb_tmdb_tvdb
from src.apply_overrides import get_source_override
from src.is_scene import is_scene
from src.audio import get_audio_languages, get_audio_v2
from src.edition import get_edition
from src.video import get_video_codec, get_video_encode, get_uhd, get_hdr
from src.tags import get_tag, tag_override
from src.get_disc import get_disc

try:
    import traceback
    import os
    import re
    from guessit import guessit
    import ntpath
    from pathlib import Path
    import json
    import glob
    from pymediainfo import MediaInfo
    import tmdbsimple as tmdb
    import time
    import itertools
    from difflib import SequenceMatcher
except ModuleNotFoundError:
    console.print(traceback.print_exc())
    console.print('[bold red]Missing Module Found. Please reinstall required dependancies.')
    console.print('[yellow]pip3 install --user -U -r requirements.txt')
    exit()
except KeyboardInterrupt:
    exit()


class Prep():
    """
    Prepare for upload:
        Mediainfo/BDInfo
        Screenshots
        Database Identifiers (TMDB/IMDB/MAL/etc)
        Create Name
    """
    def __init__(self, screens, img_host, config):
        self.screens = screens
        self.config = config
        self.img_host = img_host.lower()
        tmdb.API_KEY = config['DEFAULT']['tmdb_api']

    async def gather_prep(self, meta, mode):
        # set some details we'll need
        meta['cutoff'] = int(self.config['DEFAULT'].get('cutoff_screens', 1))
        tvdb_api = str(self.config['DEFAULT'].get('tvdb_api', None))
        tvdb_token = str(self.config['DEFAULT'].get('tvdb_token', None))
        meta['mode'] = mode
        meta['isdir'] = os.path.isdir(meta['path'])
        base_dir = meta['base_dir']
        meta['saved_description'] = False
        client = Clients(config=config)
        meta['skip_auto_torrent'] = config['DEFAULT'].get('skip_auto_torrent', False)
        hash_ids = ['infohash', 'torrent_hash', 'skip_auto_torrent']
        tracker_ids = ['ptp', 'bhd', 'btn', 'blu', 'aither', 'lst', 'oe', 'hdb', 'huno']

        # make sure these are set in meta
        meta['we_checked_tvdb'] = False
        meta['we_checked_tmdb'] = False
        meta['we_asked_tvmaze'] = False

        folder_id = os.path.basename(meta['path'])
        if meta.get('uuid', None) is None:
            meta['uuid'] = folder_id
        if not os.path.exists(f"{base_dir}/tmp/{meta['uuid']}"):
            Path(f"{base_dir}/tmp/{meta['uuid']}").mkdir(parents=True, exist_ok=True)

        if meta['debug']:
            console.print(f"[cyan]ID: {meta['uuid']}")

        meta['is_disc'], videoloc, bdinfo, meta['discs'] = await get_disc(meta)

        # Debugging information
        # console.print(f"Debug: meta['filelist'] before population: {meta.get('filelist', 'Not Set')}")

        if meta['is_disc'] == "BDMV":
            video, meta['scene'], meta['imdb_id'] = await is_scene(meta['path'], meta, meta.get('imdb_id', 0))
            meta['filelist'] = []  # No filelist for discs, use path
            search_term = os.path.basename(meta['path'])
            search_file_folder = 'folder'
            try:
                guess_name = bdinfo['title'].replace('-', ' ')
                filename = guessit(re.sub(r"[^0-9a-zA-Z\[\\]]+", " ", guess_name), {"excludes": ["country", "language"]})['title']
                untouched_filename = bdinfo['title']
                try:
                    meta['search_year'] = guessit(bdinfo['title'])['year']
                except Exception:
                    meta['search_year'] = ""
            except Exception:
                guess_name = bdinfo['label'].replace('-', ' ')
                filename = guessit(re.sub(r"[^0-9a-zA-Z\[\\]]+", " ", guess_name), {"excludes": ["country", "language"]})['title']
                untouched_filename = bdinfo['label']
                try:
                    meta['search_year'] = guessit(bdinfo['label'])['year']
                except Exception:
                    meta['search_year'] = ""

            if meta.get('resolution', None) is None:
                meta['resolution'] = await mi_resolution(bdinfo['video'][0]['res'], guessit(video), width="OTHER", scan="p", height="OTHER", actual_height=0)
            meta['sd'] = await self.is_sd(meta['resolution'])

            mi = None

        elif meta['is_disc'] == "DVD":
            video, meta['scene'], meta['imdb_id'] = await is_scene(meta['path'], meta, meta.get('imdb_id', 0))
            meta['filelist'] = []
            search_term = os.path.basename(meta['path'])
            search_file_folder = 'folder'
            guess_name = meta['discs'][0]['path'].replace('-', ' ')
            filename = guessit(guess_name, {"excludes": ["country", "language"]})['title']
            untouched_filename = os.path.basename(os.path.dirname(meta['discs'][0]['path']))
            try:
                meta['search_year'] = guessit(meta['discs'][0]['path'])['year']
            except Exception:
                meta['search_year'] = ""
            if not meta.get('edit', False):
                mi = await exportInfo(f"{meta['discs'][0]['path']}/VTS_{meta['discs'][0]['main_set'][0][:2]}_1.VOB", False, meta['uuid'], meta['base_dir'], export_text=False)
                meta['mediainfo'] = mi
            else:
                mi = meta['mediainfo']

            meta['dvd_size'] = await self.get_dvd_size(meta['discs'], meta.get('manual_dvds'))
            meta['resolution'] = await self.get_resolution(guessit(video), meta['uuid'], base_dir)
            meta['sd'] = await self.is_sd(meta['resolution'])

        elif meta['is_disc'] == "HDDVD":
            video, meta['scene'], meta['imdb_id'] = await is_scene(meta['path'], meta, meta.get('imdb_id', 0))
            meta['filelist'] = []
            search_term = os.path.basename(meta['path'])
            search_file_folder = 'folder'
            guess_name = meta['discs'][0]['path'].replace('-', '')
            filename = guessit(guess_name, {"excludes": ["country", "language"]})['title']
            untouched_filename = os.path.basename(meta['discs'][0]['path'])
            videopath = meta['discs'][0]['largest_evo']
            try:
                meta['search_year'] = guessit(meta['discs'][0]['path'])['year']
            except Exception:
                meta['search_year'] = ""
            if not meta.get('edit', False):
                mi = await exportInfo(meta['discs'][0]['largest_evo'], False, meta['uuid'], meta['base_dir'], export_text=False)
                meta['mediainfo'] = mi
            else:
                mi = meta['mediainfo']
            meta['resolution'] = await self.get_resolution(guessit(video), meta['uuid'], base_dir)
            meta['sd'] = await self.is_sd(meta['resolution'])

        else:
            # handle some specific cases that trouble guessit and then id grabbing
            def extract_title_and_year(filename):
                basename = os.path.basename(filename)
                basename = os.path.splitext(basename)[0]

                secondary_title = None
                year = None

                # Check for AKA patterns first
                aka_patterns = [' AKA ', '.aka.', ' aka ', '.AKA.']
                for pattern in aka_patterns:
                    if pattern in basename:
                        aka_parts = basename.split(pattern, 1)
                        if len(aka_parts) > 1:
                            primary_title = aka_parts[0].strip()
                            secondary_part = aka_parts[1].strip()

                            # Look for a year in the primary title
                            year_match_primary = re.search(r'\b(19|20)\d{2}\b', primary_title)
                            if year_match_primary:
                                year = year_match_primary.group(0)

                            # Process secondary title
                            secondary_match = re.match(r"^(\d+)", secondary_part)
                            if secondary_match:
                                secondary_title = secondary_match.group(1)
                            else:
                                # Catch everything after AKA until it hits a year or release info
                                year_or_release_match = re.search(r'\b(19|20)\d{2}\b|\bBluRay\b|\bREMUX\b|\b\d+p\b|\bDTS-HD\b|\bAVC\b', secondary_part)
                                if year_or_release_match:
                                    # Check if we found a year in the secondary part
                                    if re.match(r'\b(19|20)\d{2}\b', year_or_release_match.group(0)):
                                        # If no year was found in primary title, or we want to override
                                        if not year:
                                            year = year_or_release_match.group(0)

                                    secondary_title = secondary_part[:year_or_release_match.start()].strip()
                                else:
                                    secondary_title = secondary_part

                            primary_title = primary_title.replace('.', ' ')
                            secondary_title = secondary_title.replace('.', ' ')
                            return primary_title, secondary_title, year

                # if not AKA, catch titles that begin with a year
                match = re.match(r"^(\d+)", basename)
                if match:
                    potential_title = match.group(1)
                    # Check if this title could also be a year (1900-2099)
                    could_be_year = re.match(r'^(19|20)\d{2}$', potential_title) is not None

                    # Search for a different year elsewhere in the filename
                    year_match = re.search(r'\b(19|20)\d{2}\b', basename)

                    # Only accept the year_match if it's different from the potential_title
                    if year_match and (not could_be_year or year_match.group(0) != potential_title):
                        year = year_match.group(0)
                    else:
                        year = None

                    return potential_title, None, year

                # If no pattern match works but there's still a year in the filename, extract it
                year_match = re.search(r'\b(19|20)\d{2}\b', basename)
                if year_match:
                    year = year_match.group(0)
                    return None, None, year

                return None, None, None

            videopath, meta['filelist'] = await self.get_video(videoloc, meta.get('mode', 'discord'))
            search_term = os.path.basename(meta['filelist'][0]) if meta['filelist'] else None
            search_file_folder = 'file'

            video, meta['scene'], meta['imdb_id'] = await is_scene(videopath, meta, meta.get('imdb_id', 0))

            title, secondary_title, extracted_year = extract_title_and_year(video)
            if meta['debug']:
                console.print(f"Title: {title}, Secondary Title: {secondary_title}, Year: {extracted_year}")
            if secondary_title:
                meta['secondary_title'] = secondary_title
            if extracted_year and not meta.get('year'):
                meta['year'] = extracted_year

            guess_name = ntpath.basename(video).replace('-', ' ')

            if title:
                filename = title
            else:
                filename = guessit(re.sub(r"[^0-9a-zA-Z\[\\]]+", " ", guess_name), {"excludes": ["country", "language"]}).get("title", guessit(re.sub("[^0-9a-zA-Z]+", " ", guess_name), {"excludes": ["country", "language"]})["title"])
            untouched_filename = os.path.basename(video)

            # rely only on guessit for search_year for tv matching
            try:
                meta['search_year'] = guessit(video)['year']
            except Exception:
                meta['search_year'] = ""

            if not meta.get('edit', False):
                mi = await exportInfo(videopath, meta['isdir'], meta['uuid'], base_dir, export_text=True)
                meta['mediainfo'] = mi
            else:
                mi = meta['mediainfo']

            if meta.get('resolution', None) is None:
                meta['resolution'] = await self.get_resolution(guessit(video), meta['uuid'], base_dir)

        meta['sd'] = await self.is_sd(meta['resolution'])

        if " AKA " in filename.replace('.', ' '):
            filename = filename.split('AKA')[0]
        meta['filename'] = filename
        meta['bdinfo'] = bdinfo

        # Check if there's a language restriction
        if meta['has_languages'] is not None:
            audio_languages = await get_audio_languages(mi, meta)
            any_of_languages = meta['has_languages'].lower().split(",")
            # We need to have user input languages and file must have audio tracks.
            if len(any_of_languages) > 0 and len(audio_languages) > 0 and not set(any_of_languages).intersection(set(audio_languages)):
                console.print(f"[red] None of the required languages ({meta['has_languages']}) is available on the file {audio_languages}")
                raise Exception("No matching languages")

        if 'description' not in meta or meta.get('description') is None:
            meta['description'] = ""

        description_text = meta.get('description', '')
        if description_text is None:
            description_text = ""
        with open(f"{meta['base_dir']}/tmp/{meta['uuid']}/DESCRIPTION.txt", 'w', newline="", encoding='utf8') as description:
            if len(description_text):
                description.write(description_text)

        # auto torrent searching with qbittorrent that grabs torrent ids for metadata searching
        if not any(meta.get(id_type) for id_type in hash_ids + tracker_ids):
            await client.get_pathed_torrents(meta['path'], meta)

        # Ensure all manual IDs have proper default values
        meta['tmdb_manual'] = meta.get('tmdb_manual') or 0
        meta['imdb_manual'] = meta.get('imdb_manual') or 0
        meta['mal_manual'] = meta.get('mal_manual') or 0
        meta['tvdb_manual'] = meta.get('tvdb_manual') or 0
        meta['tvmaze_manual'] = meta.get('tvmaze_manual') or 0

        # Set tmdb_id
        try:
            meta['tmdb_id'] = int(meta['tmdb_manual'])
        except (ValueError, TypeError):
            meta['tmdb_id'] = 0

        # Set imdb_id with proper handling for 'tt' prefix
        try:
            if not meta.get('imdb_id'):
                imdb_value = meta['imdb_manual']
                if imdb_value:
                    if str(imdb_value).startswith('tt'):
                        meta['imdb_id'] = int(str(imdb_value)[2:])
                    else:
                        meta['imdb_id'] = int(imdb_value)
                else:
                    meta['imdb_id'] = 0
        except (ValueError, TypeError):
            meta['imdb_id'] = 0

        # Set mal_id
        try:
            meta['mal_id'] = int(meta['mal_manual'])
        except (ValueError, TypeError):
            meta['mal_id'] = 0

        # Set tvdb_id
        try:
            meta['tvdb_id'] = int(meta['tvdb_manual'])
        except (ValueError, TypeError):
            meta['tvdb_id'] = 0

        try:
            meta['tvmaze_id'] = int(meta['tvmaze_manual'])
        except (ValueError, TypeError):
            meta['tvmaze_id'] = 0

        if meta.get('category', None) is not None:
            meta['category'] = meta['category'].upper()

        # check if we've already searched torrents
        if 'base_torrent_created' not in meta:
            meta['base_torrent_created'] = False
        if 'we_checked_them_all' not in meta:
            meta['we_checked_them_all'] = False

        # if not auto qbittorrent search, this also checks with the infohash if passed.
        if meta.get('infohash') is not None and not meta['base_torrent_created'] and not meta['we_checked_them_all']:
            meta = await client.get_ptp_from_hash(meta)

        if not meta.get('image_list') and not meta.get('edit', False):
            # from the torrent id, get the torrent data
            initial_cat_check = await self.get_cat(video, meta)
            await get_tracker_data(video, meta, search_term, search_file_folder, initial_cat_check)
        else:
            console.print("Skipping existing search as meta already populated")

        # if there's no region/distributor info, lets ping some unit3d trackers and see if we get it
        ping_unit3d_config = self.config['DEFAULT'].get('ping_unit3d', False)
        if (not meta.get('region') or not meta.get('distributor')) and meta['is_disc'] == "BDMV" and ping_unit3d_config and not meta.get('edit', False):
            await ping_unit3d(meta)

        # the first user override check that allows to set metadata ids.
        user_overrides = config['DEFAULT'].get('user_overrides', False)
        if user_overrides and (meta.get('imdb_id') != 0 or meta.get('tvdb_id') != 0):
            meta = await get_source_override(meta, other_id=True)
            meta['no_override'] = True

        if meta['debug']:
            console.print("ID inputs into prep")
            console.print("category:", meta.get("category"))
            console.print(f"Raw TVDB ID: {meta['tvdb_id']} (type: {type(meta['tvdb_id']).__name__})")
            console.print(f"Raw IMDb ID: {meta['imdb_id']} (type: {type(meta['imdb_id']).__name__})")
            console.print(f"Raw TMDb ID: {meta['tmdb_id']} (type: {type(meta['tmdb_id']).__name__})")
            console.print(f"Raw TVMAZE ID: {meta['tvmaze_id']} (type: {type(meta['tvmaze_id']).__name__})")
            console.print(f"Raw MAL ID: {meta['mal_id']} (type: {type(meta['mal_id']).__name__})")

        console.print("[yellow]Building meta data.....")

        # set a timer to check speed
        if meta['debug']:
            meta_start_time = time.time()

        if meta.get('manual_language'):
            meta['original_langauge'] = meta.get('manual_language').lower()

        meta['type'] = await self.get_type(video, meta['scene'], meta['is_disc'], meta)

        if meta.get('category', None) is None:
            meta['category'] = await self.get_cat(video, meta)
        else:
            meta['category'] = meta['category'].upper()

        # if it's not an anime, we can run season/episode checks now to speed the process
        if meta.get("not_anime", False) and meta.get("category") == "TV":
            meta = await get_season_episode(video, meta)

        # if we have all of the ids, search everything all at once
        if int(meta['imdb_id']) != 0 and int(meta['tvdb_id']) != 0 and int(meta['tmdb_id']) != 0 and int(meta['tvmaze_id']) != 0:
            meta = await all_ids(meta, tvdb_api, tvdb_token)

        # Check if IMDb, TMDb, and TVDb IDs are all present
        elif int(meta['imdb_id']) != 0 and int(meta['tvdb_id']) != 0 and int(meta['tmdb_id']) != 0:
            meta = await imdb_tmdb_tvdb(meta, filename, tvdb_api, tvdb_token)

        # Check if both IMDb and TVDB IDs are present
        elif int(meta['imdb_id']) != 0 and int(meta['tvdb_id']) != 0:
            meta = await imdb_tvdb(meta, filename, tvdb_api, tvdb_token)

        # Check if both IMDb and TMDb IDs are present
        elif int(meta['imdb_id']) != 0 and int(meta['tmdb_id']) != 0:
            meta = await imdb_tmdb(meta, filename)

        # Get TMDB and IMDb metadata only if IDs are still missing, first checking mediainfo
        if meta.get('tmdb_id') == 0 and meta.get('imdb_id') == 0:
            console.print("Fetching TMDB ID...")
            meta['category'], meta['tmdb_id'], meta['imdb_id'] = await get_tmdb_imdb_from_mediainfo(
                mi, meta['category'], meta['is_disc'], meta['tmdb_id'], meta['imdb_id']
            )

        # if we're still missing both ids, lets search with the filename
        if meta.get('tmdb_id') == 0 and meta.get('imdb_id') == 0:
            console.print("Fetching TMDB ID from filename...")
            meta = await get_tmdb_id(filename, meta['search_year'], meta, meta['category'], untouched_filename)

        # If we have an IMDb ID but no TMDb ID, fetch TMDb ID from IMDb
        elif meta.get('imdb_id') != 0 and meta.get('tmdb_id') == 0:
            category, tmdb_id, original_language = await get_tmdb_from_imdb(
                meta['imdb_id'],
                meta.get('tvdb_id'),
                meta.get('search_year'),
                filename,
                debug=meta.get('debug', False),
                mode=meta.get('mode', 'discord'),
                category_preference=meta.get('category')
            )

            meta['category'] = category
            meta['tmdb_id'] = int(tmdb_id)
            meta['original_language'] = original_language

        # we have tmdb id one way or another, so lets check we have the data
        if int(meta['tmdb_id']) != 0:
            # if we have these fields already, we probably got them from a multi id searching

            if not meta.get('edit', False):
                essential_fields = ['title', 'year', 'genres', 'overview']
                tmdb_metadata_populated = all(meta.get(field) is not None for field in essential_fields)
            else:
                # if we're in that blastard edit mode, ignore any previous set data and get fresh
                tmdb_metadata_populated = False

            # otherwise, get it
            if not tmdb_metadata_populated:
                console.print("Fetching TMDB metadata...")
                try:
                    tmdb_metadata = await tmdb_other_meta(
                        tmdb_id=meta['tmdb_id'],
                        path=meta.get('path'),
                        search_year=meta.get('search_year'),
                        category=meta.get('category'),
                        imdb_id=meta.get('imdb_id', 0),
                        manual_language=meta.get('manual_language'),
                        anime=meta.get('anime', False),
                        mal_manual=meta.get('mal_manual'),
                        aka=meta.get('aka', ''),
                        original_language=meta.get('original_language'),
                        poster=meta.get('poster'),
                        debug=meta.get('debug', False),
                        mode=meta.get('mode', 'cli'),
                        tvdb_id=meta.get('tvdb_id', 0)
                    )

                    # Check if the metadata is empty or missing essential fields
                    if not tmdb_metadata or not all(tmdb_metadata.get(field) for field in ['title', 'year']):
                        error_msg = f"Failed to retrieve essential metadata from TMDB ID: {meta['tmdb_id']}"
                        console.print(f"[bold red]{error_msg}[/bold red]")
                        raise ValueError(error_msg)

                    # Update meta with return values from tmdb_other_meta
                    meta.update(tmdb_metadata)

                except Exception as e:
                    error_msg = f"TMDB metadata retrieval failed for ID {meta['tmdb_id']}: {str(e)}"
                    console.print(f"[bold red]{error_msg}[/bold red]")
                    raise RuntimeError(error_msg) from e

        # Search TVMaze only if it's a TV category and tvmaze_id is still missing
        if meta['category'] == "TV":
            if meta.get('tvmaze_id', 0) == 0:
                meta['tvmaze_id'], meta['imdb_id'], meta['tvdb_id'] = await search_tvmaze(
                    filename, meta['search_year'], meta.get('imdb_id', 0), meta.get('tvdb_id', 0),
                    manual_date=meta.get('manual_date'),
                    tvmaze_manual=meta.get('tvmaze_manual'),
                    debug=meta.get('debug', False),
                    return_full_tuple=True
                )
        else:
            meta.setdefault('tvmaze_id', 0)

        # If no IMDb ID, search for it
        # bad filenames are bad
        if meta.get('imdb_id') == 0:
            meta['imdb_id'] = await search_imdb(filename, meta['search_year'])

        # Ensure IMDb info is retrieved if it wasn't already fetched
        if meta.get('imdb_info', None) is None and int(meta['imdb_id']) != 0:
            imdb_info = await get_imdb_info_api(meta['imdb_id'], manual_language=meta.get('manual_language'), debug=meta.get('debug', False))
            meta['imdb_info'] = imdb_info
            meta['tv_year'] = imdb_info.get('tv_year', None)
            check_valid_data = meta.get('imdb_info', {}).get('title', "")
            if check_valid_data:
                aka = meta.get('imdb_info', {}).get('aka', "").strip()
                title = meta.get('imdb_info', {}).get('title', "").strip().lower()
                year = str(meta.get('imdb_info', {}).get('year', ""))

                if aka and not meta.get('aka'):
                    aka_trimmed = aka[4:].strip().lower() if aka.lower().startswith("aka") else aka.lower()
                    difference = SequenceMatcher(None, title, aka_trimmed).ratio()
                    if difference >= 0.9 or not aka_trimmed or aka_trimmed in title:
                        aka = None

                    if aka is not None:
                        if f"({year})" in aka:
                            aka = aka.replace(f"({year})", "").strip()
                        meta['aka'] = f"AKA {aka.strip()}"
                        meta['title'] = f"{meta.get('imdb_info', {}).get('title', '').strip()}"

        if meta['category'] == "TV":
            # if it wasn't skipped earlier, make sure we have the season/episode data
            if not meta.get('not_anime', False):
                meta = await get_season_episode(video, meta)
            # get all the episode data
            meta = await get_tv_data(meta, base_dir, tvdb_api, tvdb_token)

        # if we're using tvdb, lets use it's series name if it applies
        if tvdb_api and tvdb_token:
            if meta.get('tvdb_episode_data') and meta.get('tvdb_episode_data').get('series_name') != "" and meta.get('title') != meta.get('tvdb_episode_data').get('series_name'):
                series_name = meta.get('tvdb_episode_data').get('series_name', '')
                series_name = series_name.replace('(', '').replace(')', '').strip()
                meta['title'] = series_name
                if meta['debug']:
                    console.print(f"[yellow]tvdb series name: {meta.get('tvdb_episode_data').get('series_name')}")
            elif meta.get('tvdb_series_name') and meta.get('tvdb_series_name') != "" and meta.get('title') != meta.get('tvdb_series_name'):
                series_name = meta.get('tvdb_series_name')
                series_name = series_name.replace('(', '').replace(')', '').strip()
                meta['title'] = series_name
                if meta['debug']:
                    console.print(f"[yellow]tvdb series name: {meta.get('tvdb_series_name')}")

        # bluray.com data if config
        get_bluray_info = self.config['DEFAULT'].get('get_bluray_info', False)
        meta['bluray_score'] = int(self.config['DEFAULT'].get('bluray_score', 100))
        meta['bluray_single_score'] = int(self.config['DEFAULT'].get('bluray_single_score', 100))
        meta['use_bluray_images'] = self.config['DEFAULT'].get('use_bluray_images', False)
        if meta.get('is_disc') == "BDMV" and get_bluray_info and (meta.get('distributor') is None or meta.get('region') is None) and meta.get('imdb_id') != 0:
            await get_bluray_releases(meta)

        # and if we getting bluray images, we'll rehost them
        if meta.get('is_disc') == "BDMV" and meta.get('use_bluray_images', False):
            from src.rehostimages import check_hosts
            url_host_mapping = {
                "ibb.co": "imgbb",
                "pixhost.to": "pixhost",
                "imgbox.com": "imgbox",
            }

            approved_image_hosts = ['imgbox', 'imgbb', 'pixhost']
            await check_hosts(meta, "covers", url_host_mapping=url_host_mapping, img_host_index=1, approved_image_hosts=approved_image_hosts)

        if meta.get('tag', None) is None:
            # if flagged from scene checking, lets use the scene name which will have proper tags
            if meta.get('we_need_tag', False):
                meta['tag'] = await get_tag(meta['scene_name'], meta)
            else:
                meta['tag'] = await get_tag(video, meta)
                # all lowercase filenames will have bad group tag, it's probably a scene release.
                # some extracted files do not match release name so lets double check if it really is a scene release
                if not meta.get('scene') and meta['tag']:
                    base = os.path.basename(video)
                    match = re.match(r"^(.+)\.[a-zA-Z0-9]{3}$", os.path.basename(video))
                    if match and (not meta['is_disc'] or meta.get('keep_folder', False)):
                        base = match.group(1)
                        is_all_lowercase = base.islower()
                        if is_all_lowercase:
                            release_name = await is_scene(videopath, meta, meta.get('imdb_id', 0), lower=True)
                            if release_name is not None:
                                meta['scene_name'] = release_name
                                meta['tag'] = await get_tag(release_name, meta)

        else:
            if not meta['tag'].startswith('-') and meta['tag'] != "":
                meta['tag'] = f"-{meta['tag']}"

        meta = await tag_override(meta)

        # user override check that only sets data after metadata setting
        if user_overrides and not meta.get('no_override', False):
            meta = await get_source_override(meta)

        if meta.get('tag') == "-SubsPlease":  # SubsPlease-specific
            tracks = meta.get('mediainfo', {}).get('media', {}).get('track', [])  # Get all tracks
            bitrate = tracks[1].get('BitRate', '') if len(tracks) > 1 and not isinstance(tracks[1].get('BitRate', ''), dict) else ''  # Check that bitrate is not a dict
            bitrate_oldMediaInfo = tracks[0].get('OverallBitRate', '') if len(tracks) > 0 and not isinstance(tracks[0].get('OverallBitRate', ''), dict) else ''  # Check for old MediaInfo
            meta['episode_title'] = ""
            if (bitrate.isdigit() and int(bitrate) >= 8000000) or (bitrate_oldMediaInfo.isdigit() and int(bitrate_oldMediaInfo) >= 8000000) and meta.get('resolution') == "1080p":  # 8Mbps for 1080p
                meta['service'] = "CR"
            elif (bitrate.isdigit() or bitrate_oldMediaInfo.isdigit()) and meta.get('resolution') == "1080p":  # Only assign if at least one bitrate is present, otherwise leave it to user
                meta['service'] = "HIDI"
            elif (bitrate.isdigit() and int(bitrate) >= 4000000) or (bitrate_oldMediaInfo.isdigit() and int(bitrate_oldMediaInfo) >= 4000000) and meta.get('resolution') == "720p":  # 4Mbps for 720p
                meta['service'] = "CR"
            elif (bitrate.isdigit() or bitrate_oldMediaInfo.isdigit()) and meta.get('resolution') == "720p":
                meta['service'] = "HIDI"

        meta['video'] = video

        meta['audio'], meta['channels'], meta['has_commentary'] = await get_audio_v2(mi, meta, bdinfo)

        if meta['tag'][1:].startswith(meta['channels']):
            meta['tag'] = meta['tag'].replace(f"-{meta['channels']}", '')

        if meta.get('no_tag', False):
            meta['tag'] = ""

        meta['3D'] = await self.is_3d(mi, bdinfo)

        meta['source'], meta['type'] = await self.get_source(meta['type'], video, meta['path'], meta['is_disc'], meta, folder_id, base_dir)

        if meta.get('service', None) in (None, ''):
            meta['service'], meta['service_longname'] = await get_service(video, meta.get('tag', ''), meta['audio'], meta['filename'])
        elif meta.get('service'):
            services = await get_service(get_services_only=True)
            meta['service_longname'] = max((k for k, v in services.items() if v == meta['service']), key=len, default=meta['service'])

        meta['uhd'] = await get_uhd(meta['type'], guessit(meta['path']), meta['resolution'], meta['path'])
        meta['hdr'] = await get_hdr(mi, bdinfo)

        meta['distributor'] = await get_distributor(meta['distributor'])

        if meta.get('is_disc', None) == "BDMV":  # Blu-ray Specific
            meta['region'] = await get_region(bdinfo, meta.get('region', None))
            meta['video_codec'] = await get_video_codec(bdinfo)
        else:
            meta['video_encode'], meta['video_codec'], meta['has_encode_settings'], meta['bit_depth'] = await get_video_encode(mi, meta['type'], bdinfo)

        if meta.get('no_edition') is False:
            meta['edition'], meta['repack'] = await get_edition(meta['path'], bdinfo, meta['filelist'], meta.get('manual_edition'), meta)
            if "REPACK" in meta.get('edition', ""):
                meta['repack'] = re.search(r"REPACK[\d]?", meta['edition'])[0]
                meta['edition'] = re.sub(r"REPACK[\d]?", "", meta['edition']).strip().replace('  ', ' ')
        else:
            meta['edition'] = ""

        meta.get('stream', False)
        meta['stream'] = await self.stream_optimized(meta['stream'])
        meta.get('anon', False)
        meta['anon'] = self.is_anon(meta['anon'])

        # return duplicate ids so I don't have to catch every site file
        meta['tmdb'] = meta.get('tmdb_id')
        if int(meta.get('imdb_id')) != 0:
            imdb_str = str(meta['imdb_id']).zfill(7)
            meta['imdb'] = imdb_str
        else:
            meta['imdb'] = '0'
        meta['mal'] = meta.get('mal_id')
        meta['tvdb'] = meta.get('tvdb_id')
        meta['tvmaze'] = meta.get('tvmaze_id')

        # we finished the metadata, time it
        if meta['debug']:
            meta_finish_time = time.time()
            console.print(f"Metadata processed in {meta_finish_time - meta_start_time:.2f} seconds")

        return meta

    async def get_cat(self, video, meta):
        if meta.get('category'):
            return meta.get('category')

        path_patterns = [
            r'(?i)[\\/](?:tv|tvshows|tv.shows|series|shows)[\\/]',
            r'(?i)[\\/](?:season\s*\d+|s\d+|complete)[\\/]',
            r'(?i)[\\/](?:s\d{1,2}e\d{1,2}|s\d{1,2}|season\s*\d+)',
            r'(?i)(?:complete series|tv pack|season\s*\d+\s*complete)'
        ]

        filename_patterns = [
            r'(?i)s\d{1,2}e\d{1,2}',
            r'(?i)\d{1,2}x\d{2}',
            r'(?i)(?:season|series)\s*\d+',
            r'(?i)e\d{2,3}\s*\-',
            r'(?i)(?:complete|full)\s*(?:season|series)'
        ]

        path = meta.get('path', '')
        uuid = meta.get('uuid', '')

        for pattern in path_patterns:
            if re.search(pattern, path):
                return "TV"

        for pattern in filename_patterns:
            if re.search(pattern, uuid) or re.search(pattern, os.path.basename(path)):
                return "TV"

        try:
            category = guessit(video.replace('1.0', ''))['type']
            if category.lower() == "movie":
                category = "MOVIE"  # 1
            elif category.lower() in ("tv", "episode"):
                category = "TV"  # 2
            else:
                category = "TV"
            return category
        except Exception:
            return "TV"

    """
    Get video files

    """
    async def get_video(self, videoloc, mode):
        filelist = []
        videoloc = os.path.abspath(videoloc)
        if os.path.isdir(videoloc):
            globlist = glob.glob1(videoloc, "*.mkv") + glob.glob1(videoloc, "*.mp4") + glob.glob1(videoloc, "*.ts")
            for file in globlist:
                if not file.lower().endswith('sample.mkv') or "!sample" in file.lower():
                    filelist.append(os.path.abspath(f"{videoloc}{os.sep}{file}"))
            try:
                video = sorted(filelist)[0]
            except IndexError:
                console.print("[bold red]No Video files found")
                if mode == 'cli':
                    exit()
        else:
            video = videoloc
            filelist.append(videoloc)
        filelist = sorted(filelist)
        return video, filelist

    """
    Get Resolution
    """

    async def get_resolution(self, guess, folder_id, base_dir):
        with open(f'{base_dir}/tmp/{folder_id}/MediaInfo.json', 'r', encoding='utf-8') as f:
            mi = json.load(f)
            try:
                width = mi['media']['track'][1]['Width']
                height = mi['media']['track'][1]['Height']
            except Exception:
                width = 0
                height = 0
            framerate = mi['media']['track'][1].get('FrameRate', '')
            try:
                scan = mi['media']['track'][1]['ScanType']
            except Exception:
                scan = "Progressive"
            if scan == "Progressive":
                scan = "p"
            elif scan == "Interlaced":
                scan = 'i'
            elif framerate == "25.000":
                scan = "p"
            else:
                # Fallback using regex on meta['uuid'] - mainly for HUNO fun and games.
                match = re.search(r'\b(1080p|720p|2160p)\b', folder_id, re.IGNORECASE)
                if match:
                    scan = "p"  # Assume progressive based on common resolution markers
                else:
                    scan = "i"  # Default to interlaced if no indicators are found
            width_list = [3840, 2560, 1920, 1280, 1024, 960, 854, 720, 15360, 7680, 0]
            height_list = [2160, 1440, 1080, 720, 576, 540, 480, 8640, 4320, 0]
            width = await self.closest(width_list, int(width))
            actual_height = int(height)
            height = await self.closest(height_list, int(height))
            res = f"{width}x{height}{scan}"
            resolution = await mi_resolution(res, guess, width, scan, height, actual_height)
        return resolution

    async def closest(self, lst, K):
        # Get closest, but not over
        lst = sorted(lst)
        mi_input = K
        res = 0
        for each in lst:
            if mi_input > each:
                pass
            else:
                res = each
                break
        return res

        # return lst[min(range(len(lst)), key = lambda i: abs(lst[i]-K))]

    async def is_sd(self, resolution):
        if resolution in ("480i", "480p", "576i", "576p", "540p"):
            sd = 1
        else:
            sd = 0
        return sd

    """
    Get type and category
    """

    async def get_type(self, video, scene, is_disc, meta):
        if meta.get('manual_type'):
            type = meta.get('manual_type')
        else:
            filename = os.path.basename(video).lower()
            if "remux" in filename:
                type = "REMUX"
            elif any(word in filename for word in [" web ", ".web.", "web-dl", "webdl"]):
                type = "WEBDL"
            elif "webrip" in filename:
                type = "WEBRIP"
            # elif scene == True:
                # type = "ENCODE"
            elif "hdtv" in filename:
                type = "HDTV"
            elif is_disc is not None:
                type = "DISC"
            elif "dvdrip" in filename:
                type = "DVDRIP"
                # exit()
            else:
                type = "ENCODE"
        return type

    async def is_3d(self, mi, bdinfo):
        if bdinfo is not None:
            if bdinfo['video'][0]['3d'] != "":
                return "3D"
            else:
                return ""
        else:
            return ""

    async def get_source(self, type, video, path, is_disc, meta, folder_id, base_dir):
        if not meta.get('is_disc') == "BDMV":
            try:
                with open(f'{base_dir}/tmp/{folder_id}/MediaInfo.json', 'r', encoding='utf-8') as f:
                    mi = json.load(f)
            except Exception:
                if meta['debug']:
                    console.print("No mediainfo.json")
        try:
            if meta.get('manual_source', None):
                source = meta['manual_source']
            else:
                try:
                    source = guessit(video)['source']
                except Exception:
                    try:
                        source = guessit(path)['source']
                    except Exception:
                        source = "BluRay"
            if source in ("Blu-ray", "Ultra HD Blu-ray", "BluRay", "BR") or is_disc == "BDMV":
                if type == "DISC":
                    source = "Blu-ray"
                elif type in ('ENCODE', 'REMUX'):
                    source = "BluRay"
            if is_disc == "DVD" or source in ("DVD", "dvd"):
                try:
                    if is_disc == "DVD":
                        mediainfo = MediaInfo.parse(f"{meta['discs'][0]['path']}/VTS_{meta['discs'][0]['main_set'][0][:2]}_0.IFO")
                    else:
                        mediainfo = MediaInfo.parse(video)
                    for track in mediainfo.tracks:
                        if track.track_type == "Video":
                            system = track.standard
                    if system not in ("PAL", "NTSC"):
                        raise WeirdSystem  # noqa: F405
                except Exception:
                    try:
                        other = guessit(video)['other']
                        if "PAL" in other:
                            system = "PAL"
                        elif "NTSC" in other:
                            system = "NTSC"
                    except Exception:
                        system = ""
                    if system == "" or system is None:
                        try:
                            framerate = mi['media']['track'][1].get('FrameRate', '')
                            if '25' in framerate or '50' in framerate:
                                system = "PAL"
                            elif framerate:
                                system = "NTSC"
                            else:
                                system = ""
                        except Exception:
                            system = ""
                finally:
                    if system is None:
                        system = ""
                    if type == "REMUX":
                        system = f"{system} DVD".strip()
                    source = system
            if source in ("Web", "WEB"):
                if type == "ENCODE":
                    type = "WEBRIP"
            if source in ("HD-DVD", "HD DVD", "HDDVD"):
                if is_disc == "HDDVD":
                    source = "HD DVD"
                if type in ("ENCODE", "REMUX"):
                    source = "HDDVD"
            if type in ("WEBDL", 'WEBRIP'):
                source = "Web"
            if source == "Ultra HDTV":
                source = "UHDTV"
        except Exception:
            console.print(traceback.format_exc())
            source = "BluRay"

        return source, type

    async def stream_optimized(self, stream_opt):
        if stream_opt is True:
            stream = 1
        else:
            stream = 0
        return stream

    def is_anon(self, anon_in):
        anon = self.config['DEFAULT'].get("Anon", "False")
        if anon.lower() == "true":
            console.print("[bold red]Global ANON has been removed in favor of per-tracker settings. Please update your config accordingly.")
            time.sleep(10)
        if anon_in is True:
            anon_out = 1
        else:
            anon_out = 0
        return anon_out

    async def get_dvd_size(self, discs, manual_dvds):
        sizes = []
        dvd_sizes = []
        for each in discs:
            sizes.append(each['size'])
        grouped_sizes = [list(i) for j, i in itertools.groupby(sorted(sizes))]
        for each in grouped_sizes:
            if len(each) > 1:
                dvd_sizes.append(f"{len(each)}x{each[0]}")
            else:
                dvd_sizes.append(each[0])
        dvd_sizes.sort()
        compact = " ".join(dvd_sizes)

        if manual_dvds:
            compact = str(manual_dvds)

        return compact
