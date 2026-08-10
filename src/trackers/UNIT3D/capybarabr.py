# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import re
from typing import Any

from src.console import logger
from src.get_desc import DescriptionBuilder
from src.meta import Meta
from src.trackers.common import Common
from src.trackers.UNIT3D import UNIT3D


class CapybaraBR(UNIT3D):
    """
    CapybaraBR is a BRAZILIAN Private Torrent Tracker for MOVIES / TV / GENERAL
    """

    tracker = "CAPYBARABR"
    display_name = "CapybaraBR"
    base_url = "https://capybarabr.com"
    allows_bloated_audio = True
    banned_groups: tuple[str, ...] = ()
    banned_url = f"{base_url}/api/banned-groups"
    banned_groups_auth_mode = "api_token"
    banned_groups_response_key = "groups"
    id_url = f"{base_url}/api/torrents/"
    upload_url = f"{base_url}/api/torrents/upload"
    search_url = f"{base_url}/api/torrents/filter"
    torrent_url = f"{base_url}/torrents/"
    requests_url = f"{base_url}/api/requests/filter"
    pending_url = f"{base_url}/api/torrents/pending"
    supported_categories = ("TV", "MOVIE", "BOOK", "GAME")
    tracker_urls = ("capybarabr.com",)

    def __init__(self, config: dict[str, Any]):
        super().__init__(config, tracker_name="CAPYBARABR")
        self.config = config
        self.common = Common(config)

    async def get_category_id(self, meta: Meta, category: str = "", reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        category_id: dict[str, str] = {"MOVIE": "1", "TV": "2", "ANIMES": "4", "BOOK": "11", "COMIC_MANGA": "10", "GAME": "5"}

        if mapping_only:
            return category_id
        if reverse:
            return {v: k for k, v in category_id.items()}

        resolved_category = category if category else meta.category
        if meta.anime is True and resolved_category == "TV":
            resolved_category = "ANIMES"

        if resolved_category == "BOOK" and (str(meta.type).upper() in ("CBR", "CBZ") or meta.manga or meta.comic):
            resolved_category = "COMIC_MANGA"

        if resolved_category:
            return {"category_id": category_id.get(resolved_category, "0")}

        return {"category_id": "0"}

    async def get_type_id(self, meta: Meta, type: str = "", reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        nin_term = (bytes([110, 105, 110, 116, 101, 110, 100, 111]).decode()).upper()
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
            f"{nin_term}": "50",
        }

        if mapping_only:
            return type_id
        if reverse:
            return {v: k for k, v in type_id.items()}

        resolved_type = type if type else meta.type
        if resolved_type == "GAME" or (meta.category == "GAME" and resolved_type not in type_id):
            platform = meta.platform.lower()
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
            resolved_id = type_id.get(str(resolved_type), "0")

        return {"type_id": resolved_id}

    async def get_resolution_id(self, meta: Meta, resolution: str = "", reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        resolution_id = {
            "4320p": "1",
            "2160p": "2",
            "1080p": "3",
            "1080i": "4",
            "720p": "5",
            "576p": "6",
            "576i": "7",
            "480p": "8",
            "480i": "9",
            "Other": "10",
        }

        if mapping_only:
            return resolution_id
        if reverse:
            return {v: k for k, v in resolution_id.items()}
        if resolution:
            return {"resolution_id": resolution_id.get(resolution, "10")}
        meta_resolution = meta.resolution
        resolved_id = resolution_id.get(meta_resolution, "10")
        return {"resolution_id": resolved_id}

    async def get_description(self, meta: Meta) -> dict[str, str]:
        signature = f"[right][url=https://github.com/wastaken7/Upload-Assistant][size=4]Compartilhado com {meta.ua_name} {meta.current_version} (fork)[/size][/url][/right]"
        return {"description": await DescriptionBuilder(self.tracker, self.config).unit3d_edit_desc(meta, signature=signature)}

    async def get_name(self, meta: Meta) -> dict[str, str]:
        category = meta.category
        cbr_name = meta.name

        if category == "BOOK":
            book_title = self.common.portuguese_title_capitalization(meta.title)
            year_str = str(meta.year) if meta.year is not None else ""
            cbr_name = f"{book_title} - {meta.author} [{year_str}] [AUDIOBOOK]" if meta.audiobook else f"{book_title} - {meta.author} [{year_str}]"
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
                game_lang = "[MULTI]"
            elif game_lang_has_eng:
                game_lang = "[INGLÊS]"
            else:
                game_lang = f"[{meta.language.upper()}]"

            game_subcategory = meta.game_subcategory.lower()
            update = "Update" if game_subcategory == "update" else ""
            dlc = "[DLC]" if game_subcategory == "dlc" else "[+DLC]" if game_subcategory == "full_game_dlc" else ""
            if dlc:
                dlc = f" {dlc}"

            year_str = str(meta.year) if meta.year is not None else ""
            cbr_name = f"{meta.title} {update} {meta.game_version} {year_str} - {tag} {game_lang}{dlc}"

        elif category in ("MOVIE", "TV"):
            cbr_name = cbr_name.replace("DD+ ", "DDP").replace("DD ", "DD").replace("AAC ", "AAC").replace("FLAC ", "FLAC").replace("Dubbed", "").replace("Dual-Audio", "")

            # If it is a Series or Anime, remove the year from the title.
            if meta.category in ["TV", "ANIMES"]:
                year_str = str(meta.year) if meta.year is not None else ""
                if year_str and year_str in cbr_name:
                    cbr_name = cbr_name.replace(f"({year_str})", "").replace(year_str, "").strip()

            # Remove the AKA title, unless it is Brazilian
            if meta.original_language != "pt":
                cbr_name = cbr_name.replace(meta.aka, "")

            # If it is Brazilian, use only the AKA title, deleting the foreign title
            if meta.original_language == "pt" and meta.aka:
                aka_clean = meta.aka.replace("AKA", "").strip()
                title = meta.title
                cbr_name = cbr_name.replace(meta.aka, "").replace(title, aka_clean).strip()

            if self.tracker == "CAPYBARABR" and meta.type == "DVDRIP":
                title = meta.aka.replace("AKA", "").strip() if meta.original_language == "pt" and meta.aka else meta.title
                episode = f"{meta.season}{meta.episode}" if category == "TV" else ""
                audio = str(meta.audio).replace("DD+ ", "DDP").replace("DD ", "DD").replace("AAC ", "AAC").replace("FLAC ", "FLAC")
                cbr_name = " ".join(part for part in (title, str(meta.year or ""), episode, meta.resolution, "DVDRip", audio, meta.video_encode) if part)
                if meta.tag:
                    cbr_name += meta.tag

            tag_lower = "" if not meta.tag else meta.tag.lower()
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

                        match = None
                        for source_name in (meta.path, meta.uuid):
                            if source_name:
                                match = re.search(r"-([^.-]+)\.(?:DUAL|MULTI)(?=-|\.|$)", str(source_name), re.IGNORECASE)
                                if match:
                                    break
                        current_group_tag = (meta.tag or "").lstrip("-")
                        if match and match.group(1).casefold() != current_group_tag.casefold():
                            cbr_name = f"{parts[0]}-{match.group(1)}{audio_tag}-{parts[1]}"
                        else:
                            cbr_name = f"{parts[0]}{audio_tag}-{parts[1]}"
                    else:
                        cbr_name += audio_tag

            if not meta.tag or any(invalid_tag in tag_lower for invalid_tag in invalid_tags):
                for invalid_tag in invalid_tags:
                    cbr_name = re.sub(f"-{invalid_tag}", "", cbr_name, flags=re.IGNORECASE)
                cbr_name = f"{cbr_name}-NoGroup"

        return {"name": re.sub(r"\s{2,}", " ", cbr_name)}

    async def get_additional_data(self, meta: Meta) -> dict[str, str]:
        return {
            "mod_queue_opt_in": await self.get_flag(meta, "modq"),
        }

    async def get_additional_checks(self, meta: Meta) -> bool:
        if meta.category == "BOOK" and meta.audiobook and not meta.narrator:
            logger.info(f"{self.tracker}: [bold red]Narrator is required for audiobooks. Skipping upload...[/bold red]")
            return False

        if meta.category in ["MOVIE", "TV"]:
            upload_type = str(meta.type).lower()
            upload_source = str(meta.source).lower()

            # Encodes must include the "Encode settings" field in the MediaInfo.
            if upload_type == "encode" and not meta.has_encode_settings:
                logger.info(f"{self.tracker}: [bold red]'Encode settings' field in the MediaInfo is required for encodes. Skipping upload...[/bold red]")
                return False

            # Blu-ray remuxes that include encode settings must also include BDInfo.
            if (
                upload_type == "remux"
                and (upload_source == "bluray" or upload_source == "blu-ray")
                and meta.has_encode_settings
                and not self.common.has_bdinfo(f"{meta.description}\n{meta.description_link_content}\n{meta.description_file_content}")
            ):
                logger.info(
                    f"{self.tracker}: [bold red]"
                    "BDInfo is required for Blu-ray remuxes that include 'Encode settings' field in the MediaInfo. "
                    "You can add BDInfo to the description using -df (path/to/file.txt) "
                    "or -pb (Pastebin link). "
                    "Skipping upload..."
                    "[/bold red]"
                )
                return False

            return await self.common.check_portuguese_video_requirements(meta, self.tracker)

        return True
