import pytest

import web_ui.server as server


def test_health_endpoint_is_not_rate_limited() -> None:
    client = server.app.test_client()

    for _ in range(80):
        response = client.get("/api/health")
        assert response.status_code == 200


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [(None, 0), ("", 0), ("0", 0), ("1", 1), (" 2 ", 2), ("10", 10)],
)
def test_trusted_proxy_count_parsing(raw_value: str | None, expected: int) -> None:
    assert server._parse_trusted_proxy_count(raw_value) == expected


@pytest.mark.parametrize("raw_value", ["-1", "11", "not-a-number"])
def test_trusted_proxy_count_rejects_unsafe_values(raw_value: str) -> None:
    with pytest.raises(ValueError, match="UA_WEBUI_TRUSTED_PROXY_COUNT"):
        server._parse_trusted_proxy_count(raw_value)


def test_proxy_headers_are_ignored_without_explicit_trust() -> None:
    direct_app = object()

    assert server._apply_proxy_fix(direct_app, 0) is direct_app


def test_proxy_fix_uses_the_configured_hop_count(monkeypatch) -> None:
    captured: dict[str, object] = {}
    wrapped_app = object()

    def fake_proxy_fix(wsgi_app: object, **kwargs: int) -> object:
        captured["wsgi_app"] = wsgi_app
        captured.update(kwargs)
        return wrapped_app

    monkeypatch.setattr(server, "ProxyFix", fake_proxy_fix)
    direct_app = object()

    assert server._apply_proxy_fix(direct_app, 2) is wrapped_app
    assert captured == {
        "wsgi_app": direct_app,
        "x_for": 2,
        "x_proto": 2,
        "x_host": 2,
    }
