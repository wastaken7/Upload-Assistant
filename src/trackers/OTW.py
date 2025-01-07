# -*- coding: utf-8 -*-
# import discord
import asyncio
import platform
import os
import httpx
from urllib.parse import urlparse
import glob
import requests
from src.trackers.COMMON import COMMON
from src.console import console
from src.takescreens import disc_screenshots, dvd_screenshots, screenshots
from src.uploadscreens import upload_screens


class OTW():
    """
    Edit for Tracker:
        Edit BASE.torrent with announce and source
        Check for duplicates
        Set type/category IDs
        Upload
    """

    def __init__(self, config):
        self.config = config
        self.tracker = 'OTW'
        self.source_flag = 'OLD'
        self.upload_url = 'https://oldtoons.world/api/torrents/upload'
        self.search_url = 'https://oldtoons.world/api/torrents/filter'
        self.signature = "\n[center][url=https://github.com/Audionut/Upload-Assistant]Created by Audionut's Upload Assistant[/url][/center]"
        self.banned_groups = [
            '[Oj]', '3LTON', '4yEo', 'ADE', 'AFG', 'AniHLS', 'AnimeRG', 'AniURL', 'AROMA', 'aXXo', 'Brrip', 'CHD', 'CM8', 'CrEwSaDe', 'd3g', 'DeadFish', 'DNL', 'ELiTE', 'eSc', 'FaNGDiNG0', 'FGT', 'Flights',
            'FRDS', 'FUM', 'HAiKU', 'HD2DVD', 'HDS', 'HDTime', 'Hi10', 'ION10', 'iPlanet', 'JIVE', 'KiNGDOM', 'Leffe', 'LEGi0N', 'LOAD', 'MeGusta', 'mHD', 'mSD', 'NhaNc3', 'nHD', 'nikt0', 'NOIVTC', 'OFT',
            'nSD', 'PiRaTeS', 'playBD', 'PlaySD', 'playXD', 'PRODJi', 'RAPiDCOWS', 'RARBG', 'RetroPeeps', 'RDN', 'REsuRRecTioN', 'RMTeam', 'SANTi', 'SicFoI', 'SPASM', 'SPDVD', 'STUTTERSHIT', 'Telly', 'TM',
            'TRiToN', 'UPiNSMOKE', 'URANiME', 'WAF', 'x0r', 'xRed', 'XS', 'YIFY', 'ZKBL', 'ZmN', 'ZMNT', 'AOC',
            ['EVO', 'Raw Content Only'], ['TERMiNAL', 'Raw Content Only'], ['ViSION', 'Note the capitalization and characters used'], ['CMRG', 'Raw Content Only']
        ]
        pass

    async def get_cat_id(self, category_name):
        category_id = {
            'MOVIE': '1',
            'TV': '2',
        }.get(category_name, '0')
        return category_id

    async def get_type_id(self, type):
        type_id = {
            'DISC': '1',
            'REMUX': '2',
            'WEBDL': '4',
            'WEBRIP': '5',
            'HDTV': '6',
            'ENCODE': '3'
        }.get(type, '0')
        return type_id

    async def get_res_id(self, resolution):
        resolution_id = {
            '8640p': '10',
            '4320p': '1',
            '2160p': '2',
            '1440p': '3',
            '1080p': '3',
            '1080i': '4',
            '720p': '5',
            '576p': '6',
            '576i': '7',
            '480p': '8',
            '480i': '9'
        }.get(resolution, '10')
        return resolution_id

    async def upload(self, meta, disctype):
        common = COMMON(config=self.config)
        await self.upload_with_retry(meta, common)

    async def upload_with_retry(self, meta, common, img_host_index=1):
        url_host_mapping = {
            "ibb.co": "imgbb",
            "pixhost.to": "pixhost",
            "imgbox.com": "imgbox",
            "imagebam.com": "bam",
        }

        approved_image_hosts = ['imgbox', 'imgbb', 'pixhost', 'bam']

        for image in meta['image_list']:
            raw_url = image['raw_url']
            parsed_url = urlparse(raw_url)
            hostname = parsed_url.netloc
            mapped_host = self.match_host(hostname, url_host_mapping.keys())
            mapped_host = url_host_mapping.get(mapped_host, mapped_host)
            if meta['debug']:
                if mapped_host in approved_image_hosts:
                    console.print(f"[green]URL '{raw_url}' is correctly matched to approved host '{mapped_host}'.")
                else:
                    console.print(f"[red]URL '{raw_url}' is not recognized as part of an approved host.")

        if all(
            url_host_mapping.get(
                self.match_host(urlparse(image['raw_url']).netloc, url_host_mapping.keys()),
                self.match_host(urlparse(image['raw_url']).netloc, url_host_mapping.keys()),
            ) in approved_image_hosts
            for image in meta['image_list']
        ):
            image_list = meta['image_list']
        else:
            images_reuploaded = False
            while img_host_index <= len(approved_image_hosts):
                image_list, retry_mode, images_reuploaded = await self.handle_image_upload(meta, img_host_index, approved_image_hosts)

                if retry_mode:
                    console.print(f"[yellow]Switching to the next image host. Current index: {img_host_index}")
                    img_host_index += 1
                    continue

                new_images_key = 'otw_images_key'
                if image_list is not None:
                    image_list = meta[new_images_key]
                    break

            if image_list is None:
                console.print("[red]All image hosts failed. Please check your configuration.")
                return

        common = COMMON(config=self.config)
        await common.edit_torrent(meta, self.tracker, self.source_flag)
        cat_id = await self.get_cat_id(meta['category'])
        type_id = await self.get_type_id(meta['type'])
        resolution_id = await self.get_res_id(meta['resolution'])
        await common.unit3d_edit_desc(meta, self.tracker, self.signature)
        region_id = await common.unit3d_region_ids(meta.get('region'))
        distributor_id = await common.unit3d_distributor_ids(meta.get('distributor'))
        if meta['anon'] == 0 and not self.config['TRACKERS'][self.tracker].get('anon', "False"):
            anon = 0
        else:
            anon = 1

        if meta['bdinfo'] is not None:
            mi_dump = None
            bd_dump = open(f"{meta['base_dir']}/tmp/{meta['uuid']}/BD_SUMMARY_00.txt", 'r', encoding='utf-8').read()
        else:
            mi_dump = open(f"{meta['base_dir']}/tmp/{meta['uuid']}/MEDIAINFO.txt", 'r', encoding='utf-8').read()
            bd_dump = None
        desc = open(f"{meta['base_dir']}/tmp/{meta['uuid']}/[{self.tracker}]DESCRIPTION.txt", 'r', encoding='utf-8').read()
        open_torrent = open(f"{meta['base_dir']}/tmp/{meta['uuid']}/[{self.tracker}]{meta['clean_name']}.torrent", 'rb')
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
            'name': meta['name'],
            'description': desc,
            'mediainfo': mi_dump,
            'bdinfo': bd_dump,
            'category_id': cat_id,
            'type_id': type_id,
            'resolution_id': resolution_id,
            'tmdb': meta['tmdb'],
            'imdb': meta['imdb_id'].replace('tt', ''),
            'tvdb': meta['tvdb_id'],
            'mal': meta['mal_id'],
            'igdb': 0,
            'anonymous': anon,
            'stream': meta['stream'],
            'sd': meta['sd'],
            'keywords': meta['keywords'],
            'personal_release': int(meta.get('personalrelease', False)),
            'internal': 0,
            'featured': 0,
            'free': 0,
            'doubleup': 0,
            'sticky': 0,
        }
        # Internal
        if self.config['TRACKERS'][self.tracker].get('internal', False) is True:
            if meta['tag'] != "" and (meta['tag'][1:] in self.config['TRACKERS'][self.tracker].get('internal_groups', [])):
                data['internal'] = 1

        if region_id != 0:
            data['region_id'] = region_id
        if distributor_id != 0:
            data['distributor_id'] = distributor_id
        if meta.get('category') == "TV":
            data['season_number'] = meta.get('season_int', '0')
            data['episode_number'] = meta.get('episode_int', '0')
        headers = {
            'User-Agent': f'Upload Assistant/2.2 ({platform.system()} {platform.release()})'
        }
        params = {
            'api_token': self.config['TRACKERS'][self.tracker]['api_key'].strip()
        }

        if meta['debug'] is False:
            response = requests.post(url=self.upload_url, files=files, data=data, headers=headers, params=params)
            try:
                console.print(response.json())
                # adding torrent link to comment of torrent file
                t_id = response.json()['data'].split(".")[1].split("/")[3]
                await common.add_tracker_torrent(meta, self.tracker, self.source_flag, self.config['TRACKERS'][self.tracker].get('announce_url'), "https://oldtoons.world/torrents/" + t_id)
            except Exception:
                console.print("It may have uploaded, go check")
                return
        else:
            console.print("[cyan]Request Data:")
            console.print(data)
        open_torrent.close()

    async def handle_image_upload(self, meta, img_host_index=1, approved_image_hosts=None, file=None):
        if approved_image_hosts is None:
            approved_image_hosts = ['imgbox', 'imgbb', 'pixhost']

        url_host_mapping = {
            "ibb.co": "imgbb",
            "pixhost.to": "pixhost",
            "imgbox.com": "imgbox",
        }

        retry_mode = False
        images_reuploaded = False
        new_images_key = 'otw_images_key'
        discs = meta.get('discs', [])  # noqa F841
        filelist = meta.get('video', [])
        filename = meta['filename']
        path = meta['path']
        if isinstance(filelist, str):
            filelist = [filelist]

        multi_screens = int(self.config['DEFAULT'].get('screens', 6))
        base_dir = meta['base_dir']
        folder_id = meta['uuid']
        meta[new_images_key] = []

        screenshots_dir = os.path.join(base_dir, 'tmp', folder_id)
        all_screenshots = []

        for i, file in enumerate(filelist):
            filename_pattern = f"{filename}*.png"

            if meta['is_disc'] == "DVD":
                existing_screens = glob.glob(f"{meta['base_dir']}/tmp/{meta['uuid']}/{meta['discs'][0]['name']}-*.png")
            else:
                existing_screens = glob.glob(os.path.join(screenshots_dir, filename_pattern))

            if len(existing_screens) < multi_screens:
                if meta.get('debug'):
                    console.print("[yellow]The image host of existing images is not supported.")
                    console.print(f"[yellow]Insufficient screenshots found: generating {multi_screens} screenshots.")
                if meta['is_disc'] == "BDMV":
                    try:
                        disc_screenshots(meta, filename, meta['bdinfo'], folder_id, base_dir, meta.get('vapoursynth', False), [], meta.get('ffdebug', False), multi_screens, True)
                    except Exception as e:
                        print(f"Error during BDMV screenshot capture: {e}")
                elif meta['is_disc'] == "DVD":
                    try:
                        dvd_screenshots(
                            meta, 0, None, True
                        )
                    except Exception as e:
                        print(f"Error during DVD screenshot capture: {e}")
                else:
                    try:
                        screenshots(
                            path, filename, meta['uuid'], base_dir, meta, multi_screens, True, None)
                    except Exception as e:
                        print(f"Error during generic screenshot capture: {e}")

                if meta['is_disc'] == "DVD":
                    existing_screens = glob.glob(f"{meta['base_dir']}/tmp/{meta['uuid']}/{meta['discs'][0]['name']}-*.png")
                else:
                    existing_screens = glob.glob(os.path.join(screenshots_dir, filename_pattern))

            all_screenshots.extend(existing_screens)

        if not all_screenshots:
            console.print("[red]No screenshots were generated or found. Please check the screenshot generation process.")
            return [], True, images_reuploaded

        if not meta.get('skip_imghost_upload', False):
            uploaded_images = []
            while True:
                current_img_host_key = f'img_host_{img_host_index}'
                current_img_host = self.config.get('DEFAULT', {}).get(current_img_host_key)

                if not current_img_host:
                    console.print("[red]No more image hosts left to try.")
                    return

                if current_img_host not in approved_image_hosts:
                    console.print(f"[red]Your preferred image host '{current_img_host}' is not supported at OTW, trying next host.")
                    retry_mode = True
                    images_reuploaded = True
                    img_host_index += 1
                    continue
                else:
                    meta['imghost'] = current_img_host
                    console.print(f"[green]Uploading to approved host '{current_img_host}'.")
                    break

            uploaded_images, _ = upload_screens(
                meta, multi_screens, img_host_index, 0, multi_screens,
                all_screenshots, {new_images_key: meta[new_images_key]}, retry_mode
            )

            if uploaded_images:
                meta[new_images_key] = uploaded_images

            if meta['debug']:
                for image in uploaded_images:
                    console.print(f"[debug] Response in upload_image_task: {image['img_url']}, {image['raw_url']}, {image['web_url']}")

            for image in meta.get(new_images_key, []):
                raw_url = image['raw_url']
                parsed_url = urlparse(raw_url)
                hostname = parsed_url.netloc
                mapped_host = self.match_host(hostname, url_host_mapping.keys())
                mapped_host = url_host_mapping.get(mapped_host, mapped_host)

                if mapped_host not in approved_image_hosts:
                    console.print(f"[red]Unsupported image host detected in URL '{raw_url}'. Please use one of the approved image hosts.")
                    return meta[new_images_key], True, images_reuploaded  # Trigger retry_mode if switching hosts

            if all(
                url_host_mapping.get(
                    self.match_host(urlparse(image['raw_url']).netloc, url_host_mapping.keys()),
                    self.match_host(urlparse(image['raw_url']).netloc, url_host_mapping.keys()),
                ) in approved_image_hosts
                for image in meta[new_images_key]
            ):

                return meta[new_images_key], False, images_reuploaded
        else:
            return meta[new_images_key], False, images_reuploaded

    async def search_existing(self, meta, disctype):
        if not any(genre in meta['genres'] for genre in ['Animation', 'Family']):
            console.print('[bold red]This content is not allowed at OTW.')
            meta['skipping'] = "OTW"
            return
        disallowed_keywords = {'XXX', 'Erotic', 'Porn', 'Hentai', 'Adult Animation', 'Orgy'}
        if any(keyword.lower() in disallowed_keywords for keyword in map(str.lower, meta['keywords'])):
            console.print('[bold red]Adult animation not allowed at OTW.')
            meta['skipping'] = "RTF"
            return []
        dupes = []
        console.print("[yellow]Searching for existing torrents on OTW...")
        params = {
            'api_token': self.config['TRACKERS'][self.tracker]['api_key'].strip(),
            'tmdbId': meta['tmdb'],
            'categories[]': await self.get_cat_id(meta['category']),
            'types[]': await self.get_type_id(meta['type']),
            'resolutions[]': await self.get_res_id(meta['resolution']),
            'name': ""
        }
        if meta.get('edition', "") != "":
            params['name'] = params['name'] + f" {meta['edition']}"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(url=self.search_url, params=params)
                if response.status_code == 200:
                    data = response.json()
                    for each in data['data']:
                        result = [each][0]['attributes']['name']
                        dupes.append(result)
                else:
                    console.print(f"[bold red]Failed to search torrents. HTTP Status: {response.status_code}")
        except httpx.TimeoutException:
            console.print("[bold red]Request timed out after 5 seconds")
        except httpx.RequestError as e:
            console.print(f"[bold red]Unable to search for existing torrents: {e}")
        except Exception as e:
            console.print(f"[bold red]Unexpected error: {e}")
            await asyncio.sleep(5)

        return dupes
