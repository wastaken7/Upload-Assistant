"""Upload form previews for the Web UI's "Is this correct?" prompt.

Before the release is confirmed, each tracker builds the form it will send
with ``preview=True``: the same code as the upload, without what is not known
yet (the description waits for screenshots, some fields come from the
tracker itself) and without network requests or image uploads.

The Web UI shows these previews and can change their simple fields. Accepted
changes are kept in ``meta.payload_edits`` and applied by the tracker right
before it posts the form; everything else is still built at upload time.
"""

from __future__ import annotations

import ast
import inspect
import json
import textwrap
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass, field
from functools import cache
from typing import Any, Literal, cast

from rich.markup import escape

from src import webui_events
from src.console import PromptBlockedError, logger
from src.meta import Meta

Kind = Literal["text", "choice", "flag", "readonly", "deferred"]

# Form fields that carry credentials are never shown or changed.
SECRET_FIELDS = frozenset({"auth", "user", "username", "uid", "userid", "user_id", "email", "pass", "cookie"})
SECRET_PARTS = ("passkey", "password", "token", "csrf", "apikey", "api_key", "authkey", "secret", "announce", "torrent_pass", "session")
# Bytes the previews may take in the prompt event (webui_events drops events over 256 KB).
GUI_BUDGET = 160_000
TEXT_LIMIT = 255
SHOWN_TEXT = 300
DESCRIPTION_NOTE = "Built after the screenshots are uploaded"
FROM_TRACKER_NOTE = "Filled in from the tracker's reply at upload time"
SCREENSHOTS_NOTE = "Uploaded after this question"
ASKED_NOTE = "Asked after this question"


class Later(str):
    """A form value that a preview leaves for upload time; ``describe`` shows it with its note."""

    note: str

    def __new__(cls, note: str) -> Later:
        value = super().__new__(cls, "")
        value.note = note
        return value


# What a form field stands for, so the Web UI can warn when a change there is
# better made another way (for example a wrong name is fixed with --imdb, not
# by retyping it). A tracker's spec sets ``role`` where its key means another thing.
# A spec sets role="none" where its key's usual role does not apply.
ROLE_BY_KEY: dict[str, str] = {
    **dict.fromkeys(("name", "title", "filename", "file_name", "subject", "rlsname", "scenename"), "name"),
    **dict.fromkeys(("titulobrasileiro", "title_br"), "title"),
    **dict.fromkeys(
        (
            "tmdb",
            "tmdb_id",
            "tmdbid",
            "imdb",
            "imdb_id",
            "imdbid",
            "imdbId",
            "imdb_input",
            "imdblink",
            "imdbURL",
            "imdb_c",
            "movie_imdb",
            "tv_imdb",
            "infosite",
            "t_link",
            "url",
            "media_ref",
            "tvdb",
            "tvdb_id",
            "mal",
            "mal_id",
            "igdb",
            "tvmazeid",
            "tvMazeURL",
            "animeid",
            "work",
            "douban",
            "pt_gen",
        ),
        "external_id",
    ),
    **dict.fromkeys(("category", "category_id", "cat", "catid", "type"), "category"),
    **dict.fromkeys(
        ("type_id", "subcat", "medium", "medium_sel[4]", "source", "other_source", "source_sel", "rip_type_id", "qualidade", "media", "media_type"),
        "release_type",
    ),
    **dict.fromkeys(("resolution", "resolution_id", "standard", "standard_sel[4]", "video_quality_id", "quality", "resolucaow", "resolucaoh"), "resolution"),
    **dict.fromkeys(("season_number", "episode_number", "season", "episode", "tvdb_season", "tvdb_episode", "temporada", "temporada_e", "episodio"), "season_episode"),
    **dict.fromkeys(("releasegroup", "release_group", "team_sel[4]"), "group"),
    **dict.fromkeys(("edition", "custom_edition", "remaster_title", "versao"), "edition"),
    **dict.fromkeys(("featured", "sticky", "doubleup", "free", "freeleech", "frileech", "internal", "internalrel", "exclusive", "jinzhuan", "origin"), "staff_flag"),
}


@dataclass(frozen=True)
class Spec:
    """How a known form field is labelled and edited."""

    label: str
    kind: Kind = "text"
    choices: tuple[tuple[Any, str], ...] = ()
    on: Any = "1"
    off: Any = "0"
    max_length: int = TEXT_LIMIT
    numeric: bool = False
    # What the field stands for; overrides ROLE_BY_KEY where a key means something else.
    role: str = ""


def text(label: str, *, max_length: int = TEXT_LIMIT, numeric: bool = False, role: str = "") -> Spec:
    return Spec(label, "text", max_length=max_length, numeric=numeric, role=role)


def number(label: str, *, role: str = "") -> Spec:
    return Spec(label, "text", max_length=20, numeric=True, role=role)


def flag(label: str, on: Any = "1", off: Any = "0", *, role: str = "") -> Spec:
    """A checkbox; ``off=None`` leaves the field out of the form when unchecked."""
    return Spec(label, "flag", on=on, off=off, role=role)


def readonly(label: str) -> Spec:
    return Spec(label, "readonly")


def choice(label: str, options: Mapping[Any, Any] | Iterable[Any], *, by_label: bool = False, role: str = "") -> Spec:
    """A drop-down from values or ``(value, label)`` pairs, or a ``{label: value}`` map with ``by_label``.

    Labels that share one value (for example 1080p and 1440p) become one option.
    """
    if isinstance(options, Mapping):
        mapping = cast(Mapping[Any, Any], options)
        pairs = [(value, name) for name, value in mapping.items()] if by_label else list(mapping.items())
    else:
        pairs = [item if isinstance(item, tuple) else (item, item) for item in cast(Iterable[Any], options)]
    grouped: dict[str, tuple[Any, list[str]]] = {}
    for value, name in pairs:
        if value is None or isinstance(value, (dict, list)):
            continue
        entry = grouped.setdefault(str(value), (value, []))
        name_text = str(name)
        if name_text not in entry[1]:
            entry[1].append(name_text)
    return Spec(label, "choice", choices=tuple((value, " / ".join(names)) for value, names in grouped.values()), role=role)


@cache
def code_options(getter: Callable[..., Any]) -> tuple[tuple[int | str, str], ...]:
    """The values a ``get_*`` method can return, labelled with the names its code gives them.

    Reads the method's source: values bound to local names that are returned
    (``web_dl = 4``), dict and pair lookups (``"x264": 1``, ``"webdl": "WEB-DL"``),
    and returned literals, named after what their ``if`` matched. Only these values
    can come out of the method, so they are the ones a drop-down offers.
    """
    try:
        tree = ast.parse(textwrap.dedent(inspect.getsource(getter)))
    except OSError, TypeError, SyntaxError:
        return ()
    returned: set[str] = set()
    literals: list[Any] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Return) and node.value is not None:
            for part in ast.walk(node.value):
                if isinstance(part, ast.Name):
                    returned.add(part.id)
                elif isinstance(part, ast.Constant):
                    literals.append(part.value)
    labels: dict[int | str, list[str]] = {}

    def add(value: Any, label: str) -> None:
        if (type(value) is int or type(value) is str) and value != "":
            names = labels.setdefault(value, [])
            label = value if isinstance(value, str) else label
            if label and label not in names:
                names.append(label)

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and isinstance(node.value, ast.Constant):
            if node.targets[0].id in returned:
                add(node.value.value, node.targets[0].id.replace("_", " "))
        elif isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values, strict=True):
                if isinstance(key, ast.Constant) and isinstance(key.value, str) and isinstance(value, ast.Constant):
                    add(value.value, key.value)
        elif isinstance(node, ast.Tuple) and len(node.elts) == 2:
            first, second = node.elts
            if isinstance(first, ast.Constant) and isinstance(first.value, str) and isinstance(second, ast.Constant) and type(second.value) is int:
                add(second.value, first.value)
        elif isinstance(node, ast.If):
            # ``if "2160" in resolution: return 6`` names option 6 after what it matched.
            tested = [part.value for part in ast.walk(node.test) if isinstance(part, ast.Constant) and isinstance(part.value, str)]
            for statement in node.body:
                if isinstance(statement, ast.Return) and isinstance(statement.value, ast.Constant):
                    for matched in tested:
                        add(statement.value.value, matched)
    for value in literals:
        add(value, "")
    items = list(labels.items())
    if all(type(value) is int for value, _names in items):
        items.sort(key=lambda item: cast(int, item[0]))
    return tuple((value, " / ".join(names[:4]) or str(value)) for value, names in items)


async def mapping_choice(label: str, getter: Any, meta: Meta, key: str) -> Spec | None:
    """A drop-down from a tracker's ``get_*_id(meta, mapping_only=True)`` map, if it is a flat one.

    A getter that ignores ``mapping_only`` returns ``{key: id}`` instead; its field stays a text box.
    """
    try:
        mapping = await getter(meta, mapping_only=True)
    except Exception:
        return None
    if not isinstance(mapping, Mapping) or not mapping or key in mapping:
        return None
    values = cast(Mapping[Any, Any], mapping)
    if not all(isinstance(value, (str, int)) and not isinstance(value, bool) for value in values.values()):
        return None
    return choice(label, values, by_label=True)


@dataclass
class PayloadField:
    key: str
    label: str
    kind: Kind
    value: Any = None
    choices: tuple[tuple[Any, str], ...] = ()
    on: Any = "1"
    off: Any = "0"
    max_length: int = TEXT_LIMIT
    numeric: bool = False
    note: str = ""
    role: str = ""

    @property
    def editable(self) -> bool:
        return self.kind in ("text", "choice", "flag")

    def display(self, value: Any) -> str:
        """Readable form of a raw form value."""
        if self.kind == "flag":
            return "on" if value == self.on else "off"
        if self.kind == "choice":
            for option, name in self.choices:
                if str(option) == str(value):
                    return name if name == str(option) else f"{name} ({option})"
        return str(value) if value is not None else ""

    def parse(self, value: Any) -> tuple[bool, Any]:
        """Turn a value sent by the Web UI into the raw form value, if it is valid."""
        if self.kind == "flag":
            return (True, self.on if value else self.off) if isinstance(value, bool) else (False, None)
        if not isinstance(value, str):
            return False, None
        if self.kind == "choice":
            for option, _name in self.choices:
                if str(option) == value:
                    return True, option
            return False, None
        if self.kind != "text":
            return False, None
        value = value.strip()
        if "\n" in value or "\r" in value or len(value) > self.max_length:
            return False, None
        if not value and str(self.value or ""):
            return False, None
        if self.numeric and value and not (value.isascii() and value.isdigit()):
            return False, None
        if isinstance(self.value, int) and not isinstance(self.value, bool) and value:
            return True, int(value)
        return True, value

    def to_gui(self, choice_refs: dict[str, str]) -> dict[str, Any]:
        item: dict[str, Any] = {"key": self.key, "label": webui_events.plain_text(self.label, 100, markup=False), "kind": self.kind}
        if self.kind == "flag":
            item["value"] = self.value == self.on
        elif self.kind == "choice":
            item["value"] = str(self.value)
            item["display"] = webui_events.plain_text(self.display(self.value), SHOWN_TEXT, markup=False)
            options = [[str(option), webui_events.plain_text(name, 200, markup=False)] for option, name in self.choices]
            ref_key = json.dumps(options, separators=(",", ":"))
            item["choices"] = choice_refs.setdefault(ref_key, f"c{len(choice_refs)}")
        elif self.kind == "text":
            item["value"] = webui_events.plain_text(self.value, self.max_length, markup=False)
            item["max"] = self.max_length
            if self.numeric:
                item["numeric"] = True
        elif self.kind == "readonly":
            item["value"] = _readonly_text(self.value)
        if self.note:
            item["note"] = webui_events.plain_text(self.note, SHOWN_TEXT, markup=False)
        if self.role and self.editable:
            item["role"] = self.role
        return item


@dataclass
class TrackerPreview:
    tracker: str
    name: str | None
    fields: list[PayloadField] = field(default_factory=list)

    def find(self, key: str) -> PayloadField | None:
        return next((item for item in self.fields if item.key == key), None)


def _readonly_text(value: Any) -> str:
    if value is None or value == "":
        return "(empty)"
    if isinstance(value, (bytes, bytearray)):
        return f"{len(value):,} bytes"
    if isinstance(value, (list, tuple)):
        parts = [str(item) for item in cast(Iterable[Any], value)]
        joined = ", ".join(parts)
        return webui_events.plain_text(joined, SHOWN_TEXT, markup=False) if len(joined) <= SHOWN_TEXT else f"{len(parts)} items"
    if isinstance(value, dict):
        return f"{len(cast(dict[Any, Any], value))} entries"
    text_value = str(value)
    if len(text_value) > SHOWN_TEXT or "\n" in text_value:
        return f"{len(text_value):,} characters"
    return webui_events.plain_text(text_value, SHOWN_TEXT, markup=False)


def is_secret(key: str, extra: Iterable[str] = ()) -> bool:
    lowered = key.strip().lower()
    return lowered in SECRET_FIELDS or lowered in {item.lower() for item in extra} or any(part in lowered for part in SECRET_PARTS)


def _humanize(key: str) -> str:
    words = key.replace("_", " ").replace("-", " ").strip()
    return words[:1].upper() + words[1:] if words else key


def _field(key: str, value: Any, spec: Spec | None) -> PayloadField:
    """A field is only editable through its spec; anything else is shown as it will be sent.

    Most form fields are drop-downs or checkboxes on the site, so a field without
    a spec is never offered as free text.
    """
    label = spec.label if spec else _humanize(key)
    if spec is None or spec.kind == "readonly":
        return PayloadField(key, label, "readonly", value)
    if spec.kind == "flag":
        # Some getters format a boolean as "True"/"False" rather than the usual "1"/"0".
        for on, off in ((spec.on, spec.off), ("1", "0"), ("True", "False"), (1, 0), (True, False)):
            if any(type(value) is type(option) and value == option for option in (on, off)):
                return PayloadField(key, label, "flag", value, on=on, off=off)
    elif spec.kind == "choice" and spec.choices and isinstance(value, (str, int)) and not isinstance(value, bool):
        choices = spec.choices
        if not any(str(option) == str(value) for option, _name in choices):
            choices = ((value, str(value)), *choices)
        return PayloadField(key, label, "choice", value, choices=choices)
    elif spec.kind == "text":
        if isinstance(value, int) and not isinstance(value, bool):
            return PayloadField(key, label, "text", value, max_length=spec.max_length, numeric=True)
        if isinstance(value, str) and "\n" not in value and "\r" not in value and len(value) <= spec.max_length:
            numeric = spec.numeric and (not value or value.isdigit())
            return PayloadField(key, label, "text", value, max_length=spec.max_length, numeric=numeric)
    return PayloadField(key, label, "readonly", value)


def describe(
    tracker: str,
    data: Mapping[str, Any],
    specs: Mapping[str, Spec] | None = None,
    *,
    deferred: Mapping[str, str] | None = None,
    name_key: str = "name",
    name: str | None = None,
    secret_fields: Iterable[str] = (),
) -> TrackerPreview:
    """Turn a preview form into labelled fields; ``deferred`` names fields filled in later."""
    specs = specs or {}
    deferred = deferred or {}
    secret = tuple(secret_fields)
    fields: list[PayloadField] = []
    for key, value in data.items():
        key = str(key)
        if is_secret(key, secret) or key in deferred:
            continue
        if isinstance(value, Later):
            spec = specs.get(key)
            fields.append(PayloadField(key, spec.label if spec else _humanize(key), "deferred", note=value.note))
            continue
        fields.append(_field(key, value, specs.get(key)))
    # Checkboxes left out of a form when unchecked can still be ticked.
    for key, spec in specs.items():
        if key not in data and spec.kind == "flag" and spec.off is None and not is_secret(key, secret):
            fields.append(PayloadField(key, spec.label, "flag", None, on=spec.on, off=None))
    for key, note in deferred.items():
        spec = specs.get(key)
        fields.append(PayloadField(key, spec.label if spec else _humanize(key), "deferred", note=note))
    for item in fields:
        spec = specs.get(item.key)
        role = (spec.role if spec else "") or ROLE_BY_KEY.get(item.key, "")
        item.role = "" if role == "none" else role
    if name is None and isinstance(data.get(name_key), str):
        name = cast(str, data[name_key])
    return TrackerPreview(tracker, name, fields)


def gui_payloads(previews: Iterable[TrackerPreview]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    """Previews and their shared drop-down lists for the prompt, kept within the event budget."""
    refs: dict[str, str] = {}
    items: list[dict[str, Any]] = [
        {
            "tracker": preview.tracker,
            "name": webui_events.plain_text(preview.name or "", SHOWN_TEXT, markup=False),
            "fields": [item.to_gui(refs) for item in preview.fields],
        }
        for preview in previews
    ]
    tables = {ref: options for options, ref in refs.items()}
    size = len(json.dumps(items, separators=(",", ":"))) + sum(len(options) + 20 for options in tables.values())
    notice = ""
    # Long lists (distributors) go first; those fields are then shown but not editable.
    for ref in sorted(tables, key=lambda ref: len(tables[ref]), reverse=True):
        if size <= GUI_BUDGET:
            break
        size -= len(tables.pop(ref)) + 20
        notice = "Some lists were too long to show, so those fields can't be changed here."
    if size > GUI_BUDGET:
        return [], [], "The upload data is too large to show here."
    for preview_item in items:
        for gui_field in cast(list[dict[str, Any]], preview_item["fields"]):
            if "choices" in gui_field and gui_field["choices"] not in tables:
                del gui_field["choices"]
    return items, [{"id": ref, "choices": json.loads(options)} for ref, options in tables.items()], notice


def accept_edits(meta: Meta, previews: Mapping[str, TrackerPreview], edits: Any) -> list[str]:
    """Keep the valid changes sent by the Web UI in ``meta.payload_edits``; return what changed."""
    meta.payload_edits = {}
    if not isinstance(edits, Mapping):
        return []
    changes: list[str] = []
    for tracker, values in cast(Mapping[Any, Any], edits).items():
        preview = previews.get(str(tracker))
        if preview is None or not isinstance(values, Mapping):
            continue
        accepted: dict[str, Any] = {}
        for key, value in cast(Mapping[Any, Any], values).items():
            item = preview.find(str(key))
            if item is None or not item.editable:
                continue
            valid, raw = item.parse(value)
            if not valid:
                logger.warning(f"[yellow]{escape(preview.tracker)}: ignored an invalid value for {escape(item.label)}.[/yellow]")
                continue
            if raw == item.value or (item.kind == "flag" and item.value is None and raw is None):
                continue
            accepted[item.key] = raw
            changes.append(f"{preview.tracker} {item.label}: {item.display(item.value)} → {item.display(raw)}")
        if accepted:
            meta.payload_edits[preview.tracker] = accepted
    return changes


async def unless_asked[T](value: Awaitable[T], note: str = ASKED_NOTE) -> T:
    """Await a form value that may need a question.

    While a preview is built questions are refused, so the value is left for
    upload time and shown with ``note``; the rest of the form is still previewed.
    Outside a preview nothing is refused and the value is returned as usual.
    """
    try:
        return await value
    except PromptBlockedError:
        return cast(T, Later(note))


def apply_payload_edits(meta: Meta, tracker: str, data: dict[str, Any]) -> dict[str, Any]:
    """Apply the Web UI's changes for ``tracker`` to its upload form, in place."""
    edits = cast(dict[str, dict[str, Any]], getattr(meta, "payload_edits", None) or {}).get(tracker)
    if not edits:
        return data
    for key, value in edits.items():
        if value is None:
            data.pop(key, None)
        else:
            data[key] = value
    logger.info(f"{tracker}: [green]Using upload data changed in the Web UI:[/green] {escape(', '.join(edits))}")
    return data
