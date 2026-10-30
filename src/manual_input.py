# Upload Assistant © 2026 Audionut & wastaken7 — Licensed under UAPL v1.0
"""Questions about release details the app cannot decide on its own.

Some details have no central source (there is no TMDB for adult releases, a
game's subcategory is not in IGDB, a tracker wants a pack category). Call
sites describe such a question with :class:`Question` and call :func:`ask`,
which resolves it in this order:

1. an answer given on the command line (``--answer KEY=VALUE``);
2. an answer given earlier for the same release (``meta.manual_answers``,
   saved in ``meta.json`` and reloaded on the next run);
3. the unattended policy, when nobody is there to answer;
4. an interactive prompt, which the Web UI's GUI mode shows as a form.

The CLI prompt is a plain ``cli_ui`` call, so the GUI receives it through the
existing prompt events in :mod:`src.console` and :mod:`src.webui_events`.
"""

from __future__ import annotations

import asyncio
import contextlib
import contextvars
import inspect
import json
import re
import weakref
from collections.abc import AsyncGenerator, Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, cast

import aiofiles
import cli_ui

from src import webui_events
from src.console import logger, prompt_in_thread
from src.meta import Meta

QuestionKind = Literal["confirm", "text", "list", "choice", "multi_choice"]
UnattendedPolicy = Literal["default", "skip_tracker", "fail"]
Validator = Callable[[Any], str | Awaitable[str | None] | None]

_YES = frozenset({"y", "yes", "true", "1", "s", "sim"})
_NO = frozenset({"n", "no", "false", "0", "nao", "não"})
_LIST_SEPARATOR = re.compile(r"[,;]")


@dataclass(frozen=True)
class Choice:
    value: str
    label: str = ""

    @property
    def display(self) -> str:
        return self.label or self.value


@dataclass(frozen=True)
class Question:
    """One question about the release.

    ``key`` names the answer in ``--answer`` and ``meta.manual_answers``; it
    must be listed in :data:`src.manual_questions.QUESTION_KEYS`. Answers are
    ``bool`` for ``confirm``, ``str`` for ``text`` and ``choice`` (the
    choice's ``value``) and ``list[str]`` for ``list`` and ``multi_choice``.

    An empty answer means "no answer" (``ask`` returns ``None``) unless
    ``default`` is set or ``empty_ok`` makes it a valid answer ("" or []).
    ``validate`` returns an error message for a rejected answer and may be
    async. ``store`` copies an accepted answer into the matching ``Meta``
    field, so later code and other trackers see it.
    """

    key: str
    kind: QuestionKind
    prompt: str
    title: str = ""
    choices: Sequence[Choice] = ()
    default: Any = None
    hint: str = ""
    placeholder: str = ""
    summary: Mapping[str, Any] = field(default_factory=dict[str, Any])
    focus: str = ""
    tracker: str | None = None
    unattended: UnattendedPolicy = "skip_tracker"
    empty_ok: bool = False
    remember: bool = True
    validate: Validator | None = None
    store: Callable[[Meta, Any], None] | None = None


# One prompt at a time across trackers; a holder may ask follow-up questions.
_prompt_locks: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock] = weakref.WeakKeyDictionary()
_prompt_lock_held: contextvars.ContextVar[bool] = contextvars.ContextVar("ua_prompt_lock_held", default=False)


@contextlib.asynccontextmanager
async def prompt_session() -> AsyncGenerator[None]:
    """Hold the shared prompt lock, unless this task already holds it."""
    if _prompt_lock_held.get():
        yield
        return
    loop = asyncio.get_running_loop()
    lock = _prompt_locks.get(loop)
    if lock is None:
        lock = _prompt_locks[loop] = asyncio.Lock()
    async with lock:
        token = _prompt_lock_held.set(True)
        try:
            yield
        finally:
            _prompt_lock_held.reset(token)


def is_interactive(meta: Meta) -> bool:
    return not meta.unattended or bool(meta.unattended_confirm)


def has_answer(meta: Meta, key: str) -> bool:
    """Whether ``key`` was answered on the command line or in an earlier run."""
    return key in meta.answers or key in meta.manual_answers


def split_list(raw: str) -> list[str]:
    """Split a comma or semicolon separated answer, dropping blanks and repeats."""
    items: list[str] = []
    for part in _LIST_SEPARATOR.split(raw):
        item = part.strip()
        if item and item.casefold() not in (existing.casefold() for existing in items):
            items.append(item)
    return items


def _match_choice(question: Question, raw: str) -> str | None:
    text = raw.strip()
    if text.isdigit() and 1 <= int(text) <= len(question.choices):
        return question.choices[int(text) - 1].value
    folded = text.casefold()
    for choice in question.choices:
        if folded in (choice.value.casefold(), choice.display.casefold()):
            return choice.value
    return None


def parse_answer(question: Question, raw: str) -> tuple[Any, str | None]:
    """Turn a typed answer (``--answer`` or a saved string) into the question's value."""
    text = raw.strip()
    if question.kind == "confirm":
        if text.casefold() in _YES:
            return True, None
        if text.casefold() in _NO:
            return False, None
        return None, f"'{text}' is not yes or no"
    if question.kind == "text":
        return text, None
    if question.kind == "list":
        return split_list(text), None
    if question.kind == "choice":
        value = _match_choice(question, text)
        if value is None:
            return None, f"'{text}' is not one of: {', '.join(choice.display for choice in question.choices)}"
        return value, None
    values: list[str] = []
    for part in split_list(text):
        value = _match_choice(question, part)
        if value is None:
            return None, f"'{part}' is not one of: {', '.join(choice.display for choice in question.choices)}"
        if value not in values:
            values.append(value)
    return values, None


def _is_empty(value: Any) -> bool:
    return value is None or value == "" or value == []


def _normalize(question: Question, value: Any) -> Any:
    """Apply the empty-answer rules: default, empty answer, or no answer (None)."""
    if not _is_empty(value):
        return value
    if question.default is not None:
        return question.default
    if question.empty_ok:
        return [] if question.kind in ("list", "multi_choice") else ""
    return None


def _check_saved(question: Question, value: Any) -> bool:
    """Whether a value loaded from meta.json still fits the question."""
    if question.kind == "confirm":
        return isinstance(value, bool)
    if question.kind in ("text", "choice"):
        return isinstance(value, str) and (question.kind == "text" or any(choice.value == value for choice in question.choices))
    if not isinstance(value, list):
        return False
    items = cast(list[Any], value)
    if not all(isinstance(item, str) for item in items):
        return False
    return question.kind == "list" or all(any(choice.value == item for choice in question.choices) for item in items)


async def _validate(question: Question, value: Any) -> str | None:
    if question.validate is None:
        return None
    result = question.validate(value)
    if inspect.isawaitable(result):
        result = await result
    return result


def _label(question: Question) -> str:
    return f"{question.tracker}: " if question.tracker else ""


def _ask_cli(question: Question) -> Any:
    """Ask in the terminal; runs in a worker thread."""
    if question.kind == "confirm":
        return cli_ui.ask_yes_no(question.prompt, default=bool(question.default))
    if question.kind in ("text", "list"):
        default = ", ".join(cast(list[str], question.default)) if isinstance(question.default, list) else question.default
        answer = str(cli_ui.ask_string(question.prompt, default=default) or "").strip()
        return split_list(answer) if question.kind == "list" else answer
    labels = [choice.display for choice in question.choices]
    if question.kind == "choice":
        picked = cli_ui.ask_choice(question.prompt, choices=labels, sort=False)
        return question.choices[labels.index(picked)].value if picked is not None else None
    picked_many = cli_ui.select_choices(question.prompt, choices=labels, sort=False) or []
    return [question.choices[labels.index(label)].value for label in picked_many]


def _accept(meta: Meta, question: Question, value: Any) -> Any:
    if question.remember:
        meta.manual_answers[question.key] = value
    if question.store is not None:
        question.store(meta, value)
    return value


async def ask(meta: Meta, question: Question) -> Any:
    """Resolve ``question`` and return its answer, or ``None`` when there is none."""
    label = _label(question)
    name = question.title or question.key

    raw = meta.answers.get(question.key)
    if raw is not None:
        value, error = parse_answer(question, raw)
        value = _normalize(question, value) if error is None else None
        if error is None and value is not None:
            error = await _validate(question, value)
        if error is None and value is not None:
            return _accept(meta, question, value)
        logger.info(f"{label}[red]Ignoring --answer {question.key}: {error or 'empty answer'}[/red]")

    if question.remember and question.key in meta.manual_answers:
        saved = meta.manual_answers[question.key]
        if _check_saved(question, saved) and await _validate(question, saved) is None:
            logger.info(f"{label}Using the saved answer for {name}: {_describe(question, saved)}")
            return _accept(meta, question, saved)
        meta.manual_answers.pop(question.key, None)

    if not is_interactive(meta):
        return _unattended(meta, question)

    async with prompt_session():
        while True:
            with webui_events.field_prompt(name, question.summary, focus=question.focus, hint=question.hint, placeholder=question.placeholder):
                try:
                    answer = await prompt_in_thread(_ask_cli, question)
                except EOFError:
                    return None
            value = _normalize(question, answer)
            if value is None:
                return None
            error = await _validate(question, value)
            if error is None:
                return _accept(meta, question, value)
            logger.info(f"{label}[yellow]{error}[/yellow]")


def _describe(question: Question, value: Any) -> str:
    if isinstance(value, bool):
        return "Yes" if value else "No"
    labels = {choice.value: choice.display for choice in question.choices}
    if isinstance(value, list):
        return ", ".join(labels.get(item, item) for item in value) or "None"
    return labels.get(value, value) or "None"


def _unattended(meta: Meta, question: Question) -> Any:
    label = _label(question)
    name = question.title or question.key
    if question.unattended == "default" and question.default is not None:
        logger.info(f"{label}[yellow]Unattended mode: using {_describe(question, question.default)} for {name}. Use --answer {question.key}=... to set it.[/yellow]")
        # Not remembered: an attended run of the same release should still ask.
        if question.store is not None:
            question.store(meta, question.default)
        return question.default
    if question.unattended == "skip_tracker" and question.tracker:
        logger.info(f"{label}[yellow]Unattended mode: {name} must be answered manually (--answer {question.key}=...). Skipping {question.tracker}.[/yellow]")
        meta.skipping = question.tracker
        return None
    logger.info(f"{label}[yellow]Unattended mode: {name} must be answered manually (--answer {question.key}=...).[/yellow]")
    return None


async def confirm_override(meta: Meta | None, question: str = "Do you want to upload anyway?", *, default: bool = False) -> bool:
    """Ask whether to continue despite a rule warning; unattended runs never continue.

    The answer is not remembered: the warning may differ on the next run.
    """
    if meta is not None and not is_interactive(meta):
        return False
    async with prompt_session():
        try:
            return bool(await prompt_in_thread(cli_ui.ask_yes_no, question, default=default))
        except EOFError:
            return False


async def load_saved_answers(meta: Meta) -> None:
    """Reload answers given in an earlier run of this release from its meta.json."""
    if not meta.uuid:
        return
    meta_file = Path(meta.base_dir) / "tmp" / meta.uuid / "meta.json"
    if not meta_file.is_file():
        return
    try:
        async with aiofiles.open(meta_file, encoding="utf-8") as handle:
            saved = json.loads(await handle.read()).get("manual_answers")
    except (OSError, ValueError, AttributeError) as e:
        logger.debug(f"Unable to read saved answers from {meta_file}: {e}")
        return
    if isinstance(saved, Mapping):
        for key, value in saved.items():
            meta.manual_answers.setdefault(str(key), value)


def choices_from(values: Iterable[str] | Mapping[str, str]) -> tuple[Choice, ...]:
    """Build choices from values, or from a ``{value: label}`` mapping."""
    if isinstance(values, Mapping):
        return tuple(Choice(value, label) for value, label in values.items())
    return tuple(Choice(value) for value in values)
