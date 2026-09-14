"""Shared, tracker-specific release title markers."""

import re
import unicodedata
from collections.abc import Mapping
from pathlib import Path

from src.meta import Meta
from src.release_name import (
    NameContext,
    NameRule,
    NameSelector,
    ReleaseNameBuilder,
    TrackerNameProfile,
    conditional,
    replace_context_value_with,
    replace_text,
    template,
)

INCOMPLETE_PACK_TRACKERS = frozenset(
    {
        "AITHER",
        "AVISTAZ",
        "CINEMAZ",
        "DARKPEERS",
        "HAWKEUNO",
        "HDBITS",
        "HDSPACE",
        "HDTORRENTS",
        "IPTORRENTS",
        "LST",
        "OLDTOONSWORLD",
        "ONLYENCODES",
        "PRIVATEHD",
        "RASTASTUGAN",
        "TORRENTLEECH",
        "ULCX",
        "YUSCENE",
    }
)


def add_incomplete_pack_marker(name: str, meta: Meta, tracker: str) -> str:
    """Mark confirmed incomplete packs without changing shared season metadata."""
    if tracker not in INCOMPLETE_PACK_TRACKERS or not getattr(meta, "season_pack_incomplete", False) or not meta.tv_pack or meta.category != "TV":
        return name

    season = str(meta.season or "")
    if season.isdigit():
        season = f"S{int(season):02d}"
    if not re.fullmatch(r"S\d+(?:-S?\d+)?", season, flags=re.IGNORECASE):
        return name

    # Match the whole season token, never the prefix of S030 or S03E02.
    # Consume an existing adjacent marker so repeated formatting is idempotent.
    pattern = rf"(?<![A-Za-z0-9])({re.escape(season)})(?![A-Za-z0-9])(?:[ ._-]+INCOMPLETE(?![A-Za-z0-9]))*"

    def insert(match: re.Match[str]) -> str:
        separator = "." if name[match.end() : match.end() + 1] == "." else " "
        return f"{match.group(1)}{separator}INCOMPLETE"

    return re.sub(pattern, insert, name, count=1, flags=re.IGNORECASE)


def add_incomplete_pack_marker_transform(name: str, context: NameContext) -> str:
    return add_incomplete_pack_marker(name, context.meta, context.values.get("tracker", ""))


BASE_NAME_PROFILE = TrackerNameProfile(rules=(NameRule(NameSelector(), template("base_name")),))
BASE_NAME_WITH_INCOMPLETE_PROFILE = TrackerNameProfile(
    rules=(NameRule(NameSelector(), template("base_name")),),
    transforms=(add_incomplete_pack_marker_transform,),
)
TITLE_NAME_PROFILE = TrackerNameProfile(rules=(NameRule(NameSelector(), template("title")),))
SOURCE_NAME_PROFILE = TrackerNameProfile(rules=(NameRule(NameSelector(), template("source_name")),))
SCENE_OR_BASENAME_PROFILE = TrackerNameProfile(rules=(NameRule(NameSelector(), template("scene_or_basename")),))


def invalid_group_suffix(suffix: str, *, dotted: bool = False):
    invalid_tags = ("nogrp", "nogroup", "unknown", "-unk-")

    def transform(name: str, context: NameContext) -> str:
        if dotted:
            name = name.replace(" ", ".")
        tag = context.values.get("tag", "")
        if not tag or any(invalid in tag.lower() for invalid in invalid_tags):
            for invalid in invalid_tags:
                name = re.sub(f"-{invalid}", "", name, flags=re.IGNORECASE)
            name = f"{name}-{suffix}"
        return name

    return transform


def remove_aka_and_sanitize(name: str, context: NameContext) -> str:
    aka = context.values.get("alt_title", "").strip()
    if aka:
        name = name.replace(f" {aka} ", " ")
    name = re.sub(r"[^A-Za-z0-9 ._+-]+", "", name)
    return re.sub(r"\s+", " ", name).strip()


def polish_original_title(name: str, context: NameContext) -> str:
    meta = context.meta
    imdb_info = getattr(meta, "imdb_info", {})
    if getattr(meta, "original_language", "") == "pl" and imdb_info:
        name = name.replace(context.values.get("alt_title", ""), "")
        name = name.replace(context.values.get("title", ""), str(imdb_info.get("aka", "")))
    return name.strip()


def imdb_title_transform(*, remove_web_hybrid: bool = False, anime_aka: bool = True, add_dv_profile: bool = False):
    def transform(name: str, context: NameContext) -> str:
        meta = context.meta
        imdb_info = getattr(meta, "imdb_info", {})
        imdb_name = str(imdb_info.get("title", ""))
        imdb_year = str(imdb_info.get("year", ""))
        imdb_aka = str(imdb_info.get("aka", ""))
        year = str(getattr(meta, "year", "")) if getattr(meta, "year", None) is not None else ""
        aka = context.values.get("alt_title", "")
        if imdb_name.strip():
            if aka:
                name = name.replace(f"{aka} ", "", 1)
            name = name.replace(context.values.get("title", ""), imdb_name, 1)
            allow_aka = anime_aka or not getattr(meta, "anime", False)
            if imdb_aka.strip() and imdb_aka != imdb_name and not getattr(meta, "no_aka", False) and allow_aka:
                name = name.replace(imdb_name, f"{imdb_name} AKA {imdb_aka}", 1)
        if context.values.get("category") != "TV" and imdb_year.strip() and year.strip() and imdb_year != year:
            name = name.replace(year, imdb_year, 1)
        if remove_web_hybrid:
            if context.values.get("type") == "WEBDL" and (
                "hybrid" in str(getattr(meta, "edition", "")).lower() or getattr(meta, "webdv", False)
            ):
                name = name.replace("Hybrid ", "", 1)
            if getattr(meta, "webdv", False):
                name = name.replace("HYBRID ", "", 1)
        if add_dv_profile and getattr(meta, "tracker_status", {}).get(context.values.get("tracker", ""), {}).get("other", False):
            resolution = context.values.get("resolution", "")
            name = name.replace(resolution, f"{resolution} DVP5/DVP8", 1)
        return name

    return transform


def remove_tv_episode_title(name: str, context: NameContext) -> str:
    meta = context.meta
    episode_title = str(getattr(meta, "episode_title", ""))
    resolution = context.values.get("resolution", "")
    if context.values.get("category") == "TV" and episode_title:
        return name.replace(f"{episode_title} {resolution}", resolution, 1)
    return name


def asian_cinema_transform(name: str, context: NameContext) -> str:
    meta = context.meta
    aka = context.values.get("alt_title", "")
    original_title = str(getattr(meta, "original_title", ""))
    title = context.values.get("title", "")
    marker = chr(0x202A)
    if aka:
        name = name.replace(f"{aka} ", f" / {original_title} {marker}")
    elif title != original_title:
        name = name.replace(title, f"{title} / {original_title} {marker}")
    audio = context.values.get("audio", "")
    if "AAC" in audio:
        name = name.replace(audio.strip().replace("  ", " "), audio.replace("AAC ", "AAC"))
    for old, new in (("DD+ ", "DD+"), ("UHD BluRay REMUX", "Remux"), ("BluRay REMUX", "Remux"), ("H.265", "HEVC"), (" Atmos", "")):
        name = name.replace(old, new)
    if context.values.get("is_disc", "") == "DVD":
        source = context.values.get("source", "")
        resolution = context.values.get("resolution", "")
        name = name.replace(f"{source} DVD5", f"{resolution} DVD {source}")
        name = name.replace(f"{source} DVD9", f"{resolution} DVD {source}")
        if audio == str(getattr(meta, "channels", "")):
            name = name.replace(audio, f"MPEG {audio}")
    return name + context.values.get("suffix", "")


def normalize_release_name(*, append_unrar: bool = False):
    def transform(name: str, context: NameContext) -> str:
        scene_name = context.values.get("scene_name", "")
        name = name.replace("DD+", "DDP").replace("DTS:", "DTS-").replace("HDR10+", "HDR10P")
        name = unicodedata.normalize("NFD", name)
        name = "".join(char for char in name if char.isascii() and (char.isalnum() or char in (" ", ".", "-")))
        name = name.replace("!", "")
        return f"{name} [UNRAR]" if append_unrar and scene_name else name

    return transform


def nordic_name_transform(name: str, _context: NameContext) -> str:
    name = name.replace(" ", ".").translate(
        str.maketrans({"Æ": "AE", "æ": "ae", "Ð": "D", "ð": "d", "Ø": "O", "ø": "o", "Þ": "TH", "þ": "th", "Å": "A", "å": "a", "Œ": "OE", "œ": "oe", "ß": "ss"})
    )
    name = name.replace("HDR10+", "HDR10P").replace("DD+", "DDP").replace("DTS:X", "DTS-X").replace("&", "and")
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    name = re.sub(r"\(((?:19|20)\d{2})\)", r"\1", name)
    name = re.sub(r"[^A-Za-z0-9._()\-]+", ".", name)
    return re.sub(r"\.{2,}", ".", name).strip(".")


def strip_known_extension(name: str, _context: NameContext) -> str:
    path = Path(name)
    return path.stem if path.suffix.lower() in {".mkv", ".mp4", ".avi", ".ts"} else name


def insert_foreign_language(name: str, context: NameContext) -> str:
    language = context.values.get("foreign_language", "")
    resolution = context.values.get("resolution", "")
    return name.replace(resolution, f"{language} {resolution}", 1) if language else name


def configured_metadata_name(*, append_unrar: bool = False):
    normalized = normalize_release_name(append_unrar=append_unrar)

    def transform(name: str, context: NameContext) -> str:
        return normalized(name, context) if context.values.get("use_metadata_name") == "1" else name

    return transform


def alpha_ratio_name(name: str, context: NameContext) -> str:
    meta = context.meta
    if not getattr(meta, "scene", False):
        path = Path(name)
        if path.suffix.lower() in {".mkv", ".mp4", ".avi", ".ts"}:
            name = path.stem
        for old, new in ((" ", "."), ("'", ""), (":", ""), ("(", "."), (")", "."), ("[", "."), ("]", "."), ("{", "."), ("}", ".")):
            name = name.replace(old, new)
        name = re.sub(r"\.{2,}", ".", name)
    tag = context.values.get("tag", "")
    invalid_tags = ("nogrp", "nogroup", "unknown", "-unk-")
    if not tag or any(invalid in tag.lower() for invalid in invalid_tags):
        for invalid in invalid_tags:
            name = re.sub(f"-{invalid}", "", name, flags=re.IGNORECASE)
        name = f"{name}-NoGRP"
    return name


def _btn_clean(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    value = value.replace("&", " and ").replace("'", "")
    value = re.sub(r"\s+", ".", value.strip())
    value = re.sub(r"(?i)\.DDP\.(\d(?:\.\d+)?)\.Atmos", r".DDPA\1", value)
    value = re.sub(r"(?i)\.TrueHD\.(\d(?:\.\d+)?)\.Atmos", r".TrueHDA\1", value)
    value = re.sub(r"(?i)\.(DDP|DD|AC3|DTS|AAC|FLAC|TrueHD|PCM|LPCM)\.(\d)", r".\1\2", value)
    value = re.sub(r"[^A-Za-z0-9.\-]+", ".", value)
    return re.sub(r"\.{2,}", ".", value).strip(".-")


def broadcasthe_net_name(name: str, context: NameContext) -> str:
    meta = context.meta
    name = re.sub(r"(?i)\.(avi|mkv|mp4|ts|m4v|m2ts|wmv|mpeg|mpg|vob)$", "", name)
    name = _btn_clean(name)
    if not context.values.get("scene_name"):
        aka = _btn_clean(context.values.get("alt_title", ""))
        if aka:
            name = re.sub(rf"(?i)(?:^|\.){re.escape(aka)}(?=\.|$)", ".", name, count=1)
        hdr = _btn_clean(context.values.get("hdr", ""))
        resolution = _btn_clean(context.values.get("resolution", ""))
        if hdr and resolution:
            hdr_pattern = rf"(?i)(?:^|\.){re.escape(hdr)}(?=\.|$)"
            resolution_pattern = rf"(?i)(?:^|\.){re.escape(resolution)}(?=\.|$)"
            if re.search(hdr_pattern, name) and re.search(resolution_pattern, name):
                name = re.sub(hdr_pattern, ".", name, count=1)
                name = re.sub(resolution_pattern, f".{hdr}.{resolution}", name, count=1)
        name = re.sub(r"\.{2,}", ".", name).strip(".")
    if context.values.get("resolution", "").lower() in {"sd", "480i", "480p", "576i", "576p"}:
        name = re.sub(r"(?i)(?:^|\.)(?:sd|\d{3,4}[pi])(?=\.|$)", ".", name)
        name = re.sub(r"\.{2,}", ".", name).strip(".")
    tag = context.values.get("tag", "").lstrip("-")
    if tag and not re.search(r"-[^.\-]+$", name):
        name += f"-{tag}"
    elif not tag and not re.search(r"-(?:nogrp|nogroup|unknown|unk)$", name, re.I):
        name += "-NOGRP"
    return name


def locadora_name(name: str, context: NameContext) -> str:
    replacements = {
        ".mkv": "", ".mp4": "", ".": " ", "DDP2 0": "DDP2.0", "DDP5 1": "DDP5.1", "H 264": "H.264",
        "H 265": "H.265", "DD+7 1": "DDP7.1", "AAC2 0": "AAC2.0", "DD5 1": "DD5.1", "DD2 0": "DD2.0",
        "TrueHD 7 1": "TrueHD 7.1", "TrueHD 5 1": "TrueHD 5.1", "DTS-HD MA 7 1": "DTS-HD MA 7.1",
        "DTS-HD MA 5 1": "DTS-HD MA 5.1", "DTS-X 7 1": "DTS-X 7.1", "DTS-X 5 1": "DTS-X 5.1",
        "FLAC 2 0": "FLAC 2.0", "FLAC 5 1": "FLAC 5.1", "DD1 0": "DD1.0", "DTS ES 5 1": "DTS ES 5.1",
        "DTS5 1": "DTS 5.1", "AAC1 0": "AAC1.0", "DD+5 1": "DDP5.1", "DD+2 0": "DDP2.0", "DD+1 0": "DDP1.0",
    }
    for old, new in replacements.items():
        name = name.replace(old, new)
    return invalid_group_suffix("NoGroup")(name, context)


def old_toons_world_name(name: str, context: NameContext) -> str:
    meta = context.meta
    aka = context.values.get("alt_title", "")
    if aka:
        name = name.replace(f"{aka} ", "")
    source = context.values.get("source", "")
    resolution = context.values.get("resolution", "")
    if context.values.get("is_disc") == "DVD" or (context.values.get("type") == "REMUX" and source in ("PAL DVD", "NTSC DVD", "DVD")):
        name = name.replace(source, f"{resolution} {source}", 1)
        audio = context.values.get("audio", "")
        name = name.replace(audio, f"{context.values.get('video_codec', '')} {audio}", 1)
    if context.values.get("category") == "TV" and not getattr(meta, "no_year", False) and not getattr(meta, "search_year", ""):
        candidates: list[int] = []
        tmdb_year = str(getattr(meta, "year", "")) if getattr(meta, "year", None) is not None else ""
        if tmdb_year.isdigit():
            year = tmdb_year
        else:
            imdb_year = getattr(meta, "imdb_info", {}).get("year")
            series_year = getattr(meta, "tvdb_episode_data", {}).get("series_year")
            for candidate in (imdb_year, series_year):
                if candidate and str(candidate).isdigit():
                    candidates.append(int(candidate))
            year = str(min(candidates)) if candidates else ""
        title = context.values.get("title", "")
        name = name.replace(title, f"{title} {year}", 1)
    return add_incomplete_pack_marker_transform(name, context)


def aither_name(name: str, context: NameContext) -> str:
    meta = context.meta
    resolution = context.values.get("resolution", "")
    source = context.values.get("source", "")
    name_type = context.values.get("type", "")
    video_codec = context.values.get("video_codec", "")
    video_encode = context.values.get("video_encode", "")
    year = context.values.get("year", "")
    foreign_language = context.values.get("foreign_language", "")
    if foreign_language:
        if name_type == "REMUX" and source in ("PAL DVD", "NTSC DVD", "DVD"):
            if year:
                name = name.replace(year, f"{year} {foreign_language}", 1)
        elif context.values.get("is_disc") != "BDMV":
            name = name.replace(resolution, f"{foreign_language} {resolution}", 1)
    audio = context.values.get("audio", "")
    if name_type == "DVDRIP":
        name = name.replace(f"{source} ", "", 1).replace(video_encode, "", 1)
        name = name.replace("DVDRip", f"{resolution} DVDRip", 1).replace(audio, f"{audio}{video_encode}", 1)
    elif context.values.get("is_disc") == "DVD":
        region = context.values.get("region", "")
        region_source = " ".join(part for part in (region, source) if part)
        details = " ".join(part for part in (resolution, region, source) if part)
        if region_source:
            name = name.replace(region_source, details, 1)
        name = name.replace(audio, f"{video_codec} {audio}", 1)
    elif name_type == "REMUX" and source in ("PAL DVD", "NTSC DVD", "DVD"):
        name = name.replace(source, f"{resolution} {source}", 1).replace(audio, f"{video_codec} {audio}", 1)
    if getattr(meta, "trump_reason", "") == "exact_match":
        name += " - TRUMP"
    alt_title = context.values.get("alt_title", "")
    if alt_title and year:
        name = name.replace(f"{year} {alt_title}", f"{alt_title} {year}", 1)
    return add_incomplete_pack_marker_transform(name, context)


def dreadvault_name(name: str, context: NameContext) -> str:
    resolution = context.values.get("resolution", "")
    source = context.values.get("source", "")
    name_type = context.values.get("type", "")
    video_codec = context.values.get("video_codec", "")
    video_encode = context.values.get("video_encode", "").strip()
    audio = context.values.get("audio", "")
    year = context.values.get("year", "")
    if name_type == "DVDRIP":
        name = name.replace(f"{source} ", "", 1).replace(f" {video_encode}", "", 1)
        name = name.replace("DVDRip", f"{resolution} DVDRip", 1).replace(audio, f"{audio} {video_encode}", 1)
    elif context.values.get("is_disc") == "DVD":
        region = context.values.get("region", "")
        region_source = " ".join(part for part in (region, source) if part)
        details = " ".join(part for part in (resolution, region, source) if part)
        if region_source:
            name = name.replace(region_source, details, 1)
        name = name.replace(audio, f"{video_codec} {audio}", 1)
    elif name_type == "REMUX" and source in ("PAL DVD", "NTSC DVD", "DVD"):
        name = name.replace(source, f"{resolution} {source}", 1).replace(audio, f"{video_codec} {audio}", 1)
    alt_title = context.values.get("alt_title", "")
    if alt_title and year:
        name = name.replace(f"{year} {alt_title}", f"{alt_title} {year}", 1)
    language = context.values.get("foreign_language", "")
    if language:
        dvd_remux = name_type == "REMUX" and source in ("PAL DVD", "NTSC DVD", "DVD")
        if dvd_remux and year:
            name = name.replace(year, f"{year} {language}", 1)
        elif context.values.get("is_disc") != "BDMV":
            for anchor in (resolution, context.values.get("service", ""), source):
                if anchor and anchor in name:
                    name = name.replace(anchor, f"{language} {anchor}", 1)
                    break
    return name


def only_encodes_name(name: str, context: NameContext) -> str:
    name = imdb_title_transform()(name, context)
    meta = context.meta
    resolution = context.values.get("resolution", "")
    video_encode = context.values.get("video_encode", "")
    name_type = context.values.get("type", "")
    source = context.values.get("source", "")
    audio = context.values.get("audio", "")
    video_codec = context.values.get("video_codec", "")
    if name_type == "DVDRIP":
        if context.values.get("category") == "MOVIE":
            name = name.replace(f"{source}{video_encode}", resolution, 1).replace(audio, f"{audio}{video_encode}", 1)
        else:
            name = name.replace(source, resolution, 1).replace(video_codec, f"{audio} {video_codec}", 1)
    language = context.values.get("foreign_language", "")
    if language and context.values.get("is_disc") != "BDMV":
        name = name.replace(resolution, f"{language} {resolution}", 1)
    basename = context.values.get("basename_no_ext", "")
    scale = "DS4K" if "DS4K" in basename.upper() else "RM4K" if "RM4K" in basename.upper() else ""
    if name_type in ("ENCODE", "WEBDL", "WEBRIP") and scale:
        if scale not in name and resolution in name:
            name = name.replace(resolution, f"{resolution} {scale}", 1)
        elif resolution and f"{resolution} {scale}" not in name:
            name = name.replace(scale, f"{resolution} {scale}", 1)
    name = invalid_group_suffix("NOGRP")(name, context)
    return add_incomplete_pack_marker_transform(name, context)


def non_scene_dotted_name(name: str, context: NameContext) -> str:
    if not getattr(context.meta, "scene", False):
        for old, new in ((".mkv", ""), (".mp4", ""), (".torrent", ""), (" ", ".")):
            name = name.replace(old, new)
    return name


def append_context_value(field_name: str):
    def transform(name: str, context: NameContext) -> str:
        return name + context.values.get(field_name, "")

    return transform


def iptorrents_name(name: str, context: NameContext) -> str:
    replacements = {
        "3DAccess": "3DA", "AreaFiles": "AF", "BeyondHD": "BHD", "Blu-Bits": "BluHD", "Bluebird": "BB",
        "BlueEvolution": "BluEvo", "Chdbits": "CHD", "HDAccess": "HDA", "HDChina": "HDC", "HDClub": "HDCL",
        "HDGeek": "HDG", "HDRoad": "HDR", "HDStar": "HDS", "HDWing": "HDW", "ExtraTorrent": "ETRG",
        "IWStream": "IWS", "Kingdom-KVCD": "KVCD", "MVGroup": "MVG", "Projekt-Revolution": "Projekt",
        "PublicHD": "PHD", "SpaceHD": "SHD", "ThumperDC": "TDC", "TheWolfsDen": "TWD",
    }
    for old, new in replacements.items():
        if old in name:
            name = name.replace(old, new)
    name = name.replace("'", "").replace('"', "")
    if getattr(context.meta, "scene", False) and "[NO RAR]" not in name.upper():
        name += " [NO RAR]"
    name = re.sub(r"\s{2,}", " ", name)
    return add_incomplete_pack_marker_transform(name, context)


def capybara_video_name(name: str, context: NameContext) -> str:
    meta = context.meta
    if context.values.get("category") not in ("MOVIE", "TV"):
        return re.sub(r"\s{2,}", " ", name)
    for old, new in (("DD+ ", "DDP"), ("DD ", "DD"), ("AAC ", "AAC"), ("FLAC ", "FLAC"), ("Dubbed", ""), ("Dual-Audio", "")):
        name = name.replace(old, new)
    if meta.category in ("TV", "ANIMES"):
        year = str(meta.year) if meta.year is not None else ""
        if year and year in name:
            name = name.replace(f"({year})", "").replace(year, "").strip()
    if meta.original_language != "pt":
        name = name.replace(meta.aka, "")
    elif meta.aka:
        localized = meta.aka.replace("AKA", "").strip()
        name = name.replace(meta.aka, "").replace(meta.title, localized).strip()
    if context.values.get("tracker") == "CAPYBARABR" and meta.type == "DVDRIP":
        title = meta.aka.replace("AKA", "").strip() if meta.original_language == "pt" and meta.aka else meta.title
        episode = f"{meta.season}{meta.episode}" if meta.category == "TV" else ""
        audio = str(meta.audio)
        for old, new in (("DD+ ", "DDP"), ("DD ", "DD"), ("AAC ", "AAC"), ("FLAC ", "FLAC")):
            audio = audio.replace(old, new)
        name = " ".join(part for part in (title, str(meta.year or ""), episode, meta.resolution, "DVDRip", audio, meta.video_encode) if part)
        if meta.tag:
            name += meta.tag
    if not meta.is_disc and meta.audio_languages:
        try:
            languages = set(meta.audio_languages)
        except TypeError:
            languages = set()
        if any(lang.lower() == "portuguese" or lang == "português" for lang in languages):
            audio_tag = " MULTI" if len(languages) >= 3 else " DUAL" if len(languages) == 2 else ""
            if audio_tag and "-" in name:
                parts = name.rsplit("-", 1)
                match = next((found for source in (meta.path, meta.uuid) if source and (found := re.search(r"-([^.-]+)\.(?:DUAL|MULTI)(?=-|\.|$)", str(source), re.I))), None)
                group = (meta.tag or "").lstrip("-")
                name = f"{parts[0]}-{match.group(1)}{audio_tag}-{parts[1]}" if match and match.group(1).casefold() != group.casefold() else f"{parts[0]}{audio_tag}-{parts[1]}"
            elif audio_tag:
                name += audio_tag
    name = invalid_group_suffix("NoGroup")(name, context)
    return re.sub(r"\s{2,}", " ", name)


def avistaz_name(name: str, context: NameContext) -> str:
    meta = context.meta
    tracker = context.values.get("tracker", "")
    for value in (meta.aka or "", meta.manual_episode_title or "", meta.daily_episode_title or "", "Dubbed", "Dual-Audio"):
        name = name.replace(value, "")
    if tracker in ("CINEMAZ", "PRIVATEHD"):
        for term in (r"\bLIMITED\b", r"\bCriterion Collection\b", r"\b\d{1,3}(?:st|nd|rd|th)\s+Anniversary Edition\b"):
            name = re.sub(term, "", name, flags=re.IGNORECASE).strip()
        name = re.sub(r"\bDirector[’'`]s\s+Cut\b", "DC", name, flags=re.IGNORECASE)
        name = re.sub(r"\bExtended\s+Cut\b", "EXT" if tracker == "CINEMAZ" else "Extended", name, flags=re.IGNORECASE)
        name = re.sub(r"\bTheatrical\s+Cut\b", "TC" if tracker == "CINEMAZ" else "Theatrical", name, flags=re.IGNORECASE)
        name = name.replace("[", "").replace("]", "")
        if tracker == "CINEMAZ" and (meta.webdv or "hybrid" in (meta.edition or "").casefold()):
            title_match = re.search(re.escape(meta.title), name, flags=re.IGNORECASE) if meta.title else None
            start = title_match.end() if title_match else 0
            hybrid = re.search(r"\bHYBRID\b", name[start:], flags=re.IGNORECASE)
            if hybrid:
                begin, end = start + hybrid.start(), start + hybrid.end()
                without = f"{name[:begin]}{name[end:]}"
                resolution = re.search(r"\b(?:\d{3,4}[pi]|4K|UHD|SD)\b", without, flags=re.IGNORECASE)
                if resolution:
                    name = f"{without[:resolution.end()]} HYBRID{without[resolution.end():]}"
        name = re.sub(r"\s{2,}", " ", name).strip()
    if meta.has_encode_settings:
        name = name.replace("H.264", "x264").replace("H.265", "x265")
    tag = meta.tag or ""
    invalid = ("nogrp", "nogroup", "unknown", "-unk-")
    if not tag or any(item in tag.lower() for item in invalid):
        for item in invalid:
            name = re.sub(f"-{item}", "", name, flags=re.IGNORECASE)
        if tracker == "CINEMAZ":
            name += "-NoGroup"
        if tracker == "PRIVATEHD":
            name += "-NOGROUP"
    if meta.category == "TV":
        year = meta.year
        if not meta.no_year and not meta.search_year:
            season_year = next((item.get("year") for item in meta.imdb_info.get("seasons_summary", []) if item.get("season") == meta.season_int), None) if meta.season_int else None
            year = season_year or year
            if year:
                name = name.replace(meta.title, f"{meta.title} {year}", 1)
        if tracker == "PRIVATEHD" and year:
            name = name.replace(str(year), "")
        if tracker == "AVISTAZ" and meta.tv_pack and year:
            name = name.replace(f"{meta.title} {year} {meta.season}", f"{meta.title} {meta.season} {year}")
    source = meta.source
    if meta.type == "DVDRIP" and source:
        name = name.replace(source, "")
    if meta.is_disc == "DVD":
        if meta.region:
            name = name.replace(meta.region, "")
        if source and meta.resolution:
            name = name.replace(source, meta.resolution)
        if meta.audio:
            suffix = f" {meta.video_codec.strip()}" if meta.video_codec.strip() else ""
            name = name.replace(meta.audio, f"{meta.audio}{suffix}")
    name = re.sub(r"\s{2,}", " ", name)
    return add_incomplete_pack_marker_transform(name, context)


def latteam_video_name(name: str, context: NameContext) -> str:
    meta = context.meta
    if meta.category == "BOOK":
        return re.sub(r"\s{2,}", " ", name).strip()
    aka = meta.aka
    name = name.replace("Dual-Audio", "").replace("Dubbed", "").replace(aka, "")
    if meta.type != "DISC":
        if meta.original_language == "es" and aka:
            name = name.replace(meta.title, aka.replace("AKA", "")).strip()
        latin_codes = {
            "es-419",
            "es-ar",
            "es-bo",
            "es-cl",
            "es-co",
            "es-cr",
            "es-do",
            "es-ec",
            "es-gt",
            "es-hn",
            "es-mx",
            "es-ni",
            "es-pa",
            "es-pe",
            "es-pr",
            "es-py",
            "es-sv",
            "es-uy",
            "es-ve",
        }
        latin = castilian = False
        found = 0
        for track in meta.mediainfo.get("media", {}).get("track", [])[2:]:
            if not isinstance(track, dict) or track.get("@type") != "Audio":
                continue
            language = str(track.get("Language", "")).lower()
            title = str(track.get("Title", "")).lower()
            if "commentary" in title:
                continue
            if language in latin_codes or (language == "es" and any(word in title for word in ("latino", "latin america"))):
                latin = True
                found += 1
            elif (language == "es" and "castellano" in title) or language in ("es", "es-es"):
                castilian = True
                found += 1
        if found and castilian and not latin:
            name = name.replace(meta.tag, f" [CAST]{meta.tag}") if meta.tag else f"{name} [CAST]"
        elif not found:
            name = name.replace(meta.tag, f" [SUBS]{meta.tag}") if meta.tag else f"{name} [SUBS]"
    return re.sub(r"\s{2,}", " ", name)


def midnight_scene_name(name: str, context: NameContext) -> str:
    if context.values.get("category") == "MUSIC":
        return name
    language = context.values.get("foreign_language", "")
    if language:
        name = re.sub(r"\bDual-Audio\b", "", name, flags=re.IGNORECASE)
        name = " ".join(name.split())
        source = context.values.get("source", "")
        if context.values.get("type") == "REMUX" and source in ("PAL DVD", "NTSC DVD", "DVD"):
            year = str(getattr(context.meta, "year", "") or "")
            if year:
                name = name.replace(year, f"{year} {language}", 1)
        elif context.values.get("is_disc") != "BDMV":
            resolution = context.values.get("resolution", "")
            name = name.replace(resolution, f"{language} {resolution}", 1)
    return name


def zenith_video_name(name: str, context: NameContext) -> str:
    meta = context.meta
    if meta.category == "TV" and meta.episode_title:
        name = name.replace(f"{meta.episode_title} {meta.resolution}", meta.resolution, 1)
    imdb_year = str(meta.imdb_info.get("year", ""))
    year = str(meta.year) if meta.year is not None else ""
    if meta.category != "TV" and imdb_year.strip() and year.strip() and imdb_year != year:
        name = name.replace(year, imdb_year, 1)
    return name


def darkpeers_video_name(name: str, context: NameContext) -> str:
    meta = context.meta
    if meta.category not in ("MUSIC", "BOOK"):
        if meta.category == "TV" and context.values.get("remove_tv_year"):
            title = str(meta.title or "").strip()
            year = str(meta.year or "").strip()
            name = re.sub(rf"^({re.escape(title)})\s+{re.escape(year)}(?=\s|$)", r"\1", name, count=1, flags=re.IGNORECASE)
            name = " ".join(name.split())
        audio = context.values.get("replacement_audio", "")
        if audio and "Dual-Audio" in name:
            name = name.replace("Dual-Audio", audio)
        return add_incomplete_pack_marker_transform(name, context)
    return name


def lst_name(name: str, context: NameContext) -> str:
    meta = context.meta
    if meta.category not in ("MUSIC", "BOOK") and meta.type == "DVDRIP":
        resolution = context.values.get("resolution", "")
        if meta.category == "MOVIE":
            name = name.replace(f"{meta.source}{meta.video_encode}", resolution, 1)
            name = name.replace(meta.audio, f"{meta.audio}{meta.video_encode}", 1)
        else:
            name = name.replace(str(meta.source), resolution, 1)
            name = name.replace(meta.video_codec, f"{meta.audio} {meta.video_codec}", 1)
    group = context.values.get("group_suffix", "")
    if group:
        name += group
    if getattr(meta, "trump_reason", "") == "exact_match":
        name += " - TRUMP"
    return add_incomplete_pack_marker_transform(name, context)


def _dvd_source(context: NameContext) -> bool:
    return context.values.get("source", "") in {"PAL DVD", "NTSC DVD", "DVD", "NTSC", "PAL"}


INSERT_VIDEO_CODEC_BEFORE_DVD_AUDIO = conditional(
    _dvd_source,
    replace_context_value_with(
        "audio",
        lambda context: " ".join(part for part in (context.values.get("video_codec", ""), " ".join(context.values.get("audio", "").split())) if part),
    ),
)
DVD_CODEC_NAME_PROFILE = TrackerNameProfile(
    rules=(NameRule(NameSelector(), template("base_name")),),
    transforms=(INSERT_VIDEO_CODEC_BEFORE_DVD_AUDIO, replace_text(("DD+", "DDP"))),
)


def filelist_name_transform(name: str, context: NameContext) -> str:
    meta = context.meta
    hdr = context.values.get("hdr", "")
    audio = context.values.get("audio", "")
    if "DV" in hdr:
        name = name.replace(" DV ", " DoVi ")
    if context.values.get("type") in ("WEBDL", "WEBRIP", "ENCODE"):
        name = name.replace(audio, audio.replace(" ", "", 1))
    name = name.replace(context.values.get("alt_title", ""), "")
    imdb_info = getattr(meta, "imdb_info", {})
    if isinstance(imdb_info, dict):
        title = context.values.get("title", "")
        imdb_aka = str(imdb_info.get("aka", ""))
        if imdb_aka:
            name = name.replace(title, imdb_aka)
        meta_year = str(getattr(meta, "year", "")).strip() if getattr(meta, "year", None) is not None else ""
        imdb_year = str(imdb_info.get("year", meta_year))
        if meta_year and meta_year != imdb_year:
            name = name.replace(meta_year, imdb_year)
    basename = str(getattr(meta, "basename_no_ext", ""))
    if "DD+" in audio and "DDP" in basename:
        name = name.replace("DD+", "DDP")
    if "Atmos" in audio and "Atmos" not in basename:
        name = name.replace("Atmos", "")
    for old, new in (
        ("BluRay REMUX", "Remux"),
        ("BluRay Remux", "Remux"),
        ("Bluray Remux", "Remux"),
        ("PQ10", "HDR"),
        ("HDR10+", "HDR"),
        ("DoVi HDR HEVC", "HEVC DoVi HDR"),
        ("HDR HEVC", "HEVC HDR"),
        ("DoVi HEVC", "HEVC DoVi"),
        ("DTS7.1", "DTS"),
        ("DTS5.1", "DTS"),
        ("DTS2.0", "DTS"),
        ("DTS1.0", "DTS"),
        ("Dubbed", ""),
        ("Dual-Audio", ""),
    ):
        name = name.replace(old, new)
    name = " ".join(name.split())
    name = re.sub(r"[^0-9a-zA-ZÀ-ÿ. &+'\-\[\]]+", "", name)
    return name.replace(" ", ".").replace("..", ".")


def hdbits_name_transform(name: str, context: NameContext) -> str:
    meta = context.meta
    audio = context.values.get("audio", "")
    name = name.replace("H.265", "HEVC")
    service = context.values.get("service", "")
    if service:
        name = name.replace(f"{service} ", "", 1)
    hdr = context.values.get("hdr", "")
    if "DV" in hdr:
        name = name.replace(" DV ", " DoVi ")
    if "HDR" in hdr and "HDR10+" not in hdr:
        name = name.replace("HDR", "HDR10")
    compact_audio = audio.replace(" ", "", 1).replace(" Atmos", "") if context.values.get("type") in ("WEBDL", "WEBRIP", "ENCODE") else audio.replace(" Atmos", "")
    name = name.replace(audio, compact_audio)
    name = name.replace(context.values.get("alt_title", ""), "")
    imdb_info = getattr(meta, "imdb_info", {})
    if imdb_info:
        name = name.replace(context.values.get("title", ""), str(imdb_info["aka"]))
        meta_year = str(getattr(meta, "year", "")) if getattr(meta, "year", None) is not None else ""
        imdb_year = str(imdb_info.get("year", meta_year))
        if meta_year and meta_year != imdb_year:
            name = name.replace(meta_year, imdb_year)
    for old, new in (
        ("PQ10", "HDR"),
        ("Dubbed", ""),
        ("Dual-Audio", ""),
        ("REMUX", "Remux"),
        ("BluRay Remux", "Remux"),
        ("UHD Remux", "Remux"),
        ("DTS-HD HRA", "DTS-HD HR"),
    ):
        name = name.replace(old, new)
    name = " ".join(name.split())
    name = re.sub(r"[^0-9a-zA-ZÀ-ÿ. :&+'\-\[\]]+", "", name)
    return name.replace(" .", ".").replace("..", ".")


def hdtorrents_name_transform(name: str, context: NameContext) -> str:
    audio = context.values.get("audio", "")
    if context.values.get("type") in ("WEBDL", "WEBRIP", "ENCODE"):
        name = name.replace(audio, audio.replace(" ", "", 1))
    if "DV" in context.values.get("hdr", ""):
        name = name.replace(" DV ", " DoVi ")
    name = name.replace("BluRay REMUX", "Blu-ray Remux")
    name = " ".join(name.split())
    name = re.sub(r"[^0-9a-zA-ZÀ-ÿ. &+'\-\[\]]+", "", name)
    return name.replace(":", "").replace("..", " ").replace("  ", " ")


class TrackerNameMixin:
    name_profile: TrackerNameProfile = BASE_NAME_PROFILE
    tracker = ""

    async def get_name_overrides(self, _context: NameContext) -> Mapping[str, str]:
        return {}

    async def render_name(self, meta: Meta) -> str:
        builder = ReleaseNameBuilder()

        async def overrides(context: NameContext) -> Mapping[str, str]:
            values = {"tracker": str(getattr(self, "tracker", ""))}
            values.update(await self.get_name_overrides(context))
            return values

        name, _missing = await builder.render(meta, self.name_profile, overrides)
        return name


class StringTrackerNameMixin(TrackerNameMixin):
    async def get_name(self, meta: Meta) -> str:
        return await self.render_name(meta)
