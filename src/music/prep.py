"""Bridge the music domain into Upload Assistant's shared ``Meta`` object."""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any

import aiofiles
import cli_ui
import mutagen

from src.cogs.redaction import PathAwareEncoder
from src.console import logger
from src.meta import Meta
from src.music.analyzer import MusicReleaseAnalyzer
from src.music.models import MetadataSource, MusicRelease
from src.music.sources import DiscogsEnricher, MusicBrainzEnricher
from src.music.validation import MusicValidator
from src.temp_paths import artwork_dir, music_release_snapshot_path


def _image_suffix(data: bytes, mime: str = "") -> str:
    """Infer a safe suffix for extracted embedded artwork."""
    mime = mime.casefold()
    if "png" in mime or data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if "webp" in mime or (data[:4] == b"RIFF" and data[8:12] == b"WEBP"):
        return ".webp"
    return ".jpg"


def _extract_embedded_artwork(audio_paths: list[str], output_dir: Path) -> Path | None:
    """Extract the first front-cover image from FLAC, ID3 or MP4 tags."""
    for audio_path in audio_paths:
        try:
            audio = mutagen.File(audio_path)
        except mutagen.MutagenError, OSError:
            continue
        if audio is None:
            continue
        data: bytes | None = None
        mime = ""
        if getattr(audio, "pictures", None):
            pictures = list(audio.pictures)
            picture = next((item for item in pictures if getattr(item, "type", None) == 3), pictures[0])
            data, mime = bytes(picture.data), str(getattr(picture, "mime", ""))
        elif getattr(audio, "tags", None):
            apics = [value for key, value in audio.tags.items() if str(key).startswith("APIC")]
            if apics:
                picture = next((item for item in apics if getattr(item, "type", None) == 3), apics[0])
                data, mime = bytes(picture.data), str(getattr(picture, "mime", ""))
        if data is None:
            try:
                covr = audio["covr"]
            except KeyError, TypeError:
                covr = []
            if covr:
                data = bytes(covr[0])
        if data:
            destination = output_dir / f"MUSIC_COVER{_image_suffix(data, mime)}"
            destination.write_bytes(data)
            return destination
    return None


async def prepare_music_cover(meta: Meta, release: Any) -> str:
    """Resolve local or embedded artwork to a hostable temporary/local path.

    This phase never uploads an image and never alters source files.  Hosting is
    deliberately deferred until the user has confirmed the upload workflow.
    """
    configured = Path(str(meta.artwork_path or ""))
    if configured.is_file():
        return str(configured)
    output_dir = artwork_dir(meta.base_dir, str(meta.uuid))
    extracted = await asyncio.to_thread(_extract_embedded_artwork, [track.path for track in release.tracks], output_dir)
    if extracted:
        meta.artwork_path = str(extracted)
        return meta.artwork_path
    return ""


def _music_override_year(value: Any, name: str) -> str:
    """Return a safe four-digit CLI override year or ignore an invalid one."""
    # argparse/Meta use zero as the unset sentinel for optional year values.
    # It is not a user error and should not produce noise on every MUSIC run.
    if value in (None, "", 0, "0"):
        return ""
    try:
        year = int(value)
    except TypeError, ValueError:
        return ""
    if 1000 <= year <= 3000:
        return str(year)
    logger.warning(f"[yellow]MUSIC: ignoring invalid {name} override {value!r}; expected a four-digit year.[/yellow]")
    return ""


def _apply_music_cli_overrides(meta: Meta, release: Any) -> None:
    """Apply intentional CLI values after analysis and before enrichment.

    This keeps embedded tags authoritative by default while ensuring an
    explicit command-line correction wins over lower-confidence inference or
    a later optional MusicBrainz result.
    """

    def set_user(name: str, value: Any) -> None:
        release.set_field(name, value, MetadataSource.USER, 1.0, force=True)

    artist = str(meta.music_artist or "").strip()
    if artist:
        artists = [part.strip() for part in re.split(r"\s+&\s+", artist) if part.strip()]
        set_user("artist", artist)
        set_user("artists", artists or [artist])
    album = str(meta.music_album or "").strip()
    if album:
        set_user("album", album)

    original_year = _music_override_year(meta.manual_year, "--year")
    if original_year:
        set_user("year", original_year)
    release_year = _music_override_year(meta.music_release_year, "--music-release-year")
    if release_year:
        set_user("release_year", release_year)
    edition_year = _music_override_year(meta.music_edition_year, "--music-edition-year")
    if edition_year:
        set_user("edition_year", edition_year)

    media_map = {
        "cd": "CD",
        "web": "WEB",
        "vinyl": "Vinyl",
        "dvd": "DVD",
        "bd": "BD",
        "soundboard": "Soundboard",
        "sacd": "SACD",
        "dat": "DAT",
        "cassette": "Cassette",
    }
    media = media_map.get(str(meta.music_media or "").casefold())
    # Reuse the existing --source flag when it maps unambiguously to music.
    media = media or media_map.get(str(meta.manual_source or "").casefold())
    if media:
        set_user("media", media)

    release_type_map = {
        item.casefold(): item
        for item in (
            "Album",
            "Soundtrack",
            "EP",
            "Anthology",
            "Compilation",
            "Sampler",
            "Single",
            "Demo",
            "Live album",
            "Split",
            "Remix",
            "Bootleg",
            "Interview",
            "Mixtape",
            "DJ Mix",
            "Concert recording",
            "Unknown",
        )
    }
    release_type = release_type_map.get(str(meta.music_release_type or "").casefold())
    if release_type:
        set_user("release_type", release_type)

    label = str(meta.music_label or "").strip()
    if label:
        set_user("release_label", label)
    catalogue = str(meta.music_catalogue_number or "").strip()
    if catalogue:
        set_user("release_catalogue_number", catalogue)
    genres = [item.strip() for item in str(meta.music_genres or "").split(",") if item.strip()]
    if genres:
        set_user("genres", genres)

    edition = meta.manual_edition
    if isinstance(edition, list):
        edition = " ".join(str(item).strip() for item in edition if str(item).strip())
    if str(edition or "").strip():
        set_user("edition", str(edition).strip())


def _discogs_ids(meta: Meta, release: Any) -> tuple[str, str]:
    """Resolve explicit Discogs arguments without guessing a title search."""
    release_id = ""
    master_id = ""
    values = (
        (meta.music_discogs_release_id, "release", "--music-discogs-release-id"),
        (meta.music_discogs_master_id, "master", "--music-discogs-master-id"),
        (meta.music_discogs_id, "release", "--music-discogs-id"),
    )
    for value, default_kind, argument in values:
        if not str(value or "").strip():
            continue
        reference = DiscogsEnricher.parse_reference(value, default_kind)
        if not reference:
            logger.warning(f"[yellow]MUSIC: ignoring invalid {argument} value; use a positive Discogs ID, URL, release/ID or master/ID.[/yellow]")
            continue
        kind, identifier = reference
        if kind == "release" and not release_id:
            release_id = identifier
        elif kind == "master" and not master_id:
            master_id = identifier
    if release_id:
        release.external_ids["discogs_release"] = release_id
        release.set_field("discogs_release", release_id, MetadataSource.USER, 1.0, force=True)
    if master_id:
        release.external_ids["discogs_master"] = master_id
        release.set_field("discogs_master", master_id, MetadataSource.USER, 1.0, force=True)
    return release_id, master_id


async def _find_discogs_release(meta: Meta, release: Any, token: str) -> str:
    """Find an exact Discogs pressing, never silently resolving ambiguity."""
    matches = await DiscogsEnricher(token=token, base_dir=str(meta.base_dir or "")).find_exact_releases(str(release.get("artist", "")), str(release.get("album", "")))
    filtered_matches = DiscogsEnricher.filter_releases_by_media(matches, release.get("media", ""))
    if len(filtered_matches) != len(matches):
        logger.info(f"[cyan]MUSIC: filtered Discogs matches by {release.get('media')} media ({len(matches)} -> {len(filtered_matches)}).[/cyan]")
    matches = filtered_matches
    catalogue = release.get("directory_catalogue_number", "") or release.get("release_catalogue_number", release.get("catalogue_number", ""))
    catalogue_matches = DiscogsEnricher.filter_releases_by_catalogue(matches, catalogue)
    if len(catalogue_matches) != len(matches):
        logger.info(f"[cyan]MUSIC: filtered Discogs matches by catalogue number ({len(matches)} -> {len(catalogue_matches)}).[/cyan]")
    matches = catalogue_matches
    if len(matches) == 1:
        identifier = str(matches[0].get("id", ""))
        if identifier.isdigit():
            logger.info(f"[cyan]MUSIC: found one exact Discogs release match ({identifier}).[/cyan]")
            return identifier
    if not matches:
        logger.info("[yellow]MUSIC: no exact Discogs release match found.[/yellow]")
        return ""
    if meta.unattended:
        logger.info("[yellow]MUSIC: multiple exact Discogs release matches in unattended mode; skipping Discogs.[/yellow]")
        return ""
    logger.info("[bold yellow]Multiple exact Discogs releases found; select one or 0 to skip:[/bold yellow]")
    for index, candidate in enumerate(matches, 1):
        details = " / ".join(str(candidate.get(key, "")).strip() for key in ("year", "country", "catno") if str(candidate.get(key, "")).strip())
        logger.info(f"[cyan]{index}.[/cyan] {candidate.get('title', '')} {f'({details})' if details else ''} [dim]ID: {candidate.get('id', '')}[/dim]")
    while True:
        try:
            choice = (cli_ui.ask_string(f"Discogs release (1-{len(matches)}, 0 to skip): ") or "").strip()
        except EOFError, KeyboardInterrupt:
            logger.info("[yellow]MUSIC: Discogs selection cancelled; skipping Discogs.[/yellow]")
            return ""
        if choice in {"", "0"}:
            return ""
        if choice.isdigit() and 1 <= int(choice) <= len(matches):
            identifier = str(matches[int(choice) - 1].get("id", ""))
            if identifier.isdigit():
                return identifier
        logger.info("[red]Invalid Discogs selection. Enter a listed number or 0.[/red]")


async def gather_music_prep(meta: Meta, config: dict[str, Any]) -> None:
    """Analyze a local release and publish a JSON-safe music snapshot into meta."""
    analyzer = MusicReleaseAnalyzer()
    release = analyzer.analyze(str(meta.path or ""))
    _apply_music_cli_overrides(meta, release)
    default_config = config.get("DEFAULT", {}) if isinstance(config.get("DEFAULT", {}), dict) else {}
    enrichment_enabled = meta.music_enrichment if meta.music_enrichment is not None else default_config.get("music_enrichment_enabled", False)
    if enrichment_enabled:
        await MusicBrainzEnricher(base_dir=str(meta.base_dir or "")).enrich(release)
    issues = MusicValidator().validate(release)
    release.warnings.extend(f"{issue.level}: {issue.message}" for issue in issues)
    _sync_release_to_meta(meta, release)
    await prepare_music_cover(meta, release)

    if not meta.edit and release.tracks:
        try:
            largest_track = max(release.tracks, key=lambda t: Path(t.path).stat().st_size if Path(t.path).is_file() else 0)
            from src.exportmi import export_info

            meta.mediainfo = await export_info(
                largest_track.path,
                meta.isdir,
                meta.uuid,
                meta.base_dir,
                is_dvd=False,
            )
        except Exception as e:
            logger.error(f"[yellow]Warning: MediaInfo export failed for music: {e}[/yellow]")
            meta.mediainfo = {}
    await _write_music_release_snapshot(meta, release)


async def enrich_music_from_discogs(meta: Meta, config: dict[str, Any]) -> bool:
    """Resolve Discogs after any exact tracker torrent has enriched the release.

    The Orpheus torrent lookup runs immediately before this function and can
    contribute the pressing's catalogue number, label and Discogs master link.
    These make automatic Discogs selection substantially safer than a title
    search alone. Explicit command-line IDs remain the highest priority.
    """
    if meta.category != "MUSIC" or not meta.music_discogs_enabled or not isinstance(meta.music_release, dict):
        return False
    release = MusicRelease.from_dict(meta.music_release)
    settings = config.get("DEFAULT", {}) if isinstance(config.get("DEFAULT", {}), dict) else {}
    token = str(settings.get("music_discogs_token", ""))
    release_id, master_id = _discogs_ids(meta, release)
    existing_release = DiscogsEnricher.parse_reference(release.external_ids.get("discogs_release", ""), "release")
    existing_master = DiscogsEnricher.parse_reference(release.external_ids.get("discogs_master", ""), "master")
    if not release_id and existing_release and existing_release[0] == "release":
        release_id = existing_release[1]
    if not master_id and existing_master and existing_master[0] == "master":
        master_id = existing_master[1]
    if not release_id:
        release_id = await _find_discogs_release(meta, release, token)
    if not release_id and not master_id:
        return False
    await DiscogsEnricher(token=token, base_dir=str(meta.base_dir or "")).enrich(release, release_id=release_id, master_id=master_id)
    _sync_release_to_meta(meta, release)
    await _write_music_release_snapshot(meta, release)
    return True


def _sync_release_to_meta(meta: Meta, release: MusicRelease) -> None:
    """Publish the tracker-neutral release model to the shared metadata object."""
    meta.music_release = release.to_dict()
    meta.artist = str(release.get("artist", meta.artist))
    meta.title = str(release.get("album", meta.title))
    meta.year = int(release.get("year")) if str(release.get("year", "")).isdigit() else meta.year
    meta.format = str(release.get("format", meta.format))
    meta.source = str(release.get("media", meta.source or "")) or meta.source
    meta.scene = bool(release.get("scene", meta.scene))
    meta.genres = list(release.get("genres", meta.genres)) if isinstance(release.get("genres", meta.genres), list) else meta.genres
    meta.audio = f"{meta.format} / {release.get('disc_count', 1)} disc(s) / {release.get('track_count', 0)} track(s)"
    meta.filelist = [track.path for track in release.tracks]
    meta.name_notag = _music_name(release)
    meta.name = meta.name_notag
    meta.clean_name = meta.name_notag


async def _write_music_release_snapshot(meta: Meta, release: MusicRelease) -> None:
    """Persist the current release snapshot for review and later upload stages."""
    path = music_release_snapshot_path(meta.base_dir, str(meta.uuid))
    path.parent.mkdir(parents=True, exist_ok=True)
    async with aiofiles.open(path, "w", encoding="utf-8") as file:
        await file.write(json.dumps(release.to_dict(), indent=2, cls=PathAwareEncoder))


def _set_tracker_field(release: MusicRelease, name: str, value: Any, confidence: float) -> None:
    """Use tracker data only to fill gaps; local evidence and CLI input win."""
    existing = release.fields.get(name)
    protected = {MetadataSource.USER, MetadataSource.FILE_TAG, MetadataSource.AUXILIARY}
    effective_confidence = 0.0 if existing and existing.source in protected else confidence
    release.set_field(name, value, MetadataSource.TRACKER, effective_confidence)


def _orpheus_people(group: dict[str, Any], role: str) -> list[str]:
    music_info = group.get("musicInfo")
    if not isinstance(music_info, dict):
        return []
    people = music_info.get(role)
    if not isinstance(people, list):
        return []
    return list(dict.fromkeys(str(person.get("name", "")).strip() for person in people if isinstance(person, dict) and str(person.get("name", "")).strip()))


async def enrich_music_from_orpheus(meta: Meta, config: dict[str, Any]) -> bool:
    """Enrich an analyzed MUSIC release from an explicitly known Orpheus torrent.

    The ID is obtained from a matched client's torrent comment or ``--tracker-id``;
    this never searches Orpheus by name and never performs a state-changing call.
    """
    identifier = meta.get_tracker_id("ORPHEUS") or ""
    if meta.category != "MUSIC" or not identifier.isdigit() or not isinstance(meta.music_release, dict):
        return False

    from src.trackers.orpheus import Orpheus

    orpheus = Orpheus(config)
    result = await orpheus.get_torrent(identifier, meta)
    if not isinstance(result, dict):
        logger.info(f"[yellow]MUSIC: Orpheus metadata was unavailable for torrent {identifier}.[/yellow]")
        return False
    group, torrent = result.get("group"), result.get("torrent")
    if not isinstance(group, dict) or not isinstance(torrent, dict):
        return False

    release = MusicRelease.from_dict(meta.music_release)
    artists = _orpheus_people(group, "artists")
    composers = _orpheus_people(group, "composers")
    _set_tracker_field(release, "album", str(group.get("name", "")).strip(), 0.93)
    if artists:
        _set_tracker_field(release, "artists", artists, 0.93)
        _set_tracker_field(release, "artist", " & ".join(artists), 0.93)
    if composers:
        _set_tracker_field(release, "composers", composers, 0.9)
    _set_tracker_field(release, "year", str(group.get("year", "")).strip(), 0.84)
    _set_tracker_field(release, "release_type", str(group.get("releaseTypeName", "")).strip(), 0.88)
    _set_tracker_field(release, "genres", group.get("tags", []), 0.78)
    _set_tracker_field(release, "media", str(torrent.get("media", "")).strip(), 0.9)
    _set_tracker_field(release, "release_year", str(torrent.get("remasterYear", "")).strip(), 0.89)
    remaster_title = str(torrent.get("remasterTitle", "")).strip()
    if remaster_title:
        _set_tracker_field(release, "edition", remaster_title, 0.9)
        _set_tracker_field(release, "edition_year", str(torrent.get("remasterYear", "")).strip(), 0.89)
    _set_tracker_field(release, "release_label", str(torrent.get("remasterRecordLabel", "")).strip(), 0.91)
    _set_tracker_field(release, "release_catalogue_number", str(torrent.get("remasterCatalogueNumber", "")).strip(), 0.91)
    _set_tracker_field(release, "orpheus_encoding", str(torrent.get("encoding", "")).strip(), 0.9)

    release.external_ids.setdefault("orpheus_torrent", identifier)
    group_id = str(group.get("id", "")).strip()
    if group_id:
        release.external_ids.setdefault("orpheus_group", group_id)
        release.external_ids.setdefault("orpheus_url", f"{orpheus.base_url}/torrents.php?id={group_id}&torrentid={identifier}")
    wiki = str(group.get("wikiBBcode", ""))
    for key, pattern in (
        ("musicbrainz_release", r"musicbrainz\.org/release/([0-9a-f-]{36})"),
        ("discogs_release", r"discogs\.com/release/(\d+)"),
        ("discogs_master", r"discogs\.com/master/(\d+)"),
    ):
        match = re.search(pattern, wiki, flags=re.IGNORECASE)
        if match:
            release.external_ids.setdefault(key, match.group(1))

    if not meta.artwork_url and not meta.artwork_path:
        cover = str(group.get("wikiImage", "")).strip()
        if cover.startswith(("https://", "http://")):
            meta.artwork_url = cover
            _set_tracker_field(release, "cover_url", cover, 0.75)

    _sync_release_to_meta(meta, release)
    await _write_music_release_snapshot(meta, release)
    logger.info(f"[green]MUSIC: enriched metadata from Orpheus torrent {identifier}.[/green]")
    return True


def _music_name(release: Any) -> str:
    pieces = [str(release.get("artist", "")), "-", str(release.get("album", ""))]
    year = str(release.get("year", ""))
    if year:
        pieces.append(f"[{year}]")
    media, format_name = str(release.get("media", "")), str(release.get("format", ""))
    if media or format_name:
        pieces.append(f"[{media} {format_name}]".strip())
    return " ".join(part for part in pieces if part).replace("  ", " ").strip()
