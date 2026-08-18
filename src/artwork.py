"""Shared artwork validation and explicit-artwork preparation helpers."""

import asyncio
import ipaddress
import re
import socket
import warnings
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

import httpx
from PIL import Image

from src.console import logger
from src.meta import Meta
from src.temp_paths import artwork_dir

_SUPPORTED_COVER_FORMATS = {"GIF", "JPEG", "PNG", "WEBP"}
# File extensions worth opening at all when scanning a directory for artwork.
_COVER_SUFFIXES = {".gif", ".jpg", ".jpeg", ".png", ".webp"}
MAX_ARTWORK_BYTES = 10 * 1024 * 1024
MAX_ARTWORK_PIXELS = 40_000_000
_POSTER_KEYWORDS = ("poster", "cover", "front", "folder", "artwork", "capa")
_BANNER_KEYWORDS = ("banner", "backdrop", "landscape", "header")


def is_public_http_url(value: str | None) -> bool:
    """Return whether an HTTP(S) URL resolves exclusively to public IPs."""
    parsed = urlparse(str(value or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    try:
        addresses = {result[4][0] for result in socket.getaddrinfo(parsed.hostname, None, type=socket.SOCK_STREAM)}
        return bool(addresses) and all(ipaddress.ip_address(address).is_global for address in addresses)
    except OSError, ValueError:
        return False


def is_valid_image_bytes(image_bytes: bytes) -> bool:
    """Return whether bytes contain a decodable, non-empty supported image."""
    if not image_bytes:
        return False

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(image_bytes)) as image:
                if image.format not in _SUPPORTED_COVER_FORMATS or image.width <= 0 or image.height <= 0 or image.width * image.height > MAX_ARTWORK_PIXELS:
                    return False
                image.verify()
        return True
    except OSError, SyntaxError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning:
        return False


def is_valid_cover_image(path: str | Path | None) -> bool:
    """Return whether *path* is a decodable cover image accepted by uploads."""
    if not path:
        return False
    image_path = Path(path)
    try:
        if not image_path.is_file():
            return False
        # Check the size before reading: artwork above the limit is rejected
        # later anyway, and reading it first is pure waste. This stays here
        # rather than in the caller because it never rejects a usable cover.
        size = image_path.stat().st_size
        if size == 0 or size > MAX_ARTWORK_BYTES:
            return False
        return is_valid_image_bytes(image_path.read_bytes())
    except OSError:
        return False


def _find_local_artwork_sources(media_path: str) -> dict[str, Path]:
    """Find the best poster and banner image beside the media being uploaded."""
    if not media_path:
        return {}
    path = Path(media_path).expanduser()
    directory = path if path.is_dir() else path.parent
    if not directory.is_dir():
        return {}

    candidates: dict[str, list[tuple[tuple[int, int, str], Path]]] = {"poster": [], "banner": []}
    for candidate in directory.iterdir():
        # Filter by suffix before opening anything: this runs over every file
        # sitting next to the media, so without it a release stored beside other
        # media reads those files in full just to find out they are not covers.
        # The check belongs here rather than in is_valid_cover_image(), which
        # also validates paths the user supplied explicitly and must not reject
        # an image for having an unusual or missing extension.
        if candidate.suffix.casefold() not in _COVER_SUFFIXES:
            continue
        if not candidate.is_file() or not is_valid_cover_image(candidate):
            continue
        words = set(re.findall(r"[a-z0-9]+", candidate.stem.casefold()))
        is_banner = any(keyword in words for keyword in _BANNER_KEYWORDS)
        if is_banner:
            priority = min(_BANNER_KEYWORDS.index(keyword) for keyword in words if keyword in _BANNER_KEYWORDS)
            candidates["banner"].append(((priority, int(candidate.stem.casefold() not in _BANNER_KEYWORDS), candidate.name.casefold()), candidate))
            continue
        if any(keyword in words for keyword in _POSTER_KEYWORDS):
            priority = min(_POSTER_KEYWORDS.index(keyword) for keyword in words if keyword in _POSTER_KEYWORDS)
            candidates["poster"].append(((priority, int(candidate.stem.casefold() not in _POSTER_KEYWORDS), candidate.name.casefold()), candidate))

    return {kind: min(matches, key=lambda item: item[0])[1] for kind, matches in candidates.items() if matches}


async def _download_public_image(url: str) -> bytes | None:
    """Download an explicit image without following redirects to private hosts."""
    current_url = url
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=False, trust_env=False) as client:
            for _ in range(4):
                if not is_public_http_url(current_url):
                    logger.warning("[yellow]Artwork URL is not a public HTTP(S) URL; ignoring it.[/yellow]")
                    return None
                async with client.stream("GET", current_url) as response:
                    if response.is_redirect:
                        location = response.headers.get("Location")
                        if not location:
                            return None
                        current_url = str(response.url.join(location))
                        continue
                    content_length = response.headers.get("Content-Length")
                    if response.status_code != 200 or (content_length and (not content_length.isdigit() or int(content_length) > MAX_ARTWORK_BYTES)):
                        logger.warning("[yellow]Artwork URL did not return a supported image; ignoring it.[/yellow]")
                        return None
                    content = bytearray()
                    async for chunk in response.aiter_bytes():
                        content.extend(chunk)
                        if len(content) > MAX_ARTWORK_BYTES:
                            logger.warning("[yellow]Artwork download exceeds the 10 MiB limit; ignoring it.[/yellow]")
                            return None
                    if not is_valid_image_bytes(bytes(content)):
                        logger.warning("[yellow]Artwork URL did not return a supported image; ignoring it.[/yellow]")
                        return None
                    return bytes(content)
    except httpx.HTTPError as error:
        logger.warning(f"[yellow]Unable to download artwork: {error}[/yellow]")
    return None


def _write_png(source: Path | bytes, destination: Path) -> bool:
    """Validate and re-encode artwork into the canonical PNG artifact."""
    temporary = destination.with_suffix(".tmp")
    try:
        image_source = BytesIO(source) if isinstance(source, bytes) else source
        with Image.open(image_source) as image:
            image.load()
            if image.format not in _SUPPORTED_COVER_FORMATS or image.width <= 0 or image.height <= 0:
                return False
            if image.mode not in {"RGB", "RGBA"}:
                image = image.convert("RGBA" if "transparency" in image.info else "RGB")
            destination.parent.mkdir(parents=True, exist_ok=True)
            image.save(temporary, "PNG")
        temporary.replace(destination)
        return True
    except OSError, SyntaxError, ValueError:
        temporary.unlink(missing_ok=True)
        return False


async def prepare_artwork(meta: Meta) -> None:
    """Resolve every artwork source into the canonical per-release PNG files.

    Explicit arguments win over local files beside the media; those in turn win
    over category-specific extraction and remote metadata providers.
    """
    output_dir = artwork_dir(meta.base_dir, meta.uuid)
    local_sources = await asyncio.to_thread(_find_local_artwork_sources, str(meta.path or ""))
    for input_name, output_name, meta_name in (
        ("explicit_poster", "POSTER.png", "artwork_path"),
        ("explicit_banner", "POSTER_BANNER.png", "artwork_banner_path"),
    ):
        value = str(getattr(meta, input_name) or "").strip()
        kind = "poster" if input_name == "explicit_poster" else "banner"
        source_path = Path(value).expanduser() if value else local_sources.get(kind)
        is_discovered_local = not value and source_path is not None
        if source_path is None:
            current_path = Path(str(getattr(meta, meta_name) or ""))
            source_path = current_path if is_valid_cover_image(current_path) else None
        source: Path | bytes | None
        if source_path is not None and source_path.is_file():
            source = source_path
        elif value and urlparse(value).scheme in {"http", "https"}:
            source = await _download_public_image(value)
        elif kind == "poster" and is_public_http_url(meta.artwork_url):
            source = await _download_public_image(meta.artwork_url)
        elif value:
            logger.warning(f"[yellow]{input_name.replace('_', ' ')} must be an existing image file or public HTTP(S) URL; ignoring it.[/yellow]")
            continue
        else:
            continue

        destination = output_dir / output_name
        if source is None or not await asyncio.to_thread(_write_png, source, destination):
            logger.warning(f"[yellow]Could not prepare {input_name.replace('_', ' ')}; ignoring it.[/yellow]")
            continue

        setattr(meta, meta_name, str(destination))
        if input_name == "explicit_poster":
            if value:
                # An explicit URL remains useful to trackers; a file replaces
                # any provider URL that might point at different artwork.
                meta.artwork_url = value if isinstance(source, bytes) else ""
            elif is_discovered_local:
                meta.artwork_url = ""
