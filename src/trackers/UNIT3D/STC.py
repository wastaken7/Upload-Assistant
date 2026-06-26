# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import re
from typing import Any, Optional

import cli_ui

from src.console import console
from src.get_desc import DescriptionBuilder
from src.meta import Meta
from src.rehostimages import RehostImagesManager
from src.trackers.COMMON import COMMON
from src.trackers.UNIT3D import UNIT3D

Config = dict[str, Any]


class STC(UNIT3D):
    supported_categories = ("TV", "MOVIE")
    def __init__(self, config: Config) -> None:
        super().__init__(config, tracker_name='STC')
        self.config: Config = config
        self.common = COMMON(config)
        self.rehost_images_manager = RehostImagesManager(config)
        self.tracker = 'STC'
        self.base_url = 'https://skipthecommercials.xyz'
        self.id_url = f'{self.base_url}/api/torrents/'
        self.upload_url = f'{self.base_url}/api/torrents/upload'
        self.search_url = f'{self.base_url}/api/torrents/filter'
        self.torrent_url = f'{self.base_url}/torrents/'
        self.banned_groups = [""]
        self.approved_image_hosts = ['imgbox', 'imgbb']
        pass

    async def get_type_id(
        self,
        meta: Meta,
        type: Optional[str] = None,
        reverse: bool = False,
        mapping_only: bool = False,
    ) -> dict[str, str]:
        _ = (type, reverse, mapping_only)
        type_value = str(meta.type)
        type_id = {
            'DISC': '1',
            'REMUX': '2',
            'WEBDL': '4',
            'WEBRIP': '5',
            'HDTV': '6',
            'ENCODE': '3'
        }.get(type_value, '0')
        if meta.tv_pack:
            is_web = type_value in ["WEBDL", "WEBRIP"]
            type_id = ("17" if not is_web else "14") if meta.sd else ("18" if not is_web else "13")

        return {'type_id': type_id}

    async def get_additional_checks(self, meta: Meta) -> bool:
        should_continue = True
        if str(meta.category) != "TV":
            if not bool(meta.unattended):
                console.print(f'[bold red]Only TV uploads allowed at {self.tracker}.[/bold red]')
            return False

        genres = f"{meta.keywords} {meta.combined_genres}"
        adult_keywords = ['xxx', 'erotic', 'porn', 'adult', 'orgy', 'hentai', 'adult animation', 'softcore']
        if any(re.search(rf'(^|,\s*){re.escape(keyword)}(\s*,|$)', genres, re.IGNORECASE) for keyword in adult_keywords):
            if not bool(meta.unattended) or (bool(meta.unattended) and meta.unattended_confirm):
                console.print(f'[bold red]Porn is not allowed at {self.tracker}.[/bold red]')
                if cli_ui.ask_yes_no("Do you want to upload anyway?", default=False):
                    pass
                else:
                    return False
            else:
                return False

        return should_continue

    async def check_image_hosts(self, meta: Meta) -> None:
        url_host_mapping = {
            "ibb.co": "imgbb",
            "imgbox.com": "imgbox",
        }
        await self.rehost_images_manager.check_hosts(
            meta,
            self.tracker,
            url_host_mapping=url_host_mapping,
            img_host_index=1,
            approved_image_hosts=self.approved_image_hosts,
        )

    async def get_description(self, meta: Meta) -> dict[str, str]:
        return {
            "description": await DescriptionBuilder(self.tracker, self.config).unit3d_edit_desc(
                meta,
                approved_image_hosts=self.approved_image_hosts,
            )
        }
