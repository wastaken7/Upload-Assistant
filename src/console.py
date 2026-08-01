# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import asyncio
import contextlib
import contextvars
import logging
import os
import re
import threading
from collections.abc import AsyncGenerator, Callable, Generator
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.logging import RichHandler
from rich.progress import Progress
from rich.text import Text


def ansi_to_html(ansi_chunk: str, width: int = 120) -> str:
    """Convert an ANSI-containing text chunk to an HTML fragment using Rich.

    This creates a short-lived Console in record mode, renders the ANSI
    content into it (via Text.from_ansi) and exports an HTML fragment
    with inline styles so it can be embedded directly into the web UI.
    """
    try:
        c = Console(record=True, force_terminal=True, width=width)
        # Try parsing ANSI sequences first. If there are no style spans and
        # the chunk looks like Rich markup (e.g. contains [bold] tags),
        # parse as markup so styled output is preserved.
        text = Text.from_ansi(ansi_chunk)
        with contextlib.suppress(Exception):
            if (not getattr(text, "spans", None) or len(text.spans) == 0) and "[" in ansi_chunk and "]" in ansi_chunk:
                # Parse Rich markup into a Text instance
                with contextlib.suppress(Exception):
                    text = Text.from_markup(ansi_chunk)
            # If introspecting spans fails for any reason, proceed with the original text
        c.print(text, end="")
        # inline_styles keeps the fragment self-contained
        # export the recorded renderable as HTML with inline styles
        html = c.export_html(inline_styles=True)
        # Rich returns a full HTML document; extract the body contents so the
        # web UI can embed the fragment directly.
        with contextlib.suppress(Exception):
            import re

            m = re.search(r"<body[^>]*>(.*?)</body>", html, re.S | re.I)
            if m:
                return m.group(1).strip()
        return html
    except Exception:
        # Fallback: escape HTML to avoid breaking the page
        import html as _html

        return f"<div>{_html.escape(ansi_chunk)}</div>"


# Create a shared Console instance used throughout the project.
# Force terminal mode so that when other processes import `src.console.console`
# they will emit ANSI color codes to stdout even when not attached to a real TTY.
_webui_force_color = bool(os.environ.get("UA_WEBUI_FORCE_COLOR", "").strip())
console = Console(
    force_terminal=True,
    color_system="truecolor" if _webui_force_color else "auto",
    legacy_windows=False if _webui_force_color else None,
)

# Rich permits one Live renderable per Console. Long-running local jobs can
# overlap (for example, an early BASE torrent hash alongside Usenet archive
# preparation), so they share one multi-row progress panel instead of raising
# ``LiveError`` and forcing a slower fallback.
_live_progress_lock = threading.Lock()
_shared_progress: Progress | None = None
_shared_progress_users = 0
_suppress_cli_progress = contextvars.ContextVar("suppress_cli_progress", default=False)


@contextlib.contextmanager
def suppress_cli_progress() -> Generator[None]:
    """Temporarily hide terminal progress while background preparation runs."""
    token = _suppress_cli_progress.set(True)
    try:
        yield
    finally:
        _suppress_cli_progress.reset(token)


def is_cli_progress_suppressed() -> bool:
    """Return whether the current task should avoid rendering terminal progress."""
    return _suppress_cli_progress.get()


@contextlib.contextmanager
def progress_display(*columns: Any, **kwargs: Any) -> Generator[Progress]:
    """Yield a progress panel that safely shares the console's single Live display."""
    global _shared_progress, _shared_progress_users

    requested_disabled = bool(kwargs.get("disable", False)) or is_cli_progress_suppressed()
    if requested_disabled:
        kwargs["disable"] = True
    shared = not requested_disabled
    if shared:
        with _live_progress_lock:
            if _shared_progress is None:
                new_progress = Progress(*columns, **kwargs)
                new_progress.start()
                _shared_progress = new_progress
            progress = _shared_progress
            _shared_progress_users += 1
    else:
        progress = Progress(*columns, **kwargs)
        progress.start()

    try:
        yield progress
    finally:
        if shared:
            with _live_progress_lock:
                _shared_progress_users -= 1
                if _shared_progress_users == 0 and _shared_progress is not None:
                    _shared_progress.stop()
                    _shared_progress = None
        else:
            progress.stop()


# Configure logger integrated with Rich console
logger = logging.getLogger("UploadAssistant")
logger.setLevel(logging.INFO)

# Load configuration settings for the RichHandler
try:
    from data.config import config

    config_default: dict[str, Any] = config.get("DEFAULT", {})
except ImportError:
    config = {}
    config_default: dict[str, Any] = {}

# RichHandler captures logs and outputs them using our shared console instance.
# We enable markup=True to preserve Rich color formatting like [yellow], [red], etc.
rich_handler = RichHandler(
    console=console,
    show_time=bool(config_default.get("console_show_time", False)),
    show_level=bool(config_default.get("console_show_level", False)),
    show_path=bool(config_default.get("console_show_path", False)),
    markup=bool(config_default.get("console_markup", True)),
)
rich_handler.setFormatter(logging.Formatter("%(message)s"))
logger.addHandler(rich_handler)


class LogBufferHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.buffer: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.buffer.append(record)


_log_buffer_lock = asyncio.Lock()


@contextlib.asynccontextmanager
async def buffer_console_logs() -> AsyncGenerator[None]:
    """Temporarily hold console log output in memory while user prompts are active."""
    async with _log_buffer_lock:
        root_logger = logger
        original_rich_handlers = [h for h in root_logger.handlers if isinstance(h, RichHandler)]
        buffer_handler = LogBufferHandler()

        for h in original_rich_handlers:
            root_logger.removeHandler(h)
        root_logger.addHandler(buffer_handler)

        try:
            yield
        finally:
            root_logger.removeHandler(buffer_handler)
            for h in original_rich_handlers:
                root_logger.addHandler(h)
            for record in buffer_handler.buffer:
                for h in original_rich_handlers:
                    h.handle(record)


async def prompt_in_thread[PromptResult](callback: Callable[..., PromptResult], /, *args: Any, **kwargs: Any) -> PromptResult:
    """Run an interactive prompt without blocking the event loop or interleaving logs."""
    async with buffer_console_logs():
        return await asyncio.to_thread(callback, *args, **kwargs)


# Context variable to hold the path to the current release's log file (e.g. /tmp/<uuid>/upload.log)
current_release_log_path: contextvars.ContextVar[str | None] = contextvars.ContextVar("current_release_log_path", default=None)


class LogFileFormatter(logging.Formatter):
    def __init__(self, fmt: str = "[%(asctime)s] %(levelname)s: %(message)s", datefmt: str = "%Y-%m-%d %H:%M:%S") -> None:
        super().__init__(fmt, datefmt)
        self.console = Console(color_system=None, width=150)
        self.ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

    def format(self, record: logging.LogRecord) -> str:
        # Format the record normally first
        formatted = super().format(record)

        # Strip ANSI escape sequences
        formatted = self.ansi_escape.sub("", formatted)

        # Strip Rich markup using Console
        with contextlib.suppress(Exception):
            formatted = self.console.render_str(formatted).plain

        return formatted


class DynamicFileHandler(logging.Handler):
    def __init__(self, formatter=None) -> None:
        super().__init__()
        if formatter:
            self.setFormatter(formatter)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            # Check if write_log is enabled in config. Use lazy lookup to support reload
            try:
                from data.config import config

                write_log = bool(config.get("DEFAULT", {}).get("write_log", False))
            except Exception:
                write_log = False

            if not write_log:
                return

            log_path = current_release_log_path.get()
            if not log_path:
                return

            # Format message
            msg = self.format(record)

            # Ensure target directory exists
            log_dir = Path(log_path).parent
            if str(log_dir) and not log_dir.exists():
                log_dir.mkdir(parents=True, exist_ok=True)

            # Append message to file
            with Path(log_path).open("a", encoding="utf-8") as f:
                f.write(msg + "\n")
        except Exception:
            self.handleError(record)


# Add the dynamic file handler to UploadAssistant logger
dynamic_file_handler = DynamicFileHandler(LogFileFormatter())
logger.addHandler(dynamic_file_handler)
