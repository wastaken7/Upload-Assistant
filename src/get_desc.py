# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import asyncio
import contextlib
import html
import json
import os
import re
import urllib.parse
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import Any, cast
from urllib.parse import ParseResult

import aiofiles
import httpx
import langcodes
from jinja2 import Template
from langcodes.tag_parser import LanguageTagError
from pymediainfo import MediaInfo

from src.bbcode import BBCODE
from src.cogs.redaction import PathAwareEncoder
from src.console import logger
from src.description_review import apply_saved_draft
from src.languages import languages_manager
from src.meta import Meta
from src.screenshot_manifest import files as manifest_files
from src.takescreens import TakeScreensManager
from src.tracker_images import get_tracker_image_collection
from src.trackers.common import Common
from src.uploadscreens import UploadScreensManager


def html_to_bbcode(text: str) -> str:
    """Convert HTML tags to BBCode format."""
    if not text:
        return text

    # Clean up <br> tags adjacent to list item tags to prevent empty lines
    text = re.sub(r"<br\s*/?>\s*</li>", "</li>", text, flags=re.IGNORECASE)
    text = re.sub(r"<li>\s*<br\s*/?>", "<li>", text, flags=re.IGNORECASE)

    # Define HTML to BBCode tag mappings
    html_bbcode_map = [
        (r"<b>(.*?)</b>", r"[b]\1[/b]"),
        (r"<i>(.*?)</i>", r"[i]\1[/i]"),
        (r"<u>(.*?)</u>", r"[u]\1[/u]"),
        (r"<s>(.*?)</s>", r"[s]\1[/s]"),
        (r"<em>(.*?)</em>", r"[i]\1[/i]"),
        (r"<strong>(.*?)</strong>", r"[b]\1[/b]"),
        (r"<strike>(.*?)</strike>", r"[s]\1[/s]"),
        (r"<del>(.*?)</del>", r"[s]\1[/s]"),
        (r"<br\s*/?>", r"\n"),
        (r"<br>", r"\n"),
        (r"<p>(.*?)</p>", r"\1\n"),
        (r"<li>(.*?)</li>", r"* \1\n"),
        (r"<li>", r"* "),
        (r"</li>", r"\n"),
        (r"<ul[^>]*>", r""),
        (r"</ul>", r""),
    ]

    converted_text = text
    for html_pattern, bbcode_replacement in html_bbcode_map:
        converted_text = re.sub(html_pattern, bbcode_replacement, converted_text, flags=re.IGNORECASE | re.DOTALL)

    # Strip any residual HTML tags
    return re.sub(r"<[^>]+>", "", converted_text)


async def gen_desc(
    meta: Meta,
    _takescreens_manager: TakeScreensManager,
    _uploadscreens_manager: UploadScreensManager,
) -> Meta:
    apply_saved_draft(meta)

    def clean_text(text: str) -> str:
        return text.replace("\r\n", "\n").strip()

    description_link = meta.description_link
    description_file = meta.description_file
    scene_nfo = False
    bhd_nfo = False

    description_lines: list[str] = []
    content_written = False

    base_dir = meta.base_dir
    uuid = meta.uuid
    specified_dir = Path(base_dir) / "tmp" / uuid
    source_dir = Path(meta.path or "")

    if meta.description_override:
        description_lines.append(clean_text(meta.description_override))
        content_written = True
    elif meta.description_template:
        try:
            template_path = f"{meta.base_dir}/data/templates/{meta.description_template}.txt"
            async with aiofiles.open(template_path, encoding="utf-8") as f:
                template = Template(await f.read())
            template_desc = template.render(meta)
            cleaned_content = clean_text(template_desc)
            if cleaned_content:
                if len(template_desc) > 0:
                    description_lines.append(cleaned_content)
                    meta.description_template_content = cleaned_content
                content_written = True
        except FileNotFoundError:
            logger.info(f"[ERROR] Template '{meta.description_template}' not found.")
    if meta.nfo:
        logger.debug(f"specified_dir_path: {specified_dir}")
        logger.debug(f"sourcedir_path: {source_dir}")
        if "auto_nfo" in meta and meta.auto_nfo is True:
            nfo_files = sorted(str(p) for p in specified_dir.glob("*.nfo"))
            scene_nfo = True
        elif "bhd_nfo" in meta and meta.bhd_nfo is True:
            nfo_files = sorted(str(p) for p in specified_dir.glob("*.nfo"))
            bhd_nfo = True
        else:
            nfo_files = sorted(str(p) for p in source_dir.glob("*.nfo"))
        if not nfo_files:
            logger.info("NFO was set but no nfo file was found")
            if not content_written:
                description_lines.append("")
            meta.description = "\n".join(description_lines).strip()
            meta.saved_description = bool(meta.description)
            return meta

        if nfo_files:
            nfo = nfo_files[0]
            try:
                async with aiofiles.open(nfo, encoding="utf-8") as nfo_file:
                    nfo_content = await nfo_file.read()
                logger.debug("NFO content read with utf-8 encoding.")
            except UnicodeDecodeError:
                logger.debug("utf-8 decoding failed, trying latin1.")
                async with aiofiles.open(nfo, encoding="latin1") as nfo_file:
                    nfo_content = await nfo_file.read()

            if not content_written:
                if scene_nfo is True:
                    description_lines.append(f"[center][spoiler=Scene NFO:][code]{nfo_content}[/code][/spoiler][/center]")
                elif bhd_nfo is True:
                    description_lines.append(f"[center][spoiler=FraMeSToR NFO:][code]{nfo_content}[/code][/spoiler][/center]")
                else:
                    description_lines.append(f"[code]{nfo_content}[/code]")

                content_written = True

            nfo_content_utf8 = nfo_content.encode("utf-8", "ignore").decode("utf-8")
            meta.description_nfo_content = nfo_content_utf8

    if description_link:
        try:
            parsed: ParseResult = urllib.parse.urlparse(description_link.replace("/raw/", "/") or "")
            split = os.path.split(parsed.path)
            raw = parsed._replace(path=f"{split[0]}/raw/{split[1]}" if split[0] != "/" else f"/raw{parsed.path}")
            raw_url = urllib.parse.urlunparse(raw)
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.get(raw_url)
            description_link_content = response.text
            cleaned_content = clean_text(description_link_content)
            if cleaned_content and "Not Found" not in cleaned_content:
                if not content_written:
                    description_lines.append(cleaned_content)
                meta.description_link_content = cleaned_content
                content_written = True
            elif cleaned_content and "Not Found" in cleaned_content:
                logger.error("Description link returned 'Not Found'")
        except Exception as e:
            logger.info(f"[ERROR] Failed to fetch description from link: {e}")
            raise e

    if description_file and Path(description_file).is_file():
        async with aiofiles.open(description_file, encoding="utf-8") as f:
            file_content = await f.read()
        cleaned_content = clean_text(file_content)
        if cleaned_content:
            if not content_written:
                description_lines.append(cleaned_content)
            meta.description_file_content = cleaned_content
            content_written = True

    if not content_written:
        description_text = meta.description.strip() if meta.description else ""
        if description_text:
            description_lines.append(description_text)
            content_written = True

    if not meta.skip_gen_desc and not content_written:
        description_text = meta.description.strip() if meta.description else ""
        if description_text:
            description_lines = [description_text]
            content_written = True

    meta.description = "\n".join(description_lines).strip()
    meta.saved_description = bool(meta.description)

    if meta.description in ("None", "", " "):
        meta.description = ""

    return meta


class DescriptionBuilder:
    def __init__(self, tracker: str, config: dict[str, Any]):
        self.config: dict[str, Any] = config
        self.common = Common(config)
        self.tracker: str = tracker
        self.takescreens_manager = TakeScreensManager(config)
        self.uploadscreens_manager = UploadScreensManager(config)

        trackers_config = self.config.get("TRACKERS")
        if not isinstance(trackers_config, dict):
            raise KeyError("Missing 'TRACKERS' section in config")
        trackers_config_map = cast(dict[str, Any], trackers_config)

        tracker_cfg = trackers_config_map.get(tracker)
        if tracker_cfg is None:
            available = list(trackers_config_map.keys())
            raise KeyError(f"Missing tracker config for '{tracker}'; available trackers: {available}")

        self.tracker_config: dict[str, Any] = cast(dict[str, Any], tracker_cfg) if isinstance(tracker_cfg, dict) else {}
        self.parser = self.common.parser

    def _get_bool_config(self, key: str, default: bool = False) -> bool:
        """Helper to get a boolean config value safely. Falls back to DEFAULT or default if invalid/empty."""
        val = self.tracker_config.get(key)
        if val is None or val == "":
            val = self.config["DEFAULT"].get(key, default)

        if isinstance(val, bool):
            return val
        if isinstance(val, str):
            val_lower = val.lower().strip()
            if val_lower in ("true", "1", "yes", "on"):
                return True
            if val_lower in ("false", "0", "no", "off", ""):
                return False
        try:
            return bool(int(val))
        except ValueError, TypeError:
            return default

    def _get_int_config(self, key: str, default: Any = 0) -> int:
        """Helper to get an integer config value safely. Falls back to DEFAULT or default if invalid/empty."""
        val = self.tracker_config.get(key)
        if val is None or val == "":
            val = self.config["DEFAULT"].get(key, default)

        try:
            return int(val)
        except ValueError, TypeError:
            try:
                return int(default)
            except ValueError, TypeError:
                return 0

    def _get_str_config(self, key: str, default: str = "") -> str:
        """Helper to get a string config value safely. Empty string is returned if it is a valid override."""
        if key in self.tracker_config:
            val = self.tracker_config[key]
            if val is not None:
                return str(val)
        val = self.config["DEFAULT"].get(key, default)
        return str(val) if val is not None else default

    async def get_custom_header(self) -> str:
        """Returns a custom header if configured."""
        try:
            custom_description_header = self._get_str_config("custom_description_header", "")
            if custom_description_header:
                return custom_description_header
        except Exception as e:
            logger.warning(f"[yellow]Warning: Error setting custom description header: {e!s}[/yellow]")

        return ""

    async def get_tonemapped_header(self, meta: Meta) -> str:
        try:
            tonemapped_description_header = self._get_str_config("tonemapped_header", "")
            if tonemapped_description_header and meta.tonemapped:
                return tonemapped_description_header
        except Exception as e:
            logger.warning(f"[yellow]Warning: Error setting tonemapped header: {e!s}[/yellow]")
        return ""

    async def get_logo_section(self, meta: Meta) -> tuple[str, str]:
        """Returns the logo URL and size if applicable."""
        logo, logo_size = "", ""
        try:
            if not self._get_bool_config("add_logo", False):
                return logo, logo_size

            if self.tracker in ("BJSHARE", "ANTHELION", "GREATPOSTERWALL", "BRASILTRACKER", "FUNFILE", "HDSPACE", "HDTORRENTS", "SPEEDAPP"):
                logo_resize_url = meta.tmdb_logo
                if logo_resize_url:
                    if logo_resize_url.endswith(".svg"):
                        logo_resize_url = logo_resize_url.replace(".svg", ".png")
                    logo = f"https://image.tmdb.org/t/p/w300/{logo_resize_url}"
                    logo_size = "300"
                    return logo, logo_size

            logo = meta.logo
            logo_size = str(self._get_int_config("logo_size", 300))

            if logo:
                return logo, logo_size
        except Exception as e:
            logger.warning(f"[yellow]Warning: Error getting logo section: {e!s}[/yellow]")

        return logo, logo_size

    async def get_tv_info(self, meta: Meta) -> tuple[str, str]:
        title: str = ""
        overview: str = ""
        try:
            if not self._get_bool_config("episode_overview", False) or meta.category != "TV":
                return title, overview

            if self.tracker in ("CAPYBARABR", "BJSHARE", "BRASILTRACKER", "LOCADORA", "SAMARITANO"):
                episode_tmdb_data = meta.episode_tmdb_data
                title = episode_tmdb_data.get("name", "")
                overview = episode_tmdb_data.get("overview", "")
                return title, overview

            tvmaze_episode_data = meta.tvmaze_episode_data

            season_name = tvmaze_episode_data.get("season_name", "") or meta.tvdb_season_name
            season_number = meta.season
            episode_number = meta.episode
            overview = tvmaze_episode_data.get("overview", "") or meta.overview_meta

            # Convert HTML tags to BBCode
            if overview:
                overview = html_to_bbcode(overview)

            episode_name = tvmaze_episode_data.get("episode_name", "")
            episode_title = meta.auto_episode_title or (episode_name if (not episode_name.lower().startswith("episode") and "tba" not in episode_name.lower()) else "")

            title = ""
            if season_name:
                title = f"{season_name}"
                if season_number:
                    title += f" - {season_number}{episode_number}"

            if episode_title:
                if title:
                    title += ": "
                title += f"{episode_title}"

        except Exception as e:
            logger.warning(f"[yellow]Warning: Error getting TV info: {e!s}[/yellow]")

        return title, overview

    async def get_mediainfo_section(self, meta: Meta) -> str:
        """Returns the mediainfo section, using a cache file if available."""
        if meta.is_disc == "BDMV" or meta.category in ("GAME", "BOOK", "MUSIC"):
            return ""

        if self._get_bool_config("full_mediainfo", True) or meta.is_disc:
            mi_path = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/MEDIAINFO_CLEANPATH.txt"
            if await self.common.path_exists(mi_path):
                async with aiofiles.open(mi_path, encoding="utf-8") as mi:
                    return await mi.read()

        cache_file_dir = Path(meta.base_dir) / "tmp" / meta.uuid
        cache_file_path = Path(cache_file_dir) / "MEDIAINFO_SHORT.txt"

        file_exists = Path(cache_file_path).exists()
        file_size = Path(cache_file_path).stat().st_size if file_exists else 0

        if file_exists and file_size > 0:
            with contextlib.suppress(Exception):
                async with aiofiles.open(cache_file_path, encoding="utf-8") as f:
                    return await f.read()

        video_file = meta.filelist[0]

        if meta.mediainfo:
            media_info_content = self.format_short_mediainfo_json(meta.mediainfo, video_file)
            if media_info_content:
                with contextlib.suppress(Exception):
                    await self.common.makedirs(str(cache_file_dir))
                    async with aiofiles.open(cache_file_path, mode="w", encoding="utf-8") as f:
                        await f.write(media_info_content)
                return media_info_content

        return ""

    @staticmethod
    def format_short_mediainfo_json(mediainfo: dict[str, Any] | None, video_file: str = "") -> str:
        """Render the short MediaInfo section from meta.mediainfo."""
        if not mediainfo:
            return ""
        raw_tracks = mediainfo.get("media", {}).get("track", [])
        if not isinstance(raw_tracks, list):
            return ""
        tracks = [track for track in raw_tracks if isinstance(track, dict)]

        def value(track: dict[str, Any], key: str) -> str:
            field = track.get(key, "")
            return field.strip() if isinstance(field, str) else ""

        def format_duration(seconds: str) -> str:
            try:
                milliseconds = int((Decimal(seconds) * 1000).to_integral_value(rounding=ROUND_HALF_UP))
            except InvalidOperation, ValueError:
                return ""
            hours, milliseconds = divmod(milliseconds, 3_600_000)
            minutes, milliseconds = divmod(milliseconds, 60_000)
            seconds, milliseconds = divmod(milliseconds, 1000)
            return f"{hours:02}:{minutes:02}:{seconds:02}.{milliseconds:03}"

        def format_size(bytes_value: str) -> str:
            try:
                gibibytes = Decimal(bytes_value) / (1024**3)
            except InvalidOperation:
                return ""
            precision = ".1f" if gibibytes >= 10 else ".2f"
            return f"{gibibytes:{precision}} GiB"

        def format_bitrate(bits_per_second: str) -> str:
            try:
                bitrate = Decimal(bits_per_second)
            except InvalidOperation:
                return ""
            if bitrate >= 10_000_000:
                return f"{bitrate / 1_000_000:.1f} Mb/s"
            return f"{int((bitrate / 1000).to_integral_value(rounding=ROUND_HALF_UP)):,}".replace(",", " ") + " kb/s"

        def format_sampling_rate(hertz: str) -> str:
            try:
                return f"{Decimal(hertz) / 1000:.1f} kHz"
            except InvalidOperation:
                return ""

        def language_name(language: str) -> str:
            if not language:
                return ""
            try:
                parsed = langcodes.Language.get(language)
                name = parsed.language_name("en")
                return f"{name} ({parsed.territory})" if parsed.territory else name
            except LanguageTagError:
                return language

        general = next((track for track in tracks if value(track, "@type") == "General"), None)
        if general is None:
            return ""

        filename = Path(value(general, "CompleteName") or video_file).stem
        output = [
            filename,
            "",
            "---GENERAL----",
            f"Size...........: {format_size(value(general, 'FileSize'))}",
            f"Container......: {value(general, 'Format')}",
            f"Duration.......: {format_duration(value(general, 'Duration'))}",
            "",
        ]

        for video in (track for track in tracks if value(track, "@type") == "Video"):
            codec = value(video, "Format")
            codec += ", " + value(video, "Encoded_Library") if value(video, "Encoded_Library") else ""
            codec += ", " + value(video, "HDR_Format_String") if value(video, "HDR_Format_String") else ""
            codec += ", " + value(video, "transfer_characteristics") if value(video, "transfer_characteristics") else ""
            output.extend(
                [
                    "---VIDEO----",
                    f"Codec..........: {codec}",
                    f"Resolution.....: {value(video, 'Width')}x{value(video, 'Height')}",
                    f"Bit rate.......: {format_bitrate(value(video, 'BitRate'))}",
                    f"Frame rate.....: {value(video, 'FrameRate')} fps",
                    "",
                ]
            )

        for audio in (track for track in tracks if value(track, "@type") == "Audio"):
            title = value(audio, "Title")
            output.extend(
                [
                    "---AUDIO----",
                    f"Format.........: {value(audio, 'Format_Commercial_IfAny') or value(audio, 'Format')}",
                    f"Channels.......: {value(audio, 'Channels')} channel{'s' if value(audio, 'Channels') != '1' else ''}",
                    f"Sample rate....: {format_sampling_rate(value(audio, 'SamplingRate'))}",
                    f"Bit rate.......: {format_bitrate(value(audio, 'BitRate'))}",
                    f"Language.......: {language_name(value(audio, 'Language'))}{f' ({title})' if title else ''}",
                    "",
                ]
            )

        for index, text in enumerate(track for track in tracks if value(track, "@type") == "Text"):
            if index == 0:
                output.append("---SUBTITLES---")
            title = value(text, "Title")
            output.append(f"Language.......: {language_name(value(text, 'Language'))}{f' ({title})' if title else ''}, {value(text, 'Format')}")

        return "\n".join(output).rstrip() + "\n"

    async def get_bdinfo_section(self, meta: Meta) -> str:
        """Returns the bdinfo section if applicable."""
        try:
            if meta.is_disc == "BDMV":
                bdinfo_sections: list[str] = []
                if meta.discs:
                    for disc in meta.discs:
                        file_info = disc.get("summary", "")
                        if file_info:
                            bdinfo_sections.append(file_info)
                return "\n\n".join(bdinfo_sections)
        except Exception as e:
            logger.warning(f"[yellow]Warning: Error getting bdinfo section: {e!s}[/yellow]")

        return ""

    async def screenshot_header(self) -> str:
        """Returns the screenshot header if applicable."""
        try:
            screenheader = self._get_str_config("screenshot_header", "")
            if screenheader:
                return screenheader
        except Exception as e:
            logger.warning(f"[yellow]Warning: Error getting screenshot header: {e!s}[/yellow]")

        return ""

    async def menu_screenshot_header(self, meta: Meta) -> str:
        """Returns the screenshot header for menus if applicable."""
        try:
            menu_images = get_tracker_image_collection(meta, self.tracker, "menu_images")
            if meta.is_disc and menu_images:
                disc_menu_header = self._get_str_config("disc_menu_header", "")
                if disc_menu_header:
                    return disc_menu_header
        except Exception as e:
            logger.warning(f"[yellow]Warning: Error getting menus screenshot header: {e!s}[/yellow]")

        return ""

    async def get_user_description(self, meta: Meta) -> str:
        """Returns the user-provided description (file or link)"""
        try:
            if meta.description_override:
                return ""
            description_file_content = meta.description_file_content.strip()
            description_link_content = meta.description_link_content.strip()

            if description_file_content or description_link_content:
                if description_file_content:
                    return description_file_content
                if description_link_content:
                    return description_link_content
        except Exception as e:
            logger.warning(f"[yellow]Warning: Error getting user description: {e!s}[/yellow]")

        return ""

    async def get_custom_signature(self) -> str:
        custom_signature: str = ""
        try:
            custom_signature = self._get_str_config("custom_signature", "")
        except Exception as e:
            logger.warning(f"[yellow]Warning: Error setting custom signature: {e!s}[/yellow]")

        return custom_signature

    async def get_bluray_section(self, meta: Meta) -> tuple[str, str]:
        release_url: str = ""
        cover_list: list[str] = []
        cover_images: str = ""

        try:
            cover_size = self._get_int_config("bluray_image_size", 250)
            bluray_link = self._get_bool_config("add_bluray_link", False)

            if meta.is_disc in ["BDMV", "DVD"] and bluray_link and meta.release_url:
                release_url = meta.release_url

            cover_data = meta.hosted_artwork
            if not cover_data and await self.common.path_exists(f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/covers.json"):
                try:
                    async with aiofiles.open(f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/covers.json", encoding="utf-8") as f:
                        cover_data = json.loads(await f.read())
                except Exception:
                    cover_data = None

            use_bluray_images = self._get_bool_config("use_bluray_images", False)
            if meta.is_disc in ["BDMV", "DVD"] and use_bluray_images and cover_data:
                for img_data in cover_data:
                    web_url = img_data.get("web_url", "")
                    raw_url = img_data.get("raw_url", "")

                    if self.tracker == "TORRENTLEECH":
                        cover_list.append(f"""<a href="{web_url}"><img src="{raw_url}" style="max-width: {cover_size}px;"></a>  """)
                    elif self.tracker == "HDTORRENTS":
                        cover_list.append(f"<a href='{raw_url}'><img src='{web_url}' height=137></a> ")
                    else:
                        cover_list.append(f"[url={web_url}][img={cover_size}]{raw_url}[/img][/url]")

            if cover_list:
                cover_images = "".join(cover_list)

        except Exception as e:
            logger.warning(f"[yellow]Warning: Error getting bluray section: {e!s}[/yellow]")

        return release_url, cover_images

    async def get_audio_spectrogram_section(self, meta: Meta) -> str:
        """Returns the audio spectrogram section if applicable."""
        try:
            add_audio_spectrogram = self._get_bool_config("add_audio_spectrogram", False)
            add_spec = meta.audio_spectrogram or meta.audio_spectrogram_tracks or add_audio_spectrogram
            if not add_spec:
                return ""

            spectrograms_images = get_tracker_image_collection(meta, self.tracker, "spectrograms_images")
            if not spectrograms_images:
                return ""
            audio_spectrogram_header = self._get_str_config("audio_spectrogram_header", "[center][b]Audio Spectrogram[/b][/center]")
            desc_parts: list[str] = [audio_spectrogram_header] if audio_spectrogram_header is not None else []
            desc_parts.append("\n[center]")
            screens_per_row = await self.get_screens_per_row()
            for img_index, spec_img in enumerate(spectrograms_images):
                if isinstance(spec_img, dict):
                    web_url = spec_img.get("web_url")
                    raw_url = spec_img.get("raw_url")
                    img_url = spec_img.get("img_url", raw_url) or ""
                    if web_url and raw_url:
                        desc_parts.append(self.format_screenshot(web_url, raw_url, img_url))
                        if screens_per_row and (img_index + 1) % screens_per_row == 0:
                            desc_parts.append("\n")
            desc_parts.append("[/center]\n")
            return "".join(desc_parts)
        except Exception as e:
            logger.warning(f"[yellow]Warning: Error getting audio spectrogram section: {e!s}[/yellow]")
        return ""

    def _build_book_desc_section(self, meta: Meta, header_size: int = 0, table: bool = True, underline: bool = False, bullet: str = "") -> str:
        """Build the BBCode table or list for BOOK-category uploads."""
        if self.tracker in ("TORRENTLEECH", "IMMORTALSEED", "IPTORRENTS", "SPEEDAPP"):
            table = False
            header_size = -1
        elif self.tracker in ("BJSHARE", "BRASILTRACKER", "AMIGOSSHARE"):
            if not header_size:
                header_size = 3
            if self.tracker == "AMIGOSSHARE":
                table = False

        header = "[h2]" if not header_size else f"[size={header_size}][b]"
        header_end = "[/h2]" if not header_size else "[/b][/size]\n"

        asin = meta.asin
        author = meta.author
        book_translator = meta.book_translator
        edition = meta.edition
        isbn = meta.isbn
        narrator = meta.narrator
        overview = meta.overview
        publisher = meta.publisher
        year = str(meta.year) if meta.year is not None else ""

        use_pt_br = self.tracker in ("AMIGOSSHARE", "BRASILTRACKER", "CAPYBARABR", "SAMARITANO", "BJSHARE")

        str_asin = "ASIN"
        str_author = "Author" if not use_pt_br else "Autor"
        str_avg_bitrate = "Average Bitrate" if not use_pt_br else "Bitrate Médio"
        str_book_translator = "Translator" if not use_pt_br else "Tradutor"
        str_duration = "Duration" if not use_pt_br else "Duração"
        str_edition = "Edition" if not use_pt_br else "Edição"
        str_isbn = "ISBN"
        str_narrator = "Narrator" if not use_pt_br else "Narrador"
        str_overview = "Overview" if not use_pt_br else "Visão Geral"
        str_publisher = "Publisher" if not use_pt_br else "Editora"
        str_technical_details = "Technical Details" if not use_pt_br else "Detalhes Técnicos"
        str_year = "Release Year" if not use_pt_br else "Ano de Lançamento"

        if overview:
            overview = html_to_bbcode(overview)
            overview = re.sub(r"<[^>]+>", "", overview).strip()

        # Collect key-value pairs
        fields: list[tuple[str, str]] = []
        if author:
            fields.append((str_author, author))
        if book_translator:
            fields.append((str_book_translator, book_translator))
        if narrator:
            fields.append((str_narrator, narrator))
        if publisher:
            fields.append((str_publisher, publisher))
        if isbn:
            fields.append((str_isbn, isbn))
        if asin:
            fields.append((str_asin, asin))
        if edition:
            fields.append((str_edition, edition))
        if year:
            fields.append((str_year, year))
        if meta.audiobook:
            audiobook_duration_formatted = meta.audiobook_duration_formatted
            avg_bitrate = meta.audiobook_bitrate
            if audiobook_duration_formatted:
                fields.append((str_duration, audiobook_duration_formatted))
            if avg_bitrate:
                fields.append((str_avg_bitrate, f"{avg_bitrate} kbps"))

        if not (fields or overview):
            return ""

        if table:
            final_book_parts: list[str] = []
            if underline:
                header = "[b][u]"
                header_end = "[/u][/b]\n"
            elif header_size == -1:
                header = "[b]"
                header_end = "[/b]\n"

            if fields:
                final_book_parts.append(f"{header}{str_technical_details}{header_end}")
                table_lines = ["[table]"]
                for label, val in fields:
                    table_lines.append(f"[tr][td][b]{label}[/b][/td][td]{val}[/td][/tr]")
                table_lines.append("[/table]")
                final_book_parts.append("\n".join(table_lines))

            if meta.epubmeta_output:
                final_book_parts.append(f"[spoiler=EPUB Metadata][code]{meta.epubmeta_output}[/code][/spoiler]")

            if overview:
                final_book_parts.append(f"{header}{str_overview}{header_end}\n{overview}")

            return "\n\n".join(part for part in final_book_parts if part.strip())
        book_parts = []
        prefix = f"{bullet} " if bullet else ""
        for label, val in fields:
            book_parts.append(f"{prefix}[b]{label}:[/b] {val}")

        final_book_parts = []
        if underline:
            header = "[b][u]"
            header_end = "[/u][/b]\n"
        elif header_size == -1:
            header = "[b]"
            header_end = "[/b]\n"
        else:
            header = "[h2]" if not header_size else f"[size={header_size}][b]"
            header_end = "[/h2]" if not header_size else "[/b][/size]\n"

        if book_parts:
            final_book_parts.append(f"{header}{str_technical_details}{header_end}" + "\n".join(book_parts))

        if overview:
            final_book_parts.append(f"{header}{str_overview}{header_end}{overview}")

        return "\n\n".join(final_book_parts)

    def _build_game_desc_section(self, meta: Meta, header_size: int = 0, table: bool = True) -> str:
        """Build the beautiful BBCode layout for GAME-category uploads."""
        if meta.category != "GAME":
            return ""

        game_parts: list[str] = []

        if self.tracker == "TORRENTLEECH" and not header_size:
            header_size = 1
        elif self.tracker in ("BJSHARE", "BRASILTRACKER") and not header_size:
            header_size = 3

        header = "[h2]" if not header_size else f"[size={header_size}][b]"
        header_end = "[/h2]" if not header_size else "[/b][/size]\n"

        use_pt_br = self.tracker in ("AMIGOSSHARE", "BRASILTRACKER", "CAPYBARABR", "SAMARITANO", "BJSHARE")
        str_technical_details = "Technical Details" if not use_pt_br else "Detalhes Técnicos"
        str_overview = "Overview" if not use_pt_br else "Visão Geral"
        str_platform = "Platform" if not use_pt_br else "Plataforma"
        str_version = "Version" if not use_pt_br else "Versão"
        str_genre = "Genre" if not use_pt_br else "Gênero"
        str_developer = "Developer" if not use_pt_br else "Desenvolvedor"
        str_publisher = "Publisher" if not use_pt_br else "Distribuidora"
        str_system_requirements = "System Requirements" if not use_pt_br else "Requisitos do Sistema"
        str_minimum = "Minimum" if not use_pt_br else "Mínimo"
        str_recommended = "Recommended" if not use_pt_br else "Recomendado"
        str_official_supported_languages = "Officially Supported Languages" if not use_pt_br else "Idiomas Oficialmente Suportados"
        str_language = "Language" if not use_pt_br else "Idioma"
        str_support = "Support" if not use_pt_br else "Suporte"

        # 1. Technical Details
        fields: list[tuple[str, str]] = []
        if meta.platform:
            fields.append((str_platform, meta.platform))
        if meta.game_version:
            fields.append((str_version, meta.game_version))
        if meta.genres:
            fields.append((str_genre, ", ".join(meta.genres)))
        if meta.developer:
            fields.append((str_developer, meta.developer))
        if meta.publisher:
            fields.append((str_publisher, meta.publisher))
        if meta.steam_url:
            fields.append(("Steam", f"[url]{meta.steam_url}[/url]"))

        if fields:
            details_lines = []
            details_lines.append(f"{header}{str_technical_details}{header_end}")
            if table:
                table_lines = ["[table]"]
                for label, val in fields:
                    table_lines.append(f"[tr][td][b]{label}[/b][/td][td]{val}[/td][/tr]")
                table_lines.append("[/table]")
                details_lines.append("\n".join(table_lines))
            else:
                for label, val in fields:
                    details_lines.append(f"[b]{label}[/b] {val}")
            game_parts.append("\n".join(details_lines))

        # 2. Overview Section
        overview_text = ""
        localized_overviews = meta.localized_overviews
        pt_br_overview = localized_overviews.get("brazilian", "") if isinstance(localized_overviews, dict) else ""
        overview = meta.overview if not use_pt_br else pt_br_overview

        # Strip HTML tags and convert to BBCode if present
        if overview:
            overview = html_to_bbcode(str(overview))
            overview = re.sub(r"<[^>]+>", "", overview).strip()

        if overview:
            overview_text = f"\n{header}{str_overview}{header_end}\n{overview}\n"

        if overview_text:
            game_parts.append(overview_text)

        # 3. System Requirements Section
        req_min = meta.requirements_minimum
        req_rec = meta.requirements_recommended

        if req_min or req_rec:
            import html

            header_title = f"{str_system_requirements}"
            game_parts.append(f"{header}{header_title}{header_end}")

            col_min_header = f"{str_minimum}"
            col_rec_header = f"{str_recommended}"

            clean_min = ""
            if req_min:
                clean_min = html_to_bbcode(req_min)
                clean_min = html.unescape(clean_min)
                clean_min = re.sub(r"<[^>]+>", "", clean_min).strip()
                clean_min = re.sub(r"^\[b\](Minimum|Mínimo):\[/b\]\s*", "", clean_min, flags=re.IGNORECASE)

            clean_rec = ""
            if req_rec:
                clean_rec = html_to_bbcode(req_rec)
                clean_rec = html.unescape(clean_rec)
                clean_rec = re.sub(r"<[^>]+>", "", clean_rec).strip()
                clean_rec = re.sub(r"^\[b\](Recommended|Recomendado):\[/b\]\s*", "", clean_rec, flags=re.IGNORECASE)

            if table:
                clean_min = clean_min or "-"
                clean_rec = clean_rec or "-"

                table_lines = ["[table]"]
                table_lines.append(f"[tr][td][b]{col_min_header}[/b][/td][td][b]{col_rec_header}[/b][/td][/tr]")
                table_lines.append(f"[tr][td]{clean_min}[/td][td]{clean_rec}[/td][/tr]")
                table_lines.append("[/table]")
                game_parts.append("\n".join(table_lines))
            else:
                # Simple BBCode format without table
                simple_lines = []
                if clean_min:
                    simple_lines.append(f"[b]{col_min_header}[/b] {clean_min}")
                if clean_rec:
                    simple_lines.append(f"\n[b]{col_rec_header}[/b] {clean_rec}")
                game_parts.append("\n".join(simple_lines))

        # 4. Supported Languages
        languages = meta.languages
        if languages and isinstance(languages, dict):
            if table:
                table_rows = []
                table_rows.append(f"[tr][td][b]{str_language}[/b][/td][td][b]{str_support}[/b][/td][/tr]")

                for lang, support in sorted(languages.items()):
                    lang = (lang or "").strip() or "-"
                    support_str = ", ".join(support).strip() or "-"

                    table_rows.append(f"[tr][td]{lang}[/td][td]{support_str}[/td][/tr]")

                table_text = "\n".join(table_rows)
                spoiler_str = f"{header}{str_official_supported_languages}{header_end}\n[table]\n{table_text}\n[/table]\n"
                game_parts.append(spoiler_str)
            else:
                # Simple BBCode format without table
                simple_lang_lines = []
                for lang, support in sorted(languages.items()):
                    support_str = ", ".join(support)
                    simple_lang_lines.append(f"[b]{lang}[/b]: {support_str}")
                simple_section = f"{header}{str_official_supported_languages}{header_end}\n" + "\n".join(simple_lang_lines) + "\n"
                game_parts.append(simple_section)

        return "\n".join(part for part in game_parts if part.strip())

    def _build_music_desc_section(self, meta: Meta, header_size: int = 0, table: bool = True) -> str:
        """Build a tracker-neutral BBCode summary for MUSIC-category uploads."""
        if meta.category != "MUSIC" or not isinstance(meta.music_release, dict):
            return ""

        if self.tracker in ("TORRENTLEECH", "IMMORTALSEED", "IPTORRENTS", "SPEEDAPP"):
            table = False

        release = meta.music_release
        fields_data = release.get("fields", {})
        tracks = release.get("tracks", [])
        external_ids = release.get("external_ids", {})
        if not isinstance(fields_data, dict):
            fields_data = {}
        if not isinstance(tracks, list):
            tracks = []
        if not isinstance(external_ids, dict):
            external_ids = {}
        if not fields_data and not tracks and not external_ids:
            return ""

        if self.tracker == "TORRENTLEECH" and not header_size:
            header_size = 1
        elif self.tracker in ("BJSHARE", "BRASILTRACKER", "SPEEDAPP") and not header_size:
            header_size = 3

        header = "[h2]" if not header_size else f"[size={header_size}][b]"
        header_end = "[/h2]" if not header_size else "[/b][/size]\n"
        use_pt_br = self.tracker in ("AMIGOSSHARE", "BRASILTRACKER", "CAPYBARABR", "SAMARITANO", "BJSHARE")

        def value(name: str, fallback: Any = "") -> Any:
            """Return a populated normalized release field or its fallback."""
            item = fields_data.get(name, {})
            if isinstance(item, dict) and item.get("value") not in (None, "", [], {}):
                return item["value"]
            return fallback

        def display(item: Any) -> str:
            """Format a release field for human-readable BBCode output."""
            if isinstance(item, list):
                return ", ".join(str(part) for part in item if str(part).strip())
            return str(item).strip() if item not in (None, "") else ""

        def technical_values(name: str, formatter: Any = str) -> str:
            """Format unique valid technical values from the release tracks."""
            formatted_values: dict[Any, str] = {}
            for track in tracks:
                if not isinstance(track, dict):
                    continue
                item = track.get(name)
                if item in (None, ""):
                    continue
                try:
                    hash(item)
                    formatted = display(formatter(item))
                except TypeError, ValueError, OverflowError:
                    continue
                if formatted:
                    formatted_values[item] = formatted
            return ", ".join(formatted_values[item] for item in sorted(formatted_values, key=str))

        text = {
            "details": "Music Details" if not use_pt_br else "Detalhes da Música",
            "artist": "Artist" if not use_pt_br else "Artista",
            "album": "Album" if not use_pt_br else "Álbum",
            "year": "Original Release Year" if not use_pt_br else "Ano de Lançamento Original",
            "release_year": "Release Year" if not use_pt_br else "Ano desta Edição",
            "edition": "Edition" if not use_pt_br else "Edição",
            "edition_year": "Edition Year" if not use_pt_br else "Ano da Edição",
            "type": "Release Type" if not use_pt_br else "Tipo de Lançamento",
            "media": "Media" if not use_pt_br else "Mídia",
            "label": "Label" if not use_pt_br else "Gravadora",
            "catalogue": "Catalogue Number" if not use_pt_br else "Número de Catálogo",
            "genres": "Genres" if not use_pt_br else "Gêneros",
            "tracks": "Tracks" if not use_pt_br else "Faixas",
            "discs": "Discs" if not use_pt_br else "Discos",
            "format": "Format" if not use_pt_br else "Formato",
            "codec": "Codec",
            "bit_depth": "Bit Depth" if not use_pt_br else "Profundidade de Bits",
            "sample_rate": "Sample Rate" if not use_pt_br else "Taxa de Amostragem",
            "channels": "Channels" if not use_pt_br else "Canais",
            "bitrate": "Bitrate",
            "external_ids": "External IDs" if not use_pt_br else "IDs Externos",
        }

        def musicbrainz_link(kind: str, identifier: Any) -> str:
            """Return a safe MusicBrainz BBCode link for a canonical UUID."""
            identifier = str(identifier or "").strip()
            if not re.fullmatch(r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}", identifier, re.IGNORECASE):
                return ""
            return f"[url=https://musicbrainz.org/{kind}/{identifier}]{identifier}[/url]"

        def discogs_link(kind: str, identifier: Any) -> str:
            """Return a safe Discogs BBCode link for a known release/master ID."""
            raw_identifier = str(identifier or "").strip()
            match = re.fullmatch(
                rf"(?:https?://(?:www\.)?discogs\.com/)?{kind}(?:/|:)(\d+)(?:-[^/?#]+)?/?(?:[?#].*)?",
                raw_identifier,
                re.IGNORECASE,
            )
            numeric_identifier = match.group(1) if match else raw_identifier if raw_identifier.isdecimal() else ""
            return f"[url=https://www.discogs.com/{kind}/{numeric_identifier}]{numeric_identifier}[/url]" if numeric_identifier else ""

        external_id_links = [
            ("MusicBrainz Release", musicbrainz_link("release", external_ids.get("musicbrainz_release"))),
            ("MusicBrainz Release Group", musicbrainz_link("release-group", external_ids.get("musicbrainz_release_group"))),
            ("Discogs Release", discogs_link("release", external_ids.get("discogs_release"))),
            ("Discogs Master", discogs_link("master", external_ids.get("discogs_master"))),
        ]
        external_id_links = [f"{label}: {link}" for label, link in external_id_links if link]

        music_fields = [
            (text["artist"], display(value("artists", value("artist", meta.artist)))),
            (text["album"], display(value("album", meta.title))),
            (text["year"], display(value("year", meta.year))),
            (text["release_year"], display(value("release_year"))),
            (text["edition"], display(value("edition"))),
            (text["edition_year"], display(value("edition_year"))),
            (text["type"], display(value("release_type"))),
            (text["media"], display(value("media", meta.source))),
            (text["label"], display(value("release_label", value("label")))),
            (text["catalogue"], display(value("release_catalogue_number"))),
            (text["genres"], display(value("genres"))),
            (text["tracks"], display(value("track_count", len(tracks)))),
            (text["discs"], display(value("disc_count", 1))),
            (text["format"], display(value("format", technical_values("format")))),
            (text["codec"], technical_values("codec")),
            (text["bit_depth"], technical_values("bit_depth", lambda item: f"{item}-bit")),
            (text["sample_rate"], technical_values("sample_rate", lambda item: f"{int(item) / 1000:g} kHz")),
            (text["channels"], technical_values("channels", lambda item: {1: "Mono", 2: "Stereo"}.get(int(item), f"{item} channels"))),
            (text["bitrate"], technical_values("bitrate", lambda item: f"{round(int(item) / 1000)} kbps")),
            (text["external_ids"], ", ".join(external_id_links) if table else "\n".join(external_id_links)),
        ]
        music_fields = [(label, field_value) for label, field_value in music_fields if field_value]
        if not music_fields:
            return ""

        if table:
            table_lines = ["[table]"]
            table_lines.extend(f"[tr][td][b]{label}[/b][/td][td]{field_value}[/td][/tr]" for label, field_value in music_fields)
            table_lines.append("[/table]")
            body = "\n".join(table_lines)
        else:
            body = "\n".join(f"[b]{label}:[/b] {field_value}" for label, field_value in music_fields)
        return f"{header}{text['details']}{header_end}\n{body}"

    async def general_description_generator(
        self,
        meta: Meta,
        # Section controls
        audio_spectrogram: bool,
        bluray: bool,
        book: bool,
        custom_header: bool,
        custom_signature: bool,
        description: bool,
        game: bool,
        languages: bool,
        logo: bool,
        mediainfo: bool,
        menu_screenshots: bool,
        nfo: bool,
        screenshots: bool,
        tonemapped_header: bool,
        tv_info: bool,
        ua_signature: bool,
        user_description: bool,
        music: bool = True,
        approved_image_hosts: list[str] | None = None,
        signature: str = "",
        desc_header: str = "",
    ) -> str:
        apply_saved_draft(meta)
        image_list = get_tracker_image_collection(meta, self.tracker, "screenshots")
        image_list = cast(list[Any], image_list)

        if image_list is None:
            image_list = []
        if approved_image_hosts is None:
            approved_image_hosts = []
        if image_list:
            images = image_list
            multi_screens = 0
        else:
            images = meta.image_list
            multi_screens = self._get_int_config("multiScreens", 2)
        if meta.sorted_filelist:
            multi_screens = 0

        desc_parts: list[str] = []

        # Custom Header
        if custom_header:
            if not desc_header:
                desc_header = await self.get_custom_header()
            if desc_header:
                desc_parts.append(desc_header + "\n")

        # Language
        if languages:
            try:
                if not meta.language_checked:
                    await languages_manager.process_desc_language(meta, self.tracker)
                if meta.audio_languages and meta.write_audio_languages:
                    desc_parts.append(f"[code]Audio Language/s: {', '.join(meta.audio_languages)}[/code]")

                if meta.subtitle_languages and meta.write_subtitle_languages:
                    desc_parts.append(f"[code]Subtitle Language/s: {', '.join(meta.subtitle_languages)}[/code]")
                if meta.subtitle_languages and meta.write_hc_languages:
                    desc_parts.append(f"[code]Hardcoded Subtitle Language/s: {', '.join(meta.subtitle_languages)}[/code]")
            except Exception as e:
                logger.warning(f"[yellow]Warning: Error processing language: {e!s}[/yellow]")

        # Logo
        if logo:
            logo_url, logo_size = await self.get_logo_section(meta)
            if logo_url and logo_size:
                desc_parts.append(f"[center][img={logo_size}]{logo_url}[/img][/center]\n")

        # Mediainfo / BDInfo section for trackers like BJSHARE
        if mediainfo:
            if self.tracker == "BJSHARE":
                if meta.is_disc == "DVD":
                    desc_parts.append(f"[hide=DVD MediaInfo][pre]{await self.get_mediainfo_section(meta)}[/pre][/hide]")
                bd_info = await self.get_bdinfo_section(meta)
                if bd_info:
                    desc_parts.append(f"[hide=BDInfo][pre]{bd_info}[/pre][/hide]")
            elif self.tracker == "DIGITALCORE":
                bd_info = await self.get_bdinfo_section(meta)
                if bd_info:
                    desc_parts.append(bd_info)
            elif self.tracker in ("FUNFILE", "HDSPACE", "IPTORRENTS", "IMMORTALSEED"):
                mediainfo_sec = await self.get_mediainfo_section(meta)
                if mediainfo_sec:
                    desc_parts.append(f"[pre]{mediainfo_sec}[/pre]")
                bd_info = await self.get_bdinfo_section(meta)
                if bd_info:
                    desc_parts.append(f"[pre]{bd_info}[/pre]")
            elif self.tracker == "PTSKIT":
                mediainfo_sec = await self.get_mediainfo_section(meta)
                if mediainfo_sec:
                    desc_parts.append(mediainfo_sec)
                bd_info = await self.get_bdinfo_section(meta)
                if bd_info:
                    desc_parts.append(bd_info)
            elif self.tracker == "HDTORRENTS":
                mediainfo_sec = await self.get_mediainfo_section(meta)
                if mediainfo_sec:
                    desc_parts.append(f"[left][font=consolas]{mediainfo_sec}[/font][/left]")
                bd_info = await self.get_bdinfo_section(meta)
                if bd_info:
                    desc_parts.append(f"[left][font=consolas]{bd_info}[/font][/left]")
            elif self.tracker == "MORETHANTV":
                mediainfo_sec = await self.get_mediainfo_section(meta)
                if mediainfo_sec:
                    desc_parts.append(f"[mediainfo]{mediainfo_sec}[/mediainfo]\n\n")
                bd_info = await self.get_bdinfo_section(meta)
                if bd_info:
                    desc_parts.append(f"[mediainfo]{bd_info}[/mediainfo]\n\n")
                if meta.is_disc == "DVD" and isinstance(meta.discs, list) and len(meta.discs) > 0 and "vob_mi" in meta.discs[0]:
                    desc_parts.append(f"[mediainfo]{meta.discs[0]['vob_mi']}[/mediainfo]\n\n")
            elif self.tracker == "TORRENTLEECH":
                mediainfo_sec = await self.get_mediainfo_section(meta)
                if mediainfo_sec:
                    desc_parts.append(mediainfo_sec)
                bd_info = await self.get_bdinfo_section(meta)
                if bd_info:
                    desc_parts.append(bd_info)
            else:
                pass

        # Blu-ray
        if bluray:
            release_url, cover_images = await self.get_bluray_section(meta)
            if release_url:
                desc_parts.append(f"[center]{release_url}[/center]")
            if cover_images:
                desc_parts.append(f"[center]{cover_images}[/center]\n")

        # TV
        if tv_info:
            title, episode_overview = await self.get_tv_info(meta)
            if episode_overview:
                if title:
                    desc_parts.append(f"[center]{title}[/center]\n")
                desc_parts.append(f"[center]{episode_overview}[/center]\n")

        # Book details
        if book and meta.category == "BOOK":
            book_section = self._build_book_desc_section(meta)
            if book_section:
                desc_parts.append(book_section)

        # Game details
        if game and meta.category == "GAME":
            game_section = self._build_game_desc_section(meta)
            if game_section:
                desc_parts.append(game_section)

        # Music details
        if music and meta.category == "MUSIC":
            music_section = self._build_music_desc_section(meta)
            if music_section:
                desc_parts.append(music_section)

        if self.tracker == "MTEAM" and meta.mteam_description:
            desc_parts.append(meta.mteam_description)

        if self.tracker in {"LAJIDUI", "LONGPT", "PTCAFE", "PTFANS", "PTGTK", "RAILGUNPT", "NEXUSPHP"} and meta.nexusphp_description:
            desc_parts.append(meta.nexusphp_description)

        # Description that may come from API requests
        if description:
            meta_description_value = meta.description
            if isinstance(meta_description_value, str):
                meta_description = meta_description_value
            elif meta_description_value is None:
                meta_description = ""
            else:
                meta_description = str(meta_description_value)
            # Add FraMeSToR NFO to AITHER
            if self.tracker == "AITHER" and "framestor" in meta and meta.framestor:
                nfo_content = meta.description_nfo_content
                if nfo_content:
                    aither_framestor_nfo = f"[code]{nfo_content}[/code]"
                    aither_framestor_nfo = aither_framestor_nfo.replace(
                        "https://i.imgur.com/e9o0zpQ.png",
                        "https://beyondhd.co/images/2017/11/30/c5802892418ee2046efba17166f0cad9.png",
                    )
                    images = []
                    desc_parts.append(aither_framestor_nfo)
                else:
                    # Remove NFO from description
                    meta_description = re.sub(
                        r"\[center\]\[spoiler=.*? NFO:\]\[code\](.*?)\[/code\]\[/spoiler\]\[/center\]",
                        "",
                        meta_description,
                        flags=re.DOTALL,
                    )
                    if meta_description:
                        desc_parts.append(meta_description)
            elif meta_description:
                if self.tracker == "MORETHANTV":
                    meta_description = re.sub(r"\[/?quote\]", "", meta_description, flags=re.IGNORECASE).strip()
                    if meta_description:
                        desc_parts.append(f"[spoiler=Notes]{meta_description}[/spoiler]")
                else:
                    desc_parts.append(meta_description)

        # NFO details
        if nfo:
            nfo_content = meta.description_nfo_content
            if isinstance(nfo_content, str) and nfo_content:
                if self.tracker == "DIGITALCORE":
                    desc_parts.append(f"[nfo]{nfo_content}[/nfo]")
                elif self.tracker == "TORRENTLEECH":
                    desc_parts.append(f"<div style='display: flex; justify-content: center;'><div style='background-color: #000000; color: #ffffff;'>{nfo_content}</div></div>")
                else:
                    desc_parts.append(f"[pre]{nfo_content}[/pre]")

        # Description from file/pastebin link
        if user_description:
            desc_parts.append(await self.get_user_description(meta))

        # Menu Screenshots
        if menu_screenshots:
            desc_parts.append(await self.menu_section(meta))

        # Tonemapped Header
        if tonemapped_header:
            desc_parts.append(await self.get_tonemapped_header(meta))

        # Discs and Screenshots
        if screenshots:
            discs_and_screenshots = await self._handle_discs_and_screenshots(meta, approved_image_hosts, images, multi_screens)
            desc_parts.append(discs_and_screenshots)

        # Audio Spectrograms
        if audio_spectrogram:
            desc_parts.append(await self.get_audio_spectrogram_section(meta))

        # Custom Signature
        if custom_signature:
            desc_parts.append(await self.get_custom_signature())

        # UA Signature
        if ua_signature:
            if not signature:
                script_signature = meta.ua_signature
                signature = f"[right][url=https://github.com/wastaken7/Upload-Assistant][size=4]{script_signature}[/size][/url][/right]"
            desc_parts.append(signature)

        description_str: str = "\n".join(part for part in desc_parts if part.strip())

        # Formatting
        description_str = self.tracker_specific_formats(self.tracker, description_str)

        if meta.debug:
            desc_file = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/[{self.tracker}]DESCRIPTION.txt"
            logger.debug(f"DEBUG: Saving final description to [yellow]{desc_file}[/yellow]")
            async with aiofiles.open(desc_file, "w", encoding="utf-8") as description_file:
                await description_file.write(description_str)

        return description_str

    async def unit3d_edit_desc(
        self,
        meta: Meta,
        signature: str = "",
        desc_header: str = "",
        approved_image_hosts: list[str] | None = None,
        audio_spectrogram: bool = True,
    ) -> str:
        return await self.general_description_generator(
            meta,
            audio_spectrogram=audio_spectrogram,
            bluray=True,
            book=True,
            custom_header=True,
            custom_signature=True,
            description=True,
            game=True,
            languages=False,
            logo=True,
            mediainfo=False,
            menu_screenshots=True,
            nfo=False,
            screenshots=True,
            tonemapped_header=True,
            tv_info=True,
            ua_signature=True,
            user_description=True,
            music=True,
            signature=signature,
            desc_header=desc_header,
            approved_image_hosts=approved_image_hosts,
        )

    async def _check_saved_pack_image_links(self, meta: Meta, approved_image_hosts: list[str]) -> dict[str, Any]:
        pack_images_file = Path(meta.base_dir) / "tmp" / meta.uuid / "pack_image_links.json"
        pack_images_data: dict[str, Any] = {}
        approved_hosts = set(approved_image_hosts or [])
        if await self.common.path_exists(pack_images_file):
            try:
                async with aiofiles.open(pack_images_file, encoding="utf-8") as f:
                    pack_images_data = json.loads(await f.read())

                    # Filter out keys with non-approved image hosts
                    keys_to_remove: list[str] = []
                    for key_name, key_data in pack_images_data.get("keys", {}).items():
                        images_to_keep: list[dict[str, str]] = []
                        for img in key_data.get("images", []):
                            raw_url = img.get("raw_url", "")
                            # Extract hostname from URL and check against approved hosts
                            try:
                                parsed_url: ParseResult = urllib.parse.urlparse(raw_url or "")
                                hostname = parsed_url.netloc

                                # Use suffix-based matching: check if hostname matches or is subdomain of approved host
                                host_approved = False
                                if not approved_hosts:
                                    host_approved = True  # If no approved hosts specified, allow all
                                else:
                                    for approved_host in approved_hosts:
                                        if hostname == approved_host or hostname.endswith(f".{approved_host}"):
                                            host_approved = True
                                            break

                                if host_approved:
                                    images_to_keep.append(img)
                                elif meta.debug:
                                    logger.info(f"[yellow]Filtering out image from non-approved host: {hostname}[/yellow]")
                            except Exception:
                                # If URL parsing fails, skip this image
                                logger.debug(f"[yellow]Could not parse URL: {raw_url}[/yellow]")
                                continue

                        if images_to_keep:
                            # Update the key with only approved images
                            pack_images_data["keys"][key_name]["images"] = images_to_keep
                            pack_images_data["keys"][key_name]["count"] = len(images_to_keep)
                        else:
                            # Mark key for removal if no approved images
                            keys_to_remove.append(key_name)

                    # Remove keys with no approved images
                    for key_name in keys_to_remove:
                        del pack_images_data["keys"][key_name]
                        logger.debug(f"[yellow]Removed key '{key_name}' - no approved image hosts[/yellow]")

                    # Recalculate total count
                    pack_images_data["total_count"] = sum(key_data["count"] for key_data in pack_images_data.get("keys", {}).values())

                    if pack_images_data.get("total_count", 0) < 3:
                        pack_images_data = {}  # Invalidate if less than 3 images total
                        logger.debug("[yellow]Invalidating pack images - less than 3 approved images total[/yellow]")
                    else:
                        logger.debug(f"[green]Loaded previously uploaded images from {pack_images_file}")
                        logger.debug(f"[blue]Found {pack_images_data.get('total_count', 0)} approved images across {len(pack_images_data.get('keys', {}))} keys[/blue]")
            except Exception as e:
                logger.warning(f"[yellow]Warning: Could not load pack image data: {e!s}[/yellow]")
        return pack_images_data

    async def _handle_discs_and_screenshots(self, meta: Meta, approved_image_hosts: list[str], images: list[dict[str, str]], multi_screens: int) -> str:
        if not images:
            return ""
        try:
            screenheader = await self.screenshot_header()
        except Exception:
            screenheader = None

        # Check for saved pack_image_links.json file
        pack_images_data = await self._check_saved_pack_image_links(meta, approved_image_hosts)

        char_limit = self._get_int_config("charLimit", 14000)
        file_limit = self._get_int_config("fileLimit", 5)
        thumb_size = self._get_int_config("pack_thumb_size", 300)
        process_limit = self._get_int_config("processLimit", 10)

        screens_per_row = await self.get_screens_per_row()

        desc_parts: list[str] = []

        if meta.category == "GAME":
            if screenheader is not None:
                desc_parts.append(screenheader + "\n")
            desc_parts.append("[center]")
            for img_index in range(len(images[: meta.screens if meta.screens is not None else 6])):
                web_url = images[img_index]["web_url"]
                raw_url = images[img_index]["raw_url"]
                desc_parts.append(self.format_screenshot(web_url, raw_url))
                if screens_per_row and (img_index + 1) % screens_per_row == 0:
                    desc_parts.append("\n")
            desc_parts.append("[/center]")
            return "".join(desc_parts)

        discs = meta.discs
        if len(discs) == 1:
            each = discs[0]
            if each["type"] == "DVD":
                desc_parts.append("[center]")
                desc_parts.append(f"[spoiler={Path(each['vob']).name}][code]{each['vob_mi']}[/code][/spoiler]\n\n")
                desc_parts.append("[/center]")
            if screenheader is not None:
                desc_parts.append(screenheader + "\n")
            desc_parts.append("[center]")
            for img_index in range(len(images[: meta.screens])):
                web_url = images[img_index]["web_url"]
                raw_url = images[img_index]["raw_url"]
                img_url = images[img_index].get("img_url", raw_url)
                desc_parts.append(self.format_screenshot(web_url, raw_url, img_url))
                if screens_per_row and (img_index + 1) % screens_per_row == 0:
                    desc_parts.append("\n")
            desc_parts.append("[/center]")
            if each["type"] == "BDMV":
                bdinfo_keys = [key for key in each if key.startswith("bdinfo")]
                if len(bdinfo_keys) > 1:
                    if "retry_count" not in meta:
                        meta.retry_count = 0

                    for i, key in enumerate(bdinfo_keys[1:], start=1):  # Skip the first bdinfo
                        new_images_key = f"new_images_playlist_{i}"
                        bdinfo = each[key]
                        edition = bdinfo.get("edition", "Unknown Edition")

                        # Find the corresponding summary for this bdinfo
                        summary_key = f"summary_{i}" if i > 0 else "summary"
                        summary = each.get(summary_key, "No summary available")

                        # Check for saved images first
                        if pack_images_data and "keys" in pack_images_data and new_images_key in pack_images_data["keys"]:
                            saved_images = pack_images_data["keys"][new_images_key]["images"]
                            if saved_images:
                                logger.debug(f"[yellow]Using saved images from pack_image_links.json for {new_images_key}")

                                meta[new_images_key] = []
                                for img in saved_images:
                                    meta[new_images_key].append(
                                        {
                                            "img_url": img.get("img_url", ""),
                                            "raw_url": img.get("raw_url", ""),
                                            "web_url": img.get("web_url", ""),
                                        }
                                    )

                        if meta.get(new_images_key):
                            desc_parts.append("[center]\n\n")
                            # Use the summary corresponding to the current bdinfo
                            desc_parts.append(f"[spoiler={edition}][code]{summary}[/code][/spoiler]\n\n")
                            logger.debug("[yellow]Using original uploaded images for first disc")
                            desc_parts.append("[center]")
                            for img in meta[new_images_key]:
                                web_url = img["web_url"]
                                raw_url = img["raw_url"]
                                img_url = img.get("img_url", raw_url)
                                desc_parts.append(self.format_screenshot(web_url, raw_url, img_url, thumb_size))
                            desc_parts.append("[/center]\n\n")
                        else:
                            desc_parts.append("[center]\n\n")
                            # Use the summary corresponding to the current bdinfo
                            desc_parts.append(f"[spoiler={edition}][code]{summary}[/code][/spoiler]\n\n")
                            desc_parts.append("[/center]\n\n")
                            meta.retry_count += 1
                            meta[new_images_key] = []
                            new_screens = [f.name for f in manifest_files(meta.base_dir, meta.uuid, f"PLAYLIST_{i}")]
                            if not new_screens:
                                logger.warning(f"[yellow]Missing prepared screenshots for PLAYLIST_{i}; skipping its images in the description.[/yellow]")
                            if new_screens and not meta.skip_imghost_upload:
                                uploaded_images, _ = await self.uploadscreens_manager.upload_screens(
                                    meta,
                                    multi_screens,
                                    1,
                                    0,
                                    multi_screens,
                                    new_screens,
                                    {new_images_key: meta[new_images_key]},
                                    allowed_hosts=approved_image_hosts,
                                )
                                if uploaded_images and not meta.skip_imghost_upload:
                                    await self.common.save_image_links(meta, new_images_key, uploaded_images)
                                for img in uploaded_images:
                                    meta[new_images_key].append(
                                        {
                                            "img_url": img["img_url"],
                                            "raw_url": img["raw_url"],
                                            "web_url": img["web_url"],
                                        }
                                    )

                                desc_parts.append("[center]")
                                for img in uploaded_images:
                                    web_url = img["web_url"]
                                    raw_url = img["raw_url"]
                                    img_url = img.get("img_url", raw_url) or ""
                                    desc_parts.append(self.format_screenshot(web_url, raw_url, img_url, thumb_size))
                                desc_parts.append("[/center]\n\n")

                            meta_filename = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/meta.json"
                            async with aiofiles.open(meta_filename, "w") as f:
                                await f.write(json.dumps(meta.to_dict(), indent=4, cls=PathAwareEncoder))

        # Handle multiple discs case
        elif len(discs) > 1:
            # Initialize retry_count if not already set
            if "retry_count" not in meta:
                meta.retry_count = 0

            total_discs_to_process = min(len(discs), process_limit)
            processed_count = 0
            if multi_screens != 0:
                logger.info("[cyan]Processing screenshots for packed content (multiScreens)[/cyan]")
                logger.info(f"[cyan]{total_discs_to_process} files (processLimit)[/cyan]")

            for i, each in enumerate(discs):
                # Set a unique key per disc for managing images
                new_images_key = f"new_images_disc_{i}"

                if i == 0:
                    desc_parts.append("[center]")
                    if each["type"] == "BDMV":
                        desc_parts.append(f"{each.get('name', 'BDINFO')}\n\n")
                    elif each["type"] == "DVD":
                        desc_parts.append(f"{each['name']}:\n")
                        desc_parts.append(f"[spoiler={Path(each['vob']).name}][code]{each['vob_mi']}[/code][/spoiler]")
                        desc_parts.append(f"[spoiler={Path(each['ifo']).name}][code]{each['ifo_mi']}[/code][/spoiler]\n\n")
                    # For the first disc, use images from `meta.image_list` and add screenheader if applicable
                    logger.debug("[yellow]Using original uploaded images for first disc")
                    if screenheader is not None:
                        desc_parts.append("[/center]\n\n")
                        desc_parts.append(screenheader + "\n")
                        desc_parts.append("[center]")
                    for img_index in range(len(images[: meta.screens])):
                        web_url = images[img_index]["web_url"]
                        raw_url = images[img_index]["raw_url"]
                        img_url = images[img_index].get("img_url", raw_url)
                        desc_parts.append(self.format_screenshot(web_url, raw_url, img_url, thumb_size))
                        if screens_per_row and (img_index + 1) % screens_per_row == 0:
                            desc_parts.append("\n")
                    desc_parts.append("[/center]\n\n")
                else:
                    if multi_screens != 0:
                        processed_count += 1
                        disc_name = each.get("name", f"Disc {i}")
                        logger.info(
                            f"\rProcessing disc {processed_count}/{total_discs_to_process}: {disc_name[:40]}{'...' if len(disc_name) > 40 else ''}",
                            extra={"markup": False},
                        )
                        # Check if screenshots exist for the current disc key
                        # Check for saved images first
                        if pack_images_data and "keys" in pack_images_data and new_images_key in pack_images_data["keys"]:
                            saved_images = pack_images_data["keys"][new_images_key]["images"]
                            if saved_images:
                                logger.debug(f"[yellow]Using saved images from pack_image_links.json for {new_images_key}")

                                meta[new_images_key] = []
                                for img in saved_images:
                                    meta[new_images_key].append(
                                        {
                                            "img_url": img.get("img_url", ""),
                                            "raw_url": img.get("raw_url", ""),
                                            "web_url": img.get("web_url", ""),
                                        }
                                    )
                        if meta.get(new_images_key):
                            logger.debug(f"[yellow]Found needed image URLs for {new_images_key}")
                            desc_parts.append("[center]")
                            if each["type"] == "BDMV":
                                desc_parts.append(f"[spoiler={each.get('name', 'BDINFO')}][code]{each['summary']}[/code][/spoiler]\n\n")
                            elif each["type"] == "DVD":
                                desc_parts.append(f"{each['name']}:\n")
                                desc_parts.append(f"[spoiler={Path(each['vob']).name}][code]{each['vob_mi']}[/code][/spoiler] ")
                                desc_parts.append(f"[spoiler={Path(each['ifo']).name}][code]{each['ifo_mi']}[/code][/spoiler]\n\n")
                            desc_parts.append("[/center]\n\n")
                            # Use existing URLs from meta to write to descfile
                            desc_parts.append("[center]")
                            for img in meta[new_images_key]:
                                web_url = img["web_url"]
                                raw_url = img["raw_url"]
                                img_url = img.get("img_url", raw_url)
                                desc_parts.append(self.format_screenshot(web_url, raw_url, img_url, thumb_size))
                            desc_parts.append("[/center]\n\n")
                        else:
                            # Increment retry_count for tracking but use unique disc keys for each disc
                            meta.retry_count += 1
                            meta[new_images_key] = []
                            desc_parts.append("[center]")
                            if each["type"] == "BDMV":
                                desc_parts.append(f"[spoiler={each.get('name', 'BDINFO')}][code]{each['summary']}[/code][/spoiler]\n\n")
                            elif each["type"] == "DVD":
                                desc_parts.append(f"{each['name']}:\n")
                                desc_parts.append(f"[spoiler={Path(each['vob']).name}][code]{each['vob_mi']}[/code][/spoiler] ")
                                desc_parts.append(f"[spoiler={Path(each['ifo']).name}][code]{each['ifo_mi']}[/code][/spoiler]\n\n")
                            desc_parts.append("[/center]\n\n")
                            # Check if new screenshots already exist before running prep.screenshots
                            new_screens: list[str] = []
                            if each["type"] == "BDMV":
                                new_screens = [f.name for f in manifest_files(meta.base_dir, meta.uuid, f"FILE_{i}")]
                            elif each["type"] == "DVD":
                                new_screens = [
                                    f.name for f in manifest_files(meta.base_dir, meta.uuid, await self.takescreens_manager.sanitize_filename(meta.discs[i]["name"]))
                                ]
                            if not new_screens:
                                logger.warning(f"[yellow]Missing prepared screenshots for {new_images_key}; skipping its images in the description.[/yellow]")

                            if new_screens and not meta.skip_imghost_upload:
                                uploaded_images, _ = await self.uploadscreens_manager.upload_screens(
                                    meta,
                                    multi_screens,
                                    1,
                                    0,
                                    multi_screens,
                                    new_screens,
                                    {new_images_key: meta[new_images_key]},
                                    allowed_hosts=approved_image_hosts,
                                )
                                if uploaded_images and not meta.skip_imghost_upload:
                                    await self.common.save_image_links(meta, new_images_key, uploaded_images)
                                # Append each uploaded image's data to `meta[new_images_key]`
                                for img in uploaded_images:
                                    meta[new_images_key].append(
                                        {
                                            "img_url": img["img_url"],
                                            "raw_url": img["raw_url"],
                                            "web_url": img["web_url"],
                                        }
                                    )

                                # Write new URLs to descfile
                                desc_parts.append("[center]")
                                for img in uploaded_images:
                                    web_url = img["web_url"]
                                    raw_url = img["raw_url"]
                                    img_url = img.get("img_url", raw_url) or ""
                                    desc_parts.append(self.format_screenshot(web_url, raw_url, img_url, thumb_size))
                                desc_parts.append("[/center]\n\n")

                            # Save the updated meta to `meta.json` after upload
                            meta_filename = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/meta.json"
                            async with aiofiles.open(meta_filename, "w") as f:
                                await f.write(json.dumps(meta.to_dict(), indent=4, cls=PathAwareEncoder))
                        logger.info("")

        # Handle single file case
        filelist = meta.filelist
        if len(filelist) == 1:
            if meta.comparison and meta.comparison_groups:
                desc_parts.append("[center]")
                comparison_groups = meta.comparison_groups
                if not isinstance(comparison_groups, dict):
                    comparison_groups = {str(i): v for i, v in enumerate(comparison_groups)}
                sorted_group_indices = sorted(comparison_groups.keys(), key=lambda x: int(x))

                comp_sources: list[str] = []
                for group_idx in sorted_group_indices:
                    group_data = comparison_groups[group_idx]
                    group_name = group_data.get("name", f"Group {group_idx}")
                    comp_sources.append(group_name)

                sources_string = ", ".join(comp_sources)
                desc_parts.append(f"[comparison={sources_string}]\n")

                images_per_group = min([len(comparison_groups[idx].get("urls", [])) for idx in sorted_group_indices])

                for img_idx in range(images_per_group):
                    for group_idx in sorted_group_indices:
                        group_data = comparison_groups[group_idx]
                        urls = group_data.get("urls", [])
                        if img_idx < len(urls):
                            img_url = urls[img_idx].get("raw_url", "")
                            if img_url:
                                desc_parts.append(f"{img_url}\n")

                desc_parts.append("[/comparison][/center]\n\n")

            if screenheader is not None:
                desc_parts.append(screenheader + "\n")
            desc_parts.append("[center]")
            for img_index in range(len(images[: meta.screens])):
                web_url = images[img_index]["web_url"]
                raw_url = images[img_index]["raw_url"]
                img_url = images[img_index].get("img_url", raw_url)
                desc_parts.append(self.format_screenshot(web_url, raw_url, img_url))
                if screens_per_row and (img_index + 1) % screens_per_row == 0:
                    desc_parts.append("\n")
            desc_parts.append("[/center]")

        # Handle multiple files case
        # Initialize character counter
        char_count = 0
        max_char_limit = char_limit  # Character limit
        other_files_spoiler_open = False  # Track if "Other files" spoiler has been opened
        total_files_to_process = min(len(filelist), process_limit)
        processed_count = 0
        if multi_screens != 0 and total_files_to_process > 1:
            logger.info("[cyan]Processing screenshots for packed content (multiScreens)[/cyan]")
            logger.info(f"[cyan]{total_files_to_process} files (processLimit)[/cyan]")

        # First Pass: Create and Upload Images for Each File
        for i, file in enumerate(filelist):
            if i >= process_limit:
                # console.print("[yellow]Skipping processing more files as they exceed the process limit.")
                continue
            if multi_screens != 0:
                if total_files_to_process > 1:
                    processed_count += 1
                    filename = Path(file).name
                    logger.info(f"\rProcessing file {processed_count}/{total_files_to_process}: {filename[:40]}{'...' if len(filename) > 40 else ''}", extra={"markup": False})
                if i > 0:
                    new_images_key = f"new_images_file_{i}"
                    # Check for saved images first
                    if pack_images_data and "keys" in pack_images_data and new_images_key in pack_images_data["keys"]:
                        saved_images = pack_images_data["keys"][new_images_key]["images"]
                        if saved_images:
                            logger.debug(f"[yellow]Using saved images from pack_image_links.json for {new_images_key}")

                            meta[new_images_key] = []
                            for img in saved_images:
                                meta[new_images_key].append(
                                    {
                                        "img_url": img.get("img_url", ""),
                                        "raw_url": img.get("raw_url", ""),
                                        "web_url": img.get("web_url", ""),
                                    }
                                )
                    if new_images_key not in meta or not meta[new_images_key]:
                        meta[new_images_key] = []
                        # Proceed with image generation if not already present
                        new_screens = [f.name for f in manifest_files(meta.base_dir, meta.uuid, f"FILE_{i}")]

                        # If no screenshots exist, create them
                        if not new_screens:
                            if meta.debug:
                                logger.info(f"[yellow]No existing screenshots for {new_images_key}; generating new ones.")
                            try:
                                await self.takescreens_manager.screenshots(
                                    file,
                                    f"FILE_{i}",
                                    meta.uuid,
                                    meta.base_dir,
                                    meta,
                                    multi_screens,
                                    True,
                                    capture_group=f"FILE_{i}",
                                )
                                await asyncio.sleep(0.1)
                            except Exception as e:
                                logger.info(f"Error during generic screenshot capture: {e}", extra={"markup": False})

                        new_screens = [f.name for f in manifest_files(meta.base_dir, meta.uuid, f"FILE_{i}")]

                        # Upload generated screenshots
                        if new_screens and not meta.skip_imghost_upload:
                            uploaded_images, _ = await self.uploadscreens_manager.upload_screens(
                                meta,
                                multi_screens,
                                1,
                                0,
                                multi_screens,
                                new_screens,
                                {new_images_key: meta[new_images_key]},
                                allowed_hosts=approved_image_hosts,
                            )
                            if uploaded_images and not meta.skip_imghost_upload:
                                await self.common.save_image_links(meta, new_images_key, uploaded_images)
                            for img in uploaded_images:
                                meta[new_images_key].append(
                                    {
                                        "img_url": img["img_url"],
                                        "raw_url": img["raw_url"],
                                        "web_url": img["web_url"],
                                    }
                                )

                            await asyncio.sleep(0.1)

                await asyncio.sleep(0.05)

        # Save updated meta
        meta_filename = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/meta.json"
        async with aiofiles.open(meta_filename, "w") as f:
            await f.write(json.dumps(meta.to_dict(), indent=4, cls=PathAwareEncoder))
        await asyncio.sleep(0.1)

        # Second Pass: Process MediaInfo and Write Descriptions
        if len(filelist) > 1:
            for i, file in enumerate(filelist):
                if i >= process_limit:
                    continue
                # Extract filename directly from the file path
                filename = Path(file.strip()).stem.replace("[", "").replace("]", "")

                # If we are beyond the file limit, add all further files in a spoiler
                if multi_screens != 0 and i >= file_limit and not other_files_spoiler_open:
                    desc_parts.append("[center][spoiler=Other files]\n")
                    char_count += len("[center][spoiler=Other files]\n")
                    other_files_spoiler_open = True

                # Write filename in BBCode format with MediaInfo in spoiler if not the first file
                if multi_screens != 0:
                    if i > 0 and char_count < max_char_limit:
                        mi_dump = MediaInfo.parse(file, output="STRING", full=False, mediainfo_options={"inform_version": "1"})
                        parsed_mediainfo = self.parser.parse_mediainfo(mi_dump)
                        formatted_bbcode = self.parser.format_bbcode(parsed_mediainfo)
                        desc_parts.append(f"[center][spoiler={filename}]{formatted_bbcode}[/spoiler][/center]\n")
                        char_count += len(f"[center][spoiler={filename}]{formatted_bbcode}[/spoiler][/center]\n")
                    else:
                        if i == 0 and images and screenheader is not None:
                            desc_parts.append(screenheader + "\n")
                            char_count += len(screenheader + "\n")
                        desc_parts.append(f"[center]{filename}\n[/center]\n")
                        char_count += len(f"[center]{filename}\n[/center]\n")

                # Write images if they exist
                new_images_key = f"new_images_file_{i}"
                if i == 0:  # For the first file, use 'image_list' key and add screenheader if applicable
                    if images:
                        if screenheader is not None:
                            desc_parts.append(screenheader + "\n")
                            char_count += len(screenheader + "\n")
                        desc_parts.append("[center]")
                        char_count += len("[center]")
                        for img_index in range(len(images)):
                            web_url = images[img_index]["web_url"]
                            raw_url = images[img_index]["raw_url"]
                            img_url = images[img_index].get("img_url", raw_url)
                            image_str = self.format_screenshot(web_url, raw_url, img_url, thumb_size)
                            desc_parts.append(image_str)
                            char_count += len(image_str)
                            if screens_per_row and (img_index + 1) % screens_per_row == 0:
                                desc_parts.append("\n")
                        desc_parts.append("[/center]\n\n")
                        char_count += len("[/center]\n\n")
                elif multi_screens != 0 and new_images_key in meta and meta[new_images_key]:
                    desc_parts.append("[center]")
                    char_count += len("[center]")
                    for img in meta[new_images_key]:
                        web_url = img["web_url"]
                        raw_url = img["raw_url"]
                        img_url = img.get("img_url", raw_url)
                        image_str = self.format_screenshot(web_url, raw_url, img_url, thumb_size)
                        desc_parts.append(image_str)
                        char_count += len(image_str)
                    desc_parts.append("[/center]\n\n")
                    char_count += len("[/center]\n\n")

            if other_files_spoiler_open:
                desc_parts.append("[/spoiler][/center]\n")
                char_count += len("[/spoiler][/center]\n")

        if char_count >= 1 and meta.debug:
            logger.info(f"[yellow]Total characters written to description: {char_count}")
        if total_files_to_process > 1:
            logger.info("")

        return "".join(p for p in desc_parts if p)

    async def get_screens_per_row(self) -> int:
        try:
            # If screens_per_row is set, use that to determine how many screenshots should be on each row. Otherwise, use 2 as default
            screens_per_row = self._get_int_config("screens_per_row", 2)
            if self.tracker == "HAWKEUNO":
                width = self._get_int_config("thumbnail_size", 350)
                # Adjust screens_per_row to keep total width below 1100
                while screens_per_row * width > 1100 and screens_per_row > 1:
                    screens_per_row -= 1
        except Exception:
            screens_per_row = 2
        return screens_per_row

    async def menu_section(self, meta: Meta) -> str:
        menu_image_section = ""
        try:
            disc_menu_header = await self.menu_screenshot_header(meta)
            screens_per_row = await self.get_screens_per_row()
            if meta.is_disc:
                menu_parts: list[str] = []
                menu_images = get_tracker_image_collection(meta, self.tracker, "menu_images")
                if disc_menu_header and menu_images:
                    menu_parts.append(disc_menu_header + "\n")
                if menu_images:
                    menu_parts.append("[center]")
                    for img_index, image in enumerate(menu_images):
                        web_url = image.get("web_url")
                        raw_url = image.get("raw_url")
                        img_url = image.get("img_url", raw_url)
                        if not web_url or not raw_url:
                            continue
                        menu_parts.append(self.format_screenshot(web_url, raw_url, img_url))
                        if screens_per_row and (img_index + 1) % screens_per_row == 0:
                            menu_parts.append("\n")
                    menu_parts.append("[/center]\n\n")
                    menu_image_section = "".join(menu_parts)
        except Exception as e:
            logger.warning(f"[yellow]Warning: Error processing disc menu section: {e!s}[/yellow]")

        return menu_image_section

    def format_screenshot(self, web_url: str, raw_url: str, img_url: str = "", thumb_size: str | int = "") -> str:
        if not img_url:
            img_url = raw_url
        if not thumb_size:
            thumb_size = self._get_int_config("thumbnail_size", 350)

        nexusphp_trackers = {"LAJIDUI", "LONGPT", "PTCAFE", "PTFANS", "PTGTK", "RAILGUNPT", "NEXUSPHP"}
        if self.tracker in nexusphp_trackers:
            return f"[img]{raw_url}[/img]"
        if self.tracker == "HDTORRENTS":
            return f"<a href='{raw_url}'><img src='{img_url}' height=137></a> "
        if self.tracker == "TORRENTLEECH":
            return f'<a href="{web_url}"><img src="{img_url}" style="max-width: {thumb_size}px;"></a>  '
        if self.tracker == "FUNFILE":
            return f'<a href="{web_url}" target="_blank"><img src="{img_url}" width="{thumb_size}"></a> '
        if self.tracker == "GREATPOSTERWALL":
            return f"[img]{raw_url}[/img] "
        if self.tracker in ("HDSPACE", "IPTORRENTS"):
            if "imgbox" not in web_url:
                return f"[url={web_url}][img]{img_url}[/img][/url]\n"
            return f"[url={web_url}][img]{img_url}[/img][/url] "
        if self.tracker == "MORETHANTV":
            return f"[url={raw_url}][img={thumb_size}]{img_url}[/img][/url] "
        return f"[url={web_url}][img={thumb_size}]{raw_url}[/img][/url] "

    def tracker_specific_formats(self, tracker: str, description: str) -> str:
        bbcode = BBCODE()
        if tracker == "BRASILTRACKER":
            description = bbcode.remove_img_resize(description)
            description = bbcode.remove_list(description)

        if tracker == "BJSHARE":
            description = bbcode.convert_named_spoiler_to_named_hide(description)
            description = bbcode.convert_spoiler_to_hide(description)
            description = bbcode.remove_img_resize(description)
            description = bbcode.convert_to_align(description)
            description = bbcode.remove_list(description)
            description = description.replace("[code]", "[pre]").replace("[/code]", "[/pre]")

        if tracker == "ANTHELION":
            description = bbcode.convert_to_align(description)
            description = bbcode.remove_img_resize(description)
            description = bbcode.remove_sup(description)
            description = bbcode.remove_sub(description)
            description = bbcode.remove_list(description)
            description = description.replace("•", "-").replace("’", "'").replace("–", "-")  # noqa: RUF001
            description = description.replace("[code]", "[pre]").replace("[/code]", "[/pre]")

        if tracker == "DIGITALCORE":
            description = description.replace("[user]", "").replace("[/user]", "")
            description = description.replace("[align=left]", "").replace("[/align]", "")
            description = description.replace("[right]", "").replace("[/right]", "")
            description = description.replace("[align=right]", "").replace("[/align]", "")
            description = bbcode.remove_sup(description)
            description = bbcode.remove_sub(description)
            description = description.replace("[alert]", "").replace("[/alert]", "")
            description = description.replace("[note]", "").replace("[/note]", "")
            description = description.replace("[hr]", "").replace("[/hr]", "")
            description = description.replace("[h1]", "[u][b]").replace("[/h1]", "[/b][/u]")
            description = description.replace("[h2]", "[u][b]").replace("[/h2]", "[/b][/u]")
            description = description.replace("[h3]", "[u][b]").replace("[/h3]", "[/b][/u]")
            description = description.replace("[ul]", "").replace("[/ul]", "")
            description = description.replace("[ol]", "").replace("[/ol]", "")
            description = description.replace("[*] ", "• ").replace("[*]", "• ")
            description = bbcode.convert_named_spoiler_to_normal_spoiler(description)
            description = bbcode.remove_list(description)
            description = description.strip()

        if tracker == "FUNFILE":
            description = description.replace("[user]", "").replace("[/user]", "")
            description = description.replace("[align=left]", "").replace("[/align]", "")
            description = description.replace("[right]", "").replace("[/right]", "")
            description = description.replace("[align=right]", "").replace("[/align]", "")
            description = bbcode.remove_sub(description)
            description = bbcode.remove_sup(description)
            description = description.replace("[alert]", "").replace("[/alert]", "")
            description = description.replace("[note]", "").replace("[/note]", "")
            description = description.replace("[hr]", "").replace("[/hr]", "")
            description = description.replace("[h1]", "[u][b]").replace("[/h1]", "[/b][/u]")
            description = description.replace("[h2]", "[u][b]").replace("[/h2]", "[/b][/u]")
            description = description.replace("[h3]", "[u][b]").replace("[/h3]", "[/b][/u]")
            description = description.replace("[ul]", "").replace("[/ul]", "")
            description = description.replace("[ol]", "").replace("[/ol]", "")
            description = description.replace("[hide]", "").replace("[/hide]", "")
            description = description.replace("•", "-").replace("“", '"').replace("”", '"')
            description = bbcode.convert_comparison_to_centered(description, 1000)
            description = bbcode.remove_spoiler(description)

            # [url][img=000]...[/img][/url]
            description = re.sub(
                r"\[url=(?P<href>[^\]]+)\]\[img=(?P<width>\d+)\](?P<src>[^\[]+)\[/img\]\[/url\]",
                r'<a href="\g<href>" target="_blank"><img src="\g<src>" width="\g<width>"></a>',
                description,
                flags=re.IGNORECASE,
            )

            # [url][img]...[/img][/url]
            description = re.sub(
                r"\[url=(?P<href>[^\]]+)\]\[img\](?P<src>[^\[]+)\[/img\]\[/url\]",
                r'<a href="\g<href>" target="_blank"><img src="\g<src>" width="220"></a>',
                description,
                flags=re.IGNORECASE,
            )

            # [img=200]...[/img] (no [url])
            description = re.sub(r"\[img=(?P<width>\d+)\](?P<src>[^\[]+)\[/img\]", r'<img src="\g<src>" width="\g<width>">', description, flags=re.IGNORECASE)

        if tracker == "GREATPOSTERWALL":
            description = bbcode.remove_sup(description)
            description = bbcode.remove_sub(description)
            description = bbcode.convert_to_align(description)
            description = bbcode.remove_list(description)
            description = description.replace("[code]", "[pre]").replace("[/code]", "[/pre]")
            description = re.sub(r"\[url=[^\]]+\]\[img(?:=[^\]]+)?\]([^\[]+)\[/img\]\[/url\]", r"[img]\1[/img]", description, flags=re.IGNORECASE)

        if tracker == "HDSPACE":
            description = description.replace("[user]", "").replace("[/user]", "")
            description = description.replace("[align=left]", "").replace("[/align]", "")
            description = description.replace("[right]", "").replace("[/right]", "")
            description = description.replace("[align=right]", "").replace("[/align]", "")
            description = bbcode.remove_sub(description)
            description = bbcode.remove_sup(description)
            description = description.replace("[alert]", "").replace("[/alert]", "")
            description = description.replace("[note]", "").replace("[/note]", "")
            description = description.replace("[hr]", "").replace("[/hr]", "")
            description = description.replace("[h1]", "[u][b]").replace("[/h1]", "[/b][/u]")
            description = description.replace("[h2]", "[u][b]").replace("[/h2]", "[/b][/u]")
            description = description.replace("[h3]", "[u][b]").replace("[/h3]", "[/b][/u]")
            description = description.replace("[ul]", "").replace("[/ul]", "")
            description = description.replace("[ol]", "").replace("[/ol]", "")
            description = bbcode.remove_hide(description)
            description = bbcode.remove_img_resize(description)
            description = bbcode.convert_comparison_to_centered(description, 1000)
            description = bbcode.remove_spoiler(description)
            description = bbcode.remove_color(description)

            # Apply custom image line breaks for HDSPACE: if "imgbox" is not in the web_url, place only one image per line.
            def hds_image_formatter(match) -> str:
                web_url = match.group(1)
                raw_url = match.group(2)
                if "imgbox" not in web_url:
                    return f"[url={web_url}][img]{raw_url}[/img][/url]\n"
                return f"[url={web_url}][img]{raw_url}[/img][/url]"

            pattern = r"\[url=([^\]]+)\]\[img(?:=[^\]]*)?\]([^\[]+)\[/img\]\[/url\]\s*"
            description = re.sub(pattern, hds_image_formatter, description)

        if tracker == "IPTORRENTS":
            description = description.replace("[user]", "").replace("[/user]", "")
            description = description.replace("[align=left]", "").replace("[/align]", "")
            description = description.replace("[right]", "").replace("[/right]", "")
            description = description.replace("[align=right]", "").replace("[/align]", "")
            description = bbcode.remove_sub(description)
            description = bbcode.remove_sup(description)
            description = description.replace("[alert]", "").replace("[/alert]", "")
            description = description.replace("[note]", "").replace("[/note]", "")
            description = description.replace("[hr]", "").replace("[/hr]", "")
            description = description.replace("[h1]", "[u][b]").replace("[/h1]", "[/b][/u]")
            description = description.replace("[h2]", "[u][b]").replace("[/h2]", "[/b][/u]")
            description = description.replace("[h3]", "[u][b]").replace("[/h3]", "[/b][/u]")
            description = description.replace("[ul]", "").replace("[/ul]", "")
            description = description.replace("[ol]", "").replace("[/ol]", "")
            description = bbcode.remove_hide(description)
            description = bbcode.remove_img_resize(description)
            description = bbcode.convert_comparison_to_centered(description, 1000)
            description = bbcode.remove_spoiler(description)

        if tracker == "HDTORRENTS":
            description = description.replace("[user]", "").replace("[/user]", "")
            description = description.replace("[align=left]", "").replace("[/align]", "")
            description = description.replace("[align=right]", "").replace("[/align]", "")
            description = bbcode.remove_sub(description)
            description = bbcode.remove_sup(description)
            description = description.replace("[alert]", "").replace("[/alert]", "")
            description = description.replace("[note]", "").replace("[/note]", "")
            description = description.replace("[hr]", "").replace("[/hr]", "")
            description = description.replace("[h1]", "[u][b]").replace("[/h1]", "[/b][/u]")
            description = description.replace("[h2]", "[u][b]").replace("[/h2]", "[/b][/u]")
            description = description.replace("[h3]", "[u][b]").replace("[/h3]", "[/b][/u]")
            description = description.replace("[ul]", "").replace("[/ul]", "")
            description = description.replace("[ol]", "").replace("[/ol]", "")
            description = bbcode.convert_spoiler_to_hide(description)
            description = bbcode.remove_img_resize(description)
            description = bbcode.convert_comparison_to_centered(description, 1000)
            description = bbcode.remove_spoiler(description)
            description = bbcode.remove_list(description)

        if tracker == "PTSKIT":
            description = description.replace("[user]", "").replace("[/user]", "")
            description = description.replace("[align=left]", "").replace("[/align]", "")
            description = description.replace("[right]", "").replace("[/right]", "")
            description = description.replace("[align=right]", "").replace("[/align]", "")
            description = description.replace("[sup]", "").replace("[/sup]", "")
            description = description.replace("[sub]", "").replace("[/sub]", "")
            description = description.replace("[alert]", "").replace("[/alert]", "")
            description = description.replace("[note]", "").replace("[/note]", "")
            description = description.replace("[hr]", "").replace("[/hr]", "")
            description = description.replace("[h1]", "[u][b]").replace("[/h1]", "[/b][/u]")
            description = description.replace("[h2]", "[u][b]").replace("[/h2]", "[/b][/u]")
            description = description.replace("[h3]", "[u][b]").replace("[/h3]", "[/b][/u]")
            description = description.replace("[ul]", "").replace("[/ul]", "")
            description = description.replace("[ol]", "").replace("[/ol]", "")
            description = description.replace("[hide]", "").replace("[/hide]", "")
            description = re.sub(r"\[center\]\[spoiler=.*? NFO:\]\[code\](.*?)\[/code\]\[/spoiler\]\[/center\]", r"", description, flags=re.DOTALL)
            description = bbcode.convert_comparison_to_centered(description, 1000)
            description = bbcode.remove_spoiler(description)
            description = re.sub(r"\n{3,}", "\n\n", description)

        if tracker == "SPEEDAPP":
            description = bbcode.remove_img_resize(description)
            description = bbcode.convert_named_spoiler_to_normal_spoiler(description)
            description = description.replace("[note]", "Note: ").replace("[/note]", "").replace("[code]", "").replace("[/code]", "").replace("[*]", "• ")
            description = bbcode.remove_spoiler(description)
            description = bbcode.remove_list(description)

        if tracker == "TORRENTLEECH":
            description = description.replace("[center]", "<center>").replace("[/center]", "</center>")
            description = re.sub(r"\[\*\]", "\n[*]", description, flags=re.IGNORECASE)
            description = re.sub(r"\[c\](.*?)\[/c\]", r"[code]\1[/code]", description, flags=re.IGNORECASE | re.DOTALL)
            description = re.sub(r"\[hr\]", "---", description, flags=re.IGNORECASE)
            description = re.sub(r'\[img=[\d"x]+\]', "[img]", description, flags=re.IGNORECASE)
            description = description.replace("[*] ", "• ").replace("[*]", "• ").replace("[note]", "Note: ").replace("[/note]", "").replace("[code]", "").replace("[/code]", "")
            description = bbcode.remove_list(description)
            description = bbcode.convert_comparison_to_centered(description, 1000)
            description = bbcode.remove_spoiler(description)
            description = re.sub(r"\n{3,}", "\n\n", description)

        if tracker == "IMMORTALSEED":
            # all tags must be removed, this is a plain-text only description
            description = html.unescape(description)
            # Preserve text structure where markup normally separates content.
            description = re.sub(r"<br\s*/?\s*>", "\n", description, flags=re.IGNORECASE)
            description = re.sub(r"</(?:p|div|li|tr|h[1-6]|blockquote|pre)\s*>", "\n", description, flags=re.IGNORECASE)
            description = re.sub(r"<!--.*?-->|<![^>]*>|</?[a-z][^>]*>", "", description, flags=re.IGNORECASE | re.DOTALL)
            # Strip BBCode names and attributes while retaining their contents.
            description = re.sub(r"\[/?[a-z][a-z0-9_-]*(?:=[^\]]*|\s+[^\]]*)?\]|\[\*\]", "", description, flags=re.IGNORECASE)

        from src.trackersetup import api_trackers as unit3d_trackers

        if tracker in unit3d_trackers:
            description = bbcode.convert_hide_to_spoiler(description)
            description = description.replace("[user]", "").replace("[/user]", "")
            description = description.replace("[hr]", "").replace("[/hr]", "")
            description = description.replace("[ul]", "").replace("[/ul]", "")
            description = description.replace("[ol]", "").replace("[/ol]", "")
            description = bbcode.convert_comparison_to_collapse(description, 1000)

        return bbcode.remove_extra_lines(description)
