# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import asyncio
import contextlib
import functools
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

from src.bbcode import BBCODE
from src.console import console, logger, prompt_in_thread
from src.exportmi import export_info
from src.languages import languages_manager
from src.meta import Meta
from src.usenetcreate import verify_nzb_has_password


@functools.lru_cache(maxsize=1)
def _get_unit3d_default_ids() -> dict[str, Any]:
    json_path = Path(__file__).resolve().parent.parent.parent / "data" / "unit3d_default_ids.json"
    if json_path.exists():
        with contextlib.suppress(Exception), json_path.open(encoding="utf-8") as f:
            return json.load(f)
    return {}


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
                return None

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
        region_map = _get_unit3d_default_ids().get("regions", {})

        if reverse:
            try:
                target_id = str(int(region_id))
            except ValueError, TypeError:
                return ""
            for code, id_value in region_map.items():
                if str(id_value) == target_id:
                    return code
            return ""
        region_id_value = region_map.get(region.upper()) or region_map.get(region)
        return str(region_id_value) if region_id_value else ""

    async def unit3d_distributor_ids(self, distributor: str = "", reverse: bool = False, distributor_id: int = 0) -> str:
        distributor_map = _get_unit3d_default_ids().get("distributors", {})

        if reverse:
            try:
                target_id = str(int(distributor_id))
            except ValueError, TypeError:
                return ""
            for name, id_value in distributor_map.items():
                if str(id_value) == target_id:
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
            selection = (await prompt_in_thread(cli_ui.ask_string, f"Do you want to use these IDs from {tracker_name}? (Y/n): ", default="") or "").strip().lower()
            try:
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
