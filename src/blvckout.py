# Upload Assistant © 2026 Audionut & wastaken7 — Licensed under UAPL v1.0
"""Read-only BLVCKOUT movie catalogue lookups for XXX releases.

BLVCKOUT needs a read API key. The key is sent only to the fixed API origin,
redirects are not followed, and cached results never contain it.
"""

from __future__ import annotations

import re
from typing import Any, cast

import httpx

from src.console import logger
from src.metadata_cache import cache_for, is_cache_miss
from src.xxx_match import RECORD_VERSION, XxxRelease, content_tags, first_image, plain_text, safe_https_url, unique_names

API = "https://blvckout.foo/api/v1"
PROVIDER = "blvckout"
LABEL = "BLVCKOUT"
_ID = re.compile(r"[A-Za-z0-9-]{1,80}")


def parse_reference(value: str) -> str | None:
    """Read ``--blvckout`` as a release ID, also from a ``/releases/ID`` link."""
    text = str(value or "").strip()
    match = re.search(r"/releases/([A-Za-z0-9-]+)", text)
    identity = match.group(1) if match else text
    return identity if _ID.fullmatch(identity) else None


def _names(values: Any) -> list[str]:
    items = cast(list[Any], values) if isinstance(values, list) else []
    return unique_names([cast(dict[str, Any], item).get("name") if isinstance(item, dict) else item for item in items if isinstance(item, (str, dict))])


def _year(value: Any) -> int | None:
    match = re.fullmatch(r"(19|20)\d\d", str(value or "").strip())
    return int(match.group(0)) if match else None


def normalize(row: dict[str, Any]) -> XxxRelease | None:
    identity = str(row.get("id") or "")
    if not _ID.fullmatch(identity):
        return None
    date = str(row.get("release_date") or "")[:10]
    date = date if re.fullmatch(r"(19|20)\d\d-\d\d-\d\d", date) else ""
    try:
        runtime = int(row.get("runtime_minutes") or 0)
    except TypeError, ValueError:
        runtime = 0
    return XxxRelease(
        provider=PROVIDER,
        kind="movies",
        id=identity,
        title=" ".join(str(row.get("title") or "").split())[:300],
        date=date,
        year=_year(row.get("production_year")) or _year(row.get("year")) or (int(date[:4]) if date else None),
        studio=" ".join(str(row.get("studio") or "").split())[:120],
        performers=_names(row.get("performers")),
        tags=content_tags(_names(row.get("genres"))),
        description=plain_text(row.get("description") or row.get("notes")),
        poster_url=first_image(row.get("front_cover")),
        url=safe_https_url(row.get("source_url") or row.get("url")),
        duration_minutes=runtime if 1 <= runtime <= 2000 else None,
    )


class BlvckoutClient:
    def __init__(self, api_key: str, *, base_dir: str = "", user_agent: str = "Upload-Assistant") -> None:
        self.api_key = api_key.strip()
        self.base_dir = base_dir
        self.user_agent = user_agent
        self.rejected = False

    @property
    def enabled(self) -> bool:
        return bool(self.api_key) and not self.rejected

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """Return the decoded response, ``{}`` for not found, or None when the request failed."""
        if not self.enabled:
            return None
        headers = {"Authorization": f"Bearer {self.api_key}", "Accept": "application/json", "User-Agent": self.user_agent}
        try:
            async with httpx.AsyncClient(timeout=20.0, follow_redirects=False, trust_env=False) as client:
                response = await client.get(f"{API}{path}", params=params, headers=headers)
        except httpx.HTTPError as exc:
            logger.warning(f"[yellow]{LABEL}: request failed: {type(exc).__name__}[/yellow]")
            return None
        if response.status_code in (401, 403):
            self.rejected = True
            logger.warning(f"[yellow]{LABEL} rejected the API key. Check its expiry, its read permission and DEFAULT.blvckout_api_key.[/yellow]")
            return None
        if response.status_code == 404:
            return {}
        if response.status_code == 429:
            logger.warning(f"[yellow]{LABEL}: rate limit reached; skipping the lookup.[/yellow]")
            return None
        if response.status_code != 200:
            logger.warning(f"[yellow]{LABEL} returned HTTP {response.status_code}.[/yellow]")
            return None
        try:
            return response.json()
        except ValueError:
            logger.warning(f"[yellow]{LABEL} returned an unexpected response.[/yellow]")
            return None

    async def search(self, query: str) -> list[XxxRelease]:
        query = " ".join(query.split())[:250]
        if len(query) < 2:
            return []
        cache = cache_for(self.base_dir)
        key = query.casefold()
        cached = await cache.get(PROVIDER, "search", f"{RECORD_VERSION}:{key}")
        if not is_cache_miss(cached) and isinstance(cached, list):
            return [release for release in (XxxRelease.from_dict(item) for item in cast(list[Any], cached)) if release]
        data = await self._get("/releases", {"q": query, "limit": 12})
        if data is None:
            return []
        items = cast(dict[str, Any], data).get("items") if isinstance(data, dict) else None
        rows = cast(list[Any], items) if isinstance(items, list) else []
        releases = [release for release in (normalize(cast(dict[str, Any], row)) for row in rows[:12] if isinstance(row, dict)) if release]
        await cache.set(PROVIDER, "search", f"{RECORD_VERSION}:{key}", [release.to_dict() for release in releases], negative=not releases)
        return releases

    async def detail(self, identity: str) -> XxxRelease | None:
        if not _ID.fullmatch(identity):
            return None
        cache = cache_for(self.base_dir)
        cached = await cache.get(PROVIDER, "release", f"{RECORD_VERSION}:{identity}")
        if not is_cache_miss(cached):
            return XxxRelease.from_dict(cached)
        data = await self._get(f"/releases/{identity}")
        if data is None:
            return None
        release = normalize(cast(dict[str, Any], data)) if isinstance(data, dict) else None
        await cache.set(PROVIDER, "release", f"{RECORD_VERSION}:{identity}", release.to_dict() if release else None, negative=release is None)
        return release
