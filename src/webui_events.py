"""Structured run events for the Web UI's GUI output mode.

The Web UI starts ``upload.py`` as a child process and turns its terminal
output into HTML. The GUI mode needs a few facts the terminal only shows as
coloured text: run stages, prompts, dupes, missing disc details and tracker
results. This module writes them as ``UA_GUI_EVENT_JSON:<nonce>:`` lines on
stdout, which the server strips from the terminal stream and forwards as
``gui`` session events. The nonce is a secret the server passes to each child,
so text the run prints (a tracker's release names, for example) cannot forge
an event by containing the prefix.

Every helper is a no-op unless ``UA_WEBUI_GUI_EVENTS=1`` and a nonce are set,
so the CLI output is unchanged.
"""

from __future__ import annotations

import contextlib
import contextvars
import itertools
import json
import logging
import os
import re
import sys
import time
from collections.abc import Generator, Iterable, Mapping
from datetime import date, datetime
from pathlib import Path
from threading import Lock
from typing import Any, Literal, cast

GUI_EVENT_STDOUT_PREFIX = "UA_GUI_EVENT_JSON:"
GUI_EVENTS_ENV = "UA_WEBUI_GUI_EVENTS"
GUI_EVENT_NONCE_ENV = "UA_WEBUI_GUI_EVENT_NONCE"
GUI_EVENT_KINDS = frozenset({"item", "stage", "notice", "notice_group", "prompt", "dupes", "dupe_review", "slot", "tracker", "request"})
STAGE_KEYS = ("prep", "confirm", "dupes", "screens", "torrent", "upload", "requests")
STAGE_STATUSES = frozenset({"start", "done", "skip", "fail"})
NOTICE_LEVELS = frozenset({"error", "warning", "attention"})
TRACKER_STATUSES = frozenset({"pending", "success", "failed", "skipped", "dupe", "banned"})
# Bound events: the session log replays them and the browser renders text.
# Lists are large enough that the GUI shows every dupe or option the terminal
# does; an event over the byte limit is dropped whole, so it stays generous.
MAX_TEXT_LENGTH = 1000
MAX_LIST_ITEMS = 500
MAX_EVENT_BYTES = 262144
# The Web UI runs uploads unbuffered in a Windows pseudo console, which takes
# only part of a write over 16 KB and drops the rest; events go out in pieces.
STDOUT_WRITE_CHUNK = 4096
MAX_CHECK_MESSAGES = 20
# Local artwork the Web UI may serve as a queue item's cover thumbnail.
ARTWORK_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".webp"})
TMDB_POSTER_BASE = "https://image.tmdb.org/t/p/w500"

type StageStatus = Literal["start", "done", "skip", "fail"]
type NoticeLevel = Literal["error", "warning", "attention"]
type TrackerStatus = Literal["pending", "success", "failed", "skipped", "dupe", "banned"]

_stdout_lock = Lock()
_prompt_ids = itertools.count(1)
_current_item: dict[str, Any] | None = None
_active_stage: str | None = None
# Stages started for the current item, so the final tracker summary knows whether uploading ran.
_started_stages: set[str] = set()
_prompt_context: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar("ua_gui_prompt_context", default=None)
_tracker_check: contextvars.ContextVar[_TrackerCheckMessages | None] = contextvars.ContextVar("ua_gui_tracker_check", default=None)
_dupe_review: contextvars.ContextVar[_DupeReviewProgress | None] = contextvars.ContextVar("ua_gui_dupe_review", default=None)
_ANSI_ESCAPE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
_MARKUP_TAG = re.compile(r"\[/?[a-zA-Z#][^\[\]]*\]|\[/\]")
# ISO 3166-1 alpha-2 code naming a bundled ``static/img/flags/<code>.svg``.
_FLAG_CODE = re.compile(r"[a-z]{2}")


def enabled() -> bool:
    return os.environ.get(GUI_EVENTS_ENV) == "1" and bool(os.environ.get(GUI_EVENT_NONCE_ENV))


def event_prefix(nonce: str) -> str:
    """Return the line prefix of events written with ``nonce``."""
    return f"{GUI_EVENT_STDOUT_PREFIX}{nonce}:"


def plain_text(value: Any, limit: int = MAX_TEXT_LENGTH, *, markup: bool = True) -> str:
    """Return redacted, markup-free text that is safe to show as plain text."""
    text = _ANSI_ESCAPE.sub("", str(value if value is not None else ""))
    if markup:
        try:
            from rich.text import Text

            text = Text.from_markup(text).plain
        except Exception:
            text = _MARKUP_TAG.sub("", text)
    try:
        from src.cogs.redaction import Redaction

        text = str(Redaction.redact_value(text))
    except Exception:
        return ""
    text = text.strip()
    return text if len(text) <= limit else f"{text[: limit - 1]}…"


def _http_link(value: Any) -> str:
    link = plain_text(value, 2000)
    return link if link.lower().startswith(("http://", "https://")) else ""


def _emit(kind: str, payload: Mapping[str, Any]) -> None:
    if not enabled():
        return
    event: dict[str, Any] = {"kind": kind, "ts": round(time.time(), 3), **payload}
    if _current_item is not None and kind != "item":
        event["item"] = _current_item["index"]
    try:
        line = json.dumps(event, separators=(",", ":"), default=str)
    except TypeError, ValueError:
        return
    if len(line) > MAX_EVENT_BYTES:
        return
    text = f"\n{event_prefix(os.environ.get(GUI_EVENT_NONCE_ENV, ''))}{line}\n"
    with _stdout_lock, contextlib.suppress(Exception):
        for start in range(0, len(text), STDOUT_WRITE_CHUNK):
            sys.stdout.write(text[start : start + STDOUT_WRITE_CHUNK])
        sys.stdout.flush()


def begin_item(path: str, index: int, total: int) -> None:
    """Start a queue item; later events are tagged with its index."""
    global _current_item, _active_stage
    _current_item = {"index": int(index), "total": int(total), "name": plain_text(Path(str(path)).name or path, 300)}
    _active_stage = None
    _started_stages.clear()
    _emit("item", _current_item)


def _item_artwork(meta: Mapping[str, Any]) -> dict[str, str]:
    """Return the release cover as a public URL or a local image file.

    A local ``artwork_file`` is never shown to the browser: the server swaps
    it for an authenticated URL before forwarding the event.
    """
    url = _http_link(meta.get("artwork_url")) if meta.get("artwork_url") else ""
    if url:
        return {"artwork": url}
    artwork_path = str(meta.get("artwork_path") or "")
    if artwork_path:
        with contextlib.suppress(OSError, ValueError):
            local = Path(artwork_path).resolve()
            if local.suffix.casefold() in ARTWORK_SUFFIXES and local.is_file():
                return {"artwork_file": str(local)}
    tmdb_poster = str(meta.get("tmdb_poster_path") or "")
    if tmdb_poster.startswith("/"):
        return {"artwork": _http_link(f"{TMDB_POSTER_BASE}{tmdb_poster}")}
    return {}


def update_item(*, personal_release: bool | None = None, run_options: Mapping[str, Any] | None = None, artwork: Mapping[str, Any] | None = None) -> None:
    """Publish resolved release flags, bounded run settings and the release cover."""
    global _current_item
    if not enabled() or _current_item is None:
        return
    _current_item = dict(_current_item)
    if artwork is not None:
        # Keep a cover already found when a later call no longer has one, e.g.
        # after its temporary file was removed at the end of the item.
        resolved = _item_artwork(artwork)
        if resolved:
            _current_item.pop("artwork", None)
            _current_item.pop("artwork_file", None)
            _current_item.update(resolved)
    if personal_release is not None:
        _current_item["personal_release"] = bool(personal_release)
    if run_options is not None:
        options: dict[str, Any] = {key: run_options.get(key) is True for key in ("debug", "no_seed", "skip_imghost_upload", "nohash", "ffdebug")}
        options["client_disabled"] = run_options.get("client") == "none"
        options["category"] = plain_text(run_options.get("category", ""), 20, markup=False)
        base_dir, folder = run_options.get("base_dir"), run_options.get("uuid")
        options["prep_directory"] = plain_text(Path(str(base_dir)) / "tmp" / str(folder), markup=False) if base_dir and folder else ""
        _current_item["run_options"] = options
    _emit("item", _current_item)


def stage(key: str, status: StageStatus) -> None:
    global _active_stage
    if key not in STAGE_KEYS or status not in STAGE_STATUSES:
        return
    if status == "start":
        _active_stage = key
        _started_stages.add(key)
    elif _active_stage == key:
        _active_stage = None
    _emit("stage", {"key": key, "status": status})


def current_item_index() -> int | None:
    """Index of the queue item being processed, or None before the first one."""
    return _current_item["index"] if _current_item is not None else None


def fail_active_stage() -> None:
    """Mark the stage that was running when an item stopped early as failed."""
    if _active_stage is not None:
        stage(_active_stage, "fail")


@contextlib.contextmanager
def stage_scope(key: str) -> Generator[None]:
    """Mark a stage as started, then done or failed when the block exits."""
    stage(key, "start")
    try:
        yield
    except BaseException:
        stage(key, "fail")
        raise
    stage(key, "done")


def notice(level: NoticeLevel, text: Any, *, tracker: str | None = None, key: str | None = None) -> None:
    if not enabled():
        return
    if level not in NOTICE_LEVELS:
        return
    message = plain_text(text)
    if not message:
        return
    payload: dict[str, Any] = {"level": level, "text": message}
    if tracker:
        payload["tracker"] = plain_text(tracker, 64)
    if key:
        payload["key"] = plain_text(key, 200)
    _emit("notice", payload)


def notice_group(group: str, notices: Iterable[Mapping[str, Any]]) -> None:
    """Replace every notice previously sent for ``group`` with ``notices``."""
    if not enabled():
        return
    items: list[dict[str, Any]] = []
    for entry in notices:
        level = entry.get("level")
        message = plain_text(entry.get("text"))
        if level not in NOTICE_LEVELS or not message:
            continue
        item: dict[str, Any] = {"level": level, "text": message}
        if entry.get("tracker"):
            item["tracker"] = plain_text(entry["tracker"], 64)
        items.append(item)
        if len(items) >= MAX_LIST_ITEMS:
            break
    _emit("notice_group", {"group": plain_text(group, 64), "notices": items})


class _TrackerCheckMessages(logging.Handler):
    """Keep a check's own explanations separate from concurrent tracker logs."""

    def __init__(self, tracker: str) -> None:
        """Collect INFO-level explanations for one tracker's check context."""
        super().__init__(level=logging.INFO)
        self.tracker = tracker
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        """Retain bounded, redacted messages only from the owning check."""
        if _tracker_check.get() is not self:
            return
        try:
            message = plain_text(record.getMessage(), markup=getattr(record, "markup", True) is not False)
            message = re.sub(rf"(?im)^[ \t]*{re.escape(self.tracker)}:[ \t]*", "", message).strip()
            if message and message not in self.messages:
                self.messages.append(message)
                # Keep the latest explanations, including a failure at the end of a noisy check.
                self.messages[:] = self.messages[-MAX_CHECK_MESSAGES:]
        except Exception:
            self.handleError(record)


@contextlib.contextmanager
def capture_tracker_checks(tracker: str, logger: logging.Logger) -> Generator[list[str]]:
    """Attach check messages to GUI prompts while leaving normal logging intact."""
    if not enabled():
        yield []
        return
    handler = _TrackerCheckMessages(tracker)
    token = _tracker_check.set(handler)
    logger.addHandler(handler)
    try:
        yield handler.messages
    finally:
        logger.removeHandler(handler)
        _tracker_check.reset(token)
        handler.close()


@contextlib.contextmanager
def prompt_context(**context: Any) -> Generator[None]:
    """Attach context (for example the tracker being asked about) to prompts in this block."""
    current = _prompt_context.get() or {}
    token = _prompt_context.set({**current, **context})
    try:
        yield
    finally:
        _prompt_context.reset(token)


class _DupeReviewProgress:
    """Keep discovery totals and actual review order local to one tracker batch."""

    def __init__(self, trackers: Iterable[str]) -> None:
        """Start discovery with every selected tracker unresolved."""
        self.pending = set(trackers)
        self.trackers: list[str] = []
        self.started: list[str] = []
        self.lock = Lock()

    def update(self, tracker: str, *, needs_review: bool = False, opened: bool = False, finished: bool = False) -> None:
        """Publish a changed total or first prompt while serializing worker updates."""
        # Searches run on the event loop; prompts open in worker threads.
        with self.lock:
            before = (len(self.pending), tuple(self.trackers), tuple(self.started))
            self.pending.discard(tracker)
            if (needs_review or opened) and tracker not in self.trackers:
                self.trackers.append(tracker)
            if opened and tracker not in self.started:
                self.started.append(tracker)
            if finished and tracker not in self.started and tracker in self.trackers:
                self.trackers.remove(tracker)
            if before != (len(self.pending), tuple(self.trackers), tuple(self.started)):
                _emit("dupe_review", {"trackers": self.trackers, "started": self.started, "checking": len(self.pending)})


@contextlib.contextmanager
def dupe_review_scope(trackers: Iterable[str]) -> Generator[None]:
    """Share review discovery across this batch's concurrent tracker checks."""
    if not enabled():
        yield
        return
    names = [plain_text(name, 100, markup=False) for name in itertools.islice(trackers, MAX_LIST_ITEMS)]
    progress = _DupeReviewProgress(names)
    token = _dupe_review.set(progress)
    try:
        _emit("dupe_review", {"trackers": [], "started": [], "checking": len(progress.pending)})
        yield
    finally:
        _dupe_review.reset(token)


def dupe_review_ready(tracker: str, *, needs_review: bool = False, finished: bool = False) -> None:
    """Record a resolved check, excluding trackers that need no manual review."""
    progress = _dupe_review.get()
    if enabled() and progress is not None:
        progress.update(plain_text(tracker, 100, markup=False), needs_review=needs_review, finished=finished)


@contextlib.contextmanager
def numbered_options(
    options: Iterable[Any],
    *,
    actions: Iterable[tuple[str, str]] = (),
    start: int = 1,
    images: Iterable[str] = (),
    details: Iterable[Mapping[str, Any]] = (),
    hint: str = "",
) -> Generator[None]:
    """Show the numbered list printed before a free-text prompt as answer buttons.

    The terminal prints the list and asks for its number; the GUI only gets
    the question, so the list is attached here. Option N is answered with
    its number counted from ``start``; ``actions`` are other accepted
    answers as ``(answer, label)``, for example ``("0", "Skip")`` or
    ``("", "Keep it")`` for pressing Enter. ``images`` are optional
    thumbnail URLs, one per option ("" for none), such as posters.
    ``details`` are optional, one per option: ``meta`` (a short line such as
    IDs), ``text`` (a synopsis) and ``link``/``link_label`` (the entry on its
    site, e.g. TMDb), shown under the option's label, and ``flag`` (a
    lowercase ISO 3166-1 alpha-2 country code, shown as its flag). ``hint``
    explains above the list why the question is asked.
    """
    thumbnails = [_http_link(image) if image else "" for image in images]
    context: dict[str, Any] = {"kind": "options", "options": list(options), "actions": list(actions), "start": str(int(start))}
    if any(thumbnails):
        context["images"] = thumbnails
    option_details = [
        {
            "meta": plain_text(detail.get("meta"), 300, markup=False),
            "text": plain_text(detail.get("text"), 400, markup=False),
            "link": _http_link(detail.get("link")) if detail.get("link") else "",
            "link_label": plain_text(detail.get("link_label"), 40, markup=False),
            "flag": flag if _FLAG_CODE.fullmatch(flag := str(detail.get("flag") or "")) else "",
        }
        for detail in details
    ]
    if any(any(detail.values()) for detail in option_details):
        context["details"] = option_details
    if hint:
        context["hint"] = plain_text(hint, 600, markup=False)
    with prompt_context(**context):
        yield


def answer_buttons(actions: Iterable[tuple[str, str]]) -> contextlib.AbstractContextManager[None]:
    """Show the answers a free-text prompt accepts (``(answer, label)``) as buttons."""
    return numbered_options((), actions=actions)


def field_prompt(
    title: str,
    summary: Mapping[str, Any] | None = None,
    *,
    focus: str = "",
    hint: str = "",
    actions: Iterable[tuple[str, str]] = (),
    placeholder: str = "",
) -> contextlib.AbstractContextManager[None]:
    """Show a free-text question as a form field with what it is about.

    The terminal prints the facts a question refers to (the release's
    current metadata, the tracks without a language) before asking; the GUI
    shows them as a table instead of raw output. ``summary`` maps labels to
    values, and the row named ``focus`` is the one being asked for (shown
    even when empty). ``actions`` are other accepted answers as
    ``(answer, label)``, such as ``("", "Keep 2024")`` or a suggested value;
    ``hint`` explains what is accepted and ``placeholder`` fills the input.
    """
    rows: dict[str, str] = {}
    for label, value in (summary or {}).items():
        text = ", ".join(str(part) for part in cast(Iterable[Any], value)) if isinstance(value, (list, tuple)) else "" if value is None else str(value)
        if text.strip() or label == focus:
            rows[label] = text
    context: dict[str, Any] = {"kind": "field", "title": title, "summary": rows, "actions": list(actions)}
    if focus:
        context["focus"] = focus
    if hint:
        context["hint"] = hint
    if placeholder:
        context["placeholder"] = placeholder
    return prompt_context(**context)


def editor_available() -> bool:
    """Whether an "edit" answer may open a text editor.

    A Web UI run has no terminal on the server, so the editor would open
    where nobody sees it. Descriptions are edited in the Web UI's own
    description review instead.
    """
    return os.environ.get("UA_WEBUI_ACTIVE") != "1"


def letter_prompt(choices: Iterable[tuple[str, str]], enter: str) -> tuple[str, list[tuple[str, str]]]:
    """Build an "Enter 'x' to ..., or press Enter to ..." question and its answer buttons.

    ``choices`` are ``(letter, action)`` pairs. An ``e`` (edit) choice is left
    out when no editor is available, so the question never offers it.
    """
    available = [(letter, action) for letter, action in choices if letter != "e" or editor_available()]
    offered = ", ".join(f"'{letter}' to {action}" for letter, action in available)
    question = f"Enter {offered}, or press Enter to {enter}: " if offered else f"Press Enter to {enter}: "
    buttons = [("", enter[:1].upper() + enter[1:])] + [(letter, action[:1].upper() + action[1:]) for letter, action in available]
    return question, buttons


def _context_payload() -> dict[str, Any] | None:
    """Serialize prompt details, including explanations from an active tracker check."""
    # Context values (release names, option labels) are plain text from tags or
    # trackers; parsing them as markup would drop text like "[remastered]".
    context = dict(_prompt_context.get() or {})
    check = _tracker_check.get()
    if check is not None and check.messages:
        context.setdefault("tracker", check.tracker)
        context.setdefault("check_messages", check.messages)
    if not context:
        return None
    payload: dict[str, Any] = {}
    for name, value in context.items():
        if isinstance(value, Mapping):
            entries = list(cast(Mapping[Any, Any], value).items())[:MAX_LIST_ITEMS]
            payload[name] = {plain_text(k, 64, markup=False): plain_text(v, MAX_TEXT_LENGTH if name == "summary" else 300, markup=False) for k, v in entries}
        elif isinstance(value, list):
            # Lists keep their order; (answer, label) pairs become two-item lists.
            items = cast(list[Any], value)[:MAX_LIST_ITEMS]
            payload[name] = [
                [plain_text(part, 300, markup=False) for part in item]
                if isinstance(item, tuple)
                # Option details are already plain and bounded by numbered_options.
                else dict(cast(Mapping[str, Any], item))
                if isinstance(item, Mapping)
                else plain_text(item, MAX_TEXT_LENGTH if name == "check_messages" else 300, markup=False)
                for item in items
            ]
        elif isinstance(value, bool):
            payload[name] = value
        elif value is not None:
            payload[name] = plain_text(value, MAX_TEXT_LENGTH if name == "hint" else 300, markup=False)
    return payload


def prompt_open(prompt_type: Literal["yes_no", "text", "choice", "multi_choice"], question: Any, *, choices: Iterable[Any] = (), default: Any = None) -> int | None:
    """Announce an interactive prompt and return its id for ``prompt_close``."""
    from src.console import check_prompt_allowed

    # A blocked question must not flash up in the Web UI before it is refused.
    check_prompt_allowed()
    if not enabled():
        return None
    prompt_id = next(_prompt_ids)
    payload: dict[str, Any] = {"action": "open", "id": prompt_id, "type": prompt_type, "question": plain_text(question)}
    choice_labels = [plain_text(choice, 300, markup=False) for choice in itertools.islice(choices, MAX_LIST_ITEMS)]
    if choice_labels:
        payload["choices"] = choice_labels
    if isinstance(default, bool):
        payload["default"] = default
    elif default is not None:
        payload["default"] = plain_text(default, 300, markup=False)
    context = _context_payload()
    if context:
        payload["context"] = context
        progress = _dupe_review.get()
        if progress is not None and context.get("kind") == "dupes" and context.get("tracker"):
            progress.update(str(context["tracker"]), opened=True)
    _emit("prompt", payload)
    return prompt_id


def prompt_close(prompt_id: int | None) -> None:
    if prompt_id is not None:
        _emit("prompt", {"action": "close", "id": prompt_id})


def _release_entries(entries: Iterable[Mapping[str, Any] | str], source_size: int | None) -> list[dict[str, Any]]:
    """Name, link and size of releases on a site, with the terminal's size-difference colour."""
    from src.uphelper import get_color_for_diff, parse_size_to_bytes

    items: list[dict[str, Any]] = []
    seen_links: set[str] = set()
    for entry in entries:
        if isinstance(entry, Mapping):
            link = _http_link(entry.get("link"))
            if link and link in seen_links:
                continue
            if link:
                seen_links.add(link)
            item: dict[str, Any] = {"name": plain_text(entry.get("name"), 300, markup=False)}
            if link:
                item["link"] = link
            size = parse_size_to_bytes(entry.get("size")) if entry.get("size") else None
            if size:
                item["size"] = size
                if source_size:
                    diff = (size - source_size) / source_size
                    item["diff_pct"] = round(diff * 100)
                    # Red means nearly the same size as the upload, green very different.
                    item["color"] = f"#{get_color_for_diff(abs(diff))}"
        else:
            item = {"name": plain_text(entry, 300, markup=False)}
        if item["name"]:
            items.append(item)
        if len(items) >= MAX_LIST_ITEMS:
            break
    return items


def dupes(tracker: str, entries: Iterable[Mapping[str, Any] | str], *, source_size: int | None = None, note: str = "", trumpable: bool = False) -> None:
    """Report the possible duplicates shown before an "upload anyway?" prompt."""
    if not enabled():
        return
    payload: dict[str, Any] = {"tracker": plain_text(tracker, 64), "entries": _release_entries(entries, source_size), "trumpable": bool(trumpable)}
    if note:
        payload["note"] = plain_text(note)
    _emit("dupes", payload)


def slot(
    tracker: str,
    verdict: str,
    title: str,
    reason: str,
    *,
    slot_name: str = "",
    why: str = "",
    conflicts: Iterable[Mapping[str, Any]] = (),
    notes: Iterable[str] = (),
    rules_date: date | None = None,
    source_size: int | None = None,
) -> None:
    """Report a tracker's slot recommendation with the same detail as the terminal box."""
    if not enabled():
        return
    payload: dict[str, Any] = {
        "tracker": plain_text(tracker, 64),
        "verdict": plain_text(verdict, 16).lower(),
        "title": plain_text(title, 200),
        "reason": plain_text(reason),
    }
    if slot_name:
        payload["slot"] = plain_text(slot_name, 200)
    if why:
        payload["why"] = plain_text(why)
    conflict_items = _release_entries(conflicts, source_size)
    if conflict_items:
        payload["conflicts"] = conflict_items
    note_items = [plain_text(note) for note in itertools.islice(notes, MAX_LIST_ITEMS) if note]
    if note_items:
        payload["notes"] = note_items
    if rules_date is not None:
        age_days = (datetime.now().astimezone().date() - rules_date).days
        age = "today" if age_days <= 0 else f"{age_days} day{'s' if age_days != 1 else ''} ago"
        payload["rules"] = f"Rules as of {rules_date.isoformat()} ({age}). This is only a recommendation; tracker rules change over time."
    _emit("slot", payload)


def tracker_result(
    tracker: str,
    status: TrackerStatus,
    *,
    link: Any = None,
    torrent_id: Any = None,
    message: Any = None,
    duration: float | None = None,
) -> None:
    if not enabled() or status not in TRACKER_STATUSES:
        return
    payload: dict[str, Any] = {"tracker": plain_text(tracker, 64), "status": status}
    url = _http_link(link)
    if url:
        payload["link"] = url
    if torrent_id not in (None, ""):
        payload["torrent_id"] = plain_text(torrent_id, 64)
    text = plain_text(message) if message else ""
    if text:
        payload["message"] = text
    if isinstance(duration, (int, float)) and duration > 0:
        payload["duration"] = round(float(duration), 2)
    _emit("tracker", payload)


def request_match(tracker: str, name: Any, *, link: Any = None, reward: Any = None, status: Any = None, exact: bool = False) -> None:
    if not enabled():
        return
    payload: dict[str, Any] = {"tracker": plain_text(tracker, 64), "name": plain_text(name, 300, markup=False), "exact": bool(exact)}
    url = _http_link(link)
    if url:
        payload["link"] = url
    if reward not in (None, ""):
        payload["reward"] = plain_text(reward, 100)
    if status not in (None, ""):
        payload["status"] = plain_text(status, 100)
    if payload["name"]:
        _emit("request", payload)


def tracker_status_from_meta(status: Mapping[str, Any], *, final: bool, upload_started: bool = True) -> TrackerStatus:
    """Classify a ``meta.tracker_status`` entry for the results panel.

    ``upload_started`` is False when the item ended before its upload stage,
    e.g. too few trackers passed; approved trackers were then never tried.
    """
    message = str(status.get("status_message") or "").lower()
    if status.get("banned"):
        return "banned"
    if status.get("upload_success") is True:
        return "success"
    if status.get("upload_success") is False:
        return "failed"
    if status.get("dupe"):
        return "dupe"
    if status.get("skipped"):
        return "skipped"
    if "dupe" in message or "duplicate" in message:
        return "dupe"
    if status.get("upload") is True:
        if not final:
            return "pending"
        # An approved upload with no result by the end of the item errored out.
        return "failed" if upload_started else "skipped"
    return "skipped"


_DEFAULT_STATUS_MESSAGES: dict[str, str] = {
    "banned": "Release group is banned on this tracker",
    "dupe": "Possible dupe on this tracker",
    "skipped": "Not uploaded",
    "failed": "Upload did not complete",
}


def publish_tracker_statuses(tracker_status: Mapping[str, Any], *, final: bool = False) -> None:
    """Send every tracker's current state, e.g. after dupe checks or at the end of an item."""
    if not enabled():
        return
    for tracker, raw_status in tracker_status.items():
        if not isinstance(raw_status, Mapping) or str(tracker).upper() in {"MANUAL", "USENET"}:
            continue
        status = cast(Mapping[str, Any], raw_status)
        resolved = tracker_status_from_meta(status, final=final, upload_started="upload" in _started_stages)
        if resolved == "success":
            tracker_result(str(tracker), resolved, link=status.get("torrent_link"), torrent_id=status.get("torrent_id"))
            continue
        if resolved == "pending":
            # Passed the dupe check and approved; the upload result comes later.
            tracker_result(str(tracker), resolved, message="No potential dupes found" if status.get("dupe") is False else None)
            continue
        message = status.get("status_message") or _DEFAULT_STATUS_MESSAGES.get(resolved)
        tracker_result(str(tracker), resolved, message=message)
