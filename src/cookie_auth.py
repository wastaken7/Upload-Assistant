# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import http.cookiejar
import json
import re
import stat
import traceback
from pathlib import Path
from typing import Any, cast

import aiofiles
import httpx
from bs4 import BeautifulSoup
from bs4.element import AttributeValueList

from src.console import logger
from src.meta import Meta
from src.trackers.common import Common


def _attr_to_string(value: str | AttributeValueList | None) -> str:
    """Convert BeautifulSoup attribute values to a plain string."""
    if isinstance(value, str):
        return value
    if isinstance(value, AttributeValueList):
        return " ".join(value)
    return ""


def extract_upload_error(html: str) -> str:
    """Extract the useful error message from common tracker upload pages."""
    soup = BeautifulSoup(html, "html.parser")

    def clean(value: str) -> str:
        return " ".join(value.split()).strip(" :-")

    # Modern tracker themes usually put all upload errors in this notification.
    for element in soup.select(".notification-border-e .notification-body"):
        message = clean(element.get_text(" ", strip=True))
        if message:
            return message

    # Older themes mark the error heading, while the actual message is in its
    # next sibling or in the nearest small container.
    for element in soup.select("[class*='error']"):
        element_message = clean(element.get_text(" ", strip=True))
        if element_message and element_message.lower() not in {"error", "erro"}:
            return element_message
        for parent in [element, *element.parents]:
            message = clean(parent.get_text(" ", strip=True))
            if len(message) > len(element_message) and len(message) < 500:
                message = re.sub(r"^(?:erro|error)\b", "", message, flags=re.IGNORECASE)
                if message := clean(message):
                    return message

    for heading in soup.select("h1, h2, h3, h4"):
        if not re.search(r"error|failed", heading.get_text(" ", strip=True), re.IGNORECASE):
            continue
        sibling = heading.find_next_sibling(["p", "div"])
        message = clean(sibling.get_text(" ", strip=True)) if sibling else ""
        if message:
            return message

    # A few trackers only return their upload-blocking notice.
    for heading in soup.select("h1.dnu_header, h2.dnu_header, h3.dnu_header, #dnu_header"):
        message = clean(heading.get_text(" ", strip=True))
        if re.search(r"proib|permitid|not allowed|forbidden", message, re.IGNORECASE):
            return message

    # Some legacy pages render the complete error as one text node.
    for text_parent in soup.select("td, div, p, h1, h2, h3, h4, b, span, font"):
        raw_message = clean(text_parent.get_text(" ", strip=True))
        if not re.match(r"^(?:error\s*:|upload failed!)", raw_message, re.IGNORECASE):
            continue
        for parent in [text_parent, *text_parent.parents]:
            message = clean(parent.get_text(" ", strip=True))
            if len(message) > 500 or not re.match(r"^(?:error\s*:|upload failed!)", message, re.IGNORECASE):
                continue
            message = re.sub(r"^(?:error\s*:|upload failed!?)\s*", "", message, flags=re.IGNORECASE)
            message = re.sub(r"\s+Back$", "", message, flags=re.IGNORECASE)
            if message := clean(message):
                return message

    return ""


def get_tracker_domain(tracker: str, config: dict[str, Any] | None = None) -> str:
    """Extract or map a tracker name to its primary domain name."""
    try:
        from src.trackersetup import tracker_class_map

        cls = tracker_class_map.get(tracker.upper())
        if cls and hasattr(cls, "base_url") and isinstance(cls.base_url, str):
            from urllib.parse import urlparse

            netloc = urlparse(cls.base_url).netloc
            if netloc:
                domain = netloc.lower().lstrip(".")
                if domain.startswith("www."):
                    domain = domain[4:]
                return domain
    except Exception as e:
        logger.error(f"[yellow]Warning: Error getting tracker domain: {e}[/yellow]")

    if config:
        tracker_cfg = config.get("TRACKERS", {}).get(tracker, {})
        announce_url = tracker_cfg.get("announce_url", "")
        if announce_url:
            try:
                from urllib.parse import urlparse

                parsed_url = cast(Any, urlparse(announce_url))
                netloc = str(parsed_url.netloc)
                if netloc:
                    domain = netloc.lower().lstrip(".")
                    if domain.startswith("www."):
                        domain = domain[4:]
                    return domain
            except Exception as e:
                logger.error(f"[yellow]Warning: Error getting tracker domain: {e}[/yellow]")

    # Fallback/Hardcoded domains
    fallback_domains = {
        "amigosshare": "amigos-share.club",
        "avistaz": "avistaz.to",
        "bjshare": "bj-share.info",
        "brasiltracker": "brasiltracker.org",
        "cinemaz": "cinemaz.to",
        "greatposterwall": "greatposterwall.com",
        "hdbits": "hdbits.org",
        "hdspace": "hd-space.org",
        "hdtorrents": "hd-torrents.org",
        "iptorrents": "iptorrents.com",
        "immortalseed": "immortalseed.me",
        "lajidui": "lajidui.top",
        "longpt": "longpt.org",
        "privatehd": "privatehd.to",
        "ptcafe": "ptcafe.club",
        "ptfans": "ptfans.cc",
        "ptgtk": "gtkpw.xyz",
        "ptskit": "ptskit.org",
        "railgunpt": "bilibili.download",
        "torrentleech": "torrentleech.org",
        "filelist": "filelist.io",
        "passthepopcorn": "passthepopcorn.me",
        "pterclub": "pterclub.com",
    }

    t_lower = tracker.lower()
    if t_lower in fallback_domains:
        return fallback_domains[t_lower]

    return t_lower


def find_cookie_file(base_dir: str, tracker: str, config: dict[str, Any] | None = None) -> str:
    """
    Find the cookie file for a tracker.
    First checks if the tracker's config has a custom 'cookie_file' path.
    Then scans data/cookies/ for files:
    - First looks for files whose names contain the tracker name (case insensitive).
    - If not found, looks for text/json files whose contents contain the tracker's domain.
    - If still not found, falls back to the default 'data/cookies/{tracker}.txt' (or json/etc).
    """
    cookies_dir = Path(base_dir) / "data" / "cookies"
    if not cookies_dir.exists():
        cookies_dir.mkdir(parents=True, exist_ok=True)

    # 1. Check if tracker config has 'cookie_file' or 'cookies'
    tracker_config = cast(dict[str, Any], config.get("TRACKERS", {}).get(tracker, {})) if config else {}
    custom_cookie_file = tracker_config.get("cookie_file", "").strip() or tracker_config.get("cookies", "").strip()
    if custom_cookie_file:
        custom_path = Path(custom_cookie_file)
        if custom_path.is_absolute():
            return str(custom_path.resolve())
        if len(custom_path.parts) > 1 and custom_path.parts[0] == "data":
            return str((Path(base_dir) / custom_cookie_file).resolve())
        return str((cookies_dir / custom_cookie_file).resolve())

    matching_files: list[Path] = []

    # 2. Try to find by filename match in data/cookies/
    if cookies_dir.exists():
        files: list[Path] = sorted(cookies_dir.glob("*"), key=lambda p: p.name)

        # Check for exact name match (with any extension)
        matching_files.extend(file_path for file_path in files if file_path.is_file() and file_path.stem.lower() == tracker.lower())

        # Check for partial name match (e.g. "my_avistaz_cookies.txt")
        if not matching_files:
            matching_files.extend(file_path for file_path in files if file_path.is_file() and tracker.lower() in file_path.name.lower())

        # 3. Try to find by content/domain match
        if not matching_files:
            domain = get_tracker_domain(tracker, config)
            if domain:
                for file_path in files:
                    if not file_path.is_file():
                        continue
                    # Only search text/json files
                    if file_path.suffix.lower() in [".txt", ".json"]:
                        try:
                            with file_path.open("r", encoding="utf-8", errors="ignore") as f:
                                head = f.read(10240)
                                if domain in head.lower():
                                    matching_files.append(file_path)
                        except Exception as e:
                            logger.error(f"[yellow]Warning: Error reading cookie file: {e}[/yellow]")

    if matching_files:
        if len(matching_files) > 1:
            file_names = ", ".join(f.name for f in matching_files)
            logger.warning(f"[yellow]{tracker}: Found multiple cookie files ({file_names}). Using the first one by default: {matching_files[0].name}[/yellow]")
        return str(matching_files[0].resolve())

    # 4. Fallback to default
    if tracker == "FILELIST":
        return str((cookies_dir / "FILELIST.json").resolve())
    if tracker == "PASSTHEPOPCORN":
        return str((cookies_dir / f"{tracker}.json").resolve())
    if tracker == "Pterimg":
        return str((cookies_dir / "Pterimg.json").resolve())

    return str((cookies_dir / f"{tracker}.txt").resolve())


class CookieValidator:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.common = Common(config)

    async def load_session_cookies(self, meta: Meta, tracker: str) -> http.cookiejar.MozillaCookieJar | None:
        cookie_file = find_cookie_file(meta.base_dir, tracker, self.config)
        cookie_jar = http.cookiejar.MozillaCookieJar(cookie_file)

        try:
            cookie_jar.load(ignore_discard=True, ignore_expires=True)
        except http.cookiejar.LoadError as e:
            logger.info(f"{tracker}: Failed to load the cookie file: {e}")
            logger.info(f"{tracker}: Please ensure the cookie file is in the correct format (Netscape).")
            return None
        except FileNotFoundError:
            # Attempt automatic login for ALPHARATIO tracker
            if tracker == "ALPHARATIO":
                logger.info(f"{tracker}: [yellow]Cookie file not found. Attempting automatic login...[/yellow]")
                if await self.ar_login(meta, tracker, cookie_file):
                    # Try loading the newly created cookie file
                    try:
                        cookie_jar.load(ignore_discard=True, ignore_expires=True)
                        return cookie_jar
                    except Exception as e:
                        logger.info(f"{tracker}: Failed to load cookies after login: {e}")
                        return None
                else:
                    logger.info(f"{tracker}: Automatic login failed.")
                    return None

            logger.info(
                f"{tracker}: [red]Cookie file not found.[/red]\n"
                f"{tracker}: You must first log in through your usual browser and export the cookies to: [yellow]{cookie_file}[/yellow]\n"
                f'{tracker}: Cookies can be exported using browser extensions like "cookies.txt" (Firefox) or "Get cookies.txt LOCALLY" (Chrome).'
            )
            return None

        return cookie_jar

    async def save_session_cookies(self, tracker: str, cookie_jar: http.cookiejar.MozillaCookieJar | None) -> None:
        """Save updated cookies after a successful validation."""
        if not cookie_jar:
            logger.info(f"{tracker}: Cookie jar not initialized, cannot save cookies.")
            return

        try:
            cookie_jar.save(ignore_discard=True, ignore_expires=True)
        except Exception as e:
            logger.info(f"{tracker}: Failed to update the cookie file: {e}")

    async def get_ar_auth_key(self, meta: Meta, tracker: str) -> str | None:
        """Retrieve the saved auth key for ALPHARATIO tracker."""
        cookie_file = find_cookie_file(meta.base_dir, tracker, self.config)
        auth_file = cookie_file.replace(".txt", "_auth.txt")

        if Path(auth_file).exists():
            try:
                async with aiofiles.open(auth_file, encoding="utf-8") as f:
                    auth_key = await f.read()
                    auth_key = auth_key.strip()
                    if auth_key:
                        return auth_key
            except Exception as e:
                logger.info(f"{tracker}: Error reading auth key: {e}")

        return None

    async def ar_login(self, meta: Meta, tracker: str, cookie_file: str) -> bool:
        """Perform automatic login to ALPHARATIO and save cookies in Netscape format."""
        username = self.config["TRACKERS"][tracker].get("username", "").strip()
        password = self.config["TRACKERS"][tracker].get("password", "").strip()

        if not username or not password:
            logger.info(f"{tracker}: Username or password not configured in config.")
            return False

        base_url = "https://alpharatio.cc"
        login_url = f"{base_url}/login.php"

        headers = {"User-Agent": f"{meta.ua_name} {(meta.current_version if meta.current_version is not None else 'github.com/wastaken7/Upload-Assistant')}"}

        try:
            async with httpx.AsyncClient(headers=headers, timeout=30.0, follow_redirects=True) as client:
                # Perform login
                login_data: dict[str, str] = {
                    "username": username,
                    "password": password,
                    "keeplogged": "1",
                    "login": "Login",
                }

                response = await client.post(login_url, data=login_data)

                if response.status_code != 200:
                    logger.info(f"{tracker}: Login failed with status code {response.status_code}")
                    return False

                # Check for login success by looking for error indicators
                if "login.php?act=recover" in response.text or "Forgot your password" in response.text:
                    logger.info(f"{tracker}: [red]Login failed. Please check your username and password.[/red]")
                    if meta.debug:
                        failure_path = await self.common.save_html_file(meta, tracker, response.text, "Failed_Login")
                        logger.debug(f"{tracker}: Login response saved to [yellow]{failure_path}[/yellow] for debugging.")
                    return False

                # Validate we're logged in by checking the torrents page
                test_response = await client.get(f"{base_url}/torrents.php")
                if test_response.status_code == 200 and "login.php?act=recover" not in test_response.text:
                    logger.info(f"{tracker}: [green]Login successful![/green]")

                    # Extract auth key from the response page
                    auth_key = None
                    soup = BeautifulSoup(test_response.text, "html.parser")
                    logout_link = soup.find("a", href=True, text="Logout")
                    if logout_link:
                        href = _attr_to_string(logout_link.get("href"))
                        auth_match = re.search(r"auth=([^&]+)", href)
                        if auth_match:
                            auth_key = auth_match.group(1)
                            logger.info(f"{tracker}: [green]Auth key extracted successfully[/green]")

                    # Save cookies in Netscape format
                    Path(cookie_file).parent.mkdir(parents=True, exist_ok=True)
                    cookie_jar = http.cookiejar.MozillaCookieJar(cookie_file)

                    # Convert httpx cookies to MozillaCookieJar format
                    for cookie_name in client.cookies:
                        # Get the cookie object for additional attributes
                        for cookie in client.cookies.jar:
                            if cookie.name == cookie_name:
                                rest = getattr(cookie, "_rest", {})
                                rest_map = cast(dict[str, Any], rest) if isinstance(rest, dict) else {}
                                ck = http.cookiejar.Cookie(
                                    version=0,
                                    name=cookie.name,
                                    value=cookie.value,
                                    port=None,
                                    port_specified=False,
                                    domain=cookie.domain if cookie.domain else ".alpharatio.cc",
                                    domain_specified=True,
                                    domain_initial_dot=(cookie.domain or ".alpharatio.cc").startswith("."),
                                    path=cookie.path if cookie.path else "/",
                                    path_specified=True,
                                    secure=bool(rest_map.get("secure")) if rest_map else True,
                                    expires=None,
                                    discard=False,
                                    comment=None,
                                    comment_url=None,
                                    rest={},
                                    rfc2109=False,
                                )
                                cookie_jar.set_cookie(ck)
                                break

                    cookie_jar.save(ignore_discard=True, ignore_expires=True)
                    logger.info(f"{tracker}: [green]Cookies saved to {cookie_file}[/green]")

                    # Save auth key to a separate file if found
                    if auth_key:
                        auth_file = cookie_file.replace(".txt", "_auth.txt")
                        async with aiofiles.open(auth_file, "w", encoding="utf-8") as f:
                            await f.write(auth_key)
                        logger.info(f"{tracker}: [green]Auth key saved to {auth_file}[/green]")

                    return True

                logger.info(f"{tracker}: [red]Login validation failed.[/red]")
                return False

        except httpx.TimeoutException:
            logger.info(f"{tracker}: Connection timed out. The site may be down or unreachable.")
            return False
        except httpx.ConnectError:
            logger.info(f"{tracker}: Failed to connect. The site may be down or your connection is blocked.")
            return False
        except Exception as e:
            logger.info(f"{tracker}: Login error: {e}")
            logger.debug(traceback.format_exc())
            return False

    async def cookie_validation(
        self,
        meta: Meta,
        tracker: str,
        test_url: str = "",
        status_code: str = "",
        error_text: str = "",
        success_text: str = "",
        token_pattern: str = "",
    ) -> bool:
        """
        Validate login cookies for a tracker by checking specific indicators on a test page.
        Return False to skip the upload if credentials are invalid.
        """
        cookie_jar = await self.load_session_cookies(meta, tracker)
        if not cookie_jar:
            return False

        headers = {"User-Agent": f"{meta.ua_name} {(meta.current_version if meta.current_version is not None else 'github.com/wastaken7/Upload-Assistant')}"}

        try:
            async with httpx.AsyncClient(headers=headers, timeout=20.0, cookies=cookie_jar) as session:
                response = await session.get(test_url)
                text = response.text
                # if meta.debug:
                #    console.print(text)

                # Check for key indicators of successful login
                # This is the most precise method if you can find a unique string that only appears when logged in
                if success_text and success_text not in text:
                    await self.handle_validation_failure(meta, tracker, text)
                    return False

                # Check for key indicators of failed login
                # For example, “Forgot your password” <- this indicates that you are on the login page
                if error_text and error_text in text:
                    await self.handle_validation_failure(meta, tracker, text)
                    return False

                # Check for status code
                # This is often not very accurate, as websites may use the same status code for successful uploads and failures
                if status_code and response.status_code != int(status_code):
                    await self.handle_validation_failure(meta, tracker, text)
                    return False

                # Find the auth token if it is needed
                if token_pattern:
                    match = re.search(token_pattern, text)
                    if not match:
                        await self.handle_validation_failure(meta, tracker, text)
                        return False
                    # Dynamically set a class attribute to store the token
                    from src.trackersetup import tracker_class_map

                    cls = tracker_class_map.get(tracker.upper())
                    if cls:
                        cls.secret_token = str(match.group(1))

                # Save cookies only after a confirmed valid login
                await self.save_session_cookies(tracker, cookie_jar)
                return True

        except httpx.ConnectTimeout:
            logger.info(f"{tracker}: Connection timeout. Server took too long to respond.")
        except httpx.ReadTimeout:
            logger.info(f"{tracker}: Read timeout. Data transfer stopped prematurely.")
        except httpx.ConnectError:
            logger.info(f"{tracker}: Connection failed. Check URL, port, and network status.")
        except httpx.ProxyError:
            logger.info(f"{tracker}: Proxy error. Failed to connect via proxy.")
        except httpx.DecodingError:
            logger.info(f"{tracker}: Decoding failed. Response content is not valid (e.g., unexpected encoding).")
        except httpx.TooManyRedirects:
            logger.info(f"{tracker}: Too many redirects. Request exceeded the maximum redirect limit.")
        except httpx.HTTPStatusError as e:
            status_code = str(e.response.status_code)
            reason = e.response.reason_phrase if e.response.reason_phrase else "Unknown Reason"
            url = e.request.url
            logger.info(f"{tracker}: HTTP status error {status_code}: {reason} for {url}")
        except httpx.RequestError as e:
            logger.info(f"{tracker}: General request error: {e}")
        except Exception as e:
            logger.info(f"{tracker}: Unexpected validation error: {e}")

        return False

    async def handle_validation_failure(self, meta: Meta, tracker: str, text: str) -> None:
        logger.info(
            f"{tracker}: Validation failed. The cookie appears to be expired or invalid.\n{tracker}: Please log in through your usual browser and export the cookies again."
        )
        failure_path = await self.common.save_html_file(meta, tracker, text, "Failed_Login")
        logger.info(
            f"The web page has been saved to {failure_path} for analysis.\n"
            "Do not share this file publicly, as it may contain confidential information such as passkeys, IP address, e-mail, etc.\n"
            "You can open this file in a web browser to see what went wrong.\n"
        )

        return

    async def find_html_token(self, tracker: str, token_pattern: str, response: str) -> str | None:
        """Find the auth token in a web page using a regular expression pattern."""
        auth_match = re.search(token_pattern, response)
        if not auth_match:
            logger.info(
                f"{tracker}: The required token could not be found in the page's HTML. Pattern used: {token_pattern}\n"
                f"{tracker}: This can happen if the site HTML has changed or if the login failed silently."
            )
            return None
        return str(auth_match.group(1))

    def _save_cookies_secure(self, session_cookies: Any, cookiefile: str) -> None:
        """Securely save session cookies using JSON instead of pickle"""
        try:
            # Convert RequestsCookieJar to dictionary for JSON serialization
            cookie_dict = {}
            for cookie in session_cookies:
                cookie_dict[cookie.name] = {"value": cookie.value, "domain": cookie.domain, "path": cookie.path, "secure": cookie.secure, "expires": cookie.expires}

            with Path(cookiefile).open("w", encoding="utf-8") as f:
                json.dump(cookie_dict, f, indent=2)

            # Set restrictive permissions (0o600) to protect cookie secrets
            Path(cookiefile).chmod(stat.S_IRUSR | stat.S_IWUSR)

        except OSError as e:
            logger.error(f"[red]Error with cookie file operations: {e}[/red]")
            raise
        except (TypeError, ValueError) as e:
            logger.error(f"[red]Error encoding cookies to JSON: {e}[/red]")
            raise

    def _load_cookies_secure(self, session: Any, cookiefile: str, _tracker: str) -> None:
        """Securely load session cookies from JSON instead of pickle"""

        # Load cookies from JSON file only. Legacy pickle migration is intentionally not automatic
        # to avoid executing untrusted pickle payloads during normal startup.
        try:
            with Path(cookiefile).open(encoding="utf-8") as f:
                cookie_dict = json.load(f)

            # Convert dictionary back to session cookies
            for name, cookie_data in cookie_dict.items():
                # Prevent None domain values
                domain = cookie_data.get("domain")
                if domain is None:
                    domain = ""  # Use empty string instead of None

                session.cookies.set(name=name, value=cookie_data["value"], domain=domain, path=cookie_data.get("path", "/"), secure=cookie_data.get("secure", False))

        except OSError as e:
            logger.error(f"[red]Error reading cookie file: {e}[/red]")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"[red]Error decoding JSON from cookie file: {e}[/red]")
            raise

    def _load_cookies_dict_secure(self, cookiefile: str) -> dict[str, Any]:
        """Securely load cookies as dictionary from JSON instead of pickle"""
        try:
            with Path(cookiefile).open(encoding="utf-8") as f:
                cookie_dict = json.load(f)
            return cast(dict[str, Any], cookie_dict)
        except OSError as e:
            logger.error(f"[red]Error reading cookie file: {e}[/red]")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"[red]Error decoding JSON from cookie file: {e}[/red]")
            raise


class CookieAuthUploader:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.common = Common(config)

    async def handle_upload(
        self,
        meta: Meta,
        tracker: str,
        source_flag: str,
        torrent_url: str,
        data: dict[str, Any],
        torrent_field_name: str,
        upload_cookies: Any,
        upload_url: str,
        default_announce: str = "",
        torrent_name: str = "",
        id_pattern: str = "",
        success_status_code: str = "",
        error_text: str = "",
        success_text: str = "",
        success_list: list[str] | None = None,
        additional_files: dict[str, Any] | None = None,
        hash_is_id: bool = False,
    ) -> bool:
        """
        Upload a torrent to a tracker using cookies for authentication.
        Return True if the upload is successful, False otherwise.

        1.  Create the [tracker].torrent file and set the source flag.
            Uses default_announce if provided as some trackers require it.

        2.  Load the torrent file into memory.
        3.  Post the torrent file and form data to the provided upload URL using the provided cookies.
        4.  Check the response for success indicators.
        5.  Handle success or failure accordingly.

        A successful upload will create a torrent entry with the announce URL and torrent ID (if applicable).
        A failed upload will save the response HTML for analysis and also create a torrent entry with the announce URL,
        as the upload may have partially succeeded.
        """
        values: list[str | list[str] | None] = [success_status_code, error_text, success_text, success_list]
        count = sum(bool(v) for v in values)

        if count == 0 or count > 1:
            if count == 0:
                error = "You must provide at least one of: success_status_code, error_text, success_text, or success_list."
            else:
                error = "Only one of success_status_code, error_text, success_text, or success_list should be provided."
            meta.tracker_status[tracker]["status_message"] = error
            return False

        user_announce_url = self.config["TRACKERS"][tracker]["announce_url"]

        files = await self.load_torrent_file(
            meta,
            tracker,
            torrent_field_name,
            torrent_name,
            source_flag,
            default_announce,
        )
        if additional_files:
            files.update(additional_files)

        headers = {"User-Agent": f"{meta.ua_name} {(meta.current_version if meta.current_version is not None else 'github.com/wastaken7/Upload-Assistant')}"}

        if meta.debug:
            self.upload_debug(tracker, data)
            meta.tracker_status[tracker]["status_message"] = "Debug mode enabled, not uploading"
            await self.common.create_torrent_for_upload(meta, f"{tracker}" + "_DEBUG", f"{tracker}" + "_DEBUG", announce_url="https://fake.tracker")
            return True

        success = False
        try:
            async with httpx.AsyncClient(headers=headers, timeout=30.0, cookies=upload_cookies, follow_redirects=True) as session:
                response = await session.post(upload_url, data=data, files=files)

                if (success_text and success_text in response.text) or (success_list and any(item in response.text for item in success_list)):
                    success = True

                elif success_status_code:
                    valid_codes = {int(code.strip()) for code in success_status_code.split(",") if code.strip().isdigit()}

                    if response.status_code in valid_codes:
                        success = True

                elif error_text and error_text not in response.text:
                    success = True

                if success:
                    await self.handle_successful_upload(
                        meta,
                        tracker,
                        response,
                        id_pattern,
                        hash_is_id,
                        source_flag,
                        user_announce_url,
                        torrent_url,
                    )
                    return True
                await self.handle_failed_upload(
                    meta,
                    tracker,
                    success_status_code,
                    success_text,
                    error_text,
                    response,
                    success_list,
                )
                return False

        except httpx.ConnectTimeout:
            meta.tracker_status[tracker]["status_message"] = "Connection timed out"
        except httpx.ReadTimeout:
            meta.tracker_status[tracker]["status_message"] = "Read timed out"
        except httpx.ConnectError:
            meta.tracker_status[tracker]["status_message"] = "Failed to connect to the server"
        except httpx.ProxyError:
            meta.tracker_status[tracker]["status_message"] = "Proxy connection failed"
        except httpx.DecodingError:
            meta.tracker_status[tracker]["status_message"] = "Response decoding failed"
        except httpx.TooManyRedirects:
            meta.tracker_status[tracker]["status_message"] = "Too many redirects"
        except httpx.HTTPStatusError as e:
            meta.tracker_status[tracker]["status_message"] = f"HTTP error {e.response.status_code}: {e}"
        except httpx.RequestError as e:
            meta.tracker_status[tracker]["status_message"] = f"Request error: {e}"
        except Exception as e:
            meta.tracker_status[tracker]["status_message"] = f"Unexpected upload error: {e}"

        await self.common.create_torrent_ready_to_seed(meta, tracker, source_flag, user_announce_url, torrent_url)
        return False

    def upload_debug(self, tracker: str, data: Any) -> None:
        try:
            if isinstance(data, dict):
                data_dict = cast(dict[str, Any], data)
                sensitive_keywords = ["password", "passkey", "auth", "csrf", "token"]

                clean_dict = {k: ("[REDACTED]" if any(kw in k.lower() for kw in sensitive_keywords) else v) for k, v in data_dict.items()}
                logger.info(f"{tracker}: Form Data: {clean_dict}")
            else:
                logger.info(f"{tracker}: Form Data: {data}")
        except Exception as e:
            logger.info(f"Error displaying form data: {e}")
            raise

    async def load_torrent_file(
        self,
        meta: Meta,
        tracker: str,
        torrent_field_name: str,
        torrent_name: str,
        source_flag: str,
        default_announce: str,
    ) -> dict[str, tuple[str, bytes, str]]:
        """Load the torrent file into memory."""
        await self.common.create_torrent_for_upload(meta, tracker, source_flag, announce_url=default_announce)
        torrent_path = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/[{tracker}].torrent"
        async with aiofiles.open(torrent_path, "rb") as f:
            file_bytes = await f.read()

        name = torrent_name if torrent_name else f"{tracker}.{meta.infohash}.placeholder"

        return {
            torrent_field_name: (
                f"{name}.torrent",
                file_bytes,
                "application/x-bittorrent",
            )
        }

    async def handle_successful_upload(
        self,
        meta: Meta,
        tracker: str,
        response: httpx.Response,
        id_pattern: str,
        hash_is_id: bool,
        source_flag: str,
        user_announce_url: str,
        torrent_url: str,
    ) -> bool:
        torrent_id = ""
        if id_pattern:
            # First try to match the pattern in the response URL (for redirects)
            url_match = re.search(id_pattern, str(response.url))
            if url_match:
                torrent_id = url_match.group(1)
                meta.tracker_status[tracker]["torrent_id"] = torrent_id
            else:
                # Fall back to searching in response text
                text_match = re.search(id_pattern, response.text)
                if text_match:
                    torrent_id = text_match.group(1)
                    meta.tracker_status[tracker]["torrent_id"] = torrent_id

        torrent_hash = await self.common.create_torrent_ready_to_seed(meta, tracker, source_flag, user_announce_url, torrent_url + torrent_id, hash_is_id=hash_is_id)

        if hash_is_id and torrent_hash is not None:
            meta.tracker_status[tracker]["torrent_id"] = torrent_hash

        meta.tracker_status[tracker]["status_message"] = "Torrent uploaded successfully."

        return True

    async def handle_failed_upload(
        self,
        meta: Meta,
        tracker: str,
        success_status_code: str,
        success_text: str,
        error_text: str,
        response: httpx.Response,
        success_list: list[str] | None = None,
    ) -> bool:
        message = ["data error: The upload appears to have failed. It may have uploaded, go check."]
        if success_text:
            message.append(f"Could not find the success text '{success_text}' in the response.")
        elif success_list:
            message.append(f"Could not find any of the success strings in {success_list} in the response.")
        elif error_text:
            message.append(f"Found the error text '{error_text}' in the response.")
        elif success_status_code:
            message.append(f"Expected status code '{success_status_code}', got '{response.status_code}'.")
        else:
            message.append("Unknown upload error.")

        if error_message := extract_upload_error(response.text):
            message.append(f"Tracker error: {error_message}")

        failure_path = await self.common.save_html_file(meta, tracker, response.text, "Failed_Upload")
        message.append(
            f"The web page has been saved to {failure_path} for analysis.\n"
            "Do not share this file publicly, as it may contain confidential information such as passkeys, IP address, e-mail, etc.\n"
            "You can open this file in a web browser to see what went wrong.\n"
        )

        meta.tracker_status[tracker]["status_message"] = "\n".join(message)
        return False
