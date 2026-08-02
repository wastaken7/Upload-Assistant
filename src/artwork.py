"""Shared artwork validation helpers."""

import ipaddress
import socket
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image

_SUPPORTED_COVER_FORMATS = {"GIF", "JPEG", "PNG", "WEBP"}


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
        with Image.open(BytesIO(image_bytes)) as image:
            if image.format not in _SUPPORTED_COVER_FORMATS or image.width <= 0 or image.height <= 0:
                return False
            image.verify()
        return True
    except OSError, SyntaxError, ValueError:
        return False


def is_valid_cover_image(path: str | Path | None) -> bool:
    """Return whether *path* is a decodable cover image accepted by uploads."""
    if not path:
        return False
    image_path = Path(path)
    try:
        if not image_path.is_file() or image_path.stat().st_size == 0:
            return False
        return is_valid_image_bytes(image_path.read_bytes())
    except OSError:
        return False
