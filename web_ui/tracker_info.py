"""Tracker configuration, status probes and Prowlarr caches."""

import re
import threading
import time
import urllib.parse
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from web_ui import flask_compat as flask_compat_mod
from web_ui.context import APP_VERSION
from web_ui.flask_compat import _is_obj_sequence, _is_str_mapping

_TRACKER_STATUS_CACHE_SECONDS = 15 * 60
_TRACKER_STATUS_MAX_WORKERS = 8
_tracker_status_cache: dict[str, dict[str, Any]] = {}
_tracker_status_cache_lock = threading.Lock()
_tracker_status_check_lock = threading.Lock()
# Every tracker list request otherwise waits on a Prowlarr round trip.
_PROWLARR_REPORT_CACHE_SECONDS = 5 * 60
_prowlarr_report_cache: dict[tuple[str, str, frozenset[str]], tuple[float, Any]] = {}
_prowlarr_report_cache_lock = threading.Lock()
_prowlarr_report_cache_generation = 0


_TRACKER_CONFIGURATION_KEYS = frozenset(
    {
        "api_key",
        "torznab_api_key",
        "announce_url",
        "my_announce_url",
        "username",
        "password",
        "passkey",
        "cookie_file",
        "cookies",
        "ApiUser",
        "bhd_rss_key",
        "bioma_api_key",
        "image_host_api_key",
        "ptgen_api",
    }
)

_TRACKER_REQUIRED_SETUP_KEYS = (
    "ApiUser",
    "api_key",
    "torznab_api_key",
    "announce_url",
    "my_announce_url",
    "username",
    "password",
    "passkey",
)

_TRACKER_SETUP_PLACEHOLDER_PATTERN = re.compile(
    r"<[^>]+>|\b(?:your|custom|insert|replace|example)\b|\b(?:api[ _-]?user|username|password|passkey)\b",
    re.IGNORECASE,
)

_TRACKER_DEFAULT_OVERRIDE_KEYS = (
    "add_audio_spectrogram",
    "add_bluray_link",
    "add_dynamic_hdr_plot",
    "add_logo",
    "audio_spectrogram_header",
    "bluray_image_size",
    "charLimit",
    "custom_description_header",
    "custom_footer",
    "custom_header",
    "custom_signature",
    "disc_menu_header",
    "dynamic_hdr_plot_header",
    "episode_overview",
    "fileLimit",
    "inject_delay",
    "logo_size",
    "mediainfo_header",
    "multiScreens",
    "pack_thumb_size",
    "processLimit",
    "screens_per_row",
    "screenshot_header",
    "thumbnail_size",
    "tonemapped_header",
    "use_bluray_images",
    "user_description",
)


def _has_configured_tracker_value(tracker_config: Mapping[str, Any], example_tracker_config: Mapping[str, Any]) -> bool:
    """Return whether a tracker has a meaningful user-supplied setup value."""
    for key in _TRACKER_CONFIGURATION_KEYS:
        if key not in tracker_config:
            continue

        value = tracker_config[key]
        if isinstance(value, str):
            value = value.strip()
        example_value = example_tracker_config.get(key)
        if isinstance(example_value, str):
            example_value = example_value.strip()
        if value in (None, "", False) or value == example_value:
            continue
        return True

    return False


def _tracker_setup_value_is_complete(
    key: str,
    tracker_config: Mapping[str, Any],
    example_tracker_config: Mapping[str, Any],
) -> bool:
    """Return whether a required tracker setup value is usable."""
    value = tracker_config.get(key)
    if value is None or value is False:
        return False
    if not isinstance(value, str):
        return True

    normalized = value.strip()
    if not normalized:
        return False

    example_value = example_tracker_config.get(key)
    normalized_example = example_value.strip() if isinstance(example_value, str) else ""
    placeholder_example = normalized_example.replace("_", " ").replace("-", " ")
    return not (normalized_example and normalized == normalized_example and _TRACKER_SETUP_PLACEHOLDER_PATTERN.search(placeholder_example))


def _tracker_setup_is_complete(
    tracker_config: Mapping[str, Any],
    example_tracker_config: Mapping[str, Any],
    *,
    cookie_required: bool,
    cookie_configured: bool,
    optional_setup_keys: set[str] | frozenset[str] = frozenset(),
) -> bool:
    """Return whether all detected authentication requirements are complete."""
    if cookie_required and not cookie_configured:
        return False

    required_keys = [key for key in _TRACKER_REQUIRED_SETUP_KEYS if key in example_tracker_config and key not in optional_setup_keys]
    if required_keys:
        return all(_tracker_setup_value_is_complete(key, tracker_config, example_tracker_config) for key in required_keys)

    if cookie_required:
        return True
    return _has_configured_tracker_value(tracker_config, example_tracker_config)


def _configured_tracker_names(
    trackers_section: Mapping[str, Any],
    example_trackers: Mapping[str, Any],
    supported_trackers: Mapping[str, Any],
    cookie_trackers: set[str] | None = None,
    user_config: Mapping[str, Any] | None = None,
) -> set[str]:
    """Return supported tracker names whose detected setup requirements are complete."""
    supported_names = {str(name).upper() for name in supported_trackers}
    configured: set[str] = set()
    cookie_tracker_names = {str(name).upper() for name in (cookie_trackers or set())}

    tracker_configs: dict[str, Mapping[str, object]] = {str(name).upper(): value for name, value in trackers_section.items() if _is_str_mapping(value)}
    example_configs: dict[str, Mapping[str, object]] = {str(name).upper(): value for name, value in example_trackers.items() if _is_str_mapping(value)}

    # Older configurations stored the BroadcasTheNet API key in DEFAULT.
    default_section_raw: object = user_config.get("DEFAULT") if user_config else None
    legacy_btn_api: object = default_section_raw.get("btn_api") if _is_str_mapping(default_section_raw) else None
    if isinstance(legacy_btn_api, str):
        legacy_btn_api = legacy_btn_api.strip()

    for tracker_name in supported_names:
        tracker_config = dict(tracker_configs.get(tracker_name, {}))
        example_tracker_config = example_configs.get(tracker_name, {})
        if tracker_name == "BROADCASTHENET" and legacy_btn_api and not tracker_config.get("api_key"):
            tracker_config["api_key"] = legacy_btn_api

        tracker_class = supported_trackers.get(tracker_name)
        cookie_required = str(getattr(tracker_class, "auth_type", "") or "").strip().lower() == "cookies"
        optional_setup_keys = {str(key) for key in (getattr(tracker_class, "optional_setup_keys", ()) or ())}
        if _tracker_setup_is_complete(
            tracker_config,
            example_tracker_config,
            cookie_required=cookie_required,
            cookie_configured=tracker_name in cookie_tracker_names,
            optional_setup_keys=optional_setup_keys,
        ):
            configured.add(tracker_name)

    return configured & supported_names


def _configured_cookie_tracker_names(
    supported_trackers: Mapping[str, Any],
    user_config: dict[str, Any],
    state_dir: Path,
    cookie_file_finder: Callable[[str, str, dict[str, Any] | None], str],
) -> set[str]:
    """Return cookie-configured trackers without one bad lookup stopping the rest."""
    configured: set[str] = set()
    for tracker_name in supported_trackers:
        try:
            has_cookie_file = Path(cookie_file_finder(str(state_dir), tracker_name, user_config)).is_file()
        except AttributeError, OSError, TypeError, ValueError:
            has_cookie_file = False
        if has_cookie_file:
            configured.add(tracker_name.upper())

    return configured


def _tracker_codebase(tracker_name: str) -> str | None:
    """Expose the framework registered for a tracker."""
    from src.trackersetup import get_tracker_framework

    framework = get_tracker_framework(tracker_name) or ""
    return {"UNIT3D": "UNIT3D", "GAZELLE": "Gazelle", "NEXUSPHP": "NexusPHP", "AVISTAZ": "AvistaZ", "LUMINANCE": "Luminance"}.get(framework)


def _tracker_destination_type(tracker_class: Any) -> str:
    """Return the WebUI destination category without changing tracker IDs."""
    return "usenet" if bool(getattr(tracker_class, "is_usenet", False)) else "torrent"


def _tracker_supported_categories(tracker_class: Any) -> list[str]:
    """Return normalized upload categories declared by a tracker class."""
    categories: object = getattr(tracker_class, "supported_categories", ()) or ()
    if isinstance(categories, str):
        categories_list: list[object] = [categories]
    elif _is_obj_sequence(categories):
        categories_list = list(categories)
    elif isinstance(categories, set):
        categories_list = list(cast(set[object], categories))
    else:
        return []
    return list(dict.fromkeys(str(category).strip().upper() for category in categories_list if str(category).strip()))


def _tracker_status_from_http_code(status_code: int) -> tuple[str, str]:
    """Map a tracker homepage response to a deliberately advisory state."""
    if status_code == 429:
        return "issue", "The tracker is reachable but is rate limiting requests (HTTP 429)."
    if status_code >= 500:
        return "issue", f"The tracker returned a server error (HTTP {status_code})."
    if 100 <= status_code < 500:
        return "available", "The tracker website responded."
    return "issue", "The tracker returned an unexpected response."


def _probe_tracker_url(tracker_name: str, base_url: str) -> dict[str, Any]:
    """Perform a lightweight website reachability probe without using credentials."""
    checked_at = datetime.now(UTC).isoformat()
    parsed_url = urllib.parse.urlsplit(base_url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.hostname:
        return {
            "name": tracker_name,
            "state": "not_checked",
            "message": "No status URL is available for this tracker.",
            "checked_at": checked_at,
        }

    httpx = None
    try:
        httpx = flask_compat_mod._dynamic_import("httpx")
        with (
            httpx.Client(
                follow_redirects=True,
                timeout=4.0,
                headers={"User-Agent": f"Upload-Assistant-WebUI/{APP_VERSION}"},
            ) as client,
            client.stream("GET", base_url) as response,
        ):
            # Streaming avoids downloading tracker homepages just to confirm
            # that the service can answer an HTTP request.
            status_code = int(response.status_code)
        state, message = _tracker_status_from_http_code(status_code)
        result: dict[str, Any] = {
            "name": tracker_name,
            "state": state,
            "message": message,
            "status_code": status_code,
            "checked_at": checked_at,
        }
        if status_code == 429:
            result["reason"] = "rate_limit"
        elif status_code >= 500:
            result["reason"] = "server_error"
        return result
    except Exception as error:
        # Keep network and DNS exception details out of the browser response.
        # A later check can distinguish a transient local-network problem from
        # a tracker outage.
        is_timeout = bool(httpx is not None and isinstance(error, getattr(httpx, "TimeoutException", ())))
        return {
            "name": tracker_name,
            "state": "unavailable",
            "reason": "timeout" if is_timeout else "connection",
            "message": ("The tracker website did not respond before the status check timed out." if is_timeout else "The tracker website could not be reached."),
            "checked_at": checked_at,
        }


def _tracker_status_cache_payload(tracker_names: Sequence[str]) -> dict[str, dict[str, Any]]:
    """Return cached status entries, marking old results as stale."""
    now = time.time()
    payload: dict[str, dict[str, Any]] = {}
    with _tracker_status_cache_lock:
        for tracker_name in tracker_names:
            cached = _tracker_status_cache.get(tracker_name)
            if cached is None:
                payload[tracker_name] = {
                    "name": tracker_name,
                    "state": "not_checked",
                    "message": "Not checked yet.",
                    "checked_at": None,
                    "stale": False,
                }
                continue
            entry = {key: value for key, value in cached.items() if key != "_checked_epoch"}
            checked_epoch = float(cached.get("_checked_epoch", 0.0))
            entry["stale"] = now - checked_epoch > _TRACKER_STATUS_CACHE_SECONDS
            payload[tracker_name] = entry
    return payload


def _supported_tracker_status_targets() -> dict[str, str]:
    """Return trusted tracker names and homepage URLs from the class catalogue."""
    from src.trackersetup import tracker_class_map

    return {str(tracker_name).upper(): str(getattr(tracker_class, "base_url", "") or "").strip() for tracker_name, tracker_class in tracker_class_map.items()}


def _cached_prowlarr_credentials(base_url: str, api_key: str, supported_trackers: set[str]) -> Any:
    """Reuse a recent Prowlarr credential report for the same connection.

    Failures are not cached, and changing the URL or API key misses the cache.
    """
    from src.prowlarr import fetch_prowlarr_credentials

    # The cached report already holds this process's credentials in memory.
    key = (base_url, api_key, frozenset(supported_trackers))
    now = time.monotonic()
    with _prowlarr_report_cache_lock:
        cached = _prowlarr_report_cache.get(key)
        generation = _prowlarr_report_cache_generation
    if cached and now - cached[0] < _PROWLARR_REPORT_CACHE_SECONDS:
        return cached[1]
    report = fetch_prowlarr_credentials(base_url, api_key, supported_trackers)
    with _prowlarr_report_cache_lock:
        # A fetch that started before an invalidation must not restore old data.
        if generation == _prowlarr_report_cache_generation:
            _prowlarr_report_cache.clear()
            _prowlarr_report_cache[key] = (now, report)
    return report


def _invalidate_prowlarr_report_cache() -> None:
    global _prowlarr_report_cache_generation
    with _prowlarr_report_cache_lock:
        _prowlarr_report_cache.clear()
        _prowlarr_report_cache_generation += 1
