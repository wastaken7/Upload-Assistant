# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import re
from typing import Any

from src.console import logger
from src.meta import Meta
from src.trackers.common import Common
from src.trackers.naming import BLU_EDITION_TERMS, VideoNameRules, add_incomplete_pack_marker, build_video_name
from src.trackers.UNIT3D import UNIT3D

# Aither keeps editions (Criterion, Remastered, Anniversary...) in the description; cuts stay in the title.
AITHER_EDITION_TERMS = re.compile(
    rf"{BLU_EDITION_TERMS.pattern}|\brestored\b|\bmultiple(?:\s+languages)?\b",
    re.IGNORECASE,
)
AITHER_NAME_RULES = VideoNameRules(
    language_slot="before_cut",
    english_dub_only=True,
    edition_terms=AITHER_EDITION_TERMS,
    dvd_resolution=True,
    dvd_video_codec=True,
    three_d_slot="source_on_discs",
    honor_manual_year_on_tv=True,
)


class Aither(UNIT3D):
    """
    Aither is a Private Torrent Tracker for HD MOVIES / TV

    API spec: https://aither.cc/pages/api
    Synced with: last edited October 19, 2026.
    """

    tracker = "AITHER"
    display_name = "Aither"
    base_url = "https://aither.cc"
    banned_groups: tuple[str, ...] = ()
    banned_url = f"{base_url}/api/blacklists/releasegroups"
    claims_url = f"{base_url}/api/internals/claim"
    id_url = f"{base_url}/api/torrents/"
    upload_url = f"{base_url}/api/torrents/upload"
    search_url = f"{base_url}/api/torrents/filter"
    torrent_url = f"{base_url}/torrents/"
    requests_url = f"{base_url}/api/requests/filter"
    trumping_url = f"{base_url}/api/trumping-reports/filter"
    supported_categories = ("TV", "MOVIE")
    tracker_urls = ("https://aither.cc",)
    allowed_bloated_audio_languages = ("en",)

    def __init__(self, config: dict[str, Any]):
        super().__init__(config, tracker_name="AITHER")
        self.config = config
        self.common = Common(config)

    async def get_category_id(self, meta: Meta, category: str = "", reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        category_id = {
            "MOVIE": "1",
            "TV": "2",
            "SPORTS": "9",
        }
        if mapping_only:
            return category_id
        if reverse:
            return {value: key for key, value in category_id.items()}

        resolved_category = "SPORTS" if meta.is_sports else category or meta.category
        return {"category_id": category_id.get(resolved_category, "0")}

    async def get_resolution_id(self, meta: Meta, resolution: str = "", reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        # Aither has its own 1440p resolution (id 42) instead of grouping it with 1080p.
        resolution_id = {
            "8640p": "10",
            "4320p": "1",
            "2160p": "2",
            "1440p": "42",
            "1080p": "3",
            "1080i": "4",
            "720p": "5",
            "576p": "6",
            "576i": "7",
            "480p": "8",
            "480i": "9",
        }
        if mapping_only:
            return resolution_id
        if reverse:
            return {value: key for key, value in resolution_id.items()}
        return {"resolution_id": resolution_id.get(resolution or meta.resolution, "10")}

    async def get_season_number(self, meta: Meta) -> dict[str, str]:
        if (await self.get_category_id(meta))["category_id"] != "2":
            return {}
        return await super().get_season_number(meta)

    async def get_episode_number(self, meta: Meta) -> dict[str, str]:
        if (await self.get_category_id(meta))["category_id"] != "2":
            return {}
        return await super().get_episode_number(meta)

    async def get_additional_checks(self, meta: Meta):
        should_continue = True

        if meta.is_disc not in ["BDMV", "DVD"] and not await self.common.check_language_requirements(
            meta, self.tracker, languages_to_check=["english"], check_audio=True, check_subtitle=True, original_language=True, original_required=True
        ):
            return False

        if meta.valid_mi is False:
            logger.info(f"{self.tracker}: [bold red]No unique ID in mediainfo, skipping {self.tracker} upload.")
            return False

        return should_continue

    async def get_additional_data(self, meta: Meta):
        hdr_value = meta.hdr or ""
        has_hdr10p = "HDR10+" in hdr_value

        data: dict[str, Any] = {
            "mod_queue_opt_in": await self.get_flag(meta, "modq"),
        }
        if "DV" in hdr_value:
            data["dv"] = 1
        if has_hdr10p:
            data["hdr10p"] = 1
        elif not has_hdr10p and any(flag in hdr_value for flag in ["HDR", "HLG"]):
            data["hdr"] = 1

        if await self.get_flag(meta, "refundable") == "1":
            data["refundable"] = "1"

        freeleech_until = meta.get("freeleech_until", 0) or self.tracker_config.get("freeleech_until", 0)
        if freeleech_until:
            try:
                fl_until_val = int(freeleech_until)
                if fl_until_val > 0:
                    data["fl_until"] = fl_until_val
            except ValueError, TypeError:
                pass

        double_upload_until = meta.get("double_upload_until", 0) or self.tracker_config.get("double_upload_until", 0)
        if double_upload_until:
            try:
                du_until_val = int(double_upload_until)
                if du_until_val > 0:
                    data["du_until"] = du_until_val
            except ValueError, TypeError:
                pass

        return data

    async def get_name(self, meta: Meta):
        # A manual --name or a type outside the guide falls back to the generic name.
        aither_name = await build_video_name(meta, AITHER_NAME_RULES, self.tracker) or meta.name
        if meta.trump_reason == "exact_match":
            aither_name = aither_name + " - TRUMP"
        return {"name": add_incomplete_pack_marker(aither_name, meta, self.tracker)}
