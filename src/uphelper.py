# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import json
import os
import re
import sys
from collections.abc import Mapping
from difflib import SequenceMatcher
from typing import Any, Callable, Optional, Union, cast

import aiofiles
import cli_ui
from rich.markup import escape

from cogs.redaction import Redaction
from src.bdinfo_comparator import compare_bdinfo, has_bdinfo_content
from src.cleanup import cleanup_manager
from src.console import console
from src.trackersetup import tracker_class_map

Meta = dict[str, Any]
DupeEntry = dict[str, Any]


def parse_size_to_bytes(size_str: Any) -> Optional[int]:
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
                        if unit in ("tb", "tib", "pb", "pib"):
                            # A large unit like TiB/TB indicates a decimal fraction (e.g., 1.544 TiB)
                            s = s.replace(",", ".")
                        else:
                            # For B, KB, MB, GB, etc., it is a thousands separator (e.g., 1,024 MB)
                            s = s.replace(",", "")
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


def hsl_to_rgb(h: float, s: float, l: float) -> tuple[int, int, int]:
    # h in [0, 360], s in [0, 1], l in [0, 1]
    c = (1.0 - abs(2.0 * l - 1.0)) * s
    x = c * (1.0 - abs((h / 60.0) % 2.0 - 1.0))
    m = l - c / 2.0
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
        self.default_config = cast(Mapping[str, Any], config.get('DEFAULT', {}))
        if not isinstance(self.default_config, dict):
            raise ValueError("'DEFAULT' config section must be a dict")
        self.tracker_class_map = cast(Mapping[str, Any], tracker_class_map)

    async def dupe_check(self, dupes: list[Union[DupeEntry, str]], meta: Meta, tracker_name: str) -> tuple[bool, Meta]:
        def _format_dupe(entry: Union[DupeEntry, str]) -> str:
            if isinstance(entry, dict):
                name = str(entry.get('name', ''))
                link = entry.get('link')

                size_diff_str = ""
                if self.default_config.get("show_dupe_size_diff", True):
                    upload_size = meta.get("source_size")
                    dupe_size_raw = entry.get("size")
                    dupe_size = parse_size_to_bytes(dupe_size_raw)
                    if upload_size and dupe_size:
                        diff_bytes = dupe_size - upload_size
                        diff_mb = int(round(diff_bytes / (1024 * 1024)))
                        diff_pct = int(round((diff_bytes / upload_size) * 100))

                        p = abs(diff_pct) / 100.0
                        color_hex = get_color_for_diff(p)
                        size_diff_str = f" - [#{color_hex}][{diff_mb:+d} MB / {diff_pct:+d}%][/]"

                if isinstance(link, str) and link:
                    if self.default_config.get("embed_dupe_links", True):
                        return f"[link={link}]{escape(name)}[/link]{size_diff_str}"
                    else:
                        return f"{name} - {link}{size_diff_str}"
                return f"{name}{size_diff_str}"
            return str(entry)

        def _format_dupes_list(entries: list[Union[DupeEntry, str]]) -> str:
            seen = set()
            formatted = []
            for entry in entries:
                if isinstance(entry, dict) and entry.get("link"):
                    link = entry.get("link")
                    if link in seen:
                        continue
                    seen.add(link)
                formatted.append(_format_dupe(entry))
            return "\n".join(formatted)

        dupes_list: list[Union[DupeEntry, str]] = dupes
        upload: bool = False
        meta['were_trumping'] = False
        if not dupes_list:
            if meta['debug']:
                console.print(f"[green]No dupes found at[/green] [yellow]{tracker_name}[/yellow]")
            return False,  meta
        else:
            tracker_class_factory = cast(Callable[..., Any], self.tracker_class_map[tracker_name])
            tracker_class = tracker_class_factory(config=self.config)
            try:
                tracker_rename = await tracker_class.get_name(meta)
            except Exception:
                try:
                    tracker_rename = await tracker_class.edit_name(meta)
                except Exception:
                    tracker_rename = None
            display_name: Optional[str] = None
            if tracker_rename is not None:
                if isinstance(tracker_rename, dict) and 'name' in tracker_rename:
                    tracker_rename_dict = cast(dict[str, Any], tracker_rename)
                    display_name = str(tracker_rename_dict.get('name', ''))
                elif isinstance(tracker_rename, str):
                    display_name = tracker_rename

            # Show naming change before dupe prompts so user knows what the final name will be
            if display_name is not None and display_name != "" and display_name != meta.get('name', ''):
                console.print(f"[bold yellow]{tracker_name} applies a naming change for this release: [green]{display_name}[/green][/bold yellow]")

            trumpable_text = None
            if meta.get('trumpable_id') or (meta.get('season_pack_contains_episode') and meta.get(f'{tracker_name}_matched_episode_ids', [])):
                trumpable_dupes = [
                    entry
                    for entry in dupes_list
                    if isinstance(entry, dict) and entry.get('trumpable')
                ]
                if trumpable_dupes:
                    trumpable_text = _format_dupes_list(trumpable_dupes)
                    console.print("[bold red]Trumpable found![/bold red]")
                elif meta.get('season_pack_contains_episode') and meta.get(f'{tracker_name}_matched_episode_ids', []):
                    matched_episodes = cast(list[DupeEntry], meta.get(f'{tracker_name}_matched_episode_ids', []))
                    user_tag = str(meta.get('tag', '')).lstrip('-').lower()  # Remove leading dash for comparison

                    # Try to find a release with matching tag
                    selected_match = None
                    tag_matched = False
                    if user_tag:
                        for ep in matched_episodes:
                            ep_name = str(ep.get('name', '')).lower()
                            # Tag typically appears at end of name like "H.265-ETHEL"
                            if ep_name.endswith(user_tag) or f"-{user_tag}" in ep_name:
                                selected_match = ep
                                tag_matched = True
                                break

                    # Fall back to first match if no tag match found
                    if not selected_match:
                        selected_match = matched_episodes[0]

                    trumpable_text = _format_dupe(selected_match)
                    console.print("[bold red]Trumpable found based on episode matching![/bold red]")

                    if user_tag and not tag_matched:
                        console.print(f"[yellow]Note: No release found with matching tag '{meta.get('tag')}'. Selected release may be from a different group.[/yellow]")

            if (not meta['unattended'] or (meta['unattended'] and meta.get('unattended_confirm', False))) and not meta.get('ask_dupe', False):
                dupe_text = _format_dupes_list(dupes_list)

                if trumpable_text and (meta.get('trumpable_id') or (meta.get('season_pack_contains_episode') and meta.get(f'{tracker_name}_matched_episode_ids', []))):
                    console.print(f"[bold cyan]{trumpable_text}[/bold cyan]")
                    console.print("[yellow]Please check the trumpable entries above to see if you want to upload[/yellow]")
                    console.print("[yellow]You will have the option to report the trumpable torrent if you upload.[/yellow]")
                    if meta.get('dupe', False) is False:
                        try:
                            upload = cli_ui.ask_yes_no("Are you trumping this release?", default=False)
                            if upload:
                                meta['we_asked'] = True
                                meta['were_trumping'] = True
                                if not meta.get(f'{tracker_name}_trumpable_id'):
                                    meta[f'{tracker_name}_trumpable_id'] = meta.get(f'{tracker_name}_matched_id', None)
                                if meta.get('filename_match', False) and meta.get('file_count_match', False):
                                    meta['trump_reason'] = 'exact_match'
                                else:
                                    meta['trump_reason'] = 'trumpable_release'
                                if meta['debug']:
                                    console.print(f"[bold green]Trump reason: {meta['trump_reason']} on {tracker_name}[/bold green]")
                            else:
                                # For season packs: individual episodes are only in dupes for trumping purposes.
                                # If user declines to trump, filter them out so they aren't shown as "potential dupes"
                                # (they wouldn't match season/episode anyway).
                                if meta.get('tv_pack') and meta.get('season_pack_contains_episode') and meta.get(f'{tracker_name}_matched_episode_ids', []):
                                    matched_ids = {ep.get('id') for ep in meta.get(f'{tracker_name}_matched_episode_ids', []) if ep.get('id')}
                                    dupes_list = [
                                        d for d in dupes_list
                                        if not (isinstance(d, dict) and d.get('id') in matched_ids)
                                    ]
                                    # Clear tracker-specific matched_episode_ids since we're not trumping
                                    meta[f'{tracker_name}_matched_episode_ids'] = []
                        except EOFError:
                            console.print("\n[red]Exiting on user request (Ctrl+C)[/red]")
                            await cleanup_manager.cleanup()
                            cleanup_manager.reset_terminal()
                            sys.exit(1)

                if not meta.get('were_trumping', False):
                    if meta.get('filename_match', False) and meta.get('file_count_match', False):
                        console.print(f'[bold red]Exact match found! - {meta["filename_match"]}[/bold red]')
                        try:
                            if tracker_name in ["AITHER", "LST"]:
                                console.print(f"[yellow]{tracker_name} supports automatic trumping of exact matches, if the file is allowed to be trumped.[/yellow]")
                                upload = cli_ui.ask_yes_no("Are you trumping this exact match?", default=False)
                                if upload:
                                    meta['we_asked'] = True
                                    meta['were_trumping'] = True
                                    meta['trump_reason'] = 'exact_match'
                                    if not meta.get(f'{tracker_name}_trumpable_id'):
                                        meta[f'{tracker_name}_trumpable_id'] = meta.get(f'{tracker_name}_matched_id', None)
                            else:
                                upload = cli_ui.ask_yes_no(f"Upload to {tracker_name} anyway?", default=False)
                                meta['we_asked'] = True
                        except EOFError:
                            console.print("\n[red]Exiting on user request (Ctrl+C)[/red]")
                            await cleanup_manager.cleanup()
                            cleanup_manager.reset_terminal()
                            sys.exit(1)
                    elif dupes_list:
                        # Rebuild dupe_text in case dupes was filtered after trump decline
                        dupe_text = _format_dupes_list(dupes_list)
                        if meta.get('season_pack_exists', False):
                            # Display only the matched season pack info from dupe_checking
                            season_pack_name = meta.get('season_pack_name', '')
                            season_pack_link = meta.get('season_pack_link')
                            if season_pack_link:
                                if self.default_config.get("embed_dupe_links", False):
                                    season_pack_text = f"[link={season_pack_link}]{escape(season_pack_name)}[/link]"
                                else:
                                    season_pack_text = f"{season_pack_name} - {season_pack_link}"
                            else:
                                season_pack_text = season_pack_name
                            console.print(f"[yellow]Note: A season pack exists on {tracker_name}[/yellow]")
                            console.print("[yellow]Ensure your upload is not part of that season pack, or is otherwise allowed.[/yellow]")
                            console.print()
                            console.print(f"[bold cyan]{season_pack_text}[/bold cyan]")
                        else:
                            console.print(f"[bold blue]Check if these are actually dupes from {tracker_name}:[/bold blue]")
                            console.print()
                            console.print(f"[bold cyan]{dupe_text}[/bold cyan]")
                        if meta.get('dupe', False) is False:
                            try:
                                if meta.get('is_disc') == "BDMV":
                                    self.ask_bdinfo_comparison(meta, dupes_list, tracker_name)
                                upload = cli_ui.ask_yes_no(f"Upload to {tracker_name} anyway?", default=False)
                                meta['we_asked'] = True
                            except EOFError:
                                console.print("\n[red]Exiting on user request (Ctrl+C)[/red]")
                                await cleanup_manager.cleanup()
                                cleanup_manager.reset_terminal()
                                sys.exit(1)
                        else:
                            upload = True
                    else:
                        # dupes list was emptied after filtering (e.g., season pack declined trump, no other dupes)
                        upload = True

            else:
                upload = meta.get('dupe', False) is not False

            display_name = display_name if display_name is not None else str(meta.get('name', ''))
            display_name = str(display_name)

            if tracker_name in ["BHD"]:
                if meta['debug']:
                    console.print("[yellow]BHD cross seeding check[/yellow]")
                tracker_download_link = meta.get(f'{tracker_name}_matched_download')
                # Ensure display_name is a string before using 'in' operator
                if display_name:
                    edition = meta.get('edition', '')
                    region = meta.get('region', '')
                    if edition and edition in display_name:
                        display_name = display_name.replace(f"{edition} ", "")
                    if region and region in display_name:
                        display_name = display_name.replace(f"{region} ", "")
                for d in dupes_list:
                    if isinstance(d, dict):
                        entry_name = str(d.get('name', '')).lower()
                        similarity = SequenceMatcher(None, entry_name, display_name.lower().strip()).ratio()
                        if similarity > 0.9 and meta.get('size_match', False) and tracker_download_link:
                            meta[f'{tracker_name}_cross_seed'] = tracker_download_link
                            if meta['debug']:
                                console.print(f'[bold red]Cross-seed link saved for {tracker_name}: {Redaction.redact_private_info(tracker_download_link)}.[/bold red]')
                            break

            elif meta.get('filename_match', False) and meta.get('file_count_match', False):
                if meta['debug']:
                    console.print(f"[yellow]{tracker_name} filename and file count cross seeding check[/yellow]")
                tracker_download_link = meta.get(f'{tracker_name}_matched_download')
                for d in dupes_list:
                    if isinstance(d, dict) and tracker_download_link:
                        meta[f'{tracker_name}_cross_seed'] = tracker_download_link
                        if meta['debug']:
                            console.print(f'[bold red]Cross-seed link saved for {tracker_name}: {Redaction.redact_private_info(tracker_download_link)}.[/bold red]')
                        break

            elif meta.get('size_match', False):
                if meta['debug']:
                    console.print(f"[yellow]{tracker_name} size cross seeding check[/yellow]")
                tracker_download_link = meta.get(f'{tracker_name}_matched_download')
                for d in dupes_list:
                    if isinstance(d, dict):
                        entry_name = str(d.get('name', '')).lower()
                        similarity = SequenceMatcher(None, entry_name, display_name.lower().strip()).ratio()
                        if meta['debug']:
                            console.print(f"[debug] Comparing sizes with similarity {similarity:.4f}")
                        if similarity > 0.9 and tracker_download_link:
                            meta[f'{tracker_name}_cross_seed'] = tracker_download_link
                            if meta['debug']:
                                console.print(f'[bold red]Cross-seed link saved for {tracker_name}: {Redaction.redact_private_info(tracker_download_link)}.[/bold red]')
                            break

            if upload is False:
                return True, meta
            else:
                for each in dupes_list:
                    each_name = str(each.get('name')) if isinstance(each, dict) else str(each)
                    if each_name == meta['name']:
                        meta['name'] = f"{meta['name']} DUPE?"

                return False, meta

    def ask_bdinfo_comparison(self, meta: Meta, dupes: list[Union[DupeEntry, str]], tracker_name: str) -> None:
        """
        Check if any duplicate has BDInfo content and ask the user
        if they want to perform a comparison.
        """
        possible = any(
            isinstance(entry, dict) and has_bdinfo_content(entry)
            for entry in dupes
        )

        if not possible:
            return

        question = (
            "\033[1;35mFound BDInfo content in potential duplicates."
            "\033[0m Perform a comparison?"
        )
        if cli_ui.ask_yes_no(question, default=True):
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
                console.print()
                console.print("\n\n".join(warnings))

            if results:
                console.print()
                console.print("\n".join(results))
                console.print()

    async def get_confirmation(self, meta: Meta) -> bool:
        confirm: bool = False
        lines: list[Union[str, tuple[str, str]]] = []
        missing_warning = "[bold red]⚠️ Missing[/bold red]"
        if meta['debug'] is True:
            lines.append("[bold red]DEBUG: True - Will not actually upload![/bold red]")
            lines.append(f"Prep material saved to {meta['base_dir']}/tmp/{meta['uuid']}")
        lines.append("")
        lines.append(("Title", f"{meta['title']} ({meta['year']})"))
        lines.append(("Category", str(meta["category"])))
        edition = meta.get("edition")

        # BOOK
        if meta["category"] == "BOOK":
            author = meta.get("author") or missing_warning
            book_translator = meta.get("book_translator") or ""
            publisher = meta.get("publisher") or ""  # not essential
            book_language = meta.get("book_language") or missing_warning
            isbn = meta.get("isbn") or ""  # not essential
            asin = meta.get("asin") or ""  # not essential
            narrator = meta.get("narrator") or missing_warning
            audiobook_duration_formatted = meta.get("audiobook_duration_formatted") or missing_warning
            poster = meta.get("poster") or "[yellow][italic]not found online - will be auto-generated[/italic][/yellow]"
            comic = bool(meta.get("comic"))
            manga = bool(meta.get("manga"))
            magazine = bool(meta.get("magazine"))
            newspaper = bool(meta.get("newspaper"))

            def format_value(value: bool) -> str:
                return "[green]True[/green]" if value else "[purple]False[/purple]"

            lines.append(("Author", str(author)))
            if book_translator:
                lines.append(("Translator", str(book_translator)))
            lines.append(("Publisher", str(publisher)))
            lines.append(("Language", str(book_language)))
            lines.append(("ISBN", str(isbn)))
            lines.append(("ASIN", str(asin)))
            lines.append(("Comic", format_value(comic)))
            lines.append(("Manga", format_value(manga)))
            lines.append(("Magazine", format_value(magazine)))
            lines.append(("Newspaper", format_value(newspaper)))
            if meta.get("audiobook"):
                lines.append(("Narrator", str(narrator)))
                lines.append(("Duration", str(audiobook_duration_formatted)))
            lines.append(("Cover", str(poster)))

        elif meta["category"] == "GAME":
            notes = meta.get("description_link", "") or meta.get("description_file", "") or ""
            if notes:
                # don't leak links or file paths
                notes = notes[:16] if notes.startswith("http") else f"./{os.path.basename(notes)}"
            if meta.get("platform", "") == "PC":
                notes = notes if notes else "[yellow][italic]Installation instructions missing. Use -df or -dp to add them.[/italic][/yellow]"

            game_subcategory_str = {"full_game": "Full Game", "full_game_dlc": "Full Game + DLC", "dlc": "DLC", "update": "Update"}.get(meta["game_subcategory"], "Unknown")
            game_subcategory = f"[italic]{meta['game_subcategory']}[/italic] ({game_subcategory_str})"
            version = meta.get("game_version") or missing_warning
            developer = meta.get("developer") or missing_warning
            publisher = meta.get("publisher") or missing_warning
            platform = meta.get("platform") or missing_warning
            poster = meta.get("poster") or missing_warning
            igdb_id = meta.get("igdb_id") or "0"
            steam_url = meta.get("steam_url")
            languages = len(meta.get("languages", [])) if meta.get("languages") else missing_warning

            lines.append(("Subcategory", game_subcategory))
            lines.append(("Version", version))
            if notes:
                lines.append(("Notes", notes))
            lines.append(("Developer", str(developer)))
            lines.append(("Publisher", str(publisher)))
            lines.append(("Platform", str(platform)))
            lines.append(("Cover", str(poster)))
            if int(igdb_id) > 0:
                lines.append(("IGDB", str(igdb_id)))
            if steam_url:
                lines.append(("Steam", str(steam_url)))
            if languages:
                if isinstance(languages, dict):
                    lang_summary = ", ".join(f"{lang} ({'/'.join(supports)})" for lang, supports in languages.items())
                elif isinstance(languages, list):
                    lang_summary = ", ".join(languages)
                else:
                    lang_summary = str(languages)
                lines.append(("Languages", lang_summary))

        if not meta.get('emby', False):
            lines.append(("Overview", f"{meta['overview'][:60]}...."))
            if meta.get('category') == 'TV' and not meta.get('tv_pack') and meta.get('auto_episode_title'):
                lines.append(("Episode Title", str(meta["auto_episode_title"])))
            if meta.get('category') == 'TV' and not meta.get('tv_pack') and meta.get('overview_meta'):
                lines.append(("Episode overview", str(meta["overview_meta"])))
            lines.append(("Genre", str(meta["genres"])))
            if str(meta.get('demographic', '')) != '':
                lines.append(("Demographic", str(meta["demographic"])))
        if meta.get('emby_debug', False):
            if int(meta.get('original_imdb', 0)) != 0:
                imdb = str(meta.get('original_imdb', 0)).zfill(7)
                lines.append(("IMDB", f"https://www.imdb.com/title/tt{imdb}"))
            if int(meta.get('original_tmdb', 0)) != 0:
                lines.append(("TMDB", f"https://www.themoviedb.org/{meta['category'].lower()}/{meta['original_tmdb']}"))
            if int(meta.get('original_tvdb', 0)) != 0:
                lines.append(("TVDB", f"https://www.thetvdb.com/?id={meta['original_tvdb']}&tab=series"))
            if int(meta.get('original_tvmaze', 0)) != 0:
                lines.append(("TVMaze", f"https://www.tvmaze.com/shows/{meta['original_tvmaze']}"))
            if int(meta.get('original_mal', 0)) != 0:
                lines.append(("MAL", f"https://myanimelist.net/anime/{meta['original_mal']}"))
        else:
            if int(meta.get('tmdb_id') or 0) != 0:
                lines.append(("TMDB", f"https://www.themoviedb.org/{meta['category'].lower()}/{meta['tmdb_id']}"))
            if int(meta.get('imdb_id') or 0) != 0:
                lines.append(("IMDB", f"https://www.imdb.com/title/tt{meta['imdb']}"))
            if int(meta.get('tvdb_id') or 0) != 0:
                lines.append(("TVDB", f"https://www.thetvdb.com/?id={meta['tvdb_id']}&tab=series"))
            if int(meta.get('tvmaze_id') or 0) != 0:
                lines.append(("TVMaze", f"https://www.tvmaze.com/shows/{meta['tvmaze_id']}"))
            if int(meta.get('mal_id') or 0) != 0:
                lines.append(("MAL", f"https://myanimelist.net/anime/{meta['mal_id']}"))

        resolution = meta.get("resolution", "")
        source = meta.get("source", "")
        type_ = meta.get("type", "")
        tag = meta.get("tag", "")
        if tag and tag.startswith("-"):
            tag = tag[1:]
        region = meta.get("region") or missing_warning
        distributor = meta.get("distributor") or missing_warning
        edition = meta.get("edition", "")

        lines.append(("Edition", str(edition)))
        lines.append(("Resolution", str(resolution)))
        lines.append(("Source", str(source)))
        lines.append(("Type", str(type_)))
        lines.append(("Edition", str(edition)))

        if meta.get("category") != "BOOK":
            lines.append(("Group Tag", str(tag)))

        if meta.get("is_disc"):
            lines.append(("Region", str(region)))
            lines.append(("Distributor", str(distributor)))

        if not meta.get('emby', False):
            if int(meta.get('freeleech', 0)) != 0:
                lines.append(("Freeleech", str(meta["freeleech"])))
            lines.append("")

            if meta.get('personalrelease', False) is True:
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

        console.print("\n".join(formatted_lines), highlight=False)

        if meta.get('unattended', False) and not meta.get('unattended_confirm', False) and not meta.get('emby_debug', False):
            if meta['debug'] is True:
                console.print("[bold yellow]Unattended mode is enabled, skipping confirmation.[/bold yellow]")
            return True
        else:
            if not meta.get('emby', False):
                await self.get_missing(meta)
                ring_the_bell = "\a" if bool(self.default_config.get("sfx_on_prompt", True)) else ""
                if ring_the_bell:
                    console.print(ring_the_bell)

            if meta.get('is disc', False) is True:
                meta['keep_folder'] = False

            if meta.get('keep_folder') and meta['isdir']:
                kf_confirm = console.input("[bold yellow]You specified --keep-folder. Uploading in folders might not be allowed.[/bold yellow] [green]Proceed? y/N: [/green]").strip().lower()
                if kf_confirm != 'y':
                    console.print("[bold red]Aborting...[/bold red]")
                    exit()
            if not meta.get('emby', False):
                console.print(f"[bold]Base Name:[/bold] {meta['name']}\n", highlight=False)
                confirm = console.input("[bold green]Is this correct?[/bold green] [yellow]y/N[/yellow]: ").strip().lower() == 'y'
            elif not meta.get('emby_debug', False):
                confirm = console.input("[bold green]Is this correct?[/bold green] [yellow]y/N[/yellow]: ").strip().lower() == 'y'
        if meta.get('emby_debug', False):
            if meta.get('original_imdb', 0) != meta.get('imdb_id', 0):
                imdb = str(meta.get('imdb_id', 0)).zfill(7)
                console.print(f"[bold red]IMDB ID changed from {meta['original_imdb']} to {meta['imdb_id']}[/bold red]")
                console.print(f"[bold cyan]IMDB URL:[/bold cyan] [yellow]https://www.imdb.com/title/tt{imdb}[/yellow]")
            if meta.get('original_tmdb', 0) != meta.get('tmdb_id', 0):
                console.print(f"[bold red]TMDB ID changed from {meta['original_tmdb']} to {meta['tmdb_id']}[/bold red]")
                console.print(f"[bold cyan]TMDB URL:[/bold cyan] [yellow]https://www.themoviedb.org/{meta['category'].lower()}/{meta['tmdb_id']}[/yellow]")
            if meta.get('original_mal', 0) != meta.get('mal_id', 0):
                console.print(f"[bold red]MAL ID changed from {meta['original_mal']} to {meta['mal_id']}[/bold red]")
                console.print(f"[bold cyan]MAL URL:[/bold cyan] [yellow]https://myanimelist.net/anime/{meta['mal_id']}[/yellow]")
            if meta.get('original_tvmaze', 0) != meta.get('tvmaze_id', 0):
                console.print(f"[bold red]TVMaze ID changed from {meta['original_tvmaze']} to {meta['tvmaze_id']}[/bold red]")
                console.print(f"[bold cyan]TVMaze URL:[/bold cyan] [yellow]https://www.tvmaze.com/shows/{meta['tvmaze_id']}[/yellow]")
            if meta.get('original_tvdb', 0) != meta.get('tvdb_id', 0):
                console.print(f"[bold red]TVDB ID changed from {meta['original_tvdb']} to {meta['tvdb_id']}[/bold red]")
                console.print(f"[bold cyan]TVDB URL:[/bold cyan] [yellow]https://www.thetvdb.com/?id={meta['tvdb_id']}&tab=series[/yellow]")
            if meta.get('original_category', None) != meta.get('category', None):
                console.print(f"[bold red]Category changed from {meta['original_category']} to {meta['category']}[/bold red]")
            console.print(f"[bold cyan]Regex Title:[/bold cyan] [yellow]{meta.get('regex_title', 'N/A')}[/yellow], [bold cyan]Secondary Title:[/bold cyan] [yellow]{meta.get('regex_secondary_title', 'N/A')}[/yellow], [bold cyan]Year:[/bold cyan] [yellow]{meta.get('regex_year', 'N/A')}, [bold cyan]AKA:[/bold cyan] [yellow]{meta.get('aka', '')}[/yellow]")
            console.print()
            if meta.get('original_imdb', 0) == meta.get('imdb_id', 0) and meta.get('original_tmdb', 0) == meta.get('tmdb_id', 0) and meta.get('original_mal', 0) == meta.get('mal_id', 0) and meta.get('original_tvmaze', 0) == meta.get('tvmaze_id', 0) and meta.get('original_tvdb', 0) == meta.get('tvdb_id', 0) and meta.get('original_category', None) == meta.get('category', None):
                console.print("[bold yellow]Database ID's are correct![/bold yellow]")
                return True
            else:
                nfo_dir = os.path.join(f"{meta['base_dir']}/data")
                os.makedirs(nfo_dir, exist_ok=True)
                json_file_path = os.path.join(nfo_dir, "db_check.json")

                def imdb_url(imdb_id: Any) -> Optional[str]:
                    return f"https://www.imdb.com/title/tt{str(imdb_id).zfill(7)}" if imdb_id and str(imdb_id).isdigit() else None

                def tmdb_url(tmdb_id: Any, category: Any) -> Optional[str]:
                    return f"https://www.themoviedb.org/{str(category).lower()}/{tmdb_id}" if tmdb_id and category else None

                def tvdb_url(tvdb_id: Any) -> Optional[str]:
                    return f"https://www.thetvdb.com/?id={tvdb_id}&tab=series" if tvdb_id else None

                def tvmaze_url(tvmaze_id: Any) -> Optional[str]:
                    return f"https://www.tvmaze.com/shows/{tvmaze_id}" if tvmaze_id else None

                def mal_url(mal_id: Any) -> Optional[str]:
                    return f"https://myanimelist.net/anime/{mal_id}" if mal_id else None

                db_check_entry = {
                    "path": meta.get('path'),
                    "original": {
                        "imdb_id": meta.get('original_imdb', 'N/A'),
                        "imdb_url": imdb_url(meta.get('original_imdb')),
                        "tmdb_id": meta.get('original_tmdb', 'N/A'),
                        "tmdb_url": tmdb_url(meta.get('original_tmdb'), meta.get('original_category')),
                        "tvdb_id": meta.get('original_tvdb', 'N/A'),
                        "tvdb_url": tvdb_url(meta.get('original_tvdb')),
                        "tvmaze_id": meta.get('original_tvmaze', 'N/A'),
                        "tvmaze_url": tvmaze_url(meta.get('original_tvmaze')),
                        "mal_id": meta.get('original_mal', 'N/A'),
                        "mal_url": mal_url(meta.get('original_mal')),
                        "category": meta.get('original_category', 'N/A')
                    },
                    "changed": {
                        "imdb_id": meta.get('imdb_id', 'N/A'),
                        "imdb_url": imdb_url(meta.get('imdb_id')),
                        "tmdb_id": meta.get('tmdb_id', 'N/A'),
                        "tmdb_url": tmdb_url(meta.get('tmdb_id'), meta.get('category')),
                        "tvdb_id": meta.get('tvdb_id', 'N/A'),
                        "tvdb_url": tvdb_url(meta.get('tvdb_id')),
                        "tvmaze_id": meta.get('tvmaze_id', 'N/A'),
                        "tvmaze_url": tvmaze_url(meta.get('tvmaze_id')),
                        "mal_id": meta.get('mal_id', 'N/A'),
                        "mal_url": mal_url(meta.get('mal_id')),
                        "category": meta.get('category', 'N/A')
                    },
                    "tracker": meta.get('matched_tracker', 'N/A'),
                }

                # Append to JSON file (as a list of entries)
                db_data_list: list[dict[str, Any]] = []
                if os.path.exists(json_file_path):
                    async with aiofiles.open(json_file_path, encoding='utf-8') as f:
                        try:
                            file_contents = await f.read()
                            if file_contents:
                                parsed_data = json.loads(file_contents)
                                if isinstance(parsed_data, list):
                                    db_data_list = cast(list[dict[str, Any]], parsed_data)
                        except Exception:
                            db_data_list = []
                db_data_list.append(db_check_entry)

                async with aiofiles.open(json_file_path, 'w', encoding='utf-8') as f:
                    await f.write(json.dumps(db_data_list, indent=2, ensure_ascii=False))
                return True

        return confirm

    async def get_missing(self, meta: Meta) -> None:
        info_notes = {
            'edition': 'Special Edition/Release',
            'description': "Please include Remux/Encode Notes if possible",
            'service': "WEB Service e.g.(AMZN, NF)",
            'region': "Disc Region",
            'imdb': 'IMDb ID (tt1234567)',
            'distributor': "Disc Distributor e.g.(BFI, Criterion)"
        }
        potential_missing = cast(list[str], meta.get("potential_missing", []))
        if meta["category"] in ("TV", "MOVIE"):
            if meta.get("imdb_id", 0) == 0:
                meta["imdb_id"] = 0
                if "imdb_id" not in potential_missing:
                    potential_missing.append("imdb_id")
                    meta["potential_missing"] = potential_missing
            else:
                potential_missing = cast(list[str], meta.get("potential_missing", []))

        missing = [
            f"--{each} | {info_notes.get(each, '')}"
            for each in potential_missing
            if str(meta.get(each, '')).strip() in ["", "None", "0"]
        ]

        if missing:
            console.print("[bold yellow]Potentially missing information:[/bold yellow]")
            for each in missing:
                cli_ui.info(each)
                print()
