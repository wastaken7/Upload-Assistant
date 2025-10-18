from src.console import console
import aiofiles
from src.get_desc import DescriptionBuilder


class YGG:
    def __init__(self, config):
        self.config = config
        self.tracker = 'YGG'
        self.source_flag = 'YGG'
        self.tracker_url = 'https://www.yggtorrent.top'
        self.upload_url = f'{self.tracker}/user/upload_torrent_action'
        self.search_url = f'{self.tracker}/engine/search?'
        self.torrent_url = f'{self.tracker}/torrent/'
        self.banned_groups = []
        pass

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
            if meta['anime']:
                return animation
            return movie
        elif meta['category'] == 'TV':
            if meta['anime']:
                return animation_series
            return tv_series
        if any(keyword in meta['keywords'] for keyword in ['documentary', 'biography']):
            return documentary
        if any(keyword in meta['keywords'] for keyword in ['tv show', 'talk show', 'game show']):
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

    async def get_data(self, meta):
        return meta['data']

    async def upload(self, meta):
        console.print("[yellow]YGG is not yet supported for uploads.")
        return False

    async def search_existing(self, meta, disctype):
        console.print("[yellow]YGG is not yet supported for searching existing torrents.")
        return []

    async def validate_credentials(self, meta):
        console.print("[yellow]YGG is not yet supported for validating credentials.")
        return False
