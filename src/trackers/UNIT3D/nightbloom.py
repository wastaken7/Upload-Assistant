# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import re
from pathlib import Path
from typing import Any

from src.meta import Meta
from src.trackers.common import Common
from src.trackers.UNIT3D import UNIT3D

# The fields of the site's upload form.
_UPLOAD_FIELDS = frozenset(
    {
        "name",
        "category_id",
        "type_id",
        "resolution_id",
        "tmdb",
        "imdb",
        "tvdb",
        "mal",
        "igdb",
        "season_number",
        "episode_number",
        "distributor_id",
        "region_id",
        "description",
        "mediainfo",
        "bdinfo",
        "keywords",
        "anonymous",
        "personal_release",
    }
)

# Dots that stay in a name: audio channels (5.1) and H.264/H.265.
_KEPT_DOT = re.compile(r"(?<!\d)\d\.\d(?!\d)|(?<![A-Za-z0-9])H\.26[45](?!\d)", re.IGNORECASE)


def _spaced(name: str) -> str:
    kept = {match.start() + match.group().index(".") for match in _KEPT_DOT.finditer(name)}
    spaced = "".join(" " if char == "." and index not in kept else char for index, char in enumerate(name))
    return " ".join(spaced.split())


class Nightbloom(UNIT3D):
    """Nightbloom (NIG) is a custom tracker with a UNIT3D-compatible API."""

    tracker = "NIGHTBLOOM"
    display_name = "Nightbloom"
    base_url = "https://nightbloom.cx"
    banned_groups: tuple[str, ...] = ()
    id_url = f"{base_url}/api/torrents/"
    upload_url = f"{base_url}/api/torrents/upload"
    requests_url = f"{base_url}/api/requests/filter"
    search_url = f"{base_url}/api/torrents/filter"
    torrent_url = f"{base_url}/torrents/"
    supported_categories = ("MOVIE", "TV")
    tracker_urls = ("nightbloom.cx",)

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config, tracker_name=self.tracker)
        self.common = Common(config)

    async def get_category_id(self, meta: Meta, category: str = "", reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        category_id = {
            "MOVIE": "1",
            "TV": "2",
            "ANIME": "6",
        }
        if mapping_only:
            return category_id
        if reverse:
            return {v: k for k, v in category_id.items()}
        resolved = category or meta.category or ""
        if meta.anime and resolved in ("MOVIE", "TV"):
            resolved = "ANIME"
        return {"category_id": category_id.get(resolved, "0")}

    async def get_name(self, meta: Meta) -> dict[str, str]:
        # Releases keep the group's own name, with spaces for dots.
        original = (meta.scene_name or meta.basename_no_ext or "").strip()
        if not meta.scene_name and meta.isdir and not meta.tv_pack and meta.episode and len(meta.filelist) == 1:
            original = Path(meta.filelist[0]).stem.strip()
        tag = (meta.tag or "").strip()
        if original and tag and original.casefold().endswith(tag.casefold()):
            return {"name": _spaced(original)}
        return await super().get_name(meta)

    async def get_data(self, meta: Meta, preview: bool = False) -> dict[str, str]:
        data = await super().get_data(meta, preview=preview)
        return {key: value for key, value in data.items() if key in _UPLOAD_FIELDS}
