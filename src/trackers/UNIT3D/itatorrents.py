# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
from typing import Any

from src.console import logger
from src.languages import languages_manager
from src.meta import Meta
from src.release_name import NameContext, NameRule, NameSelector, TrackerNameProfile, collapse_whitespace, replace_text, template
from src.trackers.common import Common
from src.trackers.naming import append_context_value
from src.trackers.UNIT3D import UNIT3D

Config = dict[str, Any]


class ItaTorrents(UNIT3D):
    """
    ItaTorrents is an ITALIAN Private tracker for MOVIES / TV / GENERAL
    """

    tracker = "ITATORRENTS"
    name_profile = TrackerNameProfile(
        rules=(
            NameRule(
                NameSelector(type="DISC"),
                template(
                    "title",
                    "year",
                    "season_episode",
                    "repack",
                    "resolution",
                    "edition",
                    "region",
                    "three_d",
                    "source",
                    "resolved_type_label",
                    "hdr",
                    "video_codec",
                    "dubs",
                    "audio",
                ),
            ),
            NameRule(
                NameSelector(type="REMUX"),
                template(
                    "title",
                    "year",
                    "season_episode",
                    "repack",
                    "resolution",
                    "edition",
                    "region",
                    "three_d",
                    "source",
                    "resolved_type_label",
                    "hdr",
                    "video_codec",
                    "dubs",
                    "audio",
                ),
            ),
            NameRule(
                NameSelector(),
                template("title", "year", "season_episode", "repack", "resolution", "edition", "three_d", "resolved_type_label", "dubs", "audio", "hdr", "video_codec"),
            ),
        ),
        transforms=(collapse_whitespace, append_context_value("tag"), replace_text(("Dubbed", ""), ("Dual-Audio", ""))),
    )

    async def get_name_overrides(self, context: NameContext) -> dict[str, str]:
        meta = context.meta
        resolved = await self.get_type_name(meta) or ""
        label = (
            "REMUX"
            if resolved == "REMUX"
            else ""
            if resolved == "DISC"
            else resolved.replace("WEBDL", "WEB-DL").replace("WEBRIP", "WEBRip").replace("DVDRIP", "DVDRip").replace("ENCODE", "BluRay")
        )
        return {"edition": meta.edition, "dubs": await self.get_dubs(meta), "resolved_type_label": label}

    display_name = "ItaTorrents"
    base_url = "https://itatorrents.xyz"
    banned_groups = ()
    id_url = f"{base_url}/api/torrents/"
    upload_url = f"{base_url}/api/torrents/upload"
    requests_url = f"{base_url}/api/requests/filter"
    search_url = f"{base_url}/api/torrents/filter"
    torrent_url = f"{base_url}/torrents/"
    supported_categories = ("TV", "MOVIE")
    tracker_urls = ("https://itatorrents.xyz",)
    allowed_bloated_audio_languages = ("it",)

    def __init__(self, config: Config) -> None:
        super().__init__(config, tracker_name="ITATORRENTS")
        self.config: Config = config
        self.common = Common(config)

    async def get_type_name(self, meta: Meta) -> str | None:
        type_name: str | None = None

        uuid_string = meta.basename_no_ext
        if uuid_string:
            lower_uuid = uuid_string.lower()

            if "dlmux" in lower_uuid:
                type_name = "DLMux"
            elif "bdmux" in lower_uuid:
                type_name = "BDMux"
            elif "webmux" in lower_uuid:
                type_name = "WEBMux"
            elif "dvdmux" in lower_uuid:
                type_name = "DVDMux"
            elif "bdrip" in lower_uuid:
                type_name = "BDRip"

        if type_name is None:
            type_value = meta.type
            type_name = str(type_value) if type_value else None

        return type_name

    async def get_type_id(self, meta: Meta, type: str | None = None, reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        type_id_map = {
            "DISC": "1",
            "REMUX": "2",
            "WEBDL": "4",
            "WEBRIP": "5",
            "HDTV": "6",
            "ENCODE": "3",
            "DLMux": "27",
            "BDMux": "29",
            "WEBMux": "26",
            "DVDMux": "39",
            "BDRip": "25",
            "DVDRIP": "24",
            "Cinema-MD": "14",
        }
        if mapping_only:
            return type_id_map
        if reverse:
            return {v: k for k, v in type_id_map.items()}
        if type is not None:
            return {"type_id": type_id_map.get(type, "0")}

        resolved_type = await self.get_type_name(meta)
        type_id = type_id_map.get(resolved_type or "", "0")

        return {"type_id": type_id}

    async def get_dubs(self, meta: Meta) -> str:
        if not meta.language_checked:
            await languages_manager.process_desc_language(meta, tracker=self.tracker)
        dubs = ""
        audio_languages_value = meta.audio_languages
        audio_languages: set[str] = set()
        if isinstance(audio_languages_value, list):
            audio_languages_list = audio_languages_value
            audio_languages = {str(lang) for lang in audio_languages_list}
        if audio_languages:
            dubs = " ".join(lang[:3].upper() for lang in audio_languages)
        return dubs

    async def get_additional_checks(self, meta: Meta) -> bool:
        # From rules:
        # "Non sono ammessi film e serie tv che non comprendono il doppiaggio in italiano."
        # Translates to "Films and TV series that do not include Italian dubbing are not permitted."
        italian_languages = ["italian", "italiano"]
        if not await self.common.check_language_requirements(meta, self.tracker, languages_to_check=italian_languages, check_audio=True):
            logger.info(f"{self.tracker}: Upload Rules: https://itatorrents.xyz/wikis/5")
            return False
        return True
