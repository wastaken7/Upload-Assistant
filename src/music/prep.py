"""Bridge the music domain into Upload Assistant's shared ``Meta`` object."""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any

import aiofiles
import mutagen

from cogs.redaction import PathAwareEncoder
from src.console import logger
from src.meta import Meta
from src.music.analyzer import MusicReleaseAnalyzer
from src.music.models import MetadataSource
from src.music.sources import DiscogsEnricher, MusicBrainzEnricher
from src.music.validation import MusicValidator


def _preferred_artwork(release: Any) -> Path | None:
    """Choose a likely front cover from sidecar artwork without touching it."""
    root = Path(release.root)
    candidates = [root / relative for relative in release.auxiliary.artwork]
    candidates = [candidate for candidate in candidates if candidate.is_file()]
    if not candidates:
        return None

    def sort_key(candidate: Path) -> tuple[int, str]:
        stem = candidate.stem.casefold()
        priority = 0 if re.search(r"(?:^|[ _.-])(cover|front|folder|album)(?:$|[ _.-])", stem) else 1
        return priority, str(candidate).casefold()

    return min(candidates, key=sort_key)


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
    configured = Path(str(meta.cover_path or ""))
    if configured.is_file():
        return str(configured)
    local_cover = _preferred_artwork(release)
    if local_cover:
        meta.cover_path = str(local_cover)
        return meta.cover_path

    output_dir = Path(meta.base_dir) / "tmp" / str(meta.uuid)
    output_dir.mkdir(parents=True, exist_ok=True)
    extracted = await asyncio.to_thread(_extract_embedded_artwork, [track.path for track in release.tracks], output_dir)
    if extracted:
        meta.cover_path = str(extracted)
        logger.info("[cyan]Music: extracted embedded front-cover artwork.[/cyan]")
        return meta.cover_path
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

    cover = str(meta.music_cover or "").strip()
    if cover.startswith(("http://", "https://")):
        meta.cover = cover
        set_user("cover_url", cover)
    elif cover:
        cover_path = Path(cover).expanduser()
        if cover_path.is_file():
            meta.cover_path = str(cover_path.resolve())
        else:
            logger.warning("[yellow]MUSIC: --music-cover is neither a public HTTP(S) URL nor an existing image file; ignoring it.[/yellow]")


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


async def gather_music_prep(meta: Meta, config: dict[str, Any]) -> None:
    """Analyze a local release and publish a JSON-safe music snapshot into meta."""
    analyzer = MusicReleaseAnalyzer()
    release = analyzer.analyze(str(meta.path or ""))
    _apply_music_cli_overrides(meta, release)
    default_config = config.get("DEFAULT", {}) if isinstance(config.get("DEFAULT", {}), dict) else {}
    discogs_release_id, discogs_master_id = _discogs_ids(meta, release)
    enrichment_enabled = meta.music_enrichment if meta.music_enrichment is not None else default_config.get("music_enrichment_enabled", False)
    if enrichment_enabled:
        await MusicBrainzEnricher().enrich(release)
    if discogs_release_id or discogs_master_id:
        await DiscogsEnricher(token=str(default_config.get("music_discogs_token", ""))).enrich(release, release_id=discogs_release_id, master_id=discogs_master_id)

    issues = MusicValidator().validate(release)
    release.warnings.extend(f"{issue.level}: {issue.message}" for issue in issues)
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
    await prepare_music_cover(meta, release)
    meta.name_notag = _music_name(release)
    meta.name = meta.name_notag
    meta.clean_name = meta.name_notag

    if not meta.edit and release.tracks:
        try:
            largest_track = max(release.tracks, key=lambda t: Path(t.path).stat().st_size if Path(t.path).is_file() else 0)
            from src.exportmi import export_info

            mi = await export_info(
                largest_track.path,
                meta.isdir,
                meta.uuid,
                meta.base_dir,
                is_dvd=False,
            )
            meta.mediainfo = mi
        except Exception as e:
            logger.error(f"[yellow]Warning: MediaInfo export failed for music: {e}[/yellow]")
            meta.mediainfo = {}

    path = Path(meta.base_dir) / "tmp" / str(meta.uuid) / "music_release.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    async with aiofiles.open(path, "w", encoding="utf-8") as file:
        await file.write(json.dumps(release.to_dict(), indent=2, cls=PathAwareEncoder))


def _music_name(release: Any) -> str:
    pieces = [str(release.get("artist", "")), "-", str(release.get("album", ""))]
    year = str(release.get("year", ""))
    if year:
        pieces.append(f"[{year}]")
    media, format_name = str(release.get("media", "")), str(release.get("format", ""))
    if media or format_name:
        pieces.append(f"[{media} {format_name}]".strip())
    return " ".join(part for part in pieces if part).replace("  ", " ").strip()
