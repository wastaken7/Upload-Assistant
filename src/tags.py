# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import asyncio
import json
import os
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import guessit

from src.console import console
from src.meta import Meta

guessit_module: Any = cast(Any, guessit)
GuessitFn = Callable[[str, dict[str, Any] | None], dict[str, Any]]


def guessit_fn(value: str, options: dict[str, Any] | None = None) -> dict[str, Any]:
    return cast(dict[str, Any], guessit_module.guessit(value, options))


async def get_tag(video: str, meta: Meta, season_pack_check: bool = False) -> str:
    # Using regex from cross-seed (https://github.com/cross-seed/cross-seed/tree/master?tab=Apache-2.0-1-ov-file)
    release_group = None
    basename = os.path.basename(video)
    matched_anime = False

    # Try specialized regex patterns first
    if meta.anime:
        # Anime pattern: [Group] at the beginning
        basename_stripped = os.path.splitext(basename)[0]
        anime_match = re.search(r'^\s*\[(.+?)\]', basename_stripped)
        if anime_match:
            matched_anime = True
            release_group = anime_match.group(1)
            if meta.debug:
                console.print(f"Anime regex match: {release_group}")
    if (not meta.anime or not matched_anime) and meta.is_disc != "BDMV":
        # Non-anime pattern: group at the end after last hyphen, avoiding resolutions and numbers
        if os.path.isdir(video):
            # If video is a directory, use the directory name as basename
            basename_stripped = os.path.basename(os.path.normpath(video))
        elif (meta.tv_pack or meta.keep_folder or meta.category in ("BOOK", "GAME")) and not season_pack_check:
            basename_stripped = meta.uuid
        else:
            # If video is a file, use the filename without extension
            basename_no_path = os.path.basename(video)
            name, ext = os.path.splitext(basename_no_path)
            # If the extension contains a hyphen, it's not a real extension
            basename_stripped = basename_no_path if ext and '-' in ext else name
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
        name, ext = os.path.splitext(basename_stripped)
        if ext.lower() in known_extensions:
            basename_stripped = name

        non_anime_match = re.search(r'(?<=-)((?!\s*(?:WEB-DL|Blu-ray|H-264|H-265))(?:\W|\b)(?!(?:\d{3,4}[ip]))(?!\d+\b)(?:\W|\b)([\w .]+?))(?:\[.+\])?(?:\))?(?:\s\[.+\])?$', basename_stripped)
        if non_anime_match:
            release_group = non_anime_match.group(1).strip()
            if "Z0N3" in release_group:
                release_group = release_group.replace("Z0N3", "D-Z0N3")
            if not meta.scene and release_group and len(release_group) > 12:
                release_group = None
            if meta.debug:
                console.print(f"Non-anime regex match: {release_group}")

    # If regex patterns didn't work, fall back to guessit
    if not release_group and meta.is_disc:
        try:
            parsed = guessit_fn(video)
            release_group = cast(str | None, parsed.get('release_group'))
            if meta.debug:
                console.print(f"Guessit match: {release_group}")

        except Exception as e:
            console.print(f"Error while parsing group tag: {e}")
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
                    if key == 'type':
                        if meta[key] == "ENCODE":
                            meta[key] = value.get(key)
                        else:
                            pass
                    elif key == 'personalrelease':
                        meta[key] = _is_true(value.get(key, "False"))
                    elif key == 'template':
                        meta.description_template = value.get(key)
                    else:
                        meta[key] = value.get(key)
    except Exception as e:
        console.print(f"Error while loading tags.json: {e}")
        return meta
    return meta


def _is_true(value: Any) -> bool:
    return str(value).strip().lower() == "true"
