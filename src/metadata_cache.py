"""Persistent, provider-scoped cache for external metadata responses."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

_VERSION = 1
_LOCKS: dict[Path, asyncio.Lock] = {}
_MISSING = object()
_RUN_DISABLED = False


def _default_config() -> dict[str, Any]:
    try:
        from data.config import config

        return config if isinstance(config, dict) else {}
    except (ImportError, ModuleNotFoundError):
        return {}


def _project_root() -> Path:
    """Locate the configured Upload-Assistant checkout independently of cwd."""
    try:
        import data.config as config_module

        config_file = getattr(config_module, "__file__", None)
        if config_file:
            return Path(config_file).resolve().parent.parent
    except (ImportError, ModuleNotFoundError):
        pass
    return Path.cwd()


class MetadataCache:
    """JSON cache whose entries are safe to share between upload runs.

    Cache files intentionally contain no credentials.  A key is hashed so title
    searches do not become filesystem paths and every entry carries its own TTL.
    """

    def __init__(self, base_dir: str | Path, config: dict[str, Any] | None = None) -> None:
        config = config or _default_config()
        default = config.get("DEFAULT", config) if isinstance(config, dict) else {}
        default = default if isinstance(default, dict) else {}
        self.enabled = bool(default.get("metadata_cache_enabled", True))
        configured_dir = str(default.get("metadata_cache_dir", "data/cache/metadata")).strip()
        root = Path(base_dir) if base_dir else _project_root()
        cache_dir = Path(configured_dir or "data/cache/metadata")
        self.root = cache_dir if cache_dir.is_absolute() else root / cache_dir
        try:
            self.default_ttl = max(0, int(default.get("metadata_cache_default_ttl_hours", 168))) * 3600
        except (TypeError, ValueError):
            self.default_ttl = 168 * 3600
        try:
            self.negative_ttl = max(0, int(default.get("metadata_cache_negative_ttl_minutes", 60))) * 60
        except (TypeError, ValueError):
            self.negative_ttl = 60 * 60
        services = default.get("metadata_cache_services", {})
        self.services = services if isinstance(services, dict) else {}

    def _service_settings(self, provider: str) -> dict[str, Any]:
        value = self.services.get(provider, {})
        return value if isinstance(value, dict) else {}

    def is_enabled(self, provider: str) -> bool:
        return not _RUN_DISABLED and self.enabled and bool(self._service_settings(provider).get("enabled", True))

    def ttl(self, provider: str, resource: str, negative: bool = False) -> int:
        if negative:
            return self.negative_ttl
        settings = self._service_settings(provider)
        resource_ttl = settings.get(f"{resource}_ttl_hours", settings.get("ttl_hours", self.default_ttl // 3600))
        try:
            return max(0, int(resource_ttl)) * 3600
        except (TypeError, ValueError):
            return self.default_ttl

    def _path(self, provider: str, resource: str, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        safe_provider = "".join(char for char in provider.lower() if char.isalnum() or char in "_-")
        safe_resource = "".join(char for char in resource.lower() if char.isalnum() or char in "_-")
        return self.root / safe_provider / safe_resource / f"{digest}.json"

    async def get(self, provider: str, resource: str, key: str) -> Any:
        if not self.is_enabled(provider):
            return _MISSING
        path = self._path(provider, resource, key)
        try:
            raw = await asyncio.to_thread(path.read_text, encoding="utf-8")
            entry = json.loads(raw)
            if not isinstance(entry, dict) or entry.get("version") != _VERSION or float(entry.get("expires_at", 0)) < time.time():
                return _MISSING
            return entry.get("value", _MISSING)
        except (OSError, ValueError, TypeError):
            return _MISSING

    async def set(self, provider: str, resource: str, key: str, value: Any, *, negative: bool = False) -> None:
        if not self.is_enabled(provider):
            return
        ttl = self.ttl(provider, resource, negative)
        if ttl <= 0:
            return
        path = self._path(provider, resource, key)
        entry = {"version": _VERSION, "fetched_at": time.time(), "expires_at": time.time() + ttl, "value": value}
        try:
            serialized = json.dumps(entry, ensure_ascii=False, indent=2)
        except (TypeError, ValueError):
            return
        lock = _LOCKS.setdefault(path, asyncio.Lock())
        async with lock:
            try:
                await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
                temporary = path.with_suffix(f".tmp.{os.getpid()}")
                await asyncio.to_thread(temporary.write_text, serialized, encoding="utf-8")
                await asyncio.to_thread(temporary.replace, path)
            except OSError:
                return


def cache_for(base_dir: str | Path, config: dict[str, Any] | None = None) -> MetadataCache:
    return MetadataCache(base_dir, config)


def is_cache_miss(value: Any) -> bool:
    return value is _MISSING


def set_run_disabled(disabled: bool) -> None:
    """Apply the CLI cache override to all metadata providers in this process."""
    global _RUN_DISABLED
    _RUN_DISABLED = disabled


def tracker_metadata_cache_for(base_dir: str | Path, config: dict[str, Any]) -> MetadataCache:
    """Create the separately configured cache for explicit tracker torrent IDs."""
    default_value = config.get("DEFAULT", {}) if isinstance(config, dict) else {}
    default = default_value if isinstance(default_value, dict) else {}
    cache_config = {
        "DEFAULT": {
            "metadata_cache_enabled": default.get("tracker_metadata_cache_enabled", True),
            "metadata_cache_dir": default.get("tracker_metadata_cache_dir", "data/cache/tracker_metadata"),
            "metadata_cache_default_ttl_hours": default.get("tracker_metadata_cache_ttl_hours", 24),
            "metadata_cache_negative_ttl_minutes": default.get("tracker_metadata_cache_negative_ttl_minutes", 15),
        }
    }
    return MetadataCache(base_dir, cache_config)
