# -*- coding: utf-8 -*-
# import discord
import os
import asyncio
import requests
import platform
from str2bool import str2bool
from pymediainfo import MediaInfo
import math
from torf import Torrent
from pathlib import Path
from src.trackers.COMMON import COMMON
from src.console import console

class ANT():
    """
    Edit for Tracker:
        Edit BASE.torrent with announce and source
        Check for duplicates
        Set type/category IDs
        Upload
    """

    ###############################################################
    # #######                    EDIT ME                    ##### #
    ###############################################################

    # ALSO EDIT CLASS NAME ABOVE

    def __init__(self, config):
        self.config = config
        self.tracker = 'ANT'
        self.source_flag = 'ANT'
        self.search_url = 'https://anthelion.me/api.php'
        self.upload_url = 'https://anthelion.me/api.php'
        self.banned_groups = ['3LTON', '4yEo', 'ADE', 'AFG', 'AniHLS', 'AnimeRG', 'AniURL', 'AROMA', 'aXXo', 'Brrip', 'CHD', 'CM8', 
                            'CrEwSaDe', 'd3g', 'DDR', 'DNL', 'DeadFish', 'ELiTE', 'eSc', 'FaNGDiNG0', 'FGT', 'Flights', 'FRDS', 
                            'FUM', 'HAiKU', 'HD2DVD', 'HDS', 'HDTime', 'Hi10', 'ION10', 'iPlanet', 'JIVE', 'KiNGDOM', 'Leffe', 
                            'LiGaS', 'LOAD', 'MeGusta', 'MkvCage', 'mHD', 'mSD', 'NhaNc3', 'nHD', 'NOIVTC', 'nSD', 'Oj', 'Ozlem', 
                            'PiRaTeS', 'PRoDJi', 'RAPiDCOWS', 'RARBG', 'RetroPeeps', 'RDN', 'REsuRRecTioN', 'RMTeam', 'SANTi', 
                            'SicFoI', 'SPASM', 'SPDVD', 'STUTTERSHIT', 'TBS', 'Telly', 'TM', 'UPiNSMOKE', 'URANiME', 'WAF', 'xRed', 
                            'XS', 'YIFY', 'YTS', 'Zeus', 'ZKBL', 'ZmN', 'ZMNT']
        self.signature = None
        pass

    async def get_flags(self, meta):
        flags = []
        for each in ['Directors', 'Extended', 'Uncut', 'Unrated', '4KRemaster']:
            if each in meta['edition'].replace("'", ""):
                flags.append(each)
        for each in ['Dual-Audio', 'Atmos']:
            if each in meta['audio']:
                flags.append(each.replace('-', ''))
        if meta.get('has_commentary', False):
            flags.append('Commentary')
        if meta['3D'] == "3D":
            flags.append('3D')
        if "HDR" in meta['hdr']:
            flags.append('HDR10')
        if "DV" in meta['hdr']:
            flags.append('DV')
        if "Criterion" in meta.get('distributor', ''):
            flags.append('Criterion')
        if "REMUX" in meta['type']:
            flags.append('Remux')
        return flags

    ###############################################################
    # ####   STOP HERE UNLESS EXTRA MODIFICATION IS NEEDED    ### #
    ###############################################################

    async def upload(self, meta):
        common = COMMON(config=self.config)
        torrent_filename = "BASE"
        torrent = Torrent.read(f"{meta['base_dir']}/tmp/{meta['uuid']}/BASE.torrent")
        total_size = sum(file.size for file in torrent.files)

        # Calculate the number of pieces and the torrent file size based on the current piece size
        def calculate_pieces_and_file_size(total_size, piece_size):
            num_pieces = math.ceil(total_size / piece_size)
            torrent_file_size = 20 + (num_pieces * 20)  # Approximate size: 20 bytes header + 20 bytes per piece
            return num_pieces, torrent_file_size

        # Check if the existing torrent fits within the constraints
        num_pieces, torrent_file_size = calculate_pieces_and_file_size(total_size, torrent.piece_size)

        # If the torrent doesn't meet the constraints, regenerate it
        if not (1000 <= num_pieces <= 2000) or torrent_file_size > 102400:
            console.print("[yellow]Regenerating torrent to fit within 1000-2000 pieces and 100 KiB .torrent size limit needed for ANT.")
            from src.prep import Prep
            prep = Prep(screens=meta['screens'], img_host=meta['imghost'], config=self.config)
            
            # Call create_torrent with the default piece size calculation
            prep.create_torrent(meta, Path(meta['path']), "ANT")
            torrent_filename = "ANT"
        else:
            console.print("[green]Existing torrent meets the constraints.")

        await common.edit_torrent(meta, self.tracker, self.source_flag, torrent_filename=torrent_filename)
        flags = await self.get_flags(meta)
        if meta['anon'] == 0 and bool(str2bool(str(self.config['TRACKERS'][self.tracker].get('anon', "False")))) is False:
            anon = 0
        else:
            anon = 1

        if meta['bdinfo'] is not None:
            bd_dump = open(f"{meta['base_dir']}/tmp/{meta['uuid']}/BD_SUMMARY_00.txt", 'r', encoding='utf-8').read()
            bd_dump = f'[spoiler=BDInfo][pre]{bd_dump}[/pre][/spoiler]'
            path = os.path.join(meta['bdinfo']['path'], 'STREAM')
            file_name = meta['bdinfo']['files'][0]['file'].lower()
            m2ts = os.path.join(path, file_name)
            media_info_output = str(MediaInfo.parse(m2ts, output="text", full=False))
            mi_dump = media_info_output.replace('\r\n', '\n')
        else:
            mi_dump = open(f"{meta['base_dir']}/tmp/{meta['uuid']}/MEDIAINFO.txt", 'r', encoding='utf-8').read()
        open_torrent = open(f"{meta['base_dir']}/tmp/{meta['uuid']}/[{self.tracker}]{meta['clean_name']}.torrent", 'rb')
        files = {'file_input': open_torrent}
        data = {
            'api_key': self.config['TRACKERS'][self.tracker]['api_key'].strip(),
            'action': 'upload',
            'tmdbid': meta['tmdb'],
            'mediainfo': mi_dump,
            'flags[]': flags,
            'anonymous': anon,
            'screenshots': '\n'.join([x['raw_url'] for x in meta['image_list']][:4])
        }
        if meta['bdinfo'] is not None:
            data.update({
                'media': 'Blu-ray',
                'releasegroup': str(meta['tag'])[1:],
                'release_desc': bd_dump,
                'flagchangereason': "BDMV Uploaded with L4G's Upload Assistant"})
        if meta['scene']:
            # ID of "Scene?" checkbox on upload form is actually "censored"
            data['censored'] = 1
        headers = {
            'User-Agent': f'Upload Assistant/2.1 ({platform.system()} {platform.release()})'
        }
        
        try:
            if not meta['debug']:
                response = requests.post(url=self.upload_url, files=files, data=data, headers=headers)
                if response.status_code in [200, 201]:
                    response_data = response.json()
                else:
                    response_data = {
                        "error": f"Unexpected status code: {response.status_code}",
                        "response_content": response.text  # or use response.json() if JSON is expected
                    }
                console.print(response_data)
            else:
                console.print("[cyan]Request Data:")
                console.print(data)
        finally:
            open_torrent.close()

    async def edit_desc(self, meta):
        return

    async def search_existing(self, meta):
        dupes = []
        console.print("[yellow]Searching for existing torrents on site...")
        params = {
            'apikey': self.config['TRACKERS'][self.tracker]['api_key'].strip(),
            't': 'search',
            'o': 'json'
        }
        if str(meta['tmdb']) != "0":
            params['tmdb'] = meta['tmdb']
        elif int(meta['imdb_id'].replace('tt', '')) != 0:
            params['imdb'] = meta['imdb_id']
        try:
            response = requests.get(url='https://anthelion.me/api', params=params)
            response = response.json()
            for each in response['item']:
                largest = [each][0]['files'][0]
                for file in [each][0]['files']:
                    if int(file['size']) > int(largest['size']):
                        largest = file
                result = largest['name']
                dupes.append(result)
        except Exception:
            console.print('[bold red]Unable to search for existing torrents on site. Either the site is down or your API key is incorrect')
            await asyncio.sleep(5)

        return dupes