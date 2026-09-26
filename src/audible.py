# Upload Assistant © 2026 Audionut & wastaken7 — Licensed under UAPL v1.0
from __future__ import annotations

import contextlib
import html
import json
import re
from typing import Any
from urllib.parse import urlsplit

import httpx
from bs4 import BeautifulSoup

from src.console import logger
from src.metadata_cache import cache_for, is_cache_miss

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


def build_audible_author_url(asin: str, domain: str) -> str:
    """Build an Audible author URL on the selected marketplace."""
    normalized_asin = str(asin or "").strip().upper()
    if not _ASIN_RE.fullmatch(normalized_asin):
        raise ValueError("Audible author ASIN must contain 10 letters or digits")
    return f"https://www.{normalize_audible_domain(domain)}/author/{normalized_asin}"


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


def _clean_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    value = re.sub(r"\\u([0-9a-fA-F]{4})", lambda match: chr(int(match.group(1), 16)), value)
    return html.unescape(value).strip()


def _names(value: Any) -> str:
    if isinstance(value, dict):
        value = [value]
    if not isinstance(value, list):
        return ""
    return ", ".join(name for item in value if isinstance(item, dict) if (name := _clean_text(item.get("name"))))


def _authors(value: Any) -> list[dict[str, str]]:
    if isinstance(value, dict):
        value = [value]
    if not isinstance(value, list):
        return []
    authors = []
    for item in value:
        if not isinstance(item, dict) or not (name := _clean_text(item.get("name"))):
            continue
        asin = str(item.get("asin") or "").strip().upper()
        authors.append({"name": name, "asin": asin if _ASIN_RE.fullmatch(asin) else ""})
    return authors


def _parse_product(product: Any, asin: str) -> dict[str, Any] | None:
    if not isinstance(product, dict) or str(product.get("asin", "")).upper() != asin or not _clean_text(product.get("title")):
        return None
    result: dict[str, Any] = {
        "title": _clean_text(product.get("title")),
        "author": _names(product.get("authors")),
        "audible_authors": _authors(product.get("authors")),
        "narrator": _names(product.get("narrators")),
        "publisher": _clean_text(product.get("publisher_name")),
        "overview": _clean_text(product.get("publisher_summary") or product.get("merchandising_description") or product.get("merchandising_summary")),
        "isbn": _clean_text(product.get("isbn")),
        "language": _clean_text(product.get("language")),
    }
    date = product.get("release_date") or product.get("publication_datetime")
    if isinstance(date, str) and re.match(r"^\d{4}", date):
        result["year"] = int(date[:4])
    images = product.get("product_images")
    if isinstance(images, dict):
        available_images = ((int(size), url) for size, url in images.items() if str(size).isdigit() and isinstance(url, str) and url)
        result["artwork_url"] = max(available_images, default=(0, ""))[1]
    series = product.get("series")
    if isinstance(series, list) and series:
        first = series[0]
        if isinstance(first, dict):
            result["book_series"] = _clean_text(first.get("title") or first.get("name"))
            sequence = first.get("sequence")
            if isinstance(sequence, (str, int, float)) and not isinstance(sequence, bool):
                result["book_series_index"] = _clean_text(str(sequence))
    format_type = _clean_text(product.get("format_type")).lower()
    if format_type in ("abridged", "unabridged"):
        result["edition"] = format_type.capitalize()
    minutes = product.get("runtime_length_min")
    if isinstance(minutes, int) and minutes > 0:
        result["runtime_minutes"] = minutes
    rating = product.get("rating")
    distribution = rating.get("overall_distribution", {}) if isinstance(rating, dict) else {}
    if isinstance(distribution, dict):
        count = distribution.get("num_ratings")
        average = distribution.get("average_rating")
        if isinstance(count, int) and count > 0 and isinstance(average, (int, float)) and 0 < average <= 5:
            result["rating_count"] = count
            result["rating_average"] = round(float(average), 1)
    return {key: value for key, value in result.items() if value not in (None, "")}


def _parse_page(markup: str, asin: str) -> dict[str, Any] | None:
    soup = BeautifulSoup(markup, "html.parser")
    structured_items: list[dict[str, Any]] = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or script.get_text())
        except TypeError, ValueError:
            continue
        structured_items.extend(item for item in (data if isinstance(data, list) else [data]) if isinstance(item, dict))
    if not any(item.get("@type") == "Product" and str(item.get("productID", "")).upper() == asin for item in structured_items):
        return None
    for item in structured_items:
        if item.get("@type") != "Audiobook":
            continue
        rating = item.get("aggregateRating", {})
        product = {
            "asin": asin,
            "title": item.get("name"),
            "authors": item.get("author"),
            "narrators": item.get("readBy"),
            "publisher_name": item.get("publisher"),
            "publisher_summary": item.get("description"),
            "release_date": item.get("datePublished"),
            "language": item.get("inLanguage"),
            "product_images": {"500": item.get("image")},
        }
        duration = item.get("duration")
        if isinstance(duration, str) and (match := re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?", duration)):
            product["runtime_length_min"] = int(match.group(1) or 0) * 60 + int(match.group(2) or 0)
        if isinstance(rating, dict):
            with contextlib.suppress(KeyError, TypeError, ValueError):
                product["rating"] = {"overall_distribution": {"average_rating": float(rating["ratingValue"]), "num_ratings": int(rating["ratingCount"])}}
        return _parse_product(product, asin)
    return None


async def fetch_audible_metadata(asin: str, domain: str, base_dir: str) -> dict[str, Any] | None:
    """Fetch public catalog metadata for one ASIN and marketplace, without account credentials."""
    asin = str(asin or "").strip().upper()
    if not _ASIN_RE.fullmatch(asin):
        return None
    try:
        domain = normalize_audible_domain(domain)
    except ValueError:
        return None
    cache = cache_for(base_dir)
    cache_key = f"v2:{domain}:{asin}"
    cached = await cache.get("audible", "product", cache_key)
    if not is_cache_miss(cached) and isinstance(cached, dict):
        return None if cached.get("not_found") else cached
    params = {
        "response_groups": "contributors,media,product_attrs,product_desc,product_details,product_extended_attrs,rating,series",
        "image_sizes": "1215,900,500",
    }
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        api_status = None
        page_status = None
        try:
            response = await client.get(f"https://api.{domain}/1.0/catalog/products/{asin}", params=params)
            api_status = response.status_code
            if response.status_code == 200:
                payload = response.json()
                result = _parse_product(payload.get("product"), asin) if isinstance(payload, dict) else None
                if result:
                    await cache.set("audible", "product", cache_key, result)
                    return result
        except (httpx.HTTPError, ValueError) as error:
            logger.debug(f"[yellow]Audible catalog lookup failed for {asin}: {error}[/yellow]")
        try:
            page = await client.get(build_audible_url(asin, domain))
            page_status = page.status_code
            if page.status_code == 200:
                result = _parse_page(page.text, asin)
                if result:
                    await cache.set("audible", "product", cache_key, result)
                    return result
        except httpx.HTTPError as error:
            logger.debug(f"[yellow]Audible page lookup failed for {asin}: {error}[/yellow]")
        if api_status == page_status == 404:
            await cache.set("audible", "product", cache_key, {"not_found": True}, negative=True)
    return None
