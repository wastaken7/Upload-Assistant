from src.console import console
import aiofiles
import httpx
import platform
from urllib.parse import urlparse
from src.get_desc import DescriptionBuilder


class YGG:
    def __init__(self, config):
        self.config = config
        self.tracker = 'YGG'
        self.source_flag = 'YGG'

        url_from_config = self.config['TRACKERS'][self.tracker].get('url')
        parsed_url = urlparse(url_from_config)
        self.config_url = parsed_url.netloc
        self.base_url = f'https://{self.config_url}'

        self.upload_url = f'{self.base_url}/user/upload_torrent_action'
        self.search_url = f'{self.base_url}/engine/search?'
        self.torrent_url = f'{self.base_url}/torrent/'
        self.announce_url = self.config['TRACKERS'][self.tracker]['announce_url']
        self.banned_groups = []
        self.session = httpx.AsyncClient(headers={
            'User-Agent': f'Upload Assistant ({platform.system()} {platform.release()})'
        }, timeout=60.0)
        pass

    async def validate_credentials(self, meta):
        console.print("[yellow]YGG is not yet supported for validating credentials.")
        return False

    async def login(self, meta):
        auth_url = f'{self.base_url}/auth/process_login'
        user = self.config['TRACKERS'][self.tracker].get('username')
        password = self.config['TRACKERS'][self.tracker].get('password')
        data = {'id': user, 'pass': password}
        try:
            response = await self.session.post(auth_url, data=data)
            response.raise_for_status()

            if 'Déconnexion' in response.text:
                console.print(f'{self.tracker}: Successfully logged in.')
                return True
            else:
                console.print(f'{self.tracker}: Login failed. Check your username and password.')
                return False
        except httpx.TimeoutException:
            console.print(f'{self.tracker}: Error in {self.tracker}: Timeout while trying to log in.')
            return False
        except httpx.HTTPStatusError as e:
            console.print(f'{self.tracker}: HTTP error during login for {self.tracker}: Status {e.response.status_code}.')
            return False
        except httpx.RequestError as e:
            console.print(f'{self.tracker}: Network error during login for {self.tracker}: {e.__class__.__name__}.')
            return False
        except Exception as e:
            console.print(f'{self.tracker}: Unexpected error during login: {e}')

        return False

    async def search_existing(self, meta, disctype):
        console.print("[yellow]YGG is not yet supported for searching existing torrents.")
        return []

    async def get_additional_checks(self, meta):
        if await self.get_category_id(meta) == 0:
            console.print(f'[bold red]{self.tracker}: Category not supported. Skipping upload...[/bold red]')
            meta['skipping'] = f'{self.tracker}'
            return False
        if await self.get_type_id(meta) == 0:
            console.print(f'[bold red]{self.tracker}: Type not supported. Skipping upload...[/bold red]')
            meta['skipping'] = f'{self.tracker}'
            return False
        if await self.get_quality(meta) == 0:
            console.print(f'[bold red]{self.tracker}: Quality not supported. Skipping upload...[/bold red]')
            meta['skipping'] = f'{self.tracker}'
            return False

        return True

    async def get_category_id(self, meta):
        return 2145

    async def get_type_id(self, meta):
        animation = 2178
        animation_series = 2179
        documentary = 2181
        tv_show = 2182
        movie = 2183
        tv_series = 2184

        if meta['category'] == 'MOVIE':
            if meta.get('anime', False):
                return animation
            return movie
        elif meta['category'] == 'TV':
            if meta.get('anime', False):
                return animation_series
            return tv_series

        meta_keywords_list = [k.strip() for k in meta.get('keywords', "").split(',')]
        if any(keyword in meta_keywords_list for keyword in ['documentary', 'biography']):
            return documentary
        if any(keyword in meta_keywords_list for keyword in ['tv show', 'talk show', 'game show']):
            return tv_show

        return 0

    async def get_name(self, meta):
        return meta['uuid']

    async def get_description(self, meta):
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
            desc_parts.append(f'[center]{episode_overview}[/center]')

        # User description
        desc_parts.append(await builder.get_user_description(meta))

        # Screenshot Header
        desc_parts.append(await builder.screenshot_header(self.tracker))

        # Screenshots
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
        description = bbcode.convert_named_spoiler_to_normal_spoiler(description)
        description = bbcode.convert_comparison_to_centered(description, 1000)
        description = description.strip()
        description = bbcode.remove_extra_lines(description)

        async with aiofiles.open(f"{meta['base_dir']}/tmp/{meta['uuid']}/[{self.tracker}]DESCRIPTION.txt", 'w', encoding='utf-8') as description_file:
            await description_file.write(description)

        return description

    async def get_files(self, meta):
        nfo_content = ""
        # Nfo is MEDIAINFO_CLEANPATH.txt or BD_SUMMARY_00.txt
        if meta.get('is_disc') == 'BDMV':
            nfo_path = f"{meta['base_dir']}/tmp/{meta['uuid']}/BD_SUMMARY_00.txt"
        else:
            nfo_path = f"{meta['base_dir']}/tmp/{meta['uuid']}/MEDIAINFO_CLEANPATH.txt"
        async with aiofiles.open(nfo_path, 'r', encoding='utf-8') as f:
            nfo_content = await f.read()

        return {'nfo_file': (f"[{self.tracker}]DESCRIPTION.nfo", nfo_content, 'text/plain')}

    async def get_language(self, meta):
        english = 1  # Only when there is no French dubbing or subtitles
        french_truefrench = 2  # Only when there is French dubbing and it is BDMV
        silent = 3  # search for the keyword silent
        multi_french_included = 4  # when there is French dubbing and other languages as well
        multi_quebecois_included = 5  # when there is Canadian French dubbing and other languages as well
        quebecois_french = 6  # only when there is only Canadian French
        vfstfr = 7  # French SDH subtitles
        vostfr = 8  # French subtitles, but no dubbing

        results = []

        has_fr_dub = 'French' in meta.get('audio_languages', [])
        has_fr_sub = 'French' in meta.get('subtitle_languages', [])

        mediainfo_tracks = meta.get('mediainfo', {}).get('media', {}).get('track', [])
        has_can_fr_dub = any(
            'Canadian' in track.get('Title', '') and track.get('@type') == 'Audio'
            for track in mediainfo_tracks
        )
        has_can_fr_sub = any(
            'Canadian' in track.get('Title', '') and track.get('@type') == 'Text'
            for track in mediainfo_tracks
        )

        # French dubbing and subtitles
        if has_fr_dub and has_fr_sub:
            if meta.get('is_disc') == 'BDMV':
                results.append(french_truefrench)
            else:
                results.append(multi_french_included)

        # Canadian French dubbing and subtitles
        if has_can_fr_dub and has_can_fr_sub:
            if meta.get('is_disc') == 'BDMV':
                results.append(quebecois_french)
            else:
                results.append(multi_quebecois_included)

        # Only French subtitles (no dub)
        if has_fr_sub and not has_fr_dub:
            results.append(vostfr)

        # Only French dubbing (no subs)
        if has_fr_dub and not has_fr_sub:
            results.append(multi_french_included)

        # Silent keyword
        if 'silent' in meta.get('keywords', []):
            results.append(silent)

        # French SDH subtitles
        if has_fr_sub:
            if any('SDH' in track.get('Title', '') for track in mediainfo_tracks):
                results.append(vfstfr)

        # Fallback: English only
        if not results:
            results.append(english)

        return results

    async def get_quality(self, meta):
        bdrip_brrip = 1        # BDrip/BRrip [Rip SD (non-HD) from Bluray or HDrip]
        bluray_4k = 2          # Bluray 4K [Full or Remux]
        bluray_full = 3        # Bluray [Full]
        bluray_remux = 4       # Bluray [Remux]
        dvd_r5 = 5             # DVD-R 5 [DVD < 4.37GB]
        dvd_r9 = 6             # DVD-R 9 [DVD > 4.37GB]
        dvdrip = 7             # DVDrip [Ripped from DVD-R]
        hdrip_1080 = 8         # HDrip 1080 [Rip HD from Bluray]
        hdrip_4k = 9           # HDrip 4k [Rip HD 4k from 4k source]
        hdrip_720 = 10         # HDrip 720 [Rip HD from Bluray]
        tvrip = 11             # TVrip [Rip SD (non-HD) from HD/SD TV source]
        tvrip_hd_1080 = 12     # TVripHD 1080 [Rip HD from Source TV HD]
        tvrip_hd_4k = 13       # TvripHD 4k [Rip HD 4k from Source TV 4k]
        tvrip_hd_720 = 14      # TVripHD 720 [Rip HD from Source TV HD]
        vcd_svcd_vhsrip = 15   # VCD/SVCD/VHSrip
        web_dl = 16            # Web-Dl
        web_dl_1080 = 17       # Web-Dl 1080
        web_dl_4k = 18         # Web-Dl 4K
        web_dl_720 = 19        # Web-Dl 720
        webrip = 20            # WEBrip
        webrip_1080 = 21       # WEBrip 1080
        webrip_4k = 22         # WEBrip 4K
        webrip_720 = 23        # WEBrip 720

        source_type = meta.get('type', '').lower()
        resolution = meta.get('resolution', '').lower()
        is_disc = meta.get('is_disc')

        if is_disc == 'BDMV':
            if resolution == '2160p':
                return bluray_4k
            return bluray_full
        elif is_disc == 'DVD':
            if meta.get('dvd_size') == 'DVD5':
                return dvd_r5
            return dvd_r9

        if source_type == 'remux':
            if resolution == '2160p':
                return bluray_4k
            return bluray_remux

        if source_type in ('bdrip', 'brrip', 'encode'):
            if resolution == '1080p':
                return hdrip_1080
            if resolution == '720p':
                return hdrip_720
            if resolution == '2160p':
                return hdrip_4k
            return bdrip_brrip

        if source_type == 'dvdrip':
            return dvdrip

        if source_type in ('hdtv', 'pdtv', 'sdtv', 'tvrip'):
            if resolution == '2160p':
                return tvrip_hd_4k
            if resolution == '1080p':
                return tvrip_hd_1080
            if resolution == '720p':
                return tvrip_hd_720
            return tvrip

        if source_type in ('web-dl', 'webdl'):
            if resolution == '2160p':
                return web_dl_4k
            if resolution == '1080p':
                return web_dl_1080
            if resolution == '720p':
                return web_dl_720
            return web_dl

        if source_type == 'webrip':
            if resolution == '2160p':
                return webrip_4k
            if resolution == '1080p':
                return webrip_1080
            if resolution == '720p':
                return webrip_720
            return webrip

        if source_type in ('vhsrip', 'vcd', 'svcd'):
            return vcd_svcd_vhsrip

        return 0

    async def get_data(self, meta):
        return meta['data']

    async def upload(self, meta):
        console.print("[yellow]YGG is not yet supported for uploads.")
        return False
