# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
from typing import Any, cast

from src.console import logger
from src.languages import languages_manager
from src.manual_input import Question, ask, choices_from, confirm_override
from src.meta import Meta
from src.trackers.common import Common
from src.trackers.UNIT3D import UNIT3D

Config = dict[str, Any]


class Torrenteros(UNIT3D):
    """
    Torrenteros (TTR) is a SPANISH Torrent Tracker for MOVIES / TV / GENERAL
    """

    tracker = "TORRENTEROS"
    display_name = "Torrenteros"
    base_url = "https://torrenteros.org"
    banned_groups = ()
    ttr_name = ""  # Initialize instance variable
    id_url = f"{base_url}/api/torrents/"
    upload_url = f"{base_url}/api/torrents/upload"
    search_url = f"{base_url}/api/torrents/filter"
    torrent_url = f"{base_url}/torrents/"
    supported_categories = ("TV", "MOVIE")
    tracker_urls = ("https://torrenteros.org",)
    allowed_bloated_audio_languages = ("es",)

    def __init__(self, config: Config) -> None:
        super().__init__(config, tracker_name="TORRENTEROS")
        self.config: Config = config
        self.common = Common(config)

    async def get_name(self, meta: Meta) -> dict[str, str]:
        if meta.manual_name is not None:
            return {"name": meta.manual_name.strip()}

        name = self.ttr_name or await self.build_name(meta)

        return {"name": name}

    async def build_name(self, meta: Meta) -> str:
        name = meta.name_notag

        async def ask_spanish_type(kind: str) -> str:
            variant = await ask(
                meta,
                Question(
                    key="torrenteros.spanish_variant",
                    kind="choice",
                    prompt=f"{self.tracker}: Found Spanish {kind} track. Is it Castellano or Latino?",
                    title="Spanish variant",
                    choices=choices_from(["Castellano", "Latino", "Castellano Latino"]),
                    default="Castellano",
                    summary={"Tracker": self.tracker, "Release": meta.name, "Track": kind},
                    tracker=self.tracker,
                    unattended="default",
                ),
            )
            return str(variant or "Castellano")

        def get_spanish_type(lang_code: str) -> str | None:
            if not lang_code:
                return None
            lang_code = lang_code.lower()
            if lang_code in ("es-es", "es", "spa"):
                return "Castellano"
            if lang_code.startswith("es-"):
                return "Latino"
            return None

        if meta.is_disc == "BDMV":
            spanish_audio = "Spanish" in (meta.audio_languages or [])
            spanish_subtitle = "Spanish" in (meta.subtitle_languages or [])
            if spanish_audio:
                name += f" {await ask_spanish_type('audio')}"

            elif spanish_subtitle:
                name += f" {await ask_spanish_type('subtitle')} Subs"

        else:
            tracks = cast(
                list[dict[str, Any]],
                meta.mediainfo.get("media", {}).get("track", []),
            )
            spanish_audio_type = None
            spanish_subs_type = None

            for track in tracks:
                if track.get("@type") == "Audio":
                    lang = track.get("Language", "")
                    if isinstance(lang, dict):
                        lang = ""
                    spanish_audio_type = get_spanish_type(str(lang).strip())
                    if spanish_audio_type:
                        break

            for track in tracks:
                if track.get("@type") == "Text":
                    lang = track.get("Language", "")
                    if isinstance(lang, dict):
                        lang = ""
                    spanish_subs_type = get_spanish_type(str(lang).strip())
                    if spanish_subs_type:
                        break

            if spanish_audio_type:
                name += f" {spanish_audio_type}"
            elif spanish_subs_type:
                name += f" {spanish_subs_type} Subs"

        tag = meta.tag
        if tag:
            name += tag

        self.ttr_name = name

        return name

    async def get_additional_data(self, meta: Meta) -> dict[str, Any]:
        data: dict[str, Any] = {
            "mod_queue_opt_in": await self.get_flag(meta, "modq"),
        }

        return data

    async def get_additional_checks(self, meta: Meta) -> bool:
        if not meta.language_checked:
            await languages_manager.process_desc_language(meta, tracker=self.tracker)

        if "Spanish" not in (meta.audio_languages or []):
            if "Spanish" not in (meta.subtitle_languages or []):
                logger.info(f"{self.tracker}: [bold red]requires at least one Spanish audio or subtitle track.")
                return False
            logger.info(f"{self.tracker}: [yellow]No Spanish audio track found, but Spanish subtitles are present.[/yellow]")
            if not await confirm_override(meta):
                return False

        return True
