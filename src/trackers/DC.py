# -*- coding: utf-8 -*-
import aiofiles
import httpx
from src.console import console
from src.get_desc import DescriptionBuilder
from src.rehostimages import check_hosts
from src.trackers.COMMON import COMMON


class DC:
    def __init__(self, config):
        self.config = config
        self.common = COMMON(config)
        self.tracker = 'DC'
        self.source_flag = 'DigitalCore.club'
        self.base_url = 'https://digitalcore.club'
        self.torrent_url = f'{self.base_url}/torrent/'
        self.api_base_url = f'{self.base_url}/api/v1'
        self.banned_groups = ['']
        self.api_key = self.config['TRACKERS'][self.tracker].get('api_key')
        self.passkey = self.config['TRACKERS'][self.tracker].get('passkey')
        self.announce_list = [
            f'https://tracker.digitalcore.club/announce/{self.passkey}',
            f'https://trackerprxy.digitalcore.club/announce/{self.passkey}'
        ]
        self.session = httpx.AsyncClient(headers={
            'X-API-KEY': self.api_key
        }, timeout=30.0)

    async def mediainfo(self, meta):
        if meta.get('is_disc') == 'BDMV':
            mediainfo = await self.common.get_bdmv_mediainfo(meta, remove=['File size', 'Overall bit rate'])
        else:
            mi_path = f"{meta['base_dir']}/tmp/{meta['uuid']}/MEDIAINFO_CLEANPATH.txt"
            with open(mi_path, 'r', encoding='utf-8') as f:
                mediainfo = f.read()

        return mediainfo

    async def generate_description(self, meta):
        builder = DescriptionBuilder(self.config)
        desc_parts = []

        # Custom Header
        desc_parts.append(await builder.get_custom_header(self.tracker))

        # Logo
        logo, logo_size = await builder.get_logo_section(meta, self.tracker)
        if logo and logo_size:
            desc_parts.append(f'[center][img={logo_size}]{logo}[/img][/center]')

        # TV
        title, episode_image, episode_overview = await builder.get_tv_info(meta, self.tracker)
        if episode_overview:
            desc_parts.append(f'[center]{title}[/center]')

            if episode_image:
                desc_parts.append(f"[center][img=300]{episode_image}[/img][/center]")

            desc_parts.append(f'[center]{episode_overview}[/center]')

        # File information
        desc_parts.append(await builder.get_bdinfo_section(meta))

        # NFO
        if meta.get('description_nfo_content', ''):
            desc_parts.append(f"[nfo]{meta.get('description_nfo_content')}[/nfo]")

        # User description
        desc_parts.append(await builder.get_user_description(meta))

        # Screenshot Header
        desc_parts.append(await builder.screenshot_header(self.tracker))

        # Screenshots
        if f'{self.tracker}_images_key' in meta:
            images = meta[f'{self.tracker}_images_key']
        else:
            images = meta['image_list']
        if images:
            screenshots_block = '[center]\n'
            for i, image in enumerate(images, start=1):
                img_url = image['img_url']
                web_url = image['web_url']
                screenshots_block += f'[url={web_url}][img=350]{img_url}[/img][/url] '
                # limits to 2 screens per line, as the description box is small
                if i % 2 == 0:
                    screenshots_block += '\n'
            screenshots_block += '\n[/center]'
            desc_parts.append(screenshots_block)

        # Tonemapped Header
        desc_parts.append(await builder.get_tonemapped_header(meta, self.tracker))

        # Signature
        desc_parts.append(f"[center][url=https://github.com/Audionut/Upload-Assistant]{meta['ua_signature']}[/url][/center]")

        description = '\n\n'.join(part for part in desc_parts if part.strip())

        from src.bbcode import BBCODE
        bbcode = BBCODE()
        description = description.replace('[user]', '').replace('[/user]', '')
        description = description.replace('[align=left]', '').replace('[/align]', '')
        description = description.replace('[right]', '').replace('[/right]', '')
        description = description.replace('[align=right]', '').replace('[/align]', '')
        description = bbcode.remove_sup(description)
        description = bbcode.remove_sub(description)
        description = description.replace('[alert]', '').replace('[/alert]', '')
        description = description.replace('[note]', '').replace('[/note]', '')
        description = description.replace('[hr]', '').replace('[/hr]', '')
        description = description.replace('[h1]', '[u][b]').replace('[/h1]', '[/b][/u]')
        description = description.replace('[h2]', '[u][b]').replace('[/h2]', '[/b][/u]')
        description = description.replace('[h3]', '[u][b]').replace('[/h3]', '[/b][/u]')
        description = description.replace('[ul]', '').replace('[/ul]', '')
        description = description.replace('[ol]', '').replace('[/ol]', '')
        description = bbcode.convert_named_spoiler_to_normal_spoiler(description)
        description = bbcode.convert_comparison_to_centered(description, 1000)
        description = description.strip()
        description = bbcode.remove_extra_lines(description)

        async with aiofiles.open(f"{meta['base_dir']}/tmp/{meta['uuid']}/[{self.tracker}]DESCRIPTION.txt", 'w', encoding='utf-8') as description_file:
            await description_file.write(description)

        return description

    async def get_category_id(self, meta):
        resolution = meta.get('resolution', '')
        category = meta.get('category', '')
        is_disc = meta.get('is_disc', '')
        tv_pack = meta.get('tv_pack', '')
        sd = meta.get('sd', '')

        if is_disc == 'BDMV':
            if resolution == '1080p' and category == 'MOVIE':
                return 3
            elif resolution == '2160p' and category == 'MOVIE':
                return 38
            elif category == 'TV':
                return 14
        if is_disc == 'DVD':
            if category == 'MOVIE':
                return 1
            elif category == 'TV':
                return 11
        if category == 'TV' and tv_pack == 1:
            return 12
        if sd == 1:
            if category == 'MOVIE':
                return 2
            elif category == 'TV':
                return 10
        category_map = {
            'MOVIE': {'2160p': 4, '1080p': 6, '1080i': 6, '720p': 5},
            'TV': {'2160p': 13, '1080p': 9, '1080i': 9, '720p': 8},
        }
        if category in category_map:
            return category_map[category].get(resolution)
        return None

    async def search_existing(self, meta, results):
        imdb_id = meta.get('imdb_info', {}).get('imdbID')
        if not imdb_id:
            console.print(f'[bold yellow]Cannot perform search on {self.tracker}: IMDb ID not found in metadata.[/bold yellow]')
            return []

        search_url = f'{self.api_base_url}/torrents'
        search_params = {'searchText': imdb_id}
        search_results = []
        dupes = []
        try:
            response = await self.session.get(search_url, params=search_params, headers=self.session.headers, timeout=15)
            response.raise_for_status()

            if response.text and response.text != '[]':
                search_results = response.json()
                results = search_results
                if search_results and isinstance(search_results, list):
                    should_continue = await self.get_title(meta, results)
                    if not should_continue:
                        print('An UNRAR duplicate of this specific release already exists on site.')
                        meta['skipping'] = f'{self.tracker}'
                        return

                    for each in search_results:
                        name = each.get('name')
                        torrent_id = each.get('id')
                        size = each.get('size')
                        torrent_link = f'{self.torrent_url}{torrent_id}/' if torrent_id else None
                        dupe_entry = {
                            'name': name,
                            'size': size,
                            'link': torrent_link
                        }
                        dupes.append(dupe_entry)

                    return dupes

        except Exception as e:
            console.print(f'[bold red]Error searching for IMDb ID {imdb_id} on {self.tracker}: {e}[/bold red]')

        return []

    async def get_title(self, meta, results):
        results = results
        is_scene = bool(meta.get('scene_name'))
        base_name = meta['scene_name'] if is_scene else meta['uuid']

        needs_unrar_tag = False

        if results:
            upload_title = {meta['uuid']}
            if is_scene:
                upload_title.add(meta['scene_name'])

            matching_titles = [
                t for t in results
                if t.get('name') in upload_title
            ]

            if matching_titles:
                unrar_version_exists = any(t.get('unrar', 0) != 0 for t in matching_titles)

                if unrar_version_exists:
                    return False
                else:
                    console.print(f'[bold yellow]Found a RAR version of this release on {self.tracker}. Appending [UNRAR] to filename.[/bold yellow]')
                    needs_unrar_tag = True

        if needs_unrar_tag:
            upload_base_name = meta['scene_name'] if is_scene else meta['uuid']
            title = f'{upload_base_name} [UNRAR].torrent'
        else:
            title = f'{base_name}.torrent'

        container = '.' + meta.get('container', 'mkv')
        title = title.replace(container, '').replace(container.upper(), '')

        return title

    async def fetch_data(self, meta):
        approved_image_hosts = ['imgbox', 'imgbb', 'bhd', 'imgur', 'postimg', 'digitalcore']
        url_host_mapping = {
            'ibb.co': 'imgbb',
            'imgbox.com': 'imgbox',
            'beyondhd.co': 'bhd',
            'imgur.com': 'imgur',
            'postimg.cc': 'postimg',
            'digitalcore.club': 'digitalcore'
        }
        await check_hosts(meta, self.tracker, url_host_mapping=url_host_mapping, img_host_index=1, approved_image_hosts=approved_image_hosts)

        anon = '1' if meta['anon'] or self.config['TRACKERS'][self.tracker].get('anon', False) else '0'

        data = {
            'category': await self.get_category_id(meta),
            'imdbId': meta.get('imdb_info', {}).get('imdbID', ''),
            'nfo': await self.generate_description(meta),
            'mediainfo': await self.mediainfo(meta),
            'reqid': '0',
            'section': 'new',
            'frileech': '1',
            'anonymousUpload': anon,
            'p2p': '0',
            'unrar': '1',
        }

        return data

    async def upload(self, meta, results):
        await self.common.edit_torrent(meta, self.tracker, self.source_flag)
        data = await self.fetch_data(meta)
        title = await self.get_title(meta, results)
        status_message = ''
        torrent_id = ''

        if not meta.get('debug', False):
            upload_url = f'{self.api_base_url}/torrents/upload'
            torrent_path = f"{meta['base_dir']}/tmp/{meta['uuid']}/[{self.tracker}].torrent"

            with open(torrent_path, 'rb') as torrent_file:
                files = {'file': (title, torrent_file, 'application/x-bittorrent')}

                response = await self.session.post(upload_url, data=data, files=files, headers=self.session.headers, timeout=90)
                response.raise_for_status()
                status_message = response.json()

                if response.status_code == 200 and status_message.get('id'):
                    torrent_id = str(status_message.get('id', ''))
                    if torrent_id:
                        meta['tracker_status'][self.tracker]['torrent_id'] = torrent_id

                else:
                    console.print(f"{status_message.get('message', 'Unknown API error.')}")
                    meta['skipping'] = f"{self.tracker}"
                    return

        else:
            console.print(data)
            status_message = 'Debug mode enabled, not uploading'

        await self.common.add_tracker_torrent(meta, self.tracker, self.source_flag, self.announce_list, self.torrent_url + torrent_id + '/')

        meta['tracker_status'][self.tracker]['status_message'] = status_message
