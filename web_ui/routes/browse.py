"""File browser routes."""

import os
import stat
import sys
import traceback
from pathlib import Path

from web_ui import paths as paths_mod
from web_ui import security as security_mod
from web_ui.context import console
from web_ui.extensions import _rate_limit_key_func, limiter
from web_ui.flask_compat import Blueprint, jsonify, request
from web_ui.paths import _BROWSE_SEARCH_SEP_RE, SUPPORTED_DESC_EXTS, BrowseItem, _resolve_browse_path
from web_ui.security import _token_is_valid

bp = Blueprint("browse", __name__)


@bp.route("/api/browse_roots")
@limiter.exempt
def browse_roots():
    """Return configured browse roots"""
    roots = paths_mod._get_browse_roots()
    if not roots:
        return jsonify({"error": "Browsing is not configured", "success": False}), 400

    # First pass: collect all display names to detect duplicates
    name_to_roots: dict[str, list[str]] = {}
    for root in roots:
        display_name = Path(root.rstrip(os.sep)).name or root
        if display_name not in name_to_roots:
            name_to_roots[display_name] = []
        name_to_roots[display_name].append(root)

    # Second pass: build items with subtitles when needed
    items: list[BrowseItem] = []
    for root in roots:
        display_name = Path(root.rstrip(os.sep)).name or root
        try:
            stat_res = Path(root).stat()
            mtime = stat_res.st_mtime
            size = 0
        except Exception:
            mtime = 0.0
            size = 0
        item: BrowseItem = {
            "name": display_name,
            "path": root,
            "type": "folder",
            "children": [],
            "mtime": mtime,
            "size": size,
        }

        # Add subtitle if multiple roots share the same folder name
        if len(name_to_roots.get(display_name, [])) > 1:
            # Show parent path or drive letter
            parent = str(Path(root.rstrip(os.sep)).parent)
            if parent:
                # On Windows, show drive letter + parent; on Unix, show parent path
                item["subtitle"] = parent
            else:
                # Fallback to full path if no parent (e.g., drive root)
                item["subtitle"] = root

        items.append(item)

    # If caller used a bearer token, require it to be valid.
    bearer = security_mod._get_bearer_from_header()
    if bearer and not _token_is_valid(bearer):
        return jsonify({"success": False, "error": "Forbidden (invalid token)"}), 403

    return jsonify({"items": items, "success": True})


@bp.route("/api/browse")
@limiter.limit("600 per minute", key_func=_rate_limit_key_func, override_defaults=True)
def browse_path():
    """Browse filesystem paths"""
    requested: str = str(request.args.get("path", ""))
    file_filter: str = str(request.args.get("filter", "video"))  # 'video' or 'desc'
    try:
        path = _resolve_browse_path(requested)
    except ValueError as e:
        # Log details server-side, but avoid leaking paths/internal details to clients.
        console.print(f"Path resolution error for requested {requested!r}: {e}", markup=False)
        return jsonify({"error": "Invalid path specified", "success": False}), 400

    # Explicitly assert the resolved path is within allowed browse roots.
    try:
        paths_mod._assert_safe_resolved_path(path)
    except ValueError:
        console.print(f"Path failed safety check: {requested!r}", markup=False)
        return jsonify({"error": "Invalid path specified", "success": False}), 400

    # Defensive sanity checks before using `path` in filesystem operations.
    safe_path = str(Path(path).resolve())
    if "\x00" in safe_path:
        console.print("Path contains invalid characters", markup=False)
        return jsonify({"error": "Invalid path specified", "success": False}), 400
    # codeql[py/path-injection]
    if not Path(safe_path).is_dir():
        console.print("Requested path is not a directory", markup=False)
        return jsonify({"error": "Invalid path specified", "success": False}), 400

    console.print("Browsing path allowed", markup=False)

    try:
        items: list[BrowseItem] = []
        try:
            # `safe_path` was computed above; perform an explicit realpath
            # containment check using stdlib functions so static analyzers
            # can reason about the safety of the listing operation.
            real_safe = os.path.realpath(safe_path)
            allowed = False
            for root in paths_mod._get_browse_roots():
                root_real = os.path.realpath(str(Path(root).resolve()))
                try:
                    if os.path.commonpath([real_safe, root_real]) == root_real:
                        allowed = True
                        break
                except ValueError:
                    # Different drives on Windows - not allowed
                    continue
            if not allowed:
                console.print(f"Path failed containment check before listing: {safe_path!r}", markup=False)
                return jsonify({"error": "Invalid path specified", "success": False}), 400

            # codeql[py/path-injection]
            with os.scandir(safe_path) as entries:
                directory_entries = sorted(entries, key=lambda entry: entry.name)
            for entry in directory_entries:
                item = entry.name
                full_path = Path(safe_path) / item
                if paths_mod._is_hidden_browse_entry(entry):
                    continue
                try:
                    # Ordinary entries returned by scandir are direct children of
                    # the validated parent. Resolve links and all Windows reparse
                    # points (including junctions) before exposing their targets.
                    # Use one no-follow snapshot for both classification and
                    # displayed metadata. DirEntry's cached type can predate a
                    # replacement, so it must not trigger a later following stat.
                    stat_res = entry.stat(follow_symlinks=False)
                    attributes = getattr(stat_res, "st_file_attributes", 0)
                    is_link = stat.S_ISLNK(stat_res.st_mode) or bool(attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)
                    is_dir = stat.S_ISDIR(stat_res.st_mode)
                    if is_link:
                        # Directory symlinks remain expandable, but size/mtime
                        # below always describe the link itself, never its target.
                        is_dir = bool(attributes & stat.FILE_ATTRIBUTE_DIRECTORY) if sys.platform == "win32" else entry.is_dir()
                        try:
                            paths_mod._assert_safe_resolved_path(full_path)
                        except ValueError:
                            continue

                    # Keep description browsing limited to known text-ish files.
                    # Default browsing should expose any file inside allowed roots
                    # so books, games, ISOs, and other upload types are visible.
                    if not is_dir and file_filter == "desc":
                        ext = Path(item.lower()).suffix
                        if ext not in SUPPORTED_DESC_EXTS:
                            continue

                    mtime = stat_res.st_mtime
                    size = stat_res.st_size if not is_dir else 0

                    items.append(
                        {
                            "name": item,
                            "path": str(full_path),
                            "type": "folder" if is_dir else "file",
                            "children": [] if is_dir else None,
                            "mtime": mtime,
                            "size": size,
                        }
                    )
                except PermissionError, OSError:
                    continue

            console.print(f"Found {len(items)} items in {path}", markup=False)

        except PermissionError:
            console.print(f"Error: Permission denied: {path}", markup=False)
            return jsonify({"error": "Permission denied", "success": False}), 403

        # If caller used a bearer token, require it to be valid. Valid bearer
        # tokens are allowed without CSRF since they are intended for programmatic
        # access. Otherwise require an authenticated web session + CSRF + same-origin.
        bearer = security_mod._get_bearer_from_header()
        if bearer:
            if not _token_is_valid(bearer):
                return jsonify({"success": False, "error": "Forbidden (invalid token)"}), 403
        else:
            # Require session-based callers to be authenticated and provide CSRF + Origin
            if not security_mod._is_authenticated():
                return jsonify({"success": False, "error": "Authentication required (web session)"}), 401
            if not security_mod._verify_csrf_header() or not security_mod._verify_same_origin():
                return jsonify({"success": False, "error": "CSRF/Origin validation failed"}), 403

        return jsonify({"items": items, "success": True, "path": path, "count": len(items)})

    except Exception as e:
        console.print(f"Error browsing {path}: {e}", markup=False)
        console.print(traceback.format_exc(), markup=False)
        return jsonify({"error": "Error browsing path", "success": False}), 500


@bp.route("/api/browse_search")
@limiter.limit("60 per minute", key_func=_rate_limit_key_func, override_defaults=True)
def browse_search():
    """Search filesystem for files/folders matching a query string"""
    query = (request.args.get("q") or "").strip()
    file_filter: str = request.args.get("filter", "video")
    try:
        max_results = min(int(request.args.get("max_results", "100")), 500)
        if max_results < 1:
            max_results = 100
    except ValueError, TypeError:
        max_results = 100

    if not query:
        return jsonify({"success": True, "items": [], "query": ""})

    bearer = security_mod._get_bearer_from_header()
    if bearer:
        if not _token_is_valid(bearer):
            return jsonify({"success": False, "error": "Forbidden (invalid token)"}), 403
    else:
        if not security_mod._is_authenticated():
            return jsonify({"success": False, "error": "Authentication required (web session)"}), 401
        if not security_mod._verify_csrf_header() or not security_mod._verify_same_origin():
            return jsonify({"success": False, "error": "CSRF/Origin validation failed"}), 403

    roots = paths_mod._get_browse_roots()
    if not roots:
        return jsonify({"success": False, "error": "Browsing is not configured"}), 400

    # A supplied scope must never silently fall back to all configured roots.
    if "path" in request.args:
        if len(request.args.getlist("path")) != 1 or not request.args["path"].strip():
            return jsonify({"success": False, "error": "Select a folder to search"}), 400
        try:
            # The tree only hands out absolute paths; never join a relative
            # scope onto a default root.
            if not Path(request.args["path"]).is_absolute():
                raise ValueError("Search scope must be absolute")
            # Keep the selected path inside the configured roots before
            # resolving links. Its target may live in a different allowed root.
            lexical_scope = Path(os.path.abspath(request.args["path"]))  # noqa: PTH100
            if not any(lexical_scope.is_relative_to(root) for root in roots):
                raise ValueError("Scope is outside browse roots")
            # Validate the target with the shared resolver, without changing
            # the stricter lexical-root policy used by other browse/upload APIs.
            scope = Path(_resolve_browse_path(str(lexical_scope.resolve())))
            roots = [str(scope)]
            # Surface an unavailable/unreadable explicit selection instead of
            # returning a misleading empty successful search.
            with os.scandir(scope):
                pass
        except ValueError, OSError:
            return jsonify({"success": False, "error": "Search folder is unavailable or not allowed"}), 400

    # Split on common separators
    query_tokens = [t for t in _BROWSE_SEARCH_SEP_RE.split(query.lower()) if t]
    if not query_tokens:
        return jsonify({"success": True, "items": [], "query": query})

    def name_matches(name: str) -> bool:
        """Check if query tokens appear as whole-word ordered subsequence in the name."""
        name_tokens = [t for t in _BROWSE_SEARCH_SEP_RE.split(name.lower()) if t]
        pos = 0
        for qt in query_tokens:
            found = False
            while pos < len(name_tokens):
                if name_tokens[pos] == qt:
                    pos += 1
                    found = True
                    break
                pos += 1
            if not found:
                return False
        return True

    items: list[BrowseItem] = []
    files: list[BrowseItem] = []
    seen: set[str] = set()
    # Directories walked after the result list filled up; folders found
    # there may still displace files, but only within a bounded budget.
    dirs_after_full = 0
    budget_spent = False

    try:
        for root in roots:
            root_abs = str(Path(root).resolve())
            if not Path(root_abs).is_dir():
                continue
            try:
                for dirpath, dirnames, filenames in os.walk(root_abs, followlinks=False):
                    if len(items) + len(files) >= max_results:
                        dirs_after_full += 1

                    # Prune system/hidden directories before os.walk enters them.
                    visible = [d for d in dirnames if not paths_mod._is_hidden_browse_entry(Path(dirpath) / d)]
                    # os.walk never descends symlinks; prune Windows junctions
                    # too so every walked folder lives under the root. Linked
                    # folders still match below, as the tree lists them.
                    dirnames[:] = [d for d in visible if not (Path(dirpath) / d).is_junction()]

                    # Check dirs
                    for dirname in visible:
                        if name_matches(dirname):
                            full_path = Path(dirpath) / dirname
                            try:
                                paths_mod._assert_safe_resolved_path(full_path)
                            except ValueError:
                                continue
                            try:
                                stat_res = Path(full_path).stat()
                                mtime = stat_res.st_mtime
                                size = 0
                            except Exception:
                                mtime = 0.0
                                size = 0
                            if str(full_path) in seen:
                                continue
                            seen.add(str(full_path))
                            items.append(
                                {
                                    "name": dirname,
                                    "path": str(full_path),
                                    "type": "folder",
                                    "children": [],
                                    "mtime": mtime,
                                    "size": size,
                                }
                            )
                            if len(items) >= max_results:
                                break

                    if len(items) >= max_results:
                        break

                    # Keep only bounded provisional files; later folders take
                    # their places before the response is truncated.
                    for filename in filenames:
                        if len(files) >= max_results:
                            break
                        if not name_matches(filename):
                            continue
                        if paths_mod._is_hidden_browse_entry(Path(dirpath) / filename):
                            continue
                        if file_filter == "desc":
                            ext = Path(filename.lower()).suffix
                            if ext not in SUPPORTED_DESC_EXTS:
                                continue
                        full_path = Path(dirpath) / filename
                        try:
                            paths_mod._assert_safe_resolved_path(full_path)
                        except ValueError:
                            continue
                        try:
                            stat_res = Path(full_path).stat()
                            mtime = stat_res.st_mtime
                            size = stat_res.st_size
                        except Exception:
                            mtime = 0.0
                            size = 0
                        if str(full_path) in seen:
                            continue
                        seen.add(str(full_path))
                        files.append(
                            {
                                "name": filename,
                                "path": str(full_path),
                                "type": "file",
                                "children": None,
                                "mtime": mtime,
                                "size": size,
                            }
                        )
                    # os.walk scans before yielding; stop here rather than
                    # asking it to enumerate the first over-budget directory.
                    if len(items) + len(files) >= max_results and dirs_after_full >= paths_mod._BROWSE_SEARCH_FOLDER_SCAN_DIRS:
                        budget_spent = True
                        break
            except PermissionError:
                continue
            except Exception as e:
                console.print(f"Error searching in {root}: {e}", markup=False)
                continue

            if len(items) >= max_results or budget_spent:
                break

        items.extend(files[: max_results - len(items)])
        # Sort the selected folders/files alphabetically within each group.
        items.sort(key=lambda x: (0 if x.get("type") == "folder" else 1, (x.get("name") or "").lower()))

        return jsonify({"success": True, "items": items, "query": query, "count": len(items), "truncated": len(items) >= max_results})

    except Exception as e:
        console.print(f"Error in browse_search: {e}", markup=False)
        console.print(traceback.format_exc(), markup=False)
        return jsonify({"error": "Error searching files", "success": False}), 500
