"""Config file parsing, editing and Web UI config sections."""

import ast
import json
import math
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal, TypedDict, cast

from web_ui import context as context_mod
from web_ui import security as security_mod
from web_ui.context import console
from web_ui.flask_compat import _is_obj_dict, _is_obj_list, _is_obj_sequence
from web_ui.request_utils import _as_dict
from web_ui.security import _json_safe
from web_ui.tracker_info import _TRACKER_DEFAULT_OVERRIDE_KEYS


class ConfigItem(TypedDict, total=False):
    key: str
    value: object
    example_value: object
    source: Literal["config", "example"]
    children: list[ConfigItem]
    help: list[str]
    subsection: str | bool
    override_fields: list[ConfigItem]
    field_type: str
    field_min: int


class ConfigSection(TypedDict, total=False):
    section: str
    items: list[ConfigItem]
    client_types: list[str]


def _parse_config_source(source: str) -> dict[str, Any]:
    """Read literal configuration without executing Python from the file."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        config_node: ast.expr | None = None
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "config":
                    config_node = node.value
                    break
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "config":
            config_node = node.value

        if config_node is not None:
            config_value = ast.literal_eval(config_node)
            if isinstance(config_value, dict):
                config_value_dict = cast(dict[Any, Any], config_value)
                return {str(key): value for key, value in config_value_dict.items()}
    raise ValueError("Config assignment not found")


def _load_config_from_file(path: Path) -> dict[str, Any] | None:
    """Load and return the ``config`` dict from a Python config file.

    Only files inside the repository or runtime ``data/`` directories with a
    ``.py`` extension are accepted.  No ownership or permission checks are
    performed — the file lives in a user-controlled directory and the app
    already writes to it freely via ``config_update``.

    Returns None on error (file missing, invalid path, parse error, or no valid
    config dict).  Returns {} for a valid file that defines config = {}.
    """
    if not path.exists():
        return None

    # Preserve support for Python files beneath the repository data directory
    # while also accepting files beneath the user-owned runtime data directory.
    allowed_data_dirs = {
        (context_mod.CODE_DIR / "data").resolve(),
        (context_mod.STATE_DIR / "data").resolve(),
    }
    try:
        resolved_path = path.resolve()
        if path.suffix != ".py" or not any(resolved_path.is_relative_to(directory) for directory in allowed_data_dirs):
            return None
    except Exception:
        return None

    try:
        with Path(path).open(encoding="utf-8") as f:
            content = f.read()
        return _parse_config_source(content)
    except Exception as exc:
        console.print(f"[yellow]Failed to parse config file {path.name}: {exc}[/yellow]")
        return None


def _get_nested_value(data: Any, path: list[str]) -> Any:
    current: Any = data
    for key in path:
        if not isinstance(current, dict):
            return None
        current_dict = _as_dict(current)
        if current_dict is None:
            return None
        current = current_dict.get(key)
    return current


def _coerce_config_value(raw: Any, example_value: Any) -> Any:
    if isinstance(example_value, bool):
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, str):
            return raw.strip().lower() in {"1", "true", "yes", "y", "on"}
        return bool(raw)

    if isinstance(example_value, int) and not isinstance(example_value, bool):
        if isinstance(raw, (int, float)):
            return int(raw)
        if isinstance(raw, str) and raw.strip():
            return int(raw.strip())
        return 0

    if isinstance(example_value, float):
        if isinstance(raw, (int, float)):
            return float(raw)
        if isinstance(raw, str) and raw.strip():
            return float(raw.strip())
        return 0.0

    if example_value is None:
        if isinstance(raw, str) and raw.strip().lower() in {"", "none", "null"}:
            return None
        return raw

    if isinstance(example_value, (list, dict)):
        if isinstance(raw, list):
            return cast(list[Any], raw)
        if isinstance(raw, dict):
            return cast(dict[str, Any], raw)
        if isinstance(raw, str):
            raw_str = raw.strip()
            if not raw_str:
                return [] if isinstance(example_value, list) else {}
            try:
                loaded: Any = json.loads(raw_str)
                return loaded
            except json.JSONDecodeError:
                return raw
        return raw

    if isinstance(raw, str):
        return raw

    return str(raw)


def _python_literal(value: object) -> str:
    if isinstance(value, str):
        return repr(value)
    if value is None:
        return "None"
    if isinstance(value, bool):
        return "True" if value else "False"
    return repr(value)


def _format_config_tree(tree: ast.AST) -> str:
    """Format an AST tree in the same style as example_config.py"""
    lines: list[str] = []

    # Cast to Module to access body attribute
    if not isinstance(tree, ast.Module):
        return ast.unparse(tree)

    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "config":
                    if isinstance(node.value, ast.Dict):
                        lines.append("config = {")
                        lines.extend(_format_dict(node.value, 1))
                        lines.append("}")
                    else:
                        lines.append(ast.unparse(node))
                    break
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "config":
            if isinstance(node.value, ast.Dict):
                lines.append(f"config: {ast.unparse(node.annotation)} = {{")
                lines.extend(_format_dict(node.value, 1))
                lines.append("}")
            else:
                lines.append(ast.unparse(node))
        else:
            # Keep other statements as-is
            lines.append(ast.unparse(node))

    return "\n".join(lines)


def _format_dict(dict_node: ast.Dict, indent_level: int) -> list[str]:
    """Format a dictionary node with proper indentation"""
    lines: list[str] = []
    indent = "    " * indent_level

    for _i, (key_node, value_node) in enumerate(zip(dict_node.keys, dict_node.values, strict=False)):
        key_str = repr(key_node.value) if isinstance(key_node, ast.Constant) and isinstance(key_node.value, str) else ast.unparse(key_node) if key_node is not None else "None"

        if isinstance(value_node, ast.Dict):
            lines.append(f"{indent}{key_str}: {{")
            lines.extend(_format_dict(value_node, indent_level + 1))
            lines.append(f"{indent}}},")
        else:
            value_str = ast.unparse(value_node)
            lines.append(f"{indent}{key_str}: {value_str},")

    return lines


def _replace_config_value_in_source(source: str, key_path: list[str], new_value: str) -> str:
    tree = ast.parse(source)
    config_assign: ast.Assign | ast.AnnAssign | None = None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "config":
                    config_assign = node
                    break
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "config":
            config_assign = node
        if config_assign:
            break

    if config_assign is None or not isinstance(config_assign.value, ast.Dict):
        raise ValueError("Config assignment not found")

    current_dict = config_assign.value
    target_node: ast.AST | None = None

    for i, key in enumerate(key_path):
        found = False
        for k_node, v_node in zip(current_dict.keys, current_dict.values, strict=False):
            if isinstance(k_node, ast.Constant) and isinstance(k_node.value, str) and k_node.value == key:
                if isinstance(v_node, ast.Dict):
                    if i < len(key_path) - 1:  # Not the final key
                        current_dict = v_node
                        found = True
                        break
                    # Final key - update existing value
                    target_node = v_node
                    found = True
                    break
                target_node = v_node
                found = True
                break

        if not found:
            if i == len(key_path) - 1:  # Final key doesn't exist - need to add it
                # Add new key-value pair to current_dict
                new_key_node = ast.Constant(value=key)
                new_value_node = ast.parse(new_value, mode="eval").body

                current_dict.keys.append(new_key_node)
                current_dict.values.append(new_value_node)

                # Reconstruct the source with the new key using proper formatting
                return _format_config_tree(tree)
            # Sparse user configs may omit an entire example-backed section.
            # Build its parents in the staged AST, without replacing scalars.
            new_dict_node = ast.Dict(keys=[], values=[])
            current_dict.keys.append(ast.Constant(value=key))
            current_dict.values.append(new_dict_node)
            current_dict = new_dict_node
            continue

        if target_node is not None and i < len(key_path) - 1:
            raise ValueError("Invalid path for config update")

    if target_node is None:
        raise ValueError("Target node not found")

    if not hasattr(target_node, "lineno") or not hasattr(target_node, "end_lineno"):
        raise ValueError("Unable to locate config value position")

    lineno = cast(int | None, getattr(target_node, "lineno", None))
    end_lineno = cast(int | None, getattr(target_node, "end_lineno", None))
    col_offset = cast(int, getattr(target_node, "col_offset", 0))
    end_col_offset = cast(int, getattr(target_node, "end_col_offset", 0))
    if lineno is None or end_lineno is None:
        raise ValueError("Unable to locate config value position")

    lines = source.splitlines(keepends=True)
    start = sum(len(line) for line in lines[: lineno - 1]) + col_offset
    end = sum(len(line) for line in lines[: end_lineno - 1]) + end_col_offset

    updated_source = f"{source[:start]}{new_value}{source[end:]}"

    # Reformat the entire config to ensure consistent styling
    updated_tree = ast.parse(updated_source)
    return _format_config_tree(updated_tree)


def _remove_config_key_in_source(source: str, key_path: list[str]) -> str:
    """Remove a key from the config source if it exists"""
    tree = ast.parse(source)
    config_assign: ast.Assign | ast.AnnAssign | None = None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "config":
                    config_assign = node
                    break
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "config":
            config_assign = node
        if config_assign:
            break

    if config_assign is None or not isinstance(config_assign.value, ast.Dict):
        return source  # No config found, return as-is

    current_dict = config_assign.value

    for i, key in enumerate(key_path):
        found = False
        for j, (k_node, v_node) in enumerate(zip(current_dict.keys, current_dict.values, strict=False)):
            if isinstance(k_node, ast.Constant) and isinstance(k_node.value, str) and k_node.value == key:
                if isinstance(v_node, ast.Dict):
                    if i < len(key_path) - 1:  # Not the final key
                        current_dict = v_node
                        found = True
                        break
                    # Final key - remove it
                    # Remove the key-value pair
                    del current_dict.keys[j]
                    del current_dict.values[j]
                    # Reconstruct the source
                    return _format_config_tree(tree)
                if i == len(key_path) - 1:  # Final key - remove it
                    del current_dict.keys[j]
                    del current_dict.values[j]
                    return _format_config_tree(tree)
                found = True
                break

        if not found:
            return source  # Key not found, return as-is

    return source  # Should not reach here


_RELEASE_GROUP_OVERRIDE_FIELDS = (
    "custom_description_header",
    "screenshot_header",
    "disc_menu_header",
    "audio_spectrogram_header",
    "dynamic_hdr_plot_header",
    "tonemapped_header",
    "custom_signature",
)
_RELEASE_GROUP_BOOL_FIELDS = (
    "episode_overview",
    "add_logo",
    "full_mediainfo",
    "add_bluray_link",
    "use_bluray_images",
    "add_audio_spectrogram",
    "add_dynamic_hdr_plot",
    "hide_screenshot_header_if_only_section",
)
_RELEASE_GROUP_INT_FIELDS = (
    "thumbnail_size",
    "screens_per_row",
    "logo_size",
    "bluray_image_size",
    "pack_thumb_size",
    "multiScreens",
)

_RELEASE_GROUP_IMAGE_SIZE_FIELDS = {"thumbnail_size", "pack_thumb_size", "logo_size", "bluray_image_size"}


def _is_release_group_override_path(path: list[str]) -> bool:
    """Identify the complete DEFAULT or tracker-specific release-group mapping."""
    return path == ["DEFAULT", "tag_overrides"] or (len(path) == 3 and path[0] == "TRACKERS" and path[2] == "tag_overrides")


def _validate_release_group_overrides(value: object) -> None:
    """Reject malformed maps and names that collide under description matching."""
    if not _is_obj_dict(value):
        raise ValueError("Release group overrides must be a dictionary.")
    seen: set[str] = set()
    for name, fields in value.items():
        if not isinstance(name, str) or not name.strip().lstrip("-") or any(ord(char) < 32 for char in name):
            raise ValueError("Each release group needs a non-empty name without control characters.")
        normalized_name = name.strip().lstrip("-").casefold()
        if normalized_name in seen:
            raise ValueError(f"Duplicate release group: {name}. Names are matched without case or leading hyphens.")
        seen.add(normalized_name)
        if not _is_obj_dict(fields):
            raise ValueError(f"Overrides for {name} must be a dictionary.")
        for field, field_val in fields.items():
            if not isinstance(field, str) or not field:
                raise ValueError(f"Overrides for {name} need non-empty field names.")
            if field_val is None:
                continue
            if field in _RELEASE_GROUP_BOOL_FIELDS:
                if isinstance(field_val, bool) or (isinstance(field_val, str) and field_val.strip().lower() in ("true", "false", "1", "0", "yes", "no", "on", "off")):
                    continue
                raise ValueError(f"{field} for {name} must be a boolean or null.")
            if field in _RELEASE_GROUP_INT_FIELDS:
                minimum = 1 if field in _RELEASE_GROUP_IMAGE_SIZE_FIELDS else 0
                try:
                    if isinstance(field_val, bool) or not isinstance(field_val, (str, int)) or int(field_val) < minimum:
                        raise ValueError
                except ValueError, TypeError:
                    raise ValueError(f"{field} for {name} must be an integer of at least {minimum}, or null.") from None
                continue
            if not isinstance(field_val, str):
                raise ValueError(f"Overrides for {name} must contain text fields or null values.")


REDACTED_PLACEHOLDER = "<REDACTED>"
# Keep in sync with sensitiveKeyPattern in web_ui/static/js/config_app.js.
_SENSITIVE_CONFIG_KEY_PATTERN = re.compile(
    r"(api|username|password|announce_url|rss_key|passkey|qui_proxy_url|userhash|secret|token|client_id|login_answer|rtorrent_url|^cookies$)",
    re.IGNORECASE,
)


def _is_sensitive_config_path(path: list[str]) -> bool:
    """Return True when the config field at ``path`` holds a credential."""
    if not path:
        return False
    key = path[-1]
    if _SENSITIVE_CONFIG_KEY_PATTERN.search(key):
        return True
    return "TORRENT_CLIENTS" in path and re.search(r"(user|pass)", key, re.IGNORECASE) is not None


def _redact_config_value(path: list[str], value: Any, example_value: Any) -> Any:
    """Hide a saved credential before it is sent to the browser.

    Values equal to the public example (placeholders) stay visible so the UI can
    still tell an unconfigured field from a configured one.
    """
    if not isinstance(value, str) or not value.strip() or value == example_value:
        return value
    return REDACTED_PLACEHOLDER if _is_sensitive_config_path(path) else value


# Draft fields that decide where a torrent-client test sends saved credentials.
TORRENT_CLIENT_DESTINATION_KEYS = (
    "torrent_client",
    "qbit_url",
    "qbit_port",
    "deluge_url",
    "deluge_port",
    "transmission_protocol",
    "transmission_host",
    "transmission_port",
    "transmission_path",
    "VERIFY_WEBUI_CERTIFICATE",
)


# Values the connection test uses when a destination field is missing.
TORRENT_CLIENT_DESTINATION_DEFAULTS: dict[str, Any] = {
    "transmission_protocol": "http",
    "transmission_path": "/transmission/rpc",
    "VERIFY_WEBUI_CERTIFICATE": True,
}


def _contains_redacted(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(_contains_redacted(item) for item in cast(Mapping[str, Any], value).values())
    return value == REDACTED_PLACEHOLDER


def _same_destination_value(draft: Any, saved: Any, *, boolean: bool = False) -> bool:
    """Compare a draft destination field with its saved value, ignoring surrounding whitespace.

    Case and trailing slashes are kept: URL paths are case- and slash-sensitive
    and a reverse proxy may route them to different services.
    """
    if boolean:
        return isinstance(draft, bool) and draft == (True if saved is None else saved)
    if isinstance(draft, bool) or isinstance(saved, bool):
        # A JSON true must not match a saved port such as 9091.
        return False
    return _normalize_destination(draft) == _normalize_destination(saved)


def _normalize_destination(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _destination_matches(draft: Mapping[str, Any], saved: Any, keys: tuple[str, ...]) -> bool:
    """Return True when the draft would contact the same place as the saved config.

    Missing fields resolve to the connection test's defaults on both sides, so
    omitting a field cannot silently change the destination.
    """
    saved_dict = _as_dict(saved)
    if saved_dict is None:
        return False
    for key in keys:
        default = TORRENT_CLIENT_DESTINATION_DEFAULTS.get(key)
        # A placeholder in a destination field never matches, so it cannot skip the check.
        if not _same_destination_value(draft.get(key, default), saved_dict.get(key, default), boolean=key == "VERIFY_WEBUI_CERTIFICATE"):
            return False
    return True


def _find_redacted_sensitive_path(path: list[str], value: Any) -> list[str] | None:
    """Return the first sensitive path under ``value`` that holds the placeholder."""
    if isinstance(value, Mapping):
        for key, child in cast(Mapping[str, Any], value).items():
            found = _find_redacted_sensitive_path([*path, str(key)], child)
            if found is not None:
                return found
        return None
    return path if value == REDACTED_PLACEHOLDER and _is_sensitive_config_path(path) else None


def _restore_redacted_values(draft: Any, saved: Any) -> Any:
    """Replace ``<REDACTED>`` placeholders in a draft with the saved values."""
    if isinstance(draft, Mapping):
        saved_dict = _as_dict(saved) or {}
        draft_dict = cast(Mapping[str, Any], draft)
        return {key: _restore_redacted_values(value, saved_dict.get(key)) for key, value in draft_dict.items()}
    if draft == REDACTED_PLACEHOLDER:
        return saved if isinstance(saved, str) else ""
    return draft


def _build_config_items(
    example_section: dict[str, Any],
    user_section: dict[str, Any],
    comments_map: dict[str, list[str]],
    subsection_map: dict[str, str],
    path: list[str],
) -> list[ConfigItem]:
    items: list[ConfigItem] = []
    user_dict: dict[str, Any] = _as_dict(user_section) or {}

    if path == ["DEFAULT"]:
        from src.screenshot_overlays import OVERLAY_KEYS, overlay_enabled, overlay_options

        # Resolve old combined settings and individual-only configurations using
        # the same rules as capture. Reading settings never rewrites the config.
        if "frame_overlay" in user_dict or any(key in user_dict for key in OVERLAY_KEYS):
            user_dict = {**user_dict, **overlay_options(user_dict), "frame_overlay": overlay_enabled(user_dict)}

    merged_keys: list[str] = [str(key) for key in example_section]
    if user_dict:
        merged_keys.extend([str(key) for key in user_dict if key not in example_section])
    if len(path) == 2 and path[0] == "TRACKERS" and "tag_overrides" not in merged_keys:
        merged_keys.append("tag_overrides")

    current_subsection: str | None = None
    subsection_items: list[ConfigItem] = []

    def flush_subsection() -> None:
        nonlocal subsection_items, current_subsection
        if current_subsection and subsection_items:
            items.append(
                {
                    "key": current_subsection,
                    "children": subsection_items,
                    "source": "example",
                    "help": [],
                    "subsection": True,
                }
            )
        subsection_items = []

    for key in merged_keys:
        # Legacy configs can retain removed settings after default synchronization.
        if path == ["DEFAULT"] and key in {"keep_meta", "dvd_mediainfo_path"}:
            continue
        example_value = example_section.get(key)
        user_value = user_dict.get(key)
        key_path = [*path, key]
        help_text = comments_map.get("/".join(key_path), [])
        subsection_label = subsection_map.get("/".join(key_path))
        if subsection_label != current_subsection:
            flush_subsection()
            current_subsection = subsection_label
        if _is_release_group_override_path(key_path):
            # Example group names are documentation, not inherited user entries.
            item: ConfigItem = {
                "key": key,
                "value": _json_safe(user_value if key in user_dict else {}),
                "example_value": {},
                "source": "config" if key in user_dict else "example",
                "children": [],
                "help": help_text or comments_map.get("DEFAULT/tag_overrides", []),
                "override_fields": [
                    {
                        "key": field,
                        "field_type": field_type,
                        "field_min": 1 if field in _RELEASE_GROUP_IMAGE_SIZE_FIELDS else 0,
                        "help": comments_map.get(f"DEFAULT/{field}", []),
                    }
                    for fields, field_type in (
                        (_RELEASE_GROUP_OVERRIDE_FIELDS, "text"),
                        (_RELEASE_GROUP_BOOL_FIELDS, "boolean"),
                        (_RELEASE_GROUP_INT_FIELDS, "number"),
                    )
                    for field in fields
                ],
            }
        elif isinstance(example_value, Mapping) or isinstance(user_value, Mapping):
            example_value = _as_dict(example_value) or {}
            user_value = _as_dict(user_value) or {}
            children = _build_config_items(example_value, user_value, comments_map, subsection_map, key_path)
            source: Literal["config", "example"] = "config" if key in user_dict else "example"
            item = {
                "key": key,
                "source": source,
                "children": children,
                "help": help_text,
            }
        else:
            if key in user_dict:
                value = user_value
                source = "config"
            else:
                value = example_value
                source = "example"
            item = {
                "key": key,
                "value": _json_safe(_redact_config_value(key_path, value, example_value)),
                "example_value": _json_safe(example_value),
                "source": source,
                "help": help_text,
            }

        if current_subsection:
            subsection_items.append(item)
        else:
            items.append(item)

    flush_subsection()

    return items


def _prepare_default_webui_section(
    example_section: dict[str, Any],
    comments_map: dict[str, list[str]],
    subsection_map: dict[str, str],
) -> dict[str, Any]:
    """Arrange the DEFAULT section for the Config page: add optional fields and group related settings."""
    client_list_defaults: tuple[tuple[str, list[str], list[str]], ...] = (
        (
            "injecting_client_list",
            [],
            [
                "Clients used for injection (adding uploaded torrents for seeding).",
                "If omitted or empty, injection uses default_torrent_client.",
                'Example: ["qbittorrent", "rtorrent"]',
            ],
        ),
        (
            "searching_client_list",
            [],
            [
                "Clients searched for existing torrents.",
                "If omitted or empty, searching uses default_torrent_client.",
                'Example: ["qbittorrent", "qbittorrent_searching"]',
            ],
        ),
    )
    arr_optional_fields: dict[str, tuple[tuple[str, list[str]], ...]] = {
        "sonarr_api_key": tuple(
            (
                field_key,
                [
                    f"Settings for Sonarr instance {instance_number}.",
                    "Optional; instances are queried in numeric order.",
                ],
            )
            for instance_number in (2, 3, 4)
            for field_key in (
                f"sonarr_url_{instance_number - 1}",
                f"sonarr_api_key_{instance_number - 1}",
            )
        ),
        "radarr_api_key": tuple(
            (
                field_key,
                [
                    f"Settings for Radarr instance {instance_number}.",
                    "Optional; instances are queried in numeric order.",
                ],
            )
            for instance_number in (2, 3, 4)
            for field_key in (
                f"radarr_url_{instance_number - 1}",
                f"radarr_api_key_{instance_number - 1}",
            )
        ),
    }

    prepared: dict[str, Any] = {}
    inserted_client_lists = False
    for key, value in example_section.items():
        prepared[key] = value
        if key == "default_torrent_client":
            for client_key, default_value, help_text in client_list_defaults:
                prepared[client_key] = default_value
                comments_map.setdefault(f"DEFAULT/{client_key}", help_text)
                subsection_map[f"DEFAULT/{client_key}"] = "CLIENT SELECTION"
            inserted_client_lists = True
        for field_key, help_text in arr_optional_fields.get(key, ()):
            prepared[field_key] = ""
            comments_map.setdefault(f"DEFAULT/{field_key}", help_text)
            subsection_map[f"DEFAULT/{field_key}"] = "ARR INTEGRATION"

    if not inserted_client_lists:
        for client_key, default_value, help_text in client_list_defaults:
            prepared[client_key] = default_value
            comments_map.setdefault(f"DEFAULT/{client_key}", help_text)
            subsection_map[f"DEFAULT/{client_key}"] = "CLIENT SELECTION"

    if "stats_enabled" in prepared or "history_enabled" in prepared:
        # Group statistics and history with Main Settings only for WebUI presentation.
        # Keep the fields together so the builder emits a single subsection.
        for local_data_key in ("stats_enabled", "history_enabled", "history_retention_days"):
            if local_data_key in prepared:
                subsection_map[f"DEFAULT/{local_data_key}"] = "MAIN SETTINGS"
        main_settings = {key: value for key, value in prepared.items() if subsection_map.get(f"DEFAULT/{key}") == "MAIN SETTINGS"}
        prepared = {**main_settings, **prepared}

    # Keep WebUI-only options together for presentation while saving their
    # values at the original DEFAULT paths used by the upload session manager.
    webui_settings = {key: value for key, value in prepared.items() if key.startswith("webui_")}
    for key in webui_settings:
        subsection_map[f"DEFAULT/{key}"] = "WEBUI SETTINGS"
    main_settings = {key: value for key, value in prepared.items() if subsection_map.get(f"DEFAULT/{key}") == "MAIN SETTINGS"}
    other_settings = {key: value for key, value in prepared.items() if key not in main_settings and key not in webui_settings}
    return {**main_settings, **webui_settings, **other_settings}


def _torrent_client_template(
    example_clients: Mapping[str, Any],
    client_type: str,
) -> tuple[str, dict[str, Any]] | None:
    """Return the preferred example template for a torrent client type."""
    matches: list[tuple[str, dict[str, Any]]] = []
    for template_name, template_value in example_clients.items():
        template = _as_dict(template_value)
        if template and str(template.get("torrent_client", "")).lower() == client_type.lower():
            matches.append((str(template_name), template))
    if not matches:
        return None
    matches.sort(key=lambda match: (match[0] != "qbittorrent", match[0]))
    return matches[0]


def _prepare_torrent_client_webui_section(
    example_section: dict[str, Any],
    user_section: Mapping[str, Any],
    comments_map: dict[str, list[str]],
) -> dict[str, Any]:
    """Add example-backed metadata for custom-named torrent clients."""
    prepared = dict(example_section)
    for client_name, client_value in user_section.items():
        if client_name in prepared:
            continue
        client_config = _as_dict(client_value)
        if not client_config:
            continue
        match = _torrent_client_template(
            example_section,
            str(client_config.get("torrent_client", "")),
        )
        if match is None:
            continue
        template_name, template = match
        prepared[str(client_name)] = dict(template)
        for field_name in template:
            source_path = f"TORRENT_CLIENTS/{template_name}/{field_name}"
            target_path = f"TORRENT_CLIENTS/{client_name}/{field_name}"
            if source_path in comments_map:
                comments_map[target_path] = list(comments_map[source_path])
    return prepared


def _extract_example_metadata(example_path: Path) -> tuple[dict[str, list[str]], dict[str, str]]:
    if not example_path.exists():
        return {}, {}

    source = example_path.read_text(encoding="utf-8")
    lines = source.splitlines()
    tree = ast.parse(source)

    config_assign: ast.Assign | ast.AnnAssign | None = None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "config":
                    config_assign = node
                    break
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "config":
            config_assign = node
        if config_assign:
            break

    if config_assign is None or not isinstance(config_assign.value, ast.Dict):
        return {}, {}

    comment_map: dict[str, list[str]] = {}
    subsection_map: dict[str, str] = {}

    def delimited_header_title(line: str) -> str | None:
        match = re.fullmatch(r"#\s*---\s*(.+?)\s*---\s*", line.strip())
        if not match:
            return None
        title = match.group(1).strip()
        return title if any(char.isalpha() for char in title) else None

    def collect_comments(lineno: int) -> list[str]:
        idx = lineno - 2
        comments: list[str] = []
        while idx >= 0:
            line = lines[idx]
            stripped = line.strip()
            if not stripped:
                if comments:
                    break
                idx -= 1
                continue
            if delimited_header_title(stripped):
                break
            if stripped.startswith("#"):
                comments.insert(0, stripped.lstrip("#").strip())
                idx -= 1
                continue
            break
        return comments

    def find_headers(
        start_line: int,
        end_line: int,
        child_ranges: list[tuple[int, int]],
    ) -> list[tuple[int, str]]:
        headers: list[tuple[int, str]] = []
        for idx in range(start_line - 1, end_line):
            if idx <= 0 or idx + 1 >= len(lines):
                continue
            stripped = lines[idx].strip()
            if not stripped.startswith("#"):
                continue
            title = stripped.lstrip("#").strip()
            if not title:
                continue
            delimited_title = delimited_header_title(stripped)
            if delimited_title:
                title = delimited_title
            else:
                if title != title.upper():
                    continue
                if not any(char.isalpha() for char in title):
                    continue
                if lines[idx - 1].strip() or lines[idx + 1].strip():
                    continue
            line_no = idx + 1
            if any(start <= line_no <= end for start, end in child_ranges):
                continue
            headers.append((line_no, title))
        return headers

    def walk_dict(node: ast.Dict, path: list[str]) -> None:
        key_entries: list[tuple[str, int, ast.AST]] = []
        child_ranges: list[tuple[int, int]] = []
        for key_node, value_node in zip(node.keys, node.values, strict=False):
            if not isinstance(key_node, ast.Constant) or not isinstance(key_node.value, str):
                continue
            key = key_node.value
            lineno = getattr(key_node, "lineno", None)
            if isinstance(lineno, int):
                comment_map["/".join([*path, key])] = collect_comments(lineno)
                key_entries.append((key, lineno, value_node))

            if isinstance(value_node, ast.Dict):
                start = getattr(value_node, "lineno", None)
                end = getattr(value_node, "end_lineno", None)
                if isinstance(start, int) and isinstance(end, int):
                    child_ranges.append((start, end))

            if isinstance(value_node, ast.Dict):
                walk_dict(value_node, [*path, key])

        start_line = getattr(node, "lineno", None)
        end_line = getattr(node, "end_lineno", None)
        if isinstance(start_line, int) and isinstance(end_line, int) and key_entries:
            headers = sorted(find_headers(start_line, end_line, child_ranges), key=lambda h: h[0])
            key_entries.sort(key=lambda entry: entry[1])
            header_idx = 0
            current_header: str | None = None
            for key, lineno, _ in key_entries:
                while header_idx < len(headers) and headers[header_idx][0] < lineno:
                    current_header = headers[header_idx][1]
                    header_idx += 1
                if current_header:
                    subsection_map["/".join([*path, key])] = current_header

    walk_dict(config_assign.value, [])
    return comment_map, subsection_map


def _configured_torrent_client_names(
    user_config: Mapping[str, Any],
    example_config: Mapping[str, Any],
) -> list[str]:
    """Return user-created, edited, or actively referenced torrent clients."""
    user_clients = _as_dict(user_config.get("TORRENT_CLIENTS")) or {}
    example_clients = _as_dict(example_config.get("TORRENT_CLIENTS")) or {}
    example_by_name = {str(name).casefold(): _as_dict(value) or {} for name, value in example_clients.items()}

    referenced: set[str] = set()
    default_section = _as_dict(user_config.get("DEFAULT")) or {}
    for key in ("default_torrent_client", "injecting_client_list", "searching_client_list"):
        value = default_section.get(key)
        if isinstance(value, str):
            referenced.update(name.strip().casefold() for name in value.split(",") if name.strip())
        elif _is_obj_sequence(value):
            referenced.update(str(name).strip().casefold() for name in value if str(name).strip())

    configured: list[str] = []
    for name, value in user_clients.items():
        client_name = str(name)
        normalized_name = client_name.casefold()
        client_config = _as_dict(value) or {}
        example_client = example_by_name.get(normalized_name)
        if example_client is None or client_config != example_client or normalized_name in referenced:
            configured.append(client_name)

    return sorted(configured, key=str.casefold)


def _apply_config_update(source: str, example_config: dict[str, Any], data: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Validate and stage one edit without writing any changes to disk."""
    prior_config = _parse_config_source(source)
    path_raw = data.get("path", [])
    path: list[str] = []
    if _is_obj_list(path_raw) and all(isinstance(part, str) and part for part in path_raw):
        path = [str(part) for part in path_raw]
    raw_value = data.get("value")

    if not path:
        raise ValueError("Invalid path")
    example_value = _get_nested_value(example_config, path)

    if example_value is None and len(path) >= 3 and path[0] == "TORRENT_CLIENTS":
        user_client = _get_nested_value(prior_config, path[:2])
        example_clients = _as_dict(example_config.get("TORRENT_CLIENTS")) or {}
        user_client_config = _as_dict(user_client)
        if user_client_config:
            match = _torrent_client_template(
                example_clients,
                str(user_client_config.get("torrent_client", "")),
            )
            if match is not None:
                _template_name, template = match
                example_value = _get_nested_value(template, path[2:])

    # Special handling for WebUI-managed fields that don't exist in example config.
    key = path[-1] if path else ""
    is_optional_arr_field = len(path) == 2 and path[0] == "DEFAULT" and re.fullmatch(r"(?:sonarr|radarr)_(?:url|api_key)_[1-3]", key) is not None
    force_remove_optional_arr_field = is_optional_arr_field and data.get("remove") is True
    is_tracker_default_override = len(path) == 3 and path[0] == "TRACKERS" and key in _TRACKER_DEFAULT_OVERRIDE_KEYS
    # Retain an explicit inheritance marker so startup sync cannot restore an
    # example override. Accept removal requests from older WebUI tabs as well.
    inherit_tracker_override = is_tracker_default_override and (raw_value is None or data.get("remove") is True)
    if is_tracker_default_override and example_value is None and isinstance(_get_nested_value(example_config, path[:2]), Mapping):
        # Existing overrides may outlive a field's entry in the tracker template.
        # Keep those displayed fields editable/inheritable without adding new ones.
        saved_tracker = _as_dict(_get_nested_value(prior_config, path[:2])) or {}
        if key in saved_tracker:
            example_value = _get_nested_value(example_config, ["DEFAULT", key])
            if example_value is None:
                example_value = saved_tracker[key] if saved_tracker[key] is not None else ""
    is_release_group_override = _is_release_group_override_path(path)
    if is_release_group_override:
        if not isinstance(_get_nested_value(example_config, path[:-1]), Mapping):
            raise ValueError("Unknown release group override scope")
        example_value = {}
    elif key in ["injecting_client_list", "searching_client_list"]:
        example_value = []  # Default to empty list
    elif is_optional_arr_field:
        example_value = ""
    elif example_value is None:
        raise ValueError("Path not found in example config")

    is_webui_prompt_timeout = path == ["DEFAULT", "webui_unattended_prompt_timeout"]
    if is_webui_prompt_timeout:
        if isinstance(raw_value, bool) or not isinstance(raw_value, (str, int, float)) or (isinstance(raw_value, str) and not raw_value.strip()):
            raise ValueError("Enter a timeout in minutes, or 0 to wait indefinitely")
        # The runtime accepts fractional minutes even though the example is 60.
        example_value = 60.0
    coerced_value = None if inherit_tracker_override else _coerce_config_value(raw_value, example_value)
    # The browser only ever sees the placeholder; never persist it, including
    # inside a whole-section update.
    redacted_path = _find_redacted_sensitive_path(path, coerced_value)
    if redacted_path is not None:
        raise ValueError(f"Refusing to save the redacted placeholder for {'/'.join(redacted_path)}; re-enter the value")
    if len(path) == 2 and path[0] == "TRACKERS" and coerced_value == {} and isinstance(example_value, Mapping):
        saved_trackers = _as_dict(prior_config.get("TRACKERS")) or {}
        if path[1].casefold() not in {str(name).casefold() for name in saved_trackers}:
            # Startup sync never fills tracker blocks, so persist the template
            # values the WebUI displays. DEFAULT overrides remain inherited.
            example_tracker: dict[str, Any] = _as_dict(example_value) or {}
            coerced_value = {
                name: value
                for name, value in example_tracker.items()
                if name not in _TRACKER_DEFAULT_OVERRIDE_KEYS and name != "tag_overrides" and not isinstance(value, Mapping)
            }
    if is_webui_prompt_timeout and (not isinstance(coerced_value, (int, float)) or not math.isfinite(coerced_value) or coerced_value < 0):
        raise ValueError("Unattended prompt timeout must be a finite number of minutes greater than or equal to 0")
    overlay_choices = {"overlay_position": {"left", "right"}, "overlay_layout": {"stacked", "single_line"}}
    if path[:1] == ["DEFAULT"] and len(path) == 2 and key in overlay_choices and (not isinstance(coerced_value, str) or coerced_value not in overlay_choices[key]):
        raise ValueError(f"Invalid {key} value")
    if is_release_group_override:
        _validate_release_group_overrides(coerced_value)
    new_value_literal = _python_literal(coerced_value)

    # Keep optional WebUI-managed values out of config.py when they are unused.
    # Tracker overrides instead retain None to inherit subsequent DEFAULT changes.
    key = path[-1] if path else ""
    should_remove_empty_value = (key in ["injecting_client_list", "searching_client_list"] and coerced_value == []) or (
        is_optional_arr_field and (coerced_value == "" or force_remove_optional_arr_field)
    )
    prior_value = _get_nested_value(prior_config, path)
    if should_remove_empty_value:
        updated_source = _remove_config_key_in_source(source, path)
    else:
        if len(path) == 2 and path[0] == "DEFAULT":
            from src.screenshot_overlays import OVERLAY_KEYS, overlay_enabled, overlay_options

            prior_defaults = _as_dict(prior_config.get("DEFAULT")) or {}
            if key == "frame_overlay":
                # Freeze legacy label preferences before changing the master so
                # switching off and back on restores exactly the same selections.
                for overlay_key, selected in overlay_options(prior_defaults).items():
                    if overlay_key not in prior_defaults:
                        source = _replace_config_value_in_source(source, ["DEFAULT", overlay_key], _python_literal(selected))
            elif key in OVERLAY_KEYS and "frame_overlay" not in prior_defaults:
                # Editing labels must preserve the master state shown in the UI,
                # including configs that have never saved an explicit master.
                source = _replace_config_value_in_source(source, ["DEFAULT", "frame_overlay"], _python_literal(overlay_enabled(prior_defaults)))
        updated_source = _replace_config_value_in_source(source, path, new_value_literal)
    return updated_source, {
        "path": path,
        "value": coerced_value,
        "prior_value": prior_value,
        "action": "remove_key" if should_remove_empty_value else "update_value",
    }


def _audit_config_updates(records: list[dict[str, Any]], success: bool, error: str | None = None) -> None:
    for record in records:
        try:
            security_mod._write_audit_log(
                record["action"],
                record["path"],
                record["prior_value"],
                None if record["action"] == "remove_key" else record["value"],
                success,
                error,
            )
        except Exception as audit_error:
            console.print(f"Failed to write config audit record: {audit_error}", markup=False)
