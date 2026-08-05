# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import asyncio
import contextlib
import json
import re
import sys
from collections.abc import Callable, Mapping
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, cast

import aiofiles
import cli_ui
from rich.markup import escape

from src.bdinfo_comparator import compare_bdinfo, has_bdinfo_content
from src.cleanup import cleanup_manager
from src.cogs.redaction import Redaction
from src.config_helpers import format_terminal_link
from src.console import logger, prompt_in_thread
from src.meta import Meta
from src.trackersetup import tracker_class_map

DupeEntry = dict[str, Any]


def _music_confirmation_lines(meta: Meta, missing_warning: str) -> list[tuple[str, str] | str]:
    """Build a concise, tracker-neutral MUSIC review for the confirmation UI.

    Music analysis intentionally remains in ``meta.music_release`` so tracker
    adapters can use the full provenance-rich model.  The confirmation prompt
    should expose the important parts of that analysis without printing local
    paths, complete tags, or an unbounded list of warnings.
    """
    release = meta.music_release if isinstance(meta.music_release, dict) else {}
    fields = release.get("fields", {}) if isinstance(release.get("fields"), dict) else {}
    tracks = release.get("tracks", []) if isinstance(release.get("tracks"), list) else []
    auxiliary = release.get("auxiliary", {}) if isinstance(release.get("auxiliary"), dict) else {}
    warnings = release.get("warnings", []) if isinstance(release.get("warnings"), list) else []
    conflicts = release.get("conflicts", {}) if isinstance(release.get("conflicts"), dict) else {}

    def value(name: str, fallback: Any = "") -> Any:
        entry = fields.get(name, {})
        if isinstance(entry, dict) and entry.get("value") not in (None, "", [], {}):
            return entry["value"]
        return fallback

    def source(name: str) -> str:
        entry = fields.get(name, {})
        source_name = entry.get("source", "") if isinstance(entry, dict) else ""
        return {
            "file_tag": "tags",
            "auxiliary": "auxiliary files",
            "directory": "folder name",
            "external": "external metadata",
            "user": "user input",
            "tracker": "tracker",
            "inferred": "inferred",
        }.get(str(source_name), "")

    def display(name: str, fallback: Any = "") -> str:
        item = value(name, fallback)
        if isinstance(item, list):
            item = " & ".join(str(part) for part in item)
        text = str(item).strip()
        provenance = source(name)
        return escape(text) + (f" [dim]({provenance})[/dim]" if text and provenance else "")

    def technical_values(key: str, formatter: Callable[[Any], str]) -> str:
        values = sorted({track.get(key) for track in tracks if isinstance(track, dict) and track.get(key) not in (None, "")})
        if not values:
            return ""
        rendered = [formatter(item) for item in values]
        return ", ".join(rendered) if len(rendered) <= 2 else f"{len(rendered)} variants"

    artist = display("artists", value("artist", meta.artist))
    album = display("album", meta.title)
    year = display("year", meta.year)
    media = display("media", meta.source)
    release_type = display("release_type")
    format_name = display("format", meta.format)
    formats = technical_values("format", str)
    codecs = technical_values("codec", str)
    bit_depth = technical_values("bit_depth", lambda item: f"{item}-bit")
    sample_rate = technical_values("sample_rate", lambda item: f"{int(item) / 1000:g} kHz")
    channels = technical_values("channels", lambda item: {1: "Mono", 2: "Stereo"}.get(int(item), f"{item} channels"))
    bitrate = technical_values("bitrate", lambda item: f"{round(int(item) / 1000)} kbps")
    # Container and codec are commonly both "FLAC"; repeating them adds no
    # review value, while different values (for example M4A / AAC) stay clear.
    if formats.casefold() == codecs.casefold():
        codecs = ""
    technical = " / ".join(part for part in (formats or format_name, codecs, bit_depth, sample_rate, channels, bitrate) if part)

    disc_count = value("disc_count", 1)
    track_count = value("track_count", len(tracks))
    edition = display("edition")
    edition_year = display("edition_year")
    release_year = display("release_year")
    retail_date = display("retail_date")
    release_label = display("release_label")
    release_catalogue = display("release_catalogue_number")
    genres = display("genres")

    lines: list[tuple[str, str] | str] = [
        ("Artist", artist or missing_warning),
        ("Album", album or missing_warning),
        ("Original Year", year or missing_warning),
        ("Release Type", release_type or missing_warning),
        ("Media", media or missing_warning),
        ("Tracks / Discs", f"{track_count or missing_warning} / {disc_count or 1}"),
        ("Audio", technical or format_name or missing_warning),
    ]
    if genres:
        lines.append(("Genre", genres))
    if any((release_year, retail_date, release_label, release_catalogue)):
        release_details = " / ".join(part for part in (release_year, retail_date, release_label, release_catalogue) if part)
        lines.append(("This Release", release_details))
    if edition:
        edition_details = " / ".join(part for part in (edition, edition_year) if part)
        lines.append(("Edition", edition_details))

    if re.match(r"^https?://[^/]+", str(meta.artwork_url or "").strip(), flags=re.IGNORECASE):
        artwork = "public URL supplied"
    elif Path(str(meta.artwork_path or "")).is_file():
        artwork = "local/embedded artwork available"
        if meta.debug:
            artwork += "; host upload skipped in debug"
    else:
        artwork = "not found (optional for Orpheus)"
    lines.append(("Artwork", artwork))

    sidecars = []
    for label, key in (("log", "logs"), ("cue", "cues"), ("NFO", "nfos"), ("playlist", "playlists"), ("SFV", "sfvs"), ("artwork", "artwork"), ("scan", "scans")):
        count = len(auxiliary.get(key, [])) if isinstance(auxiliary.get(key, []), list) else 0
        if count:
            sidecars.append(f"{count} {label}{'' if count == 1 else 's'}")
    if sidecars:
        lines.append(("Auxiliary", ", ".join(sidecars)))

    if conflicts:
        names = ", ".join(str(name).replace("_", " ") for name in sorted(conflicts)[:5])
        extra = f" (+{len(conflicts) - 5})" if len(conflicts) > 5 else ""
        lines.append(("Metadata conflicts", f"[yellow]{escape(names)}{extra}[/yellow]"))
    if warnings:
        preview = "; ".join(str(item) for item in warnings[:3])
        extra = f" (+{len(warnings) - 3} more)" if len(warnings) > 3 else ""
        lines.append(("Music validation", f"[yellow]{escape(preview)}{extra}[/yellow]"))
    return lines


def parse_size_to_bytes(size_str: Any) -> int | None:
    if size_str is None:
        return None
    if isinstance(size_str, (int, float)):
        return int(size_str)

    # It must be a string. Clean it up.
    s = str(size_str).strip()
    if not s:
        return None

    # Try converting directly to int in case it's pure bytes (like UNIT3D)
    if s.isdigit():
        return int(s)

    try:
        # Normalize commas/dots
        if "," in s:
            if "." in s:
                # e.g., 1,024.50 MB -> comma is thousands separator
                s = s.replace(",", "")
            else:
                # No dot, only comma. E.g., 1,024 MB or 1,544 TiB or 389,61 MiB
                match_comma = re.search(r",(\d+)\s*[a-zA-Z]*$", s)
                if match_comma:
                    digits_after = match_comma.group(1)
                    if len(digits_after) == 3:
                        # Ambiguous: could be thousands (1,024 MB) or decimal (1,544 TiB)
                        match_unit = re.search(r"([a-zA-Z]+)$", s)
                        unit = match_unit.group(1).lower() if match_unit else ""
                        # A large unit like TiB/TB indicates a decimal fraction (e.g., 1.544 TiB)
                        # For B, KB, MB, GB, etc., the comma is a thousands separator (e.g., 1,024 MB)
                        s = s.replace(",", ".") if unit in ("tb", "tib", "pb", "pib") else s.replace(",", "")
                    else:
                        # 1, 2, or 4+ digits after comma -> decimal separator
                        s = s.replace(",", ".")

        match = re.match(r"^([\d.]+)\s*([a-zA-Z]+)$", s)
        if not match:
            return int(float(s))

        value_str, unit = match.groups()
        value = float(value_str)
        unit = unit.lower()

        units_map = {
            "b": 1,
            "kb": 1024,
            "kib": 1024,
            "mb": 1024**2,
            "mib": 1024**2,
            "gb": 1024**3,
            "gib": 1024**3,
            "tb": 1024**4,
            "tib": 1024**4,
        }

        if unit in units_map:
            return int(value * units_map[unit])
        return int(value)
    except Exception:
        return None


def hsl_to_rgb(h: float, s: float, lx: float) -> tuple[int, int, int]:
    # h in [0, 360], s in [0, 1], l in [0, 1]
    c = (1.0 - abs(2.0 * lx - 1.0)) * s
    x = c * (1.0 - abs((h / 60.0) % 2.0 - 1.0))
    m = lx - c / 2.0
    if 0 <= h < 60:
        r, g, b = c, x, 0.0
    elif 60 <= h < 120:
        r, g, b = x, c, 0.0
    elif 120 <= h < 180:
        r, g, b = 0.0, c, x
    elif 180 <= h < 240:
        r, g, b = 0.0, x, c
    elif 240 <= h < 300:
        r, g, b = x, 0.0, c
    else:
        r, g, b = c, 0.0, x
    return int((r + m) * 255), int((g + m) * 255), int((b + m) * 255)


def get_color_for_diff(p: float) -> str:
    # Interpolate Hue from 120 (green) to 0 (red) for p in [0.0, 0.5]
    # saturation = 0.9, lightness = 0.6
    x = max(0.0, min(1.0, 1.0 - p / 0.5))
    h = 120.0 * (1.0 - x)
    r, g, b = hsl_to_rgb(h, 0.9, 0.6)
    return f"{r:02x}{g:02x}{b:02x}"


class UploadHelper:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.default_config = cast(Mapping[str, Any], config.get("DEFAULT", {}))
        if not isinstance(self.default_config, dict):
            raise ValueError("'DEFAULT' config section must be a dict")
        self.tracker_class_map = cast(Mapping[str, Any], tracker_class_map)
        self._prompt_lock = asyncio.Lock()

    async def prompt_yes_no(self, question: str, *, default: bool = False) -> bool:
        """Ask one interactive question at a time without blocking the event loop."""
        async with self._prompt_lock:
            return await prompt_in_thread(cli_ui.ask_yes_no, question, default=default)

    async def dupe_check(self, dupes: list[DupeEntry | str], meta: Meta, tracker_name: str) -> tuple[bool, Meta]:
        def _format_dupe(entry: DupeEntry | str) -> str:
            if isinstance(entry, dict):
                name = str(entry.get("name", ""))
                link = entry.get("link")

                size_diff_str = ""
                if self.default_config.get("show_dupe_size_diff", True):
                    upload_size = meta.source_size
                    dupe_size_raw = entry.get("size")
                    dupe_size = parse_size_to_bytes(dupe_size_raw)
                    if upload_size and dupe_size:
                        diff_bytes = dupe_size - upload_size
                        diff_mb = round(diff_bytes / (1024 * 1024))
                        diff_pct = round((diff_bytes / upload_size) * 100)

                        p = abs(diff_pct) / 100.0
                        color_hex = get_color_for_diff(p)
                        size_diff_str = f" - [#{color_hex}][{diff_mb:+d} MB / {diff_pct:+d}%][/]"

                if isinstance(link, str) and link:
                    return f"{format_terminal_link(name, link, self.default_config)}{size_diff_str}"
                return f"{name}{size_diff_str}"
            return entry

        def _format_dupes_list(entries: list[Any]) -> str:
            seen: set[str] = set()
            formatted = []
            for entry in entries:
                if isinstance(entry, dict) and entry.get("link"):
                    link = entry.get("link")
                    if link in seen:
                        continue
                    seen.add(link)
                formatted.append(_format_dupe(entry))
            return "\n".join(formatted)

        dupes_list: list[DupeEntry | str] = dupes
        upload: bool = False
        meta.were_trumping = False
        if not dupes_list:
            logger.debug(f"[green]No dupes found at[/green] [yellow]{tracker_name}[/yellow]")
            return False, meta
        tracker_class_factory = cast(Callable[..., Any], self.tracker_class_map[tracker_name])
        tracker_class = tracker_class_factory(config=self.config)
        try:
            tracker_rename = await tracker_class.get_name(meta)
        except Exception:
            tracker_rename = None
        display_name: str | None = None
        if tracker_rename is not None:
            if isinstance(tracker_rename, dict) and "name" in tracker_rename:
                tracker_rename_dict = cast(dict[str, Any], tracker_rename)
                display_name = str(tracker_rename_dict.get("name", ""))
            elif isinstance(tracker_rename, str):
                display_name = tracker_rename

        if meta.dupe is False and meta.season_pack_exists and bool(getattr(tracker_class, "reject_episode_if_season_pack_exists", False)):
            pack_name = meta.season_pack_name or "matching season pack"
            logger.info(f"[bold red]{tracker_name}: {pack_name} already contains this episode. Skipping individual episode upload.[/bold red]")
            return True, meta

        # Show naming change before dupe prompts so user knows what the final name will be
        pass

        trumpable_text = None
        if meta.trumpable_id or (meta.season_pack_contains_episode and meta.get(f"{tracker_name}_matched_episode_ids", [])):
            trumpable_dupes = [entry for entry in dupes_list if isinstance(entry, dict) and entry.get("trumpable")]
            if trumpable_dupes:
                trumpable_text = _format_dupes_list(trumpable_dupes)
                logger.info("[bold red]Trumpable found![/bold red]")
            elif meta.season_pack_contains_episode and meta.get(f"{tracker_name}_matched_episode_ids", []):
                matched_episodes = cast(list[DupeEntry], meta.get(f"{tracker_name}_matched_episode_ids", []))
                user_tag = meta.tag.lstrip("-").lower() if meta.tag else ""  # Remove leading dash for comparison

                # Try to find a release with matching tag
                selected_match = None
                tag_matched = False
                if user_tag:
                    for ep in matched_episodes:
                        ep_name = str(ep.get("name", "")).lower()
                        # Tag typically appears at end of name like "H.265-ETHEL"
                        if ep_name.endswith(user_tag) or f"-{user_tag}" in ep_name:
                            selected_match = ep
                            tag_matched = True
                            break

                # Fall back to first match if no tag match found
                if not selected_match:
                    selected_match = matched_episodes[0]

                trumpable_text = _format_dupe(selected_match)
                logger.info("[bold red]Trumpable found based on episode matching![/bold red]")

                if user_tag and not tag_matched:
                    logger.info(f"[yellow]Note: No release found with matching tag '{meta.tag}'. Selected release may be from a different group.[/yellow]")

        if (not meta.unattended or (meta.unattended and meta.unattended_confirm)) and not meta.ask_dupe:
            dupe_text = _format_dupes_list(dupes_list)

            if trumpable_text and (meta.trumpable_id or (meta.season_pack_contains_episode and meta.get(f"{tracker_name}_matched_episode_ids", []))):
                logger.info(f"[bold cyan]{trumpable_text}[/bold cyan]")
                logger.info("[yellow]Please check the trumpable entries above to see if you want to upload[/yellow]")
                logger.info("[yellow]You will have the option to report the trumpable torrent if you upload.[/yellow]")
                if meta.dupe is False:
                    try:
                        upload = await self.prompt_yes_no(f"Are you trumping this release on {tracker_name}?", default=False)
                        if upload:
                            meta.we_asked = True
                            meta.were_trumping = True
                            if not meta.get(f"{tracker_name}_trumpable_id"):
                                meta[f"{tracker_name}_trumpable_id"] = meta.get(f"{tracker_name}_matched_id", None)
                            if meta.filename_match and meta.file_count_match:
                                meta.trump_reason = "exact_match"
                            else:
                                meta.trump_reason = "trumpable_release"
                            logger.debug(f"[bold green]Trump reason: {meta.trump_reason} on {tracker_name}[/bold green]")
                        else:
                            # For season packs: individual episodes are only in dupes for trumping purposes.
                            # If user declines to trump, filter them out so they aren't shown as "potential dupes"
                            # (they wouldn't match season/episode anyway).
                            if meta.tv_pack and meta.season_pack_contains_episode and meta.get(f"{tracker_name}_matched_episode_ids", []):
                                matched_ids = {ep.get("id") for ep in meta.get(f"{tracker_name}_matched_episode_ids", []) if ep.get("id")}
                                dupes_list = [d for d in dupes_list if not (isinstance(d, dict) and d.get("id") in matched_ids)]
                                # Clear tracker-specific matched_episode_ids since we're not trumping
                                meta[f"{tracker_name}_matched_episode_ids"] = []
                    except EOFError:
                        logger.info("\n[red]Exiting on user request (Ctrl+C)[/red]")
                        await cleanup_manager.cleanup()
                        cleanup_manager.reset_terminal()
                        sys.exit(1)

            if not meta.were_trumping:
                if meta.filename_match and meta.file_count_match:
                    logger.info(f"[bold red]Exact match found! - {meta.filename_match}[/bold red]")
                    try:
                        if tracker_name in ["AITHER", "LST"]:
                            logger.info(f"[yellow]{tracker_name} supports automatic trumping of exact matches, if the file is allowed to be trumped.[/yellow]")
                            upload = await self.prompt_yes_no(f"Are you trumping this exact match on {tracker_name}?", default=False)
                            if upload:
                                meta.we_asked = True
                                meta.were_trumping = True
                                meta.trump_reason = "exact_match"
                                if not meta.get(f"{tracker_name}_trumpable_id"):
                                    meta[f"{tracker_name}_trumpable_id"] = meta.get(f"{tracker_name}_matched_id", None)
                        else:
                            upload = await self.prompt_yes_no(f"Upload to {tracker_name} anyway?", default=False)
                            meta.we_asked = True
                    except EOFError:
                        logger.info("\n[red]Exiting on user request (Ctrl+C)[/red]")
                        await cleanup_manager.cleanup()
                        cleanup_manager.reset_terminal()
                        sys.exit(1)
                elif dupes_list:
                    # Rebuild dupe_text in case dupes was filtered after trump decline
                    dupe_text = _format_dupes_list(dupes_list)
                    if meta.season_pack_exists:
                        # Display only the matched season pack info from dupe_checking
                        season_pack_name = meta.season_pack_name
                        season_pack_link = meta.season_pack_link
                        season_pack_text = format_terminal_link(season_pack_name, season_pack_link, self.default_config) if season_pack_link else season_pack_name
                        logger.info(f"[yellow]Note: A season pack exists on {tracker_name}[/yellow]")
                        logger.info("[yellow]Ensure your upload is not part of that season pack, or is otherwise allowed.[/yellow]")
                        logger.info("")
                        logger.info(f"[bold cyan]{season_pack_text}[/bold cyan]")
                    else:
                        logger.info(f"[bold blue]{tracker_name}[/bold blue]: Check if these are actually dupes:")
                        logger.info("")
                        logger.info(f"[bold cyan]{dupe_text}[/bold cyan]", extra={"highlighter": None})
                    if meta.dupe is False:
                        try:
                            if meta.is_disc == "BDMV":
                                await self.ask_bdinfo_comparison(meta, dupes_list, tracker_name)
                            upload = await self.prompt_yes_no(f"Upload to {tracker_name} anyway?", default=False)
                            meta.we_asked = True
                        except EOFError:
                            logger.info("\n[red]Exiting on user request (Ctrl+C)[/red]")
                            await cleanup_manager.cleanup()
                            cleanup_manager.reset_terminal()
                            sys.exit(1)
                    else:
                        upload = True
                else:
                    # dupes list was emptied after filtering (e.g., season pack declined trump, no other dupes)
                    upload = True

        else:
            upload = meta.dupe is not False

        display_name = display_name if display_name is not None else meta.name
        display_name = display_name

        if tracker_name in ["BEYONDHD"]:
            logger.debug("[yellow]BEYONDHD cross seeding check[/yellow]")
            tracker_download_link = meta.get(f"{tracker_name}_matched_download")
            # Ensure display_name is a string before using 'in' operator
            if display_name:
                edition = meta.edition
                region = meta.region
                if edition and edition in display_name:
                    display_name = display_name.replace(f"{edition} ", "")
                if region and region in display_name:
                    display_name = display_name.replace(f"{region} ", "")
            for d in dupes_list:
                if isinstance(d, dict):
                    entry_name = str(d.get("name", "")).lower()
                    similarity = SequenceMatcher(None, entry_name, display_name.lower().strip()).ratio()
                    if similarity > 0.9 and meta.size_match and tracker_download_link:
                        meta[f"{tracker_name}_cross_seed"] = tracker_download_link
                        logger.debug(f"[bold red]Cross-seed link saved for {tracker_name}: {Redaction.redact_private_info(tracker_download_link)}.[/bold red]")
                        break

        elif meta.filename_match and meta.file_count_match:
            logger.debug(f"[yellow]{tracker_name} filename and file count cross seeding check[/yellow]")
            tracker_download_link = meta.get(f"{tracker_name}_matched_download")
            for d in dupes_list:
                if isinstance(d, dict) and tracker_download_link:
                    meta[f"{tracker_name}_cross_seed"] = tracker_download_link
                    logger.debug(f"[bold red]Cross-seed link saved for {tracker_name}: {Redaction.redact_private_info(tracker_download_link)}.[/bold red]")
                    break

        elif meta.size_match:
            logger.debug(f"[yellow]{tracker_name} size cross seeding check[/yellow]")
            tracker_download_link = meta.get(f"{tracker_name}_matched_download")
            for d in dupes_list:
                if isinstance(d, dict):
                    entry_name = str(d.get("name", "")).lower()
                    similarity = SequenceMatcher(None, entry_name, display_name.lower().strip()).ratio()
                    logger.debug(f"[debug] Comparing sizes with similarity {similarity:.4f}")
                    if similarity > 0.9 and tracker_download_link:
                        meta[f"{tracker_name}_cross_seed"] = tracker_download_link
                        logger.debug(f"[bold red]Cross-seed link saved for {tracker_name}: {Redaction.redact_private_info(tracker_download_link)}.[/bold red]")
                        break

        if upload is False:
            return True, meta
        for each in dupes_list:
            each_name = str(each.get("name")) if isinstance(each, dict) else each
            if each_name == meta.name:
                meta.name = f"{meta.name} DUPE?"

        return False, meta

    async def ask_bdinfo_comparison(self, meta: Meta, dupes: list[DupeEntry | str], tracker_name: str) -> None:
        """
        Check if any duplicate has BDInfo content and ask the user
        if they want to perform a comparison.
        """
        possible = any(isinstance(entry, dict) and has_bdinfo_content(entry) for entry in dupes)

        if not possible:
            return

        question = "[bold magenta]Found BDInfo content in potential duplicates.[/bold magenta] Perform a comparison?"
        if await self.prompt_yes_no(question, default=True):
            warnings: list[str] = []
            results: list[str] = []

            for entry in dupes:
                if not isinstance(entry, dict):
                    continue

                warning_message, results_message = compare_bdinfo(meta, entry, tracker_name)

                if warning_message:
                    warnings.append(warning_message)
                if results_message:
                    results.append(results_message)

            if warnings:
                logger.info("")
                logger.info("\n\n".join(warnings))

            if results:
                logger.info("")
                logger.info("\n".join(results))
                logger.info("")

    async def get_confirmation(self, meta: Meta) -> bool:
        confirm: bool = False
        lines: list[str | tuple[str, str]] = []
        missing_warning = "[bold red]⚠️ Missing[/bold red]"
        if meta.debug is True:
            lines.append("[bold red]DEBUG: True - Will not actually upload![/bold red]")
            lines.append(f"Prep material saved to {meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}")
        lines.append("")
        lines.append(("Title", f"{meta.title} ({meta.year})"))
        lines.append(("Category", meta.category))
        edition = meta.edition

        # BOOK
        if meta.category == "BOOK":
            author = meta.author or missing_warning
            book_translator = meta.book_translator or ""
            publisher = meta.publisher or ""  # not essential
            book_language = meta.book_language or missing_warning
            isbn = meta.isbn or ""  # not essential
            asin = meta.asin or ""  # not essential
            narrator = meta.narrator or missing_warning
            audiobook_duration_formatted = meta.audiobook_duration_formatted or missing_warning
            poster = "Found" if bool(meta.artwork_url or meta.artwork_path) else missing_warning
            comic = meta.comic
            manga = meta.manga
            magazine = meta.magazine
            newspaper = meta.newspaper

            def format_value(value: bool) -> str:
                return "[green]True[/green]" if value else "[purple]False[/purple]"

            lines.append(("Author", author))
            if book_translator:
                lines.append(("Translator", book_translator))
            lines.append(("Publisher", publisher))
            lines.append(("Language", book_language))
            lines.append(("ISBN", isbn))
            lines.append(("ASIN", asin))
            lines.append(("Comic", format_value(comic)))
            lines.append(("Manga", format_value(manga)))
            lines.append(("Magazine", format_value(magazine)))
            lines.append(("Newspaper", format_value(newspaper)))
            if meta.audiobook:
                lines.append(("Narrator", narrator))
                lines.append(("Duration", audiobook_duration_formatted))
            lines.append(("Cover", poster))

        elif meta.category == "GAME":
            notes = meta.description_link or meta.description_file or ""
            if notes:
                # don't leak links or file paths
                notes = notes[:16] if notes.startswith("http") else f"./{Path(notes).name}"
            if meta.platform == "PC":
                notes = notes if notes else "[yellow][italic]Installation instructions missing. Use -df or -dp to add them.[/italic][/yellow]"

            game_subcategory_str = {"full_game": "Full Game", "full_game_dlc": "Full Game + DLC", "dlc": "DLC", "update": "Update"}.get(meta.game_subcategory, "Unknown")
            game_subcategory = f"[italic]{meta.game_subcategory}[/italic] ({game_subcategory_str})"
            version = meta.game_version or missing_warning
            developer = meta.developer or missing_warning
            publisher = meta.publisher or missing_warning
            platform = meta.platform or missing_warning
            poster = "Found" if bool(meta.artwork_url or meta.artwork_path) else missing_warning
            igdb_id = meta.igdb_id or "0"
            steam_url = meta.steam_url
            languages = len(meta.languages) if meta.languages else missing_warning

            lines.append(("Subcategory", game_subcategory))
            lines.append(("Version", version))
            if notes:
                lines.append(("Notes", notes))
            lines.append(("Developer", developer))
            lines.append(("Publisher", publisher))
            lines.append(("Platform", platform))
            lines.append(("Cover", poster))
            if int(igdb_id) > 0:
                lines.append(("IGDB", str(igdb_id)))
            if steam_url:
                lines.append(("Steam", steam_url))
            if languages:
                if isinstance(languages, dict):
                    lang_summary = ", ".join(f"{lang} ({'/'.join(supports)})" for lang, supports in languages.items())
                elif isinstance(languages, list):
                    lang_summary = ", ".join(languages)
                else:
                    lang_summary = str(languages)
                lines.append(("Languages", lang_summary))

        if meta.category == "MUSIC":
            lines.extend(_music_confirmation_lines(meta, missing_warning))
        else:
            lines.append(("Overview", f"{meta.overview[:60]}...."))
            if meta.category == "TV" and not meta.tv_pack and meta.auto_episode_title:
                lines.append(("Episode Title", (meta.auto_episode_title)))
            if meta.category == "TV" and not meta.tv_pack and meta.overview_meta:
                lines.append(("Episode overview:", meta.overview_meta[:60] + "...."))
            lines.append(("Genre", ", ".join(meta.genres)))
            if meta.demographic != "":
                lines.append(("Demographic", meta.demographic))

            if meta.tmdb_id or 0 != 0:
                lines.append(("TMDB", f"https://www.themoviedb.org/{(meta.category or '').lower()}/{meta.tmdb_id}"))
            if meta.imdb_id or 0 != 0:
                lines.append(("IMDB", f"https://www.imdb.com/title/tt{meta.imdb}"))
            if meta.tvdb_id or 0 != 0:
                lines.append(("TVDB", f"https://www.thetvdb.com/?id={meta.tvdb_id}&tab=series"))
            if meta.tvmaze_id or 0 != 0:
                lines.append(("TVMaze", f"https://www.thetvmaze.com/shows/{meta.tvmaze_id}"))
            if meta.mal_id or 0 != 0:
                lines.append(("MAL", f"https://myanimelist.net/anime/{meta.mal_id}"))

            resolution = meta.resolution
            source = meta.source
            type_ = meta.type or ""
            tag = meta.tag or ""
            if tag and tag.startswith("-"):
                tag = tag[1:]
            region = meta.region or missing_warning
            distributor = meta.distributor or missing_warning
            edition = meta.edition

            lines.append(("Edition", edition))
            lines.append(("Resolution", resolution))
            lines.append(("Source", str(source)))
            lines.append(("Type", type_))

            if meta.category != "BOOK":
                lines.append(("Group Tag", tag))

            if meta.is_disc:
                lines.append(("Region", region))
                lines.append(("Distributor", distributor))

            if meta.freeleech != 0:
                lines.append(("Freeleech", str(meta.freeleech)))
        lines.append("")

        if meta.personalrelease is True:
            lines.append("[bold green]Personal Release![/bold green]")

        # Format and align labels and values
        max_label_len = 0
        for item in lines:
            if isinstance(item, tuple):
                label, _ = item
                if len(label) > max_label_len:
                    max_label_len = len(label)

        formatted_lines: list[str] = []
        for item in lines:
            if isinstance(item, tuple):
                label, value = item
                padding = f"[white]{'.' * (max_label_len - len(label))}[/white]"
                formatted_lines.append(f"[bold cyan]{label}[/bold cyan]{padding} {value}")
            else:
                formatted_lines.append(item)

        logger.info("\n".join(formatted_lines), extra={"highlighter": None})

        if meta.unattended and not meta.unattended_confirm:
            if meta.debug is True:
                logger.info("[bold yellow]Unattended mode is enabled, skipping confirmation.[/bold yellow]")
            return True
        ring_the_bell = "\a" if bool(self.default_config.get("sfx_on_prompt", True)) else ""
        if ring_the_bell:
            logger.info(ring_the_bell)

        if meta.is_disc:
            meta.keep_folder = False

        if meta.keep_folder and meta.isdir:
            kf_confirm = await self.prompt_yes_no(
                "You specified --keep-folder. Uploading in folders might not be allowed. Proceed?",
                default=False,
            )
            if not kf_confirm:
                logger.info("[bold red]Aborting...[/bold red]")
                exit()
        tracker_release_names: dict[str, str] = {}
        for tracker_name in meta.trackers:
            if tracker_name in ("MANUAL", "USENET"):
                continue
            with contextlib.suppress(Exception):
                tracker_class_factory = cast(Callable[..., Any], self.tracker_class_map.get(tracker_name))
                if not tracker_class_factory:
                    continue
                tracker_class = tracker_class_factory(config=self.config)
                try:
                    tracker_rename = await tracker_class.get_name(meta)
                    if isinstance(tracker_rename, dict) and len(tracker_rename) == 1:
                        tracker_rename = str(next(iter(tracker_rename.values())))
                except Exception as e:
                    logger.error(f"Error: {e}")
                    tracker_rename = None

                display_name = None
                if tracker_rename is not None:
                    if isinstance(tracker_rename, dict) and "name" in tracker_rename:
                        tracker_rename_dict = cast(dict[str, Any], tracker_rename)
                        display_name = str(tracker_rename_dict.get("name", ""))
                    elif isinstance(tracker_rename, str):
                        display_name = tracker_rename

                if display_name:
                    tracker_release_names[tracker_name] = display_name

        if tracker_release_names:
            logger.info(f"[bold]Base Name:[/bold] {meta.name}\n", extra={"highlighter": None})
            max_t_len = max(len(t) for t in tracker_release_names)
            for t_name, d_name in sorted(tracker_release_names.items()):
                prefix = f"{t_name}:".ljust(max_t_len + 1)
                logger.info(f"{prefix} {d_name}", extra={"highlighter": None})
            logger.info("")
        else:
            logger.info(f"[bold]Base Name:[/bold] {meta.name}\n", extra={"highlighter": None})

        confirm = await self.prompt_yes_no("Is this correct?")
        logger.info("")

        if confirm:
            if (
                meta.original_imdb == meta.imdb_id
                and meta.original_tmdb == meta.tmdb_id
                and meta.original_mal == meta.mal_id
                and meta.original_tvmaze == meta.tvmaze_id
                and meta.original_tvdb == meta.tvdb_id
                and meta.original_category == meta.category
            ):
                logger.info("[bold yellow]Database ID's are correct![/bold yellow]")
                return True
            nfo_dir = Path(f"{meta.base_dir}/data")
            Path(nfo_dir).mkdir(parents=True, exist_ok=True)
            json_file_path = Path(nfo_dir) / "db_check.json"

            def imdb_url(imdb_id: Any) -> str | None:
                return f"https://www.imdb.com/title/tt{str(imdb_id).zfill(7)}" if imdb_id and str(imdb_id).isdigit() else None

            def tmdb_url(tmdb_id: Any, category: Any) -> str | None:
                return f"https://www.themoviedb.org/{str(category).lower()}/{tmdb_id}" if tmdb_id and category else None

            def tvdb_url(tvdb_id: Any) -> str | None:
                return f"https://www.thetvdb.com/?id={tvdb_id}&tab=series" if tvdb_id else None

            def tvmaze_url(tvmaze_id: Any) -> str | None:
                return f"https://www.tvmaze.com/shows/{tvmaze_id}" if tvmaze_id else None

            def mal_url(mal_id: Any) -> str | None:
                return f"https://myanimelist.net/anime/{mal_id}" if mal_id else None

            db_check_entry: dict[str, Any] = {
                "path": meta.path,
                "original": {
                    "imdb_id": (meta.original_imdb if meta.original_imdb is not None else "N/A"),
                    "imdb_url": imdb_url(meta.original_imdb),
                    "tmdb_id": (meta.original_tmdb if meta.original_tmdb is not None else "N/A"),
                    "tmdb_url": tmdb_url(meta.original_tmdb, meta.original_category),
                    "tvdb_id": (meta.original_tvdb if meta.original_tvdb is not None else "N/A"),
                    "tvdb_url": tvdb_url(meta.original_tvdb),
                    "tvmaze_id": (meta.original_tvmaze if meta.original_tvmaze is not None else "N/A"),
                    "tvmaze_url": tvmaze_url(meta.original_tvmaze),
                    "mal_id": (meta.original_mal if meta.original_mal is not None else "N/A"),
                    "mal_url": mal_url(meta.original_mal),
                    "category": (meta.original_category if meta.original_category is not None else "N/A"),
                },
                "changed": {
                    "imdb_id": (meta.imdb_id if meta.imdb_id is not None else "N/A"),
                    "imdb_url": imdb_url(meta.imdb_id),
                    "tmdb_id": (meta.tmdb_id if meta.tmdb_id is not None else "N/A"),
                    "tmdb_url": tmdb_url(meta.tmdb_id, meta.category),
                    "tvdb_id": (meta.tvdb_id if meta.tvdb_id is not None else "N/A"),
                    "tvdb_url": tvdb_url(meta.tvdb_id),
                    "tvmaze_id": (meta.tvmaze_id if meta.tvmaze_id is not None else "N/A"),
                    "tvmaze_url": tvmaze_url(meta.tvmaze_id),
                    "mal_id": (meta.mal_id if meta.mal_id is not None else "N/A"),
                    "mal_url": mal_url(meta.mal_id),
                    "category": (meta.category if meta.category is not None else "N/A"),
                },
                "tracker": (meta.matched_tracker if meta.matched_tracker is not None else "N/A"),
            }

            # Append to JSON file (as a list of entries)
            db_data_list: list[dict[str, Any]] = []
            if Path(json_file_path).exists():
                async with aiofiles.open(json_file_path, encoding="utf-8") as f:
                    try:
                        file_contents = await f.read()
                        if file_contents:
                            parsed_data = json.loads(file_contents)
                            if isinstance(parsed_data, list):
                                db_data_list = cast(list[dict[str, Any]], parsed_data)
                    except Exception:
                        db_data_list = []
            db_data_list.append(db_check_entry)

            async with aiofiles.open(json_file_path, "w", encoding="utf-8") as f:
                await f.write(json.dumps(db_data_list, indent=2, ensure_ascii=False))
            return True

        return confirm
