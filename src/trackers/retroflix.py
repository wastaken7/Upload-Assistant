# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import base64
import datetime
import re
from typing import Any, cast

import aiofiles
import httpx

from src import payload_preview
from src.cogs.redaction import Redaction
from src.console import logger
from src.get_desc import DescriptionBuilder
from src.meta import Meta
from src.trackers.common import Common


def bearer_authorization(token: object) -> str:
    """The Authorization value for an API token, accepting one saved with or without "Bearer "."""
    value = str(token or "").strip()
    if not value or value.lower().startswith("bearer "):
        return value
    return f"Bearer {value}"


class RetroFlix:
    """
    RTF Private Torrent Tracker
    """

    base_url = "https://retroflix.club"

    auth_type = "other_api"
    optional_setup_keys = frozenset({"username", "password"})
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

    def _headers(self) -> dict[str, str]:
        """Headers for API calls, with the token sent the way the API documents it (Bearer)."""
        return {"accept": "application/json", "Authorization": bearer_authorization(self.config["TRACKERS"][self.tracker].get("api_key", ""))}

    async def get_data(self, meta: Meta, preview: bool = False) -> dict[str, Any]:
        """Build the upload form; a ``preview`` leaves out the description, MediaInfo/BDInfo and screenshots."""
        mi_dump = bd_dump = None
        description = ""
        if not preview:
            # The site shows the screenshots field in its own section, so they stay out of the description.
            description = await DescriptionBuilder(self.tracker, self.config).general_description_generator(
                meta,
                mediainfo=False,
                nfo=False,
                screenshots=False,
                signature=self.forum_link,
            )
            if meta.bdinfo:
                async with aiofiles.open(f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/BD_SUMMARY_00.txt", encoding="utf-8") as f:
                    bd_dump = await f.read()
            else:
                async with aiofiles.open(f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/MEDIAINFO.txt", encoding="utf-8") as f:
                    mi_dump = await f.read()

        screenshots = [] if preview else [image["raw_url"] for image in meta.image_list if image["raw_url"] is not None]

        imdb_url_value = meta.imdb_info.get("imdb_url", "")
        imdb_url = str(imdb_url_value) if imdb_url_value else ""
        json_data: dict[str, Any] = {
            "name": await self.get_name(meta),
            # Short description, typically a genre list; the site fills it from IMDb.
            "description": "",
            # editing mediainfo so that instead of 1 080p its 1,080p as site mediainfo parser wont work other wise.
            "mediaInfo": re.sub(r"(\d+)\s+(\d+)", r"\1,\2", mi_dump or "") if bd_dump is None else f"{bd_dump}",
            "nfo": "",
            "url": f"{imdb_url}/" if imdb_url else "",
            # Long description (BBCode), shown under "Description"; the IMDb plot is shown separately.
            "descr": description,
            "poster": meta.artwork_url,
            "type": "401" if meta.category == "MOVIE" else "402",
            "screenshots": screenshots,
            "isAnonymous": self.config["TRACKERS"][self.tracker]["anon"],
        }
        return json_data

    async def get_payload_preview(self, meta: Meta) -> payload_preview.TrackerPreview:
        """The upload form as it is known before screenshots, for the Web UI to show and edit."""
        specs = {
            "name": payload_preview.text("Name"),
            "description": payload_preview.readonly("Description"),
            "nfo": payload_preview.readonly("NFO"),
            "url": payload_preview.text("IMDb URL"),
            "poster": payload_preview.text("Poster URL", max_length=1000),
            "type": payload_preview.choice("Category", {"MOVIE": "401", "TV": "402"}, by_label=True),
            "isAnonymous": payload_preview.flag("Anonymous", on=True, off=False),
        }
        deferred = {
            "descr": payload_preview.DESCRIPTION_NOTE,
            "mediaInfo": "Read from the MediaInfo/BDInfo report at upload time",
            "screenshots": "Uploaded after this question",
        }
        return payload_preview.describe(self.tracker, await self.get_data(meta, preview=True), specs, deferred=deferred)

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
        json_data = payload_preview.apply_payload_edits(meta, self.tracker, await self.get_data(meta))

        async with aiofiles.open(f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/[{self.tracker}].torrent", "rb") as binary_file:
            binary_file_data = await binary_file.read()
            base64_encoded_data = base64.b64encode(binary_file_data)
            base64_message = base64_encoded_data.decode("utf-8")
            json_data["file"] = base64_message

        headers = {**self._headers(), "Content-Type": "application/json"}

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
        if not await common.check_adult_media_allowed(meta, self.tracker):
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
                    logger.info(f"{self.tracker}: [red]Content must be older than 10 Years to upload at RETROFLIX")
                    return False
            except ValueError, AttributeError:
                # If date parsing fails, fall back to year comparison
                release_year = meta.release_date.split("-")[0]
                if release_year.isdigit():
                    year = int(release_year)
                    if datetime.datetime.now(datetime.UTC).date().year - year <= 9:
                        logger.info(f"{self.tracker}: [red]Content must be older than 10 Years to upload at RETROFLIX")
                        return False

        elif meta.category == "TV" and most_recent_aired_date:
            # For TV shows, use the most recent aired date for comparison if available
            ten_years_ago = datetime.datetime.now(datetime.UTC).date() - datetime.timedelta(days=365 * 10 + 3)  # add leeway
            if most_recent_aired_date > ten_years_ago:
                logger.info(f"{self.tracker}: [red]Content must be older than 10 Years to upload at RETROFLIX")
                return False

        else:
            if year is not None and datetime.datetime.now(datetime.UTC).date().year - year <= 9:
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
        headers = self._headers()
        params = {"includingDead": "included"}

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

    async def api_test(self, meta: Meta) -> bool:  # noqa: ARG002 - called with meta by upload.py
        """Check the API token, logging in again when there is none or the site rejects it.

        RetroFlix tokens expire, so a rejected token is replaced by logging in with the
        configured username and password. The new token is kept in memory for this run only.
        """
        if str(self.config["TRACKERS"][self.tracker].get("api_key", "")).strip():
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(f"{self.base_url}/api/test", headers=self._headers())
            except httpx.RequestError as e:
                logger.info(f"{self.tracker}: [bold red]Could not reach the API: {e!s}")
                return False
            if response.status_code == 200:
                return True
            if response.status_code not in (401, 403):
                logger.info(f"{self.tracker}: [bold red]Unexpected response while testing the API token: HTTP {response.status_code}")
                return False
            logger.info(f"{self.tracker}: [yellow]The API token was rejected, logging in for a new one")
        return await self.generate_new_api()

    async def generate_new_api(self) -> bool:
        """Log in with the configured username and password and keep the new token in memory."""
        tracker_config = self.config["TRACKERS"][self.tracker]
        username = str(tracker_config.get("username", "")).strip()
        password = str(tracker_config.get("password", ""))
        if not username or not password:
            logger.info(f"{self.tracker}: [bold red]No valid API token and no username/password to get one; add them to the config.")
            return False

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.post(f"{self.base_url}/api/login", headers={"accept": "application/json"}, json={"username": username, "password": password})
        except httpx.RequestError as e:
            logger.info(f"{self.tracker}: [bold red]An error occurred while logging in: {e!s}")
            return False

        if response.status_code != 201:
            try:
                message = str(response.json().get("message", ""))
            except ValueError:
                message = ""
            logger.info(f"{self.tracker}: [bold red]Login failed (HTTP {response.status_code}){': ' + message if message else ''}")
            return False

        try:
            token = str(response.json().get("token") or "")
        except ValueError:
            token = ""
        if not token:
            logger.info(f"{self.tracker}: [bold red]The login response did not contain a token.")
            return False

        # Shared with the rest of this run (cross-seeding reads it too); the config file is left untouched.
        tracker_config["api_key"] = token
        logger.info(f"{self.tracker}: [green]Logged in and got a new API token for this run.")
        return True

    async def get_name(self, meta: Meta) -> str:
        return meta.name
