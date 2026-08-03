# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import re
import unicodedata
from pathlib import Path
from typing import Any

import cli_ui

from src.console import console
from src.languages import languages_manager
from src.meta import Meta
from src.trackers.UNIT3D import UNIT3D

Config = dict[str, Any]


class NordicQuality(UNIT3D):
    """NordicQuality UNIT3D tracker adapter."""

    tracker = "NORDICQUALITY"
    display_name = "NordicQuality"
    base_url = "https://nordicq.org"
    banned_groups: tuple[str, ...] = ()
    id_url = f"{base_url}/api/torrents/"
    upload_url = f"{base_url}/api/torrents/upload"
    search_url = f"{base_url}/api/torrents/filter"
    torrent_url = f"{base_url}/torrents/"
    supported_categories = ("TV", "MOVIE")
    tracker_urls = (base_url,)
    NORDIC_LANGUAGE_TOKENS = frozenset(
        {
            "da",
            "dan",
            "danish",
            "fi",
            "fin",
            "finnish",
            "ice",
            "icelandic",
            "is",
            "isl",
            "no",
            "nno",
            "nob",
            "nor",
            "norwegian",
            "sv",
            "swe",
            "swedish",
        }
    )

    def __init__(self, config: Config) -> None:
        super().__init__(config, tracker_name=self.tracker)

    @staticmethod
    def _language_values(languages: Any) -> list[str]:
        if isinstance(languages, str):
            return [languages]
        if isinstance(languages, list):
            return [language for language in languages if isinstance(language, str)]
        return []

    @classmethod
    def _language_tokens(cls, languages: Any) -> set[str]:
        tokens: set[str] = set()
        for language in cls._language_values(languages):
            normalized = unicodedata.normalize("NFKD", language)
            normalized = "".join(character for character in normalized if not unicodedata.combining(character))
            tokens.update(re.findall(r"[a-z0-9]+", normalized.casefold()))
        return tokens

    async def get_additional_checks(self, meta: Meta) -> bool:
        if meta.category not in {"MOVIE", "TV"}:
            return True

        if not meta.language_checked:
            await languages_manager.process_desc_language(meta, tracker=self.tracker)

        console.print(f"[yellow]{self.tracker}: Checking file for approved Nordic subtitles...[/yellow]")
        subtitle_languages = meta.subtitle_languages
        subtitle_tokens = self._language_tokens(subtitle_languages)

        if self.NORDIC_LANGUAGE_TOKENS.intersection(subtitle_tokens):
            nordic_subtitles = [
                subtitle
                for subtitle in self._language_values(subtitle_languages)
                if self.NORDIC_LANGUAGE_TOKENS.intersection(self._language_tokens(subtitle))
            ]
            console.print(f"[green]{self.tracker}: Nordic subtitle requirement met: {', '.join(nordic_subtitles)}[/green]")
            return meta.unattended or cli_ui.ask_yes_no("Do you wish to continue uploading?", default=False)

        subtitle_display = ", ".join(subtitle_languages) if isinstance(subtitle_languages, list) else str(subtitle_languages or "None")
        console.print(
            f"[bold red]{self.tracker} requires at least one Nordic subtitle for Movie and TV uploads.\n"
            f"Found Subtitles: {subtitle_display}[/bold red]"
        )
        return False

    async def get_name(self, meta: Meta) -> dict[str, str]:
        name = Path(meta.uuid).stem.replace(" ", ".")

        name = name.translate(
            str.maketrans(
                {
                    "\u00c6": "AE",
                    "\u00e6": "ae",
                    "\u00d0": "D",
                    "\u00f0": "d",
                    "\u00d8": "O",
                    "\u00f8": "o",
                    "\u00de": "TH",
                    "\u00fe": "th",
                    "\u00c5": "A",
                    "\u00e5": "a",
                    "\u0152": "OE",
                    "\u0153": "oe",
                    "\u00df": "ss",
                }
            )
        )

        name = name.replace("HDR10+", "HDR10P").replace("DD+", "DDP").replace("DTS:X", "DTS-X").replace("&", "and")
        name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
        name = re.sub(r"[^A-Za-z0-9._()\-]+", ".", name)
        name = re.sub(r"\.{2,}", ".", name).strip(".")

        console.print(f"[cyan]Name: {name}")
        return {"name": name}
