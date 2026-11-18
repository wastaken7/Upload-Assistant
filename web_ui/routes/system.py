"""Health, update, changelog and external tool status routes."""

from collections.abc import Mapping
from typing import Any

from src.external_tools import EXTERNAL_TOOL_KEYS, check_external_tools
from src.update_checker import get_changelog_history, get_update_status
from web_ui import config_store as config_store_mod
from web_ui import context as context_mod
from web_ui import security as security_mod
from web_ui.context import console
from web_ui.extensions import _rate_limit_key_func, limiter
from web_ui.flask_compat import Blueprint, _is_str_mapping, jsonify, request
from web_ui.request_utils import _as_dict

bp = Blueprint("system", __name__)


@bp.route("/api/health")
@limiter.exempt
def health():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "success": True, "message": "Upload-Assistant Web UI is running"})


@bp.route("/api/update_status")
@limiter.limit("7200 per hour", key_func=_rate_limit_key_func, override_defaults=True)
def update_status():
    """Return the cached upstream release status for the shared application rail."""
    if not security_mod._is_authenticated():
        return jsonify({"success": False, "error": "Authentication required (web session)"}), 401
    if not security_mod._verify_csrf_header() or not security_mod._verify_same_origin():
        return jsonify({"success": False, "error": "CSRF/Origin validation failed"}), 403

    user_config = config_store_mod._load_config_from_file(context_mod.STATE_DIR / "data" / "config.py") or {}
    example_config = config_store_mod._load_config_from_file(context_mod.CODE_DIR / "data" / "example_config.py") or {}
    user_defaults = _as_dict(user_config.get("DEFAULT")) or {}
    example_defaults = _as_dict(example_config.get("DEFAULT")) or {}
    force = str(request.args.get("refresh", "")).strip().lower() in {"1", "true", "yes"}
    enabled = bool(user_defaults.get("update_notification", example_defaults.get("update_notification", True)))
    raw_cache_hours = user_defaults.get(
        "update_notification_cache_hours",
        example_defaults.get("update_notification_cache_hours", 4),
    )
    try:
        cache_hours = max(0.0, float(raw_cache_hours))
    except TypeError, ValueError:
        cache_hours = 4.0

    return jsonify(
        get_update_status(
            enabled=enabled or force,
            cache_hours=cache_hours,
            force=force,
        )
    )


@bp.route("/api/changelog")
def changelog():
    """Return cached upstream release history for the shared changelog viewer."""
    if not security_mod._is_authenticated():
        return jsonify({"success": False, "error": "Authentication required (web session)"}), 401
    if not security_mod._verify_csrf_header() or not security_mod._verify_same_origin():
        return jsonify({"success": False, "error": "CSRF/Origin validation failed"}), 403

    user_config = config_store_mod._load_config_from_file(context_mod.STATE_DIR / "data" / "config.py") or {}
    example_config = config_store_mod._load_config_from_file(context_mod.CODE_DIR / "data" / "example_config.py") or {}
    user_defaults = _as_dict(user_config.get("DEFAULT")) or {}
    example_defaults = _as_dict(example_config.get("DEFAULT")) or {}
    force = request.args.get("refresh", "").strip().lower() in {"1", "true", "yes"}
    raw_cache_hours = user_defaults.get(
        "update_notification_cache_hours",
        example_defaults.get("update_notification_cache_hours", 4),
    )
    try:
        cache_hours = max(0.0, float(raw_cache_hours))
    except TypeError, ValueError:
        cache_hours = 4.0

    return jsonify(
        get_changelog_history(
            cache_hours=cache_hours,
            force=force,
        )
    )


@bp.route("/api/external_tools_status", methods=["POST"])
@limiter.limit("60 per hour", key_func=_rate_limit_key_func)
def external_tools_status():
    """Check configured, detected, and runtime-managed external tools."""
    if not security_mod._is_authenticated():
        return jsonify({"success": False, "error": "Authentication required (web session)"}), 401
    if not security_mod._verify_csrf_header() or not security_mod._verify_same_origin():
        return jsonify({"success": False, "error": "CSRF/Origin validation failed"}), 403

    payload = request.get_json(silent=True)
    payload_map: Mapping[str, object] = payload if _is_str_mapping(payload) else {}
    raw_paths = payload_map.get("paths", {})
    if not _is_str_mapping(raw_paths):
        return jsonify({"success": False, "error": "Invalid external tool paths"}), 400

    user_config = config_store_mod._load_config_from_file(context_mod.STATE_DIR / "data" / "config.py") or {}
    example_config = config_store_mod._load_config_from_file(context_mod.CODE_DIR / "data" / "example_config.py") or {}
    user_defaults = _as_dict(user_config.get("DEFAULT")) or {}
    example_defaults = _as_dict(example_config.get("DEFAULT")) or {}
    effective_defaults: dict[str, Any] = {}

    for key in EXTERNAL_TOOL_KEYS:
        value = raw_paths.get(key, user_defaults.get(key, example_defaults.get(key, "")))
        if value is None:
            value = ""
        if not isinstance(value, str) or len(value) > 4096:
            return jsonify({"success": False, "error": f"Invalid path value for {key}"}), 400
        effective_defaults[key] = value

    try:
        statuses = check_external_tools(
            effective_defaults,
            state_dir=context_mod.STATE_DIR,
            code_dir=context_mod.CODE_DIR,
        )
    except Exception as error:
        console.print(f"External tool status check failed: {error}", markup=False)
        return jsonify({"success": False, "error": "Unable to check external tools"}), 500

    return jsonify({"success": True, "statuses": statuses})
