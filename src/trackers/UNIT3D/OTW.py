# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import re
from typing import Any, Optional, cast

import cli_ui

from src.console import console
from src.meta import Meta
from src.trackers.COMMON import COMMON
from src.trackers.UNIT3D import UNIT3D

Config = dict[str, Any]


class OTW(UNIT3D):
    supported_categories = ("TV", "MOVIE")
    tracker_urls = ['https://oldtoons.world']
    def __init__(self, config: Config) -> None:
        super().__init__(config, tracker_name='OTW')
        self.config: Config = config
        self.common = COMMON(config)
        self.tracker = 'OTW'
        self.base_url = 'https://oldtoons.world'
        self.id_url = f'{self.base_url}/api/torrents/'
        self.upload_url = f'{self.base_url}/api/torrents/upload'
        self.search_url = f'{self.base_url}/api/torrents/filter'
        self.requests_url = f'{self.base_url}/api/requests/filter'
        self.torrent_url = f'{self.base_url}/torrents/'
        self.banned_groups = [
            '[Oj]', '3LTON', '4yEo', 'ADE', 'AFG', 'AniHLS', 'AnimeRG', 'AniURL',
            'AROMA', 'aXXo', 'CM8', 'CrEwSaDe', 'DeadFish', 'DNL', 'ELiTE',
            'eSc', 'FaNGDiNG0', 'FGT', 'Flights', 'FRDS', 'FUM', 'GalaxyRG', 'HAiKU',
            'HD2DVD', 'HDS', 'HDTime', 'Hi10', 'INFINITY', 'ION10', 'iPlanet', 'JIVE', 'KiNGDOM',
            'LAMA', 'Leffe', 'LOAD', 'mHD', 'NhaNc3', 'nHD', 'NOIVTC', 'nSD', 'PiRaTeS',
            'PRODJi', 'RAPiDCOWS', 'RARBG', 'RDN', 'REsuRRecTioN', 'RMTeam', 'SANTi',
            'SicFoI', 'SPASM', 'STUTTERSHIT', 'Telly', 'TM', 'UPiNSMOKE', 'WAF', 'xRed',
            'XS', 'YELLO', 'YIFY', 'YTS', 'ZKBL', 'ZmN', '4f8c4100292', 'Azkars', 'Sync0rdi'
        ]

    async def get_additional_checks(self, meta: Meta) -> bool:
        should_continue = True
        combined_genres_value = meta.combined_genres
        # Normalize combined_genres to a list of individual genre strings.
        if isinstance(combined_genres_value, list):
            combined_genres = cast(list[str], combined_genres_value)
        else:
            # Split comma-separated strings and strip whitespace
            combined_genres = [g.strip() for g in str(combined_genres_value).split(',') if g.strip()]

        if not any(genre in combined_genres for genre in ['Animation', 'Family']):
            if not meta.unattended or (meta.unattended and meta.unattended_confirm):
                console.print('[bold red]Genre does not match Animation or Family for OTW.')
                if cli_ui.ask_yes_no("Do you want to upload anyway?", default=False):
                    pass
                else:
                    return False
            else:
                return False

        keywords = ', '.join(meta.keywords)
        combined_genres_text = ', '.join(combined_genres)
        genres = f"{keywords} {combined_genres_text}"
        adult_keywords = ['xxx', 'erotic', 'porn', 'adult', 'orgy', 'hentai', 'adult animation', 'softcore']
        if any(re.search(rf'(^|,\s*){re.escape(keyword)}(\s*,|$)', genres, re.IGNORECASE) for keyword in adult_keywords):
            if not meta.unattended or (meta.unattended and meta.unattended_confirm):
                console.print('[bold red]Adult animation not allowed at OTW.')
                if cli_ui.ask_yes_no("Do you want to upload anyway?", default=False):
                    pass
                else:
                    return False
            else:
                return False

        game_show_keywords = ['reality', 'game show', 'game-show', 'reality tv', 'reality television']
        if any(re.search(rf'(^|,\s*){re.escape(keyword)}(\s*,|$)', genres, re.IGNORECASE) for keyword in game_show_keywords):
            if not meta.unattended or (meta.unattended and meta.unattended_confirm):
                console.print('[bold red]Reality / Game Show content not allowed at OTW.')
                if cli_ui.ask_yes_no("Do you want to upload anyway?", default=False):
                    pass
                else:
                    return False
            else:
                return False

        if meta.type not in ["WEBDL"] and not meta.is_disc and meta.tag in ["CMRG", "EVO", "TERMiNAL", "ViSION"]:
            if not meta.unattended or (meta.unattended and meta.unattended_confirm):
                console.print(f"[bold red]Group {meta.tag} is only allowed for raw type content at OTW[/bold red]")
                if cli_ui.ask_yes_no("Do you want to upload anyway?", default=False):
                    pass
                else:
                    return False
            else:
                return False

        return should_continue

    async def get_type_id(
        self,
        meta: Meta,
        type: Optional[str] = None,
        reverse: bool = False,
        mapping_only: bool = False
    ) -> dict[str, str]:
        meta_type = str(meta.type)
        if meta.is_disc == "BDMV":
            return {'type_id': '1'}
        elif meta.is_disc and meta.is_disc != "BDMV":
            return {'type_id': '7'}
        if meta_type == "DVDRIP":
            return {'type_id': '8'}
        type_id = {
            'DISC': '1',
            'REMUX': '2',
            'WEBDL': '4',
            'WEBRIP': '5',
            'HDTV': '6',
            'ENCODE': '3'
        }
        if mapping_only:
            return type_id
        elif reverse:
            return {v: k for k, v in type_id.items()}
        type_value = type if type is not None else meta_type
        return {'type_id': type_id.get(type_value, '0')}

    async def get_name(self, meta: Meta) -> dict[str, str]:
        otw_name = meta.name
        source = str(meta.source)
        resolution = meta.resolution
        aka = meta.aka
        type = str(meta.type)
        video_codec = meta.video_codec
        if aka:
            otw_name = otw_name.replace(f"{aka} ", '')
        is_disc = str(meta.is_disc)
        audio = meta.audio
        if is_disc == "DVD" or (type == "REMUX" and source in ("PAL DVD", "NTSC DVD", "DVD")):
            otw_name = otw_name.replace(source, f"{resolution} {source}", 1)
            otw_name = otw_name.replace(audio, f"{video_codec} {audio}", 1)
        if str(meta.category) == "TV":
            years: list[int] = []

            tmdb_year = meta.year
            if tmdb_year and tmdb_year.isdigit():
                year = tmdb_year
            else:
                if tmdb_year and tmdb_year.isdigit():
                    years.append(int(tmdb_year))

                imdb_info = cast(dict[str, Any], meta.imdb_info)
                imdb_year = imdb_info.get('year')
                if imdb_year and str(imdb_year).isdigit():
                    years.append(int(imdb_year))

                tvdb_episode_data = meta.tvdb_episode_data
                series_year = tvdb_episode_data.get('series_year')
                if series_year and str(series_year).isdigit():
                    years.append(int(series_year))
                # Use the oldest year if any found, else empty string
                year = str(min(years)) if years else ""
            if not meta.no_year and not meta.search_year:
                title = meta.title
                otw_name = otw_name.replace(title, f"{title} {year}", 1)

        return {'name': otw_name}

    async def get_additional_data(self, meta: Meta) -> dict[str, Any]:
        data: dict[str, Any] = {
            'mod_queue_opt_in': await self.get_flag(meta, 'modq'),
        }

        return data
