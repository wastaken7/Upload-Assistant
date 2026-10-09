"""Filesystem policy shared by the WebUI and its upload subprocess.

This constrains upload inputs; the subprocess still needs normal OS permissions.
"""

import hashlib
import json
import os
import secrets
from collections.abc import Sequence
from functools import lru_cache
from pathlib import Path

ROOTS_ENV = "UA_WEBUI_ALLOWED_ROOTS"
QUEUE_ENV = "UA_WEBUI_QUEUE_PATH"
QUEUE_HASH_ENV = "UA_WEBUI_QUEUE_SHA256"
MAX_UPLOAD_PATHS = 1000
# Keep this set local to one validation phase; later phases must inspect again.
type InspectedDirectories = set[tuple[str, tuple[str, ...]]]


def is_generated_queue_path(path: str) -> bool:
    queue_path = os.environ.get(QUEUE_ENV)
    if not queue_path:
        return False
    return os.path.normcase(os.path.realpath(path)) == os.path.normcase(os.path.realpath(queue_path))


@lru_cache(maxsize=1)
def _argument_parser():
    from src.args import Args
    from src.meta import Meta

    _, parser, _ = Args({"DEFAULT": {"screens": 1}}).parse(["--webui"], Meta())
    parser.allow_abbrev = False
    return parser


def validate_argument_paths(args: Sequence[str], roots: Sequence[str], *, inspected_directories: InspectedDirectories | None = None) -> None:
    """Prevent arguments from adding unvalidated content or local file inputs."""
    for value in args:
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError("Invalid control character in arg")
        if value.split("=", 1)[0] in {"--help", "-h", "--paths-from-stdin"}:
            raise ValueError("This operation is only available in CLI mode")
    try:
        options, unknown = _argument_parser().parse_known_args(["_webui_content_", *args])
    except SystemExit as error:
        raise ValueError("Invalid execution arguments") from error
    if unknown:
        raise ValueError(f"Unrecognized argument: {unknown[0]}")
    if options.path != ["_webui_content_"]:
        raise ValueError("Additional paths must be entered one per line in the path field")
    if options.webui or options.site_upload or options.unit3d or options.cleanup:
        raise ValueError("This operation is only available in CLI mode")
    if options.queue and (len(options.queue[0]) > 128 or any(char in options.queue[0] for char in "/\\:") or options.queue[0] in {".", ".."}):
        raise ValueError("Queue name must be a simple name, not a path")
    for value in [*(options.description_file or []), *(options.comparison or [])]:
        validate_content_path(value, roots, allow_queue_file=True, inspected_directories=inspected_directories)
    for values in (options.explicit_poster, options.explicit_banner):
        if values and not values[0].lower().startswith(("https://", "http://")):
            validate_content_path(values[0], roots, allow_queue_file=True, inspected_directories=inspected_directories)
    for value in options.path_to_menu_screenshots or []:
        if value.lower() != "auto":
            validate_content_path(value, roots, allow_queue_file=True, inspected_directories=inspected_directories)


def subprocess_roots() -> list[str] | None:
    raw = os.environ.get(ROOTS_ENV)
    if raw is None:
        return None  # Ordinary CLI execution is unchanged.
    roots = json.loads(raw)
    if not isinstance(roots, list) or not roots or not all(isinstance(root, str) and root for root in roots):
        raise ValueError("Upload roots are not configured")
    return roots


def validate_content_path(path: str, roots: Sequence[str], *, allow_queue_file: bool = False, inspected_directories: InspectedDirectories | None = None) -> str:
    """Resolve a content input and reject escaping links throughout directories."""
    if not isinstance(path, str) or not path or len(path) > 4096 or any(ord(char) < 32 or ord(char) == 127 for char in path):
        raise ValueError("Invalid upload path")
    canonical_roots = [os.path.normcase(str(Path(root).resolve())) for root in roots]
    if not canonical_roots:
        raise ValueError("Upload roots are not configured")

    def checked(candidate: Path) -> Path:
        resolved = candidate.resolve(strict=True)
        normalized = os.path.normcase(str(resolved))
        for root in canonical_roots:
            try:
                if os.path.commonpath([normalized, root]) == root:
                    return resolved
            except ValueError:
                continue
        raise ValueError("Path outside allowed roots")

    try:
        resolved = checked(Path(path))
        if not resolved.is_dir() and not resolved.is_file():
            raise ValueError("Path must be a regular file or directory")
        if resolved.is_file():
            if not allow_queue_file and resolved.suffix.lower() in {".txt", ".log"}:
                raise ValueError("Paste queue paths one per line instead of selecting a text or log queue")
            return str(resolved)

        inspection_key = (os.path.normcase(str(resolved)), tuple(canonical_roots))
        if inspected_directories is not None and inspection_key in inspected_directories:
            return str(resolved)

        def walk_error(error: OSError) -> None:
            raise error

        for directory, directories, files in os.walk(resolved, followlinks=False, onerror=walk_error):
            for name in directories:
                child = Path(directory) / name
                checked(child)
                # Do not traverse directory links/junctions, even inside a root:
                # consumers may follow them and cycles make inspection incomplete.
                if child.is_symlink() or child.is_junction():
                    raise ValueError("Upload folders cannot contain directory links or junctions")
            for name in files:
                child = checked(Path(directory) / name)
                if not child.is_file():
                    raise ValueError("Upload folders can only contain regular files")
        if inspected_directories is not None:
            inspected_directories.add(inspection_key)
        return str(resolved)
    except OSError as error:
        raise ValueError("Upload path does not exist or cannot be inspected") from error


def validate_subprocess_path(path: str) -> str:
    roots = subprocess_roots()
    return path if roots is None else validate_content_path(path, roots)


def read_generated_queue(path: str) -> list[str]:
    """Read the exact server-issued contents once, before interpreting arguments."""
    content = Path(path).read_bytes()
    if not secrets.compare_digest(hashlib.sha256(content).hexdigest(), os.environ.get(QUEUE_HASH_ENV, "")):
        raise ValueError("WebUI queue was modified; select the paths again")
    return content.decode("utf-8").splitlines()


def validate_subprocess_queue(queue: Sequence[object]) -> None:
    """Check the complete expanded queue before processing its first item."""
    roots = subprocess_roots()
    if roots is None:
        return
    if len(queue) > MAX_UPLOAD_PATHS:
        raise ValueError(f"Maximum {MAX_UPLOAD_PATHS} paths per upload")
    inspected_directories: InspectedDirectories = set()
    for number, item in enumerate(queue, 1):
        try:
            path = item.get("path") if isinstance(item, dict) else item
            if not isinstance(path, str):
                raise ValueError("Invalid upload path")
            validate_content_path(path, roots, inspected_directories=inspected_directories)
            if isinstance(item, dict):
                args = item.get("args", [])
                if not isinstance(args, list) or not args or not all(isinstance(value, str) for value in args):
                    raise ValueError("Invalid queue arguments")
                validate_argument_paths(args[1:], roots, inspected_directories=inspected_directories)
        except ValueError as error:
            raise ValueError(f"Invalid queue item {number}: {error}") from error
