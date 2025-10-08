import aiofiles
import http.cookiejar
import httpx
import os
import re
from src.console import console
from src.trackers.COMMON import COMMON


class CookieValidator:
    def __init__(self):
        pass

    async def load_session_cookies(self, meta, tracker):
        cookie_file = os.path.abspath(f"{meta['base_dir']}/data/cookies/{tracker}.txt")
        cookie_jar = http.cookiejar.MozillaCookieJar(cookie_file)

        try:
            cookie_jar.load(ignore_discard=True, ignore_expires=True)
        except http.cookiejar.LoadError as e:
            console.print(f"{tracker}: Failed to load the cookie file: {e}")
            console.print(
                f"{tracker}: Please ensure the cookie file is in the correct format (Netscape)."
            )
            return False
        except FileNotFoundError:
            console.print(
                f"{tracker}: [red]Cookie file not found.[/red]\n"
                f"{tracker}: You must first log in through your usual browser and export the cookies to: [yellow]{cookie_file}[/yellow]\n"
                f'{tracker}: Cookies can be exported using browser extensions like "cookies.txt" (Firefox) or "Get cookies.txt LOCALLY" (Chrome).'
            )
            return False

        return cookie_jar

    async def save_session_cookies(self, tracker, cookie_jar):
        """Save updated cookies."""
        if not cookie_jar:
            console.print(
                f"{tracker}: Cookie jar not initialized, cannot save cookies."
            )
            return

        try:
            cookie_jar.save(ignore_discard=True, ignore_expires=True)
        except Exception as e:
            console.print(f"{tracker}: Failed to update the cookie file: {e}")

    async def cookie_validation(
        self,
        meta,
        tracker,
        test_url="",
        status_code="",
        error_text="",
        success_text="",
        token_pattern="",
    ):
        """
        Validate login cookies for a tracker by checking specific indicators on a test page.
        Return False to skip the upload if credentials are invalid.
        """
        cookie_jar = await self.load_session_cookies(meta, tracker)
        if not cookie_jar:
            return False

        headers = {
            "User-Agent": f"Upload Assistant {meta.get('current_version', 'github.com/Audionut/Upload-Assistant')}"
        }

        try:
            async with httpx.AsyncClient(
                headers=headers, timeout=20.0, cookies=cookie_jar
            ) as session:
                response = await session.get(test_url)
                text = response.text
                # if meta.get('debug', False):
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
                token = ""
                if token_pattern:
                    match = re.search(token_pattern, text)
                    if not match:
                        await self.handle_validation_failure(meta, tracker, text)
                        return False
                    token = str(match.group(1))

                # Save cookies only after a confirmed valid login
                await self.save_session_cookies(tracker, cookie_jar)
                return token or True

        except httpx.ConnectTimeout:
            console.print(f"{tracker}: Connection timed out")
        except httpx.ReadTimeout:
            console.print(f"{tracker}: Read timed out")
        except httpx.ConnectError:
            console.print(f"{tracker}: Failed to connect to the server")
        except httpx.ProxyError:
            console.print(f"{tracker}: Proxy connection failed")
        except httpx.DecodingError:
            console.print(f"{tracker}: Response decoding failed")
        except httpx.TooManyRedirects:
            console.print(f"{tracker}: Too many redirects")
        except httpx.HTTPStatusError as e:
            console.print(f"{tracker}: HTTP error {e.response.status_code}: {e}")
        except httpx.RequestError as e:
            console.print(f"{tracker}: Request error: {e}")
        except Exception as e:
            console.print(f"{tracker}: Unexpected error: {e}")

        return False

    async def handle_validation_failure(self, meta, tracker, text):
        console.print(
            f"{tracker}: Validation failed. The cookie appears to be expired or invalid.\n"
            f"{tracker}: Please log in through your usual browser and export the cookies again."
        )
        failure_path = (
            f"{meta['base_dir']}/tmp/{meta['uuid']}/[{tracker}]Failed_Login.html"
        )
        os.makedirs(os.path.dirname(failure_path), exist_ok=True)
        async with aiofiles.open(failure_path, "w", encoding="utf-8") as f:
            await f.write(text)
        console.print(
            f"The web page has been saved to [yellow]{failure_path}[/yellow] for analysis.\n"
            "[red]Do not share this file publicly[/red], as it may contain confidential information such as passkeys, IP address, e-mail, etc.\n"
            "You can open this file in a web browser to see what went wrong.\n"
        )

        return

    async def find_html_token(self, tracker, token_pattern, response):
        auth_match = re.search(token_pattern, response)
        if not auth_match:
            console.print(
                f"{tracker}: The required token could not be found in the page's HTML.\n"
                f"{tracker}: This can happen if the site HTML has changed or if the login failed silently."
            )
            return False
        else:
            return str(auth_match.group(1))


class CookieUploader:
    def __init__(self, config):
        self.config = config
        pass

    async def handle_upload(
        self,
        meta,
        tracker,
        source_flag,
        announce,
        torrent_url,
        data,
        file_name,
        upload_cookies,
        upload_url,
        id_pattern="",
        success_status_code="",
        error_text="",
        success_text="",
    ):
        values = [success_status_code, error_text, success_text]
        count = sum(bool(v) for v in values)

        if count == 0 or count > 1:
            if count == 0:
                error = "You must provide at least one of: success_status_code, error_text, or success_text."
            else:
                error = "Only one of success_status_code, error_text, or success_text should be provided."
            meta["tracker_status"][tracker]["status_message"] = error
            return False

        await COMMON(config=self.config).edit_torrent(meta, tracker, source_flag)
        torrent_path = f"{meta['base_dir']}/tmp/{meta['uuid']}/[{self.tracker}].torrent"
        with open(torrent_path, 'rb') as torrent_file:
            files = {
                file_name: (f'[{tracker}].torrent', torrent_file, 'application/x-bittorrent'),
            }

        headers = {
            "User-Agent": f"Upload Assistant {meta.get('current_version', 'github.com/Audionut/Upload-Assistant')}"
        }

        try:
            async with httpx.AsyncClient(
                headers=headers, timeout=30.0, cookies=upload_cookies
            ) as session:

                if not meta.get("debug", False):
                    response = await session.post(upload_url, data=data, files=files)

                    if success_text and success_text in response.text:
                        return await self.handle_successful_upload(meta, tracker, response, id_pattern, source_flag, announce, torrent_url)

                    elif success_status_code and int(response.status_code) == int(success_status_code):
                        return await self.handle_successful_upload(meta, tracker, response, id_pattern, source_flag, announce, torrent_url)

                    elif error_text and error_text not in response.text:
                        return await self.handle_successful_upload(meta, tracker, response, id_pattern, source_flag, announce, torrent_url)

                    else:
                        return await self.handle_failed_upload(
                            meta, tracker, success_status_code, success_text, error_text, response
                        )

                else:
                    console.print("Headers:")
                    console.print(session.headers)
                    console.print()
                    console.print("Cookies:")
                    console.print(session.cookies)
                    console.print()
                    console.print("Form data:")
                    console.print(data)
                    meta["tracker_status"][tracker]["status_message"] = "Debug mode enabled, not uploading"

        except httpx.ConnectTimeout:
            meta["tracker_status"][tracker]["status_message"] = f"{tracker}: Connection timed out"
            return False
        except httpx.ReadTimeout:
            meta["tracker_status"][tracker]["status_message"] = f"{tracker}: Read timed out"
            return False
        except httpx.ConnectError:
            meta["tracker_status"][tracker]["status_message"] = f"{tracker}: Failed to connect to the server"
            return False
        except httpx.ProxyError:
            meta["tracker_status"][tracker]["status_message"] = f"{tracker}: Proxy connection failed"
            return False
        except httpx.DecodingError:
            meta["tracker_status"][tracker]["status_message"] = f"{tracker}: Response decoding failed"
            return False
        except httpx.TooManyRedirects:
            meta["tracker_status"][tracker]["status_message"] = f"{tracker}: Too many redirects"
            return False
        except httpx.HTTPStatusError as e:
            meta["tracker_status"][tracker]["status_message"] = f"{tracker}: HTTP error {e.response.status_code}: {e}"
            return False
        except httpx.RequestError as e:
            meta["tracker_status"][tracker]["status_message"] = f"{tracker}: Request error: {e}"
            return False
        except Exception as e:
            meta["tracker_status"][tracker]["status_message"] = f"{tracker}: Unexpected error: {e}"
            return False

        return False

    async def handle_successful_upload(self, meta, tracker, response, id_pattern, source_flag, announce, torrent_url):
        torrent_id = ''
        if id_pattern:
            match = re.search(id_pattern, response.text)
            if match:
                torrent_id = match.group(1)
                meta["tracker_status"][tracker]["torrent_id"] = torrent_id

        meta["tracker_status"][tracker]["status_message"] = "Torrent uploaded successfully."
        await COMMON(config=self.config).add_tracker_torrent(meta, tracker, source_flag, announce, torrent_url + torrent_id)

        return True

    async def handle_failed_upload(
        self, meta, tracker, status_code, success_text, error_text, response
    ):
        message = "data error: The upload appears to have failed. It may have uploaded, go check."
        if success_text:
            message += (
                f"\nCould not find the success text '{success_text}' in the response."
            )
        elif error_text in response.text:
            message += f"\nFound the error text '{error_text}' in the response."
        elif status_code and response.status_code != int(status_code):
            message += (
                f"\nExpected status code '{status_code}', got '{response.status_code}'."
            )
        else:
            message += "\nUnknown upload error."

        failure_path = (
            f"{meta['base_dir']}/tmp/{meta['uuid']}/[{tracker}]Failed_Upload.html"
        )
        os.makedirs(os.path.dirname(failure_path), exist_ok=True)
        async with aiofiles.open(failure_path, "w", encoding="utf-8") as f:
            await f.write(response.text)

        message += (
            f"\nThe web page has been saved to [yellow]{failure_path}[/yellow] for analysis.\n"
            "[red]Do not share this file publicly[/red], as it may contain confidential information such as passkeys, IP address, e-mail, etc.\n"
            "You can open this file in a web browser to see what went wrong.\n"
        )

        meta["tracker_status"][tracker]["status_message"] = message
        return False
