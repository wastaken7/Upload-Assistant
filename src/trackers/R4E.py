# -*- coding: utf-8 -*-
# import discord
import asyncio
import requests
from str2bool import str2bool
import tmdbsimple as tmdb
import platform
import bencodepy
import os
import glob

from src.trackers.COMMON import COMMON
from src.console import console


class R4E():
    """
    Edit for Tracker:
        Edit BASE.torrent with announce and source
        Check for duplicates
        Set type/category IDs
        Upload
    """
    def __init__(self, config):
        self.config = config
        self.tracker = 'R4E'
        self.source_flag = 'R4E'
        # self.signature = f"\n[center][url=https://github.com/L4GSP1KE/Upload-Assistant]Created by L4G's Upload Assistant[/url][/center]"
        self.signature = None
        self.banned_groups = [""]
        pass

    async def upload(self, meta, disctype):
        common = COMMON(config=self.config)
        await common.edit_torrent(meta, self.tracker, self.source_flag)
        cat_id = await self.get_cat_id(meta['category'], meta['tmdb'])
        type_id = await self.get_type_id(meta['resolution'])
        await common.unit3d_edit_desc(meta, self.tracker, self.signature)
        name = await self.edit_name(meta)
        if meta['anon'] == 0 and bool(str2bool(str(self.config['TRACKERS']['R4E'].get('anon', "False")))) is False:
            anon = 0
        else:
            anon = 1
        if meta['bdinfo'] is not None:
            mi_dump = None
            bd_dump = open(f"{meta['base_dir']}/tmp/{meta['uuid']}/BD_SUMMARY_00.txt", 'r', encoding='utf-8').read()
        else:
            mi_dump = open(f"{meta['base_dir']}/tmp/{meta['uuid']}/MEDIAINFO.txt", 'r', encoding='utf-8').read()
            bd_dump = None
        desc = open(f"{meta['base_dir']}/tmp/{meta['uuid']}/[R4E]DESCRIPTION.txt", 'r', encoding='utf-8').read()
        open_torrent = open(f"{meta['base_dir']}/tmp/{meta['uuid']}/[R4E]{meta['clean_name']}.torrent", 'rb')
        files = {'torrent': open_torrent}
        base_dir = meta['base_dir']
        uuid = meta['uuid']
        specified_dir_path = os.path.join(base_dir, "tmp", uuid, "*.nfo")
        nfo_files = glob.glob(specified_dir_path)
        nfo_file = None
        if nfo_files:
            nfo_file = open(nfo_files[0], 'rb')
        if nfo_file:
            files['nfo'] = ("nfo_file.nfo", nfo_file, "text/plain")
        data = {
            'name': name,
            'description': desc,
            'mediainfo': mi_dump,
            'bdinfo': bd_dump,
            'category_id': cat_id,
            'type_id': type_id,
            'tmdb': meta['tmdb'],
            'imdb': meta['imdb_id'].replace('tt', ''),
            'tvdb': meta['tvdb_id'],
            'mal': meta['mal_id'],
            'igdb': 0,
            'anonymous': anon,
            'stream': meta['stream'],
            'sd': meta['sd'],
            'keywords': meta['keywords'],
            # 'personal_release' : int(meta.get('personalrelease', False)), NOT IMPLEMENTED on R4E
            # 'internal' : 0,
            # 'featured' : 0,
            # 'free' : 0,
            # 'double_up' : 0,
            # 'sticky' : 0,
        }
        headers = {
            'User-Agent': f'Upload Assistant/2.2 ({platform.system()} {platform.release()})'
        }
        url = f"https://racing4everyone.eu/api/torrents/upload?api_token={self.config['TRACKERS']['R4E']['api_key'].strip()}"
        if meta.get('category') == "TV":
            data['season_number'] = meta.get('season_int', '0')
            data['episode_number'] = meta.get('episode_int', '0')
        if meta['debug'] is False:
            response = requests.post(url=url, files=files, data=data, headers=headers)
            try:

                console.print(response.json())
            except Exception:
                console.print("It may have uploaded, go check")
                return
        else:
            console.print("[cyan]Request Data:")
            console.print(data)
        open_torrent.close()

    async def edit_name(self, meta):
        name = meta['name']
        return name

    async def get_cat_id(self, category_name, tmdb_id):
        if category_name == 'MOVIE':
            movie = tmdb.Movies(tmdb_id)
            movie_info = movie.info()
            is_docu = self.is_docu(movie_info['genres'])
            category_id = '70'  # Motorsports Movie
            if is_docu:
                category_id = '66'  # Documentary
        elif category_name == 'TV':
            tv = tmdb.TV(tmdb_id)
            tv_info = tv.info()
            is_docu = self.is_docu(tv_info['genres'])
            category_id = '79'  # TV Series
            if is_docu:
                category_id = '2'  # TV Documentary
        else:
            category_id = '24'
        return category_id

    async def get_type_id(self, type):
        type_id = {
            '8640p': '2160p',
            '4320p': '2160p',
            '2160p': '2160p',
            '1440p': '1080p',
            '1080p': '1080p',
            '1080i': '1080i',
            '720p': '720p',
            '576p': 'SD',
            '576i': 'SD',
            '480p': 'SD',
            '480i': 'SD'
        }.get(type, '10')
        return type_id

    async def is_docu(self, genres):
        is_docu = False
        for each in genres:
            if each['id'] == 99:
                is_docu = True
        return is_docu

    async def search_existing(self, meta, disctype):
        dupes = []
        console.print("[yellow]Searching for existing torrents on R4E...")
        url = "https://racing4everyone.eu/api/torrents/filter"
        params = {
            'api_token': self.config['TRACKERS']['R4E']['api_key'].strip(),
            'tmdb': meta['tmdb'],
            'categories[]': await self.get_cat_id(meta['category']),
            'types[]': await self.get_type_id(meta['type']),
            'name': ""
        }
        if meta['category'] == 'TV':
            params['name'] = f"{meta.get('season', '')}{meta.get('episode', '')}"
        if meta.get('edition', "") != "":
            params['name'] = params['name'] + meta['edition']
        try:
            response = requests.get(url=url, params=params)
            response = response.json()
            for each in response['data']:
                result = [each][0]['attributes']['name']
                # difference = SequenceMatcher(None, meta['clean_name'], result).ratio()
                # if difference >= 0.05:
                dupes.append(result)
        except Exception:
            console.print('[bold red]Unable to search for existing torrents on site. Either the site is down or your API key is incorrect')
            await asyncio.sleep(5)

        return dupes

    async def search_torrent_page(self, meta, disctype):
        torrent_file_path = f"{meta['base_dir']}/tmp/{meta['uuid']}/[{self.tracker}]{meta['clean_name']}.torrent"
        Name = meta['name']
        quoted_name = f'"{Name}"'

        params = {
            'api_token': self.config['TRACKERS'][self.tracker]['api_key'].strip(),
            'name': quoted_name
        }

        try:
            response = requests.get(url=self.search_url, params=params)
            response.raise_for_status()
            response_data = response.json()

            if response_data['data'] and isinstance(response_data['data'], list):
                details_link = response_data['data'][0]['attributes'].get('details_link')

                if details_link:
                    with open(torrent_file_path, 'rb') as open_torrent:
                        torrent_data = open_torrent.read()

                    torrent = bencodepy.decode(torrent_data)
                    torrent[b'comment'] = details_link.encode('utf-8')
                    updated_torrent_data = bencodepy.encode(torrent)

                    with open(torrent_file_path, 'wb') as updated_torrent_file:
                        updated_torrent_file.write(updated_torrent_data)

                    return details_link
                else:
                    return None
            else:
                return None

        except requests.exceptions.RequestException as e:
            print(f"An error occurred during the request: {e}")
            return None
