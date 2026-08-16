# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import asyncio
import json
import platform
from pathlib import Path
from typing import Any, cast

import aiofiles
import cli_ui
import httpx
from rich.markup import escape

from src.cogs.redaction import Redaction
from src.console import logger, prompt_in_thread
from src.get_desc import DescriptionBuilder
from src.mediainfo import strip_report_by_line
from src.meta import Meta
from src.torrentcreate import TorrentCreator
from src.trackers.common import Common

Config = dict[str, Any]


class Anthelion:
    """
    Anthelion (ANT) is a Private Torrent Tracker for MOVIES
    """

    auth_type = "other_api"
    tracker = "ANTHELION"
    display_name = "Anthelion"
    source_flag = "ANT"
    allowed_bloated_audio_languages = ("en",)
    reject_english_original_bloat = True
    banned_groups = (
        "3LTON",
        "4yEo",
        "ADE",
        "AFG",
        "AniHLS",
        "AnimeRG",
        "AniURL",
        "AROMA",
        "aXXo",
        "Brrip",
        "CHD",
        "CM8",
        "CrEwSaDe",
        "d3g",
        "DDR",
        "DeadFish",
        "DNL",
        "ELiTE",
        "eSc",
        "EVO",
        "FaNGDiNG0",
        "FGT",
        "FRDS",
        "FUM",
        "HAiKU",
        "HD2DVD",
        "HDS",
        "HDTime",
        "Hi10",
        "ION10",
        "iPlanet",
        "JIVE",
        "KiNGDOM",
        "Leffe",
        "LiGaS",
        "LOAD",
        "MeGusta",
        "mHD",
        "MkvCage",
        "mSD",
        "NhaNc3",
        "nHD",
        "NOIVTC",
        "nSD",
        "Oj",
        "Ozlem",
        "PiRaTeS",
        "PRoDJi",
        "RAPiDCOWS",
        "RARBG",
        "RDN",
        "REsuRRecTioN",
        "RetroPeeps",
        "RMTeam",
        "SANTi",
        "SicFoI",
        "SM737",
        "SPASM",
        "SPDVD",
        "STUTTERSHIT",
        "TBS",
        "Telly",
        "TM",
        "UPiNSMOKE",
        "URANiME",
        "WAF",
        "xRed",
        "XS",
        "YIFY",
        "YTS",
        "Zeus",
        "ZKBL",
        "ZmN",
        "ZMNT",
    )
    base_url = "https://anthelion.me"
    api_url = f"{base_url}/api.php"
    supported_categories = ("MOVIE",)
    tracker_urls = ("tracker.anthelion.me",)

    def __init__(self, config: Config):
        self.config = config
        self.common = Common(config)
        self.tracker_config = self.config["TRACKERS"].get(self.tracker, {})
        self.api_key: str = str(self.tracker_config.get("api_key", "")).strip()

    async def get_flags(self, meta: Meta) -> list[str]:
        flags: list[str] = []
        flags.extend([each for each in ["Directors", "Extended", "Uncut", "Unrated", "4KRemaster", "IMAX"] if each in meta.edition.replace("'", "")])
        flags.extend([each.replace("-", "") for each in ["Dual-Audio", "Atmos"] if each in meta.audio])
        if meta.has_commentary or meta.manual_commentary:
            flags.append("Commentary")
        if meta.three_d == "3D":
            flags.append("3D")
        if "HDR" in meta.hdr:
            flags.append("HDR10")
        if "DV" in meta.hdr:
            flags.append("DV")
        if "Criterion" in (meta.distributor or meta.edition):
            flags.append("Criterion")
        if meta.type and "REMUX" in meta.type:
            flags.append("Remux")
        return flags

    async def get_release_group(self, meta: Meta) -> str:
        if meta.tag:
            tag = meta.tag

            return tag[1:]  # Remove leading character

        return ""

    async def get_tags(self, meta: Meta) -> list[str] | str:
        meta.ant_user_tags = False
        no_tags = False
        tags: list[str] = []
        if meta.genres:
            genres = meta.genres
            # Handle both string and list formats
            if isinstance(genres, str):
                tags.append(genres.replace(" ", ".").lower())
            else:
                tags.extend(genre.replace(" ", ".").lower() for genre in genres)
        else:
            no_tags = True
        if no_tags and meta.imdb_info:
            imdb_genres = meta.imdb_info.get("genres", [])
            # Handle both string and list formats
            if isinstance(imdb_genres, str):
                tags.append(imdb_genres.replace(" ", ".").lower())
            else:
                tags.extend(genre.replace(" ", ".").lower() for genre in imdb_genres)
            allowed_tags = {
                "action",
                "adventure",
                "animation",
                "comedy",
                "crime",
                "documentary",
                "drama",
                "family",
                "fantasy",
                "history",
                "horror",
                "music",
                "mystery",
                "romance",
                "sci.fi",
                "thriller",
                "war",
                "western",
            }
            tags = [tag for tag in tags if tag.lower() in allowed_tags]

            if tags:
                logger.info(f"{self.tracker}: [green]Using IMDb genres for tagging: {', '.join(tags)}")
                logger.info(
                    f"{self.tracker}: [yellow]api will accept this upload, but no tag will be added.\nYou must manually add at least one tag from the approved list when uploaded."
                )
                await asyncio.sleep(3)
                meta.ant_user_tags = True

        if not tags:
            if meta.unattended and not meta.unattended_confirm:
                logger.info(f"{self.tracker}: [yellow]Unattended mode: No genres found for tagging. Skipping {self.tracker} upload.[/yellow]")
                meta.skipping = f"{self.tracker}"
                return ""
            logger.info(f"{self.tracker}: [yellow]No genres found for tagging. Tag required.")
            logger.info(f"{self.tracker}: [yellow]Only use a tag in the approved list found in the site search box.")
            logger.info(
                f"{self.tracker}: [yellow]api will accept this upload, but no tag will be added.\nYou must manually add at least one tag from the approved list when uploaded."
            )
            await asyncio.sleep(3)
            user_tag = await prompt_in_thread(cli_ui.ask_string, "Please enter at least one tag (genre) to use for the upload", default="")
            if user_tag:
                tags.append(user_tag.replace(" ", ".").lower())
                meta.ant_user_tags = True

        return tags if not no_tags else ""

    async def get_type(self, meta: Meta) -> int:
        ant_type = None
        imdb_info = meta.imdb_info
        if imdb_info.get("type") is not None:
            imdb_type = imdb_info.get("type", "movie").lower()
            if imdb_type in ("movie", "tv movie", "tvmovie"):
                ant_type = 0 if int(imdb_info.get("runtime", "60")) >= 45 or int(imdb_info.get("runtime", "60")) == 0 else 1
            if imdb_type == "short":
                ant_type = 1
            elif imdb_type == "tv mini series":
                ant_type = 2
            elif imdb_type == "comedy":
                ant_type = 3
        else:
            keywords = [k.lower() for k in meta.keywords]
            tmdb_type = (meta.tmdb_type if meta.tmdb_type is not None else "movie").lower()
            if tmdb_type == "movie":
                ant_type = 0 if (meta.runtime if meta.runtime is not None else 60) >= 45 or (meta.runtime if meta.runtime is not None else 60) == 0 else 1
            if tmdb_type == "miniseries" or "miniseries" in keywords:
                ant_type = 2
            if "short" in keywords or "short film" in keywords:
                ant_type = 1
            elif "stand-up comedy" in keywords:
                ant_type = 3

        if ant_type is None:
            if not meta.unattended:
                ant_type_list = ["Feature Film", "Short Film", "Miniseries", "Other"]
                choice = await prompt_in_thread(cli_ui.ask_choice, "Select the proper type for ANTHELION", choices=ant_type_list)
                # Map the choice back to the integer
                type_map = {"Feature Film": 0, "Short Film": 1, "Miniseries": 2, "Other": 3}
                ant_type = type_map.get(choice, 0)
            else:
                logger.debug(f"{self.tracker}: [bold red]type could not be determined automatically in unattended mode.")
                ant_type = 0  # Default to Feature Film in unattended mode

        return ant_type

    async def upload(self, meta: Meta) -> bool:
        torrent_filename = "BASE"
        torrent_path = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/BASE.torrent"
        torrent_file_size_kib = Path(torrent_path).stat().st_size / 1024
        tracker_url: str = ""
        if meta.mkbrr:
            tracker_url = self.tracker_config.get("announce_url", "https://fake.tracker").strip()

        # Trigger regeneration automatically if size constraints aren't met
        if torrent_file_size_kib > 250:  # 250 KiB
            logger.info(f"{self.tracker}: [yellow]Existing .torrent exceeds 250 KiB and will be regenerated to fit constraints.")
            meta.max_piece_size = 128  # 128 MiB
            await TorrentCreator.create_torrent(meta, str(Path(str(meta.path))), "ANTHELION", tracker_url=tracker_url)
            torrent_filename = "ANTHELION"

        await self.common.create_torrent_for_upload(meta, self.tracker, self.source_flag, torrent_filename=torrent_filename)
        flags = await self.get_flags(meta)
        audioformat = await self.get_audio(meta)
        if not audioformat:
            logger.info(f"{self.tracker}: [bold red]upload aborted due to unsupported audio format.")
            meta.tracker_status[self.tracker]["status_message"] = "data error: upload aborted: unsupported audio format"
            return False

        torrent_file_path = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/[{self.tracker}].torrent"
        async with aiofiles.open(torrent_file_path, "rb") as f:
            torrent_bytes = await f.read()
        files = {"file_input": ("torrent.torrent", torrent_bytes, "application/x-bittorrent")}
        data: dict[str, Any] = {
            "type": await self.get_type(meta),
            "audioformat": audioformat,
            "api_key": str(self.tracker_config.get("api_key", "")).strip(),
            "action": "upload",
            "tmdbid": meta.tmdb,
            "flags[]": flags,
            "release_desc": await self.edit_desc(meta),
        }

        if meta.is_disc == "BDMV":
            async with aiofiles.open(f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/BD_SUMMARY_00.txt", encoding="utf-8") as f:
                bdinfo_output = await f.read()
            data.update({"bdinfo": bdinfo_output})
            data.update({"container_type": "m2ts"})
        else:
            mi_path = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/MEDIAINFO_CLEANPATH.txt"
            async with aiofiles.open(mi_path, encoding="utf-8") as f:
                mediainfo_output = strip_report_by_line(await f.read())
            data.update({"mediainfo": mediainfo_output})
        if meta.scene:
            # ID of "Scene?" checkbox on upload form is actually "censored"
            data["censored"] = 1

        tags = await self.get_tags(meta)
        if getattr(meta, "skipping", None) == self.tracker:
            return False
        if tags != "":
            data.update({"tags": ",".join(tags)})

        release_group = await self.get_release_group(meta)
        if release_group and release_group not in self.banned_groups:
            data.update({"releasegroup": release_group})
        else:
            data.update({"noreleasegroup": 1})

        if meta.adult_media:
            if not meta.unattended or (meta.unattended and meta.unattended_confirm):
                logger.info(f"{self.tracker}: [bold red]Adult content detected[/bold red]")
                if await prompt_in_thread(cli_ui.ask_yes_no, "Are the screenshots safe?", default=False):
                    data.update({"screenshots": "\n".join([x["raw_url"] for x in meta.image_list][:4])})
                    if not meta.ant_user_tags:
                        data.update({"flagchangereason": f"Adult with screens uploaded with {meta.ua_name}"})
                    else:
                        data.update({"flagchangereason": f"Adult with screens uploaded with {meta.ua_name}. User to add tags manually."})
                else:
                    data.update({"screenshots": ""})  # No screenshots for adult content
            else:
                data.update({"screenshots": ""})
        else:
            data.update({"screenshots": "\n".join([x["raw_url"] for x in meta.image_list][:4])})
            if meta.ant_user_tags:
                data.update({"flagchangereason": "User prompted to add tags manually"})

        headers = {
            "User-Agent": f"{meta.ua_name} {(meta.current_version if meta.current_version is not None else 'github.com/wastaken7/Upload-Assistant')} ({platform.system()} {platform.release()})"
        }

        try:
            if not meta.debug:
                async with httpx.AsyncClient(timeout=40) as client:
                    response = await client.post(url=self.api_url, files=files, data=data, headers=headers)
                    try:
                        response_data: dict[str, Any] = response.json()
                    except json.JSONDecodeError:
                        meta.tracker_status[self.tracker]["status_message"] = "data error: ANTHELION json decode error, the API is probably down"
                        return False

                    if response.status_code in [200, 201]:
                        is_success = ("success" in response_data) or (str(response_data.get("status", "")).lower() == "success")
                        if not is_success:
                            meta.tracker_status[self.tracker]["status_message"] = f"data error: {response_data}"
                            return False
                        meta.tracker_status[self.tracker]["status_message"] = response_data
                        return True

                    response_data = {"error": f"ANTHELION returned status code: {response.status_code}", "response_content": response.text}
                    meta.tracker_status[self.tracker]["status_message"] = f"data error - {response_data}"
                    return False
            else:
                if "mediainfo" in data:
                    debug_mediainfo_path = Path(meta.base_dir) / "tmp" / str(meta.uuid) / f"{self.tracker}_MEDIAINFO.txt"
                    async with aiofiles.open(debug_mediainfo_path, "w", newline="", encoding="utf-8") as f:
                        await f.write(str(data["mediainfo"]))
                    logger.info(f"{self.tracker}: [green]Final MediaInfo payload written to {debug_mediainfo_path}[/green]")
                logger.info(f"{self.tracker}: Request Data:")
                logger.info(Redaction.redact_private_info(data))
                meta.tracker_status[self.tracker]["status_message"] = "Debug mode enabled, not uploading."
                await self.common.create_torrent_for_upload(meta, f"{self.tracker}" + "_DEBUG", f"{self.tracker}" + "_DEBUG", announce_url="https://fake.tracker")
                return True
        except httpx.TimeoutException:
            meta.tracker_status[self.tracker]["status_message"] = "data error: ANTHELION request timed out while uploading."
            return False
        except httpx.RequestError as e:
            meta.tracker_status[self.tracker]["status_message"] = f"data error: An error occurred while making the request: {e}"
            return False
        except Exception as e:
            import traceback

            error_type = type(e).__name__
            error_msg = str(e) if str(e) else "No error message"
            traceback_str = traceback.format_exc()
            logger.info(f"{self.tracker}: [bold red]upload exception ({error_type}): {escape(error_msg)}[/bold red]")
            logger.info(f"{self.tracker}: [red]Traceback:\n{escape(traceback_str)}[/red]")
            meta.tracker_status[self.tracker]["status_message"] = "data error: double check if it uploaded"
            return False

    async def get_audio(self, meta: Meta) -> str:
        """
        Possible values:
        DD+, DD, DTS-HD MA, DTS, TrueHD, FLAC, PCM, OPUS, AAC, MP3, MP2
        """
        audio = meta.audio
        if not audio:
            return "NoAudio"

        audio_map = {
            "DD+": "EAC3",
            "DD": "AC3",
            "DTS-HD MA": "DTSMA",
            "DTS": "DTS",
            "TRUEHD": "TrueHD",
            "FLAC": "FLAC",
            "PCM": "PCM",
            "OPUS": "Opus",
            "AAC": "AAC",
            "MP3": "MP3",
            "MP2": "MP2",
        }
        for key, value in audio_map.items():
            if key in audio.upper():
                return value
        logger.info(
            f"{self.tracker}: Unexpected audio format: {audio}. The format must be one of the following: DD+, DD, DTS-HD MA, DTS, TRUEHD, FLAC, PCM, OPUS, AAC, MP3, MP2"
        )
        logger.info(f"{self.tracker}: Audio will be set to 'Other'. [bold red]Correct manually if necessary.[/bold red]")
        return "Other"

    async def edit_desc(self, meta: Meta) -> str:
        builder = DescriptionBuilder(self.tracker, self.config)
        user_desc = await builder.get_user_description(meta)
        has_user_desc = bool(user_desc.strip())

        return await builder.general_description_generator(
            meta,
            bluray=False,
            book=False,
            custom_header=has_user_desc,
            custom_signature=False,
            description=False,
            game=False,
            logo=has_user_desc,
            mediainfo=False,
            nfo=False,
            screenshots=False,
            tv_info=False,
            ua_signature=False,
            user_description=has_user_desc,
        )

    async def get_additional_checks(self, meta: Meta) -> bool:
        if meta.valid_mi is False:
            if not meta.unattended:
                logger.info(f"{self.tracker}: [bold red]No unique ID in mediainfo, skipping {self.tracker} upload.")
            return False

        return True

    async def search_existing(self, meta: Meta) -> list[dict[str, Any]]:
        dupes: list[dict[str, Any]] = []

        params = {"t": "search", "o": "json"}
        if meta.tmdb:
            params["tmdbid"] = str(meta.tmdb)
        elif meta.imdb_id:
            params["imdbid"] = str(meta.imdb)

        headers = {
            "X-API-Key": self.api_key,
            "User-Agent": f"{meta.ua_name} {(meta.current_version if meta.current_version is not None else 'github.com/wastaken7/Upload-Assistant')} ({platform.system()} {platform.release()})",
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url=self.api_url, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()
            target_resolution = str(meta.resolution or "").lower()
            raw_items = data.get("item", [])

            if not isinstance(raw_items, list):
                logger.warning(f"{self.tracker}: Unexpected search response: 'item' is not a list.")
                return dupes

            items = cast(list[Any], raw_items)
            for each in items:
                if not isinstance(each, dict):
                    logger.warning(f"{self.tracker}: Skipping malformed search result.")
                    continue
                search_result = cast(dict[str, Any], each)

                resolution = str(search_result.get("resolution") or "")
                if target_resolution and resolution.lower() != target_resolution:
                    logger.debug(
                        f"{self.tracker}: [yellow]Skipping {escape(str(search_result.get('fileName') or ''))} - resolution mismatch: {resolution} vs {target_resolution}"
                    )
                    continue

                largest_file: Any = None
                raw_files = search_result.get("files", [])
                files = cast(list[Any], raw_files) if isinstance(raw_files, list) else []
                valid_files: list[dict[str, Any]] = [cast(dict[str, Any], file) for file in files if isinstance(file, dict)]
                if valid_files:
                    largest = max(valid_files, key=lambda file: int(file.get("size") or 0))
                    largest_file = largest.get("name", "")

                result: dict[str, Any] = {
                    "name": largest_file or search_result.get("fileName", ""),
                    "files": [cast(dict[str, Any], file).get("name", "") for file in files if isinstance(file, dict)],
                    "size": int(search_result.get("size", 0)),
                    "link": search_result.get("guid", ""),
                    "flags": search_result.get("flags", []),
                    "file_count": search_result.get("fileCount", 0),
                    "download": search_result.get("link", "").replace("&amp;", "&"),
                }
                dupes.append(result)

                logger.debug(f"{self.tracker}: [green]Found potential dupe: {escape(result['name'])} ({result['size']} bytes)")

        return dupes

    async def get_data_from_files(self, meta: Meta) -> list[dict[str, Any]]:
        imdb_tmdb_list: list[dict[str, Any]] = []
        if meta.is_disc:
            return imdb_tmdb_list

        filelist: list[str] = meta.filelist
        if not filelist:
            logger.debug(f"{self.tracker}: [yellow]No files in filelist, skipping file-based search.")
            return imdb_tmdb_list

        filename: str = Path(filelist[0]).name

        api_key = self.tracker_config.get("api_key")
        if not api_key or not isinstance(api_key, str) or not api_key.strip():
            logger.debug(f"{self.tracker}: [yellow]API key not configured, skipping file-based search.")
            return imdb_tmdb_list

        headers = {"X-API-Key": api_key.strip(), "User-Agent": f"Upload Assistant/2.4 ({platform.system()} {platform.release()})"}

        params: dict[str, Any] = {"t": "search", "filename": filename, "o": "json"}

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(url=self.api_url, params=params, headers=headers)
                if response.status_code == 200:
                    try:
                        data = response.json()
                        items = data.get("item", [])

                        matched_item = None
                        if len(items) == 1:
                            matched_item = items[0]
                        elif len(items) > 1:
                            # Try to match filename from the files in each result
                            for item in items:
                                files = item.get("files", [])
                                for file in files:
                                    file_name = file.get("name", "")

                                    # Try exact match first (with extension)
                                    if filename.lower() == file_name.lower():
                                        matched_item = item
                                        break

                                    # Try base filename match (without extension)
                                    base_filename = Path(filename).stem
                                    base_file_name = Path(file_name).stem
                                    if base_filename.lower() == base_file_name.lower():
                                        matched_item = item
                                        break
                                if matched_item:
                                    break

                            if not matched_item:
                                logger.debug(f"{self.tracker}: [yellow]Could not match filename, returning empty list")
                                imdb_tmdb_list = []

                        if matched_item:
                            imdb_id = matched_item.get("imdb")
                            tmdb_id = matched_item.get("tmdb")
                            if imdb_id and imdb_id.startswith("tt"):
                                imdb_num = int(imdb_id[2:])
                                imdb_tmdb_list.append({"imdb_id": imdb_num})
                            if tmdb_id and str(tmdb_id).isdigit() and int(tmdb_id) != 0:
                                imdb_tmdb_list.append({"tmdb_id": int(tmdb_id)})
                    except json.JSONDecodeError:
                        logger.info(f"{self.tracker}: [bold yellow]Error parsing JSON response from {self.tracker}")
                        imdb_tmdb_list = []
                else:
                    logger.info(f"{self.tracker}: [bold red]Failed to search torrents. HTTP Status: {response.status_code}")
                    imdb_tmdb_list = []
        except httpx.TimeoutException:
            logger.info(f"{self.tracker}: [bold red]Request timed out after 5 seconds")
            imdb_tmdb_list = []
        except httpx.RequestError as e:
            logger.info(f"{self.tracker}: [bold red]Unable to search for existing torrents: {escape(str(e))}")
            imdb_tmdb_list = []
        except Exception as e:
            logger.error(f"{self.tracker}: [bold red]Unexpected error: {escape(str(e))}")
            imdb_tmdb_list = []

        return imdb_tmdb_list

    async def get_name(self, meta: Meta) -> str:
        return meta.title
