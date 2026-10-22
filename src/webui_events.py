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
GUI_EVENT_KINDS = frozenset({"item", "stage", "notice", "notice_group", "prompt", "dupes", "slot", "tracker", "request"})
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
_ANSI_ESCAPE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
_MARKUP_TAG = re.compile(r"\[/?[a-zA-Z#][^\[\]]*\]|\[/\]")


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
    with _stdout_lock, contextlib.suppress(Exception):
        sys.stdout.write(f"\n{event_prefix(os.environ.get(GUI_EVENT_NONCE_ENV, ''))}{line}\n")
        sys.stdout.flush()


def begin_item(path: str, index: int, total: int) -> None:
    """Start a queue item; later events are tagged with its index."""
    global _current_item, _active_stage
    _current_item = {"index": int(index), "total": int(total)}
    _active_stage = None
    _started_stages.clear()
    _emit("item", {"index": int(index), "total": int(total), "name": plain_text(Path(str(path)).name or path, 300)})


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


@contextlib.contextmanager
def prompt_context(**context: Any) -> Generator[None]:
    """Attach context (for example the tracker being asked about) to prompts in this block."""
    current = _prompt_context.get() or {}
    token = _prompt_context.set({**current, **context})
    try:
        yield
    finally:
        _prompt_context.reset(token)


@contextlib.contextmanager
def numbered_options(
    options: Iterable[Any],
    *,
    actions: Iterable[tuple[str, str]] = (),
    start: int = 1,
    images: Iterable[str] = (),
    details: Iterable[Mapping[str, Any]] = (),
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
    site, e.g. TMDb), shown under the option's label.
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
        }
        for detail in details
    ]
    if any(any(detail.values()) for detail in option_details):
        context["details"] = option_details
    with prompt_context(**context):
        yield


def answer_buttons(actions: Iterable[tuple[str, str]]) -> contextlib.AbstractContextManager[None]:
    """Show the answers a free-text prompt accepts (``(answer, label)``) as buttons."""
    return numbered_options((), actions=actions)


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
    # Context values (release names, option labels) are plain text from tags or
    # trackers; parsing them as markup would drop text like "[remastered]".
    context = _prompt_context.get()
    if not context:
        return None
    payload: dict[str, Any] = {}
    for name, value in context.items():
        if isinstance(value, Mapping):
            entries = list(cast(Mapping[Any, Any], value).items())[:MAX_LIST_ITEMS]
            payload[name] = {plain_text(k, 64, markup=False): plain_text(v, 300, markup=False) for k, v in entries}
        elif isinstance(value, list):
            # Lists keep their order; (answer, label) pairs become two-item lists.
            items = cast(list[Any], value)[:MAX_LIST_ITEMS]
            payload[name] = [
                [plain_text(part, 300, markup=False) for part in item]
                if isinstance(item, tuple)
                # Option details are already plain and bounded by numbered_options.
                else dict(cast(Mapping[str, Any], item))
                if isinstance(item, Mapping)
                else plain_text(item, 300, markup=False)
                for item in items
            ]
        elif isinstance(value, bool):
            payload[name] = value
        elif value is not None:
            payload[name] = plain_text(value, 300, markup=False)
    return payload


def prompt_open(prompt_type: Literal["yes_no", "text", "choice"], question: Any, *, choices: Iterable[Any] = (), default: Any = None) -> int | None:
    """Announce an interactive prompt and return its id for ``prompt_close``."""
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
    if status.get("dupe") or "dupe" in message or "duplicate" in message:
        return "dupe"
    if status.get("skipped"):
        return "skipped"
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
