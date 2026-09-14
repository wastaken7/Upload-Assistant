# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
from typing import Any, cast

import cli_ui

from src.console import logger
from src.languages import languages_manager
from src.meta import Meta
from src.release_name import NameContext, NameRule, NameSelector, TrackerNameProfile, template
from src.trackers.common import Common
from src.trackers.UNIT3D import UNIT3D

Config = dict[str, Any]


class Torrenteros(UNIT3D):
    """
    Torrenteros (TTR) is a SPANISH Torrent Tracker for MOVIES / TV / GENERAL
    """

    tracker = "TORRENTEROS"
    name_profile = TrackerNameProfile(rules=(NameRule(NameSelector(), template("ttr_base", "spanish_suffix", "direct_tag", separator="")),))
    display_name = "Torrenteros"
    base_url = "https://torrenteros.org"
    banned_groups = ()
    ttr_name_parts: dict[str, str] | None = None
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

    @staticmethod
    def _spanish_type(language: str) -> str | None:
        language = language.lower()
        if language in ("es-es", "es", "spa"):
            return "Castellano"
        return "Latino" if language.startswith("es-") else None

    def _ask_spanish_type(self, kind: str, *, subtitles: bool = False) -> str:
        logger.info(f"{self.tracker}: [green]Found Spanish {kind} track.[/green] [yellow]Is it Castellano or Latino?[/yellow]")
        logger.info(f"{self.tracker}: 1 = Castellano")
        logger.info(f"{self.tracker}: 2 = Latino")
        logger.info(f"{self.tracker}: 3 = Castellano Latino")
        choice = str(cli_ui.ask_string("Enter choice (1-3): "))
        values = {"1": "Castellano", "2": "Latino", "3": "Castellano Latino"}
        return f"{values.get(choice, 'Castellano')}{' Subs' if subtitles else ''}"

    async def get_name_overrides(self, context: NameContext) -> dict[str, str]:
        if self.ttr_name_parts is not None:
            return dict(self.ttr_name_parts)
        meta = context.meta
        suffix = ""
        if meta.is_disc == "BDMV":
            if "Spanish" in (meta.audio_languages or []):
                suffix = "Castellano" if meta.unattended or meta.unattended_confirm else self._ask_spanish_type("audio")
            elif "Spanish" in (meta.subtitle_languages or []):
                suffix = "Castellano Subs" if meta.unattended or meta.unattended_confirm else self._ask_spanish_type("subtitle", subtitles=True)
        else:
            tracks = cast(list[dict[str, Any]], meta.mediainfo.get("media", {}).get("track", []))
            audio = next((self._spanish_type(str(track.get("Language", "")).strip()) for track in tracks if track.get("@type") == "Audio" and not isinstance(track.get("Language", ""), dict) and self._spanish_type(str(track.get("Language", "")).strip())), None)
            subtitles = next((self._spanish_type(str(track.get("Language", "")).strip()) for track in tracks if track.get("@type") == "Text" and not isinstance(track.get("Language", ""), dict) and self._spanish_type(str(track.get("Language", "")).strip())), None)
            suffix = audio if audio else f"{subtitles} Subs" if subtitles else ""
        parts = {
            "ttr_base": meta.name_notag,
            "spanish_suffix": f" {suffix}" if suffix else "",
            "direct_tag": meta.tag or "",
        }
        self.ttr_name_parts = parts
        return dict(parts)

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
            if meta.unattended:
                if not meta.unattended_confirm:
                    return False
            else:
                logger.info(f"{self.tracker}: [yellow]No Spanish audio track found, but Spanish subtitles are present.[/yellow]")
                if not cli_ui.ask_yes_no("Do you want to upload anyway?", default=False):
                    return False

        return True
