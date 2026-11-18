"""Execution preview and review routes (covers, screenshots, MediaInfo, description)."""

import asyncio
import mimetypes
import re
from pathlib import Path

from src.meta import Meta
from web_ui import preview as preview_mod
from web_ui import security as security_mod
from web_ui import session_state as session_state_mod
from web_ui.context import console
from web_ui.extensions import _rate_limit_key_func, limiter
from web_ui.flask_compat import Blueprint, _is_obj_dict, _ResponseLike, jsonify, request, send_file
from web_ui.preview import (
    _execution_preview_cover_url,
    _find_execution_preview,
    _hosted_image_discard_supported,
    _screenshot_capture_supported,
    _screenshot_review_meta,
    _stringify_preview_value,
)
from web_ui.request_utils import _request_json_dict
from web_ui.session_state import active_processes_lock

bp = Blueprint("review", __name__)


@bp.route("/api/execution_preview")
@limiter.limit("7200 per hour", key_func=_rate_limit_key_func, override_defaults=True)
def execution_preview():
    """Return the current media preview for an active execution session."""

    def no_store(response: _ResponseLike) -> _ResponseLike:
        response.headers["Cache-Control"] = "no-store, max-age=0"
        return response

    session_id = str(request.args.get("session_id", "")).strip()
    if not session_id:
        return no_store(jsonify({"success": False, "error": "Missing session_id"})), 400

    preview = _find_execution_preview(session_id)
    if preview is None:
        return no_store(jsonify({"success": False, "error": "Session not found"})), 404

    return no_store(jsonify({"success": True, "media": preview}))


@bp.route("/api/execution_preview_cover")
@limiter.limit("7200 per hour", key_func=_rate_limit_key_func, override_defaults=True)
def execution_preview_cover():
    """Serve a local preview cover image for the active execution session."""
    session_id = str(request.args.get("session_id", "")).strip()
    if not session_id:
        return jsonify({"success": False, "error": "Missing session_id"}), 400

    cover_file = preview_mod._find_execution_preview_cover_file(session_id)
    if cover_file is None:
        return jsonify({"success": False, "error": "Cover not found"}), 404

    mimetype = mimetypes.guess_type(str(cover_file))[0] or "application/octet-stream"
    return send_file(cover_file, mimetype=mimetype, conditional=True, max_age=30)


@bp.route("/api/execution_item_cover")
@limiter.limit("7200 per hour", key_func=_rate_limit_key_func, override_defaults=True)
def execution_item_cover():
    """Serve the local cover of one queue item shown in the Results panel."""
    session_id = str(request.args.get("session_id", "")).strip()
    item = str(request.args.get("item", "")).strip()
    if not session_id or not item.isdecimal():
        return jsonify({"success": False, "error": "Missing session_id or item"}), 400

    with active_processes_lock:
        covers = session_state_mod.active_processes.get(session_id, {}).get("item_covers")
        cover_file = covers.get(int(item)) if _is_obj_dict(covers) else None
    if not isinstance(cover_file, Path) or not cover_file.is_file():
        return jsonify({"success": False, "error": "Cover not found"}), 404

    mimetype = mimetypes.guess_type(str(cover_file))[0] or "application/octet-stream"
    return send_file(cover_file, mimetype=mimetype, conditional=True, max_age=30)


@bp.route("/api/execution_preview_cover/regenerate", methods=["POST"])
@limiter.limit("600 per hour", key_func=_rate_limit_key_func, override_defaults=True)
def regenerate_execution_preview_cover():
    """Regenerate the local XXX preview cover from another video frame."""
    if not security_mod._verify_csrf_header() or not security_mod._verify_same_origin():
        return jsonify({"success": False, "error": "CSRF/Origin validation failed"}), 403

    payload = _request_json_dict()
    session_id = _stringify_preview_value(payload.get("session_id"))
    execution_path, meta_file, meta_data = preview_mod._resolve_execution_preview_meta(session_id)
    if meta_file is None or meta_data is None:
        return jsonify({"success": False, "error": "Execution metadata is not available yet"}), 404
    media_id = _stringify_preview_value(payload.get("media_id"))
    current_media_id = _stringify_preview_value(meta_data.get("uuid")) or execution_path
    if not media_id or media_id != current_media_id:
        return jsonify({"success": False, "error": "The execution preview has moved to another item"}), 409
    if _stringify_preview_value(meta_data.get("category")).upper() != "XXX":
        return jsonify({"success": False, "error": "Cover regeneration is only available for XXX"}), 400

    try:
        from src.takescreens import xxx_fallback_cover

        meta = Meta(dict(meta_data))
        folder_id = meta.uuid or Path(execution_path).name
        cover = asyncio.run(xxx_fallback_cover(list(meta.filelist or []), folder_id, meta.base_dir, meta, random_frame=True))
        if not cover:
            return jsonify({"success": False, "error": "Could not generate a new cover from the source video"}), 422
        cache_key = preview_mod._execution_preview_cover_cache_key(session_id, folder_id)
        return jsonify(
            {
                "success": True,
                "poster_url": _execution_preview_cover_url(session_id, cache_key),
            }
        )
    except (FileNotFoundError, ValueError) as error:
        return jsonify({"success": False, "error": str(error)}), 404
    except Exception as error:
        console.print(f"XXX cover regeneration failed for {session_id}: {error}", markup=False)
        return jsonify({"success": False, "error": "Could not regenerate the XXX cover"}), 500


@bp.route("/api/execution_screenshots")
@limiter.limit("7200 per hour", key_func=_rate_limit_key_func, override_defaults=True)
def execution_screenshots():
    """List local FFmpeg screenshots belonging to the active execution only."""
    session_id = str(request.args.get("session_id", "")).strip()
    if not session_id:
        return jsonify({"success": False, "error": "Missing session_id"}), 400
    resolved = preview_mod._resolve_execution_screenshot_review(session_id)
    if resolved is None:
        return jsonify({"success": False, "error": "Screenshots are not available yet"}), 404

    from src.screenshot_review import ReviewedScreenshot, image_version, list_review_items

    temp_dir, meta_data = resolved
    meta_data = _screenshot_review_meta(temp_dir, meta_data)
    items = list_review_items(temp_dir, meta_data)
    can_capture = _screenshot_capture_supported(meta_data)
    can_discard = _hosted_image_discard_supported(meta_data)

    def image_urls(item: ReviewedScreenshot) -> tuple[str, str]:
        """Return (grid, full-size) URLs; remote hosts expose a lighter ``img_url`` thumbnail."""
        if item.path:
            local_url = f"/api/execution_screenshots/{item.id}/image?session_id={session_id}&v={image_version(temp_dir, item.id, item.path.stat().st_mtime_ns)}"
            return local_url, local_url
        remote = item.remote_image or {}
        img_url = str(remote.get("img_url") or "")
        raw_url = str(remote.get("raw_url") or "")
        return img_url or raw_url, raw_url or img_url

    return jsonify(
        {
            "success": True,
            # Additions to hosted images do not need a local frame, even after every hosted image was discarded.
            "can_add": (bool(items) or bool(meta_data.get("image_list"))) and can_capture,
            "screenshots": [
                {
                    "id": item.id,
                    "filename": item.path.name if item.path else f"Remote image {item.index + 1}",
                    "size": item.path.stat().st_size if item.path else None,
                    "source": item.source,
                    "group": item.group,
                    "image_url": urls[0],
                    "full_image_url": urls[1],
                    "can_replace": can_capture and item.source != "addition",
                    "can_delete": item.source in {"local", "addition"} or can_discard,
                }
                for item in items
                for urls in (image_urls(item),)
            ],
        }
    )


@bp.route("/api/execution_mediainfo")
@limiter.limit("7200 per hour", key_func=_rate_limit_key_func, override_defaults=True)
def execution_mediainfo():
    """Return read-only MediaInfo/BDInfo reports for the active execution only."""
    session_id = str(request.args.get("session_id", "")).strip()
    if not session_id:
        return jsonify({"success": False, "error": "Missing session_id"}), 400
    resolved = preview_mod._resolve_execution_screenshot_review(session_id)
    if resolved is None:
        return jsonify({"success": False, "error": "MediaInfo is not available yet"}), 404

    from src.mediainfo_review import report_items

    temp_dir, meta_data = resolved
    kind, reports = report_items(meta_data, temp_dir)
    if not reports:
        return jsonify({"success": False, "kind": kind, "error": "MediaInfo is not available yet"}), 404
    response = jsonify({"success": True, "kind": kind, "reports": reports})
    response.headers["Cache-Control"] = "no-store, max-age=0"
    return response


@bp.route("/api/execution_description")
@limiter.limit("7200 per hour", key_func=_rate_limit_key_func, override_defaults=True)
def execution_description():
    """Return the editable base-description draft and its read-only sources."""
    session_id = str(request.args.get("session_id", "")).strip()
    resolved = preview_mod._resolve_execution_description_review(session_id)
    if resolved is None:
        return jsonify({"success": False, "error": "Description is not available yet"}), 404
    from src.description_review import draft, source_items

    temp_dir, _meta_file, meta_data = resolved
    content, version = draft(meta_data, temp_dir)
    return jsonify(
        {
            "success": True,
            # The item this draft belongs to; the editor drops a draft for an
            # item other than the one it shows.
            "media_id": _stringify_preview_value(meta_data.get("uuid")),
            "content": content,
            "version": version,
            "sources": source_items(meta_data),
        }
    )


def _description_item_error(payload: dict[str, object], meta_data: dict[str, object]) -> tuple[_ResponseLike, int] | None:
    """Refuse a description write made for a queue item that is no longer current."""
    requested_item = _stringify_preview_value(payload.get("media_id"))
    if not requested_item:
        return jsonify({"success": False, "error": "Description item is required"}), 400
    # The description panel exists only for items with a release UUID, which is
    # the media_id /api/execution_preview reports for them.
    if requested_item != _stringify_preview_value(meta_data.get("uuid")):
        return jsonify({"success": False, "error": "The upload moved on to another item"}), 409
    return None


@bp.route("/api/execution_description", methods=["PUT"])
@limiter.limit("600 per hour", key_func=_rate_limit_key_func, override_defaults=True)
def save_execution_description():
    """Persist an edited draft for the current execution with optimistic locking."""
    if not security_mod._verify_csrf_header() or not security_mod._verify_same_origin():
        return jsonify({"success": False, "error": "CSRF/Origin validation failed"}), 403
    payload = _request_json_dict()
    session_id = _stringify_preview_value(payload.get("session_id"))
    content = payload.get("content")
    if not isinstance(content, str):
        return jsonify({"success": False, "error": "Description content must be text"}), 400
    if len(content) > 1_000_000:
        return jsonify({"success": False, "error": "Description exceeds the 1,000,000-character limit"}), 413
    resolved = preview_mod._resolve_execution_description_review(session_id)
    if resolved is None:
        return jsonify({"success": False, "error": "Description is not available yet"}), 404

    from src.description_review import ReviewConflictError, save_review

    requested_version = payload.get("version")
    if not isinstance(requested_version, int):
        return jsonify({"success": False, "error": "Description version is required"}), 400

    temp_dir, _meta_file, meta_data = resolved
    item_error = _description_item_error(payload, meta_data)
    if item_error is not None:
        return item_error
    try:
        # save_review holds the execution's file lock while it checks the version and
        # writes, so the compare-and-swap also covers the upload process's own writes.
        saved = save_review(temp_dir, content, expected_version=requested_version)
    except ReviewConflictError as conflict:
        return jsonify({"success": False, "error": "Description changed in another browser tab", "version": conflict.current_version}), 409
    except TimeoutError:
        return jsonify({"success": False, "error": "Description is being updated, try again"}), 503
    return jsonify({"success": True, "content": content, "version": saved["version"]})


@bp.route("/api/execution_description/reset", methods=["POST"])
@limiter.limit("600 per hour", key_func=_rate_limit_key_func, override_defaults=True)
def reset_execution_description():
    """Restore the draft from one of the read-only sources."""
    if not security_mod._verify_csrf_header() or not security_mod._verify_same_origin():
        return jsonify({"success": False, "error": "CSRF/Origin validation failed"}), 403
    payload = _request_json_dict()
    session_id = _stringify_preview_value(payload.get("session_id"))
    source_key = _stringify_preview_value(payload.get("source_key"))
    resolved = preview_mod._resolve_execution_description_review(session_id)
    if resolved is None:
        return jsonify({"success": False, "error": "Description is not available yet"}), 404
    requested_version = payload.get("version")
    if not isinstance(requested_version, int):
        return jsonify({"success": False, "error": "Description version is required"}), 400

    from src.description_review import ReviewConflictError, save_review, source_items

    temp_dir, _meta_file, meta_data = resolved
    item_error = _description_item_error(payload, meta_data)
    if item_error is not None:
        return item_error
    source = next((item for item in source_items(meta_data) if item["key"] == source_key), None)
    if source is None:
        return jsonify({"success": False, "error": "Description source was not found"}), 404
    content = source["content"]
    try:
        saved = save_review(temp_dir, content, expected_version=requested_version)
    except ReviewConflictError as conflict:
        return jsonify({"success": False, "error": "Description changed in another browser tab", "version": conflict.current_version}), 409
    except TimeoutError:
        return jsonify({"success": False, "error": "Description is being updated, try again"}), 503
    return jsonify({"success": True, "content": content, "version": saved["version"]})


@bp.route("/api/execution_screenshots/<screenshot_id>/image")
@limiter.limit("7200 per hour", key_func=_rate_limit_key_func, override_defaults=True)
def execution_screenshot_image(screenshot_id: str):
    """Serve one reviewed local screenshot after resolving it through its session."""
    session_id = str(request.args.get("session_id", "")).strip()
    resolved = preview_mod._resolve_execution_screenshot_review(session_id)
    if resolved is None:
        return jsonify({"success": False, "error": "Screenshots are not available yet"}), 404
    from src.screenshot_review import list_review_items

    temp_dir, meta_data = resolved
    meta_data = _screenshot_review_meta(temp_dir, meta_data)
    screenshot = next((item for item in list_review_items(temp_dir, meta_data) if item.id == screenshot_id), None)
    if screenshot is None or screenshot.path is None:
        return jsonify({"success": False, "error": "Screenshot not found"}), 404
    response = send_file(screenshot.path, mimetype="image/png", conditional=True, max_age=0)
    response.headers["Cache-Control"] = "no-store, max-age=0"
    return response


@bp.route("/api/execution_screenshots/add", methods=["POST"])
@limiter.limit("600 per hour", key_func=_rate_limit_key_func, override_defaults=True)
def add_execution_screenshot():
    """Capture one extra local screenshot for the active execution."""
    if not security_mod._verify_csrf_header() or not security_mod._verify_same_origin():
        return jsonify({"success": False, "error": "CSRF/Origin validation failed"}), 403
    payload = _request_json_dict()
    session_id = _stringify_preview_value(payload.get("session_id"))
    group = _stringify_preview_value(payload.get("group")) or "main"
    resolved = preview_mod._resolve_execution_screenshot_review(session_id)
    if resolved is None:
        return jsonify({"success": False, "error": "Screenshots are not available yet"}), 404
    temp_dir, meta_data = resolved
    meta_data = _screenshot_review_meta(temp_dir, meta_data)
    if not _screenshot_capture_supported(meta_data):
        return jsonify({"success": False, "error": "Screenshot capture is not supported for this release"}), 400

    try:
        from src.screenshot_review import add_screenshot

        asyncio.run(add_screenshot(temp_dir, meta_data, group))
    except (FileNotFoundError, ValueError) as error:
        return jsonify({"success": False, "error": str(error)}), 404
    except Exception as error:
        console.print(f"Screenshot add failed for {session_id}: {error}", markup=False)
        return jsonify({"success": False, "error": "Could not add screenshot"}), 500
    return jsonify({"success": True})


@bp.route("/api/execution_screenshots/<screenshot_id>/<action>", methods=["POST"])
@limiter.limit("600 per hour", key_func=_rate_limit_key_func, override_defaults=True)
def mutate_execution_screenshot(screenshot_id: str, action: str):
    """Delete or replace a reviewed frame with CSRF and same-origin protection."""
    if action not in {"delete", "replace", "undo"}:
        return jsonify({"success": False, "error": "Unsupported screenshot action"}), 404
    if not security_mod._verify_csrf_header() or not security_mod._verify_same_origin():
        return jsonify({"success": False, "error": "CSRF/Origin validation failed"}), 403
    payload = _request_json_dict()
    session_id = _stringify_preview_value(payload.get("session_id"))
    resolved = preview_mod._resolve_execution_screenshot_review(session_id)
    if resolved is None:
        return jsonify({"success": False, "error": "Screenshots are not available yet"}), 404
    temp_dir, meta_data = resolved
    meta_data = _screenshot_review_meta(temp_dir, meta_data)
    if action == "replace" and not _screenshot_capture_supported(meta_data):
        return jsonify({"success": False, "error": "Screenshot capture is not supported for this release"}), 400
    if action == "delete" and re.fullmatch(r"remote-\d+", screenshot_id) and not _hosted_image_discard_supported(meta_data):
        return jsonify({"success": False, "error": "Hosted images cannot be discarded for this release"}), 400

    try:
        from src.screenshot_review import delete_screenshot, replace_screenshot, undo_remote_replacement

        if action == "delete":
            delete_screenshot(temp_dir, meta_data, screenshot_id)
        elif action == "undo":
            undo_remote_replacement(temp_dir, screenshot_id)
        else:
            asyncio.run(replace_screenshot(temp_dir, meta_data, screenshot_id))
    except (FileNotFoundError, ValueError) as error:
        return jsonify({"success": False, "error": str(error)}), 404
    except Exception as error:
        console.print(f"Screenshot {action} failed for {session_id}: {error}", markup=False)
        return jsonify({"success": False, "error": f"Could not {action} screenshot"}), 500

    return jsonify({"success": True})
