"""Keep an existing user configuration compatible with the bundled schema."""

import ast
import copy
import pprint
import re
import shutil
import sys
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CONFIG_SCHEMA_VERSION = 1
SCHEMA_VERSION_KEY = "config_schema_version"

# Legacy tracker acronyms written by older Upload Assistant releases.
TRACKER_ALIASES = {
    "AR": "ALPHARATIO",
    "ASC": "AMIGOSSHARE",
    "ANT": "ANTHELION",
    "AZ": "AVISTAZ",
    "BHD": "BEYONDHD",
    "CZ": "CINEMAZ",
    "BHDTV": "BITHDTV",
    "BJS": "BJSHARE",
    "PHD": "PRIVATEHD",
    "BT": "BRASILTRACKER",
    "DC": "DIGITALCORE",
    "FL": "FILELIST",
    "FF": "FUNFILE",
    "GPW": "GREATPOSTERWALL",
    "HDB": "HDBITS",
    "HDS": "HDSPACE",
    "HDT": "HDTORRENTS",
    "IS": "IMMORTALSEED",
    "IPT": "IPTORRENTS",
    "MKO": "MAKINGOFF",
    "MTV": "MORETHANTV",
    "NBL": "NEBULANCE",
    "LPT": "LONGPT",
    "PTER": "PTERCLUB",
    "PTCAFE": "PTCAFE",
    "PTFANS": "PTFANS",
    "PTS": "PTSKIT",
    "PTGTK": "PTGTK",
    "RPT": "RAILGUNPT",
    "RTF": "RETROFLIX",
    "RMC": "RETROMOVIESCLUB",
    "SPD": "SPEEDAPP",
    "SN": "SWARMAZON",
    "TTG": "TOTHEGLORY",
    "THR": "TORRENTHR",
    "TL": "TORRENTLEECH",
    "TVC": "TVCHAOSUK",
    "ACM": "ASIANCINEMA",
    "A4K": "AURA4K",
    "CRP": "CURUPIRA",
    "DS": "DRUNKENSLUG",
    "BLU": "BLUTOPIA",
    "CBR": "CAPYBARABR",
    "TIK": "CINEMATIK",
    "DP": "DARKPEERS",
    "EMUW": "EMUWAREZ",
    "HUNO": "HAWKEUNO",
    "HHD": "HOMIEHELPDESK",
    "IHD": "INFINITYHD",
    "ITT": "ITATORRENTS",
    "LT": "LATTEAM",
    "LCD": "LOCADORA",
    "LUME": "LUMINARR",
    "MS": "MIDNIGHTSCENE",
    "OTW": "OLDTOONSWORLD",
    "OE": "ONLYENCODES",
    "PTT": "POLISHTORRENT",
    "PT": "PORTUGAS",
    "R4E": "RACING4EVERYONE",
    "RAS": "RASTASTUGAN",
    "RF": "REELFLIX",
    "SAM": "SAMARITANO",
    "SP": "SEEDPOOL",
    "SHRI": "SHAREISLAND",
    "STC": "SKIPTHECOMMERCIALS",
    "LDU": "LASTDIGITALUNDERGROUND",
    "TOS": "THEOLDSCHOOL",
    "TLZ": "THELEACHZONE",
    "DT": "DESITORRENTS",
    "TTR": "TORRENTEROS",
    "UTP": "UTOPIA",
    "YUS": "YUSCENE",
    "ZNTH": "ZENITH",
    "SUIO": "SUIO",
    "UNIT3D_TEMPLATE": "UNIT3DTEMPLATE",
}

ConfigDict = dict[str, Any]


def ensure_config_exists(config_path: Path, example_path: Path) -> bool:
    """Create the initial user config from the bundled example when needed."""
    if config_path.exists() or not example_path.exists():
        return False
    config_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(example_path, config_path)
    return True


def _read_config_literal(path: Path) -> tuple[ConfigDict, ast.Dict, str] | None:
    """Read the literal assigned to ``config`` without executing user code."""
    try:
        source = path.read_text(encoding="utf-8")
    except OSError:
        return None
    return _read_config_literal_source(source, str(path))


def _read_config_literal_source(source: str, filename: str = "config.py") -> tuple[ConfigDict, ast.Dict, str] | None:
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError:
        return None

    for node in tree.body:
        value: ast.expr | None = None
        is_config_assignment = isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "config" for target in node.targets)
        is_config_annotation = isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "config"
        if is_config_assignment or is_config_annotation:
            value = node.value
        if not isinstance(value, ast.Dict):
            continue
        try:
            config = ast.literal_eval(value)
        except ValueError, SyntaxError:
            return None
        if isinstance(config, dict):
            return config, value, source
    return None


def _dict_nodes(node: ast.Dict, path: tuple[str, ...] = ()) -> dict[tuple[str, ...], ast.Dict]:
    result = {path: node}
    for key, value in zip(node.keys, node.values, strict=False):
        if isinstance(key, ast.Constant) and isinstance(key.value, str) and isinstance(value, ast.Dict):
            result.update(_dict_nodes(value, (*path, key.value)))
    return result


def _apply_source_edits(source: str, edits: list[tuple[int, int, str]]) -> str:
    for start, end, replacement in sorted(edits, reverse=True):
        source = source[:start] + replacement + source[end:]
    return source


def _line_offsets(lines: list[str]) -> list[int]:
    offsets: list[int] = []
    offset = 0
    for line in lines:
        offsets.append(offset)
        offset += len(line)
    return offsets


def _offset(lines: list[str], line: int, column: int, offsets: list[int] | None = None) -> int:
    """Convert AST UTF-8 byte columns to Python string offsets."""
    offsets = offsets or _line_offsets(lines)
    prefix = lines[line - 1].encode("utf-8")[:column].decode("utf-8")
    return offsets[line - 1] + len(prefix)


def _migrate_tracker_aliases(source: str, config_node: ast.Dict, config: ConfigDict) -> tuple[str, list[str]]:
    """Rename unambiguous legacy tracker aliases without overwriting settings."""
    nodes = _dict_nodes(config_node)
    edits: list[tuple[int, int, str]] = []
    migrated: list[str] = []
    lines = source.splitlines(keepends=True)
    trackers = config.get("TRACKERS")
    tracker_node = nodes.get(("TRACKERS",))
    if isinstance(trackers, Mapping) and tracker_node:
        for key_node in tracker_node.keys:
            if not isinstance(key_node, ast.Constant) or not isinstance(key_node.value, str):
                continue
            old_name = key_node.value
            new_name = TRACKER_ALIASES.get(old_name.upper())
            if new_name and new_name not in trackers:
                start = _offset(lines, key_node.lineno, key_node.col_offset)
                end = _offset(lines, key_node.end_lineno, key_node.end_col_offset)
                edits.append((start, end, repr(new_name)))
                migrated.append(f"TRACKERS.{old_name}->{new_name}")
    default = config.get("DEFAULT")
    default_node = nodes.get(("DEFAULT",))
    if isinstance(default, Mapping) and default_node and isinstance(default.get("default_trackers"), str):
        renamed = [TRACKER_ALIASES.get(name.strip().upper(), name.strip()) for name in default["default_trackers"].split(",") if name.strip()]
        replacement = ",".join(renamed)
        if replacement != default["default_trackers"]:
            for key_node, value_node in zip(default_node.keys, default_node.values, strict=False):
                if isinstance(key_node, ast.Constant) and key_node.value == "default_trackers":
                    edits.append(
                        (_offset(lines, value_node.lineno, value_node.col_offset), _offset(lines, value_node.end_lineno, value_node.end_col_offset), repr(replacement))
                    )
                    migrated.append("DEFAULT.default_trackers")
                    break
    return _apply_source_edits(source, edits), migrated


def _matching_client_template(client: Mapping[str, Any], templates: Mapping[str, Any]) -> Mapping[str, Any] | None:
    client_type = client.get("torrent_client")
    if not client_type:
        return None
    for template in templates.values():
        if isinstance(template, Mapping) and template.get("torrent_client") == client_type:
            return template
    return None


def _collect_missing_values(template: ConfigDict, config: ConfigDict) -> dict[tuple[str, ...], ConfigDict]:
    """Return missing values grouped by the existing dictionary that owns them."""
    additions: dict[tuple[str, ...], ConfigDict] = {}

    def add(parent: tuple[str, ...], key: str, value: Any) -> None:
        additions.setdefault(parent, {})[key] = copy.deepcopy(value)

    def walk(template_section: Mapping[str, Any], config_section: Mapping[str, Any], path: tuple[str, ...]) -> None:
        for key, template_value in template_section.items():
            if key not in config_section:
                add(path, key, template_value)
            elif isinstance(template_value, Mapping) and isinstance(config_section[key], Mapping):
                walk(template_value, config_section[key], (*path, key))

    for section, template_section in template.items():
        if section == "TORRENT_CLIENTS":
            clients = config.get(section)
            if not isinstance(clients, Mapping):
                add((), section, template_section)
                continue
            for name, client in clients.items():
                if not isinstance(name, str) or not isinstance(client, Mapping):
                    continue
                client_template = _matching_client_template(client, template_section) if isinstance(template_section, Mapping) else None
                if client_template:
                    walk(client_template, client, (section, name))
        elif section not in config:
            add((), section, template_section)
        elif isinstance(template_section, Mapping) and isinstance(config[section], Mapping):
            walk(template_section, config[section], (section,))

    default = config.get("DEFAULT")
    if isinstance(default, Mapping) and SCHEMA_VERSION_KEY not in default:
        add(("DEFAULT",), SCHEMA_VERSION_KEY, CONFIG_SCHEMA_VERSION)
    return additions


def _collect_obsolete_paths(config: ConfigDict, template: ConfigDict) -> list[tuple[str, ...]]:
    """Find keys no longer represented by the example configuration.

    Torrent-client names are user-defined, so that whole section is excluded from
    automatic review.  Its keys may be implementation-specific as well.
    """
    obsolete: list[tuple[str, ...]] = []

    default_keys = set(template.get("DEFAULT", {}))

    def walk(current: Mapping[str, Any], example: Mapping[str, Any], path: tuple[str, ...]) -> None:
        for key, value in current.items():
            tracker_override = len(path) == 2 and path[0] == "TRACKERS" and key in default_keys
            if key not in example and not tracker_override:
                obsolete.append((*path, key))
            elif isinstance(value, Mapping) and isinstance(example[key], Mapping):
                walk(value, example[key], (*path, key))

    for section, value in config.items():
        if section == "TORRENT_CLIENTS":
            continue
        if section not in template:
            obsolete.append((section,))
        elif isinstance(value, Mapping) and isinstance(template[section], Mapping):
            walk(value, template[section], (section,))
    return obsolete


def find_obsolete_config_paths(config_path: Path, example_path: Path) -> list[str]:
    """Return obsolete configuration paths without changing either file."""
    parsed_config = _read_config_literal(config_path)
    parsed_example = _read_config_literal(example_path)
    if not parsed_config or not parsed_example:
        return []
    config, _, _ = parsed_config
    example, _, _ = parsed_example
    return [".".join(path) for path in _collect_obsolete_paths(config, example)]


def _format_entry(key: str, value: Any, indent: str) -> str:
    rendered = pprint.pformat(value, width=120, sort_dicts=False)
    rendered = rendered.replace("\n", "\n" + indent)
    return f"{indent}{key!r}: {rendered},\n"


def _apply_additions(
    source: str,
    nodes: Mapping[tuple[str, ...], ast.Dict],
    additions: Mapping[tuple[str, ...], ConfigDict],
    version_edit: tuple[int, int, str] | None = None,
    removal_edits: list[tuple[int, int, str]] | None = None,
) -> str:
    """Insert only missing dictionary entries, retaining existing comments and formatting."""
    source_lines = source.splitlines(keepends=True)
    line_offsets = _line_offsets(source_lines)

    edits: list[tuple[int, int, str]] = []
    lines = source.splitlines()
    for path, values in additions.items():
        node = nodes.get(path)
        if node is None:
            continue
        closing_line = lines[node.end_lineno - 1]
        closing_indent = closing_line[: len(closing_line) - len(closing_line.lstrip())]
        entry_indent = closing_indent + "    "
        insert_at = _offset(source_lines, node.end_lineno, node.end_col_offset - 1, line_offsets)
        separator = ""
        if node.values:
            last = node.values[-1]
            last_end = _offset(source_lines, last.end_lineno, last.end_col_offset, line_offsets)
            if not source[last_end:insert_at].lstrip().startswith(","):
                separator = ","
        entries = "".join(_format_entry(key, value, entry_indent) for key, value in values.items())
        edits.append((insert_at, insert_at, f"{separator}\n{entries}{closing_indent}"))

    if version_edit:
        edits.append(version_edit)
    if removal_edits:
        edits.extend(removal_edits)
    for start, end, text in sorted(edits, reverse=True):
        source = source[:start] + text + source[end:]
    return source


def _entry_removal_edits(source: str, config_node: ast.Dict, paths: list[tuple[str, ...]]) -> list[tuple[int, int, str]]:
    """Build source edits which remove selected dict entries and their comments."""
    nodes = _dict_nodes(config_node)
    lines = source.splitlines(keepends=True)
    line_offsets = _line_offsets(lines)
    edits: list[tuple[int, int, str]] = []
    for path in paths:
        parent = nodes.get(path[:-1])
        if parent is None:
            continue
        for key, value in zip(parent.keys, parent.values, strict=False):
            if not isinstance(key, ast.Constant) or key.value != path[-1]:
                continue
            start_line = key.lineno - 1
            while start_line > 0 and lines[start_line - 1].lstrip().startswith("#"):
                start_line -= 1
            start = line_offsets[start_line]
            end = _offset(lines, value.end_lineno, value.end_col_offset, line_offsets)
            while end < len(source) and source[end] in " \t":
                end += 1
            if end < len(source) and source[end] == ",":
                end += 1
            while end < len(source) and source[end] in "\r\n":
                end += 1
            edits.append((start, end, ""))
            break
    return edits


def _prompt_obsolete_removals(paths: list[tuple[str, ...]]) -> list[tuple[str, ...]]:
    """Ask the user before removing each obsolete setting."""
    if not sys.stdin.isatty():
        return []
    selected: list[tuple[str, ...]] = []
    print("Configuration settings no longer present in example_config.py:")
    for path in paths:
        dotted_path = ".".join(path)
        try:
            answer = input(f"Remove {dotted_path}? [y/N]: ")
        except EOFError:
            break
        if answer.strip().lower() in {"y", "yes"}:
            selected.append(path)
    return selected


def _schema_version_edit(source: str, config_node: ast.Dict, config: ConfigDict) -> tuple[int, int, str] | None:
    default = config.get("DEFAULT")
    if not isinstance(default, Mapping) or default.get(SCHEMA_VERSION_KEY) == CONFIG_SCHEMA_VERSION:
        return None
    for key, value in zip(config_node.keys, config_node.values, strict=False):
        if isinstance(key, ast.Constant) and key.value == "DEFAULT" and isinstance(value, ast.Dict):
            for default_key, default_value in zip(value.keys, value.values, strict=False):
                if isinstance(default_key, ast.Constant) and default_key.value == SCHEMA_VERSION_KEY:
                    lines = source.splitlines(keepends=True)
                    offsets = _line_offsets(lines)
                    start = _offset(lines, default_value.lineno, default_value.col_offset, offsets)
                    end = _offset(lines, default_value.end_lineno, default_value.end_col_offset, offsets)
                    return start, end, str(CONFIG_SCHEMA_VERSION)
    return None


def _required_setting_keys(example_source: str) -> set[str]:
    """Find settings explicitly labelled REQUIRED in the example's comments."""
    required: set[str] = set()
    comments: list[str] = []
    for line in example_source.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            comments.append(stripped)
            continue
        key_match = re.match(r"[\"']([^\"']+)[\"']\s*:", stripped)
        if key_match and any("REQUIRED" in comment.upper() for comment in comments):
            required.add(key_match.group(1))
        if stripped and not stripped.startswith("#"):
            comments = []
    return required


def _prompt_required_values(additions: Mapping[tuple[str, ...], ConfigDict], example_source: str) -> None:
    """Offer values only for newly added fields marked REQUIRED by the schema."""
    if not sys.stdin.isatty():
        return
    required_keys = _required_setting_keys(example_source)
    for parent, values in additions.items():
        for key, default in values.items():
            if key not in required_keys or not isinstance(default, str):
                continue
            path = ".".join((*parent, key))
            try:
                value = input(f"New required setting {path} [leave blank to use the default]: ").strip()
            except EOFError:
                return
            if value:
                values[key] = value


def sync_config_schema(
    config_path: Path,
    example_path: Path,
    *,
    prompt_for_required: bool = False,
    prompt_for_obsolete: bool = False,
) -> list[str]:
    """Add defaults introduced by the current schema and return their dotted paths.

    The original configuration is backed up before the first write.  Existing values,
    including settings no longer present in the example, are deliberately untouched.
    """
    parsed_config = _read_config_literal(config_path)
    parsed_example = _read_config_literal(example_path)
    if not parsed_config or not parsed_example:
        return []
    config, config_node, source = parsed_config
    original_source = source
    example, _example_node, _example_source = parsed_example
    source, migrated_paths = _migrate_tracker_aliases(source, config_node, config)
    if migrated_paths:
        migrated_config = _read_config_literal_source(source, str(config_path))
        if migrated_config is None:
            return []
        config, config_node, source = migrated_config
    additions = _collect_missing_values(example, config)
    obsolete_paths = _collect_obsolete_paths(config, example)
    removals = _prompt_obsolete_removals(obsolete_paths) if prompt_for_obsolete else []
    version_edit = _schema_version_edit(source, config_node, config)
    version_updated = version_edit is not None
    if not additions and not version_updated and not removals and not migrated_paths:
        return []

    if prompt_for_required:
        _prompt_required_values(additions, _example_source)

    removal_edits = _entry_removal_edits(source, config_node, removals)
    updated = _apply_additions(source, _dict_nodes(config_node), additions, version_edit, removal_edits)
    if updated == original_source:
        return []
    if _read_config_literal_source(updated, str(config_path)) is None:
        return []
    backup_path = config_path.with_suffix(config_path.suffix + ".bak")
    if backup_path.exists():
        backup_path = config_path.with_suffix(f"{config_path.suffix}.{datetime.now(UTC):%Y%m%d%H%M%S}.bak")
    backup_path.write_text(original_source, encoding="utf-8")
    temp_path = config_path.with_suffix(config_path.suffix + ".tmp")
    temp_path.write_text(updated, encoding="utf-8")
    temp_path.replace(config_path)
    paths = [".".join((*parent, key)) for parent, values in additions.items() for key in values]
    if version_updated and f"DEFAULT.{SCHEMA_VERSION_KEY}" not in paths:
        paths.append(f"DEFAULT.{SCHEMA_VERSION_KEY}")
    paths.extend(".".join(path) for path in removals)
    paths.extend(migrated_paths)
    return paths
