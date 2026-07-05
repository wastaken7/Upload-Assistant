# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
from typing import Any

import cli_ui

from src.console import logger
from src.languages import languages_manager
from src.meta import Meta
from src.tmdb import TmdbManager
from src.trackers.UNIT3D import UNIT3D


class DP(UNIT3D):
    supported_categories = ("TV", "MOVIE", "BOOK", "GAME")
    tracker_urls = ['https://darkpeers.org']

    def __init__(self, config: dict[str, Any]):
        super().__init__(config, tracker_name='DP')
        self.config = config
        self.tmdb_manager = TmdbManager(config)
        self.tracker = 'DP'
        self.base_url = 'https://darkpeers.org'
        self.id_url = f'{self.base_url}/api/torrents/'
        self.upload_url = f'{self.base_url}/api/torrents/upload'
        self.requests_url = f'{self.base_url}/api/requests/filter'
        self.search_url = f'{self.base_url}/api/torrents/filter'
        self.torrent_url = f'{self.base_url}/torrents/'
        self.banned_groups = [
            'ARCADE', 'aXXo', 'BANDOLEROS', 'BONE', 'BRrip', 'CM8', 'CrEwSaDe', 'CTFOH', 'dAV1nci', 'DNL',
            'eranger2', 'FaNGDiNG0', 'FGT', 'FiSTER', 'flower', 'GalaxyTV', 'HD2DVD', 'HDTime', 'HorribleSubs',
            'iHYTECH', 'ION10', 'iPlanet', 'KiNGDOM', 'LAMA', 'MeGusta', 'mHD', 'mSD', 'NaNi', 'NhaNc3', 'nHD',
            'nikt0', 'nSD', 'OFT', 'PiTBULL', 'PRODJi', 'PSA', 'RARBG', 'Rifftrax', 'ROCKETRACCOON',
            'SANTi', 'SasukeducK', 'SEEDSTER', 'ShAaNiG', 'Sicario', 'STUTTERSHIT', 'Subsplease', 'SyncUp',
            'TAoE', 'TGALAXY', 'TGx', 'TORRENTGALAXY', 'ToVaR', 'Trix', 'TSP', 'TSPxL', 'ViSION', 'VXT',
            'WAF', 'WKS', 'X0r', 'YIFY', 'YTS',
        ]

    async def get_additional_checks(self, meta: Meta) -> bool:
        should_continue = True
        if meta.keep_folder:
            if not meta.unattended or (meta.unattended and meta.unattended_confirm):
                logger.info(f'[bold red]{self.tracker} does not allow single files in a folder.')
                if cli_ui.ask_yes_no("Do you want to upload anyway?", default=False):
                    pass
                else:
                    return False
            else:
                return False

        nordic_languages = ['danish', 'swedish', 'norwegian', 'icelandic', 'finnish', 'english']
        if not await self.common.check_language_requirements(
            meta, self.tracker, languages_to_check=nordic_languages, check_audio=True, check_subtitle=True
        ):
            return False

        if meta.type not in ["WEBDL"] and meta.tag in ["EVO"]:
            if not meta.unattended:
                logger.info(f"[bold red]{self.tracker} does not allow EVO for non-WEBDL types, skipping upload.")
            return False

        if meta.hardcoded_subs and not meta.unattended:
            logger.info(f"[bold red]{self.tracker} does not allow hardcoded subtitles.")
            return False

        return should_continue

    async def get_additional_data(self, meta: Meta) -> dict[str, Any]:
        data = {
            'mod_queue_opt_in': await self.get_flag(meta, 'modq'),
        }

        return data

    async def get_audio(self, meta: Meta) -> str:
        languages_result = "SKIPPED"

        if not meta.language_checked:
            await languages_manager.process_desc_language(meta, tracker=self.tracker)

        audio_languages = meta.audio_languages
        if isinstance(audio_languages, list):
            audio_languages_list = audio_languages
            normalized_languages = {str(lang).strip() for lang in audio_languages_list if str(lang).strip()}

            if len(normalized_languages) > 2:
                languages_result = "MULTi"
            elif len(normalized_languages) > 1:
                languages_result = "Dual-Audio"
            else:
                languages_result = next(iter(normalized_languages), "SKIPPED")

        return f'{languages_result}'

    async def get_name(self, meta: Meta) -> dict[str, str]:
        dp_name = meta.name

        audio = await self.get_audio(meta)
        if audio and audio != "SKIPPED" and "Dual-Audio" in dp_name:
            dp_name = dp_name.replace("Dual-Audio", audio)

        return {'name': dp_name}

    async def get_category_id(self, meta: Meta, category: str = "", reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        category_id = {
            "MOVIE": "1",
            "TV": "2",
            "BOOK": "8",
            "GAME": "4",
        }
        if mapping_only:
            return category_id
        elif reverse:
            return {v: k for k, v in category_id.items()}
        elif category:
            return {"category_id": category_id.get(category, "0")}
        else:
            meta_category = meta.category
            resolved_id = category_id.get(meta_category, "0")
            return {"category_id": resolved_id}

    async def get_type_id(self, meta: Meta, type: str = "", reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        type_id = {
            "DISC": "1",
            "REMUX": "2",
            "WEBDL": "4",
            "WEBRIP": "5",
            "HDTV": "6",
            "ENCODE": "3",
            "DVDRIP": "3",
            "AUDIOBOOK": "15",
            "COMIC": "17",
            "EBOOK": "18",
            "PC": "9",
            "LINUX": "14",
            "MAC": "11",
            "CONSOLE": "10",
        }
        if mapping_only:
            return type_id
        elif reverse:
            return {v: k for k, v in type_id.items()}

        meta_type = "" if not meta.type else meta.type.upper()

        # Book
        if meta.category == "BOOK":
            if type:
                t_upper = type.upper()
                if t_upper in ("CBR", "CBZ"):
                    t_upper = "COMIC"
                elif t_upper in ("EPUB", "PDF", "MOBI", "AZW3", "KFX"):
                    t_upper = "EBOOK"
                elif t_upper in ("MP3", "M4B", "FLAC", "AAC", "M4A", "OGG", "WAV"):
                    t_upper = "AUDIOBOOK"
                return {"type_id": type_id.get(t_upper, type_id.get(type, "0"))}
            else:
                if meta.category == "BOOK":
                    if meta.audiobook:
                        meta_type = "AUDIOBOOK"
                    elif meta.comic or meta_type in ("CBR", "CBZ"):
                        meta_type = "COMIC"
                    else:
                        meta_type = "EBOOK"

        if meta.category == "GAME":
            meta_type = "CONSOLE" if meta.console_game else meta.platform.upper()

        resolved_id = type_id.get(meta_type, "0")
        return {"type_id": resolved_id}
