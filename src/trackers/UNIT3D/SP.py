# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import os
import re
from typing import Any, Optional, cast

import cli_ui

from src.console import console
from src.meta import Meta
from src.trackers.COMMON import COMMON
from src.trackers.UNIT3D import UNIT3D

Config = dict[str, Any]


class SP(UNIT3D):
    supported_categories = ("TV", "MOVIE")
    tracker_urls = ['https://seedpool.org']
    def __init__(self, config: Config) -> None:
        super().__init__(config, tracker_name='SP')
        self.config: Config = config
        self.common = COMMON(config)
        self.tracker = 'SP'
        self.base_url = 'https://seedpool.org'
        self.id_url = f'{self.base_url}/api/torrents/'
        self.upload_url = f'{self.base_url}/api/torrents/upload'
        self.search_url = f'{self.base_url}/api/torrents/filter'
        self.torrent_url = f'{self.base_url}/torrents/'
        self.banned_groups = []

    async def get_category_id(
        self,
        meta: Meta,
        category: Optional[str] = None,
        reverse: bool = False,
        mapping_only: bool = False
    ) -> dict[str, str]:
        _ = (category, reverse, mapping_only)
        category_name = str(meta.category).upper()
        release_title = meta.name
        mal_id = meta.mal_id or 0

        # Custom SEEDPOOL category logic
        # Anime TV go in the Anime category
        if mal_id != 0 and category_name == 'TV':
            return {'category_id': '6'}

        # Sports
        if self.contains_sports_patterns(release_title):
            return {'category_id': '8'}

        # Default category logic
        category_id = {
            'MOVIE': '1',
            'TV': '2',
        }.get(category_name, '0')
        return {'category_id': category_id}

    # New function to check for sports releases in a title
    def contains_sports_patterns(self, release_title: str) -> bool:
        patterns = [
            r'EFL.*', r'.*mlb.*', r'.*formula1.*', r'.*nascar.*', r'.*nfl.*', r'.*wrc.*', r'.*wwe.*',
            r'.*fifa.*', r'.*boxing.*', r'.*rally.*', r'.*ufc.*', r'.*ppv.*', r'.*uefa.*', r'.*nhl.*',
            r'.*nba.*', r'.*motogp.*', r'.*moto2.*', r'.*moto3.*', r'.*gamenight.*', r'.*darksport.*',
            r'.*overtake.*'
        ]

        return any(re.search(pattern, release_title, re.IGNORECASE) for pattern in patterns)

    async def get_type_id(
        self,
        meta: Meta,
        type: Optional[str] = None,
        reverse: bool = False,
        mapping_only: bool = False
    ) -> dict[str, str]:
        _ = (type, reverse, mapping_only)
        type_value = str(meta.type)
        type_id = {
            'DISC': '1',
            'REMUX': '2',
            'WEBDL': '4',
            'WEBRIP': '5',
            'HDTV': '6',
            'ENCODE': '3',
            'DVDRIP': '3'
        }.get(type_value, '0')
        return {'type_id': type_id}

    async def get_name(self, meta: Meta) -> dict[str, str]:
        KNOWN_EXTENSIONS = {".mkv", ".mp4", ".avi", ".ts"}
        if meta.scene:
            scene_name = meta.scene_name
            name = scene_name if scene_name != "" else meta.basename_no_ext.replace(" ", ".")
        elif bool(meta.is_disc):
            name = meta.name.replace(" ", ".")
        else:
            base_name = meta.name.replace(" ", ".")
            uuid_name = meta.basename_no_ext.replace(" ", ".")
            name = base_name if meta.mal_id or 0 != 0 else uuid_name
        base, ext = os.path.splitext(name)
        if ext.lower() in KNOWN_EXTENSIONS:
            name = base.replace(" ", ".")
        console.print(f"[cyan]Name: {name}")

        return {'name': name}

    async def get_additional_checks(self, meta: Meta) -> bool:
        resolution = meta.resolution
        if resolution not in ['8640p', '4320p', '2160p', '1440p', '1080p', '1080i']:
            console.print(f'[bold red]Only 1080 or higher resolutions allowed at {self.tracker}.[/bold red]')
            if not meta.unattended or (bool(meta.unattended) and meta.unattended_confirm):
                if cli_ui.ask_yes_no("Do you want to upload anyway?", default=False):
                    pass
                else:
                    return False
            else:
                return False

        disallowed_keywords = {'xxx', 'erotic', 'porn'}
        disallowed_genres = {'adult', 'erotica'}
        keywords = [k.strip() for k in meta.keywords if k.strip()]
        combined_genres_val = meta.combined_genres
        if isinstance(combined_genres_val, str):
            combined_genres = [g.strip() for g in combined_genres_val.split(",") if g.strip()]
        else:
            combined_genres = [str(g) for g in cast(list[Any], combined_genres_val)]
        if any(keyword.lower() in disallowed_keywords for keyword in keywords) or any(
            genre.lower() in disallowed_genres for genre in combined_genres
        ):
            if not meta.unattended or (bool(meta.unattended) and meta.unattended_confirm):
                console.print(f'[bold red]Porn/xxx is not allowed at {self.tracker}.[/bold red]')
                if cli_ui.ask_yes_no("Do you want to upload anyway?", default=False):
                    pass
                else:
                    return False
            else:
                return False

        return True

    async def get_additional_data(self, meta: Meta) -> dict[str, Any]:
        data = {
            'mod_queue_opt_in': await self.get_flag(meta, 'modq'),
        }

        return data
