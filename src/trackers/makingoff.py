import asyncio
import contextlib
import gettext
import re
import secrets
import shutil
import urllib.parse
from html.entities import codepoint2name
from pathlib import Path
from typing import Any, ClassVar

import aiofiles
import httpx
import langcodes
import pycountry
from bs4 import BeautifulSoup

from cogs.redaction import Redaction
from src.console import logger
from src.genre_map import ENG_TO_PTBR_GENRE_MAP
from src.languages import languages_manager
from src.meta import Meta
from src.trackers.common import Common

Config = dict[str, Any]


class MakingOff:
    """
    Making Off is a BRAZILIAN Private Torrent Tracker for MOVIES / TV / GENERAL
    """

    auth_type = "cookies"
    tracker = "MAKINGOFF"
    display_name = "MakingOff"
    source_flag = ""
    base_url = "https://makingoff.org/forum"
    banned_groups: tuple[str, ...] = ()
    index_url = "https://indice.makingoff.org/"
    torrent_url = ""
    supported_categories = ("MOVIE",)
    tmdb_localization_requirements: ClassVar = {
        "pt-BR": {
            "main": "credits,translations",
        },
        "en-US": {
            "main": "translations",
        },
    }

    # HMediaInfo constants
    VIDEO_CODEC_MAP: ClassVar[list[tuple[list[str], str]]] = [
        (["avc", "h.264", "h264"], "H.264"),
        (["hevc", "h.265", "h265"], "H.265 (HEVC)"),
        (["av1"], "AV1"),
        (["vp9"], "VP9"),
        (["xvid"], "XviD"),
        (["divx"], "DivX"),
        (["mpeg-4"], "MPEG-4"),
        (["mpeg"], "MPEG-2"),
    ]

    AUDIO_CODEC_MAP: ClassVar[list[tuple[list[str], str]]] = [
        (["aac"], "AAC"),
        (["e-ac-3", "eac3"], "E-AC-3 (Dolby Digital Plus)"),
        (["ac-3", "ac3"], "AC-3 (Dolby Digital)"),
        (["truehd"], "Dolby TrueHD"),
        (["dts"], "DTS"),
        (["mp3", "mpeg audio"], "MP3"),
        (["flac"], "FLAC"),
        (["opus"], "Opus"),
    ]

    def __init__(self, config: Config):
        self.config = config
        self.common = Common(config)

        # Cache for the resolved PT-BR display title, keyed by meta.uuid.
        self._display_title_cache: dict[str, str] = {}

        tracker_config = dict(dict(config.get("TRACKERS", {})).get("MAKINGOFF", {}))
        public_trackers_raw = tracker_config.get("trackers", [])
        if isinstance(public_trackers_raw, str):
            self._public_trackers: list[str] = [t.strip() for t in public_trackers_raw.splitlines() if t.strip()]
        else:
            self._public_trackers = list(public_trackers_raw)

        self.session = httpx.AsyncClient(
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
                "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7"),
                "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
                "Accept-Encoding": "gzip, deflate",
                "Sec-Ch-Ua": '"Google Chrome";v="149", "Chromium";v="149", "Not)A;Brand";v="24"',
                "Sec-Ch-Ua-Mobile": "?0",
                "Sec-Ch-Ua-Platform": '"Windows"',
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1",
            },
            timeout=60.0,
        )

    def _normalize_codec(self, fmt: str, mapping: list[tuple[list[str], str]]) -> str:
        f = fmt.lower()
        for keys, label in mapping:
            if any(k in f for k in keys):
                return label
        return fmt

    def _mediainfo_video_codec(self, meta: Meta, video_track: dict[str, Any]) -> str:
        """Return the normalised video codec label."""
        fmt = video_track.get("Format", "").strip()
        if not fmt:
            fmt = (meta.video_encode or meta.video_codec or "").strip()
        return self._normalize_codec(fmt, self.VIDEO_CODEC_MAP) if fmt else ""

    def _mediainfo_audio_codec(self, meta: Meta, audio_track: dict[str, Any]) -> str:
        """Return the normalised audio codec label."""
        fmt = audio_track.get("Format", "").strip()
        if not fmt:
            fmt = (meta.audio or "").strip()
        return self._normalize_codec(fmt, self.AUDIO_CODEC_MAP) if fmt else ""

    def _mediainfo_container(self, general_track: dict[str, Any], fallback: str = "") -> str:
        """Return the container format, preferring mediainfo General track."""
        fmt = (general_track.get("Format", "") or "").lower()
        if "matroska" in fmt:
            return "MKV"
        if "avi" in fmt:
            return "AVI"
        if "mp4" in fmt or "mpeg-4" in fmt:
            return "MP4"
        if fmt:
            return general_track.get("Format", fallback)
        return fallback

    def _mediainfo_filesize(self, meta: Meta) -> str:
        """Return a human-readable file size (GB or MB)."""
        try:
            gb = meta.source_size / 1024**3
            return f"{gb:.2f} GB" if gb >= 1 else f"{meta.source_size / 1024**2:.0f} MB"
        except TypeError, ValueError:
            return "N/A"

    def _mediainfo_duration(self, general_track: dict[str, Any], video_track: dict[str, Any]) -> str:
        """Return duration in minutes from mediainfo General track."""
        raw = general_track.get("Duration") or video_track.get("Duration") or ""
        try:
            return str(int(float(raw)) // 60)
        except TypeError, ValueError:
            return ""

    def _aspect_ratio(self, width: Any, height: Any) -> str:
        """Return an aspect ratio category from video dimensions."""
        try:
            r = int(width) / int(height)
            if r < 1.4:
                return "Tela Cheia (4x3)"
            if r < 1.8:
                return "Widescreen (16x9)"
            if r < 2.3:
                return "Widescreen (2.35:1)"
            return "Widescreen (2.39:1)"
        except TypeError, ValueError, ZeroDivisionError:
            return "Widescreen (16x9)"

    def _html_encode(self, text: str) -> str:
        """Replace non-ASCII codepoints with named HTML entities where possible."""
        result = []
        for ch in text:
            cp = ord(ch)
            if cp > 127 and cp in codepoint2name:
                result.append(f"&{codepoint2name[cp]};")
            else:
                result.append(ch)
        return "".join(result)

    def _screen_rows(self, image_urls: list[str]) -> str:
        """Pair screenshot URLs into two-column BBCode rows."""
        rows = ""
        for i in range(0, len(image_urls), 2):
            left = image_urls[i]
            right = image_urls[i + 1] if i + 1 < len(image_urls) else ""
            cells = f"[screenLeft][screenIma]{left}[/screenIma][/screenLeft][screenRight][screenIma]{right}[/screenIma][/screenRight][/tr]"
            rows += cells if i == 0 else f"[tr]{cells}"
        return rows

    def _build_bbcode(
        self,
        *,
        title_br: str,
        title_orig: str,
        release: str,
        poster_url: str,
        overview: str,
        image_urls: list[str],
        cast_text: str,
        genres: str,
        directors: str,
        duration: str,
        year: str,
        countries: str,
        audio: str,
        subs: str,
        imdb_url: str,
        quality: str,
        container: str,
        video_codec: str,
        video_brate: str,
        audio_codec: str,
        audio_brate: str,
        res_str: str,
        aspect: str,
        fps_str: str,
        filesize: str,
    ) -> str:
        """Render and return the complete BBCode post body."""
        s_rows = self._screen_rows(image_urls)

        if imdb_url:
            imdb_line = f'<div><strong class="bbc">IMDB: </strong><a class="bbc_url" href="{imdb_url}" title="Link externo">{imdb_url}</a>[/info]</div>\n'
        else:
            imdb_line = "<div>[/info]</div>\n"

        bbcode = (
            f"<div>[tablePrinc][tr][titMasc]Título do Filme[/titMasc][/tr]</div>\n"
            f"<div>[tr][titTrad]{title_br}[/titTrad][titOri]{title_orig}[/titOri]"
            f"[release]{release}[/release][/tr]</div>\n"
            f"<div>[tr][posterMasc]Poster[/posterMasc]</div>\n"
            f"<div>[sinopseMasc]Sinopse[/sinopseMasc][/tr]</div>\n"
            f"<div>[tr][poster][posterIma]{poster_url}[/posterIma][/poster]</div>\n"
            f"<div>[sinopse]{overview}[/sinopse]</div>\n"
            f"<div>[tableScreen]Screenshots[/tableScreen]</div>\n"
            f"<div>{s_rows}"
            f"[closeTab][/closeTab][/tablePrinc]</div>\n"
            f"<div>[tablePrinc][tr][posterMasc]Elenco[/posterMasc]</div>\n"
            f"<div>[infoMasc]Informações sobre o filme[/infoMasc]</div>\n"
            f"<div>[infoMasc]Informações sobre o release[/infoMasc]</div>\n"
            f"<div>[/tr][tr][elenco]\n{cast_text}\n[/elenco]</div>\n"
            f'<div>[info]<strong class="bbc">Gênero: </strong>{genres}</div>\n'
            f'<div><strong class="bbc">Diretor: </strong>{directors}</div>\n'
            f'<div><strong class="bbc">Duração: </strong>{duration} minutos</div>\n'
            f'<div><strong class="bbc">Ano de Lançamento: </strong>{year}</div>\n'
            f'<div><strong class="bbc">País de Origem: </strong>{countries}</div>\n'
            f'<div><strong class="bbc">Idioma do Áudio: </strong>{audio}</div>\n'
            f"{imdb_line}"
            f'<div>[info]<strong class="bbc">Qualidade de Vídeo: </strong>{quality}</div>\n'
            f'<div><strong class="bbc">Container: </strong>{container}</div>\n'
            f'<div><strong class="bbc">Vídeo Codec: </strong>{video_codec}</div>\n'
            f'<div><strong class="bbc">Vídeo Bitrate: </strong>{video_brate} Kbps</div>\n'
            f'<div><strong class="bbc">Áudio Codec: </strong>{audio_codec}</div>\n'
            f'<div><strong class="bbc">Áudio Bitrate: </strong>{audio_brate} Kbps</div>\n'
            f'<div><strong class="bbc">Resolução: </strong>{res_str}</div>\n'
            f'<div><strong class="bbc">Formato de Tela: </strong>{aspect}</div>\n'
            f'<div><strong class="bbc">Frame Rate: </strong>{fps_str}</div>\n'
            f'<div><strong class="bbc">Tamanho: </strong>{filesize}</div>\n'
            f'<div><strong class="bbc">Legendas: </strong>{subs}[/info]</div>\n'
            f"<div>[/tr][tr][rodape]Coopere, deixe semeando ao menos duas vezes o tamanho do arquivo que baixar.[/rodape]"
            f"[/tr][/tablePrinc]</div>"
        )

        return self._html_encode(bbcode)

    def _get_lang_name(self, lang_string: str) -> str:
        with contextlib.suppress(Exception):
            lang = langcodes.find(lang_string)
            if lang and lang.is_valid():
                return lang.display_name("pt").capitalize()
        return lang_string.capitalize()

    def _localizer_countries(self, meta: Meta) -> str:
        """Convert production country codes to PT-BR names."""
        try:
            pt_normal = gettext.translation("iso3166-1", pycountry.LOCALES_DIR, languages=["pt_BR"])
            pt_historic = gettext.translation("iso3166-3", pycountry.LOCALES_DIR, languages=["pt_BR"])
        except OSError:
            pt_normal = None
            pt_historic = None

        custom_country_mapping: dict[str, str] = {
            "XC": "Checoslováquia",
        }

        prod_countries = meta.production_countries
        origin_countries = meta.origin_country

        codes = [c.get("iso_3166_1", "") for c in prod_countries if c.get("iso_3166_1")] if prod_countries else [c for c in origin_countries if c]

        names = []
        for code in codes:
            if not code:
                continue
            code_upper = code.upper()
            if code_upper in custom_country_mapping:
                names.append(custom_country_mapping[code_upper])
                continue

            # Tenta encontrar no pycountry (países ativos)
            country = pycountry.countries.get(alpha_2=code_upper)
            if country:
                names.append(pt_normal.gettext(country.name) if pt_normal else country.name)
                continue

            # Tenta encontrar no pycountry (países históricos, ex: SU)
            historic_country = pycountry.historic_countries.get(alpha_2=code_upper)
            if historic_country:
                names.append(pt_historic.gettext(historic_country.name) if pt_historic else historic_country.name)
                continue

            names.append(code)

        return ", ".join(names) if names else "Desconhecido"

    def _localizer_genres(self, meta: Meta) -> str:
        """Convert genre names to PT-BR.

        Accepts both a comma-separated string and a list, as the Meta
        object may expose genres in either form depending on UA version.
        """
        genres_raw = meta.genres or meta.combined_genres or ""
        if not genres_raw:
            return "Desconhecido"
        genre_list = [g.strip() for g in genres_raw if g.strip()] if isinstance(genres_raw, list) else [g.strip() for g in genres_raw.split(",") if g.strip()]
        if not genre_list:
            return "Desconhecido"

        translated_genres = []
        for g in genre_list:
            translated = ENG_TO_PTBR_GENRE_MAP.get(g.lower(), g)
            if translated is not None and translated != g:
                translated = translated.title()
            translated_genres.append(translated)
        return ", ".join(translated_genres)

    def _localizer_audio_language(self, meta: Meta) -> str:
        """
        Determine audio language(s) in PT-BR.

        Resolution order: meta audio_languages, mediainfo audio tracks,
        then meta original_language as last resort.
        """
        return "Desconhecido" if not meta.audio_languages else ", ".join(self._get_lang_name(lang.strip()) for lang in meta.audio_languages)

    def _localizer_video_quality(self, meta: Meta) -> str:
        """Convert release type to a localised video quality label."""
        type_raw = meta.type or ""

        video_quality_ptbr: dict[str, str] = {
            "WEBDL": "WEB-DL",
            "WEBRIP": "WEB-Rip",
            "BLURAY": "BluRay",
            "REMUX": "BluRay Remux",
            "ENCODE": "BluRay",
            "DISC": "Blu-Ray Full",
            "DVDRIP": "DVDRip",
            "HDTV": "HDTV",
            "CAM": "CAM",
        }

        return video_quality_ptbr.get(type_raw.upper(), type_raw)

    # -- IPB client methods

    def live_session_id(self) -> str:
        """Return the most recent session_id cookie value."""
        values = [c.value for c in self.session.cookies.jar if c.name == "session_id" and c.value]
        return values[-1] if values else ""

    async def refresh_session(self) -> bool:
        """
        Refresh the IPB session token.

        IPB rotates the 's' token on each authenticated request. Sends a
        lightweight GET and verifies the response is not an anonymous session.

        Returns:
            bool: True if an authenticated session_id was obtained.
        """
        try:
            resp = await self.session.get(f"{self.base_url}/index.php?")
            resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.error(f"[cyan]{self.tracker}:[/cyan] Error validating session: {e}")
            return False

        live = self.live_session_id()
        if not live:
            match = re.search(r"[?&]s=([a-f0-9]{32})", resp.text)
            if match:
                live = match.group(1)
                self.session.cookies.set("session_id", live, domain="makingoff.org")
                self.session.cookies.set("session_id", live, domain="indice.makingoff.org")

        if not live:
            return False

        if "id='login_form'" in resp.text or 'id="login_form"' in resp.text:
            logger.warning(f"[cyan]{self.tracker}:[/cyan] The session is unauthenticated. Check member_id and pass_hash on the configuration.")
            return False

        return True

    async def get_new_post_tokens(self, forum_id: int) -> tuple[str, str, str]:
        """
        Retrieve tokens required to create a new forum topic.

        Args:
            forum_id (int): Target forum ID.

        Returns:
            tuple[str, str, str]: Session ID, auth key, attachment post key.
        """
        url = f"{self.base_url}/index.php?app=forums&module=post&section=post&do=new_post&f={forum_id}"
        try:
            resp = await self.session.get(url)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.error(f"[cyan]{self.tracker}:[/cyan] Failed loading topic new page: {e}")
            return "", "", ""

        soup = BeautifulSoup(resp.text, "html.parser")

        def _val(name: str) -> str:
            tag = soup.find("input", {"name": name})
            return str(tag.get("value", "")) if tag and hasattr(tag, "get") else ""  # type: ignore[union-attr]

        session_id = self.live_session_id() or _val("s")
        auth_key = _val("auth_key")
        attach_post_key = _val("attach_post_key")

        if "id='sign_in'" in resp.text or 'id="sign_in"' in resp.text:
            logger.warning(f"[cyan]{self.tracker}:[/cyan] Unauthenticated session detected on this page. Copy new headers from the browser.")
            return "", "", ""

        if not auth_key or not attach_post_key:
            logger.warning(f"[cyan]{self.tracker}:[/cyan] It wasn't possible to extract auth_key or attach_post_key. Check if the session is valid.")

        return session_id, auth_key, attach_post_key

    async def get_post_resolution(self, topic_url: str) -> int:
        """
        Fetches the topic resolution

        Returns:
            int: its resolution.
        """
        topic_url = re.sub(r"^https?://(www\.)?makingoff\.org", "https://makingoff.org", topic_url)

        try:
            resp = await self.session.get(topic_url, follow_redirects=True)
            resp.raise_for_status()
        except httpx.HTTPError:
            return 0

        soup = BeautifulSoup(resp.content, "html.parser", from_encoding="iso-8859-1")

        resolution = ""
        first_post = soup.find("div", attrs={"itemprop": "commentText"})
        if first_post:
            text = first_post.get_text(" ", strip=True)
            m = re.search(r"Resolu[^\s:]*[:\s]+(\d{3,4})\s*[xX×]\s*(\d{3,4})", text)  # noqa: RUF001
            if m:
                resolution = f"{m.group(1)}x{m.group(2)}"

        return int(resolution.split("x")[1]) if resolution else 0

    async def upload_attachment(
        self,
        torrent_path: str,
        session_id: str,
        attach_post_key: str,
        forum_id: int,
    ) -> bool:
        """
        Upload a torrent file as a forum attachment.

        Args:
            torrent_path (str): Path to the torrent file.
            session_id (str): Active forum session ID.
            attach_post_key (str): Attachment post key.
            forum_id (int): Target forum ID.

        Returns:
            bool: True if the upload succeeded.
        """
        url = (
            f"{self.base_url}/index.php?"
            f"s={session_id}"
            f"&app=core&module=attach&section=attach"
            f"&do=attachUploadiFrame"
            f"&attach_rel_module=post&attach_rel_id=0"
            f"&attach_post_key={attach_post_key}"
            f"&forum_id={forum_id}"
            f"&fetch_all=1"
        )
        try:
            async with aiofiles.open(torrent_path, "rb") as f:
                data = await f.read()
            filename = Path(torrent_path).name
            resp = await self.session.post(
                url,
                files={"FILE_UPLOAD": (filename, data, "application/x-bittorrent")},
            )
            resp.raise_for_status()
        except FileNotFoundError:
            logger.error(f"[cyan]{self.tracker}:[/cyan] [bold red]Torrent file not found[/bold red]: {torrent_path}")
            return False
        except httpx.HTTPError as e:
            logger.error(f"[cyan]{self.tracker}:[/cyan] [bold red]Failed uploading attachment:[/bold red] {e}")
            return False

        if '"is_error":0' in resp.text or '"msg":"upload_ok"' in resp.text:
            logger.info(f"[cyan]{self.tracker}:[/cyan] [green]Attachment sent successfully.[/green]")
            return True

        logger.error(f"[cyan]{self.tracker}:[/cyan] [bold red]Unwanted response while uploading attachment:[/bold red]\n{resp.text[:500]}")
        return False

    async def search(self, index_url: str, phrase: str) -> dict[str, str] | None:
        """
        Performs a search on the given index url

        Args:
            index_url (str): The index url (e.g. "https://indice.makingoff.org").
            phrase (str): The text to be searched.

        Returns:
            dict[str, str]: A dictionary mapping title -> topic URL.
            None: if the search results nothing.
        """
        # do the search operation
        response_url = index_url.rstrip("/") + "/response.php"
        payload = {
            "current": "1",
            "rowCount": "50",
            "sort[tid]": "desc",
            "searchPhrase": phrase,
            "id": "b0df282a-0d67-40e5-8558-c9e93b7befed",
        }
        try:
            resp = await self.session.post(
                response_url,
                data=payload,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": index_url,
                    "Origin": index_url,
                },
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as e:
            logger.error(f"[cyan]{self.tracker}:[/cyan] [bold red]Error on the search:[/bold red] {e}")
            return None
        except Exception as e:
            logger.error(f"[cyan]{self.tracker}:[/cyan] [bold red]Unwanted response while searching:[/bold red] {e}")
            return None

        rows = data.get("rows") or []
        if not rows:
            return None

        # parse the dict from the response
        # title -> url
        results: dict[str, str] = {}
        for row in rows:
            title = row.get("title", "").strip()
            link_html = row.get("link", "")
            url_match = re.search(r'href=["\']([^"\']+)["\']', link_html)
            if title and url_match:
                results[title] = url_match.group(1)

        return results or None

    def get_topic_fields(
        self,
        forum_id: int,
        session_id: str,
        auth_key: str,
        attach_post_key: str,
        topic_title: str,
        post_body: str,
    ) -> dict[str, str]:
        """
        Build the dictionary of form fields for creating a new topic.
        """
        return {
            "enableemo": "yes",
            "enablesig": "yes",
            "TopicTitle": topic_title,
            "isRte": "1",
            "noSmilies": "0",
            "noCKEditor": "0",
            "Post": post_body,
            "st": "0",
            "app": "forums",
            "module": "post",
            "section": "post",
            "do": "new_post_do",
            "s": session_id,
            "p": "0",
            "t": "",
            "f": str(forum_id),
            "parent_id": "0",
            "attach_post_key": attach_post_key,
            "auth_key": auth_key,
            "removeattachid": "0",
            "return": "",
            "_from": "",
            "dosubmit": "Criar novo tópico",
        }

    async def create_topic(
        self,
        forum_id: int,
        session_id: str,
        auth_key: str,
        attach_post_key: str,
        topic_title: str,
        post_body: str,
    ) -> str:
        """
        Create a new forum topic and return its URL.

        The forum uses ISO-8859-1. Form fields are encoded as Latin-1 with
        HTML numeric entities for out-of-range characters, matching what a
        browser would submit.

        Args:
            forum_id (int): Target forum ID.
            session_id (str): Active forum session ID.
            auth_key (str): Forum authentication key.
            attach_post_key (str): Attachment post key.
            topic_title (str): Topic title.
            post_body (str): Topic content.

        Returns:
            str: Topic URL, or an empty string if creation failed.
        """
        fields = self.get_topic_fields(
            forum_id=forum_id,
            session_id=session_id,
            auth_key=auth_key,
            attach_post_key=attach_post_key,
            topic_title=topic_title,
            post_body=post_body,
        )

        body = "&".join(
            f"{urllib.parse.quote_plus(k)}={urllib.parse.quote_plus((v).encode('latin-1', errors='xmlcharrefreplace').decode('latin-1'), encoding='latin-1')}"
            for k, v in fields.items()
        )

        try:
            resp = await self.session.post(
                f"{self.base_url}/index.php?",
                content=body.encode("latin-1"),
                headers={"Content-Type": "application/x-www-form-urlencoded; charset=ISO-8859-1"},
                follow_redirects=True,
            )
            resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.error(f"[cyan]{self.tracker}:[/cyan] Failed creating topic: {e}")
            return ""

        topic_url = str(resp.url)
        if "showtopic=" in topic_url or "topic/" in topic_url:
            return topic_url

        match = re.search(r"showtopic=(\d+)", resp.text)
        if match:
            return f"{self.base_url}/index.php?showtopic={match.group(1)}"

        logger.warning(f"[yellow]{self.tracker}:[/yellow] Topic possibly created, but it wasn't possible to get the url.")
        return topic_url

    async def validate_credentials(self, _meta: Meta) -> bool:
        """
        Validate tracker credentials and configure the authenticated session.

        Accepts either a full ``cookie_header`` string (recommended, copied
        directly from the browser) or individual ``member_id`` / ``pass_hash``
        fields.  The ``session_id`` cookie is always generated automatically
        as a random 32-character hex token — IPB rotates it on every
        authenticated response, so the first value just needs to exist.

        Args:
            meta: Release metadata.

        Returns:
            bool: True if the credentials are valid.
        """
        tracker_config = dict(dict(self.config.get("TRACKERS", {})).get(self.tracker, {}))

        raw_cookie_header = tracker_config.get("cookie_header", "").strip()
        if raw_cookie_header:
            for part in raw_cookie_header.split(";"):
                if "=" not in part:
                    continue
                name, _, value = part.strip().partition("=")
                if name:
                    self.session.cookies.set(name, value, domain="makingoff.org")
                    self.session.cookies.set(name, value, domain="indice.makingoff.org")
        else:
            member_id = tracker_config.get("member_id", "").strip()
            pass_hash = tracker_config.get("pass_hash", "").strip()

            if not member_id or not pass_hash:
                logger.error(
                    f"[cyan]{self.tracker}:[/cyan] [bold red]Incomplete credentials on configuration "
                    f"Fill 'cookie_header' (recommended) or 'member_id' and 'pass_hash' "
                    f"in config['TRACKERS']['{self.tracker}'].[/bold red]"
                )
                return False

            # Generate a fresh random session_id; IPB replaces it after the
            # first authenticated request, so the exact value does not matter.
            session_id = secrets.token_hex(16)

            for domain in ("makingoff.org", "indice.makingoff.org"):
                self.session.cookies.set("session_id", session_id, domain=domain)
                self.session.cookies.set("member_id", member_id, domain=domain)
                self.session.cookies.set("pass_hash", pass_hash, domain=domain)

        if not await self.refresh_session():
            logger.error(f"[cyan]{self.tracker}:[/cyan] [bold red]Session couldn't be validated.[/bold red] Cookies may be expired.")
            return False

        return True

    async def search_existing(self, meta: Meta) -> list[dict[str, str]]:
        """
        Search for existing releases on the forum before uploading.

        Args:
            meta: Release metadata.

        Returns:
            list[dict[str, str]]: Detected duplicate entries.
        """
        duplicates: list[dict[str, str]] = []

        if not await self.validate_credentials(meta):
            return duplicates

        hidef_resolutions = {"720p", "1080i", "1080p", "2160p", "4320p"}
        resolution_str = meta.resolution
        uploading_hidef = resolution_str in hidef_resolutions
        upload_year = str(meta.year)

        title_ptbr = await self._resolve_display_title(meta)
        title_orig = meta.original_title
        title_en = meta.title

        if self._is_brazilian(meta):
            candidates = [title_ptbr]
        else:
            candidates = []
            for t in [title_ptbr, title_en, title_orig]:
                if t and t not in candidates:
                    candidates.append(t)

        results: dict[str, str] = {}
        for candidate in candidates:
            term = candidate.strip()
            logger.info(f"[cyan]{self.tracker}:[/cyan] [yellow]Searching for:[/yellow] {term}")
            found = await self.search(self.index_url, term)
            if found:
                results = found
                break

        if not results:
            return duplicates

        for title, url in results.items():
            existing_hidef = title.strip().startswith("[Hidef]")

            if upload_year:
                year_int = int(upload_year)
                if not any(f"({y})" in title for y in (year_int - 1, year_int, year_int + 1)):
                    logger.info(f"[cyan]{self.tracker}:[/cyan] [yellow]Skipping: different year in existing release:[/yellow] {title}")
                    continue

            # Uploading SD while a Hidef exists → block immediately.
            if not uploading_hidef and existing_hidef:
                logger.warning(f"[cyan]{self.tracker}:[/cyan] [bold red]Aborting: A Hidef release exists:[/bold red] {title}")
                meta.skipping = self.tracker
                duplicates.append({"name": title, "size": "", "link": url})
                continue

            # Uploading Hidef over an existing SD → allowed.
            if uploading_hidef and not existing_hidef:
                continue

            # Same tier (SD vs SD or Hidef vs Hidef) → compare resolution.
            resolution = await self.get_post_resolution(url)

            try:
                upload_height = int(resolution_str.replace("p", "").replace("i", ""))
            except TypeError, ValueError:
                upload_height = 0

            if resolution >= upload_height:
                logger.warning(f"[cyan]{self.tracker}:[/cyan] [bold red]Aborting: A better or equivalent Hidef release exists:[/bold red] {title}")
                meta.skipping = self.tracker
                duplicates.append({"name": title, "size": str(resolution), "link": url})
                continue

        return duplicates

    # -- forum routing

    async def get_forum_id(self, meta: Meta) -> int:
        """
        Determine the target forum ID based on content type and country of origin.

        Args:
            meta: Release metadata.

        Returns:
            int: Selected forum ID.
        """
        # https://en.wikipedia.org/wiki/List_of_ISO_3166_country_codes
        africa = [
            "DZ",
            "AO",
            "BJ",
            "BW",
            "BF",
            "BI",
            "CM",
            "CV",
            "CF",
            "TD",
            "KM",
            "CD",
            "CG",
            "CI",
            "DJ",
            "EG",
            "GQ",
            "ER",
            "ET",
            "GA",
            "GM",
            "GH",
            "GN",
            "GW",
            "KE",
            "LS",
            "LR",
            "LY",
            "MG",
            "MW",
            "ML",
            "MR",
            "MU",
            "MA",
            "MZ",
            "NA",
            "NE",
            "NG",
            "RW",
            "ST",
            "SN",
            "SC",
            "SL",
            "SO",
            "ZA",
            "SS",
            "SD",
            "SZ",
            "TZ",
            "TG",
            "TN",
            "UG",
            "ZM",
            "ZW",
        ]

        asia = [
            "AF",
            "AM",
            "AZ",
            "BD",
            "BT",
            "BN",
            "KH",
            "CN",
            "GE",
            "IN",
            "ID",
            "JP",
            "KZ",
            "KG",
            "LA",
            "MY",
            "MV",
            "MN",
            "MM",
            "NP",
            "KP",
            "KR",
            "PK",
            "PH",
            "SG",
            "LK",
            "TW",
            "TJ",
            "TH",
            "TL",
            "TM",
            "UZ",
            "VN",
        ]

        europe = [
            "AL",
            "XC",
            "AD",
            "AT",
            "BY",
            "BE",
            "BA",
            "BG",
            "HR",
            "SU",
            "CY",
            "CZ",
            "DK",
            "EE",
            "FI",
            "FR",
            "DE",
            "GR",
            "HU",
            "IS",
            "IE",
            "IT",
            "XK",
            "LV",
            "LI",
            "LT",
            "LU",
            "MT",
            "MD",
            "MC",
            "ME",
            "MK",
            "NL",
            "NO",
            "PL",
            "PT",
            "RO",
            "RU",
            "SM",
            "RS",
            "SK",
            "SI",
            "ES",
            "SE",
            "CH",
            "UA",
            "GB",
            "VA",
        ]

        latin_america = ["AR", "BO", "CL", "CO", "CR", "CU", "DO", "EC", "SV", "GT", "HN", "MX", "NI", "PA", "PY", "PE", "UY", "VE"]

        brasil = ["BR"]
        north_america = ["US", "CA"]

        oceania = ["AU", "FJ", "KI", "MH", "FM", "NR", "NZ", "PW", "PG", "WS", "SB", "TO", "TV", "VU"]

        middle_east = ["BH", "IR", "IQ", "IL", "JO", "KW", "LB", "OM", "QA", "SA", "SY", "AE", "YE"]

        forum_id_by_country: dict[str, int] = {}
        for code in africa:
            forum_id_by_country[code] = 461
        for code in asia:
            forum_id_by_country[code] = 24
        for code in europe:
            forum_id_by_country[code] = 25
        for code in latin_america:
            forum_id_by_country[code] = 29
        for code in brasil:
            forum_id_by_country[code] = 27
        for code in north_america:
            forum_id_by_country[code] = 26
        for code in oceania:
            forum_id_by_country[code] = 31
        for code in middle_east:
            forum_id_by_country[code] = 30

        genres_raw = meta.genres or meta.combined_genres
        genres_str = ", ".join(genres_raw) if isinstance(genres_raw, list) else genres_raw
        if "documentary" in genres_str.lower() or "documentário" in genres_str.lower():
            return 28

        if 0 < meta.runtime < 40:
            return 77

        origin_countries: list[str] = meta.origin_country
        if not origin_countries:
            prod_countries = meta.production_countries
            origin_countries = [c.get("iso_3166_1", "") for c in prod_countries if c.get("iso_3166_1")]

        for code in origin_countries:
            if code in forum_id_by_country:
                return forum_id_by_country[code]

        logger.info(
            f"[cyan]{self.tracker}:[/cyan] [bold yellow]Unmapped origin country [/bold yellow]({origin_countries}). [bold yellow]Select the subforum manually:[/bold yellow]"
        )
        forum_options = {
            "1": (461, "África"),
            "2": (24, "Asiático"),
            "3": (77, "Curtas"),
            "4": (28, "Documentários"),
            "5": (25, "Europeu"),
            "6": (29, "Latino Americano"),
            "7": (27, "Nacional (Brasil)"),
            "8": (26, "Norte-Americano"),
            "9": (31, "Oceania"),
            "10": (30, "Oriente Médio"),
        }
        for k, (fid, name) in forum_options.items():
            logger.info(f"  {k}) {name} (ID: {fid})")

        choice = (await asyncio.to_thread(input, "Escolha: ")).strip()
        if choice in forum_options:
            return forum_options[choice][0]

        logger.warning(f"[cyan]{self.tracker}:[/cyan] [yellow]Invalid option, using North-American (26) as default.[/yellow]")
        return 26

    # -- title resolution

    def _is_brazilian(self, meta: Meta) -> bool:
        """
        Detect whether the release is a Brazilian production.

        Checks origin_country and production_countries first; falls back to
        original_language == 'pt' for older/regional titles.

        Args:
            meta: Release metadata.

        Returns:
            bool: True if the release is considered Brazilian.
        """
        origin_countries: list[str] = meta.origin_country
        prod_codes = [c.get("iso_3166_1", "") for c in meta.production_countries if c.get("iso_3166_1")]
        if "BR" in origin_countries or "BR" in prod_codes:
            return True
        return str(meta.original_language).lower() == "pt"

    def _find_translation_title(self, ptbr_main_or_en_main: dict[str, Any], iso_639_1: str, iso_3166_1: str | None = None) -> str:
        translations = ptbr_main_or_en_main.get("translations", {}).get("translations", [])
        primary = next(
            (t for t in translations if t.get("iso_639_1") == iso_639_1 and (iso_3166_1 is None or t.get("iso_3166_1") == iso_3166_1)),
            None,
        )
        if not primary and iso_3166_1:
            primary = next(
                (t for t in translations if t.get("iso_639_1") == iso_639_1),
                None,
            )
        return (primary or {}).get("data", {}).get("title", "") or ""

    async def _resolve_display_title(self, meta: Meta) -> str:
        """
        Resolve the display title, preferring PT-BR.

        For Brazilian films, tries PT-BR first then falls back to
        original_title. For foreign films, tries PT-BR then English
        when the native and original titles are identical.

        The resolved title is cached on the tracker instance (keyed by
        ``meta.uuid``) so that repeated calls within the same upload do
        not trigger extra TMDB requests.

        Args:
            meta: Release metadata.

        Returns:
            str: Resolved display title.
        """
        cache_key: str = meta.uuid
        if cache_key and cache_key in self._display_title_cache:
            return self._display_title_cache[cache_key]

        title_native = meta.title
        title_orig = meta.original_title

        ptbr_main = meta.tmdb_localized_data.get("pt-BR", {}).get("main", {})
        en_main = meta.tmdb_localized_data.get("en-US", {}).get("main", {})

        if self._is_brazilian(meta):
            if ptbr_main:
                ptbr = self._find_translation_title(ptbr_main, "pt", "BR")
                if ptbr:
                    title_native = ptbr
                elif title_orig:
                    title_native = title_orig
        else:
            if ptbr_main:
                ptbr = self._find_translation_title(ptbr_main, "pt", "BR")
                if ptbr and ptbr.lower() != title_orig.lower():
                    title_native = ptbr
                elif title_native.lower() == title_orig.lower() and en_main:
                    en = self._find_translation_title(en_main, "en", "US")
                    if en and en.lower() != title_orig.lower():
                        title_native = en

        if cache_key:
            self._display_title_cache[cache_key] = title_native
        return title_native

    # -- topic title

    async def get_topic_title(self, meta: Meta) -> str:
        """
        Generate the forum topic title.

        Format for Brazilian films:  [Hidef] PT-BR Title (Year)
        Format for foreign films:    [Hidef] PT-BR Title / Original Title (Year)

        Args:
            meta (dict[str, Any]): Release metadata.

        Returns:
            str: Formatted topic title.
        """
        hidef_resolutions = {"720p", "1080i", "1080p", "2160p", "4320p"}
        prefix = "[Hidef] " if meta.resolution in hidef_resolutions else ""

        title_ptbr = await self._resolve_display_title(meta)
        year: str = str(meta.year) if meta.year else ""

        if self._is_brazilian(meta):
            title_part = title_ptbr
        else:
            title_orig = meta.original_title
            title_part = f"{title_ptbr} / {title_orig}" if title_orig and title_orig.lower() != title_ptbr.lower() else title_ptbr

        return f"{prefix}{title_part} ({year})" if year else f"{prefix}{title_part}"

    # -- description generation

    def _extract_image_urls(self, meta: Meta) -> list[str]:
        """
        Extract screenshot URLs from meta image_list.

        Handles both plain URL strings and dict entries produced by
        various image host modules.

        Args:
            meta (dict[str, Any]): Release metadata.

        Returns:
            list[str]: Resolved image URLs.
        """
        urls: list[str] = []
        for img in meta.image_list:
            if isinstance(img, str):
                urls.append(img)
            elif isinstance(img, dict):
                url = img.get("raw_url") or img.get("img_url") or img.get("url") or img.get("web_url") or ""
                if url:
                    urls.append(url)
        return urls

    async def _subtitles_ptbr(self, meta: Meta) -> str:
        """
        Prompt the user to select a subtitle type.

        Returns:
            str: Selected subtitle type label.
        """
        if not meta.language_checked:
            await languages_manager.process_desc_language(meta, tracker=self.tracker)
        portuguese_languages = {"portuguese", "português", "pt"}

        meta_subtitle_languages = meta.subtitle_languages if meta.subtitle_languages else []
        found_languages = {lang.lower() for lang in meta_subtitle_languages}

        if any(lang in portuguese_languages for lang in found_languages):
            return "Embutidas"

        # Fallback to asking
        options = {"1": "Anexas", "2": "Embutidas", "3": "Fixas", "4": "Sem Legenda"}
        logger.info(f"[cyan]{self.tracker}:[/cyan] [yellow]Any subtitles?[/yellow]")
        for k, v in options.items():
            logger.info(f"  {k}) {v}")
        selection = (await asyncio.to_thread(input, "Choose: ")).strip()
        return options.get(selection, "")

    async def generate_description(self, meta: Meta) -> str:
        """
        Generate the BBCode description for the forum post.

        Args:
            meta (dict[str, Any]): Release metadata.

        Returns:
            str: Formatted BBCode description.
        """
        title_br = await self._resolve_display_title(meta)
        title_orig = title_br if self._is_brazilian(meta) else meta.original_title or title_br

        release_name = meta.basename_no_ext or meta.name or meta.uuid
        release = release_name.replace(" ", ".")

        # Prefer TMDB PT-BR overview already cached by the UA; fall back to
        # translation details from the pre-fetched translations list.
        ptbr_main = meta.tmdb_localized_data.get("pt-BR", {}).get("main", {})

        poster_raw = ptbr_main.get("poster_path") or meta.tmdb_poster
        poster_url = poster_raw if poster_raw.startswith("http") else f"https://image.tmdb.org/t/p/original{poster_raw}" if poster_raw else ""

        pt_overview = ""
        if ptbr_main:
            translations = ptbr_main.get("translations", {}).get("translations", [])
            for iso_3166_1 in ("BR", None):
                match = next(
                    (t for t in translations if t.get("iso_639_1") == "pt" and (iso_3166_1 is None or t.get("iso_3166_1") == iso_3166_1)),
                    None,
                )
                if match:
                    pt_overview = match.get("data", {}).get("overview", "")
                    if pt_overview:
                        break

        overview = ptbr_main.get("overview") or pt_overview or meta.overview

        cast_list = ptbr_main.get("credits", {}).get("cast", [])[:15] if ptbr_main else []
        cast_names = [m["name"] for m in cast_list if m.get("name")]
        cast_text = "".join(f"<div>{name.strip()}</div>\n" for name in cast_names if name.strip())

        tmdb_dirs = [m["name"] for m in ptbr_main.get("credits", {}).get("crew", []) if m.get("job") == "Director"] if ptbr_main else []
        imdb_dirs = meta.imdb_info.get("directors", []) or []
        directors = ", ".join(tmdb_dirs if tmdb_dirs else imdb_dirs)

        imdb_url = ""
        if meta.imdb_id or meta.imdb_info.get("imdb_url"):
            imdb_url = meta.imdb_info.get("imdb_url") or f"https://www.imdb.com/title/tt{str(meta.imdb_id).zfill(7)}/"

        # Extract tracks from meta.mediainfo
        tracks = meta.mediainfo.get("media", {}).get("track", [])
        video_track = next((t for t in tracks if t.get("@type") == "Video"), {})
        audio_track = next((t for t in tracks if t.get("@type") == "Audio"), {})
        general_track = next((t for t in tracks if t.get("@type") == "General"), {})

        width, height = meta.video_width or 0, meta.video_height or 0

        return self._build_bbcode(
            title_br=title_br,
            title_orig=title_orig,
            release=release,
            poster_url=poster_url,
            overview=overview,
            image_urls=self._extract_image_urls(meta),
            cast_text=cast_text,
            genres=self._localizer_genres(meta),
            directors=directors,
            duration=str(meta.runtime or self._mediainfo_duration(general_track, video_track) or ""),
            year=str(getattr(meta, "year", "") or ""),
            countries=self._localizer_countries(meta),
            audio=self._localizer_audio_language(meta),
            subs=await self._subtitles_ptbr(meta),
            imdb_url=imdb_url,
            quality=self._localizer_video_quality(meta),
            container=self._mediainfo_container(general_track, fallback=(getattr(meta, "container", "") or "").upper()),
            video_codec=self._mediainfo_video_codec(meta, video_track),
            video_brate=str(meta.video_bitrate),
            audio_codec=self._mediainfo_audio_codec(meta, audio_track),
            audio_brate=str(meta.audio_bitrate),
            res_str=f"{width}x{height}",
            aspect=self._aspect_ratio(width, height),
            fps_str=f"{meta.frame_rate:.3f} FPS" if meta.frame_rate else "23.976 FPS",
            filesize=self._mediainfo_filesize(meta),
        )

    async def get_additional_checks(self, meta: Meta) -> bool:
        """
        Validate tracker-specific requirements before uploading.

        Args:
            meta (dict[str, Any]): Release metadata.

        Returns:
            bool: True if the release meets all requirements.
        """
        if meta.resolution == "2160p":
            logger.warning(f"[cyan]{self.tracker}:[/cyan] [bold red]4K Resolution (2160p) isn't allowed on this forum.[/bold red]")
            return False

        video = meta.video_codec.upper()
        if not any(c in video for c in ("H264", "H.264", "AVC")):
            logger.warning(f"[cyan]{self.tracker}:[/cyan] [bold red]Only H.264 codec is allowed on this forum.[/bold red]")
            return False

        if not meta.is_disc and meta.container.upper() not in ("MKV", "AVI"):
            logger.warning(f"[cyan]{self.tracker}:[/cyan] [bold red]Only MKV/AVI containers are allowed on this forum.[/bold red]")
            return False

        return True

    async def upload(self, meta: Meta) -> bool:
        """
        Upload a release by creating a forum topic with the torrent as attachment.

        Args:
            meta (dict[str, Any]): Release metadata.

        Returns:
            bool: True if the upload succeeded.
        """
        forum_id = await self.get_forum_id(meta)
        logger.info(f"[cyan]{self.tracker}:[/cyan] [green]Selected subforum:[/green] {forum_id} ")
        await self.common.create_torrent_for_upload(
            meta=meta,
            tracker=self.tracker,
            source_flag=self.source_flag,
            is_public=True,
            public_trackers=self._public_trackers,
        )
        torrent_path = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/[{self.tracker}].torrent"

        # Creates a copy of the torrent with the media filename,
        # this one should be attached to the topic.
        release_name = meta.basename_no_ext or meta.name or meta.uuid
        release_filename = release_name.replace(" ", ".")
        named_torrent_path = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/{release_filename}.torrent"
        shutil.copy2(torrent_path, named_torrent_path)

        if meta.debug:
            topic_title = await self.get_topic_title(meta)
            post_body = await self.generate_description(meta)

            fields = self.get_topic_fields(
                forum_id=forum_id,
                session_id="DEBUG_SESSION",
                auth_key="DEBUG_AUTH",
                attach_post_key="DEBUG_ATTACH",
                topic_title=topic_title,
                post_body=post_body,
            )

            logger.info(f"[cyan]{self.tracker} Request Data:[/cyan]")
            logger.info(Redaction.redact_private_info(fields))

            txt_path = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/MKO_bbcode.txt"
            async with aiofiles.open(txt_path, "w", encoding="utf-8") as f:
                await f.write(f"TITULO: {topic_title}\n\n")
                await f.write(post_body)
            logger.info(f"[cyan]{self.tracker}:[/cyan] [yellow]BBCode saved.[/yellow] {txt_path}")
            meta["tracker_status"][self.tracker]["status_message"] = "Debug mode enabled, not uploading (simulated successfully)"
            return True

        # The UA instantiates a fresh tracker object for the upload step,
        # so credentials must be loaded again here.
        if not await self.validate_credentials(meta):
            meta["tracker_status"][self.tracker]["status_message"] = "data error: Failed to validate credentials before upload."
            return False

        session_id, auth_key, attach_post_key = await self.get_new_post_tokens(forum_id)
        if not auth_key or not attach_post_key:
            meta["tracker_status"][self.tracker]["status_message"] = "data error: Failed to retrieve IPB session tokens."
            return False

        if not await self.upload_attachment(named_torrent_path, session_id, attach_post_key, forum_id):
            meta["tracker_status"][self.tracker]["status_message"] = "data error: Failed to upload .torrent attachment."
            return False

        topic_title = await self.get_topic_title(meta)
        post_body = await self.generate_description(meta)

        topic_url = await self.create_topic(
            forum_id=forum_id,
            session_id=session_id,
            auth_key=auth_key,
            attach_post_key=attach_post_key,
            topic_title=topic_title,
            post_body=post_body,
        )

        if topic_url:
            meta["tracker_status"][self.tracker]["status_message"] = "Upload successful"
            meta["tracker_status"][self.tracker]["torrent_id"] = topic_url
            return True

        meta["tracker_status"][self.tracker]["status_message"] = "data error: Failed creating the forum topic."
        return False
