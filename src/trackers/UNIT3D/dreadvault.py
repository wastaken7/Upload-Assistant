# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import re
from typing import Any, cast

import cli_ui

from src.console import logger
from src.languages import languages_manager
from src.meta import Meta
from src.release_name import NameContext, NameRule, NameSelector, TrackerNameProfile, template
from src.trackers.common import Common
from src.trackers.naming import dreadvault_name
from src.trackers.UNIT3D import UNIT3D

Config = dict[str, Any]


class DreadVault(UNIT3D):
    """
    DreadVault (DV) is a Private Torrent Tracker for HORROR MOVIES / TV
    """

    tracker = "DREADVAULT"
    name_profile = TrackerNameProfile(
        rules=(NameRule(NameSelector(), template("base_name")),),
        transforms=(dreadvault_name,),
    )

    async def get_name_overrides(self, context: NameContext) -> dict[str, str]:
        meta = context.meta
        year = str(meta.year) if meta.year is not None else ""
        if meta.category == "TV":
            year = str(meta.year) if meta.year is not None and meta.search_year != "" else ""
        manual_year = str(meta.manual_year)
        if manual_year and int(manual_year) > 0:
            year = manual_year
        if meta.no_year:
            year = ""
        if not meta.language_checked:
            await languages_manager.process_desc_language(meta, tracker=self.tracker)
        languages = [] if not meta.audio_languages else meta.audio_languages
        if languages and not await languages_manager.has_english_language(languages):
            return {"year": year, "foreign_language": str(languages[0]).upper()}
        return {"year": year}

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
