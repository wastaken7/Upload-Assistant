import hashlib
import re
from pathlib import Path
from typing import Any, cast

import httpx
from PIL import Image

from src.console import logger
from src.meta import Meta
from src.trackers.common import Common
from src.trackers.UNIT3D import UNIT3D

type OptionCatalog = dict[str, dict[str, str]]


class Unwalled(UNIT3D):
    tracker = "UNWALLED"
    display_name = "Unwalled"
    base_url = "https://unwalled.cc"
    source_flag = "Unwalled"
    id_url = f"{base_url}/api/torrents/"
    upload_url = f"{base_url}/api/torrents/upload"
    search_url = f"{base_url}/api/torrents/filter"
    torrent_url = f"{base_url}/torrents/"
    supported_categories = ("PODCAST",)
    tracker_urls = ("https://unwalled.cc",)
    banned_groups: tuple[str, ...] = ()

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config, tracker_name=self.tracker)
        self.common = Common(config)
        self.option_catalog: OptionCatalog = {"categories": {}, "types": {}}

    @staticmethod
    def _normalize_option(value: str) -> str:
        return " ".join(value.casefold().split())

    @classmethod
    def catalog_from_response(cls, payload: dict[str, Any]) -> OptionCatalog:
        catalog: OptionCatalog = {"categories": {}, "types": {}}
        raw_entries = payload.get("data", [])
        if not isinstance(raw_entries, list):
            return catalog
        entries = cast(list[object], raw_entries)
        for raw_entry in entries:
            if not isinstance(raw_entry, dict):
                continue
            entry = cast(dict[str, object], raw_entry)
            raw_attributes = entry.get("attributes", {})
            if not isinstance(raw_attributes, dict):
                continue
            attributes = cast(dict[str, object], raw_attributes)
            for plural, name_key, id_key in (("categories", "category", "category_id"), ("types", "type", "type_id")):
                name = attributes.get(name_key)
                option_id = attributes.get(id_key)
                if isinstance(name, str) and name.strip() and str(option_id or "").isdigit():
                    catalog[plural][cls._normalize_option(name)] = str(option_id)
        return catalog

    async def discover_options(self) -> OptionCatalog:
        if any(self.option_catalog.values()):
            return self.option_catalog
        headers = {"authorization": f"Bearer {self.api_key}", "accept": "application/json"}
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                response = await client.get(self.search_url, headers=headers, params={"name": "", "perPage": "100"})
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as error:
            logger.info(f"{self.tracker}: [yellow]Unable to discover category/type IDs: {error}[/yellow]")
            return self.option_catalog
        if isinstance(payload, dict):
            self.option_catalog = self.catalog_from_response(payload)
        return self.option_catalog

    async def _resolve_option(self, value: str, plural: str) -> str:
        requested = value.strip()
        if requested.isdigit() and int(requested) > 0:
            return requested
        if not requested:
            singular = plural.removesuffix("s")
            raise ValueError(f"Set --unwalled-{singular} or TRACKERS.UNWALLED.{singular}")
        catalog = await self.discover_options()
        option_id = catalog[plural].get(self._normalize_option(requested))
        if option_id:
            return option_id
        available = ", ".join(sorted(catalog[plural])) or "none discovered"
        raise ValueError(f"Unknown Unwalled {plural.removesuffix('s')} {requested!r}; available: {available}. A numeric ID is also accepted")

    async def get_category_id(self, meta: Meta, category: str = "", reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        catalog = await self.discover_options() if mapping_only or reverse else self.option_catalog
        if mapping_only:
            return catalog["categories"]
        if reverse:
            return {option_id: name for name, option_id in catalog["categories"].items()}
        requested = category or meta.unwalled_category or str(self.tracker_config.get("category", ""))
        return {"category_id": await self._resolve_option(requested, "categories")}

    async def get_type_id(self, meta: Meta, type: str = "", reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        catalog = await self.discover_options() if mapping_only or reverse else self.option_catalog
        if mapping_only:
            return catalog["types"]
        if reverse:
            return {option_id: name for name, option_id in catalog["types"].items()}
        requested = type or meta.unwalled_type or str(self.tracker_config.get("type", ""))
        return {"type_id": await self._resolve_option(requested, "types")}

    async def get_resolution_id(self, meta: Meta, resolution: str = "", reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        if meta.type == "AUDIO" and not mapping_only and not reverse and not resolution:
            return {}
        return await super().get_resolution_id(meta, resolution, reverse, mapping_only)

    async def get_name(self, meta: Meta) -> dict[str, str]:
        name = re.sub(r"\s+", " ", (meta.podcast_title or meta.name).replace("&", "and")).strip()
        return {"name": name}

    @staticmethod
    def _valid_filename(name: str) -> bool:
        if len(name.encode("utf-8")) > 255 or not name or set(name) == {"."}:
            return False
        if re.search(r"[\\/?<>:*|\x00-\x1f]", name):
            return False
        if name.startswith(".pad") or name.startswith("____padding"):
            return False
        stem = name.split(".", 1)[0].upper()
        reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{number}" for number in range(1, 10)), *(f"LPT{number}" for number in range(1, 10))}
        return stem not in reserved

    @staticmethod
    def _image_details(path_value: str) -> tuple[Path, str, tuple[int, int]] | None:
        path = Path(path_value)
        try:
            with Image.open(path) as image:
                image.load()
                return path, str(image.format or ""), image.size
        except OSError, ValueError:
            return None

    def _valid_artwork(self, meta: Meta) -> bool:
        cover = self._image_details(meta.artwork_path)
        banner = self._image_details(str(meta.artwork_banner_path or ""))
        if cover is None or cover[1] != "JPEG" or cover[2][0] != cover[2][1] or cover[2][0] < 400:
            logger.info(f"{self.tracker}: [bold red]Cover must be a square JPEG of at least 400x400.[/bold red]")
            return False
        banner_ratio = banner[2][0] / banner[2][1] if banner and banner[2][1] else 0
        if banner is None or banner[1] != "JPEG" or banner[2][0] < 960 or banner[2][1] < 540 or abs(banner_ratio - (16 / 9)) > 0.03:
            logger.info(f"{self.tracker}: [bold red]Banner must be a 16:9 JPEG of at least 960x540.[/bold red]")
            return False
        if cover[0].resolve() == banner[0].resolve() or hashlib.sha256(cover[0].read_bytes()).digest() == hashlib.sha256(banner[0].read_bytes()).digest():
            logger.info(f"{self.tracker}: [bold red]Cover and banner must be different images.[/bold red]")
            return False
        return True

    async def get_additional_checks(self, meta: Meta) -> bool:
        if meta.category != "PODCAST":
            return False
        if not meta.name and not meta.podcast_title:
            logger.info(f"{self.tracker}: [bold red]A podcast torrent title is required.[/bold red]")
            return False
        if not meta.filelist or any(not self._valid_filename(Path(str(file)).name) for file in meta.filelist):
            logger.info(f"{self.tracker}: [bold red]The torrent contains a filename rejected by Unwalled.[/bold red]")
            return False
        if not self._valid_artwork(meta):
            return False
        try:
            await self.get_category_id(meta)
            await self.get_type_id(meta)
        except ValueError as error:
            logger.info(f"{self.tracker}: [bold red]{error}[/bold red]")
            return False
        upload_size = sum(path.stat().st_size for path in (Path(meta.artwork_path), Path(str(meta.artwork_banner_path or ""))) if path.is_file())
        base_torrent = Path(meta.base_dir) / "tmp" / meta.uuid / "BASE.torrent"
        if base_torrent.is_file():
            upload_size += base_torrent.stat().st_size
        if upload_size >= 1024 * 1024:
            logger.info(f"{self.tracker}: [bold red]Torrent, cover and banner must total less than 1 MiB.[/bold red]")
            return False
        return True

    async def get_upload_torrent_filename(self, meta: Meta) -> str:
        await self.common.create_torrent_for_upload(meta, self.tracker, self.source_flag, announce_url=self.announce_url)
        return f"[{self.tracker}]"
