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


def _remove_last(name: str, token: str) -> str:
    if not token:
        return name
    # Padding makes the matched leading space's index equal the token's index in name.
    start = max(f" {name} ".rfind(f" {token}{boundary}") for boundary in (" ", "-"))
    if start < 0:
        return name
    end = start + len(token)
    if name[end : end + 1] == " ":
        return name[:start] + name[end + 1 :]
    return name[: max(0, start - 1)] + name[end:]


def _replace_last(name: str, token: str, replacement: str) -> str:
    if not token:
        return name
    start = max(f" {name} ".rfind(f" {token}{boundary}") for boundary in (" ", "-"))
    if start < 0:
        return name
    return name[:start] + replacement + name[start + len(token) :]


def _insert_before_last(name: str, token: str, prefix: str) -> str:
    if not token or not prefix:
        return name
    start = max(f" {name} ".rfind(f" {token}{boundary}") for boundary in (" ", "-"))
    if start < 0 or f" {name[:start]}".endswith(f" {prefix} "):
        return name
    return name[:start] + f"{prefix} " + name[start:]


def _insert_after_last(name: str, token: str, suffix: str) -> str:
    if not token or not suffix:
        return name
    start = max(f" {name} ".rfind(f" {token}{boundary}") for boundary in (" ", "-"))
    if start < 0:
        return name
    end = start + len(token)
    if f"{name[end:]} ".startswith((f" {suffix} ", f" {suffix}-")):
        return name
    return name[:end] + f" {suffix}" + name[end:]


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
        resolution: str = meta.resolution if meta.resolution != "OTHER" else ""
        video_encode: str = meta.video_encode
        name_type: str = meta.type or ""
        source: str = meta.source or ""
        alt_title = meta.aka if not meta.no_aka else ""
        full_disc = name_type == "DISC"
        dvd_encode = name_type == "ENCODE" and source in ("NTSC", "PAL")

        year = str(meta.year) if meta.year is not None else ""
        if meta.category == "TV":
            year = str(meta.year) if (meta.year is not None and meta.search_year != "") else ""
        manual_year_value = str(meta.manual_year)
        if manual_year_value and int(manual_year_value) > 0:
            year = manual_year_value
        if meta.no_year:
            year = ""

        if dvd_encode:
            # For an ENCODE, get_source returns a bare NTSC/PAL only for DVD sources; the site titles that DVDRip.
            dvd_tokens = f" {f'{resolution} {source}'.strip()} "
            start = dreadvault_name.rfind(dvd_tokens)
            if start >= 0:
                prefix = dreadvault_name[:start]
                for token in (meta.repack, meta.edition):
                    if token:
                        prefix = prefix.removesuffix(f" {token}")
                dreadvault_name = prefix + f" {resolution} DVDRip " + dreadvault_name[start + len(dvd_tokens) :]

        if name_type == "DVDRIP":
            source = "DVDRip"
            encode_token = video_encode.strip()
            dreadvault_name = _remove_last(dreadvault_name, meta.source or "")
            if encode_token:
                encode_span = f" {encode_token} DVDRip"
                start = max(f"{dreadvault_name} ".rfind(f"{encode_span}{boundary}") for boundary in (" ", "-"))
                if start >= 0:
                    dreadvault_name = dreadvault_name[:start] + dreadvault_name[start + len(encode_token) + 1 :]
                    dreadvault_name = _insert_after_last(dreadvault_name, meta.audio or source, encode_token)
            if resolution:
                dreadvault_name = _insert_before_last(dreadvault_name, source, resolution)

        if alt_title and year:
            dreadvault_name = dreadvault_name.replace(f"{year} {alt_title}", f"{alt_title} {year}", 1)

        edition = re.sub(r"\b(?:4K Remaster(?:ed)?|Remaster(?:ed)?|Criterion|Arrow|RESTORED|Internal|Limited|Retail|Version)\b", "", meta.edition, flags=re.IGNORECASE)
        edition = " ".join(edition.split())
        if name_type != "DVDRIP" and not dvd_encode:
            dreadvault_name = _replace_last(dreadvault_name, meta.edition, edition)

        if name_type == "REMUX" and source in ("PAL DVD", "NTSC DVD", "DVD"):
            dreadvault_name = _replace_last(dreadvault_name, f"{source} REMUX", f"{resolution} DVD REMUX".strip())
        elif full_disc and meta.is_disc == "BDMV":
            dreadvault_name = _replace_last(dreadvault_name, source, "Blu-ray")

        episode_field = ""
        if meta.category == "TV":
            season = "" if meta.no_season else str(meta.season or "")
            episode_field = f"{season}{meta.episode}"
            if name_type == "DVDRIP" and meta.episode:
                dreadvault_name = _replace_last(dreadvault_name, season, episode_field)
            if not episode_field:
                episode_fields = re.findall(r"\bS\d+(?:E\d+)*\b", dreadvault_name)
                episode_field = episode_fields[-1] if episode_fields else ""
            if not meta.tv_pack and re.fullmatch(r"E\d+", meta.episode):
                episode_title = meta.manual_episode_title or meta.daily_episode_title or meta.auto_episode_title or ""
                dreadvault_name = _insert_after_last(dreadvault_name, episode_field, episode_title)
                episode_field = f"{episode_field} {episode_title}".strip()

        if not meta.language_checked:
            await languages_manager.process_desc_language(meta, tracker=self.tracker)
        # The language parser excludes commentary and shortens multi-word MediaInfo language names.
        aliases = {"en": "english", "eng": "english", "no": "zxx", "no linguistic content": "zxx"}
        audio_languages: list[str] = [aliases.get(language.lower().strip(), language.lower().strip()) for language in meta.audio_languages or []]
        has_non_linguistic = "zxx" in audio_languages
        audio_languages = [language for language in audio_languages if language not in {"", "und", "undetermined", "unknown", "xx", "zxx"}]
        languages = set(audio_languages)
        dub = ""
        if not full_disc:
            if len(languages) >= 3:
                dub = "Multi-Audio"
            elif len(languages) == 2:
                dub = "Dual-Audio"
            elif languages == {"english"} and (meta.original_language or "").lower() not in ("", "en", "eng", "english", "xx", "und", "zxx", "mul"):
                dub = "Dubbed"
            if (meta.no_dub and dub == "Dubbed") or (meta.no_dual and dub in ("Dual-Audio", "Multi-Audio")):
                dub = ""
        if audio_languages or has_non_linguistic:
            audio = re.sub(r"^(?:Dual-Audio|Multi-Audio|MULTI|Dubbed)\s+", "", meta.audio)
            audio = f"{dub} {audio}".strip()
            dreadvault_name = _replace_last(dreadvault_name, meta.audio, audio)

        if not full_disc and (audio_languages or has_non_linguistic) and not await languages_manager.has_english_language(audio_languages):
            foreign_lang = audio_languages[0].upper() if audio_languages else "ZXX"
            anchor = episode_field or year
            if anchor:
                dreadvault_name = _insert_after_last(dreadvault_name, anchor, foreign_lang)
            else:
                for anchor in (resolution, str(meta.service), meta.region, source):
                    if anchor and f" {anchor} " in f" {dreadvault_name} ":
                        dreadvault_name = _insert_before_last(dreadvault_name, anchor, foreign_lang)
                        break

        return {"name": " ".join(dreadvault_name.split())}

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
