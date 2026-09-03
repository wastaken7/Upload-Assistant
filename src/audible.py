# Upload Assistant © 2026 Audionut & wastaken7 — Licensed under UAPL v1.0
from __future__ import annotations

import re
from urllib.parse import urlsplit

_ASIN_RE = re.compile(r"^[A-Z0-9]{10}$", re.IGNORECASE)
_AUDIBLE_HOST_RE = re.compile(r"^(?:www\.)?audible\.[a-z]{2,3}(?:\.[a-z]{2})?$", re.IGNORECASE)


def normalize_audible_domain(value: str) -> str:
    """Return a validated Audible marketplace hostname."""
    candidate = str(value or "").strip().lower().rstrip("/")
    if "://" in candidate:
        parsed = urlsplit(candidate)
        if parsed.scheme != "https" or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
            raise ValueError("Audible domain must be a hostname, such as audible.co.uk")
        candidate = parsed.hostname or ""
    candidate = candidate.removeprefix("www.")
    if not _AUDIBLE_HOST_RE.fullmatch(candidate):
        raise ValueError("invalid Audible marketplace domain")
    return candidate


def build_audible_url(asin: str, domain: str) -> str:
    """Build a canonical Audible product URL from an ASIN and marketplace."""
    normalized_asin = str(asin or "").strip().upper()
    if not _ASIN_RE.fullmatch(normalized_asin):
        raise ValueError("Audible ASIN must contain 10 letters or digits")
    return f"https://www.{normalize_audible_domain(domain)}/pd/{normalized_asin}"


def normalize_audible_url(value: str) -> str:
    """Validate an Audible product URL and reduce it to its canonical form."""
    parsed = urlsplit(str(value or "").strip())
    if parsed.scheme.lower() != "https" or parsed.username or parsed.password or parsed.port:
        raise ValueError("Audible URL must be an HTTPS product URL")
    domain = normalize_audible_domain(parsed.hostname or "")
    asin = next((part for part in reversed(parsed.path.split("/")) if _ASIN_RE.fullmatch(part)), "")
    if not asin:
        raise ValueError("Audible URL must contain a 10-character ASIN")
    return build_audible_url(asin, domain)


def resolve_audible_url(asin: str, *, explicit_url: str = "", domain: str = "") -> str:
    """Resolve the exact Audible URL that should be embedded for an ASIN."""
    normalized_asin = str(asin or "").strip().upper()
    if explicit_url:
        audible_url = normalize_audible_url(explicit_url)
        if audible_url.rsplit("/", 1)[-1] != normalized_asin:
            raise ValueError("Audible URL ASIN does not match the book ASIN")
        return audible_url
    if domain:
        return build_audible_url(normalized_asin, domain)
    return ""
