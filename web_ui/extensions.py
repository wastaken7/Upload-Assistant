"""Flask extensions shared by the Web UI app and its blueprints."""

from web_ui import security as security_mod
from web_ui.flask_compat import Limiter, _LimiterLike, get_remote_address

# Bound to the app with limiter.init_app() in web_ui.server.
limiter: _LimiterLike = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://",
)


def _rate_limit_key_func() -> str:
    """Rate limit key function that considers authentication status."""
    if security_mod._is_authenticated():
        return f"auth:{get_remote_address()}"
    return f"unauth:{get_remote_address()}"
