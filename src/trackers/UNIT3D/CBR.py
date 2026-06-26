# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import re
from typing import Any

from src.console import console
from src.get_desc import DescriptionBuilder
from src.meta import Meta
from src.trackers.COMMON import COMMON
from src.trackers.UNIT3D import UNIT3D


class CBR(UNIT3D):
    supported_categories = ("TV", "MOVIE", "BOOK", "GAME")
    tracker_urls = ['capybarabr.com']

    def __init__(self, config: dict[str, Any]):
        super().__init__(config, tracker_name='CBR')
        self.config = config
        self.common = COMMON(config)
        self.tracker = 'CBR'
        self.base_url = 'https://capybarabr.com'
        self.id_url = f'{self.base_url}/api/torrents/'
        self.upload_url = f'{self.base_url}/api/torrents/upload'
        self.search_url = f'{self.base_url}/api/torrents/filter'
        self.torrent_url = f'{self.base_url}/torrents/'
        self.requests_url = f'{self.base_url}/api/requests/filter'
        self.pending_url = f"{self.base_url}/api/torrents/pending"
        self.banned_groups = [
            "4K4U", "afm72", "Alcaide_Kira", "AROMA", "ASM", "Bandi", "BiTOR", "BLUDV", "Bluespots",
            "BOLS", "CaNNIBal", "Comando", "d3g", "DepraveD", "EMBER", "FGT", "FreetheFish", "Garshasp",
            "Ghost", "Grym", "HDS", "Hi10", "HiQVE", "Hiro360", "ImE", "ION10", "iVy", "Judas", "LAMA",
            "Langbard", "Lapumia", "LION", "MeGusta", "MONOLITH", "MRCS", "NaNi", "Natty", "nikt0",
            "OEPlus", "OFT", "OsC", "Panda", "PANDEMONiUM", "PHOCiS", "PiRaTeS", "PYC", "QxR", "r00t",
            "Ralphy", "RARBG", "RetroPeeps", "RZeroX", "S74Ll10n", "SAMPA", "Sicario", "SiCFoI", "Silence",
            "SkipTT", "SM737", "SPDVD", "STUTTERSHIT", "SWTYBLZ", "t3nzin", "TAoE", "TEKNO3D", "Telly", "TGx",
            "Tigole", "TSP", "TSPxL", "TWA", "UnKn0wn", "VXT", "Vyndros", "W32", "Will1869", "x0r", "YIFY", "YTS.MX", "YTS"
        ]

    async def get_category_id(self, meta: Meta, category: str = "", reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        category_id: dict[str, str] = {"MOVIE": "1", "TV": "2", "ANIMES": "4", "BOOK": "11", "COMIC_MANGA": "10", "GAME": "5"}

        if mapping_only:
            return category_id
        elif reverse:
            return {v: k for k, v in category_id.items()}

        resolved_category = category if category else meta.category
        if meta.anime is True and resolved_category == "TV":
            resolved_category = "ANIMES"

        if resolved_category == "BOOK" and (meta.type.upper() in ("CBR", "CBZ") or meta.manga or meta.comic):
            resolved_category = "COMIC_MANGA"

        if resolved_category:
            return {"category_id": category_id.get(resolved_category, "0")}

        return {"category_id": "0"}

    async def get_type_id(self, meta: Meta, type: str = "", reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        type_id = {
            "DISC": "1",
            "REMUX": "2",
            "ENCODE": "3",
            "DVDRIP": "3",
            "WEBDL": "4",
            "WEBRIP": "5",
            "HDTV": "6",
            "AZW3": "13",
            "CBR": "14",
            "CBZ": "15",
            "MOBI": "16",
            "PDF": "17",
            "EPUB": "18",
            "KFX": "19",
            "MP4": "21",
            "TS": "22",
            "MKV": "23",
            "MP3": "24",
            "M4B": "43",
            "FLAC": "43",
            "AAC": "43",
            "M4A": "43",
            "OGG": "43",
            "WAV": "43",
            "AUDIOBOOK": "24",
            "OUTROS": "43",
            "PC": "46",
            "PLAYSTATION": "48",
            "XBOX": "49",
            "NINTENDO": "50",
        }

        if mapping_only:
            return type_id
        elif reverse:
            return {v: k for k, v in type_id.items()}

        resolved_type = type if type else meta.type
        if resolved_type == "GAME" or (meta.category == "GAME" and resolved_type not in type_id):
            platform = str(meta.platform).lower()
            nin_term = bytes([110, 105, 110, 116, 101, 110, 100, 111]).decode()

            if any(word in platform for word in ["playstation", "ps5", "ps4", "ps3", "ps2", "ps1", "psp", "vita"]):
                resolved_id = "48"
            elif "xbox" in platform:
                resolved_id = "49"
            elif any(word in platform for word in [f"{nin_term}", "switch", "wii", "3ds", "nds", "ds"]):
                resolved_id = "50"
            else:
                resolved_id = "46"
        else:
            resolved_id = type_id.get(resolved_type, "0")

        return {"type_id": resolved_id}

    async def get_resolution_id(self, meta: Meta, resolution: str = "", reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        resolution_id = {
            '4320p': '1',
            '2160p': '2',
            '1080p': '3',
            '1080i': '4',
            '720p': '5',
            '576p': '6',
            '576i': '7',
            '480p': '8',
            '480i': '9',
            'Other': '10',
        }

        if mapping_only:
            return resolution_id
        elif reverse:
            return {v: k for k, v in resolution_id.items()}
        elif resolution:
            return {"resolution_id": resolution_id.get(resolution, "10")}
        else:
            meta_resolution = meta.resolution
            resolved_id = resolution_id.get(meta_resolution, "10")
            return {"resolution_id": resolved_id}

    async def get_description(self, meta: Meta) -> dict[str, str]:
        signature = f"[right][url=https://github.com/wastaken7/Upload-Assistant][size=4]Compartilhado com {meta.ua_name} {meta.current_version} (fork)[/size][/url][/right]"
        return {"description": await DescriptionBuilder(self.tracker, self.config).unit3d_edit_desc(meta, signature=signature)}

    async def get_name(self, meta: Meta) -> dict[str, str]:
        category = meta.category
        cbr_name = str(meta.name)
        name = str(meta.name)

        if category == "BOOK":
            book_title = self.common.portuguese_title_capitalization(meta.title)
            cbr_name = f"{book_title} - {meta.author} [{meta.year}] [AUDIOBOOK]" if meta.audiobook else f"{book_title} - {meta.author} [{meta.year}]"
            book_language_iso = meta.book_language_iso
            if book_language_iso and book_language_iso != "por":
                cbr_name += f" [{book_language_iso.upper()}]"

        elif category == "GAME":
            tag = meta.tag
            if tag:
                tag = tag.lstrip("-")
            game_has_multiple_languages = len(meta.languages) > 1
            game_lang_has_pt = "PORTUGUESE" in str(meta.languages).upper()
            game_lang_has_eng = "ENGLISH" in str(meta.languages).upper()

            if game_has_multiple_languages and game_lang_has_pt:
                game_lang = "MULTI"
            elif game_lang_has_eng:
                game_lang = "INGLÊS"
            else:
                game_lang = meta.language.upper()

            game_subcategory = meta.game_subcategory.lower()
            update = "Update" if game_subcategory == "update" else ""
            dlc = "[DLC]" if game_subcategory == "dlc" else "[+DLC]" if game_subcategory == "full_game_dlc" else ""
            if dlc:
                dlc = f" {dlc}"

            cbr_name = f"{meta.title} {update} {meta.game_version} {meta.year} - {tag} [{game_lang}]{dlc}"

        elif category in ("MOVIE", "TV"):
            cbr_name = cbr_name.replace("DD+ ", "DDP").replace("DD ", "DD").replace("AAC ", "AAC").replace("FLAC ", "FLAC").replace("Dubbed", "").replace("Dual-Audio", "")

            # If it is a Series or Anime, remove the year from the title.
            if meta.category in ["TV", "ANIMES"]:
                year = str(meta.year)
                if year and year in cbr_name:
                    cbr_name = cbr_name.replace(f"({year})", "").replace(year, "").strip()

            # Remove the AKA title, unless it is Brazilian
            if meta.original_language != "pt":
                cbr_name = cbr_name.replace(meta.aka, "")

            # If it is Brazilian, use only the AKA title, deleting the foreign title
            if meta.original_language == "pt" and meta.aka:
                aka_clean = str(meta.aka).replace("AKA", "").strip()
                title = meta.title
                cbr_name = cbr_name.replace(meta.aka, "").replace(title, aka_clean).strip()

            tag_lower = str(meta.tag).lower()
            invalid_tags = ["nogrp", "nogroup", "unknown", "-unk-"]

            if not meta.is_disc:
                audio_tag = ""
                audio_langs = meta.audio_languages
                if audio_langs:
                    try:
                        audio_languages: set[str] = set(audio_langs)
                    except TypeError:
                        audio_languages = set()

                    if any(lang.lower() == "portuguese" or lang == "português" for lang in audio_languages):
                        if len(audio_languages) >= 3:
                            audio_tag = " MULTI"
                        elif len(audio_languages) == 2:
                            audio_tag = " DUAL"
                        else:
                            audio_tag = ""

                    if audio_tag:
                        if "-" in cbr_name:
                            parts = cbr_name.rsplit("-", 1)

                            custom_tag = dict(dict(self.config.get("TRACKERS", {})).get(self.tracker, {})).get("tag_for_custom_release", "")
                            if custom_tag and custom_tag in name:
                                match = re.search(r"-([^.-]+)\.(?:DUAL|MULTI)", meta.uuid)
                                if match and match.group(1) != meta.tag:
                                    original_group_tag = match.group(1)
                                    cbr_name = f"{parts[0]}-{original_group_tag}{audio_tag}-{parts[1]}"
                                else:
                                    cbr_name = f"{parts[0]}{audio_tag}-{parts[1]}"
                            else:
                                cbr_name = f"{parts[0]}{audio_tag}-{parts[1]}"
                        else:
                            cbr_name += audio_tag

            if meta.tag == "" or any(invalid_tag in tag_lower for invalid_tag in invalid_tags):
                for invalid_tag in invalid_tags:
                    cbr_name = re.sub(f"-{invalid_tag}", "", cbr_name, flags=re.IGNORECASE)
                cbr_name = f"{cbr_name}-NoGroup"

        return {"name": re.sub(r"\s{2,}", " ", cbr_name)}

    async def get_additional_data(self, meta: Meta) -> dict[str, str]:
        data = {
            'mod_queue_opt_in': await self.get_flag(meta, 'modq'),
        }

        return data

    async def get_additional_checks(self, meta: Meta) -> bool:
        if meta.category == "BOOK" and bool(meta.audiobook) and not meta.narrator:
            console.print(f"{self.tracker}: [bold red]Narrator is required for audiobooks. Skipping upload...[/bold red]")
            return False

        if meta.category in ["MOVIE", "TV"]:
            subtitles = await self.common.check_language_requirements(meta, self.tracker, languages_to_check=["portuguese", "português"], check_audio=True, check_subtitle=True)
            if not subtitles and (not meta.unattended or (meta.unattended and meta.unattended_confirm)):
                proceed = await self.common.prompt_user_for_confirmation(
                    f"{self.tracker}: No Portuguese audio or subtitles found. Do you want to proceed with the upload?",
                )
                return proceed
            return subtitles

        return True
