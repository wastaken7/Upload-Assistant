"""Release-name transforms owned by UNIT3D trackers."""

import re

from src.release_name import NameContext


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
            if context.values.get("type") == "WEBDL" and ("hybrid" in str(getattr(meta, "edition", "")).lower() or getattr(meta, "webdv", False)):
                name = name.replace("Hybrid ", "", 1)
            if getattr(meta, "webdv", False):
                name = name.replace("HYBRID ", "", 1)
        if add_dv_profile and getattr(meta, "tracker_status", {}).get(context.values.get("tracker", ""), {}).get("other", False):
            resolution = context.values.get("resolution", "")
            name = name.replace(resolution, f"{resolution} DVP5/DVP8", 1)
        return name

    return transform


def append_context_value(field_name: str):
    def transform(name: str, context: NameContext) -> str:
        return name + context.values.get(field_name, "")

    return transform
