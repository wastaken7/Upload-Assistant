# -*- coding: utf-8 -*-
# import discord
import aiofiles
import click
import os
import re
import urllib.request
from src.console import console
from src.trackers.COMMON import COMMON
from src.trackers.UNIT3D import UNIT3D
from src.uploadscreens import upload_screens


class TIK(UNIT3D):
    def __init__(self, config):
        super().__init__(config, tracker_name='TIK')
        self.config = config
        self.common = COMMON(config)
        self.tracker = 'TIK'
        self.source_flag = 'TIK'
        self.base_url = 'https://cinematik.net'
        self.id_url = f'{self.base_url}/api/torrents/'
        self.upload_url = f'{self.base_url}/api/torrents/upload'
        self.search_url = f'{self.base_url}/api/torrents/filter'
        self.torrent_url = f'{self.base_url}/torrents/'
        self.banned_groups = []
        pass

    async def get_additional_checks(self, meta):
        should_continue = True

        if not meta['is_disc']:
            console.print("[red]Only disc-based content allowed at TIK")
            return False

        return should_continue

    async def get_additional_data(self, meta):
        data = {
            'modq': await self.get_flag(meta, 'modq'),
        }

        return data

    async def get_name(self, meta):
        disctype = meta.get('disctype', None)
        basename = os.path.basename(next(iter(meta['filelist']), meta['path']))
        type = meta.get('type', "")
        title = meta.get('title', "").replace('AKA', '/').strip()
        alt_title = meta.get('aka', "").replace('AKA', '/').strip()
        year = meta.get('year', "")
        resolution = meta.get('resolution', "")
        season = meta.get('season', "")
        repack = meta.get('repack', "")
        if repack.strip():
            repack = f"[{repack}]"
        three_d = meta.get('3D', "")
        three_d_tag = f"[{three_d}]" if three_d else ""
        tag = meta.get('tag', "").replace("-", "- ")
        if tag == "":
            tag = "- NOGRP"
        source = meta.get('source', "")
        uhd = meta.get('uhd', "")  # noqa #841
        hdr = meta.get('hdr', "")
        if not hdr.strip():
            hdr = "SDR"
        distributor = meta.get('distributor', "")  # noqa F841
        video_codec = meta.get('video_codec', "")
        video_encode = meta.get('video_encode', "").replace(".", "")
        if 'x265' in basename:
            video_encode = video_encode.replace('H', 'x')
        dvd_size = meta.get('dvd_size', "")
        search_year = meta.get('search_year', "")
        if not str(search_year).strip():
            search_year = year
        meta['category_id'] = (await self.get_category_id(meta))['category_id']

        name = ""
        alt_title_part = f" {alt_title}" if alt_title else ""
        if meta['category_id'] in ("1", "3", "5", "6"):
            if meta['is_disc'] == 'BDMV':
                name = f"{title}{alt_title_part} ({year}) {disctype} {resolution} {video_codec} {three_d_tag}"
            elif meta['is_disc'] == 'DVD':
                name = f"{title}{alt_title_part} ({year}) {source} {dvd_size}"
        elif meta['category'] == "TV":  # TV SPECIFIC
            if type == "DISC":  # Disk
                if meta['is_disc'] == 'BDMV':
                    name = f"{title}{alt_title_part} ({search_year}) {season} {disctype} {resolution} {video_codec}"
                if meta['is_disc'] == 'DVD':
                    name = f"{title}{alt_title_part} ({search_year}) {season} {source} {dvd_size}"

        return {'name': name}

    async def get_category_id(self, meta):
        category_name = meta['category']
        foreign = meta.get('foreign', False)
        opera = meta.get('opera', False)
        asian = meta.get('asian', False)
        category_id = {
            'FILM': '1',
            'TV': '2',
            'Foreign Film': '3',
            'Foreign TV': '4',
            'Opera & Musical': '5',
            'Asian Film': '6',
        }.get(category_name, '0')

        if category_name == 'MOVIE':
            if foreign:
                category_id = '3'
            elif opera:
                category_id = '5'
            elif asian:
                category_id = '6'
            else:
                category_id = '1'
        elif category_name == 'TV':
            if foreign:
                category_id = '4'
            elif opera:
                category_id = '5'
            else:
                category_id = '2'

        return {'category_id': category_id}

    async def get_type_id(self, meta):
        disctype = meta.get('disctype', None)
        type_id_map = {
            'Custom': '1',
            'BD100': '3',
            'BD66': '4',
            'BD50': '5',
            'BD25': '6',
            'NTSC DVD9': '7',
            'NTSC DVD5': '8',
            'PAL DVD9': '9',
            'PAL DVD5': '10',
            '3D': '11'
        }

        if not disctype:
            console.print("[red]You must specify a --disctype")
            # Raise an exception since we can't proceed without disctype
            raise ValueError("disctype is required for TIK tracker but was not provided")

        disctype_value = disctype[0] if isinstance(disctype, list) else disctype
        type_id = type_id_map.get(disctype_value, '1')  # '1' is the default fallback

        return {'type_id': type_id}

    async def get_resolution_id(self, meta):
        resolution_id = {
            'Other': '10',
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
        }.get(meta['resolution'], '10')
        return {'resolution_id': resolution_id}

    async def get_description(self, meta):
        signature = f"\n[right][url=https://github.com/Audionut/Upload-Assistant][size=4]{meta['ua_signature']}[/size][/url][/right]"
        await self.common.unit3d_edit_desc(meta, self.tracker, signature, comparison=True)
        if meta.get('description_link') or meta.get('description_file'):
            async with aiofiles.open(f'{meta["base_dir"]}/tmp/{meta["uuid"]}/[{self.tracker}]DESCRIPTION.txt', 'r', encoding='utf-8') as f:
                desc = await f.read()

            print(f'Custom Description Link/File Path: {desc}')
            return {'description': desc}

        if len(meta.get('discs', [])) > 0:
            summary = meta['discs'][0].get('summary', '')
        else:
            summary = None

        # Proceed with matching Total Bitrate if the summary exists
        if summary:
            match = re.search(r"Total Bitrate: ([\d.]+ Mbps)", summary)
            if match:
                total_bitrate = match.group(1)
            else:
                total_bitrate = "Unknown"
        else:
            total_bitrate = "Unknown"

        country_name = self.country_code_to_name(meta.get('region'))

        # Rehost poster if tmdb_poster is available
        poster_url = f"https://image.tmdb.org/t/p/original{meta.get('tmdb_poster', '')}"

        # Define the paths for both jpg and png poster images
        poster_jpg_path = f"{meta['base_dir']}/tmp/{meta['uuid']}/poster.jpg"
        poster_png_path = f"{meta['base_dir']}/tmp/{meta['uuid']}/poster.png"

        # Check if either poster.jpg or poster.png already exists
        if os.path.exists(poster_jpg_path):
            poster_path = poster_jpg_path
            console.print("[green]Poster already exists as poster.jpg, skipping download.[/green]")
        elif os.path.exists(poster_png_path):
            poster_path = poster_png_path
            console.print("[green]Poster already exists as poster.png, skipping download.[/green]")
        else:
            # No poster file exists, download the poster image
            poster_path = poster_jpg_path  # Default to saving as poster.jpg
            try:
                urllib.request.urlretrieve(poster_url, poster_path)
                console.print(f"[green]Poster downloaded to {poster_path}[/green]")
            except Exception as e:
                console.print(f"[red]Error downloading poster: {e}[/red]")

        # Upload the downloaded or existing poster image once
        if os.path.exists(poster_path):
            try:
                console.print("Uploading standard poster to image host....")
                new_poster_url, _ = await upload_screens(meta, 1, 1, 0, 1, [poster_path], {})

                # Ensure that the new poster URL is assigned only once
                if len(new_poster_url) > 0:
                    poster_url = new_poster_url[0]['raw_url']
            except Exception as e:
                console.print(f"[red]Error uploading poster: {e}[/red]")
        else:
            console.print("[red]Poster file not found, cannot upload.[/red]")

        # Generate the description text
        desc_text = []

        images = meta['image_list']
        discs = meta.get('discs', [])  # noqa #F841

        if len(images) >= 6:
            image_link_1 = images[0]['raw_url']
            image_link_2 = images[1]['raw_url']
            image_link_3 = images[2]['raw_url']
            image_link_4 = images[3]['raw_url']
            image_link_5 = images[4]['raw_url']
            image_link_6 = images[5]['raw_url']
        else:
            image_link_1 = image_link_2 = image_link_3 = image_link_4 = image_link_5 = image_link_6 = ""

        # Write the cover section with rehosted poster URL
        desc_text.append("[h3]Cover[/h3] [color=red]A stock poster has been automatically added, but you'll get more love if you include a proper cover, see rule 6.6[/color]\n")
        desc_text.append("[center]\n")
        desc_text.append(f"[IMG=500]{poster_url}[/IMG]\n")
        desc_text.append("[/center]\n\n")

        # Write screenshots section
        desc_text.append("[h3]Screenshots[/h3]\n")
        desc_text.append("[center]\n")
        desc_text.append(f"[URL={image_link_1}][IMG=300]{image_link_1}[/IMG][/URL] ")
        desc_text.append(f"[URL={image_link_2}][IMG=300]{image_link_2}[/IMG][/URL] ")
        desc_text.append(f"[URL={image_link_3}][IMG=300]{image_link_3}[/IMG][/URL]\n ")
        desc_text.append(f"[URL={image_link_4}][IMG=300]{image_link_4}[/IMG][/URL] ")
        desc_text.append(f"[URL={image_link_5}][IMG=300]{image_link_5}[/IMG][/URL] ")
        desc_text.append(f"[URL={image_link_6}][IMG=300]{image_link_6}[/IMG][/URL]\n")
        desc_text.append("[/center]\n\n")

        # Write synopsis section with the custom title
        desc_text.append("[h3]Synopsis/Review/Personal Thoughts (edit as needed)[/h3]\n")
        desc_text.append("[color=red]Default TMDB sypnosis added, more love if you use a sypnosis from credible film institutions such as the BFI or directly quoting well-known film critics, see rule 6.3[/color]\n")
        desc_text.append("[quote]\n")
        desc_text.append(f"{meta.get('overview', 'No synopsis available.')}\n")
        desc_text.append("[/quote]\n\n")

        # Write technical info section
        desc_text.append("[h3]Technical Info[/h3]\n")
        desc_text.append("[code]\n")
        if meta['is_disc'] == 'BDMV':
            desc_text.append(f"  Disc Label.........:{meta.get('bdinfo', {}).get('label', '')}\n")
        desc_text.append(f"  IMDb...............: [url]{str(meta.get('imdb_info', {}).get('imdb_url', ''))}{str(meta.get('imdb_rating', ''))}[/url]\n")
        desc_text.append(f"  Year...............: {meta.get('year', '')}\n")
        desc_text.append(f"  Country............: {country_name}\n")
        if meta['is_disc'] == 'BDMV':
            desc_text.append(f"  Runtime............: {meta.get('bdinfo', {}).get('length', '')} hrs [color=red](double check this is actual runtime)[/color]\n")
        else:
            desc_text.append("  Runtime............:  [color=red]Insert the actual runtime[/color]\n")

        if meta['is_disc'] == 'BDMV':
            audio_languages = ', '.join([f"{track.get('language', 'Unknown')} {track.get('codec', 'Unknown')} {track.get('channels', 'Unknown')}" for track in meta.get('bdinfo', {}).get('audio', [])])
            desc_text.append(f"  Audio..............: {audio_languages}\n")
            desc_text.append(f"  Subtitles..........: {', '.join(meta.get('bdinfo', {}).get('subtitles', []))}\n")
        else:
            # Process each disc's `vob_mi` or `ifo_mi` to extract audio and subtitles separately
            for disc in meta.get('discs', []):
                vob_mi = disc.get('vob_mi', '')
                ifo_mi = disc.get('ifo_mi', '')

                unique_audio = set()  # Store unique audio strings

                audio_section = vob_mi.split('\n\nAudio\n')[1].split('\n\n')[0] if 'Audio\n' in vob_mi else None
                if audio_section:
                    if "AC-3" in audio_section:
                        codec = "AC-3"
                    elif "DTS" in audio_section:
                        codec = "DTS"
                    elif "MPEG Audio" in audio_section:
                        codec = "MPEG Audio"
                    elif "PCM" in audio_section:
                        codec = "PCM"
                    elif "AAC" in audio_section:
                        codec = "AAC"
                    else:
                        codec = "Unknown"

                    channels = audio_section.split("Channel(s)")[1].split(":")[1].strip().split(" ")[0] if "Channel(s)" in audio_section else "Unknown"
                    # Convert 6 channels to 5.1, otherwise leave as is
                    channels = "5.1" if channels == "6" else channels
                    language = disc.get('ifo_mi_full', '').split('Language')[1].split(":")[1].strip().split('\n')[0] if "Language" in disc.get('ifo_mi_full', '') else "Unknown"
                    audio_info = f"{language} {codec} {channels}"
                    unique_audio.add(audio_info)

                # Append audio information to the description
                if unique_audio:
                    desc_text.append(f"  Audio..............: {', '.join(sorted(unique_audio))}\n")

                # Subtitle extraction using the helper function
                unique_subtitles = self.parse_subtitles(ifo_mi)

                # Append subtitle information to the description
                if unique_subtitles:
                    desc_text.append(f"  Subtitles..........: {', '.join(sorted(unique_subtitles))}\n")

        if meta['is_disc'] == 'BDMV':
            video_info = meta.get('bdinfo', {}).get('video', [])
            video_resolution = video_info[0].get('resolution', 'Unknown')
            desc_text.append(f"  Video Format.......: {video_resolution}\n")
        else:
            desc_text.append(f"  DVD Format.........: {meta.get('source', 'Unknown')}\n")
        desc_text.append("  Film Aspect Ratio..: [color=red]The actual aspect ratio of the content, not including the black bars[/color]\n")
        if meta['is_disc'] == 'BDMV':
            desc_text.append(f"  Source.............: {meta.get('disctype', 'Unknown')}\n")
        else:
            desc_text.append(f"  Source.............: {meta.get('dvd_size', 'Unknown')}\n")
        desc_text.append(f"  Film Distributor...: [url={meta.get('distributor_link', '')}]{meta.get('distributor', 'Unknown')}[/url] [color=red]Don't forget the actual distributor link\n")
        desc_text.append(f"  Average Bitrate....: {total_bitrate}\n")
        desc_text.append("  Ripping Program....:  [color=red]Specify - if it's your rip or custom version, otherwise 'Not my rip'[/color]\n")
        desc_text.append("\n")
        if meta.get('untouched') is True:
            desc_text.append("  Menus......: [X] Untouched\n")
            desc_text.append("  Video......: [X] Untouched\n")
            desc_text.append("  Extras.....: [X] Untouched\n")
            desc_text.append("  Audio......: [X] Untouched\n")
        else:
            desc_text.append("  Menus......: [ ] Untouched\n")
            desc_text.append("               [ ] Stripped\n")
            desc_text.append("  Video......: [ ] Untouched\n")
            desc_text.append("               [ ] Re-encoded\n")
            desc_text.append("  Extras.....: [ ] Untouched\n")
            desc_text.append("               [ ] Stripped\n")
            desc_text.append("               [ ] Re-encoded\n")
            desc_text.append("               [ ] None\n")
            desc_text.append("  Audio......: [ ] Untouched\n")
            desc_text.append("               [ ] Stripped tracks\n")

        desc_text.append("[/code]\n\n")

        # Extras
        desc_text.append("[h4]Extras[/h4]\n")
        desc_text.append("[*] Insert special feature 1 here\n")
        desc_text.append("[*] Insert special feature 2 here\n")
        desc_text.append("... (add more special features as needed)\n\n")

        # Uploader Comments
        desc_text.append("[h4]Uploader Comments[/h4]\n")
        desc_text.append(f" - {meta.get('uploader_comments', 'No comments.')}\n")

        # Convert the list to a single string for the description
        description = ''.join(desc_text)

        # Ask user if they want to edit or keep the description
        console.print(f"Current description: {description}", markup=False)
        console.print("[cyan]Do you want to edit or keep the description?[/cyan]")
        edit_choice = input("Enter 'e' to edit, or press Enter to keep it as is: ")

        if edit_choice.lower() == 'e':
            edited_description = click.edit(description)
            if edited_description:
                description = edited_description.strip()
            console.print(f"Final description after editing: {description}", markup=False)
        else:
            console.print("[green]Keeping the original description.[/green]")

        # Write the final description to the file
        async with aiofiles.open(f'{meta["base_dir"]}/tmp/{meta["uuid"]}/[{self.tracker}]DESCRIPTION.txt', 'w', encoding='utf-8') as desc_file:
            await desc_file.write(description)

        return {'description': description}

    def parse_subtitles(self, disc_mi):
        unique_subtitles = set()  # Store unique subtitle strings
        lines = disc_mi.splitlines()  # Split the multiline text into individual lines
        current_block = None

        for line in lines:
            # Detect the start of a subtitle block (Text #)
            if line.startswith("Text #"):
                current_block = "subtitle"
                continue

            # Extract language information for subtitles
            if current_block == "subtitle" and "Language" in line:
                language = line.split(":")[1].strip()
                unique_subtitles.add(language)

        return unique_subtitles

    def country_code_to_name(self, code):
        country_mapping = {
            'AFG': 'Afghanistan', 'ALB': 'Albania', 'DZA': 'Algeria', 'AND': 'Andorra', 'AGO': 'Angola',
            'ARG': 'Argentina', 'ARM': 'Armenia', 'AUS': 'Australia', 'AUT': 'Austria', 'AZE': 'Azerbaijan',
            'BHS': 'Bahamas', 'BHR': 'Bahrain', 'BGD': 'Bangladesh', 'BRB': 'Barbados', 'BLR': 'Belarus',
            'BEL': 'Belgium', 'BLZ': 'Belize', 'BEN': 'Benin', 'BTN': 'Bhutan', 'BOL': 'Bolivia',
            'BIH': 'Bosnia and Herzegovina', 'BWA': 'Botswana', 'BRA': 'Brazil', 'BRN': 'Brunei',
            'BGR': 'Bulgaria', 'BFA': 'Burkina Faso', 'BDI': 'Burundi', 'CPV': 'Cabo Verde', 'KHM': 'Cambodia',
            'CMR': 'Cameroon', 'CAN': 'Canada', 'CAF': 'Central African Republic', 'TCD': 'Chad', 'CHL': 'Chile',
            'CHN': 'China', 'COL': 'Colombia', 'COM': 'Comoros', 'COG': 'Congo', 'CRI': 'Costa Rica',
            'HRV': 'Croatia', 'CUB': 'Cuba', 'CYP': 'Cyprus', 'CZE': 'Czech Republic', 'DNK': 'Denmark',
            'DJI': 'Djibouti', 'DMA': 'Dominica', 'DOM': 'Dominican Republic', 'ECU': 'Ecuador', 'EGY': 'Egypt',
            'SLV': 'El Salvador', 'GNQ': 'Equatorial Guinea', 'ERI': 'Eritrea', 'EST': 'Estonia',
            'SWZ': 'Eswatini', 'ETH': 'Ethiopia', 'FJI': 'Fiji', 'FIN': 'Finland', 'FRA': 'France',
            'GAB': 'Gabon', 'GMB': 'Gambia', 'GEO': 'Georgia', 'DEU': 'Germany', 'GHA': 'Ghana',
            'GRC': 'Greece', 'GRD': 'Grenada', 'GTM': 'Guatemala', 'GIN': 'Guinea', 'GNB': 'Guinea-Bissau',
            'GUY': 'Guyana', 'HTI': 'Haiti', 'HND': 'Honduras', 'HUN': 'Hungary', 'ISL': 'Iceland', 'IND': 'India',
            'IDN': 'Indonesia', 'IRN': 'Iran', 'IRQ': 'Iraq', 'IRL': 'Ireland', 'ISR': 'Israel', 'ITA': 'Italy',
            'JAM': 'Jamaica', 'JPN': 'Japan', 'JOR': 'Jordan', 'KAZ': 'Kazakhstan', 'KEN': 'Kenya',
            'KIR': 'Kiribati', 'KOR': 'Korea', 'KWT': 'Kuwait', 'KGZ': 'Kyrgyzstan', 'LAO': 'Laos', 'LVA': 'Latvia',
            'LBN': 'Lebanon', 'LSO': 'Lesotho', 'LBR': 'Liberia', 'LBY': 'Libya', 'LIE': 'Liechtenstein',
            'LTU': 'Lithuania', 'LUX': 'Luxembourg', 'MDG': 'Madagascar', 'MWI': 'Malawi', 'MYS': 'Malaysia',
            'MDV': 'Maldives', 'MLI': 'Mali', 'MLT': 'Malta', 'MHL': 'Marshall Islands', 'MRT': 'Mauritania',
            'MUS': 'Mauritius', 'MEX': 'Mexico', 'FSM': 'Micronesia', 'MDA': 'Moldova', 'MCO': 'Monaco',
            'MNG': 'Mongolia', 'MNE': 'Montenegro', 'MAR': 'Morocco', 'MOZ': 'Mozambique', 'MMR': 'Myanmar',
            'NAM': 'Namibia', 'NRU': 'Nauru', 'NPL': 'Nepal', 'NLD': 'Netherlands', 'NZL': 'New Zealand',
            'NIC': 'Nicaragua', 'NER': 'Niger', 'NGA': 'Nigeria', 'MKD': 'North Macedonia', 'NOR': 'Norway',
            'OMN': 'Oman', 'PAK': 'Pakistan', 'PLW': 'Palau', 'PAN': 'Panama', 'PNG': 'Papua New Guinea',
            'PRY': 'Paraguay', 'PER': 'Peru', 'PHL': 'Philippines', 'POL': 'Poland', 'PRT': 'Portugal',
            'QAT': 'Qatar', 'ROU': 'Romania', 'RUS': 'Russia', 'RWA': 'Rwanda', 'KNA': 'Saint Kitts and Nevis',
            'LCA': 'Saint Lucia', 'VCT': 'Saint Vincent and the Grenadines', 'WSM': 'Samoa', 'SMR': 'San Marino',
            'STP': 'Sao Tome and Principe', 'SAU': 'Saudi Arabia', 'SEN': 'Senegal', 'SRB': 'Serbia',
            'SYC': 'Seychelles', 'SLE': 'Sierra Leone', 'SGP': 'Singapore', 'SVK': 'Slovakia', 'SVN': 'Slovenia',
            'SLB': 'Solomon Islands', 'SOM': 'Somalia', 'ZAF': 'South Africa', 'SSD': 'South Sudan',
            'ESP': 'Spain', 'LKA': 'Sri Lanka', 'SDN': 'Sudan', 'SUR': 'Suriname', 'SWE': 'Sweden',
            'CHE': 'Switzerland', 'SYR': 'Syria', 'TWN': 'Taiwan', 'TJK': 'Tajikistan', 'TZA': 'Tanzania',
            'THA': 'Thailand', 'TLS': 'Timor-Leste', 'TGO': 'Togo', 'TON': 'Tonga', 'TTO': 'Trinidad and Tobago',
            'TUN': 'Tunisia', 'TUR': 'Turkey', 'TKM': 'Turkmenistan', 'TUV': 'Tuvalu', 'UGA': 'Uganda',
            'UKR': 'Ukraine', 'ARE': 'United Arab Emirates', 'GBR': 'United Kingdom', 'USA': 'United States',
            'URY': 'Uruguay', 'UZB': 'Uzbekistan', 'VUT': 'Vanuatu', 'VEN': 'Venezuela', 'VNM': 'Vietnam',
            'YEM': 'Yemen', 'ZMB': 'Zambia', 'ZWE': 'Zimbabwe'
        }
        return country_mapping.get(code.upper(), 'Unknown Country')
