# -*- coding: utf-8 -*-
import aiofiles
import bencodepy
import httpx
import os
import re
from bs4 import BeautifulSoup
from src.bbcode import BBCODE
from src.console import console
from src.cookie_auth import CookieValidator, CookieAuthUploader
from src.get_desc import DescriptionBuilder


class IPT:
    def __init__(self, config):
        self.config = config
        self.cookie_validator = CookieValidator(config)
        self.cookie_auth_uploader = CookieAuthUploader(config)
        self.tracker = 'IPT'
        self.source_flag = 'IPTorrents'
        self.base_url = 'https://iptorrents.com'
        self.torrent_url = 'https://iptorrents.com/torrent.php?id='
        self.session = httpx.AsyncClient(headers={
            'User-Agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:144.0) Gecko/20100101 Firefox/144.0"
        }, timeout=30)
        self.banned_groups = [
            "1337x", "3DM", "3dtorrents", "ali213", "AreaFiles", "BD25", "BlackBox", "BLuBits",
            "bluhd.org", "BTN", "BTNet", "Catalyst RG", "CBUT", "CHDBits", "CHDTV.Net", "CINEMANIA",
            "CorePack", "CorePacks", "CPG", "DADDY", "Digital Desi Releasers", "DDR", "DLLHits", "DLBR",
            "DRIG", "DVDSEED", "EncodeKing", "FGT", "filelist.ro", "flashtorrents", "Ganool", "HD4FUN",
            "HDAccess", "HDChina", "HDGeek", "HDME", "HDRoad", "HDStar", "HDTime", "HDTurk", "HDWing",
            "h33t", "HorribleSubs", "hqsource.org", "IWStream", "Kingdom-KVCD", "MeGaHeRTZ", "MkvCage",
            "MVGroup.org", "MYEGY", "nosTEAM", "os4world", "OntohinBD", "Pimp4003", "Projekt-Revolution",
            "ps3gameroom", "PTP", "RARBG/RBG", "RLS", "RLSM", "Shaanig", "SHOWSCEN", "SiRiUs sHaRe",
            "SFS-RG", "SFS", "SilverTorrents", "SpaceHD", "The Wolfs Den", "TPTB", "TTG", "UNKNOWN",
            "X360ISO", "YIFY", "zombiRG"
        ]

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

        # TV
        title, episode_image, episode_overview = await builder.get_tv_info(meta, self.tracker, resize=True)
        if episode_overview:
            desc_parts.append(f'[center]{title}[/center]')

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
                screenshots_block += f"[url={image['web_url']}][img]{image['img_url']}[/img][/url] "
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
        self.session.cookies = await self.cookie_validator.load_session_cookies(meta, self.tracker)
        dupes = []
        cat_id = 72 if meta['category'] == 'MOVIE' else 73 if meta['category'] == 'TV' else 0
        if not cat_id:
            return dupes
        search_url = f"{self.base_url}/t?72=&q={meta['title']}"

        try:
            response = await self.session.get(search_url, follow_redirects=True)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            torrent_table = soup.find('table', id='torrents')

            if torrent_table:
                rows = torrent_table.find('tbody').find_all('tr')

                for row in rows:
                    cells = row.find_all('td')

                    if len(cells) > 5:
                        name_cell = cells[1]
                        link_tag = name_cell.find('a', class_='hv')

                        if link_tag:
                            name = link_tag.get_text(strip=True)
                            torrent_path = link_tag.get('href')
                            torrent_link = f"{self.base_url}{torrent_path}"
                            size = cells[5].get_text(strip=True)

                            duplicate_entry = {
                                'name': name,
                                'size': size,
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
        movie_dvd_r = 6
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
            else:
                if meta.get('original_language') and meta.get('original_language') != 'en':
                    return tv_non_english
            if is_disc:
                if is_disc == 'BDMV':
                    return tv_bd
                if is_disc == 'DVD':
                    return tv_dvd_r
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

    async def get_name(self, meta):
        if meta.get('scene_name', ''):
            name = meta.get('scene_name')
        else:
            name = meta.get('clean_name')

        replacements = {
            '3DAccess': '3DA',
            'AreaFiles': 'AF',
            'BeyondHD': 'BHD',
            'Blackcat': 'Blackcat',
            'Blu-Bits': 'BluHD',
            'Bluebird': 'BB',
            'BlueEvolution': 'BluEvo',
            'Chdbits': 'CHD',
            'CtrlHD': 'CtrlHD',
            'HDAccess': 'HDA',
            'HDChina': 'HDC',
            'HDClub': 'HDCL',
            'HDGeek': 'HDG',
            'HDRoad': 'HDR',
            'HDStar': 'HDS',
            'HDWing': 'HDW',
            'ExtraTorrent': 'ETRG',
            'IWStream': 'IWS',
            'Kingdom-KVCD': 'KVCD',
            'MVGroup': 'MVG',
            'Projekt-Revolution': 'Projekt',
            'PublicHD': 'PHD',
            'SpaceHD': 'SHD',
            'ThumperDC': 'TDC',
            'TrollHD': 'TrollHD',
            'TheWolfsDen': 'TWD',
        }

        for key, value in replacements.items():
            if key in name:
                name = name.replace(key, value)

        name = name.replace("'", "").replace('"', "")

        if meta.get('scene', False):
            if '[NO RAR]' not in name.upper():
                name += ' [NO RAR]'

        name = re.sub(r"\s{2,}", " ", name)

        return name

    async def get_is_freeleech(self, meta):
        torrent_path = f"{meta['base_dir']}/tmp/{meta['uuid']}/BASE.torrent"
        if not os.path.exists(torrent_path):
            return False

        try:
            async with aiofiles.open(torrent_path, 'rb') as f:
                torrent_data = await f.read()
            metainfo = bencodepy.decode(torrent_data)
            info = metainfo.get(b'info', {})
            total_size = 0
            if b'files' in info:
                for file_info in info[b'files']:
                    total_size += file_info.get(b'length', 0)
            else:
                total_size = info.get(b'length', 0)
            size_gb = total_size / (1024 ** 3)
            return size_gb >= 8
        except Exception as e:
            console.print(f"[bold red]Error reading torrent file for size check on {self.tracker}: {e}[/bold red]")
            return False

    async def get_data(self, meta):
        data = {
            'name': meta['name'],
            'descr': await self.generate_description(meta),
            'type': await self.get_category_id(meta),
        }

        if await self.get_is_freeleech(meta):
            data['freeleech'] = 'on'

        # Anon
        anon = not (meta['anon'] == 0 and not self.config['TRACKERS'][self.tracker].get('anon', False))
        if anon:
            data.update({
                'anonymous': 'on'
            })

        return data

    async def upload(self, meta, disctype):
        self.session.cookies = await self.cookie_validator.load_session_cookies(meta, self.tracker)
        data = await self.get_data(meta)

        upload = await self.cookie_auth_uploader.handle_upload(
            meta=meta,
            tracker=self.tracker,
            source_flag=self.source_flag,
            torrent_url=self.torrent_url,
            data=data,
            torrent_field_name='file',
            torrent_name=await self.get_name(meta),
            upload_cookies=self.session.cookies,
            upload_url=f"{self.base_url}/takeupload.php",
            error_text="Upload failed!",
            id_pattern=r'download\.php/(\d+)/'
        )

        if upload and self.config['TRACKERS'][self.tracker]['force_data']:
            await self.edit_post_upload(meta)

        return

    async def edit_post_upload(self, meta):
        torrent_id = meta["tracker_status"][self.tracker]["torrent_id"]
        data = {
            'name': meta['name'],
            'descr': await self.generate_description(meta),
            'type': await self.get_category_id(meta),
            'imdb_id': str(meta.get('imdb_info', {}).get('imdbID', '')),
            'id': torrent_id,
        }

        edit_url = f"https://iptorrents.com/t/{torrent_id}/edit"

        response = await self.session.post(edit_url, data=data)
        if not response.status_code == 302:
            meta["tracker_status"][self.tracker]["status_message"] += " Failed to edit torrent."
