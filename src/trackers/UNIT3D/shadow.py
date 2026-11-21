# Upload Assistant © 2026 Audionut & wastaken7 — Licensed under UAPL v1.0
import re
from pathlib import Path
from typing import Any, ClassVar

from src import payload_preview, unit3d_catalogs
from src.meta import Meta
from src.trackers.UNIT3D import UNIT3D, ParamsList
from src.xxx_match import is_pack_name


_ROMANIAN_LANGUAGE = r"(?:ro|ron|rum|romanian|română|romana)(?:[-_]ro)?"
_ROMANIAN_SUBTITLE_LABEL = re.compile(rf"{_ROMANIAN_LANGUAGE}(?:$|[\s(])", re.IGNORECASE)
_ROMANIAN_SUBTITLE_FILENAME = re.compile(rf"(?:^|[._ -]){_ROMANIAN_LANGUAGE}(?:[._ -](?:forced|sdh|cc))*$", re.IGNORECASE)


class Shadow(UNIT3D):
    tracker = "SHADOW"
    display_name = "Shadow"
    base_url = "https://shadow.vip3ra.org"
    id_url = f"{base_url}/api/torrents/"
    search_url = f"{base_url}/api/torrents/filter"
    upload_url = f"{base_url}/api/torrents/upload"
    torrent_url = f"{base_url}/torrents/"
    tracker_urls = ("shadow.vip3ra.org",)
    supported_categories = ("MOVIE", "TV", "BOOK", "GAME", "MUSIC", "XXX")

    category_choices: ClassVar[dict[str, tuple[str, ...]]] = {
        "MOVIE": ("2", "12", "13", "14", "15", "16", "22", "28", "29"),
        "TV": ("11", "17", "22"),
        "BOOK": ("23",),
        "GAME": ("19", "20"),
        "MUSIC": ("26", "27", "31"),
        "XXX": ("21", "33"),
    }
    video_type_ids: ClassVar[dict[str, str]] = {"DISC": "1", "REMUX": "2", "ENCODE": "3", "WEBDL": "4", "WEBRIP": "5", "HDTV": "6", "DVDRIP": "50"}
    book_type_ids: ClassVar[dict[str, str]] = {"PDF": "29", "EPUB": "30", "MOBI": "31", "CBZ": "32", "CBR": "32"}
    music_type_ids: ClassVar[dict[str, str]] = {
        "album": "7",
        "single": "8",
        "ep": "9",
        "live album": "10",
        "concert recording": "10",
        "compilation": "11",
        "anthology": "11",
        "flac": "12",
        "mp3": "13",
    }
    type_choices: ClassVar[dict[str, range]] = {
        "BOOK": range(29, 35),
        "GAME": range(15, 23),
        "MUSIC": range(7, 15),
        "XXX": range(42, 48),
    }
    video_type_choices = (*range(1, 7), *range(48, 55))

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config, tracker_name=self.tracker)

    @staticmethod
    def _console_type(meta: Meta) -> str:
        platform = meta.platform.strip().upper()
        if platform.startswith(("PS", "PLAYSTATION")):
            return "16"
        if platform.startswith(("XBOX", "X360", "XONE", "XSX")):
            return "17"
        if platform.startswith(("NINTENDO", "SWITCH", "WII", "3DS", "NDS", "NES", "SNES")):
            return "18"
        return "22" if meta.console_game else ""

    @staticmethod
    def _music_release_type(meta: Meta) -> str:
        if meta.music_release_type:
            return meta.music_release_type.strip().casefold()
        value = meta.music_release.get("fields", {}).get("release_type", {}).get("value")
        return str(value or "").strip().casefold()

    @staticmethod
    def _video_quality(meta: Meta) -> str:
        resolution = meta.resolution.lower()
        if resolution in {"2160p", "4320p"}:
            return "4K"
        if meta.sd or resolution in {"576p", "576i", "540p", "480p", "480i"}:
            return "SD"
        return "HD"

    async def _has_romanian_subtitles(self, meta: Meta) -> bool:
        subtitles = meta.subtitle_languages
        labels = [subtitles] if isinstance(subtitles, str) else list(subtitles or [])
        if meta.hardcoded_subs_language:
            labels.append(meta.hardcoded_subs_language)
        if meta.is_disc == "BDMV":
            labels.extend(meta.bdinfo.get("subtitles") or [])
        elif meta.is_disc != "DVD":
            # Keep embedded tracks visible even if a hardcoded-subtitle correction replaced the prepared language list.
            tracks = (meta.mediainfo.get("media") or {}).get("track") or []
            labels.extend(track.get("Language") for track in tracks if isinstance(track, dict) and track.get("@type") == "Text")
        if any(_ROMANIAN_SUBTITLE_LABEL.match(part.strip()) for label in labels if isinstance(label, str) for part in re.split(r"[,;]", label)):
            return True

        return (
            any(_ROMANIAN_SUBTITLE_FILENAME.search(Path(path).stem) for path in meta.subtitle_files)
            and await self.common.get_torrent_filename(meta, self.tracker_config) == "BASE_SUBS"
        )

    async def get_category_id(self, meta: Meta, category: str = "", reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        if mapping_only or reverse:
            choices = unit3d_catalogs.classification_choices(self.tracker, "categories")
            return {label: value for value, label in choices} if mapping_only else dict(choices)

        category = category or meta.category
        if category in {"MOVIE", "TV"}:
            combined_genres = re.split(r"[,|/]", meta.combined_genres) if isinstance(meta.combined_genres, str) else meta.combined_genres
            genres = (*meta.genres, *combined_genres, *meta.keywords)
            if any(genre.strip().casefold() in {"documentary", "documentar"} for genre in genres):
                return {"category_id": "22"}
            romanian_subtitles = await self._has_romanian_subtitles(meta)
            if category == "MOVIE":
                standard_id, romanian_id = {"SD": ("12", "15"), "HD": ("13", "2"), "4K": ("14", "16")}[self._video_quality(meta)]
                return {"category_id": romanian_id if romanian_subtitles else standard_id}
            return {"category_id": "11" if romanian_subtitles else "17"}
        if category == "BOOK":
            return {"category_id": "23"}
        if category == "GAME":
            return {"category_id": "20" if self._console_type(meta) else "19"}
        if category == "MUSIC":
            return {"category_id": "27" if self._music_release_type(meta) == "album" else "26"}
        if category == "XXX":
            return {"category_id": "33" if is_pack_name(meta.basename_no_ext or meta.name) else "21"}
        return {"category_id": "0"}

    async def get_type_id(self, meta: Meta, type: str = "", reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        if mapping_only:
            return dict(self.video_type_ids)
        if reverse:
            return dict(unit3d_catalogs.classification_choices(self.tracker, "types"))
        if type:
            return {"type_id": self.video_type_ids.get(type.upper(), "0")}
        if meta.category == "BOOK":
            book_format = (meta.type or meta.container or "").strip().upper().lstrip(".")
            return {"type_id": "33" if meta.audiobook else self.book_type_ids.get(book_format, "34")}
        if meta.category == "GAME":
            if meta.game_subcategory in {"dlc", "update"}:
                return {"type_id": "21"}
            return {"type_id": self._console_type(meta) or "15"}
        if meta.category == "MUSIC":
            release_type = self._music_release_type(meta)
            return {"type_id": self.music_type_ids.get(release_type, self.music_type_ids.get(meta.format.strip().casefold(), "14"))}
        if meta.category == "XXX":
            return {"type_id": {"HD": "42", "SD": "43", "4K": "44"}[self._video_quality(meta)]}
        return {"type_id": self.video_type_ids.get((meta.type or "").upper(), "0")}

    async def get_resolution_id(self, meta: Meta, resolution: str = "", reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        choices = unit3d_catalogs.classification_choices(self.tracker, "resolutions")
        if mapping_only:
            return {label: value for value, label in choices}
        if reverse:
            return dict(choices)
        if not resolution and meta.category in {"BOOK", "GAME", "MUSIC"}:
            return {}
        resolution_ids = {label.casefold(): value for value, label in choices}
        return {"resolution_id": resolution_ids.get((resolution or meta.resolution).casefold(), resolution_ids["other"])}

    async def get_search_urls(self, meta: Meta, request_params: ParamsList) -> list[tuple[str, ParamsList, bool]]:
        categories = self.category_choices.get(meta.category, ())
        params = [(key, value) for key, value in request_params if key != "categories[]"]
        if meta.category in {"MOVIE", "TV"} and not meta.tmdb:
            title = meta.title or meta.name
            name = f"{title} {meta.season}".strip() if meta.category == "TV" else title
            params = [(key, value) for key, value in params if key not in {"name", "tmdbId"}]
            params.append(("name", name))
        params.extend(("categories[]", category_id) for category_id in categories)
        return await super().get_search_urls(meta, params)

    async def get_payload_specs(self, meta: Meta) -> dict[str, payload_preview.Spec]:
        specs = await super().get_payload_specs(meta)
        categories = self.category_choices.get(meta.category, ())
        category_choices = unit3d_catalogs.classification_choices(self.tracker, "categories")
        specs["category_id"] = payload_preview.choice("Category", [(value, label) for value, label in category_choices if value in categories])
        types = self.type_choices.get(meta.category, self.video_type_choices)
        type_choices = unit3d_catalogs.classification_choices(self.tracker, "types")
        specs["type_id"] = payload_preview.choice("Type", [(value, label) for value, label in type_choices if int(value) in types])
        return specs
