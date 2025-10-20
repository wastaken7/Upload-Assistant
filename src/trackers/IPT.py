# -*- coding: utf-8 -*-
import aiofiles
import glob
import httpx
import os
import platform
import re
from src.cookie_auth import CookieValidator, CookieAuthUploader
from bs4 import BeautifulSoup
from src.bbcode import BBCODE
from src.console import console
from src.get_desc import DescriptionBuilder
from src.trackers.COMMON import COMMON


class IPT:
    def __init__(self, config):
        self.config = config
        self.cookie_validator = CookieValidator(config)
        self.cookie_auth_uploader = CookieAuthUploader(config)
        self.tracker = 'IPT'
        self.source_flag = 'IPTorrents'
        self.banned_groups = ['']
        self.base_url = 'https://iptorrents.com'
        self.torrent_url = 'https://iptorrents.com/torrent.php?id='
        self.announce = self.config['TRACKERS'][self.tracker]['announce_url']
        self.session = httpx.AsyncClient(headers={
            'User-Agent': f"Upload Assistant/2.3 ({platform.system()} {platform.release()})"
        }, timeout=30)

    async def validate_credentials(self, meta):
        self.session.cookies = await self.cookie_validator.load_session_cookies(meta, self.tracker)
        return await self.cookie_validator.cookie_validation(
            meta=meta,
            tracker=self.tracker,
            test_url=f'{self.base_url}/upload.php',
            success_text='Your announce url is',
        )

    async def generate_description(self, meta):
        builder = DescriptionBuilder(self.config)
        desc_parts = []

        # Custom Header
        desc_parts.append(await builder.get_custom_header(self.tracker))

        # Logo
        logo_resize_url = meta.get('tmdb_logo', '')
        if logo_resize_url:
            desc_parts.append(f"[center][img]https://image.tmdb.org/t/p/w300/{logo_resize_url}[/img][/center]")

        # TV
        title, episode_image, episode_overview = await builder.get_tv_info(meta, self.tracker, resize=True)
        if episode_overview:
            desc_parts.append(f'[center]{title}[/center]')

            if episode_image:
                desc_parts.append(f"[center][img]{episode_image}[/img][/center]")

            desc_parts.append(f'[center]{episode_overview}[/center]')

        # File information
        mediainfo = await builder.get_mediainfo_section(meta, self.tracker)
        if mediainfo:
            desc_parts.append(f'[pre]{mediainfo}[/pre]')

        bdinfo = await builder.get_bdinfo_section(meta)
        if bdinfo:
            desc_parts.append(f'[pre]{bdinfo}[/pre]')

        # User description
        desc_parts.append(await builder.get_user_description(meta))

        # Screenshot Header
        desc_parts.append(await builder.screenshot_header(self.tracker))

        # Screenshots
        images = meta.get('image_list', [])
        if images:
            screenshots_block = ''
            for image in images:
                screenshots_block += f"[url={image['web_url']}][img]{image['img_url']}[/img][/url]"
            desc_parts.append('[center]\n' + screenshots_block + '[/center]')

        # Tonemapped Header
        desc_parts.append(await builder.get_tonemapped_header(meta, self.tracker))

        description = '\n\n'.join(part for part in desc_parts if part.strip())

        bbcode = BBCODE()
        description = description.replace('[user]', '').replace('[/user]', '')
        description = description.replace('[align=left]', '').replace('[/align]', '')
        description = description.replace('[right]', '').replace('[/right]', '')
        description = description.replace('[align=right]', '').replace('[/align]', '')
        description = bbcode.remove_sub(description)
        description = bbcode.remove_sup(description)
        description = description.replace('[alert]', '').replace('[/alert]', '')
        description = description.replace('[note]', '').replace('[/note]', '')
        description = description.replace('[hr]', '').replace('[/hr]', '')
        description = description.replace('[h1]', '[u][b]').replace('[/h1]', '[/b][/u]')
        description = description.replace('[h2]', '[u][b]').replace('[/h2]', '[/b][/u]')
        description = description.replace('[h3]', '[u][b]').replace('[/h3]', '[/b][/u]')
        description = description.replace('[ul]', '').replace('[/ul]', '')
        description = description.replace('[ol]', '').replace('[/ol]', '')
        description = bbcode.remove_hide(description)
        description = bbcode.remove_img_resize(description)
        description = bbcode.convert_comparison_to_centered(description, 1000)
        description = bbcode.remove_spoiler(description)
        description = bbcode.remove_extra_lines(description)

        async with aiofiles.open(f"{meta['base_dir']}/tmp/{meta['uuid']}/[{self.tracker}]DESCRIPTION.txt", 'w', encoding='utf-8') as description_file:
            await description_file.write(description)

        return description

    async def search_existing(self, meta, disctype):
        dupes = []
        imdb_id = meta.get('imdb', '')
        if imdb_id == '0':
            console.print(f'IMDb ID not found, cannot search for duplicates on {self.tracker}.')
            return dupes

        search_url = f'{self.base_url}/index.php?'

        params = {
            'page': 'torrents',
            'search': imdb_id,
            'active': '0',
            'options': '2'
        }

        try:
            response = await self.session.get(search_url, params=params)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')

            all_tables = soup.find_all('table', class_='lista')

            torrent_rows = []

            for table in all_tables:
                recommend_header = table.find('td', class_='block', string='Our Team Recommend')
                if recommend_header:
                    continue

                rows_in_table = table.select('tr:has(td.lista)')
                torrent_rows.extend(rows_in_table)

            for row in torrent_rows:
                name_tag = row.select_one('td:nth-child(2) > a[href*="page=torrent-details&id="]')
                name = name_tag.get_text(strip=True) if name_tag else 'Unknown Name'

                link_tag = name_tag
                torrent_link = None
                if link_tag and 'href' in link_tag.attrs:
                    torrent_link = f'{self.base_url}/{link_tag["href"]}'

                duplicate_entry = {
                    'name': name,
                    'size': None,
                    'link': torrent_link
                }
                dupes.append(duplicate_entry)

        except Exception as e:
            console.print(f'[bold red]Error searching for duplicates on {self.tracker}: {e}[/bold red]')

        return dupes

    async def get_category_id(self, meta):
        resolution = meta.get('resolution')
        category = meta.get('category')
        type_ = meta.get('type')
        is_disc = meta.get('is_disc')
        genres = meta.get('genres', '').lower()
        source = meta.get('source', '').lower()

        # TV
        tv_web_dl = 22
        tv_x265 = 99
        tv_xvid = 4
        tv_480p = 78
        tv_packs = 65
        tv_x264 = 5
        tv_bd = 23
        documentaries = 26
        sports = 55
        tv_sd_x264 = 79
        tv_dvd_rip = 25
        tv_non_english = 82
        tv_packs_non_english = 83
        tv_dvd_r = 24

        # Movies
        movie_hd_bluray = 48
        movie_web_dl = 20
        movie_4k = 101
        movie_xvid = 7
        movie_x265 = 100
        movie_non_english = 38
        movie_bd_r = 89
        movie_bd_rip = 90
        movie_packs = 68
        movie_dvd_r = 6
        movie_mp4 = 62
        movie_3d = 87
        movie_kids = 54
        movie_480p = 77
        movie_cam = 96

        if 'documentary' in genres:
            return documentaries
        if 'sport' in genres:
            return sports

        if category == 'MOVIE':
            if is_disc == 'BDMV':
                return movie_bd_r
            if is_disc == 'DVD':
                return movie_dvd_r
            if resolution == '2160p':
                return movie_4k
            if '3D' in meta.get('3d', ''):
                return movie_3d
            if meta.get('video_codec', '').lower() == 'x265':
                return movie_x265
            if type_ in ('WEBDL', 'WEBRIP'):
                return movie_web_dl
            if source == 'bluray' and resolution in ('1080p', '720p'):
                return movie_hd_bluray
            if type_ == 'BDRIP':
                return movie_bd_rip
            if resolution == '480p':
                return movie_480p
            if type_ == 'XVID':
                return movie_xvid
            if source in ('CAM', 'TS', 'TC'):
                return movie_cam
            if 'kids' in genres or 'family' in genres:
                return movie_kids
            if meta.get('original_language') and meta.get('original_language') != 'en':
                return movie_non_english
            return movie_hd_bluray

        elif category == 'TV':
            if meta.get('tv_pack', False):
                if meta.get('original_language') and meta.get('original_language') != 'en':
                    return tv_packs_non_english
                return tv_packs
            if meta.get('video_codec', '').lower() == 'x265':
                return tv_x265
            if type_ in ('WEBDL', 'WEBRIP'):
                return tv_web_dl
            if type_ == 'DVDRIP':
                return tv_dvd_rip
            if resolution == '480p':
                return tv_480p
            if type_ == 'XVID':
                return tv_xvid
            return tv_x264

    async def get_data(self, meta):
        data = {
            'name': meta['name'],
            'descr': await self.generate_description(meta),
            'type': await self.get_category_id(meta),
        }

        # Anon
        anon = not (meta['anon'] == 0 and not self.config['TRACKERS'][self.tracker].get('anon', False))
        if anon:
            data.update({
                'anonymous': 'true'
            })
        else:
            data.update({
                'anonymous': 'false'
            })

        return data

    async def upload(self, meta, disctype):
        self.session.cookies = await self.cookie_validator.load_session_cookies(meta, self.tracker)
        data = await self.get_data(meta)

        await self.cookie_auth_uploader.handle_upload(
            meta=meta,
            tracker=self.tracker,
            source_flag=self.source_flag,
            torrent_url=self.torrent_url,
            data=data,
            torrent_field_name='file',
            upload_cookies=self.session.cookies,
            upload_url="https://iptorrents.com/takeupload.php",
            hash_is_id=True,
            success_text="download.php?id=",
        )

        return
