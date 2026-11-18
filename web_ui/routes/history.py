"""Upload stats and history routes."""

import json
import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from web_ui import config_store as config_store_mod
from web_ui import context as context_mod
from web_ui import security as security_mod
from web_ui.extensions import _rate_limit_key_func, limiter
from web_ui.flask_compat import Blueprint, Response, jsonify, request
from web_ui.request_utils import _request_json_dict

bp = Blueprint("history", __name__)


def _add_stats_destination_display_names(payload: dict[str, Any]) -> None:
    """Add catalogue-backed labels without changing persisted destination keys."""
    from src.trackersetup import tracker_class_map

    rows = payload.get("uploads", {}).get("by_destination", [])
    filter_rows = payload.get("filters", {}).get("destinations", [])
    for row in [*rows, *filter_rows]:
        destination = str(row.get("destination") or "")
        tracker_class = tracker_class_map.get(destination.upper())
        row["display_name"] = str(getattr(tracker_class, "display_name", destination))
    for node in payload.get("sankey", {}).get("nodes", []):
        destination = str(node.get("destination") or "")
        if destination:
            tracker_class = tracker_class_map.get(destination.upper())
            node["label"] = str(getattr(tracker_class, "display_name", destination))


@bp.route("/api/stats", methods=["GET", "DELETE"])
def stats_api():
    """Read or reset local aggregate statistics for an authenticated browser."""
    if not security_mod._is_authenticated() or security_mod._get_bearer_from_header():
        return jsonify({"success": False, "error": "Authentication required (web session)"}), 401
    if not security_mod._verify_csrf_header() or not security_mod._verify_same_origin():
        return jsonify({"success": False, "error": "CSRF/Origin validation failed"}), 403

    from src.stats import get_empty_stats, get_stats, reset_stats, stats_collection_enabled

    if request.method == "DELETE":
        body = _request_json_dict()
        if body.get("confirmation") != "RESET":
            return jsonify({"success": False, "error": "Type RESET to confirm"}), 400
        try:
            return jsonify({"success": True, "reset_at": reset_stats(context_mod.STATE_DIR)})
        except OSError, sqlite3.Error:
            return jsonify({"success": False, "error": "Unable to reset statistics"}), 500

    period = str(request.args.get("range", "30d"))
    mode = str(request.args.get("mode", "real"))
    date_from = request.args.get("from")
    date_to = request.args.get("to")
    tracker = str(request.args.get("tracker", ""))
    time_basis = str(request.args.get("timezone", "utc"))
    local_date = request.args.get("today")
    try:
        config = config_store_mod._load_config_from_file(context_mod.STATE_DIR / "data" / "config.py") or {}
        enabled = stats_collection_enabled(config)
        payload = (
            get_stats(
                period,
                mode,
                context_mod.STATE_DIR,
                date_from=date_from,
                date_to=date_to,
                tracker=tracker,
                time_basis=time_basis,
                local_date=local_date,
            )
            if enabled
            else get_empty_stats(
                period,
                mode,
                date_from=date_from,
                date_to=date_to,
                tracker=tracker,
                time_basis=time_basis,
                local_date=local_date,
            )
        )
        _add_stats_destination_display_names(payload)
        payload["enabled"] = enabled
        return jsonify(payload), 200 if payload["success"] else 500
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400


def _history_request_error() -> tuple[Any, int] | None:
    """Allow history requests only from an authenticated browser session (no API tokens)."""
    if not security_mod._is_authenticated() or security_mod._get_bearer_from_header():
        return jsonify({"success": False, "error": "Authentication required (web session)"}), 401
    if not security_mod._verify_csrf_header() or not security_mod._verify_same_origin():
        return jsonify({"success": False, "error": "CSRF/Origin validation failed"}), 403
    return None


def _history_tracker_names(codes: Iterable[str]) -> dict[str, str]:
    from src.trackersetup import tracker_class_map

    return {code: str(getattr(tracker_class_map.get(code), "display_name", code)) for code in codes}


@bp.route("/api/history", methods=["GET", "DELETE"])
@limiter.limit("600 per hour", key_func=_rate_limit_key_func, override_defaults=True)
def history_api():
    """List or clear the local upload history."""
    error = _history_request_error()
    if error is not None:
        return error

    from src.upload_history import clear_history, history_enabled, list_items

    if request.method == "DELETE":
        if _request_json_dict().get("confirmation") != "CLEAR":
            return jsonify({"success": False, "error": "Type CLEAR to confirm"}), 400
        try:
            return jsonify({"success": True, "removed": clear_history(context_mod.STATE_DIR)})
        except OSError, sqlite3.Error:
            return jsonify({"success": False, "error": "Unable to clear the upload history"}), 500

    args = request.args
    try:
        page = list_items(
            context_mod.STATE_DIR,
            search=str(args.get("q", ""))[:200],
            category=str(args.get("category", "")),
            tracker=str(args.get("tracker", "")),
            tracker_status=str(args.get("tracker_status", "")),
            outcome=str(args.get("outcome", "")),
            has_requests=str(args.get("requests", "")).lower() in {"1", "true", "yes"},
            after=str(args.get("after", "")),
            before=str(args.get("before", "")),
            limit=int(args.get("limit", 50)),
            offset=int(args.get("offset", 0)),
        )
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except OSError, sqlite3.Error:
        return jsonify({"success": False, "error": "Unable to read the upload history"}), 500
    trackers = {tracker["tracker"] for item in page["items"] for tracker in item["trackers"]} | set(page["facets"]["trackers"])
    config = config_store_mod._load_config_from_file(context_mod.STATE_DIR / "data" / "config.py") or {}
    return jsonify({**page, "tracker_names": _history_tracker_names(sorted(trackers)), "enabled": history_enabled(config), "success": True})


@bp.route("/api/history/export")
@limiter.limit("120 per hour", key_func=_rate_limit_key_func, override_defaults=True)
def history_export_api():
    """Download every history entry matching the list filters as CSV or JSON."""
    error = _history_request_error()
    if error is not None:
        return error

    from src.upload_history import export_csv, export_items

    args = request.args
    export_format = str(args.get("format", "csv")).lower()
    if export_format not in {"csv", "json"}:
        return jsonify({"success": False, "error": "format must be csv or json"}), 400
    try:
        items = export_items(
            context_mod.STATE_DIR,
            search=str(args.get("q", ""))[:200],
            category=str(args.get("category", "")),
            tracker=str(args.get("tracker", "")),
            tracker_status=str(args.get("tracker_status", "")),
            outcome=str(args.get("outcome", "")),
            has_requests=str(args.get("requests", "")).lower() in {"1", "true", "yes"},
            after=str(args.get("after", "")),
            before=str(args.get("before", "")),
        )
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except OSError, sqlite3.Error:
        return jsonify({"success": False, "error": "Unable to read the upload history"}), 500
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%SZ")
    if export_format == "json":
        body, mimetype = json.dumps({"items": items}, ensure_ascii=False, indent=2), "application/json"
    else:
        body, mimetype = export_csv(items), "text/csv; charset=utf-8"
    response = Response(body, mimetype=mimetype)
    response.headers["Content-Disposition"] = f'attachment; filename="upload-assistant-history-{stamp}.{export_format}"'
    return response


@bp.route("/api/history/<int:item_id>", methods=["GET", "DELETE"])
@limiter.limit("600 per hour", key_func=_rate_limit_key_func, override_defaults=True)
def history_item_api(item_id: int):
    """Read or delete one upload history entry."""
    error = _history_request_error()
    if error is not None:
        return error

    from src.upload_history import delete_item, get_item

    try:
        if request.method == "DELETE":
            if not delete_item(item_id, context_mod.STATE_DIR):
                return jsonify({"success": False, "error": "History entry not found"}), 404
            return jsonify({"success": True})
        item = get_item(item_id, context_mod.STATE_DIR)
    except OSError, sqlite3.Error:
        return jsonify({"success": False, "error": "Unable to read the upload history"}), 500
    if item is None:
        return jsonify({"success": False, "error": "History entry not found"}), 404
    item["tracker_names"] = _history_tracker_names(tracker["tracker"] for tracker in item["trackers"])
    return jsonify({"success": True, "item": item})
