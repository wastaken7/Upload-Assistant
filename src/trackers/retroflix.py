# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import base64
import datetime
import re
from typing import Any, cast

import aiofiles
import httpx

from src.cogs.redaction import Redaction
from src.console import logger
from src.get_desc import DescriptionBuilder
from src.meta import Meta
from src.trackers.common import Common


class RetroFlix:
    """
    RTF Private Torrent Tracker
    """

    base_url = "https://retroflix.club"

    auth_type = "other_api"
    tracker = "RETROFLIX"
    display_name = "RetroFlix"
    allows_bloated_audio = True
    source_flag = "sunshine"
    banned_groups: tuple[str, ...] = ()
    upload_url = f"{base_url}/api/upload"
    search_url = f"{base_url}/api/torrent"
    torrent_url = f"{base_url}/browse/t/"
    forum_link = f"{base_url}/forums.php?action=viewtopic&topicid=3619"
    tracker_urls = ("peer.retroflix",)
    supported_categories = ("TV", "MOVIE")

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    async def upload(self, meta: Meta) -> bool:
        """Upload a torrent to RETROFLIX tracker.

        Args:
            meta: Metadata dictionary containing torrent information (name, mediainfo, screenshots, etc.).
            disctype: Type of disc (e.g., 'BD', 'DVD').

        Returns:
            True if upload was successful, False otherwise.
        """
        common = Common(config=self.config)
        await common.create_torrent_for_upload(meta, self.tracker, self.source_flag)
        await DescriptionBuilder(self.tracker, self.config).general_description_generator(
            meta,
            mediainfo=False,
            nfo=False,
            signature=self.forum_link,
        )
        if meta.bdinfo:
            mi_dump = None
            async with aiofiles.open(f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/BD_SUMMARY_00.txt", encoding="utf-8") as f:
                bd_dump = await f.read()
        else:
            async with aiofiles.open(f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/MEDIAINFO.txt", encoding="utf-8") as f:
                mi_dump = await f.read()
            bd_dump = None

        screenshots = [image["raw_url"] for image in meta.image_list if image["raw_url"] is not None]

        imdb_url_value = meta.imdb_info.get("imdb_url", "")
        imdb_url = str(imdb_url_value) if imdb_url_value else ""
        json_data: dict[str, Any] = {
            "name": await self.get_name(meta),
            # description does not work for some reason
            "description": "",
            # editing mediainfo so that instead of 1 080p its 1,080p as site mediainfo parser wont work other wise.
            "mediaInfo": re.sub(r"(\d+)\s+(\d+)", r"\1,\2", mi_dump or "") if bd_dump is None else f"{bd_dump}",
            "nfo": "",
            "url": f"{imdb_url}/" if imdb_url else "",
            # auto pulled from IMDB
            "descr": "",
            "poster": meta.artwork_url,
            "type": "401" if meta.category == "MOVIE" else "402",
            "screenshots": screenshots,
            "isAnonymous": self.config["TRACKERS"][self.tracker]["anon"],
        }

        async with aiofiles.open(f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/[{self.tracker}].torrent", "rb") as binary_file:
            binary_file_data = await binary_file.read()
            base64_encoded_data = base64.b64encode(binary_file_data)
            base64_message = base64_encoded_data.decode("utf-8")
            json_data["file"] = base64_message

        headers: dict[str, Any] = {
            "accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": self.config["TRACKERS"][self.tracker]["api_key"].strip(),
        }

        if meta.debug is False:
            try:
                async with httpx.AsyncClient(timeout=40.0) as client:
                    response = await client.post(url=self.upload_url, json=json_data, headers=headers)

                    # Handle successful upload (201)
                    if response.status_code == 201:
                        try:
                            response_json = response.json()

                            # Check if there's an error in the response despite 201 status
                            if response_json.get("error", False):
                                error_msg = response_json.get("message", "Unknown error occurred")
                                meta.tracker_status[self.tracker]["status_message"] = f"Upload error: {error_msg}"
                                return False

                            meta.tracker_status[self.tracker]["status_message"] = response_json
                            t_id = response_json["torrent"]["id"]
                            meta.tracker_status[self.tracker]["torrent_id"] = t_id
                            await common.create_torrent_ready_to_seed(
                                meta, self.tracker, self.source_flag, self.config["TRACKERS"][self.tracker].get("announce_url"), f"{self.base_url}/browse/t/" + str(t_id)
                            )
                            return True
                        except KeyError as e:
                            meta.tracker_status[self.tracker]["status_message"] = f"Error parsing response: {response.text}: missing key {e}"
                            return False

                    # Handle error responses
                    elif response.status_code == 400:
                        response_json = response.json()
                        error_msg = response_json.get("message", "Bad request or torrent file")
                        meta.tracker_status[self.tracker]["status_message"] = f"Bad request: {error_msg}"
                        return False

                    elif response.status_code == 403:
                        response_json = response.json()
                        error_msg = response_json.get("message", "You are not allowed to upload")
                        meta.tracker_status[self.tracker]["status_message"] = f"Permission denied: {error_msg}"
                        return False

                    elif response.status_code == 409:
                        response_json = response.json()
                        error_msg = response_json.get("message", "Torrent already exists")
                        meta.tracker_status[self.tracker]["status_message"] = f"Duplicate: {error_msg}"
                        return False

                    elif response.status_code == 413:
                        response_json = response.json()
                        error_msg = response_json.get("message", "Torrent file is too big or has too many files")
                        meta.tracker_status[self.tracker]["status_message"] = f"File size error: {error_msg}"
                        return False

                    elif response.status_code == 422:
                        response_json = response.json()
                        error_msg = response_json.get("message", "Upload rejected based on rules")
                        meta.tracker_status[self.tracker]["status_message"] = f"Upload rejected: {error_msg}"
                        return False

                    else:
                        # Handle any other status codes
                        try:
                            response_json = response.json()
                            error_msg = response_json.get("message", f"HTTP {response.status_code}")
                        except Exception:
                            error_msg = f"HTTP {response.status_code}: {response.text[:200]}"

                        logger.info(f"{self.tracker}: [bold red]Unexpected response: {error_msg}")
                        meta.tracker_status[self.tracker]["status_message"] = f"Unexpected response: {error_msg}"
                        return False

            except httpx.TimeoutException:
                meta.tracker_status[self.tracker]["status_message"] = "data error: RETROFLIX request timed out while uploading."
                return False
            except httpx.RequestError as e:
                meta.tracker_status[self.tracker]["status_message"] = f"data error: An error occurred while making the request: {e}"
                return False
            except Exception as e:
                meta.tracker_status[self.tracker]["status_message"] = f"data error - Unexpected error: {e}"
                return False

        else:
            logger.info(f"{self.tracker}: Request Data:")
            debug_data = json_data.copy()
            if debug_data.get("file"):
                debug_data["file"] = f"{str(debug_data['file'])[:10]}..."
            logger.info(Redaction.redact_private_info(debug_data))
            meta.tracker_status[self.tracker]["status_message"] = "Debug mode enabled, not uploading."
            await common.create_torrent_for_upload(meta, f"{self.tracker}" + "_DEBUG", f"{self.tracker}" + "_DEBUG", announce_url="https://fake.tracker")
            return True  # Debug mode - simulated success

    async def get_additional_checks(self, meta: Meta) -> bool:
        common = Common(config=self.config)
        if not common.check_and_confirm_adult_media_upload(meta, self.tracker):
            return False

        year_value = meta.year
        year = (year_value) if (isinstance(year_value, int) or (isinstance(year_value, str) and year_value.isdigit())) else None
        # Collect all possible years from different sources
        years: list[int] = []

        # IMDB end year
        imdb_end_year = meta.imdb_info.get("end_year")
        if imdb_end_year and str(imdb_end_year).isdigit():
            years.append(int(imdb_end_year))

        # TVDB episode year
        tvdb_episode_year = meta.tvdb_episode_year
        if tvdb_episode_year and tvdb_episode_year.isdigit():
            years.append(int(tvdb_episode_year))

        # Get most recent aired date from all TVDB episodes
        most_recent_aired_date = None
        tvdb_episodes_value = meta.tvdb_episode_data.get("episodes", [])
        tvdb_episodes = cast(list[dict[str, Any]], tvdb_episodes_value) if isinstance(tvdb_episodes_value, list) else []
        if tvdb_episodes:
            for episode in tvdb_episodes:
                aired_date = str(episode.get("aired", ""))
                if aired_date and "-" in aired_date:
                    try:
                        episode_date = datetime.datetime.strptime(aired_date, "%Y-%m-%d").replace(tzinfo=datetime.UTC).date()
                        if most_recent_aired_date is None or episode_date > most_recent_aired_date:
                            most_recent_aired_date = episode_date
                    except ValueError, AttributeError:
                        try:
                            episode_year_value = aired_date.split("-")[0]
                            if episode_year_value.isdigit():
                                years.append(int(episode_year_value))
                        except ValueError, AttributeError:
                            continue

        # Add the year from most recent aired date if found
        if most_recent_aired_date:
            years.append(most_recent_aired_date.year)

        # Use the most recent year found, fallback to meta year
        most_recent_year = max(years) if years else year

        # Update year with the most recent year for TV shows
        if meta.category == "TV":
            year = most_recent_year

        # Check if content is at least 10 years old using actual date comparison
        if meta.category == "MOVIE" and meta.release_date:
            try:
                release_date = datetime.datetime.strptime(meta.release_date, "%Y-%m-%d").replace(tzinfo=datetime.UTC).date()
                year = release_date.year
                # Calculate date exactly 10 years ago from today
                ten_years_ago = datetime.datetime.now(datetime.UTC).date() - datetime.timedelta(days=365 * 10 + 3)  # add leeway
                if release_date > ten_years_ago:
                    if not meta.unattended:
                        logger.info(f"{self.tracker}: [red]Content must be older than 10 Years to upload at RETROFLIX")
                    return False
            except ValueError, AttributeError:
                # If date parsing fails, fall back to year comparison
                release_year = meta.release_date.split("-")[0]
                if release_year.isdigit():
                    year = int(release_year)
                    if datetime.datetime.now(datetime.UTC).date().year - year <= 9:
                        if not meta.unattended:
                            logger.info(f"{self.tracker}: [red]Content must be older than 10 Years to upload at RETROFLIX")
                        return False

        elif meta.category == "TV" and most_recent_aired_date:
            # For TV shows, use the most recent aired date for comparison if available
            ten_years_ago = datetime.datetime.now(datetime.UTC).date() - datetime.timedelta(days=365 * 10 + 3)  # add leeway
            if most_recent_aired_date > ten_years_ago:
                if not meta.unattended:
                    logger.info(f"{self.tracker}: [red]Content must be older than 10 Years to upload at RETROFLIX")
                return False

        else:
            if year is not None and datetime.datetime.now(datetime.UTC).date().year - year <= 9:
                if not meta.unattended:
                    logger.info(f"{self.tracker}: [red]Content must be older than 10 Years to upload at RETROFLIX")
                return False
        return True

    async def search_existing(self, meta: Meta) -> list[dict[str, Any]]:
        """Search for existing torrents on RETROFLIX tracker.

        Searches for duplicate torrents using IMDB ID or title.

        Args:
            meta: Metadata dictionary containing torrent information.

        Returns:
            List of dictionaries containing information about existing torrents (dupes).
            Returns empty list if search fails.
        """
        dupes: list[dict[str, Any]] = []
        headers: dict[str, Any] = {
            "accept": "application/json",
            "Authorization": self.config["TRACKERS"][self.tracker]["api_key"].strip(),
        }
        params = {"includingDead": "1"}

        imdb_id_value = meta.imdb_id or 0
        if imdb_id_value != 0:
            imdb_id_str = str(meta.imdb_id)
            params["imdbId"] = imdb_id_str if imdb_id_str.startswith("tt") else "tt" + imdb_id_str
        else:
            params["search"] = meta.title.replace(":", "").replace("'", "").replace(",", "")

        def build_download_url(entry: dict[str, Any]) -> str:
            torrent_id = entry.get("id")
            torrent_url = str(entry.get("url", ""))
            if not torrent_id:
                match = re.search(r"/browse/t/(\d+)", torrent_url)
                if match:
                    torrent_id = match.group(1)

            if torrent_id:
                return f"{self.base_url}/api/torrent/{torrent_id}/download"

            return torrent_url

        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(self.search_url, params=params, headers=headers)
            response.raise_for_status()
            data = cast(list[dict[str, Any]], response.json())
            for each in data:
                download_url = build_download_url(each)
                result: dict[str, Any] = {
                    "name": str(each.get("name", "")),
                    "size": each.get("size", 0),
                    "files": str(each.get("name", "")),
                    "link": str(each.get("url", "")),
                    "download": download_url,
                }
                dupes.append(result)

        return dupes

    async def api_test(self, meta: Meta) -> bool | None:
        """Test if the stored API key is valid.

        RETROFLIX API keys expire weekly, so this method validates the current key
        and generates a new one if needed.

        Args:
            meta: Metadata dictionary containing base directory path.

        Returns:
            True if API key is valid, None if key generation was attempted.
        """
        headers: dict[str, Any] = {
            "accept": "application/json",
            "Authorization": self.config["TRACKERS"][self.tracker]["api_key"].strip(),
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.base_url}/api/test", headers=headers)

                if response.status_code != 200:
                    logger.info(f"{self.tracker}: [bold red]Your API key is incorrect SO generating a new one")
                    await self.generate_new_api(meta)
                    return None
                return True
        except httpx.RequestError as e:
            logger.info(f"{self.tracker}: [bold red]Error testing API: {e!s}")
            await self.generate_new_api(meta)
            return None
        except Exception as e:
            logger.error(f"{self.tracker}: [bold red]Unexpected error testing API: {e!s}")
            await self.generate_new_api(meta)
            return None

    async def generate_new_api(self, meta: Meta) -> bool | None:
        """Generate a new API key for RETROFLIX tracker.

        Authenticates using username/password and retrieves a new API token,
        then updates both the in-memory config and the config file on disk.

        Args:
            meta: Metadata dictionary containing base directory path for config file location.

        Returns:
            True if new API key was successfully generated and saved, None otherwise.
        """
        headers = {
            "accept": "application/json",
        }

        json_data = {
            "username": self.config["TRACKERS"][self.tracker]["username"],
            "password": self.config["TRACKERS"][self.tracker]["password"],
        }

        base_dir = meta.base_dir if meta.base_dir is not None else "."
        config_path = f"{base_dir}/data/config.py"

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(f"{self.base_url}/api/login", headers=headers, json=json_data)

            if response.status_code == 201:
                token = response.json().get("token")
                if token:
                    try:
                        # Update the in-memory config dictionary
                        self.config["TRACKERS"][self.tracker]["api_key"] = token

                        # Now we update the config file on disk using utf-8 encoding
                        async with aiofiles.open(config_path, encoding="utf-8") as file:
                            config_data = await file.read()

                        # Find the RETROFLIX tracker and replace the api_key value (supports single/double quotes and multiline blocks)
                        pattern = r"(['\"]RETROFLIX['\"]\s*:\s*{.*?['\"]api_key['\"]\s*:\s*)(['\"])[^'\"]*(['\"])"
                        new_config_data, replacements = re.subn(
                            pattern,
                            rf"\1\2{token}\3",
                            config_data,
                            count=1,
                            flags=re.DOTALL,
                        )
                        if replacements == 0:
                            logger.info(f"{self.tracker}: [bold red]Failed to update RETROFLIX api_key in config file.")
                            return None

                        # Write the updated config back to the file
                        async with aiofiles.open(config_path, "w", encoding="utf-8") as file:
                            await file.write(new_config_data)

                        logger.info(f"{self.tracker}: [bold green]API Key successfully saved to {config_path}")
                        return True
                    except Exception as e:
                        logger.info(f"{self.tracker}: [bold red]Failed to update config file: {e!s}")
                        return None
                else:
                    logger.info(f"{self.tracker}: [bold red]API response does not contain a token.")
                    return None
            else:
                logger.info(f"{self.tracker}: [bold red]Error getting new API key: {response.status_code}, please check username and password in the config.")
                return None

        except httpx.RequestError as e:
            logger.info(f"{self.tracker}: [bold red]An error occurred while requesting the API: {e!s}")
            return None

        except Exception as e:
            logger.info(f"{self.tracker}: [bold red]An unexpected error occurred: {e!s}")
            return None

    async def get_name(self, meta: Meta) -> str:
        return meta.name
