# Upload Assistant © 2026 Audionut & wastaken7 — Licensed under UAPL v1.0
"""Read-only ThePornDB (TPDB) lookups for XXX releases.

Scenes are found by file hash (``hash``/``hashType``) or by a release name the
API parses itself (``parse``); movies by ``parse``. The API key is sent only to
the fixed API origin, redirects are not followed, and cached results never
contain it.
"""

from __future__ import annotations

import re
from typing import Any, cast

import httpx

from src.console import logger
from src.metadata_cache import cache_for, is_cache_miss
from src.xxx_match import RECORD_VERSION, XxxRelease, content_tags, first_image, plain_text, safe_https_url, unique_names

API = "https://api.theporndb.net"
PROVIDER = "tpdb"
LABEL = "ThePornDB"
KINDS = ("scenes", "movies", "jav")
_TYPE_KINDS = {"scene": "scenes", "movie": "movies", "jav": "jav"}
_ID = re.compile(r"[A-Za-z0-9-]{1,80}")


def parse_reference(value: str) -> tuple[str, str] | None:
    """Read ``--tpdb`` as ``(kind, id)``: ``scenes/ID``, ``movies/ID``, a TPDB link or a bare scene ID."""
    text = str(value or "").strip()
    match = re.search(r"theporndb\.net/(scenes|movies|jav)/([A-Za-z0-9-]+)", text, re.IGNORECASE)
    if match:
        return match.group(1).lower(), match.group(2)
    kind, separator, identity = text.partition("/")
    if separator:
        kind = kind.strip().lower()
        kind = _TYPE_KINDS.get(kind, kind)
        return (kind, identity.strip()) if kind in KINDS and _ID.fullmatch(identity.strip()) else None
    return ("scenes", text) if _ID.fullmatch(text) else None


def _names(values: Any) -> list[str]:
    names: list[str] = []
    for value in cast(list[Any], values) if isinstance(values, list) else []:
        if not isinstance(value, dict):
            continue
        item = cast(dict[str, Any], value)
        parent = item.get("parent")
        # A performer's parent is the canonical performer; the scene may credit an alias.
        name = cast(dict[str, Any], parent).get("name") if isinstance(parent, dict) else None
        names.append(str(name or item.get("name") or ""))
    return unique_names(names)


def normalize(row: dict[str, Any], kind: str) -> XxxRelease | None:
    """Turn one API record into an :class:`XxxRelease`, or None when it has no ID."""
    identity = str(row.get("_id") or row.get("id") or "")
    if not _ID.fullmatch(identity):
        return None
    kind = _TYPE_KINDS.get(str(row.get("type") or "").casefold(), kind)
    site = cast(dict[str, Any], row.get("site")) if isinstance(row.get("site"), dict) else {}
    studio = str(site.get("name") or "").strip()
    if kind == "movies":
        # Movie studios imported from store catalogues carry a "(...)" suffix.
        studio = re.sub(r"\s*\([^)]*\)$", "", studio).strip()
    network = ""
    platform = re.fullmatch(r"([^:]{2,30}):\s+(.+)", studio)
    if platform:
        # Creator sites are named "Platform: Creator"; the creator is the studio.
        network, studio = platform.group(1).strip(), platform.group(2).strip()
    for relation in ("network", "parent"):
        related = site.get(relation)
        name = str(cast(dict[str, Any], related).get("name") or "").strip() if isinstance(related, dict) else ""
        if name and name.casefold() != studio.casefold() and not network:
            network = name
            break
    date = str(row.get("date") or "")[:10]
    date = date if re.fullmatch(r"(19|20)\d\d-\d\d-\d\d", date) else ""
    try:
        seconds = int(float(row.get("duration") or 0))
    except TypeError, ValueError:
        seconds = 0
    tags = content_tags([cast(dict[str, Any], tag).get("name") for tag in cast(list[Any], row.get("tags") or []) if isinstance(tag, dict)])
    background = row.get("background")
    # A scene's or JAV title's "poster" is a cropped, watermarked thumbnail; its
    # background is the original image. A movie's posters are its front cover.
    if kind == "movies":
        poster = first_image(row.get("posters"), row.get("poster"), row.get("image"), background)
        banner = ""
    else:
        poster = first_image(background, row.get("image"), row.get("posters"), row.get("poster"))
        banner = first_image(cast(dict[str, Any], background).get("full") if isinstance(background, dict) else background)
    short_name = str(site.get("short_name") or "").strip()
    return XxxRelease(
        provider=PROVIDER,
        kind=kind,
        id=identity,
        title=" ".join(str(row.get("title") or "").split())[:300],
        date=date,
        year=int(date[:4]) if date else None,
        studio=studio[:120],
        network=network[:120],
        aliases=[short_name[:120]] if short_name else [],
        performers=_names(row.get("performers")),
        tags=tags,
        description=plain_text(row.get("description")),
        poster_url=poster,
        banner_url=banner if banner != poster else "",
        url=safe_https_url(row.get("url")),
        duration_minutes=round(seconds / 60) if seconds >= 60 else None,
        code=str(row.get("external_id") or "").upper()[:40] if kind == "jav" else "",
    )


class TpdbClient:
    def __init__(self, api_key: str, *, base_dir: str = "", user_agent: str = "Upload-Assistant") -> None:
        self.api_key = api_key.strip()
        self.base_dir = base_dir
        self.user_agent = user_agent
        self.rejected = False

    @property
    def enabled(self) -> bool:
        return bool(self.api_key) and not self.rejected

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """Return the response's ``data``, ``[]`` for not found, or None when the request failed."""
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
            logger.warning(f"[yellow]{LABEL} rejected the API key. Check DEFAULT.tpdb_api_key.[/yellow]")
            return None
        if response.status_code == 404:
            return []
        if response.status_code == 429:
            logger.warning(f"[yellow]{LABEL}: rate limit reached; skipping the lookup.[/yellow]")
            return None
        if response.status_code != 200:
            logger.warning(f"[yellow]{LABEL} returned HTTP {response.status_code}.[/yellow]")
            return None
        try:
            body = response.json()
        except ValueError:
            logger.warning(f"[yellow]{LABEL} returned an unexpected response.[/yellow]")
            return None
        return cast(dict[str, Any], body).get("data") if isinstance(body, dict) else None

    async def _cached_list(self, resource: str, key: str, path: str, params: dict[str, Any], kind: str) -> list[XxxRelease]:
        cache = cache_for(self.base_dir)
        cached = await cache.get(PROVIDER, resource, f"{RECORD_VERSION}:{key}")
        if not is_cache_miss(cached) and isinstance(cached, list):
            return [release for release in (XxxRelease.from_dict(item) for item in cast(list[Any], cached)) if release]
        data = await self._get(path, params)
        if data is None:
            return []
        rows = cast(list[Any], data) if isinstance(data, list) else []
        releases = [release for release in (normalize(cast(dict[str, Any], row), kind) for row in rows[:25] if isinstance(row, dict)) if release]
        await cache.set(PROVIDER, resource, f"{RECORD_VERSION}:{key}", [release.to_dict() for release in releases], negative=not releases)
        return releases

    async def search(self, kind: str, query: str) -> list[XxxRelease]:
        """Search scenes, movies or JAV with a release name or title that TPDB parses."""
        query = " ".join(query.split())[:250]
        if kind not in KINDS or len(query) < 2:
            return []
        return await self._cached_list(f"{kind}_search", query.casefold(), f"/{kind}", {"parse": query}, kind)

    async def search_words(self, query: str) -> list[XxxRelease]:
        """Search scenes by free words (performers, title) when the name cannot be parsed."""
        query = " ".join(query.split())[:120]
        if len(query) < 3:
            return []
        return await self._cached_list("scenes_words", query.casefold(), "/scenes", {"q": query}, "scenes")

    async def find_by_hash(self, file_hash: str, hash_type: str = "OSHASH") -> list[XxxRelease]:
        """Return the scenes whose submitted file hash equals ``file_hash``."""
        if not re.fullmatch(r"[0-9a-fA-F]{16,64}", file_hash):
            return []
        releases = await self._cached_list("hash", f"{hash_type}:{file_hash.lower()}", "/scenes", {"hash": file_hash.lower(), "hashType": hash_type}, "scenes")
        for release in releases:
            release.via_hash = True
        return releases

    async def detail(self, kind: str, identity: str) -> XxxRelease | None:
        """Return one scene or movie by its TPDB ID."""
        if kind not in KINDS or not _ID.fullmatch(identity):
            return None
        cache = cache_for(self.base_dir)
        cached = await cache.get(PROVIDER, kind, f"{RECORD_VERSION}:{identity}")
        if not is_cache_miss(cached):
            return XxxRelease.from_dict(cached)
        data = await self._get(f"/{kind}/{identity}")
        if data is None:
            return None
        release = normalize(cast(dict[str, Any], data), kind) if isinstance(data, dict) else None
        await cache.set(PROVIDER, kind, f"{RECORD_VERSION}:{identity}", release.to_dict() if release else None, negative=release is None)
        return release
