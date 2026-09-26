"""Safely add new bundled configuration defaults to a user's config file."""

import ast
import os
import pprint
import shutil
import tempfile
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast


class ConfigSyncError(RuntimeError):
    """Raised when a configuration cannot be synchronized safely."""


@dataclass(frozen=True)
class ConfigSyncResult:
    """Describe the outcome of synchronizing one user configuration."""

    added_paths: tuple[str, ...] = ()
    backup_path: Path | None = None

    @property
    def changed(self) -> bool:
        return bool(self.added_paths)


@dataclass(frozen=True)
class _ParsedConfig:
    value: dict[str, Any]
    dict_nodes: dict[tuple[str, ...], ast.Dict]


@dataclass(frozen=True)
class _Addition:
    parent_path: tuple[str, ...]
    key: str
    value: Any

    @property
    def dotted_path(self) -> str:
        return ".".join((*self.parent_path, self.key))


def _config_assignment(tree: ast.Module) -> ast.Assign | ast.AnnAssign | None:
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "config" for target in node.targets):
            return node
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "config":
            return node
    return None


def _index_dict_nodes(node: ast.Dict, path: tuple[str, ...], index: dict[tuple[str, ...], ast.Dict]) -> None:
    index[path] = node
    for key_node, value_node in zip(node.keys, node.values, strict=False):
        if isinstance(key_node, ast.Constant) and isinstance(key_node.value, str) and isinstance(value_node, ast.Dict):
            _index_dict_nodes(value_node, (*path, key_node.value), index)


def _parse_config(source: str, label: str) -> _ParsedConfig:
    try:
        tree = ast.parse(source, filename=label)
    except SyntaxError as exc:
        raise ConfigSyncError(f"{label} has invalid Python syntax: {exc.msg}") from exc

    assignment = _config_assignment(tree)
    if assignment is None or not isinstance(assignment.value, ast.Dict):
        raise ConfigSyncError(f"{label} must contain a literal dictionary assigned to 'config'")

    try:
        raw_value = ast.literal_eval(assignment.value)
    except (TypeError, ValueError) as exc:
        raise ConfigSyncError(f"{label} contains non-literal configuration values") from exc
    if not isinstance(raw_value, dict):
        raise ConfigSyncError(f"{label} must contain a dictionary with string keys")
    raw_dict = cast(dict[Any, Any], raw_value)
    if any(not isinstance(key, str) for key in raw_dict):
        raise ConfigSyncError(f"{label} must contain a dictionary with string keys")

    dict_nodes: dict[tuple[str, ...], ast.Dict] = {}
    _index_dict_nodes(assignment.value, (), dict_nodes)
    return _ParsedConfig(cast(dict[str, Any], raw_dict), dict_nodes)


def _collect_additions(
    template: Mapping[str, Any],
    user: Mapping[str, Any],
    parent_path: tuple[str, ...] = (),
) -> list[_Addition]:
    additions: list[_Addition] = []
    for key, template_value in template.items():
        if key not in user:
            additions.append(_Addition(parent_path, key, template_value))
            continue
        user_value = user[key]
        if isinstance(template_value, Mapping) and isinstance(user_value, Mapping):
            additions.extend(_collect_additions(template_value, user_value, (*parent_path, key)))
    return additions


def _source_offset(source: str, lineno: int, byte_col: int) -> int:
    lines = source.splitlines(keepends=True)
    try:
        line = lines[lineno - 1]
    except IndexError as exc:
        raise ConfigSyncError("Configuration AST contains an invalid source position") from exc
    try:
        char_col = len(line.encode("utf-8")[:byte_col].decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise ConfigSyncError("Configuration AST position splits a UTF-8 character") from exc
    return sum(len(item) for item in lines[: lineno - 1]) + char_col


def _has_trailing_comma(source: str, node: ast.Dict, closing_offset: int) -> bool:
    if not node.values:
        return True
    last_value = node.values[-1]
    if last_value.end_lineno is None or last_value.end_col_offset is None:
        raise ConfigSyncError("Unable to locate the final configuration value")
    value_end = _source_offset(source, last_value.end_lineno, last_value.end_col_offset)
    suffix = source[value_end:closing_offset]
    without_comments = "\n".join(line.split("#", 1)[0] for line in suffix.splitlines())
    return "," in without_comments


def _format_value(value: Any, continuation_indent: str, newline: str) -> str:
    rendered = pprint.pformat(value, width=120, sort_dicts=False)
    return rendered.replace("\n", f"{newline}{continuation_indent}")


def _render_additions(source: str, node: ast.Dict, additions: list[_Addition], newline: str) -> tuple[int, str, tuple[int, str] | None]:
    if node.end_lineno is None or node.end_col_offset is None:
        raise ConfigSyncError("Unable to locate a configuration dictionary")
    node_end = _source_offset(source, node.end_lineno, node.end_col_offset)
    closing_offset = node_end - 1
    if source[closing_offset:node_end] != "}":
        raise ConfigSyncError("Configuration dictionary does not end with '}'")

    line_start = source.rfind("\n", 0, closing_offset) + 1
    before_brace = source[line_start:closing_offset]
    closing_indent = before_brace if not before_brace.strip() else source[line_start : line_start + len(before_brace) - len(before_brace.lstrip())]
    entry_indent = f"{closing_indent}    "

    rendered_entries = [f"{entry_indent}{addition.key!r}: {_format_value(addition.value, entry_indent, newline)}," for addition in additions]
    if before_brace.strip():
        insertion = f"{newline}{newline.join(rendered_entries)}{newline}{closing_indent}"
    else:
        # Existing indentation before the closing brace supplies the first part
        # of the first entry's indentation.
        relative_entries = [entry[len(closing_indent) :] if entry.startswith(closing_indent) else entry for entry in rendered_entries]
        insertion = f"{newline.join(relative_entries)}{newline}{closing_indent}"

    comma_edit: tuple[int, str] | None = None
    if node.values and not _has_trailing_comma(source, node, closing_offset):
        last_value = node.values[-1]
        if last_value.end_lineno is None or last_value.end_col_offset is None:
            raise ConfigSyncError("Unable to locate the final configuration value")
        comma_edit = (_source_offset(source, last_value.end_lineno, last_value.end_col_offset), ",")
    return closing_offset, insertion, comma_edit


def _apply_additions(source: str, parsed: _ParsedConfig, additions: list[_Addition]) -> str:
    grouped: dict[tuple[str, ...], list[_Addition]] = {}
    for addition in additions:
        grouped.setdefault(addition.parent_path, []).append(addition)

    newline = "\r\n" if "\r\n" in source else "\n"
    edits: list[tuple[int, str]] = []
    for parent_path, parent_additions in grouped.items():
        node = parsed.dict_nodes.get(parent_path)
        if node is None:
            raise ConfigSyncError(f"Unable to locate configuration section {'.'.join(parent_path)}")
        offset, insertion, comma_edit = _render_additions(source, node, parent_additions, newline)
        edits.append((offset, insertion))
        if comma_edit is not None:
            edits.append(comma_edit)

    updated = source
    for offset, text in sorted(edits, key=lambda edit: edit[0], reverse=True):
        updated = f"{updated[:offset]}{text}{updated[offset:]}"
    return updated


def _preserves_user_values(before: Mapping[str, Any], after: Mapping[str, Any]) -> bool:
    for key, before_value in before.items():
        if key not in after:
            return False
        after_value = after[key]
        if isinstance(before_value, Mapping) and isinstance(after_value, Mapping):
            if not _preserves_user_values(before_value, after_value):
                return False
        elif type(before_value) is not type(after_value) or before_value != after_value:
            return False
    return True


def _next_backup_path(config_path: Path) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    candidate = config_path.with_name(f"{config_path.name}.backup-{timestamp}")
    counter = 2
    while candidate.exists():
        candidate = config_path.with_name(f"{config_path.name}.backup-{timestamp}-{counter}")
        counter += 1
    return candidate


@contextmanager
def _sync_lock(config_path: Path, timeout: float = 10.0) -> Iterator[None]:
    lock_path = config_path.with_name(f"{config_path.name}.sync.lock")
    lock_file = lock_path.open("a+b")
    started = time.monotonic()
    try:
        if os.name == "nt":
            import msvcrt

            while True:
                try:
                    lock_file.seek(0)
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError as exc:
                    if time.monotonic() - started >= timeout:
                        raise ConfigSyncError("Timed out waiting for the configuration sync lock") from exc
                    time.sleep(0.05)
            try:
                yield
            finally:
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            while True:
                try:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError as exc:
                    if time.monotonic() - started >= timeout:
                        raise ConfigSyncError("Timed out waiting for the configuration sync lock") from exc
                    time.sleep(0.05)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
    finally:
        lock_file.close()


def sync_user_config(config_path: Path, example_path: Path) -> ConfigSyncResult:
    """Add missing example keys to an existing config without changing user values.

    A timestamped backup is created only when the configuration changes. The
    replacement is validated and written atomically in the same directory.
    Repeated calls are idempotent.
    """
    if not config_path.is_file():
        raise ConfigSyncError(f"Configuration file does not exist: {config_path}")
    if not example_path.is_file():
        raise ConfigSyncError(f"Bundled example configuration does not exist: {example_path}")

    with _sync_lock(config_path):
        original_bytes = config_path.read_bytes()
        try:
            original_source = original_bytes.decode("utf-8")
            example_source = example_path.read_text(encoding="utf-8")
        except UnicodeError as exc:
            raise ConfigSyncError("Configuration files must use UTF-8 encoding") from exc

        user_config = _parse_config(original_source, str(config_path))
        example_config = _parse_config(example_source, str(example_path))
        additions = _collect_additions(example_config.value, user_config.value)
        if not additions:
            return ConfigSyncResult()

        updated_source = _apply_additions(original_source, user_config, additions)
        updated_config = _parse_config(updated_source, str(config_path))
        if not _preserves_user_values(user_config.value, updated_config.value):
            raise ConfigSyncError("Generated configuration did not preserve every existing user value")
        remaining = _collect_additions(example_config.value, updated_config.value)
        if remaining:
            raise ConfigSyncError(f"Generated configuration is still missing {remaining[0].dotted_path}")

        # An external editor is not required to honor our process lock. Avoid
        # replacing a file that changed after it was read.
        if config_path.read_bytes() != original_bytes:
            raise ConfigSyncError("Configuration changed while it was being synchronized; try again")

        backup_path = _next_backup_path(config_path)
        shutil.copy2(config_path, backup_path)
        if backup_path.read_bytes() != original_bytes:
            raise ConfigSyncError("Configuration changed before its backup could be verified; try again")
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="",
                dir=config_path.parent,
                prefix=f".{config_path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temp_file:
                temp_file.write(updated_source)
                temp_file.flush()
                os.fsync(temp_file.fileno())
                temp_path = Path(temp_file.name)
            shutil.copymode(config_path, temp_path)
            _parse_config(temp_path.read_text(encoding="utf-8"), str(temp_path))
            if config_path.read_bytes() != original_bytes:
                raise ConfigSyncError("Configuration changed before it could be replaced; try again")
            temp_path.replace(config_path)
            temp_path = None
        except Exception as exc:
            raise ConfigSyncError(f"Could not replace the configuration safely: {exc}") from exc
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)

        return ConfigSyncResult(
            added_paths=tuple(addition.dotted_path for addition in additions),
            backup_path=backup_path,
        )
