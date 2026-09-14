# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
from typing import Any, ClassVar

from src.console import logger
from src.languages import languages_manager
from src.meta import Meta
from src.release_name import NameContext, NameRule, NameSelector, TrackerNameProfile, template
from src.trackers.common import Common
from src.trackers.naming import aither_name
from src.trackers.UNIT3D import UNIT3D


class Aither(UNIT3D):
    """
    Aither is a Private Torrent Tracker for HD MOVIES / TV
    """

    tracker = "AITHER"
    name_profile = TrackerNameProfile(
        rules=(NameRule(NameSelector(), template("base_name")),),
        transforms=(aither_name,),
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
            return {"year": year, "foreign_language": languages[0].upper()}
        return {"year": year}

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
    REGION_IDS: ClassVar[dict[str, str]] = {
        "FIN": "244",
        "SWE": "246",
        "CZE": "247",
        "EST": "248",
    }

    def __init__(self, config: dict[str, Any]):
        super().__init__(config, tracker_name="AITHER")
        self.config = config
        self.common = Common(config)

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
            data["refundable"] = True

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

    async def get_region_id(self, meta: Meta) -> dict[str, str]:
        region_id = self.REGION_IDS.get(str(meta.region or "").upper())
        if region_id:
            return {"region_id": region_id}
        return await super().get_region_id(meta)

    async def get_region_name(self, region_id: int | str | None) -> str:
        region_name = {value: key for key, value in self.REGION_IDS.items()}.get(str(region_id), "")
        if region_name:
            return region_name
        try:
            normalized_id = int(region_id) if region_id is not None else 0
        except TypeError, ValueError:
            return ""
        return await self.common.unit3d_region_ids(reverse=True, region_id=normalized_id)
