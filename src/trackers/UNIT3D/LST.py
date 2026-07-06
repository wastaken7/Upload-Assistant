# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
from typing import Any

from src.console import logger
from src.meta import Meta
from src.trackers.COMMON import COMMON
from src.trackers.UNIT3D import UNIT3D

Config = dict[str, Any]


class LST(UNIT3D):
    supported_categories = ("TV", "MOVIE", "BOOK")
    tracker_urls = ['https://lst.gg']

    def __init__(self, config: Config) -> None:
        super().__init__(config, tracker_name='LST')
        self.config: Config = config
        self.common = COMMON(config)
        self.tracker = 'LST'
        self.base_url = 'https://lst.gg'
        self.banned_url = f'{self.base_url}/api/bannedReleaseGroups'
        self.id_url = f'{self.base_url}/api/torrents/'
        self.upload_url = f'{self.base_url}/api/torrents/upload'
        self.search_url = f'{self.base_url}/api/torrents/filter'
        self.torrent_url = f'{self.base_url}/torrents/'
        self.trumping_url = f'{self.base_url}/api/reports/torrents/'
        self.banned_groups = []

    async def get_additional_checks(self, meta: Meta) -> bool:
        if meta.category == "BOOK":
            return True

        should_continue = True
        if not meta.valid_mi_settings:
            logger.info(f"[bold red]No encoding settings in mediainfo, skipping {self.tracker} upload.[/bold red]")
            return False

        if meta.is_disc not in ["BDMV", "DVD"] and not await self.common.check_language_requirements(
            meta, self.tracker, languages_to_check=["english"], check_audio=True, check_subtitle=True, original_language=True
        ):
            return False

        return should_continue

    async def get_category_id(self, meta: Meta, category: str | None = None, reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        category_id = {
            "MOVIE": "1",
            "TV": "2",
            "BOOK": "9",
        }
        if mapping_only:
            return category_id
        elif reverse:
            return {v: k for k, v in category_id.items()}

        resolved_category = category if category is not None and category != "" else meta.category
        return {"category_id": category_id.get(resolved_category, "0")}

    async def get_type_id(self, meta: Meta, type: str | None = None, reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        type_id = {
            "DISC": "1",
            "REMUX": "2",
            "ENCODE": "3",
            "DVDRIP": "3",
            "WEBDL": "4",
            "WEBRIP": "5",
            "HDTV": "6",
            "SDTV": "16",
            "FLAC": "7",
            "ALAC": "8",
            "AC3": "9",
            "AAC": "10",
            "MP3": "11",
            "MAC": "12",
            "WINDOWS": "13",
            "LINUX": "14",
            "OTHER": "15",
        }
        if mapping_only:
            return type_id
        elif reverse:
            return {v: k for k, v in type_id.items()}

        resolved_type = type if type is not None and type != "" else meta.type
        if isinstance(resolved_type, str):
            resolved_type = resolved_type.upper().strip().lstrip(".")

        val = type_id.get(resolved_type or "", "0")
        if meta.category == "BOOK" and resolved_type not in type_id:
            val = "15"

        return {"type_id": val}

    async def get_additional_data(self, meta: Meta) -> dict[str, Any]:
        data: dict[str, Any] = {
            'mod_queue_opt_in': await self.get_flag(meta, 'modq'),
            'draft_queue_opt_in': await self.get_flag(meta, 'draft'),
        }

        # Only add edition_id if we have a valid edition
        edition_id = await self.get_edition(meta)
        if edition_id is not None:
            data['edition_id'] = edition_id

        if meta.category == "BOOK":
            openlibrary_id = meta.openlibrary or meta.openlibrary_id or meta.openlibrary_book_id or ""
            isbn = meta.isbn or ""

            data["book_exists_on_openlibrary"] = "1"
            data["openlibrary_book_id"] = openlibrary_id
            data["openlibrary_isbn"] = isbn
            data["extra_openlibrary_ids"] = meta.extra_openlibrary_ids or ""

        return data

    async def get_edition(self, meta: Meta) -> int | None:
        edition_mapping = {
            'Alternative Cut': 12,
            'Collector\'s Edition': 1,
            'Director\'s Cut': 2,
            'Extended Cut': 3,
            'Extended Uncut': 4,
            'Extended Unrated': 5,
            'Limited Edition': 6,
            'Special Edition': 7,
            'Theatrical Cut': 8,
            'Uncut': 9,
            'Unrated': 10,
            'X Cut': 11,
            'Other': 0  # Default value for "Other"
        }
        edition = meta.edition
        if edition in edition_mapping:
            return edition_mapping[edition]
        else:
            return None

    async def get_name(self, meta: Meta) -> dict[str, str]:
        lst_name = meta.name
        resolution = meta.resolution
        video_encode = meta.video_encode
        name_type = meta.type

        if name_type == "DVDRIP":
            if meta.category == "MOVIE":
                lst_name = lst_name.replace(f"{meta.source}{meta.video_encode}", f"{resolution}", 1)
                lst_name = lst_name.replace(meta.audio, f"{meta.audio}{video_encode}", 1)
            else:
                lst_name = lst_name.replace(str(meta.source), f"{resolution}", 1)
                lst_name = lst_name.replace(meta.video_codec, f"{meta.audio} {meta.video_codec}", 1)

        if meta.trump_reason == "exact_match":
            lst_name = lst_name + " - TRUMP"

        return {'name': lst_name}
