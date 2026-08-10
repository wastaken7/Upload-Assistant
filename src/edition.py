# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import cli_ui
import guessit

from src.console import logger, prompt_in_thread
from src.meta import Meta
from src.region import get_distributor

guessit_module: Any = cast(Any, guessit)
GuessitFn = Callable[[str, dict[str, Any] | None], dict[str, Any]]


def guessit_fn(value: str, options: dict[str, Any] | None = None) -> dict[str, Any]:
    return cast(dict[str, Any], guessit_module.guessit(value, options))


def _has_release_token(value: str, token: str) -> bool:
    """Return whether a scene-release marker appears as its own token.

    Release names commonly use dots, dashes, and spaces as separators.  A
    substring check is too broad here: for example, ``TV2`` is a broadcaster,
    not the ``V2`` marker for a repack.
    """
    return re.search(rf"(?<![A-Z0-9]){re.escape(token)}(?![A-Z0-9])", value, flags=re.IGNORECASE) is not None


def _strip_release_tokens(value: str) -> str:
    """Remove standalone release markers while preserving adjacent text."""
    return re.sub(r"(?<![A-Z0-9])(?:REPACK\d?|RERIP|PROPER\d?)(?![A-Z0-9])", "", value, flags=re.IGNORECASE).strip()


async def get_edition(video: str, bdinfo: dict[str, Any] | None, filelist: list[str], manual_edition: str | list[str], meta: Meta) -> tuple[str, str, bool]:
    edition = ""
    imdb_info = cast(dict[str, Any], meta.imdb_info)
    edition_details = cast(dict[str, dict[str, Any]], imdb_info.get("edition_details", {}))
    imdb_edition_count_value = imdb_info.get("edition_count", len(edition_details))
    try:
        imdb_edition_count = int(imdb_edition_count_value)
    except TypeError, ValueError:
        imdb_edition_count = len(edition_details)

    if meta.category == "MOVIE" and not meta.anime and edition_details and imdb_edition_count > 1 and not manual_edition:
        if meta.is_disc != "BDMV" and meta.mediainfo.get("media", {}).get("track"):
            mediainfo = meta.mediainfo
            tracks = cast(list[dict[str, Any]], mediainfo.get("media", {}).get("track", []))
            general_track = next((track for track in tracks if track.get("@type") == "General"), None)

            if general_track and general_track.get("Duration"):
                try:
                    media_duration_seconds = float(general_track["Duration"])
                    formatted_duration = format_duration(media_duration_seconds)
                    logger.debug(f"[cyan]Found media duration: {formatted_duration} ({media_duration_seconds} seconds)[/cyan]")

                    leeway_seconds = 50
                    matching_editions: list[dict[str, Any]] = []

                    # Find all matching editions
                    for edition_info in edition_details.values():
                        edition_seconds = float(edition_info.get("seconds", 0) or 0)
                        edition_formatted = format_duration(edition_seconds)
                        difference = abs(media_duration_seconds - edition_seconds)

                        if difference <= leeway_seconds:
                            attributes = edition_info.get("attributes")
                            attributes_list = attributes if isinstance(attributes, list) else []
                            has_attributes = bool(attributes_list)
                            logger.debug(
                                f"[green]Potential match: {edition_info.get('display_name', '')} - duration {edition_formatted}, difference: {format_duration(difference)}[/green]"
                            )

                            if has_attributes:
                                edition_name = " ".join(smart_title(str(attr)) for attr in attributes_list)

                                matching_editions.append(
                                    {
                                        "name": edition_name,
                                        "display_name": str(edition_info.get("display_name", "")),
                                        "has_attributes": bool(edition_info.get("attributes") and len(edition_info["attributes"]) > 0),
                                        "minutes": edition_info.get("minutes"),
                                        "difference": difference,
                                        "formatted_duration": edition_formatted,
                                    }
                                )
                            else:
                                logger.debug("[yellow]Edition without attributes are theatrical editions and skipped[/yellow]")

                    if len(matching_editions) > 1:
                        if not meta.unattended or (meta.unattended and meta.unattended_confirm):
                            logger.info(f"[yellow]Media file duration {formatted_duration} matches multiple editions:[/yellow]")
                            for i, ed in enumerate(matching_editions):
                                diff_formatted = format_duration(float(ed.get("difference", 0) or 0))
                                logger.info(
                                    f"[yellow]{i + 1}. [green]{ed.get('name', '')} ({ed.get('display_name', '')}, duration: {ed.get('formatted_duration', '')}, diff: {diff_formatted})[/yellow]"
                                )

                            try:
                                choice = (
                                    await prompt_in_thread(
                                        cli_ui.ask_string, f"Select edition number (1-{len(matching_editions)}) or press Enter to use the closest match:", default=""
                                    )
                                    or ""
                                )

                                if choice.strip() and choice.isdigit() and 1 <= int(choice) <= len(matching_editions):
                                    selected = matching_editions[int(choice) - 1]
                                else:
                                    selected = min(matching_editions, key=lambda x: float(x.get("difference", 0) or 0))
                                    logger.info(f"[yellow]Using closest match: {selected.get('name', '')}[/yellow]")
                            except Exception as e:
                                logger.error(f"[red]Error processing selection: {e}. Using closest match.[/red]")
                                selected = min(matching_editions, key=lambda x: float(x.get("difference", 0) or 0))
                        else:
                            selected = min(matching_editions, key=lambda x: float(x.get("difference", 0) or 0))
                            logger.info(f"[yellow]Multiple matches found in unattended mode. Using closest match: {selected.get('name', '')}[/yellow]")

                        edition = str(selected.get("name", "")) if selected.get("has_attributes") else ""

                        logger.info(f"[bold green]Setting edition from duration match: {edition}[/bold green]")

                    elif len(matching_editions) == 1:
                        selected = matching_editions[0]
                        edition = str(selected.get("name", "")) if selected.get("has_attributes") else ""  # No special edition for single matches without attributes

                        logger.info(f"[bold green]Setting edition from duration match: {edition}[/bold green]")

                    else:
                        logger.debug(f"[yellow]No matching editions found within {leeway_seconds} seconds of media duration[/yellow]")

                except (ValueError, TypeError) as e:
                    logger.info(f"[yellow]Error parsing duration: {e}[/yellow]")

        elif meta.is_disc == "BDMV" and meta.discs:
            logger.debug("[cyan]Checking BDMV playlists for edition matches...[/cyan]")
            matched_editions: list[str] = []

            all_playlists: list[dict[str, Any]] = []
            discs = cast(list[dict[str, Any]], meta.discs)
            for disc in discs:
                if not meta.unattended or (meta.unattended and meta.unattended_confirm):
                    playlists = disc.get("playlists")
                    if isinstance(playlists, list):
                        all_playlists.extend(cast(list[dict[str, Any]], playlists))
                else:
                    valid_playlists = disc.get("all_valid_playlists")
                    if isinstance(valid_playlists, list):
                        all_playlists.extend(cast(list[dict[str, Any]], valid_playlists))
            logger.debug(f"[cyan]Found {len(all_playlists)} playlists to check against IMDb editions[/cyan]")

            leeway_seconds = 50
            matched_editions_with_attributes: list[str] = []
            matched_editions_without_attributes: list[str] = []

            for playlist in all_playlists:
                playlist_file = str(playlist.get("file") or "")
                playlist_edition = str(playlist.get("edition") or "")
                if playlist.get("duration"):
                    playlist_duration = float(playlist.get("duration") or 0)
                    formatted_duration = format_duration(playlist_duration)
                    logger.debug(f"[cyan]Checking playlist duration: {formatted_duration} seconds[/cyan]")

                    playlist_matching_editions: list[dict[str, Any]] = []

                    for edition_info in edition_details.values():
                        edition_seconds = float(edition_info.get("seconds", 0) or 0)
                        difference = abs(playlist_duration - edition_seconds)

                        if difference <= leeway_seconds:
                            # Store the complete edition info
                            attributes = edition_info.get("attributes")
                            attributes_list = attributes if isinstance(attributes, list) else []
                            if attributes_list:
                                edition_name = " ".join(smart_title(str(attr)) for attr in attributes_list)
                            else:
                                edition_name = f"{edition_info.get('minutes')} Minute Version (Theatrical)"

                            playlist_matching_editions.append(
                                {
                                    "name": edition_name,
                                    "display_name": str(edition_info.get("display_name", "")),
                                    "has_attributes": bool(edition_info.get("attributes") and len(edition_info["attributes"]) > 0),
                                    "minutes": edition_info.get("minutes"),
                                    "difference": difference,
                                }
                            )

                    # If multiple editions match this playlist, ask the user
                    if len(playlist_matching_editions) > 1:
                        if not meta.unattended or (meta.unattended and meta.unattended_confirm):
                            logger.info(
                                f"[yellow]Playlist edition [green]{playlist_edition} [yellow]using file [green]{playlist_file} [yellow]with duration [green]{formatted_duration} [yellow]matches multiple editions:[/yellow]"
                            )
                            for i, ed in enumerate(playlist_matching_editions):
                                logger.info(f"[yellow]{i + 1}. [green]{ed['name']} ({ed['display_name']}, diff: {ed['difference']:.2f} seconds)")

                            try:
                                choice = (
                                    await prompt_in_thread(
                                        cli_ui.ask_string,
                                        f"Select edition number (1-{len(playlist_matching_editions)}), press e to use playlist edition or press Enter to use the closest match:",
                                        default="",
                                    )
                                    or ""
                                )

                                playlist_selected: str | dict[str, Any]

                                if choice.strip() and choice.isdigit() and 1 <= int(choice) <= len(playlist_matching_editions):
                                    playlist_selected = playlist_matching_editions[int(choice) - 1]
                                elif choice.strip().lower() == "e":
                                    playlist_selected = playlist_edition
                                else:
                                    # Default to the closest match (smallest difference)
                                    playlist_selected = min(playlist_matching_editions, key=lambda x: x["difference"])
                                    logger.info(f"[yellow]Using closest match: {playlist_selected['name']}[/yellow]")

                                # Add the selected edition to our matches
                                if isinstance(playlist_selected, str):
                                    normalized_playlist = playlist_selected.strip().lower()
                                    if not normalized_playlist:
                                        # Empty playlist edition, fall back to closest match
                                        logger.info("[yellow]Empty playlist edition, using closest match.[/yellow]")
                                        playlist_selected = min(playlist_matching_editions, key=lambda x: x["difference"])
                                        if playlist_selected["has_attributes"]:
                                            if playlist_selected["name"] not in matched_editions_with_attributes:
                                                matched_editions_with_attributes.append(playlist_selected["name"])
                                                logger.info(f"[green]Added edition with attributes: {playlist_selected['name']}[/green]")
                                        else:
                                            matched_editions_without_attributes.append(str(playlist_selected["minutes"]))
                                            logger.info(f"[yellow]Added edition without attributes: {playlist_selected['name']}[/yellow]")
                                    elif normalized_playlist in ("theatrical", "theater", "theatre"):
                                        # Theatrical is a non-attribute edition; use closest match's minutes
                                        logger.info(f"[yellow]Playlist edition '{playlist_selected}' is theatrical, treating as non-attribute edition.[/yellow]")
                                        fallback = min(playlist_matching_editions, key=lambda x: x["difference"])
                                        matched_editions_without_attributes.append(str(fallback["minutes"]))
                                    else:
                                        # Genuine attribute edition from playlist
                                        if playlist_selected.strip() not in matched_editions_with_attributes:
                                            matched_editions_with_attributes.append(playlist_selected.strip())
                                            logger.info(f"[green]Using playlist edition: {playlist_selected}[/green]")
                                        else:
                                            logger.info(f"[yellow]Playlist edition '{playlist_selected}' already added, skipping duplicate.[/yellow]")
                                else:
                                    if playlist_selected["has_attributes"]:
                                        if playlist_selected["name"] not in matched_editions_with_attributes:
                                            matched_editions_with_attributes.append(playlist_selected["name"])
                                            logger.info(f"[green]Added edition with attributes: {playlist_selected['name']}[/green]")
                                    else:
                                        matched_editions_without_attributes.append(str(playlist_selected["minutes"]))
                                        logger.info(f"[yellow]Added edition without attributes: {playlist_selected['name']}[/yellow]")

                            except Exception as e:
                                logger.error(f"[red]Error processing selection: {e}. Using closest match.[/red]")
                                # Default to closest match
                                fallback_selected = min(playlist_matching_editions, key=lambda x: x["difference"])
                                if fallback_selected["has_attributes"]:
                                    matched_editions_with_attributes.append(fallback_selected["name"])
                                else:
                                    matched_editions_without_attributes.append(str(fallback_selected["minutes"]))
                        else:
                            logger.info(
                                f"[yellow]Playlist edition [green]{playlist_edition} [yellow]using file [green]{playlist_file} [yellow]with duration [green]{formatted_duration} [yellow]matches multiple editions, but unattended mode is enabled. Using closest match.[/yellow]"
                            )
                            unattended_selected = min(playlist_matching_editions, key=lambda x: x["difference"])
                            if unattended_selected["has_attributes"]:
                                matched_editions_with_attributes.append(unattended_selected["name"])
                            else:
                                matched_editions_without_attributes.append(str(unattended_selected["minutes"]))

                    # If just one edition matches, add it directly
                    elif len(playlist_matching_editions) == 1:
                        edition_info = playlist_matching_editions[0]
                        logger.debug(f"[green]Playlist {playlist_edition} matches edition: {edition_info['display_name']} {edition_info['name']}[/green]")

                        if edition_info["has_attributes"]:
                            if edition_info["name"] not in matched_editions_with_attributes:
                                matched_editions_with_attributes.append(edition_info["name"])
                                logger.debug(f"[green]Added edition with attributes: {edition_info['name']}[/green]")
                        else:
                            matched_editions_without_attributes.append(str(edition_info["minutes"]))
                            logger.debug(f"[yellow]Added edition without attributes: {edition_info['name']}[/yellow]")

                # Process the matched editions
                if matched_editions_with_attributes or matched_editions_without_attributes:
                    # Only use "Theatrical" if we have at least one edition with attributes
                    if matched_editions_with_attributes and matched_editions_without_attributes:
                        matched_editions = [*matched_editions_with_attributes, "Theatrical"]
                        logger.debug("[cyan]Adding 'Theatrical' label because we have both attribute and non-attribute editions[/cyan]")
                    elif matched_editions_with_attributes:
                        matched_editions = matched_editions_with_attributes
                        logger.debug("[cyan]Using only editions with attributes[/cyan]")
                    else:
                        logger.debug("[cyan]No useful editions found[/cyan]")

                    # Handle final edition formatting
                    if matched_editions:
                        # If multiple editions, prefix with count
                        if len(matched_editions) > 1:
                            unique_editions = list(set(matched_editions))  # Remove duplicates
                            if "Theatrical" in unique_editions:
                                unique_editions.remove("Theatrical")
                                unique_editions = ["Theatrical", *sorted(unique_editions)]
                            edition = f"{len(unique_editions)}in1 " + " / ".join(unique_editions) if len(unique_editions) > 1 else unique_editions[0]  # Just one unique edition
                        else:
                            edition = matched_editions[0]

                        logger.debug(f"[bold green]Setting edition from BDMV playlist matches: {edition}[/bold green]")

    if edition and (edition.lower() in ["cut", "approximate"] or len(edition) < 6):
        edition = ""
    if edition and "edition" in edition.lower():
        edition = re.sub(r"\bedition\b", "", edition, flags=re.IGNORECASE).strip()
    if edition and "extended" in edition.lower():
        edition = "Extended"

    if not edition:
        if video.lower().startswith("dc"):
            video = video.lower().replace("dc", "", 1)

        guess: Any = guessit_fn(video)

        tag_value: Any = guess.get("release_group", "NOGROUP")
        tag = " ".join(str(t) for t in tag_value) if isinstance(tag_value, list) else str(tag_value)
        repack = ""

        if bdinfo is not None:
            try:
                edition_value: Any = guessit_fn(bdinfo["label"]).get("edition", "")
            except Exception as e:
                logger.debug(f"BDInfo Edition Guess Error: {e}", extra={"markup": False})
                edition_value = ""
        else:
            try:
                edition_value = guess.get("edition", "")
            except Exception as e:
                logger.debug(f"Video Edition Guess Error: {e}", extra={"markup": False})
                edition_value = ""

        edition = " ".join(str(e) for e in cast(list[Any], edition_value)) if isinstance(edition_value, list) else str(edition_value or "")

        if len(filelist) == 1:
            video = Path(video).name

        video = video.upper().replace(".", " ").replace(tag.upper(), "").replace("-", " ")

        if "OPEN MATTE" in video.upper():
            edition = edition + " Open Matte"

    # Manual edition overrides everything
    if manual_edition:
        if isinstance(manual_edition, list):
            manual_edition = " ".join(e for e in manual_edition)
        edition = manual_edition

    edition = edition.replace(",", " ")

    # Handle repack info
    repack = ""
    release_text = f"{video} {edition}"
    if _has_release_token(release_text, "REPACK") or _has_release_token(release_text, "V2"):
        repack = "REPACK"
    if _has_release_token(release_text, "REPACK2") or _has_release_token(release_text, "V3"):
        repack = "REPACK2"
    if _has_release_token(release_text, "REPACK3") or _has_release_token(release_text, "V4"):
        repack = "REPACK3"
    if _has_release_token(release_text, "PROPER"):
        repack = "PROPER"
    if _has_release_token(release_text, "PROPER2"):
        repack = "PROPER2"
    if _has_release_token(release_text, "PROPER3"):
        repack = "PROPER3"
    if _has_release_token(release_text, "RERIP"):
        repack = "RERIP"

    # Only remove REPACK, RERIP, or PROPER from edition if not in manual edition
    if not manual_edition or (
        isinstance(manual_edition, str)
        and all(tag.lower() not in ["repack", "repack2", "repack3", "proper", "proper2", "proper3", "rerip"] for tag in manual_edition.strip().lower().split())
    ):
        edition = _strip_release_tokens(edition)

    if not meta.webdv:
        hybrid = False
        if "HYBRID" in video.upper() or "HYBRID" in edition.upper():
            hybrid = True
    else:
        hybrid = meta.webdv

    # Handle distributor info
    if edition:
        distributors = await get_distributor(edition)

        bad = ["internal", "limited", "retail", "version", "remastered"]

        if distributors and meta.is_disc:
            bad.append(distributors.lower())
            meta.distributor = distributors

        if any(term.lower() in edition.lower() for term in bad):
            edition = re.sub(r"\b(?:" + "|".join(bad) + r")\b", "", edition, flags=re.IGNORECASE).strip()
            # Clean up extra spaces
            while "  " in edition:
                edition = edition.replace("  ", " ")

        if edition != "":
            edition = edition.strip()
            logger.debug(f"Final Edition: {edition}")

    return edition, repack, hybrid


def format_duration(seconds: float) -> str:
    """Convert seconds to a human-readable HH:MM:SS format."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours}:{minutes:02d}:{secs:02d}"


def smart_title(s: str) -> str:
    """Custom title function that doesn't capitalize after apostrophes"""
    result = s.title()
    # Fix capitalization after apostrophes
    return re.sub(r"(\w)'(\w)", lambda m: f"{m.group(1)}'{m.group(2).lower()}", result)
