import re
from pathlib import Path
from typing import Any, cast

import httpx

from src.console import logger
from src.meta import Meta
from src.trackers.UNIT3D import UNIT3D
from src.trackers.UNIT3D.unwalled_validation import UnwalledValidationMixin

type OptionCatalog = dict[str, dict[str, str]]


class Unwalled(UnwalledValidationMixin, UNIT3D):
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
    download_url_hosts = ("unwalled.cc",)
    max_torrent_download_size = 1024 * 1024
    max_json_response_size = 2 * 1024 * 1024
    follow_upload_redirects = False
    follow_search_redirects = False
    expose_remote_error_details = False
    banned_groups: tuple[str, ...] = ()

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config, tracker_name=self.tracker)
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
        max_size = self.max_json_response_size or 2 * 1024 * 1024
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=self.follow_search_redirects) as client:
                for page in range(1, 101):
                    async with client.stream("GET", self.search_url, headers=headers, params={"name": "", "perPage": "100", "page": str(page)}) as response:
                        response.raise_for_status()
                        bounded_response = await self._bounded_response(response, max_size)
                    raw_payload = bounded_response.json()
                    if not isinstance(raw_payload, dict):
                        break
                    payload = cast(dict[str, Any], raw_payload)
                    discovered = self.catalog_from_response(payload)
                    self.option_catalog["categories"].update(discovered["categories"])
                    self.option_catalog["types"].update(discovered["types"])
                    entries = payload.get("data")
                    if not isinstance(entries, list) or len(entries) < 100:
                        break
        except (httpx.HTTPError, ValueError) as error:
            logger.info(f"{self.tracker}: [yellow]Unable to discover category/type IDs: {error}[/yellow]")
            return self.option_catalog
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
        if meta.category == "PODCAST" and not mapping_only and not reverse and not resolution:
            return {}
        return await super().get_resolution_id(meta, resolution, reverse, mapping_only)

    def get_search_name(self, meta: Meta) -> str:
        return re.sub(r"\s+", " ", (meta.podcast_title or meta.name).replace("&", "and")).strip()

    async def get_name(self, meta: Meta) -> dict[str, str]:
        name = re.sub(r"\s+", " ", (meta.podcast_title or meta.name).replace("&", "and")).strip()
        return {"name": name}

    async def get_additional_checks(self, meta: Meta) -> bool:
        if meta.category != "PODCAST":
            return False
        if not meta.name and not meta.podcast_title:
            logger.info(f"{self.tracker}: [bold red]A podcast torrent title is required.[/bold red]")
            return False
        if not meta.debug and not self._valid_announce_url(self.announce_url):
            logger.info(f"{self.tracker}: [bold red]Configure a valid personal Unwalled announce URL.[/bold red]")
            return False
        if not meta.filelist or not self._valid_torrent_paths(meta):
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
        artwork_size = sum(path.stat().st_size for path in (Path(meta.artwork_path), Path(str(meta.artwork_banner_path or ""))) if path.is_file())
        if artwork_size >= 1024 * 1024:
            logger.info(f"{self.tracker}: [bold red]Cover and banner leave no room for a torrent under the 1 MiB limit.[/bold red]")
            return False
        base_torrent = Path(meta.base_dir) / "tmp" / meta.uuid / "BASE.torrent"
        if base_torrent.is_file() and not self._torrent_is_v1(base_torrent):
            logger.info(f"{self.tracker}: [bold red]Unwalled requires a V1 torrent.[/bold red]")
            return False
        return True

    async def get_upload_torrent_filename(self, meta: Meta) -> str:
        announce_url = "https://fake.tracker" if meta.debug else self.announce_url
        if not meta.debug and not self._valid_announce_url(announce_url):
            raise ValueError("A valid personal Unwalled announce URL is required")
        await self.common.create_torrent_for_upload(meta, self.tracker, self.source_flag, announce_url=announce_url)
        torrent_filename = f"[{self.tracker}]"
        torrent_path = Path(meta.base_dir) / "tmp" / meta.uuid / f"{torrent_filename}.torrent"
        if not self._valid_upload_bundle(meta, torrent_path):
            raise ValueError("Unwalled upload bundle validation failed")
        return torrent_filename
