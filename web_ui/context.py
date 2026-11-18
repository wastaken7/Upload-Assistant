"""Shared Web UI runtime context: console, paths, config directory and access log."""

import contextlib
import importlib
from collections.abc import Callable
from pathlib import Path

import web_ui.auth as auth_mod

# Every Web UI module reads these through this module, so one attribute redirects them all.
from src.app_paths import CODE_DIR as CODE_DIR
from src.app_paths import DATA_DIR as DATA_DIR
from src.app_paths import STATE_DIR as STATE_DIR
from src.version import __version__
from web_ui.flask_compat import _AccessLoggerLike, _ConsoleLike

APP_VERSION = __version__

# Helper to convert ANSI -> HTML using Rich (optional)
ansi_to_html: Callable[[str], str] | None = None


class _NullConsole:
    def print(self, *_args: object, **_kwargs: object) -> None:
        return None

    def input(self, prompt: str = "") -> str:
        raise EOFError(prompt)


console: _ConsoleLike = _NullConsole()
with contextlib.suppress(Exception):
    console_mod = importlib.import_module("src.console")
    ansi_to_html = getattr(console_mod, "ansi_to_html", None)
    loaded_console = getattr(console_mod, "console", None)
    if loaded_console is not None:
        console = loaded_console

cfg_dir = auth_mod.get_config_dir()
cfg_dir.mkdir(parents=True, exist_ok=True)


# Access logging helper
AccessLogger: Callable[[Path], _AccessLoggerLike] | None = None
with contextlib.suppress(Exception):
    access_log_mod = importlib.import_module("web_ui.access_log")
    AccessLogger = getattr(access_log_mod, "AccessLogger", None)

access_logger: _AccessLoggerLike | None = AccessLogger(cfg_dir) if AccessLogger is not None else None


# Helper: simple file-backed config store under the auth config dir. Values
# are stored as raw text. This replaces OS keyring usage and allows Docker
# and non-Docker deployments to persist credentials via the configured
# persistent config mechanism.
def _cfg_file_path(name: str) -> Path:
    return cfg_dir / name


def _cfg_read(name: str) -> str | None:
    p = _cfg_file_path(name)
    with contextlib.suppress(Exception):
        if p.exists():
            return p.read_text(encoding="utf-8")
    return None


def _cfg_write(name: str, value: str) -> None:
    p = _cfg_file_path(name)
    with contextlib.suppress(Exception):
        auth_mod.write_private_text(p, value)


def _cfg_delete(name: str) -> None:
    p = _cfg_file_path(name)
    with contextlib.suppress(Exception):
        if p.exists():
            p.unlink()


# Keep this helper referenced so static analysis does not flag it as unused.
_ = _cfg_delete
