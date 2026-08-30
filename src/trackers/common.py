# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import asyncio
import contextlib
import hashlib
import json
import os
import re
import secrets
import sys
import unicodedata
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import aiofiles
import bencodepy
import cli_ui
import click
import httpx
import langcodes
from langcodes import tag_parser
from torf import Torrent
from unidecode import unidecode

from src.bbcode import BBCODE
from src.console import console, logger, prompt_in_thread
from src.exportmi import export_info
from src.genre_map import AUDIBLE_ENG_GENRE_MAP, AUDIBLE_PTBR_GENRE_MAP, ENG_TO_PTBR_GENRE_MAP
from src.languages import languages_manager
from src.meta import Meta
from src.usenetcreate import verify_nzb_has_password


class Common:
    PORTUGUESE_SUBTITLE_EXTENSIONS: frozenset[str] = frozenset({".ass", ".ssa", ".srt", ".sub", ".vtt"})
    PORTUGUESE_SUBTITLE_WORDS: frozenset[str] = frozenset(
        {
            "agora",
            "aqui",
            "bem",
            "como",
            "com",
            "entao",
            "essa",
            "esse",
            "esta",
            "estao",
            "isso",
            "muito",
            "nao",
            "obrigada",
            "obrigado",
            "onde",
            "para",
            "porque",
            "posso",
            "pode",
            "quando",
            "que",
            "senhor",
            "senhora",
            "sua",
            "suas",
            "seu",
            "seus",
            "tambem",
            "tenho",
            "temos",
            "uma",
            "voce",
            "vamos",
        }
    )
    LANGUAGE_EQUIVALENCE_GROUPS: tuple[set[str], ...] = (
        {"chinese", "mandarin", "zh", "zho", "chi", "cmn", "chinese simplified", "chinese traditional", "zh hans", "zh hant"},
        {"english", "eng", "en", "en us", "en gb", "english cc", "english sdh", "english forced"},
        {"french", "fra", "fre", "fr", "francais", "français", "french canada", "french canadian"},
        {"portuguese", "por", "pt", "pt pt", "brazilian portuguese", "portuguese brazil", "portuguese br", "pt br", "brazilian"},
        {"spanish", "spa", "es", "es es", "spanish latin america", "latin american spanish", "es 419", "es mx", "castilian", "espanol", "español", "latino"},
    )

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.parser = self.MediaInfoParser()

    def _normalize_language_token(self, language: str) -> str:
        normalized = unicodedata.normalize("NFKD", language)
        normalized = "".join(char for char in normalized if not unicodedata.combining(char))
        normalized = normalized.casefold()
        normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
        return re.sub(r"\s+", " ", normalized).strip()

    def _build_language_alias_lookup(self) -> dict[str, set[str]]:
        alias_lookup: dict[str, set[str]] = {}
        for group in self.LANGUAGE_EQUIVALENCE_GROUPS:
            normalized_group = {self._normalize_language_token(value) for value in group if value}
            for value in normalized_group:
                alias_lookup[value] = set(normalized_group)
        return alias_lookup

    def _coerce_language_values(self, values: Any) -> list[str]:
        if isinstance(values, str):
            return [values]
        if isinstance(values, list):
            return [value for value in values if isinstance(value, str)]
        return []

    def _expand_language_candidates(self, language: str, alias_lookup: dict[str, set[str]]) -> set[str]:
        normalized = self._normalize_language_token(language)
        if not normalized:
            return set()

        candidates: set[str] = {normalized}
        tokens = normalized.split()
        if tokens:
            candidates.add(tokens[0])

        first_chunk = language.split(",")[0].strip()
        if first_chunk and first_chunk != language:
            chunk_normalized = self._normalize_language_token(first_chunk)
            if chunk_normalized:
                candidates.add(chunk_normalized)

        parse_inputs = {language.strip(), normalized.replace(" ", "-")}
        for parse_input in parse_inputs:
            if not parse_input:
                continue
            try:
                parsed_lang = langcodes.Language.get(parse_input)
                display_name = parsed_lang.display_name()
                language_name = parsed_lang.language_name()
                language_code = parsed_lang.language
                for value in (display_name, language_name, language_code):
                    if value:
                        value_normalized = self._normalize_language_token(value)
                        if value_normalized:
                            candidates.add(value_normalized)
            except tag_parser.LanguageTagError, LookupError, AttributeError, ValueError:
                continue

        expanded = set(candidates)
        for candidate in candidates:
            aliases = alias_lookup.get(candidate)
            if aliases:
                expanded.update(aliases)
        return expanded

    def _expand_language_list(self, values: list[str], alias_lookup: dict[str, set[str]]) -> set[str]:
        expanded: set[str] = set()
        for value in values:
            expanded.update(self._expand_language_candidates(value, alias_lookup))
        return expanded

    @staticmethod
    def _read_subtitle_text(path: Path) -> str:
        for encoding in ("utf-8-sig", "utf-16", "cp1252"):
            try:
                return path.read_text(encoding=encoding)
            except UnicodeError:
                continue
            except OSError:
                return ""
        return ""

    async def has_portuguese_external_subtitle(self, meta: Meta) -> bool:
        """Check external subtitle filenames and textual content for Portuguese."""
        aliases = {
            "brazilian",
            "brazilian portuguese",
            "por",
            "portuguese",
            "portugues",
            "pt",
            "pt br",
            "ptbr",
            "pt brasil",
        }
        normalized_aliases = {self._normalize_language_token(alias) for alias in aliases}
        text_paths: list[Path] = []

        for subtitle_file in meta.subtitle_files or []:
            path = Path(str(subtitle_file))
            filename = self._normalize_language_token(path.stem)
            filename_tokens = filename.split()
            while filename_tokens and filename_tokens[-1] in {"forced", "sdh"}:
                filename_tokens.pop()
            filename_without_flags = " ".join(filename_tokens)
            if any(filename_without_flags == alias or filename_without_flags.endswith(f" {alias}") for alias in normalized_aliases):
                return True
            if path.suffix.casefold() in self.PORTUGUESE_SUBTITLE_EXTENSIONS:
                text_paths.append(path)

        for path in text_paths:
            text = await asyncio.to_thread(self._read_subtitle_text, path)
            words = set(re.findall(r"[a-z]+", self._normalize_language_token(text)))
            if len(words & self.PORTUGUESE_SUBTITLE_WORDS) >= 3:
                return True

        return False

    async def check_portuguese_video_requirements(self, meta: Meta, tracker: str) -> bool:
        if await self.has_portuguese_external_subtitle(meta):
            return True

        subtitles = await self.check_language_requirements(
            meta,
            tracker,
            languages_to_check=["portuguese", "português", "por", "pt", "pt-br", "pt br", "brazilian portuguese"],
            check_audio=True,
            check_subtitle=True,
            prompt_on_failure=False,
        )
        if not subtitles and (not meta.unattended or meta.unattended_confirm):
            return await self.prompt_user_for_confirmation(f"{tracker}: No Portuguese audio or subtitles found. Do you want to proceed with the upload?")
        return subtitles

    def _format_language_for_display(self, language: str) -> str:
        if not language:
            return ""
        try:
            parsed_lang = langcodes.Language.get(language)
            display_name = parsed_lang.display_name()
            return display_name.lower() if display_name else language.lower()
        except tag_parser.LanguageTagError, LookupError, AttributeError, ValueError:
            return language.lower()

    async def path_exists(self, path: str) -> bool:
        """Async wrapper for os.path.exists"""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, os.path.exists, path)

    async def remove_file(self, path: str) -> None:
        """Async wrapper for os.remove"""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, os.remove, path)

    async def makedirs(self, path: str, exist_ok: bool = True) -> None:
        """Async wrapper for os.makedirs"""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda p, e: Path(p).mkdir(parents=True, exist_ok=e), path, exist_ok)

    async def get_torrent_filename(self, meta: Meta, tracker_config: Any) -> str:
        """
        Decide which torrent filename/prefix to use (BASE or BASE_SUBS) depending on
        the allow_ext_subtitles setting and presence of the subtitles torrent.
        """
        torrent_filename = "BASE"
        allow_ext_subtitles = False
        if isinstance(tracker_config, dict):
            allow_ext_subtitles = tracker_config.get("allow_ext_subtitles", False)
        if allow_ext_subtitles:
            subs_path = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/BASE_SUBS.torrent"
            if await self.path_exists(subs_path):
                torrent_filename = "BASE_SUBS"
        return torrent_filename

    async def create_torrent_for_upload(
        self,
        meta: Meta,
        tracker: str,
        source_flag: str,
        torrent_filename: str = "BASE",
        announce_url: str = "",
        is_public: bool = False,
        public_trackers: list[str] | None = None,
    ) -> None:
        tracker_cfg = self.config.get("TRACKERS", {}).get(tracker, {})
        if torrent_filename == "BASE":
            torrent_filename = await self.get_torrent_filename(meta, tracker_cfg)

        path = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/{torrent_filename}.torrent"
        if await self.path_exists(path):
            loop = asyncio.get_running_loop()
            new_torrent = await loop.run_in_executor(None, lambda: Torrent.read(path))
            for each in list(new_torrent.metainfo):
                if each not in (
                    "announce",
                    "comment",
                    "creation date",
                    "created by",
                    "encoding",
                    "info",
                    "imdb",
                    "tmdb",
                    "tvdb",
                    "tvmaze",
                    "mal",
                    "douban",
                    "igdb",
                    "asin",
                    "isbn",
                ):
                    new_torrent.metainfo.pop(each, None)  # type: ignore
            if is_public:
                new_torrent.metainfo.get("info", {}).pop("private", None)
                if public_trackers:
                    new_torrent.metainfo["announce"] = public_trackers[0]
                    new_torrent.metainfo["announce-list"] = [[t] for t in public_trackers]
                else:
                    new_torrent.metainfo.pop("announce", None)
                    new_torrent.metainfo.pop("announce-list", None)
            else:
                if announce_url:
                    new_torrent.metainfo["announce"] = announce_url
                else:
                    raw_announce = self.config["TRACKERS"][tracker].get("announce_url")
                    new_torrent.metainfo["announce"] = str(raw_announce).strip() if raw_announce else "https://fake.tracker"
            new_torrent.metainfo["info"]["source"] = source_flag
            if "created by" in new_torrent.metainfo:
                created_by = new_torrent.metainfo["created by"]
                if "mkbrr" in created_by.lower():
                    new_torrent.metainfo["created by"] = f"{created_by} using {meta.ua_name} {meta.current_version}"
            # setting comment as blank as if BASE.torrent is manually created then it can result in private info such as download link being exposed.
            new_torrent.metainfo["comment"] = ""
            entropy_value = meta.entropy
            if entropy_value is not None:
                try:
                    entropy_int = int(entropy_value)
                    if entropy_int == 32:
                        new_torrent.metainfo["info"]["entropy"] = secrets.randbelow(2**32)  # type: ignore
                    elif entropy_int == 64:
                        new_torrent.metainfo["info"]["entropy"] = secrets.randbelow(2**64)  # type: ignore
                except ValueError, TypeError:
                    # Skip entropy setting if value is invalid
                    pass
            out_path = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/[{tracker}].torrent"
            await loop.run_in_executor(None, lambda: Torrent.copy(new_torrent).write(out_path, overwrite=True))

    async def download_tracker_torrent(
        self,
        meta: Meta,
        tracker: str,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
        downurl: str = "",
        hash_is_id: bool = False,
        cross: bool = False,
    ) -> str | None:
        path = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/[{tracker}_cross].torrent" if cross else f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/[{tracker}].torrent"
        if downurl:
            try:
                cookie_jar = None
                from src.trackersetup import http_trackers

                if tracker in http_trackers:
                    with contextlib.suppress(Exception):
                        from src.cookie_auth import CookieValidator

                        cookie_validator = CookieValidator(self.config)
                        cookie_jar = await cookie_validator.load_session_cookies(meta, tracker)

                async with (
                    httpx.AsyncClient(headers=headers, params=params, cookies=cookie_jar, follow_redirects=True, timeout=30.0) as session,
                    session.stream("GET", downurl) as r,
                ):
                    r.raise_for_status()
                    async with aiofiles.open(path, "wb") as f:
                        async for chunk in r.aiter_bytes():
                            await f.write(chunk)

                if cross:
                    return None

                if hash_is_id:
                    return await self.get_torrent_hash(meta, tracker)
                return path

            except Exception as e:
                logger.warning(f"[yellow]Warning: Could not download torrent file: {e!s}[/yellow]")
                logger.info("[yellow]Download manually from the tracker.[/yellow]")
                return None

        return None

    async def create_torrent_ready_to_seed(
        self,
        meta: Meta,
        tracker: str,
        source_flag: str,
        new_tracker: str | list[str],
        comment: str = "",
        hash_is_id: bool = False,
    ) -> str | None:
        """
        Modifies the torrent file to include the tracker's announce URL, a comment, and a source flag.
        """
        path = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/[{tracker}].torrent"
        if await self.path_exists(path):
            loop = asyncio.get_running_loop()
            new_torrent = await loop.run_in_executor(None, lambda: Torrent.read(path))
            if isinstance(new_tracker, list):
                if not new_tracker:
                    logger.error(f"[red]Error: Empty tracker list provided for {tracker}. Cannot create torrent.[/red]")
                    return None
                new_torrent.metainfo["announce"] = new_tracker[0]
                new_torrent.metainfo["announce-list"] = [new_tracker]
            else:
                new_torrent.metainfo["announce"] = new_tracker
            new_torrent.metainfo["info"]["source"] = source_flag

            # Calculate hash only when hash_is_id is True
            torrent_hash: str | None = None
            if hash_is_id:
                info_data = new_torrent.metainfo.get("info", {})
                bencode_module = cast(Any, bencodepy)
                encode = cast(Callable[[Any], bytes], bencode_module.encode)
                info_bytes = encode(info_data)
                torrent_hash = hashlib.sha1(info_bytes, usedforsecurity=False).hexdigest()  # SHA1 required for torrent info hash
                new_torrent.metainfo["comment"] = comment + torrent_hash
            else:
                new_torrent.metainfo["comment"] = comment

            await loop.run_in_executor(None, lambda: Torrent.copy(new_torrent).write(path, overwrite=True))

            return torrent_hash

        return None

    async def get_torrent_hash(self, meta: Meta, tracker: str) -> str:
        torrent_path = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/[{tracker}].torrent"
        async with aiofiles.open(torrent_path, "rb") as torrent_file:
            torrent_content = await torrent_file.read()
            bencode_module = cast(Any, bencodepy)
            decode = cast(Callable[[bytes], Any], bencode_module.decode)
            torrent_data = decode(torrent_content)
            if not isinstance(torrent_data, dict):
                return ""
            torrent_dict = cast(dict[bytes, Any], torrent_data)
            info_value = torrent_dict.get(b"info")
            if not isinstance(info_value, dict):
                return ""
            bencode_module = cast(Any, bencodepy)
            encode = cast(Callable[[Any], bytes], bencode_module.encode)
            info = encode(info_value)
            return hashlib.sha1(info, usedforsecurity=False).hexdigest()  # SHA1 required for torrent info hash

    async def save_image_links(self, meta: Meta, image_key: str, image_list: list[dict[str, str]] | None) -> str | None:
        if image_list is None:
            logger.info("[yellow]No image links to save.[/yellow]")
            return None

        output_dir = Path(meta.base_dir) / "tmp" / meta.uuid
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        output_file = Path(output_dir) / "pack_image_links.json"

        # Load existing data if the file exists
        existing_data: dict[str, Any] = {}
        if Path(output_file).exists():
            try:
                async with aiofiles.open(output_file, encoding="utf-8") as f:
                    content = await f.read()
                    loaded_data: dict[str, Any] = {}
                    if content.strip():
                        parsed = json.loads(content)
                        if isinstance(parsed, dict):
                            loaded_data = cast(dict[str, Any], parsed)
                        else:
                            logger.warning("[yellow]Warning: Existing image data has invalid schema, reinitializing.[/yellow]")

                    # Validate schema: must have 'keys' as dict and 'total_count' as int
                    if isinstance(loaded_data.get("keys"), dict) and isinstance(loaded_data.get("total_count"), int):
                        existing_data = loaded_data
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"[yellow]Warning: Could not load existing image data: {e!s}[/yellow]")

        # Create data structure if it doesn't exist or was invalid
        if not existing_data:
            existing_data = {"keys": {}, "total_count": 0}

        # Ensure 'keys' is a dict (extra safety)
        keys_data: dict[str, dict[str, Any]] = {}
        keys_raw = existing_data.get("keys")
        if isinstance(keys_raw, dict):
            keys_data = cast(dict[str, dict[str, Any]], keys_raw)
        else:
            existing_data["keys"] = keys_data

        if image_key not in keys_data or not isinstance(keys_data.get(image_key), dict):
            keys_data[image_key] = {"count": 0, "images": []}
        key_entry = keys_data[image_key]
        images_list: list[dict[str, Any]] = []
        if isinstance(key_entry.get("images"), list):
            images_list = cast(list[dict[str, Any]], key_entry["images"])
        else:
            key_entry["images"] = images_list

        # Add new images to the specific key
        for idx, img in enumerate(image_list):
            image_entry: dict[str, Any] = {
                "index": key_entry["count"] + idx,
                "raw_url": img.get("raw_url", ""),
                "web_url": img.get("web_url", ""),
                "img_url": img.get("img_url", ""),
            }
            images_list.append(image_entry)

        # Update counts
        key_entry["count"] = len(images_list)
        # Safely compute total_count, handling any malformed per-key entries
        total = 0
        for key_data in keys_data.values():
            if isinstance(key_data.get("count"), int):
                total += key_data["count"]
        existing_data["total_count"] = total

        try:
            async with aiofiles.open(output_file, "w", encoding="utf-8") as f:
                await f.write(json.dumps(existing_data, indent=2))

            logger.debug(f"[green]Saved {len(image_list)} new images for key '{image_key}' (total: {existing_data['total_count']}):[/green]")
            logger.debug(f"[blue]  - JSON: {output_file}[/blue]")

            return output_file
        except Exception as e:
            logger.info(f"[bold red]Error saving image links: {e}[/bold red]")
            return None

    async def unit3d_region_ids(self, region: str = "", reverse: bool = False, region_id: int = 0) -> str:
        region_map = {
            "AFG": 1,
            "AIA": 2,
            "ALA": 3,
            "ALG": 4,
            "AND": 5,
            "ANG": 6,
            "ARG": 7,
            "ARM": 8,
            "ARU": 9,
            "ASA": 10,
            "ATA": 11,
            "ATF": 12,
            "ATG": 13,
            "AUS": 14,
            "AUT": 15,
            "AZE": 16,
            "BAH": 17,
            "BAN": 18,
            "BDI": 19,
            "BEL": 20,
            "BEN": 21,
            "BER": 22,
            "BES": 23,
            "BFA": 24,
            "BHR": 25,
            "BHU": 26,
            "BIH": 27,
            "BLM": 28,
            "BLR": 29,
            "BLZ": 30,
            "BOL": 31,
            "BOT": 32,
            "BRA": 33,
            "BRB": 34,
            "BRU": 35,
            "BVT": 36,
            "CAM": 37,
            "CAN": 38,
            "CAY": 39,
            "CCK": 40,
            "CEE": 41,
            "CGO": 42,
            "CHA": 43,
            "CHI": 44,
            "CHN": 45,
            "CIV": 46,
            "CMR": 47,
            "COD": 48,
            "COK": 49,
            "COL": 50,
            "COM": 51,
            "CPV": 52,
            "CRC": 53,
            "CRO": 54,
            "CTA": 55,
            "CUB": 56,
            "CUW": 57,
            "CXR": 58,
            "CYP": 59,
            "DJI": 60,
            "DMA": 61,
            "DOM": 62,
            "ECU": 63,
            "EGY": 64,
            "ENG": 65,
            "EQG": 66,
            "ERI": 67,
            "ESH": 68,
            "ESP": 69,
            "ETH": 70,
            "FIJ": 71,
            "FLK": 72,
            "FRA": 73,
            "FRO": 74,
            "FSM": 75,
            "GAB": 76,
            "GAM": 77,
            "GBR": 78,
            "GEO": 79,
            "GER": 80,
            "GGY": 81,
            "GHA": 82,
            "GIB": 83,
            "GLP": 84,
            "GNB": 85,
            "GRE": 86,
            "GRL": 87,
            "GRN": 88,
            "GUA": 89,
            "GUF": 90,
            "GUI": 91,
            "GUM": 92,
            "GUY": 93,
            "HAI": 94,
            "HKG": 95,
            "HMD": 96,
            "HON": 97,
            "HUN": 98,
            "IDN": 99,
            "IMN": 100,
            "IND": 101,
            "IOT": 102,
            "IRL": 103,
            "IRN": 104,
            "IRQ": 105,
            "ISL": 106,
            "ISR": 107,
            "ITA": 108,
            "JAM": 109,
            "JEY": 110,
            "JOR": 111,
            "JPN": 112,
            "KAZ": 113,
            "KEN": 114,
            "KGZ": 115,
            "KIR": 116,
            "KNA": 117,
            "KOR": 118,
            "KSA": 119,
            "KUW": 120,
            "KVX": 121,
            "LAO": 122,
            "LBN": 123,
            "LBR": 124,
            "LBY": 125,
            "LCA": 126,
            "LES": 127,
            "LIE": 128,
            "LKA": 129,
            "LUX": 130,
            "MAC": 131,
            "MAD": 132,
            "MAF": 133,
            "MAR": 134,
            "MAS": 135,
            "MDA": 136,
            "MDV": 137,
            "MEX": 138,
            "MHL": 139,
            "MKD": 140,
            "MLI": 141,
            "MLT": 142,
            "MNG": 143,
            "MNP": 144,
            "MON": 145,
            "MOZ": 146,
            "MRI": 147,
            "MSR": 148,
            "MTN": 149,
            "MTQ": 150,
            "MWI": 151,
            "MYA": 152,
            "MYT": 153,
            "NAM": 154,
            "NCA": 155,
            "NCL": 156,
            "NEP": 157,
            "NFK": 158,
            "NIG": 159,
            "NIR": 160,
            "NIU": 161,
            "NLD": 162,
            "NOR": 163,
            "NRU": 164,
            "NZL": 165,
            "OMA": 166,
            "PAK": 167,
            "PAN": 168,
            "PAR": 169,
            "PCN": 170,
            "PER": 171,
            "PHI": 172,
            "PLE": 173,
            "PLW": 174,
            "PNG": 175,
            "POL": 176,
            "POR": 177,
            "PRK": 178,
            "PUR": 179,
            "QAT": 180,
            "REU": 181,
            "ROU": 182,
            "RSA": 183,
            "RUS": 184,
            "RWA": 185,
            "SAM": 186,
            "SCO": 187,
            "SDN": 188,
            "SEN": 189,
            "SEY": 190,
            "SGS": 191,
            "SHN": 192,
            "SIN": 193,
            "SJM": 194,
            "SLE": 195,
            "SLV": 196,
            "SMR": 197,
            "SOL": 198,
            "SOM": 199,
            "SPM": 200,
            "SRB": 201,
            "SSD": 202,
            "STP": 203,
            "SUI": 204,
            "SUR": 205,
            "SWZ": 206,
            "SXM": 207,
            "SYR": 208,
            "TAH": 209,
            "TAN": 210,
            "TCA": 211,
            "TGA": 212,
            "THA": 213,
            "TJK": 214,
            "TKL": 215,
            "TKM": 216,
            "TLS": 217,
            "TOG": 218,
            "TRI": 219,
            "TUN": 220,
            "TUR": 221,
            "TUV": 222,
            "TWN": 223,
            "UAE": 224,
            "UGA": 225,
            "UKR": 226,
            "UMI": 227,
            "URU": 228,
            "USA": 229,
            "UZB": 230,
            "VAN": 231,
            "VAT": 232,
            "VEN": 233,
            "VGB": 234,
            "VIE": 235,
            "VIN": 236,
            "VIR": 237,
            "WAL": 238,
            "WLF": 239,
            "YEM": 240,
            "ZAM": 241,
            "ZIM": 242,
            "EUR": 243,
        }

        if reverse:
            # Reverse lookup: Find region code by ID
            # Convert to int to handle cases where API returns string
            try:
                region_id = region_id
            except ValueError, TypeError:
                return ""
            for code, id_value in region_map.items():
                if id_value == region_id:
                    return code
            return ""
        # Forward lookup: Find region ID by code
        region_id_value = region_map.get(region)
        return str(region_id_value) if region_id_value else ""

    async def unit3d_distributor_ids(self, distributor: str = "", reverse: bool = False, distributor_id: int = 0) -> str:
        distributor_map = {
            "01 DISTRIBUTION": 1,
            "100 DESTINATIONS TRAVEL FILM": 2,
            "101 FILMS": 3,
            "1FILMS": 4,
            "2 ENTERTAIN VIDEO": 5,
            "20TH CENTURY FOX": 6,
            "2L": 7,
            "3D CONTENT HUB": 8,
            "3D MEDIA": 9,
            "3L FILM": 10,
            "4DIGITAL": 11,
            "4DVD": 12,
            "4K ULTRA HD MOVIES": 13,
            "4K UHD": 13,
            "8-FILMS": 14,
            "84 ENTERTAINMENT": 15,
            "88 FILMS": 16,
            "@ANIME": 17,
            "ANIME": 17,
            "A CONTRACORRIENTE": 18,
            "A CONTRACORRIENTE FILMS": 19,
            "A&E HOME VIDEO": 20,
            "A&E": 20,
            "A&M RECORDS": 21,
            "A+E NETWORKS": 22,
            "A+R": 23,
            "A-FILM": 24,
            "AAA": 25,
            "AB VIDÉO": 26,
            "AB VIDEO": 26,
            "ABC - (AUSTRALIAN BROADCASTING CORPORATION)": 27,
            "ABC": 27,
            "ABKCO": 28,
            "ABSOLUT MEDIEN": 29,
            "ABSOLUTE": 30,
            "ACCENT FILM ENTERTAINMENT": 31,
            "ACCENTUS": 32,
            "ACORN MEDIA": 33,
            "AD VITAM": 34,
            "ADA": 35,
            "ADITYA VIDEOS": 36,
            "ADSO FILMS": 37,
            "AFM RECORDS": 38,
            "AGFA": 39,
            "AIX RECORDS": 40,
            "ALAMODE FILM": 41,
            "ALBA RECORDS": 42,
            "ALBANY RECORDS": 43,
            "ALBATROS": 44,
            "ALCHEMY": 45,
            "ALIVE": 46,
            "ALL ANIME": 47,
            "ALL INTERACTIVE ENTERTAINMENT": 48,
            "ALLEGRO": 49,
            "ALLIANCE": 50,
            "ALPHA MUSIC": 51,
            "ALTERDYSTRYBUCJA": 52,
            "ALTERED INNOCENCE": 53,
            "ALTITUDE FILM DISTRIBUTION": 54,
            "ALUCARD RECORDS": 55,
            "AMAZING D.C.": 56,
            "AMAZING DC": 56,
            "AMMO CONTENT": 57,
            "AMUSE SOFT ENTERTAINMENT": 58,
            "ANCONNECT": 59,
            "ANEC": 60,
            "ANIMATSU": 61,
            "ANIME HOUSE": 62,
            "ANIME LTD": 63,
            "ANIME WORKS": 64,
            "ANIMEIGO": 65,
            "ANIPLEX": 66,
            "ANOLIS ENTERTAINMENT": 67,
            "ANOTHER WORLD ENTERTAINMENT": 68,
            "AP INTERNATIONAL": 69,
            "APPLE": 70,
            "ARA MEDIA": 71,
            "ARBELOS": 72,
            "ARC ENTERTAINMENT": 73,
            "ARP SÉLECTION": 74,
            "ARP SELECTION": 74,
            "ARROW": 75,
            "ART SERVICE": 76,
            "ART VISION": 77,
            "ARTE ÉDITIONS": 78,
            "ARTE EDITIONS": 78,
            "ARTE VIDÉO": 79,
            "ARTE VIDEO": 79,
            "ARTHAUS MUSIK": 80,
            "ARTIFICIAL EYE": 81,
            "ARTSPLOITATION FILMS": 82,
            "ARTUS FILMS": 83,
            "ASCOT ELITE HOME ENTERTAINMENT": 84,
            "ASIA VIDEO": 85,
            "ASMIK ACE": 86,
            "ASTRO RECORDS & FILMWORKS": 87,
            "ASYLUM": 88,
            "ATLANTIC FILM": 89,
            "ATLANTIC RECORDS": 90,
            "ATLAS FILM": 91,
            "AUDIO VISUAL ENTERTAINMENT": 92,
            "AURO-3D CREATIVE LABEL": 93,
            "AURUM": 94,
            "AV VISIONEN": 95,
            "AV-JET": 96,
            "AVALON": 97,
            "AVENTI": 98,
            "AVEX TRAX": 99,
            "AXIOM": 100,
            "AXIS RECORDS": 101,
            "AYNGARAN": 102,
            "BAC FILMS": 103,
            "BACH FILMS": 104,
            "BANDAI VISUAL": 105,
            "BARCLAY": 106,
            "BBC": 107,
            "BRITISH BROADCASTING CORPORATION": 107,
            "BBI FILMS": 108,
            "BBI": 108,
            "BCI HOME ENTERTAINMENT": 109,
            "BEGGARS BANQUET": 110,
            "BEL AIR CLASSIQUES": 111,
            "BELGA FILMS": 112,
            "BELVEDERE": 113,
            "BENELUX FILM DISTRIBUTORS": 114,
            "BENNETT-WATT MEDIA": 115,
            "BERLIN CLASSICS": 116,
            "BERLINER PHILHARMONIKER RECORDINGS": 117,
            "BEST ENTERTAINMENT": 118,
            "BEYOND HOME ENTERTAINMENT": 119,
            "BFI VIDEO": 120,
            "BFI": 120,
            "BRITISH FILM INSTITUTE": 120,
            "BFS ENTERTAINMENT": 121,
            "BFS": 121,
            "BHAVANI": 122,
            "BIBER RECORDS": 123,
            "BIG HOME VIDEO": 124,
            "BILDSTÖRUNG": 125,
            "BILDSTORUNG": 125,
            "BILL ZEBUB": 126,
            "BIRNENBLATT": 127,
            "BIT WEL": 128,
            "BLACK BOX": 129,
            "BLACK HILL PICTURES": 130,
            "BLACK HILL": 130,
            "BLACK HOLE RECORDINGS": 131,
            "BLACK HOLE": 131,
            "BLAQOUT": 132,
            "BLAUFIELD MUSIC": 133,
            "BLAUFIELD": 133,
            "BLOCKBUSTER ENTERTAINMENT": 134,
            "BLOCKBUSTER": 134,
            "BLU PHASE MEDIA": 135,
            "BLU-RAY ONLY": 136,
            "BLU-RAY": 136,
            "BLURAY ONLY": 136,
            "BLURAY": 136,
            "BLUE GENTIAN RECORDS": 137,
            "BLUE KINO": 138,
            "BLUE UNDERGROUND": 139,
            "BMG/ARISTA": 140,
            "BMG": 140,
            "BMGARISTA": 140,
            "BMG ARISTA": 140,
            "ARISTA": 140,
            "ARISTA/BMG": 140,
            "ARISTABMG": 140,
            "ARISTA BMG": 140,
            "BONTON FILM": 141,
            "BONTON": 141,
            "BOOMERANG PICTURES": 142,
            "BOOMERANG": 142,
            "BQHL ÉDITIONS": 143,
            "BQHL EDITIONS": 143,
            "BQHL": 143,
            "BREAKING GLASS": 144,
            "BRIDGESTONE": 145,
            "BRINK": 146,
            "BROAD GREEN PICTURES": 147,
            "BROAD GREEN": 147,
            "BUSCH MEDIA GROUP": 148,
            "BUSCH": 148,
            "C MAJOR": 149,
            "C.B.S.": 150,
            "CAICHANG": 151,
            "CALIFÓRNIA FILMES": 152,
            "CALIFORNIA FILMES": 152,
            "CALIFORNIA": 152,
            "CAMEO": 153,
            "CAMERA OBSCURA": 154,
            "CAMERATA": 155,
            "CAMP MOTION PICTURES": 156,
            "CAMP MOTION": 156,
            "CAPELIGHT PICTURES": 157,
            "CAPELIGHT": 157,
            "CAPITOL": 159,
            "CAPITOL RECORDS": 159,
            "CAPRICCI": 160,
            "CARGO RECORDS": 161,
            "CARLOTTA FILMS": 162,
            "CARLOTTA": 162,
            "CARLOTA": 162,
            "CARMEN FILM": 163,
            "CASCADE": 164,
            "CATCHPLAY": 165,
            "CAULDRON FILMS": 166,
            "CAULDRON": 166,
            "CBS TELEVISION STUDIOS": 167,
            "CBS": 167,
            "CCTV": 168,
            "CCV ENTERTAINMENT": 169,
            "CCV": 169,
            "CD BABY": 170,
            "CD LAND": 171,
            "CECCHI GORI": 172,
            "CENTURY MEDIA": 173,
            "CHUAN XUN SHI DAI MULTIMEDIA": 174,
            "CINE-ASIA": 175,
            "CINÉART": 176,
            "CINEART": 176,
            "CINEDIGM": 177,
            "CINEFIL IMAGICA": 178,
            "CINEMA EPOCH": 179,
            "CINEMA GUILD": 180,
            "CINEMA LIBRE STUDIOS": 181,
            "CINEMA MONDO": 182,
            "CINEMATIC VISION": 183,
            "CINEPLOIT RECORDS": 184,
            "CINESTRANGE EXTREME": 185,
            "CITEL VIDEO": 186,
            "CITEL": 186,
            "CJ ENTERTAINMENT": 187,
            "CJ": 187,
            "CLASSIC MEDIA": 188,
            "CLASSICFLIX": 189,
            "CLASSICLINE": 190,
            "CLAUDIO RECORDS": 191,
            "CLEAR VISION": 192,
            "CLEOPATRA": 193,
            "CLOSE UP": 194,
            "CMS MEDIA LIMITED": 195,
            "CMV LASERVISION": 196,
            "CN ENTERTAINMENT": 197,
            "CODE RED": 198,
            "COHEN MEDIA GROUP": 199,
            "COHEN": 199,
            "COIN DE MIRE CINÉMA": 200,
            "COIN DE MIRE CINEMA": 200,
            "COLOSSEO FILM": 201,
            "COLUMBIA": 203,
            "COLUMBIA PICTURES": 203,
            "COLUMBIA/TRI-STAR": 204,
            "TRI-STAR": 204,
            "COMMERCIAL MARKETING": 205,
            "CONCORD MUSIC GROUP": 206,
            "CONCORDE VIDEO": 207,
            "CONDOR": 208,
            "CONSTANTIN FILM": 209,
            "CONSTANTIN": 209,
            "CONSTANTINO FILMES": 210,
            "CONSTANTINO": 210,
            "CONSTRUCTIVE MEDIA SERVICE": 211,
            "CONSTRUCTIVE": 211,
            "CONTENT ZONE": 212,
            "CONTENTS GATE": 213,
            "COQUEIRO VERDE": 214,
            "CORNERSTONE MEDIA": 215,
            "CORNERSTONE": 215,
            "CP DIGITAL": 216,
            "CREST MOVIES": 217,
            "CRITERION": 218,
            "CRITERION COLLECTION": 218,
            "CC": 218,
            "CRYSTAL CLASSICS": 219,
            "CULT EPICS": 220,
            "CULT FILMS": 221,
            "CULT VIDEO": 222,
            "CURZON FILM WORLD": 223,
            "D FILMS": 224,
            "D'AILLY COMPANY": 225,
            "DAILLY COMPANY": 225,
            "D AILLY COMPANY": 225,
            "D'AILLY": 225,
            "DAILLY": 225,
            "D AILLY": 225,
            "DA CAPO": 226,
            "DA MUSIC": 227,
            "DALL'ANGELO PICTURES": 228,
            "DALLANGELO PICTURES": 228,
            "DALL'ANGELO": 228,
            "DALL ANGELO PICTURES": 228,
            "DALL ANGELO": 228,
            "DAREDO": 229,
            "DARK FORCE ENTERTAINMENT": 230,
            "DARK FORCE": 230,
            "DARK SIDE RELEASING": 231,
            "DARK SIDE": 231,
            "DAZZLER MEDIA": 232,
            "DAZZLER": 232,
            "DCM PICTURES": 233,
            "DCM": 233,
            "DEAPLANETA": 234,
            "DECCA": 235,
            "DEEPJOY": 236,
            "DEFIANT SCREEN ENTERTAINMENT": 237,
            "DEFIANT SCREEN": 237,
            "DEFIANT": 237,
            "DELOS": 238,
            "DELPHIAN RECORDS": 239,
            "DELPHIAN": 239,
            "DELTA MUSIC & ENTERTAINMENT": 240,
            "DELTA MUSIC AND ENTERTAINMENT": 240,
            "DELTA MUSIC ENTERTAINMENT": 240,
            "DELTA MUSIC": 240,
            "DELTAMAC CO. LTD.": 241,
            "DELTAMAC CO LTD": 241,
            "DELTAMAC CO": 241,
            "DELTAMAC": 241,
            "DEMAND MEDIA": 242,
            "DEMAND": 242,
            "DEP": 243,
            "DEUTSCHE GRAMMOPHON": 244,
            "DFW": 245,
            "DGM": 246,
            "DIAPHANA": 247,
            "DIGIDREAMS STUDIOS": 248,
            "DIGIDREAMS": 248,
            "DIGITAL ENVIRONMENTS": 249,
            "DIGITAL": 249,
            "DISCOTEK MEDIA": 250,
            "DISCOVERY CHANNEL": 251,
            "DISCOVERY": 251,
            "DISK KINO": 252,
            "DISNEY / BUENA VISTA": 253,
            "DISNEY": 253,
            "BUENA VISTA": 253,
            "DISNEY BUENA VISTA": 253,
            "DISTRIBUTION SELECT": 254,
            "DIVISA": 255,
            "DNC ENTERTAINMENT": 256,
            "DNC": 256,
            "DOGWOOF": 257,
            "DOLMEN HOME VIDEO": 258,
            "DOLMEN": 258,
            "DONAU FILM": 259,
            "DONAU": 259,
            "DORADO FILMS": 260,
            "DORADO": 260,
            "DRAFTHOUSE FILMS": 261,
            "DRAFTHOUSE": 261,
            "DRAGON FILM ENTERTAINMENT": 262,
            "DRAGON ENTERTAINMENT": 262,
            "DRAGON FILM": 262,
            "DRAGON": 262,
            "DREAMWORKS": 263,
            "DRIVE ON RECORDS": 264,
            "DRIVE ON": 264,
            "DRIVE-ON": 264,
            "DRIVEON": 264,
            "DS MEDIA": 265,
            "DTP ENTERTAINMENT AG": 266,
            "DTP ENTERTAINMENT": 266,
            "DTP AG": 266,
            "DTP": 266,
            "DTS ENTERTAINMENT": 267,
            "DTS": 267,
            "DUKE MARKETING": 268,
            "DUKE VIDEO DISTRIBUTION": 269,
            "DUKE": 269,
            "DUTCH FILMWORKS": 270,
            "DUTCH": 270,
            "DVD INTERNATIONAL": 271,
            "DVD": 271,
            "DYBEX": 272,
            "DYNAMIC": 273,
            "DYNIT": 274,
            "E1 ENTERTAINMENT": 275,
            "E1": 275,
            "EAGLE ENTERTAINMENT": 276,
            "EAGLE HOME ENTERTAINMENT PVT.LTD.": 277,
            "EAGLE HOME ENTERTAINMENT PVTLTD": 277,
            "EAGLE HOME ENTERTAINMENT PVT LTD": 277,
            "EAGLE HOME ENTERTAINMENT": 277,
            "EAGLE PICTURES": 278,
            "EAGLE ROCK ENTERTAINMENT": 279,
            "EAGLE ROCK": 279,
            "EAGLE VISION MEDIA": 280,
            "EAGLE VISION": 280,
            "EARMUSIC": 281,
            "EARTH ENTERTAINMENT": 282,
            "EARTH": 282,
            "ECHO BRIDGE ENTERTAINMENT": 283,
            "ECHO BRIDGE": 283,
            "EDEL GERMANY GMBH": 284,
            "EDEL GERMANY": 284,
            "EDEL RECORDS": 285,
            "EDITION TONFILM": 286,
            "EDITIONS MONTPARNASSE": 287,
            "EDKO FILMS LTD.": 288,
            "EDKO FILMS LTD": 288,
            "EDKO FILMS": 288,
            "EDKO": 288,
            "EIN'S M&M CO": 289,
            "EINS M&M CO": 289,
            "EIN'S M&M": 289,
            "EINS M&M": 289,
            "ELEA-MEDIA": 290,
            "ELEA MEDIA": 290,
            "ELEA": 290,
            "ELECTRIC PICTURE": 291,
            "ELECTRIC": 291,
            "ELEPHANT FILMS": 292,
            "ELEPHANT": 292,
            "ELEVATION": 293,
            "EMI": 294,
            "EMON": 295,
            "EMS": 296,
            "EMYLIA": 297,
            "ENE MEDIA": 298,
            "ENE": 298,
            "ENTERTAINMENT IN VIDEO": 299,
            "ENTERTAINMENT IN": 299,
            "ENTERTAINMENT ONE": 300,
            "ENTERTAINMENT ONE FILMS CANADA INC.": 301,
            "ENTERTAINMENT ONE FILMS CANADA INC": 301,
            "ENTERTAINMENT ONE FILMS CANADA": 301,
            "ENTERTAINMENT ONE CANADA INC": 301,
            "ENTERTAINMENT ONE CANADA": 301,
            "ENTERTAINMENTONE": 302,
            "EONE": 303,
            "EOS": 304,
            "EPIC PICTURES": 305,
            "EPIC": 305,
            "EPIC RECORDS": 306,
            "ERATO": 307,
            "EROS": 308,
            "ESC EDITIONS": 309,
            "ESCAPI MEDIA BV": 310,
            "ESOTERIC RECORDINGS": 311,
            "ESPN FILMS": 312,
            "EUREKA ENTERTAINMENT": 313,
            "EUREKA": 313,
            "EURO PICTURES": 314,
            "EURO VIDEO": 315,
            "EUROARTS": 316,
            "EUROPA FILMES": 317,
            "EUROPA": 317,
            "EUROPACORP": 318,
            "EUROZOOM": 319,
            "EXCEL": 320,
            "EXPLOSIVE MEDIA": 321,
            "EXPLOSIVE": 321,
            "EXTRALUCID FILMS": 322,
            "EXTRALUCID": 322,
            "EYE SEE MOVIES": 323,
            "EYE SEE": 323,
            "EYK MEDIA": 324,
            "EYK": 324,
            "FABULOUS FILMS": 325,
            "FABULOUS": 325,
            "FACTORIS FILMS": 326,
            "FACTORIS": 326,
            "FARAO RECORDS": 327,
            "FARBFILM HOME ENTERTAINMENT": 328,
            "FARBFILM ENTERTAINMENT": 328,
            "FARBFILM HOME": 328,
            "FARBFILM": 328,
            "FEELGOOD ENTERTAINMENT": 329,
            "FEELGOOD": 329,
            "FERNSEHJUWELEN": 330,
            "FILM CHEST": 331,
            "FILM MEDIA": 332,
            "FILM MOVEMENT": 333,
            "FILM4": 334,
            "FILMART": 335,
            "FILMAURO": 336,
            "FILMAX": 337,
            "FILMCONFECT HOME ENTERTAINMENT": 338,
            "FILMCONFECT ENTERTAINMENT": 338,
            "FILMCONFECT HOME": 338,
            "FILMCONFECT": 338,
            "FILMEDIA": 339,
            "FILMJUWELEN": 340,
            "FILMOTEKA NARODAWA": 341,
            "FILMRISE": 342,
            "FINAL CUT ENTERTAINMENT": 343,
            "FINAL CUT": 343,
            "FIREHOUSE 12 RECORDS": 344,
            "FIREHOUSE 12": 344,
            "FIRST INTERNATIONAL PRODUCTION": 345,
            "FIRST INTERNATIONAL": 345,
            "FIRST LOOK STUDIOS": 346,
            "FIRST LOOK": 346,
            "FLAGMAN TRADE": 347,
            "FLASHSTAR FILMES": 348,
            "FLASHSTAR": 348,
            "FLICKER ALLEY": 349,
            "FNC ADD CULTURE": 350,
            "FOCUS FILMES": 351,
            "FOCUS": 351,
            "FOKUS MEDIA": 352,
            "FOKUSA": 352,
            "FOX PATHE EUROPA": 353,
            "FOX PATHE": 353,
            "FOX EUROPA": 353,
            "FOX/MGM": 354,
            "FOX MGM": 354,
            "MGM": 354,
            "MGM/FOX": 354,
            "FOX": 354,
            "FPE": 355,
            "FRANCE TÉLÉVISIONS DISTRIBUTION": 356,
            "FRANCE TELEVISIONS DISTRIBUTION": 356,
            "FRANCE TELEVISIONS": 356,
            "FRANCE": 356,
            "FREE DOLPHIN ENTERTAINMENT": 357,
            "FREE DOLPHIN": 357,
            "FREESTYLE DIGITAL MEDIA": 358,
            "FREESTYLE DIGITAL": 358,
            "FREESTYLE": 358,
            "FREMANTLE HOME ENTERTAINMENT": 359,
            "FREMANTLE ENTERTAINMENT": 359,
            "FREMANTLE HOME": 359,
            "FREMANTL": 359,
            "FRENETIC FILMS": 360,
            "FRENETIC": 360,
            "FRONTIER WORKS": 361,
            "FRONTIER": 361,
            "FRONTIERS MUSIC": 362,
            "FRONTIERS RECORDS": 363,
            "FS FILM OY": 364,
            "FS FILM": 364,
            "FULL MOON FEATURES": 365,
            "FULL MOON": 365,
            "FUN CITY EDITIONS": 366,
            "FUN CITY": 366,
            "FUNIMATION ENTERTAINMENT": 367,
            "FUNIMATION": 367,
            "FUSION": 368,
            "FUTUREFILM": 369,
            "G2 PICTURES": 370,
            "G2": 370,
            "GAGA COMMUNICATIONS": 371,
            "GAGA": 371,
            "GAIAM": 372,
            "GALAPAGOS": 373,
            "GAMMA HOME ENTERTAINMENT": 374,
            "GAMMA ENTERTAINMENT": 374,
            "GAMMA HOME": 374,
            "GAMMA": 374,
            "GARAGEHOUSE PICTURES": 375,
            "GARAGEHOUSE": 375,
            "GARAGEPLAY (車庫娛樂)": 376,
            "車庫娛樂": 376,
            "GARAGEPLAY (Che Ku Yu Le )": 376,
            "GARAGEPLAY": 376,
            "Che Ku Yu Le": 376,
            "GAUMONT": 377,
            "GEFFEN": 378,
            "GENEON ENTERTAINMENT": 379,
            "GENEON": 379,
            "GENEON UNIVERSAL ENTERTAINMENT": 380,
            "GENERAL VIDEO RECORDING": 381,
            "GLASS DOLL FILMS": 382,
            "GLASS DOLL": 382,
            "GLOBE MUSIC MEDIA": 383,
            "GLOBE MUSIC": 383,
            "GLOBE MEDIA": 383,
            "GLOBE": 383,
            "GO ENTERTAIN": 384,
            "GO": 384,
            "GOLDEN HARVEST": 385,
            "GOOD!MOVIES": 386,
            "GOOD! MOVIES": 386,
            "GOOD MOVIES": 386,
            "GRAPEVINE VIDEO": 387,
            "GRAPEVINE": 387,
            "GRASSHOPPER FILM": 388,
            "GRASSHOPPER FILMS": 388,
            "GRASSHOPPER": 388,
            "GRAVITAS VENTURES": 389,
            "GRAVITAS": 389,
            "GREAT MOVIES": 390,
            "GREAT": 390,
            "GREEN APPLE ENTERTAINMENT": 391,
            "GREEN ENTERTAINMENT": 391,
            "GREEN APPLE": 391,
            "GREEN": 391,
            "GREENNARAE MEDIA": 392,
            "GREENNARAE": 392,
            "GRINDHOUSE RELEASING": 393,
            "GRINDHOUSE": 393,
            "GRIND HOUSE": 393,
            "GRYPHON ENTERTAINMENT": 394,
            "GRYPHON": 394,
            "GUNPOWDER & SKY": 395,
            "GUNPOWDER AND SKY": 395,
            "GUNPOWDER SKY": 395,
            "GUNPOWDER + SKY": 395,
            "GUNPOWDER": 395,
            "HANABEE ENTERTAINMENT": 396,
            "HANABEE": 396,
            "HANNOVER HOUSE": 397,
            "HANNOVER": 397,
            "HANSESOUND": 398,
            "HANSE SOUND": 398,
            "HANSE": 398,
            "HAPPINET": 399,
            "HARMONIA MUNDI": 400,
            "HARMONIA": 400,
            "HBO": 401,
            "HDC": 402,
            "HEC": 403,
            "HELL & BACK RECORDINGS": 404,
            "HELL AND BACK RECORDINGS": 404,
            "HELL & BACK": 404,
            "HELL AND BACK": 404,
            "HEN'S TOOTH VIDEO": 405,
            "HENS TOOTH VIDEO": 405,
            "HEN'S TOOTH": 405,
            "HENS TOOTH": 405,
            "HIGH FLIERS": 406,
            "HIGHLIGHT": 407,
            "HILLSONG": 408,
            "HISTORY CHANNEL": 409,
            "HISTORY": 409,
            "HK VIDÉO": 410,
            "HK VIDEO": 410,
            "HK": 410,
            "HMH HAMBURGER MEDIEN HAUS": 411,
            "HAMBURGER MEDIEN HAUS": 411,
            "HMH HAMBURGER MEDIEN": 411,
            "HMH HAMBURGER": 411,
            "HMH": 411,
            "HOLLYWOOD CLASSIC ENTERTAINMENT": 412,
            "HOLLYWOOD CLASSIC": 412,
            "HOLLYWOOD PICTURES": 413,
            "HOLLYWOOD": 413,
            "HOPSCOTCH ENTERTAINMENT": 414,
            "HOPSCOTCH": 414,
            "HPM": 415,
            "HÄNNSLER CLASSIC": 416,
            "HANNSLER CLASSIC": 416,
            "HANNSLER": 416,
            "I-CATCHER": 417,
            "I CATCHER": 417,
            "ICATCHER": 417,
            "I-ON NEW MEDIA": 418,
            "I ON NEW MEDIA": 418,
            "ION NEW MEDIA": 418,
            "ION MEDIA": 418,
            "I-ON": 418,
            "ION": 418,
            "IAN PRODUCTIONS": 419,
            "IAN": 419,
            "ICESTORM": 420,
            "ICON FILM DISTRIBUTION": 421,
            "ICON DISTRIBUTION": 421,
            "ICON FILM": 421,
            "ICON": 421,
            "IDEALE AUDIENCE": 422,
            "IDEALE": 422,
            "IFC FILMS": 423,
            "IFC": 423,
            "IFILM": 424,
            "ILLUSIONS UNLTD.": 425,
            "ILLUSIONS UNLTD": 425,
            "ILLUSIONS": 425,
            "IMAGE ENTERTAINMENT": 426,
            "IMAGE": 426,
            "IMAGEM FILMES": 427,
            "IMAGEM": 427,
            "IMOVISION": 428,
            "IMPERIAL CINEPIX": 429,
            "IMPRINT": 430,
            "IMPULS HOME ENTERTAINMENT": 431,
            "IMPULS ENTERTAINMENT": 431,
            "IMPULS HOME": 431,
            "IMPULS": 431,
            "IN-AKUSTIK": 432,
            "IN AKUSTIK": 432,
            "INAKUSTIK": 432,
            "INCEPTION MEDIA GROUP": 433,
            "INCEPTION MEDIA": 433,
            "INCEPTION GROUP": 433,
            "INCEPTION": 433,
            "INDEPENDENT": 434,
            "INDICAN": 435,
            "INDIE RIGHTS": 436,
            "INDIE": 436,
            "INDIGO": 437,
            "INFO": 438,
            "INJOINGAN": 439,
            "INKED PICTURES": 440,
            "INKED": 440,
            "INSIDE OUT MUSIC": 441,
            "INSIDE MUSIC": 441,
            "INSIDE OUT": 441,
            "INSIDE": 441,
            "INTERCOM": 442,
            "INTERCONTINENTAL VIDEO": 443,
            "INTERCONTINENTAL": 443,
            "INTERGROOVE": 444,
            "INTERSCOPE": 445,
            "INVINCIBLE PICTURES": 446,
            "INVINCIBLE": 446,
            "ISLAND/MERCURY": 447,
            "ISLAND MERCURY": 447,
            "ISLANDMERCURY": 447,
            "ISLAND & MERCURY": 447,
            "ISLAND AND MERCURY": 447,
            "ISLAND": 447,
            "ITN": 448,
            "ITV DVD": 449,
            "ITV": 449,
            "IVC": 450,
            "IVE ENTERTAINMENT": 451,
            "IVE": 451,
            "J&R ADVENTURES": 452,
            "J&R": 452,
            "JR": 452,
            "JAKOB": 453,
            "JONU MEDIA": 454,
            "JONU": 454,
            "JRB PRODUCTIONS": 455,
            "JRB": 455,
            "JUST BRIDGE ENTERTAINMENT": 456,
            "JUST BRIDGE": 456,
            "JUST ENTERTAINMENT": 456,
            "JUST": 456,
            "KABOOM ENTERTAINMENT": 457,
            "KABOOM": 457,
            "KADOKAWA ENTERTAINMENT": 458,
            "KADOKAWA": 458,
            "KAIROS": 459,
            "KALEIDOSCOPE ENTERTAINMENT": 460,
            "KALEIDOSCOPE": 460,
            "KAM & RONSON ENTERPRISES": 461,
            "KAM & RONSON": 461,
            "KAM&RONSON ENTERPRISES": 461,
            "KAM&RONSON": 461,
            "KAM AND RONSON ENTERPRISES": 461,
            "KAM AND RONSON": 461,
            "KANA HOME VIDEO": 462,
            "KARMA FILMS": 463,
            "KARMA": 463,
            "KATZENBERGER": 464,
            "KAZE": 465,
            "KBS MEDIA": 466,
            "KBS": 466,
            "KD MEDIA": 467,
            "KD": 467,
            "KING MEDIA": 468,
            "KING": 468,
            "KING RECORDS": 469,
            "KINO LORBER": 470,
            "KINO": 470,
            "KINO SWIAT": 471,
            "KINOKUNIYA": 472,
            "KINOWELT HOME ENTERTAINMENT/DVD": 473,
            "KINOWELT HOME ENTERTAINMENT": 473,
            "KINOWELT ENTERTAINMENT": 473,
            "KINOWELT HOME DVD": 473,
            "KINOWELT ENTERTAINMENT/DVD": 473,
            "KINOWELT DVD": 473,
            "KINOWELT": 473,
            "KIT PARKER FILMS": 474,
            "KIT PARKER": 474,
            "KITTY MEDIA": 475,
            "KNM HOME ENTERTAINMENT": 476,
            "KNM ENTERTAINMENT": 476,
            "KNM HOME": 476,
            "KNM": 476,
            "KOBA FILMS": 477,
            "KOBA": 477,
            "KOCH ENTERTAINMENT": 478,
            "KOCH MEDIA": 479,
            "KOCH": 479,
            "KRAKEN RELEASING": 480,
            "KRAKEN": 480,
            "KSCOPE": 481,
            "KSM": 482,
            "KULTUR": 483,
            "L'ATELIER D'IMAGES": 484,
            "LATELIER D'IMAGES": 484,
            "L'ATELIER DIMAGES": 484,
            "LATELIER DIMAGES": 484,
            "L ATELIER D'IMAGES": 484,
            "L'ATELIER D IMAGES": 484,
            "L ATELIER D IMAGES": 484,
            "L'ATELIER": 484,
            "L ATELIER": 484,
            "LATELIER": 484,
            "LA AVENTURA AUDIOVISUAL": 485,
            "LA AVENTURA": 485,
            "LACE GROUP": 486,
            "LACE": 486,
            "LASER PARADISE": 487,
            "LAYONS": 488,
            "LCJ EDITIONS": 489,
            "LCJ": 489,
            "LE CHAT QUI FUME": 490,
            "LE PACTE": 491,
            "LEDICK FILMHANDEL": 492,
            "LEGEND": 493,
            "LEOMARK STUDIOS": 494,
            "LEOMARK": 494,
            "LEONINE FILMS": 495,
            "LEONINE": 495,
            "LICHTUNG MEDIA LTD": 496,
            "LICHTUNG LTD": 496,
            "LICHTUNG MEDIA LTD.": 496,
            "LICHTUNG LTD.": 496,
            "LICHTUNG MEDIA": 496,
            "LICHTUNG": 496,
            "LIGHTHOUSE HOME ENTERTAINMENT": 497,
            "LIGHTHOUSE ENTERTAINMENT": 497,
            "LIGHTHOUSE HOME": 497,
            "LIGHTHOUSE": 497,
            "LIGHTYEAR": 498,
            "LIONSGATE FILMS": 499,
            "LIONSGATE": 499,
            "LIZARD CINEMA TRADE": 500,
            "LLAMENTOL": 501,
            "LOBSTER FILMS": 502,
            "LOBSTER": 502,
            "LOGON": 503,
            "LORBER FILMS": 504,
            "LORBER": 504,
            "LOS BANDITOS FILMS": 505,
            "LOS BANDITOS": 505,
            "LOUD & PROUD RECORDS": 506,
            "LOUD AND PROUD RECORDS": 506,
            "LOUD & PROUD": 506,
            "LOUD AND PROUD": 506,
            "LSO LIVE": 507,
            "LUCASFILM": 508,
            "LUCKY RED": 509,
            "LUMIÈRE HOME ENTERTAINMENT": 510,
            "LUMIERE HOME ENTERTAINMENT": 510,
            "LUMIERE ENTERTAINMENT": 510,
            "LUMIERE HOME": 510,
            "LUMIERE": 510,
            "M6 VIDEO": 511,
            "M6": 511,
            "MAD DIMENSION": 512,
            "MADMAN ENTERTAINMENT": 513,
            "MADMAN": 513,
            "MAGIC BOX": 514,
            "MAGIC PLAY": 515,
            "MAGNA HOME ENTERTAINMENT": 516,
            "MAGNA ENTERTAINMENT": 516,
            "MAGNA HOME": 516,
            "MAGNA": 516,
            "MAGNOLIA PICTURES": 517,
            "MAGNOLIA": 517,
            "MAIDEN JAPAN": 518,
            "MAIDEN": 518,
            "MAJENG MEDIA": 519,
            "MAJENG": 519,
            "MAJESTIC HOME ENTERTAINMENT": 520,
            "MAJESTIC ENTERTAINMENT": 520,
            "MAJESTIC HOME": 520,
            "MAJESTIC": 520,
            "MANGA HOME ENTERTAINMENT": 521,
            "MANGA ENTERTAINMENT": 521,
            "MANGA HOME": 521,
            "MANGA": 521,
            "MANTA LAB": 522,
            "MAPLE STUDIOS": 523,
            "MAPLE": 523,
            "MARCO POLO PRODUCTION": 524,
            "MARCO POLO": 524,
            "MARIINSKY": 525,
            "MARVEL STUDIOS": 526,
            "MARVEL": 526,
            "MASCOT RECORDS": 527,
            "MASCOT": 527,
            "MASSACRE VIDEO": 528,
            "MASSACRE": 528,
            "MATCHBOX": 529,
            "MATRIX D": 530,
            "MAXAM": 531,
            "MAYA HOME ENTERTAINMENT": 532,
            "MAYA ENTERTAINMENT": 532,
            "MAYA HOME": 532,
            "MAYAT": 532,
            "MDG": 533,
            "MEDIA BLASTERS": 534,
            "MEDIA FACTORY": 535,
            "MEDIA TARGET DISTRIBUTION": 536,
            "MEDIA TARGET": 536,
            "MEDIAINVISION": 537,
            "MEDIATOON": 538,
            "MEDIATRES ESTUDIO": 539,
            "MEDIATRES STUDIO": 539,
            "MEDIATRES": 539,
            "MEDICI ARTS": 540,
            "MEDICI CLASSICS": 541,
            "MEDIUMRARE ENTERTAINMENT": 542,
            "MEDIUMRARE": 542,
            "MEDUSA": 543,
            "MEGASTAR": 544,
            "MEI AH": 545,
            "MELI MÉDIAS": 546,
            "MELI MEDIAS": 546,
            "MEMENTO FILMS": 547,
            "MEMENTO": 547,
            "MENEMSHA FILMS": 548,
            "MENEMSHA": 548,
            "MERCURY": 549,
            "MERCURY STUDIOS": 550,
            "MERGE SOFT PRODUCTIONS": 551,
            "MERGE PRODUCTIONS": 551,
            "MERGE SOFT": 551,
            "MERGE": 551,
            "METAL BLADE RECORDS": 552,
            "METAL BLADE": 552,
            "METEOR": 553,
            "METRO-GOLDWYN-MAYER": 554,
            "METRO GOLDWYN MAYER": 554,
            "METROGOLDWYNMAYER": 554,
            "METRODOME VIDEO": 555,
            "METRODOME": 555,
            "METROPOLITAN": 556,
            "MFA+": 557,
            "MFA": 557,
            "MIG FILMGROUP": 558,
            "MIG": 558,
            "MILESTONE": 559,
            "MILL CREEK ENTERTAINMENT": 560,
            "MILL CREEK": 560,
            "MILLENNIUM MEDIA": 561,
            "MILLENNIUM": 561,
            "MIRAGE ENTERTAINMENT": 562,
            "MIRAGE": 562,
            "MIRAMAX": 563,
            "MISTERIYA ZVUKA": 564,
            "MK2": 565,
            "MODE RECORDS": 566,
            "MODE": 566,
            "MOMENTUM PICTURES": 567,
            "MONDO HOME ENTERTAINMENT": 568,
            "MONDO ENTERTAINMENT": 568,
            "MONDO HOME": 568,
            "MONDO MACABRO": 569,
            "MONGREL MEDIA": 570,
            "MONOLIT": 571,
            "MONOLITH VIDEO": 572,
            "MONOLITH": 572,
            "MONSTER PICTURES": 573,
            "MONSTER": 573,
            "MONTEREY VIDEO": 574,
            "MONTEREY": 574,
            "MONUMENT RELEASING": 575,
            "MONUMENT": 575,
            "MORNINGSTAR": 576,
            "MORNING STAR": 576,
            "MOSERBAER": 577,
            "MOVIEMAX": 578,
            "MOVINSIDE": 579,
            "MPI MEDIA GROUP": 580,
            "MPI MEDIA": 580,
            "MPI": 580,
            "MR. BONGO FILMS": 581,
            "MR BONGO FILMS": 581,
            "MR BONGO": 581,
            "MRG (MERIDIAN)": 582,
            "MRG MERIDIAN": 582,
            "MRG": 582,
            "MERIDIAN": 582,
            "MUBI": 583,
            "MUG SHOT PRODUCTIONS": 584,
            "MUG SHOT": 584,
            "MULTIMUSIC": 585,
            "MULTI-MUSIC": 585,
            "MULTI MUSIC": 585,
            "MUSE": 586,
            "MUSIC BOX FILMS": 587,
            "MUSIC BOX": 587,
            "MUSICBOX": 587,
            "MUSIC BROKERS": 588,
            "MUSIC THEORIES": 589,
            "MUSIC VIDEO DISTRIBUTORS": 590,
            "MUSIC VIDEO": 590,
            "MUSTANG ENTERTAINMENT": 591,
            "MUSTANG": 591,
            "MVD VISUAL": 592,
            "MVD": 592,
            "MVD/VSC": 593,
            "MVL": 594,
            "MVM ENTERTAINMENT": 595,
            "MVM": 595,
            "MYNDFORM": 596,
            "MYSTIC NIGHT PICTURES": 597,
            "MYSTIC NIGHT": 597,
            "NAMELESS MEDIA": 598,
            "NAMELESS": 598,
            "NAPALM RECORDS": 599,
            "NAPALM": 599,
            "NATIONAL ENTERTAINMENT MEDIA": 600,
            "NATIONAL ENTERTAINMENT": 600,
            "NATIONAL MEDIA": 600,
            "NATIONAL FILM ARCHIVE": 601,
            "NATIONAL ARCHIVE": 601,
            "NATIONAL FILM": 601,
            "NATIONAL GEOGRAPHIC": 602,
            "NAT GEO TV": 602,
            "NAT GEO": 602,
            "NGO": 602,
            "NAXOS": 603,
            "NBCUNIVERSAL ENTERTAINMENT JAPAN": 604,
            "NBC UNIVERSAL ENTERTAINMENT JAPAN": 604,
            "NBCUNIVERSAL JAPAN": 604,
            "NBC UNIVERSAL JAPAN": 604,
            "NBC JAPAN": 604,
            "NBO ENTERTAINMENT": 605,
            "NBO": 605,
            "NEOS": 606,
            "NETFLIX": 607,
            "NETWORK": 608,
            "NEW BLOOD": 609,
            "NEW DISC": 610,
            "NEW KSM": 611,
            "NEW LINE CINEMA": 612,
            "NEW LINE": 612,
            "NEW MOVIE TRADING CO. LTD": 613,
            "NEW MOVIE TRADING CO LTD": 613,
            "NEW MOVIE TRADING CO": 613,
            "NEW MOVIE TRADING": 613,
            "NEW WAVE FILMS": 614,
            "NEW WAVE": 614,
            "NFI": 615,
            "NHK": 616,
            "NIPPONART": 617,
            "NIS AMERICA": 618,
            "NJUTAFILMS": 619,
            "NOBLE ENTERTAINMENT": 620,
            "NOBLE": 620,
            "NORDISK FILM": 621,
            "NORDISK": 621,
            "NORSK FILM": 622,
            "NORSK": 622,
            "NORTH AMERICAN MOTION PICTURES": 623,
            "NOS AUDIOVISUAIS": 624,
            "NOTORIOUS PICTURES": 625,
            "NOTORIOUS": 625,
            "NOVA MEDIA": 626,
            "NOVA": 626,
            "NOVA SALES AND DISTRIBUTION": 627,
            "NOVA SALES & DISTRIBUTION": 627,
            "NSM": 628,
            "NSM RECORDS": 629,
            "NUCLEAR BLAST": 630,
            "NUCLEUS FILMS": 631,
            "NUCLEUS": 631,
            "OBERLIN MUSIC": 632,
            "OBERLIN": 632,
            "OBRAS-PRIMAS DO CINEMA": 633,
            "OBRAS PRIMAS DO CINEMA": 633,
            "OBRASPRIMAS DO CINEMA": 633,
            "OBRAS-PRIMAS CINEMA": 633,
            "OBRAS PRIMAS CINEMA": 633,
            "OBRASPRIMAS CINEMA": 633,
            "OBRAS-PRIMAS": 633,
            "OBRAS PRIMAS": 633,
            "OBRASPRIMAS": 633,
            "ODEON": 634,
            "OFDB FILMWORKS": 635,
            "OFDB": 635,
            "OLIVE FILMS": 636,
            "OLIVE": 636,
            "ONDINE": 637,
            "ONSCREEN FILMS": 638,
            "ONSCREEN": 638,
            "OPENING DISTRIBUTION": 639,
            "OPERA AUSTRALIA": 640,
            "OPTIMUM HOME ENTERTAINMENT": 641,
            "OPTIMUM ENTERTAINMENT": 641,
            "OPTIMUM HOME": 641,
            "OPTIMUM": 641,
            "OPUS ARTE": 642,
            "ORANGE STUDIO": 643,
            "ORANGE": 643,
            "ORLANDO EASTWOOD FILMS": 644,
            "ORLANDO FILMS": 644,
            "ORLANDO EASTWOOD": 644,
            "ORLANDO": 644,
            "ORUSTAK PICTURES": 645,
            "ORUSTAK": 645,
            "OSCILLOSCOPE PICTURES": 646,
            "OSCILLOSCOPE": 646,
            "OUTPLAY": 647,
            "PALISADES TARTAN": 648,
            "PAN VISION": 649,
            "PANVISION": 649,
            "PANAMINT CINEMA": 650,
            "PANAMINT": 650,
            "PANDASTORM ENTERTAINMENT": 651,
            "PANDA STORM ENTERTAINMENT": 651,
            "PANDASTORM": 651,
            "PANDA STORM": 651,
            "PANDORA FILM": 652,
            "PANDORA": 652,
            "PANEGYRIC": 653,
            "PANORAMA": 654,
            "PARADE DECK FILMS": 655,
            "PARADE DECK": 655,
            "PARADISE": 656,
            "PARADISO FILMS": 657,
            "PARADOX": 658,
            "PARAMOUNT PICTURES": 659,
            "PARAMOUNT": 659,
            "PARIS FILMES": 660,
            "PARIS FILMS": 660,
            "PARIS": 660,
            "PARK CIRCUS": 661,
            "PARLOPHONE": 662,
            "PASSION RIVER": 663,
            "PATHE DISTRIBUTION": 664,
            "PATHE": 664,
            "PBS": 665,
            "PEACE ARCH TRINITY": 666,
            "PECCADILLO PICTURES": 667,
            "PEPPERMINT": 668,
            "PHASE 4 FILMS": 669,
            "PHASE 4": 669,
            "PHILHARMONIA BAROQUE": 670,
            "PICTURE HOUSE ENTERTAINMENT": 671,
            "PICTURE ENTERTAINMENT": 671,
            "PICTURE HOUSE": 671,
            "PICTURE": 671,
            "PIDAX": 672,
            "PINK FLOYD RECORDS": 673,
            "PINK FLOYD": 673,
            "PINNACLE FILMS": 674,
            "PINNACLE": 674,
            "PLAIN": 675,
            "PLATFORM ENTERTAINMENT LIMITED": 676,
            "PLATFORM ENTERTAINMENT LTD": 676,
            "PLATFORM ENTERTAINMENT LTD.": 676,
            "PLATFORM ENTERTAINMENT": 676,
            "PLATFORM": 676,
            "PLAYARTE": 677,
            "PLG UK CLASSICS": 678,
            "PLG UK": 678,
            "PLG": 678,
            "POLYBAND & TOPPIC VIDEO/WVG": 679,
            "POLYBAND AND TOPPIC VIDEO/WVG": 679,
            "POLYBAND & TOPPIC VIDEO WVG": 679,
            "POLYBAND & TOPPIC VIDEO AND WVG": 679,
            "POLYBAND & TOPPIC VIDEO & WVG": 679,
            "POLYBAND AND TOPPIC VIDEO WVG": 679,
            "POLYBAND AND TOPPIC VIDEO AND WVG": 679,
            "POLYBAND AND TOPPIC VIDEO & WVG": 679,
            "POLYBAND & TOPPIC VIDEO": 679,
            "POLYBAND AND TOPPIC VIDEO": 679,
            "POLYBAND & TOPPIC": 679,
            "POLYBAND AND TOPPIC": 679,
            "POLYBAND": 679,
            "WVG": 679,
            "POLYDOR": 680,
            "PONY": 681,
            "PONY CANYON": 682,
            "POTEMKINE": 683,
            "POWERHOUSE FILMS": 684,
            "POWERHOUSE": 684,
            "POWERSTATIOM": 685,
            "PRIDE & JOY": 686,
            "PRIDE AND JOY": 686,
            "PRINZ MEDIA": 687,
            "PRINZ": 687,
            "PRIS AUDIOVISUAIS": 688,
            "PRO VIDEO": 689,
            "PRO-VIDEO": 689,
            "PRO-MOTION": 690,
            "PRO MOTION": 690,
            "PROD. JRB": 691,
            "PROD JRB": 691,
            "PRODISC": 692,
            "PROKINO": 693,
            "PROVOGUE RECORDS": 694,
            "PROVOGUE": 694,
            "PROWARE": 695,
            "PULP VIDEO": 696,
            "PULP": 696,
            "PULSE VIDEO": 697,
            "PULSE": 697,
            "PURE AUDIO RECORDINGS": 698,
            "PURE AUDIO": 698,
            "PURE FLIX ENTERTAINMENT": 699,
            "PURE FLIX": 699,
            "PURE ENTERTAINMENT": 699,
            "PYRAMIDE VIDEO": 700,
            "PYRAMIDE": 700,
            "QUALITY FILMS": 701,
            "QUALITY": 701,
            "QUARTO VALLEY RECORDS": 702,
            "QUARTO VALLEY": 702,
            "QUESTAR": 703,
            "R SQUARED FILMS": 704,
            "R SQUARED": 704,
            "RAPID EYE MOVIES": 705,
            "RAPID EYE": 705,
            "RARO VIDEO": 706,
            "RARO": 706,
            "RAROVIDEO U.S.": 707,
            "RAROVIDEO US": 707,
            "RARO VIDEO US": 707,
            "RARO VIDEO U.S.": 707,
            "RARO U.S.": 707,
            "RARO US": 707,
            "RAVEN BANNER RELEASING": 708,
            "RAVEN BANNER": 708,
            "RAVEN": 708,
            "RAZOR DIGITAL ENTERTAINMENT": 709,
            "RAZOR DIGITAL": 709,
            "RCA": 710,
            "RCO LIVE": 711,
            "RCO": 711,
            "RCV": 712,
            "REAL GONE MUSIC": 713,
            "REAL GONE": 713,
            "REANIMEDIA": 714,
            "REANI MEDIA": 714,
            "REDEMPTION": 715,
            "REEL": 716,
            "RELIANCE HOME VIDEO & GAMES": 717,
            "RELIANCE HOME VIDEO AND GAMES": 717,
            "RELIANCE HOME VIDEO": 717,
            "RELIANCE VIDEO": 717,
            "RELIANCE HOME": 717,
            "RELIANCE": 717,
            "REM CULTURE": 718,
            "REMAIN IN LIGHT": 719,
            "REPRISE": 720,
            "RESEN": 721,
            "RETROMEDIA": 722,
            "REVELATION FILMS LTD.": 723,
            "REVELATION FILMS LTD": 723,
            "REVELATION FILMS": 723,
            "REVELATION LTD.": 723,
            "REVELATION LTD": 723,
            "REVELATION": 723,
            "REVOLVER ENTERTAINMENT": 724,
            "REVOLVER": 724,
            "RHINO MUSIC": 725,
            "RHINO": 725,
            "RHV": 726,
            "RIGHT STUF": 727,
            "RIMINI EDITIONS": 728,
            "RISING SUN MEDIA": 729,
            "RLJ ENTERTAINMENT": 730,
            "RLJ": 730,
            "ROADRUNNER RECORDS": 731,
            "ROADSHOW ENTERTAINMENT": 732,
            "ROADSHOW": 732,
            "RONE": 733,
            "RONIN FLIX": 734,
            "ROTANA HOME ENTERTAINMENT": 735,
            "ROTANA ENTERTAINMENT": 735,
            "ROTANA HOME": 735,
            "ROTANA": 735,
            "ROUGH TRADE": 736,
            "ROUNDER": 737,
            "SAFFRON HILL FILMS": 738,
            "SAFFRON HILL": 738,
            "SAFFRON": 738,
            "SAMUEL GOLDWYN FILMS": 739,
            "SAMUEL GOLDWYN": 739,
            "SAN FRANCISCO SYMPHONY": 740,
            "SANDREW METRONOME": 741,
            "SAPHRANE": 742,
            "SAVOR": 743,
            "SCANBOX ENTERTAINMENT": 744,
            "SCANBOX": 744,
            "SCENIC LABS": 745,
            "SCHRÖDERMEDIA": 746,
            "SCHRODERMEDIA": 746,
            "SCHRODER MEDIA": 746,
            "SCORPION RELEASING": 747,
            "SCORPION": 747,
            "SCREAM TEAM RELEASING": 748,
            "SCREAM TEAM": 748,
            "SCREEN MEDIA": 749,
            "SCREEN": 749,
            "SCREENBOUND PICTURES": 750,
            "SCREENBOUND": 750,
            "SCREENWAVE MEDIA": 751,
            "SCREENWAVE": 751,
            "SECOND RUN": 752,
            "SECOND SIGHT": 753,
            "SEEDSMAN GROUP": 754,
            "SELECT VIDEO": 755,
            "SELECTA VISION": 756,
            "SENATOR": 757,
            "SENTAI FILMWORKS": 758,
            "SENTAI": 758,
            "SEVEN7": 759,
            "SEVERIN FILMS": 760,
            "SEVERIN": 760,
            "SEVILLE": 761,
            "SEYONS ENTERTAINMENT": 762,
            "SEYONS": 762,
            "SF STUDIOS": 763,
            "SGL ENTERTAINMENT": 764,
            "SGL": 764,
            "SHAMELESS": 765,
            "SHAMROCK MEDIA": 766,
            "SHAMROCK": 766,
            "SHANGHAI EPIC MUSIC ENTERTAINMENT": 767,
            "SHANGHAI EPIC ENTERTAINMENT": 767,
            "SHANGHAI EPIC MUSIC": 767,
            "SHANGHAI MUSIC ENTERTAINMENT": 767,
            "SHANGHAI ENTERTAINMENT": 767,
            "SHANGHAI MUSIC": 767,
            "SHANGHAI": 767,
            "SHEMAROO": 768,
            "SHOCHIKU": 769,
            "SHOCK": 770,
            "SHOGAKU KAN": 771,
            "SHOUT FACTORY": 772,
            "SHOUT! FACTORY": 772,
            "SHOUT": 772,
            "SHOUT!": 772,
            "SHOWBOX": 773,
            "SHOWTIME ENTERTAINMENT": 774,
            "SHOWTIME": 774,
            "SHRIEK SHOW": 775,
            "SHUDDER": 776,
            "SIDONIS": 777,
            "SIDONIS CALYSTA": 778,
            "SIGNAL ONE ENTERTAINMENT": 779,
            "SIGNAL ONE": 779,
            "SIGNATURE ENTERTAINMENT": 780,
            "SIGNATURE": 780,
            "SILVER VISION": 781,
            "SINISTER FILM": 782,
            "SINISTER": 782,
            "SIREN VISUAL ENTERTAINMENT": 783,
            "SIREN VISUAL": 783,
            "SIREN ENTERTAINMENT": 783,
            "SIREN": 783,
            "SKANI": 784,
            "SKY DIGI": 785,
            "SLASHER // VIDEO": 786,
            "SLASHER / VIDEO": 786,
            "SLASHER VIDEO": 786,
            "SLASHER": 786,
            "SLOVAK FILM INSTITUTE": 787,
            "SLOVAK FILM": 787,
            "SFI": 787,
            "SM LIFE DESIGN GROUP": 788,
            "SMOOTH PICTURES": 789,
            "SMOOTH": 789,
            "SNAPPER MUSIC": 790,
            "SNAPPER": 790,
            "SODA PICTURES": 791,
            "SODA": 791,
            "SONO LUMINUS": 792,
            "SONY MUSIC": 793,
            "SONY PICTURES": 794,
            "SONY": 794,
            "SONY PICTURES CLASSICS": 795,
            "SONY CLASSICS": 795,
            "SOUL MEDIA": 796,
            "SOUL": 796,
            "SOULFOOD MUSIC DISTRIBUTION": 797,
            "SOULFOOD DISTRIBUTION": 797,
            "SOULFOOD MUSIC": 797,
            "SOULFOOD": 797,
            "SOYUZ": 798,
            "SPECTRUM": 799,
            "SPENTZOS FILM": 800,
            "SPENTZOS": 800,
            "SPIRIT ENTERTAINMENT": 801,
            "SPIRIT": 801,
            "SPIRIT MEDIA GMBH": 802,
            "SPIRIT MEDIA": 802,
            "SPLENDID ENTERTAINMENT": 803,
            "SPLENDID FILM": 804,
            "SPO": 805,
            "SQUARE ENIX": 806,
            "SRI BALAJI VIDEO": 807,
            "SRI BALAJI": 807,
            "SRI": 807,
            "SRI VIDEO": 807,
            "SRS CINEMA": 808,
            "SRS": 808,
            "SSO RECORDINGS": 809,
            "SSO": 809,
            "ST2 MUSIC": 810,
            "ST2": 810,
            "STAR MEDIA ENTERTAINMENT": 811,
            "STAR ENTERTAINMENT": 811,
            "STAR MEDIA": 811,
            "STAR": 811,
            "STARLIGHT": 812,
            "STARZ / ANCHOR BAY": 813,
            "STARZ ANCHOR BAY": 813,
            "STARZ": 813,
            "ANCHOR BAY": 813,
            "STER KINEKOR": 814,
            "STERLING ENTERTAINMENT": 815,
            "STERLING": 815,
            "STINGRAY": 816,
            "STOCKFISCH RECORDS": 817,
            "STOCKFISCH": 817,
            "STRAND RELEASING": 818,
            "STRAND": 818,
            "STUDIO 4K": 819,
            "STUDIO CANAL": 820,
            "STUDIO GHIBLI": 821,
            "GHIBLI": 821,
            "STUDIO HAMBURG ENTERPRISES": 822,
            "HAMBURG ENTERPRISES": 822,
            "STUDIO HAMBURG": 822,
            "HAMBURG": 822,
            "STUDIO S": 823,
            "SUBKULTUR ENTERTAINMENT": 824,
            "SUBKULTUR": 824,
            "SUEVIA FILMS": 825,
            "SUEVIA": 825,
            "SUMMIT ENTERTAINMENT": 826,
            "SUMMIT": 826,
            "SUNFILM ENTERTAINMENT": 827,
            "SUNFILM": 827,
            "SURROUND RECORDS": 828,
            "SURROUND": 828,
            "SVENSK FILMINDUSTRI": 829,
            "SVENSK": 829,
            "SWEN FILMES": 830,
            "SWEN FILMS": 830,
            "SWEN": 830,
            "SYNAPSE FILMS": 831,
            "SYNAPSE": 831,
            "SYNDICADO": 832,
            "SYNERGETIC": 833,
            "T- SERIES": 834,
            "T-SERIES": 834,
            "T SERIES": 834,
            "TSERIES": 834,
            "T.V.P.": 835,
            "TVP": 835,
            "TACET RECORDS": 836,
            "TACET": 836,
            "TAI SENG": 837,
            "TAI SHENG": 838,
            "TAKEONE": 839,
            "TAKESHOBO": 840,
            "TAMASA DIFFUSION": 841,
            "TC ENTERTAINMENT": 842,
            "TC": 842,
            "TDK": 843,
            "TEAM MARKETING": 844,
            "TEATRO REAL": 845,
            "TEMA DISTRIBUCIONES": 846,
            "TEMPE DIGITAL": 847,
            "TF1 VIDÉO": 848,
            "TF1 VIDEO": 848,
            "TF1": 848,
            "THE BLU": 849,
            "BLU": 849,
            "THE ECSTASY OF FILMS": 850,
            "THE FILM DETECTIVE": 851,
            "FILM DETECTIVE": 851,
            "THE JOKERS": 852,
            "JOKERS": 852,
            "THE ON": 853,
            "ON": 853,
            "THIMFILM": 854,
            "THIM FILM": 854,
            "THIM": 854,
            "THIRD WINDOW FILMS": 855,
            "THIRD WINDOW": 855,
            "3RD WINDOW FILMS": 855,
            "3RD WINDOW": 855,
            "THUNDERBEAN ANIMATION": 856,
            "THUNDERBEAN": 856,
            "THUNDERBIRD RELEASING": 857,
            "THUNDERBIRD": 857,
            "TIBERIUS FILM": 858,
            "TIME LIFE": 859,
            "TIMELESS MEDIA GROUP": 860,
            "TIMELESS MEDIA": 860,
            "TIMELESS GROUP": 860,
            "TIMELESS": 860,
            "TLA RELEASING": 861,
            "TLA": 861,
            "TOBIS FILM": 862,
            "TOBIS": 862,
            "TOEI": 863,
            "TOHO": 864,
            "TOKYO SHOCK": 865,
            "TOKYO": 865,
            "TONPOOL MEDIEN GMBH": 866,
            "TONPOOL MEDIEN": 866,
            "TOPICS ENTERTAINMENT": 867,
            "TOPICS": 867,
            "TOUCHSTONE PICTURES": 868,
            "TOUCHSTONE": 868,
            "TRANSMISSION FILMS": 869,
            "TRANSMISSION": 869,
            "TRAVEL VIDEO STORE": 870,
            "TRIART": 871,
            "TRIGON FILM": 872,
            "TRIGON": 872,
            "TRINITY HOME ENTERTAINMENT": 873,
            "TRINITY ENTERTAINMENT": 873,
            "TRINITY HOME": 873,
            "TRINITY": 873,
            "TRIPICTURES": 874,
            "TRI-PICTURES": 874,
            "TRI PICTURES": 874,
            "TROMA": 875,
            "TURBINE MEDIEN": 876,
            "TURTLE RECORDS": 877,
            "TURTLE": 877,
            "TVA FILMS": 878,
            "TVA": 878,
            "TWILIGHT TIME": 879,
            "TWILIGHT": 879,
            "TT": 879,
            "TWIN CO., LTD.": 880,
            "TWIN CO, LTD.": 880,
            "TWIN CO., LTD": 880,
            "TWIN CO, LTD": 880,
            "TWIN CO LTD": 880,
            "TWIN LTD": 880,
            "TWIN CO.": 880,
            "TWIN CO": 880,
            "TWIN": 880,
            "UCA": 881,
            "UDR": 882,
            "UEK": 883,
            "UFA/DVD": 884,
            "UFA DVD": 884,
            "UFADVD": 884,
            "UGC PH": 885,
            "ULTIMATE3DHEAVEN": 886,
            "ULTRA": 887,
            "UMBRELLA ENTERTAINMENT": 888,
            "UMBRELLA": 888,
            "UMC": 889,
            "UNCORK'D ENTERTAINMENT": 890,
            "UNCORKD ENTERTAINMENT": 890,
            "UNCORK D ENTERTAINMENT": 890,
            "UNCORK'D": 890,
            "UNCORK D": 890,
            "UNCORKD": 890,
            "UNEARTHED FILMS": 891,
            "UNEARTHED": 891,
            "UNI DISC": 892,
            "UNIMUNDOS": 893,
            "UNITEL": 894,
            "UNIVERSAL MUSIC": 895,
            "UNIVERSAL SONY PICTURES HOME ENTERTAINMENT": 896,
            "UNIVERSAL SONY PICTURES ENTERTAINMENT": 896,
            "UNIVERSAL SONY PICTURES HOME": 896,
            "UNIVERSAL SONY PICTURES": 896,
            "UNIVERSAL HOME ENTERTAINMENT": 896,
            "UNIVERSAL ENTERTAINMENT": 896,
            "UNIVERSAL HOME": 896,
            "UNIVERSAL STUDIOS": 897,
            "UNIVERSAL": 897,
            "UNIVERSE LASER & VIDEO CO.": 898,
            "UNIVERSE LASER AND VIDEO CO.": 898,
            "UNIVERSE LASER & VIDEO CO": 898,
            "UNIVERSE LASER AND VIDEO CO": 898,
            "UNIVERSE LASER CO.": 898,
            "UNIVERSE LASER CO": 898,
            "UNIVERSE LASER": 898,
            "UNIVERSUM FILM": 899,
            "UNIVERSUM": 899,
            "UTV": 900,
            "VAP": 901,
            "VCI": 902,
            "VENDETTA FILMS": 903,
            "VENDETTA": 903,
            "VERSÁTIL HOME VIDEO": 904,
            "VERSÁTIL VIDEO": 904,
            "VERSÁTIL HOME": 904,
            "VERSÁTIL": 904,
            "VERSATIL HOME VIDEO": 904,
            "VERSATIL VIDEO": 904,
            "VERSATIL HOME": 904,
            "VERSATIL": 904,
            "VERTICAL ENTERTAINMENT": 905,
            "VERTICAL": 905,
            "VÉRTICE 360º": 906,
            "VÉRTICE 360": 906,
            "VERTICE 360o": 906,
            "VERTICE 360": 906,
            "VERTIGO BERLIN": 907,
            "VÉRTIGO FILMS": 908,
            "VÉRTIGO": 908,
            "VERTIGO FILMS": 908,
            "VERTIGO": 908,
            "VERVE PICTURES": 909,
            "VIA VISION ENTERTAINMENT": 910,
            "VIA VISION": 910,
            "VICOL ENTERTAINMENT": 911,
            "VICOL": 911,
            "VICOM": 912,
            "VICTOR ENTERTAINMENT": 913,
            "VICTOR": 913,
            "VIDEA CDE": 914,
            "VIDEO FILM EXPRESS": 915,
            "VIDEO FILM": 915,
            "VIDEO EXPRESS": 915,
            "VIDEO MUSIC, INC.": 916,
            "VIDEO MUSIC, INC": 916,
            "VIDEO MUSIC INC.": 916,
            "VIDEO MUSIC INC": 916,
            "VIDEO MUSIC": 916,
            "VIDEO SERVICE CORP.": 917,
            "VIDEO SERVICE CORP": 917,
            "VIDEO SERVICE": 917,
            "VIDEO TRAVEL": 918,
            "VIDEOMAX": 919,
            "VIDEO MAX": 919,
            "VII PILLARS ENTERTAINMENT": 920,
            "VII PILLARS": 920,
            "VILLAGE FILMS": 921,
            "VINEGAR SYNDROME": 922,
            "VINEGAR": 922,
            "VS": 922,
            "VINNY MOVIES": 923,
            "VINNY": 923,
            "VIRGIL FILMS & ENTERTAINMENT": 924,
            "VIRGIL FILMS AND ENTERTAINMENT": 924,
            "VIRGIL ENTERTAINMENT": 924,
            "VIRGIL FILMS": 924,
            "VIRGIL": 924,
            "VIRGIN RECORDS": 925,
            "VIRGIN": 925,
            "VISION FILMS": 926,
            "VISION": 926,
            "VISUAL ENTERTAINMENT GROUP": 927,
            "VISUAL GROUP": 927,
            "VISUAL ENTERTAINMENT": 927,
            "VISUAL": 927,
            "VIVENDI VISUAL ENTERTAINMENT": 928,
            "VIVENDI VISUAL": 928,
            "VIVENDI": 928,
            "VIZ PICTURES": 929,
            "VIZ": 929,
            "VLMEDIA": 930,
            "VL MEDIA": 930,
            "VL": 930,
            "VOLGA": 931,
            "VVS FILMS": 932,
            "VVS": 932,
            "VZ HANDELS GMBH": 933,
            "VZ HANDELS": 933,
            "WARD RECORDS": 934,
            "WARD": 934,
            "WARNER BROS.": 935,
            "WARNER BROS": 935,
            "WARNER ARCHIVE": 935,
            "WARNER ARCHIVE COLLECTION": 935,
            "WAC": 935,
            "WARNER": 935,
            "WARNER MUSIC": 936,
            "WEA": 937,
            "WEINSTEIN COMPANY": 938,
            "WEINSTEIN": 938,
            "WELL GO USA": 939,
            "WELL GO": 939,
            "WELTKINO FILMVERLEIH": 940,
            "WEST VIDEO": 941,
            "WEST": 941,
            "WHITE PEARL MOVIES": 942,
            "WHITE PEARL": 942,
            "WICKED-VISION MEDIA": 943,
            "WICKED VISION MEDIA": 943,
            "WICKEDVISION MEDIA": 943,
            "WICKED-VISION": 943,
            "WICKED VISION": 943,
            "WICKEDVISION": 943,
            "WIENERWORLD": 944,
            "WILD BUNCH": 945,
            "WILD EYE RELEASING": 946,
            "WILD EYE": 946,
            "WILD SIDE VIDEO": 947,
            "WILD SIDE": 947,
            "WME": 948,
            "WOLFE VIDEO": 949,
            "WOLFE": 949,
            "WORD ON FIRE": 950,
            "WORKS FILM GROUP": 951,
            "WORLD WRESTLING": 952,
            "WVG MEDIEN": 953,
            "WWE STUDIOS": 954,
            "WWE": 954,
            "X RATED KULT": 955,
            "X-RATED KULT": 955,
            "X RATED CULT": 955,
            "X-RATED CULT": 955,
            "X RATED": 955,
            "X-RATED": 955,
            "XCESS": 956,
            "XLRATOR": 957,
            "XT VIDEO": 958,
            "XT": 958,
            "YAMATO VIDEO": 959,
            "YAMATO": 959,
            "YASH RAJ FILMS": 960,
            "YASH RAJS": 960,
            "ZEITGEIST FILMS": 961,
            "ZEITGEIST": 961,
            "ZENITH PICTURES": 962,
            "ZENITH": 962,
            "ZIMA": 963,
            "ZYLO": 964,
            "ZYX MUSIC": 965,
            "ZYX": 965,
        }

        if reverse:
            # Convert to int to handle cases where API returns string
            try:
                distributor_id = distributor_id
            except ValueError, TypeError:
                return ""
            for name, id_value in distributor_map.items():
                if id_value == distributor_id:
                    return name
            return ""
        distributor_id_value = distributor_map.get(distributor)
        return str(distributor_id_value) if distributor_id_value else ""

    async def prompt_user_for_id_selection(
        self,
        meta: Meta,
        tmdb: str | int | None = None,
        imdb: str | int | None = None,
        tvdb: str | int | None = None,
        mal: str | int | None = None,
        filename: str | list[str] | None = None,
        tracker_name: str | None = None,
    ) -> bool:
        if not tracker_name:
            tracker_name = "Tracker"  # Fallback if tracker_name is not provided

        if imdb:
            imdb = str(imdb).zfill(7)  # Convert to string and ensure IMDb ID is 7 characters long by adding leading zeros
            # console.print(f"[cyan]Found IMDb ID: https://www.imdb.com/title/tt{imdb}[/cyan]")

        if any([tmdb, imdb, tvdb, mal]):
            logger.info(f"[cyan]Found the following IDs on {tracker_name}:")
            if tmdb:
                logger.info(f"TMDb ID: {tmdb}")
            if imdb:
                logger.info(f"IMDb ID: https://www.imdb.com/title/tt{imdb}")
            if tvdb:
                logger.info(f"TVDb ID: {tvdb}")
            if mal:
                logger.info(f"MAL ID: {mal}")

        if filename:
            logger.info(f"Filename: {filename}")  # Ensure filename is printed if available

        if not meta.unattended:
            try:
                selection = (await prompt_in_thread(cli_ui.ask_string, f"Do you want to use these IDs from {tracker_name}? (Y/n): ", default="") or "").strip().lower()
                return selection == "" or selection == "y" or selection == "yes"
            except KeyboardInterrupt, EOFError:
                sys.exit(1)
        else:
            return True

    async def prompt_user_for_confirmation(self, message: str, meta: Meta | None = None) -> bool:
        if meta and meta.unattended and not meta.unattended_confirm:
            return False
        response = (await prompt_in_thread(cli_ui.ask_string, f"{message} (Y/n): ", default="") or "").strip().lower()
        return response == "" or response == "y"

    async def _apply_region_distributor(self, meta: Meta, attributes: dict[str, Any]) -> None:
        region_id = attributes.get("region_id", 0)
        distributor_id = attributes.get("distributor_id", 0)

        logger.debug(f"[blue]Region ID: {region_id}[/blue]")
        logger.debug(f"[blue]Distributor ID: {distributor_id}[/blue]")

        if not meta.region and region_id:
            region_name = await self.unit3d_region_ids(reverse=True, region_id=region_id)
            if region_name:
                meta.region = region_name
                logger.debug(f"[green]Mapped region_id {region_id} to '{region_name}'[/green]")

        if not meta.distributor and distributor_id:
            distributor_name = await self.unit3d_distributor_ids(reverse=True, distributor_id=distributor_id)
            if distributor_name:
                meta.distributor = distributor_name
                logger.debug(f"[green]Mapped distributor_id {distributor_id} to '{distributor_name}'[/green]")

    async def unit3d_region_distributor(self, meta: Meta, tracker: str, torrent_url: str, id: str = "") -> None:
        """Get region and distributor information from API response"""
        raw_api_key = self.config["TRACKERS"][tracker].get("api_key")
        api_key = str(raw_api_key).strip() if raw_api_key else ""
        params: dict[str, str] = {"api_token": api_key}
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        }
        url = f"{torrent_url}{id}"
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url=url, params=params, headers=headers)
                json_response = response.json()
        except (httpx.RequestError, httpx.TimeoutException) as e:
            logger.info(f"[yellow]Request error in unit3d_region_distributor: {e}[/yellow]")
            return
        except ValueError:
            return
        try:
            data: list[dict[str, Any]] | str = json_response.get("data", [])
            if data == "404":
                logger.info("[yellow]No data found (404). Returning None.[/yellow]")
                return

            if data and isinstance(data, list):
                attributes = data[0].get("attributes", {})
                await self._apply_region_distributor(meta, attributes)
                return
            # Handle direct attributes from JSON response (when not in a list)
            attributes = json_response.get("attributes", {})
            if attributes:
                await self._apply_region_distributor(meta, attributes)
        except Exception as e:
            console.print_exception()
            logger.info(f"[yellow]Invalid Response from {tracker} API. Error: {e!s}[/yellow]")
            return

    async def unit3d_torrent_info(
        self,
        tracker: str,
        torrent_url: str,
        search_url: str,
        meta: Meta,
        id: str | int | None = None,
        file_name: str | list[str] | None = None,
        skip_tracker_descriptions: bool = False,
        public_torrent_url: str | None = None,
        region_resolver: Callable[[Any], Any] | None = None,
    ) -> tuple[
        int | None,
        int | None,
        int | None,
        int | None,
        str | None,
        str | None,
        str | None,
        list[dict[str, str]],
        str | list[str] | None,
    ]:
        tmdb = imdb = tvdb = description = category = infohash = mal = files = None
        imagelist: list[dict[str, str]] = []

        # Build the params for the API request
        raw_api_key = self.config["TRACKERS"][tracker].get("api_key")
        api_key = str(raw_api_key).strip() if raw_api_key else ""
        params: dict[str, Any] = {"api_token": api_key}
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        }

        # Determine the search method and add parameters accordingly
        if file_name:
            params["file_name"] = file_name  # Add file_name to params
            logger.debug(f"[green]Searching {tracker} by file name: [bold yellow]{file_name}[/bold yellow]")
            url = search_url
        elif id:
            url = f"{torrent_url}{id}"
            logger.debug(f"[green]Searching {tracker} by ID: [bold yellow]{id}[/bold yellow] via {url}")
        else:
            logger.debug("[red]No ID or file name provided for search.[/red]")
            return None, None, None, None, None, None, None, [], None

        # Make the GET request with proper encoding handled by 'params'
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                if id and public_torrent_url:
                    logger.info(f"Searching for information on [bold cyan]{tracker.title()}[/bold cyan] ({public_torrent_url.rstrip('/')}/{id})")
                else:
                    logger.info(f"Searching for information on [bold cyan]{tracker}[/bold cyan]")
                response = await client.get(url=url, params=params, headers=headers)
                json_response = response.json()
        except (httpx.RequestError, httpx.TimeoutException) as e:
            logger.info(f"[yellow]Request error in unit3d_torrent_info: {e}[/yellow]")
            return None, None, None, None, None, None, None, [], None
        except ValueError:
            return None, None, None, None, None, None, None, [], None

        try:
            # Handle response when searching by file name (which might return a 'data' array)
            data: list[dict[str, Any]] | str = json_response.get("data", [])
            if data == "404":
                logger.info("[yellow]No data found (404). Returning None.[/yellow]")
                return None, None, None, None, None, None, None, [], None

            if data and isinstance(data, list):  # Ensure data is a list before accessing it
                attributes = data[0].get("attributes", {})

                # Extract data from the attributes
                category = attributes.get("category")
                description = attributes.get("description")
                tmdb = int(attributes.get("tmdb_id") or 0)
                tvdb = int(attributes.get("tvdb_id") or 0)
                mal = int(attributes.get("mal_id") or 0)
                imdb = int(attributes.get("imdb_id") or 0)
                infohash = attributes.get("info_hash")
                tmdb = 0 if tmdb == 0 else tmdb
                tvdb = 0 if tvdb == 0 else tvdb
                mal = 0 if mal == 0 else mal
                imdb = 0 if imdb == 0 else imdb
                if not meta.region and meta.is_disc in ("BDMV", "DVD"):
                    region_id = attributes.get("region_id")
                    region_name = await region_resolver(region_id) if region_resolver else await self.unit3d_region_ids(reverse=True, region_id=region_id)
                    if region_name:
                        meta.region = region_name
                if not meta.distributor and meta.is_disc in ("BDMV", "DVD"):
                    distributor_id = attributes.get("distributor_id")
                    distributor_name = await self.unit3d_distributor_ids(reverse=True, distributor_id=distributor_id)
                    if distributor_name:
                        meta.distributor = distributor_name
            else:
                # Handle response when searching by ID
                if id and not data:
                    attributes = json_response.get("attributes", {})

                    # Extract data from the attributes
                    category = attributes.get("category")
                    description = attributes.get("description")
                    tmdb = int(attributes.get("tmdb_id") or 0)
                    tvdb = int(attributes.get("tvdb_id") or 0)
                    mal = int(attributes.get("mal_id") or 0)
                    imdb = int(attributes.get("imdb_id") or 0)
                    infohash = attributes.get("info_hash")
                    tmdb = 0 if tmdb == 0 else tmdb
                    tvdb = 0 if tvdb == 0 else tvdb
                    mal = 0 if mal == 0 else mal
                    imdb = 0 if imdb == 0 else imdb
                    if not meta.region and meta.is_disc in ("BDMV", "DVD"):
                        region_id = attributes.get("region_id")
                        region_name = await region_resolver(region_id) if region_resolver else await self.unit3d_region_ids(reverse=True, region_id=region_id)
                        if region_name:
                            meta.region = region_name
                    if not meta.distributor and meta.is_disc in ("BDMV", "DVD"):
                        distributor_id = attributes.get("distributor_id")
                        distributor_name = await self.unit3d_distributor_ids(reverse=True, distributor_id=distributor_id)
                        if distributor_name:
                            meta.distributor = distributor_name
                    # Handle file name extraction
                    files = attributes.get("files", [])
                    if files:
                        file_name = files[0]["name"] if len(files) == 1 else [file["name"] for file in files[:5]]

                    logger.debug(f"[blue]Extracted filename(s): {file_name}[/blue]")  # Print the extracted filename(s)

            if (tmdb or imdb or tvdb) and not id:
                # Only prompt the user for ID selection if not searching by ID
                try:
                    if not await self.prompt_user_for_id_selection(meta, tmdb, imdb, tvdb, mal, file_name, tracker_name=tracker):
                        logger.info("[yellow]User chose to skip based on IDs.[/yellow]")
                        return None, None, None, None, None, None, None, [], None
                except KeyboardInterrupt, EOFError:
                    sys.exit(1)

            if description:
                raw_descriptions = getattr(meta, "tracker_description_raw", {}) or {}
                raw_descriptions[tracker] = description
                meta.tracker_description_raw = raw_descriptions
                bbcode = BBCODE()
                description, imagelist = bbcode.clean_unit3d_description(description, torrent_url)
                if not skip_tracker_descriptions:
                    logger.info(f"[green]Successfully grabbed description from {tracker}")
                    logger.info(f"Extracted description: \n\n{description}\n\n", extra={"markup": False, "highlighter": None})

                    # A tracker ID only identifies the source of this metadata.  It
                    # must not suppress the interactive review of the description.
                    # Candidate collection sets ``unattended`` explicitly and is
                    # therefore still non-interactive.
                    if meta.unattended:
                        return tmdb, imdb, tvdb, mal, description, category, infohash, imagelist, file_name
                    logger.info("[cyan]Do you want to edit, discard or keep the description?[/cyan]")
                    edit_choice = cli_ui.ask_string("Enter 'e' to edit, 'd' to discard, or press Enter to keep it as is:")

                    if (edit_choice or "").lower() == "e":
                        edited_description = cast(str | None, click.edit(cast(Any, description)))
                        if edited_description:
                            description = edited_description.strip()
                    elif (edit_choice or "").lower() == "d":
                        description = None
                        logger.info("[yellow]Description discarded.[/yellow]")
                    else:
                        logger.info("[green]Keeping the original description.[/green]")
                    if not meta.keep_images:
                        imagelist = []
                else:
                    description = ""
                    if not meta.keep_images:
                        imagelist = []

            return tmdb, imdb, tvdb, mal, description, category, infohash, imagelist, file_name

        except Exception as e:
            console.print_exception()
            logger.info(f"[yellow]Invalid Response from {tracker} API. Error: {e!s}[/yellow]")
            return None, None, None, None, None, None, None, [], None

    async def parse_cookie_file(self, cookiefile: str) -> dict[str, str]:
        """Parse a cookies.txt file and return a dictionary of key value pairs
        compatible with requests."""

        cookies: dict[str, str] = {}
        async with aiofiles.open(cookiefile) as fp:
            content = await fp.read()
            for line in content.splitlines():
                if line.strip() and not line.startswith(("# ", "#")):
                    line_fields = re.split(" |\t", line.strip())
                    line_fields = [x for x in line_fields if x != ""]
                    if len(line_fields) >= 7:
                        cookies[line_fields[5]] = line_fields[6]
        return cookies

    async def ptgen(self, meta: Meta, ptgen_site: str = "", ptgen_retry: int = 3) -> str:
        ptgen_text = ""
        url = "https://ptgen.zhenzhen.workers.dev"
        if ptgen_site != "":
            url = ptgen_site
        params: dict[str, Any] = {}
        data: dict[str, Any] = {}

        async def fetch_ptgen(client: httpx.AsyncClient, request_url: str, request_params: dict[str, Any]) -> dict[str, Any] | None:
            """Helper to fetch and parse ptgen response with error handling."""
            try:
                response = await client.get(request_url, params=request_params, timeout=30.0)
                json_data: dict[str, Any] = response.json()
                return json_data
            except httpx.RequestError, httpx.TimeoutException, ValueError:
                return None

        try:
            async with httpx.AsyncClient() as client:
                # get douban url
                if meta.imdb_id is not None and meta.imdb_id != 0:
                    data["search"] = f"tt{meta.imdb_id}"
                    ptgen_json = await fetch_ptgen(client, url, data)

                    # Check for error and retry if needed
                    if ptgen_json is None or ptgen_json.get("error") is not None:
                        for _retry in range(ptgen_retry):
                            ptgen_json = await fetch_ptgen(client, url, data)
                            if ptgen_json is not None and ptgen_json.get("error") is None:
                                break

                    # Try to extract douban link
                    try:
                        if ptgen_json and "data" in ptgen_json and ptgen_json["data"]:
                            params["url"] = ptgen_json["data"][0]["link"]
                        else:
                            raise KeyError("No data in response")
                    except KeyError, IndexError, TypeError:
                        logger.info("[red]Unable to get data from ptgen using IMDb")
                        if not meta.unattended or (meta.unattended and meta.unattended_confirm):
                            params["url"] = await prompt_in_thread(cli_ui.ask_string, "Please enter Douban link:", default="") or ""
                        else:
                            params["url"] = ""
                else:
                    logger.info("[red]No IMDb id was found.")
                    if not meta.unattended or (meta.unattended and meta.unattended_confirm):
                        params["url"] = await prompt_in_thread(cli_ui.ask_string, "Please enter Douban link:", default="") or ""
                    else:
                        params["url"] = ""

                # Fetch with douban URL
                ptgen_json = await fetch_ptgen(client, url, params)
                if ptgen_json is None or ptgen_json.get("error") is not None:
                    for _retry in range(ptgen_retry):
                        ptgen_json = await fetch_ptgen(client, url, params)
                        if ptgen_json is not None and ptgen_json.get("error") is None:
                            break

                if ptgen_json is None:
                    logger.info("[bold red]Failed to get valid ptgen response after retries")
                    return ""

                meta.ptgen = ptgen_json
                async with aiofiles.open(f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/meta.json", "w", encoding="utf-8") as f:
                    await f.write(json.dumps(meta.to_dict(), indent=4))

                ptgen_text = ptgen_json.get("format", "")
                if "[/img]" in ptgen_text:
                    ptgen_text = ptgen_text.split("[/img]")[1]
                ptgen_text = f"[img]{meta.imdb_info.get('cover', meta.artwork_url)}[/img]{ptgen_text}"

        except Exception:
            console.print_exception()
            logger.info("[bold red]There was an error getting the ptgen \\nUploading without ptgen")
            return ""
        return ptgen_text

    class MediaInfoParser:
        def parse_mediainfo(self, mediainfo_text: str) -> dict[str, Any]:
            # Patterns for matching sections and fields
            section_pattern = re.compile(r"^(General|Video|Audio|Text|Menu)(?:\s#\d+)?", re.IGNORECASE)
            parsed_data: dict[str, Any] = {"general": {}, "video": [], "audio": [], "text": []}
            current_section: str | None = None
            current_track: dict[str, str] = {}

            # Field lists based on PHP definitions
            general_fields = {"file_name", "format", "duration", "file_size", "bit_rate"}
            video_fields = {
                "format",
                "format_version",
                "codec",
                "width",
                "height",
                "stream_size",
                "framerate_mode",
                "frame_rate",
                "aspect_ratio",
                "bit_rate",
                "bit_rate_mode",
                "bit_rate_nominal",
                "bit_pixel_frame",
                "bit_depth",
                "language",
                "format_profile",
                "color_primaries",
                "title",
                "scan_type",
                "transfer_characteristics",
                "hdr_format",
            }
            audio_fields = {"codec", "format", "bit_rate", "channels", "title", "language", "format_profile", "stream_size"}
            # text_fields = {'title', 'language'}

            # Split MediaInfo by lines and process each line
            for line in mediainfo_text.splitlines():
                line = line.strip()

                # Detect a new section
                section_match = section_pattern.match(line)
                if section_match:
                    # Save the last track data if moving to a new section
                    if current_section and current_track:
                        if current_section in ["video", "audio", "text"]:
                            parsed_data[current_section].append(current_track)
                        else:
                            parsed_data[current_section] = current_track
                        # Debug output for finalizing the current track data
                        # print(f"Final processed track data for section '{current_section}': {current_track}")
                        current_track = {}  # Reset current track

                    # Update the current section
                    current_section = section_match.group(1).lower()
                    continue

                # Split each line on the first colon to separate property and value
                if ":" in line:
                    property_name, property_value = map(str.strip, line.split(":", 1))
                    property_name = property_name.lower().replace(" ", "_")

                    # Add property if it's a recognized field for the current section
                    if (
                        (current_section == "general" and property_name in general_fields)
                        or (current_section == "video" and property_name in video_fields)
                        or (current_section == "audio" and property_name in audio_fields)
                    ):
                        current_track[property_name] = property_value
                    elif current_section == "text":
                        # Processing specific properties for text
                        # Process title field
                        if property_name == "title" and "title" not in current_track:
                            # print(f"\nProcessing Title: '{property_value}'")  # Debugging output

                            # Store the title as-is since it should remain descriptive
                            current_track["title"] = property_value
                            # print(f"Stored title: '{property_value}'")

                        # Process language field only if it hasn't already been set
                        elif property_name == "language" and "language" not in current_track:
                            current_track["language"] = property_value

            # Append the last track to the parsed data if it exists
            if current_section and current_track:
                if current_section in ["video", "audio", "text"]:
                    parsed_data[current_section].append(current_track)
                else:
                    parsed_data[current_section] = current_track
                # Final debug output for the last track data
                # print(f"Final processed track data for last section '{current_section}': {current_track}")

            # Debug output for the complete parsed_data
            # print("\nComplete Parsed Data:")
            # for section, data in parsed_data.items():
            #    print(f"{section}: {data}")

            return parsed_data

        def format_bbcode(self, parsed_mediainfo: dict[str, Any]) -> str:
            bbcode_output = "\n"

            # Format General Section
            if "general" in parsed_mediainfo:
                bbcode_output += "[b]General[/b]\n"
                for prop, value in parsed_mediainfo["general"].items():
                    bbcode_output += f"[b]{prop.replace('_', ' ').capitalize()}:[/b] {value}\n"

            # Format Video Section
            if "video" in parsed_mediainfo:
                bbcode_output += "\n[b]Video[/b]\n"
                for track in parsed_mediainfo["video"]:
                    for prop, value in track.items():
                        bbcode_output += f"[b]{prop.replace('_', ' ').capitalize()}:[/b] {value}\n"

            # Format Audio Section
            if "audio" in parsed_mediainfo:
                bbcode_output += "\n[b]Audio[/b]\n"
                for index, track in enumerate(parsed_mediainfo["audio"], start=1):  # Start enumeration at 1
                    parts = [f"{index}."]  # Start with track number without a trailing slash

                    language = track.get("language", "").lower()
                    parts.append(language.capitalize() if language else "")

                    # Other properties to concatenate (language already handled above)
                    properties = ["codec", "format", "channels", "bit_rate", "format_profile", "stream_size"]
                    parts.extend([track[prop] for prop in properties if track.get(prop)])

                    # Join parts (starting from index 1, after the track number) with slashes and add to bbcode_output
                    bbcode_output += f"{parts[0]} " + " / ".join(parts[1:]) + "\n"

            # Format Text Section - Centered, spaced apart
            if "text" in parsed_mediainfo:
                bbcode_output += "\n[b]Subtitles[/b]\n"
                subtitle_entries: list[str] = []
                for track in parsed_mediainfo["text"]:
                    language_display = track.get("language", "")
                    subtitle_entries.append(language_display)
                bbcode_output += " ".join(subtitle_entries)

            bbcode_output += "\n"
            return bbcode_output

    async def get_bdmv_mediainfo(self, meta: Meta, remove: list[str] | None = None, char_limit: int = 0) -> str:
        """
        Generate and sanitize MediaInfo for BDMV discs.

        This is required by specific trackers that demand MediaInfo regardless of the media type.
        Playlists are preferred because raw .m2ts files lack language metadata.
        However, since playlists can become bloated with hundreds of tracks, the method
        falls back to the largest .m2ts file if the output exceeds the character limit.

        :param remove: String or list of strings identifying line prefixes to be filtered out.
                       Useful for avoiding tracker parser errors (e.g., misinterpreting '2 bytes' as '2TB').
        :param char_limit: Max character length allowed before falling back to the largest M2TS.
        :return: A string containing the cleaned MediaInfo content.
        """
        mediainfo = ""
        mi_path = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/MEDIAINFO_CLEANPATH.txt"

        if meta.is_disc == "BDMV":
            # 1. Generate/Load initial MediaInfo (Playlist) if not exists
            if not Path(mi_path).is_file():
                logger.debug("[blue]Generating MediaInfo for BDMV...[/blue]")

                path = meta.discs[0]["playlists"][0]["path"]
                await export_info(path, False, meta.uuid, meta.base_dir, is_dvd=False)

            # Helper to read and filter lines from the export file
            async def read_and_clean() -> str:
                if not Path(mi_path).is_file():
                    return ""

                async with aiofiles.open(mi_path, encoding="utf-8") as f:
                    lines = await f.readlines()

                if remove:
                    lines = [line for line in lines if not any(line.strip().startswith(prefix) for prefix in remove)]

                return "".join(lines)

            mediainfo = await read_and_clean()

            # 2. Check char_limit and fallback to largest M2TS if necessary
            if char_limit and len(mediainfo) > char_limit:
                logger.debug(f"[yellow]MediaInfo length ({len(mediainfo)}) exceeds limit ({char_limit}). Falling back to largest M2TS...[/yellow]")

                items = meta.discs[0]["playlists"][0].get("items", [])

                if items:
                    largest_item = max(items, key=lambda x: x.get("size", 0))
                    largest_m2ts = largest_item.get("file")

                    if largest_m2ts:
                        logger.debug(f"[blue]Selected largest M2TS from meta: {Path(largest_m2ts).name}[/blue]")

                        await export_info(largest_m2ts, False, meta.uuid, meta.base_dir, is_dvd=False)

                        mediainfo = await read_and_clean()

        return mediainfo

    async def check_language_requirements(
        self,
        meta: Meta,
        tracker: str,
        languages_to_check: list[str],
        check_audio: bool = False,
        check_subtitle: bool = False,
        require_both: bool = False,
        original_language: bool = False,
        original_required: bool = False,
        prompt_on_failure: bool = True,
    ) -> bool:
        """
        Check if the media metadata meets specific language requirements for audio and/or subtitles.

        The function evaluates whether the provided media contains the required languages.
        It can also handle logic for original language tracks and cross-reference them
        with subtitles if the primary audio requirement isn't met.

        :param meta: Dictionary containing media metadata (audio_languages, subtitle_languages, etc.).
        :type meta: Meta
        :param tracker: Name of the tracker being processed, used for logging/output.
        :type tracker: str
        :param languages_to_check: A list of language names or codes to search for.
        :type languages_to_check: List[str]
        :param check_audio: If True, validates if required languages are present in audio tracks.
        :type check_audio: bool
        :param check_subtitle: If True, validates if required languages are present in subtitle tracks.
        :type check_subtitle: bool
        :param require_both: If True, both audio AND subtitle requirements must be satisfied.
                             If False, satisfying either is enough (OR logic).
        :type require_both: bool
        :param original_language: If True, checks if the media's original language matches the audio
                                  track, allowing a fallback to subtitle-only validation.
        :type original_language: bool
        :param original_required: If True, the original language must be present in the audio tracks.
        :type original_required: bool
        :param prompt_on_failure: If True, ask whether to continue when the requirement is not met.
        :type prompt_on_failure: bool
        :return: True if the media meets the specified language requirements, False otherwise.
        :rtype: bool
        """
        category = meta.category
        if category not in ("TV", "MOVIE", "BOOK"):
            return True

        if category == "BOOK":
            book_language = meta.book_language
            if book_language:
                book_language_lower = book_language.lower()
                languages_lower = [lang.lower() for lang in languages_to_check]
                meets_requirement = not (languages_lower and book_language_lower not in languages_lower)
                if not meets_requirement:
                    logger.info(
                        f"[red]Language requirement not met for [bold]{tracker}[/bold].[/red]\n"
                        f"[yellow]Required one of:[/yellow] {', '.join(languages_to_check)}\n"
                        f"[cyan]Found book language:[/cyan] {book_language}"
                    )
                    if prompt_on_failure:
                        return await self.prompt_user_for_confirmation(
                            f"{tracker}: Language requirements not met. Do you want to proceed with the upload?",
                            meta,
                        )
                return meets_requirement
            return True

        try:
            if not meta.language_checked:
                await languages_manager.process_desc_language(meta, tracker=tracker)

            alias_lookup = self._build_language_alias_lookup()

            meta_audio_languages = self._coerce_language_values(meta.audio_languages)
            meta_subtitle_languages = self._coerce_language_values(meta.subtitle_languages)

            languages_to_check = [lang.lower() for lang in languages_to_check]
            audio_languages = [lang.lower() for lang in meta_audio_languages]
            subtitle_languages = [lang.lower() for lang in meta_subtitle_languages]
            audio_languages_normalized = {self._normalize_language_token(lang) for lang in meta_audio_languages if isinstance(lang, str) and lang.strip()}
            language_display = None
            original_ok = False
            if original_language:
                original_language_raw = meta.original_language
                first_lang = ""
                if original_language_raw:
                    if isinstance(original_language_raw, str):
                        first_lang = original_language_raw
                    elif isinstance(original_language_raw, list) and original_language_raw:
                        first_lang = original_language_raw[0] if isinstance(original_language_raw[0], str) else ""

                if first_lang:
                    first_lang = first_lang.strip()
                    language_display = self._format_language_for_display(first_lang)
                    original_language_expanded = self._expand_language_candidates(first_lang, alias_lookup)
                    original_ok = bool(original_language_expanded.intersection(audio_languages_normalized))

                    if meta.debug and not original_ok:
                        logger.info(f"[blue]Debug: Original language expanded candidates: {', '.join(sorted(original_language_expanded)) or 'None'}[/blue]")

            if original_required and not original_ok:
                logger.info(
                    f"[red]Original language requirement not met for [bold]{tracker}[/bold].[/red]\n"
                    f"[yellow]Required original audio language:[/yellow] {language_display}\n"
                    f"[cyan]Found Audio Languages:[/cyan] {', '.join(audio_languages) or 'None'}"
                )
                if prompt_on_failure:
                    return await self.prompt_user_for_confirmation(
                        f"{tracker}: Language requirements not met. Do you want to proceed with the upload?",
                        meta,
                    )
                return False

            audio_ok = not check_audio or any(lang in audio_languages for lang in languages_to_check)
            subtitle_ok = not check_subtitle or any(lang in subtitle_languages for lang in languages_to_check)

            logger.debug(f"[blue]Debug: Audio Languages Found: {audio_languages}[/blue]")
            logger.debug(f"[blue]Debug: Subtitle Languages Found: {subtitle_languages}[/blue]")
            logger.debug(f"[blue]Debug: Original Audio Language: {language_display}[/blue]")
            logger.debug(f"[blue]Debug: Audio OK: {audio_ok}, Subtitle OK: {subtitle_ok}, Original OK: {original_ok}[/blue]")

            if not audio_ok and original_ok:
                if subtitle_ok:
                    return subtitle_ok
                logger.info(
                    f"[red]Language requirement not met for [bold]{tracker}[/bold].[/red]\n"
                    f"[yellow]Required subtitles in one of the following with an original audio track:[/yellow] "
                    f"{', '.join(languages_to_check)}\n"
                    f"[cyan]Found Audio:[/cyan] {', '.join(audio_languages) or 'None'}\n"
                    f"[cyan]Found Subtitles:[/cyan] {', '.join(subtitle_languages) or 'None'}\n"
                    f"[cyan]Original Audio Language:[/cyan] {language_display}"
                )
                return False

            if not check_audio and not check_subtitle:
                return True

            meets_requirement = audio_ok and subtitle_ok if require_both else (check_audio and audio_ok) or (check_subtitle and subtitle_ok)

            if require_both:
                if not meets_requirement:
                    logger.info(
                        f"[red]Language requirement not met for [bold]{tracker}[/bold].[/red]\n"
                        f"[yellow]Required both audio and subtitles in one of the following:[/yellow] "
                        f"{', '.join(languages_to_check)}\n"
                        f"[cyan]Found Audio:[/cyan] {', '.join(audio_languages) or 'None'}\n"
                        f"[cyan]Found Subtitles:[/cyan] {', '.join(subtitle_languages) or 'None'}"
                    )
            else:
                if not meets_requirement:
                    logger.info(
                        f"[red]Language requirement not met for [bold]{tracker}[/bold].[/red]\n"
                        f"[yellow]Required at least one of the following:[/yellow] "
                        f"{', '.join(languages_to_check)}\n"
                        f"[cyan]Found Audio:[/cyan] {', '.join(audio_languages) or 'None'}\n"
                        f"[cyan]Found Subtitles:[/cyan] {', '.join(subtitle_languages) or 'None'}"
                    )

            if not meets_requirement and prompt_on_failure:
                return await self.prompt_user_for_confirmation(
                    f"{tracker}: Language requirements not met. Do you want to proceed with the upload?",
                    meta,
                )
            return meets_requirement

        except Exception as e:
            console.print_exception()
            logger.error(f"[red]Error checking language requirements: {e}[/red]")
            return False

    async def save_html_file(self, meta: Meta, tracker: str, text: str = "", file_name: str = "") -> str:
        """
        Save provided text as an HTML file.

        :param tracker: Name of the tracker for naming the file.
        :param text: The HTML content to save.
        :param file_name: Optional custom file name (without extension).
        :return: Path to the saved HTML file.
        :rtype: str
        """
        html_path = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/[{tracker}]{file_name}.html"
        Path(html_path).parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(html_path, "w", encoding="utf-8") as f:
            await f.write(text)
        return html_path

    def get_small_description(self, meta: Meta) -> str:
        """
        Generate a small description from meta data.
        Mainly used for Chinese trackers.

        :param meta: Meta data.
        :return: Small description.
        :rtype: str
        """
        resolution = meta.resolution
        audio = meta.audio
        video_bitrate = meta.video_bitrate if meta.video_bitrate else 0
        audio_bitrate = meta.audio_bitrate if meta.audio_bitrate else 0

        return f"{resolution} @ {video_bitrate} kbps - {audio} @ {audio_bitrate} kbps"

    def check_and_confirm_adult_media_upload(self, meta: Meta, tracker: str) -> bool:
        """
        Check if the media is categorized as adult/pornographic and prompt the user for confirmation before uploading to a non-adult tracker.

        :param meta: Metadata dictionary containing category and genre information.
        :param tracker: The tracker name for display in the prompt.
        :return: True if the user confirms or if the media is not adult, False otherwise.
        """
        if meta.adult_media:
            if not meta.unattended or (meta.unattended and meta.unattended_confirm):
                logger.info(f"[bold red]Pornography is not allowed at {tracker}.[/bold red]")
                if cli_ui.ask_yes_no("Do you want to upload anyway?", default=False):
                    pass
                else:
                    return False
            else:
                return False

        return True

    def portuguese_title_capitalization(self, title: str) -> str:
        """Capitalizes a Portuguese title."""
        lowercase_words = {
            # Articles
            "a",
            "o",
            "as",
            "os",
            "um",
            "uma",
            "uns",
            "umas",
            # Prepositions
            "de",
            "do",
            "da",
            "dos",
            "das",
            "em",
            "no",
            "na",
            "nos",
            "nas",
            "por",
            "pelo",
            "pela",
            "pelos",
            "pelas",
            "para",
            "com",
            "sob",
            "sobre",
            "sem",
            # Conjunctions
            "e",
            "ou",
            "mas",
            "nem",
            "que",
            "se",
        }

        # Split by separators (like :, -, (, ), [, ]) so each segment is capitalized independently
        parts = re.split(r"([:\-\(\)\[\]])", title)

        formatted_parts = []
        for part in parts:
            if not part:
                formatted_parts.append("")
                continue
            if re.match(r"^[:\-\(\)\[\]]$", part):
                formatted_parts.append(part)
                continue

            # For this text segment, split into words and spaces
            tokens = re.split(r"(\s+)", part)
            formatted_tokens = []
            word_count = 0

            for token in tokens:
                if not token:
                    formatted_tokens.append("")
                    continue
                if token.isspace():
                    formatted_tokens.append(token)
                    continue

                # This is a word token
                # Extract core word (ignoring punctuation at start/end)
                prefix_match = re.match(r"^[^\w]+", token)
                prefix = prefix_match.group(0) if prefix_match else ""

                suffix_match = re.search(r"[^\w]+$", token)
                suffix = suffix_match.group(0) if suffix_match else ""

                core = token[len(prefix) : len(token) - len(suffix)] if suffix else token[len(prefix) :]

                if not core:
                    # No alphanumeric chars, keep as is
                    formatted_tokens.append(token)
                    word_count += 1
                    continue

                clean_core = core.lower()

                if word_count == 0:
                    # First word in the segment
                    capitalized_core = core[0].upper() + core[1:] if len(core) > 0 else core
                elif clean_core in lowercase_words:
                    capitalized_core = clean_core
                else:
                    capitalized_core = core[0].upper() + core[1:] if len(core) > 0 else core

                formatted_tokens.append(prefix + capitalized_core + suffix)
                word_count += 1

            formatted_parts.append("".join(formatted_tokens))

        return "".join(formatted_parts)

    async def check_nzb_file(self, tracker: str, meta: Meta) -> bool:
        nzb_path = meta.nzb_path
        if not nzb_path or not Path(nzb_path).exists():
            logger.error(f"{tracker}: [red]Error: The NZB file is missing. Aborting upload...[/red]")
            return False

        usenet_cfg = self.config.get("USENET", {})
        # skip_archive means no 7z/rar was created (for either uploader — pesto's
        # --nzb-password only tags NZB metadata, it doesn't encrypt), so a
        # configured password was never applied and won't be in the NZB.
        # That's expected, not an error.
        password_applies = bool(meta.archive_password or usenet_cfg.get("archive_password")) and not usenet_cfg.get("skip_archive", False)
        if password_applies and not await verify_nzb_has_password(nzb_path):
            logger.error(f"{tracker}: [red]Error: The NZB file does not contain the password in its metadata header. Aborting upload...[/red]")
            return False
        return True

    def has_bdinfo(self, content: str) -> bool:
        """
        Check if the provided content contains BDInfo information.
        """
        if not content or not isinstance(content, str):
            return False

        bdinfo_pattern = [
            r"DISC INFO:",
            r"Disc Title:\s*",
            r"Disc Label:\s*",
            r"PLAYLIST REPORT:",
            r"\(\*\)\s*Indicates included stream hidden",
        ]

        combined_regex = "|".join(bdinfo_pattern)

        return bool(re.search(combined_regex, content, re.IGNORECASE))

    async def get_portuguese_tags(
        self,
        meta: Meta,
        tracker: str,
        tmdb_data: dict[str, Any] | None = None,
    ) -> str:
        """
        Map genres from meta.genres, meta.keywords, or TMDB to Portuguese tags formatted with dots."

        BJSHARE rejects more than 5 tags, so we limit the output to 5 tags.
        """
        matched_tags: list[str] = []

        genres_list = meta.genres or meta.keywords or []
        for genre in genres_list:
            genre_lower = genre.strip().lower()
            if not genre_lower:
                continue

            mapped_list: list[str] = []
            if mapped := ENG_TO_PTBR_GENRE_MAP.get(genre_lower):
                mapped_list.append(mapped)
            elif genre_lower in ENG_TO_PTBR_GENRE_MAP.values():
                mapped_list.append(genre_lower)
            elif mapped_audible := AUDIBLE_PTBR_GENRE_MAP.get(genre_lower):
                mapped_list.extend(mapped_audible)
            elif any(genre_lower in vals for vals in AUDIBLE_PTBR_GENRE_MAP.values()):
                mapped_list.append(genre_lower)
            elif mapped_aud_eng := AUDIBLE_ENG_GENRE_MAP.get(genre_lower):
                for p in mapped_aud_eng:
                    if p_mapped := ENG_TO_PTBR_GENRE_MAP.get(p):
                        mapped_list.append(p_mapped)
                    else:
                        mapped_list.append(p)
            elif meta.category == "BOOK":
                mapped_list.append(genre_lower)

            for m in mapped_list:
                if m and m not in matched_tags:
                    matched_tags.append(m)

        if meta.category in ("TV", "MOVIE") and not matched_tags and tmdb_data:
            genres_data: list[dict[str, Any]] = tmdb_data.get("genres", [])
            for g in genres_data:
                name = str(g.get("name", "")).lower().strip()
                if name:
                    mapped = ENG_TO_PTBR_GENRE_MAP.get(name) or (name if name in ENG_TO_PTBR_GENRE_MAP.values() else None)
                    if mapped and mapped not in matched_tags:
                        matched_tags.append(mapped)

        # If we have matched tags, return them
        if matched_tags:
            formatted_tags = [unidecode(t.strip()).replace(" ", ".") for t in matched_tags if t.strip()]
            return ", ".join(formatted_tags[:5])

        if meta.category == "XXX":
            return "adulto"

        if meta.category not in ("GAME", "TV", "MOVIE"):
            return ""

        # Final fallback: ask user
        if meta.unattended and not meta.unattended_confirm:
            logger.info(f"{tracker}: [yellow]Unattended mode: Gêneros não encontrados. Pulando upload para {tracker}.[/yellow]")
            meta.skipping = f"{tracker}"
            return ""

        tags_raw = await prompt_in_thread(cli_ui.ask_string, f"Digite os gêneros (no formato do {tracker}): ")
        raw_list = [unidecode(t.strip()).replace(" ", ".") for t in re.split(r"[,;]", tags_raw or "") if t.strip()]
        return ", ".join(raw_list[:5])
