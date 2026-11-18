"""Execution preview extraction from upload metadata."""

import os
import re
import urllib.parse
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, TypedDict, cast

from src.webui_events import ARTWORK_SUFFIXES
from web_ui import context as context_mod
from web_ui import session_state as session_state_mod
from web_ui.context import console
from web_ui.flask_compat import _is_obj_list, _is_obj_sequence, _is_str_mapping
from web_ui.request_utils import _json_load_dict
from web_ui.session_state import active_processes_lock


def _stringify_preview_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _stringify_optional_id(value: object) -> str:
    text = _stringify_preview_value(value)
    return "" if text in {"", "0"} else text


def _extract_preview_imdb_id(meta_data: Mapping[str, object]) -> str:
    """Format IMDb title IDs without losing zeros or truncating newer IDs."""
    for key in ("imdb_id", "imdb_tt", "imdb"):
        value = _stringify_optional_id(meta_data.get(key))
        match = re.fullmatch(r"(?:tt)?([0-9]+)", value, re.IGNORECASE)
        if match and match[1].strip("0"):
            return f"tt{match[1].zfill(7)}"
    return ""


def _string_list_preview_values(value: object) -> list[str]:
    results: list[str] = []
    if isinstance(value, str):
        cleaned = value.strip()
        if cleaned:
            results.append(cleaned)
        return results
    if _is_obj_sequence(value):
        for item in value:
            label = _stringify_preview_value(item.get("name")) if _is_str_mapping(item) else _stringify_preview_value(item)
            if label:
                results.append(label)
    return results


def _format_preview_size(value: object) -> str:
    """Return a compact binary size for a positive byte count."""
    if isinstance(value, bool) or not isinstance(value, (int, float, str, bytes, bytearray)):
        return ""
    try:
        size = int(value)
    except TypeError, ValueError:
        return ""
    if size <= 0:
        return ""
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    amount = float(size)
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            precision = 0 if unit == "B" else 1
            return f"{amount:.{precision}f} {unit}"
        amount /= 1024
    return ""


def _preview_mapping_values(value: object) -> str:
    if not _is_str_mapping(value):
        return ""
    return ", ".join(
        f"{_stringify_preview_value(key)}: {_stringify_preview_value(item)}" for key, item in value.items() if _stringify_preview_value(key) and _stringify_preview_value(item)
    )


def _preview_detail_item(key: str, label: str, value: object) -> PreviewDetailItem | None:
    if isinstance(value, Mapping):
        text = _preview_mapping_values(value)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        text = ", ".join(_string_list_preview_values(value))
    else:
        text = _stringify_preview_value(value)
    if not text:
        return None
    return {"key": key, "label": label, "value": text}


def _preview_detail_section(key: str, label: str, rows: Sequence[tuple[str, str, object]]) -> PreviewDetailSection | None:
    items = [item for item_key, item_label, value in rows if (item := _preview_detail_item(item_key, item_label, value))]
    if not items:
        return None
    return {"key": key, "label": label, "items": items}


def _extract_preview_detail_sections(meta_data: Mapping[str, object], music: Mapping[str, object]) -> list[PreviewDetailSection]:
    """Build ordered, display-safe detail groups for the execution preview."""
    category = _stringify_preview_value(meta_data.get("category")).upper()
    filelist = meta_data.get("filelist")
    file_count = len(filelist) if isinstance(filelist, Sequence) and not isinstance(filelist, (str, bytes, bytearray)) else 0
    video_codec = _stringify_preview_value(meta_data.get("video_codec")) or _stringify_preview_value(meta_data.get("video_encode"))

    sections: list[PreviewDetailSection] = []
    media_section = _preview_detail_section(
        "media",
        "Media",
        (
            ("type", "Type", meta_data.get("type")),
            ("source", "Source", meta_data.get("source")),
            ("resolution", "Resolution", meta_data.get("resolution")),
            ("container", "Container", meta_data.get("container")),
            ("video_codec", "Video", video_codec),
            ("audio", "Audio", meta_data.get("audio")),
            ("size", "Size", _format_preview_size(meta_data.get("source_size"))),
            ("files", "Files", file_count or ""),
        ),
    )
    if media_section:
        sections.append(media_section)

    if category == "MOVIE":
        category_section = _preview_detail_section(
            "movie",
            "Movie Details",
            (
                ("release_date", "Release Date", meta_data.get("release_date")),
                ("edition", "Edition", meta_data.get("edition")),
                ("directors", "Director", meta_data.get("directors")),
                ("studios", "Studio", meta_data.get("studios")),
                ("cast", "Cast", meta_data.get("cast")),
                ("original_language", "Original Language", meta_data.get("original_language")),
                ("country", "Country", meta_data.get("origin_country") or meta_data.get("origin_country_code")),
            ),
        )
    elif category == "TV":
        episode = _stringify_preview_value(meta_data.get("episode_title")) or _stringify_preview_value(meta_data.get("episode_name"))
        episode_code = "".join(
            value for value in (_stringify_preview_value(meta_data.get("season")), _stringify_preview_value(meta_data.get("episode"))) if value not in {"", "0"}
        )
        episode_display = " — ".join(value for value in (episode_code, episode) if value)
        tv_pack_raw = _stringify_preview_value(meta_data.get("tv_pack")).lower()
        package = "Season Pack" if tv_pack_raw not in ("", "0", "false", "none", "null") else "Single Episode"
        category_section = _preview_detail_section(
            "tv",
            "TV Details",
            (
                ("episode", "Episode", episode_display),
                ("package", "Package", package),
                ("season_name", "Season", meta_data.get("season_name") or meta_data.get("tvdb_season_name")),
                ("air_date", "Air Date", meta_data.get("episode_airdate")),
                ("service", "Service", meta_data.get("service_longname")),
                ("networks", "Network", meta_data.get("networks")),
            ),
        )
    elif category == "BOOK":
        series = _stringify_preview_value(meta_data.get("book_series"))
        series_index = _stringify_preview_value(meta_data.get("book_series_index"))
        series_display = f"{series} #{series_index}" if series and series_index else series
        bitrate = _stringify_preview_value(meta_data.get("audiobook_bitrate"))
        if bitrate.isdigit():
            bitrate = f"{bitrate} kbps"
        category_section = _preview_detail_section(
            "book",
            "Book Details",
            (
                ("author", "Author", meta_data.get("author") or meta_data.get("book_author")),
                ("narrator", "Narrator", meta_data.get("narrator")),
                ("translator", "Translator", meta_data.get("book_translator")),
                ("series", "Series", series_display),
                ("publisher", "Publisher", meta_data.get("publisher") or meta_data.get("book_publisher")),
                ("service", "Service", meta_data.get("service_longname") or meta_data.get("service")),
                ("language", "Language", meta_data.get("book_language")),
                ("isbn", "ISBN", meta_data.get("isbn") or meta_data.get("book_isbn")),
                ("asin", "ASIN", meta_data.get("asin") or meta_data.get("book_asin")),
                ("format", "Format", "Audiobook" if bool(meta_data.get("audiobook")) else "Book"),
                ("duration", "Duration", meta_data.get("audiobook_duration_formatted")),
                ("bitrate", "Bitrate", bitrate),
            ),
        )
    elif category == "MUSIC":

        def music_value(name: str, source_name: str = "") -> str:
            value = _stringify_preview_value(music.get(name))
            source = _stringify_preview_value(music.get(source_name)) if source_name else ""
            return f"{value} ({source})" if value and source else value

        track_count = _stringify_preview_value(music.get("track_count"))
        disc_count = _stringify_preview_value(music.get("disc_count"))
        tracks_discs = f"{track_count or '?'} / {disc_count or '1'}" if track_count or disc_count else ""
        release = " • ".join(
            value
            for value in (
                _stringify_preview_value(music.get("release_year")),
                _stringify_preview_value(music.get("retail_date")),
                _stringify_preview_value(music.get("release_label")),
                _stringify_preview_value(music.get("release_catalogue_number")),
            )
            if value
        )
        edition = " • ".join(value for value in (_stringify_preview_value(music.get("edition")), _stringify_preview_value(music.get("edition_year"))) if value)
        category_section = _preview_detail_section(
            "music",
            "Music Details",
            (
                ("artist", "Artist", music_value("artist", "artist_source")),
                ("album", "Album", music_value("album", "album_source")),
                ("original_year", "Original Year", music_value("original_year", "year_source")),
                ("release_type", "Release Type", music_value("release_type", "release_type_source")),
                ("media", "Media", music_value("media", "media_source")),
                ("technical", "Technical", music.get("technical")),
                ("tracks_discs", "Tracks / Discs", tracks_discs),
                ("release", "This Release", release),
                ("edition", "Edition", edition),
                ("auxiliary", "Auxiliary Files", music.get("auxiliary")),
                ("conflicts", "Metadata Conflicts", music.get("conflicts")),
            ),
        )
    elif category == "GAME":
        edition = " • ".join(
            value
            for value in (
                _stringify_preview_value(meta_data.get("game_release_edition")),
                _stringify_preview_value(meta_data.get("game_release_edition_year")),
            )
            if value
        )
        category_section = _preview_detail_section(
            "game",
            "Game Details",
            (
                ("platform", "Platform", meta_data.get("platform")),
                ("release_type", "Release Type", meta_data.get("game_subcategory") or meta_data.get("game_release_type")),
                ("version", "Version", meta_data.get("game_version")),
                ("edition", "Edition", edition),
                ("developer", "Developer", meta_data.get("developer")),
                ("publisher", "Publisher", meta_data.get("publisher")),
                ("region", "Region", meta_data.get("game_region")),
                ("system", "System", meta_data.get("game_system")),
                ("release_date", "Release Date", meta_data.get("igdb_first_release_date")),
                ("engines", "Engine", meta_data.get("game_engines")),
                ("modes", "Modes", meta_data.get("game_modes")),
                ("age_ratings", "Age Rating", meta_data.get("game_age_ratings")),
            ),
        )
    elif category == "XXX":
        category_section = _preview_detail_section(
            "xxx",
            "Release Details",
            (
                ("publisher", "Studio / Publisher", meta_data.get("publisher")),
                ("studios", "Studio", meta_data.get("studios")),
                ("release_date", "Release Date", meta_data.get("release_date")),
                ("performers", "Performers", meta_data.get("cast")),
            ),
        )
    else:
        category_section = None

    if category_section:
        sections.append(category_section)
    return sections


def _book_cover_from_meta(meta_data: Mapping[str, object], preview_session_id: str) -> str:
    covers_value = meta_data.get("covers")
    if _is_obj_sequence(covers_value):
        for item in covers_value:
            if not _is_str_mapping(item):
                continue
            for key in ("raw_url", "img_url", "web_url"):
                candidate = _stringify_preview_value(item.get(key))
                if candidate:
                    return candidate

    meta_uuid = _stringify_preview_value(meta_data.get("uuid"))
    if not meta_uuid:
        return ""

    tmp_dir = context_mod.STATE_DIR / "tmp" / meta_uuid / "artwork"
    for filename in ("POSTER.png", "poster.png", "POSTER.jpg", "poster.jpg", "POSTER.jpeg", "poster.jpeg", "cover.jpg", "cover.jpeg", "cover.png"):
        if (tmp_dir / filename).exists():
            return _execution_preview_cover_url(preview_session_id, meta_uuid)
    return ""


def _execution_preview_cover_url(preview_session_id: str, cache_key: str) -> str:
    """Return a per-item cover URL so the browser cannot reuse the prior cover."""
    version = urllib.parse.quote(str(cache_key), safe="")
    return f"/api/execution_preview_cover?session_id={urllib.parse.quote(preview_session_id, safe='')}&v={version}"


def _validated_item_cover(artwork_file: str, release_path: str) -> Path | None:
    """Accept a queue item's cover only as an image in temp storage or its release folder."""
    try:
        candidate = Path(artwork_file).resolve()
        if candidate.suffix.casefold() not in ARTWORK_SUFFIXES or not candidate.is_file():
            return None
        roots = [(context_mod.STATE_DIR / "tmp").resolve()]
        if release_path:
            release = Path(release_path).resolve()
            roots.append(release if release.is_dir() else release.parent)
    except OSError, ValueError:
        return None
    return candidate if any(candidate.is_relative_to(root) for root in roots) else None


def _resolve_gui_item_artwork(session_id: str, process_state: dict[str, object], event: dict[str, object]) -> dict[str, object]:
    """Swap a queue item's local cover path for an authenticated thumbnail URL.

    The path never reaches the browser or the session log; the server keeps
    it per item so the Results panel can still show it after the queue moves on.
    """
    if event.get("kind") != "item" or "artwork_file" not in event:
        return event
    event = dict(event)
    artwork_file = event.pop("artwork_file")
    index = event.get("index")
    if not isinstance(index, int) or isinstance(index, bool) or not isinstance(artwork_file, str):
        return event
    cover = _validated_item_cover(artwork_file, _stringify_preview_value(process_state.get("path")))
    if cover is None:
        return event
    try:
        version = cover.stat().st_mtime_ns
    except OSError:
        return event
    with active_processes_lock:
        covers = cast(dict[int, Path], process_state.setdefault("item_covers", {}))
        covers[index] = cover
    event["artwork"] = f"/api/execution_item_cover?session_id={urllib.parse.quote(session_id, safe='')}&item={index}&v={version}"
    return event


def _execution_preview_cover_cache_key(session_id: str, fallback: str) -> str:
    cover_file = _find_execution_preview_cover_file(session_id)
    if cover_file is None:
        return fallback
    try:
        return f"{fallback}:{cover_file.stat().st_mtime_ns}"
    except OSError:
        return fallback


def _music_cover_from_meta(meta_data: Mapping[str, object], preview_session_id: str) -> str:
    """Return a public cover URL or the authenticated local-preview endpoint."""
    for key in ("cover", "poster"):
        candidate = _stringify_preview_value(meta_data.get(key))
        if _is_http_url(candidate):
            return candidate
    if _find_execution_preview_cover_file(preview_session_id) is not None:
        cache_key = _stringify_preview_value(meta_data.get("uuid")) or _stringify_preview_value(meta_data.get("path"))
        return _execution_preview_cover_url(preview_session_id, cache_key)
    return ""


def _is_http_url(value: str) -> bool:
    return value.startswith(("http://", "https://"))


def _read_execution_preview_meta_file(meta_file: Path) -> Mapping[str, object] | None:
    try:
        return _json_load_dict(meta_file.read_text(encoding="utf-8"))
    except Exception:
        return None


_PREVIEW_META_RESOLVE_ATTEMPTS = 3


def _read_preview_meta_for_target(execution_path: str, known_uuid: str) -> tuple[Path | None, Mapping[str, object] | None, str]:
    """Read one target's metadata; return the file, its data and the UUID to cache."""
    base_tmp_dir = context_mod.STATE_DIR / "tmp"
    alias_meta_file = base_tmp_dir / Path(execution_path).name / "meta.json"
    alias_meta = _read_execution_preview_meta_file(alias_meta_file) if alias_meta_file.exists() else None
    meta_uuid = known_uuid
    if not meta_uuid and alias_meta is not None:
        meta_uuid = _stringify_preview_value(alias_meta.get("uuid"))

    if meta_uuid:
        canonical_meta_file = base_tmp_dir / meta_uuid / "meta.json"
        canonical_meta = _read_execution_preview_meta_file(canonical_meta_file) if canonical_meta_file.exists() else None
        if canonical_meta is not None and _preview_meta_matches_target(canonical_meta, execution_path):
            return canonical_meta_file, canonical_meta, meta_uuid

    if alias_meta is not None and _preview_meta_matches_target(alias_meta, execution_path):
        alias_uuid = _stringify_preview_value(alias_meta.get("uuid"))
        # An alias left by another release is not this target's metadata; wait
        # until the published UUID's own metadata is readable.
        if not known_uuid or alias_uuid == known_uuid:
            return alias_meta_file, alias_meta, alias_uuid

    return None, None, ""


def _preview_meta_matches_target(meta_data: Mapping[str, object], execution_path: str) -> bool:
    """Reject metadata another item with the same basename (so the same tmp dir) left behind."""
    meta_path = _stringify_preview_value(meta_data.get("path"))
    if not meta_path:
        return True
    try:
        return os.path.normcase(os.path.realpath(meta_path)) == os.path.normcase(os.path.realpath(execution_path))
    except OSError, ValueError:
        return False


def _resolve_execution_preview_meta(session_id: str) -> tuple[str, Path | None, Mapping[str, object] | None]:
    execution_path, meta_file, meta_data, _status = _resolve_execution_preview_target(session_id)
    return execution_path, meta_file, meta_data


def _resolve_execution_preview_target(
    session_id: str,
    *,
    with_status: bool = False,
) -> tuple[str, Path | None, Mapping[str, object] | None, dict[str, object]]:
    """Resolve metadata; with_status adds a prompt/progress snapshot taken when the target was validated."""
    for _attempt in range(_PREVIEW_META_RESOLVE_ATTEMPTS):
        # Snapshot the target, read its files without the lock, then cache the
        # UUID only if a queue advance has not moved the target meanwhile.
        with session_state_mod.active_processes_lock:
            process_info = session_state_mod.active_processes.get(session_id)
            if process_info is None:
                return "", None, None, {}
            execution_path = _stringify_preview_value(process_info.get("path"))
            known_uuid = _stringify_preview_value(process_info.get("meta_uuid"))
        if not execution_path:
            return "", None, None, {}

        meta_file, meta_data, uuid_to_cache = _read_preview_meta_for_target(execution_path, known_uuid)

        with session_state_mod.active_processes_lock:
            target_unchanged = (
                session_state_mod.active_processes.get(session_id) is process_info
                and _stringify_preview_value(process_info.get("path")) == execution_path
                and _stringify_preview_value(process_info.get("meta_uuid")) == known_uuid
            )
            if target_unchanged:
                if uuid_to_cache:
                    process_info["meta_uuid"] = uuid_to_cache
                status: dict[str, object] = {}
                if with_status:
                    raw_input_type = process_info.get("input_type")
                    status = {
                        "awaiting_input": bool(process_info.get("awaiting_input")),
                        "input_type": raw_input_type if isinstance(raw_input_type, str) else None,
                        "progress": session_state_mod._progress_items_locked(process_info),
                    }
                return execution_path, meta_file, meta_data, status
    # The target kept moving; report nothing rather than a previous item's path.
    return "", None, None, {}


def _append_metadata_source(
    sources: list[MetadataSource],
    seen_keys: set[str],
    key: str,
    label: str,
    value: str,
    url: str = "",
) -> None:
    normalized_value = value.strip()
    if not normalized_value:
        return
    dedupe_key = f"{key}:{normalized_value.lower()}"
    if dedupe_key in seen_keys:
        return
    seen_keys.add(dedupe_key)
    source: MetadataSource = {
        "key": key,
        "label": label,
        "value": normalized_value,
    }
    if url:
        source["url"] = url
    sources.append(source)


def _extract_metadata_sources(meta_data: Mapping[str, object]) -> list[MetadataSource]:
    from urllib.parse import quote

    category = _stringify_preview_value(meta_data.get("category")).upper()
    tmdb_value = _stringify_optional_id(meta_data.get("tmdb_id")) or _stringify_optional_id(meta_data.get("tmdb"))
    imdb_value = _extract_preview_imdb_id(meta_data)
    tvdb_value = _stringify_optional_id(meta_data.get("tvdb_id")) or _stringify_optional_id(meta_data.get("tvdb"))
    tvmaze_value = _stringify_optional_id(meta_data.get("tvmaze_id")) or _stringify_optional_id(meta_data.get("tvmaze"))
    mal_value = _stringify_optional_id(meta_data.get("mal_id")) or _stringify_optional_id(meta_data.get("mal"))
    douban_value = _stringify_optional_id(meta_data.get("douban_id"))
    igdb_value = _stringify_optional_id(meta_data.get("igdb_id"))
    igdb_url = _stringify_preview_value(meta_data.get("igdb_url"))
    steam_url = _stringify_preview_value(meta_data.get("steam_url"))
    openlibrary_value = (
        _stringify_preview_value(meta_data.get("openlibrary"))
        or _stringify_preview_value(meta_data.get("openlibrary_id"))
        or _stringify_preview_value(meta_data.get("openlibrary_book_id"))
    )
    isbn_value = _stringify_preview_value(meta_data.get("isbn"))
    asin_value = _stringify_preview_value(meta_data.get("asin")) or _stringify_preview_value(meta_data.get("book_asin"))
    audible_url = _stringify_preview_value(meta_data.get("audible_url"))

    sources: list[MetadataSource] = []
    seen_keys: set[str] = set()

    if category in {"MOVIE", "TV"} and tmdb_value:
        tmdb_kind = "tv" if category == "TV" else "movie"
        _append_metadata_source(
            sources,
            seen_keys,
            "tmdb",
            "TMDb",
            tmdb_value,
            f"https://www.themoviedb.org/{tmdb_kind}/{quote(tmdb_value)}",
        )

    if category in {"MOVIE", "TV"} and imdb_value:
        _append_metadata_source(
            sources,
            seen_keys,
            "imdb",
            "IMDb",
            imdb_value,
            f"https://www.imdb.com/title/{quote(imdb_value)}/",
        )

    if category == "TV" and tvdb_value:
        _append_metadata_source(
            sources,
            seen_keys,
            "tvdb",
            "TVDb",
            tvdb_value,
            f"https://thetvdb.com/dereferrer/series/{quote(tvdb_value)}",
        )

    if category == "TV" and tvmaze_value:
        _append_metadata_source(
            sources,
            seen_keys,
            "tvmaze",
            "TVMaze",
            tvmaze_value,
            f"https://www.tvmaze.com/shows/{quote(tvmaze_value)}",
        )

    if category in {"TV", "BOOK"} and mal_value:
        mal_kind = "manga" if category == "BOOK" else "anime"
        _append_metadata_source(
            sources,
            seen_keys,
            "mal",
            "MyAnimeList",
            mal_value,
            f"https://myanimelist.net/{mal_kind}/{quote(mal_value)}",
        )

    if category in {"MOVIE", "TV"} and douban_value:
        _append_metadata_source(
            sources,
            seen_keys,
            "douban",
            "Douban",
            douban_value,
            f"https://movie.douban.com/subject/{quote(douban_value)}/",
        )

    if category == "GAME" and igdb_value:
        _append_metadata_source(
            sources,
            seen_keys,
            "igdb",
            "IGDB",
            igdb_value,
            igdb_url if _is_http_url(igdb_url) else f"https://www.igdb.com/search?type=1&q={quote(igdb_value)}",
        )

    if category == "XXX":
        source_url = _stringify_preview_value(meta_data.get("xxx_source_url"))
        for key, label in (("tpdb", "ThePornDB"), ("blvckout", "BLVCKOUT")):
            value = _stringify_preview_value(meta_data.get(f"{key}_id"))
            if value:
                _append_metadata_source(sources, seen_keys, key, label, value, source_url if _is_http_url(source_url) else "")

    if category == "GAME" and steam_url:
        steam_value = steam_url.rstrip("/").split("/")[-1] or steam_url
        _append_metadata_source(sources, seen_keys, "steam", "Steam", steam_value, steam_url)

    if openlibrary_value:
        if openlibrary_value.startswith("OL"):
            if "W" in openlibrary_value:
                openlibrary_url = f"https://openlibrary.org/works/{quote(openlibrary_value)}"
            elif "M" in openlibrary_value:
                openlibrary_url = f"https://openlibrary.org/books/{quote(openlibrary_value)}"
            else:
                openlibrary_url = f"https://openlibrary.org/search?q={quote(openlibrary_value)}"
        else:
            openlibrary_url = f"https://openlibrary.org/search?q={quote(openlibrary_value)}"
        _append_metadata_source(
            sources,
            seen_keys,
            "openlibrary",
            "Open Library",
            openlibrary_value,
            openlibrary_url,
        )

    if category == "BOOK" and isbn_value:
        _append_metadata_source(
            sources,
            seen_keys,
            "google_books",
            "Google Books",
            isbn_value,
        )

    if category == "BOOK" and asin_value:
        _append_metadata_source(
            sources,
            seen_keys,
            "audible",
            "Audible",
            asin_value,
            audible_url if _is_http_url(audible_url) else "",
        )

    if category == "MUSIC":
        from src.music.sources import DiscogsEnricher

        music_release = meta_data.get("music_release")
        fields: object = music_release.get("fields") if _is_str_mapping(music_release) else None
        external_ids: object = music_release.get("external_ids") if _is_str_mapping(music_release) else None
        musicbrainz_release = ""
        if _is_str_mapping(fields):
            musicbrainz_entry: object = fields.get("musicbrainz_release")
            if _is_str_mapping(musicbrainz_entry):
                musicbrainz_release = _stringify_preview_value(musicbrainz_entry.get("value"))
        if not musicbrainz_release and _is_str_mapping(external_ids):
            musicbrainz_release = _stringify_preview_value(external_ids.get("musicbrainz_release"))
        if musicbrainz_release:
            _append_metadata_source(
                sources,
                seen_keys,
                "musicbrainz",
                "MusicBrainz",
                musicbrainz_release,
                f"https://musicbrainz.org/release/{quote(musicbrainz_release)}",
            )

        if _is_str_mapping(external_ids):
            discogs_references: tuple[tuple[str, object], ...] = (
                ("release", external_ids.get("discogs_release")),
                ("master", external_ids.get("discogs_master")),
            )
            for reference_kind, reference_value in discogs_references:
                parsed_reference = DiscogsEnricher.parse_reference(_stringify_preview_value(reference_value), reference_kind)
                if parsed_reference:
                    parsed_kind, discogs_id = parsed_reference
                    _append_metadata_source(
                        sources,
                        seen_keys,
                        f"discogs_{parsed_kind}",
                        f"Discogs {parsed_kind.title()}",
                        discogs_id,
                        f"https://www.discogs.com/{parsed_kind}/{quote(discogs_id)}",
                    )

    return sources


def _music_preview_from_meta(meta_data: Mapping[str, object]) -> dict[str, object]:
    """Extract display-safe MUSIC data from the normalized release snapshot."""
    release = meta_data.get("music_release")
    if not _is_str_mapping(release):
        return {}
    raw_fields = release.get("fields")
    fields: Mapping[str, object] = raw_fields if _is_str_mapping(raw_fields) else {}
    raw_tracks = release.get("tracks")
    tracks: Sequence[object] = raw_tracks if _is_obj_sequence(raw_tracks) else []
    raw_auxiliary = release.get("auxiliary")
    auxiliary: Mapping[str, object] = raw_auxiliary if _is_str_mapping(raw_auxiliary) else {}
    raw_warnings = release.get("warnings")
    warnings: Sequence[object] = raw_warnings if _is_obj_sequence(raw_warnings) else []
    raw_conflicts = release.get("conflicts")
    conflicts: Mapping[str, object] = raw_conflicts if _is_str_mapping(raw_conflicts) else {}

    def field_value(name: str, fallback: object = "") -> object:
        entry = fields.get(name)
        if _is_str_mapping(entry) and entry.get("value") not in (None, "", [], {}):
            return entry["value"]
        return fallback

    def source(name: str) -> str:
        entry = fields.get(name)
        raw = _stringify_preview_value(entry.get("source")) if _is_str_mapping(entry) else ""
        return {
            "file_tag": "File tags",
            "auxiliary": "Auxiliary files",
            "directory": "Folder name",
            "external": "External metadata",
            "user": "User input",
            "tracker": "Tracker",
            "inferred": "Inferred",
        }.get(raw, "")

    def text(name: str, fallback: object = "") -> str:
        value = field_value(name, fallback)
        if _is_obj_sequence(value):
            return " & ".join(_stringify_preview_value(item) for item in value if _stringify_preview_value(item))
        return _stringify_preview_value(value)

    def _as_int(value: object) -> int:
        if isinstance(value, (int, float, str, bytes, bytearray)):
            return int(value)
        return int(str(value))

    def technical_values(key: str, formatter: Callable[[object], str]) -> str:
        values = {track.get(key) for track in tracks if _is_str_mapping(track) and track.get(key) not in (None, "")}
        if not values:
            return ""
        try:
            ordered: list[object] = sorted(cast(Iterable[Any], values))
        except TypeError:
            ordered = sorted(values, key=str)
        rendered = [formatter(value) for value in ordered]
        return ", ".join(rendered) if len(rendered) <= 2 else f"{len(rendered)} variants"

    formats = technical_values("format", _stringify_preview_value)
    codecs = technical_values("codec", _stringify_preview_value)
    if formats.casefold() == codecs.casefold():
        codecs = ""
    bit_depth = technical_values("bit_depth", lambda value: f"{value}-bit")
    sample_rate = technical_values("sample_rate", lambda value: f"{_as_int(value) / 1000:g} kHz")
    channels = technical_values(
        "channels",
        lambda value: {1: "Mono", 2: "Stereo"}.get(_as_int(value), f"{value} channels"),
    )
    bitrate = technical_values("bitrate", lambda value: f"{round(_as_int(value) / 1000)} kbps")
    technical = " / ".join(item for item in (formats or text("format", meta_data.get("format")), codecs, bit_depth, sample_rate, channels, bitrate) if item)

    sidecars: list[str] = []
    for label, key in (("log", "logs"), ("cue", "cues"), ("NFO", "nfos"), ("playlist", "playlists"), ("SFV", "sfvs"), ("artwork", "artwork"), ("scan", "scans")):
        items = auxiliary.get(key, [])
        count = len(items) if _is_obj_sequence(items) else 0
        if count:
            sidecars.append(f"{count} {label}{'' if count == 1 else 's'}")

    genres_value = field_value("genres", [])
    genres = _string_list_preview_values(genres_value)
    artist = text("artists", field_value("artist", meta_data.get("artist", "")))
    return {
        "artist": artist,
        "artist_source": source("artists") or source("artist"),
        "album": text("album", meta_data.get("title", "")),
        "album_source": source("album"),
        "original_year": text("year", meta_data.get("year", "")),
        "year_source": source("year"),
        "release_type": text("release_type"),
        "release_type_source": source("release_type"),
        "media": text("media", meta_data.get("source", "")),
        "media_source": source("media"),
        "technical": technical,
        "track_count": text("track_count", len(tracks)),
        "disc_count": text("disc_count", 1),
        "release_year": text("release_year"),
        "retail_date": text("retail_date"),
        "release_label": text("release_label"),
        "release_catalogue_number": text("release_catalogue_number"),
        "edition": text("edition"),
        "edition_year": text("edition_year"),
        "genres": genres,
        "auxiliary": sidecars,
        "warnings": [_stringify_preview_value(item) for item in warnings[:5] if _stringify_preview_value(item)],
        "conflicts": [str(name).replace("_", " ") for name in sorted(conflicts)[:5]],
    }


def _preview_media_track_value(track: Mapping[str, object], *keys: str) -> str:
    """Return the first useful MediaInfo value across common key variants."""
    for key in keys:
        value = track.get(key)
        # Missing MediaInfo fields may be saved as empty dictionaries.
        text = _stringify_preview_value(value) if isinstance(value, (str, int, float)) else ""
        if text:
            return text

    folded = {str(key).casefold(): value for key, value in track.items()}
    for key in keys:
        value = folded.get(key.casefold())
        text = _stringify_preview_value(value) if isinstance(value, (str, int, float)) else ""
        if text:
            return text

    return ""


def _preview_track_flag(track: Mapping[str, object], *keys: str) -> bool:
    value = _preview_media_track_value(track, *keys).strip().casefold()
    return value in {"yes", "true", "1", "y"}


def _extract_preview_media_tracks(
    meta_data: Mapping[str, object],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Extract display-safe audio and subtitle tracks from saved MediaInfo data."""
    mediainfo = meta_data.get("mediainfo")
    raw_tracks: list[Mapping[str, object]] = []

    if _is_str_mapping(mediainfo):
        media = mediainfo.get("media")
        if _is_str_mapping(media):
            tracks = media.get("track")
            if _is_obj_sequence(tracks):
                raw_tracks.extend(track for track in tracks if _is_str_mapping(track))

        if not raw_tracks:
            for key in ("tracks", "track"):
                tracks = mediainfo.get(key)
                if _is_obj_sequence(tracks):
                    raw_tracks.extend(track for track in tracks if _is_str_mapping(track))
                    if raw_tracks:
                        break
    elif _is_obj_sequence(mediainfo):
        raw_tracks.extend(track for track in mediainfo if _is_str_mapping(track))

    audio_tracks: list[dict[str, object]] = []
    subtitle_tracks: list[dict[str, object]] = []

    for track in raw_tracks:
        track_type = _preview_media_track_value(
            track,
            "@type",
            "track_type",
            "TrackType",
            "type",
        ).casefold()

        if track_type == "audio":
            target = audio_tracks
        elif track_type in {"text", "subtitle", "subtitles"}:
            target = subtitle_tracks
        else:
            continue

        title = _preview_media_track_value(track, "Title", "title", "TrackTitle")
        language = _preview_media_track_value(
            track,
            "Language_String",
            "Language",
            "language",
            "Language_String1",
        )
        format_name = _preview_media_track_value(
            track,
            "Format_Commercial_IfAny",
            "Format",
            "format",
            "CodecID",
            "codec_id",
            "codec",
        )
        channels = _preview_media_track_value(
            track,
            "ChannelLayout",
            "ChannelLayout_Original",
            "Channels",
            "channels",
            "Channel(s)",
        )
        bitrate = _preview_media_track_value(
            track,
            "BitRate_String",
            "BitRate",
            "bitrate",
            "bit_rate",
        )
        if bitrate.isdigit():
            bitrate = f"{round(int(bitrate) / 1000)} kbps"

        service_kind = _preview_media_track_value(track, "ServiceKind", "service_kind")
        hearing_impaired = _preview_track_flag(track, "HearingImpaired", "hearing_impaired")
        commentary = "commentary" in title.casefold() or "commentary" in service_kind.casefold()

        target.append(
            {
                "index": len(target) + 1,
                "language": language,
                "language_code": _preview_media_track_value(track, "Language", "language"),
                "title": title,
                "format": format_name,
                "channels": channels,
                "bitrate": bitrate,
                "default": _preview_track_flag(track, "Default", "default"),
                "forced": _preview_track_flag(track, "Forced", "forced"),
                "hearing_impaired": hearing_impaired,
                "commentary": commentary,
            }
        )

    return audio_tracks, subtitle_tracks


def _extract_execution_preview(meta_data: Mapping[str, object], fallback_path: str, preview_session_id: str = "") -> ExecutionPreview:
    title = _stringify_preview_value(meta_data.get("title")) or _stringify_preview_value(meta_data.get("name"))
    original_title = _stringify_preview_value(meta_data.get("original_title"))
    category = _stringify_preview_value(meta_data.get("category")).upper()
    # ``artwork_url`` and ``tmdb_poster_path`` are the current metadata
    # contract for MOVIE/TV.  Keep the older fields as fallbacks so previews
    # remain available for already-created temp metadata.
    poster_url = _stringify_preview_value(meta_data.get("artwork_url")) or _stringify_preview_value(meta_data.get("poster"))
    if not poster_url and preview_session_id and _find_execution_preview_cover_file(preview_session_id) is not None:
        cache_key = _execution_preview_cover_cache_key(
            preview_session_id,
            _stringify_preview_value(meta_data.get("uuid")) or fallback_path,
        )
        poster_url = _execution_preview_cover_url(preview_session_id, cache_key)
    if category == "MUSIC":
        poster_url = _music_cover_from_meta(meta_data, _stringify_preview_value(meta_data.get("webui_session_id")))
    tmdb_poster = _stringify_preview_value(meta_data.get("tmdb_poster_path")) or _stringify_preview_value(meta_data.get("tmdb_poster"))
    if not poster_url and tmdb_poster:
        poster_url = tmdb_poster if tmdb_poster.startswith("http") else f"https://image.tmdb.org/t/p/w500{tmdb_poster}"
    music = _music_preview_from_meta(meta_data)
    detail_sections = _extract_preview_detail_sections(meta_data, music)
    genres = _string_list_preview_values(meta_data.get("genres")) or _string_list_preview_values(music.get("genres"))
    networks = _string_list_preview_values(meta_data.get("networks"))
    audiobook_bitrate = _stringify_preview_value(meta_data.get("audiobook_bitrate"))
    if audiobook_bitrate.isdigit():
        audiobook_bitrate = f"{audiobook_bitrate} kbps"
    tv_pack_raw = _stringify_preview_value(meta_data.get("tv_pack")).lower()
    audio_tracks, subtitle_tracks = _extract_preview_media_tracks(meta_data)

    return {
        "media_id": _stringify_preview_value(meta_data.get("uuid")) or fallback_path,
        "path": _stringify_preview_value(meta_data.get("path")) or fallback_path,
        "filename": Path(fallback_path).name,
        "title": title or _stringify_preview_value(music.get("album")),
        "original_title": original_title,
        "year": _stringify_preview_value(meta_data.get("year")),
        "category": _stringify_preview_value(meta_data.get("category")),
        "media_type": _stringify_preview_value(meta_data.get("type")),
        "source": _stringify_preview_value(meta_data.get("source")),
        "resolution": _stringify_preview_value(meta_data.get("resolution")),
        "tmdb": _stringify_optional_id(meta_data.get("tmdb_id")) or _stringify_optional_id(meta_data.get("tmdb")),
        "imdb": _extract_preview_imdb_id(meta_data),
        "metadata_sources": _extract_metadata_sources(meta_data),
        "poster_url": poster_url,
        "backdrop_url": _stringify_preview_value(meta_data.get("backdrop")),
        "overview": _stringify_preview_value(meta_data.get("overview")),
        "genres": genres,
        "name": _stringify_preview_value(meta_data.get("name")),
        "status": "ready",
        "audio": _stringify_preview_value(meta_data.get("audio")),
        "audio_tracks": audio_tracks,
        "subtitle_tracks": subtitle_tracks,
        "service": _stringify_preview_value(meta_data.get("service_longname") or meta_data.get("service")),
        "networks": networks,
        "season": _stringify_preview_value(meta_data.get("season")),
        "episode": _stringify_preview_value(meta_data.get("episode")),
        "episode_title": _stringify_preview_value(meta_data.get("episode_title")),
        "episode_name": _stringify_preview_value(meta_data.get("episode_name")),
        "episode_overview": _stringify_preview_value(meta_data.get("episode_overview")),
        "tv_pack": tv_pack_raw not in ("", "0", "false", "none", "null"),
        "author": _stringify_preview_value(meta_data.get("author")),
        "narrator": _stringify_preview_value(meta_data.get("narrator")),
        "publisher": _stringify_preview_value(meta_data.get("publisher")),
        "book_language": _stringify_preview_value(meta_data.get("book_language")),
        "audiobook": bool(meta_data.get("audiobook")),
        "audiobook_duration": _stringify_preview_value(meta_data.get("audiobook_duration_formatted")),
        "audiobook_bitrate": audiobook_bitrate,
        "book_series": _stringify_preview_value(meta_data.get("book_series")),
        "book_series_index": _stringify_preview_value(meta_data.get("book_series_index")),
        "platform": _stringify_preview_value(meta_data.get("platform")),
        "game_version": _stringify_preview_value(meta_data.get("game_version")),
        "game_subcategory": _stringify_preview_value(meta_data.get("game_subcategory")),
        "game_region": _stringify_preview_value(meta_data.get("game_region")),
        "game_system": _stringify_preview_value(meta_data.get("game_system")),
        "developer": _stringify_preview_value(meta_data.get("developer")),
        "music": music,
        "detail_sections": detail_sections,
        "awaiting_input": False,
        "input_type": None,
    }


def _find_execution_preview(session_id: str) -> ExecutionPreview | None:
    # Prompt and progress come from the snapshot taken with the metadata's target.
    execution_path, resolved_meta_file, resolved_meta, status = _resolve_execution_preview_target(session_id, with_status=True)
    if not execution_path:
        return None

    execution_name = Path(execution_path).name
    awaiting_input = bool(status.get("awaiting_input"))
    raw_input_type = status.get("input_type")
    input_type = raw_input_type if isinstance(raw_input_type, str) else None
    progress = cast(list[dict[str, object]], status.get("progress") or [])
    if resolved_meta_file is not None and resolved_meta is not None:
        try:
            meta_data: Mapping[str, object] = resolved_meta
            if _stringify_preview_value(meta_data.get("category")) == "BOOK":
                current_poster = _stringify_preview_value(meta_data.get("poster"))
                if not _is_http_url(current_poster):
                    try:
                        enriched_meta = dict(meta_data)
                        enriched_meta["poster"] = _book_cover_from_meta(meta_data, session_id)
                        meta_data = enriched_meta
                    except Exception as err:
                        console.print(f"Execution preview cover enrichment failed for session {session_id}: {err}", markup=False)
            if _stringify_preview_value(meta_data.get("category")).upper() == "MUSIC":
                meta_data = {**meta_data, "webui_session_id": session_id}
            preview = _extract_execution_preview(meta_data, execution_path, session_id)
            preview["awaiting_input"] = awaiting_input
            preview["input_type"] = input_type
            preview["progress"] = progress
            return preview
        except Exception:  # noqa: S110
            pass

    empty_music: dict[str, object] = {}
    return {
        "path": execution_path,
        "filename": execution_name,
        "title": "",
        "original_title": "",
        "year": "",
        "category": "",
        "media_type": "",
        "source": "",
        "resolution": "",
        "tmdb": "",
        "imdb": "",
        "metadata_sources": [],
        "poster_url": "",
        "backdrop_url": "",
        "overview": "",
        "genres": [],
        "name": "",
        "status": "waiting",
        "audio": "",
        "audio_tracks": [],
        "subtitle_tracks": [],
        "service": "",
        "networks": [],
        "season": "",
        "episode": "",
        "episode_title": "",
        "episode_name": "",
        "episode_overview": "",
        "tv_pack": False,
        "author": "",
        "narrator": "",
        "publisher": "",
        "book_language": "",
        "audiobook": False,
        "audiobook_duration": "",
        "audiobook_bitrate": "",
        "book_series": "",
        "book_series_index": "",
        "platform": "",
        "game_version": "",
        "game_subcategory": "",
        "game_region": "",
        "game_system": "",
        "developer": "",
        "music": empty_music,
        "detail_sections": [],
        "awaiting_input": awaiting_input,
        "input_type": input_type,
        "progress": progress,
    }


def _find_execution_preview_cover_file(session_id: str) -> Path | None:
    execution_path, _resolved_meta_file, resolved_meta = _resolve_execution_preview_meta(session_id)
    if not execution_path:
        return None

    meta_uuid = _stringify_preview_value(resolved_meta.get("uuid")) if resolved_meta is not None else ""
    candidate_dirs: list[Path] = []
    if meta_uuid:
        release_tmp = context_mod.STATE_DIR / "tmp" / meta_uuid
        candidate_dirs.append(release_tmp / "artwork")
    release_tmp = context_mod.STATE_DIR / "tmp" / Path(execution_path).name
    candidate_dirs.append(release_tmp / "artwork")

    # A music sidecar cover may stay beside the release, while embedded art is
    # extracted into tmp/MUSIC_COVER.*.  Never serve an arbitrary configured
    # path: accept it only when it is inside this release's selected root.
    if isinstance(resolved_meta, Mapping):
        cover_path = _stringify_preview_value(resolved_meta.get("cover_path"))
        if cover_path:
            try:
                candidate = Path(cover_path).resolve()
                release_path = Path(execution_path).resolve()
                release_root = release_path if release_path.is_dir() else release_path.parent
                candidate.relative_to(release_root)
                if candidate.is_file() and candidate.suffix.casefold() in {".jpg", ".jpeg", ".png", ".webp"}:
                    return candidate
            except OSError, ValueError:
                pass

    seen: set[str] = set()
    for tmp_dir in candidate_dirs:
        tmp_dir_key = str(tmp_dir)
        if tmp_dir_key in seen or not tmp_dir.exists():
            continue
        seen.add(tmp_dir_key)
        for filename in (
            "MUSIC_COVER.jpg",
            "MUSIC_COVER.png",
            "MUSIC_COVER.webp",
            "POSTER.png",
            "poster.png",
            "POSTER.jpg",
            "POSTER.jpeg",
            "poster.jpg",
            "poster.jpeg",
            "cover.jpg",
            "cover.png",
            "cover.webp",
            "manual_cover.jpg",
            "music_cover.jpg",
        ):
            candidate = tmp_dir / filename
            if candidate.is_file():
                return candidate
    return None


def _resolve_execution_review_temp_dir(meta_data: Mapping[str, object]) -> Path | None:
    """Resolve a release temp directory from trusted execution metadata."""
    meta_uuid = _stringify_preview_value(meta_data.get("uuid"))
    if not meta_uuid:
        return None
    temp_root = (context_mod.STATE_DIR / "tmp").resolve()
    try:
        temp_dir = (temp_root / meta_uuid).resolve()
        temp_dir.relative_to(temp_root)
    except OSError, ValueError:
        return None
    if not temp_dir.is_dir():
        return None
    return temp_dir


def _resolve_execution_screenshot_review(session_id: str) -> tuple[Path, Mapping[str, object]] | None:
    """Resolve the current execution's screenshot directory without trusting client paths."""
    _execution_path, meta_file, meta_data = _resolve_execution_preview_meta(session_id)
    if meta_file is None or meta_data is None:
        return None
    temp_dir = _resolve_execution_review_temp_dir(meta_data)
    if temp_dir is None:
        return None
    return temp_dir, meta_data


def _resolve_execution_description_review(session_id: str) -> tuple[Path, Path, dict[str, object]] | None:
    """Resolve the active description draft through the execution session only."""
    _execution_path, meta_file, meta_data = _resolve_execution_preview_meta(session_id)
    if meta_file is None or meta_data is None:
        return None
    temp_dir = _resolve_execution_review_temp_dir(meta_data)
    if temp_dir is None:
        return None
    return temp_dir, meta_file, dict(meta_data)


def _screenshot_capture_supported(meta_data: Mapping[str, object]) -> bool:
    """Return whether review actions may capture new frames or book pages.

    GAME images come from IGDB and MUSIC artwork is not video, so there is
    nothing meaningful to capture for those categories. Ebooks capture pages
    locally; audiobooks have no pages and hosted book images cannot be mixed.
    """
    category = _stringify_preview_value(meta_data.get("category")).upper()
    if category in {"GAME", "MUSIC"}:
        return False
    if category == "BOOK":
        # The early snapshot may still point at the release folder; pages need the resolved book file.
        filelist = meta_data.get("filelist")
        candidates: list[object] = [*(filelist if _is_obj_list(filelist) else []), meta_data.get("path")]
        has_source = any(isinstance(candidate, str) and candidate and Path(candidate).is_file() for candidate in candidates)
        image_list = meta_data.get("image_list")
        return has_source and not meta_data.get("audiobook") and not (_is_obj_list(image_list) and image_list)
    is_disc = meta_data.get("is_disc")
    return not is_disc or is_disc == "BDMV"


def _hosted_image_discard_supported(meta_data: Mapping[str, object]) -> bool:
    """Return whether hosted images may be discarded from the review.

    The upload stage captures fresh video frames (DVDs included) when discards
    leave the list below the cutoff.  IGDB, music and book images have no such
    replacement, so they stay as they are.
    """
    return _stringify_preview_value(meta_data.get("category")).upper() not in {"GAME", "MUSIC", "BOOK"}


def _screenshot_review_meta(temp_dir: Path, meta_data: Mapping[str, object]) -> Mapping[str, object]:
    """Include cached hosted images when a resumed run has not restored them into meta.json yet."""
    result = dict(meta_data)
    if result.get("image_list"):
        return result
    try:
        cached = _json_load_dict((temp_dir / "image_data.json").read_text(encoding="utf-8"))
    except Exception:
        cached = None
    if cached and _is_obj_list(cached.get("image_list")):
        result["image_list"] = cached["image_list"]
    return result


class MetadataSource(TypedDict, total=False):
    """Serialized metadata provider/source entry for the execution preview."""

    key: str
    label: str
    value: str
    url: str


class PreviewDetailItem(TypedDict):
    key: str
    label: str
    value: str


class PreviewDetailSection(TypedDict):
    key: str
    label: str
    items: list[PreviewDetailItem]


class ProgressItem(TypedDict, total=False):
    id: str
    label: str
    current: float
    total: float
    detail: str
    status: str
    group: str
    unit: str
    updated_at: float


class ExecutionPreview(TypedDict, total=False):
    """Serialized preview data for the media currently being processed."""

    media_id: str
    path: str
    filename: str
    title: str
    original_title: str
    year: str
    category: str
    media_type: str
    source: str
    resolution: str
    tmdb: str
    imdb: str
    metadata_sources: list[MetadataSource]
    poster_url: str
    backdrop_url: str
    overview: str
    genres: list[str]
    name: str
    status: str
    audio: str
    audio_tracks: list[dict[str, object]]
    subtitle_tracks: list[dict[str, object]]
    service: str
    networks: list[str]
    season: str
    episode: str
    episode_title: str
    episode_name: str
    episode_overview: str
    tv_pack: bool
    author: str
    narrator: str
    publisher: str
    book_language: str
    audiobook: bool
    audiobook_duration: str
    audiobook_bitrate: str
    book_series: str
    book_series_index: str
    platform: str
    game_version: str
    game_subcategory: str
    game_region: str
    game_system: str
    developer: str
    music: dict[str, object]
    detail_sections: list[PreviewDetailSection]
    awaiting_input: bool
    input_type: str | None
    progress: list[ProgressItem] | list[dict[str, object]]
