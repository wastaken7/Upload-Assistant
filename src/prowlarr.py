# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
from __future__ import annotations

import http.cookiejar
import re
from dataclasses import dataclass, field
from http.cookies import CookieError, SimpleCookie
from typing import Any, cast
from urllib.parse import urlsplit

import httpx


class ProwlarrError(RuntimeError):
    """A safe, user-facing Prowlarr connection or response error."""


@dataclass(frozen=True)
class ProwlarrCredential:
    api_key: str = ""
    cookie: str = ""
    base_url: str = ""


@dataclass(frozen=True)
class ProwlarrCredentialReport:
    credentials: dict[str, ProwlarrCredential] = field(default_factory=dict[str, ProwlarrCredential])
    enabled_indexers: int = 0
    matched_indexers: int = 0
    masked_credentials: int = 0
    unsupported_indexers: int = 0
    version: str = ""


_DEFINITION_ALIASES = {
    "1PTBAR": "1PTBA",
    "HDSPACECOOKIE": "HDSPACE",
    "HHD": "HOMIEHELPDESK",
    "UPLOADCX": "ULCX",
    "XINGYUNG": "XINGYUNGEPT",
}
_MASKED_VALUE = re.compile(r"\*+")


def _api_url(base_url: str, path: str) -> str:
    normalized = str(base_url or "").strip().rstrip("/")
    parsed = urlsplit(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.query or parsed.fragment:
        raise ProwlarrError("Prowlarr URL must be an HTTP or HTTPS base URL")
    return f"{normalized}{path}"


def _usable_secret(value: object) -> str:
    if not isinstance(value, str):
        return ""
    normalized = value.strip()
    if not normalized or _MASKED_VALUE.fullmatch(normalized) or "\r" in normalized or "\n" in normalized:
        return ""
    return normalized


def _usable_cookie(value: object, base_url: str) -> str:
    header = _usable_secret(value)
    parsed = urlsplit(base_url)
    if not header or parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return ""
    cookies = SimpleCookie()
    try:
        cookies.load(header)
    except CookieError:
        return ""
    return header if cookies else ""


def _definition_tracker(definition: object, supported_trackers: set[str]) -> str | None:
    if not isinstance(definition, str) or not definition.strip():
        return None
    normalized = re.sub(r"[^A-Za-z0-9]", "", re.sub(r"-api$", "", definition.strip(), flags=re.IGNORECASE)).upper()
    tracker = _DEFINITION_ALIASES.get(normalized, normalized)
    return tracker if tracker in supported_trackers else None


def resolve_prowlarr_credentials(indexers: object, supported_trackers: set[str]) -> ProwlarrCredentialReport:
    """Resolve supported API-key and cookie credentials from an indexer response."""
    if not isinstance(indexers, list):
        raise ProwlarrError("Prowlarr returned an invalid indexer response")

    supported = {str(name).strip().upper() for name in supported_trackers}
    credentials: dict[str, ProwlarrCredential] = {}
    enabled_count = 0
    matched_count = 0
    masked_count = 0
    unsupported_count = 0

    for indexer_value in cast(list[object], indexers):
        indexer = cast(dict[str, object], indexer_value) if isinstance(indexer_value, dict) else None
        if indexer is None or indexer.get("enable") is not True:
            continue
        enabled_count += 1
        fields_value = indexer.get("fields")
        if not isinstance(fields_value, list):
            unsupported_count += 1
            continue

        field_values: dict[str, object] = {}
        for field_value in cast(list[object], fields_value):
            if not isinstance(field_value, dict):
                continue
            field_item = cast(dict[str, object], field_value)
            name = field_item.get("name")
            if isinstance(name, str):
                field_values[name] = field_item.get("value")
        raw_api_key = field_values.get("apikey", field_values.get("apiKey"))
        raw_cookie = field_values.get("cookie")
        masked_count += sum(isinstance(value, str) and bool(_MASKED_VALUE.fullmatch(value.strip())) for value in (raw_api_key, raw_cookie))
        tracker = _definition_tracker(field_values.get("definitionFile"), supported)
        if tracker is None:
            unsupported_count += 1
            continue
        matched_count += 1

        base_url = str(field_values.get("baseUrl") or "").strip()
        api_key = _usable_secret(raw_api_key)
        cookie = _usable_cookie(raw_cookie, base_url)
        if not api_key and not cookie:
            continue

        # One Prowlarr definition should map to one UA tracker. If duplicates
        # exist, retain the first enabled credential deterministically.
        credentials.setdefault(tracker, ProwlarrCredential(api_key=api_key, cookie=cookie, base_url=base_url))

    return ProwlarrCredentialReport(
        credentials=credentials,
        enabled_indexers=enabled_count,
        matched_indexers=matched_count,
        masked_credentials=masked_count,
        unsupported_indexers=unsupported_count,
    )


def fetch_prowlarr_credentials(
    base_url: str,
    api_key: str,
    supported_trackers: set[str],
    *,
    include_status: bool = False,
) -> ProwlarrCredentialReport:
    """Fetch Prowlarr credentials without logging or persisting secret values."""
    key = _usable_secret(api_key)
    if not key:
        raise ProwlarrError("Prowlarr API key is required")

    try:
        with httpx.Client(headers={"X-Api-Key": key}, timeout=10.0) as client:
            response = client.get(_api_url(base_url, "/api/v1/indexer"))
            response.raise_for_status()
            report = resolve_prowlarr_credentials(response.json(), supported_trackers)
            version = ""
            if include_status:
                status_response = client.get(_api_url(base_url, "/api/v1/system/status"))
                status_response.raise_for_status()
                status_value: object = status_response.json()
                if isinstance(status_value, dict):
                    status = cast(dict[str, object], status_value)
                    version = str(status.get("version") or "").strip()
            return ProwlarrCredentialReport(
                credentials=report.credentials,
                enabled_indexers=report.enabled_indexers,
                matched_indexers=report.matched_indexers,
                masked_credentials=report.masked_credentials,
                unsupported_indexers=report.unsupported_indexers,
                version=version,
            )
    except ProwlarrError:
        raise
    except httpx.HTTPStatusError as error:
        status_code = error.response.status_code
        if status_code in {401, 403}:
            raise ProwlarrError("Prowlarr rejected the API key") from error
        raise ProwlarrError(f"Prowlarr returned HTTP {status_code}") from error
    except httpx.TimeoutException as error:
        raise ProwlarrError("Prowlarr connection timed out") from error
    except httpx.RequestError as error:
        raise ProwlarrError("Prowlarr could not be reached") from error
    except ValueError as error:
        raise ProwlarrError("Prowlarr returned invalid JSON") from error


def apply_prowlarr_credentials(config: dict[str, Any], report: ProwlarrCredentialReport) -> set[str]:
    """Apply missing credentials to a runtime config and return their sources."""
    trackers_value: object = config.setdefault("TRACKERS", {})
    if not isinstance(trackers_value, dict):
        return set()
    trackers = cast(dict[str, object], trackers_value)

    applied: set[str] = set()
    for tracker, credential in report.credentials.items():
        tracker_config_value = trackers.setdefault(tracker, {})
        if not isinstance(tracker_config_value, dict):
            continue
        tracker_config = cast(dict[str, object], tracker_config_value)

        used = False
        if credential.api_key and not str(tracker_config.get("api_key") or "").strip():
            tracker_config["api_key"] = credential.api_key
            used = True
        if credential.cookie:
            tracker_config["_prowlarr_cookie"] = {
                "header": credential.cookie,
                "base_url": credential.base_url,
            }
            used = True
        if used:
            tracker_config["_prowlarr_credential_source"] = True
            applied.add(tracker)
    return applied


def configured_prowlarr(config: dict[str, Any]) -> tuple[str, str] | None:
    default_value: object = config.get("DEFAULT", {})
    if not isinstance(default_value, dict):
        return None
    default = cast(dict[str, object], default_value)
    base_url = str(default.get("prowlarr_url") or "").strip()
    api_key = str(default.get("prowlarr_api_key") or "").strip()
    return (base_url, api_key) if base_url and api_key else None


def prowlarr_cookie_jar(tracker_config: dict[str, Any]) -> http.cookiejar.CookieJar | None:
    """Build a process-local cookie jar from a hydrated Prowlarr credential."""
    value_raw: object = tracker_config.get("_prowlarr_cookie")
    if not isinstance(value_raw, dict):
        return None
    value = cast(dict[str, object], value_raw)
    base_url = str(value.get("base_url") or "").strip()
    header = _usable_cookie(value.get("header"), base_url)
    parsed = urlsplit(base_url)
    if not header or parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None

    cookies = SimpleCookie()
    try:
        cookies.load(header)
    except CookieError:
        return None
    if not cookies:
        return None

    jar = http.cookiejar.CookieJar()
    for name, morsel in cookies.items():
        jar.set_cookie(
            http.cookiejar.Cookie(
                version=0,
                name=name,
                value=morsel.value,
                port=None,
                port_specified=False,
                domain=parsed.hostname,
                domain_specified=True,
                domain_initial_dot=False,
                path="/",
                path_specified=True,
                secure=parsed.scheme == "https",
                expires=None,
                discard=True,
                comment=None,
                comment_url=None,
                rest={"HttpOnly": ""},
                rfc2109=False,
            )
        )
    return jar
