"""Flask and extension imports with the typed protocols the Web UI uses."""

import importlib
from collections.abc import Callable, Iterator, Mapping, Sequence
from types import ModuleType
from typing import Any, Protocol, TypedDict, TypeIs, TypeVar, overload

_T = TypeVar("_T")


def _is_str_dict(val: object) -> TypeIs[dict[str, Any]]:
    return isinstance(val, dict)


def _is_obj_dict(val: object) -> TypeIs[dict[object, object]]:
    return isinstance(val, dict)


def _is_str_mapping(val: object) -> TypeIs[Mapping[str, object]]:
    return isinstance(val, Mapping)


def _is_obj_list(val: object) -> TypeIs[list[object]]:
    return isinstance(val, list)


def _is_obj_sequence(val: object) -> TypeIs[Sequence[object]]:
    return isinstance(val, Sequence) and not isinstance(val, (str, bytes, bytearray))


def _module_name(*parts: str) -> str:
    return "".join(parts)


def _dynamic_import(module_name: str) -> ModuleType:
    return importlib.import_module(module_name)


class _AuthLike(Protocol):
    username: str | None
    password: str | None
    type: str


class _HeadersLike(Protocol):
    def get(self, key: str, default: str | None = None) -> str | None: ...
    def items(self) -> Sequence[tuple[str, str]]: ...


class _ArgsLike(Protocol):
    @overload
    def get(self, key: str) -> str | None: ...
    @overload
    def get(self, key: str, default: str) -> str: ...
    @overload
    def get(self, key: str, default: _T) -> str | _T: ...
    def get(self, key: str, default: object = None) -> object: ...
    def getlist(self, key: str) -> list[str]: ...
    def __getitem__(self, key: str) -> str: ...
    def __iter__(self) -> Iterator[str]: ...
    def __len__(self) -> int: ...


class _RequestLike(Protocol):
    headers: _HeadersLike
    form: Mapping[str, str]
    args: _ArgsLike
    cookies: Mapping[str, str]
    authorization: _AuthLike | None
    endpoint: str | None
    method: str
    path: str
    host: str
    host_url: str
    scheme: str
    remote_addr: str | None
    environ: Mapping[str, object]
    json: object | None

    def get_json(self, silent: bool = False) -> object | None: ...

    def get_data(self, as_text: bool = False) -> str: ...


class _ResponseLike(Protocol):
    status_code: int
    headers: dict[str, str]

    def set_cookie(self, key: str, value: str, max_age: int | None = None, httponly: bool = False, secure: bool = False, samesite: str | None = None) -> None: ...
    def delete_cookie(self, key: str) -> None: ...
    def get_json(self, silent: bool = False) -> object: ...


class _ConsoleLike(Protocol):
    def print(self, *args: object, **kwargs: object) -> object: ...
    def input(self, prompt: str = "") -> str: ...


class _PopenGroupKwargs(TypedDict, total=False):
    creationflags: int
    start_new_session: bool


class _WebUIProcess(Protocol):
    pid: int

    def poll(self) -> int | None: ...
    def wait(self, timeout: float | None = None) -> int: ...


class _SessionLike(Protocol):
    permanent: bool

    def __getitem__(self, key: str) -> object: ...
    def __setitem__(self, key: str, value: object) -> None: ...
    def __delitem__(self, key: str) -> None: ...
    def __iter__(self) -> Sequence[str]: ...
    def __len__(self) -> int: ...
    def get(self, key: str, default: object = ...) -> object: ...
    def pop(self, key: str, default: object = ...) -> object: ...
    def clear(self) -> None: ...


class _GLike(Protocol):
    authenticated: bool
    username: str | None


class _LimiterLike(Protocol):
    def init_app(self, app: object) -> None: ...

    def exempt(self, obj: Callable[..., object]) -> Callable[..., object]: ...

    def limit(
        self,
        limit_value: str,
        *,
        key_func: Callable[[], str] | None = None,
        error_message: str | None = None,
        override_defaults: bool = True,
        deduct_when: Callable[[_ResponseLike], bool] | None = None,
    ) -> Callable[[Callable[..., object]], Callable[..., object]]: ...


class _AccessLoggerLike(Protocol):
    def should_log(self, success: bool) -> bool: ...
    def get_level(self) -> str: ...
    def set_level(self, level: str) -> bool: ...
    def tail(self, n: int) -> list[object]: ...
    def log(
        self,
        *,
        endpoint: str,
        method: str,
        remote_addr: str | None,
        username: str | None,
        success: bool,
        status: int,
        headers: Mapping[str, object] | None,
        details: str | None,
    ) -> None: ...


pyotp = _dynamic_import(_module_name("py", "otp"))
flask = _dynamic_import(_module_name("fl", "ask"))
flask_cors = _dynamic_import(_module_name("flask", "_cors"))
flask_limiter = _dynamic_import(_module_name("flask", "_limiter"))
flask_limiter_util = _dynamic_import(_module_name("flask", "_limiter", ".util"))
werkzeug_security = _dynamic_import(_module_name("werkzeug", ".security"))
werkzeug_proxy_fix = _dynamic_import(_module_name("werkzeug", ".middleware", ".proxy_fix"))
flask_session = _dynamic_import(_module_name("flask", "_session"))

Blueprint: Callable[..., Any] = flask.Blueprint
Flask: Callable[[str], object] = flask.Flask
Response: Callable[..., _ResponseLike] = flask.Response
g: _GLike = flask.g
jsonify: Callable[..., _ResponseLike] = flask.jsonify
redirect: Callable[..., _ResponseLike] = flask.redirect
render_template: Callable[..., object] = flask.render_template
request: _RequestLike = flask.request
send_file: Callable[..., _ResponseLike] = flask.send_file
session: _SessionLike = flask.session
url_for: Callable[..., str] = flask.url_for
current_app: Any = flask.current_app
CORS: Callable[..., object] = flask_cors.CORS
Limiter: Callable[..., _LimiterLike] = flask_limiter.Limiter
get_remote_address: Callable[[], str] = flask_limiter_util.get_remote_address
safe_join: Callable[..., str | None] = werkzeug_security.safe_join
ProxyFix: Callable[..., object] = werkzeug_proxy_fix.ProxyFix
Session: Callable[..., object] = flask_session.Session
