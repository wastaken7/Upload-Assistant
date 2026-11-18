"""Config editor routes."""

import os
import re
from collections.abc import Callable, Mapping, Sequence
from functools import wraps
from pathlib import Path
from typing import Any, cast

from src.args import tracker_cli_aliases
from src.config_sync import ConfigSyncError, ConfigWriteConflictError, config_write_lock, replace_config_source
from web_ui import config_store as config_store_mod
from web_ui import context as context_mod
from web_ui import flask_compat as flask_compat_mod
from web_ui import security as security_mod
from web_ui.config_store import (
    ConfigSection,
    _audit_config_updates,
    _build_config_items,
    _configured_torrent_client_names,
    _extract_example_metadata,
    _parse_config_source,
    _prepare_default_webui_section,
    _prepare_torrent_client_webui_section,
    _python_literal,
    _remove_config_key_in_source,
    _replace_config_value_in_source,
)
from web_ui.context import console
from web_ui.extensions import _rate_limit_key_func, limiter
from web_ui.flask_compat import Blueprint, _is_obj_list, _is_str_dict, jsonify
from web_ui.request_utils import _as_dict, _request_json_dict
from web_ui.security import _json_safe
from web_ui.tracker_info import _TRACKER_DEFAULT_OVERRIDE_KEYS, _invalidate_prowlarr_report_cache

bp = Blueprint("config", __name__)


@bp.route("/api/config_options")
def config_options():
    """Return config options based on example_config.py with overrides from config.py"""
    # Require an authenticated web session; disallow bearer/basic API auth for config access
    if not security_mod._is_authenticated():
        return jsonify({"success": False, "error": "Authentication required (web session)"}), 401

    # Require CSRF and same-origin for reading configuration options
    if not security_mod._verify_csrf_header() or not security_mod._verify_same_origin():
        return jsonify({"success": False, "error": "CSRF/Origin validation failed"}), 403

    base_dir = context_mod.STATE_DIR
    example_path = context_mod.CODE_DIR / "data" / "example_config.py"
    config_path = base_dir / "data" / "config.py"

    example_config_loaded = config_store_mod._load_config_from_file(example_path)
    example_config = example_config_loaded or {}
    user_config_loaded = config_store_mod._load_config_from_file(config_path)
    user_config = user_config_loaded or {}
    comments_map, subsection_map = _extract_example_metadata(example_path)

    # Determine config load status so the UI can warn the user
    # instead of silently showing defaults.
    config_warning: str | None = None
    if not config_path.exists():
        config_warning = "No config.py found — showing example defaults. Configure your settings and save, or place your config.py into the mounted data/ directory."
    elif user_config_loaded is None:
        config_warning = (
            "config.py exists but could not be loaded — showing example defaults. "
            "Check the container logs for details. The file may have a syntax error "
            "or may not contain a valid 'config' dict."
        )

    sections: list[ConfigSection] = []

    for section_name, example_section_raw in example_config.items():
        if not isinstance(example_section_raw, Mapping):
            continue
        example_section = cast(dict[str, Any], example_section_raw)

        if section_name == "DEFAULT":
            example_section = _prepare_default_webui_section(
                example_section,
                comments_map,
                subsection_map,
            )

        user_section_raw = user_config.get(section_name, {})
        user_section = cast(dict[str, Any], user_section_raw) if isinstance(user_section_raw, Mapping) else {}
        if section_name == "TORRENT_CLIENTS":
            example_section = _prepare_torrent_client_webui_section(
                example_section,
                user_section,
                comments_map,
            )
        items = _build_config_items(example_section, user_section, comments_map, subsection_map, [section_name])

        sections.append({"section": section_name, "items": items})

        if section_name == "TORRENT_CLIENTS":
            client_types: set[str] = set()
            for item in items:
                children = item.get("children")
                if children:
                    client_type_item = next((c for c in children if c.get("key") == "torrent_client"), None)
                    if client_type_item:
                        client_types.add(str(client_type_item.get("value", "unknown")))
            sections[-1]["client_types"] = sorted(client_types, key=lambda x: (x != "qbit", x))

    result: dict[str, object] = {"success": True, "sections": sections}
    if config_warning:
        result["config_warning"] = config_warning
    return jsonify(result)


@bp.route("/api/torrent_clients")
def torrent_clients():
    """Return torrent clients that are configured or actively referenced."""
    # Require web session for config listing (disallow bearer token access)
    if not security_mod._is_authenticated():
        return jsonify({"success": False, "error": "Authentication required (web session)"}), 401

    # Require CSRF + same-origin for config-related reads
    if not security_mod._verify_csrf_header() or not security_mod._verify_same_origin():
        return jsonify({"success": False, "error": "CSRF/Origin validation failed"}), 403

    base_dir = context_mod.STATE_DIR
    config_path = base_dir / "data" / "config.py"

    user_config = config_store_mod._load_config_from_file(config_path) or {}

    example_config = config_store_mod._load_config_from_file(context_mod.CODE_DIR / "data" / "example_config.py") or {}
    client_names = _configured_torrent_client_names(user_config, example_config)

    return jsonify({"success": True, "clients": client_names})


@bp.route("/api/config_test_prowlarr", methods=["POST"])
@limiter.limit("30 per hour", key_func=_rate_limit_key_func)
def config_test_prowlarr():
    """Test draft Prowlarr settings and return credential-free metadata."""
    if not security_mod._is_authenticated():
        return jsonify({"success": False, "error": "Authentication required (web session)"}), 401
    if not security_mod._verify_csrf_header() or not security_mod._verify_same_origin():
        return jsonify({"success": False, "error": "CSRF/Origin validation failed"}), 403
    # These tests send saved credentials to the draft's address.
    if (reauth := security_mod._settings_reauth_required_response()) is not None:
        return reauth

    data = _request_json_dict()
    base_url = str(data.get("url") or "").strip()
    api_key = str(data.get("api_key") or "").strip()
    if api_key == config_store_mod.REDACTED_PLACEHOLDER:
        # The browser only holds the placeholder for a saved key. Send it only to
        # the saved Prowlarr address, so an edited URL cannot collect the key.
        saved_config = config_store_mod._load_config_from_file(context_mod.STATE_DIR / "data" / "config.py") or {}
        saved_default = _as_dict(saved_config.get("DEFAULT")) or {}
        if not config_store_mod._same_destination_value(base_url, saved_default.get("prowlarr_url")):
            return jsonify({"success": False, "error": "The Prowlarr URL changed. Re-enter the API key to test the new address."}), 400
        api_key = str(saved_default.get("prowlarr_api_key") or "").strip()
    if not base_url or not api_key:
        return jsonify({"success": False, "error": "Prowlarr URL and API key are required"}), 400

    from src.prowlarr import ProwlarrError, fetch_prowlarr_credentials
    from src.trackersetup import tracker_class_map

    try:
        report = fetch_prowlarr_credentials(base_url, api_key, set(tracker_class_map), include_status=True)
    except ProwlarrError as error:
        return jsonify({"success": False, "error": str(error)}), 400
    except Exception:
        return jsonify({"success": False, "error": "Unable to test the Prowlarr connection"}), 500

    # A manual test is the way to pick up indexer changes before the cache expires.
    _invalidate_prowlarr_report_cache()

    api_key_trackers = sorted(name for name, credential in report.credentials.items() if credential.api_key)
    cookie_trackers = sorted(name for name, credential in report.credentials.items() if credential.cookie)
    return jsonify(
        {
            "success": True,
            "message": f"Connected to Prowlarr {report.version or '(version unavailable)'}. Found credentials for {len(report.credentials)} supported tracker(s).",
            "version": report.version,
            "enabled_indexers": report.enabled_indexers,
            "matched_indexers": report.matched_indexers,
            "credential_trackers": sorted(report.credentials),
            "api_key_trackers": api_key_trackers,
            "cookie_trackers": cookie_trackers,
            "masked_credentials": report.masked_credentials,
            "unsupported_indexers": report.unsupported_indexers,
        }
    )


def _config_write_route(view: Callable[..., Any]) -> Callable[..., Any]:
    """Guard and serialize every WebUI config writer with startup synchronization."""

    @wraps(view)
    def guarded(*args: Any, **kwargs: Any) -> Any:
        if not security_mod._is_authenticated():
            return jsonify({"success": False, "error": "Authentication required (web session)"}), 401
        if not security_mod._verify_csrf_header() or not security_mod._verify_same_origin():
            return jsonify({"success": False, "error": "CSRF/Origin validation failed"}), 403
        if (reauth := security_mod._settings_reauth_required_response()) is not None:
            return reauth
        try:
            with config_write_lock(context_mod.STATE_DIR / "data" / "config.py"):
                return view(*args, **kwargs)
        except ConfigWriteConflictError as error:
            return jsonify({"success": False, "error": str(error)}), 409
        except (ValueError, SyntaxError, UnicodeError) as error:
            return jsonify({"success": False, "error": f"Configuration file could not be parsed: {error}"}), 400
        except (ConfigSyncError, OSError) as error:
            console.print(f"Failed to save configuration safely: {error}", markup=False)
            return jsonify({"success": False, "error": "Unable to save configuration safely. Pending changes are kept; please try again."}), 500

    return guarded


@bp.route("/api/config_set_tracker_overrides", methods=["POST"])
@_config_write_route
def config_set_tracker_overrides():
    """Enable tracker DEFAULT overrides or retain their keys with inherited values."""
    data = _request_json_dict()
    tracker_name = str(data.get("tracker", "")).strip().upper()
    enabled = data.get("enabled")
    if not tracker_name or not isinstance(enabled, bool):
        return jsonify({"success": False, "error": "Invalid tracker override request"}), 400

    example_config = config_store_mod._load_config_from_file(context_mod.CODE_DIR / "data" / "example_config.py") or {}
    example_trackers = _as_dict(example_config.get("TRACKERS")) or {}
    actual_example_name = next(
        (str(name) for name in example_trackers if str(name).upper() == tracker_name),
        None,
    )
    if actual_example_name is None:
        return jsonify({"success": False, "error": "Unknown tracker"}), 404
    example_tracker = _as_dict(example_trackers.get(actual_example_name)) or {}
    override_keys = [key for key in _TRACKER_DEFAULT_OVERRIDE_KEYS if key in example_tracker]
    config_path = context_mod.STATE_DIR / "data" / "config.py"
    original_bytes = config_path.read_bytes()
    source = original_bytes.decode("utf-8")
    user_config = _parse_config_source(source)
    user_trackers = _as_dict(user_config.get("TRACKERS")) or {}
    actual_user_name = next(
        (str(name) for name in user_trackers if str(name).upper() == tracker_name),
        actual_example_name,
    )
    if not enabled:
        saved_tracker = _as_dict(user_trackers.get(actual_user_name)) or {}
        override_keys = [key for key in _TRACKER_DEFAULT_OVERRIDE_KEYS if key in example_tracker or key in saved_tracker]
    if not override_keys:
        return jsonify({"success": False, "error": "This tracker has no DEFAULT override block"}), 400

    try:
        if not isinstance(user_config.get("TRACKERS"), Mapping):
            source = _replace_config_value_in_source(source, ["TRACKERS"], "{}")
        if not isinstance(user_trackers.get(actual_user_name), Mapping):
            source = _replace_config_value_in_source(source, ["TRACKERS", actual_user_name], "{}")
        for key in override_keys:
            source = _replace_config_value_in_source(
                source,
                ["TRACKERS", actual_user_name, key],
                _python_literal(example_tracker[key] if enabled else None),
            )
        replace_config_source(config_path, source, original_bytes)
        try:
            security_mod._write_audit_log(
                "set_tracker_default_overrides",
                ["TRACKERS", actual_user_name],
                None,
                {"enabled": enabled, "keys": override_keys},
                True,
            )
        except Exception as audit_error:
            console.print(f"Failed to write config audit record: {audit_error}", markup=False)
    except ConfigSyncError:
        raise
    except Exception as error:
        console.print(f"Failed to update tracker DEFAULT overrides: {error}", markup=False)
        return jsonify({"success": False, "error": "An error occurred while updating tracker overrides"}), 500

    return jsonify(
        {
            "success": True,
            "tracker": actual_user_name,
            "enabled": enabled,
            "keys": override_keys,
        }
    )


@bp.route("/api/config_update", methods=["POST"])
@_config_write_route
def config_update():
    """Save one field or a batch of field edits after staging every change."""
    data = _request_json_dict()
    is_batch = "updates" in data
    updates = data.get("updates") if is_batch else [data]
    if not _is_obj_list(updates) or not 1 <= len(updates) <= 1000 or not all(_is_str_dict(update) for update in updates):
        return jsonify({"success": False, "error": "Provide between 1 and 1000 configuration updates"}), 400

    config_path = context_mod.STATE_DIR / "data" / "config.py"
    original_bytes = config_path.read_bytes()
    source = original_bytes.decode("utf-8")
    example_config = config_store_mod._load_config_from_file(context_mod.CODE_DIR / "data" / "example_config.py") or {}
    records: list[dict[str, Any]] = []
    try:
        for update in cast(list[dict[str, Any]], updates):
            source, record = config_store_mod._apply_config_update(source, example_config, update)
            records.append(record)
        if any(record["path"][0] == "TRACKERS" and (len(record["path"]) <= 2 or record["path"][2] == "cli_alias") for record in records):
            # Validate the final batch, so two aliases can be swapped together.
            tracker_cli_aliases(_parse_config_source(source))
        # A bad edit anywhere in the batch leaves the original file untouched.
        replace_config_source(config_path, source, original_bytes)
    except (ValueError, TypeError) as error:
        return jsonify({"success": False, "error": str(error)}), 400
    except ConfigSyncError as error:
        _audit_config_updates(records, False, str(error))
        raise
    except Exception as error:
        _audit_config_updates(records, False, str(error))
        return jsonify({"success": False, "error": "An error occurred while updating the configuration"}), 500

    _audit_config_updates(records, True)
    # Echo saved values back without credentials, like /api/config_options.
    values = [_json_safe(config_store_mod._redact_config_value(record["path"], record["value"], None)) for record in records]
    if is_batch:
        return jsonify({"success": True, "values": values})
    return jsonify({"success": True, "value": values[0]})


@bp.route("/api/config_remove_subsection", methods=["POST"])
@_config_write_route
def config_remove_subsection():
    """Remove a subsection (top-level key) from the user's config.py if present"""
    # Require authenticated web session and CSRF protection; disallow bearer/basic API auth
    data = _request_json_dict()
    path_raw = data.get("path", [])
    path: list[str] = []
    if isinstance(path_raw, Sequence) and not isinstance(path_raw, (str, bytes, bytearray)):
        path_items: Sequence[Any] = cast(Sequence[Any], path_raw)
        path.extend(p for p in path_items if isinstance(p, str) and p)

    if not path:
        return jsonify({"success": False, "error": "Invalid path"}), 400

    base_dir = context_mod.STATE_DIR
    config_path = base_dir / "data" / "config.py"
    original_bytes = config_path.read_bytes()
    source = original_bytes.decode("utf-8")

    try:
        updated = _remove_config_key_in_source(source, path)
        if updated == source:
            # Nothing changed
            return jsonify({"success": True, "value": None})
        replace_config_source(config_path, updated, original_bytes)
        return jsonify({"success": True})
    except ConfigSyncError:
        raise
    except Exception:
        return jsonify({"success": False, "error": "An error occurred while removing the configuration subsection"}), 500


@bp.route("/api/config_add_torrent_client", methods=["POST"])
@_config_write_route
def config_add_torrent_client():
    """Create a custom-named torrent client from an example template."""
    data = _request_json_dict()
    client_name = str(data.get("name", "")).strip()
    template_name = str(data.get("template", "")).strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", client_name):
        return jsonify(
            {
                "success": False,
                "error": "Client names may contain letters, numbers, hyphens, and underscores.",
            }
        ), 400

    example_config = config_store_mod._load_config_from_file(context_mod.CODE_DIR / "data" / "example_config.py") or {}
    example_clients = _as_dict(example_config.get("TORRENT_CLIENTS")) or {}
    template = _as_dict(example_clients.get(template_name))
    if not template:
        return jsonify({"success": False, "error": "Unknown torrent client template"}), 400

    config_path = context_mod.STATE_DIR / "data" / "config.py"
    original_bytes = config_path.read_bytes()
    source = original_bytes.decode("utf-8")
    user_config = _parse_config_source(source)
    user_clients = _as_dict(user_config.get("TORRENT_CLIENTS")) or {}
    if client_name.casefold() in {str(name).casefold() for name in user_clients}:
        return jsonify({"success": False, "error": "A client with that name already exists"}), 409

    try:
        if not isinstance(user_config.get("TORRENT_CLIENTS"), Mapping):
            source = _replace_config_value_in_source(source, ["TORRENT_CLIENTS"], "{}")
        updated = _replace_config_value_in_source(
            source,
            ["TORRENT_CLIENTS", client_name],
            _python_literal(dict(template)),
        )
        replace_config_source(config_path, updated, original_bytes)
        try:
            security_mod._write_audit_log(
                "add_subsection",
                ["TORRENT_CLIENTS", client_name],
                None,
                {"template": template_name},
                True,
            )
        except Exception as audit_error:
            console.print(f"Failed to write config audit record: {audit_error}", markup=False)
    except ConfigSyncError:
        raise
    except Exception as error:
        console.print(f"Failed to add torrent client: {error}", markup=False)
        return jsonify({"success": False, "error": "An error occurred while adding the torrent client"}), 500

    return jsonify(
        {
            "success": True,
            "name": client_name,
            "torrent_client": template.get("torrent_client", ""),
        }
    )


@bp.route("/api/config_rename_torrent_client", methods=["POST"])
@_config_write_route
def config_rename_torrent_client():
    """Rename a torrent-client block and its DEFAULT client references."""
    data = _request_json_dict()
    old_name = str(data.get("old_name", "")).strip()
    new_name = str(data.get("new_name", "")).strip()
    if not old_name or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", new_name):
        return jsonify(
            {
                "success": False,
                "error": "Client names may contain letters, numbers, hyphens, and underscores.",
            }
        ), 400
    if old_name.casefold() == new_name.casefold():
        return jsonify({"success": False, "error": "Choose a different client name"}), 400

    config_path = context_mod.STATE_DIR / "data" / "config.py"
    original_bytes = config_path.read_bytes()
    source = original_bytes.decode("utf-8")
    user_config = _parse_config_source(source)
    user_clients = _as_dict(user_config.get("TORRENT_CLIENTS")) or {}
    actual_old_name = next(
        (str(name) for name in user_clients if str(name).casefold() == old_name.casefold()),
        None,
    )
    existing_new_name = next(
        (str(name) for name in user_clients if str(name).casefold() == new_name.casefold()),
        None,
    )

    # Treat a completed earlier attempt as success so Save Config can be retried.
    if actual_old_name is None and existing_new_name is not None:
        return jsonify({"success": True, "old_name": old_name, "new_name": existing_new_name})
    if actual_old_name is None:
        return jsonify({"success": False, "error": "Torrent client not found"}), 404
    if existing_new_name is not None:
        return jsonify({"success": False, "error": "A client with that name already exists"}), 409

    client_config = _as_dict(user_clients.get(actual_old_name))
    if client_config is None:
        return jsonify({"success": False, "error": "Torrent client configuration is invalid"}), 400

    try:
        updated = _replace_config_value_in_source(
            source,
            ["TORRENT_CLIENTS", new_name],
            _python_literal(dict(client_config)),
        )
        updated = _remove_config_key_in_source(updated, ["TORRENT_CLIENTS", actual_old_name])

        default_config = _as_dict(user_config.get("DEFAULT")) or {}
        reference_keys = (
            "default_torrent_client",
            "injecting_client_list",
            "searching_client_list",
        )
        updated_references: list[str] = []
        for key in reference_keys:
            current_value = default_config.get(key)
            next_value: object = current_value
            if isinstance(current_value, str) and current_value.casefold() == actual_old_name.casefold():
                next_value = new_name
            elif _is_obj_list(current_value):
                next_value = [new_name if isinstance(value, str) and value.casefold() == actual_old_name.casefold() else value for value in current_value]
            if next_value != current_value:
                updated = _replace_config_value_in_source(updated, ["DEFAULT", key], _python_literal(next_value))
                updated_references.append(key)

        replace_config_source(config_path, updated, original_bytes)
        try:
            security_mod._write_audit_log(
                "rename_subsection",
                ["TORRENT_CLIENTS", actual_old_name],
                {"name": actual_old_name},
                {"name": new_name},
                True,
            )
        except Exception as audit_error:
            console.print(f"Failed to write config audit record: {audit_error}", markup=False)
    except ConfigSyncError:
        raise
    except Exception as error:
        console.print(f"Failed to rename torrent client: {error}", markup=False)
        return jsonify({"success": False, "error": "An error occurred while renaming the torrent client"}), 500

    return jsonify(
        {
            "success": True,
            "old_name": actual_old_name,
            "new_name": new_name,
            "updated_references": updated_references,
        }
    )


@bp.route("/api/config_test_torrent_client", methods=["POST"])
@limiter.limit("30 per hour", key_func=_rate_limit_key_func)
def config_test_torrent_client():
    """Test a torrent-client draft without saving or mutating it."""
    if not security_mod._is_authenticated():
        return jsonify({"success": False, "error": "Authentication required (web session)"}), 401
    if not security_mod._verify_csrf_header() or not security_mod._verify_same_origin():
        return jsonify({"success": False, "error": "CSRF/Origin validation failed"}), 403
    # These tests send saved credentials to the draft's address.
    if (reauth := security_mod._settings_reauth_required_response()) is not None:
        return reauth

    data = _request_json_dict()
    client_name = str(data.get("name", "")).strip()
    client_config = _as_dict(data.get("config"))
    if not client_name or client_config is None:
        return jsonify({"success": False, "error": "Invalid torrent client configuration"}), 400
    # Saved credentials reach the browser as placeholders; test with the saved values.
    # saved_name covers a client renamed in the editor but not yet saved.
    saved_name = str(data.get("saved_name") or client_name).strip()
    saved_config = config_store_mod._load_config_from_file(context_mod.STATE_DIR / "data" / "config.py") or {}
    saved_clients = _as_dict(saved_config.get("TORRENT_CLIENTS")) or {}
    saved_client = next(
        (value for name, value in saved_clients.items() if str(name).casefold() == saved_name.casefold()),
        None,
    )
    if config_store_mod._contains_redacted(client_config):
        # Saved credentials may only go to the saved address, so an edited
        # address cannot collect them.
        if not config_store_mod._destination_matches(client_config, saved_client, config_store_mod.TORRENT_CLIENT_DESTINATION_KEYS):
            return jsonify(
                {
                    "success": False,
                    "error": "The client address changed. Re-enter its password or API key to test the new address.",
                }
            ), 400
        client_config = config_store_mod._restore_redacted_values(client_config, saved_client)

    destination_defaults = config_store_mod.TORRENT_CLIENT_DESTINATION_DEFAULTS
    client_type = str(client_config.get("torrent_client", "")).strip().lower()
    if client_type not in {"qbit", "rtorrent", "deluge", "transmission", "watch"}:
        return jsonify({"success": False, "error": "Unsupported torrent client type"}), 400

    try:
        message = "Connection successful"
        if client_type == "qbit":
            proxy_url = str(client_config.get("qui_proxy_url", "")).strip()
            verify_certificate = bool(client_config.get("VERIFY_WEBUI_CERTIFICATE", destination_defaults["VERIFY_WEBUI_CERTIFICATE"]))
            version: str | None = None
            proxy_failure = ""
            if proxy_url:
                httpx = flask_compat_mod._dynamic_import("httpx")
                try:
                    response = httpx.get(
                        f"{proxy_url.rstrip('/')}/api/v2/app/version",
                        timeout=10.0,
                        verify=verify_certificate,
                    )
                    response.raise_for_status()
                    version = str(response.text).strip().strip('"')
                except httpx.HTTPError as error:
                    from src.torrent_clients.qbittorrent import has_direct_qbit_auth

                    status_code = getattr(getattr(error, "response", None), "status_code", None)
                    # The uploader treats HTTP 404 as an answer from qBittorrent and does not fall back.
                    if status_code == 404 or not has_direct_qbit_auth(client_config):
                        raise
                    # Report the same fallback the uploader uses, naming the error type only,
                    # since httpx messages can contain the proxy key.
                    proxy_failure = f"HTTP {status_code}" if status_code else type(error).__name__
            if version is None:
                qbittorrentapi = flask_compat_mod._dynamic_import("qbittorrentapi")
                qbit_kwargs: dict[str, object] = {
                    "host": str(client_config.get("qbit_url", "")),
                    "port": str(client_config.get("qbit_port", "")),
                    "VERIFY_WEBUI_CERTIFICATE": verify_certificate,
                    "FORCE_SCHEME_FROM_HOST": True,
                    "REQUESTS_ARGS": {"timeout": 10},
                }
                api_key = str(client_config.get("qbit_api_key", "")).strip()
                if api_key:
                    qbit_kwargs["api_key"] = api_key
                else:
                    qbit_kwargs["username"] = str(client_config.get("qbit_user", ""))
                    qbit_kwargs["password"] = str(client_config.get("qbit_pass", ""))
                qbit_client = qbittorrentapi.Client(**qbit_kwargs)
                if not api_key:
                    qbit_client.auth_log_in()
                version_value = qbit_client.app_version
                if callable(version_value):
                    version_value = version_value()
                version = str(version_value)
            message = f"Connected to qBittorrent {version}" if version else "Connected to qBittorrent"
            if proxy_failure:
                message = f"qui proxy failed ({proxy_failure}); {message} through the WebUI credentials fallback"
        elif client_type == "rtorrent":
            httpx = flask_compat_mod._dynamic_import("httpx")
            xmlrpc_client = flask_compat_mod._dynamic_import("xmlrpc.client")
            rtorrent_url = str(client_config.get("rtorrent_url", "")).strip()
            if not rtorrent_url:
                raise ValueError("Missing rTorrent URL")
            payload = xmlrpc_client.dumps((), methodname="system.client_version")
            response = httpx.post(
                rtorrent_url,
                content=payload,
                headers={"Content-Type": "text/xml"},
                timeout=10.0,
            )
            response.raise_for_status()
            values, _method = xmlrpc_client.loads(response.content)
            version = str(values[0]) if values else ""
            message = f"Connected to rTorrent {version}" if version else "Connected to rTorrent"
        elif client_type == "deluge":
            deluge_client_module = flask_compat_mod._dynamic_import("deluge_client")
            deluge_client = deluge_client_module.DelugeRPCClient(
                str(client_config.get("deluge_url", "")),
                int(client_config.get("deluge_port", 0)),
                str(client_config.get("deluge_user", "")),
                str(client_config.get("deluge_pass", "")),
            )
            deluge_client.connect()
            if not deluge_client.connected:
                raise ConnectionError("Deluge did not accept the connection")
            if hasattr(deluge_client, "disconnect"):
                deluge_client.disconnect()
            message = "Connected to Deluge"
        elif client_type == "transmission":
            transmission_rpc = flask_compat_mod._dynamic_import("transmission_rpc")
            transmission_client = transmission_rpc.Client(
                protocol=str(client_config.get("transmission_protocol", destination_defaults["transmission_protocol"])),
                host=str(client_config.get("transmission_host", "")),
                port=int(client_config.get("transmission_port", 0)),
                username=str(client_config.get("transmission_username", "")),
                password=str(client_config.get("transmission_password", "")),
                path=str(client_config.get("transmission_path", destination_defaults["transmission_path"])),
                timeout=10,
            )
            transmission_client.get_session()
            message = "Connected to Transmission"
        else:
            watch_folder = Path(str(client_config.get("watch_folder", ""))).expanduser()
            if not watch_folder.is_dir():
                return jsonify({"success": False, "error": "Watch folder does not exist or is not a directory"}), 400
            if not os.access(watch_folder, os.W_OK):
                return jsonify({"success": False, "error": "Watch folder is not writable"}), 400
            message = "Watch folder is available and writable"
    except Exception as error:
        error_type = type(error).__name__
        console.print(
            f"Torrent client connection test failed for {client_name} ({client_type}): {error_type}",
            markup=False,
        )
        normalized_error = error_type.casefold()
        if "login" in normalized_error or "auth" in normalized_error:
            error_message = "Authentication failed. Check the configured credentials."
        elif "timeout" in normalized_error:
            error_message = "Connection timed out. Check the address, port, and network access."
        elif "connect" in normalized_error or "connection" in normalized_error:
            error_message = "Unable to reach the client. Check the address, port, and network access."
        elif error_type == "HTTPStatusError":
            status_code = getattr(getattr(error, "response", None), "status_code", None)
            if status_code in {401, 403}:
                error_message = "Authentication failed. Check the configured credentials."
            elif status_code == 404:
                error_message = "The client endpoint was not found. Check the configured URL or path."
            else:
                error_message = f"The client rejected the connection (HTTP {status_code or 'error'})."
        else:
            error_message = f"Connection failed ({error_type})."
        return jsonify({"success": False, "error": error_message}), 400

    return jsonify({"success": True, "message": message})
