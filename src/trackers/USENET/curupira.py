# Upload Assistant © 2026 Audionut & wastaken7 — Licensed under UAPL v1.0
import contextlib
import json
from pathlib import Path
from typing import Any, cast
from xml.etree import ElementTree

import aiofiles
import httpx
import langcodes

from src.cogs.redaction import Redaction
from src.console import logger
from src.meta import Meta
from src.tracker_images import get_tracker_image_collection
from src.trackers.common import Common
from src.trackers.USENET.search_helpers import build_newznab_search_query, parse_newznab_dupes

Config = dict[str, Any]


class Curupira:
    """
    CRP Private Torrent Tracker
    """

    base_url = "https://curupira.cc"

    auth_type = "other_api"
    tracker = "CURUPIRA"
    display_name = "Curupira"
    banned_groups = (
        "4K4U",
        "afm72",
        "Alcaide_Kira",
        "AROMA",
        "ASM",
        "Bandi",
        "BiTOR",
        "BLUDV",
        "Bluespots",
        "BOLS",
        "CaNNIBal",
        "Comando",
        "d3g",
        "DepraveD",
        "EMBER",
        "Emmid",
        "FGT",
        "FreetheFish",
        "Garshasp",
        "Ghost",
        "Grym",
        "HDS",
        "Hi10",
        "HiQVE",
        "Hiro360",
        "ImE",
        "ION10",
        "iVy",
        "Judas",
        "LAMA",
        "Langbard",
        "Lapumia",
        "LION",
        "MeGusta",
        "Memoriadatv",
        "MONOLITH",
        "MRCS",
        "NaNi",
        "Natty",
        "nikt0",
        "OEPlus",
        "OFT",
        "OsC",
        "Panda",
        "PANDEMONiUM",
        "PHOCiS",
        "PiRaTeS",
        "PYC",
        "r00t",
        "Ralphy",
        "RARBG",
        "RetroPeeps",
        "RZeroX",
        "S74Ll10n",
        "SAMPA",
        "Sicario",
        "SiCFoI",
        "Silence",
        "SkipTT",
        "SM737",
        "SPDVD",
        "STUTTERSHIT",
        "SWTYBLZ",
        "t3nzin",
        "TAoE",
        "TEKNO3D",
        "Telly",
        "TGx",
        "Tigole",
        "TSP",
        "TSPxL",
        "TWA",
        "UnKn0wn",
        "VXT",
        "Vyndros",
        "W32",
        "Will1869",
        "x0r",
        "YIFY",
        "YTS.MX",
        "YTS",
    )
    upload_url = f"{base_url}/v1/releases"
    torrent_url = f"{base_url}/releases/"
    supported_categories = ("TV", "MOVIE", "GAME", "BOOK")
    is_usenet = True
    allows_bloated_audio = True
    exact_match_only = False

    def __init__(self, config: Config) -> None:
        self.config = config
        self.common = Common(config)
        self.api_key = self.config.get("TRACKERS", {}).get(self.tracker, {}).get("api_key", "").strip()

    async def get_search_name(self, meta: Meta) -> str:
        return await self.get_name(meta)

    def get_search_query(self, meta: Meta) -> str:
        return build_newznab_search_query(meta)

    def _parse_dupes_from_response(self, response_text: str) -> list[dict[str, Any]]:
        return parse_newznab_dupes(response_text)

    async def search_existing(self, meta: Meta) -> list[Any]:
        release_name = await self.get_name(meta)
        cache_file = Path(meta.base_dir) / "tmp" / meta.uuid / f"{self.tracker}_upload_ok"
        if release_name and Path(cache_file).exists():
            logger.info(f"{self.tracker}: [yellow]Found local upload cache.[/yellow]")
            return [release_name]

        params_list: list[dict[str, str]] = []
        exact_name = await self.get_search_name(meta)
        if exact_name:
            params_list.append(
                {
                    "t": "search",
                    "q": exact_name,
                }
            )

        params: dict[str, str] = {}

        category = meta.category.upper()

        if category == "TV":
            params["t"] = "tvsearch"
            if meta.tvdb_id and str(meta.tvdb_id).isdigit() and int(meta.tvdb_id) > 0:
                params["tvdbid"] = str(meta.tvdb_id)
            elif meta.tmdb_id and str(meta.tmdb_id).isdigit() and int(meta.tmdb_id) > 0:
                params["tmdbid"] = str(meta.tmdb_id)
            elif meta.imdb_id and int(meta.imdb_id) > 0:
                params["imdbid"] = f"tt{meta.imdb}"
            else:
                params["q"] = self.get_search_query(meta)

            if meta.season_int > 0:
                params["season"] = str(meta.season_int)
            if meta.episode_int > 0:
                params["ep"] = str(meta.episode_int)
        elif category == "MOVIE":
            params["t"] = "movie"
            if meta.imdb_id and int(meta.imdb_id) > 0:
                params["imdbid"] = f"tt{meta.imdb}"
            elif meta.tmdb_id and str(meta.tmdb_id).isdigit() and int(meta.tmdb_id) > 0:
                params["tmdbid"] = str(meta.tmdb_id)
            else:
                params["q"] = self.get_search_query(meta)
        else:
            params["t"] = "search"
            params["cat"] = self.get_category_id(meta)
            params["q"] = self.get_search_query(meta)

        if "q" not in params or not params["q"]:
            params["q"] = self.get_search_query(meta)

        params_list.append(params)

        dupes: list[dict[str, Any]] = []
        seen_keys: set[str] = set()
        async with httpx.AsyncClient(timeout=10.0) as client:
            for query_params in params_list:
                try:
                    request_params = {
                        "apikey": str(self.api_key),
                        "limit": "100",
                        **query_params,
                    }
                    response = await client.get(f"{self.base_url}/api", params=request_params)

                    if response.status_code != 200 or not response.text.strip():
                        logger.info(f"{self.tracker}: [yellow]Duplicate search failed with HTTP {response.status_code}.[/yellow]")
                        continue

                    for dupe in self._parse_dupes_from_response(response.text):
                        key = str(dupe.get("link") or dupe.get("name") or "")
                        if key in seen_keys:
                            continue
                        seen_keys.add(key)
                        dupes.append(dupe)
                except ElementTree.ParseError:
                    logger.info(f"{self.tracker}: [yellow]Failed to parse duplicate search response.[/yellow]")
                except httpx.TimeoutException:
                    logger.info(f"{self.tracker}: [yellow]Duplicate search timed out.[/yellow]")
                except httpx.RequestError as e:
                    logger.info(f"{self.tracker}: [yellow]Duplicate search request failed: {e}[/yellow]")

        return dupes

    async def get_additional_checks(self, _meta: Meta) -> bool:
        return True

    def get_category_id(self, meta: Meta) -> str:
        # Check if anime
        if meta.anime:
            return "5070"

        category = meta.category.upper()
        resolution = meta.resolution.lower()

        uhd_resolutions = {"2160p", "4320p", "8640p"}
        hd_resolutions = {"1080p", "1080i", "720p", "1440p"}

        if category == "MOVIE":
            if resolution in uhd_resolutions:
                return "2045"
            if resolution in hd_resolutions:
                return "2040"
            return "2030"
        if category == "TV":
            if resolution in uhd_resolutions:
                return "5045"
            if resolution in hd_resolutions:
                return "5040"
            return "5030"
        if category == "BOOK":
            if meta.audiobook:
                return "3030"
            return "7020"
        if category == "GAME":
            return "4050"
        if category == "MUSIC":
            return "3000"

        # Fallback to general TV HD or Movies HD/SD depending on category
        if category == "TV":
            return "5000"
        return "2000"

    async def get_name(self, meta: Meta) -> str:
        return meta.scene_name or meta.basename_no_ext

    def get_iso_639_1(self, lang_name: str) -> str | None:
        with contextlib.suppress(Exception):
            lang = langcodes.find(lang_name)
            if lang and lang.is_valid():
                return lang.language
        return None

    def get_source(self, meta: Meta) -> str | None:
        source = meta.source
        if not source:
            return None
        source_upper = source.upper()
        if "BLU" in source_upper:
            if meta.is_disc:
                return "Full Disc"
            return "BluRay"
        if "WEB" in source_upper:
            return "WEBRip" if meta.type == "WEBRIP" else "WEB-DL"
        if "HDTV" in source_upper:
            return "HDTV"
        if "DVD" in source_upper:
            return "DVD"
        return source

    async def _prepare_files(self, meta: Meta) -> dict[str, Any] | None:
        nzb_path = meta.nzb_path

        if not nzb_path or not await self.common.check_nzb_file(self.tracker, meta):
            return None

        # Prepare multipart/form-data
        async with aiofiles.open(nzb_path, "rb") as f:
            nzb_content = await f.read()

        files = {"nzb_file": (Path(nzb_path).name, nzb_content, "application/x-nzb")}

        # NFO file (optional)
        nfo_dir = Path(meta.base_dir) / "tmp" / meta.uuid
        nfo_files = list(nfo_dir.glob("*.nfo"))
        nfo_path = nfo_files[0] if nfo_files else None
        if nfo_path and nfo_path.exists():
            async with aiofiles.open(nfo_path, "rb") as f:
                nfo_content = await f.read()
            files["nfo_file"] = (nfo_path.name, nfo_content, "application/octet-stream")

        return files

    async def get_media_info(self, meta: Meta) -> str:
        info_file_path = ""
        info_file_path = (
            f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/BD_SUMMARY_00.txt"
            if meta.is_disc == "BDMV"
            else f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/MEDIAINFO_CLEANPATH.txt"
        )

        if Path(info_file_path).exists():
            try:
                async with aiofiles.open(info_file_path, encoding="utf-8") as f:
                    return await f.read()
            except Exception as e:
                logger.info(f"{self.tracker}: [bold red]Erro ao ler o arquivo de info em {info_file_path}: {e}[/bold red]")
                return ""
        else:
            logger.info(f"[bold red]Arquivo de info não encontrado: {info_file_path}[/bold red]")
            return ""

    def get_cover(self, meta: Meta) -> str:
        covers = meta.hosted_artwork
        if isinstance(covers, list):
            for entry in covers:
                if not isinstance(entry, dict):
                    continue
                raw_url = entry.get("raw_url")
                if isinstance(raw_url, str) and raw_url.startswith("https://"):
                    return raw_url

        artwork_url = meta.artwork_url
        if isinstance(artwork_url, str) and artwork_url.startswith("https://"):
            return artwork_url

        return ""

    async def get_screens(self, meta: Meta) -> list[str]:
        menu_images = [cast(dict[str, Any], img) for img in get_tracker_image_collection(meta, self.tracker, "menu_images") if isinstance(img, dict)]
        images_value = get_tracker_image_collection(meta, self.tracker, "screenshots")
        image_entries: list[Any] = cast(list[Any], images_value) if isinstance(images_value, list) else []
        images_list = [cast(dict[str, Any], img) for img in image_entries if isinstance(img, dict)]
        spectrograms_images = [cast(dict[str, Any], img) for img in get_tracker_image_collection(meta, self.tracker, "spectrograms_images") if isinstance(img, dict)]
        dynamic_hdr_plot_images = [cast(dict[str, Any], img) for img in get_tracker_image_collection(meta, self.tracker, "dynamic_hdr_plot_images") if isinstance(img, dict)]

        non_hdr_images = menu_images + images_list + spectrograms_images
        valid_dynamic_hdr_plots = [image for image in dynamic_hdr_plot_images if isinstance(image.get("raw_url"), str) and image["raw_url"]]
        # Curupira accepts at most six URLs. Reserve slots for metadata plots,
        # which are appended after screenshots in the normal display order.
        combined_images = non_hdr_images[: max(0, 6 - len(valid_dynamic_hdr_plots))] + valid_dynamic_hdr_plots

        urls: list[str] = []
        for image in combined_images:
            raw_url = image.get("raw_url")
            if isinstance(raw_url, str) and raw_url:
                urls.append(raw_url)

        return urls[:6]

    async def _prepare_data(self, meta: Meta) -> dict[str, Any]:
        screenshot_urls = await self.get_screens(meta)
        data = {
            "name": await self.get_name(meta),
            "category_id": self.get_category_id(meta),
        }

        # Cover
        if meta.category not in ("MOVIE", "TV"):
            cover_url = self.get_cover(meta)
            if cover_url:
                data["custom_cover_url"] = cover_url

        # MediaInfo text (optional)
        if meta.category in ("TV", "MOVIE") or meta.audiobook:
            data["mediainfo_text"] = await self.get_media_info(meta)

        # Quality (optional)
        quality = meta.resolution
        if quality and quality.upper() != "OTHER":
            data["quality"] = quality

        # Source (optional)
        source = self.get_source(meta)
        if source:
            data["source"] = source

        if meta.is_disc:
            # Audio and Subtitles languages (optional, as ISO 639-1 JSON array)
            audio_langs: list[str] = []
            for lang in meta.audio_languages or []:
                iso = self.get_iso_639_1(lang)
                if iso:
                    audio_langs.append(iso)
            if audio_langs:
                data["audio_langs"] = json.dumps(audio_langs)
            subtitle_languages = meta.subtitle_languages
            subtitle_langs = (
                subtitle_languages if isinstance(subtitle_languages, list) else [subtitle_languages] if isinstance(subtitle_languages, str) and subtitle_languages else []
            )
            subs_langs: list[str] = []
            for lang in subtitle_langs:
                iso = self.get_iso_639_1(lang)
                if iso:
                    subs_langs.append(iso)
            if subs_langs:
                data["subs_langs"] = json.dumps(subs_langs)

        # TMDb id and type (optional)
        tmdb_id = meta.tmdb_id
        if tmdb_id and str(tmdb_id).isdigit() and tmdb_id > 0:
            data["tmdb_id"] = str(tmdb_id)
            tmdb_type = meta.category.lower()
            if tmdb_type in ("movie", "tv"):
                data["tmdb_type"] = tmdb_type

        # MyAnimeList id (optional)
        mal_id = meta.mal_id
        if mal_id and str(mal_id).isdigit() and mal_id > 0:
            data["mal_id"] = str(mal_id)

        # Anonymous (optional)
        anon = 0 if meta.anon == 0 and not self.config.get("TRACKERS", {}).get(self.tracker, {}).get("anon", False) else 1
        if anon:
            data["anonymous"] = "true"

        # Screenshots (optional)
        if screenshot_urls:
            data["screenshot_urls"] = json.dumps(screenshot_urls[:6])

        return data

    async def upload(self, meta: Meta) -> bool | None:
        status_map = meta.tracker_status
        if self.tracker not in status_map:
            status_map[self.tracker] = {}
        status_dict = status_map[self.tracker]

        if not await self.common.check_nzb_file(self.tracker, meta):
            status_dict["status_message"] = "data error: NZB file missing or password missing in header"
            return False

        files = await self._prepare_files(meta)
        if not files:
            logger.error(f"{self.tracker}: [red]Error: NZB file not found for {self.tracker}.[/red]")
            status_dict["status_message"] = "data error: NZB file not found"
            return False

        data = await self._prepare_data(meta)

        if meta.debug:
            logger.debug(f"{self.tracker}: [cyan]Upload (DEBUG MODE):[/cyan]")
            logger.debug(f"{self.tracker}: URL: {self.upload_url}")
            logger.debug(f"{self.tracker}: Category ID: {self.get_category_id(meta)}")
            logger.debug(f"{self.tracker}: Fields:")
            logger.debug(Redaction.redact_private_info(data))
            logger.debug(f"{self.tracker}: Files:")
            logger.debug({k: v[0] for k, v in files.items()})

            status_dict["status_message"] = "Debug mode enabled, skipping upload."
            return True

        # Perform actual upload
        params = {"apikey": self.api_key}
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    self.upload_url,
                    files=files,
                    data=data,
                    params=params,
                    headers={"User-Agent": f"Upload-Assistant {(meta.current_version if meta.current_version is not None else 'github.com/wastaken7/Upload-Assistant')}"},
                )

            if response.status_code not in (200, 201):
                status_dict["status_message"] = f"data error: HTTP {response.status_code} - {response.text}"
                return False

            response_json = response.json()
            status_dict["status_message"] = "Upload successful"

            cache_dir = Path(meta.base_dir) / "tmp" / meta.uuid
            Path(cache_dir).mkdir(parents=True, exist_ok=True)
            async with aiofiles.open(Path(cache_dir) / f"{self.tracker}_upload_ok", "w", encoding="utf-8") as cache_handle:
                await cache_handle.write("ok")

            # Try to grab release ID from response
            release_id = response_json.get("public_id")
            if release_id:
                status_dict["torrent_id"] = str(release_id)

            return True

        except httpx.TimeoutException:
            status_dict["status_message"] = "data error: Request timed out after 60 seconds"
            return False
        except httpx.RequestError as e:
            status_dict["status_message"] = f"data error: Unable to upload. Error: {e}"
            return False
        except Exception as e:
            status_dict["status_message"] = f"data error: Unexpected error. Error: {e}"
            return False
