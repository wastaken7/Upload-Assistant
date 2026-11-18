"""Helpers that read and coerce request and JSON data."""

import json
from collections.abc import Mapping, Sequence
from typing import Any, cast

from web_ui.flask_compat import request


def _as_dict(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    value_dict: dict[Any, Any] = cast(dict[Any, Any], value)
    result: dict[str, Any] = {}
    for key, item in value_dict.items():
        result[str(key)] = item
    return result


def _as_str_list(value: Any) -> list[str] | None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return None
    value_seq: Sequence[Any] = cast(Sequence[Any], value)
    return [str(item) for item in value_seq]


def _json_load_dict(text: str) -> dict[str, Any]:
    loaded = json.loads(text)
    return _as_dict(loaded) or {}


def _json_load_list(text: str) -> list[Any]:
    loaded = json.loads(text)
    if isinstance(loaded, Sequence) and not isinstance(loaded, (str, bytes, bytearray)):
        loaded_seq: Sequence[Any] = cast(Sequence[Any], loaded)
        return list(loaded_seq)
    return []


def _request_json_dict() -> dict[str, Any]:
    try:
        data = request.get_json(silent=True)
        if isinstance(data, Mapping):
            data_dict: dict[Any, Any] = cast(dict[Any, Any], data)
            result: dict[str, Any] = {}
            for key, value in data_dict.items():
                result[str(key)] = value
            return result
    except Exception:  # noqa: S110
        pass
    return {}


def _request_header(name: str, default: str = "") -> str:
    value = request.headers.get(name)
    return value if isinstance(value, str) else default


def _request_form_text(name: str, default: str = "") -> str:
    value = request.form.get(name)
    return value if isinstance(value, str) else default


def _request_cookie_text(name: str, default: str = "") -> str:
    value = request.cookies.get(name)
    return value if isinstance(value, str) else default


# Keep this helper referenced so static analysis does not flag it as unused.
_ = _json_load_list
