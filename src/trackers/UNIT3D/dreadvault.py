# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import re
from typing import Any, cast

import cli_ui

from src.console import logger
from src.languages import languages_manager
from src.meta import Meta
from src.trackers.common import Common
from src.trackers.UNIT3D import UNIT3D

Config = dict[str, Any]


class DreadVault(UNIT3D):
    """
    DreadVault (DV) is a Private Torrent Tracker for HORROR MOVIES / TV
    """

    tracker = "DREADVAULT"
    display_name = "DreadVault"
    allows_bloated_audio = True
    base_url = "https://dreadvault.org"
    banned_groups = (
        "AOC",
        "AOS",
        "BONE",
        "EVO",
        "FGT",
        "LAMA",
        "NeoNoir",
        "PSA",
        "RARBG",
        "VXT",
        "YIFY",
        "YTS",
    )
    id_url = f"{base_url}/api/torrents/"
    upload_url = f"{base_url}/api/torrents/upload"
    requests_url = f"{base_url}/api/requests/filter"
    search_url = f"{base_url}/api/torrents/filter"
    torrent_url = f"{base_url}/torrents/"
    supported_categories = ("TV", "MOVIE")
    tracker_urls = ("https://dreadvault.org",)
    # site rules allow coexisting releases; only a literal duplicate (same files
    # and size) is a dupe
    exact_match_only = True

    def __init__(self, config: Config) -> None:
        super().__init__(config, tracker_name="DREADVAULT")
        self.config: Config = config
        self.common = Common(config)

    async def get_name(self, meta: Meta) -> dict[str, str]:
        dreadvault_name: str = meta.name
        resolution: str = meta.resolution
        video_codec: str = meta.video_codec
        video_encode: str = meta.video_encode
        name_type: str = meta.type or ""
        source: str = meta.source or ""
        alt_title = meta.aka if not meta.no_aka else ""

        year = str(meta.year) if meta.year is not None else ""
        if meta.category == "TV":
            year = str(meta.year) if (meta.year is not None and meta.search_year != "") else ""
        manual_year_value = str(meta.manual_year)
        if manual_year_value and int(manual_year_value) > 0:
            year = manual_year_value
        if meta.no_year:
            year = ""

        if name_type == "DVDRIP":
            source = "DVDRip"
            encode_token = video_encode.strip()
            dreadvault_name = dreadvault_name.replace(f"{meta.source} ", "", 1)
            dreadvault_name = dreadvault_name.replace(f" {encode_token}", "", 1)
            dreadvault_name = dreadvault_name.replace(f"{source}", f"{resolution} {source}", 1)
            dreadvault_name = dreadvault_name.replace((meta.audio), f"{meta.audio} {encode_token}", 1)

        elif meta.is_disc == "DVD":
            region_and_source = " ".join(part for part in (meta.region, source) if part)
            disc_details = " ".join(part for part in (resolution, meta.region, source) if part)
            if region_and_source:
                dreadvault_name = dreadvault_name.replace(region_and_source, disc_details, 1)
            dreadvault_name = dreadvault_name.replace((meta.audio), f"{video_codec} {meta.audio}", 1)

        elif name_type == "REMUX" and source in ("PAL DVD", "NTSC DVD", "DVD"):
            dreadvault_name = dreadvault_name.replace(meta.source or "", f"{resolution} {meta.source}", 1)
            dreadvault_name = dreadvault_name.replace((meta.audio), f"{video_codec} {meta.audio}", 1)

        if alt_title and year:
            dreadvault_name = dreadvault_name.replace(f"{year} {alt_title}", f"{alt_title} {year}", 1)

        # The marker goes immediately before the resolution, so it has to run AFTER the branches
        # above: the DVDRip and DVD-disc templates carry no resolution of their own, and those
        # branches are what insert it. Running first silently dropped the marker on both.
        if not meta.language_checked:
            await languages_manager.process_desc_language(meta, tracker=self.tracker)
        audio_languages: list[str] = [] if not meta.audio_languages else meta.audio_languages
        if audio_languages and not await languages_manager.has_english_language(audio_languages):
            foreign_lang = audio_languages[0].upper()
            dvd_remux = name_type == "REMUX" and source in ("PAL DVD", "NTSC DVD", "DVD")
            if dvd_remux and year:
                dreadvault_name = dreadvault_name.replace(year, f"{year} {foreign_lang}", 1)
            elif meta.is_disc != "BDMV":
                # get_name drops the resolution token when it is OTHER; the next slot anchors the marker:
                # the service on a web release, the source everywhere else.
                for anchor in (meta.resolution, str(meta.service), source):
                    if anchor and anchor in dreadvault_name:
                        dreadvault_name = dreadvault_name.replace(anchor, f"{foreign_lang} {anchor}", 1)
                        break

        return {"name": dreadvault_name}

    async def get_additional_checks(self, meta: Meta) -> bool:
        combined_genres_value = meta.combined_genres
        if isinstance(combined_genres_value, list):
            combined_genres = cast(list[str], combined_genres_value)
        else:
            combined_genres = [genre.strip() for genre in str(combined_genres_value).split(",") if genre.strip()]

        # substring per term: the horror signal is often a compound keyword
        searchable = {term.lower() for term in [*combined_genres, *meta.keywords]}
        if not any("horror" in term for term in searchable):
            if not meta.unattended or (meta.unattended and meta.unattended_confirm):
                logger.info(f"{self.tracker}: [bold red]Only horror content is allowed at {self.tracker}.[/bold red]")
                if cli_ui.ask_yes_no("Do you want to upload anyway?", default=False):
                    pass
                else:
                    return False
            else:
                return False

        genres = ", ".join([*meta.keywords, *combined_genres])
        # only terms that never appear as TMDB keywords on legitimate horror
        adult_keywords = ["xxx", "porn", "adult", "hentai", "softcore"]
        if any(re.search(rf"(^|,\s*){re.escape(keyword)}(\s*,|$)", genres, re.IGNORECASE) for keyword in adult_keywords):
            if not meta.unattended or (meta.unattended and meta.unattended_confirm):
                logger.info(f"{self.tracker}: [bold red]Porn/xxx is not allowed at {self.tracker}.[/bold red]")
                if cli_ui.ask_yes_no("Do you want to upload anyway?", default=False):
                    pass
                else:
                    return False
            else:
                return False

        return self.common.check_and_confirm_adult_media_upload(meta, self.tracker)
