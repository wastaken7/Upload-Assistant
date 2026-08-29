# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import asyncio
import json
import os
import re
from collections.abc import Callable
from importlib import import_module
from pathlib import Path
from typing import Any, cast

from src.console import logger
from src.meta import Meta

guessit_module = import_module("guessit")
GuessitFn = Callable[[str, dict[str, Any] | None], dict[str, Any]]
_TECHNICAL_HYPHEN_PREFIXES = {"blu", "dts", "web"}


def guessit_fn(value: str, options: dict[str, Any] | None = None) -> dict[str, Any]:
    return cast(dict[str, Any], guessit_module.guessit(value, options))


async def get_tag(video: str, meta: Meta, season_pack_check: bool = False) -> str:
    # Using regex from cross-seed (https://github.com/cross-seed/cross-seed/tree/master?tab=Apache-2.0-1-ov-file)
    release_group = None
    matched_anime = False

    # Try specialized regex patterns first
    if meta.anime:
        # Anime pattern: [Group] at the beginning
        basename_stripped = Path(video).stem
        anime_match = re.search(r"^\s*\[(.+?)\]", basename_stripped)
        if anime_match:
            matched_anime = True
            release_group = anime_match.group(1)
            logger.debug(f"Anime regex match: {release_group}")
    if (not meta.anime or not matched_anime) and meta.is_disc != "BDMV":
        # Non-anime pattern: group at the end after last hyphen, avoiding resolutions and numbers
        if Path(video).is_dir():
            # If video is a directory, use the directory name as basename
            basename_stripped = Path(os.path.normpath(video)).name
        elif (meta.tv_pack or meta.keep_folder or meta.category in ("BOOK", "GAME")) and not season_pack_check:
            basename_stripped = meta.uuid
        else:
            # If video is a file, use the filename without extension
            basename_no_path = Path(video).name
            name, ext = Path(basename_no_path).stem, Path(basename_no_path).suffix
            # If the extension contains a hyphen, it's not a real extension
            basename_stripped = basename_no_path if ext and "-" in ext else name
        # Strip common file extensions if present (e.g. from directories or custom uuid paths)
        known_extensions = {
            ".mkv",
            ".mp4",
            ".ts",
            ".avi",
            ".divx",
            ".m2ts",
            ".pdf",
            ".epub",
            ".mobi",
            ".cbz",
            ".cbr",
            ".mp3",
            ".m4b",
            ".flac",
            ".aac",
            ".m4a",
            ".ogg",
            ".wav",
            ".zip",
            ".rar",
            ".tar",
            ".7z",
        }
        name, ext = Path(basename_stripped).stem, Path(basename_stripped).suffix
        if ext.lower() in known_extensions:
            basename_stripped = name

        non_anime_match = re.search(
            r"(?<=-)((?!\s*(?:WEB-DL|Blu-ray|H-264|H-265))(?:\W|\b)(?!(?:\d{3,4}[ip]))(?!\d+\b)(?:\W|\b)([\w .]+?))(?:\[.+\])?(?:\))?(?:\s\[.+\])?$", basename_stripped
        )
        if non_anime_match:
            release_group = non_anime_match.group(1).strip()
            hyphen_idx = non_anime_match.start() - 1
            technical_prefix_match = re.search(r"([A-Za-z]+)$", basename_stripped[:hyphen_idx])
            if technical_prefix_match and technical_prefix_match.group(1).casefold() in _TECHNICAL_HYPHEN_PREFIXES:
                release_group = None

            # Prevent misinterpreting "Author - Title" space-hyphen-space separators as release groups
            if release_group and meta.category in ("BOOK", "GAME"):
                if hyphen_idx > 0 and basename_stripped[hyphen_idx - 1].isspace():
                    release_group = None
                else:
                    tag_norm = "".join(c for c in release_group.lower() if c.isalnum())
                    title_norm = "".join(c for c in (meta.title or "").lower() if c.isalnum())
                    author_norm = "".join(c for c in (meta.author or "").lower() if c.isalnum())
                    if tag_norm and (
                        tag_norm in (title_norm, author_norm)
                        or (len(tag_norm) >= 4 and (tag_norm in title_norm or tag_norm in author_norm))
                        or (len(title_norm) >= 4 and title_norm in tag_norm)
                        or (len(author_norm) >= 4 and author_norm in tag_norm)
                    ):
                        release_group = None
                    else:
                        # Rejoin an intra-word hyphen (e.g. "Spider-Man" -> "spiderman") so short
                        # trailing fragments of hyphenated title/author words aren't taken as groups
                        prefix_match = re.search(r"(\w+)$", basename_stripped[:hyphen_idx])
                        first_word_match = re.match(r"\w+", release_group)
                        if prefix_match and first_word_match:
                            merged = (prefix_match.group(1) + first_word_match.group(0)).lower()
                            merged = "".join(c for c in merged if c.isalnum())
                            if merged and (merged in title_norm or merged in author_norm):
                                release_group = None

            if release_group:
                if "Z0N3" in release_group:
                    release_group = release_group.replace("Z0N3", "D-Z0N3")
                if not meta.scene and len(release_group) > 12:
                    release_group = None
            logger.debug(f"Non-anime regex match: {release_group}")

    # If regex patterns didn't work, fall back to guessit
    if not release_group and meta.is_disc:
        try:
            parsed = guessit_fn(video)
            release_group = cast(str | None, parsed.get("release_group"))
            logger.debug(f"Guessit match: {release_group}")

        except Exception as e:
            logger.info(f"Error while parsing group tag: {e}")
            release_group = None

    # BDMV validation
    if meta.is_disc == "BDMV" and release_group and f"{release_group}" not in video:
        release_group = None

    # Format the tag
    tag = f"-{release_group}" if release_group else ""

    # Clean up any tags that are just a hyphen
    if tag == "-":
        tag = ""

    # Remove generic "no group" tags
    if tag and tag[1:].lower() in ["hd.ma.5.1", "untouched"]:
        tag = ""

    return tag


async def tag_override(meta: Meta) -> Meta:
    try:
        tags_text = await asyncio.to_thread(Path(f"{meta.base_dir}/data/tags.json").read_text, encoding="utf-8")
        tags = json.loads(tags_text)

        for tag in tags:
            value = tags.get(tag)
            if value.get("in_name", "") == tag and tag in meta.path:
                meta.tag = f"-{tag}"
            if meta.tag and meta.tag[1:] == tag:
                for key in value:
                    if key == "type":
                        if meta[key] == "ENCODE":
                            meta[key] = value.get(key)
                        else:
                            pass
                    elif key == "personalrelease":
                        meta[key] = _is_true(value.get(key, "False"))
                    elif key == "template":
                        meta.description_template = value.get(key)
                    else:
                        meta[key] = value.get(key)
    except Exception as e:
        logger.info(f"Error while loading tags.json: {e}")
        return meta
    return meta


def _is_true(value: Any) -> bool:
    return str(value).strip().lower() == "true"
