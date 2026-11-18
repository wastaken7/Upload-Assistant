"""Tracker list, status and API key routes."""

import concurrent.futures
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from src.args import tracker_cli_aliases
from src.meta import Meta
from web_ui import config_store as config_store_mod
from web_ui import context as context_mod
from web_ui import security as security_mod
from web_ui import tracker_info as tracker_info_mod
from web_ui.extensions import _rate_limit_key_func, limiter
from web_ui.flask_compat import Blueprint, _is_obj_list, _is_str_dict, _is_str_mapping, jsonify
from web_ui.request_utils import _request_json_dict
from web_ui.tracker_info import (
    _TRACKER_STATUS_CACHE_SECONDS,
    _TRACKER_STATUS_MAX_WORKERS,
    _cached_prowlarr_credentials,
    _configured_cookie_tracker_names,
    _configured_tracker_names,
    _probe_tracker_url,
    _tracker_codebase,
    _tracker_destination_type,
    _tracker_status_cache,
    _tracker_status_cache_lock,
    _tracker_status_cache_payload,
    _tracker_status_check_lock,
    _tracker_supported_categories,
)

bp = Blueprint("trackers", __name__)


@bp.route("/api/tracker_status")
def get_tracker_status():
    """Return cached, credential-free tracker reachability checks."""
    if not security_mod._is_authenticated():
        return jsonify({"success": False, "error": "Authentication required (web session)"}), 401
    if not security_mod._verify_csrf_header() or not security_mod._verify_same_origin():
        return jsonify({"success": False, "error": "CSRF/Origin validation failed"}), 403

    with _tracker_status_cache_lock:
        cached_names = sorted(_tracker_status_cache)

    return jsonify(
        {
            "success": True,
            "cache_seconds": _TRACKER_STATUS_CACHE_SECONDS,
            "statuses": _tracker_status_cache_payload(cached_names),
        }
    )


@bp.route("/api/tracker_status", methods=["POST"])
@limiter.limit("30 per hour", key_func=_rate_limit_key_func)
def refresh_tracker_status():
    """Refresh selected tracker reachability checks."""
    if not security_mod._is_authenticated():
        return jsonify({"success": False, "error": "Authentication required (web session)"}), 401
    if not security_mod._verify_csrf_header() or not security_mod._verify_same_origin():
        return jsonify({"success": False, "error": "CSRF/Origin validation failed"}), 403

    try:
        supported_targets = tracker_info_mod._supported_tracker_status_targets()
    except Exception as error:
        return jsonify({"success": False, "error": f"Failed to load trackers: {error}"}), 500

    data = _request_json_dict()
    requested = data.get("trackers")
    if not _is_obj_list(requested):
        return jsonify({"success": False, "error": "Trackers must be provided as a list"}), 400

    tracker_names = list(dict.fromkeys(str(name).strip().upper() for name in requested[:100] if str(name).strip()))
    unknown = [name for name in tracker_names if name not in supported_targets]
    if unknown:
        return jsonify({"success": False, "error": "One or more trackers are not supported"}), 400
    if not tracker_names:
        return jsonify({"success": False, "error": "Select at least one tracker to check"}), 400

    checked_results: list[dict[str, Any]] = []
    with _tracker_status_check_lock:
        worker_count = min(_TRACKER_STATUS_MAX_WORKERS, len(tracker_names))
        with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = {executor.submit(_probe_tracker_url, name, supported_targets[name]): name for name in tracker_names}
            checked_results.extend(future.result() for future in concurrent.futures.as_completed(futures))

        checked_epoch = time.time()
        with _tracker_status_cache_lock:
            for result in checked_results:
                name = str(result["name"])
                _tracker_status_cache[name] = {**result, "_checked_epoch": checked_epoch}

    return jsonify(
        {
            "success": True,
            "cache_seconds": _TRACKER_STATUS_CACHE_SECONDS,
            "statuses": _tracker_status_cache_payload(tracker_names),
        }
    )


@bp.route("/api/trackers")
@limiter.limit("7200 per hour", key_func=_rate_limit_key_func, override_defaults=True)
def get_trackers():
    """Return supported trackers, including their default/configured status."""
    if not security_mod._is_authenticated():
        return jsonify({"success": False, "error": "Authentication required (web session)"}), 401

    if not security_mod._verify_csrf_header() or not security_mod._verify_same_origin():
        return jsonify({"success": False, "error": "CSRF/Origin validation failed"}), 403

    base_dir = context_mod.STATE_DIR
    config_path = base_dir / "data" / "config.py"
    user_config = config_store_mod._load_config_from_file(config_path) or {}

    # Load tracker_class_map from src.trackersetup
    try:
        from src.trackersetup import tracker_class_map
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to load trackers: {e}"}), 500

    example_config = config_store_mod._load_config_from_file(context_mod.CODE_DIR / "data" / "example_config.py") or {}
    example_trackers_raw = example_config.get("TRACKERS", {})
    example_trackers = cast(dict[str, Any], example_trackers_raw) if isinstance(example_trackers_raw, Mapping) else {}

    from src.prowlarr import ProwlarrError, apply_prowlarr_credentials, configured_prowlarr

    prowlarr_sources: set[str] = set()
    prowlarr_cookie_trackers: set[str] = set()
    try:
        if prowlarr_connection := configured_prowlarr(user_config):
            prowlarr_report = _cached_prowlarr_credentials(
                prowlarr_connection[0],
                prowlarr_connection[1],
                set(tracker_class_map),
            )
            prowlarr_sources = apply_prowlarr_credentials(user_config, prowlarr_report)
            prowlarr_cookie_trackers = {name for name, credential in prowlarr_report.credentials.items() if credential.cookie}
    except ProwlarrError:
        # The tracker catalogue remains usable with local configuration when
        # the optional Prowlarr instance is unavailable.
        prowlarr_sources = set()
        prowlarr_cookie_trackers = set()

    trackers_section_raw = user_config.get("TRACKERS", {})
    trackers_section = cast(dict[str, Any], trackers_section_raw) if isinstance(trackers_section_raw, Mapping) else {}
    default_trackers_val = trackers_section.get("default_trackers", "")
    default_trackers_list: list[str] = []
    if isinstance(default_trackers_val, str):
        default_trackers_list = [t.strip().upper() for t in default_trackers_val.split(",") if t.strip()]
    elif _is_obj_list(default_trackers_val):
        default_trackers_list = [str(t).strip().upper() for t in default_trackers_val if str(t).strip()]
    default_trackers_list = [Meta.canonical_tracker_name(name) for name in default_trackers_list]

    cookie_trackers: set[str] = set()
    try:
        from src.cookie_auth import CookieDirectoryScan, find_cookie_file

        cookie_scan = CookieDirectoryScan(context_mod.STATE_DIR)
    except Exception:
        # Cookie discovery is an additional configuration signal. A missing or
        # unreadable cookies directory should not prevent the selector loading.
        cookie_trackers = set()
    else:
        cookie_trackers = _configured_cookie_tracker_names(
            tracker_class_map,
            user_config,
            context_mod.STATE_DIR,
            lambda base_dir, tracker, config: find_cookie_file(base_dir, tracker, config, scan=cookie_scan),
        )

    prowlarr_sources -= cookie_trackers
    cookie_trackers |= prowlarr_cookie_trackers

    configured_trackers = _configured_tracker_names(
        trackers_section,
        example_trackers,
        tracker_class_map,
        cookie_trackers,
        user_config,
    )

    trackers_data: list[dict[str, Any]] = []
    from src.api_key_expiry import get_api_key_expiry

    for tracker_name, tracker_class in tracker_class_map.items():
        display_name = getattr(tracker_class, "display_name", tracker_name)
        base_url = getattr(tracker_class, "base_url", "")
        auth_type = str(getattr(tracker_class, "auth_type", "") or "").strip().lower()
        optional_setup_keys = sorted(str(key) for key in (getattr(tracker_class, "optional_setup_keys", ()) or ()))
        destination_type = _tracker_destination_type(tracker_class)
        supported_categories = _tracker_supported_categories(tracker_class)
        expiry_supported = bool(getattr(tracker_class, "api_key_expiry_supported", False))
        tracker_config = trackers_section.get(tracker_name, {})
        api_key = str(tracker_config.get("api_key") or "").strip() if _is_str_mapping(tracker_config) else ""
        favicon_url = ""
        static_dir = Path(__file__).parent.parent / "static"
        for ext in ["png", "svg", "ico"]:
            local_path = static_dir / "img" / "trackers" / f"{tracker_name.lower()}.{ext}"
            if local_path.is_file():
                favicon_url = f"/static/img/trackers/{tracker_name.lower()}.{ext}"
                break

        trackers_data.append(
            {
                "name": tracker_name,
                "display_name": display_name,
                "codebase": _tracker_codebase(tracker_name),
                "base_url": base_url,
                "favicon": favicon_url,
                "configured": tracker_name.upper() in configured_trackers,
                "credential_source": ("prowlarr" if tracker_name.upper() in prowlarr_sources else "local" if tracker_name.upper() in configured_trackers else None),
                "api_key_expiry_supported": expiry_supported,
                "api_key_expiry": get_api_key_expiry(tracker_name, api_key, base_url, context_mod.STATE_DIR) if expiry_supported else None,
                "auth_type": auth_type,
                "optional_setup_keys": optional_setup_keys,
                "cookie_configured": tracker_name.upper() in cookie_trackers,
                "destination_type": destination_type,
                "supported_categories": supported_categories,
            }
        )

    trackers_data.sort(key=lambda x: str(x["display_name"]).lower())

    aliases = Meta.tracker_name_aliases()
    alias_error = ""
    try:
        aliases.update({alias: Meta.canonical_tracker_name(name) for alias, name in tracker_cli_aliases(user_config).items()})
    except ValueError as error:
        # A malformed manual edit must not hide the configuration/selector UI.
        alias_error = str(error)
    return jsonify({"success": True, "default_trackers": default_trackers_list, "trackers": trackers_data, "tracker_aliases": aliases, "alias_error": alias_error})


@bp.route("/api/tracker_api_key_status", methods=["POST"])
@limiter.limit("120 per hour", key_func=_rate_limit_key_func)
def tracker_api_key_status():
    """Read cached expiry or explicitly check a saved/draft tracker API key."""
    if not security_mod._is_authenticated():
        return jsonify({"success": False, "error": "Authentication required (web session)"}), 401
    if not security_mod._verify_csrf_header() or not security_mod._verify_same_origin():
        return jsonify({"success": False, "error": "CSRF/Origin validation failed"}), 403

    import httpx

    from src.api_key_expiry import get_api_key_expiry, record_api_key_expiry
    from src.prowlarr import ProwlarrError, configured_prowlarr, fetch_prowlarr_credentials
    from src.trackersetup import tracker_class_map

    data = _request_json_dict()
    tracker = str(data.get("tracker") or "").strip().upper()
    tracker_class = tracker_class_map.get(tracker)
    if not tracker_class or not getattr(tracker_class, "api_key_expiry_supported", False):
        return jsonify({"success": False, "error": "API key expiry checks are not supported for this tracker"}), 400
    config = config_store_mod._load_config_from_file(context_mod.STATE_DIR / "data" / "config.py") or {}
    # The browser only holds a placeholder for a saved key, so use the saved one.
    if "api_key" in data and data["api_key"] != config_store_mod.REDACTED_PLACEHOLDER:
        api_key = data["api_key"]
    else:
        trackers_config = config.get("TRACKERS")
        tracker_config = trackers_config.get(tracker) if _is_str_mapping(trackers_config) else None
        api_key = tracker_config.get("api_key", "") if _is_str_mapping(tracker_config) else ""
    if not isinstance(api_key, str) or "\r" in api_key or "\n" in api_key:
        return jsonify({"success": False, "error": "Enter a valid API key"}), 400
    api_key = api_key.strip()
    source = "local"
    refresh = data.get("refresh") is True
    if not api_key and refresh:
        try:
            if connection := configured_prowlarr(config):
                report = fetch_prowlarr_credentials(*connection, {tracker})
                credential = report.credentials.get(tracker)
                api_key = credential.api_key if credential else ""
                source = "prowlarr"
        except ProwlarrError as error:
            return jsonify({"success": False, "error": str(error)}), 400
    base_url = tracker_class.base_url
    if not refresh:
        return jsonify({"success": True, "expiry": get_api_key_expiry(tracker, api_key, base_url, context_mod.STATE_DIR)})
    if not api_key:
        return jsonify({"success": False, "error": "Enter an API key or configure a Prowlarr credential source"}), 400

    # Use the existing search endpoint/permissions, not /user's additional
    # account-information permission. The destination comes from UA's tracker
    # definition; draft config cannot redirect a credential to another host.
    try:
        with httpx.Client(timeout=10.0, follow_redirects=False) as client:
            response = client.get(
                tracker_class.search_url,
                headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
                params={"perPage": 1},
            )
            response.raise_for_status()
            payload = response.json()
        if not _is_str_dict(payload) or payload.get("success") is False:
            return jsonify({"success": False, "error": "The tracker returned an unsuccessful API response"}), 400
        observed = record_api_key_expiry(tracker, api_key, base_url, response, context_mod.STATE_DIR, payload=payload)
    except httpx.HTTPStatusError as error:
        code = error.response.status_code
        message = (
            "The tracker rejected the API key. It may be invalid, revoked or expired."
            if code == 401
            else "The tracker denied the API request. Check the key's search/download permissions and account access."
            if code == 403
            else f"The tracker returned HTTP {code}. Try again later."
        )
        return jsonify({"success": False, "error": message}), 400
    except httpx.RequestError:
        return jsonify({"success": False, "error": "The tracker could not be reached. Try again later."}), 400
    except ValueError:
        return jsonify({"success": False, "error": "The tracker did not return a valid JSON API response"}), 400

    expiry = observed or get_api_key_expiry(tracker, api_key, base_url, context_mod.STATE_DIR)
    return jsonify(
        {
            "success": True,
            "expiry": expiry,
            "credential_source": source,
            "message": "API key accepted." if observed else "API key accepted, but expiry was not reported. Any date shown is the last observed expiry.",
        }
    )
